"""A second set of attack tests for check.py.

Each test plants a wrong rating row that must be rejected (or an unrelated row that must not hide a gap), or a correct
row that must be kept. Attacks 1, 2, 4, 5, 6 and 9 first check a control (a correct row, or the gap without the
unrelated row). Input: a frozen copy of the 2026-11-07 HON RY SJ run in tests/fixtures/hon-ry-sj-2026-11-07-round2.
From the agent/ folder, run all tests with: python3 -m unittest discover -s tests
One file only: python3 -m unittest discover -s tests -p test_attacks_round2.py
Standard library only.
"""
import sys
import unittest
from pathlib import Path


def _find_skill_dir() -> Path:
    here = Path(__file__).resolve().parent
    for cand in [
        Path.cwd() / "skills" / "credit-watch",
        here / "skills" / "credit-watch",
        here.parent / "skills" / "credit-watch",
        Path.cwd() / "repo" / "skills" / "credit-watch",
        here / "repo" / "skills" / "credit-watch",
    ]:
        if (cand / "tools" / "check.py").exists():
            return cand
    raise RuntimeError("Cannot locate skills/credit-watch directory; run from repo/.")


SKILL = _find_skill_dir()
TOOLS = SKILL / "tools"
FROZEN_RUN = Path(__file__).resolve().parent / "fixtures" / "hon-ry-sj-2026-11-07-round2"
sys.path.insert(0, str(TOOLS))
import common as C  # noqa: E402
import fetch as F   # noqa: E402
import check as K   # noqa: E402
import finish as N  # noqa: E402


class FrozenRunBase(unittest.TestCase):
    """Loads the frozen 2026-11-07 passages and ratings for HON, RY, SJ."""

    @classmethod
    def setUpClass(cls):
        cls.passages_data = C.read_json(FROZEN_RUN / "passages.json")
        cls.passages = {p["id"]: p for p in cls.passages_data["passages"]}
        cls.tickers = cls.passages_data["tickers"]
        cls.ratings_data = C.read_json(FROZEN_RUN / "ratings.json")
        cls.rows = {r["id"]: r for r in cls.ratings_data["rows"]}
        cls.gaps = {g["id"]: g for g in cls.ratings_data["gaps"]}


class CheckAttacksRound2(FrozenRunBase):
    """Ten cases for check.py: wrong rows it must reject (1, 2, 4, 5, 6), correct rows it must keep (3, 7, 8), an
    unrelated row that must not hide a gap (9), and a table with unread cells that must be reported (10)."""

    def test_attack_01_check_prose_same_agency_multi_clause_steals_upgrade_and_grade_for_affirmed_idr(self):
        """Attack 1: one Fitch quote has three clauses (legacy debt upgraded to AA+, short-term debt affirmed at F1+,
        long-term issuer default rating confirmed at AA-); a row that reports the AA- rating as upgraded to AA+ must
        be rejected."""
        p15 = self.passages["P15"]
        tk = self.tickers["RY"]
        quote = (
            "On May 12, 2026, Fitch Ratings (i) upgraded our legacy senior long-term debt "
            "rating to AA+ from AA; (ii) affirmed our short-term debt rating as F1+ and "
            "(iii) confirmed our long-term issuer default rating applicable to our senior "
            "long-term debt remains at AA-."
        )
        control = {
            "passage_id": "P15",
            "agency": "Fitch",
            "rated_entity": "Royal Bank of Canada",
            "what_is_rated": "long-term issuer default rating",
            "grade": "AA-",
            "outlook_or_watch": "",
            "action": "affirmed",
            "rating_date": "2026-05-12",
            "date_kind": "action",
            "quote": quote,
        }
        self.assertEqual(K.check_row(control, p15, tk)[0], [], "Control row must pass")

        wrong_row = {
            **control,
            "grade": "AA+",      # stolen from clause (i) legacy senior debt
            "action": "upgrade", # stolen from clause (i); clause (iii) confirmed IDR remains at AA-
        }
        why, _ = K.check_row(wrong_row, p15, tk)
        self.assertTrue(
            why,
            "Attack 1 bypassed check.py: Fitch's confirmed AA- IDR was accepted as upgraded to AA+ because scope_of pools all clauses of the same agency.",
        )

    def test_attack_02_check_new_state_regex_misses_trailing_from_grade_before_following_clause(self):
        """Attack 2: the sentence 'upgraded our issuer rating to AA+ from AA following the publication ...' must not be
        accepted with the old grade AA."""
        p17 = self.passages["P17"]
        tk = self.tickers["RY"]
        quote = (
            "(6) On May 12, 2026, Fitch Ratings upgraded our issuer rating to AA+ from AA "
            "following the publication on May 8, 2026 of Fitch Ratings' updated bank rating criteria."
        )
        control = {
            "passage_id": "P17",
            "agency": "Fitch",
            "rated_entity": "Royal Bank of Canada",
            "what_is_rated": "issuer rating",
            "grade": "AA+",
            "outlook_or_watch": "",
            "action": "upgrade",
            "rating_date": "2026-05-12",
            "date_kind": "action",
            "quote": quote,
        }
        self.assertEqual(K.check_row(control, p17, tk)[0], [], "Control row must pass")

        wrong_row = {
            **control,
            "grade": "AA",  # old 'from AA' grade before the upgrade
        }
        why, _ = K.check_row(wrong_row, p17, tk)
        self.assertTrue(
            why,
            "Attack 2 bypassed check.py: old grade 'AA' in 'to AA+ from AA following the publication...' passed because new_state() only strips trailing 'from X' within 20 chars of [,;.]|$|and.",
        )

    def test_attack_03_check_new_state_regex_falsely_rejects_true_new_grade_when_old_grade_has_parentheses(self):
        """Attack 3 (a correct row must be kept): the sentence 'downgraded our long-term rating from AA (high) to AA.'
        with the new grade AA must be accepted."""
        p_dbrs = {
            **self.passages["P15"],
            "text": "On May 12, 2026, DBRS downgraded our long-term rating from AA (high) to AA.",
        }
        tk = self.tickers["RY"]
        valid_row = {
            "passage_id": "P15",
            "agency": "DBRS Morningstar",
            "rated_entity": "Royal Bank of Canada",
            "what_is_rated": "long-term rating",
            "grade": "AA",
            "outlook_or_watch": "",
            "action": "downgrade",
            "rating_date": "2026-05-12",
            "date_kind": "action",
            "quote": p_dbrs["text"],
        }
        why, _ = K.check_row(valid_row, p_dbrs, tk)
        self.assertEqual(
            why,
            [],
            f"Attack 3 false rejection in check.py: valid DBRS new grade 'AA' in 'from AA (high) to AA.' was rejected with {why}.",
        )

    def test_attack_04_check_prose_watch_removed_inverted_to_watch_placed_via_from_watch_token(self):
        """Attack 4: the sentence 'outlook from watch negative to negative' must not be accepted with action 'watch
        placed'; S&P took the company off watch."""
        p5 = self.passages["P5"]
        tk = self.tickers["HON"]
        quote = "On March 6, 2026, S&P revised their credit rating outlook from watch negative to negative."
        control = {
            "passage_id": "P5",
            "agency": "S&P",
            "rated_entity": "Honeywell International Inc.",
            "what_is_rated": "outlook",
            "grade": "",
            "outlook_or_watch": "negative",
            "action": "outlook change",
            "rating_date": "2026-03-06",
            "date_kind": "action",
            "quote": quote,
        }
        self.assertEqual(K.check_row(control, p5, tk)[0], [], "Control row must pass")

        wrong_row = {
            **control,
            "action": "watch placed",  # S&P removed HON from watch negative; it did not place HON on watch
        }
        why, _ = K.check_row(wrong_row, p5, tk)
        self.assertTrue(
            why,
            "Attack 4 bypassed check.py: 'from watch negative to negative' was accepted with inverted action='watch placed'.",
        )

    def test_attack_05_check_c3_accepts_criteria_publication_date_as_rating_action_date(self):
        """Attack 5: the sentence upgrades on May 12, 2026 and mentions criteria published on May 8, 2026; a row dated
        2026-05-08 must be rejected, or kept only with a note that several dates are in the quote."""
        p17 = self.passages["P17"]
        tk = self.tickers["RY"]
        quote = (
            "(6) On May 12, 2026, Fitch Ratings upgraded our issuer rating to AA+ from AA "
            "following the publication on May 8, 2026 of Fitch Ratings' updated bank rating criteria."
        )
        control = {
            "passage_id": "P17",
            "agency": "Fitch",
            "rated_entity": "Royal Bank of Canada",
            "what_is_rated": "issuer rating",
            "grade": "AA+",
            "outlook_or_watch": "",
            "action": "upgrade",
            "rating_date": "2026-05-12",
            "date_kind": "action",
            "quote": quote,
        }
        self.assertEqual(K.check_row(control, p17, tk)[0], [], "Control row must pass")

        wrong_row = {
            **control,
            "rating_date": "2026-05-08",  # date Fitch published bank rating criteria, not the May 12 upgrade date
        }
        why, norm = K.check_row(wrong_row, p17, tk)
        self.assertTrue(
            why or "several" in norm.get("read", ""),  # kept only when flagged for a person to verify
            "Attack 5 bypassed check.py: criteria publication date 2026-05-08 was accepted as the upgrade action date.",
        )

    def test_attack_06_check_prose_conjunction_and_pools_two_agencies_into_same_clause(self):
        """Attack 6: one sentence holds an S&P outlook (negative) and, after ', and', a Fitch outlook (stable); a row
        that gives S&P the outlook 'stable' must be rejected, or kept only with a note that several agencies are in
        the quote."""
        p5_compound = {
            **self.passages["P5"],
            "text": (
                "On March 6, 2026, S&P revised their credit rating outlook from watch negative to negative, "
                "and Fitch revised their credit rating outlook from watch negative to stable."
            ),
        }
        tk = self.tickers["HON"]
        control = {
            "passage_id": "P5",
            "agency": "S&P",
            "rated_entity": "Honeywell International Inc.",
            "what_is_rated": "outlook",
            "grade": "",
            "outlook_or_watch": "negative",
            "action": "outlook change",
            "rating_date": "2026-03-06",
            "date_kind": "action",
            "quote": p5_compound["text"],
        }
        self.assertEqual(K.check_row(control, p5_compound, tk)[0], [], "Control row must pass")

        wrong_row = {
            **control,
            "outlook_or_watch": "stable",  # Fitch's outlook, not S&P's
        }
        why, norm = K.check_row(wrong_row, p5_compound, tk)
        self.assertTrue(
            why or "several" in norm.get("read", ""),  # kept only when flagged for a person to verify
            "Attack 6 bypassed check.py: S&P was accepted with Fitch's 'stable' outlook in a ', and ' compound sentence.",
        )

    def test_attack_07_check_conditional_regex_falsely_rejects_actual_downgrade_with_could_or_if(self):
        """Attack 7 (a correct row must be kept): a real downgrade sentence that also says costs 'could' rise 'if'
        market conditions tighten must be accepted."""
        p_real = {
            **self.passages["P5"],
            "text": (
                "On February 2, 2026, Moody's downgraded our long-term debt rating to A3 from A2, "
                "which could increase our borrowing costs if market conditions tighten."
            ),
        }
        tk = self.tickers["HON"]
        valid_row = {
            "passage_id": "P5",
            "agency": "Moody's",
            "rated_entity": "Honeywell International Inc.",
            "what_is_rated": "long-term debt",
            "grade": "A3",
            "outlook_or_watch": "",
            "action": "downgrade",
            "rating_date": "2026-02-02",
            "date_kind": "action",
            "quote": p_real["text"],
        }
        why, _ = K.check_row(valid_row, p_real, tk)
        self.assertEqual(
            why,
            [],
            f"Attack 7 false rejection in check.py: valid downgrade quote containing 'could'/'if' was rejected with {why}.",
        )

    def test_attack_08_check_scope_of_splits_on_inc_period_and_falsely_rejects_sp_action_date(self):
        """Attack 8 (a correct row must be kept): 'On May 12, 2026, S&P Global Inc. (S&P) upgraded our long-term debt
        rating to A+ from A ...' with the date 2026-05-12 must be accepted; 'Inc.' ends with a period but is not the
        end of the sentence."""
        p_sp = {
            **self.passages["P5"],
            "filed": "2026-05-28",
            "text": (
                "On May 12, 2026, S&P Global Inc. (S&P) upgraded our long-term debt rating to A+ from A "
                "following criteria published on May 8, 2026."
            ),
        }
        tk = self.tickers["HON"]
        valid_row = {
            "passage_id": "P5",
            "agency": "S&P",
            "rated_entity": "Honeywell International Inc.",
            "what_is_rated": "long-term debt",
            "grade": "A+",
            "outlook_or_watch": "",
            "action": "upgrade",
            "rating_date": "2026-05-12",
            "date_kind": "action",
            "quote": p_sp["text"],
        }
        why, _ = K.check_row(valid_row, p_sp, tk)
        self.assertEqual(
            why,
            [],
            f"Attack 8 false rejection in check.py: valid S&P row with 'S&P Global Inc. (S&P)' had its true action date rejected with {why}.",
        )

    def test_attack_09_check_ga_ii_grade_change_gap_suppressed_by_unrelated_short_term_action(self):
        """Attack 9: S&P's senior unsecured grade falls from A (2025-12-31) to BBB+ (2026-03-31) with no dated action;
        an unrelated short-term 'assigned' row (2026-01-15) must not hide the gap that check.py lists."""
        tk_map = {"HON": {"name": "Honeywell International Inc.", "filings": 2, "manual": 0, "unreadable": []}}
        base_rows = [
            {
                "ticker": "HON",
                "entity": "Honeywell International Inc.",
                "agency": "S&P",
                "item": "senior unsecured",
                "grade": "A",
                "outlook": "",
                "rating_date": "2025-12-31",
                "date_kind": "as_of",
                "action": "none",
                "filed": "2026-02-17",
                "id": "R1",
            },
            {
                "ticker": "HON",
                "entity": "Honeywell International Inc.",
                "agency": "S&P",
                "item": "senior unsecured",
                "grade": "BBB+",
                "outlook": "",
                "rating_date": "2026-03-31",
                "date_kind": "as_of",
                "action": "none",
                "filed": "2026-04-23",
                "id": "R3",
            },
        ]
        control_gaps = K.gaps_for(base_rows, tk_map, "2026-05-01", "2025-05-01")
        self.assertTrue(
            any(g["rule"] == "G-a changed, no date" for g in control_gaps),
            "Control must flag G-a when senior unsecured grade drops from A to BBB+ without a dated action",
        )

        attack_rows = [
            base_rows[0],
            {
                "ticker": "HON",
                "entity": "Honeywell International Inc.",
                "agency": "S&P",
                "item": "short-term",
                "grade": "A-1",
                "outlook": "",
                "rating_date": "2026-01-15",
                "date_kind": "action",
                "action": "assigned",
                "filed": "2026-02-17",
                "id": "R2",
            },
            base_rows[1],
        ]
        gaps = K.gaps_for(attack_rows, tk_map, "2026-05-01", "2025-05-01")
        self.assertTrue(
            any(g["rule"] == "G-a changed, no date" for g in gaps),
            "Attack 9 suppressed G-a (ii): an unrelated short-term 'assigned' action hid an unexplained long-term downgrade from A to BBB+.",
        )

    def test_attack_10_check_empty_tables_misses_table_with_only_one_of_nine_cells_extracted(self):
        """Attack 10: a 9-cell rating table (three items for S&P, Fitch and Moody's) with a row for only one cell must
        still be reported by check.py (as a table with unread cells, or in its printed output)."""
        import json
        import shutil
        import subprocess
        import tempfile

        d = Path(tempfile.mkdtemp())
        try:
            run_dir = d / "credit-watch" / "run"
            run_dir.mkdir(parents=True)
            p1 = self.passages["P1"]
            ps_min = {
                "made": "2026-11-07T18:00:00",
                "as_of": "2026-11-07",
                "window_start": "2025-05-08",
                "tickers": {"HON": self.tickers["HON"]},
                "passages": [p1],
                "set_aside": [],
            }
            (run_dir / "passages.json").write_text(json.dumps(ps_min))
            # Only 1 row extracted out of 9 cells in P1 (Fitch and Moody's completely skipped, all 6 grades skipped)
            one_row = [
                {
                    "passage_id": "P1",
                    "agency": "S&P",
                    "rated_entity": "Honeywell International Inc.",
                    "what_is_rated": "outlook",
                    "grade": "",
                    "outlook_or_watch": "Watch Negative",
                    "action": "none",
                    "rating_date": "2025-06-30",
                    "date_kind": "as_of",
                    "quote": "Row: Outlook | S&P: Watch Negative | Fitch: Watch Negative | Moody's: Stable",
                }
            ]
            (run_dir / "rows.json").write_text(json.dumps({"rows": one_row}))
            r = subprocess.run([sys.executable, str(TOOLS / "check.py")], cwd=d, capture_output=True, text=True)
            self.assertEqual(r.returncode, 0)
            res = json.loads((run_dir / "ratings.json").read_text())
            self.assertTrue(
                res.get("empty_tables") or "missing" in r.stdout.lower() or "skipped" in r.stdout.lower(),
                "Attack 10 bypassed table coverage check: extracting 1 of 9 cells in P1 left empty_tables == [] with no warning for the 6 missing grade cells.",
            )
        finally:
            shutil.rmtree(d)

# The note-sentence attacks on finish.py (free text checked by regex) were removed on 2026-11-07: code now
# writes every note line from the checked rows. tests/test_note.py checks that each line states only its
# cited rows' values.


if __name__ == "__main__":
    unittest.main()
