"""Build normalized V2 market inputs at daily, weekly and monthly frequency."""
from __future__ import annotations

import numpy as np
import pandas as pd

from .runtime import PROCESSED, RAW, read_parquet_or_empty, save_parquet
from .v2_model_core import chalco_demand, zijin_demand, rolling_score

FREQUENCIES = ("daily", "weekly", "monthly")


def _read_stock(code: str) -> pd.DataFrame:
    daily = read_parquet_or_empty(RAW / "stock_daily_raw" / f"{code}.parquet")
    if daily.empty:
        return pd.DataFrame(columns=["date", "actual_stock_close_raw"])
    daily = daily[["date", "close"]].copy(); daily["date"] = pd.to_datetime(daily["date"])
    return daily.rename(columns={"close": "actual_stock_close_raw"}).sort_values("date").drop_duplicates("date", keep="last")


def _read_price(name: str, output_col: str, value_col: str = "close") -> pd.DataFrame:
    daily = pd.read_csv(RAW / name, usecols=["date", value_col])
    daily["date"] = pd.to_datetime(daily["date"])
    return daily.rename(columns={value_col: output_col}).sort_values("date").drop_duplicates("date", keep="last")


def _asof_datetime(frame: pd.DataFrame, column: str) -> pd.DataFrame:
    """Use one timestamp precision before as-of joins (pandas requires an exact match)."""
    result = frame.copy()
    result[column] = pd.to_datetime(result[column], errors="coerce").astype("datetime64[ns]")
    return result.dropna(subset=[column]).sort_values(column)


def _backward_price_join(left: pd.DataFrame, right: pd.DataFrame) -> pd.DataFrame:
    """Use the last observable market close, never a future quote."""
    return pd.merge_asof(_asof_datetime(left, "date"), _asof_datetime(right, "date"), on="date", direction="backward")


def _pmi_asof(left: pd.DataFrame) -> pd.DataFrame:
    pmi = read_parquet_or_empty(RAW / "china_pmi_monthly.parquet")
    if pmi.empty:
        left = left.copy(); left["pmi"] = pd.NA; return left
    pmi = pmi[["date", "pmi"]].copy(); pmi["date"] = pd.to_datetime(pmi["date"])
    return _backward_price_join(left, pmi)


def _real_proxy_asof(left: pd.DataFrame) -> pd.DataFrame:
    proxy = read_parquet_or_empty(PROCESSED / "real_proxy_observations.parquet")
    if proxy.empty: return left
    proxy = _asof_datetime(proxy, "available_date")
    return pd.merge_asof(_asof_datetime(left, "date"), proxy, left_on="date", right_on="available_date", direction="backward")

def _real_score(series: pd.Series, frequency: str, default: float, inverse: bool=False) -> pd.Series:
    window = {"daily": 756, "weekly": 156, "monthly": 36}[frequency]
    score = rolling_score(pd.to_numeric(series, errors="coerce"), window)
    if inverse: score = 1 - score
    return score.fillna(default)

def _set_score(frame: pd.DataFrame, output: str, source: str, frequency: str, default: float, inverse: bool=False) -> None:
    value = pd.to_numeric(frame.get(source, pd.Series(np.nan, index=frame.index)), errors="coerce")
    frame[output] = _real_score(value, frequency, default, inverse)
    frame[f"{output}_source"] = np.where(value.notna(), f"REAL_API:{source}", "DEFAULT_PROXY")

def _flags(frame: pd.DataFrame, score_columns: list[str]) -> pd.Series:
    def one(row):
        real = [c.removesuffix("_score") for c in score_columns if str(row.get(f"{c}_source", "")).startswith("REAL_API")]
        defaults = [c.removesuffix("_score") for c in score_columns if not str(row.get(f"{c}_source", "")).startswith("REAL_API")]
        return "REAL_API:" + ",".join(real) + ";DEFAULT_PROXY:" + ",".join(defaults) + ";MARKET_ASOF_BACKWARD;PROXY_ASOF_BACKWARD"
    return frame.apply(one, axis=1)

def _resample(frame: pd.DataFrame, frequency: str) -> pd.DataFrame:
    if frequency == "daily":
        return frame.copy()
    rule = "W-FRI" if frequency == "weekly" else "ME"
    last_date = frame["date"].max()
    sampled = frame.set_index("date").resample(rule).last().reset_index()
    # The current week/month is not complete when its period label exceeds the
    # last observed trading date. Dropping it prevents a future-labelled signal.
    return sampled[sampled["date"] <= last_date].dropna(subset=["actual_stock_close_raw"]).reset_index(drop=True)


def _quality_flag(frame: pd.DataFrame, default_fields: list[str]) -> pd.Series:
    return "DEFAULT_PROXY:" + ",".join(default_fields) + ";MARKET_ASOF_BACKWARD;PMI_ASOF_BACKWARD"


def strict_production() -> pd.DataFrame:
    production = read_parquet_or_empty(PROCESSED / "production_quarterly.parquet")
    if production.empty:
        return production
    production = production.copy(); production["code"] = production["code"].astype(str).str.zfill(6); production["quarter"] = pd.to_datetime(production["quarter"])
    production = production[(production["code"] == "601899") & production["strict_usable"].fillna(False)]
    production = production[production["source_period"].astype(str).str.contains("STRICT_SINGLE|2026Q1", regex=True, na=False)].drop_duplicates("quarter", keep="last")
    announcements = read_parquet_or_empty(PROCESSED / "announcement_index.parquet")
    if not announcements.empty:
        announcements = announcements.copy(); announcements["code"] = announcements["code"].astype(str).str.zfill(6); announcements["announcement_time"] = pd.to_datetime(announcements["announcement_time"], errors="coerce")
        announcements = announcements[announcements["code"] == "601899"]
        announcements["quarter"] = pd.to_datetime(announcements["report_year"].astype(int).astype(str) + "-" + (announcements["report_quarter"].astype(int) * 3).astype(str) + "-01") + pd.offsets.MonthEnd(0)
        dates = announcements.groupby("quarter", as_index=False)["announcement_time"].min().rename(columns={"announcement_time": "production_available_date"})
        production = production.merge(dates, on="quarter", how="left")
    else:
        production["production_available_date"] = pd.NaT
    days = production["quarter"].dt.quarter.map({1: 45, 2: 60, 3: 45, 4: 120})
    production["production_available_date"] = pd.to_datetime(production["production_available_date"], errors="coerce").fillna(production["quarter"] + pd.to_timedelta(days, unit="D"))
    production["effective_date"] = production["production_available_date"]
    return production.sort_values("production_available_date").reset_index(drop=True)


def _chalco_daily() -> pd.DataFrame:
    market = _read_stock("601600")
    market = _backward_price_join(market, _read_price("shfe_al.csv", "al_price"))
    market = _backward_price_join(market, _read_price("shfe_ao.csv", "alumina_price"))
    market = _pmi_asof(market)
    market = _real_proxy_asof(market)
    market["al_spread"] = market["al_price"] - 1.925 * market["alumina_price"]
    return market.dropna(subset=["al_price", "alumina_price"])


def _zijin_daily() -> pd.DataFrame:
    market = _read_stock("601899")
    market = _backward_price_join(market, _read_price("shfe_cu.csv", "cu_price"))
    market = _backward_price_join(market, _read_price("sge_au9999.csv", "au_price_rmb_g", "au_price_rmb_g"))
    market = _pmi_asof(market)
    market = _real_proxy_asof(market)
    return market.dropna(subset=["cu_price", "au_price_rmb_g"])


def _finish_chalco(frame: pd.DataFrame, frequency: str) -> pd.DataFrame:
    frame = _resample(frame, frequency)
    _set_score(frame, "inventory_score", "al_inventory", frequency, .5, inverse=True)
    _set_score(frame, "grid_proxy_score", "industry_power_yoy", frequency, .55)
    _set_score(frame, "nev_proxy_score", "nev_share", frequency, .55)
    _set_score(frame, "property_proxy_score", "property_sentiment", frequency, .45)
    frame = chalco_demand(frame, frequency)
    frame["al_spread_k"] = frame["al_spread"] / 1000.0; frame["alumina_price_k"] = frame["alumina_price"] / 1000.0
    frame["is_q4"] = frame["date"].dt.quarter.eq(4).astype(int); frame["alumina_price_source"] = "SHFE_AO"
    frame["data_quality_flag"] = _flags(frame, ["inventory_score", "grid_proxy_score", "nev_proxy_score", "property_proxy_score"])
    return frame



def _finish_zijin(frame: pd.DataFrame, frequency: str) -> pd.DataFrame:
    frame = _resample(frame, frequency)
    _set_score(frame, "cu_inventory_score", "cu_inventory", frequency, .5, inverse=True)
    _set_score(frame, "power_grid_proxy_score", "industry_power_yoy", frequency, .55)
    _set_score(frame, "risk_score", "qvix", frequency, .5, inverse=True)
    _set_score(frame, "real_rate_score", "us10y_nominal_yield", frequency, .5, inverse=True)
    gold_change = pd.to_numeric(frame.get("central_bank_gold_reserve"), errors="coerce").diff()
    frame["central_bank_gold_proxy_score"] = _real_score(gold_change, frequency, .6)
    frame["central_bank_gold_proxy_score_source"] = np.where(gold_change.notna(), "REAL_API:central_bank_gold_reserve_change", "DEFAULT_PROXY")
    _set_score(frame, "gold_etf_proxy_score", "gold_etf_holdings", frequency, .55)
    _set_score(frame, "usd_score", "usd_index", frequency, .5, inverse=True)
    frame = zijin_demand(frame, frequency)
    frame["is_q4"] = frame["date"].dt.quarter.eq(4).astype(int)
    frame["data_quality_flag"] = _flags(frame, ["cu_inventory_score", "power_grid_proxy_score", "risk_score", "real_rate_score", "central_bank_gold_proxy_score", "gold_etf_proxy_score", "usd_score"])
    return frame



def build(frequencies: tuple[str, ...] = FREQUENCIES) -> dict[str, int]:
    chalco_daily, zijin_daily = _chalco_daily(), _zijin_daily()
    result: dict[str, int] = {}
    for frequency in frequencies:
        if frequency not in FREQUENCIES:
            raise ValueError(f"Unsupported frequency: {frequency}")
        chalco = _finish_chalco(chalco_daily, frequency); zijin = _finish_zijin(zijin_daily, frequency)
        save_parquet(chalco, PROCESSED / f"v2_chalco_{frequency}_market.parquet")
        save_parquet(zijin, PROCESSED / f"v2_zijin_{frequency}_market.parquet")
        result[f"chalco_{frequency}"] = len(chalco); result[f"zijin_{frequency}"] = len(zijin)
    production = strict_production(); save_parquet(production, PROCESSED / "v2_zijin_strict_production.parquet")
    result["strict_production_quarters"] = len(production)
    return result


if __name__ == "__main__":
    print(build())


