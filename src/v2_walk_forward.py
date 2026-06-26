"""Auditable monthly expanding walk-forward backtest for the V2 strict model.

Strict refers to the production series: no annual allocation, no forward-fill and
no proxy production is admitted.  Demand inputs may contain explicitly labelled
DEFAULT_PROXY values; they are retained for model transparency, not disguised as
observations.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

os.environ.setdefault('MPLCONFIGDIR', str(Path.cwd() / '.cache' / 'matplotlib'))

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.linear_model import RidgeCV
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

from .runtime import PROCESSED, REPORTS, read_parquet_or_empty
from .v2_model_core import VERSION, signal

ALPHAS = [0.01, 0.1, 1, 5, 10, 20, 50]
MIN_TRAIN_QUARTERS = 6
FREQUENCIES = ("daily", "weekly", "monthly")


def _quarter_end(year: pd.Series, quarter: pd.Series) -> pd.Series:
    return pd.to_datetime(year.astype(int).astype(str) + "-" + (quarter.astype(int) * 3).astype(str) + "-01") + pd.offsets.MonthEnd(0)


def _fallback_available_date(quarter: pd.Series) -> pd.Series:
    quarter = pd.to_datetime(quarter)
    days = quarter.dt.quarter.map({1: 45, 2: 60, 3: 45, 4: 120})
    return quarter + pd.to_timedelta(days, unit="D")


def asof_join_quarterly_to_monthly(
    monthly_df: pd.DataFrame,
    quarterly_df: pd.DataFrame,
    date_col: str = "date",
    available_col: str = "available_date",
) -> pd.DataFrame:
    """Backward as-of join: a month only sees reports public by month end."""
    left = monthly_df.copy().sort_values(date_col)
    right = quarterly_df.copy().sort_values(available_col)
    left[date_col] = pd.to_datetime(left[date_col])
    right[available_col] = pd.to_datetime(right[available_col])
    return pd.merge_asof(left, right, left_on=date_col, right_on=available_col, direction="backward")


def _announcement_dates(code: str) -> pd.DataFrame:
    index = read_parquet_or_empty(PROCESSED / "announcement_index.parquet")
    if index.empty:
        return pd.DataFrame(columns=["quarter", "cninfo_announcement_date"])
    index = index.copy()
    index["code"] = index["code"].astype(str).str.zfill(6)
    index = index[index["code"] == code]
    index["announcement_time"] = pd.to_datetime(index["announcement_time"], errors="coerce")
    index["quarter"] = _quarter_end(index["report_year"], index["report_quarter"])
    return index.groupby("quarter", as_index=False)["announcement_time"].min().rename(columns={"announcement_time": "cninfo_announcement_date"})


def _financial(code: str) -> pd.DataFrame:
    financial = read_parquet_or_empty(PROCESSED / "financial_quarterly.parquet")
    required = {"quarter", "code", "net_profit_q", "revenue_q", "eps_q", "announcement_date"}
    if financial.empty or not required.issubset(financial.columns):
        return pd.DataFrame(columns=["quarter", "net_profit_q", "financial_available_date"])
    financial = financial.copy()
    financial["code"] = financial["code"].astype(str).str.zfill(6)
    financial = financial[financial["code"] == code]
    financial["quarter"] = pd.to_datetime(financial["quarter"])
    financial["announcement_date"] = pd.to_datetime(financial["announcement_date"], errors="coerce")
    financial = financial.merge(_announcement_dates(code), on="quarter", how="left")
    financial["financial_available_date"] = financial["cninfo_announcement_date"].fillna(financial["announcement_date"])
    financial["financial_available_date"] = financial["financial_available_date"].fillna(_fallback_available_date(financial["quarter"]))
    financial["financial_announcement_source"] = np.where(
        financial["cninfo_announcement_date"].notna(), "CNINFO_ANNOUNCEMENT_INDEX",
        np.where(financial["announcement_date"].notna(), "FINANCIAL_SOURCE", "CALENDAR_FALLBACK"),
    )
    return financial.sort_values("financial_available_date").drop_duplicates("quarter", keep="last").reset_index(drop=True)


def _market(name: str, company: str) -> pd.DataFrame:
    market = read_parquet_or_empty(PROCESSED / name)
    if market.empty:
        return market
    market = market.copy()
    market["date"] = pd.to_datetime(market["date"])
    rename = {"zijin_demand_score": "demand_score"}
    market = market.rename(columns={key: value for key, value in rename.items() if key in market and value not in market})
    market["company"] = company
    market["is_q4"] = market.get("is_q4", market["date"].dt.quarter.eq(4).astype(int)).fillna(0).astype(int)
    return market.sort_values("date").reset_index(drop=True)


def _quarter_market_samples(market: pd.DataFrame) -> pd.DataFrame:
    """Map each report-period end to its last observable market record."""
    start = pd.Timestamp(market["date"].min()).to_period("Q").end_time.normalize()
    end = pd.Timestamp(market["date"].max()).to_period("Q").end_time.normalize()
    quarters = pd.DataFrame({"quarter": pd.date_range(start, end, freq="QE")})
    return pd.merge_asof(quarters.sort_values("quarter"), market.sort_values("date"), left_on="quarter", right_on="date", direction="backward")


def _strict_production() -> pd.DataFrame:
    production = read_parquet_or_empty(PROCESSED / "v2_zijin_strict_production.parquet")
    required = {"quarter", "cu_ton", "au_kg", "strict_usable"}
    if production.empty or not required.issubset(production.columns):
        return pd.DataFrame(columns=["quarter", "cu_ton", "au_kg", "production_available_date"])
    production = production.copy()
    production["quarter"] = pd.to_datetime(production["quarter"])
    production = production[production["strict_usable"].fillna(False)].copy()
    if "parse_confidence" in production:
        production = production[production["parse_confidence"].fillna(0).astype(float) >= 0.7].copy()
    if "source_period" in production:
        production = production[production["source_period"].astype(str).str.contains("STRICT_SINGLE|2026Q1", regex=True, na=False)]
    production["production_available_date"] = pd.to_datetime(production.get("production_available_date", production.get("effective_date")), errors="coerce")
    production["production_available_date"] = production["production_available_date"].fillna(_fallback_available_date(production["quarter"]))
    return production.sort_values("production_available_date").drop_duplicates("quarter", keep="last").reset_index(drop=True)


def _visible_financial(monthly: pd.DataFrame, financial: pd.DataFrame) -> pd.DataFrame:
    visible = financial[["quarter", "financial_available_date"]].rename(columns={"quarter": "visible_quarter", "financial_available_date": "visible_financial_announcement_date"})
    visible["available_date"] = visible["visible_financial_announcement_date"]
    joined = asof_join_quarterly_to_monthly(monthly, visible, available_col="available_date")
    return joined.drop(columns=["available_date"], errors="ignore")


def _visible_production(monthly: pd.DataFrame, production: pd.DataFrame) -> pd.DataFrame:
    visible_columns = ["quarter", "production_available_date", "cu_ton", "au_kg", "source_pdf", "source_title", "parse_confidence", "data_quality_flag", "strict_usable"]
    available = production[[c for c in visible_columns if c in production]].copy()
    available = available.rename(columns={
        "quarter": "visible_production_quarter", "production_available_date": "visible_production_available_date",
        "source_pdf": "production_data_source", "strict_usable": "production_strict_usable",
        "data_quality_flag": "production_data_quality_flag",
    })
    available["available_date"] = available["visible_production_available_date"]
    joined = asof_join_quarterly_to_monthly(monthly, available, available_col="available_date")
    return joined.drop(columns=["available_date"], errors="ignore")


def _fit_predict(train: pd.DataFrame, features: list[str], row: pd.Series) -> tuple[float, float, float, dict[str, float]]:
    model = RidgeCV(alphas=ALPHAS)
    model.fit(train[features], train["net_profit_q"])
    prediction = float(model.predict(pd.DataFrame([row[features]], columns=features))[0])
    coefficients = {feature: float(value) for feature, value in zip(features, model.coef_)}
    return prediction, float(model.alpha_), float(model.intercept_), coefficients


def _base_row(row: pd.Series, company: str, frequency: str) -> dict:
    return {
        "trade_date": row["date"], "company": company, "frequency": frequency, "mode": "walk_forward_strict",
        "model_version": VERSION, "profit_model_version": "v2_chalco_original_profit_model" if company == "chalco" else VERSION, "strict_status": "blocked", "blocked_reason": "", "signal_status": "not_available",
        "actual_stock_close_raw": row.get("actual_stock_close_raw"), "model_price": np.nan, "gap": np.nan, "signal": pd.NA,
        "q_profit_pred_bn": np.nan, "annual_profit_pred_bn": np.nan, "eps_pred": np.nan, "target_pe": np.nan,
        "demand_score": row.get("demand_score"), "is_q4": row.get("is_q4"),
        "visible_quarter": row.get("visible_quarter"),
        "visible_financial_announcement_date": row.get("visible_financial_announcement_date"),
        "visible_production_available_date": row.get("visible_production_available_date"),
        "train_quarters_count": 0, "ridge_alpha": np.nan, "ridge_intercept": np.nan, "ridge_coef_json": pd.NA,
        "data_quality_flag": row.get("data_quality_flag", ""),
    }


def _enrich_chalco(row: pd.Series, output: dict) -> None:
    for col in ["al_price", "alumina_price", "al_spread", "al_spread_k", "alumina_price_k", "inventory_score", "al_price_trend_score", "al_spread_score", "grid_proxy_score", "nev_proxy_score", "pmi_score", "property_proxy_score", "alumina_price_source"]:
        output[col] = row.get(col, pd.NA)


def _enrich_zijin(row: pd.Series, output: dict) -> None:
    for col in ["cu_price", "au_price_rmb_g", "cu_ton", "au_kg", "cu_au_revenue_index", "revenue_x_demand", "cu_demand_score", "au_demand_score", "cu_inventory_score", "cu_price_trend_score", "power_grid_proxy_score", "pmi_score", "risk_score", "real_rate_score", "central_bank_gold_proxy_score", "gold_etf_proxy_score", "usd_score", "production_data_source", "production_strict_usable", "parse_confidence"]:
        output[col] = row.get(col, pd.NA)


def _quarter_training_chalco(market: pd.DataFrame, financial: pd.DataFrame) -> pd.DataFrame:
    samples = _quarter_market_samples(market).merge(financial, on="quarter", how="inner", suffixes=("", "_financial"))
    samples["training_available_date"] = samples["financial_available_date"]
    return samples


def _quarter_training_zijin(market: pd.DataFrame, financial: pd.DataFrame, production: pd.DataFrame) -> pd.DataFrame:
    production_fields = ["quarter", "cu_ton", "au_kg", "production_available_date", "strict_usable", "parse_confidence", "source_pdf"]
    samples = _quarter_market_samples(market).merge(financial, on="quarter", how="inner", suffixes=("", "_financial"))
    samples = samples.merge(production[[c for c in production_fields if c in production]], on="quarter", how="inner")
    samples["cu_au_revenue_index"] = (samples["cu_ton"] * samples["cu_price"] + samples["au_kg"] * 1000 * samples["au_price_rmb_g"]) / 1e9
    samples["revenue_x_demand"] = samples["cu_au_revenue_index"] * (samples["demand_score"] - 0.5)
    samples["training_available_date"] = samples[["financial_available_date", "production_available_date"]].max(axis=1)
    return samples


CHALCO_C_FEATURES = ["al_spread_q_mean", "alumina_price_q_mean", "demand_score_q_mean", "last_announced_q_profit_bn", "ttm_announced_profit_bn", "last_2q_avg_profit_bn", "is_q1", "is_q2", "is_q3", "is_q4"]

def _chalco_anchor(financial: pd.DataFrame, available_at: pd.Timestamp) -> dict[str, float]:
    visible = financial[financial["financial_available_date"] <= available_at].sort_values("financial_available_date")["net_profit_q"].astype(float).tail(4)
    return {"last_announced_q_profit_bn": visible.iloc[-1] if len(visible) else np.nan, "ttm_announced_profit_bn": visible.sum() if len(visible) == 4 else np.nan, "last_2q_avg_profit_bn": visible.tail(2).mean() if len(visible) >= 2 else np.nan}

def _chalco_c_training(market: pd.DataFrame, financial: pd.DataFrame) -> pd.DataFrame:
    source = market.copy(); source["quarter"] = source["date"].dt.to_period("Q").dt.end_time.dt.normalize()
    quarterly = source.groupby("quarter", as_index=False).agg(al_spread_q_mean=("al_spread", "mean"), alumina_price_q_mean=("alumina_price", "mean"), demand_score_q_mean=("demand_score", "mean"))
    for q in (1, 2, 3, 4): quarterly[f"is_q{q}"] = quarterly["quarter"].dt.quarter.eq(q).astype(int)
    anchors = pd.DataFrame([_chalco_anchor(financial, q) for q in quarterly["quarter"]])
    quarterly = pd.concat([quarterly, anchors], axis=1).merge(financial, on="quarter", how="inner")
    return quarterly

def _chalco_c_current(market: pd.DataFrame, row: pd.Series, financial: pd.DataFrame) -> pd.Series:
    current_quarter = pd.Timestamp(row["date"]).to_period("Q").end_time.normalize()
    part = market[(market["date"] <= row["date"]) & (market["date"].dt.to_period("Q").dt.end_time.dt.normalize() == current_quarter)]
    current = row.copy(); current["al_spread_q_mean"] = part["al_spread"].mean(); current["alumina_price_q_mean"] = part["alumina_price"].mean(); current["demand_score_q_mean"] = part["demand_score"].mean()
    for key, value in _chalco_anchor(financial, pd.Timestamp(row["date"])).items(): current[key] = value
    for q in (1, 2, 3, 4): current[f"is_q{q}"] = int(current_quarter.quarter == q)
    return current

def _fit_chalco_c(train: pd.DataFrame, row: pd.Series) -> tuple[float, float, float, dict[str, float]]:
    model = Pipeline([( "scale", StandardScaler()), ("ridge", RidgeCV(alphas=ALPHAS))])
    model.fit(train[CHALCO_C_FEATURES], train["net_profit_q"])
    ridge = model.named_steps["ridge"]
    pred = float(model.predict(pd.DataFrame([row[CHALCO_C_FEATURES]], columns=CHALCO_C_FEATURES))[0])
    return pred, float(ridge.alpha_), float(ridge.intercept_), {feature: float(value) for feature, value in zip(CHALCO_C_FEATURES, ridge.coef_)}

def _walk(company: str, market: pd.DataFrame, financial: pd.DataFrame, production: pd.DataFrame | None = None, frequency: str = "monthly") -> pd.DataFrame:
    if market.empty:
        return pd.DataFrame()
    monthly = _visible_financial(market, financial)
    if company == "zijin":
        assert production is not None
        monthly = _visible_production(monthly, production)
        monthly["cu_au_revenue_index"] = (monthly["cu_ton"] * monthly["cu_price"] + monthly["au_kg"] * 1000 * monthly["au_price_rmb_g"]) / 1e9
        monthly["revenue_x_demand"] = monthly["cu_au_revenue_index"] * (monthly["demand_score"] - 0.5)
        training = _quarter_training_zijin(market, financial, production)
        features = ["cu_au_revenue_index", "revenue_x_demand", "is_q4"]
    else:
        training = _chalco_c_training(market, financial)
        training["training_available_date"] = training["financial_available_date"]
        features = CHALCO_C_FEATURES
    training = training.dropna(subset=features + ["net_profit_q", "training_available_date"]).sort_values("training_available_date")

    components: list[dict] = []
    for _, monthly_row in monthly.iterrows():
        out = _base_row(monthly_row, company, frequency)
        if company == "chalco":
            _enrich_chalco(monthly_row, out)
        else:
            _enrich_zijin(monthly_row, out)
        current_row = _chalco_c_current(market, monthly_row, financial) if company == "chalco" else monthly_row
        if any(pd.isna(current_row.get(feature)) for feature in features):
            out["blocked_reason"] = f"missing_{frequency}_market_data" if company == "chalco" else "missing_strict_production"
            components.append(out); continue
        available = training[training["training_available_date"] <= monthly_row["date"]]
        out["train_quarters_count"] = len(available)
        if len(available) < MIN_TRAIN_QUARTERS:
            out["blocked_reason"] = "insufficient_training_data"
            components.append(out); continue
        try:
            pred, alpha, intercept, coefficients = _fit_chalco_c(available, current_row) if company == "chalco" else _fit_predict(available, features, monthly_row)
        except Exception as exc:  # explicit audit outcome instead of a blank result
            out["blocked_reason"] = f"model_fit_failed:{type(exc).__name__}"
            components.append(out); continue
        annual = pred * 4
        shares = 171.55 if company == "chalco" else 265.91
        pe = (8.5 + 3.0 * (monthly_row["demand_score"] - 0.5) - 0.5 * monthly_row["is_q4"]) if company == "chalco" else (11.0 + 4.0 * (monthly_row["demand_score"] - 0.5) + 0.5 - 0.3)
        pe = float(np.clip(pe, 6.5, 11.5) if company == "chalco" else np.clip(pe, 8.5, 15.0))
        model_price = annual / shares * pe
        if not np.isfinite(model_price) or model_price <= 0:
            out["blocked_reason"] = "nonpositive_model_price"
            components.append(out); continue
        out.update({"strict_status": "strict", "q_profit_pred_bn": pred, "annual_profit_pred_bn": annual, "eps_pred": annual / shares, "target_pe": pe, "model_price": model_price, "gap": monthly_row["actual_stock_close_raw"] / model_price - 1, "ridge_alpha": alpha, "ridge_intercept": intercept, "ridge_coef_json": json.dumps(coefficients, ensure_ascii=False), "blocked_reason": ""})
        if company == "chalco":
            out.update({"profit_model_version": "v2_1_chalco_profit_model", "selected_profit_model": "C_profit_anchor_ridge", "al_spread_q_mean": current_row["al_spread_q_mean"], "alumina_price_q_mean": current_row["alumina_price_q_mean"], "demand_score_q_mean": current_row["demand_score_q_mean"], "last_announced_q_profit_bn": current_row["last_announced_q_profit_bn"], "ttm_announced_profit_bn": current_row["ttm_announced_profit_bn"], "last_2q_avg_profit_bn": current_row["last_2q_avg_profit_bn"]})
        raw_signal = signal(pd.Series([out["gap"]]))[0]
        if company == "chalco":
            out["raw_signal"] = raw_signal
            out["signal"] = "research_only_v21_insufficient_oos"
            out["signal_status"] = "research_only_v21_insufficient_oos"
        else:
            out["signal"] = raw_signal
            out["signal_status"] = "active"
        components.append(out)
    frame = pd.DataFrame(components)
    suffix = {"daily": "d", "weekly": "w", "monthly": "m"}[frequency]
    for horizon in (1, 3, 6):
        frame[f"fwd_{horizon}{suffix}_return"] = frame["actual_stock_close_raw"].shift(-horizon) / frame["actual_stock_close_raw"] - 1
    return frame


def _metrics(frame: pd.DataFrame) -> pd.DataFrame:
    usable = frame[frame["strict_status"].eq("strict") & frame["model_price"].notna()].copy()
    result = {"n": len(usable), "start_date": usable["trade_date"].min() if len(usable) else pd.NaT, "end_date": usable["trade_date"].max() if len(usable) else pd.NaT, "latest_actual": usable["actual_stock_close_raw"].iloc[-1] if len(usable) else np.nan, "latest_model_price": usable["model_price"].iloc[-1] if len(usable) else np.nan, "latest_gap": usable["gap"].iloc[-1] if len(usable) else np.nan, "mae": np.nan, "rmse": np.nan, "mape": np.nan, "r2": np.nan, "corr": np.nan, "within_10pct": np.nan, "within_15pct": np.nan, "blocked_months": int(len(frame) - len(usable)), "usable_months": len(usable), "undervalued_periods": int(usable["signal"].eq("undervalued").sum()), "neutral_periods": int(usable["signal"].eq("neutral").sum()), "overvalued_periods": int(usable["signal"].eq("overvalued").sum())}
    if len(usable):
        actual, predicted = usable["actual_stock_close_raw"], usable["model_price"]
        result.update({"mae": mean_absolute_error(actual, predicted), "rmse": mean_squared_error(actual, predicted) ** 0.5, "mape": (np.abs(actual - predicted) / actual).mean(), "within_10pct": (np.abs(usable["gap"]) <= .10).mean(), "within_15pct": (np.abs(usable["gap"]) <= .15).mean()})
        if len(usable) >= 2:
            result["r2"] = r2_score(actual, predicted); result["corr"] = actual.corr(predicted)
    return pd.DataFrame([result])


def _signal_summary(frame: pd.DataFrame, frequency: str) -> pd.DataFrame:
    usable = frame[frame["strict_status"].eq("strict")].copy()
    rows = []
    for current_signal in ["undervalued", "neutral", "overvalued"]:
        part = usable[usable["signal"].eq(current_signal)]
        row = {"signal": current_signal, "n_total": len(part), "avg_gap": part["gap"].mean()}
        for horizon in (1, 3, 6):
            suffix = {"daily": "d", "weekly": "w", "monthly": "m"}[frequency]; column = f"fwd_{horizon}{suffix}_return"; values = part[column].dropna()
            row[f"avg_fwd_{horizon}{suffix}_return"] = values.mean()
            if current_signal == "undervalued": hit = values.gt(0)
            elif current_signal == "overvalued": hit = values.lt(0)
            else: hit = values.abs().le(.12)
            row[f"hit_fwd_{horizon}{suffix}"] = hit.mean() if len(values) else np.nan
        rows.append(row)
    return pd.DataFrame(rows)


def _plots(company: str, frame: pd.DataFrame, outdir: Path, frequency: str) -> None:
    usable = frame[frame["strict_status"].eq("strict")].copy()
    if len(usable) < 6:
        return
    x = pd.to_datetime(usable["trade_date"])
    fig, ax = plt.subplots(figsize=(10, 4)); ax.plot(x, usable["actual_stock_close_raw"], label="actual raw close"); ax.plot(x, usable["model_price"], label="V2 model price"); ax.set_title(f"{company} {frequency}: actual vs V2 strict model price"); ax.legend(); fig.autofmt_xdate(); fig.tight_layout(); fig.savefig(outdir / f"{company}_actual_vs_predicted.png", dpi=150); plt.close(fig)
    fig, ax = plt.subplots(figsize=(10, 4)); ax.plot(x, usable["gap"], label="gap"); ax.axhline(.12, color="red", linestyle="--", label="+12%"); ax.axhline(-.12, color="green", linestyle="--", label="-12%"); ax.axhline(0, color="black", linewidth=.8); ax.set_title(f"{company} {frequency}: valuation gap"); ax.legend(); fig.autofmt_xdate(); fig.tight_layout(); fig.savefig(outdir / f"{company}_gap.png", dpi=150); plt.close(fig)


def _write_company(company: str, frame: pd.DataFrame, outdir: Path, frequency: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    metrics = _metrics(frame); signals = _signal_summary(frame, frequency)
    frame.to_csv(outdir / f"{company}_components.csv", index=False, encoding="utf-8-sig")
    frame[frame["strict_status"].eq("strict")].to_csv(outdir / f"{company}_backtest.csv", index=False, encoding="utf-8-sig")
    metrics.to_csv(outdir / f"{company}_metrics.csv", index=False, encoding="utf-8-sig")
    signals.to_csv(outdir / f"{company}_signal_summary.csv", index=False, encoding="utf-8-sig")
    _plots(company, frame, outdir, frequency)
    return metrics, signals


def _summary(chalco: pd.DataFrame, zijin: pd.DataFrame, production: pd.DataFrame, outdir: Path, frequency: str) -> None:
    def status(frame: pd.DataFrame) -> str:
        blocked = frame.loc[frame["strict_status"].eq("blocked"), "blocked_reason"].value_counts().to_dict()
        return f"usable {frequency} rows: {int(frame['strict_status'].eq('strict').sum())}; blocked rows: {int(frame['strict_status'].eq('blocked').sum())}; blocked reasons: {blocked}"
    text = f"# V2 {frequency} strict walk-forward summary\n\n"
    text += "- V2 strict calculation layer connected: True\n"
    text += f"- 中国铝业：{status(chalco)}\n"
    text += f"- 紫金矿业：{status(zijin)}\n"
    quarters = ", ".join(pd.to_datetime(production["quarter"]).dt.to_period("Q").astype(str).tolist()) if len(production) else "none"
    text += f"- 紫金 strict 产量覆盖季度：{quarters}\n"
    text += "- 财务与产量均采用公告日期 backward as-of；没有年度均分、生产 forward-fill 或 proxy 生产。\n"
    text += "- 中国铝业：已切换至 V2.1 的 C_profit_anchor_ridge 利润层；因独立 OOS 季度仍很少，gap 信号标记为 research_only_v21_insufficient_oos，raw_signal 仅作诊断，不可交易。\n"
    text += "- DEFAULT_PROXY 需求字段逐行标在 data_quality_flag；strict 仅指产量层，不表示需求代理已变为真实观测。\n"
    text += "- 重要限制：日/周频会增加估值更新次数，但利润训练样本仍是公告后的季度数据；高频行之间高度相关，不能按行数理解为独立样本或交易有效性。\n"
    text += "- 输出为研究回测，不构成投资建议。\n"
    outdir.joinpath("summary.md").write_text(text, encoding="utf-8")


def run_v2_walk_forward_strict(frequency: str = "monthly") -> dict[str, int]:
    if frequency not in FREQUENCIES:
        raise ValueError(f"Unsupported frequency: {frequency}")
    outdir = REPORTS / "frequency_backtest_v2" / frequency / "walk_forward_strict"
    outdir.mkdir(parents=True, exist_ok=True)
    chalco_market = _market(f"v2_chalco_{frequency}_market.parquet", "chalco")
    zijin_market = _market(f"v2_zijin_{frequency}_market.parquet", "zijin")
    chalco_financial, zijin_financial = _financial("601600"), _financial("601899")
    production = _strict_production()
    if production["quarter"].nunique() < MIN_TRAIN_QUARTERS:
        raise RuntimeError("missing_strict_production: fewer than six strict production quarters")
    chalco = _walk("chalco", chalco_market, chalco_financial, frequency=frequency)
    zijin = _walk("zijin", zijin_market, zijin_financial, production, frequency)
    if chalco.empty or zijin.empty:
        raise RuntimeError(f"missing_{frequency}_market_data or missing_financial_quarterly")
    _write_company("chalco", chalco, outdir, frequency); _write_company("zijin", zijin, outdir, frequency)
    _summary(chalco, zijin, production, outdir, frequency)
    return {"frequency": frequency, "chalco_usable_rows": int(chalco["strict_status"].eq("strict").sum()), "zijin_usable_rows": int(zijin["strict_status"].eq("strict").sum()), "strict_production_quarters": int(production["quarter"].nunique())}


def run_v2_monthly_walk_forward_strict() -> dict[str, int]:
    return run_v2_walk_forward_strict("monthly")


def main() -> None:
    parser = argparse.ArgumentParser(); parser.add_argument("--frequency", choices=FREQUENCIES, default="monthly"); args = parser.parse_args()
    print(run_v2_walk_forward_strict(args.frequency))


if __name__ == "__main__":
    main()



