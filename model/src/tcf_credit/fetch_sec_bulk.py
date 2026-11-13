"""Pipeline step 1: download the SEC EDGAR bulk files (XBRL company facts, submissions and the current ticker list).

Goes in:  nothing but a folder name. Needs TCF_SEC_CONTACT set (see sec_http.py): the SEC asks every automated
          client to say who it is.
Comes out: companyfacts.zip, submissions.zip and company_tickers_exchange.json in OUT_DIR (files already there are
          kept). With --tickers-only, only company_tickers_exchange.json (under 1 MB): the pipeline needs only this file,
          because step 3b (fetch_companyfacts) asks the SEC for each linked company's facts itself. The two zip files
          (about 2 GB together) are for exploring the SEC data on your own.
Data:     public SEC data (network needed; the zip files are large).

Usage: python -m tcf_credit.fetch_sec_bulk OUT_DIR [--tickers-only]
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
    wanted = ["company_tickers_exchange.json"] if "--tickers-only" in sys.argv else list(FILES)
    for name, url in ((n, FILES[n]) for n in wanted):
        print(name, download(url, out / name).stat().st_size, flush=True)
