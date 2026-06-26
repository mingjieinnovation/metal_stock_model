from __future__ import annotations

from datetime import datetime, timedelta

import pandas as pd

from .runtime import CACHE, PROCESSED, RAW, REPORTS, ensure_layout, read_parquet_or_empty


def check_missing_rate(df: pd.DataFrame) -> float:
    return float(df.isna().mean().mean()) if not df.empty else 1.0


def check_stale_data(df: pd.DataFrame, date_col: str, max_days: int = 120) -> bool:
    if df.empty or date_col not in df: return True
    latest = pd.to_datetime(df[date_col], errors="coerce").max()
    return pd.isna(latest) or (pd.Timestamp.now().normalize() - latest.normalize()).days > max_days


def check_parse_confidence(df: pd.DataFrame) -> float:
    if df.empty or "parse_confidence" not in df: return 0.0
    return float(pd.to_numeric(df["parse_confidence"], errors="coerce").mean())


def make_data_quality_report() -> pd.DataFrame:
    rows = []
    for path, date_col in ((PROCESSED / "financial_quarterly.parquet", "quarter"), (PROCESSED / "production_quarterly.parquet", "quarter"), (PROCESSED / "chalco_quarterly_features.parquet", "quarter"), (PROCESSED / "zijin_quarterly_features.parquet", "quarter")):
        data = read_parquet_or_empty(path)
        rows.append({"dataset": path.stem, "rows": len(data), "missing_rate": check_missing_rate(data), "stale": check_stale_data(data, date_col), "mean_parse_confidence": check_parse_confidence(data), "warning": "missing or stale" if data.empty or check_stale_data(data, date_col) else ""})
    status = pd.read_csv(CACHE / "api_status.csv") if (CACHE / "api_status.csv").exists() else pd.DataFrame()
    if not status.empty:
        for dataset, item in status.groupby("dataset").tail(1).set_index("dataset").iterrows():
            rows.append({"dataset": f"api:{dataset}", "rows": pd.NA, "missing_rate": pd.NA, "stale": not bool(item.success), "mean_parse_confidence": pd.NA, "warning": item.detail, "source": item.source})
    return pd.DataFrame(rows)


def main() -> None:
    ensure_layout(); report = make_data_quality_report(); report.to_csv(REPORTS / "data_quality_report.csv", index=False, encoding="utf-8-sig")
    lines = ["# Data quality report", "", "| Dataset | Rows | Missing rate | Stale | Parse confidence | Warning |", "|---|---:|---:|---|---:|---|"]
    for row in report.itertuples(index=False): lines.append(f"| {row.dataset} | {row.rows} | {row.missing_rate} | {row.stale} | {row.mean_parse_confidence} | {row.warning} |")
    (REPORTS / "data_quality_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")





def _extra_quality_rows() -> list[dict]:
    rows = []
    financial = read_parquet_or_empty(PROCESSED / "financial_quarterly.parquet")
    for field in ("revenue_cum", "net_profit_cum", "eps_cum", "announcement_date", "revenue_q", "net_profit_q", "eps_q"):
        rows.append({"dataset": f"financial:{field}", "rows": len(financial), "missing_rate": float(financial[field].isna().mean()) if field in financial and len(financial) else 1.0, "stale": False, "mean_parse_confidence": pd.NA, "warning": "financial field missing" if field not in financial or financial[field].isna().all() else ""})
    if not financial.empty:
        flag = financial.get("data_quality_flag", pd.Series(dtype=str)).astype(str).str.contains("NET_PROFIT_USED_AS_ATTRIBUTABLE").any()
        rows.append({"dataset": "financial:attributable_profit", "rows": len(financial), "missing_rate": 0.0, "stale": False, "mean_parse_confidence": pd.NA, "warning": "NET_PROFIT_USED_AS_ATTRIBUTABLE" if flag else ""})
    announcement = read_parquet_or_empty(PROCESSED / "announcement_index.parquet")
    rows.append({"dataset": "announcement_index", "rows": len(announcement), "missing_rate": check_missing_rate(announcement), "stale": announcement.empty, "mean_parse_confidence": pd.NA, "warning": "announcement index empty" if announcement.empty else ""})
    if not announcement.empty and "download_status" in announcement:
        rows.append({"dataset": "announcement:pdf_download", "rows": len(announcement), "missing_rate": float((announcement.download_status != "downloaded").mean()), "stale": False, "mean_parse_confidence": pd.NA, "warning": "some PDF downloads failed" if (announcement.download_status != "downloaded").any() else ""})
    for path, label, date_col in ((RAW / "china_pmi_monthly.parquet", "macro:PMI", "date"), (RAW / "hs300_daily.parquet", "macro:HS300", "date")):
        data = read_parquet_or_empty(path); rows.append({"dataset": label, "rows": len(data), "missing_rate": check_missing_rate(data), "stale": check_stale_data(data, date_col, 10), "mean_parse_confidence": pd.NA, "warning": "missing or older than 10 days" if data.empty or check_stale_data(data, date_col, 10) else ""})
    chalco = read_parquet_or_empty(PROCESSED / "chalco_quarterly_features.parquet")
    if not chalco.empty and "alumina_price_source" in chalco:
        missing = chalco.alumina_price_source.astype(str).str.contains("MISSING_AO").sum()
        rows.append({"dataset": "chalco:alumina_2020_2023", "rows": int(missing), "missing_rate": float(missing / len(chalco)), "stale": False, "mean_parse_confidence": pd.NA, "warning": "AO futures unavailable before 2023-06-19; use SMM API or fallback" if missing else ""})
    return rows


def main() -> None:
    ensure_layout(); report = pd.concat([make_data_quality_report(), pd.DataFrame(_extra_quality_rows())], ignore_index=True)
    report.to_csv(REPORTS / "data_quality_report.csv", index=False, encoding="utf-8-sig")
    lines = ["# Data quality report", "", "| Dataset | Rows | Missing rate | Stale | Parse confidence | Warning |", "|---|---:|---:|---|---:|---|"]
    for row in report.itertuples(index=False): lines.append(f"| {row.dataset} | {row.rows} | {row.missing_rate} | {row.stale} | {row.mean_parse_confidence} | {row.warning} |")
    (REPORTS / "data_quality_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()


