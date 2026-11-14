# Known limitations

A tool you understand is safer than a tool you trust. This page lists what the model and the agent cannot do, so you
know where to check. If a word is new, see the [glossary](GLOSSARY.md).

## The model

1. **Exact results need licensed data.** The lecture's market inputs come from CRSP stock prices through WRDS (to match
   each company to its stock, the code used two WRDS identifier tables:
   the Compustat company file, only its gvkey and CIK columns, and the CRSP/Compustat Merged link table; no Compustat
   financial data is used, and the accounting numbers are from SEC filings). Without that access, rebuild on public
   data (the numbers will differ); with your own WRDS account, use the lecture's route. See
   [DATA-GUIDE.md](DATA-GUIDE.md).
2. **Free data may have survivorship bias.** Free price histories such as Yahoo's tend to omit companies that stopped
   trading. These may include companies that got into trouble, so a model built on free prices could look better than it
   is. The one run of 13 November 2026 scored lower than the lecture (0.759 against 0.802; see item 8), and one run
   cannot tell how much of that comes from the missing companies.
3. **The yearly level can shift.** In 2020 about 29% of reports were followed by a downgrade, but the average predicted
   probability was about 14%. The model ranks companies well within a year and cannot tell you the level of the year.
   Read a probability as a ranking.
4. **Narrow scope.** The model scores only US companies that file a 10-K with the SEC and have an S&P rating. It does
   not score Canadian or other foreign companies that do not file a 10-K, private companies, ETFs, or companies S&P does
   not rate. Financials and utilities are left out. The rule is in `model/src/tcf_credit/build_panel.py`.
5. **It predicts downgrades by S&P only.** A downgrade to default counts as a downgrade (the SEC's code DG includes
   classifying the company as in default); if the rating is withdrawn first, the report is dropped. It does not predict
   other agencies' actions or stock returns.
6. **It uses the past.** What explained downgrades in 2016 to 2024 may not explain the next ones. A shock the inputs
   cannot see, such as a sudden pandemic, may not be foreseen.
7. **The rating state is part of the input.** The model leans on the agency's own rating, outlook and watch. So it is
   not independent of the agency's view.
8. **Public data gives different numbers.** The public route was run from start to end on 13 November 2026: 4,902
   test reports with 515 downgrades and logit ROC-AUC 0.759, against 6,380 reports, 862 downgrades and 0.802 in the
   lecture. Fewer reports are tested because free prices are missing for many companies, often ones that stopped
   trading. Only one run was made.
9. **Notebooks 1 to 4 were not run on a free-route table.** They were run on the lecture's own table (the licensed
   route), where all five notebooks ran and gave the published numbers. Notebook 5 was also run on the table that the
   free route built on 13 November 2026. Notebooks 1 to 4 were not run on that free-route table, so a cell may fail
   there; if one does, the message names the cell.
10. **The WRDS sign-in was never run against WRDS.** No WRDS account was available. On the lecture's saved data the
    package's code rebuilds the lecture's table and results exactly, but the download step (`fetch_wrds.py`) was run
    only in the automatic tests, with a test stand-in for the connection.
11. **Nobody has followed the README from zero on a clean machine since it was rewritten** (13 November 2026). The
    parts were checked one by one on Linux with Python 3.14 and 3.13: the install, the tests, the rebuild command and
    the notebooks. Windows and macOS were not tried.
12. **Nothing here is investment advice.**

## The agent (`credit-watch`)

These limits come from live runs of the agent and from reading its code. Keep them in mind when you read a note.

1. **Canadian firms that file only in Canada.** The tool does not download from SEDAR+; you download the file yourself
   and give the tool its path: `fetch.py TICKER=manual --file <path> --filed <YYYY-MM-DD>`. If you leave out `--filed`,
   the filing date is read from the file's first two pages (a PDF) or its first 6,000 characters (other files), which is
   not always the date it was filed.
2. **A Canadian firm that is not in `data/canada.csv`.** That file is a short list of Canada-only firms with a direct
   filing link. For any other Canadian firm given as `TICKER=manual`, the tool uses the ticker as the company name: a
   live run on 12 November 2026 for Stella-Jones as `SJ=manual` gave a note titled "SJ (SJ)". By our reading of the code
   (not shown in a saved run), the note may also say "No long-term grade of the company itself" although grades are
   listed, because the rated company's name does not match the ticker. The note's model-score line says the model covers
   only S&P-rated US 10-K filers.
3. **Long passages are cut.** A rating paragraph is cut at 4,000 characters, a rating table at 60 rows or 8,000
   characters. The note lists a gap for each cut. Read that part of the filing yourself.
4. **Dates of undated actions.** When a rating action has no full date, the tool looks from the date of the last earlier
   rating of the same rated company and agency (or from the start of the period read) up to the filing that reported it;
   if the sentence names a month and year, only that month is searched. A gap may therefore look longer or shorter than
   it is.
5. **Actions that name no agency give no rating row.** A sentence such as "The major credit rating agencies downgraded
   our ratings" is listed as a gap (type G-a, explained in agent/README.md under "How the checks work"; at most 5 per
   firm, main filings only, not exhibits) and the note points to it. But the tool cannot make a rating row (one agency,
   one rated company, one rated item) from it. Only sentences that match the code's patterns are found (under 400
   characters, with no word such as "could", "may" or "if" before the action word). Read the filing text when a note
   looks too empty.
6. **A column name to know.** The field `what_is_rated` (in `rows.json`, the file the AI writes) holds the label of the
   rated item as the filing words it, such as "Long-term" or "Commercial paper"; for an outlook or watch rating row it
   holds "outlook".
7. **No model score here.** The model's code is in `model/`, but the trained model, its licensed training data and its
   scores are not included (the slides keep one classroom example), so the note says the company is not scored. The
   ratings, checks and gaps work without it.
8. **Long notes.** A firm with many rating actions gets a longer note than the saved examples. Read it one line at a
   time.
9. **The AI may not stop where it should.** In one live run, the AI ran the lookup twice more with other options before
   it showed the stop message to the user. The code does not depend on this; read what the AI ran.
10. **PDF text is copied as extracted.** A PDF can give broken words (a live run showed "I ssuer Rating"); quotes keep
    them.
11. **The one-step install was run live only with opencode.** On 13 November 2026 opencode (DeepSeek 4.1 Flash)
    installed the package from an empty home folder: once from a local copy with the full model install (all three
    checks passed, about 6 minutes) and once from the GitHub link without the model packages (about 1.5 minutes). With
    Claude Code and Codex the installer was **not** run live; for those two only the unit tests of `install.py` ran, so
    their skill folders (`~/.claude/skills/`, `~/.codex/skills/`) come from the products' documentation.

Also:

- **SEC filings only.** Some companies never state their ratings in filings; the note says so (gap G-c).
- **The AI is a reader, not an authority.** Tables are matched by code; sentences are marked "AI-read text: verify
  quote" for you to check against the filing.
- **A rating found in a filing is old news.** For current ratings, go to the agencies and to the company's
  investor-relations page.

Full text: [agent/README.md](../agent/README.md), Known limitations.
