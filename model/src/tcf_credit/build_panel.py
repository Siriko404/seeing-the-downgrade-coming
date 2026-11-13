"""Pipeline step 4: build the panel, one row per original annual report (10-K) of a linked US company.

Goes in:  the rating-event table (ratings_parser), the company links (link_obligors) and the folder of SEC company
          facts (fetch_companyfacts), one CSV per company.
Comes out: a CSV panel with the 10-K ratios, the S&P rating state and the label. In training mode, financial and
          utility companies are left out: the model does not cover them.
Data:     public data only (SEC filings and the agencies' public rating files).

The rules that keep out look-ahead:
  - Snapshot date t = 10-K filing date + 1 day. Every input is a number as first filed in that 10-K; later
    restatements are ignored, because they were not known on the day.
  - The rating state at t uses only S&P long-term foreign-currency issuer rating actions dated before t.
  - Label: 1 if S&P downgrades the company (action DG) in the 365 days after t; 0 if it does not. The row is dropped
    (censored) if the rating is withdrawn (WD, WE, WO) first, or if the 365 days are not over by the end of the rating
    data (t + 365 > coverage end), because the outcome is not known yet.
Usage: python -m tcf_credit.build_panel EVENTS_CSV_GZ LINKS_CSV COMPANYFACTS_DIR OUT_CSV [--coverage-end 2025-12-05]
       [--score CIK,CIK,...]   scoring mode: the latest three 10-Ks of each listed CIK (the two earlier ones give
                               features_v2 its changes and three-year volatility), no label (window not observed yet);
                               the rating state is the latest S&P event before t that the files hold.
"""
import collections
import csv
import datetime as dt
import gzip
import math
import sys
from pathlib import Path

# Rating notch: 1 = AAA ... 10 = BBB- (the last investment grade) ... 21 = C; 22 = in default (such rows are dropped).
NOTCH = {r: i for i, r in enumerate("AAA AA+ AA AA- A+ A A- BBB+ BBB BBB- BB+ BB BB- B+ B B- CCC+ CCC CCC- CC C".split(), 1)}
NOTCH.update({"SD": 22, "D": 22})
WITHDRAW = {"WD", "WE", "WO"}


def sector(sic: str) -> str:
    """Group the four-digit industry code (SIC) into broad sectors."""
    try:
        s = int(sic)
    except ValueError:
        return "unknown"
    for lo, hi, name in [(100, 999, "agriculture"), (1000, 1499, "mining_energy"), (1500, 1799, "construction"),
                         (2000, 2999, "manufacturing_nondurable"), (3000, 3999, "manufacturing_durable"),
                         (4000, 4899, "transport_telecom"), (5000, 5199, "wholesale"), (5200, 5999, "retail"),
                         (7000, 8999, "services")]:
        if lo <= s <= hi:
            return name
    return "other"


def excluded(sic: str) -> bool:
    """True for financials (SIC 6000-6799) and electric, gas and water utilities, which the model does not cover."""
    try:
        s = int(sic)
    except ValueError:
        return False
    return 6000 <= s <= 6799 or 4900 <= s <= 4949     # financials; electric, gas and water utilities (not 4953 refuse)


def d(s: str) -> dt.date:
    """The date in the first ten characters of a string (YYYY-MM-DD)."""
    return dt.date.fromisoformat(s[:10])


def load_events(path: str) -> dict:
    """Read the rating events and keep only S&P corporate long-term foreign-currency issuer ratings, per obligor."""
    ev = collections.defaultdict(list)
    for r in csv.DictReader(gzip.open(path, "rt")):
        if (r["agency"] != "S&P" or r["sec_class"] != "Corporate" or r["rating_type"] != "Issuer Credit Rating"
                or r["rating_subtype"] != "Foreign Currency LT"):
            continue
        key = r["obligor_id"] or ("LEI:" + r["lei"] if r["lei"] else "NAME:" + r["obligor_name"].strip().upper())
        ev[key].append((d(r["action_date"]), r["rating"], r["action_class"], r["outlook"], r["watch"]))
    for k in ev:
        ev[k].sort()
    return ev


def rating_state(events: list, t: dt.date) -> dict:
    """The rating, outlook, CreditWatch status and recent actions as they stood on day t
    (only events before t count)."""
    past = [e for e in events if e[0] < t]
    if not past:
        return {}
    rating = past[-1][1]
    outlook = next((e[3] for e in reversed(past) if e[3]), "")
    watch = past[-1][4]
    year_ago = t - dt.timedelta(days=365)
    return {"rating": rating, "notch": NOTCH.get(rating.split("/")[0]), "outlook": outlook, "watch": watch,
            "dg_prev_year": int(any(e[2] == "DG" and e[0] >= year_ago for e in past)),
            "up_prev_year": int(any(e[2] == "UP" and e[0] >= year_ago for e in past)),
            "years_rated": round((t - past[0][0]).days / 365.25, 2),
            "days_since_action": (t - max(e[0] for e in past if e[2])).days if any(e[2] for e in past) else None}


def label(events: list, t: dt.date, end: dt.date):
    """1, 0, or None (censored). The window (t, t+365] must lie inside coverage."""
    horizon = t + dt.timedelta(days=365)
    if horizon > end:
        return None
    for e in events:
        if t < e[0] <= horizon:
            if e[2] == "DG":
                return 1
            if e[2] in WITHDRAW:
                return None
    return 0


def first(vals: dict, *tags):
    """The first of several alternative XBRL tags that the company reported
    (companies label the same item differently)."""
    for tg in tags:
        if vals.get(tg) is not None:
            return vals[tg], tg
    return None, ""


def snapshots(cf_csv: Path):
    """Yield (accn, filed, period_end, values) for each original 10-K, using only facts filed in that 10-K."""
    rows = list(csv.DictReader(cf_csv.open()))
    by_accn = collections.defaultdict(list)
    for r in rows:
        if r.get("form") == "10-K":
            by_accn[r["accn"]].append(r)
    for accn, facts in by_accn.items():
        filed = min(d(f["filed"]) for f in facts)
        ends = collections.Counter(f["end"] for f in facts if f["tag"] == "Assets")
        if not ends:
            continue
        period_end = max(ends)                      # the balance-sheet date of this 10-K
        pe = d(period_end)
        vals = {}
        for f in facts:
            if f["end"] != period_end or f["unit"] not in ("USD", "shares"):
                continue
            if f["start"]:                          # duration item: keep the full fiscal year only
                days = (pe - d(f["start"])).days
                if not 330 <= days <= 400:
                    continue
            vals.setdefault(f["tag"], float(f["val"]))
        float_vals = [float(f["val"]) for f in facts if f["tag"] == "EntityPublicFloat" and f["unit"] == "USD"]
        vals["EntityPublicFloat"] = float_vals[0] if float_vals else None
        share_vals = [float(f["val"]) for f in facts if f["tag"] == "EntityCommonStockSharesOutstanding" and f["unit"] == "shares"]
        # Share classes are listed separately, so their counts are added up.
        vals["EntityCommonStockSharesOutstanding"] = sum(share_vals) if share_vals else None
        yield accn, filed, pe, vals


def ratio(a, b):
    """a / b, or empty when either is missing or b is zero."""
    return a / b if a is not None and b not in (None, 0) else None


def main() -> None:
    """Walk through every linked company and 10-K, compute the ratios, attach rating state and label, write the CSV."""
    args = sys.argv[1:]
    events_path, links_path, cf_dir, out = args[:4]
    end = d(args[args.index("--coverage-end") + 1]) if "--coverage-end" in args else dt.date(2025, 12, 5)
    events = load_events(events_path)
    score = set(args[args.index("--score") + 1].split(",")) if "--score" in args else None
    links = [r for r in csv.DictReader(open(links_path)) if r["us"] == "1" and r["cik"] and (score is None or r["cik"] in score)]
    by_cik = collections.defaultdict(list)
    for r in links:
        by_cik[r["cik"]].append(r)
    stats = collections.Counter()
    cols = ["cik", "obligor", "sp_name", "accn", "t", "period_end", "fy_end_year", "sic", "sector", "label",
            "rating", "notch", "ig", "outlook_neg", "outlook_pos", "watch_neg", "watch_pos", "dg_prev_year", "up_prev_year",
            "years_rated", "days_since_action",
            "assets", "debt", "debt_src", "debt_assets", "ebit_assets", "wc_assets", "ebit_interest", "interest_src",
            "cfo_debt", "log_assets", "re_assets", "cash_assets", "op_margin", "dividend_payer", "float_debt",
            "debt_ebitda", "shares", "debt_current"]
    with open(out, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        for cik, obls in by_cik.items():
            sic = obls[0]["sic"]
            if excluded(sic) and score is None:
                stats["cik excluded financial/utility"] += 1
                continue
            ob = max(obls, key=lambda r: len(events.get(r["obligor_id"], [])))
            ev = events.get(ob["obligor_id"], [])
            cf = Path(cf_dir) / f"{cik}.csv"
            if not cf.exists() or cf.read_text(errors="replace").startswith("no_xbrl"):
                stats["cik without XBRL"] += 1
                continue
            snaps = sorted(snapshots(cf), key=lambda s: s[1])
            for accn, filed, pe, v in (snaps[-3:] if score is not None else snaps):
                t = filed + dt.timedelta(days=1)
                if not dt.date(2011, 1, 1) <= t:      # the SEC's XBRL company facts start around 2009-2011
                    continue
                st = rating_state(ev, t)
                if not st or st["notch"] is None or st["notch"] >= 22:
                    stats["row not rated or in default at t"] += 1
                    continue
                y = label(ev, t, end) if score is None else ""
                if y is None:
                    stats["row censored or window beyond coverage"] += 1
                    continue
                assets = v.get("Assets")
                ltd, src = first(v, "LongTermDebt", "LongTermDebtAndCapitalLeaseObligations", "DebtInstrumentCarryingAmount")
                if ltd is None:
                    nc, _ = first(v, "LongTermDebtNoncurrent")
                    cur, _ = first(v, "LongTermDebtCurrent", "DebtCurrent", "LongTermDebtAndCapitalLeaseObligationsCurrent")
                    if nc is not None:
                        ltd, src = nc + (cur or 0), "LongTermDebtNoncurrent+current"
                short = (v.get("ShortTermBorrowings") or 0) + (v.get("CommercialPaper") or 0)
                debt = ltd + short if ltd is not None else (short or None)
                ebit, _ = first(v, "OperatingIncomeLoss")
                interest, isrc = first(v, "InterestExpense", "InterestExpenseNonoperating", "InterestExpenseDebt", "InterestPaidNet")
                rev, _ = first(v, "Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax", "SalesRevenueNet")
                da, _ = first(v, "DepreciationDepletionAndAmortization", "DepreciationAndAmortization",
                              "DepreciationAmortizationAndAccretionNet", "Depreciation")
                ca, cl = v.get("AssetsCurrent"), v.get("LiabilitiesCurrent")
                div, _ = first(v, "PaymentsOfDividends", "PaymentsOfDividendsCommonStock")
                w.writerow({
                    "cik": cik, "obligor": ob["obligor_id"], "sp_name": ob["sp_name"], "accn": accn, "t": t.isoformat(),
                    "period_end": pe.isoformat(), "fy_end_year": pe.year, "sic": sic, "sector": sector(sic), "label": y,
                    "rating": st["rating"], "notch": st["notch"], "ig": int(st["notch"] <= 10),
                    "outlook_neg": int(st["outlook"] == "Negative"), "outlook_pos": int(st["outlook"] == "Positive"),
                    "watch_neg": int(st["watch"] == "WatchNeg"), "watch_pos": int(st["watch"] == "WatchPos"),
                    "dg_prev_year": st["dg_prev_year"], "up_prev_year": st["up_prev_year"],
                    "years_rated": st["years_rated"], "days_since_action": st["days_since_action"],
                    "assets": assets, "debt": debt, "debt_src": src, "debt_assets": ratio(debt, assets),
                    "ebit_assets": ratio(ebit, assets),
                    "wc_assets": ratio(ca - cl, assets) if ca is not None and cl is not None else None,
                    "ebit_interest": ratio(ebit, interest), "interest_src": isrc,
                    "cfo_debt": ratio(v.get("NetCashProvidedByUsedInOperatingActivities"), debt),
                    "log_assets": math.log(assets) if assets and assets > 0 else None,
                    "re_assets": ratio(v.get("RetainedEarningsAccumulatedDeficit"), assets),
                    "cash_assets": ratio(v.get("CashAndCashEquivalentsAtCarryingValue"), assets),
                    "op_margin": ratio(ebit, rev), "dividend_payer": int(bool(div and div > 0)),
                    "float_debt": ratio(v.get("EntityPublicFloat"), debt),
                    "debt_ebitda": ratio(debt, (ebit + da) if ebit is not None and da is not None else None),
                    "shares": v.get("EntityCommonStockSharesOutstanding"),
                    "debt_current": (first(v, "LongTermDebtCurrent", "DebtCurrent")[0] or 0) + short,
                })
                stats["rows"] += 1
                stats[f"label {y}"] += 1
    print(dict(stats))


if __name__ == "__main__":
    main()
