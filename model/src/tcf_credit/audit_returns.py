"""Pipeline step 9b (LICENSED data): audit the extreme 12-month winners of a returns.py run: real price moves or data
errors?

Goes in:  the returns.py output folder, the CRSP folder, and the CRSP stock-names file. Comes out: audit_summary.json
(counts) and audit_detail.csv (firm-level, licensed: keep private). Data: needs CRSP.

For every snapshot whose stock return over the 12 months after t is at least --min-growth times (default 4x), checks
the CRSP rows behind it. Pass/fail checks:
  recompute   compounding the daily returns again gives the same 12-month return (skipped if delisted in the window);
  price_path  the compounded return agrees with the split-adjusted price change (|prc| / cfacpr) from the last price on
              or before t to the last price in the window: (1 + return) / price change between 0.95 and 1.5 (dividends
              can only add);
  big_days    every day with |ret| > 50% matches its own adjusted price change within 10%;
  coverage    at most 5% of the window's trading days have a missing return (missing days count as 0%);
  identity    on t the security's CRSP share code is 10 or 11 (our reading: ordinary common shares) in the CRSP name
              history;
  unique      no duplicated (permno, date) rows in the window.
Described, not judged: start price under $1 and under $5, the largest single-day return, the share of the 12-month
log return made on that one day, flagged or not, downgraded or not, test year.
Firm-level rows go to OUT_DIR/audit_detail.csv only (CRSP-derived, licensed: never publish it);
the printed summary and OUT_DIR/audit_summary.json hold counts and pooled figures only.
Usage: python -m tcf_credit.audit_returns RETURNS_OUT_DIR CRSP_DIR STOCKNAMES_PARQUET OUT_DIR [--min-growth 4]
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

BIG_DAY = 0.5


def audit_one(row, g: pd.DataFrame, names: pd.DataFrame) -> dict:
    """Run the six checks (listed above) on one snapshot. row: the snapshot (permno, t, fwd_ret_12m, delisted_12m);
    g: that stock's CRSP rows sorted by date."""
    end = row.t + pd.DateOffset(months=12)
    win = g[(g.date > row.t) & (g.date <= end)]
    out = dict(window_days=len(win))
    out["unique"] = not win.date.duplicated().any()
    out["coverage"] = bool(len(win)) and win.ret.isna().mean() <= 0.05
    growth = float(np.prod(1 + win.ret.fillna(0.0).to_numpy()))
    out["recompute"] = None if row.delisted_12m else abs(growth - 1 - row.fwd_ret_12m) < 1e-6
    adj = (g.prc.abs() / g.cfacpr).where(g.prc.abs() > 0)
    before = adj[(g.date <= row.t)].dropna()
    inside = adj[(g.date > row.t) & (g.date <= end)].dropna()
    if len(before) and len(inside) and not row.delisted_12m:
        ratio = growth / (inside.iloc[-1] / before.iloc[-1])
        out["price_path"] = 0.95 <= ratio <= 1.5
        out["growth_over_price_change"] = round(float(ratio), 4)
    else:
        out["price_path"] = None
    adj_all = adj.to_numpy()
    ok = True
    pos = np.flatnonzero(((g.date > row.t) & (g.date <= end)).to_numpy() & (g.ret.abs() > BIG_DAY).to_numpy())
    for i in pos:
        if i == 0 or not np.isfinite(adj_all[i]) or not np.isfinite(adj_all[i - 1]):
            ok = False
            continue
        implied = adj_all[i] / adj_all[i - 1] - 1
        ok &= abs((1 + g.ret.iloc[i]) / (1 + implied) - 1) <= 0.10
    out["big_days"] = bool(ok)
    out["big_day_count"] = int(len(pos))
    n = names[(names.permno == row.permno) & (names.namedt <= row.t) & (names.nameenddt >= row.t)]
    out["identity"] = bool(len(n)) and bool(n.shrcd.isin([10, 11]).all())
    p0 = g.prc.abs()[g.date <= row.t].dropna()
    out["start_price"] = float(p0.iloc[-1]) if len(p0) else np.nan
    r = win.ret.dropna()
    out["max_day_ret"] = float(r.max()) if len(r) else np.nan
    total_log = np.log(growth) if growth > 0 else np.nan
    out["max_day_share_of_log_return"] = float(np.log1p(r.max()) / total_log) if len(r) and total_log > 0 else np.nan
    return out


def main():
    """Pick the extreme winners, audit each one, and write the detail table and the summary."""
    args = sys.argv[1:]
    ret_dir, crsp, names_path, out = Path(args[0]), Path(args[1]), Path(args[2]), Path(args[3])
    min_growth = float(args[args.index("--min-growth") + 1]) if "--min-growth" in args else 4.0
    out.mkdir(parents=True, exist_ok=True)
    snap = pd.read_csv(ret_dir / "snapshot_returns.csv", parse_dates=["t"])
    ext = snap[1 + snap.fwd_ret_12m >= min_growth].copy()
    daily = pd.read_parquet(crsp / "crsp_daily.parquet", columns=["permno", "date", "prc", "ret", "cfacpr"])
    daily = daily[daily.permno.isin(set(ext.permno))].sort_values(["permno", "date"])
    daily["date"] = pd.to_datetime(daily.date)
    names = pd.read_parquet(names_path, columns=["permno", "namedt", "nameenddt", "shrcd"])
    names["namedt"] = pd.to_datetime(names.namedt)
    names["nameenddt"] = pd.to_datetime(names.nameenddt)
    by = {p: g.reset_index(drop=True) for p, g in daily.groupby("permno")}
    rows = []
    for row in ext.itertuples():
        g = by.get(row.permno)
        res = audit_one(row, g, names) if g is not None else dict(missing_crsp=True)
        rows.append(dict(cik=row.cik, permno=row.permno, t=row.t.date(), year=row.year, flag=row.flag, label=row.label,
                         fwd_ret_12m=row.fwd_ret_12m, delisted_12m=row.delisted_12m, **res))
    det = pd.DataFrame(rows)
    det.to_csv(out / "audit_detail.csv", index=False)

    checks = ["recompute", "price_path", "big_days", "coverage", "identity", "unique"]
    summ = {"min_growth": min_growth, "snapshots": len(snap), "extreme_snapshots": len(det),
            "extreme_firms": int(det.cik.nunique()), "at_least_10x": int((1 + det.fwd_ret_12m >= 10).sum()),
            "checks": {}}
    for c in checks:
        v = det[c] if c in det else pd.Series(dtype=object)
        summ["checks"][c] = {"pass": int((v == True).sum()), "fail": int((v == False).sum()),  # noqa: E712
                             "not_applicable": int(v.isna().sum())}
    judged = det[checks].apply(lambda r: all(x is not False for x in r), axis=1)
    summ["all_checks_pass"] = int(judged.sum())
    summ["described"] = {
        "flagged": int(det.flag.sum()), "downgraded": int(det.label.sum()),
        "start_price_under_1": int((det.start_price < 1).sum()), "start_price_under_5": int((det.start_price < 5).sum()),
        "with_a_day_over_50pct": int((det.big_day_count > 0).sum()),
        "median_share_of_log_return_on_best_day": round(float(det.max_day_share_of_log_return.median()), 3),
        "by_test_year": det.groupby("year").size().astype(int).to_dict(),
        "flagged_by_test_year": det[det.flag == 1].groupby("year").size().astype(int).to_dict()}
    # How much of the pooled raw flagged-minus-unflagged mean comes from these snapshots.
    d = snap.dropna(subset=["ex_12m"])
    keep = ~d.index.isin(ext.index)
    diff = lambda x: x[x.flag == 1].ex_12m.mean() - x[x.flag == 0].ex_12m.mean()
    summ["raw_mean_diff_12m"] = {"all": round(float(diff(d)), 4), "without_extreme": round(float(diff(d[keep])), 4),
                                 "flagged_mean_without_extreme": round(float(d[keep & (d.flag == 1)].ex_12m.mean()), 4),
                                 "unflagged_mean_without_extreme": round(float(d[keep & (d.flag == 0)].ex_12m.mean()), 4)}
    (out / "audit_summary.json").write_text(json.dumps(summ, indent=1, default=str))
    print(json.dumps(summ, indent=1, default=str))


if __name__ == "__main__":
    main()
