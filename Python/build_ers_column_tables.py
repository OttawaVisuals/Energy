"""
Join full-scan ERS column stats + NRCan data dictionary + the Retrofit
Explorer's BASE_MAPPING into one JSON blob for the "data availability" mockup
page (docs transparency material -- not part of the production pipeline).

Inputs:
  Python/ers_full_column_stats.csv   -- per-column % filled / unique count,
                                         all 433 raw ERS columns, full scan
                                         of C:\\ERS\\*.csv (ers_full_column_stats.py)
  Python/nrcan_data_dictionary.csv   -- NRCan's own column descriptions,
                                         extracted from the open-data-dictionary xlsx
  Python/ers_web_pipeline.py         -- BASE_MAPPING (source col -> friendly
                                         name -> conversion) is imported directly,
                                         so this stays in sync with the real pipeline

Output: Python/ers_column_tables.json  {all_columns: [...], used_columns: [...]}
"""

import csv
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import ers_web_pipeline as pipeline  # noqa: E402

STATS_CSV = Path(__file__).parent / "ers_full_column_stats.csv"
DICT_CSV = Path(__file__).parent / "nrcan_data_dictionary.csv"
OUT_JSON = Path(__file__).parent / "ers_column_tables.json"

# What each source column feeds on the Retrofit Explorer page -- hand-mapped
# against ers_web_pipeline.py's flag/derived-column logic (lines ~582-629) and
# docs/RETROFITS.md, since that logic isn't itself a lookup table.
USED_FOR = {
    'HOUSEID':        'Pairing key: matches one home\'s before (D) and after (E) audits',
    'CLIENTPCODE':     'FSA (postal first 3 chars) -- area selector, map',
    'PROVINCE':        'Province selector',
    'YEARBUILT':       'Year-built distribution',
    'FLOORAREA':       'Floor-area distribution; same-home match gate (\u226410% change pre/post)',
    'TYPEOFHOUSE':     'Building-type filter/breakdown; same-home match gate (must match pre/post)',
    'STOREYS':         'Storeys distribution; same-home match gate (must match pre/post)',
    'FNDTYPE':         'Foundation type (displayed)',
    'NUMDWELLINGUNITS':'Same-home match gate (must match pre/post) -- not shown in table',
    'EVALTYPE':        'Splits each row into "before" (D) vs "after" (E) audit',
    'ENTRYDATE':       'Audit date; pairing order gate (E must postdate D); audit-year extraction',
    'EGHFCONTOTAL':    '% energy saved; retrofit depth (shallow/medium/deep) thresholds',
    'EGHFURNACEAEC':   '% heating energy saved',
    'EGHFCONELEC':     'Energy-by-fuel chart, fuel Sankey',
    'EGHFCONNGAS':     'Energy-by-fuel chart, fuel Sankey',
    'EGHFCONOIL':      'Energy-by-fuel chart, fuel Sankey',
    'EGHFCONPROP':     'Energy-by-fuel chart, fuel Sankey',
    'EGHFCONWOOD':     'Energy-by-fuel chart, fuel Sankey (tonnes fallback path)',
    'EGHFCONWOODGJ':   'Preferred wood-energy source when populated (HOT2000 v11.2+)',
    'EGHHEATFCONSE':   'Heating-only per-fuel breakdown',
    'EGHHEATFCONSG':   'Heating-only per-fuel breakdown',
    'EGHHEATFCONSO':   'Heating-only per-fuel breakdown',
    'EGHHEATFCONSP':   'Heating-only per-fuel breakdown',
    'EGHHEATFCONSW':   'Heating-only per-fuel breakdown',
    'EGHHLAIR':        '"Where the heat escapes" component chart (infiltration)',
    'EGHHLCEILING':    '"Where the heat escapes" component chart (roof)',
    'EGHHLWALLS':      '"Where the heat escapes" component chart (wall)',
    'EGHHLFOUND':      '"Where the heat escapes" component chart (foundation)',
    'EGHHLEXPOSEDFLR': '"Where the heat escapes" component chart (exposed floor)',
    'EGHHLWINDOOR':    '"Where the heat escapes" component chart (window/door)',
    'CENVENTSYSTYPE':  'Ventilation type (HRV/none/exhaust-only), displayed',
    'AIR50P':          'Air_Tightness_Upgrade flag (post <0.90\u00d7 pre); air-tightness chart',
    'CEILINS':         'Roof_Insulation_Upgrade flag (post >1.10\u00d7 pre); roof insulation chart',
    'MAINWALLINS':     'Wall_Insulation_Upgrade flag (post >1.10\u00d7 pre); wall insulation chart',
    'FNDWALLINS':      'Foundation_Insulation_Upgrade flag (post >1.10\u00d7 pre); foundation chart',
    'EGHINEXPOSEDFLR': 'Floor_Insulation_Upgrade flag (post >1.10\u00d7 pre); floor insulation chart',
    'WINDOWCODE':      'Windows_Change flag (code present + different pre/post)',
    'FURNACEFUEL':     'Heating_Change / FuelSwitch flags; fuel breakdown, Sankey',
    'FURNACETYPE':     'Heating_Change flag; equipment-type display',
    'HEATAFUE':        'Equipment efficiency, displayed',
    'EGHFURSEASEFF':   'Heat pump seasonal COP, displayed',
    'HPSOURCE':        'HeatPump_Addition flag (no HP pre, HP present post)',
    'COP':             'Heat pump COP, displayed',
    'AHRI':            'Join key to AHRI certificate lookup (capacity/HSPF2/brand/model)',
    'AIRCONDTYPE':     'Cooling_Change flag -- not itself shown in table',
    'EGHDESHTLOSS':    'Design (peak) heat-loss chart; heat-pump sizing-ratio calc',
    'ERSGHG':          'GHG emissions chart',
    'KWPV':            'Solar PV added, KPI + chart',
}

FRIENDLY_BY_SRC = {}
CONV_BY_SRC = {}
for out_name, src, dset, conv in pipeline.BASE_MAPPING:
    prefix = 'Pre_/Post_' if out_name.startswith(('Pre_', 'Post_')) else ''
    friendly = out_name
    if out_name.startswith('Pre_'):
        friendly = 'Pre_/Post_' + out_name[4:]
    elif out_name.startswith('Post_'):
        continue  # already captured by the Pre_ entry, same source col
    FRIENDLY_BY_SRC.setdefault(src, friendly)
    if conv is not None:
        CONV_BY_SRC[src] = conv

# Columns only referenced via FILTER_COLS / flag logic (no BASE_MAPPING entry)
EXTRA_USED_SRC = ['NUMDWELLINGUNITS', 'EVALTYPE', 'AIRCONDTYPE']
for c in EXTRA_USED_SRC:
    FRIENDLY_BY_SRC.setdefault(c, '(filter/flag only, not a displayed column)')

CONV_LABELS = {
    0.27778: '\u00d7 0.27778 (MJ \u2192 kWh)',
    10.3611: '\u00d7 10.3611 (m\u00b3 \u2192 kWh)',
    10.7778: '\u00d7 10.7778 (L \u2192 kWh)',
    7.0917:  '\u00d7 7.0917 (L \u2192 kWh)',
    3888.89: '\u00d7 3888.89 (tonne \u2192 kWh, fallback)',
    0.001:   '\u00d7 0.001 (W \u2192 kW)',
}


def main():
    desc = {}
    with open(DICT_CSV, encoding='utf-8') as f:
        for row in csv.DictReader(f):
            desc[row['column_name'].strip()] = (row.get('description_en') or '').strip()

    all_cols = []
    with open(STATS_CSV, encoding='utf-8') as f:
        for row in csv.DictReader(f):
            col = row['column_name']
            all_cols.append({
                'column': col,
                'description': desc.get(col, ''),
                'pct': float(row['pct_populated']),
                'unique': row['unique_count'],
                'used': col in FRIENDLY_BY_SRC,
            })

    stats_by_col = {r['column']: r for r in all_cols}

    # Pipeline-order groups (mirrors the section comments in BASE_MAPPING),
    # rather than alphabetical -- reads as a story when embedded as a static
    # table in retrofits.html, matching how sections B/C/D there are grouped.
    GROUPS = [
        ('Identity & pairing', ['HOUSEID', 'CLIENTPCODE', 'PROVINCE', 'YEARBUILT',
                                 'FLOORAREA', 'TYPEOFHOUSE', 'STOREYS', 'FNDTYPE',
                                 'NUMDWELLINGUNITS', 'EVALTYPE', 'ENTRYDATE']),
        ('Energy totals, per fuel (whole-house)', ['EGHFCONTOTAL', 'EGHFURNACEAEC',
                                 'EGHFCONELEC', 'EGHFCONNGAS', 'EGHFCONOIL',
                                 'EGHFCONPROP', 'EGHFCONWOOD', 'EGHFCONWOODGJ']),
        ('Heating-only energy, per fuel', ['EGHHEATFCONSE', 'EGHHEATFCONSG',
                                 'EGHHEATFCONSO', 'EGHHEATFCONSP', 'EGHHEATFCONSW']),
        ('Annual heat loss by component', ['EGHHLAIR', 'EGHHLCEILING', 'EGHHLWALLS',
                                 'EGHHLFOUND', 'EGHHLEXPOSEDFLR', 'EGHHLWINDOOR']),
        ('Ventilation', ['CENVENTSYSTYPE']),
        ('Envelope', ['AIR50P', 'CEILINS', 'MAINWALLINS', 'FNDWALLINS',
                                 'EGHINEXPOSEDFLR', 'WINDOWCODE']),
        ('HVAC', ['FURNACEFUEL', 'FURNACETYPE', 'HEATAFUE', 'EGHFURSEASEFF',
                                 'HPSOURCE', 'COP', 'AHRI', 'AIRCONDTYPE']),
        ('Design heat loss, GHG & solar', ['EGHDESHTLOSS', 'ERSGHG', 'KWPV']),
    ]

    used_cols = []
    for group_name, srcs in GROUPS:
        for src in srcs:
            friendly = FRIENDLY_BY_SRC.get(src, '')
            stat = stats_by_col.get(src, {'pct': None, 'description': desc.get(src, '')})
            conv = CONV_BY_SRC.get(src)
            used_cols.append({
                'group': group_name,
                'source': src,
                'friendly': friendly,
                'description': desc.get(src, ''),
                'pct': stat.get('pct'),
                'conversion': CONV_LABELS.get(conv, '') if conv else '',
                'used_for': USED_FOR.get(src, ''),
            })

    out = {'all_columns': all_cols, 'used_columns': used_cols}
    OUT_JSON.write_text(json.dumps(out, indent=1), encoding='utf-8')
    print(f"all_columns: {len(all_cols)}, used_columns: {len(used_cols)}")
    print(f"Wrote {OUT_JSON}")


if __name__ == '__main__':
    main()
