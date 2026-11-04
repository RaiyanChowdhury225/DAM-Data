"""
RQ2 - Ramadan / Eid price patterns (descriptive association, NOT causal).

DATA REALITY: usable weekly data is only 2024 (partial), 2025 (full) and 2026 (partial),
plus a few 2023 months. So only ~2-3 Ramadan/Eid cycles can be observed. Results are
EXPLORATORY and the script prints exactly which event-years each window covers.

Per commodity-unit:
  1. Weekly median price per division series (log), minus the series-year mean.
  2. Average across divisions -> one weekly deviation y_t.
  3. Regress y_t on event-window dummies + month-of-year dummies, Newey-West (4 lags) SEs.
     Reference = weeks outside all windows.
  4. Also report the raw (uncontrolled) difference: mean y inside window minus outside.
  5. Benjamini-Hochberg correction across all commodity x window tests.
  A window is estimated only if it is observed (>= MIN_WEEKS_IN_WINDOW weeks) in at least
  MIN_EVENT_YEARS different event years.

Windows (mutually exclusive, on the week's mid-date):
  ramadan_pre  28 days before Ramadan | ramadan  Ramadan except last 14 days
  fitr_pre     last 14 days before Eid-ul-Fitr | fitr_post  Eid + next 27 days
  adha_pre     14 days before Eid-ul-Adha      | adha_post  Eid + next 13 days

DATES: computed from the Umm al-Qura calendar (pip install hijridate). Bangladesh uses
local moon sighting, so dates may differ by ~1 day. Put verified dates in
data/external/religious_dates_verified.csv (columns: ramadan_start, eid_fitr, eid_adha)
and the script will use that instead.

Run:  python rq2_holiday_effects.py
"""
import numpy as np
import pandas as pd
import statsmodels.api as sm
from statsmodels.stats.multitest import multipletests

from dam_common import *

MIN_WEEKS = 60               # total weeks needed per commodity-unit
MIN_EVENT_YEARS = 2          # a window must be observed in >= this many separate years
MIN_WEEKS_IN_WINDOW = 2      # weeks a commodity needs inside a window-year to count it
MIN_SERIES_YEAR_WEEKS = 20   # weeks a series-year needs to be used at all
WINDOWS = ["ramadan_pre", "ramadan", "fitr_pre", "fitr_post", "adha_pre", "adha_post"]

# ---------------- 1. event dates ----------------
verified = EXT / "religious_dates_verified.csv"
if verified.exists():
    ev = pd.read_csv(verified, parse_dates=["ramadan_start", "eid_fitr", "eid_adha"])
    print(f"Using VERIFIED dates from {verified}")
else:
    try:
        from hijridate import Hijri
    except ImportError:
        try:
            from hijri_converter import Hijri
        except ImportError:
            raise SystemExit("Run:  pip install hijridate   (or supply the verified CSV)")
    ev = pd.DataFrame([{
        "ramadan_start": pd.Timestamp(Hijri(h, 9, 1).to_gregorian()),
        "eid_fitr": pd.Timestamp(Hijri(h, 10, 1).to_gregorian()),
        "eid_adha": pd.Timestamp(Hijri(h, 12, 10).to_gregorian()),
    } for h in range(1441, 1449)])
    ev["note"] = "Umm al-Qura calculation; Bangladesh may differ by ~1 day. VERIFY."
    ev.to_csv(EXT / "religious_dates_approx.csv", index=False)
    print(f"Approximate dates written to {EXT / 'religious_dates_approx.csv'} - please verify.")
    print(ev[["ramadan_start", "eid_fitr", "eid_adha"]].to_string(index=False))

D = pd.Timedelta


def build_intervals(events, shift_days=0):
    """Event windows; shift_days > 0 moves every date later (used for placebo tests)."""
    iv = []   # (label, start, end, event_year) in PRIORITY order
    sh = D(days=shift_days)
    for _, r in events.iterrows():
        rs, ef, ea = r["ramadan_start"] + sh, r["eid_fitr"] + sh, r["eid_adha"] + sh
        ky, ka = rs.year, ea.year
        iv += [
            ("fitr_pre", ef - D(days=14), ef - D(days=1), ky),
            ("ramadan", rs, ef - D(days=15), ky),
            ("ramadan_pre", rs - D(days=28), rs - D(days=1), ky),
            ("fitr_post", ef, ef + D(days=27), ky),
            ("adha_pre", ea - D(days=14), ea - D(days=1), ka),
            ("adha_post", ea, ea + D(days=13), ka),
        ]
    return iv


def label_weeks(mid, intervals):
    lab = pd.Series("none", index=mid.index, dtype=object)
    yr = pd.Series(np.nan, index=mid.index)
    for name, st, en, k in intervals:
        hit = (mid >= st) & (mid <= en) & (lab == "none")
        lab[hit] = name
        yr[hit] = k
    return lab, yr


# ---------------- 2. weekly deviation series ----------------
df = load_clean()
d = valid_prices(df)
d["week"] = d["parsed_date"].dt.to_period("W").dt.start_time
w = d.groupby(SERIES + ["week"], as_index=False).agg(p=("midpoint_price", "median"))
w["logp"] = np.log(w["p"])
w["year"] = w["week"].dt.year
w["n"] = w.groupby(SERIES + ["year"])["logp"].transform("size")
w = w[w["n"] >= MIN_SERIES_YEAR_WEEKS].copy()
if w.empty:
    raise SystemExit("No series-year has enough weekly data.")
w["y"] = w["logp"] - w.groupby(SERIES + ["year"])["logp"].transform("mean")

cw = w.groupby(["commodity_name", "unit", "week"], as_index=False).agg(
    y=("y", "mean"), n_div=("division", "nunique"))
cw["mid"] = cw["week"] + D(days=3)
cw["month"] = cw["mid"].dt.month
cw0 = cw.copy()

def estimate(intervals, show_coverage=False):
    cw = cw0.copy()
    cw["window"], cw["event_year"] = label_weeks(cw["mid"], intervals)
    if show_coverage:
        print("\nCOVERAGE: distinct weeks observed in each window, by event year")
        cov = cw[cw.window != "none"].groupby(["window", "event_year"])["week"].nunique().unstack(fill_value=0)
        print(cov.reindex(WINDOWS).fillna(0).astype(int).to_string())
    out = []
    for (com, unit), g in cw.groupby(["commodity_name", "unit"]):
        g = g.sort_values("week")
        if len(g) < MIN_WEEKS:
            continue
        wins = []
        for x in WINDOWS:
            cnt = g[g.window == x].groupby("event_year").size()
            if (cnt >= MIN_WEEKS_IN_WINDOW).sum() >= MIN_EVENT_YEARS:
                wins.append(x)
        if not wins:
            continue
        X = pd.DataFrame({x: (g["window"] == x).astype(float) for x in wins}, index=g.index)
        X = pd.concat([X, pd.get_dummies(g["month"], prefix="m", drop_first=True).astype(float)], axis=1)
        X = sm.add_constant(X)
        if len(g) <= X.shape[1] + 10:
            continue
        fit = sm.OLS(g["y"], X).fit(cov_type="HAC", cov_kwds={"maxlags": 4})
        for x in wins:
            b, se = fit.params[x], fit.bse[x]
            inside = g.loc[g.window == x, "y"].mean()
            outside = g.loc[g.window == "none", "y"].mean()
            out.append({
                "commodity_name": com, "unit": unit, "window": x,
                "raw_pct_diff": (np.exp(inside - outside) - 1) * 100,
                "pct_effect": (np.exp(b) - 1) * 100,
                "ci_low_pct": (np.exp(b - 1.96 * se) - 1) * 100,
                "ci_high_pct": (np.exp(b + 1.96 * se) - 1) * 100,
                "p_value": fit.pvalues[x],
                "weeks_in_window": int((g["window"] == x).sum()),
                "event_years": int((g[g.window == x].groupby("event_year").size() >= MIN_WEEKS_IN_WINDOW).sum()),
                "total_weeks": len(g), "avg_divisions": g["n_div"].mean(),
            })
    if not out:
        return pd.DataFrame()
    r = pd.DataFrame(out)
    r["q_BH"] = multipletests(r["p_value"], method="fdr_bh")[1]
    r["significant_q05"] = r["q_BH"] < 0.05
    return r


# ---------------- 3. real event dates ----------------
res = estimate(build_intervals(ev), show_coverage=True)
if res.empty:
    raise SystemExit("No commodity-window met the coverage rules. See the COVERAGE table above; "
                     "lower MIN_EVENT_YEARS / MIN_WEEKS or recover more years of data.")
res = res.sort_values(["window", "p_value"])
res.to_csv(OUT / "rq2_holiday_effects_by_commodity.csv", index=False)

summary = res.groupby("window").agg(
    commodities=("commodity_name", "size"),
    median_raw_pct=("raw_pct_diff", "median"),
    median_adj_pct=("pct_effect", "median"),
    share_positive=("pct_effect", lambda s: (s > 0).mean()),
    n_sig_q05=("significant_q05", "sum"),
).reset_index()
summary["n_sig_positive"] = summary["window"].map(
    res[res.significant_q05 & (res.pct_effect > 0)].groupby("window").size()).fillna(0).astype(int)
summary.to_csv(OUT / "rq2_holiday_summary_by_window.csv", index=False)

print("\nSUMMARY (raw = no controls; adj = controls for month of year; vs non-event weeks)")
print(summary.to_string(index=False, float_format="{:.2f}".format))
sig = res[res.significant_q05]
print(f"\nSignificant after FDR (q<0.05): {len(sig)}")
if len(sig):
    print(sig.reindex(sig.pct_effect.abs().sort_values(ascending=False).index).head(20)[
        ["commodity_name", "unit", "window", "pct_effect", "ci_low_pct", "ci_high_pct", "q_BH", "event_years"]
    ].to_string(index=False, float_format="{:.2f}".format))
# ---------------- 4. PLACEBO TEST ----------------
# Same model, but every event window is moved by 120-240 days to dates with no religious
# event. Any "significant" placebo result is noise/seasonal artefact. If placebo results are
# about as common as real ones, the real ones cannot be distinguished from noise.
rows = [{"run": "REAL DATES", "tests": len(res), "p_below_05_share": (res.p_value < .05).mean(),
         "q_below_05": int(res.significant_q05.sum()), "q_below_05_share": res.significant_q05.mean()}]
for sh in [120, 150, 180, 210, 240]:
    pr = estimate(build_intervals(ev, shift_days=sh))
    if pr.empty:
        continue
    rows.append({"run": f"placebo +{sh} days", "tests": len(pr),
                 "p_below_05_share": (pr.p_value < .05).mean(),
                 "q_below_05": int(pr.significant_q05.sum()), "q_below_05_share": pr.significant_q05.mean()})
plc = pd.DataFrame(rows)
plc.to_csv(OUT / "rq2_placebo_summary.csv", index=False)
print("\nPLACEBO TEST (real event dates vs. dates shifted to non-event periods)")
print(plc.to_string(index=False, float_format="{:.2f}".format))
print("If placebo shares are similar to the real-date row, the 'significant' results are not "
      "evidence of a holiday effect.")

print("\nEXPLORATORY: associations from only a few event cycles, not causal effects. Ramadan "
      "moves ~11 days earlier each year, so with 2-3 years it is only weakly separable from "
      "calendar month; expect wide intervals.")
