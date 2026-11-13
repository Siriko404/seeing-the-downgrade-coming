# Glossary

The main terms you meet in this package, in alphabetical order. Each entry is a few plain sentences.

**10-K.** The annual report a US public company files with the SEC. It holds audited financial statements and often a
paragraph on the company's credit ratings. The model's unit of observation is one 10-K.

**10-Q.** The quarterly report a US public company files with the SEC for the first three quarters of its year. It is
shorter than a 10-K and its numbers are not audited.

**8-K.** A short report a US public company files with the SEC when something important happens, such as a new loan or a change of auditor. The
agent reads 8-Ks because some of them mention credit ratings.

**AI agent.** A program that uses a language model to carry out a task in several steps, such as running commands and
reading files, instead of only answering one question. In this package the agent reads filings but does not decide
anything alone: code checks and writes the result.

**As-of date (backtest).** The date you pretend it is. In a backtest you give an as-of date in the past, and the code may use only what was public by then, for example only 10-Ks filed on or before that day.

**Base rate.** How common the thing you predict is overall. In the lecture's test years about 13.5% of annual reports
were followed by a downgrade, so a model that said "13.5%" for every company would have the right base rate and no
skill.

**Calibrated cut.** Another name for the flag line: a cut-off score chosen from an earlier year's scores, so that about the top 10% of them pass it, then held fixed for the year being tested.

**Calibration.** Whether the probabilities mean what they say: of all companies given 20%, about 20% should be
downgraded. A model can rank companies well and still be badly calibrated.

**CIK.** Central Index Key, the number the SEC gives each company or person that files with it. It is more reliable
than a name or a ticker, which can be reused or changed.

**Compustat.** A licensed database of company financial statements. The lecture's route used only its company file's two ID columns (gvkey and CIK), together with the CRSP/Compustat Merged link table, to link SEC
company numbers to stock records. No Compustat financial data is used.

**Connectome.** A complete map of which neuron connects to which in a brain, and how strongly. The fly models use the
published connectome of a fruit fly.

**Credit rating.** A grade (for example AA, BBB or B) that an agency such as S&P gives to a borrower to say how likely it
is to repay. S&P and Fitch use letters from AAA (safest) down to D (default); Moody's uses Aaa down to C.

**CRSP.** The Center for Research in Security Prices, a licensed database of US stock prices and returns, including
stocks that stopped trading. The lecture used it for the market inputs.

**Decision tree.** A chain of yes/no questions on the inputs (for example, "is debt to assets above 0.4?") that ends in a prediction. Gradient boosting and random forests are made of many trees.

**Design matrix.** The table of inputs, one row per report and one column per input, after the numbers are prepared (gaps filled, values put on a common scale), as it is fed to the model.

**Downgrade.** An agency lowers a credit rating by one or more notches. In this package, a downgrade means a lowering of
S&P's long-term issuer credit rating of the company.

**EBIT.** Earnings before interest and taxes: what a company earns from its business before paying lenders and the tax authority. Dividing it by assets or by interest expense gives profitability and coverage ratios.

**EBITDA.** EBIT plus depreciation and amortisation. It is a rough measure of operating cash earnings. Debt divided by EBITDA says how many years of earnings it would take to repay the debt.

**EDGAR.** The SEC's free public website and database of company filings (10-K, 10-Q, 8-K and more).

**Embargo.** A gap left between the training years and the test year, so no training example's outcome window reaches
into the test year. Here the gap is one year.

**False alarm.** A company the model flags that is not downgraded within 12 months. The false-alarm rate is the share of
non-downgraded reports that the flag line flagged.

**Feature.** See *Input*.

**Flag line.** The score above which the model flags a company. Here it is set so that only the top 10% of an earlier
year's scores pass it, and then held fixed for the test year.

**FRED.** The Federal Reserve Bank of St. Louis's free database of economic series, such as bond
spreads and the VIX. The model's unemployment, industrial production and GDP growth come from the Philadelphia Fed Real-Time Data Set instead.

**Gradient boosting.** A method that builds many small decision trees one after another, each one correcting the
mistakes of the trees before it. It can find patterns a logit cannot, and it can also overfit.

**Input.** A number the model uses to make a prediction, such as debt divided by assets. Machine-learning books call it a
*feature*. Most columns of the panel are inputs; a few (names, dates, raw amounts, years rated) are kept for reference and the model does not read them.

**Investment grade.** A rating of BBB- or higher at S&P. Below that, bonds are called high-yield or "junk".


**Kenyon cell.** A type of neuron in the fruit fly's mushroom body, the part of the brain that learns smells. Each one
listens to a mix of inputs, and only a few fire at a time. The fly models keep only the most active 5%.

**Label.** The answer the model learns to predict. Here it is 1 if S&P downgrades the company within 12 months after the
report, and 0 if it does not.

**Logit.** Short for logistic regression. It adds up the inputs, each times a weight, and turns the sum into a probability
between 0 and 1. It is the main model here because it is simple and hard to overfit.

**Look-ahead bias.** Using information that was not yet public at the time of the prediction, for example a figure that
a company restated a year later. It makes a model look better than it could have been in real life.

**Loughran-McDonald word lists.** Lists of words that mean negative or uncertain in financial writing, made by Tim Loughran and
Bill McDonald for 10-K text. The model's text test counts how often those words occur.

**Miss.** A company that is downgraded within 12 months but that the model did not flag.

**Neural network.** A model built from layers of small units that each add up their inputs and pass on a result. With
enough units it can fit very complex shapes, and it can overfit.

**Notch.** One step on a rating scale. AA to AA- is one notch; BBB- to BB+ is also one notch. In the panel, notch counts
from 1 (AAA) upward.

**Offline mode.** Running the agent with no internet, on saved copies of filings. It is for practice and for classrooms
where the network is slow.

**Outlook.** An agency's view of the likely direction of a rating over a longer period (S&P: up to two years for investment grade, up to one year for speculative grade; Fitch: one to two years; Moody's: the medium term): positive, negative,
stable or developing. A negative outlook is a warning, not a downgrade.

**Overfitting.** A model that has learned the quirks of its training data and so does worse on new data. A high score
on the training years can hide it; only the test years show it.

**Panel.** A table with one row per company per period. Here, one row per company per 10-K, with the inputs and the
label.

**PR-AUC.** Area under the precision-recall curve. Precision is the share of flagged companies that were really
downgraded; recall is the share of all downgrades that were flagged. When downgrades are rare, PR-AUC is harder to
score well on than ROC-AUC.

**Precision and recall.** Precision is the share of flagged companies that were really downgraded. Recall is the share of all downgrades that were flagged. Flagging more companies raises recall and usually lowers precision.

**Prompt.** The text you give a language model to tell it what to do. In this package the skill's instructions are part
of the prompt.

**Random forest.** A method that builds many decision trees on different random parts of the data and averages their
votes.

**Random seed.** A starting number for a computer's random choices. The same seed gives the same random draws, so a result can be repeated exactly.

**Rating history (Rule 17g-7).** SEC Rule 17g-7 makes each rating agency post its rating actions, in a standard
computer-readable form, on its own website. Together they give a public record of rating changes over time.

**Rating state.** The company's rating, outlook and watch status on the day of the prediction, plus recent changes. In
this package it is read from the agencies' 17g-7 histories.

**Rating-event codes (DG, UP, NW, WD).** The labels in the agencies' rating histories for what happened. DG is a downgrade, UP an upgrade, NW a new rating (the first grade the agency gives). Three codes mean the rating was withdrawn: WD because the company defaulted, WE because the debt was paid off in full, WO for any other reason (source: the SEC's Rating History Files Publication Guide).

**Readout.** The last, trained layer that reads the active cells of a fixed network and turns them into a probability.
In the fly models, it is a logit, and it is the only part that learns.

**Regularisation (the C setting).** A penalty that keeps a model's weights small so that it does not fit noise. In the logit the setting is called C: a smaller C means a stronger penalty and a simpler model. It is chosen on years before the test years.

**ROC-AUC.** Area under the ROC curve. It is the chance that the model gives a higher score to a randomly chosen
downgraded company than to a randomly chosen company that was not downgraded. 0.5 means no skill, 1.0 means perfect.

**Rolling origin.** A test method that repeats the same steps year after year: train on the past, test on the next
unseen year, then move forward. It copies how a model would really be used.

**SEDAR+.** The Canadian securities regulators' filing system. The tool does not download from SEDAR+;
you download the file yourself.

**Shuffled control.** The same fixed network with its connections scrambled at random. If the real wiring does no better
than the shuffled wiring, the wiring pattern is not what helps.

**Skill.** A folder of instructions and tools that an AI agent can load for one kind of task. `credit-watch` is a skill.

**Snapshot.** The moment at which the model makes its prediction for one report: the day after the 10-K is filed. Only
information known by then may be used.

**Sparse code.** A representation in which only a few units are on and the rest are off. The fly models keep only the most active 5% of Kenyon cells on.

**Survivorship bias.** Studying only companies that still exist or still trade, so failures drop out of the data. Free
price histories often leave out firms that stopped trading, so results built from them may differ from results on complete data.

**Synapse.** The contact point where one neuron sends a signal to another. A connectome counts synapses between every pair of neurons, and the count gives the strength of the connection.

**Watch (CreditWatch, review for downgrade).** A statement by an agency that a rating is under review for a possible change in the short term. S&P says a
CreditWatch is normally resolved within 90 days. S&P calls it CreditWatch, Moody's calls it a review, Fitch calls it Rating Watch. It is a shorter-term review than an outlook.

**Winsorise.** Replace extreme values by a chosen limit (for example the 1st and 99th percentile) so that a few outliers do not dominate a result.

**WRDS.** Wharton Research Data Services, a platform through which many university libraries offer CRSP and Compustat to
their students.

**XBRL.** A standard computer-readable format for the numbers in financial reports. The SEC's company facts and the agencies' 17g-7 rating histories are published in it.

**XGBoost.** An optimized, efficient software library for gradient boosting.
