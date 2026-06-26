from __future__ import annotations

import logging
import shutil
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

from .runtime import CACHE, RAW, REPORTS, call_with_timeout, ensure_layout, read_parquet_or_empty, save_parquet, write_status

CODES = {"601600": "\u4e2d\u56fd\u94dd\u4e1a", "601899": "\u7d2b\u91d1\u77ff\u4e1a", "000300": "\u6caa\u6df1300"}
RAW_STOCK_DIR = RAW / "stock_daily_raw"
CACHE_STOCK_DIR = CACHE / "stock_daily_raw"
INVALID_DIR = CACHE / "invalid_adjusted"
SCHEMA = ["date", "code", "open", "high", "low", "close", "volume", "amount", "pct_chg", "provider", "adjust", "fetched_at", "data_quality_flag"]


def _column(frame: pd.DataFrame, names: tuple[str, ...]) -> str | None:
    mapping = {str(c).strip().lower(): c for c in frame.columns}
    for name in names:
        if name.lower() in mapping: return mapping[name.lower()]
    return next((c for c in frame.columns if any(name.lower() in str(c).lower() for name in names)), None)


def normalize_stock_df(df: pd.DataFrame, code: str, provider: str, adjust: str) -> pd.DataFrame:
    if adjust != "none": raise ValueError("Stock prices must be raw/unadjusted: adjust must be 'none'")
    date_col = _column(df, ("date", "\u65e5\u671f")); close_col = _column(df, ("close", "\u6536\u76d8", "\u6536\u76d8\u4ef7"))
    if not date_col or not close_col: raise ValueError(f"Missing date/close columns from {provider}: {list(df.columns)}")
    aliases = {"open": ("open", "\u5f00\u76d8", "\u5f00\u76d8\u4ef7"), "high": ("high", "\u6700\u9ad8", "\u6700\u9ad8\u4ef7"), "low": ("low", "\u6700\u4f4e", "\u6700\u4f4e\u4ef7"), "volume": ("volume", "\u6210\u4ea4\u91cf"), "amount": ("amount", "\u6210\u4ea4\u989d"), "pct_chg": ("pct_chg", "\u6da8\u8dcc\u5e45", "\u6da8\u8dcc\u5e45%")}
    out = pd.DataFrame({"date": pd.to_datetime(df[date_col], errors="coerce"), "code": code, "close": pd.to_numeric(df[close_col], errors="coerce")})
    for field, names in aliases.items():
        column = _column(df, names); out[field] = pd.to_numeric(df[column], errors="coerce") if column else pd.NA
    out["provider"], out["adjust"], out["fetched_at"], out["data_quality_flag"] = provider, adjust, datetime.now(timezone.utc).isoformat(), ""
    out = out.dropna(subset=["date", "close"]).sort_values("date").drop_duplicates("date", keep="last")
    if out.empty: raise ValueError(f"{provider} produced no usable raw-price rows")
    return out.reindex(columns=SCHEMA)


def fetch_by_efinance_raw(code: str, start: str, end: str) -> pd.DataFrame:
    import efinance as ef
    frame = call_with_timeout(ef.stock.get_quote_history, stock_codes=code, beg=start, end=end, klt=101, fqt=0)
    return normalize_stock_df(frame, code, "efinance_eastmoney", "none")


def fetch_by_akshare_eastmoney_raw(code: str, start: str, end: str) -> pd.DataFrame:
    import akshare as ak
    frame = call_with_timeout(ak.stock_zh_a_hist, symbol=code, period="daily", start_date=start, end_date=end, adjust="")
    return normalize_stock_df(frame, code, "akshare_eastmoney", "none")


def to_tencent_symbol(code: str) -> str:
    return ("sh" if code.startswith(("6", "000300")) else "sz") + code


def fetch_by_akshare_tencent_raw(code: str, start: str, end: str) -> pd.DataFrame:
    import akshare as ak
    frame = call_with_timeout(ak.stock_zh_a_hist_tx, symbol=to_tencent_symbol(code), start_date=start, end_date=end, adjust="")
    return normalize_stock_df(frame, code, "akshare_tencent", "none")


def read_valid_cache(code: str, max_age_days: int = 10) -> pd.DataFrame:
    frame = read_parquet_or_empty(CACHE_STOCK_DIR / f"{code}.parquet", SCHEMA)
    if frame.empty: raise FileNotFoundError(f"No raw cache for {code}")
    if "adjust" not in frame or set(frame["adjust"].dropna().astype(str)) != {"none"}: raise ValueError("cache adjustment is not none")
    if "provider" not in frame or frame["provider"].isna().any() or (frame["provider"].astype(str).str.strip() == "").any(): raise ValueError("cache provider missing")
    last = pd.to_datetime(frame["date"], errors="coerce").max()
    if pd.isna(last) or last.date() < date.today() - timedelta(days=max_age_days): raise ValueError(f"cache stale: {last}")
    return frame.reindex(columns=SCHEMA)


def fetch_stock_raw_with_fallback(code: str, start: str, end: str) -> pd.DataFrame:
    errors = []
    for provider in (fetch_by_efinance_raw, fetch_by_akshare_eastmoney_raw, fetch_by_akshare_tencent_raw):
        try: return provider(code, start, end)
        except Exception as exc: errors.append(f"{provider.__name__}: {exc}")
    try: return read_valid_cache(code)
    except Exception as exc: errors.append(f"cache: {exc}")
    raise RuntimeError(" | ".join(errors))


def invalidate_adjusted_cache() -> pd.DataFrame:
    ensure_layout(); RAW_STOCK_DIR.mkdir(parents=True, exist_ok=True); CACHE_STOCK_DIR.mkdir(parents=True, exist_ok=True); INVALID_DIR.mkdir(parents=True, exist_ok=True)
    records = []
    candidates = list(RAW.glob("stock*.csv")) + list(RAW.glob("stock*.parquet")) + list(CACHE.glob("stock*.csv")) + list(CACHE.glob("stock*.parquet"))
    for path in candidates:
        if INVALID_DIR in path.parents: continue
        invalid, reason = False, ""
        name = path.name.lower()
        if any(x in name for x in ("qfq", "hfq", "adjusted")): invalid, reason = True, "filename_adjusted"
        else:
            try:
                frame = pd.read_csv(path) if path.suffix == ".csv" else read_parquet_or_empty(path)
                adjust = set(frame.get("adjust", pd.Series(dtype=str)).dropna().astype(str).str.lower())
                if not adjust: invalid, reason = True, "legacy_adjustment_unknown"
                elif adjust != {"none"}: invalid, reason = True, f"adjust={adjust}"
            except Exception as exc: invalid, reason = True, f"unreadable:{exc}"
        if invalid:
            destination = INVALID_DIR / path.name
            if destination.exists(): destination = INVALID_DIR / f"{path.stem}_{datetime.now().strftime('%Y%m%d%H%M%S')}{path.suffix}"
            shutil.move(str(path), str(destination)); records.append({"original_path": str(path), "invalid_path": str(destination), "reason": reason, "invalidated_at": datetime.now(timezone.utc).isoformat()})
    report = pd.DataFrame(records, columns=["original_path", "invalid_path", "reason", "invalidated_at"])
    report.to_csv(REPORTS / "invalidated_stock_cache.csv", index=False, encoding="utf-8-sig")
    return report


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s"); ensure_layout(); invalidate_adjusted_cache(); RAW_STOCK_DIR.mkdir(parents=True, exist_ok=True); CACHE_STOCK_DIR.mkdir(parents=True, exist_ok=True)
    start, end = "20200101", date.today().strftime("%Y%m%d")
    for code in CODES:
        try:
            data = fetch_stock_raw_with_fallback(code, start, end)
            save_parquet(data, RAW_STOCK_DIR / f"{code}.parquet"); save_parquet(data, CACHE_STOCK_DIR / f"{code}.parquet")
            write_status(f"stock_raw_{code}", data.provider.iloc[-1], True, f"{len(data)} raw rows through {data.date.max()}")
        except Exception as exc:
            write_status(f"stock_raw_{code}", "UNAVAILABLE", False, str(exc)); logging.error("Raw stock price unavailable for %s: %s", code, exc)


if __name__ == "__main__":
    main()
