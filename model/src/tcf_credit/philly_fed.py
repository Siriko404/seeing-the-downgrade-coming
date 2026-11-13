"""Pipeline step 6 helper: convert the Philadelphia Fed Real-Time Data Set spreadsheets into the CSV files that
features_v2.Macro reads.

Goes in:  a folder with the public Philadelphia Fed spreadsheets rucQvMd.xlsx (unemployment rate vintages),
          iptMvMd.xlsx (industrial production vintages) and routput_first_second_third.xlsx (real GDP growth, first,
          second, third release and most recent).
Comes out: four CSV files in OUT_DIR: unemployment_first_release.csv, indpro_vintages.csv,
          indpro_first_release.csv and gdp_growth_first_second_third.csv. The columns and the date text ("1948:01",
          "1965:Q3") are the ones features_v2.Macro expects.
Data:     public data (Philadelphia Fed, Real-Time Data Research Center).
Usage: python -m tcf_credit.philly_fed XLSX_DIR OUT_DIR

The spreadsheets mark missing numbers as the Excel error "#N/A", which pandas reads as an empty value. In a vintage
spreadsheet the first column is the date and every later column is one vintage. A row's first release is its first
non-empty value (in vintage order); its latest value is its last non-empty value. The newest vintages can stop before
old months, so the last column is not always the latest value.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd


def read_table(path: Path, sheet: str) -> pd.DataFrame:
    """Read one vintage sheet and keep the date column as text ("1948:01", not a date)."""
    return pd.read_excel(path, sheet_name=sheet, dtype={"DATE": str})


def vintage_first_last(df: pd.DataFrame) -> pd.DataFrame:
    """One row per month with a value: date, first release, its vintage, and the latest value."""
    values = df.iloc[:, 1:].to_numpy()
    present = df.iloc[:, 1:].notna().to_numpy()
    first = present.argmax(axis=1)
    last = present.shape[1] - 1 - present[:, ::-1].argmax(axis=1)
    rows = present.any(axis=1)
    r = np.arange(len(df))
    return pd.DataFrame({
        "date": df.iloc[:, 0].to_numpy()[rows],
        "first_release": values[r, first][rows],
        "first_vintage": df.columns[1:].to_numpy()[first][rows],
        "latest": values[r, last][rows],
    })


def convert(xlsx_dir: Path, out_dir: Path) -> None:
    """Write the four CSV files from the three spreadsheets."""
    xlsx_dir, out_dir = Path(xlsx_dir), Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    unemployment = read_table(xlsx_dir / "rucQvMd.xlsx", "ruc")
    vintage_first_last(unemployment).to_csv(out_dir / "unemployment_first_release.csv", index=False)
    indpro = read_table(xlsx_dir / "iptMvMd.xlsx", "ipt")
    indpro.to_csv(out_dir / "indpro_vintages.csv", index=False)
    vintage_first_last(indpro).to_csv(out_dir / "indpro_first_release.csv", index=False)
    gdp = pd.read_excel(xlsx_dir / "routput_first_second_third.xlsx", sheet_name="DATA", header=4)
    gdp.to_csv(out_dir / "gdp_growth_first_second_third.csv", index=False)


def main() -> None:
    """Convert the spreadsheets in the first folder and write the CSVs into the second folder."""
    convert(Path(sys.argv[1]), Path(sys.argv[2]))


if __name__ == "__main__":
    main()
