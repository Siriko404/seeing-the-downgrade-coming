# Credit-downgrade model and credit-watch agent

Study package from a guest lecture on 11 November 2026 for ADM4357 (Telfer Capital Fund, University of Ottawa).
It has two parts: a credit-downgrade model in `model/` and the `credit-watch` skill in `agent/`.
It is teaching material, not investment advice.

## Quick start

### With your AI agent

Give your agent this link and say "install everything".

https://github.com/Siriko404/seeing-the-downgrade-coming

Your agent asks for your name and e-mail (the SEC contact), installs both parts, and explains what you have.
This was tested live with opencode on 13 November 2026.
It was not run live with Claude Code or Codex.

### By hand

```
git clone https://github.com/Siriko404/seeing-the-downgrade-coming.git
cd seeing-the-downgrade-coming
python3 install.py --check
```

The model needs Python 3.12 or newer; the install downloads about 1.7 GB of packages.
On Windows use `python` in place of `python3`.

## Try the skill first

Start a new agent session, then run `/credit-watch HON --offline`.
It needs no network and no contact; the note is `credit-watch/run/note_HON.md`.
The skill reads SEC filings, code checks every row, and code writes a cited note.
Read [agent/README.md](agent/README.md) and [agent/MODIFYING.md](agent/MODIFYING.md).

## Build the real table

1. Set your own SEC contact with `python3 install.py --contact "Name e-mail"` or `TCF_SEC_CONTACT`:

   ```
   export TCF_SEC_CONTACT="Your Name you@school.ca"    # Linux and macOS
   $env:TCF_SEC_CONTACT="Your Name you@school.ca"      # Windows PowerShell
   ```

2. Download these files by hand in your browser: five rating-history ZIP files, two Loughran-McDonald files,
   and three FRED files.
   On 13 November 2026 FRED did not answer the automatic download on either machine tried.
   Expect to save the three FRED files by hand.
   The rebuild prints each page and where to save each file.

3. Activate the environment with `source .venv/bin/activate` (Windows PowerShell: `.venv\Scripts\Activate.ps1`).

4. From the repository folder, run the rebuild:

   ```
   PYTHONPATH=model/src python -m tcf_credit.rebuild data build --route free
   ```

   On Windows PowerShell, set `$env:PYTHONPATH="model/src"` first, then run the same line.
   On 13 November 2026 this took about 30 minutes on an 8-core cloud machine.
   Hand downloads are not included.
   The rebuild writes `build/panel_v2.csv`, the results in `build/run/`, and the rating events in
   `build/ratings/ratings_obligor_events.csv.gz`.
   See [docs/DATA-GUIDE.md](docs/DATA-GUIDE.md) for every input.

5. Open notebook 01:

   ```
   jupyter lab model/notebooks/01_data_and_inputs.ipynb
   ```

## Two ways to get the data

| Way | Who can use it | Command flag | What you get | Tested? |
|---|---|---|---|---|
| Free public data | Anyone | `--route free` | 4,902 reports, logit ROC-AUC 0.759 | Yes, start to end 13 November 2026 |
| Your own WRDS account | Anyone with WRDS | `--route wrds --wrds-user YOUR_NAME` | Lecture table | Sign-in never run |

The free run tested 4,902 reports with logit ROC-AUC 0.759; the lecture had 6,380 and 0.802.
Free prices miss many companies that stopped trading, so fewer companies enter the free table.
The WRDS route is the lecture's route; from its saved data it rebuilds the table and results exactly.
Its files hold licensed data, so never share them.

## The notebooks

- `01_data_and_inputs.ipynb`: one row, the label, the input groups, and why each input is known on the day.
- `02_train_and_test.ipynb`: year-by-year testing, logit and gradient boosting, ROC-AUC and PR-AUC.
- `03_flag_line_and_errors.ipynb`: the flag line, caught and missed downgrades, false alarms.
- `04_fly_brain.ipynb`: fruit-fly models, fixed wiring with a trained readout, and the shuffled-wiring control.
- `05_real_data.ipynb`: the two data routes and the one-command rebuild.

Notebooks 1 to 4 were run on the lecture's table, not yet on a free-route table.

## What is in the folders

- `README.md`: this file.
- `install.py`: one-step install for the model and the skill.
- `AGENTS.md`: agent instructions; `CLAUDE.md` points to it.
- `docs/`: study path, glossary, data guide, results, and known limitations.
- `model/`: the model's code, five notebooks, and tests.
- `agent/`: the `credit-watch` skill, its tests, and a tutorial notebook.
- `deck/`: the lecture slides as one PDF file.

## What is not included

- No licensed data. The lecture's stock prices came from CRSP through WRDS, so you must get your own access.
- No trained model and no scores are included. The one exception is the classroom example on the slides.
- Compass Minerals: model chance 51%; 10-K filed 29 November 2023; S&P cut the rating 204 days after the filing.
- No data files. You download the public data yourself under each source's terms.

## Tests

The model tests need the activated environment; the agent tests need only plain Python.

```
# model tests, from the repository folder
PYTHONPATH=model/src python -m unittest discover -s model/tests
# agent tests, from the agent/ folder
python3 -m unittest discover -s tests
```

## Limits

- Exact results need licensed data. Free data can have survivorship bias.
- The yearly level can shift, so read a probability as a ranking.
- The model covers only S&P-rated US 10-K filers, not financials or utilities.
- Notebooks 1 to 4 were not run on a free-route table.

Full list: [docs/KNOWN-LIMITATIONS.md](docs/KNOWN-LIMITATIONS.md). Plan: [docs/STUDY-PATH.md](docs/STUDY-PATH.md).

## Licence

Licence: code MIT (`LICENSE`); documents, notebook text and slides CC BY 4.0 (`LICENSE-docs.md`).
