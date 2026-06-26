"""Production gate: blocks tradable outputs if audit/strict/proxy checks fail."""
from __future__ import annotations
import pandas as pd
from .runtime import PROCESSED, RAW, REPORTS, read_parquet_or_empty
from .v2_production_common import write_markdown, repair_frame


def _proxy_ratio(path) -> float:
    d = read_parquet_or_empty(path)
    if d.empty or "data_quality_flag" not in d: return 1.0
    flag = str(d.iloc[-1].data_quality_flag)
    part = flag.split("DEFAULT_PROXY:", 1)[-1].split(";", 1)[0] if "DEFAULT_PROXY:" in flag else ""
    return len([x for x in part.split(",") if x]) / 7


def build() -> pd.DataFrame:
    stocks = [read_parquet_or_empty(RAW / "stock_daily_raw" / f"{c}.parquet") for c in ("601600", "601899")]
    raw_ok = all(not d.empty and "adjust" in d and set(d.adjust.astype(str).dropna()) == {"none"} for d in stocks)
    zjprod = read_parquet_or_empty(PROCESSED / "v2_zijin_strict_production.parquet")
    chprod = read_parquet_or_empty(PROCESSED / "v2_chalco_strict_production.parquet")
    zstrict = not zjprod.empty and zjprod.get("strict_usable", pd.Series(False)).fillna(False).any()
    cvolume = (not chprod.empty and all(c in chprod for c in ("primary_al_output_ton", "alumina_external_sales_ton")) and chprod.get("strict_usable", pd.Series(False)).fillna(False).any() and chprod["primary_al_output_ton"].notna().any() and chprod["alumina_external_sales_ton"].notna().any())
    rows = [
      ["è‚¡ç¥¨ä»·æ ¼ä¸å¤æƒ", "å…¨å±€", raw_ok, "BLOCKED_STOCK_ADJUSTMENT" if not raw_ok else "é€šè¿‡", "ç¦æ­¢è¾“å‡ºäº¤æ˜“ä¿¡å·"],
      ["å•†å“ä»·æ ¼æœ€æ–°æ€§", "å…¨å±€", not read_parquet_or_empty(PROCESSED / "v2_chalco_daily_market.parquet").empty, "MISSING_MARKET_DATA", "ä»…ç ”ç©¶/æŠ¥è­¦"],
      ["è´¢æŠ¥å…¬å‘Šæ—¥å¯è§", "å…¨å±€", not read_parquet_or_empty(PROCESSED / "announcement_index.parquet").empty, "MISSING_ANNOUNCEMENT_INDEX", "ç¦æ­¢ä»¥æœªæ¥è´¢æŠ¥è®­ç»ƒ"],
      ["ç´«é‡‘ä¸¥æ ¼äº§é‡", "ç´«é‡‘çŸ¿ä¸š", zstrict, "MISSING_STRICT_PRODUCTION" if not zstrict else "é€šè¿‡", "ç¦æ­¢äº¤æ˜“ä¿¡å·"],
      ["ä¸­é“ Model J äº§é‡", "ä¸­å›½é“ä¸š", cvolume, "BLOCKED_MISSING_STRICT_VOLUME" if not cvolume else "é€šè¿‡", "ç»´æŒåŒºé—´ä¼°å€¼"],
      ["ç´«é‡‘éœ€æ±‚é»˜è®¤ä»£ç†å æ¯”", "ç´«é‡‘çŸ¿ä¸š", _proxy_ratio(PROCESSED / "v2_zijin_monthly_market.parquet") <= .5, f"PROXY_RATIO={_proxy_ratio(PROCESSED / 'v2_zijin_monthly_market.parquet'):.0%}", "é™çº§ä¸ºè§‚å¯Ÿ"],
      ["ä¸­é“éœ€æ±‚é»˜è®¤ä»£ç†å æ¯”", "ä¸­å›½é“ä¸š", _proxy_ratio(PROCESSED / "v2_chalco_monthly_market.parquet") <= .5, f"PROXY_RATIO={_proxy_ratio(PROCESSED / 'v2_chalco_monthly_market.parquet'):.0%}", "ä»…ä¼°å€¼ä¸­æž¢"],
    ]
    return pd.DataFrame(rows, columns=["æ£€æŸ¥é¡¹","å…¬å¸","passed","data_quality_flag","ä¸é€šè¿‡åŽçš„è¾“å‡ºé™åˆ¶"])


def main() -> None:
    table=repair_frame(build()); table.to_csv(REPORTS / "v2_data_quality_gate.csv", index=False, encoding="utf-8-sig")
    passed=bool(table.passed.all()); text="è´¨é‡é—¸é—¨é€šè¿‡ã€‚" if passed else "è´¨é‡é—¸é—¨æœªå®Œå…¨é€šè¿‡ï¼šä¸å¾—è¾“å‡º tradable_signalï¼Œåªèƒ½è¾“å‡º valuation / observation / alertã€‚"
    write_markdown(REPORTS / "v2_data_quality_gate.md", "V2 æ•°æ®è´¨é‡é—¸é—¨", text, table)
if __name__ == "__main__": main()


