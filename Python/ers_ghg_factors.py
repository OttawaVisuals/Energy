"""
Implied GHG emissions factors per fuel type, derived from the ERS CSVs' own
paired columns (fuel consumption vs. that fuel's own reported GHG emissions).
Feeds Python/ghg_factors.py (the ERS-calibrated electricity factor used by
the "as audited" GHG scenario and the Alberta/Newfoundland correction — see
docs/RETROFITS.md and docs/ENERGUIDE_QUESTIONS.md §5.4).

For each fuel, the ERS data already carries both:
  - a whole-house annual consumption in the fuel's native unit (EGHFCON*)
  - that fuel's own annual GHG emissions in tonnes (ERS*GHG)

So the implied factor = GHG / consumption needs no single-fuel-home
filtering (unlike deriving the MJ/native-unit conversion factors in
ers_web_pipeline.py, which does need that). Aggregated as sum(GHG) /
sum(consumption) per fuel per province per year (ratio-of-sums, robust to
small denominators) rather than a mean of per-row ratios.

BUG FIXED 2026-08-02: the row mask used to require ghg > 0, which silently
excluded every row where a fuel was consumed but its true reported GHG was
0 (e.g. a hydro-heavy year/province can legitimately show ~0 electricity
GHG). Excluding true zeros from the numerator/denominator biases the factor
upward, then applying that inflated factor to every home (including the
true-zero ones) compounds into a national aggregate overestimate — measured
at +12.8% before this fix, +0.16% after. The mask now requires only that
GHG was actually *reported* (not null), so true zeros count.

Native units -> kWh via the same factors ers_web_pipeline.py uses, so all
fuels are comparable in kg CO2e/kWh:
  electricity 1:1, nat gas 10.3611 kWh/m3, oil 10.7778 kWh/L,
  propane 7.0917 kWh/L, wood 3888.89 kWh/tonne.

Output: printed tables (diagnostic), plus ers_ghg_factors_by_province_year.csv
(fuel, province, year, n, factor_native, factor_kwh — the combined table
Python/ghg_factors.py loads) and the two legacy per-fuel-year /
electricity-by-province-year CSVs for backward compatibility.
"""

import glob
import os
import pyarrow.csv as pacsv
import pyarrow.compute as pc
import pyarrow as pa
import pandas as pd

INPUT_DIR = r"C:\ERS"

FUELS = {
    'Electricity': ('EGHFCONELEC', 'ERSELECGHG', 1.0),
    'NaturalGas':  ('EGHFCONNGAS', 'ERSNGASGHG', 10.3611),
    'Oil':         ('EGHFCONOIL',  'ERSOILGHG',  10.7778),
    'Propane':     ('EGHFCONPROP', 'ERSPROPGHG', 7.0917),
    'Wood':        ('EGHFCONWOOD', 'ERSWOODGHG', 3888.89),
}

NEEDED_COLS = {'ENTRYDATE', 'EVALTYPE', 'PROVINCE'}
for cons_col, ghg_col, _ in FUELS.values():
    NEEDED_COLS.add(cons_col)
    NEEDED_COLS.add(ghg_col)

CSV_FILES = sorted(glob.glob(os.path.join(INPUT_DIR, '20*.csv')))


def process_file(csv_path):
    """Returns a long DataFrame: year, fuel, consumption_native, ghg_tonnes."""
    with open(csv_path, 'r', encoding='utf-8', errors='replace') as f:
        header = [h.strip().strip('"') for h in f.readline().strip().split(',')]
    present = [c for c in header if c in NEEDED_COLS]
    if 'ENTRYDATE' not in present or 'EVALTYPE' not in present:
        print(f"  !! {csv_path}: missing ENTRYDATE/EVALTYPE, skipping")
        return None

    read_opts = pacsv.ReadOptions(block_size=1 << 23)
    parse_opts = pacsv.ParseOptions(delimiter=',')
    convert_opts = pacsv.ConvertOptions(
        include_columns=present,
        strings_can_be_null=True,
        column_types={c: pa.string() for c in present},
    )

    rows = []
    reader = pacsv.open_csv(csv_path, read_opts, parse_opts, convert_opts)
    for batch in reader:
        tbl = pa.Table.from_batches([batch])
        # Only D (as-found/pre) rows, to avoid double-counting the same
        # household twice per pair the way pre/post retrofit pairing does —
        # here we just want a population snapshot per year, so keep both D
        # and E rows in (each is an independent audited house-state).
        df = tbl.to_pandas()
        df['year'] = df['ENTRYDATE'].astype(str).str.slice(0, 4)
        province = df['PROVINCE'] if 'PROVINCE' in df.columns else ''
        for fuel, (cons_col, ghg_col, _) in FUELS.items():
            if cons_col not in df.columns or ghg_col not in df.columns:
                continue
            cons = pd.to_numeric(df[cons_col], errors='coerce')
            ghg = pd.to_numeric(df[ghg_col], errors='coerce')
            # cons>0: need a meaningful denominator. ghg.notna() (not ghg>0):
            # a true-zero reported GHG is real data, not a missing value --
            # see the BUG FIXED note in the module docstring.
            mask = (cons > 0) & (ghg.notna())
            if mask.any():
                rows.append(pd.DataFrame({
                    'year': df.loc[mask, 'year'],
                    'province': province[mask] if 'PROVINCE' in df.columns else '',
                    'fuel': fuel,
                    'consumption_native': cons[mask],
                    'ghg_tonnes': ghg[mask],
                }))
    if not rows:
        return None
    return pd.concat(rows, ignore_index=True)


def main():
    print(f"Found {len(CSV_FILES)} CSVs in {INPUT_DIR}")
    all_frames = []
    for csv_path in CSV_FILES:
        tag = os.path.basename(csv_path)
        frame = process_file(csv_path)
        if frame is not None:
            print(f"  {tag}: {len(frame):,} fuel-rows")
            all_frames.append(frame)

    if not all_frames:
        print("No data collected.")
        return

    data = pd.concat(all_frames, ignore_index=True)

    kwh_factor = {fuel: FUELS[fuel][2] for fuel in FUELS}
    data['consumption_kwh'] = data.apply(
        lambda r: r['consumption_native'] * kwh_factor[r['fuel']], axis=1)

    print("\n=== Implied GHG factor per fuel per year (ratio of sums) ===")
    print(f"{'Fuel':<12}{'Year':<6}{'n':>10}{'tonnes CO2e/native-unit':>26}{'kg CO2e/kWh':>14}")
    by_year = data.groupby(['fuel', 'year']).apply(
        lambda g: pd.Series({
            'n': len(g),
            'factor_native': g['ghg_tonnes'].sum() / g['consumption_native'].sum(),
            'factor_kwh': g['ghg_tonnes'].sum() * 1000 / g['consumption_kwh'].sum(),
        }), include_groups=False
    ).reset_index()
    for fuel in FUELS:
        sub = by_year[by_year['fuel'] == fuel].sort_values('year')
        for _, r in sub.iterrows():
            print(f"{fuel:<12}{r['year']:<6}{int(r['n']):>10}{r['factor_native']:>26.5f}{r['factor_kwh']:>14.4f}")
        print()

    print("=== Pooled (all years) ===")
    print(f"{'Fuel':<12}{'n':>10}{'tonnes CO2e/native-unit':>26}{'kg CO2e/kWh':>14}")
    pooled = data.groupby('fuel').apply(
        lambda g: pd.Series({
            'n': len(g),
            'factor_native': g['ghg_tonnes'].sum() / g['consumption_native'].sum(),
            'factor_kwh': g['ghg_tonnes'].sum() * 1000 / g['consumption_kwh'].sum(),
        }), include_groups=False
    ).reset_index()
    for _, r in pooled.iterrows():
        print(f"{r['fuel']:<12}{int(r['n']):>10}{r['factor_native']:>26.5f}{r['factor_kwh']:>14.4f}")

    out_path = os.path.join(os.path.dirname(__file__), 'ers_ghg_factors_by_year.csv')
    by_year.to_csv(out_path, index=False)
    print(f"\nWrote {out_path}")

    print("\n=== Electricity GHG factor by province by year (ratio of sums) ===")
    elec = data[data['fuel'] == 'Electricity']
    by_prov_year = elec.groupby(['province', 'year']).apply(
        lambda g: pd.Series({
            'n': len(g),
            'factor_kwh': g['ghg_tonnes'].sum() * 1000 / g['consumption_kwh'].sum(),
        }), include_groups=False
    ).reset_index()
    by_prov_year = by_prov_year[by_prov_year['n'] >= 20]  # suppress small-n cells
    print(f"{'Province':<10}{'Year':<6}{'n':>10}{'kg CO2e/kWh':>14}")
    for prov in sorted(by_prov_year['province'].unique()):
        sub = by_prov_year[by_prov_year['province'] == prov].sort_values('year')
        for _, r in sub.iterrows():
            print(f"{prov:<10}{r['year']:<6}{int(r['n']):>10}{r['factor_kwh']:>14.4f}")
        print()

    prov_out_path = os.path.join(os.path.dirname(__file__), 'ers_ghg_electricity_by_province_year.csv')
    by_prov_year.to_csv(prov_out_path, index=False)
    print(f"Wrote {prov_out_path}")

    print("\n=== Combined per-fuel-per-province-per-year table (all fuels, n>=1) ===")
    combined = data.groupby(['fuel', 'province', 'year']).apply(
        lambda g: pd.Series({
            'n': len(g),
            'factor_native': g['ghg_tonnes'].sum() / g['consumption_native'].sum(),
            'factor_kwh': g['ghg_tonnes'].sum() * 1000 / g['consumption_kwh'].sum(),
        }), include_groups=False
    ).reset_index()
    combined_out_path = os.path.join(os.path.dirname(__file__), 'ers_ghg_factors_by_province_year.csv')
    combined.to_csv(combined_out_path, index=False)
    print(f"Wrote {combined_out_path} ({len(combined):,} fuel/province/year cells)")

    print("\n=== Electricity pooled by province (all years, n>=20) ===")
    prov_pooled = elec.groupby('province').apply(
        lambda g: pd.Series({
            'n': len(g),
            'factor_kwh': g['ghg_tonnes'].sum() * 1000 / g['consumption_kwh'].sum(),
        }), include_groups=False
    ).reset_index()
    prov_pooled = prov_pooled[prov_pooled['n'] >= 20].sort_values('factor_kwh')
    print(f"{'Province':<10}{'n':>10}{'kg CO2e/kWh':>14}")
    for _, r in prov_pooled.iterrows():
        print(f"{r['province']:<10}{int(r['n']):>10}{r['factor_kwh']:>14.4f}")


if __name__ == '__main__':
    main()
