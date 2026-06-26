"""Fetch auditable public macro/industry proxy inputs without overwriting old data on failure."""
from __future__ import annotations

import logging
import re
from datetime import timedelta

import pandas as pd

from .runtime import CACHE, PROCESSED, call_with_timeout, read_parquet_or_empty, save_parquet, write_status

OUT = PROCESSED / "real_proxy_observations.parquet"


def _date(series: pd.Series) -> pd.Series:
    numeric = pd.to_numeric(series, errors="coerce")
    if numeric.notna().mean() > .8 and numeric.dropna().abs().median() > 1e10:
        return pd.to_datetime(numeric, unit="ms", errors="coerce")
    parsed = pd.to_datetime(series, errors="coerce")
    if parsed.notna().any(): return parsed
    parts = series.astype(str).str.extract(r"(20\d{2})[^0-9]*(\d{1,2})")
    return pd.to_datetime(dict(year=pd.to_numeric(parts[0]), month=pd.to_numeric(parts[1]), day=1), errors="coerce") + pd.offsets.MonthEnd(0)


def _monthly(frame: pd.DataFrame, date_col: str, value_col: str, target: str, source: str, delay_days: int = 30) -> pd.DataFrame:
    out = pd.DataFrame({"observation_date": _date(frame[date_col]), target: pd.to_numeric(frame[value_col], errors="coerce")}).dropna()
    out["available_date"] = out["observation_date"] + pd.Timedelta(days=delay_days); out[f"{target}_source"] = source
    return out


def _daily(frame: pd.DataFrame, date_col: str, value_col: str, target: str, source: str) -> pd.DataFrame:
    out = pd.DataFrame({"observation_date": _date(frame[date_col]), target: pd.to_numeric(frame[value_col], errors="coerce")}).dropna()
    out["available_date"] = out["observation_date"]; out[f"{target}_source"] = source
    return out


def _fetch() -> list[pd.DataFrame]:
    import akshare as ak
    records = []
    for symbol, target in (("沪铝", "al_inventory"), ("沪铜", "cu_inventory")):
        raw = call_with_timeout(ak.futures_inventory_em, symbol)
        records.append(_daily(raw, "日期", "库存", target, "AKSHARE_EASTMONEY_FUTURES_INVENTORY"))
    power = call_with_timeout(ak.macro_china_society_electricity)
    records.append(_monthly(power, "统计时间", "第二产业用电量同比", "industry_power_yoy", "AKSHARE_SINA_SOCIAL_ELECTRICITY"))
    prop = call_with_timeout(ak.macro_china_real_estate)
    records.append(_monthly(prop, "日期", "最新值", "property_sentiment", "AKSHARE_EASTMONEY_REAL_ESTATE"))
    gold = call_with_timeout(ak.macro_china_foreign_exchange_gold)
    records.append(_monthly(gold, "统计时间", "黄金储备", "central_bank_gold_reserve", "AKSHARE_SINA_CENTRAL_BANK_GOLD"))
    nev = call_with_timeout(ak.car_market_fuel_cpca, "整体市场")
    nev_value = "NEV" if "NEV" in nev.columns else next(c for c in nev.columns if c != "月份")
    records.append(_monthly(nev, "月份", nev_value, "nev_share", "AKSHARE_CPCA_NEV_SHARE"))
    qvix = call_with_timeout(ak.index_option_300etf_qvix)
    records.append(_daily(qvix, "date", "close", "qvix", "AKSHARE_QVIX_300ETF"))
    rates = call_with_timeout(ak.bond_zh_us_rate, "20200101")
    records.append(_daily(rates, "日期", "美国国债收益率10年", "us10y_nominal_yield", "AKSHARE_EASTMONEY_US10Y_NOMINAL_PROXY"))
    return records


def run() -> dict[str, int]:
    try:
        frames = _fetch()
        # Combine sources by availability date without losing fields that happen
        # to arrive on different calendars. First non-null is safe because each
        # source contributes one observation per available date.
        stacked = pd.concat(frames, ignore_index=True, sort=False)
        result = stacked.groupby("available_date", as_index=False).agg(lambda s: s.dropna().iloc[0] if s.notna().any() else pd.NA)
        result = result.sort_values("available_date")
        result = result.sort_values("available_date").drop_duplicates(["available_date"], keep="last")
        save_parquet(result, OUT); save_parquet(result, CACHE / "real_proxy_observations_cache.parquet")
        write_status("real_proxy_observations", "MULTI_API", True, f"{len(result)} rows")
    except Exception as exc:
        cached = read_parquet_or_empty(CACHE / "real_proxy_observations_cache.parquet")
        if cached.empty: raise
        result = cached; write_status("real_proxy_observations", "CACHE", True, str(exc)); logging.warning("Real proxy update failed; keeping cache: %s", exc)
    return {"rows": len(result), "columns": len(result.columns)}


def main() -> None: print(run())
if __name__ == "__main__": main()


