# Study path: six sessions

Plan about 1 to 2 hours per session (the author's estimate, not measured). The model comes first (sessions 1 to 4), then the agent (sessions 5 and 6). Each
session has a goal, what to open, what to do, and a self-check. If a word is new, look it up in the
[glossary](GLOSSARY.md).

Before session 1, finish steps 1 and 2 in the [README](../README.md#start-here-in-3-steps): a Python environment with JupyterLab, and passing
tests. Step 3 there (open notebook 01) is session 1.

Notebooks that run on the example data give made-up numbers. Do not compare them with the lecture's results.

---

## Session 1: the question and the inputs (estimate: about 1.5 hours)

**Goal.** Say in your own words what the model predicts and what goes into it.

**Open.**
- `deck/lecture-slides.pdf`: skim it first as the overview (its last page, and `docs/SLIDE-ERRATA.md`, list corrections to the slides)
- [README](../README.md) (the two parts)
- [docs/GLOSSARY.md](GLOSSARY.md): read the terms "credit rating", "notch", "investment grade", "outlook", "label", "panel", "look-ahead bias"
- [docs/DATA-GUIDE.md](DATA-GUIDE.md): the first two sections and the table of inputs
- `model/notebooks/01_data_and_inputs.ipynb`

**Do.**
1. Read the data guide's list of input groups. For each group, write one sentence on why it could warn of a downgrade.
2. Run notebook 01 from top to bottom. It makes the example table with `model/synthetic/make_panel.py`, and shows the
   `notch` column and the rule that the snapshot is the day after the filing.
3. In the notebook, look at one row of the table. Find its label, its notch and its debt-to-assets ratio.

**Self-check.**
- What does "label = 1" mean, and when is the label first known?
- Why is a report's snapshot date one day after the filing date?
- Which input groups come from the 10-K, which from the rating agency, which from the market, which from the economy?

---

## Session 2: train and test (estimate: about 2 hours)

**Goal.** Understand how the model is trained and tested without peeking at the future.

**Open.**
- `model/notebooks/02_train_and_test.ipynb`
- Glossary: "rolling origin", "embargo", "logit", "overfitting", "ROC-AUC", "PR-AUC", "base rate"

**Do.**
1. Run notebook 02.
2. Find where the notebook chooses the training years and the test year. Write down, for one test year, which years
   it trains on and which year it leaves out (the embargo). If the notebook lets you change the test year, do so and re-run.
3. Compare the logit with the other engines, if the notebook shows them. The example data give made-up numbers, so ask
   which differences you would trust on real data and why.
4. Read the module description at the top of `model/src/tcf_credit/evaluate.py`.

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
1. Run notebook 03. Find the flag line and the counts of false alarms and misses. If the notebook lets you move the line
   (for example from the top 10% to the top 5% or 20%), do so and watch how both counts change.
2. Find the notebook's comparison of the actual share of downgrades with the average predicted probability for each year.
   In the lecture's data, 2020 had the largest gap (actual 29%, predicted 14%); 2018 and 2024 also differed by more than 11 points, the other way (see RESULTS.md).
3. Read RESULTS.md. For each number, say aloud what it means and what it does not show.
4. Read LITERATURE.md. Write down two reasons why our AUC and a paper's AUC cannot be compared directly.

**Self-check.**
- What is the flag line, and why is it set from an earlier year's scores?
- If you flag more companies, what happens to misses and to false alarms?
- In 2020 the model ranked firms well but missed the yearly level. What does that say about reading the probability
  as a ranking?

---

## Session 4: the fly brain (estimate: about 1.5 hours)

**Goal.** See what a fixed, brain-shaped network can and cannot add.

**Open.**
- `model/notebooks/04_fly_brain.ipynb`
- `model/FLY-DATA.md` (the two public connectome files)
- Glossary: "connectome", "Kenyon cell", "readout", "shuffled control"

**Do.**
1. Run notebook 04 on the example data.
2. Find where the wiring is fixed and where learning happens. Only the readout is trained.
3. Compare the real wiring with the shuffled wiring in the notebook. The lecture's finding (see RESULTS.md) was no
   consistent edge for the real wiring; on example data, do not expect any pattern.

**Self-check.**
- Why is the shuffled control needed?
- If real and shuffled wiring score the same, what is the wiring *not* adding?
- Name one reason a result like this does not prove that the fly brain "knows" nothing about credit.

---

## Session 5: the agent, offline (estimate: about 1.5 hours)

**Goal.** Understand the division of work between the AI and the code, and see a note without using the internet.

The agent alone is written for Python 3.10 or newer; it was run only on Python 3.14.

**Open.**
- `agent/README.md`
- `agent/notebooks/agent_tutorial.ipynb`
- `agent/skills/credit-watch/SKILL.md` (the instructions the AI gets)
- Glossary: "AI agent", "skill", "prompt", "offline mode", "8-K", "CIK", "EDGAR", "SEDAR+"

**Do.**
1. Read the agent README up to the "How the checks work" section.
2. Run the tutorial notebook. It works in offline mode, on the saved copies of filings that come with the agent.
3. Read the checks (C1 to C4) in the agent README. Pick one and, using the notebook, find what that check protects
   against.
4. Run the agent tests: `cd agent`, then `python3 -m unittest discover -s tests`.

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
1. Give the SEC a contact: your own name and e-mail address, as the agent README describes. Do not share it or save
   it in a file you publish.
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

- **Rebuild on public data.** Follow [DATA-GUIDE.md](DATA-GUIDE.md), way 2. That route has not been run from start to end, and the script that converts the Philadelphia Fed economy files is missing. Expect results to differ from the lecture
  and think about why (for example, free price histories often omit companies that stopped trading; this was not tested).
- **Add an input.** Pick one idea (for example, a change in interest coverage over two years). Add it as a column,
  re-run the test, and report whether the AUC moved by more than the year-to-year spread.
- **Try another horizon.** Predict a downgrade within 6 months or 24 months. Remember that a short and a long horizon are different questions, so their scores are not comparable;
  see LITERATURE.md.
- **Change the flag line.** Choose the share to flag by the cost of a miss against the cost of a false alarm.
- **Test the agent.** Give it a firm with unusual wording and see what it misses.
