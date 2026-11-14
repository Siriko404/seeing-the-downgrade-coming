"""Tests for tickers.py (pipeline step 5a helper: the ticker lists for the free price route).

The small test writes small test inputs (a panel and an SEC file) to a temporary folder and runs the command. The reference test
runs it on the public reference files when they exist and is skipped otherwise. Neither test needs the internet.
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from tcf_credit.tickers import build, cik_text, read_sec

SRC = Path(__file__).resolve().parents[1] / "src"


def reference(name: str) -> Path:
    """Find a reference file or folder by looking under ref/ above this file, or use TCF_REF_DIR."""
    roots = [Path(os.environ["TCF_REF_DIR"])] if "TCF_REF_DIR" in os.environ else []
    roots += [p / "ref" for p in Path(__file__).resolve().parents]
    for root in roots:
        if (root / name).exists():
            return root / name
    return Path("/nonexistent") / name


REF_PANEL = reference("panel_public.csv")
REF_SEC = reference("company_tickers_exchange.json")
REF_YAHOO = reference("yahoo_tickers.csv")


class TickerTests(unittest.TestCase):
    """Checks of CIK matching, share classes and the two output files."""
    def test_build_keeps_panel_order_and_primary_listing(self):
        panel = pd.DataFrame({"cik": ["0000200", "100", "300", "100"]})
        sec = pd.DataFrame({"cik": ["200", "100", "100", "300", "400"],
                            "name": ["B", "A", "A", "C", "D"],
                            "ticker": ["BBB", "AAA", "AA-A", "CCC", "DDD"],
                            "exchange": ["NYSE", "Nasdaq", "NYSE", "OTC", "NYSE"]})
        out = build(panel, sec)
        self.assertEqual(out.cik.tolist(), ["200", "100", "300"])
        self.assertEqual(out.ticker.tolist(), ["BBB", "AAA", "CCC"])
        self.assertEqual(out.exchange.tolist(), ["NYSE", "Nasdaq", "OTC"])

    def test_share_class_spelling_is_kept(self):
        panel = pd.DataFrame({"cik": ["1"]})
        sec = pd.DataFrame({"cik": ["1"], "name": ["B"], "ticker": ["BRK-B"], "exchange": ["NYSE"]})
        self.assertEqual(build(panel, sec).ticker.tolist(), ["BRK-B"])

    def test_command_writes_both_files_with_spy(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            pd.DataFrame({"cik": ["100", "200", "300", "100"]}).to_csv(d / "panel.csv", index=False)
            payload = {"fields": ["cik", "name", "ticker", "exchange"],
                       "data": [[200, "B", "BBB", "NYSE"], [100, "A", "AAA", "Nasdaq"],
                                [100, "A", "AA-A", "NYSE"], [300, "C", "CCC", "OTC"]]}
            (d / "sec.json").write_text(json.dumps(payload))
            r = subprocess.run([sys.executable, "-m", "tcf_credit.tickers", str(d / "panel.csv"),
                                str(d / "sec.json"), str(d / "out")], capture_output=True, text=True,
                               env={"PYTHONPATH": str(SRC)})
            self.assertEqual(r.returncode, 0, r.stderr)
            got = pd.read_csv(d / "out" / "TICKERS.csv", dtype={"cik": str})
            self.assertEqual(got.columns.tolist(), ["cik", "ticker", "exchange"])
            self.assertEqual(got.cik.tolist(), ["100", "200", "300"])
            lines = (d / "out" / "TICKERS.txt").read_text().splitlines()
            self.assertEqual(lines, ["AAA", "BBB", "CCC", "SPY"])

    @unittest.skipUnless(REF_PANEL.exists() and REF_SEC.exists(), "SEC reference files not found")
    def test_reference_panel_and_sec_file(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            r = subprocess.run([sys.executable, "-m", "tcf_credit.tickers", str(REF_PANEL), str(REF_SEC),
                                str(d)], capture_output=True, text=True, env={"PYTHONPATH": str(SRC)})
            self.assertEqual(r.returncode, 0, r.stderr)
            got = pd.read_csv(d / "TICKERS.csv", dtype=str)
            panel = pd.read_csv(REF_PANEL, dtype={"cik": str})
            sec = read_sec(REF_SEC)
            want_ciks = set(cik_text(panel.cik)) & set(sec.cik)
            self.assertEqual(set(got.cik), want_ciks)
            self.assertEqual(len(got), len(want_ciks))
            for row in got.itertuples():
                choices = set(zip(sec[sec.cik == row.cik].ticker, sec[sec.cik == row.cik].exchange))
                self.assertIn((row.ticker, row.exchange), choices)
            lines = (d / "TICKERS.txt").read_text().splitlines()
            self.assertEqual(lines.count("SPY"), 1)
            self.assertTrue(set(got.ticker) <= set(lines))
            if REF_YAHOO.exists():
                yahoo = pd.read_csv(REF_YAHOO, dtype={"cik": str})
                shared = set(yahoo.cik) & set(cik_text(panel.cik))
                self.assertTrue(shared <= set(got.cik))


if __name__ == "__main__":
    unittest.main()
