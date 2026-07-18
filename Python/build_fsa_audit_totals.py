"""
Per-FSA "audited population" totals for the Retrofit Explorer KPI.

The Retrofit Explorer only ships MATCHED pairs (one D + one E audit per HOUSEID).
For the "retrofits selected" KPI we also want a denominator that reflects the FULL
audited population of an area: every HOUSEID that has *any* D (initial) or E
(follow-up) evaluation, matched or not.

That number can't be derived from the shipped matched-pair JSON, so this script does
one lightweight streaming pass over the raw ERS CSVs (C:\\ERS), reading only four
columns, and writes a sidecar the split_fsa_json.py step folds into each province's
_index.json as `dore_count`.

FSA assignment per HOUSEID: a home is counted once, under the FSA of its D record's
CLIENTPCODE when it has one, else its E record's. (A D record's CLIENTPCODE always
wins — D is unconditional, E only fills gaps — so processing order across files does
not matter. Homes whose D and E sit in different FSAs, which is rare, land in the D
FSA.)

Output: C:\\ERS\\web\\fsa_audit_totals.json  ->  {PROVINCE: {FSA: unique_houseids}}

Run this after refreshing the raw CSVs and before re-running split_fsa_json.py.
This does NOT touch the heavy ers_web_pipeline.py parquet build.
"""

import os
import json
from collections import Counter

import pyarrow as pa
import pyarrow.csv as pacsv
import pyarrow.compute as pc


# =============================================================================
# CONFIG
# =============================================================================

INPUT_DIR   = r"C:\ERS"
OUTPUT_PATH = r"C:\ERS\web\fsa_audit_totals.json"

# Same file list as ers_web_pipeline.py (evaluation entry years 2004-2026).
CSV_FILES = [
    '2004-2006.csv', '2007.csv', '2008.csv', '2009.csv', '2010.csv',
    '2011.csv', '2012.csv', '2013.csv', '2014.csv', '2015.csv',
    '2016.csv', '2017.csv', '2018.csv', '2019.csv', '2020.csv',
    '2021.csv', '2022.csv', '2023.csv', '2024.csv', '2025.csv',
    '2026.csv',
]

NEEDED_COLS = ['HOUSEID', 'EVALTYPE', 'CLIENTPCODE', 'PROVINCE']


def norm_fsa(v):
    """CLIENTPCODE -> 3-char FSA, matching the _index.json keys."""
    if v is None:
        return None
    s = str(v).strip().upper().replace(' ', '')
    return s[:3] if len(s) >= 3 else None


def scan_file(csv_path, home):
    """Stream one CSV, updating home[HOUSEID] = 'PROV|FSA'.

    D records assign unconditionally; E records only fill a gap (setdefault),
    so a HOUSEID's D-record FSA always wins regardless of file order.
    """
    with open(csv_path, 'r', encoding='utf-8', errors='replace') as f:
        header = [h.strip().strip('"') for h in f.readline().strip().split(',')]
    present = [c for c in NEEDED_COLS if c in header]
    if 'EVALTYPE' not in present or 'HOUSEID' not in present or 'CLIENTPCODE' not in present:
        print(f"  !! {os.path.basename(csv_path)}: missing a needed column — skipping")
        return 0

    read_opts    = pacsv.ReadOptions(block_size=1 << 23)
    parse_opts   = pacsv.ParseOptions(delimiter=',')
    convert_opts = pacsv.ConvertOptions(
        include_columns=present,
        strings_can_be_null=True,
        column_types={c: pa.string() for c in present},
    )

    n_rows = 0
    reader = pacsv.open_csv(csv_path, read_opts, parse_opts, convert_opts)
    for batch in reader:
        tbl = pa.Table.from_batches([batch])
        # Keep only D and E rows.
        et = tbl.column('EVALTYPE')
        mask = pc.or_(pc.equal(et, 'D'), pc.equal(et, 'E'))
        tbl = tbl.filter(mask)
        if tbl.num_rows == 0:
            continue

        hids  = tbl.column('HOUSEID').to_pylist()
        ets   = tbl.column('EVALTYPE').to_pylist()
        pcs   = tbl.column('CLIENTPCODE').to_pylist()
        provs = (tbl.column('PROVINCE').to_pylist()
                 if 'PROVINCE' in present else [None] * tbl.num_rows)

        for hid, et_v, cp, prov in zip(hids, ets, pcs, provs):
            if not hid:
                continue
            fsa = norm_fsa(cp)
            if not fsa or not prov:
                continue
            key = f"{prov}|{fsa}"
            if et_v == 'D':
                home[hid] = key            # D wins unconditionally
            else:
                home.setdefault(hid, key)  # E only fills a gap
            n_rows += 1
    return n_rows


def main():
    home = {}
    for name in CSV_FILES:
        path = os.path.join(INPUT_DIR, name)
        if not os.path.exists(path):
            print(f"  -- {name}: not found, skipping")
            continue
        n = scan_file(path, home)
        print(f"  {name}: {n:,} D/E rows scanned  (running unique HOUSEIDs: {len(home):,})")

    # Tally unique HOUSEIDs per (province, fsa).
    counts = Counter(home.values())
    out = {}
    for key, cnt in counts.items():
        prov, fsa = key.split('|', 1)
        out.setdefault(prov, {})[fsa] = cnt

    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, separators=(',', ':'))

    total = sum(counts.values())
    print(f"\n  unique HOUSEIDs with any D or E: {total:,}")
    print(f"  provinces: {len(out)}  |  FSA cells: {sum(len(v) for v in out.values()):,}")
    print(f"  wrote {OUTPUT_PATH}")


if __name__ == '__main__':
    main()
