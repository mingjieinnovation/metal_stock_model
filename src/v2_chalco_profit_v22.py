"""V2.2 Chalco: announcement-safe TTM profit diagnostics and walk-forward models."""
from __future__ import annotations

import json
import numpy as np
import pandas as pd
from sklearn.linear_model import RidgeCV
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from .runtime import PROCESSED, REPORTS, read_parquet_or_empty, save_parquet
from .v2_chalco_profit_v21 import C_FEATURES, _quarter_end_features
from .v2_walk_forward import ALPHAS, MIN_TRAIN_QUARTERS

SHARES_BN = 171.55
E_FEATURES = ["al_spread_q_mean", "al_spread_q_mean_lag1", "al_spread_q_mean_lag2", "alumina_price_q_mean", "al_price_q_mean", "demand_score_q_mean", "ttm_announced_profit_bn", "last_4q_avg_profit_bn", "is_q1", "is_q2", "is_q3", "is_q4"]
WEIGHTS = [(0.2, 0.3, 0.5), (0.3, 0.3, 0.4), (0.4, 0.3, 0.3), (0.5, 0.25, 0.25)]
OPTIONAL_STATUS = "coal_price_q_mean=MISSING;power_cost_proxy=MISSING;primary_al_output_ton=MISSING;alumina_output_ton=MISSING;MODEL_F=BLOCKED_MISSING_AUDITABLE_VOLUME"


def _prepare() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    aggregated, financial, _ = _quarter_end_features()
    financial = financial.sort_values("quarter").copy()
    financial["ttm_net_profit_bn"] = financial["net_profit_q"].rolling(4, min_periods=4).sum()
    data = aggregated.merge(financial[["quarter", "net_profit_q", "ttm_net_profit_bn", "financial_available_date"]], on="quarter", how="inner")
    # Raw lag columns are defined explicitly here to retain the feature names in
    # the V2.2 specification; no proxy values are introduced.
    for base in ("al_spread_q_mean", "alumina_price_q_mean", "al_price_q_mean"):
        data[f"{base}_lag1"] = data[base].shift(1)
        data[f"{base}_lag2"] = data[base].shift(2)
    return aggregated, financial, data


def _fit(train: pd.DataFrame, features: list[str], target: str, row: pd.Series) -> tuple[float, Pipeline]:
    model = Pipeline([("scale", StandardScaler()), ("ridge", RidgeCV(alphas=ALPHAS))])
    model.fit(train[features], train[target])
    return float(model.predict(pd.DataFrame([row[features]], columns=features))[0]), model


def _r2(actual: pd.Series, predicted: pd.Series) -> float:
    if len(actual) < 2 or np.isclose(np.sum((actual - actual.mean()) ** 2), 0): return np.nan
    return float(1 - np.sum((actual - predicted) ** 2) / np.sum((actual - actual.mean()) ** 2))


def _metric(part: pd.DataFrame, model: str, full_r2: float, adjusted_r2: float, status: str = "ok") -> dict:
    error = part["ttm_profit_pred_bn"] - part["actual_ttm_profit_bn"]
    qerror = part["q_profit_pred_bn"] - part["actual_q_profit_bn"]
    direction = np.sign(part["q_profit_pred_bn"] - part["last_announced_q_profit_bn"]) == np.sign(part["actual_q_profit_bn"] - part["last_announced_q_profit_bn"])
    return {"model": model, "status": status, "n": len(part), "mae": np.abs(error).mean(), "rmse": np.sqrt(np.mean(error ** 2)), "mape": (np.abs(error) / part["actual_ttm_profit_bn"].replace(0, np.nan)).mean(), "bias": error.mean(), "r2": _r2(part["actual_ttm_profit_bn"], part["ttm_profit_pred_bn"]), "adjusted_r2": adjusted_r2, "full_sample_r2": full_r2, "walk_forward_oos_r2": _r2(part["actual_ttm_profit_bn"], part["ttm_profit_pred_bn"]), "ttm_target_r2": _r2(part["actual_ttm_profit_bn"], part["ttm_profit_pred_bn"]), "single_quarter_target_r2": _r2(part["actual_q_profit_bn"], part["q_profit_pred_bn"]), "directional_accuracy": direction.mean(), "latest_q_profit_pred": part.iloc[-1]["q_profit_pred_bn"], "latest_ttm_profit_pred": part.iloc[-1]["ttm_profit_pred_bn"], "optional_feature_status": OPTIONAL_STATUS}


def _full_diagnostic(data: pd.DataFrame) -> tuple[float, float]:
    sample = data.dropna(subset=E_FEATURES + ["ttm_net_profit_bn"])
    if len(sample) <= MIN_TRAIN_QUARTERS: return np.nan, np.nan
    pred, model = _fit(sample, E_FEATURES, "ttm_net_profit_bn", sample.iloc[-1])
    fitted = model.predict(sample[E_FEATURES]); r2 = _r2(sample["ttm_net_profit_bn"], pd.Series(fitted, index=sample.index)); n, p = len(sample), len(E_FEATURES)
    adjusted = np.nan if n <= p + 1 else 1 - (1 - r2) * (n - 1) / (n - p - 1)
    return r2, adjusted


def _choose_weights(train: pd.DataFrame, commodity: Pipeline) -> tuple[float, float, float]:
    cp = commodity.predict(train[C_FEATURES]); last = train["last_announced_q_profit_bn"].to_numpy(); ttm4 = (train["ttm_announced_profit_bn"] / 4).to_numpy(); actual = train["net_profit_q"].to_numpy()
    scores = {w: np.mean(np.abs(w[0]*cp + w[1]*last + w[2]*ttm4 - actual)) for w in WEIGHTS}
    return min(scores, key=scores.get)


def walk_forward(data: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict] = []
    for _, target in data.sort_values("quarter").iterrows():
        historical = data[data["financial_available_date"] <= target["quarter"]].copy()
        # Model E: direct TTM target.
        train_e = historical.dropna(subset=E_FEATURES + ["ttm_net_profit_bn"])
        if len(train_e) >= MIN_TRAIN_QUARTERS and not target[E_FEATURES].isna().any():
            ttm_pred, model = _fit(train_e, E_FEATURES, "ttm_net_profit_bn", target)
            prior_ttm = target["ttm_announced_profit_bn"]
            q_pred = ttm_pred - prior_ttm + target["last_announced_q_profit_bn"] if pd.notna(prior_ttm) else np.nan
            ridge = model.named_steps["ridge"]
            rows.append({"quarter": target["quarter"], "model": "E_ttm_profit_ridge", "q_profit_pred_bn": q_pred, "ttm_profit_pred_bn": ttm_pred, "actual_q_profit_bn": target["net_profit_q"], "actual_ttm_profit_bn": target["ttm_net_profit_bn"], "last_announced_q_profit_bn": target["last_announced_q_profit_bn"], "train_quarters_count": len(train_e), "ridge_alpha": ridge.alpha_, "ridge_coef_json": json.dumps(dict(zip(E_FEATURES, ridge.coef_)), ensure_ascii=False), "selected_weights": pd.NA, "data_quality_flag": OPTIONAL_STATUS})
        # Model G: commodity-quarter model blended with only historical announced anchors.
        train_g = historical.dropna(subset=C_FEATURES + ["net_profit_q", "last_announced_q_profit_bn", "ttm_announced_profit_bn"])
        if len(train_g) >= MIN_TRAIN_QUARTERS and not target[C_FEATURES].isna().any():
            q_commodity, commodity = _fit(train_g, C_FEATURES, "net_profit_q", target)
            weight = _choose_weights(train_g, commodity)
            q_pred = weight[0]*q_commodity + weight[1]*target["last_announced_q_profit_bn"] + weight[2]*(target["ttm_announced_profit_bn"] / 4)
            ttm_pred = target["ttm_announced_profit_bn"] - target["last_announced_q_profit_bn"] + q_pred
            ridge = commodity.named_steps["ridge"]
            rows.append({"quarter": target["quarter"], "model": "G_blended_profit", "q_profit_pred_bn": q_pred, "ttm_profit_pred_bn": ttm_pred, "actual_q_profit_bn": target["net_profit_q"], "actual_ttm_profit_bn": target["ttm_net_profit_bn"], "last_announced_q_profit_bn": target["last_announced_q_profit_bn"], "train_quarters_count": len(train_g), "ridge_alpha": ridge.alpha_, "ridge_coef_json": json.dumps(dict(zip(C_FEATURES, ridge.coef_)), ensure_ascii=False), "selected_weights": json.dumps(weight), "data_quality_flag": OPTIONAL_STATUS})
    return pd.DataFrame(rows)


def _current_features(aggregated: pd.DataFrame, financial: pd.DataFrame) -> pd.Series:
    market = read_parquet_or_empty(PROCESSED / "v2_chalco_monthly_market.parquet").copy(); market["date"] = pd.to_datetime(market["date"])
    date = market["date"].max(); quarter = date.to_period("Q").end_time.normalize(); part = market[market["date"].dt.to_period("Q").dt.end_time.dt.normalize().eq(quarter)]
    row = {"date": date, "quarter": quarter, "al_spread_q_mean": part["al_spread"].mean(), "alumina_price_q_mean": part["alumina_price"].mean(), "al_price_q_mean": part["al_price"].mean(), "demand_score_q_mean": part["demand_score"].mean(), "actual_stock_close_raw": part["actual_stock_close_raw"].iloc[-1], "data_quality_flag": str(part["data_quality_flag"].iloc[-1]) + ";" + OPTIONAL_STATUS}
    prior = aggregated[aggregated["quarter"] < quarter].sort_values("quarter")
    for base in ("al_spread_q_mean", "alumina_price_q_mean", "al_price_q_mean"):
        row[f"{base}_lag1"] = prior[base].iloc[-1] if len(prior) else np.nan; row[f"{base}_lag2"] = prior[base].iloc[-2] if len(prior) > 1 else np.nan
    for q in (1,2,3,4): row[f"is_q{q}"] = int(quarter.quarter == q)
    visible = financial[financial["financial_available_date"] <= date].sort_values("financial_available_date")["net_profit_q"].astype(float).tail(4)
    row["last_announced_q_profit_bn"] = visible.iloc[-1] if len(visible) else np.nan; row["ttm_announced_profit_bn"] = visible.sum() if len(visible) == 4 else np.nan; row["last_2q_avg_profit_bn"] = visible.tail(2).mean() if len(visible) >= 2 else np.nan; row["last_4q_avg_profit_bn"] = visible.mean() if len(visible) == 4 else np.nan
    return pd.Series(row)


def _latest_prediction(aggregated: pd.DataFrame, financial: pd.DataFrame, data: pd.DataFrame, selected: str, oos_ttm_r2: float, oos_q_r2: float, oos_n: int) -> pd.DataFrame:
    row = _current_features(aggregated, financial); train = data[data["financial_available_date"] <= row["date"]]
    if selected == "E_ttm_profit_ridge":
        fit_train = train.dropna(subset=E_FEATURES + ["ttm_net_profit_bn"]); ttm_pred, _ = _fit(fit_train, E_FEATURES, "ttm_net_profit_bn", row); q_pred = ttm_pred - row["ttm_announced_profit_bn"] + row["last_announced_q_profit_bn"]; weights = pd.NA
    else:
        fit_train = train.dropna(subset=C_FEATURES + ["net_profit_q", "last_announced_q_profit_bn", "ttm_announced_profit_bn"]); q_commodity, model = _fit(fit_train, C_FEATURES, "net_profit_q", row); w = _choose_weights(fit_train, model); q_pred = w[0]*q_commodity + w[1]*row["last_announced_q_profit_bn"] + w[2]*(row["ttm_announced_profit_bn"]/4); ttm_pred = row["ttm_announced_profit_bn"] - row["last_announced_q_profit_bn"] + q_pred; weights = json.dumps(w)
    pe = float(np.clip(8.5 + 3*(row["demand_score_q_mean"]-.5) - .5*row["is_q4"], 6.5, 11.5)); model_price = q_pred*4/SHARES_BN*pe
    if oos_ttm_r2 >= .7: status = "valuation_anchor_usable_but_signal_requires_confirmation"
    else: status = "research_only_v22_ttm_oos_below_target"
    if oos_q_r2 >= .7 and oos_n >= 10: status = "tradable_signal_candidate"
    return pd.DataFrame([{"date": row["date"], "selected_model": selected, "q_profit_pred_bn": q_pred, "ttm_profit_pred_bn": ttm_pred, "annual_profit_pred_bn": ttm_pred, "eps_pred": ttm_pred/SHARES_BN, "target_pe": pe, "model_price": model_price, "gap": row["actual_stock_close_raw"]/model_price-1, "signal_status": status, "profit_model_warning": "NO_PE_UPLIFT;" + OPTIONAL_STATUS, "selected_weights": weights, "train_quarters_count": len(fit_train), "data_quality_flag": row["data_quality_flag"]}])


def run() -> dict[str, object]:
    aggregated, financial, data = _prepare(); walk = walk_forward(data); full_r2, adjusted = _full_diagnostic(data)
    if walk.empty: raise RuntimeError("insufficient_training_data")
    metrics = pd.DataFrame([_metric(part, model, full_r2 if model == "E_ttm_profit_ridge" else np.nan, adjusted if model == "E_ttm_profit_ridge" else np.nan) for model, part in walk.groupby("model")])
    metrics = pd.concat([metrics, pd.DataFrame([{ "model": "F_industry_segment_proxy", "status": "blocked_missing_auditable_volume", "n": 0, "mae": np.nan, "rmse": np.nan, "mape": np.nan, "bias": np.nan, "r2": np.nan, "adjusted_r2": np.nan, "full_sample_r2": np.nan, "walk_forward_oos_r2": np.nan, "ttm_target_r2": np.nan, "single_quarter_target_r2": np.nan, "directional_accuracy": np.nan, "latest_q_profit_pred": np.nan, "latest_ttm_profit_pred": np.nan, "optional_feature_status": OPTIONAL_STATUS }])], ignore_index=True)
    candidates = metrics[metrics["status"].eq("ok")].sort_values(["walk_forward_oos_r2", "mape"], ascending=[False, True]); selected = str(candidates.iloc[0]["model"]); selected_metrics = candidates.iloc[0]
    prediction = _latest_prediction(aggregated, financial, data, selected, float(selected_metrics["ttm_target_r2"]), float(selected_metrics["single_quarter_target_r2"]), int(selected_metrics["n"]))
    metrics["latest_model_price"] = np.nan; metrics.loc[metrics["model"].eq(selected), "latest_model_price"] = float(prediction.iloc[0]["model_price"]); metrics["signal_status"] = "research_only_v22_ttm_oos_below_target"; metrics.loc[metrics["model"].eq(selected), "signal_status"] = prediction.iloc[0]["signal_status"]
    metrics.to_csv(REPORTS / "v2_chalco_profit_v22_model_comparison.csv", index=False, encoding="utf-8-sig"); walk.to_csv(REPORTS / "v2_chalco_profit_v22_walkforward.csv", index=False, encoding="utf-8-sig"); save_parquet(prediction, PROCESSED / "v2_chalco_profit_v22_predictions.parquet")
    diagnostic_only = bool(full_r2 >= .7 and selected_metrics["ttm_target_r2"] < .7)
    text = "# China Aluminum V2.2 TTM profit-model summary\n\n"
    text += f"- Selected model: `{selected}`.\n- Model E full-sample diagnostic TTM R²: {full_r2:.3f}; adjusted R²: {adjusted if pd.notna(adjusted) else 'not estimable (n <= p + 1)'}.\n"
    text += f"- Selected TTM walk-forward OOS R²: {selected_metrics['ttm_target_r2']:.3f}; single-quarter OOS R²: {selected_metrics['single_quarter_target_r2']:.3f}; OOS independent quarters: {int(selected_metrics['n'])}.\n"
    if diagnostic_only: text += "- R² target reached only in diagnostic mode, not in tradable walk-forward mode.\n"
    if int(selected_metrics['n']) < 10: text += "- Fewer than 10 independent OOS quarters: neither a low single-quarter R² is a final failure nor a high R² is evidence of tradability.\n"
    text += f"- Latest q-profit prediction: {prediction.iloc[0]['q_profit_pred_bn']:.2f} bn RMB; latest TTM-profit prediction: {prediction.iloc[0]['ttm_profit_pred_bn']:.2f} bn RMB; model price at unchanged PE logic: {prediction.iloc[0]['model_price']:.2f}.\n"
    text += f"- Signal status: `{prediction.iloc[0]['signal_status']}`.\n- Optional coal/power/volume fields: {OPTIONAL_STATUS}. Model F is blocked, not silently proxied.\n- No PE uplift, future financials, future announcement dates or full-sample fit are used as trading evidence.\n"
    (REPORTS / "v2_chalco_profit_v22_summary.md").write_text(text, encoding="utf-8")
    return {"selected_model": selected, "ttm_full_sample_r2": round(float(full_r2),4), "selected_ttm_oos_r2": round(float(selected_metrics["ttm_target_r2"]),4), "latest_model_price": round(float(prediction.iloc[0]["model_price"]),4)}


def main() -> None: print(run())
if __name__ == "__main__": main()

