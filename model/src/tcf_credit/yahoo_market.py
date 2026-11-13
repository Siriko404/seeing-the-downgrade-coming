"""Pipeline step 5a (free stand-in for CRSP): write a CRSP-format market folder from public Yahoo prices.

Goes in:  a folder of Yahoo price files (fetch_yahoo output), a CSV of cik,ticker pairs and the panel from
          build_panel (it gives each company's shares outstanding).
Comes out: a folder in the layout that market_features and features_v2 read, so the rest of the pipeline is unchanged.
Data:     public Yahoo prices. They miss companies that stopped trading (survivorship bias), so results differ from
          CRSP. Also used when a report is newer than the CRSP files the lecture had.

market_features and features_v2 read a CRSP-format folder; this script writes the same four files for the listed
companies:
  crsp_links.csv      cik, permno (the CIK stands in for the permno), linkdt 1900-01-01, linkenddt empty
  crsp_daily.parquet  permno, date, prc (close), ret (daily change in adjusted close, dividends included),
                      shrout (thousands; shares outstanding from the company's latest 10-K cover page, held constant;
                      empty when the cover page gives none (a company with several share classes has them added up by
                      build_panel): then market value, mcap_debt and dd_naive stay empty and the model imputes them)
  crsp_sp500.csv      date, sprtrn  } both from SPY's adjusted close: SPY's total return stands in for the S&P 500
  crsp_vwretd.csv     date, vwretd  } return and for the value-weighted market return that the model was trained on
Usage: python -m tcf_credit.yahoo_market YAHOO_DIR TICKERS_CSV PANEL_CSV OUT_DIR
TICKERS_CSV: cik,ticker. PANEL_CSV: build_panel --score output (gives the shares outstanding).
"""
import sys
from pathlib import Path

import pandas as pd


def daily(path: Path) -> pd.DataFrame:
    """One Yahoo price file as CRSP-style daily rows: close price and daily return from the adjusted close."""
    y = pd.read_csv(path, parse_dates=["date"]).sort_values("date")
    return pd.DataFrame({"date": y.date, "prc": y.close, "ret": y.adjclose.pct_change()}).dropna(subset=["prc"])


def main():
    """Write the four CRSP-format files for the listed companies; skip tickers without a Yahoo file."""
    ydir, tickers_csv, panel_csv, out = Path(sys.argv[1]), sys.argv[2], sys.argv[3], Path(sys.argv[4])
    out.mkdir(parents=True, exist_ok=True)
    tickers = pd.read_csv(tickers_csv, dtype={"cik": str})
    panel = pd.read_csv(panel_csv, dtype={"cik": str}, parse_dates=["t"]).sort_values("t")
    shares = panel.dropna(subset=["shares"]).groupby("cik").shares.last()
    links, frames = [], []
    for r in tickers.itertuples():
        f = ydir / f"{r.ticker}.csv"
        if not f.exists():
            print(f"skip {r.ticker}: no Yahoo file")
            continue
        d = daily(f)
        d["permno"], d["shrout"] = int(r.cik), shares[r.cik] / 1000 if r.cik in shares else float("nan")
        frames.append(d)
        links.append({"cik": r.cik, "permno": int(r.cik), "linkdt": "1900-01-01", "linkenddt": ""})
    pd.DataFrame(links).to_csv(out / "crsp_links.csv", index=False)
    pd.concat(frames)[["permno", "date", "prc", "ret", "shrout"]].to_parquet(out / "crsp_daily.parquet", index=False)
    m = daily(ydir / "SPY.csv").dropna(subset=["ret"])
    m[["date", "ret"]].rename(columns={"ret": "sprtrn"}).to_csv(out / "crsp_sp500.csv", index=False)
    m[["date", "ret"]].rename(columns={"ret": "vwretd"}).to_csv(out / "crsp_vwretd.csv", index=False)
    print(f"{len(links)} companies; market proxy SPY {m.date.min().date()} to {m.date.max().date()}")


if __name__ == "__main__":
    main()
