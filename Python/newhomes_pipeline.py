"""
newhomes_pipeline.py

EnerGuide new-construction (P/N) CSV -> web-ready per-province parquet for the
New Homes Explorer (newhomes.html), the new-construction sibling of the
Retrofit Explorer.

Where retrofits use EVALTYPE D (pre) / E (post-retrofit) existing-home audits,
NEW CONSTRUCTION uses two other evaluation types in the SAME source CSVs:

    P = "Plan" file        -> the home AS DESIGNED (from architectural plans,
                              submitted before construction)
    N = "As-built" file    -> the home AS BUILT (evaluated + blower-door tested
                              after construction is finished)

(Confirmed against NRCan's EnerGuide Rating System open-data documentation.)

So no new download is needed: the C:\\ERS\\<year>.csv files already contain the
new-construction records. This pipeline just filters to P/N instead of D/E.

New construction is small (~30k homes/year, ~300k total across all years) — it
fits comfortably in memory — so unlike ers_web_pipeline.py this does a SINGLE
streaming pass over each CSV and does all pairing/province-splitting in memory.

MODEL: one row per AS-BUILT (N) home. The matching PLAN (P) record for the same
HOUSEID is left-joined so we can compare as-designed vs as-built. Homes with a
plan file but no as-built file yet (not built / not tested) are excluded — the
population is "finished, tested new homes."

Derived columns:
    RatingGap  = ERSRating - Designed_ERSRating   (GJ/yr; <0 = as-built beats design)
    AirGap     = AirLeakage - Designed_AirLeakage (ACH50; <0 = tighter than design)
    EUI        = TotalEnergy / FloorArea          (kWh/m2/yr)
    Year       = calendar year of the as-built evaluation (from ENTRYDATE)

OUTPUT: <OUTPUT_DIR>/nc_<PROVINCE>.parquet   (human-readable strings, NOT
        dictionary-encoded — precompute + FSA-split read these directly)
"""

import os
import csv
from pathlib import Path

import pandas as pd
import numpy as np
import pyarrow as pa
import pyarrow.csv as pacsv


# =============================================================================
# CONFIG
# =============================================================================

INPUT_DIR  = r"C:\ERS"
OUTPUT_DIR = r"C:\ERS\web_nc"

CSV_FILES = [
    '2004-2006.csv', '2007.csv', '2008.csv', '2009.csv', '2010.csv',
    '2011.csv', '2012.csv', '2013.csv', '2014.csv', '2015.csv',
    '2016.csv', '2017.csv', '2018.csv', '2019.csv', '2020.csv',
    '2021.csv', '2022.csv', '2023.csv', '2024.csv', '2025.csv',
    '2026.csv',
]

MJ_TO_KWH = 0.27778

# Source CSV columns we need (all read as strings, coerced later).
SOURCE_COLS = [
    'HOUSEID', 'EVALTYPE', 'ENTRYDATE', 'PROVINCE', 'CLIENTPCODE',
    'TYPEOFHOUSE', 'STOREYS', 'FLOORAREA',
    'ERSRATING', 'EGHRATING', 'ENERGYPERFORMANCETIER', 'INSCOPEOFNBC',
    'OVERALLIMPROVEMENT', 'ESTAR',
    'ERSGHG', 'GHGI',
    'AIR50P', 'EGHFCONTOTAL', 'EGHDESHTLOSS',
    'FURNACEFUEL', 'FURNACETYPE', 'KWPV',
]


# =============================================================================
# STEP 1 — stream each CSV once, keep only P/N rows
# =============================================================================

def read_pn_records(csv_path):
    """Return a DataFrame of the P and N rows in one CSV (needed cols only)."""
    with open(csv_path, 'r', encoding='utf-8', errors='replace') as f:
        header = [h.strip().strip('"') for h in f.readline().strip().split(',')]
    present = [c for c in SOURCE_COLS if c in header]
    if 'EVALTYPE' not in present or 'HOUSEID' not in present:
        print(f"  !! {os.path.basename(csv_path)}: missing EVALTYPE/HOUSEID — skipping")
        return None

    read_opts    = pacsv.ReadOptions(block_size=1 << 23)
    parse_opts   = pacsv.ParseOptions(delimiter=',')
    convert_opts = pacsv.ConvertOptions(
        include_columns=present,
        strings_can_be_null=True,
        column_types={c: pa.string() for c in present},
    )

    frames = []
    reader = pacsv.open_csv(csv_path, read_opts, parse_opts, convert_opts)
    for batch in reader:
        tbl = pa.Table.from_batches([batch])
        df = tbl.to_pandas()
        df = df[df['EVALTYPE'].isin(('P', 'N'))]
        if len(df):
            frames.append(df)
    if not frames:
        return None
    out = pd.concat(frames, ignore_index=True)
    # Make sure every expected column exists even if this (older) file lacked it
    for c in SOURCE_COLS:
        if c not in out.columns:
            out[c] = np.nan
    return out


# =============================================================================
# STEP 2 — build the per-home (as-built + designed) table
# =============================================================================

def coerce(s):
    return pd.to_numeric(s, errors='coerce')


def title_case(s):
    if not isinstance(s, str) or not s.strip():
        return np.nan
    import re
    return re.sub(r'\b\w', lambda m: m.group().upper(), s.strip())


def build_home_table(all_pn):
    """all_pn: concat of every year's P/N rows. Returns one row per as-built home."""
    all_pn = all_pn.copy()
    all_pn['HOUSEID'] = all_pn['HOUSEID'].astype(str)
    all_pn['_year'] = pd.to_datetime(all_pn['ENTRYDATE'], errors='coerce').dt.year

    n_rows = all_pn[all_pn['EVALTYPE'] == 'N']
    p_rows = all_pn[all_pn['EVALTYPE'] == 'P']

    # Keep homes with exactly one as-built record (drops rare dupes/re-evals).
    n_counts = n_rows.groupby('HOUSEID').size()
    keep_ids = set(n_counts[n_counts == 1].index)
    n_rows = n_rows[n_rows['HOUSEID'].isin(keep_ids)].set_index('HOUSEID')

    # Designed values: exactly one plan file per home (else leave design blank).
    p_counts = p_rows.groupby('HOUSEID').size()
    p_ids = set(p_counts[p_counts == 1].index)
    p_rows = p_rows[p_rows['HOUSEID'].isin(p_ids)].set_index('HOUSEID')

    print(f"  as-built (N) homes: {len(n_rows):,}   plan (P) files matched: "
          f"{len(set(n_rows.index) & p_ids):,}")

    def col(src, key, conv=None):
        s = src[key] if key in src.columns else pd.Series(index=src.index, dtype=object)
        return coerce(s) if conv == 'num' else s

    out = pd.DataFrame(index=n_rows.index)

    # --- identity / location (as-built) ---
    out['Year']       = n_rows['_year'].astype('Int64')
    out['PT']         = n_rows['PROVINCE']
    out['FSA']        = n_rows['CLIENTPCODE'].astype(str).str.strip().str.upper().str[:3]
    out['BldgType']   = n_rows['TYPEOFHOUSE'].map(title_case)
    out['Storeys']    = n_rows['STOREYS'].map(title_case)
    out['FloorArea']  = col(n_rows, 'FLOORAREA', 'num')

    # --- as-built performance ---
    out['ERSRating']  = col(n_rows, 'ERSRATING', 'num')       # GJ/yr, lower=better
    out['EGHRating']  = col(n_rows, 'EGHRATING', 'num')       # 0-100 (pre-2019)
    out['Tier']       = col(n_rows, 'ENERGYPERFORMANCETIER', 'num')
    out['InScopeNBC'] = n_rows['INSCOPEOFNBC'].astype(str).str.strip().str.upper().eq('T')
    out['Improvement']= col(n_rows, 'OVERALLIMPROVEMENT', 'num')  # % better than NBC ref
    out['CompliancePath'] = n_rows['ESTAR'].map(title_case)
    out['GHG']        = col(n_rows, 'ERSGHG', 'num')          # tonnes/yr
    out['GHGI']       = col(n_rows, 'GHGI', 'num')            # intensity, kg/m2/yr-ish
    out['AirLeakage'] = col(n_rows, 'AIR50P', 'num')         # ACH50
    out['TotalEnergy']= col(n_rows, 'EGHFCONTOTAL', 'num') * MJ_TO_KWH  # kWh/yr
    out['HeatLoss']   = col(n_rows, 'EGHDESHTLOSS', 'num') * 0.001      # kW (design)
    out['HeatFuel']   = n_rows['FURNACEFUEL'].map(title_case)
    out['HeatType']   = n_rows['FURNACETYPE'].map(title_case)
    out['SolarPV']    = col(n_rows, 'KWPV', 'num')           # kW DC

    # --- designed (plan) counterparts, aligned by HOUSEID ---
    out['Designed_ERSRating']  = p_rows['ERSRATING'].reindex(out.index).pipe(coerce)
    out['Designed_AirLeakage'] = p_rows['AIR50P'].reindex(out.index).pipe(coerce)
    de = p_rows['EGHFCONTOTAL'].reindex(out.index).pipe(coerce) * MJ_TO_KWH
    out['Designed_TotalEnergy'] = de
    out['Designed_Tier']       = p_rows['ENERGYPERFORMANCETIER'].reindex(out.index).pipe(coerce)

    # --- derived ---
    out['RatingGap'] = out['ERSRating'] - out['Designed_ERSRating']       # <0 beats design
    out['AirGap']    = out['AirLeakage'] - out['Designed_AirLeakage']     # <0 tighter than design
    area = out['FloorArea']
    out['EUI'] = (out['TotalEnergy'] / area).where(area > 0)              # kWh/m2/yr

    out = out.reset_index(drop=True)
    return out


# =============================================================================
# MAIN
# =============================================================================

def main():
    Path(OUTPUT_DIR).mkdir(parents=True, exist_ok=True)

    print("=== STEP 1: reading P/N records from CSVs ===")
    frames = []
    for fname in CSV_FILES:
        csv_path = os.path.join(INPUT_DIR, fname)
        if not os.path.exists(csv_path):
            print(f"  !! missing: {csv_path}")
            continue
        df = read_pn_records(csv_path)
        if df is not None:
            frames.append(df)
            print(f"  {fname}: {len(df):,} P/N rows")

    if not frames:
        print("!! no P/N records found — nothing to do")
        return

    all_pn = pd.concat(frames, ignore_index=True)
    del frames
    print(f"  total P/N rows: {len(all_pn):,}")

    print("=== STEP 2: building per-home as-built/designed table ===")
    homes = build_home_table(all_pn)
    print(f"  {len(homes):,} as-built homes")

    print("=== STEP 3: writing per-province parquet ===")
    homes = homes[homes['PT'].notna() & (homes['PT'].astype(str).str.strip() != '')]
    for prov, grp in homes.groupby('PT'):
        prov = str(prov).strip()
        if not prov:
            continue
        out_path = os.path.join(OUTPUT_DIR, f"nc_{prov}.parquet")
        grp.drop(columns=['PT']).to_parquet(out_path, index=False)
        print(f"  {prov}: {len(grp):,} homes -> {out_path}")

    print("done.")


if __name__ == '__main__':
    main()
