from __future__ import annotations

import joblib
import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge, RidgeCV
from sklearn.metrics import mean_absolute_error, r2_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from .runtime import MODELS, PROCESSED, RAW, REPORTS, ensure_layout, read_parquet_or_empty, save_parquet, safe_json


def _daily_stock(code: str) -> pd.DataFrame:
    frame = read_parquet_or_empty(RAW / "stock_daily_raw" / f"{code}.parquet")
    if frame.empty or "adjust" not in frame or set(frame.adjust.dropna().astype(str)) != {"none"}:
        raise ValueError(f"{code}: verified unadjusted raw stock data is required")
    frame["date"] = pd.to_datetime(frame.date, errors="coerce")
    return frame[["date", "close"]].rename(columns={"close": "stock_close_raw"}).dropna()


def _daily_price(filename: str, value: str) -> pd.DataFrame:
    frame = pd.read_csv(RAW / filename); frame["date"] = pd.to_datetime(frame.date, errors="coerce")
    frame[value] = pd.to_numeric(frame.close if "close" in frame else frame[value], errors="coerce")
    return frame[["date", value]].dropna()


def build_daily_features(company: str) -> pd.DataFrame:
    if company == "chalco":
        data = _daily_stock("601600").merge(_daily_price("shfe_al.csv", "al_price"), on="date").merge(_daily_price("shfe_ao.csv", "alumina_price"), on="date")
        data["al_spread"] = data.al_price - 1.925 * data.alumina_price
        return data
    gold = pd.read_csv(RAW / "sge_au9999.csv"); gold["date"] = pd.to_datetime(gold.date, errors="coerce"); gold["au_price_rmb_g"] = pd.to_numeric(gold.au_price_rmb_g, errors="coerce")
    return _daily_stock("601899").merge(_daily_price("shfe_cu.csv", "cu_price"), on="date").merge(gold[["date", "au_price_rmb_g"]].dropna(), on="date")


def run_daily_model(company: str, min_train_days: int = 252) -> dict:
    features = ["al_price", "alumina_price"] if company == "chalco" else ["cu_price", "au_price_rmb_g"]
    data = build_daily_features(company).dropna().sort_values("date").reset_index(drop=True)
    save_parquet(data, PROCESSED / f"{company}_daily_market_features.parquet")
    if len(data) <= min_train_days + 1:
        summary = {"company": company, "frequency": "daily", "status": "insufficient_data", "rows": len(data)}; safe_json(REPORTS / f"{company}_market_daily_summary.json", summary); return summary
    selector = Pipeline([("scale", StandardScaler()), ("ridge", RidgeCV(alphas=np.logspace(-4, 4, 25), cv=5))])
    selector.fit(data.iloc[:min_train_days][features], data.iloc[:min_train_days].stock_close_raw)
    alpha = float(selector.named_steps["ridge"].alpha_); rows = []
    for index in range(min_train_days, len(data)):
        train, test = data.iloc[:index], data.iloc[[index]]
        model = Pipeline([("scale", StandardScaler()), ("ridge", Ridge(alpha=alpha))]); model.fit(train[features], train.stock_close_raw)
        predicted = float(model.predict(test[features])[0])
        rows.append({"trade_date": test.iloc[0].date, "actual_stock_close_raw": float(test.iloc[0].stock_close_raw), "predicted_stock_close": predicted})
    backtest = pd.DataFrame(rows); backtest["residual"] = backtest.actual_stock_close_raw - backtest.predicted_stock_close
    backtest.to_csv(REPORTS / f"{company}_market_daily_backtest.csv", index=False, encoding="utf-8-sig")
    final = Pipeline([("scale", StandardScaler()), ("ridge", Ridge(alpha=alpha))]); final.fit(data[features], data.stock_close_raw); joblib.dump(final, MODELS / f"{company}_market_daily_model.joblib")
    summary = {"company": company, "frequency": "daily", "rows": len(data), "initial_training_days": min_train_days, "out_of_sample_days": len(backtest), "ridge_alpha": alpha, "r2": r2_score(backtest.actual_stock_close_raw, backtest.predicted_stock_close), "mae": mean_absolute_error(backtest.actual_stock_close_raw, backtest.predicted_stock_close)}
    safe_json(REPORTS / f"{company}_market_daily_summary.json", summary)
    return {**summary, **backtest.iloc[-1].to_dict()}


def main() -> None:
    ensure_layout(); results = []
    for company in ("chalco", "zijin"):
        try: results.append(run_daily_model(company))
        except Exception as exc: results.append({"company": company, "frequency": "daily", "status": "failed", "error": str(exc)})
    pd.DataFrame(results).to_csv(REPORTS / "daily_market_prediction.csv", index=False, encoding="utf-8-sig")


if __name__ == "__main__":
    main()

