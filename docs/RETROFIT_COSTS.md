# Retrofit Costs

**Status: proof of concept, exploratory — no live page, no committed pipeline output.**
This document records the methodology used in a PEI-scoped POC that pairs NRCan's
EnerGuide/ERS retrofit records (the same source as the [Retrofit Explorer](RETROFITS.md))
against a US cost-per-measure dataset, to test whether a defensible **estimated retrofit
cost** can be attached to each ERS record. Nothing here is wired into `retrofits.html`
or any other page.

---

## Table of contents
- [What this is trying to answer](#what-this-is-trying-to-answer)
- [Data sources](#data-sources)
- [Why this isn't a simple join](#why-this-isnt-a-simple-join)
- [Methodology](#methodology)
  - [REMDB pricing mechanics](#remdb-pricing-mechanics)
  - [Envelope area proxies](#envelope-area-proxies)
  - [Measures priced](#measures-priced)
  - [Measures explicitly NOT priced](#measures-explicitly-not-priced)
- [Production pipeline change](#production-pipeline-change)
- [PEI POC results](#pei-poc-results)
- [Open questions / next steps](#open-questions--next-steps)
- [Files](#files)
- [Changelog](#changelog)

---

## What this is trying to answer

The Retrofit Explorer shows *what* changed in a retrofit (insulation levels, heating
equipment, air-tightness) and the energy/GHG effect, but never *what it cost*. Could we
attach a defensible dollar estimate to each ERS retrofit record, using a real
per-measure cost dataset instead of a single rule-of-thumb "$/retrofit" number?

The answer, from this POC: **partially, and only with several explicit, documented
assumptions** — the ERS data was never designed to support cost estimation, so most of
the work here is bridging fields ERS does track to the inputs a cost dataset actually
needs.

**As of 2026-07-31 the model is framed as *incremental* cost, not full cost** — see the
next section. The full-cost mechanics below (REMDB pricing, area proxies) are unchanged;
what changed is that each measure's figure is now the *extra* cost over what a homeowner
would have spent anyway.

---

## Incremental cost model

REMDB can price the *full* installed cost of a measure, but a full cost is the wrong
number for most of these retrofits: the honest question is **how much more** an efficient
choice costs than the business-as-usual (BAU) thing the homeowner would have done regardless.
Every figure is now that increment. Where a measure has no BAU alternative, incremental
and full cost are identical.

| Measure | Business-as-usual baseline | Incremental cost |
|---|---|---|
| Roof/attic, wall, foundation insulation | **none** — cavity fill has no maintenance equivalent | full REMDB cavity-fill cost (unchanged) |
| Air sealing | **none** | full REMDB air-sealing cost (unchanged) |
| Windows | a **standard** window at the *pre-retrofit* pane count | `efficient(post pane) − standard(pre pane)`, per window |
| ASHP | replace the pre-audit heating system like-for-like **plus** a central A/C — the two appliances an ASHP does the job of | `ASHP − BAU heating − BAU cooling` |

### Insulation & air sealing — incremental *is* the full cost

Nobody fills a wall cavity, insulates an attic floor, or blower-door-seals a house as
routine upkeep, so there is no BAU spend to net out. This is exactly why the cavity-fill
rate that read as "too low" for a *full* retrofit (it excludes scaffolding, re-cladding,
etc.) is the *right* number for an incremental one — those exterior-work costs only exist
if you were re-siding anyway, which is itself the BAU case. Formulas unchanged:
`[ base $/ft² + (R-coef × ΔR added) + install adder ] × area`.

### Windows — standard vs efficient, keyed to pane count

The window code carries both the **pane count** (digit 1: `1/2/3` = single/double/triple)
and the **efficiency features** (digit 2 = coating/Low-E, digit 3 = fill/argon). BAU is
that the homeowner replaces aging windows with **standard** units *at the pane count they
already had*; the retrofit installs **efficient** (Low-E) units, sometimes at a higher pane
count. One formula covers both of your cases:

```
incremental per window = EfficientPrice(post_pane) − StandardPrice(pre_pane)
window line            = incremental per window × NUMWINDOWS
```

- pane unchanged (double → double): `Efficient(double) − Standard(double)`
- pane upgraded (double → triple): `Efficient(triple) − Standard(double)`

Standard vs efficient prices come from REMDB's **raw `Windows Data` sheet** (not the
collapsed Machine-Read flat-by-frame rate, which cannot see glazing at all), keyed by
(frame material, pane count, class): `Standard` glass = BAU, `Low-E` / `Energy Efficient`
glass = the retrofit.

**Noise control (size-normalised + trimmed).** The raw rows mix window sizes, and a small
window costs more per ft² than a large one — so the *per-window* prices were noisy. Two steps:
1. Work in **`$/ft²` of glass** and re-multiply by our **one default window size
   (1.4 m² ≈ 15.1 ft²)**, the size the rest of the model uses — both classes then priced at
   the *same* area, removing the sampling artifact.
2. Within each price cell, **drop the highest and lowest `$/ft²`** before taking the median,
   so a single extreme row can't swing it.

For **triple-pane**, the strict (frame, class) cells are too thin to trim (Low-E n=1, a
low outlier). Since a triple-pane window is efficient *by construction*, its price is
taken by **pooling all triple-pane rows for that frame** (any class) and then trimming —
n=15 for Vinyl, a stable $111/ft². Resulting Vinyl table:

| Vinyl, priced at the default 1.4 m² window | $/ft² | per window |
|---|---|---|
| Standard, double-pane | $23.3 (n=8) | **$352** |
| Efficient (Low-E), double-pane | $53.1 (n=134) | **$801** |
| Triple-pane (pooled, trimmed) | $111 (n=15) | **$1,678** |

Worked increments: **double→double = $801 − $352 ≈ $449/window**; **double→triple =
$1,678 − $352 ≈ $1,326/window**. Both now defensible; the triple figure carries a wider
error bar (pooled across classes) but no longer depends on a single row.

### ASHP — vs a furnace/boiler *plus* a central A/C

An ASHP does two jobs a conventional home does with two appliances — it heats and it cools —
so its BAU baseline is both of them, each replaced at end of life:

```
incremental = ASHP_cost − BAU_heating_cost − BAU_cooling_cost   (may be negative)
```

- **BAU heating — like-for-like, gas furnace only as a last resort.** On PEI, 80% of
  ASHP-addition homes were oil-heated pre-retrofit and under 1% were on gas — a uniform
  gas-furnace baseline priced the wrong replacement for the overwhelming majority of
  records. `Pre_HeatType` (`FURNACETYPE`) and `Pre_HeatFuel` (`FURNACEFUEL`) already
  survive the pipeline, so the BAU is now the home's **own pre-audit equipment**, bucketed
  into Furnace/Heater vs. Boiler vs. Baseboard and crossed with fuel, mapped to the closest
  REMDB row:

  | Pre-audit type + fuel | REMDB row | Match |
  |---|---|---|
  | Boiler + Oil | `Boiler / Oil` | REMDB-fitted (n=120) |
  | Boiler + Natural Gas | `Boiler / Gas (Condensing`\|`Non-Condensing)`, picked by `Pre_HeatAFUE` ≥0.90 | REMDB-fitted |
  | Furnace/Heater + Natural Gas | `Furnaces / Gas Furnace` | REMDB-fitted |
  | Baseboard/Hydronic + Electricity | `Electric Baseboard` | REMDB-fitted |
  | Furnace/Heater + Oil | `Furnaces / Oil Furnace` | **self-derived** (REMDB never fit this class — see below) |
  | Boiler + Electricity | `Boiler / Electric` | **self-derived** |
  | Everything else (propane, wood stove/boiler, electric furnace, unparseable) | `Furnaces / Gas Furnace` | assumed-default fallback — REMDB has no row for these at all |

  Sized the same way as before: `Pre_HeatLoss` (design heat loss, kW→BTU/hr) for capacity,
  `Pre_HeatAFUE` for boilers/furnaces (falls back to a REMDB-bounds-typical 0.80/0.83 when
  missing). Every ASHP record carries `BAUHeatingSource` (`'like_for_like'` /
  `'assumed_default'`) so the fallback is never silently mixed with a real match. Re-run on
  PEI: **1,650 of 1,759 ASHP records (94%) now get a like-for-like match**, versus the old
  model's uniform assumption for 100%. Median ASHP incremental cost dropped from $5,227 to
  **$3,438** (mid case) — expected, since replacing an actual oil system is pricier than
  the old flat gas-furnace baseline, so crediting the real BAU lowers ASHP's net premium;
  8.6% of records now go negative (up from ~0%), a real signal that ASHP undercuts the
  actual old system more often than the generic baseline implied.

  **Two self-derived REMDB rows.** REMDB's own quantile regression was only fit for Gas
  Furnace / Gas+Oil Boiler / Electric Baseboard — never Oil Furnace or Electric Boiler,
  despite both having real raw line items sitting unused in the source workbooks
  (`Non-Envelope Measures 7-18-24.xlsx`, `Furnace Data` / `Boiler Data` sheets). Rather than
  falling back to gas furnace for 53% of PEI's ASHP records (the oil-furnace share), two
  simple price rows were derived directly from those raw line items, in the same $/BTU
  quantile-band spirit REMDB uses elsewhere:
  - **Oil Furnace** — 6 RSMeans "Installed Cost (O&P)" line items (56,000–200,000 BTU/hr,
    already fully-loaded retail prices, no separate installation adder needed). Low/Mid/High
    = 10th/50th/90th percentile of installed-$/BTU across those 6 points
    ($0.0311 / $0.0401 / $0.0643 per BTU/hr).
  - **Boiler / Electric** — 10 Viessmann/Argo material-price line items (13,652–54,600
    BTU/hr). Low/Mid/High = 10th/50th/90th percentile of material-$/BTU
    ($0.0532 / $0.0659 / $0.1253 per BTU/hr), plus REMDB's own `Boiler / Oil` retrofit
    installation adder ($4,040), borrowed as the nearest fitted boiler-class analog since no
    electric-boiler installation cost data exists in the raw sheets.

  Both are flagged `self_derived=True` internally and reported as `'like_for_like'` (they
  price the home's real equipment, just via our own regression instead of REMDB's) — never
  silently blended with REMDB's own fitted classes. n is small (6 and 10 points) — these are
  order-of-magnitude-defensible, not REMDB-grade fits; worth widening the sample if this
  moves past POC.
- **BAU cooling** — an air conditioner at the ASHP's *own* cooling capacity and SEER1.
  ERS **does** record the home's pre-retrofit cooling, so the credit is data-driven rather
  than blanket: `ACCENTESTAR` (central A/C present), `ACWINDNUM` (count of window units),
  and `ERSSPACECOOLENERGY` / `ERSDesCoolLoss` (cooling energy / design load > 0) together
  say whether — and what kind of — cooling was already there. Mapping:
  - had **central** A/C → credit `Air Conditioner / Centrally ducted` (it would be replaced anyway);
  - had **window** units, or the ASHP is ductless → credit `Air Conditioner / Room AC`;
  - had **no** cooling → still credit a central A/C (the canonical "furnace + A/C" pair an
    ASHP substitutes for), since the ASHP's price genuinely includes delivering cooling.

  This is the "credit the avoided A/C" step: without it, comparing a heat-pump (heating +
  cooling) to a furnace (heating only) would penalise the ASHP for doing more.
- **The result can be negative.** An ASHP is sometimes cheaper than a new furnace + A/C —
  a real, defensible finding shown as-is, never floored at zero.

Note the gas-furnace baseline is a *uniform assumption*, not the home's actual pre-audit
fuel: a house heated by electric baseboard or oil is still credited a gas furnace, because
the question is "what would they most likely have installed instead," not "what did they
have." Flagged as an assumption in the display.

---

## Data sources

### ERS (input side)
Same source as [RETROFITS.md](RETROFITS.md) — NRCan's EnerGuide/HOT2000 pre/post audit
pairs, `Python/ers_web_pipeline.py` output (`C:\ERS\web\ers_web_<PROVINCE>.parquet`).

### REMDB (cost side)
**PNNL/DOE's National Residential Efficiency Measures Database (REMDB)**, vintage
`2024.12.23` (envelope/non-envelope raw-data workbooks dated July 2024). Committed to
this repo under `retrofits/USCosts/`:

| File | Contents |
|---|---|
| `REMDB_2024.12.23.xlsx` (`Machine Read` sheet) | 133 component/class rows: quantile-regression coefficients (10th/50th/90th — "Low/Mid/High") mapping 1–2 performance metrics to a **2023 USD** material price, plus new-construction/retrofit installation multipliers or adders, lifetime, and a numbered source list |
| `Envelope Measures_Active_7-12-24.xlsx` | Raw line-item data behind the envelope regressions (insulation, air sealing, doors, windows, ducts, etc.) |
| `Non-Envelope Measures 7-18-24.xlsx` | Raw line-item data behind HVAC/appliance regressions (ASHP, furnaces, boilers, water heaters, etc.) |
| `Machine Readable Guidance Document 12-23.docx` | REMDB's own methodology write-up — the worked examples here (ASHP multiplier method, attic-insulation adder method) are the ground truth for the pricing mechanics below |

**Currency/market caveat, stated once and applying everywhere in this doc:** REMDB is
**2023 USD**, sourced from US retail/contractor data (RSMeans, Homewyse, DOE rulemaking
technical support documents). No CAD conversion or Canadian-labor adjustment has been
applied anywhere in this POC — every dollar figure below is a US-priced estimate applied
to a Canadian house, not a Canadian cost.

### Utility rates (payback side)

Payback (incremental cost ÷ annual $ saved) needs a $/kWh-equivalent rate per fuel per
province — separate from REMDB, computed in `utility_rates_reference.json` and applied the
same way `Python/precompute_province_stats.py` already prices $-saved for the (currently
dormant — see below) bill-saving card. Built in three layers, run in this order:

1. `Python/utility_rates_reference.py` — electricity + gas, scraped monthly from
   `MaxPr1me/canada-utility-rates` (GitHub), one blended $/kWh or $/m³ per province.
2. `Python/add_oil_propane_rates.py` — adds heating oil / propane (NRCan "Prices by City",
   manual-download Excel exports, averaged per province) and heating wood (one flat national
   estimate, single secondary source — see that script's docstring, unchanged this round).
3. **`Python/override_electricity_rates.py` (new, 2026-07-31)** — replaces step 1's
   **electricity** figures only, province by province, with rates from
   [offgridsolarsystem.ca's Canada electricity rates page](https://offgridsolarsystem.ca/blog/Canada-electricity-rates.html)
   (page's own "Updated: July 1, 2026").

**Why the source was swapped for electricity, not gas:** cross-checking `canada-utility-rates`'
Saskatchewan electricity figure against SaskPower's own published rate PDF found it stale by
~67% (9.28 ¢/kWh dated 2025-01-01 in our data vs. SaskPower's actual current 15.476 ¢/kWh,
effective 2026-02-01) — and it had been flagged **"high confidence."** Force-refreshing the
upstream scrape reproduced the same stale number, confirming the gap is in the upstream source
itself, not a local cache. The blog source was spot-checked against that same SaskPower PDF and
matched exactly, and it gives clean coverage for all 13 provinces/territories in one place
(the old source had no gas coverage at all for 5 of them). Gas was checked too, while at it:
every province's gas `effective_date` reads exactly `2024-10-01` — the gas side of the same
upstream scrape looks frozen at one snapshot, ~21 months stale as of this writing, a more
systemic problem than electricity's per-utility gaps but with **no verified replacement source
lined up yet**, so gas is left as-is, **flagged**, not fixed.

**Known limitations of the new electricity source, not yet resolved (FLAGGED — needs more
investigation before this data should be treated as authoritative):**
- It's a third-party rate-aggregation blog, not a government or utility-primary source. Only
  Saskatchewan has been independently re-verified against the actual utility (SaskPower's PDF,
  exact match); every other province's figure is trusted as-published, unverified.
- Most provinces publish only the blog's own **all-in blended headline rate** (energy + delivery
  folded together at the blog's own assumed "typical usage"), not a clean energy-only commodity
  rate. Two exceptions where the blog states energy separately (SK, NS) use the energy-only
  figure, matching this pipeline's existing "volumetric energy only" convention elsewhere
  (fixed monthly charges are deliberately excluded because they largely cancel in a pre/post
  retrofit delta — but a blended rate that folds an *assumed-usage* fixed-charge share into
  ¢/kWh does **not** cancel the same way for homes whose actual usage differs from that
  assumption, which most ERS retrofit homes' actual usage will).
- BC, Yukon, and NWT publish as **ranges**, not single rates (BC: 3 different figures across
  BC Hydro's 2 tiers + FortisBC; YT: 18.0–24.0¢; NT: 25.0–34.0¢, post-subsidy). The range
  **midpoint** was used as a point estimate for YT/NT; BC uses BC Hydro's own Step 1 headline.
  None of these were reconciled against which figure best represents a typical retrofit-scale
  ERS home.
- NT and NU's figures are explicitly **post-subsidy** (Territorial Power Support Program),
  a different quantity than every other province's pre-subsidy published tariff — not
  apples-to-apples with the rest of the table.
- Every entry carries a `superseded` field in `utility_rates_reference.json` holding the old
  `canada-utility-rates`-sourced value, for comparison/rollback.

**Separately, `retrofits.html`'s own "$ saved" stat card is currently dead markup** — the
`renderCost`/`renderProvinceCost` functions its code comments reference don't exist in the
file, so payback will be computed directly in the cost pipeline (`retrofit_cost_estimate.py`),
not by finishing that dormant frontend feature.

---

## Why this isn't a simple join

REMDB prices measures per unit of **area** (insulation, windows, doors — $/sqft) or per
unit of **capacity + efficiency** (HVAC — e.g. tons + SEER1). ERS, as extracted by the
existing pipeline, carries neither:

- **No per-component envelope area at all.** Confirmed against the raw `C:\ERS\*.csv`
  headers (433 columns): the only area fields are whole-house/whole-floor
  (`FLOORAREA`, `HEATEDFLOORAREA`, `BASEMENTFLOORAR`, `CRAWLSPFLOORAR`,
  `SLABFLOORAREA`, `WALKOUTFLOORAR`). No wall, ceiling, foundation-wall, rim-joist,
  window, or door area/perimeter/dimension field exists anywhere in the public NRCan
  extract — not a pipeline omission, a genuine absence at the source. The surface-area
  geometry lives only inside individual HOT2000 `.h2k` files, which aren't distributed.
- **No HVAC cooling-capacity/SEER metric matching REMDB's regression inputs**, in the
  fields the existing pipeline surfaces. `Post_HPCapacity47/5` (kW) and `Post_HPHSPF2`
  are *heating*-side figures; REMDB's Air Source Heat Pump regression needs *cooling*
  capacity (tons) and SEER1. This data does exist in `lookup/ahri_numbers.json`
  (`cooling_capacity_btuh`, `seer2`) — it just wasn't being surfaced (see
  [Production pipeline change](#production-pipeline-change)).
- **No door-replacement signal.** `NUMDOORS` is a static count (present on every
  record, unchanged pre/post) — there is no flag indicating a door was actually
  replaced, unlike windows (`Windows_Change`) or insulation
  (`*_Insulation_Upgrade`).

So most of this POC is building geometry and equipment-classification proxies to bridge
the gap, each one an explicit, separately-stated assumption — not a hidden default.

---

## Methodology

### REMDB pricing mechanics

From the guidance doc's two worked examples (confirmed: each REMDB component/class row
uses **exactly one** of two installation methods — never both):

```
material_price = coef1 * metric1 + coef2 * metric2 + intercept
```
(`metric2`/`coef2` are absent — effectively 0 — for single-metric or no-metric
components; e.g. windows have no metric at all, so `material_price = intercept`.)

Then, per component/class row:
```
if installation_multiplier_retrofit != 1:
    installed_cost = material_price * installation_multiplier_retrofit
else:
    installed_cost = material_price + installation_adder_retrofit
```

Low/Mid/High coefficients and intercepts are carried through independently, giving a
low/mid/high **sensitivity range** for every priced measure and every summed total —
never collapsed to a single point estimate.

Metric values are clamped to REMDB's stated Lower/Upper Bound for that regression
before use (per the guidance doc's "Calculations Beyond Bounded Values" section).

### Area basis, confirmed against REMDB's raw data sheets

The "$/sqft" a REMDB regression is priced in is **not the same area for every
measure** — confirmed by opening the underlying raw-data sheets (not just the
guidance doc's two worked examples), since the guidance doc itself never
states which area basis applies per component:

| Measure | Area basis | Confirmed from |
|---|---|---|
| Air sealing | Whole-house **floor area** (`sq_ft_home`) | `Air Sealing Data` sheet: `$/sqft = total_cost / sq_ft_home` |
| Windows | The **window's own area** (its glass/unit area, not floor area) | `Windows Data` sheet: rows are per-product, `Width(in) x Height(in) -> Area (sq. in) -> Materials ($/SF)` |
| Wall insulation | **Wall surface area** | `Wood Stud` sheet: `$/SF` rows tagged `Wall` in Source Notes |
| Roof/attic insulation | **Ceiling/attic surface area** | `Unfinished Attic` sheet: `$/SF` rows tagged `Floor/Ceiling` in Source Notes |

This matters because it confirms the existing ERS-side proxies
(`WallArea_m2`, `RoofArea_m2`, `WindowArea_m2`) are matched to the correct
area basis, not just plausibly named.

### Envelope area proxies

Since no per-component area exists in ERS, every envelope area is a **geometric proxy**
derived from whole-house fields, using a **rectangle footprint assumption**:

```
long_side  = sqrt(area / RECT_ASPECT_RATIO)
short_side = RECT_ASPECT_RATIO * long_side
perimeter  = 2 * (long_side + short_side)
```

with `RECT_ASPECT_RATIO = 2/3` (short:long side ratio). **This is a judgment call, not
backed by a local dataset of actual Canadian house footprint proportions** — none was
found in this repo (checked `HeatPump/data/` and NRCan-archetype-adjacent files). A
square (ratio 1:1) was rejected because it *minimizes* perimeter for a given area and so
systematically underestimates wall area for any real, non-square house. Sourcing a real
footprint-ratio distribution (e.g. NBC reference-house archetypes, a CMHC housing-stock
study) is an open item before this goes beyond POC.

| Proxy | Formula | Notes |
|---|---|---|
| `RoofArea_m2` | `FOOTPRINT` | Ceiling/attic area ≈ building footprint |
| `WallArea_m2` | `rect_perimeter(FOOTPRINT) * Storeys * 2.44m` | 2.44 m = assumed 8 ft storey height |
| `FoundationWallArea_m2` | `rect_perimeter(BASEMENTFLOORAR) * 2.0m` | Only for houses with a basement (`FoundationType` contains `'B'`); 2.0 m = assumed interior-insulation coverage height, **not** full basement wall height, since retrofit basement insulation is typically installed from the inside and doesn't need to run the full height |
| `WindowArea_m2` | `NUMWINDOWS * 1.4 m²` | Average window unit size, assumed |
| `DoorArea_m2` | `NUMDOORS * 1.9 m²` | Average door unit size, assumed (not currently priced — see below) |

### Measures priced

All use REMDB's **Retrofit**-scenario coefficients (not New Construction), and default
to the **"Batt"** insulation class / **"Vinyl"** window class since ERS records
R-value/RSI but never the installed material.

| Measure | ERS trigger | REMDB row | Input(s) |
|---|---|---|---|
| Roof/attic insulation | `Roof_Insulation_Upgrade == True` | Unfinished Attic (Ceiling) / Batt | ΔR-value (Post − Pre RSI, converted ×5.678) as the R-value of the *added* material; `RoofArea_m2` |
| Wall insulation | `Wall_Insulation_Upgrade == True` | Wood/Steel Stud / Batt | ΔR-value; `WallArea_m2` |
| Foundation/basement wall insulation | `Foundation_Insulation_Upgrade == True`, basement houses only | Unfinished Basement (Wall) / Batt | ΔR-value; `FoundationWallArea_m2` |
| Windows | `Windows_Change == True` | Window / {`WindowClass`} | Flat $/sqft (no performance metric); `WindowArea_m2`; class from `UGRWINDOWCODE` (see below) |
| Air source heat pump | `HeatPump_Addition == True`, `ASHPClass` assigned | Air Source Heat Pump / {class} | `Post_HPCoolingCapacityTons`, `Post_HPSEER1Est` (both from the extended AHRI join — see below) |

**Wall construction type and insulation material are both fixed assumptions,
not sourced from ERS.** REMDB actually prices five distinct wall systems
(Wood/Steel Stud, Double Wood Stud, CMU, ICF, SIP) and multiple insulation
materials per system (Batt, Rigid Foam, Spray Foam, etc.) — real price
differences exist between them. Checked
`nrcan-open-data-dictionary-dictionnaire-des-donnees-ouvertes-de-rncan.xlsx`
for a wall-construction-type field: none exists. The only wall fields are
`WALLDEF`/`UGRWALLDEF` (a text description of % wall area + nominal R-value),
`MAINWALLINS`/`UGRWALLINS` (effective RSI), `FNDWALLINS`, and
`PONYWALLEXISTS` — nothing distinguishes stud vs. masonry vs. panel
construction, or insulation material. The Wood/Steel Stud + Batt default is
a genuine ERS-source gap, not a pipeline oversight — resolving it would need
the underlying `.h2k` files, which aren't distributed. Similarly, REMDB
splits attic insulation into `Unfinished Attic (Ceiling)` (attic-floor
insulation) vs. `Unfinished Attic (Roof)` (roof-deck/cathedral insulation) —
ERS's `Roof_Insulation_Upgrade` flag doesn't distinguish which was done; this
POC only prices the Ceiling variant.

**Window frame class is sourced from ERS, not assumed.** `UGRWINDOWCODE`
(post-retrofit window code of the windows occupying the greatest area) is a
6-digit HOT2000 code; digit 6 (rightmost) is the frame material, decodable
via `Support.xlsx`'s `Frame` sheet (0/1 = Aluminum/Aluminum Thermal Break, 2 =
Wood, 3 = Aluminum Clad Wood, 4/5 = Vinyl/Reinforced Vinyl). Mapped to
REMDB's three Window classes:
- Aluminum, Aluminum Thermal Break → REMDB `Metal`
- Vinyl, Reinforced Vinyl → REMDB `Vinyl`
- Wood, Aluminum Clad Wood, or an undecodable/missing code → **no REMDB Wood
  class exists**, so these fall back to `Vinyl` (the cheaper of the two real
  classes); tagged `WindowClassSource = 'assumed_default'` so the fallback is
  never silently hidden, mirroring the ASHP reported/assumed-default pattern.

On PEI: of 1,172 window-change records, 966 (82%) get a **reported** frame
class (1,150 Vinyl, 22 Metal) instead of a guess; 206 (18%) still fall back
(no code, undecodable, or wood-frame). Cost impact was small (median $20,459
reported vs. $21,823 assumed-default, mid case) — reassuring, but as with
ASHP, a small delta doesn't make the fallback a measurement.

**Air sealing has a real, unused REMDB regression.** Checked REMDB's
`Machine Read` sheet directly: there is a dedicated `Air Sealing` component
(two rows — `<40% Reduction` and `>40% Reduction`), priced in `2023$/sqft` as
a function of **percent leakage reduction**, applied to whole-house floor
area (confirmed above). ERS's blower-door pre/post result gives a real
measured leakage reduction — this is one of the *more* defensible measures
available (a measured input, not a geometric guess) — but it was **not
included in this POC's priced-measures list**. Left as the clearest next
addition (see [Open questions](#open-questions--next-steps)).

**ASHP classification (`ASHPClass`)** — REMDB has three ASHP classes (Centrally ducted,
Non-ducted single-zone, Non-ducted multi-zone) with materially different cost curves.
ERS's `UGRHPEquipType` field distinguishes these, but **is only reliably populated from
2025 onward** (52% coverage in 2025, 100% in 2026; under 3% in every year 2012–2024 — a
recent NRCan data-collection addition, not a quality gap). Classification logic:

- `UGRHPEquipType == 'Central split system'` → `Centrally ducted`
- `UGRHPEquipType` contains `'Ductless'` and `UGRNUMBEROFHEADS >= 2` → `Non-ducted, multi-zone`
- `UGRHPEquipType` contains `'Ductless'` and `UGRNUMBEROFHEADS < 2` (including the
  common `0` value, treated as under-reported rather than truly zero heads) →
  `Non-ducted, single-zone`
- `'Ground source heat pump'` / `'Not installed'` → excluded (GSHP is n=1 in PEI, not
  worth its own REMDB costing path here)
- **Fallback for `HeatPump_Addition == True` records with no `UGRHPEquipType` at all**
  (the large majority, pre-2025): default to `'Non-ducted, single-zone'` — PEI's
  observed dominant type by roughly 15:1 over centrally ducted in the years the field
  *is* recorded. This is an **assumed** class, not a reported one; every record carries
  a parallel `ASHPClassSource` column (`'reported'` / `'assumed_default'`) so the
  distinction is never lost downstream. In the PEI POC the two groups' median costs
  landed close together ($10,562 reported vs. $9,514 assumed-default), which is
  reassuring but does not make the assumption a measurement.

**SEER1 estimate (`Post_HPSEER1Est`)** — REMDB's ASHP regression was fit on **SEER1**
(the pre-2023 DOE test-procedure metric). AHRI certificates issued since 2023 report
only **SEER2**, a stricter test. `Post_HPSEER1Est = Post_HPSEER2 / 0.95`, using the
commonly cited approximate SEER2→SEER1 conversion factor for split systems. This is an
**estimate**, not a certified value — flagged distinctly from `Post_HPSEER2` (the raw
certified figure) in the data.

### Measures explicitly NOT priced

| Measure | Why not |
|---|---|
| Floor (exposed floor) insulation | RSI delta exists (`Pre_/Post_FloorInsulation`) but no area proxy at all, and it's rare (193/12,554 PEI records — not worth inventing an assumption for) |
| Doors | No door-replacement change signal in ERS (`NUMDOORS` is a static count) — pricing "however many doors this house has" would silently assume every retrofit replaced its doors |
| Furnace / boiler | REMDB prices furnaces on (Heating Capacity BTU/hr, AFUE); no furnace/boiler capacity field survives the pipeline, and even the raw `TYPE1CAPACITY`/`HEATSYSSIZEOP` fields are static pre-retrofit values, not necessarily the new equipment's size |
| Ground source heat pump | n=1 in PEI; not worth a separate REMDB GSHP costing path for this POC |
| **Any measure on a multi-dwelling building** | Apartment / Apartment Row / Detached & Attached Duplex & Triplex (311 PEI records) are excluded outright — the ERS record's `FOOTPRINT`/`NUMWINDOWS`/`BASEMENTFLOORAR` describe the whole building, so REMDB's single-family per-ft²/per-unit curves would inflate every measure (see [Changelog 2026-07-31](#changelog)) |

---

## Production pipeline change

One real (non-scratchpad) change was made to support ASHP costing:
**`Python/join_hp_capacity.py`** was extended to surface two AHRI certificate fields
that were already present in `lookup/ahri_numbers.json` but not previously pulled
through:

- `Post_HPCoolingCapacityTons` ← `cooling_capacity_btuh` (÷ 12,000)
- `Post_HPSEER2` ← `seer2` (as certified)
- `Post_HPSEER1Est` ← `Post_HPSEER2 / 0.95` (see above)

This is additive (3 new columns, `NEW_COLS` extended 7 → 10) and the script remains
idempotent/safe to rerun, per its existing design. It was re-run for all 12 province/territory codes
after the change (`ers_web_*.parquet` regenerated in place, `C:\ERS\web\`).

Coverage on PEI: of 12,554 paired records, 7,545 carry a `Post_HPAHRI` code, 7,488 of
those resolve to a lookup entry, and 7,057 of those (94% of matches) have both
`cooling_capacity_btuh` and `seer2` populated.

Everything else in this document (area proxies, `ASHPClass` derivation, REMDB pricing)
lives only in scratchpad scripts — see [Files](#files) — pending a decision on whether
to formalize this into a real pipeline step.

---

## PEI POC results

12,554 paired PEI retrofit records (`ers_web_PE.parquet`), all figures **2023 USD, mid
(50th-percentile) case** unless noted:

| Measure | Records priced | Median | p10–p90 |
|---|---|---|---|
| Roof/attic insulation | 4,883 (39%) | $2,091 | $1,128–$3,248 |
| Wall insulation | 1,016 (8%) | $1,287 | $1,043–$1,599 |
| Foundation/basement insulation | 4,355 (35%) | $1,120 | $857–$1,418 |
| Windows | 1,172 (9%; 966 reported frame class, 206 assumed-default) | $20,459 | $13,639–$36,826 |
| ASHP | 1,817 (130 reported class, 1,687 assumed-default class) | $9,551 | $8,253–$10,562 |
| **Any measure priced** | **8,535 / 12,554 (68%)** | **$3,059** | **$1,041–$18,941** |

The window figure is the single largest, most assumption-heavy line (both the material
class and the per-window area are guesses) and is the one most worth pressure-testing
against real invoices before trusting.

---

## Open questions / next steps

- **Air sealing is not yet priced**, despite REMDB having a direct, real
  regression for it (`Air Sealing` / `<40%` and `>40% Reduction`, driven by
  measured blower-door leakage reduction — see above). This is the clearest
  next measure to add: unlike windows/walls/roof, it needs no geometric area
  proxy invention beyond the floor-area field ERS already carries.
- **Footprint aspect ratio (2:3)** is asserted, not sourced. Worth checking NBC
  reference-house archetypes or a CMHC housing-stock study for a real distribution.
- **Window/door average unit size** (1.4 m² / 1.9 m²) are round-number placeholders,
  not measured.
- **Window frame material** is now sourced from ERS (`UGRWINDOWCODE` → REMDB
  `Vinyl`/`Metal`, see above) — 82% reported on PEI, 18% still an assumed
  fallback (Wood-frame codes have no REMDB equivalent).
- **Insulation material class** (defaulted to "Batt" everywhere) drives real REMDB
  price spread (batt vs. spray foam vs. rigid foam differ substantially) and ERS
  records none of it.
- **Wall construction type** (Wood/Steel Stud vs. Double Wood Stud vs. CMU vs.
  ICF vs. SIP) has no ERS field at all (checked the NRCan open-data
  dictionary — confirmed absent, see above); REMDB prices all five
  differently. Same gap for attic-floor vs. roof-deck insulation
  (`Unfinished Attic (Ceiling)` vs. `(Roof)`) — ERS doesn't distinguish which
  was retrofitted.
- **SEER2→SEER1 factor (0.95)** is a commonly cited approximation, not derived from
  Canadian AHRI data specifically.
- **Furnace/boiler and floor-insulation costing** remain entirely unpriced — would need
  new pipeline fields (furnace capacity) that don't currently survive Step 1, or an
  area proxy that doesn't exist yet.
- **USD → CAD conversion and Canadian labor-cost adjustment**: not attempted anywhere
  in this POC. Every number above is a US-priced estimate, full stop.
- **Scale beyond PEI**: the methodology is province-agnostic (all inputs are national
  ERS fields), but PEI's *ASHP mix* (heavily ductless) is not necessarily representative
  of other provinces — the `ASHPClass` fallback default would need re-checking per
  province before reuse.
- **Formalize into a real pipeline step** (currently scratchpad-only, per-run scripts)
  if this moves past POC.

---

## Files

**Committed to `main` — the POC now lives here permanently, not in a session
scratchpad (2026-07-31: the original scratchpad scripts were lost between
sessions — see the changelog entry below):**
- `retrofits/USCosts/` — REMDB source workbooks (see [Data sources](#data-sources))
- `Python/join_hp_capacity.py` — extended with `Post_HPCoolingCapacityTons`,
  `Post_HPSEER2`, `Post_HPSEER1Est` (see [Production pipeline change](#production-pipeline-change))
- `Python/retrofit_cost_extract_fields.py` — scans the raw national
  `C:\ERS\*.csv` yearly files, re-derives the same D(pre)/E(post) HOUSEID pairing
  `ers_web_pipeline.py` uses, and pulls the fields `BASE_MAPPING` doesn't carry:
  `FOOTPRINT`, `NUMWINDOWS`, `NUMDOORS`, `BASEMENTFLOORAR` (post-side geometry),
  `HPEquipType`, `NUMBEROFHEADS` (post-side, installed ASHP config — the
  **base-case** field, not `UGRHPEquipType`, which is the auditor's *proposed*
  upgrade, not what was installed), and `ACCENTESTAR`/`ACWINDNUM`/
  `ERSSPACECOOLENERGY`/`ERSDesCoolLoss` (pre-side, existing cooling for the A/C
  credit). Writes `retrofits/data/<PROVINCE>_extra_fields.parquet`.
- `Python/retrofit_cost_estimate.py` — parses REMDB's `Machine Read` sheet into a
  price table, joins the extra-fields parquet onto `ers_web_<PROVINCE>.parquet`,
  derives area proxies / window class / ASHP class / **the like-for-like BAU
  heating baseline** (see above), prices every measure at REMDB's Low/Mid/High
  bands, and writes `retrofits/data/<PROVINCE>_priced.json`.
- `Python/build_retrofit_costs_json.py` — splits each `retrofits/data/<PROV>_priced.json`
  into the `retrofit_costs_json/<PROV>/<FSA>.json` companion tree `retrofits.html`
  actually fetches — a `.gitignore`d, gh-pages-only tree, same as `fsa_json`
  (see the 2026-07-31 (8) changelog entry for the full design).
- `retrofits/data/*.parquet`, `retrofits/data/*_priced.json` — **local-only
  pipeline intermediates, `.gitignore`d, not committed anywhere.** This was
  a reasonable call at PEI scale (a few MB) but not at national scale (657MB
  for all 12 province/territory codes) — corrected 2026-07-31. Not served directly either:
  `retrofit_costs_json/` is what `retrofits.html` fetches. Regenerate by
  re-running `retrofit_cost_extract_fields.py` → `retrofit_cost_estimate.py`.
- `retrofits/review/` — the two standalone review pages, regenerated from the
  JSON above. Committed to `main` (small, ~3.4MB) but not deployed to
  gh-pages — dev/review artifacts, not linked from `retrofits.html`'s nav.

---

## Changelog

### 2026-07-31 (8) — wired into retrofits.html (proof of concept, live behind a data check)
Built the `retrofit_costs_json` companion tree and joined it into
`retrofits.html`'s FSA/province/national views. First real UI for this POC —
previously only the standalone PEI review pages existed.

- **`Python/build_retrofit_costs_json.py`** — splits each
  `retrofits/data/<PROV>_priced.json` into `retrofit_costs_json/<PROV>/
  <FSA>.json` (columnar `{columns,rows}` format, same trick
  `split_fsa_json.py` uses — dictionary-coded categoricals in a shared
  `_dictionary.json` instead of repeating string labels per home; per-home
  size dropped ~37% vs. the first, uncompressed pass), plus
  `<PROV>/_summary.json` and a national `_canada.json` rollup.
- **`Python/split_fsa_json.py`**: re-added `HOUSEID` to `KEEP_COLS` (was
  deliberately dropped for size) — the join key `retrofit_costs_json` needs
  to match a table row to its cost estimate. This forced a **full
  regeneration of the 827MB `fsa_json` tree** (not incremental — the field
  touches every row of every file). Decision (Simon): worth it, and worth
  doing now rather than deferring, but keep `retrofit_costs_json` as a
  **separate tree**, not merged into `fsa_json` — cost methodology changed 5
  times in this single session alone, all without touching ERS row data;
  merging would have forced this same 827MB rebuild on every one of those
  iterations instead of a few-minute script run.
- **`retrofits.html` / `assets/retrofits.js`**: new "Estimated retrofit
  cost" card (Low/Mid/High band toggle, total for the view, per-measure
  breakdown, median payback), two new per-house table columns (Est. cost,
  Payback), and a per-house detail-row breakdown, all tagged **"Proof of
  concept."** Fetched lazily and in parallel with the existing `fsa_json`
  fetch — a missing/unpriced province or FSA just hides the card, not an
  error. Updated the page's own "this tool cannot show retrofit cost or
  payback" disclaimer, which predated this work and was no longer accurate.
- Verified end-to-end locally (PE/C1A): totals, per-measure breakdown, band
  toggle, and per-house payback all cross-check against the underlying
  `_priced.json` figures; no regression in the existing bill-saving ($-saved)
  card, which shares `utility_rates_reference.json` but is otherwise
  unrelated code.
- **Not yet done**: `province_json`/`geo_json`/`census_json` aren't present
  in this local checkout, so province-mode UI rendering wasn't visually
  verified end-to-end (the underlying `RETRO_PROVINCE_SUMMARY` fetch was
  confirmed correct via console — the gap is a pre-existing local-data
  absence, unrelated to this work). Should be spot-checked once deployed.
  Per-house payback is computed once at the mid band only — it doesn't
  currently re-derive for the Low/High toggle (a minor, known simplification).

### 2026-07-31 (7) — electricity rate source swapped after catching a stale, "high confidence" SK rate
See the new [Utility rates (payback side)](#utility-rates-payback-side) section for full
detail. Short version: cross-checking the electricity rate source against a secondary source
(offgridsolarsystem.ca) caught Saskatchewan's rate understated ~67% (stale by over a year,
despite being flagged "high confidence" by the existing pipeline) — confirmed against
SaskPower's own published rate PDF. Decision (Simon): **switch electricity to the new source
for all 13 provinces/territories, leave natural gas on the old source** (which turned out to
have its own, more systemic staleness — every province's gas `effective_date` reads
`2024-10-01`, ~21 months stale — but no verified replacement is lined up yet, so gas is
flagged, not swapped). New script: `Python/override_electricity_rates.py`. The new source is a
third-party blog, not a primary/government source, and only SK has been independently
re-verified — **flagged for further investigation**, not treated as settled.

### 2026-07-31 (6) — full national coverage (all 10 provinces + NT and NU)
Ran the remaining 9 provinces/territories (AB, BC, MB, NB, NF, NS, NT, NU, SK)
after ON/QC validated clean. `retrofits/data/<PROV>_extra_fields.parquet` and
`<PROV>_priced.json` now exist for all 12 province/territory codes the ERS data
carries — the 10 provinces plus NT and NU. **Yukon is absent entirely**: it has no
ERS records, so there is nothing to price, and `_canada.json`'s
`provinces_included` lists 12 codes, not 13. NU is n=4 — negligible ERS coverage,
kept for completeness, not meaningfully priceable.

| Province | Paired | Priced | ASHP records | ASHP class fallback |
|---|---|---|---|---|
| ON | 691,657 | 610,284 | 83,620 | Centrally ducted |
| QC | 270,333 | 220,557 | 45,933 | Centrally ducted |
| BC | 126,103 | 105,512 | 20,262 | Centrally ducted |
| NS | 79,727 | 74,418 | 20,385 | Non-ducted, multi-zone |
| AB | 85,031 | 77,006 | 2,249 | Centrally ducted |
| NB | 66,552 | 59,058 | 18,130 | Non-ducted, multi-zone |
| SK | 48,433 | 42,569 | 236 | Centrally ducted |
| MB | 26,706 | 23,302 | 1,091 | Centrally ducted |
| PE | 12,243 | 11,589 | 1,759 | Non-ducted, multi-zone |
| NF | 12,949 | 12,550 | 5,131 | Non-ducted, multi-zone |
| NT | 306 | 268 | 2 | Centrally ducted |
| NU | 4 | 4 | 0 | Non-ducted, single-zone |
| **National** | **1,420,044** | **1,237,117** | **198,798** | — |

The ASHP class fallback split cleanly along a real housing-stock line: the
Atlantic provinces (PE, NB, NF, NS) fall back to ductless multi-zone, every
other province/territory falls back to centrally-ducted — consistent with
Atlantic Canada's older, non-forced-air housing stock (this pattern held for
all 4 Atlantic provinces independently, not just PEI, reinforcing that the
per-province computation in 2026-07-31 (5) was the right fix).

**Next (in progress, per chat 2026-07-31):** a `retrofit_costs_json/<PROV>/
<FSA>.json` companion tree (mirroring `fsa_json`'s per-FSA structure, not
merged into it) carrying full Low/Mid/High per-measure figures (not just the
mid-case total) plus a per-home payback estimate, joined into `retrofits.html`
by `HOUSEID`. Payback = incremental cost (mid) ÷ annual $ savings, the latter
computed with the same blended provincial rates
`Python/precompute_province_stats.py` already uses
(`utility_rates_reference.json`, all provinces — not the ON/QC/AB-only
`prices_json`) — computed directly in the cost pipeline rather than depending
on `retrofits.html`'s existing "$ saved" stat card, which is currently dead
markup (the `renderCost`/`renderProvinceCost` functions its own comments
reference don't exist in the file). Alberta's rates are flagged low-confidence
(deregulated market, some components are screening estimates); propane/oil/
wood rates are lower-confidence single-province averages everywhere. Decision
(Simon): show payback everywhere, flagged, rather than hide it where
confidence is lower — consistent with how the rest of this page treats
assumptions.

### 2026-07-31 (5) — validated on ON + QC; ASHP class fallback now per-province
Staged national rollout, step 1 (see 2026-07-31 (4)'s "Scale beyond PEI" open
item): generalized both scripts to run any province (`PROVINCES_TO_RUN`,
currently `['PE', 'ON', 'QC']`), with `retrofit_cost_extract_fields.py` doing
one pass over the raw CSVs for all requested provinces instead of one pass
per province. Ran ON and QC as the validation step before all 12:

- **The ASHP class fallback (`Non-ducted, single-zone` used to be hardcoded
  to PEI's own ratio) is now computed per province** from that province's own
  reported `HPEquipType` split (`province_ashp_fallback`), not reused as a
  national constant. Result confirms this was the right call to check first:
  PE's fallback is `Non-ducted, multi-zone` (74 vs 37 reported, refining an
  even earlier single-zone-only assumption), but **ON and QC both fall back
  to `Centrally ducted`** — expected, given their much larger existing
  forced-air-furnace housing stock, and the opposite of PEI's ductless-heavy
  market. Reusing PEI's constant nationally would have mispriced the
  fallback ASHP class for the majority of ON/QC's pre-2025 records.
- **BAU heating fuel mix came out exactly as regional heating-stock knowledge
  would predict** — a strong sanity check that the fuel/type-driven
  classification (not hardcoded) generalizes correctly:

  | Province | ASHP records | Dominant BAU heating | Median ASHP incremental | % negative |
  |---|---|---|---|---|
  | PE | 1,759 | Boiler/Oil (47%) | $5,296 | 7.3% |
  | ON | 83,620 | Furnaces/Gas Furnace (91%) | $9,970 | 0.0% |
  | QC | 45,933 | Electric Baseboard (50%) | $12,671 | 0.2% |

  QC's electric-baseboard dominance (Hydro-Québec's low electricity rates)
  and ON's gas-furnace dominance are both well-known regional patterns — the
  model reproduced them from `Pre_HeatFuel`/`Pre_HeatType` alone, with no
  province-specific tuning required in `classify_bau_heating`.
- 9 provinces/territories remain (AB, BC, MB, NB, NF, NS, NT, NU, SK) — add to
  `PROVINCES_TO_RUN` and re-run once reviewed.
- **Not yet done**: joining this into `retrofits.html`. Plan (discussed, not
  yet built): ship a companion `retrofit_costs_json/<PROV>/<FSA>.json` tree
  mirroring `fsa_json`'s existing per-FSA-file structure (keyed by
  `HOUSEID`), fetched lazily alongside the existing FSA fetch, adding a
  mid-case total-cost column to the per-house table (`table-card`) that
  already renders when a user picks an FSA. Deliberately not inlining a
  national JSON like the PE-only review page does — PE is ~12k paired
  records, ON alone is ~692k.

### 2026-07-31 (4) — like-for-like ASHP heating BAU; POC moved to a permanent location
The prior scratchpad scripts (`pei_retrofit_cost_poc.py`,
`pei_retrofit_cost_estimate.py`) were lost between sessions — scratchpad is
per-session and ephemeral. Rebuilt the whole pipeline as two permanent,
committed scripts (`Python/retrofit_cost_extract_fields.py`,
`Python/retrofit_cost_estimate.py` — see [Files](#files)) plus committed
outputs (`retrofits/data/`), and used the rebuild to fix the ASHP heating BAU:

- **BAU heating is now like-for-like** (the home's own `Pre_HeatType` +
  `Pre_HeatFuel`, mapped to the closest REMDB row), not a uniform gas-furnace
  assumption. Gas furnace is now only the fallback for fuel/type combinations
  REMDB genuinely has no row for (propane, wood, electric furnace). See
  [Incremental cost model](#incremental-cost-model) for the full mapping table.
- Added two **self-derived REMDB rows** (Oil Furnace, Electric Boiler) that
  REMDB's own regression never fit despite having raw line-item data for both —
  derived from the exact raw rows Simon pulled directly out of
  `Non-Envelope Measures 7-18-24.xlsx` (Thermo Pride/RSMeans oil furnaces,
  Viessmann/Argo electric boilers). Without these, 53% of PEI's ASHP records
  (the oil-furnace share) would still have fallen back to gas furnace.
- Result: **94% of PEI's 1,759 ASHP records now get a like-for-like BAU match**
  (was ~7%, 130/1,817, under the old `UGRHPEquipType`-only reported/assumed
  split — that split was about ASHP *class*, not the heating BAU, which was
  100% assumed before this fix). Median ASHP incremental cost: **$3,438** (was
  $5,227); 8.6% of records now negative (was ~0%).
- Also fixed a latent bug caught in this rebuild: REMDB's `Solar PV` row is
  priced in **$/Watt**, not a flat $ total (unlike every other REMDB row used
  here) — an early pass on this rebuild multiplied by system size everywhere
  *except* PV. Also clamped PV system-size outliers (>20 kW, clearly a
  unit/data artifact, not a residential system) out of pricing.
- Field sourcing correction: uses **base-case** `HPEquipType`/`NUMBEROFHEADS`/
  `WINDOWCODE` (via `Pre_/Post_WindowCode`, already in the web parquet) instead
  of the `UGR*`-prefixed fields the original POC read — NRCan's dictionary
  defines `UGR*` as the auditor's *proposed* upgrade case, not the installed
  equipment. (The review page had already flagged this as an open "Original vs
  Corrected" question in an earlier iteration; this rebuild settles it in favor
  of Corrected and drops the toggle — there is now one method, not two.)
- PEI, single-dwelling only: 11,589 / 12,243 paired records (95%) now have at
  least one priced measure (up from 68% in the original 5-measure run — this
  rebuild also prices air sealing, solar PV, and HRV/ERV, which the original
  [PEI POC results](#pei-poc-results) table below predates).

### 2026-07-31 (3) — incremental model implemented and re-priced
Built the incremental model into the POC and regenerated both review pages
(`retrofits/review/`). Changes:
- **Extract**: added `ACCENTESTAR` / `ACWINDNUM` / `ERSSPACECOOLENERGY` to
  `pei_extract_fields.py` (pre-existing cooling). Heating baseline uses
  `Pre_HeatLoss` (already in the parquet).
- **Windows**: `pei_price_audit.py` now decodes pane count (WINDOWCODE digit 1)
  from the base-case pre/post codes and charges `efficient(post) −
  standard(pre)` per window, priced on residential vinyl at the trimmed 1.4 m²
  rate, ×NUMWINDOWS, floored at $0. **PEI median $6,284** (was $20,459 full).
- **ASHP**: now `ASHP − gas furnace − A/C`. Gas furnace sized from
  `Pre_HeatLoss` (kW→BTU/hr) at AFUE 0.95; A/C at the ASHP's tons and *standard*
  efficiency (SEER1 13 / CEER 11 — a basic unit, not the ASHP's premium rating),
  central for ducted / room for ductless. **PEI median $5,227** (was ~$9,500
  full); no PEI record went negative.
- Insulation, air sealing, PV, HRV unchanged. Reporting/JSON now key off explicit
  `{measure}_priced` masks, not `>0`, so zero/negative increments still count.
- Methodology page: incremental banner, per-measure incremental formulas and
  derivations, and a "one component vs incremental" clarifier on the Window/ASHP
  tabs (their live calculator still illustrates component pricing). Review page:
  incremental framing note.

Verified: both pages render with no console errors, 11,274 priced homes. The
methodology-first entry below records the design that this implements.

### 2026-07-31 (2) — reframed as an incremental-cost model (methodology, since implemented)
Reworked the whole model from *full* cost to *incremental* cost (extra over
business-as-usual). Added the [Incremental cost model](#incremental-cost-model)
section. Decisions (Simon): ASHP BAU = like-for-like heating replacement **plus**
a central A/C credit (the two appliances an ASHP replaces); windows priced as
`efficient(post pane) − standard(pre pane)` per window, using REMDB's raw
`Windows Data` sheet for the standard-vs-efficient split. Insulation and air
sealing are unchanged — they have no BAU baseline, so incremental = full cost,
which is why the cavity-fill rate is now correct rather than "too low".
**Status: methodology written for review; the pricing scripts and review pages
still emit full cost and have not yet been re-run against this model.** Refined
after review:
- **Windows** — median `$/ft²` per (frame, pane, class) with the highest and
  lowest `$/ft²` dropped, re-multiplied by the default 1.4 m² window. Triple-pane
  priced by pooling all triple-pane rows for the frame (triple = efficient by
  construction) then trimming. Increments: double→double ≈ $449/window,
  double→triple ≈ $1,326/window.
- **ASHP heating BAU** — simplified to a **new natural-gas furnace for every
  ASHP** (sized from `Pre_HeatLoss`), instead of per-type replacement; sidesteps
  REMDB's missing oil/electric/wood rows.
- **A/C credit** — data-driven from `ACCENTESTAR` / `ACWINDNUM` /
  `ERSSPACECOOLENERGY` (central vs room vs none).
No open methodology items remain; next step is implementation (re-pricing).

### 2026-07-31 — review fixes: phantom windows, multi-unit exclusion, cavity-fill labeling, plain-text formulas
Review of the PEI results (Simon) surfaced four things, all now fixed in the
POC scripts and the two review pages (`retrofits/review/`):

- **Windows were priced when nothing changed.** The pipeline sets
  `Windows_Change` by comparing `WINDOWCODE` as *raw text*, so an identical code
  stored once as `201030.0` and once as `201030` reads as a change. **254 of
  1,172 PEI window "changes" (22%) are this formatting artifact** — HOUSEID
  920329 (the highest-cost record) was exactly this. The POC now normalizes the
  numeric code and prices only a real difference (918 real changes on PEI). Fixed
  **POC-side only** (`pei_price_audit.py`); the pipeline flag at
  `ers_web_pipeline.py:591` is a separate follow-up — it also affects the
  Retrofit Explorer's window-change display.
- **The 72-window outlier was not a data error.** HOUSEID 920329 is an
  **Apartment** (1,400 m², foundation `B1..B8;P1..P8`) — 72 windows is real for
  a multi-unit building. The problem is pricing a whole apartment block with
  single-family per-window/per-ft² curves. **Multi-dwelling building types
  (Apartment, Apartment Row, Detached/Attached Duplex & Triplex — 311 PEI
  records) are now excluded from costing**, since their ERS record describes the
  whole building, not one dwelling. Single-dwelling forms (row-house units,
  semi/double-detached) are kept.
- **Wall & basement costs read as too low** because REMDB's
  `Wood/Steel Stud / Batt` and `Unfinished Basement (Wall) / Batt` rows (~$1.5/ft²)
  are **bare cavity-fill insulation rates** — no scaffolding, sheathing
  removal/replacement, cladding, framing, finish or moisture work. This is now
  labeled prominently on the methodology page (a hard "cavity fill only" chip on
  both measures): the figure is a floor, not a full-job cost. REMDB has no
  exterior-over-clad line at all.
- **Methodology page now shows each measure's cost formula in plain words**
  (a "the formula, in words" box in stage 4) when a measure is selected, above
  the numeric worked example.

Number shifts on PEI (mid case, vs the pre-fix run): windows priced 1,172 → 892;
wall 1,016 → 966; foundation 4,355 → 4,253; roof 4,883 → 4,751; ASHP 1,817 →
1,759. Note the review pages now also price air sealing, solar PV and HRV/ERV
(added since the [PEI POC results](#pei-poc-results) table below, which reflects
the original five-measure run).

### 2026-07-30 (2) — area-basis audit, window frame classification
- Confirmed each priced measure's "$/sqft" area basis directly from REMDB's
  raw data sheets (not just the guidance doc's two examples): air sealing =
  whole-house floor area, windows = the window's own area, wall/roof =
  wall/ceiling surface area. All match the existing ERS-side proxies.
- Confirmed REMDB has a real, unused `Air Sealing` regression (driven by
  measured leakage reduction) — flagged as the clearest next measure to add,
  since it needs no new geometric proxy.
- Checked the NRCan open-data dictionary for a wall-construction-type field:
  confirmed none exists (`WALLDEF`/`UGRWALLDEF` are text descriptions only).
  Wood/Steel Stud + Batt remains a stated assumption, not resolvable from the
  public ERS extract.
- Added window frame-material classification: `UGRWINDOWCODE`'s frame digit,
  decoded via `Support.xlsx`'s `Frame` sheet, mapped to REMDB's `Vinyl`/`Metal`
  classes (Wood-frame codes fall back to Vinyl, tagged
  `WindowClassSource='assumed_default'`). Wired into both scratchpad scripts
  and re-run: 966/1,172 (82%) PEI window-change records now get a reported
  class instead of a blanket Vinyl guess; cost impact was small (~6%).

### 2026-07-30 — proof of concept (PEI)
- Reviewed `retrofits/USCosts/` (REMDB) and confirmed it's a US 2023-USD dataset with
  no direct Canadian equivalent committed elsewhere in the repo.
- Confirmed, against the raw ERS CSV headers, that no per-component envelope area
  exists in the public NRCan extract at any level (not a pipeline gap, a source gap).
- Built rectangle-footprint area proxies (roof, wall, foundation wall, window, door)
  and priced roof/wall/foundation insulation + windows against REMDB.
- Checked `lookup/ahri_numbers.json` and found `cooling_capacity_btuh`/`seer2` already
  present; extended `Python/join_hp_capacity.py` to surface them (production change,
  rerun across all 12 province/territory codes) and added ASHP costing, including a
  ducted-vs-ductless classification with an explicit reported/assumed-default split.
- PEI POC: 8,535 / 12,554 paired records (68%) now have at least one priced measure.
