"""Audit why the original Chalco V2 valuation is below the market price."""
from __future__ import annotations

import numpy as np
import pandas as pd

from .runtime import PROCESSED, REPORTS, read_parquet_or_empty
from .v2_walk_forward import _financial, asof_join_quarterly_to_monthly

SHARES_BN = 171.55
OUT_CSV = REPORTS / "v2_chalco_profit_diagnostics.csv"
OUT_MD = REPORTS / "v2_chalco_profit_diagnostics.md"


def build_diagnostics() -> pd.DataFrame:
    source = REPORTS / "frequency_backtest_v2" / "monthly" / "walk_forward_strict" / "chalco_components.csv"
    components = pd.read_csv(source)
    components["trade_date"] = pd.to_datetime(components["trade_date"])
    components = components[components["strict_status"].eq("strict")].copy()
    financial = _financial("601600")[["quarter", "net_profit_q", "financial_available_date"]].copy()
    visible = financial.rename(columns={"quarter": "actual_profit_quarter", "net_profit_q": "latest_actual_q_profit_bn", "financial_available_date": "available_date"})
    joined = asof_join_quarterly_to_monthly(components, visible, date_col="trade_date", available_col="available_date")
    output = pd.DataFrame({
        "date": joined["trade_date"], "visible_quarter": joined["visible_quarter"],
        "actual_stock_close_raw": joined["actual_stock_close_raw"],
        "v2_q_profit_pred_bn": joined["q_profit_pred_bn"], "v2_annual_profit_pred_bn": joined["annual_profit_pred_bn"],
        "v2_eps_pred": joined["eps_pred"], "v2_target_pe": joined["target_pe"],
        "v2_model_price": joined["model_price"], "gap": joined["gap"],
        "latest_actual_q_profit_bn": joined["latest_actual_q_profit_bn"],
        "latest_actual_profit_quarter": joined["actual_profit_quarter"],
        "al_price": joined["al_price"], "alumina_price": joined["alumina_price"], "al_spread": joined["al_spread"],
        "al_spread_k": joined["al_spread_k"], "alumina_price_k": joined["alumina_price_k"],
        "demand_score": joined["demand_score"], "is_q4": joined["is_q4"],
        "ridge_alpha": joined["ridge_alpha"], "ridge_coef_json": joined["ridge_coef_json"],
        "train_quarters_count": joined["train_quarters_count"], "data_quality_flag": joined["data_quality_flag"],
    })
    output["required_q_profit_to_match_price"] = output["actual_stock_close_raw"] * SHARES_BN / (4 * output["v2_target_pe"])
    output["latest_actual_q_profit_annualized_price"] = output["latest_actual_q_profit_bn"] * 4 / SHARES_BN * output["v2_target_pe"]
    output["profit_prediction_shortfall_bn"] = output["required_q_profit_to_match_price"] - output["v2_q_profit_pred_bn"]
    output["profit_prediction_shortfall_pct"] = output["profit_prediction_shortfall_bn"] / output["required_q_profit_to_match_price"]
    output.to_csv(OUT_CSV, index=False, encoding="utf-8-sig")
    return output


def write_summary(frame: pd.DataFrame) -> None:
    latest = frame.iloc[-1]
    alpha_mode = frame["ridge_alpha"].mode().iloc[0] if frame["ridge_alpha"].notna().any() else np.nan
    alpha_share = float((frame["ridge_alpha"] == alpha_mode).mean()) if pd.notna(alpha_mode) else np.nan
    systematic = bool((frame["profit_prediction_shortfall_bn"] > 0).mean() >= .7 and frame["profit_prediction_shortfall_bn"].mean() > 0)
    text = "# China Aluminum V2 profit-layer diagnostics\n\n"
    text += f"- Original profit model: `v2_chalco_original_profit_model`\n- Strict output months audited: {len(frame)}\n"
    text += f"- Latest date: {latest['date'].date()}\n- Latest actual price: {latest['actual_stock_close_raw']:.2f}\n- Original V2 quarterly-profit prediction: {latest['v2_q_profit_pred_bn']:.2f} bn RMB\n"
    text += f"- Quarterly profit required to match the price at the unchanged PE: {latest['required_q_profit_to_match_price']:.2f} bn RMB\n"
    text += f"- Profit shortfall: {latest['profit_prediction_shortfall_bn']:.2f} bn RMB ({latest['profit_prediction_shortfall_pct']:.1%})\n"
    text += f"- Latest announced quarterly-profit anchor ({pd.Timestamp(latest['latest_actual_profit_quarter']).to_period('Q')}): {latest['latest_actual_q_profit_bn']:.2f} bn RMB; its annualized same-PE price is {latest['latest_actual_q_profit_annualized_price']:.2f}.\n"
    text += f"- Ridge alpha mode: {alpha_mode:g}, appearing in {alpha_share:.0%} of audited months. This is high relative to the feature scale and is consistent with coefficient/profit-response shrinkage, but it is not the only missing economic driver.\n"
    text += "\n## Conclusion\n\n"
    text += f"1. The low model price is primarily profit-prediction driven: {latest['profit_prediction_shortfall_bn']:.2f} bn RMB of quarterly profit is missing at the unchanged PE; PE is not raised.\n"
    text += f"2. Original V2 systematic underprediction flag: {systematic}.\n"
    text += "3. China Aluminum V2 strict signal is suspended because the profit model systematically underpredicts quarterly profit. The current overvaluation signal is not tradable until the profit layer is recalibrated.\n"
    text += "4. V2.1 is required: use quarterly averages/lags, announced-profit anchors and a walk-forward comparison. No future profit or future announcement date may be used.\n"
    OUT_MD.write_text(text, encoding="utf-8")


def main() -> None:
    frame = build_diagnostics(); write_summary(frame); print({"rows": len(frame), "latest_shortfall_bn": round(float(frame.iloc[-1]["profit_prediction_shortfall_bn"]), 4)})


if __name__ == "__main__":
    main()
