# Retrofit Explorer — Text Inventory

A single reference of **every piece of text the page displays**, where it appears, and **under which condition** it appears. The goal is to make wording consistent: the same concept should read the same way everywhere.

Source: [`retrofits.html`](retrofits.html). All text below lives in that one file — either as static HTML or as strings inside the `<script>` block. Values pulled from the external JSON files (province/FSA/census/lookup data) are shown as `{placeholders}`.

---

## How the page is conditioned

Almost every variation comes from one of four switches. Keep these in mind when reading each row.

| Switch | Values | Driven by | Notes |
|---|---|---|---|
| **View mode** | Simple · Advanced | `body.mode-simple` / `body.mode-advanced` (toggle in header) | Advanced-only sections carry `data-mode="advanced"` and are CSS-hidden in Simple. Captions swap via `.cap-simple` / `.cap-advanced`. |
| **Data scope** | All of Canada (`CA`) · Province-wide · FSA-level | `#province-sel` + `#fsa-sel` | `MODE` = `'province'` or `'fsa'`. Some cards exist only in FSA mode. |
| **Data state** | loading · empty/no-data · error · normal | fetch lifecycle | Each has its own message string. |
| **Value sign** | positive (saved) · negative (increased) | per-home or per-slice value | Changes wording AND colour (green vs red). |

Cross-cutting wording conventions currently in use (candidates to standardize):
- **Saving shown as a reduction:** `−{n}` (minus glyph U+2212) for a drop, `+{n}` for an increase. Used in EUI/GHG KPIs and fuel "Savings" bar.
- **Percent change in table:** `+{n}%` / `{n}%` via `fmtPct()`.
- **"matched homes"** vs **"retrofits"** vs **"audits"** vs **"dwellings"** — four different nouns for counts; see the inconsistencies list at the end.
- **Median qualifier:** "median home", "median energy saved", etc.

---

## 1. Header (always visible)

| Text | Element / source | Condition |
|---|---|---|
| `retrofit` + province short code | `.logo` / `#logo-province` | `#logo-province` starts as `Canada`; `load()` sets it to the province short code (`CA`, `AB`, …). |
| `Simple` / `Advanced` | `.mode-btn` buttons | Always. Active button styled; `setViewMode()` toggles. |
| Province dropdown options | `#province-sel` | `All of Canada` (selected), `Select province…`, then the 10 provinces (Alberta … Saskatchewan). |
| `EnerGuide data` | `.header-badge` `#header-badge` | Initial. Then overwritten per scope (next rows). Hidden under 600px. |
| `EnerGuide data · {province} · loading…` | `#header-badge` | While `load()` is fetching. |
| `EnerGuide data · {province} · {n} audits` | `#header-badge` | Province/Canada view loaded. |
| `EnerGuide data · {province} · {FSA} · {n} audits` | `#header-badge` | FSA view loaded. |

---

## 2. Hero (always visible)

| Text | Element | Condition |
|---|---|---|
| `Select a province above to begin` | `.hero-eyebrow` `#hero-eyebrow` | Initial only. |
| `{province} · Home energy retrofits` | `#hero-eyebrow` | After `load()`. |
| `What did homes like yours do — and did it work?` ("homes like yours" italic/amber) | `.hero h1` | Always (static). |
| `Real audit data from Canadian homes. Select your province, then pick your FSA to find retrofits comparable to yours and see actual energy savings — or browse province-wide trends by house type.` | `.hero-sub` | Always (static). |

### 2a. Filter bar

| Text | Element | Condition |
|---|---|---|
| `Your FSA` (label) | `#fsa-sel` group | Always. |
| `All areas (province-wide)` | `#fsa-sel` default option | Province with FSA data. |
| `{FSA} ({n} homes)` | `#fsa-sel` options | Per FSA from `_index.json`. |
| `Not available for All of Canada` | `#fsa-sel` | Scope = CA (dropdown disabled). |
| `House type` (label) / `All types` | `#type-sel` | Always; options per scope. |
| `Heating fuel` (label) / `All fuels` | `#fuel-sel` group | **FSA mode only** (`display:none` otherwise). |
| `Retrofit depth` (label) | `#depth-sel` group | **FSA mode only**. Options: `Any depth`, `Deep — over 50% savings`, `Medium — 10 to 50%`, `Shallow — under 10%`. |
| `Reset` | `.filter-reset` | Always. |
| `{n} retrofits match` (`{n}` = `—`, `…`, or count) | `.filter-count` / `#result-count` | `—` initial, `…` while loading, then count. |

---

## 3. FSA map card — "Find your area"

Whole card (`#fsa-map-card`) shown only when a province with a boundary file is selected; hidden for All-of-Canada and provinces without geometry.

| Text | Element / source | Condition |
|---|---|---|
| `Find your area` | `.card-title` | Always when card shown. |
| `Click an FSA to select it. Colour = {meaning}.` | `.note` / `#map-color-meaning` | `{meaning}` = `audits collected` (default/sequential scale) **or** `median energy saving` (when FSAs have `median_saving_pct`). |
| `Reset view` | `#map-reset-btn` | Visible only when zoomed/panned in. |
| Legend (audit scale): `Fewer audits` / `More audits` | `#map-legend` | When colouring by audit count. |
| Legend (savings scale): `{lo}% (increase)` / `0%` / `{hi}%+ saved` | `#map-legend` | When colouring by median saving. |
| `© OpenStreetMap contributors` | `.map-attribution` | Always (static). |
| `Loading map…` | `#fsa-map-svg` | While geometry fetches. |
| `Map not available for this province` | `#fsa-map-svg` | Geometry fetch failed. |
| **Tooltip** `{FSA}` + `{population} population` + `{n} audits` + `{p}% median saving` | `#map-tip` (`onFsaMapHover`) | Hover over an FSA with data; population/saving lines only if present. |
| **Tooltip** `{FSA}` + `No audit data` | `#map-tip` | Hover over an FSA without audit data. |
| `Zoom in` / `Zoom out` (aria-labels) | zoom buttons | Always. |

---

## 4. Section: "Did the retrofits work?"

Heading (`.section-head`, always visible):
- **H2:** `Did the retrofits work?`
- **Sub:** `The bottom-line outcome across every matched home in this view.`

### 4a. Top stat cards (`.stats-grid`, always visible)

Each card has a fixed **label** + dynamic **value** + dynamic **sub**. Values come from `render()` (FSA) or `renderProvince()` (province); both produce identical wording.

| Label (static) | Value | Sub | Condition |
|---|---|---|---|
| `Median energy saving` | `{n}%` or `—` | `loading…` → `median energy saved` / `median energy increased` | Sub depends on sign of median; empty if no data. |
| `Median EUI saving` | `{n}` or `—` | `kWh/m² · median home` (static) | — |
| `Median GHG saving` | `{n}` or `—` | `tCO2e/yr · median home` (static) | — |
| `Deep retrofits` | `{n}` | `{p}% of matched homes` | Sub empty if n=0. |
| `Heat pumps added` | `{n}` | `{p}% of retrofits` | Sub empty if n=0. |
| `Fuel switches` | `{n}` | `changed heating fuel` (static; sub `{p}% of matched homes` computed but the static HTML sub reads "changed heating fuel") | ⚠ see inconsistencies. |
| `Solar PV added` | `{n}` | `{p}% of matched homes` | Sub empty if n=0. |

> Note: the `Fuel switches` sub is set to `{p}% of matched homes` by `render()`/`renderProvince()`, overwriting the static `changed heating fuel`. Other "changed heating fuel" style copy does not appear. Worth confirming intended wording.

### 4b. Energy saving distribution card (always visible)

| Text | Source | Condition |
|---|---|---|
| `Energy saving distribution — 1% increments` | `.card-title` | Always. |
| **Caption (Simple):** `Most homes save energy; a few use more, often after switching to a heat pump.` | `.cap-simple` | Simple mode. |
| **Caption (Advanced):** `Negative values mean total energy use increased — often due to fuel switching where electricity rises but total emissions fall.` | `.cap-advanced` | Advanced mode. |
| Chart tooltip: `{k}% saving` / `{n} homes` | `renderHist` / `renderProvinceHist` | Hover. |
| Axis titles: `Energy saving %` (x), `Homes` (y) | chart | Always. |

---

## 5. Section: "Energy & emissions — before vs after"

Heading (always visible):
- **H2:** `Energy & emissions — before vs after`
- **Sub:** `How much each home used and emitted before and after the work, and how the fuel mix shifted.`

### 5a. EUI card (always visible)

| Text | Source | Condition |
|---|---|---|
| `Energy use intensity (EUI) — kWh per m²` | `.card-title` | Always. |
| KPI: `{pre}` `Pre-retrofit median / kWh/m²` → `{post}` `Post-retrofit median / kWh/m²` | `renderEUI` / `renderProvinceEUI` | Always; values `—` if missing. |
| KPI saving block: `{−n or +n}` + `kWh/m² · median home` (FSA) **or** `kWh/m² saved` (province) | same | ⚠ Two different sub-labels for the same number across modes. Shown only when a saving exists. |
| **Caption (Simple):** `Energy use per square metre, before and after — lower is more efficient.` | `.cap-simple` | Simple. |
| **Caption (Advanced):** `EUI = total energy ÷ floor area. A lower EUI means a more efficient home. Pre- and post-retrofit distributions are shown as lines; the amber bars show, for the homes that improved, how much their EUI dropped by. Outliers above 500 kWh/m² clipped for scale.` | `.cap-advanced` | Advanced. |

### 5b. EUI slopegraph "Every home, pre → post EUI" — `#slopegraph-card`

Advanced-only **and** FSA-only (`toggleSlopegraphCard`).

| Text | Source | Condition |
|---|---|---|
| `Every home, pre → post EUI` | `.card-title` | Shown. |
| Caption: `Each line is one matched home: left point = pre-retrofit EUI, right point = post-retrofit EUI. Colour = number of retrofit measures done (see legend) — darker lines did more, so a darker band ending lower shows whether doing more measures tracks with bigger drops. Lines are drawn at low opacity so darker bands show where homes cluster. Outliers above 500 kWh/m² clipped for scale, same as the chart above.` | `.note` | Shown. |
| Canvas headers: `Pre-retrofit` / `Post-retrofit`; axis `kWh/m²` | `paintSlopegraph` | Drawn. |
| Legend: `0`, `1`, … `{max}+` | `#slope-legend` | Per measure count. |
| `No data for this selection` | `paintSlopegraph` | No pairs. |

### 5c. GHG card (always visible)

| Text | Source | Condition |
|---|---|---|
| `GHG emissions — tCO2e per year` | `.card-title` | Always. |
| KPI: `{pre}` `Pre-retrofit median / tCO2e/yr` → `{post}` `Post-retrofit median / tCO2e/yr` | `renderGHG` / `renderProvinceGHG` | Always. |
| KPI saving: `{−n/+n}` + `tCO2e/yr · median home` (FSA) **or** `tCO2e/yr saved` (province) | same | ⚠ Two sub-labels again. |
| **Caption (Simple):** `Greenhouse gas emissions from home energy use, before and after.` | `.cap-simple` | Simple. |
| **Caption (Advanced):** `Modelled annual greenhouse gas emissions from home energy use. Fuel switching to electricity can lower GHG even when total energy use rises, depending on grid mix. Pre/post shown as filled areas; amber bars show the reduction distribution.` | `.cap-advanced` | Advanced. |

### 5d. Heat loss card (always visible)

| Text | Source | Condition |
|---|---|---|
| `Heat loss — pre & post (GJ/yr)` | `.card-title` | Always. |
| **Caption (Simple):** `How much heat the home loses, before and after — lower is better.` | `.cap-simple` | Simple. |
| **Caption (Advanced):** `Total modelled heat loss through the building envelope and ventilation. Lower is better. Pre/post shown as filled areas; amber bars show the reduction distribution.` | `.cap-advanced` | Advanced. |

### 5e. Energy by fuel card (Advanced-only)

| Text | Source | Condition |
|---|---|---|
| `Energy by fuel — pre vs post · total kWh across all matched homes` | `.card-title` | Advanced. |
| Caption: `Each fuel gets a box sized to its larger of pre/post use; the fill level shows the actual pre or post value as a share of that box, so a half-filled box means usage dropped by half. The bottom row shows the resulting saving (green) or increase (red) per fuel. This chart uses total energy summed across all matched homes (not the median used elsewhere on this page), so each fuel's share adds up to the true total — and a fuel used by a minority of homes still shows up instead of medianing to zero. Hover any box for exact values.` | `.note` | Advanced. |
| Row labels: `Pre-retrofit`, `Post-retrofit`, `Savings` | `paintFuelBreakdown` | Always when drawn. |
| `Total saved: {n} kWh` / `Total increased: {n} kWh` | `paintFuelBreakdown` | Sign of total. |
| `No fuel data for this selection` | `paintFuelBreakdown` | No fuels. |
| Tooltip: `{fuel} — {Pre/Post-retrofit}` + `{n} kWh`; or `{fuel}` + `Saved/Increased: {n} kWh` | `onFuelBreakdownHover` | Hover. |

### 5f. Sankey card (Advanced-only)

| Text | Source | Condition |
|---|---|---|
| `Heating fuel flow — aggregate energy pre → post (GWh)` | `.card-title` | Advanced. |
| Caption: `Flow width = total energy (GWh) across all matched homes. Grey flows = same fuel, no switch. Coloured flows = fuel switch. Hover a flow for details.` | `.note` | Advanced. |
| Node labels: `{fuel} ({n} GWh)` | `drawNodes` | Drawn. |
| Flow tooltip: `{from} → {to} | Pre: {n} GWh | Post: {n} GWh | Change: {n} GWh` | `attachFlowTip` | Hover/focus. |

---

## 6. Section: "What was upgraded"

Heading (always visible):
- **H2:** `What was upgraded`
- **Sub:** `Which measures were carried out, and how far insulation and airtightness actually moved.`

### 6a. Measures card (always visible)

| Text | Source | Condition |
|---|---|---|
| `What measures were done` | `.card-title` | Always. |
| Measure rows `{label}` + `{p}%` | `renderMeasures` / `renderProvinceMeasures` | Labels from `MEASURES`: `Air sealing`, `Roof insulation`, `Foundation insulation`, `Wall insulation`, `Heat pump added`, `Heating system changed`, `Windows changed`, `Floor insulation`. |
| `No matches` | `renderMeasures` | n=0. |

### 6b. Measures by vintage — `#vintage-card`

Advanced-only **and** FSA-only.

| Text | Source | Condition |
|---|---|---|
| `Measures by vintage` | `.card-title` | Shown. |
| Caption: `For homes built in each decade, the share that got each measure. Vintage buckets with fewer than 20 matched homes are dropped to avoid noisy percentages.` | `.note` | Shown. |
| Tooltip: `Built {decade}s` / `{measure}: {p}% (n={total})` | `renderVintageMeasures` | Hover. |
| `Not enough homes per vintage to show this breakdown` | `drawEmptyCanvasMsg` | All buckets < 20 homes. |

### 6c. Insulation & air leakage card (always visible)

| Text | Source | Condition |
|---|---|---|
| `Insulation & air leakage — median pre → post` | `.card-title` | Always. |
| KPI items: `Roof insulation`, `Wall insulation`, `Foundation ins.`, `Air leakage`, plus `Fuel switching` | `renderKPI` / `renderProvinceKPI` | Always. |
| KPI value line: `{R}` → `{R}` with `R-value ({rsi} → {rsi} RSI)` (insulation) or unit `ACH50` (air) | same | Per measure. |
| KPI delta: `{+/-d} R ▲ improved` / `▼ declined` (or unit) | same | Sign + higher/lower-is-better. |
| Fuel switching KPI: `{p}%` + `of matched homes` | same | Always. |
| **Caption (Simple):** `Higher R-value and lower air leakage are both better.` | `.cap-simple` | Simple. |
| **Caption (Advanced):** `R-value = imperial thermal resistance (higher = better; RSI shown in brackets is the metric equivalent, R = RSI × 5.68). ACH50 = air changes per hour at 50 Pa (lower = better).` | `.cap-advanced` | Advanced. |
| Sub-chart titles: `Roof insulation`, `Wall insulation`, `Foundation insulation`, `Air leakage` | `.measure-chart-title` | Always. |

### 6d. Solar PV card (Advanced-only)

| Text | Source | Condition |
|---|---|---|
| `Solar PV adoption` | `.card-title` | Advanced. |
| KPI: `{p}%` `Pre-retrofit / with solar PV` → `{p}%` `Post-retrofit / with solar PV` + `{kw}` `median kW among adopters` | `renderSolar` / `renderProvinceSolar` | Advanced; median block only if adopters exist. |
| Caption: `Share of matched homes with solar PV recorded pre- and post-retrofit, and the median system size among adopters.` | `.note` | Advanced. |

---

## 7. Section: "The homes in this view" (Advanced-only)

Heading carries `data-mode="advanced"`:
- **H2:** `The homes in this view`
- **Sub:** `Who these retrofitted homes are — vintage, size, type — and how they sit within the wider neighbourhood.`

### 7a. Year built + Floor area (Advanced-only)

| Text | Source | Condition |
|---|---|---|
| `Year built` / `Floor area (m²)` | `.card-title` | Advanced. |
| Year legend: `Audited homes` (+ `All FSA dwellings (census)` when census overlay loads) | `renderYearHist` / `renderProvinceYearHist` | FSA: census line added if available. Province: legend is `Single detached`/`Attached` (split) or selected type. |
| Area legend: `Single detached` / `Attached` (or selected type) | `renderAreaHist` / province variant | — |
| Year tooltip: `{label}` / `{dataset}: {p}%` (FSA census) or `{label}s` / `{dataset}: {n} homes` (province) | charts | Hover. |
| Area tooltip: `{a}–{a+50} m²` / `{dataset}: {n} homes` | charts | Hover. |

### 7b. Building type + Storeys (Advanced-only)

| Text | Source | Condition |
|---|---|---|
| `Building type` / `Number of storeys` | `.card-title` | Advanced. |
| Type legend (FSA, with census): `Audited homes` / `All FSA dwellings (census)` | `renderTypeDonut` | When census `dwelling_type` available. |
| Type donut leader labels: `{type} – {p}%` | `donutLeaderLines` | No-census fallback / province. |
| Type bar tooltip: `{dataset}: {p}%`; donut tooltip: `{label}: {n} ({p}%)` | charts | Hover. |
| Storey labels (donut): `Split entry`, `2.5 storeys`, `3 storeys`, `2 storeys`, `1 storey`, `1.5 storeys`, `Split level`, `Unknown` | `renderStoreyDonut` `MAP` | Per value; `Unknown` if unmapped/missing. |
| Dwelling-type labels (census cross-walk): `Single-detached`, `Semi-detached`, `Row house`, `Duplex apt`, `Apt (<5 storeys)`, `Apt (5+ storeys)`, `Other attached`, `Movable` | `DWELLING_TYPE_LABELS` | Census comparison chart. |

### 7c. Neighbourhood housing stock — `#census-card`

Advanced-only **and** FSA-only (no Canada/province rollup).

| Text | Source | Condition |
|---|---|---|
| `Neighbourhood housing stock — 2021 Census` | `.card-title` | Shown. |
| `Tenure` / `Dwelling condition` | `.measure-chart-title` | Shown. |
| Coverage KPIs: `Total private dwellings` (`2021 Census`), `Audited homes (this FSA)` (`EnerGuide`), `Audit coverage` (`of all dwellings`) | `renderCensus` | Shown. |
| Tenure gauge: `{p}%` + `owner-occupied`; legend `Owner {p}%` / `Renter {p}%` | `renderCensus` | If tenure data present. |
| Condition gauge: `{p}%` + `need major repairs`; legend `Major repairs {p}%` / `Minor/none {p}%` | `renderCensus` | If condition data present. |
| Owner KPIs: `Owners with a mortgage`, `Spending 30%+ on shelter`, `In core housing need`, `Median dwelling value` (`$` value) | `renderCensus` | Values `—` if suppressed. |
| Caption: `Statistics Canada 2021 Census Profile, FSA level — describes all private dwellings in this FSA, not just the homes that got an EnerGuide audit. "Audit coverage" above compares the two — see also the Building type and Year built charts above, which overlay this same census data for direct comparison. Owner stats (mortgage/shelter-cost/core-housing-need/dwelling-value) are 25%-sample-data estimates and may be suppressed (—) for small FSAs.` | `.note` | Shown. |
| `Loading…` | `#census-coverage-kpis` | While fetching. |
| `No census data for this FSA` | same | FSA not in census file. |
| `Could not load census data` | same | Fetch error. |

---

## 8. Section: "Equipment detail" (Advanced-only)

Heading `data-mode="advanced"`:
- **H2:** `Equipment detail`
- **Sub:** `Raw heat-pump and window references recorded for the matched homes.`

### 8a. Heat pump AHRI + window codes (Advanced-only)

| Text | Source | Condition |
|---|---|---|
| `Common heat pump models (AHRI number)` | `.card-title` | Advanced. |
| AHRI rows: `{decoded name}` + `AHRI {code}` (or raw code) + `{count}` | `renderAhriWindowFsa` / `renderAhriWindowProvince` | Decoded if lookup loaded, else raw. |
| Caption: `Top 5 most common AHRI certification numbers among heat pumps in matched homes (pre- and post-retrofit combined). Numbers outside the top 5 are not shown individually to avoid singling out near-unique installations.` | `.note` | Advanced. |
| `Common window codes` | `.card-title` | Advanced. |
| `Pre-retrofit` / `Post-retrofit` | `.measure-chart-title` | Advanced. |
| Window rows: `{decoded desc}` + `Code {code}` (or raw) + `{count}` | same renderers | Decoded if lookup loaded. |
| Caption: `Top 5 window codes by frequency, decoded into glazing/coating/fill/spacer/frame using NRCan's published code tables.` | `.note` | Advanced. |
| `No data` | `barListHTML` | Empty list. |

### 8b. Most common window changes — `#window-changes-card`

Advanced-only **and** FSA-only.

| Text | Source | Condition |
|---|---|---|
| `Most common window changes` | `.card-title` | Shown. |
| Rows: `{attribute label}` + `Most often: {from} → {to}` + `{p}%` | `renderWindowChanges` | Attribute labels: `Glazing (panes/coats)`, `Coating/tint`, `Gas fill`, `Spacer`, `Window type`, `Frame material`. |
| Caption: `For homes with a decodable window code both before and after, the share where each attribute changed at all, ranked — top 5 of 6 tracked attributes. Glazing and coating are the two attributes that most directly drive a window's R-value, so they're worth watching specifically. "Most often" shows the single most common from → to change for that attribute. Codes outside NRCan's standard table (custom/user-defined windows) aren't included.` | `.note` | Shown. |
| `Loading…` | `#window-changes-list` | Components not loaded. |
| `No decodable window codes for this selection` | same | None decode. |

---

## 9. Section: "Individual retrofits" — `#sec-individual` / `#table-card`

Advanced-only **and** FSA-only (hidden in province mode via `render()`/`renderProvince()`).

| Text | Source | Condition |
|---|---|---|
| **H2:** `Individual retrofits` | `.section-head` | FSA + Advanced. |
| **Sub:** `Every matched home in this FSA, one row each — click to expand. (FSA view only.)` | | |
| `Individual retrofits — click a row for detail` | `.card-title` | — |
| Sort row: `Sort by` + `Energy saving` / `Year built` / `Floor area` | `.sort-row` | Always. |
| Table headers: `FSA`, `Type`, `Built`, `m²`, `EUI kWh/m²`, `Fuel`, `Saving`, `Depth` | `<thead>` | Always. |
| Saving cell: `{+/−p}%` (via `fmtPct`) | `renderTable` | Sign → green/red. |
| Depth badge: `Deep` / `Medium` / `Shallow` / `Increased` | `renderTable` | Per retrofit-depth flag; `Increased` if negative saving and no depth flag. |
| Fuel cell: `{pre}` (→ `{post}` if fuel switched); `?` if missing | `renderTable` | — |
| Footer: `Showing top {MAX} of {n} matching retrofits` **or** `{n} matching retrofits` | `#tbl-footer` | If results exceed 100. |
| `No matching retrofits` | `renderTable` | Empty. |

### 9a. Expanded row detail (`makeInlineSVG`)

| Text | Condition |
|---|---|
| `Energy use intensity (EUI), kWh/m²` (heading) | Always in detail. |
| `Envelope measures` (heading); bar labels `Roof R`, `Wall R`, `Foundation R`, `Air ACH50` | Always. |
| Legend: `Pre` / `Post` | Always. |
| Measure chips (`{measure label}`) or `No measures flagged` | Chips if any flag set. |
| `HVAC & energy` (heading); column headers `Measure`, `Pre-audit`, `Post-audit`, `Savings` | Always. |
| Rows: `Audit year` (`{n} yr apart`), `Heating fuel`, `Heating type`, `Heat pump` (`Changed` / `—`), `Energy`, `GHG`, `Heat loss`, `Solar PV` | Per row; `Changed`/`—` or numeric delta. |

---

## 10. Methodology (always visible, collapsed `<details>`)

Static long-form copy. Summary + 9 subsections.

| Element | Text (verbatim) |
|---|---|
| `summary` | `How this data was built — methodology` |
| intro | `This tool visualises real home-energy audits, but the numbers go through several steps before they reach the charts. Here is the whole journey in plain terms.` |
| `1 · Where the data comes from` | EnerGuide/ERS open dataset, 2004–2025, HOT2000. |
| `2 · Matching "before" and "after"` | Type D = before, type E = after; exactly one each, after dated later → one pre→post row. |
| `3 · Making sure it's really the same home` | Floor area ≤10% change; house type, storeys, units unchanged. |
| `4 · Putting everything in the same units` | Convert all fuels to kWh; GHG straight from audit (tCO₂e/yr) with grid mix. |
| `5 · Fields we calculate ourselves` | EUI, Energy saving %, Retrofit depth (Shallow ≤10%, Medium 10–50%, Deep ≥50%), Fuel switch. |
| `6 · What counts as an "upgrade"` | Insulation +>10%, air sealing −>10%, windows differ, heating differs, heat pump newly present. |
| `7 · Two views, two ways of counting` | FSA = live in-browser from raw rows; province = precomputed in Python by house type. |
| `8 · How the histograms are built` | Bucket widths: 20 kWh/m², 5 GJ/yr, 1% saving; improvement charts count only homes that improved. |
| `9 · Things to keep in mind` (caveats) | Modelled not metered; per-fuel medians don't sum; outliers clipped (>500 kWh/m²); pre-retrofit solar rarely recorded; no cost data. |

> ⚠ The methodology says heat-loss buckets are `5 GJ/yr`, but the code (`BINS.heatloss`) uses **2 GJ/yr**. See inconsistencies.

---

## 11. Footer (always visible)

| Text | Source | Condition |
|---|---|---|
| `Data: Natural Resources Canada EnerGuide · {scope} audits 2004–2025` | `footer` / `#footer-province` | `#footer-province` = `Canadian home energy audits` initially, then `{province} audits`. |
| `Values are modelled energy estimates, not metered consumption. Retrofit costs not available in source data.` | `footer` | Always. |

---

## 12. Generic / shared state messages

| Text | Source | Condition |
|---|---|---|
| `Could not load data` + `Could not fetch the FSA index for {province}.` | `load()` catch | FSA index fetch fails. |
| `Could not load data` + `Could not fetch data for FSA {FSA}.` | `loadFsaView` catch | FSA rows fetch fails. |
| `Could not load data` + `Could not fetch the province summary for {province}.` | `loadProvinceView` catch | Province summary fetch fails. |
| `No data` / `No matches` / `Loading…` | `barListHTML`, `renderMeasures`, list renderers | Empty/loading lists. |

---

## Appendix A — Wording inconsistencies to resolve

These are the concrete mismatches surfaced while inventorying. Standardizing these is likely the point of this exercise.

1. **EUI / GHG saving sub-label differs by scope.**
   - FSA mode: `kWh/m² · median home` / `tCO2e/yr · median home`
   - Province mode: `kWh/m² saved` / `tCO2e/yr saved`
   - The stat-card subs (section 4a) use a third form: `kWh/m² · median home`, `tCO2e/yr · median home`. Pick one phrasing.

2. **Count nouns are inconsistent.** The page variously says `matched homes`, `retrofits`, `audits`, `homes`, `dwellings` for related counts:
   - `{n} retrofits match` (filter), `% of matched homes` (deep/solar/fuel), `% of retrofits` (heat pumps), `{n} audits` (header/map), `{n} homes` (FSA dropdown / chart tooltips), `matching retrofits` (table footer). Decide a canonical term per concept (audited home vs retrofit vs dwelling).

3. **`Fuel switches` stat sub.** Static HTML reads `changed heating fuel`; JS overwrites it with `{p}% of matched homes`. Confirm intended copy.

4. **Heat-loss bucket width.** Methodology §8 says `5 GJ/yr`; code uses `2 GJ/yr` (`BINS.heatloss`). Fix one.

5. **Saving sign glyph.** Reductions use `−` (U+2212) in KPI/fuel blocks but `fmtPct` in the table uses a plain hyphen for negatives and `+` for positives. Align the minus glyph and +/− convention.

6. **"Foundation" label is abbreviated only in the KPI grid** (`Foundation ins.`) vs full `Foundation insulation` elsewhere. Minor.

7. **Heading punctuation / em-dash usage** is consistent (good) — em dashes throughout card titles. Keep as the house style.

---

## Appendix B — Fixed vocabulary (for reference when standardizing)

- **Measure labels** (`MEASURES`): Air sealing · Roof insulation · Foundation insulation · Wall insulation · Heat pump added · Heating system changed · Windows changed · Floor insulation.
- **Retrofit depth:** Deep (≥50%) · Medium (10–50%) · Shallow (≤10%) · Increased (negative).
- **Units shown:** `kWh/m²` (EUI), `tCO2e/yr` (GHG), `GJ/yr` (heat loss), `R-value` / `RSI` / `ACH50` (envelope), `kW` (solar), `GWh` (Sankey/fuel aggregate), `%` (savings/shares).
- **Pre/Post wording:** always `Pre-retrofit` / `Post-retrofit` (charts) or `Pre-audit` / `Post-audit` (table detail) — note this is two different pairings.
