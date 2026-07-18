# Energy Suite — Roadmap & Build Prompts

Master plan for finishing the in-flight projects and starting the new ones, written
2026-07-10. Each item has paste-able Claude Code prompts (run from `C:\Energy`) with a
suggested model. Companion docs: [PLAN.md](PLAN.md) (heat pump), [CEUD_PLAN.md](CEUD_PLAN.md),
[CONSTRUCTION_PLAN.md](CONSTRUCTION_PLAN.md), [GEOTHERMAL_STATUS.md](GEOTHERMAL_STATUS.md).

**Status snapshot (2026-07-12 — verified against the repo, the GitHub Actions
API, and the on-disk state):**

| Project | State |
|---|---|
| Retrofit Explorer | ✅ done, deployed — +4 additions 2026-07-17 (item 10); audit funnel + pairing-filter fix 2026-07-18 (item 11); EnerGuide-demo visual polish 2026-07-18 (item 12) |
| Construction Tracker | ✅ done, deployed — first scheduled refresh fires 2026-07-20 (monthly, 20th 14:00 UTC); not yet observed green |
| CEUD Explorer | ✅ done (all 5 sectors live) |
| Geothermal | ✅ committed (`cf1c862`) & live: `…/Energy/Geothermal/output/` |
| Heat Pump tool | ✅ **all 7 phases done + operating costs (item 4 Phase 2)**, live: `…/Energy/heatpump` |
| Project Atlas | ✅ `project-atlas.html` committed (`508761e`, 2026-07-11) — internal status page; keep in sync when items ship (distinct from the item-5 public landing page) |
| AHRI housekeeping (item 2) | ✅ done 2026-07-12 — legacy files archived in `Python/ahri_archive/`, seen-files moved to `Python/`, Readme.MD heat-pump link added. Follow-up flagged: `lookup/ahri_numbers.json` is missing 7 newly-seen AHRI numbers (rerun `build_ahri_lookup.py`) |
| Energy prices | ✅ done 2026-07-12, all 3 phases — `Python/rates_etl.py` → `prices_json/`, monthly workflow (first scheduled run 2026-08-03), costs live in heatpump.html |
| Landing page | 🆕 not started (`…/Energy/` 404s) |
| Live grid dashboard | 🔨 ETL done (`Python/grid_etl.py`); weekly workflow's first scheduled run is Mon 2026-07-13 13:00 UTC — check it went green; `grid.html` page not started |
| Ottawa heat demand / case study | 🔨 in progress — [HEATDEMAND_PLAN.md](HEATDEMAND_PLAN.md) Phases 0–2 done 2026-07-16 (building stock + per-building heat load); **next: Phase 2.5 stock-count fix (defensibility blocker), then 3–6**. Reframed 2026-07-16 as the **Ottawa Case Study** (§0 of that plan): six-step narrative ending in a case-study page, with the map as expert explorer |
| Geothermal v2 | ✅ done 2026-07-15 (item 8) — all 4 phases: data fixes, conductivity sensitivity, drilling difficulty, segment suitability |
| Heat Pump v2 | ✅ done 2026-07-17 (item 9) — all 6 workstreams (B ECCC EF basis, A 14 cities, C weather-year lens, D sizing sweep, E lifecycle sourcing + below-lock-out toggle, F chart re-org) |

**Recommended order (remaining):** 5 → 6-page → 7 → 9 (items 2, 4 and 8
completed). Items 5, 6-page, 7 and 9 are independent of each other, except
item 8 Phase D consumes item 7's `heat_demand_grid.geojson` if it exists (it
degrades gracefully otherwise — running 7 first makes the district-energy
score better). Within item 9, run its prompts in order (1 → 5).

---

## 1. Ship the Geothermal map — ✅ DONE (2026-07-10)

Committed in `cf1c862` (everything fit under GitHub's 100 MB limit, nothing
gitignored) and published via the existing Pages setup — live at
<https://ottawavisuals.github.io/Energy/Geothermal/output/> (commit `ab46158`
added the link to `Geothermal/README.md` + `Readme.MD` and fixed a stale
retrofits URL found in passing). Verified live: six layers toggle, popups
render, no console errors. `GEOTHERMAL_STATUS.md` records the session.

---

## 2. Repo housekeeping — AHRI legacy files — ✅ DONE (2026-07-12)

Legacy certificate-PDF artifacts moved to `Python/ahri_archive/` (with README);
`ahri_numbers_seen.{csv,json}` moved to `Python/`; all five scripts that
read/write them updated to repo-root-anchored paths and compile-checked;
`list_ahri_numbers.py` re-run from its new location. That re-run revealed the
underlying site JSONs had changed since the seen-list was last generated:
7 AHRI numbers rotated in, 7 out, counts shifted (old top 5,465 → 5,138) —
so `lookup/ahri_numbers.json` (untouched per this item's rule 3) is now
missing 7 numbers; flagged as a follow-up task to rerun `build_ahri_lookup.py`.
`Python/ahri_numbers_seen.csv` is intentionally left as-is: it's the frozen
popularity-ranking input the shipped NEEP analysis used. Readme.MD gained the
Heat Pump Explorer section + live URL.

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
4. While in Readme.MD: add the Heat Pump Explorer to the tool list with its
   live URL (https://ottawavisuals.github.io/Energy/heatpump) alongside the
   retrofits and geothermal links — it shipped without a Readme mention.

Update Readme.MD's repository-layout section if it references moved paths.
```

---

## 3. Heat Pump tool — ✅ DONE, all 7 phases (2026-07-10)

Landed in commit `2837ef9`; live at <https://ottawavisuals.github.io/Energy/heatpump>.
Everything below (3a, 3b, EF surface, Phase 4, 5, 6, 7) is built, validated and
documented in [HeatPump/METHODOLOGY.md](HeatPump/METHODOLOGY.md); PLAN.md's
status header has the narrative. **Independently re-verified 2026-07-10
(review session):** `test_hp_curves.py` 7/7 pass; page loads with zero console
errors and the in-page self-test reproduces all 15 Phase-5 vectors in the
browser (important because Node is not installed on this machine, so
`engine.test.js` had only ever run via its Python mirror); headline outputs for
Ottawa/Montreal match the Phase-7 validation tables exactly; the Quebec
near-zero-baseline guard works; all processed JSONs serve 200 on Pages.

**Documented deviations from the original plan (all judged acceptable):**

- **3b spec sheets:** most manufacturers gate extended temperature tables
  behind contractor logins, so the curves' backbone is the four AHRI-certified
  NEEP points per model (47/17/5 °F + LCT, max speed), with Mitsubishi's open
  submittal as the independent cross-check (one >10 % flag, investigated:
  indoor-pairing difference). Honest and recorded — but coarser than the
  planned engineering-book digitization between −8 °C and +8 °C.
- **Model approval:** 3b was meant to pause for user sign-off on the candidate
  models; it proceeded with a data-driven selection instead (documented table
  in METHODOLOGY §3b — swapping a model is a one-line edit in
  `extract_neep_points.py` + re-run, if you want different ones).
- **Tbalance:** calibrated at 8–12 °C, not the planned ~15–16 °C — investigated
  and explained in METHODOLOGY §Phase 4.
- **Bonus:** Edmonton shipped as a fifth city.

**Remaining follow-ups:** (a) operating-cost integration once item 4's
`prices_json/` exists — the UI already shows a clearly-marked hook card;
(b) `Readme.MD` does not yet mention/link the Heat Pump Explorer (folded into
the item 2 prompt below).

<details><summary>Original Phase 3–7 plan and prompts (completed — kept for the record)</summary>

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

</details>

---

## 4. Energy prices layer — ✅ DONE, all 3 phases (2026-07-12)

Phase 0 scouting: `Python/rates_source_notes.md` (raw-URL pattern, schema,
coverage, caveats — notably stale carbon components excluded, AB screening
supplements for missing transmission/gas-commodity, Enbridge rate-zone note).
Phase 1: `Python/rates_etl.py` → `prices_json/{on,qc,ab,meta}.json` (<5 KB
each), 5/5 validation bands PASS; monthly workflow
`.github/workflows/rates-refresh.yml` (3rd of month — first scheduled run
2026-08-03, upstream scrapes on the 1st). Phase 2: heatpump.html's hook card
replaced with real per-scenario costs — the engine now emits a month×hour
electricity matrix so TOU/ULO are priced exactly (weekday rules weighted
5/7:2/7 over the TMY year); tiered plans priced marginally over documented
baselines; ON plan selector; gas fixed-charge policy and all caveats in the
card's fine print. Verified in browser: zero console errors, 15/15 self-test
vectors, hand-checked Ottawa/Calgary bills. Method: METHODOLOGY.md
§Operating cost. The retrofit-explorer "$ impact" context lines remain a
possible later add-on (see note at the end of this item).

<details><summary>Original phase prompts (completed — kept for the record)</summary>

https://github.com/MaxPr1me/canada-utility-rates already scrapes electricity and
natural-gas rates across Canadian utilities (BC Hydro, AESO, ATCO, Enbridge,
Énergir, ENMAX, …) on a scheduled GitHub workflow, with a JSON export pipeline
(`pipeline/export_json.py`, `data/exports/`) and a documented schema
(`schema/`). We consume its output rather than rebuilding scrapers.

Unlocks: operating-cost estimates in the Heat Pump tool (now shipped with a
clearly-marked hook card waiting on `prices_json/` — see Phase 2 below), payback
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

### Prompt — Phase 2: wire costs into the shipped Heat Pump tool (Sonnet)

*(Was "covered inside the Phase 6 prompt", but the tool shipped before the
rates existed, so the integration is now its own pass.)*

```text
Read ROADMAP.md item 4 and prices_json/meta.json first. heatpump.html is live
and complete except for its operating-cost hook: the "Annual operating cost"
card (search for "Operating cost hook") currently shows placeholder text
saying costs will appear once prices_json/ exists. Replace it: fetch the
user's province's rates via the existing BASE_URL/DATA pattern, and compute
per-scenario annual cost from the simulation's hourly energy-by-source output
(the engine already tracks it hourly, so apply TOU electricity schedules
exactly; gas/oil are volumetric + fixed charges — state which fixed charges
are included and that the delta, not the absolute bill, is the headline).
Show current-heating vs heat-pump annual cost and the delta, with
effective_date + utility attribution in small print. Re-run the in-page
self-test, verify in a browser preview (zero console errors, costs change
with city/fuel/bucket inputs, Quebec + Alberta sane), and add a short
"Operating cost" subsection to HeatPump/METHODOLOGY.md documenting the
tariff-reduction choices. Keep the card graceful if a province's rates file
is missing.
```

</details>

A later small prompt can add "typical annual $ impact" context lines to
Retrofit Explorer using median fuel deltas × current rates — the heat pump
cost integration it depended on is now done.

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
Tracker, Ottawa Geothermal Map
(https://ottawavisuals.github.io/Energy/Geothermal/output/), and the Heat
Pump Explorer (https://ottawavisuals.github.io/Energy/heatpump — live, NOT
coming-soon), plus a greyed "coming soon" card for the grid dashboard
(grid.html, ROADMAP.md item 6) — each with a one-sentence plain-language
description, the data
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
`curl`/`requests` with a browser User-Agent. **Correction found while building
the ETL:** there is no scriptable *recent* AESO source at all — the "direct CSVs
on aeso.ca" lead didn't pan out (404s), and AESO's real-time API
(`developer-apim.aeso.ca`) requires a registered API key we don't have. AB is
therefore parse-only from whatever CSD zips the user has manually placed in
`HeatPump/data/raw/aeso/` (currently through 2026-06) — **not** live-refreshed
by the weekly workflow. ON (IESO) *is* fully live and refreshes every run.

### ETL — done (`Python/grid_etl.py`)

Reuses fetch/parse/EF logic via a new shared module,
`HeatPump/pipeline/grid_common.py` (fetch_ieso.py, fetch_aeso.py,
build_grid_ef.py, build_grid_ef_ab.py were refactored to import from it — outputs
verified byte-identical to the pre-refactor Phase-1 JSONs). Outputs
`grid_json/{grid_on,grid_ab,grid_qc,meta}.json` (163 KB / 176 KB / <1 KB), each
with hourly resolution for the last 14 days and daily min/mean/max beyond, back
to a rolling ~12-month window. QC is a static flat-EF context card (HQ's export
is likewise a manually-placed, non-live file). Validation prints (a) an
ETL-correctness cross-check against the already-validated Phase-1 master JSONs
for overlapping months, and (b) the annual figure vs TAF/Alberta.ca published
references for any full year in scope — see the script's docstring for why no
independent *monthly* published reference exists to check against. Weekly
GitHub Actions workflow: `.github/workflows/grid-refresh.yml` (Mondays 13:00
UTC); AB/QC staying stale doesn't block the ON commit.

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

## 7. Ottawa heat demand map → Ottawa Case Study (in progress)

> **Superseded 2026-07-16 by [HEATDEMAND_PLAN.md](HEATDEMAND_PLAN.md)** — a
> fuller plan (building stock w/ height+type, current load, electrified
> load + feeder stress, intervention score, waste-heat hook) with its own
> paste-able prompts. The two prompts below are kept for the record.
>
> **Reframed 2026-07-16 (second pass):** the end product is the **Ottawa Case
> Study** — a six-step narrative (grid constraints → ground resource →
> building heat loads → electrified share → electrification peak vs grid →
> candidate areas), delivered as a case-study page with the interactive map
> as the expert explorer. Status: Phases 0–2 built; live queue is
> **2.5 (stock-count fix) → 3 → 4 → 5 → 6 (case-study page)** — prompts in
> HEATDEMAND_PLAN.md §5.

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

## 8. Geothermal v2 — data fixes, conductivity sensitivity, drilling difficulty, segment suitability (4 sessions)

**✅ DONE 2026-07-15 — all four phases (A data fixes, B conductivity sensitivity,
C drilling difficulty, D segment suitability) built, verified and republished.**
See GEOTHERMAL_STATUS.md session entries and Geothermal/README.md §3.1/§3.7/§3.8/§3.9.

Rework of the shipped geothermal map (item 1), planned 2026-07-15 after a data
audit of `ottawa_geothermal.gpkg` and the raw exports. Audit findings the
phases are built on (all verified against the on-disk data):

- **Categorization bugs:** `status` shows `code:0` for 464 wells — the
  `_code_final_status.csv` code-0 row has a *blank* description, and
  `decode()` treats blank as unresolved. `well_use` shows "Commerical"
  (typo in the source `_codeWaterUse` table) and is NaN for 8,123 wells
  (tblWWR has a `USE_2ND` column to fall back on).
- **Missing geometry (5,068 wells):** only 65 are recoverable from
  `tblBore_Hole.EAST83/NORTH83` (NAD83 UTM; ZONE=18 for all but ~12 rows) —
  checked; the rest have no coordinates anywhere in the export. Recover the
  65, document the rest as irreducible.
- **Missing bedrock depth (27,428 wells):** 10,915 of them have a
  bedrock-bucket formation interval whose `top_depth_m` can stand in for
  `DP_BEDROCK` — checked.
- **Unknown lithology/conductivity (9,180 wells, 7,872 with no formation
  record at all):** the unused GSC bedrock geology gdb
  (`Geothermal/Data/Raw/GSC/gsc_bedrock_geology.gdb.zip`) can assign a
  mapped-geology fallback bucket by spatial join (this was already README
  next-step #5).
- **Sensitivity is exactly computable client-side:** IDW is *linear* in the
  per-well conductivity values, so precomputing each grid cell's IDW weight
  share per lithology bucket makes user-edited bucket conductivities an
  exact recompute (cell κ = Σ shareᵦ × κᵦ) — no server, no approximation.
- **Difficulty inputs exist:** 7,395 wells log boulders / stones / quicksand /
  hardpan layers; 503 wells have flowing-artesian pump tests;
  overburden thickness ≈ casing metres; drilling-method codes are decoded
  for 50,720 wells (validation cross-check).

Phases A→D are sequential — each rebuilds the chain on top of the previous.
Commit after each phase (the map stays publishable throughout).

### Prompt — Phase A: well data quality fixes (Sonnet)

```text
Read GEOTHERMAL_STATUS.md, Geothermal/README.md §3.1 and ROADMAP.md item 8
first. Goal: fix the categorization/missing-data issues in
Geothermal/scripts/combine_wells.py and rebuild ottawa_geothermal.gpkg.
The audit numbers below were verified 2026-07-15 against the current gpkg.

1. Code decoding: decode() returns "code:0" for 464 wells because
   _code_final_status.csv's code-0 row has a blank DES. Treat a blank/NaN
   description as "Not specified" instead of unresolved. Also normalize
   the source table's "Commerical" typo to "Commercial" at decode time
   (leave the raw CSVs untouched).
2. well_use is NaN for 8,123 wells. tblWWR has USE_2ND — fall back to it
   when USE_1ST is empty and report how many recover.
3. Geometry: 5,068 wells have none. tblBore_Hole_Ottawa.csv carries
   ZONE/EAST83/NORTH83 (NAD83 UTM; zone 18 except ~12 rows) — checked:
   exactly 65 of the missing-geometry wells have usable coordinates there.
   Recover those (EPSG:26918→4326, respect ZONE, drop zones not in
   {17,18}), add a geometry_source flag (shp | borehole), and document the
   remaining ~5,000 as irreducible in README §5.
4. bedrock_depth_m is missing for 27,428 wells; 10,915 of them have a
   bedrock-bucket formation interval (checked). Where the shapefile
   DP_BEDROCK is null, use the minimum top_depth_m of the well's
   bedrock-bucket layers; add bedrock_depth_source (shp | formations).
   Sanity check: on wells where BOTH exist, print the median absolute
   difference between DP_BEDROCK and the formations-derived depth —
   investigate if it's more than a few metres.
5. Lithology fallback from mapped geology: 9,180 wells have unknown
   lithology (7,872 with no formation record at all). Unzip
   Geothermal/Data/Raw/GSC/gsc_bedrock_geology.gdb.zip, inspect its
   layers, and spatial-join unknown-lithology wells to the mapped bedrock
   formation; map the GSC rock-type attribute onto combine_wells.py's
   lithology buckets (document the mapping table in README). Add
   lithology_source (well_log | gsc_map) to the wells layer and keep
   estimated_conductivity_* consistent. GSC-derived lithology is weaker
   evidence — the flag must survive into merge_layers.py's popup fields
   so later phases can show it.
6. Re-run the chain (combine_wells → interpolate_conductivity →
   merge_layers → build_map) and report new conductivity-class counts vs
   old (medium 37,671 / low 7,351 / high 1,701 / unknown 9,180). Update
   Geothermal/README.md (§3.1, §4, §5) and append a session entry to
   GEOTHERMAL_STATUS.md. Verify the rebuilt map in a browser preview
   (well popups show the source flags, no console errors).
```

### Prompt — Phase B: sourced conductivity table + sensitivity UI (Opus)

```text
Read GEOTHERMAL_STATUS.md, Geothermal/README.md (§3.1, §3.3, §3.5) and
ROADMAP.md item 8 (Phase B) first. Two deliverables: a literature-sourced
conductivity reference table, and a map panel to edit per-bucket values
with exact live recompute.

1. Reference table. Create Geothermal/Data/conductivity_reference.csv:
   one row per lithology bucket in combine_wells.py's CONDUCTIVITY_WM
   (limestone, dolostone, sandstone, shale, granite, gneiss, clay, silt,
   sand, gravel, till, fill, basalt, rock), columns: bucket, default_wmk,
   min_wmk, max_wmk, notes, source. Source every range from published
   GSHP/thermogeology literature — VDI 4640 Part 1 tables, ASHRAE
   Handbook (Geothermal Energy chapter), Banks "An Introduction to
   Thermogeology", IGSHPA / CSA C448 guidance; use WebSearch to confirm
   exact values and cite precisely (document + table number). If a
   current default sits outside the literature range, change it and
   record the change. Note saturated-vs-dry sensitivity for soils in the
   notes column but keep one default per bucket. combine_wells.py and
   interpolate_conductivity.py must read this CSV (CONDUCTIVITY_WM
   becomes the fallback only).
2. Exact client-side sensitivity. IDW cell conductivity is linear in the
   per-well bucket values, so per-cell bucket weight shares make edited
   values an exact recompute. In interpolate_conductivity.py, also emit
   each cell's IDW weight share per bucket (sums to 1; quantize to 3
   decimals, drop shares < 0.001 and renormalize — then verify max
   reconstruction error vs the exact surface < 0.01 W/m·K). Carry the
   shares through merge_layers.py into build_map.py's compact grid
   tuples (bucket indices 0–13, sparse [idx,share] pairs; keep
   output/index.html ≲ 8 MB).
3. Map UI (map_template.html): collapsible "Conductivity assumptions"
   panel — one row per bucket with an editable numeric input clamped to
   [min_wmk, max_wmk], default value and source shown, and a Reset-all
   button. On change: recompute every grid cell (Σ shareᵦ × κᵦ), redraw
   the canvas layer, refresh the legend, and make well popups compute
   their conductivity from the well's bucket at open time (wells already
   carry a lithology; embed the bucket index). State in the panel
   whether well marker COLORS track the edits or stay at defaults
   (pick one, document why).
4. Re-run the chain and verify in a browser preview: editing granite
   3.2 → 2.6 visibly shifts Shield cells' class; Reset restores; no
   console errors; size budget respected. Remember this environment's
   preview quirks (no rAF — force draws, verify via canvas pixel
   sampling). Update README (§3.3, §3.5, new "Conductivity assumptions &
   sources" section) and GEOTHERMAL_STATUS.md.
```

### Prompt — Phase C: drilling difficulty layer (Opus)

```text
Read GEOTHERMAL_STATUS.md, Geothermal/README.md and ROADMAP.md item 8
(Phase C) first. Goal: a per-well drilling-difficulty score for vertical
GSHP boreholes, gridded like conductivity, shipped as a new toggleable
map layer.

1. New script Geothermal/scripts/build_difficulty.py reading
   ottawa_geothermal.gpkg. Score components (availability verified):
   - Overburden thickness (bedrock_depth_m, incl. Phase A's formations
     fallback): deeper overburden = more casing = cost. Document the
     scale (e.g. 0 points at 0 m rising to max at ≥ 30 m).
   - Problematic overburden layers from formations: boulders, stones,
     quicksand/heaving sand, hardpan (7,395 wells log at least one) —
     casing-advance / lost-circulation risk.
   - Hard crystalline bedrock (granite/gneiss buckets): slower
     penetration and bit wear — moderate penalty; limestone/dolostone
     baseline; shale/sandstone easiest.
   - Artesian risk: flowing wells (pump_tests flowing_rate_lpm > 0 —
     503 wells; plus tblWater flowing kinds). Sparse, so treat as a
     neighborhood indicator (share of flowing wells within ~1 km), not
     a per-well binary.
   Combine into difficulty_score 0–100 with documented weights and a
   3-class label (easy / moderate / difficult). It's a screening
   heuristic: write the formula and each weight's rationale in README,
   round scores to 5 (no false precision).
2. Validate BEFORE gridding: (a) cross-tab score class vs decoded
   construction method — hard-rock areas should skew air-percussion/
   rotary-air vs cable-tool; (b) correlation of score vs total depth;
   (c) eyeball the spatial pattern (eastern clay plain should be
   casing-heavy, Shield edge hard-rock). Print all three, investigate
   surprises before proceeding.
3. Grid it with the same IDW conventions as interpolate_conductivity.py
   (500 m, k=12, power 2, 2 km cutoff) — factor the shared IDW code into
   a small module instead of copy-pasting — emitting
   Data/processed/difficulty_grid.geojson with score, class and the
   dominant driver per cell (for the popup).
4. Wire into merge_layers.py + build_map.py + map_template.html as a new
   toggleable choropleth with a popup breakdown (overburden / problem
   layers / rock hardness / artesian). Re-run the chain, browser-verify
   (toggle, popups, no console errors, size budget), update README (new
   method section, §4 results, §5 caveat: difficulty is relative
   screening, not a quote) and GEOTHERMAL_STATUS.md.
```

### Prompt — Phase D: segment suitability (residential / large buildings / district energy) (Opus)

```text
Read GEOTHERMAL_STATUS.md, Geothermal/README.md, and ROADMAP.md items 7
and 8 (Phase D) first. Goal: replace the map's one-size-fits-all reading
with per-segment suitability scores — (1) residential & small commercial,
(2) large buildings, (3) district energy — which differ in depth needs,
land, load balancing, yield and grid draw.

1. New script Geothermal/scripts/build_suitability.py producing three
   0–100 scores per existing 500 m grid cell. First define each segment's
   requirement profile in README, citing where citations exist (CSA C448
   / IGSHPA sizing conventions, Canadian district-energy literature):
   - Residential/small commercial (~1–10 tons): 1–3 boreholes at
     ~100–200 m; drilling difficulty and thin overburden dominate cost;
     conductivity matters moderately; open-loop bonus where neighborhood
     wells show static level + modest yield; feeder capacity irrelevant.
   - Large buildings (50+ tons): borefields — conductivity weighs
     heavier (borehole metres scale roughly with 1/λ); heating-dominant
     Ottawa loads risk long-term ground thermal depletion, worse in
     low-conductivity clay (penalize); feeder headroom matters (join
     GridCapacity polygons); industrial/employment zoning as a
     land-availability bonus.
   - District energy: needs demand density plus a big resource:
     high-yield aquifer (neighborhood pump-test yield stats),
     trunk-sewer proximity (heat recovery), feeder headroom, land. If
     Data/processed/heat_demand_grid.geojson exists (ROADMAP item 7),
     use it for demand density; else use the City potential layer +
     zoning as a proxy and leave a clearly-marked upgrade hook.
   Normalize each factor to 0–1 with documented transforms; publish the
   weight table in README; emit per-cell factor values (for popup
   breakdowns), not just composites.
2. Map: a segment selector (radio buttons) restyling ONE "Suitability"
   layer, popup showing the active segment's factor breakdown. The
   Phase B conductivity panel must stay live: conductivity edits flow
   into the suitability recompute, so ship weights + per-cell factors
   and compute composites in JS (the conductivity factor recomputes from
   the Phase B bucket shares).
3. Sanity checks: print inter-segment score correlations (> 0.95
   everywhere means redundant weights — fix); top-decile district-energy
   cells should sit in the serviced urban area near trunk sewers; top
   residential cells should NOT concentrate downtown. Investigate
   surprises.
4. Re-run the chain, browser-verify everything (layer toggles, segment
   switching, popups, a conductivity edit updating suitability, no
   console errors), keep output/index.html within budget (drop per-cell
   fields popups don't show), update README + GEOTHERMAL_STATUS.md,
   republish per item 1's deployment pattern, and flip ROADMAP item 8's
   status row to done.
```

---

## 9. Heat Pump v2 — more cities, weather years, EF options, sizing sensitivity, lifecycle sourcing, chart re-org (4–5 sessions)

Planned 2026-07-17 from user feedback on the shipped tool. Six workstreams
(A–F below); the paste-able prompts bundle them into 5 sessions. Read
[PLAN.md](PLAN.md) and [HeatPump/METHODOLOGY.md](HeatPump/METHODOLOGY.md)
before any of them. Current state being extended: 5 cities
(Ottawa/Toronto/Montreal/Calgary/Edmonton), hourly grid EF for ON/QC/AB
only (avg + marginal), CWEC2020 TMY + 2019–2026 ECCC hourly history,
tiered ASHP curves with hard lock-outs at the published minimum operating
temperature, methane slider 0–3% @ GWP 28, line-loss slider default 5%.

### A. More large cities — ✅ DONE (2026-07-17)

Added 9 cities (Vancouver, Winnipeg, Quebec City, Halifax, Saskatoon, Regina,
Hamilton, London, Windsor) → 14 total; all had ERS parquets. Extended
fetch_tmy.py (new combined-zip CWEC source), fetch_weather.py, build_archetypes.py,
new build_tmy_temps.py; wired CITY_PROV/CITY_KEY/CITIES + cost guard in
heatpump.html. BC/MB/SK/NS use ECCC-annual + flat marginal (Hourly-average
disabled). All 56 archetypes within ±10%; sanity gates pass (Vancouver COP 3.5 >
Ottawa 2.4); no console errors. METHODOLOGY.md "v2 city additions" documents
stations/FSA/design-temps. Original spec below.

### A (original spec). More large cities (including provinces with no hourly grid data)

Proposed additions (adjustable): **Vancouver, Winnipeg, Quebec City,
Halifax, Saskatoon, Regina, Hamilton, London, Windsor** (the last three
reuse the ON grid surface; only weather + archetypes are new work for
them). Per new city: CWEC2020 TMY station (fetch_tmy.py already downloads
per-province zips — add stations), ECCC hourly weather (extend
fetch_weather.py station table), archetypes from the ERS parquet
(`C:\ERS\web\ers_web_<PROV>.parquet` — verify BC/MB/SK/NS parquets exist
first; if one is missing, drop that city or build the parquet), design
temperature, FSA prefixes. Grid EF for BC/MB/SK/NS comes from workstream
B — **no hourly pipeline for these provinces** (deliberate): they get the
ECCC/NIR annual average + an estimated marginal only, and the UI labels
them accordingly.

### B. Third EF basis: ECCC/NIR published annual averages — ✅ DONE (2026-07-17)

Built `pipeline/build_grid_ef_annual.py` → `data/processed/grid_ef_annual.json`
(StatCan WDS 38-10-0097 electric-utility GHG ÷ 25-10-0015 utility generation;
national validates to ECCC's 100 g/kWh @2022). heatpump.html EF control is now
3-way (Marginal / Hourly average / ECCC yearly), with the hourly options
disabled + auto-fallback for annual-only provinces, and flat marginal estimates
for SK/NS/NB (hydro provinces = average). METHODOLOGY.md "Third EF basis"
section documents sources, the utility-denominator choice, and the ON/AB scope
deviations. All 15 self-test vectors still pass; verified in-browser (ON: 500 /
96.9 / 56.4 g/kWh across the three bases). Original spec below.

### B (original spec). Third EF basis: ECCC/NIR published annual averages

Add `data/processed/grid_ef_annual.json`: one published annual-average EF
per province per year (g CO₂e/kWh), from ECCC NIR Annex 13 electricity
intensity tables (canada.ca fetches are flaky here — use `curl -L`, or the
open.canada.ca mirror of the electricity-intensity tables; TAF's PDF
already covers ON). Marginal estimates for new provinces: SK ≈ AB's gas
fleet (~540), MB/BC ≈ hydro-dominated — document the choice (gas-fired
margin vs import margin) rather than hand-waving it. UI: EF basis becomes
a 3-way choice — "hourly average (this tool's surface)" / "marginal" /
"ECCC yearly average" — with the first option greyed out for provinces
without an hourly surface. The engine already accepts a flat level via
`efLevel`-style override; a flat annual factor is the degenerate case of
the surface (shape ≡ 1).

### C. Historical weather years + design temperatures — ✅ DONE (2026-07-17)

Built `pipeline/build_weather_years.py` → `weather_<city>.json` × 14 (CWEEDS
2020 1998–2017 + MSC Datamart 2019–2025, 24 yrs each, ~0.8 MB, 2018 gap noted).
Years tagged typical/coldest/mildest by HDD18; multi-decade 2.5%-ile design temp
now matches NBC 2020 Table C-2 closely (Ottawa −24.0 vs −24). heatpump.html gains
a weather-year selector, a weather-file SVG (min–max monthly band + design
markers) and a memoized cross-year emissions band. Verified in-browser (Ottawa
+1..+15%, Vancouver −90..−92%, Halifax +46..+57%); self-test intact. Original
spec below.

### C (original spec). Historical weather years + design temperatures ("weather lens")

- Extend the hourly record to ~20 years (2006–2026) for all cities.
  **Trap:** `dd.weather.gc.ca/today/...` only holds recent data; older
  years come from `climate.weather.gc.ca/climate_data/bulk_data_e.html`
  (per-station, per-month CSV), and station IDs change over time (e.g.
  Ottawa Intl A has different stationIDs pre/post ~2011) — use ECCC's
  Station Inventory CSV to stitch a continuous record per city.
  Alternative worth checking first: CWEEDS 2020 files (same
  collaboration.cmc.ec.gc.ca tree as CWEC) ship multi-decade hourly per
  station in one download.
- From the record, tag **representative years** (closest to TMY HDD),
  **extreme cold** (max HDD / coldest design-week) and **mild** years.
- Add published **design temperatures** (NBC 2020 Appendix C January 2.5%
  and 1% values, which CSA F280-12 references) alongside the computed
  2.5th-percentile values already in METHODOLOGY.md — show both.
- Ship per-city `weather_<city>.json` (quantized 0.1 °C ints, one array
  per year) small enough to lazy-load; UI gains a weather selector
  (TMY / named year / coldest / mildest), a weather-file plot (monthly
  means + temperature-duration curve + design-temp markers), and the
  headline gets a min–max band across years.

### D. Sizing sensitivity (under/oversizing) — ✅ DONE (2026-07-17)

Sizing-sweep card in heatpump.html: `simulate()` re-run at 40–160% of design
heat loss in 5% steps on every input change, charting seasonal COP / backup
share / backup-unmet hours / annual GHG / operating cost vs size, with a marker
at the current slider and a green best-point dot; cost curve hidden for
rates-less cities. Card + METHODOLOGY.md §"Sizing sensitivity" state the
no-cycling-model caveat (oversizing penalty understated; refrigerant-charge
penalty *is* captured). Verified in-browser (Ottawa: 40%→13% backup/5,919 kg,
100%→1.2%/5,337 kg). Original spec below.

### D (original spec). Sizing sensitivity (under/oversizing)

Client-side sweep — `simulate()` is milliseconds, so run it at ~40–160%
of design heat loss in steps and chart seasonal COP, backup share,
lock-out/unmet hours, GHG and operating cost vs sizing, with a marker at
the current slider value. Document the honest limitation: the engine has
no cycling model, so the oversizing penalty (short-cycling, worse
part-load COP) is understated — oversizing looks free here and isn't in
real life; say so on the card.

### E. Lifecycle sourcing — methane, GWP20, line losses, below-lock-out behaviour — ✅ DONE (2026-07-17)

heatpump.html: methane GWP toggle (28 AR5 100-yr / 82.5 AR6 fossil 20-yr), leak
slider widened to 0–5% with NIR-implied/measurement-adjusted/high presets, and an
advanced below-lock-out toggle (hard stop vs continue-derated: capacity
extrapolated on the coldest-segment slope, COP held at floor, labelled
manufacturer-unspecified). Engine change mirrored across app/engine.js + the
inlined heatpump.html copy + validate_engine.py; all 15 in-page self-test vectors
still pass in default mode and **2 new derated vectors** (JS + Python, identical
to 4 dp) were added (engine.test.js / validate_engine.py Case 6). METHODOLOGY.md
§"Lifecycle sourcing" cites ECCC NIR, the ~1.5× atmospheric-measurement
literature (Alvarez 2018; Nature Comms 2021), Canadian post-meter 2.0–2.5×
(IOPscience 2026), reproduces the ~3%-at-GWP20 ≈ ×1.9 arithmetic, and documents
World Bank/IEA T&D (~5%) plus why Portfolio Manager's 2.05 source–site ratio is
not used (double-counts generation losses). Verified in-browser (GWP20 flips the
Ottawa gas verdict from "raises" to "cuts"; derate serves +2,693 kWh at
−35 °C Winnipeg). Original spec below.

### E (original spec). Lifecycle sourcing — methane, GWP20, line losses, below-lock-out behaviour

- **Methane:** add a GWP toggle (100-yr = 28–30 vs 20-yr ≈ 82.5) and widen
  the leak slider to 0–5% with labelled presets: NIR-implied (~0.5–1%),
  measurement-adjusted (~1.5× NIR per the atmospheric-measurement
  literature), high estimate. Add a post-meter leakage note (Canadian
  building-level measurements run 2.0–2.5× the NIR end-use factor).
  Reproduce in METHODOLOGY.md the arithmetic showing ~3% full-chain
  leakage at GWP20 ≈ ×1.9 on gas-heating GHG — the user's remembered
  "×1.9 report" claim — and cite each input. (If the user finds the
  actual report, add it as a named preset.)
- **Line losses:** keep ~5% default; cite World Bank Canada T&D losses
  (~5.1%, 2023) and utility figures (AESO ~4.4% transmission, BC Hydro
  ~10% incl. distribution). Explicitly document why the ENERGY STAR
  Portfolio Manager source–site ratio (2.05 for Canadian electricity) is
  **not** usable here: it includes thermal-generation conversion losses,
  which our g/kWh-generated EF already accounts for — using it would
  double-count.
- **Below-lock-out behaviour:** the Tier-1 −25 °C cut-off is the
  manufacturers' published minimum operating temperature (Mitsubishi
  H2i's guaranteed-operation floor), not a physical stop. Add an
  advanced toggle: "hard stop at published minimum" (current, default)
  vs "continue derated below minimum" (extrapolate capacity on the last
  slope, hold the COP floor); state that below-LCT behaviour is
  manufacturer-unspecified.

### F. Chart re-organization — ✅ DONE (2026-07-17)

heatpump.html's output cards are now six numbered `<section>`s with
Fraunces headers + one-line intros: (01) Verdict & annual GHG breakdown;
(02) How the model works — load-vs-capacity / who-delivers-heat /
equipment curve as tabs sharing a `.seg` control (default tab is the key
chart; "Equipment curve" tab stays advanced-only via `data-mode`); (03)
Across the year — annual + seasonal energy grid-2, monthly emissions,
hourly explorer; (04) Sensitivity lenses — weather-years card, sizing
sweep, and a copy-only "Emissions basis, compared" card pointing at the
existing EF-basis toggle (no new chart built — the toggle already drives
every chart on the page); (05) Operating cost; (06) Assumptions &
methodology (intro added above the existing accordion). DOM/layout/copy
only — no chart-drawing logic touched; the SVG charts (key/source/
equipment/weather/sweep) are viewBox-based so tab-hiding doesn't break
them, confirmed by inspecting `renderKeyChart` etc. Verified in-browser
via the local static-server preview (screenshots are unreliable after
`scroll-behavior:smooth`; used `scrollTo({behavior:'instant'})` per the
known preview quirk): zero console errors, 15/15 self-test vectors, all
Chart.js canvases pixel-sampled non-blank, tab switching confirmed both
directions, `#methodology` anchor + `openMethod()` still work, desktop
(1280px) and mobile (375px) layouts both clean.

<details><summary>Original spec (completed — kept for the record)</summary>

Regroup the output cards into a narrative: (1) Verdict + annual GHG;
(2) "How the model works" — load-vs-capacity, who-delivers-heat,
equipment curve (consider tabs to reduce scroll); (3) "Across the year" —
monthly energy, monthly emissions, hourly explorer; (4) "Sensitivity
lenses" — weather year, sizing sweep, EF basis (new charts from C/D/B);
(5) Operating cost. Section headers with one-line plain-language intros.

</details>

### Suggested order & prompts

B → A → C → D+E → F (B unblocks A's new provinces; C is independent of
A/B but shares the weather pipeline; D/E are small and independent; F
last since it re-homes charts the earlier phases add). Sessions:

### Prompt 1 — ECCC/NIR annual EF basis (Opus)

```
Read PLAN.md, ROADMAP.md item 9 workstream B, and HeatPump/METHODOLOGY.md
(grid EF sections) first. Build HeatPump/pipeline/build_grid_ef_annual.py:
fetch (curl -L; canada.ca is flaky — document what worked) the ECCC
NIR electricity-intensity-by-province tables and produce
data/processed/grid_ef_annual.json: {province: {year: g_per_kWh}} for at
least ON/QC/AB/BC/MB/SK/NS, latest available year plus history, each
value with its source year and NIR edition in a meta block. Cross-check
ON/QC/AB against the tool's own computed annual averages and TAF's
published AEFs; explain deviations in METHODOLOGY.md (NIR is
consumption-based incl. imports? generation-based? state the scope you
find). Add marginal estimates for BC/MB/SK/NS with a documented rationale
per province. Then wire heatpump.html: EF basis becomes a 3-way toggle
(hourly average / marginal / ECCC yearly average); ECCC mode uses a flat
level with shape ≡ 1 through the existing efLevel path; label clearly
which basis is active and add a methodology-panel paragraph. Update
METHODOLOGY.md and this ROADMAP row. Verify in the browser (all cities ×
all 3 bases, no console errors).
```

### Prompt 2 — new cities end-to-end (Opus)

```
Read PLAN.md, ROADMAP.md item 9 workstream A, and HeatPump/METHODOLOGY.md
(Phases 2 and 4) first. Add these cities to the heat pump tool:
Vancouver, Winnipeg, Quebec City, Halifax, Saskatoon, Regina, Hamilton,
London, Windsor (drop any whose ERS parquet C:\ERS\web\ers_web_<PROV>.parquet
is missing — check first and report). For each: (1) CWEC2020 TMY station in
fetch_tmy.py (primary airport; record climate ID in METHODOLOGY.md);
(2) hourly weather 2019+ in fetch_weather.py; (3) archetypes in
build_archetypes.py (FSA prefixes documented like the existing 5);
(4) design temperature (computed 2.5%-ile, same convention); (5) province
wiring: ON cities use the existing ON EF surface; BC/MB/SK/NS cities use
grid_ef_annual.json (ECCC + marginal only — the hourly-average option
must be disabled with an explanatory hint, not silently absent).
Rebuild tmy_temps.json/archetypes.json, update CITY_PROV/CITY_KEY and the
city selector in heatpump.html, update METHODOLOGY.md tables, and verify
each new city in the browser (sane design loads, sane GHG verdicts, no
console errors). Sanity-gate: Vancouver's ASHP seasonal COP must beat
Ottawa's; Winnipeg/Saskatoon design temps should be ≤ Edmonton's ballpark.
```

### Prompt 3 — historical weather years + design temps + weather lens (Opus)

```
Read PLAN.md, ROADMAP.md item 9 workstream C, and HeatPump/METHODOLOGY.md
(Phase 2) first. Extend the weather record to ~2006–2026 for every city
in archetypes.json. First evaluate CWEEDS 2020 (same CMC tree as CWEC) as
the bulk source; fall back to climate.weather.gc.ca bulk_data_e.html
per-station monthly CSVs, using ECCC's Station Inventory to stitch
station-ID changes (document the stitching per city). QC gaps >10% of a
year: flag, don't impute. Outputs: (a) per-city
HeatPump/data/processed/weather_<city>.json — one quantized (0.1 °C int)
8760/8784 array per year plus per-year HDD18 and min-temp summary,
lazy-loaded; (b) NBC 2020 Appendix C January 2.5%/1% design temperatures
added to archetypes.json meta alongside the computed percentiles (cite
the NBC table edition). UI: a "weather year" selector (Typical (TMY) /
each year / coldest / mildest, tagged by HDD); a weather-file card
plotting monthly mean ± band, temperature-duration curve, and design-temp
markers for the selected series; and a headline min–max band across all
years (run simulate() per year — it's fast, but cache). Keep per-city
JSON under ~1 MB (quantize + no whitespace). Update METHODOLOGY.md
(sources, stitching, year tags) and verify in-browser across 3 cities
including one new one.
```

### Prompt 4 — sizing sensitivity + lifecycle sourcing + below-lock-out toggle (Opus)

```
Read ROADMAP.md item 9 workstreams D and E, HeatPump/METHODOLOGY.md
(Phases 3b/5, lifecycle constants) first. Three additions to
heatpump.html (+ engine where needed):
1. Sizing sweep card: run simulate() at 40–160% of design heat loss
   (step ≤5%), chart seasonal COP, backup share, unmet/lock-out hours,
   annual GHG and operating cost vs size, marker at the current slider.
   State on the card that no cycling model exists so oversizing penalties
   are understated.
2. Lifecycle sourcing: methane GWP toggle (100-yr 28 / 20-yr 82.5, AR5 —
   cite), leak slider 0–5% with labelled presets (NIR-implied ~0.5–1%;
   measurement-adjusted ~1.5×; high). Research and cite in
   METHODOLOGY.md: ECCC NIR upstream methane, the atmospheric-measurement
   underestimation literature (~1.5×), Canadian post-meter building
   measurements (2.0–2.5× NIR end-use factor), and reproduce the
   arithmetic showing ~3% full-chain leakage at GWP20 ≈ ×1.9 on gas
   heating GHG. Line losses: keep 5% default; cite World Bank Canada T&D
   (~5.1%) and utility figures; add a METHODOLOGY.md paragraph explaining
   why Portfolio Manager's 2.05 source-site ratio would double-count
   generation losses and is not used.
3. Below-lock-out toggle (advanced): default "hard stop at published
   minimum operating temperature" (current behaviour); alternative
   "continue derated below minimum" — capacity extrapolated on the last
   segment slope, COP held at the floor, clearly labelled
   manufacturer-unspecified. Engine change must keep all 15 self-test
   vectors passing unchanged in default mode; add 2 new vectors for the
   derated mode (JS + Python mirror, identical to 4 dp).
Verify everything in-browser; update METHODOLOGY.md and the assumptions
panel.
```

### Prompt 5 — chart re-organization (Sonnet)

```
Read ROADMAP.md item 9 workstream F. Reorganize heatpump.html's output
cards into titled sections with one-line intros: (1) Verdict + annual
GHG breakdown; (2) How the model works (load-vs-capacity, who delivers
the heat, equipment curve — tabbed if it reduces scroll without hiding
the key chart); (3) Across the year (monthly energy, monthly emissions,
hourly explorer); (4) Sensitivity lenses (weather year + band, sizing
sweep, EF basis comparison); (5) Operating cost; (6) Assumptions &
methodology. No chart logic changes — DOM/layout/copy only. Keep
anchors/IDs working, mobile layout intact, dark mode intact. Verify
in-browser at desktop and mobile widths, no console errors, screenshot
each section.
```

---

## 10. Retrofit Explorer — post-launch additions (✅ DONE 2026-07-17)

Four user-requested additions to `retrofits.html` (FSA view):

1. **Audits-per-year × type chart** — new advanced card in "What was upgraded":
   stacked bars per audit year, two stacks (initial D / follow-up E), each split
   into the current filter selection (solid) vs filtered-out (faded). New
   `renderAuditYearChart()`, called from `renderAdvancedSections()`; recomputes
   with the filters.
2. **"Retrofits selected" KPI** — new first stat-card: matched homes matching the
   filters, and that as a % of the area's full audited population (every HOUSEID
   with any D or E audit). Denominator = new `dore_count` field in each
   `_index.json` entry (`doreCountForSelectedFsa()`).
3. **Detail-panel layout fix** — pinned the envelope-measures column width in
   `makeInlineSVG()` so the HVAC & energy subtable no longer shifts between homes.
4. **Section/measure icons** — hand-crafted inline SVG line-icons (`ICONS` map +
   `injectIcons()`), injected into section `<h2>`s and measure sub-chart titles
   via `data-icon` attributes.

**Data:** `dore_count` is produced by a new lightweight raw-CSV scan
(`Python/build_fsa_audit_totals.py` → `C:\ERS\web\fsa_audit_totals.json`, ~2.15M
HOUSEIDs, 1,692 FSA cells) and folded into `_index.json` by `split_fsa_json.py`
(re-run from the existing parquet — the heavy `ers_web_pipeline.py` is untouched).
Sanity: `dore_count ≥ row_count` for all 1,661 shipped FSAs, no nulls. Updated
`_index.json` copied into the repo `fsa_json/<PROV>/`.

---

## 11. Retrofit Explorer — audit funnel, province/Canada audits-per-year, pairing-filter fix (✅ 2026-07-18)

**11a · Audit-funnel Sankey + audits-per-year everywhere.**
- New `renderFunnel()` card ("From every audit to your selection") on `retrofits.html`,
  kept alongside the existing fuel-flow Sankey. A home-composition funnel: all audited
  homes → {Both D&E, D-only, E-only, New build P/N} → Matched pairs (+ Not paired) →
  Meets filters (+ Filtered out). Left three stages are fixed per area; only the last
  split tracks the dropdowns. Works in FSA / province / Canada views.
- Fixed the audits-per-year chart for province & Canada (was FSA-only, needed row-level
  `Pre/Post_Year`): `precompute_province_stats.py` now ships per-slice `d_year_bins`/
  `e_year_bins`, `aggregate_canada.py` rolls them up, new `renderProvinceAuditYearChart()`.
- **Data contract change:** `build_fsa_audit_totals.py` output reshaped to
  `{"by_fsa":{PROV:{FSA:{t,de,d,e,nc}}},"by_province":{...}}` (composition, now incl. P/N),
  feeding both the `dore_count` KPI and the funnel. `precompute` reads `by_province` →
  province `funnel` block; `split_fsa_json` folds `composition` into `_index.json`. See
  the [[ers-retrofit-data-refresh]] memory for the updated run order (build_fsa_audit_totals
  must precede BOTH precompute and split_fsa now).

**11b · Pairing-drop investigation + Gate D fix.**
The funnel exposed that only ~537,881 of ~1.63M homes-with-both-D&E become matched pairs.
Diagnostics (`Python/diagnose_pairing_drops.py`, `Python/diagnose_gates_ab.py`) attributed
each dropped home to its first-failing gate (pipeline order): A multiple audits 9.1%,
B E-not-after-D 5.2%, C floor-area>10% 0.4%, **D structural 52.2%**. Gate D was almost
entirely a `NUMDWELLINGUNITS` artifact — under pandas 3.x, `astype(str)` keeps missing as
NaN and NaN≠NaN, so both-blank compared unequal (89%), plus `'1.0'` vs `'1'` format (8%);
only 0.1% were genuine unit changes.
- **Fixed** the structural filter in `ers_web_pipeline.py` (`same_categorical`/`same_numeric`
  helpers): both-blank → unchanged (kept), `NUMDWELLINGUNITS` compared as a number
  (`'1.0'`==`'1'`); still drops one-side-blank and genuinely-different. Full pipeline re-run;
  matched pairs 537,881 → **1,369,305** (~2.5×; ON 222,515 → 672,857). Downstream
  (`precompute`/`split_fsa`/`aggregate_canada`) + repo copy of `province_json` and full
  `fsa_json` re-done (`build_fsa_audit_totals` NOT re-run — composition unchanged).
- **Gates A & B kept as-is** (strict 1 D + 1 E; E strictly after D) pending questions to the
  NRCan EnerGuide team, documented in a new "A′ · Open questions" methodology subsection in
  `retrofits.html`. Gate B is a month-precision date artifact (99.4% same-month ties); Gate A
  could relax to oldest-D + newest-E (99.6% date-valid) but risks merging separate retrofit
  rounds. See [[ers-pairing-dwellingunits-drop]] memory.

---

## 12. Retrofit Explorer — EnerGuide-demo visual polish (✅ 2026-07-18)

Five presentation fixes to `retrofits.html` ahead of a demo to the EnerGuide team, no pipeline
or data-contract changes — all front-end.

1. **FSA map colour scale.** `buildFsaColorScale()` switched from a straight linear lerp to a
   gamma-corrected one (`lerpColorGamma`, `t^0.55`): the old 0%→light-grey/40%→green ramp left
   most of a province's real range (typically 0–40%) looking near-identical pale. The legend
   gradient is now sampled from the same function (10 stops) instead of a flat 2-stop CSS
   gradient, so it actually matches the fill. Each FSA shape also prints its own median-saving %
   at its bbox centre (`paintFsaMap()`), sized off that shape's own footprint and skipped below
   a legibility floor; text colour picked for contrast against its fill (`textColorForFill()`).
2. **KPI row: 10 boxes, 2×5, reordered.** Added "Avg. measures per home" (mean of the 8 tracked
   measure flags per matched home — computed client-side from existing data, no pipeline change)
   to the `.stats-grid`, now fixed at `repeat(5,1fr)` (was `auto-fit`, which didn't reliably give
   2 rows). Reordered to outcomes-first / activity-second: selected → energy → EUI → GHG → bill
   saving, then avg. measures → deep retrofits → heat pumps → fuel switches → solar PV.
3. **Audit funnel colours.** Columns 2 (Matched pairs) and 3 (Meets filters) both used the same
   green, making the funnel's last two stages hard to tell apart. Column 3 ("Meets filters" /
   "Filtered out") recoloured to amber (`#E8A124`/`#F2D9A6`), added to the funnel legend.
4. **Heating-fuel Sankey.** `FUEL_COLORS` already assigned a fixed hex per fuel (this predates
   the session) — only change was `Electricity` blue → green (`#1A7A55`), since electricity is
   the cleanest option on every grid this tool covers and switching *into* it should read as
   "toward green."
5. **Per-measure info buttons.** The "What measures were done" card had one combined "?" covering
   all 8 measures. Removed it; each `MEASURES` entry now carries its own `tip` string, rendered
   as a per-row info button in both `renderMeasures()` (FSA) and `renderProvinceMeasures()`.

Methodology updated in `retrofits.html`: "Fields we calculate ourselves" (avg. measures
definition), Advanced section C (calculated-field table row), and a new "Map colour scale"
paragraph in Advanced section F.

---

## Session hygiene

- Each prompt is self-contained; run in a fresh session, in order within an item.
- After each session: update the project's STATUS/METHODOLOGY file, commit.
- Remaining dependency: item 4 Phase 0 → Phase 1 → Phase 2 (heat pump cost
  integration) in order. Items 2, 5, 6-page and 7 are independent of each other
  and of item 4 — any order. Item 5's grid-dashboard card is "coming soon"
  until 6-page ships (flip it then).
- Opus for methodology-heavy or design-heavy work (silent-error risk); Sonnet
  for data plumbing with clear validation criteria.
