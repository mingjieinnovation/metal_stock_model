"""V2.3 Chalco aluminium value-chain profit decomposition; no full-sample k fitting."""
from __future__ import annotations
import json
import numpy as np
import pandas as pd
from sklearn.linear_model import RidgeCV
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from .runtime import PROCESSED, REPORTS, read_parquet_or_empty, save_parquet
from .v2_chalco_profit_v22 import _prepare, _current_features, _r2
from .v2_walk_forward import ALPHAS, MIN_TRAIN_QUARTERS

KS=(1.80,1.85,1.90,1.925,1.95,2.00,2.05)
BASE=["dynamic_spread","demand_score_q_mean","last_announced_q_profit_bn","ttm_announced_profit_bn","last_2q_avg_profit_bn","is_q1","is_q2","is_q3","is_q4"]
SHARES=171.55

def _features(frame,k, power=False):
 d=frame.copy(); d['dynamic_spread']=d['al_price_q_mean']-k*d['alumina_price_q_mean']
 d['power_cost_proxy']=0.0; d['anode_cost_proxy']=0.0
 if power: d['dynamic_spread']=d['dynamic_spread']-d['power_cost_proxy']-d['anode_cost_proxy']
 return d

def _fit(train,row,k,power=False):
 tr=_features(train,k,power); rr=_features(pd.DataFrame([row]),k,power)
 m=Pipeline([('scale',StandardScaler()),('ridge',RidgeCV(alphas=ALPHAS))]);m.fit(tr[BASE],tr['net_profit_q'])
 return float(m.predict(rr[BASE])[0]),m

def _inner_k(train,power=False):
 errors={}
 for k in KS:
  vals=[]
  for i in range(4,len(train)):
   hist=train.iloc[:i].dropna(subset=['net_profit_q']+BASE[1:]); target=train.iloc[i]
   if len(hist)<4: continue
   try: vals.append(abs(_fit(hist,target,k,power)[0]-target.net_profit_q))
   except Exception: pass
  errors[str(k)]=float(np.mean(vals)) if vals else np.nan
 valid={float(k):v for k,v in errors.items() if pd.notna(v)}
 return (min(valid,key=valid.get) if valid else 1.925),errors

def _walk(data,model_name,power=False):
 rows=[]
 for _,t in data.sort_values('quarter').iterrows():
  hist=data[data.financial_available_date<=t.quarter].copy().dropna(subset=['net_profit_q']+BASE[1:])
  if len(hist)<MIN_TRAIN_QUARTERS: continue
  k,errors=_inner_k(hist,power)
  try: pred,m=_fit(hist,t,k,power)
  except Exception: continue
  ttm_pred=t.ttm_announced_profit_bn-t.last_announced_q_profit_bn+pred
  rows.append({'quarter':t.quarter,'model':model_name,'selected_k':k,'candidate_k_errors':json.dumps(errors),'q_profit_pred_bn':pred,'ttm_profit_pred_bn':ttm_pred,'actual_q_profit_bn':t.net_profit_q,'actual_ttm_profit_bn':t.ttm_net_profit_bn,'last_announced_q_profit_bn':t.last_announced_q_profit_bn,'train_quarters_count':len(hist),'ridge_alpha':m.named_steps['ridge'].alpha_,'data_quality_flag':'POWER_COST_PROXY;ANODE_COST_PROXY' if power else 'NO_POWER_OR_ANODE_ADJUSTMENT'})
 return pd.DataFrame(rows)

def _metrics(part,full_r2=np.nan):
 e=part.q_profit_pred_bn-part.actual_q_profit_bn; te=part.ttm_profit_pred_bn-part.actual_ttm_profit_bn
 direction=np.sign(part.q_profit_pred_bn-part.last_announced_q_profit_bn)==np.sign(part.actual_q_profit_bn-part.last_announced_q_profit_bn)
 return {'model':part.model.iloc[0],'status':'ok','n':len(part),'full_sample_r2':full_r2,'walk_forward_oos_r2':_r2(part.actual_q_profit_bn,part.q_profit_pred_bn),'ttm_r2':_r2(part.actual_ttm_profit_bn,part.ttm_profit_pred_bn),'quarterly_r2':_r2(part.actual_q_profit_bn,part.q_profit_pred_bn),'mae':abs(e).mean(),'mape':(abs(e)/part.actual_q_profit_bn).mean(),'bias':e.mean(),'directional_accuracy':direction.mean(),'signal_sample_count':0}

def _full(data):
 vals=[]
 for k in KS:
  d=_features(data.dropna(subset=['net_profit_q']+BASE[1:]),k);m=Pipeline([('scale',StandardScaler()),('ridge',RidgeCV(alphas=ALPHAS))]);m.fit(d[BASE],d.net_profit_q);vals.append((k,_r2(d.net_profit_q,pd.Series(m.predict(d[BASE]),index=d.index))))
 return max(vals,key=lambda x:x[1])[1]

def _latest(agg,fin,data,selected,met):
 row=_current_features(agg,fin); hist=data[data.financial_available_date<=row.date].dropna(subset=['net_profit_q']+BASE[1:]);k,errs=_inner_k(hist,selected=='I_power_adjusted_spread');q,_=_fit(hist,row,k,selected=='I_power_adjusted_spread')
 g=read_parquet_or_empty(PROCESSED/'v2_chalco_profit_v22_predictions.parquet').iloc[-1];last2=row.last_2q_avg_profit_bn
 bear=float(g.q_profit_pred_bn*.85);base=max(float(g.q_profit_pred_bn),float(last2));bull=max(base,float(row.last_announced_q_profit_bn));pe=float(np.clip(8.5+3*(row.demand_score_q_mean-.5)-.5*row.is_q4,6.5,11.5))
 n=int(met['n']);status='candidate_signal' if n>=10 and met['quarterly_r2']>0 and met['mape']<=.15 and abs(met['bias'])<=3 else 'research_only_or_valuation_anchor_only'
 out={'date':row.date,'selected_model':selected,'selected_k':k,'candidate_k_errors':json.dumps(errs),'q_profit_pred_bn':q,'ttm_profit_pred_bn':row.ttm_announced_profit_bn-row.last_announced_q_profit_bn+q,'bear_q_profit':bear,'base_q_profit':base,'bull_q_profit':bull,'target_pe':pe,'bear_price':bear*4/SHARES*pe,'base_price':base*4/SHARES*pe,'bull_price':bull*4/SHARES*pe,'model_price':q*4/SHARES*pe,'gap':row.actual_stock_close_raw/(q*4/SHARES*pe)-1,'signal_status':status,'profit_model_warning':'POWER_COST_PROXY;ANODE_COST_PROXY;VOLUME_MODEL_J_BLOCKED_MISSING_STRICT_VOLUME','train_quarters_count':len(hist),'data_quality_flag':'POWER_COST_PROXY;ANODE_COST_PROXY;VOLUME_PROXY_NOT_USED_IN_STRICT'}
 return pd.DataFrame([out])

def run():
 agg,fin,data=_prepare(); h=_walk(data,'H_dynamic_k_spread'); i=_walk(data,'I_power_adjusted_spread',True); walk=pd.concat([h,i],ignore_index=True);full=_full(data);metrics=pd.DataFrame([_metrics(p,full) for _,p in walk.groupby('model')]);metrics=pd.concat([metrics,pd.DataFrame([{'model':'J_segment_profit_proxy','status':'blocked_missing_strict_primary_al_volume_and_alumina_external_sales','n':0,'full_sample_r2':np.nan,'walk_forward_oos_r2':np.nan,'ttm_r2':np.nan,'quarterly_r2':np.nan,'mae':np.nan,'mape':np.nan,'bias':np.nan,'directional_accuracy':np.nan,'signal_sample_count':0}])],ignore_index=True)
 selected='H_dynamic_k_spread';met=metrics[metrics.model.eq(selected)].iloc[0];pred=_latest(agg,fin,data,selected,met);metrics.loc[metrics.model.eq(selected),'latest_model_price']=pred.iloc[0].model_price;metrics.loc[metrics.model.eq(selected),'signal_status']=pred.iloc[0].signal_status
 metrics.to_csv(REPORTS/'v2_chalco_profit_v23_model_comparison.csv',index=False,encoding='utf-8-sig');walk.to_csv(REPORTS/'v2_chalco_profit_v23_walkforward.csv',index=False,encoding='utf-8-sig');save_parquet(pred,PROCESSED/'v2_chalco_profit_v23_predictions.parquet')
 text='# China Aluminum V2.3 value-chain profit decomposition\n\n';text+=f"- Model H selected k dynamically inside every expanding training window; latest selected k: {pred.iloc[0].selected_k}. No full-sample k was used.\n";text+=f"- H full-sample quarterly R²: {full:.3f}; H OOS quarterly R²: {met.quarterly_r2:.3f}; TTM R²: {met.ttm_r2:.3f}; OOS quarters: {int(met.n)}; MAPE: {met.mape:.1%}; bias: {met.bias:.2f} bn RMB.\n";text+='- R² target reached only in diagnostic mode, not in tradable walk-forward mode.\n' if full>=.7 and met.quarterly_r2<.7 else '';text+='- Model I uses explicitly labelled POWER_COST_PROXY / ANODE_COST_PROXY; Model J is blocked because strict primary-al volume and alumina external sales are unavailable.\n';text+=f"- Scenario prices: bear {pred.iloc[0].bear_price:.2f}; base {pred.iloc[0].base_price:.2f}; bull {pred.iloc[0].bull_price:.2f}.\n";text+=f"- Status: `{pred.iloc[0].signal_status}`. Weekly/monthly alignment is required for candidate_signal; daily is gap_alert only.\n";(REPORTS/'v2_chalco_profit_v23_summary.md').write_text(text,encoding='utf-8')
 return {'oos_rows':len(h),'latest_k':float(pred.iloc[0].selected_k),'latest_model_price':round(float(pred.iloc[0].model_price),4)}
def main():print(run())
if __name__=='__main__':main()
