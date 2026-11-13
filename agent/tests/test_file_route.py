"""SEDAR+ by hand: no code downloads Canadian filings (you download them yourself). A firm with no SEC number
and no saved file stops with the SEDAR+ link and the rerun command; --file copies the user's download into
credit-watch/manual/<TICKER>/ and reads it.
Standard library only: python3 -m unittest discover -s tests
"""
import io
import os
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1] / "skills" / "credit-watch"
sys.path.insert(0, str(SKILL / "tools"))
os.environ["CREDIT_WATCH_SCORES"] = str(Path(tempfile.gettempdir()) / "credit-watch-tests-no-scores.csv")
os.environ["CREDIT_WATCH_MODEL"] = ""
import common as C  # noqa: E402
import fetch as F   # noqa: E402

AIF = b"Annual Information Form. DBRS Morningstar rates our senior unsecured notes BBB (high) with a stable trend."


class FileRouteTests(unittest.TestCase):
    def setUp(self):
        self.d, self.cwd = tempfile.mkdtemp(), os.getcwd()
        os.chdir(self.d)
        self.dl = Path(self.d) / "user-files"
        self.dl.mkdir()
        self.f = self.dl / "dol-aif.txt"
        self.f.write_bytes(AIF)

    def tearDown(self):
        os.chdir(self.cwd)
        shutil.rmtree(self.d)

    def run_main(self, *args):
        with redirect_stdout(io.StringIO()) as out:
            F.main(list(args))
        return out.getvalue()

    def test_file_is_copied_with_its_source_and_read(self):
        out = self.run_main("DOL=manual", "--file", str(self.f), "--filed", "2026-03-01", "--offline")
        self.assertTrue(self.f.exists())                                  # the user's download stays
        saved = C.MANUAL / "DOL" / "dol-aif.txt"
        self.assertEqual(saved.read_bytes(), AIF)
        src = (C.MANUAL / "DOL" / "dol-aif.txt.source.txt").read_text()
        self.assertIn("filing date: 2026-03-01", src)
        self.assertIn("form: Annual Information Form", src)
        self.assertIn("downloaded by: the user", src)
        self.assertIn("1 manual files", out)
        ps = C.read_json(C.RUN / "passages.json")["passages"]
        self.assertTrue(any("BBB (high)" in p["text"] and p["filed"] == "2026-03-01" for p in ps))

    def test_same_file_twice_is_not_copied_again(self):
        for _ in range(2):
            self.run_main("DOL=manual", "--file", str(self.f), "--filed", "2026-03-01", "--offline")
        self.assertEqual(len(F.manual_docs("DOL")), 1)

    def test_each_file_keeps_its_own_date_beside_an_older_folder_source(self):
        d = C.MANUAL / "DOL"
        d.mkdir(parents=True)
        (d / "old.txt").write_bytes(b"S&P rates us BBB.")
        (d / "source.txt").write_text("link: x\nfiling date: 2025-03-01\nform: AIF\ndownloaded by: person\n")
        self.run_main("DOL=manual", "--file", str(self.f), "--filed", "2026-03-01", "--offline")
        dates = {p.name: s["filing date"] for p, s in F.manual_docs("DOL")}
        self.assertEqual(dates, {"old.txt": "2025-03-01", "dol-aif.txt": "2026-03-01"})

    def test_sec_filer_refuses_a_file(self):
        with self.assertRaises(SystemExit) as e:
            self.run_main("JPM=19617", "--file", str(self.f), "--filed", "2026-03-01", "--offline")
        self.assertIn("SEC filer", str(e.exception))
        self.assertIn("JPM=manual", str(e.exception))
        self.assertFalse((C.MANUAL / "JPM").exists())

    def test_file_needs_a_filing_date_and_never_guesses(self):
        with self.assertRaises(SystemExit) as e:
            self.run_main("DOL=manual", "--file", str(self.f), "--offline")
        self.assertIn("--filed", str(e.exception))
        with self.assertRaises(SystemExit):
            self.run_main("DOL=manual", "--file", str(self.f), "--filed", "March 2026", "--offline")
        self.assertFalse((C.MANUAL / "DOL").exists())

    def test_unreadable_file_is_not_copied(self):
        bad = self.dl / "x.docx"
        bad.write_bytes(b"PK")
        with self.assertRaises(SystemExit):
            self.run_main("DOL=manual", "--file", str(bad), "--filed", "2026-03-01", "--offline")
        broken = self.dl / "x.pdf"
        broken.write_bytes(b"not a pdf")
        with self.assertRaises(SystemExit) as e:
            self.run_main("DOL=manual", "--file", str(broken), "--filed", "2026-03-01", "--offline")
        self.assertIn("Nothing was copied", str(e.exception))
        self.assertFalse((C.MANUAL / "DOL").exists())

    def test_no_sec_number_and_no_file_stops_with_the_link_and_keeps_the_last_note(self):
        C.RUN.mkdir(parents=True)
        (C.RUN / "note_HON.md").write_text("last note")
        with self.assertRaises(SystemExit) as e:
            self.run_main("DOL=manual", "--offline")
        msg = str(e.exception)
        self.assertIn("https://www.sedarplus.ca", msg)
        self.assertIn("DOL=manual --file", msg)
        self.assertIn("--filed", msg)
        self.assertTrue((C.RUN / "note_HON.md").exists())

    def test_unknown_ticker_message_gives_the_link(self):
        firms = [("19617", "JPM", "JPMorgan Chase & Co.", "NYSE")]
        orig = F.sec_firms
        F.sec_firms = lambda sec: firms
        try:
            with self.assertRaises(SystemExit) as e:
                F.company("QQZZ", object())
        finally:
            F.sec_firms = orig
        self.assertIn("https://www.sedarplus.ca", str(e.exception))
        self.assertIn("https://www.google.com/search?q=TSX+QQZZ+annual+information+form+pdf", str(e.exception))
        self.assertIn("QQZZ=manual --file", str(e.exception))

    def test_holdings_with_a_sedar_firm_do_not_stop(self):
        h = Path(self.d) / "h.txt"
        h.write_text("DOL\n")
        out = self.run_main("--holdings", str(h), "--offline")
        self.assertIn("holdings: 1 firms", out)


class DirectLinkTests(unittest.TestCase):
    """The user is given the company's own filings page (canada.csv); no US ticker is captured by a Canadian name."""
    def test_no_us_ticker_or_firm_is_captured_by_a_canadian_name(self):
        firms = [("60086", "L", "LOEWS CORP", "NYSE"), ("1594805", "SHOP", "SHOPIFY INC.", "Nasdaq")]
        orig = F.sec_firms
        F.sec_firms = lambda sec: firms
        try:
            self.assertEqual(F.company("L", object())["cik"], "60086")
            self.assertEqual(F.company("shopify", object())["cik"], "1594805")
        finally:
            F.sec_firms = orig

    def test_stop_message_gives_the_company_link_then_sedar(self):
        msg = F.canadian_file(C.canada()["DOL"])
        lines = msg.splitlines()
        self.assertEqual(lines[0], F.BLOCK_START)
        self.assertIn("Download link: https://www.dollarama.com/en-CA/corp/wp-content/uploads/2026/04/"
                      "2026-Annual-Information-Form-EN.pdf", lines)             # the link alone on its line
        self.assertIn("SEDAR+: https://www.sedarplus.ca", lines)
        self.assertIn("For the AI: a file given: run again as DOL=manual --file", msg)
        self.assertLess(lines.index(F.BLOCK_END), [i for i, x in enumerate(lines) if x.startswith("For the AI")][0])
        self.assertNotIn("google", msg)

class CanadaListTests(unittest.TestCase):
    """Large SEDAR+-only firms: own filing link, found by ticker only when SEC has no such ticker."""
    def setUp(self):
        self.orig = F.sec_firms
        F.sec_firms = lambda sec: [("60086", "L", "LOEWS CORP", "NYSE"), ("19617", "JPM", "JPMorgan Chase & Co.", "NYSE")]

    def tearDown(self):
        F.sec_firms = self.orig

    def test_symbol_sec_does_not_list_goes_to_the_canadian_firm(self):
        co = F.company("FM", object())
        self.assertEqual((co["ticker"], co["cik"], co["name"]), ("FM", "", "First Quantum Minerals Ltd."))
        self.assertTrue(co["filings_link"].startswith("https://www.first-quantum.com/"))

    def test_us_ticker_stays_the_us_firm_and_name_reaches_the_canadian_one(self):
        self.assertEqual(F.company("L", object())["cik"], "60086")
        self.assertEqual(F.company("Loblaw", object())["name"], "Loblaw Companies Limited")
        self.assertEqual(F.company("L=manual", object())["name"], "Loblaw Companies Limited")
        self.assertEqual(F.company("First Quantum", object())["ticker"], "FM")

    def test_every_canada_row_has_a_company_link(self):
        for t, r in C.canada().items():
            self.assertTrue(r["filings_link"].startswith("https://"), t)

    def test_unknown_name_gives_a_search_link_for_that_name(self):
        with self.assertRaises(SystemExit) as e:
            F.company("Boralex", object())
        self.assertIn("https://www.google.com/search?q=Boralex+annual+information+form+pdf", str(e.exception))
        msg = str(e.exception)
        block = msg[msg.index(F.BLOCK_START):msg.index(F.BLOCK_END)]
        self.assertNotIn("files only", block)                  # never claims an unmatched firm is Canadian
        self.assertIn('No SEC filer matches "Boralex".', block)
        self.assertIn("A US company:", block)
        self.assertIn("A Canadian company:", block)

    def test_canada_post_gets_a_neutral_block_with_a_search_link(self):
        with self.assertRaises(SystemExit) as e:
            F.company("Canada Post", object())
        lines = str(e.exception).splitlines()
        self.assertIn("Search link: https://www.google.com/search?q=Canada+Post+annual+information+form+pdf", lines)
        self.assertNotIn("SEDAR+ only", str(e.exception))

    def test_known_canadian_firm_is_stated_as_such(self):
        msg = F.canadian_file(C.canada()["FM"])
        self.assertIn("First Quantum Minerals Ltd. files only in Canada (SEDAR+). This tool does not download from SEDAR+: you download the file yourself.", msg)
        self.assertIn("Download link: https://www.first-quantum.com/", msg)


class SameFileDateTests(unittest.TestCase):
    def test_a_file_put_there_by_hand_gets_its_date_from_file(self):
        d, cwd = tempfile.mkdtemp(), os.getcwd()
        os.chdir(d)
        try:
            (C.MANUAL / "DOL").mkdir(parents=True)
            (C.MANUAL / "DOL" / "aif.txt").write_bytes(AIF)
            dl = Path(d) / "aif.txt"
            dl.write_bytes(AIF)
            with redirect_stdout(io.StringIO()):
                F.main(["DOL=manual", "--file", str(dl), "--filed", "2026-04-14", "--offline"])
            self.assertEqual([s["filing date"] for _, s in F.manual_docs("DOL")], ["2026-04-14"])
            ps = C.read_json(C.RUN / "passages.json")["passages"]
            self.assertTrue(ps and all(p["filed"] == "2026-04-14" for p in ps))
        finally:
            os.chdir(cwd)
            shutil.rmtree(d)


class PageDateTests(unittest.TestCase):
    """--filed is optional: the date on the file's first pages is used and labelled; asked for when there is none."""
    def setUp(self):
        self.d, self.cwd = tempfile.mkdtemp(), os.getcwd()
        os.chdir(self.d)

    def tearDown(self):
        os.chdir(self.cwd)
        shutil.rmtree(self.d)

    def write(self, text):
        f = Path(self.d) / "aif.txt"
        f.write_text(text)
        return f

    def run_main(self, *args):
        with redirect_stdout(io.StringIO()) as out:
            F.main(list(args))
        return out.getvalue()

    def test_date_on_the_first_page_is_used_and_labelled(self):
        f = self.write("Annual Information Form For the financial year ended December 31, 2025\n\nMarch 12, 2026\n\n"
                       "DBRS Morningstar rates our notes BBB with a stable trend.")
        out = self.run_main("DOL=manual", "--file", str(f), "--offline")
        self.assertIn("filing date 2026-03-12, read from the file's first pages: check it", out)
        src = (C.MANUAL / "DOL" / "aif.txt.source.txt").read_text()
        self.assertIn("filing date: 2026-03-12", src)
        self.assertIn("not a SEDAR+ filing date", src)
        ps = C.read_json(C.RUN / "passages.json")["passages"]
        self.assertTrue(ps and all(p["filed"] == "2026-03-12" and "first page" in p["form"] for p in ps))

    def test_unreadable_pdf_without_a_date_says_why_not_no_date(self):
        """Live run 2026-11-12: with pypdf missing, a PDF gave "no date found"; the real reason must come first."""
        f = Path(self.d) / "aif.pdf"
        f.write_bytes(b"not a pdf")
        with self.assertRaises(SystemExit) as e:
            self.run_main("DOL=manual", "--file", str(f), "--offline")
        self.assertIn("Nothing was copied", str(e.exception))
        self.assertNotIn("no date found", str(e.exception))
        self.assertFalse((C.MANUAL / "DOL").exists())

    def test_a_year_end_alone_is_not_taken_as_the_date(self):
        f = self.write("Annual Information Form for the year ended April 26, 2026\n\nS&P rates us BBB.")
        with self.assertRaises(SystemExit) as e:
            self.run_main("DOL", "--file", str(f), "--offline")
        self.assertIn(F.BLOCK_START, str(e.exception))
        self.assertIn("Give me its filing date (YYYY-MM-DD)", str(e.exception))
        self.assertFalse((C.MANUAL / "DOL").exists())

    def test_a_past_date_needs_the_real_filing_date(self):
        f = self.write("Annual Information Form\n\nMarch 12, 2026\n\nS&P rates us BBB.")
        with self.assertRaises(SystemExit) as e:
            self.run_main("DOL=manual", "--file", str(f), "--as-of", "2026-06-30", "--offline")
        self.assertIn("--as-of", str(e.exception))
        self.assertFalse((C.MANUAL / "DOL").exists())

    def test_given_date_wins_over_the_page(self):
        f = self.write("Annual Information Form\n\nMarch 12, 2026\n\nS&P rates us BBB.")
        self.run_main("DOL=manual", "--file", str(f), "--filed", "2026-03-20", "--offline")
        src = (C.MANUAL / "DOL" / "aif.txt.source.txt").read_text()
        self.assertIn("filing date: 2026-03-20", src)
        self.assertNotIn("first page", src)

    def test_blocks_ask_for_the_file_path_only(self):
        for msg in (F.canadian_file(C.canada()["FM"]), F.unknown_firm("Boralex", ticker=False)):
            block = msg[msg.index(F.BLOCK_START):msg.index(F.BLOCK_END)]
            self.assertIn("then give me the file path.", block)
            self.assertNotIn("YYYY-MM-DD", block)

class SkillTextFileTests(unittest.TestCase):
    def test_skill_tells_the_ai_the_file_route_and_never_to_download(self):
        s = (SKILL / "SKILL.md").read_text()
        self.assertIn("--file", s)
        self.assertIn("--filed", s)
        self.assertIn("Never download", s)
        self.assertIn("never name or confirm a company yourself", s)
        self.assertIn("Your whole reply = that block, copied word for word", s)
        self.assertIn(F.BLOCK_START, s)
        self.assertIn("Never tell user to put files there", s)


if __name__ == "__main__":
    unittest.main()
