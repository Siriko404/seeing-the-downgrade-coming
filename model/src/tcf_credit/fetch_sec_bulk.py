"""Pipeline step 1: download the SEC EDGAR bulk files (XBRL company facts, submissions and the current ticker list).

Goes in:  nothing but a folder name. Needs TCF_SEC_CONTACT set (see sec_http.py): the SEC asks every automated
          client to say who it is.
Comes out: companyfacts.zip, submissions.zip and company_tickers_exchange.json in OUT_DIR (files already there are
          kept).
Data:     public SEC data (network needed; the zip files are large).

Usage: python -m tcf_credit.fetch_sec_bulk OUT_DIR
"""
import sys
from pathlib import Path

from tcf_credit.sec_http import download

FILES = {
    "companyfacts.zip": "https://www.sec.gov/Archives/edgar/daily-index/xbrl/companyfacts.zip",
    "submissions.zip": "https://www.sec.gov/Archives/edgar/daily-index/bulkdata/submissions.zip",
    "company_tickers_exchange.json": "https://www.sec.gov/files/company_tickers_exchange.json",
}

if __name__ == "__main__":
    out = Path(sys.argv[1])
    for name, url in FILES.items():
        print(name, download(url, out / name).stat().st_size, flush=True)
