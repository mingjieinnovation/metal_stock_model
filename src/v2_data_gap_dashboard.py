"""Auditable dashboard of known V2 data gaps; no model fitting."""
from __future__ import annotations
import pandas as pd
from .runtime import PROCESSED, REPORTS, read_parquet_or_empty
from .v2_production_common import write_markdown, repair_frame


def _exists(path, field=None) -> bool:
    data = read_parquet_or_empty(path)
    return not data.empty and (field is None or field in data and data[field].notna().any())


def build() -> pd.DataFrame:
    chalco_prod = read_parquet_or_empty(PROCESSED / "v2_chalco_strict_production.parquet")
    def strict(f): return not chalco_prod.empty and f in chalco_prod and chalco_prod.get("strict_usable", pd.Series(False)).fillna(False).any() and chalco_prod[f].notna().any()
    fred = read_parquet_or_empty(PROCESSED / "fred_macro_features.parquet")
    rows = [
      ["åŽŸé“/ç”µè§£é“äº§é‡", "ä¸­å›½é“ä¸š", "æœ€é«˜", "å·²æŽ¥å…¥" if strict("primary_al_output_ton") else "ç¼ºå¤±", "PDF_STRICT" if strict("primary_al_output_ton") else "BLOCKED", False, True, "Model J", "éœ€è¦ä¸¥æ ¼å­£åº¦äº§é‡", "ä¸‹è½½å¹¶è§£æžä¸­é“å­£æŠ¥ PDF"],
      ["æ°§åŒ–é“å¤–é”€é‡", "ä¸­å›½é“ä¸š", "æœ€é«˜", "å·²æŽ¥å…¥" if strict("alumina_external_sales_ton") else "ç¼ºå¤±", "PDF_STRICT" if strict("alumina_external_sales_ton") else "BLOCKED", False, True, "Model J", "éœ€è¦ä¸¥æ ¼å­£åº¦å¤–é”€é‡", "ä¸‹è½½å¹¶è§£æžä¸­é“å­£æŠ¥ PDF"],
      ["åŒºåŸŸç”µä»·", "ä¸­å›½é“ä¸š", "é«˜", "ç¼ºå°‘ä»˜è´¹æ•°æ®", "BLOCKED", False, True, "Model I", "çœŸå®žç”µä»·", "é…ç½® SMM/Mysteel/Baichuan token"],
      ["é¢„ç„™é˜³æž", "ä¸­å›½é“ä¸š", "é«˜", "ç¼ºå°‘ä»˜è´¹æ•°æ®", "BLOCKED", False, True, "Model I", "çœŸå®žé˜³æžä»·æ ¼", "é…ç½® SMM/Mysteel/Baichuan token"],
      ["åŠ¨åŠ›ç…¤", "ä¸­å›½é“ä¸š", "ä¸­", "ç¼ºå°‘ä»˜è´¹æ•°æ®", "BLOCKED", False, False, "", "æˆæœ¬åˆ†è§£", "é…ç½®ä»˜è´¹æ•°æ® token"],
      ["2020-2023æ°§åŒ–é“çŽ°è´§", "ä¸­å›½é“ä¸š", "ä¸­", "AOæœŸè´§ä¸Šå¸‚å‰ç¼ºå£", "BLOCKED", False, False, "åŽ†å²æ‰©æ ·", "çœŸå®žçŽ°è´§åŽ†å²", "é…ç½® SMM/Baichuan åŽ†å²æ•°æ®"],
      ["10YçœŸå®žåˆ©çŽ‡ DFII10", "ç´«é‡‘çŸ¿ä¸š", "é«˜", "å·²æŽ¥å…¥" if (not fred.empty and fred.source_type.astype(str).eq("API").any()) else "ç­‰å¾… FRED key", "API" if (not fred.empty and fred.source_type.astype(str).eq("API").any()) else "BLOCKED", True, False, "éœ€æ±‚åˆ†æ•°", "é™ä½Žä»£ç†å æ¯”", "é…ç½® FRED_API_KEY"],
      ["ç¾Žå…ƒæŒ‡æ•°", "ç´«é‡‘çŸ¿ä¸š", "é«˜", "å·²æŽ¥å…¥" if (not fred.empty and fred.data_item.astype(str).eq("usd_index").any()) else "ç¼ºå¤±", "API" if (not fred.empty and fred.data_item.astype(str).eq("usd_index").any()) else "BLOCKED", True, False, "éœ€æ±‚åˆ†æ•°", "é™ä½Žä»£ç†å æ¯”", "é…ç½® FRED_API_KEY"],
      ["é»„é‡‘ ETF", "ç´«é‡‘çŸ¿ä¸š", "é«˜", "å·²æŽ¥å…¥" if _exists(PROCESSED / "wgc_gold_etf_monthly.parquet", "value") else "ç¼ºå¤±", "API" if _exists(PROCESSED / "wgc_gold_etf_monthly.parquet", "value") else "BLOCKED", True, False, "éœ€æ±‚åˆ†æ•°", "é™ä½Žä»£ç†å æ¯”", "é…ç½® WGC_COOKIE"],
      ["é“œåº“å­˜", "ç´«é‡‘çŸ¿ä¸š", "ä¸­", "å…¬å¼€ API å·²æŽ¥å…¥ï¼ŒåŽ†å²çª—å£ä¸è¶³", "API", True, False, "éœ€æ±‚åˆ†æ•°", "å½¢æˆå¯é æ»šåŠ¨åˆ†ä½", "æŒç»­ç´¯ç§¯å¯å®¡è®¡åŽ†å²"],
      ["æµ·å¤–é£Žé™©æŠ˜æ‰£", "ç´«é‡‘çŸ¿ä¸š", "ä¸­", "ç¼ºå°‘ç»“æž„åŒ–çœŸå®žæ¥æº", "BLOCKED", True, False, "éœ€æ±‚åˆ†æ•°", "äº‹ä»¶é£Žé™©å› å­", "ç¡®è®¤å¯å®¡è®¡äº‹ä»¶æ•°æ®æº"],
    ]
    return pd.DataFrame(rows, columns=["data_item","company","priority","current_status","source_type","is_proxy","is_blocking_model","blocked_model","required_for_signal_upgrade","next_action"])


def main() -> None:
    table = repair_frame(build()); table.to_csv(REPORTS / "v2_data_gap_dashboard.csv", index=False, encoding="utf-8-sig")
    write_markdown(REPORTS / "v2_data_gap_dashboard.md", "V2 æ•°æ®ç¼ºå£çœ‹æ¿", "çŠ¶æ€ä»¥å½“å‰æœ¬åœ°æ•°æ®ä¸ºå‡†ï¼›BLOCKED è¡¨ç¤ºä¸èƒ½ä»¥é»˜è®¤å€¼å†’å……çœŸå®žæ•°æ®ã€‚", table)
if __name__ == "__main__": main()

