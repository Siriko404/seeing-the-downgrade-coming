"""Pipeline step 8 (compare): does adding or removing inputs change the results?

Goes in:  the folders of two evaluate.py runs on the same panel (for example one run with --drop and one without).
Comes out: for each model both runs have, a printed line with pooled ROC-AUC and PR-AUC in each run, the difference and
          a 95% interval from a firm-clustered bootstrap (whole companies are drawn again with replacement, so a
          firm's years stay together).
Data:     no licensed data; works on the example panel's runs too.
Usage: python -m tcf_credit.compare_runs RUN_A_DIR RUN_B_DIR [--boot 1000]
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, roc_auc_score


def main():
    """For each model present in both runs, print the change in pooled ROC-AUC and PR-AUC with its interval."""
    args = sys.argv[1:]
    a_dir, b_dir = Path(args[0]), Path(args[1])
    n_boot = int(args[args.index("--boot") + 1]) if "--boot" in args else 1000
    a = pd.read_csv(a_dir / "predictions.csv")
    b = pd.read_csv(b_dir / "predictions.csv")
    rng = np.random.default_rng(0)
    for model in sorted(set(a.model) & set(b.model)):
        # Rows are aligned by position (a company number (CIK) can have two reports on one date, so cik + t is not a
        # unique key); the identifying columns must agree row by row, or the two runs are not comparable.
        ra, rb = a[a.model == model].reset_index(drop=True), b[b.model == model].reset_index(drop=True)
        key = ["year", "cik", "t", "label"]
        if len(ra) != len(rb) or not ra[key].equals(rb[key]):
            raise SystemExit(f"{model}: runs are not on the same test snapshots")
        m = ra[key].assign(p_a=ra.p, p_b=rb.p)
        firms = m.cik.unique()
        idx = {f: np.flatnonzero(m.cik.to_numpy() == f) for f in firms}
        y, pa, pb = m.label.to_numpy(), m.p_a.to_numpy(), m.p_b.to_numpy()
        d_auc, d_ap = [], []
        for _ in range(n_boot):
            rows = np.concatenate([idx[f] for f in rng.choice(firms, len(firms))])
            yy = y[rows]
            if yy.min() == yy.max():
                continue
            d_auc.append(roc_auc_score(yy, pb[rows]) - roc_auc_score(yy, pa[rows]))
            d_ap.append(average_precision_score(yy, pb[rows]) - average_precision_score(yy, pa[rows]))
        auc_a, auc_b = roc_auc_score(y, pa), roc_auc_score(y, pb)
        ap_a, ap_b = average_precision_score(y, pa), average_precision_score(y, pb)
        lo, hi = np.percentile(d_auc, [2.5, 97.5])
        alo, ahi = np.percentile(d_ap, [2.5, 97.5])
        print(f"{model}: n {len(m)}, ROC-AUC {auc_a:.4f} -> {auc_b:.4f} (diff {auc_b - auc_a:+.4f}, 95% CI {lo:+.4f}..{hi:+.4f}); "
              f"PR-AUC {ap_a:.4f} -> {ap_b:.4f} (diff {ap_b - ap_a:+.4f}, 95% CI {alo:+.4f}..{ahi:+.4f})")


if __name__ == "__main__":
    main()
