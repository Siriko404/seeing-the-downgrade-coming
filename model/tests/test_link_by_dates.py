"""link_obligors --by-dates (2026-11-10): a name that maps to several SEC filers is linked, for scoring only, to the one
that filed 10-Ks under that name while S&P rated the obligor. Without the option nothing changes."""
import csv
import gzip
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
EV = ["agency", "sec_class", "rating_type", "obligor_id", "lei", "obligor_name", "action_class", "action_date"]
HD = ["cik", "filing_date", "form", "period", "name", "former_names", "sic", "state_inc", "ba_state", "fye"]


def run(d, *extra):
    out = Path(d) / f"links{len(extra)}.csv"
    subprocess.run([sys.executable, "-m", "tcf_credit.link_obligors", str(Path(d) / "ev.csv.gz"), str(Path(d) / "hd.csv"),
                    str(out), *extra], check=True, capture_output=True, env={"PYTHONPATH": str(SRC)})
    return {r["obligor_id"]: r for r in csv.DictReader(open(out))}


class ByDatesTests(unittest.TestCase):
    """Checks of link_obligors with and without `--by-dates` on a few made-up rating events and filers."""
    def setUp(self):
        self.d = tempfile.mkdtemp()
        with gzip.open(Path(self.d) / "ev.csv.gz", "wt", newline="") as f:
            w = csv.writer(f); w.writerow(EV)
            w.writerow(["S&P", "Corporate", "Issuer Credit Rating", "1", "", "Walt Disney Company (The)", "", "2019-03-12"])
            w.writerow(["S&P", "Corporate", "Issuer Credit Rating", "1", "", "Walt Disney Company (The)", "", "2024-12-02"])
            w.writerow(["S&P", "Corporate", "Issuer Credit Rating", "2", "", "Duff & Phelps Holdings Corporation", "", "2018-01-01"])
        with open(Path(self.d) / "hd.csv", "w", newline="") as f:
            w = csv.writer(f); w.writerow(HD)
            w.writerow(["1001039", "20151120", "10-K", "", "WALT DISNEY CO/", "", "4888", "DE", "CA", "0930"])
            w.writerow(["1001039", "20181121", "10-K", "", "TWDC HOLDCO 613 CORP", "WALT DISNEY CO/", "4888", "DE", "CA", "0930"])
            w.writerow(["1744489", "20191120", "10-K", "", "Walt Disney Co", "", "7990", "DE", "CA", "0930"])
            w.writerow(["883237", "20180301", "10-K", "", "VIRTUS INVESTMENT PARTNERS INC", "DUFF & PHELPS CORP", "6282", "DE", "CT", "1231"])
            w.writerow(["1409", "20100301", "10-K", "", "DUFF & PHELPS CORP", "", "6282", "DE", "NY", "1231"])

    def test_default_output_leaves_both_ambiguous(self):
        r = run(self.d)
        self.assertEqual((r["1"]["match"], r["1"]["cik"]), ("ambiguous", ""))
        self.assertEqual((r["2"]["match"], r["2"]["cik"]), ("ambiguous", ""))

    def test_by_dates_links_the_filer_of_those_years_under_that_name(self):
        r = run(self.d, "--by-dates")
        self.assertEqual((r["1"]["match"], r["1"]["cik"]), ("dated", "1744489"))   # Disney: the 2019 company
        self.assertEqual((r["2"]["match"], r["2"]["cik"]), ("ambiguous", ""))      # a former name now used by Virtus


if __name__ == "__main__":
    unittest.main()
