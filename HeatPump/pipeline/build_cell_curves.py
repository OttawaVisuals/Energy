"""
Heat-pump tier x capacity-band cell curve library (Phase 3c promotion).

WHY THIS EXISTS
----------------
build_tier_curves.py digitized 9 manufacturer datasheets (3 performance tiers
x 3 capacity bands, picked off the tier-selection scatter on 2026-07-29) as a
*working document* -- its own docstring said "if hp_curves.json is rebuilt
from these 9 units, this is the file to promote into a real pipeline script".
This is that promotion: same 9 units, same point-transcription and
interpolation/extrapolation rules, now resampled onto a uniform temperature
grid and written as a real producer script with a JSON output the live engine
(heatpump.html / app/engine.js) can read directly, replacing the old
average_installed/tier1-3 curves in hp_curves.json.

INPUTS
------
  data/interim/datasheet_points_v2.json   GREE 23-pt real datasheet curve,
                                          shared by mid_18-30k and mid_30-42k
  data/interim/hp_units_joined.csv        AHRI-certified rated 47F capacity
                                          (c47) for each cell's unit -- the
                                          normalization denominator, per the
                                          "normalize on the certificate, not
                                          the datasheet" rule (TIER_SPEC.md
                                          Section 5)

OUTPUT
------
  data/processed/hp_cell_curves.json      9 cells, each: curve (T_C /
                                          cap_frac_of_rated47 / cap_kW / COP
                                          on a uniform 0.5C grid),
                                          min_op_temp_C, brand_model, ahri,
                                          w (ERS appearances), rank, source,
                                          flags (the caveats recorded during
                                          transcription -- carried into the
                                          JSON, not left in code comments,
                                          per the data-honesty rail)

METHOD
------
Unchanged from build_tier_curves.py: two independent point series per unit,
capacity(T) and COP(T). Solid/true interpolation between published points of
the same metric. Below the coldest published point down to the unit's
lockout: linear extrapolation for capacity (slope of the coldest published
segment, floored at 0), COP floored at (coldest published COP - 0.3) -- the
same floor rule build_hp_curves.py uses for the shipped curve library. Above
the warmest published point up to WARM_MAX_C: held flat (not a claim about
behaviour there, just keeps the grid populated).

Capacity is normalized on each unit's AHRI-certified rated 47F capacity
(hp_units_joined.csv `c47`), not the datasheet's own 47F figure -- datasheet
47F readings are often a maximum-output figure, not the certified rated
point (TIER_SPEC.md Section 5, trap 1).

Run: python pipeline/build_cell_curves.py
Imported by build_tier_curves.py, which now takes UNITS/build_segments from
here instead of defining them, so tier_scatter.html and the shipped engine
curve provably read the same source.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
OUT_JSON = HERE.parent / "data/processed/hp_cell_curves.json"

GRID = np.round(np.arange(-30.0, 20.0 + 1e-9, 0.5), 2)   # uniform temp grid, C
WARM_MAX_C = 20.0

# Cooling grid: separate from the heating GRID above (different physical range --
# cooling load lives at the WARM end, heating's GRID stops at 20C). Simple flat
# clamp outside each unit's own published range, matching the convention already
# used for ac_curves.json/hp_curves.json's cooling curves (Simon 2026-08-31),
# rather than the heating side's linear-extrapolation-to-lockout rule -- cooling
# units here don't have a published lockout the way heating compressors do.
COOL_GRID = np.round(np.arange(-15.0, 55.0 + 1e-9, 0.5), 2)

# --------------------------------------------------------------------------
# The 9 selected cells. Every point below was read directly off a manufacturer
# document by Simon or Claude during chat on 2026-07-29 -- see `source`.
# T in Celsius throughout; capacity in Btu/h; COP dimensionless.
# --------------------------------------------------------------------------
UNITS = {
    "low_<18k": {
        "brand_model": "Cooper & Hunter CH-12SPH-230VO", "ahri": "205263878", "w": 123,
        "rank": "#7 of 158 (Lennox/Panasonic/Zephyr/Elios/Moovair/Napoleon all lacked datasheets)",
        "source": "C&H submittal, indoor 70F, MAX-speed column of a min/rated/max table",
        "cap_points": [(-15.0, 8611), (-8.33, 11225), (8.33, 13764)],
        "cop_points": [(-15.0, 1.83), (-8.33, 2.28), (8.33, 3.57)],
        "lockout_C": -15.0,
        "flags": ["Lockout not published; using coldest tested point (5F) as the floor -- no "
                  "dotted extrapolation drawn below it.",
                  "COP peaks at the RATED (mid) speed at 17F (2.67), not at max speed (2.28) -- "
                  "the only unit in this set where that's true. Using max-speed points throughout "
                  "for consistency with every other cell."],
    },
    "low_18-30k": {
        "brand_model": "Tosot TUD24W2/D-D(U)", "ahri": "211078853", "w": 122,
        "rank": "#9 of 178 (ACD/GREE/Tosot-18k/Samsung/KingHome all lacked datasheets)",
        "source": "TOSOT_TUD24W2DDU_Specification_Sheet.pdf p.5 EXTENDED RATINGS HEATING "
                  "PERFORMANCE, 70F/59F return-air column, MAX OUTPUT, 17-pt (replaces the "
                  "earlier 3-anchor transcription -- those 3 points are an exact subset of "
                  "this table's 5F/17F/47F rows, same underlying source, now with the full curve)",
        "cap_points": [(-15.0, 13100), (-12.22, 13500), (-9.44, 14000), (-8.33, 14600),
                        (-6.67, 15500), (-3.89, 15800), (-1.11, 16200), (1.67, 16700),
                        (4.44, 19000), (7.22, 21000), (8.33, 23000), (10.0, 24300),
                        (12.78, 25600), (15.56, 27000), (18.33, 27000), (21.11, 27000),
                        (23.89, 27000)],
        "cop_points": [(-15.0, 1.75), (-12.22, 1.89), (-9.44, 2.07), (-8.33, 2.30),
                        (-6.67, 2.54), (-3.89, 2.54), (-1.11, 2.58), (1.67, 2.65),
                        (4.44, 2.83), (7.22, 2.93), (8.33, 3.08), (10.0, 3.22),
                        (12.78, 3.36), (15.56, 3.52), (18.33, 3.72), (21.11, 3.90),
                        (23.89, 4.10)],
        "lockout_C": -15.0,
        "flags": ["Lockout confirmed from spec page: 'Heating Temperature Range 5-75F'."],
        "cool_cap_points": [(-15.00, 24000), (-12.22, 24000), (-9.44, 24000), (-6.67, 24000),
                        (-3.89, 24000), (-1.11, 24000), (1.67, 24000), (4.44, 24000),
                        (7.22, 24000), (10.00, 24000), (12.78, 24000), (15.56, 24000),
                        (18.33, 24500), (21.11, 25000), (23.89, 25000), (26.67, 24000),
                        (29.44, 23000), (32.22, 23000), (35.00, 23000), (37.78, 22000),
                        (40.56, 21000), (43.33, 20100), (46.11, 19100)],
        "cool_cop_points": [(-15.00, 3.974), (-12.22, 3.951), (-9.44, 3.930), (-6.67, 3.907),
                        (-3.89, 3.886), (-1.11, 3.866), (1.67, 3.822), (4.44, 3.781),
                        (7.22, 3.743), (10.00, 3.684), (12.78, 3.625), (15.56, 3.570),
                        (18.33, 3.590), (21.11, 3.611), (23.89, 3.558), (26.67, 3.534),
                        (29.44, 3.274), (32.22, 3.165), (35.00, 3.078), (37.78, 2.840),
                        (40.56, 2.620), (43.33, 2.424), (46.11, 2.230)],
        "cool_source": "TOSOT_TUD24W2DDU_Specification_Sheet.pdf p.4 EXTENDED RATINGS "
                       "COOLING PERFORMANCE, 80F/67F return-air column, MAX OUTPUT, 23-pt "
                       "(COP = EER / 3.412, no COP column published directly)",
        "rated_cap_95f_btuh": 23000.0,
    },
    "low_30-42k": {
        "brand_model": "Tosot TUD36W2/D-D(U)", "ahri": "211078855", "w": 156,
        "rank": "#4 of 173 (KingHome #1 lacked a datasheet)",
        "source": "TOSOT_TUD36.pdf p.4 EXTENDED RATINGS, indoor 70F, MAX OUTPUT column, 17-pt",
        "cap_points": [(-15.0, 18700), (-12.22, 18700), (-9.44, 18800), (-8.33, 19000),
                        (-6.67, 22150), (-3.89, 24180), (-1.11, 26320), (1.67, 28560),
                        (4.44, 30100), (7.22, 31800), (8.33, 34000), (10.0, 34900),
                        (12.78, 35900), (15.56, 37000), (18.33, 37000), (21.11, 37000),
                        (23.89, 37000)],
        "cop_points": [(-15.0, 1.76), (-12.22, 1.85), (-9.44, 1.96), (-8.33, 2.10),
                        (-6.67, 2.06), (-3.89, 2.24), (-1.11, 2.45), (1.67, 2.67),
                        (4.44, 2.73), (7.22, 2.82), (8.33, 2.93), (10.0, 2.99),
                        (12.78, 3.06), (15.56, 3.14), (18.33, 3.30), (21.11, 3.48),
                        (23.89, 3.66)],
        "lockout_C": -15.0,
        "flags": ["Lockout confirmed from spec page: 'Heating Temperature Range 5-75F'. "
                  "COP@5F=1.76 is an exact match to the AHRI record -- best agreement of any unit."],
        "cool_cap_points": [(-15.00, 31700), (-12.22, 31700), (-9.44, 31700), (-6.67, 31700),
                        (-3.89, 31700), (-1.11, 31700), (1.67, 31700), (4.44, 31700),
                        (7.22, 31700), (10.00, 31700), (12.78, 31700), (15.56, 31700),
                        (18.33, 31700), (21.11, 33000), (23.89, 34000), (26.67, 35000),
                        (29.44, 34000), (32.22, 34000), (35.00, 34000), (37.78, 31600),
                        (40.56, 29200), (43.33, 26900), (46.11, 24500)],
        "cool_cop_points": [(-15.00, 3.872), (-12.22, 3.854), (-9.44, 3.839), (-6.67, 3.825),
                        (-3.89, 3.807), (-1.11, 3.792), (1.67, 3.760), (4.44, 3.746),
                        (7.22, 3.731), (10.00, 3.687), (12.78, 3.643), (15.56, 3.614),
                        (18.33, 3.520), (21.11, 3.637), (23.89, 3.719), (26.67, 3.872),
                        (29.44, 3.496), (32.22, 3.242), (35.00, 2.931), (37.78, 2.764),
                        (40.56, 2.594), (43.33, 2.427), (46.11, 2.245)],
        "cool_source": "TOSOT_TUD36.pdf p.4 EXTENDED RATINGS COOLING PERFORMANCE, "
                       "80F/67F return air column, MAX OUTPUT, 23-pt",
        "rated_cap_95f_btuh": 34000.0,
    },
    "mid_<18k": {
        "brand_model": "LG LSU120HSV5", "ahri": "10570123", "w": 4182,
        "rank": "#1 of 344",
        "source": "LG submittal (ajmadison) 4-pt capacity; COP only published at rated 47F "
                  "(backed out from power draw) -- 5F COP is the AHRI record, not an independent "
                  "datasheet measurement",
        "cap_points": [(-19.44, 10360), (-14.44, 11930), (-7.22, 13810), (8.33, 13600)],
        "cop_points": [(-15.0, 1.80), (8.33, 3.83)],
        "lockout_C": -20.0,
        "flags": ["Lockout approximated from LG's stated Heating (WB) -4F operating floor "
                  "(wet-bulb, not dry-bulb -- treated as roughly equivalent here).",
                  "COP curve between 47F and 5F is a straight interpolation between two anchors, "
                  "not measured at the intermediate submittal capacity points (19F/6F/-3F)."],
    },
    "mid_18-30k": {
        "brand_model": "GREE GUD36W/A-D(U) (24k-rated pairing)", "ahri": "206249116", "w": 2253,
        "rank": "#2 of 1,024 (Daikin 3MXL24WMVJU* #1 lacked a datasheet)",
        "source": "GREE FLEXX Ultra18 Extended Ratings (digitized, datasheet_points_v2.json)",
        "flags": ["Same physical outdoor unit (FLEXX36HP230V1AO) as mid/30-42k below -- GREE's own "
                  "extended-ratings doc groups the 24k- and 36k-rated systems under one identical "
                  "table (confirmed against GREE_FLEXX_extended_ratings.pdf, which explicitly pairs "
                  "FLEXX24HP230V1BH and FLEXX36HP230V1AO in the same table). Not a digitization "
                  "error."],
        "reuse_from": "mid_30-42k",
    },
    "mid_30-42k": {
        "brand_model": "GREE GUD36W/A-D(U)", "ahri": "211644151", "w": 11555,
        "rank": "#1 of 916 -- the single most-installed unit in the whole dataset",
        "source": "GREE FLEXX Ultra18 Extended Ratings (digitized, datasheet_points_v2.json), 23-pt",
        "cap_points": None, "cop_points": None,  # filled from datasheet_points_v2.json below
        "lockout_C": -30.0,
        "flags": [],
        "cool_cap_points": [(-15.00, 36000), (-12.22, 36000), (-9.44, 36000), (-6.67, 36000),
                        (-3.89, 36000), (-1.11, 36000), (1.67, 36000), (4.44, 36000),
                        (7.22, 36000), (10.00, 36000), (12.78, 36000), (15.56, 36000),
                        (18.33, 36000), (21.11, 36000), (23.89, 36000), (26.67, 36000),
                        (29.44, 35500), (32.22, 35000), (35.00, 34000), (37.78, 34000),
                        (40.56, 34000), (43.33, 33500), (46.11, 33000), (48.89, 32300),
                        (51.67, 30500), (53.89, 29500)],
        "cool_cop_points": [(-15.00, 4.795), (-12.22, 4.730), (-9.44, 4.669), (-6.67, 4.587),
                        (-3.89, 4.528), (-1.11, 4.452), (1.67, 4.396), (4.44, 4.341),
                        (7.22, 4.270), (10.00, 4.220), (12.78, 4.171), (15.56, 4.121),
                        (18.33, 4.059), (21.11, 3.980), (23.89, 3.907), (26.67, 3.637),
                        (29.44, 3.356), (32.22, 3.157), (35.00, 2.931), (37.78, 2.767),
                        (40.56, 2.623), (43.33, 2.456), (46.11, 2.359), (48.89, 2.339),
                        (51.67, 2.321), (53.89, 2.307)],
        "cool_source": "GREE_FLEXX_extended_ratings.pdf p.4, FLEXX36HP230V1BH/FLEXX36HP230V1AO, "
                       "80F/67F return air column, MAX OUTPUT, 26-pt (widest hot-end range of "
                       "any cell here, to 53.9C/129F)",
        "rated_cap_95f_btuh": 34000.0,
    },
    "high_<18k": {
        "brand_model": "Fujitsu AOUG15LZAH1", "ahri": "206597213", "w": 1918,
        "rank": "#3 of 445 (Panasonic #1 lacked a datasheet; LG #2 excluded -- COP 5.97 data error)",
        "source": "Fujitsu design & technical manual, indoor 21.1C DB, MAX output, 10-pt",
        "cap_points": [(-26.1, 16275), (-20.6, 18630), (-15.0, 20984), (-10.0, 21598),
                        (-5.0, 22246), (0.0, 22860), (5.0, 23475), (8.3, 23884),
                        (10.0, 24873), (15.0, 25897)],
        "cop_points": [(-26.1, 1.66), (-20.6, 1.89), (-15.0, 2.12), (-10.0, 2.28),
                        (-5.0, 2.45), (0.0, 2.64), (5.0, 3.03), (8.3, 3.20),
                        (10.0, 3.56), (15.0, 4.17)],
        "lockout_C": -26.1,
        "flags": ["Lockout not published in the excerpt reviewed; using the coldest tested point "
                  "(-26.1C) as the floor -- no dotted extrapolation below it.",
                  "Cross-check at 5F: curve gives COP 2.12 vs. the AHRI record's 2.34 (9.4% gap) -- "
                  "the widest mismatch of any unit in this set, right at the pipeline's 10% "
                  "cross-check tolerance."],
        "cool_cap_points": [(-10.0, 16105), (-5.0, 15866), (0.0, 15593), (5.0, 15355),
                        (10.0, 15116), (15.0, 14843), (19.4, 17061), (25.0, 16276),
                        (30.6, 15423), (35.0, 14502), (40.0, 12727), (46.1, 11601)],
        "cool_cop_points": [(-10.0, 12.757), (-5.0, 11.625), (0.0, 10.881), (5.0, 10.714),
                        (10.0, 10.302), (15.0, 9.457), (19.4, 6.667), (25.0, 5.679),
                        (30.6, 4.758), (35.0, 4.087), (40.0, 3.657), (46.1, 3.366)],
        "cool_source": "Fujitsu General Design & Technical Manual DR_AS117EF_03, "
                       "5-1 Cooling capacity, ASUG15LZAS, 80F/67F indoor DB/WB column, 12-pt",
        "rated_cap_95f_btuh": 14500.0,
    },
    "high_18-30k": {
        "brand_model": "Moovair DMA24HOS20230E7", "ahri": "212361759", "w": 4206,
        "rank": "#2 of 1,741 (MDV MOD30-24 #1 also has real data -- 2-pt only, swapped out for "
                "this richer 15-pt curve)",
        "source": "Moovair M20 Heat+ Central Moov -30C Performance Data, indoor 70F row, 15-pt",
        "cap_points": [(-30.0, 17380), (-25.0, 19980), (-20.0, 22200), (-17.8, 23200),
                        (-15.0, 24130), (-12.2, 24250), (-8.3, 24390), (-6.7, 25150),
                        (-3.9, 25900), (0.0, 26630), (1.7, 27300), (4.4, 29290),
                        (8.3, 31230), (10.0, 31740), (13.9, 32170)],
        "cop_points": [(-30.0, 1.23), (-25.0, 1.40), (-20.0, 1.63), (-17.8, 1.75),
                        (-15.0, 1.86), (-12.2, 1.98), (-8.3, 2.11), (-6.7, 2.21),
                        (-3.9, 2.31), (0.0, 2.40), (1.7, 2.51), (4.4, 2.82),
                        (8.3, 3.16), (10.0, 3.23), (13.9, 3.32)],
        "lockout_C": -30.0,
        "flags": ["Cross-check at 5F: curve gives COP 1.86 vs. the AHRI record's 1.95 (4.6% gap)."],
    },
    "high_30-42k": {
        "brand_model": "Fujitsu AOUG36LMAS1", "ahri": "205123809", "w": 1795,
        "rank": "#1 of 1,302",
        "source": "Fujitsu design & technical manual, indoor 21.1C DB, MAX output, 9-pt",
        "cap_points": [(-20.6, 28831), (-15.0, 32960), (-10.0, 36747), (-5.0, 40705),
                        (0.0, 44834), (5.0, 49099), (8.3, 51999), (10.0, 53500), (15.0, 58072)],
        "cop_points": [(-20.6, 1.97), (-15.0, 2.03), (-10.0, 2.11), (-5.0, 2.24),
                        (0.0, 2.41), (5.0, 2.64), (8.3, 2.83), (10.0, 2.93), (15.0, 3.32)],
        "lockout_C": -20.6,   # Simon's -20C call, clamped to the coldest tested point (-20.6C)
        "flags": ["Cross-check at 5F: curve gives COP 2.03 vs. the AHRI record's 2.00 (1.3% gap) -- "
                  "the anchor unit for this tier."],
        "cool_cap_points": [(-10.0, 39956), (0.0, 43198), (5.0, 43914), (10.0, 44051),
                        (15.0, 43607), (19.4, 42720), (25.0, 40946), (30.0, 38694),
                        (35.0, 35998), (40.0, 32449), (46.1, 27502)],
        "cool_cop_points": [(-10.0, 6.888), (0.0, 6.362), (5.0, 5.986), (10.0, 5.589),
                        (15.0, 5.153), (19.4, 4.760), (25.0, 4.240), (30.0, 3.767),
                        (35.0, 3.318), (40.0, 2.805), (46.1, 2.214)],
        "cool_source": "Fujitsu General Design & Technical Manual DR_AR048EF_13, "
                       "4-1 Cooling capacity, AMUG36LMAS, 80F/67F indoor DB/WB column, 11-pt",
        "rated_cap_95f_btuh": 36000.0,
    },
}

# GREE's real 23-pt curve, shared by mid_18-30k and mid_30-42k (see reuse_from above).
_ds2 = json.loads((HERE.parent / "data/interim/datasheet_points_v2.json").read_text(encoding="utf-8"))
_gree_pts = _ds2["units"]["211644151"]["points"]
_gree_cap = [(p["T_C"], round(p["cap_kW"] * 3412)) for p in _gree_pts]
_gree_cop = [(p["T_C"], p["COP"]) for p in _gree_pts]
UNITS["mid_30-42k"]["cap_points"] = _gree_cap
UNITS["mid_30-42k"]["cop_points"] = _gree_cop
UNITS["mid_18-30k"]["cap_points"] = _gree_cap
UNITS["mid_18-30k"]["cop_points"] = _gree_cop
UNITS["mid_18-30k"]["lockout_C"] = -30.0
UNITS["mid_18-30k"]["cool_cap_points"] = UNITS["mid_30-42k"]["cool_cap_points"]
UNITS["mid_18-30k"]["cool_cop_points"] = UNITS["mid_30-42k"]["cool_cop_points"]
UNITS["mid_18-30k"]["cool_source"] = UNITS["mid_30-42k"]["cool_source"]
UNITS["mid_18-30k"]["rated_cap_95f_btuh"] = UNITS["mid_30-42k"]["rated_cap_95f_btuh"]

# AHRI-certified rated 47F capacity (Btu/h) per unit, from hp_units_joined.csv
# `c47` -- the certificate, not the datasheet's own 47F reading (TIER_SPEC.md
# Section 5, trap 1: datasheet 47F is often a max-output figure).
RATED_CAP_47F_BTUH = {
    "low_<18k": 12000.0,
    "low_18-30k": 23000.0,
    "low_30-42k": 34000.0,
    "mid_<18k": 13600.0,
    "mid_18-30k": 24000.0,
    "mid_30-42k": 36000.0,
    "high_<18k": 14500.0,
    "high_18-30k": 25000.0,
    "high_30-42k": 36000.0,
}


def _sample_cool_grid(points):
    """Cooling curve on COOL_GRID: true interpolation between published points,
    flat-clamped outside the published range (see COOL_GRID comment above --
    no lockout/extrapolation logic here, unlike the heating side)."""
    pts = sorted(points)
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return [float(np.interp(t, xs, ys)) for t in COOL_GRID]


def build_cool_segments(points, chart_min_C=-15.0, chart_max_C=55.0):
    """(T,V) list -> list of (T0,V0,T1,V1,solid) for a cooling curve: solid
    segments between real published points, flat (non-solid, i.e. flagged as
    extrapolation for dashed rendering) segments from the chart bounds in to
    the first/last real point -- mirrors build_segments()'s solid/dashed
    convention for the heating info-panel chart, but flat rather than sloped
    since cooling has no lockout to extrapolate toward."""
    pts = sorted(points)
    cold_T, cold_V = pts[0]
    warm_T, warm_V = pts[-1]
    segs = []
    if chart_min_C < cold_T - 1e-6:
        segs.append((chart_min_C, cold_V, cold_T, cold_V, False))
    for i in range(len(pts) - 1):
        segs.append((pts[i][0], pts[i][1], pts[i + 1][0], pts[i + 1][1], True))
    if warm_T < chart_max_C - 1e-6:
        segs.append((warm_T, warm_V, chart_max_C, warm_V, False))
    return segs


def build_segments(points, lockout_C, is_cop):
    """(T,V) list -> list of (T0,V0,T1,V1,solid) covering lockout..WARM_MAX_C."""
    pts = sorted(points)
    segs = []
    cold_T, cold_V = pts[0]
    warm_T, warm_V = pts[-1]
    if lockout_C < cold_T - 1e-6:
        if is_cop:
            lock_V = max(cold_V - 0.3, 0.1)
        else:
            if len(pts) >= 2:
                (t0, v0), (t1, v1) = pts[0], pts[1]
                slope = (v1 - v0) / (t1 - t0)
            else:
                slope = 0.0
            lock_V = max(cold_V + slope * (lockout_C - cold_T), 0.0)
        segs.append((lockout_C, lock_V, cold_T, cold_V, False))
    for i in range(len(pts) - 1):
        segs.append((pts[i][0], pts[i][1], pts[i + 1][0], pts[i + 1][1], True))
    if warm_T < WARM_MAX_C - 1e-6:
        segs.append((warm_T, warm_V, WARM_MAX_C, warm_V, False))
    return segs


def _sample_grid(points, lockout_C, is_cop):
    """Evaluate build_segments() piecewise-linear curve on GRID, None below lockout."""
    segs = build_segments(points, lockout_C, is_cop)
    out = []
    for t in GRID:
        if t < lockout_C - 1e-6:
            out.append(None)
            continue
        v = None
        for (t0, v0, t1, v1, _solid) in segs:
            if t0 - 1e-6 <= t <= t1 + 1e-6:
                frac = 0.0 if t1 == t0 else (t - t0) / (t1 - t0)
                v = v0 + frac * (v1 - v0)
                break
        out.append(v)
    return out


def build_cell_curves():
    cells_out = {}
    for cell_id, u in UNITS.items():
        rated47 = RATED_CAP_47F_BTUH[cell_id]
        cap_grid = _sample_grid(u["cap_points"], u["lockout_C"], is_cop=False)
        cop_grid = _sample_grid(u["cop_points"], u["lockout_C"], is_cop=True)
        cells_out[cell_id] = {
            "brand_model": u["brand_model"],
            "ahri": u["ahri"],
            "w": u["w"],
            "rank": u["rank"],
            "source": u["source"],
            "flags": u["flags"],
            "min_op_temp_C": u["lockout_C"],
            "rated_cap_47f_btuh": rated47,
            "curve": {
                "T_C": [float(t) for t in GRID],
                "cap_kW": [None if v is None else round(v / 3412.0, 4) for v in cap_grid],
                "cap_frac_of_rated47": [None if v is None else round(v / rated47, 4) for v in cap_grid],
                "COP": [None if v is None else round(v, 4) for v in cop_grid],
            },
        }
        if u.get("cool_cap_points"):
            rated95 = u["rated_cap_95f_btuh"]
            cool_cap_grid = _sample_cool_grid(u["cool_cap_points"])
            cool_cop_grid = _sample_cool_grid(u["cool_cop_points"])
            cool_xs = [p[0] for p in u["cool_cap_points"]]
            cells_out[cell_id]["cooling"] = {
                "source": u["cool_source"],
                "rated_cap_95f_btuh": rated95,
                "source_range_C": [round(min(cool_xs), 2), round(max(cool_xs), 2)],
                "extrapolation": "flat (clamped) outside the published range",
                "curve": {
                    "T_C": [float(t) for t in COOL_GRID],
                    "cap_kW": [round(v / 3412.0, 4) for v in cool_cap_grid],
                    "cap_frac_of_rated95": [round(v / rated95, 4) for v in cool_cap_grid],
                    "COP": [round(v, 4) for v in cool_cop_grid],
                },
            }
    out = {
        "meta": {
            "phase": "3c cell-curve promotion",
            "generated_from": "pipeline/build_cell_curves.py UNITS (hand-transcribed "
                              "from primary manufacturer datasheets, 2026-07-29 selection "
                              "chat) + data/interim/datasheet_points_v2.json (GREE 23-pt)",
            "temp_grid_C": {"min": float(GRID[0]), "max": float(GRID[-1]), "step": 0.5},
            "capacity_normalization": "fraction of AHRI-certified rated 47F capacity "
                                      "(hp_units_joined.csv c47), not the datasheet's own "
                                      "47F reading -- see TIER_SPEC.md Section 5 trap 1",
            "modelling": "operation = max heating output (full call for heat). Between "
                        "published points: true linear interpolation. Below coldest "
                        "published point to lockout: capacity linear extrapolation "
                        "(floored at 0), COP floored at (coldest published COP - 0.3). "
                        "Above warmest published point: held flat to 20C, not a real claim.",
            "selection": "3 performance tiers (low/mid/high COP@5F x capacity "
                        "maintenance) x 3 capacity bands (<18k/18-30k/30-42k Btu/h), "
                        "picked by eye off the tier-selection scatter -- see "
                        "TIER_SPEC.md and data/interim/tier_scatter.html",
        },
        "cells": cells_out,
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(out, indent=2), encoding="utf-8")
    kb = OUT_JSON.stat().st_size / 1024
    print(f"[out] wrote {OUT_JSON} ({kb:.0f} KB)")
    for cell_id, c in cells_out.items():
        n = sum(1 for v in c["curve"]["cap_kW"] if v is not None)
        print(f"  {cell_id:14s} {c['brand_model']:35s} {n} grid pts, "
              f"lockout {c['min_op_temp_C']}C")
    return out


if __name__ == "__main__":
    build_cell_curves()
