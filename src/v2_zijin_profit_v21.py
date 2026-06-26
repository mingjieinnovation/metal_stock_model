"""Zijin V2.1: strict production, real-proxy demand and announced-profit anchors."""
from __future__ import annotations
import json
import numpy as np
import pandas as pd
from sklearn.linear_model import RidgeCV
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from .runtime import PROCESSED, REPORTS, read_parquet_or_empty, save_parquet
from .v2_walk_forward import ALPHAS, MIN_TRAIN_QUARTERS, _financial, _strict_production

SHARES=265.91
A=['cu_au_revenue_index','revenue_x_demand','is_q4']
B=['cu_au_revenue_index','revenue_x_demand','last_announced_q_profit_bn','ttm_announced_profit_bn','last_2q_avg_profit_bn','is_q1','is_q2','is_q3','is_q4']

def _anchors(fin,when):
 v=fin[fin.financial_available_date<=when].sort_values('financial_available_date').net_profit_q.astype(float).tail(4)
 return {'last_announced_q_profit_bn':v.iloc[-1] if len(v) else np.nan,'ttm_announced_profit_bn':v.sum() if len(v)==4 else np.nan,'last_2q_avg_profit_bn':v.tail(2).mean() if len(v)>=2 else np.nan}

def _data():
 m=read_parquet_or_empty(PROCESSED/'v2_zijin_monthly_market.parquet').copy();m.date=pd.to_datetime(m.date);m['quarter']=m.date.dt.to_period('Q').dt.end_time.dt.normalize()
 q=m.groupby('quarter',as_index=False).agg(cu_price=('cu_price','mean'),au_price_rmb_g=('au_price_rmb_g','mean'),demand_score=('demand_score','mean'))
 for n in (1,2,3,4):q[f'is_q{n}']=q.quarter.dt.quarter.eq(n).astype(int)
 fin=_financial('601899');prod=_strict_production()[['quarter','cu_ton','au_kg','production_available_date']]
 d=q.merge(fin,on='quarter',how='inner').merge(prod,on='quarter',how='inner');d['cu_au_revenue_index']=(d.cu_ton*d.cu_price+d.au_kg*1000*d.au_price_rmb_g)/1e9;d['revenue_x_demand']=d.cu_au_revenue_index*(d.demand_score-.5);d['training_available_date']=d[['financial_available_date','production_available_date']].max(axis=1)
 d=pd.concat([d,pd.DataFrame([_anchors(fin,x) for x in d.quarter])],axis=1);return m,fin,prod,d

def _fit(train,row,features):
 p=Pipeline([('scale',StandardScaler()),('ridge',RidgeCV(alphas=ALPHAS))]);p.fit(train[features],train.net_profit_q);return float(p.predict(pd.DataFrame([row[features]],columns=features))[0]),p

def _walk(d,model,features):
 rows=[]
 for _,t in d.sort_values('quarter').iterrows():
  h=d[d.training_available_date<=t.quarter].dropna(subset=features+['net_profit_q'])
  if len(h)<MIN_TRAIN_QUARTERS:continue
  pred,p=_fit(h,t,features);r=p.named_steps['ridge'];rows.append({'quarter':t.quarter,'model':model,'q_profit_pred_bn':pred,'actual_q_profit_bn':t.net_profit_q,'last_announced_q_profit_bn':t.last_announced_q_profit_bn,'train_quarters_count':len(h),'ridge_alpha':r.alpha_,'ridge_coef_json':json.dumps(dict(zip(features,r.coef_)),ensure_ascii=False)})
 return pd.DataFrame(rows)

def _metrics(x):
 e=x.q_profit_pred_bn-x.actual_q_profit_bn;den=np.sum((x.actual_q_profit_bn-x.actual_q_profit_bn.mean())**2);r2=np.nan if len(x)<2 or den==0 else 1-np.sum(e**2)/den;da=(np.sign(x.q_profit_pred_bn-x.last_announced_q_profit_bn)==np.sign(x.actual_q_profit_bn-x.last_announced_q_profit_bn)).mean()
 return {'model':x.model.iloc[0],'n':len(x),'mae':abs(e).mean(),'mape':(abs(e)/x.actual_q_profit_bn).mean(),'bias':e.mean(),'walk_forward_oos_r2':r2,'directional_accuracy':da}

def run():
 m,fin,prod,d=_data();a=_walk(d,'A_strict_cu_au_revenue',A);b=_walk(d,'B_strict_revenue_profit_anchor',B);walk=pd.concat([a,b],ignore_index=True);met=pd.DataFrame([_metrics(x) for _,x in walk.groupby('model')]);selected=met.sort_values(['mape','bias'],key=lambda x:abs(x) if x.name=='bias' else x).iloc[0].model
 latest=m.iloc[-1].copy();visible=prod[prod.production_available_date<=latest.date].sort_values('production_available_date').iloc[-1];latest['cu_ton']=visible.cu_ton;latest['au_kg']=visible.au_kg;latest['cu_au_revenue_index']=(latest.cu_ton*latest.cu_price+latest.au_kg*1000*latest.au_price_rmb_g)/1e9;latest['revenue_x_demand']=latest.cu_au_revenue_index*(latest.demand_score-.5);latest['quarter']=latest.date.to_period('Q').end_time.normalize();
 for n in (1,2,3,4):latest[f'is_q{n}']=int(latest.quarter.quarter==n)
 for k,v in _anchors(fin,latest.date).items():latest[k]=v
 feat=A if selected.startswith('A') else B;train=d[d.training_available_date<=latest.date].dropna(subset=feat+['net_profit_q']);q,p=_fit(train,latest,feat);pe=float(np.clip(11+4*(latest.demand_score-.5)+.5-.3,8.5,15));price=q*4/SHARES*pe;sel=met[met.model.eq(selected)].iloc[0];status='candidate_signal' if sel.n>=10 and sel.walk_forward_oos_r2>0 and sel.mape<=.15 and abs(sel.bias)<=3 else 'research_only_or_valuation_anchor_only';pred=pd.DataFrame([{'date':latest.date,'selected_model':selected,'q_profit_pred_bn':q,'annual_profit_pred_bn':q*4,'eps_pred':q*4/SHARES,'target_pe':pe,'model_price':price,'gap':latest.actual_stock_close_raw/price-1,'signal_status':status,'production_strict_usable':True,'production_available_date':visible.production_available_date,'data_quality_flag':latest.data_quality_flag,'train_quarters_count':len(train)}]);
 met['latest_model_price']=np.where(met.model.eq(selected),price,np.nan);met['signal_status']=np.where(met.model.eq(selected),status,'comparison_only');met.to_csv(REPORTS/'v2_zijin_profit_v21_model_comparison.csv',index=False,encoding='utf-8-sig');walk.to_csv(REPORTS/'v2_zijin_profit_v21_walkforward.csv',index=False,encoding='utf-8-sig');save_parquet(pred,PROCESSED/'v2_zijin_profit_v21_predictions.parquet');text='# Zijin V2.1 strict profit-model update\n\n';text+=f'- Selected model: `{selected}`; OOS quarters {int(sel.n)}; OOS R² {sel.walk_forward_oos_r2:.3f}; MAPE {sel.mape:.1%}; bias {sel.bias:.2f} bn RMB.\n';text+=f'- Latest q profit {q:.2f} bn RMB; model price {price:.2f}; strict production available {visible.production_available_date.date()}.\n';text+=f'- Signal status: `{status}`. Strict production is real PDF-derived; demand score is mixed real API/default proxy and is labelled row by row.\n';(REPORTS/'v2_zijin_profit_v21_summary.md').write_text(text,encoding='utf-8');return {'selected_model':selected,'oos_rows':len(walk),'latest_model_price':round(price,4)}
def main():print(run())
if __name__=='__main__':main()
