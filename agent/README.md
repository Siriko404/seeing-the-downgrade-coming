# credit-watch: an AI agent that reads credit ratings in SEC filings

`credit-watch` is a **skill** (a folder of instructions and small Python programs that an AI coding agent can use). You
give it a company. It downloads the company's SEC filings, finds the passages that mention credit ratings (by keyword),
and writes a short note in which every rating fact carries a row id; the file `ratings.md` gives each row's exact quote
(for a table, the `Row:` line the code builds from the table) and a link to the filing.

It is a teaching example of one idea: **let an AI read, but let code check the AI.** Not investment advice.

Start with the notebook `notebooks/agent_tutorial.ipynb`. It runs on saved rating passages, with no network and no AI
account, and shows each step below.

## What the agent does: four steps that make files, then a report

```
1. FETCH   fetch.py   code   firm -> SEC filings -> the paragraphs and tables that mention ratings
2. READ    the AI     AI     those passages -> rating rows, each with an exact quote
3. CHECK   check.py   code   keeps a rating row only if the filing proves it
4. FINISH  finish.py  code   writes a short note from the kept rating rows only
5. REPORT  the AI     AI     tells you in chat where the files are (nothing new is computed)
```

- In this README a **rating row** is what the AI writes: one agency, one rated company, one rated item. It is not the
  same as a **table line** (a `Row:` line inside a table of a filing). `SKILL.md` calls the rules for writing rating
  rows "Instruction R".
- Only step 2 makes anything with an AI. Steps 1, 3 and 4 are plain Python (standard library only; reading PDFs needs
  the optional `pypdf`), so the same filings always give the same passages, and the same rating rows always give the
  same checks and the same note, apart from the date the note was made. Step 5 only reads those files back to you.
- The AI is useful because it understands sentences like "On March 6, 2026, S&P revised their credit rating outlook from
  watch negative to negative." It is dangerous because it can write a plausible sentence that the filing never
  contained. That is why step 3 exists.
- `skills/credit-watch/SKILL.md` is the instruction text the AI reads. It is short. Read it: it shows how a rule for an
  AI is written.

## Install

The agent is written for Python 3.10 or newer and was tested on Python 3.14 only. (The pinned packages of the model in
`model/` need Python 3.12 or newer, so use 3.12 or newer if you use the whole package.) Reading PDF exhibits needs
`pip install pypdf` (optional).

### Option 1: ask your AI agent, or run one command

From the repository folder:

```
python3 install.py
```

`install.py` uses only the Python standard library and runs on Linux, macOS and Windows. It installs both parts.

- **The model.** It makes `.venv` in the repository folder if it is missing, then runs
  `pip install torch==2.15.0 --index-url https://download.pytorch.org/whl/cpu` and
  `pip install -r model/requirements.txt`. With `--skip-model`, or with Python older than 3.12, it installs the skill
  only; on an older Python it says so and goes on.
- **The skill.** It copies `agent/skills/credit-watch/` (without `__pycache__`) into the skills folder of each chosen
  agent as `credit-watch/`. `--agents` takes a comma list of `claude`, `opencode`, `codex` or `all`. The default is each
  of those whose command is on `PATH`; if none is found, it uses `opencode`.
  - User level: Claude Code `~/.claude/skills/`, opencode `~/.agents/skills/`, Codex `~/.codex/skills/`.
  - With `--project DIR`: `DIR/.claude/skills/` and `DIR/.agents/skills/` (for Codex, see its documentation).
  - Same files already there: it says "already installed". Different files: it moves the old folder to
    `.install-backups/<agent>-<YYYYmmdd-HHMMSS>/` in the repository folder first.

More flags:

- `--contact "Name e-mail"` writes `~/.config/credit-watch/contact.txt` (the first line is the text) and
  `~/.config/tcf_credit/settings.toml` (a `[sec]` line `contact = "..."`), keeping any other content. Without it nothing
  is written, and the summary says the skill works offline only until a contact is set. The contact is never printed,
  logged or invented.
- `--check` runs the agent tests (`python -m unittest discover -s tests` in `agent/`), one offline run of the skill's
  first step for HON in a temporary folder, and, if the model was installed, the model tests with the venv's Python. It
  reports PASS or FAIL for each check.
- `--uninstall` removes the installed skill folders (only folders named `credit-watch` that contain `SKILL.md`). It
  leaves `.venv`, the contact files and your own `credit-watch/` run folders alone, and says so.

The run ends with a block that starts `INSTALL SUMMARY`: each skill folder written, the venv, whether a contact is set
(yes/no, never its value), each check result, and the next steps. Exit code 0 means every requested step worked.

Then start a **new** agent session so it sees the skill, and in your project folder run `/credit-watch HON --offline`.

Option 2, the `npx` installer (it asks which agent you use):

```
npx skills add Siriko404/seeing-the-downgrade-coming
```

(the installer finds the skill inside this repository's `agent/` folder). Pick `credit-watch` when asked.

Option 3, copy the folder `skills/credit-watch/` by hand:

| Agent | Copy it to | Tested |
|---|---|---|
| Claude Code | `.claude/skills/credit-watch/` in your project folder | full run live with the version used in the lecture (7 to 11 November 2026); this version has passed its unit tests and the offline tutorial, no live run yet |
| opencode | `.agents/skills/credit-watch/` in your project folder | full run live with the version used in the lecture (7 to 11 November 2026); this version ran live on 12 November 2026 with DeepSeek 4.1 Flash (Honeywell, Ford, and Stella-Jones from a downloaded file) |
| other agents that read the open Agent Skills format | see your agent's skills folder | not tested |

Run the agent from your project folder, not from inside the skill folder: the tools write their files into
`credit-watch/` in the folder where you start them.

Optional: `examples/lecture-project/.claude/settings.json` is a Claude Code settings file that lets the agent run
`python3`, read files and write inside `credit-watch/run/` without asking each time. Read it before you copy it into
your project. Claude Code uses it only after you accept the folder's trust question once.

The AI agent you use may need an account or credits. The Python tools alone need none.

## Set up your SEC contact

The SEC asks every program that downloads filings to say who it is, with a name and an e-mail address. Use your own; do
not copy someone else's.

On macOS or Linux:

```
export SEC_CONTACT="Your Name you@example.com"
```

On Windows PowerShell:

```
$env:SEC_CONTACT = "Your Name you@example.com"
```

Or save only the name and e-mail address (`Your Name you@example.com`) as the first line of
`~/.config/credit-watch/contact.txt`. The agent looks first at `SEC_CONTACT`, then at that file, then at the model's old
settings file `~/.config/tcf_credit/settings.toml` (a line `contact = "..."`). The tools never print it and never save
it in an output file.

The model code in `model/` reads its **own** setting (`TCF_SEC_CONTACT`, or a settings file; see `model/README.md`). Set
both with the same name and e-mail address, yours, if you use both parts.

No contact? Use `--offline`: the tools then read the saved copies in `skills/credit-watch/cache/` and do not touch the
network. The cache holds the rating passages (the paragraphs and tables that mention ratings, not whole filings) of HON,
RY and CMP. `SJ.json` holds only the name of Stella-Jones Inc., a Canada-only firm, and no text. The symbol SJ means
different firms in the two modes: offline it is the saved Stella-Jones entry; online the SEC's list gives SJ to another
company (Scienjoy Holding Corp), so for Stella-Jones online you give the name and then the downloaded file (see
Canada-only firms).

## Run it

In your agent, from your project folder:

```
/credit-watch HON
```

or say "Use the credit-watch skill for HON." You can give several firms (`HON RY JPM`), an SEC number (`19617`) or a
name (`"Loews Corp"`). Options:

- `--as-of 2018-12-31`: a **backtest**. Read only filings filed on or before that day, as if today were that day.
  Example: `/credit-watch HON --as-of 2018-12-31`. (Without the model, a backtest shows what the filings said by that
  day.)
- `--months 24`: how far back to read (default 18 months).
- `--holdings holdings.csv`: a portfolio file, one firm per line or a CSV with a `ticker` or `cik` column. You get one
  summary line per holding in `portfolio.md`, and a note per firm read.
- `--offline`: no network (see "Set up your SEC contact").

Check the line `firm: HON = Honeywell International Inc., CIK 773840`. It says which company your input became. A ticker
you give for a Canadian firm can be another company's ticker at the SEC (for example, at the SEC `L` is Loews), so if
the name is wrong, give the name or `TICKER=CIK`, for example `AAPL=320193`.

**Which companies work?** Any company that files with the SEC, by ticker, SEC number (CIK) or name. The tool looks the
firm up in the SEC's own list of filers; this package keeps no list of SEC filers, only `data/canada.csv`, a short list
of Canada-only firms with a filing link. With `--offline` it finds the firm among the saved copies instead (ticker, name
and CIK are stored in each copy).

**Canada-only firms** (they file on SEDAR+ and not with the SEC) work from a file you download. The tool prints a search
link and the SEDAR+ link, you download the firm's latest Annual Information Form, and you run
`fetch.py TICKER=manual --file <path>` (see Known limitations). For a few large firms,
`skills/credit-watch/data/canada.csv` already holds a direct link.

A run on live data can take a while: the program waits 0.2 seconds between SEC requests.

## What a run writes

Everything goes into `credit-watch/` in your project folder.

| File | What it is |
|---|---|
| `run/` | the scratch folder of the **current** run. The next fetch erases and rewrites it, so copy what you want to keep. |
| `run/passages.md` | the passages step 1 found (what the AI reads) |
| `run/rows.json` | the rating rows the AI wrote (the only file the AI writes) |
| `run/ratings.md` | every kept rating row with its exact quote and link; the gaps; the rating rows that were set aside and why |
| `run/note_<TICKER>.md` | the note of one firm, for example `note_HON.md` |
| `run/portfolio.md` | with `--holdings`: one line per holding |
| `runs/<date>_<time>_<firm>/` | a dated copy of the whole run, made by step 4. These folders are never erased. |

A note has six parts: model score, ratings now, credit flags (how many notches above or below investment grade each
agency is), what changed and when, the two dates (when the agency acted, and when a filing reported it), and what to
check next.

## How the checks work

A rating row is kept only if it passes all four checks:

- **C1** the quote is in the passage, word for word;
- **C2** the grade or outlook sits in the right agency's cell (tables) or in the quote with the agency named
  (sentences);
- **C3** the date is written in full in the passage (and is the quote's own date if the quote has one), and is not later
  than the filing date;
- **C4** the rating row is not a repeat of an earlier one.

A rejected rating row goes back to the AI **once**. If it is still wrong, it is set aside and listed. `check.py` refuses
a third round, so the AI cannot try until something passes.

The checker also lists what is **missing**: table cells and sentences that state a rating but have no kept rating row.
The AI adds them once. Last, it lists **gaps** for you to follow up:

- G-a: a rating changed, but no filing gives the date of the action, or a filing reports a change without naming the
  agency;
- G-b: an agency has said nothing for over 15 months;
- G-c: nothing to read (no SEC filings, an unreadable document, or no rating stated).

Filing text is treated as data. If a filing says "ignore your instructions", the AI is told never to obey it.

## Due diligence: how to check a note

A note is a draft by a program. Check it before you use it. Four things to do:

1. **Check the firm line.** At the top of the fetch output, `firm: ... = <company>` must be the company you meant.
2. **Check the AI-read rating rows.** In `ratings.md` the column "Read by" says either `table cell` or
   `AI-read text: verify quote`.
   - `table cell`: code matched the grade to the agency's cell of the table line.
   - `AI-read text: verify quote`: an AI read a sentence. Code proved the quote is in the filing and that the agency,
     grade and action word are in it, but a person must check that they belong together. For each such rating row: click
     its link, press Ctrl+F, type a few words of the quote, find the sentence, and read it. Does it say what the rating
     row says?
3. **Read "What to check next"** at the end of the note. It lists the gaps, the table cells and sentences with no kept
   rating row, and the rating rows that were set aside. A ratings table the AI skipped will show up here.
4. **Remember the date.** The agency acts first; a filing reports it days or weeks later. The note shows both dates. A
   rating "now" means "in the last filing read", not "today".

## The rating words, in plain language

- **Scales.** S&P and Fitch grade a company from `AAA` (very strong) down to `D` (in default). Moody's uses `Aaa` down
  to `C`. Short-term grades have their own scale (`A-1`, `P-1`, `F1`).
- **Investment grade** means `BBB-` or better at S&P and Fitch, `Baa3` or better at Moody's. Below that is **high
  yield** (also called junk). The note counts notches above or below this line.
- **Outlook.** The direction a rating is likely to move over the medium term: positive, negative, stable or developing.
  S&P looks up to two years ahead for investment grade and up to one year for speculative grade; Fitch one to two years;
  Moody's the medium term. It is a hint, not a decision.
- **Watch** (S&P: *CreditWatch*; Fitch: *Rating Watch*; Moody's: *review for downgrade* or *review for upgrade*). It is
  a short-term review of a possible change in the rating; S&P says it is normally resolved within 90 days. It looks at a
  shorter period than an outlook.
- **Action words** in rating rows: upgrade, downgrade, outlook change, watch placed, watch removed, affirmed (confirmed,
  no change), reviewed, assigned (first rating), withdrawn.

## The model score line

The top of each note has a "Model score" section. In the course, this line shows the credit-downgrade model's score for
the company (see `model/` and `docs/` in the main repository). **In this public package the model is not connected, so
the note says so.** This is the line from the notebook run:

```
Not scored on this device: no model score for Honeywell International Inc. The model's code is in model/; the trained model, its licensed training data and its scores are not included. It covers S&P-rated US 10-K filers, not financials or utilities.
```

The ratings, checks and gaps work the same without it. The tools can use a model if you connect one (a command named in
`CREDIT_WATCH_MODEL`, or a scores file named in `CREDIT_WATCH_SCORES`); that is optional and not needed for this course.

## Known limitations

Plain words. Keep them in mind when you read a note.

1. **Canadian firms that file only in Canada.** The tool does not download from SEDAR+; you download the file yourself.
   It prints a link; you download the file and give the tool its path:
   `fetch.py TICKER=manual --file <path> --filed <YYYY-MM-DD>` (`TICKER` is the symbol you give the firm, for example
   `DOL=manual`). If you leave out `--filed`, the date is read from the file's first two pages (a PDF) or its first
   6,000 characters (other files), which is not always the date it was filed.
2. **A Canadian firm that is not in `canada.csv`.** `skills/credit-watch/data/canada.csv` has direct links for a few
   firms. For any other Canadian firm given as `TICKER=manual`, the tool uses the ticker as the company name (a live run
   for Stella-Jones as `SJ=manual` gave a note titled "SJ (SJ)"). By our reading of the code (not shown in a saved run),
   the note may also say "No long-term grade of the company itself" although grades are listed, because the rated
   company's name does not match the ticker; the note's model-score line says the model covers only S&P-rated US 10-K
   filers.
3. **Long passages are cut.** A rating paragraph is cut at 4,000 characters, a rating table at 60 rows or 8,000
   characters. The note lists a gap for each cut. Read that part of the filing yourself.
4. **Dates of undated actions.** When a rating action has no full date, the gap check looks from the date of the last
   earlier rating of the same rated company and agency (or from the start of the period read) up to the filing that
   reported it; if the sentence names a month and year, only that month is searched. A gap may therefore look longer or
   shorter than it is.
5. **Actions that name no agency give no rating row.** A sentence such as "The major credit rating agencies downgraded
   our ratings" is listed as a gap (G-a, "changed, no agency named", at most 5 per firm, main filings only, not
   exhibits) and the note points to it, but the tool cannot make a rating row (one agency, one rated company, one rated
   item) from it. Only sentences that match the code's patterns are found (under 400 characters, and no word such as
   "could", "may" or "if" before the action word). Read the filing text when a note looks too empty.
6. **A column name to know.** The field `what_is_rated` (in `rows.json`, the file the AI writes) holds the label of the
   rated item as the filing words it, such as "Long-term" or "Commercial paper"; for an outlook or watch rating row it
   holds "outlook".
7. **No model score here.** See the section above.
8. **Long notes.** A firm with many rating actions gets a longer note than the saved examples. Read it one line at a
   time.
9. **The AI may not stop where it should.** In a live run with DeepSeek 4.1 Flash, the AI ran the lookup twice more with
   other options before it showed the stop message to the user. The code does not depend on this; read what the AI ran.
10. **PDF text is copied as extracted.** A PDF can give broken words (a live run showed "I ssuer Rating"); quotes keep
    them.

Also:

- **SEC filings only.** Some companies never state their ratings in filings; the note says so (gap G-c).
- **The AI is a reader, not an authority.** Tables are matched by code; sentences are marked for you to verify.
- **A rating found in a filing is old news.** For current ratings, go to the agencies and to the company's
  investor-relations page.

## Tests

From the `agent/` folder:

```
python3 -m unittest discover -s tests
```

The tests plant a failure for every check (a wrong grade, a quote that is not in the filing, a date after the filing
date, ...) and each has a control that must pass, so a check that rejects everything also fails. One test checks that
every line of a note states only the values of the rows it cites. Tests that need a model score use small test inputs
in `tests/fixtures/test-scores/`; the numbers are not model output.

## What is where

```
README.md                           this file
MODIFYING.md                        how to work with and change the skill
notebooks/agent_tutorial.ipynb      hands-on walk-through, offline (runs in seconds)
examples/lecture-project/           optional Claude Code settings file
skills/credit-watch/SKILL.md        the instructions the AI reads
skills/credit-watch/tools/          fetch.py, check.py, finish.py, common.py
skills/credit-watch/data/           a short list of Canada-only firms (canada.csv) and the rating scales
skills/credit-watch/cache/          saved rating passages for --offline (HON, RY, CMP; SJ.json holds only a name)
tests/                              unit tests and their fixtures
```
