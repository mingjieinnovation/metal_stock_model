"""Weekly observation report; does not retrain or emit a direct trade order."""
from __future__ import annotations
import pandas as pd
from .runtime import PROCESSED, REPORTS, read_parquet_or_empty, save_parquet
from .v2_data_layer import build
from .v2_production_common import write_markdown

def main() -> None:
    build(("weekly",)); c=read_parquet_or_empty(PROCESSED/"v2_chalco_weekly_market.parquet");z=read_parquet_or_empty(PROCESSED/"v2_zijin_weekly_market.parquet");v=read_parquet_or_empty(PROCESSED/"v2_chalco_profit_v23_predictions.parquet");zp=read_parquet_or_empty(PROCESSED/"v2_zijin_profit_v21_predictions.parquet");rows=[]
    if not c.empty:
        r=c.iloc[-1];base=float(v.iloc[-1].base_price) if not v.empty else float("nan");deteriorating=len(c)>1 and r.al_spread<c.iloc[-2].al_spread
        status="weekly_candidate_observation" if pd.notna(base) and r.actual_stock_close_raw<base and not deteriorating else "research_only"
        rows.append({"公司":"中国铝业","日期":r.date,"周末价格":r.actual_stock_close_raw,"4周均价":c.actual_stock_close_raw.tail(4).mean(),"13周铝价趋势":r.al_price_trend_score,"QTD铝价差":c[c.date.dt.quarter.eq(r.date.quarter)].al_spread.mean(),"状态":status,"限制":"仅交易观察，需月度估值未高估"})
    if not z.empty:
        r=z.iloc[-1];model=float(zp.iloc[-1].model_price) if not zp.empty else float("nan");gap=r.actual_stock_close_raw/model-1 if model else float("nan");default="DEFAULT_PROXY" in str(r.data_quality_flag)
        status="weekly_undervalued_observation" if gap<-.12 and not default else "watch_only"
        rows.append({"公司":"紫金矿业","日期":r.date,"周末价格":r.actual_stock_close_raw,"4周均价":z.actual_stock_close_raw.tail(4).mean(),"13周铜价趋势":r.cu_price_trend_score,"周度gap":gap,"状态":status,"限制":"默认代理主导时自动降级"})
    out=pd.DataFrame(rows);save_parquet(out,PROCESSED/"v2_weekly_features.parquet");write_markdown(REPORTS/"v2_weekly_signal.md","V2 周度信号观察","周度仅用于交易观察；不等于交易指令。",out)
if __name__=="__main__":main()
