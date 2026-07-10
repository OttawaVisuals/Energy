# build_grid_ef.py
# Computes Ontario hourly grid emissions intensity (average + marginal) from
# IESO generation-by-fuel data (see fetch_ieso.py), using a gas combustion
# emission factor calibrated against The Atmospheric Fund's published,
# NIR-sourced Annual Average Emissions Factors (2024 edition).
#
# Methodology (matches TAF's approach, itself built on IESO + NIR data):
#   - Direct (combustion) emissions only. Nuclear/Hydro/Wind/Solar/Biofuel/
#     Other treated as zero-emission generation (consistent with TAF's
#     methodology, which attributes essentially all direct grid emissions
#     to natural gas).
#   - Average EF(h) = gas_output(h) / total_output(h) * GAS_EF_G_PER_KWH
#   - Marginal EF(h) = GAS_EF_G_PER_KWH whenever gas output(h) > 0, else
#     Average EF(h). In Ontario, gas is on nearly every hour in recent
#     years, so marginal ~= GAS_EF_G_PER_KWH most of the time.
#
# GAS_EF_G_PER_KWH calibration:
#   TAF (2024 edition, "Ontario Electricity Emissions Factors and
#   Guidelines") publishes Annual AEF = total emissions / total generation,
#   using IESO generation output and NIR's natural gas emissions intensity
#   (NIR gas generation in GWh / NIR gas emissions in ktCO2e). Their
#   published values: 2020->36, 2021->44, 2022->51, 2023->67 gCO2e/kWh.
#   Dividing each by our own computed gas-generation-fraction for that year
#   backs out an implied gas intensity of 526, 496, 474, 502 g/kWh
#   (avg ~500, spread +/-5%) -- consistent with PLAN.md's own estimate of
#   "gas CCGT/peakers ~490-550 g/kWh". We use 500 g CO2e/kWh as the single
#   documented gas combustion factor.
#   TODO: replace with a year-by-year NIR-derived gas intensity if/when we
#   pull NIR Part 3 Table A13 gas generation/emissions directly, instead of
#   backing it out of TAF's published AEF.
#
# Output: data/processed/grid_ef_on.json
#   { "hourly": [{Date, Hour, AvgEF_g_per_kWh, MarginalEF_g_per_kWh, GasFrac}, ...],
#     "meta": {...} }
#
# pip install pandas

import os
import sys
import json
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from grid_common import compute_ef_on, ON_GAS_EF_G_PER_KWH  # noqa: E402

# ─── CONFIG ───────────────────────────────────────────────────────────────────

HERE        = os.path.dirname(os.path.abspath(__file__))
IN_CSV      = os.path.join(HERE, "..", "data", "interim", "ieso_hourly_by_fuel.csv")
OUT_JSON    = os.path.join(HERE, "..", "data", "processed", "grid_ef_on.json")

GAS_EF_G_PER_KWH = ON_GAS_EF_G_PER_KWH  # see calibration note above, now in grid_common.py

# TAF (2024 ed.) published Annual AEF, gCO2e/kWh -- our validation targets.
# Source: "Ontario Electricity Emissions Factors and Guidelines", TAF, June 2024,
# p.11 (Historical Average Emissions Factors).
TAF_ANNUAL_AEF = {2015: 46, 2016: 40, 2017: 18, 2018: 29, 2019: 29,
                   2020: 36, 2021: 44, 2022: 51, 2023: 67}
VALIDATION_TOLERANCE = 0.15  # +/-15%, per PLAN.md

# ─── LOAD ─────────────────────────────────────────────────────────────────────

def load_generation() -> pd.DataFrame:
    df = pd.read_csv(IN_CSV)
    df["Date"] = pd.to_datetime(df["Date"])
    wide = df.pivot_table(index=["Date", "Hour"], columns="Fuel",
                           values="Output_MW", aggfunc="sum", fill_value=0.0)
    wide = wide.reset_index()
    fuel_cols = [c for c in wide.columns if c not in ("Date", "Hour")]
    wide["Total_MW"] = wide[fuel_cols].sum(axis=1)
    if "GAS" not in wide.columns:
        wide["GAS"] = 0.0
    return wide


# ─── COMPUTE EF ───────────────────────────────────────────────────────────────

def compute_ef(wide: pd.DataFrame) -> pd.DataFrame:
    return compute_ef_on(wide)


# ─── VALIDATE ─────────────────────────────────────────────────────────────────

def validate(ef: pd.DataFrame) -> None:
    print("\n" + "=" * 60)
    print("Validation vs TAF published Annual AEF (NIR-derived)")
    print("=" * 60)

    ef = ef.copy()
    ef["Year"] = ef["Date"].dt.year

    # Generation-weighted annual average (not a simple mean of hourly EFs)
    annual = ef.groupby("Year").apply(
        lambda g: (g["AvgEF_g_per_kWh"] * g["Total_MW"]).sum() / g["Total_MW"].sum(),
        include_groups=False,
    )

    all_ok = True
    for year, computed in annual.items():
        published = TAF_ANNUAL_AEF.get(year)
        if published is None:
            print(f"  {year}: computed={computed:5.1f} g/kWh   (no TAF reference)")
            continue
        pct_diff = (computed - published) / published
        ok = abs(pct_diff) <= VALIDATION_TOLERANCE
        all_ok &= ok
        flag = "OK" if ok else "FAIL"
        print(f"  {year}: computed={computed:5.1f}  published={published:5.1f}  "
              f"diff={pct_diff:+.1%}   [{flag}]")

    print("\n" + ("All years within +/-15% of TAF reference." if all_ok
                   else "One or more years outside +/-15% -- review GAS_EF_G_PER_KWH."))


# ─── MAIN ─────────────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("Ontario grid EF -- average + marginal, hourly")
    print("=" * 60)

    wide = load_generation()
    print(f"\nLoaded {len(wide):,} hourly rows, "
          f"{wide['Date'].min().date()} -> {wide['Date'].max().date()}")

    ef = compute_ef(wide)
    validate(ef)

    os.makedirs(os.path.dirname(OUT_JSON), exist_ok=True)
    hourly_records = [
        {
            "Date": row.Date.strftime("%Y-%m-%d"),
            "Hour": int(row.Hour),
            "AvgEF_g_per_kWh": round(row.AvgEF_g_per_kWh, 2),
            "MarginalEF_g_per_kWh": round(row.MarginalEF_g_per_kWh, 2),
            "GasFrac": round(row.GasFrac, 4),
        }
        for row in ef.itertuples(index=False)
    ]

    payload = {
        "meta": {
            "province": "ON",
            "gas_ef_g_per_kwh": GAS_EF_G_PER_KWH,
            "methodology": (
                "Direct combustion emissions only. All non-gas fuels treated "
                "as zero-emission. Gas EF calibrated against TAF (2024) "
                "published Annual AEF, itself NIR-derived. See build_grid_ef.py "
                "header and METHODOLOGY.md for full derivation."
            ),
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
