from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Paths:
    root: Path

    @property
    def raw(self) -> Path:
        return self.root / "data" / "raw"

    @property
    def manual(self) -> Path:
        return self.root / "data" / "manual"

    @property
    def reports(self) -> Path:
        return self.root / "reports"


STOCKS = {
    "chalco": {"code": "601600", "display": "中国铝业", "file": "stock_601600.csv"},
    "zijin": {"code": "601899", "display": "紫金矿业", "file": "stock_601899.csv"},
}

# The fetcher also tries compatible aliases because AKShare identifiers vary.
FUTURES = {
    "al": {"contracts": ("AL0", "AL", "沪铝0"), "file": "shfe_al.csv"},
    "cu": {"contracts": ("CU0", "CU", "沪铜0"), "file": "shfe_cu.csv"},
    "au": {"contracts": ("AU0", "AU", "沪金0"), "file": "shfe_au.csv"},
    "ao": {"contracts": ("AO0", "AO", "氧化铝0"), "file": "shfe_ao.csv"},
}

SGE_FILE = "sge_au9999.csv"
MANUAL_ALUMINA_FILE = "chalco_alumina_spot_monthly.csv"
