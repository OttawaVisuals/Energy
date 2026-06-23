"""
split_fsa_json.py

Splits each province's parquet (output of ers_web_pipeline.py Step 3) into
one JSON file per FSA, containing the raw rows for that FSA only, with
human-readable strings (no dictionary encoding — see note below).

This is what the FSA-level view of Retrofit Explorer fetches: when a user
selects/types/clicks an FSA, the browser fetches ONE small file instead of
the full province dataset. The existing client-side filter/render pipeline
(applyFilters / render in retrofits.html) needs a small adapter to read this
shape — see the loading-code update notes shared alongside this script.

Dictionary encoding is intentionally NOT applied here: per-FSA files are
small enough (median ~490 rows, largest observed 5,839 rows across all of
Canada) that the string-vs-int savings aren't worth the extra fetch + decode
step the old pipeline needed for whole-province CSVs. Strings ship as-is.

OUTPUT FORMAT — array-of-arrays, not array-of-objects:
    {"columns": ["FSA","BldgType",...], "rows": [["L3R","Single Detached",...], ...]}
  Array-of-objects (repeating all ~50 key names on every row) was measured
  at ~1MB for a 585-row FSA; this format is ~230KB for the same data (77%
  smaller) because column names are written once instead of once per row.
  Reconstruct a row object client-side with columns[i] -> rows[r][i], or
  index directly by position if you'd rather not reconstruct objects at all.

COLUMN TRIM: only columns retrofits.html's JS actually reads are kept (see
KEEP_COLS below) — verified against every column reference in the file.
~19 unused source columns (raw HOUSEID, audit dates, AFUE/COP/window-code
detail columns, etc.) are dropped.

CATEGORICAL NORMALIZATION: BldgType, Storeys, FoundationType, and the fuel/
heat-type/heat-pump-type columns are case-normalized before grouping (same
rule retrofits.html's old buildDecoders() applied at decode time). Without
this, casing variants from different audit years ('single detached' vs
'Single Detached') silently split one real category into two — confirmed
in AB.json where this affected ~91% of all rows before the fix.

INPUT:  <OUTPUT_DIR>/ers_web_<PROVINCE>.parquet  (pre-dictionary-encoding)
OUTPUT: <OUTPUT_DIR>/fsa_json/<PROVINCE>/<FSA>.json   ({columns, rows} object)
        <OUTPUT_DIR>/fsa_json/<PROVINCE>/_index.json  ([{fsa, row_count}, ...])
"""

import os
import glob
import json
from pathlib import Path

import pandas as pd
import numpy as np

# =============================================================================
# CONFIG
# =============================================================================

OUTPUT_DIR = r"C:\ERS\web"                          # same as pipeline OUTPUT_DIR
FSA_JSON_DIR = os.path.join(OUTPUT_DIR, "fsa_json")

# Same normalization as precompute_province_stats.py — collapses casing
# variants ('single detached' / 'Single Detached') to one canonical string
# BEFORE writing files, so the FSA-view filters/dropdowns don't silently
# split one real-world category into two.
CATEGORICAL_COLS = [
    'FSA', 'BldgType', 'Storeys', 'FoundationType',
    'Pre_HeatFuel', 'Post_HeatFuel', 'Pre_HeatType', 'Post_HeatType',
    'Pre_HPType', 'Post_HPType',
]

# Only columns retrofits.html's JS actually reads (verified against every
# r.Field / r['Field'] / flag(r,key) / dynamic Pre_${key} reference in the
# file), PLUS a few kept on explicit request even though current JS doesn't
# read them yet: Pre/Post_WindowCode, FoundationType, Cooling_Change, and
# Pre_Year/Post_Year (audit year only, extracted from Pre_Date/Post_Date —
# the full date string is dropped, see year_from_date() below).
# Remaining unused columns (HOUSEID, PT, full dates, AFUE, COP,
# FloorInsulation, HeatEnergySavingPct) stay dropped to keep file size down.
# If you add a new chart/field reference in retrofits.html, add the matching
# source column name here too, or the new field will silently be empty.
KEEP_COLS = [
    'FSA', 'BldgType', 'Storeys', 'FoundationType', 'YearBuilt', 'FloorArea',
    'Pre_Year', 'Post_Year',
    'Pre_TotalEnergy', 'Post_TotalEnergy',
    'Pre_HeatFuel', 'Post_HeatFuel', 'Pre_HeatType', 'Post_HeatType',
    'Pre_HPType', 'Post_HPType',
    'Pre_WindowCode', 'Post_WindowCode',
    'Pre_AirLeakage', 'Post_AirLeakage',
    'Pre_RoofInsulation', 'Post_RoofInsulation',
    'Pre_WallInsulation', 'Post_WallInsulation',
    'Pre_FoundationInsulation', 'Post_FoundationInsulation',
    'Pre_GHG', 'Post_GHG',
    'Pre_HeatLoss', 'Post_HeatLoss',
    'Pre_SolarPV', 'Post_SolarPV',
    'Pre_Electricity', 'Post_Electricity',
    'Pre_NaturalGas', 'Post_NaturalGas',
    'Pre_Oil', 'Post_Oil',
    'Pre_Propane', 'Post_Propane',
    'Pre_Wood', 'Post_Wood',
    'Air_Tightness_Upgrade', 'Roof_Insulation_Upgrade',
    'Foundation_Insulation_Upgrade', 'Wall_Insulation_Upgrade',
    'Floor_Insulation_Upgrade', 'Windows_Change',
    'Heating_Change', 'Cooling_Change', 'HeatPump_Addition',
    'Deep_Retrofit', 'Medium_Retrofit', 'Shallow_Retrofit',
    'FuelSwitch', 'EnergySavingPct',
]


def title_case(s):
    if not isinstance(s, str) or not s.strip():
        return s
    import re
    return re.sub(r'\b\w', lambda m: m.group().upper(), s.strip())


def normalize_categoricals(df):
    """Same logic as precompute_province_stats.py — see that file for why."""
    df = df.copy()
    for col in CATEGORICAL_COLS:
        if col not in df.columns:
            continue
        if col == 'FSA':
            df[col] = df[col].astype(str).str.strip().str.upper()
        elif col in ('Pre_HeatFuel', 'Post_HeatFuel'):
            df[col] = df[col].astype(str).str.strip().map(title_case)
        elif col == 'Storeys':
            df[col] = df[col].astype(str).str.strip().map(
                lambda s: (s[:1].upper() + s[1:].lower()) if s else s)
        elif col in ('Pre_HPType', 'Post_HPType'):
            df[col] = df[col].astype(str).str.strip().map(
                lambda s: '' if (not isinstance(s, str) or s == '0' or s.lower().startswith('n/a'))
                else title_case(s))
        else:
            df[col] = df[col].astype(str).str.strip().map(title_case)
        df[col] = df[col].replace({'': np.nan, 'Nan': np.nan, 'None': np.nan})
    return df


def add_year_columns(df):
    """
    Extract just the year from Pre_Date/Post_Date (format 'YYYY-MM-DD') into
    new Pre_Year/Post_Year integer columns. The full date string is not kept
    in KEEP_COLS — only the year, per explicit request — so this must run
    before the column trim in split_province().
    """
    df = df.copy()
    for src, dst in (('Pre_Date', 'Pre_Year'), ('Post_Date', 'Post_Year')):
        if src in df.columns:
            years = pd.to_datetime(df[src], errors='coerce').dt.year
            # nullable integer dtype so missing/unparseable dates become
            # JSON null instead of NaN-as-float
            df[dst] = years.astype('Int64')
        else:
            df[dst] = pd.NA
    return df


def coerce_value(v):
    """
    Convert a single cell to its JSON-ready form:
      - NaN/NaT/None -> None
      - numeric-looking strings -> int or float (old pipeline stored some
        numeric columns as strings; this avoids shipping '175.5' as a string
        when 175.5 is half the bytes and what the JS num() helper wants anyway)
      - numpy scalar types -> native Python types
      - everything else -> left as-is
    """
    if v is None:
        return None
    if isinstance(v, float) and np.isnan(v):
        return None
    try:
        if pd.isna(v):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(v, (np.bool_, bool)):
        return bool(v)
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.floating, float)):
        return round(float(v), 4)
    if isinstance(v, str):
        s = v.strip()
        try:
            f = float(s)
            return int(f) if f.is_integer() else round(f, 4)
        except ValueError:
            return v
    return v


def split_province(parquet_path, out_root):
    province = Path(parquet_path).stem.replace('ers_web_', '')
    print(f"\n--- {province} ---")
    df = pd.read_parquet(parquet_path)
    df = normalize_categoricals(df)
    df = add_year_columns(df)
    print(f"  loaded {len(df):,} rows")

    if 'FSA' not in df.columns:
        print(f"  !! no FSA column — skipping")
        return

    cols_present = [c for c in KEEP_COLS if c in df.columns]
    missing = [c for c in KEEP_COLS if c not in df.columns]
    if missing:
        print(f"  !! columns in KEEP_COLS not found in source, skipped: {missing}")

    prov_dir = os.path.join(out_root, province)
    Path(prov_dir).mkdir(parents=True, exist_ok=True)

    index = []
    n_files = 0
    for fsa, group in df.groupby('FSA'):
        if not fsa or pd.isna(fsa):
            continue
        rows = [
            [coerce_value(v) for v in row]
            for row in group[cols_present].itertuples(index=False, name=None)
        ]
        payload = {'columns': cols_present, 'rows': rows}
        out_path = os.path.join(prov_dir, f"{fsa}.json")
        with open(out_path, 'w', encoding='utf-8') as f:
            json.dump(payload, f, ensure_ascii=False, separators=(',', ':'))
        index.append({'fsa': fsa, 'row_count': len(rows)})
        n_files += 1

    index.sort(key=lambda d: d['fsa'])
    index_path = os.path.join(prov_dir, '_index.json')
    with open(index_path, 'w', encoding='utf-8') as f:
        json.dump(index, f, ensure_ascii=False, indent=2)

    total_size_kb = sum(
        os.path.getsize(os.path.join(prov_dir, f"{e['fsa']}.json")) for e in index
    ) / 1024
    print(f"  wrote {n_files} FSA files ({total_size_kb:.0f} KB total) + _index.json"
          f" ({len(index)} FSAs)")


def main():
    parquet_files = sorted(glob.glob(os.path.join(OUTPUT_DIR, "ers_web_*.parquet")))
    if not parquet_files:
        print(f"!! no province parquets found in {OUTPUT_DIR}")
        return
    for pf in parquet_files:
        split_province(pf, FSA_JSON_DIR)
    print(f"\ndone. FSA JSON files written under {FSA_JSON_DIR}")


if __name__ == '__main__':
    main()
