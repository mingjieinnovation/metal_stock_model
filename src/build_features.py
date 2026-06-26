from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import pandas as pd

from .runtime import FALLBACK, PROCESSED, RAW, ensure_layout, read_parquet_or_empty, save_parquet, write_status


def _monthly_to_quarter(frame: pd.DataFrame, value: str) -> pd.DataFrame:
    if frame.empty: return pd.DataFrame(columns=["quarter", value])
    data = frame.copy(); data["date"] = pd.to_datetime(data["date"], errors="coerce")
    data[value] = pd.to_numeric(data[value], errors="coerce")
    data = data.dropna(subset=["date", value]).set_index("date")
    return data[value].resample("QE").last().rename(value).reset_index().rename(columns={"date": "quarter"})


def _raw_price(product: str, target: str) -> pd.DataFrame:
    new = read_parquet_or_empty(RAW / f"shfe_{product}_main_daily.parquet")
    if new.empty:
        legacy = RAW / f"shfe_{product}.csv"
        new = pd.read_csv(legacy) if legacy.exists() else pd.DataFrame(columns=["date", "close"])
    if "close" not in new and target in new: new = new.rename(columns={target: "close"})
    return _monthly_to_quarter(new.rename(columns={"close": target}), target)


def _stock_price(code: str) -> pd.DataFrame:
    frame = read_parquet_or_empty(RAW / f"stock_{code}.parquet")
    if frame.empty:
        legacy = RAW / f"stock_{code}.csv"; frame = pd.read_csv(legacy) if legacy.exists() else pd.DataFrame(columns=["date", "close"])
    value = "stock_close" if "stock_close" in frame else "close"
    return _monthly_to_quarter(frame.rename(columns={value: "stock_close"}), "stock_close")


def _sge_gold() -> pd.DataFrame:
    legacy = RAW / "sge_au9999.csv"
    frame = pd.read_csv(legacy) if legacy.exists() else pd.DataFrame(columns=["date", "au_price_rmb_g"])
    return _monthly_to_quarter(frame, "au_price_rmb_g")


def _pmi() -> pd.DataFrame:
    frame = read_parquet_or_empty(RAW / "china_pmi_monthly.parquet")
    result = _monthly_to_quarter(frame, "pmi")
    if result.empty:
        return pd.DataFrame(columns=["quarter", "demand_score"])
    result["demand_score"] = (result["pmi"] - 50).clip(-5, 5) / 5
    return result[["quarter", "demand_score"]]


def _financial(code: str) -> pd.DataFrame:
    frame = read_parquet_or_empty(PROCESSED / "financial_quarterly.parquet")
    selected = frame[frame.get("code", pd.Series(dtype=str)).astype(str) == code].copy() if not frame.empty else frame
    if selected.empty:
        fallback = FALLBACK / ("chalco_quarterly_profit.csv" if code == "601600" else "zijin_quarterly_profit.csv")
        if fallback.exists():
            selected = pd.read_csv(fallback); selected["source"] = "FALLBACK_CSV"; selected["data_quality_flag"] = "financial_fallback"
            if "net_profit_q" not in selected and "net_profit_bn" in selected: selected["net_profit_q"] = selected["net_profit_bn"]
            if "eps_q" not in selected and "eps" in selected: selected["eps_q"] = selected["eps"]
    if selected.empty: return pd.DataFrame(columns=["quarter", "net_profit_bn", "eps", "financial_source", "data_quality_flag"])
    selected["quarter"] = pd.to_datetime(selected["quarter"], errors="coerce")
    selected["net_profit_bn"] = pd.to_numeric(selected.get("net_profit_q"), errors="coerce")
    selected["eps"] = pd.to_numeric(selected.get("eps_q"), errors="coerce")
    selected["financial_source"] = selected.get("source", "NEUTRAL_DEFAULT")
    return selected[["quarter", "net_profit_bn", "eps", "financial_source", "data_quality_flag"]].drop_duplicates("quarter", keep="last")


def _production(code: str) -> pd.DataFrame:
    frame = read_parquet_or_empty(PROCESSED / "production_quarterly.parquet")
    if frame.empty: return pd.DataFrame(columns=["quarter", "cu_ton", "au_kg", "alumina_output_ton", "primary_al_output_ton", "production_source", "parse_confidence", "parse_warning"])
    output = frame[frame["code"].astype(str) == code].copy(); output["quarter"] = pd.to_datetime(output["quarter"], errors="coerce")
    output["production_source"] = output.get("source", "API_CNINFO_PDF")
    return output[[c for c in ["quarter", "cu_ton", "au_kg", "alumina_output_ton", "primary_al_output_ton", "production_source", "parse_confidence", "parse_warning"] if c in output]].drop_duplicates("quarter", keep="last")


def _alumina_price(al_price: pd.DataFrame) -> pd.DataFrame:
    """Use AO only where listed; never infer pre-listing alumina prices."""
    ao = _raw_price("ao", "alumina_price")
    fallback = FALLBACK / "chalco_alumina_spot_monthly.csv"
    fallback_q = pd.DataFrame(columns=["quarter", "fallback_price"])
    if fallback.exists() and fallback.stat().st_size > 40:
        raw = pd.read_csv(fallback)
        date_col = "month" if "month" in raw else "date"
        raw[date_col] = pd.to_datetime(raw[date_col], errors="coerce")
        raw["alumina_price"] = pd.to_numeric(raw["alumina_price"], errors="coerce")
        fallback_q = raw.dropna(subset=[date_col, "alumina_price"]).set_index(date_col)["alumina_price"].resample("QE").last().rename("fallback_price").reset_index().rename(columns={date_col: "quarter"})
    base = al_price[["quarter"]].drop_duplicates().merge(ao[["quarter", "alumina_price"]], on="quarter", how="left").merge(fallback_q, on="quarter", how="left")
    base["alumina_price_source"] = np.where(base["alumina_price"].notna(), "SHFE_AO", np.where(base["fallback_price"].notna(), "FALLBACK_CSV", "MISSING_AO_PRE_2023"))
    base["alumina_price"] = base["alumina_price"].combine_first(base["fallback_price"])
    return base[["quarter", "alumina_price", "alumina_price_source"]]
def build_chalco_quarterly_features() -> pd.DataFrame:
    stock, al, financial = _stock_price("601600"), _raw_price("al", "al_price"), _financial("601600")
    data = financial.merge(stock, on="quarter", how="left").merge(al, on="quarter", how="left").merge(_alumina_price(al), on="quarter", how="left").merge(_pmi(), on="quarter", how="left").merge(_production("601600"), on="quarter", how="left")
    data["al_spread"] = data["al_price"] - 1.925 * data["alumina_price"]
    data["is_q4"] = (pd.to_datetime(data["quarter"]).dt.quarter == 4).astype(int)
    data["demand_score"] = data["demand_score"].fillna(0); data["data_quality_flag"] = data["data_quality_flag"].fillna("")
    return data.sort_values("quarter")


def build_zijin_quarterly_features() -> pd.DataFrame:
    stock, cu, au, financial = _stock_price("601899"), _raw_price("cu", "cu_price"), _sge_gold(), _financial("601899")
    data = financial.merge(stock, on="quarter", how="left").merge(cu, on="quarter", how="left").merge(au, on="quarter", how="left").merge(_pmi(), on="quarter", how="left").merge(_production("601899"), on="quarter", how="left")
    data["cu_ton"] = pd.to_numeric(data.get("cu_ton", pd.Series(0, index=data.index)), errors="coerce").fillna(0)
    data["au_kg"] = pd.to_numeric(data.get("au_kg", pd.Series(0, index=data.index)), errors="coerce").fillna(0)
    data["cu_au_revenue_index"] = data["cu_price"] * data["cu_ton"] + data["au_price_rmb_g"] * data["au_kg"] * 1000
    data["is_q4"] = (pd.to_datetime(data["quarter"]).dt.quarter == 4).astype(int)
    data["demand_score"] = data["demand_score"].fillna(0); data["data_quality_flag"] = data["data_quality_flag"].fillna("")
    return data.sort_values("quarter")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    ensure_layout()
    chalco, zijin = build_chalco_quarterly_features(), build_zijin_quarterly_features()
    save_parquet(chalco, PROCESSED / "chalco_quarterly_features.parquet"); save_parquet(zijin, PROCESSED / "zijin_quarterly_features.parquet")
    write_status("quarterly_features", "API_AND_CACHE", not chalco.empty or not zijin.empty, f"chalco={len(chalco)}, zijin={len(zijin)}")


if __name__ == "__main__":
    main()



