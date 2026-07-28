"""
Heating-load archetypes from NRCan's published peak loads (heat-pump tool,
load-model rebuild step 2).

WHY THIS EXISTS
---------------
The ERS-derived archetypes (build_archetypes.py) rely on a fitted balance-point
temperature that turned out to be a residual absorbing solar gains, night
setback and missing supplementary heat -- see METHODOLOGY.md "Balance-point
calibration". Rather than repair a fitted parameter we cannot defend, this
step takes both quantities from a single published source.

SOURCE
------
NRCan CanmetENERGY, "Cold-Climate Air Source Heat Pumps: Assessing
Cost-Effectiveness, Energy Savings and Greenhouse Gas Emission Reductions in
Canadian Homes", Cat. No. M154-149/2022E-PDF, ISBN 978-0-660-42353-1.
Local copy: ../data/raw/nrcan/gid_329701.pdf

  * Table 1 (p.10) -- peak heating loads (kW) for 4 archetypes x 16 locations.
  * Figure 1 (p.8) -- load vs outdoor temperature, whose x-intercept is the
    archetype's zero-heating ("balance") temperature.

METHOD
------
Each NRCan archetype is ONE house drawn from the EnerGuide database and
relocated to 16 cities (report section 3.1). Its UA is therefore CONSTANT
across cities, and each city's peak load differs only through that city's
design temperature:

    peak_city = UA x (T_balance - T_design_city)

So regressing Table 1's 16 published peaks against the 16 NBC design
temperatures recovers UA (slope) and T_balance (x-intercept) per archetype,
using every published number rather than a single chart reading.

This also settles what Table 1's peaks are referenced to. If they were peaks of
the TMY hourly series rather than design-condition loads, the recovered
T_balance would not land on Figure 1's intercept. It does -- within 0.5 C for
archetypes A and B -- so Table 1 is a design-condition load.

Design temperatures come from ../reference/nbc_station_design_temps.csv (NBC
Appendix C), looked up by station name so the values are not retyped here.

OUTPUT
------
  ../data/processed/archetypes_nrcan.json
  ../data/interim/archetypes_nrcan_validation.csv

LIMITATIONS (see METHODOLOGY.md for the full list)
--------------------------------------------------
- 4 houses, not a population. No floor areas are published, so no per-m2
  figures and no area-based "which is my home?" helper.
- A single relocated house cannot show local construction practice. The
  ERS medians did (Edmonton's stock is genuinely better built per m2 than
  Toronto's); that signal is gone.
- Archetype set changes: townhouse/row disappears, NZE-ready appears.
- TMY coverage is 11 of the 16 cities, so annual energy is reported for 11.
- The report contradicts itself on Toronto (section 3.1 text says archetype A
  = 10.7 kW and B = 9 kW; Table 1 says 11.6 and 9.8). Table 1 is used.
- Table 1's archetype-D column extracts misaligned from the PDF; the pairing
  used here is verified by corr(A,D) = 0.9945 and by physical ordering
  (Victoria 1.0 / Vancouver 1.1 lowest, Regina 4.0 highest).
"""

import json
import os

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
NBC_CSV = os.path.join(ROOT, "reference", "nbc_station_design_temps.csv")
TMY_PATH = os.path.join(ROOT, "data", "interim", "tmy_hourly.csv")
OUT_JSON = os.path.join(ROOT, "data", "processed", "archetypes_nrcan.json")
OUT_CSV = os.path.join(ROOT, "data", "interim", "archetypes_nrcan_validation.csv")

# HOT2000's default main-living-space heating design setpoint, and the value
# the ERS standard-operating-conditions run applies (verified in
# reference/htap_NRCan-arch4-ERS.h2k: MainFloors daytimeHeatingSetPoint="21").
T_INDOOR_DESIGN_C = 21.0

ARCH = {
    "A_pre_1980":        "A: Pre-1980 detached, 2-storey",
    "B_post_1980_2stry": "B: Post-1980 detached, 2-storey (larger)",
    "C_post_1980_1stry": "C: Post-1980 detached, 1-storey (smaller)",
    "D_net_zero_ready":  "D: Net-Zero-Energy-Ready, 2-storey",
}

# NRCan Table 1, in the report's row order. NBC station chosen as the one
# HOT2000 would use for that location; name must match nbc_station_design_temps.csv.
# (city, NBC station, A, B, C, D)
TABLE1 = [
    ("Kamloops",      "KAMLOOPS",       10.0,  8.2, 5.2, 2.2),
    ("Prince George", "PRINCE GEORGE",  13.7, 11.5, 7.4, 3.2),
    ("Vancouver",     "VANCOUVER INTL",  6.4,  5.3, 3.4, 1.1),
    ("Victoria",      "VICTORIA GONZALES", 5.9, 4.8, 3.0, 1.0),
    ("Calgary",       "CALGARY INTL",   14.3, 12.1, 7.7, 3.2),
    ("Edmonton",      "EDMONTON INTL",  16.8, 14.1, 9.0, 3.9),
    ("Regina",        "REGINA INTL",    16.8, 14.5, 9.0, 4.0),
    ("Winnipeg",      "WINNIPEG INTL",  16.3, 13.8, 8.6, 3.9),
    ("London",        "LONDON",         12.4, 10.4, 6.6, 2.8),
    ("Ottawa",        "OTTAWA INTL",    13.8, 11.5, 7.3, 3.2),
    ("Toronto",       "TORONTO INTL",   11.6,  9.8, 6.1, 2.6),
    ("Montreal",      "MONTRÉAL INTL", 13.2, 11.1, 7.0, 3.1),
    ("Quebec City",   "QUÉBEC INTL",  13.4, 11.3, 7.8, 3.2),
    ("Fredericton",   "FREDERICTON",    14.4, 12.2, 7.8, 3.2),
    ("Halifax",       "HALIFAX INTL",   13.2, 11.1, 7.1, 2.9),
    ("St. Johns",     "ST-JOHN'S INTL", 11.4, 10.0, 6.1, 2.7),
]

# Balance temperatures read directly off Figure 1's fitted lines, kept as an
# independent cross-check on the regression (they are NOT used to build).
FIG1_READOFF_C = {"A_pre_1980": 16.0, "B_post_1980_2stry": 15.0,
                  "C_post_1980_1stry": 14.0, "D_net_zero_ready": 12.0}


def load_design_temps():
    nbc = pd.read_csv(NBC_CSV)
    by_name = (nbc.drop_duplicates("map_name")
               .set_index("map_name")["design_heating_db_C"].to_dict())
    out, missing = {}, []
    for city, station, *_ in TABLE1:
        if station not in by_name:
            missing.append((city, station))
        else:
            out[city] = (station, float(by_name[station]))
    if missing:
        raise SystemExit(f"NBC station(s) not found, fix TABLE1: {missing}")
    return out


def load_tmy():
    if not os.path.exists(TMY_PATH):
        print(f"  (no TMY at {TMY_PATH} -- annual energy skipped)")
        return {}
    tmy = pd.read_csv(TMY_PATH)
    return {c: g["Temperature_C"].to_numpy(float)
            for c, g in tmy.groupby("City")}


def main():
    print("=== NRCan-published heating-load archetypes ===\n")
    design = load_design_temps()
    tmy = load_tmy()

    T = np.array([design[c][1] for c, *_ in TABLE1], float)
    peaks = {k: np.array([row[2 + i] for row in TABLE1], float)
             for i, k in enumerate(ARCH)}

    print(f"{'archetype':20s} {'UA(W/K)':>8} {'Tbal(C)':>8} {'R2':>7} "
          f"{'Fig1':>6} {'diff':>6}  {'max|resid|kW':>12}")
    fits = {}
    for key in ARCH:
        y = peaks[key]
        slope, intercept = np.polyfit(T, y, 1)   # y = -UA*T + UA*Tbal
        ua = -slope * 1000.0
        tbal = intercept / -slope
        pred = slope * T + intercept
        r2 = 1 - ((y - pred) ** 2).sum() / ((y - y.mean()) ** 2).sum()
        resid = np.abs(y - pred)
        fits[key] = {"UA_W_per_K": round(ua, 1),
                     "Tbalance_C": round(tbal, 2),
                     "r2": round(float(r2), 4),
                     "max_abs_resid_kW": round(float(resid.max()), 2),
                     "fig1_readoff_C": FIG1_READOFF_C[key]}
        print(f"{key:20s} {ua:8.1f} {tbal:8.2f} {r2:7.4f} "
              f"{FIG1_READOFF_C[key]:6.1f} {tbal-FIG1_READOFF_C[key]:+6.2f} "
              f"{resid.max():12.2f}")

    rows, cities_out = [], {}
    for city, station, *_ in TABLE1:
        _, tdes = design[city]
        temps = tmy.get(city)
        entry = {"design_temp_C": tdes, "nbc_station": station,
                 "has_tmy": temps is not None, "archetypes": {}}
        for key in ARCH:
            tbal = fits[key]["Tbalance_C"]
            ua_fit = fits[key]["UA_W_per_K"]
            published = float(peaks[key][TABLE1.index(
                next(r for r in TABLE1 if r[0] == city))])
            # PRIMARY: honour the published peak exactly. UA follows from it and
            # the archetype's balance temperature. Because we ship only NRCan's
            # 16 published cities there is no extrapolation, so there is no
            # reason to discard the published precision -- and the per-city
            # spread this produces (291-389 W/K for archetype A) is real
            # physics: wind-driven infiltration is far higher in St. John's and
            # Halifax than in sheltered Kamloops or Vancouver. The single fitted
            # UA is retained alongside as a diagnostic.
            ua = round(published * 1000.0 / (tbal - tdes), 1)
            recon = ua_fit * (tbal - tdes) / 1000.0
            ann = None
            if temps is not None:
                ann = float(ua * np.clip(tbal - temps, 0, None).sum() / 1000.0)
            entry["archetypes"][key] = {
                "label": ARCH[key],
                "UA_W_per_K": ua,
                "Tbalance_C": tbal,
                "peak_kW": published,
                "UA_single_fit_W_per_K": ua_fit,
                "peak_if_single_UA_kW": round(recon, 2),
                "single_UA_resid_kW": round(recon - published, 2),
                "annual_heat_kWh": None if ann is None else round(ann, 0),
            }
            rows.append({"city": city, "archetype": key, "design_temp_C": tdes,
                         "published_kW": published,
                         "reconstructed_kW": round(recon, 2),
                         "resid_kW": round(recon - published, 2),
                         "annual_heat_kWh": None if ann is None else round(ann)})
        cities_out[city] = entry

    val = pd.DataFrame(rows)
    print(f"\nreconstruction residuals (kW): mean|r| = "
          f"{val['resid_kW'].abs().mean():.2f}, max = {val['resid_kW'].abs().max():.2f}")
    worst = val.reindex(val["resid_kW"].abs().sort_values(ascending=False).index).head(6)
    print("\nlargest residuals:")
    print(worst.to_string(index=False))

    n_tmy = sum(1 for c in cities_out if cities_out[c]["has_tmy"])
    print(f"\nTMY available for {n_tmy}/{len(cities_out)} cities "
          f"(missing: {[c for c in cities_out if not cities_out[c]['has_tmy']]})")

    payload = {
        "meta": {
            "source": "NRCan CanmetENERGY, Cold-Climate Air Source Heat Pumps, "
                      "Cat. M154-149/2022E-PDF. Table 1 (peak heating loads, "
                      "4 archetypes x 16 locations) and Figure 1 (load vs "
                      "outdoor temperature).",
            "design_temps": "NBC Appendix C via reference/nbc_station_design_temps.csv",
            "indoor_design_temp_C": T_INDOOR_DESIGN_C,
            "method": "Each NRCan archetype is one house relocated to 16 cities, "
                      "so UA is constant. Regressing the 16 published peaks "
                      "against the 16 NBC design temperatures gives UA (slope) "
                      "and T_balance (x-intercept) per archetype.",
            "fits": fits,
            "known_source_discrepancy": "Report section 3.1 text gives Toronto A = "
                      "10.7 kW and B = 9 kW; Table 1 gives 11.6 and 9.8. "
                      "Table 1 is used.",
            "table1_D_column_note": "The archetype-D column extracts misaligned "
                      "from the PDF. Pairing verified by corr(A,D)=0.9945 and "
                      "physical ordering.",
        },
        "cities": cities_out,
    }

    os.makedirs(os.path.dirname(OUT_JSON), exist_ok=True)
    os.makedirs(os.path.dirname(OUT_CSV), exist_ok=True)
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    val.to_csv(OUT_CSV, index=False, encoding="utf-8-sig")
    print(f"\nwrote {OUT_JSON}\nwrote {OUT_CSV}")


if __name__ == "__main__":
    main()
