# model/ - the credit-downgrade model

This folder holds the code of the model from the lecture. It predicts the chance that S&P cuts a US company's long-term
credit rating within 12 months of the company's annual report (10-K). The inputs are the 10-K ratios, the S&P rating
state, stock-market inputs and the economy. The main model is a logistic regression ("logit": a weighted sum of the
inputs turned into a probability). Other engines are compared with it: gradient boosting, XGBoost, random forest, a
neural network and "fly brain" models. All are tested year by year on years they never saw.

```
model/
  src/tcf_credit/   the code, one module per pipeline step (below)
  synthetic/        make_panel.py: writes an example (made-up) panel, and its test
  tests/            unit tests of the code
  notebooks/        01 data and inputs, 02 train and test, 03 flag line and errors, 04 fly brain,
                    05 real data
  requirements.txt  the Python packages
```

## Three ways to study the model

1. **Example data (anyone).** A made-up panel with the real columns, made by `model/synthetic/make_panel.py`. Steps 7
   and 8 and the notebooks run on it (checked once on one Linux laptop with Python 3.14); the numbers mean nothing.
   Start here (the notebooks do exactly this).
2. **Public data (anyone, more work).** SEC company facts, the agencies' public rating histories (SEC Rule 17g-7), the
   Loughran-McDonald 10-K header file, FRED and the Philadelphia Fed real-time files, and free Yahoo prices in place of
   CRSP. Results will differ from the lecture (for example, free prices may omit companies that stopped trading). Not
   run end to end.
3. **Licensed data (if your library gives you WRDS).** The lecture's exact route: CRSP, plus two identifier tables used
   only to match companies to stocks (the Compustat company file's gvkey and CIK columns and the CRSP/Compustat Merged
   link table).

## Install

You need Python 3.12 or newer (the pinned numpy, scipy and xgboost need it). Everything was run only on Linux with
Python 3.14; the Windows and macOS commands are untested.

```
python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install torch --index-url https://download.pytorch.org/whl/cpu   # installs the CPU-only build of torch (Linux and Windows)
pip install -r model/requirements.txt   # includes JupyterLab for the notebooks
export PYTHONPATH=model/src          # Windows (PowerShell): $env:PYTHONPATH = "model/src"
```

Run every command below from the repository folder, with the environment active and `PYTHONPATH` set.

## Run the tests

```
python -m unittest discover -s model/tests
python -m unittest discover -s model/synthetic
```

The first line tests the model code, the second tests the example-data generator. No data and no internet are needed.

## What you will see

- The tests may print warnings; what matters is the last line, `OK`.
- The virtual environment took about 1.7 GB on one Linux laptop (CPU-only torch, JupyterLab included).
- Notebook 04 downloads about 133 MB the first time it runs; later runs reuse the download.
- The SEC asks every program to declare a contact (your name and e-mail). The model reads it from the environment
  variable `TCF_SEC_CONTACT`, or from `[sec] contact` in `~/.config/tcf_credit/settings.toml`. The `credit-watch` agent
  uses its own setting, `SEC_CONTACT`. It is the same e-mail in two places; set both if you use both.

## The pipeline, step by step

Steps marked **LICENSED** need CRSP stock prices (and two identifier tables, used only to match a company to its stock:
the Compustat company file's gvkey and CIK columns and the CRSP/Compustat Merged link table); every other step uses
public data or nothing at all. Each module starts with a docstring (the explanation at the top of a Python file) that
says what goes in, what comes out and what data it needs; the docstrings of `fly.py`, `brain.py` and `readout.py` also
explain the idea.

| Step | What it does | Module and command | Data |
|---|---|---|---|
| 1 | Download the SEC ticker list (the pipeline needs only this file; without `--tickers-only` the command also downloads the bulk company facts and filing lists, about 2 GB, for your own exploring). Needs `TCF_SEC_CONTACT` set to your own contact, as the SEC requires | `python -m tcf_credit.fetch_sec_bulk DATA/sec --tickers-only` | public |
| 1 | Download the free public inputs with one command: FRED and the Philadelphia Fed files are fetched, and the Loughran-McDonald and rating files are still downloaded by hand; `fetch_public` prints where to get them (it prints the page, exact file and folder to use; the rating file name patterns are in `ratings_parser.py`; the economy file names are given below in this README) | `python -m tcf_credit.fetch_public DATA [--only fred,philly,lm,ratings]` | public |
| 1 | Convert the Philadelphia Fed real-time spreadsheets to the CSV files that step 6 reads (the date text stays as in the spreadsheets) | `python -m tcf_credit.philly_fed XLSX_DIR DATA/fred/realtime` | public |
| 1 | Reduce the Loughran-McDonald header file (the list of 10-K filers and their names) | `python -m tcf_credit.lm_headers DATA/lm_headers.csv 2009 < HEADER_FILE.csv` | public |
| 2 | Read the agencies' rating ZIP files into one table of rating events | `python -m tcf_credit.ratings_parser DATA/ratings OUT/ratings` | public |
| 3 | Link each rated company to its SEC number (CIK) by name | `python -m tcf_credit.link_obligors OUT/ratings/ratings_obligor_events.csv.gz DATA/lm_headers.csv OUT/links.csv` | public |
| 3b | Fetch each linked company's XBRL numbers (the tagged financial data in each filing) from the SEC | `python -m tcf_credit.fetch_companyfacts OUT/links.csv DATA/companyfacts --us-only` | public |
| 4 | Build the panel: one row per 10-K, with ratios, the rating state (the S&P rating, outlook, watch status and recent actions on the snapshot date, which is the filing date plus one day) and the label (1 if S&P downgrades the company within 365 days after the snapshot date, else 0) | `python -m tcf_credit.build_panel OUT/ratings/ratings_obligor_events.csv.gz OUT/links.csv DATA/companyfacts OUT/panel.csv` | public |
| 4 | Write the ticker lists for the free price route: `TICKERS.csv` (cik,ticker,exchange) for the panel's companies that have a SEC ticker, and `TICKERS.txt` (one ticker per line plus SPY) | `python -m tcf_credit.tickers OUT/panel.csv DATA/sec/company_tickers_exchange.json OUT` | public |
| 5a | Prices, licensed route: sign in to WRDS with your own account and pull the link table, CRSP daily data, the market return, delisting returns and stock names in one command. For people who already have a local copy of the CRSP files, the old route is still there (`WRDS_LOCAL_DIR` holds the two identifier tables; `SOURCE` is where your copy lives, or set `TCF_CRSP_SOURCE`) | `python -m tcf_credit.fetch_wrds OUT/panel.csv OUT/crsp [--username NAME] [--from-year 2009]`; old route: `python -m tcf_credit.fetch_crsp OUT/panel.csv WRDS_LOCAL_DIR OUT/crsp --source SOURCE`, then `python -m tcf_credit.fetch_crsp_delist OUT/crsp --source SOURCE` | **LICENSED** |
| 5a | Prices, free stand-in: download Yahoo prices, then write them in the CRSP layout | `python -m tcf_credit.fetch_yahoo TICKERS.txt DATA/yahoo`, then `python -m tcf_credit.yahoo_market DATA/yahoo TICKERS.csv OUT/panel.csv OUT/crsp` (`TICKERS.csv` has the columns cik,ticker; the ticker file for `fetch_yahoo` must include SPY, the stand-in for the market) | public (survivorship bias) |
| 5b | Add the market inputs (12-month return, volatility, distance to default: a naive formula from the stock's value, volatility and debt) | `python -m tcf_credit.market_features OUT/panel.csv OUT/crsp OUT/panel_market.csv` | needs 5a |
| 6 | Add changes since the last report, beta, and the economy as first released (this is the input set the code calls "v2"; "v2" is only its name) | `python -m tcf_credit.features_v2 OUT/panel_market.csv OUT/crsp DATA/fred OUT/panel_v2.csv` | needs 5a |
| 6 | Optional: add the tone of each 10-K's text, for `evaluate --text` (`SUMMARIES.csv` is the Loughran-McDonald 10-X Summaries file, downloaded by hand from sraf.nd.edu) | `python -m tcf_credit.lm_tone PANEL.csv SUMMARIES.csv OUT.csv` | public |
| 7 | Test the models year by year (rolling origin: each test year uses only earlier years for training; one-year gap: the year just before the test year is left out of training). `--jobs N` runs the test years in N worker processes (default: the number of CPU cores; `--jobs 1` runs them one after another); the output files are the same for any N | `python -m tcf_credit.evaluate OUT/panel_v2.csv OUT/run [--zoo] [--jobs N]` | none beyond the panel |
| 8 | Compare models with a firm-clustered bootstrap (whole companies are drawn again with replacement, so a firm's years stay together), or two runs with each other | `python -m tcf_credit.compare_models OUT/run`, `python -m tcf_credit.compare_runs RUN_A RUN_B` | none beyond the run |
| 9, 9b | Do flagged stocks do worse than the market afterwards? Audit the extreme winners | `python -m tcf_credit.returns RUN OUT/panel_v2.csv OUT/crsp OUT/returns`, `python -m tcf_credit.audit_returns OUT/returns OUT/crsp STOCKNAMES.parquet OUT/audit` (`STOCKNAMES.parquet` is the CRSP stock-names file) | **LICENSED** |

To skip steps 1 to 6, write an example panel and start at step 7:

```
python model/synthetic/make_panel.py --out example_panel.csv.gz
python -m tcf_credit.evaluate example_panel.csv.gz example_run
python -m tcf_credit.compare_models example_run
```

The economy files that step 6 reads are public: three daily series from FRED and three real-time files from the
Philadelphia Fed. Step 6 expects, in `DATA/fred`: `BAA10Y.csv`, `T10Y3M.csv`, `VIXCLS.csv`, and in `DATA/fred/realtime`:
`unemployment_first_release.csv`, `indpro_vintages.csv`, `gdp_growth_first_second_third.csv` (see `Macro` in
`features_v2.py`). The Philadelphia Fed files are public spreadsheets: `fetch_public` downloads the FRED series and the
spreadsheets, and `philly_fed.py` converts the spreadsheets to these three CSV files (see the pipeline table). The
Loughran-McDonald and rating files are still downloaded by hand; `fetch_public` prints where to get them.

Other files in `src/tcf_credit/`: `zoo.py` (the extra engines of `evaluate --zoo`), `fly.py`, `brain.py` and
`readout.py` (the fly brain models, notebook 04), `trend_v3.py` (an optional experiment, not used by the main model,
that tests whether trend inputs help), `sec_http.py` (SEC downloads).

## Scoring a company

Scoring runs the same steps on the latest 10-K of the companies you name, trains the logit on the years before, and
reports the probability, the flag line and whether the company is flagged.

```
python -m tcf_credit.credit_model HON --build BUILD_FOLDER --events OUT/ratings/ratings_obligor_events.csv.gz
```

`--build` (or the environment variable `TCF_BUILD`) is the folder with your own pipeline outputs; `--events` (or
`TCF_EVENTS`) is the rating-event table from step 2. Run `python -m tcf_credit.credit_model --help` for the folder
layout. `score_holdings.py` is the lower-level piece that does the scoring itself. There are no default paths: the
command stops with a message if they are missing.

## The notebooks

Open them with `jupyter lab model/notebooks`. Each makes its own example panel in a temporary folder, deletes it at the
end, and runs in under five minutes.

1. `01_data_and_inputs.ipynb`: one row, the label, the four input groups of the main model (plus text tone, a fifth
   group used only in a side test), why each is known on the day.
2. `02_train_and_test.ipynb`: rolling-origin testing, logit and gradient boosting, ROC-AUC and PR-AUC.
3. `03_flag_line_and_errors.ipynb`: the flag line, caught and missed downgrades, false alarms.
4. `04_fly_brain.ipynb`: the fruit-fly models: a fixed wiring with a trained readout, the shuffled-wiring control, the
   whole-brain version, and what the lecture found.
5. `05_real_data.ipynb`: the real data. It runs the one-command rebuild (free public data or the WRDS route), then
   reads the real panel and the year-by-year results.

## Results you may quote (lecture, licensed data, aggregates only)

- Test years 2016-2024: 6,380 annual reports, 862 followed by an S&P downgrade within 12 months (13.5%).
- Logit: ROC-AUC 0.802, PR-AUC 0.494. Other single engines (not the fly models): ROC-AUC 0.785-0.808; boosting
  (0.808) is slightly above the logit, but its interval includes zero, so no single engine is clearly better than the
  logit. The neural network is clearly below. Both averages that include the logit are clearly above it: the
  logit-boosting average (0.817) by 0.014 (interval 0.009-0.020; it is also ahead on PR-AUC, +0.019) and the average of
  all non-fly models (0.813) by 0.011. S&P rating state alone: 0.757.
- Fly brain models: ROC-AUC 0.759-0.807; the real fly wiring had no consistent edge over shuffled wiring.
- Flag line (the score that marked the top 10% of an earlier year's scores): flagged 888 of 6,380 reports, caught 407 of
  862 downgrades, with 8.7% false alarms. Flagging the top 10% of each test year instead (642 reports, 10.06%) caught
  353, with 5.2% false alarms.

Your results will differ from these. The example data is made up; free price histories often omit delisted firms, which
can bias the public route (not tested).

A flag is a reason to look, not a reason to sell.
