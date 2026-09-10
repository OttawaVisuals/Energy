"""
ahri_export.py

One-off analytical export of every AHRI-certificate-bearing audit record in
the ERS corpus, for HVAC-design analysis: what heat pump was actually
selected, against what the house's design load and heating consumption were
at that same audit.

Built 2026-09-10 at the request of an external collaborator interested in
HVAC design/sizing data. Not part of the Retrofit Explorer web pipeline --
this reads the raw ERS CSVs directly and writes plain CSVs for offline use.

WHY RAW CSVs AND NOT THE PAIRED WEB PARQUET
    C:\\ERS\\web\\ers_web_<PT>.parquet is a D->E *paired* dataset: only homes
    with both a pre- and a post-retrofit audit survive its pairing gates. It
    carries ~312k AHRI records against 443k in the raw corpus -- a ~30% loss,
    mostly homes audited once and never followed up. It also omits Yukon
    entirely (YK is absent from ers_web_pipeline.py's ALL_PROVINCES list
    though it is present in the source data). For a sizing question, every
    audit record that names a heat pump is in scope, so this script goes to
    the source and emits one row per audit record.

RECORD UNIVERSE
    Every row of every C:\\ERS\\<year>.csv whose AHRI column matches
    ^\\d{7,10}$ after stripping a trailing '.0'. That gate is the one
    build_ahri_lookup_full.py validated against a full-corpus scan: it
    cleanly separates real certificate IDs from the '0' no-heat-pump
    placeholder (~1.2M rows) and short junk values ('12345', '210', ...).
    All four EVALTYPEs are kept and flagged:
        D = pre-retrofit audit (an existing heat pump found at audit)
        E = post-retrofit audit (the heat pump installed)
        P = new construction, plan
        N = new construction, as-built

INPUTS
    C:\\ERS\\<year>.csv        raw ERS corpus, 21 files, ~8.4 GB (local only)
    lookup/ahri_numbers.json  AHRI directory certificates, 15,149 entries,
                              built by build_ahri_lookup_full.py and kept
                              current by refresh_ahri_lookup.py

OUTPUTS  (C:\\ERS\\ahri_export\\)
    ahri_by_year_<PT>.csv          audit year x EVALTYPE counts, per province
    ahri_detail_<PT>.csv           one row per AHRI-bearing audit record
    ahri_canada_directory.csv      one row per distinct AHRI number, national
                                   count + per-province counts + the full
                                   directory certificate record
    ahri_column_availability.csv   per-year fill rate of every source column,
                                   among AHRI-bearing rows
    ahri_export_README.md          field definitions and the caveats that
                                   matter for sizing work (written by hand,
                                   not by this script)

CAVEATS THAT MATTER  (repeated in the README that ships with the output)
    - EGHDESHTLOSS is HOT2000 design heat loss GROSS of internal and solar
      gains. Right basis for F280-style sizing; ~23% above the load implied
      by ERS standard operating conditions, so SizingRatio_* reads low if
      compared against a gains-inclusive design load.
    - HPCAP runs ~1.55x the AHRI certificate rating and is not usable as a
      capacity. CCASHPCAP is certificate-validated but exists only for
      ccASHP records from 2021 onward. The Cert_Cap* columns from the
      directory join are the reliable capacity figures.
    - FURNACETYPE / FURNACEFUEL describe the BACKUP heat, not the heat pump.
      SUPPHTGTYPE1 is supplementary heating, which is not the same thing as
      heat-pump backup either.
    - 517 of the 15,666 observed AHRI codes never resolved against the
      directory. They are kept with Cert_Resolved=No and blank cert fields,
      never dropped. Occurrence-weighted certificate coverage is ~99.2%.

Usage:
    python Python/ahri_export.py
"""

import csv
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.csv as pacsv

# =============================================================================
# CONFIG
# =============================================================================

REPO_ROOT = Path(__file__).resolve().parent.parent
INPUT_DIR = Path(r"C:\ERS")
OUTPUT_DIR = Path(r"C:\ERS\ahri_export")
LOOKUP = REPO_ROOT / "lookup" / "ahri_numbers.json"

CSV_FILES = [
    '2004-2006.csv', '2007.csv', '2008.csv', '2009.csv', '2010.csv',
    '2011.csv', '2012.csv', '2013.csv', '2014.csv', '2015.csv',
    '2016.csv', '2017.csv', '2018.csv', '2019.csv', '2020.csv',
    '2021.csv', '2022.csv', '2023.csv', '2024.csv', '2025.csv',
    '2026.csv',
]

AHRI_RE = r'\d{7,10}'

# MJ -> kWh, the same factor ers_web_pipeline.py uses for EGHFCONTOTAL /
# EGHFURNACEAEC / EGHHEATFCONS*.
MJ_TO_KWH = 0.27778
BTUH_TO_KW = 0.00029307107

# =============================================================================
# SOURCE COLUMNS
# =============================================================================

# Read for every row (the denominator of audits per year).
COUNT_COLS = ['PROVINCE', 'EVALTYPE', 'ENTRYDATE', 'AHRI']

# Carried onto AHRI-bearing detail rows, in output order.
IDENTITY_COLS = ['HOUSEID', 'PROVINCE', 'CLIENTPCODE', 'EVALTYPE', 'ENTRYDATE']
HOUSE_COLS = ['TYPEOFHOUSE', 'FLOORAREA', 'STOREYS', 'YEARBUILT',
              'FNDTYPE', 'NUMDWELLINGUNITS', 'AIR50P']
LOAD_COLS = ['EGHDESHTLOSS']
ENERGY_COLS = ['EGHFURNACEAEC', 'EGHFCONTOTAL',
               'EGHHEATFCONSE', 'EGHHEATFCONSG', 'EGHHEATFCONSO',
               'EGHHEATFCONSP', 'EGHHEATFCONSW']
HP_COLS = ['AHRI', 'HPSOURCE', 'HPEquipType', 'HPCAP', 'CCASHP',
           'CCASHPCAP', 'COP', 'CCASHPCOP', 'CCASHPHSPF2',
           'CCASHPSEER2', 'CCASHPCAPACITYMAINTENANCE',
           'ASHPHSPF2', 'ASHPSEER2', 'HPESTAR', 'AIRCONDTYPE', 'AIRCOP']
BACKUP_COLS = ['FURNACETYPE', 'FURNACEFUEL', 'SUPPHTGTYPE1', 'SUPPHTGFUEL1']

DETAIL_SOURCE_COLS = (IDENTITY_COLS + HOUSE_COLS + LOAD_COLS +
                      ENERGY_COLS + HP_COLS + BACKUP_COLS)

READ_COLS = sorted(set(COUNT_COLS) | set(DETAIL_SOURCE_COLS))

# Certificate fields lifted onto each detail row (the compact block; the full
# certificate record goes to ahri_canada_directory.csv).
CERT_DETAIL_FIELDS = [
    ('Cert_Brand', 'brand'),
    ('Cert_Model', 'model'),
    ('Cert_IndoorModel', 'indoor_model'),
    ('Cert_Cap47_btuh', 'heating_capacity_47f_btuh'),
    ('Cert_Cap17_btuh', 'heating_capacity_17f_btuh'),
    ('Cert_Cap5_btuh', 'heating_capacity_5f_btuh'),
    ('Cert_COP5', 'heating_cop_5f'),
    ('Cert_HSPF2', 'hspf2'),
    ('Cert_SEER2', 'seer2'),
    ('Cert_ColdClimate', 'cold_climate'),
]

DETAIL_HEADER = (
    ['HOUSEID', 'PT', 'FSA', 'EVALTYPE', 'ENTRYDATE', 'AuditYear'] +
    HOUSE_COLS +
    ['EGHDESHTLOSS', 'PeakLoad_kW'] +
    ['EGHFURNACEAEC', 'HeatEnergy_kWh', 'EGHFCONTOTAL', 'TotalEnergy_kWh',
     'HeatElectricity_kWh', 'HeatNaturalGas_kWh', 'HeatOil_kWh',
     'HeatPropane_kWh', 'HeatWood_kWh'] +
    HP_COLS +
    BACKUP_COLS +
    ['Cert_Resolved'] + [name for name, _ in CERT_DETAIL_FIELDS] +
    ['Cert_Cap47_kW', 'Cert_Cap5_kW', 'SizingRatio_47F', 'SizingRatio_5F']
)


def num(series):
    """Source columns are read as strings; coerce to float, blanks -> NaN."""
    return pd.to_numeric(series.astype(str).str.strip(), errors='coerce')


def strip_float_artifact(series):
    """Some source years write integer identifiers as floats ('211644151.0').

    Left alone, the same AHRI number counts as two different ones -- confirmed
    for ~20% of ON's unique codes (see ers_web_pipeline.py's note). HOUSEID has
    the same problem and is the join key an analyst will use against other
    extracts, so both go through this.
    """
    return (series.fillna('').astype(str).str.strip()
            .str.replace(r'\.0$', '', regex=True))


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    with open(LOOKUP, encoding='utf-8') as f:
        certs = json.load(f)
    print(f"AHRI directory: {len(certs):,} certificates")

    # --- accumulators -------------------------------------------------------
    audits_total = Counter()              # (PT, AuditYear, EVALTYPE) -> rows
    ahri_records = Counter()              # same key -> AHRI-bearing rows
    ahri_distinct = defaultdict(set)      # same key -> set of AHRI numbers
    number_prov = defaultdict(Counter)    # AHRI number -> Counter of PT
    fill = defaultdict(Counter)           # AuditYear -> column -> populated
    fill_rows = Counter()                 # AuditYear -> AHRI-bearing rows

    writers = {}
    detail_rows = 0

    def writer_for(pt):
        if pt not in writers:
            fh = open(OUTPUT_DIR / f"ahri_detail_{pt}.csv", 'w',
                      newline='', encoding='utf-8')
            w = csv.writer(fh)
            w.writerow(DETAIL_HEADER)
            writers[pt] = (fh, w)
        return writers[pt][1]

    for fname in CSV_FILES:
        path = INPUT_DIR / fname
        if not path.exists():
            print(f"  !! {fname} not found -- skipping")
            continue

        with open(path, 'r', encoding='utf-8', errors='replace') as f:
            header = [h.strip().strip('"')
                      for h in f.readline().strip().split(',')]
        present = [c for c in READ_COLS if c in header]
        missing = [c for c in READ_COLS if c not in header]
        if missing:
            print(f"  !! {fname}: missing columns {missing}")

        reader = pacsv.open_csv(
            path,
            pacsv.ReadOptions(block_size=1 << 23),
            pacsv.ParseOptions(delimiter=','),
            pacsv.ConvertOptions(include_columns=present,
                                 strings_can_be_null=True,
                                 column_types={c: pa.string() for c in present}),
        )

        file_ahri = 0
        for batch in reader:
            df = pa.Table.from_batches([batch]).to_pandas()
            for c in missing:
                df[c] = ''
            df = df.fillna('')

            pt = df['PROVINCE'].str.strip()
            ev = df['EVALTYPE'].str.strip()
            year = df['ENTRYDATE'].str.strip().str[:4]

            # Denominator: every audit record, AHRI or not.
            audits_total.update(zip(pt, year, ev))

            ahri = strip_float_artifact(df['AHRI'])
            mask = ahri.str.fullmatch(AHRI_RE)
            if not mask.any():
                continue

            sub = df[mask].copy()
            sub['_ahri'] = ahri[mask]
            sub['_pt'] = pt[mask]
            sub['_ev'] = ev[mask]
            sub['_year'] = year[mask]

            ahri_records.update(zip(sub['_pt'], sub['_year'], sub['_ev']))
            for k, a in zip(zip(sub['_pt'], sub['_year'], sub['_ev']),
                            sub['_ahri']):
                ahri_distinct[k].add(a)
            for a, p in zip(sub['_ahri'], sub['_pt']):
                number_prov[a][p] += 1

            # Column availability: populated = non-blank and not a bare zero.
            for y, grp in sub.groupby('_year'):
                fill_rows[y] += len(grp)
                for c in DETAIL_SOURCE_COLS:
                    v = grp[c].astype(str).str.strip()
                    populated = ((v != '') & (v != '0') &
                                 (v != '0.0') & (v != '0.00'))
                    fill[y][c] += int(populated.sum())

            # --- assemble the detail rows ---
            deshtloss = num(sub['EGHDESHTLOSS'])
            out = pd.DataFrame({
                'HOUSEID': strip_float_artifact(sub['HOUSEID']),
                'PT': sub['_pt'],
                'FSA': sub['CLIENTPCODE'],
                'EVALTYPE': sub['_ev'],
                'ENTRYDATE': sub['ENTRYDATE'],
                'AuditYear': sub['_year'],
            })
            for c in HOUSE_COLS:
                out[c] = sub[c]
            out['EGHDESHTLOSS'] = sub['EGHDESHTLOSS']
            out['PeakLoad_kW'] = (deshtloss / 1000.0).round(3)
            out['EGHFURNACEAEC'] = sub['EGHFURNACEAEC']
            out['HeatEnergy_kWh'] = (num(sub['EGHFURNACEAEC']) * MJ_TO_KWH).round(1)
            out['EGHFCONTOTAL'] = sub['EGHFCONTOTAL']
            out['TotalEnergy_kWh'] = (num(sub['EGHFCONTOTAL']) * MJ_TO_KWH).round(1)
            for outname, src in [('HeatElectricity_kWh', 'EGHHEATFCONSE'),
                                 ('HeatNaturalGas_kWh', 'EGHHEATFCONSG'),
                                 ('HeatOil_kWh', 'EGHHEATFCONSO'),
                                 ('HeatPropane_kWh', 'EGHHEATFCONSP'),
                                 ('HeatWood_kWh', 'EGHHEATFCONSW')]:
                out[outname] = (num(sub[src]) * MJ_TO_KWH).round(1)
            for c in HP_COLS:
                out[c] = sub['_ahri'] if c == 'AHRI' else sub[c]
            for c in BACKUP_COLS:
                out[c] = sub[c]

            # --- certificate join ---
            recs = [certs.get(a) for a in sub['_ahri']]
            out['Cert_Resolved'] = ['Yes' if r else 'No' for r in recs]
            for name, key in CERT_DETAIL_FIELDS:
                out[name] = [(r or {}).get(key, '') for r in recs]

            cap47 = num(out['Cert_Cap47_btuh']) * BTUH_TO_KW
            cap5 = num(out['Cert_Cap5_btuh']) * BTUH_TO_KW
            load = (deshtloss / 1000.0).where(deshtloss > 0)
            load.index = cap47.index
            out['Cert_Cap47_kW'] = cap47.round(3)
            out['Cert_Cap5_kW'] = cap5.round(3)
            out['SizingRatio_47F'] = (cap47 / load).round(3)
            out['SizingRatio_5F'] = (cap5 / load).round(3)

            for pt_code, grp in out.groupby('PT'):
                writer_for(pt_code).writerows(
                    grp[DETAIL_HEADER].fillna('').values.tolist())

            file_ahri += len(out)
            detail_rows += len(out)

        print(f"  {fname}: {file_ahri:,} AHRI-bearing records")

    for fh, _ in writers.values():
        fh.close()
    print(f"\nDetail rows written: {detail_rows:,} across {len(writers)} provinces")

    # --- per-province year summaries ---------------------------------------
    provinces = sorted(writers.keys())
    for pt_code in provinces:
        rows = []
        for k in sorted(k for k in audits_total if k[0] == pt_code and k[1]):
            _, y, ev = k
            n_ahri = ahri_records.get(k, 0)
            total = audits_total[k]
            rows.append({
                'PT': pt_code,
                'AuditYear': y,
                'EVALTYPE': ev,
                'AHRI_Records': n_ahri,
                'Distinct_AHRI_Numbers': len(ahri_distinct.get(k, ())),
                'Total_Audits': total,
                'Pct_With_AHRI': round(100.0 * n_ahri / total, 2) if total else '',
            })
        pd.DataFrame(rows).to_csv(
            OUTPUT_DIR / f"ahri_by_year_{pt_code}.csv", index=False)
    print(f"Year summaries written for: {', '.join(provinces)}")

    # --- national directory -------------------------------------------------
    cert_field_order = []
    for rec in certs.values():
        for k in rec:
            if k not in cert_field_order and not k.startswith('_'):
                cert_field_order.append(k)

    rows = []
    for a, pc in number_prov.items():
        rec = certs.get(a)
        row = {'AHRI_Number': a, 'Total_Count': sum(pc.values())}
        for p in provinces:
            row[f'Count_{p}'] = pc.get(p, 0)
        row['Cert_Resolved'] = 'Yes' if rec else 'No'
        for k in cert_field_order:
            row[k] = (rec or {}).get(k, '')
        rows.append(row)
    nat = pd.DataFrame(rows).sort_values('Total_Count', ascending=False)
    nat.to_csv(OUTPUT_DIR / "ahri_canada_directory.csv", index=False)
    resolved = (nat['Cert_Resolved'] == 'Yes')
    weighted = nat.loc[resolved, 'Total_Count'].sum() / nat['Total_Count'].sum()
    print(f"National directory: {len(nat):,} distinct AHRI numbers, "
          f"{resolved.sum():,} resolved ({weighted:.3%} occurrence-weighted)")

    # --- column availability ------------------------------------------------
    years = sorted(y for y in fill_rows if y)
    rows = []
    for c in DETAIL_SOURCE_COLS:
        row = {'Column': c}
        for y in years:
            n = fill_rows[y]
            row[y] = round(100.0 * fill[y][c] / n, 1) if n else ''
        rows.append(row)
    pd.DataFrame(rows).to_csv(
        OUTPUT_DIR / "ahri_column_availability.csv", index=False)
    with open(OUTPUT_DIR / "ahri_column_availability.csv", 'a',
              encoding='utf-8') as f:
        f.write('\n')
        f.write('# Percent of AHRI-bearing rows in that audit year where the '
                'column is populated\n')
        f.write('# (non-blank and not a bare 0). Every year of the source '
                'corpus carries the\n')
        f.write('# identical 433-column header, so a low figure means the '
                'field was not being\n')
        f.write('# collected that year, not that the column is absent.\n')
        f.write('# AHRI-bearing rows per audit year:\n')
        for y in years:
            f.write(f'#   {y}: {fill_rows[y]:,}\n')
    print(f"Column availability written for audit years {years[0]}-{years[-1]}")


if __name__ == '__main__':
    main()
