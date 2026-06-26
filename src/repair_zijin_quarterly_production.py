from __future__ import annotations

import re
import pandas as pd
from pathlib import Path

from .parse_production_reports import CODE, OUT_COLUMNS, AUDIT_COLUMNS, ANCHORS, _convert, _diff, extract_text
from .runtime import PROCESSED, RAW, REPORTS, read_parquet_or_empty, save_parquet

ANCHOR_EXTRA = {"2023Q1": (249699.,15952.), "2023Q3": (754000.,50000.), "2024Q1": (262649.,16805.), "2024Q3": (None,None), "2025Q1": (None,None)}


def _values(text: str, label: str, metal: str):
    units = r"万吨|吨" if metal == "cu" else r"吨|千克|公斤|盎司"
    patterns = [rf"{label}\s+({units})\s+([0-9][0-9,，.]*)", rf"{label}[^0-9]{{0,30}}([0-9][0-9,，.]*)\s*({units})"]
    found=[]
    for i, pattern in enumerate(patterns):
        for pair in re.findall(pattern,text,re.S):
            unit, raw = pair if i == 0 else (pair[1],pair[0]); value=float(raw.replace(',','').replace('，','')); found.append((raw,unit,_convert(value,unit,metal)))
    return found


def _pick(values, anchor):
    if not values:return None,None,None
    return min(values,key=lambda x: abs(x[2]-anchor)/anchor) if anchor else values[0]


def main():
    index=read_parquet_or_empty(PROCESSED/'announcement_index.parquet'); index['code']=index.code.astype(str).str.zfill(6)
    base=read_parquet_or_empty(PROCESSED/'production_quarterly.parquet'); repaired=[]; audits=[]
    for period,(acu,aau) in ANCHOR_EXTRA.items():
        y,q=int(period[:4]),int(period[-1]); hit=index[(index.code==CODE)&(index.report_year==y)&(index.report_quarter==q)&(index.download_status=='downloaded')]
        if hit.empty: audits.append({'code':CODE,'period':period,'parse_warning':'PDF_MISSING'});continue
        item=hit.sort_values('announcement_time').iloc[-1]; text=extract_text(RAW/str(item.local_pdf_path)); cr,cu_u,cu=_pick(_values(text,'矿山产铜','cu')+_values(text,'矿产铜','cu'),acu); ar,au_u,au=_pick(_values(text,'矿山产金','au')+_values(text,'矿产金','au'),aau)
        cd,ad=_diff(cu,acu),_diff(au,aau); conf=.35*(cu is not None)+.35*(au is not None)+.1*(cd is not None and cd<.03)+.1*(ad is not None and ad<.03)
        cumulative=q in (2,3,4); strict=(not cumulative and conf>=.7); warning='CUMULATIVE_DATA_NEEDS_QUARTER_CONVERSION' if cumulative else ''
        if (cd is not None and cd>.1) or (ad is not None and ad>.1): warning=(warning+';' if warning else '')+'LOW_CONFIDENCE_ANCHOR_MISMATCH';strict=False
        audits.append({'code':CODE,'period':period,'source_pdf':str(item.local_pdf_path),'source_title':item.title,'extracted_cu_raw':cr,'extracted_cu_unit':cu_u,'cu_ton':cu,'extracted_au_raw':ar,'extracted_au_unit':au_u,'au_kg':au,'anchor_cu_ton':acu,'anchor_au_kg':aau,'cu_anchor_diff_pct':cd,'au_anchor_diff_pct':ad,'parse_confidence':conf,'strict_usable':strict,'proxy_usable':False,'parse_warning':warning})
        repaired.append({'quarter':pd.Timestamp(year=y,month=q*3,day=1)+pd.offsets.MonthEnd(0),'code':CODE,'cu_ton':cu,'au_kg':au,'source_pdf':str(item.local_pdf_path),'source_title':item.title,'source_type':'CNINFO_PDF_TABLE_TEXT','source_period':period,'is_cumulative':cumulative,'parse_confidence':conf,'parse_warning':warning,'data_quality_flag':'' if strict else 'NOT_STRICT_USABLE','strict_usable':strict,'proxy_usable':False,'source':'API_CNINFO_PDF'})
    repair=pd.DataFrame(repaired).reindex(columns=OUT_COLUMNS); audit=pd.DataFrame(audits).reindex(columns=AUDIT_COLUMNS); keep=base[~base.source_period.isin(repair.source_period)] if not repair.empty else base; save_parquet(pd.concat([keep,repair],ignore_index=True),PROCESSED/'production_quarterly.parquet'); audit.to_csv(REPORTS/'zijin_quarterly_production_repair.csv',index=False,encoding='utf-8-sig')
    lines=['# Zijin quarterly production repair','']+[f"- {r.period}: cu={r.cu_ton}, au={r.au_kg}, strict={r.strict_usable}, warning={r.parse_warning}" for r in audit.itertuples(index=False)]; (REPORTS/'zijin_quarterly_production_repair.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')

if __name__=='__main__':main()
