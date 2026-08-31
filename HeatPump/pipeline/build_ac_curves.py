"""
build_ac_curves.py — standard-AC capacity and COP curve (input to the
"potential AC" scenario, see METHODOLOGY.md and the heat pump engine's
existing cooling-load solve in build_city_house_profiles.py).

Same idea as build_unit_curves.py's heat pump curves, mirrored for a
conventional (non-heat-pump) central air conditioner: one representative
size, capacity and COP vs. outdoor temperature, in the same
{T_C[], cap_frac[], COP[]} shape the engine already consumes for heat pumps.

SOURCE
------
Goodman GLXS4B (R-32 split-system AC, up to 15.2 SEER2, 1.5-5 ton),
`data/raw/AC/ss-glxs4b-r32.pdf`, "Performance Data" table (pp. 18-19).
One representative size used: GLXS4BA3610*/CAPTA3626* (3 ton, 36,000 Btu/h
nominal) -- central in Goodman's 1.5-5 ton range and close to the median
real-home design cooling load found in house_profiles_<city>.json (city
averages cluster ~4.4-6.8 kW = 15,000-23,000 Btu/h).

This table (unlike the "Expanded Cooling Data" grid, which cross-tabs
airflow x indoor wet bulb x indoor dry bulb) is already a clean single
curve at one fixed indoor condition (80F DB / 67F WB): Total Btu/h,
Sensible/Latent split and Total Watts vs. outdoor temperature, 75-115F.
COP(T) = Total_Btu/h / (Total_Watts * 3.412) falls straight out --
manufacturer-published, not digitized off a chart.

NORMALIZATION ANCHOR DIFFERS FROM THE HEAT PUMP CURVES ON PURPOSE:
build_unit_curves.py normalizes on rated capacity AT 47F, because that is
the AHRI heating rating point the heat pump certificates use. Cooling's
standard AHRI/SEER rating point is 95F outdoor, not 47F -- so this script's
`cap_frac_of_rated95` is fractional capacity relative to the 95F point, a
different (correct-for-cooling) anchor. Do not compare the two fractions
directly across heating and cooling curves without accounting for this.

EXTRAPOLATION (per Simon 2026-08-31): the published table only covers
75-115F (23.9-46.1C). Held FLAT outside that range in both directions --
below 75F because the cooling load only turns on above a balance point
found to sit ~17-21C (see house_profiles_<city>.json), i.e. within a few
degrees of the table's own low end, so flat-holding is a small, bounded
extrapolation, not a long one; above 115F symmetrically, since Canadian
TMY files essentially never reach it. This is a genuine assumption
(no data says a real unit's curve flattens exactly there) -- flagged in
the output, not hidden.

TVA @ 95F cross-check point (a second Goodman-published rating at the same
95F outdoor temperature but different fixed indoor/airflow condition) is
carried as `cross_check`, mirroring build_unit_curves.py's cross-check
pattern -- not blended into the curve itself.

OUTPUT
------
data/processed/ac_curves.json -- same {T_C[], cap_frac[], COP[]} shape as
hp_curves.json's per-model curves, one model only.
"""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC_PDF = ROOT / "data" / "raw" / "AC" / "ss-glxs4b-r32.pdf"
DEST = ROOT / "data" / "processed" / "ac_curves.json"

BTU_PER_KWH = 3412.14

# Goodman GLXS4BA3610*/CAPTA3626*, "Performance Data" table, p.18.
# Conditions: 80F indoor dry bulb, 67F indoor wet bulb, 1138 CFM.
# (outdoor_F, total_Btuh, sensible_Btuh, latent_Btuh, total_W)
RAW_POINTS_F = [
    (75, 36670, 26080, 10590, 2380),
    (80, 36215, 26205, 10010, 2515),
    (85, 35760, 26330, 9430, 2650),
    (90, 34980, 26085, 8895, 2795),
    (95, 34200, 25840, 8360, 2940),
    (100, 33245, 25475, 7770, 3105),
    (105, 32290, 25110, 7180, 3270),
    (110, 31420, 25215, 6205, 3460),
    (115, 30550, 25320, 5230, 3650),
]
# TVA @ 95F outdoor, 75F indoor DB / 63F indoor WB -- a different fixed
# indoor condition than the main table, used only as a cross-check.
TVA_95F = (95, 32980, 25250, 7730, 2950)

RATED_ANCHOR_F = 95.0  # standard AHRI/SEER cooling rating point
STEP_C = 0.5
GRID_MIN_C = 10.0   # covers the coldest solved balance point (~17-21C) with margin
GRID_MAX_C = 50.0   # covers the hottest design_cooling_db_C (~32C) with margin


def f_to_c(f):
    return (f - 32.0) * 5.0 / 9.0


def interp_flat(x, xs, ys):
    """Linear interpolation between published points; FLAT (clamped) outside
    the measured range, per Simon 2026-08-31 -- not linear extrapolation."""
    if x <= xs[0]:
        return ys[0]
    if x >= xs[-1]:
        return ys[-1]
    for i in range(1, len(xs)):
        if x <= xs[i]:
            x0, x1, y0, y1 = xs[i - 1], xs[i], ys[i - 1], ys[i]
            return y0 + (y1 - y0) * (x - x0) / (x1 - x0)
    return ys[-1]


def main():
    pts = []
    for f, total_btuh, sens_btuh, lat_btuh, watts in RAW_POINTS_F:
        t_c = round(f_to_c(f), 2)
        cap_kw = total_btuh / BTU_PER_KWH
        cop = total_btuh / (watts * BTU_PER_KWH / 1000.0)
        pts.append({
            "T_C": t_c, "T_F": f, "cap_kW": round(cap_kw, 4),
            "COP": round(cop, 3), "sensible_frac": round(sens_btuh / total_btuh, 3),
            "src": f"Performance Data table, {f}F outdoor, 80F/67F indoor",
        })

    xs = [p["T_C"] for p in pts]
    caps = [p["cap_kW"] for p in pts]
    cops = [p["COP"] for p in pts]

    rated_c = f_to_c(RATED_ANCHOR_F)
    rated_cap_kw = interp_flat(rated_c, xs, caps)

    n = int(round((GRID_MAX_C - GRID_MIN_C) / STEP_C))
    grid = [round(GRID_MIN_C + i * STEP_C, 2) for i in range(n + 1)]

    tva_f, tva_total, tva_sens, tva_lat, tva_w = TVA_95F
    tva_cop = tva_total / (tva_w * BTU_PER_KWH / 1000.0)
    cross_check = {
        "label": "TVA @ 95F (different fixed indoor condition: 75F DB/63F WB, "
                 "vs. the main table's 80F DB/67F WB)",
        "T_F": tva_f, "cap_kW": round(tva_total / BTU_PER_KWH, 4),
        "COP": round(tva_cop, 3),
    }

    model = {
        "brand": "Goodman",
        "outdoor_model": "GLXS4BA3610A*",
        "indoor_coil": "CAPTA3626*",
        "label": "Goodman GLXS4B 3-ton (36,000 Btu/h nominal, up to 15.2 SEER2)",
        "refrigerant": "R-32",
        "source_doc": "SS-GLXS4B-R32 (03/26), Performance Data table p.18",
        "nominal_cap_btuh": 36000,
        "rated_anchor_F": RATED_ANCHOR_F,
        "rated_cap_kW": round(rated_cap_kw, 4),
        "datasheet_points": pts,
        "cross_check": cross_check,
        "curve": {
            "T_C": grid,
            "cap_frac_of_rated95": [round(interp_flat(t, xs, caps) / rated_cap_kw, 4) for t in grid],
            "COP": [round(interp_flat(t, xs, cops), 3) for t in grid],
        },
        "source_range_C": [round(xs[0], 2), round(xs[-1], 2)],
        "extrapolation": "flat (clamped) below %.1fC and above %.1fC -- see module docstring" % (xs[0], xs[-1]),
    }

    DEST.parent.mkdir(parents=True, exist_ok=True)
    DEST.write_text(json.dumps({
        "note": ("Standard central-AC capacity/COP curve, one representative "
                 "Goodman GLXS4B size (3 ton). Manufacturer Performance Data "
                 "table, not digitized off a chart. Normalized on rated "
                 "capacity AT 95F (the cooling AHRI anchor), NOT 47F -- do "
                 "not compare cap_frac directly against the heat pump curves' "
                 "47F-anchored fractions. Flat-extrapolated outside the "
                 "published 75-115F range, per Simon 2026-08-31."),
        "step_C": STEP_C,
        "models": {"Goodman_GLXS4BA3610": model},
    }, indent=1), encoding="utf-8")

    print(f"source: {SRC_PDF.relative_to(ROOT.parent)}")
    print(f"{'T_F':>5} {'T_C':>6} {'cap_kW':>8} {'COP':>6}")
    for p in pts:
        print(f"{p['T_F']:>5} {p['T_C']:>6.1f} {p['cap_kW']:>8.3f} {p['COP']:>6.3f}")
    print(f"\nrated (95F anchor): {rated_cap_kw:.3f} kW")
    print(f"cross-check TVA@95F: cap={cross_check['cap_kW']:.3f}kW COP={cross_check['COP']:.3f} "
          f"(vs. main-table 95F: cap={caps[4]:.3f}kW COP={cops[4]:.3f} -- "
          f"different indoor condition, some divergence expected)")
    print(f"\nwrote {DEST}")


if __name__ == "__main__":
    main()
