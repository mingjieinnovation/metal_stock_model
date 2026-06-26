"""One auditable inventory of external factors, including explicit paid-data blocks."""
from __future__ import annotations
import os
import pandas as pd
from .fetch_fred_macro import run as fred_run
from .fetch_wgc_gold_etf import run as wgc_run
from .fetch_real_proxies import run as proxy_run
from .runtime import PROCESSED, REPORTS, read_parquet_or_empty, save_parquet
from .v2_production_common import source_record, write_markdown

PAID_CHALCO = ["动力煤价格", "预焙阳极价格", "烧碱价格", "铝土矿价格", "区域电价", "2020-2023氧化铝现货"]

def run() -> pd.DataFrame:
    frames = []
    if os.getenv("V2_SKIP_PUBLIC_PROXY_REFRESH", "").strip() != "1":
        try: proxy_run()
        except Exception: pass
    frames += [read_parquet_or_empty(PROCESSED / "fred_macro_features.parquet"), read_parquet_or_empty(PROCESSED / "wgc_gold_etf_monthly.parquet")]
    if frames[0].empty: frames[0] = fred_run()
    if frames[1].empty: frames[1] = wgc_run()
    rows=[]
    for item in PAID_CHALCO:
        has_token=any(os.getenv(k, "").strip() for k in ("SMM_TOKEN", "MYSTEEL_TOKEN", "BAICHUAN_TOKEN"))
        rows.append(source_record("SMM/Mysteel/Baichuan", "BLOCKED", is_proxy=False, flag="BLOCKED_NEEDS_PAID_DATA" if not has_token else "TOKEN_PRESENT_CONNECTOR_NOT_IMPLEMENTED", item=item))
    base=pd.concat([f for f in frames if not f.empty]+[pd.DataFrame(rows)],ignore_index=True,sort=False)
    save_parquet(base,PROCESSED/"v2_real_factors.parquet")
    summary=base.groupby(["source_type","data_quality_flag"],dropna=False).size().reset_index(name="记录数") if not base.empty else base
    write_markdown(REPORTS/"v2_real_factor_status.md","V2 外部真实因子状态","本表不将缺失付费数据伪装成代理。FRED、WGC 和公开库存等数据均保留来源状态。",summary)
    return base

def main() -> None: print({"rows":len(run())})
if __name__=="__main__":main()
