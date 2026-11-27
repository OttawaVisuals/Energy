# District Energy Explorer

2026-10-31: shared artwork/header, chart controls and one-column phone chart
grids; see [Visual polish](VISUAL_POLISH.md). Publication pending.

2026-10-30: matching tab icon and social preview added; see [branding](BRANDING.md).

2026-10-30: approved landing-page icon option 1 connects an energy centre to
multiple buildings through amber/teal thermal pipes (`assets/icons/district-energy.png`).
Conceptual illustration, not a detailed network design. Applied locally; Published 2026-10-30.

**Page:** [`districtenergy.html`](../districtenergy.html) · **Live:** https://ottawavisuals.github.io/Energy/districtenergy
**Pipeline:** [`Python/district_energy_etl.py`](../Python/district_energy_etl.py)
**Data:** `districtenergy_json/` (gitignored on `main`, published to `gh-pages`)
**Curated inputs:** `districtenergy/curated/` (committed — hand-entered, not regenerable)
**Raw inputs:** `districtenergy/raw/` (gitignored — re-downloadable)

Created 2026-09-03. Restructured 2026-09-04.

---

## What it is

An explainer *and* an explorer for Canadian district energy, aimed at both
audiences at once, in five sections:

- **§01 District Energy 101** — what a district energy system is, the IEA
  1G→4G generation ladder (including the IEA's own objection to the term
  "5G", displayed on the page as "1st Gen"–"4th Gen"), heat carriers, single-
  vs two-pipe vs ambient-loop networks, and a quick description of every
  energy source and piece of equipment (including geothermal, waste heat and
  solar thermal, added 2026-09-04 alongside the diagram).
- **§02 What Canada has built, and what's coming** — the national inventory
  (all 254 systems CEEDC records, mapped and filterable, against a background
  layer of Canada's whole innovative-energy fleet), the coverage-honesty
  charts, the projects that postdate the inventory, and what operators say
  they're considering next.
- **§03 Policy, and why it isn't scaling** — municipal, provincial and federal
  levers, then the barriers, then what the evidence actually supports on cost
  and emissions. See **Non-CEEDC content**, below.
- **§04 World leaders** — four country profiles (Denmark, Sweden, Germany,
  Finland) contrasting how other mature markets got there, each tied back to a
  specific Canadian gap. See **Non-CEEDC content**.
- **§05 How this page was built** — the two methodologies.

### Layout rules, after the 2026-09-04 restructure

Worth knowing before editing, because two of these were bugs:

1. **Boxes are for charts, diagrams, tables and the generation ladder.**
   Descriptive prose is unboxed (`.plain` / `.prose`) and **single column** —
   no side-by-side text.
2. **`.prose` is `max-width:1000px` at `15px`.** It was 820px/14px, which
   rendered at 72% of a 1,140px column. Do not "fix" text width with a
   descendant selector like `.plain .prose` — the markup is
   `class="prose plain"` on a single element, so a descendant selector silently
   does nothing. That exact mistake shipped once.
3. **A chart is either full-width with a ~900-wide viewBox authored for it, or
   two-up in `.chart-grid`.** Never a 460-wide viewBox stretched full width:
   the decarb chart rendered 869×623px that way, ~2.4× intended.
4. **The sticky section nav is rect-based, not IntersectionObserver.** IO
   callbacks are dispatched from the rendering pipeline, which doesn't run
   frames in this repo's preview renderer, so an IO-driven nav highlights
   nothing there. A `scroll` handler plus `getBoundingClientRect` works in
   both.

---

## Non-CEEDC content (added 2026-09-04)

Three pieces of the page are **not derived from the CEEDC inventory** and
carry their own citations rather than a pipeline provenance trail. They are
static HTML, hand-written and hand-sourced — there is no JSON round-trip and
no curated-input file, the same pattern the "why anyone builds one" prose
already used before this restructure:

- **Policy and barriers (§03).** Primary source is the **Building
  Decarbonization Alliance + Dunsky Energy + Climate white paper**,
  [*Thermal Energy Networks in Canada*](https://buildingdecarbonization.ca/report/thermal-energy-networks-in-canada/)
  (2025, 42pp). ⚠️ **WebFetch returns this PDF as unparseable binary.** It was
  extracted with `pymupdf` against the cached download instead — do that again
  rather than concluding the report has no usable content, which is what
  happened on the first attempt. The chapters used are *Policy and Regulatory
  Landscape Across Canada* (pp. 14–21) and *Why TENs Aren't Scaling (Yet)*
  (pp. 22–25). Facts drawn from it: only the **BCUC** has a provincial
  thermal-utility regulatory framework as of May 2025, against **15 US states**
  with legislation passed or in development; Vancouver has Canada's only active
  building emissions performance standard, with Montréal and Toronto at
  disclosure stage; Alberta rolled back municipal authority to exceed code in
  2023 and Ontario's Bill 17 may do likewise; the federal consumer carbon price
  was repealed April 2025; the Canada Green Buildings Strategy "has little to
  say on" thermal networks; **the national model code treats network heat as
  purchased energy at an assumed COP of 1.0**, penalising a plant-side heat
  pump against an identical basement-side one; and the barrier set (financing
  asymmetry vs gas rate-base recovery, unclear stakeholder roles, municipal
  capacity and awareness). Vancouver's mandatory connection is cited to the
  primary document,
  [Energy Utility System By-law No. 9552](https://bylaws.vancouver.ca/9552c.pdf).
- **The UK consumer survey (§03).** Via the same paper: a 2022 national survey
  of 2,244 heat-network customers against 1,733 matched non-users found a lower
  average bill (£600 vs £960) but **1 in 10 paying £2,000+**, more outages
  (50% vs 29%) and 39% satisfaction with complaint handling. Kept because it is
  the only consumer-side evidence found that cuts against the technology, and
  it comes from a report advocating for it.
- **Cost & emissions (§03).** No rigorous Canadian cost/GHG comparison against
  individual furnaces exists publicly. What's on the page instead: the white
  paper's own hedged framing (networks are *"not inherently low carbon"* and
  *"may not always reduce energy costs compared to the current fossil-fired
  status quo"* while often beating **other low-carbon pathways**); the federal
  government's measured **63% emissions cut** at the NCR DES (one project's
  engineering estimate, not a national average); and the potential figures —
  ~3% of Canadian heating demand served today, **70% of Canadians living where
  networks could serve them (McMaster University's finding, cited by BDA — not
  BDA's own)**, and Québec's recoverable waste heat at ~40% of residential
  heating demand (64–81 PJ) — all labelled technical potential, not forecast.
  CEEDC's own stated limitation (**What this page deliberately does not
  claim**, below) is cross-referenced rather than repeated.
- **World leaders (§04).** Denmark (~70% of households, cost-based municipal
  pricing — [RAP, Jan. 2025](https://www.raponline.org/wp-content/uploads/2025/01/RAP-Oxenaar-Making-Europes-homes-Hygge-January-2025.pdf));
  Sweden (~90% of multi-family/public buildings, density-limited —
  [Stockholm Environment Institute](https://www.sei.org/publications/swedish-heat-energy-system-new-tensions-and-lock-ins-after-a-successful-transition/));
  Germany (2024 *Wärmeplanungsgesetz* mandating 100,000 connections/year —
  [Clean Energy Wire](https://www.cleanenergywire.org/news/germany-connect-100000-buildings-district-heating-annually));
  Finland (Fortum/Microsoft data-centre waste heat, ~40% of local network
  capacity — [Hitachi Energy](https://www.hitachienergy.com/us/en/news-and-events/features/2024/03/fortum-to-use-waste-heat-from-data-centers-to-heat-premises-and-homes)).

None of this touches `district_energy_etl.py` or `districtenergy_json/` — it
is static prose in `districtenergy.html`, so refreshing the CEEDC pipeline
never goes stale here, but it also won't get *fresher* on its own. If Germany
hits its 2026 municipal-heat-plan deadline or Vancouver expands the NEU
service area, this section needs a manual revisit, same as `projects.json`'s
`reviewed` date.

---

## Sources

| What | Source | Vintage |
|---|---|---|
| District energy inventory | CEEDC (Canadian Energy and Emissions Data Centre), SFU — `CEEDC_IEF_district energy.xlsx` | dashboard last updated **2024-01-24** |
| Full IEF superset (map context layer) | CEEDC — `CEEDC_IEF_public.xlsx`, 3,644 facilities | same |
| Published aggregates the file can't reproduce | Griffin, B. (2023). *District Energy in Canada*. CEEDC, for CanmetENERGY-Ottawa, NRCan | **December 2023** |
| Generation definitions | [IEA DHC, *District heating network generation definitions*](https://www.iea-dhc.org/fileadmin/public_documents/2402_IEA_DHC_DH_generations_definitions.pdf) | February 2024 |
| Building-stock context (3.1% / 1.4% figures) | NRCan CEUD 2023, via the CEEDC report | 2023 |
| Province outlines | repo's own `geo_json/*.json`; Yukon from `lfsa000b21a_e.json` | static |

**Where the files come from.** Both workbooks are public downloads exposed
inside CEEDC's own Tableau dashboard
(<https://cieedacdb.rem.sfu.ca:8006/district-energy-inventory/> → "Download
data"). They are not linked from `sfu.ca/ceedc/databases.html` — that page only
embeds the dashboard, so the download links are only discoverable from inside
the rendered viz.

**Licensing.** CEEDC states no licence, citation requirement or redistribution
terms on the databases page, the publications page, the report, or the main
site (`ceedc/contact/terms-conditions.html` 404s). Confirmed with Simon
2026-09-03: he works with people at CEEDC, there is no problem using the data,
**the requirement is to reference the source**. The page therefore credits CEEDC
in the header badge, the footer, every methodology block and the sources panel,
and links back to both their dashboard and their report.

---

## The thing that will bite you: file ≠ report

**CEEDC's public download does not reproduce the totals in CEEDC's published
report.** Respondent-confidential values were withheld from the public file, so
every total derived from the workbook comes out lower, on a smaller n:

| | Public file | 2023 report |
|---|---|---|
| Steam capacity | 3,757 MW (n=50) | 3,990 MW (n=57) |
| Hot-water capacity | 932 MW (n=54) | 1,024 MW (n=68) |
| Cooling capacity | 946 MW (n=40) | 981 MW (n=43) |
| Electrical capacity | 276 MW (n=25) | 314 MW (n=26) |
| Steam production | 4.05M MWh (n=31) | 5.13M MWh (n=57) |

Both are correct — they answer different questions. The pipeline computes this
delta rather than asserting it (`meta.json → file_vs_report`), and the page
shows it as a table in Advanced mode. **Never present a file-derived total as
the report's figure, or vice versa.** The KPI row deliberately uses *report*
figures for national headline numbers (capacity, energy delivered, buildings)
and *file* figures for anything with a per-system breakdown, and labels which
is which.

---

## Data honesty rails applied

Per `CLAUDE.md`, each of these is surfaced on the page, not just here:

- **Response rate.** 238 operating systems identified; **38 completed the 2023
  questionnaire (21%)**; ~160 have detailed data from any survey year. Section
  06 states this in the page's own words.
- **Coverage.** **90 of 238 operating systems (38%) report zero quantitative
  fields** — name, city, province, fuel, often a year, and nothing measurable.
  Charted directly (`data_density`), because it is the ceiling on every capacity
  and energy figure on the page.
- **Data vintage.** `year_reported` runs **2014–2023** per row (82 rows are 2017,
  40 are 2018, 40 are 2022). "The 2023 inventory" is a decade of snapshots
  stacked together — CEEDC's own stated caveat. Charted, and exposed per system
  in the detail panel.
- **Tri-state flags preserved.** `de_hs` / `de_hw` / `de_cw` are Yes / No /
  empty. 98 operating systems say "no cooling"; 99 more never answered.
  Collapsing empty→false would invent 99 confirmed no-cooling systems, so
  "not reported" is its own bar on the services chart.
- **Nothing dropped silently.** The two suspect hot-water temperatures
  (Confederation Heights 175 °C, Cape Breton University 200 °C — almost
  certainly steam temperatures in the wrong field) are kept, ringed on the
  chart, and listed in `meta.json`. Same for the one Planned system with a past
  commissioning year (University of Lethbridge, 1970 — probably a planned
  conversion) and any implied capacity factor over 100%.
- **Small n labelled.** Every chart carries its own n, because coverage varies
  field by field. The IEA generation chart carries an explicit
  "illustrative, not representative" callout at n=26.

---

## Methodology decisions worth defending

### IEA generation assignment

Applied to `de_hw_supply` only. Thresholds straight from IEA DHC (Feb 2024):

| | Rule |
|---|---|
| 1G | steam carrier, **independent of temperature** |
| 2G | liquid water **> 100 °C** |
| 3G | **70–100 °C** |
| 4G | **maximum forward flow 70 °C** |
| TSN | near-ambient loop feeding decentralised heat pumps — a **subclass of 4G** |

Three decisions:

1. **1G is never inferred from a temperature.** IEA defines it by carrier, so
   the steam-network count (**94 operating systems**) is reported separately
   with its own n rather than folded into the ladder. Systems running steam
   *and* hot water cannot be reduced to a single generation at all, and the page
   says so instead of summing them into one tidy histogram. This was an explicit
   decision with Simon on 2026-09-03: the alternative — inferring 1G from the
   steam flag to boost n from 26 to ~120 — was considered and rejected as
   conflating "uses steam" with "is a 1G network".
2. **Exactly 70 °C → 4G.** It falls inside both the 3G range ("between 100 °C
   and 70 °C") and the 4G rule ("maximum of 70 °C"); the 4G rule is more
   specific and names 70 °C as the physical DHW thermal-disinfection threshold.
3. **"5G" is not used.** IEA DHC explicitly recommends against it. The page uses
   *thermal source network* and shows it as a subclass of 4G, and explains why.

Result: **n = 26** (2G 5, 3G 17, 4G 4), one TSN (UBC Okanagan, 8 °C supply /
4 °C return), two flagged suspects. That is **11% of the operating fleet** —
enough to place real Canadian systems on the ladder, nowhere near enough to
characterise the country, and the page says exactly that.

### Fuels: sets, not a primary fuel

The workbook has **no primary-fuel column**. CEEDC's dashboard derives one
inside its Tableau `.hyper` extract, which is not published. Rather than guess
at their priority order, the pipeline keeps the **complete fuel set** per system
and reports single-source vs multi-source counts separately, mirroring the
report's own Table 8. This is also the more honest framing — 42% of systems are
multi-source, and oil is overwhelmingly a backup/peaking fuel sitting *next to*
gas rather than a primary fuel.

### Capacity factor

`de_*_production ÷ (de_*_capacity × 8760)`, only where both are present and
non-zero. Values >100% are flagged in `meta.json`, not clipped. CEEDC's own
averages are 13–20%; their stated reasons (short seasons, redundancy, planned
expansion, retired-but-retained capital) are reproduced on the page, because a
reader who sees "14% capacity factor" without them will conclude the asset is
broken.

### Geometry

Province outlines are unioned from the repo's existing FSA polygons and
simplified to 0.06° / 0.02 deg² minimum area (tuned to land under the 300 KB
per-file budget: 307 KB → 155 KB). Yukon has no `geo_json` file — the same gap
`Python/canada_boundary.py` documents — so its outline is reprojected from the
national FSA file using that module's inverse-Lambert, imported rather than
copied. The page projects with a **Lambert conformal conic** (standard parallels
49°N / 77°N, central meridian −96°); equirectangular is unusable across
41–84°N. All 254 facilities carry source coordinates, all inside Canada's
bounding box; **nothing is geocoded here.**

⚠️ **The y-axis trap, for whoever ports this projection next.** The textbook LCC
formula `y = ρ0 − ρ·cos θ` is written for a maths axis where y increases
*northward*. SVG's y increases *downward*. Used unflipped it draws Canada upside
down — which looks plausible enough at a glance to pass review, and did: the
first build shipped inverted (Windsor above Arviat) and survived a numeric check
that only confirmed the *formula* gave larger y for higher latitude. The fix
negates y inside `LCC()` itself, so `fitMap`'s bounds and the drawn points stay
derived from the same numbers. If you touch this, assert on rendered
coordinates: northernmost system's `cy` < southernmost's, westernmost's `cx` <
easternmost's. (CFS Alert at 82.5°N and Windsor at 42.3°N are a convenient pair,
and both are in the data.)

---

## Known source quirks

All handled in the pipeline, all listed in `meta.json → known_source_quirks`:

1. **The Metadata sheet is misaligned.** Its "Detail" column lags the "Field"
   column by exactly 4 rows from row 60 onward, so `geo_used` reads as "Solid
   Biomass" and `waste_used` as "Spent Pulping Liquor" if taken at face value.
   The `FUELS` table in the pipeline is the corrected mapping, cross-checked
   against the fuel legend CEEDC's own dashboard renders.
2. The Metadata sheet documents an `npri` field the data sheet does not have,
   and omits the `operator` field it does have.
3. `municipality_type` ships in mixed case (`large` and `Large`, `Small` and
   `small`) — lowercased in the pipeline.
4. Facility and city names carry stray double and trailing spaces
   (`CFB Halifax  - Bedford`, `Mississauga `) — whitespace-normalised.
5. Names contain combining Unicode (`Sen̓áḵw`, `Oujé-Bougoumou`). Everything is
   read and written UTF-8; on Windows, run the pipeline with
   `PYTHONIOENCODING=utf-8` or console output will raise on the QA print.
6. Sheet layout is **row 1 = units, row 2 = field names, row 3+ = data** — not
   a normal header row.

---

## Public funders: GMF and CIB (added 2026-11-25)

Section "Who is paying" on the page, between the project cards and the planned-systems table.

- **Pipeline:** `Python/district_funders_etl.py` -> `districtenergy_json/funded_projects.json` (`{meta, gmf[], cib[]}`). Resumable; GMF detail pages cached in `Python/gmf_cache/` (scratch).
- **GMF** (Green Municipal Fund, FCM): info.gmf-fmv.ca is a Power Pages portal with no API (`/_odata` not exposed). We walk `/en-US/ProjectSearch/?page=N` (1,165 projects, 10 per page; the keyword filter is ignored) for card fields, then `/projectdetails/?id=GUID` for `Project value`, `Grant amount`, `Loan amount`. 1,165 collected, 0 detail failures.
- **CIB** (Canada Infrastructure Bank): public GraphQL `entries(type:"project")`, 131 projects. Section handle is `projects`, entry type `project`. `commitment` is free text, parsed to CAD millions; 9 unparsed (null, raw string kept).
- **"District energy" rule:** GMF sub-sector starts with "District Energy" (63 projects: 48 feasibility studies, 12 capital, 3 pilot); CIB name contains "District Energy" (3: Markham, Enwave, Lulu Island). Name-only for CIB, so retrofit programmes by district energy operators (e.g. Creative Energy Retrofits) are under "All funded projects".
- **Licensing, decided 2026-11-25: facts + links only.** CIB terms of use bar copying or republishing site content without written consent; GMF terms returned 403 and could not be read. Only names, places, types, dates and dollar amounts are kept, each linked to its source page; no descriptions or images. A judgment call, not legal clearance. Possible follow-up: ask CIB and FCM for written consent.
- **Stage / fuel / size splits (added 2026-11-25).** *Stage:* `study` = GMF `type` in {Feasibility Study, Plan, Program Design Study, Program Evaluation Study} (48 of the 63 district energy projects); `project` = everything else (12 capital, 3 pilot). *Fuel:* GMF's own District Energy sub-sector label (Waste energy recovery 21, CHP 14, Multiple sources 9, Biomass 7, Other 7, Renewable source 5); no fuel is inferred from description text (keyword matching was noisy: "natural gas" hit 48 of 63, mostly emissions wording). *Size:* GMF `Project value` in bands (<$250k, $250k-1M, $1-5M, >$5M), a cost proxy, not capacity. *Capacity:* only 3 of the 15 non-study projects state a plant MW in their description (Vancouver False Creek sewage heat +5 MW; Markham 2007 plan +5.0 MW CHP; Markham expansion existing plant), hand-entered as numbers in `districtenergy/curated/gmf_capacity.json`, no text copied. The other 12 are blank. Of 63, descriptions mention any physical size for 26, in mixed units, so no size column was built from them.
- **Not used:** the Azure Maps key visible in GMF's page source.
- **Limits:** amounts are as reported by the funder; a GMF study is not a built system; a CIB commitment is a ceiling.

## Fuel supply and trade (added 2026-11-26)

Section "Where Canada's fuels come from", at the end of section 02, after "What operators say they're considering next". Moved here from the Grid page by decision on 2026-11-26 (it fits district energy fuel choice better); the Grid page keeps only its biomass-heat capacity section.

- **Pipeline:** `Python/fuel_trade_etl.py` -> `districtenergy_json/fuel_trade.json` (41 KB, `{meta, data[fuel][geo][year] = [production, imports, exports, net_transfer_in]}` in PJ). Downloads StatCan full-table CSVs into `Python/fueltrade_cache/` (scratch, gitignored). Manual run, about once a year.
- **Fuels and tables:** natural gas, light fuel oil, heavy fuel oil from 25-10-0029 (TJ, annual, 2005-2025); electricity from 25-10-0021 (MWh; generation, US imports and exports, interprovincial receipts minus deliveries, 2005-2025); propane from 25-10-0081 (monthly m3, summed to calendar years, only years with all 12 months for every flow, so 2019-2025; 2026 partial year dropped).
- **Conversions:** TJ/1000, MWh x 3.6 GJ/MWh, propane m3 x 25.60 GJ/m3 (assumed HOT2000-internal factor, see memory note on fuel factors). Labelled "converted" on the page.
- **All 13 provinces and territories plus Canada.** The aggregates "Atlantic provinces" and "Yukon, NT and Nunavut" are excluded (double counting).
- **Checks (`meta.checks`):** 0029 electricity exports vs 0021: 194 cells compared, 21 differ by more than 2% (18 before 2018; the 3 recent ones are rounding on values near zero), so the page uses 0021 for electricity throughout. Provinces summed vs the Canada row: electricity 0%; gas up to 11% in some years (0% in 2024); light fuel oil, heavy fuel oil and propane far lower than Canada, because StatCan suppresses cells. Suppressed cells stay null and show as a dash, never zero. Missing cells: gas 81, light fuel oil 502, heavy fuel oil 402, propane 664, electricity 7.
- **Display (Canada-wide since 2026-11-26).** Third version the same day. v1 was a province table with per-column bars (read as percentages, not comparable); v2 was two stacked bars per province. Both were dropped for a **Canada-wide** chart because the provincial split misleads: in 25-10-0029 net inter-regional transfers sum to exactly zero across provinces every year checked, and a province served through a neighbour shows blank imports plus a matching transfer instead (Nova Scotia gas: blank imports, +25.3 PJ transfer in 2025, mirrored by New Brunswick at -25.3 PJ with 96.4 PJ of imports; Quebec the same, about 437 PJ received). The table appears to record trade where fuel crosses the border; that is an inference, since its notes define transfers but not imports. Now one row per fuel: top bar = made in Canada + imported; bottom bar = exported + "left in Canada" (derived: made + imported - exported; absorbs stock changes, losses and fuel used in production, so it is not consumption). Year selector (2005-2025; propane only 2019+, other years say "No Statistics Canada value"). **Show: Total (PJ)** uses one scale across fuels (small fuels are thin); **Share (%)** scales each fuel to its own supply. Checked 42 year x view combinations: no bar over 100%. Numbers table in Advanced. `fuel_trade.json` still holds every province for a later, caveated provincial view.
- **Biomass: none.** The page says why: no StatCan wood volume or trade series (Simon's statement; not independently confirmed beyond the table's "Renewable fuels" row, which at 80 PJ of Canadian production is liquid biofuels, not wood).
- **Limits.** Not consumption and not a supply balance. "Imports" and "exports" follow StatCan's labels (international); flows between provinces are a separate column shown in Advanced. Light fuel oil as "closest to home heating oil" is our assumption, not StatCan's label. Propane production is blank for Ontario and BC in 2025 (suppressed or incomplete months), so provinces sum to well under Canada. Not checked against an outside source such as CER or ECCC.
- **Lesson:** a StatCan WDS coordinate pull of 25-10-0029 returned values shifted onto the wrong fuel rows; the full-table CSV was correct. Use the CSV.

## Pipelines points map (added 2026-11-26)

Section "Pipelines: what flows, and where incidents happened", after "Where Canada's fuels come from".

- **Pipeline:** `Python/pipeline_etl.py` -> `districtenergy_json/pipelines.json` (542 KB: `meta`, columnar `incidents`, `flows`, `no_coords`). Downloads to `Python/pipeline_cache/` (gitignored). Both inputs are CER open data, Open Government Licence - Canada.
- **Incidents:** dataset fd17f08f, `pipeline-incidents-data.csv` (cp1252), 2,039 rows, 2008-2026, quarterly updates. Volume is numeric for 594; 252 "Not Provided" and 1,193 "Not Applicable" (no release) stay null. 362 rows carry the CER's own Significant flag. One record is in Maine (kept).
- **Flows:** dataset dc343c43, 19 per-pipeline files (gas daily, oil monthly), per-year means of throughput and capacity in 1000 m3/d with n. "Full" year = 360+ days or 12 months. Oil product rows summed per month; repeated capacity taken once. Dots sum same pipeline + key point + direction; different directions are never summed.
- **Gaps (quantified):** 98 groups, 35 without coordinates (Enbridge Mainline, Trans Mountain, Trans-Northern, Line 9, Southern Lights, Montreal, Westspur, Brunswick). Listed in the Advanced view, not placed, not geocoded by us.
- **Source fix:** Suffield key points have positive longitudes (+110.481, +110.797); sign flipped, recorded in `meta.coordinate_fixes`.
- **Decision (Simon, 2026-11-26): points now, lines later or never.** The CER publishes no open route geometry we could find. Its interactive map draws pipelines from a WMS at `services.gdmpipelines.com` (web map `c0f51bf0...`, layer "Regulated Pipelines (EN)", licence field "None"). Not an open dataset, so not used; same stance as NEEP (no direct calls to undocumented services). Open item: ask the CER (the ArcGIS item owner is their GIS staff) for a geometry file or permission.
- **Methane floor (added 2026-11-27).** Gas incidents with a numeric volume converted to CO2e under the map: CO2e = m3 x methane share x 0.68 kg/m3 x 28. Substances counted: Natural Gas - Sweet, Natural Gas - Sour, Fuel Gas (615 rows, 384 with volume, 70,472,150 m3); propane, NGL and mixed HVP excluded. All years: **1.21 Mt CO2e (1.07-1.30)**; largest incident INC2013-146 (16.5 million m3) = 23%; 231 incidents without volume not counted. **Assumptions are ours:** methane 80/90/97%, 0.68 kg/m3 (methane near 15 C, 1 atm), GWP 28 (IPCC AR5 100-yr). **Unresolved:** the CER dictionary says only "approximate volume released in cubic meters" (no standard-conditions statement), so the volume basis is unknown and the range does not cover it. The dictionary describes ~100 fields (recovered volume, pipe size, etc.) while the open CSV has 16, and its Significant definition is truncated in the source file. Not cross-checked against ECCC's inventory. Excludes burned gas, venting and small leaks (not incidents). Decision (Simon, 2026-11-27): estimate anyway, label it a floor; asking the CER first was the alternative.
- **Not used:** `apportionment.csv` (nominations, not flow); archived Trans Mountain file (overlaps the current file). Data dictionary calls gas capacity GJ/d but the column is 1000 m3/d; the column name is used.
- **Limits.** Federally regulated systems only (most local gas distribution is provincial). Key points are measurement locations, not the whole line, so never add them up. Gas and oil m3 are not energy-comparable, and incident release volumes mix gas and liquid m3. Annual means hide peaks; a few points average slightly above 100% of reported capacity (not explained by us). The national map has no zoom, so the dots cluster in the south.
- **Refresh:** `python -I Python/pipeline_etl.py --refresh`, then republish `pipelines.json` to gh-pages. CER updates incidents quarterly.

## Pipe cost card (added 2026-11-27)

Section 01, "What does the pipe cost?", after "One pipe, two pipes, or more". Hand-transcribed static HTML: no pipeline, no JSON. Two simple-view paragraphs, a comparison table, a supplier note and sources; an Advanced card holds the detail.

- **Mississauga.** FVB Energy, *City of Mississauga District Energy Study*, final 2023-03-22, Tables 17 and 19 (pp. 54-55). Text extracted with `pdftotext -layout` (the web-fetch tool only returned raw PDF bytes). Class D preliminary (-25%/+50%), 2022$, includes contractor OH&P, construction management, engineering and 15% contingency, excludes taxes. 10,840 trench metres, $57.6M, **$5,300/tm**; phases 770 m $2,651; 1,950 m $6,327; 2,920 m $7,182; 1,210 m $4,852; 2,570 m $5,416; 860 m $1,688; 560 m $1,818. The $/tm column was verified by dividing each total by its length (the PDF's table text was scrambled). 4-pipe trench (hot and chilled). Pipe: pre-insulated steel (CSA B51, 1,600 kPa, 95 C) with PEX or PE-RT optional on the hot side, HDPE for cooling. Piping is about 15% of the $381.8M total. Trenchless is stated at 3x or more of open trench. No manufacturer named; Appendix C is not in the published PDF (the file ends at Appendix A drawings).
- **Port Alberni.** Farallon Consultants Limited (S. Salter, P.Eng.), 2012-07-16, Appendix 3, pp. 58-59. 3,000 m: 880 m on roads at $300/m + 2,120 m off-road at $250/m = $794,000; piping and mechanical $1,443,000 (**about $481/m**, derived by us); connections and ETS $1,285,000; subtotal $3,522,000 (all verified by arithmetic). Basis is the City's trenching experience and comparable projects checked against RETScreen, not vendor quotes. 3-line system. Contingency 20%, engineering 15%, project management 10% are listed as inputs; whether the subtotal includes them is unconfirmed.
- **Supplier.** GF Urecon (GF Piping Systems), Canadian since 1969, plant in Calmar, AB (plant location from an older mining-industry listing, not reconfirmed); distributes Kingspan LOGSTOR rigid and flexible pipe (EN 253). No other Canadian maker found by one standard web search each; Perma-Pipe, Thermacor, Isoplus and Rehau not checked.
- **Decisions (Simon, 2026-11-27):** publish facts and links only, no table copies (judgment call, not legal clearance); name GF Urecon.
- **Limits.** What the data can't tell us: what Canadian projects paid, cost by pipe diameter. What we assumed: nothing added, not inflation-adjusted. What would change the answer: a measured cost from a built system, or Mississauga's pipe-size appendix. The two benchmarks differ in decade, setting and pipe count and are not put on one axis.
- **Not found:** Courtenay BC 2013 (Farallon, Table 6, "Capital Cost Summary, Distribution Piping"): the courtenay.ca PDF returned 404 on 2026-11-27. Alberta "district energy and cogen" paper and the DEA Technology Data catalogue were surfaced by search but not read.
- **Refresh:** none (static). Revisit if a Canadian built-system cost or a pipe-size breakdown becomes available.

## Outputs

| File | Size | Contents |
|---|---|---|
| `facilities.json` | 119 KB | 254 systems, full detail |
| `ief_context.json` | 222 KB | 3,390 non-DE IEF facilities — id, prov, lat/lon (3 dp), kind. Deliberately minimal: drawn at 0.28 opacity with pointer events off, so names/statuses would add ~40% for something never rendered |
| `aggregates.json` | 13 KB | every rollup, each with its own n |
| `canada_outline.json` | 155 KB | simplified province outlines |
| `report_2023.json` | 20 KB | copy of the curated report tables |
| `projects.json` | 9 KB | copy of the curated project list |
| `meta.json` | 3 KB | provenance, QA counts, file-vs-report delta |
| `funded_projects.json` | 630 KB | GMF + CIB project facts and links (see section above) |
| `fuel_trade.json` | 41 KB | StatCan production, imports, exports, interprovincial transfers by province, 5 fuels, PJ (see "Fuel supply and trade") |
| `pipelines.json` | 542 KB | CER incidents (2,039) and flow key points (63 mapped, 35 without coordinates) (see "Pipelines points map") |

---

## Refreshing

1. Re-download both workbooks from CEEDC's dashboard into
   `districtenergy/raw/` (the "Download data" links inside the viz).
2. `PYTHONIOENCODING=utf-8 python Python/district_energy_etl.py`
3. Check the QA block it prints — especially `hw_supply_suspect` and the
   file-vs-report deltas — before deploying.
4. `./deploy.sh`

**When CEEDC publishes a new edition**, the curated files need hand attention
too: `districtenergy/curated/report_2023.json` is transcribed from the 2023 PDF
and will not update itself, and `projects.json` carries a `reviewed` date that
should be bumped when the project list is re-checked.

---

## What this page deliberately does not claim

CEEDC is explicit that its data **cannot** answer whether district energy saves
energy or emissions versus the alternative: provincial aggregates for heating
and cooling supplied are hard to estimate, and many systems show energy per unit
floor area *above* provincial averages. The page reproduces that limitation
rather than working around it. **No efficiency comparison, no GHG-savings claim
and no cost-benefit number is derived from the CEEDC data.**

§01's pipe cost card (added 2026-11-27) follows the same rule: two feasibility-study benchmarks, each attributed and labelled modelled, none derived from CEEDC data.

§03 does discuss cost and emissions, but every figure there is attributed to an
outside source and labelled for what it is — one project's engineering estimate,
a technical-potential study, or an advocacy organization's own hedged wording.
Keep that separation if you edit it: the moment a CEEDC-derived number is used
to argue a savings case, the page is making a claim its own data explicitly
cannot support.

---

## Backlog

- **No OG card for `permits.html`** — noticed while adding the district energy
  card to `Python/build_og_images.py`. `assets/og/permits.png` does not exist,
  so the Permits Explorer has a broken social preview. Unrelated to this tool;
  one line in `CARDS` fixes it.
- **The inventory predates the NCR DES conversion.** Confederation Heights
  appears in the data as a 175 °C hot-water system; it is now part of the
  converted low-temperature NCR DES. That is a nice illustration of staleness,
  currently made in prose in section 08 — it could be drawn as a before/after on
  the generation chart.
- **Cross-link to the Heat Pump Explorer.** 67% of surveyed operators named heat
  pumps as their leading decarbonization option, and this suite has a whole tool
  about heat pump performance in cold climates. No link between them yet.
- **Cross-link to CEUD.** The 3.1% and 1.4% context figures come from CEUD,
  which is a tool in this suite; currently only mentioned in the sources panel.
