# ONGrid.py
# Single script that produces three output files for Power BI:
#
#   All_Generators_Aggregated.csv  — generation data
#       Columns: HourIndex, Fuel Type, Region, Output, Capability, Capacity, Utilization
#
#   Emission_Factors.csv           — subregional consumption-based EFs
#       Columns: HourIndex, Region, EmissionFactor_tCO2e_per_MWh
#
#   Date_Table.csv                 — dimension table for Power BI time axis
#       Columns: HourIndex, Date, Hour, Year, Quarter, Month, MonthName,
#                WeekOfYear, DayOfYear, DayOfMonth, DayOfWeek, DayName, IsWeekend
#
# Inputs required in DIR:
#   - IESO generator output CSVs (PUB_GenOutputCapabilityMonth_YYYYMM.csv)
#   - Generator_List.csv
#   - SubOntario_Consumption_EF_YYYY.csv (one per year, from colleague)
#
# pip install pandas

import os
import glob
import pandas as pd
from io import StringIO

# ─── CONFIG ───────────────────────────────────────────────────────────────────

DIR            = r"C:\_IESO"
GENERATOR_LIST = os.path.join(DIR, "Generator_List.csv")
GEN_OUT        = os.path.join(DIR, "All_Generators_Aggregated.csv")
EF_OUT         = os.path.join(DIR, "Emission_Factors.csv")
DATE_OUT       = os.path.join(DIR, "Date_Table.csv")
REPORT_CSV     = os.path.join(DIR, "Aggregation_Report.csv")
UNMATCHED_CSV  = os.path.join(DIR, "Unmatched_Generators.csv")

START_DATE = pd.Timestamp("2020-01-01")

# ─── MEASUREMENT MAPPING ──────────────────────────────────────────────────────
# Fuel types with Capability/Output:                  Nuclear, Natural Gas, Biofuel
# Fuel types with Available Capacity/Forecast/Output: Hydro, Wind, Solar
#
#   Output     → "Output" measurement (all fuel types)
#   Capability → available capacity: "Capability" (thermal) or "Forecast" (renewables)
#   Capacity   → total system capacity: "Capability" (thermal) or "Available Capacity" (renewables)

MEASUREMENT_TO_OUTPUT     = "Output"
MEASUREMENT_TO_CAPABILITY = {"Capability", "Forecast"}
MEASUREMENT_TO_CAPACITY   = {"Capability", "Available Capacity"}

# Regions in the EF files (Ontario = province-wide aggregate)
EF_REGIONS = ["Ontario", "Northwest", "Northeast", "Ottawa", "East",
              "Toronto", "Essa", "Bruce", "Southwest", "Niagara", "West"]

# ════════════════════════════════════════════════════════════════════════════
# PART 1 — GENERATION AGGREGATION
# ════════════════════════════════════════════════════════════════════════════

print("=" * 60)
print("PART 1 — Generation aggregation")
print("=" * 60)

# ─── LOAD REGION LOOKUP ───────────────────────────────────────────────────────

# 'utf-8-sig' handles Excel-saved CSVs with a hidden BOM character at the start
gen_list = pd.read_csv(GENERATOR_LIST, encoding='utf-8-sig')
gen_list.columns = gen_list.columns.str.strip()

# Build { "GENERATOR_NAME": "Region" } for fast lookups with .map()
gen_lookup = gen_list.set_index('Generator List')['Region'].to_dict()

# ─── FIND INPUT FILES ─────────────────────────────────────────────────────────

# Exclude all output files and the EF files from the colleague
excluded = {
    "All_Generators_Aggregated.csv", "Aggregation_Report.csv",
    "Generator_List.csv", "Unmatched_Generators.csv",
    "Emission_Factors.csv", "Date_Table.csv", "emission_rates.csv"
}
all_files = [f for f in os.listdir(DIR) if f.lower().endswith(".csv")]
csv_files = sorted([
    f for f in all_files
    if "_v" not in f.lower()
    and f not in excluded
    and not f.startswith("SubOntario_")  # skip EF files from colleague
])

print(f"\nFound {len(csv_files)} generator CSV files to aggregate.")

all_data      = []
report_rows   = []
all_unmatched = {}

# ─── PROCESS EACH FILE ────────────────────────────────────────────────────────

for name in csv_files:
    path = os.path.join(DIR, name)

    try:
        print(f"\n📄 {name}")

        # Read raw text and strip trailing commas.
        # IESO CSVs sometimes pad every line with trailing commas, which makes
        # pandas think there's an extra empty column.
        with open(path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        cleaned_content = ''.join(line.rstrip(',\n') + '\n' for line in lines)

        # Parse CSV.
        # - skiprows=3: first 3 rows are IESO metadata, not data
        # - dtype=str: keep everything as text until we explicitly convert
        # - na_filter=False: empty cells become '' not NaN
        df = pd.read_csv(
            StringIO(cleaned_content),
            skiprows=3,
            header=0,
            dtype=str,
            on_bad_lines="skip",
            na_filter=False,
            skipinitialspace=True,
            encoding='utf-8',
            sep=','
        )

        if 'Generator' not in df.columns:
            print(f"⚠️  'Generator' column not found, skipping")
            continue

        # Normalize Fuel Type to title case (HYDRO → Hydro, etc.)
        if 'Fuel Type' in df.columns:
            df['Fuel Type'] = df['Fuel Type'].str.title()

        # Parse Delivery Date and filter to Jan 1 2020 onward
        df['Delivery Date'] = pd.to_datetime(df['Delivery Date'], errors='coerce')
        df = df[df['Delivery Date'] >= START_DATE].copy()

        if df.empty:
            print(f"   ⏭️  No data on or after {START_DATE.date()}, skipping")
            continue

        # Map each generator to its region
        df['Region'] = df['Generator'].map(gen_lookup).fillna('Unknown')

        # Track unmatched generators for the report
        unmatched_rows = df[df['Region'] == 'Unknown'][['Generator', 'Fuel Type']].drop_duplicates()
        for _, row in unmatched_rows.iterrows():
            gen, fuel = row['Generator'], row['Fuel Type']
            if gen not in all_unmatched:
                all_unmatched[gen] = {'files': set(), 'fuels': set()}
            all_unmatched[gen]['files'].add(name)
            all_unmatched[gen]['fuels'].add(fuel)
        unmatched_names = unmatched_rows['Generator'].unique()
        if len(unmatched_names):
            print(f"   ⚠️  {len(unmatched_names)} generators not found in Generator_List")

        # Rename "Hour 1" → "1", "Hour 2" → "2", etc., then convert to numeric
        hour_cols = [col for col in df.columns if col.startswith('Hour ')]
        rename_map = {col: col.replace('Hour ', '') for col in hour_cols}
        df.rename(columns=rename_map, inplace=True)
        hour_cols = list(rename_map.values())
        for col in hour_cols:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)

        print(f"   Original: {len(df)} rows, {df['Generator'].nunique()} generators")

        # Aggregate — sum all hour columns across generators,
        # grouped by Date + Fuel Type + Region + Measurement
        groupby_cols = ['Delivery Date', 'Fuel Type', 'Region', 'Measurement']
        aggregated = df.groupby(groupby_cols, as_index=False).agg(
            {col: 'sum' for col in hour_cols}
        )

        # Unpivot hours into two columns: Hour (1–24) and Value
        melted = aggregated.melt(
            id_vars=groupby_cols,
            value_vars=hour_cols,
            var_name='Hour',
            value_name='Value'
        )
        melted['Hour'] = melted['Hour'].astype(int)

        # Pivot Measurement into Output, Capability, Capacity columns
        id_cols = ['Delivery Date', 'Fuel Type', 'Region', 'Hour']

        def extract_measure(df_melted, measure_names):
            """Filter to rows matching any of the given measurement names, sum by id_cols."""
            subset = df_melted[df_melted['Measurement'].isin(measure_names)]
            return subset.groupby(id_cols, as_index=False)['Value'].sum()

        base = melted[id_cols].drop_duplicates()
        for col_name, measure_names in [
            ("Output",     {MEASUREMENT_TO_OUTPUT}),
            ("Capability", MEASUREMENT_TO_CAPABILITY),
            ("Capacity",   MEASUREMENT_TO_CAPACITY),
        ]:
            base = base.merge(
                extract_measure(melted, measure_names).rename(columns={'Value': col_name}),
                on=id_cols, how='left'
            )

        # Compute Utilization = Output / Capability.
        # Returns null for division by zero, missing Capability, or values > 100%
        # so Power BI averages aren't skewed by bad data.
        base['Utilization'] = base.apply(
            lambda r: None if (pd.isna(r['Capability']) or r['Capability'] == 0
                               or r['Output'] / r['Capability'] > 1)
                      else r['Output'] / r['Capability'],
            axis=1
        )

        # Add HourIndex and drop Delivery Date + Hour — those live in Date_Table
        base['HourIndex'] = (base['Delivery Date'] - START_DATE).dt.days * 24 + base['Hour']
        base = base[['HourIndex', 'Fuel Type', 'Region',
                     'Output', 'Capability', 'Capacity', 'Utilization']]

        all_data.append(base)
        print(f"   ✅ Shaped to {len(base):,} rows")

        report_rows.append({
            "File": name,
            "OriginalRows": len(df),
            "ShapedRows": len(base),
            "UniqueGenerators": df['Generator'].nunique(),
            "UnmatchedGenerators": len(unmatched_names)
        })

    except Exception as e:
        print(f"❌ Error reading {name} -> {e}")
        import traceback
        traceback.print_exc()
        report_rows.append({
            "File": name,
            "OriginalRows": 0,
            "ShapedRows": 0,
            "UniqueGenerators": 0,
            "UnmatchedGenerators": 0
        })

# ─── WRITE GENERATION OUTPUT ──────────────────────────────────────────────────

if all_data:
    out = pd.concat(all_data, ignore_index=True)
    out = out.sort_values(['HourIndex', 'Fuel Type', 'Region']).reset_index(drop=True)

    # Data completeness check — flag any HourIndex with zero, null, or missing Output
    hour_totals  = out.groupby('HourIndex')['Output'].sum()
    missing      = hour_totals[hour_totals == 0].index.tolist()
    null_hours   = out[out['Output'].isna()]['HourIndex'].nunique()
    full_range   = pd.RangeIndex(out['HourIndex'].min(), out['HourIndex'].max() + 1)
    gap_indexes  = sorted(set(full_range) - set(hour_totals.index))
    gaps         = len(gap_indexes)

    # Convert missing HourIndexes back to readable dates for easier diagnosis.
    # Group consecutive HourIndexes into date ranges to keep the output concise.
    def gap_indexes_to_date_ranges(indexes):
        if not indexes:
            return []
        ranges = []
        start = prev = indexes[0]
        for idx in indexes[1:]:
            if idx == prev + 1:
                prev = idx
            else:
                ranges.append((start, prev))
                start = prev = idx
        ranges.append((start, prev))
        results = []
        for s, e in ranges:
            s_date = START_DATE + pd.Timedelta(hours=s - 1)
            e_date = START_DATE + pd.Timedelta(hours=e - 1)
            if s == e:
                results.append(f"HourIndex {s} ({s_date.strftime('%Y-%m-%d H%H')})")
            else:
                results.append(f"HourIndex {s}–{e} ({s_date.strftime('%Y-%m-%d')} → {e_date.strftime('%Y-%m-%d')})")
        return results

    print(f"\n─── Data completeness check ───")
    print(f"{'✅' if not missing   else '⚠️ '} Zero-output hours:  {len(missing)}"
          + (f" — first 10: {missing[:10]}" if missing else ""))
    print(f"{'✅' if not null_hours else '⚠️ '} Null Output rows:   {null_hours} HourIndex value(s) affected")
    if gaps:
        date_ranges = gap_indexes_to_date_ranges(gap_indexes)
        print(f"⚠️  HourIndex gaps:     {gaps} missing hour(s) across {len(date_ranges)} range(s):")
        for r in date_ranges:
            print(f"   • {r}")
    else:
        print(f"✅ HourIndex gaps:     0")

    out.to_csv(GEN_OUT, index=False, encoding='utf-8')
    print(f"\n✅ All_Generators_Aggregated.csv: {len(out):,} rows → {GEN_OUT}")
else:
    print("\n⚠️ No generation data to write.")

pd.DataFrame(report_rows).to_csv(REPORT_CSV, index=False, encoding='utf-8')
print(f"📝 Aggregation_Report.csv → {REPORT_CSV}")

if all_unmatched:
    pd.DataFrame([
        {"Generator": g, "Fuel Type": "; ".join(sorted(d['fuels'])),
         "FoundInFiles": "; ".join(sorted(d['files']))}
        for g, d in sorted(all_unmatched.items())
    ]).to_csv(UNMATCHED_CSV, index=False, encoding='utf-8')
    print(f"⚠️  {len(all_unmatched)} unmatched generators → {UNMATCHED_CSV}")
    print(f"   → Add them to Generator_List.csv and re-run.")
else:
    print("✅ All generators matched to a region.")

# ════════════════════════════════════════════════════════════════════════════
# PART 2 — EMISSION FACTORS
# ════════════════════════════════════════════════════════════════════════════

print("\n" + "=" * 60)
print("PART 2 — Emission factor combine")
print("=" * 60)

ef_files = sorted(glob.glob(os.path.join(DIR, "SubOntario_Consumption_EF_*.csv")))

if not ef_files:
    print("⚠️  No SubOntario_Consumption_EF_YYYY.csv files found — skipping EF output.")
else:
    print(f"\nFound {len(ef_files)} EF file(s):")
    ef_frames = []

    for path in ef_files:
        df_ef = pd.read_csv(path, encoding='utf-8-sig')
        df_ef['Delivery Date'] = pd.to_datetime(df_ef['Delivery Date'], errors='coerce')
        df_ef['Hour'] = pd.to_numeric(df_ef['Hour'], errors='coerce')
        df_ef = df_ef.dropna(subset=['Delivery Date', 'Hour'])

        # Unpivot region columns into rows
        region_cols = [c for c in EF_REGIONS if c in df_ef.columns]
        melted_ef = df_ef.melt(
            id_vars=['Delivery Date', 'Hour'],
            value_vars=region_cols,
            var_name='Region',
            value_name='EmissionFactor_tCO2e_per_MWh'
        )
        ef_frames.append(melted_ef)
        print(f"  ✅ {os.path.basename(path)}: {len(melted_ef):,} rows")

    ef_out = pd.concat(ef_frames, ignore_index=True)
    ef_out['HourIndex'] = (ef_out['Delivery Date'] - START_DATE).dt.days * 24 + ef_out['Hour']
    ef_out = (ef_out[['HourIndex', 'Region', 'EmissionFactor_tCO2e_per_MWh']]
              .sort_values(['HourIndex', 'Region'])
              .reset_index(drop=True))

    ef_out.to_csv(EF_OUT, index=False, encoding='utf-8')
    print(f"\n✅ Emission_Factors.csv: {len(ef_out):,} rows → {EF_OUT}")
    print(f"   HourIndex range: {ef_out['HourIndex'].min()} → {ef_out['HourIndex'].max()}")

# ════════════════════════════════════════════════════════════════════════════
# PART 3 — DATE TABLE
# ════════════════════════════════════════════════════════════════════════════

print("\n" + "=" * 60)
print("PART 3 — Date table")
print("=" * 60)

if all_data:
    # Build from the full HourIndex range of the generation data — not from the
    # EF files — so the date table always covers all years even when EF files
    # lag behind (e.g. colleague has only published up to 2024).
    hour_min = out['HourIndex'].min()
    hour_max = out['HourIndex'].max()

    date_table = pd.DataFrame({'HourIndex': range(hour_min, hour_max + 1)})

    # Reconstruct datetime from HourIndex: index 1 = Hour 1 on Jan 1 2020
    date_table['_dt']       = START_DATE + pd.to_timedelta(date_table['HourIndex'] - 1, unit='h')
    date_table['Date']      = date_table['_dt'].dt.date
    date_table['Hour']      = date_table['_dt'].dt.hour + 1  # 1-based to match IESO convention
    date_table['Year']      = date_table['_dt'].dt.year
    date_table['Quarter']   = date_table['_dt'].dt.quarter
    date_table['Month']     = date_table['_dt'].dt.month
    date_table['MonthName'] = date_table['_dt'].dt.strftime('%B')
    date_table['WeekOfYear']= date_table['_dt'].dt.isocalendar().week.astype(int)
    date_table['DayOfYear'] = date_table['_dt'].dt.day_of_year
    date_table['DayOfMonth']= date_table['_dt'].dt.day
    date_table['DayOfWeek'] = date_table['_dt'].dt.dayofweek + 1  # 1=Monday, 7=Sunday
    date_table['DayName']   = date_table['_dt'].dt.strftime('%A')
    date_table['IsWeekend'] = date_table['DayOfWeek'].isin([6, 7]).astype(int)

    date_table = date_table[[
        'HourIndex', 'Date', 'Hour', 'Year', 'Quarter', 'Month', 'MonthName',
        'WeekOfYear', 'DayOfYear', 'DayOfMonth', 'DayOfWeek', 'DayName', 'IsWeekend'
    ]]

    date_table.to_csv(DATE_OUT, index=False, encoding='utf-8')
    print(f"\n✅ Date_Table.csv: {len(date_table):,} rows → {DATE_OUT}")
    print(f"   HourIndex range: {hour_min} → {hour_max}")
else:
    print("⚠️  No generation data — Date_Table.csv not written.")

print("\n" + "=" * 60)
print("Done.")
print("=" * 60)