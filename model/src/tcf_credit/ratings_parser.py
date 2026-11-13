"""Pipeline step 2: read the credit-rating histories that rating agencies publish under SEC Rule 17g-7(b).

Goes in:  the agencies' ZIP archives (S&P, Fitch, Moody's), downloaded by hand from the agencies' public rating-history
          pages; the file name patterns are SP-Corporate-*.zip, SP-Financial-*.zip, SP-Insurance-*.zip,
          Fitch_Ratings-*.zip and xbrl100-obligor-*.zip (SOURCES below).
Comes out: ratings_obligor_events.csv.gz (one row per rating action of a company: agency, company name, rating,
          action date, action type such as downgrade, outlook, CreditWatch) and MANIFEST.txt (what was read, with a
          checksum of the table).
Data:     public data only.

Each agency posts its full rating history as XBRL files (a tagged-XML format) in ZIP archives. This module reads the
issuer-level rating events (the rating of the company itself) and writes one table.

Ratings of single bonds are skipped. The table has no bond-identifier column: those identifiers are licensed and may
not be redistributed.

Command line:
    python -m tcf_credit.ratings_parser DATA_DIR OUT_DIR
where DATA_DIR holds the ZIP files whose name patterns are listed in SOURCES below.
"""
from __future__ import annotations

import csv
import gzip
import hashlib
import re
import sys
import zipfile
from pathlib import Path
from typing import Callable, Iterator

COLUMNS = [
    "agency", "source_file_date", "sec_class", "obligor_name", "obligor_id", "lei", "rating",
    "action_date", "action_class", "rating_type", "rating_subtype", "rating_term",
    "outlook", "watch", "issuer_paid", "action_note",
]

# agency -> (file name pattern, which archive members to read)
SOURCES: list[tuple[str, str, Callable[[str], bool]]] = [
    ("S&P", "SP-Corporate-*.zip", lambda n: n.endswith("OBLIGOR.xml")),
    ("S&P", "SP-Financial-*.zip", lambda n: n.endswith("OBLIGOR.xml")),
    ("S&P", "SP-Insurance-*.zip", lambda n: n.endswith("OBLIGOR.xml")),
    ("Fitch", "Fitch_Ratings-*.zip",
     lambda n: any(k in n for k in ("-Corporate-", "-Financial-", "-Insurance-"))),
    ("Moody's", "xbrl100-obligor-*.zip", lambda n: True),
]

_OBLIGOR = re.compile(r"<(?:\w+:)?OD>(.*?)</(?:\w+:)?OD>", re.S)
_RATING = re.compile(r"<(?:\w+:)?ORD>(.*?)</(?:\w+:)?ORD>", re.S)


def _field(block: str, name: str) -> str:
    """The text of one XML tag inside a block, or empty."""
    m = re.search(r"<(?:\w+:)?%s(?:\s[^>]*)?>([^<]*)<" % name, block)
    return m.group(1).strip().strip('"') if m else ""


def _unescape(s: str) -> str:
    """Turn XML escapes such as &amp; back into characters."""
    for a, b in (("&amp;", "&"), ("&apos;", "'"), ("&quot;", '"'), ("&lt;", "<"), ("&gt;", ">")):
        s = s.replace(a, b)
    return s


def parse_xbrl(agency: str, file_date: str, text: str) -> Iterator[list[str]]:
    """Yield one row (see COLUMNS) for every obligor-level rating event in one XBRL document."""
    for od in _OBLIGOR.findall(text):
        name = _unescape(_field(od, "OBNAME"))
        obligor_id, lei, sec_class = _field(od, "OI"), _field(od, "LEI"), _field(od, "OSC")
        for r in _RATING.findall(od):
            yield [
                agency, file_date, sec_class, name, obligor_id, lei, _field(r, "R"),
                _field(r, "RAD"), _field(r, "RAC"),
                _unescape(_field(r, "RT")), _unescape(_field(r, "RST")), _unescape(_field(r, "RTT")),
                _field(r, "ROL"), _field(r, "WST"), _field(r, "IP"), _unescape(_field(r, "OAN")),
            ]


def parse_archives(data_dir: Path, out_dir: Path) -> dict[str, int]:
    """Parse every archive found in data_dir; write the table and a manifest to out_dir."""
    out_dir.mkdir(parents=True, exist_ok=True)
    table = out_dir / "ratings_obligor_events.csv.gz"
    counts: dict[str, int] = {}
    notes: list[str] = []
    with gzip.open(table, "wt", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(COLUMNS)
        for agency, pattern, pick in SOURCES:
            for zpath in sorted(data_dir.glob(pattern)):
                file_date = re.search(r"(\d{4}-\d\d-\d\d)", zpath.name)
                file_date = file_date.group(1) if file_date else ""
                read = 0
                with zipfile.ZipFile(zpath) as z:
                    for member in z.namelist():
                        if not pick(member):
                            continue
                        read += 1
                        text = z.read(member).decode("utf-8", errors="replace")
                        for row in parse_xbrl(agency, file_date, text):
                            writer.writerow(row)
                            counts[agency] = counts.get(agency, 0) + 1
                notes.append(f"{agency} {zpath.name}: {read} files read")
    digest = hashlib.sha256(table.read_bytes()).hexdigest()
    manifest = ["Obligor-level rating events from SEC Rule 17g-7 files.", *notes,
                "Rows: " + ", ".join(f"{a} {n}" for a, n in counts.items()),
                f"{table.name} sha256 {digest}",
                "Rating events of single bonds, and bond identifiers, are not included."]
    (out_dir / "MANIFEST.txt").write_text("\n".join(manifest) + "\n", encoding="utf-8")
    return counts


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    print(parse_archives(Path(sys.argv[1]), Path(sys.argv[2])))
