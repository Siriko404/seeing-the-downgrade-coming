"""Pipeline step 3b (after linking): fetch SEC XBRL company facts for the linked companies, keeping only the tags listed
in TAGS (the model reads all of them except Liabilities, StockholdersEquity, NetIncomeLoss and the pre-tax income
tag).

Goes in:  the links CSV (link_obligors output) and a folder name. Needs TCF_SEC_CONTACT set (see sec_http.py).
Comes out: one CSV per company number (CIK) in OUT_DIR, holding only values from 10-K forms (a form starting with
10-K, so amendments such as 10-K/A are included; build_panel keeps the original 10-K only) of the tags in TAGS: cik,
taxonomy, tag,
          unit, start, end, val, form, fy, fp, filed, accn. A company without XBRL data gets a file saying "no_xbrl".
          Companies already done are skipped. build_panel reads this folder.
Data:     public SEC data (network needed).
Usage: python -m tcf_credit.fetch_companyfacts LINKS_CSV OUT_DIR [--us-only]
"""
import csv
import gzip
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path


TAGS = {
    "us-gaap": [
        "Assets", "Liabilities", "AssetsCurrent", "LiabilitiesCurrent", "StockholdersEquity",
        "CashAndCashEquivalentsAtCarryingValue", "RetainedEarningsAccumulatedDeficit",
        "LongTermDebt", "LongTermDebtNoncurrent", "LongTermDebtCurrent", "DebtCurrent", "ShortTermBorrowings",
        "CommercialPaper", "LongTermDebtAndCapitalLeaseObligations", "LongTermDebtAndCapitalLeaseObligationsCurrent",
        "DebtInstrumentCarryingAmount", "OperatingIncomeLoss", "NetIncomeLoss",
        "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
        "InterestExpense", "InterestExpenseNonoperating", "InterestExpenseDebt", "InterestPaidNet",
        "Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax", "SalesRevenueNet",
        "NetCashProvidedByUsedInOperatingActivities", "DepreciationDepletionAndAmortization",
        "DepreciationAndAmortization", "DepreciationAmortizationAndAccretionNet", "Depreciation",
        "PaymentsOfDividends", "PaymentsOfDividendsCommonStock",
    ],
    "dei": ["EntityPublicFloat", "EntityCommonStockSharesOutstanding"],
}


import threading
_lock, _last = threading.Lock(), [0.0]


def fetch(cik: str) -> dict:
    """Download one company's full facts file from the SEC, waiting so that all threads together stay below the SEC's rate limit."""
    url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{int(cik):010d}.json"
    from tcf_credit.sec_http import request

    with _lock:
        wait = 0.2 - (time.monotonic() - _last[0])
        if wait > 0:
            time.sleep(wait)
        _last[0] = time.monotonic()
    req = request(url)
    req.add_header("Accept-Encoding", "gzip")
    with urllib.request.urlopen(req, timeout=120) as r:
        raw = r.read()
        if r.headers.get("Content-Encoding") == "gzip":
            raw = gzip.decompress(raw)
    return json.loads(raw)


def one(cik: str, out: Path) -> str:
    """Fetch one company and write its CSV; returns skip, no_xbrl or done."""
    dest = out / f"{cik}.csv"
    if dest.exists():
        return "skip"
    try:
        facts = fetch(cik)["facts"]
    except urllib.error.HTTPError as e:
        if e.code == 404:
            dest.write_text("no_xbrl\n")
            return "no_xbrl"
        raise
    rows = []
    for tax, tags in TAGS.items():
        for tag in tags:
            for unit, vals in facts.get(tax, {}).get(tag, {}).get("units", {}).items():
                for v in vals:
                    if str(v.get("form", "")).startswith("10-K"):
                        rows.append([cik, tax, tag, unit, v.get("start", ""), v["end"], v["val"], v["form"],
                                     v.get("fy", ""), v.get("fp", ""), v["filed"], v["accn"]])
    tmp = dest.with_suffix(".part")
    with tmp.open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["cik", "taxonomy", "tag", "unit", "start", "end", "val", "form", "fy", "fp", "filed", "accn"])
        w.writerows(rows)
    tmp.rename(dest)
    return "done"


def main() -> None:
    """Four worker threads; each request still waits for the shared limiter (at most about 5 per second)."""
    from concurrent.futures import ThreadPoolExecutor
    import collections
    links, out = sys.argv[1], Path(sys.argv[2])
    us_only = "--us-only" in sys.argv
    out.mkdir(parents=True, exist_ok=True)
    ciks = sorted({r["cik"] for r in csv.DictReader(open(links)) if r["cik"] and (r["us"] == "1" or not us_only)})
    counts = collections.Counter()
    with ThreadPoolExecutor(4) as pool:
        for i, res in enumerate(pool.map(lambda c: one(c, out), ciks), 1):
            counts[res] += 1
            if i % 200 == 0:
                print(f"{i}/{len(ciks)} {dict(counts)}", flush=True)
    print(f"finished {len(ciks)} ciks; {dict(counts)}")


if __name__ == "__main__":
    main()
