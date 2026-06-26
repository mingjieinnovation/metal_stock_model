from __future__ import annotations

import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.linear_model import RidgeCV
from sklearn.metrics import mean_absolute_error, r2_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from .runtime import MODELS, PROCESSED, RAW, REPORTS, ensure_layout, read_parquet_or_empty, save_parquet, safe_json


def _monthly_stock(code: str) -> pd.DataFrame:
    data = read_parquet_or_empty(RAW / "stock_daily_raw" / f"{code}.parquet")
    if data.empty: raise ValueError(f"Missing unadjusted stock cache for {code}; run src.fetch_stock")
    if "adjust" not in data or set(data["adjust"].dropna().astype(str)) != {"none"}:
        raise ValueError("Stock price data must be raw/unadjusted. Adjusted cache is not allowed.")
    if data["provider"].isna().any(): raise ValueError("stock provider missing")
    data["date"] = pd.to_datetime(data["date"], errors="coerce")
    indexed = data.dropna(subset=["date", "close"]).set_index("date").sort_index()
    close = indexed["close"].resample("ME").last().rename("stock_close_raw")
    trade_date = indexed["close"].resample("ME").apply(lambda values: values.index[-1] if len(values) else pd.NaT).rename("stock_trade_date")
    return pd.concat([close, trade_date], axis=1).reset_index()


def _monthly_csv(filename: str, value: str) -> pd.DataFrame:
    data = pd.read_csv(RAW / filename); data["date"] = pd.to_datetime(data["date"], errors="coerce")
    data[value] = pd.to_numeric(data["close"] if "close" in data else data[value], errors="coerce")
    return data.dropna(subset=["date", value]).set_index("date")[value].resample("ME").last().reset_index()
def build_market_features(company: str) -> pd.DataFrame:
    if company == "chalco":
        stock = _monthly_stock("601600")
        al = _monthly_csv("shfe_al.csv", "al_price")
        ao = _monthly_csv("shfe_ao.csv", "alumina_price")
        data = stock.merge(al, on="date").merge(ao, on="date")
        data["al_spread"] = data.al_price - 1.925 * data.alumina_price
        return data
    stock = _monthly_stock("601899")
    cu = _monthly_csv("shfe_cu.csv", "cu_price")
    gold = pd.read_csv(RAW / "sge_au9999.csv"); gold["date"] = pd.to_datetime(gold.date, errors="coerce"); gold["au_price_rmb_g"] = pd.to_numeric(gold.au_price_rmb_g, errors="coerce")
    gold = gold.dropna().set_index("date")["au_price_rmb_g"].resample("ME").last().reset_index()
    return stock.merge(cu, on="date").merge(gold, on="date")


def train_and_backtest(company: str) -> dict:
    features = ["al_price", "alumina_price"] if company == "chalco" else ["cu_price", "au_price_rmb_g"]
    data = build_market_features(company).dropna().sort_values("date").reset_index(drop=True)
    save_parquet(data, PROCESSED / f"{company}_monthly_market_features.parquet")
    if len(data) < 26:
        summary = {"company": company, "frequency": "monthly", "status": "insufficient_data", "rows": len(data)}; safe_json(REPORTS / f"{company}_market_monthly_summary.json", summary); return summary
    rows = []
    for index in range(24, len(data)):
        train, test = data.iloc[:index], data.iloc[[index]]
        model = Pipeline([("scale", StandardScaler()), ("ridge", RidgeCV(alphas=np.logspace(-4, 4, 25), cv=min(5, len(train))))])
        model.fit(train[features], train.stock_close_raw); predicted = float(model.predict(test[features])[0])
        rows.append({"month": test.iloc[0].date, "stock_trade_date": test.iloc[0].stock_trade_date, "actual_stock_close_raw": float(test.iloc[0].stock_close_raw), "predicted_stock_close": predicted})
    result = pd.DataFrame(rows); result["residual"] = result.actual_stock_close_raw - result.predicted_stock_close
    result.to_csv(REPORTS / f"{company}_market_monthly_backtest.csv", index=False, encoding="utf-8-sig")
    final = Pipeline([("scale", StandardScaler()), ("ridge", RidgeCV(alphas=np.logspace(-4, 4, 25), cv=min(5, len(data))))]); final.fit(data[features], data.stock_close_raw); joblib.dump(final, MODELS / f"{company}_market_monthly_model.joblib")
    summary = {"company": company, "frequency": "monthly", "rows": len(data), "out_of_sample_months": len(result), "r2": r2_score(result.actual_stock_close_raw, result.predicted_stock_close), "mae": mean_absolute_error(result.actual_stock_close_raw, result.predicted_stock_close), "price_adjustment_required": "none"}
    safe_json(REPORTS / f"{company}_market_monthly_summary.json", summary); return summary


def main() -> None:
    ensure_layout()
    for company in ("chalco", "zijin"):
        try: train_and_backtest(company)
        except Exception as exc: safe_json(REPORTS / f"{company}_market_monthly_summary.json", {"company": company, "status": "failed", "error": str(exc)})


if __name__ == "__main__":
    main()




