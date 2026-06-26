"""One conservative, auditable latest-decision table; never refits a model."""
from __future__ import annotations
import numpy as np
import pandas as pd
from .runtime import PROCESSED, REPORTS, read_parquet_or_empty
from .v2_production_common import write_markdown, repair_frame


def _latest(path):
    d=read_parquet_or_empty(path)
    return d.iloc[-1] if not d.empty else pd.Series(dtype=object)


def _proxy_ratio(company: str) -> float:
    d=read_parquet_or_empty(PROCESSED/f"v2_{company}_monthly_market.parquet")
    if d.empty or "data_quality_flag" not in d:return 1.0
    s=str(d.iloc[-1].data_quality_flag); text=s.split("DEFAULT_PROXY:",1)[-1].split(";",1)[0] if "DEFAULT_PROXY:" in s else ""
    return len([x for x in text.split(",") if x])/7


def build() -> pd.DataFrame:
    chalco=_latest(PROCESSED/"v2_chalco_profit_v23_predictions.parquet"); zijin=_latest(PROCESSED/"v2_zijin_profit_v21_predictions.parquet")
    cm=_latest(PROCESSED/"v2_chalco_monthly_market.parquet"); zm=_latest(PROCESSED/"v2_zijin_monthly_market.parquet")
    actual_c=float(cm.get("actual_stock_close_raw",np.nan)); bear=float(chalco.get("bear_price",np.nan)); base=float(chalco.get("base_price",np.nan)); bull=float(chalco.get("bull_price",np.nan))
    zone=("extreme_undervaluation_observation" if actual_c<bear else "undervalued_but_requires_fundamental_confirmation" if actual_c<base else "fair_value_zone" if actual_c<=bull else "strong_cycle_expectation_priced_in") if np.isfinite(actual_c) and np.isfinite(bear) else "unavailable"
    actual_z=float(zm.get("actual_stock_close_raw",np.nan)); model_z=float(zijin.get("model_price",np.nan)); gap=actual_z/model_z-1 if model_z else np.nan; zr=_proxy_ratio("zijin")
    ztrend=bool(zm.get("cu_price",np.nan)>0 and zm.get("au_price_rmb_g",np.nan)>0)
    ztrade=bool(zijin.get("production_strict_usable",False)) and zr<.5 and np.isfinite(gap) and abs(gap)>.12 and ztrend
    cr=_proxy_ratio("chalco")
    rows=[
      {"company":"ä¸­å›½é“ä¸š","main_model":"V2.3-K Bear/Base/Bull","actual_price":actual_c,"model_price_or_range":f"{bear:.2f} / {base:.2f} / {bull:.2f}" if np.isfinite(bear) else "ä¸å¯ç”¨","bear_price":bear,"base_price":base,"bull_price":bull,"gap":np.nan,"price_zone":zone,"data_quality_score":round(1-cr,2),"proxy_ratio":round(cr,2),"signal_status":"valuation_anchor_only","can_trade":False,"reason":"V2.3 ä»…å…è®¸åŒºé—´ä¼°å€¼ï¼›Model J ä»ç¼ºä¸¥æ ¼äº§é‡ï¼Œä¸” OOS æ¡ä»¶æœªæ»¡è¶³ã€‚","next_watch_item":"ä¸¥æ ¼åŽŸé“äº§é‡ä¸Žæ°§åŒ–é“å¤–é”€é‡"},
      {"company":"ç´«é‡‘çŸ¿ä¸š","main_model":"V2.1 strict é“œé‡‘æ”¶å…¥æ¨¡åž‹","actual_price":actual_z,"model_price_or_range":model_z,"bear_price":np.nan,"base_price":np.nan,"bull_price":np.nan,"gap":gap,"price_zone":"undervalued" if gap<-.12 else "overvalued" if gap>.12 else "fair_value_zone","data_quality_score":round(1-zr,2),"proxy_ratio":round(zr,2),"signal_status":"valuation_observation" if not ztrade else "weekly_undervalued_observation","can_trade":ztrade,"reason":"ä¸¥æ ¼äº§é‡å·²æŽ¥å…¥ï¼›è‹¥éœ€æ±‚åˆ†æ•°ä»ç”±é»˜è®¤ä»£ç†ä¸»å¯¼ï¼Œåˆ™è‡ªåŠ¨é™çº§ä¸ºè§‚å¯Ÿã€‚","next_watch_item":"DFII10ã€ç¾Žå…ƒæŒ‡æ•°ã€é»„é‡‘ ETF ä¸Žé“œåº“å­˜åŽ†å²"},
    ]
    return pd.DataFrame(rows)


def main() -> None:
    table=repair_frame(build()); table.to_csv(REPORTS/"v2_latest_decision_table.csv",index=False,encoding="utf-8-sig")
    write_markdown(REPORTS/"v2_latest_decision_table.md","V2 æœ€æ–°å†³ç­–è¡¨","æ­¤è¡¨ä¸ºç ”ç©¶ç”¨é€”ï¼›ä¸­å›½é“ä¸šä¸è¾“å‡ºäº¤æ˜“ä¿¡å·ï¼Œè´¨é‡é—¸é—¨ä¸é€šè¿‡æ—¶æ‰€æœ‰ç»“æžœè‡ªåŠ¨é™çº§ã€‚",table)
if __name__=="__main__":main()

