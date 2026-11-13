"""The note is written by code: every line that cites rows may state only those rows' values.

Runs check.py and finish.py on a saved run (HON RY SJ, 152 rows) and checks each note line that
cites R# ids: every grade, ISO date, day count and agency in the line belongs to a cited row.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1] / "skills" / "credit-watch"
TOOLS = SKILL / "tools"
FIX = Path(__file__).resolve().parent / "fixtures" / "hon-ry-sj-2026-11-07"   # saved passages.json and rows.json
sys.path.insert(0, str(TOOLS))
import common as C  # noqa: E402
import check as K  # noqa: E402
import fetch as F   # noqa: E402


def bad_values(line: str, cited: list) -> list:
    """Values in a note line that no cited row holds."""
    out = []
    body = re.sub(r"\[[^\]]*\]|\([^)]*verify[^)]*\)", " ", line)
    names = " ".join(r["entity"] + " " + r["what_is_rated"] for r in cited)
    grades = {r["grade"] for r in cited} | {g for r in cited for g in F.grade_tokens(r["what_is_rated"], True)}
    for g in F.grade_tokens(re.sub(re.escape(names) if names else "^$", " ", body), True):
        if C.grade(cited[0]["agency"], g) not in grades and g not in grades and g not in names:
            out.append(f"grade {g}")
    dates = {r["rating_date"] for r in cited} | {r["filed"] for r in cited}
    out += [f"date {d}" for d in re.findall(r"\d{4}-\d{2}-\d{2}", body) if d not in dates]
    lags = {r["lag_days"] for r in cited}
    out += [f"lag {n}" for n in re.findall(r"(\d+) days", body) if int(n) not in lags]
    out += [f"agency {a}" for a in C.AGENCIES if C.agency_in(body, a) and a not in {r["agency"] for r in cited}]
    return out


class NoteFromRows(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.d = Path(tempfile.mkdtemp())
        run = cls.d / "credit-watch/run"
        run.mkdir(parents=True)
        for f in ("passages.json", "rows.json"):
            shutil.copy(FIX / f, run / f)
        env = {**os.environ, "CREDIT_WATCH_SCORES": str(cls.d / "none.csv")}
        subprocess.run([sys.executable, str(TOOLS / "check.py"), "--again"], cwd=cls.d, capture_output=True, env=env)
        r = subprocess.run([sys.executable, str(TOOLS / "finish.py")], cwd=cls.d, capture_output=True, text=True, env=env)
        assert r.returncode == 0, r.stdout + r.stderr
        cls.res = json.loads((run / "ratings.json").read_text())
        cls.rows = {r["id"]: r for r in cls.res["rows"]}
        cls.notes = {t: (run / f"note_{t}.md").read_text() for t in cls.res["notes"]}
        cls.table = (run / "ratings.md").read_text()

    def test_every_ticker_has_a_note(self):
        self.assertEqual(sorted(self.notes), ["HON", "RY", "SJ"])

    def test_each_cited_line_states_only_its_rows(self):
        checked = 0
        for t, text in self.notes.items():
            body = text.split("## Sources")[0]
            for line in body.splitlines():
                ids = re.findall(r"\bR\d+\b", " ".join(re.findall(r"\[([^\]]*)\]", line)))
                if not ids or line.startswith("- Open the filing link"):
                    continue
                cited = [self.rows[i] for i in ids]
                self.assertTrue(all(r["ticker"] == t for r in cited), line)
                if "before a filing reported it" in line or "trail their as-of date by" in line:   # two-dates line:
                    m = re.findall(r"(\d+) to (\d+) days", line) or [(re.findall(r"(\d+) days?", line)[0],) * 2]  # low, high
                    lo, hi = map(int, m[0])
                    self.assertEqual({lo, hi} - {r["lag_days"] for r in cited}, set(), line)
                    checked += 1                             # checked: its low and high lags are the cited rows'
                    continue
                self.assertEqual(bad_values(line, cited), [], line)
                checked += 1
        self.assertGreater(checked, 20)

    def test_every_ratings_table_row_states_only_its_row(self):
        """ratings.md replaced the evidence file: each R# row holds its own quote in full, its own link and its own values."""
        checked = 0
        ids = set()
        for line in self.table.splitlines():
            m = re.match(r"\| (R\d+) \|", line)
            if not m:
                continue
            r = self.rows[m.group(1)]
            ids.add(r["id"])
            self.assertIn('"' + K.cell(r["quote"]) + '"', line)                # its own quote, uncut ('|' shown as '/')
            self.assertIn(r["url"], line)
            head = re.sub(r'\[[^\]]*\]\([^)]*\).*$', " ", line)                 # the row's values, before link and quote
            self.assertEqual(bad_values(head, [r]), [], line)
            checked += 1
        self.assertEqual(ids, set(self.rows))                                    # every row, once
        self.assertGreater(checked, 100)
        self.assertFalse(list((self.d / "credit-watch/run").glob("evidence_*.md")))

    def test_no_advice_or_model_words_outside_score_part(self):
        for text in self.notes.values():
            rest = text.split("## Ratings now")[1]
            self.assertIsNone(re.search(r"\b(buy|sell|hold|recommend\w*|probabilit\w*|likely|expect\w*)\b", rest,
                                        re.I), rest[:200])

    def test_ai_read_rows_are_marked(self):
        hon = self.notes["HON"]
        for r in self.res["rows"]:
            if r["ticker"] == "HON" and r["read"] != "table cell":
                self.assertIn(r["id"], hon.split("## What to check next")[1].split("## Sources")[0])


if __name__ == "__main__":
    unittest.main()
