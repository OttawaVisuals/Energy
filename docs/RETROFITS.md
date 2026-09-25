# Retrofit Explorer

An interactive tool for exploring real Canadian home-energy retrofits — built from
Natural Resources Canada's **EnerGuide / Energy Rating System (ERS)** open audit data
(audit years **2004–2026**).

Pick a province, then optionally drill into a postal-code area (FSA) to see how homes
*like yours* were upgraded and what energy savings actually resulted.

**Live:** https://ottawavisuals.github.io/Energy/retrofits

Sibling tool: the **New Homes Explorer** ([NEWHOMES.md](NEWHOMES.md)) applies the
same architecture to the new-construction slice of the same data.

---

## Table of contents
- [What it shows](#what-it-shows)
- [Repository layout](#repository-layout)
- [Data source](#data-source)
- [The data pipeline](#the-data-pipeline)
  - [Step 1 — `ers_web_pipeline.py`](#step-1--ers_web_pipelinepy-raw-csvs--per-province-parquet)
  - [Step 1b — `join_hp_capacity.py`](#step-1b--join_hp_capacitypy-parquet--parquet-ahri-certificate-join)
  - [Step 1c — `compute_ghg_scenarios.py`](#step-1c--compute_ghg_scenariospy-parquet--parquet-ghg-scenario-columns)
  - [Step 2 — `split_fsa_json.py`](#step-2--split_fsa_jsonpy-parquet--per-fsa-json)
  - [Step 3 — `precompute_province_stats.py`](#step-3--precompute_province_statspy-parquet--province-summaries)
- [Unit conversions](#unit-conversions)
- [GHG scenarios](#ghg-scenarios)
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
├─ retrofits.html                  # the page markup
├─ assets/
│  ├─ retrofits.css                 # the page's styles (split out 2026-07-24)
│  └─ retrofits.js                  # every renderer — look here, not in the HTML
├─ province_json/
│  ├─ AB.json                       # one precomputed summary per province
│  ├─ CA.json                       # the national rollup (Step 4)
│  └─ … (BC, MB, NB, NF, NS, NT, NU, ON, PE, QC, SK)
├─ fsa_json/
│  ├─ AB/
│  │  ├─ _index.json                # FSAs in this province + row counts, median saving, dore_count
│  │  ├─ T0A.json                   # raw matched rows for one FSA
│  │  └─ … (one file per FSA)
│  └─ …
├─ retrofit_costs_json/             # the cost POC's companion tree, same per-FSA layout,
│  ├─ _canada.json                  # joined client-side to fsa_json by HOUSEID
│  ├─ _dictionary.json              # shared categorical dictionary for the coded columns
│  └─ <PROV>/<FSA>.json
├─ census_json/ geo_json/ climate_json/   # context layers (census panel, FSA map, HDD/CDD)
├─ retrofit_casestudies_json/       # one-off scrape of retrofitcanada.com/case-studies,
│  └─ _all.json                     # feeds retrofit-insights.html §10 — see below
└─ utility_rates_reference.json     # blended per-province rates for the bill card + payback
Python/
├─ ers_web_pipeline.py              # Step 1: raw ERS CSVs -> per-province parquet
├─ join_hp_capacity.py              # Step 1b: joins Post_HPAHRI against lookup/ahri_numbers.json
├─ ers_ghg_factors.py               # derives the ERS-calibrated GHG factor table (feeds Step 1c)
├─ ghg_factors.py                   # GHG factor constants/lookups (official ECCC/OBPS + ERS-calibrated)
├─ compute_ghg_scenarios.py         # Step 1c: adds the 6 GHG scenario columns
├─ split_fsa_json.py                # Step 2: parquet -> per-FSA JSON
├─ precompute_province_stats.py     # Step 3: parquet -> province summaries
├─ aggregate_canada.py              # Step 4: province summaries -> CA.json rollup
├─ build_fsa_audit_totals.py        # independent sidecar: the audited-population denominator
│                                   # (dore_count) that Step 2 writes into _index.json
├─ retrofit_cost_extract_fields.py  # cost POC: pulls the ERS fields BASE_MAPPING doesn't carry
├─ retrofit_cost_estimate.py        # cost POC: the REMDB pricing pass, per province
├─ build_retrofit_costs_json.py     # cost POC: splits the output into retrofit_costs_json/
└─ retrofit_casestudies_scrape.py   # one-off: scrapes Retrofit Canada's case-study library
                                    # -> retrofit_casestudies_json/_all.json (no ERS input at all)
lookup/
├─ ahri_numbers.json                # AHRI certificate data (brand/model/capacity/HSPF2/…),
│                                   # keyed by AHRI reference number (see build_ahri_lookup_full.py).
│                                   # Joined into the data trees at build time by Step 1b AND
│                                   # fetched at runtime by assets/retrofits.js for the
│                                   # equipment-detail cards.
├─ window_codes.json                # HOT2000 WINDOWCODE digit tables
└─ window_components.json           # per-digit component labels for the window-change card
```

Data ships on the `gh-pages` branch alongside the pages, so `BASE_URL` is `'./'`
(see the top of `assets/retrofits.js`) and every fetch is same-origin.

---

## Data source

All figures originate from the **NRCan EnerGuide / ERS** dataset of home-energy audits,
modelled in NRCan's **HOT2000** software. Homes are de-duplicated and linked by a stable
address identifier (`HOUSEID`); area is identified by the first three characters of the
postal code (`CLIENTPCODE` → `FSA`). These are **modelled** estimates, not metered
utility consumption.

The source extract carries 433 columns per audit record; the main pipeline reads 48 of
them (the cost POC reads a further handful straight from the raw CSVs — footprint,
window/door counts, ASHP configuration, pre-existing cooling — because Step 1's
`BASE_MAPPING` doesn't carry them). For
the full column-by-column picture — every ERS column with its fill rate and cardinality,
not just the ones this page uses — see [ERS_DATA_DICTIONARY.md](ERS_DATA_DICTIONARY.md).
`retrofits.html` itself has the used-column breakdown (source column, conversion factor,
what it feeds) in its own "Data availability" collapsible section.

---

## The data pipeline

Three scripts run in order, plus two optional sidecars (Step 1b, Step 1c) between
Step 1 and Steps 2/3 that enrich the same parquet in place. Steps 2 and 3 both read
the per-province parquet that Step 1 (and, if run, Step 1b/1c) produces.

```
raw yearly ERS CSVs ──[1] ers_web_pipeline.py──▶ ers_web_<PROV>.parquet
                                                   │
                                     [1b] join_hp_capacity.py (overwrites in place)
                                                   │
                                     [1c] compute_ghg_scenarios.py (overwrites in place)
                                                   │
                                                   ├─[2] split_fsa_json.py            ──▶ fsa_json/<PROV>/*.json
                                                   └─[3] precompute_province_stats.py ──▶ province_json/<PROV>.json
```

### Step 1 — `ers_web_pipeline.py` (raw CSVs → per-province parquet)

Turns the yearly ERS exports (`2004-2006.csv` … `2025.csv`) into one cleaned parquet per
province. What it does:

1. **Split each row by evaluation type.** Every audit record carries an `EVALTYPE`. The
   pipeline treats type **`D`** as the *initial* ("before") evaluation and **`E`** as the
   *follow-up* ("after") evaluation, streaming each into separate intermediates.
2. **Pair before/after by home.** It keeps every `HOUSEID` with **at least one `D` and at
   least one `E`**, reduces the home to its **oldest `D` and newest `E`**, then requires
   the **`E` audit to be dated no earlier than the `D` audit** (same month allowed since
   2026-09-23 — `ENTRYDATE` is month-precision). Each surviving pair becomes one
   `pre`/`post` row. (Changed 2026-07-24 — the rule was previously *exactly* one of each,
   which dropped every multi-audit home. See "Gate A — recovered" under
   [Data notes & caveats](#data-notes--caveats).)
3. **Reject mismatched pairs** (guards against comparing two different homes, or a
   change in the model rather than the house): a pair is dropped unless floor area changed
   by **≤ 5%** (was 10% until 2026-09-23), house type, storeys, and number of dwelling
   units are **identical** pre vs post, *and* both audits used the **same HOT2000 weather
   file** (`WTHDATA`, added 2026-09-23). The pipeline prints how many pairs each filter
   removed (`Same-home filter drops`).
4. **Map ~45 source columns** to friendly names and **convert units to kWh** (see
   [Unit conversions](#unit-conversions)).
5. **Compute per-home flags and derived columns** (see
   [How each measure is flagged](#how-each-measure-is-flagged)).
6. **Write** `ers_web_<PROV>.parquet` per province.

> **Legacy note:** Step 1 also contains optional machinery to dictionary-encode strings,
> emit a gzipped CSV, and write a shared `ers_web_keys.json`. The **current** web app does
> **not** use those — Step 2 ships already-decoded strings — so `ers_web_keys.json` is no
> longer fetched by `retrofits.html`. Treat that part of Step 1 as legacy/optional output.

### Step 1b — `join_hp_capacity.py` (parquet → parquet, AHRI certificate join)

Joins each province's parquet against `lookup/ahri_numbers.json` (see
[`build_ahri_lookup_full.py`](../Python/build_ahri_lookup_full.py)) on `Post_HPAHRI`,
adding 7 new `Post_`-prefixed columns and **overwriting the parquet in place**:
`HPCapacity47`, `HPCapacity5` (kW), `HPHSPF2`, `HPCertCOP5`, `HPColdClimate`,
`HPBrand`, `HPModel`.

**Why a separate script, not part of Step 1's `BASE_MAPPING`:** Step 1 is the
expensive, rarely-rerun full-CSV streaming pass; this join is cheap and needs
re-running whenever the AHRI lookup grows, without re-ingesting any CSVs — the same
role `build_fsa_audit_totals.py` already plays as an independent sidecar feeding
Steps 2/3.

**Why join on the AHRI certificate, not the raw auditor-entered `HPCAP` field:**
validated against real AHRI certificates across 318,585 rows nationally,
`HPCAP` (Watts) runs a median **1.6×** the certified 47°F capacity, clusters
visibly near 1×/2×/4× of the true value (consistent with a unit-entry error),
and 63% of AHRI codes appearing more than once show inconsistent `HPCAP`
values across different audit rows for the same certified unit — unusable for
a sizing claim. The certificate's own `heating_capacity_47f_btuh`/
`heating_capacity_5f_btuh` fields are the trustworthy source; 5°F (≈ −15°C) is
used as a Canadian design-day proxy.

**What about the raw `COP` and `CCASHP*` fields?** Not joined here (this step only
adds capacity/HSPF/COP-at-5F from the certificate), but validated the same way:
the generic `COP` field looked unreliable at first — it runs systematically
higher than the certificate's 5°F COP — until a spot-check against NEEP's
published performance table for the site's most common installed unit (AHRI
211644151) showed why: NEEP lists that unit at COP 3.00 at the AHRI 47°F rated
point and 1.80 at 5°F, and the ERS `COP` field's median for that exact unit is
**2.99** — matching 47°F, not 5°F. So `COP` isn't unreliable, it's rated at a
different, warmer condition than the certificate field it was being compared
against. The AHRI Directory's search API only exposes a certified COP at 5°F
(confirmed by listing all 40 fields it returns for one certificate — no 47°F
COP field exists), so this can't be validated at 47°F across the full dataset
yet. The cold-climate-ASHP-specific fields, by contrast, already carry a
same-condition comparison: `CCASHPCOP` (present when `CCASHP` = "T") matches
the certificate's 5°F COP almost exactly — HOT2000 most likely populates it
from the AHRI number directly — and `CCASHPCAPACITYMAINTENANCE` (the
auditor-recorded 5F/47F capacity ratio, as a %) tracks the certified
equivalent closely: across 210,243 rows nationally, the median difference is
0.0 percentage points, and 85% of homes land within ±10pp. None of
`CCASHPCAP`/`CCASHPCAPACITYMAINTENANCE`/`CCASHPCOP` are currently used on the
page — noted here as the fields to prefer if that changes. Diagnostics:
[`diagnose_hpcap_vs_ahri.py`](../Python/diagnose_hpcap_vs_ahri.py),
[`diagnose_ccashp_vs_ahri.py`](../Python/diagnose_ccashp_vs_ahri.py).

**Post-only:** pre-existing heat pumps are rare (~1.6% of homes), and the sizing/
backup-pairing story this feeds is about the retrofit's end state.

**Coverage:** measured on Ontario's paired parquet, **75.9%** of homes with a heat
pump post-retrofit resolve to a usable certificate (a further ~8% resolve to a
"Delisted" status-only entry with no specs). Coverage is highest for retrofits from
about 2019 onward — the AHRI reference number is much less consistently recorded by
auditors in earlier years.

### Step 1c — `compute_ghg_scenarios.py` (parquet → parquet, GHG columns)

Adds 2 columns, `Pre_/Post_GHG_current`: each home's own fuel consumption × current (2026)
official ECCC/OBPS factors — see [GHG](#ghg-scenarios) below. Needs only
`Python/ghg_factors.py`. (Until 2026-09-23 it wrote 6 scenario columns and depended on
`Python/ers_ghg_factors.py`'s output; that script is no longer part of the chain.)

### GHG scenarios

**Current method (since 2026-09-23): one basis.** Every matched home's GHG, before and
after, is its own fuel consumption (kWh, ~100% complete) × the **current (2026) official
ECCC/OBPS factor** for each fuel: the province's grid factor for electricity, fixed
combustion constants for gas / oil / propane, 0 for wood (biogenic-neutral; ECCC has no
residential wood factor). The same factors apply to every audit year, so retrofits from
different years compare on equal footing; the figure is what each retrofit's energy
change is worth in emissions today, not what it emitted at the time. Columns:
`Pre_/Post_GHG_current` (Step 1c). Both pages show this basis only — no dropdown.

**Why (decision 2026-09-23).** The EnerGuide data team advised using current emission
factors and ignoring the audit's own GHG reporting: `ERSGHG` was populated for only
50.5% of matched pairs, and the factors behind it were updated sporadically, so audits
from different years embed different, sometimes outdated, factors. This also retires the
open question of which factors HOT2000 uses ([ENERGUIDE_QUESTIONS.md §5.4](ENERGUIDE_QUESTIONS.md)).
The raw `ERSGHG` field is no longer pulled by Step 1.

Current electricity factors, g CO2e/kWh (2026, `ghg_factors.OBPS_ELECTRICITY`):
AB 438 · BC 18 · MB 2.5 · NB 234 · NL 17 · NS 581 · NT 420 · NU 800 · ON 59 · PE 234 ·
QC 1.9 · SK 631 · YT 74. Combustion: natural gas 185–189 (varies slightly by province),
oil 255.4, propane 213.6, wood 0.

Effect on the national headline (2026-09-24 build): typical home **6.9 → 5.0 tCO2e/yr**
(exact medians before/after; the Canada view shows 6.0 → 5.0 because `aggregate_canada.py`
reports medians at the lower edge of 1-tonne bins — see Data notes), against 4.0 → 2.0 on
the old raw-`ERSGHG` basis — the new figure covers every matched home instead of half, at
2026 factors. Retrofit Insights: **2,933,816
tCO2e/yr net saved across all 1,517,936 matched pairs**; 63,172 homes (4.1%) show a
modelled GHG rise.

#### History: the four GHG bases (2026-08-02 → 2026-09-23, retired)

From 2026-08-02 both pages offered a **GHG basis** dropdown with four bases, kept here as
the decision record:

| Scenario | Electricity factor | Combustion factor |
|---|---|---|
| `reported` | — (raw `ERSGHG`, ~50.5% coverage) | — |
| `current` (the one kept) | flat 2026 official ECCC/OBPS, same for every audit year | fixed official ECCC/OBPS constants |
| `current_corrected` | same, Alberta/Newfoundland use ERS-calibrated instead | fixed official ECCC/OBPS constants |
| `as_audited` (was the default) | ERS-calibrated, matched to each home's own audit year | ERS-calibrated, year-varying |

ERS-implied vs ECCC electricity factors, g CO2e/kWh, as shown on the page until
2026-09-23 ("—" = fewer than 30 audits that province/year):

| Province | ERS 2016 | ERS 2020 | ERS 2023 | ERS 2026 | ECCC 2026 | ERS-aligned |
|---|---|---|---|---|---|---|
| Alberta | 15.8 | 848.2 | 765.9 | 584.7 | 438.0 | **584.7** |
| British Columbia | 9.8 | 10.5 | 12.0 | 16.1 | 18.0 | 18.0 |
| Manitoba | 0.0 | 1.7 | 1.2 | 0.8 | 2.5 | 2.5 |
| N.W.T. | 0.9 | 240.4 | 207.7 | — | 420.0 | 420.0 |
| New Brunswick | 322.3 | 294.4 | 296.1 | 306.0 | 234.0 | 234.0 |
| Nfld. & Labrador | — | — | 33.1 | 23.1 | 17.0 | **23.1** |
| Nova Scotia | 75.5 | 739.1 | 731.4 | 718.0 | 581.0 | 581.0 |
| Nunavut | — | — | — | — | 800.0 | 800.0 |
| Ontario | 0.0 | 43.0 | 31.9 | 33.0 | 59.0 | 59.0 |
| P.E.I. | — | 292.7 | 292.7 | 306.0 | 234.0 | 234.0 |
| Quebec | 0.1 | 1.3 | 1.0 | 1.5 | 1.9 | 1.9 |
| Saskatchewan | 98.9 | 758.7 | 734.3 | 692.4 | 631.0 | 631.0 |
| Yukon | 0.4 | 51.8 | 64.2 | 91.8 | 74.0 | 74.0 |

Combustion, national: natural gas ERS 5.3 / 183.6 / 186.1 / 188.1 (2016/2020/2023/2026)
vs ECCC 185.4; oil 26.5 / 255.0 / 255.6 / 255.6 vs 255.4; propane 7.3 / 218.9 / 218.8 /
218.9 vs 213.6. The near-zero 2016 values are Ontario's `ERSNGASGHG` running near-zero
for 2006–2016 despite real gas use — one of the "sporadic factor updates" the EnerGuide
team referred to.

The reasoning behind the retired bases, as written at the time:

**Sources & derivation (retired bases)**: `Python/ers_ghg_factors.py` (ERS-calibrated factor
derivation — fixed 2026-08-02, see its module docstring for the survivorship-bias
bug this replaced: excluding true-zero-GHG rows from the ratio inflated the
factor and overstated the national total by +12.8% before the fix, +0.16%
after), `Python/ghg_factors.py` (constants + lookups, official ECCC/OBPS
figures cited inline), `Python/compute_ghg_scenarios.py` (writes the 6
scenario columns). Full year/province factor tables:
`Python/ers_ghg_factors_by_province_year.csv`.

---

## How each measure is flagged

All thresholds are computed per home in Step 1:

| Field | Rule |
|---|---|
| `Roof_/Wall_/Foundation_/Floor_Insulation_Upgrade` | post insulation RSI **> 1.10 ×** pre (more than 10% higher) |
| `Air_Tightness_Upgrade` | post air leakage (ACH50) **< 0.90 ×** pre (more than 10% tighter) |
| `Windows_Change` | `WINDOWCODE` present in both audits and different, after normalizing text format (`201030.0` = `201030`; before 2026-09-23 a raw string compare counted that as a change; national window changes fell 444,304 → 304,471 after the fix despite 5% more matched pairs, so the artifact was large, though not isolated exactly because the pair set changed in the same build). `WINDOWCODE` describes the windows with the greatest area, so this reads as a full or main-type replacement |
| `Windows_Partial` | added 2026-09-23: `WINDOWCODE` unchanged but `NUMWINESTAR` (installed ENERGY STAR windows) rose, both audits recorded. Mutually exclusive with `Windows_Change`. On 2020–2024 pairs: median 5 windows, ~32% of the house. Caveat: 98% of D audits record 0, so some E counts may include ENERGY STAR windows that pre-dated the D audit |
| `Heating_Change` | heating **fuel** or **equipment type** differs, raw ERS diff (row-level table, FSA mode). Aggregate charts (province mode, `retrofit-insights.html`) override this downstream to `Heating_Change & ~HeatPump_Addition` — see the note below the table. |
| `Cooling_Change` | air-conditioner type differs |
| `HeatPump_Addition` | no heat pump pre, heat pump present post |
| `Shallow_Retrofit` | post total energy is **90–100%** of pre (0–10% saved) |
| `Medium_Retrofit` | post total energy is **50–90%** of pre (10–50% saved) |
| `Deep_Retrofit` | post total energy is **≤ 50%** of pre (≥ 50% saved) |
| `FuelSwitch` | primary heating fuel differs pre vs post |
| `EnergySavingPct` | `(pre − post) / pre`, where pre > 0. **Positive = energy saved.** |

**"Heating system changed" excludes heat pump additions, in aggregate charts only.** `Heating_Change` is a raw `FURNACEFUEL`/`FURNACETYPE` diff, and adding a heat pump *is* a furnace type/fuel change — so without an exclusion, "Heating system changed" and "Heat pump added" double-counted the same homes, and a measure-mix bundle like "Heat pump + Heating system" read as little more than "heat pump, plus the paperwork that comes with it". `Python/precompute_province_stats.py` (province mode, both pages) and `Python/build_insights.py` (`retrofit-insights.html`) both override `Heating_Change = Heating_Change & ~HeatPump_Addition` immediately after loading each province parquet, before any measure-mix/bundle/share is computed. This is a downstream, display-only categorization choice, not a data correction — the raw `Heating_Change` column in the parquets (and in the per-home table shown in FSA mode, sourced from `fsa_json`) is untouched and can still be `true` alongside `HeatPump_Addition`. A home that replaced a gas furnace with a heat pump now counts only toward "Heat pump added" in every aggregate chart on both pages.

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
  "era_labels": {"ecoenergy": "ecoENERGY (2007–2012)", "none": "No program",
                 "greener": "Greener Homes (2021–2024)"},
  "by_type": {
    "All types":      { "row_count": 70348, "median_saving_pct": 0.128, "...": "…",
                         "by_era": { "ecoenergy": { "...": "same shape, this era" },
                                     "none": { "...": "…" }, "greener": { "...": "…" } } },
    "Single Detached":{ "row_count": 63700, "...": "same shape, this house type", "by_era": { "...": "…" } }
  }
}
```

Each `by_type` slice contains the medians, counts, and pre-binned histograms for every
chart (`eui_pre_bins`, `ghg_post_bins`, `sankey_flows`, `waterfall`, `insulation_kpis`,
`insulation_histograms`, `measures`, etc.). The house-type dropdown in province mode is
populated from these keys.

Each `by_type` slice also nests a **`by_era`** sub-object — the same shape again, one
level down, for each of the 3 program eras (`ecoenergy` / `none` / `greener`), so the
"Program era" filter can combine with the house-type filter in province/Canada mode.
Rows are classified by their **initial (D / Pre_Date) audit year**, not the follow-up
year — a home can start under a program and not complete its follow-up until after the
program closed (measured: ~46,000 Greener Homes starts finished in 2025-26, after the
grant closed to new applicants 2024-03-31). `CA.json` (`aggregate_canada.py`) carries
the same `by_era` under its one `"All types"` slice.
Boundaries are defined in three places that must stay in sync: `ERA_DEFS` in
`precompute_province_stats.py`, `ERA_DEFS`/`ERA_KEYS` in `aggregate_canada.py` and
`Python/build_insights.py`, and `ERA_DEFS` in `assets/retrofits.js`.

---

## Front-end architecture

`retrofits.html` is markup only (no build step). Chart.js comes from a CDN; the page's own
CSS and JavaScript live beside it in **`assets/retrofits.css`** and
**`assets/retrofits.js`** — split out of the HTML on 2026-07-24 because 200 KB of inline
script had to be re-downloaded and re-parsed on every single page view. The script is
loaded with `defer` at the end of `<body>`, exactly where it used to sit inline, so
execution order is unchanged. **Look for render functions in `assets/retrofits.js`, not in
the HTML.**

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

The front-end widths live in one object near the top of `assets/retrofits.js`:

```js
const BINS = { year:10, area:50, eui:20, ghg:1, heatloss:2, savingsPct:1, cost:250, hpSizing:0.1 };
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
| Heat pump sizing ratio | 0.1 | `hpSizing` | `step=0.1`, max 3.0 (47°F **and** 5°F) |
| EUI improvement | 10 kWh/m² | (renderer literal) | `step=10`, 0–500 |
| Roof / air insul. | 0.5 | (renderer arg) | `step=0.5` |
| Wall / foundation insul. | 0.25 | (renderer arg) | `step=0.25` |

The heat pump sizing ratio is a **fractional** step, unlike the other JS-side bins
(all integer widths). `bin_counts()` rounds fractional-step bin keys to 2 decimal
places (`round(float(b), 2)`) to avoid floating-point drift splitting one real bin
into two (`0.30000000000000004` vs `0.3`) — the JS side (`hpSizingBins()`) replicates
that exact rounding for the same reason.

**When you change any of these, change it in both places.** This is the single most likely
source of "the province chart and the FSA chart disagree" bugs.

---

## Regenerating the data

Edit the `OUTPUT_DIR` / `INPUT_DIR` paths at the top of each script, then run in order:

```bash
# 1) Raw ERS yearly CSVs -> one cleaned parquet per province
python scripts/ers_web_pipeline.py

# 1b) Join Post_HPAHRI against lookup/ahri_numbers.json -- overwrites the parquet in place.
#     Safe to skip if lookup/ahri_numbers.json hasn't changed since the last run (idempotent).
python scripts/join_hp_capacity.py

# 1c) Add Pre_/Post_GHG_current (current official factors) -- overwrites the parquet
#     in place; idempotent. REQUIRED: Step 3 fails without these columns.
python scripts/compute_ghg_scenarios.py

# 2) Province parquet -> per-FSA JSON (+ _index.json)
python scripts/split_fsa_json.py

# 3) Province parquet -> province_json/<PROV>.json summaries
python scripts/precompute_province_stats.py

# 4) Province summaries -> province_json/CA.json national rollup
python scripts/aggregate_canada.py

# 5) retrofit-insights.html's insights_json/ (reads the same parquets)
python scripts/build_insights.py
```

Then **publish** the regenerated `fsa_json/` and `province_json/` to `gh-pages` (see
[Deployment](#deployment)). They are gitignored on `main` — committing them there does
nothing.

- To process a single province while testing, set `PROVINCE_FILTER` in Step 1.
- If you add a chart/field to `retrofits.html`, update `KEEP_COLS` in Step 2 **and**, if it
  needs a precomputed bin, add it to Step 3 with a width that matches `BINS`.
- To refresh the AHRI certificate lookup itself (a separate, much longer-running step —
  hours, hits an undocumented external API at ~1.7s/number), see
  `Python/build_ahri_lookup_full.py`. Step 1b only needs re-running after that lookup
  changes; the CSV-ingest pipeline (Steps 1-3) doesn't depend on its refresh cadence.
- See [GHG scenarios](#ghg-scenarios) for what Step 1c computes and why; its official
  ECCC/OBPS constants (`Python/ghg_factors.py`) are a separate, manually-updated citation
  and don't need re-fetching on every pipeline run.

**Retrofit Insights** (`retrofit-insights.html`, ROADMAP item 13) reads the same
Step-1 parquets plus `build_fsa_audit_totals.py`'s audit sidecar, via a separate
script — `Python/build_insights.py` → `insights_json/`. It runs after Step 1
(parquets) and after `build_fsa_audit_totals.py`, but is **independent of**
Step 2 (`split_fsa_json.py`) — it does not read or write `fsa_json/`. Its other
two inputs, `census_json/fsa_census.json` (2021 Census) and
`climate_json/fsa_climate.json` (ECCC climate normals), are **static** and do
not need to be re-run as part of this refresh cadence.

> **`build_insights.py` does not write the whole of `insights_json/`.** Section 06B
> ("Cold-climate equipment") reads two more files —
> `insights_json/hp_ahri_scatter.json` and `insights_json/cchp_screen.json` — written
> by a **separate** script, `Python/build_hp_equipment_insights.py`, from the heat-pump
> tool's Phase-3c interim CSVs. It has no dependency on the ERS refresh, but it is easy
> to forget: if those two files are absent from the tree you deploy, section 06B goes
> dead on the live page with a "CCHP screen unavailable" note and nothing fails
> locally. (Exactly that happened between 2026-07-30 and 2026-08-03.) Run it whenever
> you rebuild `insights_json/`, and confirm both files are in the published tree.

**Retrofit Costs** (the proof-of-concept cost/payback layer inside `retrofits.html`)
is a third independent chain off the same Step-1 parquets:
`retrofit_cost_extract_fields.py` → `retrofit_cost_estimate.py` →
`build_retrofit_costs_json.py` → `retrofit_costs_json/`. It is joined to `fsa_json`
client-side by `HOUSEID`, so it can be re-run and re-published on its own without
touching Steps 2/3. Full method: [docs/RETROFIT_COSTS.md](RETROFIT_COSTS.md).

**Case studies** (`retrofit-insights.html` §10, "One house at a time") has no ERS
input at all: `Python/retrofit_casestudies_scrape.py` scrapes Retrofit Canada's
case-study library (retrofitcanada.com/case-studies, shared under their site's
open-content terms — see the module docstring) directly into
`retrofit_casestudies_json/_all.json`, fetched client-side like everything else on
the page but outside the `insights_json/` rollup pattern. It's a manual one-off,
not part of the refresh cadence above — there's no bulk API, and the library only
grows via their submission form, so re-run it by hand when you want a refresh.
Non-residential (commercial/institutional feasibility studies) and non-Canadian
cases are filtered out and recorded, with reason, in the JSON's `excluded` array
rather than silently dropped. Needs `beautifulsoup4` in addition to the
dependencies below.

**Dependencies:** `pandas`, `numpy`, `pyarrow` (Step 1 also uses `pyarrow.csv`).

---

## Local development

No build tooling required:

```bash
# Serve the repo root — every fetch is same-origin and relative
python -m http.server 8123
# visit http://localhost:8123/retrofits.html
```

`BASE_URL` is `'./'` unconditionally, so the page reads whatever data trees sit
beside it — `fsa_json/`, `province_json/`, `retrofit_costs_json/`, `geo_json/`,
`census_json/`, `lookup/` and `utility_rates_reference.json`. Locally that means
your own pipeline output; on `gh-pages` it means the published copy. Opening the
file over `file://` will not work: the fetches are blocked by CORS. There is a
ready-made static-server entry in `.claude/launch.json` on port 8123.

---

## Deployment

Served by **GitHub Pages** from the `gh-pages` branch at
<https://ottawavisuals.github.io/Energy/retrofits>. Code, pipelines and docs live on
`main`; `gh-pages` holds the pages *plus every generated data tree*, rebuilt as a
single force-pushed commit by `./deploy.sh`. **Committing data to `main` publishes
nothing** — the generated trees are gitignored there by design.

So a data refresh means: re-run the pipeline, then publish. Either `./deploy.sh`
(needs every tree in its `PATHS` list present on local disk — including
`retrofit_costs_json` and a complete `lookup/`), or, when only a few paths changed
and the rest of the trees aren't in your checkout, the incremental
build-on-top-of-`origin/gh-pages` pattern documented in
[CLAUDE.md](../CLAUDE.md). `.nojekyll` is mandatory — the trees contain
`_index.json` and Jekyll drops underscore paths.

---

## Data notes & caveats

- **Modelled, not metered.** All energy/GHG values come from HOT2000, not utility bills.
  Real consumption varies with weather and occupant behaviour.
- **Matched homes only.** A home needs at least one before (D) and one after (E) audit —
  reduced to its **oldest D and newest E** — with the E not dated earlier, and must pass
  the same-home checks (≤5% area change; unchanged type/storeys/units; same weather file). A home audited more
  than once therefore contributes a single row spanning its whole audit history, which
  may cover more than one retrofit project.
- **Pairing gates A and B — measured 2026-07-24** (`diagnose_gates_ab.py`, full scan of
  all 21 source CSVs; 2,154,236 homes, 1,630,171 with at least one D and one E).

  **Gate A — recovered 2026-07-24.** The pipeline now reduces each home to oldest D +
  newest E; the matched sample went **1,369,305 → 1,451,433 (+82,128, +6.0%)** and the
  matched share of homes having both a D and an E audit went 84.0% → 89.1%. The pair
  stage gained the full predicted +148,155; the structural and floor-area gates then
  removed proportionally more of the recovered homes, which is expected — a home with
  several audits spans a longer period and is likelier to have changed structurally.
  Headline figures barely moved (median saving 20% before and after; whole-home heat
  loss −12%), which is the check that the recovered homes are representative. Original
  measurement follows.

  **Gate A — "exactly one D and one E" dropped 149,145 homes.** Multiplicity is mostly
  small and symmetric: D=2/E=2 is 54%, D=2/E=1 is 28%, and 96% of cases sit at ≤3 of
  each. Reducing each home to **oldest D + newest E** would give a valid,
  correctly-ordered pair for **148,511 of them (99.6%)**; only 634 fail on date order
  or unparseable dates. This is a real ~10% recovery of the matched sample and the
  reduction rule matches what the page already claims to measure (earliest before vs
  latest after). The caveat is interpretive, not technical: a D=2/E=2 home may be two
  separate retrofit projects, and collapsing it reports the combined change as one.

  **Gate B — RESOLVED 2026-09-23: same-month pairs now kept.** The EnerGuide data team
  confirmed same-month D and E audits are usable. The rule is now `E >= D`: 84,754
  same-month pairs are kept and only 482 genuine E-before-D reversals drop. The
  paragraph below, written 2026-07-24, argued the opposite and is kept as the record;
  its "no recoverable ordering" reasoning was wrong, since `EVALTYPE`, not the date,
  says which audit came first.

  *Original (superseded):* **Gate B — "E dated after D" drops 84,755 pairs, and should stay dropped.** The
  earlier assumption that these were parsing failures is wrong: **zero** are
  unparseable. 99.4% (84,253) have E on the *exact same calendar day* as D, and every
  frequent case is a first-of-month placeholder (`2011-03-01 → 2011-03-01` alone is
  6,219 homes, a batch-load artifact). Only 502 have E genuinely before D. Because the
  day component is a placeholder, these pairs carry **no recoverable ordering** — the
  source cannot tell us which audit is the "before". Admitting them would mean assuming
  a direction on a page whose entire premise is before-vs-after, so the honest handling
  is to keep excluding them and document the reason here.

  **Current gate breakdown (2026-09-24 build, pipeline's own counts).** 1,517,936
  matched rows, one per address (0 duplicate `HOUSEID`s since the 2026-09-24 fix).
  Removed, in pipeline order: date order 482 ·
  floor area >5% 63,236 (of which ~18,700 moved 5–10%, removed only because of the
  2026-09-23 tightening) · type / storeys / units 60,268 · weather file 5,338.

  **Independent recount (2026-09-25, `diagnose_pairing_drops.py`, updated with the
  ID normalization and weather gate).** 1,647,596 homes carry both a D and an E;
  1,517,574 (92.1%) survive, 362 (0.02%) below the pipeline — the recount keys
  `HOUSEID` nationally, the pipeline per province (see the cross-province quirk).
  First-failing gate: date order 486 · floor area >5% 63,896 (19,143 in the 5–10%
  band) · type / storeys / units 60,281 · weather file 5,359. Against the
  2026-08-06 run (1,629,313 → 1,451,433, 89.1%): +18,283 candidates from the ID fix,
  ~84,300 fewer date drops from keeping same-month audits, ~29,000 more floor-area
  drops from the 5% rule, structural about flat. Within the structural gate,
  `NUMDWELLINGUNITS` still dominates (57,817): 79.7% are recorded in one audit and
  blank in the other (top cases blank → `0.0` 15,912, blank → `1.0`/`1` 25,866),
  20.3% genuinely different counts. Open question whether the one-side-blank cases
  should count as unchanged.

  **Weather file (`WTHDATA`) — gate added 2026-09-23.** Three files cover almost every
  audit (`WTH100` 56%, `Wth2020` 35%, `Wth110` 9%). 5,258 matched pairs (0.35%) changed
  file between D and E, 5,141 of them `Wth110` → `Wth2020`. Those pairs showed a 31%
  median saving against 20%; most of the gap is the longer audit gap (~3.5 years vs 0.4),
  but at matched gap and years the pairs that kept `Wth110` still saved 28.5% vs 33.4%
  (n=62, weak). Excluded rather than flagged so no saving on the page can come from a
  model change. The HOT2000 v10 → v11 upgrade (`PROGRAMNAME`) was checked at the same
  time: only 97 matched pairs span it, all of them also weather-file changes, so this
  gate covers both. Diagnostic: scratch script, not committed; figures reproducible from
  `PROGRAMNAME`/`WTHDATA` on oldest-D/newest-E pairs.

  *Earlier (2026-08-06):* **Full gate breakdown of the current drop (`diagnose_pairing_drops.py`, updated
  to match the pipeline post-2026-07-24/-18 fixes).** Of 1,629,313 homes nationally
  carrying both a D and an E, 1,451,433 (89.1%) survive; the remaining ~177,880 split
  roughly two-fifths Gate B (date order — see above), one-fifth Gate C (floor area
  changed >10%), and just over one-third Gate D (structural mismatch), within which a
  `NUMDWELLINGUNITS` difference is still the largest single reason but is now split
  roughly 4-to-1 between "recorded in one audit, blank in the other" (a real change,
  by the both-missing-is-unchanged rule above) and a genuine change in unit count —
  not the formatting/both-blank artifact the earlier fix already absorbed. This is a
  reconstruction run outside the pipeline over the full raw dataset, so shares are
  approximate (same-day date ties can be attributed slightly differently gate-to-gate
  than in the streaming pipeline); it is not itself part of the production pipeline.
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
- **No cost data in the source.** ERS has no cost fields at all, so every dollar
  figure on the page comes from outside it and is labelled as such: the "Energy
  bill" card prices modelled consumption at current provincial rates
  (`utility_rates_reference.json`), and the proof-of-concept retrofit cost and
  payback estimate prices recorded measures against PNNL/DOE's REMDB. Neither is a
  utility bill or a contractor quote — see
  [docs/RETROFIT_COSTS.md](RETROFIT_COSTS.md).
- **`Post_HeatFuel`/`Post_HeatType` is the backup, not the heat pump, for heat-pump
  homes.** HOT2000 models the heat pump as a component separate from the "primary
  heating equipment" these columns actually describe. `retrofits.html` relabels them
  "Backup fuel"/"Backup type" wherever `Post_HPType` indicates a heat pump is present
  (the individual-home detail table, and the "Heat pump + backup" equipment-detail
  card) — but the raw column names in `fsa_json`/parquet are unchanged.
- **Heat pump sizing coverage tops out around 76% of heat-pump homes** (Step 1b), and
  is skewed toward retrofits from ~2019 onward — see that step's description. This is
  a real data-availability gap (older audits less consistently record an AHRI
  reference number), not a pipeline bug; the sizing chart's home count will be
  noticeably smaller than the "Heat pumps added" KPI's.
- **The raw auditor-entered `HPCAP` field is unreliable for sizing claims** — validated
  against real AHRI certificates, it runs a median 1.6× the certified value, and the
  same AHRI number produces inconsistent values across different audit rows. Not used
  anywhere on the page; Step 1b's certificate join is the trustworthy source instead.
  The generic `COP` field looks unreliable the same way at first, but a NEEP
  cross-check shows it's actually rated at 47°F rather than the certificate's 5°F —
  see Step 1b above. `CCASHPCOP`/`CCASHPCAPACITYMAINTENANCE` (cold-climate-ASHP-only
  fields) track the certificate closely and are not currently used on the page.

---

## Changelog

### 2026-09-24 Duplicate HOUSEID rows fixed — exact-record selection by EVALUATIONSID

**Symptom.** 20,460 extra rows across 14,486 addresses (up to 9 rows for one
address); the July build had 20,736, so it predates the 2026-09-23 changes.

**Cause.** `process_pairs()` pulled each pair's D and E back out of their year files
by `HOUSEID` only. `HOUSEID` is an **address** key (NRCan dictionary: "all
evaluations with the same address information … will have the same HouseID"), so any
other evaluation at the same address in the same year file came along too, and the
`HOUSEID` join emitted every D × E combination. Some of those rows paired a D that was
not the oldest or an E that was not the newest; within one address the copies'
savings differed by more than 5 points for 5,658 addresses. The raw data holds no
exact duplicate records — all 40,235 same-address, same-type, same-file groups are
distinct evaluations.

**Fix.** `build_pairs_index()` now records the `EVALUATIONSID` of the chosen oldest D
and newest E (unique per D record and per E record), and `process_pairs()` selects
by those IDs. Month ties (two evaluations at one address in its oldest or newest
month, ~11,600 addresses on the D side) break on `EVALUATIONSID` for a deterministic
choice. The pipeline now prints `duplicate HOUSEID rows: N (expected 0)`.

**Pairing rule unchanged, by decision.** `EVALUATIONSID` is also NRCan's own D↔E
pair key (1,769,466 IDs hold exactly one D and one E). Pairing by it would give one
row per retrofit project rather than per address; Simon chose to keep oldest D +
newest E per address, which captures a home's whole history across programs —
`EVALUATIONSID` alone doesn't. For the record: 130,414 of the 1,630,171 address
pairs (8%) join a D and E from different evaluations, which is what the
oldest/newest rule means for re-audited homes; 22,424 evaluation pairs have a
different `HOUSEID` on D and E (address record changed) and are not linked by the
address rule.

**Effect of the selection fix alone.** 1,523,774 → 1,502,376 rows, 0 duplicates.

**Second bug, same day: `HOUSEID` text format.** Every yearly CSV up to `2025.csv`
writes IDs float-style (`5063805.0`); `2026.csv` (July 2026 refresh) writes
`5063805`. Compared as text, 23,402 addresses split in two — a D in 2025.csv and an
E in 2026.csv never paired, and a split address could appear twice in one FSA file
(1,085 such repeats, where `split_fsa_json.py` writes IDs as numbers). Fixed by
`normalize_ids()` in `ers_web_pipeline.py` (strips a trailing `.0` from `HOUSEID`
and `EVALUATIONSID` as each CSV batch is read) and the same normalization in
`build_fsa_audit_totals.py`. Homes with both a D and an E: 1,629,313 → **1,646,734**;
E-only addresses 22,681 → 2,605 (most were the 2026 half of a split address).
Because the parquets now carry normalized IDs, the three scripts that join them to
raw-CSV IDs normalize too, including any cached lookups:
`HeatPump/pipeline/build_city_design_temps.py`, `build_city_house_profiles.py`,
`Python/retrofit_cost_extract_fields.py` — without that they would silently match
~nothing on their next run.

**Known source quirk, not fixed:** 1,187 raw `HOUSEID`s (mostly 2022+, many ending
`…746`) are reused for different addresses in different provinces. Pairing runs
per province, so every pair is internally consistent (its D and E share an
`EVALUATIONSID`); the effective unique key is (province, `HOUSEID`), which is what
the pipeline's duplicate check tests. Side effects are small: the national audit
funnel counts each such ID once (~0.05%), and the heat-pump city lookup
(first-hit-wins by `HOUSEID`) may take the wrong province's station for ~500 homes.

**Final effect (2026-09-24 build).** **1,517,936** matched rows, 0 duplicates per
province. Median saving 19.8% (20% as displayed). Retrofit Insights GHG: 2,933,816
tCO2e/yr net saved.

### 2026-09-23/24 EnerGuide data-team answers applied — pairing, windows, GHG

Answers from a meeting with the team responsible for the EnerGuide data, applied in
one pass. Matched pairs **1,451,433 → 1,523,774** (+72,341, +5.0%; 1,517,936 after the
next day's duplicate and ID-format fixes); median saving
unchanged at 20%.

- **Same-month D/E kept** (`E > D` → `E >= D` in `build_pairs_index`): +84,754 pairs.
  The team confirmed same-month audits are usable. Closes Gate B.
- **Floor-area gate 10% → 5%**: −18,719 pairs whose area moved 5–10% (diagnostic).
- **Weather-file gate added** (`WTHDATA` must match D vs E): −5,338 pairs. Covers the
  97 pairs spanning HOT2000 v10 → v11. See Data notes.
- **`Windows_Change` `.0` fix**: codes normalized before comparing. National window
  changes 444,304 → 304,471 despite 5% more pairs, so a large share of the old count was formatting artifacts (not isolated exactly: the pair set changed in the same build; PEI measured 22% on 2026-07-31).
  The same fix was applied POC-side on 2026-07-31 only; now at the source.
- **New `Windows_Partial` flag** from `NUMWINESTAR` (team suggestion): 181,584 homes,
  shown as "Some windows replaced". Kept separate so window costs and "Windows changed"
  stay tied to the code. Window heat loss (`EGHHLWINDOOR`) was offered as another
  signal but not used: it also moves with weather-file / version changes.
- **GHG: one basis, current official factors.** Dropdown removed from both pages;
  `ERSGHG` and the two ERS-calibrated scenarios retired (team advice: partial
  reporting, sporadic factor updates). History and the factor tables kept under
  [GHG scenarios](#ghg-scenarios).
- **Wood (team answer 6), no change needed:** the team noted softwood/hardwood
  differences and suggested using heating consumption for all-wood homes. `wood_kwh()`
  already prefers `EGHFCONWOODGJ`, then `EGHHEATFCONSW` (heating consumption); the
  species-sensitive tonnes × 14 GJ/t fallback applies to ~0.3% of records.
- `diagnose_pairing_drops.py` mirrors the new date and floor-area rules and reports the
  5–10% band separately; the pipeline now prints per-gate drop counts and window-flag
  overlap. Chain order corrected here: Steps 1b and 1c are **required** (Step 3
  crashes without the GHG columns), and `aggregate_canada.py` / `build_insights.py`
  are listed.
- **Open, not introduced here:** cost-model figures on the page (1,420,044 of
  1,451,433) are from the last `retrofit_cost_estimate.py` run and were not regenerated.
  (The duplicate-`HOUSEID` rows found in this pass were fixed the next day — see
  2026-09-24 below.)

### 2026-09-23 Mobile-friendly filter bar (collapsing summary, theme toggle in header)

**Why.** The sticky filter bar never shrank on phones. Measured on a 375×812
viewport, scrolled down with an FSA selected, it stayed **372px tall in Simple
and 488px in Advanced**. Together with the 48px header, that covered 52% / 66% of
the screen over every chart. The Heat Pump Explorer's equivalent bar collapses to
46px. The old compact state only hid the field labels, and only at ≥900px.

- **Collapsing summary bar, all widths.** Past 72px of scroll, the whole filter bar
  hides behind `.filter-compact-bar`. It shows a one-line summary
  (`K1A, Ontario · Double/Semi-Detached · 12 retrofits`) plus an explicit **Edit
  filters** button, ported from `heatpump.html`'s `.ctrl-compact-bar`.
  Expand/collapse happens only on click (`_filterUserExpanded`), never on hover.
  `updateFilterSummary()` reads the selects' own option text, so the summary can't
  drift from the full bar. Filters left at their "All …"/"Any …" default are left
  out. A `MutationObserver` on `#result-count` keeps it current, because every
  filter change ends in a new count. Collapsed height is now **53px** on a phone
  (was 372/488) and 53px on desktop (was 110).
- **The small-sample warning stays visible.** While collapsed, the 2–3 line
  `#small-n-warn` is swapped for an amber "small sample" tag in the summary line.
  The small-n label is never dropped.
- **Theme toggle moved into the header**, same spot as `heatpump.html`. This
  removes one row from the phone filter grid.
- **Phone grid:** Simple/Advanced and Reset now share one row, and the match count
  gets its own full-width row.
- **Home link on phones.** "⌂ All tools" (`.home-link`) now stays visible at ≤600px,
  where the other sibling links hide. The `retrofitCanada` logo is also a link to
  `index.html`.

### 2026-08-27 Case-study section rework — filter, project table, R-value slopegraph

- **Building-type multi-select filter** (`#cs-type-filter`, pills built from the
  data's own distinct `Building Type` values, all on by default) now drives
  every chart/table in §10 through a single `renderCsAll()` re-render, gated
  so a theme toggle re-renders in place without resetting the user's
  selection (`CS_INITED` guard around the one-time fetch/pill-build step).
- **Project summary table** replaces the old "all cases" table: Project,
  Location, Year Built, Retrofit Status, Building Type, Energy Saving,
  Retrofit Type, Performance Level — still sortable, still click-through to
  the source page.
- **New R-value slopegraph**: one small hand-built inline-SVG chart per
  envelope component (attic/roof, wall, foundation wall), each on its own
  R-value axis since the components don't share a scale (attic R-values run
  past R-80, foundation walls can sit under R-5). Pre-retrofit axis on the
  left, post-retrofit on the right; each project is one line, coloured by its
  overall annual energy saving % (same cream→amber ramp as the province bar
  charts/choropleth elsewhere on the page); a gradient legend gives the %
  range, with a separate grey marker for projects that don't report a saving
  figure. Colours are resolved from `readPalette()` and baked into the SVG
  string at render time — hand-built SVG can't reliably consume a CSS
  `var()` reference here (see the comment above `readPalette()`) — so this
  chart re-renders like every other chart on a theme change.
- **Envelope-values table** underneath: the slopegraph's data in table form
  (Project, Energy Saving, pre/post R-value per component), restricted to
  the ~34 of 41 cases reporting at least one envelope R-value.
- Both new tables and the slopegraph read from the same filtered case list as
  the existing range table, so narrowing the building-type filter (e.g. to
  just bungalows) updates all four consistently.

### 2026-08-25 Case-study ranges — a second, external dataset on Retrofit Insights

- **New §10 on `retrofit-insights.html`, "One house at a time"**: min–median–max
  ranges (envelope R-values, ACH50, EUI, GHG/energy savings) by performance-level
  bucket (Net Zero / Net-Zero Ready / Partial-Other / Unknown), plus a sortable
  table of every case linking out to its source, built from a new external
  dataset — Retrofit Canada's case-study library — scraped once by the new
  `Python/retrofit_casestudies_scrape.py` into `retrofit_casestudies_json/_all.json`.
  Deliberately kept separate from the ERS-derived numbers everywhere else on the
  page: different population (48 self-submitted showcase projects vs. 1.45M
  audits), different methodology, never averaged together. 7 non-residential
  (commercial/institutional feasibility studies) or non-Canadian cases are
  filtered out of the 48 and recorded with reason rather than silently dropped,
  leaving 41. Surfaced as an explicit caveat rather than silently absorbed: 11 of
  those 41 report savings above 100% (net-positive-energy homes under each
  project's own reporting basis, not a data error). See the new "Case studies"
  paragraph under [Regenerating the data](#regenerating-the-data) above.

### 2026-08-06 HPCAP/COP/CCASHP validation against AHRI+NEEP, full pairing-gate breakdown

- **Corrected the `1.55×` HPCAP finding and resolved the `COP` rating-condition
  question.** Re-measured `HPCAP` vs the AHRI certificate over 318,585 rows
  nationally (median 1.6×, 1×/2×/4× clustering, 63% of repeated AHRI codes
  inconsistent across rows — new diagnostic:
  [`diagnose_hpcap_vs_ahri.py`](../Python/diagnose_hpcap_vs_ahri.py)). The generic
  `COP` field looked similarly unreliable against the certificate's 5°F COP, until
  a NEEP performance-table cross-check for the site's most common installed unit
  (AHRI 211644151) showed the ERS `COP` median (2.99) matches NEEP's **47°F**-rated
  COP (3.00), not the 5°F one (1.80) — `COP` is rated at 47°F, not 5°F as assumed.
  Confirmed AHRI's own search API has no 47°F COP field to validate against directly
  (all 40 fields the detail endpoint returns were enumerated live). The
  cold-climate-ASHP-specific fields `CCASHPCOP` and `CCASHPCAPACITYMAINTENANCE`
  (new diagnostic: [`diagnose_ccashp_vs_ahri.py`](../Python/diagnose_ccashp_vs_ahri.py))
  track the certificate closely instead — `CCASHPCOP` matches the certified 5°F COP
  almost exactly (HOT2000 most likely populates it from the AHRI number directly),
  and `CCASHPCAPACITYMAINTENANCE` (5F/47F capacity ratio, %) has a median difference
  of 0.0pp from the certified equivalent across 210,243 rows, 85% within ±10pp.
  Updated Step 1b above, the two limitations bullets, and `retrofits.html`'s
  sizing-chart note and AHRI-enrichment methodology section to match; none of the
  three CCASHP fields are used on the page yet.
- **Full gate-by-gate breakdown of the pairing drop**, extending the existing
  Gate A/B measurement above to Gates C (floor area) and D (structural): of the
  ~177,880 D&E homes nationally that don't reach the matched sample, roughly
  two-fifths fail Gate B, one-fifth Gate C, and just over one-third Gate D — added
  to `retrofits.html` section A and the Gate A/B note above.
  [`diagnose_pairing_drops.py`](../Python/diagnose_pairing_drops.py) was itself
  stale (it still modelled the pre-2026-07-18/-24 gate logic) and has been updated
  to match the shipped pipeline before this measurement was taken.

### 2026-08-05 Energy impact card, cumulative-audits timeline line, scorecard fix, Heating_Change redefinition

- **New "energy impact" card** on Retrofit Insights (section 03, beside the existing GHG
  impact card): total kWh/GWh saved net across matched pairs, priced at today's
  per-province rates (reuses `precompute_province_stats.price_vec_for()`/
  `add_cost_columns()` verbatim — no separate pricing logic), and converted into a
  "homes powered for a year" equivalent using NRCan **CEUD**'s own residential
  "Total Energy Use" ÷ "Total Households" figures (`ceud_json/res_<region>.json`,
  already scraped by `Python/ceud_etl.py` — no live CEUD site dependency). New
  `Python/build_insights.py::build_energy_impact()` → `insights_json/energy_impact.json`.
  CEUD reports a **grand-total** record alongside per-end-use/fuel/building-type
  *breakdowns of that same total* — summing every record naively inflates the total
  ~6x; only the no-dimension record is the real total (caught before shipping).
  Equivalency grid also gets a GWh figure, an illustrative EV-km distance (19 kWh/100km,
  not a specific model), and icons ported from Ottawa Visuals' `ghg_calculator.html`
  (SVG paths, `currentColor` fill so they follow this page's theme toggle) for both the
  GHG and energy equivalency cards — plus a new hand-drawn plug icon (the source
  calculator has no EV/plug icon of its own) and house/bolt/money icons for the energy
  card, none of which existed there before.
- **Retrofit Insights timeline chart** gets a second, dashed line: cumulative share of
  housing stock ever audited (running total of initial-D audits since 2000 ÷ that
  year's CEUD household count), stopping at 2023 (CEUD's latest year) rather than
  extrapolating. New `cum_pct_of_stock` in `timeline.json`, sourced the same way as the
  energy card above.
- **Scorecard table fix**: a bar at its column's max value (100% width) used to run
  edge-to-edge with no gap, visually blending into the next column's value. Bars now
  cap at `max-width:calc(100% - 6px)` and every bar cell gets a fixed 2px white
  right-border, cutting a clean line through the fill regardless of theme.
- **`Heating_Change` redefined, in aggregate charts only, to exclude heat pump
  additions.** `Heating_Change` is a raw `FURNACEFUEL`/`FURNACETYPE` diff, and adding a
  heat pump *is* a furnace type/fuel change — so "Heating system changed" and "Heat
  pump added" were double-counting the same homes, and the "Heat pump + Heating
  system" bundle on Retrofit Insights' measure-bundles chart read as little more than
  "heat pump, plus the paperwork". `Python/build_insights.py` and
  `Python/precompute_province_stats.py` (i.e. every aggregate chart on **both** pages)
  now override `Heating_Change = Heating_Change & ~HeatPump_Addition` immediately after
  loading each province parquet. Downstream-only — no ERS pipeline rerun, no `fsa_json`
  regen; the raw per-home `Heating_Change` in FSA mode's live table is unchanged and can
  still be `true` alongside `HeatPump_Addition`. See the flag table above.
- **New "peak demand" card**, same section: design/peak heat-loss (HOT2000's
  `EGHDESHTLOSS`, already used as a peak-heating-demand proxy elsewhere) pre vs post,
  for matched pairs that were **electrically heated pre-retrofit** (`Pre_HeatFuel ==
  "Electricity"`) — 388,842 of 1.45M matched pairs (27%). National total: 732,283 kW
  decrease; 163,919 of those homes (42%) added a heat pump. New
  `Python/build_insights.py::build_peak_reduction()` → `insights_json/peak_reduction.json`,
  national + by-province. A dropdown prices the avoided kW against any of the 12
  resources in IESO's "2024 Annual Planning Outlook: Resource Costs and Trends" (March
  2024) Table 1 — capital $/kW and fixed O&M $/kW-yr, embedded as
  `IESO_RESOURCE_COSTS_2024`. Two caveats stated on-page: (1) this is a **thermal**
  design-load figure, not metered electrical demand — solid for homes still on
  electric-resistance heat (COP≈1), but understates the true electric-peak drop for
  the 42% that added a heat pump, since the field can't see the heat source's COP, only
  the building's own heat-loss change; (2) the IESO cost table is Ontario grid-planning
  data, applied here as an illustrative national benchmark for "what a kW of avoided
  peak is worth in new-generation terms," not a claim that any specific province would
  have built exactly that resource.

### 2026-08-04 Program-era filter (ecoENERGY / no program / Greener Homes)

- **New "Program era" dropdown**, same filter-bar row as house type, in all three
  modes: FSA (client-filtered on `Pre_Year`), province, and Canada (both reading a
  new `by_era` sub-slice nested under every `by_type` slice — see the
  `province_json/<PROV>.json` shape above). Classified by each pair's **initial (D)**
  audit year, not the follow-up year, because a home can start under a program and
  not finish its follow-up until after the program closed — measured against the
  real data: ~46,000 Greener Homes starts (about 10% of that era's starts) completed
  their follow-up in 2025-26, after the grant closed to new applicants 2024-03-31.
- **`retrofit-insights.html`** gained a companion national chart ("What did each era
  build?", in the Timeline section): the 8 tracked measures as a share of that era's
  matched retrofits, from a new `insights_json/program_era.json`
  (`build_program_era()` in `Python/build_insights.py`). Fetched independently of
  `timeline.json` so a pre-refresh `insights_json/` degrades by hiding the new card,
  not by breaking the existing timeline chart.
- Era boundaries (ecoENERGY 2007–2012, Greener Homes 2021–2024) mirror the eras
  already drawn on the Retrofit Insights timeline chart and must be kept in sync
  across four places: `ERA_DEFS` in `precompute_province_stats.py`, `ERA_DEFS`/
  `ERA_KEYS` in `aggregate_canada.py`, `ERA_DEFS` in `Python/build_insights.py`, and
  `ERA_DEFS` in `assets/retrofits.js`.
- `aggregate_canada.py`'s national-recombination logic was refactored into a reusable
  `aggregate_slices()` function so it could run once for the totals and once more per
  era; fixed a latent bug in the same pass (`solar_median_kw` can be explicitly
  `None`, not just absent, for a slice with matched pairs but zero solar adopters —
  `.get(key, 0)`'s default only covers a *missing* key, not present-and-`None`. Was
  always theoretically possible for a small province, but era sub-slicing made a
  nonzero-n/zero-adopter bucket common enough to hit on the very first run).

### 2026-08-03 pipeline diagram, and this document brought back in line with the code

- **New "Pipeline overview" diagram** at the top of the advanced methodology: the
  full CSV → parquet → JSON → page flow as hoverable/focusable SVG boxes, each
  tooltip carrying the actual numbers, filters or datasets behind that stage,
  including the emission-factor and retrofit-cost branches. Electricity-rate source
  corrected in the tooltips; the unused Climate Normals credit dropped.
- **Documentation audit.** This file had drifted from the code in seven places, all
  corrected above: the unit-conversion table still carried pre-2026-07 oil
  (10.2 → **10.7778**) and wood (flat 4166.7 → the **GJ/MJ/tonne fallback chain**)
  factors; Step 1 still described the *exactly*-one-D-and-E pairing rule replaced on
  2026-07-24; the repository layout, Local development and Deployment sections still
  described fetching from `main` via `raw.githubusercontent.com` (the `gh-pages`
  split made `BASE_URL` `'./'`); `lookup/ahri_numbers.json` was described as never
  fetched by the page, which `assets/retrofits.js` has since started doing at
  runtime for the equipment-detail cards; the "no payback or dollar figures are
  possible" caveat predated both the bill card and the cost POC; the audit range
  said 2004–2025; and Step 1c was printed above Step 1.
- **Page corrections in the same pass.** The cost POC's coverage was stated as "all
  12 provinces + 2 territories" — it is **10 provinces + NT and NU** (Yukon has no
  ERS records). Its 1,420,044-record input is now explained rather than left to
  contradict the 1,451,433 matched-pair figure beside it (apartments, duplexes and
  triplexes — 31,389 records — are excluded, since REMDB's regressions and the
  footprint proxies assume single-dwelling geometry). **Solar PV and HRV/ERV** were
  being priced and rendered but appeared in neither methodology section; both are
  now documented, including the HRV's fixed-placeholder-metrics caveat. REMDB and
  the ECCC emission factors were added to the Sources list. Doc links that 404'd on
  the live site (`docs/` is not deployed to `gh-pages`) now point at the `main`
  blob, matching how `ERS_DATA_DICTIONARY.md` was already linked.
- **`deploy.sh` fixed:** `retrofit_costs_json` was missing from `PATHS`, so the next
  full deploy would have silently dropped the entire cost feature from the live site
  — it was only present via an earlier incremental push.

### 2026-08-02 GHG scenarios — 4 bases replace the raw-ERSGHG-only chart
- **New Step 1c (`compute_ghg_scenarios.py`)** adds `Pre_/Post_GHG_current`,
  `_current_corrected`, `_as_audited` alongside the existing, untouched
  `Pre_/Post_GHG` (raw `ERSGHG`) — see [GHG scenarios](#ghg-scenarios). Fixes the
  50.5%-coverage gap in every GHG chart/median on this page (raw `ERSGHG` was the
  only source before this).
- **Fixed a survivorship bias in `ers_ghg_factors.py`** (the ERS-calibrated factor
  derivation): excluding true-zero-GHG rows from the ratio inflated the implied
  factor and overstated the national aggregate by +12.8%; the fix (require GHG
  *reported*, not *positive*) brings it to +0.16%.
- **New `GHG basis` dropdown** above the GHG chart (both retrofits.html and
  retrofit-insights.html), defaulting to `as_audited` (validated to −0.66%
  national aggregate bias against real `ERSGHG`).
- Investigated why Alberta/Newfoundland need a correction against the official
  ECCC factors (not a within-province/FSA effect — see
  [ENERGUIDE_QUESTIONS.md §5.4](ENERGUIDE_QUESTIONS.md)) and why `as_audited`
  needs year-varying, not flat, combustion factors (Ontario's `ERSNGASGHG` runs
  near-zero 2006–2016 despite real gas consumption).

### 2026-07-31 Retrofit Costs proof of concept lands in the page

- **A cost and payback estimate, from outside the ERS data.** ERS has no cost fields,
  so this is a separate model: each home's recorded measures priced against PNNL/DOE's
  REMDB (2023 USD, vintage 2024.12.23), incremental to the business-as-usual choice,
  at REMDB's 10th/50th/90th-percentile bands. Eight measures priced — roof, wall and
  foundation insulation, air sealing, windows, ASHP, solar PV, HRV/ERV.
- **New independent pipeline chain**, off the same Step-1 parquets and not touching
  Steps 2/3: `retrofit_cost_extract_fields.py` → `retrofit_cost_estimate.py` →
  `build_retrofit_costs_json.py` → `retrofit_costs_json/`, joined to `fsa_json`
  client-side by `HOUSEID` precisely so cost-method changes don't force an
  `fsa_json` rebuild.
- **Scope:** 10 provinces + NT and NU; 1,420,044 single-dwelling paired records
  (multi-unit excluded), 1,237,117 with at least one priced measure (87%).
- Everything it rests on is flagged on the page: US cost data with no CAD or
  Canadian-labour adjustment, an assumed rectangle footprint, and utility rates whose
  electricity source is cross-checked only for Saskatchewan. Full method:
  [docs/RETROFIT_COSTS.md](RETROFIT_COSTS.md).

### 2026-07-24 heat-loss breakdown, asset split, measured pairing gates
- **New chart: "Where the heat escapes — annual loss by component."** Surfaces the
  `Pre_/Post_HeatLoss{WindowDoor,Wall,Foundation,Roof,Floor,Air}` columns that had only
  been visible inside an expanded row. Shared drawing code
  (`drawHeatLossComponents`) serves both modes: `renderHeatLossComponents()` sums raw
  rows in FSA mode, `renderProvinceHeatLossComponents()` reads the new
  `heatloss_components` key in province mode. **Per-home means, not medians** — the
  chart reports each component's share of total loss, which requires the six to sum to
  the whole-home figure. New mirror pair to keep in sync: `HL_COMPONENT_FIELDS` in
  `assets/retrofits.js` ↔ `HEATLOSS_COMPONENTS` in `precompute_province_stats.py`, with
  `aggregate_canada.py` combining them by `row_count` weighting (same as `waterfall`).
  Nationally: foundation 25%, air leakage 24%, windows/doors 22%, walls 21%, roof 8%,
  exposed floor 0.5%; 38,081 → 33,416 kWh/yr (−12%).
- **CSS and JS extracted** to `assets/retrofits.css` / `assets/retrofits.js` (see
  Front-end architecture). Repeat-visit transfer drops from ~93 KB to ~26 KB gzipped
  and 200 KB of script no longer blocks HTML parsing; first-visit total is unchanged.
- **Analytics tag fixed** — the `gtag.js` loader was requesting the placeholder
  measurement ID `G-XXXXXXXXXX` while `gtag('config')` used the real `G-3QLS1Q554N`.
- **Pairing gates A and B measured** (`diagnose_gates_ab.py`, full 9.5 GB scan) — see
  the new "Pairing gates" note under Data notes & caveats. No pipeline change yet.

### 2026-07 heat pump sizing & backup pairing
- **New Step 1b (`join_hp_capacity.py`)** joins `Post_HPAHRI` against a newly-built
  full AHRI certificate lookup (`lookup/ahri_numbers.json`, 15,148 entries — up from
  ~40 previously, which only covered the site's own top-5-per-province display list)
  to add verified heat-pump capacity/efficiency columns. See that step's description
  above for the full rationale.
- **"Heat pump + backup" and "Heat pump sizing" cards** added to the Equipment detail
  section: a backup-fuel breakdown for heat-pump homes (with a non-electric
  "actually used" sub-stat), and a capacity-vs-design-heat-loss sizing histogram
  (47°F mild-day and 5°F design-day series).
- **Individual-home detail table** relabels the heating-fuel/type rows "Backup
  fuel"/"Backup type" for heat-pump homes, and adds a certificate-capacity row.
- **`lookup/ahri_numbers.json` stays build-time-only.** It's now 4.87MB (up from a few
  KB); `retrofits.html` never fetches it directly — all AHRI-derived fields reach the
  browser pre-joined into `fsa_json`/`province_json` by Steps 1b/2/3.
  *(Superseded — see 2026-08-03 below: the file is now also fetched at runtime.)*

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
