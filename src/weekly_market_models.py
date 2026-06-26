from __future__ import annotations

import joblib
import numpy as np
import pandas as pd
from sklearn.linear_model import RidgeCV
from sklearn.metrics import mean_absolute_error, r2_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from .runtime import MODELS, PROCESSED, RAW, REPORTS, ensure_layout, read_parquet_or_empty, save_parquet, safe_json


def _weekly_stock(code: str) -> pd.DataFrame:
    frame = read_parquet_or_empty(RAW / "stock_daily_raw" / f"{code}.parquet")
    if frame.empty or "adjust" not in frame or set(frame["adjust"].dropna().astype(str)) != {"none"}:
        raise ValueError(f"{code}: verified unadjusted raw stock data is required")
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
    indexed = frame.dropna(subset=["date", "close"]).set_index("date").sort_index()
    close = indexed["close"].resample("W-FRI").last().rename("stock_close_raw")
    trade_date = indexed["close"].resample("W-FRI").apply(lambda values: values.index[-1] if len(values) else pd.NaT).rename("stock_trade_date")
    return pd.concat([close, trade_date], axis=1).reset_index().rename(columns={"date": "week"})


def _weekly_commodity(filename: str, value: str) -> pd.DataFrame:
    frame = pd.read_csv(RAW / filename); frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
    frame[value] = pd.to_numeric(frame["close"] if "close" in frame else frame[value], errors="coerce")
    return frame.dropna(subset=["date", value]).set_index("date")[value].resample("W-FRI").last().reset_index().rename(columns={"date": "week"})


def build_weekly_features(company: str) -> pd.DataFrame:
    if company == "chalco":
        stock = _weekly_stock("601600"); al = _weekly_commodity("shfe_al.csv", "al_price"); ao = _weekly_commodity("shfe_ao.csv", "alumina_price")
        data = stock.merge(al, on="week").merge(ao, on="week")
        data["al_spread"] = data.al_price - 1.925 * data.alumina_price
        return data
    stock = _weekly_stock("601899"); cu = _weekly_commodity("shfe_cu.csv", "cu_price")
    gold = pd.read_csv(RAW / "sge_au9999.csv"); gold["date"] = pd.to_datetime(gold.date, errors="coerce"); gold["au_price_rmb_g"] = pd.to_numeric(gold.au_price_rmb_g, errors="coerce")
    gold = gold.dropna().set_index("date")["au_price_rmb_g"].resample("W-FRI").last().reset_index().rename(columns={"date": "week"})
    return stock.merge(cu, on="week").merge(gold, on="week")


def run_weekly_model(company: str, min_train_weeks: int = 52) -> dict:
    features = ["al_price", "alumina_price"] if company == "chalco" else ["cu_price", "au_price_rmb_g"]
    data = build_weekly_features(company).dropna().sort_values("week").reset_index(drop=True)
    save_parquet(data, PROCESSED / f"{company}_weekly_market_features.parquet")
    if len(data) <= min_train_weeks + 1:
        summary = {"company": company, "frequency": "weekly", "status": "insufficient_data", "rows": len(data)}
        safe_json(REPORTS / f"{company}_market_weekly_summary.json", summary); return summary
    rows = []
    for index in range(min_train_weeks, len(data)):
        train, test = data.iloc[:index], data.iloc[[index]]
        model = Pipeline([("scale", StandardScaler()), ("ridge", RidgeCV(alphas=np.logspace(-4, 4, 25), cv=min(5, len(train))))])
        model.fit(train[features], train.stock_close_raw); prediction = float(model.predict(test[features])[0])
        rows.append({"week": test.iloc[0].week, "stock_trade_date": test.iloc[0].stock_trade_date, "actual_stock_close_raw": float(test.iloc[0].stock_close_raw), "predicted_stock_close": prediction})
    backtest = pd.DataFrame(rows); backtest["residual"] = backtest.actual_stock_close_raw - backtest.predicted_stock_close
    backtest.to_csv(REPORTS / f"{company}_market_weekly_backtest.csv", index=False, encoding="utf-8-sig")
    final = Pipeline([("scale", StandardScaler()), ("ridge", RidgeCV(alphas=np.logspace(-4, 4, 25), cv=min(5, len(data))))]); final.fit(data[features], data.stock_close_raw); joblib.dump(final, MODELS / f"{company}_market_weekly_model.joblib")
    summary = {"company": company, "frequency": "weekly", "rows": len(data), "initial_training_weeks": min_train_weeks, "out_of_sample_weeks": len(backtest), "r2": r2_score(backtest.actual_stock_close_raw, backtest.predicted_stock_close), "mae": mean_absolute_error(backtest.actual_stock_close_raw, backtest.predicted_stock_close)}
    safe_json(REPORTS / f"{company}_market_weekly_summary.json", summary)
    return {**summary, **backtest.iloc[-1].to_dict()}


def main() -> None:
    ensure_layout(); results = []
    for company in ("chalco", "zijin"):
        try: results.append(run_weekly_model(company))
        except Exception as exc: results.append({"company": company, "frequency": "weekly", "status": "failed", "error": str(exc)})
    pd.DataFrame(results).to_csv(REPORTS / "weekly_market_prediction.csv", index=False, encoding="utf-8-sig")


if __name__ == "__main__":
    main()

