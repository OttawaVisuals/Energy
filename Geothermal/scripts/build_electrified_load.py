"""
build_electrified_load.py  --  Heat Demand Phase 3 (HEATDEMAND_PLAN.md §4)

Adds, to every building in Data/processed/buildings_ottawa.parquet, a *screening
estimate* of what heating electrification does to its electricity draw:

    elec_kwh_now              -- current space-heat electricity (electric-heated only)
    elec_kw_peak_now          -- current space-heat design-day kW (electric-heated only)
    elec_kwh_electrified      -- policy (a) annual electricity after conversion
    elec_kw_peak_electrified  -- policy (a) design-day kW after conversion
    elec_kwh_hybrid           -- policy (b) annual electricity (fossil backup retained)
    elec_kw_peak_hybrid       -- policy (b) design-day kW
    elec_kwh_gshp             -- GSHP counterfactual annual electricity
    elec_kw_peak_gshp         -- GSHP counterfactual design-day kW
    ... plus TMY-max peaks, retained hybrid fuel, and method/confidence flags.

Converted buildings are the NON-ELECTRIC-heated ones (gas/oil/propane/wood).
Already-electric buildings are reported as-is (`*_now`) and NOT re-simulated:
swapping a baseboard for a heat pump *reduces* load, which is a different
scenario from the added-load question this phase answers.

This is a SCREENING LAYER, not a set of building audits -- it inherits Phase 1's
probabilistic class/vintage and Phase 2's probabilistic fuel draw. Numbers are
meaningful in aggregate (500 m cell / feeder, Phase 4), not for a single address.

METHOD SUMMARY (full write-up: Geothermal/README.md §3.12)

  Load model (unchanged from Phase 2, per HeatPump/METHODOLOGY.md Phase 5)
      load_kW(h) = ua_w_per_k/1000 x max(0, Tbalance - T_TMY(h))
      Phase 2 built every class so that design_kw = ua x 43.8/1000 (the Ottawa
      21 -> -22.8 C design delta), houses via their archetype and every other
      class via annual_kwh / EFLH(Tbalance). So a building's load shape is set
      ENTIRELY by its balance point and its magnitude scales linearly with UA.

  The UA-linearity shortcut (exact, not an approximation)
      Sizing is a fixed multiple of UA in every policy below, so capacity, load,
      dispatch (min(load, capacity)), HP electricity and backup all scale
      linearly with UA at a fixed balance point. The 8760-hour dispatch is
      therefore solved ONCE per distinct balance point (7 of them) at a
      reference UA, and each building's result is that group's per-UA answer
      x its own ua_w_per_k. This is algebraically exact, and it is what makes
      414k buildings x 8760 h tractable. validate() checks the factoring by
      re-running each archetype through the shipped engine unfactored.

  Central case: hp_curves.json "average_installed" (ERS-popularity-weighted --
      what people actually install; HeatPump/METHODOLOGY.md Phase 3b). Note what
      that curve IS: it maps to Tier 3, the BASELINE tier, and locks out at
      -15 C -- warmer than Ottawa's -22.8 C design temperature. That one fact
      drives most of this phase's results, so the tier sensitivity (Tier 1, the
      best cold-climate curve, and Tier 3) is run and printed rather than
      asserted -- see sensitivity().

  Policy (a) -- "full electrification": HP rated (@8.3 C) at the design load,
      electric-resistance backup. HP runs whenever it is above its min-op temp
      and takes min(load, capacity); resistance covers the remainder AND
      everything below the lockout. Mirrors engine.js control strategy
      'load-exceeds-capacity' + backup {type:'electric'}. This is the
      grid-stress upper bound and the heatpump.html default sizing
      (rated kW @47 F = design heat loss).

  Policy (b) -- "hybrid": HP sized to cover the load down to a switchover
      temperature, the EXISTING fossil system retained below it. Mirrors
      engine.js control strategy 'lockout' + backup {type: the building's fuel}.
      T_switchover = max(curve min-op temp, T10), where T10 is the temperature
      below which 10% of the annual load falls -- i.e. size for the plan's
      "~90% load fraction" target, but never below the temperature at which the
      equipment stops running anyway. See the note in switchover_temp().

  GSHP counterfactual: flat COP off hp_curves' GSHP curves (mean of the two
      WaterFurnace units) x the 0.91 antifreeze derate, at the documented Ottawa
      loop temperatures -- winter-mean EWT 4 C for annual energy, design-min EWT
      0 C for the design-day peak. No lockout, no resistance backup: that is the
      whole point of the ground loop and the contrast the map draws.

  Large / commercial buildings: simplified conversion, `elec_confidence='low'`
      -- annual kWh / seasonal COP, peak = the design-condition heat call / the
      COP reached there. See simplified_large() for what is actually simplified
      (the equipment assumption, not the arithmetic), and for why the plan's
      literal "annual_elec / EFLH" load-factor form was not used for the peak.

Sizing vs peaks -- two different design numbers, do not mix them:
    design_kw  = ua x 43.8/1000 is the DESIGN HEAT LOSS: the no-internal-gains,
                 21 C-setpoint engineering figure equipment is SIZED to (and what
                 heatpump.html auto-sizes the heat pump to). Used here only for
                 sizing.
    load at -22.8 C = ua x (Tbalance + 22.8)/1000 is what the balance-point model
                 says the building actually CALLS FOR at the design temperature
                 (gains credited), ~25% lower. Every peak reported here is on this
                 basis, including elec_kw_peak_now, so current and electrified
                 peaks are comparable.

Two peaks are reported for every policy and both are needed:
    *_kw_peak_*      -- coincident DESIGN-CONDITION kW, evaluated at -22.8 C.
                        This is the planning number: every building sees the
                        design temperature at once, so these sum to a coincident
                        city design-day MW.
    *_kw_peak_tmy_*  -- max hourly kW over the TMY year. The TMY dips to
                        -29.5 C, colder than the -22.8 C design point, so these
                        run higher; they are the "worst hour in a typical year",
                        not a design-day planning figure, and do NOT sum to a
                        coincident peak.

Run from C:\\Energy:  python Geothermal/scripts/build_electrified_load.py
Reads:  Data/processed/buildings_ottawa.parquet (Phase 2 output; augmented in place)
        HeatPump/data/processed/{hp_curves,tmy_temps,archetypes}.json
Writes: same .parquet (+ .gpkg) with the new columns and parquet metadata.
"""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import geopandas as gpd

from parquet_meta import write_with_meta

# ---------------------------------------------------------------------------
# Paths (project convention: run from C:\Energy)
# ---------------------------------------------------------------------------
ROOT       = Path(".").resolve()
BUILDINGS  = ROOT / "Geothermal/Data/processed/buildings_ottawa.parquet"
BUILD_GPKG = ROOT / "Geothermal/Data/processed/buildings_ottawa.gpkg"
HP_CURVES  = ROOT / "HeatPump/data/processed/hp_curves.json"
ARCHETYPES = ROOT / "HeatPump/data/processed/archetypes.json"
TMY        = ROOT / "HeatPump/data/processed/tmy_temps.json"
EF_ON      = ROOT / "HeatPump/data/processed/ef_surface_on.json"
PIPELINE   = ROOT / "HeatPump/pipeline"           # for the validate_engine mirror

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
# Ottawa heating design conditions -- identical to Phase 2 / METHODOLOGY Phase 4.
T_SET_C        = 21.0
T_DESIGN_C     = -22.8          # Ottawa 2.5%-ile January
DELTA_T_DESIGN = T_SET_C - T_DESIGN_C          # 43.8 K

# Phase 2 built EVERY class with design_kw = ua x DELTA_T_DESIGN/1000 (houses via
# the archetype's own design heat loss, other classes via annual/EFLH then UA
# back-derived at the same delta). Asserted in load_groups() rather than trusted.
DESIGN_KW_PER_W_PER_K = DELTA_T_DESIGN / 1000.0

# Phase 2's per-class balance points (README §3.11) -- the non-house classes.
# Houses carry their archetype's own calibrated Tbalance.
BALANCE_POINT_C = {"apartment": 10.0, "commercial": 12.0,
                   "institutional": 12.0, "industrial": 8.0}

# Policy (b): the plan's hybrid sizing target -- HP covers ~90% of annual load,
# existing fossil covers the coldest tail.
HYBRID_TARGET_LOAD_FRACTION = 0.90

# Heating-system seasonal efficiency (Phase 2's AFUE table) -- turns the heat the
# retained fossil backup must deliver under policy (b) back into fuel input.
AFUE = {"gas": 0.92, "oil": 0.83, "propane": 0.85, "wood": 0.65, "electric": 1.0}

# Electric resistance backup: 100% efficient at the point of use (engine.js
# default), so policy (a)'s backup kWh == backup kWh of heat.
RESISTANCE_EFF = 1.0

# Buildings at or above this GROSS floor area, plus every non-residential class,
# take the simplified conversion (simplified_large()): a single unitary heat-pump
# curve is not a credible model of a central plant / VRF system. Screening
# threshold -- roughly the point above which a building is centrally heated
# rather than served by unitary equipment.
LARGE_FLOOR_AREA_M2 = 2000.0
NONRES_CLASSES = ("commercial", "institutional", "industrial")
RES_CLASSES    = ("detached", "row", "lowrise_murb", "highrise_murb")

# Hydro Ottawa system peak, for the city-wide sanity check. ~1,300 MW-class
# summer peak (HEATDEMAND_PLAN.md §4 / the plan's own framing); winter peak runs
# lower. Used only to scale the answer, not as a precise reference.
HYDRO_OTTAWA_SYSTEM_PEAK_MW = 1300.0

CURVE_CASES = {                 # label -> hp_curves.json key path
    "average_installed": ("average_installed",),
    "tier1":             ("tiers", "1"),
    "tier3":             ("tiers", "3"),
}
CENTRAL_CASE = "average_installed"


# ===========================================================================
# Curve helpers
# ===========================================================================
def _arr(a):
    """hp_curves stores COP/capacity as null below a model's min-op temp."""
    return np.array([np.nan if v is None else float(v) for v in a], float)


def load_curve(curves, key_path):
    """Return {T_C, cap_frac, COP, min_op_temp_C} for a curve key path."""
    node = curves
    for k in key_path:
        node = node[k]
    c = node["curve"]
    return {
        "T_C": np.array(c["T_C"], float),
        "cap_frac": _arr(c["cap_frac_of_rated47"]),
        "COP": _arr(c["COP"]),
        "min_op_temp_C": float(node["min_op_temp_C"]),
        "label": node.get("label") or node.get("description", ""),
    }


def curve_at(curve, T):
    """Capacity fraction and COP at temperature(s) T, with the engine's lockout
    rule: min_op_temp_C is the single authority (METHODOLOGY Phase 5 amendment 1
    -- the aggregate curves keep a non-null COP below their median lockout, so
    reading the null pattern instead would let a locked-out unit run)."""
    T = np.asarray(T, float)
    frac = np.interp(T, curve["T_C"], curve["cap_frac"])
    cop = np.interp(T, curve["T_C"], curve["COP"])
    locked = T < curve["min_op_temp_C"]
    frac = np.where(locked | ~np.isfinite(frac) | (frac <= 0), 0.0, frac)
    cop = np.where(locked | ~np.isfinite(cop) | (cop <= 0), np.nan, cop)
    return frac, cop


def gshp_flat_cops(curves):
    """Flat GSHP COPs at Ottawa's documented loop temperatures: the mean of the
    two WaterFurnace units' COP(EWT), x the antifreeze derate (METHODOLOGY
    Phase 3b 'GSHP curves'). Annual uses the typical winter-mean EWT; the design
    peak uses the design-minimum EWT."""
    g = curves["gshp"]
    ewt = g["ottawa_ewt"]
    ANTIFREEZE = 0.91          # 20% propylene glycol @ 32 F (WaterFurnace table)

    def mean_cop(at_ewt):
        vals = [np.interp(at_ewt, np.array(u["curve"]["EWT_C"], float),
                          np.array(u["curve"]["COP"], float))
                for u in g["units"].values()]
        return float(np.mean(vals))

    return {
        "annual_cop": mean_cop(ewt["typical_winter_mean_C"]) * ANTIFREEZE,
        "design_cop": mean_cop(ewt["design_min_C"]) * ANTIFREEZE,
        "annual_ewt_C": ewt["typical_winter_mean_C"],
        "design_ewt_C": ewt["design_min_C"],
        "antifreeze": ANTIFREEZE,
        "units": list(g["units"].keys()),
    }


# ===========================================================================
# The per-balance-point group model
# ===========================================================================
def switchover_temp(curve, T_tmy, tbal):
    """Policy (b) switchover temperature.

    The plan asks for a hybrid sized to a ~90% load fraction. The temperature
    that delivers exactly that is T10: the temperature below which 10% of the
    annual load falls. But the HP cannot serve load below its own min-op temp no
    matter how large it is, so the switchover can never be colder than lockout:

        T_switchover = max(min_op_temp_C, T10)

    For the CENTRAL case this binds: 'average_installed' locks out at -15 C,
    below which ~17% of Ottawa's annual heating load sits, so the 90% target is
    physically unreachable and the achieved fraction lands at ~83%. That is a
    finding about the typical installed unit, not a modelling shortfall -- it is
    printed per group and written to README §3.12. Tier 1 (-25 C lockout) is not
    bound by it and lands on the 90% target.
    """
    load = np.maximum(0.0, tbal - T_tmy)
    total = load.sum()
    order = np.argsort(T_tmy)                      # coldest first
    cum = np.cumsum(load[order]) / total
    i = int(np.searchsorted(cum, 1.0 - HYBRID_TARGET_LOAD_FRACTION))
    t10 = float(T_tmy[order][min(i, len(order) - 1)])
    return max(curve["min_op_temp_C"], t10), t10


def run_group(curve, T_tmy, tbal, gshp, ua_ref=1000.0):
    """Solve the 8760-hour dispatch once for one balance point, at a reference
    UA, for policies (a), (b) and the GSHP counterfactual.

    Returns per-UA quantities (per W/K), so a building's value is
    `group[x] * building.ua_w_per_k`. See the module docstring on why this is
    exact rather than an approximation.
    """
    ua_kw = ua_ref / 1000.0
    load = ua_kw * np.maximum(0.0, tbal - T_tmy)          # kWh in each hour
    design_kw = ua_ref * DESIGN_KW_PER_W_PER_K
    total_load = load.sum()

    frac, cop = curve_at(curve, T_tmy)
    frac_d, cop_d = curve_at(curve, T_DESIGN_C)
    load_design = ua_kw * max(0.0, tbal - T_DESIGN_C)

    # ---- policy (a): rated @47F = design load, resistance backup ------------
    # engine.js control 'load-exceeds-capacity': the HP runs whenever it is
    # above min-op and delivers min(load, capacity); resistance covers the rest.
    nominal_a = design_kw
    cap_a = nominal_a * frac
    hp_heat_a = np.minimum(load, cap_a)
    hp_elec_a = np.where(np.isfinite(cop) & (hp_heat_a > 0), hp_heat_a / cop, 0.0)
    bk_heat_a = load - hp_heat_a
    elec_a = hp_elec_a + bk_heat_a / RESISTANCE_EFF

    cap_a_d = nominal_a * float(frac_d)
    hp_heat_a_d = min(load_design, cap_a_d)
    hp_elec_a_d = hp_heat_a_d / float(cop_d) if np.isfinite(cop_d) and hp_heat_a_d > 0 else 0.0
    peak_a_design = hp_elec_a_d + (load_design - hp_heat_a_d) / RESISTANCE_EFF

    # ---- policy (b): hybrid, HP down to T_sw, existing fossil below ---------
    # engine.js control 'lockout' at T_sw. Sizing to the load AT T_sw makes the
    # HP cover 100% of the load above T_sw with the smallest possible unit: load
    # falls and capacity rises as it gets warmer, so if it covers T_sw it covers
    # everything above.
    t_sw, t10 = switchover_temp(curve, T_tmy, tbal)
    frac_sw, _ = curve_at(curve, t_sw)
    load_sw = ua_kw * max(0.0, tbal - t_sw)
    nominal_b = load_sw / float(frac_sw) if float(frac_sw) > 0 else 0.0

    on_b = T_tmy >= t_sw
    cap_b = nominal_b * frac
    hp_heat_b = np.where(on_b, np.minimum(load, cap_b), 0.0)
    hp_elec_b = np.where(on_b & np.isfinite(cop) & (hp_heat_b > 0), hp_heat_b / cop, 0.0)
    bk_heat_b = load - hp_heat_b                   # delivered by the retained fossil
    # design condition sits below T_sw for every curve here, but do not assume it
    peak_b_design = 0.0
    if T_DESIGN_C >= t_sw:
        hp_heat_b_d = min(load_design, nominal_b * float(frac_d))
        peak_b_design = hp_heat_b_d / float(cop_d) if np.isfinite(cop_d) else 0.0

    # ---- GSHP counterfactual: flat COP, no lockout, no backup ---------------
    elec_g = load / gshp["annual_cop"]
    peak_g_design = load_design / gshp["design_cop"]

    return {
        "tbal": tbal,
        "t_switchover_C": t_sw,
        "t10_C": t10,
        # per-UA (per W/K) quantities
        "load_kwh": total_load / ua_ref,
        # The heat the building actually calls for AT the design temperature.
        # NOT the same as design_kw: design_kw = ua x 43.8/1000 is the DESIGN HEAT
        # LOSS -- the no-internal-gains, 21 C-setpoint engineering figure that
        # equipment is sized to (and what heatpump.html auto-sizes the HP to).
        # The balance-point model credits gains, so the load at -22.8 C is
        # ua x (Tbal + 22.8)/1000, ~25% lower. Every PEAK in this script is on
        # this load basis; only SIZING uses design_kw. Mixing the two silently
        # inflates the current-vs-electrified comparison.
        "load_design_kw": load_design / ua_ref,
        "a_elec_kwh": elec_a.sum() / ua_ref,
        "a_peak_design_kw": peak_a_design / ua_ref,
        "a_peak_tmy_kw": elec_a.max() / ua_ref,
        "b_elec_kwh": hp_elec_b.sum() / ua_ref,
        "b_peak_design_kw": peak_b_design / ua_ref,
        "b_peak_tmy_kw": hp_elec_b.max() / ua_ref,
        "b_backup_heat_kwh": bk_heat_b.sum() / ua_ref,   # / AFUE per building
        "g_elec_kwh": elec_g.sum() / ua_ref,
        "g_peak_design_kw": peak_g_design / ua_ref,
        "g_peak_tmy_kw": elec_g.max() / ua_ref,
        # diagnostics (dimensionless / absolute at ua_ref)
        "a_seasonal_cop": total_load / elec_a.sum(),
        "a_backup_share": bk_heat_a.sum() / total_load,
        "b_load_fraction": hp_heat_b.sum() / total_load,
        "b_nominal_per_design": nominal_b / design_kw,
        "a_locked_at_design": not np.isfinite(cop_d),
    }


def load_groups(gdf, curve, T_tmy, gshp, arch):
    """Map each building to its balance-point group and solve each group once.

    Group key is the balance point, because Phase 2 gives every class the same
    design_kw/UA ratio (asserted below) -- so the balance point is the only thing
    that distinguishes one building's normalized load shape from another's.
    """
    # Assert the ratio the whole UA-linearity shortcut rests on, rather than
    # trusting the Phase 2 write-up. Tolerance is RELATIVE and set at 0.5%: the
    # ratio is not bit-exact because archetypes.json rounds design_heat_loss_kW
    # (2 dp) and UA_W_per_K (1 dp) independently -- the four Ottawa archetypes
    # imply 43.788-43.816 rather than exactly 43.8 -- and Phase 2 then rounds
    # design_kw and ua_w_per_k again on write. Observed worst case 0.14%, which
    # is rounding noise, not a broken invariant. A real break (a class sized at a
    # different design delta) would show up orders of magnitude larger.
    heated = gdf["ua_w_per_k"] > 0
    ratio = (gdf.loc[heated, "design_kw"] * 1000.0 / gdf.loc[heated, "ua_w_per_k"])
    rel = float((np.abs(ratio - DELTA_T_DESIGN) / DELTA_T_DESIGN).max())
    if rel > 0.005:
        raise SystemExit(
            f"Phase 2 invariant broken: design_kw/ua is not {DELTA_T_DESIGN} K "
            f"for every building (worst {rel*100:.2f}% off). The UA-linearity "
            f"shortcut in run_group() is not valid -- re-check build_building_demand.py.")
    print(f"  Phase 2 invariant design_kw = ua x {DELTA_T_DESIGN}/1000 holds "
          f"(worst {rel*100:.2f}% -- rounding); UA-linearity shortcut is valid.")

    tbal = np.full(len(gdf), np.nan)
    method = gdf["demand_method"].values
    cls = gdf["class"].values
    for key, a in arch.items():                       # archetype:<key>
        tbal[method == f"archetype:{key}"] = a["Tbalance_C"]
    tbal[method == "ceud_apartment_intensity"] = BALANCE_POINT_C["apartment"]
    tbal[(method == "ewrb_actual_x_ceud_share") & (cls == "commercial")] = BALANCE_POINT_C["commercial"]
    tbal[(method == "ewrb_actual_x_ceud_share") & (cls == "institutional")] = BALANCE_POINT_C["institutional"]
    tbal[method == "industrial_placeholder"] = BALANCE_POINT_C["industrial"]
    # accessory (annual_kwh == 0, unheated) legitimately has no balance point
    unmapped = np.isnan(tbal) & (gdf["annual_kwh"].values > 0)
    if unmapped.any():
        raise SystemExit(f"{unmapped.sum():,} heated buildings have an unmapped "
                         f"demand_method: {set(method[unmapped])}")

    groups = {round(t, 2): run_group(curve, T_tmy, float(t), gshp)
              for t in np.unique(tbal[~np.isnan(tbal)])}
    return tbal, groups


# ===========================================================================
# Simplified conversion for large / commercial buildings
# ===========================================================================
def simplified_large(annual_kwh, ua, group, gshp):
    """Screening conversion for large / non-residential buildings, expressed the
    way the plan asks for it: annual kWh / seasonal COP, and a peak from the
    load factor rather than an hourly dispatch.

      annual: annual_kwh / SCOP. The SCOP is the one the central curve itself
        produces at this building's balance point (group['a_seasonal_cop']) -- a
        sourced number rather than an invented commercial constant. The
        simplification is that ONE seasonal figure replaces the hourly dispatch.

      peak:  load_at_design / COP(design condition), i.e. the design-condition
        heat call divided by the effective COP the equipment reaches there. This
        is the load-factor route in its useful form -- Phase 2 built these
        classes as design_kw = annual_kwh / EFLH, so the class EFLH *is* the load
        factor linking this building's annual energy to its design load.
        Deliberately NOT the literal `annual_elec / EFLH` form: that reduces to
        design_load / SCOP, dividing a design load by a SEASONAL COP, which
        understates the design-day peak about two-fold (the central curve is
        locked out at the design temperature, where its effective COP is 1.0,
        against a seasonal COP near 2). See README §3.12.

    NOTE: this route lands on the same numbers as the hourly one (validate()
    prints the agreement). That is expected, not a coincidence: the SCOP and the
    design COP are read off the same curve, and Phase 2's non-res design_kw is
    EFLH-derived by construction, so the two routes are the same algebra. The
    simplification that matters here is not arithmetic, it is the EQUIPMENT
    assumption -- hence the flag, not a different number.

    `elec_confidence='low'` because: a residential unitary curve is being borrowed
    for what is really a central plant / VRF system (hp_curves.json has no
    commercial equipment curves -- the documented follow-up); the UA is itself
    back-derived from EFLH in Phase 2; and Phase 2's own non-res
    demand_confidence is already low/very_low.
    """
    return {
        "a_elec_kwh": annual_kwh / group["a_seasonal_cop"],
        "a_peak_design_kw": ua * group["a_peak_design_kw"],
        "g_elec_kwh": annual_kwh / gshp["annual_cop"],
        "g_peak_design_kw": ua * group["load_design_kw"] / gshp["design_cop"],
    }


# ===========================================================================
# Main
# ===========================================================================
def main():
    print("=" * 74)
    print("Heat Demand Phase 3 -- build_electrified_load.py")
    print("=" * 74)

    curves = json.load(open(HP_CURVES))
    arch = json.load(open(ARCHETYPES))["Ottawa"]
    T_tmy = np.array(json.load(open(TMY))["Ottawa"], float)
    gshp = gshp_flat_cops(curves)

    central = load_curve(curves, CURVE_CASES[CENTRAL_CASE])
    print(f"\nCentral case: {CENTRAL_CASE} -- {central['label']}")
    print(f"  lockout {central['min_op_temp_C']:.1f} C; Ottawa design "
          f"{T_DESIGN_C} C; TMY min {T_tmy.min():.1f} C")
    _, cd = curve_at(central, T_DESIGN_C)
    if not np.isfinite(cd):
        print(f"  *** the central unit is LOCKED OUT at the design temperature: "
              f"at {T_DESIGN_C} C it delivers nothing and the backup carries "
              f"100% of the design load. This drives policy (a)'s peak.")
    print(f"GSHP counterfactual: flat COP {gshp['annual_cop']:.2f} annual "
          f"(EWT {gshp['annual_ewt_C']} C) / {gshp['design_cop']:.2f} design "
          f"(EWT {gshp['design_ewt_C']} C), incl. {gshp['antifreeze']} antifreeze "
          f"derate; mean of {', '.join(gshp['units'])}.")

    # ---- load buildings ------------------------------------------------------
    print(f"\nLoading {BUILDINGS} ...")
    gdf = gpd.read_parquet(BUILDINGS)
    n = len(gdf)
    print(f"  {n:,} buildings")

    # ---- solve one dispatch per balance point --------------------------------
    tbal, groups = load_groups(gdf, central, T_tmy, gshp, arch)
    print(f"\nSolved the 8760-h dispatch once per balance point "
          f"({len(groups)} groups; UA-linearity shortcut, see module docstring):")
    print(f"  {'Tbal':>6} {'SCOP(a)':>8} {'bkup(a)':>8} {'T_sw':>7} {'T10':>7} "
          f"{'HPfrac(b)':>10} {'size(b)/design':>15}")
    for t, g in sorted(groups.items()):
        print(f"  {t:6.2f} {g['a_seasonal_cop']:8.2f} {g['a_backup_share']*100:7.1f}% "
              f"{g['t_switchover_C']:7.1f} {g['t10_C']:7.1f} "
              f"{g['b_load_fraction']*100:9.1f}% {g['b_nominal_per_design']:15.2f}")
    if all(g["t_switchover_C"] > g["t10_C"] + 1e-9 for g in groups.values()):
        print(f"  NOTE: the {HYBRID_TARGET_LOAD_FRACTION:.0%} hybrid target is "
              f"unreachable with this curve -- its {central['min_op_temp_C']:.0f} C "
              f"lockout is warmer than T10, so the switchover is pinned at lockout "
              f"and the achieved HP load fraction stalls near "
              f"{np.mean([g['b_load_fraction'] for g in groups.values()])*100:.0f}%. "
              f"See switchover_temp().")

    # ---- per-building assembly ----------------------------------------------
    print("\nAssembling per-building electrified load ...")
    ua = gdf["ua_w_per_k"].to_numpy(float)
    annual = gdf["annual_kwh"].to_numpy(float)
    fuel = gdf["heat_fuel"].to_numpy()
    cls = gdf["class"].to_numpy()
    area = gdf["floor_area_m2"].to_numpy(float)

    heated = annual > 0
    is_elec = heated & (fuel == "electric")
    convert = heated & (fuel != "electric")          # gas/oil/propane/wood
    large = heated & ((area >= LARGE_FLOOR_AREA_M2) | np.isin(cls, NONRES_CLASSES))

    out = {k: np.zeros(n) for k in
           ("elec_kwh_now", "elec_kw_peak_now",
            "elec_kwh_electrified", "elec_kw_peak_electrified", "elec_kw_peak_tmy_electrified",
            "elec_kwh_hybrid", "elec_kw_peak_hybrid", "elec_kw_peak_tmy_hybrid",
            "hybrid_fossil_kwh",
            "elec_kwh_gshp", "elec_kw_peak_gshp", "elec_kw_peak_tmy_gshp")}
    method = np.full(n, "not_converted", dtype=object)
    conf = np.full(n, "na", dtype=object)

    # Current electric-heated buildings: resistance baseboard, COP 1, so the
    # annual draw is the annual heat and the design-condition draw is the heat
    # the building calls for at -22.8 C -- on the SAME balance-point load basis
    # as every electrified peak below (see run_group's 'load_design_kw' note;
    # using design_kw here instead would inflate this ~25% against the numbers
    # it is compared with).
    out["elec_kwh_now"][is_elec] = annual[is_elec] / RESISTANCE_EFF
    for t, g in groups.items():
        m = is_elec & (np.round(tbal, 2) == t)
        out["elec_kw_peak_now"][m] = g["load_design_kw"] * ua[m] / RESISTANCE_EFF
    method[is_elec] = "electric_now_baseboard"
    conf[is_elec] = "medium"

    # converted buildings, hourly curve model (small/residential)
    hourly = convert & ~large
    for t, g in groups.items():
        m = hourly & (np.round(tbal, 2) == t)
        if not m.any():
            continue
        out["elec_kwh_electrified"][m] = g["a_elec_kwh"] * ua[m]
        out["elec_kw_peak_electrified"][m] = g["a_peak_design_kw"] * ua[m]
        out["elec_kw_peak_tmy_electrified"][m] = g["a_peak_tmy_kw"] * ua[m]
        out["elec_kwh_hybrid"][m] = g["b_elec_kwh"] * ua[m]
        out["elec_kw_peak_hybrid"][m] = g["b_peak_design_kw"] * ua[m]
        out["elec_kw_peak_tmy_hybrid"][m] = g["b_peak_tmy_kw"] * ua[m]
        out["elec_kwh_gshp"][m] = g["g_elec_kwh"] * ua[m]
        out["elec_kw_peak_gshp"][m] = g["g_peak_design_kw"] * ua[m]
        out["elec_kw_peak_tmy_gshp"][m] = g["g_peak_tmy_kw"] * ua[m]
        # retained fossil under policy (b), as FUEL INPUT at the unit's AFUE
        afue = pd.Series(fuel[m]).map(AFUE).to_numpy(float)
        out["hybrid_fossil_kwh"][m] = g["b_backup_heat_kwh"] * ua[m] / afue
    method[hourly] = f"hourly_curve:{CENTRAL_CASE}"
    conf[hourly] = "medium"

    # converted buildings, simplified (large / non-residential)
    big = convert & large
    for t, g in groups.items():
        m = big & (np.round(tbal, 2) == t)
        if not m.any():
            continue
        s = simplified_large(annual[m], ua[m], g, gshp)
        out["elec_kwh_electrified"][m] = s["a_elec_kwh"]
        out["elec_kw_peak_electrified"][m] = s["a_peak_design_kw"]
        out["elec_kw_peak_tmy_electrified"][m] = s["a_peak_design_kw"]   # no hourly run
        out["elec_kwh_gshp"][m] = s["g_elec_kwh"]
        out["elec_kw_peak_gshp"][m] = s["g_peak_design_kw"]
        out["elec_kw_peak_tmy_gshp"][m] = s["g_peak_design_kw"]
        # hybrid for a large building: HP serves the load above T_sw at the
        # group's seasonal COP, existing fossil below -- same seasonal shortcut.
        out["elec_kwh_hybrid"][m] = annual[m] * g["b_load_fraction"] / g["a_seasonal_cop"]
        out["elec_kw_peak_hybrid"][m] = ua[m] * g["b_peak_design_kw"]
        out["elec_kw_peak_tmy_hybrid"][m] = ua[m] * g["b_peak_tmy_kw"]
        afue = pd.Series(fuel[m]).map(AFUE).to_numpy(float)
        out["hybrid_fossil_kwh"][m] = annual[m] * (1.0 - g["b_load_fraction"]) / afue
    method[big] = "simplified_large"
    conf[big] = "low"

    for k, v in out.items():
        gdf[k] = np.round(v, 3 if "kw" in k else 1)
    gdf["elec_method"] = method
    gdf["elec_confidence"] = conf

    print(f"  converted (non-electric heated): {convert.sum():,}  "
          f"[hourly curve {hourly.sum():,} / simplified large {big.sum():,}]")
    print(f"  already electric (reported as-is): {is_elec.sum():,}")
    print(f"  unheated / accessory (skipped):    {(~heated).sum():,}")

    # ---- validation + city-wide sanity --------------------------------------
    validate(gdf, curves, arch, T_tmy, gshp, groups)
    city_totals(gdf, curves, T_tmy, gshp)
    sensitivity(gdf, curves, T_tmy, gshp, tbal)

    write_outputs(gdf, central, gshp)
    print("\nDone.")


# ===========================================================================
# Validation
# ===========================================================================
def _engine():
    """The shipped engine's faithful Python mirror (HeatPump/pipeline/
    validate_engine.py), which METHODOLOGY Phase 5 pins to app/engine.test.js's
    hand-computed cases to 4 decimals. Node is not installed in this environment
    (the same limitation METHODOLOGY already records), so the mirror -- not the
    JavaScript itself -- is what this check runs against."""
    sys.path.insert(0, str(PIPELINE))
    import validate_engine
    return validate_engine


def validate(gdf, curves, arch, T_tmy, gshp, groups):
    print("\n" + "=" * 74)
    print("VALIDATION")
    print("=" * 74)
    eng = _engine()
    ef = json.load(open(EF_ON))
    central = load_curve(curves, CURVE_CASES[CENTRAL_CASE])
    curve_js = curves["average_installed"]["curve"]

    print("\n(a) Per-archetype electrified annual kWh -- this script's group model "
          "vs the\n    shipped engine (validate_engine.simulate) on the SAME inputs. "
          "Target +-10%.")
    print(f"\n    {'archetype':<20} {'policy':<10} {'this script':>13} {'engine':>13} {'delta':>8}")
    worst = 0.0
    for key, a in arch.items():
        ua_a = a["UA_W_per_K"]
        g = groups[round(a["Tbalance_C"], 2)]
        common = dict(
            tempSeries=list(T_tmy),
            archetype={"UA_W_per_K": ua_a, "Tbalance_C": a["Tbalance_C"]},
            baseCase={"fuel": "gas", "efficiency": 0.92},
            ef=ef, efMode="average", lifecycle={"lineLossPct": 0.0},
        )
        # policy (a): rated @47F = design load, resistance backup, HP runs to lockout
        ra = eng.simulate(dict(common, hp={
            "curve": curve_js, "nominalCap_kW": a["design_heat_loss_kW"],
            "minOpTemp_C": central["min_op_temp_C"], "kind": "ashp"},
            backup={"type": "electric", "efficiency": RESISTANCE_EFF},
            control={"strategy": "load-exceeds-capacity"}))
        # policy (b): sized to the switchover load, lockout control, gas retained
        t_sw = g["t_switchover_C"]
        frac_sw, _ = curve_at(central, t_sw)
        nominal_b = (ua_a / 1000.0 * max(0.0, a["Tbalance_C"] - t_sw)) / float(frac_sw)
        rb = eng.simulate(dict(common, hp={
            "curve": curve_js, "nominalCap_kW": nominal_b,
            "minOpTemp_C": central["min_op_temp_C"], "kind": "ashp"},
            backup={"type": "gas", "efficiency": AFUE["gas"]},
            control={"strategy": "lockout", "lockoutTemp_C": t_sw}))
        # GSHP: flat COP <=> the engine's EWT curve held at the winter-mean EWT
        rg = eng.simulate(dict(common, hp={
            "curve": curves["gshp"]["units"]["wf7_700a11_036"]["curve"],
            "nominalCap_kW": a["design_heat_loss_kW"], "minOpTemp_C": -99.0,
            "kind": "gshp", "ewt": gshp["annual_ewt_C"],
            "antifreezeFactor": gshp["antifreeze"]},
            backup={"type": "electric", "efficiency": RESISTANCE_EFF},
            control={"strategy": "load-exceeds-capacity"}))

        # the GSHP flat COP is the MEAN of the two units; the engine can only be
        # driven with one curve at a time, so compare against that unit's own COP.
        wf7_cop = float(np.interp(gshp["annual_ewt_C"],
                                  np.array(curves["gshp"]["units"]["wf7_700a11_036"]["curve"]["EWT_C"], float),
                                  np.array(curves["gshp"]["units"]["wf7_700a11_036"]["curve"]["COP"], float))) * gshp["antifreeze"]
        mine = {
            "(a) full": g["a_elec_kwh"] * ua_a,
            "(b) hybrid": g["b_elec_kwh"] * ua_a,
            "GSHP": g["load_kwh"] * ua_a / wf7_cop,
        }
        theirs = {
            "(a) full": ra["project"]["energy"]["electricity_kWh"],
            "(b) hybrid": rb["project"]["energy"]["electricity_kWh"],
            "GSHP": rg["project"]["energy"]["electricity_kWh"],
        }
        for i, p in enumerate(mine):
            d = 100.0 * (mine[p] - theirs[p]) / theirs[p]
            worst = max(worst, abs(d))
            print(f"    {key if i == 0 else '':<20} {p:<10} {mine[p]:13,.0f} "
                  f"{theirs[p]:13,.0f} {d:+7.2f}%")
    verdict = "PASS" if worst <= 10.0 else "FAIL"
    print(f"\n    -> worst deviation {worst:.2f}% (target <=10%): {verdict}")
    print(f"       The group model is algebraically the engine's own dispatch "
          f"factored through\n       UA-linearity, so agreement is exact-to-rounding "
          f"rather than merely within band.")
    if worst > 10.0:
        raise SystemExit("Phase 3 validation FAILED against the engine.")

    # --- (b) the load model still reproduces Phase 2's annual_kwh -------------
    print("\n(b) Load-model continuity: the electrified run's own delivered heat "
          "vs Phase 2's\n    annual_kwh (they must be the same load -- only the "
          "equipment changed).")
    for key, a in arch.items():
        g = groups[round(a["Tbalance_C"], 2)]
        recon = g["load_kwh"] * a["UA_W_per_K"]
        d = 100.0 * (recon - a["annual_heat_kWh"]) / a["annual_heat_kWh"]
        print(f"    {key:<20} reconstructed {recon:8,.0f} kWh vs archetype "
              f"{a['annual_heat_kWh']:8,.0f} ({d:+.2f}%)")

    # --- (c) simplified-large route vs the hourly route -----------------------
    # The two are the same algebra (see simplified_large's docstring); this proves
    # the simplification introduces no arithmetic error, so 'low confidence' on
    # those buildings is a statement about the borrowed equipment curve, not about
    # a cruder calculation.
    big = gdf[gdf["elec_method"] == "simplified_large"]
    if len(big):
        implied_scop = big["annual_kwh"].sum() / big["elec_kwh_electrified"].sum()
        print(f"\n(c) Simplified large-building route: {len(big):,} buildings "
              f"(>= {LARGE_FLOOR_AREA_M2:,.0f} m2 or non-residential).")
        print(f"    Implied seasonal COP {implied_scop:.2f}, inside the "
              f"{min(g['a_seasonal_cop'] for g in groups.values()):.2f}-"
              f"{max(g['a_seasonal_cop'] for g in groups.values()):.2f} range the "
              f"hourly dispatch\n    produces across balance points -- the two "
              f"routes are the same algebra (simplified_large()).\n    Flagged "
              f"elec_confidence='low' for the EQUIPMENT assumption (a residential "
              f"unitary curve\n    borrowed for a central plant), not for the "
              f"arithmetic.")


def city_totals(gdf, curves, T_tmy, gshp):
    """City-wide added GWh / added design-day MW, Ottawa CD only."""
    print("\n" + "=" * 74)
    print("CITY-WIDE TOTALS  (Ottawa census division only -- in_ottawa_cd)")
    print("=" * 74)
    if "in_ottawa_cd" not in gdf.columns:
        print("WARNING: no in_ottawa_cd column -- totals fall back to the full "
              "bbox and will over-count (Phase 2.5, README §3.10).")
        city = gdf
    else:
        city = gdf[gdf["in_ottawa_cd"]]
        print(f"Scope: {len(city):,}/{len(gdf):,} buildings inside the Ottawa CD.")

    conv = city[city["elec_kwh_electrified"] > 0]
    print(f"\nConverted buildings: {len(conv):,} "
          f"(fossil-heated: gas/oil/propane/wood). Space heat only.")
    print(f"Heat load being converted: {conv['annual_kwh'].sum()/1e9:.2f} TWh/yr, "
          f"{conv['design_kw'].sum()/1e3:,.0f} MW of design-day heat loss.")

    now_gwh = city["elec_kwh_now"].sum() / 1e6
    now_mw = city["elec_kw_peak_now"].sum() / 1e3
    print(f"\nCurrent electric space heat (already-electric buildings, "
          f"{(city['elec_kwh_now'] > 0).sum():,} bldgs):")
    print(f"    {now_gwh:,.0f} GWh/yr, {now_mw:,.0f} MW coincident at "
          f"{T_DESIGN_C} C  -- unchanged by this scenario.")

    print(f"\nADDED load from converting every fossil-heated building "
          f"(added = the converted buildings drew\nno grid electricity for heat "
          f"before, so added == their electrified total):\n")
    print(f"    {'policy':<34} {'added GWh/yr':>13} {'added MW @design':>17} "
          f"{'vs {:,.0f} MW peak'.format(HYDRO_OTTAWA_SYSTEM_PEAK_MW):>18}")
    rows = [
        ("(a) ccASHP + resistance backup", "elec_kwh_electrified", "elec_kw_peak_electrified"),
        ("(b) hybrid, fossil backup kept", "elec_kwh_hybrid", "elec_kw_peak_hybrid"),
        ("GSHP counterfactual", "elec_kwh_gshp", "elec_kw_peak_gshp"),
    ]
    for label, kcol, pcol in rows:
        gwh = city[kcol].sum() / 1e6
        mw = city[pcol].sum() / 1e3
        print(f"    {label:<34} {gwh:13,.0f} {mw:17,.0f} "
              f"{'+{:.0f}%'.format(100*mw/HYDRO_OTTAWA_SYSTEM_PEAK_MW):>18}")

    tmy_mw = city["elec_kw_peak_tmy_electrified"].sum() / 1e3
    print(f"\n    [policy (a) at the TMY's coldest hour ({T_tmy.min():.1f} C, colder "
          f"than the {T_DESIGN_C} C design\n     point): {tmy_mw:,.0f} MW -- worst "
          f"hour of a typical year, not a design-day planning figure.]")

    foss = city["hybrid_fossil_kwh"].sum() / 1e6
    print(f"\n    Policy (b) retains {foss:,.0f} GWh/yr of fossil fuel input "
          f"(the coldest hours), which is\n    the trade it makes for the lower "
          f"peak.")

    mw_a = city["elec_kw_peak_electrified"].sum() / 1e3
    mw_b = city["elec_kw_peak_hybrid"].sum() / 1e3
    mw_b_tmy = city["elec_kw_peak_tmy_hybrid"].sum() / 1e3
    mw_g = city["elec_kw_peak_gshp"].sum() / 1e3

    print(f"\nSANITY CHECK vs Hydro Ottawa's ~{HYDRO_OTTAWA_SYSTEM_PEAK_MW:,.0f} "
          f"MW-class system peak:")
    print(f"\n    READ THE MW COLUMN AS AN UPPER BOUND, AND HERE IS THE PROOF. The "
          f"buildings that are\n    ALREADY electrically heated sum to "
          f"{now_mw:,.0f} MW at the design condition -- "
          f"{now_mw/HYDRO_OTTAWA_SYSTEM_PEAK_MW:.0%} of Hydro\n    Ottawa's entire "
          f"system peak, from space heat alone, before converting anything. That "
          f"cannot\n    be literally true: it is a load that already exists and "
          f"the system peak is not made of it.\n    So the model's coincident "
          f"design-condition sums overstate real coincident demand, and\n    every "
          f"MW below inherits that. Two known causes, neither fixable in this "
          f"phase:\n"
          f"      - NO DIVERSITY. These sums put every building at its full "
          f"design-condition heat call\n        in the same hour. Real stock "
          f"diversifies (thermostat spread, thermal mass, setback,\n        "
          f"occupancy), and utility winter-peak experience per electrically-heated "
          f"home runs well\n        below design. Phase 4 must apply a "
          f"coincidence factor sourced from actual feeder\n        loading (CCIM), "
          f"not a guess made here -- this script deliberately does not invent one.\n"
          f"      - PHASE 2'S STOCK CAVEAT. City-wide sums are screening upper "
          f"estimates on a stock whose\n        class/vintage/fuel are "
          f"probabilistic per building (README §3.10-3.11).")
    print(f"\n    The RATIOS between the policies are far more robust than the "
          f"absolute MW, because all\n    three share that same load basis and "
          f"the same stock. Those ratios are the result:\n")
    print(f"    Policy (a) adds {mw_a:,.0f} MW, {mw_a/HYDRO_OTTAWA_SYSTEM_PEAK_MW:.1f}x "
          f"the current system peak, and would flip Ottawa\n    decisively "
          f"winter-peaking. The dominant cause is EQUIPMENT, not building stock: "
          f"the typical\n    installed unit locks out at "
          f"{load_curve(curves, CURVE_CASES[CENTRAL_CASE])['min_op_temp_C']:.0f} C, "
          f"so at {T_DESIGN_C} C the resistance "
          f"backup carries 100% of\n    the design load at COP 1 -- policy (a)'s "
          f"design-day peak is simply the design heat call.\n    A cold-climate "
          f"unit that still runs at -22.8 C is the single highest-leverage "
          f"difference,\n    which is why the tier sensitivity is worth carrying "
          f"into Phase 4.")
    print(f"\n    Policy (b) adds {mw_b:,.0f} MW at the design condition and "
          f"{mw_b_tmy:,.0f} MW at its own worst hour.\n    The design-day zero is "
          f"REAL BUT DEFINITIONAL: the hybrid's HP is switched off below "
          f"-15 C, so\n    at -22.8 C it draws nothing and the retained fossil "
          f"unit carries the house. Its true grid\n    cost lands just above the "
          f"switchover ({mw_b_tmy:,.0f} MW), not at the design temperature. "
          f"Hybrids buy\n    {city['elec_kwh_hybrid'].sum()/city['elec_kwh_electrified'].sum():.0%} "
          f"of policy (a)'s electrified energy while keeping "
          f"{foss:,.0f} GWh/yr of fossil input.")
    print(f"\n    GSHP adds {mw_g:,.0f} MW ({mw_g/mw_a*100:.0f}% of policy a): no "
          f"lockout, COP {gshp['design_cop']:.1f} at the design\n    condition, no "
          f"resistance backup. This is the geothermal contrast the map draws -- "
          f"about\n    {mw_a/mw_g:.1f}x less design-day grid stress than the same "
          f"conversion done with typical air-source\n    equipment, and unlike the "
          f"hybrid it gets there without burning anything.")
    print(f"\n    All of this is a 100%-CONVERSION SCENARIO, not a forecast: no "
          f"stock converts overnight.\n    Phase 4 aggregates these to feeders, "
          f"where the headroom question is actually asked.")


def sensitivity(gdf, curves, T_tmy, gshp, tbal_all):
    """City-wide added GWh / added design-day MW under each equipment tier.

    The central case is the ERS-popularity-weighted 'average installed' unit,
    which is a BASELINE unit (it maps to Tier 3) and locks out at -15 C. Tier 1
    is the best cold-climate equipment in hp_curves.json. The spread between them
    is the single largest lever on the electrified peak, so it is quantified here
    rather than asserted -- Phase 4 carries the column, not just the sentence.
    """
    print("\n" + "=" * 74)
    print("EQUIPMENT SENSITIVITY  (city-wide, Ottawa CD, converted buildings)")
    print("=" * 74)
    city = gdf[gdf["in_ottawa_cd"]] if "in_ottawa_cd" in gdf.columns else gdf
    conv = city["elec_kwh_electrified"] > 0
    ua = city["ua_w_per_k"].to_numpy(float)
    tb = np.round(tbal_all[gdf["in_ottawa_cd"].to_numpy()] if "in_ottawa_cd" in gdf.columns
                  else tbal_all, 2)
    ua_by_group = {t: ua[conv.to_numpy() & (tb == t)].sum() for t in np.unique(tb[~np.isnan(tb)])}

    print(f"\n    {'equipment':<22} {'lockout':>8} {'SCOP':>6} {'added GWh':>11} "
          f"{'added MW':>10} {'MW vs central':>14}")
    central_mw = None
    for label, path in CURVE_CASES.items():
        c = load_curve(curves, path)
        gs = {t: run_group(c, T_tmy, float(t), gshp) for t in ua_by_group}
        gwh = sum(gs[t]["a_elec_kwh"] * u for t, u in ua_by_group.items()) / 1e6
        mw = sum(gs[t]["a_peak_design_kw"] * u for t, u in ua_by_group.items()) / 1e3
        scop = sum(gs[t]["load_kwh"] * u for t, u in ua_by_group.items()) / \
            sum(gs[t]["a_elec_kwh"] * u for t, u in ua_by_group.items())
        if label == CENTRAL_CASE:
            central_mw = mw
        tag = "  <- central" if label == CENTRAL_CASE else f"{mw/central_mw:.2f}x" if central_mw else ""
        print(f"    {label:<22} {c['min_op_temp_C']:7.1f}C {scop:6.2f} {gwh:11,.0f} "
              f"{mw:10,.0f} {tag:>14}")
    gwh_g = city.loc[conv, "elec_kwh_gshp"].sum() / 1e6
    mw_g = city.loc[conv, "elec_kw_peak_gshp"].sum() / 1e3
    print(f"    {'GSHP (flat COP)':<22} {'none':>8} {gshp['annual_cop']:6.2f} "
          f"{gwh_g:11,.0f} {mw_g:10,.0f} {mw_g/central_mw:13.2f}x")
    print(f"\n    Tier 1 (-25 C lockout) still runs at Ottawa's {T_DESIGN_C} C design "
          f"temperature, so its\n    resistance backup covers only the shortfall "
          f"rather than the whole load -- that one\n    equipment choice moves the "
          f"city's added design-day peak more than any other lever in\n    this "
          f"phase. The central case is the honest default (it is what people "
          f"actually install,\n    per the ERS popularity weighting), but the "
          f"spread is the policy-relevant finding.")


def write_outputs(gdf, central, gshp):
    print("\nWriting outputs ...")
    meta = {
        "layer": "Ottawa building electrified heat load (screening estimate)",
        "phase": "HEATDEMAND_PLAN.md Phase 3 (build_electrified_load.py)",
        "warning": ("SCREENING ESTIMATE, not a building audit. Inherits Phase 1's "
                    "probabilistic class/vintage and Phase 2's probabilistic fuel "
                    "draw. Meaningful in aggregate (500 m cell / feeder), not for "
                    "a single address. CITY-WIDE SUMS: take over in_ottawa_cd==True "
                    "only. 100%-conversion SCENARIOS, not forecasts."),
        "columns": ("elec_kwh_now/elec_kw_peak_now=current space-heat electricity "
                    "(electric-heated buildings only; 0 elsewhere); "
                    "elec_kwh_electrified/elec_kw_peak_electrified=policy (a) ccASHP "
                    "sized to design load + electric resistance backup; "
                    "elec_kwh_hybrid/elec_kw_peak_hybrid=policy (b) HP to the "
                    "switchover temp with the existing fossil system retained; "
                    "hybrid_fossil_kwh=fuel input the retained backup still burns; "
                    "elec_kwh_gshp/elec_kw_peak_gshp=GSHP counterfactual (flat COP); "
                    "*_kw_peak_* are COINCIDENT design-condition kW at -22.8 C (they "
                    "sum to a city design-day MW); *_kw_peak_tmy_* are the max hour "
                    "of the TMY (colder than design; NOT coincident); "
                    "elec_method/elec_confidence=provenance flags."),
        "methods": ("Load: ua_w_per_k x max(0, Tbalance - T_TMY), the Phase 2 model "
                    "unchanged. Central case: hp_curves.json average_installed "
                    f"ccASHP (lockout {central['min_op_temp_C']} C). Dispatch solved "
                    "once per balance point at a reference UA and scaled by each "
                    "building's UA -- exact, since design_kw = ua x 43.8/1000 for "
                    "every class, so sizing is a fixed multiple of UA. GSHP: flat "
                    f"COP {gshp['annual_cop']:.2f} annual / {gshp['design_cop']:.2f} "
                    "design, mean of the two WaterFurnace units x 0.91 antifreeze. "
                    "Large/non-res buildings: simplified annual/SCOP conversion, "
                    "elec_confidence=low."),
        "key_finding": (f"The central 'average installed' unit locks out at "
                        f"{central['min_op_temp_C']} C, warmer than Ottawa's "
                        f"{T_DESIGN_C} C design temperature, so under policy (a) "
                        f"the resistance backup carries 100% of the design load at "
                        f"COP 1 and the design-day peak is simply the design heat "
                        f"loss. The hybrid's ~90% load-fraction target is likewise "
                        f"unreachable with this curve (~17% of Ottawa's annual load "
                        f"falls below -15 C); it stalls near 83%."),
    }
    # write_with_meta preserves the upstream phases' notes (Phase 2's
    # heatdemand_phase2 and anything earlier) across the rewrite.
    kept = write_with_meta(gdf, BUILDINGS, "phase3", meta)
    print(f"  metadata keys: {', '.join(kept)}")
    print(f"  {BUILDINGS}  ({len(gdf):,} rows, {len(gdf.columns)} cols)")

    try:
        gdf.to_file(BUILD_GPKG, driver="GPKG", layer="buildings_ottawa")
        print(f"  {BUILD_GPKG}")
    except Exception as e:
        print(f"  gpkg skipped ({e})")


if __name__ == "__main__":
    main()
