# Retrofit Explorer

An interactive tool for exploring real Canadian home-energy retrofits — built from
Natural Resources Canada's **EnerGuide / Energy Rating System (ERS)** open audit data
(audit years **2004–2025**).

Pick a province, then optionally drill into a postal-code area (FSA) to see how homes
*like yours* were upgraded and what energy savings actually resulted.

**Live:** https://ottawavisuals.github.io/Ottawa-Visuals/retrofits

---

## Table of contents
- [What it shows](#what-it-shows)
- [Repository layout](#repository-layout)
- [Data source](#data-source)
- [The data pipeline](#the-data-pipeline)
  - [Step 1 — `ers_web_pipeline.py`](#step-1--ers_web_pipelinepy-raw-csvs--per-province-parquet)
  - [Step 2 — `split_fsa_json.py`](#step-2--split_fsa_jsonpy-parquet--per-fsa-json)
  - [Step 3 — `precompute_province_stats.py`](#step-3--precompute_province_statspy-parquet--province-summaries)
- [Unit conversions](#unit-conversions)
- [How each measure is flagged](#how-each-measure-is-flagged)
- [Data file formats](#data-file-formats)
- [Front-end architecture](#front-end-architecture)
- [The bin-width contract](#the-bin-width-contract-important)
- [Regenerating the data](#regenerating-the-data)
- [Local development](#local-development)
- [Deployment](#deployment)
- [Data notes & caveats](#data-notes--caveats)
- [Changelog](#changelog)

---

## What it shows

For a selected province (or a single FSA within it):

- Headline stats: median energy saving, EUI saving, GHG saving, deep retrofits, heat pumps added, fuel switches, solar PV added.
- Distributions: year built, floor area, building type, storeys.
- Energy: EUI (pre vs post), GHG emissions, design heat loss (kW — peak heating
  demand, not annual energy), an energy-by-fuel comparison, and a fuel-flow Sankey.
- Envelope: insulation (roof / wall / foundation) and air-tightness, pre vs post, plus improvement-only histograms.
- A measures breakdown and retrofit-profile spider chart.
- A 1%-increment energy-saving distribution.
- **FSA view only:** a sortable, expandable table of individual audited homes.

---

## Repository layout

```
Energy/
├─ retrofits.html                  # the entire app (HTML + CSS + JS, single file)
├─ province_json/
│  ├─ AB.json                       # one precomputed summary per province
│  └─ … (BC, MB, NB, NF, NS, ON, PE, QC, SK)
└─ fsa_json/
   ├─ AB/
   │  ├─ _index.json                # list of FSAs in this province + row counts
   │  ├─ T0A.json                   # raw matched rows for one FSA
   │  └─ … (one file per FSA)
   └─ …
Python/
├─ ers_web_pipeline.py              # Step 1: raw ERS CSVs -> per-province parquet
├─ split_fsa_json.py                # Step 2: parquet -> per-FSA JSON
├─ precompute_province_stats.py     # Step 3: parquet -> province summaries
└─ aggregate_canada.py              # Step 4: province summaries -> CA.json rollup
```

The front-end fetches data from the `main` branch via `raw.githubusercontent.com`
(see `BASE_URL` near the top of the `<script>` block in `retrofits.html`).

---

## Data source

All figures originate from the **NRCan EnerGuide / ERS** dataset of home-energy audits,
modelled in NRCan's **HOT2000** software. Homes are de-duplicated and linked by a stable
address identifier (`HOUSEID`); area is identified by the first three characters of the
postal code (`CLIENTPCODE` → `FSA`). These are **modelled** estimates, not metered
utility consumption.

---

## The data pipeline

Three scripts run in order. Steps 2 and 3 both read the per-province parquet that Step 1
produces.

```
raw yearly ERS CSVs ──[1] ers_web_pipeline.py──▶ ers_web_<PROV>.parquet
                                                   ├─[2] split_fsa_json.py            ──▶ fsa_json/<PROV>/*.json
                                                   └─[3] precompute_province_stats.py ──▶ province_json/<PROV>.json
```

### Step 1 — `ers_web_pipeline.py` (raw CSVs → per-province parquet)

Turns the yearly ERS exports (`2004-2006.csv` … `2025.csv`) into one cleaned parquet per
province. What it does:

1. **Split each row by evaluation type.** Every audit record carries an `EVALTYPE`. The
   pipeline treats type **`D`** as the *initial* ("before") evaluation and **`E`** as the
   *follow-up* ("after") evaluation, streaming each into separate intermediates.
2. **Pair before/after by home.** It keeps only `HOUSEID`s that have **exactly one `D`
   and exactly one `E`**, then requires the **`E` audit to be dated after the `D` audit**.
   Each surviving pair becomes one `pre`/`post` row.
3. **Reject mismatched pairs** (guards against comparing two different homes): a pair is
   dropped unless floor area changed by **≤ 10%** *and* house type, storeys, and number of
   dwelling units are **identical** pre vs post.
4. **Map ~45 source columns** to friendly names and **convert units to kWh** (see
   [Unit conversions](#unit-conversions)).
5. **Compute per-home flags and derived columns** (see
   [How each measure is flagged](#how-each-measure-is-flagged)).
6. **Write** `ers_web_<PROV>.parquet` per province.

> **Legacy note:** Step 1 also contains optional machinery to dictionary-encode strings,
> emit a gzipped CSV, and write a shared `ers_web_keys.json`. The **current** web app does
> **not** use those — Step 2 ships already-decoded strings — so `ers_web_keys.json` is no
> longer fetched by `retrofits.html`. Treat that part of Step 1 as legacy/optional output.

### Step 2 — `split_fsa_json.py` (parquet → per-FSA JSON)

Splits a province parquet into one small JSON file per FSA — what the FSA-level view
fetches when you select an area.

- **Normalises categories.** `BldgType`, `Storeys`, fuel/heat-type columns, etc. are
  case-folded to a canonical form *before* grouping. Without this, casing variants from
  different audit years (`single detached` vs `Single Detached`) silently split one real
  category into two — this affected ~91% of AB rows before the fix.
- **Extracts audit years** (`Pre_Year` / `Post_Year`) from the entry dates; the full date
  string is dropped.
- **Trims to the columns the front-end actually reads** (`KEEP_COLS`). If you add a new
  chart/field reference in `retrofits.html`, add the matching column here or it ships empty.
- **Writes** `fsa_json/<PROV>/<FSA>.json` as a compact `{columns, rows}` array-of-arrays
  (≈77% smaller than array-of-objects), plus `fsa_json/<PROV>/_index.json`.

### Step 3 — `precompute_province_stats.py` (parquet → province summaries)

Reduces each province to a fixed summary so the province-wide view never has to scan raw
rows in the browser. For the whole province **and** for each house type it precomputes:
medians (saving %, EUI, GHG), counts (deep retrofits, heat pumps, fuel switches, solar),
and ready-to-plot histogram **bins** for every chart — plus the Sankey flows, the
energy-by-fuel "waterfall", insulation KPIs/histograms, and the measures breakdown.

**This script is a deliberate mirror of the JavaScript renderers** in `retrofits.html`:
the same filters, the same median definition, and — critically — the **same bin widths**.
If the two ever disagree, the province view and the FSA view will show differently-shaped
charts for the same data. See [the bin-width contract](#the-bin-width-contract-important).

---

## Unit conversions

Applied in Step 1 so every fuel is comparable in **kWh** (heat loss in **kW**):

| Quantity | Source unit | Factor | Result |
|---|---|---|---|
| Total energy | MJ | × 0.27778 | kWh |
| Heating energy | MJ | × 0.27778 | kWh |
| Electricity | kWh | — (as-is) | kWh |
| Natural gas | m³ | × 10.361194 | kWh |
| Oil | L | × 10.2 | kWh |
| Propane | L | × 7.092 | kWh |
| Wood | tonne | × 4166.7 | kWh |
| Design heat loss | W | × 0.001 | kW |
| GHG (`ERSGHG`) | tCO₂e/yr | — (as-is) | tCO₂e/yr |
| Solar PV (`KWPV`) | kW DC | — (as-is) | kW |

GHG already includes electricity emissions via each province's grid factor, so
fuel-switching to electricity is reflected correctly.

---

## How each measure is flagged

All thresholds are computed per home in Step 1:

| Field | Rule |
|---|---|
| `Roof_/Wall_/Foundation_/Floor_Insulation_Upgrade` | post insulation RSI **> 1.10 ×** pre (more than 10% higher) |
| `Air_Tightness_Upgrade` | post air leakage (ACH50) **< 0.90 ×** pre (more than 10% tighter) |
| `Windows_Change` | window code present in both audits and different |
| `Heating_Change` | heating **fuel** or **equipment type** differs |
| `Cooling_Change` | air-conditioner type differs |
| `HeatPump_Addition` | no heat pump pre, heat pump present post |
| `Shallow_Retrofit` | post total energy is **90–100%** of pre (0–10% saved) |
| `Medium_Retrofit` | post total energy is **50–90%** of pre (10–50% saved) |
| `Deep_Retrofit` | post total energy is **≤ 50%** of pre (≥ 50% saved) |
| `FuelSwitch` | primary heating fuel differs pre vs post |
| `EnergySavingPct` | `(pre − post) / pre`, where pre > 0. **Positive = energy saved.** |

---

## Data file formats

### `fsa_json/<PROV>/_index.json`

```json
[
  { "fsa": "T0A", "row_count": 375 },
  { "fsa": "T0B", "row_count": 520 }
]
```

### `fsa_json/<PROV>/<FSA>.json`

Array-of-arrays to keep files small. The browser reconstructs row objects by zipping
`columns` with each `rows` entry.

```json
{
  "columns": ["FSA","BldgType","Storeys","YearBuilt","FloorArea",
              "Pre_TotalEnergy","Post_TotalEnergy","Pre_HeatFuel","Post_HeatFuel",
              "...","EnergySavingPct"],
  "rows": [
    ["T0A","Single Detached","One storey",1979,144.9,64859.1,59534.6,
     "Natural Gas","Natural Gas","...",0.0821]
  ]
}
```

Boolean-ish flag columns may arrive as `true`/`false` or `1`/`0`; the front-end's
`flag()` helper normalises both.

### `province_json/<PROV>.json`

```json
{
  "province": "AB",
  "total_rows": 70348,
  "by_type": {
    "All types":      { "row_count": 70348, "median_saving_pct": 0.128, "...": "…" },
    "Single Detached":{ "row_count": 63700, "...": "same shape, this house type" }
  }
}
```

Each `by_type` slice contains the medians, counts, and pre-binned histograms for every
chart (`eui_pre_bins`, `ghg_post_bins`, `sankey_flows`, `waterfall`, `insulation_kpis`,
`insulation_histograms`, `measures`, etc.). The house-type dropdown in province mode is
populated from these keys.

---

## Front-end architecture

`retrofits.html` is a single self-contained file (no build step). It pulls in Chart.js
from a CDN; everything else — CSS, the Sankey/spider SVG renderers, all chart logic — is
inline.

Two render modes share the same DOM:

| | **Province mode** | **FSA mode** |
|---|---|---|
| Trigger | a province selected, FSA = "All areas" | a specific FSA selected |
| Data | precomputed `province_json/<PROV>.json` | raw rows from `fsa_json/<PROV>/<FSA>.json` |
| Filters | house type only | house type, heating fuel, retrofit depth |
| Table | hidden (no row-level data) | shown (sortable, expandable) |
| Renderers | `renderProvince*()` (read bins) | `render*()` (bin rows live) |

A `LOAD_TOKEN` counter guards against a slow fetch from a previous selection landing after
a newer one — every load mints a fresh token and stale results are discarded. Fetched
payloads are cached so re-selecting a province or FSA is instant.

---

## The bin-width contract (important)

Province mode reads **precomputed** histogram bins; FSA mode bins **raw rows live**. They
must agree on bucket widths or the same data will look different across the two views.

The front-end widths live in one object near the top of the `<script>`:

```js
const BINS = { year:10, area:50, eui:20, ghg:1, heatloss:2, savingsPct:1 };
```

These must match `precompute_province_stats.py`:

| Chart | Width | JS (`BINS`) | Python (`bin_counts(..., step=)`) |
|---|---|---|---|
| Year built | 10 yr | `year` | `step=10` |
| Floor area | 50 m² | `area` | `step=50`, max 700 |
| EUI | 20 kWh/m² | `eui` | `step=20`, max 500 |
| GHG | 1 tCO₂e/yr | `ghg` | `step=1`, max 30 (pre/post **and** delta) |
| Design heat loss | 2 kW | `heatloss` | `step=2`, 0–150 (pre/post **and** delta) |
| Saving % | 1% | `savingsPct` | per-1% |
| EUI improvement | 10 kWh/m² | (renderer literal) | `step=10`, 0–500 |
| Roof / air insul. | 0.5 | (renderer arg) | `step=0.5` |
| Wall / foundation insul. | 0.25 | (renderer arg) | `step=0.25` |

**When you change any of these, change it in both places.** This is the single most likely
source of "the province chart and the FSA chart disagree" bugs.

---

## Regenerating the data

Edit the `OUTPUT_DIR` / `INPUT_DIR` paths at the top of each script, then run in order:

```bash
# 1) Raw ERS yearly CSVs -> one cleaned parquet per province
python scripts/ers_web_pipeline.py

# 2) Province parquet -> per-FSA JSON (+ _index.json)
python scripts/split_fsa_json.py

# 3) Province parquet -> province_json/<PROV>.json summaries
python scripts/precompute_province_stats.py
```

Then commit the regenerated `Energy/fsa_json/` and `Energy/province_json/` to `main`.

- To process a single province while testing, set `PROVINCE_FILTER` in Step 1.
- If you add a chart/field to `retrofits.html`, update `KEEP_COLS` in Step 2 **and**, if it
  needs a precomputed bin, add it to Step 3 with a width that matches `BINS`.

**Dependencies:** `pandas`, `numpy`, `pyarrow` (Step 1 also uses `pyarrow.csv`).

---

## Local development

No build tooling required:

```bash
# Quickest: open it — it loads live data from raw.githubusercontent.com
open Energy/retrofits.html

# Or serve locally (avoids file:// quirks)
cd Energy && python -m http.server 8000
# visit http://localhost:8000/retrofits.html
```

When served from `localhost`/`127.0.0.1`, `BASE_URL` automatically switches to relative
paths, so the page reads the `fsa_json/`, `province_json/`, `geo_json/`, `census_json/`
and `lookup/` folders sitting next to it — local pipeline output is testable before
pushing. Any other host reads the published GitHub copy.

---

## Deployment

Served by **GitHub Pages** from this repo; `retrofits.html` lives under `Energy/` and is
reached at `…/Ottawa-Visuals/retrofits`. Data is loaded at runtime from `main` via
`raw.githubusercontent.com`, so **publishing new data is just a commit to `main`** — no
page redeploy needed.

---

## Data notes & caveats

- **Modelled, not metered.** All energy/GHG values come from HOT2000, not utility bills.
  Real consumption varies with weather and occupant behaviour.
- **Matched homes only.** A home needs exactly one before and one after audit (after dated
  later), and must pass the same-home checks (≤10% area change; unchanged type/storeys/units).
- **The sample is self-selected.** Requiring a matched before/after audit pair means the
  data is dominated by incentive-program participants who completed their retrofit and
  booked the follow-up audit. Savings shown likely run higher than for a randomly chosen
  renovation. (Also stated in the in-page methodology.)
- **Energy-by-fuel uses means/totals, not medians.** The FSA view sums raw rows; the
  province summaries ship per-home *means* per fuel (mean × row count = exact total).
  Means are additive across fuels and keep minority fuels (oil, wood, propane) visible —
  a median would zero out any fuel used by fewer than half the homes.
- **Outliers clipped** for readability (e.g. EUI > 500 kWh/m², GHG > 30 tCO₂e/yr,
  design heat loss > 150 kW).
- **Solar pre vs post.** `Pre_/Post_SolarPV` both read the audit's `KWPV` (kW DC). Pre-retrofit
  audits rarely record existing PV, so `solar_pre_pct` is typically ~0 and "solar added"
  reflects systems present at the follow-up audit — it may slightly overcount homes that
  already had panels. This is a source-data characteristic, not a pipeline error.
- **Saving-% sign is confirmed:** `EnergySavingPct = (pre − post)/pre`, so positive means
  energy was saved, negative means it rose (common with heat-pump fuel switching).
- **No cost data** in the source — no payback or dollar figures are possible.

---

## Changelog

### 2026-07 accuracy & UX pass
- **Heat loss relabelled to its true unit.** `Pre/Post_HeatLoss` is *design heat loss*
  in **kW** (EGHDESHTLOSS, W → kW) — peak heating demand, what equipment is sized to —
  not annual GJ. The chart, tooltips, per-home detail table, and methodology previously
  said "GJ/yr"; all now say kW and explain the sizing angle.
- **Heat-loss bin contract fixed.** JS `BINS.heatloss` was 2 while Step 3 used `step=5`,
  so the FSA and province views binned the same data differently. Both are now 2 kW.
- **Province waterfall now uses means, not medians.** Step 3 computed per-fuel *medians*,
  which zeroed out minority fuels (oil/wood/propane vanished from the chart) and didn't
  match the FSA view's raw totals. It now ships per-home means (mean × row count = exact
  total). ON, for example, now shows all five fuels.
- **Province view gained GHG and heat-loss improvement histograms** (`ghg_delta_bins`,
  `heatloss_delta_bins` in Step 3 + `aggregate_canada.py`), matching the FSA view's amber
  Improvement bars.
- **Broken `#province-sel` inline style fixed** — backslash-escaped quotes inside an HTML
  attribute truncated the style, spilled garbage attributes onto the element, and 404'd on
  a mangled URL. Styling moved into the stylesheet.
- **Postal-code quick find** — type a postal code, land directly on your FSA (first letter
  → province, first three characters → FSA; X tries NT then NU).
- **Shareable deep links** — `?prov=ON&fsa=K0A` in the URL, kept in sync via
  `replaceState`, validated against `_index.json` on load.
- **NT and Nunavut selectable** — their data always existed (and was counted in the Canada
  totals) but wasn't reachable from the dropdown. Map degrades gracefully (no boundary file).
- **Small-sample warning** — views with fewer than 30 matched homes get an explicit
  "medians are noisy" caution in the count bar.
- **Selection-bias disclosure** added to the in-page methodology and this README.
- **Faster loads** — province summary now fetched in parallel with the FSA index instead
  of after it; the FSA map paints without waiting for the ~1.2 MB census file (population
  is patched into tooltips when it arrives).
- **Local dev** — `BASE_URL` auto-switches to relative paths on `localhost`, so
  `python -m http.server` serves your local data instead of the published GitHub copy.
- Label consistency: "Heat pumps added" now reads "% of matched homes" like every other
  stat; hero copy says savings are estimates (modelled), not "actual".

### Front-end fixes
- **Removed dead code** — `KEYS_URL` / `CODED_COLS` and the old `ers_web_keys.json` decode
  step (the file is legacy and 404s; FSA JSON ships already-decoded).
- **Fixed a stale-fetch race** — FSA/reset handlers now mint a fresh `LOAD_TOKEN`.
- **Centralised bin widths** into a single `BINS` object (see the contract above).
- **Accessibility:** keyboard-operable + `aria-expanded` table rows; Sankey flows now work
  on touch and keyboard with screen-reader labels (were hover-only); spider chart given a
  role/label; visible keyboard-focus styles.
- **Colour-blind-safe palette** — pre/post bars are now navy (pre) / green (post) instead
  of red/green.
- **Province building-type donut** now reflects the selected house type.
- **Methodology** — added an in-page collapsible methodology section, expanded to document
  the matching rules, same-home checks, unit conversions, and upgrade thresholds.

### Documentation
- This README expanded to document all three pipeline scripts, unit conversions, flag
  rules, and the full bin-width contract. The two earlier "open items" (saving-% sign and
  solar) are resolved above using the script logic.

---

# Construction Tracker

`construction.html` — Canadian building permits, housing starts and construction
investment in one dashboard, at national, provincial and metro-area (CMA) level.
Full design/data plan: `CONSTRUCTION_PLAN.md`; build log: `CONSTRUCTION_STATUS.md`.

## What it shows

For Canada, any province, or eight major CMAs: headline KPIs (permit value, starts,
under-construction stock, investment, each with y/y change), the permits → starts →
under-construction → completions pipeline, starts by dwelling type and by intended
market (homeowner / condo / rental), residential vs non-residential permit values
(nominal or constant $), investment by work type (new / renovation / conversion),
per-capita provincial comparisons, and a sortable CMA table. Advanced mode adds the
rate cycle (starts vs BoC overnight + 5-yr mortgage), net new supply (units created
vs lost on permits), and construction employment vs backlog.

## Data pipeline

```
Python/construction_etl.py          # core: StatCan 34-10-0292 (permits),
                                    #   34-10-0293 (investment), 34-10-0151 +
                                    #   34-10-0154 (starts/UC/completions),
                                    #   34-10-0158 (SAAR), 34-10-0148 (market)
Python/construction_context_etl.py  # context: 18-10-0205 NHPI, 17-10-0009 pop,
                                    #   14-10-0355 construction employment,
                                    #   34-10-0145 5-yr mortgage, 18-10-0289 BCPI,
                                    #   Bank of Canada Valet (overnight rate)
        → construction_json/        # one compact JSON per geography + context.json
                                    #   + meta.json (key scheme, units, dates)
```

Conventions: dollar series stored in **millions**; unit counts as **integers**;
unadjusted variants shipped only where no seasonally adjusted sibling exists.
Permits & investment history begins 2017–2018 (StatCan's redesigned programs);
CMHC series run from 1990. **Known data gap:** CMHC discontinued province-level
under-construction and completions after 2022 in every table (verified against
34-10-0151/0136/0139/0126); those series end Dec 2022 for provinces/Canada and
the page annotates this. Metro areas (34-10-0154) carry all pipeline stages to
the current month.

## Regenerating / refresh

```bash
cd Python
python construction_etl.py            # cached downloads; --refresh to force
python construction_context_etl.py
```

`.github/workflows/construction-refresh.yml` does this monthly (20th, 14:00 UTC)
and commits `construction_json/` only when all fetches succeed and data changed.
