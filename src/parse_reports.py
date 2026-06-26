from __future__ import annotations

import logging
import re
from pathlib import Path

import pandas as pd

from .runtime import FALLBACK, PROCESSED, RAW, ensure_layout, read_parquet_or_empty, save_parquet, write_status

COLUMNS = ["quarter", "code", "cu_ton", "au_kg", "alumina_output_ton", "primary_al_output_ton", "source_pdf", "parse_confidence", "parse_warning", "source"]


def extract_text_from_pdf(pdf_path: str) -> str:
    """Extract embedded PDF text with pdfplumber first and pypdf as a portable fallback."""
    errors = []
    try:
        import pdfplumber
        with pdfplumber.open(pdf_path) as pdf:
            text = "\n".join((page.extract_text() or "") for page in pdf.pages)
        if text.strip():
            return text
    except Exception as exc:
        errors.append(f"pdfplumber:{exc}")
    try:
        from pypdf import PdfReader
        text = "\n".join((page.extract_text() or "") for page in PdfReader(pdf_path).pages)
        if text.strip():
            return text
    except Exception as exc:
        errors.append(f"pypdf:{exc}")
    raise RuntimeError("PDF text extraction failed: " + " | ".join(errors))
def _unit_value(text: str, phrases: tuple[str, ...], target: str) -> float | None:
    for phrase in phrases:
        match = re.search(rf"{phrase}.{{0,80}}?([0-9][0-9,，.]*)\s*(万吨|万 吨|吨|千克|公斤|克|盎司)", text, re.IGNORECASE | re.DOTALL)
        if not match:
            continue
        value = float(match.group(1).replace(",", "").replace("，", "")); unit = match.group(2).replace(" ", "")
        if target == "ton":
            return value * 10000 if unit == "万吨" else value
        if target == "kg":
            if unit == "千克" or unit == "公斤": return value
            if unit == "克": return value / 1000
            if unit == "盎司": return value * 0.0311035
    return None


def parse_zijin_production(text: str) -> dict:
    values = {"cu_ton": _unit_value(text, ("矿产铜", "产铜"), "ton"), "au_kg": _unit_value(text, ("矿产金", "产金"), "kg")}
    values["parse_confidence"] = sum(value is not None for value in values.values()) / 2
    values["parse_warning"] = "" if values["parse_confidence"] >= 0.7 else "low confidence or missing mining production"
    return values


def parse_chalco_production(text: str) -> dict:
    values = {"alumina_output_ton": _unit_value(text, ("氧化铝产量", "氧化铝产"), "ton"), "primary_al_output_ton": _unit_value(text, ("原铝产量", "电解铝产量", "原铝产"), "ton")}
    values["parse_confidence"] = sum(value is not None for value in values.values()) / 2
    values["parse_warning"] = "" if values["parse_confidence"] >= 0.7 else "low confidence or missing aluminium production"
    return values


def build_production_quarterly_from_reports() -> pd.DataFrame:
    index = read_parquet_or_empty(PROCESSED / "announcement_index.parquet")
    rows = []
    for item in index.itertuples(index=False):
        if getattr(item, "download_status", "") not in ("downloaded", "cached"):
            continue
        year, number = getattr(item, "report_year", None), getattr(item, "report_quarter", None)
        if pd.isna(year) or pd.isna(number):
            continue
        quarter = pd.Timestamp(year=int(year), month=int(number) * 3, day=1) + pd.offsets.MonthEnd(0)
        pdf = RAW / str(item.local_pdf_path)
        try:
            code = str(item.code).zfill(6)
            parsed = parse_zijin_production(extract_text_from_pdf(str(pdf))) if code == "601899" else parse_chalco_production(extract_text_from_pdf(str(pdf)))
            rows.append({"quarter": quarter, "code": code, "cu_ton": pd.NA, "au_kg": pd.NA, "alumina_output_ton": pd.NA, "primary_al_output_ton": pd.NA, "source_pdf": str(item.local_pdf_path), "source": "API_CNINFO_PDF", **parsed})
        except Exception as exc:
            logging.warning("Could not parse %s: %s", pdf, exc)
    return pd.DataFrame(rows).reindex(columns=COLUMNS) if rows else pd.DataFrame(columns=COLUMNS)
def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    ensure_layout(); parsed = build_production_quarterly_from_reports()
    source = "API_CNINFO_PDF"
    if parsed.empty:
        fallback = FALLBACK / "production_quarterly.csv"
        if fallback.exists():
            parsed = pd.read_csv(fallback).reindex(columns=COLUMNS); source = "FALLBACK_CSV"
    save_parquet(parsed, PROCESSED / "production_quarterly.parquet")
    write_status("production_quarterly", source, not parsed.empty, f"{len(parsed)} parsed rows")


if __name__ == "__main__":
    main()





def normalize_unit(value: float, unit: str, metal: str) -> float:
    unit = str(unit).replace(" ", "")
    if metal in ("cu", "alumina", "primary_al"):
        return value * 10000 if unit == "\u4e07\u5428" else value
    if metal == "au":
        if unit in ("\u5343\u514b", "\u516c\u65a4"): return value
        if unit == "\u5428": return value * 1000
        if unit == "\u76ce\u53f8": return value / 32.1507
    return value


def convert_cumulative_production_to_single_quarter(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty: return df
    out = df.copy(); out["quarter"] = pd.to_datetime(out["quarter"]); out = out.sort_values(["code", "quarter"])
    for field in ("cu_ton", "au_kg", "alumina_output_ton", "primary_al_output_ton"):
        if field in out:
            out[field] = pd.to_numeric(out[field], errors="coerce")
            out[field] = out.groupby(["code", out["quarter"].dt.year])[field].diff().fillna(out[field])
    return out



