"""Tests of three crash fixes in the credit-watch tools.

Three cases: no network when a firm or a holdings file is looked up (one plain line, no traceback), an empty or
non-text quote on a table row (the row is rejected, no crash), and a check.py error, which must not use up one of the
two check rounds.
From the agent/ folder, run all tests with: python3 -m unittest discover -s tests
One file only: python3 -m unittest discover -s tests -p test_crash_fixes.py
Standard library only.
"""
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1] / "skills" / "credit-watch" / "tools"
sys.path.insert(0, str(TOOLS))
os.environ["CREDIT_WATCH_SCORES"] = str(Path(tempfile.gettempdir()) / "credit-watch-tests-no-scores.csv")
os.environ["CREDIT_WATCH_MODEL"] = ""
import common as C  # noqa: E402
import fetch as F   # noqa: E402
import check as K   # noqa: E402

TABLE = (b"<html><body><p>Our credit ratings at December 31, 2025 were:</p><table>"
         b"<tr><td>Agency</td><td>Long-term</td><td>Outlook</td></tr>"
         b"<tr><td>S&amp;P</td><td>A</td><td>Stable</td></tr>"
         b"<tr><td>Moody's</td><td>A2</td><td>Negative</td></tr></table></body></html>")
STAMP = {"ticker": "X", "company": "X CORP", "form": "10-K", "doc_type": "10-K", "filed": "2026-02-10",
         "url": "https://www.sec.gov/Archives/edgar/data/1/000000000126000001/x.htm"}
TK = {"name": "X CORP", "cik": "1", "aliases": ""}


def table_passage():
    ps = F.passages_of(F.blocks_of(TABLE, "x.htm"), STAMP, [])
    p = next(p for p in ps if p["kind"] == "table")
    return {**p, "id": "P1"}


def row(quote):
    return {"passage_id": "P1", "agency": "S&P", "rated_entity": "X Corp", "what_is_rated": "long-term issuer rating",
            "grade": "A", "outlook_or_watch": "stable", "action": "", "rating_date": "2025-12-31",
            "date_kind": "as_of", "quote": quote}


class DeadSec:
    """A stand-in for the SEC client whose every request fails as if there were no network."""
    def __init__(self, *a):
        self.requests = 0

    def get(self, url, keep):
        self.requests += 1
        raise ConnectionError(f"{url}: <urlopen error [Errno -3] Temporary failure in name resolution>")


class LookupWithoutNetworkTests(unittest.TestCase):
    """No network at lookup: a firm stops with one plain message, and a holdings file does not crash."""
    def setUp(self):
        self.d, self.cwd = tempfile.mkdtemp(), os.getcwd()
        os.chdir(self.d)
        self.saved = F.Sec, F.contact
        F.Sec, F.contact = DeadSec, (lambda: "Test Person contact")

    def tearDown(self):
        F.Sec, F.contact = self.saved
        os.chdir(self.cwd)
        shutil.rmtree(self.d)

    def test_firm_lookup_without_network_is_a_plain_exit(self):
        for arg in ("F", "Ford Motor", "37996"):
            with redirect_stdout(io.StringIO()), self.assertRaises(SystemExit) as e:
                F.main([arg])
            self.assertIn("company list could not be reached", str(e.exception), arg)
            self.assertIn("TICKER=CIK", str(e.exception), arg)

    def test_holdings_lookup_without_network_does_not_crash(self):
        Path("h.txt").write_text("F\nFord Motor\n")
        try:
            with redirect_stdout(io.StringIO()):
                F.main(["--holdings", "h.txt"])
        except SystemExit:
            pass                                    # a plain stop is fine; a traceback is not


class EmptyQuoteTests(unittest.TestCase):
    """An empty or non-text quote on a table row is rejected in words, not a crash."""
    def test_empty_and_non_text_quotes_are_rejected(self):
        p = table_passage()
        for q in ("", " ", "\n", None, 0, [], {}):
            why, _ = K.check_row(row(q), p, TK, p["text"])
            self.assertTrue(why, repr(q))

    def test_whole_is_false_for_an_empty_quote(self):
        self.assertFalse(K.whole("", "S&P A Stable"))
        self.assertFalse(K.whole("   ", "S&P A Stable"))


class RoundCounterTests(unittest.TestCase):
    """A checker that stops with an error does not use up a round."""
    def setUp(self):
        self.d, self.cwd = tempfile.mkdtemp(), os.getcwd()
        os.chdir(self.d)
        import subprocess
        r = subprocess.run([sys.executable, str(TOOLS / "fetch.py"), "HON", "--offline"], capture_output=True, text=True)
        assert r.returncode == 0, r.stderr
        C.write_json(C.RUN / "rows.json", {"rows": [row("not in the passage")]})
        self.saved, self.argv = K.check_row, sys.argv

    def tearDown(self):
        K.check_row, sys.argv = self.saved, self.argv
        os.chdir(self.cwd)
        shutil.rmtree(self.d)

    def test_failed_check_does_not_count_as_a_round(self):
        def boom(*a, **k):
            raise RuntimeError("planted")
        K.check_row, sys.argv = boom, ["check.py"]
        with redirect_stdout(io.StringIO()), self.assertRaises(RuntimeError):
            K.main()
        self.assertFalse((C.RUN / "check_round.txt").exists())
        K.check_row = self.saved
        with redirect_stdout(io.StringIO()):
            K.main()
        self.assertEqual((C.RUN / "check_round.txt").read_text(), "1")


if __name__ == "__main__":
    unittest.main()
