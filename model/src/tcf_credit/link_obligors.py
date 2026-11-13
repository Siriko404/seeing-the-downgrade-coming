"""Pipeline step 3: link each S&P-rated company (an "obligor") to its SEC filer number (CIK) by company name.

Goes in:  the rating-event table (ratings_parser output) and the reduced Loughran-McDonald 10-K header file
          (lm_headers output), which lists every 10-K filer with its current and former names.
Comes out: a links CSV, one row per S&P obligor: the CIK it matched (or none), how it matched, the industry code and
          state of the filer, and whether it is a US company. build_panel keeps only the US rows.
Data:     public data only.

Why a name match: the rating files carry a company name but no CIK. Obligors are keyed by S&P obligor id, else LEI
(legal entity identifier), else name.
Names are matched exactly after normalisation (capital letters, no "Inc"/"Corp" endings), against each CIK's current
and former names. A second, lower-confidence pass also drops the words HOLDINGS, HOLDING, GROUP, INTERNATIONAL and
INTL. A normalised name that maps to more than one CIK is ambiguous and not linked: a wrong link would attach another
company's ratios to a rating.
Usage: python -m tcf_credit.link_obligors EVENTS_CSV_GZ LM_HEADERS_CSV OUT_CSV [--by-dates]
--by-dates (scoring list only, never the training panel): a name that maps to several CIKs is linked when exactly one
of them filed a 10-K under that name while S&P rated the obligor (for example Walt Disney, where two SEC filers have
used the name). Such links get match "dated". Without the option the output is unchanged.
"""
import collections
import csv
import gzip
import re
import sys

SUFFIX = {"INC", "INCORPORATED", "CORP", "CORPORATION", "CO", "COMPANY", "LTD", "LIMITED", "LLC", "LP", "PLC", "THE",
          "NV", "SA", "AG", "LLP", "COS", "CORPORATIONS", "DE", "NEW"}
LOOSE = {"HOLDINGS", "HOLDING", "GROUP", "INTERNATIONAL", "INTL"}
US_STATES = set("AL AK AZ AR CA CO CT DE DC FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY NC ND "
                "OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY PR".split())


def norm(name: str, loose: bool = False) -> str:
    """Make a company name comparable: upper case, no punctuation, no legal ending (Inc, Corp, Ltd ...)."""
    s = name.upper().replace("&", " AND ")
    s = re.sub(r"\(.*?\)", " ", s)
    s = re.sub(r"/[A-Z]{2}/?$", " ", s)            # EDGAR state tags like /DE/
    s = re.sub(r"[^A-Z0-9 ]", " ", s)
    words = s.split()
    while words and words[-1] in SUFFIX | (LOOSE if loose else set()):
        words.pop()
    if words and words[0] == "THE":
        words = words[1:]
    if loose:
        words = [w for w in words if w not in LOOSE]
    return " ".join(words)


def main() -> None:
    """Index the SEC filers by name, then look up every S&P obligor and write one link row for each."""
    events, headers, out = sys.argv[1:4]
    by_dates = "--by-dates" in sys.argv[4:]
    sec = collections.defaultdict(lambda: {"names": set(), "filings": 0, "first": "9", "last": "0", "sic": "", "state": "", "name": ""})
    # cik -> (10-K filing date, name it filed under, normalised both ways)
    named = collections.defaultdict(list)
    for r in csv.DictReader(open(headers)):
        c = sec[r["cik"]]
        if r["form"] != "10-K/A":
            named[r["cik"]].append((r["filing_date"], norm(r["name"]), norm(r["name"], True)))
        c["names"].add(r["name"])
        c["names"].update(x for x in r["former_names"].split("|") if x)
        if r["form"] != "10-K/A":
            c["filings"] += 1
        if r["filing_date"] >= c["last"]:
            c["last"], c["sic"], c["state"], c["name"] = r["filing_date"], r["sic"], r["ba_state"], r["name"]
        c["first"] = min(c["first"], r["filing_date"])
    index = {False: collections.defaultdict(set), True: collections.defaultdict(set)}
    for cik, c in sec.items():
        for n in c["names"]:
            for loose in (False, True):
                k = norm(n, loose)
                if k:
                    index[loose][k].add(cik)
    obl = {}
    for r in csv.DictReader(gzip.open(events, "rt")):
        if r["agency"] != "S&P" or r["sec_class"] != "Corporate" or r["rating_type"] != "Issuer Credit Rating":
            continue
        key = r["obligor_id"] or ("LEI:" + r["lei"] if r["lei"] else "NAME:" + r["obligor_name"].strip().upper())
        o = obl.setdefault(key, {"names": collections.Counter(), "lei": "", "dg": 0, "first": "9", "last": "0"})
        o["names"][r["obligor_name"]] += 1
        o["lei"] = o["lei"] or r["lei"]
        o["dg"] += r["action_class"] == "DG"
        o["first"], o["last"] = min(o["first"], r["action_date"]), max(o["last"], r["action_date"])
    stats = collections.Counter()
    with open(out, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["obligor_id", "sp_name", "lei", "sp_first", "sp_last", "sp_dg_rows", "cik", "sec_name", "match",
                    "sic", "ba_state", "us", "n_10k", "first_10k", "last_10k"])
        for oid, o in obl.items():
            names = [n for n, _ in o["names"].most_common()]
            cik, how = None, "none"
            for loose in (False, True):
                hits = set().union(*(index[loose].get(norm(n, loose), set()) for n in names))
                if len(hits) == 1:
                    cik, how = hits.pop(), "loose" if loose else "exact"
                    break
                if len(hits) > 1:
                    how = "ambiguous"
                    sl, sf = o["last"].replace("-", ""), o["first"].replace("-", "")   # 10-K dates are YYYYMMDD
                    keys = {norm(n, loose) for n in names}   # filed a 10-K under this very name while S&P rated it:
                    live = [c for c in hits if any(sf <= d <= sl and (k2 if loose else k1) in keys   # a former name
                                                   for d, k1, k2 in named[c])]   # now used by another firm fails
                    if by_dates and len(live) == 1:      # only one of them filed 10-Ks while S&P rated this obligor
                        cik, how = live[0], "dated"
                    break
            stats[how] += 1
            c = sec.get(cik) if cik else None
            us = bool(c and c["state"] in US_STATES)
            stats["us" if us else ("linked_non_us" if c else "")] += 1
            w.writerow([oid, names[0], o["lei"], o["first"], o["last"], o["dg"], cik or "", c["name"] if c else "", how,
                        c["sic"] if c else "", c["state"] if c else "", int(us), c["filings"] if c else 0,
                        c["first"] if c else "", c["last"] if c else ""])
    stats.pop("", None)
    print(len(obl), "S&P corporate obligors;", dict(stats))


if __name__ == "__main__":
    main()
