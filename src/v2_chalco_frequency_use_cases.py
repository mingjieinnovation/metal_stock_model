"""Classify Chalco V2.2 outputs by valuation, trading observation and gap alert use."""
from __future__ import annotations

import numpy as np
import pandas as pd

from .runtime import PROCESSED, REPORTS, read_parquet_or_empty

ROOT = REPORTS / "frequency_backtest_v2"
OUT = REPORTS / "v2_chalco_frequency_use_case_summary.md"
CSV = REPORTS / "v2_chalco_frequency_use_case_summary.csv"


def _components(freq: str) -> pd.DataFrame:
    data = pd.read_csv(ROOT / freq / "walk_forward_strict" / "chalco_components.csv")
    data = data[data["strict_status"].eq("strict")].copy()
    data["trade_date"] = pd.to_datetime(data["trade_date"])
    data["raw_signal"] = data["raw_signal"].fillna(data["signal"])
    return data.sort_values("trade_date").reset_index(drop=True)


def _forward(frame: pd.DataFrame, horizons: tuple[int, ...], unit: str) -> pd.DataFrame:
    frame = frame.copy()
    for h in horizons:
        frame[f"fwd_{h}{unit}_return"] = frame["actual_stock_close_raw"].shift(-h) / frame["actual_stock_close_raw"] - 1
    return frame


def _change_rate(frame: pd.DataFrame) -> float:
    return float(frame["raw_signal"].ne(frame["raw_signal"].shift()).iloc[1:].mean()) if len(frame) > 1 else np.nan


def _hit(signal: pd.Series, returns: pd.Series) -> pd.Series:
    return np.where(signal.eq("undervalued"), returns.gt(0), np.where(signal.eq("overvalued"), returns.lt(0), returns.abs().le(.12)))


def run() -> dict[str, object]:
    daily = _forward(_components("daily"), (1, 5, 20), "d")
    weekly = _forward(_components("weekly"), (4, 13, 26), "w")
    monthly = _forward(_components("monthly"), (1, 3, 6), "m")
    # Month-end receives the most recent completed weekly observation only.
    aligned = pd.merge_asof(monthly.sort_values("trade_date"), weekly[["trade_date", "raw_signal", "model_price", "actual_stock_close_raw", "fwd_4w_return", "fwd_13w_return", "fwd_26w_return"]].sort_values("trade_date"), on="trade_date", direction="backward", suffixes=("_monthly", "_weekly"))
    aligned["same_direction"] = aligned["raw_signal_monthly"].eq(aligned["raw_signal_weekly"])
    aligned["stronger_signal"] = np.where(aligned["same_direction"], "research_only_stronger_signal", "not_aligned")
    same = aligned[aligned["same_direction"]].copy()
    rows = []
    for use_case, frame, freq, horizons, unit in [
        ("daily_v22_gap_alert", daily, "daily", (1, 5, 20), "d"),
        ("weekly_v22_trading_observation", weekly, "weekly", (4, 13, 26), "w"),
        ("monthly_v22_valuation_anchor", monthly, "monthly", (1, 3, 6), "m"),
    ]:
        row = {"use_case": use_case, "frequency": freq, "usable_rows": len(frame), "signal_change_rate": _change_rate(frame), "latest_date": frame.iloc[-1]["trade_date"], "latest_raw_signal": frame.iloc[-1]["raw_signal"], "latest_gap": frame.iloc[-1]["gap"], "latest_model_price": frame.iloc[-1]["model_price"], "signal_status": frame.iloc[-1]["signal_status"]}
        for h in horizons:
            values = frame[f"fwd_{h}{unit}_return"].dropna(); row[f"avg_fwd_{h}{unit}_return"] = values.mean(); row[f"n_fwd_{h}{unit}"] = len(values)
        rows.append(row)
    for h in (4, 13, 26):
        values = same[f"fwd_{h}w_return"].dropna(); hits = _hit(same.loc[values.index, "raw_signal_monthly"], values)
        rows.append({"use_case": "weekly_monthly_same_direction", "frequency": "weekly+monthly", "usable_rows": len(same), "signal_change_rate": np.nan, "latest_date": same.iloc[-1]["trade_date"] if len(same) else pd.NaT, "latest_raw_signal": same.iloc[-1]["raw_signal_monthly"] if len(same) else pd.NA, "latest_gap": np.nan, "latest_model_price": np.nan, "signal_status": "research_only_stronger_signal", f"avg_fwd_{h}w_return": values.mean(), f"n_fwd_{h}w": len(values), f"hit_fwd_{h}w": hits.mean() if len(values) else np.nan})
    summary = pd.DataFrame(rows); summary.to_csv(CSV, index=False, encoding="utf-8-sig")
    v22 = read_parquet_or_empty(PROCESSED / "v2_chalco_profit_v22_predictions.parquet")
    anchor = v22.iloc[-1] if len(v22) else pd.Series(dtype=object)
    weekly_change, daily_change, monthly_change = _change_rate(weekly), _change_rate(daily), _change_rate(monthly)
    text = "# China Aluminum V2.2 frequency use-case summary\n\n"
    text += "## 1. monthly_v22_valuation_anchor\n\n"
    text += f"- Use: valuation center and holding judgement only. Latest V2.2 TTM model price: {anchor.get('model_price', np.nan):.2f}; gap: {anchor.get('gap', np.nan):.1%}; status: `{anchor.get('signal_status', 'missing')}`.\n"
    text += f"- Monthly raw-signal change rate: {monthly_change:.1%}. Forward-return fields are 1M/3M/6M and are descriptive only.\n"
    text += "- Conclusion: monthly is the preferred valuation anchor because its TTM profit target matches the holding/valuation horizon; it is not a stand-alone tradable signal while TTM OOS validation remains below target.\n\n"
    text += "## 2. weekly_v22_trading_observation\n\n"
    text += f"- Use: trading observation, using 4W/13W/26W forward-return analysis. Weekly raw-signal change rate: {weekly_change:.1%}.\n"
    text += "- Rule: a `stronger_signal` is eligible only when weekly and monthly raw signals are aligned. It remains `research_only_stronger_signal` until the monthly valuation anchor has sufficient OOS confirmation.\n"
    for h in (4,13,26):
        values = same[f"fwd_{h}w_return"].dropna(); hits = _hit(same.loc[values.index, "raw_signal_monthly"], values)
        text += f"- Same-direction weekly/monthly: {len(values)} available {h}W outcomes; average return {values.mean():.2%}; directional hit rate {hits.mean():.1%}.\n"
    text += "\n## 3. daily_v22_gap_alert\n\n"
    text += f"- Use: short-term gap alert only. Daily raw-signal change rate: {daily_change:.1%}, versus weekly {weekly_change:.1%}.\n"
    text += "- Daily output may flag rapid price/model divergence, but it cannot independently create `tradable_signal`. Higher row count does not create more independent quarterly-profit evidence.\n\n"
    text += "## Decision hierarchy\n\n"
    text += "- If daily and monthly conflict: use monthly for valuation judgement, weekly for trading observation, and daily only for alerts.\n"
    text += "- If weekly and monthly align: label the observation `research_only_stronger_signal`; do not treat it as tradable before V2.2 TTM walk-forward validation improves.\n"
    text += f"- Stability comparison: weekly is {'more' if weekly_change < daily_change else 'not more'} stable than daily by raw-signal change rate ({weekly_change:.1%} vs {daily_change:.1%}).\n"
    text += "- No PE uplift, future financial data, future announcement dates, or volume proxy disguised as strict data are used in this framework.\n"
    text += "\n## Scope boundary and stability interpretation\n\n"
    text += "- The V2.2 TTM model is the monthly valuation anchor. Weekly and daily rows use announcement-safe V2.1-C raw-gap observations assigned to V2.2 operational use cases; they are not separately validated high-frequency TTM models.\n"
    text += f"- Weekly is {'more' if weekly_change < daily_change else 'not more'} stable than daily by raw-signal change rate in this sample: {weekly_change:.1%} versus {daily_change:.1%}.\n"
    text += "- Daily gap alerts cannot be promoted to a tradable signal: daily rows do not add independent quarterly-profit evidence, regardless of the number of observations.\n"
    OUT.write_text(text, encoding="utf-8")
    return {"daily_change_rate": daily_change, "weekly_change_rate": weekly_change, "monthly_change_rate": monthly_change, "same_direction_rows": len(same)}


def main() -> None: print(run())
if __name__ == "__main__": main()
