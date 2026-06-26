"""Fetch auditable FRED macro series; a missing key is a visible BLOCKED state."""
from __future__ import annotations
import os
import pandas as pd
import requests

from .runtime import CACHE, RAW, PROCESSED, read_parquet_or_empty, save_parquet, write_status
from .v2_production_common import source_record

SERIES = {"DFII10": ("us_10y_real_yield", False), "DGS10": ("us_10y_nominal_yield", False),
          "DTWEXBGS": ("usd_index", False), "DEXCHUS": ("usd_cny", False)}


def _api(series: str, key: str) -> pd.DataFrame:
    response = requests.get("https://api.stlouisfed.org/fred/series/observations", params={
        "series_id": series, "api_key": key, "file_type": "json", "observation_start": "2020-01-01"}, timeout=30)
    response.raise_for_status()
    data = response.json().get("observations", [])
    out = pd.DataFrame(data)
    if out.empty: return out
    return pd.DataFrame({"available_date": pd.to_datetime(out["date"], errors="coerce"),
                         "value": pd.to_numeric(out["value"], errors="coerce")}).dropna()


def run() -> pd.DataFrame:
    key = os.getenv("FRED_API_KEY", "").strip(); rows = []
    if not key:
        rows = [source_record(name, "BLOCKED", is_proxy=(name == "us_10y_nominal_yield"),
                              flag="MISSING_FRED_API_KEY", item=name) for name, _ in SERIES.values()]
        out = pd.DataFrame(rows); save_parquet(out, PROCESSED / "fred_macro_features.parquet"); return out
    try:
        for series, (name, _) in SERIES.items():
            raw = _api(series, key)
            for r in raw.itertuples(index=False):
                rows.append(source_record(f"FRED:{series}", "API", available_date=r.available_date,
                                          is_proxy=(series == "DGS10"), item=name, value=r.value,
                                          flag="NOMINAL_RATE_PROXY" if series == "DGS10" else ""))
        out = pd.DataFrame(rows)
        save_parquet(out, RAW / "fred_macro_daily.parquet"); save_parquet(out, CACHE / "fred_macro_daily_cache.parquet")
        save_parquet(out, PROCESSED / "fred_macro_features.parquet"); write_status("fred_macro", "FRED_API", True, f"{len(out)} rows")
    except Exception as exc:
        out = read_parquet_or_empty(CACHE / "fred_macro_daily_cache.parquet")
        if out.empty:
            out = pd.DataFrame([source_record("FRED", "BLOCKED", flag=f"FRED_API_FAILED:{type(exc).__name__}", item="fred_macro")])
        else:
            out["source_type"] = "CACHE"; out["data_quality_flag"] = "FRED_API_FAILED_USING_CACHE"
        save_parquet(out, PROCESSED / "fred_macro_features.parquet"); write_status("fred_macro", "CACHE" if not out.empty else "BLOCKED", not out.empty, str(exc))
    return out


def main() -> None: print({"rows": len(run())})
if __name__ == "__main__": main()
