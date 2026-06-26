from __future__ import annotations

import json

import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, r2_score
from sklearn.linear_model import Ridge
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from .fit_profit_models import SPECS
from .runtime import PROCESSED, REPORTS, ensure_layout, read_parquet_or_empty, safe_json


def walkforward(company: str) -> tuple[pd.DataFrame, dict]:
    features = SPECS[company]; data = read_parquet_or_empty(PROCESSED / f"{company}_quarterly_features.parquet")
    data = data.dropna(subset=["net_profit_bn", *features]).sort_values("quarter").reset_index(drop=True) if not data.empty else data
    if len(data) < 10:
        return pd.DataFrame(), {"company": company, "status": "insufficient_data", "training_rows": len(data)}
    records = []
    for index in range(8, len(data)):
        train, test = data.iloc[:index], data.iloc[[index]]
        model = Pipeline([("scale", StandardScaler()), ("ridge", Ridge(alpha=1.0))]); model.fit(train[features], train["net_profit_bn"])
        predicted = float(model.predict(test[features])[0]); actual = float(test.iloc[0]["net_profit_bn"])
        records.append({"quarter": test.iloc[0]["quarter"], "actual_net_profit_bn": actual, "predicted_net_profit_bn": predicted, "residual": actual - predicted})
    results = pd.DataFrame(records); summary = {"company": company, "status": "ok", "observations": len(results), "r2": r2_score(results.actual_net_profit_bn, results.predicted_net_profit_bn), "mae_bn": mean_absolute_error(results.actual_net_profit_bn, results.predicted_net_profit_bn)}
    return results, summary


def main() -> None:
    ensure_layout()
    for company in SPECS:
        result, summary = walkforward(company)
        result.to_csv(REPORTS / f"{company}_profit_walkforward.csv", index=False, encoding="utf-8-sig")
        safe_json(REPORTS / f"{company}_profit_walkforward_summary.json", summary)


if __name__ == "__main__":
    main()
