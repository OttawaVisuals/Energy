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

# Per-FSA audit-composition totals, written by build_fsa_audit_totals.py.
# New shape: {"by_fsa": {PROV: {FSA: {"t","de","d","e","nc"}}}, "by_province": {...}}.
# Folded into each _index.json entry as:
#   dore_count  — homes with any D or E (de+d+e), the "retrofits selected" KPI
#                 denominator (unchanged from before)
#   composition — the full {t,de,d,e,nc} cell, used by the audit-funnel Sankey
# Optional: if missing, both are emitted as null.
AUDIT_TOTALS_PATH = os.path.join(OUTPUT_DIR, "fsa_audit_totals.json")

# Same normalization as precompute_province_stats.py — collapses casing
# variants ('single detached' / 'Single Detached') to one canonical string
# BEFORE writing files, so the FSA-view filters/dropdowns don't silently
# split one real-world category into two.
CATEGORICAL_COLS = [
    'FSA', 'BldgType', 'Storeys', 'FoundationType',
    'Pre_HeatFuel', 'Post_HeatFuel', 'Pre_HeatType', 'Post_HeatType',
    'Pre_HPType', 'Post_HPType', 'Pre_VentType', 'Post_VentType',
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
    # HOUSEID: re-added 2026-07-31 (previously dropped for size — see the note
    # above) so retrofits.html can join a row to its retrofit-cost estimate in
    # the separate retrofit_costs_json/<PROV>/<FSA>.json companion tree (keyed
    # by HOUSEID). See docs/RETROFIT_COSTS.md.
    'HOUSEID',
    'FSA', 'BldgType', 'Storeys', 'FoundationType', 'YearBuilt', 'FloorArea',
    'Pre_Year', 'Post_Year',
    'Pre_TotalEnergy', 'Post_TotalEnergy',
    'Pre_HeatFuel', 'Post_HeatFuel', 'Pre_HeatType', 'Post_HeatType',
    'Pre_HPType', 'Post_HPType',
    'Pre_HPAHRI', 'Post_HPAHRI',
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
    'Pre_HeatElectricity', 'Post_HeatElectricity',
    'Pre_HeatNaturalGas', 'Post_HeatNaturalGas',
    'Pre_HeatOil', 'Post_HeatOil',
    'Pre_HeatPropane', 'Post_HeatPropane',
    'Pre_HeatWood', 'Post_HeatWood',
    'Pre_HeatLossAir', 'Post_HeatLossAir',
    'Pre_HeatLossRoof', 'Post_HeatLossRoof',
    'Pre_HeatLossWall', 'Post_HeatLossWall',
    'Pre_HeatLossFoundation', 'Post_HeatLossFoundation',
    'Pre_HeatLossFloor', 'Post_HeatLossFloor',
    'Pre_HeatLossWindowDoor', 'Post_HeatLossWindowDoor',
    'Pre_VentType', 'Post_VentType',
    'Air_Tightness_Upgrade', 'Roof_Insulation_Upgrade',
    'Foundation_Insulation_Upgrade', 'Wall_Insulation_Upgrade',
    'Floor_Insulation_Upgrade', 'Windows_Change',
    'Heating_Change', 'Cooling_Change', 'HeatPump_Addition',
    'Deep_Retrofit', 'Medium_Retrofit', 'Shallow_Retrofit',
    'FuelSwitch', 'EnergySavingPct',
    # AHRI-certificate-verified heat pump capacity/efficiency (join_hp_capacity.py,
    # keyed on Post_HPAHRI). Post-only -- see that script's docstring for why.
    # Post_HPBrand/Post_HPModel are masked to the same top-5 AHRI numbers as
    # Post_HPAHRI (see the masking step in split_province() below); the
    # capacity/efficiency numbers are NOT masked -- they're physical
    # quantities, not identifiers, and FSA mode's sizing histogram needs the
    # same population as province mode's precomputed (unmasked) one or the
    # two views will disagree.
    'Post_HPCapacity47', 'Post_HPCapacity5',
    'Post_HPHSPF2', 'Post_HPCertCOP5',
    'Post_HPColdClimate', 'Post_HPBrand', 'Post_HPModel',
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


# Per-column float precision. Energy columns are annual kWh — sub-kWh digits
# are pure noise (the source models to ~0.1 Wh) and were ~20% of each file's
# gzipped size. Everything else numeric gets 2 dp (RSI/ACH/GHG/kW values are
# only ever displayed at 0-1 dp and binned far coarser than that);
# EnergySavingPct keeps 4 dp because 1%-bin boundaries round from it.
INT_COLS = {
    'Pre_TotalEnergy', 'Post_TotalEnergy',
    'Pre_Electricity', 'Post_Electricity', 'Pre_NaturalGas', 'Post_NaturalGas',
    'Pre_Oil', 'Post_Oil', 'Pre_Propane', 'Post_Propane', 'Pre_Wood', 'Post_Wood',
}
PRECISION_4_COLS = {'EnergySavingPct'}


def _round_for(col, f):
    if col in INT_COLS:
        return round(f)
    if col in PRECISION_4_COLS:
        return round(f, 4)
    r = round(f, 2)
    return int(r) if float(r).is_integer() else r


def coerce_value(v, col=None):
    """
    Convert a single cell to its JSON-ready form:
      - NaN/NaT/None -> None
      - numeric-looking strings -> int or float (old pipeline stored some
        numeric columns as strings; this avoids shipping '175.5' as a string
        when 175.5 is half the bytes and what the JS num() helper wants anyway)
      - numpy scalar types -> native Python types, rounded per _round_for
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
        return _round_for(col, float(v))
    if isinstance(v, str):
        s = v.strip()
        try:
            f = float(s)
            return int(f) if f.is_integer() else _round_for(col, f)
        except ValueError:
            return v
    return v


def normalize_ahri_cols(df):
    """
    Defensive: some source AHRI values carry a stray trailing '.0' (the same
    model double-counted under two keys, e.g. '211644151' vs '211644151.0')
    — normalize even though ers_web_pipeline.py now does this too, in case
    the parquet being read here predates that fix. Must run before
    top_ahri_set() and the masking step below, or the dedup doesn't help.
    """
    df = df.copy()
    for col in ('Pre_HPAHRI', 'Post_HPAHRI'):
        if col in df.columns:
            s = df[col].astype(str).str.strip().str.replace(r'\.0+$', '', regex=True)
            df[col] = s.replace({'': np.nan, 'nan': np.nan, 'None': np.nan})
    return df


def top_ahri_set(df, n=5, min_digits=4):
    """
    The AHRI column identifies a specific certified heat pump model — too
    granular to expose per-home as-is (long tail of near-unique values, and
    some short junk/placeholder codes). Per explicit request: only the
    province's own top N most common AHRI numbers (with >= min_digits
    digits) are kept; every other value is blanked to null at FSA-file
    write time. This mirrors the top-N AHRI numbers shown in that same
    province's precompute_province_stats.py output, so the two views agree.
    """
    vals = pd.concat([df.get('Pre_HPAHRI', pd.Series(dtype=str)),
                       df.get('Post_HPAHRI', pd.Series(dtype=str))])
    vals = vals.dropna().astype(str).str.strip()
    vals = vals[vals.str.count(r'\d') >= min_digits]
    vals = vals[vals != '']
    return set(vals.value_counts().head(n).index)


def load_audit_totals():
    """Audit-composition sidecar (build_fsa_audit_totals.py), or {} if not built.
    Shape: {"by_fsa": {PROV: {FSA: {t,de,d,e,nc}}}, "by_province": {...}}."""
    if not os.path.exists(AUDIT_TOTALS_PATH):
        print(f"  -- no {os.path.basename(AUDIT_TOTALS_PATH)} found; dore_count/composition -> null"
              f" (run build_fsa_audit_totals.py to populate it)")
        return {}
    with open(AUDIT_TOTALS_PATH, 'r', encoding='utf-8') as f:
        return json.load(f)


def split_province(parquet_path, out_root, audit_totals=None):
    province = Path(parquet_path).stem.replace('ers_web_', '')
    prov_totals = ((audit_totals or {}).get('by_fsa', {})).get(province, {})
    print(f"\n--- {province} ---")
    df = pd.read_parquet(parquet_path)
    df = normalize_categoricals(df)
    df = add_year_columns(df)
    df = normalize_ahri_cols(df)
    print(f"  loaded {len(df):,} rows")

    if 'FSA' not in df.columns:
        print(f"  !! no FSA column — skipping")
        return

    top_ahri = top_ahri_set(df)
    # Save the row-level "is this AHRI number one of the top 5" mask BEFORE
    # blanking Post_HPAHRI itself, so Post_HPBrand/Post_HPModel (identifying,
    # like the AHRI number) get the same treatment. Post_HPCapacity47/5,
    # Post_HPHSPF2, Post_HPCertCOP5, Post_HPColdClimate are NOT masked --
    # see the KEEP_COLS comment above.
    post_ahri_top5 = (df['Post_HPAHRI'].astype(str).str.strip().isin(top_ahri)
                      if 'Post_HPAHRI' in df.columns else None)
    for col in ('Pre_HPAHRI', 'Post_HPAHRI'):
        if col in df.columns:
            df[col] = df[col].where(df[col].astype(str).str.strip().isin(top_ahri))
    if post_ahri_top5 is not None:
        for col in ('Post_HPBrand', 'Post_HPModel'):
            if col in df.columns:
                df[col] = df[col].where(post_ahri_top5)

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
            [coerce_value(v, c) for c, v in zip(cols_present, row)]
            for row in group[cols_present].itertuples(index=False, name=None)
        ]
        payload = {'columns': cols_present, 'rows': rows}
        out_path = os.path.join(prov_dir, f"{fsa}.json")
        with open(out_path, 'w', encoding='utf-8') as f:
            json.dump(payload, f, ensure_ascii=False, separators=(',', ':'))
        # Median (not mean) energy-saving %, matching the "median home"
        # convention used everywhere else on the page — for the FSA map.
        savings = pd.to_numeric(group['EnergySavingPct'], errors='coerce').dropna()
        median_saving_pct = round(float(savings.median()), 4) if len(savings) else None
        # Audit composition of this FSA (matched + unmatched, all eval types).
        # `dore_count` (= de+d+e) is the "retrofits selected" KPI denominator;
        # `composition` ({t,de,d,e,nc}) drives the audit-funnel Sankey's fixed
        # left-hand stages. Both null when the sidecar hasn't been built yet.
        cell = prov_totals.get(fsa)
        dore_count = (cell['de'] + cell['d'] + cell['e']) if cell else None
        index.append({'fsa': fsa, 'row_count': len(rows),
                      'median_saving_pct': median_saving_pct,
                      'dore_count': dore_count,
                      'composition': cell})
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
    audit_totals = load_audit_totals()
    for pf in parquet_files:
        split_province(pf, FSA_JSON_DIR, audit_totals)
    print(f"\ndone. FSA JSON files written under {FSA_JSON_DIR}")


if __name__ == '__main__':
    main()
