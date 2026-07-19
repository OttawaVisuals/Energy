# Construction Activity Dashboard — Plan

A single-file HTML page (`construction.html`) tracking Canadian building-sector activity —
building permits, housing starts, and construction investment — at the **national,
provincial, and CMA** level, following the same architecture as `ceud.html` and
`retrofits.html` (Python ETL → precomputed JSON → static page on GitHub Pages).

Scope decisions (confirmed 2026-07-09):
- **Geography:** Canada, provinces, and major CMAs (Ottawa-Gatineau, Toronto, Vancouver, …).
  A city-of-Ottawa open-data deep dive (geocoded permits, ward map) is deferred to a later phase.
- **Sectors:** residential **and** non-residential (industrial / commercial / institutional).
- **Context series:** included (rates, price indices, population, employment) as overlays.
- **Refresh:** monthly GitHub Action runs the ETL and commits updated JSON.

---

## 1. Data sources

All core tables are on the **Statistics Canada Web Data Service** (free JSON API, no key).
Table IDs below were verified live against `getCubeMetadata` on 2026-07-09 — the older
permits/investment tables (34-10-0285, 34-10-0066, 34-10-0175) are **archived**; the
tables listed here are their current successors.

### 1.1 Core activity tables (monthly)

| Table | Content | Geography | Key dimensions |
|---|---|---|---|
| **34-10-0292** | Building permits | Canada, provinces, CMAs (66 geos) | 89 building types (res: single/semi/row/apartment; non-res: industrial/commercial/institutional); type of work (new vs renovation); **5 variables**: permit value, dwelling units *created*, units *lost*, units *demolished*, permit count; SA/NSA × current/constant $ |
| **34-10-0293** | Investment in building construction | Canada, provinces, CMAs (66 geos) | 34 structure types; new construction vs renovations vs conversions; SA/NSA × current/constant $ |
| **34-10-0151** | Housing starts, under construction, completions (CMHC) | Canada, provinces | starts / under construction / completions; 5 dwelling types; unadjusted (SAAR from 34-10-0158). *Replaced planned 34-10-0143, whose UC/completions series dead-end in 2002/2022.* |
| **34-10-0154** | Starts, under construction, completions in **selected CMAs** (CMHC) | CMAs | same pipeline measures at CMA level |
| **34-10-0148** | Housing starts **by intended market** (CMHC) | Canada, provinces, centres 10 000+ | rental / condo / freehold / co-op — the purpose-built-rental story |
| **34-10-0149 / 0150** | Absorptions & unabsorbed inventory of newly completed dwellings (CMHC) | CMAs | completed-and-unsold stock — supply-overhang indicator |

Notes:
- **Provincial pipeline gap:** CMHC discontinued province-level under-construction and
  completions after 2022 in every StatCan table (verified live 2026-07-09: 34-10-0151,
  0136, 0139 and annual 0126 are all null from 2023; only starts continue monthly).
  CMA-level series (34-10-0154) remain current. The dashboard annotates this rather
  than approximating.
- 34-10-0292 covering units *created, lost and demolished* enables **net new units** charts, not just gross permits.
- Ottawa-Gatineau appears as separate Ontario / Quebec parts in 34-10-0292/0293 — sum for the full CMA, or show the Ontario part to match "Ottawa".

### 1.2 Context / driver series

| Table / source | Content | Frequency |
|---|---|---|
| **18-10-0205** | New housing price index (by CMA) | monthly |
| **18-10-0289** | Building construction price indexes, by building type and CMA (successor to 18-10-0276) | quarterly |
| **34-10-0145** | CMHC 5-year conventional mortgage lending rate | monthly |
| **Bank of Canada Valet API** (`https://www.bankofcanada.ca/valet/observations/V39079/json`) | Overnight policy rate | daily → resample monthly |
| **17-10-0009** | Population estimates (Canada, provinces) — per-capita normalization | quarterly |
| **14-10-0355** | Employment by industry (construction NAICS 23), provinces | monthly |
| **34-10-0127…0133** | CMHC rental vacancy rates & average rents (October survey) | annual |

### 1.3 Deferred (later phase)

- **City of Ottawa Open Data** — individual geocoded building permits via ArcGIS REST
  (open.ottawa.ca) → ward-level map section.
- Other municipal open-data portals (Toronto, Calgary, Vancouver) follow the same pattern.

---

## 2. ETL — `Python/construction_etl.py`

1. Pull each table via WDS `getFullTableDownloadCSV` (big tables) or
   `getDataFromVectorsAndLatestNPeriods` (small vector sets like rates).
   *Reminder: WebFetch is blocked for some data hosts — use `curl`/`requests` directly,
   which works fine for StatCan and BoC.*
2. Filter to the member subset the page actually uses (e.g. ~10 of the 89 building types,
   drop the granular "foundation/superstructure" work stages).
3. Write compact per-geography JSON to `construction_json/`, mirroring the `ceud_json`
   naming pattern:
   - `constr_ca.json`, `constr_on.json`, … `constr_ab.json` (one per province + Canada)
   - `cma_ottawa.json`, `cma_toronto.json`, … (one per selected CMA)
   - `context.json` (rates, price indices, population — small, shared)
   - `meta.json` (last-updated dates per source, series start dates)
4. Each JSON: `{series_key: {start: "1990-01", freq: "m", values: [...]}}` — arrays, not
   row objects, to keep files small.
5. **Storage conventions** (added 2026-07-09 after the Phase-1 size review):
   - Only series a planned chart actually reads are written — whitelist by chart,
     not by dimension. Aggregates (total / residential / non-residential) carry the
     full work-type breakdown; detail building types carry `work=total` only.
   - All dollar series (`permits.value.*`, `invest.*`) are stored in **millions of
     dollars** (2 decimals); all unit counts are **integer units** (SAAR multiplied
     out from StatCan's thousands). `meta.json` `series_units` records this.
   - Unadjusted (`nsa_*`) variants are shipped only where no seasonally adjusted
     sibling exists; when both are published, only `sa_*` is kept.
   - Result: far fewer series (~65–80) and roughly 5–10× smaller files per geography
     than the naive dump.

**Refresh:** `.github/workflows/construction-refresh.yml` — monthly cron (StatCan releases
permits ~6 weeks after reference month, starts mid-month, investment ~2 months). Runs the
ETL, commits `construction_json/` if changed.

---

## 3. Page structure — `construction.html`

Same design system as `ceud.html` (Fraunces/Inter, KPI band, `chart-grid` cards,
inline-SVG charts, shared tooltip, simple/advanced toggle). Geography selector at top:
**Canada → province → CMA** (reuse the retrofits selector pattern).

| # | Section | Chart | Data |
|---|---|---|---|
| 1 | **Headline KPIs** | Tiles with sparkline + YoY%: permit value, starts (SAAR), under construction, investment | 0292, 0143, 0293 |
| 2 | **The pipeline** *(signature chart)* | Permits (units) → starts → under construction → completions as layered monthly series; under-construction stock as area behind flow lines | 0292 + 0143/0154 |
| 3 | **What's being built** | Stacked area of starts by dwelling type (single / semi / row / apartment) — the decades-long shift to apartments | 0143 |
| 4 | **Who it's built for** | Starts by intended market: rental vs condo vs freehold (stacked bars, share toggle) | 0148 |
| 5 | **Residential vs non-residential** | Permit value split; ICI breakdown (industrial / commercial / institutional) | 0292 |
| 6 | **New build vs renovation** | Investment by work type — ties into the retrofits page story | 0293 |
| 7 | **Real vs nominal** | Constant-$ toggle on value charts; NHPI / BCPI lines in advanced mode | 0292/0293 constant $, 18-10-0205/0289 |
| 8 | **Provincial comparison** | Per-capita permits/starts bar chart + small multiples; Canada map choropleth (advanced) | 0292, 0143, 17-10-0009 |
| 9 | **CMA comparison** | Sortable table with sparklines: starts, permits value, under construction, unabsorbed inventory | 0154, 0292, 0149 |
| 10 | **Rate cycle overlay** | Starts (6-mo trend) vs BoC overnight rate + 5-yr mortgage rate, dual axis | 0143, 0145, Valet |
| 11 | **Net new supply** *(advanced)* | Units created − lost − demolished from the permits table | 0292 |
| 12 | **Construction labour** *(advanced)* | Construction employment vs units under construction — capacity constraint view | 14-10-0355, 0143 |

Footer: source attribution (Statistics Canada, CMHC, Bank of Canada), last-updated dates
from `meta.json`, methodology notes (SA vs SAAR, constant-$ base year, CMA definitions).

---

## 4. Build order

1. `construction_etl.py` — permits (0292) + starts (0143/0154) + investment (0293),
   Canada + provinces + 6–8 CMAs → `construction_json/`.
2. `construction.html` skeleton: selector, KPI band, sections 1–3.
3. Sections 4–9 (market type, splits, comparisons).
4. Context ETL (rates, prices, population) + sections 10–12.
5. GitHub Action + README section.
6. *(Later)* Ottawa open-data permit map phase.

---

## 5. Claude Code prompt playbook

One prompt per phase, in order. Each is self-contained — paste it into a **fresh
Claude Code session** in `C:\Energy`; it does not assume memory of any prior session.
Run one phase at a time and eyeball the result before moving on.

**Model suggestion:** use **Opus** (or better) for Phases 1, 2 and 6 — they involve
API archaeology, data-shape design, and chart layout decisions. **Sonnet** is fine for
Phases 3, 4 and 5, which mostly extend established patterns.

**General tips**
- If a phase goes sideways, it's cheaper to restart the session with the same prompt
  plus one sentence about what went wrong than to keep patching.
- After each phase, commit before starting the next, so a bad phase is a clean revert.
- StatCan occasionally rate-limits; if the ETL fails on a fetch, just rerun.

### Phase 1 — Core ETL

```text
Read CONSTRUCTION_PLAN.md, especially sections 1.1 and 2. Then build
Python/construction_etl.py.

Task: pull the core activity tables from the Statistics Canada Web Data Service
(WDS) REST API and write compact JSON for a static dashboard:

- 34-10-0292 building permits (monthly): permit value (current AND constant $,
  seasonally adjusted), dwelling units created / lost / demolished, permit count.
  Keep a usable subset of building types: total, total residential, single, semi,
  row, apartment, total non-residential, industrial, commercial, institutional.
  Keep type of work: total, new construction, renovation. Drop the granular
  construction-stage members (foundation, superstructure, etc.).
- 34-10-0293 investment in building construction (monthly): same structure-type
  subset, work types new/renovation/conversion/total, seasonally adjusted,
  current and constant $.
- 34-10-0143 housing starts / under construction / completions (monthly,
  Canada + provinces): all 6 dwelling types, both SAAR and unadjusted.
- 34-10-0154 same pipeline measures for selected CMAs (monthly).
- 34-10-0148 housing starts by intended market (rental / condo / freehold /
  co-op), Canada + provinces.

Geographies: Canada, all 10 provinces, and these CMAs: Ottawa-Gatineau
(Ontario part and Quebec part, plus a computed combined series), Toronto,
Montreal, Vancouver, Calgary, Edmonton, Winnipeg, Halifax.

Implementation notes:
- Use the WDS getFullTableDownloadCSV endpoint (POST product id + language,
  response contains a URL to a zip of the full CSV; download, unzip, filter
  with pandas). Verify each table's live member names with getCubeMetadata
  first rather than hardcoding blind — member names in this plan were checked
  on 2026-07-09 but confirm before filtering.
- Fetch with the requests library directly (works fine for StatCan).
- Output to construction_json/ following section 2 of the plan:
  constr_ca.json, constr_on.json ... one per province; cma_ottawa.json etc.
  one per CMA; meta.json with per-table last reference month and series start.
- Series format: {"series_key": {"start": "YYYY-MM", "freq": "m",
  "values": [...]}} with nulls for gaps. Keys like
  "permits.value.residential.new.sa_constant" — document the key scheme in a
  header comment.
- Keep each province file under ~300 KB; trim history to 1990+ if needed.

Follow the style of the existing scripts in Python/ (see ceud_etl.py and
ers_web_pipeline.py). When done: run the script, then print a summary — file
count, sizes, date range per table — and sanity-check one known value against
StatCan's website (e.g. latest national housing starts SAAR) and report the
comparison.
```

### Phase 2 — Page skeleton + signature charts

```text
Read CONSTRUCTION_PLAN.md (section 3) and skim ceud.html to absorb its design
system: fonts (Fraunces/Inter), CSS variables, KPI band, .chart-grid cards,
inline-SVG charts with the shared .chart-tip tooltip, legend components, and
the simple/advanced mode toggle. The data is already in construction_json/
(format documented in the header of Python/construction_etl.py).

Build construction.html as a single self-contained file (HTML + CSS + JS, no
frameworks, no chart libraries — hand-rolled SVG like ceud.html) containing:

1. Header + geography selector: Canada → province → CMA, styled like the
   retrofits.html selector. Data loads per-geography JSON on selection.
2. Headline KPI band (plan section 3, row 1): latest permit value, housing
   starts (SAAR), units under construction, investment — each with a
   12-month sparkline and YoY % badge (green/red).
3. The pipeline chart (plan section 3, row 2): permits (dwelling units
   created), starts, and completions as monthly lines with a 6-month
   moving-average toggle, drawn over a shaded area of units under
   construction. Shared tooltip showing all series at the hovered month.
4. "What's being built" (row 3): stacked area of starts by dwelling type,
   with an absolute/share toggle.

For development, fetch from the local construction_json/ directory; keep a
BASE_URL constant at the top of the script block that can be switched to
raw.githubusercontent.com like retrofits.html does.

Verify in the browser preview: no console errors, charts render for Canada,
Ontario, and Ottawa-Gatineau, tooltips work, selector switches cleanly.
Screenshot the result.
```

### Phase 3 — Remaining core sections

```text
Read CONSTRUCTION_PLAN.md section 3. construction.html already has the
selector, KPI band, the pipeline chart, and the dwelling-type stacked area
(rows 1–3 of the section table). Add rows 4–9, reusing the existing chart
helpers, tooltip, legend and card patterns already in the file:

4. Starts by intended market: rental / condo / freehold stacked bars with a
   share toggle (data keys under "starts_market.*").
5. Residential vs non-residential permit value, with an ICI
   (industrial/commercial/institutional) breakdown.
6. Investment new-build vs renovation vs conversion.
7. Real vs nominal: add a constant-$ toggle to the value-based charts
   (the *_constant series are already in the JSON).
8. Provincial comparison: per-capita horizontal bar chart (population is in
   context.json if present, else hardcode 2025 provincial populations with a
   TODO) plus small-multiple sparklines per province.
9. CMA comparison: sortable table — starts (trailing 12m), permit value
   (trailing 12m), under construction, each with a sparkline column.

Mark sections 7's price-index lines and anything depending on context.json as
advanced-mode if the file doesn't exist yet (Phase 4 adds it). Verify in the
browser preview for at least Canada, Quebec, and Toronto; check the console
for errors; screenshot each new section.
```

### Phase 4 — Context ETL + advanced sections

```text
Read CONSTRUCTION_PLAN.md sections 1.2 and 3 (rows 10–12).

Part A — extend the ETL. Add a fetch_context() step to
Python/construction_etl.py (or a small sibling script) producing
construction_json/context.json with:
- 18-10-0205 new housing price index (Canada + the plan's CMAs), monthly
- 18-10-0289 building construction price indexes (residential + non-res
  composite per CMA), quarterly
- 34-10-0145 CMHC 5-year conventional mortgage rate, monthly
- Bank of Canada overnight rate from the Valet API
  (https://www.bankofcanada.ca/valet/observations/V39079/json), resampled to
  monthly (month-end value)
- 17-10-0009 quarterly population, Canada + provinces
- 14-10-0355 construction employment (NAICS 23), provinces, SA
Use the same series JSON format as the other files. Run it and report ranges.

Part B — add the three advanced-mode sections to construction.html:
10. Rate cycle overlay: housing starts (6-month MA) vs overnight rate and
    5-yr mortgage rate, dual y-axis, recession-style shading optional.
11. Net new supply: units created minus lost minus demolished (stacked +/-
    bars with a net line), from the permits series already loaded.
12. Construction labour: construction employment vs units under construction,
    indexed to 100 at a common base year.
Also wire the per-capita normalization in the provincial comparison to the
real population series, replacing any hardcoded values.

Verify in the browser preview in advanced mode; screenshot the new sections.
```

### Phase 5 — Automation + docs

```text
Read CONSTRUCTION_PLAN.md section 2 (refresh) for context.

1. Create .github/workflows/construction-refresh.yml: monthly cron (around
   the 20th, after StatCan's permits release), ubuntu-latest, Python 3.12,
   pip install requests pandas, run Python/construction_etl.py (both core and
   context steps), then commit and push construction_json/ only if files
   changed. Guard against committing on fetch failure: the script must exit
   nonzero if any table fetch fails, and the workflow must not commit then.
2. Add a "Construction dashboard" section to Readme.MD following the style of
   the existing retrofit documentation: what the page shows, data sources
   with table numbers (copy from CONSTRUCTION_PLAN.md section 1), pipeline
   steps, how to regenerate locally, and the live GitHub Pages URL pattern.
3. Update CONSTRUCTION_PLAN.md: mark completed phases and note anything that
   diverged from the plan.

Do not enable the workflow blindly — validate the YAML (actionlint if
available, otherwise careful review) and do a dry run of the ETL locally to
confirm exit codes behave as specified.
```

### Phase 6 (later) — Ottawa permit map

```text
Read CONSTRUCTION_PLAN.md sections 1.3 and 3. construction.html is a working
CMA-level dashboard; this phase adds an Ottawa deep-dive section.

1. Explore the City of Ottawa open data portal (open.ottawa.ca) for the
   issued building permits dataset; it is served from an ArcGIS hub, so
   locate the ArcGIS REST FeatureServer endpoint and check available fields
   (permit type, construction value, issue date, ward, coordinates) and how
   far back records go.
2. Write Python/ottawa_permits_etl.py: pull the last 5 years of permits,
   aggregate to (a) monthly totals by permit type and (b) ward-level rollups
   (count + construction value, trailing 12 months), plus a thinned point
   set (round coordinates, drop fields) for a dot map kept under ~1 MB.
   Output to construction_json/ottawa/.
3. Add an "Ottawa deep-dive" section to construction.html, visible when
   Ottawa-Gatineau is selected: ward choropleth + dot map as inline SVG
   (reuse the FSA_Maps approach — no Leaflet), a permit-type breakdown, and
   a monthly issuance trend against the CMA-level StatCan series as a
   cross-check.

Verify in the browser preview; compare the open-data monthly totals against
the StatCan Ottawa series and report how closely they track (they will not
match exactly — different coverage — but should correlate; explain any large
divergence in a footnote on the page).
```
