# Methodology — Heat Pump Explorer

What the tool does, where every number comes from, and what is assumed rather
than measured. Structured to follow the calculation itself, in the order the
page presents it.

Companion documents: [../docs/HEATPUMP.md](../docs/HEATPUMP.md) (what the tool
is, and who it is for) · [../ROADMAP.md](../ROADMAP.md) (decisions, with dates).

---

## 1. Scope and architecture

An hour-by-hour simulation of switching a Canadian home from its existing
heating system to an air-source heat pump: 8,760 hours of one year, run in the
browser, for **14 cities**.

It is a **screening tool**. It is useful for direction and rough magnitude, and
it is not a substitute for a heat-loss assessment or a contractor's quote.

The architecture is fixed: an offline Python pipeline writes compact JSON, and
one self-contained HTML page reads it. No backend, no build step, no runtime
dependencies.

| Stage | Location |
|---|---|
| Fetch and build | `pipeline/*.py` |
| Generated data | `data/processed/*.json` |
| Page | `../heatpump.html` |
| Engine | `app/engine.js`, mirrored for tests by `pipeline/validate_engine.py` |

The engine is a single dependency-free pure function, `simulate(opts)`, with no
DOM access and no imports, so the same file runs in Node and in the browser. The
page inlines a copy; the two are kept identical.

Outputs are split into a **base case** (the existing system) and a **project
case** (heat pump, with backup), reported as annual and monthly energy by source
and GHG by category.

---

## 2. Weather

### Typical year

**Source:** [ECCC CWEC2020](https://collaboration.cmc.ec.gc.ca/cmc/climate/Engineer_Climate/CWEC_FMCCE/CWEC_FMCCE_v_2020/)
(Canadian Weather Year for Energy Calculation), one weather-station record per
city. Fetched by `pipeline/fetch_tmy.py`; `build_tmy_temps.py` writes
`data/processed/tmy_temps.json`.

Each station file is a typical year: 8,760 hours built by splicing twelve
typical meteorological months chosen from a multi-decade record. Dry-bulb
temperature is stored in 0.1 °C and converted on parse.

### Historical years

**Source:** ECCC MSC Datamart hourly observations
(`https://dd.weather.gc.ca/today/climate/observations/hourly/csv/<PROV>/`),
same stations, fetched by `pipeline/fetch_weather.py` for 2019 onward. The
deeper record is **CWEEDS 2020**, the hourly station series for 1998–2017 from
the same CMC tree, with climate IDs matching CWEC exactly.

`build_weather_years.py` combines them into one lazily-loaded
`data/processed/weather_<city>.json` per city, keeping the newest 24 years and
quantizing temperature to tenths of a degree. **2018 falls between the two
sources and is left as a gap** (`years_missing`), not interpolated.

Every complete year (≥ 8,000 hours) carries its heating degree-days, minimum
and mean, and is tagged **typical-like** (HDD18 closest to the TMY), **coldest**
(highest HDD18) or **mildest** (lowest HDD18) for the weather-year selector.
Running the simulation across all stored years produces the cross-year emissions
band shown on the page.

### Design temperature

The **2.5th-percentile January dry-bulb**, computed over the full ~24-year
record, per station. Used to convert the user's design heat load into a UA (§3).

Computed values track NBC 2020 Appendix C, Table C-2 closely — Ottawa −24.0 vs
NBC −24, Toronto −18.0 vs −18, Montreal −22.8 vs −23, Winnipeg −31.2 vs −31,
Quebec City −25.4 vs −25, Windsor −15.2 vs −16. **Calgary is the exception at
−27.1 vs NBC −30**, which is consistent with its chinook-driven variability.
Each `weather_<city>.json` carries both the computed value and the published NBC
2.5 % and 1 % figures; the page shows the NBC values as reference overlays.

`city_design_temps.json` holds the house-weighted design temperature per city,
joined from HOT2000 weather-station records across 84 cities and 1,020,246
homes. This is the value the load calculation uses.

---

## 3. Heat load

Two user inputs drive this step directly. There is no house-type dropdown
choosing them.

| Input | Meaning |
|---|---|
| **Design heat load** (kW) | What the home needs on the city's coldest design day |
| **Zero-heat temperature** (°C) | The outdoor temperature above which no heat is needed |

```
UA_W_per_K = design_load_kW × 1000 ÷ (zero_heat_temp − city_design_temp)
Load_kW(h) = UA_W_per_K / 1000 × max(0, zero_heat_temp − T_outdoor(h))
```

Domestic hot water is excluded.

**The model has no separate term for internal or solar gains.** The zero-heat
temperature stands in for them: a real house stops needing heat above some
temperature precisely because occupants, appliances and sun make up the
difference. This makes it an *effective* balance point, not a physical
measurement.

**Why the design load is a user input.** It is the single most consequential
number in the simulation, and deriving it from a house-type archetype hid that
behind a label — the archetype choice was silently setting the answer. It is now
explicit and adjustable. `archetypes.json` still supplies four vintage medians
per city as an on-screen reference for calibration, but does not drive the
slider.

**Design heat loss is not adjusted for gains, and should not be.** `EGHDESHTLOSS`
in the EnerGuide data is a CSA F280 design heat loss, and F280 deliberately takes
no credit for solar or internal gains when sizing. Gains belong in the annual
energy calculation, not in the design load.

### Real-homes explorer

Every ERS-audited home in the selected city, pre-retrofit — up to ~290,000 homes
per city, the full set rather than a sample. Built by
`build_city_house_profiles.py` into `house_profiles_<city>.json`.

| Quantity | ERS field | Notes |
|---|---|---|
| Peak load | `EGHDESHTLOSS` | Design heat loss at the city's design temperature, taken from the audit |
| Energy consumed | `EGHFURNACEAEC` | Fuel or electricity used by the heating system — not heat delivered |
| Seasonal efficiency | `EGHFURSEASEFF` | AFUE-style percentage; above 100 % for a heat pump |
| Heat delivered | — | `consumed × efficiency ÷ 100` |

Homes with a seasonal efficiency outside 30–400 % are excluded, and the count is
reported per city rather than dropped silently.

Each home's balance point is **solved, not measured**: UA is fixed from
`EGHDESHTLOSS ÷ (21 °C − city design temp)` — 21 °C being HOT2000's indoor design
setpoint, the temperature `EGHDESHTLOSS` is computed at — and the balance point
is then the one unknown chosen so that integrating the load line over a full TMY
year reproduces that home's own delivered annual energy. Because gains are
excluded by construction, this absorbs real gains, occupant behaviour and
TMY-versus-actual-year weather into a single number.

"Worst" and "best" are the 99th and 1st percentile of a combined peak-load and
delivered-energy ranking within the filtered set, not the literal extremes, so a
single mis-keyed audit row cannot stretch the display. "Average" is the
arithmetic mean of the filtered set, not any real home.

---

## 4. Heat pump performance

The user picks a **performance tier** and a **capacity band**. That pair pins
exactly one of **nine real, individually AHRI-certified units** — no scaling, no
averaging, no interpolation between models. The simulation runs that unit's own
published capacity and COP curve.

### Sampling frame

Every AHRI-certified reference number appearing in Canada's EnerGuide/ERS
audit records: **439,975 record appearances across 15,148 distinct certified
models**. Counts are record appearances, not installed units — a home audited
twice counts twice, and retrofit and new-construction records are pooled.

### Data sources, and which one wins

| Source | Role |
|---|---|
| EnerGuide/ERS audit records | Selection weights (appearance counts) |
| AHRI Directory | Certified ratings used for bucketing — **authoritative** |
| NRCan Searchable Product List | HSPF2 Region V, ccASHP grouping, Canadian eligibility — **fills gaps only, never overrides** |
| ENERGY STAR | Compressor staging, market, vintage — **attributes only** |
| Manufacturer datasheets | Performance curves |
| NEEP ccASHP listing | Performance-curve fallback, cited per model |

The precedence is not arbitrary. **ENERGY STAR carries no independent
performance data**: across 3,447 models present in both it and the AHRI scrape,
5 °F capacity agrees within 2 % on 100 % of rows — it republishes AHRI figures.
**NRCan agrees closely but not perfectly**: across 4,435 models carrying capacity
maintenance from both, the median absolute difference is 0.5 pp, but 17.0 %
differ by more than 2 pp. So AHRI governs, and NRCan is used to fill models AHRI
does not cover (+448 models, +23,615 appearances).

**Bucket assignment is scrape-date dependent.** AHRI amends certificates
retroactively — one unit's cold-climate designation was confirmed flipping from
No to Yes on 2026-07-22. Entries carry a `_checked` date.

### Implausible ratings are screened, not dropped

Certificates carrying a COP at 5 °F above 3.0, or a capacity maintenance above
1.30, are flagged and excluded from selection rather than silently kept or
silently removed. Both populations are small and real: 6 models / 1,975
appearances above the COP threshold, 21 models / 3,040 appearances above the
capacity-maintenance threshold.

### Tiering metric

**Capacity maintenance = capacity at 5 °F ÷ capacity at 47 °F.** This is not an
invented metric: it is the ratio ENERGY STAR v6.2, CEE and NRCan's Greener Homes
ccASHP criterion all use, the last stating it as
`(Max −15 °C) / (Rated 8.3 °C) ≥ 70 %`.

COP at 5 °F is the secondary axis. It is a poor primary ranking metric because
1.75 is the shared certification floor across ENERGY STAR, CEE and NEEP, and a
majority of records report exactly 1.80 — the distribution piles up against its
own floor.

**The rating basis is mixed, deliberately.** The 5 °F rating is at *maximum*
capacity; 47 °F and 17 °F are *rated* points. This is why a large share of models
report a 5 °F capacity above their 17 °F capacity: correct and expected, not a
data error. Filtering for monotonicity would discard roughly 180,000 appearances
of valid data. The fitted capacity curve is therefore a **maximum-capacity
envelope** below about 17 °C, which is how the engine consumes it.

### The 3 × 3 grid

**No cut point enters the simulation.** The tier and band boundaries classify
the installed base for the selection scatter and label the dropdowns; the
calculation runs on whichever of the nine units the dropdown pins, using that
unit's own curve. Changing a boundary would re-label the picture, not change any
result.

The boundaries shown on the scatter are **terciles of the install-weighted
distribution**, computed from the data rather than fixed by hand:

| Axis | Tercile cut points (as shipped) |
|---|---|
| COP at 5 °F | 1.80 / 1.91 |
| Capacity maintenance | 0.727 / 0.883 |

Capacity bands are < 18k / 18–30k / 30–42k Btu/h.

**The COP axis cannot support terciles, and this is a property of the data, not
of the method.** Install-weighted, **41.9 % of the base reports a COP at 5 °F of
exactly 1.80**, and only **4.6 % falls below it** — the certification floor of
1.75 and the reporting convention pile the distribution onto a single value. A
"bottom third" on this axis does not exist: the tercile algorithm puts its lower
boundary exactly on the spike, leaving 4.6 % below and 58.6 % in the middle band.
Capacity maintenance, by contrast, splits cleanly at 32.0 / 34.4 / 33.6 %.

This is why capacity maintenance is the primary metric and COP at 5 °F is
reported as an attribute of each unit rather than used to rank them.

**A third of the sampling frame cannot be placed on the grid at all.** Of
439,975 record appearances, **298,209 (67.8 %) carry the certified points the
grid needs**; the rest are missing a 5 °F capacity, a 5 °F COP or a rated 47 °F
capacity. That population is not a residue: 99 % of it is discontinued or
delisted equipment predating the rating, none flagged cold-climate, none on
current refrigerants. It is excluded and counted on the page's own scatter gate,
not hidden.

### The nine units

For each cell we work down the list of most-installed certified models and take
the **first one whose manufacturer publishes a usable performance table**. Where
the most-installed unit has no readable spec sheet, the next most-installed is
used, and so on. The per-cell `rank` field in `hp_cell_curves.json` records which
units were passed over and why.

That constraint is real and sometimes binding: it is why two cells rest on units
with a few hundred appearances while a neighbouring cell rests on one with
11,555.

| Cell | Unit | AHRI | ERS appearances | Lockout °C | Rated 47 °F Btu/h |
|---|---|---|---:|---:|---:|
| low `<18k` | GE Appliances ASH112PRDWA | 202588311 | 846 | −26.1 | 12,000 |
| low `18-30k` | Tosot TUD24W2/D-D(U) | 211078853 | 122 | −15.0 | 23,000 |
| low `30-42k` | Tosot TUD36W2/D-D(U) | 211078855 | 156 | −15.0 | 34,000 |
| mid `<18k` | GE Appliances ASH115PRDWA | 202588312 | 868 | −26.1 | 13,600 |
| mid `18-30k` | GREE GUD36W/A-D(U), 24k pairing | 206249116 | 2,253 | −30.0 | 24,000 |
| mid `30-42k` | GREE GUD36W/A-D(U) | 211644151 | 11,555 | −30.0 | 36,000 |
| high `<18k` | Fujitsu AOUG15LZAH1 | 206597213 | 1,918 | −26.1 | 14,500 |
| high `18-30k` | Moovair DMA24HOS20230E7 | 212361759 | 4,206 | −30.0 | 25,000 |
| high `30-42k` | Fujitsu AOUG36LMAS1 | 205123809 | 1,795 | −20.6 | 36,000 |

> **Provisional — under review.** The unit selection is temporary and pending a
> review. In the 18–30k band the tier labels do not match the units' specs: the
> Moovair DMA24HOS20230E7 sits in **Premium** with a capacity maintenance of
> 0.800, below the **Mid-Range** GREE GUD36W/A-D(U) at 0.917. The other seven
> cells are correctly ordered.

### Curve construction

Built by `pipeline/build_cell_curves.py` on a −30 … +20 °C grid at 0.5 °C steps,
at maximum heating output — the condition a cold home calling for full heat
actually creates.

- **Between published points:** linear interpolation.
- **Below the coldest published point, down to lockout:** capacity extrapolated
  linearly and floored at zero; COP floored at the coldest published COP minus
  0.3.
- **Above the warmest published point:** held flat to 20 °C. This is a
  placeholder, not a claim about performance.
- **Normalization:** capacity is expressed as a fraction of the unit's
  **AHRI-certified** rated 47 °F capacity, not the datasheet's own 47 °F reading.
  The two can differ; the certificate governs.
- **Lockout:** eight of nine cells carry a real manufacturer-datasheet minimum
  operating temperature. The ninth, `mid_18-30k`, uses a documented −20 °C
  assumption clamped to that unit's coldest tested point (−20.6 °C) rather than a
  silent default.
- **Defrost:** a 7 % COP derate across −7 … +4 °C, applied as a continuous
  multiplicative factor with 1 °C ramps so the curve stays continuous. This is a
  single default figure, not a per-model measurement.

**Where the curve points come from.** Each unit's own published manufacturer
datasheet (submittal or product data), cited per cell in the `source` field —
AHRI publishes capacity at three temperatures and COP at only one, which is not
enough points to simulate a season. Where no datasheet table exists for a unit,
its **NEEP cold-climate listing** is used instead and cited for that model.

**Cross-check.** The page carries a per-unit table comparing the digitized curve
against the AHRI certificate and against NEEP's republication of the same
certificate's Min/Rated/Max tables, for heating and cooling, at every whole
degree either source publishes. Its purpose is to make a column mix-up visible
rather than silent. NEEP values were pulled by browsing the rendered product
pages.

### Screen against the US DOE Cold Climate Challenge

A separate screen of the whole installed base against the **US DOE Cold Climate
Heat Pump Technology Challenge** specifications (Table II-3), built by
`pipeline/screen_cchp.py`. It answers a different question from the tiering: not
"what do Canadians install", but "how much of what Canadians install would clear
the frontier specification". Results are surfaced on
[retrofit-insights.html](../retrofit-insights.html), not on this page.

**It is a screen against published certificate ratings, not a certification.**
The Challenge is a verification programme with its own laboratory test protocol;
we hold AHRI certificate figures. A unit passing here has *rating-consistent*
performance and nothing more. The output column is named `screen_pass`, and the
honest wording is "screened against the DOE Challenge specifications" — never
"meets the DOE Challenge".

**Four of roughly eight criteria are checkable** from the ratings we hold. The
rest — turndown ratio, compressor cut-out/cut-in, electric heat staging, the
ENERGY STAR CACHP clauses — are recorded as `not_checkable` columns rather than
quietly ignored.

Against all 439,975 appearances:

| Verdict | Models | Appearances | % |
|---|---:|---:|---:|
| `screen_pass` | 4 | 8 | 0.00 % |
| `near` (one gate failed) | 671 | 8,975 | 2.04 % |
| `fail` | 4,644 | 194,294 | 44.16 % |
| `out_of_scope` (< 24,000 Btu/h) | 3,866 | 151,496 | 34.43 % |
| `unknown` (a needed rating absent) | 5,963 | 85,202 | 19.37 % |

**The qualifying set is knife-edge, not merely small.** Three of the four report
COP 2.10 against a 2.1 threshold and a capacity ratio of 1.0000 against 100 %.
That is design-to-spec, not coincidence, and it means a routine certificate
revision could move a unit across the line. None of the four is a cell
representative in the 3 × 3 grid.

The grid describes the *installed* base, which is a historical record. This
screen is the reminder that it is not evidence about what today's best equipment
can do.

### Cooling

The same nine units' cooling curves, where the datasheet publishes them, plus a
standard-AC counterfactual from `ac_curves.json`. Cooling capacity is not
clamped at a ceiling: where demand exceeds what the unit can deliver, the
shortfall is **flagged rather than silently capped**.

SEER/SEER2 badges do not predict TMY-integrated real-world performance in this
data, and the tool does not use them as a performance input.

### Sizing sweep

A 40–160 % sweep of the selected cell's own capacity curve, shown as a
sensitivity band. It is a **synthetic rescaling for sensitivity analysis, not a
menu of purchasable sizes** — real units come only in the nine discrete cells,
and the card says so.

---

## 5. Backup and switch-over

The baseline system is assumed to cover 100 % of the load on its own, with no
part-load derating or cycling losses. Its efficiency defaults to a typical value
for the chosen fuel and is adjustable:

| Fuel | Default | Range | Roughly |
|---|---:|---:|---|
| Natural gas | 80 % | 70–98 % | 80 % older standard-efficiency · 95–98 % newest condensing |
| Oil | 83 % | 60–90 % | 83 % typical in-service · 90 % newer high-efficiency |
| Propane | 90 % | 75–96 % | 90 % mid-efficiency · 96 % newest condensing |
| Electric baseboard | 100 % | 95–100 % | Resistance heating |

The backup dispatch strategy is **derived from the backup type**, not chosen
separately:

- **Electric backup** → `load-exceeds-capacity`. The heat pump runs whenever it
  is above its minimum operating temperature and delivers `min(load, capacity)`;
  resistance heat tops up any shortfall.
- **Gas, oil or propane backup** → `lockout`. Below a user-set **switch-over
  temperature** the heat pump is switched off entirely, regardless of the
  capacity it could still deliver, and the whole load goes to the furnace.

The switch-over temperature can be set warmer than the unit's lockout. It cannot
usefully be set colder: below the unit's own lockout the heat pump cannot run
regardless.

**Below the published minimum operating temperature.** The manufacturer's
minimum is a warranty and ratings boundary, not a hard physical stop, so the
engine offers two behaviours:

- `hard` (default): the compressor stops, and load falls to backup or goes unmet.
- `derate`: the unit keeps running, with capacity extrapolated on the coldest
  defined segment's slope and **COP held flat at its floor**. If the capacity
  extrapolation reaches zero it reverts to a hard stop.

Real below-lockout behaviour is manufacturer-unspecified — no datasheet publishes
it — so `derate` is labelled an assumption in the UI and its hours are counted
separately. It never fires in the default mode.

**Cycling below minimum capacity is not modelled.** Only the maximum-compressor
curve exists, so a modulating inverter is costed at its max-speed COP. Real
part-load COP is usually higher, making this conservative.

---

## 6. Emissions

GHG is split into four categories: **combustion, electricity, refrigerant and
upstream methane**, in kg CO₂e/yr.

### 6.1 Combustion factors

Direct combustion factors in g CO₂e per kWh of fuel input, HHV basis to match
the efficiency convention. Each is **derived in code** from the volumetric factor
and the energy content rather than hardcoded, so the two cannot disagree, and the
energy contents are shared with the retrofit pipeline.

| Fuel | g CO₂e/kWh | Basis (CO₂ + CH₄ + N₂O, residential rows, ECCC NIR) |
|---|---:|---|
| Natural gas | 185.41 | (1921 + 0.072) g CO₂e/m³ ÷ 10.3611 kWh/m³ |
| Light fuel oil (No. 2) | 255.44 | (2753 + 0.026 + 0.006) g CO₂e/L ÷ 10.7778 kWh/L |
| Propane | 213.65 | (1515 + 0.027 + 0.108) g CO₂e/L ÷ 7.0917 kWh/L |
| Electricity | 0 | grid EF only |

### 6.2 Grid emissions: three bases

| Basis | What it answers |
|---|---|
| **Marginal** (default, ON/AB) | What does *new* load emit — the generator the grid ramps to meet it |
| **Hourly average** (ON/AB) | The whole generation mix that hour, temperature × hour × season |
| **ECCC yearly** (all provinces) | The province's flat published inventory average |

Quebec is served on the **ECCC yearly basis only**. Its thermal generation is
under 0.01 % of the grid, so an hourly average or marginal basis carries no
meaningful signal, and both understate the province against the published
inventory average of roughly 1.3 g/kWh. The other two options are disabled for
Quebec cities, with the reason shown in the UI.

Provinces with no hourly pipeline (BC, MB, SK, NS, NB, NL, PE) use the ECCC
yearly basis plus a flat marginal screening estimate.

### 6.3 Ontario

**Source.** [IESO — Generator Output by Fuel Type Hourly Report](https://reports-public.ieso.ca/public/GenOutputbyFuelHourly/),
one XML file per year (`PUB_GenOutputbyFuelHourly_<year>.xml`), province-wide
hourly output aggregated by fuel: nuclear, gas, hydro, wind, solar, biofuel,
other. Continuous from 2020-01-01 to the present. `pipeline/fetch_ieso.py`
downloads to `data/raw/ieso/`; the parse writes
`data/interim/ieso_hourly_by_fuel.csv` (Date, Hour, Fuel, Output_MW).

The report covers generators connected to the IESO-administered market;
behind-the-meter and small embedded generators (historically under 20 MW) are
outside it. Imports and exports are not included, so this is a production-based
intensity for Ontario generation, not a consumption-based intensity for Ontario
demand.

**Emission factor model.** Direct combustion emissions only — upstream methane
and grid losses are applied separately (see *Lifecycle emissions*). Nuclear,
hydro, wind, solar, biofuel and other are treated as zero direct emissions, and
all direct grid emissions are attributed to natural gas:

```
AvgEF(hour)      = GasFraction(hour) × GasEF(year)
MarginalEF(hour) = GasEF(year)  when gas output > 0, else AvgEF(hour)
```

Gas output is nonzero in nearly every hour of the record, so `MarginalEF` is
close to a flat `GasEF(year)` throughout. The Atmospheric Fund (TAF) uses the
same attribution in its published Ontario factors.

**Gas emission factor.** TAF publishes the NIR-derived natural gas intensity
directly, so it is used as published rather than inferred: *Ontario Electricity
Emissions Factors and Guidelines* (2025 edition) data tables, sheet 10
"Natural Gas Consumption Intensity". Values for 2015–2023 are NIR-derived; TAF
estimates 2024–2025 as the mean of 2022 and 2023.

Those published values are **consumption-side** — TAF's sheet title states they
include transmission and distribution losses. The engine applies line losses
itself (7.4 % for Ontario), so `grid_common.on_gas_ef()` divides by 1.074 to
give a generation-side factor:

| Year | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 |
|---|---|---|---|---|---|---|
| TAF published, incl. T&D | 514 | 482 | 459 | 442 | 451 | 451 |
| Generation-side, ÷ 1.074 | 478.6 | 448.8 | 427.4 | 411.5 | 419.9 | 419.9 |

*Assumed, not published:* TAF does not state the loss rate behind its own
figures. The divisor is set equal to the rate the engine re-applies, so the two
cancel and the tool reproduces TAF's published consumption-side intensity
exactly. The factor reported on its own — on the grid dashboard, or here with
upstream losses switched off — does move with this choice: at 5 % the 2024
factor would read 430 rather than 420 g/kWh. Years past the published table
carry the last value forward; TAF's 2026+ forecast series projects a future
plant mix and is not used for observed generation.

**Validation.** Generation-weighted annual average from the hourly series,
scaled back to TAF's consumption-side scope, against TAF's published Annual
Average Emissions Factor (sheet 1):

| Year | Computed (gen-side) | × 1.074 | TAF published | Δ |
|---|---|---|---|---|
| 2020 | 32.8 | 35.2 | 35 | +0.6 % |
| 2021 | 39.8 | 42.7 | 43 | −0.6 % |
| 2022 | 46.0 | 49.4 | 49 | +0.9 % |
| 2023 | 54.9 | 58.9 | 59 | −0.1 % |
| 2024 | 68.3 | 73.3 | 73 | +0.4 % |

Tolerance is ±15 %; all five years land inside ±1 %. TAF's table stops at 2024.

An independent check comes from the third emissions basis, which reaches
Ontario by a different route entirely — ECCC inventory emissions over StatCan
utility generation, using neither IESO data nor TAF as an intermediate. For
2023 it gives 56.4 g/kWh against this pipeline's 54.9: a 2.7 % gap between two
methods that share no inputs.

**Output.** `build_grid_ef.py` → `data/processed/grid_ef_on.json`, the full
hourly average and marginal series (~6 MB). This is a pipeline intermediate;
the browser loads the binned surface built from it (see *Grid EF surface*).

### 6.4 Alberta

**Source.** AESO — CSD Generation (Hourly), historical dataset, downloaded by
hand as ~6-month zips into `data/raw/aeso/` and parsed by `pipeline/fetch_aeso.py`.
AESO's historical dataset is Box-hosted with no scriptable direct-download URL,
so this step is manual by necessity and Alberta's coverage lags Ontario's.

**Emission factor model.** Direct combustion only. Hydro, wind, solar, other and
storage are zero. `DUAL FUEL` — transitional coal units converted to co-fire or
burn gas — is grouped with gas, since those units are mostly or entirely
gas-fired by the time they carry the tag.

```
AvgEF(hour)      = CoalFrac(hour) × COAL_EF + GasLikeFrac(hour) × GAS_EF
MarginalEF(hour) = GAS_EF  when gas-like output > 0, else AvgEF(hour)
```

**COAL_EF = 1050, GAS_EF = 540 g CO₂e/kWh**, fitted by least squares against
Alberta's published grid intensity for 2019–2023.

> **Known stale, as of 2026-09-09.** Those constants were fitted against
> Alberta's published series as it stood at the time (630 / 630 / 580 / 510 /
> 470 for 2019–2023). Alberta has since revised and extended that series from
> the 2026 National Inventory Report to **629 / 578 / 506 / 459 / 420, plus 335
> for 2024** — every year after 2019 revised down by around 10 %. Refitting
> against the current series gives COAL_EF ≈ 1200 and GAS_EF ≈ 427. The
> constants have deliberately **not** been changed pending a decision, and
> `build_grid_ef_annual.py`'s validation printout still compares against the
> superseded 470 for 2023. Treat Alberta's absolute intensity as roughly
> 10–15 % high until this is resolved.

**Coal on the margin.** Alberta had substantial coal generation through about
2021 — up to half of generation in 2015 — and coal, not only gas, may have set
the margin in some pre-2022 hours. The "gas is always marginal" simplification is
well justified for 2022 onward, where coal is under 12 % of generation, and less
so before that.

### 6.5 Quebec

**Source.** Hydro-Québec hourly generation by source, manually placed in
`data/raw/hq/` and parsed by `pipeline/fetch_hq.py`. Thermal generation — small
remote and off-grid diesel and gas serving communities not connected to the main
hydro grid — is between 0.0007 % and 0.005 % of total generation in every year
with data.

Two known gaps in the source file, neither imputed: **2021 is entirely missing**
(and the first three weeks of January 2022), and **7,307 rows carry a blank date
field** in three contiguous blocks that cannot be assigned real timestamps. The
blank-date rows are dropped and the count is reported on every run.

**The tool does not use this hourly series.** Quebec is served on the ECCC yearly
basis (§6.2). The hourly pipeline and its `THERMAL_EF_G_PER_KWH` of 700 g/kWh —
an assumed figure for small diesel generation, never independently calibrated —
are retained as a record, and their magnitude cannot matter: at under 0.01 %
share, doubling the constant moves the annual average by hundredths of a g/kWh.

The gap this leaves is worth stating plainly. Quebec's **marginal** intensity is
not modelled. New winter load in Quebec may in practice be served by imports of
higher-carbon power rather than by curtailing zero-carbon hydro, which would put
the marginal figure far above the production-based average. Modelling that needs
hourly intertie flow data the tool does not have.

### 6.6 The hourly surface: temperature × hour × season

Grid intensity is not a function of temperature alone — hour-of-day, season and
outages all move it. Binning by temperature alone and applying a typical year
would smear morning-peak gas hours into mild afternoons. So `build_ef_surface.py`
bins the hourly EF by **temperature (2 °C bins) × hour-of-day (1–24) × season
(DJF/MAM/JJA/SON)** over the full overlapping record.

**Shape × level.** The provincial grids are not stationary: Ontario's average EF
rose from about 31 to about 81 g/kWh between 2020 and 2025 as gas generation
grew; Alberta's fell from about 650 to about 414 as coal retired. That drift is a
fleet and policy effect, not a weather effect, so each hourly EF is decomposed as

```
EF(hour) = annual_level(year) × shape(temp, hour, season)
```

Pooling absolute EF instead reconstructs the multi-year mean correctly but cannot
reproduce any individual year — an early attempt gave an overall error of −0.1 %
with per-year errors up to +96 %. Each file stores the shape cells, every
calendar year's level, and a `reference_level` set to the most recent complete
year (2025), which the engine treats as the current grid. Any stored year's level
can be swapped in to draw the historical band.

**Province versus city temperature.** The grid EF is province-wide, so each
surface is keyed on one proxy city's temperature — ON on London, AB on Calgary.
The proxy cannot select a different fuel mix, only whose temperature time-aligns
the bins against province-wide demand. Ontario was originally keyed on Toronto,
whose 2020–2026 record only reaches −22.6 °C, so the coldest bins were empty and
design-load temperatures fell through to the flat global mean. London tracks
province-wide gas output essentially as tightly (winter correlation −0.420 versus
−0.419) while reaching −24.8 °C.

**Thin-bin fallback.** Tails are thin, so the surface stores progressively coarser
aggregates and `lookup_shape()` takes the first whose cell has **at least 20
hours**:

```
fine  →  coarse_ts (temp × season)  →  coarse_t (temp)  →  global
```

Every cell carries its hour count, so the rule is explicit and reproducible.
Worked example on the current Ontario surface: winter, 19h, −18 °C has only 2
hours in the fine cell, so it falls back to the coarse_ts cell (155 hours, ratio
1.6042), giving 1.6042 × 81.387 ≈ **131 g/kWh** on the 2025 reference level.

Below the coldest bin that clears the threshold, the engine fits a least-squares
line through the tail's six most extreme sufficiently-sampled bins and extends it,
floored at zero. A two-point edge slope was tried and rejected: the outermost bin
has the fewest hours of any that clears the threshold, so one point's sampling
noise can flip the extrapolated direction.

### 6.7 The ECCC yearly basis

A single flat published annual-average intensity per province, built by
`build_grid_ef_annual.py`. It is the only basis available for provinces with no
hourly pipeline, and for Ontario and Alberta it is an official-inventory
alternative computed by a genuinely independent route.

Both inputs come from the **StatCan Web Data Service** full-table CSV endpoint
(`canada.ca` and `open.canada.ca`'s CKAN API are both WAF-blocked here; StatCan
WDS is not):

- **Numerator** — StatCan **38-10-0097**, *Physical flow account for GHG
  emissions*, sector *Electric power generation, transmission and distribution
  [BS22110]* — ECCC National Inventory Report data carried in StatCan's
  environmental-economic accounts, kt CO₂e by province.
- **Denominator** — StatCan **25-10-0015**, *Electric power generation, monthly
  generation by type*, class *Electricity producers, electric utilities*, summed
  to annual, MWh.

```
intensity_g_per_kWh = kt_CO2e × 1e6 / utility_generation_MWh
```

**Why utility-only in the denominator.** The numerator is the utility industry's
emissions. Large industrial cogeneration — Alberta oil-sands self-generation, for
instance — is booked under its host industry, not BS22110. Dividing utility
emissions by *total* generation deflates the result; Alberta came out at 323
g/kWh for 2022 that way. Restricting the denominator to utility generation keeps
both sides on one scope, and makes the national figure validate almost exactly
against ECCC's published headline (Canada 2022: computed 101.3 versus published
100).

### 6.8 Lifecycle terms

**Upstream methane.** Calibrated against The Atmospheric Fund's *Fugitive Methane*
guideline (May 2022). TAF publishes a **+65 %** increase over combustion-only for
a single home switching fuels with no pipeline infrastructure change, on a
20-year GWP basis — the row that matches this tool's question, per TAF's own
guidance that modelling activities affecting gas consumption should use GWP20 and
inventories should use GWP100.

The engine has exactly one upstream lever, `methaneLeakPct × methaneGWP`. TAF's
+65 % is mostly **non-methane process emissions** (+55 of the 65 points — flaring,
venting, compressor combustion), which TAF states cannot be disaggregated. So the
lever is **calibrated to reproduce TAF's published +65 % ratio in aggregate**:
`methaneLeakPct = 2.14 %` at `GWP = 85`, landing at +64.4 %.

**That 2.14 % is a bundled stand-in for two effects, not a literal leak-rate
reading.** Feeding TAF's headline 2.7 % full-chain leak rate through this formula
would implicitly claim all of the +65 % is methane, and overshoots to about +82 %,
past TAF's own +92 % neighbourhood-conversion scenario.

Propane gets **no** upstream adder. No defensible propane upstream-loss constant
exists yet, and reusing the natural-gas figure would be wrong.

**Refrigerant GWP**, from IPCC AR6 WGI Chapter 7 Supplementary Material, Table
7.SM.7, read directly. Blend arithmetic reproduces the shipped figures exactly
(R-410A = 50 % R-32 + 50 % R-125; R-454B = 68.9 % R-32 + 31.1 % R-1234yf):

| Refrigerant | GWP100 | GWP20 |
|---|---:|---:|
| R-410A | 2,256 | 4,715 |
| R-32 | 771 | 2,690 |
| R-454B | 531 | 1,854 |
| R-290 (propane) | 0.02 | 0.07 |

A user toggle selects the horizon, defaulting to 100-year. The upstream-methane
term keeps its fixed 20-year GWP of 85 regardless, because its 2.14 % rate is
calibrated specifically against TAF's GWP20-basis ratio; switching it would need
a recalibration TAF's guideline does not provide.

**Refrigerant charge mass** is fitted to real manufacturer spec-sheet data, with
n = 6 units for R-410A and n = 4 for R-454B. **R-32 and R-290 remain unverified**:
they are the R-410A curve scaled by a ratio reported by a peer tool for an
unstated reference unit. At 3 tons the fit gives R-410A 4.63 kg, R-454B 6.72 kg,
R-32 2.96 kg, R-290 0.64 kg. A handful of units from a few brands is a
spot-check, not a survey of the residential market.

**Line loss**, province-specific, applied to all delivered electricity:

| Province | Loss | Source |
|---|---:|---|
| Ontario | 7.4 % | IESO transmission ~2 % compounded with the OEB's audited distributor Total Loss Factor 5.31 % |
| Alberta | 7.68 % | CEA Electricity Consumption Report, transmission + distribution combined (2002) |
| Quebec | 7.5 % | Régie de l'énergie blended T&D factor |
| Elsewhere | 5 % | Canada-wide estimate |

All three province-specific sources are dated (2002–2008). They are the best
specific data found, not a claim of current-year precision.

---

## 7. Operating cost

The cost card prices the simulation's energy flows with `prices_json/{on,qc,ab}.json`,
built by `Python/rates_etl.py` from published residential tariffs plus StatCan
18-10-0001 for heating oil.

**Tariff application.** The engine emits a month × hour-of-day electricity matrix
for both scenarios, so time-of-use plans are priced per (month, hour). The
typical year has no weekday structure, so weekday-only TOU rules are weighted
**5/7 weekday to 2/7 weekend** per cell — exact in expectation for a
temperature-driven load. Holidays are treated as regular weekdays, worth under
1 %. Ontario offers TOU (default) and ULO; both scenarios always use the same
plan.

**Fixed charges.** The electricity service charge is identical in both scenarios
and excluded. The gas fixed charge is counted only in scenarios that consume gas,
so a gas home switching to a heat pump without gas backup sees the dropped fixed
charge in its savings — the card says so, and gives the number to subtract for
homes keeping gas service.

**Unit conversions** are read from the engine's own exported constants — gas at
10.3611 kWh/m³, oil at 10.7778 kWh/L — so the price card and the emission factors
cannot drift apart.

**Stated in the card's fine print:** carbon components are excluded (the federal
consumer fuel charge has been zero since 2025-04-01); Alberta values carry
screening supplements for transmission and default gas supply and are badged as
estimates; the Ontario gas tariff is the Union-South rate zone; the Ontario
Electricity Rebate is not modelled, since it scales both scenarios equally;
everything is pre-tax. **The headline is the delta, not the absolute bills.**

Cities in provinces without a rates file degrade to energy and emissions only.
New Ontario cities reuse Toronto's entry and Quebec City reuses Montreal's, which
is valid for the *delta* because the volumetric rates that drive it are
province-uniform.

---

## 8. Simulation engine

`app/engine.js` — one pure function, `simulate(opts)`, running 8,760 hours.

```
load_kW(h) = UA_W_per_K / 1000 × max(0, Tbalance − Tout(h))
```

Above the balance point nothing runs. Otherwise:

- **Base case** delivers the load from the incumbent system:
  `fuel_in = load / efficiency`, combustion GHG = `combustion_EF × fuel_in`. An
  electric baseboard instead draws grid electricity at that hour's EF.
- **Project case** dispatches the heat pump per the control strategy (§5).
  `hp_electricity = hp_heat / COP(T)`; `backup_electricity = backup_heat /
  backup_eff`, or backup fuel for a combustion backup. All electricity is grossed
  up by line losses and charged at that hour's grid EF.

Hourly grid EF is `level × shape(tbin, hour, season)`, with the shape lookup
reproducing `build_ef_surface.lookup_shape`'s fallback order exactly. The `efMode`
flag selects both the level index and the shape-ratio field, so average and
marginal are consistent all the way through.

Lockout is governed by the curve's own `min_op_temp_C`, not by a null COP — the
aggregate curves keep a non-null COP below their lockout, so `min_op_temp_C` is
the single authority.

---

## 9. Validation

### Engine

Six test vectors covering capacity shortfall with electric backup, the
above-balance-point zero case, lockout dispatch, refrigerant amortization,
upstream methane on base gas, and below-lockout derate. They run twice — against
`app/engine.js` under Node, and against `pipeline/validate_engine.py`, a faithful
Python mirror. **Both pass, and agree to four decimal places.** A divergence
between the browser engine and the Python mirror fails the run.

### Grid emission factors

Ontario reconciles against TAF's published Annual Average Emissions Factor within
±0.9 % for 2020–2024 (§6.3). Alberta passes its ±15 % gate against the published
series it was fitted to, with the staleness caveat in §6.4. The national figure on
the ECCC yearly basis computes to 101.3 g/kWh for 2022 against ECCC's published
headline of 100.

Two independent routes agree on Ontario. The hourly pipeline (IESO generation ×
TAF's NIR gas intensity) gives 54.9 g/kWh for 2023; the ECCC yearly basis (ECCC
inventory emissions ÷ StatCan utility generation) gives 56.4. The two share no
inputs.

### The hourly surface

Each year's surface is applied hour by hour to that year's own temperature series
and the reconstructed annual mean compared against the figure computed directly
from the hourly series. Tolerance ±10 %:

| Province | Worst per-year | Overall |
|---|---:|---:|
| ON | 4.5 % | +0.2 % |
| AB | 0.4 % | +0.1 % |
| QC | 7.4 % | +0.2 % |

Alberta reconstructs almost exactly — its coal/gas fraction shape is very stable
year to year. Ontario carries more residual because its gas-dispatch shape itself
drifts as the fleet grows. **Quebec's percentages are meaningless**: they sit on an
essentially-zero base, where 7.4 % is 0.0003 g/kWh of rounding. They are reported
for completeness, and Quebec no longer uses this surface (§6.5).

### Against published benchmarks

> **Superseded as of 2026-09-09 and not yet re-run.** The Phase 7 benchmark
> comparison — this tool's annual outputs against NRCan/CanmetENERGY 2022,
> Pembina/CCI 2023 and Efficiency Canada 2023 — was produced against an Ontario
> grid of 96.9 g/kWh average and 500 g/kWh marginal, and a flat 5 % line loss.
> Both have since changed (§6.3, §6.8). The qualitative findings it reached still
> hold: no deviation over 30 % lacked a methodological explanation, and every
> notable gap traced to grid basis, grid vintage or archetype floor area. **The
> numeric tables did not survive the change and have been withheld rather than
> reprinted.** They also cannot currently be regenerated: `validate_engine.py`
> runs the six unit vectors only, and no committed script reproduces the
> benchmark scenarios.

---

## 10. Limitations

**What the data cannot tell us**

- Whether a specific home will behave like its modelled load line. The tool has
  no envelope model, no air-leakage term and no occupant behaviour.
- What a heat pump does below its published minimum operating temperature. No
  manufacturer publishes it.
- What Quebec's marginal emissions intensity actually is. That needs intertie
  flow data the tool does not have (§6.5).
- Real part-load efficiency. Only maximum-compressor curves exist, so a
  modulating inverter is costed at its max-speed COP — conservative, since real
  part-load COP is usually higher.
- Anything about a specific unit's installed performance. Certified ratings are
  laboratory values; commissioning, duct condition and sizing all move real
  results.

**What we assumed**

| Assumption | Value | Why it is an assumption |
|---|---|---|
| Ontario T&D loss inside TAF's published factor | 7.4 % | TAF does not publish the rate it used; ours is set equal to the rate the engine re-applies so the round trip cancels (§6.3) |
| Defrost derate | 7 % COP across −7…+4 °C | A single default, not a per-model measurement |
| `mid_18-30k` lockout | −20 °C | The only cell without a datasheet lockout; clamped to that unit's coldest tested point |
| Quebec thermal EF | 700 g/kWh | Never independently calibrated; cannot matter at under 0.01 % share |
| Upstream methane lever | 2.14 % at GWP 85 | A bundled stand-in for methane *and* non-methane process emissions, calibrated to TAF's +65 % |
| R-32 and R-290 charge mass | Peer-tool ratio | Not verified against any manufacturer datasheet |
| Baseline system | Covers 100 % of load, no cycling losses | No part-load derating modelled |
| Alberta coal/gas factors | 1050 / 540 | Fitted against a published series the publisher has since revised (§6.4) |

**What would change the answer**

- **The grid basis.** Marginal versus average versus inventory-average moves
  Ontario results more than any equipment choice. This is why all three are
  offered rather than one being picked for the user.
- **The design heat load.** It scales the entire simulation, which is why it is
  a direct user input rather than an archetype's hidden consequence.
- **The switch-over temperature**, in any dual-fuel scenario.
- **The grid's future.** The surface models weather-driven shape and a per-year
  level; it does not forecast. Using the most recent complete year as "today's
  grid" assumes the near future resembles it — and Ontario's level is actively
  rising.

---

## 11. Reproducing

Order matters where a step consumes another's output.

```
# Grid
python pipeline/fetch_ieso.py            # → data/interim/ieso_hourly_by_fuel.csv
python pipeline/fetch_aeso.py            # parses hand-placed zips in data/raw/aeso/
python pipeline/fetch_hq.py              # parses hand-placed HQ csv in data/raw/hq/
python pipeline/build_grid_ef.py         # → grid_ef_on.json
python pipeline/build_grid_ef_ab.py      # → grid_ef_ab.json
python pipeline/build_grid_ef_qc.py      # → grid_ef_qc.json
python pipeline/build_grid_ef_annual.py  # → grid_ef_annual.json   (StatCan WDS)

# Weather
python pipeline/fetch_tmy.py             # → data/interim/tmy_hourly.csv
python pipeline/fetch_weather.py         # → data/interim/weather_hourly.csv
python pipeline/build_tmy_temps.py       # → tmy_temps.json
python pipeline/build_weather_years.py   # → weather_<city>.json
python pipeline/build_city_design_temps.py

# Grid surface (needs grid EF + weather)
python pipeline/build_ef_surface.py      # → ef_surface_{on,ab,qc}.json

# Equipment
python pipeline/build_cell_curves.py     # → hp_cell_curves.json
python pipeline/build_hp_tier_selection.py   # → hp_tier_selection.json
python pipeline/build_ac_curves.py       # → ac_curves.json

# Homes
python pipeline/build_archetypes.py      # → archetypes.json
python pipeline/build_city_house_profiles.py

# Checks
python pipeline/validate_engine.py       # 6 vectors, Python mirror + node
python pipeline/test_hp_curves.py
```

`grid_common.py` is shared with `Python/grid_etl.py`, which builds the separate
grid dashboard. **A change to an emission factor there changes both tools**, so
regenerate `grid_json/` alongside this tool's data.

`data/raw/` and `data/interim/` are local-only and gitignored. Losing them is
fine — re-run the pipeline. What has to be defensible is the process, which is
versioned; not the bytes.

---

## 12. Sources

| Dataset | Publisher | Vintage | Use | Notes |
|---|---|---|---|---|
| Generator Output by Fuel Type Hourly | IESO | 2020– | ON hourly grid mix | Fetch with a browser User-Agent |
| CSD Generation (Hourly) | AESO | 2015– | AB hourly grid mix | Box-hosted, manual download |
| Hourly generation by source | Hydro-Québec | 2019– | QC grid mix | Manual; 2021 missing; not used by the tool |
| Ontario Electricity Emissions Factors and Guidelines | The Atmospheric Fund | 2025 ed. | ON gas intensity, validation | Sheets 1 and 10 |
| Fugitive Methane guideline | The Atmospheric Fund | May 2022 | Upstream methane calibration | |
| Physical flow account for GHG emissions (38-10-0097) | StatCan / ECCC NIR | 2009–2023 | ECCC yearly numerator | Via StatCan WDS |
| Electric power generation by type (25-10-0015) | StatCan | 2009–2023 | ECCC yearly denominator | Utility class only |
| Greenhouse gas intensity of Alberta's electricity grid | Alberta.ca / ECCC NIR | 2026 NIR | AB validation | Revised; see §6.4 |
| CWEC2020 | ECCC | 2020 | Typical year | |
| CWEEDS 2020 | ECCC | 1998–2017 | Multi-decade record | |
| MSC Datamart hourly observations | ECCC | 2019– | Recent years | |
| NBC Appendix C Table C-2 | NRC | 2020 | Design-temperature reference | Displayed, not used in the calculation |
| EnerGuide / ERS audit records | NRCan | — | Sampling frame, design heat loss, real homes | |
| AHRI Directory certificates | AHRI | — | Tiering and rated points | |
| Manufacturer datasheets | various | — | Capacity and COP curves | Cited per cell; local only |
| ccASHP product listings | NEEP | — | Curve fallback, cross-check table | Not redistributable — see below |
| AR6 WGI Ch.7 SM Table 7.SM.7 | IPCC | 2021 | Refrigerant GWP | |
| National Inventory Report residential factors | ECCC | — | Combustion factors | |
| Residential tariffs | provincial utilities | monthly | Cost card | |
| Heating oil prices (18-10-0001) | StatCan | — | Cost card | |

**Redistribution.** NEEP's product list is not openly redistributable. No NEEP
data is embedded in any shipped file: the published curves are digitized from
manufacturer datasheets, and NEEP appears only as a per-model fallback citation
and in the on-page cross-check table. Manufacturer datasheet PDFs are kept
locally and are not committed.
