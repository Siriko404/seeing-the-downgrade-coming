"""Tests for fetch_wrds.py (pipeline step 5a, licensed route through WRDS).

A fake connection with the same `raw_sql(sql, params=..., date_cols=...)` interface as wrds.Connection serves small
made-up tables. No data, no internet and no WRDS account are needed.
"""
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

from tcf_credit import fetch_wrds
from tcf_credit.features_v2 import V2_COLUMNS
from tcf_credit.market_features import EMPTY

# The output column types named in ref/crsp_layout_schema.txt.
DAILY_SCHEMA = [("permno", "int64"), ("date", "timestamp[us]"), ("prc", "double"), ("ret", "double"),
                ("shrout", "double"), ("cfacpr", "double")]
NAME_SCHEMA = [("permno", "int64"), ("namedt", "date32[day]"), ("nameenddt", "date32[day]"), ("shrcd", "int64"),
               ("exchcd", "int64"), ("siccd", "int64"), ("ncusip", "string"), ("ticker", "string"),
               ("comnam", "string"), ("shrcls", "string"), ("permco", "int64"), ("hexcd", "int64"),
               ("cusip", "string"), ("st_date", "date32[day]"), ("end_date", "date32[day]"), ("namedum", "double")]

TABLE_SPECS = {
    "comp.company": {},
    "crsp.ccmxpf_lnkhist": {},
    "crsp.stocknames_v2": {"permno": "permno"},
    "crsp.stocknames": {"permno": "permno"},
    "crsp.dsedelist": {"permno": "permno", "date": "dlstdt", "rename": {"dlstdt": "date"}},
    "crsp.stkdelists": {"permno": "permno", "date": "delistingdt",
                        "rename": {"delistingdt": "date", "delret": "dlret"}, "add": {"dlstcd": np.nan}},
    "crsp.wrds_dailyindexret_query": {"date": "dlycaldt", "rename": {"dlycaldt": "date"}},
    "crsp.dsi": {"date": "date"},
    "crsp.dsf_v2": {"permno": "permno", "date": "dlycaldt",
                    "rename": {"dlycaldt": "date", "dlyprc": "prc", "dlyret": "ret", "dlycumfacpr": "cfacpr"}},
    "crsp.dsf": {"permno": "permno", "date": "date"},
}
# Longer names first, so crsp.dsf_v2 is not mistaken for crsp.dsf.
TABLE_ORDER = ["crsp.ccmxpf_lnkhist", "comp.company", "crsp.stocknames_v2", "crsp.stocknames",
               "crsp.wrds_dailyindexret_query", "crsp.dsedelist", "crsp.stkdelists", "crsp.dsi",
               "crsp.dsf_v2", "crsp.dsf"]


class FakeConnection:
    """A stand-in for wrds.Connection that serves made-up tables and records every SQL call."""

    def __init__(self, tables: dict):
        self.tables = tables
        self.calls = []

    def raw_sql(self, sql, params=None, date_cols=None):
        self.calls.append(SimpleNamespace(sql=sql, params=params, date_cols=date_cols))
        key = next(k for k in TABLE_ORDER if k in sql)
        spec = TABLE_SPECS[key]
        df = self.tables[key].copy()
        params = params or {}
        if "permnos" in params and "permno" in spec:
            df = df[df[spec["permno"]].isin(list(params["permnos"]))]
        if "start" in params and spec.get("date"):
            df = df[df[spec["date"]] >= pd.Timestamp(params["start"])]
        if "end" in params and spec.get("date"):
            df = df[df[spec["date"]] <= pd.Timestamp(params["end"])]
        for col, value in spec.get("add", {}).items():
            df[col] = value
        return df.rename(columns=spec.get("rename", {}))

    def sql_for(self, table):
        """The SQL strings that asked for one table."""
        return [c.sql for c in self.calls if table in c.sql]


def empty_tables(**overrides):
    """Every fake table, empty with the right columns, then replace the ones a test needs."""
    tables = {
        "comp.company": pd.DataFrame(columns=["gvkey", "cik"]),
        "crsp.ccmxpf_lnkhist": pd.DataFrame(
            columns=["gvkey", "lpermno", "linkdt", "linkenddt", "linktype", "linkprim"]),
        "crsp.dsf": pd.DataFrame(columns=["permno", "date", "prc", "ret", "shrout", "cfacpr"]),
        "crsp.dsf_v2": pd.DataFrame(
            columns=["permno", "dlycaldt", "dlyprc", "dlyret", "shrout", "dlycumfacpr"]),
        "crsp.dsi": pd.DataFrame(columns=["date", "sprtrn", "vwretd"]),
        "crsp.wrds_dailyindexret_query": pd.DataFrame(columns=["dlycaldt", "sprtrn", "vwretd"]),
        "crsp.dsedelist": pd.DataFrame(columns=["permno", "dlstdt", "dlret", "dlstcd"]),
        "crsp.stkdelists": pd.DataFrame(columns=["permno", "delistingdt", "delret"]),
        "crsp.stocknames": pd.DataFrame(columns=fetch_wrds.NAME_COLUMNS),
        "crsp.stocknames_v2": pd.DataFrame(
            columns=["permno", "namedt", "nameenddt", "permco", "cusip", "hdrcusip", "ticker", "issuernm",
                     "primaryexch", "siccd", "shareclass", "sharetype", "securitytype", "securitysubtype",
                     "usincflg", "issuertype"]),
    }
    tables.update(overrides)
    return tables


def write_panel(folder: Path, rows) -> Path:
    """Write a small panel, with every column that market_features and features_v2 read."""
    base = {"debt": 1000.0, "debt_current": 200.0, "label": 0, "debt_assets": 0.3, "ebit_assets": 0.1,
            "ebit_interest": 5.0, "cfo_debt": 0.2, "cash_assets": 0.1, "op_margin": 0.1, "debt_ebitda": 2.0}
    df = pd.DataFrame([{**base, **r} for r in rows])
    path = folder / "panel.csv"
    df.to_csv(path, index=False)
    return path


def link_case():
    """Two panel CIKs and a CCM table with the rows the link rule must keep and must drop."""
    tables = empty_tables()
    tables["comp.company"] = pd.DataFrame({"gvkey": ["100", "200", "300"], "cik": ["0001", "2", "3"]})
    tables["crsp.ccmxpf_lnkhist"] = pd.DataFrame({
        "gvkey": ["100", "100", "100", "100", "200", "300"],
        "lpermno": [10001, 10002, 10003, 10004, 20001, 30001],
        "linkdt": pd.to_datetime(["2009-01-01"] * 6),
        "linkenddt": pd.to_datetime(["2099-12-31"] * 6),
        "linktype": ["LU", "LC", "LS", "LU", "LU", "LU"],
        "linkprim": ["P", "C", "P", "J", "P", "P"],
    })
    tmp = tempfile.TemporaryDirectory()
    panel = write_panel(Path(tmp.name), [{"cik": "1", "t": "2021-03-01"}, {"cik": "2", "t": "2021-03-01"}])
    return FakeConnection(tables), panel, tmp


def market_case():
    """A fake with enough daily rows for market_features and features_v2, plus one legacy delisting."""
    rng = np.random.default_rng(0)
    dates = pd.bdate_range("2019-01-01", "2021-03-01")
    mkt = pd.Series(rng.normal(0.0002, 0.01, len(dates)), index=dates)
    tables = empty_tables()
    tables["comp.company"] = pd.DataFrame({"gvkey": ["100", "200"], "cik": ["0001", "2"]})
    tables["crsp.ccmxpf_lnkhist"] = pd.DataFrame({
        "gvkey": ["100", "200"], "lpermno": [10001, 20001], "linkdt": pd.to_datetime(["2009-01-01"] * 2),
        "linkenddt": pd.to_datetime(["2099-12-31"] * 2), "linktype": ["LU", "LU"], "linkprim": ["P", "P"]})
    daily = []
    for permno, beta in ((10001, 2.0), (20001, 1.0)):
        ret = beta * mkt.to_numpy() + rng.normal(0, 0.002, len(dates))
        daily.append(pd.DataFrame({"permno": permno, "date": dates, "prc": 10.0, "ret": ret,
                                   "shrout": 1000.0, "cfacpr": 1.0}))
    tables["crsp.dsf"] = pd.concat(daily, ignore_index=True)
    tables["crsp.dsi"] = pd.DataFrame({"date": dates, "sprtrn": mkt.to_numpy(), "vwretd": mkt.to_numpy()})
    tables["crsp.dsedelist"] = pd.DataFrame({"permno": [10001], "dlstdt": pd.to_datetime(["2020-06-01"]),
                                             "dlret": [-0.5], "dlstcd": [500]})
    tables["crsp.stocknames"] = pd.DataFrame([{
        "permno": 10001, "namedt": pd.Timestamp("2010-01-01"), "nameenddt": pd.Timestamp("2099-12-31"),
        "shrcd": 10, "exchcd": 1, "siccd": 3990, "ncusip": "12345610", "ticker": "AAA",
        "comnam": "ALPHA INC", "shrcls": "A", "permco": 9001, "hexcd": 1, "cusip": "12345610",
        "st_date": pd.Timestamp("2010-01-31"), "end_date": pd.Timestamp("2099-12-31"), "namedum": 2.0}])
    tmp = tempfile.TemporaryDirectory()
    panel = write_panel(Path(tmp.name), [{"cik": "1", "t": "2021-03-01"}, {"cik": "2", "t": "2021-03-01"}])
    return FakeConnection(tables), panel, tmp


def fred_files(folder: Path):
    """The six economy files that features_v2 reads, with small made-up numbers."""
    folder.mkdir(parents=True)
    (folder / "realtime").mkdir()
    pd.DataFrame({"date": ["2019:03", "2020:03"], "first_release": [3.8, 4.4],
                  "first_vintage": ["RUC19Q2", "RUC20Q2"], "latest": [3.8, 4.4]}).to_csv(
        folder / "realtime/unemployment_first_release.csv", index=False)
    ip = pd.DataFrame({"DATE": [f"2019:{m:02d}" for m in range(1, 13)] + [f"2020:{m:02d}" for m in range(1, 4)]})
    ip["IPT20M3"] = list(range(100, 112)) + [112, 113, np.nan]
    ip.to_csv(folder / "realtime/indpro_vintages.csv", index=False)
    pd.DataFrame({"Date": ["2019:Q4", "2020:Q1"], "First": [2.1, -4.8]}).to_csv(
        folder / "realtime/gdp_growth_first_second_third.csv", index=False)
    days = pd.date_range("2019-01-01", "2021-03-01")
    for name, value in (("BAA10Y", 2.0), ("T10Y3M", 0.5), ("VIXCLS", 20.0)):
        pd.DataFrame({"observation_date": days.strftime("%Y-%m-%d"), name: value}).to_csv(
            folder / f"{name}.csv", index=False)


class HelperTests(unittest.TestCase):
    """Checks of the small helpers that decide the SQL chunks."""

    def test_permno_chunks_are_sorted_unique_and_bounded(self):
        chunks = fetch_wrds.permno_chunks([5, 3, 3] + list(range(10, 1010)))
        self.assertTrue(all(len(c) <= fetch_wrds.CHUNK_PERMNOS for c in chunks))
        self.assertEqual(sorted(p for c in chunks for p in c), [3, 5] + list(range(10, 1010)))
        self.assertEqual(len(chunks), 3)

    def test_date_windows_cover_the_range_without_gaps(self):
        start, end = pd.Timestamp("2009-05-01"), pd.Timestamp("2021-03-01")
        windows = fetch_wrds.date_windows(start, end)
        self.assertEqual(windows[0][0], start)
        self.assertEqual(windows[-1][1], end)
        self.assertTrue(all((b[0] - a[1]).days == 1 for a, b in zip(windows, windows[1:])))
        self.assertTrue(all(a[1] <= pd.Timestamp(year=a[0].year + fetch_wrds.CHUNK_YEARS, month=1, day=1)
                            for a in windows))

    def test_module_does_not_import_wrds_at_the_top(self):
        self.assertNotIn("wrds", fetch_wrds.__dict__)

    def test_v2_names_use_the_share_code_mapping(self):
        df = pd.DataFrame({
            "permno": [1, 2, 3], "namedt": pd.to_datetime(["2020-01-01"] * 3),
            "nameenddt": pd.to_datetime(["2021-01-01"] * 3), "permco": [10, 10, 10], "cusip": ["a", "b", "c"],
            "hdrcusip": ["A", "B", "C"], "ticker": ["a", "b", "c"], "issuernm": ["A", "B", "C"],
            "primaryexch": ["N", "Q", "A"], "siccd": [1, 2, 3], "shareclass": ["A", "A", "A"],
            "sharetype": ["NS", "NS", "CE"], "securitytype": ["EQTY", "EQTY", "EQTY"],
            "securitysubtype": ["COM", "COM", "COM"], "usincflg": ["Y", "Y", "Y"],
            "issuertype": ["ACOR", "CORP", "CORP"]})
        out = fetch_wrds._names_v2_to_legacy(df)
        self.assertEqual(out.shrcd.tolist(), [10, 11, 0])
        self.assertEqual(out.exchcd.tolist(), [1, 3, 2])
        self.assertEqual(out.ncusip.tolist(), ["a", "b", "c"])
        self.assertEqual(out.cusip.tolist(), ["A", "B", "C"])


class LinkTests(unittest.TestCase):
    """Checks that the link rule is the one in fetch_crsp.py."""

    def test_link_types_primary_links_and_panel_ciks(self):
        fake, panel, tmp = link_case()
        self.addCleanup(tmp.cleanup)
        link = fetch_wrds.fetch_links(fake, str(panel))
        self.assertEqual(set(link.permno), {10001, 10002, 20001})
        self.assertNotIn(30001, set(link.permno))
        self.assertEqual(link.cik.nunique(), 2)
        self.assertIn("linktype IN ('LU', 'LC')", fake.sql_for("crsp.ccmxpf_lnkhist")[0])
        self.assertIn("linkprim IN ('P', 'C')", fake.sql_for("crsp.ccmxpf_lnkhist")[0])

    def test_links_csv_has_the_schema_columns(self):
        fake, panel, tmp = link_case()
        self.addCleanup(tmp.cleanup)
        link = fetch_wrds.fetch_links(fake, str(panel))
        with tempfile.TemporaryDirectory() as d:
            link.to_csv(Path(d) / "crsp_links.csv", index=False)
            self.assertEqual(pd.read_csv(Path(d) / "crsp_links.csv").columns.tolist(),
                             ["gvkey", "cik", "permno", "linkdt", "linkenddt"])


class QueryTests(unittest.TestCase):
    """Checks the SQL scope, the chunks, and the legacy / CIZ split."""

    def test_daily_asks_only_for_linked_permnos_and_needed_dates_in_chunks(self):
        n = fetch_wrds.CHUNK_PERMNOS * 2 + 1
        tables = empty_tables()
        tables["comp.company"] = pd.DataFrame({"gvkey": [f"g{i}" for i in range(n)],
                                               "cik": [str(i) for i in range(n)]})
        tables["crsp.ccmxpf_lnkhist"] = pd.DataFrame({
            "gvkey": [f"g{i}" for i in range(n)], "lpermno": [1000 + i for i in range(n)],
            "linkdt": pd.to_datetime(["2009-01-01"] * n), "linkenddt": pd.to_datetime(["2099-12-31"] * n),
            "linktype": ["LU"] * n, "linkprim": ["P"] * n})
        tables["crsp.dsf"] = pd.DataFrame(columns=["permno", "date", "prc", "ret", "shrout", "cfacpr"])
        tables["crsp.dsf_v2"] = pd.DataFrame(
            columns=["permno", "dlycaldt", "dlyprc", "dlyret", "shrout", "dlycumfacpr"])
        with tempfile.TemporaryDirectory() as d:
            panel = write_panel(Path(d), [{"cik": str(i), "t": "2026-01-01"} for i in range(n)])
            fake = FakeConnection(tables)
            link = fetch_wrds.fetch_links(fake, str(panel))
            permnos = sorted(link.permno)
            fake.calls.clear()
            start, end = pd.Timestamp("2009-01-01"), pd.Timestamp("2027-01-01")
            daily = fetch_wrds.fetch_daily(fake, permnos, start, end)
        daily_calls = [c for c in fake.calls if "crsp.dsf" in c.sql]
        self.assertGreater(len(daily_calls), 3)
        seen = set()
        for call in daily_calls:
            self.assertLessEqual(len(call.params["permnos"]), fetch_wrds.CHUNK_PERMNOS)
            self.assertTrue(set(call.params["permnos"]) <= set(permnos))
            self.assertGreaterEqual(pd.Timestamp(call.params["start"]), start)
            self.assertLessEqual(pd.Timestamp(call.params["end"]), end)
            self.assertLessEqual(pd.Timestamp(call.params["end"]),
                                 pd.Timestamp(year=pd.Timestamp(call.params["start"]).year
                                              + fetch_wrds.CHUNK_YEARS, month=1, day=1))
            seen.update(call.params["permnos"])
        self.assertEqual(seen, set(permnos))
        self.assertTrue(any("crsp.dsf_v2" in c.sql for c in fake.calls))
        self.assertTrue(daily.empty)

    def test_v2_tables_are_used_after_2024_and_keep_their_delisting_semantics(self):
        tables = empty_tables()
        dates = pd.bdate_range("2024-12-02", "2025-05-30")
        tables["crsp.dsf"] = pd.DataFrame({"permno": 10001, "date": dates[dates < "2025-01-01"],
                                           "prc": 10.0, "ret": 0.0, "shrout": 1000.0, "cfacpr": 1.0})
        v2dates = dates[dates >= "2025-01-01"]
        tables["crsp.dsf_v2"] = pd.DataFrame({"permno": 10001, "dlycaldt": v2dates, "dlyprc": 20.0,
                                              "dlyret": 0.01, "shrout": 2000.0, "dlycumfacpr": 2.0})
        tables["crsp.dsi"] = pd.DataFrame({"date": dates[dates < "2025-01-01"], "sprtrn": 0.001, "vwretd": 0.002})
        tables["crsp.wrds_dailyindexret_query"] = pd.DataFrame({"dlycaldt": v2dates, "sprtrn": 0.003,
                                                               "vwretd": 0.004})
        tables["crsp.dsedelist"] = pd.DataFrame(columns=["permno", "dlstdt", "dlret", "dlstcd"])
        tables["crsp.stkdelists"] = pd.DataFrame({"permno": [10001], "delistingdt": pd.to_datetime(["2025-03-03"]),
                                                  "delret": [-0.9]})
        tables["crsp.stocknames"] = pd.DataFrame(columns=fetch_wrds.NAME_COLUMNS)
        tables["crsp.stocknames_v2"] = pd.DataFrame([{
            "permno": 10001, "namedt": pd.Timestamp("2024-01-01"), "nameenddt": pd.Timestamp("2025-12-31"),
            "permco": 9001, "cusip": "11111111", "hdrcusip": "22222222", "ticker": "AAA",
            "issuernm": "ALPHA INC", "primaryexch": "Q", "siccd": 3990, "shareclass": "A",
            "sharetype": "NS", "securitytype": "EQTY", "securitysubtype": "COM", "usincflg": "Y",
            "issuertype": "CORP"}])
        fake = FakeConnection(tables)
        start, end = pd.Timestamp("2024-12-01"), pd.Timestamp("2025-06-01")
        daily = fetch_wrds.fetch_daily(fake, [10001], start, end)
        index = fetch_wrds.fetch_index(fake, start, end)
        delist = fetch_wrds.fetch_delist(fake, [10001], start, end)
        names = fetch_wrds.fetch_names(fake, [10001])
        self.assertEqual(set(daily.permno), {10001})
        self.assertTrue((daily.date >= pd.Timestamp("2024-12-01")).all())
        self.assertEqual(float(daily[daily.date >= "2025-01-01"].shrout.iloc[0]), 2000.0)
        self.assertEqual(float(daily[daily.date >= "2025-01-01"].cfacpr.iloc[0]), 2.0)
        self.assertEqual(len(index), len(dates))
        row = delist[(delist.permno == 10001) & (delist.date == pd.Timestamp("2025-03-03"))].iloc[0]
        self.assertEqual(row.dlret, 0.0)
        self.assertTrue(pd.isna(row.dlstcd))
        self.assertEqual(names.iloc[0].shrcd, 11)
        self.assertEqual(names.iloc[0].exchcd, 3)
        self.assertTrue(any("crsp.dsf_v2" in c.sql for c in fake.calls))
        self.assertTrue(any("crsp.wrds_dailyindexret_query" in c.sql for c in fake.calls))
        self.assertTrue(any("crsp.stkdelists" in c.sql for c in fake.calls))
        self.assertTrue(any("crsp.stocknames_v2" in c.sql for c in fake.calls))
        self.assertFalse(any(30001 in c.params.get("permnos", ()) for c in fake.calls if c.params))


class WrittenFilesTests(unittest.TestCase):
    """End to end with the fake: write the folder, check its types, and read it with the next two steps."""

    def test_main_writes_the_same_folder_and_market_features_and_features_v2_read_it(self):
        fake, panel, tmp = market_case()
        self.addCleanup(tmp.cleanup)
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "crsp"
            with mock.patch.object(fetch_wrds, "connect", return_value=fake), \
                    mock.patch.object(sys, "argv", ["fetch_wrds", str(panel), str(out), "--from-year", "2019"]):
                fetch_wrds.main()

            self.assertEqual(pd.read_csv(out / "crsp_links.csv").columns.tolist(),
                             ["gvkey", "cik", "permno", "linkdt", "linkenddt"])
            self.assertEqual(pd.read_csv(out / "crsp_sp500.csv").columns.tolist(), ["date", "sprtrn"])
            self.assertEqual(pd.read_csv(out / "crsp_vwretd.csv").columns.tolist(), ["date", "vwretd"])
            self.assertEqual(pd.read_csv(out / "crsp_delist.csv").columns.tolist(),
                             ["permno", "date", "dlret", "dlstcd"])
            self.assertEqual([(f.name, str(f.type)) for f in pq.read_schema(out / "crsp_daily.parquet")],
                             DAILY_SCHEMA)
            self.assertEqual([(f.name, str(f.type)) for f in
                              pq.read_schema(out / "wrds_crsp_stocknames.parquet")], NAME_SCHEMA)

            daily = pd.read_parquet(out / "crsp_daily.parquet")
            self.assertEqual(set(daily.permno), {10001, 20001})
            self.assertTrue(daily.date.min() >= pd.Timestamp("2019-01-01"))
            self.assertTrue(daily.date.max() <= pd.Timestamp("2022-03-01"))
            delist = pd.read_csv(out / "crsp_delist.csv")
            self.assertEqual(delist[["permno", "dlret", "dlstcd"]].iloc[0].tolist(), [10001, -0.5, 500])

            from tcf_credit import features_v2, market_features
            mpanel = Path(d) / "panel_market.csv"
            with mock.patch.object(sys, "argv", ["market_features", str(panel), str(out), str(mpanel)]):
                market_features.main()
            m = pd.read_csv(mpanel)
            self.assertEqual(int(m.has_prices.sum()), 2)
            self.assertEqual(set(m.permno.dropna().astype(int)), {10001, 20001})
            self.assertTrue(set(EMPTY).issubset(m.columns))

            fred = Path(d) / "fred"
            fred_files(fred)
            v2 = Path(d) / "panel_v2.csv"
            with mock.patch.object(sys, "argv", ["features_v2", str(mpanel), str(out), str(fred), str(v2)]):
                features_v2.main()
            out_v2 = pd.read_csv(v2)
            self.assertTrue(set(V2_COLUMNS).issubset(out_v2.columns))
            self.assertTrue(out_v2.beta_12m.notna().all())


if __name__ == "__main__":
    unittest.main()
