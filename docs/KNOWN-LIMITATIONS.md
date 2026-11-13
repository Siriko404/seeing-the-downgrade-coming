# Known limitations

A tool you understand is safer than a tool you trust. This page lists what the model and the agent cannot do, so you
know where to check. If a word is new, see the [glossary](GLOSSARY.md).

## The model

1. **Exact results need licensed data.** The lecture's market inputs come from CRSP stock prices through WRDS (to match each company to its stock, the code used two WRDS identifier tables: the Compustat company file, only its gvkey and CIK columns, and the CRSP/Compustat Merged link table;
   no Compustat financial data is used, and the accounting numbers are from SEC filings). Without
   that access, you can study the code on made-up data (the numbers mean nothing) or rebuild on public data (the numbers
   will differ). See [DATA-GUIDE.md](DATA-GUIDE.md).
2. **Free data may have survivorship bias.** Free price histories such as Yahoo's tend to omit companies that stopped trading. These may include
   companies that got into trouble, so a model built on free prices could look better than it is. This was not tested here.
3. **The yearly level can shift.** In 2020 about 29% of reports were followed by a downgrade, but the average predicted
   probability was about 14%. The model ranks companies well within a year and cannot tell you the level of the year. Read a
   probability as a ranking.
4. **Narrow scope.** The model scores only US companies that file a 10-K with the SEC and have an S&P rating. It does not
   score Canadian or other foreign companies that do not file a 10-K, private companies, ETFs, or companies S&P does not
   rate. Financials and utilities are left out.
   The rule is in `model/src/tcf_credit/build_panel.py`.
5. **It predicts downgrades by S&P only.** A downgrade to default counts as a downgrade (the SEC's code DG includes classifying the company as in default); if the rating is withdrawn first, the report is dropped. It does not predict other agencies' actions or stock returns.
6. **It uses the past.** What explained downgrades in 2016 to 2024 may not explain the next ones. A shock the inputs cannot
   see, such as a sudden pandemic, may not be foreseen.
7. **The rating state is part of the input.** The model leans on the agency's own rating, outlook and watch. So it
   is not independent of the agency's view.
8. **Not run from start to end on public data.** The public route in the data guide is an outline, and the script that converts the Philadelphia Fed economy files is missing from the package.
9. **Nothing here is investment advice.**

## The agent (`credit-watch`)

These are limits of the agent as written. For the full description, see `agent/README.md`.

1. **A Canadian company that is not in the agent's company lists.** If you give such a company as `TICKER=manual`, the
   agent takes the ticker as the company name. The note may then say "No long-term grade of the company itself" although
   grades are listed (our reading of the code, not a logged run). Check the
   company name the agent prints first.
2. **Long rating paragraphs are cut.** Text paragraphs are cut at 4,000 characters (rating tables at 60 rows or 8,000 characters). A longer
   rating paragraph loses its end, and the note may then list a gap. If the note lists a gap for a company you know is
   rated, read the filing yourself.
3. **Dates of undated actions can be off.** If a rating action has no date in the text, the gap window starts at the
   beginning of the read window (or at the last dated row), not at the year of the action itself.
4. **Actions with no named agency are missed.** A sentence such as "The major credit rating agencies downgraded our
   ratings" has no agency name, so it is not listed. The note can then say "no rating" when there was a downgrade.
5. **One column has a misleading name.** The field `what_is_rated` is really the row type. For an outlook or watch row it
   holds "outlook".
6. **Canadian companies that file only on SEDAR+.** The tool does not download from SEDAR+. The agent prints a link, and you
   download the file and give its path. The filing date is read from the file's first pages (two PDF pages, or the first 6,000 characters of other files), which may not be the date on
   SEDAR+.
7. **No model score in the public package.** The model's code is in `model/`, but the trained model, its licensed training data and its scores are not included (the
   slides keep one classroom example), so the note says the company is not scored. The agent works without it.
8. **Long notes.** A company with many rating actions can produce a long note. It is
   long, so read it line by line.
9. **The AI reads the text rows.** Table cells are matched by code. A text row was read by an AI; code checks the quote and
   some details, and the row is marked "AI-read text: verify quote". The check is only as good as your reading of the
   source.
10. **SEC filings only, and uneven.** Some companies never state their ratings in a filing, and the note says so.
11. **It needs an AI agent to run.** An AI agent may need an account or credits (a paid plan, API credits or a free model). The Python tools alone run free.
