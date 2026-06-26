"""Quarterly disclosure refresh. Updates source tables but deliberately never retrains models."""
from __future__ import annotations
import logging
import os
import pandas as pd
from . import fetch_announcements, fetch_fundamentals
from .fetch_external_real_factors import run as external_run
from .parse_chalco_production_reports import main as parse_chalco
from .parse_production_reports import main as parse_zijin
from .runtime import PROCESSED, REPORTS, read_parquet_or_empty
from .v2_production_common import write_markdown

def main() -> None:
    logging.basicConfig(level=logging.INFO)
    tasks=() if os.getenv("V2_OFFLINE_VALIDATE", "") == "1" else (fetch_announcements.main,fetch_fundamentals.main,parse_zijin,parse_chalco,external_run)
    for fn in tasks:
        try: fn()
        except Exception as exc: logging.exception("季度更新子任务失败（保留旧数据）: %s",exc)
    z=read_parquet_or_empty(PROCESSED/"v2_zijin_strict_production.parquet");c=read_parquet_or_empty(PROCESSED/"v2_chalco_strict_production.parquet")
    zcount=int(z.get("strict_usable",pd.Series(dtype=bool)).fillna(False).sum()) if not z.empty else 0
    ccount=int(c.get("strict_usable",pd.Series(dtype=bool)).fillna(False).sum()) if not c.empty else 0
    rows=pd.DataFrame([{"公司":"紫金矿业","严格产量记录":zcount,"模型状态":"strict production available" if zcount else "BLOCKED"},{"公司":"中国铝业","严格产量记录":ccount,"模型状态":"Model J 可复核" if ccount else "BLOCKED_MISSING_STRICT_VOLUME"}])
    write_markdown(REPORTS/"v2_quarterly_model_review.md","V2 季度模型复核","本任务仅刷新财报、公告和生产审计；财报更新后才允许由人工/独立工作流批准重训。",rows)
if __name__=="__main__":main()
