"""
dam_common.py  -  shared loading/cleaning code for all DAM-Data analysis scripts.

Lives next to the rq*.py scripts; run them from any folder.
It never modifies prices.csv.
"""
import os
from pathlib import Path

import numpy as np
import pandas as pd

# ------------------------------------------------------------------
# Paths (override with the DAM_ROOT environment variable if needed)
# ------------------------------------------------------------------
ROOT = Path(os.environ.get("DAM_ROOT", Path(__file__).resolve().parent.parent))
DATA_FILE = ROOT / "data" / "final" / "prices.csv"
OUT = ROOT / "data" / "final" / "analysis"
EXT = ROOT / "data" / "external"          # hand-collected inputs (CPI, holiday dates)
FIG = OUT / "figures"
for _p in (OUT, EXT, FIG):
    _p.mkdir(parents=True, exist_ok=True)

# A "series" = one commodity, in one unit, in one division.
# Prices are NEVER pooled across different units.
SERIES = ["commodity_name", "unit", "division"]

def load_clean() -> pd.DataFrame:
    """Load prices.csv and compute midpoint prices."""
    df = pd.read_csv(DATA_FILE, dtype={"date": "string"})

    # dates are repaired upstream (data/date_repairs.csv) and written as ISO by clean.py
    df["parsed_date"] = pd.to_datetime(df["date"], format="%Y-%m-%d", errors="coerce")
    if df["parsed_date"].isna().any():
        bad = df.loc[df["parsed_date"].isna(), "date"].unique()[:10]
        raise ValueError(f"prices.csv has non-ISO dates {list(bad)}: re-run clean.py")

    df["min_price"] = pd.to_numeric(df["min_price"], errors="coerce")
    df["max_price"] = pd.to_numeric(df["max_price"], errors="coerce")

    ok = (
        df["min_price"].notna()
        & df["max_price"].notna()
        & (df["min_price"] >= 0)
        & (df["max_price"] >= df["min_price"])
    )
    df["midpoint_price"] = np.where(ok, (df["min_price"] + df["max_price"]) / 2, np.nan)

    df["year"] = df["parsed_date"].dt.year
    df["month"] = df["parsed_date"].dt.month
    return df


def valid_prices(df: pd.DataFrame) -> pd.DataFrame:
    """Rows with a usable, strictly positive midpoint (needed for logs / ratios)."""
    return df[df["midpoint_price"].notna() & (df["midpoint_price"] > 0)].copy()


def monthly_medians(d: pd.DataFrame) -> pd.DataFrame:
    """Median midpoint price per series-year-month."""
    return d.groupby(SERIES + ["year", "month"], as_index=False).agg(
        monthly_median_price=("midpoint_price", "median"),
        observations=("midpoint_price", "size"),
    )


def save_fig(fig, name: str):
    fig.tight_layout()
    fig.savefig(FIG / name, dpi=200)
    print(f"  figure -> {FIG / name}")
