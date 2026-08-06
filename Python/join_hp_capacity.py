"""
join_hp_capacity.py

Sidecar pipeline step: joins each province's parquet (output of Step 1,
ers_web_pipeline.py) against the AHRI certificate lookup (lookup/ahri_numbers.json)
to add verified heat-pump capacity/efficiency columns, keyed on Post_HPAHRI.

Why this is a separate script, not part of ers_web_pipeline.py's BASE_MAPPING:
BASE_MAPPING maps CSV columns to output columns inline during the expensive,
rarely-rerun full-CSV streaming pass. A lookup join is cheap and needs to be
re-run any time lookup/ahri_numbers.json grows (e.g. after a fuller AHRI
scrape) without re-running the whole CSV ingest — the same reasoning that
already puts build_fsa_audit_totals.py outside that pipeline as an
independent sidecar feeding Steps 2/3.

Why join on Post_HPAHRI, not the raw auditor-entered HPCAP: validated against
real AHRI certificates (see docs/RETROFITS.md), HPCAP runs a median 1.6x
high and the same AHRI number produces inconsistent (1x/2x/4x) values across
different audit rows. The certificate's own heating_capacity_47f_btuh /
heating_capacity_5f_btuh fields are the trustworthy source. 5F (~-15C) is
used as a Canadian design-day proxy for "does this heat pump carry the full
load on the coldest day, or is it deliberately undersized against backup".

Post-only: pre-existing heat pumps are rare (~1.6% of homes) and the sizing/
pairing story this feeds is about the retrofit's end state, not the baseline.

INPUT:  <OUTPUT_DIR>/ers_web_<PROVINCE>.parquet  (Step 1 output)
        lookup/ahri_numbers.json                  (AHRI certificate data)
OUTPUT: same parquet, overwritten in place with 9 new Post_-prefixed columns:
        Post_HPCapacity47, Post_HPCapacity5  (kW)
        Post_HPHSPF2, Post_HPCertCOP5        (COP at 5F -- distinct from the
                                               existing auditor-entered Post_HPCOP)
        Post_HPColdClimate                   ("Yes"/"No"/blank)
        Post_HPBrand, Post_HPModel
        Post_HPCoolingCapacityTons           (from cooling_capacity_btuh, /12000)
        Post_HPSEER2                         (as certified -- AHRI has reported
                                               SEER2, not SEER1, since the 2023
                                               DOE test-procedure change)
        Post_HPSEER1Est                      (SEER2 / 0.95 -- the commonly used
                                               approximate SEER2->SEER1 conversion
                                               for split systems; an ESTIMATE, not
                                               a certified value -- added because
                                               REMDB's ASHP cost regressions (see
                                               retrofits/USCosts/) were fit on SEER1)

Idempotent: safe to re-run after the lookup grows -- recomputes and
overwrites the 9 columns from Post_HPAHRI each time.
"""

import glob
import json
import os
import re
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

OUTPUT_DIR = r"C:\ERS\web"   # same as ers_web_pipeline.py's OUTPUT_DIR
REPO_ROOT = Path(__file__).resolve().parent.parent
LOOKUP_PATH = REPO_ROOT / "lookup" / "ahri_numbers.json"

BTUH_TO_KW = 0.00029307107
BTUH_TO_TONS = 1 / 12000
SEER2_TO_SEER1_FACTOR = 0.95   # approximate; see module docstring

NEW_COLS = [
    'Post_HPCapacity47', 'Post_HPCapacity5',
    'Post_HPHSPF2', 'Post_HPCertCOP5',
    'Post_HPColdClimate', 'Post_HPBrand', 'Post_HPModel',
    'Post_HPCoolingCapacityTons', 'Post_HPSEER2', 'Post_HPSEER1Est',
]


def clean_ahri(s):
    """Mirrors ers_web_pipeline.py's clean_ahri / split_fsa_json.py's
    normalize_ahri_cols: strip, drop a stray trailing '.0' some source years
    serialize the identifier with."""
    s = s.astype(str).str.strip()
    s = s.str.replace(r'\.0+$', '', regex=True)
    # '0' is HOT2000's own "no heat pump" placeholder, not a real AHRI code --
    # it simply won't match any lookup key, but excluding it here too keeps
    # the has-an-AHRI-number diagnostic count honest.
    return s.replace({'': None, 'nan': None, 'None': None, 'NaN': None, '0': None})


def load_lookup():
    with open(LOOKUP_PATH, encoding='utf-8') as f:
        return json.load(f)


def to_float(v):
    try:
        return float(str(v).replace(',', ''))
    except (TypeError, ValueError):
        return None


def build_capacity_frame(ahri_series, lookup):
    """ahri_series: cleaned AHRI strings (or NaN). Returns a DataFrame of the
    7 new columns, index-aligned to ahri_series."""
    out = {c: [None] * len(ahri_series) for c in NEW_COLS}
    for i, code in enumerate(ahri_series):
        if code is None:
            continue
        entry = lookup.get(code)
        if not entry:
            continue
        h47 = to_float(entry.get('heating_capacity_47f_btuh'))
        h5 = to_float(entry.get('heating_capacity_5f_btuh'))
        if h47 is not None:
            out['Post_HPCapacity47'][i] = round(h47 * BTUH_TO_KW, 3)
        if h5 is not None:
            out['Post_HPCapacity5'][i] = round(h5 * BTUH_TO_KW, 3)
        hspf2 = to_float(entry.get('hspf2'))
        if hspf2 is not None:
            out['Post_HPHSPF2'][i] = hspf2
        cop5 = to_float(entry.get('heating_cop_5f'))
        if cop5 is not None:
            out['Post_HPCertCOP5'][i] = cop5
        cc = entry.get('cold_climate')
        if cc:
            out['Post_HPColdClimate'][i] = cc
        if entry.get('brand'):
            out['Post_HPBrand'][i] = entry['brand']
        if entry.get('model'):
            out['Post_HPModel'][i] = entry['model']
        cool_btuh = to_float(entry.get('cooling_capacity_btuh'))
        if cool_btuh is not None:
            out['Post_HPCoolingCapacityTons'][i] = round(cool_btuh * BTUH_TO_TONS, 3)
        seer2 = to_float(entry.get('seer2'))
        if seer2 is not None:
            out['Post_HPSEER2'][i] = seer2
            out['Post_HPSEER1Est'][i] = round(seer2 / SEER2_TO_SEER1_FACTOR, 2)
    return pd.DataFrame(out, index=ahri_series.index)


def process_parquet(path, lookup):
    province = Path(path).stem.replace('ers_web_', '')
    df = pd.read_parquet(path)
    if 'Post_HPAHRI' not in df.columns:
        print(f"  {province}: no Post_HPAHRI column, skipping")
        return

    ahri_clean = clean_ahri(df['Post_HPAHRI'])
    cap_df = build_capacity_frame(ahri_clean, lookup)

    for col in NEW_COLS:
        df[col] = cap_df[col]

    n_hp_ahri = ahri_clean.notna().sum()
    n_resolved = (df['Post_HPCapacity47'].notna() | df['Post_HPColdClimate'].notna()).sum()
    print(f"  {province}: {len(df):,} rows, {n_hp_ahri:,} with an AHRI number, "
          f"{n_resolved:,} resolved to cert data")

    tmp_path = str(path) + '.tmp'
    table = pa.Table.from_pandas(df, preserve_index=False)
    pq.write_table(table, tmp_path, compression='snappy')
    os.replace(tmp_path, path)


def main():
    if not LOOKUP_PATH.exists():
        print(f"!! {LOOKUP_PATH} not found -- run build_ahri_lookup_full.py first")
        return
    lookup = load_lookup()
    print(f"loaded {len(lookup):,} AHRI entries from {LOOKUP_PATH}")

    parquet_files = sorted(glob.glob(os.path.join(OUTPUT_DIR, "ers_web_*.parquet")))
    if not parquet_files:
        print(f"!! no province parquets found in {OUTPUT_DIR}")
        return

    for path in parquet_files:
        process_parquet(path, lookup)

    print(f"\ndone. {len(parquet_files)} province parquets updated in place.")


if __name__ == '__main__':
    main()
