"""List distinct raw commodity names and units, to build the mapping table."""
import csv
from collections import Counter
from pathlib import Path

BASE = Path(__file__).resolve().parent
rows = list(csv.DictReader(open(BASE / "data/extracted/prices_raw.csv", encoding="utf-8-sig")))

# Dhaka splits type and name ("ডাল" + "মসুর (উন্নত)"), so keep both
names = Counter((r["commodity_type_raw"], r["commodity_name_raw"]) for r in rows)
units = Counter(r["unit_raw"] for r in rows)

out = BASE / "data/extracted/distinct_names.csv"
with open(out, "w", newline="", encoding="utf-8-sig") as f:
    w = csv.writer(f)
    w.writerow(["commodity_type_raw", "commodity_name_raw", "rows"])
    for (t, n), c in sorted(names.items(), key=lambda x: -x[1]):
        w.writerow([t, n, c])

print(f"{len(names)} distinct type+name combinations -> {out}")
print(f"\n{len(units)} distinct units:")
for u, c in units.most_common():
    print(f"  {c:6d}  {u!r}")