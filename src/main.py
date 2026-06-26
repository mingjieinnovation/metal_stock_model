from __future__ import annotations

import argparse
import logging
from datetime import date
from pathlib import Path

import pandas as pd

from .config import FUTURES, SGE_FILE, STOCKS, Paths
from .features import build_chalco_features, build_zijin_features
from .fetchers import fetch_sge_au9999, fetch_shfe_future, fetch_stock_history, five_year_start
from .io_utils import ensure_directories, update_or_keep
from .modeling import run_expanding_backtest


def update_raw_data(paths: Paths, start: date, end: date) -> None:
    for item in STOCKS.values():
        update_or_keep(
            paths.raw / item["file"],
            lambda item=item: fetch_stock_history(item["code"], start, end),
            item["display"],
        )
    for name, item in FUTURES.items():
        update_or_keep(
            paths.raw / item["file"],
            lambda item=item: fetch_shfe_future(item["contracts"], start, end),
            f"SHFE {name.upper()}",
        )
    update_or_keep(paths.raw / SGE_FILE, lambda: fetch_sge_au9999(start, end), "SGE Au99.99")


def write_signal_markdown(signals: pd.DataFrame, errors: list[str], destination: Path) -> None:
    lines = ["# Latest metal-stock model signals", "", "Monthly model estimates; not investment advice.", ""]
    if not signals.empty:
        lines.extend(["| Model | As of | Actual close | Estimated close | Difference | R² | MAE |", "|---|---:|---:|---:|---:|---:|---:|"])
        for row in signals.itertuples(index=False):
            lines.append(
                f"| {row.model} | {row.as_of_month} | {row.actual_stock_close:.2f} | "
                f"{row.model_estimated_close:.2f} | {row.upside_downside_pct:.2f}% | "
                f"{row.backtest_r2:.3f} | {row.backtest_mae:.3f} |"
            )
    if errors:
        lines.extend(["", "## Non-fatal update issues", ""])
        lines.extend(f"- {error}" for error in errors)
    destination.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Update metal prices and backtest monthly equity models.")
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="Project root (default: current directory)")
    parser.add_argument("--skip-fetch", action="store_true", help="Run reports from existing raw CSV files only")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    paths = Paths(args.root.resolve())
    ensure_directories(paths.raw, paths.manual, paths.reports)
    today = date.today()
    start = five_year_start(today)
    if not args.skip_fetch:
        update_raw_data(paths, start, today)

    errors: list[str] = []
    signals: list[dict[str, object]] = []
    cutoff = pd.Timestamp(today) - pd.DateOffset(years=5)
    jobs = [
        ("chalco", lambda: build_chalco_features(paths.raw, paths.manual, cutoff), ["al_spread", "al_price"]),
        ("zijin", lambda: build_zijin_features(paths.raw, cutoff), ["cu_price", "au_price_rmb_g"]),
    ]
    labels = {"chalco": "中国铝业 601600.SH", "zijin": "紫金矿业 601899.SH"}
    for name, build_features, feature_columns in jobs:
        try:
            result = run_expanding_backtest(build_features(), "stock_close", feature_columns, labels[name])
            result.backtest.to_csv(paths.reports / f"{name}_backtest.csv", index=False, encoding="utf-8-sig")
            signals.append(result.latest_signal)
            logging.info("Completed %s backtest", labels[name])
        except Exception as exc:
            message = f"{labels[name]} report not refreshed: {exc}"
            logging.warning(message)
            errors.append(message)

    signal_frame = pd.DataFrame(signals)
    signal_frame.to_csv(paths.reports / "latest_signal.csv", index=False, encoding="utf-8-sig")
    write_signal_markdown(signal_frame, errors, paths.reports / "latest_signal.md")
    logging.info("Pipeline finished. %s model report(s) refreshed.", len(signals))


if __name__ == "__main__":
    main()
