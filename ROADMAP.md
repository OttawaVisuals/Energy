# Energy Suite — Roadmap & Build Prompts

Master plan for finishing the in-flight projects and starting the new ones, written
2026-07-10. Each item has paste-able Claude Code prompts (run from `C:\Energy`) with a
suggested model. Companion docs: [PLAN.md](PLAN.md) (heat pump), [CEUD_PLAN.md](CEUD_PLAN.md),
[CONSTRUCTION_PLAN.md](CONSTRUCTION_PLAN.md), [GEOTHERMAL_STATUS.md](GEOTHERMAL_STATUS.md).

**Status snapshot (2026-07-10):**

| Project | State |
|---|---|
| Retrofit Explorer | ✅ done, deployed |
| Construction Tracker | ✅ done, deployed, monthly auto-refresh |
| CEUD Explorer | ✅ done (all 5 sectors live) |
| Geothermal | ⚠️ built & verified, **uncommitted + unpublished** |
| Heat Pump tool | 🔨 Phases 1–2 of 7 done; no `heatpump.html` yet |
| Energy prices | 🆕 new — consume MaxPr1me/canada-utility-rates |
| Landing page | 🆕 new |
| Live grid dashboard | 🆕 new — reuses HeatPump Phase 1 pipelines |
| Ottawa heat demand map | 🆕 new — fuses Geothermal + GridCapacity + ERS |

**Recommended order:** 1 → 2 → 3 (multi-session) → 4 → 5, with 6 and 7 as
independent follow-ons whenever. Item 4 should land before Heat Pump Phase 6 (UI)
so operating costs can ship in the tool's v1.

---

## 1. Ship the Geothermal map (≈1 session, quick win)

Everything works locally but nothing is committed: `git status` shows
`GEOTHERMAL_STATUS.md`, `Geothermal/README.md`, five scripts, all processed outputs,
and `Geothermal/output/` untracked, plus modified `combine_wells.py` and the gpkg.
And publishing to GitHub Pages is the top "next step" in the status file.

### Prompt — commit + publish (Sonnet)

```text
Read GEOTHERMAL_STATUS.md and Geothermal/README.md first. Two tasks:

1. COMMIT the finished geothermal work. Review git status: stage the geothermal
   scripts, README, status doc, GEOTHERMAL_STATUS.md, the _code_*.csv lookup
   tables, and Geothermal/output/index.html. For the large processed outputs
   (combined_layers.geojson 41 MB, sewer_lines.geojson 17 MB, the .tif), check
   each against GitHub's 100 MB hard limit and decide: commit if reasonably
   sized and useful to consumers, otherwise gitignore and note in the README
   how to regenerate them. The modified ottawa_geothermal.gpkg should be
   committed (it is the canonical dataset). Write a clear commit message
   summarizing the pipeline completion.

2. PUBLISH the map. The other tools (retrofits.html, ceud.html,
   construction.html) are served via GitHub Pages — inspect how this repo /
   the OttawaVisuals account does it (check for existing Pages config, the
   BASE_URL pattern in retrofits.html, and the live URL in Readme.MD) and
   follow the same pattern so Geothermal/output/index.html is reachable at a
   stable public URL. The map is fully self-contained (6.8 MB, only the OSM
   basemap loads from CDN) so no data-hosting changes are needed.

Verify the published URL loads in a browser preview (all six layers toggle,
popups work). Then add the live link to the top of Geothermal/README.md and
Readme.MD, and update GEOTHERMAL_STATUS.md.
```

---

## 2. Repo housekeeping — AHRI legacy files (½ session)

Root-level clutter: `ahri_certificates/` (38 PDFs), `ahri_certificates_parsed.csv`,
`ahri_directory_check.csv`, `ahri_numbers_seen.{csv,json}`. Per
`Python/build_ahri_lookup.py`'s docstring, the certificate-PDF workflow is **legacy**
— superseded by the direct AHRI Directory fetch that writes `lookup/ahri_numbers.json`
for retrofits.html. But `ahri_numbers_seen.csv` is *not* junk: it is the popularity
ranking of heat pump models in the ERS data, and item 3 below uses it.

### Prompt (Sonnet)

```text
Housekeeping in C:\Energy. Read the docstrings of Python/build_ahri_lookup.py,
Python/parse_ahri_certificates.py and Python/list_ahri_numbers.py first so you
understand which AHRI workflow is current (directory fetch → lookup/
ahri_numbers.json, consumed by retrofits.html) and which is legacy
(certificate PDFs → ahri_certificates_parsed.csv).

1. Move the legacy artifacts (ahri_certificates/ PDFs,
   ahri_certificates_parsed.csv, ahri_directory_check.csv) into a new
   Python/ahri_archive/ folder (or gitignore them if never committed) with a
   short README saying they're superseded and by what.
2. KEEP ahri_numbers_seen.csv/json accessible — they are the input for the
   heat pump popularity analysis (see ROADMAP.md item 3). Move them next to
   the scripts that produce them (Python/) and update any paths in
   list_ahri_numbers.py / build_ahri_lookup.py accordingly. Re-run whatever
   is cheap to re-run to confirm nothing broke.
3. Do NOT touch lookup/ahri_numbers.json (live site dependency).

Update Readme.MD's repository-layout section if it references moved paths.
```

---

## 3. Heat Pump tool — Phases 3–7

The flagship unfinished project. Phases 1–2 (grid EF for ON/AB/QC, weather + TMY)
are done — see [HeatPump/METHODOLOGY.md](HeatPump/METHODOLOGY.md). What remains:
the deferred EF lookup surface, equipment curves (**revised approach below**),
archetypes, the simulation engine, the UI, and validation.

### 3a. Revised Phase 3 approach: NEEP buckets + spec-sheet deep-dive

Instead of hand-picking representative units from NEEP and interpolating everything
from its 3–4 rating points, do this:

1. **Bucket the NEEP ccASHP database into performance tiers.** For every unit,
   compute two screening metrics from the NEEP rating points:
   - **COP at 5 °F (−15 °C)** — cold-climate efficiency;
   - **capacity retention** = max capacity at 5 °F ÷ rated capacity at 47 °F.
   Cluster (or quantile-cut) the population into tiers, e.g.:
   - **Tier 1 "cold-climate premium"** — top-decile COP@5°F *and* retention ≳ 90–100 %;
   - **Tier 2 "mid-market cold-climate"** — median COP, retention ~70–85 %;
   - **Tier 3 "baseline"** — low COP@5°F, retention ≲ 60 %, higher min-operating temp.
2. **Pull 2–3 real model numbers per tier** (units near each tier's centroid, from
   major brands with public engineering manuals).
3. **Fetch the manufacturers' detailed spec sheets / engineering data books** for
   those models — they publish capacity & input power at many more temperature
   points (often −30 °C to 15 °C in 5 °C steps, at several indoor conditions) than
   NEEP's 3–4 points. Build the piecewise curves from *that* data; use the NEEP
   points as a cross-check (flag any >10 % disagreement).
4. **Add an "average installed" bucket from our own retrofit data.** The ERS
   pipeline already extracts `Pre_/Post_HPAHRI` (AHRI reference numbers) and
   `Python/ahri_numbers_seen.csv` ranks them by frequency (top unit: 5,465
   occurrences). Cross-match the top ~10 AHRI numbers to NEEP entries (via
   brand/model in `lookup/ahri_numbers.json`); the popularity-weighted composite
   of the matchable ones becomes the tool's default "typical heat pump Canadians
   actually installed" — a genuinely novel feature no other calculator has.

The UI then offers ~4 buckets (Tier 1 / Tier 2 / Tier 3 / Average installed)
instead of a bewildering model picker, each backed by real spec-sheet curves.

### Prompt — Phase 3a: NEEP acquisition + bucket analysis (Opus)

```text
Read PLAN.md (Phases section + methodology decisions) and ROADMAP.md item 3a
in C:\Energy first. Goal: bucket the NEEP cold-climate ASHP database into
performance tiers and select representative models.

1. Acquire the NEEP ccASHP product list (ashp.neep.org). Look for a bulk
   download (CSV/Excel export or the site's JSON API). If WebFetch is blocked
   for the domain use curl -L (see memory notes re gov/utility sites). Save
   the raw file under HeatPump/data/raw/neep/ and document the retrieval in
   HeatPump/METHODOLOGY.md.
2. Build HeatPump/pipeline/neep_buckets.py:
   - parse capacity (min/rated/max) and COP at 47/17/5 °F (and −13 °F where
     present) per unit; convert to SI;
   - compute per unit: COP@5°F, capacity retention (max cap @5°F / rated cap
     @47°F), min operating temperature, and rated capacity class (bin into
     ~2/3/4-ton classes so tiers compare like-for-like sizes);
   - quantile-cut or k-means into 3 tiers per ROADMAP.md item 3a; print the
     tier boundary stats and population counts;
   - for each tier, output the 5 units nearest the tier centroid that belong
     to major brands (Mitsubishi, Daikin, Fujitsu, LG, Samsung, Carrier/
     Midea, Gree, Lennox, Trane) — these are spec-sheet lookup candidates.
3. Cross-match the top ~10 AHRI numbers from Python/ahri_numbers_seen.csv
   against the NEEP list using brand+outdoor model from lookup/
   ahri_numbers.json (normalize model strings; * wildcards and revision
   suffixes will need fuzzy matching — document match rate). Report which
   popular units matched, their tier positions, and the popularity-weighted
   mean COP@5°F / retention of the matched set (this seeds the "average
   installed" bucket).
4. Output: HeatPump/data/interim/neep_tiers.csv (unit → metrics → tier) and
   a short markdown report HeatPump/data/interim/neep_tier_report.md with
   the tier definitions, candidate models per tier, and the AHRI match
   results. Update METHODOLOGY.md. Do NOT build final curves yet — that is
   Phase 3b after the user picks/approves the candidate models.
```

### Prompt — Phase 3b: spec-sheet curves (Opus)

```text
Read PLAN.md, ROADMAP.md item 3a, HeatPump/data/interim/neep_tier_report.md
and HeatPump/METHODOLOGY.md first. The representative models per tier are
chosen; now build the real performance curves.

1. For each selected model, find the manufacturer's engineering data book /
   extended performance tables (capacity and input power vs outdoor temp,
   ideally −30 °C to +15 °C, at nominal indoor conditions and max compressor
   speed). Save PDFs/extracts under HeatPump/data/raw/spec_sheets/<brand>/.
   Record exact document titles, URLs and table numbers in METHODOLOGY.md.
2. Build HeatPump/pipeline/build_hp_curves.py:
   - digitize the spec-sheet points into per-model capacity(T) and COP(T)
     piecewise-linear curves in SI, at max capacity operation;
   - below the coldest published point: extrapolate capacity linearly, floor
     COP at (coldest published COP − 0.3), zero output below the model's
     minimum operating temperature;
   - apply a defrost derate of 7% to COP between −7 °C and +4 °C unless the
     spec sheet states defrost-inclusive ratings (check and record per model);
   - cross-check each curve against the model's NEEP 47/17/5 °F points —
     flag deviations > 10% and investigate before accepting;
   - aggregate models within a tier into one normalized tier curve
     (capacity as fraction of rated @47 °F, so the UI can scale to any
     nominal size), and build the "average installed" curve as the
     popularity-weighted blend from the Phase 3a AHRI matches;
   - add a GSHP curve set: COP vs entering water temperature from AHRI/ISO
     13256 rating points for 2–3 representative water-to-air units (per
     PLAN.md), with EWT for Ottawa-area vertical loops documented.
3. Output: HeatPump/data/processed/hp_curves.json (tier curves + per-model
   curves + GSHP) and a matplotlib sanity plot per tier (capacity + COP vs
   T with the NEEP check points overlaid). Write tests asserting capacity
   and COP monotonicity above −15 °C and continuity at segment joints.
   Update METHODOLOGY.md with every assumption.
```

### Prompt — EF lookup surface (deferred from Phase 1) (Sonnet)

```text
Read HeatPump/METHODOLOGY.md (Phase 1 + Phase 2 sections) and PLAN.md
methodology decision #2 first. Weather data now exists
(HeatPump/data/interim/weather_hourly.csv, tmy_hourly.csv), which unblocks
the deferred temp × hour-of-day × season EF lookup.

Build HeatPump/pipeline/build_ef_surface.py: join each province's hourly
average+marginal EF series (data/processed/grid_ef_on.json, _ab, _qc) with
the matching hourly temperature history, then bin EF by temperature (2 °C
bins) × hour-of-day × season over the full overlapping history. Output one
compact lookup JSON per province into data/processed/ (target < 100 KB
each): mean average-EF and mean marginal-EF per bin, plus bin sample counts
so the engine can fall back to coarser bins when a cell is thin (< 20 h).
Validate: reconstruct annual average intensity from the surface applied to
the historical temperature series — must land within ±10% of the directly
computed annual figure from Phase 1; print the comparison. Document method
and the thin-bin fallback in METHODOLOGY.md.
```

### Prompt — Phase 4: archetypes (Sonnet)

```text
Read PLAN.md (Phase 4) and ROADMAP.md item 3. Build heating-load archetypes
for the launch cities (Ottawa, Toronto, Montreal, Calgary or Edmonton) from
the ERS parquet produced by Python/ers_web_pipeline.py.

For each city (select by FSA prefix) derive 3–4 archetypes: pre-1980
detached, 1980–2005 detached, post-2005 detached, townhouse/row. For each:
median design heat loss (kW at design temp — the data's EGHDESHTLOSS-derived
Pre_HeatLoss), floor area, and annual space-heating energy; back out UA
(W/K) and balance-point temperature assuming internal+solar gains offset
load above ~15–16 °C (state the assumption; calibrate Tbalance so the
UA × HDH annual load reproduces the ERS median annual heating energy within
±10% using that city's TMY series from HeatPump/data/interim/).
Use PRE-retrofit values (the tool models replacing heating in an existing,
un-retrofitted home) — note this choice. Output
HeatPump/data/processed/archetypes.json ({city: {archetype: {UA, Tbalance,
design_heat_loss_kW, floor_area_m2, annual_heat_kWh, n_homes}}}), a
validation printout comparing reconstructed vs observed annual load, and a
METHODOLOGY.md section. Cross-check one archetype against NRCan published
typical values and note the delta.
```

### Prompt — Phase 5: simulation engine (Opus)

Use the existing Phase 5 prompt in [PLAN.md](PLAN.md) §"Paste-able Claude Code
prompts" as-is, with two amendments: the heat pump input is a **tier curve from
`hp_curves.json`** (normalized curve × user-selected nominal capacity), and the
hourly EF comes from the **Phase-1-deferred EF surface** (average/marginal toggle
per methodology decision #1).

### Prompt — Phase 6: UI (Opus — design-heavy)

```text
Read PLAN.md (goal, methodology decisions, Phase 6) and ROADMAP.md items 3–4
first, and skim retrofits.html + ceud.html for the shared design system
(navy #0B2545 / amber #E8A124 / cream #F7F4EE, Fraunces + Inter, white
cards, sticky header, Simple/Advanced toggle, BASE_URL localhost pattern).

Build heatpump.html (single self-contained file, sibling of the other
tools). Inputs: city, archetype (with "which is my home?" helper text),
current heating (gas furnace / oil furnace / electric baseboard, with
efficiency), heat pump bucket (Tier 1 / Tier 2 / Tier 3 / Average installed
— explain each in one plain-English line), nominal size (auto-suggested
from archetype design heat loss with a sizing note), backup type, control
strategy, and an average vs marginal emissions toggle (Advanced; default
marginal for "new load" per methodology decision #1, with an in-page
explainer). The engine.js simulation from Phase 5 runs client-side on every
input change. Outputs: annual energy by source, GHG comparison bar broken
into combustion / electricity / refrigerant / upstream methane, monthly
energy + GHG, and THE key chart: heating load vs heat-pump capacity across
outdoor temperature, with balance point, HP cutoff and backup region shaded.
If the energy-prices data (ROADMAP.md item 4) is available in prices_json/,
include annual operating cost per scenario using each province's current
rates; otherwise leave a clearly-marked hook. "Show assumptions" expandable
citing METHODOLOGY.md. Run /dataviz before building charts. Verify in a
browser preview: no console errors, engine results match the Phase 5 test
vectors, all inputs re-render correctly.
```

### Prompt — Phase 7: validation & writeup (Opus)

```text
Read PLAN.md Phase 7, HeatPump/METHODOLOGY.md in full, and the finished
tool. Compare the tool's annual outputs (energy, GHG deltas for gas→ASHP
and baseboard→ASHP in Ottawa, Toronto, Montreal, Calgary) against published
benchmarks: NRCan ASHP studies, RAP and Pembina ON/AB analyses, and any
recent CMHC/Efficiency Canada figures. Tabulate tool vs benchmark with the
methodological reasons for each delta (average vs marginal EF is the big
one — show both). Add a "Validation" section to METHODOLOGY.md and a short
plain-language accuracy note to heatpump.html's assumptions panel. Flag
anything > 30% off with no explanation as a bug to investigate, and
investigate it.
```

---

## 4. Energy prices layer — consume `MaxPr1me/canada-utility-rates`

https://github.com/MaxPr1me/canada-utility-rates already scrapes electricity and
natural-gas rates across Canadian utilities (BC Hydro, AESO, ATCO, Enbridge,
Énergir, ENMAX, …) on a scheduled GitHub workflow, with a JSON export pipeline
(`pipeline/export_json.py`, `data/exports/`) and a documented schema
(`schema/`). We consume its output rather than rebuilding scrapers.

Unlocks: operating-cost estimates in the Heat Pump tool (do this first), payback
context in Retrofit Explorer, and $-per-GJ context in CEUD — the "no cost data"
caveat finally gets an answer.

### Prompt — Phase 0: scout the exports (Sonnet)

```text
Investigate https://github.com/MaxPr1me/canada-utility-rates as a data
source for C:\Energy (read its README, docs/, schema/, and
pipeline/export_json.py via raw.githubusercontent.com or a shallow clone
into the scratchpad). Questions to answer in a written report
(Python/rates_source_notes.md):
1. What do the exported JSONs contain and where do they live (committed to
   the repo? published via the deploy workflow / GitHub Pages? release
   assets?) — find the stable raw URL pattern we can fetch.
2. Schema: per-utility rate structures (tiered/TOU/flat, fixed monthly
   charges, riders, delivery vs commodity), units, effective dates,
   currency of updates (the scrape.yml cadence).
3. Coverage: which provinces/utilities, and which of our launch cities
   (Ottawa, Toronto, Montreal, Calgary, Edmonton) are fully covered for
   BOTH electricity and natural gas. Note gaps (e.g. heating oil — not in
   scope there; propose StatCan 18-10-0001 monthly fuel prices as the
   oil/propane fallback).
4. How to reduce a full tariff to what our tools need: effective $/kWh and
   $/m³ marginal rates + fixed charges for a typical residential profile
   (incl. TOU handling — the heat pump engine is hourly, so TOU can be
   applied exactly; propose the JSON shape for that).
Do not build the ETL yet.
```

### Prompt — Phase 1: rates ETL (Sonnet)

```text
Read Python/rates_source_notes.md and ROADMAP.md item 4 first. Build
Python/rates_etl.py: fetch the canada-utility-rates exports (plus the
StatCan fallback series for heating oil/propane identified in the notes),
and emit compact prices_json/ files: one per province with residential
electricity rates (flat or hourly-applicable TOU schedule + fixed charges),
natural gas ($/m³ all-in marginal + fixed), and oil/propane $/L, each with
effective_date and source attribution. Follow the repo's ETL conventions
(cache dir, --refresh flag, repo-relative paths — see
Python/construction_etl.py). Include a meta.json documenting units and the
tariff-reduction method. Validate: print an all-in monthly bill for a
1,000 kWh + 200 m³ Ottawa household and sanity-check against the utility's
published bill examples (±10%). Then extend
.github/workflows/construction-refresh.yml's pattern with a monthly
rates-refresh workflow (separate yml, no commit on fetch failure).
```

### Phase 2 — integration

Covered inside the Heat Pump Phase 6 prompt (operating-cost hook). A later small
prompt can add "typical annual $ impact" context lines to Retrofit Explorer using
median fuel deltas × current rates — do that only after the heat pump tool ships.

---

## 5. Landing page hub (1 session)

Four (soon six) tools, no front door.

### Prompt (Opus — design-heavy)

```text
Read Readme.MD and skim retrofits.html, ceud.html, construction.html
headers/hero sections for the shared design system. Build index.html at the
repo root: a landing page in the same navy/amber/cream + Fraunces/Inter
language presenting the suite ("Ottawa Visuals — Canadian energy data
tools"). One card per tool — Retrofit Explorer, CEUD Explorer, Construction
Tracker, Ottawa Geothermal Map (use the live URL from ROADMAP.md item 1),
plus greyed "coming soon" cards for the Heat Pump tool and anything else
unreleased — each with a one-sentence plain-language description, the data
source, and a small representative static graphic (inline SVG, no live data
fetches; keep the page < 200 KB total). Add a short "about the data"
footer. Follow the deployment pattern the other pages use so it becomes the
site's front page, and add cross-links from each existing tool's header
back to the hub (small, unobtrusive). Verify in a browser preview at
mobile and desktop widths.
```

---

## 6. Live grid dashboard (2 sessions)

Mostly reuse: `HeatPump/pipeline/fetch_ieso.py` / `fetch_aeso.py` already map
hourly generation to fuels with NIR emission factors. Repoint at recent data for
a "what's powering the grid right now / this month" dashboard, which doubles as a
public explainer of the heat pump tool's marginal-emissions methodology.

Known quirks (from memory + METHODOLOGY.md): IESO/AESO block WebFetch — use
`curl`; AESO's Box-hosted files are unscriptable but direct CSVs on aeso.ca work;
ECCC endpoints need `curl -L`.

### Prompt — ETL (Sonnet)

```text
Read HeatPump/METHODOLOGY.md Phase 1 sections and ROADMAP.md item 6. Build
Python/grid_etl.py reusing the fetch+fuel-mapping+EF logic from
HeatPump/pipeline/fetch_ieso.py and fetch_aeso.py (import/refactor shared
code into a module rather than copy-pasting; IESO/AESO need curl not
WebFetch). Output grid_json/: for ON and AB (QC as flat-EF context), the
last 12 months of hourly generation by fuel and computed average+marginal
intensity, downsampled sensibly (hourly for last 14 days, daily min/mean/
max beyond) to keep each file < 300 KB, plus a meta.json with EF sources
and last-updated. Add a weekly refresh workflow following
construction-refresh.yml's pattern. Validate monthly averages against
IESO/AESO published figures and print the comparison.
```

### Prompt — page (Opus)

```text
Read ROADMAP.md item 6 and skim construction.html for the design system and
BASE_URL pattern. Build grid.html: current + recent grid mix and emissions
intensity for ON and AB from grid_json/. Sections: (1) latest-day stacked
generation-by-fuel area with intensity line beneath (chart-pair pattern
from construction.html, not dual axes); (2) 12-month daily intensity band
(min/mean/max); (3) an "average vs marginal emissions" explainer panel with
a small interactive toggle demonstrating why new load (like a heat pump) is
priced at the margin — link to heatpump.html; (4) typical-day profiles by
season (Advanced). Run /dataviz before building charts. Simple/Advanced
toggle, same header/hub link, verified in browser preview with zero console
errors and values spot-checked against grid_json.
```

---

## 7. Ottawa heat demand map (2–3 sessions, most novel)

Fuses three finished projects: where is geothermal feasible (conductivity grid +
city potential layer) *and* needed (building heat demand) *and* grid-constrained
(feeder capacity)? Deliberately deferred inputs now become useful: building
footprints (TopographicMapping/3, ~392k polygons — fetch was skipped because
"nothing consumes them yet"; this consumes them).

### Prompt — heat demand layer (Opus — methodology-heavy)

```text
Read GEOTHERMAL_STATUS.md, Geothermal/README.md and ROADMAP.md item 7.
Build Geothermal/scripts/build_heat_demand.py:
1. Fetch Ottawa building footprints from the City ArcGIS server
   (TopographicMapping/3 — see fetch_municipal_layers.py for the fetch
   pattern and the esriJSON fallback gotcha; ~392k polygons, so paginate,
   cache raw pulls under Data/Raw/, and filter early to buildings > 40 m²).
2. Estimate per-building annual space-heat demand: footprint area × storeys
   proxy (if no height attribute, use a documented single-storey-equivalent
   assumption) × an intensity (kWh/m²·yr) drawn from the ERS Ottawa
   pre-retrofit medians by vintage — reuse the HeatPump Phase 4 archetype
   values if HeatPump/data/processed/archetypes.json exists, else compute
   Ottawa medians directly from the ERS parquet. If a construction-era
   attribute is unavailable per building, apply the city-wide vintage mix.
   Document every assumption; this is a screening layer, not a building
   audit — say so in the output metadata.
3. Aggregate demand onto the existing 500 m conductivity grid cells and
   emit Data/processed/heat_demand_grid.geojson (kWh/yr and kW-peak per
   cell using the ERS design-heat-loss ratio).
4. Compute a composite screening score per cell: heat demand × conductivity
   class × feeder headroom (join GridCapacity polygons) — document the
   scoring formula and normalize each factor; emit it on the same grid.
Validate: city-wide summed residential heat demand should land within ±30%
of CEUD Ontario residential space-heating scaled to Ottawa household count
(ceud_json/res_on.json + Census data) — print the comparison.
```

### Prompt — map integration (Sonnet)

```text
Read Geothermal/README.md and ROADMAP.md item 7. Extend
Geothermal/scripts/merge_layers.py and build_map.py to add two toggleable
layers from Data/processed/heat_demand_grid.geojson: heat demand (kWh/yr
choropleth) and the composite geothermal-opportunity score, with popups
showing the score breakdown (demand / conductivity / feeder headroom).
Keep the embedded-tuple size discipline (output/index.html should stay
under ~10 MB — drop per-cell fields the popup doesn't show). Re-run the
full chain, verify in a browser preview (all eight layers, popups, no
console errors), update README.md §layers and GEOTHERMAL_STATUS.md, and
republish per the item-1 deployment pattern.
```

---

## Session hygiene

- Each prompt is self-contained; run in a fresh session, in order within an item.
- After each session: update the project's STATUS/METHODOLOGY file, commit.
- Heat pump phases must land in order (3a → 3b → EF surface/4 in either order →
  5 → 6 → 7). Item 4 Phase 1 should finish before Heat Pump Phase 6.
- Opus for methodology-heavy or design-heavy work (silent-error risk); Sonnet
  for data plumbing with clear validation criteria.
