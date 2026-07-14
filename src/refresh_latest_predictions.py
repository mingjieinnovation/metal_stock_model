"""Refresh latest V2 prediction files from current visible market/fundamental data.

This module is intentionally explicit: it refreshes latest valuation predictions using
existing V2 model logic, but it does not promote daily alerts into tradable signals.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from .runtime import PROCESSED, REPORTS, ensure_layout, read_parquet_or_empty
from .v2_data_layer import build as build_market_layers
from .repair_zijin_quarterly_production import main as repair_zijin_production
from .convert_zijin_cumulative_production import main as convert_zijin_production
from .v2_chalco_profit_v22 import run as run_chalco_v22
from .v2_chalco_profit_v23 import run as run_chalco_v23
from .v2_zijin_profit_v21 import run as run_zijin_v21
from .update_daily_market import _alert as rewrite_daily_alert
from .v2_production_common import write_markdown


def _latest_summary(path: Path, fields: list[str]) -> dict[str, Any]:
    frame = read_parquet_or_empty(path)
    if frame.empty:
        return {"path": str(path), "rows": 0, **{field: pd.NA for field in fields}}
    row = frame.iloc[-1]
    out: dict[str, Any] = {"path": str(path), "rows": len(frame)}
    for field in fields:
        out[field] = row.get(field, pd.NA)
    return out


def run() -> dict[str, Any]:
    ensure_layout()
    # Keep strict Zijin production materialized before rebuilding the V2 data layer.
    # These are local parsers/converters over already downloaded filings; they do
    # not use annual equal splits, forward-fill, or zero-fill.
    repair_zijin_production()
    convert_zijin_production()

    market_counts = build_market_layers(("daily", "weekly", "monthly"))

    # V2.3 scenario prices depend on V2.2 blended-quarter profit output, so V2.2
    # is refreshed first. These calls reuse the existing model definitions and
    # announcement-safe visibility rules; they are not a PE uplift or signal promotion.
    chalco_v22 = run_chalco_v22()
    chalco_v23 = run_chalco_v23()
    zijin_v21 = run_zijin_v21()

    # Daily alert reads the latest prediction files, so rewrite it after refresh.
    rewrite_daily_alert()

    rows = [
        {
            "company": "中国铝业",
            "model": "v2_chalco_profit_v23",
            **_latest_summary(
                PROCESSED / "v2_chalco_profit_v23_predictions.parquet",
                ["date", "bear_price", "base_price", "bull_price", "model_price", "signal_status", "data_quality_flag"],
            ),
        },
        {
            "company": "紫金矿业",
            "model": "v2_zijin_profit_v21",
            **_latest_summary(
                PROCESSED / "v2_zijin_profit_v21_predictions.parquet",
                ["date", "model_price", "gap", "signal_status", "data_quality_flag"],
            ),
        },
    ]
    audit = pd.DataFrame(rows)
    audit["refreshed_at_utc"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    audit["refresh_scope"] = "latest_prediction_refresh_no_signal_promotion"
    audit.to_csv(REPORTS / "v2_latest_prediction_refresh_audit.csv", index=False, encoding="utf-8-sig")
    write_markdown(
        REPORTS / "v2_latest_prediction_refresh_audit.md",
        "V2 latest prediction refresh audit",
        "This refresh updates latest prediction files using existing V2 model logic and current visible data. Daily outputs remain gap alerts only; this step does not promote any result to a tradable signal.",
        audit,
    )

    return {
        "market_counts": market_counts,
        "chalco_v22": chalco_v22,
        "chalco_v23": chalco_v23,
        "zijin_v21": zijin_v21,
        "audit_rows": len(audit),
    }


def main() -> None:
    print(run())


if __name__ == "__main__":
    main()
