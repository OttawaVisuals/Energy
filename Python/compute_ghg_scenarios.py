"""
compute_ghg_scenarios.py

Sidecar pipeline step (Step 1c, like join_hp_capacity.py's Step 1b): adds 6
GHG scenario columns to each province's parquet, computed from each home's
OWN fuel consumption (Pre_/Post_Electricity/NaturalGas/Oil/Propane/Wood --
already ~100% complete) rather than the raw ERSGHG field, which is only
populated for 50.5% of matched pairs (see docs/RETROFITS.md).

Why this exists: retrofits.html and retrofit-insights.html's GHG charts read
Pre_GHG/Post_GHG (raw ERSGHG) directly today, so almost half of matched pairs
are silently excluded from every GHG median/total on both pages. See
docs/ENERGUIDE_QUESTIONS.md SS5.4 for the full investigation (why HOT2000's own
factor can't be reproduced exactly, and why Alberta/Newfoundland need a
correction) and Python/ghg_factors.py for the factor constants/citations.

Adds, alongside the existing (untouched) Pre_GHG/Post_GHG:
  Pre_/Post_GHG_current            -- flat 2026 official OBPS factor
  Pre_/Post_GHG_current_corrected  -- same, AB/NF use ERS-calibrated instead
  Pre_/Post_GHG_as_audited         -- ERS-calibrated, matched to each side's
                                       own audit year (Pre_Date / Post_Date)

Combustion (gas/oil/propane) uses the FIXED official constants for scenarios
1/2, but YEAR-VARYING ERS-calibrated factors for scenario 3 -- see
ghg_factors.py's module docstring "WHY SCENARIO 3 NEEDS YEAR-VARYING
COMBUSTION" (Ontario's own ERSNGASGHG runs near-zero 2006-2016 despite real
consumption; a flat modern factor overstates historical gas GHG badly).
Wood is always 0 (biogenic-neutral; no official factor exists, and the
ERS-implied ratio is not physically plausible) in every scenario.

INPUT:  <OUTPUT_DIR>/ers_web_<PROVINCE>.parquet  (Step 1 output)
        Python/ers_ghg_factors_by_province_year.csv (Python/ers_ghg_factors.py output)
OUTPUT: same parquet, overwritten in place with 6 new columns.

Idempotent: safe to re-run after ers_ghg_factors.py or ghg_factors.py change
-- recomputes and overwrites the 6 columns each time.
"""

import glob
import os
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

import ghg_factors as gf

OUTPUT_DIR = r"C:\ERS\web"   # same as ers_web_pipeline.py's OUTPUT_DIR

CONSUMPTION_COLS = ["Electricity", "NaturalGas", "Oil", "Propane", "Wood"]

SCENARIOS = ["current", "current_corrected", "as_audited"]
NEW_COLS = [f"{side}_GHG_{scen}" for side in ("Pre", "Post") for scen in SCENARIOS]


def num(s):
    return pd.to_numeric(s, errors="coerce").fillna(0.0)


def compute_side_ghg(df, side, province, ers_elec, ers_combustion):
    """Returns a dict of {scenario: pd.Series of tCO2e} for one side (Pre/Post)."""
    elec = num(df[f"{side}_Electricity"])
    gas = num(df[f"{side}_NaturalGas"])
    oil = num(df[f"{side}_Oil"])
    prop = num(df[f"{side}_Propane"])
    wood = num(df[f"{side}_Wood"])
    year = df[f"{side}_Date"].astype(str).str.slice(0, 4)
    years_unique = year.unique()

    # scenarios 1/2: fixed official combustion constants (see ghg_factors.py
    # module docstring for why this is fine for these two but not scenario 3)
    gas_f, oil_f, prop_f, wood_f = gf.official_combustion_g_per_kwh(province)
    combustion_g_official = gas * gas_f + oil * oil_f + prop * prop_f + wood * wood_f

    out = {}

    current_elec_f = gf.current_electricity_g_per_kwh(province, ers_elec)
    out["current"] = (elec * current_elec_f + combustion_g_official) / 1e6

    corrected_elec_f = gf.current_corrected_electricity_g_per_kwh(province, ers_elec)
    out["current_corrected"] = (elec * corrected_elec_f + combustion_g_official) / 1e6

    # scenario 3: ERS-calibrated, year-varying, for BOTH electricity and
    # combustion -- see "WHY SCENARIO 3 NEEDS YEAR-VARYING COMBUSTION" in
    # ghg_factors.py's module docstring.
    elec_year_factors = {y: gf.as_audited_electricity_g_per_kwh(province, y, ers_elec)
                          for y in years_unique}
    elec_f_as_audited = year.map(elec_year_factors).astype(float)

    combustion_year_factors = {y: ers_combustion.factors_g_per_kwh(province, y)
                                for y in years_unique}
    gas_f_aa = year.map({y: v[0] for y, v in combustion_year_factors.items()}).astype(float)
    oil_f_aa = year.map({y: v[1] for y, v in combustion_year_factors.items()}).astype(float)
    prop_f_aa = year.map({y: v[2] for y, v in combustion_year_factors.items()}).astype(float)
    # wood factor is always 0 (combustion_year_factors[y][3]); no term needed.

    out["as_audited"] = (elec * elec_f_as_audited + gas * gas_f_aa
                          + oil * oil_f_aa + prop * prop_f_aa) / 1e6

    return out


def process_parquet(path, ers_elec, ers_combustion):
    province = Path(path).stem.replace("ers_web_", "")
    df = pd.read_parquet(path)

    for side in ("Pre", "Post"):
        missing = [c for c in CONSUMPTION_COLS if f"{side}_{c}" not in df.columns]
        if missing or f"{side}_Date" not in df.columns:
            print(f"  {province}: missing {side} columns {missing or [f'{side}_Date']}, skipping")
            return
        results = compute_side_ghg(df, side, province, ers_elec, ers_combustion)
        for scen, series in results.items():
            df[f"{side}_GHG_{scen}"] = series.round(4)

    print(f"  {province}: {len(df):,} rows -- added {len(NEW_COLS)} scenario columns")

    tmp_path = str(path) + ".tmp"
    table = pa.Table.from_pandas(df, preserve_index=False)
    pq.write_table(table, tmp_path, compression="snappy")
    os.replace(tmp_path, path)


def main():
    if not os.path.exists(gf.ERS_FACTOR_TABLE):
        print(f"!! {gf.ERS_FACTOR_TABLE} not found -- run ers_ghg_factors.py first")
        return
    ers_elec = gf.ErsElectricityFactors()
    ers_combustion = gf.ErsCombustionFactors()

    parquet_files = sorted(glob.glob(os.path.join(OUTPUT_DIR, "ers_web_*.parquet")))
    if not parquet_files:
        print(f"!! no province parquets found in {OUTPUT_DIR}")
        return

    print(f"Adding GHG scenario columns to {len(parquet_files)} province parquets...")
    for path in parquet_files:
        process_parquet(path, ers_elec, ers_combustion)

    print(f"\ndone. {len(parquet_files)} province parquets updated in place.")


if __name__ == "__main__":
    main()
