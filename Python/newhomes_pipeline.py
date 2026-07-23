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

    # --- energy per fuel (whole-house) ---
    'EGHFCONELEC', 'EGHFCONNGAS', 'EGHFCONOIL', 'EGHFCONPROP',
    'EGHFCONWOOD', 'EGHFCONWOODGJ',

    # --- space heating energy per fuel (HOT2000's own heating-only split) ---
    'EGHHEATFCONSE', 'EGHHEATFCONSG', 'EGHHEATFCONSO', 'EGHHEATFCONSP',
    'EGHHEATFCONSW',

    # --- annual heat loss by building component ---
    'EGHHLAIR', 'EGHHLCEILING', 'EGHHLWALLS', 'EGHHLFOUND',
    'EGHHLEXPOSEDFLR', 'EGHHLWINDOOR',

    # --- GHG per fuel ---
    'ERSELECGHG', 'ERSNGASGHG', 'ERSOILGHG', 'ERSPROPGHG', 'ERSWOODGHG',

    # --- envelope: insulation levels + window code ---
    'CEILINS', 'MAINWALLINS', 'FNDWALLINS', 'EGHINEXPOSEDFLR', 'WINDOWCODE',

    # --- ventilation ---
    'CENVENTSYSTYPE',

    # --- heating equipment efficiency ---
    'HEATAFUE', 'EGHFURSEASEFF',

    # --- heat pump specifics ---
    'HPSOURCE', 'COP', 'HPEquipType', 'CCASHP', 'CCASHPCAP',
    'CCASHPHSPF', 'ASHPHSPF', 'ASHPSEER',

    # --- AHRI certificate number ---
    'AHRI',
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


GJ_TO_KWH = 277.778


def wood_kwh(df):
    """Wood energy in kWh. Same priority order as ers_web_pipeline.py's
    wood_kwh: EGHFCONWOODGJ (direct, HOT2000 v11.2+) > EGHHEATFCONSW (HOT2000's
    own heating-fuel split) > EGHFCONWOOD tonnes * 14.0 GJ/t fallback, clipped
    to EGHFCONTOTAL. See that function's docstring for the full derivation."""
    tonnes = coerce(df['EGHFCONWOOD']) if 'EGHFCONWOOD' in df.columns \
        else pd.Series(np.nan, index=df.index)
    heatw = coerce(df['EGHHEATFCONSW']) if 'EGHHEATFCONSW' in df.columns \
        else pd.Series(np.nan, index=df.index)

    kwh = tonnes * 3888.89  # tonne -> kWh (14.0 GJ/t fallback)
    kwh = kwh.where(~(heatw > 0), heatw * GJ_TO_KWH / 1000.0)
    if 'EGHFCONWOODGJ' in df.columns:
        gj = coerce(df['EGHFCONWOODGJ'])
        corroborated = (tonnes.fillna(0) > 0) | (heatw.fillna(0) > 0)
        kwh = kwh.where(~((gj > 0) & corroborated), gj * GJ_TO_KWH)

    if 'EGHFCONTOTAL' in df.columns:
        total_kwh = coerce(df['EGHFCONTOTAL']) * MJ_TO_KWH
        kwh = kwh.where(~((total_kwh > 0) & (kwh > total_kwh)), total_kwh)
    return kwh


# AHRI is an identifier, not a number -- some source-CSV years write it as
# e.g. '211644151.0' for the same model as another year's '211644151'
# (same quirk documented in ers_web_pipeline.py's clean_ahri).
def clean_ahri(s):
    s = s.astype(str).str.strip()
    s = s.str.replace(r'\.0+$', '', regex=True)
    return s.replace({'': np.nan, 'nan': np.nan, 'None': np.nan})


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

    def pcol(key, conv=None):
        """Plan-file (P) counterpart of `key`, reindexed/aligned to `out`."""
        s = p_rows[key].reindex(out.index) if key in p_rows.columns \
            else pd.Series(np.nan, index=out.index)
        return coerce(s) if conv == 'num' else s

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

    # --- energy per fuel (whole-house, kWh) ---
    out['Electricity'] = col(n_rows, 'EGHFCONELEC', 'num')
    out['NaturalGas']  = col(n_rows, 'EGHFCONNGAS', 'num') * 10.3611   # m3 -> kWh (37.30 MJ/m3)
    out['Oil']         = col(n_rows, 'EGHFCONOIL', 'num') * 10.7778    # L -> kWh (38.80 MJ/L)
    out['Propane']     = col(n_rows, 'EGHFCONPROP', 'num') * 7.0917    # L -> kWh (25.53 MJ/L)
    out['Wood']        = wood_kwh(n_rows)

    # --- space heating energy per fuel (HOT2000's own heating-only split) ---
    out['HeatElectricity'] = col(n_rows, 'EGHHEATFCONSE', 'num') * MJ_TO_KWH
    out['HeatNaturalGas']  = col(n_rows, 'EGHHEATFCONSG', 'num') * MJ_TO_KWH
    out['HeatOil']         = col(n_rows, 'EGHHEATFCONSO', 'num') * MJ_TO_KWH
    out['HeatPropane']     = col(n_rows, 'EGHHEATFCONSP', 'num') * MJ_TO_KWH
    out['HeatWood']        = col(n_rows, 'EGHHEATFCONSW', 'num') * MJ_TO_KWH

    # --- annual heat loss by building component (MJ -> kWh; unit inferred from
    # scale like ers_web_pipeline.py's Pre/Post_HeatLoss*, not independently
    # reconciled -- treat as directionally reliable for a component-share view) ---
    out['HeatLossAir']        = col(n_rows, 'EGHHLAIR', 'num') * MJ_TO_KWH
    out['HeatLossRoof']       = col(n_rows, 'EGHHLCEILING', 'num') * MJ_TO_KWH
    out['HeatLossWall']       = col(n_rows, 'EGHHLWALLS', 'num') * MJ_TO_KWH
    out['HeatLossFoundation'] = col(n_rows, 'EGHHLFOUND', 'num') * MJ_TO_KWH
    out['HeatLossFloor']      = col(n_rows, 'EGHHLEXPOSEDFLR', 'num') * MJ_TO_KWH
    out['HeatLossWindowDoor'] = col(n_rows, 'EGHHLWINDOOR', 'num') * MJ_TO_KWH

    # --- GHG per fuel (tonnes/yr) ---
    out['GHGElectricity'] = col(n_rows, 'ERSELECGHG', 'num')
    out['GHGNaturalGas']  = col(n_rows, 'ERSNGASGHG', 'num')
    out['GHGOil']         = col(n_rows, 'ERSOILGHG', 'num')
    out['GHGPropane']     = col(n_rows, 'ERSPROPGHG', 'num')
    out['GHGWood']        = col(n_rows, 'ERSWOODGHG', 'num')

    # --- envelope: insulation levels (RSI) + window code ---
    out['RoofInsulation']       = col(n_rows, 'CEILINS', 'num')
    out['WallInsulation']       = col(n_rows, 'MAINWALLINS', 'num')
    out['FoundationInsulation'] = col(n_rows, 'FNDWALLINS', 'num')
    out['FloorInsulation']      = col(n_rows, 'EGHINEXPOSEDFLR', 'num')
    out['WindowCode']           = n_rows['WINDOWCODE']

    # --- ventilation ---
    out['VentType'] = n_rows['CENVENTSYSTYPE']

    # --- heating equipment efficiency ---
    out['HeatAFUE']        = col(n_rows, 'HEATAFUE', 'num')
    out['HeatSeasonalCOP'] = col(n_rows, 'EGHFURSEASEFF', 'num')

    # --- heat pump specifics ---
    out['HPType']         = n_rows['HPSOURCE']
    out['HPCOP']          = col(n_rows, 'COP', 'num')
    out['HPEquipType']    = n_rows['HPEquipType']
    out['CCASHP']         = n_rows['CCASHP'].astype(str).str.strip().str.upper().eq('T')
    out['CCASHPCapacity'] = col(n_rows, 'CCASHPCAP', 'num')
    out['CCASHPHSPF']     = col(n_rows, 'CCASHPHSPF', 'num')
    out['ASHPHSPF']       = col(n_rows, 'ASHPHSPF', 'num')
    out['ASHPSEER']       = col(n_rows, 'ASHPSEER', 'num')

    # --- AHRI certificate number (strips the '.0'-suffix artifact some
    # source years write -- see clean_ahri docstring) ---
    out['HPAHRI'] = clean_ahri(n_rows['AHRI'])

    # --- designed (plan) counterparts, aligned by HOUSEID ---
    out['Designed_ERSRating']   = pcol('ERSRATING', 'num')
    out['Designed_AirLeakage']  = pcol('AIR50P', 'num')
    out['Designed_TotalEnergy'] = pcol('EGHFCONTOTAL', 'num') * MJ_TO_KWH
    out['Designed_Tier']        = pcol('ENERGYPERFORMANCETIER', 'num')
    out['Designed_HeatLoss']    = pcol('EGHDESHTLOSS', 'num') * 0.001

    out['Designed_Electricity'] = pcol('EGHFCONELEC', 'num')
    out['Designed_NaturalGas']  = pcol('EGHFCONNGAS', 'num') * 10.3611
    out['Designed_Oil']         = pcol('EGHFCONOIL', 'num') * 10.7778
    out['Designed_Propane']     = pcol('EGHFCONPROP', 'num') * 7.0917
    out['Designed_Wood']        = wood_kwh(p_rows).reindex(out.index)

    out['Designed_HeatElectricity'] = pcol('EGHHEATFCONSE', 'num') * MJ_TO_KWH
    out['Designed_HeatNaturalGas']  = pcol('EGHHEATFCONSG', 'num') * MJ_TO_KWH
    out['Designed_HeatOil']         = pcol('EGHHEATFCONSO', 'num') * MJ_TO_KWH
    out['Designed_HeatPropane']     = pcol('EGHHEATFCONSP', 'num') * MJ_TO_KWH
    out['Designed_HeatWood']        = pcol('EGHHEATFCONSW', 'num') * MJ_TO_KWH

    out['Designed_HeatLossAir']        = pcol('EGHHLAIR', 'num') * MJ_TO_KWH
    out['Designed_HeatLossRoof']       = pcol('EGHHLCEILING', 'num') * MJ_TO_KWH
    out['Designed_HeatLossWall']       = pcol('EGHHLWALLS', 'num') * MJ_TO_KWH
    out['Designed_HeatLossFoundation'] = pcol('EGHHLFOUND', 'num') * MJ_TO_KWH
    out['Designed_HeatLossFloor']      = pcol('EGHHLEXPOSEDFLR', 'num') * MJ_TO_KWH
    out['Designed_HeatLossWindowDoor'] = pcol('EGHHLWINDOOR', 'num') * MJ_TO_KWH

    out['Designed_GHGElectricity'] = pcol('ERSELECGHG', 'num')
    out['Designed_GHGNaturalGas']  = pcol('ERSNGASGHG', 'num')
    out['Designed_GHGOil']         = pcol('ERSOILGHG', 'num')
    out['Designed_GHGPropane']     = pcol('ERSPROPGHG', 'num')
    out['Designed_GHGWood']        = pcol('ERSWOODGHG', 'num')

    out['Designed_RoofInsulation']       = pcol('CEILINS', 'num')
    out['Designed_WallInsulation']       = pcol('MAINWALLINS', 'num')
    out['Designed_FoundationInsulation'] = pcol('FNDWALLINS', 'num')
    out['Designed_FloorInsulation']      = pcol('EGHINEXPOSEDFLR', 'num')
    out['Designed_WindowCode']           = pcol('WINDOWCODE')

    out['Designed_VentType'] = pcol('CENVENTSYSTYPE')

    out['Designed_HeatAFUE']        = pcol('HEATAFUE', 'num')
    out['Designed_HeatSeasonalCOP'] = pcol('EGHFURSEASEFF', 'num')

    out['Designed_HPType']         = pcol('HPSOURCE')
    out['Designed_HPCOP']          = pcol('COP', 'num')
    out['Designed_HPEquipType']    = pcol('HPEquipType')
    out['Designed_CCASHP']         = pcol('CCASHP').astype(str).str.strip().str.upper().eq('T')
    out['Designed_CCASHPCapacity'] = pcol('CCASHPCAP', 'num')
    out['Designed_CCASHPHSPF']     = pcol('CCASHPHSPF', 'num')
    out['Designed_ASHPHSPF']       = pcol('ASHPHSPF', 'num')
    out['Designed_ASHPSEER']       = pcol('ASHPSEER', 'num')
    out['Designed_HPAHRI']         = clean_ahri(pcol('AHRI'))

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
