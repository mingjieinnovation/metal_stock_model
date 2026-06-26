"""WGC ETF loader with explicit cookie/cache/blocked provenance."""
from __future__ import annotations
import os
import pandas as pd
import requests

from .runtime import CACHE, RAW, PROCESSED, read_parquet_or_empty, save_parquet, write_status
from .v2_production_common import source_record


def run() -> pd.DataFrame:
    cache = CACHE / "wgc_gold_etf_monthly_cache.parquet"; cookie = os.getenv("WGC_COOKIE", "").strip()
    if not cookie:
        old = read_parquet_or_empty(cache)
        if old.empty:
            out = pd.DataFrame([source_record("WGC", "BLOCKED", is_proxy=True, flag="MISSING_WGC_DATA;MISSING_WGC_COOKIE", item="gold_etf")])
        else:
            out = old.copy(); out["source_type"] = "CACHE"; out["data_quality_flag"] = "WGC_COOKIE_MISSING_USING_CACHE"
        save_parquet(out, PROCESSED / "wgc_gold_etf_monthly.parquet"); write_status("wgc_gold_etf", "CACHE" if not old.empty else "BLOCKED", not old.empty, "WGC_COOKIE missing")
        return out
    url = os.getenv("WGC_GOLD_ETF_URL", "").strip()
    if not url:
        out = pd.DataFrame([source_record("WGC", "BLOCKED", is_proxy=True, flag="WGC_URL_NOT_CONFIGURED", item="gold_etf")])
        save_parquet(out, PROCESSED / "wgc_gold_etf_monthly.parquet"); return out
    try:
        response = requests.get(url, headers={"Cookie": cookie, "User-Agent": "Mozilla/5.0"}, timeout=30); response.raise_for_status()
        excel = RAW / "wgc_gold_etf.xlsx"; excel.write_bytes(response.content)
        raw = pd.read_excel(excel); date = next(c for c in raw if "date" in str(c).lower() or "日期" in str(c)); value = next(c for c in raw if "hold" in str(c).lower() or "吨" in str(c))
        out = pd.DataFrame([source_record("WGC", "API", available_date=d, item="gold_etf_holdings", value=v) for d, v in zip(raw[date], raw[value]) if pd.notna(v)])
        save_parquet(out, cache); save_parquet(out, PROCESSED / "wgc_gold_etf_monthly.parquet"); write_status("wgc_gold_etf", "WGC", True, f"{len(out)} rows")
    except Exception as exc:
        out = read_parquet_or_empty(cache)
        if out.empty: out = pd.DataFrame([source_record("WGC", "BLOCKED", is_proxy=True, flag=f"WGC_DOWNLOAD_FAILED:{type(exc).__name__}", item="gold_etf")])
        else: out["source_type"] = "CACHE"; out["data_quality_flag"] = "WGC_DOWNLOAD_FAILED_USING_CACHE"
        save_parquet(out, PROCESSED / "wgc_gold_etf_monthly.parquet"); write_status("wgc_gold_etf", "CACHE", not out.empty, str(exc))
    return out


def main() -> None: print({"rows": len(run())})
if __name__ == "__main__": main()
