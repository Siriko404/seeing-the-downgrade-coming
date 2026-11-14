"""Write small test inputs for the credit-downgrade model. Test-only helper; students do not use it.

What this file is
-----------------
The model's real input is a panel built from public SEC filings and rating files plus licensed CRSP stock data, which
cannot be shared. The tests need a table with the same column names (except the licensed stock identifier permno),
the same column types and a similar shape, so that the model code can be exercised. This helper writes such a table
from random draws with company names "Example Co 001", "Example Co 002", ...; the company numbers (CIK) are counted
up from 9,000,001 and the report numbers (accession numbers) are built from the CIK, the year and a counter. Every
value is a test input: a result on this table says nothing about real companies. Nothing outside `model/tests/` may
import this file.

How to run it
-------------
From the folder that holds `model/`:

    python model/tests/support/panel_for_tests.py              # writes model/tests/support/out/small_test_panel.csv
    python model/tests/support/panel_for_tests.py --out my_panel.csv.gz --firms 800 --seed 7

Options: --firms (default 400), --first-year and --last-year (fiscal years, default 2009 and 2025), --seed (default 1),
--target-rate (share of rows with a downgrade, default 0.12), --coverage-end, --out. The same seed always gives the
same file, byte for byte. In Python:

    from support.panel_for_tests import make_panel
    panel = make_panel(n_firms=400, seed=1)      # a pandas DataFrame

How the test inputs are built
-----------------------------
1. Each company gets a fixed "quality" number, and each year a "shock" that fades slowly (an AR(1) series, meaning
   this year's shock is 0.6 times last year's plus new noise). Quality, shock and the economy together give a
   "health" number for every report.
2. The ratios (debt/assets, EBIT/assets, ...) and the stock-market inputs are drawn from health
   plus noise. Debt, assets and the other money amounts are drawn first and the ratios are computed from them, so the
   columns agree with each other (for example debt_assets is debt divided by assets). The rating follows quality and
   LAST year's shock, so it lags the financial ratios, as real ratings tend to. The outlook and watch flags are drawn
   from this year's shock (the watch through the outlook).
3. The economy (unemployment, bond spread, ...) is one shared monthly series, looked up at the filing date.
4. The label (1 = S&P downgrades the company within 12 months of the report, 0 = it does not) is drawn from a simple
   rule. With z(x) = (x - typical value) / typical spread, the log-odds of a downgrade are
       intercept
       + 0.9 * z(debt_assets) - 0.9 * z(ebit_assets) + 0.35 * z(notch)
       + 1.1 * outlook_neg + 1.4 * watch_neg + 0.6 * dg_prev_year
       + 0.3 * z(vol_12m) - 0.3 * z(ret_12m) + 0.4 * z(baa10y)
       + noise (normal, spread 0.8)
   Missing inputs count as typical. The intercept is searched so that about --target-rate of the rows end up with
   label 1. The noise keeps the task hard: no model can get it right every time. The rule is the same for every
   year, so a model trained on early years works on later ones; in real data that is not guaranteed.
5. As in the real panel, a report is dropped when its 12-month label window is not finished by --coverage-end
   (default 2025-12-05), so the last years hold few or no rows. Some ratios are left empty at random, and a company's
   first reports have empty "change since last report" columns. About 12% of rows have no stock-market inputs
   (has_prices = 0).

Differences from the real panel
-------------------------------
- The licensed stock-database identifier column of the real panel is left out. evaluate.py and the notebooks never
  read it (features_v2.py and returns.py do, but they are not run on this table).
- notch runs from 1 (AAA) to 21 (C); the real panel also leaves out rows already in default (notch 22).
- Company numbers (CIK) start at 9,000,001; this range is meant to stay clear of real company numbers (not checked
  against EDGAR).
"""
import argparse
import gzip
from pathlib import Path

import numpy as np
import pandas as pd

# ---- fixed tables -------------------------------------------------------------------------------------------------
RATINGS = "AAA AA+ AA AA- A+ A A- BBB+ BBB BBB- BB+ BB BB- B+ B B- CCC+ CCC CCC- CC C".split()   # notch 1..21
# Same sector boundaries as the real panel (build_panel.sector); a test checks the two agree.
SECTOR_BOUNDS = [(100, 999, "agriculture"), (1000, 1499, "mining_energy"), (1500, 1799, "construction"),
                 (2000, 2999, "manufacturing_nondurable"), (3000, 3999, "manufacturing_durable"),
                 (4000, 4899, "transport_telecom"), (5000, 5199, "wholesale"), (5200, 5999, "retail"),
                 (7000, 8999, "services")]
# Industry codes (SIC) of non-financial, non-utility companies, with how often each is drawn.
SIC_CHOICES = [(100, 1), (1040, 2), (1311, 4), (1600, 2), (2000, 3), (2834, 5), (2911, 2), (3312, 2), (3571, 3),
               (3674, 5), (3711, 3), (3841, 3), (4011, 2), (4813, 3), (4953, 1), (5000, 2), (5140, 2), (5311, 3),
               (5812, 3), (7372, 6), (7370, 3), (8062, 2)]
FISCAL_MONTHS = [(12, 0.62), (6, 0.10), (9, 0.10), (3, 0.08), (1, 0.05), (10, 0.05)]
DEBT_SRC = ["LongTermDebt", "LongTermDebtAndCapitalLeaseObligations", "DebtInstrumentCarryingAmount",
            "LongTermDebtNoncurrent+current"]
INTEREST_SRC = ["InterestExpense", "InterestExpenseNonoperating", "InterestExpenseDebt", "InterestPaidNet"]
# The columns of the real panel, in order, without its licensed stock-database identifier.
COLUMNS = ["cik", "obligor", "sp_name", "accn", "t", "period_end", "fy_end_year", "sic", "sector", "label", "rating",
           "notch", "ig", "outlook_neg", "outlook_pos", "watch_neg", "watch_pos", "dg_prev_year", "up_prev_year",
           "years_rated", "days_since_action", "assets", "debt", "debt_src", "debt_assets", "ebit_assets", "wc_assets",
           "ebit_interest", "interest_src", "cfo_debt", "log_assets", "re_assets", "cash_assets", "op_margin",
           "dividend_payer", "float_debt", "debt_ebitda", "shares", "debt_current", "has_prices", "ret_12m", "ret_6m",
           "vol_12m", "mcap_debt", "dd_naive", "neg_ebitda", "chg_debt_assets", "chg_ebit_assets", "chg_ebit_interest",
           "chg_cfo_debt", "chg_cash_assets", "chg_op_margin", "chg_debt_ebitda", "vol_ebit_assets_3y", "beta_12m",
           "idio_vol_12m", "unemp", "unemp_chg_12m", "ip_growth_12m", "gdp_growth", "baa10y", "t10y3m", "vix_20d"]
CHG = ["debt_assets", "ebit_assets", "ebit_interest", "cfo_debt", "cash_assets", "op_margin", "debt_ebitda"]
INT_COLUMNS = ["cik", "fy_end_year", "sic", "label", "notch", "ig", "outlook_neg", "outlook_pos", "watch_neg",
               "watch_pos", "dg_prev_year", "up_prev_year", "days_since_action", "dividend_payer", "has_prices"]
STR_COLUMNS = ["obligor", "sp_name", "accn", "t", "period_end", "sector", "rating", "debt_src", "interest_src"]
# Share of rows left empty at random, per column (the real filings miss items too).
MISSING = {"wc_assets": 0.04, "ebit_interest": 0.06, "cfo_debt": 0.05, "re_assets": 0.03, "cash_assets": 0.03,
           "op_margin": 0.03, "float_debt": 0.08, "debt_ebitda": 0.05}
HAS_PRICES_SHARE = 0.88

# The rule for the label in these test inputs. Each term is (column, typical value, typical spread, weight) or (column, weight)
# for 0/1 columns. Documented in the module docstring.
LABEL_TERMS = [("debt_assets", 0.33, 0.15, 0.9), ("ebit_assets", 0.07, 0.05, -0.9), ("notch", 12.5, 3.4, 0.35),
               ("vol_12m", 0.30, 0.10, 0.3), ("ret_12m", 0.0, 0.25, -0.3), ("baa10y", 2.2, 0.7, 0.4)]
LABEL_FLAGS = [("outlook_neg", 1.1), ("watch_neg", 1.4), ("dg_prev_year", 0.6)]
LABEL_NOISE_SD = 0.8


def sigmoid(x):
    """The logistic function: turns a score into a probability between 0 and 1."""
    return 1.0 / (1.0 + np.exp(-x))


def sector_of(sic):
    """The sector name for an industry code (SIC), from SECTOR_BOUNDS; "other" if no range fits."""
    for lo, hi, name in SECTOR_BOUNDS:
        if lo <= sic <= hi:
            return name
    return "other"


def make_economy(rng, first_year, last_year):
    """One shared monthly economy. A slow 'cycle' number (high = bad times) drives all seven series."""
    months = pd.period_range(f"{first_year - 3}-01", f"{last_year + 3}-12", freq="M")
    n = len(months)
    cycle = np.zeros(n)
    for i in range(1, n):
        cycle[i] = 0.97 * cycle[i - 1] + rng.normal(0, 0.22)

    def ar(sd, rho=0.8):
        """A series of length n that depends on its previous value (weight `rho`) plus random noise."""
        x = np.zeros(n)
        for i in range(1, n):
            x[i] = rho * x[i - 1] + rng.normal(0, sd)
        return x

    unemp = np.clip(5.5 + 1.3 * cycle + ar(0.12), 3.0, 11.0)
    eco = pd.DataFrame({
        "unemp": unemp,
        "ip_growth_12m": np.clip(0.02 - 0.03 * cycle + ar(0.004), -0.15, 0.12),
        "gdp_growth": np.clip(2.5 - 2.0 * cycle + ar(0.5), -8.0, 8.0),
        "baa10y": np.clip(2.2 + 0.7 * cycle + ar(0.06), 1.2, 5.0),
        "t10y3m": np.clip(1.5 - 0.6 * cycle + ar(0.12), -1.0, 3.5),
        "vix_20d": np.clip(18 + 5.0 * cycle + ar(1.0), 10.0, 60.0),
        "cycle": cycle,
    }, index=months)
    eco["unemp_chg_12m"] = eco["unemp"] - eco["unemp"].shift(12)
    return eco


def month_end(year, month):
    """The last day of the given month, for columns of years and months."""
    return pd.to_datetime(pd.DataFrame({"year": year, "month": month, "day": 1})) + pd.offsets.MonthEnd(0)


def solve_intercept(base, target_rate):
    """Find the intercept b so that the mean of sigmoid(base + b) equals target_rate (bisection)."""
    lo, hi = -15.0, 15.0
    for _ in range(60):
        mid = (lo + hi) / 2
        if sigmoid(base + mid).mean() < target_rate:
            lo = mid
        else:
            hi = mid
    return round((lo + hi) / 2, 4)


def make_panel(n_firms=400, first_year=2009, last_year=2025, seed=1, target_rate=0.12, coverage_end="2025-12-05"):
    """Return the test panel as a DataFrame (columns in COLUMNS order). See the module docstring."""
    rng = np.random.default_rng(seed)
    eco = make_economy(rng, first_year, last_year)
    years = np.arange(first_year, last_year + 1)
    n_years = len(years)
    n = n_firms

    # ---- one record per company ---------------------------------------------------------------------------------
    width = max(3, len(str(n)))
    cik = 9_000_000 + np.arange(1, n + 1)
    names = [f"Example Co {i:0{width}d}" for i in range(1, n + 1)]
    sic_values, sic_w = zip(*SIC_CHOICES)
    sic = rng.choice(sic_values, n, p=np.array(sic_w) / sum(sic_w))
    fm_values, fm_w = zip(*FISCAL_MONTHS)
    fiscal_month = rng.choice(fm_values, n, p=np.array(fm_w) / sum(fm_w))
    quality = rng.normal(0, 1, n)
    leverage_gap = rng.normal(0, 0.08, n)
    log_assets0 = np.clip(22.3 + 1.3 * rng.normal(0, 1, n) + 0.3 * quality, 18.6, 25.0)
    turnover0 = rng.normal(-0.2, 0.5, n)
    rating_gap = rng.normal(0, 0.8, n)
    filing_lag0 = rng.integers(35, 71, n)
    first_event_back = rng.integers(1500, 6000, n)           # days before Jan 1 of first_year the first rating was set
    start_fy = np.where(rng.random(n) < 0.8, first_year, rng.integers(first_year, min(first_year + 6, last_year) + 1, n))
    end_fy = np.where(rng.random(n) < 0.85, last_year, [rng.integers(s + 3, last_year + 1) if s + 3 <= last_year else last_year
                                                        for s in start_fy])

    # ---- shocks on a (company x year) grid ------------------------------------------------------------------
    shock = np.zeros((n, n_years))
    shock[:, 0] = rng.normal(0, 0.7, n)
    for j in range(1, n_years):
        shock[:, j] = 0.6 * shock[:, j - 1] + rng.normal(0, 0.5, n)
    lagged = np.concatenate([shock[:, :1], shock[:, :-1]], axis=1)
    notch_float = 12.5 - 3.3 * quality[:, None] - 1.2 * lagged + rating_gap[:, None]
    notch_grid = np.clip(np.rint(notch_float), 1, 21).astype(int)
    prev_notch = np.concatenate([notch_grid[:, :1], notch_grid[:, :-1]], axis=1)
    active = (years[None, :] >= start_fy[:, None]) & (years[None, :] <= end_fy[:, None])
    has_prev = np.concatenate([np.zeros((n, 1), bool), active[:, 1:] & active[:, :-1]], axis=1)

    fi, yi = np.nonzero(active)                                # row -> company index, year index
    m = len(fi)
    fy = years[yi]
    df = pd.DataFrame({"cik": cik[fi], "obligor": np.array(names)[fi], "fy_end_year": fy})
    df["sp_name"] = df["obligor"] + " Inc"
    df["sic"] = sic[fi]
    df["sector"] = [sector_of(int(s)) for s in df["sic"]]

    # ---- dates ----------------------------------------------------------------------------------------------
    pe = month_end(fy, fiscal_month[fi])
    lag = filing_lag0[fi] + rng.integers(0, 9, m)
    t = pe + pd.to_timedelta(lag + 1, unit="D")                 # filing date + 1 day, as in the real panel
    df["period_end"] = pe.dt.strftime("%Y-%m-%d")
    df["t"] = t.dt.strftime("%Y-%m-%d")
    seq = pd.Series(np.arange(m)).groupby(t.dt.year.to_numpy()).cumcount().to_numpy() + 1
    df["accn"] = [f"{c:010d}-{y % 100:02d}-{s:06d}" for c, y, s in zip(df["cik"], t.dt.year, seq)]
    e = eco.reindex(pd.PeriodIndex(t.dt.to_period("M")))
    e.index = df.index
    cyc = e["cycle"].to_numpy()

    # ---- health and the S&P rating state ------------------------------------------------------------------------
    s_now = shock[fi, yi]
    health = 0.8 * quality[fi] + 0.8 * s_now - 0.25 * cyc
    notch = notch_grid[fi, yi]
    df["notch"] = notch
    df["rating"] = np.array(RATINGS)[notch - 1]
    df["ig"] = (notch <= 10).astype(int)
    hp = has_prev[fi, yi]
    df["dg_prev_year"] = (hp & (notch > prev_notch[fi, yi])).astype(int)
    df["up_prev_year"] = (hp & (notch < prev_notch[fi, yi])).astype(int)
    outlook_neg = rng.random(m) < sigmoid(-2.2 - 1.0 * s_now)
    outlook_pos = (rng.random(m) < sigmoid(-2.6 + 0.9 * s_now)) & ~outlook_neg
    watch_neg = rng.random(m) < 0.01 + 0.10 * outlook_neg
    watch_pos = (rng.random(m) < 0.01 + 0.05 * outlook_pos) & ~watch_neg
    df["outlook_neg"], df["outlook_pos"] = outlook_neg.astype(int), outlook_pos.astype(int)
    df["watch_neg"], df["watch_pos"] = watch_neg.astype(int), watch_pos.astype(int)
    changed = (df["dg_prev_year"] + df["up_prev_year"]).to_numpy() > 0
    df["days_since_action"] = np.where(changed, rng.integers(30, 331, m), rng.integers(200, 1501, m))
    first_event = pd.Timestamp(f"{first_year}-01-01") - pd.to_timedelta(first_event_back[fi], unit="D")
    df["years_rated"] = ((t - first_event).dt.days / 365.25).round(2)

    # ---- 10-K amounts and ratios (amounts first, ratios computed from them)
    # ---------------------------------------------
    log_a = log_assets0[fi] + 0.04 * (fy - first_year) + rng.normal(0, 0.06, m)
    assets = np.rint(np.exp(log_a))
    debt_assets_true = np.clip(0.33 - 0.09 * health + leverage_gap[fi] + rng.normal(0, 0.07, m), 0.02, 1.2)
    debt = np.maximum(np.rint(debt_assets_true * assets), 1.0)
    ebit = np.rint(np.clip(0.07 + 0.035 * health + rng.normal(0, 0.025, m), -0.25, 0.30) * assets)
    revenue = np.maximum(assets * np.exp(turnover0[fi] + rng.normal(0, 0.1, m)), 1.0)
    da = assets * rng.uniform(0.02, 0.06, m)
    ebitda = ebit + da
    interest = debt * rng.uniform(0.03, 0.08, m)
    cfo = 0.75 * ebitda + rng.normal(0, 0.01, m) * assets
    wc = np.clip(0.10 + 0.03 * health + rng.normal(0, 0.08, m), -0.4, 0.6) * assets
    re = np.clip(0.12 + 0.12 * health + rng.normal(0, 0.2, m), -1.5, 0.8) * assets
    cash = np.clip(np.exp(rng.normal(-2.6 + 0.2 * health, 0.6, m)), 0.003, 0.5) * assets
    mcap = assets * np.exp(rng.normal(-0.4 + 0.45 * health, 0.5, m))      # market value of the shares
    debt_current = np.rint(debt * rng.uniform(0.02, 0.25, m))
    df["assets"], df["debt"], df["debt_current"] = assets, debt, debt_current
    df["debt_src"] = rng.choice(DEBT_SRC, m, p=[0.5, 0.25, 0.1, 0.15])
    df["interest_src"] = rng.choice(INTEREST_SRC, m, p=[0.6, 0.2, 0.1, 0.1])
    df["debt_assets"] = debt / assets
    df["ebit_assets"] = ebit / assets
    df["wc_assets"] = wc / assets
    df["ebit_interest"] = np.clip(ebit / interest, -30, 80)
    df["cfo_debt"] = np.clip(cfo / debt, -1, 3)
    df["log_assets"] = np.log(assets)
    df["re_assets"] = re / assets
    df["cash_assets"] = cash / assets
    df["op_margin"] = np.clip(ebit / revenue, -2, 0.6)
    df["dividend_payer"] = (rng.random(m) < sigmoid(-0.5 + 0.8 * health + 0.3 * (log_a - 22.3))).astype(int)
    df["float_debt"] = 0.8 * mcap * np.exp(rng.normal(0, 0.15, m)) / debt
    neg = ebitda < 0
    # debt_ebitda is zeroed when EBITDA < 0.
    df["debt_ebitda"] = np.where(neg, 0.0, np.clip(debt / np.where(neg, 1.0, ebitda), 0, 100))
    df["neg_ebitda"] = neg.astype(float)
    df["shares"] = np.rint(mcap / np.exp(rng.normal(3.2, 0.8, m)))

    # ---- stock-market inputs (empty when the stock has no price history)
    # --------------------------------------------------
    vol = np.clip(np.exp(rng.normal(np.log(0.30) - 0.2 * health + 0.1 * cyc, 0.25, m)), 0.08, 1.5)
    ret12 = np.clip(0.06 * health + rng.normal(0, 0.25, m), -0.8, 1.5)
    ret6 = np.clip(0.5 * ret12 + rng.normal(0, 0.15, m), -0.8, 1.2)
    fv = debt_current + 0.5 * np.maximum(debt - debt_current, 0.0)       # same formula as market_features.row_features
    v = mcap + fv
    sigma_v = mcap / v * vol + fv / v * (0.05 + 0.25 * vol)
    dd = np.clip((np.log(v / fv) + (ret12 + 0.08 - sigma_v ** 2 / 2)) / sigma_v, -10, 30)
    has_prices = rng.random(m) < HAS_PRICES_SHARE
    market = {"ret_12m": ret12, "ret_6m": ret6, "vol_12m": vol, "mcap_debt": mcap / debt, "dd_naive": dd,
              "beta_12m": np.clip(rng.normal(1.0 - 0.1 * health, 0.35, m), 0.1, 2.5),
              "idio_vol_12m": vol * rng.uniform(0.6, 0.95, m)}
    df["has_prices"] = has_prices.astype(int)
    for k, x in market.items():
        df[k] = np.where(has_prices, x, np.nan)

    # ---- the economy at the filing date --------------------------------------------------------------------------
    for k in ["unemp", "unemp_chg_12m", "ip_growth_12m", "gdp_growth", "baa10y", "t10y3m", "vix_20d"]:
        df[k] = e[k].to_numpy()

    # ---- censoring, then random gaps, then changes between reports --------------------------------------------------
    keep = (t + pd.Timedelta(days=365)) <= pd.Timestamp(coverage_end)          # label window finished
    df = df[keep.to_numpy()].copy()
    for col, share in MISSING.items():
        hole = rng.random(len(df)) < share
        if col == "debt_ebitda":
            hole &= df["neg_ebitda"].to_numpy() == 0           # a zeroed (negative-EBITDA) value is never empty
        df.loc[hole, col] = np.nan
    df["neg_ebitda"] = df["neg_ebitda"].where(df["debt_ebitda"].notna() | (df["neg_ebitda"] == 1), np.nan)
    df = df.sort_values(["cik", "t"]).reset_index(drop=True)
    g = df.groupby("cik")
    consecutive = (g["fy_end_year"].diff() == 1).to_numpy()
    for c in CHG:
        df[f"chg_{c}"] = (df[c] - g[c].shift(1)).where(consecutive)
    three = g["ebit_assets"].transform(lambda s: s.rolling(3).std())
    ok3 = consecutive & pd.Series(consecutive).groupby(df["cik"]).shift(1, fill_value=False).to_numpy()
    df["vol_ebit_assets_3y"] = three.where(ok3)

    # ---- the label
    # --------------------------------------------------------------------------------------------------------
    base = np.zeros(len(df))
    for col, centre, spread, weight in LABEL_TERMS:
        base += weight * ((df[col] - centre) / spread).fillna(0.0).to_numpy()
    for col, weight in LABEL_FLAGS:
        base += weight * df[col].to_numpy()
    base += rng.normal(0, LABEL_NOISE_SD, len(df))
    b0 = solve_intercept(base, target_rate)
    df["label"] = (rng.random(len(df)) < sigmoid(base + b0)).astype(int)

    # ---- types and rounding
    # --------------------------------------------------------------------------------------------------
    out = df[COLUMNS].copy()
    for c in COLUMNS:
        if c in INT_COLUMNS:
            out[c] = out[c].astype("int64")
        elif c in STR_COLUMNS:
            out[c] = out[c].astype(str)
        else:
            out[c] = out[c].astype("float64").round(6)
    return out


def write_csv(df, path):
    """Write the panel as CSV (gzip if the name ends in .gz). The gzip header carries no clock time, so the same
    panel always gives the same bytes."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = df.to_csv(index=False, lineterminator="\n").encode("utf-8")
    if path.suffix == ".gz":
        data = gzip.compress(data, compresslevel=6, mtime=0)
    path.write_bytes(data)


def main():
    """Read the command-line options, make the test panel and write it to a file."""
    here = Path(__file__).resolve().parent
    p = argparse.ArgumentParser(description="Write a small test panel for the credit model (test-only helper).")
    p.add_argument("--out", default=str(here / "out" / "small_test_panel.csv"), help="output file (.csv or .csv.gz)")
    p.add_argument("--firms", type=int, default=400, help="number of test companies (default 400)")
    p.add_argument("--first-year", type=int, default=2009, help="first fiscal year (default 2009)")
    p.add_argument("--last-year", type=int, default=2025, help="last fiscal year (default 2025)")
    p.add_argument("--seed", type=int, default=1, help="random seed (default 1)")
    p.add_argument("--target-rate", type=float, default=0.12, help="share of rows with label 1 (default 0.12)")
    p.add_argument("--coverage-end", default="2025-12-05", help="reports whose 12-month window ends later are dropped")
    a = p.parse_args()
    panel = make_panel(a.firms, a.first_year, a.last_year, a.seed, a.target_rate, a.coverage_end)
    write_csv(panel, a.out)
    print(f"wrote {len(panel)} rows, {panel.cik.nunique()} companies, label share {panel.label.mean():.3f} to {a.out}")


if __name__ == "__main__":
    main()
