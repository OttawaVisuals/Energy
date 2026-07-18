"""
DIAGNOSTIC (not part of the production pipeline).

Follow-up to diagnose_pairing_drops.py, digging into gates A and B of the D&E
pairing funnel:

  GATE A (149,145 dropped): homes with >1 D or >1 E audit. The pipeline requires
    EXACTLY one D + one E. Question: distribution of (#D, #E) among these — how
    many are "extra D only" / "extra E only" / both, to judge whether an
    oldest-D + newest-E rule would recover them. Also: how many would satisfy
    date order (newest E dated after oldest D) under that rule.

  GATE B (84,755 dropped): exact-1D-1E homes where E is not dated after D. Is
    this a real error (E genuinely before/same-day as D) or a format artifact
    (unparseable dates)? Categorize the failures and show raw date pairs.

One streaming pass over C:\\ERS, three columns (HOUSEID, EVALTYPE, ENTRYDATE).
Read-only. Per home we keep (#D, #E, earliest D date, latest E date); date
strings are interned (low cardinality) to keep the ~2M-home dict small.
"""

import os
import sys
from collections import Counter

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
NEEDED = ['HOUSEID', 'EVALTYPE', 'ENTRYDATE']


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
        dts  = (tbl.column('ENTRYDATE').to_pylist()
                if 'ENTRYDATE' in present else [None] * tbl.num_rows)
        for hid, et_v, dt in zip(hids, ets, dts):
            if not hid:
                continue
            dt = sys.intern(dt) if dt else None
            r = home.get(hid)
            if r is None:
                r = home[hid] = [0, 0, None, None]   # nD, nE, earliestD, latestE
            if et_v == 'D':
                r[0] += 1
                if dt is not None and (r[2] is None or dt < r[2]):
                    r[2] = dt
            else:
                r[1] += 1
                if dt is not None and (r[3] is None or dt > r[3]):
                    r[3] = dt
            n += 1
    return n


def main():
    home = {}
    for name in CSV_FILES:
        path = os.path.join(INPUT_DIR, name)
        if not os.path.exists(path):
            print(f"  -- {name}: not found"); continue
        c = scan_file(path, home)
        print(f"  {name}: {c:,} D/E rows  (unique homes so far: {len(home):,})")

    # Split candidates (>=1 D and >=1 E) into exact-1+1 vs multiple.
    combo = Counter()                 # (nD,nE) among MULTIPLE homes
    candidates = multiple = exact = 0
    ex_dD, ex_dE = [], []             # exact-home earliest-D / latest-E dates
    mu_dD, mu_dE = [], []             # multiple-home earliest-D / latest-E dates
    for nD, nE, dD, eE in home.values():
        if nD >= 1 and nE >= 1:
            candidates += 1
            if nD == 1 and nE == 1:
                exact += 1
                ex_dD.append(dD); ex_dE.append(eE)
            else:
                multiple += 1
                combo[(min(nD, 6), min(nE, 6))] += 1   # cap at 6+ for a compact table
                mu_dD.append(dD); mu_dE.append(eE)
    del home

    # ---------------- GATE A ----------------
    extra_d = sum(v for (d, e), v in combo.items() if d > 1 and e == 1)
    extra_e = sum(v for (d, e), v in combo.items() if d == 1 and e > 1)
    both    = sum(v for (d, e), v in combo.items() if d > 1 and e > 1)
    print("\n" + "=" * 62)
    print(f"GATE A — multiple-audit homes ({multiple:,} of {candidates:,} candidates)")
    print("=" * 62)
    print(f"  extra D only (>1 D, 1 E): {extra_d:>10,}  {extra_d/multiple*100:4.1f}%")
    print(f"  extra E only (1 D, >1 E): {extra_e:>10,}  {extra_e/multiple*100:4.1f}%")
    print(f"  both >1                 : {both:>10,}  {both/multiple*100:4.1f}%")
    print("  (#D, #E) distribution [6 = 6-or-more]:")
    for (d, e), v in combo.most_common(15):
        dl = f"{d}+" if d == 6 else str(d)
        el = f"{e}+" if e == 6 else str(e)
        print(f"    D={dl:<3} E={el:<3} {v:>10,}  {v/multiple*100:4.1f}%")

    # Under an oldest-D + newest-E rule, how many multiple homes would clear the
    # date-order gate (latest E strictly after earliest D)?
    md = pd.to_datetime(pd.Series(mu_dD), errors='coerce')
    me = pd.to_datetime(pd.Series(mu_dE), errors='coerce')
    ok = (me > md).fillna(False)
    print(f"\n  If reduced to oldest-D + newest-E, date-order (newest E > oldest D):")
    print(f"    would pass: {int(ok.sum()):,}  ({ok.mean()*100:.1f}%)  "
          f"| fail/unparseable: {int((~ok).sum()):,}")
    print("    (these would still face the floor-area + structural gates)")

    # ---------------- GATE B ----------------
    dd = pd.to_datetime(pd.Series(ex_dD), errors='coerce')
    ee = pd.to_datetime(pd.Series(ex_dE), errors='coerce')
    pass_b = (ee > dd).fillna(False)
    failb = ~pass_b
    nfail = int(failb.sum())
    unparse = (dd.isna() | ee.isna())
    same_day = (~unparse) & (ee == dd)
    reversed_ = (~unparse) & (ee < dd)
    print("\n" + "=" * 62)
    print(f"GATE B — exact-1+1 homes where E not after D "
          f"({nfail:,} of {exact:,} exact homes)")
    print("=" * 62)
    cats = {
        'unparseable date(s) (format/missing)': int((failb & unparse).sum()),
        'same calendar day (E == D)':           int((failb & same_day).sum()),
        'E genuinely before D':                 int((failb & reversed_).sum()),
    }
    for k, v in cats.items():
        print(f"    {k:<40} {v:>9,}  {v/nfail*100:4.1f}%" if nfail else f"    {k}: -")
    # raw examples of the failing date pairs
    draw = pd.Series(ex_dD)[failb.to_numpy()]
    eraw = pd.Series(ex_dE)[failb.to_numpy()]
    top = Counter(zip((repr(x) for x in draw), (repr(x) for x in eraw))).most_common(10)
    print("  top raw (D date -> E date) pairs among failures:")
    for (a, b), c in top:
        print(f"    {a:>13} -> {b:<13} {c:>8,}  {c/nfail*100:4.1f}%")


if __name__ == '__main__':
    main()
