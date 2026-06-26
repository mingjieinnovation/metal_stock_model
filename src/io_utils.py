from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)


def ensure_directories(*directories: Path) -> None:
    for directory in directories:
        directory.mkdir(parents=True, exist_ok=True)


def read_csv_if_exists(path: Path) -> pd.DataFrame:
    if not path.exists() or path.stat().st_size == 0:
        return pd.DataFrame()
    return pd.read_csv(path)


def _normalise_date_column(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame
    result = frame.copy()
    result["date"] = pd.to_datetime(result["date"], errors="coerce")
    result = result.dropna(subset=["date"]).sort_values("date")
    return result.drop_duplicates(subset=["date"], keep="last")


def merge_and_save(new_data: pd.DataFrame, path: Path) -> pd.DataFrame:
    """Append fresh observations without discarding a usable local history."""
    fresh = _normalise_date_column(new_data)
    old = _normalise_date_column(read_csv_if_exists(path))
    if fresh.empty:
        raise ValueError("fetch returned no rows with a valid date")
    combined = pd.concat([old, fresh], ignore_index=True, sort=False)
    combined = _normalise_date_column(combined)
    combined["date"] = combined["date"].dt.strftime("%Y-%m-%d")
    combined.to_csv(path, index=False, encoding="utf-8-sig")
    logger.info("Saved %s rows to %s", len(combined), path)
    return combined


def update_or_keep(path: Path, fetcher, label: str) -> bool:
    """Fetch and merge data; on failure leave the existing CSV untouched."""
    try:
        merge_and_save(fetcher(), path)
        return True
    except Exception as exc:
        logger.warning("%s update failed; retaining old file (%s): %s", label, path, exc)
        return False
