"""Pipeline step 5a (LICENSED data): pull CRSP delisting returns and the value-weighted market return.

Goes in:  the market folder that fetch_crsp wrote (it reads CRSP_DIR/crsp_links.csv) and the same CRSP source.
Comes out: CRSP_DIR/crsp_delist.csv (permno, date, dlret, dlstcd: the return a stock earned when it was delisted and
          why) and CRSP_DIR/crsp_vwretd.csv (the market return). features_v2 needs the second file; returns.py needs
          both.
Data:     needs CRSP through WRDS. Vendor data stays on your computer: never put it in a repository.

Reads only the needed columns of each source file (copied to a temporary folder and deleted). Give the source with
--source or the environment variable TCF_CRSP_SOURCE, as for fetch_crsp.
Usage: python -m tcf_credit.fetch_crsp_delist CRSP_DIR --source SOURCE [--from-year 2009]
"""
import io
import sys
import tempfile
import zipfile
from pathlib import Path

import pandas as pd

from tcf_credit.fetch_crsp import copy_in, list_daily, source_from

WANT = ["permno", "date", "dlret", "dlstcd", "vwretd"]


def keep(df, permnos):
    """From one raw CRSP file: the delisting rows of the linked stocks and the market return by day."""
    df.columns = [c.lower() for c in df.columns]
    df = df[[c for c in WANT if c in df.columns]].copy()
    df["date"] = pd.to_datetime(df.date)
    mk = df[["date", "vwretd"]].drop_duplicates("date")
    d = df[df.dlstcd.notna() & df.permno.isin(permnos)][["permno", "date", "dlret", "dlstcd"]]
    return d, mk


def main():
    """Read every CRSP daily file once, keeping delisting rows and the market return."""
    args = sys.argv[1:]
    source = source_from(args)
    out = Path(args[0])
    from_year = int(args[args.index("--from-year") + 1]) if "--from-year" in args else 2009
    permnos = set(pd.read_csv(out / "crsp_links.csv").permno.astype(int))
    names = list_daily(source)
    names = sorted(n for n in names if int(n.split("_")[2]) >= from_year)
    dl, mk = [], []
    with tempfile.TemporaryDirectory() as tmp:
        for n in names:
            local = Path(tmp) / n
            copy_in(source, f"daily_1999-2022/{n}", local)
            d, m = keep(pd.read_parquet(local, columns=["PERMNO", "date", "DLRET", "DLSTCD", "vwretd"]), permnos)
            local.unlink()
            dl.append(d); mk.append(m)
            print(f"{n}: {len(d)} delisting rows", flush=True)
        zname = "crsp_dsf_2022-01-03_to_2024-12-30.zip"
        local = Path(tmp) / zname
        copy_in(source, zname, local)
        with zipfile.ZipFile(local) as z:
            inner = [i for i in z.namelist() if i.lower().endswith(".csv")][0]
            with z.open(inner) as fh:
                for chunk in pd.read_csv(io.TextIOWrapper(fh), chunksize=1_000_000, low_memory=False,
                                         usecols=lambda c: c.lower() in WANT):
                    chunk["DLRET" if "DLRET" in chunk else "dlret"] = pd.to_numeric(
                        chunk["DLRET" if "DLRET" in chunk else "dlret"], errors="coerce")
                    d, m = keep(chunk, permnos)
                    dl.append(d); mk.append(m)
        local.unlink()
    d = pd.concat(dl).drop_duplicates(["permno", "date"]).sort_values(["permno", "date"])
    d["dlret"] = pd.to_numeric(d.dlret, errors="coerce")
    d.to_csv(out / "crsp_delist.csv", index=False)
    m = pd.concat(mk).drop_duplicates("date").sort_values("date")
    m.to_csv(out / "crsp_vwretd.csv", index=False)
    print(f"delisting rows {len(d)} (permnos {d.permno.nunique()}, dlret missing {d.dlret.isna().sum()}); "
          f"market days {len(m)}, vwretd missing {m.vwretd.isna().sum()}")


if __name__ == "__main__":
    main()
