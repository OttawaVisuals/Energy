"""
Phase 4 — Heating-load archetypes per launch city (PLAN.md Phase 4,
ROADMAP.md item 3).

Builds 3-4 archetypes per city (pre-1980 detached, 1980-2005 detached,
post-2005 detached, townhouse/row) from the ERS/EnerGuide web parquet
(Python/ers_web_pipeline.py output, C:\\ERS\\web\\ers_web_<PROV>.parquet).

For each archetype: median design heat loss (kW), floor area (m2), and
annual delivered space-heating energy (kWh); back out UA (W/K) from the
design heat loss at a data-driven city design temperature, then calibrate
a balance-point temperature (T_balance) so that UA x heating-degree-hours
(from the city's TMY series) reproduces the ERS median annual heating
energy within +/-10%.

Uses PRE-retrofit values throughout (see METHODOLOGY.md "Archetypes" —
the tool models replacing heating in an existing, un-retrofitted home).

Output: data/processed/archetypes.json
"""

import json
from pathlib import Path

import numpy as np
import pandas as pd

ERS_DIR = Path(r"C:\ERS\web")
TMY_PATH = Path(__file__).resolve().parent.parent / "data" / "interim" / "tmy_hourly.csv"
WEATHER_PATH = Path(__file__).resolve().parent.parent / "data" / "interim" / "weather_hourly.csv"
OUT_PATH = Path(__file__).resolve().parent.parent / "data" / "processed" / "archetypes.json"

# Indoor design temperature (HOT2000 default main-living-space heating
# setpoint) used to back out UA from EGHDESHTLOSS-derived design heat loss.
T_INDOOR_DESIGN_C = 21.0

# City -> (province parquet, FSA-prefix list). FSA prefixes chosen from
# Canada Post geography: Ottawa urban core = K1/K2 (K4 = Kanata/Stittsville
# outer suburb, included; K0/K6/K7/K8/K9 are other Eastern Ontario towns,
# excluded). Toronto = all M. Montreal = all H (island + Laval H7/H9).
# Calgary = T2/T3. Edmonton = T5/T6.
CITY_CONFIG = {
    "Ottawa":   {"province": "ON", "fsa_prefixes": ["K1", "K2", "K4"]},
    "Toronto":  {"province": "ON", "fsa_prefixes": ["M"]},
    "Montreal": {"province": "QC", "fsa_prefixes": ["H"]},
    "Calgary":  {"province": "AB", "fsa_prefixes": ["T2", "T3"]},
    "Edmonton": {"province": "AB", "fsa_prefixes": ["T5", "T6"]},
}

DETACHED_TYPES = {"single detached"}
ROW_TYPES = {"row house, end unit", "row house, middle unit"}

MIN_N_HOMES = 30  # below this, flag low-confidence in the output

COLS = [
    "FSA", "YearBuilt", "FloorArea", "BldgType",
    "Pre_HeatLoss", "Pre_HeatEnergy", "Pre_HeatSeasonalCOP",
]


def load_province(prov):
    path = ERS_DIR / f"ers_web_{prov}.parquet"
    df = pd.read_parquet(path, columns=COLS)
    df["YearBuilt"] = pd.to_numeric(df["YearBuilt"], errors="coerce")
    df["FloorArea"] = pd.to_numeric(df["FloorArea"], errors="coerce")
    df["Pre_HeatLoss"] = pd.to_numeric(df["Pre_HeatLoss"], errors="coerce")
    df["Pre_HeatEnergy"] = pd.to_numeric(df["Pre_HeatEnergy"], errors="coerce")
    df["Pre_HeatSeasonalCOP"] = pd.to_numeric(df["Pre_HeatSeasonalCOP"], errors="coerce")
    df["BldgType_norm"] = df["BldgType"].astype(str).str.strip().str.lower()

    # Fuel-input -> delivered space-heat energy. Pre_HeatEnergy (EGHFURNACEAEC)
    # is annual fuel/electricity *input* to the primary heating system;
    # Pre_HeatSeasonalCOP (EGHFURSEASEFF) is its seasonal efficiency (AFUE-style
    # percentage for combustion equipment, ~100 for electric-resistance). The
    # UA x HDH load model represents heat *delivered* to the building, so we
    # convert: delivered = input x (efficiency / 100).
    df["Pre_HeatDelivered"] = df["Pre_HeatEnergy"] * (df["Pre_HeatSeasonalCOP"] / 100.0)

    # Plausibility filters — drop parsing junk / outliers before taking medians.
    df = df[
        df["FloorArea"].between(40, 1000)
        & df["YearBuilt"].between(1900, 2026)
        & df["Pre_HeatLoss"].between(1, 50)
        & df["Pre_HeatSeasonalCOP"].between(30, 400)
        & df["Pre_HeatDelivered"].between(500, 100_000)
    ]
    return df


def select_city_rows(df, fsa_prefixes):
    mask = np.zeros(len(df), dtype=bool)
    fsa = df["FSA"].astype(str)
    for prefix in fsa_prefixes:
        mask |= fsa.str.startswith(prefix)
    return df[mask]


def archetype_slices(df):
    """Yield (archetype_name, sub-dataframe) for the 4 archetypes."""
    detached = df[df["BldgType_norm"].isin(DETACHED_TYPES)]
    row = df[df["BldgType_norm"].isin(ROW_TYPES)]

    yield "pre_1980_detached", detached[detached["YearBuilt"] < 1980]
    yield "1980_2005_detached", detached[detached["YearBuilt"].between(1980, 2005)]
    yield "post_2005_detached", detached[detached["YearBuilt"] > 2005]
    yield "townhouse_row", row


def city_design_temp(city):
    """
    2.5th-percentile January outdoor temperature from our own ECCC hourly
    record (data/interim/weather_hourly.csv) — a data-driven proxy for the
    NBC-style "January 2.5%" HVAC design temperature. Uses our own 2019-2026
    record (8 years) rather than NBC's 30-year climate normal, so treat as
    approximate; it landed within ~2-4 C of commonly published NBC 2020
    Appendix C design temperatures for these five stations during spot-check.
    """
    weather = pd.read_csv(WEATHER_PATH, parse_dates=["Date"])
    jan = weather[(weather["City"] == city) & (weather["Date"].dt.month == 1)]
    return float(jan["Temperature_C"].quantile(0.025))


def load_tmy(city):
    tmy = pd.read_csv(TMY_PATH)
    return tmy[tmy["City"] == city]["Temperature_C"].to_numpy(dtype=float)


def annual_load_kwh(ua_w_per_k, t_balance_c, tmy_temps_c):
    """UA (W/K) x sum of hourly (Tbalance - Tout)+ over the TMY year -> kWh."""
    deg_hours = np.clip(t_balance_c - tmy_temps_c, a_min=0, a_max=None).sum()
    return ua_w_per_k * deg_hours / 1000.0


def calibrate_t_balance(ua_w_per_k, target_kwh, tmy_temps_c, lo=8.0, hi=21.0):
    """
    Bisection on T_balance so that annual_load_kwh(UA, Tbalance, TMY) matches
    target_kwh. annual_load_kwh is monotonically non-decreasing in Tbalance
    (raising Tbalance can only add positive-ΔT hours), so bisection is safe.
    Returns (t_balance, reconstructed_kwh, clamped: bool).
    """
    f_lo = annual_load_kwh(ua_w_per_k, lo, tmy_temps_c) - target_kwh
    f_hi = annual_load_kwh(ua_w_per_k, hi, tmy_temps_c) - target_kwh

    if f_lo >= 0:
        return lo, annual_load_kwh(ua_w_per_k, lo, tmy_temps_c), True
    if f_hi <= 0:
        return hi, annual_load_kwh(ua_w_per_k, hi, tmy_temps_c), True

    for _ in range(60):
        mid = (lo + hi) / 2.0
        f_mid = annual_load_kwh(ua_w_per_k, mid, tmy_temps_c) - target_kwh
        if abs(f_mid) < 1e-6:
            break
        if f_mid > 0:
            hi = mid
        else:
            lo = mid
    t_bal = (lo + hi) / 2.0
    return t_bal, annual_load_kwh(ua_w_per_k, t_bal, tmy_temps_c), False


def main():
    print("=== Phase 4: heating-load archetypes ===\n")

    province_frames = {}
    for city, cfg in CITY_CONFIG.items():
        prov = cfg["province"]
        if prov not in province_frames:
            print(f"loading ERS parquet for {prov} ...")
            province_frames[prov] = load_province(prov)

    results = {}
    validation_rows = []

    for city, cfg in CITY_CONFIG.items():
        prov = cfg["province"]
        df_prov = province_frames[prov]
        df_city = select_city_rows(df_prov, cfg["fsa_prefixes"])
        t_design = city_design_temp(city)
        tmy_temps = load_tmy(city)

        print(f"\n--- {city} (FSA {'/'.join(cfg['fsa_prefixes'])}, "
              f"n={len(df_city):,}, design temp={t_design:.1f} C) ---")

        city_out = {}
        for arch_name, sub in archetype_slices(df_city):
            n = len(sub)
            if n == 0:
                print(f"  {arch_name}: 0 homes — skipped")
                continue

            design_heat_loss_kw = float(sub["Pre_HeatLoss"].median())
            floor_area_m2 = float(sub["FloorArea"].median())
            annual_heat_kwh_observed = float(sub["Pre_HeatDelivered"].median())

            ua_w_per_k = design_heat_loss_kw * 1000.0 / (T_INDOOR_DESIGN_C - t_design)

            t_balance, reconstructed_kwh, clamped = calibrate_t_balance(
                ua_w_per_k, annual_heat_kwh_observed, tmy_temps
            )
            pct_error = (reconstructed_kwh - annual_heat_kwh_observed) / annual_heat_kwh_observed * 100.0

            flag = "" if n >= MIN_N_HOMES else "  [LOW N — low confidence]"
            clamp_flag = "  [T_balance clamped to bound]" if clamped else ""
            print(f"  {arch_name:22s} n={n:6,d}  UA={ua_w_per_k:7.1f} W/K  "
                  f"Tbal={t_balance:5.1f} C  design_loss={design_heat_loss_kw:5.2f} kW  "
                  f"area={floor_area_m2:6.1f} m2  obs={annual_heat_kwh_observed:8.0f} kWh  "
                  f"recon={reconstructed_kwh:8.0f} kWh  err={pct_error:+5.1f}%{flag}{clamp_flag}")

            city_out[arch_name] = {
                "UA_W_per_K": round(ua_w_per_k, 1),
                "Tbalance_C": round(t_balance, 2),
                "design_heat_loss_kW": round(design_heat_loss_kw, 2),
                "floor_area_m2": round(floor_area_m2, 1),
                "annual_heat_kWh": round(annual_heat_kwh_observed, 0),
                "n_homes": n,
            }

            validation_rows.append({
                "city": city, "archetype": arch_name, "n_homes": n,
                "design_temp_C": round(t_design, 1),
                "observed_annual_kWh": round(annual_heat_kwh_observed, 0),
                "reconstructed_annual_kWh": round(reconstructed_kwh, 0),
                "pct_error": round(pct_error, 1),
                "within_10pct": abs(pct_error) <= 10.0,
            })

        results[city] = city_out

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    print(f"\nwrote {OUT_PATH}")

    print("\n=== Validation: reconstructed vs observed annual heating energy ===")
    val_df = pd.DataFrame(validation_rows)
    print(val_df.to_string(index=False))
    n_fail = (~val_df["within_10pct"]).sum()
    print(f"\n{len(val_df) - n_fail}/{len(val_df)} archetypes within +/-10% "
          f"({n_fail} outside tolerance)")

    val_csv = Path(__file__).resolve().parent.parent / "data" / "interim" / "archetype_validation.csv"
    val_df.to_csv(val_csv, index=False)
    print(f"wrote {val_csv}")


if __name__ == "__main__":
    main()
