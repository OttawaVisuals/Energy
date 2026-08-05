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
└─ build_retrofit_costs_json.py     # cost POC: splits the output into retrofit_costs_json/
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
   the **`E` audit to be dated after the `D` audit**. Each surviving pair becomes one
   `pre`/`post` row. (Changed 2026-07-24 — the rule was previously *exactly* one of each,
   which dropped every multi-audit home. See "Gate A — recovered" under
   [Data notes & caveats](#data-notes--caveats).)
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
validated against real AHRI certificates, `HPCAP` (Watts) runs a median **1.55×**
high, and the same AHRI number produces inconsistent (1×/2×/4×) values across
different audit rows — unusable for a sizing claim. The certificate's own
`heating_capacity_47f_btuh`/`heating_capacity_5f_btuh` fields are the trustworthy
source; 5°F (≈ −15°C) is used as a Canadian design-day proxy.

**Post-only:** pre-existing heat pumps are rare (~1.6% of homes), and the sizing/
backup-pairing story this feeds is about the retrofit's end state.

**Coverage:** measured on Ontario's paired parquet, **75.9%** of homes with a heat
pump post-retrofit resolve to a usable certificate (a further ~8% resolve to a
"Delisted" status-only entry with no specs). Coverage is highest for retrofits from
about 2019 onward — the AHRI reference number is much less consistently recorded by
auditors in earlier years.

### Step 1c — `compute_ghg_scenarios.py` (parquet → parquet, GHG scenario columns)

Adds 6 columns (`Pre_/Post_GHG_current`, `_current_corrected`, `_as_audited`) alongside
the existing, untouched `Pre_/Post_GHG` (raw `ERSGHG`) — see [GHG scenarios](#ghg-scenarios)
below. Depends on `Python/ers_ghg_factors.py`'s output
(`ers_ghg_factors_by_province_year.csv`) being current; re-run that first if it's stale.

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
- **Masks identifying heat-pump fields, not physical quantities.** `Post_HPAHRI` is
  blanked per-row unless it's one of the province's own top-5 most common AHRI
  numbers (`top_ahri_set()`) — too granular to expose otherwise (a long tail of
  near-unique installs). `Post_HPBrand`/`Post_HPModel` get the **same** row-level
  mask (they're equally identifying). `Post_HPCapacity47/5`, `Post_HPHSPF2`,
  `Post_HPCertCOP5`, `Post_HPColdClimate` are **left unmasked** — they're derived
  physical quantities, not identifiers, and the FSA-mode sizing histogram needs to
  see the same population as province mode's precomputed (never-masked) one, or the
  two views will disagree. Note: capacity+HSPF2+COP together can still narrow a
  masked row back toward its real AHRI number via the public AHRI directory — a
  minor residual, not treated as a hard privacy boundary.

### Step 3 — `precompute_province_stats.py` (parquet → province summaries)

Reduces each province to a fixed summary so the province-wide view never has to scan raw
rows in the browser. For the whole province **and** for each house type it precomputes:
medians (saving %, EUI, GHG), counts (deep retrofits, heat pumps, fuel switches, solar),
and ready-to-plot histogram **bins** for every chart — plus the Sankey flows, the
energy-by-fuel "waterfall", insulation KPIs/histograms, and the measures breakdown.

Also computes, for heat-pump homes only: a sizing-ratio histogram/median (AHRI-verified
capacity ÷ design heat loss, at 47°F and 5°F — `hp_sizing47/5_bins`/`_median`), a
backup-fuel breakdown (`backup_fuel_counts`, `Post_HeatFuel` restricted to heat-pump
homes — the "Heat Pump + backup" pairing, since HOT2000 tracks the heat pump as a
component separate from that column), and a "backup actually used" count
(`backup_used_counts`) restricted to **Natural Gas, Oil, and Propane** — the fuels with
a 1:1 label-to-consumption-column mapping. Excluded: Electricity
(`Post_HeatElectricity` can't distinguish the heat pump's own electricity use from an
electric-baseboard backup's) and the wood species (`Mixed Wood`/`Hardwood`/`Wood
Pellets`/`Softwood` all share one `Post_HeatWood` consumption column, so a per-species
check isn't meaningful). Both are still counted in `backup_fuel_counts`. The
denominator for each fuel is homes whose *own* `backup_fuel` is that fuel, not every
heat-pump home — otherwise the stat could exceed `backup_fuel_counts[fuel]` (a home
with a different backup can still show trace nonzero consumption in an unrelated fuel
channel) and read as a nonsensical >100%.

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
| Natural gas | m³ | × 10.3611 | kWh (37.30 MJ/m³, CER) |
| Oil | L | × 10.7778 | kWh (38.80 MJ/L light fuel oil, StatCan RESD 57-003-X) |
| Propane | L | × 7.0917 | kWh (25.53 MJ/L, CER) |
| Wood | GJ, else MJ, else tonne | × 277.778, else × 0.27778, else × 3888.89 | kWh (see below) |
| Design heat loss | W | × 0.001 | kW |
| GHG (`ERSGHG`) | tCO₂e/yr | — (as-is) | tCO₂e/yr |
| Solar PV (`KWPV`) | kW DC | — (as-is) | kW |
| Heat pump capacity (Step 1b, AHRI cert.) | BTU/h | × 0.00029307107 | kW |

GHG already includes electricity emissions via each province's grid factor, so
fuel-switching to electricity is reflected correctly.

**Wood is a three-way fallback chain, not one factor.** Since HOT2000 v11.2 the
source reports wood energy directly in GJ (`EGHFCONWOODGJ`, 43.4% filled) and that
is used verbatim — no heating-value assumption at all. Otherwise the pipeline
prefers `EGHHEATFCONSW`, HOT2000's own per-home heating-fuel split (already MJ,
also no assumption). Only the remaining ~0.3% of tonnes-only records fall back to
`EGHFCONWOOD` at a flat 14.0 GJ/t (NRCan Solid Biofuels Bulletin No. 2). The
earlier flat-factor-only version produced a handful of homes whose computed wood
energy exceeded their own reported total; preferring `EGHHEATFCONSW` fixed that by
construction. `retrofits.html`'s Methodology B carries the same table with the
per-fuel citations.

### GHG scenarios

`Pre_GHG`/`Post_GHG` (raw `ERSGHG`) is only populated for **50.5%** of matched
pairs nationally (measured 2026-08-02; Quebec ~78%, Ontario ~43%, Saskatchewan
~9%). Rather than build every GHG chart on half the population, **Step 1c**
(`Python/compute_ghg_scenarios.py`) calculates GHG for every matched home from
its own recorded fuel consumption (~100% complete), giving 4 bases — switched
by the **GHG basis** dropdown above the GHG chart on both retrofits.html and
retrofit-insights.html:

| Scenario | Electricity factor | Combustion factor |
|---|---|---|
| `reported` | — (raw `ERSGHG`, ~50.5% coverage) | — |
| `current` | flat 2026 official ECCC/OBPS, same for every audit year | fixed official ECCC/OBPS constants |
| `current_corrected` | same, Alberta/Newfoundland use ERS-calibrated instead | fixed official ECCC/OBPS constants |
| `as_audited` (default) | ERS-calibrated, matched to each home's own audit year | ERS-calibrated, year-varying |

**Why Alberta/Newfoundland are corrected, and why `as_audited` needs
year-varying combustion, not the fixed constants:** validated against real
`ERSGHG`, the official ECCC factors agree with the ERS data almost exactly for
combustion (gas/oil/propane, within 0.1–3.5%) but electricity is off by
18–29% (Alberta) and 27–49% (Newfoundland & Labrador), consistently across
2023–2026 at large sample sizes (40,000+ homes/yr for Alberta) — not noise.
Checked for FSA-level/regional variation and found none explains it: Newfoundland's
audited homes are almost all on the island, so the official province-wide
figure (diluted by Labrador's near-zero-carbon Churchill Falls hydro) doesn't
represent them; Alberta has only 159 of 85,771 homes that are electric-only
heated, nowhere near enough to test locally, and its grid has no published
zonal split. We could not find NRCan documentation of what HOT2000 uses
internally for this (open question — see
[ENERGUIDE_QUESTIONS.md §5.4](ENERGUIDE_QUESTIONS.md)), so these two provinces
substitute the ERS-calibrated factor, which by construction reproduces what
HOT2000 actually computed for these same audits. Separately, applying a flat
*modern* combustion factor across all history overstates Ontario's
pre-2017 gas GHG badly — `ERSNGASGHG` there runs near-zero for 2006–2016
despite substantial real gas consumption (n=54,967 in 2016 alone) — so
`as_audited` uses a year-varying ERS-calibrated combustion factor, not the
flat official constant. **Validated end to end**: `as_audited`'s national
aggregate lands within **−0.66%** of the real reported total, every
large-sample province within about ±2% except Quebec (−5.3%, small absolute
base). Wood is treated as 0 (biogenic-neutral) in every scenario — ECCC has no
residential wood-combustion factor at all, and the ERS-implied ratio
(~358 kg CO2e/kg) is not physically plausible.

**Sources & derivation**: `Python/ers_ghg_factors.py` (ERS-calibrated factor
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
| `Windows_Change` | window code present in both audits and different |
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

# (only if ers_ghg_factors_by_province_year.csv is stale, e.g. after Step 1 re-ingests
#  new CSV years) Recompute the ERS-calibrated GHG factor table from the raw yearly CSVs.
python scripts/ers_ghg_factors.py

# 1c) Add the 6 GHG scenario columns -- overwrites the parquet in place. Depends on
#     ers_ghg_factors_by_province_year.csv (previous step); idempotent otherwise.
python scripts/compute_ghg_scenarios.py

# 2) Province parquet -> per-FSA JSON (+ _index.json)
python scripts/split_fsa_json.py

# 3) Province parquet -> province_json/<PROV>.json summaries
python scripts/precompute_province_stats.py
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
  reduced to its **oldest D and newest E** — with the E dated later, and must pass the
  same-home checks (≤10% area change; unchanged type/storeys/units). A home audited more
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

  **Gate B — "E dated after D" drops 84,755 pairs, and should stay dropped.** The
  earlier assumption that these were parsing failures is wrong: **zero** are
  unparseable. 99.4% (84,253) have E on the *exact same calendar day* as D, and every
  frequent case is a first-of-month placeholder (`2011-03-01 → 2011-03-01` alone is
  6,219 homes, a batch-load artifact). Only 502 have E genuinely before D. Because the
  day component is a placeholder, these pairs carry **no recoverable ordering** — the
  source cannot tell us which audit is the "before". Admitting them would mean assuming
  a direction on a page whose entire premise is before-vs-after, so the honest handling
  is to keep excluding them and document the reason here.
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
  against real AHRI certificates, it runs a median 1.55× high, and the same AHRI
  number produces inconsistent values across different audit rows. Not used anywhere
  on the page; Step 1b's certificate join is the trustworthy source instead.

---

## Changelog

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
