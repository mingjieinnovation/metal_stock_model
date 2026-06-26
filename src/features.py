from __future__ import annotations

from pathlib import Path

import pandas as pd

from .config import MANUAL_ALUMINA_FILE
from .io_utils import read_csv_if_exists


def daily_to_month_end(frame: pd.DataFrame, value_name: str) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame(columns=["date", value_name])
    result = frame[["date", value_name]].copy()
    result["date"] = pd.to_datetime(result["date"], errors="coerce")
    result[value_name] = pd.to_numeric(result[value_name], errors="coerce")
    result = result.dropna().set_index("date").sort_index()
    return result.resample("ME").last().reset_index()


def load_raw_monthly(raw_path: Path, value_name: str) -> pd.DataFrame:
    frame = read_csv_if_exists(raw_path)
    if frame.empty:
        raise FileNotFoundError(f"Missing raw data: {raw_path}")
    source_value = value_name if value_name in frame.columns else "close"
    return daily_to_month_end(frame, source_value).rename(columns={source_value: value_name})


def load_manual_alumina(manual_dir: Path) -> pd.DataFrame:
    path = manual_dir / MANUAL_ALUMINA_FILE
    frame = read_csv_if_exists(path)
    if frame.empty:
        return pd.DataFrame(columns=["date", "alumina_price"])
    date_column = "date" if "date" in frame.columns else "month"
    value_column = "alumina_price" if "alumina_price" in frame.columns else "price"
    return daily_to_month_end(frame.rename(columns={date_column: "date", value_column: "alumina_price"}), "alumina_price")


def choose_alumina(ao_monthly: pd.DataFrame, manual_monthly: pd.DataFrame) -> pd.DataFrame:
    """Prefer AO futures, filling absent monthly history from manual spot data."""
    ao = ao_monthly.rename(columns={"close": "alumina_price"})[["date", "alumina_price"]]
    manual = manual_monthly[["date", "alumina_price"]]
    joined = ao.merge(manual, on="date", how="outer", suffixes=("_ao", "_manual"))
    joined["alumina_price"] = joined["alumina_price_ao"].combine_first(joined["alumina_price_manual"])
    return joined[["date", "alumina_price"]].sort_values("date")


def build_chalco_features(raw_dir: Path, manual_dir: Path, five_year_start: pd.Timestamp) -> pd.DataFrame:
    stock = load_raw_monthly(raw_dir / "stock_601600.csv", "stock_close")
    aluminium = load_raw_monthly(raw_dir / "shfe_al.csv", "al_price")
    try:
        ao = load_raw_monthly(raw_dir / "shfe_ao.csv", "close")
    except FileNotFoundError:
        ao = pd.DataFrame(columns=["date", "close"])
    alumina = choose_alumina(ao, load_manual_alumina(manual_dir))
    result = stock.merge(aluminium, on="date", how="inner").merge(alumina, on="date", how="inner")
    result["al_spread"] = result["al_price"] - 1.925 * result["alumina_price"]
    return result[result["date"] >= five_year_start].dropna().sort_values("date")


def build_zijin_features(raw_dir: Path, five_year_start: pd.Timestamp) -> pd.DataFrame:
    stock = load_raw_monthly(raw_dir / "stock_601899.csv", "stock_close")
    copper = load_raw_monthly(raw_dir / "shfe_cu.csv", "cu_price")
    gold = load_raw_monthly(raw_dir / "sge_au9999.csv", "au_price_rmb_g")
    result = stock.merge(copper, on="date", how="inner").merge(gold, on="date", how="inner")
    return result[result["date"] >= five_year_start].dropna().sort_values("date")
