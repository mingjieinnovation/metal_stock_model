"""Read-only V2 model explanation report. Never refits or alters model outputs."""
from __future__ import annotations
import json, numpy as np, pandas as pd
from .runtime import PROCESSED, REPORTS, read_parquet_or_empty
from .v2_chalco_profit_v21 import _quarter_end_features
from .v2_zijin_profit_v21 import _data as zijin_data

OUT=REPORTS

def _coef(path):
 d=pd.read_csv(path);d=d[d.strict_status.eq('strict')];return json.loads(d.iloc[-1].ridge_coef_json) if len(d) else {}
def _r2(x,y):
 x=pd.to_numeric(x,errors='coerce');y=pd.to_numeric(y,errors='coerce');m=x.notna()&y.notna();return x[m].corr(y[m])**2 if m.sum()>2 else np.nan
def _row(company,version,model,factor,group,target,coef,stdcoef,corr,source,quality,proxy,meaning,expected):
 sign='positive' if coef>0 else 'negative' if coef<0 else 'zero';consistent=(expected=='mixed' or sign==expected)
 return {'company':company,'model_version':version,'model_name':model,'factor_name':factor,'factor_group':group,'target':target,'coefficient':coef,'standardized_coefficient':stdcoef,'coefficient_sign':sign,'expected_sign':expected,'sign_consistent':consistent,'correlation_with_target':corr,'univariate_r2':corr*corr if pd.notna(corr) else np.nan,'ablation_delta_mae':np.nan,'ablation_delta_rmse':np.nan,'ablation_delta_r2':np.nan,'permutation_importance_mean':np.nan,'permutation_importance_std':np.nan,'data_source':source,'data_quality_flag':quality,'is_proxy':proxy,'interpretation':meaning,'usage_recommendation':'保留并持续审计' if not proxy else '仅研究用途，优先替换为真实数据','analysis_status':'ABLATION_AND_PERMUTATION_NOT_COMPUTED_NO_RETRAIN','explanatory_power_grade':'PROXY_ONLY' if proxy else ('UNSTABLE' if not consistent else 'MEDIUM')}
def run():
 agg,fin,chalco=_quarter_end_features();zc_m,zc_f,zc_p,zijin=zijin_data(); rows=[]
 cc=_coef(OUT/'frequency_backtest_v2/monthly/walk_forward_strict/chalco_components.csv')
 cmap={'al_spread_q_mean':('商品利润','季度平均铝氧价差','positive','SHFE AL/AO','中'), 'alumina_price_q_mean':('成本/氧化铝业务','季度均价氧化铝','mixed','SHFE AO','中'), 'demand_score_q_mean':('需求','综合需求状态','positive','真实PMI/部分真实API+默认代理','低至中'), 'last_announced_q_profit_bn':('利润锚','最近已公告利润','positive','公告日约束财报','中高'), 'ttm_announced_profit_bn':('利润锚','已公告TTM利润','positive','公告日约束财报','中高'), 'last_2q_avg_profit_bn':('利润锚','近两季均值','positive','公告日约束财报','中高'), 'is_q1':('季节性','Q1虚拟变量','mixed','日历','高'),'is_q2':('季节性','Q2虚拟变量','mixed','日历','高'),'is_q3':('季节性','Q3虚拟变量','mixed','日历','高'),'is_q4':('季节性','Q4虚拟变量','mixed','日历','高')}
 for f,c in cc.items():
  g,mean,exp,src,q=cmap.get(f,('其他','模型特征','mixed','模型输出','中'));corr=chalco[f].corr(chalco.net_profit_q) if f in chalco else np.nan;rows.append(_row('中国铝业','V2.1-C','利润锚Ridge',f,g,'单季归母净利润(亿元)',c,corr,corr,src,q,'DEFAULT' in src,mean,exp))
 # V2.3 special diagnostic factors
 for f,g,mean,src,q,proxy in [('selected_k','动态成本权重','训练窗内部选择的氧化铝成本权重','V2.3候选窗口','中',False),('power_cost_proxy','成本','电力成本代理','缺真实电价','低',True),('anode_cost_proxy','成本','阳极成本代理','缺真实阳极价格','低',True),('primary_al_volume','产量','原铝产量','缺strict数据','低',True),('alumina_external_sales','销量','氧化铝外销量','缺strict数据','低',True)]:rows.append(_row('中国铝业','V2.3', '产业链分解',f,g,'单季归母净利润(亿元)',np.nan,np.nan,np.nan,src,q,proxy,mean,'mixed'))
 zc=_coef(OUT/'frequency_backtest_v2/monthly/walk_forward_strict/zijin_components.csv');zmap={'cu_au_revenue_index':('收入','铜金价格×strict产量收入环境','positive','SHFE铜+SGE Au99.99+PDF strict产量','中高',False),'revenue_x_demand':('交互','收入环境×需求状态','positive','收入指数+需求分数','低至中',True),'is_q4':('季节性','Q4虚拟变量','mixed','日历','高',False)}
 for f,c in zc.items():
  g,mean,exp,src,q,proxy=zmap.get(f,('其他','模型特征','mixed','模型','中',False));corr=zijin[f].corr(zijin.net_profit_q) if f in zijin else np.nan;std=c*zijin[f].std()/zijin.net_profit_q.std() if f in zijin else np.nan;rows.append(_row('紫金矿业','V2 strict','铜金收入Ridge',f,g,'单季归母净利润(亿元)',c,std,corr,src,q,proxy,mean,exp))
 # Demand components are explanatory-state inputs, not directly fitted profit coefficients.
 for f,g,mean,src,q,proxy in [('cu_price','价格','铜价工业金属景气','SHFE铜','中',False),('au_price_rmb_g','价格','金价人民币计价','SGE Au99.99','中高',False),('cu_ton','产量','矿产铜','PDF strict','高',False),('au_kg','产量','矿产金','PDF strict','高',False),('cu_demand_score','需求','铜需求子分数','真实库存/PMI+部分代理','低至中',True),('au_demand_score','需求','黄金需求子分数','名义利率代理/部分默认代理','低',True),('demand_score','需求','铜金加权需求分数','混合','低至中',True)]:rows.append(_row('紫金矿业','V2 strict','需求与收入状态',f,g,'单季归母净利润(亿元)',np.nan,np.nan,zijin[f].corr(zijin.net_profit_q) if f in zijin else np.nan,src,q,proxy,mean,'positive' if f not in ('au_demand_score','demand_score') else 'mixed'))
 df=pd.DataFrame(rows);df.to_csv(OUT/'v2_factor_explanatory_power.csv',index=False,encoding='utf-8-sig')
 md='# V2 因子解释力报告\n\n';md+='本报告只读取既有输出，不重新训练、不重新拟合、也不改写模型。Ablation 与 permutation 必须重训 walk-forward，依本轮限制统一标为 `NOT_COMPUTED_NO_RETRAIN`。\n\n'
 md+='## 中国铝业\n\n';md+='V2.1-C 是利润水平锚定模型：已公告单季利润、TTM、近两季均值降低高利润季系统性低估；季度平均铝氧价差反映截至当前时点的产业利润环境。它适合利润锚定，不适合单点交易信号。\n\n';md+='V2.2 的 E 高 full-sample TTM R² 仅是诊断；G 的 OOS 仍为负，因此只能 research_only。V2.3 的 selected_k=2.05 是训练窗内成本权重，不是物理消耗率；Model I 仍是电力/阳极 proxy，Model J 缺严格产销量必须 blocked，Model K 区间优于点估计。\n\n';md+='## 紫金矿业\n\n';md+='铜价和金价只有与 strict 矿产铜/金产量相乘后才构成收入环境。铜偏工业需求，金偏金融/避险；收入指数不等于真实营收，未扣成本、权益比例、税费、汇率和副产品。\n\n';md+='铜需求由库存、趋势、电网/工业、PMI、风险构成；黄金需求由利率、央行购金、ETF、美元和风险构成。真实库存/QVIX/名义利率代理已部分接入，但黄金ETF、美元等仍含代理，故 gap 应结合数据质量而不是机械交易。\n\n';(OUT/'v2_model_explanation.md').write_text(md,encoding='utf-8')
 fac='# V2 因子解释力逐项说明\n\n';
 for _,r in df.iterrows():fac+=f"### {r.company}｜{r.factor_name}\n- 经济含义：{r.interpretation}\n- 数据：{r.data_source}；质量：{r.data_quality_flag}；proxy：{r.is_proxy}\n- 系数/标准化系数：{r.coefficient} / {r.standardized_coefficient}；单变量R²：{r.univariate_r2}\n- 分级：{r.explanatory_power_grade}。未做 ablation/permutation（本轮禁止重训）。\n- 使用：{r.usage_recommendation}\n\n";
 (OUT/'v2_factor_explanatory_power.md').write_text(fac,encoding='utf-8')
 usage='# V2 模型使用指南\n\n## 紫金矿业\n- 月度用于估值中枢，周度用于交易观察，日度只做 gap alert。\n- 只有 strict production 可见、需求分数未被默认代理主导、gap<-12% 且铜金趋势确认时，才讨论低估观察；不是自动买卖。\n\n## 中国铝业\n- 当前不能用单点 gap 交易。优先使用 V2.3-K Bear/Base/Bull：低于 Bear 才是极端低估观察；Bear-Base 需基本面确认；Base-Bull 为合理区间；高于 Bull 表示高景气预期已较充分反映。\n- 只有 OOS季度≥10、OOS R²>0、MAPE≤15%、|Bias|≤3亿元且周月同向，才可 candidate_signal；当前不满足。\n';(OUT/'v2_model_usage_guide.md').write_text(usage,encoding='utf-8')
 lim='# V2 模型限制\n\n## 中铝\n- AO 历史短；2020-2023氧化铝历史不完整；无严格连续电价、阳极、原铝产量、氧化铝外销量。\n- 氧化铝和电解铝业务方向可能相反；会计项目、减值、投资收益和少数股东损益未充分建模；OOS季度很少。\n\n## 紫金\n- 铜金价格解释收入环境不等于利润；海外权益、税费、汇率和政治风险不完整。\n- real_rate 当前为名义美债收益率代理；ETF/美元仍可能缺失；PDF产量需要持续审计。\n';(OUT/'v2_model_limitations.md').write_text(lim,encoding='utf-8')
 nxt='# V2 后续升级路线\n\n## 中铝 P0\n1. 严格原铝产量、氧化铝产量/外销量；2. 电价、阳极、动力煤；3. 2020-2023氧化铝现货；4. 碳素、烧碱、铝土矿成本。\n\n## 中铝 P1/P2\n- 严格化 Model J，真实 power-adjusted spread，拆分氧化铝业务；月度区间、周度确认、日度报警；等待OOS扩大。\n\n## 紫金\n- 接入连续LME/SHFE/COMEX库存、美元、真实利率、黄金ETF持仓，维护PDF审计，补海外风险折扣。\n';(OUT/'v2_next_steps_for_model_upgrade.md').write_text(nxt,encoding='utf-8')
 return {'factors':len(df)}
def main():print(run())
if __name__=='__main__':main()
