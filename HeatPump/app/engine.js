/*
 * engine.js -- Heat Pump tool, Phase 5 core simulation engine.
 *
 * A single pure function, simulate(), that runs one heating year hour by hour
 * and returns annual + monthly energy-by-source and GHG-by-category for a
 * BASE case (the existing gas/oil furnace or electric baseboard) and a PROJECT
 * case (an air-source heat pump with optional backup). No DOM, no
 * dependencies -- runs unchanged in the browser and in Node.
 *
 * A ground-source (kind:'gshp') code path exists below but is NOT wired into
 * the shipping UI -- every caller passes kind:'ashp', so the tool is
 * air-source-only, matching the methodology panel's "no ground-source option
 * in this version". The GSHP branch is dormant scaffolding for a later phase;
 * do not describe it as a user-facing feature until a caller sets kind:'gshp'.
 *
 * Two amendments to the PLAN.md Phase 5 prompt (see METHODOLOGY.md "Simulation
 * engine (Phase 5)"):
 *
 *   1. Heat pump input is a NORMALIZED TIER CURVE from hp_curves.json --
 *      { T_C[], cap_frac_of_rated47[], COP[] } -- scaled by a user-selected
 *      nominal capacity (kW at 47 F). The engine multiplies the fractional
 *      capacity by nominalCap_kW; the fractional shape is size-independent so
 *      any per-model, per-tier or "average installed" curve plugs in the same
 *      way. Lockout is governed by the curve's own min_op_temp_C, NOT by the
 *      COP array being null (the aggregate tier/average curves keep a non-null
 *      COP below their median lockout temperature).
 *
 *   2. Hourly grid emissions factor comes from the Phase-2 EF SURFACE
 *      (ef_surface_{on,ab,qc}.json), with an average / marginal toggle per
 *      methodology decision #1. EF(hour) = level * shape(tbin, hour, season);
 *      the toggle selects both the level index and the shape-ratio field.
 *
 * All physical constants are documented inline and in METHODOLOGY.md.
 *
 * NOTE: this file is a verbatim extract of the engine inlined in
 * heatpump.html (the shipping copy). If you change one, re-sync the other.
 * Later additions beyond the original Phase 5 outputs, all additive:
 *   - energy.elec_month_hour  (12x24 kWh matrix, for TOU pricing)
 *   - hourly.{ef_g_per_kWh, load_kW, base_ghg_kg, proj_ghg_kg}
 *   - hourly.{base_energy_kWh, hp_elec_kWh, backup_energy_kWh}
 *     (purchased-energy series, for the by-temperature charts)
 */

(function (root, factory) {
  if (typeof module === "object" && module.exports) {
    module.exports = factory();
  } else {
    root.HeatPumpEngine = factory();
  }
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  // --------------------------------------------------------------------------
  // Physical constants (ECCC National Inventory Report; see METHODOLOGY.md).
  // --------------------------------------------------------------------------

  // Direct combustion emission factors, grams CO2e per kWh of FUEL INPUT
  // (higher-heating-value basis, matching the AFUE/seasonal-efficiency the
  // base-case `efficiency` is expressed on). Electric baseboard has no
  // combustion term -- its emissions come entirely from the grid.
  var COMBUSTION_EF_G_PER_KWH = {
    gas: 181.0, // natural gas: 1.921 kg CO2e/m3 / 10.55 kWh/m3
    oil: 275.0, // light fuel oil (No.2): ~2.75 kg CO2e/L / ~10 kWh/L
    propane: 214.0, // 1.55 kg CO2e/L / ~7.2 kWh/L
    electric: 0.0,
  };

  // Natural-gas physical properties, for converting a gas energy throughput
  // (kWh, HHV) into a leaked-methane mass for the upstream-methane term.
  var GAS_KWH_PER_M3 = 10.55; // HHV energy content
  var GAS_KG_PER_M3 = 0.68; // density of pipeline gas (~100% CH4 assumed for leak)

  var CH4_GWP_DEFAULT = 28.0; // AR5, 100-yr (methane); AR6 ~29.8

  var SEASON_BY_MONTH = {
    1: "winter", 2: "winter", 3: "spring", 4: "spring", 5: "spring",
    6: "summer", 7: "summer", 8: "summer", 9: "fall", 10: "fall",
    11: "fall", 12: "winter",
  };

  // Cumulative days before month m (1-indexed), non-leap and leap.
  var CUM_DAYS = {
    common: [0, 0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334],
    leap: [0, 0, 31, 60, 91, 121, 152, 182, 213, 244, 274, 305, 335],
  };

  // --------------------------------------------------------------------------
  // Small helpers.
  // --------------------------------------------------------------------------

  // Month (1..12) for a 0-based day-of-year, given a calendar (365 or 366 days).
  function monthOfDay(dayOfYear, leap) {
    var cum = leap ? CUM_DAYS.leap : CUM_DAYS.common;
    for (var m = 12; m >= 1; m--) {
      if (dayOfYear >= cum[m]) return m;
    }
    return 1;
  }

  // Left edge (inclusive) of the 2 C temperature bin -- mirrors
  // build_ef_surface.temp_bin_left exactly (floor to a multiple of 2).
  function tempBinLeft(tempC) {
    return Math.floor(tempC / 2) * 2;
  }

  // Linear interpolation of `ys` (parallel to ascending `xs`) at `x`, clamped
  // at both ends. Returns null if either bracketing y is null (locked-out
  // per-model curves store null COP below min-op temperature).
  function interp(xs, ys, x) {
    var n = xs.length;
    if (x <= xs[0]) return ys[0];
    if (x >= xs[n - 1]) return ys[n - 1];
    // Uniform 0.5 C grid in hp_curves.json, but do a safe binary search so the
    // engine also works on irregular grids.
    var lo = 0,
      hi = n - 1;
    while (hi - lo > 1) {
      var mid = (lo + hi) >> 1;
      if (xs[mid] <= x) lo = mid;
      else hi = mid;
    }
    var y0 = ys[lo],
      y1 = ys[hi];
    if (y0 === null || y1 === null) return null;
    var t = (x - xs[lo]) / (xs[hi] - xs[lo]);
    return y0 + t * (y1 - y0);
  }

  // Cold edge of an ASHP curve: the two coldest grid points where BOTH capacity
  // and COP are defined (curves store null below the model's lockout). Returns
  // the coldest defined point (tEdge/capEdge/copFloor) and the slope of the
  // coldest defined capacity segment. Used only by the optional
  // "continue derated below the published minimum operating temperature" mode --
  // capacity is extrapolated on capSlope, COP is held at copFloor. Behaviour
  // below the published minimum is manufacturer-unspecified (see METHODOLOGY.md).
  function coldEdge(curve) {
    var T = curve.T_C,
      cap = curve.cap_frac_of_rated47,
      cop = curve.COP;
    var i0 = -1;
    for (var i = 0; i < T.length; i++) {
      if (cap[i] != null && cop[i] != null) { i0 = i; break; }
    }
    if (i0 < 0) return null;
    var i1 = i0 + 1;
    while (i1 < T.length && (cap[i1] == null || cop[i1] == null)) i1++;
    var slope = i1 < T.length ? (cap[i1] - cap[i0]) / (T[i1] - T[i0]) : 0;
    return { tEdge: T[i0], capEdge: cap[i0], copFloor: cop[i0], capSlope: slope };
  }

  // Grid-EF shape ratio with the surface's thin-bin fallback -- a direct port
  // of build_ef_surface.lookup_shape (fine -> coarse_ts -> coarse_t -> global).
  // `field`: 0 = average-EF ratio, 1 = marginal-EF ratio.
  function lookupShape(ef, season, hour, tbin, field) {
    var thin = (ef.meta && ef.meta.thin_bin_min_hours) || 20;
    var h = String(hour),
      tb = String(tbin);
    var c =
      ef.fine && ef.fine[season] && ef.fine[season][h] && ef.fine[season][h][tb];
    if (c && c[2] >= thin) return c[field];
    c = ef.coarse_ts && ef.coarse_ts[season] && ef.coarse_ts[season][tb];
    if (c && c[2] >= thin) return c[field];
    c = ef.coarse_t && ef.coarse_t[tb];
    if (c && c[2] >= thin) return c[field];
    return ef.global[field];
  }

  // Absolute grid EF (g CO2e / kWh generated) for one hour under the selected
  // average / marginal mode.
  function gridEF(ef, season, hour, tbin, mode, levelOverride) {
    var field = mode === "marginal" ? 1 : 0;
    var level = levelOverride
      ? levelOverride[field]
      : ef.reference_level_g_per_kWh[field];
    return level * lookupShape(ef, season, hour, tbin, field);
  }

  // --------------------------------------------------------------------------
  // Heat-pump capacity & COP at a given hour.
  //
  // Air-source: read cap_frac_of_rated47 and COP off the tier curve at the
  // outdoor temperature, scale capacity by nominalCap_kW. Ground-source: read
  // cap_frac_of_ewt0 and COP off the EWT curve at the hour's entering-water
  // temperature. In both cases the curve's min_op_temp_C is the authoritative
  // lockout gate.
  // --------------------------------------------------------------------------
  function hpPerformance(hp, tempC, ewtC) {
    var curve = hp.curve;
    if (hp.kind === "gshp") {
      // Ground loops do not lock out on air temperature; they run whenever the
      // building calls for heat. Capacity/COP track entering water temperature.
      var copG = interp(curve.EWT_C, curve.COP, ewtC);
      var fracG = interp(curve.EWT_C, curve.cap_frac_of_ewt0, ewtC);
      var af = hp.antifreezeFactor == null ? 1.0 : hp.antifreezeFactor;
      return { capacity_kW: hp.nominalCap_kW * fracG, cop: copG * af, locked: false };
    }
    // Air-source.
    if (tempC < hp.minOpTemp_C) {
      // Default (`belowLockout` unset or 'hard'): hard stop at the published
      // minimum operating temperature -- the current, validated behaviour.
      // Optional 'derate': keep running below it, extrapolating capacity on the
      // coldest defined segment's slope and holding COP at the floor. Clearly
      // manufacturer-unspecified (see METHODOLOGY.md).
      if (hp.belowLockout === "derate") {
        var e = coldEdge(curve);
        if (e) {
          var capf = e.capEdge + e.capSlope * (tempC - e.tEdge);
          if (capf > 0) {
            return {
              capacity_kW: hp.nominalCap_kW * capf,
              cop: e.copFloor,
              locked: false,
              derated: true,
            };
          }
        }
      }
      return { capacity_kW: 0, cop: null, locked: true };
    }
    var cop = interp(curve.T_C, curve.COP, tempC);
    var frac = interp(curve.T_C, curve.cap_frac_of_rated47, tempC);
    if (cop === null || frac === null || frac <= 0) {
      return { capacity_kW: 0, cop: null, locked: true };
    }
    return { capacity_kW: hp.nominalCap_kW * frac, cop: cop, locked: false };
  }

  // --------------------------------------------------------------------------
  // simulate()
  //
  // opts = {
  //   tempSeries:   Array<number>  outdoor dry-bulb C, one per hour (8760/8784)
  //   archetype:    { UA_W_per_K, Tbalance_C }
  //   baseCase:     { fuel: 'gas'|'oil'|'propane'|'electric', efficiency }
  //                   efficiency is a fraction (AFUE/seasonal); electric ~1.0
  //   hp: {
  //     curve: { T_C[], cap_frac_of_rated47[], COP[] }   // ASHP tier/model curve
  //            | { EWT_C[], COP[], cap_frac_of_ewt0[] }  // GSHP curve
  //     nominalCap_kW,           // user-selected rated capacity @47F (ASHP) or @0C (GSHP)
  //     minOpTemp_C,             // lockout temperature (ASHP)
  //     kind: 'ashp' | 'gshp',   // default 'ashp'
  //     belowLockout?: 'hard' | 'derate', // ASHP behaviour below minOpTemp_C:
  //         'hard' (default) = hard stop; 'derate' = keep running, capacity
  //         extrapolated on the coldest segment slope, COP held at the floor
  //         (manufacturer-unspecified below the published minimum)
  //     ewtSeries?, ewt?,        // GSHP entering-water temp (series or constant C)
  //     antifreezeFactor?        // GSHP COP derate for glycol (~0.91), default 1.0
  //   }
  //   backup:  { type: 'electric'|'gas'|'oil'|'propane'|'none', efficiency }
  //   control: { strategy: 'lockout'|'load-exceeds-capacity', lockoutTemp_C? }
  //   lifecycle: {
  //     refrigerantGWP, charge_kg, leakRate_frac,   // annual leak fraction
  //     eolLossFrac?, lifetimeYears?,               // amortized end-of-life loss
  //     methaneLeakPct?, methaneGWP?,               // upstream gas methane
  //     oilUpstreamFrac?,                           // upstream oil adder (frac of combustion)
  //     lineLossPct?                                // grid line losses on delivered elec
  //   }
  //   ef:       province EF surface JSON (ef_surface_*.json)
  //   efMode:   'average' | 'marginal'   (default 'average')
  //   efLevel?: [avg, marg]  override grid level (e.g. a historical year); default reference
  //   startMonth?: 1..12 for hour 0 (default 1 = Jan 1, matching TMY)
  // }
  // --------------------------------------------------------------------------
  function simulate(opts) {
    var temps = opts.tempSeries;
    var N = temps.length;
    var leap = N === 8784;

    var UA_kW_per_K = opts.archetype.UA_W_per_K / 1000.0;
    var Tbal = opts.archetype.Tbalance_C;

    var baseFuel = opts.baseCase.fuel;
    var baseEff = opts.baseCase.efficiency;
    var baseCombEF = COMBUSTION_EF_G_PER_KWH[baseFuel];
    if (baseCombEF === undefined) throw new Error("unknown base fuel: " + baseFuel);

    var hp = opts.hp;
    if (hp.kind === undefined) hp.kind = "ashp";

    var backup = opts.backup || { type: "electric", efficiency: 1.0 };
    var backupCombEF =
      backup.type === "none" ? 0.0 : COMBUSTION_EF_G_PER_KWH[backup.type];
    if (backupCombEF === undefined) throw new Error("unknown backup type: " + backup.type);

    var control = opts.control || { strategy: "load-exceeds-capacity" };
    var lc = opts.lifecycle || {};
    var lineLoss = 1.0 + (lc.lineLossPct == null ? 5.0 : lc.lineLossPct) / 100.0;
    var methanePct = lc.methaneLeakPct == null ? 0.0 : lc.methaneLeakPct;
    var methaneGWP = lc.methaneGWP == null ? CH4_GWP_DEFAULT : lc.methaneGWP;
    var oilUpstream = lc.oilUpstreamFrac == null ? 0.0 : lc.oilUpstreamFrac;

    var efMode = opts.efMode === "marginal" ? "marginal" : "average";
    var efLevel = opts.efLevel || null;
    var startMonth = opts.startMonth || 1;

    // ---- accumulators ----
    var zeros12 = function () {
      return [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0];
    };
    // energy
    var m_base_fuel = zeros12(), // fuel input (gas/oil/propane) kWh
      m_base_elec = zeros12(); // site electricity kWh (electric base case)
    var m_hp_elec = zeros12(),
      m_bk_elec = zeros12(),
      m_bk_fuel = zeros12();
    // month x hour-of-day electricity (kWh), so the cost layer can price
    // time-of-use tariffs exactly. TMY has no weekday structure, so TOU
    // weekday/weekend rules are weighted 5/7 : 2/7 downstream.
    var mh24 = function () {
      var a = [];
      for (var m = 0; m < 12; m++) {
        var row = [];
        for (var h = 0; h < 24; h++) row.push(0);
        a.push(row);
      }
      return a;
    };
    var mh_base_elec = mh24(),
      mh_proj_elec = mh24();
    // ghg (kg CO2e) -- combustion / electricity, per case, per month
    var m_base_comb = zeros12(),
      m_base_elecghg = zeros12(),
      m_base_ch4 = zeros12(),
      m_base_oilup = zeros12();
    var m_proj_comb = zeros12(),
      m_proj_elecghg = zeros12(),
      m_proj_ch4 = zeros12();
    // delivered-heat diagnostics
    var totalLoad = 0,
      hpDelivered = 0,
      bkDelivered = 0;
    var hpRunHours = 0,
      backupHours = 0,
      lockoutHours = 0,
      deratedHours = 0,
      heatingHours = 0;

    // hourly series (length N), for the 8760-hour chart: grid intensity is
    // captured for every hour (not just heating hours) so its own daily/
    // seasonal shape is visible independent of when the home actually heats.
    var h_ef = new Array(N).fill(0),
      h_load = new Array(N).fill(0),
      h_base_ghg = new Array(N).fill(0),
      h_proj_ghg = new Array(N).fill(0);
    // hourly PURCHASED energy (kWh input, not heat delivered): the base system's
    // fuel-or-electricity draw, the heat pump's electricity, and the backup's
    // fuel-or-electricity draw -- lets the UI aggregate energy by any key
    // (temperature bins, etc.) without re-deriving the dispatch.
    var h_base_in = new Array(N).fill(0),
      h_hp_elec = new Array(N).fill(0),
      h_bk_in = new Array(N).fill(0);

    var G2KG = 0.001; // grams -> kg

    for (var i = 0; i < N; i++) {
      var T = temps[i];
      var hour = (i % 24) + 1; // 1..24, matching the surface's convention
      var dayOfYear = Math.floor(i / 24);
      var month = monthOfDay(dayOfYear, leap);
      if (startMonth !== 1) month = ((month - 1 + (startMonth - 1)) % 12) + 1;
      var mi = month - 1;
      var season = SEASON_BY_MONTH[month];
      var tbin = tempBinLeft(T);

      var efThisHour = gridEF(opts.ef, season, hour, tbin, efMode, efLevel);
      h_ef[i] = efThisHour;

      // ---- heating load this hour (kWh delivered) ----
      var load = UA_kW_per_K * Math.max(0, Tbal - T); // kW == kWh over 1 h
      h_load[i] = load;
      if (load <= 0) continue; // above balance point: nothing runs
      heatingHours++;
      totalLoad += load;

      // ---- BASE case: same delivered heat from the incumbent system ----
      if (baseFuel === "electric") {
        var baseElec = load / baseEff; // ~= load
        m_base_elec[mi] += baseElec;
        mh_base_elec[mi][hour - 1] += baseElec;
        h_base_in[i] = baseElec;
        var baseElecGhg = efThisHour * baseElec * lineLoss * G2KG;
        m_base_elecghg[mi] += baseElecGhg;
        h_base_ghg[i] += baseElecGhg;
      } else {
        var baseFuelIn = load / baseEff;
        m_base_fuel[mi] += baseFuelIn;
        h_base_in[i] = baseFuelIn;
        var baseCombGhg = baseCombEF * baseFuelIn * G2KG;
        m_base_comb[mi] += baseCombGhg;
        h_base_ghg[i] += baseCombGhg;
        if (baseFuel === "oil") {
          m_base_oilup[mi] += oilUpstream * baseCombEF * baseFuelIn * G2KG;
        } else if (baseFuel === "gas") {
          // Methane-leak adder is pipeline-gas-specific (density/energy
          // constants below are natural gas's, not propane's); propane gets
          // no leak adder here rather than reusing gas's number -- no
          // defensible propane upstream-loss constant exists yet.
          var baseM3 = baseFuelIn / GAS_KWH_PER_M3;
          var baseCH4kg = (methanePct / 100.0) * baseM3 * GAS_KG_PER_M3;
          m_base_ch4[mi] += baseCH4kg * methaneGWP;
        }
      }

      // ---- PROJECT case: heat pump (+ backup) for the same load ----
      var ewt =
        hp.kind === "gshp"
          ? hp.ewtSeries
            ? hp.ewtSeries[i]
            : hp.ewt
          : undefined;
      var perf = hpPerformance(hp, T, ewt);

      // Control strategy decides whether the HP is allowed to run this hour and
      // how much of the load it may take.
      var hpAllowed = !perf.locked;
      if (control.strategy === "lockout") {
        // "lockout at T": the HP is simply switched off below the setpoint,
        // regardless of the capacity it could still deliver there.
        if (T < control.lockoutTemp_C) hpAllowed = false;
      }

      var hpHeat = 0,
        hpElec = 0;
      if (hpAllowed && perf.capacity_kW > 0 && perf.cop) {
        hpHeat = Math.min(load, perf.capacity_kW);
        hpElec = hpHeat / perf.cop;
        m_hp_elec[mi] += hpElec;
        mh_proj_elec[mi][hour - 1] += hpElec;
        h_hp_elec[i] = hpElec;
        var hpGhg = efThisHour * hpElec * lineLoss * G2KG;
        m_proj_elecghg[mi] += hpGhg;
        h_proj_ghg[i] += hpGhg;
        hpDelivered += hpHeat;
        hpRunHours++;
        if (perf.derated) deratedHours++;
      } else if (perf.locked || (control.strategy === "lockout" && T < control.lockoutTemp_C)) {
        lockoutHours++;
      }

      // Backup covers whatever the HP did not.
      var bkHeat = load - hpHeat;
      if (bkHeat > 1e-12 && backup.type !== "none") {
        backupHours++;
        bkDelivered += bkHeat;
        if (backup.type === "electric") {
          var bkElec = bkHeat / backup.efficiency;
          m_bk_elec[mi] += bkElec;
          mh_proj_elec[mi][hour - 1] += bkElec;
          h_bk_in[i] = bkElec;
          var bkGhg = efThisHour * bkElec * lineLoss * G2KG;
          m_proj_elecghg[mi] += bkGhg;
          h_proj_ghg[i] += bkGhg;
        } else {
          var bkFuelIn = bkHeat / backup.efficiency;
          m_bk_fuel[mi] += bkFuelIn;
          h_bk_in[i] = bkFuelIn;
          var bkCombGhg = backupCombEF * bkFuelIn * G2KG;
          m_proj_comb[mi] += bkCombGhg;
          h_proj_ghg[i] += bkCombGhg;
          if (backup.type === "gas") {
            // See base-case note above: propane leak adder omitted, not
            // reused from gas's density/energy constants.
            var bkM3 = bkFuelIn / GAS_KWH_PER_M3;
            var bkCH4kg = (methanePct / 100.0) * bkM3 * GAS_KG_PER_M3;
            m_proj_ch4[mi] += bkCH4kg * methaneGWP;
          }
        }
      } else if (bkHeat > 1e-12 && backup.type === "none") {
        // No backup: this load simply goes unmet. Track it as backup-required
        // hours so the UI can warn, but add no energy/emissions.
        backupHours++;
      }
    }

    // ---- refrigerant (annual, amortized) -- PROJECT case only ----
    var refrigerantKg = 0;
    if (lc.charge_kg && lc.refrigerantGWP) {
      var eol = lc.eolLossFrac == null ? 0.0 : lc.eolLossFrac;
      var life = lc.lifetimeYears == null ? 15.0 : lc.lifetimeYears;
      var annualLeakFrac = (lc.leakRate_frac || 0.0) + eol / life;
      refrigerantKg = lc.charge_kg * annualLeakFrac * lc.refrigerantGWP;
    }

    // ---- roll monthly -> annual, assemble output ----
    function sum(a) {
      var s = 0;
      for (var k = 0; k < a.length; k++) s += a[k];
      return s;
    }
    function monthlyRows(fields) {
      var rows = [];
      for (var mo = 0; mo < 12; mo++) {
        var r = { month: mo + 1 };
        for (var name in fields) r[name] = fields[name][mo];
        rows.push(r);
      }
      return rows;
    }

    var base_comb = sum(m_base_comb),
      base_elecghg = sum(m_base_elecghg),
      base_ch4 = sum(m_base_ch4),
      base_oilup = sum(m_base_oilup);
    var proj_comb = sum(m_proj_comb),
      proj_elecghg = sum(m_proj_elecghg),
      proj_ch4 = sum(m_proj_ch4);

    var base = {
      energy: {
        fuel_kWh: sum(m_base_fuel),
        electricity_kWh: sum(m_base_elec),
        elec_month_hour: mh_base_elec,
      },
      ghg: {
        combustion: base_comb,
        electricity: base_elecghg,
        refrigerant: 0,
        upstream_methane: base_ch4,
        upstream_oil: base_oilup,
        total: base_comb + base_elecghg + base_ch4 + base_oilup,
      },
      monthly: monthlyRows({
        fuel_kWh: m_base_fuel,
        electricity_kWh: m_base_elec,
        combustion: m_base_comb,
        electricity_ghg: m_base_elecghg,
        upstream_methane: m_base_ch4,
        upstream_oil: m_base_oilup,
      }),
    };

    var proj_elec_total = sum(m_hp_elec) + sum(m_bk_elec);
    var project = {
      energy: {
        hp_electricity_kWh: sum(m_hp_elec),
        backup_electricity_kWh: sum(m_bk_elec),
        backup_fuel_kWh: sum(m_bk_fuel),
        electricity_kWh: proj_elec_total,
        elec_month_hour: mh_proj_elec,
      },
      ghg: {
        combustion: proj_comb,
        electricity: proj_elecghg,
        refrigerant: refrigerantKg,
        upstream_methane: proj_ch4,
        upstream_oil: 0,
        total: proj_comb + proj_elecghg + refrigerantKg + proj_ch4,
      },
      monthly: monthlyRows({
        hp_electricity_kWh: m_hp_elec,
        backup_electricity_kWh: m_bk_elec,
        backup_fuel_kWh: m_bk_fuel,
        combustion: m_proj_comb,
        electricity_ghg: m_proj_elecghg,
        upstream_methane: m_proj_ch4,
      }),
      diagnostics: {
        load_kWh: totalLoad,
        hp_delivered_kWh: hpDelivered,
        backup_delivered_kWh: bkDelivered,
        seasonal_cop: sum(m_hp_elec) > 0 ? hpDelivered / sum(m_hp_elec) : null,
        heating_hours: heatingHours,
        hp_run_hours: hpRunHours,
        backup_hours: backupHours,
        lockout_hours: lockoutHours,
        derated_hours: deratedHours,
      },
    };

    return {
      base: base,
      project: project,
      hourly: {
        ef_g_per_kWh: h_ef,
        load_kW: h_load,
        base_ghg_kg: h_base_ghg,
        proj_ghg_kg: h_proj_ghg,
        base_energy_kWh: h_base_in,
        hp_elec_kWh: h_hp_elec,
        backup_energy_kWh: h_bk_in,
      },
      meta: {
        hours: N,
        ef_mode: efMode,
        ef_level_g_per_kWh: efLevel || opts.ef.reference_level_g_per_kWh,
        ef_province: opts.ef.meta ? opts.ef.meta.province : null,
        control_strategy: control.strategy,
      },
    };
  }

  return {
    simulate: simulate,
    // exported for tests / reuse
    interp: interp,
    tempBinLeft: tempBinLeft,
    lookupShape: lookupShape,
    gridEF: gridEF,
    hpPerformance: hpPerformance,
    monthOfDay: monthOfDay,
    COMBUSTION_EF_G_PER_KWH: COMBUSTION_EF_G_PER_KWH,
    GAS_KWH_PER_M3: GAS_KWH_PER_M3,
    GAS_KG_PER_M3: GAS_KG_PER_M3,
  };
});

