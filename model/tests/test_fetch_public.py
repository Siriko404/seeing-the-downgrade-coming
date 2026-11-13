"""Tests for fetch_public.py (pipeline step 1: download the free inputs).

HTTP is mocked with a small fake response, so the tests need no network.
They check the file names and layout, that a finished file is skipped, and that a missing manual file is listed.
"""
import io
import tempfile
import unittest
import zipfile
from contextlib import redirect_stdout
from pathlib import Path

from tcf_credit.fetch_public import FRED, MANUAL, PHILLY, run


def xlsx_bytes() -> bytes:
    """A tiny but valid xlsx-like ZIP archive."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("xl/workbook.xml", "<workbook>" + "x" * 2000 + "</workbook>")
    return buf.getvalue()


class FakeResponse:
    """The part of an HTTP response that download() uses."""
    def __init__(self, data: bytes, status: int = 200):
        self.data, self.status, self.pos = data, status, 0

    def read(self, n: int = -1) -> bytes:
        end = len(self.data) if n < 0 else min(len(self.data), self.pos + n)
        chunk = self.data[self.pos:end]
        self.pos = end
        return chunk

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def opener(url: str, headers: dict | None = None) -> FakeResponse:
    """Answer FRED and Philadelphia Fed URLs with small valid files."""
    if "fredgraph.csv" in url:
        series = url.split("id=")[-1]
        rows = "".join(f"2026-01-{i:02d},1.0\n" for i in range(1, 29))
        return FakeResponse(f"observation_date,{series}\n{rows}".encode())
    for name in PHILLY:
        if name in url:
            return FakeResponse(xlsx_bytes())
    raise AssertionError(f"unexpected URL {url}")


class Layout(unittest.TestCase):
    """The downloaded files land at the paths the later pipeline steps read."""
    def test_names_and_folders(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            out = io.StringIO()
            with redirect_stdout(out):
                missing = run(d, ["fred", "philly"], opener=opener, pause=0)
            self.assertEqual(missing, [])
            for series in FRED:
                p = d / "fred" / f"{series}.csv"
                self.assertTrue(p.is_file(), p)
                self.assertTrue(p.read_text().startswith("observation_date,"))
            for name in PHILLY:
                self.assertTrue((d / "fred" / "realtime" / name).is_file(), name)
            self.assertEqual(list((d / "fred" / "realtime").glob("*.part")), [])
            self.assertIn("All selected files are present.", out.getvalue())


class Resume(unittest.TestCase):
    """A file that is already complete is not downloaded again."""
    def test_skip_finished_files(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / "fred" / "realtime").mkdir(parents=True)
            for series in FRED:
                (d / "fred" / f"{series}.csv").write_text(
                    f"observation_date,{series}\n" + "".join(f"2026-01-{i:02d},1.0\n" for i in range(1, 29)))
            for name in PHILLY:
                (d / "fred" / "realtime" / name).write_bytes(xlsx_bytes())

            def no_network(url, headers=None):
                raise AssertionError("a finished file should not be downloaded again")

            out = io.StringIO()
            with redirect_stdout(out):
                missing = run(d, ["fred", "philly"], opener=no_network, pause=0)
            self.assertEqual(missing, [])
            self.assertEqual(out.getvalue().count("skip "), len(FRED) + len(PHILLY))


class ManualFiles(unittest.TestCase):
    """Files that must be downloaded by hand are explained and listed at the end."""
    def test_missing_manual_file_is_listed(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            out = io.StringIO()
            with redirect_stdout(out):
                missing = run(d, ["lm", "ratings"], opener=opener, pause=0)
            text = out.getvalue()
            self.assertIn("https://sraf.nd.edu/sec-edgar-data/10-x-header-data/", text)
            self.assertIn("LoughranMcDonald_10-K_HeaderData_1993-2025.csv", text)
            self.assertIn("https://www.spglobal.com/ratings/en/regulatory/ratingshistory", text)
            self.assertIn("Still missing", text)
            self.assertEqual(len(missing), len(MANUAL))
            self.assertFalse((d / "lm").exists())
            self.assertFalse((d / "ratings").exists())

    def test_other_month_rating_file_counts(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / "ratings").mkdir()
            (d / "ratings" / "SP-Corporate-2030-01-01.zip").write_bytes(b"zip")
            out = io.StringIO()
            with redirect_stdout(out):
                missing = run(d, ["ratings"], opener=opener, pause=0)
            self.assertNotIn(str(d / "ratings" / "SP-Corporate-2026-11-01.zip"), missing)
            self.assertIn(str(d / "ratings" / "SP-Financial-2026-11-01.zip"), missing)

    def test_present_manual_file_is_not_listed(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / "lm").mkdir()
            first = MANUAL[0]
            (d / first.dest).write_text("x")
            out = io.StringIO()
            with redirect_stdout(out):
                missing = run(d, ["lm"], opener=opener, pause=0)
            self.assertNotIn(str(d / first.dest), missing)
            self.assertIn(str(d / MANUAL[1].dest), missing)


if __name__ == "__main__":
    unittest.main()
