from __future__ import annotations

import logging
from datetime import date, timedelta

import pandas as pd

from .fetchers import fetch_shfe_future
from .runtime import CACHE, RAW, call_with_timeout, ensure_layout, save_parquet, write_status

CONTRACTS = {"al": ("AL0", "AL", "沪铝0"), "cu": ("CU0", "CU", "沪铜0"), "ao": ("AO0", "AO", "氧化铝0"), "au": ("AU0", "AU", "沪金0")}


def _column(frame: pd.DataFrame, names: tuple[str, ...]) -> str | None:
    lookup = {str(c).strip().lower(): c for c in frame.columns}
    return next((lookup[n.lower()] for n in names if n.lower() in lookup), None)


def _select_daily_main(frame: pd.DataFrame, product: str) -> pd.DataFrame:
    product_col = _column(frame, ("symbol", "合约", "合约代码"))
    date_col = _column(frame, ("date", "日期", "交易日期"))
    close_col = _column(frame, ("close", "收盘价", "收盘"))
    if not all((product_col, date_col, close_col)):
        raise ValueError("SHFE daily response lacks contract/date/close fields")
    candidates = frame[frame[product_col].astype(str).str.upper().str.startswith(product.upper())].copy()
    if candidates.empty:
        raise ValueError(f"No {product} contracts in SHFE response")
    rank_col = _column(candidates, ("open_interest", "持仓量")) or _column(candidates, ("volume", "成交量"))
    candidates[date_col] = pd.to_datetime(candidates[date_col], errors="coerce")
    candidates[close_col] = pd.to_numeric(candidates[close_col], errors="coerce")
    candidates = candidates.dropna(subset=[date_col, close_col])
    if rank_col:
        candidates[rank_col] = pd.to_numeric(candidates[rank_col], errors="coerce").fillna(-1)
        candidates = candidates.sort_values([date_col, rank_col]).groupby(date_col, as_index=False).tail(1)
    else:
        candidates = candidates.sort_values(date_col).drop_duplicates(date_col, keep="last")
    return candidates[[date_col, close_col]].rename(columns={date_col: "date", close_col: "close"})


def _fetch_all_contracts(start: date, end: date) -> pd.DataFrame:
    import akshare as ak
    return call_with_timeout(ak.get_futures_daily, start_date=start.strftime("%Y%m%d"), end_date=end.strftime("%Y%m%d"), market="SHFE")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    ensure_layout()
    start, end = date.today() - timedelta(days=365 * 6), date.today()
    all_contracts = None
    try:
        all_contracts = _fetch_all_contracts(start, end)
    except Exception as exc:
        logging.warning("Full SHFE daily endpoint unavailable; falling back to continuous contracts: %s", exc)
    for product, aliases in CONTRACTS.items():
        try:
            if all_contracts is not None and not all_contracts.empty:
                frame, source = _select_daily_main(all_contracts, product), "API_SHFE"
            else:
                frame, source = call_with_timeout(fetch_shfe_future, aliases, start, end), "API_SHFE_MAIN_CONTINUOUS"
            frame["contract_product"], frame["source"] = product.upper(), source
            save_parquet(frame, RAW / f"shfe_{product}_main_daily.parquet")
            save_parquet(frame, CACHE / f"shfe_{product}_main_api_cache.parquet")
            write_status(f"shfe_{product}", source, True, f"{len(frame)} rows")
        except Exception as exc:
            write_status(f"shfe_{product}", "CACHE", False, str(exc))
            logging.warning("%s update failed; keeping cache: %s", product.upper(), exc)


if __name__ == "__main__":
    main()

