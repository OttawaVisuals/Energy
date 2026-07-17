/*
 * engine.test.js -- hand-computed unit tests for engine.simulate().
 *
 * Dependency-free: run with `node engine.test.js` (exit 0 = pass). Every
 * EXPECTED value below is computed by hand in the comments and is the SAME
 * number asserted by the Python mirror pipeline/validate_engine.py, so the two
 * languages are pinned to one shared source of truth (identical to 4 decimals).
 *
 * Synthetic rig (clean arithmetic, not the real JSON):
 *   curve      cap_frac = 0.5, COP = 2.5 at every T, min-op -30 C
 *   nominal    10 kW      -> capacity = 5 kW at any operating temperature
 *   archetype  UA = 250 W/K (0.25 kW/K), Tbalance = 18 C
 *   baseCase   gas, efficiency 0.8
 *   backup     electric, efficiency 1.0
 *   EF surface global shape [1,1], reference level [100 avg, 500 marg] g/kWh
 *   line loss  5%   (factor 1.05)
 */

var E = require("./engine.js");

// ---- synthetic fixtures ----
var CURVE = {
  T_C: [-30, 15],
  cap_frac_of_rated47: [0.5, 0.5],
  COP: [2.5, 2.5],
};
var EF = {
  meta: { thin_bin_min_hours: 20, province: "TEST" },
  reference_level_g_per_kWh: [100, 500],
  fine: {},
  coarse_ts: {},
  coarse_t: {},
  global: [1.0, 1.0, 1],
};
function baseOpts(overrides) {
  var o = {
    tempSeries: [-10],
    archetype: { UA_W_per_K: 250, Tbalance_C: 18 },
    baseCase: { fuel: "gas", efficiency: 0.8 },
    hp: { curve: CURVE, nominalCap_kW: 10, minOpTemp_C: -30, kind: "ashp" },
    backup: { type: "electric", efficiency: 1.0 },
    control: { strategy: "load-exceeds-capacity" },
    lifecycle: { lineLossPct: 5 },
    ef: EF,
    efMode: "average",
  };
  for (var k in overrides || {}) o[k] = overrides[k];
  return o;
}

// ---- tiny assertion harness ----
var failures = 0;
function approx(name, got, want) {
  var ok = Math.abs(got - want) < 5e-5;
  if (!ok) {
    failures++;
    console.error("  FAIL " + name + ": got " + got + " want " + want);
  } else {
    console.log("  ok   " + name + " = " + got);
  }
}

// ==========================================================================
// Case 1: constant -10 C hour, load EXCEEDS heat-pump capacity, electric backup.
//   load  = 0.25 * (18 - (-10)) = 7.0 kWh delivered
//   cap   = 5.0 kW  -> HP delivers 5.0, backup delivers 2.0
//   HP elec      = 5.0 / 2.5 = 2.0 kWh
//   backup elec  = 2.0 / 1.0 = 2.0 kWh   (total site elec 4.0)
//   proj elec GHG (avg)  = 100 * 4.0 * 1.05 / 1000 = 0.42 kg
//   proj elec GHG (marg) = 500 * 4.0 * 1.05 / 1000 = 2.10 kg
//   base gas fuel = 7.0 / 0.8 = 8.75 kWh ; base combustion = 181*8.75/1000 = 1.58375 kg
// ==========================================================================
console.log("Case 1: -10 C, load > capacity, electric backup");
var r1 = E.simulate(baseOpts());
approx("load_kWh", r1.project.diagnostics.load_kWh, 7.0);
approx("hp_delivered_kWh", r1.project.diagnostics.hp_delivered_kWh, 5.0);
approx("backup_delivered_kWh", r1.project.diagnostics.backup_delivered_kWh, 2.0);
approx("hp_electricity_kWh", r1.project.energy.hp_electricity_kWh, 2.0);
approx("backup_electricity_kWh", r1.project.energy.backup_electricity_kWh, 2.0);
approx("project electricity_kWh", r1.project.energy.electricity_kWh, 4.0);
approx("project ghg.electricity (avg)", r1.project.ghg.electricity, 0.42);
approx("base fuel_kWh", r1.base.energy.fuel_kWh, 8.75);
approx("base ghg.combustion", r1.base.ghg.combustion, 1.58375);
approx("hp_run_hours", r1.project.diagnostics.hp_run_hours, 1);
approx("backup_hours", r1.project.diagnostics.backup_hours, 1);

var r1m = E.simulate(baseOpts({ efMode: "marginal" }));
approx("project ghg.electricity (marginal)", r1m.project.ghg.electricity, 2.1);

// ==========================================================================
// Case 2: hour ABOVE the balance point (20 C > 18 C) -> everything is zero.
// ==========================================================================
console.log("Case 2: +20 C, above balance point -> zero");
var r2 = E.simulate(baseOpts({ tempSeries: [20] }));
approx("load_kWh", r2.project.diagnostics.load_kWh, 0.0);
approx("heating_hours", r2.project.diagnostics.heating_hours, 0);
approx("project electricity_kWh", r2.project.energy.electricity_kWh, 0.0);
approx("project ghg.total", r2.project.ghg.total, 0.0);
approx("base fuel_kWh", r2.base.energy.fuel_kWh, 0.0);
approx("base ghg.total", r2.base.ghg.total, 0.0);

// ==========================================================================
// Case 3: LOCKOUT strategy at -5 C, hour at -10 C (below setpoint).
//   HP is switched off entirely even though 5 kW of capacity is available.
//   All 7.0 kWh -> electric backup ; HP elec = 0.
//   proj elec GHG = 100 * 7.0 * 1.05 / 1000 = 0.735 kg
// ==========================================================================
console.log("Case 3: lockout at -5 C, T=-10 -> HP ignored, all to backup");
var r3 = E.simulate(
  baseOpts({ control: { strategy: "lockout", lockoutTemp_C: -5 } })
);
approx("hp_delivered_kWh", r3.project.diagnostics.hp_delivered_kWh, 0.0);
approx("hp_run_hours", r3.project.diagnostics.hp_run_hours, 0);
approx("lockout_hours", r3.project.diagnostics.lockout_hours, 1);
approx("backup_delivered_kWh", r3.project.diagnostics.backup_delivered_kWh, 7.0);
approx("backup_electricity_kWh", r3.project.energy.backup_electricity_kWh, 7.0);
approx("project ghg.electricity", r3.project.ghg.electricity, 0.735);

// ==========================================================================
// Case 4: refrigerant term (annual, amortized). charge 3 kg, 5%/yr leak,
//   80% end-of-life loss over 15-yr life, GWP 2256 (R-410A AR6).
//   annual leak frac = 0.05 + 0.80/15 = 0.1033333
//   refrigerant GHG  = 3 * 0.1033333 * 2256 = 699.36 kg
// ==========================================================================
console.log("Case 4: refrigerant amortization");
var r4 = E.simulate(
  baseOpts({
    lifecycle: {
      lineLossPct: 5,
      charge_kg: 3,
      leakRate_frac: 0.05,
      eolLossFrac: 0.8,
      lifetimeYears: 15,
      refrigerantGWP: 2256,
    },
  })
);
approx("project ghg.refrigerant", r4.project.ghg.refrigerant, 699.36);

// ==========================================================================
// Case 5: upstream methane on the BASE gas throughput. Force a clean 100 kWh
//   of gas input by choosing load 80 kWh (eff 0.8 -> 100 kWh fuel) via a big UA.
//   100 kWh -> 100/10.55 = 9.478673 m3 -> *0.68 = 6.445498 kg gas
//   2% leak -> 0.128910 kg CH4 -> *28 = 3.609479 kg CO2e
// ==========================================================================
console.log("Case 5: upstream methane on base gas");
// UA chosen so load = 80 kWh at -10 C: UA*(18+10)=80 -> UA = 80/28 kW/K = 2857.142857 W/K
var r5 = E.simulate(
  baseOpts({
    archetype: { UA_W_per_K: (80 / 28) * 1000, Tbalance_C: 18 },
    lifecycle: { lineLossPct: 5, methaneLeakPct: 2, methaneGWP: 28 },
  })
);
approx("base fuel_kWh", r5.base.energy.fuel_kWh, 100.0);
approx("base ghg.upstream_methane", r5.base.ghg.upstream_methane, 3.609479);

// ==========================================================================
// Case 6: below-lock-out "derate" mode (ROADMAP item 9 workstream E).
//   Curve   T_C [-10,0,15], cap_frac [0.5,0.7,1.0], COP [2.0,3.0,4.0], min-op -10.
//   Coldest defined point (-10 C, cap 0.5, COP 2.0); coldest capacity segment
//   slope = (0.7-0.5)/(0-(-10)) = 0.02/C; COP floor 2.0.
//   Hour at -20 C (10 C below the published minimum):
//     load       = 0.25*(18+20) = 9.5 kWh
//     derate cap = 0.5 + 0.02*(-20+10) = 0.3 frac -> 10 kW * 0.3 = 3.0 kW
//     HP delivers min(9.5,3.0)=3.0 ; HP elec = 3.0/2.0 = 1.5 kWh
//     lockout_hours 0, derated_hours 1, hp_run 1 ; backup delivers 6.5.
//   Default 'hard' mode on the SAME curve/hour: HP locked out, delivers 0.
// ==========================================================================
console.log("Case 6: below-lock-out derate mode");
var CURVE_D = { T_C: [-10, 0, 15], cap_frac_of_rated47: [0.5, 0.7, 1.0], COP: [2.0, 3.0, 4.0] };
var r6 = E.simulate(
  baseOpts({
    tempSeries: [-20],
    hp: { curve: CURVE_D, nominalCap_kW: 10, minOpTemp_C: -10, kind: "ashp", belowLockout: "derate" },
  })
);
approx("derate hp_delivered_kWh", r6.project.diagnostics.hp_delivered_kWh, 3.0);
approx("derate hp_electricity_kWh", r6.project.energy.hp_electricity_kWh, 1.5);
// guard: default hard-stop on the same curve/hour locks the compressor out.
var r6h = E.simulate(
  baseOpts({
    tempSeries: [-20],
    hp: { curve: CURVE_D, nominalCap_kW: 10, minOpTemp_C: -10, kind: "ashp" },
  })
);
approx("hard hp_delivered_kWh", r6h.project.diagnostics.hp_delivered_kWh, 0.0);

// ---- summary ----
if (failures) {
  console.error("\n" + failures + " assertion(s) FAILED");
  process.exit(1);
} else {
  console.log("\nAll engine.js assertions passed.");
}
