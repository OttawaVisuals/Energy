"""
DIAGNOSTIC (not part of the production pipeline).

Where do the D&E homes that DON'T become matched pairs get dropped?

The Retrofit Explorer's audit funnel shows ~1.6M homes nationally with both a D
(initial) and an E (follow-up) evaluation, but only ~0.54M become matched pairs —
~1.1M are dropped. This script reproduces ers_web_pipeline.py's pairing gates,
in the SAME order, and attributes each dropped home to the FIRST gate it fails,
so the drop counts form a clean funnel that sums exactly.

Gates (ers_web_pipeline.py order):
  A  Multiple audits   — a home must have EXACTLY one D and one E; homes with a
                         re-audit (>1 D or >1 E) are dropped (build_pairs_index).
  B  Date order        — the E must be dated strictly after the D (build_pairs_index).
  C  Floor-area change — |E area - D area| / D area must be <= 10%, D area > 0
                         (_join_and_write floor-area filter).
  D  Structural change — TYPEOFHOUSE, STOREYS and NUMDWELLINGUNITS must all match
                         between the D and the E (_join_and_write structural filter).

Universe note: this matches ers_web_pipeline.py (PROVINCE_FILTER=None), which does
NOT require a province, so the candidate count here can be slightly higher than the
funnel's "Both D&E" number (build_fsa_audit_totals.py only counts homes carrying a
province). Survivors should land within rounding of the shipped matched-pair total.

One streaming pass over C:\\ERS (D/E rows only, 7 columns). Read-only.
"""

import os
import sys
from collections import Counter

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.csv as pacsv
import pyarrow.compute as pc

INPUT_DIR = r"C:\ERS"
CSV_FILES = [
    '2004-2006.csv', '2007.csv', '2008.csv', '2009.csv', '2010.csv',
    '2011.csv', '2012.csv', '2013.csv', '2014.csv', '2015.csv',
    '2016.csv', '2017.csv', '2018.csv', '2019.csv', '2020.csv',
    '2021.csv', '2022.csv', '2023.csv', '2024.csv', '2025.csv',
    '2026.csv',
]
NEEDED = ['HOUSEID', 'EVALTYPE', 'ENTRYDATE', 'FLOORAREA',
          'TYPEOFHOUSE', 'STOREYS', 'NUMDWELLINGUNITS']

# home[hid] = [nD, nE, dtuple, etuple]
#   tuple = (entrydate, floorarea, typeofhouse, storeys, numdwellingunits)
# Low-cardinality categoricals are interned to keep the ~2M-home dict small.
def rec(entrydate, area, htype, storeys, dwell):
    return (entrydate, area,
            sys.intern(htype) if htype else htype,
            sys.intern(storeys) if storeys else storeys,
            sys.intern(dwell) if dwell else dwell)


def scan_file(csv_path, home):
    with open(csv_path, 'r', encoding='utf-8', errors='replace') as f:
        header = [h.strip().strip('"') for h in f.readline().strip().split(',')]
    present = [c for c in NEEDED if c in header]
    if 'EVALTYPE' not in present or 'HOUSEID' not in present:
        print(f"  !! {os.path.basename(csv_path)}: missing EVALTYPE/HOUSEID — skipping")
        return 0

    read_opts    = pacsv.ReadOptions(block_size=1 << 23)
    parse_opts   = pacsv.ParseOptions(delimiter=',')
    convert_opts = pacsv.ConvertOptions(
        include_columns=present, strings_can_be_null=True,
        column_types={c: pa.string() for c in present})

    def col(tbl, name):
        return tbl.column(name).to_pylist() if name in present else [None] * tbl.num_rows

    n = 0
    reader = pacsv.open_csv(csv_path, read_opts, parse_opts, convert_opts)
    for batch in reader:
        tbl = pa.Table.from_batches([batch])
        et = tbl.column('EVALTYPE')
        tbl = tbl.filter(pc.or_(pc.equal(et, 'D'), pc.equal(et, 'E')))
        if tbl.num_rows == 0:
            continue
        hids = tbl.column('HOUSEID').to_pylist()
        ets  = tbl.column('EVALTYPE').to_pylist()
        dts  = col(tbl, 'ENTRYDATE'); fas = col(tbl, 'FLOORAREA')
        tys  = col(tbl, 'TYPEOFHOUSE'); sts = col(tbl, 'STOREYS'); dws = col(tbl, 'NUMDWELLINGUNITS')
        for hid, et_v, dt, fa, ty, st, dw in zip(hids, ets, dts, fas, tys, sts, dws):
            if not hid:
                continue
            r = home.get(hid)
            if r is None:
                r = home[hid] = [0, 0, None, None]
            if et_v == 'D':
                r[0] += 1; r[2] = rec(dt, fa, ty, st, dw)
            else:
                r[1] += 1; r[3] = rec(dt, fa, ty, st, dw)
            n += 1
    return n


def to_float(s):
    return pd.to_numeric(pd.Series(s), errors='coerce')


def main():
    home = {}
    for name in CSV_FILES:
        path = os.path.join(INPUT_DIR, name)
        if not os.path.exists(path):
            print(f"  -- {name}: not found"); continue
        c = scan_file(path, home)
        print(f"  {name}: {c:,} D/E rows  (unique homes so far: {len(home):,})")

    # ---- Gate A: candidates (>=1 D and >=1 E) then exactly-1+1 ----
    candidates = multiple = 0
    d_dates, e_dates, d_areas, e_areas = [], [], [], []
    d_ty, e_ty, d_st, e_st, d_dw, e_dw = [], [], [], [], [], []
    for nD, nE, dtup, etup in home.values():
        if nD >= 1 and nE >= 1:
            candidates += 1
            if nD > 1 or nE > 1:
                multiple += 1
            else:
                d_dates.append(dtup[0]); e_dates.append(etup[0])
                d_areas.append(dtup[1]); e_areas.append(etup[1])
                d_ty.append(dtup[2]);    e_ty.append(etup[2])
                d_st.append(dtup[3]);    e_st.append(etup[3])
                d_dw.append(dtup[4]);    e_dw.append(etup[4])
    del home

    exact = len(d_dates)

    # ---- Gate B: E dated strictly after D (NaT -> fails, as in the pipeline) ----
    dd = pd.to_datetime(pd.Series(d_dates), errors='coerce')
    ed = pd.to_datetime(pd.Series(e_dates), errors='coerce')
    pass_b = (ed > dd).fillna(False).to_numpy()

    # ---- Gate C: floor area within +/-10%, D area > 0 ----
    fad = to_float(d_areas); fae = to_float(e_areas)
    pass_c = ((fad > 0) & ((fae - fad).abs() / fad <= 0.10)).fillna(False).to_numpy()

    # ---- Gate D: type / storeys / dwellings unchanged (str compare, like pipeline) ----
    s = lambda lst: pd.Series(lst).astype(str)
    ty_same = (s(d_ty) == s(e_ty)).to_numpy()
    st_same = (s(d_st) == s(e_st)).to_numpy()
    dw_same = (s(d_dw) == s(e_dw)).to_numpy()
    pass_d = ty_same & st_same & dw_same

    # ---- First-failing-gate attribution (sequential, sums exactly) ----
    drop_date  = int((~pass_b).sum())
    reach_c    = pass_b
    drop_area  = int((reach_c & ~pass_c).sum())
    reach_d    = reach_c & pass_c
    drop_struct = int((reach_d & ~pass_d).sum())
    survivors  = int((reach_d & pass_d).sum())

    # Structural sub-breakdown among homes that REACH gate D (overlap allowed).
    among = reach_d
    sub = {
        'storeys changed':   int((among & ~st_same).sum()),
        'house type changed':int((among & ~ty_same).sum()),
        'dwelling units changed': int((among & ~dw_same).sum()),
    }

    # ---- Report ----
    def line(label, count, denom):
        pct = f"{count/denom*100:5.1f}%" if denom else "   -  "
        print(f"  {label:<34} {count:>11,}  {pct} of candidates")

    print("\n" + "=" * 64)
    print("D&E PAIRING DROP FUNNEL  (first-failing gate, pipeline order)")
    print("=" * 64)
    line("Candidates (>=1 D and >=1 E)", candidates, candidates)
    print("  " + "-" * 60)
    line("A  dropped: multiple audits (>1 D or >1 E)", multiple, candidates)
    line("   -> exactly one D + one E", exact, candidates)
    line("B  dropped: E not dated after D", drop_date, candidates)
    line("C  dropped: floor area changed >10%", drop_area, candidates)
    line("D  dropped: type/storeys/dwellings changed", drop_struct, candidates)
    print("  " + "-" * 60)
    line("MATCHED PAIRS (survivors)", survivors, candidates)
    print("\n  Structural (gate D) sub-reasons, among the",
          f"{int(among.sum()):,} homes reaching gate D")
    print("  (not mutually exclusive — a home can fail more than one):")
    for k, v in sorted(sub.items(), key=lambda kv: -kv[1]):
        d = int(among.sum())
        print(f"    {k:<26} {v:>10,}  {v/d*100:5.1f}%" if d else f"    {k}: -")

    drops = multiple + drop_date + drop_area + drop_struct
    print(f"\n  check: survivors + drops = {survivors + drops:,}"
          f"  (candidates = {candidates:,})")

    # ---- Drill-down: characterize the NUMDWELLINGUNITS mismatch ----
    # (the dominant gate-D reason). Is one side missing, or are both present
    # with genuinely different counts? Missing on one side => data artifact
    # (recoverable); both-present-and-different => a real change.
    dwm = reach_d & ~dw_same
    draw = np.array(d_dw, dtype=object)[dwm]
    eraw = np.array(e_dw, dtype=object)[dwm]
    tot = int(dwm.sum())

    def is_missing(x):
        return x is None or (isinstance(x, str) and x.strip() == '')

    def as_num(x):  # '1.0' / '1' -> 1.0 ; missing/other -> None
        if is_missing(x):
            return None
        try:
            return float(x)
        except (TypeError, ValueError):
            return None

    dmiss = np.array([is_missing(x) for x in draw])
    emiss = np.array([is_missing(x) for x in eraw])
    dnum = [as_num(x) for x in draw]; enum = [as_num(x) for x in eraw]
    # "Same number, different text" = both parse to the SAME float (e.g. 1.0 vs 1)
    same_number = np.array([(a is not None and a == b) for a, b in zip(dnum, enum)])
    real_change = np.array([(a is not None and b is not None and a != b)
                            for a, b in zip(dnum, enum)])

    cat = {
        'both blank/None': int((dmiss & emiss).sum()),
        'one side blank, other has a value': int((dmiss ^ emiss).sum()),
        'same number, different text (1.0 vs 1)': int(same_number.sum()),
        'genuinely different counts': int(real_change.sum()),
    }
    print(f"\n  NUMDWELLINGUNITS mismatch breakdown (of {tot:,} dropped homes):")
    for k, v in cat.items():
        print(f"    {k:<42} {v:>10,}  {v/tot*100:5.1f}%" if tot else f"    {k}: -")
    top = Counter(zip((repr(x) for x in draw), (repr(x) for x in eraw))).most_common(12)
    print("  top raw (D value -> E value) pairs [repr shows None vs '' vs text]:")
    for (a, b), c in top:
        print(f"    {a:>8} -> {b:<8} {c:>10,}  {c/tot*100:5.1f}%")


if __name__ == '__main__':
    main()
