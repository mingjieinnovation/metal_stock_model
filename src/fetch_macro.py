from __future__ import annotations

import logging
import re
from datetime import date, timedelta

import pandas as pd

from .fetchers import fetch_stock_history
from .runtime import CACHE, RAW, call_with_timeout, ensure_layout, read_parquet_or_empty, save_parquet, write_status


def _find(frame: pd.DataFrame, *tokens: str) -> str | None:
    for column in frame.columns:
        text = str(column)
        if all(token in text for token in tokens):
            return column
    return None


def fetch_pmi() -> pd.DataFrame:
    import akshare as ak
    frame = call_with_timeout(ak.macro_china_pmi)
    date_col = _find(frame, "\u6708") or frame.columns[0]
    pmi_col = _find(frame, "\u5236\u9020\u4e1a", "\u6307\u6570")
    if not pmi_col: raise ValueError("PMI manufacturing index column absent")
    dates = frame[date_col].astype(str).str.extract(r"(20\d{2}).*?(\d{1,2})").astype(float)
    output = pd.DataFrame({"date": pd.to_datetime(dict(year=dates[0], month=dates[1], day=1), errors="coerce") + pd.offsets.MonthEnd(0), "pmi": pd.to_numeric(frame[pmi_col], errors="coerce"), "pmi_forecast": pd.NA, "pmi_prev": pd.NA, "source": "API_EASTMONEY"})
    return output.dropna(subset=["date", "pmi"]).sort_values("date")


def fetch_hs300() -> pd.DataFrame:
    start, end = date(2020, 1, 1), date.today()
    try:
        raw = call_with_timeout(fetch_stock_history, "000300", start, end)
        raw = raw.rename(columns={"close": "close"})
        raw["source"] = "API_EASTMONEY"
        for column in ("open", "high", "low", "volume"):
            if column not in raw: raw[column] = pd.NA
        return raw[["date", "open", "close", "high", "low", "volume", "source"]]
    except Exception:
        import akshare as ak
        raw = call_with_timeout(ak.stock_zh_index_daily_em, symbol="sh000300", start_date="20200101")
        cols = {str(c).lower(): c for c in raw.columns}; date_col = cols.get("date") or raw.columns[0]; close_col = cols.get("close") or next(c for c in raw.columns if "\u6536\u76d8" in str(c))
        output = raw.rename(columns={date_col: "date", close_col: "close"}); output["source"] = "API_EASTMONEY"
        for column in ("open", "high", "low", "volume"):
            if column not in output: output[column] = pd.NA
        return output[["date", "open", "close", "high", "low", "volume", "source"]]


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s"); ensure_layout()
    for name, fetcher in (("china_pmi_monthly", fetch_pmi), ("hs300_daily", fetch_hs300)):
        try:
            data = fetcher(); save_parquet(data, RAW / f"{name}.parquet"); save_parquet(data, CACHE / f"{name}_api_cache.parquet"); write_status(name, "API_EASTMONEY", True, f"{len(data)} rows")
        except Exception as exc:
            cached = read_parquet_or_empty(CACHE / f"{name}_api_cache.parquet")
            write_status(name, "CACHE", not cached.empty, str(exc)); logging.warning("%s failed; retained cache: %s", name, exc)


if __name__ == "__main__":
    main()
