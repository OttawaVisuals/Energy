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

### v2 city additions (2026-07-17, ROADMAP item 9 workstream A)

Extended the tool from 5 to **14 cities**, adding 9 (Vancouver, Winnipeg,
Quebec City, Halifax, Saskatoon, Regina, Hamilton, London, Windsor). All 9 have
a provincial ERS parquet (`C:\ERS\web\ers_web_<PROV>.parquet`) — none were
dropped. Cities in BC/MB/SK/NS have **no hourly grid pipeline**: they use the
ECCC yearly-average basis + a flat marginal estimate from `grid_ef_annual.json`
(see "Third EF basis"); the UI disables the *Hourly average* option for them.
ON cities (Hamilton/London/Windsor) reuse the existing ON EF surface; Quebec
City reuses the QC surface.

**CWEC2020 distribution change:** the old per-province TMY URLs
(`CWEC-FMCCE_by-par_prov.CSV/CWEC_2020_<prov>.zip`) now 404. `fetch_tmy.py` was
rewritten to download the single combined by-province CSV archive (discovered
from the version directory listing, since its filename carries an export
timestamp) and extract each station's inner province zip from it.

TMY station (CWEC), historical-weather station (MSC Datamart), FSA prefixes,
and computed design temperature per new city:

| City | CWEC / weather climate ID | FSA prefixes | Design temp (2.5%-ile Jan, computed) | TMY mean / min °C |
|---|---|---|---|---|
| Vancouver | 1108395 | V5/V6/V7 | −4.7 | 10.6 / −5.8 |
| Winnipeg | 5023227 | R2/R3 | −31.1 | 3.9 / −35.2 |
| Quebec City | 7016293 | G1/G2 | −24.1 | 5.4 / −25.5 |
| Halifax | 8202251 | B3 | −15.1 | 7.4 / −20.5 |
| Saskatoon | 4057152 | S7 | −34.2 | 3.0 / −36.3 |
| Regina | 4016566 | S4 | −32.6 | 3.6 / −37.0 |
| Hamilton | 6153193 | L8/L9 | −17.4 | 8.2 / −22.9 |
| London | 6144473 | N5/N6 | −17.9 | 8.8 / −24.6 |
| Windsor | 6139527 (TMY) / 6139530 (weather) | N8/N9 | −16.2 | 10.8 / −18.8 |

**Windsor climate-ID note:** CWEC's TMY station is 6139527 (WINDSOR A, older
ID); the live MSC Datamart station for the same airport is 6139530 (WINDSOR A,
current auto) — 6139527 has no `today`-endpoint hourly file. Same site,
different climate-ID vintages.

All 56 archetypes (14 cities × 4) calibrated within ±10% (see
`archetype_validation.csv`). Two low-`n` cells flagged (Regina townhouse_row
n=17, Saskatoon townhouse_row n=43 near the 30-home threshold); two minor
Windsor weather gaps (Aug 2023, Feb 2024) flagged not imputed, both irrelevant
to the January design-temp percentile. `build_tmy_temps.py` (new) regenerates
the browser-facing `tmy_temps.json` for all 14 cities from `tmy_hourly.csv`.

**In-browser sanity gates (verified 2026-07-17):** Vancouver seasonal COP 3.5 >
Ottawa 2.4 (milder climate) ✓; prairie design temps (Winnipeg −31, Saskatoon
−34, Regina −33) in Edmonton's −32 ballpark ✓; BC/MB/SK/NS correctly show the
*Hourly average* basis disabled with BC 26.5 / MB 2.3 / SK 750 / NS 800 g/kWh;
no console errors across all 14 cities.

**Cost note:** BC/MB/SK/NS have no `prices_json/` file → cost card degrades to
"energy and emissions only". New ON cities reuse Toronto's rate entry and
Quebec City reuses Montreal's, valid for the cost *delta* because the volumetric
rates that drive it are province-uniform (OEB RPP TOU energy prices province-
wide; Union-South gas zone for SW Ontario; Hydro-Québec Rate D uniform).

### v2 weather lens: multi-decade record + design temps (2026-07-17, workstream C)

Adds a **"weather year" lens** so a user can drive the simulation with the TMY
*or* any real historical year, see the coldest/mildest extremes, and read the
weather-sensitivity of the result. Built by `pipeline/build_weather_years.py` →
one lazy-loaded `data/processed/weather_<city>.json` per city (727–811 KB each,
under the ~1 MB target).

**Sources.** The multi-decade base is **CWEEDS 2020** (Canadian Weather Energy
and Engineering Data Sets), the hourly record per station, **1998–2017** (some
stations 2000/2003 on), same CMC tree as the CWEC TMY — dry-bulb temperature is
column 30 (0.1 °C) and station files match the CWEC climate IDs exactly. Recent
complete years (**2019–2025**) come from the MSC Datamart record already fetched
(`weather_hourly.csv`). **2018** falls between the two sources and is left as a
gap (`years_missing`), not imputed. Kept to the newest 24 years per city to bound
file size; temperatures quantized to integer tenths of a degree.

**Year tagging.** Each complete year (≥ 8000 h) carries its HDD18, min and mean.
The record is tagged **typical-like** (HDD18 closest to the TMY's), **coldest**
(max HDD18) and **mildest** (min HDD18) for the selector.

**Design temperatures.** The 2.5%-ile January temperature is now computed over
the **full ~24-year record** (vs the old 8-year weather file used for the
archetype UA back-out) — which sharply improved the match to **NBC 2020
Appendix C, Table C-2**: Ottawa −24.0 (NBC −24), Toronto −18.0 (−18), Montreal
−22.8 (−23), Winnipeg −31.2 (−31), Quebec City −25.4 (−25), Windsor −15.2 (−16);
Calgary −27.1 vs NBC −30 is the one notable gap (chinook-variable). Each
`weather_<city>.json` meta carries both the computed value and the published NBC
2020 2.5%/1% figures (commonly-published Table C-2 values, cited as such). The
**archetype UA calibration still uses the original per-city design temp**; the
NBC/multi-decade values are shown in the UI as reference overlays, not fed back
into UA (left for a future pass to avoid re-touching the validated archetypes).

**UI.** A "weather year" dropdown (Typical (TMY) / each year, tagged); a
weather-file card whose SVG shows the **min–max monthly-mean band across all
years**, the selected series, and dashed design-temperature markers; and a
**cross-year emissions band** — `simulate()` is re-run for every year (memoized
on the inputs) and the min–max GHG-change is reported (e.g. Ottawa marginal
basis +1 % to +15 %; Vancouver −90 % to −92 %; Halifax +46 % to +57 % on its
800 g/kWh coal marginal — colder years worse, as expected). Verified in-browser
across ON/BC/NS cities; all 15 engine self-test vectors still pass; no console
errors.

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

## Third EF basis: ECCC/NIR published annual averages (v2, 2026-07-17)

Adds a **third grid-EF option** to the tool (ROADMAP item 9 workstream B),
alongside the hourly *average* and *marginal* surfaces: **"ECCC yearly"** — a
single flat published annual-average grid intensity per province. Built by
`pipeline/build_grid_ef_annual.py` → `data/processed/grid_ef_annual.json`.

It serves two purposes:

1. It is the **only** grid EF available for provinces with no hourly pipeline
   (BC/MB/SK/NS/NB/NL/PE) — everything the tool needs to add cities outside
   ON/QC/AB (ROADMAP item 9 workstream A).
2. For ON/QC/AB it is an **official-inventory-average** alternative whose
   difference from the tool's own hourly-surface average is itself informative
   (the surface is calibrated to the latest complete year and attributes all
   ON emissions to gas; the inventory average is a different, published scope).

### Source and formula

Both inputs are pulled machine-readably from the **StatCan Web Data Service**
full-table CSV endpoint (`canada.ca` and `open.canada.ca`'s CKAN API are both
WAF-blocked to `curl`/WebFetch in this environment — "Request Rejected"; StatCan
WDS is not, and returns clean zips):

- **GHG numerator** — StatCan **38-10-0097** *Physical flow account for GHG
  emissions*, sector *Electric power generation, transmission and distribution
  [BS22110]* (this is ECCC National Inventory Report data carried in StatCan's
  environmental-economic accounts), kt CO₂e, by province, 2009–2023.
- **Generation denominator** — StatCan **25-10-0015** *Electric power
  generation, monthly generation by type*, class *Electricity producers,
  electric utilities*, *Total all types*, summed to annual, by province, MWh.

```
intensity_g_per_kWh = kt_CO2e × 1e6 / utility_generation_MWh
```

**Why the utility-only denominator (not total generation):** the numerator
(BS22110) is the *utility industry's* emissions. Large industrial
cogeneration — e.g. Alberta oil-sands self-generation — is booked under its
host industry (oil & gas), **not** BS22110. Dividing utility-industry emissions
by *total* generation (which includes that industrial self-gen) deflates the
intensity — Alberta came out at 323 g/kWh (2022) that way. Restricting the
denominator to **utility** generation keeps numerator and denominator on the
same scope and makes the **national** result validate almost exactly against
ECCC's published headline.

### Validation and documented deviations

| Geography | Year | Computed | Published anchor | Δ | Note |
|---|---|---|---|---|---|
| Canada | 2022 | 101.3 | 100 (ECCC headline) | +1 % | near-exact — the scope check |
| Ontario | 2022 | 48.0 | 51 (TAF AEF) | −6 % | see below |
| Ontario | 2023 | 56.4 | 67 (TAF AEF) | −16 % | see below |
| Alberta | 2019 | 566 | 630 (Alberta.ca Fig 7) | −10 % | see below |
| Alberta | 2022 | 408 | 510 (Alberta.ca Fig 7) | −20 % | see below |

The national number lands on ECCC's published headline (101 vs 100), confirming
the scope is right. The provincial deviations are **documented scope
differences, not errors** (and the whole point of offering this as a *distinct*
basis from the hourly surface):

- **Ontario ~10–20 % below TAF's Annual AEF.** TAF attributes *all* grid
  emissions to gas and uses a year-specific NIR gas intensity; this basis uses
  the inventory's *actual electric-utility emissions* over utility generation.
  Both are defensible; they are different constructions.
- **Alberta ~20 % below Alberta.ca Figure 7.** Alberta's published grid
  intensity allocates industrial-cogeneration emissions to electricity; BS22110
  does not. Flagged, not "fixed" — a user who wants the cogen-inclusive number
  should read it off Alberta's figure, which the tool cites.

### Marginal estimates for annual-only provinces

Provinces without an hourly surface get a **single flat marginal estimate**
(g/kWh) with a per-province rationale, used when the user picks the *marginal*
basis for them (`MARGINAL_ESTIMATES` in the script):

| Province | Marginal | Rationale |
|---|---|---|
| SK | 750 | coal/gas fleet frequently marginal for new winter load |
| NS | 800 | coal/petcoke-heavy; thermal on the margin |
| NB | 550 | gas/oil thermal meets incremental winter load |
| BC, MB, NL, PE | = annual avg | hydro-dominant: domestic margin is flexible hydro (near-zero); winter **import** margin is higher but contested/unmodeled — set equal to the average with this caveat, matching the QC treatment in the hourly pipeline |

These are **screening estimates**, labelled as such in the UI. ON/QC/AB are not
in this table — they carry a real hourly marginal channel.

### Engine / UI wiring

The engine is unchanged. The "ECCC yearly" and annual-only-province paths feed
`simulate()` a **degenerate flat "surface"** (`flatSurface()` in
`heatpump.html`): `global = [1, 1]` so `lookupShape` falls straight through to
the global cell (ratio 1), and `reference_level_g_per_kWh = [level, level]` —
so `gridEF` returns the flat published level every hour. The EF-basis control is
now three-way (*Marginal / Hourly average / ECCC yearly*); for provinces without
an hourly surface the *Hourly average* button is disabled with an explanatory
hint, and the basis auto-falls-back to *ECCC yearly*. Re-run:
`python build_grid_ef_annual.py` (`--force` to re-download).

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

> **Superseded 2026-07-27.** The proxy above is being replaced by the home's
> *actual* station design temperature — see
> "[City design temperatures from HOT2000 weather stations](#city-design-temperatures-from-hot2000-weather-stations-2026-07-27)"
> below. `build_archetypes.py` has **not** been rewired yet; it still uses the
> computed 2.5%-ile proxy. The new table is built and committed, the swap is
> the next step of the load-model rebuild.

### City design temperatures from HOT2000 weather stations (2026-07-27)

Built by `pipeline/build_city_design_temps.py`.
Outputs `data/processed/city_design_temps.json` + `data/interim/city_design_temps.csv`.

**The problem this fixes.** `EGHDESHTLOSS` is computed by HOT2000 at the design
temperature of *the home's own weather station*, drawn from HOT2000's weather
library. Dividing it by a proxy derived from a different record, over a
different period, mixes two climate bases in one equation. The raw ERS year
files carry `WEATHERLOC` (station) and `WTHDATA` (library version), so the real
basis is recoverable — those columns were simply never carried into
`ers_web_*.parquet`.

**Method.**

1. Universe = every `HOUSEID` in the web parquets (the paired, gated homes that
   reach the retrofit page): **1,430,221**.
2. One pass over `C:\ERS\*.csv`, first-hit-wins per `HOUSEID` (a home
   re-evaluated later keeps its earliest station). **100.0% matched, 0
   unmatched**; every year file 2004–2026 carried both columns. Cached to
   `data/interim/houseid_city.parquet` so the 7.7 GB scan runs once.
3. `CLIENTCITY` (operator-entered free text: 35,450 distinct raw values,
   23,984 after folding) is normalised for mojibake, accents and punctuation —
   merging `MONTRÉAL`/`MONTREAL`, `QUÉBEC`/`QUEBEC`, `ST. CATHARINES`/`ST
   CATHARINES` — then rolled into metro areas by the explicit `CITY_MEMBERS`
   table in the script.
4. Each station is joined to NBC Appendix C design heating dry-bulb via
   `reference/nbc_station_design_temps.csv` (419 stations, 334 distinct NBC
   locations). **Zero homes lack a design temperature.**
5. **City design temperature = the house-weighted mean** of each home's own
   station value — *not* the modal station's. Homes inside one city spread
   across many stations (Toronto: 55 stations, the top one only 42%), so the
   mode is not representative.

**Result: 84 cities, 1,020,246 homes (71.3% of the universe).** Top 10:

| City | homes | % | design °C (wtd) | modal station (share) | n stations |
|---|---|---|---|---|---|
| Toronto | 293,950 | 20.6 | −18.4 | TORONTO MET RES STN (42%) | 55 |
| Montreal | 73,322 | 5.1 | −23.6 | MCTAVISH (22%) | 43 |
| Ottawa-Gatineau | 57,971 | 4.1 | −24.1 | OTTAWA (63%) | 34 |
| Vancouver | 50,636 | 3.5 | −4.9 | VANCOUVER (69%) | 52 |
| London | 35,309 | 2.5 | −18.4 | LONDON (98%) | 26 |
| Calgary | 35,130 | 2.5 | −26.1 | CALGARY INTL (42%) | 25 |
| Kitchener-Waterloo | 31,170 | 2.2 | −18.3 | TORONTO MET RES STN (46%) | 40 |
| Hamilton | 31,150 | 2.2 | −17.9 | SIMCOE (54%) | 30 |
| Quebec City | 30,538 | 2.1 | −25.5 | QUEBEC (45%) | 33 |
| Edmonton | 29,986 | 2.1 | −30.7 | EDMONTON INTL (51%) | 30 |

Full 84-city table in `data/interim/city_design_temps.csv`.

**What the data can't tell us / what we assumed / what would change the answer:**

- **Station-name matching is not exact for everyone.** Only ~53% of homes match
  NBC by `exact` station name. The two largest stations — 265,001 homes, ~19% —
  are `alias:nearest (Downsview absent)` and `alias:downtown approx`, and they
  disagree by 3.5 °C. `matched_via` is carried into the output so the match
  quality travels with the number.
- **The weather library is mostly not `Wth2020`.** Across the universe:
  `WTH100` 56.3%, `Wth2020` 35.4%, `Wth110` 8.0%. We hold one NBC-vintage value
  per station and apply it to all vintages. Library revisions typically move a
  station 1–2 °C → roughly 2–3% on peak load (see the sensitivity table below).
- **The percentile is inferred, not stated.** The source file has no metadata;
  value-matching against published NBC figures (Toronto Intl −18.3, Ottawa Intl
  −24.3, Winnipeg −31.3) indicates **2.5% January dry-bulb**. Confirm with the
  file's author before citing, and pin the NBC edition (2015 vs 2020 shifts some
  stations ~1 °C).
- **28.7% of homes are unassigned** — genuine mid-size municipalities outside
  the 84 listed (Saint-Bruno-de-Montarville, Summerside, Cobourg, Rivière-du-Loup…),
  not mapping failures. They are counted and reported, never silently dropped.
- **`CITY_MEMBERS` is a judgement call**, written out in full in the script.
  Notably Oshawa is folded into Toronto.
- **`design_temp_spread_C` is large in some cities** (Toronto 23.4, Victoria
  32.6) because a handful of homes carry distant stations — presumably data
  entry or relocated files. It barely moves the weighted mean, but it is
  reported rather than trimmed.
- **Two cities to override by hand**: **Barrie** (weighted −22.0 vs modal −26.6
  — modal station is MUSKOKA, well north) and **Trois-Rivières** (draws QUEBEC
  as top station, making it climatically identical to Quebec City).

**Design-temperature sensitivity.** How much does getting `T_design` wrong
actually matter? Holding Toronto pre-1980 detached fixed (design heat loss
16.27 kW, annual delivered heat 23,343 kWh) and re-fitting `Tbalance` each time:

| T_design | UA (W/K) | fitted Tbalance | peak @ TMY min | peak @ 1%-ile |
|---|---|---|---|---|
| −14.0 | 464.9 | 11.37 | 16.54 kW | 12.07 kW |
| −17.1 *(current proxy)* | 427.0 | 12.27 | 15.57 kW | 11.47 kW |
| −20.0 | 396.8 | 13.07 | 14.79 kW | 10.98 kW |
| −22.0 | 378.4 | 13.61 | 14.31 kW | 10.67 kW |

An **8 °C** swing moves the peak only ~14%, because the balance-point fit
compensates: a colder `T_design` lowers UA, and the fit raises `Tbalance` to
keep annual energy on target. **The annual-energy anchor does the real work;
`T_design` is a weak lever.** The reason to use the real station value is
defensibility, not accuracy — "we used the station HOT2000 used" is a
one-sentence defence.

The genuinely dominant choice is the **peak basis**: 15.57 kW at the single
coldest TMY hour vs 11.47 kW at the 1st percentile, a 26% swing. See the
open issues below.

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

> **Open issue, found 2026-07-27 — `Tbalance` is a residual, not a physical
> balance point, and using it to size equipment double-counts sunshine.**
>
> `Tbalance` is the model's *single free parameter*, so it absorbs everything
> the model does not represent: solar gains, internal gains, setback behaviour,
> heat delivered by supplementary systems that `EGHFURNACEAEC` excludes, and any
> error in `T_design`. It cannot honestly be described as "the temperature at
> which the house stops needing heat."
>
> Backing the implied gains out of the fits — `gains_kW = UA × (21 − Tbalance)` —
> gives **2.5–4.1 kW across every city and archetype**, remarkably flat despite
> floor areas of 149–341 m² and UA of 209–463 W/K:
>
> | | Toronto | Ottawa | Montreal | Edmonton | Vancouver |
> |---|---|---|---|---|---|
> | pre-1980 | 3.73 | 3.94 | 3.84 | 2.87 | 3.53 |
> | 1980–2005 | 3.80 | 4.03 | 3.38 | 3.21 | 3.47 |
> | post-2005 | 4.12 | 3.84 | 3.02 | 2.53 | 3.00 |
> | townhouse | 3.41 | 3.40 | 3.72 | 2.54 | 2.69 |
>
> Two conclusions:
>
> 1. **Gains behave as a roughly constant absolute power, not a fraction of
>    design load.** Any "peak = X% of design heat loss" rule is therefore the
>    wrong shape — the same physical credit is 23% of a Toronto pre-1980 home's
>    design load and 44% of a Vancouver townhouse's.
> 2. **3.5 kW is 2–3× plausible internal gains** (typically 5–8 W/m², so
>    1.0–1.6 kW for a 200 m² home; the table implies 12–23 W/m²). The excess is
>    mostly **solar**, because `Tbalance` is fitted against *annual* energy and
>    therefore encodes *season-average* gains. But the sizing peak is a January
>    pre-dawn hour, when **solar is zero**. Using the annual-fitted `Tbalance`
>    to compute the peak credits the house with sunshine it is not receiving and
>    **undersizes the heat pump**. Missing supplementary heat biases the same
>    way.
>
> **The fix is two gains numbers, not one**: season-average (internal + solar)
> for the annual-energy calibration, and peak-hour internal-only for sizing.
> Collapsing them into a single `Tbalance` is the actual defect, and it is
> independent of the design-temperature question above.
>
> Cross-check available: NRCan CanmetENERGY, *Cold-Climate Air Source Heat
> Pumps* (Cat. M154-149/2022E-PDF, `data/raw/nrcan/gid_329701.pdf`) Table 1
> gives peak heating loads for four EnerGuide-drawn archetypes in 16 cities —
> Toronto 11.6 / 9.8 / 6.1 / ~2.2 kW. Our Toronto archetypes currently compute
> 15.6–12.1 kW simulated peak against 13.0–16.3 kW gross design heat loss. The
> report also gives a temperature-vs-load scatter with fitted lines (Figure 1)
> whose slope is UA_net and x-intercept the effective balance temperature —
> a direct published check on both quantities. **Note the report contradicts
> itself on Toronto**: §3.1 text says Archetype A is 10.7 kW and B is 9 kW;
> Table 1 says 11.6 and 9.8. Cite Table 1 and note the discrepancy.
>
> Two further reasons our figures sit above NRCan's, both definitional rather
> than errors: `EGHDESHTLOSS` is a **gross** design heat loss with no gains
> credit, while NRCan Table 1 is a **net** peak from an hourly simulation that
> credits solar and internal gains (report §3.2); and ours is the **median of
> tens of thousands of audited local homes** (Toronto pre-1980: 57,256 homes,
> median 199 m², 85.6 W/m²) whereas NRCan's is **one hand-picked house
> relocated** to 16 cities. The latter shows up as a structural tell: NRCan's
> loads scale with climate (Toronto 11.6 → Edmonton 16.8 kW) while ours are
> nearly flat and Edmonton is *lower* than Toronto, because Edmonton's audited
> stock is genuinely better built per m². Our archetypes bundle house *and*
> local construction practice, so cross-city comparisons are not comparing the
> same building.

### NRCan-published archetypes (2026-07-27) — the replacement

Built by `pipeline/build_archetypes_nrcan.py`.
Outputs `data/processed/archetypes_nrcan.json` + `data/interim/archetypes_nrcan_validation.csv`.

**Why replace the ERS archetypes.** The fitted `Tbalance` above is a residual, not
a balance point (see the open issue). Rather than repair a parameter we cannot
defend, both quantities now come from one published source.

**Source.** NRCan CanmetENERGY, *Cold-Climate Air Source Heat Pumps: Assessing
Cost-Effectiveness, Energy Savings and Greenhouse Gas Emission Reductions in
Canadian Homes*, Cat. No. M154-149/2022E-PDF, ISBN 978-0-660-42353-1
(`data/raw/nrcan/gid_329701.pdf`) — **Table 1** (peak heating loads, 4 archetypes
× 16 locations) and **Figure 1** (load vs outdoor temperature, whose x-intercept
is the zero-heating temperature).

**Method.** Each NRCan archetype is *one house* drawn from the EnerGuide database
and relocated to 16 cities (report §3.1), so its UA is constant and each city's
peak differs only through that city's design temperature:

```
peak_city = UA × (T_balance − T_design_city)
```

Regressing Table 1's 16 published peaks against the 16 NBC Appendix C design
temperatures therefore recovers UA (slope) and `T_balance` (x-intercept) per
archetype, using every published number rather than one chart reading:

| Archetype | UA (W/K) | T_balance | R² | Figure 1 read-off | diff |
|---|---|---|---|---|---|
| A: pre-1980, 2-storey | 339.1 | **16.53 °C** | 0.921 | 16 | +0.53 |
| B: post-1980, 2-storey (larger) | 290.9 | **15.89 °C** | 0.905 | 15 | +0.89 |
| C: post-1980, 1-storey (smaller) | 187.0 | **15.47 °C** | 0.921 | 14 | +1.47 |
| D: Net-Zero-Energy-Ready | 92.4 | **10.26 °C** | 0.926 | 12 | −1.74 |

This also **settles what Table 1's peaks are referenced to.** Had they been peaks
of an hourly TMY series rather than design-condition loads, the recovered
`T_balance` would not land on Figure 1's intercept. It does — within 0.5 °C for A
and B — so Table 1 is a design-condition load. That mattered: the alternative
reading changes UA by ~16%.

**UA is taken per city, not from the single fit.** Because we ship only NRCan's
16 published cities there is no extrapolation, so `UA_city = peak_published /
(T_balance − T_design_city)` — which reproduces the published peak *exactly*.
The single fitted UA is retained in the output as a diagnostic.

The per-city spread this exposes is **real physics, not noise**. Implied UA for
archetype A:

| | UA (W/K) | | UA (W/K) |
|---|---|---|---|
| St. John's | 389 | Toronto | 333 |
| Halifax | 382 | Prince George | 309 |
| Fredericton | 362 | Vancouver | 306 |
| Edmonton / London | 355 | Kamloops | 291 |

The same house needs 34% more heat at design conditions in St. John's than in
Kamloops. That is **wind-driven infiltration** — windy Atlantic coast vs
sheltered interior valley — which HOT2000 models and a single UA cannot. Forcing
one UA costs up to 1.65 kW (14% on St. John's archetype B) and discards the
effect; taking UA per city keeps it.

**Sanity check.** Toronto archetype A gives 26,157 kWh/yr delivered heat against
the ERS Toronto pre-1980 detached median of 23,343 kWh — 12% apart, the right
order for one specific house vs a population median.

**What the data can't tell us / what we assumed / what would change the answer:**

- **Four houses, not a population.** Sample size stops being a claim we can make.
- **No floor areas are published.** No per-m² figures, and no area-based "which is
  my home?" helper.
- **A relocated house cannot show local construction practice.** The ERS medians
  did — Edmonton's audited stock is genuinely better built per m² than Toronto's.
  That signal is gone; the model now says "the same house in a different climate."
- **The archetype set changes**: townhouse/row disappears, Net-Zero-Ready appears.
- **TMY covers 11 of the 16 cities.** Annual energy is reported for those 11;
  Kamloops, Prince George, Victoria, Fredericton and St. John's have peak load
  and UA but no annual figure until CWEC files are added.
- **The report contradicts itself on Toronto.** §3.1 text gives archetype A =
  10.7 kW and B = 9 kW; Table 1 gives 11.6 and 9.8. **Table 1 is used**; cite it,
  and note the discrepancy rather than let a reader find it.
- **Table 1's archetype-D column extracts misaligned from the PDF.** The pairing
  used was verified by `corr(A, D) = 0.9945` and by physical ordering (Victoria
  1.0 and Vancouver 1.1 lowest, Regina 4.0 highest). Toronto D = 2.6 kW from
  Table 1, against 2.4 kW in the §3.1 text — the same text-vs-table pattern.
- **Design temperatures are NBC Appendix C**, which is *probably* what HOT2000's
  weather library uses but is not confirmed; the residual structure above is
  partly wind and partly any mismatch here.
- **Solar gains are inside `T_balance`.** As with the ERS archetypes, the balance
  temperature is a season-average construct, so using it for a January pre-dawn
  sizing peak still over-credits solar. The difference is that `T_balance` is now
  *published* rather than fitted to our own data.

### Open question for the HOT2000 / EnerGuide team

Returning to ERS-derived archetypes — which would restore the population sample,
floor areas, local construction practice and the townhouse archetype — needs one
thing we do not have. **The public ERS extract carries annual figures and design
heat loss only; it has no monthly outputs.** CanmetENERGY's own HTAP tool
(`github.com/canmet-energy/htap`, LGPL-3.0, `inc/hourly.rb`) builds hourly load
shapes — the "load fitting technique" referenced in the report — from four
monthly HOT2000 fields:

| Field | Purpose |
|---|---|
| `energy_loadGJ` | monthly conduction loss |
| `solar_gainsGJ` | monthly solar gain |
| `internal_gainsGJ` | monthly internal gain |
| `aux_energy_GJ` | monthly auxiliary heat, used to rebalance the hourly series |

**The ask:** either those four monthly fields added to the ERS extract, or the
standard-operating-conditions **solar gain per city** (the only house- and
climate-specific term we cannot derive). Everything else is already in hand:
UA from `EGHDESHTLOSS` ÷ station design temperature, the ERS SOC setpoint
schedule, and the SOC internal-gains constant — all verified against a real
CanmetENERGY `.h2k` file (see below).

### HOT2000 standard operating conditions, verified from an `.h2k` file

`reference/htap_NRCan-arch4-ERS.h2k` — an ERS standard-operating-conditions run
from CanmetENERGY's HTAP repository (LGPL-3.0). The ERS documentation does not
publish these values: HOT2000 User Guide v15.8 §7.12 only says *"Do not change
any values/selections in the Base Loads, Water Usage or Electrical Use screens"*,
and none of the guide's 22 Technical Procedures cross-references covers them.
They are program defaults, readable from any `.h2k`:

- **Setpoints**: main floors 21 °C daytime, **18 °C at night for 8 h** (setback
  ends 07:00 per HTAP's `temp_schedule`), basement 19 °C,
  `basementFractionOfInternalGains = 0.15`.
- **Occupancy**: 2 adults + 1 child, each `atHome = 50%`.
- **Interior electrical base load**: appliances 6.2997 + lighting 2.6 + other 9.7
  = **18.6 kWh/day = 0.775 kW** (exterior 0.9 kWh/day excluded — it does not heat
  the house). Hot water 189.8 L/day at 55 °C.
- **Utilized gains** (`<Gains>`): internal **0.88 kW, near-constant** across every
  heating month (0.878–0.902); solar 0.76–1.65 kW, January 1.05 kW.
  `SolarUtilization` = 0.996 in January, so in deep winter utilized ≈ available.
- **HTAP's hourly internal-gain profile** (`inc/hourly.rb`, `norm_int_gains`)
  puts hours 02:00–06:00 at **0.56–0.59×** the monthly mean — so pre-dawn
  internal gains are ≈ 0.49 kW, at an 18 °C setpoint, with zero solar.
- **`designHeatLossRate`** sits in `<Other>`, entirely outside the monthly gains
  balance — confirming `EGHDESHTLOSS` is in **watts** and is **gross, with no
  gains credit**, as assumed throughout.

Internal gains and setpoints are SOC constants and therefore generalise to every
ERS-rated house. **Solar does not** — it is specific to that house's windows and
climate, which is why it is the outstanding ask above.

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

**Below the published minimum operating temperature** (`hp.belowLockout`, v2,
workstream E). Orthogonal to the control strategy, this governs what the ASHP
does at outdoor temperatures below the curve's `min_op_temp_C`:

- `hard` (default, and the pre-v2 behaviour): the compressor **stops** — zero
  capacity, load falls to backup/unmet. This is the manufacturers' *published*
  minimum (e.g. Mitsubishi H2i's guaranteed-operation floor, −25 °C for Tier 1),
  which is a warranty/ratings boundary, **not** a hard physical stop.
- `derate`: the pump **keeps running** below the published minimum. Capacity is
  extrapolated on the slope of the coldest *defined* curve segment
  (`coldEdge()` finds the two coldest grid points where both capacity and COP are
  non-null) and **COP is held flat at the floor** (the coldest defined COP). If
  the linear capacity extrapolation reaches zero it reverts to a hard stop.
  Real below-LCT behaviour is **manufacturer-unspecified** — no datasheet
  publishes it — so this mode is clearly labelled as an assumption in the UI and
  its hours are counted separately (`diagnostics.derated_hours`). It never fires
  in default mode, so all pre-v2 results are unchanged.

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
  `charge_kg × (leakRate_frac + eolLossFrac/lifetimeYears) × GWP`. Both
  `charge_kg` and `GWP` are now per-refrigerant (corrected 2026-08-12 — see
  **§Refrigerant GWP and charge mass** below); `charge_kg` = rated capacity
  (kW) × a per-refrigerant kg/kW constant, `GWP` = AR6 blend-weighted GWP100.
- **Upstream methane**: `methaneLeakPct%` of gas throughput (mass, via
  10.55 kWh/m³ and 0.68 kg/m³, ~100 % CH₄) × `methaneGWP`. The engine still
  accepts both as independent parameters, but the live page currently exposes
  only a single "Upstream & grid losses: Yes/No" switch (not a slider) that
  applies fixed defaults when Yes: `methaneLeakPct` = **2.14** (a calibrated
  methane-equivalent rate, not a literal leak reading — see **§Lifecycle
  sourcing**) and `methaneGWP` = **85** (20-yr, per TAF's Fugitive Methane
  guideline). Sources and the arithmetic are in **§Lifecycle sourcing** below.
- **Upstream oil**: optional adder `oilUpstreamFrac` × oil combustion.
- **Line losses**: default 5 % on delivered electricity (sourced in
  **§Lifecycle sourcing**).

Calendar (for season/hour-of-day, which key the EF surface) is derived from the
hour index assuming the series starts Jan 1 (matching TMY); an 8784-length
series is treated as a leap year. Hour-of-day is `1..24` to match the surface's
convention.

### Validation

`app/engine.test.js` (Node) and `pipeline/validate_engine.py` (a faithful Python
port) run the **same six hand-computed cases** and assert **identical results to
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
6. **Below-lock-out derate mode** (v2) — synthetic curve `T_C [−10, 0, 15]`,
   `cap_frac [0.5, 0.7, 1.0]`, `COP [2.0, 3.0, 4.0]`, published minimum −10 °C,
   hour at −20 °C (10 °C below it). Coldest capacity segment slope
   `(0.7−0.5)/(0−(−10)) = 0.02 /°C`, COP floor 2.0. Derated capacity
   `0.5 + 0.02·(−20−(−10)) = 0.3` → `10 kW × 0.3 = 3.0 kW`; HP delivers 3.0 kWh,
   HP electricity `3.0/2.0 = 1.5 kWh`; `lockout_hours 0, derated_hours 1`. A
   guard vector confirms the **default `hard` mode on the same curve/hour locks
   out** (HP delivers 0). These are the **two new derated vectors** added in v2;
   the browser self-test (`heatpump.html`) reproduces all 15 vectors including
   these two.

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
- The optional below-lock-out **derate** mode (workstream E) extrapolates
  capacity and holds COP at the floor — genuinely manufacturer-unspecified
  territory. It is off by default and clearly labelled where it is on.
- The **sizing sweep** (workstream D) re-runs the year across 40–160 % of design
  heat loss but has **no short-cycling model**, so the oversizing penalty is
  understated (see §Sizing sensitivity).

---

## Sizing sensitivity (v2, ROADMAP item 9 workstream D)

`heatpump.html` runs `simulate()` **25 times per input change** — the nominal
capacity swept from **40 % to 160 % of the archetype's design heat loss in 5 %
steps** (the design load is the `100 %` anchor) — and charts, versus size:
**seasonal COP, backup share, hours needing backup / unmet, annual GHG, and
annual operating cost**. A vertical marker shows the current slider position and
a green dot the best (lowest, or highest for COP) point across the sweep. Each
sweep point clones the live `buildOpts()` and overrides only `nominalCap_kW`
(and `charge_kg`, which scales with nominal for the refrigerant term), so the
sweep uses exactly the same weather, grid basis, control strategy and lifecycle
settings as the headline run. The operating-cost curve reuses the operating-cost
card's own pricing (`projectCostOf()`), and is hidden for cities without a rates
file.

**Documented limitation — oversizing looks free here and is not.** The engine
models only the **max-compressor** curve (Phase 3b); it has **no cycling / part-load
model**. An oversized inverter in a mild hour would in reality short-cycle and run
at a degraded part-load COP, but the sweep costs every hour at the steady
max-speed COP. So on the chart, sizing up past the design load has almost no
penalty (a hair more refrigerant charge), whereas in a real home it wastes money
and wears the compressor. **Undersizing** (left of the marker) *is* modelled
correctly: the capacity shortfall on cold hours is pushed onto the backup (or
left unmet with `backup: none`), which the curves capture. The card states this
caveat inline.

---

## Lifecycle sourcing — methane, GWP20, line losses (v3, corrected 2026-08-11)

> **Superseded (2026-08-11):** the v2 methane defaults below (1 % leak, GWP 28)
> were reconstructed from a remembered "×1.9 report" claim without the source
> document in hand. User supplied the actual source — The Atmospheric Fund's
> [*Fugitive Methane*](https://taf.ca/publications/fugitive-methane/) guideline
> (May 2022) — which gives real, citable numbers for exactly this tool's use
> case. First pass at applying it (same day) used TAF's headline "2.7 % full
> life-cycle leak" figure directly through the engine's leak%×GWP formula —
> **wrong**, because that 2.7 % is TAF's full-chain leak rate for their
> *infrastructure-change* scenario, and running it through our formula
> overshoots to ≈+82%, past even TAF's own +92% upper scenario. Corrected
> below: the engine's single leak-rate lever is **calibrated** to reproduce
> TAF's actual **+65%** headline (`CH4_GWP_DEFAULT` = 85, `methaneLeakPct`
> default = 2.14, not 2.7) — see "The arithmetic" below for why a literal
> reading of TAF's 2.7% doesn't work here.
>
> **Still open:** a review of BDA's *Heat Pump Lifecycle Emissions Explorer*
> found our refrigerant GWPs are AR4/AR5-era and inconsistent with the engine
> test vector, and that we have no AC counterfactual, no per-refrigerant charge
> mass, and no forward grid trajectory. Nothing changed there yet — see
> [BDA_COMPARISON.md](BDA_COMPARISON.md) and the ROADMAP entry.

### The source: TAF's *Fugitive Methane* guideline (May 2022)

TAF (The Atmospheric Fund, a Toronto-Hamilton regional climate agency)
publishes life-cycle natural-gas emissions factors for Ontario, built by
reconciling Canada's National Inventory Report (NIR, ~1.3 % leak) against
top-down atmospheric-measurement studies. Their headline: **a 2.7 % full
life-cycle leak rate — roughly double the NIR figure** — split across four
life-cycle stages (extraction 1.8 %, upstream transmission 0.3 %, local
transmission/distribution 0.2 %, post-metering 0.4 %). Their published
emissions factors combine that leak rate with a separate, non-disaggregable
**"process emissions"** term (extraction-related CO₂ from flaring, venting,
compressor combustion — footnote 4 of the guideline: *"process emissions
cannot be disaggregated between extraction, transmission, and distribution
with current data sources"*) into one headline ratio per scenario:

| TAF scenario | GWP | EF (kg CO₂e/m³) | vs. combustion-only (1.90) | of which: process / fugitive methane |
|---|---|---:|---:|---|
| Project, **no** pipeline infrastructure change (a single home switching fuels) | 20-yr | 3.13 | **+65 %** | +55 pts process, **+10 pts methane** |
| Project **that changes** pipeline infrastructure (neighbourhood-scale conversion) | 20-yr | 3.65 | **+92 %** | +82 pts process, +10 pts methane |
| Emissions inventory (Scope 1+3) | 100-yr | 2.45 | +29 % | — |

TAF's own guidance (p.7) specifies which GWP horizon applies to which use:
*"Modelling activities that impact natural gas consumption: use GWP20"* vs.
*"Reporting greenhouse gas emission inventories: use GWP100."* This tool
models a single home's fuel-switch decision, not an inventory — so the
correct row is the **first one**: no pipeline infrastructure change, GWP20,
+65 % over combustion-only. The **+92 % row is the right citation for a
future neighbourhood/city-scale conversion tool** (relevant to the Ottawa
`HEATDEMAND_PLAN` work), not this single-home tool.

**Why this engine can't just plug in TAF's numbers directly.** TAF's +65%
is *mostly* non-methane "process emissions" (+55 of the 65 points) that our
engine has no separate model for — it has exactly one upstream lever,
`methaneLeakPct × methaneGWP`. Feeding that lever TAF's headline 2.7% full
lifecycle leak rate (as the first pass at this fix did) implicitly claims
*all* of TAF's +65% is methane, which isn't what TAF says, and produces a
ratio well past what TAF actually published. The defensible fix, given a
single lever: calibrate `methaneLeakPct` so the engine's own formula
reproduces TAF's **published +65% ratio** in aggregate, and document plainly
that the resulting percentage is a bundled stand-in for both effects, not a
literal methane leak-rate reading.

### Methane global-warming potential — the 100-yr / 20-yr toggle

Methane is a short-lived but potent greenhouse gas, so its CO₂-equivalent
depends strongly on the time horizon chosen:

- **20-yr, GWP 85** (default, per TAF's Figure 2 — the tool's `CH4_GWP_DEFAULT`).
  Matches IPCC AR6 fossil-methane GWP-20 (82.5) within rounding; we use TAF's
  own stated figure since it's the number their EFs above are built on.
- **100-yr, GWP ≈ 28–30.** IPCC AR5 Ch. 8 gives 28 (AR6 fossil gives 29.8);
  TAF's own inventory-scope figure (+29 %, table above) implicitly uses a
  100-yr horizon. This is the inventory-standard horizon, not the one this
  tool defaults to, since the tool models a consumption decision, not an
  inventory.

The 20-yr horizon weights methane's near-term warming roughly 3× the 100-yr
value — the honest lens for a decision about *near-term* climate forcing,
per TAF's own reasoning.

### The arithmetic — calibrating the single leak-rate lever to TAF's +65%

Natural gas combustion is **181 g CO₂e/kWh** (HHV). One kWh of gas (HHV) is
`1 / 10.55 = 0.094787 m³`; at 0.68 kg/m³ (≈ 100 % CH₄ for the leak) that is
**0.064455 kg** of gas per kWh delivered to the meter. Solving for the leak
rate that makes `combustion × (1 + leak% × 0.064455 × GWP85 / combustion)`
equal TAF's own **3.13 / 1.90 = 1.6474** ratio gives **leak% = 2.14%**:

```
0.02140 × 0.064455    = 0.0013793 kg CH4-equivalent per kWh
0.0013793 kg × 85      = 0.11724 kg CO2e    = 117.2 g CO2e per kWh gas
combustion + upstream  = 181 + 117.2        = 298.2 g CO2e per kWh gas
ratio to combustion only = 298.2 / 181      = 1.647  = +64.7 %  ≈ TAF's +65 %
```

**2.14%, not TAF's headline 2.7%, is the calibrated value** — using the
literal 2.7% full-lifecycle rate in this same formula gives `+82%` (shown
by mistake in the first pass at this fix, now corrected), because 2.7% is
TAF's *leak-only* rate for a different scenario (infrastructure change,
full chain), not a number meant to be multiplied straight through a
methane-only formula to reproduce the no-infrastructure-change +65%. 2.14%
is a bundled proxy standing in for TAF's process-emissions term as well as
its fugitive-methane term — call it a "methane-equivalent" rate, not a
literal leak-rate reading.

### Grid line losses — 5 % default, and why not Portfolio Manager's 1.83

The line-loss slider (default **5 %**) grosses up delivered electricity to
generated electricity, because the grid EF is expressed per **kWh generated**.

- **World Bank / IEA** electricity transmission-and-distribution losses for
  Canada (indicator `EG.ELC.LOSS.ZS`, World Development Indicators, sourced
  from the IEA Energy Statistics Data Browser) — live-queried 2026-08-11
  against the World Bank API (`api.worldbank.org/v2/country/CA/indicator/
  EG.ELC.LOSS.ZS`): **5.14% (2019), 5.04% (2020), 4.02% (2021), 4.01% (2022),
  4.00% (2023), 4.15% (2024)**. Our 5% default sits at the recent high end —
  mildly conservative.
- **Utility figures** vary by system: transmission-only losses (e.g. AESO's
  Alberta transmission grid) are ~4 % while a full transmission+distribution
  path to a home (e.g. BC Hydro) can reach ~10 %. 5 % is a reasonable
  province-agnostic midpoint for a residential connection.

**Why ENERGY STAR Portfolio Manager's source–site ratio (1.83 for Canadian grid
electricity — corrected 2026-08-11; a prior version of this doc misstated it
as 2.05) is *not* used here.** Portfolio Manager's 1.83 (Portfolio Manager
Technical Reference, *Source Energy*, Aug 2023, Figure 1/Figure 12 — user
supplied and directly verified against the source PDF) converts **site**
electricity to **primary source energy** — it bundles the
**thermal-generation conversion losses at the power plant** (the ~1.8×
penalty of burning fuel to make electricity, given Canada's largely
hydro/nuclear grid) *together with* the few-percent T&D losses. Figure 12 of
that same document computes the ratio as (fuel consumed for generation +
renewables) ÷ (electricity **sold to customers** + net exports) — i.e. the
denominator is already net of T&D losses, confirming the ratio bundles both
effects rather than being a T&D-only figure.
Our grid emission factor is already **grams CO₂e per kWh *generated*** — it has
the generation mix and its conversion losses fully baked in. Multiplying
delivered kWh by 1.83 would **double-count** the generation-side losses (once in
the EF, once in the ratio) and roughly double every electricity emission. The
only quantity we still need to add on top of a per-kWh-generated EF is the
**delivery loss between the plant busbar and the meter** — i.e. T&D only — which
is the ~5 % line-loss slider, *not* the 1.83 source–site ratio.

---

## Refrigerant GWP and charge mass (corrected 2026-08-12)

**The bug (found in review, 2026-07-28; fixed 2026-08-12):** the four
refrigerant options (R-410A, R-32, R-454B, R-290) shared one flat charge
mass (`0.25 kg per rated kW`, the same for all four) and used AR4/AR5-era
GWP100 values that were also internally inconsistent — the UI selector said
R-410A's GWP was 2088, but the engine's own self-test vector
(`METHODOLOGY.md` §Validation) had already been using 2256 for the same
refrigerant. Both are now fixed and use one consistent number throughout.

**GWP100 — IPCC AR6, blend-weighted.** AR6 WG1 Ch.7 Table 7.SM.7 gives GWPs
per pure molecule; commercial refrigerant blends are weighted by their
constituent mass fractions (e.g. R-410A = 50% R-32 + 50% R-125 by mass).
Sourced via a peer tool's review (Building Decarbonization Alliance's *Heat
Pump Lifecycle Emissions Explorer* — see `BDA_COMPARISON.md`), which shows
its blend arithmetic in a code comment:

| Refrigerant | GWP100 (was) | GWP100 (now) |
|---|---:|---:|
| R-410A | 2088 | **2256** |
| R-32 | 675 | **771** |
| R-454B | 467 | **531** |
| R-290 (propane) | 3 | **0.02** |

**Charge mass — ratio-scaled from a peer tool, anchored to our own baseline.**
The engine computes `charge_kg = ratedCap_kW × (kg per kW)`. R-410A's
`0.25 kg/kW` is this tool's own original figure (kept as the anchor — not
independently re-sourced here). The other three refrigerants are that
baseline scaled by the *ratio* between refrigerants in the same peer tool's
reference unit (R-410A 3.6 kg : R-454B 3.4 kg : R-32 2.3 kg : R-290 0.5 kg).
Because that reference unit's own capacity isn't stated in the peer tool's
published constants, only the **ratio** between refrigerants is portable —
not their absolute kg figures, which is why our R-410A anchor (`0.25 kg/kW`)
is kept rather than replaced with `3.6 kg ÷ (their unknown capacity)`:

| Refrigerant | Ratio to R-410A | kg/kW (this tool) |
|---|---:|---:|
| R-410A | 1.000 | **0.250** |
| R-454B | 0.944 | **0.236** |
| R-32 | 0.639 | **0.160** |
| R-290 (propane) | 0.139 | **0.035** |

R-290's low ratio is physically expected, not just an artifact of a smaller
molecule: propane's flammability class caps the maximum allowable charge in
a residential system by refrigeration/building code, independent of its
thermodynamic properties.

**Uncertainty, stated plainly.** This is a ratio-scaling approximation, not
an independently-sourced per-refrigerant charge curve fitted to real
manufacturer data across the capacity range this tool covers (<18k to
≥42k Btu/h). A real per-unit charge figure would vary by manufacturer,
system architecture (line-set length, indoor coil design) and refrigerant
circuit design, not just refrigerant type and capacity. Treat the resulting
`charge_kg` as a representative estimate, same caveat level as the rest of
this tool's screening-grade lifecycle terms.

**Corroboration check (2026-08-12) — weak, not a source.** A general web
search turned up density-based line-set-charge factors on several
HVAC-contractor "refrigerant charge calculator" sites (e.g. hvactoolkit.org,
aristotleair.com, hvacbase.org) — uncited rule-of-thumb content aimed at
installers, not a manufacturer spec, AHRI figure, or engineering standard,
and no original source was traced. They put R-32 at ≈0.65× and R-454B at
≈0.93× an R-410A charge for the same capacity, versus this tool's 0.639/0.944
— in the same neighbourhood, which is worth recording, but this is **not**
independent verification of the BDA-derived ratios and should not be read as
such. No comparable figure exists anywhere for R-290, whose charge is
code-capped by flammability class rather than density, so it has no check at
all. If a defensible per-refrigerant charge curve is ever needed, the right
next step is AHRI's certified-equipment nameplate data or manufacturer
submittal sheets, not another web search.

### GWP20 added, as a user toggle (2026-08-12)

User asked for the GWP source and whether to re-implement GWP20 alongside
GWP100 — the engine had only ever used the 100-year figure, while the
upstream-methane term (above) already runs on a fixed 20-year GWP per TAF's
own guidance that near-term fuel-switching analysis should use the 20-year
horizon, not the 100-year inventory basis. HFCs are short-lived (5–30 yr
atmospheric lifetime), so unlike CO₂ they look considerably worse on a
20-year window than a 100-year one — neither horizon is "wrong," they
answer different questions (100-yr: standard national/corporate GHG
inventories; 20-yr: near-term climate forcing).

**Sourcing — primary source read in full, 2026-08-12.** User added
`HeatPump/data/raw/IPCC_AR6_WGI_Chapter07_SM.pdf` to the repo (the fetch
tool gets HTTP 403 on the IPCC site directly; a normal download does not).
**Table 7.SM.7** (p.29, "Data Table" — actually spans pp.16-27, "Tables of
Greenhouse Gas Lifetimes, Radiative Efficiencies and Metrics") was read
directly. Per-molecule GWP20/GWP100, exactly as printed:

| Molecule | GWP20 | GWP100 |
|---|---:|---:|
| HFC-32 (CH₂F₂) | 2,690 | 771 |
| HFC-125 (CHF₂CF₃) | 6,740 | 3,740 |
| HFO-1234yf (CF₃CF=CH₂) | 1.81 | 0.501 |
| Propane (C₃H₈) | 0.072 | 0.02 |

Blend arithmetic (R-410A = 50% R-32 + 50% R-125; R-454B = 68.9% R-32 +
31.1% R-1234yf, per Chemours' Opteon XL41 datasheet composition) reproduces
our shipped figures to the decimal, not just approximately:

- R-410A GWP20 = 0.5×2,690 + 0.5×6,740 = **4,715.0** (shipped: 4715)
- R-410A GWP100 = 0.5×771 + 0.5×3,740 = 2,255.5 ≈ **2,256** (shipped: 2256)
- R-454B GWP20 = 0.689×2,690 + 0.311×1.81 = **1,853.97** (shipped: 1854)
- R-454B GWP100 = 0.689×771 + 0.311×0.501 = 531.37 ≈ **531** (shipped: 531)
- R-290 (propane, unblended): GWP20 **0.072**, GWP100 **0.02** — matches
  shipped values exactly.

This supersedes the earlier version of this fix, which relied on two
secondary sources (GHG Protocol's reprint, and Refrigerant Management
Solutions' NY-state compliance table) because the primary PDF returned
HTTP 403 to the fetch tool. Both secondary sources turn out to have been
correct — this primary read confirms them exactly — but they were
presented at the time as "confirmed" without disclosing that the primary
document had not actually been opened. That was a mistake in how the
sourcing was reported, not in the numbers themselves; flagged and
corrected same day (see `source-access-and-assumption-transparency`
project memory).

| Refrigerant | GWP100 | GWP20 |
|---|---:|---:|
| R-410A | 2,256 | 4,715 |
| R-32 | 771 | 2,690 |
| R-454B | 531 | 1,854 |
| R-290 (propane) | 0.02 | 0.07 |

**Implementation.** `heatpump.html` — new `REFRIG_GWP100` / `REFRIG_GWP20`
constants (replacing the single `REFRIG_GWP`), a `refrigGWP(refrig,horizon)`
lookup, and a **GWP horizon** segmented toggle next to the refrigerant
selector (`#gwp-horizon-seg`, same `.seg` pattern as the existing
average/marginal grid-basis toggle), defaulting to **100-yr**. A live hint
under the refrigerant dropdown shows the resolved GWP value. The toggle is
part of the `recompute()` cache key so switching it forces a fresh
calculation. Self-test vectors are unaffected (they pass an explicit
`refrigerantGWP` literal, not the UI lookup).

**Scope decision:** the upstream-methane term keeps its existing fixed
20-year GWP (85, TAF Fugitive Methane guideline) rather than also being
wired to this toggle — its 2.14% leak-equivalent rate is calibrated
specifically against TAF's own GWP20-basis +65% ratio (see "Lifecycle terms"
above), and switching it to GWP100 would require a separately-sourced
recalibration TAF's guideline doesn't provide. The new toggle affects only
the refrigerant-leak term.

---

## Refrigerant charge mass — real manufacturer data (2026-08-12)

**Prior state.** `charge_kg = ratedCap_kW × (kg per kW)`, one flat ratio per
refrigerant: R-410A 0.250 (this tool's own unsourced original figure, kept
as an anchor), R-454B 0.236, R-32 0.160, R-290 0.035 (all three scaled off
R-410A by a *ratio* reported by a peer tool, BDA's Heat Pump Lifecycle
Emissions Explorer, for an unstated reference unit — see "Refrigerant GWP
and charge mass" above). User asked directly whether the manufacturer spec
sheets already on file (`data/raw/spec_sheets/`, gathered for Phase 3c
capacity/COP curve work) list factory refrigerant charge. **They do, in
most of them** — this had gone unused for the charge-mass question.

### Extraction

Searched every PDF in `data/raw/spec_sheets/` (`pdftotext -layout`, grepped
for charge/refrigerant fields) for a **factory-charge weight paired with a
stated rated capacity for the same single-zone/single-outdoor-unit model**
— excluding multi-zone systems (total charge depends on how many indoor
heads are connected, not a fixed nameplate figure) and any table where the
capacity-to-charge column mapping was ambiguous. Every accepted point, its
source file, and the exact source text is in
`HeatPump/reference/refrigerant_charge_datapoints.csv`.

**R-410A, n=6** (GREE GUD48W2 ducted single-zone; Carrier 25HNB9 3/4/5-ton;
TOSOT APEX 24k; LG LA120HYV3 ductless mini-split):

| Unit | Rated capacity | Factory charge | kg/kW |
|---|---:|---:|---:|
| GREE GUD48W2 | 13.48 kW | 4.499 kg | 0.334 |
| Carrier 25HNB9 (3-ton) | 10.55 kW | 6.39 kg | 0.606 |
| Carrier 25HNB9 (4-ton) | 14.07 kW | 6.78 kg | 0.482 |
| Carrier 25HNB9 (5-ton) | 17.58 kW | 6.78 kg | 0.386 |
| TOSOT APEX 24k | 7.03 kW* | 3.487 kg | 0.496 |
| LG LA120HYV3 | 3.99 kW | 1.151 kg | 0.288 |

*TOSOT's rated *heating* capacity column was misaligned in the source PDF
(printed the electrical spec instead); the *cooling* rated capacity (24,000
Btu/h) is used as a proxy, same convention already used elsewhere in this
tool when a heating figure isn't cleanly available.

**R-454B, n=4** (Lennox SL22KLV 2/3/4/5-ton, the only R-454B line found
with both capacity and charge):

| Unit | Rated capacity | Factory charge | kg/kW |
|---|---:|---:|---:|
| SL22KLV-024 (2-ton) | 6.45 kW | 4.905 kg | 0.760 |
| SL22KLV-036 (3-ton) | 9.67 kW | 7.625 kg | 0.789 |
| SL22KLV-048 (4-ton) | 12.89 kW | 7.625 kg | 0.592 |
| SL22KLV-060 (5-ton) | 16.11 kW | 7.427 kg | 0.461 |

Flagged, not corrected: the 4-ton and 5-ton units carry *less or equal*
charge than the 3-ton unit, printed exactly that way in the source
document. Kept as printed rather than adjusted on suspicion of a
transcription error — a real possibility, but not one this pass can
confirm or rule out.

**No R-32 or R-290 unit was found** in the spec-sheet set with a stated
charge — that set was gathered for capacity/COP curves, not for charge, and
happens to be all R-410A/R-454B units. This is a real gap, not resolved
here.

### Fit

Both real refrigerants' data show the same **shape a flat ratio cannot
express**: charge per kW of capacity is *higher* for smaller units, not
constant — consistent with a largely fixed line-set/coil charge that gets
amortized over more capacity as units get bigger. A linear fit,
`charge_kg = a + b × ratedCap_kW` (least-squares, `numpy.polyfit`), captures
this:

| Refrigerant | a (kg) | b (kg/kW) | n | Source |
|---|---:|---:|---:|---|
| R-410A | 0.505 | 0.391 | 6 | real manufacturer data |
| R-454B | 4.245 | 0.235 | 4 | real manufacturer data |
| R-32 | 0.322 | 0.250 | 0 | R-410A curve × BDA's 0.639 charge ratio (unverified) |
| R-290 | 0.070 | 0.054 | 0 | R-410A curve × BDA's 0.139 charge ratio (unverified) |

R-32 and R-290 keep the **old ratio-scaling approach** — applied to the new
R-410A curve's `a` and `b` together rather than to a single flat number, so
at least the *shape* is now consistent with real data even though the
*magnitude* for these two remains an unverified peer-tool ratio.

Charge at standard sizes (1 ton = 3.517 kW), for reference:

| Refrigerant | 2 ton | 3 ton | 4 ton | Source |
|---|---:|---:|---:|---|
| R-410A | 3.26 kg | 4.63 kg | 6.01 kg | real spec-sheet fit, n=6 |
| R-454B | 5.90 kg | 6.72 kg | 7.55 kg | real spec-sheet fit, n=4 |
| R-32 | 2.08 kg | 2.96 kg | 3.84 kg | BDA ratio × R-410A curve — unverified |
| R-290 | 0.45 kg | 0.64 kg | 0.83 kg | BDA ratio × R-410A curve — unverified |

### What this changes

The real data show the tool's prior R-410A baseline (0.250 kg/kW) was **too
low across the entire sampled capacity range** — every one of the 6 real
units runs higher, from +15% (LG, smallest unit) to +142% (Carrier 3-ton).
The refrigerant-leak GHG term was therefore understating emissions for
every refrigerant option, not just misjudging the ratios between them (the
2026-08-12 GWP fix, above, was a separate and independent correction to the
same term).

### Uncertainty, stated plainly

n=6 and n=4 from a handful of brands is a spot-check, not a systematic
survey of the residential ASHP market — a proper version would need dozens
of units per refrigerant across more manufacturers and capacity bands. The
extraction was manual (grep + hand verification per file), not an automated
parser, because the charge field's table layout differs by brand the same
way the capacity/COP tables already documented in `DATASHEET_INVENTORY.md`
do, and building a bespoke parser for ~10 usable points was not worth it.
R-32 and R-290 remain entirely unverified against manufacturer data. Treat
this as a real improvement over the prior ratio-scaled baseline, not a
settled figure.

---

## Tiered electricity pricing — removed (2026-08-12)

**Why.** Tiered plans (ON's monthly two-tier structure, QC's Hydro-Québec
Rate D daily two-tier structure) price a household's *marginal* kWh
differently depending on how much it has already used in the billing period.
To price the *added* heating load correctly within a tiered plan, the engine
had to assume a **non-heating household baseline** — 750 kWh/month for ON,
25 kWh/day for QC — neither of which this tool has any way to know for a
real household (appliances, occupants, other electric loads are entirely
unmodelled). User's call: remove the feature rather than keep it resting on
an unstated guess.

**What was removed** (`heatpump.html`): the `tierCost`/`monthlyTieredRate`
functions, the `tiered` branch of `costElectricity`, the
`BASELINE_ON_KWH_MONTH`/`BASELINE_QC_KWH_DAY` constants, and the `tiered`
entry from `PLAN_LABEL`. `Python/rates_etl.py`'s `build_on_city` no longer
collects the OEB tiered tariff; `prices_json/on.json` regenerated without
it (both cities keep TOU as default and ULO as the alternative — no loss of
functionality for Ontario, which has two genuine non-tiered options).

**The Quebec problem.** Hydro-Québec's Rate D is the *only* public
residential tariff QC has data for, and it **has no flat/non-tiered
option** — removing "tiered" outright would have left Quebec with zero
supported electricity plans and a broken operating-cost card. Rather than
silently degrade QC to "rates unavailable" or invent a new baseline
assumption in a different guise (e.g. a "typical" blended rate, which
would just relocate the same unknowable-occupant-usage problem), Quebec's
plan is now priced entirely at **Rate D's tier-2 (marginal/top-tier) rate**
— `plans.marginal`, `type: "flat"`, `price_cad_per_kwh` = the tier-2 figure
(0.11142 CAD/kWh as of the 2026-04-01 rates on file). This needs **no
baseline assumption at all**: Rate D's first tier ends at 40 kWh/day
(~1,200 kWh/month), and any home with a materially-sized electric heating
load — the exact case this tool models — will push its *total* daily usage
past that threshold on essentially every day it's heating, so its heating
electricity sits in tier 2 regardless of what else the household draws.
The only place this slightly overstates cost is the sliver of load on the
very mildest heating days, where a low-heating-demand home's total daily
usage might dip back under the 40 kWh threshold — a small, one-directional
(cost-conservative, not cost-flattering) approximation, stated here rather
than left implicit.

**Validation constant updated.** `rates_etl.py`'s self-check band for a
1,500 kWh Montreal month moved from the old tier-1-heavy estimate
($120–185) to reflect all-marginal pricing (**$150–200**, actual ≈ $181.17
= 1,500 × 0.11142 + $14.04 fixed) — the same real published Rate D numbers,
just a different exposure assumption per the above.

**Verified live:** ON's plan selector now shows only Time-of-use (default)
and Ultra-low overnight; Quebec's cost card renders correctly with "Hydro-
Québec, marginal (top-tier) plan" in the fine print and no plan selector
(single plan, row auto-hidden — same UI behaviour as any city with one
plan); zero console errors in either case.

---

## Line loss — province-specific (2026-08-12)

**Where this started.** User: "for the upstream GHG, I think we need to use
the 1.83 factor (the IESO data is electricity generation, not purchase, so
for 100 kWh of electricity you use, 183 kWh needs to be generated)." This
was investigated before implementing anything, per the standing rule to
flag inaccessible sources and shaky premises rather than build on them
silently (see project memory `source-access-and-assumption-transparency`).

**Why 1.83 doesn't hold up.** The 1.83 figure is ENERGY STAR Portfolio
Manager's electricity "source-site" ratio. What it actually measures,
per ENERGY STAR's own definition, is losses across *production*,
transmission and delivery — and production (the thermal inefficiency of
burning fuel to generate electricity, often ~35–45% efficient) is the
dominant term, not transmission/distribution loss; Canada's ratio is
explicitly lower than the US's specifically because Canada's hydro/nuclear
mix has less of that generation inefficiency to begin with. This tool's
grid EF is already expressed **per kWh generated** (`build_grid_ef.py`'s
`Average EF = gas_output(h) / total_output(h) * GAS_EF`, both IESO
generation-by-fuel figures) — a gas plant's thermal inefficiency is exactly
why its g/kWh figure is high in the first place; that inefficiency is
already in the number. Applying 1.83 on top would double-count it. Real
Canadian T&D loss data confirms this: IESO's own transmission loss is only
~2% of generated power (IESO Transmission Planning Guideline), nowhere
near 83%.

**The real question, and the answer.** The legitimate version of the user's
concern — IESO/AESO/HQ generation data vs. what a home actually purchases —
*is* the existing line-loss term, previously a flat 5% Canada-wide World
Bank/IEA estimate. Investigated with province-specific regulator data
instead:

- **ON — 7.4%.** Ontario Energy Board's own [Distribution System Losses
  audit](https://www.oeb.ca/oeb/_Documents/Audit/report_audit_system_losses_20080624.pdf)
  (2008, data 2002–2006): distributors' approved Total Loss Factor (TLF)
  averaged **5.31–5.42%** (2005–2006) — defined by the OEB as "the value by
  which the end-use metered load must be multiplied... to equal the
  estimate of the total energy supplied," i.e. exactly the wholesale-
  purchase-to-retail-meter gap. This is distribution-only; IESO's own
  transmission loss is separately ~2%. Compounded: 1.02 × 1.0531 ≈ 1.074 →
  **7.4%**.
- **AB — 7.68%.** The same OEB report's cross-jurisdiction appendix cites
  the CEA's Electricity Consumption Report, corroborated by a CASA-hosted
  study of Alberta's electrical supply system efficiency: Alberta
  transmission losses 4.45% (2003) and transmission+distribution
  **combined 7.68%** (2002) — already a full-chain figure, used directly.
- **QC — 7.5%.** Same OEB appendix, citing Québec's own Régie de l'énergie:
  a **blended** (T&D combined) loss factor of 7.5% — used directly.
- **BC/MB/NS/SK — 5% (unchanged fallback).** No province-specific source
  found for these; they also have no hourly grid pipeline in this tool
  (flat ECCC-annual EF only), so the generic Canada-wide World Bank/IEA
  figure remains the best available default.

**Uncertainty, stated plainly.** All three province-specific sources are
dated (2002–2008) — the OEB report itself is from 2008, the CEA/Alberta
data from 2002–2003. This is the most specific data found, not a claim of
current-year precision; distribution infrastructure and loss rates do
shift over a couple of decades (the OEB report's own 2019–2024-era
successor, if one exists, was not located). All three provinces converge
surprisingly tightly (7.4–7.68%) despite being independently sourced,
which is reassuring but could also mean the underlying CEA-era methodology
was shared across jurisdictions rather than three truly independent
measurements — noted, not resolved.

**Implementation.** `heatpump.html` — `LINELOSS_PCT_BY_PROV` replaces the
flat `UPSTREAM_LINELOSS_PCT` constant; `lineLossPctFor(city)` looks up the
current city's province, falling back to 5% for provinces without a
specific figure. Recalculated on both the upstream Yes/No toggle and city
change (so switching provinces updates the default). No new UI control —
still governed by the existing Yes/No toggle, per the "Open to-do" note in
"Lifecycle terms" above about eventually exposing these as adjustable
rates again.

**Impact on already-published figures:** small. Moving from 5% to
7.4–7.68% shifts only the *electricity* GHG term (not gas combustion or
refrigerant) by roughly +2.3–2.6%, i.e. well inside this project's existing
±15–30% validation tolerances — see the flag added to "Validation against
published benchmarks" above.

---

## Methane leakage map — GFEI 2016 (2026-08-12)

Added a section-page map ("Where upstream methane comes from") plus a
methodology entry (`#m-methane-map` in `heatpump.html`) so the fixed
2.14% upstream-methane lever (see above) has a geographic anchor: where
fugitive oil/gas/coal methane actually clusters in Canada.

**Source.** NASA GES DISC's Global Fuel Exploitation Inventory (GFEI) CH4,
v1, 2016 (Scarpelli et al. 2020, https://doi.org/10.5194/essd-12-563-2020;
DOI 10.5067/Q28GFYJYFZ7H). A global 0.1°×0.1° grid built from countries'
own UNFCCC reports where available, IPCC 2006 defaults elsewhere, for
IPCC category 1B2 (fuel exploitation — fugitive emissions, not
combustion), spatially allocated to mines, wells, pipelines, compressor
stations, storage, processing plants and refineries **combined into one
number per fuel type**. It is not a pipeline-only or transmission-only
layer, despite starting life (in the prior session that sourced this
file) framed as "pipeline GIS data" — that framing doesn't survive
contact with what the file actually contains, and the page/doc language
was corrected to avoid repeating it. NASA/US-federal data products are
public domain and freely redistributable — no EULA constraint like
NRCan's heat-pump tool (see `heatpump-nrcan-and-neep-licensing` decision).

**2016 is the newest vintage at this scope.** Checked for a newer
equivalent; none exists that we could find. Treated explicitly as a
historical snapshot in the page copy, not implied as current.

**Processing** (`Python/gfei_ch4_extract.py`): subset the global `.nc` to
Canada's bounding box (41–79°N, 142–50°W) at the **native 0.1° resolution**
— no aggregation. An earlier version of this pipeline block-meant to a
coarser 0.5° grid purely to shrink the file, but that discarded real
structure: 0.1° resolution visibly shows the Great Lakes, coastlines and
what reads as actual road/well-pad texture across the AB/BC/SK oil-and-gas
belt, all of which the 0.5° version blurred into flat horizontal stripes.
Output: `HeatPump/data/processed/gfei_ch4_canada_2016.json`, ~115,000
nonzero cells, ~3.4 MB (lon/lat stored as compact `row`/`col` grid indices
— `lat = lat0 + row*0.1`, `lon = lon0 + col*0.1` — rather than repeating
float coordinates per cell, to keep the native-resolution file smaller
than it would otherwise be; served same-origin so a normal HTTP gzip
transfer applies).

**Resolved vs. background split.** At native resolution a second problem
became visible: large contiguous patches share the *exact* same emission
value — GFEI spreads a country/region's reported total across cells it
can't spatially resolve using one shared modelled rate (a proxy mask —
basin extent, well density, etc.) rather than an independently-estimated
per-cell value, which reads as a flat, illegible block rather than
texture. Checked directly against the raw NetCDF values (not inferred
from the plot): within the Canada subset, **56% of nonzero gas cells**
share their exact float32 value with at least one other cell (one value
alone — `8.816e-10` — repeats across 10,620 cells), a coincidence that's
essentially impossible at that scale unless deliberately assigned. Oil is
almost entirely unaffected (99.3% of nonzero oil cells hold a genuinely
unique value) and coal likewise (86.2% unique, one 12-cell repeated
patch). The pipeline now flags each cell, **per fuel layer independently**,
as `background` if its exact value is shared by ≥1 other nonzero cell of
that layer within the subset, `resolved` otherwise — stored as a 4-bit
`bg_bits` mask per cell (oil=1, gas=2, coal=4, total=8) rather than four
separate boolean fields, to keep the file smaller. No threshold to
justify: either a value is unique or it demonstrably isn't.

**Rendering** (`heatpump.html`, `renderMethaneMap`/`loadMethaneMap`).
Switched from per-cell SVG `<rect>` elements (fine at 5,200 cells, not at
115,000 — that many DOM nodes visibly slowed the page) to a **canvas pixel
buffer**: one canvas pixel per native grid cell, built with
`ImageData`/`putImageData` in a single pass and then CSS-scaled up with
`image-rendering:pixelated`. Hover uses a `Map` keyed by `"row,col"` for
O(1) lookups instead of per-shape `<title>` tooltips (which don't exist at
this cell count either). **Resolved** cells draw on the log-scaled,
single-hue amber sequential ramp (pale → deep brown, consistent with the
existing "Upstream fuel supply" amber used elsewhere on this page); the
log domain is computed from resolved cells only, so a handful of flat
background values can't compress the genuinely-varying signal's range.
**Background** cells draw as a flat neutral gray, distinct from the ramp
on purpose — the map should not imply those locations were independently
measured — with a page-level "Hide background" checkbox to drop them
entirely for readers who want to see only the resolved signal. Projection
unchanged: simple equirectangular with an x-axis cosine correction at the
bbox's mid-latitude (~60°N) to avoid extreme east–west stretch —
approximate, fine for a "where does it cluster" visual, not a
precise-distance map.

**Cropped to Canada + outline overlay (same day, follow-up pass).** The
lat/lon bounding box used to subset the NetCDF (41–79°N, 142–50°W) still
included a strip of US territory along the border — Great Lakes south
shore, North Dakota, Maine — which showed up on the map with no visual
indication it wasn't Canada. Fixed by building a single unioned Canada
land-boundary polygon (`Python/canada_boundary.py`) from the FSA geometry
already committed for the choropleth maps (`geo_json/*.json`) plus Yukon
(missing from that set — pulled from the raw national file at the repo
root and reprojected with the same hand-derived inverse Lambert formula
`Python/build_fsa_geometry.py` uses, copied rather than imported so this
module doesn't depend on that one-off script), simplified to the grid's
own ~0.1° resolution and buffered outward 0.05° so grid cells right at the
real coast/border aren't dropped just because their center sits a hair
outside the vector line. 33,201 of 115,271 cells (mostly US) were dropped
this way; background/resolved percentages were recomputed *after* the
crop so they reflect Canada alone, not the wider bbox (Canada-only gas is
78% background, up from the wider bbox's 56% — the US portion this
removed had relatively more independently-resolved cells, i.e. was
skewing the "how much is real signal" read on this map before the fix).
A second, much more heavily simplified/area-filtered version of the same
polygon (`canada_outline` in the shipped JSON, ~182 rings before
tightening → 34–44 rings, tolerance 0.12°, islands under 0.4 deg² dropped)
is drawn by the page as a thin reference outline over the data, so a
reader can place what they're looking at without needing basemap tiles.

**Sinusoidal projection, collapsed-by-default, gas-first defaults (same
day, second follow-up pass).** The canvas raster had been drawn with each
grid cell as one literal pixel — an uncorrected Plate Carrée, which reads
as a flat, unnaturally wide rectangle at high latitude (a degree of
longitude spans a real distance at 42°N very different from one at 78°N,
but the raw grid gives both the same pixel width) and doesn't match how
Canada is normally drawn. Replaced with a **sinusoidal (Sanson-Flamsteed)
projection** — a real, named equal-area projection, not an ad hoc squeeze:
each row is horizontally rescaled by `cos(lat)/cos(lat0)` about the grid's
own centre column (`lat0` = the bbox's southmost row, so the south stays
full width and rows narrow going north; y/latitude is untouched). Built by
rendering the raw raster to an off-screen canvas exactly as before, then
`drawImage`-ing it onto the visible canvas one row at a time at that row's
own scale — 380 draw calls, trivial cost. The `canada_outline` overlay and
the hover-tooltip's screen-to-grid-cell lookup both apply the identical
per-row transform (and its inverse, for hover) so the outline still traces
the warped coastline and hovering still resolves the correct cell.

Both this section and "What real homes in \<city\> look like" are now
wrapped in native `<details>`, collapsed by default, matching the
`<details>` pattern already used for the methodology accordion elsewhere
on this page. Collapsing-by-default made the map's ~3MB JSON fetch worth
deferring: it's now requested only on the `<details>` element's first
`toggle` to `open`, not unconditionally at page load, via
`bindMethaneMapLazyLoad()`. Page defaults changed from "all sources" +
background shown to **gas** + **background hidden** — gas is where nearly
all of the background/shared-rate problem lives (see above), so hiding it
by default shows the most legible view first; readers can switch either
back on.

**Sinusoidal → Albers Equal-Area Conic (same day, third follow-up pass).**
Compared six candidate projections side by side (Plate Carrée, Sinusoidal,
Lambert Conformal Conic, Albers Equal-Area Conic, oblique Stereographic,
Orthographic) rendered from the same `canada_outline` data via `pyproj`,
as a one-off comparison script, not part of the shipped pipeline. Landed
on **Albers Equal-Area Conic** (standard parallels 50°N/70°N, origin 40°N,
central meridian 96°W — the same parameters as Esri's "Canada Albers Equal
Area Conic", a standard choice for Canadian thematic maps) over the more
visually familiar Lambert Conformal Conic for one specific reason: **this
map's colour encodes emission density per km².** Lambert is conformal
(preserves local angles/shape) but not equal-area, so it can quietly
distort the apparent size of a patch relative to its real land area —
exactly the wrong property for a map where "the coloured patch looks big"
is meant to mean "this covers a lot of km²," not "the projection stretched
it here." Sinusoidal was already equal-area (Snyder's pseudocylindrical
family), so the change is really "equal-area, but shaped like the country
people actually recognize" rather than a correctness fix.

Implementation is a step up from Sinusoidal's per-row horizontal scale,
because a conic projection genuinely curves in two dimensions — there's no
single per-row scale factor that reproduces it. Standard spherical Albers
forward/inverse formulas (Snyder eq. 14-1..14-4 / 24-1..24-3) are
implemented directly in `heatpump.html` (`albersForward`/`albersInverse`).
Rendering builds a **destination-pixel → source-cell lookup table** once
per data load (`buildMethaneMapProjection`): for every pixel in the output
canvas, inverse-project it back to lon/lat and nearest-neighbour-sample the
source grid (native cell spacing is small enough that nearest-neighbour is
indistinguishable from any smarter resampling at this map's display size).
That table — an `Int32Array`, one entry per destination pixel, pointing at
an index into `d.cells` or `-1` — is then reused by every subsequent
render (metric/background toggles) and by hover, so the relatively
expensive inverse-trig only runs once per page visit (~60ms for the
~450,000-pixel canvas, measured in-browser), not once per interaction
(~15-20ms per re-render, reading the lookup table). The `canada_outline`
overlay uses the plain forward projection (vector data doesn't need the
inverse/lookup machinery); hover looks up the same table used for
rendering rather than repeating any trig at all.

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

> **Stale-by-a-little, flagged rather than silently left (2026-08-12).** This
> section's tables were produced with the flat 5% line-loss figure in force
> at the time. Line loss is now province-specific (7.4% ON, 7.68% AB, 7.5%
> QC — see "Line loss — province-specific" below), so the electricity-GHG
> figures below understate the current live page by roughly the same small
> margin the line-loss figure moved (≈ +2.4% ON, +2.7% AB electricity-GHG
> component only — gas-combustion and refrigerant terms are unaffected).
> This is well inside the ±15–30% tolerances this section already works to,
> so the qualitative conclusions below still hold; the absolute numbers were
> not re-run against the new line-loss figures for this pass.

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
  regular weekdays (<1% effect). ON offers TOU (default) and ULO via a plan
  selector; both scenarios always use the same plan. **Tiered plans removed
  2026-08-12 — see "Tiered electricity pricing — removed" below.**
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

## Per-temperature visuals & KPI row (2026-07-16)

Aligns the page with the tool's original visual brief: KPIs covering
**energy, GHG and $** in one row, and per-temperature views of energy use
and emissions for both scenarios. No methodology change — purely new
aggregations of quantities the engine already computed hour-by-hour.

**Engine (additive only).** `simulate()` now also emits hourly
**purchased-energy** series alongside the existing hourly GHG series:
`hourly.base_energy_kWh` (the incumbent system's fuel-or-electricity input),
`hourly.hp_elec_kWh`, and `hourly.backup_energy_kWh` (fuel or electricity,
per the backup type). All 15 self-test vectors unchanged and passing.
`app/engine.js` had drifted behind the engine inlined in `heatpump.html`
(it lacked `elec_month_hour` and the hourly series); it is now a verbatim
extract of the inlined copy, with a header note saying so — edit one,
re-sync the other.

> ⚠️ **Known tech debt — the two engines must be consolidated (deferred).**
> "Edit one, re-sync the other" is a manual discipline, not a guarantee: this
> exact pair has already drifted once (that's why the paragraph above exists),
> and the copy users actually run is the *inlined* one, so a fix applied only
> to `app/engine.js` would pass `engine.test.js` and `validate_engine.py` while
> changing nothing on the live page. The fix is one source of truth — a build
> step that injects `app/engine.js` into `heatpump.html`, or shipping it as a
> separate `<script src>` and deleting the inline copy. Tracked in
> [ROADMAP.md](../ROADMAP.md) under Queued. **Scheduled for later; not part of
> the current heat-pump-selection rework.** Until then, any engine change must
> be applied to BOTH copies in the same commit.

**"By outdoor temperature" chart pair — removed 2026-07-30.** An earlier
version binned every positive-load TMY hour into 2 °C bins (`tempBinLeft`)
and summed energy and emissions per bin, as a pair of charts in "Across the
year". The **page re-organisation of 2026-07-30** removed both as redundant
with the load-vs-capacity chart in the "Why: heat needed vs heat delivered"
section, which already shows the temperature dependence directly. The
`binByTemp` / `renderTempEnergyChart` / `renderTempGhgChart` functions and the
`tempEnergyChart` / `tempGhgChart` canvases were deleted from `heatpump.html`.

**KPI row.** Added two cards: **Energy purchased** (base fuel+electricity →
HP+backup input, % change) and **Operating cost** (the $ delta from the
cost card, `now → after` amounts in the subtitle; shows "rates unavailable"
if the province's prices file fails to load, and carries the same
"(screening estimate)" flag as the cost card for low-confidence AB rates).

**Stale text fixed.** The assumptions panel's "What this does not do" still
said "No operating-cost/$ figures yet" from before the rates work; it now
says operating cost is covered but **capital cost / payback is not**.

**Verification (2026-07-16, browser at localhost):** engine self-test 15/15;
zero console errors; bin sums cross-checked against annual totals (above);
Montreal baseboard + no-backup case exercises the guards (near-zero-base
verdict, refrigerant-only delta, backup series dropped, unmet-heat KPI);
canvases confirmed painted via pixel sampling (this preview renderer
doesn't pump rAF, so screenshots are not reliable here).

## "Show the calculation" walkthrough (2026-07-16)

Adds an inline, collapsible **step-by-step calculation** under the KPI row
(`heatpump.html`, `renderWalkthrough()`), so the whole model can be
explained to anyone by hand. It is a **presentation layer only** — no
engine or methodology change; it re-states quantities the engine already
computes, with the current inputs plugged in, and updates on every
recompute. Collapsed by default (`<details>`), shown in both Simple and
Advanced modes.

Six steps, each with a plain-language sentence + the actual arithmetic:
1. **Heat demand** — archetype (n audited homes, area, design load) →
   `UA × (Tbalance − outdoor)` → annual heat over the heating hours.
2. **Heat-pump efficiency** — tier + representative models → seasonal COP;
   pump-vs-backup share of the year's heat.
3. **Energy purchased** — base `heat ÷ efficiency` (fuel, incl. m³ for gas)
   vs HP electricity + backup; the % change.
4. **Emissions today** — combustion `fuel × EF` (+ upstream methane/oil),
   or grid electricity for a baseboard base.
5. **Emissions with the heat pump** — `elec × grid-EF × line-loss` +
   refrigerant (+ backup combustion where applicable); the change.
6. **Operating cost** — the two annual bills and their difference
   (filled by `renderCost`; degrades to a plain "rates unavailable" note).

**Exact reconciliation.** Steps 4–5 display the *effective* grid intensity
actually applied — `ghg.electricity / (elec_kWh × line_loss)`, the
season-weighted average over the hourly EF surface — rather than the flat
reference level, so the shown arithmetic ties out to the headline totals to
the rounding shown (verified live: Ottawa gas→Tier-1 traces 22,986 kWh heat
→ 24,985 kWh gas → 5.0 t now vs 5.3 t / +7% / −61% energy / $822 per year,
matching the KPIs exactly).

**Guards reused.** Step 5 carries the same **near-zero-base** guard as the
verdict banner: when the incumbent grid is essentially carbon-free (QC
baseboard), it drops the exploding percentage and states the refrigerant-vs-
zero-carbon trade in words instead (confirmed no `\d{4,}%` renders in that
case). Line-loss shown to 2 dp so a 5 % loss reads `1.05`, not a rounded
`1.1`.

## One-line summary + KPI tooltips (2026-07-16)

Two small readability additions on top of the walkthrough, both presentation
only.

**"The short version" lede.** A single synthesis sentence at the very top of
the results (above the carbon verdict banner), combining all three headline
dimensions — energy, carbon, cost — in plain language, e.g. *"A premium heat
pump in a pre-1980 detached home in Ottawa uses 61% less energy but raises
carbon 7% on the marginal grid, and costs $822/yr more to run."* Built in
`render()`; the cost clause is patched in by `renderCost()` (async prices),
mirroring the cost-KPI pattern. The energy/carbon conjunction is "but" when
the two stories diverge (energy improves, carbon doesn't — including the
near-zero-grid case) and "and" otherwise. It reuses the same near-zero-base
guard (no exploding percentage; "barely changes carbon (grid already
near-zero)"). Archetype rendered via a short `ARCH_PHRASE` map ("pre-1980
detached home", "townhouse") so it reads naturally mid-sentence, unlike the
comma-form dropdown labels.

**KPI info tooltips.** Each of the seven stat cards carries a small "i" glyph
(`.stat-i`, native `title` + `aria-label`) with a one-line plain-English
explanation of what the number means and how it's derived (`TIP` map). The
Operating-cost card is rebuilt asynchronously by `setCostStat`, which now
also emits the glyph, so the tooltip survives the price load.

**Verification (2026-07-16, localhost):** self-test 15/15, zero console
errors; summary checked across Ottawa gas/marginal (diverge → "but", costs
more), Toronto townhouse gas (both improve → "and"), and Montreal baseboard
(near-zero guard → "barely changes carbon", saves $1,459); all 7 glyphs
render with tooltips.

---

## Heat pump performance tiers, rebuilt from AHRI (Phase 3c)

**Full specification: [TIER_SPEC.md](TIER_SPEC.md).** Summary of the decisions
and their evidence, recorded here because they supersede the Phase 3a/3b
NEEP-derived tiering described above.

**What changed and why.** The Phase 3a/3b tiers bucketed the NEEP product list.
That made the tier definition depend on a third-party database we cannot
redistribute, with boundaries of our own invention. The Phase 3c tiers are built
from AHRI-certified ratings on the actual Canadian installed base (439,975 AHRI
appearances, 15,148 distinct models from the ERS data), with cut points anchored
on published program thresholds.

**Tiering metric: capacity maintenance = capacity at 5 °F ÷ capacity at 47 °F.**
Not invented here — it is the ratio ENERGY STAR v6.2, CEE and NRCan's Greener
Homes ccASHP criterion all use, the last stating it explicitly as
`(Max −15 °C [5 °F]) / (Rated 8.3 °C [47 °F]) ≥ 70%`.

**The mixed rating basis (important).** The 5 °F rating is at MAXIMUM capacity;
47 °F and 17 °F are RATED points. NEEP ccASHP Specification v4.0 is explicit
("COP at 5°F ≥ 1.75 at maximum capacity operation"; 47/17 °F in the "Rated"
reporting column, 5 °F in "Maximum"). This is why 47.7% of models report a 5 °F
capacity above their 17 °F capacity — correct and expected, not a data error. A
monotonicity filter would silently discard ~180,000 installs of valid data. The
fitted capacity curve is therefore a **maximum-capacity envelope** below ~17 °C,
which matches how the engine consumes it, but must be stated in the UI.

**Rejected axes, with reasons.** COP @ 5 °F is unusable for ranking: 1.75 is the
shared certification floor across ENERGY STAR/CEE/NEEP and 54.8% of installs
report exactly 1.80. HSPF2 Region IV is *anti-correlated* with cold performance
here (the ≥10 band retains less capacity, 0.68, than the 9–10 band, 0.77) — it
is a mild-climate seasonal average. HSPF2 **Region V** is the correct
cold-climate seasonal metric, correlates better with capacity maintenance
(0.508 vs 0.449), and is available only from NRCan; it is used as the secondary
axis and as the COP-curve constraint.

**Source verification.** ENERGY STAR republishes AHRI figures rather than
measuring independently — on 3,447 models in both, 5 °F capacity agrees within
2% on 100% of rows. It is used for attributes only (compressor staging, market,
vintage). NRCan agrees with AHRI to a median 0.5 pp on capacity maintenance but
differs by >2 pp on 17.0% of models; AHRI is authoritative, NRCan fills gaps.

**AHRI's `cold_climate` flag is not used as the cut.** It is 99.8% precise but
under-reports badly — 91,431 installs meet the ≥70% criterion while flagged
`No`, because the designation post-dates their certificates.

**Tiers** (cut points 0.60 / 0.70 / 0.85; the first two are published program
floors, the third an install-weighted split of the large ≥0.70 mass):

| Tier | Definition | Installs | % base | med HSPF2 Reg V |
|---|---|---:|---:|---:|
| T0 Legacy (unrated) | no 5 °F point | 121,977 | 27.7% | — |
| T1 Non-cold-climate | < 0.60 | 12,921 | 2.9% | 6.95 |
| T2 Standard | 0.60–0.70 | 14,142 | 3.2% | 7.10 |
| T3 Cold-climate | 0.70–0.85 | 169,513 | 38.5% | 7.40 |
| T4 Premium cold-climate | ≥ 0.85 | 121,422 | 27.6% | 8.00 |

Region V rises monotonically T1→T4 without being used in the assignment — an
independent confirmation that the metric orders equipment sensibly.

**T0 is a real population, not a residue.** 99.2% Discontinued/Delisted, 0.0%
flagged ccASHP, 0.0% on new refrigerants — genuinely pre-designation equipment.
It gets a conservative modelled curve and must not be presented as equivalent to
a rated tier.

**Open item: `min_op_temp_C` (compressor lockout) has no source.** Not in AHRI,
not in ENERGY STAR, not in NRCan; NEEP requests it from manufacturers but it
lives in the product database, not the specification. Previously supplied by the
NEEP extract. Must be resolved — from manufacturer datasheets or a documented
per-tier assumption — before the rebuilt curves ship, since the engine's lockout
behaviour is governed by it.

---

## US DOE Cold Climate Heat Pump Challenge screen (2026-07-27)

Screens the whole installed base against the specifications of the **US DOE
Cold Climate Heat Pump (CCHP) Technology Challenge**, Table II-3:
<https://www.energy.gov/cmei/buildings/cchp-technology-challenge-specifications>

Built by `pipeline/screen_cchp.py`. Outputs `data/interim/cchp_qualifying.csv`
(units passing every checkable criterion) and `data/interim/cchp_screen.csv`
(all 15,148 models with their per-criterion result, for audit).

**Surfaced 2026-07-30** on [retrofit-insights.html](../retrofit-insights.html)
(section 06, "Cold-climate equipment"), alongside an AHRI COP-vs-capacity-
maintenance scatter of the same universe. Built by
`Python/build_hp_equipment_insights.py`, which reads the two CSVs above (plus
`hp_units_joined.csv` and `hp_buckets.csv` for the scatter) and writes
`insights_json/hp_ahri_scatter.json` and `insights_json/cchp_screen.json` —
see `docs/archive/ROADMAP_COMPLETED.md` item 14 for the build note.

### What the screen is, and what it is not

It is a screen against **published certificate ratings**. The Challenge is a
verification programme with its own H11/H1N laboratory test protocol, and we
hold AHRI certificate figures. A unit passing here has *rating-consistent*
performance and nothing more. The passing verdict is therefore named
`screen_pass`, and no column in the output is named "meets" or "certified".
**Do not relabel these in the UI.** The honest page wording is *"screened
against the DOE Challenge specifications"*, never *"meets the DOE Challenge"*.

### Thresholds (Table II-3)

| Nominal capacity (Btu/h) | COP at 5 °F | Capacity ratio at 5 °F |
|---|---:|---:|
| ≥ 24,000 and ≤ 36,000 | 2.4 | 100% |
| > 36,000 and ≤ 48,000 | 2.4 | 100% |
| > 48,000 | 2.1 | 100% |

Plus: minimum HSPF2 `8.5 × (1 + capacity factor) × (1 + COP factor)`, minimum
turndown ratio 30%, low-temperature compressor cut-out/cut-in limits at 5 °F
and −15 °F, electric heat staging per Table II-1, refrigerant GWP ≤ 750
(AR4 100-year), and ENERGY STAR CACHP §3C/4B/4C/4D.

### Which criteria we can actually check

Four of roughly eight. The rest are recorded as `not_checkable` columns rather
than quietly ignored:

| Criterion | Source | Status |
|---|---|---|
| Nominal capacity band | AHRI heating rated 47 °F | ⚠️ approximation — see caveat 1 |
| COP @ 5 °F ≥ 2.4 / 2.1 | AHRI certificate | ✅ |
| Capacity ratio ≥ 100% | AHRI, Max 5 °F ÷ Rated 47 °F | ⚠️ basis — see caveat 2 |
| HSPF2 ≥ 8.5 | NRCan SPL / ENERGY STAR | ⚠️ floor only — see caveat 3 |
| Refrigerant GWP ≤ 750 | ENERGY STAR refrigerant + AR4 table | ✅ |
| Turndown ratio ≥ 30% | — | ❌ needs minimum capacity; not in AHRI |
| Compressor cut-out / cut-in | — | ❌ not in AHRI or ENERGY STAR; datasheets give a lock-out only |
| Electric heat staging (Table II-1) | — | ❌ |
| ENERGY STAR CACHP §3C/4B/4C/4D | — | ❌ partially proxied by `es_cold_climate`, not evaluated |

**Caveat 1 — capacity band basis.** Table II-3 note 1 defines nominal capacity
by the **A2 test of Appendix M1**, a *cooling* test. We hold AHRI **heating
rated capacity at 47 °F**. Close, but not the same test: a unit near a band
edge (24,000 / 36,000 / 48,000 Btu/h) could be assigned the wrong COP
threshold. Carried per row as `band_basis`.

**Caveat 2 — capacity ratio basis.** Ours is `Max 5 °F / Rated 47 °F`, the
ratio ENERGY STAR v6.2, CEE and NRCan Greener Homes all define (TIER_SPEC.md
§2). The Challenge states "Capacity Ratio 100%" without naming the two points.
If it intends rated-to-rated, our figure is the **more generous** of the two —
so the qualifying set is, if anything, an over-count. Carried as `ratio_basis`.

**Caveat 3 — HSPF2 is a floor test only.** The real threshold is
`8.5 × (1 + capacity factor) × (1 + COP factor)`, and both factors derive from
H11/H1N verification-test results we do not have. We can only test the base
8.5. A `screen_pass` unit may still fail the actual, higher bar.
`hspf2_floor_only` is `True` on **every** row for exactly this reason.

### Results

Denominator is all **439,975 ERS appearances** across 15,148 models — the full
universe, not the 317,056-appearance screened grid of TIER_SPEC.md §3.

| Verdict | Models | Appearances | % |
|---|---:|---:|---:|
| `screen_pass` | 4 | 8 | 0.00% |
| `near` (exactly one gate failed) | 671 | 8,975 | 2.04% |
| `fail` | 4,644 | 194,294 | 44.16% |
| `out_of_scope` (<24,000 Btu/h) | 3,866 | 151,496 | 34.43% |
| `unknown` (a needed rating is absent) | 5,963 | 85,202 | 19.37% |

**The qualifying four:**

| AHRI | Brand / model | Band | c47 | COP@5 °F / thr | Cap. ratio | HSPF2 IV | Refrigerant (GWP) | Appear. |
|---|---|---|---:|---|---:|---:|---|---:|
| 217120762 | GREE GUD60W2/NHE-D(U) | >48k | 54,000 | 2.10 / 2.1 | 1.0000 | 10.50 | R-32 (675) | 4 |
| 214568857 | GREE GUD60W2/NHE-D(U) | >48k | 54,000 | 2.10 / 2.1 | 1.0000 | 10.50 | R-32 (675) | 2 |
| 215213332 | GREE FXU60HP230V1R32AO | >48k | 54,000 | 2.10 / 2.1 | 1.0000 | 10.50 | R-32 (675) | 1 |
| 216776011 | LENNOX SL22KLV-036-230A** | 24–36k | 32,600 | 2.42 / 2.4 | 1.0184 | 10.50 | R-454B (466) | 1 |

All four are Active, continuously variable, ENERGY STAR Most Efficient **and**
ENERGY STAR Cold Climate, and none carries an implausible rating.

### What the result actually means

**1. The qualifying set is knife-edge, not merely small.** Three of the four
report COP 2.10 against a 2.1 threshold and capacity ratio 1.0000 against 100%.
That is design-to-spec, not coincidence — and it means a routine certificate
amendment of 0.01 would drop them out. Any page showing this number must show
that it is fragile; a bare "4 models" implies a stability the data does not
have. (Bucket assignment is already known to be scrape-date dependent —
TIER_SPEC.md §6.4.)

**2. COP is the binding constraint, not capacity ratio.** Among units failing
exactly one gate: COP @ 5 °F blocks the most volume (203 models, 5,075
appearances), HSPF2 the most models (387), capacity ratio only 80 models.
Separately, **342 models — 5.3% of the screened base — already hold ≥100%
capacity at 5 °F** but pair it with a COP far below 2.4. Holding capacity in the
cold is achievable and increasingly common; holding it *efficiently* is what is
rare. That is the Challenge's design intent visible in Canadian install data.

**3. Refrigerant is an independent gate that removes almost everything.** The
base is **59.6% R-410A (GWP 2,088)** and only **2.6% at GWP ≤ 750**. GWP blocks
just one `near` unit — but that unit is **Mitsubishi MXZ-3C30NAHZ4 with 693
appearances**, by far the largest single unit anywhere near the bar, failing on
refrigerant alone with a capacity ratio of exactly 1.0000. Its R-454B successor
generation would plausibly pass outright.

**4. `out_of_scope` is a statement about the Challenge, not the equipment.**
Table II-3's smallest row starts at 24,000 Btu/h. The 34.4% of the base below
it is not failing anything — the Challenge deliberately does not address that
size class. Never render `out_of_scope` in the same visual channel as `fail`.

**5. The finding is the point, not the selection.** No qualifying unit is a
representative of any of the 36 tier cells (TIER_SPEC.md §4) — the two GREE 54k
units land in `>2.0 × ≥0.80 × ≥42k`, worth 0.1% of the base, and the LENNOX in
`>2.0 × ≥0.80 × 18–30k`. The screen changes no curve and no tier. Its value is
the statement that **essentially none of what Canadians have actually installed
meets the Challenge bar** — which is expected, since Challenge products reached
market in 2024–25 and our selection frame is historical audit records.

### Data-honesty notes

- **Nothing is dropped.** Implausible ratings (COP > 3.0, capacity ratio > 1.30
  — TIER_SPEC.md §6.2) are flagged in `implausible_rating` and still written. A
  screen that silently discarded them would hide the units most likely to pass
  on bad data. None of the four qualifying units is flagged.
- **Unknown never resolves to pass.** A missing rating yields `unknown` for that
  criterion and an `unknown` verdict overall. ENERGY STAR joins only ~62% of
  appearances, so most of the base cannot be GWP-tested at all — that is the
  bulk of the 19.37% `unknown` row.
- **Five designations, five different things.** ENERGY STAR Cold Climate,
  ENERGY STAR Most Efficient, NEEP ccASHP, AHRI's `cold_climate` flag and this
  DOE screen are five distinct labels. If a page shows more than one, it needs
  an explicit "these are not the same thing" line or the simple and advanced
  methodology sections will contradict each other.

### Reproducing

```bash
python HeatPump/pipeline/screen_cchp.py
```

Reads `data/interim/hp_units_joined.csv`, `energystar_by_ahri.csv`,
`nrcan_spl.csv` and `hp_buckets.csv`. **Note the reproducibility gap:**
`hp_units_joined.csv` has no producer script in the repo (see ROADMAP.md,
Queued), so this screen currently depends on a file that cannot be regenerated.

---

## Design-heat-load & selection rework — decisions taken 2026-07-28

Four decisions taken after discussion with a colleague. **Implemented
2026-07-29** in `heatpump.html` / `HeatPump/app/engine.js` (mirrored). They are
recorded here so the reasoning survives.

### 1. The ERS heat loss was right all along — F280 excludes gains

`EGHDESHTLOSS` is a **CSA F280 design heat loss**, and F280 deliberately takes
**no credit for solar or internal gains** when sizing. Our long-running worry —
recorded above in "Balance-point calibration" and again under "NRCan-published
archetypes", that the fitted `T_balance` was a residual absorbing solar gains,
night setback and missing supplementary heat, and that we therefore undersize by
~23 % against HOT2000's standard operating conditions — **was the wrong frame for
the sizing question.** Gains belong in the *annual energy* calculation, not in
the *design load*. The ERS design heat loss needs no repair for sizing purposes.

This does **not** retire the gains question for the energy simulation, where
gains genuinely do reduce delivered heat; see
[../docs/ENERGUIDE_QUESTIONS.md](../docs/ENERGUIDE_QUESTIONS.md), which still
wants the four monthly HOT2000 fields.

### 2. Stop sizing on archetypes — put design heat load in the user's hands

Archetypes were only ever a device for getting to a design load, and most of
them carry large heat losses, so the archetype choice was silently driving the
sizing answer. Replace with:

- a **dropdown or slider for design heat load** (kW), set directly by the user;
- a **distribution chart of design heat loss for the selected location**, from
  the ERS data, so a user can see where their number sits in the local stock
  rather than picking a label and inheriting its load.

This makes the single most consequential input explicit and adjustable instead
of implicit in an archetype name — and `city_design_temps.json` (84 cities,
1,020,246 homes, every home's `EGHDESHTLOSS` divided by the design temperature
it was actually computed at) is already the right input for the distribution.

### 3. NRCan report and archetypes: parked

`build_archetypes_nrcan.py`, `archetypes_nrcan.json` and the
"NRCan-published archetypes" section above are **kept as reference and not used
for the methodology**. The regression recovering UA and `T_balance` from Table 1
against NBC design temperatures stands as documented work, and the finding that
Table 1 is a design-condition load rather than a TMY peak is still worth having.
But decision 2 removes the need for a published archetype set, and its known
limitations (4 houses not a population, no floor areas, townhouse archetype
gone, TMY for 11 of 16 cities) no longer have to be lived with.

The ROADMAP's "wire `heatpump.html` onto `archetypes_nrcan.json`" step is
therefore **cancelled, not outstanding.** That wiring had actually been written
as uncommitted working-tree changes (page fetching `archetypes_nrcan.json`, city
list cut to NRCan's 11, archetypes A–D); it was **never committed or deployed**,
and was **reverted on 2026-07-28**. The live tool keeps running the ERS
`archetypes.json` and 14 cities until the rebuild lands, so nothing published
claims the parked method.

### 4. Heat-pump selection: two dropdowns, tier and capacity

The user picks a **performance tier** and a **nominal capacity** separately,
rather than the tool auto-sizing from an archetype. This makes the sizing
decision visible and lets a user test an over- or under-sized unit against their
own design load — which the sizing sweep (see "Sizing sensitivity") already
showed is where the interesting behaviour lives.

Consequence for the curve library: the **36-cell candidate table
(`cell_candidates.csv`) is an overcomplication** and is superseded by a
**3 tiers × 3–4 capacities = 9–12 cell** grid, i.e. 9–12 datasheets to pull and
defend rather than 36. Selection of those cells is being done by eye against the
real installed distribution — see the next section.

### What this blocked on — now resolved (2026-07-29)

- `buildOpts()` now takes `state.designLoad` (kW) and `state.balancePoint` (°C)
  as direct user inputs; `UA_W_per_K` is derived as
  `designLoad_kW * 1000 / (balancePoint - T_design_city)`, with
  `T_design_city` read from `city_design_temps.json`.
- `autoSize()` and the "which is my home?" floor-area helper are removed. A
  lightweight reference display (4 archetype-vintage medians for the selected
  city, from `archetypes.json`) is shown beside the design-load slider for
  calibration only — it does not drive the slider. This is deliberately the
  4-point version, not a full ERS population histogram; a fuller distribution
  remains a possible future addition.
- The tier/capacity dropdowns (`in-tier`, `in-band`) pin exactly one of the 9
  real cell curves from `hp_cell_curves.json` (see "Part 1" below) — no
  scaling, no interpolation.
- The two known engine bugs are fixed in both `engine.js` and the inlined copy:
  propane backup now defaults to 90% AFUE (previously fell through to 100%);
  the upstream-methane leak adder is restricted to `fuel/backup.type ===
  "gas"` (previously misapplied natural-gas density/energy constants to
  propane too). Propane gets no leak adder — no defensible propane
  upstream-loss constant exists yet, stated as a gap rather than reusing
  gas's number.
- Backup control strategy is now **derived from the backup type**, not a
  separate manual dropdown: electric resistance always tops up any capacity
  shortfall (`control.strategy = 'load-exceeds-capacity'`); gas/oil backup is
  a temperature switchover (`control.strategy = 'lockout'`) via a
  switch-over-temperature slider (repurposed from the old lock-out slider),
  shown only when backup is gas or oil. `engine.js`'s existing hour-by-hour
  `simulate()` already implemented both dispatch modes correctly — it was not
  rewritten, only how the UI derives `control.strategy` changed.
- The sizing-sweep card (40–160% of design load) was kept, sweeping a
  *synthetic* scaling of the selected cell's own capacity curve — explicitly
  labelled a hypothetical resizing for sensitivity analysis, not a menu of
  purchasable sizes (real units come only in the 9 discrete tier × band
  cells). This was the least-disruptive option once the continuous
  nominal-capacity slider was removed.
- Propane was also added as a **baseline** heating-fuel option (`in-fuel`),
  since the engine already fully supports it and the addition was trivial;
  this was not explicitly required by the plan but is a natural completion of
  the propane bug fix.

---

## Tier-selection scatter (2026-07-28)

A visual aid for choosing the 9–12 cells of decision 4 above, built by
`pipeline/build_tier_scatter.py` → `data/interim/tier_scatter.html`
(self-contained, inline SVG, no CDN or build step, per the repo architecture
rule). It is a **selection aid, not a browser-facing deliverable** — it lives in
`data/interim/` and is not published.

| Channel | Quantity |
|---|---|
| Y | COP @ 5 °F (−15 °C), max compressor speed |
| X | Capacity maintenance = max cap @ 5 °F ÷ rated cap @ 47 °F |
| Bubble **area** | Appearances in the ERS retrofit data |
| Colour | Nominal size band from rated capacity @ 47 °F |

Input is `data/interim/hp_units_joined.csv` (one row per AHRI-certified unit),
with brand/model joined from `hp_buckets.csv` for the hover labels. **The
`hp_units_joined.csv` reproducibility gap applies here too** — it has no
producer script in the repo, so this scatter currently rests on a file that
cannot be regenerated. See the Phase 3c note above and ROADMAP.md.

### Gate — quantified, not silent

A unit is plotted only if it carries **all three** of capacity maintenance,
COP @ 5 °F and rated capacity @ 47 °F:

| | Units | ERS appearances |
|---|---|---|
| In `hp_units_joined.csv` | 15,148 | 439,975 |
| **Plotted** | **7,314** | **298,209 (67.8 %)** |

Missing-field counts driving the drop: capacity maintenance 7,390 · COP @ 5 °F
7,551 · rated capacity @ 47 °F 3,600 (overlapping). Nothing is imputed. The
gate is stated on the page itself, not only here. **A third of installed
appearances are invisible to this plot** — the selected cells are representative
of the units we have AHRI metrics for, not of the installed fleet outright.

23 units fall outside the plot window (CM 0.15–1.35, COP 0.5–3.5); they are
**clamped to the edge and drawn with a dashed outline**, not dropped.

### What the distribution shows

Appearance-weighted terciles are drawn as guide lines — **as a reference, not as
the proposed boundaries**. The COP lower tercile lands on **exactly 1.80**,
because COP @ 5 °F piles up hard against NEEP's own 1.75 inclusion floor. That
is the point of drawing them: it shows concretely why a naive quantile cut is a
bad way to place these tiers (the same degeneracy that made k-means incoherent
in Phase 3a), and why the cells are being chosen by eye instead.

Share of plotted appearances, 3 COP tiers × 4 capacity bands:

| COP @ 5 °F | <18k | 18–30k | 30–42k | ≥42k |
|---|---|---|---|---|
| low (< 1.80) | 1.4 % | 2.1 % | 1.0 % | 0.2 % |
| mid (1.80–1.91) | 9.4 % | 19.7 % | **26.3 %** | 3.3 % |
| high (≥ 1.91) | 8.7 % | 18.4 % | 8.2 % | 1.4 % |

Two readings that bear on cell selection: the installed fleet is concentrated in
the **mid-COP band** (1.80–1.91) — consistent with Phase 3a's finding that the
most-installed units lean baseline, not premium — and the **≥42k column carries
under 5 % of appearances**, so a fourth capacity band at the top end buys very
little. A 3 × 3 grid over <18k / 18–30k / 30–42k covers **93.2 %** of plotted
appearances.

---

## Real-homes balance-point fix (2026-08-12)

The "real homes" section's per-house **balance point** (`house_profiles_<city>.json`,
`balance_point_T0_C`, built by `pipeline/build_city_house_profiles.py` and its
single-FSA precursor `pipeline/check_balance_point_k1s.py`) was landing far
colder than expected — e.g. Toronto's "worst" home at **11.5 °C**, against
NRCan/CanmetENERGY's *Cold-Climate Air Source Heat Pumps* report giving a
Net-Zero-Ready home ≈ 10 °C and a 10 kW/−18 °C worst-case home ≈ 16 °C. User
flagged the discrepancy 2026-08-12.

### The bug

Both scripts solve for the balance point `T0` by matching a straight-line
no-gains load model's predicted annual energy to the home's own observed
delivered energy:

```
slope (UA, kW/C) = Pre_HeatLoss / (ANCHOR - T_design)
predicted annual kWh = slope * DDH(T0)         DDH(T0) = Σ_hours max(T0 - T_hour, 0)
solve: predicted annual kWh = Pre_HeatDelivered   for T0
```

The bug was `ANCHOR = T0` — using the *unknown being solved for* as the
temperature the design heat loss is anchored at. But per "UA from design heat
loss — indoor/outdoor design temperature" above, `Pre_HeatLoss` (`EGHDESHTLOSS`)
is HOT2000's design heat loss computed at its **fixed default indoor setpoint,
21 °C** — not at the balance point. Since a home's balance point sits *below*
21 °C by construction (gains offset some loss, so less than the full
21 °C-to-outdoor delta is needed before heating stops), anchoring UA on `T0`
instead of 21 °C always uses too small a denominator, inflating UA. To match
the same observed annual energy with an inflated UA, the solver is forced to
push `T0` down. The effect compounds for higher-loss ("worst") homes, which is
why the worst-house figures were the most visibly wrong.

This is a **regression** of a bug already caught once, upstream: the archetype-
level work earlier in this document (see "UA from design heat loss" and
"Finding: calibrated Tbalance (8–12 °C) is lower than the ~15–16 °C planning
assumption") already anchors UA on the fixed 21 °C setpoint. The per-house
sketch (`check_balance_point_k1s.py`, 2026-08-11) reintroduced the T0-anchored
version as a simplification, and `build_city_house_profiles.py` inherited it.

### The fix

`ANCHOR = 21.0` (`T_INDOOR`), fixed, in both scripts:

```
UA = Pre_HeatLoss / (21.0 - T_design)                 # fixed, one value per house
target_DDH = Pre_HeatDelivered / UA = (Pre_HeatDelivered / Pre_HeatLoss) * (21.0 - T_design)
solve: DDH(T0) = target_DDH                             for T0
```

Because `DDH(T0)` is monotonic increasing in `T0` by construction (raising the
balance point can only add non-negative terms to the degree-hour sum), this
also **removes a piece of complexity the old formula needed**: the old
`h(T0) = DDH(T0)/(T0-T_design)` had a spurious non-monotonic dip just above
`T_design` (documented in the pre-fix version of this script's docstring),
requiring a monotonic-branch restriction before solving. That dip was an
artifact of the wrong anchor, not a real feature of the physics — it is gone
under the fixed formula.

### Verification — 10 random Toronto homes, full arithmetic

Sampled with a fixed seed (`np.random.RandomState(42)` via
`DataFrame.sample(random_state=42)`), old vs. new method side by side
(`T_design` = −18.4 °C for Toronto):

| HOUSEID | Design loss (kW) | Delivered (kWh) | Old T0 (°C) | New T0 (°C) | Δ |
|---|---|---|---|---|---|
| 338489 | 29.87 | 49,791 | 11.19 | 14.34 | +3.15 |
| 1130112 | 16.58 | 24,333 | 9.30 | 12.88 | +3.58 |
| 1723665 | 21.31 | 33,358 | 10.22 | 13.60 | +3.38 |
| 5356194 | 17.81 | 23,543 | 7.91 | 11.75 | +3.84 |
| 942998 | 15.79 | 20,050 | 7.42 | 11.34 | +3.91 |
| 853324 | 12.26 | 17,637 | 9.02 | 12.66 | +3.64 |
| 1639276 | 13.69 | 18,869 | 8.45 | 12.20 | +3.75 |
| 1750640 | 13.87 | 20,506 | 9.40 | 12.96 | +3.56 |
| 979761 | 15.87 | 27,464 | 11.79 | 14.79 | +3.00 |
| 950292 | 11.44 | 16,830 | 9.33 | 12.90 | +3.58 |

Worked example, HOUSEID 5356194 (Single Detached, 340 m², built 1994):

- `Pre_HeatLoss` = 17.810 kW, `Pre_HeatEnergy` (consumed) = 25,180 kWh,
  `Pre_HeatSeasonalCOP` = 93.5 % → `Pre_HeatDelivered` = 25,180 × 0.935 =
  23,543 kWh.
- **Old:** target `h` = 23,543 / 17.810 = 1,321.92; solving
  `DDH(T0)/(T0-(-18.4)) = 1,321.92` on the monotonic branch → **T0 = 7.91 °C**;
  implied UA = 17.810/(7.91+18.4) = 0.677 kW/°C.
- **New:** UA = 17.810/(21.0+18.4) = 0.452 kW/°C (fixed); target DDH =
  23,543/0.452 = 52,084 degree-hours; solving `DDH(T0) = 52,084` →
  **T0 = 11.75 °C**.

Consistent **+3.0 to +3.9 °C** shift across all 10 homes — systematic, not
noise, matching the sign and rough magnitude the algebra above predicts.

### What the fix does and doesn't close

The fix closes roughly a third to a half of the gap to CanmetENERGY's ~16 °C
worst-house figure — it does not fully close it. The remainder is the
**already-documented** steady-state/occupant-behaviour gap from "Finding:
calibrated Tbalance (8–12 °C) is lower than the ~15–16 °C planning assumption"
above: even a correctly-anchored no-gains model run against ERS's steady-state,
no-solar, design-wind-speed `EGHDESHTLOSS` and a constant-setpoint TMY year
tends to run cold relative to a real home's average-weather behaviour (reduced
wind and some incidental solar outside the design-day extreme; real thermostat
setbacks cut realized annual heating hours below what a constant-setpoint TMY
simulation predicts). That gap is not resolved by this fix and is not
resolvable from ERS data alone — it is a genuine finding, not silently
absorbed, and is flagged the same way on the page (`heatpump.html`
"Real homes explorer — how the balance point is derived") and in
`check_balance_point_k1s.py`'s docstring.

### What changed on disk

- `pipeline/check_balance_point_k1s.py` — `T_INDOOR = 21.0` fixed anchor,
  docstring updated.
- `pipeline/build_city_house_profiles.py` — `T_INDOOR = 21.0` fixed anchor,
  monotonic-branch workaround removed (no longer needed), docstring and
  shipped JSON `meta.method` string updated.
- `data/processed/house_profiles_<city>.json` — regenerated for all 14
  cities (747,829 homes total; drop-rate percentages per city unchanged from
  before the fix — only `balance_point_T0_C` values shifted).
- `heatpump.html` — "Real homes explorer" advanced-methodology paragraph
  updated to state the fixed-21 °C anchor and note the 2026-08-12 fix.

Scope note: this fix is **local to the real-homes per-house explorer**. The
simulation engine's own `Tbalance` (used by `simulate()` for the archetype-
level What-if calculator) is a **separate calibration**, already anchored
correctly at the fixed 21 °C indoor setpoint per the Phase-4 archetype work
above — it was not affected by this bug and needed no change.

---

## In-page methodology section rebuilt (2026-08-12)

`heatpump.html`'s "Assumptions & methodology" accordion (`#method-details`)
was rewritten in full, in response to a direct ask: it had grown as a log of
sequential fixes (this same document's own pattern), which made it hard to
read as a single account of what the tool currently does. This document
(`METHODOLOGY.md`) keeps the chronological log — that's its job. The
in-page section does not; it is the reader-facing summary and needed a
different shape.

**What changed:**

- **Reordered to follow the page's own step sequence** — Weather → Heat
  load → Equipment → Energy purchased → Grid emissions → Emissions → Cost,
  then limitations and sources — replacing an order that had drifted from
  the page's actual Step 1–7 layout as sections were added over time.
- **All "previously X, now Y" / "corrected 2026-08-12" / "earlier version"
  narrative language removed.** The page states only what is currently
  true; the history lives here instead.
- **Short sentences, bullets and tables** in place of long paragraphs.
- **Every assumption paired with its source**, inline or in a table column.
- **Three analyses folded into their natural home in the step sequence**,
  rather than living in separate sections disconnected from the step they
  support:
  - The ERS per-house heat-load/balance-point derivation (field table:
    `EGHDESHTLOSS`/`EGHFURNACEAEC`/`EGHFURSEASEFF`) — into Step 2, Heat load.
  - The AHRI/ERS tier-selection sampling method (439,975 record appearances,
    3×3 COP/capacity-maintenance grid) — into Step 3, Equipment.
  - The methane leakage map — into Step 6, Emissions, as a sub-section of
    the upstream-methane term it backs (previously a separate top-level
    section unconnected to that term).

**What did not change:** the three `data-method` jump-link anchors info
buttons scroll to (`m-grid`, `m-lifecycle`, `m-methane-map`) are preserved
on the corresponding headings, so existing "?" info-tip links still resolve.
No calculation, constant, or formula changed — this was a presentation-only
rewrite of the same facts already covered elsewhere in this document.
