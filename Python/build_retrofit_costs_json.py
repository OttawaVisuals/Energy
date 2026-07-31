"""
build_retrofit_costs_json.py

Splits each retrofits/data/<PROV>_priced.json (retrofit_cost_estimate.py's
output — full per-measure Low/Mid/High cost + payback per home) into a
companion tree mirroring fsa_json's own per-FSA-file layout AND its
size-saving tricks:

    retrofit_costs_json/<PROV>/<FSA>.json    — {columns:[...], rows:[[...]]}
                                                same array-of-arrays shape
                                                split_fsa_json.py uses (see
                                                that script's docstring —
                                                measured ~77% smaller than
                                                array-of-objects)
    retrofit_costs_json/<PROV>/_summary.json — province-level aggregates
    retrofit_costs_json/_canada.json         — national rollup
    retrofit_costs_json/_dictionary.json     — code -> label lookups for
                                                every dictionary-coded column
                                                below (ac, acs, bh, bhs, wc,
                                                wcs), one shared file for the
                                                whole tree — mirrors
                                                ers_web_pipeline.py's own
                                                "global dictionary across all
                                                provinces" convention.

Deliberately a SEPARATE tree from fsa_json, not merged into it — cost
methodology has changed independently of the underlying ERS row data
repeatedly in one session (2026-07-31); keeping them separate means a
cost-only fix stays a few-minute script run instead of an 827MB fsa_json
rebuild every time. See docs/RETROFIT_COSTS.md.

JOIN KEY: `id` (column 0) is HOUSEID normalized to a plain integer string
("281681", not "281681.0") to match what split_fsa_json.py's coerce_value()
produces for fsa_json rows (numeric-looking strings become JS numbers, which
stringify without a trailing ".0") — retrofits.html joins with
String(r.HOUSEID) against this file's ids.

STATIC per-province flags (electricity/gas confidence — identical for every
home in a province) are NOT repeated per home; they live once in
_summary.json. Only the two flags that vary PER HOME (this home's dominant
pre-fuel was oil/propane/wood, priced at the national screening-constant
fallback, not real province data) are kept, packed into one small bitmask
column (pbFuel: 1=oil, 2=propane, 4=wood, OR'd — see _dictionary.json).

Run: python Python/build_retrofit_costs_json.py
"""

import json
import os

import numpy as np

IN_DIR = os.path.join("retrofits", "data")
OUT_DIR = "retrofit_costs_json"

ALL_PROVINCES = ['AB', 'BC', 'MB', 'NB', 'NF', 'NS', 'NT', 'NU',
                  'ON', 'PE', 'QC', 'SK']

MEASURE_ORDER = ['Roof', 'Wall', 'Foundation', 'Window', 'ASHP', 'AirSeal', 'PV', 'HRV']
MEASURE_ABBR = {'Roof': 'Roof', 'Wall': 'Wall', 'Foundation': 'Fnd', 'Window': 'Win',
                'ASHP': 'ASHP', 'AirSeal': 'Seal', 'PV': 'PV', 'HRV': 'HRV'}

COLUMNS = ['id']
for m in MEASURE_ORDER:
    a = MEASURE_ABBR[m]
    COLUMNS += [f'{a}_l', f'{a}_m', f'{a}_h']
COLUMNS += ['Tot_l', 'Tot_m', 'Tot_h', 'ac', 'acs', 'bh', 'bhs', 'bsd', 'wc', 'wcs',
            'sav', 'pbY', 'pbFuel']

ASHP_CLASS_CODES = {'Centrally ducted': 1, 'Non-ducted, single-zone': 2, 'Non-ducted, multi-zone': 3}
SOURCE_CODES = {'reported': 1, 'like_for_like': 1, 'assumed_default': 2}
WINDOW_CLASS_CODES = {'Vinyl': 1, 'Metal': 2}
BAU_HEATING_CODES = {
    'Furnaces / Gas Furnace': 1, 'Furnaces / Oil Furnace': 2, 'Boiler / Oil': 3,
    'Boiler / Gas (Non-Condensing)': 4, 'Boiler / Gas (Condensing)': 5,
    'Boiler / Electric': 6, 'Electric Baseboard': 7,
}
PBFUEL_BITS = {'home_pre_fuel_oil_screening_rate': 1,
               'home_pre_fuel_propane_screening_rate': 2,
               'home_pre_fuel_wood_screening_rate': 4}

DICTIONARY = {
    'ac': {str(v): k for k, v in ASHP_CLASS_CODES.items()},
    'acs': {'1': 'reported', '2': 'assumed_default'},
    'bh': {str(v): k for k, v in BAU_HEATING_CODES.items()},
    'bhs': {'1': 'like_for_like', '2': 'assumed_default'},
    'wc': {str(v): k for k, v in WINDOW_CLASS_CODES.items()},
    'wcs': {'1': 'reported', '2': 'assumed_default'},
    'pbFuel_bits': {'1': 'oil', '2': 'propane', '4': 'wood',
                     'note': "this home's dominant pre-retrofit fuel among those bits was priced "
                             "at a national screening-constant rate (no real per-province data yet) "
                             "— see docs/RETROFIT_COSTS.md 'Utility rates'. Bits OR'd."},
    'columns': {c: c for c in COLUMNS},  # self-documenting column-name list
}


def clean_id(raw_id):
    """'281681.0' -> '281681' — matches split_fsa_json.py's coerce_value()
    numeric-string handling so both trees' HOUSEID join cleanly."""
    s = str(raw_id)
    if s.endswith('.0'):
        s = s[:-2]
    return s


def home_row(h):
    row = [clean_id(h['id'])]
    for m in MEASURE_ORDER:
        v = h.get('measures', {}).get(m)
        row += (v if v else [None, None, None])
    row += (h.get('total') or [None, None, None])
    row.append(ASHP_CLASS_CODES.get(h.get('ashp_class')))
    row.append(SOURCE_CODES.get(h.get('ashp_class_source')))
    bh = h.get('bau_heating')
    row.append(BAU_HEATING_CODES.get(bh))
    row.append(SOURCE_CODES.get(h.get('bau_heating_source')))
    row.append(1 if h.get('bau_self_derived') else 0)
    row.append(WINDOW_CLASS_CODES.get(h.get('window_class')))
    row.append(SOURCE_CODES.get(h.get('window_class_source')))
    row.append(h.get('annual_dollar_saved'))
    row.append(h.get('payback_years'))
    flags = h.get('payback_flags') or []
    bitmask = sum(bit for name, bit in PBFUEL_BITS.items() if name in flags)
    row.append(bitmask or None)
    return row


def pctl(arr, p):
    if not arr:
        return None
    return round(float(np.percentile(np.array(arr, dtype=float), p)), 2)


def summarize(homes):
    out = {'n_priced': len(homes), 'measures': {}}
    for m in MEASURE_ORDER:
        vals = [h['measures'][m] for h in homes if m in h.get('measures', {})]
        if not vals:
            continue
        out['measures'][m] = {
            'n': len(vals),
            'low': {'p10': pctl([v[0] for v in vals], 10), 'median': pctl([v[0] for v in vals], 50),
                    'sum': round(sum(v[0] for v in vals), 2)},
            'mid': {'p10': pctl([v[1] for v in vals], 10), 'median': pctl([v[1] for v in vals], 50),
                    'p90': pctl([v[1] for v in vals], 90), 'sum': round(sum(v[1] for v in vals), 2)},
            'high': {'p90': pctl([v[2] for v in vals], 90), 'median': pctl([v[2] for v in vals], 50),
                     'sum': round(sum(v[2] for v in vals), 2)},
        }
    totals = [h['total'] for h in homes if 'total' in h]
    if totals:
        out['total'] = {
            'low': {'median': pctl([t[0] for t in totals], 50), 'sum': round(sum(t[0] for t in totals), 2)},
            'mid': {'p10': pctl([t[1] for t in totals], 10), 'median': pctl([t[1] for t in totals], 50),
                    'p90': pctl([t[1] for t in totals], 90), 'sum': round(sum(t[1] for t in totals), 2)},
            'high': {'median': pctl([t[2] for t in totals], 50), 'sum': round(sum(t[2] for t in totals), 2)},
        }
    paybacks = [h['payback_years'] for h in homes if h.get('payback_years') is not None
                and 0 < h['payback_years'] < 100]
    if paybacks:
        out['payback_years_median'] = pctl(paybacks, 50)
        out['payback_years_p10'] = pctl(paybacks, 10)
        out['payback_years_n'] = len(paybacks)
    rate_flags = homes[0].get('payback_flags', []) if homes else []
    out['province_rate_flags'] = [f for f in rate_flags if not f.startswith('home_pre_fuel_')]
    return out


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    all_homes_national = []

    for prov in ALL_PROVINCES:
        in_path = os.path.join(IN_DIR, f'{prov}_priced.json')
        if not os.path.exists(in_path):
            print(f"  {prov}: no priced.json, skipping")
            continue
        with open(in_path, encoding='utf-8') as f:
            data = json.load(f)
        homes = data['homes']
        all_homes_national.extend(homes)

        prov_dir = os.path.join(OUT_DIR, prov)
        os.makedirs(prov_dir, exist_ok=True)

        by_fsa = {}
        for h in homes:
            by_fsa.setdefault(h.get('fsa') or '_unknown', []).append(h)

        total_bytes = 0
        for fsa, hs in by_fsa.items():
            rows = [home_row(h) for h in hs]
            payload = {'columns': COLUMNS, 'rows': rows}
            out_path = os.path.join(prov_dir, f'{fsa.replace("/", "_")}.json')
            text = json.dumps(payload, separators=(',', ':'))
            with open(out_path, 'w', encoding='utf-8') as f:
                f.write(text)
            total_bytes += len(text)

        summary = summarize(homes)
        summary['province'] = prov
        summary['generated'] = data.get('generated')
        summary['ashp_class_fallback'] = data.get('ashp_class_fallback')
        with open(os.path.join(prov_dir, '_summary.json'), 'w', encoding='utf-8') as f:
            json.dump(summary, f, separators=(',', ':'))

        print(f"  {prov}: {len(homes)} homes / {len(by_fsa)} FSAs, {total_bytes/1024/1024:.1f} MB")

    national = summarize(all_homes_national)
    national['provinces_included'] = [p for p in ALL_PROVINCES
                                       if os.path.exists(os.path.join(IN_DIR, f'{p}_priced.json'))]
    with open(os.path.join(OUT_DIR, '_canada.json'), 'w', encoding='utf-8') as f:
        json.dump(national, f, separators=(',', ':'))

    with open(os.path.join(OUT_DIR, '_dictionary.json'), 'w', encoding='utf-8') as f:
        json.dump(DICTIONARY, f, indent=1)

    print(f"wrote {OUT_DIR}/_canada.json — {national['n_priced']} homes nationally")
    print(f"wrote {OUT_DIR}/_dictionary.json")


if __name__ == '__main__':
    main()
