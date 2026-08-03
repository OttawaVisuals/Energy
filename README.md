# Energy Suite — Canadian energy data tools

A collection of interactive, open-data tools about how Canada uses energy:
home retrofits, new construction, heat pumps, geothermal potential, grid
emissions, energy prices and construction activity. Every tool follows the same
pattern: an offline Python pipeline turns public data into compact committed
JSON, and a single self-contained HTML page renders it — no backend, hosted on
GitHub Pages.

> **📋 [Project Tracker & Roadmap → ROADMAP.md](ROADMAP.md)** — what's shipped,
> what's in flight, what's next. Start here.

**🏠 [Landing page →](https://ottawavisuals.github.io/Energy/)** — one card per
tool, the public front door.

## 🔗 Live tools

| Tool | What it is | Live page |
|---|---|---|
| 🏠 **Retrofit Explorer** | 1.45M real Canadian home-energy retrofits (NRCan EnerGuide audits, 2004–2026) — savings, measures, per-FSA drill-down | [/retrofits](https://ottawavisuals.github.io/Energy/retrofits) |
| 📈 **Retrofit Insights** | National big-picture view of the same 1.45M retrofits — leaderboards, choropleth, what makes a retrofit work, climate/equity linkage, missed-opportunity ranking, program-era timeline | [/retrofit-insights](https://ottawavisuals.github.io/Energy/retrofit-insights) |
| 🏡 **New Homes Explorer** | How efficient new construction actually is — as-designed vs as-built EnerGuide evaluations | [/newhomes](https://ottawavisuals.github.io/Energy/newhomes) |
| 🔥 **Heat Pump Explorer** | Hourly simulation of switching to a cold-climate heat pump in 14 cities: energy, GHG, costs, backup needs | [/heatpump](https://ottawavisuals.github.io/Energy/heatpump) |
| 🌍 **Ottawa Geothermal Map** | Ground-source heat pump screening for Ottawa: conductivity from 55k water wells, drilling difficulty, grid capacity | [/Geothermal/output/](https://ottawavisuals.github.io/Energy/Geothermal/output/) |
| 📊 **CEUD Explorer** | NRCan's Comprehensive Energy Use Database, browsable — all 5 sectors, national + provincial | [/ceud](https://ottawavisuals.github.io/Energy/ceud) |
| 🏗️ **Construction Tracker** | Permits, housing starts and construction investment — national / provincial / metro | [/construction](https://ottawavisuals.github.io/Energy/construction) |
| ⚡ **Grid Dashboard** | Ontario/Alberta generation mix & emissions intensity, plus the average-vs-marginal emissions explainer | [/grid](https://ottawavisuals.github.io/Energy/grid) |
| 🗺️ **Project Atlas** | Internal status & assumptions page for the suite | [/project-atlas](https://ottawavisuals.github.io/Energy/project-atlas) |

**Coming:** the Ottawa Case Study (heat demand → electrification → grid) —
the only thing left on the roadmap. See the [roadmap](ROADMAP.md).

## 📖 Documentation per project

| Project | Docs |
|---|---|
| Retrofit Explorer | [docs/RETROFITS.md](docs/RETROFITS.md) — data pipeline, unit conversions, flag rules, bin-width contract, changelog |
| Retrofit Insights | [ROADMAP.md](ROADMAP.md) item 13 (archived: [docs/archive/ROADMAP_COMPLETED.md](docs/archive/ROADMAP_COMPLETED.md)) — analysis inventory, honesty rails, `build_insights.py`. *No `docs/RETROFIT_INSIGHTS.md` yet — its methodology lives inline in the page.* |
| Retrofit Costs (inside Retrofit Explorer) | [docs/RETROFIT_COSTS.md](docs/RETROFIT_COSTS.md) — REMDB pairing, per-measure formulas, utility-rate sourcing, every assumption |
| New Homes Explorer | [docs/NEWHOMES.md](docs/NEWHOMES.md) |
| Heat Pump Explorer | [HeatPump/METHODOLOGY.md](HeatPump/METHODOLOGY.md) (methodology) · [HeatPump/PLAN.md](HeatPump/PLAN.md) (original plan) |
| Ottawa Geothermal Map | [Geothermal/README.md](Geothermal/README.md) (full methodology) · [GEOTHERMAL_STATUS.md](GEOTHERMAL_STATUS.md) (build log) |
| Ottawa Case Study / heat demand | [HEATDEMAND_PLAN.md](HEATDEMAND_PLAN.md) (active plan) |
| CEUD Explorer | [docs/CEUD.md](docs/CEUD.md) |
| Construction Tracker | [docs/CONSTRUCTION.md](docs/CONSTRUCTION.md) |
| *(cross-cutting)* Open questions for NRCan | [docs/ENERGUIDE_QUESTIONS.md](docs/ENERGUIDE_QUESTIONS.md) — consolidated EnerGuide/HOT2000 questions across all ERS-based tools |
| Grid Dashboard | [docs/GRID.md](docs/GRID.md) |
| Completed plans (archive) | [docs/archive/](docs/archive/README.md) |

## 🗂️ Repository layout

```
Energy/
├─ *.html                    # one page per tool
├─ assets/                   # shared site theme, retrofits.css/.js, og/ preview cards
├─ ROADMAP.md                # ← the project tracker
├─ README.md                 # this file
├─ HEATDEMAND_PLAN.md        # active plan: Ottawa Case Study
├─ GEOTHERMAL_STATUS.md      # active build log (geothermal + heat demand)
├─ docs/                     # per-project docs + docs/archive/ (completed plans)
├─ Python/                   # all ETL/pipeline scripts (each has a docstring)
├─ HeatPump/                 # heat pump tool: pipeline, data, methodology
├─ Geothermal/               # geothermal map: scripts, data, output site
├─ GridCapacity/             # Hydro Ottawa feeder capacity fetch
├─ FSA_Maps/                 # simplified FSA boundary GeoJSONs per province
├─ Census/                   # StatCan 2021 census profile source (gitignored)
├─ retrofits/                # Retrofit Costs inputs: REMDB workbooks (USCosts/),
│                            #   per-province intermediates, review pages
│
│  # generated data — published on the gh-pages branch, gitignored on main
│  # (present on your disk after running the pipelines; fetched same-origin):
├─ province_json/  fsa_json/         # Retrofit Explorer
├─ retrofit_costs_json/              # Retrofit Costs POC (joined client-side by HOUSEID)
├─ insights_json/                    # Retrofit Insights (national)
├─ climate_json/                     # per-FSA HDD/CDD (ECCC normals, static)
├─ newhomes_json/  newhomes_fsa/     # New Homes Explorer
├─ ceud_json/                        # CEUD Explorer
├─ construction_json/                # Construction Tracker (auto-refresh monthly)
├─ grid_json/                        # grid dashboard data (auto-refresh weekly)
├─ prices_json/                      # energy prices (auto-refresh monthly)
├─ census_json/  geo_json/  lookup/  # shared lookups (census, geometry, AHRI, windows)
└─ utility_rates_reference.json      # bill-card rates (fetched by retrofits.html)
```

## 🌿 Branches — code on `main`, data on `gh-pages`

| Branch | Holds | History |
|---|---|---|
| `main` | pages, `assets/`, `Python/`, per-tool pipelines, docs, trackers | full — the decision record |
| `gh-pages` | the published site: pages + every generated data tree | **one commit, force-pushed each deploy** |

GitHub Pages publishes `gh-pages`, so the data sits next to the pages and every
`BASE_URL` is simply `'./'`. Generated trees are gitignored on `main`: they live
on local disk and are rebuilt by re-running the pipelines. Data versions are
deliberately not kept — the *process* is what has to be defensible, and the
process is versioned on `main`.

Publish with `./deploy.sh` (rebuilds `gh-pages` from the working tree as a
single commit). `.nojekyll` is required — the data trees contain `_index.json`
files and Jekyll drops underscore-prefixed paths.

## ⚙️ Automated refreshes (GitHub Actions)

| Workflow | Cadence | Data |
|---|---|---|
| `grid-refresh.yml` | weekly (Mon 13:00 UTC) | `grid_json/` |
| `ahri-refresh.yml` | weekly (Mon 15:00 UTC) | `lookup/ahri_numbers.json` |
| `construction-refresh.yml` | monthly (20th 14:00 UTC) | `construction_json/` |
| `rates-refresh.yml` | monthly (3rd) | `prices_json/` |

Everything else (ERS retrofit/new-homes data, CEUD, census, geothermal) refreshes
manually — run orders are documented in each project's doc above.

## About the data

All sources are public/open data: NRCan (EnerGuide/ERS audits, CEUD), Statistics
Canada (census, permits, starts, investment), CMHC, IESO/AESO, ECCC, OEB/Hydro
Ottawa, Ontario GSC water-well records, NEEP, and provincial utility tariffs.
Figures derived from EnerGuide audits are **modelled** estimates, not metered
bills — each page carries its own methodology section and caveats.
