# Ottawa Heat Demand & Electrification Load — Plan

Written 2026-07-16. Supersedes/expands ROADMAP.md item 7. Companion docs:
[GEOTHERMAL_STATUS.md](GEOTHERMAL_STATUS.md), [Geothermal/README.md](Geothermal/README.md).

## 1. End goal

A "geothermal potential study" map for Ottawa showing, together:

| Layer | Status |
|---|---|
| Constrained areas (drilling difficulty, zoning, grid capacity) | ✅ done (geothermal v2 Phases C–D) |
| Geothermal potential (conductivity, open-loop, suitability by segment) | ✅ done (v2 Phases B–D) |
| **Current estimated heat load** (per building → per 500 m cell & per feeder) | 🆕 this plan |
| **Future load with electrification** (ASHP/GSHP conversion, peak kW) | 🆕 this plan |
| **Best spots for intervention** (demand × resource × grid composite) | 🆕 this plan |
| Waste heat potential | ⏳ later (colleague's data; sewer-flow screening as fallback — README §6.4) |

Key existing hook: `Geothermal/scripts/build_suitability.py` already consumes
`Data/processed/heat_demand_grid.geojson` if present (district-energy `demand`
factor upgrades from the binary serviced-area proxy automatically).

## 2. What we already have (no new fetch needed)

- **Residential intensities, Ottawa-specific:** `HeatPump/data/processed/archetypes.json`
  — per-vintage UA (W/K), Tbalance, design heat loss (kW @ design temp), floor
  area, annual space-heat kWh, derived from ERS pre-retrofit medians (Phase 4,
  validated ±10% vs ERS annual energy). This beats any national per-m² table
  for Ottawa houses.
- **ERS parquet** (via `Python/ers_web_pipeline.py`): per-FSA pre-retrofit
  heating-system/fuel mix, intensities by vintage — for the fuel split and for
  archetype refresh at finer granularity if needed.
- **CEUD Ontario** (`ceud_json/res_on.json`, `com_on.json`): residential
  apartment intensities (per household / per m²) and **commercial GJ/m² by
  building activity** — the non-residential intensity table.
- **Heat pump physics:** `hp_curves.json` (tier + "average installed" ASHP
  curves, GSHP curve), `tmy_temps.json` (Ottawa TMY hourly) — everything needed
  to turn a UA into an hourly load-duration curve, a design-day peak, and an
  electrified peak with COP(T) and backup assumptions.
- **Hydro Ottawa areas:** `GridCapacity/ottawa_capacity.geojson` — 3,884 feeder
  polygons with available MVA (OEB CCIM; refresh via `GridCapacity/Hydro.py`).
- **Census FSA layer:** `census_json/fsa_census.json` + `FSA_Maps/ON.geojson`.
- **500 m analysis grid:** the conductivity grid (13,778 cells) is the canonical
  cell set (`Geothermal/scripts/idw.py` conventions).

## 3. Data sources to acquire

### 3.1 Building stock (footprints + height + type)

Verified 2026-07-16: the City's footprint layer
(`maps.ottawa.ca/arcgis/rest/services/TopographicMapping/MapServer/3`, ~392k
polygons) carries **geometry only** — no height, no type. So the plan is one
canonical footprint layer enriched from other sources:

| Source | What it adds | Notes |
|---|---|---|
| [Canada Structures (Public Safety Canada)](https://open.canada.ca/data/en/dataset/3829eee9-f898-4643-9ad8-f48575b8873d) | merged ODB + OSM + Microsoft footprints, `on_structures_en.gpkg`, updated 2026-04 | **Phase 0 must inspect the ON gpkg schema** — attribute richness (type? height?) is undocumented on the portal; spec PDF exists |
| [NRCan Automatically Extracted Buildings](https://open.canada.ca/data/en/dataset/7a5cda52-c7df-427f-9ced-26f19a8a64d6) | **LiDAR-derived min/max building heights** where covered | Phase 0 checks Ottawa coverage (City LiDAR 2019–20 exists, likely ingested) |
| Overture Maps buildings | `height`, `num_floors`, `class` for many buildings; permissive licence | fallback/enrichment if the two above disappoint |
| City of Ottawa footprints (TopographicMapping/3) | best geometric fidelity, authoritative | geometry backbone candidate |
| Census 2021 **DA-level** profile (period of construction, structural dwelling type, dwelling counts) | vintage mix + dwelling-type mix per DA → assign to buildings probabilistically | FSA level is too coarse for this; fetch DA profile for Ottawa CSD |
| City zoning (full, not just industrial — `fetch_municipal_layers.py` pattern, Zoning/3 without the industrial filter) | residential/commercial/institutional/industrial classification per building | plus OSM `building=` tags via Canada Structures |
| City municipal address points (open.ottawa.ca) | units-per-building hints for MURBs | Phase 0 checks attributes |

### 3.2 Building consumption (better than pure modelling)

| Source | Use |
|---|---|
| **Ontario EWRB** — [Energy and water usage of large buildings](https://open.canada.ca/data/en/dataset/0eab2faf-6186-4a5b-8de1-b15872943c24) (data.ontario.ca, Excel, annual) | **Actual reported** energy + floor area + property type + address for every building ≥ 50k ft² (commercial, MURB > 10 units, some industrial). Geocode the Ottawa rows and use *actuals* instead of modelled values for matched large buildings; also calibrates the commercial intensity table |
| **StatCan 38-10-0286** — [Primary heating systems and type of energy](https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=3810028601) (CMA level, incl. Ottawa) | city-wide heating-system + fuel shares; reconciles the ERS per-FSA mix (ERS is an audit-biased sample) |
| **City of Ottawa community energy inventory** (Energy Evolution annual GHG/energy inventory) | city-wide actual electricity + natural gas totals — the top-level calibration target. Phase 0 locates the latest table |
| CEUD ON residential scaled to Ottawa household counts | secondary calibration (ROADMAP item 7's original ±30% check) |

Explicitly rejected: no public parcel-level assessment (MPAC is closed); no
utility billing data at sub-city granularity; SCIEU microdata is not public
(CEUD's commercial intensities already embed it).

### 3.3 Existing open projects (surveyed on GitHub 2026-07-16)

No drop-in "Ottawa heat load" project exists, but four are worth reusing
pieces of and two are methodology references:

| Project | What it is | How we use it |
|---|---|---|
| [canmet-energy/tandm](https://github.com/canmet-energy/tandm) (TaNDM) | NRCan's bottom-up building energy & emissions inventory **method** (parcel + assessment + metered utility data, aggregated by vintage × building category to neighbourhood scale; demonstrated in Kelowna 2021 with published inventory spreadsheets) | Not runnable here (needs utility/assessment data agreements; FME/ArcGIS). **Use the Kelowna 2021 inventory EUIs (by type × vintage) as an independent intensity cross-check in Phase 2**, and its vintage × category aggregation framing. Its README also confirms NRCan's own UBEM ("CEE Map") is *not* open source |
| [canmet-energy/community-energy-orchestrator](https://github.com/canmet-energy/community-energy-orchestrator) | Census housing stock → archetype assignment → EnergyPlus → community energy by fuel (139 remote communities; AGPL) | Per-building EnergyPlus is overkill for a 392k-building screening layer, but **read its census→archetype assignment logic before writing Phase 1's probabilistic vintage/type assignment** (method inspiration, not code import — AGPL) |
| [canmet-energy/housing-archetypes](https://github.com/canmet-energy/housing-archetypes) | Statistically representative Canadian low-rise housing archetypes (EnerGuide + SHEU; CSV summaries + H2K files) | **Phase 2 cross-check** of our Ottawa ERS-derived archetype intensities/UA against the national summary tables |
| [canmet-energy/btap_batch](https://github.com/canmet-energy/btap_batch) | NECB commercial archetype generator (OpenStudio/EnergyPlus, costing) | Fallback source for commercial intensities by building type if the CEUD activity mapping proves too coarse; not run by default |
| [THERMOS](https://github.com/cse-bristol/110-thermos-ui) (EU H2020, open source) | Heat-network planning tool: OSM-based building heat-demand estimation + district-network routing/economics | Its demand regressions are trained on European stock (don't trust for Ottawa), but it **accepts user-supplied per-building demands** — candidate for a later site-level district-energy network study seeded with our Phase 2 outputs |
| [Hotmaps](https://github.com/HotMaps/Hotmaps-toolbox-service) (EU H2020) | District-heating potential mapping toolbox | EU-only data; borrow its **heat-density viability thresholds** (e.g. GWh/km² classes) for the Phase 5 intervention-score documentation |

Also checked: NRCan-IETS-CE-O-HBC/{HTAP, HTAP-archetypes, ERS_Database} (we
already have our own ERS pipeline and Ottawa archetypes),
NRCan/energuide_api (superseded by our CSV pipeline),
architecture-building-systems/CityEnergyAnalyst (full UBEM platform — viable
for a follow-up deep-dive of shortlisted intervention sites, too heavy for
city-wide screening).

## 4. Pipeline (new scripts under `Geothermal/scripts/` unless noted)

```
Phase 0  scout_buildings.py-ish notes    → Data/heatdemand_source_notes.md (decision memo)
Phase 1  build_building_stock.py         → Data/processed/buildings_ottawa.parquet (+gpkg)
Phase 2  build_building_demand.py        → adds annual kWh, design kW, fuel per building
Phase 3  build_electrified_load.py       → adds electrified annual kWh + peak kW per building
Phase 4  build_heat_demand.py            → heat_demand_grid.geojson (500 m) + feeder_demand.geojson
         └─ re-run build_suitability.py  → district demand factor upgrades automatically
Phase 5  merge_layers.py + build_map.py  → new map layers (demand, electrified stress, intervention score)
```

- **Phase 1 — canonical building stock.** Pick the footprint backbone from
  Phase 0's findings; join heights (LiDAR layer or Overture; else documented
  storeys defaults by type); classify each building
  (detached / row / low-rise MURB / high-rise MURB / commercial / institutional /
  industrial) from zoning + OSM class + census DA dwelling-type mix; assign
  vintage from the DA period-of-construction mix (probabilistic, documented);
  tag each building with its 500 m cell id, feeder polygon, DA, FSA.
- **Phase 2 — current load.** Residential: archetype match (vintage × type) →
  annual space-heat kWh scaled by floor area (storeys × footprint vs archetype
  floor area, capped), design heat loss via the archetype UA ratio. Apartments:
  CEUD per-household apartment intensity × unit estimates. Non-res: CEUD
  commercial GJ/m² by activity × floor area; **EWRB actuals override modelled
  values where an address matches.** Fuel assignment per building from ERS
  per-FSA system mix reconciled to the 38-10-0286 CMA totals (gas dominant in
  serviced urban area; electric baseboard/oil pockets rural). Everything is a
  *screening estimate* — say so in output metadata.
- **Phase 3 — electrified load.** For each fossil-heated building: convert with
  the `hp_curves.json` "average installed" ccASHP curve (sensitivity: Tier 1 and
  GSHP variants), hourly over the Ottawa TMY: annual electric kWh, and **peak
  electric kW at design temp** under two documented backup policies (electric
  resistance backup vs right-sized HP + existing backup). Output per-building
  `elec_kwh_now`, `elec_kw_peak_now`, `elec_kwh_electrified`,
  `elec_kw_peak_electrified`.
- **Phase 4 — aggregation.** Sum to the canonical 500 m cells
  (`heat_demand_grid.geojson`: kWh/yr, kW design heat, kW electric peak now /
  electrified, dominant fuel, building counts by class) and to feeder polygons
  (`feeder_demand.geojson`: same + **headroom stress = added electrified MW vs
  available MVA**, with the documented caveat that CCIM "available capacity" is
  a connection-screening figure, not a planning load-flow). Validate city-wide
  totals against the community energy inventory + CEUD scaling (±30%).
- **Phase 5 — map.** Extend the shipped geothermal map: heat-demand choropleth,
  electrification grid-stress layer (feeder polygons recoloured by stress), and
  an **intervention score** = normalized(demand density) ×
  segment-suitability × grid-relief bonus (high stress ⇒ non-wire alternative
  value), with popup breakdowns. Keep the ≤ 8 MB single-file budget (aggregate
  layers only — per-building data stays in `Data/processed/`). Republish.

**Waste-heat hook (later):** Phase 4's grid schema reserves a
`waste_heat_kwh` field (null for now); when the colleague's data arrives it
joins by cell and the intervention score gains a factor. Sewer-flow screening
(README §6.4) is the public-data fallback.

## 5. Paste-able prompts

Run from `C:\Energy`, fresh session each, in order. Commit after each phase.

### Prompt — Phase 0: building-stock scouting (Sonnet)

```text
Read HEATDEMAND_PLAN.md (§3) and GEOTHERMAL_STATUS.md first. Goal: pick the
building footprint/height/type sources for Ottawa. Do not build the pipeline
yet — this is a scouting session ending in a decision memo.

1. Download the Canada Structures Ontario GeoPackage
   (open.canada.ca dataset 3829eee9-f898-4643-9ad8-f48575b8873d,
   on_structures_en.gpkg) — it may be large; if so stream/clip to the Ottawa
   bbox used in Geothermal/scripts/combine_wells.py. Inspect the schema: does
   it carry a structure type, height, source flag? Count Ottawa features and
   compare against the City layer's ~392k.
2. Check NRCan Automatically Extracted Buildings (dataset
   7a5cda52-c7df-427f-9ced-26f19a8a64d6) for Ottawa coverage and the
   height_min/height_max attributes; download the Ottawa tiles if covered.
3. Check Overture Maps buildings for Ottawa (height, num_floors, class
   coverage rates) as the enrichment fallback.
4. Check open.ottawa.ca for: municipal address points (units per building?),
   any 3D/building-height layer, and the latest community energy inventory
   (Energy Evolution annual GHG inventory — city-wide electricity + gas
   totals; record the numbers and source URL for Phase 4 calibration).
5. Fetch the Ontario EWRB "energy and water usage of large buildings" Excel
   from data.ontario.ca; count Ottawa rows, list columns, check address
   quality for geocoding.
6. Pull StatCan 38-10-0286 (primary heating systems, Ottawa CMA) via the WDS
   API (see Python/construction_etl.py for conventions) and record the
   latest fuel shares.
Write Geothermal/Data/heatdemand_source_notes.md: per-source verdict
(attributes, coverage, counts, licence, download URL/method), a
recommendation for footprint backbone + height source + type strategy, and
open risks. Note memory quirks: some gov sites block WebFetch — use curl -L.
```

### Prompt — Phase 1: canonical building stock (Sonnet)

```text
Read HEATDEMAND_PLAN.md (§3–4) and Geothermal/Data/heatdemand_source_notes.md
first. Build Geothermal/scripts/build_building_stock.py producing
Data/processed/buildings_ottawa.parquet (+ a gpkg for QGIS spot-checks):
one row per building with footprint_m2, height_m/storeys (source-flagged;
documented per-type defaults where missing), class (detached / row /
lowrise_murb / highrise_murb / commercial / institutional / industrial —
from zoning + Canada Structures/OSM type + census DA dwelling-type mix),
vintage (probabilistic from the DA period-of-construction mix — fetch the
2021 DA profile for Ottawa; before designing the assignment, skim how
canmet-energy/community-energy-orchestrator assigns archetypes from census
stock data — method inspiration only, it's AGPL, don't copy code; document
the assignment), and joins: grid cell id
(the conductivity grid via Geothermal/scripts/idw.py conventions), feeder id
(GridCapacity/ottawa_capacity.geojson), DA, FSA. Refetch the FULL zoning
layer (fetch_municipal_layers.py pattern, no industrial filter). Cache raw
pulls under Geothermal/Data/Raw/ (the City footprint layer is ~392k
polygons — paginate; esriJSON fallback gotcha documented in
fetch_municipal_layers.py). Filter to buildings > 40 m². Validate and print:
total counts by class vs census dwelling counts for Ottawa (detached/row/
apartment within ~±15%), storeys distribution sanity, share of
height-sourced vs defaulted. Document method + assumptions in
Geothermal/README.md (new section) and append to GEOTHERMAL_STATUS.md.
```

### Prompt — Phase 2: current heat load per building (Opus — methodology-heavy)

```text
Read HEATDEMAND_PLAN.md (§2–4), Geothermal/README.md (building-stock
section) and HeatPump/METHODOLOGY.md (Phase 4 archetypes) first. Build
Geothermal/scripts/build_building_demand.py: annual space-heat kWh, design
heat loss kW, and heating fuel per building in buildings_ottawa.parquet.

- Residential houses: match archetype (HeatPump/data/processed/
  archetypes.json Ottawa, vintage × type) and scale annual kWh and UA by
  floor area (storeys × footprint / archetype floor_area_m2, clamped to
  [0.5, 2.5] — document). Townhouse archetype for row; derive a semi/duplex
  treatment and document it.
- Apartments/MURBs: CEUD ON residential apartment intensity per household
  (ceud_json/res_on.json) × estimated units (floor area / a documented m²
  per unit, cross-checked against address points if Phase 0 found them).
- Non-residential: CEUD ON commercial GJ/m² by activity (com_on.json),
  mapped from building class/zoning; industrial gets a clearly-flagged
  low-confidence placeholder intensity.
- EWRB override: geocode the Ottawa EWRB rows (address → footprint match;
  report match rate); where matched, replace modelled annual energy with
  reported actuals (keep both columns) and use the delta distribution to
  bias-correct the modelled commercial stock (document).
- Fuel: assign gas/electric/oil/wood per building from the ERS per-FSA
  pre-retrofit system mix (ers parquet), reconciled so city-wide shares hit
  StatCan 38-10-0286 Ottawa CMA (iterative proportional fitting or a
  documented simpler rake). Rural unserviced areas: no-gas constraint via
  the City serviced-area layer already in the geothermal data.
Validate and print: (a) city-wide residential space heat vs CEUD ON scaled
by Ottawa household count (±30%); (b) total gas-heated share vs 38-10-0286;
(c) city-wide totals vs the community energy inventory numbers from the
Phase 0 notes (space-heat share of total gas documented); (d) EWRB matched
buildings modelled-vs-actual scatter stats; (e) cross-check our per-type ×
vintage intensities against two independent references — the TaNDM Kelowna
2021 inventory EUIs (github.com/canmet-energy/tandm, analysis-ready xlsx;
milder climate, so expect Ottawa higher — compare after a documented HDD
normalization) and the national summary tables in
github.com/canmet-energy/housing-archetypes — tabulate deltas and explain
outliers. Investigate failures before
writing output. This is a screening layer, not building audits — say so in
the parquet metadata and README. Update README + GEOTHERMAL_STATUS.md.
```

### Prompt — Phase 3: electrified load per building (Opus)

```text
Read HEATDEMAND_PLAN.md §4, HeatPump/METHODOLOGY.md (curves, engine,
archetypes) and the Phase 2 README section first. Build
Geothermal/scripts/build_electrified_load.py: for every fossil-heated
building, simulate conversion using HeatPump/data/processed/hp_curves.json
("average installed" ccASHP as the central case) hourly over the Ottawa TMY
(tmy_temps.json), reusing the load model UA × (Tbalance − T)⁺. Outputs per
building: current electric peak kW (electric-heated buildings only),
electrified annual kWh, electrified peak kW under two documented policies —
(a) HP sized to design load with electric resistance backup below cutoff,
(b) HP sized to ~90% load fraction with the existing fossil backup retained
(hybrid). Add a GSHP variant column (flat COP from hp_curves' GSHP curve) —
that's the geothermal counterfactual the map contrasts. Large/commercial
buildings: apply a documented simplified conversion (annual kWh / seasonal
COP; peak via a load-factor assumption) — flag lower confidence. Validate:
per-archetype electrified annual kWh must match heatpump.html's engine
within ±10% for the same inputs (the Python mirror test_hp_curves.py shows
how to run the curves); print a table. Print city-wide added GWh and added
design-day MW vs Hydro Ottawa's ~1,300 MW-class system peak for sanity.
Update README + GEOTHERMAL_STATUS.md.
```

### Prompt — Phase 4: grid + feeder aggregation (Sonnet)

```text
Read HEATDEMAND_PLAN.md §4 and the Phase 2–3 README sections. Build
Geothermal/scripts/build_heat_demand.py aggregating
buildings_ottawa.parquet to (1) the canonical 500 m conductivity-grid cells
→ Data/processed/heat_demand_grid.geojson (annual kWh, design kW, current
electric peak kW, electrified peak kW both policies, GSHP variant, dominant
fuel, building counts by class, plus a reserved null waste_heat_kwh field)
and (2) Hydro Ottawa feeder polygons → Data/processed/feeder_demand.geojson
(same sums + stress = added electrified MW / available MVA from
GridCapacity, with the CCIM screening-figure caveat in the properties).
Cells must be index-compatible with the conductivity grid (same ids/order
where covered). Then re-run build_suitability.py and report how the
district-energy demand factor and scores shift now that
heat_demand_grid.geojson exists (the upgrade hook is documented in README
§3.9). Validate: grid-cell sums equal building-level sums; no demand in
cells with zero buildings; print the top-10 stressed feeders and eyeball
plausibility. Update README + GEOTHERMAL_STATUS.md.
```

### Prompt — Phase 5: map integration + intervention score (Opus — design-heavy)

```text
Read HEATDEMAND_PLAN.md §4–5, Geothermal/README.md §3.4–3.9 and
GEOTHERMAL_STATUS.md (Phase D session — SUIT/GRID embedding pattern, 8 MB
budget, no-rAF preview quirks). Extend merge_layers.py + build_map.py +
map_template.html with three toggleable layers from heat_demand_grid.geojson
and feeder_demand.geojson: (1) heat demand choropleth (kWh/yr per cell,
popup with per-class breakdown + fuel mix); (2) electrification grid stress
(feeder polygons coloured by added-MW/available-MVA, policy toggle a/b);
(3) intervention score per cell = documented composite of normalized demand
density × the active segment's suitability score (reuse the Phase D SUIT
machinery — the segment radio should drive this layer too) × a grid-relief
bonus where the cell's feeder stress is high. Ground the demand-density
thresholds in the district-heating literature — the Hotmaps project's heat
density viability classes (github.com/HotMaps) are the reference to cite.
Publish the formula in README and the popup. Embed aggregates only (per-building data stays in
Data/processed/); keep output/index.html ≤ 8 MB — state the trimming used.
Re-run the full chain, browser-verify (all layers toggle, popups, segment
switch restyles intervention, conductivity edits still flow, zero console
errors — canvas pixel sampling per the no-rAF quirk), update README +
GEOTHERMAL_STATUS.md + ROADMAP item 7 status, republish to GitHub Pages.
```

## 6. Risks / open questions

- **Height coverage** is the big unknown → Phase 0 exists to resolve it; the
  fallback (documented per-type storeys defaults) mostly hurts downtown
  towers, which EWRB actuals partially rescue.
- **Vintage per building is probabilistic** (DA mix), fine for 500 m cells,
  meaningless for a single address — keep per-building outputs internal.
- **ERS sample bias** (audit volunteers, 74% zero-measure noise per memory
  notes) — mitigated by raking fuel shares to 38-10-0286 and calibrating
  totals to the community inventory.
- **CCIM available capacity ≠ hosting capacity for load** — it's a
  connection-screening figure; the stress layer must carry that caveat.
- **Ottawa–Gatineau**: everything here is Ontario-side only (consistent with
  WWIS); say so on the map.
