"""
build_hp_curves.py — Phase 3b of the Heat Pump tool.

Turns the digitized spec-sheet / AHRI-certified performance points into the
compact per-model, per-tier and GSHP performance curves the browser engine
consumes.

Inputs
------
- HeatPump/data/interim/neep_points_selected.json
      AHRI-certified max-speed heating points (capacity + COP at 47/17/5 F and
      the Lowest Cataloged Temperature) for the representative models per tier
      and the AHRI-popularity-matched "average installed" units, produced by
      `extract_neep_points.py`. This is the *real certified backbone* of the
      air-source curves.
- Manufacturer extended tables, digitized inline below with citations:
      * Mitsubishi PUZ-HA36NKA submittal — independent published cross-check.
      * WaterFurnace 7 Series 700A11 & 5 Series 500A11 spec catalogs — GSHP
        heating COP vs entering water temperature.

Modelling (see METHODOLOGY.md "Heat pump performance curves (Phase 3b)"):
- per-model capacity(T) and COP(T) piecewise-linear in SI at MAX-compressor
  operation, through the certified points;
- below the coldest published point: capacity extrapolated linearly, COP
  floored at (coldest published COP - 0.3), output ZERO below the model's
  minimum operating temperature (compressor lockout);
- a 7% defrost derate applied to COP across -7..+4 C (with 1 C continuity
  ramps just inside the band) — the NEEP/submittal max-capacity points are
  steady-state, not defrost-integrated, so the derate is appropriate;
- each curve cross-checked against the model's NEEP 47/17/5 F points (and,
  for Mitsubishi, the manufacturer submittal); deviations >10% flagged;
- models aggregated within a tier into one normalized curve (capacity as a
  fraction of rated capacity @47 F) so the UI can scale to any nominal size;
- the "average installed" curve is the popularity-weighted blend of the
  Phase-3a AHRI matches;
- a GSHP curve set: COP vs entering water temperature for two water-to-air
  units, with documented Ottawa-area vertical-loop EWT.

Outputs
-------
- HeatPump/data/processed/hp_curves.json
- HeatPump/data/interim/hp_curve_<tier>.png   (sanity plots, via --plots)

Run: python pipeline/build_hp_curves.py [--plots]
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
HP = ROOT / "HeatPump"
IN_POINTS = HP / "data/interim/neep_points_selected.json"
OUT_JSON = HP / "data/processed/hp_curves.json"
INTERIM = HP / "data/interim"

# --------------------------------------------------------------------------
# Modelling constants
# --------------------------------------------------------------------------
DEFROST_FACTOR = 0.93          # 7% COP derate in the frost-prone band
DEFROST_BAND = (-7.0, 4.0)     # C, per PLAN.md §3 / ROADMAP item 3b
DEFROST_RAMP = 1.0             # C, continuity ramp just inside each band edge
COP_FLOOR_DROP = 0.30          # COP floor below coldest point = coldest - 0.3
GRID = np.round(np.arange(-30.0, 15.0 + 1e-9, 0.5), 2)   # common temp grid, C
CROSS_CHECK_TOL = 0.10         # flag curve-vs-reference deviations > 10%

# NEEP certified check temperatures (max-speed) in C: 47 / 17 / 5 F.
CHECK_T = {"47F": 8.33, "17F": -8.33, "5F": -15.0}

# --------------------------------------------------------------------------
# Manufacturer extended / cross-check data (digitized, with citations).
# --------------------------------------------------------------------------
# Mitsubishi PUZ-HA36NKA + PVA-A36AA7 submittal, Form SB_PVA-A36AA7_PUZ-
# HA36NKA_202401 (mitsubishitechinfo.ca), "Performance" table p.2. Max-capacity
# heating COPs — an INDEPENDENT published cross-check of the NEEP backbone.
MITSU_SUBMITTAL = {
    "outdoor_model": "PUZ-HA36NKA",
    "doc": "Mitsubishi Electric Submittal SB_PVA-A36AA7_PUZ-HA36NKA_202401, p.2",
    # (T_C, max capacity BTU/h, max-capacity COP)
    "points": [(8.33, 40000, None), (-8.33, 38000, 2.27),
               (-15.0, 38000, 2.17), (-25.0, 30400, 1.50)],
    "defrost_inclusive": False,   # steady-state max-capacity ratings
}

# WaterFurnace geothermal (water-to-air) — full-load HEATING COP vs entering
# water temperature at EAT 70 F, highest cataloged loop flow, 0% antifreeze.
# Source: WaterFurnace Specification Catalogs, "Performance Data" tables.
GSHP_UNITS = {
    "wf7_700a11_036": {
        "brand": "WaterFurnace", "model": "7 Series 700A11 (036)",
        "type": "Variable-speed water-to-air", "refrigerant": "R-410A",
        "doc": "WaterFurnace 7 Series 700A11 Spec Catalog SC2700AN, "
               "'036 - 100% Full Load' p.34 (11.5 gpm / 1500 cfm)",
        "rated_cap_ewt0_kW": 37.4 * 0.29307107,   # HC MBtu/h @ 30 F -> kW
        # (EWT_C, heating COP)  [EWT F: 20/30/40/50/60/70]
        "cop_vs_ewt": [(-6.7, 3.32), (-1.1, 3.79), (4.4, 4.46),
                       (10.0, 4.83), (15.6, 5.36), (21.1, 5.84)],
        # normalized heating capacity fraction (of HC @ 30 F/-1.1 C)
        "capfrac_vs_ewt": [(-6.7, 32.6 / 37.4), (-1.1, 1.00), (4.4, 43.3 / 37.4),
                           (10.0, 48.5 / 37.4), (15.6, 54.3 / 37.4),
                           (21.1, 60.0 / 37.4)],
        "iso13256_glhp_heating_cop_0C": None,   # see note; 7 Series ~ up to 5.0
    },
    "wf5_500a11_nd038": {
        "brand": "WaterFurnace", "model": "5 Series 500A11 (ND038, dual-cap)",
        "type": "Two-stage water-to-air", "refrigerant": "R-454B",
        "doc": "WaterFurnace 5 Series 500A11 Spec Catalog SC2500AN, "
               "'ND038 High Speed' p.62 (9.0 gpm / 1250 cfm); ISO 13256-1 p.6",
        "rated_cap_ewt0_kW": 29.6 * 0.29307107,
        "cop_vs_ewt": [(-6.7, 3.34), (-1.1, 3.80), (4.4, 4.21),
                       (10.0, 4.59), (15.6, 4.88), (21.1, 5.14)],
        "capfrac_vs_ewt": [(-6.7, 26.0 / 29.6), (-1.1, 1.00), (4.4, 34.4 / 29.6),
                           (10.0, 38.6 / 29.6), (15.6, 41.8 / 29.6),
                           (21.1, 47.0 / 29.6)],
        "iso13256_glhp_heating_cop_0C": 4.2,   # 038 Full, GLHP 32 F brine, cat. p.6
    },
}

# Ottawa-area vertical closed-loop entering-water-temperature model.
# Undisturbed ground ~8-9 C (PLAN.md §4). A well-sized vertical borefield draws
# the loop down through the heating season; representative EWT band below.
OTTAWA_EWT = {
    "undisturbed_ground_C": 8.5,
    "design_min_C": 0.0,       # ~32 F at the coldest design condition
    "typical_winter_mean_C": 4.0,
    "shoulder_C": 7.0,
    "note": "Vertical closed-loop with antifreeze; catalog COP is 0% antifreeze "
            "-- apply ~0.91 (20% propylene glycol @ 32 F) for a conservative "
            "design-condition estimate (WaterFurnace antifreeze table).",
}


# --------------------------------------------------------------------------
# Curve construction
# --------------------------------------------------------------------------
def defrost_factor(T):
    """Continuous multiplicative COP factor: DEFROST_FACTOR across the band,
    1.0 outside, linear ramps of DEFROST_RAMP just inside each band edge so
    the resulting curve stays continuous."""
    lo, hi = DEFROST_BAND
    T = np.asarray(T, dtype=float)
    f = np.ones_like(T)
    inner_lo, inner_hi = lo + DEFROST_RAMP, hi - DEFROST_RAMP
    core = (T >= inner_lo) & (T <= inner_hi)
    f[core] = DEFROST_FACTOR
    lramp = (T >= lo) & (T < inner_lo)
    f[lramp] = 1.0 + (DEFROST_FACTOR - 1.0) * (T[lramp] - lo) / DEFROST_RAMP
    rramp = (T > inner_hi) & (T <= hi)
    f[rramp] = DEFROST_FACTOR + (1.0 - DEFROST_FACTOR) * (T[rramp] - inner_hi) / DEFROST_RAMP
    return f


def _interp_extrap(T, xs, ys, slope_lo, slope_hi):
    """Piecewise-linear interpolation with linear extrapolation beyond the
    endpoints using the given end-segment slopes."""
    T = np.asarray(T, dtype=float)
    out = np.interp(T, xs, ys)   # clamps outside; fix the tails below
    below = T < xs[0]
    out[below] = ys[0] + slope_lo * (T[below] - xs[0])
    above = T > xs[-1]
    out[above] = ys[-1] + slope_hi * (T[above] - xs[-1])
    return out


def build_model_curve(points, rated_cap_47_kW, min_op_temp_C,
                      apply_defrost=True):
    """Evaluate a model's capacity(T) [kW and fraction-of-rated@47] and COP(T)
    on GRID, with cold-end extrapolation, COP floor and lockout below min-op.
    `points` = list of dicts {T_C, cap_kW, COP} (certified max-speed points)."""
    pts = sorted(points, key=lambda p: p["T_C"])
    xs = np.array([p["T_C"] for p in pts])
    cap = np.array([p["cap_kW"] for p in pts])
    cop = np.array([p["COP"] for p in pts])

    # end-segment slopes for linear extrapolation
    cap_slope_lo = (cap[1] - cap[0]) / (xs[1] - xs[0])
    cap_slope_hi = (cap[-1] - cap[-2]) / (xs[-1] - xs[-2])
    cop_slope_hi = (cop[-1] - cop[-2]) / (xs[-1] - xs[-2])

    cap_kw = _interp_extrap(GRID, xs, cap, cap_slope_lo, cap_slope_hi)
    # COP: interpolate; ABOVE warmest extrapolate on slope; BELOW coldest floor
    cop_curve = _interp_extrap(GRID, xs, cop, 0.0, cop_slope_hi)
    cold_floor = cop[0] - COP_FLOOR_DROP
    below = GRID < xs[0]
    cop_curve[below] = np.maximum(cold_floor, cop_curve[below])
    cop_curve = np.maximum(cop_curve, cold_floor)   # never below the floor

    if apply_defrost:
        cop_curve = cop_curve * defrost_factor(GRID)

    # lockout: zero output (and undefined COP) below the min operating temp
    locked = GRID < (min_op_temp_C - 1e-9)
    cap_kw = np.where(locked, 0.0, np.maximum(cap_kw, 0.0))
    cop_out = np.where(locked, np.nan, cop_curve)

    cap_frac = cap_kw / rated_cap_47_kW
    return cap_kw, cap_frac, cop_out


def curve_value(T_C, grid_curve):
    """Sample a GRID-based curve array at an arbitrary temperature."""
    return float(np.interp(T_C, GRID, np.nan_to_num(grid_curve, nan=0.0)))


def pav_isotonic(y):
    """Pool-Adjacent-Violators: nearest non-decreasing (in index) fit, ignoring
    NaNs. Used only to smooth the AGGREGATE tier/average capacity curves, whose
    small residual dips come from AHRI 17 F rating conventions, not physics."""
    y = np.asarray(y, dtype=float)
    out = y.copy()
    idx = np.where(~np.isnan(y))[0]
    if len(idx) == 0:
        return out
    v = y[idx].astype(float)
    w = np.ones_like(v)
    # PAVA
    vals = list(v)
    wts = list(w)
    lvls = [[x] for x in range(len(v))]
    i = 0
    while i < len(vals) - 1:
        if vals[i] > vals[i + 1] + 1e-12:
            nv = (vals[i] * wts[i] + vals[i + 1] * wts[i + 1]) / (wts[i] + wts[i + 1])
            vals[i] = nv
            wts[i] += wts[i + 1]
            lvls[i] += lvls[i + 1]
            del vals[i + 1]; del wts[i + 1]; del lvls[i + 1]
            if i > 0:
                i -= 1
        else:
            i += 1
    fitted = np.empty(len(v))
    for val, block in zip(vals, lvls):
        for b in block:
            fitted[b] = val
    out[idx] = fitted
    return out


# --------------------------------------------------------------------------
# Aggregation
# --------------------------------------------------------------------------
def aggregate(members, weights=None, isotonic_cap=True):
    """Popularity/equal-weighted mean of member normalized curves on GRID.
    Members with a curve below their lockout contribute NaN there (excluded
    from the mean). Returns (cap_frac, COP) grid arrays."""
    cap = np.vstack([m["cap_frac"] for m in members])
    cop = np.vstack([np.where(np.isnan(m["COP"]), np.nan, m["COP"]) for m in members])
    cap = np.where(cap <= 0.0, np.nan, cap)   # exclude locked-out members
    if weights is None:
        weights = np.ones(len(members))
    weights = np.asarray(weights, dtype=float)

    def wmean(stack):
        out = np.full(stack.shape[1], np.nan)
        for j in range(stack.shape[1]):
            col = stack[:, j]
            ok = ~np.isnan(col)
            if ok.any():
                out[j] = np.average(col[ok], weights=weights[ok])
        return out

    cap_mean = wmean(cap)
    cop_mean = wmean(cop)
    if isotonic_cap:
        cap_mean = pav_isotonic(cap_mean)
        cop_mean = pav_isotonic(cop_mean)
    return cap_mean, cop_mean


# --------------------------------------------------------------------------
# Cross-check
# --------------------------------------------------------------------------
def neep_cross_check(model_id, points, cop_curve_no_defrost):
    """Compare the (defrost-free) curve COP at 47/17/5 F to the certified NEEP
    points it was built from -- should be ~0 by construction; report anyway --
    and, where available, to an independent manufacturer submittal."""
    by_t = {round(p["T_C"], 1): p for p in points}
    flags = []
    checks = []
    for lbl, T in CHECK_T.items():
        near = by_t.get(round(T, 1))
        if near is None:
            continue
        curve = curve_value(T, cop_curve_no_defrost)
        ref = near["COP"]
        dev = (curve - ref) / ref
        checks.append({"T": lbl, "ref_COP": round(ref, 3),
                       "curve_COP": round(curve, 3), "dev": round(dev, 3)})
        if abs(dev) > CROSS_CHECK_TOL:
            flags.append(f"NEEP {lbl}: {dev:+.0%}")
    return checks, flags


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------
def main(make_plots=False):
    data = json.loads(IN_POINTS.read_text(encoding="utf-8"))
    TIER_LABELS = {1: "Tier 1 - cold-climate premium",
                   2: "Tier 2 - mid-market cold-climate",
                   3: "Tier 3 - baseline"}

    models = {}          # model_id -> record (with grid arrays, temporarily)
    tier_members = {1: [], 2: [], 3: []}
    all_flags = []

    def model_id(d):
        return (d["brand"].strip().replace(" ", "_") + "__" +
                d["outdoor_model"]).replace("/", "-")

    # ---- per-model curves (tier representatives) ----
    for tier_str, mlist in data["tiers"].items():
        tier = int(tier_str)
        for d in mlist:
            mid = model_id(d)
            cap_kw, cap_frac, cop = build_model_curve(
                d["points"], d["rated_cap_47_kW"], d["min_op_temp_C"])
            _, _, cop_nod = build_model_curve(
                d["points"], d["rated_cap_47_kW"], d["min_op_temp_C"],
                apply_defrost=False)
            checks, flags = neep_cross_check(mid, d["points"], cop_nod)

            # Mitsubishi independent submittal cross-check
            mfr_check = None
            if d["outdoor_model"] == MITSU_SUBMITTAL["outdoor_model"]:
                mfr_check = {"doc": MITSU_SUBMITTAL["doc"], "points": []}
                for (T, capbtu, mcop) in MITSU_SUBMITTAL["points"]:
                    if mcop is None:
                        continue
                    curve = curve_value(T, cop_nod)
                    dev = (curve - mcop) / mcop
                    entry = {"T_C": T, "submittal_COP": mcop,
                             "curve_COP": round(curve, 3), "dev": round(dev, 3)}
                    mfr_check["points"].append(entry)
                    if abs(dev) > CROSS_CHECK_TOL:
                        all_flags.append(
                            f"{mid}: submittal {T}C COP {mcop} vs curve "
                            f"{curve:.2f} ({dev:+.0%})")
            all_flags += [f"{mid}: {f}" for f in flags]

            rec = {
                "tier": tier, "brand": d["brand"], "brand_owner": d["brand_owner"],
                "outdoor_model": d["outdoor_model"], "label": d["label"],
                "refrigerant": d["refrigerant"], "n_neep_combos": d["n_combos"],
                "rated_cap_47_kW": round(d["rated_cap_47_kW"], 3),
                "min_op_temp_C": d["min_op_temp_C"], "has_lct": d["has_lct"],
                "defrost_inclusive": False,
                "neep_points": d["points"],
                "neep_cross_check": checks,
                "manufacturer_cross_check": mfr_check,
                # grid arrays (kept for aggregation / plotting; trimmed on output)
                "cap_kw": cap_kw, "cap_frac": cap_frac, "COP": cop,
            }
            models[mid] = rec
            tier_members[tier].append(rec)

    # ---- average installed: popularity-weighted blend of AHRI matches ----
    avg_members, avg_weights, avg_comp = [], [], []
    for d in data["ahri_matched"]:
        cap_kw, cap_frac, cop = build_model_curve(
            d["points"], d["rated_cap_47_kW"], d["min_op_temp_C"])
        avg_members.append({"cap_frac": cap_frac, "COP": cop})
        avg_weights.append(d["weight"])
        avg_comp.append({"outdoor_model": d["outdoor_model"],
                         "brand": d["brand"], "weight": d["weight"],
                         "min_op_temp_C": d["min_op_temp_C"]})
    avg_cap, avg_cop = aggregate(avg_members, avg_weights)
    # representative lockout for the blend = popularity-weighted median min-op
    mo = sorted(((c["min_op_temp_C"], c["weight"]) for c in avg_comp))
    tot = sum(w for _, w in mo); acc = 0; avg_minop = mo[-1][0]
    for t, w in mo:
        acc += w
        if acc >= tot / 2:
            avg_minop = t; break

    # ---- tier aggregate curves ----
    tiers_out = {}
    for tier, mem in tier_members.items():
        cap_mean, cop_mean = aggregate(mem)
        minops = sorted(m["min_op_temp_C"] for m in mem)
        tier_minop = minops[len(minops) // 2]   # median member lockout
        tiers_out[str(tier)] = {
            "label": TIER_LABELS[tier],
            "members": [m["outdoor_model"] for m in mem],
            "min_op_temp_C": tier_minop,
            "curve": {"T_C": GRID.tolist(),
                      "cap_frac_of_rated47": _round_nan(cap_mean),
                      "COP": _round_nan(cop_mean)},
        }

    # ---- GSHP curves ----
    gshp_out = {"ottawa_ewt": OTTAWA_EWT, "units": {}}
    for uid, u in GSHP_UNITS.items():
        ewt = np.array([e for e, _ in u["cop_vs_ewt"]])
        cop = np.array([c for _, c in u["cop_vs_ewt"]])
        capf = np.array([c for _, c in u["capfrac_vs_ewt"]])
        ewt_grid = np.round(np.arange(-7.0, 21.0 + 1e-9, 0.5), 2)
        gshp_out["units"][uid] = {
            "brand": u["brand"], "model": u["model"], "type": u["type"],
            "refrigerant": u["refrigerant"], "doc": u["doc"],
            "rated_cap_ewt0_kW": round(u["rated_cap_ewt0_kW"], 3),
            "iso13256_glhp_heating_cop_0C": u["iso13256_glhp_heating_cop_0C"],
            "raw_points": [{"EWT_C": e, "COP": c, "cap_frac": cf}
                           for (e, c), (_, cf) in zip(u["cop_vs_ewt"],
                                                      u["capfrac_vs_ewt"])],
            "curve": {"EWT_C": ewt_grid.tolist(),
                      "COP": [round(float(v), 4) for v in np.interp(ewt_grid, ewt, cop)],
                      "cap_frac_of_ewt0": [round(float(v), 4)
                                           for v in np.interp(ewt_grid, ewt, capf)]},
        }

    # ---- assemble output ----
    out = {
        "meta": {
            "phase": "3b", "generated_from": IN_POINTS.name,
            "temp_grid_C": {"min": float(GRID[0]), "max": float(GRID[-1]),
                            "step": 0.5},
            "modelling": {
                "operation": "max compressor speed",
                "capacity_units": "fraction of rated capacity @47F (per-model "
                                  "curves also give absolute kW)",
                "defrost_derate": DEFROST_FACTOR,
                "defrost_band_C": DEFROST_BAND,
                "defrost_ramp_C": DEFROST_RAMP,
                "defrost_inclusive_ratings": False,
                "cop_floor_drop": COP_FLOOR_DROP,
                "cold_extrapolation": "linear capacity below coldest point; COP "
                                      "floored; zero output below min-op temp",
                "cross_check_tolerance": CROSS_CHECK_TOL,
            },
            "sources": {
                "ashp_backbone": "NEEP ccASHP HP Report, AHRI-certified max-speed "
                                 "heating points 47/17/5F + LCT",
                "mitsubishi_submittal": MITSU_SUBMITTAL["doc"],
                "gshp": [u["doc"] for u in GSHP_UNITS.values()],
            },
            "cross_check_flags": all_flags,
        },
        "models": {mid: _trim_model(r) for mid, r in models.items()},
        "tiers": tiers_out,
        "average_installed": {
            "description": "Popularity-weighted blend of the top-10 AHRI numbers "
                           "in ERS retrofit data matched to NEEP (Phase 3a).",
            "min_op_temp_C": avg_minop,
            "composition": avg_comp,
            "weight_total": int(sum(avg_weights)),
            "curve": {"T_C": GRID.tolist(),
                      "cap_frac_of_rated47": _round_nan(avg_cap),
                      "COP": _round_nan(avg_cop)},
        },
        "gshp": gshp_out,
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(out, indent=2), encoding="utf-8")
    kb = OUT_JSON.stat().st_size / 1024
    print(f"[out] wrote {OUT_JSON} ({kb:.0f} KB)")
    print(f"[cross-check] {len(all_flags)} deviation(s) > "
          f"{CROSS_CHECK_TOL:.0%} flagged:")
    for f in all_flags:
        print("   !", f)

    if make_plots:
        plot_tiers(models, tier_members, tiers_out, avg_cap, avg_cop)
    return out


def _round_nan(a):
    return [None if np.isnan(v) else round(float(v), 4) for v in a]


def _trim_model(r):
    """Convert a per-model record's grid arrays to JSON, dropping raw np arrays."""
    out = {k: v for k, v in r.items() if k not in ("cap_kw", "cap_frac", "COP")}
    out["curve"] = {
        "T_C": GRID.tolist(),
        "cap_kW": _round_nan(r["cap_kw"]),
        "cap_frac_of_rated47": _round_nan(r["cap_frac"]),
        "COP": _round_nan(r["COP"]),
    }
    return out


def plot_tiers(models, tier_members, tiers_out, avg_cap, avg_cop):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    def check_pts(rec):
        return [(p["T_C"], p["cap_kW"] / rec["rated_cap_47_kW"], p["COP"])
                for p in rec["neep_points"]]

    for tier, mem in tier_members.items():
        fig, (axc, axp) = plt.subplots(1, 2, figsize=(12, 4.6))
        for m in mem:
            axc.plot(GRID, m["cap_frac"], lw=1.6, label=m["outdoor_model"])
            axp.plot(GRID, m["COP"], lw=1.6, label=m["outdoor_model"])
            for (T, cf, cp) in check_pts(m):
                axc.scatter([T], [cf], s=28, zorder=5, edgecolor="k", linewidths=.4)
                axp.scatter([T], [cp], s=28, zorder=5, edgecolor="k", linewidths=.4)
        t = tiers_out[str(tier)]["curve"]
        axc.plot(GRID, [np.nan if v is None else v for v in t["cap_frac_of_rated47"]],
                 "k--", lw=2.4, label="TIER curve")
        axp.plot(GRID, [np.nan if v is None else v for v in t["COP"]],
                 "k--", lw=2.4, label="TIER curve")
        axc.set(title=f"{tiers_out[str(tier)]['label']}\ncapacity (fraction of "
                "rated @47F)", xlabel="Outdoor temp (C)", ylabel="cap / rated@47F")
        axp.set(title="COP (max speed, defrost-derated)", xlabel="Outdoor temp (C)",
                ylabel="COP")
        for ax in (axc, axp):
            ax.axvspan(*DEFROST_BAND, color="tab:blue", alpha=0.06)
            ax.grid(alpha=0.3); ax.legend(fontsize=7)
        fig.tight_layout()
        p = INTERIM / f"hp_curve_tier{tier}.png"
        fig.savefig(p, dpi=110); plt.close(fig)
        print(f"[plot] wrote {p}")

    # average installed + GSHP overview
    fig, (axc, axp) = plt.subplots(1, 2, figsize=(12, 4.6))
    axc.plot(GRID, [np.nan if v is None else v for v in _round_nan(avg_cap)],
             "purple", lw=2.4)
    axp.plot(GRID, [np.nan if v is None else v for v in _round_nan(avg_cop)],
             "purple", lw=2.4, label="Average installed")
    axc.set(title="Average installed - capacity", xlabel="Outdoor temp (C)",
            ylabel="cap / rated@47F"); axc.grid(alpha=.3)
    axp.set(title="Average installed - COP", xlabel="Outdoor temp (C)",
            ylabel="COP"); axp.grid(alpha=.3); axp.legend(fontsize=8)
    for ax in (axc, axp):
        ax.axvspan(*DEFROST_BAND, color="tab:blue", alpha=0.06)
    fig.tight_layout()
    p = INTERIM / "hp_curve_average_installed.png"
    fig.savefig(p, dpi=110); plt.close(fig)
    print(f"[plot] wrote {p}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--plots", action="store_true", help="write sanity plots")
    args = ap.parse_args()
    main(make_plots=args.plots)
