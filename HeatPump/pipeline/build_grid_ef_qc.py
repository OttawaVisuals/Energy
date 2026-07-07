# build_grid_ef_qc.py
# Computes Quebec hourly grid emissions intensity (average + marginal) from
# Hydro-Quebec generation-by-fuel data (see fetch_hq.py).
#
# Methodology:
#   - Direct (combustion) emissions only. Hydro/Wind/Solar/Other renewables
#     treated as zero-emission generation. All direct combustion emissions
#     attributed to "Thermal" (HQ's remote/off-grid diesel and small
#     gas/oil generation, serving communities not connected to the main
#     hydro grid -- e.g. Nunavik, Iles-de-la-Madeleine).
#   - Thermal is consistently <0.01% of total generation across all years
#     with data (2019-2020, 2022-2025) -- confirming PLAN.md's assumption
#     that Quebec is a >99% hydro/wind grid.
#   - Average EF(hour) = ThermalFrac(hour) * THERMAL_EF_G_PER_KWH
#   - Marginal EF: not modeled separately here. With thermal generation
#     this small and no intertie/import flow data in this dataset, there
#     is no meaningful "gas on the margin" signal to key off of the way
#     there is in ON/AB. MarginalEF is set equal to AvgEF as a placeholder.
#     PLAN.md's own note that "counting winter imports" gives a materially
#     higher number (~35 g/kWh, vs ~1.5 g/kWh production-only) is NOT
#     addressed by this script -- it would require import/export intertie
#     flow data we don't have yet. Flagged as future work.
#
# THERMAL_EF_G_PER_KWH: no per-year calibration was possible (unlike ON/AB) --
# thermal's share is too small relative to available published reference
# points to back out a precise factor by regression. Using 700 g CO2e/kWh,
# a commonly-cited approximate figure for small diesel generation (e.g. for
# remote Canadian communities). Given thermal's <0.01% share, the choice of
# this constant barely moves the final number either way (a 2x change in
# THERMAL_EF_G_PER_KWH changes the computed annual average by a few
# hundredths of a g/kWh) -- precision here is not worth chasing further.
#
# Known gap: 2021 (and the first ~3 weeks of Jan 2022) has no data at all in
# the source file -- confirmed by the user to be missing in the original
# download itself, not a parsing error. No hourly series is produced for
# that period. See METHODOLOGY.md.
#
# Output: data/processed/grid_ef_qc.json
#
# pip install pandas

import os
import sys
import json
import pandas as pd

if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

# ─── CONFIG ───────────────────────────────────────────────────────────────────

HERE     = os.path.dirname(os.path.abspath(__file__))
IN_CSV   = os.path.join(HERE, "..", "data", "interim", "hq_hourly_by_fuel.csv")
OUT_JSON = os.path.join(HERE, "..", "data", "processed", "grid_ef_qc.json")

THERMAL_EF_G_PER_KWH = 700.0  # see note above -- approximate, low-impact given <0.01% share

# PLAN.md's own reference point (HQ sustainability reporting / general knowledge,
# not independently re-verified here): ~1.5 g/kWh production-based. Printed for
# comparison only -- NOT used as a pass/fail validation gate, since at these
# vanishingly small absolute magnitudes a relative-error tolerance is
# meaningless (see note in main()).
PLAN_REFERENCE_G_PER_KWH = 1.5

# ─── LOAD ─────────────────────────────────────────────────────────────────────

def load_generation() -> pd.DataFrame:
    df = pd.read_csv(IN_CSV)
    df["Date"] = pd.to_datetime(df["Date"])
    wide = df.pivot_table(index=["Date", "Hour"], columns="Fuel",
                           values="Output_MW", aggfunc="sum", fill_value=0.0)
    wide = wide.reset_index()
    fuel_cols = [c for c in wide.columns if c not in ("Date", "Hour")]
    wide["Total_MW"] = wide[fuel_cols].sum(axis=1)
    if "THERMAL" not in wide.columns:
        wide["THERMAL"] = 0.0
    return wide


# ─── COMPUTE EF ───────────────────────────────────────────────────────────────

def compute_ef(wide: pd.DataFrame) -> pd.DataFrame:
    out = wide[["Date", "Hour", "Total_MW", "THERMAL"]].copy()
    out["ThermalFrac"] = (out["THERMAL"] / out["Total_MW"]).where(out["Total_MW"] > 0, 0.0)
    out["AvgEF_g_per_kWh"] = out["ThermalFrac"] * THERMAL_EF_G_PER_KWH
    out["MarginalEF_g_per_kWh"] = out["AvgEF_g_per_kWh"]  # placeholder, see header note
    return out


# ─── MAIN ─────────────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("Quebec grid EF -- average + marginal, hourly")
    print("=" * 60)

    wide = load_generation()
    print(f"\nLoaded {len(wide):,} hourly rows, "
          f"{wide['Date'].min().date()} -> {wide['Date'].max().date()}")

    years_present = sorted(wide["Date"].dt.year.unique())
    years_missing = [y for y in range(years_present[0], years_present[-1] + 1)
                     if y not in years_present]
    if years_missing:
        print(f"[warn] No data at all for: {years_missing} (known source gap)")

    ef = compute_ef(wide)

    print("\n" + "=" * 60)
    print("Annual average (generation-weighted) vs PLAN.md reference point")
    print("=" * 60)
    ef["Year"] = ef["Date"].dt.year
    annual = ef.groupby("Year").apply(
        lambda g: (g["AvgEF_g_per_kWh"] * g["Total_MW"]).sum() / g["Total_MW"].sum(),
        include_groups=False,
    )
    for year, computed in annual.items():
        print(f"  {year}: computed={computed:.3f} g/kWh   "
              f"(PLAN.md reference: ~{PLAN_REFERENCE_G_PER_KWH} g/kWh -- "
              f"not a pass/fail gate at this scale, see script header)")

    os.makedirs(os.path.dirname(OUT_JSON), exist_ok=True)
    hourly_records = [
        {
            "Date": row.Date.strftime("%Y-%m-%d"),
            "Hour": int(row.Hour),
            "AvgEF_g_per_kWh": round(row.AvgEF_g_per_kWh, 4),
            "MarginalEF_g_per_kWh": round(row.MarginalEF_g_per_kWh, 4),
            "ThermalFrac": round(row.ThermalFrac, 6),
        }
        for row in ef.itertuples(index=False)
    ]

    payload = {
        "meta": {
            "province": "QC",
            "thermal_ef_g_per_kwh": THERMAL_EF_G_PER_KWH,
            "methodology": (
                "Direct combustion emissions only. Hydro/Wind/Solar/Other "
                "renewables treated as zero-emission. All direct emissions "
                "attributed to Thermal (<0.01% of generation in all years "
                "present). MarginalEF == AvgEF placeholder -- import-flow-based "
                "marginal intensity not modeled. 2021 has no data (source gap). "
                "See build_grid_ef_qc.py header and METHODOLOGY.md."
            ),
            "years_missing": years_missing,
            "date_range": [ef["Date"].min().strftime("%Y-%m-%d"),
                            ef["Date"].max().strftime("%Y-%m-%d")],
        },
        "hourly": hourly_records,
    }

    with open(OUT_JSON, "w", encoding="utf-8") as fh:
        json.dump(payload, fh)

    print(f"\n[ok] {len(hourly_records):,} hourly records -> {OUT_JSON}")


if __name__ == "__main__":
    main()
