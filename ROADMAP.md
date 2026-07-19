# Energy Suite — Project Tracker & Roadmap

The single source of truth for what's shipped, what's in flight, and what's next.
Updated **2026-07-18** (verified against the repo, GitHub Actions, and the live site).

- 📦 Full record of completed items (prompts + build notes): [docs/archive/ROADMAP_COMPLETED.md](docs/archive/ROADMAP_COMPLETED.md)
- 🗺️ Visual status page: [project-atlas.html](project-atlas.html) — <https://ottawavisuals.github.io/Energy/project-atlas>
- 📖 Main readme (all links): [README.md](README.md)

---

## 📊 Status board

### Shipped & live ✅

| Tool | Live | Docs | Notes |
|---|---|---|---|
| 🏠 **Retrofit Explorer** | [/retrofits](https://ottawavisuals.github.io/Energy/retrofits) | [docs/RETROFITS.md](docs/RETROFITS.md) | v1 + post-launch additions, audit funnel, pairing fix (matched 538k → 1.37M), bill card, visual polish |
| 🏡 **New Homes Explorer** | [/newhomes](https://ottawavisuals.github.io/Energy/newhomes) | [docs/RETROFITS.md](docs/RETROFITS.md) | EnerGuide new-construction slice (plan/as-built); shipped 2026-07-15 |
| 📊 **CEUD Explorer** | [/ceud](https://ottawavisuals.github.io/Energy/ceud) | [docs/CEUD.md](docs/CEUD.md) | all 5 sectors live |
| 🏗️ **Construction Tracker** | [/construction](https://ottawavisuals.github.io/Energy/construction) | [docs/CONSTRUCTION.md](docs/CONSTRUCTION.md) | monthly auto-refresh; **first scheduled run 2026-07-20 — watch it go green** |
| 🌍 **Ottawa Geothermal Map** | [/Geothermal/output/](https://ottawavisuals.github.io/Energy/Geothermal/output/) | [Geothermal/README.md](Geothermal/README.md) | v2 complete: conductivity sensitivity, drilling difficulty, segment suitability |
| 🔥 **Heat Pump Explorer** | [/heatpump](https://ottawavisuals.github.io/Energy/heatpump) | [HeatPump/METHODOLOGY.md](HeatPump/METHODOLOGY.md) | v2 complete: 14 cities, weather-year lens, sizing sweep, lifecycle sourcing, operating costs |
| 🗺️ **Project Atlas** | [/project-atlas](https://ottawavisuals.github.io/Energy/project-atlas) | — | internal status/assumptions page — keep in sync when items ship |

**Data layers behind the tools (all built, all auto-refreshing):**

| Layer | Refresh | Status |
|---|---|---|
| Energy prices (`prices_json/`) | monthly, 3rd — `rates-refresh.yml` | ✅ built; first scheduled run **2026-08-03** |
| Grid mix ETL (`grid_json/`) | weekly, Mon — `grid-refresh.yml` | ✅ first scheduled run went **green 2026-07-13** |
| Construction data (`construction_json/`) | monthly, 20th — `construction-refresh.yml` | ✅ built; first scheduled run **2026-07-20** |
| Utility rates for bill cards (`utility_rates_reference.json`) | manual (`Python/utility_rates_reference.py`) | ✅ shipped 2026-07-18 |

### In flight 🔨

| Project | Progress | Next step |
|---|---|---|
| 🏙️ **Ottawa Case Study** (heat demand → electrification → grid) | `██████░░░` Phases 0–3 of 6 done | **Phase 4:** aggregate to 500 m grid + feeders, apply coincidence factor → [item 7](#7-ottawa-case-study--heat-demand-electrification-grid-in-progress) |

### Queued 🆕

| Project | Size | Blocked by |
|---|---|---|
| 📈 **Retrofit Insights** — national "big picture" page | 4 sessions | nothing — [item 13](#13-retrofit-insights--national-big-picture-page-4-sessions) |
| 🚪 **Landing page hub** (`index.html`) | 1 session | nothing — [item 5](#5-landing-page-hub-1-session) |
| ⚡ **Live grid dashboard page** (`grid.html`) | 1 session | nothing (ETL done) — [item 6](#6-live-grid-dashboard-page-1-session) |

---

## 🎯 What's next — recommended order

1. **Ottawa Case Study Phases 4 → 5 → 6** (item 7). The flagship. Phase 4 is the
   defensibility step (coincidence factor — Phase 3 proved the undiversified sums
   are upper bounds); Phase 6 is the public narrative page the whole project
   builds toward.
2. **Retrofit Insights** (item 13, Phases 0 → 3). Independent of everything else;
   biggest audience payoff after the case study. Phase 0 (income + HDD/CDD ETLs)
   is cheap and unblocks the rest.
3. **Landing page hub** (item 5). One session, makes everything else findable.
   Do after Insights ships so its card isn't "coming soon" (or ship now and add
   cards later — cards are cheap to add).
4. **Grid dashboard page** (item 6). ETL already refreshes weekly; one page
   session. Doubles as the heat-pump marginal-emissions explainer.

**Small loose ends (fold into any session):**

- [ ] Rerun `Python/build_ahri_lookup.py` — `lookup/ahri_numbers.json` is missing
      7 newly-seen AHRI numbers (flagged 2026-07-12).
- [ ] `Geothermal/scripts/build_building_demand.py` has the parquet-metadata
      clobbering bug Phase 3 fixed in its own writer — re-running Phase 2 today
      would silently destroy the `heatdemand_phase3` note (flagged 2026-07-17).
- [ ] Watch first scheduled runs: construction **2026-07-20**, rates **2026-08-03**.
- [ ] `project-atlas.html` has no New Homes Explorer section; add one next time
      the atlas is open.

---

## 5. Landing page hub (1 session)

Seven (soon eight) tools, no front door — `…/Energy/` still 404s.

### Prompt (Opus — design-heavy)

```text
Read README.md and skim retrofits.html, ceud.html, construction.html
headers/hero sections for the shared design system. Build index.html at the
repo root: a landing page in the same navy/amber/cream + Fraunces/Inter
language presenting the suite ("Ottawa Visuals — Canadian energy data
tools"). One card per tool — Retrofit Explorer, New Homes Explorer, CEUD
Explorer, Construction Tracker, Ottawa Geothermal Map
(https://ottawavisuals.github.io/Energy/Geothermal/output/), and the Heat
Pump Explorer (https://ottawavisuals.github.io/Energy/heatpump — live, NOT
coming-soon), plus a greyed "coming soon" card for the grid dashboard
(grid.html, ROADMAP.md item 6) — each with a one-sentence plain-language
description, the data source, and a small representative static graphic
(inline SVG, no live data fetches; keep the page < 200 KB total). Add a
short "about the data" footer. Follow the deployment pattern the other
pages use so it becomes the site's front page, and add cross-links from
each existing tool's header back to the hub (small, unobtrusive). Verify
in a browser preview at mobile and desktop widths.
```

---

## 6. Live grid dashboard page (1 session)

ETL is **done and auto-refreshing weekly** (`Python/grid_etl.py` →
`grid_json/{grid_on,grid_ab,grid_qc,meta}.json`; first scheduled run went green
2026-07-13). ON (IESO) is fully live; AB is parse-only from manually placed CSD
zips (no scriptable recent AESO source — real-time API needs a key we don't
have); QC is a static flat-EF context card. Full ETL notes in
[docs/archive/ROADMAP_COMPLETED.md](docs/archive/ROADMAP_COMPLETED.md) (item 6)
and the script docstring.

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

## 13. Retrofit Insights — national "big picture" page (4 sessions)

Planned 2026-07-18: `retrofits.html` is deep on *one* area at a time; this adds
the cross-sectional national view as a **separate page**,
`retrofit-insights.html` (sibling of retrofits.html, linked both ways). Scope
decisions made with the user: analysis is **descriptive + stratified** (no fitted
regression models in v1); equity lens is **income quintiles only** (no $-burden
energy-poverty modeling in v1 — extracting income is still required); all four
optional sections are in (program-era timeline, heat-pump geography,
missed-opportunity ranking, provincial scorecard).

**Architecture** (same pattern as every other tool): offline Python precompute →
compact committed JSON (`insights_json/`) → one self-contained page fetching via
the BASE_URL pattern. Row-level source is the ERS parquets
(`C:\ERS\web\ers_web_<PROV>.parquet`), NOT the shipped `fsa_json/` (which is the
page-serving split of the same data). Two data gaps must be filled first
(Phase 0): per-FSA **HDD/CDD** (new ECCC climate-normals join) and per-FSA
**income** (extension of `extract_fsa_census.py` — the source CSV has ~2,631
characteristics per FSA; income is in there, just not extracted).

**Analysis inventory the page is built on** (Phase 1 computes; Phase 2 renders):

1. **National KPIs + provincial scorecard** — participation, matched retrofits,
   median saving %, HP adoption, fuel-switch rate, deep-retrofit rate per
   province; the 30-second summary.
2. **Leaderboards + choropleth with metric switcher** — top/bottom FSAs by:
   participation rate (audited homes ÷ 2021 census dwellings), median saving %,
   pre-EUI (worst stock), pre-GHG, HP adoption. Min-n threshold so tiny FSAs
   don't dominate.
3. **What makes a successful retrofit** — top-decile savers vs the rest:
   measure-bundle savings (top combos of the 8 flags), savings vs number of
   measures, savings by vintage × climate band, starting-EUI effect.
4. **Climate linkage** — per-FSA HDD bands: pre-EUI vs HDD, savings vs HDD,
   measure mix vs HDD, HP adoption vs HDD (and CDD for the cooling/HP angle).
5. **Equity (income quintiles)** — participation, savings, HP adoption and
   deep-retrofit rate by FSA income quintile; dwelling value as secondary axis.
6. **Heat-pump geography** — HP-adoption choropleth, climate/income linkage,
   national top models (already aggregated in `province_json/CA.json` ahri data).
7. **Missed opportunity** — composite ranking: worst stock (high pre-EUI/GHG,
   old vintage) × lowest participation = "where programs should look next".
   Documented formula, screening-tool caveat.
8. **Program-era timeline** — national audits/retrofits per year annotated with
   program history (EnerGuide for Houses → ecoENERGY Retrofit–Homes → Greener
   Homes), explaining the volume spikes.

**Honesty rails (bake into every phase):** savings are modeled EnerGuide
estimates, not measured bills; negative savings are dominated by audit noise
(74% of negative-savers logged zero tracked measures — see retrofits.html
methodology); participation mixes ~20 years of cumulative audits over a 2021
dwelling snapshot; FSA-level income correlations are ecological, not
household-level ("rich FSAs" ≠ "rich participants"); ERS is self-selected, not
a random sample. Each section states its caveat on-page.

### Prompt — Phase 0: data enrichment ETLs (Sonnet)

```text
Read ROADMAP.md item 13 first. Two independent data gaps to fill for the
Retrofit Insights page; both are offline ETLs, no page work.

1. Income per FSA. Extend Python/extract_fsa_census.py: from the StatCan
   2021 Census Profile FSA CSV (Census/98-401-X2021013_English_CSV_data.csv,
   long format, 2,631 characteristics × 1,646 FSAs — the script's docstring
   explains the fixed-block fast read), also extract into a new
   "income" group: median total household income, median after-tax
   household income, prevalence of low income LIM-AT (%), and average
   household size. Find the exact CHARACTERISTIC_IDs in
   Census/98-401-X2021013_English_meta.txt — do not guess; print the
   matched characteristic names for verification. Re-run → census_json/
   fsa_census.json (existing fields must be byte-identical apart from the
   new group; verify). Sanity: national dwelling-weighted median income
   should land near StatCan's published 2020 Canada median (~$84k
   before-tax) — print the comparison.
2. HDD/CDD per FSA. New Python/build_fsa_climate.py: fetch ECCC Canadian
   Climate Normals station data (prefer 1991–2020 where published, else
   1981–2010 — record which per station) including heating degree-days
   below 18 °C and cooling degree-days above 18 °C. ECCC bulk endpoints
   need curl -L / requests with browser UA (see memory notes; WebFetch is
   blocked for some ECCC hosts). Cache raw pulls. Compute each FSA's
   centroid from FSA_Maps/<PROV>.geojson (note: file is NL.geojson but
   fsa_json/province_json use NF — normalize; PE and the territories have
   no fsa_json dir, still emit their FSAs if geometry exists) and assign
   HDD/CDD from the nearest station(s) — inverse-distance-weight the 3
   nearest stations within 200 km, else nearest single, and record
   per-FSA the station(s) + distance used. Output
   climate_json/fsa_climate.json: {FSA: {hdd, cdd, station, dist_km,
   normals_period}} — compact, one file. Validate: Ottawa-area FSAs
   ~4,400–4,600 HDD, Vancouver ~2,700–3,000, Winnipeg ~5,500–5,900;
   print a 10-FSA spot-check table and the national HDD distribution.
Document both in the scripts' docstrings; nothing else changes yet.
```

### Prompt — Phase 1: analysis precompute (Opus)

```text
Read ROADMAP.md item 13 (analysis inventory + honesty rails) first, plus
Python/precompute_province_stats.py and Python/split_fsa_json.py for the
established conventions (parquet reading, bin shapes, output style).
Build Python/build_insights.py reading the ERS parquets
(C:\ERS\web\ers_web_<PROV>.parquet — matched pairs, same rows retrofits.html
serves), C:\ERS\web\fsa_audit_totals.json (audit composition incl.
unmatched), census_json/fsa_census.json (incl. Phase 0 income group), and
climate_json/fsa_climate.json. Output compact insights_json/:

- fsa_metrics.json — one record per FSA (~1,650): matched count, audited
  count (dore), participation rate (audited ÷ census total_dwellings),
  matched-retrofit rate, median saving %, median pre/post EUI, median
  pre/post GHG, HP-addition rate, deep-retrofit rate, fuel-switch rate,
  measure-mix shares, hdd, cdd, income quintile (national,
  dwelling-weighted), median income, median dwelling value, pre-1980
  dwelling share. Null-safe; include n so the page can threshold.
- success.json — national stratified analysis: (a) savings distribution
  by measure bundle for the ~15 most common combos of the 8 flags, with
  n per bundle; (b) median savings vs number of measures (0–8);
  (c) savings by vintage band × HDD band; (d) top-decile savers vs rest:
  measure prevalence, starting EUI, vintage, fuel-switch share.
  Exclude zero-measure pairs from "what worked" stats (they're the audit-
  noise population) but report their count.
- climate.json — HDD-band (and CDD-band) aggregates: pre-EUI, saving %,
  HP rate, measure mix per band, with n.
- equity.json — income-quintile aggregates: participation, saving %, HP
  rate, deep-retrofit rate, pre-EUI per quintile; same by dwelling-value
  quintile as the secondary axis.
- opportunity.json — missed-opportunity ranking: normalized composite of
  high pre-EUI, high pre-GHG, high pre-1980 share, LOW participation;
  document the formula + weights in the script and emit per-FSA factor
  values so the page can show the breakdown. Round scores (no false
  precision).
- timeline.json — national + per-province audits per year (D and E) and
  matched retrofits by E-year. Research the program eras with WebSearch
  and cite: EnerGuide for Houses (~1998), ecoENERGY Retrofit–Homes
  (2007–2012), provincial programs if clearly attributable, Canada
  Greener Homes Grant (2021 launch, closed to new applicants 2024) —
  emit an annotations list {year_start, year_end, label, source_url}.
- meta.json — sources, build date, thresholds, formulas.

Total insights_json/ budget: < 2 MB. Validation printouts: fsa_metrics
medians for 3 known FSAs cross-checked against fsa_json/<PROV>/_index.json;
national matched total == sum of province_json totals (1,369,305-era
numbers); leaderboard top-10s by each metric printed for eyeballing;
income-quintile cut points printed. ALSO write Python/insights_notes.md —
a findings memo (what the top FSAs actually are, the strongest and
weakest linkages, surprises, anything that looks like an artifact) so the
Phase 2 page copy is grounded in real numbers, not placeholders. Flag any
correlation that is likely composition-driven (e.g. climate vs fuel mix)
rather than causal.
```

### Prompt — Phase 2: the page (Opus — design-heavy)

```text
Read ROADMAP.md item 13, Python/insights_notes.md (the findings memo — the
page copy must reflect its real numbers), and insights_json/meta.json
first. Skim retrofits.html for the shared design system (navy #0B2545 /
amber #E8A124 / cream #F7F4EE, Fraunces + Inter, white cards, sticky
header, Simple/Advanced toggle, BASE_URL localhost pattern) and reuse its
FSA-map rendering approach (FSA_Maps/<PROV>.geojson + gamma-corrected
color scale + min-n handling) rather than reinventing it. Run /dataviz
before building any chart.

Build retrofit-insights.html — single self-contained file, national
scope, narrative order: (01) hero + national KPIs; (02) provincial
scorecard; (03) the map — one Canada-wide FSA choropleth with a metric
switcher (participation / median saving / pre-EUI / pre-GHG / HP
adoption) + top-10/bottom-10 leaderboards beside it that update with the
metric, min-n threshold stated; (04) what makes a successful retrofit
(bundle chart, savings-vs-measure-count, top-decile-vs-rest profile);
(05) climate lens (HDD-band charts); (06) who participates — income
quintiles (ecological-fallacy caveat on the card); (07) heat-pump
geography (adoption map metric + climate/income linkage + national top
models); (08) missed opportunity (ranked table + map metric, formula
breakdown in popover, screening caveat); (09) the program-era timeline
(audits/yr with era annotations); (10) methodology accordion covering
every formula, threshold and honesty rail from ROADMAP item 13. Each
section: Fraunces header + one-line plain-language intro + the "so what"
sentence pulled from insights_notes.md. Advanced toggle hides the denser
cards (04c, CDD, dwelling-value quintiles). Cross-link retrofits.html ↔
retrofit-insights.html in both headers.

Loading discipline: fetch insights_json files lazily per section;
Canada-wide FSA geometry is large, so load per-province geojson
progressively and show the map skeleton first. Verify in the browser
preview at desktop + mobile widths: zero console errors, every metric
switch repaints map + leaderboards consistently, all numbers spot-check
against insights_json. Remember this environment's preview quirks (no
rAF: Chart.js needs animation:false + forced draw; verify canvases via
pixel sampling, not screenshots; scrolling needs behavior:'instant').
```

### Prompt — Phase 3: ship & integrate (Sonnet)

```text
Read ROADMAP.md item 13 first. retrofit-insights.html and insights_json/
exist and are browser-verified. Ship + integrate:
1. Commit insights_json/, climate_json/, the updated census_json/,
   retrofit-insights.html, the new Python scripts, and the retrofits.html
   header cross-link. Push, then verify the live Pages URL loads with no
   console errors and the JSONs serve 200.
2. README.md: add the page to the tool list with its live URL; update the
   repository-layout section (insights_json/, climate_json/).
3. project-atlas.html: add/flip the Retrofit Insights row.
4. Refresh chain: document in build_insights.py's docstring where it sits
   in the ERS refresh order (after ers_web_pipeline + build_fsa_audit_totals,
   independent of split_fsa_json), and add that line to the run-order notes
   wherever the chain is documented. The census + climate inputs are
   static (2021 Census / climate normals) — say so, they do NOT join the
   refresh cadence.
5. Flip ROADMAP.md item 13's status row and status-board row to done
   with a one-paragraph summary of what shipped.
```

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
| 6-ETL | Grid dashboard ETL + weekly workflow | 2026-07-12 |
| 8 | Geothermal v2 (4 phases) | 2026-07-15 |
| 9 | Heat Pump v2 (6 workstreams) | 2026-07-17 |
| 10 | Retrofit Explorer post-launch additions | 2026-07-17 |
| 11 | Retrofit audit funnel + pairing-filter fix | 2026-07-18 |
| 12 | Retrofit EnerGuide-demo visual polish | 2026-07-18 |
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
