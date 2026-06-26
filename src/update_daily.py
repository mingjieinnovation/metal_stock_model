from __future__ import annotations

import logging

import joblib
import numpy as np
import pandas as pd

from .fit_profit_models import SPECS
from .runtime import MODELS, PROCESSED, RAW, REPORTS, ensure_layout, read_parquet_or_empty

NAMES = {"chalco": "中国铝业 601600.SH", "zijin": "紫金矿业 601899.SH"}
TARGET_PE = {"chalco": 10.0, "zijin": 15.0}


def _latest_raw_price(company: str) -> dict:
    code = "601600" if company == "chalco" else "601899"
    data = read_parquet_or_empty(RAW / "stock_daily_raw" / f"{code}.parquet")
    valid = not data.empty and "adjust" in data and set(data["adjust"].dropna().astype(str)) == {"none"}
    if not valid:
        return {"actual_stock_price": np.nan, "stock_price_provider": "UNAVAILABLE", "stock_price_adjust": "invalid", "latest_trade_date": "", "stock_cache_age_days": np.nan, "market_price_verified": False}
    data["date"] = pd.to_datetime(data["date"], errors="coerce")
    last = data.dropna(subset=["date", "close"]).sort_values("date").iloc[-1]
    return {"actual_stock_price": float(last.close), "stock_price_provider": str(last.provider), "stock_price_adjust": str(last.adjust), "latest_trade_date": last.date.strftime("%Y-%m-%d"), "stock_cache_age_days": (pd.Timestamp.now().normalize() - last.date.normalize()).days, "market_price_verified": True}



def _monthly_market_estimate(company: str) -> float:
    """Use final walk-forward prediction so signal equals latest backtest row."""
    path = REPORTS / f"{company}_market_monthly_backtest.csv"
    if not path.exists(): return np.nan
    data = pd.read_csv(path).dropna(subset=["predicted_stock_close"])
    return float(data.iloc[-1]["predicted_stock_close"]) if not data.empty else np.nan
def _signal(company: str) -> dict:
    data = read_parquet_or_empty(PROCESSED / f"{company}_quarterly_features.parquet")
    if data.empty:
        return {"company": NAMES[company], "status": "missing_features"}
    features = SPECS[company]; usable = data.dropna(subset=features).sort_values("quarter")
    latest = usable.iloc[-1] if not usable.empty else data.sort_values("quarter").iloc[-1]
    forecast = np.nan; status = "model_unavailable"
    model_path = MODELS / f"{company}_profit_model.joblib"
    if model_path.exists() and not usable.empty:
        try:
            forecast = float(joblib.load(model_path).predict(pd.DataFrame([latest[features].to_dict()]))[0]); status = "ok"
        except Exception as exc: logging.warning("%s model prediction failed: %s", company, exc)
    eps_q = pd.to_numeric(latest.get("eps"), errors="coerce")
    annual_profit = forecast * 4 if pd.notna(forecast) else np.nan
    annual_eps = eps_q * 4 if pd.notna(eps_q) else np.nan
    profit_pe_fair_value = annual_eps * TARGET_PE[company] if pd.notna(annual_eps) else np.nan
    monthly_market_fair_value = _monthly_market_estimate(company)
    fair_value = monthly_market_fair_value if pd.notna(monthly_market_fair_value) else profit_pe_fair_value
    raw_price = _latest_raw_price(company); actual = raw_price["actual_stock_price"]
    return {
        "company": NAMES[company], "as_of_quarter": pd.Timestamp(latest["quarter"]).strftime("%Y-%m-%d"), **raw_price,
        "fair_value": fair_value, "deviation_pct": (fair_value / actual - 1) * 100 if pd.notna(fair_value) and actual else np.nan,
        "forecast_net_profit_bn": forecast, "annualised_net_profit_bn": annual_profit, "eps": annual_eps, "target_pe": TARGET_PE[company], "monthly_market_model_price": monthly_market_fair_value, "profit_pe_fair_value": profit_pe_fair_value,
        "demand_score": latest.get("demand_score", np.nan), "financial_source": latest.get("financial_source", "unknown"),
        "production_source": latest.get("production_source", "not_used"), "alumina_price_source": latest.get("alumina_price_source", "not_applicable"),
        "production_data_missing": pd.isna(latest.get("production_source", np.nan)) or "MISSING" in str(latest.get("production_source", "")),        "fallback_used": any("FALLBACK" in str(latest.get(col, "")) for col in ("financial_source", "production_source", "alumina_price_source")),
        "parse_confidence": latest.get("parse_confidence", np.nan), "model_status": status,
        "al_price": latest.get("al_price", np.nan), "alumina_price": latest.get("alumina_price", np.nan), "al_spread": latest.get("al_spread", np.nan),
        "cu_price": latest.get("cu_price", np.nan), "au_price_rmb_g": latest.get("au_price_rmb_g", np.nan), "cu_au_revenue_index": latest.get("cu_au_revenue_index", np.nan),
        "cu_ton": latest.get("cu_ton", np.nan), "au_kg": latest.get("au_kg", np.nan),
    }


def _markdown(signals: pd.DataFrame) -> str:
    lines = ["# Latest metal-stock valuation signal", "", "季度利润预测与动态估值；仅用于研究，不构成投资建议。", ""]
    for row in signals.to_dict("records"):
        lines += [f"## {row['company']}", ""]
        if row.get("status") == "missing_features": lines += ["WARNING: 缺少季度特征数据。", ""]; continue
        labels = [("实际股价", "actual_stock_price"), ("模型合理价（月度市场模型）", "fair_value"), ("PE 估值参考价", "profit_pe_fair_value"), ("偏离幅度", "deviation_pct"), ("预测季度归母净利润（亿元）", "forecast_net_profit_bn"), ("年化归母净利润（亿元）", "annualised_net_profit_bn"), ("EPS", "eps"), ("目标 PE", "target_pe"), ("需求得分", "demand_score")]
        if "中国铝业" in row["company"]: labels += [("沪铝价格", "al_price"), ("氧化铝价格", "alumina_price"), ("铝价差", "al_spread"), ("氧化铝价格来源", "alumina_price_source")]
        else: labels += [("铜价", "cu_price"), ("金价（元/克）", "au_price_rmb_g"), ("铜金收入指数", "cu_au_revenue_index"), ("矿产铜（吨）", "cu_ton"), ("矿产金（千克）", "au_kg"), ("产量数据来源", "production_source")]
        lines += [f"- {label}: {row.get(key, '')}" for label, key in labels]
        lines += [f"- 股票价格来源: {row.get('stock_price_provider')}", f"- 股票价格 adjust: {row.get('stock_price_adjust')}", f"- 最新交易日期: {row.get('latest_trade_date')}", f"- cache age（天）: {row.get('stock_cache_age_days')}"]
        lines += [f"- 财务数据来源: {row.get('financial_source')}", f"- 是否使用 fallback: {row.get('fallback_used')}", f"- 产量数据是否缺失: {row.get('production_data_missing')}"]
        if row.get("production_data_missing"): lines += ["- WARNING: production_data_missing=True；紫金模型已退化为价格与需求因子。"]
        if "MISSING_AO" in str(row.get("alumina_price_source", "")): lines += ["- WARNING: AO futures unavailable before 2023-06-19; use SMM API or fallback."]
        if pd.notna(row.get("parse_confidence")) and float(row["parse_confidence"]) < .7: lines += ["- WARNING: PDF 解析低置信度，不建议实盘使用。"]
        lines += [""]
    return "\n".join(lines)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s"); ensure_layout()
    signals = pd.DataFrame([_signal("chalco"), _signal("zijin")])
    signals.to_csv(REPORTS / "latest_signal.csv", index=False, encoding="utf-8-sig")
    signals[signals.company.str.contains("中国铝业")].to_csv(REPORTS / "chalco_valuation_signal_summary.csv", index=False, encoding="utf-8-sig")
    signals[signals.company.str.contains("紫金矿业")].to_csv(REPORTS / "zijin_valuation_signal_summary.csv", index=False, encoding="utf-8-sig")
    (REPORTS / "latest_signal.md").write_text(_markdown(signals), encoding="utf-8")


if __name__ == "__main__":
    main()









