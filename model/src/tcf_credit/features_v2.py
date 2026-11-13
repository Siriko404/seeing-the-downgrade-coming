"""Pipeline step 6: add the second group of inputs to the panel ("v2" is only the name of this input set), using only
data that was public on the snapshot date t.

Goes in:  the panel from market_features (ratios, rating state, market inputs), a market folder (crsp_daily.parquet and
          crsp_vwretd.csv, from CRSP or from yahoo_market) and a folder of economy data (FRED daily series and the
          Philadelphia Fed real-time data files, see Macro below).
Comes out: the same panel with these extra columns (the list V2_COLUMNS): changes since the last report, profit
          volatility, negative-EBITDA flag, beta, idiosyncratic volatility and seven economy series. This is the
          panel that evaluate.py reads.
Data:     the stock returns need CRSP (licensed) or the Yahoo stand-in; the economy files are public.

Why these inputs (the literature behind each group):
  changes in ratios since the previous 10-K (Malone, Smales & Liu 2026 build inputs from changes);
  volatility of profitability over three annual reports (an input of Baghai, Servaes & Tamayo 2014);
  negative EBITDA: debt/EBITDA set to 0 with a flag when EBITDA is negative (Baghai et al. 2014);
  market beta and idiosyncratic volatility (Baghai et al. 2014);
  the economy, as first released (Nickell, Perraudin & Varotto 2000; Figlewski, Frydman & Liang 2012). "As first
    released" matters: later revisions were not known on the day, so using them would be look-ahead.

Inputs at snapshot t (t = 10-K filing date + 1 day):
  chg_<ratio>: ratio at t minus the same ratio in the firm's previous original 10-K, if that 10-K was filed 250 to 500
    days earlier; else empty.
  vol_ebit_assets_3y: standard deviation of ebit_assets over this and the two previous annual 10-Ks (each step 250 to
    500 days); empty with fewer than three.
  neg_ebitda: 1 if EBITDA < 0 (debt/EBITDA negative with positive debt); debt_ebitda is then set to 0.
  beta_12m, idio_vol_12m: OLS of the stock's daily return on the CRSP value-weighted return over the last 252 trading
    days before t; idio_vol is the annualised residual standard deviation. Needs the market-sample coverage rules.
  unemp: latest monthly unemployment rate as first published, among months whose first vintage was out by t;
    unemp_chg_12m: that value minus the first-published value for the same month a year earlier.
  ip_growth_12m: 12-month growth of industrial production within the latest monthly vintage out by t.
  gdp_growth: first-release real GDP growth (q/q annual rate) of the latest quarter whose advance estimate was out by t
    (taken as 35 days after the quarter ends).
  baa10y, t10y3m: last daily value before t; vix_20d: mean VIX over the last 20 observations before t.
Vintage dates (Philadelphia Fed Real-Time Data Set; the monthly rule is our assumption, not checked): monthly vintage
YYMm is out by the 15th of that month; quarterly
vintage YYQn by the 15th of the middle month of quarter n.
Usage: python -m tcf_credit.features_v2 PANEL_CSV CRSP_DIR FRED_DIR OUT_CSV
"""
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

# The ratios whose change since the previous report is used as an input.
CHG = ["debt_assets", "ebit_assets", "ebit_interest", "cfo_debt", "cash_assets", "op_margin", "debt_ebitda"]
GAP = (250, 500)     # the previous 10-K must be 250-500 days older (about one year), else the change is left empty
WINDOW = 252
MACRO = ["unemp", "unemp_chg_12m", "ip_growth_12m", "gdp_growth", "baa10y", "t10y3m", "vix_20d"]
# Every column this module adds ("v2" is just the name of this input set). evaluate.py uses them as model inputs.
V2_COLUMNS = [f"chg_{c}" for c in CHG] + ["vol_ebit_assets_3y", "neg_ebitda", "beta_12m", "idio_vol_12m"] + MACRO


def vintage_date(code: str) -> pd.Timestamp:
    """'RUC20Q2' -> 2020-05-15; 'IPT20M2' -> 2020-02-15 (years 65-99 are 1900s)."""
    m = re.match(r"[A-Z]+(\d\d)([QM])(\d+)$", code)
    yy, kind, n = int(m.group(1)), m.group(2), int(m.group(3))
    year = 1900 + yy if yy >= 65 else 2000 + yy
    month = 3 * n - 1 if kind == "Q" else n
    return pd.Timestamp(year, month, 15)


def fix_debt_ebitda(df: pd.DataFrame) -> pd.DataFrame:
    """Negative EBITDA makes debt/EBITDA meaningless: set it to 0 and mark the row with neg_ebitda = 1."""
    neg = (df.debt_ebitda < 0) & (df.debt > 0)
    df = df.copy()
    df["neg_ebitda"] = neg.astype(float).where(df.debt_ebitda.notna() | neg, np.nan)
    df.loc[neg, "debt_ebitda"] = 0.0
    return df


def ratio_history(df: pd.DataFrame) -> pd.DataFrame:
    """Changes since the previous 10-K and 3-report volatility of ebit_assets, per firm in filing order."""
    df = df.sort_values(["cik", "t"]).copy()
    out = {f"chg_{c}": [] for c in CHG}
    out["vol_ebit_assets_3y"] = []
    for _, g in df.groupby("cik", sort=False):
        days = g.t.diff().dt.days
        ok1 = days.between(*GAP)
        ok2 = ok1 & ok1.shift(1, fill_value=False)
        for c in CHG:
            out[f"chg_{c}"].append((g[c] - g[c].shift(1)).where(ok1))
        e = g.ebit_assets
        three = pd.concat([e, e.shift(1), e.shift(2)], axis=1)
        out["vol_ebit_assets_3y"].append(three.std(axis=1, ddof=1).where(ok2 & three.notna().all(axis=1)))
    for k, parts in out.items():
        df[k] = pd.concat(parts)
    return df.sort_index()


def beta_idio(hist: pd.DataFrame, mkt: pd.Series, t: pd.Timestamp):
    """Market beta and idiosyncratic volatility from the stock's last 252 trading days strictly before t (no look-ahead)."""
    hist = hist[hist.date < t]
    if len(hist) < WINDOW + 1 or hist.date.iloc[-1] < t - pd.Timedelta(days=10):
        return np.nan, np.nan
    win = hist.iloc[-WINDOW:]
    r = win.ret.to_numpy(dtype=float)
    m = mkt.reindex(win.date).to_numpy(dtype=float)
    ok = np.isfinite(r) & np.isfinite(m)
    if ok.sum() < 200:
        return np.nan, np.nan
    r, m = r[ok], m[ok]
    beta = np.cov(r, m, ddof=1)[0, 1] / np.var(m, ddof=1)
    resid = r - r.mean() - beta * (m - m.mean())
    return float(beta), float(np.std(resid, ddof=2) * np.sqrt(WINDOW))


def read_fred(path: Path) -> pd.Series:
    """Read one daily FRED series (a CSV with observation_date and one value column); '.' means no observation."""
    s = pd.read_csv(path, parse_dates=["observation_date"], na_values=["."]).set_index("observation_date").iloc[:, 0]
    return pd.to_numeric(s, errors="coerce").dropna()


class Macro:
    """The economy as it was known on a given day. Reads, from FRED_DIR/realtime/, the Philadelphia Fed real-time files
    unemployment_first_release.csv, indpro_vintages.csv and gdp_growth_first_second_third.csv, and from FRED_DIR the daily
    series BAA10Y.csv, T10Y3M.csv and VIXCLS.csv (the daily series are FRED downloads; the three real-time files are CSVs converted from the Philadelphia Fed's public spreadsheets by a script that is not in this package)."""

    def __init__(self, fred: Path):
        rt = fred / "realtime"
        u = pd.read_csv(rt / "unemployment_first_release.csv", dtype={"date": str})
        u["month"] = pd.to_datetime(u.date.str.replace(":", "-") + "-01")
        u["known"] = u.first_vintage.map(vintage_date)
        self.unemp = u[["month", "first_release", "known"]].sort_values("month")
        ip = pd.read_csv(rt / "indpro_vintages.csv", dtype={"DATE": str})
        ip.index = pd.to_datetime(ip.pop("DATE").str.replace(":", "-") + "-01")
        self.ip = ip
        self.ip_known = pd.Series({c: vintage_date(c) for c in ip.columns}).sort_values()
        g = pd.read_csv(rt / "gdp_growth_first_second_third.csv", dtype={"Date": str}).dropna(subset=["First"])
        q = g.Date.str.extract(r"(\d{4}):Q(\d)").astype(int)
        qend = pd.to_datetime(dict(year=q[0], month=3 * q[1], day=1)) + pd.offsets.MonthEnd(0)
        self.gdp = pd.DataFrame({"known": qend + pd.Timedelta(days=35), "first": g.First.astype(float)}).sort_values("known")
        self.baa, self.term, self.vix = (read_fred(fred / f) for f in ("BAA10Y.csv", "T10Y3M.csv", "VIXCLS.csv"))

    def at(self, t: pd.Timestamp) -> dict:
        """The seven economy inputs using only numbers that had been published before t."""
        res = dict.fromkeys(MACRO, np.nan)
        u = self.unemp[self.unemp.known <= t]
        if len(u):
            last = u.iloc[-1]
            res["unemp"] = last.first_release
            prev = u[u.month == last.month - pd.DateOffset(years=1)]
            if len(prev):
                res["unemp_chg_12m"] = last.first_release - prev.first_release.iloc[0]
        cols = self.ip_known[self.ip_known <= t]
        if len(cols):
            v = self.ip[cols.index[-1]].dropna()
            if len(v) > 12:
                res["ip_growth_12m"] = v.iloc[-1] / v.iloc[-13] - 1
        g = self.gdp[self.gdp.known <= t]
        if len(g):
            res["gdp_growth"] = g["first"].iloc[-1]
        for k, s in (("baa10y", self.baa), ("t10y3m", self.term)):
            s = s[s.index < t]
            if len(s):
                res[k] = s.iloc[-1]
        v = self.vix[self.vix.index < t]
        if len(v) >= 20:
            res["vix_20d"] = v.iloc[-20:].mean()
        return res


def main():
    """Add the change, volatility, beta and economy columns and write the new panel."""
    panel_csv, crsp_dir, fred_dir, out = sys.argv[1], Path(sys.argv[2]), Path(sys.argv[3]), sys.argv[4]
    df = pd.read_csv(panel_csv, parse_dates=["t"], dtype={"cik": str})
    df = ratio_history(fix_debt_ebitda(df))
    daily = pd.read_parquet(crsp_dir / "crsp_daily.parquet").sort_values(["permno", "date"])
    by_permno = {p: g.reset_index(drop=True) for p, g in daily.groupby("permno")}
    mkt = pd.read_csv(crsp_dir / "crsp_vwretd.csv", parse_dates=["date"]).set_index("date").vwretd
    # The stock-market folder is keyed by the stock identifier of the licensed database (the Yahoo stand-in reuses the
    # company number (CIK) for it), so the panel's identifier column is used to find each firm's stock.
    bi = [beta_idio(by_permno[r.permno], mkt, r.t) if pd.notna(r.permno) and r.permno in by_permno else (np.nan, np.nan)
          for r in df.itertuples()]
    df["beta_12m"], df["idio_vol_12m"] = [b for b, _ in bi], [i for _, i in bi]
    macro = Macro(fred_dir)
    m = pd.DataFrame([macro.at(t) for t in df.t], index=df.index)
    df = pd.concat([df, m], axis=1)
    df.to_csv(out, index=False)
    cover = {c: f"{df[c].notna().mean():.0%}" for c in V2_COLUMNS}
    print(f"{len(df)} rows; neg_ebitda {int(df.neg_ebitda.sum())}; coverage {cover}")


if __name__ == "__main__":
    main()
