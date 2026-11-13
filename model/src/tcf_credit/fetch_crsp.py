"""Pipeline step 5a (LICENSED data): pull CRSP daily stock data for the panel's companies.

Goes in:  the panel from build_panel; WRDS_LOCAL_DIR, a folder with the Compustat company file and the CRSP/Compustat
          link table (wrds_comp_company.parquet, wrds_ccmxpf_linktable.parquet); and the place where your copy of the
          CRSP daily files lives (the "source", see below).
Comes out: OUT_DIR/crsp_links.csv, OUT_DIR/crsp_daily.parquet (permno, date, prc, ret, shrout, cfacpr) and
          OUT_DIR/crsp_sp500.csv (date, sprtrn). This is the "market folder" that market_features reads.
Data:     needs CRSP and Compustat through WRDS (your library must give you access). Vendor data stays on your
          computer: never put it in a repository.

Link: SEC company number (CIK) -> Compustat company id (gvkey, from comp_company.cik) -> CRSP stock id (permno, from the
CRSP/Compustat link table; link types LU/LC, primary links P/C only).
Each source file is copied to a temporary folder, filtered to the linked stocks and deleted, so the full files never
stay on disk.

The source is a folder (or an rclone remote such as "myremote:path") that holds daily_1999-2022/CRSP_DSF_<year>*.parquet
and crsp_dsf_2022-01-03_to_2024-12-30.zip. Give it with --source or the environment variable TCF_CRSP_SOURCE.
Usage: python -m tcf_credit.fetch_crsp PANEL_CSV WRDS_LOCAL_DIR OUT_DIR --source SOURCE [--from-year 2009]
"""
import io
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

import pandas as pd

COLS = ["permno", "date", "prc", "ret", "shrout", "cfacpr", "sprtrn"]


def source_from(args: list) -> str:
    """Where the CRSP files are: --source VALUE, else the environment variable TCF_CRSP_SOURCE. Stops with a message if
    neither is given. VALUE is a local folder, or an rclone remote path (contains ":" and is not a folder)."""
    value = args[args.index("--source") + 1] if "--source" in args else os.environ.get("TCF_CRSP_SOURCE", "")
    if not value:
        raise SystemExit("Say where your CRSP files are: --source FOLDER_OR_RCLONE_REMOTE or set TCF_CRSP_SOURCE "
                         "(expected layout: daily_1999-2022/CRSP_DSF_<year>*.parquet and the 2022-2024 zip).")
    if ":" not in value and not Path(value).is_dir():
        raise SystemExit(f"CRSP source folder not found: {value}")
    return value


def list_daily(source: str) -> list:
    """File names of the yearly daily-file parquets in <source>/daily_1999-2022."""
    if Path(source).is_dir():
        return sorted(p.name for p in (Path(source) / "daily_1999-2022").glob("CRSP_DSF_*.parquet"))
    return subprocess.run(["rclone", "lsf", f"{source}/daily_1999-2022", "--include", "CRSP_DSF_*.parquet"],
                          capture_output=True, text=True, check=True).stdout.split()


def copy_in(source: str, relative: str, local: Path) -> None:
    """Copy <source>/<relative> to the temporary file `local` (plain copy for a folder, rclone for a remote)."""
    if Path(source).is_dir():
        shutil.copyfile(Path(source) / relative, local)
    else:
        subprocess.run(["rclone", "copyto", f"{source}/{relative}", str(local)], check=True)


def links(panel_csv: str, wdir: Path) -> pd.DataFrame:
    """Which stocks belong to the panel's companies, and for which dates the link holds."""
    ciks = set(pd.read_csv(panel_csv, usecols=["cik"]).cik.astype(str))
    comp = pd.read_parquet(wdir / "wrds_comp_company.parquet", columns=["gvkey", "cik"]).dropna()
    comp["cik"] = comp.cik.astype(str).str.lstrip("0")
    comp = comp[comp.cik.isin(ciks)]
    ccm = pd.read_parquet(wdir / "wrds_ccmxpf_linktable.parquet")
    ccm = ccm[ccm.linktype.isin(["LU", "LC"]) & ccm.linkprim.isin(["P", "C"])]
    out = comp.merge(ccm[["gvkey", "lpermno", "linkdt", "linkenddt"]], on="gvkey")
    out = out.rename(columns={"lpermno": "permno"})
    out["permno"] = out.permno.astype(int)
    return out


def clean(df: pd.DataFrame, permnos: set) -> pd.DataFrame:
    """Keep the needed columns of a raw CRSP file, with lower-case names and real dates."""
    df.columns = [c.lower() for c in df.columns]
    df = df[[c for c in COLS if c in df.columns]]
    df = df[df.permno.notna()]
    df["permno"] = df.permno.astype(int)
    df["date"] = pd.to_datetime(df.date)
    return df


def main():
    """Build the link table, then read every CRSP daily file once and keep only the linked stocks' rows."""
    args = sys.argv[1:]
    source = source_from(args)
    panel_csv, wdir, out = args[0], Path(args[1]), Path(args[2])
    from_year = int(args[args.index("--from-year") + 1]) if "--from-year" in args else 2009
    out.mkdir(parents=True, exist_ok=True)
    lk = links(panel_csv, wdir)
    lk.to_csv(out / "crsp_links.csv", index=False)
    permnos = set(lk.permno)
    print(f"{lk.cik.nunique()} CIKs linked to {len(permnos)} permnos", flush=True)
    names = list_daily(source)
    names = sorted(n for n in names if int(n.split("_")[2]) >= from_year)
    parts, market = [], []
    with tempfile.TemporaryDirectory() as tmp:
        for n in names:
            local = Path(tmp) / n
            copy_in(source, f"daily_1999-2022/{n}", local)
            df = clean(pd.read_parquet(local), permnos)
            local.unlink()
            market.append(df[["date", "sprtrn"]].drop_duplicates("date"))
            parts.append(df[df.permno.isin(permnos)].drop(columns="sprtrn"))
            print(f"{n}: {len(parts[-1])} rows kept", flush=True)
        zname = "crsp_dsf_2022-01-03_to_2024-12-30.zip"
        local = Path(tmp) / zname
        copy_in(source, zname, local)
        with zipfile.ZipFile(local) as z:
            inner = [i for i in z.namelist() if i.lower().endswith(".csv")][0]
            with z.open(inner) as fh:
                reader = pd.read_csv(io.TextIOWrapper(fh), chunksize=1_000_000, low_memory=False,
                                     usecols=lambda c: c.lower() in COLS)
                for chunk in reader:
                    df = clean(chunk, permnos)
                    market.append(df[["date", "sprtrn"]].drop_duplicates("date"))
                    parts.append(df[df.permno.isin(permnos)].drop(columns="sprtrn"))
        local.unlink()
        print(f"{zname}: done", flush=True)
    daily = pd.concat(parts).drop_duplicates(["permno", "date"]).sort_values(["permno", "date"])
    for c in ("prc", "ret", "shrout", "cfacpr"):
        daily[c] = pd.to_numeric(daily[c], errors="coerce")       # anything that is not a number becomes NaN
    daily.to_parquet(out / "crsp_daily.parquet", index=False)
    mk = pd.concat(market).drop_duplicates("date").sort_values("date")
    mk.to_csv(out / "crsp_sp500.csv", index=False)
    print(f"daily rows {len(daily)}, permnos {daily.permno.nunique()}, "
          f"dates {daily.date.min().date()}..{daily.date.max().date()}; market days {len(mk)}")


if __name__ == "__main__":
    main()
