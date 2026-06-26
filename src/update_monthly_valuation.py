"""Monthly valuation anchor report using existing V2 model artifacts only."""
from __future__ import annotations
import numpy as np
import pandas as pd
from .runtime import PROCESSED, REPORTS, read_parquet_or_empty, save_parquet
from .v2_data_layer import build
from .v2_production_common import write_markdown

def main() -> None:
    build(("monthly",)); c=read_parquet_or_empty(PROCESSED/"v2_chalco_monthly_market.parquet");z=read_parquet_or_empty(PROCESSED/"v2_zijin_monthly_market.parquet");v=read_parquet_or_empty(PROCESSED/"v2_chalco_profit_v23_predictions.parquet");zp=read_parquet_or_empty(PROCESSED/"v2_zijin_profit_v21_predictions.parquet");rows=[]
    if not c.empty and not v.empty:
        r,p=c.iloc[-1],v.iloc[-1];actual=float(r.actual_stock_close_raw);bear,base,bull=float(p.bear_price),float(p.base_price),float(p.bull_price);zone="extreme_undervaluation_observation" if actual<bear else "undervalued_but_requires_fundamental_confirmation" if actual<base else "fair_value_zone" if actual<=bull else "strong_cycle_expectation_priced_in"
        rows.append({"公司":"中国铝业","日期":r.date,"实际价格":actual,"bear_price":bear,"base_price":base,"bull_price":bull,"price_zone":zone,"信号":"valuation_anchor_only","说明":"只使用 V2.3-K 区间，不使用单点 gap 交易"})
    if not z.empty and not zp.empty:
        r,p=z.iloc[-1],zp.iloc[-1];actual=float(r.actual_stock_close_raw);model=float(p.model_price);proxy=str(r.data_quality_flag).split("DEFAULT_PROXY:")[-1].split(";")[0];ratio=len([x for x in proxy.split(",") if x])/7
        rows.append({"公司":"紫金矿业","日期":r.date,"实际价格":actual,"model_price":model,"gap":actual/model-1,"proxy_ratio":ratio,"signal_confidence":"low" if ratio>.5 else "medium","信号":"valuation_observation","说明":"严格产量可用；需求代理占比高时降级"})
    out=pd.DataFrame(rows);save_parquet(out,PROCESSED/"v2_monthly_valuation.parquet");write_markdown(REPORTS/"v2_monthly_valuation.md","V2 月度估值", "中铝使用 Bear/Base/Bull 区间；紫金为严格产量支撑的估值观察。",out)
if __name__=="__main__":main()
