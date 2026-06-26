from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Callable

import pandas as pd

logger = logging.getLogger(__name__)
DATE_ALIASES = ("date", "日期", "时间", "交易日期")
CLOSE_ALIASES = ("close", "收盘", "收盘价", "最新价", "price", "价格")


def _find_column(frame: pd.DataFrame, aliases: tuple[str, ...]) -> str:
    lookup = {str(column).strip().lower(): column for column in frame.columns}
    for alias in aliases:
        if alias.lower() in lookup:
            return lookup[alias.lower()]
    raise KeyError(f"None of {aliases} found in columns {list(frame.columns)}")


def standardise_price_frame(frame: pd.DataFrame, price_name: str) -> pd.DataFrame:
    """Convert provider-specific date/closing-price columns to a stable schema."""
    if frame is None or frame.empty:
        raise ValueError("provider returned an empty dataframe")
    date_column = _find_column(frame, DATE_ALIASES)
    close_column = _find_column(frame, CLOSE_ALIASES)
    result = frame[[date_column, close_column]].copy()
    result.columns = ["date", price_name]
    result["date"] = pd.to_datetime(result["date"], errors="coerce")
    result[price_name] = pd.to_numeric(result[price_name], errors="coerce")
    result = result.dropna(subset=["date", price_name])
    if result.empty:
        raise ValueError("no valid date/price observations after normalisation")
    return result


def fetch_stock_history(code: str, start: date, end: date) -> pd.DataFrame:
    import efinance as ef

    frame = ef.stock.get_quote_history(
        stock_codes=code,
        beg=start.strftime("%Y%m%d"),
        end=end.strftime("%Y%m%d"),
        klt=101,
    )
    return standardise_price_frame(frame, "close")


def _call_futures_hist_em(contract: str, start: date, end: date) -> pd.DataFrame:
    import akshare as ak

    kwargs = {
        "symbol": contract,
        "period": "daily",
        "start_date": start.strftime("%Y%m%d"),
        "end_date": end.strftime("%Y%m%d"),
    }
    try:
        return ak.futures_hist_em(**kwargs, adjust="")
    except TypeError as exc:
        if "adjust" not in str(exc):
            raise
        return ak.futures_hist_em(**kwargs)


def _call_futures_main_sina(contract: str, start: date, end: date) -> pd.DataFrame:
    import akshare as ak

    try:
        return ak.futures_main_sina(
            symbol=contract,
            start_date=start.strftime("%Y%m%d"),
            end_date=end.strftime("%Y%m%d"),
        )
    except TypeError:
        return ak.futures_main_sina(symbol=contract)


def fetch_shfe_future(contracts: tuple[str, ...], start: date, end: date) -> pd.DataFrame:
    """Retrieve a SHFE main-continuous series with AKShare fallbacks."""
    attempts: list[tuple[str, Callable[..., pd.DataFrame]]] = []
    for contract in contracts:
        attempts.extend([(contract, _call_futures_hist_em), (contract, _call_futures_main_sina)])
    errors: list[str] = []
    for contract, method in attempts:
        try:
            frame = method(contract, start, end)
            result = standardise_price_frame(frame, "close")
            result = result[(result["date"].dt.date >= start) & (result["date"].dt.date <= end)]
            if not result.empty:
                logger.info("Fetched futures contract %s via %s", contract, method.__name__)
                return result
        except Exception as exc:
            errors.append(f"{contract}/{method.__name__}: {exc}")
    raise RuntimeError("All AKShare futures attempts failed: " + " | ".join(errors))


def fetch_sge_au9999(start: date, end: date) -> pd.DataFrame:
    import akshare as ak

    frame = ak.spot_hist_sge(symbol="Au99.99")
    result = standardise_price_frame(frame, "au_price_rmb_g")
    return result[(result["date"].dt.date >= start) & (result["date"].dt.date <= end)]


def five_year_start(today: date | None = None) -> date:
    # Fetch an extra year to make the reporting window robust to gaps.
    return (today or date.today()) - timedelta(days=365 * 6)



