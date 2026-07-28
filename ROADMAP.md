# Energy Suite — Project Tracker & Roadmap

The single source of truth for what's shipped, what's in flight, and what's next.
Updated **2026-07-27** (heat-pump load-model rebuild started: city design temperatures step shipped; CCHP Challenge screen added; earlier 2026-07-24 pass verified against the repo and commit history — GitHub Actions run status not directly queried, inferred from bot-authored commits).

- 📦 Full record of completed items (prompts + build notes): [docs/archive/ROADMAP_COMPLETED.md](docs/archive/ROADMAP_COMPLETED.md)
- 🗺️ Visual status page: [project-atlas.html](project-atlas.html) — <https://ottawavisuals.github.io/Energy/project-atlas>
- 📖 Main readme (all links): [README.md](README.md)

---

## 📊 Status board

### Shipped & live ✅

| Tool | Live | Docs | Notes |
|---|---|---|---|
| 🏠 **Retrofit Explorer** | [/retrofits](https://ottawavisuals.github.io/Energy/retrofits) | [docs/RETROFITS.md](docs/RETROFITS.md) | v1 + post-launch additions, audit funnel, pairing fixes (matched 538k → 1.37M → 1.45M), bill card, visual polish |
| 📈 **Retrofit Insights** | [/retrofit-insights](https://ottawavisuals.github.io/Energy/retrofit-insights) | [docs/archive/ROADMAP_COMPLETED.md](docs/archive/ROADMAP_COMPLETED.md) (item 13) | national big-picture page: leaderboards, choropleth, success analysis, climate/equity linkage, missed-opportunity ranking, program-era timeline; shipped 2026-07-19 |
| 🏡 **New Homes Explorer** | [/newhomes](https://ottawavisuals.github.io/Energy/newhomes) | [docs/NEWHOMES.md](docs/NEWHOMES.md) | EnerGuide new-construction slice (plan/as-built); shipped 2026-07-15; pipeline reworked 2026-07-22/23 (P/N column-fill, `ers_pn_column_fill.csv`) |
| 📊 **CEUD Explorer** | [/ceud](https://ottawavisuals.github.io/Energy/ceud) | [docs/CEUD.md](docs/CEUD.md) | all 5 sectors live |
| 🏗️ **Construction Tracker** | [/construction](https://ottawavisuals.github.io/Energy/construction) | [docs/CONSTRUCTION.md](docs/CONSTRUCTION.md) | monthly auto-refresh; **first scheduled run 2026-07-20 — watch it go green** |
| 🌍 **Ottawa Geothermal Map** | [/Geothermal/output/](https://ottawavisuals.github.io/Energy/Geothermal/output/) | [Geothermal/README.md](Geothermal/README.md) | v2 complete: conductivity sensitivity, drilling difficulty, segment suitability |
| 🔥 **Heat Pump Explorer** | [/heatpump](https://ottawavisuals.github.io/Energy/heatpump) | [HeatPump/METHODOLOGY.md](HeatPump/METHODOLOGY.md) | v2 complete: 14 cities, weather-year lens, sizing sweep, lifecycle sourcing, operating costs |
| ⚡ **Grid Dashboard** | [/grid](https://ottawavisuals.github.io/Energy/grid) | [docs/GRID.md](docs/GRID.md) | ON/AB generation mix + emissions intensity, average-vs-marginal explainer, Advanced typical-day-by-season panel; shipped 2026-07-24 |
| 🚪 **Landing page** | [/](https://ottawavisuals.github.io/Energy/) | — | one card per tool, cross-linked from every tool's header (`↳ All tools`); shipped 2026-07-24 |
| 🗺️ **Project Atlas** | [/project-atlas](https://ottawavisuals.github.io/Energy/project-atlas) | — | internal status/assumptions page — keep in sync when items ship |

**Data layers behind the tools (all built, all auto-refreshing):**

| Layer | Refresh | Status |
|---|---|---|
| Energy prices (`prices_json/`) | monthly, 3rd — `rates-refresh.yml` | ✅ built; first scheduled run **2026-08-03** (not yet happened) |
| Grid mix ETL (`grid_json/`) | weekly, Mon — `grid-refresh.yml` | ✅ first scheduled run went **green 2026-07-13** |
| AHRI cert lookup (`lookup/ahri_numbers.json`) | weekly, Mon 15:00 UTC — `ahri-refresh.yml` | ✅ shipped 2026-07-22; replaces manual `build_ahri_lookup.py` reruns |
| Construction data (`construction_json/`) | monthly, 20th — `construction-refresh.yml` | ✅ first scheduled run confirmed **green 2026-07-20** |
| Utility rates for bill cards (`utility_rates_reference.json`) | manual (`Python/utility_rates_reference.py`) | ✅ shipped 2026-07-18 |

### In flight 🔨

| Project | Progress | Next step |
|---|---|---|
| 🏙️ **Ottawa Case Study** (heat demand → electrification → grid) | `██████░░░` Phases 0–3 of 6 done | **Phase 4:** aggregate to 500 m grid + feeders, apply coincidence factor → [item 7](#7-ottawa-case-study--heat-demand-electrification-grid-in-progress) |

### Queued 🆕

- ♨️ **Heat pump tool — Phase 3c bucket rework** (spec done, curves outstanding).
  Equipment selection rebuilt on **AHRI as sampling frame / manufacturer
  datasheets as measurement**: a 3×3 grid of COP @ 5 °F × capacity maintenance,
  36 representatives chosen by real Canadian installation frequency from
  439,975 EnerGuide record appearances. Spec:
  [HeatPump/TIER_SPEC.md](HeatPump/TIER_SPEC.md). **Next step:** hand-fetch the
  6 priority units' performance data (datasheets give capacity + lockout; NEEP
  needed for power/COP), then rebuild `hp_curves.json` and rewire
  `heatpump.html`'s tier selector.

- 🌡️ **Heat pump tool — heating-load model rebuild** (started 2026-07-27,
  step 1 shipped). The load model is being rebuilt from scratch so the design
  load and load curve are explainable and defensible end to end.

  **Step 1 done: city design temperatures from the station HOT2000 actually
  used.** `HeatPump/pipeline/build_city_design_temps.py` →
  `data/processed/city_design_temps.json`. The raw ERS files carry `WEATHERLOC`
  and `WTHDATA`, which were never carried into `ers_web_*.parquet`; recovering
  them lets each home's `EGHDESHTLOSS` be divided by the design temperature it
  was actually computed at, instead of the 2.5%-ile proxy in
  `build_archetypes.py`. Scanned 1,430,221 matched pairs — **100% matched, 0
  unmatched** — and joined to NBC Appendix C via the new committed
  `HeatPump/reference/nbc_station_design_temps.csv`. **84 cities, 1,020,246
  homes (71.3%), zero homes without a design temperature.** Method + caveats in
  [HeatPump/METHODOLOGY.md](HeatPump/METHODOLOGY.md) "City design temperatures
  from HOT2000 weather stations".

  **Step 2 done: archetypes rebuilt on NRCan's published loads.**
  `HeatPump/pipeline/build_archetypes_nrcan.py` →
  `data/processed/archetypes_nrcan.json`. Decision taken 2026-07-27: **stop
  fitting a balance point to our own data and take both quantities from one
  published source** — NRCan CanmetENERGY *Cold-Climate ASHPs*
  (Cat. M154-149/2022E-PDF) Table 1 + Figure 1. Because each NRCan archetype is
  one house relocated to 16 cities, regressing the 16 published peaks against
  the 16 NBC design temperatures recovers UA and T_balance per archetype
  (R² 0.90–0.93), and independently reproduces the Figure 1 intercepts within
  0.5 °C for archetypes A and B — which also **settles that Table 1 is a
  design-condition load, not a TMY-series peak** (a 16% difference in UA).
  UA is taken **per city** from the published peak, preserving a real
  wind-infiltration effect the single fit discards (archetype A: 389 W/K in
  St. John's vs 291 in Kamloops). **Scope is NRCan's 16 cities for now**;
  TMY covers 11 of them. Full method + limitations in
  [HeatPump/METHODOLOGY.md](HeatPump/METHODOLOGY.md) "NRCan-published archetypes".

  **Steps outstanding:**
  1. **Wire `heatpump.html` onto `archetypes_nrcan.json`** — the page still
     loads the old ERS `archetypes.json`. Archetype set changes (townhouse/row
     out, Net-Zero-Ready in), the city list changes to NRCan's 11 with TMY, and
     `autoSize()` / the "which is my home?" helper both reference floor area,
     which NRCan does not publish. **Nothing is live yet.**
  2. **Commit an explicit peak-load field on a stated percentile** (1% or 2.5%
     coldest hour) rather than the single coldest TMY hour.
  3. **Decide whether to credit the night setback when sizing.** ERS SOC drops
     to 18 °C for 8 h and the sizing hour falls inside it; CSA F280 takes no
     setback credit because the system must recover. Simulate with, size without,
     and say so.
  4. **Display gross vs net** design load with both definitions stated, and say
     which one sizes the equipment.
  5. **Send the NRCan question list.** All open EnerGuide/HOT2000 questions
     across every ERS-based tool are now consolidated in
     [docs/ENERGUIDE_QUESTIONS.md](docs/ENERGUIDE_QUESTIONS.md) — the blocking
     one is the four monthly HOT2000 fields (`energy_loadGJ`, `solar_gainsGJ`,
     `internal_gainsGJ`, `aux_energy_GJ`) or, failing that, the SOC solar gain
     per city. Answering it would let us return to ERS-derived archetypes and
     recover the population sample, floor areas, local construction practice
     and the townhouse archetype. Also collects the design-temperature /
     weather-library questions, `EGHDESHTLOSS` semantics, `HPCAP` vs
     `CCASHPCAP`, `ERSRating=0`, the pairing-key question, and the ON/QC NBC
     tier gap.

  **Superseded:** the ERS design-temperature rewiring of `build_archetypes.py`
  (step 1's original purpose). `city_design_temps.json` is still the input for
  any future ERS-based work, and the 84-city table stands.

  **Two engine bugs to fix during the rebuild** (found 2026-07-27, not yet
  fixed): `buildOpts()` gives **propane backup 100% efficiency**
  (`gas?0.95:oil?0.85:1.0` has no propane branch), and `simulate()` applies the
  **upstream-methane term to propane using natural-gas properties**
  (`GAS_KWH_PER_M3` 10.55, `GAS_KG_PER_M3`, CH₄ GWP) on both baseline and backup
  sides. Also open, lower priority: no part-load/cycling degradation (curves are
  steady-state, so mild hours are optimistic) and no defrost penalty.

- 🇺🇸 **US DOE CCHP Challenge screen — analysis done 2026-07-27, not yet on any
  page.** `HeatPump/pipeline/screen_cchp.py` screens all 15,148 models against
  the [Challenge specifications](https://www.energy.gov/cmei/buildings/cchp-technology-challenge-specifications)
  Table II-3. Headline: **4 models, 8 of 439,975 ERS appearances (0.00%)** clear
  every checkable criterion, and three of the four sit *exactly* on the
  threshold. 34.4% of the base is `out_of_scope` (<24,000 Btu/h, which the
  Challenge deliberately does not address). **Decision outstanding: where and
  how to surface this** — it does not fit the 3×3 tier grid (no qualifying unit
  is a cell representative), so it wants its own framing. Method in
  [HeatPump/METHODOLOGY.md](HeatPump/METHODOLOGY.md) "US DOE Cold Climate Heat
  Pump Challenge screen"; caveats in
  [HeatPump/TIER_SPEC.md](HeatPump/TIER_SPEC.md) §6.7.

- 🧾 **Reproducibility gap: two Phase 3c inputs cannot be regenerated**
  (found 2026-07-27). `HeatPump/data/interim/hp_units_joined.csv` — the joined
  15,148-model universe that the bucket grid *and* the CCHP screen both read —
  **has no producer script anywhere in the repo**; it was built ad hoc in an
  earlier session. And `lookup/ahri_numbers.json`, the AHRI scrape itself, is
  not on local disk. Both are gitignored, so the "process, not bytes" rule does
  not currently hold for them: losing `hp_units_joined.csv` would strand Phase
  3c. **Fix:** write the join as a real pipeline step, and confirm the weekly
  `ahri-refresh.yml` still restores `lookup/`.

- 🔧 **Tech debt: consolidate the two heat-pump engines** (deferred, do later).
  `HeatPump/app/engine.js` and the copy inlined verbatim in `heatpump.html`
  (~line 743 onward) are the same ~600-line engine maintained twice — any logic
  change has to be applied to both by hand or they silently diverge, and only
  the inlined copy is what users actually run. Target: one source of truth
  (build step that injects `app/engine.js` into the page, or ship it as a
  separate `<script>` and drop the inline copy), keeping `engine.test.js` and
  `pipeline/validate_engine.py` pointed at it. **Not part of the current
  heat-pump-selection rework — flagged now, scheduled later.**

Otherwise nothing queued — next up is finishing the in-flight Ottawa Case Study
(below), then picking from the project ideas.

---

## 🎯 What's next — recommended order

1. **Ottawa Case Study Phases 4 → 5 → 6** (item 7). The only thing left on the
   board. Phase 4 is the defensibility step (coincidence factor — Phase 3
   proved the undiversified sums are upper bounds); Phase 6 is the public
   narrative page the whole project builds toward.
2. Once Phase 6 ships, pick from **Project ideas** below — nothing queued
   ahead of it.

**Site-wide polish pass — 2026-07-24:**

- [x] Social previews: `assets/og/*.png` (1200×630, generated by
      `Python/build_og_images.py`) + `og:image`/`og:url`/`twitter:card` on all
      nine pages. Rerun the script when a page's title or pitch changes.
- [x] Google Fonts made non-blocking everywhere (`rel="preload"` + onload swap,
      `<noscript>` fallback).
- [x] Analytics (`G-3QLS1Q554N`) now on all nine pages; the loader on
      retrofits.html had been requesting a placeholder `G-XXXXXXXXXX` ID.
- [x] `retrofits.html` CSS/JS extracted to `assets/retrofits.css` +
      `assets/retrofits.js` — repeat-visit transfer 93 KB → 26 KB gzipped.
- [x] New Homes: explicit empty state for the code-tier section, which was
      showing a heading over blank space in ON/QC (0 of 70,568 ON evaluations
      carry a tier). See [docs/NEWHOMES.md](docs/NEWHOMES.md).
- [x] Retrofit Explorer: new aggregate "Where the heat escapes" chart, the
      per-FSA/province twin of the per-home heat-loss breakdown.
- [x] **Pairing Gate A recovered — matched sample 1,369,305 → 1,451,433
      (+82,128, +6.0%).** `build_pairs_index()` now reduces each home to
      oldest-D + newest-E instead of requiring exactly one of each. The pair
      stage gained the predicted +148,155; the structural/floor-area gates then
      removed proportionally more of the recovered multi-audit homes (they span
      longer gaps), netting +82,128. Matched share of homes with both a D and an
      E audit rises 84.0% → 89.1%. Headline figures barely move — median saving
      stays 20%, whole-home heat loss −12% — which is the evidence the recovered
      homes are representative rather than a distortion. Full chain rerun and all
      JSON regenerated. Previous build artifacts backed up at `C:\ERS\web_prev\`.
- [ ] **Gate B — still open, and the ordering argument favours changing it.**
      84,755 pairs are dropped for "E not dated after D". None have unparseable
      dates and 99.4% are exact same-day ties; `ENTRYDATE` is month-precision
      throughout (all first-of-month). Since `EVALTYPE` already says which audit
      is the initial and which the follow-up, **the date test is only a guard
      against genuine reversals** — so `E > D` → `E >= D` would be correct and
      recovers ~84,253, leaving the 502 real reversals excluded. Not applied:
      surfaced as an open question on the page for the EnerGuide team to confirm
      first. (An earlier framing in this session — that same-day ties carry "no
      recoverable ordering" — was wrong; ordering comes from `EVALTYPE`, not the
      date.)

**Small loose ends (fold into any session):**

- [x] ~~`Geothermal/scripts/build_building_demand.py` parquet-metadata clobbering
      bug~~ — fixed 2026-07-24. Both phase writers now call the shared
      `Geothermal/scripts/parquet_meta.py:write_with_meta()`, which carries
      every `heatdemand_*` note across a rewrite. **Phase 4 must use it too.**
- [ ] Watch first scheduled run: rates **2026-08-03**. (Construction's first run
      went green 2026-07-20; AHRI lookup is now a weekly automated refresh as of
      2026-07-22 — both resolved, no longer loose ends.)

---

## 7. Ottawa Case Study — heat demand, electrification, grid (in progress)

The end product is the **Ottawa Case Study**: a six-step narrative (grid
constraints → ground resource → building heat loads → electrified share →
electrification peak vs grid → candidate areas), delivered as a case-study page
with the interactive geothermal map as the expert explorer. Full plan + prompts:
**[HEATDEMAND_PLAN.md](HEATDEMAND_PLAN.md)** (§0 narrative, §5 paste-able
prompts). Build log: [GEOTHERMAL_STATUS.md](GEOTHERMAL_STATUS.md).

| Phase | What | Status |
|---|---|---|
| 0 | Source scouting memo | ✅ 2026-07-16 |
| 1 | Canonical building stock (414k buildings, height/type/vintage) | ✅ 2026-07-16 |
| 2 | Per-building current heat load + fuel | ✅ 2026-07-16 |
| 2.5 | Stock reconciliation — implied dwellings 1.005× census, sums defensible over `in_ottawa_cd` | ✅ 2026-07-17 |
| 3 | Electrified load per building (validated 0.00% vs shipped engine) | ✅ 2026-07-17 |
| **4** | **Aggregate → 500 m grid + feeder stress; apply coincidence factor from CCIM feeder loading** | 🔨 **next** |
| 5 | New map layers (demand, grid stress, intervention score) | 🆕 |
| 6 | The case-study page — the narrative deliverable | 🆕 |

Key Phase-3 findings that shape Phase 4 (details in GEOTHERMAL_STATUS.md):
the "average installed" ccASHP locks out at −15 °C so policy (a)'s design peak
is an equipment problem (Tier 1 halves it); the ~90% hybrid target is
unreachable with that curve (stalls at 81–84%); **the peak columns are
undiversified** — already-electric stock alone sums to 1,275 MW ≈ 98% of Hydro
Ottawa's system peak, so Phase 4 must derive a coincidence factor from real
feeder loading rather than quote raw sums.

---

## 💡 Project ideas (not committed — pick when the queue clears)

1. **EWRB Large-Buildings Explorer.** Ontario's Energy & Water Reporting
   Benchmark publishes *actual reported* energy + floor area + property type for
   every building ≥ 50k ft². Already identified as a heat-demand input
   (HEATDEMAND_PLAN §3.2); a standalone benchmarking page ("how does this
   office/MURB compare to its peers?") would be the suite's first
   *measured-data* tool and reuses the whole design system.
2. **Solar PV layer / explorer.** The ERS data already tracks PV adoption
   (retrofits.html measure flag); NRCan publishes municipal photovoltaic
   potential. Per-FSA adoption vs potential = "who's leaving sun on the table" —
   a natural sibling of the Retrofit Insights choropleths.
3. **Case-study template → second city.** Once Ottawa Case Study Phase 6 ships,
   the pipeline (footprints → stock → load → electrified peak vs feeders) is
   reusable wherever a utility publishes feeder capacity maps (several ON LDCs
   do under the same OEB CCIM mandate). A second city would prove the method
   generalizes.
4. **Bill comparator standalone.** The rates layer (`prices_json/` +
   `utility_rates_reference.json`) + heat pump engine could back a simple
   "what would switching cost *me*" page — narrower and more shareable than the
   full Heat Pump Explorer.
5. **EV charging load layer.** Same grid-stress framing as the case study's
   Phase 4: per-feeder added MW from EV adoption scenarios. Complements the
   heat-pump electrification story on the same GridCapacity polygons.

---

## ✅ Completed items (full record in [docs/archive/ROADMAP_COMPLETED.md](docs/archive/ROADMAP_COMPLETED.md))

| # | Item | Done |
|---|---|---|
| 1 | Ship the Geothermal map | 2026-07-10 |
| 2 | Repo housekeeping — AHRI legacy files | 2026-07-12 |
| 3 | Heat Pump tool, all 7 phases | 2026-07-10 |
| 4 | Energy prices layer, all 3 phases | 2026-07-12 |
| 8 | Geothermal v2 (4 phases) | 2026-07-15 |
| 9 | Heat Pump v2 (6 workstreams) | 2026-07-17 |
| 10 | Retrofit Explorer post-launch additions | 2026-07-17 |
| 11 | Retrofit audit funnel + pairing-filter fix | 2026-07-18 |
| 12 | Retrofit EnerGuide-demo visual polish | 2026-07-18 |
| 13 | Retrofit Insights — national "big picture" page | 2026-07-19 |
| 6 | Live grid dashboard — ETL + page (`grid.html`) | 2026-07-12 (ETL) / 2026-07-24 (page) |
| 5 | Landing page hub (`index.html`) | 2026-07-24 |
| — | New Homes Explorer (built outside the roadmap) | 2026-07-15 |

---

## Session hygiene

- Each prompt is self-contained; run in a fresh session, in order within an item.
- After each session: update the project's STATUS/METHODOLOGY file, flip the
  status board here, and commit.
- Opus for methodology-heavy or design-heavy work (silent-error risk); Sonnet
  for data plumbing with clear validation criteria.
- When an item completes: move its full text to
  [docs/archive/ROADMAP_COMPLETED.md](docs/archive/ROADMAP_COMPLETED.md) and
  keep one line in the Completed table.
