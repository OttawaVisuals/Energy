"""Build small, identifier-free teaching aggregates for The Cold Call.

Inputs: existing ceud_json/res_ca.json and prices_json/on.json; NRCan ERS
2025.csv export (read-only). ECCC v4.0 (September 2026) residential factor
tables 1.3/2.3/3.3/4.3/5.3 and AR5 GWP100 values were checked 2026-11-04.
Outputs: coldcall_json/teaching.json and a copy beside the original game.
No household identifiers, addresses or per-home records leave this pipeline.
Run: python Python/build_coldcall_teaching.py
"""
import argparse
import hashlib
import json
import math
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
ECCC = ('https://www.canada.ca/en/environment-climate-change/services/climate-change/'
        'pricing-pollution-how-it-will-work/output-based-pricing-system/'
        'federal-greenhouse-gas-offset-system/emission-factors-reference-values.html')
GROUPS = {
    'heat_pump': ['heat_pump'], 'electric': ['electric'],
    'natural_gas': ['natural_gas_high_efficiency', 'natural_gas_medium_efficiency',
                    'natural_gas_normal_efficiency', 'natural_gas_electric'],
    'heating_oil': ['heating_oil_high_efficiency', 'heating_oil_medium_efficiency',
                    'heating_oil_normal_efficiency', 'heating_oil_electric'],
    'wood': ['wood', 'wood_electric', 'wood_heating_oil'], 'other': ['other'],
}


def fingerprint(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return {'file': path.name, 'sha256': h.hexdigest()}


def stock(path):
    d = json.loads(path.read_text(encoding='utf-8'))
    rows = [r for r in d['explanatory'] if r['variable'] == 'heating_system_stock_by_system_type']
    known = {s for values in GROUPS.values() for s in values}
    assert {r['segment'] for r in rows} == known, 'Review new or missing CEUD categories'
    years = []
    for year in sorted({r['year'] for r in rows}):
        values = {r['segment']: r['value'] for r in rows if r['year'] == year}
        assert set(values) == known and all(v is not None and v >= 0 for v in values.values())
        assert all(r['unit'] == 'thousands' for r in rows if r['year'] == year)
        counts = {k: round(sum(values[s] for s in segments) * 1000, 6) for k, segments in GROUPS.items()}
        total = sum(counts.values())
        published = next(r['value'] * 1000 for r in d['explanatory']
                         if r['year'] == year and r['variable'] == 'heating_system_stock' and r['segment'] == 'all')
        assert abs(total - published) / published < .01, 'CEUD totals require review'
        years.append({'year': year, 'counts': counts, 'sum_categories': total,
                      'separately_rounded_total': published,
                      'hp_share_pct': 100 * counts['heat_pump'] / total})
    return {'years': years, 'source': 'NRCan CEUD, Canada residential Table 27; primary heating equipment stock',
            'source_url': 'https://oee.nrcan.gc.ca/corporate/statistics/neud/dpa/showTable.cfm?type=CP&sector=res&juris=ca&year=2023&rn=27&page=0',
            'method': 'Sum 14 detailed categories into the same six groups as CEUD Explorer. Shares use the sum of rounded categories, not the separately rounded total. Counts are equipment stock, not energy shares or new sales.'}


def airtightness(path):
    cols = ['HOUSEID', 'EVALTYPE', 'PROVINCE', 'TYPEOFHOUSE', 'BUILDINGTYPE', 'AIR50P', 'LEAKAR', 'ENTRYDATE']
    stages = dict.fromkeys(['input_rows', 'initial_D', 'ontario', 'single_detached', 'house', 'entry_2025', 'with_house_id'], 0)
    kept = []
    for frame in pd.read_csv(path, usecols=cols, chunksize=50000, low_memory=False, dtype={'HOUSEID': 'string'}):
        stages['input_rows'] += len(frame)
        for key, mask in [
            ('initial_D', lambda x: x.EVALTYPE.eq('D')),
            ('ontario', lambda x: x.PROVINCE.eq('ON')),
            ('single_detached', lambda x: x.TYPEOFHOUSE.eq('Single Detached')),
            ('house', lambda x: x.BUILDINGTYPE.eq('House')),
            ('entry_2025', lambda x: pd.to_datetime(x.ENTRYDATE, errors='coerce').dt.year.eq(2025)),
            ('with_house_id', lambda x: x.HOUSEID.notna()),
        ]:
            frame = frame.loc[mask(frame)].copy()
            stages[key] += len(frame)
        kept.append(frame)
    d = pd.concat(kept).sort_values('ENTRYDATE', kind='stable').drop_duplicates('HOUSEID', keep='first')
    stages['unique_homes'] = len(d)
    stages['repeat_initial_audits_removed'] = stages['with_house_id'] - len(d)
    air = pd.to_numeric(d.AIR50P, errors='coerce')
    ela = pd.to_numeric(d.LEAKAR, errors='coerce')
    valid = air.gt(0) & air.map(math.isfinite) & ela.gt(0) & ela.map(math.isfinite)
    stages['invalid_or_nonpositive_metric_removed'] = int((~valid).sum())
    d = d.loc[valid]; air = air.loc[valid]; ela = ela.loc[valid]
    stages['valid_homes'] = len(d)
    assert len(d) >= 30, 'Do not publish small cells'
    area = float(ela.median())
    return {'scope': 'Ontario single-detached houses, initial EnerGuide audits with entry dates in 2025, as available in the 2025.csv export',
            'n': len(d), 'ach50': {'q25': float(air.quantile(.25)), 'median': float(air.median()), 'q75': float(air.quantile(.75))},
            'median_ela10_cm2': area, 'equivalent_circle_diameter_cm': math.sqrt(4 * area / math.pi),
            'entry_date_min': str(d.ENTRYDATE.min()), 'entry_date_max': str(d.ENTRYDATE.max()), 'selection': stages,
            'source_url': 'https://open.canada.ca/data/en/dataset/0a7619fd-2ffe-44b5-9027-3dfcec0866fd',
            'standard_url': 'https://publications.gc.ca/collections/collection_2019/ongc-cgsb/P29-149-010-2019-eng.pdf',
            'method': 'Earliest eligible initial audit per HOUSEID; positive finite AIR50P and LEAKAR on the same cohort. LEAKAR is equivalent leakage area in cm² at 10 Pa. Circle diameter = sqrt(4 × median area / pi). Not inferred from ACH50; the median area and median ACH need not belong to the same house. This audit sample is not representative of all Canadian homes.'}


def comparison(path):
    p = json.loads(path.read_text(encoding='utf-8'))
    e = p['electricity']['ottawa']; gas = p['natural_gas']['ottawa']; oil = p['heating_oil']['ottawa']
    rates = e['plans']['tou']['prices_cad_per_kwh']
    weights = {'off': .63, 'mid': .18, 'on': .19}
    blended = sum(rates[k] * weights[k] for k in weights) + e['volumetric_adders_cad_per_kwh']
    return {'efficiency_assumptions': {'gas': .95, 'oil': .85, 'propane': .78, 'resistance': 1, 'heat_pump': 2.8},
            'kwh_per_native_unit': {'gas': 10.3611, 'oil': 10.7778, 'propane': 7.0917},
            'prices': {'electricity_cents_per_kwh': round(blended * 100, 6), 'gas_cad_per_m3': gas['marginal_cad_per_m3'],
                       'oil_cad_per_litre': oil['cad_per_litre'], 'propane_cad_per_litre': .75},
            'price_sources': {'electricity': {'effective': e['effective_date'], 'scope': 'Hydro Ottawa TOU snapshot; assumed 63% off / 18% mid / 19% on; variable adders included', 'url': 'https://www.oeb.ca/newsroom/2025/ontario-energy-board-announces-changes-electricity-prices-households-small-businesses', 'rates': rates, 'weights': weights, 'adders_cad_per_kwh': e['volumetric_adders_cad_per_kwh']},
                              'gas': {'effective': gas['effective_date'], 'scope': 'Ontario Union South snapshot; not an Ottawa tariff', 'url': gas['source_url']},
                              'oil': {'effective': oil['ref_month'], 'scope': oil['geo_used'], 'url': 'https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=1810000101'},
                              'propane': {'effective': None, 'scope': 'Game assumption; not an observed price or supplier quote', 'url': None}},
            'price_method': 'Dated reference inputs, not current quotes or a same-date price survey. Excludes fixed fees, tax and the Ontario Electricity Rebate. Cost/kWh delivered = native-unit price / energy conversion / assumed efficiency; electricity price / COP for the heat pump. Editing values changes the lesson only, not puzzle answers.',
            'emissions': {'reference_year': 2026, 'publication': 'ECCC Emission factors and reference values v4.0, September 2026', 'source_url': ECCC,
                          'gwp100': {'CO2': 1, 'CH4': 28, 'N2O': 265},
                          'gwp_source_url': 'https://www.canada.ca/en/environment-climate-change/services/climate-change/greenhouse-gas-emissions/quantification-guidance/global-warming-potentials.html',
                          'combustion_native_g': {'gas': {'CO2': 1921, 'CH4': .037, 'N2O': .035}, 'oil': {'CO2': 2753, 'CH4': .026, 'N2O': .006}, 'propane': {'CO2': 1515, 'CH4': .027, 'N2O': .108}},
                          'electricity_g_per_kwh': {'ON': 59, 'QC': 1.9, 'AB': 438},
                          'method': 'ECCC tables 1.3, 2.3, 3.3, 4.3 and 5.3: CO2 + 28×CH4 + 265×N2O, then divide by native-unit kWh and efficiency. Gas combustion uses the Ontario marketable-gas factor throughout. Provincial selection changes electricity only. Consumption-side electricity reference factors, not hourly marginal emissions or a full lifecycle assessment; excludes upstream fuels, equipment manufacture and refrigerant leakage. Game totals keep their original rounded factors.'}}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--raw-ers', type=Path, default=Path('C:/ERS/2025.csv'))
    ap.add_argument('--out', type=Path, default=ROOT / 'coldcall_json/teaching.json')
    ap.add_argument('--as-of', default='2026-11-04')
    ap.add_argument('--no-source-copy', action='store_true')
    args = ap.parse_args()
    ceud = ROOT / 'ceud_json/res_ca.json'; prices = ROOT / 'prices_json/on.json'
    data = {'schema_version': 1, 'prepared': args.as_of, 'stock': stock(ceud), 'airtightness': airtightness(args.raw_ers),
            'comparison': comparison(prices), 'inputs': [fingerprint(x) for x in [ceud, prices, args.raw_ers]]}
    payload = json.dumps(data, ensure_ascii=False, separators=(',', ':'), allow_nan=False) + '\n'
    args.out.parent.mkdir(parents=True, exist_ok=True); args.out.write_text(payload, encoding='utf-8', newline='\n')
    if not args.no_source_copy:
        copy = Path('C:/EscapeBackpack/Cold-Call/coldcall_json/teaching.json')
        copy.parent.mkdir(parents=True, exist_ok=True); copy.write_text(payload, encoding='utf-8', newline='\n')
    print(f'Wrote {len(payload.encode("utf-8")):,} bytes; CEUD {len(data["stock"]["years"])} years; airtightness n={data["airtightness"]["n"]:,}')
    print('Airtightness selection:', data['airtightness']['selection'])


if __name__ == '__main__':
    main()
