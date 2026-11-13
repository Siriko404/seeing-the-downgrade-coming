"""Pipeline step 1 (prepares step 3): reduce the Loughran-McDonald 10-K header file to what linking needs.

Goes in:  the public Loughran-McDonald 10-K header file (LoughranMcDonald_10-K_HeaderData_1993-2024.csv, from the
          Software Repository for Accounting and Finance, sraf.nd.edu), read from standard input.
Comes out: a small CSV: cik, filing_date, form, period, name, former names, sic, state of incorporation, business
          state, fiscal year end. link_obligors uses the names (current and former) to find each company's CIK.
Data:     public data only.
Usage: python -m tcf_credit.lm_headers OUT_CSV [FROM_YEAR] < LoughranMcDonald_10-K_HeaderData_1993-2024.csv
"""
import csv
import sys

KEEP_FORMS = {"10-K", "10-K405", "10-KSB", "10-K/A"}


def main() -> None:
    """Keep annual-report rows from FROM_YEAR on and write the reduced header table."""
    out, from_year = sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "2009"
    reader = csv.DictReader(sys.stdin)
    n = 0
    with open(out, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["cik", "filing_date", "form", "period", "name", "former_names", "sic", "state_inc", "ba_state", "fye"])
        for r in reader:
            if r["fv_form_type"] not in KEEP_FORMS or r["filing_date"][:4] < from_year:
                continue
            former = "|".join(r[f"fc_former_conformed_name_{i}"].strip() for i in range(1, 6) if r[f"fc_former_conformed_name_{i}"].strip())
            w.writerow([str(int(r["cd_central_index_key"] or r["filer_cik"] or 0)), r["filing_date"], r["fv_form_type"],
                        r["g_conformed_period_of_report"], r["cd_company_conformed_name"].strip(), former,
                        r["cd_standard_industrial_classification"].strip(), r["cd_state_of_incorporation"].strip(),
                        r["ba_state"].strip(), r["cd_fiscal_year_end"].strip()])
            n += 1
    print(n, "rows written to", out)


if __name__ == "__main__":
    main()
