"""Pipeline step 5a helper: write the ticker lists that the free price route needs.

Goes in:  the panel from step 4 (panel.csv, column cik) and the SEC ticker file company_tickers_exchange.json
          (written by step 1, fetch_sec_bulk.py).
Comes out: TICKERS.csv (cik,ticker,exchange) for every panel company that has a ticker in the SEC file, in the order
          the companies first appear in the panel, and TICKERS.txt with one ticker per line plus SPY. SPY stands in
          for the market in yahoo_market.py. Share classes keep the SEC spelling, for example BRK-B.
Data:     public SEC data.
Usage: python -m tcf_credit.tickers PANEL_CSV SEC_TICKERS_JSON OUT_DIR

A CIK can have more than one ticker (share classes or other securities). This script keeps the first SEC row for the
CIK, which is the SEC's primary listing. TICKERS.txt has the same tickers as TICKERS.csv, then SPY.
"""
import json
import sys
from pathlib import Path

import pandas as pd


def cik_text(series: pd.Series) -> pd.Series:
    """CIKs as plain digits, so the panel text and the SEC numbers match."""
    text = series.astype(str).str.strip().str.replace(r"\.0$", "", regex=True)
    return text.str.lstrip("0").replace("", "0")


def read_sec(path: Path) -> pd.DataFrame:
    """Read the SEC ticker file (a JSON object with fields and data) into a table."""
    with open(path) as fh:
        payload = json.load(fh)
    sec = pd.DataFrame(payload["data"], columns=payload["fields"])
    sec["cik"] = cik_text(sec["cik"])
    sec["ticker"] = sec["ticker"].astype(str).str.strip()
    sec["exchange"] = sec["exchange"].astype(str).str.strip()
    return sec


def build(panel: pd.DataFrame, sec: pd.DataFrame) -> pd.DataFrame:
    """One row per panel company with a SEC ticker: cik, ticker, exchange, in panel order."""
    ciks = pd.DataFrame({"cik": cik_text(panel["cik"]).drop_duplicates()})
    first = sec.drop_duplicates("cik", keep="first").set_index("cik")
    out = ciks.join(first[["ticker", "exchange"]], on="cik", how="inner")
    return out[["cik", "ticker", "exchange"]].reset_index(drop=True)


def main() -> None:
    """Write TICKERS.csv and TICKERS.txt into the output folder."""
    panel_csv, sec_json, out_dir = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
    out_dir.mkdir(parents=True, exist_ok=True)
    panel = pd.read_csv(panel_csv, dtype={"cik": str})
    tickers = build(panel, read_sec(sec_json))
    tickers.to_csv(out_dir / "TICKERS.csv", index=False)
    listed = list(dict.fromkeys(tickers.ticker))
    if "SPY" not in listed:
        listed.append("SPY")
    (out_dir / "TICKERS.txt").write_text("\n".join(listed) + "\n")
    print(f"{len(tickers)} companies; {len(listed)} tickers (SPY included)")


if __name__ == "__main__":
    main()
