"""
RQ1 - Seasonal price patterns (improved version of seasonality_analysis.py).

How the seasonal index is calculated
  1. Monthly median midpoint price for each series (commodity x unit x division).
  2. A series-year qualifies if it has >= MIN_MONTHS months with data.
  3. Index = 100 * monthly median / (median of that series-year's monthly medians).
     100 = that division's typical price level in that year, so a general upward
     trend between years does not look like seasonality.
  4. Commodity-year-month index = median across divisions.
  5. Seasonal profile = median across years (with 25th/75th percentiles).

Evidence of a *real, repeating* pattern (per commodity-unit)
  - consistency: median Spearman correlation between one year's 12-month profile
    and the profile of all OTHER years (1 = same shape every year).
  - peak_stability: share of leave-one-year-out profiles with the same peak month.
  - Friedman test across months using complete (12-month) years as blocks,
    Benjamini-Hochberg corrected across commodities (exploratory).
  - division_agreement: median correlation of each division's profile with the
    national profile.

Run:  python rq1_seasonality.py
"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.stats import friedmanchisquare, spearmanr
from statsmodels.stats.multitest import multipletests

from dam_common import *

# Thresholds are set to what the current data can support (2024 partial, 2025 full,
# 2026 partial). With so few years, results are PRELIMINARY; say so in the paper.
MIN_MONTHS = 6        # months per series-year
MIN_YEARS = 2         # qualifying years per series
MIN_DIVISIONS = 3     # divisions needed before calling a pattern "national"
MIN_SHARED = 5        # months two years must share to compare their profiles

df = load_clean()
d = valid_prices(df)
m = monthly_medians(d)

# ---- eligibility ----
cov = m.groupby(SERIES + ["year"], as_index=False).agg(months=("month", "nunique"))
good = cov[cov["months"] >= MIN_MONTHS]
yrs = good.groupby(SERIES)["year"].nunique().reset_index(name="n_years")
good = good.merge(yrs[yrs["n_years"] >= MIN_YEARS][SERIES], on=SERIES)
m = m.merge(good[SERIES + ["year"]], on=SERIES + ["year"])
n_elig = good[SERIES].drop_duplicates().shape[0]
print(f"Eligible series: {n_elig}")
print("Qualifying series per year:\n", good.groupby("year").size().to_string())
if n_elig == 0:
    raise SystemExit("No series qualify. Lower MIN_MONTHS / MIN_YEARS (see table above).")

# ---- index ----
base = m.groupby(SERIES + ["year"], as_index=False).agg(base=("monthly_median_price", "median"))
m = m.merge(base, on=SERIES + ["year"])
m["seasonal_index"] = 100 * m["monthly_median_price"] / m["base"]
m.to_csv(OUT / "rq1_series_seasonal_index.csv", index=False)

nat = m.groupby(["commodity_name", "unit", "year", "month"], as_index=False).agg(
    seasonal_index=("seasonal_index", "median"),
    divisions=("division", "nunique"),
)
nat.to_csv(OUT / "rq1_commodity_year_month_index.csv", index=False)

# ---- per-commodity statistics ----
rows, profiles = [], {}
for (com, unit), g in nat.groupby(["commodity_name", "unit"]):
    piv = g.pivot(index="year", columns="month", values="seasonal_index").reindex(columns=range(1, 13))
    prof = piv.median()
    if prof.notna().sum() < 8 or len(piv) < MIN_YEARS:
        continue
    profiles[(com, unit)] = (prof, piv.quantile(.25), piv.quantile(.75))

    # consistency across years
    cors = []
    for y in piv.index:
        other = piv.drop(y).median()
        ok = piv.loc[y].notna() & other.notna()
        if ok.sum() >= MIN_SHARED:
            r = spearmanr(piv.loc[y][ok], other[ok]).correlation
            if not np.isnan(r):
                cors.append(r)

    # does one unusual year drive the peak month?
    peak = prof.idxmax()
    same = [piv.drop(y).median().idxmax() == peak for y in piv.index]

    # Friedman test (needs complete years)
    complete = piv.dropna()
    p_fr = np.nan
    if len(complete) >= 3:
        p_fr = friedmanchisquare(*[complete[c] for c in complete.columns]).pvalue

    # division agreement
    sub = m[(m.commodity_name == com) & (m.unit == unit)]
    dcors = []
    for dv, sg in sub.groupby("division"):
        dp = sg.groupby("month")["seasonal_index"].median().reindex(range(1, 13))
        ok = dp.notna() & prof.notna()
        if ok.sum() >= 6:
            dcors.append(spearmanr(dp[ok], prof[ok]).correlation)

    rows.append({
        "commodity_name": com, "unit": unit,
        "n_divisions": sub["division"].nunique(),
        "n_years": len(piv), "n_complete_years": len(complete),
        "peak_month": int(peak), "trough_month": int(prof.idxmin()),
        "peak_index": prof.max(), "trough_index": prof.min(),
        "amplitude": prof.max() - prof.min(),
        "consistency_across_years": np.median(cors) if cors else np.nan,
        "peak_stability": np.mean(same),
        "division_agreement": np.nanmedian(dcors) if dcors else np.nan,
        "friedman_p": p_fr,
    })

if not rows:
    raise SystemExit("No commodity has enough months/years for a profile. Lower thresholds.")
res = pd.DataFrame(rows)
res["friedman_q_BH"] = np.nan
mask = res["friedman_p"].notna()
if mask.any():      # needs >= 3 complete 12-month years; currently only 2025 is complete
    res.loc[mask, "friedman_q_BH"] = multipletests(res.loc[mask, "friedman_p"], method="fdr_bh")[1]

# Exploratory rule of thumb - state these thresholds openly in the paper.
res["national_claim_ok"] = res["n_divisions"] >= MIN_DIVISIONS
# Friedman is used only when available; otherwise candidates rest on amplitude +
# cross-year consistency alone and are labelled preliminary.
fr_ok = res["friedman_q_BH"].isna() | (res["friedman_q_BH"] < 0.05)
res["strong_candidate"] = (
    res["national_claim_ok"]
    & (res["amplitude"] >= 10)
    & (res["consistency_across_years"] >= 0.5)
    & (res["n_years"] >= 3)          # a 2-year "pattern" is just one comparison
    & fr_ok
)
res["evidence"] = np.where(res["friedman_q_BH"].notna(), "tested", "preliminary (<3 complete years)")
res = res.sort_values("amplitude", ascending=False)
res.to_csv(OUT / "rq1_seasonality_summary.csv", index=False)

print(f"\nCommodity-units assessed: {len(res)}")
print(f"Strong, nationally supported candidates: {int(res['strong_candidate'].sum())}")
print(res[["commodity_name", "unit", "n_divisions", "n_years", "peak_month", "trough_month",
           "amplitude", "consistency_across_years", "peak_stability", "friedman_q_BH",
           "strong_candidate"]].head(25).round(2).to_string(index=False))

# ---- figure: top candidates ----
pick = res[res["strong_candidate"]].head(6)
if pick.empty:
    pick = res.head(6)
fig, axes = plt.subplots(2, 3, figsize=(12, 6), sharex=True)
for ax, (_, r) in zip(axes.ravel(), pick.iterrows()):
    prof, lo, hi = profiles[(r.commodity_name, r.unit)]
    ax.plot(range(1, 13), prof.values, marker="o")
    ax.fill_between(range(1, 13), lo.values, hi.values, alpha=.25)
    ax.axhline(100, color="grey", lw=.7)
    ax.set_title(f"{r.commodity_name} ({r.unit}), {int(r.n_divisions)} div.", fontsize=9)
    ax.set_xticks(range(1, 13))
fig.supxlabel("Month")
fig.supylabel("Seasonal index (100 = yearly baseline)")
save_fig(fig, "rq1_top_seasonal_profiles.png")
