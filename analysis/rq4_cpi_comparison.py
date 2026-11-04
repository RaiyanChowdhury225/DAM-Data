"""
RQ4 - Compare DAM price changes with official BBS CPI over MATCHED calendar months.

DATA REALITY: DAM has partial years (2023 ~4 months, 2024 partial, 2025 full, 2026 partial),
so a continuous index from a common base year is impossible. Instead, for each pair of years
(a -> b) we compare only the calendar months observed in both:
  DAM change = equal-weight geometric mean over commodity-units of the national
               (median across divisions) monthly price ratio, same calendar months.
  CPI change = geometric mean of CPI(b, month)/CPI(a, month) over the same months.
Also a monthly year-on-year series (month vs same month a year earlier) for the chart.

YOU must supply the CPI file (I did not invent any numbers):
    data/external/bbs_cpi.csv   columns:  month (e.g. 2023-07), general_cpi, food_cpi
Source: Bangladesh Bureau of Statistics (bbs.gov.bd -> Statistics -> CPI/Inflation).
Record the BASE YEAR; do not splice series with different bases without rebasing.

Run:  python rq4_cpi_comparison.py
"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from dam_common import *

MIN_COMMON_MONTHS = 3       # months a commodity needs in both years of a pair
PAIRS = [(2023, 2025), (2024, 2025), (2025, 2026)]
CPI_FILE = EXT / "bbs_cpi.csv"

df = load_clean()
d = valid_prices(df)
m = monthly_medians(d)
nat = m.groupby(["commodity_name", "unit", "year", "month"], as_index=False).agg(
    price=("monthly_median_price", "median"))
K = ["commodity_name", "unit", "month"]


def joined(a, b):
    x = nat[nat.year == a].set_index(K)["price"].rename("a")
    y = nat[nat.year == b].set_index(K)["price"].rename("b")
    return pd.concat([x, y], axis=1, join="inner").reset_index()


def dam_pair(a, b, allowed=None):
    j = joined(a, b)
    if allowed is not None:          # only months for which CPI exists in BOTH years
        j = j[j["month"].isin(allowed)]
    if j.empty:
        return None
    cnt = j.groupby(["commodity_name", "unit"])["month"].nunique()
    keep = cnt[cnt >= MIN_COMMON_MONTHS].index
    j = j.set_index(["commodity_name", "unit"]).loc[keep].reset_index() if len(keep) else j.iloc[0:0]
    if j.empty:
        return None
    j["lr"] = np.log(j["b"] / j["a"])
    per = j.groupby(["commodity_name", "unit"])["lr"].mean()      # equal weight per commodity
    return (np.exp(per.mean()) - 1) * 100, len(per), sorted(int(x) for x in j["month"].unique())


# ---- DAM monthly YoY (month vs same month one year earlier) ----
nat["period"] = pd.to_datetime(dict(year=nat.year, month=nat.month, day=1))
prev = nat[["commodity_name", "unit", "period", "price"]].copy()
prev["period"] = prev["period"] + pd.DateOffset(years=1)
yo = nat.merge(prev, on=["commodity_name", "unit", "period"], suffixes=("", "_prev"))
yo["lr"] = np.log(yo["price"] / yo["price_prev"])
yoy = yo.groupby("period").agg(n=("lr", "size"), dam_yoy_pct=("lr", lambda s: (np.exp(s.mean()) - 1) * 100)).reset_index()
thr = min(10, max(3, int(0.5 * yoy["n"].max()))) if len(yoy) else 3
yoy = yoy[yoy["n"] >= thr]

# If a (possibly partial) CPI file exists, compare DAM only over months where CPI is available
# in both years of a pair, so DAM and CPI always cover the same calendar months.
cpi_pre = None
if CPI_FILE.exists():
    _c = pd.read_csv(CPI_FILE)
    _c = _c.dropna(subset=["month", "general_cpi", "food_cpi"])
    if not _c.empty:
        _c["period"] = pd.to_datetime(_c["month"].astype(str) + "-01")
        cpi_pre = _c.set_index("period")


def allowed_months(a, b):
    if cpi_pre is None:
        return None
    return {mo for mo in range(1, 13)
            if pd.Timestamp(a, mo, 1) in cpi_pre.index and pd.Timestamp(b, mo, 1) in cpi_pre.index}


pairs = []
for a, b in PAIRS:
    r = dam_pair(a, b, allowed_months(a, b))
    if r:
        pairs.append({"from": a, "to": b, "dam_pct": r[0], "commodity_units": r[1],
                      "months": ",".join(map(str, r[2]))})
pairs = pd.DataFrame(pairs)
print("DAM nominal change, matched calendar months (restricted to months with CPI when a CPI file exists):")
print(pairs.to_string(index=False, float_format="{:.1f}".format) if len(pairs) else "none")

if not CPI_FILE.exists():
    pd.DataFrame(columns=["month", "general_cpi", "food_cpi"]).to_csv(CPI_FILE, index=False)
    pairs.to_csv(OUT / "rq4_pair_comparison.csv", index=False)
    yoy.to_csv(OUT / "rq4_dam_monthly_yoy.csv", index=False)
    raise SystemExit(f"\nTemplate created at {CPI_FILE}. Fill it with official BBS values and re-run. "
                     "Until then RQ4 stays a stated limitation.")
cpi = pd.read_csv(CPI_FILE)
if cpi.dropna().empty:
    pairs.to_csv(OUT / "rq4_pair_comparison.csv", index=False)
    yoy.to_csv(OUT / "rq4_dam_monthly_yoy.csv", index=False)
    raise SystemExit("CPI file is empty - DAM results saved, CPI comparison skipped.")

cpi["period"] = pd.to_datetime(cpi["month"].astype(str) + "-01")
cpi = cpi.set_index("period").sort_index()


def cpi_pair(a, b, months, col):
    r = []
    for mo in months:
        pa, pb = pd.Timestamp(a, mo, 1), pd.Timestamp(b, mo, 1)
        if pa in cpi.index and pb in cpi.index:
            r.append(np.log(cpi.loc[pb, col] / cpi.loc[pa, col]))
    return (np.exp(np.mean(r)) - 1) * 100 if r else np.nan


for col in ["general_cpi", "food_cpi"]:
    pairs[col + "_pct"] = [cpi_pair(r["from"], r["to"], [int(x) for x in r["months"].split(",")], col)
                           for _, r in pairs.iterrows()]
pairs["dam_minus_food_pp"] = pairs["dam_pct"] - pairs["food_cpi_pct"]
pairs.to_csv(OUT / "rq4_pair_comparison.csv", index=False)
print("\nDAM vs BBS CPI, same calendar months:")
print(pairs.to_string(index=False, float_format="{:.1f}".format))

for col in ["general_cpi", "food_cpi"]:
    prv = cpi[col].copy(); prv.index = prv.index + pd.DateOffset(years=1)
    cpi[col + "_yoy"] = (cpi[col] / prv.reindex(cpi.index) - 1) * 100
c = yoy.merge(cpi.reset_index()[["period", "general_cpi_yoy", "food_cpi_yoy"]], on="period", how="inner")
c.to_csv(OUT / "rq4_dam_vs_cpi_monthly_yoy.csv", index=False)
cc = c.dropna(subset=["dam_yoy_pct", "food_cpi_yoy"])
if len(cc) >= 6:
    print(f"\nCorrelation of monthly YoY, DAM vs food CPI: {cc['dam_yoy_pct'].corr(cc['food_cpi_yoy']):.2f} "
          f"(n={len(cc)} months; small n, interpret cautiously)")

if len(c):
    fig, ax = plt.subplots(figsize=(9, 4))
    ax.plot(c["period"], c["dam_yoy_pct"], marker="o", label="DAM commodities (YoY %)")
    ax.plot(c["period"], c["food_cpi_yoy"], marker="o", label="BBS food CPI (YoY %)")
    ax.plot(c["period"], c["general_cpi_yoy"], marker="o", label="BBS general CPI (YoY %)")
    ax.legend(); ax.set_ylabel("Year-on-year change (%)")
    save_fig(fig, "rq4_dam_vs_cpi.png")
