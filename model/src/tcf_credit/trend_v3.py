"""Optional experiment (not part of the main pipeline): do trend inputs help the model?

The question: is a company's risk getting worse or better, and does it KEEP getting worse or better? This file builds
inputs that describe the direction of change and measures, with evaluate.py, whether they improve the results. The
main model does not use them; "v2" below is just the name of the main model's input set (see features_v2).

Goes in:  the panel from features_v2 and the rating-event table. Comes out: a panel with extra columns (build), or an
evaluate.py run that includes them (eval). Data: same as features_v2 (CRSP or the Yahoo stand-in).

Group A, trends in the inputs (all known at t):
  chg2_<ratio>: ratio at t minus the same ratio two original 10-Ks earlier (each step 250 to 500 days, as features_v2).
  n_worse_2: how many of the 7 v2 change ratios got worse in both of the last two steps (leverage and debt/EBITDA up;
    profitability, coverage, cash flow, cash and margin down). Empty without two steps.
  notch_chg_1y, notch_chg_2y: S&P notch at t minus the notch 365 / 730 days before (positive = worse); empty if not
    rated then.
  neg_actions_24m: S&P negative actions in the 730 days before t: downgrades, moves to a negative outlook, placements
    on CreditWatch negative.
  Sources: changes in inputs, Malone, Smales & Liu 2026 and Karas et al. 2025; the rating path, Mizen & Tsoukas 2012
  ("previous states") and Hamilton & Cantor 2004 (outlook). Counting persistence (worse twice in a row) is our own
  extension.
Group B, momentum of the model's own score (nested, no look-ahead):
  For each year y, a logit (main inputs) trained on years <= y-2 scores the snapshots of year y (the same embargo as the
  evaluation). For a snapshot at t: score_prev = that out-of-sample log-odds at the previous 10-K, score_prev_chg =
  previous minus the one before, score_rise_streak = consecutive rises ending at the previous 10-K (0 to 3).
Usage:
  python -m tcf_credit.trend_v3 build PANEL_V2 EVENTS OUT_PANEL
  python -m tcf_credit.trend_v3 eval PANEL OUT_DIR {v2,A,AB,AB_perm} [evaluate options]
Variants for eval: v2 = the main model's inputs only; A = plus the input trends; AB = plus the score momentum;
AB_perm = AB with the new inputs shuffled within each year, a control that should show no gain.
"""
import datetime as dt
import sys

import numpy as np
import pandas as pd

from tcf_credit import build_panel as BP
from tcf_credit.features_v2 import CHG, GAP, V2_COLUMNS

WORSE_UP = {"debt_assets", "debt_ebitda"}          # higher is worse; the other CHG ratios: lower is worse
A_COLS = [f"chg2_{c}" for c in CHG] + ["n_worse_2", "notch_chg_1y", "notch_chg_2y", "neg_actions_24m"]
B_COLS = ["score_prev", "score_prev_chg", "score_rise_streak"]


def input_trends(df: pd.DataFrame) -> pd.DataFrame:
    """Group A, part 1: changes over two reports and the count of ratios that got worse twice in a row."""
    df = df.sort_values(["cik", "t"]).copy()
    parts = {k: [] for k in [f"chg2_{c}" for c in CHG] + ["n_worse_2"]}
    for _, g in df.groupby("cik", sort=False):
        ok1 = g.t.diff().dt.days.between(*GAP)
        ok2 = ok1 & ok1.shift(1, fill_value=False)
        worse = []
        for c in CHG:
            parts[f"chg2_{c}"].append((g[c] - g[c].shift(2)).where(ok2))
            d1, d0 = g[c] - g[c].shift(1), g[c].shift(1) - g[c].shift(2)
            w = (d1 > 0) & (d0 > 0) if c in WORSE_UP else (d1 < 0) & (d0 < 0)
            worse.append(w.where(d1.notna() & d0.notna()))
        n = pd.concat(worse, axis=1)
        parts["n_worse_2"].append(n.sum(axis=1, min_count=1).where(ok2))
    for k, p in parts.items():
        df[k] = pd.concat(p)
    return df.sort_index()


def rating_path(df: pd.DataFrame, events: dict) -> pd.DataFrame:
    """Group A, part 2: how the S&P rating moved over the last one and two years, and the count of negative actions."""
    df = df.copy()
    out = {k: [] for k in ("notch_chg_1y", "notch_chg_2y", "neg_actions_24m")}
    for ob, t, notch in zip(df.obligor, df.t, df.notch):
        ev = events.get(ob, [])
        d = t.date()
        for k, days in (("notch_chg_1y", 365), ("notch_chg_2y", 730)):
            st = BP.rating_state(ev, d - dt.timedelta(days=days))
            out[k].append(notch - st["notch"] if st and st.get("notch") is not None else np.nan)
        n, prev = 0, None
        for e in ev:
            if e[0] >= d:
                break
            if e[0] >= d - dt.timedelta(days=730):
                n += (e[2] == "DG") + (e[3] == "Negative" and (prev is None or prev[3] != "Negative")) + \
                     (e[4] == "WatchNeg" and (prev is None or prev[4] != "WatchNeg"))
            prev = e
        out["neg_actions_24m"].append(n)
    for k, v in out.items():
        df[k] = v
    return df


def score_momentum(df: pd.DataFrame) -> pd.DataFrame:
    """Group B: out-of-sample logit log-odds per report (model on years <= y-2), then per firm the previous ones."""
    from sklearn.linear_model import LogisticRegression
    from tcf_credit import evaluate as E
    cols = E.cols(E.RATIOS + E.RATING + E.BINARY + V2_COLUMNS + E.MARKET)
    d = df[df.has_prices == 1].copy()
    # Same fixed row order as evaluate.main (without resetting the index, which the score series below relies on).
    d = d.sort_values(["t", "cik", "accn"], kind="stable")
    d["ebit_interest"] = d["ebit_interest"].clip(-50, 100)        # as evaluate.main
    oos = pd.Series(np.nan, index=df.index)
    for y in sorted(d.year.unique()):
        tr, te = d[d.year <= y - 2], d[d.year == y]
        if tr.label.nunique() < 2 or te.empty:
            continue
        prep = E.Prep(cols, sectors=True).fit(tr)
        m = LogisticRegression(C=0.1, max_iter=5000).fit(prep.transform(tr, True), tr.label.to_numpy())
        p = np.clip(m.predict_proba(prep.transform(te, True))[:, 1], 1e-6, 1 - 1e-6)
        oos.loc[te.index] = np.log(p / (1 - p))
    df = df.copy()
    df["_oos"] = oos
    df = df.sort_values(["cik", "t"])
    parts = {k: [] for k in B_COLS}
    for _, g in df.groupby("cik", sort=False):
        ok1 = g.t.diff().dt.days.between(*GAP)
        s1 = g._oos.shift(1).where(ok1)
        s2 = g._oos.shift(2).where(ok1 & ok1.shift(1, fill_value=False))
        parts["score_prev"].append(s1)
        parts["score_prev_chg"].append(s1 - s2)
        streak, out = 0, []
        vals, oks = g._oos.tolist(), ok1.tolist()
        for i in range(len(g)):          # rises ending at the previous 10-K
            if i >= 2 and oks[i] and oks[i - 1] and not np.isnan(vals[i - 1]) and not np.isnan(vals[i - 2]):
                streak = min(streak + 1, 3) if vals[i - 1] > vals[i - 2] else 0
            else:
                streak = 0
            out.append(float(streak) if i >= 1 and oks[i] and not np.isnan(vals[i - 1]) else np.nan)
        parts["score_rise_streak"].append(pd.Series(out, index=g.index))
    for k, p in parts.items():
        df[k] = pd.concat(p)
    return df.drop(columns="_oos").sort_index()


def build(panel, events_path, out):
    """Add all trend columns to a features_v2 panel and write it."""
    df = pd.read_csv(panel, dtype={"cik": str})
    df["t"] = pd.to_datetime(df["t"])
    df["year"] = df.t.dt.year
    df = input_trends(df)
    df = rating_path(df, BP.load_events(events_path))
    df = score_momentum(df)
    df["t"] = df.t.dt.strftime("%Y-%m-%d")
    df.drop(columns="year").to_csv(out, index=False)
    print({c: round(float(df[c].notna().mean()), 3) for c in A_COLS + B_COLS})


def run_eval(panel, out, variant, rest):
    """Run evaluate.py with the extra columns of the chosen variant."""
    from tcf_credit import evaluate as E
    new = {"v2": [], "A": A_COLS, "AB": A_COLS + B_COLS, "AB_perm": A_COLS + B_COLS}[variant]
    if variant == "AB_perm":                     # control: the new inputs shuffled within each year
        df = pd.read_csv(panel, dtype={"cik": str})
        rng = np.random.default_rng(20261108)
        yr = pd.to_datetime(df.t).dt.year
        for c in new:
            for y in yr.unique():
                idx = df.index[yr == y]
                df.loc[idx, c] = rng.permutation(df.loc[idx, c].to_numpy())
        panel = str(out).rstrip("/") + "_panel.csv.gz"
        df.to_csv(panel, index=False)
    E.EXTRA.extend(new)
    sys.argv = ["evaluate", panel, out] + rest
    E.main()


if __name__ == "__main__":
    a = sys.argv[1:]
    if a[0] == "build":
        build(*a[1:4])
    elif a[0] == "eval":
        run_eval(a[1], a[2], a[3], a[4:])
    else:
        raise SystemExit(__doc__)
