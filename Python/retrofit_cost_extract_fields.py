"""
Extract raw ERS fields for the Retrofit Costs POC that ers_web_pipeline.py's
BASE_MAPPING doesn't carry (see docs/RETROFIT_COSTS.md "Why this isn't a
simple join").

Scans the raw national C:\\ERS\\*.csv yearly files ONCE for all provinces in
PROVINCES_TO_RUN (not once per province — the CSVs are up to ~1GB/year, so a
single multi-province pass is far cheaper than re-scanning per province),
re-derives the same D(pre)/E(post) pair-per-HOUSEID join ers_web_pipeline.py
uses (on EVALTYPE), and writes one row per HOUSEID with:

  Post-side (installed/current state):
    FOOTPRINT, NUMWINDOWS, NUMDOORS, BASEMENTFLOORAR  (geometry)
    HPEquipType, NUMBEROFHEADS                        (installed ASHP config)
  Pre-side (what the home had before the retrofit):
    ACCENTESTAR, ACWINDNUM, ERSSPACECOOLENERGY, ERSDesCoolLoss  (existing cooling)

Deliberately uses the *base-case* field names (not the UGR*-prefixed
"upgrade case" / auditor-proposed variants) — UGRHPEquipType etc. describe
what the auditor recommended, not what NRCan's data dictionary confirms was
actually installed.

Output: retrofits/data/<PROVINCE>_extra_fields.parquet, keyed by HOUSEID, one
file per province in PROVINCES_TO_RUN.

Safe to re-run; only reads, never mutates C:\\ERS.
"""

import os

import pandas as pd

INPUT_DIR = r"C:\ERS"
OUT_DIR = os.path.join("retrofits", "data")

ALL_PROVINCES = ['AB', 'BC', 'MB', 'NB', 'NF', 'NS', 'NT', 'NU',
                  'ON', 'PE', 'QC', 'SK']

# PE/ON/QC already validated (2026-07-31) — see docs/RETROFIT_COSTS.md
# changelog. Now running the remaining 9 for full national coverage.
PROVINCES_TO_RUN = [p for p in ALL_PROVINCES if p not in ('PE', 'ON', 'QC')]

CSV_FILES = [
    '2004-2006.csv', '2007.csv', '2008.csv', '2009.csv', '2010.csv',
    '2011.csv', '2012.csv', '2013.csv', '2014.csv', '2015.csv',
    '2016.csv', '2017.csv', '2018.csv', '2019.csv', '2020.csv',
    '2021.csv', '2022.csv', '2023.csv', '2024.csv', '2025.csv',
    '2026.csv',
]

WANT_COLS = [
    'HOUSEID', 'EVALTYPE', 'PROVINCE',
    'FOOTPRINT', 'NUMWINDOWS', 'NUMDOORS', 'BASEMENTFLOORAR',
    'HPEquipType', 'NUMBEROFHEADS',
    'ACCENTESTAR', 'ACWINDNUM', 'ERSSPACECOOLENERGY', 'ERSDesCoolLoss',
]

POST_COLS = ['FOOTPRINT', 'NUMWINDOWS', 'NUMDOORS', 'BASEMENTFLOORAR',
             'HPEquipType', 'NUMBEROFHEADS']
PRE_COLS = ['ACCENTESTAR', 'ACWINDNUM', 'ERSSPACECOOLENERGY', 'ERSDesCoolLoss']

CHUNK_ROWS = 200_000


def extract_all(provinces):
    """One pass over every yearly CSV, splitting rows by province as we go."""
    d_rows = {p: [] for p in provinces}
    e_rows = {p: [] for p in provinces}

    for fname in CSV_FILES:
        path = os.path.join(INPUT_DIR, fname)
        if not os.path.exists(path):
            continue
        header = pd.read_csv(path, nrows=0).columns
        usecols = [c for c in WANT_COLS if c in header]
        missing = set(WANT_COLS) - set(usecols)
        if missing:
            print(f"  {fname}: missing columns {sorted(missing)} (ok if not yet in this vintage)")
        counts = {p: 0 for p in provinces}
        for chunk in pd.read_csv(path, usecols=usecols, chunksize=CHUNK_ROWS,
                                  dtype=str, low_memory=False):
            chunk = chunk[chunk['PROVINCE'].isin(provinces)]
            if chunk.empty:
                continue
            for p, sub in chunk.groupby('PROVINCE'):
                counts[p] += len(sub)
                d_rows[p].append(sub[sub['EVALTYPE'] == 'D'])
                e_rows[p].append(sub[sub['EVALTYPE'] == 'E'])
        print(f"  {fname}: " + ", ".join(f"{p}={n}" for p, n in counts.items()))

    out = {}
    for p in provinces:
        d_df = pd.concat(d_rows[p], ignore_index=True) if d_rows[p] else pd.DataFrame(columns=usecols)
        e_df = pd.concat(e_rows[p], ignore_index=True) if e_rows[p] else pd.DataFrame(columns=usecols)
        d_df = d_df.drop_duplicates(subset='HOUSEID', keep='last')
        e_df = e_df.drop_duplicates(subset='HOUSEID', keep='last')

        pre = d_df[['HOUSEID'] + [c for c in PRE_COLS if c in d_df.columns]].copy()
        pre = pre.rename(columns={c: f'Pre_{c}' for c in PRE_COLS if c in pre.columns})

        post = e_df[['HOUSEID'] + [c for c in POST_COLS if c in e_df.columns]].copy()
        post = post.rename(columns={c: f'Post_{c}' for c in POST_COLS if c in post.columns})

        out[p] = pre.merge(post, on='HOUSEID', how='outer')
    return out


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    print(f"Extracting extra fields for {PROVINCES_TO_RUN} from {INPUT_DIR} (single pass)...")
    results = extract_all(PROVINCES_TO_RUN)
    for p, out in results.items():
        out_path = os.path.join(OUT_DIR, f'{p}_extra_fields.parquet')
        out.to_parquet(out_path, index=False)
        print(f"wrote {out_path} — {len(out)} HOUSEIDs")


if __name__ == '__main__':
    main()
