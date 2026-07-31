"""
ERS raw CSV -> per-column fill-rate + cardinality stats, all 433 source columns.

One-off diagnostic for the Retrofit Explorer's "data available" table (docs
transparency page), not part of the regular pipeline. Streams all 21 raw
yearly CSVs in C:\\ERS chunk-by-chunk (dtype=str) so the ~4.5M-row / 433-column
scan doesn't require loading anything fully into memory.

For each column tracks: total row count seen, non-empty count, and a capped
set of distinct values (stops growing past UNIQUE_CAP and reports
">{UNIQUE_CAP}" instead of an exact count once capped -- keeps memory bounded
for near-unique columns like HOUSEID/EVALUATIONSID without needing exact
cardinality for those, which the table only uses qualitatively anyway).

Output: Python/ers_full_column_stats.csv
  columns: column_name, rows_seen, non_empty_count, pct_populated, unique_count, unique_capped
"""

import csv as csv_module
from pathlib import Path

import pandas as pd

INPUT_DIR = Path(r"C:\ERS")
OUTPUT_CSV = Path(r"C:\Energy\Python\ers_full_column_stats.csv")

CSV_FILES = [
    '2004-2006.csv', '2007.csv', '2008.csv', '2009.csv', '2010.csv',
    '2011.csv', '2012.csv', '2013.csv', '2014.csv', '2015.csv',
    '2016.csv', '2017.csv', '2018.csv', '2019.csv', '2020.csv',
    '2021.csv', '2022.csv', '2023.csv', '2024.csv', '2025.csv',
    '2026.csv',
]

CHUNK_ROWS = 200_000
UNIQUE_CAP = 20_000


def main():
    non_empty = {}
    rows_seen = {}
    uniques = {}
    capped = {}
    all_cols_order = []
    seen_cols = set()

    for fname in CSV_FILES:
        path = INPUT_DIR / fname
        if not path.exists():
            print(f"  (skip, missing) {fname}")
            continue
        print(f"Scanning {fname} ...")
        for chunk in pd.read_csv(
            path, dtype=str, chunksize=CHUNK_ROWS,
            low_memory=False, na_filter=True,
            quoting=csv_module.QUOTE_MINIMAL, encoding='utf-8', on_bad_lines='skip',
        ):
            for col in chunk.columns:
                if col not in seen_cols:
                    seen_cols.add(col)
                    all_cols_order.append(col)
                    non_empty[col] = 0
                    rows_seen[col] = 0
                    uniques[col] = set()
                    capped[col] = False

                series = chunk[col]
                rows_seen[col] += len(series)
                notna = series.notna()
                stripped_nonempty = notna & (series.str.strip() != '')
                non_empty[col] += int(stripped_nonempty.sum())

                if not capped[col]:
                    vals = series[stripped_nonempty].unique()
                    uniques[col].update(vals)
                    if len(uniques[col]) > UNIQUE_CAP:
                        capped[col] = True
                        uniques[col] = set()  # drop, no longer needed

    rows = []
    for col in all_cols_order:
        total = rows_seen[col]
        ne = non_empty[col]
        pct = round(100.0 * ne / total, 1) if total else 0.0
        if capped[col]:
            unique_count = f">{UNIQUE_CAP}"
        else:
            unique_count = len(uniques[col])
        rows.append({
            'column_name': col,
            'rows_seen': total,
            'non_empty_count': ne,
            'pct_populated': pct,
            'unique_count': unique_count,
        })

    out = pd.DataFrame(rows)
    out.to_csv(OUTPUT_CSV, index=False)
    print(f"\nWrote {len(out)} columns -> {OUTPUT_CSV}")


if __name__ == '__main__':
    main()
