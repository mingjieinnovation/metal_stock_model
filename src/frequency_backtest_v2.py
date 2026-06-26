"""Command-line entry point for V2 strict frequency backtests."""
from __future__ import annotations

import argparse

from .v2_walk_forward import FREQUENCIES, run_v2_walk_forward_strict


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--frequency", choices=(*FREQUENCIES, "all"), default="monthly")
    parser.add_argument("--mode", choices=("full_sample", "walk_forward", "both"), default="both")
    args = parser.parse_args()
    frequencies = FREQUENCIES if args.frequency == "all" else (args.frequency,)
    # V2 remains an expanding strict walk-forward model. --mode is accepted for
    # CLI compatibility and never invokes the retired placeholder/proxy flow.
    for frequency in frequencies:
        print(run_v2_walk_forward_strict(frequency))


if __name__ == "__main__":
    main()
