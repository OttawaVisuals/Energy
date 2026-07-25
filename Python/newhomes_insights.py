"""
Build the national "insights" payload behind the province scorecard + FSA map
at the top of newhomes.html.

Inputs (all already in the repo -- no parquet rerun needed):
  newhomes_json/<PROV>.json      province payloads written by newhomes_precompute.py
  newhomes_fsa/<PROV>/*.json     per-FSA record-level files (columns/rows)
  construction_json/constr_*.json  CMHC starts/completions, for the participation denominator

Outputs:
  newhomes_json/insights.json      province scorecard + national roll-up (small)
  newhomes_json/insights_fsa.json  one aggregate row per FSA, for the choropleth

Participation = EnerGuide as-built new-home evaluations divided by CMHC
ground-oriented completions (single + semi + row) over the same years. Both
sides are restricted to PART_YEARS because the CMHC series in construction_json
starts at 2018-01. Caveats stated on the page: CMHC surveys centres of 10,000+
population, so participation is overstated where rural building is common; and
the numerator is every dwelling type in the EnerGuide file, which is 94.3%
ground-oriented (apartments are 0.4%), so the type mismatch is immaterial.
"""
import json
import os
import glob
import statistics

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROV_JSON = os.path.join(REPO, 'newhomes_json')
FSA_JSON = os.path.join(REPO, 'newhomes_fsa')
CONSTR_JSON = os.path.join(REPO, 'construction_json')

NO_HP = 'N/A {no Heat Pump}'
MIN_N = 30                      # FSA floor for the map/leaderboards
PART_YEARS = (2018, 2025)       # inclusive; CMHC series starts 2018-01

PROV_NAME = {
    'ON': 'Ontario', 'QC': 'Quebec', 'BC': 'British Columbia', 'AB': 'Alberta',
    'NS': 'Nova Scotia', 'NB': 'New Brunswick', 'SK': 'Saskatchewan',
    'MB': 'Manitoba', 'NF': 'Newfoundland & Labrador',
    'PE': 'Prince Edward Island', 'NT': 'Northwest Territories',
    'NU': 'Nunavut', 'YK': 'Yukon',
}
# newhomes province code -> construction_json file suffix. Territories are not
# in the CMHC provincial series, so they get no participation figure.
CONSTR_CODE = {
    'ON': 'on', 'QC': 'qc', 'BC': 'bc', 'AB': 'ab', 'NS': 'ns', 'NB': 'nb',
    'SK': 'sk', 'MB': 'mb', 'NF': 'nl', 'PE': 'pe',
}
GROUND_ORIENTED = ('completions.single', 'completions.semi', 'completions.row')


def median(vals):
    vals = [v for v in vals if v is not None]
    return round(statistics.median(vals), 2) if vals else None


def completions(prov, lo, hi):
    """CMHC ground-oriented completions for a province, summed over [lo, hi]."""
    code = CONSTR_CODE.get(prov)
    if not code:
        return None
    path = os.path.join(CONSTR_JSON, f'constr_{code}.json')
    if not os.path.exists(path):
        return None
    series = json.load(open(path, encoding='utf-8'))['series']
    total = 0
    found = False
    for suffix in GROUND_ORIENTED:
        s = series.get(f'starts_unadj.{suffix}')
        if not s:
            continue
        found = True
        start_y, start_m = (int(x) for x in s['start'].split('-'))
        for i, v in enumerate(s['values']):
            if v is None:
                continue
            y = start_y + (start_m - 1 + i) // 12
            if lo <= y <= hi:
                total += v
    return total if found else None


def fsa_rows(prov):
    """Aggregate every FSA file for a province into one row each."""
    out = []
    for path in sorted(glob.glob(os.path.join(FSA_JSON, prov, '*.json'))):
        name = os.path.basename(path)[:-5]
        if name.startswith('_'):
            continue
        d = json.load(open(path, encoding='utf-8'))
        cols = {c: i for i, c in enumerate(d['columns'])}
        rows = d['rows']
        if not rows:
            continue

        def col(c):
            i = cols.get(c)
            return [r[i] for r in rows] if i is not None else []

        hp = col('HPType')
        hp_n = sum(1 for v in hp if v is not None and str(v).strip() not in ('', NO_HP))
        # Ground/water-loop share of the heat pumps present. A handful of FSAs
        # are geothermal subdivisions (L6H in Milton is 95% ground-source), so
        # a bare adoption figure there looks like an error without this split.
        gs_n = sum(1 for v in hp if str(v).strip() in ('Ground', 'Water'))
        fuel = col('HeatFuel')
        elec_n = sum(1 for v in fuel if v == 'Electricity')
        out.append({
            'fsa': name,
            'prov': prov,
            'n': len(rows),
            'hp': round(100 * hp_n / len(rows), 1),
            'gs': round(100 * gs_n / hp_n, 1) if hp_n else None,
            'elec': round(100 * elec_n / len(rows), 1) if fuel else None,
            'eui': median(col('EUI')),
            'ach': median(col('AirLeakage')),
            'ers': median(col('ERSRating')),
        })
    return out


def main():
    provinces = []
    fsas = []
    for path in sorted(glob.glob(os.path.join(PROV_JSON, '*.json'))):
        prov = os.path.basename(path)[:-5]
        if prov in ('CA', 'insights', 'insights_fsa'):
            continue
        a = json.load(open(path, encoding='utf-8'))['by_type']['All types']
        n = a['row_count']

        # Evaluations in the participation window, from the by-year fuel splits
        # (the only per-year count carried in the province payload).
        evals_win = sum(
            sum(v.values())
            for y, v in a.get('fuel_by_year', {}).items()
            if PART_YEARS[0] <= int(y) <= PART_YEARS[1]
        )
        comp = completions(prov, *PART_YEARS)

        fuel = a.get('fuel_counts', {})
        provinces.append({
            'prov': prov,
            'name': PROV_NAME.get(prov, prov),
            'n': n,
            'hp': round(100 * a.get('heat_pump_count', 0) / n, 1) if n else None,
            'solar': a.get('pct_solar'),
            'eui': round(a['median_eui'], 1) if a.get('median_eui') else None,
            'ach': a.get('median_ach'),
            'ers': a.get('median_ers'),
            'ghg': a.get('median_ghg'),
            'area': a.get('median_area'),
            'elec': round(100 * fuel.get('Electricity', 0) / n, 1) if n else None,
            'gas': round(100 * fuel.get('Natural Gas', 0) / n, 1) if n else None,
            'evals_win': evals_win,
            'completions': comp,
            'part': round(100 * evals_win / comp, 1) if comp else None,
            'paths': a.get('compliance_counts', {}),
            'tiered': sum(a.get('tier_counts', {}).values()),
        })
        fsas.extend(fsa_rows(prov))

    provinces.sort(key=lambda r: -r['n'])
    ranked = [r for r in fsas if r['n'] >= MIN_N]

    ca = json.load(open(os.path.join(PROV_JSON, 'CA.json'), encoding='utf-8'))
    ca_all = ca['by_type']['All types']
    tot_ev = sum(p['evals_win'] for p in provinces)
    tot_cp = sum(p['completions'] or 0 for p in provinces)

    payload = {
        'min_n': MIN_N,
        'part_years': list(PART_YEARS),
        'national': {
            'n': ca['total_rows'],
            'hp': round(100 * ca_all['heat_pump_count'] / ca['total_rows'], 1),
            'eui': round(ca_all['median_eui'], 1),
            'ach': ca_all['median_ach'],
            'part': round(100 * tot_ev / tot_cp, 1) if tot_cp else None,
            'evals_win': tot_ev,
            'completions': tot_cp,
        },
        'provinces': provinces,
    }
    with open(os.path.join(PROV_JSON, 'insights.json'), 'w', encoding='utf-8') as f:
        json.dump(payload, f, separators=(',', ':'))
    with open(os.path.join(PROV_JSON, 'insights_fsa.json'), 'w', encoding='utf-8') as f:
        json.dump({'min_n': MIN_N, 'rows': fsas}, f, separators=(',', ':'))

    for p in provinces:
        print(f"  {p['prov']:3} {p['n']:8,}  hp {str(p['hp']):>5}%  "
              f"part {str(p['part']):>6}%  eui {p['eui']}  ach {p['ach']}")
    print(f"\n  national participation: {payload['national']['part']}% "
          f"({tot_ev:,} evals / {tot_cp:,} completions, {PART_YEARS[0]}-{PART_YEARS[1]})")
    print(f"  FSAs: {len(fsas):,} total, {len(ranked):,} at n>={MIN_N}")
    for name in ('insights.json', 'insights_fsa.json'):
        kb = os.path.getsize(os.path.join(PROV_JSON, name)) / 1024
        print(f"  {name}: {kb:,.0f} KB")


if __name__ == '__main__':
    main()
