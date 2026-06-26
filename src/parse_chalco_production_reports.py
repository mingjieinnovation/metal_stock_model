"""Conservative parser for Chalco production PDFs; never annualises or fills missing values."""
from __future__ import annotations
import re
import pandas as pd
from .runtime import PROCESSED, RAW, REPORTS, ensure_layout, save_parquet
from .v2_production_common import write_markdown, repair_frame

CODE="601600"
FIELDS={"primary_al_output_ton":r"(?:原铝|电解铝)(?:产量|产出)?","primary_al_sales_ton":r"(?:原铝|电解铝)销量","alumina_output_ton":r"(?:氧化铝|自产冶金级氧化铝)(?:产量|产出)?","alumina_external_sales_ton":r"(?:氧化铝|自产冶金级氧化铝)(?:外销(?:量)?|销量)"}
OUT=["quarter","code",*FIELDS,"source_pdf","source_title","source_period","is_cumulative","strict_usable","parse_confidence","parse_warning","source_type","data_source","available_date","fetched_at","is_proxy","is_strict","data_quality_flag","stale_days"]

def _value(text, key):
    found=re.compile(FIELDS[key]+r"[^0-9]{0,40}([0-9][0-9,，.]*)\s*(万吨|吨)",re.S).findall(text)
    if not found:return None
    raw,unit=found[0];return float(raw.replace(",","").replace("，",""))*(10000 if unit=="万吨" else 1)

def _text_fast(pdf):
    """Bound PDF work for scheduled jobs; new reports are parsed first."""
    from pypdf import PdfReader
    reader=PdfReader(str(pdf)); parts=[]
    for page in reader.pages[:80]:
        parts.append(page.extract_text() or "")
        joined="\n".join(parts)
        if "氧化铝" in joined and ("原铝" in joined or "电解铝" in joined): break
    return "\n".join(parts)

def main() -> None:
    ensure_layout();rows=[];audit=[]
    for pdf in sorted((RAW/"reports"/CODE).glob("**/*.pdf"), reverse=True):
        match=re.search(r"(20\d{2}).*?Q([1-4])",pdf.name)
        if not match:continue
        year,quarter=int(match.group(1)),int(match.group(2))
        try:
            text=_text_fast(pdf);values={k:_value(text,k) for k in FIELDS};found=sum(v is not None for v in values.values());confidence=round(.2+.2*found,2);cumulative=quarter in (2,3,4)
            strict=not cumulative and confidence>=.7 and values["primary_al_output_ton"] is not None and values["alumina_output_ton"] is not None
            warning=("CUMULATIVE_DATA_NEEDS_COMPLETE_CONVERSION" if cumulative else "")+(";MISSING_REQUIRED_VOLUME" if not strict else "")
            row={"quarter":pd.Timestamp(year=year,month=quarter*3,day=1)+pd.offsets.MonthEnd(0),"code":CODE,**values,"source_pdf":str(pdf.relative_to(RAW)),"source_title":pdf.stem,"source_period":f"{year}Q{quarter}","is_cumulative":cumulative,"strict_usable":strict,"parse_confidence":confidence,"parse_warning":warning,"source_type":"PDF_STRICT" if strict else "PDF_LOW_CONFIDENCE","data_source":"CNINFO_OR_COMPANY_PDF","available_date":pd.NaT,"fetched_at":pd.Timestamp.utcnow(),"is_proxy":False,"is_strict":strict,"data_quality_flag":"" if strict else "NOT_STRICT_USABLE","stale_days":pd.NA};rows.append(row);audit.append({"period":row["source_period"],"source_pdf":row["source_pdf"],"parse_confidence":confidence,"strict_usable":strict,"parse_warning":warning,**values})
        except Exception as exc:audit.append({"period":f"{year}Q{quarter}","source_pdf":str(pdf.relative_to(RAW)),"parse_confidence":0,"strict_usable":False,"parse_warning":f"EXTRACTION_FAILED:{type(exc).__name__}"})
    out=pd.DataFrame(rows).reindex(columns=OUT);save_parquet(out,PROCESSED/"v2_chalco_strict_production.parquet");ad=repair_frame(pd.DataFrame(audit));ad.to_csv(REPORTS/"v2_chalco_production_parse_audit.csv",index=False,encoding="utf-8-sig")
    text="仅在单季、字段齐全且解析置信度不低于 0.7 时标记 strict。累计口径不会被直接当作单季，年度数据不会均分。"+("\n\n当前未解析到可审计中铝产量；Model J 保持 BLOCKED_MISSING_STRICT_VOLUME。" if out.empty else "")
    write_markdown(REPORTS/"v2_chalco_production_parse_audit.md","中铝产量 PDF 解析审计",text,ad)
if __name__=="__main__":main()


