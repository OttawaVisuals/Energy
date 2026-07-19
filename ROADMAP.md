# Energy Suite — Project Tracker & Roadmap

The single source of truth for what's shipped, what's in flight, and what's next.
Updated **2026-07-19** (verified against the repo, GitHub Actions, and the live site).

- 📦 Full record of completed items (prompts + build notes): [docs/archive/ROADMAP_COMPLETED.md](docs/archive/ROADMAP_COMPLETED.md)
- 🗺️ Visual status page: [project-atlas.html](project-atlas.html) — <https://ottawavisuals.github.io/Energy/project-atlas>
- 📖 Main readme (all links): [README.md](README.md)

---

## 📊 Status board

### Shipped & live ✅

| Tool | Live | Docs | Notes |
|---|---|---|---|
| 🏠 **Retrofit Explorer** | [/retrofits](https://ottawavisuals.github.io/Energy/retrofits) | [docs/RETROFITS.md](docs/RETROFITS.md) | v1 + post-launch additions, audit funnel, pairing fix (matched 538k → 1.37M), bill card, visual polish |
| 📈 **Retrofit Insights** | [/retrofit-insights](https://ottawavisuals.github.io/Energy/retrofit-insights) | [docs/archive/ROADMAP_COMPLETED.md](docs/archive/ROADMAP_COMPLETED.md) (item 13) | national big-picture page: leaderboards, choropleth, success analysis, climate/equity linkage, missed-opportunity ranking, program-era timeline; shipped 2026-07-19 |
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
| 🚪 **Landing page hub** (`index.html`) | 1 session | nothing — [item 5](#5-landing-page-hub-1-session) |
| ⚡ **Live grid dashboard page** (`grid.html`) | 1 session | nothing (ETL done) — [item 6](#6-live-grid-dashboard-page-1-session) |

---

## 🎯 What's next — recommended order

1. **Ottawa Case Study Phases 4 → 5 → 6** (item 7). The flagship. Phase 4 is the
   defensibility step (coincidence factor — Phase 3 proved the undiversified sums
   are upper bounds); Phase 6 is the public narrative page the whole project
   builds toward.
2. **Landing page hub** (item 5). One session, makes everything else findable —
   now including Retrofit Insights, shipped 2026-07-19 (item 13, archived).
3. **Grid dashboard page** (item 6). ETL already refreshes weekly; one page
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
| 13 | Retrofit Insights — national "big picture" page | 2026-07-19 |
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
