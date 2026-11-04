"""
RQ5 - Market-wide shocks and unusual periods (nothing is deleted).

For each commodity-unit:
  national monthly price = median across divisions of the division monthly medians
  spike_ratio  = national price / median of the previous 12 months (needs >= 6)
  mom_z        = robust z-score (median/MAD) of the month-on-month log change
A commodity-month is flagged when spike_ratio >= 1.5 (or <= 1/1.5) AND |mom_z| >= 3.5.
For each flag we count how many divisions moved the same way (breadth).
Market-wide: for each month, the share of commodities with month-on-month rises > 10%.

Run:  python rq5_shocks_and_anomalies.py
"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from dam_common import *

SPIKE = 1.5
Z = 3.5
MIN_RUN = 2                # months in a row above/below the level threshold = "sustained"
MIN_DIVISIONS = 3          # ignore commodity-months seen in fewer divisions (single-division noise)
DIV_THRESHOLD = 1.3        # a division "participates" if its price >= 1.3x its own trailing median

df = load_clean()
d = valid_prices(df)
m = monthly_medians(d)
m["period"] = pd.to_datetime(dict(year=m.year, month=m.month, day=1))


def add_trailing(frame, keys, col, name):
    """Median of the previous 12 CALENDAR months (needs >= 6 observed). Missing months
    are respected, so gaps in the data are not silently bridged."""
    frame = frame.sort_values(keys + ["period"]).copy()
    res = pd.Series(np.nan, index=frame.index)
    for _, g in frame.groupby(keys):
        s = g.set_index("period")[col].asfreq("MS")
        t = s.shift(1).rolling(12, min_periods=6).median()
        res.loc[g.index] = t.reindex(g["period"]).values
    frame[name] = res
    return frame


def add_mom(frame, keys, col, name):
    """Month-on-month log change, only between consecutive calendar months."""
    frame = frame.sort_values(keys + ["period"]).copy()
    res = pd.Series(np.nan, index=frame.index)
    for _, g in frame.groupby(keys):
        s = np.log(g.set_index("period")[col].asfreq("MS")).diff()
        res.loc[g.index] = s.reindex(g["period"]).values
    frame[name] = res
    return frame


# ---- division level ----
m = add_trailing(m, SERIES, "monthly_median_price", "trail")
m["div_ratio"] = m["monthly_median_price"] / m["trail"]

# ---- national level ----
nat = m.groupby(["commodity_name", "unit", "period"], as_index=False).agg(
    price=("monthly_median_price", "median"),
    divisions=("division", "nunique"),
    div_up=("div_ratio", lambda s: (s >= DIV_THRESHOLD).sum()),
    div_down=("div_ratio", lambda s: (s <= 1 / DIV_THRESHOLD).sum()),
)
nat = add_trailing(nat, ["commodity_name", "unit"], "price", "trail")
nat["spike_ratio"] = nat["price"] / nat["trail"]
nat = add_mom(nat, ["commodity_name", "unit"], "price", "dlog")


def robust_z(s):
    med = s.median()
    mad = (s - med).abs().median()
    return (s - med) / (1.4826 * mad) if mad > 0 else s * np.nan


nat["mom_z"] = nat.groupby(["commodity_name", "unit"])["dlog"].transform(robust_z)
nat.to_csv(OUT / "rq5_national_monthly_all.csv", index=False)

# Diagnostic: why was (or wasn't) the verified 2025 green chilli spike flagged?
chi = nat[nat["commodity_name"].str.lower().str.contains("chilli")
          & (nat["period"] >= "2025-04-01") & (nat["period"] <= "2025-12-01")]
print("\nGREEN CHILLI DIAGNOSTIC (flag needs spike_ratio >= 1.5 AND |mom_z| >= 3.5):")
print(chi[["commodity_name", "unit", "period", "price", "trail", "spike_ratio", "dlog", "mom_z",
           "divisions"]].to_string(index=False, float_format="{:.2f}".format))

# Two ways a month can be unusual:
#   jump      - level is >= SPIKE x (or <= 1/SPIKE of) its trailing median AND the month-on-month
#               change is a robust outlier (catches the first month of a sudden move)
#   sustained - level stays beyond that threshold for >= MIN_RUN consecutive calendar months
#               (catches an elevated episode after its first month)
nat["level_dir"] = np.select([nat.spike_ratio >= SPIKE, nat.spike_ratio <= 1 / SPIKE], [1, -1], 0)
# Length of the consecutive same-direction block each month belongs to (0 = not beyond threshold).
# Every month in a block of >= MIN_RUN months is "sustained", including the FIRST month.
block = pd.Series(0, index=nat.index)
for _, g in nat.sort_values("period").groupby(["commodity_name", "unit"]):
    vals = g.set_index("period")["level_dir"].asfreq("MS").fillna(0).astype(int)
    v, n, out_b, i = vals.values, len(vals), [0] * len(vals), 0
    while i < n:
        if v[i] == 0:
            i += 1
            continue
        j = i
        while j + 1 < n and v[j + 1] == v[i]:
            j += 1
        for k in range(i, j + 1):
            out_b[k] = j - i + 1
        i = j + 1
    block.loc[g.index] = pd.Series(out_b, index=vals.index).reindex(g["period"]).values
nat["run_length"] = block
nat["jump_flag"] = (nat.level_dir != 0) & (nat.mom_z.abs() >= Z)
nat["sustained_flag"] = nat.run_length >= MIN_RUN
nat.to_csv(OUT / "rq5_national_monthly_all.csv", index=False)

flag = nat[(nat.jump_flag | nat.sustained_flag) & (nat.divisions >= MIN_DIVISIONS)].copy()
flag["type"] = np.select([flag.jump_flag & flag.sustained_flag, flag.jump_flag], ["both", "jump"], "sustained")
flag["direction"] = np.where(flag.spike_ratio >= 1, "up", "down")
flag["div_breadth"] = np.where(flag.direction == "up", flag.div_up, flag.div_down) / flag.divisions
flag = flag.sort_values("spike_ratio", ascending=False)
flag.to_csv(OUT / "rq5_flagged_commodity_months.csv", index=False)
print(f"Flagged commodity-months: {len(flag)}  (up: {(flag.direction=='up').sum()}, "
      f"down: {(flag.direction=='down').sum()})")
print(flag[["commodity_name", "unit", "period", "price", "trail", "spike_ratio", "mom_z",
            "divisions", "div_breadth", "type"]].head(25).to_string(index=False, float_format="{:.2f}".format))

# ---- episodes: group consecutive flagged months per commodity ----
flag = flag.sort_values(["commodity_name", "unit", "period"])
_g = flag.groupby(["commodity_name", "unit"])
# a new episode starts after a gap of more than ~2 months OR when the direction flips
flag["gap"] = (_g["period"].diff().dt.days.gt(62) | (_g["direction"].shift() != flag["direction"]))
flag["episode"] = flag.groupby(["commodity_name", "unit"])["gap"].cumsum()
eps = flag.groupby(["commodity_name", "unit", "episode"]).agg(
    start=("period", "min"), end=("period", "max"), months=("period", "nunique"),
    direction=("direction", "first"), peak_ratio=("spike_ratio", lambda s: s.max() if s.max() >= 1 else s.min()),
    median_breadth=("div_breadth", "median"),
    peak_price=("price", "max"), min_price=("price", "min"),
).reset_index().sort_values("start")
eps.to_csv(OUT / "rq5_episodes.csv", index=False)

# ---- market-wide: breadth across commodities ----
nat["rise10"] = nat["dlog"] > np.log(1.10)
nat["fall10"] = nat["dlog"] < -np.log(1.10)
mk = nat.dropna(subset=["dlog"]).groupby("period").agg(
    commodities=("dlog", "size"),
    median_mom_pct=("dlog", lambda s: (np.exp(s.median()) - 1) * 100),
    share_rising_10pct=("rise10", "mean"),
    share_falling_10pct=("fall10", "mean"),
).reset_index()
mk = mk[mk["commodities"] >= min(10, max(3, int(0.5 * mk["commodities"].max())))]
mk.to_csv(OUT / "rq5_market_wide_monthly.csv", index=False)
print("\nMonths with the broadest increases:")
print(mk.sort_values("share_rising_10pct", ascending=False).head(10).to_string(index=False, float_format="{:.3f}".format))

# ---- verified green chilli episode, shown against its divisions ----
gc = m[m["commodity_name"].str.lower().str.contains("green") &
       m["commodity_name"].str.lower().str.contains("chil")]
if not gc.empty:
    fig, ax = plt.subplots(figsize=(9, 4))
    for dv, s in gc[gc.period >= "2024-01-01"].groupby("division"):
        ax.plot(s["period"], s["monthly_median_price"], lw=1, label=dv)
    ax.set_ylabel("Monthly median price (BDT per unit)")
    ax.legend(fontsize=7, ncol=2)
    ax.set_title("Green chilli by division (verified 2025 spike kept in data)")
    save_fig(fig, "rq5_green_chilli_divisions.png")

fig, ax = plt.subplots(figsize=(9, 3.5))
ax.plot(mk["period"], mk["share_rising_10pct"], label="share rising >10%")
ax.plot(mk["period"], mk["share_falling_10pct"], label="share falling >10%")
ax.set_ylabel("Share of commodities")
ax.legend()
save_fig(fig, "rq5_market_breadth.png")
