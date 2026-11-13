"""Pipeline step 5b: add stock-market inputs to the panel, using only trading days dated before the snapshot t.

Goes in:  the panel from build_panel and a market folder: crsp_links.csv, crsp_daily.parquet, crsp_sp500.csv. The folder
          comes from fetch_crsp (licensed CRSP data) or from yahoo_market (free Yahoo prices, the stand-in).
Comes out: the same panel with has_prices, permno (the stock identifier of the market folder), ret_12m, ret_6m,
vol_12m, mcap_debt and dd_naive added.
Data:     CRSP (licensed) or the Yahoo stand-in. Yahoo prices miss companies that stopped trading, which biases results.

Why "before t": the 10-K is public on t - 1 day, so only prices up to then could be used on the day.
Link at t: the panel CIK's CRSP stock identifiers ("permno" in the CRSP database; CIK -> gvkey -> permno, from
fetch_crsp) whose link is active on t - 1 day; when several are active, the one with the largest market value on its
last day before t is used.
A row gets market inputs only if the stock has at least 253 trading days before t and traded within 10 days before t.
ret_12m, ret_6m: compounded CRSP total return (ret) over the last 252 / 126 trading days before t, minus the
  compounded S&P 500 return (CRSP sprtrn) over the same dates.
vol_12m: annualised standard deviation of daily log returns over the last 252 trading days.
mcap_debt: market value on the last day before t (|prc| x shrout x 1000) / total debt from the 10-K.
dd_naive: naive distance to default in the spirit of Bharath and Shumway (2008): E = market value,
  F = current debt + half of long-term debt, sigma_D = 0.05 + 0.25 sigma_E, V = E + F,
  sigma_V = E/V sigma_E + F/V sigma_D, mu = the stock's past 12-month return, T = 1:
  dd = (ln(V/F) + (mu - sigma_V^2 / 2)) / sigma_V.
Rows without CRSP coverage keep empty market fields; has_prices marks the rows that have them.
Usage: python -m tcf_credit.market_features PANEL_CSV CRSP_DIR OUT_CSV
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

WINDOW, HALF, STALE_DAYS = 252, 126, 10
# What a row gets when the company has no usable price history (has_prices = 0).
EMPTY = dict(has_prices=0, permno=np.nan, ret_12m=np.nan, ret_6m=np.nan, vol_12m=np.nan, mcap_debt=np.nan, dd_naive=np.nan)


def stock_features(hist: pd.DataFrame, sp: pd.Series, t: pd.Timestamp):
    """hist: one permno's daily rows (date, prc, ret, shrout) sorted by date. Returns None if coverage is too short."""
    hist = hist[hist.date < t]
    if len(hist) < WINDOW + 1 or hist.date.iloc[-1] < t - pd.Timedelta(days=STALE_DAYS):
        return None
    win = hist.iloc[-WINDOW:]
    r = win.ret.fillna(0.0).to_numpy()
    m = sp.reindex(win.date).fillna(0.0).to_numpy()
    r12, r6 = np.prod(1 + r) - 1, np.prod(1 + r[-HALF:]) - 1
    m12, m6 = np.prod(1 + m) - 1, np.prod(1 + m[-HALF:]) - 1
    sigma_e = float(np.std(np.log1p(r), ddof=1) * np.sqrt(WINDOW))
    last = hist.iloc[-1]
    e = abs(last.prc) * last.shrout * 1000 if pd.notna(last.prc) and pd.notna(last.shrout) else np.nan
    return dict(r12=r12, ret_12m=r12 - m12, ret_6m=r6 - m6, vol_12m=sigma_e, e=e)


def row_features(stocks: list, debt, debt_current) -> dict:
    """stocks: list of (permno, stock_features dict). Picks the largest market value and adds the debt-based inputs."""
    permno, s = max(stocks, key=lambda ps: -1 if np.isnan(ps[1]["e"]) else ps[1]["e"])
    res = dict(EMPTY, has_prices=1, permno=permno, ret_12m=s["ret_12m"], ret_6m=s["ret_6m"], vol_12m=s["vol_12m"])
    e, sigma_e = s["e"], s["vol_12m"]
    if pd.notna(e) and e > 0 and pd.notna(debt) and debt > 0:
        res["mcap_debt"] = e / debt
        cur = debt_current if pd.notna(debt_current) else 0.0
        fv = cur + 0.5 * max(debt - cur, 0.0)
        if fv > 0:
            v = e + fv
            sigma_v = e / v * sigma_e + fv / v * (0.05 + 0.25 * sigma_e)
            res["dd_naive"] = (np.log(v / fv) + (s["r12"] - sigma_v ** 2 / 2)) / sigma_v
    return res


def main():
    """For each panel row, find the company's stock, compute the market inputs as of t, write the new panel."""
    panel_csv, crsp_dir, out = sys.argv[1], Path(sys.argv[2]), sys.argv[3]
    panel = pd.read_csv(panel_csv, parse_dates=["t"])
    links = pd.read_csv(crsp_dir / "crsp_links.csv", dtype={"cik": str}, parse_dates=["linkdt", "linkenddt"])
    links["linkenddt"] = links.linkenddt.fillna(pd.Timestamp("2099-12-31"))
    daily = pd.read_parquet(crsp_dir / "crsp_daily.parquet").sort_values(["permno", "date"])
    by_permno = {p: g.reset_index(drop=True) for p, g in daily.groupby("permno")}
    sp = pd.read_csv(crsp_dir / "crsp_sp500.csv", parse_dates=["date"]).set_index("date").sprtrn
    by_cik = {c: g for c, g in links.groupby("cik")}
    feats = []
    for row in panel.itertuples():
        res = dict(EMPTY)
        lk = by_cik.get(str(row.cik))
        if lk is not None:
            day = row.t - pd.Timedelta(days=1)
            active = lk[(lk.linkdt <= day) & (lk.linkenddt >= day)].permno.unique()
            stocks = [(p, f) for p in active if p in by_permno
                      for f in [stock_features(by_permno[p], sp, row.t)] if f is not None]
            if stocks:
                res = row_features(stocks, row.debt, row.debt_current)
        feats.append(res)
    out_df = pd.concat([panel, pd.DataFrame(feats, index=panel.index)], axis=1)
    out_df.to_csv(out, index=False)
    lab = out_df.label if "label" in out_df else pd.Series(dtype=float)
    print(f"{len(out_df)} rows; with prices {int(out_df.has_prices.sum())} ({out_df.has_prices.mean():.0%}); "
          f"downgrade rate with prices {lab[out_df.has_prices == 1].mean():.3f}, without {lab[out_df.has_prices == 0].mean():.3f}")


if __name__ == "__main__":
    main()
