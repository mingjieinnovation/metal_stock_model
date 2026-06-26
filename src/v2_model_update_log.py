"""Append-only, human-readable audit log for automated V2 jobs."""
from __future__ import annotations

import os

import pandas as pd

from .runtime import CACHE, REPORTS
from .v2_production_common import now_utc, repair_frame, write_markdown


def _read_csv(path):
    if not path.exists() or path.stat().st_size == 0:
        return pd.DataFrame()
    try:
        return pd.read_csv(path, encoding="utf-8-sig")
    except pd.errors.EmptyDataError:
        return pd.DataFrame()


def main() -> None:
    status = _read_csv(CACHE / "api_status.csv")
    if status.empty:
        status = pd.DataFrame(columns=["success", "source", "dataset"])

    latest = status.groupby("dataset", as_index=False).tail(1) if not status.empty else status
    decision = repair_frame(_read_csv(REPORTS / "v2_latest_decision_table.csv"))

    if not decision.empty and "company" in decision.columns:
        c = decision[decision.company.eq("中国铝业")].iloc[0] if decision.company.eq("中国铝业").any() else {}
        z = decision[decision.company.eq("紫金矿业")].iloc[0] if decision.company.eq("紫金矿业").any() else {}
    else:
        c = {}
        z = {}

    success = latest.get("success", pd.Series(dtype=bool)).fillna(False)
    source = latest.get("source", pd.Series(dtype=str)).astype(str)

    row = {
        "run_date": now_utc(),
        "run_type": os.getenv("V2_RUN_TYPE", "manual"),
        "updated_data": "市场/宏观/报告按本次任务状态更新",
        "api_success_count": int(success.sum()),
        "api_failed_count": int((~success).sum()),
        "cache_used_count": int(source.str.contains("CACHE").sum()),
        "fallback_used_count": int(source.str.contains("FALLBACK").sum()),
        "default_proxy_count": int(decision.get("proxy_ratio", pd.Series(dtype=float)).fillna(0).mul(7).sum())
        if not decision.empty
        else 0,
        "blocked_count": int(source.str.contains("BLOCKED").sum()),
        "models_retrained": False,
        "zijin_signal": z.get("signal_status", "unavailable"),
        "chalco_price_zone": c.get("price_zone", "unavailable"),
        "chalco_signal_status": c.get("signal_status", "unavailable"),
        "notes": "日常生产任务不重训；API 失败状态保留并显式记录。",
    }

    path = REPORTS / "v2_model_update_log.csv"
    old = repair_frame(_read_csv(path))
    if old.empty:
        old = pd.DataFrame(columns=row.keys())
    out = repair_frame(pd.concat([old, pd.DataFrame([row])], ignore_index=True).tail(500))
    out.to_csv(path, index=False, encoding="utf-8-sig")

    write_markdown(
        REPORTS / "v2_model_update_log.md",
        "V2 模型更新日志",
        "每次更新追加一行。`models_retrained=False` 表示仅刷新数据、报告和审计状态。",
        out.tail(30),
    )


if __name__ == "__main__":
    main()
