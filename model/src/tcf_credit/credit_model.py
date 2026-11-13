"""Scoring command: score firms with the model. One row per firm asked for: scored (probability, flag line, flag) or why
not.

Goes in:  the firms to score, and a "build folder" with the data the model was built from (see below).
Comes out: a table on screen, results.csv, and the scored rows added to a scores file that the credit-watch agent reads.
Data:     needs the training panel and the other files of the build folder, which you must have made yourself with the
          pipeline (README.md); with licensed CRSP data the panel's own market inputs are used, otherwise Yahoo prices.

It runs the five scoring steps unchanged (build_panel --score, yahoo_market, market_features, features_v2,
score_holdings) on the firms asked for, using the training panel and data saved on your computer. Nothing is uploaded.

FIRM is a ticker (HON), a CIK (773840) or part of a company name (honeywell). --holdings FILE reads one firm per line
(a CSV's first column, or its ticker / cik column). Firms whose files are missing from the build folder are fetched once
and saved (SEC company facts, Yahoo prices); a second run on the same saved files is meant to give the same scores.

Where the data is (there is no default; the command stops with a message if it is missing):
  --build FOLDER   (or environment variable TCF_BUILD): the build folder. It must hold sp_cik_links.csv (step 3),
                   colab_v2/data/panel_v2.csv.gz (the training panel from features_v2; the folder name is just where the
                   lecture's build kept it), company_tickers_exchange.json (step 1) and the folder fred/;
                   companyfacts/ may be missing or empty: the command fetches the files it needs into it. yahoo/
                   must already hold SPY.csv (the stand-in for the market); the command fetches only the firms' own
                   price files into it. An optional sp_cik_links_scoring.csv is used instead of sp_cik_links.csv for
                   scoring.
  --events FILE    (or environment variable TCF_EVENTS): ratings_obligor_events.csv.gz from ratings_parser (step 2).

--as-of DATE uses only 10-Ks filed on or before DATE (default: every saved 10-K). Ratings come from the agencies'
public SEC Rule 17g-7 files (S&P actions up to 2025-12-05); prices and economy series dated before each snapshot only.
Outputs: a table on screen; results.csv in --out (default ./credit-model-run); scored rows merged into
~/.config/credit-watch/scores.csv (the file /credit-watch reads; --scores-file to change, --no-scores-file to skip).
Work files (they hold the panel rows) go to ~/.cache/credit-model/<run>/, outside the agent's folder.
Usage: python -m tcf_credit.credit_model FIRM [FIRM ...] --build FOLDER --events FILE [--holdings FILE]
       [--as-of YYYY-MM-DD] [--out DIR]
"""
import csv
import datetime as dt
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
# The data locations are set by configure() when the command runs, so importing this file or asking for --help needs
# nothing to be set up.
BUILD = EVENTS = PANEL = LINKS = CF = YAHOO = FRED = SCORE_LINKS = TICKERS = None
SCORES = Path.home() / ".config/credit-watch/scores.csv"
SCORE_COLS = ["ticker", "cik", "report_filed", "snapshot_date", "report_url", "p", "cut", "flagged", "trained_to",
              "cut_from", "status", "outcome"]
COVERAGE_END = dt.date(2025, 12, 5)      # last S&P action date in the events file (build_panel --coverage-end default)


def opt(args, name, default=None):
    """The value after option `name` on the command line, or `default`."""
    return args[args.index(name) + 1] if name in args else default


def configure(args: list) -> None:
    """Set the data locations from --build / TCF_BUILD and --events / TCF_EVENTS; stop with a clear message if missing."""
    global BUILD, EVENTS, PANEL, LINKS, CF, YAHOO, FRED, SCORE_LINKS, TICKERS
    build, events = opt(args, "--build", os.environ.get("TCF_BUILD")), opt(args, "--events", os.environ.get("TCF_EVENTS"))
    if not build or not events:
        raise SystemExit("Say where the model's data is: --build FOLDER (or TCF_BUILD) and --events FILE (or TCF_EVENTS). "
                         "Run with --help to see what the folder must hold.")
    BUILD, EVENTS = Path(build), Path(events)
    PANEL = BUILD / "colab_v2/data/panel_v2.csv.gz"
    LINKS, CF, YAHOO, FRED = BUILD / "sp_cik_links.csv", BUILD / "companyfacts", BUILD / "yahoo", BUILD / "fred"
    # Scoring list: the training list plus names that matched several SEC filers, linked to the one that filed 10-Ks under
    # that name while S&P rated it (link_obligors --by-dates; Walt Disney is the example described there). Training
    # never reads it.
    SCORE_LINKS = BUILD / "sp_cik_links_scoring.csv" if (BUILD / "sp_cik_links_scoring.csv").exists() else LINKS
    TICKERS = BUILD / "company_tickers_exchange.json"


def norm(s: str) -> str:
    """Lower-case a name and drop punctuation so that company names can be compared."""
    return re.sub(r"[^a-z0-9 ]", "", s.lower()).strip()


def resolve(q: str, firms: list) -> tuple:
    """(cik, ticker, name) or (None, None, why)."""
    q = q.strip()
    if q.isdigit():
        hits = [f for f in firms if f[0] == str(int(q))]
        return hits[0] if hits else (str(int(q)), "", "")
    hits = [f for f in firms if f[1].upper() == q.upper().replace(".", "-")]
    if not hits:
        hits = [f for f in firms if norm(f[2]) == norm(q)] or [f for f in firms if norm(q) and norm(q) in norm(f[2])]
    ciks = list(dict.fromkeys(f[0] for f in hits))
    if not ciks:
        return None, None, "not found in SEC's company list (give the CIK)"
    if len(ciks) > 1:
        names = "; ".join(f"{f[1]} {f[2]} (CIK {f[0]})" for f in {f[0]: f for f in hits}.values())
        return None, None, f"ambiguous, give the ticker or CIK: {names[:300]}"
    return hits[0]


def run(step: list, log) -> None:
    """Run one pipeline step as its own process and write its output to the log; stop if it fails."""
    env = dict(os.environ, PYTHONPATH=str(REPO / "src"))
    res = subprocess.run([sys.executable, "-m", *step], cwd=REPO, env=env, capture_output=True, text=True)
    log.write(f"$ {' '.join(map(str, step))}\n{res.stdout}{res.stderr}\n")
    if res.returncode:
        raise SystemExit(f"model step failed: {step[0]} (log: {log.name})")


def use_panel_rows(path: Path) -> dict:
    """A report already in the training panel with market inputs (has_prices = 1) keeps the panel's own row (its market
    inputs, as evaluated);
    other reports keep the Yahoo-based row. Returns {(cik, t): source}."""
    import pandas as pd
    h = pd.read_csv(path, dtype={"cik": str})
    pan = pd.read_csv(PANEL, dtype={"cik": str})
    pan = pan[pan.has_prices == 1].merge(h[["cik", "t"]], on=["cik", "t"])[h.columns]
    keys = set(zip(pan.cik, pan.t))
    rest = h[[k not in keys for k in zip(h.cik, h.t)]]
    pd.concat([rest, pan]).to_csv(path, index=False)
    src = {k: "Yahoo prices" for k in zip(rest.cik, rest.t)}
    src.update({k: "training panel row (CRSP prices)" for k in keys})
    return src


def outcomes(rows: list, links: dict) -> None:
    """What S&P did in the 12 months after each scored snapshot, by the model's own label rule (S&P long-term
    foreign-currency issuer credit rating; a withdrawal first means no label). Only where that window ends inside
    S&P's record; otherwise the outcome stays empty. Public SEC Rule 17g-7 data."""
    todo = [r for r in rows if r["status"] == "scored" and r["snapshot_date"]
            and dt.date.fromisoformat(r["snapshot_date"]) + dt.timedelta(days=365) <= COVERAGE_END]
    if not todo:
        return
    sys.path.insert(0, str(REPO / "src"))
    from tcf_credit import build_panel as BP
    ev = BP.load_events(str(EVENTS))
    for r in todo:
        obls = [x for x in links.get(r["cik"], []) if x["us"] == "1"]
        e = ev.get(max(obls, key=lambda x: len(ev.get(x["obligor_id"], [])))["obligor_id"], []) if obls else []
        t = dt.date.fromisoformat(r["snapshot_date"])
        nxt = next((x for x in e if t < x[0] <= t + dt.timedelta(days=365) and (x[2] == "DG" or x[2] in BP.WITHDRAW)), None)
        r["outcome"] = ("no S&P downgrade in the 12 months after the snapshot" if nxt is None else
                        f"S&P downgraded to {nxt[1]} on {nxt[0]}, {(nxt[0] - t).days} days after the snapshot"
                        if nxt[2] == "DG" else f"S&P withdrew the rating on {nxt[0]} (no outcome by the model's rule)")


def main() -> None:
    """Resolve the firms, rebuild their latest snapshots with the pipeline, score them, write the results."""
    args = sys.argv[1:]
    if not args or "-h" in args or "--help" in args:
        print(__doc__); return
    configure(args)
    as_of = opt(args, "--as-of")
    if as_of:
        dt.date.fromisoformat(as_of)
    out = Path(opt(args, "--out", "credit-model-run"))
    scores_file = None if "--no-scores-file" in args else Path(opt(args, "--scores-file", SCORES))
    vals = {opt(args, n) for n in ("--as-of", "--out", "--holdings", "--scores-file", "--build", "--events")}
    queries = [a for a in args if not a.startswith("--") and a not in vals]
    if "--holdings" in args:
        rows = list(csv.reader(open(opt(args, "--holdings"))))
        head = [h.strip().lower() for h in rows[0]] if rows else []
        col = next((head.index(c) for c in ("ticker", "cik") if c in head), None)
        queries += [r[col if col is not None else 0].strip() for r in rows[1 if col is not None else 0:] if r and r[0].strip()]
    if not queries:
        raise SystemExit("no firm given")
    for p in (PANEL, EVENTS, LINKS, TICKERS, FRED):
        if not p.exists():
            raise SystemExit(f"model data missing: {p} (check --build and --events)")

    j = json.load(open(TICKERS))
    firms = [(str(r[0]), r[2] or "", r[1] or "") for r in j["data"]]
    links = {}
    for r in csv.DictReader(open(SCORE_LINKS)):
        if r["cik"]:
            links.setdefault(r["cik"], []).append(r)

    res, seen = [], {}
    for q in queries:
        cik, ticker, name = resolve(q, firms)
        row = {"input": q, "ticker": ticker or "", "cik": cik or "", "name": name if cik else "", "status": "",
               "report_filed": "", "snapshot_date": "", "rating": "", "p": "", "cut": "", "flagged": "",
               "trained_to": "", "cut_from": "", "inputs": "", "report_url": "", "outcome": ""}
        if cik is None:
            row["status"] = name
        elif cik in seen:
            row["status"] = f"same firm as {seen[cik]}"
        else:
            seen[cik] = q
            us = [r for r in links.get(cik, []) if r["us"] == "1"]
            if not us:
                row["status"] = ("outside the model: not in its list of S&P-rated US 10-K filers (matched to "
                                 "S&P's records by name, so some rated firms are missing; non-US filers and funds are out)")
        res.append(row)

    todo = [r for r in res if not r["status"]]
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    (Path.home() / ".cache/credit-model").mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix=stamp + "-", dir=Path.home() / ".cache/credit-model"))   # one per run
    log = open(work / "steps.log", "w")

    need_cf = [r["cik"] for r in todo if not (CF / f"{r['cik']}.csv").exists()]
    if need_cf:
        with open(work / "fetch_links.csv", "w", newline="") as f:
            w = csv.writer(f); w.writerow(["cik", "us"]); w.writerows([c, "1"] for c in need_cf)
        run(["tcf_credit.fetch_companyfacts", work / "fetch_links.csv", CF], log)
    cfw = work / "companyfacts"; cfw.mkdir()
    for r in todo:
        src = CF / f"{r['cik']}.csv"
        text = src.read_text(errors="replace") if src.exists() else ""
        if not text or text.startswith("no_xbrl"):
            r["status"] = "no XBRL company facts at SEC (no 10-K data: 20-F/40-F filer or not a reporting company)"
            continue
        lines = text.splitlines(keepends=True)
        hdr = lines[0].rstrip("\n").split(",")
        fi = hdr.index("filed")
        keep = [ln for ln in lines[1:] if not as_of or ln.split(",")[fi][:10] <= as_of] if as_of else lines[1:]
        if not any(",10-K," in ln for ln in keep):
            r["status"] = ("no 10-K in SEC's XBRL company facts" + (f" filed by {as_of}" if as_of else "") +
                           " (those facts start about 2009 to 2011; 20-F/40-F filers are outside the model)")
            continue
        (cfw / f"{r['cik']}.csv").write_text(lines[0] + "".join(keep))
    todo = [r for r in todo if not r["status"]]

    for r in todo:
        if not r["ticker"]:
            r["status"] = "no ticker in SEC's company list: no prices"
    todo = [r for r in todo if not r["status"]]
    need_px = [r["ticker"] for r in todo if not (YAHOO / f"{r['ticker']}.csv").exists()]
    if need_px:
        (work / "fetch_tickers.txt").write_text("\n".join(need_px) + "\n")
        run(["tcf_credit.fetch_yahoo", work / "fetch_tickers.txt", YAHOO], log)

    scored, inputs = {}, {}
    if todo:
        ciks = ",".join(r["cik"] for r in todo)
        with open(work / "holdings_tickers.csv", "w", newline="") as f:
            w = csv.writer(f); w.writerow(["cik", "ticker"]); w.writerows([r["cik"], r["ticker"]] for r in todo)
        run(["tcf_credit.build_panel", EVENTS, SCORE_LINKS, cfw, work / "holdings_panel.csv", "--score", ciks], log)
        panel = {}
        for p in csv.DictReader(open(work / "holdings_panel.csv")):
            panel.setdefault(p["cik"], []).append(p)
        for r in todo:
            if r["cik"] not in panel:
                r["status"] = "no 10-K from 2011 on while rated by S&P (not rated at the report date, or in default)"
        if panel:
            run(["tcf_credit.yahoo_market", YAHOO, work / "holdings_tickers.csv", work / "holdings_panel.csv",
                 work / "crsp"], log)
            run(["tcf_credit.market_features", work / "holdings_panel.csv", work / "crsp", work / "holdings_market.csv"], log)
            run(["tcf_credit.features_v2", work / "holdings_market.csv", work / "crsp", FRED, work / "holdings_v2.csv"], log)
            inputs = use_panel_rows(work / "holdings_v2.csv")
            run(["tcf_credit.score_holdings", PANEL, work / "holdings_v2.csv", work / "scores.csv"], log)
            accn = {(p["cik"], p["t"]): p["accn"] for ps in panel.values() for p in ps}
            for s in csv.DictReader(open(work / "scores.csv")):
                s["accn"] = accn[(s["cik"], s["t"])]
                scored[s["cik"]] = s
    log.close()

    for r in todo:
        s = scored.get(r["cik"])
        if r["status"] or s is None:
            r["status"] = r["status"] or "not scored (see steps.log)"
            continue
        t = dt.date.fromisoformat(s["t"])
        a = s["accn"]
        r.update(report_filed=(t - dt.timedelta(days=1)).isoformat(), snapshot_date=s["t"], rating=s["rating"],
                 inputs=inputs.get((r["cik"], s["t"]), ""),
                 report_url=f"https://www.sec.gov/Archives/edgar/data/{r['cik']}/{a.replace('-', '')}/{a}-index.htm")
        if s["scope"] != "scored":
            r["status"] = s["scope"]
            continue
        r.update(status="scored", p=s["p"], cut=s["cut"], flagged=s["flagged"], trained_to=str(int(float(s["trained_to"]))),
                 cut_from=s["cut_from"])

    outcomes(res, links)
    out.mkdir(parents=True, exist_ok=True)
    cols = list(res[0])
    with open(out / "results.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols); w.writeheader(); w.writerows(res)
    if scores_file:
        old = list(csv.DictReader(open(scores_file))) if scores_file.exists() else []
        new = [{k: r[k] for k in SCORE_COLS} for r in res if r["cik"] and not r["status"].startswith(("same firm", "ambig"))]
        keys = {(r["cik"], r["snapshot_date"]) for r in new}
        unscored = {r["cik"] for r in new if r["status"] != "scored"}      # a new reason replaces an old one
        merged = sorted([o for o in old if (o["cik"], o["snapshot_date"]) not in keys
                         and not (o["cik"] in unscored and o.get("status", "scored") != "scored")] + new,
                        key=lambda r: (r["ticker"], r["snapshot_date"]))
        scores_file.parent.mkdir(parents=True, exist_ok=True)
        with open(scores_file, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=SCORE_COLS, lineterminator="\n", restval="")
            w.writeheader(); w.writerows({k: r.get(k, "") or ("scored" if k == "status" else "") for k in SCORE_COLS}
                                         for r in merged)

    print(f"the model (logit), as of {as_of or 'latest saved 10-K'}; {len(res)} firms; work files {work}")
    print(f"{'input':<10} {'ticker':<7} {'cik':>8} {'10-K filed':<10} {'S&P':<5} {'p':>6} {'cut':>6} {'flag':<5} status")
    for r in res:
        flag = {"True": "YES", "False": "no"}.get(r["flagged"], "")
        print(f"{r['input'][:10]:<10} {r['ticker'][:7]:<7} {r['cik']:>8} {r['report_filed']:<10} {r['rating']:<5} "
              f"{r['p']:>6} {r['cut']:>6} {flag:<5} {r['status']}")
    for r in res:
        if r["outcome"]:
            print(f"{r['input'][:10]:<10} what happened next: {r['outcome']}")
    n = sum(r["status"] == "scored" for r in res)
    print(f"scored {n}, flagged {sum(r['flagged'] == 'True' for r in res)}, not scored {len(res) - n}. "
          f"Flag = probability at or above the cut (top 10% of the model's scores two years earlier).")
    print(f"results: {out / 'results.csv'}" + (f"; scores for /credit-watch: {scores_file}" if scores_file else ""))


if __name__ == "__main__":
    main()
