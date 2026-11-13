"""The package keeps no list of companies. Firms come from the SEC's own list (live) or from the saved copies in
cache/ (--offline).
From the agent/ folder, run all tests with: python3 -m unittest discover -s tests
One file only: python3 -m unittest discover -s tests -p test_no_company_list.py
Standard library only.
"""
import io
import json
import os
import shutil
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

HERE = Path(__file__).resolve().parent
AGENT = HERE.parent
SKILL = AGENT / "skills" / "credit-watch"
os.environ["CREDIT_WATCH_SCORES"] = str(Path(tempfile.gettempdir()) / "credit-watch-tests-no-scores.csv")
os.environ["CREDIT_WATCH_MODEL"] = ""
import sys  # noqa: E402
sys.path.insert(0, str(SKILL / "tools"))
import common as C  # noqa: E402
import fetch as F   # noqa: E402

LABELS = ("TCF holding", "TCF TSX", "TCF S&P", "TCF watchlist", "TCF analyst")


class NoCompanyListTests(unittest.TestCase):
    """No company list exists; firms resolve from the saved copies offline and from the SEC list live."""
    def test_company_list_file_does_not_exist_and_no_code_opens_it(self):
        self.assertFalse((SKILL / "data" / "companies.csv").exists())
        self.assertFalse(hasattr(C, "companies"))
        name = "companies" + ".csv"                       # split, so this test does not name the file itself
        for f in (SKILL / "tools").glob("*.py"):
            self.assertNotIn(name, f.read_text(), f.name)
        self.assertNotIn(name, (SKILL / "SKILL.md").read_text())

    def test_no_file_labels_a_firm_as_a_fund_holding(self):
        hits = []
        for f in AGENT.rglob("*"):
            if not f.is_file() or "__pycache__" in f.parts or f.suffix == ".pyc" or f.resolve() == Path(__file__).resolve():
                continue
            text = f.read_text(errors="ignore")
            hits += [f"{f.relative_to(AGENT)}: {x}" for x in LABELS if x in text]
        self.assertEqual(hits, [])

    def test_offline_hon_resolves_from_the_saved_copy(self):
        co = F.company("HON", None)
        self.assertEqual((co["ticker"], co["cik"], co["name"]), ("HON", "773840", "Honeywell International Inc."))
        self.assertEqual(F.company("773840", None)["ticker"], "HON")
        self.assertEqual(F.company("honeywell international inc", None)["ticker"], "HON")

    def test_offline_run_for_hon_needs_no_list(self):
        d, cwd = tempfile.mkdtemp(), os.getcwd()
        os.chdir(d)
        try:
            with redirect_stdout(io.StringIO()) as out:
                F.main(["HON", "--offline"])
            self.assertIn("firm: HON = Honeywell International Inc., CIK 773840", out.getvalue())
            ps = json.loads((C.RUN / "passages.json").read_text())
            self.assertEqual(list(ps["tickers"]), ["HON"])
            self.assertTrue(ps["passages"])
        finally:
            os.chdir(cwd)
            shutil.rmtree(d)

    def test_offline_unknown_firm_stops_with_one_plain_line(self):
        with self.assertRaises(SystemExit) as e:
            F.company("QQZZ", None)
        self.assertIn("saved copies", str(e.exception))
        self.assertIn("TICKER=CIK", str(e.exception))

    def test_stella_jones_by_name_goes_the_file_route(self):
        old = F.sec_firms
        F.sec_firms = lambda sec: [("1753673", "SJ", "Scienjoy Holding Corp", "Nasdaq")]
        try:
            self.assertEqual(F.company("SJ", object())["sec_name"], "Scienjoy Holding Corp")   # SEC's answer, accepted
            with self.assertRaises(SystemExit) as e:
                F.company("Stella-Jones", object())
            self.assertIn("SEDAR+", str(e.exception))
            self.assertIn("--file", str(e.exception))
        finally:
            F.sec_firms = old
        co = F.company("SJ=manual", None)
        self.assertEqual((co["ticker"], co["cik"]), ("SJ", ""))

    def test_sec_number_with_no_filings_stops_with_the_file_route(self):
        """A live run: "Stella-Jones" matched SEC's Stella-Jones Inc./ADR (CIK 2077242), which has no
        filings; the tool must say so in a block, so the AI does not guess other names."""
        d, cwd = tempfile.mkdtemp(), os.getcwd()
        saved = (F.company, F.fetch_ticker, F.run_model, F.Sec, C.CACHE, os.environ.get("SEC_CONTACT"))
        co = {"ticker": "STJNY", "cik": "2077242", "name": "Stella-Jones Inc./ADR", "scope": "", "matched": "test"}

        class NoSec:
            """A stand-in for the SEC client that makes no request."""
            requests = 0

            def __init__(self, *a):
                pass
        F.company = lambda arg, sec: dict(co)
        F.fetch_ticker = lambda sec, c, start, end, say: {
            "ticker": "STJNY", "name": c["name"], "cik": c["cik"], "scope": "", "aliases": "", "filings": 0,
            "documents": 0, "unreadable": [], "manual": 0, "passages": [], "set_aside": [], "skipped": 0,
            "source": "SEC live", "unnamed": [], "cut": []}
        F.run_model = lambda ciks, end: "model: not on this device"
        F.Sec, C.CACHE = NoSec, Path(d) / "cache"
        os.environ["SEC_CONTACT"] = "Test Person test@example.com"
        os.chdir(d)
        try:
            with redirect_stdout(io.StringIO()) as out:
                F.main(["Stella-Jones"])
            text = out.getvalue()
            self.assertIn("STJNY: no filings to read.", text)
            self.assertIn(F.BLOCK_START, text)
            self.assertIn("Stella-Jones Inc./ADR (SEC number 2077242) has filed no report this tool reads", text)
            self.assertIn("download its latest Annual Information Form (PDF)", text)
            self.assertIn("=manual --file <path>", text)
        finally:
            os.chdir(cwd)
            F.company, F.fetch_ticker, F.run_model, F.Sec, C.CACHE, old = saved
            if old is None:
                os.environ.pop("SEC_CONTACT", None)
            else:
                os.environ["SEC_CONTACT"] = old
            shutil.rmtree(d)

    def test_no_filings_block_only_for_one_firm_asked_live(self):
        """Offline (SEC never asked) and runs of several firms get no stop block; the note's gap G-c covers them."""
        d, cwd = tempfile.mkdtemp(), os.getcwd()
        os.chdir(d)
        try:
            with redirect_stdout(io.StringIO()) as out:
                F.main(["XYZ=2077242", "--offline"])
            self.assertNotIn(F.BLOCK_START, out.getvalue())
        finally:
            os.chdir(cwd)
            shutil.rmtree(d)
        d = tempfile.mkdtemp()
        saved = (F.company, F.fetch_ticker, F.run_model, F.Sec, C.CACHE, os.environ.get("SEC_CONTACT"))

        class NoSec:
            """A stand-in for the SEC client that makes no request."""
            requests = 0

            def __init__(self, *a):
                pass
        F.company = lambda arg, sec: {"ticker": arg, "cik": "1", "name": arg, "scope": "", "matched": "test"}
        F.fetch_ticker = lambda sec, c, start, end, say: {
            "ticker": c["ticker"], "name": c["name"], "cik": c["cik"], "scope": "", "aliases": "", "filings": 0,
            "documents": 0, "unreadable": [], "manual": 0, "passages": [], "set_aside": [], "skipped": 0,
            "source": "SEC live", "unnamed": [], "cut": []}
        F.run_model = lambda ciks, end: "model: not on this device"
        F.Sec, C.CACHE = NoSec, Path(d) / "cache"
        os.environ["SEC_CONTACT"] = "Test Person test@example.com"
        os.chdir(d)
        try:
            with redirect_stdout(io.StringIO()) as out:
                F.main(["AAA", "BBB"])
            self.assertNotIn(F.BLOCK_START, out.getvalue())
        finally:
            os.chdir(cwd)
            F.company, F.fetch_ticker, F.run_model, F.Sec, C.CACHE, old = saved
            if old is None:
                os.environ.pop("SEC_CONTACT", None)
            else:
                os.environ["SEC_CONTACT"] = old
            shutil.rmtree(d)


if __name__ == "__main__":
    unittest.main()
