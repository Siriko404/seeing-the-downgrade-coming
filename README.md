# Credit-downgrade model and credit-watch agent

Study material from a guest lecture for ADM4357 (Telfer Capital Fund, University of Ottawa), given on 11 November 2026.
It is teaching material, not investment advice. Nothing here tells you to buy, hold or sell anything.

You can work through it alone, at your own pace. A path of about six study sessions is in
[docs/STUDY-PATH.md](docs/STUDY-PATH.md).

## What is in it

**Part 1, the model (`model/`).** A credit rating agency such as S&P sometimes lowers (downgrades) the rating of a
company. The model estimates the chance that S&P downgrades a US company within 12 months of that company's annual
report (the 10-K). It reads the report's financial ratios, the company's current S&P rating and outlook, how its stock
has behaved, and the state of the economy (four groups of inputs; the word-list text test is a side test). The main
model is a logistic regression ("logit"). It is compared with gradient boosting, XGBoost, a random forest, a neural
network, and "fly brain" models (a fixed network wired like a fruit fly's brain, with only a simple readout trained).
Every model is tested year by year on years it never saw.

**Part 2, the agent (`agent/`).** `credit-watch` is a skill for an AI agent (a program that uses a language model to
carry out steps on your computer). You give it a company. Code downloads the company's SEC filings, the AI reads the
rating paragraphs into rows, code checks every row against the filing's own words, and code writes a short note in which
each rating line cites the rows it comes from. The AI reads; code checks and writes.

## Folder layout

```
README.md                  this file
docs/
  STUDY-PATH.md            six sessions, in order
  GLOSSARY.md              the main terms, in plain words
  DATA-GUIDE.md            every input, where it comes from, what you must do
  RESULTS.md               the lecture's results, and what they do not show
  LITERATURE.md            where the model stands among published work
  SLIDE-ERRATA.md          corrections to the slides
  KNOWN-LIMITATIONS.md     what the model and the agent cannot do
model/
  README.md                how the model code is organised
  FLY-DATA.md              the public fruit-fly files (for notebook 04)
  requirements.txt         Python packages
  src/tcf_credit/          the code
  tests/                   automatic tests (they use small test inputs)
  notebooks/
    01_data_and_inputs.ipynb
    02_train_and_test.ipynb
    03_flag_line_and_errors.ipynb
    04_fly_brain.ipynb
    05_real_data.ipynb
agent/
  README.md                how to install and run credit-watch
  skills/credit-watch/     the skill itself
  tests/                   automatic tests (they use small test inputs)
  notebooks/agent_tutorial.ipynb
deck/
  lecture-slides.pdf       the lecture slides (the last page lists corrections)
```

## Start here in 4 steps

1. **Get the package, then install Python and a virtual environment** (a private folder of packages for this project).
   The model needs Python 3.12 or newer; the agent alone is written for Python 3.10 or newer. Everything was run only on
   Linux, with Python 3.14 and 3.13; the Windows and macOS commands are untested. In a terminal:
   ```
   git clone https://github.com/Siriko404/seeing-the-downgrade-coming.git
   cd seeing-the-downgrade-coming
   python3 -m venv .venv
   source .venv/bin/activate          # Windows PowerShell: .venv\Scripts\Activate.ps1
   pip install torch==2.15.0 --index-url https://download.pytorch.org/whl/cpu   # installs the CPU-only build of torch (Linux and Windows)
   pip install -r model/requirements.txt
   ```
   The requirements include JupyterLab for the notebooks (`jupyter lab` opens them in your browser).
2. **Run the tests.** They check that the code works on your computer:
   ```
   PYTHONPATH=model/src python -m unittest discover -s model/tests
   ```
   (Windows PowerShell: set `$env:PYTHONPATH="model/src"` first, then run the same `python -m unittest ...` line.)
3. **Build the real table.** From the repository folder, with the environment active, run:
   ```
   PYTHONPATH=model/src python -m tcf_credit.rebuild data build --route free
   ```
   The rating files and the Loughran-McDonald file must be downloaded by hand; the command prints where. On 13
   November 2026 this route was run from start to end in about 30 minutes on an 8-core cloud machine. It writes the
   real table `build/panel_v2.csv` and the test results in `build/run/`, the rating events in
   `build/ratings/ratings_obligor_events.csv.gz`, and other files. Notebook 5 explains it.
4. **Open notebook 01:** `jupyter lab model/notebooks/01_data_and_inputs.ipynb`. It reads the table you built and
   walks through every input. Notebooks 1 to 5 read that table.

Then follow [docs/STUDY-PATH.md](docs/STUDY-PATH.md).

## What you will see

- Test runs may print warnings. What matters is the final `OK`.
- The virtual environment took about 1.7 GB of disk on one Linux laptop (CPU-only torch, JupyterLab included).
- Notebook 04 downloads about 133 MB of public fruit-fly files the first time you run it.
- The notebooks find the repository and read the real files from `build/` (or from `TCF_NB_OUT_DIR` and
  `TCF_NB_DATA_DIR` if you set them), so you do not need to change paths.

## Two ways to get the data

1. **Free public data (anyone, more work).** SEC company facts, the agencies' public rating histories, the
   Loughran-McDonald 10-K header file, FRED and Philadelphia Fed economy files, and free Yahoo prices in place of the
   licensed ones. One command runs every step:
   `PYTHONPATH=model/src python -m tcf_credit.rebuild data build --route free` (the rating files and the
   Loughran-McDonald file must be downloaded by hand; the command prints where). Free prices miss many
   companies that stopped trading, so your results will differ from the lecture. On 13 November 2026 this route was run
   from start to end in about 30 minutes on an 8-core cloud machine; the command downloaded the SEC ticker list and
   company facts, the Philadelphia Fed files and the Yahoo prices fresh, while the rating-history ZIP files and the
   Loughran-McDonald files were the lecture's hand-downloaded copies and the three FRED files were saved by hand. The
   model was tested on 4,902 annual reports with 515 downgrades, against 6,380 with 862 in the lecture, and the logit
   scored ROC-AUC 0.759 against the lecture's 0.802. FRED may not answer the automatic download; the command then
   prints the links to open in your browser. See notebook 5 and [docs/DATA-GUIDE.md](docs/DATA-GUIDE.md).
2. **Licensed data (only if your library gives you WRDS).** The lecture's own route, with your own WRDS account:
   `PYTHONPATH=model/src python -m tcf_credit.rebuild data build --route wrds --wrds-user YOUR_NAME` (it asks for your
   WRDS password). On the lecture's saved data the package's code rebuilds the lecture's table and results exactly; the
   WRDS download itself has not been run against WRDS yet (no account was available). Everything this route writes
   holds licensed data: keep it on your own computer and clear the notebook outputs before you share the notebook.

## What is NOT included, and why

- **No licensed data and no model scores are included.** The lecture's stock prices came from CRSP, a licensed database,
  through WRDS. To match each company to its CRSP stock, the code used two identifier tables from WRDS:
  the Compustat company file (only its gvkey and CIK columns) and the CRSP/Compustat Merged link table. No Compustat
  financial data is used. All accounting numbers came from the SEC filings as first filed. Licensed data is not passed
  on here; check your library's terms before you share any of it. The agent's offline demo keeps saved rating passages
  from public SEC filings in `agent/skills/credit-watch/cache/`. A rating passage is a paragraph or table that mentions
  ratings, not a whole filing. There are passages for HON, RY and CMP; the file for SJ holds only a firm name and no
  text. The agent's tests keep small saved runs built from public filings. The public data are free but must be
  downloaded by you, under their own terms.
- **No scores of real companies, with one exception.** The only real score in the package is one classroom example on
  the slides: Compass Minerals (CMP), model chance 51% of an S&P downgrade within 12 months, from its 10-K filed on 29
  November 2023 (S&P cut its rating 204 days after the filing, 203 days after the snapshot date, the day after the
  filing). There is no other real score and no file of real scores (the agent tests use small test inputs). The
  notebooks read the table you build; the agent tutorial runs on saved rating passages from real filings and shows no
  model score. The model's code is in `model/`, but the trained model, its licensed training data and its scores are
  not included, so a note made with this package shows no model score.
- **The slides are a PDF** (`deck/lecture-slides.pdf`), not an editable file.

## Read next

[Glossary](docs/GLOSSARY.md) if a word is new. [Results](docs/RESULTS.md) for what the lecture found.
[Known limitations](docs/KNOWN-LIMITATIONS.md) before you trust any number.

Licence: the code is under the MIT licence (`LICENSE`); the documents, the notebook text and the slides are under CC BY
4.0 (`LICENSE-docs.md`).
