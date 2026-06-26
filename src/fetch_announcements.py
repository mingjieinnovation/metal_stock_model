from __future__ import annotations

import logging
import re
from datetime import date
from pathlib import Path

import pandas as pd
import requests

from .runtime import CACHE, PROCESSED, RAW, call_with_timeout, ensure_layout, read_parquet_or_empty, save_parquet, write_status

CODES = {"601600": "\u4e2d\u56fd\u94dd\u4e1a", "601899": "\u7d2b\u91d1\u77ff\u4e1a"}
CATEGORIES = ("\u5e74\u62a5", "\u534a\u5e74\u62a5", "\u4e00\u5b63\u62a5", "\u4e09\u5b63\u62a5")
COLUMNS = ["code", "name", "category", "title", "announcement_time", "url", "report_year", "report_quarter", "local_pdf_path", "download_status", "source"]


def _quarter(title: str, time: object) -> tuple[int | None, int | None]:
    match = re.search(r"(20\d{2}).*?(\u7b2c\u4e00\u5b63\u5ea6|\u4e00\u5b63\u62a5|\u534a\u5e74|\u4e09\u5b63\u5ea6|\u4e09\u5b63\u62a5|\u5e74\u5ea6\u62a5\u544a|\u5e74\u62a5)", str(title))
    if match:
        quarter = {"\u7b2c\u4e00\u5b63\u5ea6": 1, "\u4e00\u5b63\u62a5": 1, "\u534a\u5e74": 2, "\u4e09\u5b63\u5ea6": 3, "\u4e09\u5b63\u62a5": 3, "\u5e74\u5ea6\u62a5\u544a": 4, "\u5e74\u62a5": 4}[match.group(2)]
        return int(match.group(1)), quarter
    return None, None


def fetch_cninfo_announcements(code: str, start_date: str, end_date: str) -> pd.DataFrame:
    import akshare as ak
    frames = []
    for category in CATEGORIES:
        raw = call_with_timeout(ak.stock_zh_a_disclosure_report_cninfo, symbol=code, market="\u6caa\u6df1\u4eac", category=category, start_date=start_date, end_date=end_date)
        if raw.empty: continue
        out = pd.DataFrame({"code": code, "name": CODES[code], "category": category, "title": raw["\u516c\u544a\u6807\u9898"], "announcement_time": pd.to_datetime(raw["\u516c\u544a\u65f6\u95f4"], errors="coerce"), "url": raw["\u516c\u544a\u94fe\u63a5"]})
        out[["report_year", "report_quarter"]] = [_quarter(t, d) for t, d in zip(out.title, out.announcement_time)]
        frames.append(out)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=COLUMNS)


def filter_periodic_reports(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty: return df
    excluded = "\u6458\u8981|\u82f1\u6587|\u66f4\u6b63|\u53d6\u6d88"
    out = df[~df["title"].astype(str).str.contains(excluded, regex=True, na=False)].copy()
    out = out.dropna(subset=["report_year", "report_quarter"]).sort_values("announcement_time")
    return out.drop_duplicates(["code", "report_year", "report_quarter"], keep="last")


def _pdf_url(url: str) -> str:
    if "finalpage" in url.lower(): return url
    match = re.search(r"announcementId=(\d+).*?announcementTime=(20\d{2}-\d{2}-\d{2})", url)
    return f"http://static.cninfo.com.cn/finalpage/{match.group(2)}/{match.group(1)}.PDF" if match else url


def download_pdf(url: str, output_path: str) -> bool:
    path = Path(output_path)
    if path.exists() and path.stat().st_size > 1024: return True
    try:
        response = requests.get(_pdf_url(url), timeout=30, headers={"User-Agent": "Mozilla/5.0"}); response.raise_for_status()
        if not response.content.startswith(b"%PDF"): return False
        path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(response.content); return True
    except Exception as exc:
        logging.warning("PDF download failed: %s", exc); return False


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s"); ensure_layout(); frames = []
    for code in CODES:
        try: frames.append(fetch_cninfo_announcements(code, "20200101", date.today().strftime("%Y%m%d")))
        except Exception as exc: logging.warning("CNINFO %s failed: %s", code, exc)
    index = filter_periodic_reports(pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=COLUMNS))
    if index.empty:
        index = read_parquet_or_empty(CACHE / "announcement_index_api_cache.parquet", COLUMNS); source = "CACHE"
    else:
        index["source"] = "API_CNINFO_PDF"; save_parquet(index, CACHE / "announcement_index_api_cache.parquet"); source = "API_CNINFO_PDF"
    paths, statuses = [], []
    for row in index.itertuples(index=False):
        filename = re.sub(r"[^A-Za-z0-9._-]+", "_", f"{row.code}_{row.report_year}Q{row.report_quarter}") + ".pdf"
        path = RAW / "reports" / str(row.code) / str(row.report_year) / filename
        paths.append(str(path.relative_to(RAW))); statuses.append("downloaded" if download_pdf(row.url, str(path)) else "failed")
    if not index.empty: index["local_pdf_path"], index["download_status"] = paths, statuses
    save_parquet(index.reindex(columns=COLUMNS), PROCESSED / "announcement_index.parquet")
    write_status("announcement_index", source, not index.empty, f"{len(index)} periodic reports")


if __name__ == "__main__":
    main()
