# Heat Pump Energy & GHG Comparison Tool — Project Plan

**Goal:** A static web tool showing the energy and GHG impact of replacing existing home space
heating (gas furnace, oil furnace, electric baseboards) with an air-source or ground-source heat
pump, for a standard year, in selected Canadian cities (ON / QC / AB).

**Status:** Phase 1a done — hourly generation by fuel for ON (IESO, 2021–2025) and AB (AESO,
2020–Jul 2025) fetched, fuel-mapped and validated against NIR Annex 7; QC flat-EF constants
written (`heatpump/data/processed/grid_qc.json`). See `heatpump/METHODOLOGY.md`. The AESO
retrieval-path risk is resolved: direct CSVs on aeso.ca + CSD fuel grouping + manual
coal-conversion table. Next: `build_grid_ef.py` (hourly average + marginal EF, temp×hour×season
surface, NIR ±15% intensity check).

---

## Feasibility verdict

Fully doable as a GitHub repo + GitHub Pages static site (matches the existing Ottawa_Visuals
pattern: project folder + top-level HTML page). Key architectural decision:

- **All heavy data work happens offline in Python** (grid emissions, weather, NEEP parsing,
  archetype calibration) and is baked into compact JSON files (~50–200 KB per city).
- **The browser runs the actual simulation.** 8,760 hours × simple arithmetic per scenario is
  milliseconds in JavaScript, so every input change recomputes instantly. No backend, no
  precomputed scenario matrix.
- All data is static or annual — no scheduled jobs needed. Manual yearly refresh is fine
  (GitHub Actions throttling is irrelevant here).

---

## Methodology decisions (the things worth getting right)

### 1. Average vs. marginal grid emissions — the biggest decision
Hourly generation by fuel gives *average* intensity, but a heat pump is *new load*, served by the
*marginal* generator. In Ontario the winter margin is almost always gas (~400–550 g CO₂e/kWh)
while the average is ~25–40 g/kWh — a 10–15× difference that flips the ASHP-vs-gas answer.
Quebec is near-zero either way; Alberta's average and margin are both gas-dominated.

**Decision: expose both as a UI toggle** ("average intensity" / "marginal intensity"). Marginal
estimated simply: gas CCGT intensity whenever gas generation is nonzero/ramping, else average.

### 2. TMY normalization trap
Grid intensity is not a function of temperature alone — hour of day, season, hydro conditions
and outages matter. Binning EF purely by temperature and applying TMY smears morning-peak gas
hours into mild afternoons. Fixes, in order of preference:

1. Bin historical EF by **temperature (2 °C bins) × hour-of-day × season** using 3–5 years of
   history, then apply to the TMY temperature series.
2. And/or run 3–5 actual historical years concurrently (weather and grid from the same hours,
   preserving their correlation) and report the range. More defensible; shows honest variance.

Do both if feasible: TMY gives the "typical" headline number, historical years give the band.

### 3. NEEP data — watch the cold end
The ccASHP list rates capacity/COP at 47/17/5 °F (some units at −13 °F), at min/rated/max.
Ottawa's design temperature (~−25 °C) is below the coldest rated point, so extrapolation does
real work:

- Extrapolate **capacity linearly** below the coldest rated point.
- **Floor the COP** (e.g., coldest rated COP − 0.3).
- Respect each unit's **minimum operating temperature** — zero output below it (compressor lockout).
- Apply a **defrost penalty** (~7% COP derate between roughly −7 and +4 °C) — omitting it
  flatters ASHPs exactly where they run the most hours.
- Cycling above the balance point: use min-capacity COP when load < min capacity (simple, adequate).

### 4. GSHP — no NEEP equivalent
Model via **entering water temperature (EWT)**: undisturbed ground temperature per city
(~8–10 °C Ottawa/Toronto/Montreal, ~4–6 °C Edmonton/Calgary) with a modest seasonal drawdown,
then COP as a function of EWT from AHRI / ISO 13256 rating points for 2–3 representative units.
No borefield simulation.

### 5. Load model
`Load(h) = UA × max(0, T_balance − T_out(h))` — standard and defensible.

- UA from ERS (EnerGuide) heat-loss data; T_balance ~16–18 °C (lower for tighter homes).
- Calibrate so annual total matches ERS heating consumption per archetype/vintage.
- Cross-check shape against the NRCan Toronto 4-archetype load profile report.
- **Exclude DHW** explicitly. Ignore setbacks and solar gains — the balance point absorbs them.

### 6. Lifecycle terms — sliders, not baked-in assumptions
These are the most contested numbers; make them user-adjustable with sensible defaults:

- **Refrigerant:** charge (kg) × annual leak rate (2–6 %/yr) + end-of-life loss (~15–100 % of
  charge, amortized) × GWP. GWP set toggle (AR5 / AR6): R-410A ~1924/2256, R-32 ~677/771,
  R-454B ~467, R-290 ~3.
- **Upstream methane:** slider 0–3 % of gas throughput (ECCC NIR implies ~0.5–1 %) × CH₄ GWP
  (~28–30). Analogous upstream factor for heating oil.
- **Grid line losses:** ~5 % on delivered electricity.

### 7. Scoping
- Offer **3–4 representative heat pump tiers** (cold-climate premium / mid / baseline + GSHP)
  built from real NEEP units, plus a "custom" mode where the user enters their own unit's
  47/17/5 °F points. 90 % of the value for 10 % of the wrangling.
- **Check NEEP redistribution terms** — publish derived curves for a handful of units with
  attribution rather than republishing the list.
- Build the thin slice first: **Ontario + Ottawa/Toronto + ASHP only**, end-to-end, before
  adding QC, AB, and GSHP.

---

## Data sources

| Data | Source | Notes |
|---|---|---|
| ON hourly generation | IESO public reports (reports-public.ieso.ca), Generator Output and Capability | Hourly per generator, years of history; fuel mapping straightforward. Intertie flows available if consumption-based EF wanted. |
| QC grid EF | Flat annual EF | HQ is >99 % hydro/wind: ~1.5 g/kWh production-based, ~35 g/kWh counting winter imports. Skip the hourly pipeline; document the choice. |
| AB hourly generation | AESO hourly metered volumes per asset (public) | **Verified:** direct CSV at aeso.ca/assets/Uploads/data-requests/ (2001–Jul 2025); asset→fuel from live CSD report + manual coal-conversion dates. Box-hosted CSD historical dataset not scriptable. |
| Hourly weather | ECCC bulk CSV API | Fetch pattern already exists in `Weather/ottawa_weather_fetch_hourly.py`. |
| TMY | CWEC2020 EPW files, ECCC engineering climate datasets | Free. |
| Building archetypes | ERS/EnerGuide anonymized database, open.canada.ca (per province) | UA + annual heating consumption. |
| Load profile shapes | NRCan Toronto 4-archetype report | Cross-check only. |
| ASHP performance | NEEP ccASHP product list | 47/17/5 °F (−13 °F for some), min/rated/max. |
| Combustion EFs | ECCC National Inventory Report | Gas CCGT/peakers ~490–550 g/kWh; furnace fuels per NIR Part 2. |

---

## Repo layout

```
Energy/
  heatpump/
    pipeline/          # Python: fetch + process, run locally or on the Pi
      fetch_ieso.py, fetch_aeso.py, fetch_weather.py,
      build_grid_ef.py, build_archetypes.py, build_hp_curves.py
    data/raw/          # gitignored bulk downloads
    data/processed/    # committed compact JSON, ~50–200 KB per city
    app/
      engine.js        # pure simulation function, no DOM, no dependencies
      engine.test.js
    METHODOLOGY.md     # every assumption, factor, and source — written as you go
heatpump.html          # the tool page
```

---

## Phases

1. **Grid emissions pipeline (Ontario first).** IESO 3–5 yr hourly gen per generator → fuel
   mapping → NIR EFs → hourly average EF + marginal series. Join ECCC hourly temperature, build
   the temp × hour × season EF surface. Validate against published annual ON intensity (±15 %).
   Output: one JSON per province.
2. **Weather & TMY.** Hourly history + CWEC EPW for launch cities (Ottawa, Toronto, Montreal,
   Calgary/Edmonton). Output: TMY series + 3–5 historical years per city.
3. **Equipment curves.** Parse NEEP, select representative units per tier, build capacity/COP
   piecewise curves with documented extrapolation, defrost derate, min-operating-temp cutoff.
   GSHP curves vs EWT. Output: small curves JSON + sanity plots.
4. **Archetypes.** From ERS per city: UA, balance point, annual heating load for 3–4 archetypes
   (pre-1980 detached, 1980–2005 detached, post-2005 detached, townhouse). Cross-check vs NRCan.
5. **Simulation engine (core).** Pure JS function
   `simulate(city, archetype, baseCase, hpConfig, backupConfig, controlStrategy, lifecycleParams)`.
   Per hour: load → HP capacity & COP at T → dispatch per control strategy → backup → emissions.
   Thin Python mirror used only in tests. Unit tests for balance-point crossover, lockout
   temperature, backup switchover.
6. **UI.** Static page matching site style: input panel; outputs — annual energy by source,
   GHG comparison bar (combustion / electricity / refrigerant / upstream methane), a
   **load-vs-capacity chart across temperature** (the one chart that explains the whole model),
   monthly breakdowns, "show assumptions" expandable citing METHODOLOGY.md.
7. **Validation & writeup.** Compare annual results vs published benchmarks (NRCan ASHP studies,
   RAP/Pembina ON & AB analyses); document deltas.

**Model choice for Claude Code:** use Opus (or strongest available) for Phases 1, 3, 5 —
methodology-heavy, errors are silent. Sonnet is fine for 2, 4, 6.

---

## Paste-able Claude Code prompts

### Phase 1 — Ontario grid EF pipeline
> In Energy/heatpump/pipeline, build a Python pipeline that downloads IESO Generator Output and
> Capability public reports for 2021–2025, maps each generator to its fuel type, and computes
> hourly Ontario grid emissions intensity (g CO₂e/kWh) using ECCC NIR combustion factors. Also
> compute a marginal-intensity series: gas CCGT intensity when gas generation is nonzero, else
> the average. Join with ECCC hourly Ottawa+Toronto temperature (reuse the fetch pattern from
> Weather/ottawa_weather_fetch_hourly.py) and output (a) the full hourly series and (b) an EF
> lookup binned by temperature (2°C bins) × hour-of-day × season, as JSON in data/processed/.
> Validate: annual average must land within published IESO/ECCC Ontario intensity ±15%; print
> the comparison. Document every factor and source in METHODOLOGY.md.

### Phase 3 — Heat pump curves
> Here is the NEEP ccASHP spreadsheet [path]. Build build_hp_curves.py that extracts capacity
> and COP at 47/17/5/−13 °F (min/rated/max) for these unit IDs [list], converts to SI, and
> produces piecewise-linear capacity(T) and COP(T) curves from −30 °C to 18 °C per unit. Below
> the coldest rated point: extrapolate capacity linearly, hold COP at a floor of (coldest COP
> − 0.3), and set output to zero below the unit's minimum operating temperature. Apply a defrost
> derate of 7% to COP between −7 and +4 °C. Add a GSHP curve set parameterized by entering water
> temperature. Output curves JSON + a matplotlib sanity plot per unit. Write tests asserting
> monotonicity of capacity and COP above −15 °C.

### Phase 5 — Simulation engine
> Write Energy/heatpump/app/engine.js: a pure function that simulates one year hourly. Inputs:
> TMY temperature array, archetype {UA, Tbalance}, base case {fuel, efficiency}, heat pump
> curves JSON, backup {type, efficiency}, control strategy ('lockout at T' or 'switch when load
> > capacity'), lifecycle params {refrigerant GWP, charge, leak rate, methane leak %, line loss
> %}, hourly EF lookup. Output: annual + monthly energy by source and GHG by category for base
> and project case. No DOM code, no dependencies. Then write engine.test.js with hand-computed
> cases: (1) constant −10 °C hour where load exceeds HP capacity with electric backup, (2) hour
> above balance point produces zero, (3) lockout strategy ignores HP capacity entirely below the
> setpoint. Also generate a Python mirror in pipeline/validate_engine.py that runs the same
> cases and asserts identical results to 4 decimals.

(Phases 2, 4, 6, 7 prompts to be written when reached — they follow the same pattern: explicit
inputs/outputs, file paths, and validation criteria.)
