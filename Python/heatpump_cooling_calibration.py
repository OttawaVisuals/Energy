"""
Phase 0 cooling-load calibration for the Heat Pump Explorer (heatpump.html).

GO/NO-GO GATE. Nothing user-facing changes here. This script tests whether a
simple cooling-balance-point model can reproduce published residential cooling
energy before we build any cooling arm into the engine or the page.

THE MODEL UNDER TEST
--------------------
The heating side uses  load = UA x (zero-heat - outdoor)  with gains excluded
deliberately (ignoring gains only oversizes slightly). That inversion does NOT
hold for cooling: at 26 C out / 22 C in, UA x 4 K is almost nothing while solar
through glazing is several kW. Solar and internal gains ARE the cooling load.

So instead of modelling gains explicitly, we push the balance point well below
the indoor setpoint and let it ABSORB the gains:

    cooling_load_kWh  = SUM over 8760 h of  UA x max(0, T_out - T_c)  x latent
    cooling_elec_kWh  = cooling_load_kWh / COP_seasonal

T_c is the free parameter. It is NOT a thermostat setpoint -- it is the outdoor
temperature above which this envelope, with its gains, needs mechanical cooling.

WHAT THIS SCRIPT DECIDES
------------------------
1. FIT       - what T_c reproduces CEUD per-home cooling, per province, across a
               range of assumed AC prevalence (prevalence is not yet known; it
               comes from ERS AIRCONDTYPE in Phase 1).
2. SHAPE     - the real test. Fix T_c and predict 2019-2023 per province from
               actual weather, then compare the YEAR-OVER-YEAR PATTERN to CEUD.
               COP_seasonal and latent are pure scale factors, so they cancel out
               of a shape comparison: this test is invariant to both, and is
               therefore the only part of the fit that can actually falsify the
               model. ON swings 12.1 -> 18.4 -> 13.2 PJ on weather alone; if our
               8760 traces cannot reproduce that swing, the approach is wrong.

INPUTS (all already on disk, nothing fetched)
---------------------------------------------
  HeatPump/data/processed/archetypes.json    UA_W_per_K, n_homes, per city/vintage
  HeatPump/data/processed/weather_<city>.json  8760 hourly temps (tenths deg C)
  ceud_json/res_{on,qc,ab}.json              NRCan CEUD space_cooling PJ,
                                             single_detached, by year
  census_json/region_census.json             single-detached dwelling counts

OUTPUTS
-------
  HeatPump/data/interim/cooling_calibration.csv   per province/year fit + residuals
  stdout report

CAVEATS THIS SCRIPT DOES NOT RESOLVE
------------------------------------
- CEUD is a FLEET average including homes with no AC. Dividing by an assumed
  prevalence to get per-AC-home is the only way to compare against a tool that
  assumes every home has central AC. Prevalence is assumed here, not measured.
- The archetype UA fleet (ERS-derived) is not the same population as the CEUD
  fleet. Absolute agreement is not expected; shape agreement is.
- Latent (dehumidification) load is a flat multiplier, not a humidity model.
"""

import csv
import json
import os

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# --- fixed assumptions (scale factors; see docstring -- shape test is immune) ---
# Fleet-stock central AC, not a new unit. SEER is Btu/Wh, so COP = SEER / 3.412.
ASSUMED_SEER = 12.0
COP_SEASONAL = ASSUMED_SEER / 3.412
# Dehumidification share of total cooling load. Humid continental (ON/QC) vs the
# dry prairie (AB). Flat multipliers, deliberately crude -- flagged in docstring.
LATENT = {"ON": 1.25, "QC": 1.25, "AB": 1.05}

# Cities present in BOTH archetypes.json and the weather set, grouped to province.
PROV_CITIES = {
    "ON": ["Ottawa", "Toronto"],
    "QC": ["Montreal", "Quebec City"],
    "AB": ["Calgary", "Edmonton"],
}
# Detached only -- CEUD slice, census slice and archetype slice all mean detached.
DETACHED = ("pre_1980_detached", "1980_2005_detached", "post_2005_detached")

YEARS = [2019, 2020, 2021, 2022, 2023]
PREVALENCE_GRID = [1.0, 0.85, 0.70, 0.50, 0.30, 0.20]

PJ_TO_KWH = 1e15 / 3.6e6


def weather_file(city):
    return os.path.join(REPO, "HeatPump", "data", "processed",
                        "weather_%s.json" % city.lower().replace(" ", ""))


def load_temps(city):
    """{year: [8760 floats in deg C]} for one city."""
    with open(weather_file(city), encoding="utf-8") as fh:
        d = json.load(fh)
    out = {}
    for yr, rec in d["years"].items():
        t = rec.get("temps_tenthsC")
        if not t:
            continue
        out[yr] = [v / 10.0 for v in t]
    return out


def city_ua_kw_per_k(arch_city):
    """n_homes-weighted UA across detached archetypes, kW/K. Also returns weight."""
    num = den = 0.0
    for key in DETACHED:
        a = arch_city.get(key)
        if not a:
            continue
        w = a.get("n_homes") or 0
        num += (a["UA_W_per_K"] / 1000.0) * w
        den += w
    return (num / den if den else 0.0), den


def cooling_elec_kwh(temps, ua_kw_per_k, t_c, latent):
    """Annual cooling electricity for one home, one weather year."""
    degree_hours = 0.0
    for t in temps:
        if t > t_c:
            degree_hours += t - t_c
    load = ua_kw_per_k * degree_hours * latent   # kWh (1 h steps)
    return load / COP_SEASONAL


def ceud_cooling_pj(prov):
    """{year: PJ} residential space cooling, single detached."""
    path = os.path.join(REPO, "ceud_json", "res_%s.json" % prov.lower())
    with open(path, encoding="utf-8") as fh:
        d = json.load(fh)
    return {
        r["year"]: r["energy_PJ"]
        for r in d["records"]
        if r.get("end_use") == "space_cooling"
        and r.get("building_type") == "single_detached"
    }


def census_detached(prov):
    path = os.path.join(REPO, "census_json", "region_census.json")
    with open(path, encoding="utf-8") as fh:
        d = json.load(fh)
    return d[prov]["dwelling_type"]["single_detached"]


def solve_t_c(prov, arch, weather, year, target_kwh_per_home):
    """Bisect for the T_c reproducing target_kwh_per_home. Monotone decreasing."""
    latent = LATENT[prov]

    def modelled(t_c):
        num = den = 0.0
        for city in PROV_CITIES[prov]:
            temps = weather[city].get(str(year))
            if not temps:
                continue
            ua, w = city_ua_kw_per_k(arch[city])
            num += cooling_elec_kwh(temps, ua, t_c, latent) * w
            den += w
        return (num / den) if den else 0.0

    lo, hi = 5.0, 30.0
    if modelled(lo) < target_kwh_per_home:
        return None, modelled(lo)      # even cooling from 5 C cannot reach target
    if modelled(hi) > target_kwh_per_home:
        return None, modelled(hi)      # target too small for any sensible T_c
    for _ in range(60):
        mid = (lo + hi) / 2.0
        if modelled(mid) > target_kwh_per_home:
            lo = mid
        else:
            hi = mid
    t_c = (lo + hi) / 2.0
    return t_c, modelled(t_c)


def main():
    arch_path = os.path.join(REPO, "HeatPump", "data", "processed", "archetypes.json")
    with open(arch_path, encoding="utf-8") as fh:
        arch = json.load(fh)

    weather = {}
    for cities in PROV_CITIES.values():
        for c in cities:
            weather[c] = load_temps(c)

    print("=" * 78)
    print("PHASE 0 -- COOLING BALANCE POINT CALIBRATION")
    print("=" * 78)
    print("Fixed: SEER %.1f (COP %.2f), latent %s" % (ASSUMED_SEER, COP_SEASONAL, LATENT))
    print("These are scale factors. The year-tracking test below is invariant to them.")

    # ---- envelope + target context -------------------------------------------
    print("\n--- Envelope (n_homes-weighted, detached) ---")
    for prov, cities in PROV_CITIES.items():
        for city in cities:
            ua, w = city_ua_kw_per_k(arch[city])
            print("  %-3s %-12s UA %.3f kW/K   (n_homes %s)" % (prov, city, ua, f"{int(w):,}"))

    ceud = {p: ceud_cooling_pj(p) for p in PROV_CITIES}
    homes = {p: census_detached(p) for p in PROV_CITIES}

    print("\n--- CEUD target, per detached home (fleet avg, incl. homes with no AC) ---")
    for prov in PROV_CITIES:
        row = "  %-3s " % prov
        for yr in YEARS:
            pj = ceud[prov].get(yr)
            row += "%d: %5.0f kWh   " % (yr, pj * PJ_TO_KWH / homes[prov]) if pj else ""
        print(row)

    # ---- 1. FIT: T_c vs assumed prevalence ------------------------------------
    print("\n" + "=" * 78)
    print("1. FITTED BALANCE POINT T_c  (2023 weather, by assumed AC prevalence)")
    print("=" * 78)
    print("  %-4s %s" % ("prev", "".join("%-12s" % p for p in PROV_CITIES)))
    for prev in PREVALENCE_GRID:
        cells = ""
        for prov in PROV_CITIES:
            pj = ceud[prov].get(2023)
            if not pj:
                cells += "%-12s" % "n/a"
                continue
            target = pj * PJ_TO_KWH / homes[prov] / prev
            t_c, got = solve_t_c(prov, arch, weather, 2023, target)
            cells += "%-12s" % ("%.1f C" % t_c if t_c is not None else "no soln")
        print("  %-4.0f%% %s" % (prev * 100, cells))
    print("\n  'no soln' = no T_c in 5-30 C reproduces that target.")

    # ---- 2. SHAPE: the falsifiable test ---------------------------------------
    print("\n" + "=" * 78)
    print("2. YEAR-TRACKING TEST  (the real validation -- immune to COP/latent)")
    print("=" * 78)
    print("  Fit T_c on 2023 at 100% prevalence, then predict other years from weather.")
    print("  If modelled/CEUD ratios stay flat across years, weather explains the swing.\n")

    rows = []
    for prov in PROV_CITIES:
        pj23 = ceud[prov].get(2023)
        if not pj23:
            continue
        target23 = pj23 * PJ_TO_KWH / homes[prov]
        t_c, _ = solve_t_c(prov, arch, weather, 2023, target23)
        if t_c is None:
            print("  %-3s could not fit a balance point on 2023 -- see table above." % prov)
            # still record the attempt so the CSV shows the failure
            rows.append({"province": prov, "year": 2023, "t_c_C": "",
                         "ceud_kwh_per_home": round(target23), "modelled_kwh_per_home": "",
                         "ratio_model_over_ceud": "", "note": "no T_c solution in 5-30C"})
            continue

        print("  %-3s  fitted T_c = %.1f C" % (prov, t_c))
        print("       %-6s %10s %10s %8s" % ("year", "CEUD", "modelled", "ratio"))
        ratios = []
        for yr in YEARS:
            pj = ceud[prov].get(yr)
            if not pj:
                continue
            num = den = 0.0
            for city in PROV_CITIES[prov]:
                temps = weather[city].get(str(yr))
                if not temps:
                    continue
                ua, w = city_ua_kw_per_k(arch[city])
                num += cooling_elec_kwh(temps, ua, t_c, LATENT[prov]) * w
                den += w
            if not den:
                continue
            model = num / den
            actual = pj * PJ_TO_KWH / homes[prov]
            ratio = model / actual if actual else 0.0
            ratios.append(ratio)
            print("       %-6d %10.0f %10.0f %8.2f" % (yr, actual, model, ratio))
            rows.append({
                "province": prov, "year": yr, "t_c_C": round(t_c, 2),
                "ceud_kwh_per_home": round(actual),
                "modelled_kwh_per_home": round(model),
                "ratio_model_over_ceud": round(ratio, 3), "note": "",
            })
        if ratios:
            spread = max(ratios) - min(ratios)
            print("       ratio spread %.2f  %s\n" % (
                spread,
                "GOOD - weather explains the year-over-year swing" if spread < 0.25
                else "POOR - weather alone does not explain the swing"))

    # ---- 3. DIAGNOSTIC: is the residual adoption growth, or bad physics? ------
    # A monotone drift in the per-year fitted T_c means the model shape is fine
    # and something outside the weather is growing. Scatter would mean bad physics.
    print("\n" + "=" * 78)
    print("3. PER-YEAR FITTED T_c  (drift => adoption growth, scatter => bad physics)")
    print("=" * 78)
    print("  %-4s %s" % ("year", "".join("%-12s" % p for p in PROV_CITIES)))
    for yr in YEARS:
        cells = ""
        for prov in PROV_CITIES:
            pj = ceud[prov].get(yr)
            if not pj:
                cells += "%-12s" % "n/a"
                continue
            target = pj * PJ_TO_KWH / homes[prov]
            t_c, _ = solve_t_c(prov, arch, weather, yr, target)
            cells += "%-12s" % ("%.1f C" % t_c if t_c is not None else "no soln")
        print("  %-4d %s" % (yr, cells))

    # ---- 4. Fix T_c, read off the implied AC prevalence -----------------------
    # If one common balance point works everywhere, then prevalence -- not
    # physics -- is what separates the provinces, and it is the thing to measure.
    common_t_c = 17.0
    print("\n" + "=" * 78)
    print("4. IMPLIED AC PREVALENCE at a single common T_c = %.1f C" % common_t_c)
    print("=" * 78)
    print("  (modelled per-AC-home cooling vs CEUD fleet average)")
    print("  %-4s %s" % ("year", "".join("%-12s" % p for p in PROV_CITIES)))
    for yr in YEARS:
        cells = ""
        for prov in PROV_CITIES:
            pj = ceud[prov].get(yr)
            if not pj:
                cells += "%-12s" % "n/a"
                continue
            num = den = 0.0
            for city in PROV_CITIES[prov]:
                temps = weather[city].get(str(yr))
                if not temps:
                    continue
                ua, w = city_ua_kw_per_k(arch[city])
                num += cooling_elec_kwh(temps, ua, common_t_c, LATENT[prov]) * w
                den += w
            per_ac_home = (num / den) if den else 0.0
            actual = pj * PJ_TO_KWH / homes[prov]
            cells += "%-12s" % ("%.0f%%" % (100 * actual / per_ac_home) if per_ac_home else "n/a")
        print("  %-4d %s" % (yr, cells))
    print("\n  Rising values = AC adoption growing (a real trend, not a model fault).")

    out = os.path.join(REPO, "HeatPump", "data", "interim", "cooling_calibration.csv")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["province", "year", "t_c_C",
                                           "ceud_kwh_per_home", "modelled_kwh_per_home",
                                           "ratio_model_over_ceud", "note"])
        w.writeheader()
        w.writerows(rows)
    print("wrote %s" % os.path.relpath(out, REPO))


if __name__ == "__main__":
    main()
