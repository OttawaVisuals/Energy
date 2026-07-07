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

- Joining this weather data with the grid EF hourly series to build the
  temperature × hour-of-day × season EF lookup table that PLAN.md's Phase 1
  called for (deferred from Phase 1, now unblocked since weather data
  exists for all 3 provinces' cities).
- Building actual archetype load profiles against this weather data
  (Phase 4).
