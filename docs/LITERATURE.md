# Where the model stands among published work

Other researchers have built downgrade models. The table shows the ROC-AUC each paper reports, next to ours (see the
[glossary](GLOSSARY.md) for ROC-AUC). **Do not read it as a league table.** Every paper has its own companies, its own
years, its own question (how far ahead), and its own way of testing. The numbers were not produced head to head.

| Paper | Sample | Question | Test | Reported ROC-AUC |
|---|---|---|---|---|
| Malone, Smales & Liu (2026) | S&P ratings, North America, 1985 to 2016 | Downgrade next year | Random 80/20 split | Ordered logit 0.536; random forest 0.741; XGBoost 0.768 |
| Kumar et al. (2025) | Issuers in a bond index, 2001 to 2024 | Downgrade within 1 month | Test on 2015 to 2024 | Transition matrix 0.54; logit 0.77; random forest 0.80; XGBoost 0.90 |
| de Oliveira & Basso (2025) | S&P, global, 2017 to 2022 | Downgrade or default within 12 months | One test year, 2022 | Logit 0.826 to 0.998 depending on the rating; trees 0.999 to 1.000 |
| Aggarwal, Singh & Thomas (2023) | Indian rating agencies | Downgrade in 1 to 12 months | Not summarised here | 0.62 to 0.81, with distance to default |
| **This model** | US companies with a 10-K and an S&P rating | Downgrade within 12 months of the 10-K | Year by year on 2016 to 2024, never seeing the test year | Logit 0.802 |

## What to take from it

- Published AUCs for a downgrade model range from barely above a coin flip (0.54) to almost perfect (1.000). A single
  number tells you little without the sample, the horizon and the test.
- Ours, 0.802, sits in the middle of the reported range. That is not a claim that ours is better or worse than any
  paper's.
- In Malone, Smales & Liu, the ordered logit is much weaker than the tree models (0.536 against 0.741 and 0.768). In our
  test the logit was close to the tree-based engines: boosting scored slightly above it (0.808 against 0.802) but its
  interval included zero, while XGBoost and the random forest scored below (0.800 and 0.794). The sample, the inputs and
  the way of testing differ, so we cannot say why.

## Why a random split can flatter or hurt

A random split puts a random 80% of all reports in training and the other 20% in testing, whatever their year.

- **It can flatter.** Reports of the same company can fall in both parts, in neighbouring years, with nearly the same
  ratios and the same rating, so the model could partly remember the company instead of learning a rule. Reports from
  the same year also fall on both sides, so year-wide shocks can be seen in training. This is our reasoning, not a
  result tested here. In real use, a model never sees the future.
- **It can hurt, or just mislead.** Over a long sample (such as 1985 to 2016) the link between ratios and downgrades may
  change, for example when agencies change their standards (Blume, Lim & MacKinlay 1998), and one pooled model may then
  fit some periods poorly. A random split also does not show how the model did in a bad year. One random draw can be
  lucky or unlucky.

Our test avoids this: each test year is a year the model never saw, and a one-year gap keeps every training outcome from
reaching into it (rolling origin with an embargo).

## Why a 1-month score and a 12-month score are not comparable

A 1-month question and a 12-month question are different tasks, so 0.90 for a 1-month question and 0.80 for a 12-month
question are not comparable. A company that is about to be downgraded may already be on CreditWatch or have a negative
outlook (agencies use these as warnings). A 12-month question looks further ahead. The horizon also changes how rare the
event is, which affects other scores such as PR-AUC.

## About the very high numbers

In de Oliveira & Basso, trees score 0.999 to 1.000. A score that close to perfect on a real credit question is
implausible. One possible cause is information from the future in the inputs (leakage). We cannot tell from the numbers.
When you see a score like this, ask what went into it before you believe it.
