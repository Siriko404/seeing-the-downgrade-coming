# AGENTS.md

Instructions for an AI coding agent that works in this repository. Follow them in order.

## 1. What this repository is

1. Teaching material for a first-year finance student: a credit-downgrade model in `model/` and the
   `credit-watch` skill for AI agents in `agent/skills/credit-watch/`.
2. The model estimates the chance that S&P downgrades a US company within 12 months of its 10-K; the skill reads
   credit ratings from SEC filings and writes a short cited note.
3. It is not investment advice. Read `README.md` and `agent/README.md` when you need the full description.

## 2. If the user asks you to install it

1. **Get the files.** If you only have the link, clone
   `https://github.com/Siriko404/seeing-the-downgrade-coming.git` into the user's current project folder, or where
   the user says, then work inside the clone.
2. **Ask one question.** Ask the user for the name and e-mail address to give the SEC as its contact. The SEC asks
   every automated client to declare one. Do not invent a contact, use your own, or use a placeholder. If the user
   declines, install without a contact.
3. **Run the installer.** From the repository folder run `python3 install.py --check` (on Windows use `python`).
   Add `--contact "Name e-mail"` only if the user gave a contact. Before it starts, tell the user that the model
   part needs Python 3.12 or newer and downloads about 1.7 GB of packages. Do not replace the installer with your
   own steps. If a step fails, show the user its message and fix the cause, then run it again.
4. **Do not fetch the hand-download files.** Do not download the five rating-history ZIP files, the two
   Loughran-McDonald files, or the three FRED files that the student must save when FRED does not answer. The sites'
   terms forbid automated downloads or need a click-through; the student downloads these in a browser. Do not start
   the 30-minute data rebuild unless the user asks. Explain these steps instead; `docs/DATA-GUIDE.md` lists them.
5. **Report what happened.** Read the `INSTALL SUMMARY` block that the installer prints. If it reports a failure, do
   not say the install succeeded. Then give the user the explanation in section 3.

## 3. What to tell the user after installing

Adapt this script; keep it short (about 15 lines when spoken):

- Tell the user what was installed and where, using the paths in `INSTALL SUMMARY`.
- Tell the user to start a new agent session so the agent sees the skill.
- Then try `/credit-watch HON --offline`. It needs no network and no contact. The note is
  `credit-watch/run/note_HON.md`; the run also writes `credit-watch/run/ratings.md`.
- Say what the skill does in one sentence: the AI reads the filings, code checks every row, and code writes a
  cited note. It is not investment advice.
- To change the skill, edit `agent/skills/credit-watch/`, run `python3 install.py --skip-model`, then run the
  agent tests. Details are in `agent/MODIFYING.md`.
- The model is five notebooks in `model/notebooks/`. They read the real table `build/panel_v2.csv`, which the
  student builds once from free public data with
  `PYTHONPATH=model/src python -m tcf_credit.rebuild data build --route free`, or with their own WRDS account with
  `PYTHONPATH=model/src python -m tcf_credit.rebuild data build --route wrds --wrds-user YOUR_NAME`.
- The student must download these files by hand: five rating-history ZIP files, two Loughran-McDonald files, and
  three FRED files only if FRED does not answer the automatic download. `docs/DATA-GUIDE.md` gives the pages and
  file names.
- Read the limits in `docs/KNOWN-LIMITATIONS.md`. Nothing here is investment advice.

## 4. If the user asks you to run or change things here

1. Run the agent tests from the `agent/` folder: `python3 -m unittest discover -s tests`.
2. Run the model tests from the repository folder:
   `PYTHONPATH=model/src python3 -m unittest discover -s model/tests`. On Windows use `python` and set
   `$env:PYTHONPATH="model/src"` first.
3. Never commit `build/`, `data/` or `credit-watch/`.
4. Keep licensed data on the user's computer; never paste it into a chat, a public place or a commit.
5. Inside a credit-watch run, obey `agent/skills/credit-watch/SKILL.md`.

## 5. Do not

- Invent a contact, or use your own or a placeholder.
- Fetch the hand-download files, or work around a site's bot block.
- Fetch SEDAR+; the student downloads those filings.
- Give buy, sell or hold advice.
- Say a step passed without seeing its output.
