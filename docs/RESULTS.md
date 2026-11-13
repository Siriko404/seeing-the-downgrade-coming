# Results from the lecture

These are the lecture's results. The accounting inputs came from SEC filings as first filed; the market inputs came from
licensed CRSP stock prices (to match companies to their stock the code used two identifier tables,
the Compustat company file's gvkey and CIK columns and the CRSP/Compustat Merged link table; no Compustat financial data
is used). They cannot be reproduced exactly from the example data or from free data (see
[DATA-GUIDE.md](DATA-GUIDE.md)). Only totals are given here: no company's data or score is shown. The one exception is a
single classroom example on the slides, described in the [README](../README.md).

If a word is new, see the [glossary](GLOSSARY.md).

## The test

- **Test years:** 2016 to 2024, one year at a time. Each year the model was trained only on earlier years, leaving a gap
  of one year (rolling origin with an embargo), so it never saw the year it was tested on.
- **Size:** 6,380 annual reports (10-Ks) of US companies with an S&P rating.
- **Downgrades:** 862 of them (13.5%) were followed by an S&P downgrade within 12 months.

In plain words: about 1 report in 7 is followed by a downgrade within a year. A model that gives every company the same
probability, 13.5%, has the right overall rate and no skill at all.

## The numbers

| Result | Number | In plain words |
|---|---|---|
| Logit, ROC-AUC | 0.802 | Pick one report that was followed by a downgrade and one that was not. The logit gave the first a higher score in about 80% of such pairs. 0.5 would be a coin flip. |
| Logit, PR-AUC | 0.494 | A harder score when downgrades are rare. A model with no skill scores about the share of downgrades, 0.135. |
| Other single engines that are not fly models (gradient boosting, boosting with direction rules, random forest, XGBoost, neural network), ROC-AUC | 0.787 to 0.795 | All scored slightly below the logit's 0.802. Averages of several models that include the logit scored up to 0.809; the logit-boosting average's edge over the logit (+0.007) is the only interval above zero. |
| S&P rating state alone, ROC-AUC | 0.757 | The company's rating, outlook and watch status, with no financial ratios, no market data and no economy. It already does most of the work. |
| Fly brain models, ROC-AUC | 0.759 to 0.807 | Networks with fixed fruit-fly wiring and a trained readout. The top value, 0.807, is a whole-brain model with shuffled wiring. Every fly model's PR-AUC (0.369 to 0.476) is below the logit's 0.494. Across the three seeds, one fly model's AUC varied by about 0.025 to 0.036. |
| Real fly wiring against shuffled wiring | no consistent edge | Scrambling the fly's connections did not lower the score in a consistent way. There is no sign that the real wiring pattern helped. |
| Flag line: the score that marked the top 10% of an earlier year's scores | caught 407 of 862 downgrades, 8.7% false alarms | The flag line was set from an earlier year's scores and then held fixed. Applied to the test years it flagged 888 of 6,380 reports (13.9%) and caught 407 of the 862 downgrades; the others were missed. Among the 5,518 reports with no downgrade, 481 (8.7%) were flagged anyway. Flagging the top 10% within each test year instead (642 reports, 10.06%) caught 353, with 5.2% false alarms. |

The logit was named the main model on 4 November 2026, before the extra models (XGBoost, random forest, neural network,
boosting with direction rules, averages and the fly models) were run. Its set of inputs was extended later, so the logit
reported here is not exactly the one named that day. The settings of every engine were chosen only on years before the
first test year.

## The yearly level

Within each year the model ranked companies well. It missed the yearly *level* in 2020: about 29% of reports were
actually followed by a downgrade, while the model's average predicted probability was about 14%. In most other years the
average prediction was above the actual rate (2018: 23.2% predicted, 10.7% actual; 2024: 21.6% predicted, 9.7% actual).
A possible reason for 2020 is that it brought an economy-wide shock (the pandemic) that no input known at the filing
date could show. This is our reading, not a tested finding.

Read the probabilities as a **ranking** (who is riskier than whom), not as exact chances. See "calibration" in the
glossary.

## What these results do not show

- **They are not investment advice** and do not say any company will be downgraded. A flag means "among the riskier
  group", not "will be downgraded".
- **A better AUC is not a better trade.** The results listed here are about downgrades, not stock returns or profit. The
  lecture also checked the later stock returns of flagged firms in a separate analysis (model step 9); that is not a
  trading strategy.
- **The differences between engines are small.** On these numbers no engine is clearly better than the logit, and the
  fly brain's real wiring shows no advantage. That does not prove that the fly brain, or any one engine, is useless.
- **The score is for a particular sample.** US companies with a 10-K and an S&P rating, excluding financials and
  utilities, 2016 to 2024. It says nothing about other countries, other agencies or private companies.
- **Free data will give different numbers** (for example, free price histories often omit companies that stopped
  trading). The public route has not been run, so the size of any difference is unknown.
- **The flag line is a choice.** A line set from the top 10% of an earlier year's scores gives 407 caught and 8.7% false
  alarms (888 of 6,380 reports flagged, 13.9%); the top 10% of each test year (642 reports) gives 353 caught and 5.2%.
  Another share would give other counts. The right share depends on what a miss costs against what a false alarm costs.
- **One period.** Nine test years that include a pandemic year are not a guarantee about the next nine.
- **Rating state is partly the answer.** The rating, outlook and watch are the agency's own opinion, so a model that
  relies on them is partly relying on the agency's view. Our reading, not tested: that is part of why the state alone is
  already at 0.757.

See [KNOWN-LIMITATIONS.md](KNOWN-LIMITATIONS.md) and [LITERATURE.md](LITERATURE.md).
