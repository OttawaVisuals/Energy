"""
compute_ghg_scenarios.py

Sidecar pipeline step (Step 1c, like join_hp_capacity.py's Step 1b): adds
2 GHG columns to each province's parquet, computed from each home's OWN fuel
consumption (Pre_/Post_Electricity/NaturalGas/Oil/Propane/Wood -- already
~100% complete) times the CURRENT (2026) official emission factors:

  Pre_/Post_GHG_current  -- tCO2e/yr. Electricity: flat 2026 ECCC/OBPS grid
                            factor for the home's province. Gas/oil/propane:
                            fixed official combustion constants. Wood: 0
                            (biogenic-neutral; no official factor exists).

Factor constants and citations live in Python/ghg_factors.py.

WHY ONE BASIS (decided 2026-09-23). Until then this step wrote three
scenarios (current / current_corrected / as_audited), the last two built on
emission factors back-calculated from the audit's own ERSGHG field, and the
pages also offered raw ERSGHG. The EnerGuide data team advised using current
emission factors only and ignoring their GHG reporting: ERSGHG was reported
for only ~50% of matched pairs, and the factors behind it were updated
sporadically. The retired scenarios and the ERS-vs-ECCC factor comparison
are recorded in docs/RETROFITS.md; Python/ers_ghg_factors.py (which derives
that comparison) is no longer part of the chain.

INPUT:  <OUTPUT_DIR>/ers_web_<PROVINCE>.parquet  (Step 1 output)
OUTPUT: same parquet, overwritten in place with the 2 columns.

Idempotent: safe to re-run after ghg_factors.py changes -- recomputes and
overwrites the 2 columns each time.
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

NEW_COLS = ["Pre_GHG_current", "Post_GHG_current"]


def num(s):
    return pd.to_numeric(s, errors="coerce").fillna(0.0)


def compute_side_ghg(df, side, province):
    """tCO2e/yr for one side (Pre/Post) at current (2026) official factors."""
    elec = num(df[f"{side}_Electricity"])
    gas = num(df[f"{side}_NaturalGas"])
    oil = num(df[f"{side}_Oil"])
    prop = num(df[f"{side}_Propane"])
    wood = num(df[f"{side}_Wood"])

    gas_f, oil_f, prop_f, wood_f = gf.official_combustion_g_per_kwh(province)
    elec_f = gf.current_electricity_g_per_kwh(province, None)
    return (elec * elec_f + gas * gas_f + oil * oil_f + prop * prop_f + wood * wood_f) / 1e6


def process_parquet(path):
    province = Path(path).stem.replace("ers_web_", "")
    df = pd.read_parquet(path)

    for side in ("Pre", "Post"):
        missing = [c for c in CONSUMPTION_COLS if f"{side}_{c}" not in df.columns]
        if missing:
            print(f"  {province}: missing {side} columns {missing}, skipping")
            return
        df[f"{side}_GHG_current"] = compute_side_ghg(df, side, province).round(4)

    # Drop columns from the retired scenarios if an older run left them behind.
    stale = [c for c in df.columns
             if c.endswith(("_GHG_current_corrected", "_GHG_as_audited"))]
    df = df.drop(columns=stale)

    print(f"  {province}: {len(df):,} rows -- wrote {NEW_COLS}"
          + (f", dropped stale {stale}" if stale else ""))

    tmp_path = str(path) + ".tmp"
    table = pa.Table.from_pandas(df, preserve_index=False)
    pq.write_table(table, tmp_path, compression="snappy")
    os.replace(tmp_path, path)


def main():
    parquet_files = sorted(glob.glob(os.path.join(OUTPUT_DIR, "ers_web_*.parquet")))
    if not parquet_files:
        print(f"!! no province parquets found in {OUTPUT_DIR}")
        return

    print(f"Adding current-factor GHG columns to {len(parquet_files)} province parquets...")
    for path in parquet_files:
        process_parquet(path)

    print(f"\ndone. {len(parquet_files)} province parquets updated in place.")


if __name__ == "__main__":
    main()
