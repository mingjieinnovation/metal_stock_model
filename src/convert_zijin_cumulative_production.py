from __future__ import annotations
import pandas as pd
from .runtime import PROCESSED, read_parquet_or_empty, save_parquet

def main():
    df=read_parquet_or_empty(PROCESSED/'production_quarterly.parquet'); derived=[]
    for year in sorted(df.quarter.dt.year.unique()):
        rows={int(r.source_period[-1]):r for _,r in df[(df.quarter.dt.year==year)&df.source_period.str.match(r'\d{4}Q[1-4]$')].iterrows()}
        if set(rows)!= {1,2,3,4}: continue
        if any(pd.isna(rows[q].cu_ton) or pd.isna(rows[q].au_kg) or rows[q].parse_confidence<.7 for q in rows): continue
        vals={1:(rows[1].cu_ton,rows[1].au_kg),2:(rows[2].cu_ton-rows[1].cu_ton,rows[2].au_kg-rows[1].au_kg),3:(rows[3].cu_ton-rows[2].cu_ton,rows[3].au_kg-rows[2].au_kg),4:(rows[4].cu_ton-rows[3].cu_ton,rows[4].au_kg-rows[3].au_kg)}
        for q,(cu,au) in vals.items():
            src=rows[q] if q==1 else rows[4]
            derived.append({**src.to_dict(),'quarter':pd.Timestamp(year=int(year),month=q*3,day=1)+pd.offsets.MonthEnd(0),'cu_ton':cu,'au_kg':au,'source_period':f'{year}Q{q}_STRICT_SINGLE','is_cumulative':False,'converted_from_cumulative':q>1,'strict_usable':True,'proxy_usable':False,'parse_warning':'DIRECT_Q1_PDF' if q==1 else 'STRICT_CUMULATIVE_CONVERSION','data_quality_flag':''})
    out=pd.DataFrame(derived); out=out.reindex(columns=list(df.columns)+(['converted_from_cumulative'] if 'converted_from_cumulative' not in df.columns else [])); existing=df[~df.source_period.str.contains('_STRICT_SINGLE',na=False)]; save_parquet(pd.concat([existing,out],ignore_index=True),PROCESSED/'production_quarterly.parquet')
if __name__=='__main__':main()
