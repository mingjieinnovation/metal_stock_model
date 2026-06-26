"""Generate the fixed cross-frequency model/backtest/factor interpretation report."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from .runtime import PROCESSED, REPORTS, read_parquet_or_empty

ROOT = REPORTS / "frequency_backtest_v2"
BACKTEST = REPORTS / "v2_model_backtest_summary.csv"
FACTORS = REPORTS / "v2_model_factor_importance.csv"
REPORT = REPORTS / "v2_model_explanation_fixed_report.md"

CHALCO_MEANINGS = {
    "al_spread_q_mean": "季度平均铝-氧化铝价差：原铝与氧化铝成本环境的利润代理。",
    "alumina_price_q_mean": "季度平均氧化铝价格：成本压力与氧化铝业务环境代理。",
    "demand_score_q_mean": "需求综合分数：库存、电网、NEV、PMI、地产等；其中多项仍是 DEFAULT_PROXY。",
    "last_announced_q_profit_bn": "最近已公告单季利润：经营利润惯性锚点，仅在公告后可见。",
    "ttm_announced_profit_bn": "已公告 TTM 利润：持续盈利能力锚点，仅在公告后可见。",
    "last_2q_avg_profit_bn": "最近两季已公告利润均值：降低单季偶然波动。",
    "is_q1": "Q1 季节性虚拟变量。", "is_q2": "Q2 季节性虚拟变量。", "is_q3": "Q3 季节性虚拟变量。", "is_q4": "Q4 季节性虚拟变量。",
}
ZIJIN_MEANINGS = {
    "cu_au_revenue_index": "铜金收入指数：(矿产铜×铜价 + 矿产金×1000×金价)/1e9；产量仅使用 strict 可见季度。",
    "revenue_x_demand": "收入指数与需求分数偏离 0.5 的交互项，反映价格/产量环境与需求状态共同变化。",
    "is_q4": "Q4 季节性虚拟变量。",
}


def _parse(value: object) -> dict[str, float]:
    try:
        result = json.loads(str(value))
        return {str(k): float(v) for k, v in result.items()}
    except Exception:
        return {}


def _factor_table(company: str, freq: str, frame: pd.DataFrame) -> pd.DataFrame:
    strict = frame[frame["strict_status"].eq("strict") & frame["ridge_coef_json"].notna()].copy()
    if strict.empty: return pd.DataFrame()
    parsed = strict["ridge_coef_json"].map(_parse); names = sorted(set().union(*parsed.tolist()))
    rows = []
    for name in names:
        coefs = parsed.map(lambda x: x.get(name, np.nan)).dropna()
        if not len(coefs): continue
        if company == "chalco":
            score = coefs.abs().mean()
            method = "mean_abs_standardized_ridge_coefficient"
            meaning = CHALCO_MEANINGS.get(name, "模型特征。")
        else:
            feature_std = pd.to_numeric(strict.get(name), errors="coerce").std() if name in strict else np.nan
            score = coefs.abs().mean() * feature_std if pd.notna(feature_std) else np.nan
            method = "mean_abs_coefficient_times_feature_std"
            meaning = ZIJIN_MEANINGS.get(name, "模型特征。")
        rows.append({"company": company, "frequency": freq, "factor": name, "importance_score": score, "coefficient_mean": coefs.mean(), "coefficient_abs_mean": coefs.abs().mean(), "importance_method": method, "meaning": meaning, "warning": "Model-internal influence proxy; not causal attribution."})
    result = pd.DataFrame(rows)
    if len(result): result["importance_share"] = result["importance_score"] / result["importance_score"].sum()
    return result.sort_values("importance_share", ascending=False)


def _backtest_row(company: str, freq: str) -> tuple[dict, pd.DataFrame]:
    path = ROOT / freq / "walk_forward_strict"; comp = pd.read_csv(path / f"{company}_components.csv"); metrics = pd.read_csv(path / f"{company}_metrics.csv").iloc[0].to_dict(); strict = comp[comp["strict_status"].eq("strict")]
    latest = strict.iloc[-1]
    row = {"company": company, "frequency": freq, "model": latest.get("profit_model_version", latest.get("model_version")), "selected_profit_model": latest.get("selected_profit_model", pd.NA), "n": metrics.get("n"), "start_date": metrics.get("start_date"), "end_date": metrics.get("end_date"), "mae": metrics.get("mae"), "rmse": metrics.get("rmse"), "mape": metrics.get("mape"), "r2_price_model": metrics.get("r2"), "corr_price_model": metrics.get("corr"), "within_10pct": metrics.get("within_10pct"), "within_15pct": metrics.get("within_15pct"), "latest_actual": latest.get("actual_stock_close_raw"), "latest_model_price": latest.get("model_price"), "latest_gap": latest.get("gap"), "latest_raw_signal": latest.get("raw_signal", latest.get("signal")), "signal_status": latest.get("signal_status", "active"), "train_quarters_count": latest.get("train_quarters_count"), "data_quality_flag": latest.get("data_quality_flag")}
    return row, _factor_table(company, freq, comp)


def _markdown_table(frame: pd.DataFrame, cols: list[str]) -> str:
    if frame.empty: return "无可用数据。\n"
    view = frame[cols].copy()
    for col in view.select_dtypes(include="number"):
        view[col] = view[col].map(lambda x: "" if pd.isna(x) else f"{x:.3f}")
    return view.to_markdown(index=False) + "\n"


def run() -> dict[str, int]:
    backtests, factor_frames = [], []
    for company in ("chalco", "zijin"):
        for freq in ("monthly", "weekly", "daily"):
            row, factors = _backtest_row(company, freq); backtests.append(row); factor_frames.append(factors)
    back = pd.DataFrame(backtests); factor = pd.concat(factor_frames, ignore_index=True)
    # V2.2 monthly TTM anchor is reported separately from the high-frequency C
    # price backtests, to avoid pretending it has daily/weekly TTM validation.
    v22_metrics = pd.read_csv(REPORTS / "v2_chalco_profit_v22_model_comparison.csv")
    v22_selected = v22_metrics[v22_metrics["model"].eq("G_blended_profit")].iloc[0]
    v22_pred = read_parquet_or_empty(PROCESSED / "v2_chalco_profit_v22_predictions.parquet").iloc[-1]
    anchor_row = {"company": "chalco", "frequency": "monthly", "model": "v2_2_chalco_profit_model", "selected_profit_model": "G_blended_profit", "n": v22_selected["n"], "start_date": pd.NA, "end_date": v22_pred["date"], "mae": v22_selected["mae"], "rmse": v22_selected["rmse"], "mape": v22_selected["mape"], "r2_price_model": pd.NA, "corr_price_model": pd.NA, "within_10pct": pd.NA, "within_15pct": pd.NA, "latest_actual": pd.NA, "latest_model_price": v22_pred["model_price"], "latest_gap": v22_pred["gap"], "latest_raw_signal": pd.NA, "signal_status": v22_pred["signal_status"], "train_quarters_count": v22_pred["train_quarters_count"], "data_quality_flag": v22_pred["data_quality_flag"], "ttm_full_sample_r2": v22_selected["full_sample_r2"], "ttm_oos_r2": v22_selected["ttm_target_r2"], "single_quarter_oos_r2": v22_selected["single_quarter_target_r2"]}
    back = pd.concat([back, pd.DataFrame([anchor_row])], ignore_index=True)
    back.to_csv(BACKTEST, index=False, encoding="utf-8-sig"); factor.to_csv(FACTORS, index=False, encoding="utf-8-sig")

    text = "# 金属股票模型固定报告\n\n"
    text += "## 阅读方式\n\n"
    text += "- R²/MAE/RMSE 是价格模型的回测拟合指标，不等于因果解释或可交易证明。\n"
    text += "- 中铝月度 V2.2 的 TTM R² 单列：0.915 是 full-sample diagnostic；-1.708 是 walk-forward OOS，不能混用。\n"
    text += "- 紫金产量使用 strict 可见季度；中铝需求层仍含 DEFAULT_PROXY，煤/电/产量未作为伪造的 strict 数据引入。\n\n"
    text += "## 一、中铝：中国铝业\n\n"
    text += "### 模型与用途\n\n"
    text += "- 月度：`monthly_v22_valuation_anchor`。V2.2 G 使用 TTM/已公告利润锚与商品利润混合；用于估值中枢和持仓判断。\n"
    text += "- 周度：`weekly_v22_trading_observation`。使用 V2.1-C 利润锚点 Ridge 的 raw gap 进行 4W/13W/26W 观察；仅与月度同向才可标为 research-only stronger observation。\n"
    text += "- 日度：`daily_v22_gap_alert`。同一 C 模型的日度 gap，仅报警，禁止单独生成 tradable signal。\n"
    text += "- C 因子：商品价差/氧化铝环境、需求分数、最近已公告利润、TTM 已公告利润、近两季均值和完整季度季节性。\n\n"
    text += _markdown_table(back[(back.company=="chalco") & back.model.ne("v2_2_chalco_profit_model")], ["frequency","model","selected_profit_model","n","mae","rmse","mape","r2_price_model","corr_price_model","latest_actual","latest_model_price","latest_gap","latest_raw_signal","signal_status"])
    text += "### V2.2 月度 TTM 估值锚\n\n"
    text += _markdown_table(back[back.model.eq("v2_2_chalco_profit_model")], ["n","mae","rmse","mape","ttm_full_sample_r2","ttm_oos_r2","single_quarter_oos_r2","latest_model_price","latest_gap","signal_status"])
    text += "### 中铝因子相对影响\n\n"
    text += _markdown_table(factor[factor.company.eq("chalco")], ["frequency","factor","importance_share","coefficient_mean","meaning","importance_method"])
    text += "\n## 二、紫金矿业\n\n"
    text += "### 模型与用途\n\n"
    text += "- 利润模型：`cu_au_revenue_index + revenue_x_demand + is_q4` 的 expanding Ridge。\n"
    text += "- 铜金收入指数使用 strict 已公告矿产铜/矿产金产量与当期铜、金价格；收入×需求交互项反映宏观需求状态；Q4 吸收季节性。\n"
    text += "- 日/周/月均在财务和 strict 产量公告后 backward as-of 更新。日/周频提高估值刷新次数，不增加独立季度利润样本。\n\n"
    text += _markdown_table(back[back.company.eq("zijin")], ["frequency","model","n","mae","rmse","mape","r2_price_model","corr_price_model","latest_actual","latest_model_price","latest_gap","latest_raw_signal","signal_status"])
    text += "### 紫金因子相对影响\n\n"
    text += _markdown_table(factor[factor.company.eq("zijin")], ["frequency","factor","importance_share","coefficient_mean","meaning","importance_method"])
    text += "\n## 三、解读边界\n\n"
    text += "- 因子相对影响：中铝 C 使用标准化 Ridge 系数绝对值；紫金使用 `|系数|×特征历史标准差` 归一化。因此它们是模型内部影响代理，不能解释成利润的真实因果贡献。\n"
    text += "- 中铝：当前任何日/周/月 gap 仍是研究用途；月度 TTM OOS 未达到 0.7，且独立季度少于 10。\n"
    text += "- 紫金：价格回测较稳定，但同样受季度样本数量、生产解析质量与需求代理限制；不构成投资建议。\n"
    REPORT.write_text(text, encoding="utf-8")
    return {"backtest_rows": len(back), "factor_rows": len(factor)}


def main() -> None: print(run())
if __name__ == "__main__": main()
