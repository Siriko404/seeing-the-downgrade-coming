"""Pipeline step 7: test the models year by year on years they never saw (rolling origin, one-year gap).

Goes in:  the panel written by features_v2 (one row per annual report, with the label and every input; the
          example panel from model/synthetic/make_panel.py works too). Only rows with stock-market inputs are used.
Comes out: in OUT_DIR, pooled.csv (one line per model and flag rule: ROC-AUC, PR-AUC, caught and missed
          downgrades, false alarms), per_year.csv, predictions.csv (every test score) and params.json.
Data:     needs no licensed data itself; with the example panel it needs nothing but the panel file.

How one test year Y works (this is the whole idea of the file):
  - Train on reports dated in years <= Y-2. Year Y-1 is left out on purpose (a "one-year gap"): a report from
    year Y-1 has a label that is only known during year Y, so it would not have been known when we scored year Y.
  - Test on reports dated in year Y.
  - The flag line (the score above which a company is flagged) comes from an EARLIER year, not from year Y itself:
    a model trained on years <= Y-4 scores year Y-2, and the line is the score that only the top 10% of those
    reports exceed. Setting the line from the test year's own scores would use information we do not have yet.
  - Settings (for example how strongly the logit is regularised) are chosen once, on validation years that end
    before the first test year, and then frozen.

Models: logistic regression ("logit", with an L2 penalty), histogram gradient boosting, a logit that sees only the
S&P rating state, and the average of the logit and boosting scores. With --zoo it also runs the models of zoo.py
(XGBoost, random forest, neural network, boosting with direction rules, fruit fly networks) and the average of the
non-fly models.
Inputs: the 10-K ratios, the S&P rating state, the market inputs and the inputs of features_v2 (ratio changes, profit
volatility, negative EBITDA, beta, idiosyncratic volatility, first-release economy). The panel must come from
features_v2.

Usage: python -m tcf_credit.evaluate PANEL_CSV OUT_DIR [--first 2016 --last 2024 --flag 0.10]
       [--text] [--drop COL,COL] [--zoo] [--only NAME,NAME] [--tune-end YEAR]
--first, --last: first and last test year. --flag: the share (0.10 = top 10%) of an earlier year's scores that sets
the flag line, and the share the rank rule flags within each test year; the flag line flags more or fewer reports (888
of 6,380 for the logit in the lecture run).
--tune-end: last validation year (default first-2, so every validation outcome is known before the first test year
starts).
"""
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score

RATIOS = ["debt_assets", "ebit_assets", "wc_assets", "ebit_interest", "cfo_debt", "log_assets", "re_assets",
          "cash_assets", "op_margin", "debt_ebitda", "float_debt"]
# years_rated is kept in the panel but not used: it grows with calendar time and the rating file starts at a fixed
# date, so test years tend to have larger values than the training years (our reading, not tested).
RATING = ["notch", "ig", "outlook_neg", "outlook_pos", "watch_neg", "watch_pos", "dg_prev_year", "up_prev_year"]
BINARY = ["dividend_payer"]
MARKET = ["ret_12m", "ret_6m", "vol_12m", "mcap_debt", "dd_naive"]
TEXT = ["lm_neg_chg", "lm_unc_chg"]   # change in Loughran-McDonald negative / uncertainty word shares since the previous 10-K (--text)
EXTRA = []   # filled in main: V2_COLUMNS (the features_v2 inputs) and MARKET always, TEXT with --text


class Prep:
    """Prepare inputs for a model. Everything is learned from the training rows only (no look-ahead): clip extreme
    values at the 1st/99th percentile, fill gaps with the median plus a "was missing" flag, scale, add sector dummies."""

    def __init__(self, numeric, sectors=True, scale=True):
        # numeric: input names; sectors: add sector dummies; scale: standardise (the logit needs it, trees do not)
        self.numeric, self.sectors, self.scale = numeric, sectors, scale

    def fit(self, df):
        # Learn clipping limits, medians, means and spreads from the training rows only.
        x = df[self.numeric].astype(float)
        self.lo, self.hi = x.quantile(0.01), x.quantile(0.99)
        x = x.clip(self.lo, self.hi, axis=1)
        self.empty = x.columns[x.isna().all()]   # empty in this training window (a change column needs two reports, so early years have none)
        self.med = x.median().fillna(0.0)          # gaps are filled with the training median (the logit also gets a missing flag)
        self.mu, self.sd = x.fillna(self.med).mean(), x.fillna(self.med).std().replace(0, 1)
        self.cats = sorted(df["sector"].unique()) if self.sectors else []
        return self

    def transform(self, df, impute=True):
        # Apply what fit learned to any rows (training or test). impute=False keeps gaps as gaps, for tree models.
        x = df[self.numeric].astype(float).clip(self.lo, self.hi, axis=1)
        if not impute and len(self.empty):   # boosting cannot bin a column with no training values: make it constant
            x[self.empty] = 0.0
        out = []
        if impute:
            out.append(x.isna().astype(float).add_suffix("_missing"))
            x = x.fillna(self.med)
            if self.scale:
                x = (x - self.mu) / self.sd
        out.insert(0, x)
        for c in self.cats:
            out.append(pd.DataFrame({f"sector_{c}": (df["sector"] == c).astype(float)}, index=df.index))
        return pd.concat(out, axis=1).to_numpy()


HGB_BASE = dict(early_stopping=True, validation_fraction=0.15, n_iter_no_change=20, max_iter=500, random_state=0)
HGB_GRID = [dict(max_depth=3, learning_rate=0.05, min_samples_leaf=50, l2_regularization=1.0),
            dict(max_depth=2, learning_rate=0.05, min_samples_leaf=100, l2_regularization=1.0),
            dict(max_leaf_nodes=15, learning_rate=0.03, min_samples_leaf=100, l2_regularization=5.0)]
LOGIT_GRID = [dict(C=0.01), dict(C=0.1), dict(C=1.0)]
DROP = []   # features removed by --drop
ZOO = False  # set by --zoo
ONLY = []   # set by --only: keep just these models (averages are computed only from the models kept)


def cols(base):
    """The input names in `base` that were not removed with --drop."""
    return [c for c in base if c not in DROP]


def features():
    """All inputs of the main models: 10-K ratios, rating state, the dividend flag, then EXTRA (set in main)."""
    return cols(RATIOS + RATING + BINARY + EXTRA)


def specs():
    """name -> dict(grid, make(params, cols), cols, impute, sectors[, same_as]). `same_as` reuses another model's choice."""
    feats = features()
    s = {
        "logit": dict(grid=LOGIT_GRID, make=lambda p, c: LogisticRegression(C=p["C"], max_iter=5000),
                      cols=feats, impute=True, sectors=True),
        "boosting": dict(grid=HGB_GRID, make=lambda p, c: HistGradientBoostingClassifier(**HGB_BASE, **p),
                         cols=feats, impute=False, sectors=True),
        "logit_rating_only": dict(grid=LOGIT_GRID, same_as="logit",
                                  make=lambda p, c: LogisticRegression(C=p["C"], max_iter=5000),
                                  cols=cols(RATING), impute=True, sectors=False),
    }
    if ZOO:
        from tcf_credit import zoo
        s.update(zoo.specs(feats))
    s = {k: v for k, v in s.items() if v["cols"]}       # e.g. the rating-only model when the rating inputs are dropped
    if ONLY:
        s = {k: v for k, v in s.items() if k in ONLY}
    for v in s.values():                                 # reuse another model's choice only if that model is in the run
        if v.get("same_as") not in s:
            v.pop("same_as", None)
    return s


def averages(names):
    """Which averages of model scores to report (each is computed from its members' scores in each fold; an average
    has no fitting of its own)."""
    out = {}
    if {"logit", "boosting"} <= set(names):
        out["avg_logit_boosting"] = ["logit", "boosting"]
    members = [n for n in ("logit", "boosting", "boosting_mono", "xgboost", "random_forest", "neural_net") if n in names]
    if ZOO and len(members) > 2:
        out["avg_non_fly"] = members
    return out


def models(params):
    """name -> (make, cols, impute, sectors) with the settings chosen by tune(); used by the rolling loop and score_holdings."""
    out = {}
    for name, sp in specs().items():
        p = params["chosen"][sp.get("same_as", name)]
        out[name] = ((lambda sp=sp, p=p: sp["make"](p, sp["cols"])), sp["cols"], sp["impute"], sp["sectors"])
    return out


def fit_predict(make, cols_, impute, sectors, train, test):
    """Fit on `train` and return (scores on train, scores on test): each score is the model's probability of a downgrade."""
    prep = Prep(cols_, sectors=sectors).fit(train)
    m = make().fit(prep.transform(train, impute), train["label"].to_numpy())
    return m.predict_proba(prep.transform(train, impute))[:, 1], m.predict_proba(prep.transform(test, impute))[:, 1]


def tune(df, first, end=None):
    """Choose each model's setting before the first test year, so no test outcome influences it: for each validation
    year V in end-2..end, train on years <= V-2 and score V, then pick the setting with the best mean average precision
    (PR-AUC). `end` defaults to first-1; main() passes first-2, so every validation label is known before testing."""
    end = first - 1 if end is None else end
    if end >= first:
        raise SystemExit(f"--tune-end {end} must be before the first test year {first}")
    folds = [(df[df.year <= v - 2], df[df.year == v]) for v in range(end - 2, end + 1)]
    folds = [(a, b) for a, b in folds if not b.empty and a.label.nunique() == 2 and b.label.nunique() == 2]
    chosen, scores = {}, {}
    for name, sp in specs().items():
        if sp.get("same_as"):
            continue
        if len(sp["grid"]) == 1:
            chosen[name] = sp["grid"][0]
            continue
        t0 = time.time()
        ap = [float(np.mean([average_precision_score(va.label, fit_predict(
            lambda p=p: sp["make"](p, sp["cols"]), sp["cols"], sp["impute"], sp["sectors"], tr, va)[1])
            for tr, va in folds])) for p in sp["grid"]]
        chosen[name] = sp["grid"][int(np.argmax(ap))]
        scores[name] = ap
        print(f"tuned {name}: {chosen[name]} ({time.time() - t0:.0f}s)", flush=True)
    return {"chosen": chosen, "tuning": {"validation_years": [int(b.year.iloc[0]) for _, b in folds],
                                         "average_precision_by_setting": scores}}


def confusion(f, y):
    """Count the four outcomes of a flag rule: flagged downgrade (TP), false alarm (FP), missed downgrade (FN), quiet non-downgrade (TN)."""
    return dict(flagged=int(f.sum()), TP=int((f & (y == 1)).sum()), FP=int((f & (y == 0)).sum()),
                FN=int((~f & (y == 1)).sum()), TN=int((~f & (y == 0)).sum()))


def main():
    """Read the options, choose the settings, run every test year, write the four result files."""
    global ZOO
    args = sys.argv[1:]
    df = pd.read_csv(args[0])
    out = Path(args[1]); out.mkdir(parents=True, exist_ok=True)
    first = int(args[args.index("--first") + 1]) if "--first" in args else 2016
    last = int(args[args.index("--last") + 1]) if "--last" in args else 2024
    flag = float(args[args.index("--flag") + 1]) if "--flag" in args else 0.10
    tune_end = int(args[args.index("--tune-end") + 1]) if "--tune-end" in args else first - 2
    if "--drop" in args:
        DROP.extend(args[args.index("--drop") + 1].split(","))
    if "--text" in args:
        EXTRA.extend(TEXT)
    from tcf_credit.features_v2 import V2_COLUMNS   # the panel must come from features_v2 (debt_ebitda is already zeroed when EBITDA < 0)
    EXTRA.extend(V2_COLUMNS)
    ZOO = "--zoo" in args
    if "--only" in args:
        ONLY.extend(args[args.index("--only") + 1].split(","))
    EXTRA.extend(MARKET)
    df = df[df.has_prices == 1].copy()          # the market inputs are part of the model, so reports without prices are left out
    df["year"] = pd.to_datetime(df["t"]).dt.year
    df["ebit_interest"] = df["ebit_interest"].clip(-50, 100)     # a tiny interest bill makes this ratio explode
    params = tune(df, first, tune_end)
    ms = models(params)
    avgs = averages(list(ms))
    rows, preds, timing = [], [], {}
    for Y in range(first, last + 1):
        train, test = df[df.year <= Y - 2], df[df.year == Y]
        if test.empty or train.label.nunique() < 2:
            continue
        calib_train, calib = df[df.year <= Y - 4], df[df.year == Y - 2]
        if calib.empty or calib_train.label.nunique() < 2:
            raise SystemExit(f"no calibration data for test year {Y}; start later with --first")
        y = test.label.to_numpy()
        scored = {}
        for name, (make, cols_, impute, sectors) in ms.items():
            t0 = time.time()
            ptr, pte = fit_predict(make, cols_, impute, sectors, train, test)
            _, pcal = fit_predict(make, cols_, impute, sectors, calib_train, calib)
            scored[name] = (ptr, pte, pcal)
            timing[name] = timing.get(name, 0.0) + time.time() - t0
        for name, members in avgs.items():
            scored[name] = tuple(np.mean([scored[m][i] for m in members], axis=0) for i in range(3))
        for name, (ptr, pte, pcal) in scored.items():
            # Rule 1 (calibrated cut, the one the lecture reports): a model trained on years <= Y-4 scores year Y-2 out
            # of sample; the cut flags the top `flag` share of those scores, so the line is set from an earlier year.
            # Rule 2 (rank): flag the riskiest `flag` share within the test year itself (for comparison only).
            f_cut = pte >= np.quantile(pcal, 1 - flag)
            f_rank = pte >= np.quantile(pte, 1 - flag)
            base = dict(year=Y, model=name, n=len(test), downgrades=int(y.sum()),
                        auc=roc_auc_score(y, pte) if y.min() != y.max() else None,
                        train_auc=roc_auc_score(train.label, ptr))
            rows.append({**base, "rule": "calibrated_cut", **confusion(f_cut, y)})
            rows.append({**base, "rule": "rank_top", **confusion(f_rank, y)})
            preds.append(pd.DataFrame({"year": Y, "model": name, "cik": test.cik, "t": test.t, "label": y, "p": pte,
                                       "flag_cut": f_cut, "flag_rank": f_rank}))
        print(f"test year {Y} done", flush=True)
    per_year = pd.DataFrame(rows)
    allp = pd.concat(preds)
    pooled = []
    for name, g in allp.groupby("model", sort=False):
        for rule, col in (("calibrated_cut", "flag_cut"), ("rank_top", "flag_rank")):
            c = confusion(g[col].to_numpy(), g.label.to_numpy())
            tp, fp, fn, tn = c["TP"], c["FP"], c["FN"], c["TN"]
            pooled.append(dict(model=name, rule=rule, n=len(g), downgrades=int(g.label.sum()), base_rate=round(g.label.mean(), 4),
                               roc_auc=round(roc_auc_score(g.label, g.p), 4), pr_auc=round(average_precision_score(g.label, g.p), 4),
                               brier=round(brier_score_loss(g.label, g.p), 4), **c,
                               miss_rate=round(fn / (tp + fn), 3), false_alarm_rate=round(fp / (fp + tn), 3),
                               precision=round(tp / (tp + fp), 3) if tp + fp else None))
    pooled = pd.DataFrame(pooled)
    per_year.to_csv(out / "per_year.csv", index=False)
    pooled.to_csv(out / "pooled.csv", index=False)
    allp.to_csv(out / "predictions.csv", index=False)
    (out / "params.json").write_text(json.dumps({**params, "drop": DROP, "extra": EXTRA, "averages": avgs,
                                                 "seconds_per_model": {k: round(v) for k, v in timing.items()}},
                                                indent=1, default=str))
    print(json.dumps(params["chosen"], default=str))
    print(pooled[pooled.rule == "calibrated_cut"].to_string(index=False))


if __name__ == "__main__":
    main()
