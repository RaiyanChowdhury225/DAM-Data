"""
features.py — build the analysis/modelling layer from the clean dataset.

    data/final/prices.csv            the dataset as published (no derived columns)
            |
            v
    data/final/prices_features.csv   the same observations plus engineered features

Everything here is DERIVED from prices.csv itself. No new data is scraped, so
the published dataset stays clean and this layer can be rebuilt at any time.

    python features.py
    python features.py --target direction    # target column = up / down / same
"""
import argparse
from pathlib import Path

import pandas as pd

BASE = Path(__file__).resolve().parent
IN_CSV = BASE / "data" / "final" / "prices.csv"
OUT_CSV = BASE / "data" / "final" / "prices_features.csv"

# Bangladesh's six-season calendar, by month
SEASON_SIX = {4: "Grishmo", 5: "Grishmo", 6: "Borsha", 7: "Borsha",
              8: "Sharat", 9: "Sharat", 10: "Hemanto", 11: "Hemanto",
              12: "Sheet", 1: "Sheet", 2: "Bosonto", 3: "Bosonto"}
# coarser three-season split, which is what most price work uses
SEASON_THREE = {3: "Summer", 4: "Summer", 5: "Summer",
                6: "Monsoon", 7: "Monsoon", 8: "Monsoon", 9: "Monsoon", 10: "Monsoon",
                11: "Winter", 12: "Winter", 1: "Winter", 2: "Winter"}
# rice harvest calendar: the two periods when new crop reaches the market
HARVEST = {4: "Boro", 5: "Boro", 6: "Boro", 7: "Aus", 8: "Aus",
           11: "Aman", 12: "Aman"}


def add_calendar(df):
    d = df["date"]
    df["year"] = d.dt.year
    df["month"] = d.dt.month
    df["day_of_week"] = d.dt.day_name()
    df["week_of_year"] = d.dt.isocalendar().week.astype("int32")
    df["season"] = df["month"].map(SEASON_SIX)          # six-season calendar
    df["season_group"] = df["month"].map(SEASON_THREE)  # summer / monsoon / winter
    df["harvest_period"] = df["month"].map(HARVEST).fillna("None")
    return df


def add_price_shape(df):
    """Features describing the price quotation itself, within one row."""
    df["avg_price"] = (df["min_price"] + df["max_price"]) / 2
    df["price_spread"] = df["max_price"] - df["min_price"]
    # spread relative to the price level: comparable across cheap and dear items
    df["spread_pct"] = (df["price_spread"] / df["avg_price"] * 100).round(2)
    return df


def add_time_series(df):
    """Features comparing an observation with earlier ones of the same series."""
    df = df.sort_values(["division", "commodity_name", "unit", "date"])
    g = df.groupby(["division", "commodity_name", "unit"], observed=True)

    df["prev_price"] = g["avg_price"].shift(1)
    # reports skip weekends and holidays, so the gap is not always one day
    df["days_since_prev"] = (df["date"] - g["date"].shift(1)).dt.days
    df["price_change"] = df["avg_price"] - df["prev_price"]
    df["pct_change"] = (df["price_change"] / df["prev_price"] * 100).round(2)

    # rolling window over the last 7 observations of this series (not 7 days)
    df["rolling_mean_7"] = g["avg_price"].transform(
        lambda s: s.rolling(7, min_periods=2).mean()).round(2)
    df["rolling_std_7"] = g["avg_price"].transform(
        lambda s: s.rolling(7, min_periods=2).std()).round(2)
    # how far today's price sits from its own recent level
    df["dev_from_rolling"] = (df["avg_price"] - df["rolling_mean_7"]).round(2)
    return df


def add_cross_section(df):
    """Features comparing a division with the rest of the country on the same day."""
    same_day = df.groupby(["date", "commodity_name", "unit"], observed=True)["avg_price"]
    df["national_avg"] = same_day.transform("mean").round(2)
    # positive => this division is dearer than the country that day
    df["premium_pct"] = ((df["avg_price"] - df["national_avg"]) / df["national_avg"] * 100).round(2)
    df["divisions_reporting"] = same_day.transform("size")
    return df


def add_target(df, kind):
    g = df.groupby(["division", "commodity_name", "unit"], observed=True)
    next_price = g["avg_price"].shift(-1)
    if kind == "price":
        df["target"] = next_price
    else:
        change = next_price - df["avg_price"]
        df["target"] = change.apply(
            lambda c: pd.NA if pd.isna(c) else ("up" if c > 0 else "down" if c < 0 else "same"))
    return df


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", choices=["price", "direction"], default="price")
    args = ap.parse_args()

    df = pd.read_csv(IN_CSV, parse_dates=["date"])
    before = len(df)

    df = add_calendar(df)
    df = add_price_shape(df)
    df = add_time_series(df)
    df = add_cross_section(df)
    df = add_target(df, args.target)

    df.to_csv(OUT_CSV, index=False, encoding="utf-8-sig")

    print(f"Wrote {len(df)} rows x {len(df.columns)} columns -> {OUT_CSV}")
    assert len(df) == before, "row count changed - features must not add or drop rows"
    print(f"  target = {args.target}; "
          f"{df['target'].isna().sum()} rows have no target (last observation of a series)")
    print(f"  {df['prev_price'].isna().sum()} rows have no previous observation")
    print("\nnew columns:")
    base = ["date", "division", "commodity_type", "commodity_name", "unit",
            "min_price", "max_price", "source_file", "source_url", "page_number"]
    for c in df.columns:
        if c not in base:
            filled = df[c].notna().mean() * 100
            print(f"  {c:20s} {filled:5.1f}% filled   e.g. {df[c].dropna().iloc[0] if filled else ''}")


if __name__ == "__main__":
    main()