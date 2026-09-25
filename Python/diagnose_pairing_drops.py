"""
DIAGNOSTIC (not part of the production pipeline).

Where do the D&E homes that DON'T become matched pairs get dropped?

This script reproduces ers_web_pipeline.py's pairing gates, in the SAME order,
and attributes each dropped home to the FIRST gate it fails, so the drop counts
form a clean funnel that sums exactly.

Last run 2026-09-25 (after both dwelling-units changes): 1,647,596 candidates
-> 1,540,773 survivors (93.5%); the pipeline itself ships 1,541,128 (see the
universe note below for the gap).
Previous full run 2026-08-06: 1,629,313 -> 1,451,433 (89.1%).

Gates (ers_web_pipeline.py order, current as of the 2026-07-18/19 fixes --
see build_pairs_index/_join_and_write):
  A  Reduce to ONE pair    — each home is reduced to its OLDEST D + NEWEST E
                             record (not dropped for having extra audits;
                             see diagnose_gates_ab.py, which measured that
                             99.6% of multi-audit homes yield a correctly-
                             ordered pair under this rule -- the pipeline used
                             to drop all 149,145 of them outright).
  B  Date order            — the (newest) E must not be dated before the
                             (oldest) D (build_pairs_index). Same-month D/E is
                             allowed since 2026-09-23: ENTRYDATE is month-
                             precision, and the EnerGuide data team confirmed
                             same-month D and E audits are usable.
  C  Floor-area change     — |E area - D area| / D area must be <= 5%, D area
                             > 0 (_join_and_write floor-area filter; tightened
                             from 10% on 2026-09-23 per the data team). The
                             report also counts the 5-10% band separately.
  D  Structural change     — TYPEOFHOUSE, STOREYS and NUMDWELLINGUNITS must all
                             match between the D and the E, via same_categorical/
                             same_numeric: both-missing counts as unchanged,
                             text-format differences ('1.0' vs '1') are ignored,
                             one-side-missing or a genuine difference drops the
                             pair (_join_and_write structural filter). Exception
                             since 2026-09-25: NUMDWELLINGUNITS missing on ONE
                             side counts as unchanged too (+22,687 pairs),
                             and so does a count of 0 (not recorded).
                             TYPEOFHOUSE / STOREYS compare ignoring
                             capitalization since 2026-09-25.
  E  Weather file          — WTHDATA must match between D and E when both are
                             recorded ('Not Applicable' counts as not recorded);
                             added 2026-09-23 per the data team.

HOUSEID is normalized as it is read (trailing '.0' stripped), matching
ers_web_pipeline.normalize_ids: files up to 2025.csv write '5063805.0', 2026.csv
writes '5063805' (fixed 2026-09-24).

Universe note: this keys homes by HOUSEID nationally, while the pipeline pairs
within each province. 1,187 HOUSEIDs are reused for different addresses in
different provinces, so this script's survivors land a few hundred below the
shipped matched-pair total (355 on 2026-09-25). It also does not require a
province, so candidates can be slightly higher than the funnel's "Both D&E"
number (build_fsa_audit_totals.py only counts homes carrying a province).

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
          'TYPEOFHOUSE', 'STOREYS', 'NUMDWELLINGUNITS', 'WTHDATA']

# home[hid] = [nD, nE, d_best, e_best]
#   d_best = (entrydate, area, typeofhouse, storeys, numdwellingunits) of the
#            OLDEST D seen so far; e_best = same shape for the NEWEST E seen.
#   Matches build_pairs_index's dropna(ENTRYDATE) + sort + drop_duplicates
#   (oldest D, newest E) -- rows with no ENTRYDATE never win a slot, same as
#   the pipeline dropping them before the sort.
# Low-cardinality categoricals are interned to keep the ~2M-home dict small.
def rec(entrydate, area, htype, storeys, dwell, wth=None):
    return (entrydate, area,
            sys.intern(htype) if htype else htype,
            sys.intern(storeys) if storeys else storeys,
            sys.intern(dwell) if dwell else dwell,
            sys.intern(wth) if wth else wth)


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
        hids = pc.replace_substring_regex(pc.utf8_trim_whitespace(tbl.column('HOUSEID')), r'\.0+$', '').to_pylist()
        ets  = tbl.column('EVALTYPE').to_pylist()
        dts  = col(tbl, 'ENTRYDATE'); fas = col(tbl, 'FLOORAREA')
        tys  = col(tbl, 'TYPEOFHOUSE'); sts = col(tbl, 'STOREYS'); dws = col(tbl, 'NUMDWELLINGUNITS'); wts = col(tbl, 'WTHDATA')
        for hid, et_v, dt, fa, ty, st, dw, wt in zip(hids, ets, dts, fas, tys, sts, dws, wts):
            if not hid or not dt:
                continue
            r = home.get(hid)
            if r is None:
                r = home[hid] = [0, 0, None, None]
            if et_v == 'D':
                r[0] += 1
                if r[2] is None or dt < r[2][0]:
                    r[2] = rec(dt, fa, ty, st, dw, wt)
            else:
                r[1] += 1
                if r[3] is None or dt > r[3][0]:
                    r[3] = rec(dt, fa, ty, st, dw, wt)
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

    # ---- Gate A: reduce each home to oldest-D + newest-E (matches build_pairs_index) ----
    candidates = 0
    d_dates, e_dates, d_areas, e_areas = [], [], [], []
    d_ty, e_ty, d_st, e_st, d_dw, e_dw = [], [], [], [], [], []
    d_wt, e_wt = [], []
    for nD, nE, dtup, etup in home.values():
        if dtup is not None and etup is not None:
            candidates += 1
            d_dates.append(dtup[0]); e_dates.append(etup[0])
            d_areas.append(dtup[1]); e_areas.append(etup[1])
            d_ty.append(dtup[2]);    e_ty.append(etup[2])
            d_st.append(dtup[3]);    e_st.append(etup[3])
            d_dw.append(dtup[4]);    e_dw.append(etup[4])
            d_wt.append(dtup[5]);    e_wt.append(etup[5])
    del home

    # ---- Gate B: E not dated before D (NaT -> fails, as in the pipeline) ----
    dd = pd.to_datetime(pd.Series(d_dates), errors='coerce')
    ed = pd.to_datetime(pd.Series(e_dates), errors='coerce')
    pass_b = (ed >= dd).fillna(False).to_numpy()
    same_month = int(((ed == dd).fillna(False)).sum())

    # ---- Gate C: floor area within +/-5%, D area > 0 ----
    fad = to_float(d_areas); fae = to_float(e_areas)
    area_chg = (fae - fad).abs() / fad
    pass_c = ((fad > 0) & (area_chg <= 0.05)).fillna(False).to_numpy()
    band_5_10 = ((fad > 0) & (area_chg > 0.05) & (area_chg <= 0.10)).fillna(False).to_numpy()

    # ---- Gate D: type / storeys / dwellings unchanged ----
    # Matches ers_web_pipeline.py's same_categorical/same_numeric (fix applied
    # 2026-07-18): both-missing counts as unchanged; NUMDWELLINGUNITS tolerates
    # text-format differences ('1.0' vs '1'). A raw str-equality compare (the
    # old version of this script) over-drops on both-blank and .0-suffix pairs.
    def _same_categorical(lst_d, lst_e):
        a = pd.Series(lst_d).astype(str).str.strip()
        b = pd.Series(lst_e).astype(str).str.strip()
        a = a.mask(a.isin(['', 'nan', 'None']))
        b = b.mask(b.isin(['', 'nan', 'None']))
        both_na = a.isna() & b.isna()
        # Case-insensitive (pipeline, 2026-09-25): 'Single detached' ==
        # 'Single Detached'.
        return (both_na | (a.str.lower() == b.str.lower())).fillna(False).to_numpy()

    def _same_numeric(lst_d, lst_e):
        # One-side-missing counts as unchanged too (pipeline rule since
        # 2026-09-25): only two recorded values that differ are a change.
        # 0 units also counts as not recorded (pipeline, 2026-09-25).
        an = to_float(lst_d); bn = to_float(lst_e)
        an, bn = an.mask(an == 0), bn.mask(bn == 0)
        return (an.isna() | bn.isna() | (an == bn)).fillna(False).to_numpy()

    ty_same = _same_categorical(d_ty, e_ty)
    st_same = _same_categorical(d_st, e_st)
    dw_same = _same_numeric(d_dw, e_dw)
    pass_d = ty_same & st_same & dw_same

    # ---- First-failing-gate attribution (sequential, sums exactly) ----
    drop_date  = int((~pass_b).sum())
    reach_c    = pass_b
    drop_area  = int((reach_c & ~pass_c).sum())
    drop_area_band = int((reach_c & band_5_10).sum())
    reach_d    = reach_c & pass_c
    drop_struct = int((reach_d & ~pass_d).sum())
    def _wnorm(l):
        s = pd.Series(l).astype(str).str.strip()
        return s.mask(s.isin(['', 'nan', 'None', 'Not Applicable']))
    wd, we = _wnorm(d_wt), _wnorm(e_wt)
    pass_e = ~(wd.notna() & we.notna() & (wd != we)).to_numpy()
    reach_e = reach_d & pass_d
    drop_wth = int((reach_e & ~pass_e).sum())
    survivors  = int((reach_e & pass_e).sum())

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
    line("Candidates (oldest-D + newest-E per home)", candidates, candidates)
    print("  " + "-" * 60)
    line("B  dropped: E dated before D", drop_date, candidates)
    line("C  dropped: floor area changed >5%", drop_area, candidates)
    line("   of which 5-10% (new under 5% rule)", drop_area_band, candidates)
    line("D  dropped: type/storeys/dwellings changed", drop_struct, candidates)
    line("E  dropped: weather file changed", drop_wth, candidates)
    print("  " + "-" * 60)
    line("MATCHED PAIRS (survivors)", survivors, candidates)
    print("\n  Structural (gate D) sub-reasons, among the",
          f"{int(among.sum()):,} homes reaching gate D")
    print("  (not mutually exclusive — a home can fail more than one):")
    for k, v in sorted(sub.items(), key=lambda kv: -kv[1]):
        d = int(among.sum())
        print(f"    {k:<26} {v:>10,}  {v/d*100:5.1f}%" if d else f"    {k}: -")

    print(f"\n  Same-month D/E pairs (kept since 2026-09-23): {same_month:,}")

    drops = drop_date + drop_area + drop_struct + drop_wth
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
