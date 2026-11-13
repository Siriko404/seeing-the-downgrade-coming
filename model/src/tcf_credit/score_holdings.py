"""Scoring step: score the holdings' latest 10-Ks with the model: the logit on every input of evaluate.py, with its flag
line.

Goes in:  the training panel (features_v2 output) and the holdings panel (made by build_panel --score, yahoo_market,
market_features and features_v2, as listed below).
Comes out: a CSV with each holding's probability of a downgrade within 12 months, the flag line and whether it is flagged,
          or the reason the holding was not scored. Data: whatever produced the two panels (CRSP or Yahoo prices).

For a holding whose latest 10-K snapshot falls in year Y, the rule of the evaluation is applied unchanged:
  probability: the logit trained on labelled snapshots dated in years <= Y-2;
  flag line:   a logit trained on years <= Y-4 scores year Y-2; the cut is the score that only the top 10% of those
               exceed. A holding is flagged when its probability is at or above the cut.
The setting (C, the strength of the penalty) is chosen on the validation years 2013-2014, as in evaluate.py.
Holdings in financials or utilities (outside the model) and holdings without prices are listed with a reason, unscored.
Pipeline (holdings dated after the CRSP files end take their market inputs from public Yahoo prices, yahoo_market.py):
  build_panel EVENTS LINKS COMPANYFACTS holdings_panel.csv --score CIK,...
  yahoo_market YAHOO_DIR holdings_tickers.csv holdings_panel.csv holdings_crsp/
  market_features holdings_panel.csv holdings_crsp/ holdings_market.csv
  features_v2 holdings_market.csv holdings_crsp/ FRED_DIR holdings_v2.csv
  score_holdings PANEL_V2_CSV holdings_v2.csv OUT_CSV
Usage: python -m tcf_credit.score_holdings PANEL_V2_CSV HOLDINGS_V2_CSV OUT_CSV [--flag 0.10]
"""
import sys

import numpy as np
import pandas as pd

from tcf_credit import evaluate as E
from tcf_credit.build_panel import excluded
from tcf_credit.features_v2 import V2_COLUMNS


FIRST_TESTED = 2016                             # first out-of-sample year of evaluate.py (--first 2016)


def prepare(df: pd.DataFrame) -> pd.DataFrame:
    """The same two preparation steps evaluate.main applies: clip the interest-cover ratio, add the report year."""
    df = df.copy()
    df["ebit_interest"] = df["ebit_interest"].clip(-50, 100)
    df["year"] = pd.to_datetime(df["t"]).dt.year
    return df


def main():
    """Fit the logit twice (for the score and for the flag line) in the way evaluate.py does, then score each holding."""
    args = sys.argv[1:]
    panel_csv, hold_csv, out = args[:3]
    flag = float(args[args.index("--flag") + 1]) if "--flag" in args else 0.10
    df = prepare(pd.read_csv(panel_csv))
    df = df[(df.has_prices == 1) & df.label.notna()]
    hold = prepare(pd.read_csv(hold_csv))
    hold = hold.sort_values("t").groupby("cik").tail(1)          # the latest 10-K; earlier ones only fed the changes
    E.EXTRA[:] = V2_COLUMNS + E.MARKET
    E.ONLY[:] = ["logit"]
    params = E.tune(df, 2016, 2014)
    make, cols, impute, sectors = E.models(params)["logit"]
    rows = []
    for r in hold.itertuples():
        res = {"cik": r.cik, "sp_name": r.sp_name, "t": r.t, "rating": r.rating, "outlook_neg": r.outlook_neg,
               "watch_neg": r.watch_neg, "scope": "scored", "p": np.nan, "cut": np.nan, "flagged": None,
               "trained_to": np.nan, "cut_from": ""}
        Y = int(r.year)
        if Y < FIRST_TESTED:                    # the setting is tuned on 2013-14; the flag line needs years <= Y-4
            res["scope"] = (f"10-K from {Y}, before the model's tested years ({FIRST_TESTED} to 2024): not scored; "
                            f"use a date in {FIRST_TESTED} or later")
        elif excluded(str(r.sic)):
            res["scope"] = "outside the model: financial or utility"
        elif r.has_prices != 1:
            res["scope"] = "no prices at t"
        else:
            one = hold[hold.cik == r.cik]
            train, calib_train, calib = df[df.year <= Y - 2], df[df.year <= Y - 4], df[df.year == Y - 2]
            _, p = E.fit_predict(make, cols, impute, sectors, train, one)
            _, pcal = E.fit_predict(make, cols, impute, sectors, calib_train, calib)
            cut = float(np.quantile(pcal, 1 - flag))
            res.update(p=round(float(p[0]), 4), cut=round(cut, 4), flagged=bool(p[0] >= cut), trained_to=Y - 2,
                       cut_from=f"model on years <= {Y - 4} scoring {Y - 2}")
        rows.append(res)
    result = pd.DataFrame(rows)
    result.to_csv(out, index=False)
    print(f"logit C={params['chosen']['logit']['C']}; training rows {len(df)}, last labelled year {df.year.max()}")
    print(result.to_string(index=False))


if __name__ == "__main__":
    main()
