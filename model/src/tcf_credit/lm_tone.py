"""Optional step (after step 6, used with evaluate.py --text): add the Loughran-McDonald tone of each 10-K's own text.

Goes in:  the panel and the Loughran-McDonald 10-X summaries file. Comes out: the panel with lm_neg, lm_unc, lm_words
and the two change columns lm_neg_chg, lm_unc_chg. Data: public data only.

Source: Loughran-McDonald 10-X Summaries (sraf.nd.edu), which count each filing's words in the LM Master Dictionary
word lists. lm_neg = N_Negative / N_Words, lm_unc = N_Uncertainty / N_Words, for the 10-K the snapshot is built from
(filed on t - 1 day, so the text is public at t). Matched by accession number, else by CIK and filing date.
The model uses the changes from the previous annual report (lm_neg_chg, lm_unc_chg), not the levels.
Caveat: the summaries use the current dictionary, whose word lists were set from older filings and revised later.
Usage: python -m tcf_credit.lm_tone PANEL_CSV LM_SUMMARIES_CSV OUT_CSV
"""
import sys

import pandas as pd

ORIGINAL_10K = {"10-K", "10-K405", "10-KSB", "10-KSB40", "10-KT"}     # amendments (10-K/A ...) are left out
PREV_MIN_DAYS, PREV_MAX_DAYS = 300, 550                               # the previous annual report must be about a year older


def add_changes(s: pd.DataFrame) -> pd.DataFrame:
    """lm_neg_chg, lm_unc_chg: this 10-K's share minus the share in the same company's previous original 10-K
    (empty when there is no previous 10-K filed 300-550 days earlier). Both filings are public at t."""
    s = s.sort_values(["cik", "filed_dt"]).copy()
    g = s.groupby("cik")
    gap = (s.filed_dt - g.filed_dt.shift()).dt.days
    ok = gap.between(PREV_MIN_DAYS, PREV_MAX_DAYS)
    s["lm_neg_chg"] = (s.lm_neg - g.lm_neg.shift()).where(ok)
    s["lm_unc_chg"] = (s.lm_unc - g.lm_unc.shift()).where(ok)
    return s


def main():
    """Match each panel row to its 10-K's word counts (by accession number, else CIK and filing date), add tone changes."""
    panel_csv, summ_csv, out = sys.argv[1:4]
    panel = pd.read_csv(panel_csv)
    s = pd.read_csv(summ_csv, usecols=["CIK", "FILING_DATE", "ACC_NUM", "FORM_TYPE", "N_Words", "N_Negative",
                                       "N_Uncertainty"])
    s = s[s.FORM_TYPE.isin(ORIGINAL_10K) & (s.N_Words > 0)].copy()
    s["lm_neg"] = s.N_Negative / s.N_Words
    s["lm_unc"] = s.N_Uncertainty / s.N_Words
    s["lm_words"] = s.N_Words
    s["cik"] = s.CIK.astype(str)
    s["filed_dt"] = pd.to_datetime(s.FILING_DATE.astype(str), format="%Y%m%d")
    s["filed"] = s.filed_dt.dt.strftime("%Y-%m-%d")
    s = add_changes(s)
    cols = ["lm_neg", "lm_unc", "lm_words", "lm_neg_chg", "lm_unc_chg"]
    by_acc = s.drop_duplicates("ACC_NUM").set_index("ACC_NUM")[cols]
    by_date = s.drop_duplicates(["cik", "filed"]).set_index(["cik", "filed"])[cols]
    a = by_acc.reindex(panel.accn)
    a.index = panel.index
    filed = (pd.to_datetime(panel.t) - pd.Timedelta(days=1)).dt.strftime("%Y-%m-%d")
    b = by_date.reindex(pd.MultiIndex.from_arrays([panel.cik.astype(str), filed]))
    b.index = panel.index
    tone = a.fillna(b)
    out_df = pd.concat([panel.drop(columns=[c for c in cols if c in panel]), tone], axis=1)
    out_df.to_csv(out, index=False)
    hit_acc, hit = a.lm_neg.notna().sum(), tone.lm_neg.notna().sum()
    print(f"{len(panel)} rows; tone found {hit} ({hit / len(panel):.0%}), {hit_acc} by accession; "
          f"change from previous 10-K found {tone.lm_neg_chg.notna().sum()}; "
          f"median lm_neg {tone.lm_neg.median():.4f}, lm_unc {tone.lm_unc.median():.4f}")


if __name__ == "__main__":
    main()
