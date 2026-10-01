"""
add_target.py — build the modelling table from the clean dataset.

data/final/prices.csv          the dataset (no target column, as published)
        |
        v
data/final/prices_modeling.csv the same rows plus the prediction target

The target is the NEXT observed price for the same commodity in the same
division, so it is derived from the dataset itself and nothing new is scraped.

    python add_target.py                  # target = next average price (regression)
    python add_target.py --target direction   # target = up / down / same (classification)
"""
import argparse
import csv
from collections import defaultdict
from pathlib import Path
from statistics import mean

BASE = Path(__file__).resolve().parent
IN_CSV = BASE / "data" / "final" / "prices.csv"
OUT_CSV = BASE / "data" / "final" / "prices_modeling.csv"


def load_rows():
    with IN_CSV.open(encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def collapse(rows):
    """One observation per date+division+commodity+unit.

    Some divisions list two varieties that the mapping merges (e.g. two kinds of
    coarse rice). Averaging them keeps one row per date so the shift lines up.
    """
    groups = defaultdict(list)
    for r in rows:
        if r["min_price"] and r["max_price"]:
            key = (r["division"], r["commodity_name"], r["unit"], r["date"])
            groups[key].append((float(r["min_price"]) + float(r["max_price"])) / 2)
    return {k: round(mean(v), 2) for k, v in groups.items()}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", choices=["price", "direction"], default="price")
    args = ap.parse_args()

    avg = collapse(load_rows())

    # series[(division, commodity, unit)] = [(date, avg_price), ...] in date order
    series = defaultdict(list)
    for (div, name, unit, date), price in avg.items():
        series[(div, name, unit)].append((date, price))
    for key in series:
        series[key].sort()

    out = []
    for (div, name, unit), points in series.items():
        for i, (date, price) in enumerate(points[:-1]):
            next_date, next_price = points[i + 1]
            # reports are not daily (no weekends/holidays), so record the gap
            gap = (int(next_date[8:10]) - int(date[8:10])
                   + 30 * (int(next_date[5:7]) - int(date[5:7])))
            if args.target == "price":
                target = next_price
            else:
                target = "up" if next_price > price else "down" if next_price < price else "same"
            out.append({"date": date, "division": div, "commodity_name": name, "unit": unit,
                        "avg_price": price, "days_to_next": gap, "target": target})

    fields = ["date", "division", "commodity_name", "unit", "avg_price", "days_to_next", "target"]
    with OUT_CSV.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(out)

    print(f"Wrote {len(out)} rows -> {OUT_CSV}  (target = {args.target})")
    print(f"  {len(series)} series (division x commodity), "
          f"{sum(1 for p in series.values() if len(p) < 3)} with fewer than 3 observations")
    if args.target == "direction":
        counts = defaultdict(int)
        for r in out:
            counts[r["target"]] += 1
        print("  class balance:", dict(counts))


if __name__ == "__main__":
    main()