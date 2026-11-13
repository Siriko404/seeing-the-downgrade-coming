import gzip
import tempfile
import unittest
import zipfile
from pathlib import Path

from tcf_credit.ratings_parser import COLUMNS, parse_archives, parse_xbrl

SP = """<r:ROCRA><r:OD>
<r:OSC contextRef="m">Corporate</r:OSC><r:OBNAME contextRef="m">Honeywell International Inc.</r:OBNAME>
<r:LEI contextRef="m">ISRPG12PN4EIEOEMW547</r:LEI>
<r:ORD><r:IP contextRef="m">true</r:IP><r:R contextRef="m">A</r:R><r:RAD contextRef="m">2012-08-01</r:RAD>
<r:ROL contextRef="m">Stable</r:ROL><r:OAN contextRef="m">Affirmation</r:OAN>
<r:RT contextRef="m">Issuer Credit Rating</r:RT><r:RST contextRef="m">Foreign Currency LT</r:RST></r:ORD>
</r:OD></r:ROCRA>"""

FITCH = """<rt:ROCRA><rt:OD>
<rt:OSC contextRef="m1">Corporate</rt:OSC><rt:OBNAME contextRef="m1">"Microsoft Corporation"</rt:OBNAME>
<rt:ORD><rt:IP contextRef="m1">false</rt:IP><rt:R contextRef="m1">AAA</rt:R><rt:RAD contextRef="m1">2021-04-01</rt:RAD>
<rt:RAC contextRef="m1">UP</rt:RAC><rt:RT contextRef="m1">Long Term Issuer Default Rating</rt:RT></rt:ORD>
<rt:ORD><rt:IP contextRef="m1">false</rt:IP><rt:R contextRef="m1">WD</rt:R><rt:RAD contextRef="m1">2023-01-24</rt:RAD>
<rt:RAC contextRef="m1">WO</rt:RAC><rt:RT contextRef="m1">Long Term Issuer Default Rating</rt:RT></rt:ORD>
</rt:OD></rt:ROCRA>"""

MOODYS = """<ROCRA><OD><OSC contextRef="m1">Corporate</OSC><OBNAME contextRef="m1">Tata Power Company Limited (The)</OBNAME>
<OI contextRef="m1">600036539</OI><ORD><IP contextRef="m1">true</IP><R contextRef="m1">Ba1</R>
<RAD contextRef="m1">2023-09-29</RAD><RAC contextRef="m1">UP</RAC><RT contextRef="m1">LT Corporate Family Ratings</RT></ORD></OD></ROCRA>"""


class ParseXbrl(unittest.TestCase):
    def rows(self, agency, text):
        return [dict(zip(COLUMNS, r)) for r in parse_xbrl(agency, "2026-11-01", text)]

    def test_sp_prefix_and_outlook(self):
        (r,) = self.rows("S&P", SP)
        self.assertEqual((r["obligor_name"], r["rating"], r["action_date"], r["outlook"]),
                         ("Honeywell International Inc.", "A", "2012-08-01", "Stable"))
        self.assertEqual(r["lei"], "ISRPG12PN4EIEOEMW547")

    def test_fitch_quotes_stripped_and_two_events(self):
        rows = self.rows("Fitch", FITCH)
        self.assertEqual([r["rating"] for r in rows], ["AAA", "WD"])
        self.assertEqual({r["obligor_name"] for r in rows}, {"Microsoft Corporation"})
        self.assertEqual([r["action_class"] for r in rows], ["UP", "WO"])

    def test_moodys_without_prefix(self):
        (r,) = self.rows("Moody's", MOODYS)
        self.assertEqual((r["obligor_id"], r["rating"], r["action_class"]), ("600036539", "Ba1", "UP"))

    def test_no_cusip_column(self):
        self.assertFalse([c for c in COLUMNS if "cusip" in c.lower()])

    def test_instrument_only_document_gives_no_rows(self):
        self.assertEqual(self.rows("S&P", "<r:ISD><r:IND><r:R>AA</r:R></r:IND></r:ISD>"), [])


class ParseArchives(unittest.TestCase):
    def test_end_to_end_on_a_small_archive(self):
        with tempfile.TemporaryDirectory() as d:
            data, out = Path(d, "data"), Path(d, "out")
            data.mkdir()
            with zipfile.ZipFile(data / "SP-Corporate-2026-11-01.zip", "w") as z:
                z.writestr("SP-NAME-1-Honeywell-2026-11-01-OBLIGOR.xml", SP)
                z.writestr("SP-NAME-1-Honeywell-2026-11-01-ISSUER.xml", SP)  # must be skipped
            counts = parse_archives(data, out)
            self.assertEqual(counts, {"S&P": 1})
            with gzip.open(out / "ratings_obligor_events.csv.gz", "rt") as fh:
                self.assertEqual(len(fh.read().strip().splitlines()), 2)
            self.assertIn("sha256", (out / "MANIFEST.txt").read_text())


if __name__ == "__main__":
    unittest.main()
