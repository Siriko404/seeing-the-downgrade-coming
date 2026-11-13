"""Pipeline step 1: download every free input for the model with one command.

Goes in:  a data folder name and, optionally, --only with any of fred, philly, lm, ratings.
Comes out: the raw public files that later steps read:
          fred/BAA10Y.csv, fred/T10Y3M.csv, fred/VIXCLS.csv;
          fred/realtime/rucQvMd.xlsx, iptMvMd.xlsx, routput_first_second_third.xlsx;
          lm/ the Loughran-McDonald 10-K header and 10-X summaries CSV files;
          ratings/ the S&P, Fitch and Moody's rating-history ZIP files.
          The command prints a short block for each file it may not download.
Data:     public data only. FRED and the Philadelphia Fed are downloaded from the network; the Loughran-McDonald
          files and the rating histories are left to the student (see below).

Sources, what their terms and robots.txt say, checked 2026-11-13:

FRED
  Page: https://fred.stlouisfed.org/graph/fredgraph.csv?id=SERIES
  robots.txt and the legal page gave no reply from this machine (the connection timed out). The graph CSV is the
  public download named in ref/fred/README.md, with no account. Automated download: tried first, one request at a
  time. On 13 November 2026 FRED did not answer this command's requests (timeout) from a laptop or from Colab, while
  the same link opened at once in a browser. So when a download fails, the command prints the link: open it in your
  browser, which saves the CSV file, and save it under the name shown.

Philadelphia Fed Real-Time Data Set for Macroeconomists
  Page: https://www.philadelphiafed.org/surveys-and-data/real-time-data-research
  robots.txt allows the data pages (it only blocks /api, search and error pages). The xlsx links are direct public
  downloads. Automated download: yes, one request at a time.

Loughran-McDonald files at the Notre Dame Software Repository for Accounting and Finance
  Pages: https://sraf.nd.edu/sec-edgar-data/10-x-header-data/
         https://sraf.nd.edu/sec-edgar-data/lm_10x_summaries/
  sraf.nd.edu/robots.txt allows the pages. The two large CSV files are served by Google Drive and show a
  "Download anyway" button, which is a click-through. The site says the lists are free for academic research.
  Automated download: no, because of the click-through.

Rating histories under SEC Rule 17g-7(b)
  S&P page: https://www.spglobal.com/ratings/en/regulatory/ratingshistory
    robots.txt and the page both answer 403 Access Denied (a bot block). Automated download: no.
  Fitch page: https://www.fitchratings.com/ratings-history-disclosure
    robots.txt allows /regulatory, but the page fills its file list with a script and gives no direct file links;
    its terms page could not be read without that script. Automated download: no, to stay safe.
  Moody's page: https://ratings.moodys.com/sec-17g-7b
    The terms of use forbid bots, spiders, scraping and data mining. Automated download: no.
  Never use a mirror or a copy of a paid vendor's file.

Usage: python -m tcf_credit.fetch_public DATA_DIR [--only fred,philly,lm,ratings]
"""
import argparse
import time
import urllib.error
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

UA = "tcf-credit-teaching/1.0"
TIMEOUT = 60
PAUSE = 0.5
SOURCES = ("fred", "philly", "lm", "ratings")

# FRED graph CSV: one public request per series, no account.
FRED = {
    "BAA10Y": "https://fred.stlouisfed.org/graph/fredgraph.csv?id=BAA10Y",
    "T10Y3M": "https://fred.stlouisfed.org/graph/fredgraph.csv?id=T10Y3M",
    "VIXCLS": "https://fred.stlouisfed.org/graph/fredgraph.csv?id=VIXCLS",
}

# Philadelphia Fed xlsx links from the variable pages on 2026-11-13.
PHILLY = {
    "rucQvMd.xlsx": ("https://www.philadelphiafed.org/-/media/FRBP/Assets/Surveys-And-Data/real-time-data/"
                     "data-files/xlsx/rucQvMd.xlsx?sc_lang=en&hash=A96BC0C2253B04EAEB8C4DC42D4F5CBA"),
    "iptMvMd.xlsx": ("https://www.philadelphiafed.org/-/media/FRBP/Assets/Surveys-And-Data/real-time-data/"
                     "data-files/xlsx/iptMvMd.xlsx?sc_lang=en&hash=71A0CD9AD2C8828F0B041196CBFB7E5E"),
    "routput_first_second_third.xlsx": (
        "https://www.philadelphiafed.org/-/media/FRBP/Assets/Surveys-And-Data/real-time-data/"
        "data-files/xlsx/routput_first_second_third.xlsx?sc_lang=en&hash=AB8BB59BBBF6840DE1448851E90D7A80"),
}


@dataclass(frozen=True)
class Manual:
    """One file the student must download by hand: the page, the file name and the place to save it."""
    page: str
    name: str
    dest: str
    note: str
    pattern: str = ""     # if set, any file with this pattern in the folder counts


# The exact files the lecture used (ref/ratings_MANIFEST.txt). Newer monthly files with the same prefixes work too.
MANUAL = (
    Manual("https://sraf.nd.edu/sec-edgar-data/10-x-header-data/",
           "LoughranMcDonald_10-K_HeaderData_1993-2025.csv",
           "lm/LoughranMcDonald_10-K_HeaderData_1993-2025.csv",
           "Click 'Download the data (1993-2025)', then 'Download anyway' if Google Drive asks.",
           "LoughranMcDonald_10-K_HeaderData_*.csv"),
    Manual("https://sraf.nd.edu/sec-edgar-data/lm_10x_summaries/",
           "Loughran-McDonald_10X_Summaries_1993-2025.csv",
           "lm/Loughran-McDonald_10X_Summaries_1993-2025.csv",
           "Click the file name, then 'Download anyway' if Google Drive asks. It is about 188 MB.",
           "Loughran-McDonald_10X_Summaries_*.csv"),
    Manual("https://www.spglobal.com/ratings/en/regulatory/ratingshistory",
           "SP-Corporate-2026-11-01.zip", "ratings/SP-Corporate-2026-11-01.zip",
           "Download the latest Corporate file. A newer monthly file with the same prefix works.",
           "SP-Corporate-*.zip"),
    Manual("https://www.spglobal.com/ratings/en/regulatory/ratingshistory",
           "SP-Financial-2026-11-01.zip", "ratings/SP-Financial-2026-11-01.zip",
           "Download the latest Financial file. A newer monthly file with the same prefix works.",
           "SP-Financial-*.zip"),
    Manual("https://www.spglobal.com/ratings/en/regulatory/ratingshistory",
           "SP-Insurance-2026-11-01.zip", "ratings/SP-Insurance-2026-11-01.zip",
           "Download the latest Insurance file. A newer monthly file with the same prefix works.",
           "SP-Insurance-*.zip"),
    Manual("https://www.fitchratings.com/ratings-history-disclosure",
           "Fitch_Ratings-2026-11-01.zip", "ratings/Fitch_Ratings-2026-11-01.zip",
           "Download the latest ratings history ZIP. A newer monthly file with the same prefix works.",
           "Fitch_Ratings-*.zip"),
    Manual("https://ratings.moodys.com/sec-17g-7b",
           "xbrl100-obligor-2026-10-13.zip", "ratings/xbrl100-obligor-2026-10-13.zip",
           "Download the latest obligor XBRL ZIP. A newer monthly file with the same prefix works.",
           "xbrl100-obligor-*.zip"),
)


def open_url(url: str, headers: dict | None = None):
    """Open a URL with the project's User-Agent and a timeout. Tests replace this function."""
    req = urllib.request.Request(url, headers={"User-Agent": UA, **(headers or {})})
    return urllib.request.urlopen(req, timeout=TIMEOUT)


def _fred_ok(path: Path) -> bool:
    """A FRED graph CSV starts with observation_date and has one more column."""
    try:
        with path.open(encoding="utf-8") as fh:
            first = fh.readline()
    except OSError:
        return False
    return first.lower().startswith("observation_date,")


def _xlsx_ok(path: Path) -> bool:
    """An xlsx file is a ZIP archive. Check the first bytes and that the archive opens."""
    try:
        with path.open("rb") as fh:
            if fh.read(4) != b"PK\x03\x04":
                return False
        with zipfile.ZipFile(path) as z:
            return bool(z.namelist())
    except (OSError, zipfile.BadZipFile):
        return False


def _complete(path: Path, min_bytes: int, check: Callable[[Path], bool] | None) -> bool:
    """True if the file is at least min_bytes long and passes the content check."""
    return path.is_file() and path.stat().st_size >= min_bytes and (check is None or check(path))


def download(url: str, dest: Path, min_bytes: int, check: Callable[[Path], bool] | None = None,
             opener: Callable | None = None, pause: float = PAUSE) -> str:
    """Download one file to dest, skipping a complete file. Return 'ok', 'skipped' or 'failed'.

    A partial file is kept as dest + '.part' and continued with a Range request when the server allows it.
    """
    opener = opener or open_url
    dest.parent.mkdir(parents=True, exist_ok=True)
    if _complete(dest, min_bytes, check):
        print(f"skip {dest} (already complete)")
        return "skipped"
    if dest.exists():
        dest.unlink()
    part = dest.with_name(dest.name + ".part")
    have = part.stat().st_size if part.exists() else 0
    headers = {"Range": f"bytes={have}-"} if have else {}
    try:
        with opener(url, headers) as resp:
            status = getattr(resp, "status", 200)
            mode = "ab" if have and status == 206 else "wb"
            if mode == "wb":
                have = 0
            with part.open(mode) as fh:
                while True:
                    block = resp.read(1 << 20)
                    if not block:
                        break
                    fh.write(block)
        if not _complete(part, min_bytes, check):
            part.unlink(missing_ok=True)
            print(f"FAILED {dest}: the download is too small or not the expected file")
            return "failed"
        part.replace(dest)
        print(f"ok {dest} ({dest.stat().st_size:,} bytes)")
        return "ok"
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        print(f"FAILED {dest}: {type(e).__name__}: {e}")
        return "failed"
    finally:
        if pause:
            time.sleep(pause)


def fetch_fred(data_dir: Path, opener: Callable | None = None, pause: float = PAUSE) -> list[str]:
    """Download the three daily FRED series. Return the destinations that failed.

    For each failed series it prints the link to open in a browser and where to save the file.
    """
    failed = []
    for series, url in FRED.items():
        dest = data_dir / "fred" / f"{series}.csv"
        if download(url, dest, 100, _fred_ok, opener, pause) == "failed":
            failed.append((url, dest))
    if failed:
        print("FRED did not answer the automatic download. Open each link in your browser (it saves a CSV file),")
        print("then move the file to the place shown and run the command again:")
        for url, dest in failed:
            print(f"  Link: {url}")
            print(f"  Save: {dest}")
            print()
    return [str(dest) for _, dest in failed]


def fetch_philly(data_dir: Path, opener: Callable | None = None, pause: float = PAUSE) -> list[str]:
    """Download the three Philadelphia Fed real-time spreadsheets. Return the destinations that failed."""
    failed = []
    for name, url in PHILLY.items():
        dest = data_dir / "fred" / "realtime" / name
        if download(url, dest, 1000, _xlsx_ok, opener, pause) == "failed":
            failed.append(str(dest))
    return failed


def _manual_present(data_dir: Path, m: Manual) -> bool:
    """True if the exact file is there, or if any file matches its pattern (ratings use monthly names)."""
    if m.pattern:
        folder = data_dir / Path(m.dest).parent
        return any(_complete(p, 1, None) for p in folder.glob(m.pattern))
    return _complete(data_dir / m.dest, 1, None)


def missing_manual(data_dir: Path) -> list[Manual]:
    """The manual files that are not in the data folder yet."""
    return [m for m in MANUAL if not _manual_present(data_dir, m)]


def print_manual(missing: list[Manual], data_dir: Path) -> None:
    """Print one short block per file: page, exact file and where to save it."""
    if not missing:
        return
    print("Manual download needed (this source does not allow automated downloads):")
    for m in missing:
        print(f"  Page: {m.page}")
        print(f"  File: {m.name}")
        print(f"  Save: {data_dir / m.dest}")
        print(f"  Note: {m.note}")
        print()


def run(data_dir: Path, only: list[str], opener: Callable | None = None, pause: float = PAUSE) -> list[str]:
    """Run the selected sources. Return a list of files that are still missing at the end."""
    data_dir = Path(data_dir)
    missing: list[str] = []
    if "fred" in only:
        missing += fetch_fred(data_dir, opener, pause)
    if "philly" in only:
        missing += fetch_philly(data_dir, opener, pause)
    manual = missing_manual(data_dir) if ("lm" in only or "ratings" in only) else []
    if "lm" in only:
        selected = [m for m in manual if m.dest.startswith("lm/")]
        print_manual(selected, data_dir)
        missing += [str(data_dir / m.dest) for m in selected]
    if "ratings" in only:
        selected = [m for m in manual if m.dest.startswith("ratings/")]
        print_manual(selected, data_dir)
        missing += [str(data_dir / m.dest) for m in selected]
    if missing:
        print(f"Still missing {len(missing)} file(s):")
        for name in missing:
            print(f"  {name}")
    else:
        print("All selected files are present.")
    return missing


def main(argv: list[str] | None = None) -> None:
    """Read the command line and run the requested sources."""
    parser = argparse.ArgumentParser(description="Download the free inputs of the credit model.")
    parser.add_argument("data_dir", type=Path, help="folder for the downloaded data")
    parser.add_argument("--only", default=",".join(SOURCES),
                        help="comma-separated sources: fred,philly,lm,ratings (default: all)")
    args = parser.parse_args(argv)
    only = [s.strip() for s in args.only.split(",") if s.strip()]
    bad = [s for s in only if s not in SOURCES]
    if bad:
        parser.error(f"unknown source(s): {', '.join(bad)}; choose from {', '.join(SOURCES)}")
    run(args.data_dir, only)


if __name__ == "__main__":
    main()
