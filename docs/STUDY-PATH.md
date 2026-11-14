# Study path: six sessions

Plan about 1 to 2 hours per session (the author's estimate, not measured). The model comes first (sessions 1 to 4), then
the agent (sessions 5 and 6). Each session has a goal, what to open, what to do, and a self-check. If a word is new,
look it up in the [glossary](GLOSSARY.md).

Before session 1, make a Python environment with JupyterLab and the packages in `model/requirements.txt`, then run the
model tests from the repository folder:

```
PYTHONPATH=model/src python -m unittest discover -s model/tests
```

Notebooks 1 to 4 read the real table that you build in session 1, `build/panel_v2.csv`, and the saved test results in
`build/run/`. The folder settings are those of notebook 5: `OUT_DIR` defaults to `<repository>/build` and `DATA_DIR` to
`<repository>/data`; the environment variables `TCF_NB_OUT_DIR` and `TCF_NB_DATA_DIR` override them. If
`OUT_DIR/panel_v2.csv` is missing, a notebook prints "No real table yet: run the rebuild first (see notebook 5)." and
every later cell that needs data prints one short line and does nothing. In that case, finish the rebuild in session 1.

The free route and the WRDS route do not give the same table, so your numbers need not equal the lecture's. On the WRDS
route every table and every notebook output holds licensed data: keep those files on your own computer and clear the
notebook outputs before you share a notebook.

---

## Session 1: the question and the inputs (estimate: about 2 hours, including the rebuild)

**Goal.** Say in your own words what the model predicts and what goes into it.

**Open.**
- `deck/lecture-slides.pdf`: skim it first as the overview (its last page, and `docs/SLIDE-ERRATA.md`, list corrections
  to the slides)
- [README](../README.md) (the two parts)
- [docs/GLOSSARY.md](GLOSSARY.md): read the terms "credit rating", "notch", "investment grade", "outlook", "label",
  "panel", "look-ahead bias"
- [docs/DATA-GUIDE.md](DATA-GUIDE.md): the sections on the free route, the WRDS route and the table of inputs
- `model/notebooks/05_real_data.ipynb`: how the rebuild works and what it writes
- `model/notebooks/01_data_and_inputs.ipynb`

**Do.**
1. Read the data guide's list of input groups. For each group, write one sentence on why it could warn of a downgrade.
2. Set your own SEC contact first: the SEC asks every automated client for one, and the rebuild stops without it.
   Use the environment variable `TCF_SEC_CONTACT` or the `[sec] contact` line in
   `~/.config/tcf_credit/settings.toml`:

   ```
   export TCF_SEC_CONTACT="Your Name you@school.ca"
   ```

   On Windows PowerShell use `$env:TCF_SEC_CONTACT = "Your Name you@school.ca"` instead. Then build the real table
   once, from the repository folder:

   ```
   PYTHONPATH=model/src python -m tcf_credit.rebuild data build --route free
   ```

   Two Loughran-McDonald files and five rating-history ZIP files (three S&P, one Fitch, one Moody's) must be
   downloaded by hand; the message names each page and the place to save it. If FRED does not answer, download its
   three files (BAA10Y, T10Y3M, VIXCLS) from the browser.

   The rebuild runs its nine steps in order. The free route downloads public files and can need several GB of disk and
   about 30 minutes on an 8-core cloud machine (13 November 2026); a home connection may be slower. If a step stops
   for a file that must be downloaded by hand, save the file where the message says and run the command again;
   finished steps are skipped. The rebuild writes `build/panel_v2.csv`, the test results in `build/run/`
   (`pooled.csv`, `per_year.csv`, `predictions.csv`, `params.json`, `comparison.csv`) and the rating
   events in `build/ratings/ratings_obligor_events.csv.gz`. Notebook 5 shows the same run and explains each file.
3. Run notebook 01 from top to bottom. It reads your real table from `build/panel_v2.csv` (or from the folder in
   `TCF_NB_OUT_DIR`), shows the `notch` column, and states the rule that the snapshot is the day after the filing. If it
   prints "No real table yet: run the rebuild first (see notebook 5).", the rebuild has not finished; return to step 2.
4. In the section "One row = one annual report of one company", the cell that ends in `.head(6)` shows six rows of your
   table. Pick one row and find its `label`, its `notch` and its `debt_assets` (debt to assets).

**Self-check.**
- What does "label = 1" mean, and when is the label first known?
- Why is a report's snapshot date one day after the filing date?
- Which input groups come from the 10-K, which from the rating agency, which from the market, which from the economy?
- Which route did you use, and why can its numbers differ from the lecture's?

---

## Session 2: train and test (estimate: about 2 hours)

**Goal.** Understand how the model is trained and tested without peeking at the future.

**Open.**
- `model/notebooks/02_train_and_test.ipynb`
- Glossary: "rolling origin", "embargo", "logit", "overfitting", "ROC-AUC", "PR-AUC", "base rate"

**Do.**
1. Run notebook 02. It reads your real table from `build/panel_v2.csv` and the saved test results from `build/run/`.
2. In the section "Rolling-origin testing", the last code cell prints a table with the columns `train on years` and
   `left out` for each test year from 2016 to 2024. Pick one test year and write down which years it trains on and which
   year it leaves out (the embargo). The first code cell of that section sets `Y = 2020` and prints, for the reports of
   year Y-2 and of year Y-1, the share whose label was already known before 1 January of Y. Change `Y` to another year
   from 2016 to 2024 and run that cell again. For Y-2 the labels are known; for Y-1 almost none are. That is the reason
   for the gap.
3. In the section "Fit the two main engines with the package's own code", the cell that starts with
   `from sklearn.metrics import` sets `Y = 2020` again and chooses the training years and the test year in the line
   `train, test = data[data.year <= Y - 2], data[data.year == Y]`. Change `Y` to another year from 2016 to 2024, then
   run that cell and the check cell that starts with `for name in hand:` again.
4. In the section "ROC-AUC and PR-AUC in plain words", the last table lists the ROC-AUC and PR-AUC of `logit`,
   `boosting`, `logit_rating_only` and `avg_logit_boosting`, and a row "(no skill)". Compare `logit` with each of the
   others. Then read the lecture's values in RESULTS.md: the logit scored ROC-AUC 0.802 and PR-AUC 0.494, the S&P
   rating state alone 0.757, the logit-boosting average 0.817 and the average of all non-fly models 0.813. Ask which
   differences you would trust on real data and why your own free-route numbers need not match the lecture's.
5. Read the module description at the top of `model/src/tcf_credit/evaluate.py`.

**Self-check.**
- Why does training stop two years before the test year, not one?
- A model scores AUC 0.5 on the test years. What does that mean?
- Why is PR-AUC more informative than ROC-AUC when only about 1 report in 7 is followed by a downgrade?

---

## Session 3: the flag line, errors and published work (estimate: about 2 hours)

**Goal.** Turn probabilities into a yes/no flag, and count what that costs.

**Open.**
- `model/notebooks/03_flag_line_and_errors.ipynb`
- [docs/RESULTS.md](RESULTS.md)
- [docs/LITERATURE.md](LITERATURE.md)

**Do.**
1. Run notebook 03. It reads your real table from `build/panel_v2.csv` and the test scores from
   `build/run/predictions.csv`. In the section "What is a flag, and where does the line come from?", the last code cell
   prints the flag line for 2020 and how many reports it flags. The section "Caught, missed, false alarms: the 2x2
   table" prints the counts of caught downgrades, missed downgrades and false alarms for that line, all test years
   together. The next code cell fills a table that compares the earlier-year line with the rank rule (flag the top share
   of each year) at several shares. Its loop is `for share in [0.05, 0.10, 0.20, 0.30]:`. Add `0.50` to the list, run
   the cell again, and watch how the caught and false-alarm counts change when more companies are flagged.
2. In the section "The level of the probabilities in a shock year", the table shows, for each test year, the actual
   downgrade rate next to the average predicted probability. On the lecture's real data the two did not stay close in
   every year. In 2020 the gap was largest (actual about 29%, predicted about 14%); 2018 and 2024 also differed by more
   than 11 points, the other way (2018: 23.2% predicted, 10.7% actual; 2024: 21.6% predicted, 9.7% actual; see
   RESULTS.md). Read the same table in your own build and find its largest gap; do not assume the lecture's gap repeats.
3. Read RESULTS.md. For each number, say aloud what it means and what it does not show.
4. Read LITERATURE.md. Write down two reasons why our AUC and a paper's AUC cannot be compared directly.

**Self-check.**
- What is the flag line, and why is it set from an earlier year's scores?
- If you flag more companies, what happens to misses and to false alarms?
- In 2020 the model ranked firms well, but its probabilities were far too low. Should you read a probability as an exact
  chance, or as a ranking of who is riskier than whom? Why?

---

## Session 4: the fly brain (estimate: about 1.5 hours)

**Goal.** See what a fixed, brain-shaped network can and cannot add.

**Open.**
- `model/notebooks/04_fly_brain.ipynb`
- `model/FLY-DATA.md` (the two public connectome files)
- Glossary: "connectome", "Kenyon cell", "readout", "shuffled control"

**Do.**
1. Run notebook 04 on your real table (the first run downloads about 133 MB). It reads `build/panel_v2.csv`.
2. Find where the wiring is fixed and where learning happens. In section 4, `fly.MushroomBody("real", seed=1, C=0.01)`
   sets up the fixed wiring. In section 7, `.fit(x_train, y_train)` trains the readout, which is the only part that
   learns.
3. In section 7, the cell that fits `fly real wiring` and `fly shuffled wiring` with seeds 1, 2 and 3 prints a table of
   mean, lowest and highest AUC, and a last line "real minus shuffled, same seed". Look at those three numbers: are they
   all positive, all negative, or mixed? The lecture's finding (see RESULTS.md and section 9 of the notebook) was no
   consistent edge for the real wiring. Read the signs in your own table too, but do not treat one positive seed as
   proof: on the lecture's data the AUC of one fly model moved by about 0.025 to 0.036 across three seeds.

**Self-check.**
- Why is the shuffled control needed?
- If real and shuffled wiring score the same, what is the wiring *not* adding?
- Name one reason a result like this does not prove that the fly brain "knows" nothing about credit.

---

## Session 5: the agent, offline (estimate: about 1.5 hours)

**Goal.** Understand the division of work between the AI and the code, and see a note without using the internet.

The agent alone is written for Python 3.10 or newer; it was run on Python 3.14 and 3.13.

**Open.**
- `agent/README.md`
- `agent/notebooks/agent_tutorial.ipynb`
- `agent/skills/credit-watch/SKILL.md` (the instructions the AI gets)
- Glossary: "AI agent", "skill", "prompt", "offline mode", "8-K", "CIK", "EDGAR", "SEDAR+"

**Do.**
1. Read the agent README up to the "How the checks work" section.
2. Run the tutorial notebook. It works in offline mode, on the saved copy of Honeywell's filings
   (`agent/skills/credit-watch/cache/HON.json`) that comes with the agent.
3. Read the checks (C1 to C4) in the agent README. In the notebook, section 6 ("Step 3, CHECK") has a table with a
   column "It protects against", and the `REJECTED` lines below it show which row failed which check (row 2 fails C1,
   row 4 fails C3, row 5 fails C4). Pick one check and say in your own words which mistake it caught. Then do "Try it
   yourself" at the end: change the `rating_date` of row 4 to `2026-03-06`, run the notebook again from the top, and see
   which line moves from "set aside" to "kept".
4. Run the agent tests from the repository folder: `cd agent`, then `python -m unittest discover -s tests`.

**Self-check.**
- Which steps does the AI do and which does code do?
- Why must every quote appear word for word in the filing?
- What does the note do with a text row that was read by the AI?

---

## Session 6: a live run and due diligence (estimate: about 2 hours)

**Goal.** Run the agent on a company of your choice, then check its work like an analyst would.

**Open.**
- `agent/README.md`, sections "Install" and "Set up your SEC contact"
- [docs/KNOWN-LIMITATIONS.md](KNOWN-LIMITATIONS.md)
- The company's own latest 10-K on EDGAR

**Do.**
1. Give the SEC a contact: your own name and e-mail address, as the agent README describes. Do not share it or save it
   in a file you publish.
2. Run the skill on one company that has a US 10-K and a published rating. Use your AI agent.
3. Due diligence on the note, line by line:
   - Open each link and find the quote. Is it word for word?
   - Check every row marked "AI-read text: verify quote".
   - Check the dates: the date the agency acted, and the date of the filing. Which is earlier?
   - Look at the gaps the note lists. Which ones can you close from the 10-K?
   - Find a rating the note missed, if any.
4. Write 5 lines: what the note got right, what it got wrong or missed, and what you would check next.

**Self-check.**
- Which parts of the note did you trust only after reading the source?
- Which limitation from KNOWN-LIMITATIONS.md did you hit, if any?
- Would you let the agent run unattended on a portfolio? Why or why not?

---

## Go further

- **Use the WRDS route.** If your library gives you WRDS with CRSP and Compustat, build the lecture's route from the
  repository folder:
  `PYTHONPATH=model/src python -m tcf_credit.rebuild data build --route wrds --wrds-user YOUR_NAME`.
  The command asks for your WRDS password itself. On the lecture's saved data the package's code rebuilds the lecture's
  table and numbers exactly; the WRDS download step itself has not yet been run against WRDS. Your rebuild can still
  differ because the rating and SEC files change over time. Everything this route writes is licensed data: keep it on
  your own computer and clear the notebook outputs before you share a notebook. Notebook 5 explains both routes.
- **Compare the free and WRDS routes.** The free route was run from start to end on 13 November 2026: 4,902 reports,
  515 downgrades, logit ROC-AUC 0.759 (lecture: 6,380 reports, 862 downgrades, 0.802). A likely reason for the gap is
  survivorship bias: free price histories often leave out companies that stopped trading, and those can be the ones
  that were downgraded; this was not tested. Read the sections on the free route and the WRDS route in DATA-GUIDE.md.
- **Add an input.** Pick one idea (for instance, a change in interest coverage over two years). Add it as a column,
  re-run the test, and report whether the AUC moved by more than the year-to-year spread.
- **Try another horizon.** Predict a downgrade within 6 months or 24 months. Remember that a short and a long horizon
  are different questions, so their scores are not comparable; see LITERATURE.md.
- **Change the flag line.** Choose the share to flag by the cost of a miss against the cost of a false alarm.
- **Test the agent.** Give it a firm with unusual wording and see what it misses.
