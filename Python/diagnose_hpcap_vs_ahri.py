"""
DIAGNOSTIC (not part of the production pipeline).

How far off is the raw auditor-entered HPCAP field from the AHRI certificate?

docs/RETROFITS.md and join_hp_capacity.py's docstring both state that HPCAP
(Watts, auditor-entered) "runs a median 1.55x high" against real AHRI
certificates and is unreliable for a sizing claim -- this script reproduces
that comparison end to end and adds a distribution/histogram, plus the same
comparison for COP (with a caveat: the AHRI lookup only carries a certified
COP at 5F, and the raw COP field's own rating condition is undocumented, so
that comparison is weaker evidence than the capacity one).

Not run against the committed parquet files: HPCAP was deliberately left out
of ers_web_pipeline.py's BASE_MAPPING (see join_hp_capacity.py docstring), so
it never reached them. This streams HPCAP/AHRI/COP straight from the raw E-row
CSVs and joins them against lookup/ahri_numbers.json directly -- the same
lookup join_hp_capacity.py uses for the committed Post_HPCapacity47 field.

INPUT:  C:\\ERS\\*.csv (E rows only, 4 columns)
        lookup/ahri_numbers.json
OUTPUT: printed distribution summary
        <scratchpad>/hpcap_vs_ahri.png (capacity-ratio histogram + COP scatter)
"""

import json
import os
import sys
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
NEEDED = ['HOUSEID', 'EVALTYPE', 'HPCAP', 'AHRI', 'COP']

REPO_ROOT = Path(__file__).resolve().parent.parent
LOOKUP_PATH = REPO_ROOT / "lookup" / "ahri_numbers.json"
OUT_PNG = Path(os.environ.get("SCRATCHPAD_DIR", str(REPO_ROOT))) / "hpcap_vs_ahri.png"

BTUH_TO_KW = 0.00029307107


def clean_ahri(s):
    """Mirrors ers_web_pipeline.py's clean_ahri / join_hp_capacity.py's clean_ahri."""
    s = s.astype(str).str.strip()
    s = s.str.replace(r'\.0+$', '', regex=True)
    return s.replace({'': None, 'nan': None, 'None': None, 'NaN': None, '0': None})


def scan_file(csv_path, rows):
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
        tbl = tbl.filter(pc.equal(tbl.column('EVALTYPE'), 'E'))
        if tbl.num_rows == 0:
            continue
        hids  = tbl.column('HOUSEID').to_pylist()
        hpcap = col(tbl, 'HPCAP')
        ahri  = col(tbl, 'AHRI')
        cop   = col(tbl, 'COP')
        for hid, hc, ah, cp in zip(hids, hpcap, ahri, cop):
            if not hid or not hc or not ah:
                continue
            rows.append((hid, hc, ah, cp))
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
        print(f"  {name}: {c:,} E rows with HPCAP+AHRI  (total so far: {len(rows):,})")

    df = pd.DataFrame(rows, columns=['HOUSEID', 'HPCAP', 'AHRI', 'COP'])
    del rows
    n_with_ahri = len(df)
    print(f"\nE-row records with both HPCAP and an AHRI number: {n_with_ahri:,}")

    df['AHRI_clean'] = clean_ahri(df['AHRI'])
    df = df.dropna(subset=['AHRI_clean'])
    print(f"  after dropping placeholder/blank AHRI ('0', '', NaN): {len(df):,}")

    def cert_cap47_kw(code):
        entry = lookup.get(code)
        if not entry:
            return np.nan
        v = entry.get('heating_capacity_47f_btuh')
        try:
            return float(str(v).replace(',', '')) * BTUH_TO_KW
        except (TypeError, ValueError):
            return np.nan

    def cert_cop5(code):
        entry = lookup.get(code)
        if not entry:
            return np.nan
        v = entry.get('heating_cop_5f')
        try:
            return float(str(v).replace(',', ''))
        except (TypeError, ValueError):
            return np.nan

    df['cert_cap47_kw'] = df['AHRI_clean'].map(cert_cap47_kw)
    df['cert_cop5'] = df['AHRI_clean'].map(cert_cop5)
    n_resolved = df['cert_cap47_kw'].notna().sum()
    print(f"  resolve to a certificate with a 47F capacity: {n_resolved:,} "
          f"({100*n_resolved/len(df):.1f}%)")

    # --- Capacity comparison: HPCAP (Watts, auditor) vs cert 47F capacity (kW) ---
    cap = df.dropna(subset=['cert_cap47_kw']).copy()
    cap['hpcap_kw'] = pd.to_numeric(cap['HPCAP'], errors='coerce') / 1000.0
    cap = cap[(cap['hpcap_kw'] > 0) & (cap['cert_cap47_kw'] > 0)]
    cap['ratio'] = cap['hpcap_kw'] / cap['cert_cap47_kw']
    n_cap = len(cap)

    print("\n" + "=" * 64)
    print(f"CAPACITY: auditor HPCAP (kW) / AHRI-certified 47F capacity (kW)")
    print("=" * 64)
    print(f"  usable pairs: {n_cap:,}")
    print(f"  median ratio: {cap['ratio'].median():.3f}")
    print(f"  IQR: [{cap['ratio'].quantile(0.25):.3f}, {cap['ratio'].quantile(0.75):.3f}]")
    print(f"  10-90pct: [{cap['ratio'].quantile(0.10):.3f}, {cap['ratio'].quantile(0.90):.3f}]")

    buckets = [
        ("< 0.5x", cap['ratio'] < 0.5),
        ("0.5x - 0.9x", (cap['ratio'] >= 0.5) & (cap['ratio'] < 0.9)),
        ("~1x (0.9-1.1)", (cap['ratio'] >= 0.9) & (cap['ratio'] < 1.1)),
        ("1.1x - 1.9x", (cap['ratio'] >= 1.1) & (cap['ratio'] < 1.9)),
        ("~2x (1.9-2.1)", (cap['ratio'] >= 1.9) & (cap['ratio'] < 2.1)),
        ("2.1x - 3.9x", (cap['ratio'] >= 2.1) & (cap['ratio'] < 3.9)),
        ("~4x (3.9-4.1)", (cap['ratio'] >= 3.9) & (cap['ratio'] < 4.1)),
        ("> 4.1x", cap['ratio'] >= 4.1),
    ]
    print("\n  ratio buckets (checking the 1x/2x/4x clustering docs mention):")
    for label, mask in buckets:
        c = int(mask.sum())
        print(f"    {label:<16} {c:>10,}  {100*c/n_cap:5.1f}%")

    # Same AHRI number, multiple rows -> how often does HPCAP disagree with
    # itself across different audit rows for the SAME certified unit?
    g = cap.groupby('AHRI_clean')['ratio'].agg(['count', 'std'])
    multi = g[g['count'] >= 2]
    print(f"\n  AHRI codes appearing >=2 times: {len(multi):,} "
          f"(covering {int(multi['count'].sum()):,} rows)")
    if len(multi):
        inconsistent = (multi['std'] > 0.15)
        print(f"    of those, ratio std > 0.15 across rows (inconsistent HPCAP "
              f"for the SAME cert): {int(inconsistent.sum()):,} "
              f"({100*inconsistent.mean():.1f}%)")

    # --- COP comparison: raw COP (auditor) vs cert 5F COP ---
    print("\n" + "=" * 64)
    print("COP: raw auditor COP field vs AHRI-certified COP at 5F")
    print("  CAVEAT: the raw COP field's own rating condition is undocumented")
    print("  (nrcan_data_dictionary.csv just says 'Heat pump coefficient of")
    print("  performance'), unlike HPCAP which is unambiguously Watts. This")
    print("  comparison is weaker evidence than the capacity one above --")
    print("  a mismatch could reflect a different test condition, not error.")
    print("=" * 64)
    copdf = df.dropna(subset=['cert_cop5']).copy()
    copdf['cop_raw'] = pd.to_numeric(copdf['COP'], errors='coerce')
    copdf = copdf[(copdf['cop_raw'] > 0) & (copdf['cert_cop5'] > 0)]
    n_cop = len(copdf)
    if n_cop:
        copdf['diff'] = copdf['cop_raw'] - copdf['cert_cop5']
        copdf['ratio'] = copdf['cop_raw'] / copdf['cert_cop5']
        print(f"  usable pairs: {n_cop:,}")
        print(f"  median auditor COP: {copdf['cop_raw'].median():.2f}  "
              f"median cert COP@5F: {copdf['cert_cop5'].median():.2f}")
        print(f"  median ratio (auditor/cert): {copdf['ratio'].median():.3f}")
        print(f"  median absolute difference: {copdf['diff'].abs().median():.3f}")
        print(f"  IQR of difference: [{copdf['diff'].quantile(0.25):.3f}, "
              f"{copdf['diff'].quantile(0.75):.3f}]")
    else:
        print("  no usable pairs (COP field mostly blank in this slice)")

    # --- Chart ---
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(1, 2, figsize=(12, 5))

    ax = axes[0]
    ax.hist(cap['ratio'].clip(0, 6), bins=120, color="#3D8065")
    for x, lbl in [(1, "1x"), (2, "2x"), (4, "4x")]:
        ax.axvline(x, color="#999", linestyle="--", linewidth=1)
        ax.text(x, ax.get_ylim()[1] * 0.95, lbl, ha="center", fontsize=9, color="#666")
    ax.set_xlabel("Auditor HPCAP / AHRI-certified 47F capacity")
    ax.set_ylabel("count")
    ax.set_title(f"Capacity ratio (n={n_cap:,})\nmedian={cap['ratio'].median():.2f}")

    ax = axes[1]
    if n_cop:
        ax.scatter(copdf['cert_cop5'], copdf['cop_raw'], s=6, alpha=0.15, color="#3D8065")
        lims = [0, max(copdf['cert_cop5'].max(), copdf['cop_raw'].max()) * 1.05]
        ax.plot(lims, lims, "--", color="#999", linewidth=1, label="auditor = cert")
        ax.set_xlim(lims); ax.set_ylim(lims)
        ax.set_xlabel("AHRI-certified COP @ 5F")
        ax.set_ylabel("Auditor-entered COP (rating condition undocumented)")
        ax.set_title(f"COP: auditor vs cert (n={n_cop:,})")
        ax.legend(loc="upper left", fontsize=9)
    else:
        ax.set_title("COP: no usable pairs")

    fig.tight_layout()
    OUT_PNG.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT_PNG, dpi=140)
    print(f"\n[out] wrote {OUT_PNG}")


if __name__ == '__main__':
    main()
