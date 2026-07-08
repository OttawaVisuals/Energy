# CEUD Explorer — Plan & Build Prompts

A user-friendly web interface for NRCan's **Comprehensive Energy Use Database (CEUD)**, sibling to `retrofits.html` (Retrofit Explorer).

Source: https://oee.nrcan.gc.ca/corporate/statistics/neud/dpa/menus/trends/comprehensive/trends_res_ca.cfm

---

## 1. The problem

CEUD is a data cube hidden behind ~50 static HTML tables **per sector**, repeated across:

- **5 sectors** — Residential, Commercial/Institutional, Industrial, Transportation, Agriculture
- **8 regions** — Canada, Atlantic, QC, ON, MB, SK, AB, BC+Territories
- **Years 2000–2023** (base year changed from 1990 to 2000 with the 2018 release)

Every table is just a different 2-D slice of the same dimensions: *year × energy source × end-use × building type × equipment type*, plus explanatory variables (households, floor space, heating degree-days, equipment stock).

**Design insight: users shouldn't navigate tables — they pick a slice and the page pivots the data. One interface replaces ~400 tables.**

## 2. The page: "Canada Energy Use Explorer" (`ceud.html`)

Same design language as Retrofit Explorer so the tools feel like siblings:
navy `#0B2545` / amber `#E8A124` / cream `#F7F4EE`, Fraunces + Inter fonts, white cards with soft shadows, sticky navy header, **Simple/Advanced mode toggle**. Copy the CSS variables and card/filter/header patterns directly from `retrofits.html`.

### Global controls (sticky header + filter bar)
- **Region** selector (Canada default; provinces in dropdown — like the retrofit page's province selector)
- **Sector** tabs: Residential | Commercial | Industrial | Transportation | Agriculture (v1: Residential only, others greyed with "coming soon")
- **Metric** toggle: Energy (PJ) | GHG (Mt CO₂e) | Intensity (GJ/household, GJ/m²) — intensity is the killer feature; the raw tables make you compute it yourself
- **Year range** slider (2000–2023)

### Sections
1. **Headline stats** — stat tiles: total energy, total GHG, % change since 2000, energy per household vs 2000. One auto-generated plain-language insight (e.g. "Ontario homes use 18% less energy per household than in 2000, but there are 32% more of them").
2. **Trends over time** (workhorse) — large stacked-area chart with a "stack by" switch: **energy source** (electricity, natural gas, oil, wood, propane) ⇄ **end-use** (space heating, water heating, appliances, lighting, cooling). Absolute vs 100%-share toggle. Replaces CEUD Tables 1–2 and most of 4–19.
3. **Where the energy goes** — treemap or two-level donut (end-use → energy source) for the selected year; scrubbing the year animates it.
4. **Compare regions** — small-multiples line charts (one mini-chart per province, shared y-axis) or ranked bars for the selected metric.
5. **Equipment & stock** (Advanced, residential) — heating system stock over time (heat pump share!), housing type mix, floor space per dwelling, appliance counts & unit energy consumption. Complements the retrofit and heat pump tools.

### Simple vs Advanced
- **Simple**: sections 1–3, plain-language captions.
- **Advanced**: adds region comparison, equipment stock, intensity decomposition, "view underlying data" table + CSV export per chart.
- Reuse the `body.mode-simple [data-mode="advanced"]{display:none}` pattern from `retrofits.html`.

## 3. Architecture

1. **Python ETL** (in `C:\Energy\Python\`): download NRCan's CEUD tables once, parse into one **tidy long-format dataset**, emit small pre-aggregated JSON files per sector-region into `C:\Energy\ceud_json\` (mirrors the `province_json/` pattern). Target ~50–150 KB per file.
2. **Single static HTML file** `C:\Energy\ceud.html`, zero backend, vanilla JS + inline SVG charts (same approach as `retrofits.html`), fetches JSON on demand.
3. **v1 scope: Residential sector, all regions.** Adding other sectors later is a pipeline task, not a redesign.

### Things to verify first (Phase 0)
- Exact download format: the CEUD site offers per-sector zips of Excel tables; there is also a CEUD dataset on **open.canada.ca** that may be cleaner. Prefer whichever parses most reliably.
- Suppressed/confidential cells ("X", "—") in provincial tables — decide handling (null + chart gap, footnote).
- Known quirk: some government endpoints need `curl -L` rather than WebFetch (see memory notes); NRCan OEE pages fetched fine via WebFetch.

---

## 4. Build prompts for Claude Code

Run these as **separate sessions/tasks in order**, from `C:\Energy`. Each prompt is self-contained.
Suggested models: **Sonnet** for Phases 0–1 (data plumbing), **Opus** for Phases 2–3 (design-heavy page build), either for 4–5.

### Phase 0 — Scout the data (Sonnet)

```text
Read C:\Energy\CEUD_PLAN.md first. Phase 0: investigate data sources for NRCan's
Comprehensive Energy Use Database (CEUD).

1. Check the CEUD site (https://oee.nrcan.gc.ca/corporate/statistics/neud/dpa/menus/trends/comprehensive_tables/list.cfm)
   for bulk downloads (zip of Excel tables per sector/region), and check
   open.canada.ca for a "Comprehensive Energy Use Database" open-data version
   (CSV/Excel). If WebFetch is blocked for a domain, use curl -L instead.
2. Download ONE sample: residential sector, Canada, latest year available.
3. Inspect its structure: sheet/table layout, header rows, dimensions covered
   (year, energy source, end-use, building type, equipment stock, explanatory
   variables), units, and how suppressed/missing cells are marked.
4. Write your findings to C:\Energy\Python\ceud_source_notes.md: chosen source,
   exact URLs/URL pattern for all regions, parsing gotchas, and a proposed tidy
   long-format schema for the JSON output.
Do not build the full pipeline yet.
```

### Phase 1 — ETL pipeline (Sonnet)

```text
Read C:\Energy\CEUD_PLAN.md and C:\Energy\Python\ceud_source_notes.md first.
Phase 1: build the CEUD ETL pipeline.

1. Write C:\Energy\Python\ceud_etl.py that downloads (and caches locally, so
   reruns don't re-download) the CEUD residential-sector tables for ALL regions
   (Canada, Atlantic, QC, ON, MB, SK, AB, BC+Territories), years 2000–latest.
2. Parse into tidy long format and emit JSON to C:\Energy\ceud_json\:
   - res_<region>.json — records: {year, energy_source, end_use, building_type,
     energy_PJ, ghg_Mt} plus a separate block for explanatory variables
     {year, variable, segment, value, unit} (households, floor space, heating
     system stock, appliance stock, heating degree-days).
   - meta.json — regions, year range, dimension values, units, source URL,
     retrieval date.
   Suppressed cells become null, never 0. Keep each file under ~200 KB
   (round to 3 significant digits).
3. Add sanity checks: sum of provinces ≈ Canada total (warn if >2% off),
   sum of end-uses ≈ sector total, no negative values. Print a validation report.
4. Document how to rerun it at the top of the script.
Style/layout of existing scripts in C:\Energy\Python\ is the reference.
```

### Phase 2 — Page skeleton + core charts (Opus)

```text
Read C:\Energy\CEUD_PLAN.md first. Phase 2: build C:\Energy\ceud.html — the
"Canada Energy Use Explorer" for the residential sector, using the JSON in
C:\Energy\ceud_json\ (see meta.json for shape).

Requirements:
- Single self-contained HTML file, vanilla JS, inline SVG charts, no build step
  and no chart libraries — exactly like C:\Energy\retrofits.html. Copy its design
  system: CSS variables (navy/amber/cream), Fraunces + Inter, card grid, sticky
  navy header, filter bar, Simple/Advanced mode toggle pattern.
- Global controls: region selector (header), sector tabs (Residential active,
  others disabled "coming soon"), metric toggle (Energy PJ | GHG Mt |
  Intensity GJ/household), year-range slider (2000–latest).
- Section 1: headline stat tiles + one auto-generated plain-language insight
  sentence comparing latest year vs 2000.
- Section 2: large stacked-area chart, "stack by" switch between energy source
  and end-use, absolute vs 100%-share toggle, hover tooltip with values.
- Section 3: breakdown for the selected year (treemap or two-level donut:
  end-use → energy source) that updates when the year slider moves.
- All charts re-render on any control change; null (suppressed) values render
  as gaps, never zero. Test by opening the page with a local static server and
  verifying charts render for Canada AND at least two provinces.
```

### Phase 3 — Advanced mode: regions, equipment, data export (Opus)

```text
Read C:\Energy\CEUD_PLAN.md first. Phase 3: extend C:\Energy\ceud.html
(built in Phase 2) with the Advanced-mode sections.

1. Compare regions: small-multiples line charts (one per region, shared y-axis)
   for the currently selected metric, plus a ranked bar chart for the selected
   year. Loads other regions' JSON lazily and caches them.
2. Equipment & stock: heating system stock over time (stacked area — highlight
   heat pump share), housing type mix, average floor space per dwelling,
   appliance stock/unit-energy trends. Use the explanatory-variables block in
   the JSON.
3. Intensity view: energy per household and per m² trends, with a caption
   separating activity growth (more/larger homes) from efficiency gains.
4. Per-chart "view data" expander showing the underlying table with a CSV
   download button (generate CSV client-side).
5. All of the above hidden in Simple mode via the existing
   [data-mode="advanced"] pattern. Verify Simple mode still shows only
   sections 1–3 and nothing is broken on mobile width (375px).
```

### Phase 4 — More sectors (Sonnet or Opus)

```text
Read C:\Energy\CEUD_PLAN.md first. Phase 4: add the remaining CEUD sectors.

1. Extend C:\Energy\Python\ceud_etl.py to also parse Commercial/Institutional,
   Transportation, Industrial, and Agriculture tables into
   C:\Energy\ceud_json\<sector>_<region>.json, reusing the same tidy schema
   (dimension names differ per sector — e.g. transportation has vehicle types
   instead of building types; put sector-specific dimensions in meta.json).
2. In ceud.html, enable the sector tabs: switching sector swaps the dataset,
   relabels dimensions from meta.json, and hides sections that don't apply
   (e.g. equipment stock is residential-only for now).
3. Re-run the Phase 1 validation checks for every sector and fix anything
   that fails.
```

### Phase 5 — Polish & QA (either)

```text
Read C:\Energy\CEUD_PLAN.md first. Phase 5: polish and QA C:\Energy\ceud.html.

1. Cross-check at least 10 random values in the UI against the live CEUD
   tables on oee.nrcan.gc.ca (mix of regions, years, end-uses). Fix mismatches.
2. Performance: page usable in <2s on first load (lazy-load non-default
   regions/sectors), no layout shift when JSON arrives.
3. Accessibility & mobile: keyboard-reachable controls, readable at 375px,
   charts have text alternatives (the "view data" tables count).
4. Add a footer with data source, database version/year, retrieval date
   (from meta.json), and a link back to the CEUD site; note that GHG for
   Table-3-style regional views excludes electricity-related emissions if
   that caveat applies to the data used.
5. Add a link between retrofits.html and ceud.html headers so the tools
   cross-reference each other.
```

---

## 5. Decisions already made (don't re-litigate in later sessions)

- Static site, no backend, no frameworks, no chart libraries — match `retrofits.html`.
- v1 = Residential sector, all regions; other sectors are Phase 4.
- Intensity metrics (per-household, per-m²) are a first-class toggle, not an afterthought.
- Suppressed data = `null` (chart gap), never zero.
- JSON pre-aggregated per sector-region, `ceud_json/` folder, mirroring `province_json/`.
