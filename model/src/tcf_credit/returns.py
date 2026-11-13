"""Pipeline step 9 (LICENSED data): do the model's flags predict stock returns after the report? (economic value test)

Goes in:  the folder of an evaluate.py run, the panel (it holds the stock identifier and past returns) and the CRSP
          folder with crsp_daily.parquet, crsp_delist.csv and crsp_vwretd.csv (fetch_crsp, fetch_crsp_delist).
Comes out: snapshot_returns.csv (firm-level, licensed: keep private) and returns_report.json (pooled figures).
Data:     needs CRSP (licensed). The Yahoo stand-in has no delisting returns, so it cannot run this step properly.

A flag is a reason to look, not a reason to sell: this step measures whether flagged stocks did worse than the market.

For every test snapshot of an evaluate.py run (default model: the main model, the logit), the stock's compounded CRSP
return over the trading days after t (t itself excluded, since the 10-K was filed the day before) up to 3, 6 and 12
months later, minus the CRSP value-weighted market return (vwretd) over the same days.
Delisting: the delisting return is added on the delisting day; if it is missing for a performance-related delisting
(codes 500-599, as this code reads them) it is set to -30% (this code's default; --missing-delist changes it, e.g.
-0.55 for Nasdaq stocks as in Shumway and Warther 1999); after delisting the position earns nothing.
Reported:
  1. mean and median excess return of flagged and unflagged snapshots, and the difference;
  2. the difference within each test year, averaged (removes common year effects);
  3. a regression of the 12-month excess return on the flag with controls known at t (past 12-month return, volatility,
     log market value) and year effects;
  each as raw excess returns, winsorised at 1%/99%, and medians;
  4. mean (winsorised) and median 12-month excess return by score decile, with the deciles drawn within each test year;
  5. median 12-month excess return of the snapshots that were, and were not, downgraded within 12 months (hindsight, for
     context only).
Intervals: firm-clustered bootstrap (companies resampled; a firm's years move together) and, as a second view,
a year-block bootstrap (test years resampled; all snapshots of a year move together, so a market-wide year counts once).
Usage: python -m tcf_credit.returns RUN_DIR PANEL_CSV CRSP_DIR OUT_DIR [--model logit] [--boot 2000]
       [--missing-delist -0.30]
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HORIZONS = {"3m": 3, "6m": 6, "12m": 12}
SHUMWAY = -0.30


def forward_returns(snap: pd.DataFrame, daily: pd.DataFrame, delist: pd.DataFrame, vw: pd.Series,
                    missing_delist: float = SHUMWAY) -> pd.DataFrame:
    """snap: rows with permno and t. Adds fwd_ret_{h} (stock), fwd_mkt_{h} (market), ex_{h} = stock - market,
    delisted_{h}. Names never clash with the panel's past-return columns. missing_delist: the return used when a
    performance-related delisting (codes 500-599) has no delisting return."""
    dl = delist.copy()
    dl["dlret"] = np.where(dl.dlret.isna() & dl.dlstcd.between(500, 599), missing_delist, dl.dlret)
    dl = dl.dropna(subset=["dlret"])
    by_permno = {p: g.set_index("date") for p, g in daily.groupby("permno")}
    dl_by = {p: g.set_index("date").dlret for p, g in dl.groupby("permno")}
    vw_log = np.log1p(vw.fillna(0.0)).cumsum()
    out = []
    for row in snap.itertuples():
        res = {}
        g = by_permno.get(row.permno)
        for name, months in HORIZONS.items():
            end = row.t + pd.DateOffset(months=months)
            r = np.nan
            delisted = 0
            if g is not None:
                days = g.loc[(g.index > row.t) & (g.index <= end), "ret"]
                if len(days):
                    daily_r = days.fillna(0.0)
                    d = dl_by.get(row.permno)
                    if d is not None:
                        hit = d[(d.index > row.t) & (d.index <= end)]
                        if len(hit):
                            delisted = 1
                            day = hit.index[0]
                            if day in daily_r.index:
                                daily_r.loc[day] = (1 + daily_r.loc[day]) * (1 + hit.iloc[0]) - 1
                            else:
                                daily_r = pd.concat([daily_r, pd.Series([hit.iloc[0]], index=[day])]).sort_index()
                            daily_r = daily_r[daily_r.index <= day]
                    r = float(np.prod(1 + daily_r.to_numpy()) - 1)
            a = vw_log[vw_log.index <= row.t]
            b = vw_log[vw_log.index <= end]
            m = float(np.exp(b.iloc[-1] - a.iloc[-1]) - 1) if len(a) and len(b) else np.nan
            res.update({f"fwd_ret_{name}": r, f"fwd_mkt_{name}": m, f"ex_{name}": r - m, f"delisted_{name}": delisted})
        out.append(res)
    res = pd.concat([snap.reset_index(drop=True), pd.DataFrame(out)], axis=1)
    if res.columns.duplicated().any():
        raise ValueError(f"duplicate columns: {list(res.columns[res.columns.duplicated()])}")
    return res


def boot_ci(stat, df, firms_idx, firms, rng, n):
    """95% interval of a statistic: resample the groups in `firms` (whole companies, or whole years) n times."""
    vals = []
    for _ in range(n):
        rows = np.concatenate([firms_idx[f] for f in rng.choice(firms, len(firms))])
        v = stat(df.iloc[rows])
        if np.isfinite(v):
            vals.append(v)
    return float(np.percentile(vals, 2.5)), float(np.percentile(vals, 97.5))


def ols_flag(df, y="ex_12m"):
    """Regression coefficient on the flag, controlling for past return, volatility, size and year."""
    d = df.dropna(subset=[y, "past_ret_12m", "vol_12m", "log_mv"])
    x = pd.concat([d[["flag", "past_ret_12m", "vol_12m", "log_mv"]].astype(float),
                   pd.get_dummies(d.year, prefix="y", dtype=float)], axis=1).to_numpy()
    beta, *_ = np.linalg.lstsq(x, d[y].to_numpy(), rcond=None)
    return float(beta[0])


def main():
    """Attach the later stock returns to the flagged and unflagged reports and write the comparison."""
    args = sys.argv[1:]
    run, panel_csv, crsp, out = Path(args[0]), args[1], Path(args[2]), Path(args[3])
    model = args[args.index("--model") + 1] if "--model" in args else "logit"
    n_boot = int(args[args.index("--boot") + 1]) if "--boot" in args else 2000
    missing_delist = float(args[args.index("--missing-delist") + 1]) if "--missing-delist" in args else SHUMWAY
    out.mkdir(parents=True, exist_ok=True)
    pred = pd.read_csv(run / "predictions.csv")
    pred = pred[pred.model == model].copy()
    panel = pd.read_csv(panel_csv, usecols=["cik", "t", "permno", "ret_12m", "vol_12m", "mcap_debt", "debt"])
    panel = panel.drop_duplicates(["cik", "t"]).rename(columns={"ret_12m": "past_ret_12m"})
    snap = pred.merge(panel, on=["cik", "t"], how="left")
    snap = snap.dropna(subset=["permno"]).copy()
    snap["permno"] = snap.permno.astype(int)
    snap["t"] = pd.to_datetime(snap.t)
    snap["flag"] = snap.flag_cut.astype(int)
    snap["log_mv"] = np.log(snap.mcap_debt * snap.debt)
    daily = pd.read_parquet(crsp / "crsp_daily.parquet", columns=["permno", "date", "ret"])
    delist = pd.read_csv(crsp / "crsp_delist.csv", parse_dates=["date"])
    vw = pd.read_csv(crsp / "crsp_vwretd.csv", parse_dates=["date"]).set_index("date").vwretd
    snap = forward_returns(snap, daily, delist, vw, missing_delist)
    snap.to_csv(out / "snapshot_returns.csv", index=False)
    if snap.t.max() + pd.DateOffset(months=12) > vw.index.max():
        print(f"note: CRSP ends {vw.index.max().date()}; windows after that are cut short at the data end")

    rng = np.random.default_rng(0)
    rng_years = np.random.default_rng(1)     # separate stream: the firm-clustered intervals stay as before
    for h in HORIZONS:                       # outlier-robust copy: winsorised at the pooled 1st/99th percentiles
        c = snap[f"ex_{h}"]
        snap[f"exw_{h}"] = c.clip(c.quantile(0.01), c.quantile(0.99))
    report = {"model": model, "snapshots": len(snap), "flagged": int(snap.flag.sum()), "missing_delist": missing_delist,
              "note": "ex = excess over CRSP value-weighted market; exw = ex winsorised at 1%/99%", "horizons": {}}
    for h in HORIZONS:
        d = snap.dropna(subset=[f"ex_{h}"])
        dfi = {f: np.flatnonzero(d.cik.to_numpy() == f) for f in d.cik.unique()}
        firms = d.cik.unique()
        years = d.year.unique()
        yi = {y: np.flatnonzero(d.year.to_numpy() == y) for y in years}
        res = dict(n=len(d), delisted_flagged=int(d[d.flag == 1][f"delisted_{h}"].sum()),
                   delisted_unflagged=int(d[d.flag == 0][f"delisted_{h}"].sum()))
        for kind, col in (("raw", f"ex_{h}"), ("winsorised", f"exw_{h}")):
            diff = lambda x, c=col: x[x.flag == 1][c].mean() - x[x.flag == 0][c].mean()
            within = lambda x, c=col: np.average(
                [g[g.flag == 1][c].mean() - g[g.flag == 0][c].mean() for _, g in x.groupby("year") if g.flag.nunique() == 2],
                weights=[len(g) for _, g in x.groupby("year") if g.flag.nunique() == 2])
            res[kind] = dict(flagged_mean=round(d[d.flag == 1][col].mean(), 4),
                             unflagged_mean=round(d[d.flag == 0][col].mean(), 4),
                             diff=round(diff(d), 4), diff_ci=[round(v, 4) for v in boot_ci(diff, d, dfi, firms, rng, n_boot)],
                             within_year_diff=round(within(d), 4),
                             within_year_ci=[round(v, 4) for v in boot_ci(within, d, dfi, firms, rng, n_boot)],
                             diff_ci_year_blocks=[round(v, 4) for v in boot_ci(diff, d, yi, years, rng_years, n_boot)],
                             within_year_ci_year_blocks=[round(v, 4) for v in boot_ci(within, d, yi, years, rng_years, n_boot)])
        med = lambda x, c=f"ex_{h}": x[x.flag == 1][c].median() - x[x.flag == 0][c].median()
        res["median"] = dict(flagged=round(d[d.flag == 1][f"ex_{h}"].median(), 4),
                             unflagged=round(d[d.flag == 0][f"ex_{h}"].median(), 4), diff=round(med(d), 4),
                             diff_ci=[round(v, 4) for v in boot_ci(med, d, dfi, firms, rng, n_boot)],
                             diff_ci_year_blocks=[round(v, 4) for v in boot_ci(med, d, yi, years, rng_years, n_boot)])
        report["horizons"][h] = res
    reg = snap.dropna(subset=["ex_12m", "past_ret_12m", "vol_12m", "log_mv"])
    rfi = {f: np.flatnonzero(reg.cik.to_numpy() == f) for f in reg.cik.unique()}
    report["regression_12m"] = {
        kind: dict(n=len(reg), flag_coef=round(ols_flag(reg, y), 4),
                   ci=[round(v, 4) for v in boot_ci(lambda x, y=y: ols_flag(x, y), reg, rfi, reg.cik.unique(), rng, n_boot // 4)])
        for kind, y in (("raw", "ex_12m"), ("winsorised", "exw_12m"))}
    report["regression_12m"]["controls"] = ["past 12-month excess return", "volatility", "log market value", "year effects"]
    snap["decile"] = snap.groupby("year").p.transform(lambda s: pd.qcut(s.rank(method="first"), 10, labels=False) + 1)
    report["by_decile_12m"] = {"mean_winsorised": snap.groupby("decile").exw_12m.mean().round(4).to_dict(),
                               "median": snap.groupby("decile").ex_12m.median().round(4).to_dict()}
    report["by_year_12m_median"] = {int(y): {"flagged": round(g[g.flag == 1].ex_12m.median(), 4),
                                             "unflagged": round(g[g.flag == 0].ex_12m.median(), 4)}
                                    for y, g in snap.groupby("year")}
    report["by_outcome_12m_median"] = {"downgraded": round(snap[snap.label == 1].ex_12m.median(), 4),
                                       "not_downgraded": round(snap[snap.label == 0].ex_12m.median(), 4)}
    (out / "returns_report.json").write_text(json.dumps(report, indent=1, default=str))
    print(json.dumps(report, indent=1, default=str))


if __name__ == "__main__":
    main()
