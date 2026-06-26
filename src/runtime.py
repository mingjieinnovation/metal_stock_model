from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Iterable

import pandas as pd

ROOT = Path.cwd()
DATA = ROOT / "data"
RAW = DATA / "raw"
CACHE = DATA / "cache"
FALLBACK = DATA / "fallback"
PROCESSED = DATA / "processed"
REPORTS = ROOT / "reports"
MODELS = ROOT / "models"


def ensure_layout() -> None:
    for path in (RAW, CACHE, FALLBACK, PROCESSED, REPORTS, MODELS, RAW / "reports"):
        path.mkdir(parents=True, exist_ok=True)


def read_parquet_or_empty(path: Path, columns: Iterable[str] = ()) -> pd.DataFrame:
    if path.exists() and path.stat().st_size:
        try:
            return pd.read_parquet(path)
        except Exception:
            try:
                return pd.read_pickle(path)
            except Exception as exc:
                logging.warning("Cannot read %s: %s", path, exc)
    return pd.DataFrame(columns=list(columns))


def save_parquet(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        frame.to_parquet(path, index=False)
    except ImportError:
        frame.to_pickle(path)
        logging.warning("pyarrow unavailable; stored local pickle fallback at %s", path)


def cache_or_fallback(cache_path: Path, fallback_path: Path, columns: Iterable[str]) -> tuple[pd.DataFrame, str]:
    cached = read_parquet_or_empty(cache_path)
    if not cached.empty:
        return cached, "CACHE"
    if fallback_path.exists() and fallback_path.stat().st_size:
        try:
            return pd.read_csv(fallback_path), "FALLBACK_CSV"
        except Exception as exc:
            logging.warning("Cannot read fallback %s: %s", fallback_path, exc)
    return pd.DataFrame(columns=list(columns)), "NEUTRAL_DEFAULT"


def write_status(dataset: str, source: str, success: bool, detail: str = "") -> None:
    ensure_layout()
    path = CACHE / "api_status.csv"
    existing = pd.read_csv(path) if path.exists() else pd.DataFrame(columns=["dataset", "checked_at", "source", "success", "detail"])
    row = pd.DataFrame([{
        "dataset": dataset, "checked_at": datetime.now().isoformat(timespec="seconds"),
        "source": source, "success": success, "detail": detail[:500],
    }])
    updated = pd.concat([existing, row], ignore_index=True).tail(500)
    updated.to_csv(path, index=False, encoding="utf-8-sig")


def safe_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def call_with_timeout(function, *args, timeout_seconds: int = 45, **kwargs):
    """Bound third-party API calls; a stalled provider must not stop the pipeline."""
    import queue
    import threading
    result: queue.Queue = queue.Queue(maxsize=1)

    def worker() -> None:
        try:
            result.put((True, function(*args, **kwargs)))
        except BaseException as exc:
            result.put((False, exc))

    thread = threading.Thread(target=worker, daemon=True)
    thread.start(); thread.join(timeout_seconds)
    if thread.is_alive():
        raise TimeoutError(f"API call exceeded {timeout_seconds}s")
    succeeded, value = result.get_nowait()
    if not succeeded:
        raise value
    return value


