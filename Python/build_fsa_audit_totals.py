"""
Per-FSA / per-province audit-composition totals for the Retrofit Explorer.

Two things depend on this sidecar:

  1. The "retrofits selected" KPI denominator — every HOUSEID in an area that has
     any initial (D) or follow-up (E) evaluation, matched or not (`dore_count`,
     folded into each FSA's _index.json entry). That number can't be derived from
     the shipped matched-pair JSON, which carries only matched pairs.

  2. The audit-funnel Sankey — the fixed left-hand stages of the funnel need the
     full composition of an area's audited population, broken down by which
     evaluation types each HOUSEID carries:
        t   total unique HOUSEIDs with ANY evaluation (D/E/P/N)
        de  homes with both a D and an E   (retrofit-pair candidates)
        d   homes with a D but no E        (initial only, terminal)
        e   homes with an E but no D        (follow-up only, terminal)
        nc  homes with only P (plan) / N (as-built) new-construction evals
     By construction t == de + d + e + nc, and dore_count == de + d + e.

This does one lightweight streaming pass over the raw ERS CSVs (C:\\ERS), reading
only four columns. Unlike the old version it also scans P/N rows (new construction),
so `t` reflects ALL EnerGuide activity in the area, not just retrofit audits.

FSA / province assignment per HOUSEID: a home is attributed to the province+FSA of
its highest-priority record, priority D > E > P > N (D wins unconditionally, same as
before; E, then P, then N only fill a gap). Homes whose records disagree on FSA — rare
— land under the D record's. A home with a province but no usable postal code is still
counted in the per-province rollup (`by_province`) but not in any FSA cell (`by_fsa`),
so summing by_fsa can undercount a province slightly; use by_province for the
province/Canada funnel totals.

Output: C:\\ERS\\web\\fsa_audit_totals.json
    {
      "by_fsa":      {PROVINCE: {FSA: {"t":,"de":,"d":,"e":,"nc":}}},
      "by_province": {PROVINCE: {"t":,"de":,"d":,"e":,"nc":}}
    }

Run this after refreshing the raw CSVs and before re-running split_fsa_json.py /
precompute_province_stats.py. This does NOT touch the heavy ers_web_pipeline.py
parquet build.
"""

import os
import json
from collections import defaultdict

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

# Evaluation-type bit flags packed into a per-home mask, and the FSA/province
# attribution priority (lower number = wins). D is the retrofit initial audit,
# E the follow-up; P/N are new-construction plan / as-built.
TYPE_BIT  = {'D': 1, 'E': 2, 'P': 4, 'N': 8}
TYPE_PRIO = {'D': 0, 'E': 1, 'P': 2, 'N': 3}
BIT_D, BIT_E = 1, 2


def norm_fsa(v):
    """CLIENTPCODE -> 3-char FSA, matching the _index.json keys."""
    if v is None:
        return None
    s = str(v).strip().upper().replace(' ', '')
    return s[:3] if len(s) >= 3 else None


def scan_file(csv_path, home):
    """Stream one CSV, updating home[HOUSEID] = [prov, fsa, setter_prio, mask].

    `mask` accumulates every evaluation type seen for the home; `prov`/`fsa` are
    taken from the highest-priority (D>E>P>N) record carrying a province.
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
        # Keep D / E / P / N rows (retrofit + new construction).
        et = tbl.column('EVALTYPE')
        mask = pc.is_in(et, value_set=pa.array(['D', 'E', 'P', 'N']))
        tbl = tbl.filter(mask)
        if tbl.num_rows == 0:
            continue

        hids  = tbl.column('HOUSEID').to_pylist()
        ets   = tbl.column('EVALTYPE').to_pylist()
        pcs   = tbl.column('CLIENTPCODE').to_pylist()
        provs = (tbl.column('PROVINCE').to_pylist()
                 if 'PROVINCE' in present else [None] * tbl.num_rows)

        for hid, et_v, cp, prov in zip(hids, ets, pcs, provs):
            if not hid or not prov:
                continue
            bit  = TYPE_BIT[et_v]
            prio = TYPE_PRIO[et_v]
            fsa  = norm_fsa(cp)
            rec = home.get(hid)
            if rec is None:
                home[hid] = [prov, fsa, prio, bit]
            else:
                rec[3] |= bit                      # accumulate every type seen
                if prio < rec[2]:                  # higher-priority record wins attribution
                    rec[0], rec[1], rec[2] = prov, fsa, prio
            n_rows += 1
    return n_rows


def classify(mask):
    """Composition bucket key for a home's accumulated evaluation-type mask."""
    has_d, has_e = bool(mask & BIT_D), bool(mask & BIT_E)
    if has_d and has_e:
        return 'de'
    if has_d:
        return 'd'
    if has_e:
        return 'e'
    return 'nc'   # only P / N


def new_cell():
    return {'t': 0, 'de': 0, 'd': 0, 'e': 0, 'nc': 0}


def main():
    home = {}
    for name in CSV_FILES:
        path = os.path.join(INPUT_DIR, name)
        if not os.path.exists(path):
            print(f"  -- {name}: not found, skipping")
            continue
        n = scan_file(path, home)
        print(f"  {name}: {n:,} D/E/P/N rows scanned  (running unique HOUSEIDs: {len(home):,})")

    by_fsa      = defaultdict(lambda: defaultdict(new_cell))
    by_province = defaultdict(new_cell)

    for prov, fsa, _prio, mask in home.values():
        cat = classify(mask)
        p = by_province[prov]
        p['t'] += 1
        p[cat] += 1
        if fsa:
            cell = by_fsa[prov][fsa]
            cell['t'] += 1
            cell[cat] += 1

    out = {
        'by_fsa':      {p: dict(fsas) for p, fsas in by_fsa.items()},
        'by_province': dict(by_province),
    }

    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, separators=(',', ':'))

    total = sum(c['t'] for c in by_province.values())
    dore  = sum(c['de'] + c['d'] + c['e'] for c in by_province.values())
    print(f"\n  unique HOUSEIDs with any D/E/P/N: {total:,}")
    print(f"    of which D-or-E (dore population): {dore:,}")
    print(f"  provinces: {len(by_province)}  |  FSA cells: {sum(len(v) for v in by_fsa.values()):,}")
    print(f"  wrote {OUTPUT_PATH}")


if __name__ == '__main__':
    main()
