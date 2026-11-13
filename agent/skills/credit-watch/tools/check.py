"""Step 3 of 4 (CHECK). Code only. The AI's rows go in; only the rows the filing proves come out.

The four steps are FETCH (fetch.py) -> READ (the AI) -> CHECK (this file) -> FINISH (finish.py). The AI can make
mistakes, so this step does not trust it: every row has to pass four tests against the passage text.
  C1  the quote appears word for word in the passage;
  C2  the grade or outlook sits in the quote, in the right agency's cell (tables) or sentence (text);
  C3  the date is written in full in the passage (and is the quote's own date if the quote has one), and is not later
  than the filing date;
  C4  the row is not a repeat of an earlier one.
A row that fails goes to "set aside" with the reason, and the AI may fix it once.

In: credit-watch/run/passages.json (from step 1) and rows.json (from the AI).
Out: ratings.md (a table for people), ratings.json (for step 4), the lag in days between an agency's action and
the filing that first reported it, and a list of gaps (things the AI should look for or a person should follow up).

Usage: python3 check.py            reads credit-watch/run/passages.json and rows.json
Writes credit-watch/run/ratings.md (for people) and ratings.json (for steps 4 and 5).
A row is kept only if it passes C1 to C4. A failed row goes to "Set aside" with the reason.
Row id R# = the row's number in rows.json, so ids stay put when other rows fail.
"""
import datetime as dt
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as C  # noqa: E402
import fetch as F   # noqa: E402

FIELDS = ["passage_id", "agency", "rated_entity", "what_is_rated", "grade", "outlook_or_watch", "action",
          "rating_date", "date_kind", "quote"]
ACTIONS = {"upgrade", "downgrade", "outlook change", "watch placed", "watch removed", "affirmed", "reviewed",
           "assigned", "withdrawn", "none"}
KINDS = {"action", "as_of", "none"}
FILER_WORDS = {"we", "our", "us", "the company", "company", "the bank", "bank", "the corporation", "corporation",
               "the registrant", "registrant", "the issuer", "issuer", "the group", "the parent", "our company",
               "our debt", "our ratings", "the firm", "the trust"}
CONDITIONAL = re.compile(r"\bat least\b|\bor (above|better|higher|lower|below)\b|\b(lower|higher) than\b|\bif\b|"
                         r"\bwould\b|\bcould\b|\bunless\b|\bthreshold\b|\bLevel \d\b|\bdepend\w* (up)?on\b|"
                         r"\bspreads?\b|\bapplicable (margin|rate|percentage)\b|\bpricing\b", re.I)
AS_OF_WORDS = re.compile(r"\bas (of|at)\b|\bat\b|\bended\b", re.I)
SILENT_DAYS = 457                                   # 15 months


def low(s):
    return C.norm_space(s).lower()


def core(name: str) -> str:
    """Company name without legal suffix and punctuation."""
    n = re.sub(r"'s\b", "", low(name).replace("\u2019", "'"))
    n = re.sub(r"[.,']", "", n).replace("-", " ")                   # 'Coca-Cola' = SEC's 'COCA COLA'
    n = re.sub(r"\b(inc|incorporated|corp|corporation|co|company|ltd|limited|llc|plc|na|sa|ag|the|group|holdings?)\b",
               " ", n)
    return re.sub(r"\s+", " ", n).strip()


FORMS = [("inc", r"inc|incorporated"), ("corp", r"corp|corporation"), ("co", r"co|company"), ("ltd", r"ltd|limited"),
         ("llc", r"llc|l l c"), ("plc", r"plc"), ("na", r"n a|na|national association"), ("lp", r"lp|l p")]


LEGAL_WORD = re.compile(r"\b(inc|incorporated|corp|corporation|co|company|ltd|limited|llc|plc|lp|l\.p|n\.a|na|sa|se|ag|nv|"
                        r"bank|trust|holdings?|group|partners)\b\.?")


def form(name: str) -> str:
    """Legal form written at the end of a name ('corp' for Corporation), '' if none."""
    n = re.sub(r"[.,']", " ", low(name)).strip()
    for f, pat in FORMS:
        if re.search(r"\b(" + pat + r")\s*$", n):
            return f
    return ""


def same_form(a: str, b: str) -> bool:
    """Northern Trust Corporation (the holding company) is not The Northern Trust Company (the bank)."""
    fa, fb = form(a), form(b)
    return not fa or not fb or fa == fb


def words(core_name: str) -> frozenset:
    """Words of a core name, initials joined ('hunt j b transport' and 'jb hunt transport' give the same words)."""
    return frozenset(re.sub(r"\b([a-z]) (?=[a-z]\b)", r"\1", core_name).split())


def is_filer(row_entity: str, tk: dict, ticker: str = "") -> bool:
    """Is the rated entity the filer itself, by name? The filing's spelling may differ from SEC's conformed name."""
    return row_entity == tk["name"] or entity_of(row_entity, tk, ticker) == tk["name"]


def entity_of(row_entity: str, tk: dict, ticker: str = "", filing_text: str = "") -> str | None:
    """Timeline name of the rated entity: the filer's name for the filer, else an exact alias of the filer (SEC former
    name or alias list), else the entity's own name if the same
    filing writes it (a subsidiary, a parent). None if none of these."""
    e = low(row_entity)
    name = tk["name"]
    if e in FILER_WORDS or e == ticker.lower() or re.fullmatch(r"(our|the company's|the bank's|its) .*", e):
        return name
    ce = core(row_entity)
    cn = core(name)
    if ce and (ce == cn or words(ce) == words(cn) or ((len(ce.split()) >= 2 or len(ce) >= 4) and cn.startswith(ce + " "))) \
            and same_form(row_entity, name):
        return name                                                          # "Canadian Natural" = the filer
    if ce.endswith(" parent") and cn.startswith(ce[:-7] + " "):            # "Eversource parent" = Eversource Energy
        return name
    for a in [x for x in tk.get("aliases", "").split(";") if x.strip()]:
        ca = core(a)
        if ca and ce == ca and same_form(row_entity, a):   # exact name only: "Honeywell Aerospace" is not "Honeywell"
            if ca in core(name) or core(name) in ca:
                if same_form(row_entity, name):              # an alias of the filer: the filer's legal form too
                    return name
                continue
            return a.strip()
    if ce and len(ce) >= 2 and re.search(r"(?<![a-z0-9])" + re.escape(ce) + r"(?![a-z0-9])", core(filing_text)):
        return C.norm_space(row_entity)
    return None


def sentences_with(text: str, start: int, end: int) -> str:
    """The sentence or line around text[start:end]."""
    pos = 0
    for sen in C.sentences(text):
        a = text.find(sen, pos)
        pos = a + len(sen)
        if a <= start and end <= pos:
            return sen
    return text


def whole(quote: str, text: str) -> bool:
    """quote occurs in text and does not cut a word or a grade in two."""
    if not isinstance(quote, str) or not quote.strip():   # an empty quote is rejected in words, not a crash
        return False
    for m in re.finditer(re.escape(quote), text):
        a, b = text[m.start() - 1: m.start()], text[m.end(): m.end() + 1]
        if not (a and quote[0].isalnum() and (a.isalnum() or a in "+-")) and \
                not (b and quote[-1].isalnum() and (b.isalnum() or b in "+-")):
            return True
    return False


def sentence_date(text: str, quote: str, date: str, canon: str) -> bool:
    """Is date the date of the quote's own sentence? A quote with no date of its own takes the date written right
    after it ('to BB+ on March 25, 2020'), else the last date written before it in its sentence ('On March 23, Fitch
    ..., and on March 25, S&P downgraded ...': S&P's is March 25),
    or, when its sentence has none, a date in the sentence just before that names the same agency
    ('On May 19, 2025, Moody's announced ... Moody's also affirmed ...')."""
    sens = [C.norm_space(s) for s in C.sentences(text)]
    head = quote[:60]
    for i, s in enumerate(sens):
        k = s.find(quote) if quote in s else s.find(head)
        if k < 0:
            continue
        rest = s[k + len(quote):] if quote in s else ""
        after = C.dates_in(rest)                # '... downgraded our rating to BB+ on March 25, 2020': the date that follows
        if after and re.fullmatch(r"[\s,]*(?:on|effective|as of|dated)?[\s,]*", rest[:after[0][1]], re.I):
            if after[0][0] == date:
                return True
            continue
        before = C.dates_in(s[:k])
        if before:
            if max(before, key=lambda x: x[1])[0] == date:
                return True
        elif i > 0 and date in {d for d, _, _ in C.dates_in(sens[i - 1])} and C.agency_in(sens[i - 1], canon):
            return True
    return False


def table_row_for(p: dict, quote: str):
    """Rows of a table passage that the quote sits in, or that sit in the quote."""
    q = C.norm_space(quote)
    rows = p.get("table", {}).get("rows", [])
    return [r for r in rows if whole(q, C.norm_space(r["line"])) or C.norm_space(r["line"]) in q]


ROW_ITEM = re.compile(r"outlook|rating|term|debt|note|bond|paper|deposit|stock|share|securit|loan|credit|issuer|"
                      r"corporate|senior|subordinat|secured|preferred|facilit|program|trend|watch|total|\(\w\)", re.I)


def row_entity(lab: str) -> str:
    """Entity a row label names: 'CL&P' (no item word), or 'Central Hudson' in 'Central Hudson - Unsecured Debt'."""
    lab = re.sub(r"\s*\((?:\d{1,2}|[ivx]{1,4})\)\s*$|\*+$", "", lab or "")   # footnote mark: 'Corporation(1)'
    m = re.match(r"(.+?)\s+[-\u2013\u2014]\s+(.+)", lab)
    if m and buckets_in(m.group(2)):
        lab = m.group(1)
    return lab if lab and not ROW_ITEM.search(lab) and not buckets_in(lab) and F.entity_label(lab, lab) else ""


def cell_for(r: dict, canon: str):
    """(item label, value, entity) of each cell of a table row that belongs to an agency, or None if the row is not
    the agency's. Agency as row label: item labels are the column headers. Agency as column: item label is the row
    label. Entity: the column-group or group heading over the cell ('' when the table names none)."""
    cells, cols = r["cells"], r["columns"]
    ents = r.get("entities") or [""] * len(cells)
    if cells and C.agency_in(cells[0], canon):
        if not cols:
            return [("", v, e) for v, e in zip(cells[1:], ents[1:])]
        kind = " ".join(v for v in cells[1:] if not cell_grades(canon, v) and not C.outlook(v))
        return [((c if C.item(c) in BUCKETS else f"{c} {kind}".strip()), v, e)        # 'Rating' column + 'Type: Issuer'
                for c, v, e in zip(cols, cells, ents)][1:]
    if cols:
        lab0 = cells[0] if not C.any_agency(cols[0]) else ""
        rent = row_entity(lab0)
        rest = re.sub(r"^\s*[-\u2013\u2014]\s*", "", lab0[len(rent):]) if rent else lab0   # 'Central Hudson - Unsecured Debt'
        grp, out = r.get("group", ""), []
        for c, v, e in zip(cols, cells, ents):
            if c and C.agency_in(c, canon):      # the item label leaves out entity names: they are the entity
                g = "" if grp and e and core(grp) == core(e) else grp
                out.append((" ".join(x for x in (g, rest, C.norm_space(C.strip_agency(c))) if x).strip(), v, rent or e))
        return out or None
    return None


def same_entity(row_entity: str, label: str, tk: dict, ticker: str) -> bool:
    """Is the row's rated entity the entity the table writes over the cell? Same name without legal suffix, one
    name inside the other, or the cell says the filer's ticker and the row names the filer."""
    a, b = core(row_entity), core(label)
    inside = lambda x, y: re.search(r"(?<![a-z0-9])" + re.escape(x) + r"(?![a-z0-9])", y)   # whole words only
    if not b or ((a == b or (a and (inside(a, b) or inside(b, a)))) and same_form(row_entity, label)):
        return True
    return b == ticker.lower() and entity_of(row_entity, tk, ticker) == tk["name"]


def same_item(label: str, item: str) -> bool:
    """Does the row's item label match the item the reader named? Same bucket in common.ITEM_SYNONYMS; an item in
    no bucket must be written in the label (a label may carry a group prefix such as 'FPL:(b)').
    Empty label: no way to tell, so yes."""
    if not re.sub(r"\(\d+\)|[^a-z]", "", low(label)):
        return True
    a, b = C.item(label), C.item(item)
    if a in BUCKETS or b in BUCKETS:
        return a == b
    return bool(b) and (b in a or (bool(a) and re.search(r"(?<![a-z0-9])" + re.escape(a) + r"(?![a-z0-9])", b) is not None))


ACT_VERBS = {"upgrade": r"upgrad|\braised\b", "downgrade": r"downgrad|\blowered\b|\bcut\b",
             "affirmed": r"affirm|confirm|maintain", "reviewed": r"review", "withdrawn": r"withdr",
             "outlook change": r"outlook|revis|trend|chang", "watch placed": r"watch|review|placed",
             "watch removed": r"watch|review|remov|resolv|conclud",
             "assigned": r"assign|initial|receiv|\bnew\b.{0,60}\brating"}
FOR_WATCH = re.compile(r"\b(review|watch)\w*\s+(for|with)\s+(possible\s+|a\s+)?(downgrade|upgrade|negative|positive)\w*", re.I)


OLD_STATE = re.compile(r"\bfrom\s+(?:its\s+|their\s+|the\s+|our\s+|a\s+)?(?:prior\s+|previous\s+|former\s+)?"
                       r"(?P<tok>(?:credit\s*watch|watch|review)\s+(?:for|with)\s+(?:possible\s+|a\s+)?(?:downgrade|upgrade|"
                       r"negative|positive|developing)\w*(?:\s+implications)?|"
                       r"(?:credit\s*watch\s+|watch\s+|review\s+)?(?:with\s+)?(?:negative|positive|developing|"
                       r"stable|evolving)(?:\s+implications)?|[A-Za-z][A-Za-z0-9+\-]{0,5}(?:\s*\((?:high|middle|low)\))?)"
                       r"(?:\s+(?:rating|ratings|outlook|trend))?", re.I)


def new_state(text: str) -> str:
    """Text with the old state taken out: the word 'from' and the grade or outlook right after it.
    'from stable to negative' -> 'to negative'; 'to AA+ from AA' -> 'to AA+'; 'from its prior A rating' -> ''.
    Words between 'from' and the old state are never taken out, so 'from developing on our Aa2 rating' keeps Aa2."""
    def cut(m):
        t = m.group("tok")
        if re.search(r"negative|positive|developing|stable|evolving|downgrade|upgrade", t, re.I) or t in GRADES or \
                re.sub(r"\s+", "", t) in GRADES:
            return " "
        return m.group(0)
    return OLD_STATE.sub(cut, text)


BUCKETS = {b for _, b in C.ITEM_SYNONYMS}
GRADES = C.all_grades()
FORWARD = re.compile(r"\bexpected to\b|\bupon (the )?(closing|completion)\b|\bwill (be )?(upgrad|downgrad|rais|lower)", re.I)


def grades_in(canon: str, text: str) -> set:
    """Grades of this agency's scales written in text (A.M. Best issuer grades in lower case too)."""
    toks = F.grade_tokens(text, True)
    if canon == "A.M. Best":
        toks += re.findall(r"(?<![A-Za-z0-9+\-])(aaa|aa[+\-]?|a[+\-]|bbb[+\-]?|bb[+\-]?|b[+\-]|ccc[+\-]?|cc)(?![A-Za-z0-9+\-])", text)
    return {C.grade(canon, x) for x in toks} - {None}


def cell_grades(canon: str, v: str) -> set:
    """Grades in a table cell; 'VMIG-1/P-1' holds two."""
    return {C.grade(canon, x.strip()) for x in [v] + v.split("/")} - {None} | grades_in(canon, v)


def buckets_in(text: str) -> set:
    """Every item bucket the text names (a clause may name several)."""
    t = re.sub(r"\(\d+\)|\*|[^a-z\- ]", " ", (text or "").lower())
    out = {b for pat, b in C.ITEM_SYNONYMS if re.search(pat, t)}
    return out | ({"senior unsecured"} if LONG_AND_SHORT.search(text or "") else set())   # 'long- and short-term debt'


ENUM = re.compile(r"(?:^|\s)\((?:[ivx]{1,4}|\d{1,2}|[a-h])\)\s*")


def moved(canon: str, quote: str) -> set:
    """'upgrade' / 'downgrade' read from the scale order of a 'to X from Y' or 'from Y to X' pair in the quote."""
    out = set()
    long_ = C.scales()[canon]["long"] if canon in C.scales() else []
    pat = r"[A-Za-z][A-Za-z0-9+\-]{0,5}(?:\s*\((?:high|middle|low)\))?"
    for m in re.finditer(rf"\bto\s+({pat})\s+from\s+({pat})|\bfrom\s+({pat})\s+to\s+({pat})", quote):
        new, old = (m.group(1), m.group(2)) if m.group(1) else (m.group(4), m.group(3))
        a, b = C.grade(canon, new), C.grade(canon, old)
        if a in long_ and b in long_ and a != b:
            out.add("upgrade" if long_.index(a) < long_.index(b) else "downgrade")
    return out


def parts_of(quote: str) -> list:
    """A quote that lists (i) ... (ii) ... or (1) ... (2) ...: one part per list item; else the whole quote."""
    parts = [x for x in ENUM.split(quote) if x.strip()]
    return parts if len(ENUM.findall(quote)) >= 2 else [quote]


LONG_AND_SHORT = re.compile(r"\blong[- ]*(?:term)?\s*(?:and|&|/)\s*short[- ]*term\b", re.I)


def both_terms(label: str, canon: str, g: str) -> str:
    """'long- and short-term debt ratings ... A2 and P-1, respectively': the label names both items, so the grade's
    own scale says which one this row is."""
    if not LONG_AND_SHORT.search(label or "") or not g or canon not in C.scales():
        return label
    gn = C.grade(canon, g)
    return "long-term debt" if gn in C.scales()[canon]["long"] else "short-term debt" if gn else label


def check_row(row: dict, p: dict | None, tk: dict | None, filing_text: str = "") -> tuple:
    """(list of failure reasons, normalised values).
    Table rows: the grade or outlook must sit in the agency's cell of the quoted 'Row:' line, under the item named.
    Text rows: the quote must name the agency and hold the grade, outlook and action word; the old state after
    'from' does not count. Text rows are marked for a person to check the quote (an AI read them)."""
    why, norm = [], {}
    miss = [f for f in FIELDS if f not in row]
    if miss:
        return [f"C0 missing fields: {', '.join(miss)}"], norm
    if p is None or tk is None:
        return [f"C0 no passage {row['passage_id']}"], norm
    if p["kind"] == "table":                     # an action written above the table is prose, not a cell
        cap = C.norm_space(p.get("table", {}).get("caption", ""))
        q = C.norm_space(str(row.get("quote") or ""))
        part = re.split(r"\s+(?=(?:Header|Columns|Row|Group):)", re.sub(r"^Table caption:\s*", "", q), maxsplit=1)[0]
        if str(row.get("date_kind", "")).strip() == "action" or (part == q and cap and whole(part, cap)):
            if not (cap and len(part) >= 4 and whole(part, cap)):
                return ["C2 a dated action in a table passage: quote the sentence of the 'Table caption:' line that "
                        "states it (the Row: lines give no action date)"], norm
            why, norm = check_row({**row, "quote": part}, {**p, "kind": "text", "text": cap}, tk, filing_text)
            if "row" in norm:
                norm["row"]["quote"] = str(row.get("quote") or "").strip()     # the words as the reader quoted them
            return why, norm
    row = {k: (row[k] if isinstance(row[k], str) else ("" if row[k] is None else str(row[k]))).strip() for k in FIELDS}
    if row["action"] not in ACTIONS:
        why.append(f"C0 action must be one of: {', '.join(sorted(ACTIONS))}")
    if row["date_kind"] not in KINDS:
        why.append("C0 date_kind must be action, as_of or none")
    if row["rating_date"] and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", row["rating_date"]):
        why.append("C0 rating_date must be YYYY-MM-DD or empty")
    if row["grade"] and row["outlook_or_watch"]:
        why.append("C0 grade and outlook go in two rows: one with the grade, one with what_is_rated 'outlook'")
    if "/" in row["grade"]:
        why.append(f"C0 one grade per row: write {' and '.join(row['grade'].split('/'))} as separate rows")
    text, quote = C.norm_space(p["text"]), C.norm_space(row["quote"])
    table = p["kind"] == "table"
    # C1 quote
    if len(quote) < 4 or not whole(quote, text):
        why.append("C1 quote is not word for word in the passage")
    if F.INJECTION.search(quote):
        why.append("C1 quote holds instruction-like text")
    # C2 agency, grade, outlook, action, item
    canon = C.agency(row["agency"])
    norm["agency"] = canon
    rows_hit = table_row_for(p, quote) if table else []
    now = new_state(quote)
    if not canon:
        why.append(f"C2 unknown agency '{row['agency']}'")
    else:
        named = C.agency_in(quote, canon) or any(cell_for(r, canon) for r in rows_hit)
        if table and not rows_hit:
            why.append("C2 quote a whole 'Row:' line of the table")
        if not named:
            why.append(f"C2 {canon} is not named in the quote or its table row")
        pairs = [x for r in rows_hit for x in (cell_for(r, canon) or [])]
        what = both_terms(row["what_is_rated"], canon, row["grade"])
        rb = C.item(what)
        if row["grade"]:
            g = C.grade(canon, row["grade"])
            norm["grade"] = g
            if g is None:
                why.append(f"C2 grade '{row['grade']}' is not on the {canon} scale")
            elif table and rows_hit:
                hits = [lab for lab, v, _ in pairs if g in cell_grades(canon, v)]
                ents = {e for lab, v, e in pairs if g in cell_grades(canon, v) and same_item(lab, row["what_is_rated"])}
                if not hits:
                    why.append(f"C2 grade {g} is not in the {canon} cell of the quoted table row")
                elif not any(same_item(lab, row["what_is_rated"]) for lab in hits):
                    why.append(f"C2 '{row['what_is_rated']}' does not match the table label of grade {g}: "
                               f"{' / '.join(sorted(set(hits)))}")
                elif ents and not any(same_entity(row["rated_entity"], e, tk, p.get("ticker", "")) for e in ents):
                    why.append(f"C2 grade {g} in this row is {' / '.join(sorted(e for e in ents if e))}'s, "
                               f"not {row['rated_entity']}'s")
                else:                                # the table's own name for the entity, for one spelling per run
                    if rb not in BUCKETS:                # and its own label for an item with no standard name
                        norm["table_item"] = C.item(sorted(lab for lab in hits if same_item(lab, row["what_is_rated"]))[0])
                    norm["table_entity"] = next((e for e in sorted(ents, key=lambda e: (core(e) != core(row["rated_entity"]), e))
                                                 if e and same_entity(row["rated_entity"], e, tk, p.get("ticker", ""))), "")
                    # exact name first: 'Ford Credit' is not 'Ford' because one name holds the other
            elif g not in grades_in(canon, quote):
                why.append(f"C2 grade {g} is not in the quote")
            elif g not in grades_in(canon, now):
                why.append(f"C2 grade {g} is the old grade ('from {row['grade']}'), not the new one")
            elif rb in BUCKETS and (bs := buckets_in(quote)) and rb not in bs:
                why.append(f"C2 the quote states grades for {', '.join(sorted(bs))}, not '{row['what_is_rated']}'")
            elif len(parts_of(quote)) > 1 and not any(
                    g in grades_in(canon, new_state(x)) and (row["action"] not in ACT_VERBS or row["action"] in
                    ("watch placed", "watch removed") or re.search(ACT_VERBS[row["action"]], FOR_WATCH.sub(" ", x), re.I)
                    or row["action"] in moved(canon, x))
                    and not (rb in BUCKETS and buckets_in(x) and rb not in buckets_in(x)) for x in parts_of(quote)):
                why.append(f"C2 no single numbered part of the quote holds grade {g}, the action and the item together")
            if g is not None:
                sc = C.scales()[canon]
                if rb == "short-term" and g not in sc["short"]:
                    why.append(f"C2 grade {g} is a long-term grade, but the item is short-term")
                elif rb in ("senior unsecured", "legacy senior", "issuer", "issuer default", "subordinated", "secured",
                            "debentures") and g not in sc["long"]:
                    why.append(f"C2 grade {g} is a short-term grade, but the item is long-term")
        if row["outlook_or_watch"]:
            o = C.outlook(row["outlook_or_watch"])
            norm["outlook"] = o
            d = o.split()[-1] if o else ""
            here = quote if table else now
            if not o:
                why.append(f"C2 '{row['outlook_or_watch']}' is not an outlook or watch")
            elif row["action"] == "watch removed" and o.startswith("watch"):
                why.append("C2 watch removed: outlook_or_watch is the outlook after the removal (e.g. 'negative'), "
                           "or empty; not the watch that was removed")
            elif d not in low(here) and not (d == "negative" and re.search(r"downgrade", here, re.I)) and \
                    not (d == "positive" and re.search(r"upgrade", here, re.I)):
                why.append(f"C2 outlook '{row['outlook_or_watch']}' is not the outlook the quote states now")
            elif o.startswith("watch") and not re.search(r"watch|review", here, re.I):
                why.append(f"C2 '{row['outlook_or_watch']}' is a watch, but the quote states no watch or review")
            elif table and rows_hit and not any(C.outlook(v) == o for _, v, _ in pairs):
                why.append(f"C2 outlook '{o}' is not in the {canon} cells of the quoted table row")
            elif table and rows_hit and not any(C.outlook(v) == o and same_entity(row["rated_entity"], e, tk, p.get("ticker", ""))
                                                for _, v, e in pairs):
                why.append(f"C2 outlook '{o}' in this row belongs to another entity, not {row['rated_entity']}")
            elif table and rows_hit and not norm.get("table_entity"):
                norm["table_entity"] = next((e for _, v, e in sorted(pairs, key=lambda x: core(x[2]) != core(row["rated_entity"]))
                                             if e and C.outlook(v) == o and
                                             same_entity(row["rated_entity"], e, tk, p.get("ticker", ""))), "")
        if row["action"] in ACT_VERBS:
            verbs = FOR_WATCH.sub(" watch ", quote)
            if row["action"] == "watch placed":            # "from watch negative to negative" is a removal
                verbs = FOR_WATCH.sub(" watch ", now)
            if row["action"] in ("upgrade", "downgrade"):
                verbs = FOR_WATCH.sub(" ", quote)
            if row["action"] == "watch removed":
                ok = re.search(r"\b(remov|withdr|resolv|conclud|taken off|came off|off)\w*\b.{0,40}?"
                               r"(credit\s*watch|\bwatch|\breview)|(credit\s*watch|\bwatch|\breview)\w*\b.{0,40}?"
                               r"\b(remov|resolv|conclud|end)", quote, re.I)
            else:
                ok = re.search(ACT_VERBS[row["action"]], verbs, re.I) or row["action"] in moved(canon, quote)
            if not ok:
                why.append(f"C2 action '{row['action']}' is not what the quote says {canon} did")
            if row["action"] in ("upgrade", "downgrade", "watch placed", "outlook change") and FORWARD.search(quote):
                why.append("C2 the quote says the action is expected, not done")
        if not row["grade"] and not row["outlook_or_watch"] and row["action"] in ("none", ""):
            why.append("C2 row states no grade, outlook, watch or action")
        if row["action"] == "assigned" and not row["grade"]:
            why.append("C2 an assigned rating needs its grade")
        if row["date_kind"] != "action" and CONDITIONAL.search(quote):
            why.append("C2 quote is a condition or threshold, not a rating the entity has")
    # C3 date and name
    if row["rating_date"]:
        ds = [d for d in C.dates_in(p["text"]) if d[0] == row["rating_date"]]
        own = [d for d, _, _ in C.dates_in(quote)]
        if not ds:
            why.append(f"C3 date {row['rating_date']} is not written in full in the passage")
        elif own and row["rating_date"] not in own:
            why.append(f"C3 date {row['rating_date']} is not the date the quote gives: {', '.join(sorted(set(own)))}")
        elif not own and not table and row["date_kind"] == "action" and canon and \
                not sentence_date(p["text"], quote, row["rating_date"], canon):
            why.append(f"C3 date {row['rating_date']} is not the date of the quoted sentence: quote the words that "
                       "give the date, or leave rating_date empty")
        if row["rating_date"] > p["filed"]:
            why.append(f"C3 date {row['rating_date']} is after the filing date {p['filed']}")
        if row["date_kind"] == "none":
            why.append("C3 a date needs date_kind action or as_of")
        elif ds:
            near = [sentences_with(p["text"], s, e) for _, s, e in ds]
            if row["date_kind"] == "action" and not any(F.ACTION_WORDS.search(x) for x in near):
                why.append("C3 date_kind action, but no action word next to the date")
            if row["date_kind"] == "as_of" and not any(AS_OF_WORDS.search(x) or re.match(r"\s*(Header|Columns|Table caption):", x)
                                                       for x in near):
                why.append("C3 date_kind as_of, but no 'as of' or 'as at' next to the date")
        if row["date_kind"] == "as_of" and row["action"] not in ("none", "affirmed", "reviewed"):
            why.append("C3 an action needs date_kind action, not as_of")
    elif row["date_kind"] != "none":
        why.append("C3 no rating_date, so date_kind must be none")
    te = norm.pop("table_entity", "")
    ent = entity_of(te or row["rated_entity"], tk, p.get("ticker", ""), filing_text or p["text"]) or \
        (te if entity_of(row["rated_entity"], tk, p.get("ticker", ""), filing_text or p["text"]) else None)
    if ent and ent != tk["name"] and not LEGAL_WORD.search(low(row["rated_entity"])) and \
            re.search(r"\b(shares?|notes?|bonds?|debentures?|debt|securities|preferred|paper|program|facility)\b",
                      low(row["rated_entity"])):                # a name with no legal form, made of security words
        why.append(f"C3 '{row['rated_entity']}' is a rated security, not a company: rated_entity is its issuer, "
                   "what_is_rated the security")
    norm["entity"] = ent
    cn = core(tk["name"])
    if (not table and ent == tk["name"] and str(p.get("doc_type", "")).upper().startswith("EX-")
            and re.search(r"\b(our|we|us)\b", low(quote)) and cn and re.search(
                r"(?<![a-z0-9])" + re.escape(cn) + r" (transaction|merger|acquisition|offer|deal)\b|"
                r"\b(merger with|acquisition by|acquired by|combination with|offer from) (the )?" + re.escape(cn) + r"\b",
                core(quote))):
        # an exhibit that says "our" and names the filer as the other side of a deal (an acquired firm's own text)
        norm["entity"] = "Another company (exhibit text)"
    if ent is None:
        why.append(f"C3 '{row['rated_entity']}' is not {tk['name']} and is not written in this filing")
    norm["item"] = "outlook" if row["outlook_or_watch"] and not row["grade"] else \
        C.item(both_terms(row["what_is_rated"], canon, row["grade"]) if canon else row["what_is_rated"])
    if norm.get("table_item") and norm["item"] != "outlook":
        norm["item"] = norm["table_item"]
    norm.pop("table_item", None)
    if not table and row["grade"] and not buckets_in(quote) and not (norm["item"] and norm["item"] in low(quote)):
        norm["item"] = "unspecified"                 # the quote names no item: the reader's guess is not kept,
        gn = C.grade(canon, row["grade"]) if canon in C.scales() else None   # but the grade's own scale says long or
        if gn and gn in C.scales()[canon].get("short", []):                  # short term, so Baa1 and P-2 never share
            norm["item"] = "short-term"                                      # one line (a false 'change' in the note)
        elif gn and gn in C.scales()[canon].get("long", []):
            norm["item"] = "long-term (item not named)"
    flags = []
    if canon and any(a != canon and C.agency_in(quote, a) for a in C.AGENCIES):
        flags.append(f"several agencies in the quote: verify which value is from {canon}")
    if len({d for d, _, _ in C.dates_in(quote)}) > 1:
        flags.append(f"several dates in the quote: verify {row['rating_date']} is the action date")
    norm["read"] = "table cell" if table else "AI-read text: verify quote" + ("; " + "; ".join(flags) if flags else "")
    norm["row"] = row
    return why, norm


def days(a: str, b: str) -> int:
    return (dt.date.fromisoformat(a) - dt.date.fromisoformat(b)).days


RANGE = re.compile(r"\S\s+(to|through)\s+\S", re.I)                   # 'AAA to D': a scale, not a rating


NOT_RATED = re.compile(r"^\s*(n/?a|nr|n\.r\.|not rated|wr|withdrawn|[\u2014\u2013\-_]+)\s*(\(\d+\))?\s*$", re.I)


def cell_values(canon: str, v: str) -> tuple:
    """(grades, outlook) a table cell states for an agency. 'A (low), Stable' holds both; 'VMIG-1/P-1' two grades;
    'AAA to D' (a scale), 'N/A' and dashes hold none."""
    v0 = C.norm_space(re.sub(r"\(\d+\)|\*", " ", v))
    if NOT_RATED.match(v0) or (RANGE.search(v0) and len(F.grade_tokens(v0, True)) >= 2):
        return set(), None
    parts = [x.strip() for x in v0.split(",")]
    g = C.grade(canon, parts[0])
    gs = {g} if g and "/" not in g else {C.grade(canon, x.strip()) for x in parts[0].split("/")} - {None}
    return gs, C.outlook(v0) or (C.outlook(parts[-1]) if len(parts) > 1 else None)


NOT_FIRM_TABLE = re.compile(r"\b(reinsurers?|reinsurance (groups|contract assets)|recoverables?|counterpart(y|ies)|"
                            r"held[- ]to[- ]maturity|available[- ]for[- ]sale|investment portfolio|securities (held|owned)|"
                            r"internal (risk )?ratings?( map| grades?| system)?|aligns?\b.{0,80}\bexternal ratings)\b",
                            re.I)
THRESHOLD_COL = re.compile(r"\b(minimum|threshold|required|trigger)\b", re.I)


def missing_cells(passages: list, kept: list, tickers: dict | None = None) -> list:
    """Table lines where an agency has a grade or outlook cell that no kept row of that passage states for that
    agency and entity. Scale ranges ('AAA to D'), 'N/A' and condition lines are not ratings."""
    out = []
    for p in passages:
        if p["kind"] != "table":
            continue
        if NOT_FIRM_TABLE.search(p.get("table", {}).get("caption", "")):
            continue                                 # reinsurers', counterparties' or securities' ratings: not the firm's
        tk = (tickers or {}).get(p["ticker"], {"name": "", "aliases": ""})
        mine_p = [r for r in kept if r["passage_id"] == p["id"]]
        for tr in p.get("table", {}).get("rows", []):
            if CONDITIONAL.search(tr["line"]):
                continue
            for canon in C.AGENCIES:
                miss = 0
                for lab, v, e in cell_for(tr, canon) or []:
                    if THRESHOLD_COL.search(lab or ""):     # 'Minimum Long-Term Investment Grade Rating': a line, not a rating
                        continue
                    gs, o = cell_values(canon, v)
                    e = re.sub(r"\((?:[a-z]|\d{1,2})\)|:", " ", e).strip()
                    ce = (entity_of(e, tk, p["ticker"], p["text"]) if e and tk.get("name") else None) or e
                    others = {core(x) for *_, x in cell_for(tr, canon) or [] if x} - {core(e)}   # 'Ford Credit' beside 'Ford'
                    mine = [r for r in mine_p if r["agency"] == canon and
                            (not e or r["entity"] == ce or (same_entity(r["entity"], e, tk, p["ticker"])
                                                            and core(r["entity"]) not in others))]
                    miss += sum(1 for g in gs if not any(r["grade"] == g for r in mine))
                    miss += 1 if o and not any(r["outlook"] == o for r in mine) else 0
                if miss:
                    out.append({"passage_id": p["id"], "ticker": p["ticker"], "agency": canon, "missing": miss,
                                "line": tr["line"][:160]})
    return out


def missing_actions(passages: list, kept: list) -> list:
    """Prose sentences that name an agency, an action word and a date (full, or month and year), and that no kept
    row quotes anywhere."""
    quoted = [C.norm_space(r["quote"]).lower() for r in kept]
    out, seen = [], set()
    for p in passages:
        text = p.get("table", {}).get("caption", "") if p["kind"] == "table" else p["text"]   # a table: its caption
        for sen in C.sentences(text):
            s = C.norm_space(sen).lower()
            near = any(C.any_agency(sen[max(0, m.start() - 60):m.start()]) or
                       re.match(r"\W*\w*\W*by\W", sen[m.end():m.end() + 12]) and C.any_agency(sen[m.end():m.end() + 60])
                       for m in F.ACTION_WORDS.finditer(sen)              # the agency acts: 'S&P revised', 'lowered by S&P'
                       if not re.match(r"\s+(thresholds?|triggers?|cushion|risks?|levels?)\b", sen[m.end():], re.I))
            if len(s) < 25 or s in seen or not (near and (C.dates_in(sen) or F.MONTH_YEAR.search(sen))):
                continue                         # the agency named near the action word; a date, full or 'In May 2026
            if CONDITIONAL.search(sen) and not re.search(r"\b(upgrad|downgrad|affirm|revis|placed|assign)", sen, re.I):
                continue
            seen.add(s)
            ds = {d for d, _, _ in C.dates_in(sen)}
            if any(r.get("rating_date") in ds and r.get("agency") and C.agency_in(sen, r["agency"]) for r in kept):
                continue                         # that agency's action of that day is kept (maybe from an earlier filing)
            core_s = re.sub(r"^\(\d+\)\s*", "", s)
            if not any(core_s in q or q in core_s for q in quoted if len(q) > 20):
                out.append({"passage_id": p["id"], "ticker": p["ticker"], "sentence": C.norm_space(sen)[:200]})
    return out


GENERIC_ITEM = re.compile(r"issuer|unspecified|long-term \(item not named\)|(?:the )?(?:(?:long[- ]term )?credit|debt)? ?ratings?")   # 'downgraded the credit
                                                     # ratings for Ford': every item of that agency moved that day


def gaps_for(rows: list, tickers: dict, as_of: str, start: str) -> list:
    """Gaps G-a, G-b, G-c: rating changes no filing dates, agencies silent for over 15 months, nothing to read."""
    out = []

    def add(t, rule, d1, d2, follow, refs, what):
        out.append({"ticker": t, "rule": rule, "from": d1, "to": d2, "what": what, "follow_up": follow, "rows": refs})

    def dated_action(t, ent, ag, d1, d2, kinds=None, item=None):
        return [r for r in rows if r["ticker"] == t and r["entity"] == ent and r["agency"] == ag and r["rating_date"]
                and r["date_kind"] == "action" and r["action"] not in ("none",) and d1 < r["rating_date"] <= d2
                and (kinds is None or r["action"] in kinds)
                and (item is None or r["item"] == item or GENERIC_ITEM.fullmatch(r["item"]))]   # another item's action: no

    def when(r):
        return r["rating_date"] or r["filed"]

    for r in rows:                                               # G-a (i): an action with no full date
        if r["action"] not in ("none", "affirmed", "reviewed") and not r["rating_date"]:
            my = F.MONTH_YEAR.search(r["quote"])
            mo = C.MONTHS.get(my.group(1).lower()) if my else None
            if mo:                                               # "In June 2017": search that month
                y = int(re.search(r"\d{4}", my.group(0)).group(0))
                d1 = dt.date(y, mo, 1).isoformat()
                d2 = (dt.date(y + mo // 12, mo % 12 + 1, 1) - dt.timedelta(days=1)).isoformat()
            else:
                before = [when(x) for x in rows if x["ticker"] == r["ticker"] and x["entity"] == r["entity"]
                          and x["agency"] == r["agency"] and when(x) < r["filed"] and x["id"] != r["id"]]
                d1, d2 = (max(before) if before else start), r["filed"]
            add(r["ticker"], "G-a changed, no date", d1, d2,
                f"Find the {r['agency']} press release on {r['entity']} for this rating action ({r['action']}), dated between {d1} and "
                f"{d2}; also the company's own press releases in that window.", [r["id"]],
                f"{r['agency']} {r['action']} stated without a full date")
    lines = {}
    for r in rows:
        if r["grade"]:
            lines.setdefault((r["ticker"], r["entity"], r["agency"], r["item"]), []).append(r)
    for (t, ent, ag, it), rs in lines.items():                   # G-a (ii): grade changed between filings, no dated action
        by = {}
        for r in rs:
            by.setdefault((when(r), r["filed"]), set()).add(r["grade"])
        pts = sorted(by.items())
        for (k0, g0), (k1, g1) in zip(pts, pts[1:]):
            if g0 != g1 and k0[0] == k1[0]:
                add(t, "G-a changed, no date", k0[0], k1[0], f"Two filings give different {ag} grades for {ent} "
                    f"{it} on the same date {k0[0]}; check the {ag} announcement for that date.",
                    [r["id"] for r in rs if when(r) == k0[0]], f"{ag} {it}: {'/'.join(sorted(g0))} vs {'/'.join(sorted(g1))}")
            elif g0 != g1 and not dated_action(t, ent, ag, k0[0], k1[0], {"upgrade", "downgrade", "withdrawn", "assigned"},
                                               it):
                add(t, "G-a changed, no date", k0[0], k1[0], f"Find the {ag} press release on {ent} between {k0[0]} "
                    f"and {k1[0]}; also the company's own press releases in that window.",
                    [r["id"] for r in rs if when(r) in (k0[0], k1[0])],
                    f"{ag} {it} moved {'/'.join(sorted(g0))} to {'/'.join(sorted(g1))} with no dated action")
    looks = {}
    for r in rows:
        if r["outlook"]:
            looks.setdefault((r["ticker"], r["entity"], r["agency"]), {}).setdefault(when(r), set()).add(r["outlook"])
    for (t, ent, ag), pts in looks.items():                      # G-a (iii): outlook changed, no dated action
        pts = sorted(pts.items())
        for (d0, o0), (d1, o1) in zip(pts, pts[1:]):
            if o0 != o1 and not dated_action(t, ent, ag, d0, d1, {"outlook change", "watch placed", "watch removed",
                                                                  "upgrade", "downgrade", "withdrawn"}):
                ids = [r["id"] for r in rows if r["ticker"] == t and r["entity"] == ent and r["agency"] == ag
                       and r["outlook"] and when(r) in (d0, d1)]
                add(t, "G-a changed, no date", d0, d1, f"Find the {ag} announcement on {ent} between {d0} and {d1}.",
                    ids, f"{ag} outlook moved {'/'.join(sorted(o0))} to {'/'.join(sorted(o1))} with no dated action")
    seen = {}
    for r in rows:
        seen.setdefault((r["ticker"], r["entity"], r["agency"]), set()).add(when(r))
    for (t, ent, ag), ds in seen.items():                        # G-b: silent for more than 15 months
        ds = sorted(ds)
        for d0, d1 in zip(ds, ds[1:] + [as_of]):
            if days(d1, d0) > SILENT_DAYS:
                add(t, "G-b silent", d0, d1, f"Check {ag}'s announcements on {ent} between {d0} and {d1}.",
                    [r["id"] for r in rows if r["ticker"] == t and r["entity"] == ent and r["agency"] == ag and
                     when(r) == d0], f"no {ag} statement on {ent} for {days(d1, d0)} days")
    for t, v in tickers.items():                                 # G-a: an action stated with no agency named
        for u in v.get("unnamed", [])[:5]:
            add(t, "G-a changed, no agency named", start, u["filed"],
                f"The {u['form']} filed {u['filed']} says: \"{u['sentence'][:220]}\" It names no agency, so no row can be "
                f"kept. Find the S&P, Moody's and Fitch announcements on {v['name']} before {u['filed']}.", [],
                "a rating action stated without naming the agency")
    for t, v in tickers.items():                                 # G-c: nothing to read
        if not v["filings"] and not v["manual"]:
            src, first = str(v.get("source", "")), v.get("first_filed", "")
            if not v.get("cik"):                                 # no SEC number: a Canada-only firm
                add(t, "G-c nothing to read", start, as_of,
                    "No SEC filings. Download the latest Annual Information Form and MD&A from SEDAR+ (sedarplus.ca) yourself, "
                    f"then give each file's path: run fetch.py {t}=manual --file <path> (the tool copies it into credit-watch/manual/{t}/).", [], "no SEC filings, no manual files")
            elif src.startswith("SEC failed"):
                add(t, "G-c nothing to read", start, as_of,
                    f"SEC did not answer for SEC number {v['cik']} ({src[len('SEC failed: '):][:120]}). Check the number at "
                    "sec.gov/edgar/search, or run again later, or use --offline.", [], "SEC gave no filing list")
            else:
                why = (f"SEC number {v['cik']} files nothing before {first}: the firm was not public yet, or reported "
                       "under an earlier SEC number (a renamed or reorganised firm). Give that number as "
                       f"{t}=CIK (sec.gov/edgar/search)." if first and first > as_of else
                       f"SEC number {v['cik']} filed no 10-K, 10-Q, 8-K, 20-F, 40-F or 6-K in this window (a fund or "
                       "ETF files other forms; an old firm may have reported under another SEC number).")
                add(t, "G-c nothing to read", start, as_of, why + " Not a SEDAR+ case.", [],
                    f"no annual, quarterly or current report filed {start} to {as_of}")
        for u in v.get("cut", []):                                 # read in part: the rest is in the filing
            add(t, "G-c read in part", u.get("filed", ""), u.get("filed", ""), f"Open by hand: {u['url']}", [],
                f"{u.get('form', '')} {u.get('doc_type', '')} filed {u.get('filed', '')}: {u['why']}")
        for u in v.get("unreadable", []):
            add(t, "G-c nothing to read", u.get("filed", ""), u.get("filed", ""), f"Open by hand: {u['url']}", [],
                f"{u.get('form', '')} {u.get('doc_type', '')} could not be read ({u['why']})")
        if (v["filings"] or v["manual"]) and not any(r["ticker"] == t for r in rows):
            named = " by a named agency" if v.get("unnamed") else ""
            add(t, "G-c nothing to read", start, as_of, f"Check each agency's site for {v['name']}; the filings state "
                f"no rating{named}.", [], f"no rating statement{named} in {v['filings']} filings and {v['manual']} manual files")
    merged = []                                  # one undated event stated in several rows or filings: one gap
    for g in out:
        same = next((m for m in merged if g["rule"] == m["rule"] == "G-a changed, no date" and
                     (g["ticker"], g["from"], g["to"]) == (m["ticker"], m["from"], m["to"]) and
                     g["what"].split(" ")[0] == m["what"].split(" ")[0] and g["what"].endswith("without a full date")
                     and m["what"].endswith("without a full date")), None)
        if same:
            same["rows"] += [r for r in g["rows"] if r not in same["rows"]]
            if g["what"] not in same["what"]:
                same["what"] = same["what"].replace(" stated without a full date", "") + " and " + g["what"]
        else:
            merged.append(g)
    for k, g in enumerate(merged, 1):
        g["id"] = f"G{k}"
    return merged


def load_rows(path: Path) -> list:
    if not path.exists():
        sys.exit(f"missing {path}: write the rows first (step 2)")
    try:
        data = C.read_json(path)
    except json.JSONDecodeError as e:
        sys.exit(f"{path} is not valid JSON: {e}")
    return data.get("rows", []) if isinstance(data, dict) else data


def cell(s) -> str:
    return str(s).replace("|", "/").replace("\n", " ")


def write_md(res: dict, path: Path):
    """Write ratings.md: one row per kept rating with its quote and link, then gaps and set-aside rows."""
    L = [f"# Credit watch: ratings found in filings", "",
         f"Made {res['made']}. Filings read: filed {res['window_start']} to {res['as_of']}. "
         "Every row below quotes its passage word for word (for a table, the 'Row:' line the code built from the table). Check any row by opening its link.", ""]
    for t, v in res["tickers"].items():
        L.append(f"- {t} {v['name']}: {v['filings']} filings, {v['documents']} documents, {v['manual']} manual files; "
                 f"source {v['source']}.")
    L += ["", "## Ratings", "",
          "| Row | Company | Rated entity | Agency | Rated item | Grade | Outlook or watch | Action | Rating date | "
          "Date kind | Filed | Lag days | Form | Link | Read by | Quote |", "|" + "---|" * 16]
    for r in res["rows"]:
        L.append("| " + " | ".join(cell(x) for x in [
            r["id"], r["ticker"], r["rated_entity"], r["agency"], r["what_is_rated"], r["grade"] or "",
            r["outlook_or_watch"], r["action"], r["rating_date"], r["date_kind"], r["filed"],
            "" if r["lag_days"] is None else r["lag_days"], r["form"], f"[{r['doc_type']}]({r['url']})",
            r.get("read", ""), '"' + r["quote"] + '"']) + " |")
    L += ["", "Lag days = filing date minus rating date. Date kind 'action' is the day the agency acted; 'as_of' is the "
          "day a ratings table is stated for. Read by 'table cell': code matched the grade to the agency's cell of the "
          "quoted table row. 'AI-read text: verify quote': an AI read the sentence; code checked that the quote is word "
          "for word, names the agency and holds the grade, outlook and action word, and that a sentence of the passage holding the date also holds an action word (an action) or 'as of', 'as at', 'at' or 'ended' (a stated-as-of grade); a person checks that they "
          "belong together.", "", "## Gaps", ""]
    if not res["gaps"]:
        L.append("None.")
    for g in res["gaps"]:
        L.append(f"- {g['id']} {g['ticker']} {g['rule']} ({g['from']} to {g['to']}): {g['what']}. Follow up: "
                 f"{g['follow_up']}" + (f" Rows: {', '.join(g['rows'])}." if g["rows"] else ""))
    L += ["", "## Set aside", ""]
    if not res["set_aside"]:
        L.append("None.")
    for s in res["set_aside"]:
        L.append(f"- {s.get('ticker', '')} {s.get('passage_id', '')} {s.get('form', '')} {s.get('filed', '')}: "
                 f"{s['why']}" + (f" — \"{cell(s.get('quote') or s.get('text', ''))[:200]}\"" if s.get('quote') or s.get('text') else ""))
    L += ["", f"Skipped by the keyword lookup (no grade, outlook or dated action): "
          + ", ".join(f"{t} {v.get('skipped', 0)}" for t, v in res["tickers"].items()) + ". Credit-agreement "
          "passages skipped: " + ", ".join(f"{t} {v.get('terms_skipped', 0)}" for t, v in res["tickers"].items()) + ".",
          "", "Tables with no kept row: " + (", ".join(res.get("empty_tables", [])) or "none") + ".",
          "Table cells with no kept row: " + ("; ".join(f"{c['passage_id']} {c['agency']} {c['missing']}"
                                                         for c in res.get("missing_cells", [])) or "none") + ".",
          "Action sentences with no kept row: " + ("; ".join(f"{a['passage_id']} \"{a['sentence']}\""
                                                            for a in res.get("missing_actions", [])) or "none") + ".", "",
          "## Notes to write", "", ", ".join(res["notes"]) or "None.", ""]
    path.write_text("\n".join(L))


def main():
    """Check every row of rows.json against passages.json, count the check round, and write ratings.json/.md."""
    run = C.RUN
    pf = run / "passages.json"
    if not pf.exists():
        sys.exit(f"missing {pf}: run fetch.py first")
    ps = C.read_json(pf)
    passages = {p["id"]: p for p in ps["passages"]}
    tickers = ps["tickers"]
    rows_in = load_rows(run / "rows.json")
    rnd_file = run / "check_round.txt"
    again = "--again" in sys.argv[1:]
    rnd = int(rnd_file.read_text()) + 1 if rnd_file.exists() and not again else 1
    if rnd > 2:
        print("check.py already ran twice. Rows are final; ratings.md is unchanged. Go to step 4.")
        return
    filing = {}                                  # every passage of one filing: a subsidiary named anywhere in it counts
    for p in ps["passages"]:
        filing[p["url"].rsplit("/", 1)[0]] = filing.get(p["url"].rsplit("/", 1)[0], "") + "\n" + p["text"]
    kept, aside, keys = [], [], {}
    for k, row in enumerate(rows_in, 1):
        if not isinstance(row, dict):
            aside.append({"why": f"C0 row {k} is not an object"})
            continue
        p = passages.get(str(row.get("passage_id", "")).strip())
        tk = tickers.get(p["ticker"]) if p else None
        why, n = check_row(row, p, tk, filing.get(p["url"].rsplit("/", 1)[0], "") if p else "")
        if not why:
            r = n["row"]
            key = (r["passage_id"], n["agency"], n["entity"], n["item"], n.get("grade"), n.get("outlook"), r["action"],
                   r["rating_date"], r["date_kind"])
            if key in keys:
                why = [f"C4 duplicate of row {keys[key]} of rows.json"]
            else:
                keys[key] = k
        if why:
            aside.append({"ticker": p["ticker"] if p else "", "passage_id": row.get("passage_id", ""),
                          "form": p["form"] if p else "", "filed": p["filed"] if p else "", "rows_json_row": k,
                          "why": "; ".join(why), "quote": str(row.get("quote", ""))})
            continue
        r = n["row"]
        if r["action"] == "outlook change" and n.get("outlook", "").startswith("watch"):
            r = {**r, "action": "watch placed"}      # one name per action: a move onto watch is 'watch placed'
        kept.append({**r, "agency": n["agency"], "grade": n.get("grade") or "", "outlook": n.get("outlook", ""),
                     "entity": n["entity"], "item": n["item"], "read": n["read"], "ticker": p["ticker"],
                     "company": p["company"],
                     "form": p["form"], "doc_type": p["doc_type"], "filed": p["filed"], "url": p["url"],
                     "lag_days": days(p["filed"], r["rating_date"]) if r["rating_date"] else None,
                     "id": f"R{k}"})                      # R# = row number in rows.json: stable when other rows fail
    first = {}                                   # one sentence repeated in a later filing: row only for the first
    for r in sorted(kept, key=lambda r: (r["filed"], int(r["id"][1:]))):
        if r["date_kind"] != "action" or r["quote"].startswith("Row:"):
            continue
        key = (r["ticker"], r["agency"], r["entity"], r["item"], r["grade"], r["outlook"], r["action"],
               r["rating_date"])                 # the same dated action, however a later filing words it
        if key in first and first[key]["filed"] < r["filed"]:
            r["repeat_of"] = first[key]["id"]
        else:
            first.setdefault(key, r)
    for r in [r for r in kept if not r["grade"] and not r["outlook"]]:   # adds nothing to a row of the same quote
        twin = next((x for x in kept if x is not r and (x["grade"] or x["outlook"]) and x["agency"] == r["agency"]
                     and x["entity"] == r["entity"] and x["passage_id"] == r["passage_id"]
                     and C.norm_space(x["quote"]) == C.norm_space(r["quote"])), None)
        if twin and r["action"] in ("affirmed", "reviewed", "withdrawn") and r["action"] != twin["action"]:
            continue                             # 'revised the outlook ... and affirmed': two facts, both kept
        if twin:
            kept.remove(r)
            aside.append({"ticker": r["ticker"], "passage_id": r["passage_id"], "form": r["form"], "filed": r["filed"],
                          "rows_json_row": int(r["id"][1:]), "why": f"C4 adds nothing: {twin['id']} states this "
                          f"agency's rating from the same quote", "quote": r["quote"]})
    for r in [r for r in kept if r.get("repeat_of")]:
        kept.remove(r)
        aside.append({"ticker": r["ticker"], "passage_id": r["passage_id"], "form": r["form"], "filed": r["filed"],
                      "rows_json_row": int(r["id"][1:]), "why": f"C4 repeat of {r['repeat_of']}: same dated action, "
                      f"first filed {next(x['filed'] for x in kept if x['id'] == r['repeat_of'])}; keep the first only",
                      "quote": r["quote"]})
    used = {r["passage_id"] for r in kept}
    empty = [p["id"] for p in ps["passages"] if p["kind"] == "table" and p["id"] not in used]
    cells = missing_cells(ps["passages"], kept, tickers)
    acts = missing_actions(ps["passages"], kept + [{"quote": a["quote"]} for a in aside if a["why"].startswith("C4 repeat")])
    gaps = gaps_for(kept, tickers, ps["as_of"], ps["window_start"])
    names = list(tickers)
    notes = names                                # every company gets a note
    res = {"made": dt.datetime.now().isoformat(timespec="seconds"), "as_of": ps["as_of"],
           "window_start": ps["window_start"], "tickers": tickers, "rows": kept, "gaps": gaps,
           "set_aside": ps.get("set_aside", []) + aside, "notes": notes, "round": rnd,
           "empty_tables": empty, "missing_cells": cells, "missing_actions": acts,
           "passage_tickers": {p["id"]: p["ticker"] for p in ps["passages"]}}
    rnd_file.write_text(str(rnd))             # a round counts only once its rows were checked without error
    C.write_json(run / "ratings.json", res)
    write_md(res, run / "ratings.md")
    print(f"check round {rnd}: {len(kept)} rows kept, {len(aside)} set aside, {len(gaps)} gaps")
    for a in aside:
        print(f"  REJECTED rows.json row {a.get('rows_json_row', '?')} ({a.get('passage_id', '')}): {a['why']}")
    if cells:
        print(f"  table cells with no kept row: " + "; ".join(f"{c['passage_id']} {c['agency']} ({c['missing']}): "
              f"{c['line'][:70]}" for c in cells[:12]) + (" ..." if len(cells) > 12 else ""))
    if acts:
        print(f"  action sentences with no kept row: " + "; ".join(f"{a['passage_id']}: \"{a['sentence'][:90]}\""
                                                                for a in acts[:8]) + (" ..." if len(acts) > 8 else ""))
    if (aside or empty or cells or acts) and rnd == 1:
        print("Fix the rejected rows once in rows.json (correct them or delete them), and add the rows the lines above "
              "show missing. Then run check.py again.")
    elif rnd > 1:
        print("Final check. Do not edit rows.json again.")
    if empty:
        print(f"  tables with no kept row: {', '.join(empty)}. Read each one again: add its rows, or leave it if it "
              "states no rating.")
    print(f"notes to write: {', '.join(notes) or 'none'}")
    print(f"wrote {(run / 'ratings.md').resolve()} and ratings.json")


if __name__ == "__main__":
    main()
