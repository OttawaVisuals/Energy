# Methodology

Every assumption, factor, and data source used by the pipeline, in the order
they were established. See `PLAN.md` for the overall project plan.

---

## Ontario grid emissions intensity (Phase 1)

### Data source

**IESO — Generator Output by Fuel Type Hourly Report**
<https://reports-public.ieso.ca/public/GenOutputbyFuelHourly/>

One XML file per year (`PUB_GenOutputbyFuelHourly_<year>.xml`), already
aggregated province-wide by fuel type — no generator-to-region or
generator-to-fuel mapping needed. Fetched by `pipeline/fetch_ieso.py` into
`data/raw/ieso/`, parsed into a tidy hourly CSV
(`data/interim/ieso_hourly_by_fuel.csv`: Date, Hour, Fuel, Output_MW).

Fuel categories reported: NUCLEAR, GAS, HYDRO, WIND, SOLAR, BIOFUEL, OTHER.
Data confirmed available continuously from 2020-01-01 to the present.

A rejected alternative source was considered and discarded: an older
per-generator report (`GenOutputCapabilityMonth`) requires a
generator→region lookup file we don't have, and would need to be
re-aggregated by fuel type ourselves. The by-fuel-hourly report gives the
same information already aggregated, with no missing dependency.

### Known limitations of the source data (inherited from IESO)

- Only reports generators connected to the IESO-administered market.
  "Behind-the-meter" generation and small embedded generators
  (historically <20 MW) are not captured.
- Imports/exports are not included — this is a **production-based**
  intensity for Ontario generation, not a **consumption-based** intensity
  for Ontario demand. Quebec/Manitoba imports (low-carbon) and any export
  flows are excluded. TAF (see below) notes 93% of 2022 Ontario imports
  came from Quebec/Manitoba, i.e. excluding them is conservative (doesn't
  inflate our intensity), but it means the true consumption-based number
  could be marginally different, especially at times of heavy import
  reliance.

### Emission factor model

Direct (combustion) emissions only — no lifecycle/upstream terms here
(those are handled separately as user-adjustable sliders per PLAN.md
§6). Nuclear, Hydro, Wind, Solar, Biofuel, and Other are treated as
**zero direct-combustion emissions**. All direct grid emissions are
attributed to natural gas generation:

```
AvgEF(hour)      = GasFraction(hour) * GAS_EF_G_PER_KWH
MarginalEF(hour) = GAS_EF_G_PER_KWH  whenever gas output > 0, else AvgEF(hour)
```

In practice, gas generation is nonzero in nearly every hour of the
2020–2026 data, so `MarginalEF` is very close to a flat `GAS_EF_G_PER_KWH`
in nearly all hours — consistent with Ontario's gas fleet being the
near-permanent marginal resource (see TAF appendix below, and PLAN.md §1).

This mirrors the exact approach used by The Atmospheric Fund (TAF) in
their published, NIR-sourced Ontario electricity emissions factors
(see next section) — we did not invent this simplification independently.

### Gas emission factor: 500 g CO2e/kWh — calibration

**Source used to calibrate:** *Ontario Electricity Emissions Factors and
Guidelines*, The Atmospheric Fund, June 2024 edition
(<https://taf.ca/custom/uploads/2024/06/TAF-Ontario-Emissions-Factors-2024.pdf>).

TAF computes Annual Average Emissions Factors (AEF) for Ontario as
`total electricity-sector emissions / total electricity produced`, using
IESO generation output combined with the National Inventory Report's (NIR)
natural gas emissions intensity (NIR gas generation in GWh ÷ NIR gas
emissions in ktCO2e) — i.e., the same "attribute all direct emissions to
gas" approach we use here, just calibrated with a year-specific gas
intensity pulled directly from the NIR rather than backed out.

TAF's published Annual AEF (gCO2e/kWh), p.11:

| Year | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 |
|---|---|---|---|---|---|---|---|---|---|
| AEF | 46 | 40 | 18 | 29 | 29 | 36 | 44 | 51 | 67 |

Using our own fetched IESO generation mix for 2020–2023, we back out the
implied gas intensity for each year (`AEF / gas_generation_fraction`,
since non-gas emissions are ~0):

| Year | Gas fraction of ON generation | Implied gas EF (g/kWh) |
|---|---|---|
| 2020 | 6.85% | 526 |
| 2021 | 8.87% | 496 |
| 2022 | 10.77% | 474 |
| 2023 | 13.34% | 502 |

These four independent values cluster tightly (474–526, average ~500,
spread ±5%), and land squarely inside the range PLAN.md's own data-source
notes anticipated ("gas CCGT/peakers ~490–550 g/kWh"). We adopted a single
constant **500 g CO2e/kWh** for the gas combustion factor
(`GAS_EF_G_PER_KWH` in `build_grid_ef.py`) rather than a year-varying
value, for simplicity — the ±5% year-to-year spread is well inside our
±15% validation tolerance.

**TODO:** replace this backed-out constant with a year-by-year factor
pulled directly from NIR Part 3 (gas generation ÷ gas emissions, Annex
13 tables) if/when we fetch NIR data directly, instead of relying on
TAF's published AEF as an intermediate. Not done yet — NIR Part 3's
detailed tables weren't successfully machine-readable in this pass
(large PDF; canada.ca fetch was also blocked in this environment, see
below).

### Validation

Generation-weighted annual average EF, computed from our own hourly
series, compared against TAF's published Annual AEF (±15% tolerance per
PLAN.md):

| Year | Computed | TAF published | Diff |
|---|---|---|---|
| 2020 | 34.2 | 36.0 | −4.9% |
| 2021 | 44.3 | 44.0 | +0.8% |
| 2022 | 53.8 | 51.0 | +5.6% |
| 2023 | 66.7 | 67.0 | −0.5% |

All four years pass well inside ±15% (max deviation 5.6%). 2024–2026 have
no TAF reference yet (published guideline only covers through 2023); our
computed 2024 value (81.3 g/kWh) is in the same ballpark as an
independently-sourced figure of 73.8 g/kWh from the Toronto Atmospheric
Fund's 2024 GTHA Carbon Emissions Inventory (different methodology/scope,
not a strict apples-to-apples check, but directionally consistent).

### Known blocked/quirky fetches (for next time)

- `canada.ca` (ECCC OBPS emission factors page) did not respond to `curl`
  in this environment — same family of issue as IESO/AESO domains being
  WebFetch-blocked. Worked around by using TAF's PDF (hosted on taf.ca)
  instead, which cites the same NIR source.
- IESO and AESO domains: use `curl` with a `User-Agent` header, not
  WebFetch (WebFetch is blocked for these domains — see prior session
  notes).

### Not yet done (explicitly out of scope for this pass)

- Temperature × hour-of-day × season EF binning (needs ECCC weather join
  — Phase 2 per PLAN.md). The current output is the full hourly average +
  marginal series, not yet binned.
- Refining `MarginalEF` beyond "flat gas EF whenever gas > 0" (e.g.
  ramping-based marginal detection).
- Quebec grid EF pipeline.
- The full hourly JSON (`data/processed/grid_ef_on.json`, ~6 MB) is an
  intermediate/validation artifact, not the final browser-facing file —
  PLAN.md's ~50–200 KB per city target applies to the final *binned*
  lookup table, which comes out of Phase 2, not this file.

---

## Alberta grid emissions intensity (Phase 1)

### Data source

**AESO — CSD Generation (Hourly), historical dataset**, manually downloaded
by the user from AESO's data-requests page (Box-hosted, not scriptable —
see below) and placed in `data/raw/aeso/` as ~6-month zip files, 2015-01
through 2026-06. Parsed by `pipeline/fetch_aeso.py` into
`data/interim/aeso_hourly_by_fuel.csv`.

This is per-**asset**, per-hour, and — unlike the plan's original
assumption — already carries **Fuel Type and Sub Fuel Type per row**, so no
separate asset→fuel mapping or manual coal→gas conversion table is needed:
each asset's fuel tag in the data reflects what it actually was at that
point in time (e.g. a plant converted from coal to gas mid-history shows up
as COAL in early rows and GAS in later ones, automatically). Also includes
`Maximum Capability` (available capacity that hour, accounting for outages/
derates) and `System Capability`, letting us compute per-fuel utilization —
the AB equivalent of the Output/Capability/Capacity/Utilization columns in
the earlier Ontario `ONGrid.py` reference script.

Confirmed data quality: 223 assets active as of 2025; only one date
(2026-06-30) has fewer than 24 hours (data cutoff at download time, not a
gap); fuel mix shows the expected coal phase-out (49.5% coal in 2015 → 0%
by 2025), which is itself a useful sanity check that the fuel tagging is
behaving as documented.

### Emission factor model

Direct combustion emissions only. Hydro, Wind, Solar, Other, and Energy
Storage treated as zero-emission. `DUAL FUEL` (transitional coal units
converted to co-fire or fully burn gas) is grouped with `GAS` as
"gas-like" — these units are already mostly/entirely gas-fired by the time
they carry this tag.

```
AvgEF(hour)      = CoalFrac(hour) * COAL_EF_G_PER_KWH
                    + GasLikeFrac(hour) * GAS_EF_G_PER_KWH
MarginalEF(hour) = GAS_EF_G_PER_KWH whenever gas-like output > 0,
                   else AvgEF(hour)
```

**Limitation (flagged, not fixed in this pass):** unlike Ontario, Alberta
had substantial coal generation through ~2021 (up to ~50% in 2015), and
coal — not just gas — may have set the margin in some pre-2022 hours. The
"gas always marginal" simplification is much better justified for 2022+
(coal <12% of generation) than for the 2015–2020 portion of the dataset.

### COAL_EF / GAS_EF calibration: 1050 / 540 g CO2e/kWh

**Source used to calibrate:** Alberta.ca, *"Alberta's greenhouse gas
emissions reduction performance"*
(<https://www.alberta.ca/albertas-greenhouse-gas-emissions-reduction-performance>),
Figure 7 "Greenhouse gas intensity of Alberta's electricity grid", sourced
from ECCC's National Inventory Report:

| Year | 2019 | 2020 | 2021 | 2022 | 2023 |
|---|---|---|---|---|---|
| Intensity (g CO2eq/kWh) | 630 | 630 | 580 | 510 | 470 |

Using our own computed AESO fuel-mix fractions for these 5 years, we fit
`intensity = coal_frac * COAL_EF + gas_like_frac * GAS_EF` by least
squares: **COAL_EF ≈ 1055, GAS_EF ≈ 542 g/kWh**, rounded to **1050 / 540**.
Both are physically plausible (Alberta's subcritical coal fleet is widely
cited around 900–1100 g/kWh; a gas EF somewhat above Ontario's calibrated
500 g/kWh is expected, since Alberta's gas fleet includes more
simple-cycle peakers relative to combined-cycle than Ontario's).

### Validation

| Year | Computed | Published | Diff |
|---|---|---|---|
| 2019 | 652.3 | 630.0 | +3.5% |
| 2020 | 598.1 | 630.0 | −5.1% |
| 2021 | 565.0 | 580.0 | −2.6% |
| 2022 | 517.2 | 510.0 | +1.4% |
| 2023 | 475.4 | 470.0 | +1.1% |

All 5 calibration years pass well inside ±15% (max deviation 5.1%).
2015–2018 have no published reference found yet (out-of-sample): computed
values (739, 728, 714, 661 g/kWh) extrapolate smoothly along the known
coal-phase-out trend (Alberta.ca separately cites 800 g/kWh in 2005 down to
630 g/kWh by 2019), with no discontinuities — a reasonable sanity check
even without a hard number to compare against. 2024–2026 (395–434 g/kWh)
likewise have no published reference yet but continue the trend smoothly.

### Not yet done

- Same weather-join/binning and marginal-refinement items as Ontario,
  above.
- The coal-margin limitation noted above, if pre-2022 Alberta scenarios
  become important to the tool.

---

## Quebec grid emissions intensity (Phase 1)

### Data source

**Hydro-Québec hourly generation by source**, manually downloaded by the
user and placed in `data/raw/hq/historique-production-electricite-quebec.csv`.
Columns: Date (ISO8601 with UTC offset), Hydroelectric, Wind, Other
renewables, Solar, Thermal, Total. Parsed by `pipeline/fetch_hq.py` into
`data/interim/hq_hourly_by_fuel.csv`.

This turned out to be real hourly generation-by-fuel data, not just the
flat annual constant PLAN.md originally proposed for Quebec ("Skip the
hourly pipeline; document the choice") — so we built a real hourly
pipeline for Quebec too, matching ON/AB's structure, rather than a
hardcoded constant.

### Data quality issues found and how they were handled

1. **2021 is entirely missing** (and the first ~3 weeks of January 2022).
   Confirmed by the user: this is a genuine gap in the original source
   file, not a download or parsing error. `fetch_hq.py` produces no hourly
   rows for this period; `build_grid_ef_qc.py`'s output JSON records
   `years_missing: [2021]` in its `meta` block so downstream consumers
   don't silently assume continuous coverage.

2. **7,307 rows with a blank Date field**, in 3 contiguous blocks, each
   spliced oddly between a `2022-12-31` row and a `2022-01-0x` row (i.e.
   the file is not fully in chronological order at those points). The
   generation values in these rows look plausible (same magnitude/shape as
   real hourly output) and their total (≈304 days) is suspiciously close
   to a full year, but there is no way to assign them real timestamps.
   **Decision: dropped, not imputed or guessed.** `fetch_hq.py` reports the
   drop count explicitly on every run.

3. **A second file the user found**
   (`historique-production-consommation-ec-horaire.csv`, "Gross output
   from HQP generating stations" / heritage-pool electricity accounting)
   does cover 2021 with no gap, but it's a **different dataset** — HQ's
   regulatory/commercial supply accounting (heritage vs non-heritage pool
   volumes, transmission losses, etc.), not a fuel-type generation
   breakdown. It has no Hydro/Wind/Solar/Thermal columns, so it cannot be
   used to fill the fuel-mix gap for 2021. Kept in `data/raw/hq/` for
   reference but not used by the pipeline.

### Emission factor model

Direct combustion emissions only. Hydro, Wind, Solar, and Other renewables
treated as zero-emission. All direct emissions attributed to "Thermal" —
HQ's small remote/off-grid diesel and gas/oil generation (serving
communities not connected to the main hydro grid, e.g. Nunavik,
Îles-de-la-Madeleine). Thermal's share of total generation is confirmed
tiny and consistent across every year with data: 0.0007%–0.005%.

```
AvgEF(hour) = ThermalFrac(hour) * THERMAL_EF_G_PER_KWH
```

**MarginalEF is set equal to AvgEF as a placeholder** — not a real
marginal calculation. With thermal this small a share and no intertie/
import flow data in this dataset, there's no meaningful "which resource is
on the margin" signal to compute from what we have. This matters more for
Quebec than it sounds: PLAN.md's own methodology note (§1) flags that
counting winter imports could push Quebec's effective marginal intensity
to ~35 g/kWh — over 1000x our production-only average — because new
electricity demand in Quebec may in practice be served by winter imports
of higher-carbon power rather than by curtailing zero-carbon domestic
hydro. **Not modeled here; flagged as a real gap, not a rounding error.**

### THERMAL_EF_G_PER_KWH: 700 g/kWh — not independently calibrated

Unlike Ontario and Alberta, no per-year regression against a published
reference was possible: thermal's share is too small relative to any
available reference point to back out a precise factor this way. Used
700 g CO2e/kWh, a commonly-cited approximate figure for small diesel
generation. Given thermal's <0.01% share, this choice barely matters: a
2x change in the constant moves the computed annual average by a few
hundredths of a g/kWh.

### On the ~1.5 g/kWh figure from PLAN.md, vs. our computed ~0.01–0.035 g/kWh

PLAN.md's own data-source notes cite "~1.5 g/kWh production-based" for
Quebec (general knowledge / HQ sustainability reporting, not independently
re-verified in this pass). Our computed combustion-only figure is
0.005–0.035 g/kWh across 2019–2025 — 50–100x smaller. **This is not treated
as a validation failure** (unlike Ontario/Alberta, no ±15% pass/fail gate
is applied here) because the two numbers likely have different accounting
scopes: 1.5 g/kWh plausibly includes things this combustion-only model
doesn't attempt, such as reservoir methane emissions from hydro
(a well-documented, if contested, non-combustion emission source for
hydro reservoirs) or non-CO2 emissions from "Other renewables" (biomass).
**Open question, not resolved in this pass** — if a precise production-based
number matters later, this needs a real source for the ~1.5 g/kWh figure's
derivation, not just PLAN.md's summary of it.

### Not yet done

- Resolving the ~1.5 g/kWh vs ~0.02 g/kWh discrepancy above.
- Import-based marginal intensity (requires intertie flow data).
- 2021 gap remains unfilled.
- Weather-join/binning, same as ON/AB.

---

## Weather & TMY (Phase 2)

Launch cities per PLAN.md: Ottawa, Toronto, Montreal, Calgary, Edmonton.
Both data sources turned out to be directly scriptable — no manual
download needed from the user, unlike AESO/HQ in Phase 1.

### TMY — CWEC2020

**Source:**
<https://collaboration.cmc.ec.gc.ca/cmc/climate/Engineer_Climate/CWEC_FMCCE/CWEC_FMCCE_v_2020/>
(plain Apache directory listing, one zip per province, each containing one
CSV per station). Fetched and parsed by `pipeline/fetch_tmy.py`, which
downloads only the 3 province zips needed (ON, QC, AB) and extracts only
the 5 target station files, not the full ~190 MB all-Canada archive.

Station chosen per city (primary international airport in each case,
matching the same Ottawa/Toronto IDs already used in the reference
`ONWeather.py`):

| City | Station | Climate ID |
|---|---|---|
| Ottawa | OTTAWA INTL A | 6106001 |
| Toronto | TORONTO INTL A | 6158731 |
| Montreal | MONTREAL INTL A | 7025251 |
| Calgary | CALGARY INTL A | 3031092 |
| Edmonton | EDMONTON INTL A | 3012216 |

Each station file is a "typical year" — 8,760 hours built by splicing
together 12 typical meteorological months chosen from a multi-decade
record. Units per the file's own header: dry bulb temperature in 0.1°C,
wind speed in 0.1 m/s (converted to whole units in the parser).

**Format quirk:** each station CSV's data rows have one more field than the
header row (the header omits a label for the leading "ECCC station
identifier" column). Without `index_col=False`, pandas silently treats
that column as a row index, shifting every other column over by one and
corrupting the date parsing. Fixed in `fetch_tmy.py`.

Output: `data/interim/tmy_hourly.csv` (City, Month, Day, Hour,
Temperature_C, WindSpeed_ms). Sanity-checked means/minimums, all
plausible for Canadian climate normals:

| City | Mean temp (°C) | Min temp (°C) |
|---|---|---|
| Ottawa | 6.9 | −29.5 |
| Toronto | 9.1 | −24.2 |
| Montreal | 7.8 | −27.2 |
| Calgary | 4.8 | −29.6 |
| Edmonton | 3.3 | −32.5 |

### Historical hourly weather

**Source:** ECCC MSC Datamart,
`https://dd.weather.gc.ca/today/climate/observations/hourly/csv/<PROV>/`
— same source and pattern as `Weather/ottawa_weather_fetch_hourly.py` and
the reference `ONWeather.py`, generalized from 10 Ontario subregions to
the 5 launch cities (same station IDs as the TMY table above). Fetched by
`pipeline/fetch_weather.py`.

Fetched 2019–2026 (matches the earliest available grid EF data, Quebec).
All 5 cities, all 8 years, ran clean: no month exceeded the 10%-missing
threshold that would have triggered a manual-review flag, and no
`weather_flags.csv` was produced. 329,160 total rows.

Output: `data/interim/weather_hourly.csv` (City, Date, Hour,
Temperature_C, WindSpeed_kmh, Humidity_pct).

### Not yet done

- Building actual archetype load profiles against this weather data
  (Phase 4).

---

## Grid EF surface: temperature × hour × season (Phase 2)

Builds the temperature × hour-of-day × season grid-EF lookup surface
PLAN.md methodology decision #2 called for (deferred out of Phase 1 until
hourly weather existed; now unblocked). Built by
`pipeline/build_ef_surface.py`; joins each province's hourly average +
marginal EF series (`data/processed/grid_ef_{on,ab,qc}.json`) with the
matching hourly temperature history (`data/interim/weather_hourly.csv`) and
bins over the full overlapping record. Output: one compact JSON per
province, `data/processed/ef_surface_{on,ab,qc}.json` (35–47 KB each, well
under the 100 KB target).

### Why a surface, not temperature-only binning

Per PLAN.md #2: grid intensity is not a function of temperature alone —
hour-of-day (morning/evening gas peaks), season (hydro conditions, AC vs
heating load), and outages all move it. Binning EF by temperature alone and
applying a TMY series would smear morning-peak gas hours into mild
afternoons. So we bin by **temperature (2 °C bins) × hour-of-day (1–24) ×
season (winter=DJF / spring=MAM / summer=JJA / fall=SON)**. Concrete
example the surface captures and a temperature-only bin would lose: an
Ontario −18 °C **winter evening (19h)** carries ~2.0× the annual-mean EF
(≈194 g/kWh on the 2025 grid), vs a ratio near 1 at the same temperature in
milder shoulder hours.

### Province vs. city temperature

The grid EF is province-wide, so each surface is per province, keyed on the
temperature of that province's **largest electricity-load centre** — the
best single-station proxy for the province-wide demand↔weather correlation
being captured:

| Province | Temperature proxy city |
|---|---|
| ON | Toronto (GTA dominates Ontario demand) |
| QC | Montreal |
| AB | Calgary |

The engine applies the resulting provincial surface to each launch city's
own temperature series (e.g. Ottawa temperatures against the ON surface).
For a screening tool the modest intra-province inter-city temperature offset
is acceptable.

### Shape × level decomposition — the key modelling choice

The provincial grids are **not stationary** over the available record:
Ontario's average EF roughly tripled 2020→2025 (≈32 → ≈97 g/kWh) as gas
generation grew; Alberta's fell by a third (≈650 → ≈414 g/kWh) as coal
retired. That drift is a **fleet/policy** effect, not a weather effect, so a
single pooled climatology of *absolute* EF reconstructs the multi-year mean
correctly but **cannot reproduce any individual year's level** (pooling a
rising series collapses to its midpoint — an early attempt did exactly this:
overall diff −0.1 %, but per-year errors up to +96 %).

So each hourly EF is decomposed as

```
EF(hour) = annual_level(year) × shape(temp, hour, season)
```

where `annual_level(year)` is that calendar year's mean EF (the trending
part) and `shape` is the multiplicative climatology — the mean of
`EF / annual_level` per bin, ~1 on average (the stationary part). The
physical driver (gas fraction, and in AB coal fraction) scales the whole
level, so a cold winter-evening hour carries roughly the same *ratio* to the
annual mean whether the year's grid is clean or dirty. Each JSON stores:

- the **shape** cells (fine + coarser fallbacks), each
  `[mean_AvgEF_ratio, mean_MarginalEF_ratio, n_hours]`;
- `levels_g_per_kWh`: every calendar year's `[avg, marg, n_hours]` level;
- `reference_level_g_per_kWh`: the **most recent complete calendar year**
  (≥ 8000 joined hours; 2025 for all three provinces) = the current grid.

The engine multiplies `shape × reference_level` for a typical-year EF on
today's grid, and can swap in any stored year's level to reproduce the
historical band — satisfying **both** of PLAN.md #2's sub-points (the TMY
"typical" headline and the honest historical variance band) from one file.
Absolute EF for any cell = `ratio × level` (e.g. the −18 °C winter-19h cell
above: 2.0019 × 96.907 ≈ 194 g/kWh).

Quebec's grid is essentially zero-carbon (≈0.02 g/kWh); the ratio is
unstable dividing near zero, so QC skips the decomposition and carries a
neutral `shape == 1` (`grid_is_zero: true`) — its level is negligible either
way.

### Thin-bin fallback

A 2 °C × 24 h × 4-season grid has ~1600–2100 populated fine cells per
province; the tails (very cold / very warm hours at odd times) are thin. The
surface stores three progressively coarser aggregates so the engine can fall
back when a fine cell has **< 20 hours** (`thin_bin_min_hours`):

```
fine      : temperature × hour × season          (preferred)
coarse_ts : temperature × season   (all hours)   (fallback 1)
coarse_t  : temperature            (all)          (fallback 2)
global    : overall mean shape                    (fallback 3)
```

`lookup_shape()` walks this order, taking the first level whose cell has
≥ 20 hours. Every cell carries its count so the rule is explicit and the
engine can reproduce it. (Worked example: Toronto winter-19h at −18 °C has
only 1 h in the fine cell → falls back to the coarse_ts −18 °C winter cell,
97 h.)

### Validation — reconstruct annual intensity, ±10 %

For each year, the surface is applied hour-by-hour to that year's own
temperature series (shape × that year's stored level, with the thin-bin
fallback) and the reconstructed annual mean is compared to the annual figure
computed directly from the Phase-1 hourly series. Worst per-year deviations:

| Province | Worst per-year | Overall (all years) |
|---|---|---|
| ON | 5.0 % | −0.3 % |
| AB | 0.4 % | +0.1 % |
| QC | 7.4 % | +0.2 % |

All pass the ±10 % tolerance. Notes:

- **AB** reconstructs almost exactly (≤ 0.4 %) — its coal/gas fraction shape
  is very stable year to year. **ON** carries a little more residual (up to
  5 %) because Ontario's gas-dispatch *shape* itself drifts slightly as the
  fleet grows, but stays well inside tolerance.
- **QC**'s percentages are on an essentially-zero base (~0.02 g/kWh); the
  7.4 % is 0.0003 g/kWh of rounding on the tiny stored level, physically
  meaningless. No ±10 % gate is really informative for QC — reported for
  completeness only.

### Not yet done / limitations

- The surface models the *weather-driven shape* and a *per-year level*; it
  does **not** forecast future levels. Using `reference_level` (latest
  complete year) as the "typical current grid" assumes the near-future grid
  resembles the most recent full year — reasonable for a screening tool, but
  Ontario's level is actively rising, so a forward year could differ.
- Load-centre single-station temperature proxy per province (§ above), not a
  population-weighted province temperature.
- Marginal-EF shape inherits Phase-1's simple marginal model (flat gas EF
  whenever gas > 0), so its ratio is ~1 almost everywhere in ON/AB and the
  surface's hour/season structure lives almost entirely in the average-EF
  channel.

---

## Heat pump performance tiers (Phase 3a)

Buckets the NEEP cold-climate ASHP list into 3 performance tiers and picks
candidate models for spec-sheet deep-dive (Phase 3b). Built by
`pipeline/neep_buckets.py`. Outputs `data/interim/neep_tiers.csv` (one row
per physical unit → metrics → tier) and `data/interim/neep_tier_report.md`.

### Data source

**NEEP ccASHP Product List**, downloaded 2026-07-10, saved at
`data/raw/neep/neep_air_source_heat_pump_2026-07-10.xlsx` (60 MB). The
workbook has 5 sheets (`HP Report`, `VRF Report`, `PTHP Report`,
`SPVHP Report`, `AHRI Rated Fields`); we use **`HP Report`** only — the
central-ducted + mini-split residential air-source list. VRF/PTHP/SPVHP are
commercial/packaged and out of scope. Row 0 is a usage-disclaimer banner
(the list is *not* for commercial use; incentive-program reuse needs
permission from ccASHP@NEEP.org — so we publish only derived curves for a
handful of units with attribution, per PLAN.md §7, never the list itself).
Header is row 1; AHRI-rated columns carry a trailing `⁺` superscript that the
parser strips.

### Units and conversions

Each row is one **AHRI-certified combination** (an outdoor unit paired with a
specific indoor unit). NEEP capacities are BTU/h, input powers kW, COP
dimensionless (verified: 10 320 BTU/h ÷ 0.84 kW = COP 3.6). Capacity → kW via
`× 0.29307107 / 1000`.

### The 180k-row duplication trap

The `HP Report` has **180,279 combinations** but only **~11,357 unique
physical outdoor units** (`brand owner + brand + outdoor model`). Carrier
Corporation alone is ~110k combinations (one central chassis certified
against countless indoor coils). Clustering on raw rows would let whoever
certified the most indoor pairings dominate the tiers. **Fix:** collapse to
one row per physical outdoor unit using the *median* of each metric across
its certified pairings, and tier on that. Tiers are then mapped back to all
combinations for reporting counts.

### Screening metrics (per unit, SI)

- **COP@5 °F** (−15 °C) — cold-climate efficiency, taken at the
  **max-compressor-speed** point (what a cold home calling for full heat
  actually draws).
- **Capacity retention** = max capacity @5 °F ÷ rated capacity @47 °F
  (dimensionless, size-independent). Values > 100 % are real for oversized
  cold-climate inverters that boost capacity at low temp.
- **Minimum operating temperature** = the Lowest Cataloged Temperature (LCT)
  where NEEP gives one (~29 % of units); otherwise floored at 5 °F (−15 °C) —
  we simply have no colder catalog point, not a lockout claim.
- **Rated-capacity size class** from rated cap @47 °F: 2-ton (< 30 000 BTU/h),
  3-ton (30 000–42 000), 4-ton (≥ 42 000) — so candidate selection compares
  like-for-like sizes.

Cleaning drops 30 / 180 279 rows (0.02 %) with missing or physically
implausible metrics (retention ∉ (0.2, 2.0] or COP ∉ (0.5, 6.0]).

### Tiering method — why composite quantile-cut, not k-means

COP@5 °F and retention are **essentially uncorrelated** (r ≈ −0.03), and
COP@5 °F is compressed against **NEEP's own 1.75 inclusion floor** (488 units
sit exactly at 1.75, none below) with heavy rounding pileups. On such data
k-means centroids land on incoherent, non-monotonic splits (a "baseline"
cluster ending up with *higher* retention than the "mid" cluster). So tiers
are assigned by **quantile-cut on a composite score** = equal-weight mean of
the percentile ranks of COP@5 °F and retention, cut into equal terciles
(Tier 1 = top third). This is robust to the skew and guarantees a monotonic
premium→baseline gradient in both metrics — the semantics the tool needs.
k-means (k=3, scipy `kmeans2`, seed 20260710) on the same standardized
features is kept only as a cross-check (~55 % unit agreement, confirming the
two methods genuinely differ on this degenerate data).

Resulting tiers (unit / combination counts):

| Tier | Centroid COP@5 °F | Centroid retention | Median min-op | Units | Combos |
|---|---|---|---|---|---|
| Tier 1 — cold-climate premium | 2.07 | 93 % | −30 °C | 3 786 | 33 205 |
| Tier 2 — mid-market cold-climate | 1.97 | 80 % | −25 °C | 3 785 | 100 343 |
| Tier 3 — baseline | 1.84 | 70 % | −25 °C | 3 786 | 46 701 |

Candidate models per tier = the 5 units nearest the tier centroid (standardized
[COP@5 °F, retention] distance) among major brands (Mitsubishi, Daikin,
Fujitsu, LG, Samsung, Carrier/Midea, Gree, Lennox, Trane), deduped by outdoor
model since ~1 300 chassis are rebadged across brand owners. See the report
for the lists — these are the Phase 3b spec-sheet lookup targets.

### AHRI popularity cross-match ("average installed" seed)

Cross-matched the **top 10 AHRI reference numbers** by frequency in the ERS
retrofit data (`ahri_numbers_seen.csv`) against NEEP. Strategy: **exact
AHRI-ref** (current or NEEP's "Old AHRI Reference Number" column) first, then
**fuzzy** normalized-brand + outdoor-model (stdlib `difflib.SequenceMatcher`
≥ 0.80; strip `*` wildcards, revision suffixes, non-alphanumerics). Brand/model
for each seen number comes from `lookup/ahri_numbers.json`.

**Match rate: 10/10 (100 %)** — 8 exact, 2 fuzzy (e.g. Daikin
`3MXL24RMVJU*` → `3MXL24WMVJU*`, score 0.91). All matched because the NEEP
list is broad (any unit meeting the 1.75 floor, not only ENERGY STAR
Cold-Climate models). **Popularity-weighted mean of the matched set:
COP@5 °F ≈ 1.87, retention ≈ 78 %** (weight 31 237 occurrences) — this seeds
the "average installed" bucket. Notably the two single most popular units
(GREE GUD36, ~10.6k combined) are **Tier 3**, so the typical installed heat
pump in the ERS data leans baseline, not premium.

### Superseded by Phase 3b (below)

- The candidate models were selected and the real capacity(T)/COP(T) curves
  built. See "Heat pump performance curves (Phase 3b)".

---

## Heat pump performance curves (Phase 3b)

Builds the per-model, per-tier, "average installed" and GSHP performance
curves the browser engine consumes. Pipeline (as of the 2026-07 re-source
below): `pipeline/build_datasheet_points.py` (encodes the primary-datasheet
points) → `pipeline/build_hp_curves.py` (builds curves) →
`pipeline/test_hp_curves.py` (validates). Output:
`data/processed/hp_curves.json` (~81 KB) plus per-tier sanity plots
`data/interim/hp_curve_tier{1,2,3}.png` and `hp_curve_average_installed.png`.

### 2026-07 UPDATE — re-sourced from primary manufacturer datasheets

The air-source curves were **re-sourced off the NEEP ccASHP list and onto
each representative unit's PRIMARY PUBLIC MANUFACTURER DATASHEET** (submittal /
product data). Motivation: the NEEP list is not openly redistributable, and the
old `hp_curves.json` embedded NEEP-derived per-model certified points
(`neep_points`) in the shipped file. The re-sourced file contains **no NEEP
data** — only points digitized from public manufacturer PDFs (kept locally in
`data/raw/spec_sheets/<brand>/`, git-ignored), each with a `source_doc`
citation. NEEP is retained only as a LOCAL tier-definition reference (Phase 3a);
`extract_neep_points.py` is no longer in the shipping pipeline.

**Representative models (two real, publicly-documented units per tier), and the
max-output heating points digitized from each:**

| Tier | Models | Key published points (cap kW @47/17°F, COP, lock-out) |
|---|---|---|
| 1 — premium | Mitsubishi **MUZ-FH12NAH** (H2i) + **PUZ-HA36NKA** (hyper-heat) | hold ~100% rated capacity to 5°F; COP ≈ 3.9–4.2 @47, 2.2–2.3 @17; lock-out −25°C |
| 2 — mid | Carrier **25HNB9** (2-stage) + Daikin **DZ20VC** (variable) | capacity fades to ~0.5–0.7 by 17°F; COP ≈ 4.1–4.3 @47, 2.3–2.9 @17; lock-out −19 to −23°C |
| 3 — baseline | Carrier **25HNB5** (single-stage) + Mitsubishi **MUZ-HM12NA2** | capacity ~0.5–0.6 by 17°F; COP ≈ 3.6–4.1 @47, 2.4–2.8 @17; lock-out −15°C |

`average_installed` now **maps to the Tier-3 (baseline) curve** (the typical
installed unit leans baseline per the Phase-3a ERS popularity analysis), rather
than a separate popularity-weighted blend of budget-brand units that lack public
extended tables.

**Convention (unchanged in spirit — still max heating output).** Capacities are
the deliverable max at each temperature; COP is that unit's published headline
efficiency (Mitsubishi rated COP@47 + max-capacity COP@17/5/LCT; Carrier/Daikin
high-stage table COP). Because these are published headline points, the tiers
turn out to differ mainly in **cold-weather capability (capacity retention +
lock-out temperature)** rather than peak COP — which is the honest distinction
(all modern units have similar mild-temperature COP; cold-climate premium means
*keeping output when it's brutally cold*, so far less backup is needed). Verified
in-engine: for an Ottawa pre-1980 detached home the tiers rank monotonically
(premium → baseline) on seasonal COP (2.32 → 2.13), backup share (0% → 2%),
lock-out hours (1 → 19) and total GHG.

**Per-source defrost.** Carrier "Integrated" capacities are already
defrost-adjusted (`defrost_inclusive: true` → the 7% derate is *not* re-applied);
Mitsubishi/Daikin points are steady-state (`false` → 7% derate in the −7…+4°C
band, as before).

**Capacity-only points.** Where a manufacturer publishes a low-temperature
capacity retention figure without a max-speed COP (e.g. Mitsubishi's "% at 5°F/
−13°F"), the point carries `COP: null`: `build_model_curve` builds the capacity
curve from all points and the COP curve from the COP-bearing points only, with
the usual cold-end floor — so a missing cold COP is a normal extrapolation, not
a gap in the capacity shape.

**Aggregate smoothing.** When two tier-mates lock out at different temperatures,
the warmer-lock-out member leaves the mean abruptly, stepping the aggregate COP.
A light nan-aware 3-point smoothing (`_smooth3`) fades that transition so the
tier curve stays continuous (the physical unit population thins gradually).

The subsections below describe the original NEEP-based construction; the curve
*construction* (piecewise-linear through the points, cold extrapolation, COP
floor, lock-out, defrost, tier aggregation, isotonic monotonicity, GSHP) is
unchanged — only the *point source* moved from NEEP to manufacturer datasheets.

### Representative models chosen

Two–three units per tier, taken from the Phase-3a candidate lists (nearest tier
centroid, major brands), biased toward models with genuinely retrievable public
performance data and toward the units Canadians actually install:

| Tier | Model (outdoor unit) | Refrigerant | Rated cap @47 °F | Min-op °C | Why |
|---|---|---|---|---|---|
| 1 | Mitsubishi P-series **PUZ-HA36NKA** | R-410A | 11.7 kW (3-ton) | −25 | hyper-heat; the one selected unit with an open extended submittal |
| 1 | Lennox **SL22KLV-036** | R-454B | 9.2 kW | −28.9 | top Tier-1 centroid candidate; premium brand |
| 1 | Carrier/Midea **D5CUHAH18AAK** (D5F) | R-454B | 5.6 kW | −30 | newest R-454B, 95 % retention, −30 °C |
| 2 | Carrier/Midea **D5CURAH24AAK** (Crossover) | R-454B | 7.0 kW | −25 | Tier-2 centroid |
| 2 | Carrier/Midea **DLCURAH24ABK** (DLF) | R-410A | 7.2 kW | −30 | Tier-2 candidate, deeper cold range |
| 2 | Samsung **AM048FCMDCG** (DVM S Mini) | R-32 | 15.8 kW (4-ton) | −25 | Tier-2 candidate, distinct brand |
| 3 | Gree **GUD36W/A-D(U)** | R-410A | 7.0 kW | −30 | **the single most-installed unit** in the ERS data |
| 3 | Mitsubishi M-series **MUZ-GS12NAH** | R-410A | 4.2 kW | −20 | Tier-3 candidate, small mini-split |
| 3 | Carrier/Midea **MO1AE-H48B-2A** (MO1) | R-454B | 14.1 kW (4-ton) | −25 | Tier-3 candidate, large ducted |

The selection is fully data-driven — swapping a model is just editing the list
in `extract_neep_points.py` and re-running. The tiering, and hence which units
sit near each centroid, is Phase 3a.

### Data acquisition — what is public and what is not

The prompt asked for manufacturers' extended engineering data books (capacity &
input power at many outdoor temperatures). The honest finding, confirmed by
downloading the actual documents (saved under `data/raw/spec_sheets/<brand>/`):

- **Only a minority of makers publish extended multi-temperature tables openly.**
  Mitsubishi and Fujitsu do; most others publish only the AHRI 47/17 (± 5) °F
  ratings on submittal/spec sheets, with the fuller "expanded ratings" behind a
  contractor login (e.g. LennoxPROs.com). Documents inspected:
  - Lennox **SL22KLV Engineering Handbook** (Form 211065, Jan 2025),
    `lennox/ehb_sl22klv_2501.pdf`, <https://www.lennox.com/dA/1dcc6642ff/ehb_sl22klv_2501.pdf>
    — product/spec + TXV/electrical data only; **no** temperature-vs-capacity
    table (those are the gated "expanded ratings").
  - Gree **FLEXX Ultra 18 Service Manual** (GC202006-I),
    `gree/FLEXX-Ultra-18-Service-Manual.pdf`, and the FLEXX Ultra submittal
    (greehvac.ca) — electronics / PCB / sensor-resistance tables and 47/17 °F
    ratings only; **no** extended heating-performance table.
- **The NEEP `HP Report` itself is the usable extended source.** It carries
  AHRI-certified **capacity + input power + COP at 47/17/5 °F and the Lowest
  Cataloged Temperature (LCT)**, at min/rated/**max** compressor speed, for
  every unit (NEEP columns 53–86). That is four real certified temperature
  points per model — 8.3 / −8.3 / −15 °C + LCT — spanning the whole
  Ottawa-relevant range. These max-speed points are therefore the **backbone**
  of every air-source curve. `extract_neep_points.py` writes them (median
  across each unit's certified indoor pairings, matching Phase 3a) to
  `data/interim/neep_points_selected.json`.
- **Mitsubishi is the one selected model with an open extended submittal**, used
  as an independent cross-check: **Submittal Data PVA-A36AA7 & PUZ-HA36NKA**
  (Form SB_PVA-A36AA7_PUZ-HA36NKA_202401), `mitsubishi/…202401.pdf`,
  <https://www.mitsubishitechinfo.ca/sites/default/files/SB_PVA-A36AA7_PUZ-HA36NKA_202401.pdf>,
  "Performance" table p.2 (max-capacity heating at 47/17/5/−13 °F).

Unit conversion: NEEP capacities BTU/h → kW × 0.29307107/1000; input-power
columns are kW (not W as the header label suggests); COP is dimensionless.
We derive power from capacity ÷ COP where needed, so COP + capacity suffice.

### Curve construction (`build_hp_curves.py`)

All curves are evaluated on a common grid −30 … +15 °C, 0.5 °C step, at
**max-compressor operation** (the point a cold home calling for full heat
actually draws).

1. **Piecewise-linear** through the certified max-speed points, in SI.
2. **Cold end** (below the coldest published point): capacity extrapolated
   linearly on the last segment's slope; COP floored at
   (coldest published COP − 0.3); **output zero below the model's minimum
   operating temperature** (compressor lockout). For every selected model the
   coldest NEEP point is the LCT, which equals the min-op temp, so in practice
   the curve goes straight to zero at lockout with essentially no extrapolation
   region — the certified data already reaches the lockout temperature.
3. **Defrost derate: 7 % on COP across −7 … +4 °C.** The NEEP/submittal
   max-capacity points are **steady-state maxima, not defrost-integrated**
   (the AHRI HSPF-integrated cyclic ratings are the *rated*, not *max*, points),
   so a defrost penalty in the frost-prone band is appropriate and is recorded
   `defrost_inclusive: false` for every model. Implemented as a **continuous**
   multiplicative factor (0.93 in the core, 1.0 outside, linear 1 °C ramps just
   inside each band edge) so the curve stays continuous at the band edges rather
   than stepping.
4. **Normalization:** each per-model curve also gives capacity as a **fraction
   of rated capacity @47 °F**, so the UI scales the shape to any nominal size.
   Absolute kW is retained too.
5. **Warm end** (above 47 °F, up to +15 °C): capacity and COP extrapolated
   linearly on the warmest segment's slope (little heating load lives here).

### Cross-check against NEEP / manufacturer points (> 10 % flagged)

Because the air-source curves are *built from* the NEEP 47/17/5 °F points, the
self-check against them is ~0 by construction (reported anyway in each model's
`neep_cross_check`). The meaningful independent check is Mitsubishi's submittal
vs the NEEP-derived curve. Result — **one deviation > 10 % flagged**:

- **PUZ-HA36NKA, 5 °F max-capacity COP: submittal 2.17 vs curve 1.92 (−12 %).**
  Investigated: the submittal pairs the outdoor unit with the **PVA-A36AA7 air
  handler**, whereas the NEEP median is across the certified **ducted P-series**
  combos; both are AHRI-certified, they simply differ by indoor coil. Capacities
  match (both 38 000 BTU/h @ 5 °F). At 17 °F (2.27 vs 2.19, +3.5 %) and −25 °C
  (1.50 vs 1.45, +3.4 %) they agree. We keep the **NEEP** value as the backbone
  for cross-model consistency and record the flag; it is a pairing difference,
  not an error.

### Per-model non-monotonic capacity — real, and how it is handled

Several real cold-climate inverters have a **max-capacity envelope that dips at
17 °F** (e.g. Gree GUD36: 5 °F max cap 20 000 BTU/h > 17 °F max cap 17 800;
Lennox SL22KLV similar), because the 17 °F *max* rating is conservative relative
to the flash-injection-boosted 5 °F point. This is a genuine AHRI rating
artefact, not noise. **Per-model curves are left faithful** to it (COP is always
monotone; capacity may dip ≤ ~11 %). The **aggregate** tier / average-installed
capacity curves — the ones the UI actually scales — are made monotone with a
pool-adjacent-violators (isotonic) pass, documented in the code, so the
"capacity rises with temperature" invariant the tool relies on holds.

### Tier and "average installed" aggregation

- **Tier curve** = equal-weight mean of the tier's member normalized curves at
  each grid temperature, over members still operating there (locked-out members
  excluded from the mean, not counted as zero); capacity made monotone by
  isotonic; tier lockout = median member min-op temp.
- **Average installed** = **popularity-weighted** blend of the 8 unique NEEP
  units matched to the top-10 AHRI reference numbers in the ERS retrofit data
  (Phase 3a), weight = ERS occurrence count (total 31 237). It leans baseline
  (the Gree GUD36 dominates), consistent with the Phase-3a weighted COP@5 °F
  ≈ 1.87. Lockout = popularity-weighted median min-op.

### GSHP curves (COP vs entering water temperature)

No NEEP equivalent; modelled per PLAN.md §4 via entering water temperature
(EWT). Two representative water-to-air units, digitized from the manufacturers'
**full-load heating performance tables** (EAT 70 °F, highest cataloged loop
flow, 0 % antifreeze), saved under `data/raw/spec_sheets/gshp/`:

- **WaterFurnace 7 Series 700A11 (036)** — premium variable-speed. Spec Catalog
  **SC2700AN**, "Performance Data · 036 - 100 % Full Load" p.34.
  <https://www.waterfurnace.com/literature/7series/sc2700an.pdf>
- **WaterFurnace 5 Series 500A11 (ND038, dual-capacity high speed)** — mainstream
  two-stage. Spec Catalog **SC2500AN**, "Performance Data · ND038 High Speed"
  p.62; AHRI/ISO 13256-1 ratings p.6 (GLHP heating @ 32 °F brine COP 4.2).
  <https://www.waterfurnace.com/literature/5series/sc2500an.pdf>

Heating COP vs EWT (°C), full load, highest flow:

| EWT | −6.7 | −1.1 | 4.4 | 10.0 | 15.6 | 21.1 |
|---|---|---|---|---|---|---|
| 7 Series COP | 3.32 | 3.79 | 4.46 | 4.83 | 5.36 | 5.84 |
| 5 Series COP | 3.34 | 3.80 | 4.21 | 4.59 | 4.88 | 5.14 |

**Ottawa-area vertical closed loop:** undisturbed ground ≈ 8.5 °C; a well-sized
borefield draws the loop down through the heating season to a **design minimum
EWT ≈ 0 °C (32 °F)**, typical winter mean ≈ 4 °C, shoulder ≈ 7 °C. Catalog COP is
0 % antifreeze; a real loop uses antifreeze, so apply ≈ 0.91 (20 % propylene
glycol @ 32 °F, WaterFurnace antifreeze table) for a conservative design-point
estimate. At the 0 °C design point the units give COP ≈ 3.8 — roughly double a
cold-climate ASHP at Ottawa's −25 °C design temperature, the expected GSHP
advantage. The ISO 13256-1 GLHP heating rating (COP 4.2 @ 32 °F brine, 5 Series)
sits above the water-based performance-table value (3.8 @ 30 °F) because the ISO
point uses EAT 68 °F and its own rated flow; we use the internally consistent
performance-table shape and note the ISO anchor.

### Tests (`test_hp_curves.py`, 7/7 pass)

- COP monotonic (non-decreasing in T) above −15 °C, checked **outside** the
  −7…+4 °C defrost band (the derate is a deliberate local COP reduction, so
  global monotonicity across the band is neither expected nor asserted);
- the in-band derate equals the documented 7 % factor;
- capacity monotonic above −15 °C for the tier and average-installed aggregates;
- continuity within each curve's operating range (the lockout-to-zero cliff is
  an intentional discontinuity and is excluded);
- lockout: zero capacity / undefined COP strictly below each model's min-op
  temperature, positive capacity above it;
- GSHP COP strictly increasing with EWT;
- each model's capacity curve passes through its NEEP certified points (≤ 3 %).

### Assumptions & limitations

- Max-speed envelope only; the engine handles cycling below min-capacity load
  separately (PLAN.md §3) — min/rated-speed COP curves are not built here.
- Extended multi-point tables were only openly available for Mitsubishi (ASHP)
  and the WaterFurnace GSHPs; all other air-source curves rest on the four
  AHRI-certified NEEP points. This is real certified data but coarser between
  47 °F and 17 °F (an 8.3 → −8.3 °C gap with no intermediate certified point);
  the piecewise-linear interpolation there is an approximation.
- The 7 % defrost figure is the PLAN.md default, not a per-model measurement.
- GSHP capacity is modelled but the tool primarily uses GSHP COP(EWT); loop
  sizing / borefield dynamics are out of scope (screening only).
- Only two GSHP units (premium variable-speed + mainstream two-stage); a third
  (single-stage budget) could be added the same way if needed.

---

## Heating-load archetypes (Phase 4)

Builds `UA` (W/K) and balance-point temperature (`Tbalance`) per city ×
archetype from the ERS/EnerGuide web parquet
(`Python/ers_web_pipeline.py` output, `C:\ERS\web\ers_web_<PROV>.parquet`).
Built by `pipeline/build_archetypes.py`. Output: `data/processed/archetypes.json`
(4 archetypes × 5 cities = 20 rows) and `data/interim/archetype_validation.csv`.

### PRE-retrofit values, not POST

Every figure (design heat loss, floor area, annual heating energy) is taken
from the ERS record's **D-evaluation (pre-retrofit)** columns, not the
E-evaluation (post-retrofit) columns the rest of the ERS pipeline usually
pairs against. The heat pump tool models a homeowner **replacing existing
heating in an as-found, un-retrofitted home** — the archetype should
describe what that home looks like *before* any envelope work, not after.
(The underlying parquet still only contains D/E-paired houses per
`ers_web_pipeline.py`'s matching logic — pairing was not required for this
step conceptually, but the same file was reused since it's already on disk
with FSA + design heat loss + floor area + heating energy in one place; only
the `Pre_*` columns are read.)

### City selection: FSA prefix

| City | FSA prefixes | Basis |
|---|---|---|
| Ottawa | K1, K2, K4 | K1/K2 = urban core; K4 = Kanata/Stittsville (outer Ottawa suburb, still City of Ottawa). K0/K6/K7/K8/K9 (rural Ottawa Valley, Cornwall, Kingston, Pembroke/Peterborough) excluded. |
| Toronto | M | All M-prefix FSAs are Toronto (proper + former inner suburbs Etobicoke/North York/Scarborough — amalgamated City of Toronto). |
| Montreal | H | All H-prefix FSAs — Montreal Island + Laval (H7/H9). |
| Calgary | T2, T3 | Standard Calgary postal geography. |
| Edmonton | T5, T6 | Standard Edmonton postal geography. |

### Archetype definitions

`BldgType` (ERS `TYPEOFHOUSE`, lowercased for matching):

- **Detached** = `Single Detached` / `Single detached` (two capitalizations
  present in the source data, both matched), split into 3 vintage bins by
  `YEARBUILT`: **pre-1980** (< 1980), **1980–2005** (1980–2005 inclusive),
  **post-2005** (> 2005).
- **townhouse_row** = `Row house, end unit` + `Row house, middle unit`
  (not split by vintage — too few rows per city × vintage cell otherwise).
  `Double/Semi-detached`, `Attached Duplex/Triplex`, `Apartment Row`,
  `Mobile Home` are **excluded from all 4 archetypes** — they don't map
  cleanly onto "detached" or "townhouse/row" and are a small share of the
  data (semi-detached is the largest of these, ~4–7% of rows per province).

Plausibility filters applied before taking medians (drops parsing junk /
data-entry outliers, not real variation): `FloorArea` 40–1000 m², `YearBuilt`
1900–2026, `Pre_HeatLoss` 1–50 kW, `Pre_HeatSeasonalCOP` 30–400 (%),
`Pre_HeatDelivered` (see below) 500–100,000 kWh/yr.

Cells below **30 homes** are still output but would be flagged low-confidence
in a UI (none of the 20 final cells fell below this threshold — the smallest
is Montreal post-2005 detached at n=143).

### Fuel-input vs. delivered heat energy — a necessary conversion

`Pre_HeatEnergy` (ERS `EGHFURNACEAEC`, already in `ers_web_pipeline.py`'s
output) is the heating system's annual **fuel/electricity input**, not the
heat actually delivered to the building. For a gas furnace at 92% AFUE,
input is delivered ÷ 0.92 — using it directly would inflate the calibration
target for combustion-heated homes (the large majority; natural gas is
Pre_HeatFuel for ~92% of ON rows) relative to electric-baseboard homes,
whose input ≈ delivered.

Since the `Load(h) = UA × max(0, Tbalance − Tout(h))` model represents heat
**delivered** to the building (PLAN.md §5), the archetype's annual target is

```
Pre_HeatDelivered = Pre_HeatEnergy × (Pre_HeatSeasonalCOP / 100)
```

using ERS's `EGHFURSEASEFF` (seasonal efficiency, an AFUE-style percentage
for combustion equipment; ≈100 for electric-resistance baseboard). This is
the annual heating energy figure reported in `archetypes.json` and compared
against the reconstructed UA×HDH load.

### UA from design heat loss — indoor/outdoor design temperature

`Pre_HeatLoss` (ERS `EGHDESHTLOSS`, kW) is HOT2000's steady-state design
heat loss: envelope + infiltration loss at the home's local design
conditions and the program's default indoor setpoint (**21 °C**, the
main-living-space heating design temperature HOT2000 uses).

```
UA (W/K) = design_heat_loss_kW × 1000 / (21 °C − T_design_city)
```

**T_design_city** (the outdoor design temperature) is **not** taken from a
published NBC table — it's computed directly from our own data: the
**2.5th-percentile January temperature** in each city's ECCC hourly record
(`data/interim/weather_hourly.csv`, 2019–2026, 8 years), the same
percentile convention the National Building Code's "January 2.5%" design
temperature uses, just computed from a shorter record (8 years) than NBC's
30-year climate normal. Chosen over hard-coding published NBC figures so
the whole pipeline stays reproducible from data already fetched in Phase 2,
and because a spot-check landed within ~2–4 °C of commonly-cited NBC 2020
values for these five stations (e.g. Ottawa ≈ −25 °C published vs. −22.8 °C
computed) — close enough for a screening-tool UA estimate, and internally
consistent since the same weather source feeds the TMY calibration below.

| City | T_design (2.5%-ile Jan, computed) |
|---|---|
| Ottawa | −22.8 °C |
| Toronto | −17.1 °C |
| Montreal | −21.1 °C |
| Calgary | −28.6 °C |
| Edmonton | −32.4 °C |

Each home's *actual* HOT2000 design temperature is set by its own weather
station/FSA, not the single city value used here — using one city-wide
`T_design` to back out UA from a *population median* design heat loss is a
population-level simplification, acceptable for archetype-level UA but not
exact per-house.

### Balance-point calibration

Per PLAN.md §5 ("assuming internal + solar gains offset load above
~15–16 °C"), `Tbalance` is meant to sit below the 21 °C indoor setpoint by
however much internal gains (people, appliances, lighting) and solar gains
typically offset. Rather than hard-coding that offset, **`Tbalance` is
solved by bisection** so that applying the archetype's UA to the city's
full TMY year (`data/interim/tmy_hourly.csv`, 8,760 h) reproduces the
observed `Pre_HeatDelivered` annual energy:

```
annual_load_kWh(Tbalance) = UA × Σ_h max(0, Tbalance − Tout(h)) / 1000
solve for Tbalance:  annual_load_kWh(Tbalance) = Pre_HeatDelivered
```

`annual_load_kWh` is monotonically non-decreasing in `Tbalance` (raising it
only adds positive-Δ hours), so bisection over `Tbalance ∈ [8, 21] °C` is
well-posed; every one of the 20 archetypes converged inside that range
(none clamped to a bound).

### Validation: reconstructed vs. observed annual load — 20/20 within ±10 %

Because `Tbalance` is *solved for* to hit the target exactly, this
validation is close to tautological by construction (all 20 cells land
within ±0.1 % — see `data/interim/archetype_validation.csv`) — the
meaningful check is not "did it match" but "did the required `Tbalance`
come out physically plausible."

### Finding: calibrated Tbalance (8–12 °C) is lower than the ~15–16 °C planning assumption

All 20 calibrated balance points land in an **8.1–12.3 °C** range —
noticeably below the 15–16 °C PLAN.md §5 anticipated (and below the
16–18 °C range PLAN.md's Phase-6 UI section mentions as a "lower for
tighter homes" starting point). This is not a bug — it's what the
bisection is forced to, given the two independently-measured ERS inputs
(median design heat loss → UA, and median annual delivered heating energy)
combined with a full TMY year:

- At the "textbook" `Tbalance ≈ 16 °C`, the archetypes' own UA × TMY-HDH
  would predict **far more** annual heating energy than the ERS median
  actually shows (e.g. Ottawa pre-1980 detached: ~41,000 kWh at 18 °C vs.
  the observed 22,990 kWh) — roughly **1.8×** too much.
- Two plausible physical contributors, neither isolated in this pass:
  (1) HOT2000's design heat loss is a **steady-state, no-solar, no-internal
  -gains, design-wind-speed** calculation — it can overstate the
  *average-weather* effective UA relative to real shoulder-season
  performance (e.g. reduced wind, some solar gain even in the design-heat
  -loss model's excluded terms) — and (2) **real occupant behaviour**
  (night/away thermostat setbacks, not modelled at all here) reduces
  realized annual heating hours below what a constant-setpoint TMY
  simulation predicts.
- **Kept as-is** rather than overridden with a fixed 15–16 °C, per the
  task's calibration instruction — but flagged here as a genuine finding,
  not silently absorbed. The simulation engine (Phase 5) should treat
  `Tbalance` as "the value that reproduces this archetype's *measured*
  annual consumption," not as a literal physical gains-offset temperature.

### Cross-check against NRCan published values

**NRCan, *Cold-climate air source heat pumps: Assessing cost-effectiveness,
energy savings and greenhouse gas emissions reductions in Canadian homes***
models a "two-storey detached home constructed before 1980" (their
Archetype A) with a peak/design heating load of **10.7 kW** when located in
Toronto (their Figure 1, temperature-vs-load regression).

Our Toronto `pre_1980_detached` archetype: **design_heat_loss = 16.26 kW**
(median of n=16,283 ERS-audited homes) — **+52 %** above NRCan's figure.

The likely driver is **floor area**, not methodology: NRCan's Archetype A
is a single fixed reference house (a specific HOT2000 model, typically
sized ~130–150 m² in this family of NRCan/CanmetENERGY studies), while our
figure is the **median across the full population** of Toronto pre-1980
detached homes in the ERS database — median floor area **200.5 m²**, i.e.
~35–50 % larger than a typical fixed reference house, which tracks
reasonably with the +52 % heat-loss delta for buildings of similar vintage
and insulation levels (heat loss scales close to linearly with envelope
area for a fixed shape/insulation level). Design-temperature choice is not
the driver — our computed Toronto T_design (−17.1 °C) is close to the NBC
2.5 % figure NRCan's own HOT2000 run would use. **Not resolved further in
this pass** — a stronger cross-check would require the NRCan report's own
archetype floor areas (not found in the search results used here), or
restricting our ERS sample to the same floor-area band NRCan used.

### Assumptions & limitations

- Single indoor design setpoint (21 °C) used for every home; ERS/HOT2000
  runs actually vary slightly by exact model inputs.
- One `T_design` and one TMY series per **city**, applied to every ERS home
  matched to that city's FSA prefixes — real intra-city variation (e.g.
  Ottawa's K4 suburb vs. K1 downtown) is not modelled.
- `townhouse_row` is not vintage-split (see above) — a pre-1980 townhouse
  and a post-2005 townhouse are pooled into one archetype per city.
- Semi-detached and duplex/triplex homes are excluded entirely, not folded
  into either detached or townhouse/row.
- The low calibrated `Tbalance` finding (above) means these archetypes are
  tuned to reproduce **average annual energy**, not necessarily a
  physically realistic **hourly shape** — PLAN.md §5's cross-check against
  the NRCan Toronto 4-archetype load-*shape* report (Phase 5/7) is the
  right place to validate the hourly profile, not this step.

---

## Simulation engine (Phase 5)

The browser-side core: `app/engine.js`, a single dependency-free pure function
`simulate(opts)` that runs one heating year hour-by-hour and returns annual +
monthly **energy-by-source** and **GHG-by-category** for a BASE case (existing
gas/oil furnace or electric baseboard) and a PROJECT case (an air- or
ground-source heat pump with optional backup). No DOM, no imports — the same
file loads in Node (`module.exports`) and the browser (`window.HeatPumpEngine`).

Two amendments to the PLAN.md Phase 5 prompt were applied (per the task brief):

1. **Heat-pump input is a normalized tier curve from `hp_curves.json`.** The
   engine takes `{ T_C[], cap_frac_of_rated47[], COP[] }` (any per-model,
   per-tier or `average_installed` curve — all share the schema) and scales the
   fractional capacity by a **user-selected nominal capacity** (kW @47 °F):
   `capacity_kW(T) = nominalCap_kW × cap_frac_of_rated47(T)`. COP is
   size-independent and read straight off the curve. **Lockout is governed by
   the curve's own `min_op_temp_C`, not by the COP array being `null`** — the
   aggregate tier/average curves keep a non-null COP below their *median*
   lockout temperature (e.g. Tier 1's curve reports COP 1.42 at −30 °C although
   its `min_op_temp_C` is −28.9 °C), so `min_op_temp_C` is the single authority.
2. **Hourly grid EF comes from the Phase-2 EF surface** (`ef_surface_*.json`)
   with an **average / marginal toggle** (methodology decision #1). For each
   hour, `EF = level × shape(tbin, hour, season)` where `shape` uses the exact
   thin-bin fallback of `build_ef_surface.lookup_shape` (fine → coarse_ts →
   coarse_t → global, <20 h). The `efMode` flag selects **both** the level
   index and the shape-ratio field (0 = average, 1 = marginal); `efLevel` can
   override the reference level with any stored historical year to draw the
   variance band (decision #2's second sub-point).

### Per-hour model

```
load_kW(h)      = UA_W_per_K/1000 × max(0, Tbalance − Tout(h))      (= kWh over 1 h)
```

Above the balance point nothing runs (load 0). Otherwise:

- **Base case** delivers `load` from the incumbent system: `fuel_in = load /
  efficiency` (AFUE/seasonal fraction), combustion GHG `= combustion_EF ×
  fuel_in`; electric baseboard instead draws grid electricity at the hourly EF.
- **Project case** dispatches the HP per the **control strategy**:
  - `load-exceeds-capacity` — HP runs whenever operating (T ≥ min-op), delivering
    `min(load, capacity)`; backup covers the remainder.
  - `lockout` — HP is switched **off entirely** below `lockoutTemp_C`, *regardless
    of the capacity it could still deliver there*; all load goes to backup.
  HP electricity `= hp_heat / COP(T)`; backup electricity `= backup_heat /
  backup_eff` (or backup fuel for a gas/oil backup). HP + backup electricity are
  grossed up by **line losses** and costed at the hourly grid EF.

Cycling below minimum capacity (PLAN.md §3) is **not** separately modelled — only
the max-compressor curve exists (Phase 3b), so a modulating inverter is costed at
its max-speed COP. Real part-load COP is usually *higher*, so this is
conservative; documented as a limitation.

### Emission categories & constants (ECCC NIR)

GHG is split into **combustion / electricity / refrigerant / upstream-methane /
upstream-oil** (kg CO2e/yr). Direct combustion factors, g CO2e/kWh of fuel input
(HHV basis, matching the efficiency convention):

| Fuel | g CO2e/kWh | Basis |
|---|---|---|
| Natural gas | 181 | 1.921 kg CO2e/m³ ÷ 10.55 kWh/m³ |
| Light fuel oil (No.2) | 275 | ~2.75 kg CO2e/L ÷ ~10 kWh/L |
| Propane | 214 | 1.55 kg CO2e/L ÷ ~7.2 kWh/L |
| Electric | 0 | grid EF only |

Lifecycle terms are user sliders (PLAN.md §6), not baked in:

- **Refrigerant** (annual, amortized, PROJECT only):
  `charge_kg × (leakRate_frac + eolLossFrac/lifetimeYears) × GWP`.
- **Upstream methane**: `methaneLeakPct%` of gas throughput (mass, via
  10.55 kWh/m³ and 0.68 kg/m³, ~100 % CH₄) × `methaneGWP` (default 28, AR5 100-yr).
- **Upstream oil**: optional adder `oilUpstreamFrac` × oil combustion.
- **Line losses**: default 5 % on delivered electricity.

Calendar (for season/hour-of-day, which key the EF surface) is derived from the
hour index assuming the series starts Jan 1 (matching TMY); an 8784-length
series is treated as a leap year. Hour-of-day is `1..24` to match the surface's
convention.

### Validation

`app/engine.test.js` (Node) and `pipeline/validate_engine.py` (a faithful Python
port) run the **same five hand-computed cases** and assert **identical results to
4 decimals** — both pinned to one shared set of EXPECTED constants:

1. **−10 °C, load > capacity, electric backup** — load 7.0 kWh, HP delivers 5.0,
   backup 2.0; HP elec 2.0 + backup elec 2.0; project electricity GHG
   0.42 kg (avg) / 2.10 kg (marginal); base gas fuel 8.75 kWh, combustion
   1.58375 kg. Exercises dispatch, backup switchover, and the avg/marginal toggle.
2. **+20 °C above balance point** — every energy and GHG term is exactly 0.
3. **Lockout at −5 °C, hour at −10 °C** — HP ignored despite 5 kW available; all
   7.0 kWh to backup, HP run-hours 0, lockout-hours 1.
4. **Refrigerant** — 3 kg, 5 %/yr + 80 % EOL/15 yr, GWP 2256 → 699.36 kg/yr.
5. **Upstream methane** — 100 kWh gas, 2 % leak, GWP 28 → 3.609479 kg/yr.

`validate_engine.py` also runs `node app/engine.test.js` when Node is present;
in the build environment here Node was unavailable, so the JavaScript engine was
verified through its identical Python mirror (all assertions pass) plus the
real-data smoke run below.

### Real-data smoke check (Ottawa pre-1980 detached, Tier-1 ASHP)

Driving the engine with the real Ottawa TMY series, the ON EF surface, the Tier-1
curve sized to the archetype's 16.3 kW design load, gas base @92 % and electric
backup:

- reconstructed annual **load 22,986 kWh** vs the archetype's calibrated target
  **22,990 kWh** (0.02 %) — confirms the load/UA/Tbalance/calendar path;
- base gas fuel **24,985 kWh** = load ÷ 0.92 exactly; **seasonal COP 2.32**,
  backup share **0.4 %** (unit sized to design load), 1 lockout hour;
- **average-EF grid → HP saves 63 %** of GHG; **marginal-EF grid → HP is 18 %
  *worse* than gas** — reproducing methodology decision #1's central warning
  (Ontario's ~500 g/kWh gas margin flips the ASHP-vs-gas answer) directly from
  the wired-up engine.

### Assumptions & limitations

- Max-speed COP only (no part-load/cycling curve) — conservative, see above.
- Single provincial EF surface applied to each city's own temperature series
  (inherited Phase-2 simplification); the surface's marginal channel is Phase-1's
  simple "flat gas EF whenever gas > 0", so marginal shape ≈ 1 almost everywhere.
- `reference_level` (latest complete year) used as the "typical current grid";
  Ontario's level is actively rising, so a forward year could be higher.
- GSHP is supported (EWT curve + antifreeze derate) but drives on a supplied EWT
  series/constant; borefield dynamics are out of scope (screening only).
- No unmet-load penalty beyond counting hours when `backup: none` can't cover the
  gap.

---

## Validation against published benchmarks (Phase 7)

Compares the finished tool's annual outputs against published Canadian
heat-pump studies. The task: confirm the tool lands in the same territory as
the literature, and — per PLAN.md's flag — investigate any deviation **> 30 %
that has no methodological explanation** as a potential bug. **Result: no such
unexplained deviation was found.** Every notable gap between the tool and a
published number is traceable to one of three documented causes (in order of
size): (1) **average vs. marginal grid EF**, (2) **grid vintage** (the tool is
calibrated to the *2025* grid; most published studies used a 2019–2021 grid),
and (3) **archetype floor area** (the tool uses the ERS *population median*,
~200 m², vs. the single fixed reference house in the NRCan study). One genuine
UI bug *was* found and fixed while running these scenarios (Quebec
baseboard→ASHP headline percentage — see the end of this section).

### How the tool figures were produced

The exact browser configuration was reproduced offline by driving the Phase-5
engine (`pipeline/validate_engine.py`'s `simulate()`, the faithful Python
mirror of `app/engine.js`) with the real processed data files, replicating
`heatpump.html`'s `buildOpts()` byte-for-byte: **archetype `pre_1980_detached`,
Tier-1 (cold-climate premium) ASHP, electric backup, HP-leads control, unit
auto-sized to the archetype's design heat loss**, lifecycle defaults (R-410A,
1 % upstream methane, 5 % line loss). Each city was run with a gas base
(92 % AFUE) and an electric-baseboard base, on **both** the average and marginal
grid basis. Reference grid levels (2025, from `ef_surface_*.json`):
ON 96.9 g/kWh avg / 500 marg; AB 414.5 avg / 540 marg; QC ≈ 0.01 either way.

### Tool outputs — annual, per city (Tier-1 ASHP, pre-1980 detached)

**Energy & seasonal performance** (grid-basis-independent):

| City | Design load / unit size | Annual heat (kWh) | Seasonal COP | Backup share | Gas base fuel (kWh) | ASHP electricity (kWh) |
|---|---|---|---|---|---|---|
| Ottawa | 16.3 kW / 16.5 kW | 22,986 | **2.32** | 0.4 % | 24,985 | 9,977 |
| Toronto | 16.3 kW / 16.5 kW | 23,333 | **2.54** | 0.1 % | 25,362 | 9,217 |
| Montreal | 16.0 kW / 16.0 kW | 22,107 | **2.37** | 0.3 % | 24,029 | 9,379 |
| Calgary | 13.5 kW / 13.5 kW | 20,120 | **2.33** | 0.2 % | 21,870 | 8,676 |

**GHG — gas furnace → ASHP** (kg CO₂e/yr; Δ% = reduction, negative = ASHP worse):

| City | Base (gas) | ASHP — avg grid | Δ% avg | ASHP — marg grid | Δ% marg |
|---|---|---|---|---|---|
| Ottawa | 4,973 | 1,600 | **−68 %** | 5,496 | **+11 %** |
| Toronto | 5,048 | 1,322 | **−74 %** | 5,097 | **+1 %** |
| Montreal | 4,783 | 251 | **−95 %** | 251 | **−95 %** |
| Calgary | 4,353 | 4,136 | **−5 %** | 5,131 | **+18 %** |

**GHG — electric baseboard → ASHP** (kg CO₂e/yr):

| City | avg: base → ASHP (Δ%) | marg: base → ASHP (Δ%) |
|---|---|---|
| Ottawa | 2,996 → 1,600 (−47 %) | 12,068 → 5,496 (−54 %) |
| Toronto | 2,606 → 1,322 (−49 %) | 12,250 → 5,097 (−58 %) |
| Montreal | 0.2 → 251 (**increase**, refrigerant only) | 0.2 → 251 (**increase**) |
| Calgary | 9,037 → 4,136 (−54 %) | 11,408 → 5,131 (−55 %) |

### The benchmarks

| Source | Relevant published figure |
|---|---|
| **NRCan / CanmetENERGY-Ottawa, 2022** — *Cold-Climate Air Source Heat Pumps: Assessing Cost-Effectiveness, Energy Savings and GHG Emissions Reductions in Canadian Homes* (M154-149/2022E). HOT2000; four EnerGuide archetypes (pre-1980 → Net-Zero-Ready) — the **same modelling family** as this tool. | gas→ASHP **"significantly reduces"** GHG in BC/MB/QC/NL and **Ontario** ("80–90 % non/low-emitting"); **increases emissions vs a gas furnace in Alberta and Saskatchewan**; vs electric resistance, **"negligible savings"** in clean-grid provinces but real savings in AB/SK. Explicitly **"calculated based on average annual emissions factors."** Cold-climate rating = COP ≥ 1.8 @ −15 °C. Notes that a **marginal** (gas) Ontario factor *reduces* the reduction — "by about 5 %" for **hybrid** systems. Archetype A (pre-1980) peak load: Toronto 11.6, Ottawa 13.8, Montreal 13.2, Calgary 14.3 kW. |
| **Pembina Institute / Canadian Climate Institute, 2023** — *Heat Pumps Pay Off*. | "Even when running on relatively **emissions-intensive** electricity, heat pumps emit **between 20 and 30 % less** carbon than gas furnaces"; heat pumps use "**up to 65 % less energy** than standard electric resistance heating." |
| **Efficiency Canada, 2023** — *Canadian Heat Pump Myth Buster*. | Field **seasonal COP 2.41** (maintaining COP > 1 for >90 % of the heating season); modelling shows **">95 % reduction in two-thirds of fossil-fuel replacement scenarios, and 49–77 % vs electric resistance"**; "≥ 50 % less electricity than baseboard"; over 2018–2022 only **0.3 % of heating hours** couldn't be met by the heat pump alone in most cities. |
| **The Atmospheric Fund / IESO**, 2024 — *Ontario Electricity Emissions Factors and Guidelines* (the tool's own grid-EF calibration source). | Average (AEF) is for **inventory / historical** accounting; **marginal (MEF)** is the correct basis for **"estimating future carbon emissions from a fuel-switching project"** — exactly the heat-pump case. Ontario AEF ≈ high-60s–80 g/kWh (2023–24); marginal on-peak/off-peak far higher. |

### Tool vs. benchmark — with the reason for each delta

| Metric | Tool | Benchmark | Delta | Explanation |
|---|---|---|---|---|
| **Seasonal COP** (4 cities) | 2.32–2.54 | 2.41 (Efficiency Canada field); ≥ 1.8 @ −15 °C rating floor | within ±5 % | none needed — direct hit. |
| **Backup share of load** | 0.1–0.4 % | "0.3 % of heating hours" unmet (2018–2022) | agrees | unit auto-sized to design load, so backup is rare. |
| **Energy saved vs baseboard** | ~55 % less electricity | "up to 65 %" (CCI); "≥ 50 %" (Eff. Canada) | inside range | tool sits at the lower-middle (Tier-1, cold cities); "up to 65 %" is the warm-climate/premium ceiling. |
| **gas→ASHP, ON (avg)** | −68 to −74 % | "significant reduction" (NRCan, avg basis) | consistent | NRCan used a **2020–21 Ontario grid (~32–41 g/kWh)**; the tool uses **2025 (97 g/kWh, ~3× dirtier)**, so its average-basis reduction is *smaller* than NRCan-era — grid vintage, fully expected. |
| **gas→ASHP, ON (marg)** | ~0 to +11 % (≈ break-even/worse) | NRCan: marginal "reduces reduction ~5 %" (hybrid) | **> 30 % vs NRCan's *average* headline — but fully explained** | (a) avg vs marginal is the whole point of the tool's toggle; (b) NRCan's ~5 % is for a **hybrid** (ASHP electricity is a small slice); a **full** ASHP prices *all* its kWh at the margin; (c) the tool's marginal channel is a deliberately pessimistic "**gas = 500 g/kWh whenever gas runs**" upper bound (Phase 1), harsher than a seasonal-hourly marginal that credits some hydro/nuclear hours. This is the honest RAP/TAF marginal view, and it is the *default* on purpose. |
| **gas→ASHP, AB** | −5 % (avg) / +18 % (marg) | NRCan: **"increases emissions in Alberta"** | direction matches | NRCan's AB grid was ~565–597 g/kWh (2020–21) → clear increase. The tool's **2025 AB grid (414 g/kWh, coal retired)** is much cleaner → average basis is now ~break-even; marginal still shows an increase, matching NRCan's sign. Grid vintage again. |
| **gas→ASHP, QC** | −95 % | NRCan: "significantly reduces" | matches | near-zero grid; the residual 5 % is refrigerant + the base's own combustion. |
| **gas→ASHP, moderate grid** | between −5 % (AB avg) and −74 % (ON avg); marginal ON/AB ≈ 0 to +18 % | Pembina/CCI "20–30 % less than gas" | tool brackets it | the "20–30 %" corresponds to a grid ≈ 150–250 g/kWh; ON-average (clean) beats it, AB and all-marginal fall below it. The tool spans the benchmark rather than contradicting it. |
| **baseboard→ASHP, ON/AB** | −47 to −58 % | NRCan: "negligible savings" (clean grids); Eff. Canada "49–77 %" | in Eff. Canada range | the tool's % ≈ the SCOP electricity saving (1 − 1/COP), robust to the avg/marginal choice. NRCan's "negligible" is an **absolute-tonnes** statement relative to the much larger gas case, not a percentage — no real conflict. |
| **baseboard→ASHP, QC** | small **increase** (refrigerant vs ~0-carbon grid) | NRCan: "negligible / near-zero" | matches (tool is *more* honest) | with QC electricity at ~0.01 g/kWh, the only GHG difference is refrigerant leakage, so the ASHP is marginally *worse* for GHG (though it still cuts energy/cost). |

### Sanity check on absolute magnitudes

The Ottawa pre-1980 gas base burns **24,985 kWh/yr ≈ 2,370 m³** of gas for space
heat (≈ 4.97 t CO₂e/yr). That is squarely in the expected 2,000–2,500 m³/yr band
for an older ~200 m² Ontario detached home — the archetype is not mis-scaled;
its loads are simply larger than NRCan's fixed reference house (Toronto
Archetype A ≈ 11.6 kW vs the tool's population-median 16.3 kW), the
floor-area difference already documented in Phase 4. Percentage deltas are
insensitive to this; absolute tonnes scale with it.

### Bug found and fixed: Quebec baseboard→ASHP headline percentage

Running the baseboard→ASHP scenario for Montreal surfaced a real UI defect (not
a methodology error). Because the QC grid is ~0.01 g/kWh, the baseboard base
case emits only **0.23 kg CO₂e/yr**, while the ASHP project case carries
**~251 kg/yr of refrigerant** leakage — so the percentage change is
`(0.23 − 251) / 0.23 ≈ −107,887 %`, which the verdict banner rendered verbatim
as *"raises emissions by 107,887 %."* The underlying physics is correct and
worth showing (in a zero-carbon grid the only heating-GHG difference is the
refrigerant), but the percentage is meaningless when the denominator is
essentially zero. **Fix:** `heatpump.html`'s verdict/stat logic now guards
against a near-zero baseline (< 1 kg CO₂e/yr) and, in that case, reports the
**absolute** change with a plain-language note ("the current electric baseboard
already emits almost nothing, so the small refrigerant footprint of a heat pump
makes it marginally higher for GHG — the real win here is energy and cost, not
carbon") instead of an exploding percentage.

### Limitations of this validation

- **No public source publishes a clean per-city gas→ASHP *percentage* table**
  the tool could be diffed against cell-by-cell; NRCan's Figure 7 is a plot, and
  the advocacy reports give single representative figures. The comparison is
  therefore "same territory, deltas explained," not "matches to ±X %."
- The strongest apples-to-apples anchor (NRCan) is on a **2020–21 grid**; the
  tool's headline is the **2025** grid. Every stored historical year's level is
  in `ef_surface_*.json`, so a future pass could reproduce NRCan's exact vintage
  by passing `efLevel` for 2020 and tighten the comparison.
- All figures above are **Tier-1** ASHP. Tier-2/3 and "average installed" curves
  lower the seasonal COP (≈ 1.9–2.2) and shift every reduction a few points
  worse — still inside the benchmark envelope, not separately tabulated here.

## Operating cost (Phase 2 of ROADMAP item 4, 2026-07-12)

heatpump.html's "Annual operating cost" card prices the simulation's energy
flows with `prices_json/{on,qc,ab}.json`, built by `Python/rates_etl.py` from
MaxPr1me/canada-utility-rates (residential tariffs, monthly upstream scrape)
plus StatCan 18-10-0001 for heating oil. Source scouting and every reduction
decision: `Python/rates_source_notes.md`; data-shape and caveats:
`prices_json/meta.json`.

**Tariff application.**

- The engine now emits a **month × hour-of-day electricity matrix**
  (`elec_month_hour`, kWh) for both scenarios, so TOU plans are priced
  exactly per (month, hour). The TMY year has no weekday structure, so
  weekday-only TOU rules are weighted **5/7 weekday : 2/7 weekend** per cell —
  exact in expectation for a temperature-driven load. Holidays are treated as
  regular weekdays (<1% effect). ON offers TOU (default), ULO and Tiered via
  a plan selector; both scenarios always use the same plan.
- **Tiered plans** (ON monthly tiers, QC 40 kWh/day) price the *added*
  heating load marginally over a documented non-heating household baseline —
  cost(baseline + heating) − cost(baseline) — with baselines of 750 kWh/month
  (ON) and 25 kWh/day (QC). QC's daily accumulator uses the month's mean
  heating day, which slightly understates tier-2 exposure on cold days.
- **Fixed charges:** the electricity service charge is identical in both
  scenarios and excluded (stated in the card). The gas fixed charge is
  counted only in scenarios that consume gas; when a gas-heated home switches
  to a heat pump without gas backup, the savings include the dropped fixed
  charge and the card says so (with the subtract-it-yourself number for
  homes keeping gas service).
- **Unit conversions:** gas at the engine's own 10.55 kWh/m³ (HHV); oil at
  10.0 kWh/L, matching the engine's oil-EF derivation.

**Honesty notes** (all surfaced in the card's fine print): carbon components
are excluded (federal consumer fuel charge zero since 2025-04-01); AB values
carry documented screening supplements (transmission ≈ $0.017/kWh, default
gas supply ≈ $2.25/GJ) and a "(screening estimate)" badge; the ON gas tariff
is the Union-South rate zone; the Ontario Electricity Rebate is not modelled
(scales both scenarios equally); everything is pre-tax. The headline is the
**delta**, not the absolute bills, and the card says why.

**Verification (2026-07-12, browser at localhost):** zero console errors; all
15 Phase-5 self-test vectors still pass after the additive engine change;
hand-checked Ottawa gas base ($917 = 2,368 m³ × 24.3¢ + $341 fixed ✓),
baseboard→HP delta consistent with 13,009 kWh saved × 18.0¢ effective TOU ✓,
Calgary all-in flat 20.5¢/kWh = RRO 16.84 + wires 1.92 + transmission
estimate 1.7 ✓; plan selector appears only for ON cities; costs update on
city/fuel/plan changes; QC/AB sane. A missing prices file degrades to the
old "energy and emissions only" message.
