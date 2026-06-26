from __future__ import annotations

import logging
from datetime import date

import pandas as pd

from .runtime import CACHE, FALLBACK, PROCESSED, call_with_timeout, cache_or_fallback, ensure_layout, read_parquet_or_empty, save_parquet, write_status

CODES = {"601600": "中国铝业", "601899": "紫金矿业"}
COLUMNS = ["quarter", "code", "name", "revenue_cum", "net_profit_cum", "eps_cum", "revenue_q", "net_profit_q", "eps_q", "announcement_date", "source", "data_quality_flag"]


def _find(frame: pd.DataFrame, candidates: tuple[str, ...]) -> str | None:
    normalized = {str(c).strip().lower(): c for c in frame.columns}
    for candidate in candidates:
        if candidate.lower() in normalized:
            return normalized[candidate.lower()]
    for column in frame.columns:
        text = str(column).lower()
        if any(candidate.lower() in text for candidate in candidates):
            return column
    return None


def _number(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series.astype(str).str.replace(",", "", regex=False), errors="coerce")


def fetch_financial_period(date: str) -> pd.DataFrame:
    """Fetch one A-share reporting period, normalised to the two research stocks."""
    import akshare as ak
    errors: list[str] = []
    for function, source in ((ak.stock_yjbb_em, "API_EASTMONEY_YJBB"), (ak.stock_lrb_em, "API_EASTMONEY_LRB")):
        try:
            raw = call_with_timeout(function, date=date)
            code_col = _find(raw, ("股票代码", "代码")); name_col = _find(raw, ("股票简称", "简称"))
            revenue_col = _find(raw, ("营业收入", "营业总收入")); profit_col = _find(raw, ("归属净利润", "净利润"))
            eps_col = _find(raw, ("每股收益", "基本每股收益", "eps")); announce_col = _find(raw, ("公告日期", "最新公告日期"))
            if not code_col or not profit_col:
                raise ValueError(f"required financial columns absent: {list(raw.columns)}")
            data = raw.copy()
            data[code_col] = data[code_col].astype(str).str.zfill(6)
            data = data[data[code_col].isin(CODES)]
            if data.empty:
                raise ValueError("target companies absent from response")
            out = pd.DataFrame({
                "quarter": pd.to_datetime(date), "code": data[code_col],
                "name": data[name_col] if name_col else data[code_col].map(CODES),
                "revenue_cum": _number(data[revenue_col]) if revenue_col else pd.NA,
                "net_profit_cum": _number(data[profit_col]),
                "eps_cum": _number(data[eps_col]) if eps_col else pd.NA,
                "announcement_date": pd.to_datetime(data[announce_col], errors="coerce") if announce_col else pd.NaT,
                "source": source, "data_quality_flag": "net_profit_approximation" if "归属" not in str(profit_col) else "",
            })
            return out
        except Exception as exc:
            errors.append(f"{function.__name__}: {exc}")
    raise RuntimeError("; ".join(errors))


def _to_yi(series: pd.Series) -> pd.Series:
    numeric = pd.to_numeric(series, errors="coerce")
    # Eastmoney reports normally arrive in yuan; fallback sheets may already be 亿.
    return numeric.where(numeric.abs() < 1_000_000, numeric / 100_000_000)


def convert_cumulative_to_single_quarter(df: pd.DataFrame) -> pd.DataFrame:
    """Convert Q1/H1/9M/FY cumulative disclosures to a stand-alone quarter."""
    if df.empty:
        return pd.DataFrame(columns=COLUMNS)
    data = df.copy(); data["quarter"] = pd.to_datetime(data["quarter"])
    data = data.sort_values(["code", "quarter"]).drop_duplicates(["code", "quarter"], keep="last")
    for column in ("revenue_cum", "net_profit_cum", "eps_cum"):
        data[column] = pd.to_numeric(data[column], errors="coerce")
    data["revenue_q"] = data.groupby(["code", data["quarter"].dt.year])["revenue_cum"].diff().fillna(data["revenue_cum"])
    data["net_profit_q"] = data.groupby(["code", data["quarter"].dt.year])["net_profit_cum"].diff().fillna(data["net_profit_cum"])
    data["eps_q"] = data.groupby(["code", data["quarter"].dt.year])["eps_cum"].diff().fillna(data["eps_cum"])
    data["net_profit_q"] = _to_yi(data["net_profit_q"])
    return data.reindex(columns=COLUMNS)


def fetch_company_financials(code: str, start_year: int, end_year: int) -> pd.DataFrame:
    periods = [f"{year}{suffix}" for year in range(start_year, end_year + 1) for suffix in ("0331", "0630", "0930", "1231")]
    rows = []
    for period in periods:
        try:
            rows.append(fetch_financial_period(period).query("code == @code"))
        except Exception as exc:
            logging.warning("Financial %s/%s unavailable: %s", code, period, exc)
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame(columns=COLUMNS)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    ensure_layout(); year = date.today().year
    api_rows = []
    for period_year in range(year - 6, year + 1):
        for suffix in ("0331", "0630", "0930", "1231"):
            try:
                api_rows.append(fetch_financial_period(f"{period_year}{suffix}"))
            except Exception as exc:
                logging.warning("Financial API %s%s failed: %s", period_year, suffix, exc)
    api_data = pd.concat(api_rows, ignore_index=True) if api_rows else pd.DataFrame(columns=COLUMNS)
    if not api_data.empty:
        save_parquet(api_data, CACHE / "financial_api_cache.parquet")
        source, detail = "API_EASTMONEY", f"{len(api_data)} cumulative rows"
    else:
        cached = read_parquet_or_empty(CACHE / "financial_api_cache.parquet", COLUMNS)
        if not cached.empty:
            api_data, source, detail = cached, "CACHE", "API unavailable; retained API cache"
        else:
            fallback_rows = []
            for code, filename in (("601600", "chalco_quarterly_profit.csv"), ("601899", "zijin_quarterly_profit.csv")):
                path = FALLBACK / filename
                if path.exists() and path.stat().st_size > 30:
                    raw = pd.read_csv(path); raw["code"] = code; raw["name"] = CODES[code]
                    raw["quarter"] = pd.to_datetime(raw["quarter"], errors="coerce")
                    raw["net_profit_q"] = raw.get("net_profit_q", raw.get("net_profit_bn"))
                    raw["eps_q"] = raw.get("eps_q", raw.get("eps")); raw["source"] = "FALLBACK_CSV"; raw["data_quality_flag"] = "financial_fallback"
                    fallback_rows.append(raw.reindex(columns=COLUMNS))
            api_data, source, detail = (pd.concat(fallback_rows, ignore_index=True) if fallback_rows else pd.DataFrame(columns=COLUMNS)), "FALLBACK_CSV", "API and cache unavailable"
    converted = convert_cumulative_to_single_quarter(api_data) if not api_data.empty and "net_profit_cum" in api_data else api_data.reindex(columns=COLUMNS)
    save_parquet(converted, PROCESSED / "financial_quarterly.parquet")
    write_status("financial_quarterly", source, not converted.empty, detail)







def report_dates(start_year: int, end_year: int) -> list[str]:
    return [f"{year}{suffix}" for year in range(start_year, end_year + 1) for suffix in ("0331", "0630", "0930", "1231")]


def fetch_yjbb_one_period(date: str) -> pd.DataFrame:
    import akshare as ak
    raw = call_with_timeout(ak.stock_yjbb_em, date=date)
    return _normalise_eastmoney(raw, date, "API_EASTMONEY_YJBB")


def fetch_lrb_one_period(date: str) -> pd.DataFrame:
    import akshare as ak
    raw = call_with_timeout(ak.stock_lrb_em, date=date)
    return _normalise_eastmoney(raw, date, "API_EASTMONEY_LRB")


def _normalise_eastmoney(raw: pd.DataFrame, report_date: str, source: str) -> pd.DataFrame:
    code_col = _find(raw, ("\u80a1\u7968\u4ee3\u7801", "\u4ee3\u7801")); name_col = _find(raw, ("\u80a1\u7968\u7b80\u79f0", "\u7b80\u79f0"))
    revenue_col = _find(raw, ("\u8425\u4e1a\u6536\u5165", "\u8425\u4e1a\u603b\u6536\u5165")); attributable_col = _find(raw, ("\u5f52\u5c5e\u51c0\u5229\u6da6",))
    profit_col = attributable_col or _find(raw, ("\u51c0\u5229\u6da6",)); eps_col = _find(raw, ("\u6bcf\u80a1\u6536\u76ca", "\u57fa\u672c\u6bcf\u80a1\u6536\u76ca", "eps")); announce_col = _find(raw, ("\u516c\u544a\u65e5\u671f", "\u6700\u65b0\u516c\u544a\u65e5\u671f"))
    if not code_col or not profit_col: raise ValueError("required Eastmoney financial columns missing")
    data = raw.copy(); data[code_col] = data[code_col].astype(str).str.zfill(6); data = data[data[code_col].isin(CODES)]
    return pd.DataFrame({"quarter": pd.to_datetime(report_date), "code": data[code_col], "name": data[name_col] if name_col else data[code_col].map(CODES), "revenue_cum": _number(data[revenue_col]) if revenue_col else pd.NA, "net_profit_cum": _number(data[profit_col]), "eps_cum": _number(data[eps_col]) if eps_col else pd.NA, "announcement_date": pd.to_datetime(data[announce_col], errors="coerce") if announce_col else pd.NaT, "source": source, "data_quality_flag": "" if attributable_col else "NET_PROFIT_USED_AS_ATTRIBUTABLE"})


def fetch_sina_financial_report(code: str) -> pd.DataFrame:
    import akshare as ak
    raw = call_with_timeout(ak.stock_financial_report_sina, stock=f"sh{code}", symbol="\u5229\u6da6\u8868")
    date_col, revenue_col = "\u62a5\u544a\u65e5", "\u8425\u4e1a\u603b\u6536\u5165"
    profit_col, eps_col, announce_col = "\u5f52\u5c5e\u4e8e\u6bcd\u516c\u53f8\u6240\u6709\u8005\u7684\u51c0\u5229\u6da6", "\u57fa\u672c\u6bcf\u80a1\u6536\u76ca", "\u516c\u544a\u65e5\u671f"
    if date_col not in raw or revenue_col not in raw: raise ValueError("Sina profit-report schema changed")
    out = pd.DataFrame({"quarter": pd.to_datetime(raw[date_col].astype(str), format="%Y%m%d", errors="coerce"), "code": code, "name": CODES[code], "revenue_cum": _number(raw[revenue_col]) / 100_000_000, "net_profit_cum": _number(raw[profit_col]) / 100_000_000, "eps_cum": _number(raw[eps_col]), "announcement_date": pd.to_datetime(raw[announce_col].astype(str), format="%Y%m%d", errors="coerce"), "source": "API_SINA", "data_quality_flag": ""})
    return out.dropna(subset=["quarter"]).sort_values("announcement_date").drop_duplicates("quarter", keep="last")


def fetch_company_financials(codes: list[str], start_year: int, end_year: int) -> pd.DataFrame:
    api_rows = []
    for period in report_dates(start_year, end_year):
        for fetcher in (fetch_yjbb_one_period, fetch_lrb_one_period):
            try:
                api_rows.append(fetcher(period))
                break
            except Exception as exc:
                logging.warning("%s %s unavailable: %s", fetcher.__name__, period, exc)
    api = pd.concat(api_rows, ignore_index=True) if api_rows else pd.DataFrame(columns=COLUMNS)
    sina_rows = []
    for code in codes:
        try:
            sina_rows.append(fetch_sina_financial_report(code))
        except Exception as exc:
            logging.warning("Sina financial %s unavailable: %s", code, exc)
    sina = pd.concat(sina_rows, ignore_index=True) if sina_rows else pd.DataFrame(columns=COLUMNS)
    combined = pd.concat([api, sina], ignore_index=True)
    if combined.empty:
        return combined
    combined = combined[combined["code"].astype(str).isin(codes)]
    combined = combined.sort_values(["code", "quarter", "source"]).drop_duplicates(["code", "quarter"], keep="first")
    return combined.reindex(columns=COLUMNS)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    ensure_layout(); end_year = date.today().year
    api_data = fetch_company_financials(list(CODES), 2020, end_year)
    if not api_data.empty:
        save_parquet(api_data, CACHE / "financial_api_cache.parquet")
        converted = convert_cumulative_to_single_quarter(api_data)
        source, detail = "API_FINANCIAL", f"{len(converted)} quarterly records"
    else:
        cached = read_parquet_or_empty(CACHE / "financial_api_cache.parquet", COLUMNS)
        if not cached.empty:
            converted, source, detail = convert_cumulative_to_single_quarter(cached), "CACHE", "API unavailable; retained API cache"
        else:
            converted, source, detail = pd.DataFrame(columns=COLUMNS), "NEUTRAL_DEFAULT", "API/cache/fallback unavailable"
    save_parquet(converted.reindex(columns=COLUMNS), PROCESSED / "financial_quarterly.parquet")
    write_status("financial_quarterly", source, not converted.empty, detail)


if __name__ == "__main__":
    main()

