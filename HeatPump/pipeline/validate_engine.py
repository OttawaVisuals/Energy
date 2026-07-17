"""
validate_engine.py -- Phase 5 cross-language check for app/engine.js.

A faithful Python port of engine.simulate() (same formulas, same constants),
run over the SAME hand-computed test cases as app/engine.test.js, asserting
identical results to 4 decimals. The expected numbers are the single shared
source of truth used by both languages.

If Node is available it additionally executes `node app/engine.test.js` so the
real JavaScript engine is exercised too; if Node is absent (as in the build
environment here) that step is skipped with a note and the Python-port check
still runs -- both are pinned to the same EXPECTED constants below.

Run:
    python HeatPump/pipeline/validate_engine.py
"""

from __future__ import annotations

import math
import os
import shutil
import subprocess
import sys

# ---------------------------------------------------------------------------
# Constants -- identical to engine.js.
# ---------------------------------------------------------------------------
COMBUSTION_EF_G_PER_KWH = {"gas": 181.0, "oil": 275.0, "propane": 214.0, "electric": 0.0}
GAS_KWH_PER_M3 = 10.55
GAS_KG_PER_M3 = 0.68
CH4_GWP_DEFAULT = 28.0
G2KG = 0.001

SEASON_BY_MONTH = {
    1: "winter", 2: "winter", 3: "spring", 4: "spring", 5: "spring",
    6: "summer", 7: "summer", 8: "summer", 9: "fall", 10: "fall",
    11: "fall", 12: "winter",
}
CUM_DAYS = {
    "common": [0, 0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334],
    "leap": [0, 0, 31, 60, 91, 121, 152, 182, 213, 244, 274, 305, 335],
}


def month_of_day(day_of_year: int, leap: bool) -> int:
    cum = CUM_DAYS["leap"] if leap else CUM_DAYS["common"]
    for m in range(12, 0, -1):
        if day_of_year >= cum[m]:
            return m
    return 1


def temp_bin_left(t: float) -> int:
    return int(math.floor(t / 2) * 2)


def interp(xs, ys, x):
    n = len(xs)
    if x <= xs[0]:
        return ys[0]
    if x >= xs[n - 1]:
        return ys[n - 1]
    lo, hi = 0, n - 1
    while hi - lo > 1:
        mid = (lo + hi) >> 1
        if xs[mid] <= x:
            lo = mid
        else:
            hi = mid
    y0, y1 = ys[lo], ys[hi]
    if y0 is None or y1 is None:
        return None
    t = (x - xs[lo]) / (xs[hi] - xs[lo])
    return y0 + t * (y1 - y0)


def cold_edge(curve):
    """Coldest defined (cap & COP) grid point and coldest-segment slope.

    Mirror of engine.js coldEdge(): used only by the optional 'derate' mode
    (continue below the published minimum operating temperature).
    """
    T, cap, cop = curve["T_C"], curve["cap_frac_of_rated47"], curve["COP"]
    i0 = -1
    for i in range(len(T)):
        if cap[i] is not None and cop[i] is not None:
            i0 = i
            break
    if i0 < 0:
        return None
    i1 = i0 + 1
    while i1 < len(T) and (cap[i1] is None or cop[i1] is None):
        i1 += 1
    slope = (cap[i1] - cap[i0]) / (T[i1] - T[i0]) if i1 < len(T) else 0.0
    return {"tEdge": T[i0], "capEdge": cap[i0], "copFloor": cop[i0], "capSlope": slope}


def lookup_shape(ef, season, hour, tbin, field):
    thin = ef.get("meta", {}).get("thin_bin_min_hours", 20)
    h, tb = str(hour), str(tbin)
    c = ef.get("fine", {}).get(season, {}).get(h, {}).get(tb)
    if c and c[2] >= thin:
        return c[field]
    c = ef.get("coarse_ts", {}).get(season, {}).get(tb)
    if c and c[2] >= thin:
        return c[field]
    c = ef.get("coarse_t", {}).get(tb)
    if c and c[2] >= thin:
        return c[field]
    return ef["global"][field]


def grid_ef(ef, season, hour, tbin, mode, level_override):
    field = 1 if mode == "marginal" else 0
    level = (level_override if level_override else ef["reference_level_g_per_kWh"])[field]
    return level * lookup_shape(ef, season, hour, tbin, field)


def hp_performance(hp, t, ewt):
    curve = hp["curve"]
    if hp.get("kind") == "gshp":
        cop = interp(curve["EWT_C"], curve["COP"], ewt)
        frac = interp(curve["EWT_C"], curve["cap_frac_of_ewt0"], ewt)
        af = hp.get("antifreezeFactor", 1.0)
        return hp["nominalCap_kW"] * frac, cop * af, False, False
    if t < hp["minOpTemp_C"]:
        # Default ('hard'): hard stop at the published minimum. Optional
        # 'derate': keep running below it, capacity extrapolated on the coldest
        # segment slope, COP held at the floor (manufacturer-unspecified).
        if hp.get("belowLockout") == "derate":
            e = cold_edge(curve)
            if e:
                capf = e["capEdge"] + e["capSlope"] * (t - e["tEdge"])
                if capf > 0:
                    return hp["nominalCap_kW"] * capf, e["copFloor"], False, True
        return 0.0, None, True, False
    cop = interp(curve["T_C"], curve["COP"], t)
    frac = interp(curve["T_C"], curve["cap_frac_of_rated47"], t)
    if cop is None or frac is None or frac <= 0:
        return 0.0, None, True, False
    return hp["nominalCap_kW"] * frac, cop, False, False


def simulate(opts):
    temps = opts["tempSeries"]
    n = len(temps)
    leap = n == 8784
    ua = opts["archetype"]["UA_W_per_K"] / 1000.0
    tbal = opts["archetype"]["Tbalance_C"]
    base_fuel = opts["baseCase"]["fuel"]
    base_eff = opts["baseCase"]["efficiency"]
    base_comb_ef = COMBUSTION_EF_G_PER_KWH[base_fuel]
    hp = opts["hp"]
    hp.setdefault("kind", "ashp")
    backup = opts.get("backup", {"type": "electric", "efficiency": 1.0})
    backup_comb_ef = 0.0 if backup["type"] == "none" else COMBUSTION_EF_G_PER_KWH[backup["type"]]
    control = opts.get("control", {"strategy": "load-exceeds-capacity"})
    lc = opts.get("lifecycle", {})
    line_loss = 1.0 + lc.get("lineLossPct", 5.0) / 100.0
    methane_pct = lc.get("methaneLeakPct", 0.0)
    methane_gwp = lc.get("methaneGWP", CH4_GWP_DEFAULT)
    oil_up = lc.get("oilUpstreamFrac", 0.0)
    ef_mode = "marginal" if opts.get("efMode") == "marginal" else "average"
    ef_level = opts.get("efLevel")
    start_month = opts.get("startMonth", 1)

    base_fuel_kwh = base_elec = 0.0
    hp_elec = bk_elec = bk_fuel = 0.0
    base_comb = base_elecghg = base_ch4 = base_oilup = 0.0
    proj_comb = proj_elecghg = proj_ch4 = 0.0
    total_load = hp_delivered = bk_delivered = 0.0
    hp_run = backup_h = lockout_h = derated_h = heating_h = 0

    for i in range(n):
        t = temps[i]
        hour = (i % 24) + 1
        day = i // 24
        month = month_of_day(day, leap)
        if start_month != 1:
            month = ((month - 1 + (start_month - 1)) % 12) + 1
        season = SEASON_BY_MONTH[month]
        tbin = temp_bin_left(t)
        load = ua * max(0.0, tbal - t)
        if load <= 0:
            continue
        heating_h += 1
        total_load += load
        ef_hr = grid_ef(opts["ef"], season, hour, tbin, ef_mode, ef_level)

        # base case
        if base_fuel == "electric":
            be = load / base_eff
            base_elec += be
            base_elecghg += ef_hr * be * line_loss * G2KG
        else:
            bf = load / base_eff
            base_fuel_kwh += bf
            base_comb += base_comb_ef * bf * G2KG
            if base_fuel == "oil":
                base_oilup += oil_up * base_comb_ef * bf * G2KG
            elif base_fuel in ("gas", "propane"):
                base_ch4 += (methane_pct / 100.0) * (bf / GAS_KWH_PER_M3) * GAS_KG_PER_M3 * methane_gwp

        # project case
        ewt = (hp.get("ewtSeries", [None] * n)[i] if hp.get("ewtSeries") else hp.get("ewt")) if hp["kind"] == "gshp" else None
        cap, cop, locked, derated = hp_performance(hp, t, ewt)
        hp_allowed = not locked
        if control["strategy"] == "lockout" and t < control["lockoutTemp_C"]:
            hp_allowed = False
        hp_heat = 0.0
        if hp_allowed and cap > 0 and cop:
            hp_heat = min(load, cap)
            he = hp_heat / cop
            hp_elec += he
            proj_elecghg += ef_hr * he * line_loss * G2KG
            hp_delivered += hp_heat
            hp_run += 1
            if derated:
                derated_h += 1
        elif locked or (control["strategy"] == "lockout" and t < control["lockoutTemp_C"]):
            lockout_h += 1

        bk_heat = load - hp_heat
        if bk_heat > 1e-12 and backup["type"] != "none":
            backup_h += 1
            bk_delivered += bk_heat
            if backup["type"] == "electric":
                bke = bk_heat / backup["efficiency"]
                bk_elec += bke
                proj_elecghg += ef_hr * bke * line_loss * G2KG
            else:
                bkf = bk_heat / backup["efficiency"]
                bk_fuel += bkf
                proj_comb += backup_comb_ef * bkf * G2KG
                if backup["type"] in ("gas", "propane"):
                    proj_ch4 += (methane_pct / 100.0) * (bkf / GAS_KWH_PER_M3) * GAS_KG_PER_M3 * methane_gwp
        elif bk_heat > 1e-12 and backup["type"] == "none":
            backup_h += 1

    refrigerant = 0.0
    if lc.get("charge_kg") and lc.get("refrigerantGWP"):
        eol = lc.get("eolLossFrac", 0.0)
        life = lc.get("lifetimeYears", 15.0)
        refrigerant = lc["charge_kg"] * (lc.get("leakRate_frac", 0.0) + eol / life) * lc["refrigerantGWP"]

    proj_elec_total = hp_elec + bk_elec
    return {
        "base": {
            "energy": {"fuel_kWh": base_fuel_kwh, "electricity_kWh": base_elec},
            "ghg": {
                "combustion": base_comb, "electricity": base_elecghg,
                "refrigerant": 0.0, "upstream_methane": base_ch4,
                "upstream_oil": base_oilup,
                "total": base_comb + base_elecghg + base_ch4 + base_oilup,
            },
        },
        "project": {
            "energy": {
                "hp_electricity_kWh": hp_elec, "backup_electricity_kWh": bk_elec,
                "backup_fuel_kWh": bk_fuel, "electricity_kWh": proj_elec_total,
            },
            "ghg": {
                "combustion": proj_comb, "electricity": proj_elecghg,
                "refrigerant": refrigerant, "upstream_methane": proj_ch4,
                "upstream_oil": 0.0,
                "total": proj_comb + proj_elecghg + refrigerant + proj_ch4,
            },
            "diagnostics": {
                "load_kWh": total_load, "hp_delivered_kWh": hp_delivered,
                "backup_delivered_kWh": bk_delivered,
                "seasonal_cop": (hp_delivered / hp_elec) if hp_elec > 0 else None,
                "heating_hours": heating_h, "hp_run_hours": hp_run,
                "backup_hours": backup_h, "lockout_hours": lockout_h,
                "derated_hours": derated_h,
            },
        },
    }


# ---------------------------------------------------------------------------
# Shared synthetic fixtures -- identical to app/engine.test.js.
# ---------------------------------------------------------------------------
CURVE = {"T_C": [-30, 15], "cap_frac_of_rated47": [0.5, 0.5], "COP": [2.5, 2.5]}
EF = {
    "meta": {"thin_bin_min_hours": 20, "province": "TEST"},
    "reference_level_g_per_kWh": [100, 500],
    "fine": {}, "coarse_ts": {}, "coarse_t": {}, "global": [1.0, 1.0, 1],
}


def base_opts(**overrides):
    o = {
        "tempSeries": [-10],
        "archetype": {"UA_W_per_K": 250, "Tbalance_C": 18},
        "baseCase": {"fuel": "gas", "efficiency": 0.8},
        "hp": {"curve": CURVE, "nominalCap_kW": 10, "minOpTemp_C": -30, "kind": "ashp"},
        "backup": {"type": "electric", "efficiency": 1.0},
        "control": {"strategy": "load-exceeds-capacity"},
        "lifecycle": {"lineLossPct": 5},
        "ef": EF,
        "efMode": "average",
    }
    o.update(overrides)
    return o


def main() -> int:
    fails = 0

    def approx(name, got, want):
        nonlocal fails
        if got is None or abs(got - want) >= 5e-5:
            fails += 1
            print(f"  FAIL {name}: got {got} want {want}")
        else:
            print(f"  ok   {name} = {got}")

    print("Case 1: -10 C, load > capacity, electric backup")
    r1 = simulate(base_opts())
    approx("load_kWh", r1["project"]["diagnostics"]["load_kWh"], 7.0)
    approx("hp_delivered_kWh", r1["project"]["diagnostics"]["hp_delivered_kWh"], 5.0)
    approx("backup_delivered_kWh", r1["project"]["diagnostics"]["backup_delivered_kWh"], 2.0)
    approx("hp_electricity_kWh", r1["project"]["energy"]["hp_electricity_kWh"], 2.0)
    approx("backup_electricity_kWh", r1["project"]["energy"]["backup_electricity_kWh"], 2.0)
    approx("project electricity_kWh", r1["project"]["energy"]["electricity_kWh"], 4.0)
    approx("project ghg.electricity (avg)", r1["project"]["ghg"]["electricity"], 0.42)
    approx("base fuel_kWh", r1["base"]["energy"]["fuel_kWh"], 8.75)
    approx("base ghg.combustion", r1["base"]["ghg"]["combustion"], 1.58375)
    r1m = simulate(base_opts(efMode="marginal"))
    approx("project ghg.electricity (marginal)", r1m["project"]["ghg"]["electricity"], 2.1)

    print("Case 2: +20 C, above balance point -> zero")
    r2 = simulate(base_opts(tempSeries=[20]))
    approx("load_kWh", r2["project"]["diagnostics"]["load_kWh"], 0.0)
    approx("heating_hours", r2["project"]["diagnostics"]["heating_hours"], 0)
    approx("project electricity_kWh", r2["project"]["energy"]["electricity_kWh"], 0.0)
    approx("project ghg.total", r2["project"]["ghg"]["total"], 0.0)
    approx("base ghg.total", r2["base"]["ghg"]["total"], 0.0)

    print("Case 3: lockout at -5 C, T=-10 -> HP ignored, all to backup")
    r3 = simulate(base_opts(control={"strategy": "lockout", "lockoutTemp_C": -5}))
    approx("hp_delivered_kWh", r3["project"]["diagnostics"]["hp_delivered_kWh"], 0.0)
    approx("hp_run_hours", r3["project"]["diagnostics"]["hp_run_hours"], 0)
    approx("lockout_hours", r3["project"]["diagnostics"]["lockout_hours"], 1)
    approx("backup_delivered_kWh", r3["project"]["diagnostics"]["backup_delivered_kWh"], 7.0)
    approx("backup_electricity_kWh", r3["project"]["energy"]["backup_electricity_kWh"], 7.0)
    approx("project ghg.electricity", r3["project"]["ghg"]["electricity"], 0.735)

    print("Case 4: refrigerant amortization")
    r4 = simulate(base_opts(lifecycle={
        "lineLossPct": 5, "charge_kg": 3, "leakRate_frac": 0.05,
        "eolLossFrac": 0.8, "lifetimeYears": 15, "refrigerantGWP": 2256,
    }))
    approx("project ghg.refrigerant", r4["project"]["ghg"]["refrigerant"], 699.36)

    print("Case 5: upstream methane on base gas")
    r5 = simulate(base_opts(
        archetype={"UA_W_per_K": (80 / 28) * 1000, "Tbalance_C": 18},
        lifecycle={"lineLossPct": 5, "methaneLeakPct": 2, "methaneGWP": 28},
    ))
    approx("base fuel_kWh", r5["base"]["energy"]["fuel_kWh"], 100.0)
    approx("base ghg.upstream_methane", r5["base"]["ghg"]["upstream_methane"], 3.609479)

    # ======================================================================
    # Case 6: below-lock-out "derate" mode (ROADMAP item 9 workstream E).
    #   Curve   T_C [-10, 0, 15], cap_frac [0.5, 0.7, 1.0], COP [2.0, 3.0, 4.0]
    #   min-op  -10 C  ->  hard stop below -10 C by default.
    #   Coldest defined point: (-10 C, cap 0.5, COP 2.0). Coldest capacity
    #   segment slope = (0.7-0.5)/(0-(-10)) = 0.02 per degC. COP floor = 2.0.
    #   Test hour at T = -20 C (10 C below the published minimum):
    #     load       = 0.25 * (18 - (-20)) = 9.5 kWh
    #     derate cap = 0.5 + 0.02*(-20 - (-10)) = 0.3 frac -> 10 kW * 0.3 = 3.0 kW
    #     HP delivers min(9.5, 3.0) = 3.0 ; HP elec = 3.0 / 2.0 = 1.5 kWh
    #     backup delivers 6.5 ; lockout_hours 0, derated_hours 1, hp_run 1.
    #   Default 'hard' mode on the SAME curve/hour: HP locked out, delivers 0.
    # ======================================================================
    print("Case 6: below-lock-out derate mode")
    CURVE_D = {"T_C": [-10, 0, 15], "cap_frac_of_rated47": [0.5, 0.7, 1.0], "COP": [2.0, 3.0, 4.0]}
    d_hp = {"curve": CURVE_D, "nominalCap_kW": 10, "minOpTemp_C": -10, "kind": "ashp", "belowLockout": "derate"}
    r6 = simulate(base_opts(tempSeries=[-20], hp=d_hp))
    approx("derate hp_delivered_kWh", r6["project"]["diagnostics"]["hp_delivered_kWh"], 3.0)
    approx("derate hp_electricity_kWh", r6["project"]["energy"]["hp_electricity_kWh"], 1.5)
    # guard: default hard-stop on the same curve/hour locks the compressor out.
    h_hp = {"curve": CURVE_D, "nominalCap_kW": 10, "minOpTemp_C": -10, "kind": "ashp"}
    r6h = simulate(base_opts(tempSeries=[-20], hp=h_hp))
    approx("hard hp_delivered_kWh", r6h["project"]["diagnostics"]["hp_delivered_kWh"], 0.0)

    print()
    if fails:
        print(f"!!! {fails} Python-mirror assertion(s) FAILED")
    else:
        print("All Python-mirror assertions passed (identical to engine.js to 4 dp).")

    # ---- also run the real JS engine if Node is available ----
    node = shutil.which("node")
    js_test = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app", "engine.test.js")
    if node:
        print("\nRunning node app/engine.test.js ...")
        proc = subprocess.run([node, js_test], capture_output=True, text=True)
        sys.stdout.write(proc.stdout)
        if proc.returncode != 0:
            sys.stderr.write(proc.stderr)
            fails += 1
    else:
        print("\n(node not found -- skipped running app/engine.test.js directly; "
              "the Python mirror above asserts the same shared expected constants.)")

    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
