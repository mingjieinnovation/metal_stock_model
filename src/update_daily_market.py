"""Daily V2 market refresh: updates data only, never refits profit models."""
from __future__ import annotations
from datetime import date
from contextlib import contextmanager
import logging
import os
from urllib.parse import urlparse
import numpy as np
import pandas as pd

from . import fetch_macro, fetch_stock
from .fetch_external_real_factors import run as external_run
from .fetchers import fetch_sge_au9999, fetch_shfe_future, five_year_start
from .runtime import RAW, PROCESSED, REPORTS, ensure_layout, read_parquet_or_empty, save_parquet, write_status
from .v2_data_layer import build
from .v2_production_common import write_markdown

@contextmanager
def _without_unreachable_loopback_proxy():
    """Temporarily bypass only the known-dead local proxy used by this runtime."""
    proxy_keys = ("ALL_PROXY", "HTTP_PROXY", "HTTPS_PROXY", "GIT_HTTP_PROXY", "GIT_HTTPS_PROXY")
    removed = {}
    for key in proxy_keys:
        value = os.environ.get(key)
        if not value:
            continue
        parsed = urlparse(value)
        if parsed.hostname in {"127.0.0.1", "localhost", "::1"} and parsed.port == 9:
            removed[key] = value
            os.environ.pop(key, None)
    try:
        yield
    finally:
        os.environ.update(removed)
CONTRACTS={"al":("AL0","AL","沪铝0"),"ao":("AO0","AO","氧化铝0"),"cu":("CU0","CU","沪铜0"),"au":("AU0","AU","沪金0")}

def _merge_csv(path, fresh, value):
    old=pd.read_csv(path) if path.exists() else pd.DataFrame(columns=["date",value])
    new=fresh.rename(columns={fresh.columns[1]:value})[["date",value]].copy(); new.date=pd.to_datetime(new.date,errors="coerce")
    out=pd.concat([old,new],ignore_index=True);out.date=pd.to_datetime(out.date,errors="coerce");out[value]=pd.to_numeric(out[value],errors="coerce")
    out=out.dropna().drop_duplicates("date",keep="last").sort_values("date");out.to_csv(path,index=False);return out

def _prices() -> None:
    start,end=five_year_start(),date.today()
    for key, aliases in CONTRACTS.items():
        path=RAW/f"shfe_{key}.csv"
        try:
            frame=fetch_shfe_future(aliases,start,end); _merge_csv(path,frame,"close");write_status(f"daily_{key}","API_AKSHARE",True,f"{len(frame)} rows")
        except Exception as exc:
            write_status(f"daily_{key}","CACHE" if path.exists() else "BLOCKED",path.exists(),str(exc));logging.warning("%s update failed; old file retained: %s",key,exc)
    try:
        frame=fetch_sge_au9999(start,end);_merge_csv(RAW/"sge_au9999.csv",frame,"au_price_rmb_g");write_status("daily_au9999","API_AKSHARE_SGE",True,f"{len(frame)} rows")
    except Exception as exc:
        write_status("daily_au9999","CACHE" if (RAW/"sge_au9999.csv").exists() else "BLOCKED",(RAW/"sge_au9999.csv").exists(),str(exc))

def _freshness(as_of):
    as_of=pd.Timestamp(as_of).date()
    stale_days=(date.today()-as_of).days
    return as_of, stale_days, "FRESH" if stale_days <= 1 else "CACHE_STALE"

def _alert() -> None:
    c=read_parquet_or_empty(PROCESSED/"v2_chalco_daily_market.parquet");z=read_parquet_or_empty(PROCESSED/"v2_zijin_daily_market.parquet")
    v23=read_parquet_or_empty(PROCESSED/"v2_chalco_profit_v23_predictions.parquet");zv=read_parquet_or_empty(PROCESSED/"v2_zijin_profit_v21_predictions.parquet");rows=[]
    if not c.empty:
        r=c.iloc[-1]; p=float(r.actual_stock_close_raw); bear=float(v23.iloc[-1].bear_price) if not v23.empty else np.nan;base=float(v23.iloc[-1].base_price) if not v23.empty else np.nan;bull=float(v23.iloc[-1].bull_price) if not v23.empty else np.nan;as_of,stale_days,status=_freshness(r.date)
        rows.append({"company":"中国铝业","data_as_of":as_of,"data_status":status,"stale_days":stale_days,"actual_price":p,"predicted_price":base,"prediction_range_bear_base_bull":f"{bear:.2f} / {base:.2f} / {bull:.2f}" if np.isfinite(bear) else "unavailable","simple_al_spread":r.al_spread,"selected_k_spread":r.al_price-2.05*r.alumina_price,"daily_position":"below_bear" if p<bear else "above_bull" if p>bull else "within_range","alert":"daily_gap_alert_only","note":"Daily deviation alert only; not a tradable signal."})
    if not z.empty:
        r=z.iloc[-1];p=float(r.actual_stock_close_raw);model=float(zv.iloc[-1].model_price) if not zv.empty else np.nan;gap=p/model-1 if model else np.nan;as_of,stale_days,status=_freshness(r.date)
        rows.append({"company":"紫金矿业","data_as_of":as_of,"data_status":status,"stale_days":stale_days,"actual_price":p,"predicted_price":model,"daily_gap":gap,"alert":"gap_alert","note":"Daily deviation alert only; not a tradable signal."})
    out=pd.DataFrame(rows);save_parquet(out,PROCESSED/"v2_daily_market_snapshot.parquet")
    write_markdown(REPORTS/"v2_daily_alert.md","V2 Daily deviation alerts","The report shows the latest available market-data date. CACHE_STALE means the external API failed and the previous data was retained. All outputs are alerts only and cannot independently create a tradable signal.",out)

def main() -> None:
    logging.basicConfig(level=logging.INFO)
    ensure_layout()
    with _without_unreachable_loopback_proxy():
        fetch_stock.main()
        fetch_macro.main()
        _prices()
        external_run()
        build(("daily",))
        _alert()
if __name__=="__main__":main()

