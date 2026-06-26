from __future__ import annotations

import logging

import joblib
import numpy as np
import pandas as pd
from sklearn.linear_model import RidgeCV
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from .runtime import MODELS, PROCESSED, ensure_layout, read_parquet_or_empty, safe_json, write_status

SPECS = {
    "chalco": ["al_spread", "alumina_price", "demand_score", "is_q4"],
    "zijin": ["cu_price", "au_price_rmb_g", "cu_au_revenue_index", "demand_score", "is_q4"],
}


def fit_company_model(company: str) -> dict:
    features = SPECS[company]; data = read_parquet_or_empty(PROCESSED / f"{company}_quarterly_features.parquet")
    train = data.dropna(subset=["net_profit_bn", *features]).copy() if not data.empty else pd.DataFrame()
    payload = {"company": company, "features": features, "training_rows": len(train), "status": "insufficient_data"}
    if len(train) < 8:
        safe_json(MODELS / f"{company}_profit_model_meta.json", payload); return payload
    model = Pipeline([("scale", StandardScaler()), ("ridge", RidgeCV(alphas=np.logspace(-4, 4, 25), cv=min(5, len(train))) )])
    model.fit(train[features], train["net_profit_bn"])
    joblib.dump(model, MODELS / f"{company}_profit_model.joblib")
    payload.update({"status": "fitted", "estimator": "StandardScaler+RidgeCV", "alpha": float(model.named_steps["ridge"].alpha_)})
    safe_json(MODELS / f"{company}_profit_model_meta.json", payload); return payload


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s"); ensure_layout()
    results = [fit_company_model(company) for company in SPECS]
    write_status("profit_models", "LOCAL_MODEL", any(x["status"] == "fitted" for x in results), str(results))


if __name__ == "__main__":
    main()
