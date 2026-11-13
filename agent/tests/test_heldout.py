"""Held-out tests of check.py on JPMorgan Chase and NextEra Energy filings that were not used to tune the checker.

The fixture tests/fixtures/jpm-nee-2026-11-07 holds JPM's 10-Q table of 2025-06-30 and NEE's 10-K table, rendered by
the current fetch.py from the SEC documents (column-group and group headings give each cell its entity), plus three
text passages as fetched on 2026-11-07. The alias list is emptied: the entity rule must work without it.
From the agent/ folder, run all tests with: python3 -m unittest discover -s tests
One file only: python3 -m unittest discover -s tests -p test_heldout.py
Standard library only.
"""
import json
import sys
import unittest
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1] / "skills" / "credit-watch"
sys.path.insert(0, str(SKILL / "tools"))
import check as K  # noqa: E402

FIX = Path(__file__).resolve().parent / "fixtures" / "jpm-nee-2026-11-07" / "passages.json"


class HeldOut(unittest.TestCase):
    """Checks of check.py on the JPM and NEE fixture passages."""
    @classmethod
    def setUpClass(cls):
        d = json.loads(FIX.read_text())
        cls.ps = {p["id"]: p for p in d["passages"]}
        cls.tk = d["tickers"]
        cls.filing = {}
        for p in d["passages"]:
            k = p["url"].rsplit("/", 1)[0]
            cls.filing[k] = cls.filing.get(k, "") + "\n" + p["text"]

    def line(self, pid, start):
        return next(r["line"] for r in self.ps[pid]["table"]["rows"] if r["line"].startswith(start))

    def why(self, pid, **kw):
        p = self.ps[pid]
        row = {"passage_id": pid, "agency": "Moody's", "rated_entity": "", "what_is_rated": "", "grade": "",
               "outlook_or_watch": "", "action": "none", "rating_date": "", "date_kind": "none", "quote": "", **kw}
        return K.check_row(row, p, self.tk[p["ticker"]], self.filing[p["url"].rsplit("/", 1)[0]])

    def jpm(self, **kw):
        q = self.line("P1", "Row: June 30, 2025: Moody's")
        return self.why("P1", rating_date="2025-06-30", date_kind="as_of", quote=q, **kw)[0]

    def test_short_term_issuer_kept(self):
        self.assertEqual(self.jpm(rated_entity="JPMorgan Chase & Co.", what_is_rated="Short-term issuer", grade="P-1"), [])
        self.assertEqual(self.jpm(rated_entity="JPMorgan Chase & Co.", what_is_rated="Long-term issuer", grade="A1"), [])

    def test_cell_entity_bound(self):
        self.assertEqual(self.jpm(rated_entity="JPMorgan Chase Bank, N.A.", what_is_rated="Long-term issuer",
                                  grade="Aa2"), [])
        self.assertTrue(self.jpm(rated_entity="JPMorgan Chase & Co.", what_is_rated="Long-term issuer", grade="Aa2"))
        self.assertEqual(self.jpm(rated_entity="JPMorgan Chase & Co.", what_is_rated="outlook",
                                  outlook_or_watch="Positive"), [])
        self.assertTrue(self.jpm(rated_entity="JPMorgan Chase & Co.", what_is_rated="outlook", outlook_or_watch="Stable"))

    def nee(self, start, **kw):
        q = self.line("P4", start)
        return self.why("P4", rating_date="2026-02-13", date_kind="as_of", quote=q, **kw)[0]

    def test_nee_groups_items_vmig(self):
        self.assertEqual(self.nee("Row: [FPL:(b)] First mortgage", rated_entity="FPL", what_is_rated="First mortgage bonds",
                                  grade="Aa2"), [])
        self.assertEqual(self.nee("Row: [NEECH:(b)] Debentures", rated_entity="NEECH", what_is_rated="Debentures",
                                  agency="S&P", grade="BBB+"), [])
        self.assertEqual(self.nee("Row: [FPL:(b)] Pollution", rated_entity="FPL", what_is_rated="Pollution control "
                                  "revenue bonds", grade="VMIG-1"), [])
        self.assertEqual(self.nee("Row: [NEE:(b)] Corporate", rated_entity="NEE", what_is_rated="Corporate credit rating",
                                  grade="Baa1"), [])
        self.assertEqual(self.nee("Row: [NEE:(b)] Corporate", rated_entity="NextEra Energy, Inc.",
                                  what_is_rated="Corporate credit rating", grade="Baa1"), [])
        self.assertTrue(self.nee("Row: [FPL:(b)] First mortgage", rated_entity="NEECH",
                                 what_is_rated="First mortgage bonds", grade="Aa2"))       # FPL's grade, NEECH's name

    def test_nee_footnote_outlook_for_entity_named_in_same_filing(self):
        q = "(b) The outlook indicated by each of Moody's, S&P and Fitch is stable."
        why, n = self.why("P5", rated_entity="NEECH", what_is_rated="outlook", outlook_or_watch="stable", quote=q)
        self.assertEqual(why, [])
        self.assertIn("several agencies", n["read"])

    def test_jp_initials_do_not_split(self):
        q = ("On November 3, 2025, Moody's revised the outlook for the Parent Company, J.P. Morgan Securities LLC, "
             "J.P. Morgan Securities plc and J.P. Morgan SE to stable from positive, and revised J.P. Morgan SE's "
             "long-term issuer rating to Aa2 from Aa3.")
        ok = dict(rated_entity="the Parent Company", what_is_rated="outlook", outlook_or_watch="stable",
                  action="outlook change", rating_date="2025-11-03", date_kind="action", quote=q)
        self.assertEqual(self.why("P3", **ok)[0], [])
        self.assertTrue(self.why("P3", **{**ok, "outlook_or_watch": "positive"})[0])         # old state
        up = dict(rated_entity="J.P. Morgan SE", what_is_rated="Long-term issuer", grade="Aa2", action="upgrade",
                  rating_date="2025-11-03", date_kind="action", quote=q)
        self.assertEqual(self.why("P3", **up)[0], [])                  # 'to Aa2 from Aa3' reads as an upgrade
        self.assertTrue(self.why("P3", **{**up, "action": "downgrade"})[0])
        self.assertTrue(self.why("P3", **{**up, "grade": "Aa3"})[0])                         # old grade

    def test_loan_pricing_is_not_a_rating(self):
        p = {**self.ps["P2"], "text": "The spreads applicable to Base Rate and Term SOFR loans depend on our senior "
                                      "public debt rating assigned by Moody's and S&P."}
        row = {"passage_id": "P2", "agency": "Moody's", "rated_entity": "our", "what_is_rated": "senior public debt",
               "grade": "", "outlook_or_watch": "", "action": "assigned", "rating_date": "", "date_kind": "none",
               "quote": p["text"]}
        self.assertTrue(K.check_row(row, p, self.tk["JPM"])[0])

    def test_removed_from_creditwatch(self):
        p = {**self.ps["P2"], "text": "On March 6, 2025, S&P removed our ratings from CreditWatch with negative "
                                      "implications and assigned a negative outlook."}
        row = {"passage_id": "P2", "agency": "S&P", "rated_entity": "our", "what_is_rated": "outlook", "grade": "",
               "outlook_or_watch": "negative", "action": "watch removed", "rating_date": "2025-03-06",
               "date_kind": "action", "quote": p["text"]}
        self.assertEqual(K.check_row(row, p, self.tk["JPM"])[0], [])
        self.assertTrue(K.check_row({**row, "action": "watch placed"}, p, self.tk["JPM"])[0])

    def test_one_value_per_row_and_filer_short_name(self):
        q = self.line("P4", "Row: [FPL:(b)] Pollution")
        base = dict(rated_entity="FPL", what_is_rated="Pollution control revenue bonds", rating_date="2026-02-13",
                    date_kind="as_of", quote=q)
        self.assertTrue(self.why("P4", grade="VMIG-1/P-1", **base)[0])               # one grade per row
        self.assertEqual(self.why("P4", grade="P-1", **base)[0], [])
        p = {**self.ps["P2"], "text": "Loews Corporation has a senior debt rating of A3 with a stable outlook from "
                                      "Moody's Investors Service."}
        row = {"passage_id": "P2", "agency": "Moody's", "rated_entity": "Loews Corporation", "what_is_rated": "senior debt",
               "grade": "A3", "outlook_or_watch": "stable", "action": "none", "rating_date": "", "date_kind": "none",
               "quote": p["text"]}
        tk = {"name": "Loews Corp", "aliases": ""}
        self.assertTrue(K.check_row(row, p, tk)[0])                                  # grade and outlook: two rows
        self.assertEqual(K.check_row({**row, "outlook_or_watch": ""}, p, tk)[0], [])
        self.assertEqual(K.entity_of("JPMorgan Chase", self.tk["JPM"], "JPM"), "JPMorgan Chase & Co.")
        self.assertIsNone(K.entity_of("JPMorgan Aerospace", self.tk["JPM"], "JPM"))

    def test_received_new_rating_is_assigned(self):
        p = {**self.ps["P2"], "text": "Subsequent to quarter end, Canadian Natural received a new long-term investment "
                                      "grade credit rating of BBB+ from Fitch Ratings."}
        row = {"passage_id": "P2", "agency": "Fitch", "rated_entity": "Canadian Natural", "what_is_rated": "long-term",
               "grade": "BBB+", "outlook_or_watch": "", "action": "assigned", "rating_date": "", "date_kind": "none",
               "quote": p["text"]}
        self.assertEqual(K.check_row(row, p, {"name": "Canadian Natural Resources Ltd", "aliases": ""})[0], [])

    def test_one_undated_event_one_gap(self):
        r = lambda i, a: {"id": i, "ticker": "L", "entity": "CNA", "agency": "A.M. Best", "action": a, "rating_date": "",
                          "filed": "2026-02-10", "quote": "A.M. Best upgraded CNA's ratings in December 2025",
                          "grade": "", "outlook": "", "item": "financial strength", "date_kind": "none"}
        g = K.gaps_for([r("R1", "upgrade"), r("R2", "upgrade"), r("R3", "outlook change")],
                       {"L": {"filings": 3, "manual": 0, "name": "Loews"}}, "2026-11-07", "2025-05-08")
        self.assertEqual(len(g), 1, g)
        self.assertEqual(g[0]["rows"], ["R1", "R2", "R3"])


if __name__ == "__main__":
    unittest.main()
