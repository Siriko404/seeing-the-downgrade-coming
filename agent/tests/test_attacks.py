"""Attacks on check.py and finish.py: wrong rows and wrong note sentences that must be caught.

Each test plants a wrong row or note sentence that misstates its filing or cited rows, checks that a valid control
still passes, and checks that the checker rejects the wrong one (or lists the gap). Input: a frozen copy of the
2026-11-07 HON RY SJ run in tests/fixtures/, so a new run does not change these tests.
"""
import subprocess
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
FROZEN_RUN = Path(__file__).resolve().parent / "fixtures" / "hon-ry-sj-2026-11-07"
sys.path.insert(0, str(TOOLS))
import common as C  # noqa: E402
import fetch as F   # noqa: E402
import check as K   # noqa: E402
import finish as N  # noqa: E402


def run_cli(tool: str, cwd: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(TOOLS / tool), *args],
        cwd=cwd,
        capture_output=True,
        text=True,
    )


class FrozenRunAttackBase(unittest.TestCase):
    """Loads the frozen HON RY SJ passages and ratings in tests/fixtures/."""

    @classmethod
    def setUpClass(cls):
        cls.passages_data = C.read_json(FROZEN_RUN / "passages.json")
        cls.passages = {p["id"]: p for p in cls.passages_data["passages"]}
        cls.tickers = cls.passages_data["tickers"]
        cls.ratings_data = C.read_json(FROZEN_RUN / "ratings.json")
        cls.rows = {r["id"]: r for r in cls.ratings_data["rows"]}
        cls.gaps = {g["id"]: g for g in cls.ratings_data["gaps"]}


class CheckRowAttacks(FrozenRunAttackBase):
    """Attacks on check.py C1-C4 and gaps_for where wrong rows pass unchecked."""

    def test_attack_01_prose_upgrade_inverted_to_downgrade_and_old_from_grade(self):
        """Attack C-01: Prose upgrade 'to AA+ from AA' reported as a 'downgrade' to the old grade 'AA'."""
        p21 = self.passages["P21"]
        tk = self.tickers["RY"]
        quote = (
            "On May 12, 2026, Fitch Ratings (i) upgraded our legacy senior long-term debt "
            "rating to AA+ from AA; (ii) affirmed our short-term debt rating as F1+ and "
            "(iii) confirmed our long-term issuer default rating applicable to our senior "
            "long-term debt remains at AA-."
        )
        control = {
            "passage_id": "P21",
            "agency": "Fitch",
            "rated_entity": "Royal Bank of Canada",
            "what_is_rated": "legacy senior long-term debt rating",
            "grade": "AA+",
            "outlook_or_watch": "",
            "action": "upgrade",
            "rating_date": "2026-05-12",
            "date_kind": "action",
            "quote": quote,
        }
        self.assertEqual(K.check_row(control, p21, tk)[0], [], "Control row must pass")

        wrong_row = {
            **control,
            "grade": "AA",          # prior grade before the upgrade ("from AA")
            "action": "downgrade",  # opposite of "upgraded"
        }
        why, _ = K.check_row(wrong_row, p21, tk)
        self.assertTrue(
            why,
            "Attack C-01 passed check.py: prose upgrade 'to AA+ from AA' was accepted as action='downgrade' with old grade='AA'.",
        )

    def test_attack_02_prose_outlook_change_reports_old_from_outlook(self):
        """Attack C-02: Prose 'from stable to review for downgrade' reported as outlook 'stable'."""
        p11 = self.passages["P11"]
        tk = self.tickers["HON"]
        quote = "On February 2, 2026, Moody's revised their credit rating outlook from stable to review for downgrade."
        control = {
            "passage_id": "P11",
            "agency": "Moody's",
            "rated_entity": "Honeywell International Inc.",
            "what_is_rated": "outlook",
            "grade": "",
            "outlook_or_watch": "review for downgrade",
            "action": "outlook change",
            "rating_date": "2026-02-02",
            "date_kind": "action",
            "quote": quote,
        }
        self.assertEqual(K.check_row(control, p11, tk)[0], [], "Control row must pass")

        wrong_row = {
            **control,
            "outlook_or_watch": "stable",  # the old outlook it moved FROM
        }
        why, _ = K.check_row(wrong_row, p11, tk)
        self.assertTrue(
            why,
            "Attack C-02 passed check.py: 'from stable to review for downgrade' was accepted with outlook_or_watch='stable'.",
        )

    def test_attack_03_prose_outlook_fabricated_watch_prefix_via_last_word_match(self):
        """Attack C-03: C2 checks only o.split()[-1], accepting 'CreditWatch negative' when quote has no watch/review."""
        p13 = self.passages["P13"]
        tk = self.tickers["HON"]
        quote = "On June 25, 2026, Moody's revised their credit rating outlook from review for downgrade to negative."
        control = {
            "passage_id": "P13",
            "agency": "Moody's",
            "rated_entity": "Honeywell International Inc.",
            "what_is_rated": "outlook",
            "grade": "",
            "outlook_or_watch": "negative",
            "action": "outlook change",
            "rating_date": "2026-06-25",
            "date_kind": "action",
            "quote": quote,
        }
        self.assertEqual(K.check_row(control, p13, tk)[0], [], "Control row must pass")

        wrong_row = {
            **control,
            "outlook_or_watch": "CreditWatch negative",
            "action": "watch placed",
        }
        why, norm = K.check_row(wrong_row, p13, tk)
        self.assertTrue(
            why,
            f"Attack C-03 passed check.py: 'CreditWatch negative' (normalised '{norm.get('outlook')}') accepted on a quote with no watch/review.",
        )

    def test_attack_04_table_substring_label_collision_legacy_vs_bail_in_senior(self):
        """Attack C-04: same_item substring check accepts 'Senior long-term debt' with Legacy grade 'AA' instead of 'AA-'."""
        p15 = self.passages["P15"]
        tk = self.tickers["RY"]
        quote = "Row: Fitch Ratings \u2021 (6) | Short-term debt: F1+ | Legacy senior long-term debt (2): AA | Senior long-term debt (3): AA- | Outlook: stable"
        control = {
            "passage_id": "P15",
            "agency": "Fitch",
            "rated_entity": "Royal Bank of Canada",
            "what_is_rated": "Senior long-term debt",
            "grade": "AA-",
            "outlook_or_watch": "",
            "action": "none",
            "rating_date": "2025-05-28",
            "date_kind": "as_of",
            "quote": quote,
        }
        self.assertEqual(K.check_row(control, p15, tk)[0], [], "Control row must pass")

        wrong_row = {
            **control,
            "grade": "AA",  # AA is Legacy senior long-term debt (2), NOT Senior long-term debt (3)
        }
        why, norm = K.check_row(wrong_row, p15, tk)
        self.assertTrue(
            why,
            f"Attack C-04 passed check.py: 'Senior long-term debt' with grade 'AA' (Legacy grade) passed and bucketed into '{norm.get('item')}'.",
        )

    def test_attack_05_action_date_stolen_from_another_agency_in_same_passage(self):
        """Attack C-05: C3 checks p['text'] instead of quote, letting S&P's March 6 row take Moody's February 2 date."""
        p11 = self.passages["P11"]
        tk = self.tickers["HON"]
        quote = "On March 6, 2026, S&P revised their credit rating outlook from watch negative to negative."
        control = {
            "passage_id": "P11",
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
        self.assertEqual(K.check_row(control, p11, tk)[0], [], "Control row must pass")

        wrong_row = {
            **control,
            "rating_date": "2026-02-02",  # Moody's date from an earlier sentence in P11, not in quote
        }
        why, _ = K.check_row(wrong_row, p11, tk)
        self.assertTrue(
            why,
            "Attack C-05 passed check.py: S&P quote stating 'On March 6, 2026' was accepted with rating_date='2026-02-02'.",
        )

    def test_attack_06_multi_agency_prose_cross_attribution_fitch_outlook_given_to_sp(self):
        """Attack C-06: Prose quote with S&P (negative) and Fitch (stable) lets S&P be assigned Fitch's 'stable' outlook."""
        p11 = self.passages["P11"]
        tk = self.tickers["HON"]
        quote = (
            "On March 6, 2026, S&P revised their credit rating outlook from watch negative to negative. "
            "On March 6, 2026, Fitch revised their credit rating outlook from watch negative to stable."
        )
        control = {
            "passage_id": "P11",
            "agency": "Fitch",
            "rated_entity": "Honeywell International Inc.",
            "what_is_rated": "outlook",
            "grade": "",
            "outlook_or_watch": "stable",
            "action": "outlook change",
            "rating_date": "2026-03-06",
            "date_kind": "action",
            "quote": quote,
        }
        self.assertEqual(K.check_row(control, p11, tk)[0], [], "Control row must pass")

        wrong_row = {
            **control,
            "agency": "S&P",  # S&P revised to negative, NOT stable
        }
        why, norm = K.check_row(wrong_row, p11, tk)
        self.assertTrue(
            why or "several" in norm.get("read", ""),  # G3 option C: kept only when flagged for a person
            "Attack C-06 passed check.py: S&P was accepted with Fitch's 'stable' outlook from a two-sentence quote.",
        )

    def test_attack_07_prose_wrong_item_assigns_long_term_grade_to_short_term_debt(self):
        """Attack C-07: Prose check ignores what_is_rated, allowing short-term debt to be given long-term grade AA+."""
        p21 = self.passages["P21"]
        tk = self.tickers["RY"]
        quote = (
            "On May 12, 2026, Fitch Ratings (i) upgraded our legacy senior long-term debt "
            "rating to AA+ from AA; (ii) affirmed our short-term debt rating as F1+ and "
            "(iii) confirmed our long-term issuer default rating applicable to our senior "
            "long-term debt remains at AA-."
        )
        control = {
            "passage_id": "P21",
            "agency": "Fitch",
            "rated_entity": "Royal Bank of Canada",
            "what_is_rated": "short-term debt rating",
            "grade": "F1+",
            "outlook_or_watch": "",
            "action": "affirmed",
            "rating_date": "2026-05-12",
            "date_kind": "action",
            "quote": quote,
        }
        self.assertEqual(K.check_row(control, p21, tk)[0], [], "Control row must pass")

        wrong_row = {
            **control,
            "grade": "AA+",  # AA+ is legacy senior long-term debt, impossible for short-term debt (F1+)
        }
        why, _ = K.check_row(wrong_row, p21, tk)
        self.assertTrue(
            why,
            "Attack C-07 passed check.py: 'short-term debt rating' was accepted with long-term grade 'AA+'.",
        )

    def test_attack_08_entity_of_substring_rewrites_separate_company_to_filer(self):
        """Attack C-08: entity_of maps 'Honeywell Aerospace Inc.' (separate ticker HONA) or 'Canada Inc.' to the filer."""
        p1 = self.passages["P1"]
        tk = self.tickers["HON"]
        quote = "Row: Long-term | S&P: A | Fitch: A | Moody's: A2"
        control = {
            "passage_id": "P1",
            "agency": "S&P",
            "rated_entity": "Honeywell International Inc.",
            "what_is_rated": "Long-term",
            "grade": "A",
            "outlook_or_watch": "",
            "action": "none",
            "rating_date": "2025-06-30",
            "date_kind": "as_of",
            "quote": quote,
        }
        self.assertEqual(K.check_row(control, p1, tk)[0], [], "Control row must pass")

        wrong_row = {
            **control,
            "rated_entity": "Honeywell Aerospace Inc.",  # Not in P1 and is separate ticker HONA
        }
        why, norm = K.check_row(wrong_row, p1, tk)
        self.assertTrue(
            why,
            f"Attack C-08 passed check.py: unmentioned separate company 'Honeywell Aerospace Inc.' was rewritten to '{norm.get('entity')}'.",
        )

    def test_attack_09_unrelated_affirmation_suppresses_ga_outlook_change_gap(self):
        """Attack C-09: dated_action in G-a (iii) accepts any action != 'none' (e.g. short-term affirmed), suppressing an unexplained outlook jump."""
        tk_map = {"HON": {"name": "Honeywell International Inc.", "filings": 2, "manual": 0, "unreadable": []}}
        base_rows = [
            {
                "ticker": "HON",
                "entity": "Honeywell International Inc.",
                "agency": "S&P",
                "item": "outlook",
                "grade": "",
                "outlook": "watch negative",
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
                "item": "outlook",
                "grade": "",
                "outlook": "stable",
                "rating_date": "2026-03-31",
                "date_kind": "as_of",
                "action": "none",
                "filed": "2026-04-23",
                "id": "R3",
            },
        ]
        # Control: without the unrelated affirmation, G-a fires
        control_gaps = K.gaps_for(base_rows, tk_map, "2026-05-01", "2025-05-01")
        self.assertTrue(
            any(g["rule"] == "G-a changed, no date" for g in control_gaps),
            "Control must flag G-a when outlook jumps from watch negative to stable without a dated action",
        )

        # Attack: add an unrelated short-term 'affirmed' or 'reviewed' row in between
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
                "action": "reviewed",
                "filed": "2026-02-17",
                "id": "R2",
            },
            base_rows[1],
        ]
        gaps = K.gaps_for(attack_rows, tk_map, "2026-05-01", "2025-05-01")
        self.assertTrue(
            any(g["rule"] == "G-a changed, no date" for g in gaps),
            "Attack C-09 suppressed G-a: an unrelated 'reviewed' row hid an unexplained outlook jump from watch negative to stable.",
        )

# The note-sentence attacks on finish.py (free text checked by regex) were removed on 2026-11-07: code now
# writes every note line from the checked rows. tests/test_note.py checks that each line states only its
# cited rows' values.


if __name__ == "__main__":
    unittest.main()
