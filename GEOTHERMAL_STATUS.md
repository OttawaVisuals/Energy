# Ottawa Geothermal — Build Log & Status

Companion to [Geothermal/ottawa-geothermal-guide.md](Geothermal/ottawa-geothermal-guide.md) (the 8-step
pipeline plan). This file records what has actually been built and run.

*Last session: 2026-07-24.*

**Live:** https://ottawavisuals.github.io/Energy/Geothermal/output/

## 2026-07-24 session — parquet-metadata carry-forward fix (no data change)

Closes the loose end flagged 2026-07-17. Every heat-demand phase augments
`buildings_ottawa.parquet` **in place** and stamps a `heatdemand_phaseN`
provenance note into its custom schema metadata. geopandas does not round-trip
custom schema metadata through the GeoDataFrame, so `gdf.to_parquet()` writes a
fresh schema and drops every note not explicitly re-attached. Phase 3 handled
this; **Phase 2 did not** — re-running `build_building_demand.py` on an
already-electrified file silently destroyed the `heatdemand_phase3` note. The
columns survived (Phase 2 reads the current parquet, so Phase 3's `elec_*`
columns pass through), so the loss was provenance only: the record of which
heat-pump curve, COP assumptions and lockout temperature produced the Phase 3
peaks Phase 4 has to defend.

**Fix:** new shared module `Geothermal/scripts/parquet_meta.py` —
`write_with_meta(gdf, path, key, meta)` reads the existing `heatdemand_*` keys
before rewriting and merges them back. Phases 2 and 3 both call it; the
hand-rolled blocks in each are gone. **Phase 4 must use it too** — that is the
point of putting it in one place.

Verified by round-trip on a scratch parquet: phase1 → 2 → 3, then a Phase 2
**re-run**, after which `heatdemand_phase3` still reads back intact, Phase 2's
own note is updated, and geo metadata/CRS survive. No pipeline re-run and no
change to any committed data.

## 2026-07-17 session — Heat Demand Phase 3: electrified load per building

[HEATDEMAND_PLAN.md](HEATDEMAND_PLAN.md) Phase 3. **New script**
`Geothermal/scripts/build_electrified_load.py` — converts every fossil-heated
building to a heat pump hour-by-hour over the Ottawa TMY and adds 12 electricity
columns + `elec_method`/`elec_confidence` to the parquet (plus a
`heatdemand_phase3` note). Method in `Geothermal/README.md` **§3.12**; this entry
is the findings.

**Validation: worst deviation 0.00%** across 4 archetypes × 3 policies against
the shipped engine (target ±10%). Node is still unavailable, so this runs against
`HeatPump/pipeline/validate_engine.py`'s faithful Python mirror — the same
limitation METHODOLOGY Phase 5 already records. Agreement is exact rather than
merely in-band because the group model *is* the engine's dispatch factored
through UA-linearity (below); the check guards that factoring.

**The 8760 × 414k problem dissolved.** Phase 2 gives every class
`design_kw = ua × 43.8/1000`, so sizing is a fixed multiple of UA and the whole
dispatch is **exactly linear in UA** at a fixed balance point. The hourly run is
solved **once per balance point (7 groups)** and scaled per building. Asserted at
run time (holds to 0.14% — `archetypes.json` rounding), not assumed.

**Headline (Ottawa CD; 253,271 buildings converted, 9.83 TWh/yr of heat):**

| Policy | Added GWh/yr | Added MW @ design | vs ~1,300 MW peak |
|---|---|---|---|
| (a) ccASHP + resistance backup | 4,613 | **5,264** | +405% |
| (b) hybrid, fossil kept | 3,410 | **0** (1,834 at its worst hour) | +0% |
| GSHP counterfactual | 2,515 | **1,482** | +114% |

**Three findings that came out of the data, not the brief:**
1. **The "average installed" ccASHP locks out at −15 °C — warmer than Ottawa's
   −22.8 °C design temperature.** So under policy (a) the resistance backup
   carries **100% of the design load at COP 1**, and the design-day peak is just
   the design heat call regardless of how good the curve is above lockout.
   Policy (a)'s peak is an **equipment** problem, not a building-stock problem.
   Sensitivity proves it: **Tier 1 (−25 °C) adds 2,836 MW — 0.54× the central
   case.** (Tier 3 reproduces the central case exactly, as its own description
   says it should — a free consistency check.)
2. **The plan's "~90% load fraction" hybrid target is unreachable** with the
   central curve: ~17% of Ottawa's annual load falls below its −15 °C lockout, so
   the switchover pins at lockout and the achieved fraction stalls at **81–84%**.
   Documented and printed rather than force-fit. Tier 1 is not bound by it.
3. **The hybrid's 0 MW is real but definitional** — its HP is off below −15 °C, so
   it draws nothing *at* −22.8 °C. Its true grid cost lands just above the
   switchover (**1,834 MW**). Reported both ways so the zero can't mislead.

> **The sanity check found the model's own ceiling — worth reading before quoting
> any MW.** Buildings that are **already** electrically heated sum to **1,275 MW**
> at design: **98% of Hydro Ottawa's entire system peak, from space heat alone,
> before converting anything.** That can't be literally true. The cause is **no
> diversity** — these sums put every building at full design-condition load in the
> same hour — compounded by Phase 2's probabilistic-stock caveat. **Phase 4 must
> apply a coincidence factor from actual CCIM feeder loading; this script
> deliberately does not invent one.** The **ratios between policies** are the
> robust result (shared load basis, shared stock); the absolute MW are upper
> bounds.

**Bug found and fixed along the way:** `elec_kw_peak_now` was built from
`design_kw` (the no-gains *sizing* figure) while every electrified peak used the
balance-point load at design (gains credited) — inflating the current-electric
peak ~32% against the very numbers it is compared with. All peaks are now on the
load basis; sizing alone uses `design_kw`. README §3.12 spells the two apart.

**Second bug — parquet metadata clobbering.** `gdf.to_parquet()` writes a fresh
schema, and geopandas doesn't round-trip custom metadata, so the phase-3 write
silently destroyed Phase 2's `heatdemand_phase2` note (recovered from git HEAD).
Phase 3 now reads prior `heatdemand_*` keys *before* rewriting and merges them
forward. **`build_building_demand.py` still has the same latent bug** — re-running
Phase 2 would destroy the phase-3 note; flagged as a follow-up.

**Deviations from the brief:** (1) the brief called `average_installed` a
"ccASHP" — it is the popularity-weighted curve and maps to **Tier 3, baseline**,
with a −15 °C lockout, which is exactly why the peaks land where they do; kept as
the central case (it is what people actually install) with the tier spread
carried alongside. (2) The plan's literal `annual_elec / EFLH` load-factor form
for large-building peaks was **not used**: it reduces to `design_load / SCOP`,
dividing a design load by a *seasonal* COP, understating the design peak ~2×. The
peak uses the design-condition COP; EFLH is used for the energy check instead.
(3) The large-building "simplified" conversion lands on the *same numbers* as the
hourly route — the SCOP and design COP come off the same curve and Phase 2's
non-res `design_kw` is EFLH-derived, so it's the same algebra. It is flagged
`elec_confidence='low'` for the **equipment** assumption (a residential unitary
curve borrowed for a central plant — `hp_curves.json` has no commercial curves),
not for the arithmetic. Said plainly rather than dressed up as a second method.

**Downstream note:** Phase 4 inherits the coincidence-factor job (above), should
carry the tier column (the spread is the policy-relevant finding), and must keep
summing over `in_ottawa_cd`.

## 2026-07-17 session — Heat Demand Phase 2.5: stock reconciliation (the defensibility fix)

[HEATDEMAND_PLAN.md](HEATDEMAND_PLAN.md) Phase 2.5 — the blocker that made every
city-wide sum unquotable. Fixed the **stock**, not the intensities. Method +
rules in `Geothermal/README.md` **§3.10.1**; this entry is the numbers.

**Diagnosis first** (printed by `reconcile_stock()` as implied dwellings by
class × `assign_path` × inside/outside the Ottawa CD). The headline "808k
implied dwellings vs 427k census households (1.89×)" turned out to be **mostly
an apples-to-oranges geography mismatch**, not a modelling error:
- **bbox beyond the city — the dominant carrier.** The analysis bbox is a
  rectangle bigger than the Ottawa CD and catches ~19% of buildings in
  surrounding townships; those carried **~353k of the 808k implied dwellings**
  (~44%), while the census households compared against are **city-only**.
  Restricting to the CD alone already put every check in band.
- **MURB no-height inflation — secondary.** A building with no height could be
  *drawn* as `highrise_murb` and then given the 10-storey `STOREY_DEFAULT`,
  inflating floor area and unit count with zero evidence (~200k bbox implied
  units; 8,614 default-height "highrises").
- **Accessory buildings — minor.** Only 1.5% of `detached` are ≤50 m²; the real
  accessory clutter sits in the unsignalled `residential_draw` pool. So suspect
  (a) was *not* the main story, (b) was.

**Fix — three seeded, documented levers in `build_building_stock.py`:**
1. **`in_ottawa_cd`** (new column) — centroid in one of the 1,392 Ottawa-CD DAs.
   **All city-wide sums now take this subset.** Dominant correction.
2. **Rule R1 — highrise requires real height evidence.** No-height probabilistic
   draws can land on detached/row/**lowrise**, never highrise. `highrise_murb`
   16,691 → **1,074** (the survivors are height-evidenced). New `assign_path`
   column records class provenance.
3. **Per-DA cap → `accessory`.** A DA's implied dwellings may exceed its census
   `total_dwellings` by at most **+15%**; the excess is reclassified to the new
   non-dwelling `accessory` class, **smallest footprint first and only from the
   unsignalled `residential_draw` path** — OSM-tagged/height-evidenced buildings
   are never touched. Reassigned **17,791 buildings across 247 DAs**; **121 DAs
   left honestly over** (their excess is real OSM/height stock, not force-fit).

**Validation after re-running `build_building_demand.py`** (all four gates pass;
city sums on the CD):
- (a) **implied dwellings 429,282 = 1.005×** census 427,113 (was 1.89×) — ±10% ✅
- (b) **residential space heat 6.68 TWh vs CEUD-scaled 7.38 TWh (−10%)** (was
  +36%) — ±20% ✅
- (c) **detached per-unit mean 22,655 kWh vs CEUD 22,520 (+1%)** — did **not**
  move (was 22,534); confirms the fix is stock, not intensity ✅
- (d) **space-heat emissions 2.20 Mt = 80%** of the Energy Evolution 2024
  buildings inventory (was 104%) — a plausible space-heat share ✅
- fuel **gas 59.1% / electric 21.0%** — on the StatCan targets.

**Bug found and fixed along the way:** the fuel IPF rake targeted StatCan
38-10-0286's **Ottawa-CMA** shares but was fitted over the **whole bbox**. That
hit 59/21 bbox-wide while leaving the *city* subset at **gas 74.2% / electric
14.1%** — invisible until Phase 2.5 correctly scoped validation to the CD. The
rake is now fitted over the CD residential subset (the geography the target
describes); outside-CD rural buildings keep their per-FSA/no-gas mix.

**Deviations from the brief:** the brief expected accessory fall-through (a) to
be a prime carrier and `build_building_demand.py` to be re-run *unchanged*. The
diagnosis showed (b) the bbox dominates instead, so the fix is weighted that
way. `build_building_demand.py` needed two **structural** (not intensity-tuning)
edits: an `accessory` handler (unheated, `annual_kwh = 0`) for the new stock
class, and the fuel-rake geography fix above; the demand *model* — archetypes,
intensities, EFLH, HEATED_FRACTION_HOUSE — is untouched, which is what the
"don't retune intensities" instruction protects (and check (c) proves it held).

**Stock now:** 414,111 buildings (336,365 inside the CD). Classes: detached
251,639 · row 100,282 · lowrise_murb 21,861 · **accessory 17,791** · commercial
11,670 · industrial 6,628 · institutional 3,166 · highrise_murb 1,074. The
detached/row *split* stays soft (inside-CD detached +23% / row −27% vs census,
**sum +3.4%**) — semis digitised as separate footprints, the known §3.10
labelling softness; it moves neither the dwelling total nor the heat sum.

**Downstream note:** Phases 4–6 must sum over `in_ottawa_cd` for any quotable
city-wide figure, and treat `accessory` as non-dwelling.

## 2026-07-16 session — plan reframe: the Ottawa Case Study (no build)

Planning session after a step-back review with the user. The project's end
product is reframed as the **Ottawa Case Study** — a simple six-step argument
(grid constraints → ground resource → building heat loads → electrified share
→ electrification peak vs grid → candidate areas), documented in
[HEATDEMAND_PLAN.md](HEATDEMAND_PLAN.md) §0. Decisions: (1) the interactive
map stays as the *expert explorer*; a new narrative **case-study page**
(Phase 6) becomes the front door — sources, process, assumptions, plainly
explained; (2) a new **Phase 2.5** fixes the building-stock over-count (808k
implied dwellings vs 427k census households) before any city-wide number is
quoted — it is the single defensibility blocker; (3) open items to resolve
with the user: locate/cite the City's commissioned geothermal study (believed
J.L. Richards — only its presumed output, the Planning/122 layer, is in the
pipeline today), and confirm CCIM feeders are the intended "Hydro Ottawa
sectors" granularity. Live queue: **2.5 → 3 → 4 → 5 → 6**, prompts in
HEATDEMAND_PLAN.md §5.

## 2026-07-16 session — Heat Demand Phase 2: per-building heat load

[HEATDEMAND_PLAN.md](HEATDEMAND_PLAN.md) Phase 2. **New script**
`Geothermal/scripts/build_building_demand.py` augments
`Data/processed/buildings_ottawa.parquet` in place with `floor_area_m2,
annual_kwh, design_kw, ua_w_per_k, units_est, heat_fuel, demand_method,
demand_confidence` (+ a `heatdemand_phase2` screening warning in the parquet
metadata). Full method in `Geothermal/README.md` §3.11 — this entry is the
numbers and decisions.

**Method (screening layer):** houses (`detached`/`row`) = Ottawa ERS archetypes
(`HeatPump/.../archetypes.json`) scaled by floor area (gross→heated ×0.80,
clamp 0.5–2.5); MURBs = CEUD ON apartment÷attached per-m² ratio × Ottawa row
archetype = **59.7 kWh/m²**; non-residential = **EWRB-2024 Ottawa actual median
Site_EUI × CEUD commercial space-heat share** (commercial ≈137, institutional
≈125, industrial ≈63 kWh/m², industrial flagged `very_low`); design kW via the
archetype ratio (houses) or TMY-derived EFLH at a per-class balance point
(others); fuel = ERS per-FSA `Pre_HeatFuel` **raked (IPF) to StatCan 38-10-0286**
(gas 59% / electric 21%) with a **rural no-gas** constraint from the serviced-
area layer, seeded draw (seed `20260716`).

**Key decisions / deviations from the brief:**
- **EWRB cannot override per building** — Phase 0 found it has no street address
  or floor area, so it's used only to *calibrate* the commercial intensity
  (its intended secondary role), replacing CEUD's provincial commercial value
  which came out **1.73× the Ottawa actual** (the known CEUD floor-space
  undercount, confirmed against 150 Ottawa EWRB commercial rows).
- **Apartment intensity via the CEUD ratio, not a raw CEUD figure + HDD uplift**
  — keeps MURBs internally consistent with (more efficient than) the Ottawa row
  archetype and avoids an external HDD guess.
- **Semi/duplex** fold into `row`/`townhouse_row` (Phase 1's enum has no `semi`);
  validated by the CEUD `single_attached` (=row+semi+attached) match to ~3%.

**Validation (printed; investigated, not force-fit):** (a) residential space
heat **10.07 TWh vs 7.38 TWh CEUD-scaled (+36%)** — *root-caused* to a Phase 1
**stock-count** issue (modelled stock implies **808k dwellings vs 427k census
households, 1.89×**; detached over-attributed per §3.10), while the **per-unit**
detached mean **22,534 kWh matches CEUD single_detached 22,520 kWh (<1%)**;
per-building values kept as-is (Phase 3 needs them), city-wide sums flagged as
upper estimates. (b) gas **59.1%** / electric **21.0%** — on the StatCan targets
by construction. (c) modelled space-heat emissions **2.84 Mt = 104%** of the
Energy Evolution 2024 buildings inventory (2.74 Mt) — the >100% is the same
stock inflation; stock-reconciled ≈76%, a plausible space-heat share. (d) EWRB
Ottawa median Site_EUI commercial 0.86 / institutional 0.78 / industrial 0.57
GJ/m². (e) per-m² ~30% below CEUD ON (ERS archetypes are larger-than-average
homes — same fact as the per-unit match); **TaNDM Kelowna** detached
HDD-normalised **29,462 kWh vs our 22,534 (−24%)**, expected (Kelowna gas
includes water heating; milder-climate normalisation approximate). TaNDM xlsx
cached at `Data/Raw/references/`.

**Biggest open item:** city-wide totals run high purely from Phase 1's
building:dwelling over-count — the highest-value fix before the Phase 4/5 map is
trusted quantitatively is tightening Phase 1 classification, not re-tuning
Phase 2 intensities (which match CEUD per unit).

## 2026-07-16 session — Heat Demand Phase 1: canonical building stock

[HEATDEMAND_PLAN.md](HEATDEMAND_PLAN.md) Phase 1 (Phase 0 scouting memo:
[`Geothermal/Data/heatdemand_source_notes.md`](Geothermal/Data/heatdemand_source_notes.md)).
New pipeline, kept in `Geothermal/scripts/` because it reuses the geothermal
grid/feeder/bbox conventions, but feeding the separate heat-demand plan, not
the suitability map.

**New script** `Geothermal/scripts/build_building_stock.py` →
`Geothermal/Data/processed/buildings_ottawa.parquet` (+ `.gpkg`), one row per
building: `footprint_m2, height_m, storeys, height_source, class, vintage,
grid_cell_id, feeder_id, da_id, fsa`. Full method (backbone/backfill height
strategy, zoning classification rule, DA-level probabilistic vintage
assignment with the `community-energy-orchestrator` inspiration note, join
conventions) documented in `Geothermal/README.md` §3.10 — this entry is the
numbers.

**New fetches** (cached under `Geothermal/Data/Raw/`):
- `Geothermal/scripts/fetch_zoning_full.py` → `Data/Raw/zoning_full.geojson`
  — full City zoning layer (14,089 features, no `ZONE_MAIN` filter this
  time), same paginated-ArcGIS pattern as `fetch_municipal_layers.py`.
- `Geothermal/scripts/fetch_da_census.py` → `Data/processed/da_census.json`
  — DA-level 2021 Census Profile for Ottawa (1,392 DAs), period-of-
  construction + dwelling-type mix. StatCan's `98-401-X2021006` bulk CSV
  (`www12.statcan.gc.ca`, `GetFile.cfm?...&GEONO=006`) turned out to ship
  pre-split by region with a `Geo_starting_row` line-number index — used it
  to jump straight to Ottawa's ~3.66M-row span instead of streaming the
  full 8.78 GB Ontario file. No WAF/Referer issue this time (contrast with
  Phase 0's Canada Structures download) — plain `curl -L` worked.
- DA boundary geometries: StatCan's national 2021 DA Digital Boundary File
  (`lda_000b21a_e.zip`, 198 MB), filtered to Ottawa's CD (`DAUID LIKE
  '3506%'`) → `Geothermal/Data/processed/da_boundaries_ottawa.geojson`
  (1,392 polygons).

**Pipeline run:** 467,379 Canada Structures features in the Ottawa bbox →
**414,111 buildings** after `footprint_m2 > 40`. Height: 84.1% Canada
Structures, 1.4% NRCan LiDAR backfill, 14.5% defaulted by type. Class split:
detached 258,013 · row 99,054 · lowrise_murb 18,889 · highrise_murb 16,691 ·
commercial 11,670 · industrial 6,628 · institutional 3,166. Vintage spread
roughly matches Ottawa's known housing-age profile (1961–1980 the largest
single band at 106,857, then a fairly even spread 1981–2021, plus 62,463
pre-1960). Join coverage: grid cell 84.0%, feeder 66.0%, DA 81.2%, FSA 99.8%
(none of those three source layers tile the full bbox — expected, documented
in README §3.10, not a join bug).

**Validation vs census** (Ottawa-area FSAs only, 52 of 1,646 in
`fsa_census.json` — first run mistakenly summed all of Ontario, caught and
fixed before reporting): detached buildings vs census detached dwellings
**−4.1%** (well inside ±15%); row/semi buildings vs census semi+row
dwellings **−16.6%** (just outside ±15% — investigated: OSM's
`detached`/`house` tags can't geometrically distinguish a semi-detached pair
from two nearby standalone houses without parcel data, so some real
semi-detached stock likely counts as `detached` instead; not force-corrected,
flagged as a known soft spot at the detached/row boundary). Apartment
buildings (35,580) vs apartment dwellings (140,690) intentionally not held
to the ±15% bar — building count vs unit count is a different denominator
(~4.0 units/MURB on average, reported for context).

**Deviations from the brief:** the City's LOD1 3D-building stretch goal
(116 per-neighbourhood MultiPatch GDBs) was not attempted — height coverage
via Canada Structures + NRCan (85.5% combined) was judged sufficient for a
screening layer, all 14.5% shortfall covered by the documented type-based
storeys default. The NRCan backfill only recovered 1.4 of the ~15 points of
gap Canada Structures left (nearest-centroid join, 15 m cutoff) — a
polygon-overlap join would likely close more of it; left as a follow-up.

## 2026-07-15 session — v2 Phase D: per-segment suitability scores

ROADMAP.md item 8 Phase D. Replaces the map's one-size-fits-all reading with
**three 0–100 suitability scores per 500 m cell** for the three GSHP market
segments, which trade off depth, land, load balancing, yield and grid draw
differently. **Screening ranking, not a feasibility study.**

1. **New script** `Geothermal/scripts/build_suitability.py` (reads the
   conductivity grid as the canonical cells + the difficulty grid, wells,
   GridCapacity, zoning, sewers, City potential). Eight 0–1 factors per cell with
   documented transforms — `cond` (from the Phase B bucket shares, **recomputed
   live**), `drill` (1 − difficulty/100), `openloop` (nbhd viable share), `yield`
   (nbhd p75 yield), `feeder` (MVA/5), `zone` (industrial zoning), `sewer`
   (1 − dist/1 km), `demand` (in City serviced area — **coarse proxy** with an
   `heat_demand_grid.geojson` upgrade hook per ROADMAP item 7). Weight table
   (sums to 1/segment): **residential** drill .55 / cond .30 / openloop .15;
   **large buildings** cond .45 / drill .25 / feeder .20 / zone .10; **district**
   demand .35 / yield .20 / sewer .20 / feeder .15 / zone .10. Full method +
   weight/factor tables in README §3.9.

2. **Sanity checks before writing (all pass):** inter-segment correlations
   res↔large +0.56, res↔district **−0.18**, large↔district +0.32 (none near the
   >0.95 redundancy line); district top-decile **100 %** in the serviced urban
   area (vs 18 %) with high sewer/feeder factors; residential top-decile **0 %**
   downtown (downtown = 2.1 % of cells) with above-baseline drilling ease. Scores:
   res min 34 / med 76 / max 90; large 19 / 54 / 87; district 0 / 15 / 95
   (bimodal by construction — urban demand proxy is binary).

3. **Emitted** `Data/processed/suitability_grid.geojson` (13,778 cells == the
   conductivity cells, same order) carrying the 8 factors + 3 default-κ
   composites; added to `merge_layers.py` (now **8 tagged layers**,
   `combined_layers.geojson` 159,765 features / 57.9 MB).

4. **Map** — `build_map.py` embeds a `SUIT` array (7 static factors 0–100 per
   cell, **index-aligned with `GRID`**; conductivity is the 8th, recomputed live;
   `len(SUIT)==len(GRID)` asserted). `map_template.html` gains: a single
   toggleable purple **Suitability** choropleth, a top-left **segment radio
   selector** restyling it, a popup showing the active segment's factor
   breakdown, a legend block, and wiring so a **conductivity-panel edit flows
   into the suitability recompute** (the `cond` factor). To hold the 8 MB budget
   with `SUIT` added, capacity/zoning/potential coordinates were trimmed 5→4 dp
   (already ~10 m-simplified, so invisible).

**Chain re-run + browser-verified** (local HTTP; canvas pixel sampling + DOM per
the no-rAF quirk, `invalidateSize` to un-stick 0×0): SUIT/GRID aligned (13,778
each) and JS composites match the Python build (res 75, large 53); the
suitability layer paints and **repaints distinctly on segment switch** via the
real radio inputs (legend header tracks: "Suitability — district energy" etc.);
a district popup reads 95/100 with demand 1.00 / sewer 0.99 / feeder 1.00, a
residential popup 90/100 with drilling ease 0.90 / conductivity 0.87 (κ 2.93);
editing **granite 3.2 → 2.6** shifts both the conductivity grid (high 1,192 → 180)
**and** the residential suitability (strong cells 6,716 → 6,439), and **Reset
restores exactly**; all 8 layers toggle; **zero console errors**;
`output/index.html` **7.9 MB** (≤ 8 MB). README updated (new §3.9, §3.4/§3.5
layer counts, §4 results, §5 caveat #10, §2 pipeline + run order, §6 hook).
Committed and republished to GitHub Pages.

## 2026-07-15 session — v2 Phase C: drilling-difficulty screening layer

ROADMAP.md item 8 Phase C. A per-well drilling-difficulty score for vertical
GSHP boreholes, gridded like conductivity and shipped as a new toggleable map
layer. **Screening heuristic, not a drilling quote.**

1. **Shared IDW module** `Geothermal/scripts/idw.py` — factored the 500 m grid
   + IDW weighting (k=12, power 2, 2 km cutoff, 1.5 km confidence radius) out of
   `interpolate_conductivity.py` so `build_difficulty.py` reuses it and the two
   grids line up cell-for-cell. Refactored `interpolate_conductivity.py` onto it;
   **re-ran and confirmed byte-for-byte-equivalent output** (13,778 cells,
   medium 12,051 / high 1,138 / low 589, shares max error 0.0034 — identical to
   the Phase B build).

2. **New script** `Geothermal/scripts/build_difficulty.py` (reads the gpkg).
   Four components → `difficulty_score` 0–100 (rounded to 5), weights summing to
   100: **overburden thickness 40** (`bedrock_depth_m/30`, capped — casing to
   bedrock, the dominant driver), **problem layers 20** (count of formation
   intervals whose *primary* material is boulders/stones/quicksand/hardpan —
   7,395 wells), **rock hardness 25** (granite/gneiss 1.0 … shale 0.15; overburden
   & unknown default to the limestone baseline 0.4), **artesian 15** (neighbourhood
   share of flowing wells within 1 km — 503 flowing wells, treated as an area
   indicator not a per-well flag). 3-class label easy < 25 / moderate 25–44 /
   difficult ≥ 45. Only wells with a known depth-to-bedrock are scored (35,702).
   Full formula + rationale in README §3.8.

3. **Validation before gridding** (all three printed, all pass — one apparent
   surprise investigated and explained): (a) rock-hardness isolates cleanly —
   granite/gneiss wells are ~70 % air-percussion/rotary-air vs 24 % cable-tool;
   the *composite* "difficult" class skews cable-tool only because it's
   overburden-weighted and deep clay plain is cable-tool territory (two real
   regimes, not a bug); Diamond coring rises easy→difficult 4.6→11.8 %. (b) score
   vs total depth weak-positive (Pearson 0.10) — depth is set by yield-seeking
   hydrogeology, not difficulty, by design. (c) spatial pattern textbook — east
   clay plain overburden-driven (14.2 vs 9.1 pts), west Shield edge
   hardness-driven (12.0 vs 7.9).

4. **Gridded** to `Data/processed/difficulty_grid.geojson` — 13,403 cells at
   500 m (score 5–75): **easy 5,750 / moderate 6,264 / difficult 1,389**
   (43/47/10 %); dominant driver overburden 6,911 / hardness 6,091 / artesian
   366 / problem 35; 87 % high-confidence. Each cell carries the full
   overburden/problem/hardness/artesian point breakdown for the popup.

5. **Wired into the map** — `merge_layers.py` adds `difficulty_grid` (now 7
   tagged layers, `combined_layers.geojson` 145,987 features / 52.5 MB);
   `build_map.py` embeds compact `[w,s,e,n,hi,score,ov,pr,hd,ar]` tuples (static,
   no client recompute); `map_template.html` gains a toggleable YlOrRd
   choropleth (easy #ffffb2 / moderate #fd8d3c / difficult #bd0026), a legend
   block, and a popup breakdown (score/class, dominant driver, the four
   component point contributions, confidence).

**Chain re-run + browser-verified** (local HTTP; canvas pixel sampling per the
no-rAF quirk, plus `invalidateSize` to un-stick the 0×0 initial map size):
difficulty layer present in the control with 13,403 cells; toggled on, the
canvas paints all three classes (moderate 468k px, easy 405k px, difficult
103k px) + low-confidence grey; a high-conf difficult cell's popup reads
"45 / 100 (difficult)" with overburden 15/40, problem 5/20, hardness 10/25,
artesian 15/15, confidence high; **zero console errors**; `output/index.html`
**7.8 MB** (≤ 8 MB budget). README updated (new §3.8 method, §4 results, §5
caveat #9, §2 pipeline + run order, §3.4/§3.5 layer counts). Not yet
republished to GitHub Pages (rebuilt files show modified/uncommitted).

## 2026-07-15 session — v2 Phase B: sourced conductivity table + live sensitivity

ROADMAP.md item 8 Phase B. Two deliverables: a literature-sourced conductivity
reference table, and an in-map panel to edit per-bucket conductivities with an
**exact** client-side recompute of the whole surface.

1. **Reference table** `Geothermal/Data/conductivity_reference.csv` — one row
   per bucket (14), columns `bucket, default_wmk, min_wmk, max_wmk, notes,
   source`. Ranges sourced from **VDI 4640 Blatt 1:2010** (the GSHP design
   standard), whose min/rec/max table is transcribed exactly in **Busby 2011
   (BGS)**; corroborated by **ASHRAE** (Kavanaugh & Rafferty 2014, Tables
   3.3/3.4) and **Banks 2012**. Validation finding: **all 14 current defaults
   already fall within their VDI 4640 ranges — none needed changing.** Two
   buckets (`fill`, `rock`) have no direct GSHP-literature category and are
   documented screening placeholders. Soil buckets carry the saturated-vs-dry
   note (sand is the extreme: ~0.4 dry vs 2.4 saturated); one default per
   bucket, using the saturated value (wells sit below the water table). Full
   table + citations in README §3.7.

2. **Shared loader** `Geothermal/scripts/conductivity.py` reads the CSV
   (fixing the canonical `BUCKET_ORDER`, indices 0–13); `combine_wells.py`,
   `interpolate_conductivity.py` and `build_map.py` all use it — the hard-coded
   `CONDUCTIVITY_WM` is now only a fallback.

3. **Exact client-side sensitivity.** IDW is linear in per-well values, so
   `interpolate_conductivity.py` now emits each cell's per-bucket IDW **weight
   shares** (`bucket_shares`, sparse `[[idx,share],…]`, quantised to 3 dp,
   shares < 0.001 dropped + renormalised; avg 2.6 buckets/cell). Verified
   reconstruction vs the exact surface: **max error 0.0034 W/m·K** (< 0.01).
   Shares flow through `merge_layers.py` into `build_map.py`'s compact grid
   tuples `[w,s,e,n,hi,shares]`; wells now carry a `bucket_idx` instead of a raw
   conductivity, and the reference table + bucket names are embedded for the UI.

4. **Map UI** (`map_template.html`) — collapsible bottom-right "Conductivity
   assumptions" panel: 14 editable inputs clamped to `[min,max]`, default+range
   shown, source in a hover tooltip, **Reset all** button. On edit: every grid
   cell recomputes as `Σ share×κ`, the canvas choropleth restyles (with a
   **forced synchronous redraw** — this env has no rAF), the legend's live
   per-class counts refresh, and each well popup recomputes its conductivity
   from its bucket at open time. **Well marker colours stay on open-loop
   feasibility, not conductivity** (documented in the panel — editing κ would
   otherwise conflate two variables on one symbol).

**Chain re-run + browser-verified** (served over local HTTP; verification via
`javascript_tool` DOM manipulation + **canvas pixel sampling**, per the no-rAF
preview quirk): editing **granite 3.2 → 2.6** shifts Shield cells out of the
high class (**high 1,192 → 180**, medium 11,989 → 12,992; grid-canvas green
pixels 92,779 → 12,983 — real repaint), **Reset** restores exactly (green back
to 92,779, legend + inputs restored), inputs clamp (5.0→4.1, 1.0→2.1,
invalid→default), a granite well's popup conductivity tracks 3.2→2.6→3.2, all 6
layers toggle, **zero console errors**. `output/index.html` **7.2 MB** (≤ 8 MB
budget). combine_wells re-run confirms identical class counts (medium 45,963 /
low 7,351 / high 1,847 / unknown 742) — the CSV values match the prior inline
defaults. README §3.3, §3.5 updated + new §3.7 "Conductivity assumptions &
sources". Not yet republished to GitHub Pages (rebuilt files show as modified,
uncommitted).

## 2026-07-15 session — v2 Phase A: well-data quality fixes

ROADMAP.md item 8 Phase A. Fixed five categorization/missing-data issues in
`combine_wells.py` and rebuilt the whole chain (combine_wells →
interpolate_conductivity → merge_layers → build_map).

1. **`status` "code:0" (464 wells)** — `_code_final_status.csv`'s code-0 row
   has a blank `DES`; `decode()` treated any code whose table lookup landed
   on a blank/NaN description as unresolved and fell through to `code:NN`.
   Fixed: blank/NaN description now decodes to `"Not specified"`. Same fix
   also normalizes `_codeWaterUse`'s "Commerical" → "Commercial" typo at
   decode time (raw CSV untouched).
2. **`well_use` fallback to `USE_2ND`** — recovers 36 of the 8,123
   `well_use`-null wells (8,087 remain null in both columns — genuinely not
   recorded).
3. **Geometry recovery** — 67 of the 5,068 no-geometry wells recovered from
   `tblBore_Hole`'s `ZONE`/`EAST83`/`NORTH83` (NAD83 UTM 17/18 → 4326); each
   well now carries `geometry_source` (`shp`|`borehole`). 5,001 remain
   irreducible (no coordinates anywhere in the export).
4. **`bedrock_depth_m` fallback** — 10,885 of the 27,428 missing-depth wells
   recovered from the shallowest bedrock-bucket formation interval's
   `top_depth_m`; `bedrock_depth_source` (`shp`|`formations`) added. On
   28,415 wells where both the shapefile value and the formations-derived
   value exist, median absolute difference is 0.02 m (negligible — no
   investigation needed). 16,543 wells remain without a bedrock depth.
5. **Lithology fallback from GSC mapped geology** — spatial-joined the 8,444
   unknown-lithology wells with usable geometry to
   `Data/Raw/GSC/gsc_bedrock_geology.gdb.zip` (`Wheeler_Bedrock` layer, read
   directly from the zip via pyogrio); recovered 8,438. `lithology_source`
   (`well_log`|`gsc_map`) added to the wells layer and carried through
   `merge_layers.py` and `build_map.py` into the well popup, since GSC-based
   lithology is weaker evidence than a driller's log. Persisted the winning
   lithology as a new `lithology` column on the wells layer (previously
   `build_map.py` recomputed a display lithology from
   `bedrock_lithology`/`primary_lithology` only, which silently dropped the
   GSC fallback from the popup — caught and fixed during browser
   verification, see below).

**Conductivity-class counts, before → after:** unknown 9,180 → **742**;
medium 37,671 → 45,963; low 7,351 → 7,351 (unchanged); high 1,701 → 1,847.
Full before/after and method detail: `Geothermal/README.md` §3.1, §4, §5.

**Chain re-run:** wells 55,903 (50,902 with geometry) · conductivity grid
13,778 cells (medium 12,051 / high 1,138 / low 589) · `combined_layers.geojson`
132,584 features / 46.7 MB · `output/index.html` 7.1 MB.

**Verified in a live browser preview** (served over local HTTP — `file://`
navigation is blocked in this environment, and full-page screenshots time
out here per the no-rAF preview-renderer quirk, so verification used
`javascript_tool` to inspect `WELLS`/`GRID` array lengths, open specific
well popups programmatically via `openPopup()` + `getPopup().getContent()`,
and read `read_console_messages`): zero console errors, 50,846 wells and
13,778 grid cells loaded, and popups for a GSC-lithology well, a
borehole-recovered-geometry well, and a formations-fallback-bedrock-depth
well all show the correct source-flag annotations — e.g. "limestone (GSC
mapped geology)", "12.2 m (formations fallback)", "Location source:
borehole record".

Not yet republished to GitHub Pages — do that alongside a future phase or on
request (`git status` currently shows the rebuilt gpkg/geojson/html as
modified, not committed).



## 2026-07-10 session — committed and published

All pipeline outputs and scripts committed to `main` (commit `cf1c862`), including
the `_code_*.csv` lookup tables, the rebuilt `ottawa_geothermal.gpkg`, all six
processed GeoJSON/TIFF layers, and `output/index.html`. Nothing needed
gitignoring — even the largest processed file (`combined_layers.geojson`, 40 MB)
is well under GitHub's 100 MB hard limit.

Published via the same GitHub Pages setup already serving `retrofits.html` /
`ceud.html` / `construction.html` from the repo root: GitHub Pages resolves
extensionless URLs by trying `path`, then `path.html`, then `path/index.html`, so
`Geothermal/output/index.html` is reachable directly at
`.../Energy/Geothermal/output/`. (In the process, found the `retrofits.html` live
link documented in `Readme.MD` pointed at a repo name — `Ottawa-Visuals` — that
404s; the working one is `.../Energy/retrofits`. Fixed both links.)

Verified live in a browser preview: page loads with no console or network errors,
all six layer checkboxes toggle, zoom controls work, and a well marker's popup
renders real data (ID, open-loop status, lithology, conductivity, yield, static
water level, depth).

## Pipeline status

| Guide step | Status | Output |
|---|---|---|
| 1. WWIS quality audit | done (June 2026) | `Geothermal/Data/Raw/WWIS/analyze*.py`, scatter PNGs, `wwis_data_quality_comparison_v2.xlsx` |
| 2. Clean & filter WWIS | done | `Geothermal/Data/processed/wwis_ottawa.geojson` |
| 3. Thermal conductivity per well | done | `Geothermal/Data/processed/thermal_conductivity.geojson` |
| 4. Open-loop feasibility | done | `Geothermal/Data/processed/open_loop_feasibility.geojson` |
| — Rich relational build (supersedes 2–4) | done, rebuilt 2026-07-09 with full code tables | `Geothermal/Data/processed/ottawa_geothermal.gpkg` via `combine_wells.py` |
| 5. Ottawa municipal layers | done 2026-07-09 (footprints & city-owned properties deferred — see below) | `zoning_industrial.geojson`, `sewer_lines.geojson`, `city_open_loop_potential.geojson` via `fetch_municipal_layers.py` |
| 6. Interpolated conductivity surface | done 2026-07-09, incl. GeoTIFF | `thermal_conductivity_grid.geojson` + `.tif` via `interpolate_conductivity.py` |
| 7. Merge layers | done 2026-07-09, 6 layers | `Geothermal/Data/processed/combined_layers.geojson` via `merge_layers.py` |
| 8. Interactive HTML map | done 2026-07-09, 6 toggleable layers | `Geothermal/output/index.html` via `build_map.py` |
| — Grid capacity (OEB CCIM) | done (July 2026) | `GridCapacity/ottawa_capacity.geojson` via `GridCapacity/Hydro.py` |

## 2026-07-09 session — steps 6–8 built and run

Environment: installed `geopandas 1.1.4`, `shapely 2.1.2`, `scipy 1.18.0`,
`pyogrio` into the system Python 3.14 (pandas/numpy/pyproj were already there).

### 1) `combine_wells.py` re-run (verify gpkg matches the rewritten script)

Rebuilt `ottawa_geothermal.gpkg` cleanly. Layer counts:

| layer | rows |
|---|---|
| wells | 55,903 (5,068 without shapefile geometry) |
| formations | 144,719 |
| water | 62,324 |
| pump_tests | 44,026 |
| construction | 125,495 |

Derived screening: conductivity class medium 35,183 / unknown 14,000 / low 6,535 /
high 185; open-loop viable 31,783 / possible 3,603 / unlikely 20,517.
All code lookups used the built-in fallbacks (no `_code_*.csv` exported yet —
exporting them from the Access db would upgrade the ~14k "unknown" lithologies).

### 2) New script: `Geothermal/scripts/interpolate_conductivity.py` (step 6)

IDW (k=12, power 2) on a 500 m grid in UTM 18N, from the gpkg wells layer
(37,916 wells with a conductivity estimate after clipping to the guide's Ottawa
bbox — the clip drops 17 mis-located wells that otherwise scattered 734 stray
cells across Ontario). Cells only emitted where the nearest well is ≤ 2 km;
confidence = high when ≥ 5 wells sit within 1.5 km.

Result: **13,376 cells** — medium 11,777 / low 1,379 / high 220; confidence
high 11,777 / low 1,599; range 1.40–2.99 W/m·K.
Not produced: the guide's optional GeoTIFF twin (needs `rasterio`; the GeoJSON
grid is what the map consumes).

### 3) New script: `Geothermal/scripts/merge_layers.py` (step 7)

Merges into one FeatureCollection with a `layer` property per feature
(`conductivity_grid`, `wells`, `grid_capacity`). Wells come from the gpkg
(bbox-clipped, slimmed to popup fields); capacity polygons are simplified
(~10 m) and slimmed; coordinates rounded to 5 decimals.

Result: `combined_layers.geojson`, **68,068 features, 24.1 MB**
(13,376 grid cells + 50,808 wells + 3,884 feeder polygons).

### 4) New scripts: `build_map.py` + `map_template.html` (step 8)

`Geothermal/output/index.html` — single self-contained Leaflet map (5.9 MB).
To keep it small the grid is embedded as `[w,s,e,n,cond,confidence]` tuples and
wells as compact arrays; only feeder capacity stays as GeoJSON. Full-fidelity
GeoJSON remains in `Data/processed/`. Three toggleable canvas-rendered layers
(conductivity choropleth, wells coloured by open-loop status, feeder capacity
red→green by MVA), popups on everything, fixed legend. OSM basemap from CDN —
the only part needing internet.

Verified in a local browser preview: all 50,808 well markers render, popups show
correct values for all three layers, no console errors, wells layer adds in
~190 ms. (Quebec side of the river is empty by construction — WWIS is
Ontario-only.)

### Grid capacity data (already fetched, now integrated)

`GridCapacity/ottawa_capacity.geojson`: 3,884 Hydro Ottawa feeder polygons from
the OEB Centralized Capacity Information Map ArcGIS service. Available capacity
0–16.4 MVA; range buckets: 0–1 MVA ×1,348, 1.1–3 ×1,655, 3.1–5 ×420,
5.1–10 ×288, 10+ ×34, unknown ×139. `last_update` in the data ≈ 2026-05-01;
re-run `GridCapacity/Hydro.py` to refresh.

## Gap-closure session (2026-07-09, second pass)

All three data gaps from the first pass were addressed:

### 1) WWIS lithology code tables exported → ~4,300 wells recovered

Exported the seven `_code_*.csv` lookup tables from the Access db
(`Data2024Q4 250723 181853.mdb`, via pyodbc) into `Geothermal/Data/`, where
`combine_wells.py` auto-prefers them over its built-ins. The formation-material
table has **82 codes vs the 15 built-ins** (codes 60–92 are texture modifiers,
correctly left unbucketed). Also extended `combine_wells.py`'s lithology
buckets (marl→clay, conglomerate/greywacke→sandstone, marble→limestone,
schist/soapstone→gneiss, quartz/chert/feldspar/flint→granite, basalt new bucket
at 2.0 W/m·K, overburden→till, quicksand→sand, gypsum→shale).

Result: conductivity-class unknowns **14,000 → 9,680**; high 185 → **1,700**
(Shield granite/gneiss wells now decoded); medium 36,965; low 7,558.
Downstream, the interpolation now uses 41,921 wells (was 37,916) and
high-conductivity cells rose 220 → **1,137**; surface range 1.40–3.20 W/m·K.

### 2) Step 5 municipal layers fetched (`fetch_municipal_layers.py`)

From the City's ArcGIS server (maps.ottawa.ca/arcgis/rest/services):

| output | source layer | features |
|---|---|---|
| `zoning_industrial.geojson` | Zoning/3, `ZONE_MAIN IN (IL,IG,IH,IP,RG,RH)` | 618 |
| `sewer_lines.geojson` | WastewaterInfrastructure/7 (sanitary) + /14 (combined) | 63,300 (17.3 MB) |
| `city_open_loop_potential.geojson` | Planning/122 — the City's own **Open Loop Geothermal Potential** layer (High/Average/Low/None) | 158 |

Gotchas recorded for reruns:
- `f=geojson` returns HTTP 400 on the WastewaterInfrastructure layers — the
  script uses esriJSON + a converter for those.
- The Zoning layer's `ZNAME_EN` mislabels IG as "Transportation Zones";
  By-law 2008-250 Part 11 defines IG = General Industrial. `build_map.py`
  ships canonical names from its own `ZONE_NAME` table.

**Deferred, deliberately:** building footprints (TopographicMapping/3 is 392k
polygons ≈ 0.5 GB; nothing consumes them yet) and city-owned properties (the
guide's dataset no longer exists on open.ottawa.ca — searched 2026-07-09).

### 3) GeoTIFF export added

`interpolate_conductivity.py` now also writes
`thermal_conductivity_grid.tif` (EPSG:32618, 500 m, NaN = no coverage;
requires `rasterio`, installed).

### Rebuilt outputs

- `combined_layers.geojson`: now **132,151 features / 41.2 MB** across six
  layers (conductivity_grid 13,383 · wells 50,808 · grid_capacity 3,884 ·
  zoning_industrial 618 · sewer_lines 63,300 · city_open_loop_potential 158).
- `output/index.html`: **6.7 MB**, six toggleable layers. Only trunk sanitary
  (`FUNCTION <> LOCAL`) + all combined sewers are embedded (5,491 polylines,
  0.5 MB) — local laterals stay in the processed GeoJSON. Verified in a live
  browser: no console errors, popups correct on all six layers (incl. the IG
  fix), municipal layers render where expected (combined sewers cluster in the
  old core; city potential covers the urban area).

## Third pass (2026-07-09): documentation + validation + lithology polish

- **Process documentation** consolidated into `Geothermal/README.md` — data
  sources, method details per script, results, caveats, next steps. This file
  stays the session-by-session build log.
- **New script `validate_against_city.py`** — spatial join of all wells to the
  City's Planning/122 potential polygons, crosstab + per-class yield stats
  (output: `Data/processed/city_validation.csv`). Findings: 32,807 of 50,808
  wells are outside the City layer (it only rates the serviced urban area —
  complementary coverage, not disagreement); within it, mean pump-test yield
  orders the City's classes correctly (High 76 L/min → Average 37 → Low/None
  27); our "unlikely" wells inside High/Average polygons are mostly
  missing-data cases, not contradictions.
- **Lithology recovery, round 2** in `combine_wells.py`: primary lithology now
  comes from the thickest *bucketable* layer (a well whose thickest interval
  has no recorded material no longer gives up), and generic "ROCK" (code 26)
  became its own bucket at 2.5 W/m·K (counts as bedrock). Unknowns
  9,680 → **9,180**; 7,872 of those have no formation record at all
  (checked — irreducible). Wells class mix now: medium 37,671 / low 7,351 /
  high 1,701.
- **Full chain re-run** (combine → interpolate → merge → build_map →
  validate): grid 13,383 cells (medium 11,174 / high 1,107 / low 1,102,
  1.40–3.20 W/m·K); `combined_layers.geojson` 132,151 features / 41.2 MB;
  `output/index.html` 6.8 MB. Map template unchanged from the verified build;
  only embedded data values changed.

## Remaining ideas / next steps

**v2 rework — see ROADMAP.md item 8** (4 phases with paste-able prompts):
A) well-data fixes (**done 2026-07-15**); B) literature-sourced conductivity
reference table + in-map editable per-bucket values with exact client-side
recompute (per-cell IDW bucket-weight shares) (**done 2026-07-15**);
C) drilling-difficulty score & grid layer (overburden, problem layers, hard
rock, artesian) (**done 2026-07-15**); D) per-segment suitability scores
(residential / large buildings / district energy) (**done 2026-07-15**, §3.9).
**All four phases complete.**

Other ideas: see `Geothermal/README.md` §6. Highlights not covered by v2:
closed-loop borehole-metres-per-kW economics per cell; building footprints
for heat demand (ROADMAP item 7); sewer heat-recovery flow estimates.

## Regenerating everything

```bash
python Geothermal/scripts/combine_wells.py             # gpkg from WWIS exports (+ _code_*.csv)
python Geothermal/scripts/fetch_municipal_layers.py    # step 5 city layers (zoning/sewers/potential)
python Geothermal/scripts/interpolate_conductivity.py  # step 6 conductivity surface (geojson + tif)
python Geothermal/scripts/build_difficulty.py          # Phase C drilling-difficulty grid (shares idw.py)
python Geothermal/scripts/build_suitability.py         # Phase D per-segment suitability scores
python Geothermal/scripts/merge_layers.py              # step 7 combined layers
python Geothermal/scripts/build_map.py                 # step 8 output/index.html
python GridCapacity/Hydro.py                           # refresh feeder capacity

# Heat Demand Phases 1-3 (building stock + load; independent of the map chain above)
python Geothermal/scripts/fetch_zoning_full.py         # full zoning layer -> Data/Raw/zoning_full.geojson
python Geothermal/scripts/fetch_da_census.py           # DA-level census profile -> Data/processed/da_census.json
python Geothermal/scripts/build_building_stock.py      # -> Data/processed/buildings_ottawa.{parquet,gpkg}
                                                       #    (incl. the Phase 2.5 reconcile_stock step)
python Geothermal/scripts/build_building_demand.py     # augments the parquet with annual_kwh/design_kw/fuel
python Geothermal/scripts/build_electrified_load.py    # Phase 3: adds elec_kwh_*/elec_kw_peak_* electrified columns
```

**Reading the outputs:** take every city-wide sum over `in_ottawa_cd == True`
(the bbox reaches into surrounding townships; the census is city-only), and
treat the `accessory` class as non-dwelling/unheated. See README §3.10.1.
