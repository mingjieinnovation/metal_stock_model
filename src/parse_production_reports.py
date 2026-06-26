from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

from .runtime import PROCESSED, RAW, REPORTS, ensure_layout, read_parquet_or_empty, save_parquet

CODE = "601899"
ANCHORS = {
    "2023Q4": (1_010_000.0, 67_500.0),
    "2024Q4": (1_070_000.0, 72_938.0),
    "2025Q4": (1_090_000.0, 89_577.0),
    "2026Q1": (260_000.0, 23_500.0),
}
TARGET_PERIODS = [f"{year}Q{q}" for year in range(2023, 2027) for q in range(1, 5) if not (year == 2026 and q > 1)]
OUT_COLUMNS = ["quarter", "code", "cu_ton", "au_kg", "source_pdf", "source_title", "source_type", "source_period", "is_cumulative", "parse_confidence", "parse_warning", "data_quality_flag", "strict_usable", "proxy_usable", "source"]
AUDIT_COLUMNS = ["code", "period", "source_pdf", "source_title", "extracted_cu_raw", "extracted_cu_unit", "cu_ton", "extracted_au_raw", "extracted_au_unit", "au_kg", "anchor_cu_ton", "anchor_au_kg", "cu_anchor_diff_pct", "au_anchor_diff_pct", "parse_confidence", "strict_usable", "proxy_usable", "parse_warning"]


def extract_text(pdf: Path) -> str:
    errors = []
    try:
        import pdfplumber
        with pdfplumber.open(str(pdf)) as doc:
            text = "\n".join(page.extract_text() or "" for page in doc.pages)
        if text.strip(): return text
    except Exception as exc: errors.append(f"pdfplumber:{exc}")
    try:
        from pypdf import PdfReader
        text = "\n".join(page.extract_text() or "" for page in PdfReader(str(pdf)).pages)
        if text.strip(): return text
    except Exception as exc: errors.append(f"pypdf:{exc}")
    raise RuntimeError(" | ".join(errors))


def _convert(value: float, unit: str, metal: str) -> float:
    unit = unit.replace(" ", "")
    if metal == "cu": return value * 10000 if unit == "万吨" else value
    if unit == "吨": return value * 1000
    if unit in ("千克", "公斤"): return value
    if unit == "盎司": return value / 32.1507
    return value


def _candidates(text: str, metal: str) -> list[tuple[float, str, float]]:
    keywords = (r"矿产铜|矿山产铜|产铜", r"矿产金|矿山产金|产金")[metal == "au"]
    units = r"万吨|吨" if metal == "cu" else r"吨|千克|公斤|盎司"
    pattern = re.compile(rf"(?:{keywords})[^0-9]{{0,35}}([0-9][0-9,，.]*)\s*({units})", re.S)
    output = []
    for raw, unit in pattern.findall(text):
        value = float(raw.replace(",", "").replace("，", "")); output.append((value, unit, _convert(value, unit, metal)))
    return output


def _select(candidates: list[tuple[float, str, float]], anchor: float | None) -> tuple[float | None, str | None, float | None]:
    if not candidates: return None, None, None
    if anchor:
        raw, unit, converted = min(candidates, key=lambda x: abs(x[2] - anchor) / anchor)
    else: raw, unit, converted = candidates[0]
    return raw, unit, converted


def _diff(value: float | None, anchor: float | None) -> float | None:
    return abs(value - anchor) / anchor if value is not None and anchor else None


def parse_anchor_reports() -> tuple[pd.DataFrame, pd.DataFrame]:
    index = read_parquet_or_empty(PROCESSED / "announcement_index.parquet")
    index["code"] = index.get("code", pd.Series(dtype=str)).astype(str).str.zfill(6)
    index = index[(index.code == CODE) & index.download_status.eq("downloaded")].copy()
    rows, audits = [], []
    for period in TARGET_PERIODS:
        anchor_cu, anchor_au = ANCHORS.get(period, (None, None))
        year, quarter = int(period[:4]), int(period[-1])
        choices = index[(index.report_year.astype(int) == year) & (index.report_quarter.astype(int) == quarter)]
        if choices.empty:
            audits.append({"code": CODE, "period": period, "anchor_cu_ton": anchor_cu, "anchor_au_kg": anchor_au, "parse_warning": "SOURCE_PDF_MISSING"}); continue
        item = choices.sort_values("announcement_time").iloc[-1]; pdf = RAW / str(item.local_pdf_path)
        try:
            text = extract_text(pdf)
            cu_raw, cu_unit, cu = _select(_candidates(text, "cu"), anchor_cu)
            au_raw, au_unit, au = _select(_candidates(text, "au"), anchor_au)
            cu_diff, au_diff = _diff(cu, anchor_cu), _diff(au, anchor_au)
            confidence = 0.0 + .35 * (cu is not None) + .35 * (au is not None)
            warnings = []
            if cu_diff is not None and cu_diff < .03: confidence += .1
            elif cu_diff is not None and cu_diff <= .10: warnings.append("ANCHOR_DEVIATION_WARNING_CU")
            elif cu_diff is not None: warnings.append("LOW_CONFIDENCE_ANCHOR_MISMATCH_CU")
            if au_diff is not None and au_diff < .03: confidence += .1
            elif au_diff is not None and au_diff <= .10: warnings.append("ANCHOR_DEVIATION_WARNING_AU")
            elif au_diff is not None: warnings.append("LOW_CONFIDENCE_ANCHOR_MISMATCH_AU")
            annual = quarter in (2, 3, 4)
            strict = (not annual) and confidence >= .7 and not any("LOW_CONFIDENCE" in w for w in warnings)
            warning = ";".join(warnings + (["CUMULATIVE_DATA_NEEDS_QUARTER_CONVERSION"] if annual else []))
            audit = {"code": CODE, "period": period, "source_pdf": str(item.local_pdf_path), "source_title": item.title, "extracted_cu_raw": cu_raw, "extracted_cu_unit": cu_unit, "cu_ton": cu, "extracted_au_raw": au_raw, "extracted_au_unit": au_unit, "au_kg": au, "anchor_cu_ton": anchor_cu, "anchor_au_kg": anchor_au, "cu_anchor_diff_pct": cu_diff, "au_anchor_diff_pct": au_diff, "parse_confidence": confidence, "strict_usable": strict, "proxy_usable": False, "parse_warning": warning}
            audits.append(audit)
            rows.append({"quarter": pd.Timestamp(year=year, month=quarter * 3, day=1) + pd.offsets.MonthEnd(0), "code": CODE, "cu_ton": cu, "au_kg": au, "source_pdf": str(item.local_pdf_path), "source_title": item.title, "source_type": "CNINFO_PDF", "source_period": period, "is_cumulative": annual, "parse_confidence": confidence, "parse_warning": warning, "data_quality_flag": "" if strict else "NOT_STRICT_USABLE", "strict_usable": strict, "proxy_usable": False, "source": "API_CNINFO_PDF"})
        except Exception as exc:
            audits.append({"code": CODE, "period": period, "source_pdf": str(item.local_pdf_path), "source_title": item.title, "anchor_cu_ton": anchor_cu, "anchor_au_kg": anchor_au, "parse_warning": f"EXTRACTION_FAILED:{exc}"})
    return pd.DataFrame(rows).reindex(columns=OUT_COLUMNS), pd.DataFrame(audits).reindex(columns=AUDIT_COLUMNS)



def derive_q4_from_cumulative(frame: pd.DataFrame) -> pd.DataFrame:
    derived = []
    for year in frame["quarter"].dt.year.dropna().unique():
        annual = frame[(frame.quarter.dt.year == year) & (frame.quarter.dt.quarter == 4) & frame.is_cumulative]
        q3 = frame[(frame.quarter.dt.year == year) & (frame.quarter.dt.quarter == 3) & frame.is_cumulative]
        if annual.empty or q3.empty: continue
        annual_row, q3_row = annual.iloc[-1], q3.iloc[-1]
        if pd.isna(annual_row.cu_ton) or pd.isna(q3_row.cu_ton) or pd.isna(annual_row.au_kg) or pd.isna(q3_row.au_kg): continue
        confidence = min(float(annual_row.parse_confidence), float(q3_row.parse_confidence))
        strict = confidence >= .7
        derived.append({"quarter": pd.Timestamp(year=int(year), month=12, day=31), "code": CODE, "cu_ton": annual_row.cu_ton - q3_row.cu_ton, "au_kg": annual_row.au_kg - q3_row.au_kg, "source_pdf": f"{annual_row.source_pdf} | {q3_row.source_pdf}", "source_title": "FY minus Q1-Q3 cumulative", "source_type": "DERIVED_FROM_CNINFO_CUMULATIVE", "source_period": f"{year}Q4_DERIVED_SINGLE", "is_cumulative": False, "parse_confidence": confidence, "parse_warning": "DERIVED_Q4_FROM_FY_MINUS_Q1_Q3", "data_quality_flag": "DERIVED_FROM_CUMULATIVE", "strict_usable": strict, "proxy_usable": False, "source": "API_CNINFO_PDF"})
    return pd.DataFrame(derived).reindex(columns=OUT_COLUMNS)
def main() -> None:
    ensure_layout(); production, audit = parse_anchor_reports(); save_parquet(production, PROCESSED / "production_quarterly.parquet")
    audit.to_csv(REPORTS / "production_parse_audit.csv", index=False, encoding="utf-8-sig")
    lines = ["# Production parse audit", "", f"Parsed records: {len(production)}", f"Strict-usable records: {int(production.strict_usable.sum()) if not production.empty else 0}", ""]
    for row in audit.itertuples(index=False): lines.append(f"- {row.period}: cu={row.cu_ton}, au={row.au_kg}, confidence={row.parse_confidence}, warning={row.parse_warning}")
    if production.empty: lines += ["", "V2 strict still blocked: no production values extracted."]
    elif production.strict_usable.sum() < 4: lines += ["", "V2 strict still blocked: only annual production data or fewer than four strict quarterly records are available.", "V2 proxy can be built only after user confirms annual-to-quarter allocation rule."]
    (REPORTS / "production_parse_audit.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()





