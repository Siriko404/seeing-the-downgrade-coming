"""Tests for problems found in live runs: false 'no dated action' gaps (Ford), the manual-file route for
Canada-only firms (TICKER=manual, --offline, a PDF without pypdf), the SKILL.md line against confirming the firm,
a table row that names no item, and run folders.

Each test checks one fix or behaviour; the name of the test says which.
From the agent/ folder, run all tests with: python3 -m unittest discover -s tests
One file only: python3 -m unittest discover -s tests -p test_live_run_fixes.py
Standard library only.
"""
import io
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

SKILL = Path(__file__).resolve().parents[1] / "skills" / "credit-watch"
TOOLS = SKILL / "tools"
sys.path.insert(0, str(TOOLS))
os.environ["CREDIT_WATCH_SCORES"] = str(Path(tempfile.gettempdir()) / "credit-watch-tests-no-scores.csv")
os.environ["CREDIT_WATCH_MODEL"] = ""
import common as C  # noqa: E402
import fetch as F   # noqa: E402
import check as K   # noqa: E402

TK = {"F": {"name": "FORD MOTOR CO", "cik": "37996", "filings": 3, "manual": 0, "documents": 3, "unreadable": [],
            "filing_dates": [], "first_filed": "1990-01-01", "source": "SEC live", "aliases": "", "scope": "",
            "unnamed": [], "cut": []}}


def row(i, item, grade, filed, date="", kind="as_of", action="none"):
    return {"id": f"R{i}", "ticker": "F", "entity": "Ford", "agency": "Moody's", "item": item, "grade": grade,
            "outlook": "", "rating_date": date or filed, "date_kind": kind, "action": action, "filed": filed,
            "quote": f"quote {i}", "passage_id": f"P{i}", "form": "10-Q", "url": "u"}


class GenericActionGapTests(unittest.TestCase):
    """A dated 'downgraded the credit ratings' action explains a move in every item line of that agency."""
    def gaps(self, rows):
        return [g for g in K.gaps_for(rows, TK, "2020-06-30", "2019-01-01") if g["rule"] == "G-a changed, no date"]

    def test_generic_dated_downgrade_explains_an_item_line(self):
        rows = [row(1, "senior unsecured", "Baa3", "2019-07-25"), row(2, "senior unsecured", "Ba1", "2019-10-24"),
                row(3, "credit ratings", "Ba1", "2019-10-24", "2019-09-09", "action", "downgrade")]
        self.assertEqual(self.gaps(rows), [])

    def test_unexplained_move_still_gives_a_gap(self):
        rows = [row(1, "senior unsecured", "Baa3", "2019-07-25"), row(2, "senior unsecured", "Ba1", "2019-10-24"),
                row(3, "short-term", "P-3", "2019-10-24", "2019-09-09", "action", "downgrade")]
        self.assertEqual(len(self.gaps(rows)), 1)


class ManualRouteTests(unittest.TestCase):
    """TICKER=manual reads only the saved manual files; --offline also reads the manual files beside a saved copy; a
    PDF without pypdf says why it was not read."""
    def setUp(self):
        self.d, self.cwd = tempfile.mkdtemp(), os.getcwd()
        os.chdir(self.d)

    def tearDown(self):
        os.chdir(self.cwd)
        shutil.rmtree(self.d)

    def save(self, t, name, body, filed="2026-03-01"):
        d = C.MANUAL / t
        d.mkdir(parents=True, exist_ok=True)
        (d / "source.txt").write_text(f"link: https://www.sedarplus.ca/x\nfiling date: {filed}\nform: AIF\n"
                                      "downloaded by: test\n")
        (d / name).write_bytes(body)

    def test_ticker_equals_manual_reads_only_the_saved_files(self):
        self.save("DOL", "aif.txt", b"S&P Global Ratings rates our senior unsecured notes BBB with a stable outlook.")
        co = F.company("DOL=manual", None)
        self.assertEqual(co["cik"], "")
        res = F.fetch_ticker(None, co, F.dt.date(2025, 1, 1), F.dt.date(2026, 6, 30), lambda *a: None)
        self.assertEqual(res["manual"], 1)
        self.assertEqual(len(res["passages"]), 1)

    def test_offline_reads_manual_files_beside_a_saved_copy(self):
        self.save("HON", "note.txt", b"DBRS Morningstar rates our senior unsecured notes A (high) with a stable trend.")
        with redirect_stdout(io.StringIO()) as out:
            F.main(["HON", "--offline"])
        self.assertIn("1 manual files", out.getvalue())
        ps = C.read_json(C.RUN / "passages.json")["passages"]
        self.assertTrue(any("DBRS Morningstar rates our senior" in p["text"] for p in ps))

    def test_pdf_without_pypdf_says_why(self):
        real = __import__("importlib.util").util.find_spec
        with mock.patch("importlib.util.find_spec", lambda n, *a: None if n == "pypdf" else real(n, *a)):
            self.assertIn("pypdf", F.unread_why("aif.pdf"))
        self.assertEqual(F.unread_why("x.htm"), "document could not be read")


class SkillTextTests(unittest.TestCase):
    """SKILL.md says the AI never confirms the firm and knows the manual route."""
    def test_agent_never_confirms_the_firm_and_knows_the_manual_route(self):
        s = (SKILL / "SKILL.md").read_text()
        self.assertIn("Never tell user it is the firm they meant", s)
        self.assertIn("`TICKER=manual`", s)


if __name__ == "__main__":
    unittest.main()


class UnnamedItemScaleTests(unittest.TestCase):
    """Couche-Tard's AIF (SEDAR+ PDF): a flattened table row names no item. Baa1 and P-2 must not share one line."""
    PASSAGE = ("The table below shows the ratings of our corporate credit, unsecured notes and U.S. commercial paper "
               "program as at April 26, 2026. Moody's rating Baa1 (stable outlook) Baa1 P-2 Long-term debt rating "
               "scale ranges from AAA to C.")

    def norm(self, grade, guess):
        p = {"id": "P1", "kind": "text", "text": self.PASSAGE, "ticker": "ATD", "filed": "2026-06-22",
             "form": "AIF", "doc_type": "manual", "url": "u"}
        tk = {"name": "Alimentation Couche-Tard Inc.", "aliases": "Couche-Tard"}
        row = {"passage_id": "P1", "agency": "Moody's", "rated_entity": "Alimentation Couche-Tard Inc.",
               "what_is_rated": guess, "grade": grade, "outlook_or_watch": "", "action": "none",
               "rating_date": "2026-04-26", "date_kind": "as_of", "quote": "Moody's rating Baa1 (stable outlook) Baa1 P-2"}
        why, n = K.check_row(row, p, tk, self.PASSAGE)
        self.assertEqual(why, [])
        return n["item"]

    def test_long_and_short_grades_get_separate_items(self):
        self.assertEqual(self.norm("Baa1", "Corporate credit"), "long-term (item not named)")
        self.assertEqual(self.norm("P-2", "U.S. Commercial paper program"), "short-term")

    def test_note_header_counts_manual_files(self):
        self.assertIn("manual files (e.g. SEDAR+)", (TOOLS / "finish.py").read_text())


class SavedRunTests(unittest.TestCase):
    """Every run is saved in its own dated, named folder; no evidence file (ratings.md is enough)."""
    def setUp(self):
        self.d = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.d)

    def run_tool(self, *args):
        r = subprocess.run([sys.executable, str(TOOLS / args[0]), *args[1:]], cwd=self.d, capture_output=True, text=True,
                           env={**os.environ, "CREDIT_WATCH_MODEL": ""})
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return r.stdout

    def one_run(self, *fetch_args):
        self.run_tool("fetch.py", *fetch_args)
        (self.d / "credit-watch/run/rows.json").write_text('{"rows": []}')
        self.run_tool("check.py")
        return self.run_tool("finish.py")

    def test_each_run_keeps_its_own_folder(self):
        out1 = self.one_run("HON", "--offline")
        first = [ln.split(": ", 1)[1] for ln in out1.splitlines() if ln.startswith("saved run: ")]
        self.assertEqual(len(first), 1)
        folder = Path(first[0])
        self.assertRegex(folder.name, r"^\d{4}-\d{2}-\d{2}_\d{6}_HON(_asof-\d{4}-\d{2}-\d{2})?$")
        self.assertTrue((folder / "note_HON.md").exists() and (folder / "ratings.md").exists())
        self.assertFalse((self.d / "credit-watch/run/evidence_HON.md").exists())
        self.assertFalse(list(folder.glob("evidence_*")))
        self.run_tool("finish.py")                                   # the same run finished again: same folder
        self.assertEqual(len(list((self.d / "credit-watch/runs").iterdir())), 1)
        import time
        time.sleep(1.1)                                              # a new fetch has a new time: a new folder
        self.one_run("RY", "--offline", "--as-of", "2026-05-31")
        names = sorted(p.name for p in (self.d / "credit-watch/runs").iterdir())
        self.assertEqual(len(names), 2, names)
        self.assertTrue(any(n.endswith("_RY_asof-2026-05-31") for n in names), names)
        self.assertTrue((folder / "note_HON.md").exists())          # the first run is still there
