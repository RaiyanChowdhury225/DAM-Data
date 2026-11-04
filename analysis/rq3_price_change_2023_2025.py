"""
RQ3 - Nominal price change 2023 -> 2025, matched calendar months, fixed basket.

Why matched months: 2023 only has a few months of data (Jul-Oct in the current
dataset). Comparing a 4-month 2023 with a 12-month 2025 would mix seasonality into
the "price change". So for each commodity-unit-division series we compare only the
calendar months observed in BOTH 2023 and 2025.

Outputs (data/final/analysis/):
  rq3_series_changes.csv, rq3_commodity_changes.csv, rq3_division_changes.csv,
  rq3_overall_index.csv, figures/rq3_*.png
Run:  python rq3_price_change_2023_2025.py
"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from dam_common import *

YEARS = [2023, 2024, 2025]
MIN_COMMON_MONTHS = 3    # calendar months a series needs in BOTH 2023 and 2025
MIN_DIV_RANK = 3         # commodity must be in >= this many divisions to be ranked
MIN_DIV_COMMON = 5       # commodity set used for the division-vs-division comparison
N_BOOT = 2000
rng = np.random.default_rng(42)

df = load_clean()
d = valid_prices(df)
d = d[d["year"].isin(YEARS)]
m = monthly_medians(d)

mm = m.pivot(index=SERIES + ["month"], columns="year",
             values="monthly_median_price").reindex(columns=YEARS)
mm.columns = [f"y{c}" for c in mm.columns]
mm = mm.reset_index().dropna(subset=["y2023", "y2025"])
print("Calendar months observed in both 2023 and 2025:",
      sorted(int(x) for x in mm["month"].unique()))

common = mm.groupby(SERIES)["month"].nunique()
keep = common[common >= MIN_COMMON_MONTHS].index
if len(keep) == 0:
    raise SystemExit("No series share enough months between 2023 and 2025. Lower MIN_COMMON_MONTHS.")
mm = mm.set_index(SERIES).loc[keep].reset_index()

wide = mm.groupby(SERIES).agg(
    p2023=("y2023", "median"),
    p2024=("y2024", "median"),      # NaN when 2024 has none of those months
    p2025=("y2025", "median"),
    common_months=("month", "nunique"),
).reset_index()
wide["abs_change"] = wide["p2025"] - wide["p2023"]
wide["pct_change"] = (wide["p2025"] / wide["p2023"] - 1) * 100
wide["log_ratio"] = np.log(wide["p2025"] / wide["p2023"])
wide.to_csv(OUT / "rq3_series_changes.csv", index=False)

print(f"Fixed-basket series (commodity-unit-division): {len(wide)}")
print(f"Commodity-unit pairs: {wide.groupby(['commodity_name','unit']).ngroups}")

# ---- commodity-unit level (median over divisions) ----
com = wide.groupby(["commodity_name", "unit"]).agg(
    n_divisions=("division", "nunique"),
    p2023=("p2023", "median"),
    p2024=("p2024", "median"),
    p2025=("p2025", "median"),
    median_division_pct_change=("pct_change", "median"),
).reset_index()
com["abs_change"] = com["p2025"] - com["p2023"]
com["pct_change_2023_2025"] = (com["p2025"] / com["p2023"] - 1) * 100
com = com.sort_values("pct_change_2023_2025", ascending=False)
com.to_csv(OUT / "rq3_commodity_changes.csv", index=False)

# Rankings only for commodities seen in several divisions (one division = anecdote).
rk = com[com["n_divisions"] >= MIN_DIV_RANK]
cols = ["commodity_name", "unit", "n_divisions", "p2023", "p2025", "pct_change_2023_2025"]
print(f"\nRanked commodities (>= {MIN_DIV_RANK} divisions): {len(rk)} of {len(com)}")
print("\nTop 10 increases:")
print(rk.head(10)[cols].to_string(index=False, float_format="{:.1f}".format))
print("\nTop 10 decreases:")
print(rk.tail(10)[cols].to_string(index=False, float_format="{:.1f}".format))

q = com["pct_change_2023_2025"].quantile([0.25, 0.5, 0.75])
print(f"\nDistribution of commodity % changes (all {len(com)}): median={q[0.5]:.1f}%  "
      f"IQR=[{q[0.25]:.1f}%, {q[0.75]:.1f}%]  share rising={(com['pct_change_2023_2025'] > 0).mean():.0%}")

# ---- division level, on a COMMON commodity set so divisions are comparable ----
# Different divisions report different commodities; comparing their raw medians
# would mostly compare commodity mixes, not places.
common_com = com[com["n_divisions"] >= MIN_DIV_COMMON][["commodity_name", "unit"]]
wc = wide.merge(common_com, on=["commodity_name", "unit"])
div = wc.groupby("division").agg(
    n_commodities=("commodity_name", "nunique"),
    median_pct_change=("pct_change", "median"),
    q25=("pct_change", lambda s: s.quantile(.25)),
    q75=("pct_change", lambda s: s.quantile(.75)),
    jevons_pct=("log_ratio", lambda s: (np.exp(s.mean()) - 1) * 100),
).reset_index()
div.to_csv(OUT / "rq3_division_changes.csv", index=False)
print(f"\nBy division, common set of {len(common_com)} commodity-units seen in >= {MIN_DIV_COMMON} divisions:")
print(div.to_string(index=False, float_format="{:.1f}".format))

# ---- overall: equal-weight geometric mean of commodity ratios ----
def jevons(lr):
    return (np.exp(lr.mean()) - 1) * 100


def boot_ci(lr):
    b = np.array([jevons(rng.choice(lr, len(lr))) for _ in range(N_BOOT)])
    return np.percentile(b, 2.5), np.percentile(b, 97.5)


rows = []
for label, sub in [("all commodity-units", com), (f">= {MIN_DIV_RANK} divisions", rk)]:
    lr = np.log(sub["p2025"] / sub["p2023"]).to_numpy()
    lr24 = np.log(sub["p2024"] / sub["p2023"]).dropna().to_numpy()
    lo, hi = boot_ci(lr)
    rows.append({
        "basket": label, "commodity_units": len(sub),
        "jevons_pct_2023_to_2025": jevons(lr), "ci_low": lo, "ci_high": hi,
        "median_commodity_pct": sub["pct_change_2023_2025"].median(),
        "jevons_pct_2023_to_2024_partial": jevons(lr24) if len(lr24) else np.nan,
        "n_with_2024": len(lr24),
    })
# Sensitivity: drop divisions whose 2023 prices look inconsistent with the other divisions.
EXCLUDE_DIVISIONS = ["Dhaka", "Khulna"]
w2 = wide[~wide["division"].isin(EXCLUDE_DIVISIONS)]
c2 = w2.groupby(["commodity_name", "unit"]).agg(
    n_divisions=("division", "nunique"), p2023=("p2023", "median"), p2025=("p2025", "median")).reset_index()
c2 = c2[c2["n_divisions"] >= MIN_DIV_RANK]
if len(c2):
    lr2 = np.log(c2["p2025"] / c2["p2023"]).to_numpy()
    lo2, hi2 = boot_ci(lr2)
    rows.append({"basket": f">= {MIN_DIV_RANK} divisions, excl. {'/'.join(EXCLUDE_DIVISIONS)}",
                 "commodity_units": len(c2), "jevons_pct_2023_to_2025": jevons(lr2),
                 "ci_low": lo2, "ci_high": hi2,
                 "median_commodity_pct": ((c2["p2025"] / c2["p2023"] - 1) * 100).median(),
                 "jevons_pct_2023_to_2024_partial": np.nan, "n_with_2024": 0})
overall = pd.DataFrame(rows)
overall.to_csv(OUT / "rq3_overall_index.csv", index=False)
print("\nOverall nominal change 2023->2025, same calendar months (equal-weight geometric mean):")
print(overall.to_string(index=False, float_format="{:.1f}".format))
print("CI = bootstrap over commodities, NOT all Bangladesh prices. 2024 column is partial: indicative only.")

# ---- figures ----
fig, ax = plt.subplots(figsize=(7, 4))
ax.hist(com["pct_change_2023_2025"], bins=20, edgecolor="k")
ax.axvline(q[0.5], color="r", ls="--", label=f"median {q[0.5]:.1f}%")
ax.set_xlabel("% change, same calendar months, 2023 to 2025")
ax.set_ylabel("Commodity-unit pairs")
ax.legend()
save_fig(fig, "rq3_change_distribution.png")

top = pd.concat([rk.head(10), rk.tail(10)]).drop_duplicates()
fig, ax = plt.subplots(figsize=(7, 6))
labels = top["commodity_name"] + " (" + top["unit"] + ")"
ax.barh(labels[::-1], top["pct_change_2023_2025"][::-1])
ax.set_xlabel("% change 2023 to 2025")
save_fig(fig, "rq3_top_bottom_commodities.png")
