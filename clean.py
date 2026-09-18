"""
clean.py — Stage 2: raw rows -> the final research dataset.

Reads   data/extracted/prices_raw.csv   (from extractor.py)
        data/commodity_map.csv          (raw Bangla name -> standard name, edited by hand)
Writes  data/final/prices.csv

One row = one commodity observation for one division on one date.
Nothing is invented here: names come from the mapping file, prices are the
numbers in the report, and missing prices stay missing.

Usage:
    python clean.py
"""
import csv
import unicodedata
from collections import Counter
from pathlib import Path

BASE = Path(__file__).resolve().parent
RAW_CSV = BASE / "data" / "extracted" / "prices_raw.csv"
MAP_CSV = BASE / "data" / "commodity_map.csv"
OUT_CSV = BASE / "data" / "final" / "prices.csv"

FIELDS = ["date", "division", "commodity_type", "commodity_name", "unit",
          "min_price", "max_price", "source_file", "source_url", "page_number"]

# raw unit text -> standard unit. The price is never rescaled: a 5-litre can
# and a hali of 4 eggs are priced as sold.
UNITS = {
    "প্রতি কেজি": "kg",
    "1 কেজি": "kg",
    "1.50-2 কেজি": "kg",          # describes the size of the fish, price is per kg
    "": "kg",                      # Rangpur rows whose ditto mark has nothing above it
    "1 লিটার": "litre",
    "01লিটার": "litre",
    "1 লিটার (925 গ্রাম)": "litre",
    "5 লিটার": "5_litre",
    "প্রতিটি": "piece",
    "4টি": "4_pieces",
    "04 টি": "4_pieces",
}


def norm(text):
    return unicodedata.normalize("NFC", (text or "").strip())


def load_map():
    """(type_raw, name_raw) -> (commodity_type, commodity_name)"""
    mapping = {}
    with MAP_CSV.open(encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            key = (norm(r["commodity_type_raw"]), norm(r["commodity_name_raw"]))
            mapping[key] = (r["commodity_type"].strip(), r["commodity_name"].strip())
    return mapping


def to_price(text):
    """'150.00' -> 150.0 ; '' / None -> None. 0.00 means 'no price in the report'."""
    if text in (None, ""):
        return None
    value = float(text)
    return None if value == 0 else value


def main():
    mapping = load_map()
    rows, problems = [], Counter()
    unmapped, unknown_units = Counter(), Counter()

    with RAW_CSV.open(encoding="utf-8-sig") as f:
        for raw in csv.DictReader(f):
            key = (norm(raw["commodity_type_raw"]), norm(raw["commodity_name_raw"]))
            if key not in mapping:
                unmapped[key] += 1                 # new wording: add it to the mapping file
                continue
            ctype, cname = mapping[key]
            unit_raw = norm(raw["unit_raw"])
            if unit_raw not in UNITS:
                unknown_units[unit_raw] += 1
                continue
            mn, mx = to_price(raw["min_price_raw"]), to_price(raw["max_price_raw"])
            if mn is None or mx is None:
                problems["no price"] += 1
            elif mn > mx:
                mn, mx = mx, mn                    # a few reports write the two the wrong way round
                problems["min/max swapped"] += 1
            rows.append({"date": raw["date_raw"], "division": raw["division_raw"],
                         "commodity_type": ctype, "commodity_name": cname,
                         "unit": UNITS[unit_raw], "min_price": mn, "max_price": mx,
                         "source_file": raw["source_file"], "source_url": raw["source_url"],
                         "page_number": raw["page_number"]})

    # same commodity twice on one date+division: usually two varieties that the
    # mapping merged (e.g. two kinds of fine rice). Worth knowing, not an error.
    dupes = Counter((r["date"], r["division"], r["commodity_name"], r["unit"]) for r in rows)
    problems["duplicate observations"] = sum(n - 1 for n in dupes.values() if n > 1)

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with OUT_CSV.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)

    print(f"Wrote {len(rows)} rows -> {OUT_CSV}")
    print(f"  {len({r['commodity_name'] for r in rows})} commodities, "
          f"{len({r['division'] for r in rows})} divisions, "
          f"{len({r['date'] for r in rows})} dates")
    for k, n in problems.most_common():
        print(f"  {k}: {n}")
    if unmapped:
        print(f"\n{sum(unmapped.values())} rows DROPPED - not in the mapping file:")
        for (t, n), c in unmapped.most_common(20):
            print(f"  {c:5d}  {t} | {n}")
    if unknown_units:
        print(f"\n{sum(unknown_units.values())} rows DROPPED - unknown unit:")
        for u, c in unknown_units.most_common():
            print(f"  {c:5d}  {u!r}")


if __name__ == "__main__":
    main()