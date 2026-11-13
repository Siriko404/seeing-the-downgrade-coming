"""Shared helpers used by the three code steps (fetch, check, finish): paths, the list of Canada-only firms, rating
scales, name and date clean-up.

Not a step of its own. The one idea worth knowing: filings spell the same thing many ways ("Moody's", "Moodys",
"A-" with three kinds of hyphen), so these helpers turn every spelling into one standard form before the code
compares anything. Python standard library only."""
import csv
import datetime as dt
import json
import os
import re
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent          # folder holding SKILL.md
DATA = SKILL / "data"
CACHE = SKILL / "cache"
ROOT = Path("credit-watch")                             # in the user's working folder
RUN = ROOT / "run"
MANUAL = ROOT / "manual"
CONFIG = Path.home() / ".config" / "credit-watch"
LOCAL_SCORES = Path(os.environ.get("CREDIT_WATCH_SCORES", CONFIG / "scores.csv"))   # written by the model command


def model_launcher() -> str:
    """The model command on this device, or '' where there is none (the trained model is not included in this package).
    Env CREDIT_WATCH_MODEL (empty: none), else the first line of ~/.config/credit-watch/model.txt."""
    if "CREDIT_WATCH_MODEL" in os.environ:
        return os.environ["CREDIT_WATCH_MODEL"].strip()
    try:
        return (CONFIG / "model.txt").read_text().strip().splitlines()[0].strip()
    except (OSError, IndexError):
        return ""

AGENCIES = {  # canonical name: spellings found in filings
    "S&P": ["S&P Global Ratings", "Standard & Poor's", "Standard and Poor's", "S&P"],
    "Moody's": ["Moody's Investors Service", "Moody's Ratings", "Moody's", "Moodys"],
    "Fitch": ["Fitch Ratings", "Fitch"],
    "DBRS Morningstar": ["Morningstar DBRS", "DBRS Morningstar", "DBRS Limited", "DBRS"],
    "A.M. Best": ["A.M. Best", "AM Best", "A. M. Best"],
    "KBRA": ["Kroll Bond Rating Agency", "KBRA"],
}
NOT_AGENCY = re.compile(r"S&P\s*(500|/TSX|MidCap|SmallCap|Dow Jones|Composite|Global Inc|"   # the index or company
                        r"(?<!from S&P )(?<!by S&P )Global\b(?!\s+(Ratings|rated|assign|lower|rais|upgrad|downgrad|"
                        r"affirm|revis|plac|has rated)))", re.I)               # 'BB rating from S&P Global' is the agency

MONTHS = {m: i for i, m in enumerate(["january", "february", "march", "april", "may", "june", "july", "august",
                                      "september", "october", "november", "december"], 1)}
MONTHS.update({k[:3]: v for k, v in list(MONTHS.items())})
MONTHS["sept"] = 9


def canada() -> dict:
    """ticker -> row of data/canada.csv: large firms filing only on SEDAR+, with their own filing link. Used only after
    SEC's list has no such ticker, or by exact name, so a US ticker (L = Loews) is never taken."""
    with open(DATA / "canada.csv", newline="") as f:
        return {r["ticker"].upper().replace(".", "-"): {"ticker": r["ticker"].upper().replace(".", "-"), "name": r["name"],
                "cik": "", "scope": "no SEC reports", "aliases": r["names"],
                "filings_link": r["filings_link"]} for r in csv.DictReader(f)}


def scales() -> dict:
    """The rating scales from data/scales.json: for each agency its long-term and short-term grades and aliases."""
    return json.loads((DATA / "scales.json").read_text())


def agency(name: str) -> str | None:
    """Canonical agency for a spelling, or None."""
    n = (name or "").strip().lower()
    for canon, spellings in AGENCIES.items():
        if n == canon.lower() or any(n == s.lower() for s in spellings):
            return canon
    return None


def agency_in(text: str, canon: str) -> bool:
    """True if the text names this agency under any of its spellings (phrases that only look like agency names are
    ignored)."""
    t = NOT_AGENCY.sub(" ", text)
    return any(re.search(r"(?<![A-Za-z])" + re.escape(s) + r"(?![A-Za-z])", t, re.I) for s in AGENCIES[canon])


def strip_agency(text: str) -> str:
    """Text without agency names ('S&P Current' -> 'Current')."""
    for sp in sorted((x for v in AGENCIES.values() for x in v), key=len, reverse=True):
        text = re.sub(r"(?<![A-Za-z])" + re.escape(sp) + r"(?![A-Za-z])", " ", text, flags=re.I)
    return text


def any_agency(text: str) -> bool:
    """True if the text names any of the known agencies."""
    return any(agency_in(text, a) for a in AGENCIES)


def grade(canon: str, g: str) -> str | None:
    """Normalised grade on the agency's scales, or None if not on them."""
    g = re.sub(r"\s+", " ", (g or "").translate(HYPHENS).strip())
    g = re.sub(r"\((cr|P|hyb|sf)\)|-PD\b|\*|\(\d\)$", "", g).strip()
    if not g or canon not in scales():
        return None
    if "/" in g:                                         # one cell, two grades: 'VMIG-1/P-1'
        parts = [grade(canon, x) for x in g.split("/")]
        return "/".join(parts) if all(parts) else None
    sc = scales()[canon]
    alias = sc.get("aliases", {})
    g2 = alias.get(g, alias.get(g.upper(), g))
    every = sc["long"] + sc["short"]
    squash = lambda x: x.replace(" ", "")
    for v in every:
        if squash(g2) == squash(v):
            return v
    for v in every:
        if squash(g2).lower() == squash(v).lower():
            return v
    return None


def all_grades() -> set:
    """Every grade, and every alias of a grade, on any agency's scales."""
    out = set()
    for sc in scales().values():
        out.update(sc["long"]); out.update(sc["short"]); out.update(sc.get("aliases", {}))
    return out


def outlook(o: str) -> str:
    """Normalised outlook or watch words: 'stable', 'negative', 'positive', 'developing', 'watch negative' ..."""
    o = (o or "").lower()
    if not o.strip():
        return ""
    w = "watch " if re.search(r"watch|review|under review", o) else ""
    for d in ("negative", "positive", "developing", "stable", "evolving"):
        if d in o or (d == "negative" and "downgrade" in o) or (d == "positive" and "upgrade" in o):
            return (w + d).strip()
    return ""                                        # not an outlook or watch


ITEM_SYNONYMS = [  # first match wins: short-term before issuer, secured before senior
    (r"\blegacy senior\b", "legacy senior"),
    (r"\b(issuer default|idr)\b", "issuer default"),
    (r"\b(commercial paper|short[- ]term|vmig|variable rate demand)\b", "short-term"),
    (r"\b(issuer|corporate credit|corporate family|long[- ]term issuer)\b", "issuer"),   # not 'company': a name
    (r"\bdeposits?\b", "deposits"),
    (r"\bsubordinated\b", "subordinated"),
    (r"\bpreferred\b", "preferred"),
    (r"\b(financial strength)\b", "financial strength"),
    (r"\b(first mortgage|mortgage bonds?|(?<!un)secured)\b", "secured"),
    (r"\bdebentures?\b", "debentures"),
    (r"\b(pollution control|revenue bonds?|industrial development)\b", "revenue bonds"),
    (r"\b(senior|unsecured|long[- ]term)\b", "senior unsecured"),
]


def item(text: str) -> str:
    """Rated item reduced to a bucket so 'Senior notes (1)' and 'senior unsecured debt' share one timeline."""
    t = re.sub(r"\(\d+\)|\*|[^a-z\- ]", " ", (text or "").lower())
    for pat, bucket in ITEM_SYNONYMS:
        if re.search(pat, t):
            return bucket
    return re.sub(r"\s+", " ", t).strip() or "unspecified"


DATE_PATTERNS = [
    re.compile(r"\b(?P<m>[A-Za-z]{3,9})\.?\s+(?P<d>\d{1,2}),?\s+(?P<y>\d{4})\b"),       # February 6, 2025
    re.compile(r"\b(?P<d>\d{1,2})\s+(?P<m>[A-Za-z]{3,9})\.?,?\s+(?P<y>\d{4})\b"),       # 6 February 2025
    re.compile(r"\b(?P<y>\d{4})-(?P<mm>\d{2})-(?P<d>\d{2})\b"),                          # 2025-02-06
]


def dates_in(text: str) -> list:
    """Every full calendar date in text: list of (iso, start, end)."""
    out = []
    for p in DATE_PATTERNS:
        for m in p.finditer(text or ""):
            try:
                mo = int(m.group("mm")) if "mm" in p.groupindex else MONTHS.get(m.group("m").lower().rstrip("."))
                if not mo:
                    continue
                d = dt.date(int(m.group("y")), mo, int(m.group("d")))
            except (ValueError, TypeError):
                continue
            out.append((d.isoformat(), m.start(), m.end()))
    return out


ABBREV = re.compile(r"(?:\b[A-Z]|\b(?:Inc|Corp|Ltd|Co|No|Nos|Mr|Ms|Dr|St|Jr|Sr|vs|approx|U\.S|N\.A|S\.A|L\.P))\.$")


def sentences(text: str) -> list:
    """Sentences of text: split after . ! ? before a capital or '(', never after an initial (J.P.) or Inc. Co. N.A."""
    out, start = [], 0
    for m in re.finditer(r"(?<=[.!?])\s+(?=[A-Z(\u2022\u25aa])|\n+", text or ""):
        if "\n" in m.group(0) or not ABBREV.search(text[max(0, m.start() - 12):m.start()]):
            out.append(text[start:m.start()])
            start = m.end()
    out.append((text or "")[start:])
    return [x for x in out if x.strip()]


HYPHENS = str.maketrans({"\u2010": "-", "\u2011": "-", "\u2012": "-", "\u2212": "-", "\u00ad": None})  # 'P‑2' = 'P-2'


def norm_space(s: str) -> str:
    """The text with each run of white space made one space, special hyphens and curly quotes made plain, and the ends
    trimmed."""
    return re.sub(r"\s+", " ", (s or "").translate(HYPHENS).replace(" ", " ").replace("’", "'").replace("‘", "'")
                  .replace("“", '"').replace("”", '"')).strip()


def read_json(p: Path):
    """The content of a JSON file."""
    return json.loads(Path(p).read_text())


def write_json(p: Path, obj) -> None:
    """Write obj to a JSON file (indent 1, non-ASCII kept) and make its folder first if needed."""
    Path(p).parent.mkdir(parents=True, exist_ok=True)
    Path(p).write_text(json.dumps(obj, indent=1, ensure_ascii=False))
