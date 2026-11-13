"""Regression tests for fixes made after a review of the tools (fetching, caching, notes). Each test fails on the
code before its fix. Standard library only: python3 -m unittest discover -s tests
"""
import gzip
import hashlib
import http.client
import json
import os
import shutil
import ssl
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1] / "skills" / "credit-watch"
TOOLS = SKILL / "tools"
sys.path.insert(0, str(TOOLS))
os.environ["CREDIT_WATCH_SCORES"] = str(Path(tempfile.gettempdir()) / "credit-watch-tests-no-scores.csv")
os.environ["CREDIT_WATCH_MODEL"] = ""
import common as C  # noqa: E402
import fetch as F   # noqa: E402
import check as K   # noqa: E402

URL = "https://www.sec.gov/Archives/edgar/data/999/000000099926000001/a.htm"
BODY = b"<html><body><p>S&amp;P rates us A.</p></body></html>"


class Resp:
    def __init__(self, mode):
        self.mode = mode
        self.headers = {"Content-Encoding": "gzip"} if mode != "plain" else {}

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self, n):
        if self.mode == "incomplete":
            raise http.client.IncompleteRead(b"abc")
        if self.mode == "ssl":
            raise ssl.SSLError("record layer failure")
        if self.mode == "badgzip":
            return b"not gzip at all"
        if self.mode == "plain":
            return BODY
        return gzip.compress(BODY)


class Opener:
    def __init__(self, mode):
        self.mode, self.calls = mode, 0

    def open(self, req, timeout=0):
        self.calls += 1
        return Resp(self.mode)


class NetworkTests(unittest.TestCase):
    """D10 and D11: a broken response or a damaged saved copy never ends the run in a traceback."""
    def setUp(self):
        self.d = Path(tempfile.mkdtemp())
        self.sleep, F.time.sleep = F.time.sleep, lambda *_: None

    def tearDown(self):
        F.time.sleep = self.sleep
        shutil.rmtree(self.d)

    def sec(self, mode):
        s = F.Sec("test contact", self.d)
        s.opener = Opener(mode)
        return s

    def saved(self):
        return self.d / (hashlib.sha1(URL.encode()).hexdigest() + ".gz")

    def test_broken_responses_end_as_connection_error(self):
        for mode in ("incomplete", "ssl", "badgzip"):
            with self.assertRaises(ConnectionError, msg=mode):
                self.sec(mode).get(URL, keep=True)
            self.assertFalse(self.saved().exists(), mode)

    def test_a_good_response_is_saved_whole(self):
        self.assertEqual(self.sec("ok").get(URL, keep=True), BODY)
        self.assertEqual(gzip.decompress(self.saved().read_bytes()), BODY)
        self.assertEqual([p.name for p in self.d.iterdir()], [self.saved().name])     # no temporary file left

    def test_damaged_saved_copy_is_fetched_again(self):
        for damaged in (gzip.compress(BODY * 50)[:40], b"", gzip.compress(b"")):
            self.saved().write_bytes(damaged)
            s = self.sec("ok")
            self.assertEqual(s.get(URL, keep=True), BODY)
            self.assertEqual(s.opener.calls, 1)
            self.assertEqual(gzip.decompress(self.saved().read_bytes()), BODY)

    def test_good_saved_copy_is_used(self):
        self.saved().write_bytes(gzip.compress(BODY))
        s = self.sec("incomplete")
        self.assertEqual(s.get(URL, keep=True), BODY)
        self.assertEqual(s.opener.calls, 0)


FORD = ("Rating Agency Actions\n\nOn March 23, 2020, Fitch downgraded our credit rating to BBB-, and on March 25, 2020, "
        "S&P downgraded our credit rating to BB+. Both Moody's and S&P now rate us as non-investment grade.")
BULLETS = ("The following rating actions were taken by these NRSROs since the filing of our 2019 Form 10-K Report:\n\n"
           "\u2022 On March 23, 2020, Fitch downgraded the credit ratings for Ford and Ford Credit (to BBB- from BBB) and "
           "maintained a negative outlook.\n\n"
           "\u2022 On March 25, 2020, Moody's downgraded the credit ratings for Ford and Ford Credit (to Ba2 from Ba1) and "
           "placed the ratings under review for downgrade (prior outlook was stable).")
ALSO = ("(a) On May 19, 2025, Moody's announced that it had revised JPMorgan Chase Bank, N.A.'s outlook to stable from "
        "developing. Moody's also affirmed JPMorgan Chase Bank, N.A.'s long-term issuer rating.")
TK = {"name": "FORD MOTOR CO", "aliases": "Ford Motor Company"}


def text_row(agency, grade, date, quote, what="credit rating", action="downgrade", entity="our"):
    return {"passage_id": "P1", "agency": agency, "rated_entity": entity, "what_is_rated": what, "grade": grade,
            "outlook_or_watch": "", "action": action, "rating_date": date, "date_kind": "action", "quote": quote}


def passage(text):
    return {"id": "P1", "kind": "text", "text": text, "filed": "2026-04-29", "ticker": "F", "doc_type": "10-Q",
            "form": "10-Q", "url": "https://www.sec.gov/Archives/edgar/data/37996/x.htm", "company": "FORD MOTOR CO"}


class TextDateTests(unittest.TestCase):
    """D9: a text row's action date must be the date of its own sentence, not any date in the passage."""
    def why(self, row, text, tk=TK):
        return K.check_row(row, passage(text), tk, text)[0]

    def test_date_of_another_agency_in_the_same_sentence_is_rejected(self):
        q = "S&P downgraded our credit rating to BB+"
        self.assertTrue(any(w.startswith("C3 date 2020-03-23 is not") for w in self.why(text_row("S&P", "BB+", "2020-03-23", q), FORD)))
        self.assertEqual(self.why(text_row("S&P", "BB+", "2020-03-25", q), FORD), [])

    def test_date_written_after_the_quote(self):
        text = ("Fitch downgraded our credit rating to BBB- on March 23, 2020, and S&P downgraded our credit rating "
                "to BB+ on March 25, 2020.")
        q = "S&P downgraded our credit rating to BB+"
        self.assertEqual(self.why(text_row("S&P", "BB+", "2020-03-25", q), text), [])
        self.assertTrue(any(w.startswith("C3 date 2020-03-23 is not") for w in self.why(text_row("S&P", "BB+", "2020-03-23", q), text)))
        q2 = "Fitch downgraded our credit rating to BBB-"
        self.assertEqual(self.why(text_row("Fitch", "BBB-", "2020-03-23", q2), text), [])

    def test_date_of_another_sentence_is_rejected(self):
        q = "Moody's downgraded the credit ratings for Ford and Ford Credit (to Ba2 from Ba1)"
        r = text_row("Moody's", "Ba2", "2020-03-23", q, "credit ratings", entity="Ford")
        self.assertTrue(any(w.startswith("C3 date 2020-03-23 is not") for w in self.why(r, BULLETS)))
        self.assertEqual(self.why({**r, "rating_date": "2020-03-25"}, BULLETS), [])

    def test_also_affirmed_takes_the_date_of_the_sentence_before_by_the_same_agency(self):
        tk = {"name": "JPMORGAN CHASE & CO", "aliases": ""}
        q = "Moody's also affirmed JPMorgan Chase Bank, N.A.'s long-term issuer rating"
        r = text_row("Moody's", "", "2025-05-19", q, "long-term issuer rating", "affirmed", "JPMorgan Chase Bank, N.A.")
        self.assertEqual(self.why(r, ALSO, tk), [])
        other = ALSO.replace("On May 19, 2025, Moody's announced", "On May 19, 2025, Fitch announced")
        self.assertTrue(any(w.startswith("C3 date 2025-05-19 is not") for w in self.why(r, other, tk)))


CAPTION_DOC = """<html><body><p>Credit Ratings</p>
<p>&#8226; On March 8, 2019, DBRS revised the outlook to negative from stable for Ford and Ford Credit and affirmed their
ratings. The following chart summarizes certain of the credit ratings and outlook presently assigned by these NRSROs:</p>
<table>
<tr><td></td><td colspan="3">Ford</td><td colspan="3">Ford Credit</td></tr>
<tr><td>NRSRO</td><td>Issuer Rating</td><td>Long-Term Senior Unsecured</td><td>Outlook / Trend</td>
<td>Long-Term Senior Unsecured</td><td>Short-Term Unsecured</td><td>Outlook / Trend</td></tr>
<tr><td>DBRS</td><td>BBB</td><td>BBB</td><td>Negative</td><td>BBB</td><td>R-2M</td><td>Negative</td></tr>
<tr><td>S&amp;P</td><td>BBB</td><td>BBB</td><td>Negative</td><td>BBB</td><td>A-2</td><td>Negative</td></tr>
</table></body></html>"""
DBRS_SENTENCE = ("On March 8, 2019, DBRS revised the outlook to negative from stable for Ford and Ford Credit and affirmed "
                 "their ratings.")


def caption_table():
    stamp = {"ticker": "F", "company": "FORD MOTOR CO", "form": "10-Q", "doc_type": "10-Q", "filed": "2019-04-26",
             "url": "https://www.sec.gov/Archives/edgar/data/37996/f.htm"}
    p = F.passages_of(F.blocks_of(CAPTION_DOC.encode(), "f.htm"), stamp, [])[0]
    return {**p, "id": "P1"}


def outlook_row(agency, quote, date="2019-03-08", entity="Ford"):
    return {"passage_id": "P1", "agency": agency, "rated_entity": entity, "what_is_rated": "outlook", "grade": "",
            "outlook_or_watch": "negative", "action": "outlook change", "rating_date": date, "date_kind": "action",
            "quote": quote}


class CaptionActionTests(unittest.TestCase):
    """D1, D2: a dated action written above a rating table binds to the agency and date of its own sentence."""
    def setUp(self):
        self.p = caption_table()
        self.line = lambda ag: next(x for x in self.p["text"].split("\n") if x.startswith("Row: NRSRO: " + ag))
        self.span = lambda ag: self.p["text"][self.p["text"].index("On March 8"):self.p["text"].index(self.line(ag))
                                              + len(self.line(ag))]

    def why(self, row):
        return K.check_row(row, self.p, TK, self.p["text"])

    def test_caption_sentence_alone_is_kept_as_a_text_row(self):
        why, n = self.why(outlook_row("DBRS Morningstar", DBRS_SENTENCE))
        self.assertEqual(why, [])
        self.assertTrue(n["read"].startswith("AI-read text"))

    def test_span_through_the_row_is_kept_for_the_agency_that_acted(self):
        why, n = self.why(outlook_row("DBRS Morningstar", self.span("DBRS")))
        self.assertEqual(why, [])
        self.assertEqual(n["row"]["quote"], self.span("DBRS"))      # the quote is kept as written
        self.assertTrue(n["read"].startswith("AI-read text"))

    def test_another_agencys_row_does_not_take_the_caption_action(self):
        self.assertTrue(self.why(outlook_row("S&P", self.span("S&P")))[0])
        self.assertTrue(self.why(outlook_row("S&P", DBRS_SENTENCE))[0])

    def test_wrong_date_and_a_sentence_from_another_filing_are_rejected(self):
        self.assertTrue(self.why(outlook_row("DBRS Morningstar", DBRS_SENTENCE, "2019-03-09"))[0])
        fitch = "On May 17, 2019, Fitch revised the outlook to negative from stable for Ford and Ford Credit."
        self.assertTrue(self.why(outlook_row("Fitch", fitch, "2019-05-17"))[0])

    def test_dated_action_quoting_only_a_row_line_is_told_to_quote_the_caption(self):
        why, _ = self.why(outlook_row("DBRS Morningstar", self.line("DBRS")))
        self.assertTrue(any("Table caption:" in w for w in why), why)

    def test_cell_rows_are_unchanged(self):
        row = {"passage_id": "P1", "agency": "S&P", "rated_entity": "Ford", "what_is_rated": "Issuer Rating",
               "grade": "BBB", "outlook_or_watch": "", "action": "none", "rating_date": "", "date_kind": "none",
               "quote": self.line("S&P")}
        why, n = self.why(row)
        self.assertEqual(why, [])
        self.assertEqual(n["read"], "table cell")

    def test_unread_caption_action_is_listed(self):
        acts = K.missing_actions([self.p], [])
        self.assertEqual([a["passage_id"] for a in acts], ["P1"])
        kept = [{"quote": DBRS_SENTENCE, "rating_date": "2019-03-08", "agency": "DBRS Morningstar"}]
        self.assertEqual(K.missing_actions([self.p], kept), [])


import finish as FN  # noqa: E402

BOEING = ("The major credit rating agencies downgraded our short term and long term credit ratings during the first "
          "quarter of 2020 and there is risk for further downgrades.")


class UnnamedAgencyTests(unittest.TestCase):
    """D3: a filing that reports a rating action without naming the agency gets a gap, and the note says so."""
    def test_sentences_found_and_left_out(self):
        blocks = lambda t: [{"kind": "p", "text": t}]
        self.assertEqual(len(F.unnamed_actions(blocks(BOEING), {})), 1)
        utx = ("In particular, following the announcement of the proposed Rockwell Collins acquisition, the credit "
               "rating agencies announced that they were reviewing our credit ratings for possible downgrades.")
        self.assertEqual(len(F.unnamed_actions(blocks(utx), {})), 1)
        for t in ("Our credit ratings could be downgraded by the rating agencies if our results weaken.",
                  "Any downgrade of our credit ratings by the rating agencies would raise our borrowing costs.",
                  "S&P downgraded our long-term credit rating to BBB- during the first quarter of 2020.",
                  "Rating agencies may lower our ratings in the future.",
                  "We check the credit rating of tenants that are rated by a nationally recognized credit rating agency, "
                  "(ii) reviewing financial statements of the tenants that are not rated.",
                  "If the rating agencies downgraded our credit ratings, our borrowing costs would rise.",
                  "We cannot know whether the credit rating agencies lowered their view of our sector."):
            self.assertEqual(F.unnamed_actions(blocks(t), {}), [], t)

    def test_fetch_reads_main_documents_not_exhibits(self):
        page = ('<tr><td>1</td><td>q</td><td><a href="/x/a.htm">a.htm</a></td><td>10-Q</td></tr>'
                '<tr><td>2</td><td>ex</td><td><a href="/x/ex99.htm">ex99.htm</a></td><td>EX-99.1</td></tr>').encode()
        sub = {"name": "BOEING CO", "sicDescription": "", "filings": {"files": [], "recent": {
            "accessionNumber": ["0000012927-20-000001"], "filingDate": ["2020-04-29"], "form": ["10-Q"],
            "primaryDocument": ["a.htm"]}}}

        class Sec:
            def get(self, url, keep):
                if "submissions" in url:
                    return json.dumps(sub).encode()
                if url.endswith("-index.htm"):
                    return page
                if url.endswith("ex99.htm"):
                    return b"<p>The rating agencies downgraded the ratings of our supplier last quarter.</p>"
                return f"<p>{BOEING}</p>".encode()
        import datetime as dt
        co = {"ticker": "BA", "name": "", "cik": "12927", "scope": "", "group": "", "aliases": ""}
        res = F.fetch_ticker(Sec(), co, dt.date(2019, 7, 1), dt.date(2020, 12, 31), lambda *a: None)
        self.assertEqual([u["sentence"] for u in res["unnamed"]], [BOEING])

    def res(self):
        tk = {"BA": {"name": "BOEING CO", "cik": "12927", "scope": "", "filings": 34, "documents": 52, "manual": 0,
                     "unreadable": [], "unnamed": [{"form": "10-Q", "filed": "2020-04-29", "sentence": BOEING}]}}
        gaps = K.gaps_for([], tk, "2020-12-31", "2019-07-01")
        return {"tickers": tk, "rows": [], "gaps": gaps, "as_of": "2020-12-31", "window_start": "2019-07-01",
                "notes": ["BA"], "missing_cells": [], "missing_actions": [], "empty_tables": [], "set_aside": []}

    def test_gap_listed_and_no_false_no_rating_claim(self):
        res = self.res()
        rules = [g["rule"] for g in res["gaps"]]
        self.assertIn("G-a changed, no agency named", rules)
        self.assertFalse(any("state no rating." in g["follow_up"] or g["what"].startswith("no rating statement in")
                             for g in res["gaps"]), res["gaps"])
        text = FN.note("BA", res)[0]
        changed = text.split("## What changed and when")[1].split("##")[0]
        self.assertNotIn("No rating action or change stated", changed)
        self.assertIn("without naming the agency", changed)


SCALE_MAP = """<html><body><p>Our rating system is designed to stratify obligors into 22 grades. The following table aligns the
relative rankings of our 22-grade internal risk ratings with the external ratings used by S&amp;P and Moody's.</p>
<table><tr><td>Ratings</td><td>BRR</td><td>S&amp;P</td><td>Moody's</td><td>Description</td></tr>
<tr><td>1</td><td>1+</td><td>AAA</td><td>Aaa</td><td>Investment grade</td></tr>
<tr><td>2</td><td>1H</td><td>AA+</td><td>Aa1</td><td>Investment grade</td></tr></table></body></html>"""


class ScaleMapTests(unittest.TestCase):
    """D5: a bank's map of its internal risk grades to agency scales is not the bank's own rating."""
    def test_internal_ratings_map_gives_no_unread_cells(self):
        stamp = {"ticker": "RY", "company": "ROYAL BANK OF CANADA", "form": "6-K", "doc_type": "EX-99.1",
                 "filed": "2020-05-27", "url": "https://www.sec.gov/Archives/edgar/data/1000275/r.htm"}
        p = {**F.passages_of(F.blocks_of(SCALE_MAP.encode(), "r.htm"), stamp, [])[0], "id": "P1"}
        self.assertEqual(K.missing_cells([p], [], {"RY": {"name": "ROYAL BANK OF CANADA", "aliases": ""}}), [])
        p2 = {**p, "table": {**p["table"], "caption": "Royal Bank of Canada credit ratings as at April 30, 2020."}}
        self.assertTrue(K.missing_cells([p2], [], {"RY": {"name": "ROYAL BANK OF CANADA", "aliases": ""}}))


class StageTests(unittest.TestCase):
    """D13: a mistyped firm stops before the last run's note is removed."""
    def setUp(self):
        self.d = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.d)

    def test_failed_lookup_keeps_the_previous_note(self):
        run = self.d / "credit-watch" / "run"
        run.mkdir(parents=True)
        (run / "note_HON.md").write_text("# Credit note: Honeywell")
        for args in (["ZZZQ", "--offline"], ["HON=abc", "--offline"]):
            r = subprocess.run([sys.executable, str(TOOLS / "fetch.py"), *args], cwd=self.d, capture_output=True,
                               text=True, env={**os.environ, "CREDIT_WATCH_MODEL": ""})
            self.assertNotEqual(r.returncode, 0, args)
            self.assertTrue((run / "note_HON.md").exists(), args)

    def test_failed_lookup_leaves_nothing_to_check_as_the_old_firm(self):
        run = self.d / "credit-watch" / "run"
        r = subprocess.run([sys.executable, str(TOOLS / "fetch.py"), "HON", "--offline"], cwd=self.d,
                           capture_output=True, text=True, env={**os.environ, "CREDIT_WATCH_MODEL": ""})
        self.assertEqual(r.returncode, 0, r.stderr)
        (run / "rows.json").write_text('{"rows": []}')
        (run / "note_HON.md").write_text("# Credit note: Honeywell")
        subprocess.run([sys.executable, str(TOOLS / "fetch.py"), "ZZZQ", "--offline"], cwd=self.d, capture_output=True,
                       text=True, env={**os.environ, "CREDIT_WATCH_MODEL": ""})
        self.assertFalse((run / "passages.json").exists())
        self.assertFalse((run / "rows.json").exists())
        c = subprocess.run([sys.executable, str(TOOLS / "check.py")], cwd=self.d, capture_output=True, text=True)
        self.assertNotEqual(c.returncode, 0)
        self.assertTrue((run / "note_HON.md").exists())


class LongPassageTests(unittest.TestCase):
    """D12: a long run of rating paragraphs is split, not cut; what is still cut is said once, for kept text only."""
    stamp = {"ticker": "X", "company": "X CORP", "form": "10-K", "doc_type": "10-K", "filed": "2026-02-01",
             "url": "https://www.sec.gov/Archives/edgar/data/1/x.htm"}

    def para(self, k, n):
        return f"Moody's rated our senior notes Baa{k % 3 + 1} with a stable outlook, note {k}. " + "Filler words. " * n

    def test_long_run_is_split_at_paragraph_ends(self):
        blocks = [{"kind": "p", "text": self.para(k, 120)} for k in range(4)]
        ps = F.passages_of(blocks, self.stamp, [])
        self.assertGreater(len(ps), 1)
        self.assertTrue(all(len(p["text"]) <= F.MAX_PASSAGE for p in ps))
        for b in blocks:
            self.assertTrue(any(b["text"] in p["text"] for p in ps))
        self.assertFalse(any(p.get("cut") for p in ps))

    def test_one_paragraph_too_long_is_cut_and_said(self):
        ps = F.passages_of([{"kind": "p", "text": self.para(1, 400)}], self.stamp, [])
        self.assertIn("cut", ps[0]["cut"])

    def test_long_table_is_said_and_its_rows_match_its_text(self):
        rows = [["", "S&P", "Moody's"]] + [[f"Series {k} notes", "BBB", "Baa2"] for k in range(80)]
        ps = F.passages_of([{"kind": "p", "text": "Ratings of our notes by S&P and Moody's:"},
                            {"kind": "table", "rows": rows}], self.stamp, [])
        t = ps[0]
        self.assertTrue(t.get("cut"))
        self.assertTrue(all(r["line"] in t["text"] for r in t["table"]["rows"]))
        short = F.passages_of([{"kind": "p", "text": "Ratings of our notes by S&P and Moody's:"},
                               {"kind": "table", "rows": rows[:5]}], self.stamp, [])[0]
        self.assertFalse(short.get("cut"))
        self.assertEqual(len(short["table"]["rows"]), 4)

    def test_cut_said_once_and_only_for_kept_passages(self):
        long_rating = self.para(1, 400)
        no_signal = "S&P ratings matter to us. " + "Filler words. " * 400          # names no grade, outlook or date
        page = lambda n: f'<tr><td>1</td><td>q</td><td><a href="/x/{n}">{n}</a></td><td>10-Q</td></tr>'.encode()
        sub = {"name": "X CORP", "sicDescription": "", "filings": {"files": [], "recent": {
            "accessionNumber": ["0000000001-26-000001", "0000000001-26-000002"],
            "filingDate": ["2026-04-23", "2026-07-23"], "form": ["10-Q", "10-Q"], "primaryDocument": ["a.htm", "b.htm"]}}}

        class Sec:
            def get(self, url, keep):
                if "submissions" in url:
                    return json.dumps(sub).encode()
                if url.endswith("-000001-index.htm"):
                    return page("a.htm")
                if url.endswith("-000002-index.htm"):
                    return page("b.htm")
                return f"<p>{long_rating}</p><p>Revenue rose.</p><p>Costs fell.</p><p>{no_signal}</p>".encode()
        import datetime as dt
        co = {"ticker": "X", "name": "", "cik": "1", "scope": "", "group": "", "aliases": ""}
        res = F.drop_terms(F.tidy(F.fetch_ticker(Sec(), co, dt.date(2026, 1, 1), dt.date(2026, 11, 7), lambda *a: None)))
        notes = F.cut_notes(res)
        self.assertEqual(len(notes), 1, notes)
        self.assertEqual(notes[0]["filed"], "2026-04-23")
        g = K.gaps_for([], {"X": {"name": "X CORP", "filings": 2, "manual": 0, "unreadable": [], "cut": notes}},
                       "2026-11-01", "2025-05-01")
        self.assertTrue(any(x["rule"] == "G-c read in part" for x in g))

class AffirmedTests(unittest.TestCase):
    """D6: 'revised the outlook ... and affirmed their ratings' keeps the affirmation beside the outlook change."""
    def test_affirmation_beside_an_outlook_change_is_kept(self):
        d = Path(tempfile.mkdtemp())
        try:
            run = d / "credit-watch" / "run"
            run.mkdir(parents=True)
            text = ("On March 8, 2019, DBRS revised the outlook to negative from stable for Ford and Ford Credit and "
                    "affirmed their ratings.")
            ps = {"made": "", "as_of": "2019-06-30", "window_start": "2018-01-01", "set_aside": [], "passages": [
                {**passage(text), "filed": "2019-04-26"}],
                "tickers": {"F": {"name": "FORD MOTOR CO", "cik": "37996", "aliases": "", "scope": "", "filings": 1,
                                  "documents": 1, "manual": 0, "unreadable": [], "source": "test"}}}
            (run / "passages.json").write_text(json.dumps(ps))
            base = {"passage_id": "P1", "agency": "DBRS Morningstar", "rated_entity": "Ford", "what_is_rated": "outlook",
                    "rating_date": "2019-03-08", "date_kind": "action", "quote": text, "grade": ""}
            rows = [{**base, "outlook_or_watch": "negative", "action": "outlook change"},
                    {**base, "what_is_rated": "ratings", "outlook_or_watch": "", "action": "affirmed"},
                    {**base, "outlook_or_watch": "", "action": "outlook change"}]
            (run / "rows.json").write_text(json.dumps({"rows": rows}))
            r = subprocess.run([sys.executable, str(TOOLS / "check.py")], cwd=d, capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)
            res = json.loads((run / "ratings.json").read_text())
            self.assertEqual(sorted(x["action"] for x in res["rows"]), ["affirmed", "outlook change"])
        finally:
            shutil.rmtree(d)


class GivenCikTests(unittest.TestCase):
    """D7: a firm given as TICKER=CIK gets a firm line with SEC's own name for that number, to check."""
    def test_sec_name_printed_for_a_given_cik(self):
        sub = {"name": "TWITTER, INC.", "sicDescription": "", "filings": {"files": [], "recent": {
            "accessionNumber": [], "filingDate": [], "form": [], "primaryDocument": []}}}

        class Sec:
            def get(self, url, keep):
                return json.dumps(sub).encode()
        import datetime as dt
        lines = []
        co = {"ticker": "TWTR", "name": "", "cik": "1418091", "scope": "", "group": "", "aliases": ""}
        F.fetch_ticker(Sec(), co, dt.date(2020, 7, 1), dt.date(2021, 12, 31), lines.append)
        self.assertTrue(any(x.startswith("firm: TWTR = TWITTER, INC., CIK 1418091") for x in lines), lines)
        lines.clear()
        F.fetch_ticker(Sec(), {**co, "name": "", "sec_name": "TWITTER, INC."}, dt.date(2020, 7, 1),
                       dt.date(2021, 12, 31), lines.append)
        self.assertFalse(any(x.startswith("firm:") for x in lines), lines)     # found by fetch: already shown


if __name__ == "__main__":
    unittest.main()
