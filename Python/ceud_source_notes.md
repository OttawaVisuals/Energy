# CEUD source notes (Phase 0)

## Chosen source

**NRCan OEE's per-table `.xls` download links**, not a bulk zip and not
open.canada.ca.

- The CEUD "Comprehensive Energy Use Database" landing page
  (`.../menus/trends/comprehensive_tables/list.cfm`) offers **no bulk
  zip/CSV download** — just links to per-sector/per-region HTML table pages.
- **open.canada.ca has no live CEUD dataset.** A CKAN search
  (`https://open.canada.ca/data/api/action/package_search?q=%22Comprehensive%20Energy%20Use%20Database%22`)
  returns exactly one hit: the old **"Energy Use Data Handbook Tables"**
  dataset (`id=de730ec2-282a-4797-b20d-733796a92f87`), last modified
  2018-04-04, `isopen: false`, format XLS/HTML, pointing back at
  `oee.nrcan.gc.ca/.../handbook/tables.cfm`. That's a static 2015-vintage
  handbook, not the annually-updated CEUD (currently through 2023). Not
  usable.
- Each individual table page on the OEE site (reached via
  `showTable.cfm?...`) has a **"Download" button linking directly to a real
  `.xls` file** containing the exact same data as the on-page HTML table,
  for *all years at once* (2000–latest in one file). This is the best
  source: structured, versioned by year in the URL path, one file per
  table per region.

## Exact URL patterns

### 1. Table index (per sector × region), to discover table numbers/titles
```
https://oee.nrcan.gc.ca/corporate/statistics/neud/dpa/menus/trends/comprehensive/trends_<sector>_<juris>.cfm
```
e.g. `trends_res_ca.cfm` (residential, Canada), `trends_res_pei.cfm` (residential, PEI — note the *page* is named `pei` but the jurisdiction **code** used everywhere else is `pe`, see table below).

### 2. HTML table view (what a user browsing the site sees)
```
https://oee.nrcan.gc.ca/corporate/statistics/neud/dpa/showTable.cfm?type=CP&sector=<sector>&juris=<juris>&year=<year>&rn=<table#>&page=0
```

### 3. Excel download (**use this one** — direct data file, all years in one sheet)
```
https://oee.nrcan.gc.ca/corporate/statistics/neud/dpa/data_e/downloads/comprehensive/Excel/<year>/<sector>_<juris>_e_<table#>.xls
```
- `<year>` = the CEUD release year folder, currently `2023` (= latest data year; the release itself covers 2000–2023 in one file, so this does **not** need to be looped per data-year, only per release).
- `<sector>` = `res` (residential; only sector needed for v1). Other sectors for Phase 4: `com` (commercial/institutional), `agg` (aggregated industries), `id` (disaggregated industries, Canada only), `tran` (transportation), `agr` (agriculture).
- `<juris>` = jurisdiction code (see table below).
- `<table#>` = 1..N, sector- and region-dependent (residential Canada goes up to at least 50; smaller regions/sectors have fewer tables — must discover per-region by scraping the index page, don't assume table count is constant).

Confirmed working example:
`https://oee.nrcan.gc.ca/corporate/statistics/neud/dpa/data_e/downloads/comprehensive/Excel/2023/res_ca_e_1.xls`

### Jurisdiction codes (residential sector; scraped from each region's index page)
| Region | juris code | index page slug |
|---|---|---|
| Canada | `ca` | `trends_res_ca` |
| Newfoundland and Labrador | `nl` | `trends_res_nf` |
| Prince Edward Island | `pe` | `trends_res_pei` |
| Nova Scotia | `ns` | `trends_res_ns` |
| New Brunswick | `nb` | `trends_res_nb` |
| Quebec | `qc` | `trends_res_qc` |
| Ontario | `on` | `trends_res_on` |
| Manitoba | `mb` | `trends_res_mb` |
| Saskatchewan | `sk` | `trends_res_sk` |
| Alberta | `ab` | `trends_res_ab` |
| British Columbia | `bc` | `trends_res_bc` |
| Territories (YT+NT+NU combined) | `tr` | `trends_res_tr` |

**Gotcha:** don't derive `juris` from the page slug (`nf` ≠ `nl`, `pei` ≠ `pe`). Always confirm by grepping `juris=` out of the actual index HTML — I hit two 404s by guessing `pei` before finding it's `pe`.

**Revised scope (per user request):** fetch all 11 individual provinces/territories above plus `ca` (national) — **12 regions total**. The plan's original 8-region grouping (`atl` and `bct` as pre-aggregated multi-province groups) is **dropped**; those two aggregate jurisdictions still exist on the site if ever needed again, but the ETL only needs the 11 atomic jurisdictions + `ca`, since any grouping (Atlantic, BC+Territories, or anything else) can be summed client-side from the atomic province data. Note NRCan does not offer a further split of Territories into Yukon/NWT/Nunavut — `tr` is the finest grain available for the North.

### Do all provinces have the same table detail? — Yes, exactly.
Checked all 11 individual jurisdictions (`nl, pe, ns, nb, qc, on, mb, sk, ab, bc, tr`, including comparing Nova Scotia against Alberta as the user asked): **every one has exactly 41 tables with identical titles, identical row layout, and identical row labels** (verified by diffing scraped title lists — zero differences across all 11). Spot-checked actual data rows (not just titles) for NS Table 9 and Territories Table 21 against the Table-1/Table-27 layout already documented above — same section-header structure, same label text, same column-year alignment. Real zeros (e.g. `Heat Pump: 0.0` in Territories in 2000, `Natural Gas: 0.0` throughout for provinces without gas distribution) are stored as `0.0`, not suppressed — consistent with the earlier PEI finding.

**However, provincial tables (41) differ systematically from the Canada/national table set (50)** — this is a structural difference between "Canada" and "a province", not a difference between provinces:
- Canada has **9 extra "by Region" tables** (comparing provinces against each other) that don't make sense for a single province and are absent there (e.g. CA Table 3, 4, 13, 16, 19, 41, 44, 47, 50).
- Canada **splits Space Heating GHG by System Type into two tables** — Table 11 "Including Electricity-Related Emissions" and Table 12 "Excluding" — whereas each province has **one combined table** (e.g. NS Table 9 "Space Heating GHG Emissions by System Type", header row reads "Excluding Electricity" only — provinces only report the excluding-electricity convention for this cut, not both).
- Canada has a **Unit Energy Consumption (UEC) table** for appliances (Table 38) that **no province has**.
- Provinces have **two tables Canada lacks**: "Gross Output Thermal Requirements per Household by Building Type and Vintage" and "...per Square Metre..." (NS Tables 32–33) — a modelled heating-demand series not broken out nationally.
- Net effect: table **numbers are not aligned between Canada and the provinces** (e.g. Table 27 = "Heating System Stock" for Canada, but Table 21 for every province) — **the ETL must map by table title, not by table number**, and must use a separate title→number lookup for `ca` vs. the 11 provinces (the 11 provinces can share one lookup, Canada needs its own).

## File structure (verified against downloaded samples)

Every table `.xls` is a legacy **BIFF `.xls`** (not `.xlsx`) — requires `xlrd` installed (`pip install xlrd`) alongside pandas; `pd.read_excel` picks it automatically once xlrd is present. `pd.ExcelFile(path).sheet_names` returns exactly **one sheet**, named `"Table <n>"`.

Layout (0-indexed rows via `header=None`):
- Rows 0–9: banner/title block — sector name (row 4), region name (row 6), table title (row 7). Skip.
- Row 10: year header row. Column 0 empty, column 1 empty, columns 2..N = years as floats (`2000.0 … 2023.0`, one file = full year range, no need to fetch per year).
- Row 11: blank spacer.
- Rows 12+: data rows. **Column 0 is always empty** (unused). **Column 1 holds the row label** (e.g. `"Total Energy Use (PJ)"`, `"Electricity"`, `"Heat Pump"`). Columns 2..N hold the numeric values aligned to the year header row.
- Section headers are their own label-only rows with all-NaN data cells, e.g. `"Energy Use by Energy Source (PJ)"`, `"Shares (%)"`, `"Activity"`, `"GHG Emissions by Energy Source (Mt of CO2e)"`. These act as sub-headings, not data — use them to tag the subsequent rows' unit/category until the next section header or blank row.
- Blank rows (all-NaN) separate sections — use as section boundaries when parsing.
- Trailing footnote rows at the bottom (as plain text in column 0, e.g. `"1) "Other" includes coal and propane."`) — skip, but worth capturing as glossary text in `meta.json` if convenient.

### Confirmed dimensions covered (Table 1, "Secondary Energy Use and GHG Emissions by Energy Source", residential/Canada)
- Total Energy Use (PJ)
- Energy Use by Energy Source (PJ): Electricity, Natural Gas, Heating Oil, Other¹, Wood (¹Other = coal + propane)
- Shares (%) of the above
- Activity: Total Floor Space (million m²), Total Households (thousands)
- Energy Intensity (GJ/m², GJ/household)
- Total GHG Emissions **Including** Electricity (Mt CO2e) + by-source breakdown + shares
- GHG Intensity (tonne/TJ)
- Total GHG Emissions **Excluding** Electricity (Mt CO2e) + GHG Intensity (tonne/TJ) — a second full GHG block; NRCan's convention is that most per-region/per-end-use GHG tables report **excluding** electricity-related emissions (electricity's GHG intensity varies hugely by province's grid, so they factor it out into a dedicated "Including Electricity" table like Table 1's Canada view, and a national grid-average adjustment elsewhere). **Preserve this distinction in the schema** — don't collapse to one `ghg_Mt` field without a flag for which convention applies, since Table titles literally say "Excluding Electricity-Related Emissions" for most region/end-use breakdowns.
- Heating Degree-Day Index, Cooling Degree-Day Index (normalized, ~1.0 = long-run normal — these are *indices*, not raw HDD/CDD values)

### Other tables sampled (residential, full title list confirmed for Canada, 50 tables total)
Full numbered list captured live from `trends_res_ca.cfm` — key ones relevant to the plan's schema:
- **Table 2**: by End-Use (Space Heating, Water Heating, Appliances, Lighting, Space Cooling — this is the "end-use" stack-by dimension for section 2 of the plan)
- **Table 3**: by Region, excluding electricity GHG
- Tables 4–19: end-use-specific breakdowns (by energy source / building type / vintage / system type) for Lighting, Space Cooling, Space Heating, Water Heating, Appliances
- **Table 20**: Total Households by Building Type and Principal Heating Energy Source
- **Table 21–26**: Housing/floor-space stock by building type and vintage
- **Table 27–31**: **Heating System Stock by Building Type and Heating System Type** — confirmed a `Heat Pump` row exists distinct from `Electric` (baseboard), `Natural Gas`, `Heating Oil`, `Wood`, `Other`, and dual-system combos (`Wood/Electric`, `Wood/Heating Oil`, `Natural Gas/Electric`, `Heating Oil/Electric`). This is the heat-pump-share series the plan calls out in Section 5 (Equipment & stock).
- **Table 32–33**: Heating/Cooling system stock efficiencies
- **Table 34–36**: Water heater stock by building type/energy source
- **Table 37–38**: Appliance stock and Unit Energy Consumption (UEC)
- Tables 39–50: same energy-source/end-use/region breakdowns repeated **per building type** (Single Detached, Single Attached, Apartments, Mobile Homes)

Smaller regions have fewer tables (e.g. some province pages omit building-type-specific tables if statistically thin) — **the pipeline must scrape each region's own index page for its actual table list/count, not assume all regions have all 50.**

## Suppressed / not-applicable cells

No confidentiality-suppressed cells were found in the residential samples checked (Canada, PEI, Territories) — NRCan's residential CEUD appears to be a fully modelled/estimated series (from their end-use model), not survey-tabulated, so it doesn't hit StatCan-style small-cell suppression.

What **does** appear as a non-numeric placeholder:
- A single **en-dash character `–` (U+2013)**, appearing for a whole row where a category is **structurally not applicable** — e.g. in region-level tables titled "Excluding Electricity-Related Emissions", the `Electricity` row under `GHG Emissions by Energy Source` is filled with `–` for every year (since electricity is excluded from that table by definition, not because data is missing).
- Confirmed: `Natural Gas = 0.0` in PEI (no gas distribution network) is a **real zero**, not suppression — distinguish `0` (genuinely zero) from `–` (not applicable) when parsing: map `–`/em-dash/blank-string cells to `null`, keep numeric `0` as `0`.
- No `"x"`, `"F"`, or `"N/A"` text markers seen in samples checked; if the ETL encounters any other stray string value in a numeric cell, treat it as `null` and log it (don't assume the marker set above is exhaustive — only 5 of the ~50+ region/table combinations were sampled).

**Units row 0 confirmed always in the row label itself** (e.g. `"Total Energy Use (PJ)"`, `"Total Households (thousands)"`, `"Energy Intensity (GJ/m2)"`) rather than a separate units column — parsing must extract the unit out of the label text via regex/lookup, there's no dedicated units field in the file.

## Proposed tidy long-format schema

Two JSON outputs per region as the plan specifies, plus one shared `meta.json`.

### `res_<region>.json`
```jsonc
{
  "region": "ca",
  "records": [
    // Energy & GHG by year × energy_source × end_use × building_type
    {
      "year": 2023,
      "energy_source": "electricity",   // "electricity" | "natural_gas" | "heating_oil" | "other" | "wood" | "all"
      "end_use": "all",                  // "all" | "space_heating" | "water_heating" | "appliances" | "lighting" | "space_cooling"
      "building_type": "all",            // "all" | "single_detached" | "single_attached" | "apartments" | "mobile_homes"
      "energy_PJ": 1372.446,
      "ghg_Mt": 41.869,
      "ghg_convention": "excl_electricity"  // "incl_electricity" | "excl_electricity" — REQUIRED, see note above; "all"/economy-wide totals carry both as separate records or as two fields, TBD in Phase 1 based on which tables are actually pulled
    }
    // ... one record per (year, energy_source, end_use, building_type) combination actually present in the source tables
  ],
  "explanatory": [
    // Activity + equipment-stock variables, kept in a separate flat block per the plan
    {"year": 2023, "variable": "households", "segment": "all", "value": 16864.975, "unit": "thousands"},
    {"year": 2023, "variable": "floor_space", "segment": "all", "value": 1650.0, "unit": "million_m2"},
    {"year": 2023, "variable": "heating_system_stock", "segment": "heat_pump", "value": 1335.229, "unit": "thousands"},
    {"year": 2023, "variable": "heating_system_stock", "segment": "electric_baseboard", "value": 5781.513, "unit": "thousands"},
    {"year": 2023, "variable": "heating_degree_day_index", "segment": "all", "value": 0.877, "unit": "index"},
    {"year": 2023, "variable": "appliance_uec", "segment": "refrigerator", "value": null, "unit": "kWh_per_year"}
    // etc — variable+segment together identify the series; unit always explicit since source mixes PJ/GJ/thousands/index
  ]
}
```
Rationale for `energy_source`/`end_use`/`building_type` all defaulting to `"all"` when not broken out: a single record set can represent Table 1 (by energy source only, end_use="all") and Table 2 (by end-use only, energy_source="all") without two incompatible schemas — consumers filter/pivot on whichever dimension they need and treat `"all"` as the aggregate. Suppressed/N/A source cells (the en-dash case) become `"energy_PJ": null` / `"ghg_Mt": null`, never `0`.

### `meta.json`
```jsonc
{
  "source": "NRCan Office of Energy Efficiency — Comprehensive Energy Use Database",
  "source_url": "https://oee.nrcan.gc.ca/corporate/statistics/neud/dpa/menus/trends/comprehensive_tables/list.cfm",
  "release_year_folder": "2023",
  "retrieved": "2026-07-08",
  "regions": {"ca": "Canada", "nl": "Newfoundland and Labrador", "pe": "Prince Edward Island", "ns": "Nova Scotia", "nb": "New Brunswick", "qc": "Quebec", "on": "Ontario", "mb": "Manitoba", "sk": "Saskatchewan", "ab": "Alberta", "bc": "British Columbia", "tr": "Territories"},
  "year_range": [2000, 2023],
  "energy_sources": ["electricity", "natural_gas", "heating_oil", "other", "wood"],
  "end_uses": ["space_heating", "water_heating", "appliances", "lighting", "space_cooling"],
  "building_types": ["single_detached", "single_attached", "apartments", "mobile_homes"],
  "units": {"energy_PJ": "petajoules", "ghg_Mt": "megatonnes CO2e", "households": "thousands", "floor_space": "million m2"},
  "ghg_caveat": "Most per-region and per-end-use GHG tables report emissions EXCLUDING electricity-related emissions (electricity grid intensity varies too much by province to blend); only the top-level national energy-source table (Table 1) reports both including and excluding.",
  "notes": "Suppressed/not-applicable source cells (en-dash '–') mapped to null. Table numbering and count varies per region — not all regions have all tables."
}
```

## Open items for Phase 1
- Decide which subset of the ~50 residential tables to actually parse for v1. The plan's schema (year × energy_source × end_use × building_type) is covered by Tables 1, 2, 39/40/43/44/46/47/49/50 (per-building-type energy+end-use) plus 3/13/16/19 (regional, not needed since we fetch per-region directly) — Tables 4–12, 14–18 are finer end-use-specific cuts (e.g. cooling by system type) that may be nice-to-have but aren't required for the plan's v1 charts.
- Table 27 family (heating system stock, incl. Heat Pump) and Table 37/38 (appliance stock/UEC) are required for the plan's Section 5 (Equipment & stock) — confirmed present and parseable.
- Only 5 of 50 residential-Canada tables and a handful of regional variants were sampled in Phase 0; Phase 1's parser should be written defensively (section-header-driven, not hardcoded row indices) since row counts differ table-to-table (e.g. Table 1 has 62 rows, Table 27 has 61, Table 5 for Territories has 50).
- Confirm table-count-per-region by scraping each region's `trends_res_<juris>.cfm` index page rather than assuming table numbers are the same across regions — not yet verified for regions other than `ca`, `pe`, `tr`.
