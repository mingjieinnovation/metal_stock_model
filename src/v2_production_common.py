from __future__ import annotations
from datetime import datetime, timezone
import os
import pandas as pd
from .runtime import read_parquet_or_empty, save_parquet
SOURCE_TYPES={"API","CACHE","FALLBACK_CSV","DEFAULT_PROXY","PDF_STRICT","PDF_LOW_CONFIDENCE","BLOCKED"}
def now_utc(): return datetime.now(timezone.utc).isoformat(timespec="seconds")
def source_record(data_source,source_type,*,available_date=None,is_proxy=False,is_strict=False,flag="",value=None,item=""):
    if source_type not in SOURCE_TYPES: raise ValueError(f"Unsupported source_type: {source_type}")
    available=pd.to_datetime(available_date,errors="coerce") if available_date is not None else pd.NaT
    stale=(pd.Timestamp.now(tz="UTC").tz_localize(None).normalize()-available.normalize()).days if pd.notna(available) else pd.NA
    return {"data_item":item,"value":value,"data_source":data_source,"source_type":source_type,"available_date":available,"fetched_at":now_utc(),"is_proxy":bool(is_proxy),"is_strict":bool(is_strict),"data_quality_flag":flag,"stale_days":stale}
def merge_cache(new,path,keys):
    old=read_parquet_or_empty(path);combined=pd.concat([old,new],ignore_index=True,sort=False) if not old.empty else new.copy()
    if combined.empty:return combined
    combined=combined.drop_duplicates(keys,keep="last").sort_values(keys).reset_index(drop=True);save_parquet(combined,path);return combined
def repair_text(value):
    if not isinstance(value,str) or not any(ord(ch)>127 for ch in value): return value
    result=value
    for _ in range(3):
        try:
            raw=bytearray()
            for char in result:
                raw.extend(bytes([ord(char)]) if ord(char)<=255 else char.encode("cp1252"))
            repaired=bytes(raw).decode("utf-8")
        except (UnicodeEncodeError,UnicodeDecodeError,ValueError): break
        if repaired==result: break
        result=repaired
    return result
def repair_frame(frame):
    out=frame.copy();out.columns=[repair_text(c) for c in out.columns]
    for col in out.select_dtypes(include=["object","string"]).columns:out[col]=out[col].map(repair_text)
    return out
def write_markdown(path,title,text,table=None):
    title,text=repair_text(title),repair_text(text);table=repair_frame(table) if table is not None else None
    lines=[f"# {title}","",text.strip(),""]
    if table is not None and not table.empty:
        cols=list(table.columns);lines += ["| "+" | ".join(cols)+" |","|"+"|".join(["---"]*len(cols))+"|"]
        for row in table.fillna("").astype(str).itertuples(index=False,name=None):lines.append("| "+" | ".join(x.replace("|","\\|").replace("\n"," ") for x in row)+" |")
    path.write_text("\n".join(lines)+"\n",encoding="utf-8")
def env_present(name):return bool(os.getenv(name,"").strip())
def latest_frame(path):
    data=read_parquet_or_empty(path)
    if data.empty:return None
    return data.sort_values("date").iloc[-1] if "date" in data else data.iloc[-1]
