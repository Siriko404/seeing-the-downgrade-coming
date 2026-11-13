"""Pipeline step 5a (LICENSED data): pull CRSP prices from WRDS with one command.

Goes in:  the panel from build_panel and your WRDS user name (the `wrds` package asks for the password itself and can
          save it in your own ~/.pgpass; this module never prints, stores or logs it).
Comes out: the same market folder that fetch_crsp.py and fetch_crsp_delist.py write: crsp_links.csv,
          crsp_daily.parquet (permno, date, prc, ret, shrout, cfacpr), crsp_sp500.csv (date, sprtrn),
          crsp_vwretd.csv (date, vwretd) and crsp_delist.csv (permno, date, dlret, dlstcd). It also writes
          wrds_crsp_stocknames.parquet (the CRSP stock-names history that audit_returns.py reads).
Data:     LICENSED. CRSP and Compustat through WRDS. Vendor data stays on your computer: never put it in a repository.

Not yet run against WRDS: there is no WRDS account on the machine where this module was written. Only the unit tests
with a fake connection were run.

Usage: python -m tcf_credit.fetch_wrds PANEL_CSV OUT_DIR [--username NAME] [--from-year 2009]

Link: SEC company number (CIK) -> Compustat company id (gvkey, from comp.company.cik) -> CRSP stock id (permno, from
the CRSP/Compustat link table; link types LU/LC, primary links P/C only). The rule is the one in fetch_crsp.links:
it is reused here, so the two routes write the same crsp_links.csv.

Only the linked permnos and the needed dates are pulled, in chunks (500 stocks and five calendar years per query).
The end date is the last panel snapshot plus 12 months, because returns.py needs one year of prices after a snapshot.

Table names and where they come from (checked on WRDS's public pages on 2026-11-13, not on a live account):
  comp.company and crsp.ccmxpf_lnkhist: the Compustat company file and the CCM link table named in fetch_crsp.py.
  crsp.dsf, crsp.dsi, crsp.dsedelist, crsp.stocknames: the legacy SIZ daily stock file, daily index file, daily
    delisting file and stock-names file. WRDS "Changes to CRSP Data" says the legacy format stops with the December
    2024 release: https://wrds-www.wharton.upenn.edu/pages/data-announcements/changes-to-crsp-data/
  crsp.dsf_v2, crsp.stocknames_v2: the WRDS-built CIZ versions. The WRDS CRSP CIZ webinar ("Useful Dataset Mapping")
    maps DSF to DSF_V2 and StockNames to StockNames_V2: https://wrds-www.wharton.upenn.edu/documents/2084/Webinar.pdf
  crsp.wrds_dailyindexret_query: the WRDS CIZ daily index return view, used by WRDS's BETA_CIZ macro:
    https://wrds-www.wharton.upenn.edu/pages/wrds-research/macros/wrds-macros-betas-ciz/
  crsp.stkdelists: the CIZ delisting history (the webinar maps DSE to stkDelists).

The two CRSP formats do not mean exactly the same thing on delisting days:
  In the legacy file `ret` leaves out the delisting return, and crsp.dsedelist holds it separately (as before).
  In the CIZ file `dlyret` already includes the delisting return. So for rows after 2024 this module writes the
  delisting date to crsp_delist.csv with dlret = 0 (and no dlstcd), so returns.py does not add it a second time.
  For the same reason a missing CIZ delisting return cannot be replaced by the -30% default in returns.py.
The CIZ shares-outstanding column `shrout` is still in thousands, as in the legacy file (the WRDS CRSP introduction
notebook calls it "the number of outstanding shares (in 1000s)"), so no rescaling is needed.
"""
import sys
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

from tcf_credit.fetch_crsp import links as crsp_links

LEGACY_END = pd.Timestamp("2024-12-31")
V2_START = pd.Timestamp("2025-01-01")
CHUNK_PERMNOS = 500
CHUNK_YEARS = 5
DAILY_COLUMNS = ["permno", "date", "prc", "ret", "shrout", "cfacpr"]
DELIST_COLUMNS = ["permno", "date", "dlret", "dlstcd"]
NAME_COLUMNS = ["permno", "namedt", "nameenddt", "shrcd", "exchcd", "siccd", "ncusip", "ticker", "comnam",
                "shrcls", "permco", "hexcd", "cusip", "st_date", "end_date", "namedum"]


def option(args: list, flag: str, default=None):
    """The value after `flag` in the command line, or `default`."""
    return args[args.index(flag) + 1] if flag in args else default


def panel_window(panel_csv: str, from_year: int):
    """First and last date the market folder must cover: 1 January of --from-year to the last snapshot + 12 months."""
    panel = pd.read_csv(panel_csv, usecols=["t"], parse_dates=["t"])
    start = pd.Timestamp(year=from_year, month=1, day=1)
    end = panel.t.max() + pd.DateOffset(months=12)
    return start, end


def connect(username=None):
    """Open a WRDS connection. `wrds` is imported here only, so the module imports without the package. The package
    asks for the password itself; it is never seen or kept by this code."""
    try:
        import wrds
    except ImportError:
        raise SystemExit("The WRDS route needs the wrds package: pip install -r model/requirements.txt") from None

    if username:
        return wrds.Connection(wrds_username=username)
    return wrds.Connection()


def permno_chunks(permnos) -> list:
    """Split the stock ids into lists of at most CHUNK_PERMNOS, so one SQL query is not too large."""
    permnos = sorted(set(int(p) for p in permnos))
    return [permnos[i:i + CHUNK_PERMNOS] for i in range(0, len(permnos), CHUNK_PERMNOS)]


def date_windows(start, end) -> list:
    """Split a date range into calendar windows of at most CHUNK_YEARS, so one SQL query is not too large."""
    start, end = pd.Timestamp(start), pd.Timestamp(end)
    out, cur = [], start
    while cur <= end:
        stop = min(pd.Timestamp(year=cur.year + CHUNK_YEARS, month=1, day=1) - pd.Timedelta(days=1), end)
        out.append((cur, stop))
        cur = stop + pd.Timedelta(days=1)
    return out


def fetch_links(conn, panel_csv: str) -> pd.DataFrame:
    """Read comp.company and the CCM link table, then apply the exact link rule of fetch_crsp.links.

    The two small tables are written to a temporary folder in the layout that fetch_crsp.links reads, so this module
    does not copy that rule."""
    comp = conn.raw_sql("SELECT gvkey, cik FROM comp.company", date_cols=[])
    ccm = conn.raw_sql(
        "SELECT gvkey, lpermno, linkdt, linkenddt, linktype, linkprim "
        "FROM crsp.ccmxpf_lnkhist "
        "WHERE linktype IN ('LU', 'LC') AND linkprim IN ('P', 'C')",
        date_cols=["linkdt", "linkenddt"])
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        comp.to_parquet(tmp / "wrds_comp_company.parquet", index=False)
        ccm.to_parquet(tmp / "wrds_ccmxpf_linktable.parquet", index=False)
        return crsp_links(panel_csv, tmp)


def _daily_part(conn, table: str, permnos: list, start, end) -> pd.DataFrame:
    """One raw daily query: the legacy table or the CIZ table, with its columns renamed to the legacy names."""
    if table == "crsp.dsf":
        sql = ("SELECT permno, date, prc, ret, shrout, cfacpr FROM crsp.dsf "
               "WHERE permno IN %(permnos)s AND date >= %(start)s AND date <= %(end)s")
        date_cols = ["date"]
    else:
        sql = ("SELECT permno, dlycaldt AS date, dlyprc AS prc, dlyret AS ret, shrout, dlycumfacpr AS cfacpr "
               "FROM crsp.dsf_v2 "
               "WHERE permno IN %(permnos)s AND dlycaldt >= %(start)s AND dlycaldt <= %(end)s")
        date_cols = ["date"]
    params = {"permnos": tuple(permnos), "start": start, "end": end}
    return conn.raw_sql(sql, params=params, date_cols=date_cols)


def fetch_daily(conn, permnos, start, end) -> pd.DataFrame:
    """The linked stocks' daily rows for the needed dates, from the legacy file to 2024 and the CIZ file after."""
    parts = []
    for chunk in permno_chunks(permnos):
        for win_start, win_end in date_windows(start, end):
            if win_start <= LEGACY_END:
                parts.append(_daily_part(conn, "crsp.dsf", chunk, win_start, min(win_end, LEGACY_END)))
            if win_end >= V2_START:
                parts.append(_daily_part(conn, "crsp.dsf_v2", chunk, max(win_start, V2_START), win_end))
    if not parts:
        return pd.DataFrame(columns=DAILY_COLUMNS)
    daily = pd.concat(parts, ignore_index=True)
    daily = daily[daily.permno.notna()].copy()
    daily["permno"] = pd.to_numeric(daily.permno, errors="coerce").astype("int64")
    daily["date"] = pd.to_datetime(daily.date).astype("datetime64[us]")
    for col in ("prc", "ret", "shrout", "cfacpr"):
        daily[col] = pd.to_numeric(daily[col], errors="coerce").astype("float64")
    daily = daily[daily.permno.isin(set(int(p) for p in permnos))]
    daily = daily.drop_duplicates(["permno", "date"]).sort_values(["permno", "date"])
    return daily[DAILY_COLUMNS].reset_index(drop=True)


def fetch_index(conn, start, end) -> pd.DataFrame:
    """The S&P 500 and value-weighted market returns by day, from crsp.dsi to 2024 and the CIZ view after."""
    parts = []
    for win_start, win_end in date_windows(start, end):
        if win_start <= LEGACY_END:
            parts.append(conn.raw_sql(
                "SELECT date, sprtrn, vwretd FROM crsp.dsi "
                "WHERE date >= %(start)s AND date <= %(end)s",
                params={"start": win_start, "end": min(win_end, LEGACY_END)}, date_cols=["date"]))
        if win_end >= V2_START:
            parts.append(conn.raw_sql(
                "SELECT dlycaldt AS date, sprtrn, vwretd FROM crsp.wrds_dailyindexret_query "
                "WHERE dlycaldt >= %(start)s AND dlycaldt <= %(end)s",
                params={"start": max(win_start, V2_START), "end": win_end}, date_cols=["date"]))
    if not parts:
        return pd.DataFrame(columns=["date", "sprtrn", "vwretd"])
    idx = pd.concat(parts, ignore_index=True)
    idx["date"] = pd.to_datetime(idx.date)
    for col in ("sprtrn", "vwretd"):
        idx[col] = pd.to_numeric(idx[col], errors="coerce").astype("float64")
    return idx.drop_duplicates("date").sort_values("date").reset_index(drop=True)


def fetch_delist(conn, permnos, start, end) -> pd.DataFrame:
    """Delisting dates and returns for the linked stocks, from crsp.dsedelist to 2024 and crsp.stkdelists after.

    In the CIZ file the return on the delisting day already includes the delisting return, so the CIZ rows are written
    with dlret = 0. This keeps returns.py from adding the same return twice. The CIZ delisting table has no numeric
    dlstcd, so that column is empty for those rows."""
    parts = []
    for chunk in permno_chunks(permnos):
        for win_start, win_end in date_windows(start, end):
            if win_start <= LEGACY_END:
                part = conn.raw_sql(
                    "SELECT permno, dlstdt AS date, dlret, dlstcd FROM crsp.dsedelist "
                    "WHERE permno IN %(permnos)s AND dlstdt >= %(start)s AND dlstdt <= %(end)s",
                    params={"permnos": tuple(chunk), "start": win_start, "end": min(win_end, LEGACY_END)},
                    date_cols=["date"])
                part["_v2"] = False
                parts.append(part)
            if win_end >= V2_START:
                part = conn.raw_sql(
                    "SELECT permno, delistingdt AS date, delret AS dlret, CAST(NULL AS INTEGER) AS dlstcd "
                    "FROM crsp.stkdelists "
                    "WHERE permno IN %(permnos)s AND delistingdt >= %(start)s AND delistingdt <= %(end)s",
                    params={"permnos": tuple(chunk), "start": max(win_start, V2_START), "end": win_end},
                    date_cols=["date"])
                part["_v2"] = True
                parts.append(part)
    if not parts:
        return pd.DataFrame(columns=DELIST_COLUMNS)
    out = pd.concat(parts, ignore_index=True)
    out = out[out.permno.notna()].copy()
    out["permno"] = pd.to_numeric(out.permno, errors="coerce").astype("int64")
    out["date"] = pd.to_datetime(out.date)
    out["dlret"] = pd.to_numeric(out.dlret, errors="coerce").astype("float64")
    out["dlstcd"] = pd.to_numeric(out.dlstcd, errors="coerce")
    out = out[out.permno.isin(set(int(p) for p in permnos))]
    out.loc[out["_v2"], "dlret"] = 0.0
    out.loc[out["_v2"], "dlstcd"] = np.nan
    out = out.drop_duplicates(["permno", "date"]).sort_values(["permno", "date"])
    return out[DELIST_COLUMNS].reset_index(drop=True)


def _names_v2_to_legacy(df: pd.DataFrame) -> pd.DataFrame:
    """Turn CIZ stocknames_v2 rows into the legacy stocknames columns, using the share-code mapping in the CRSP
    cross-reference guide. Only the ordinary common codes 10/11 can be rebuilt exactly; other rows get 0."""
    out = pd.DataFrame(index=df.index)
    out["permno"] = df.permno
    out["namedt"] = df.namedt
    out["nameenddt"] = df.nameenddt
    common = ((df.securitytype == "EQTY") & (df.securitysubtype == "COM") & (df.sharetype == "NS")
              & (df.usincflg == "Y"))
    out["shrcd"] = np.select([common & (df.issuertype == "ACOR"), common & (df.issuertype == "CORP")],
                             [10, 11], default=0)
    out["exchcd"] = df.primaryexch.map({"N": 1, "A": 2, "Q": 3}).fillna(0)
    out["siccd"] = df.siccd
    out["ncusip"] = df.cusip
    out["ticker"] = df.ticker
    out["comnam"] = df.issuernm
    out["shrcls"] = df.shareclass if "shareclass" in df else np.nan
    out["permco"] = df.permco
    out["hexcd"] = out["exchcd"]
    out["cusip"] = df.hdrcusip
    out["st_date"] = np.nan
    out["end_date"] = np.nan
    out["namedum"] = np.nan
    return out


def fetch_names(conn, permnos) -> pd.DataFrame:
    """The stock-names history for the linked stocks (legacy table and CIZ table), in the legacy 16-column layout."""
    legacy = []
    v2 = []
    for chunk in permno_chunks(permnos):
        legacy.append(conn.raw_sql(
            "SELECT permno, namedt, nameenddt, shrcd, exchcd, siccd, ncusip, ticker, comnam, shrcls, permco, "
            "hexcd, cusip, st_date, end_date, namedum FROM crsp.stocknames "
            "WHERE permno IN %(permnos)s",
            params={"permnos": tuple(chunk)}, date_cols=["namedt", "nameenddt", "st_date", "end_date"]))
        v2.append(conn.raw_sql(
            "SELECT permno, namedt, nameenddt, permco, cusip, hdrcusip, ticker, issuernm, primaryexch, siccd, "
            "shareclass, sharetype, securitytype, securitysubtype, usincflg, issuertype FROM crsp.stocknames_v2 "
            "WHERE permno IN %(permnos)s",
            params={"permnos": tuple(chunk)}, date_cols=["namedt", "nameenddt"]))
    legacy = pd.concat(legacy, ignore_index=True) if legacy else pd.DataFrame(columns=NAME_COLUMNS)
    v2 = pd.concat(v2, ignore_index=True) if v2 else pd.DataFrame()
    frames = [legacy]
    if len(v2):
        frames.append(_names_v2_to_legacy(v2))
    names = pd.concat(frames, ignore_index=True)
    names = names[names.permno.notna()].copy()
    names["permno"] = pd.to_numeric(names.permno, errors="coerce").astype("int64")
    for col in ("shrcd", "exchcd", "siccd", "permco", "hexcd"):
        names[col] = pd.to_numeric(names[col], errors="coerce").fillna(-1).astype("int64")
    for col in ("namedt", "nameenddt", "st_date", "end_date"):
        names[col] = pd.to_datetime(names[col], errors="coerce").dt.date
    for col in ("ncusip", "ticker", "comnam", "shrcls", "cusip"):
        names[col] = names[col].astype(object)
    names["namedum"] = pd.to_numeric(names.namedum, errors="coerce").astype("float64")
    names = names[names.permno.isin(set(int(p) for p in permnos))]
    names = names.drop_duplicates(["permno", "namedt", "nameenddt"])
    return names[NAME_COLUMNS].sort_values(["permno", "namedt"]).reset_index(drop=True)


def main():
    """Sign in, pull the link table, prices, index returns, delisting returns and names, and write the market folder."""
    args = sys.argv[1:]
    if len(args) < 2:
        raise SystemExit("Usage: python -m tcf_credit.fetch_wrds PANEL_CSV OUT_DIR "
                         "[--username NAME] [--from-year 2009]")
    panel_csv, out = args[0], Path(args[1])
    username = option(args, "--username")
    from_year = int(option(args, "--from-year", 2009))
    start, end = panel_window(panel_csv, from_year)
    out.mkdir(parents=True, exist_ok=True)
    conn = connect(username)
    link = fetch_links(conn, panel_csv)
    link.to_csv(out / "crsp_links.csv", index=False)
    permnos = sorted(set(link.permno.astype(int)))
    print(f"{link.cik.nunique()} CIKs linked to {len(permnos)} permnos", flush=True)
    daily = fetch_daily(conn, permnos, start, end)
    daily.to_parquet(out / "crsp_daily.parquet", index=False)
    index = fetch_index(conn, start, end)
    index[["date", "sprtrn"]].to_csv(out / "crsp_sp500.csv", index=False)
    index[["date", "vwretd"]].to_csv(out / "crsp_vwretd.csv", index=False)
    delist = fetch_delist(conn, permnos, start, end)
    delist.to_csv(out / "crsp_delist.csv", index=False)
    names = fetch_names(conn, permnos)
    names.to_parquet(out / "wrds_crsp_stocknames.parquet", index=False)
    print(f"daily rows {len(daily)}, permnos {daily.permno.nunique()}, "
          f"dates {daily.date.min().date()}..{daily.date.max().date()}; market days {len(index)}; "
          f"delisting rows {len(delist)}; name rows {len(names)}")


if __name__ == "__main__":
    main()
