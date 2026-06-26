from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression, RidgeCV
from sklearn.metrics import mean_absolute_error, r2_score


@dataclass
class ModelResult:
    backtest: pd.DataFrame
    latest_signal: dict[str, object]


def _make_model(training_rows: int):
    # Leave enough observations for a meaningful cross-validation split.
    if training_rows >= 30:
        return RidgeCV(alphas=np.logspace(-4, 4, 25), cv=5)
    return LinearRegression()


def run_expanding_backtest(
    data: pd.DataFrame, target: str, feature_columns: list[str], model_label: str, min_train: int = 24
) -> ModelResult:
    data = data.dropna(subset=[target, *feature_columns]).sort_values("date").reset_index(drop=True)
    if len(data) <= min_train + 1:
        raise ValueError(f"{model_label}: need at least {min_train + 2} complete monthly observations; got {len(data)}")

    predictions: list[dict[str, object]] = []
    for index in range(min_train, len(data)):
        train = data.iloc[:index]
        test = data.iloc[[index]]
        model = _make_model(len(train))
        model.fit(train[feature_columns], train[target])
        prediction = float(model.predict(test[feature_columns])[0])
        predictions.append(
            {
                "date": test.iloc[0]["date"],
                "actual_value": float(test.iloc[0][target]),
                "predicted_value": prediction,
                "residual": float(test.iloc[0][target]) - prediction,
            }
        )

    backtest = pd.DataFrame(predictions)
    r2 = r2_score(backtest["actual_value"], backtest["predicted_value"])
    mae = mean_absolute_error(backtest["actual_value"], backtest["predicted_value"])
    backtest.insert(0, "model", model_label)
    backtest["r2"] = r2
    backtest["mae"] = mae

    final_model = _make_model(len(data))
    final_model.fit(data[feature_columns], data[target])
    latest = data.iloc[[-1]]
    estimate = float(final_model.predict(latest[feature_columns])[0])
    actual = float(latest.iloc[0][target])
    signal = {
        "model": model_label,
        "as_of_month": pd.Timestamp(latest.iloc[0]["date"]).strftime("%Y-%m-%d"),
        "actual_stock_close": actual,
        "model_estimated_close": estimate,
        "upside_downside_pct": (estimate / actual - 1.0) * 100 if actual else np.nan,
        "backtest_r2": r2,
        "backtest_mae": mae,
        "training_months": len(data),
        "features": ", ".join(feature_columns),
        "estimator": type(final_model).__name__,
    }
    return ModelResult(backtest=backtest, latest_signal=signal)
