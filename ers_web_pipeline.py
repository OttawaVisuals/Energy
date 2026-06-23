"""
ERS CSV -> Web-ready Parquet/CSV for Retrofit Explorer.

Slimmed version of the full pipeline — same 4-step logic, reduced to ~45
columns suitable for a public-facing HTML explorer. Outputs one file per
province (Parquet + CSV).

Changes from full pipeline:
  - Column set reduced to identity, energy totals, envelope, HVAC, flags
  - All Mod_* columns dropped
  - All HeatLoss breakdown columns dropped (except total design heat loss, kept
    as a peak-demand / equipment-sizing proxy)
  - DHW, ventilation, renewables, battery dropped
  - Window count sub-columns dropped (ER bands, U-values, etc.)
  - Added: Pre/Post_HeatLoss (design heat loss, kW) — peak heating demand proxy
  - Added: Pre/Post_GHG (tonnes/year, includes electricity via provincial
    grid emission factor — ERSGHG already nets in ERSELECGHG)
  - Added: Pre/Post_SolarPV (kW DC capacity) — solar PV adoption
  - Derived columns added at write time:
      EnergySavingPct  = (Pre_TotalEnergy - Post_TotalEnergy) / Pre_TotalEnergy
      HeatEnergySavingPct = same for heating energy only
      FuelSwitch       = Pre_HeatFuel != Post_HeatFuel (bool)

Web-size optimizations (added):
  - Categorical columns dictionary-encoded to integer codes (global dictionary
    across all provinces, written to ers_web_keys.json)
  - Boolean flag columns encoded as 0/1
  - PT column dropped from CSV output (redundant with per-province filename)
  - Final CSV gzip-compressed (.csv.gz)
  - Runs ALL provinces (one file per province) when PROVINCE_FILTER is None

  - Output: <OUTPUT_DIR>/ers_web_<PROVINCE>.parquet
             <OUTPUT_DIR>/ers_web_<PROVINCE>.csv.gz
             <OUTPUT_DIR>/ers_web_keys.json   (shared dictionary, all provinces)
"""

import os
import glob
import gzip
import json
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.csv as pacsv
import pyarrow.compute as pc
import pyarrow.parquet as pq


# =============================================================================
# CONFIG — edit these
# =============================================================================

INPUT_DIR    = r"C:\ERS"
OUTPUT_DIR   = r"C:\ERS\web"          # one file per province goes here
TEMP_DIR     = r"C:\ERS\_tmp_web"

PROVINCE_FILTER = None                # Set to e.g. 'PE' for one province, or None to run all.

ALL_PROVINCES = ['AB', 'BC', 'MB', 'NB', 'NF', 'NS', 'NT', 'NU',
                  'ON', 'PE', 'QC', 'SK']

CSV_FILES = [
    '2004-2006.csv', '2007.csv', '2008.csv', '2009.csv', '2010.csv',
    '2011.csv', '2012.csv', '2013.csv', '2014.csv', '2015.csv',
    '2016.csv', '2017.csv', '2018.csv', '2019.csv', '2020.csv',
    '2021.csv', '2022.csv', '2023.csv', '2024.csv', '2025.csv',
]

CHUNK_ROWS = 100_000


# =============================================================================
# COLUMN MAPPING (reduced set for web explorer)
#
# (output_name, source_csv_col, file: 'D'|'E', conversion_or_None)
# =============================================================================

BASE_MAPPING = [
    # --- Identity & location (all from D) ---
    ('HOUSEID',         'HOUSEID',          'D', None),
    ('FSA',             'CLIENTPCODE',      'D', None),
    ('PT',              'PROVINCE',         'D', None),
    ('YearBuilt',       'YEARBUILT',        'D', None),
    ('FloorArea',       'FLOORAREA',        'D', None),
    ('BldgType',        'TYPEOFHOUSE',      'D', None),
    ('Storeys',         'STOREYS',          'D', None),
    ('FoundationType',  'FNDTYPE',          'D', None),

    # Audit years (entry dates kept as strings for display)
    ('Pre_Date',        'ENTRYDATE',        'D', None),
    ('Post_Date',       'ENTRYDATE',        'E', None),

    # --- Energy totals (MJ -> kWh) ---
    ('Pre_TotalEnergy', 'EGHFCONTOTAL',     'D', 0.27778),
    ('Post_TotalEnergy','EGHFCONTOTAL',     'E', 0.27778),
    ('Pre_HeatEnergy',  'EGHFURNACEAEC',    'D', 0.27778),
    ('Post_HeatEnergy', 'EGHFURNACEAEC',    'E', 0.27778),

    # Per-fuel (electricity stays as-is kWh; others converted)
    # Keeping these so users can see fuel switching impacts
    ('Pre_Electricity', 'EGHFCONELEC',      'D', None),
    ('Post_Electricity','EGHFCONELEC',      'E', None),
    ('Pre_NaturalGas',  'EGHFCONNGAS',      'D', 10.361194),  # m3 -> kWh
    ('Post_NaturalGas', 'EGHFCONNGAS',      'E', 10.361194),
    ('Pre_Oil',         'EGHFCONOIL',       'D', 10.2),       # L -> kWh
    ('Post_Oil',        'EGHFCONOIL',       'E', 10.2),
    ('Pre_Propane',     'EGHFCONPROP',      'D', 7.092),      # L -> kWh
    ('Post_Propane',    'EGHFCONPROP',      'E', 7.092),
    ('Pre_Wood',        'EGHFCONWOOD',      'D', 4166.7),     # tonne -> kWh
    ('Post_Wood',       'EGHFCONWOOD',      'E', 4166.7),

    # --- Envelope ---
    ('Pre_AirLeakage',          'AIR50P',          'D', None),
    ('Post_AirLeakage',         'AIR50P',          'E', None),
    ('Pre_RoofInsulation',      'CEILINS',         'D', None),
    ('Post_RoofInsulation',     'CEILINS',         'E', None),
    ('Pre_WallInsulation',      'MAINWALLINS',     'D', None),
    ('Post_WallInsulation',     'MAINWALLINS',     'E', None),
    ('Pre_FoundationInsulation','FNDWALLINS',      'D', None),
    ('Post_FoundationInsulation','FNDWALLINS',     'E', None),
    ('Pre_FloorInsulation',     'EGHINEXPOSEDFLR', 'D', None),
    ('Post_FloorInsulation',    'EGHINEXPOSEDFLR', 'E', None),
    ('Pre_WindowCode',          'WINDOWCODE',      'D', None),
    ('Post_WindowCode',         'WINDOWCODE',      'E', None),

    # --- HVAC ---
    ('Pre_HeatFuel',            'FURNACEFUEL',     'D', None),
    ('Post_HeatFuel',           'FURNACEFUEL',     'E', None),
    ('Pre_HeatType',            'FURNACETYPE',     'D', None),
    ('Post_HeatType',           'FURNACETYPE',     'E', None),
    ('Pre_HeatAFUE',            'HEATAFUE',        'D', None),
    ('Post_HeatAFUE',           'HEATAFUE',        'E', None),
    ('Pre_HeatSeasonalCOP',     'EGHFURSEASEFF',   'D', None),
    ('Post_HeatSeasonalCOP',    'EGHFURSEASEFF',   'E', None),
    ('Pre_HPType',              'HPSOURCE',        'D', None),
    ('Post_HPType',             'HPSOURCE',        'E', None),
    ('Pre_HPCOP',               'COP',             'D', None),
    ('Post_HPCOP',              'COP',             'E', None),

    # --- Heat loss (proxy for peak heating demand / equipment sizing) ---
    ('Pre_HeatLoss',            'EGHDESHTLOSS',    'D', 0.001),    # W -> kW
    ('Post_HeatLoss',           'EGHDESHTLOSS',    'E', 0.001),

    # --- GHG emissions (includes electricity via provincial grid factor) ---
    ('Pre_GHG',                 'ERSGHG',          'D', None),     # tonnes/year
    ('Post_GHG',                'ERSGHG',          'E', None),

    # --- Solar PV ---
    ('Pre_SolarPV',             'KWPV',            'D', None),     # kW DC capacity
    ('Post_SolarPV',            'KWPV',            'E', None),
]

# Columns needed for filtering (not all go to output)
FILTER_COLS = ['HOUSEID', 'EVALTYPE', 'ENTRYDATE', 'FLOORAREA',
               'TYPEOFHOUSE', 'STOREYS', 'NUMDWELLINGUNITS', 'PROVINCE']

# Flag columns computed at output stage
FLAG_COLS = [
    'Wall_Insulation_Upgrade', 'Roof_Insulation_Upgrade',
    'Foundation_Insulation_Upgrade', 'Floor_Insulation_Upgrade',
    'Windows_Change', 'Air_Tightness_Upgrade',
    'Heating_Change', 'Cooling_Change', 'HeatPump_Addition',
    'Shallow_Retrofit', 'Medium_Retrofit', 'Deep_Retrofit',
]

# Derived columns added at write time
DERIVED_COLS = ['EnergySavingPct', 'HeatEnergySavingPct', 'FuelSwitch']

NEEDED_CSV_COLS = set(FILTER_COLS)
for _, orig, _, _ in BASE_MAPPING:
    NEEDED_CSV_COLS.add(orig)
# Also need HPSOURCE and AIRCONDTYPE for flags
NEEDED_CSV_COLS.update(['HPSOURCE', 'AIRCONDTYPE', 'WINDOWCODE', 'EGHDESHTLOSS', 'ERSGHG', 'KWPV'])

D_MAPPING = [m for m in BASE_MAPPING if m[2] == 'D']
E_MAPPING = [m for m in BASE_MAPPING if m[2] == 'E']


# =============================================================================
# STEP 1: Stream CSVs, split D/E, write per-year parquet intermediates
# =============================================================================

def split_csv_to_parquet(csv_path, year_tag, temp_dir, province_filter):
    d_path = os.path.join(temp_dir, f"{year_tag}_D.parquet")
    e_path = os.path.join(temp_dir, f"{year_tag}_E.parquet")

    with open(csv_path, 'r', encoding='utf-8', errors='replace') as f:
        header = f.readline().strip().split(',')
    header = [h.strip().strip('"') for h in header]
    present = [c for c in header if c in NEEDED_CSV_COLS]

    if 'EVALTYPE' not in present or 'HOUSEID' not in present:
        print(f"  !! {year_tag}: missing EVALTYPE or HOUSEID — skipping")
        return None, None

    read_opts    = pacsv.ReadOptions(block_size=1 << 23)
    parse_opts   = pacsv.ParseOptions(delimiter=',')
    convert_opts = pacsv.ConvertOptions(
        include_columns=present,
        strings_can_be_null=True,
        column_types={c: pa.string() for c in present},
    )

    d_writer = e_writer = None
    d_count  = e_count  = 0

    reader = pacsv.open_csv(csv_path, read_opts, parse_opts, convert_opts)
    try:
        for batch in reader:
            tbl = pa.Table.from_batches([batch])

            if province_filter and 'PROVINCE' in tbl.schema.names:
                tbl = tbl.filter(pc.equal(tbl.column('PROVINCE'), province_filter))
                if tbl.num_rows == 0:
                    continue

            evaltype = tbl.column('EVALTYPE')
            d_tbl = tbl.filter(pc.equal(evaltype, 'D'))
            e_tbl = tbl.filter(pc.equal(evaltype, 'E'))

            if d_tbl.num_rows > 0:
                if d_writer is None:
                    d_writer = pq.ParquetWriter(d_path, d_tbl.schema, compression='snappy')
                d_writer.write_table(d_tbl)
                d_count += d_tbl.num_rows

            if e_tbl.num_rows > 0:
                if e_writer is None:
                    e_writer = pq.ParquetWriter(e_path, e_tbl.schema, compression='snappy')
                e_writer.write_table(e_tbl)
                e_count += e_tbl.num_rows
    finally:
        if d_writer: d_writer.close()
        if e_writer: e_writer.close()

    prov = f" [{province_filter}]" if province_filter else ""
    print(f"  {year_tag}{prov}: {d_count:,} D rows, {e_count:,} E rows")
    return (d_path if d_count > 0 else None,
            e_path if e_count > 0 else None)


# =============================================================================
# STEP 2: Build cross-year pairing index
# =============================================================================

def build_pairs_index(temp_dir, pairs_csv_path, year_tags):
    d_frames, e_frames = [], []

    for year_tag in year_tags:
        for suffix, lst in [('_D', d_frames), ('_E', e_frames)]:
            p = os.path.join(temp_dir, f"{year_tag}{suffix}.parquet")
            if os.path.exists(p):
                df = pd.read_parquet(p, columns=['HOUSEID', 'ENTRYDATE'])
                df['_year'] = year_tag
                lst.append(df)

    if not d_frames or not e_frames:
        print("  !! no D or E intermediates found")
        return

    all_d = pd.concat(d_frames, ignore_index=True)
    all_e = pd.concat(e_frames, ignore_index=True)
    del d_frames, e_frames
    print(f"  D records: {len(all_d):,}  E records: {len(all_e):,}")

    d_counts = all_d.groupby('HOUSEID').size()
    e_counts = all_e.groupby('HOUSEID').size()
    paired_ids = set(d_counts[d_counts == 1].index) & set(e_counts[e_counts == 1].index)
    print(f"  HOUSEIDs with exactly 1 D + 1 E: {len(paired_ids):,}")

    all_d = all_d[all_d['HOUSEID'].isin(paired_ids)]
    all_e = all_e[all_e['HOUSEID'].isin(paired_ids)]

    pairs = all_d.merge(all_e, on='HOUSEID', suffixes=('_D', '_E')).rename(columns={
        '_year_D': 'D_year', '_year_E': 'E_year',
        'ENTRYDATE_D': 'D_date', 'ENTRYDATE_E': 'E_date',
    })

    pairs['_d_dt'] = pd.to_datetime(pairs['D_date'], errors='coerce')
    pairs['_e_dt'] = pd.to_datetime(pairs['E_date'], errors='coerce')
    before = len(pairs)
    pairs = pairs[pairs['_e_dt'] > pairs['_d_dt']]
    print(f"  after date-order filter: {len(pairs):,} (dropped {before - len(pairs):,})")

    pairs[['HOUSEID', 'D_year', 'E_year', 'D_date', 'E_date']].to_csv(pairs_csv_path, index=False)
    print(f"  wrote {pairs_csv_path}")


# =============================================================================
# STEP 3: Join, filter, compute flags + derived cols, write output
# =============================================================================

def coerce_numeric(s):
    return pd.to_numeric(s, errors='coerce')


def apply_mapping(df, mapping):
    data = {}
    for col_name, orig, _, conv in mapping:
        if orig not in df.columns:
            data[col_name] = pd.Series(pd.NA, index=df.index)
        elif conv is not None:
            data[col_name] = coerce_numeric(df[orig]) * conv
        else:
            data[col_name] = df[orig]
    return pd.DataFrame(data, index=df.index)


def safe_get(df, col):
    return df[col] if col in df.columns else pd.Series(pd.NA, index=df.index)


def gt10pct(e_val, d_val):
    e, d = coerce_numeric(e_val), coerce_numeric(d_val)
    return ((d > 0) & (e > 1.10 * d)).fillna(False)


def no_hp(s):
    s = s.fillna('').astype(str).str.strip()
    return (s == '') | s.str.startswith('N/A')


_FINAL_WRITER = None


def _join_and_write(d_df, e_df, output_path):
    global _FINAL_WRITER

    if d_df.empty or e_df.empty:
        return 0

    merged = d_df.merge(e_df, on='HOUSEID', suffixes=('_D', '_E'))
    if merged.empty:
        return 0

    # Floor area filter: <= 10% change
    fa_d = coerce_numeric(merged['FLOORAREA_D'])
    fa_e = coerce_numeric(merged['FLOORAREA_E'])
    merged = merged[(fa_d > 0) & ((fa_e - fa_d).abs() / fa_d <= 0.10)]

    # Structural filters: type, storeys, dwellings unchanged
    merged = merged[
        (merged['TYPEOFHOUSE_D'].astype(str) == merged['TYPEOFHOUSE_E'].astype(str)) &
        (merged['STOREYS_D'].astype(str)      == merged['STOREYS_E'].astype(str))    &
        (merged['NUMDWELLINGUNITS_D'].astype(str) == merged['NUMDWELLINGUNITS_E'].astype(str))
    ]

    if merged.empty:
        return 0

    # Split back into D / E sub-frames
    d_sub = merged[[c for c in merged.columns if c.endswith('_D')]].copy()
    d_sub.columns = [c[:-2] for c in d_sub.columns]
    d_sub['HOUSEID'] = merged['HOUSEID'].values

    e_sub = merged[[c for c in merged.columns if c.endswith('_E')]].copy()
    e_sub.columns = [c[:-2] for c in e_sub.columns]

    # Apply column mapping
    d_out = apply_mapping(d_sub, D_MAPPING)
    e_out = apply_mapping(e_sub, E_MAPPING)
    result = pd.concat([d_out.reset_index(drop=True),
                        e_out.reset_index(drop=True)], axis=1)
    result = result[[m[0] for m in BASE_MAPPING]]

    # ---- Flags ----
    flags = {}
    flags['Wall_Insulation_Upgrade']       = gt10pct(safe_get(e_sub,'MAINWALLINS'),     safe_get(d_sub,'MAINWALLINS')).values
    flags['Roof_Insulation_Upgrade']       = gt10pct(safe_get(e_sub,'CEILINS'),         safe_get(d_sub,'CEILINS')).values
    flags['Foundation_Insulation_Upgrade'] = gt10pct(safe_get(e_sub,'FNDWALLINS'),      safe_get(d_sub,'FNDWALLINS')).values
    flags['Floor_Insulation_Upgrade']      = gt10pct(safe_get(e_sub,'EGHINEXPOSEDFLR'), safe_get(d_sub,'EGHINEXPOSEDFLR')).values

    wc_d = safe_get(d_sub,'WINDOWCODE').fillna('').astype(str).str.strip()
    wc_e = safe_get(e_sub,'WINDOWCODE').fillna('').astype(str).str.strip()
    flags['Windows_Change'] = ((wc_d != '') & (wc_e != '') & (wc_d != wc_e)).values

    a_d = coerce_numeric(safe_get(d_sub,'AIR50P'))
    a_e = coerce_numeric(safe_get(e_sub,'AIR50P'))
    flags['Air_Tightness_Upgrade'] = ((a_d > 0) & (a_e < 0.90 * a_d)).fillna(False).values

    flags['Heating_Change'] = (
        (d_sub.get('FURNACEFUEL', pd.Series([''] * len(d_sub))).astype(str) !=
         e_sub.get('FURNACEFUEL', pd.Series([''] * len(e_sub))).astype(str)) |
        (d_sub.get('FURNACETYPE', pd.Series([''] * len(d_sub))).astype(str) !=
         e_sub.get('FURNACETYPE', pd.Series([''] * len(e_sub))).astype(str))
    ).values

    flags['Cooling_Change'] = (
        safe_get(d_sub,'AIRCONDTYPE').astype(str) != safe_get(e_sub,'AIRCONDTYPE').astype(str)
    ).values

    flags['HeatPump_Addition'] = (no_hp(safe_get(d_sub,'HPSOURCE')) & ~no_hp(safe_get(e_sub,'HPSOURCE'))).values

    pre_tot  = coerce_numeric(safe_get(d_sub,'EGHFCONTOTAL'))
    post_tot = coerce_numeric(safe_get(e_sub,'EGHFCONTOTAL'))
    flags['Shallow_Retrofit'] = ((pre_tot > 0) & (post_tot >= 0.90 * pre_tot) & (post_tot <= pre_tot)).fillna(False).values
    flags['Medium_Retrofit']  = ((pre_tot > 0) & (post_tot <  0.90 * pre_tot) & (post_tot >  0.50 * pre_tot)).fillna(False).values
    flags['Deep_Retrofit']    = ((pre_tot > 0) & (post_tot <= 0.50 * pre_tot)).fillna(False).values

    flags_df = pd.DataFrame(flags, index=result.index)
    result = pd.concat([result, flags_df], axis=1)

    # ---- Derived columns ----
    pre_e  = coerce_numeric(result['Pre_TotalEnergy'])
    post_e = coerce_numeric(result['Post_TotalEnergy'])
    pre_h  = coerce_numeric(result['Pre_HeatEnergy'])
    post_h = coerce_numeric(result['Post_HeatEnergy'])

    result['EnergySavingPct']     = ((pre_e - post_e) / pre_e).where(pre_e > 0)
    result['HeatEnergySavingPct'] = ((pre_h - post_h) / pre_h).where(pre_h > 0)
    result['FuelSwitch']          = (
        result['Pre_HeatFuel'].astype(str) != result['Post_HeatFuel'].astype(str)
    )

    # ---- Write parquet ----
    arrow_tbl = _to_arrow(result)
    if _FINAL_WRITER is None:
        globals()['_FINAL_WRITER'] = pq.ParquetWriter(output_path, arrow_tbl.schema, compression='snappy')
    _FINAL_WRITER.write_table(arrow_tbl)
    return len(result)


NUMERIC_COLS = {name for (name, _, _, conv) in BASE_MAPPING if conv is not None}
NUMERIC_COLS.update(['EnergySavingPct', 'HeatEnergySavingPct',
                      'Pre_GHG', 'Post_GHG', 'Pre_SolarPV', 'Post_SolarPV'])
BOOL_COLS    = set(FLAG_COLS) | {'FuelSwitch'}

# Columns to dictionary-encode (string -> integer code) for the web CSV.
# PT is excluded — it's dropped entirely (redundant with the province filename).
CATEGORICAL_COLS = [
    'FSA',
    'BldgType', 'Storeys', 'FoundationType',
    'Pre_HeatFuel',  'Post_HeatFuel',
    'Pre_HeatType',  'Post_HeatType',
    'Pre_HPType',    'Post_HPType',
]


def _to_arrow(df):
    fields, arrays = [], []
    for col in df.columns:
        if col in NUMERIC_COLS:
            arr = pa.array(pd.to_numeric(df[col], errors='coerce'), type=pa.float64())
            fields.append(pa.field(col, pa.float64()))
        elif col in BOOL_COLS:
            arr = pa.array(df[col].astype(bool), type=pa.bool_())
            fields.append(pa.field(col, pa.bool_()))
        else:
            arr = pa.array(df[col].astype('string').where(df[col].notna(), None), type=pa.string())
            fields.append(pa.field(col, pa.string()))
        arrays.append(arr)
    return pa.Table.from_arrays(arrays, schema=pa.schema(fields))


def process_pairs(temp_dir, pairs_csv_path, output_path):
    pairs  = pd.read_csv(pairs_csv_path, dtype={'HOUSEID': str})
    groups = pairs.groupby(['D_year', 'E_year'])
    print(f"  {len(pairs):,} pairs across {len(groups)} year combinations")

    total = 0
    try:
        for (d_year, e_year), group in groups:
            group_ids = set(group['HOUSEID'])
            d_path = os.path.join(temp_dir, f"{d_year}_D.parquet")
            e_path = os.path.join(temp_dir, f"{e_year}_E.parquet")
            if not (os.path.exists(d_path) and os.path.exists(e_path)):
                print(f"  !! missing intermediate ({d_year}, {e_year}) — skipping")
                continue

            d_df = pd.read_parquet(d_path)
            e_df = pd.read_parquet(e_path)
            d_df['HOUSEID'] = d_df['HOUSEID'].astype(str)
            e_df['HOUSEID'] = e_df['HOUSEID'].astype(str)
            d_df = d_df[d_df['HOUSEID'].isin(group_ids)]
            e_df = e_df[e_df['HOUSEID'].isin(group_ids)]

            n = _join_and_write(d_df, e_df, output_path)
            total += n
            print(f"  D={d_year} -> E={e_year}: {n:,} pairs written")
    finally:
        global _FINAL_WRITER
        if _FINAL_WRITER:
            _FINAL_WRITER.close()
            _FINAL_WRITER = None

    return total


# =============================================================================
# DICTIONARY BUILDING & ENCODING (web-size optimization)
# =============================================================================

def build_global_dictionary(output_dir, keys_path):
    """
    Scan all province parquets in output_dir to collect every unique value for
    each categorical column, then write a single keys.json that maps
    column -> {value: code, ...}.  Values are lowercased/stripped before
    encoding so e.g. 'Single detached' and 'Single Detached' collapse to one
    code.  Codes are 1-based integers; 0 is reserved for missing/empty.
    """
    parquet_files = sorted(glob.glob(os.path.join(output_dir, 'ers_web_*.parquet')))
    if not parquet_files:
        print("  !! no province parquets found — skipping dictionary build")
        return {}

    unique = {col: set() for col in CATEGORICAL_COLS}
    for pf in parquet_files:
        prov = Path(pf).stem.replace('ers_web_', '')
        schema_cols = pq.read_schema(pf).names
        present = [c for c in CATEGORICAL_COLS if c in schema_cols]
        if not present:
            continue
        df = pd.read_parquet(pf, columns=present)
        for col in df.columns:
            vals = df[col].dropna().astype(str).str.strip().str.lower()
            vals = vals[vals != '']
            unique[col].update(vals.unique())
        print(f"  scanned {prov}")

    dictionary = {}
    for col in CATEGORICAL_COLS:
        sorted_vals = sorted(unique[col])
        dictionary[col] = {v: i + 1 for i, v in enumerate(sorted_vals)}

    with open(keys_path, 'w', encoding='utf-8') as f:
        json.dump(dictionary, f, indent=2, ensure_ascii=False)
    print(f"  wrote {keys_path}")
    return dictionary


def encode_dataframe(df, dictionary):
    """
    Apply dictionary encoding to a dataframe (returns a new dataframe):
      - Categorical columns -> integer codes (0 for missing/unknown)
      - Bool columns        -> 0/1 integers
      - PT column           -> dropped (redundant with filename)
    """
    df = df.copy()
    for col, mapping in dictionary.items():
        if col not in df.columns:
            continue
        df[col] = (
            df[col].astype(str).str.strip().str.lower()
                   .map(mapping)
                   .fillna(0)
                   .astype(int)
        )

    for col in BOOL_COLS:
        if col in df.columns:
            df[col] = df[col].astype(bool).astype(int)

    if 'PT' in df.columns:
        df = df.drop(columns=['PT'])

    return df


def write_gzipped_csv(df, csv_gz_path):
    """Write a dataframe straight to a gzip-compressed CSV."""
    with gzip.open(csv_gz_path, 'wt', newline='', encoding='utf-8', compresslevel=9) as f:
        df.to_csv(f, index=False)


# =============================================================================
# MAIN
# =============================================================================

def run_province(province, temp_dir, output_dir, csv_files, year_tags):
    """Run steps 1-3 for a single province. Returns the parquet output path,
    or None if nothing was written."""
    prov_tag    = province if province else 'ALL'
    parquet_out = os.path.join(output_dir, f"ers_web_{prov_tag}.parquet")
    pairs_csv   = os.path.join(temp_dir, f"pairs_{prov_tag}.csv")

    print(f"\n--- Province: {prov_tag} ---")

    print(f"=== STEP 1: splitting CSVs -> D/E parquet  [province={prov_tag}] ===")
    for fname in csv_files:
        csv_path  = os.path.join(INPUT_DIR, fname)
        year_tag  = fname.replace('.csv', '')
        done_mark = os.path.join(temp_dir, f"{year_tag}_{prov_tag}.done")
        if os.path.exists(done_mark):
            print(f"  {year_tag}: already done")
            continue
        if not os.path.exists(csv_path):
            print(f"  !! missing: {csv_path}")
            continue
        split_csv_to_parquet(csv_path, year_tag, temp_dir, province)
        open(done_mark, 'w').close()

    print("=== STEP 2: building pairing index ===")
    if os.path.exists(pairs_csv):
        print(f"  {pairs_csv} exists — skipping (delete to rebuild)")
    else:
        build_pairs_index(temp_dir, pairs_csv, year_tags)

    print("=== STEP 3: join + filter + flags + derived cols ===")
    if os.path.exists(parquet_out):
        print(f"  !! {parquet_out} exists — delete to re-run")
    else:
        total = process_pairs(temp_dir, pairs_csv, parquet_out)
        print(f"  {total:,} rows written to {parquet_out}")

    # Per-province temp cleanup (intermediates + pairs index only — parquet/dictionary
    # cleanup happens after ALL provinces are done, in main()).
    for year_tag in year_tags:
        for suffix in ('_D.parquet', '_E.parquet', f'_{prov_tag}.done'):
            p = os.path.join(temp_dir, f"{year_tag}{suffix}")
            if os.path.exists(p): os.remove(p)
    if os.path.exists(pairs_csv): os.remove(pairs_csv)

    return parquet_out if os.path.exists(parquet_out) else None


def main():
    Path(TEMP_DIR).mkdir(parents=True, exist_ok=True)
    Path(OUTPUT_DIR).mkdir(parents=True, exist_ok=True)

    year_tags = [f.replace('.csv', '') for f in CSV_FILES]
    provinces = [PROVINCE_FILTER] if PROVINCE_FILTER else ALL_PROVINCES

    parquet_outputs = []
    for province in provinces:
        out = run_province(province, TEMP_DIR, OUTPUT_DIR, CSV_FILES, year_tags)
        if out:
            parquet_outputs.append(out)

    print("\n=== STEP 3b: build / load global dictionary ===")
    keys_path = os.path.join(OUTPUT_DIR, 'ers_web_keys.json')
    if os.path.exists(keys_path):
        print(f"  {keys_path} exists — loading (delete to rebuild)")
        with open(keys_path, encoding='utf-8') as f:
            dictionary = json.load(f)
    else:
        # Scans ALL province parquets currently in OUTPUT_DIR, so the dictionary
        # is global and consistent across provinces.
        dictionary = build_global_dictionary(OUTPUT_DIR, keys_path)

    print("\n=== STEP 3c: write encoded, gzipped CSV per province ===")
    all_parquets = sorted(glob.glob(os.path.join(OUTPUT_DIR, 'ers_web_*.parquet')))
    for parquet_out in all_parquets:
        prov_tag   = Path(parquet_out).stem.replace('ers_web_', '')
        csv_gz_out = os.path.join(OUTPUT_DIR, f"ers_web_{prov_tag}.csv.gz")
        if os.path.exists(csv_gz_out):
            print(f"  {csv_gz_out} exists — skipping (delete to re-run)")
            continue

        df_final = pd.read_parquet(parquet_out)
        float_cols = df_final.select_dtypes('float').columns
        df_final[float_cols] = df_final[float_cols].round(2)
        df_final = encode_dataframe(df_final, dictionary)
        write_gzipped_csv(df_final, csv_gz_out)

        print(f"  wrote {csv_gz_out}")
        print(f"    rows: {len(df_final):,}  columns: {len(df_final.columns)}")
        print(f"    file size: {os.path.getsize(csv_gz_out) / 1024:.1f} KB")

    print("\n=== STEP 4: cleanup ===")
    try:
        os.rmdir(TEMP_DIR)
    except OSError:
        pass
    print("  done.")


if __name__ == '__main__':
    main()