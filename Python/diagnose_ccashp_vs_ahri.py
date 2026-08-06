"""
DIAGNOSTIC (not part of the production pipeline).

Follow-up to diagnose_hpcap_vs_ahri.py. Two things:

1. Top-10 most frequent AHRI codes among matched E-rows, with the AHRI
   certificate's COP@5F alongside the raw auditor-entered COP (both the
   generic `COP` field and the cold-climate-specific `CCASHPCOP` field,
   which the ERS data dictionary documents as ALSO rated at -15C/5F) --
   for manual cross-checking against NEEP's own database.

2. Capacity-maintenance comparison: the ERS field CCASHPCAPACITYMAINTENANCE
   is auditor-entered "Max -15C(5F) / Rated 8.3C(47F)" capacity ratio, as a
   percentage. The AHRI certificate carries both heating_capacity_47f_btuh
   and heating_capacity_5f_btuh directly, so a certified equivalent can be
   computed as cap5f/cap47f*100 and compared the same way the HPCAP/AHRI
   capacity ratio was in diagnose_hpcap_vs_ahri.py.

Unlike the generic HPCAP/COP fields (whose rating condition is undocumented),
CCASHPCAP/CCASHPCAPACITYMAINTENANCE/CCASHPCOP have explicit, matching AHRI-style
conditions in nrcan_data_dictionary.csv (CAP at 47F, CAPACITYMAINTENANCE and COP
at 5F) -- this is a cleaner apples-to-apples comparison than the earlier one.

INPUT:  C:\\ERS\\*.csv (E rows with CCASHP='T', 8 columns)
        lookup/ahri_numbers.json
OUTPUT: printed top-10 table + capacity-maintenance distribution summary
        <scratchpad>/ccashp_maintenance_vs_ahri.png (histogram)
"""

import json
import os
from pathlib import Path

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
NEEDED = ['HOUSEID', 'EVALTYPE', 'CCASHP', 'AHRI', 'CCASHPCAP',
          'CCASHPCAPACITYMAINTENANCE', 'CCASHPCOP', 'COP']

REPO_ROOT = Path(__file__).resolve().parent.parent
LOOKUP_PATH = REPO_ROOT / "lookup" / "ahri_numbers.json"
OUT_PNG = Path(os.environ.get("SCRATCHPAD_DIR", str(REPO_ROOT))) / "ccashp_maintenance_vs_ahri.png"

BTUH_TO_KW = 0.00029307107


def clean_ahri(s):
    s = s.astype(str).str.strip()
    s = s.str.replace(r'\.0+$', '', regex=True)
    return s.replace({'': None, 'nan': None, 'None': None, 'NaN': None, '0': None})


def scan_file(csv_path, rows):
    with open(csv_path, 'r', encoding='utf-8', errors='replace') as f:
        header = [h.strip().strip('"') for h in f.readline().strip().split(',')]
    present = [c for c in NEEDED if c in header]
    if 'EVALTYPE' not in present or 'HOUSEID' not in present or 'CCASHP' not in present:
        print(f"  !! {os.path.basename(csv_path)}: missing required columns — skipping")
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
        tbl = tbl.filter(pc.and_(pc.equal(tbl.column('EVALTYPE'), 'E'),
                                  pc.equal(tbl.column('CCASHP'), 'T')))
        if tbl.num_rows == 0:
            continue
        hids  = tbl.column('HOUSEID').to_pylist()
        ahri  = col(tbl, 'AHRI')
        cap   = col(tbl, 'CCASHPCAP')
        maint = col(tbl, 'CCASHPCAPACITYMAINTENANCE')
        cccop = col(tbl, 'CCASHPCOP')
        cop   = col(tbl, 'COP')
        for hid, ah, cp, mt, ccc, cg in zip(hids, ahri, cap, maint, cccop, cop):
            if not hid or not ah:
                continue
            rows.append((hid, ah, cp, mt, ccc, cg))
            n += 1
    return n


def main():
    if not LOOKUP_PATH.exists():
        print(f"!! {LOOKUP_PATH} not found -- run build_ahri_lookup_full.py first")
        return
    with open(LOOKUP_PATH, encoding='utf-8') as f:
        lookup = json.load(f)
    print(f"loaded {len(lookup):,} AHRI entries from {LOOKUP_PATH}")

    rows = []
    for name in CSV_FILES:
        path = os.path.join(INPUT_DIR, name)
        if not os.path.exists(path):
            print(f"  -- {name}: not found"); continue
        c = scan_file(path, rows)
        print(f"  {name}: {c:,} CC-ASHP E rows with an AHRI value  (total so far: {len(rows):,})")

    df = pd.DataFrame(rows, columns=['HOUSEID', 'AHRI', 'CCASHPCAP',
                                      'CCASHPCAPACITYMAINTENANCE', 'CCASHPCOP', 'COP'])
    del rows
    df['AHRI_clean'] = clean_ahri(df['AHRI'])
    df = df.dropna(subset=['AHRI_clean'])
    print(f"\ncold-climate-ASHP E rows with a usable AHRI code: {len(df):,}")

    def cert(code, field):
        entry = lookup.get(code)
        if not entry:
            return np.nan
        v = entry.get(field)
        try:
            return float(str(v).replace(',', ''))
        except (TypeError, ValueError):
            return np.nan

    df['cert_cap47_btuh'] = df['AHRI_clean'].map(lambda c: cert(c, 'heating_capacity_47f_btuh'))
    df['cert_cap5_btuh']  = df['AHRI_clean'].map(lambda c: cert(c, 'heating_capacity_5f_btuh'))
    df['cert_cop5']       = df['AHRI_clean'].map(lambda c: cert(c, 'heating_cop_5f'))
    df['brand'] = df['AHRI_clean'].map(lambda c: (lookup.get(c) or {}).get('brand'))
    df['model'] = df['AHRI_clean'].map(lambda c: (lookup.get(c) or {}).get('model'))

    # =========================================================================
    # PART 1: top-10 most frequent AHRI codes
    # =========================================================================
    print("\n" + "=" * 90)
    print("TOP 10 MOST FREQUENT AHRI CODES (cold-climate-ASHP E rows)")
    print("=" * 90)
    counts = df['AHRI_clean'].value_counts().head(10)
    df['cop_raw_n'] = pd.to_numeric(df['COP'], errors='coerce')
    df['cccop_raw_n'] = pd.to_numeric(df['CCASHPCOP'], errors='coerce')
    for code, n in counts.items():
        sub = df[df['AHRI_clean'] == code]
        cert5 = sub['cert_cop5'].iloc[0]
        brand = sub['brand'].iloc[0]
        model = sub['model'].iloc[0]
        cop_vals = sub['cop_raw_n'].dropna()
        cccop_vals = sub['cccop_raw_n'].dropna()
        print(f"\nAHRI {code}  ({brand} {model})  -- {n:,} rows")
        print(f"  AHRI cert COP@5F:        {cert5}")
        if len(cccop_vals):
            print(f"  CCASHPCOP reported (n={len(cccop_vals)}):  "
                  f"median {cccop_vals.median():.2f}, "
                  f"range [{cccop_vals.min():.2f}, {cccop_vals.max():.2f}]")
        else:
            print("  CCASHPCOP reported: (no numeric values)")
        if len(cop_vals):
            print(f"  generic COP reported (n={len(cop_vals)}):  "
                  f"median {cop_vals.median():.2f}, "
                  f"range [{cop_vals.min():.2f}, {cop_vals.max():.2f}]")
        else:
            print("  generic COP reported: (no numeric values)")

    # =========================================================================
    # PART 2: capacity-maintenance comparison
    # =========================================================================
    print("\n" + "=" * 90)
    print("CAPACITY MAINTENANCE: auditor CCASHPCAPACITYMAINTENANCE (%) vs "
          "AHRI-certified 5F/47F (%)")
    print("=" * 90)
    m = df.dropna(subset=['cert_cap47_btuh', 'cert_cap5_btuh']).copy()
    m = m[(m['cert_cap47_btuh'] > 0)]
    m['cert_maint_pct'] = 100.0 * m['cert_cap5_btuh'] / m['cert_cap47_btuh']
    m['auditor_maint_pct'] = pd.to_numeric(m['CCASHPCAPACITYMAINTENANCE'], errors='coerce')
    m = m[(m['auditor_maint_pct'] > 0) & (m['auditor_maint_pct'] < 300)]
    n_m = len(m)
    m['diff_pp'] = m['auditor_maint_pct'] - m['cert_maint_pct']
    m['ratio'] = m['auditor_maint_pct'] / m['cert_maint_pct']

    print(f"  usable pairs: {n_m:,}")
    print(f"  median cert maintenance:    {m['cert_maint_pct'].median():.1f}%")
    print(f"  median auditor maintenance: {m['auditor_maint_pct'].median():.1f}%")
    print(f"  median difference (auditor - cert): {m['diff_pp'].median():+.1f} pp")
    print(f"  IQR of difference: [{m['diff_pp'].quantile(0.25):+.1f}, "
          f"{m['diff_pp'].quantile(0.75):+.1f}] pp")
    print(f"  median ratio (auditor/cert): {m['ratio'].median():.3f}")
    print(f"  share within +/-5pp of cert:  {100*(m['diff_pp'].abs() <= 5).mean():.1f}%")
    print(f"  share within +/-10pp of cert: {100*(m['diff_pp'].abs() <= 10).mean():.1f}%")

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(1, 2, figsize=(12, 5))

    ax = axes[0]
    ax.hist(m['diff_pp'].clip(-100, 100), bins=100, color="#3D8065")
    ax.axvline(0, color="#999", linestyle="--", linewidth=1)
    ax.set_xlabel("Auditor CCASHPCAPACITYMAINTENANCE − AHRI-certified (percentage points)")
    ax.set_ylabel("count")
    ax.set_title(f"Capacity-maintenance difference (n={n_m:,})\n"
                 f"median={m['diff_pp'].median():+.1f}pp")

    ax = axes[1]
    ax.scatter(m['cert_maint_pct'], m['auditor_maint_pct'], s=6, alpha=0.15, color="#3D8065")
    lims = [0, max(m['cert_maint_pct'].max(), m['auditor_maint_pct'].max()) * 1.05]
    ax.plot(lims, lims, "--", color="#999", linewidth=1, label="auditor = cert")
    ax.set_xlim(lims); ax.set_ylim(lims)
    ax.set_xlabel("AHRI-certified capacity maintenance (%)")
    ax.set_ylabel("Auditor CCASHPCAPACITYMAINTENANCE (%)")
    ax.set_title(f"Auditor vs cert (n={n_m:,})")
    ax.legend(loc="upper left", fontsize=9)

    fig.tight_layout()
    OUT_PNG.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT_PNG, dpi=140)
    print(f"\n[out] wrote {OUT_PNG}")


if __name__ == '__main__':
    main()
