"""Step 4 of 4 (FINISH). Code only. The checked rows go in; a short cited note per firm comes out.

The four steps are FETCH (fetch.py) -> READ (the AI) -> CHECK (check.py) -> FINISH (this file). No AI writes the
note: every rating line is built from a checked row (R1, R2, ...), so each grade, date and day count can be traced to a
quote in a filing. That is why the same rows always give the same note, apart from the 'Made <date>' line.

In: credit-watch/run/ratings.json (from step 3). Out: note_<TICKER>.md (one screen per firm), portfolio.md (with
--holdings), and a dated copy of the whole run in credit-watch/runs/. The model score line is added when a score
file exists; in this package the trained model and its scores are not included, so the note says no score is available.

Usage: python3 finish.py            reads credit-watch/run/ratings.json
Writes credit-watch/run/note_<TICKER>.md for every ticker in the run. Code writes every line from the rows that
check.py kept, so each grade, date, name and day count is a row's own value, with its row id. No AI writes the note.
Model score: this run's model result when the model ran here; else the latest scored 10-K whose snapshot date (the day
after filing) is on or before the as-of date, in ~/.config/credit-watch/scores.csv (made by the model command) or
data/scores.csv (this device's file wins a tie);
a score row with a CIK matches on CIK only, a row without one on ticker.
"""
import csv
import datetime as dt
import os
import re
import shutil
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as C  # noqa: E402
import check as K  # noqa: E402

LOCAL_SCORES = C.LOCAL_SCORES
NOT_SCORED = {
    "financial": "Not scored: financial company. The model leaves out banks, insurers and other financials.",
    "utility": "Not scored: utility. The model leaves out regulated utilities.",
    "ETF": "Not scored: an ETF, not a company.",
    "no 10-K": "Not scored: files no 10-K. The model reads 10-K data.",
    "no SEC reports": "Not scored: no SEC reports.",
    "no S&P rating": "Not scored: no S&P rating in the model's data. The model predicts S&P downgrades.",
}
VERB = {"upgrade": "upgraded", "downgrade": "downgraded", "outlook change": "changed the outlook on",
        "watch placed": "placed on watch", "watch removed": "took off watch", "affirmed": "affirmed",
        "reviewed": "reviewed", "assigned": "assigned", "withdrawn": "withdrew"}


def score_files() -> list:
    out = []
    for f in (LOCAL_SCORES, C.DATA / "scores.csv"):
        if f.exists():
            with open(f, newline="") as fh:
                out.append((f, list(csv.DictReader(fh))))
    return out


def same_firm(r: dict, t: str, cik: str) -> bool:
    """A score row with a CIK matches only that CIK (SEC ticker SJ is Scienjoy, not Stella-Jones)."""
    if r.get("cik", "").strip():
        return bool(cik) and r["cik"].strip().lstrip("0") == str(cik).lstrip("0")
    return r.get("ticker", "").upper() == t.upper()


def score_of(t: str, tk: dict, as_of: str) -> tuple:
    """(score row, its file) of the latest scored 10-K on or before as_of in any scores file (this device's file wins
    a tie); (None, why) when a scores file has the firm but no such score; (None, "") when none has it."""
    best, why, seen = None, "", False
    for k, (f, rows) in enumerate(score_files()):
        mine = [r for r in rows if same_firm(r, t, tk.get("cik", ""))]
        seen = seen or bool(mine)
        for r in mine:
            if r.get("status", "scored") == "scored" and r["snapshot_date"] and r["snapshot_date"] <= as_of:
                if best is None or r["snapshot_date"] > best[0]["snapshot_date"]:
                    best = (r, f)
            elif r.get("status", "scored") != "scored" and not why:
                why = r["status"]
    if best:
        return best
    if not seen:
        return None, ""
    return None, (f"Not scored by the model: {why}." if why else f"No model score from a 10-K filed on or before {as_of}.")


def this_run(cik: str) -> dict | None:
    """This run's model row for the firm (credit-watch/run/model/results.csv), or None."""
    f = C.RUN / "model" / "results.csv"
    if not cik or not f.exists():
        return None
    with open(f, newline="") as fh:
        return next((r for r in csv.DictReader(fh) if r.get("cik", "").lstrip("0") == str(cik).lstrip("0")), None)


def model_lines(t: str, tk: dict, as_of: str, model: str = "") -> list:
    """Score lines for one firm. model: the line fetch.py wrote when it ran the model ("" when it did not run)."""
    if tk.get("scope") in NOT_SCORED:
        return [NOT_SCORED[tk["scope"]]]
    if model.startswith("model: failed"):          # this run's model result first: never hidden behind a saved one
        return ["Not scored: the model failed on this device in this run; see credit-watch/run/model/log.txt."]
    this = this_run(tk.get("cik", "")) if model.startswith("model: scored") else None
    if this is not None and this.get("status") != "scored":
        return [f"Not scored by the model: {this.get('status') or 'no score returned'}."]
    r, f = score_of(t, tk, as_of)
    if r is None and f:
        return [f]
    if r is not None:
        p, cut = float(r["p"]), float(r["cut"])
        flagged = r["flagged"].strip().lower() == "true"
        out = [f"12-month S&P downgrade probability **{p:.1%}**, from the 10-K filed {r['report_filed']} "
               f"([filing]({r['report_url']})).",
               f"Flag line **{cut:.1%}**. **{'Flagged' if flagged else 'Not flagged'}**.",
               f"Flag line: the score that only the top 10% passed when the model trained on years up to "
               f"{r['cut_from'].split('<= ')[1].split(' ')[0]} scored the {r['cut_from'].rsplit(' ', 1)[1]} 10-Ks. "
               f"This score comes from the model trained on 10-K snapshots up to {r['trained_to']}.",
               f"Score written by code from {'this device' if f == LOCAL_SCORES else 'data/scores.csv'}."]
        if r.get("outcome"):
            end = dt.date.fromisoformat(r["snapshot_date"]) + dt.timedelta(days=365)
            when_ = (f"known by {as_of}" if end <= dt.date.fromisoformat(as_of) else
                     f"hindsight: the 12 months end after {as_of}")
            out.append(f"What S&P did in the 12 months after this 10-K, by its own record ({when_}): {r['outcome']}.")
        if (dt.date.fromisoformat(as_of) - dt.date.fromisoformat(r["snapshot_date"])).days > 457:
            out.append("Warning: this score is from a 10-K more than 15 months old.")
        return out
    name = tk['name'].rstrip('.')
    if model.startswith("model: scored"):
        return [f"Not scored: the model ran on this device but returned no score for {name} "
                "(no SEC number, or see credit-watch/run/model/log.txt)."]
    if model.startswith("model: failed"):
        return [f"Not scored: the model failed on this device; see credit-watch/run/model/log.txt."]
    if model.startswith("model: skipped"):
        return [f"Not scored in this run: --offline skips the model, and no saved score for {name} fits the as-of date."]
    return [f"Not scored on this device: no model score for {name}. The model's code is in model/; the trained model, its licensed training data and its scores are not included. "
            "It covers S&P-rated US 10-K filers, not financials or utilities."]


def when(r: dict) -> str:
    return r["rating_date"] or r["filed"]


def tag(r: dict) -> str:
    return "" if r.get("read", "table cell") == "table cell" else " (AI-read text: verify quote)"


BUCKETS = {b for _, b in C.ITEM_SYNONYMS}


def current(rows: list) -> tuple:
    """(last, gone): latest stated grade per (entity, agency, "g", item) and outlook per (entity, agency, "o", "");
    a later withdrawal removes that agency's grades for the entity (one item when it names a standard item, else all,
    with the outlook). gone: (entity, agency) -> the withdrawal row, when nothing is stated after it."""
    last, gone = {}, {}
    for r in sorted(rows, key=lambda r: (when(r), r["filed"], int(r["id"][1:]))):
        if r["action"] == "withdrawn":
            one = r["item"] in BUCKETS
            for k in [k for k in last if k[:2] == (r["entity"], r["agency"]) and (not one or k[3] == r["item"])]:
                del last[k]
            if not any(k[:2] == (r["entity"], r["agency"]) for k in last):
                gone[(r["entity"], r["agency"])] = r
            continue
        if r["grade"]:
            last[(r["entity"], r["agency"], "g", r["item"])] = r
        if r["outlook"]:
            last[(r["entity"], r["agency"], "o", "")] = r
        if r["grade"] or r["outlook"]:
            gone.pop((r["entity"], r["agency"]), None)
    return last, gone


def ratings_now(rows: list, tk: dict | None = None) -> list:
    """The company's own grades and outlook per agency, one line each; every other rated entity on one line.
    Withdrawn ratings are shown as withdrawn."""
    last, gone = current(rows)
    own = lambda e: bool(tk) and K.is_filer(e, tk)
    L = []
    ents = sorted({k[0] for k in last} | {k[0] for k in gone}, key=lambda e: (not own(e), e))
    for ent in ents:
        if not own(ent) and len(ents) > 1:
            g = sorted(((k[1], v) for k, v in last.items() if k[0] == ent and k[2] == "g"), key=lambda x: (x[0], x[1]["item"]))
            items = sorted({v["what_is_rated"] for _, v in g})
            parts = [f"{ag} {v['grade']}" + (f" ({v['what_is_rated']})" if len(items) > 1 else "") for ag, v in g]
            o = sorted((k[1], v) for k, v in last.items() if k[0] == ent and k[2] == "o")
            parts += [f"{ag} outlook {v['outlook_or_watch']}" for ag, v in o]
            parts += [f"{ag} withdrawn" for (e, ag) in sorted(gone) if e == ent]
            ids = sorted({v["id"] for _, v in g + o} | {v["id"] for (e, _), v in gone.items() if e == ent},
                         key=lambda x: int(x[1:]))
            what = f"{items[0]}: " if len(items) == 1 else ""
            L.append(f"- {ent}: {what}{', '.join(parts)}. [{', '.join(ids)}]")
            continue
        L.append(f"- **{ent}**")
        for ag in sorted({k[1] for k in last if k[0] == ent} | {k[1] for k in gone if k[0] == ent}):
            if (ent, ag) in gone:
                w = gone[(ent, ag)]
                L.append(f"  - {ag}: withdrawn, {w['rating_date'] or 'no full date'}, first in the {w['form']} filed "
                         f"{w['filed']}. [{w['id']}]{tag(w)}")
                continue
            mine = [v for k, v in last.items() if k[0] == ent and k[1] == ag]
            parts = [f"{r['what_is_rated']} {r['grade']}" for r in mine if r["grade"]]
            parts += [f"outlook {r['outlook_or_watch']}" for r in mine if r["outlook"] and not r["grade"]]
            parts += [f"outlook {r['outlook_or_watch']}" for r in mine if r["outlook"] and r["grade"]
                      and not any(x["outlook"] and not x["grade"] for x in mine)]
            dates = sorted({r["rating_date"] or f"the filing of {r['filed']}" for r in mine})
            ids = sorted({r["id"] for r in mine}, key=lambda x: int(x[1:]))
            note = " (AI-read text: verify quote)" if any(tag(r) for r in mine) else ""
            L.append(f"  - {ag}: {'; '.join(parts)}. Stated for {', '.join(dates)}. [{', '.join(ids)}]{note}")
    return L or ["No rating stated in the filings read."]


def changes(rows: list, gaps: list | None = None) -> list:
    """Dated actions, oldest first, with the filing that first reported each; then grade and outlook moves seen
    between filings; then actions a filing reports without naming the agency (gaps)."""
    L = []
    unnamed = [g["id"] for g in gaps or [] if g["rule"] == "G-a changed, no agency named"]
    acts = sorted((r for r in rows if r["action"] not in ("none", "")), key=lambda r: (when(r), r["filed"]))
    same = [r for r in acts if r["action"] in ("affirmed", "reviewed")]       # no change: one line
    lines = {}                                                                 # same sentence, several rows: one line
    for r in [r for r in acts if r not in same]:
        what = " ".join(x for x in (r["what_is_rated"] if r["what_is_rated"].lower() != "outlook" else "",
                                    r["grade"], r["outlook_or_watch"]) if x)
        date = r["rating_date"] or "no full date"
        lag = f", {r['lag_days']} days after the action" if r["lag_days"] is not None else ""
        text = (f"- {date}: {r['agency']} {VERB.get(r['action'], r['action'])} {r['entity']}"
                f"{(': ' + what) if what else ''}. First in the {r['form']} filed {r['filed']}{lag}.")
        lines.setdefault(text, []).append(r)
    for text, rs in lines.items():
        L.append(f"{text} [{', '.join(r['id'] for r in rs)}]{tag(rs[0]) if any(tag(r) for r in rs) else ''}")
    if same:
        L.append("- Affirmed or reviewed, no change: " + "; ".join(
            f"{r['rating_date'] or 'no full date'} {r['agency']} [{r['id']}]" for r in same) + ".")
    seen = {}
    for r in sorted(rows, key=lambda r: (when(r), r["filed"])):
        for kind, val in (("g", r["grade"]), ("o", r["outlook"])):
            if val:
                k = (r["entity"], r["agency"], kind, r["item"] if kind == "g" else "")
                if k in seen and seen[k]["grade" if kind == "g" else "outlook"] != val and \
                        not stated_by_action(rows, seen[k], r, kind, val):
                    a = seen[k]
                    label = f"{r['what_is_rated']} grade" if kind == "g" else "outlook"
                    L.append(f"- {r['agency']} {label} for {r['entity']}: "
                             f"{a['grade'] if kind == 'g' else a['outlook_or_watch']} stated for {when(a)}, "
                             f"{r['grade'] if kind == 'g' else r['outlook_or_watch']} stated for {when(r)}. "
                             f"[{a['id']}, {r['id']}]")
                seen[k] = r
    if unnamed:
        L.append(f"- {'Also reported' if L else 'No action by a named agency in the filings read. Reported'} without "
                 f"naming the agency: see [{', '.join(unnamed)}].")
    return L or ["No rating action or change stated in the filings read."]


def stated_by_action(rows: list, a: dict, r: dict, kind: str, val: str) -> bool:
    """A dated action of the same entity and agency, after a and by r, states the new value: the move is listed."""
    return any(x["entity"] == r["entity"] and x["agency"] == r["agency"] and x["date_kind"] == "action"
               and x["action"] not in ("none", "") and x["rating_date"] and when(a) < x["rating_date"] <= when(r)
               and (x["grade"] == val and x["item"] == r["item"] if kind == "g" else x["outlook"] == val) for x in rows)


IG_ITEMS = ("issuer", "issuer default", "senior unsecured")


def own_long_term(rows: list, tk: dict, floor: bool = False) -> dict:
    """The company's own latest long-term grade at each agency: {agency: row}. Issuer grades first, then senior
    unsecured, then, if none of these, the other long-term item whose row has the highest R number. floor: only agencies with an investment-grade floor."""
    sc, latest = C.scales(), {}
    for (ent, ag, kind, it), r in current(rows)[0].items():       # withdrawn grades are gone
        s = sc.get(ag, {})
        if kind == "g" and K.is_filer(ent, tk) and r["grade"] in s.get("long", []) and (s.get("ig_floor") or not floor):
            latest.setdefault(ag, {})[it] = r
    return {ag: next((items[i] for i in IG_ITEMS if i in items), None) or max(items.values(), key=lambda r: int(r["id"][1:]))
            for ag, items in latest.items()}


def credit_flags(rows: list, tk: dict) -> list:
    """For the company's own latest long-term grade at each agency: notches above or below that agency's lowest
    investment grade (scales.json ig_floor), and a line when agencies differ by two notches or more."""
    sc, own = C.scales(), own_long_term(rows, tk, floor=True)
    parts, n, ids = [], {}, []
    for ag in sorted(own):
        r = own[ag]
        lo = sc[ag]["long"]
        n[ag] = lo.index(sc[ag]["ig_floor"]) - lo.index(r["grade"])
        parts.append((n[ag], f"{ag} {r['grade']} ({r['what_is_rated']})"))
        ids.append(r["id"])
    if not parts:
        return ["No long-term grade of the company itself in the rows."]
    words = lambda k: ("at the lowest investment grade" if k == 0 else
                       f"{k} notch{'es' * (k > 1)} above the lowest investment grade" if k > 0 else
                       f"{-k} notch{'es' * (k < -1)} below investment grade (high yield)")
    groups = [f"{words(k)}: {', '.join(x for j, x in parts if j == k)}" for k in sorted({k for k, _ in parts}, reverse=True)]
    L = [f"- {'; '.join(groups)}. [{', '.join(ids)}]"]
    spread = max(n.values()) - min(n.values())
    L.append(f"- Agencies differ by {spread} notches on {tk['name'].rstrip('.')}. [{', '.join(ids)}]" if spread >= 2 else
             "- Agencies agree within one notch." if len(n) > 1 else "- One agency's grade only.")
    return L


def two_dates(rows: list) -> list:
    """The day the agency acted, or the day a table is stated for, against the day the filing reached the SEC."""
    L = []
    span = lambda a, b: f"{a} day{'s' * (a != 1)}" if a == b else f"{a} to {b} days"
    for kind, words in (("action", "Agencies acted {} before a filing reported it"),
                        ("as_of", "Rating tables in the reports trail their as-of date by {}")):
        lags = sorted({(r["lag_days"], r["id"]) for r in rows if r["date_kind"] == kind and r["lag_days"] is not None})
        if lags:
            lo, hi = lags[0], lags[-1]
            med = statistics.median(x for x, _ in lags)
            if lo[0] == hi[0]:
                L.append(f"- {words.format(span(lo[0], lo[0]))} ({len(lags)} row{'s' * (len(lags) > 1)}). [{lo[1]}]")
            else:
                L.append(f"- {words.format(span(lo[0], hi[0]))} (median {med:g}, {len(lags)} rows). "
                         f"Shortest [{lo[1]}], longest [{hi[1]}].")
    if L:
        L.append("- The agency acts first; a reader of filings learns it only on the filing date.")
    return L or ["No dated rating in the filings read."]


def next_steps(rows: list, gaps: list, t: str = "", res: dict | None = None) -> list:
    """Gaps, AI-read text rows, and what the reader left unread or the checker set aside (passage ids)."""
    L = [f"- [{g['id']}] {g['what']}. {g['follow_up']}" for g in gaps]
    ai = [r["id"] for r in rows if tag(r)]
    if ai:
        L.append(f"- Open the filing link of each AI-read text row and check its quote: {', '.join(ai)}.")
    res = res or {}
    cells = [c for c in res.get("missing_cells", []) if c["ticker"] == t]
    if cells:
        L.append(f"- Table cells with a grade or outlook but no kept row ({sum(c['missing'] for c in cells)} cells): "
                 + "; ".join(f"{c['passage_id']} {c['agency']}" for c in cells) + ". Read them in passages.md.")
    acts = [a for a in res.get("missing_actions", []) if a["ticker"] == t]
    if acts:
        L.append(f"- Sentences that name an agency, an action and a date but no kept row ({len(acts)}): "
                 + ", ".join(sorted({a["passage_id"] for a in acts})) + ". Read them in passages.md.")
    pt = res.get("passage_tickers", {})
    empty = [x for x in res.get("empty_tables", []) if pt.get(x) == t]
    if empty:
        L.append(f"- Tables with no kept row ({len(empty)}; some list other ratings, such as securities the firm owns): "
                 + ", ".join(empty) + ".")
    aside = [a for a in res.get("set_aside", []) if a.get("ticker") == t and "rows_json_row" in a
             and not a.get("why", "").startswith("C4 repeat")]
    if aside:
        L.append(f"- Rows the checker set aside ({len(aside)}): passages "
                 + ", ".join(sorted({a["passage_id"] for a in aside if a.get("passage_id")}, key=lambda x: int(x[1:])
                                    if x[1:].isdigit() else 0)) + ". Reasons in ratings.md, Set aside.")
    return L or ["No gap found."]


def portfolio(res: dict) -> str:
    """One line per holding: model score, flag, the company's own long-term grades and outlooks, last dated action,
    and whether its filings were read (with the model on this device: the flagged holdings only)."""
    H = res.get("holdings", [])
    tks = {h["ticker"]: res["tickers"].get(h["ticker"]) or {"name": h["name"] or h["ticker"], "cik": h["cik"],
                                                             "scope": h.get("scope", "")} for h in H}
    found = {t: (None, NOT_SCORED[tk["scope"]]) if tk.get("scope") in NOT_SCORED else score_of(t, tk, res["as_of"])
             for t, tk in tks.items()}
    nxt = any(r is not None and r.get("outcome") for r, _ in found.values())   # past as-of date: S&P's record known
    L = [f"# Portfolio: {len(H)} holdings, as of {res['as_of']}", "",
         "Written by code from the model scores and the checked rows (R#). For analyst review. Not investment advice.",
         f"{res.get('model', '') or 'model: not run'}. Filings read for {sum(1 for h in H if h['read'])} of {len(H)}.", "",
         "| Holding | Score | Flag line | Flagged | Own long-term grades | Outlooks | Last dated action | Note |"
         + (" S&P in the 12 months after the 10-K (its record) |" if nxt else ""),
         "|---|---|---|---|---|---|---|---|" + ("---|" if nxt else "")]
    for h in H:
        t = h["ticker"]
        tk = tks[t]
        r, why = found[t]
        if r is not None:
            sc = [f"{float(r['p']):.1%}", f"{float(r['cut']):.1%}", "Yes" if r["flagged"].strip().lower() == "true" else "No"]
        else:
            sc = [cell(why or "not scored"), "-", "-"]
        if t in res["tickers"]:
            rows = [x for x in res["rows"] if x["ticker"] == t]
            own = own_long_term(rows, tk)
            grades = ", ".join(f"{ag} {x['grade']} [{x['id']}]" for ag, x in sorted(own.items())) or "none stated"
            looks = {}
            for x in sorted(rows, key=lambda x: (when(x), x["filed"], int(x["id"][1:]))):
                if x["outlook"] and K.is_filer(x["entity"], tk):
                    looks[x["agency"]] = x
            outl = ", ".join(f"{ag} {x['outlook']} [{x['id']}]" for ag, x in sorted(looks.items())) or "-"
            acts = sorted((x for x in rows if x["action"] not in ("none", "") and x["rating_date"]),
                          key=lambda x: (x["rating_date"], x["filed"]))
            last = f"{acts[-1]['rating_date']} {acts[-1]['agency']} {acts[-1]['action']} [{acts[-1]['id']}]" if acts else "-"
            parts = [grades, outl, last, f"[note_{t}.md](note_{t}.md)"]
        else:
            parts = [f"filings not read ({cell(h['why'])})", "-", "-", "-"]
        if nxt:
            parts.append(cell(r.get("outcome") or "-") if r is not None else "-")
        L.append(f"| {t} {cell(tk['name'])} | " + " | ".join(sc + parts) + " |")
    return "\n".join(L + ["", "Score: 12-month S&P downgrade probability. Flag line: the score only the top 10% passed when "
                          "the model scored filings two years earlier.", ""])


def cell(s) -> str:
    return str(s).replace("|", "/").replace("\n", " ")


def note(t: str, res: dict) -> tuple:
    """The text of one firm's note, with its six sections, from that firm's rows and gaps."""
    tk = res["tickers"][t]
    rows = [r for r in res["rows"] if r["ticker"] == t]
    gaps = [g for g in res["gaps"] if g["ticker"] == t]
    ml = model_lines(t, tk, res["as_of"], res.get("model", ""))
    sections = [("Model score", [f"- {x}" for x in ml]), ("Ratings now", ratings_now(rows, tk)), ("Credit flags", credit_flags(rows, tk)),
                ("What changed and when", changes(rows, gaps)), ("The two dates", two_dates(rows)),
                ("What to check next", next_steps(rows, gaps, t, res))]
    L = [f"# Credit note: {tk['name']} ({t})", "",
         f"Made {dt.date.today()} from {tk['filings']} filings" + (f" and {tk['manual']} manual files (e.g. SEDAR+)"
         if tk.get("manual") else "") + f" filed {res['window_start']} to {res['as_of']}.",
         "Every line is written by code from checked rows (R#) and gaps (G#). For analyst review. Not investment advice."]
    for head, body in sections:                      # a blank line around every heading: easy on the eye
        L += ["", f"## {head}", ""] + body
    L += ["", "Quote and link of every R#: ratings.md (one row each, with its quote and filing link). Each G# is listed under Gaps there, with what to follow up.", ""]
    return "\n".join(L), ml, rows, gaps


def save_run(res: dict, ps: dict) -> Path:
    """Copy this run's whole folder to credit-watch/runs/<date>_<time of the fetch>_<firms>[_asof-DATE]/, so the next
    fetch (which clears credit-watch/run/) cannot lose it. The same run finished twice fills the same folder."""
    made = ps.get("made") or dt.datetime.now().isoformat(timespec="seconds")
    stamp = made[:19].replace("T", "_").replace(":", "")
    firms = list(res["notes"])
    label = (f"portfolio-{len(res['holdings'])}-firms" if res.get("holdings") else
             "-".join(re.sub(r"[^A-Za-z0-9.=-]", "-", t) for t in firms[:3]) + (f"-and-{len(firms) - 3}-more" if len(firms) > 3 else ""))
    if res["as_of"] != made[:10]:
        label += f"_asof-{res['as_of']}"
    dest = C.ROOT / "runs" / f"{stamp}_{label}"
    shutil.copytree(C.RUN, dest, dirs_exist_ok=True)
    return dest


def main():
    """Write a note for every firm in ratings.json, then save a dated copy of the run."""
    rf = C.RUN / "ratings.json"
    if not rf.exists():
        sys.exit(f"missing {rf}: run check.py first")
    res = C.read_json(rf)
    pf = C.RUN / "passages.json"
    ps = C.read_json(pf) if pf.exists() else {}
    res["model"], res["holdings"] = ps.get("model", ""), ps.get("holdings", [])
    for t in res["notes"]:
        text, ml, rows, gaps = note(t, res)
        out = C.RUN / f"note_{t}.md"
        out.write_text(text)
        ai = sum(1 for r in rows if tag(r))
        print(f"{t}: note written from {len(rows)} rows ({ai} AI-read text rows to verify) and {len(gaps)} gaps; "
              f"wrote {out.resolve()}")
        print(f"  {t} model lines for your reply, copy word for word:")
        for x in ml[:2] + [x for x in ml[2:] if x.startswith("Warning")]:
            print(f"    {x}")
    if res["holdings"]:
        (C.RUN / "portfolio.md").write_text(portfolio(res))
        print(f"portfolio: {len(res['holdings'])} holdings; wrote {(C.RUN / 'portfolio.md').resolve()}")
    if not res["notes"]:
        print("no notes to write")
    else:
        try:
            print(f"saved run: {save_run(res, ps).resolve()}")
        except OSError as e:
            print(f"warning: this run was not saved under credit-watch/runs/ ({e})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
