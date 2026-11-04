"""
paper_figures.py - column-width figures for the analysis section of the paper.

Reads prices.csv (through dam_common) and the rq*.csv outputs, so run it AFTER
rq3, rq1, rq5. Writes PDF figures to data/final/analysis/figures/paper/.
Run:  python paper_figures.py
"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from dam_common import *

PAPER = FIG / "paper"
PAPER.mkdir(parents=True, exist_ok=True)

BLUE, ORANGE, GREY, INK, INK2 = "#2a78d6", "#eb6834", "#b8b7b1", "#0b0b0b", "#52514e"
plt.rcParams.update({
    "font.family": "serif", "font.serif": ["TeX Gyre Termes", "Liberation Serif", "DejaVu Serif"],
    "font.size": 7.5, "axes.titlesize": 7.5, "axes.labelsize": 7.5,
    "xtick.labelsize": 6.5, "ytick.labelsize": 6.5, "legend.fontsize": 6.5,
    "axes.edgecolor": INK2, "axes.linewidth": 0.5, "axes.labelcolor": INK,
    "xtick.color": INK2, "ytick.color": INK2, "xtick.major.width": 0.5, "ytick.major.width": 0.5,
    "axes.spines.top": False, "axes.spines.right": False,
    "savefig.bbox": "tight", "savefig.pad_inches": 0.02,
})
COL = 3.45   # IEEE single-column width, inches
MON = list("JFMAMJJASOND")


def save(fig, name):
    fig.savefig(PAPER / name)
    plt.close(fig)
    print("figure ->", PAPER / name)


df = load_clean()
d = valid_prices(df)

# ---------- Fig. A: coverage (valid rows by year x month) ----------
cov = d.groupby(["year", "month"]).size().unstack().reindex(columns=range(1, 13))
fig, ax = plt.subplots(figsize=(COL, 1.75))
vals = np.log10(cov.values.astype(float))
im = ax.imshow(vals, cmap="Blues", aspect="auto", vmin=1, vmax=np.nanmax(vals))
for i in range(cov.shape[0]):
    for j in range(12):
        v = cov.values[i, j]
        if not np.isnan(v):
            ax.text(j, i, f"{v/1000:.1f}k" if v >= 1000 else f"{int(v)}", ha="center", va="center",
                    fontsize=5, color="white" if vals[i, j] > 3.4 else INK)
ax.set_xticks(range(12), MON)
ax.set_yticks(range(len(cov.index)), cov.index)
ax.tick_params(length=0)
for s in ax.spines.values():
    s.set_visible(False)
ax.set_xlabel("Month")
save(fig, "fig_coverage.pdf")

# ---------- Fig. B: seasonal profiles of the four strongest candidates ----------
nat = pd.read_csv(OUT / "rq1_commodity_year_month_index.csv")
summ = pd.read_csv(OUT / "rq1_seasonality_summary.csv")
pick = summ[summ.strong_candidate].sort_values("amplitude", ascending=False).head(4)
fig, axes = plt.subplots(2, 2, figsize=(COL, 2.6), sharex=True)
for ax, (_, r) in zip(axes.ravel(), pick.iterrows()):
    g = nat[(nat.commodity_name == r.commodity_name) & (nat.unit == r.unit)]
    piv = g.pivot(index="year", columns="month", values="seasonal_index").reindex(columns=range(1, 13))
    for y, row in piv.iterrows():
        ax.plot(range(1, 13), row.values, color=GREY, lw=0.7)
    ax.plot(range(1, 13), piv.median().values, color=BLUE, lw=1.4, marker="o", ms=2)
    ax.axhline(100, color=INK2, lw=0.4, ls=":")
    ax.set_title(f"{r.commodity_name}\n{int(r.n_divisions)} divisions, r = {r.consistency_across_years:.2f}", pad=2, fontsize=6.5)
    ax.set_xticks(range(1, 13), MON)
    ax.grid(axis="y", color="#e6e5e0", lw=0.4)
fig.supylabel("Seasonal index", fontsize=7.5, x=0.0)
fig.tight_layout(h_pad=0.6, w_pad=0.6)
save(fig, "fig_seasonal.pdf")

# ---------- Fig. C: 2023 -> 2025 change by commodity (>= 3 divisions) ----------
com = pd.read_csv(OUT / "rq3_commodity_changes.csv")
com = com[com.n_divisions >= 3].sort_values("pct_change_2023_2025")
fig, ax = plt.subplots(figsize=(COL, 3.3))
y = np.arange(len(com))
cols = [BLUE if v >= 0 else ORANGE for v in com.pct_change_2023_2025]
ax.barh(y, com.pct_change_2023_2025, color=cols, height=0.62)
ax.axvline(0, color=INK2, lw=0.5)
ax.set_yticks(y, [f"{n} ({int(k)})" for n, k in zip(com.commodity_name, com.n_divisions)])
ax.tick_params(axis="y", length=0)
for yi, v in zip(y, com.pct_change_2023_2025):
    ax.text(v + (2 if v >= 0 else -2), yi, f"{v:+.0f}", va="center", ha="left" if v >= 0 else "right",
            fontsize=5.5, color=INK2)
ax.set_xlim(-62, 105)
ax.set_xlabel("Nominal change, Jul-Oct 2023 to Jul-Oct 2025 (%)")
ax.grid(axis="x", color="#e6e5e0", lw=0.4)
save(fig, "fig_change.pdf")

# ---------- Fig. D: green chilli 2024-2026, divisions and national median ----------
gc = d[(d.commodity_name == "Green chilli") & (d.unit == "kg")]
mm = monthly_medians(gc)
mm["period"] = pd.to_datetime(dict(year=mm.year, month=mm.month, day=1))
mm = mm[mm.period >= "2024-06-01"]
fig, ax = plt.subplots(figsize=(COL, 1.7))
for dv, g in mm.groupby("division"):
    ax.plot(g.period, g.monthly_median_price, color=GREY, lw=0.6)
natl = mm.groupby("period").monthly_median_price.median()
ax.plot(natl.index, natl.values, color=BLUE, lw=1.4, marker="o", ms=2, label="National (median of divisions)")
ax.axvspan(pd.Timestamp("2025-06-16"), pd.Timestamp("2025-11-15"), color=ORANGE, alpha=0.12, lw=0)
ax.text(pd.Timestamp("2025-09-01"), 18, "flagged\nepisode", fontsize=5.5, color=INK2, ha="center")
ax.plot([], [], color=GREY, lw=0.6, label="Individual divisions")
ax.legend(frameon=False, loc="upper center", bbox_to_anchor=(0.5, 1.22), ncol=2)
ax.set_ylabel("BDT per kg"); ax.set_ylim(0, 290)
ax.grid(axis="y", color="#e6e5e0", lw=0.4)
fig.autofmt_xdate(rotation=0, ha="center")
import matplotlib.dates as mdates
ax.xaxis.set_major_locator(mdates.MonthLocator(bymonth=[1, 4, 7, 10]))
ax.xaxis.set_major_formatter(mdates.DateFormatter("%b\n%Y"))
save(fig, "fig_chilli.pdf")
