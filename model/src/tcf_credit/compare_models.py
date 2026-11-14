"""Pipeline step 8 (compare): is any model really better than the main model (the logit)?

Goes in:  the folder of one evaluate.py run (its predictions.csv and pooled.csv).
Comes out: comparison.csv and a printed table: each model's pooled ROC-AUC and PR-AUC, its difference from the
          reference model, and a 95% interval for that difference.
Data:     no licensed data; needs nothing but the run folder.

The reference model (default: logit) was named the main model before the extra models were run (its inputs were extended
later), so the comparison asks "does anything beat the one model we named first?" and not "which of many models looks
best?". The interval comes from a firm-clustered bootstrap: whole companies are drawn again with replacement, so a
firm's several years stay together (its years are not independent). The same draws are used for every model, which makes
the differences comparable.
Usage: python -m tcf_credit.compare_models RUN_DIR [--ref logit] [--boot 2000] [--out comparison.csv]
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, roc_auc_score


def main():
    """Draw the bootstrap samples once, then score every model on the same draws."""
    args = sys.argv[1:]
    run = Path(args[0])
    ref = args[args.index("--ref") + 1] if "--ref" in args else "logit"
    n_boot = int(args[args.index("--boot") + 1]) if "--boot" in args else 2000
    out = Path(args[args.index("--out") + 1]) if "--out" in args else run / "comparison.csv"
    p = pd.read_csv(run / "predictions.csv")
    pooled = pd.read_csv(run / "pooled.csv")
    pooled = pooled[pooled.rule == "calibrated_cut"].set_index("model")
    key = ["year", "cik", "t", "label"]
    r = p[p.model == ref].reset_index(drop=True)
    firms = r.cik.unique()
    idx = {f: np.flatnonzero(r.cik.to_numpy() == f) for f in firms}
    rng = np.random.default_rng(0)
    samples = [np.concatenate([idx[f] for f in rng.choice(firms, len(firms))]) for _ in range(n_boot)]
    samples = [s for s in samples if r.label.to_numpy()[s].min() != r.label.to_numpy()[s].max()]
    y = r.label.to_numpy()
    pr = r.p.to_numpy()
    base_auc = np.array([roc_auc_score(y[s], pr[s]) for s in samples])
    base_ap = np.array([average_precision_score(y[s], pr[s]) for s in samples])
    rows = []
    for model, g in p.groupby("model", sort=False):
        g = g.reset_index(drop=True)
        if not g[key].equals(r[key]):
            raise SystemExit(f"{model}: not on the same test snapshots as {ref}")
        pm = g.p.to_numpy()
        d_auc = np.array([roc_auc_score(y[s], pm[s]) for s in samples]) - base_auc
        d_ap = np.array([average_precision_score(y[s], pm[s]) for s in samples]) - base_ap
        auc, ap = roc_auc_score(y, pm), average_precision_score(y, pm)
        c = pooled.loc[model]
        rows.append(dict(model=model, roc_auc=round(auc, 4), auc_diff=round(auc - roc_auc_score(y, pr), 4),
                         auc_lo=round(np.percentile(d_auc, 2.5), 4), auc_hi=round(np.percentile(d_auc, 97.5), 4),
                         pr_auc=round(ap, 4), ap_diff=round(ap - average_precision_score(y, pr), 4),
                         ap_lo=round(np.percentile(d_ap, 2.5), 4), ap_hi=round(np.percentile(d_ap, 97.5), 4),
                         caught=int(c.TP), false_alarm_rate=c.false_alarm_rate))
    df = pd.DataFrame(rows).sort_values("roc_auc", ascending=False)
    df.to_csv(out, index=False)
    print(f"reference {ref}; {len(samples)} firm-clustered resamples of {len(firms)} companies")
    print(df.to_string(index=False))


if __name__ == "__main__":
    main()
