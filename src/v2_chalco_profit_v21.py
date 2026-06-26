"""V2.1 Chalco profit-model comparison with announcement-safe walk-forward tests."""
from __future__ import annotations

import json
from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.linear_model import RidgeCV
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from .runtime import PROCESSED, REPORTS, read_parquet_or_empty, save_parquet
from .v2_walk_forward import ALPHAS, MIN_TRAIN_QUARTERS, _financial

SHARES_BN = 171.55
MODELS = ("A_original_v2", "B_price_expanded_ridge", "C_profit_anchor_ridge", "D_commodity_anchor_blend")
A_FEATURES = ["al_spread_q_last_k", "alumina_price_q_last_k", "demand_score_q_mean", "is_q4"]
B_FEATURES = ["al_price_q_mean", "alumina_price_q_mean", "al_spread_q_mean", "al_spread_q_mean_lag1", "alumina_price_q_mean_lag1", "demand_score_q_mean", "is_q1", "is_q2", "is_q3", "is_q4"]
C_FEATURES = ["al_spread_q_mean", "alumina_price_q_mean", "demand_score_q_mean", "last_announced_q_profit_bn", "ttm_announced_profit_bn", "last_2q_avg_profit_bn", "is_q1", "is_q2", "is_q3", "is_q4"]


@dataclass
class FitResult:
    prediction: float
    alpha: float
    intercept: float
    coefficients: dict[str, float]


def _quarter_end_features() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    market = read_parquet_or_empty(PROCESSED / "v2_chalco_monthly_market.parquet").copy()
    market["date"] = pd.to_datetime(market["date"])
    market["quarter"] = market["date"].dt.to_period("Q").dt.end_time.dt.normalize()
    aggregated = market.groupby("quarter", as_index=False).agg(
        al_price_q_mean=("al_price", "mean"), alumina_price_q_mean=("alumina_price", "mean"),
        al_spread_q_mean=("al_spread", "mean"), al_price_q_last=("al_price", "last"),
        alumina_price_q_last=("alumina_price", "last"), al_spread_q_last=("al_spread", "last"),
        demand_score_q_mean=("demand_score", "mean"), actual_stock_close_raw=("actual_stock_close_raw", "last"),
        data_quality_flag=("data_quality_flag", "last"),
    ).sort_values("quarter").reset_index(drop=True)
    for col in ("al_price_q_mean", "alumina_price_q_mean", "al_spread_q_mean", "al_price_q_last", "alumina_price_q_last", "al_spread_q_last"):
        aggregated[f"{col}_k"] = aggregated[col] / 1000.0
    for col in ("al_spread_q_mean_k", "alumina_price_q_mean_k", "al_price_q_mean_k"):
        base = col.removesuffix("_k")
        aggregated[f"{base}_lag1"] = aggregated[base].shift(1)
        aggregated[f"{base}_lag2"] = aggregated[base].shift(2)
        aggregated[f"{base}_yoy"] = aggregated[base] / aggregated[base].shift(4) - 1
        aggregated[f"{base}_lag1_k"] = aggregated[col].shift(1)
        aggregated[f"{base}_lag2_k"] = aggregated[col].shift(2)
        aggregated[f"{base}_yoy"] = aggregated[col] / aggregated[col].shift(4) - 1
    aggregated["demand_score_q_change"] = aggregated["demand_score_q_mean"].diff()
    quarter_number = aggregated["quarter"].dt.quarter
    for q in (1, 2, 3, 4):
        aggregated[f"is_q{q}"] = quarter_number.eq(q).astype(int)

    financial = _financial("601600")[["quarter", "net_profit_q", "financial_available_date"]].copy().sort_values("financial_available_date")
    rows = []
    for _, row in aggregated.iterrows():
        visible = financial[financial["financial_available_date"] <= row["quarter"]].sort_values("financial_available_date")
        profits = visible["net_profit_q"].astype(float).tail(4)
        anchor = {
            "last_announced_q_profit_bn": profits.iloc[-1] if len(profits) else np.nan,
            "ttm_announced_profit_bn": profits.sum() if len(profits) == 4 else np.nan,
            "last_2q_avg_profit_bn": profits.tail(2).mean() if len(profits) >= 2 else np.nan,
            "last_4q_avg_profit_bn": profits.mean() if len(profits) == 4 else np.nan,
        }
        rows.append(anchor)
    aggregated = pd.concat([aggregated, pd.DataFrame(rows)], axis=1)
    dataset = aggregated.merge(financial, on="quarter", how="inner")
    return aggregated, financial, dataset


def _fit(train: pd.DataFrame, features: list[str], row: pd.Series, scaled: bool) -> FitResult:
    if scaled:
        estimator = Pipeline([( "scale", StandardScaler()), ("ridge", RidgeCV(alphas=ALPHAS))])
        estimator.fit(train[features], train["net_profit_q"])
        ridge = estimator.named_steps["ridge"]
        prediction = float(estimator.predict(pd.DataFrame([row[features]], columns=features))[0])
    else:
        estimator = RidgeCV(alphas=ALPHAS); estimator.fit(train[features], train["net_profit_q"])
        ridge = estimator; prediction = float(estimator.predict(pd.DataFrame([row[features]], columns=features))[0])
    return FitResult(prediction, float(ridge.alpha_), float(ridge.intercept_), {name: float(value) for name, value in zip(features, ridge.coef_)})


def _blend_weight(train: pd.DataFrame, commodity_fit: FitResult) -> float:
    # Weight search is confined to the historical training window.  It never sees
    # the current target quarter.
    model = Pipeline([( "scale", StandardScaler()), ("ridge", RidgeCV(alphas=ALPHAS))])
    model.fit(train[B_FEATURES], train["net_profit_q"])
    commodity_history = model.predict(train[B_FEATURES])
    anchor = train["last_2q_avg_profit_bn"].fillna(train["last_announced_q_profit_bn"])
    scores = {w: np.mean(np.abs(w * commodity_history + (1 - w) * anchor - train["net_profit_q"])) for w in (.25, .5, .75)}
    return min(scores, key=scores.get)


def walk_forward(dataset: pd.DataFrame) -> pd.DataFrame:
    records: list[dict] = []
    for _, target in dataset.sort_values("quarter").iterrows():
        historical = dataset[dataset["financial_available_date"] <= target["quarter"]].copy()
        for model_name, features, scaled in (("A_original_v2", A_FEATURES, False), ("B_price_expanded_ridge", B_FEATURES, True), ("C_profit_anchor_ridge", C_FEATURES, True)):
            train = historical.dropna(subset=features + ["net_profit_q"])
            if len(train) < MIN_TRAIN_QUARTERS or target[features].isna().any():
                continue
            fit = _fit(train, features, target, scaled)
            records.append({"quarter": target["quarter"], "model": model_name, "q_profit_pred_bn": fit.prediction, "actual_q_profit_bn": target["net_profit_q"], "last_announced_q_profit_bn": target["last_announced_q_profit_bn"], "train_quarters_count": len(train), "ridge_alpha": fit.alpha, "ridge_intercept": fit.intercept, "ridge_coef_json": json.dumps(fit.coefficients, ensure_ascii=False), "selected_w": np.nan})
        train = historical.dropna(subset=B_FEATURES + ["net_profit_q", "last_announced_q_profit_bn"])
        if len(train) >= MIN_TRAIN_QUARTERS and not target[B_FEATURES].isna().any() and pd.notna(target["last_announced_q_profit_bn"]):
            commodity = _fit(train, B_FEATURES, target, True)
            anchor = target["last_2q_avg_profit_bn"] if pd.notna(target["last_2q_avg_profit_bn"]) else target["last_announced_q_profit_bn"]
            w = _blend_weight(train, commodity)
            records.append({"quarter": target["quarter"], "model": "D_commodity_anchor_blend", "q_profit_pred_bn": w * commodity.prediction + (1 - w) * anchor, "actual_q_profit_bn": target["net_profit_q"], "last_announced_q_profit_bn": target["last_announced_q_profit_bn"], "train_quarters_count": len(train), "ridge_alpha": commodity.alpha, "ridge_intercept": commodity.intercept, "ridge_coef_json": json.dumps(commodity.coefficients, ensure_ascii=False), "selected_w": w})
    return pd.DataFrame(records)


def _metrics(walk: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for model, part in walk.groupby("model"):
        error = part["q_profit_pred_bn"] - part["actual_q_profit_bn"]
        direction = np.sign(part["q_profit_pred_bn"] - part["last_announced_q_profit_bn"]) == np.sign(part["actual_q_profit_bn"] - part["last_announced_q_profit_bn"])
        rows.append({"model": model, "n": len(part), "mae": np.abs(error).mean(), "rmse": np.sqrt(np.mean(error ** 2)), "mape": (np.abs(error) / part["actual_q_profit_bn"].replace(0, np.nan)).mean(), "bias": error.mean(), "r2": 1 - np.sum(error ** 2) / np.sum((part["actual_q_profit_bn"] - part["actual_q_profit_bn"].mean()) ** 2) if len(part) > 1 else np.nan, "directional_accuracy": direction.mean(), "latest_predicted_q_profit": part.iloc[-1]["q_profit_pred_bn"], "latest_actual_q_profit_anchor": part.iloc[-1]["last_announced_q_profit_bn"]})
    return pd.DataFrame(rows)


def _select(metrics: pd.DataFrame) -> str:
    ranked = metrics.assign(abs_bias=metrics["bias"].abs()).sort_values(["mape", "abs_bias", "mae"], na_position="last")
    return str(ranked.iloc[0]["model"])


def _latest_prediction(aggregated: pd.DataFrame, financial: pd.DataFrame, selected_model: str) -> pd.DataFrame:
    market = read_parquet_or_empty(PROCESSED / "v2_chalco_monthly_market.parquet").copy(); market["date"] = pd.to_datetime(market["date"])
    latest_date = market["date"].max(); current_q = latest_date.to_period("Q").end_time.normalize()
    current = market[market["date"].dt.to_period("Q").dt.end_time.dt.normalize().eq(current_q)].copy()
    row = {"date": latest_date, "quarter": current_q, "al_price_q_mean": current["al_price"].mean(), "alumina_price_q_mean": current["alumina_price"].mean(), "al_spread_q_mean": current["al_spread"].mean(), "al_price_q_last": current["al_price"].iloc[-1], "alumina_price_q_last": current["alumina_price"].iloc[-1], "al_spread_q_last": current["al_spread"].iloc[-1], "demand_score_q_mean": current["demand_score"].mean(), "actual_stock_close_raw": current["actual_stock_close_raw"].iloc[-1], "data_quality_flag": current["data_quality_flag"].iloc[-1]}
    for key in list(row):
        if key.startswith(("al_price", "alumina_price", "al_spread")) and key.endswith(("mean", "last")):
            row[key + "_k"] = row[key] / 1000
    prior = aggregated[aggregated["quarter"] < current_q].sort_values("quarter")
    for col in ("al_spread_q_mean_k", "alumina_price_q_mean_k", "al_price_q_mean_k"):
        base = col.removesuffix("_k")
        row[f"{base}_lag1"] = prior[base].iloc[-1] if len(prior) else np.nan
        row[f"{base}_lag2"] = prior[base].iloc[-2] if len(prior) > 1 else np.nan
        row[f"{base}_yoy"] = row[base] / prior[base].iloc[-4] - 1 if len(prior) >= 4 else np.nan
        row[f"{base}_lag1_k"] = prior[col].iloc[-1] if len(prior) else np.nan
        row[f"{base}_lag2_k"] = prior[col].iloc[-2] if len(prior) > 1 else np.nan
        row[f"{base}_yoy"] = row[col] / prior[col].iloc[-4] - 1 if len(prior) >= 4 else np.nan
    row["demand_score_q_change"] = row["demand_score_q_mean"] - prior["demand_score_q_mean"].iloc[-1] if len(prior) else np.nan
    for q in (1, 2, 3, 4): row[f"is_q{q}"] = int(current_q.quarter == q)
    visible = financial[financial["financial_available_date"] <= latest_date].sort_values("financial_available_date")["net_profit_q"].tail(4)
    row["last_announced_q_profit_bn"] = visible.iloc[-1] if len(visible) else np.nan; row["ttm_announced_profit_bn"] = visible.sum() if len(visible) == 4 else np.nan; row["last_2q_avg_profit_bn"] = visible.tail(2).mean() if len(visible) >= 2 else np.nan; row["last_4q_avg_profit_bn"] = visible.mean() if len(visible) == 4 else np.nan
    row = pd.Series(row)
    historical = aggregated.merge(financial, on="quarter", how="inner"); historical = historical[historical["financial_available_date"] <= latest_date]
    if selected_model == "A_original_v2": features, scaled = A_FEATURES, False
    elif selected_model == "B_price_expanded_ridge": features, scaled = B_FEATURES, True
    else: features, scaled = C_FEATURES if selected_model == "C_profit_anchor_ridge" else B_FEATURES, True
    train = historical.dropna(subset=features + ["net_profit_q"])
    fit = _fit(train, features, row, scaled)
    pred, selected_w = fit.prediction, np.nan
    if selected_model == "D_commodity_anchor_blend":
        anchor = row["last_2q_avg_profit_bn"] if pd.notna(row["last_2q_avg_profit_bn"]) else row["last_announced_q_profit_bn"]
        selected_w = _blend_weight(train.dropna(subset=["last_announced_q_profit_bn"]), fit); pred = selected_w * fit.prediction + (1 - selected_w) * anchor
    target_pe = float(np.clip(8.5 + 3 * (row["demand_score_q_mean"] - .5) - .5 * row["is_q4"], 6.5, 11.5))
    model_price = pred * 4 / SHARES_BN * target_pe
    worsening = row["al_spread_q_mean_k"] < row["al_spread_q_mean_lag1_k"] * .95
    warning = "UNDER_PREDICTION_WARNING" if pred < row["last_announced_q_profit_bn"] and not worsening else ""
    return pd.DataFrame([{"date": latest_date, "selected_model": selected_model, "q_profit_pred_bn": pred, "annual_profit_pred_bn": pred * 4, "eps_pred": pred * 4 / SHARES_BN, "target_pe": target_pe, "model_price": model_price, "gap": row["actual_stock_close_raw"] / model_price - 1, "signal_status": "suspended_due_to_profit_underprediction", "profit_model_warning": warning, "selected_w": selected_w, "train_quarters_count": len(train), "data_quality_flag": row["data_quality_flag"]}])


def run() -> dict[str, object]:
    aggregated, financial, dataset = _quarter_end_features(); walk = walk_forward(dataset); metrics = _metrics(walk)
    if walk.empty: raise RuntimeError("insufficient_training_data")
    selected = _select(metrics); prediction = _latest_prediction(aggregated, financial, selected)
    comparison_path = REPORTS / "v2_chalco_profit_v21_model_comparison.csv"; walk_path = REPORTS / "v2_chalco_profit_v21_walkforward.csv"; summary_path = REPORTS / "v2_chalco_profit_v21_summary.md"
    metrics.to_csv(comparison_path, index=False, encoding="utf-8-sig"); walk.to_csv(walk_path, index=False, encoding="utf-8-sig"); save_parquet(prediction, PROCESSED / "v2_chalco_profit_v21_predictions.parquet")
    original = metrics[metrics["model"] == "A_original_v2"].iloc[0]; best = metrics[metrics["model"] == selected].iloc[0]; latest = prediction.iloc[0]
    improved = bool(best["mape"] < original["mape"] and abs(best["bias"]) < abs(original["bias"]))
    text = "# China Aluminum V2.1 profit-model summary\n\n"
    text += "- Original V2 systematically underestimates profit: True (see diagnostics).\n"
    text += "- Original `overvalued` signal tradable: No; suspended due to profit underprediction.\n"
    text += f"- Selected V2.1 candidate by walk-forward MAPE then absolute bias: `{selected}`.\n"
    text += f"- Selection improvement versus Model A on both MAPE and absolute bias: {improved}.\n"
    text += f"- Latest V2.1 quarterly-profit prediction: {latest['q_profit_pred_bn']:.2f} bn RMB.\n- Latest V2.1 model price at unchanged PE logic: {latest['model_price']:.2f}.\n"
    text += "- Official Chalco gap signal restored: No. The out-of-sample quarterly evaluation remains small, and demand inputs retain DEFAULT_PROXY fields. V2.1 remains a profit-layer validation result, not an investable signal.\n"
    text += "- No PE uplift was used. All anchors are filtered through financial announcement dates; Model D weight search is confined to each historical training window.\n"
    summary_path.write_text(text, encoding="utf-8")
    return {"selected_model": selected, "walkforward_rows": len(walk), "latest_q_profit_pred_bn": round(float(latest["q_profit_pred_bn"]), 4), "latest_model_price": round(float(latest["model_price"]), 4)}


def main() -> None:
    print(run())


if __name__ == "__main__":
    main()


