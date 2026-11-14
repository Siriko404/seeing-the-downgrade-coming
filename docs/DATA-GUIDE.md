# Data guide

This guide lists every input the model uses, where it comes from, whether it is public or licensed, which program
fetches or reads it, and what you must do to use it fairly.

## No licensed data and no model scores are included

This package contains **no licensed data and no model scores**, and no data files for the model: no ratings table, no
prices, no economic series. The agent's offline demo keeps saved rating passages from public SEC filings in
`agent/skills/credit-watch/cache/`. A rating passage is a paragraph or table that mentions ratings, not a whole filing.
There are passages for HON, RY and CMP; the file for SJ holds only a firm name and no text. The agent's tests keep small
saved runs built from public filings.
The lecture's numbers use licensed stock prices from CRSP, through WRDS. To match each company to its CRSP stock, the
code uses two identifier tables available through WRDS: the Compustat company file (only its gvkey and CIK columns) and
the CRSP/Compustat Merged link table. No Compustat financial data is used: all accounting numbers come from the SEC
filings as first filed. The public sources below are free, but each has terms of use. You download them yourself.

**Because of that, the lecture's numbers cannot be reproduced exactly from free data.** One possible difference is
survivorship bias: free price histories tend to leave out companies that stopped trading (bankrupt, bought, delisted),
and some of these may be companies that were downgraded. The run of the public route on 13 November 2026 shows it:
the model was tested on 4,902 annual reports with 515 downgrades (10.5%), against 6,380 with 862 (13.5%) in the
lecture, and the logit scored ROC-AUC 0.759 against 0.802.

## Three ways to study

1. **Example data (anyone).** `model/synthetic/make_panel.py` writes a made-up table with the real column names. The
   test step (`evaluate.py`) and the four model notebooks run on it; the download and licensed-data steps do not. The
   numbers mean nothing.
2. **Public data (anyone, more work).** SEC company facts, the agencies' public rating histories, FRED and Philadelphia
   Fed economy files, the Loughran-McDonald 10-K header file (and, for the side test, their 10-X summaries file of word
   counts) and free Yahoo prices in place of CRSP. Results will differ from the lecture. One command runs it
   (`python -m tcf_credit.rebuild DATA OUT --route free`); it was run from start to end on 13 November 2026, in about
   30 minutes on an 8-core cloud machine. The rating-history ZIP files and the Loughran-McDonald files were the
   lecture's hand-downloaded copies, and the 1993-2025 header file that the package names has not been run.
   `fetch_public.py` fetches the free inputs and `philly_fed.py` converts the
   Philadelphia Fed economy files (see the steps below).
3. **Licensed data (if your library gives you WRDS).** The lecture's route. See the last section.

## The inputs, in groups

The main model uses **four groups** of inputs: 10-K ratios, the S&P rating state, market inputs and the economy. A fifth
group, text tone from word lists, is used only in a side test.

All code is in `model/src/tcf_credit/`. The model's unit is one row per company per 10-K. The snapshot date *t* is the
day after the 10-K was filed, and only information public on *t* may be used (see "look-ahead bias" in the
[glossary](GLOSSARY.md)).

| Group | What it holds | Source | Public or licensed |
|---|---|---|---|
| 1. 10-K ratios | debt to assets, EBIT to assets, interest coverage, cash flow to debt, cash to assets, margin, size, changes since the last report, and more | SEC company facts | Public |
| 2. S&P rating state | notch, investment grade, outlook, watch, recent downgrade or upgrade; and the label (the panel also keeps the rating itself, years rated and days since last action, which the model does not use) | The agencies' public 17g-7 histories | Public |
| 3. Market inputs | 12-month and 6-month return beyond the market, volatility, market value to debt, distance to default, beta | CRSP in the lecture; free Yahoo prices as a stand-in | Licensed (CRSP) or public (Yahoo) |
| 4. The economy | unemployment, industrial production, GDP growth, bond spread, yield-curve slope, VIX | FRED and the Philadelphia Fed Real-Time Data Set | Public |
| Side test: text tone (not in the main model) | change in the share of negative and uncertain words in the 10-K | Loughran-McDonald word lists | Public |

The exact column names are in notebook 01 (`model/notebooks/01_data_and_inputs.ipynb`).

### 1. 10-K ratios, from SEC company facts

- **Where.** The SEC publishes the numbers in each company's filings in a standard computer-readable form (XBRL),
  collected as "company facts" on EDGAR. Values are taken as first filed in that 10-K, not as later restated.
- **Code.** `fetch_sec_bulk.py --tickers-only` downloads the SEC's ticker list, the only SEC bulk file the pipeline
  needs (without the option it also downloads the bulk company facts and filing lists, about 2 GB).
  `fetch_companyfacts.py` fetches the facts of chosen companies and keeps the tags listed in its TAGS table (the model
  reads all of them except four). `build_panel.py` builds the table (the panel) from them.
- **Terms.** The SEC asks every program to declare a contact (your name and e-mail address) in its requests, and allows
  at most 10 requests per second. `sec_http.py` waits 0.15 seconds between requests and reads your contact from the
  environment variable `TCF_SEC_CONTACT`, or from `[sec] contact` in a settings file under your home folder. Use your
  own contact. Never save it in a file you publish.

### 2. S&P rating state, from the agencies' public 17g-7 histories

- **Where.** SEC Rule 17g-7 makes each rating agency post its rating actions as computer-readable files on its own
  website (ZIP archives of XBRL files). The model uses S&P's long-term issuer credit rating in foreign currency. The
  label comes from the same history: it is 1 if a downgrade occurs in the 365 days after *t* (a downgrade to default
  counts as a downgrade: the SEC's code DG includes classifying the company as in default), and 0 if none does. A report
  is dropped if the rating is withdrawn (code WD, WE or WO) before any downgrade, or if the 12 months are not fully
  observed.
- **Code.** `ratings_parser.py` reads the ZIP archives and writes one table of company-level rating events. It skips
  instrument-level events (single bonds) and writes no column of bond identifiers, because those are licensed.
  `link_obligors.py` links S&P's rated companies to SEC filers (by CIK) through the matching of their names. It needs
  the Loughran-McDonald 10-K header file, reduced by `lm_headers.py`.
- **Terms.** Download the archives yourself from each agency's site. Their reuse terms were not checked here, so read
  them. Do not publish the files.
- **Care.** Name matching is imperfect. A name that fits more than one CIK is left unlinked, which drops some companies.

### 3. Market inputs, from CRSP or free Yahoo prices

- **Where.** In the lecture: CRSP daily prices and returns (licensed). Free stand-in: Yahoo's daily price history.
- **Code.** `fetch_yahoo.py` downloads daily prices, one request per ticker, by default one per second.
  `yahoo_market.py` writes them in the same folder layout the CRSP route uses. The SPY exchange-traded fund stands in
  for the S&P 500 and for the value-weighted market return. Shares outstanding come from the latest 10-K cover page and
  are held constant, so market value is approximate. `market_features.py` then builds the inputs from the folder:
  returns beyond the market, volatility, market value to debt, and a distance-to-default measure. `features_v2.py` adds
  beta and idiosyncratic volatility.
- **Terms.** Yahoo's service is not guaranteed and its data come with Yahoo's terms of use. Read them, keep the polite
  pace, download for your own study only, and do not redistribute. A row gets market inputs only if the stock has at
  least 253 trading days of history before *t*.
- **Care.** This is where survivorship bias enters (see above). Prices of stocks that were delisted are often missing.

### 4. The economy, from FRED and the Philadelphia Fed

- **Where.** FRED (the St. Louis Fed's free database) for the daily series (corporate bond spread over the 10-year
  Treasury, yield-curve slope, VIX). Unemployment and GDP growth are used **as first released**; industrial production
  growth is computed inside the latest monthly vintage published before *t*. All three come from the Philadelphia Fed's
  Real-Time Data Set, so that later revisions do not leak in. Its spreadsheets are converted to CSV files by
  `philly_fed.py`.
- **Code.** `fetch_public.py` downloads the FRED series and the Philadelphia Fed spreadsheets. On 13 November 2026
  FRED did not answer its automatic requests while the same links opened in a browser; when that happens it prints
  each link and where to save the file. `philly_fed.py` converts the spreadsheets. `features_v2.py` reads a folder of these files and picks the latest figure that was public by *t*.
  Its module description explains the date rules.
- **Terms.** Free to download. Some series have another owner (VIX belongs to Cboe), and FRED shows a notice on each
  series page. Read it. Do not redistribute.

### Side test: Loughran-McDonald word lists, for the text test

- **Where.** The Loughran-McDonald 10-X summaries file (word counts per filing) from the Notre Dame Software Repository
  for Accounting and Finance (sraf.nd.edu). It counts, for each filing, how many words are on the negative and uncertain
  lists.
- **Code.** `lm_tone.py` adds the *change* since the previous report in the shares of negative and uncertain words
  (`lm_neg_chg`, `lm_unc_chg`). `evaluate.py` uses them only with `--text`, so they are not part of the main model.
- **Terms.** Download from the site yourself and read its terms of use.
- **Care.** The current dictionary was made from older filings and revised later, so there is a small look-ahead in the
  word lists themselves.

## What you must do, in short

- Fetch or download every file yourself.
- Do not put any downloaded file, or any table made from it, into a public place.
- Give the SEC your own contact in every program that calls it.
- Keep the request pace the code sets.
- Read each source's terms before you use it for anything beyond your own study.

## The steps of the public route (way 2)

`python -m tcf_credit.rebuild DATA OUT --route free` runs these steps in order (run from start to end on
13 November 2026). The list says what each step does.

1. SEC: `fetch_sec_bulk.py --tickers-only`.
2. Ratings: download the 17g-7 archives, run `ratings_parser.py`, then `link_obligors.py`, then `fetch_companyfacts.py`
   on the links file it writes (for the companies you want).
3. `build_panel.py` makes the panel.
4. Prices: `fetch_yahoo.py`, then `yahoo_market.py`, then `market_features.py`.
5. Economy: run `fetch_public.py` for the FRED series and the Philadelphia Fed spreadsheets, then run `philly_fed.py`
   to convert the spreadsheets to the CSV names that `features_v2.py` reads; put them in `DATA/fred` and
   `DATA/fred/realtime`; then run `features_v2.py`.
6. `evaluate.py` runs the rolling-origin test.

Each program's first lines (its docstring) tell you its arguments.

## If your library gives you WRDS

This route is the lecture's. It is open only to students whose library subscribes to WRDS with CRSP and Compustat. Read
your library's terms first; keep the files on your own machine and out of any public place.

- `fetch_wrds.py` is the one-command route. It signs in with the official `wrds` Python package (the package asks for
  your password itself and can save it in your own `~/.pgpass`; the code never prints, stores or logs it), runs SQL on
  WRDS, and writes the same market folder that the old pair of programs writes:
  `python -m tcf_credit.fetch_wrds OUT/panel.csv OUT/crsp [--username NAME] [--from-year 2009]`.
  It links SEC CIK to Compustat gvkey (the `comp.company.cik` column), then to CRSP permno through the CCM link table
  (`crsp.ccmxpf_lnkhist`; link types LU and LC, primary links P and C), using the same rule as `fetch_crsp.py`.
  It writes `crsp_links.csv`, `crsp_daily.parquet` (permno, date, prc, ret, shrout, cfacpr), `crsp_sp500.csv`
  (date, sprtrn), `crsp_vwretd.csv` (date, vwretd), `crsp_delist.csv` (permno, date, dlret, dlstcd) and
  `wrds_crsp_stocknames.parquet` (the stock-names history that `audit_returns.py` reads).
  It pulls only the linked stocks and the needed dates, in chunks. CRSP's legacy files (`crsp.dsf`, `crsp.dsi`,
  `crsp.dsedelist`, `crsp.stocknames`) stop with the December 2024 release, so the program uses the CIZ tables
  (`crsp.dsf_v2`, `crsp.wrds_dailyindexret_query`, `crsp.stkdelists`, `crsp.stocknames_v2`) for later dates. The
  module's docstring names the WRDS page behind each table. It has not been run against a real WRDS account.
- The old files remain for people who already have a local copy of the CRSP daily files. `fetch_crsp.py` links the
  companies and copies each file of that local copy to a temporary folder, keeps only the linked stocks, and deletes
  the copy. It writes `crsp_links.csv`, `crsp_daily.parquet` and `crsp_sp500.csv`. `fetch_crsp_delist.py` then adds
  delisting returns (used only by `returns.py`) and the value-weighted market return (also needed by `features_v2.py`
  for beta and idiosyncratic volatility).
- `market_features.py` and `features_v2.py` read the same folder layout that `yahoo_market.py` writes, so both routes
  end in the same code (`evaluate.py` then reads the panel they write).
- Anything these programs write holds vendor data. Keep it out of any shared folder, and do not send it to an online
  tool.
