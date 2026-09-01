# Construction Tracker

`construction.html` — Canadian building permits, housing starts and construction
investment in one dashboard, at national, provincial and metro-area (CMA) level.
Full design/data plan: [archive/CONSTRUCTION_PLAN.md](archive/CONSTRUCTION_PLAN.md);
build log: [archive/CONSTRUCTION_STATUS.md](archive/CONSTRUCTION_STATUS.md).

**Live:** https://ottawavisuals.github.io/Energy/construction

## What it shows

For Canada, any province, or eight major CMAs: headline KPIs (permit value, starts,
under-construction stock, investment, each with y/y change), the permits → starts →
under-construction → completions pipeline, starts by dwelling type and by intended
market (homeowner / condo / rental), residential vs non-residential permit values
(nominal or constant $), per-capita provincial comparisons, and a sortable CMA table.
Advanced mode adds the rate cycle (starts vs BoC overnight + 5-yr mortgage), net new
supply (units created vs lost on permits), and construction employment vs backlog.

**"What it costs"** (added 2026-08-27): new construction vs renovation vs ownership
transfer costs, annual from 1961, nominal or constant $ (this replaced the old
trailing-12-month investment-by-work-type chart, which began in 2017 and was
nominal-only); and a renovation price index by project — heat pump, furnace, windows,
solar panels, roofing against the all-projects composite.

**"How green is what we build"** (added 2026-08-27): housing starts against the median
EnerGuide rating of new homes evaluated in the same province and year, reusing
`newhomes_json/` — the only section on the page that needs no fetch of its own; plus
a Greener Homes program card (grants, top-5 retrofit measure counts, per-province
totals).

Advanced mode also gains construction job vacancies and the average offered hourly
wage, alongside the existing employment-vs-backlog chart.

**CHBA Housing Market Index (added 2026-08-31):** a "Builder confidence" card
in the pipeline section — national single-family and multi-family HMI (0–100
sentiment scale, 50 = neutral), Q1 2021 through the current quarter, plus a
regional tile for Ontario/BC/Prairies/Atlantic views (CHBA's only regional
cuts; Quebec and the territories have no HMI region, so those views show the
national chart alone). Hand-transcribed, same cite-only pattern as Greener
Homes and CHBA Net Zero below — the HMI page's charts are static images with
no data file, and a check of their auto-generated alt text found it
unreliable (a mislabelled quarter on one chart, a swapped category on
another), so the card is built from the page's own prose "Key Findings" text
instead. Regional scores only go back to 2024 Q2 — CHBA reported them as
qualitative description, not index numbers, before that quarter. Multi-family
Atlantic Canada is never reported in any quarter checked. See
`Python/cited_figures.json`'s `chba_hmi` entry for the full quarter-by-quarter
figures and its documented gaps.

**CaGBC LEED &amp; Zero Carbon (added 2026-08-28):** a "Certified green buildings"
card — 9,952 LEED-family registrations (7,541 certified) and 461 certified
Zero Carbon Buildings, nationally, broken out by province. Built after
re-checking CaGBC's actual Terms and Conditions and Member Terms PDF: neither
addresses the project database, scraping, or data reuse, and the site-wide
"All rights reserved" footer is not a term attached to the export function.
The project-search tool at `leed.cagbc.org` needs **no sign-in** and its
export feature returns the full national list. This reverses the Tier-3
"not built" call on CaGBC — see `Python/cagbc_leed_etl.py`'s module docstring
for the full reasoning and the data-quality gates.

**Tier 3 (added 2026-08-27):** an *"Inside one city"* section (Vancouver and
Toronto permit desks — area breakdown, work-type split, and a city-vs-metro
cross-check), a *"Large buildings, measured"* card (Ontario EWRB energy
intensity by building type, Ontario/Toronto views only), and CHBA Net Zero
label counts alongside the Greener Homes figures.

**Tier 2 (added 2026-08-27):** a *"Did it sell?"* card (absorptions vs unsold
inventory, with a months-of-inventory mode) closing the pipeline past completions;
*"The cost of a building, by trade"* (BCPI by CSI division — envelope, windows and
doors, HVAC, electrical, concrete, wood — with a building-type picker); and a rental
vacancy column on the CMA table.

## Data pipeline

```
Python/construction_etl.py          # core: StatCan 34-10-0292 (permits),
                                    #   34-10-0293 (investment), 34-10-0151 +
                                    #   34-10-0154 (starts/UC/completions),
                                    #   34-10-0158 (SAAR), 34-10-0148 (market)
Python/construction_context_etl.py  # context: 18-10-0205 NHPI, 17-10-0009 pop,
                                    #   14-10-0355 construction employment,
                                    #   34-10-0145 5-yr mortgage, 18-10-0289 BCPI,
                                    #   Bank of Canada Valet (overnight rate),
                                    #   18-10-0286 renovation prices by project,
                                    #   36-10-0677 Housing Economic Account,
                                    #   14-10-0442 construction job vacancies
        → construction_json/        # one compact JSON per geography + context.json
                                    #   + meta.json (key scheme, units, dates)

Python/municipal_permits_etl.py     # Vancouver (Opendatasoft) + Toronto (CKAN)
                                    #   + Calgary (Socrata SoQL)
        → construction_json/municipal.json

Python/ewrb_etl.py                  # Ontario large-building energy disclosure
        → construction_json/ewrb.json       # XLSX per year, cached in ewrb_cache/

Python/cited_figures_verify.py      # publishes the CURATED cite-only figures
                                    #   from Python/cited_figures.json (NRCan
                                    #   Greener Homes, CHBA Net Zero) and
                                    #   re-checks each against its live page
        → construction_json/programs.json

        → construction_json/bcpi.json   # BCPI division detail, lazy-loaded by
                                        #   the page (18-10-0289); written by
                                        #   construction_context_etl.py

newhomes_json/<PROV>.json           # read directly by the page for the energy-
                                    #   performance section; produced by the New
                                    #   Homes Explorer pipeline, not by this one
```

Conventions: dollar series stored in **millions**; unit counts as **integers**;
unadjusted variants shipped only where no seasonally adjusted sibling exists.
Permits & investment history begins 2017–2018 (StatCan's redesigned programs);
CMHC series run from 1990. **Known data gap:** CMHC discontinued province-level
under-construction and completions after 2022 in every table (verified against
34-10-0151/0136/0139/0126); those series end Dec 2022 for provinces/Canada and
the page annotates this. Metro areas (34-10-0154) carry all pipeline stages to
the current month. Re-verified against 34-10-0136 and 34-10-0143 on **2026-08-27**
(still null for every province and for Canada through 2026-07, including the Toronto
and Montréal members inside 0143) — the caveat stands.

**Coverage rules for the 2026-08-27 additions.** These shape the UI, so they are not
footnotes:

- **18-10-0286** publishes its 45 project types for **CMAs only**. Provinces and the
  national composite carry the all-projects composite and nothing else, and Prince
  Edward Island has no member in the table at all. The renovation-price card therefore
  has its own metro picker rather than following the page geography. The ETL asks each
  geography for exactly what it publishes and counts what returns, so an empty key is
  never shipped.
- **36-10-0677** is provincial only, so metro views fall back to their province — stated
  on the card. It is fetched with `floor="1961-01"`; the default 1990 trim exists to keep
  the monthly CMHC files small and costs 29 years on a series only 65 points long.
- **14-10-0442** has no seasonally adjusted variant, so the card says to read the trend
  rather than quarter-to-quarter steps. It was chosen over the monthly SA 14-10-0406
  because that table is Canada-only and this page is driven by a geography selector.
- **18-10-0289 division detail** begins 2017-01 for *every* building type. The 1981
  history in that cube belongs to the non-residential composites only. Every division
  and geography shares one reference period, **2023 = 100** (verified: the 2023
  quarterly mean is 100.00 for the composite, wood, concrete and envelope alike), so
  the published index is plotted as published. An earlier draft re-based every line to
  2017 = 100; that was wrong, because it amplified whichever series started lowest —
  wood, off a 2017 lumber-cycle trough — and read as a claim about the trades rather
  than about their starting points.
- **34-10-0149 (absorptions) and 34-10-0127 (rental vacancy)** have **no provincial
  members** — they are CMA tables. The absorptions card therefore shows metro views
  directly, shows the all-CMA aggregate on a Canada view (labelled as such, since it
  excludes smaller centres and rural areas), and hides itself entirely on a provincial
  view. Vacancy is annual (October survey) while the columns beside it in the CMA
  table are monthly, which the table note states.
- **Vancouver's schema supports two extra panels the other cities can't (yet)**:
  processing time (`PermitElapsedDays`, permit-number assignment to issuance —
  median, not mean, since it's right-skewed: mean runs 40-70 days higher) by
  work type and by year, and applicant/contractor concentration (who files and
  who builds the most permits). The concentration panel is thresholded to 20+
  permits deliberately: `applicant` is "often the design professional or their
  firm" per the field's own description, and no private homeowner personally
  files dozens of permits, so the threshold keeps the published list to
  genuine repeat filers rather than surfacing an individual's name for a
  one-off renovation permit — nothing here is legally restricted (Open
  Government Licence - Vancouver permits reuse), this is a deliberate editorial
  choice. `buildingcontractor` is populated on only ~62% of permits (often not
  yet chosen at issuance), so its stats are scoped to permits naming one, with
  that coverage rate stated on the card. Toronto and Montreal do not have
  applicant/contractor fields at all.
- **Calgary's schema goes further still**: alongside the same processing-time
  and applicant/contractor-concentration panels as Vancouver (thresholded the
  same way, but with lower field coverage stated on the card — applicant
  ~66%, contractor ~60%, versus Vancouver's ~100%/~62%), Calgary has an
  `applieddate`→`issueddate`→`completeddate` chain Vancouver lacks, so it also
  gets a **time to build** panel (issuance to the permit's completed date —
  an administrative closure date that should track physical completion
  closely but may lag it) and a **$/unit, $/sqft and average unit size**
  table, scoped to residential new-construction permits with dwelling units:
  `totalsqft` is recorded on 0% of non-residential rows and only ~38% of all
  residential rows, but checked live within that exact scope it is ~91%
  populated, so $/sqft uses only the rows that have it while $/unit uses
  every qualifying row (`housingunits` is 100% populated). One fix caught
  before shipping: Calgary's dataset runs back to 1999, not 2017 like
  Vancouver's — its areas/work/concentration/processing queries were
  originally unfiltered, so they silently covered 27 years of history under
  a card that says "since 2017" everywhere else. All of them are now
  explicitly floored to 2017, mirroring Toronto's existing `d >= FLOOR` filter.
- **Edmonton (added 2026-09-01)** joins as a fourth city, re-evaluated after
  an earlier pass wrongly rejected it — its "General Building Permits"
  dataset is explicitly labelled the city's "Primary Dataset or View"
  (deduplicated, verified for accuracy, daily updates, clean back to 2009).
  What it genuinely can't support, checked live: **no concentration panel**
  — Edmonton deliberately excludes applicant/contractor names from this
  dataset as a stated privacy measure, not a data gap — and **no
  processing-time panel** — the UI column labelled "PERMIT_DATE" is actually
  the API's `issue_date` field, and "REPORT_PERMIT_DATE" is actually
  `permit_date`; checked live, the two are identical on every row (143,693 of
  143,693 since 2017), so there is no application-to-issuance interval to
  measure. It does get a **time to build** panel (permit date to
  `occupancy_granted_date`) and the same **$/unit, $/sqft and average unit
  size** table as Calgary, scoped to residential new construction — but with
  a real coverage caveat the card states: Edmonton only began systematically
  recording occupancy dates for residential permits finalized on/after
  2022-01-01 (non-residential: 2024-01-01), so the build-time panel covers a
  recent subset (22,543 of 45,374 residential-new permits since 2017 have an
  occupancy date), not the full history the rest of the card uses. Its
  `occupancy_granted_date` is stored as TEXT rather than a proper
  `calendar_date`, so Socrata's `date_diff_d` 400s on it — those rows are
  pulled raw and diffed client-side in Python instead. Its `work_type` field
  also carries overlapping labels for the same concept (`(01) New` and
  `(01) Building - New` both mean new construction), matched explicitly
  wherever new-construction scoping matters rather than picking one.
- **Mississauga (added 2026-09-01)** joins as a fifth city, on a different
  platform than the rest — an Esri ArcGIS FeatureServer, not Socrata. Its
  schema is the richest of any city here: a real STATUS field and three
  genuinely distinct dates (application/issue/complete — checked live, only
  488 of 34,615 rows share an application and issue date, unlike Edmonton's
  identical pair), so it's the only city with **both** a processing-time
  panel and a build-time panel. No concentration panel — this schema never
  had an applicant/contractor field at all, unlike Edmonton's deliberate
  exclusion. Unlike the other four cities, **Mississauga is not its own
  StatCan CMA** — it's part of the Toronto CMA, so it can't be a standalone
  selectable geo without breaking every StatCan-driven section of the page
  for a "Mississauga" geo that doesn't exist in StatCan's tables. Instead,
  "Inside one city" now supports more than one city per geo: selecting
  Toronto renders both the City of Toronto's card and the City of
  Mississauga's card together (`renderMunicipal()` matches every city whose
  own key *or* `cma` field equals the selected geo, and generates a
  full card block per match with ids suffixed by city key). Two data-quality
  finds shaped its unit-economics panel. **(1)** `APPL_AREA` is recorded in
  **square metres**, per its own field description — every other city's
  floor-area field on this page is sqft, and treating it the same way
  produced a physically impossible ~100 sqft "average unit size" before the
  conversion was added. **(2)** Scoping to every RESIDENTIAL permit with
  units added (no further filter) mixes new subdivisions with
  ALTERATION/ADDITION permits that merely add a secondary suite — checked
  live, that broader population's $/sqft came out over $2,000, another
  impossibility. Restricting to `SCOPE = 'NEW BUILDING'` fixed both at once
  (median $223-253/sqft for 2018-2023). The resulting 2024-2026 jump to a
  $2.7M+ median $/unit was checked row-by-row, not assumed: a real run of
  ~$7-10M custom detached-home permits (990-1,143 sqm each, individually
  verified), not an error — with only ~140-190 qualifying permits a year, a
  handful of genuine luxury builds can swing the median, and the card says
  so.
- **Ottawa (added 2026-09-01)** joins as a sixth city, the only one with **no
  API at all** — 15 annual XLSX workbooks (2011–present) on open.ottawa.ca,
  discovered live from the DCAT feed (not a hardcoded item list, so a newly
  published year is picked up automatically) and cached locally like
  `ewrb_etl.py`'s XLSX pattern. An earlier evaluation had ruled Ottawa out
  entirely; re-checked live this session because the earlier Edmonton
  rejection had already turned out to be wrong once, and it was — the data
  itself is rich (real contractor names, application type, ward and
  community), just not API-reachable. Real per-permit **contractor** names
  (55.7% of rows; the rest are `CONTRACTOR UNKNOWN`/`***CONTRACTOR***`
  placeholders the city itself uses when the contractor is the property
  owner) give a genuine concentration panel — no applicant field exists, so
  only half of that card's usual pair renders (the page now shows each half
  independently rather than assuming both always exist). No processing-time
  or build-time panel: only one date (issuance) exists in this data. Two
  schema eras, detected **per sheet**, not per year: 2011–2025 files have
  `CONTRACTOR`/`APPL. TYPE` columns and area already in square feet; the
  current in-progress 2026 file drops both and reports area in square
  metres (converted). A live-caught bug reshaped the parsing strategy
  entirely: an early version tried to pick "the" full-year detail sheet per
  file by name, and broke silently on the 2024–2025 combined workbook, whose
  named rollup sheet turned out to be **stale** — it only covers Jan–Aug
  2024, while Sep 2024 through Dec 2025 exist only in that file's monthly
  sheets. Fixed by reading and parsing *every* sheet in every file
  unconditionally (a pivot "Summary" sheet, or any sheet with no real
  per-permit data, correctly parses to nothing on its own — no column named
  `WARD` to build a header from) and de-duplicating by permit number, rather
  than trying to guess which single sheet is authoritative. A second finding
  shaped the unit-economics panel's caveat rather than its logic: checked
  live, a large share of the declared `VALUE` field for residential permits
  clusters tightly on a handful of near-identical $/sqft rates (hundreds of
  permits within cents of $167.22/sqft or $185.87/sqft in a single year, not
  seen on office/retail/institutional permits in the same file) — consistent
  with a standard municipal fee-assessment schedule rather than each
  builder's independently reported project cost, so the card says $/sqft
  here likely tracks Ottawa's own rate table more than the real market. See
  `Python/municipal_permits_etl.py`'s module docstring for the full writeup
  on all six cities.
- **Municipal permits are city boundaries, not CMAs.** The City of Vancouver is a
  fraction of its CMA and the City of Toronto excludes Peel, York, Durham and
  Halton, so these series cannot be reconciled with the StatCan CMA figures. The
  card says so and states the ratio (Vancouver ≈ 40% of its metro's permit value;
  Toronto ≈ 50% of its metro's dwelling units created) rather than implying the
  lines should meet. **Calgary is the exception**: per the 2021 Census the City of
  Calgary (1,306,784) is ≈88% of the Calgary CMA (1,481,806, which also covers
  Airdrie, Cochrane, Chestermere and Rocky View County), so its series tracks the
  CMA far more closely — still not identically, and the card states the live
  ratio rather than assuming it. Three cities, deliberately: Montreal (CKAN,
  `datastore_search_sql` works) has no cost or status field per permit — cost
  only exists pre-aggregated by year/borough — and two boroughs (Lachine,
  Saint-Léonard) are currently missing from an in-progress system migration.
  Edmonton (Socrata) has several overlapping/redundant permit datasets needing
  reconciliation first and no status or postal/ward field. Ottawa publishes
  permits only as ~10+ separate annual `.xlsx` bulk-download workbooks — no API,
  no server-side aggregation (an earlier pass of this evaluation wrongly assumed
  an ArcGIS feature layer existed). Calgary cleared the bar the other three
  didn't: a real status field, a clean cost field (~92-95% populated since
  2016, no Toronto-style placeholder corruption), dwelling units, and daily
  refresh via Socrata SoQL server-side aggregation.
- **Toronto's `EST_CONST_COST` is placeholder text on ~45% of rows** (the literal
  string `DO NOT UPDATE OR DELETE THIS INFO FIELD`). Its permit *counts* and
  *dwelling-unit* series are sound; its dollar totals are an undercount of unknown
  size. The cross-check therefore compares Toronto on dwelling units created and
  Vancouver on permit value — each city on what its data can actually support.
- **Toronto needs BOTH permit sets.** "Cleared" means closed, so on its own it is
  badly right-censored: the final month showed 74 permits against ~375 two months
  earlier. Active + cleared together give every permit issued, and the series then
  runs at a steady ~3,000/month.
- **Ontario EWRB is self-reported and published uncleansed**, which the province
  states plainly. 27,685 of 30,693 rows across 2018–2024 are usable; 2,776 carry no
  weather-normalized intensity, 195 report zero or negative, and 37 exceed 20 GJ/m²
  (an order of magnitude beyond any real building, so a reporting error rather than
  an inefficient one). Types thinner than 20 rows in a year are suppressed. The
  Data Quality Checker flag records whether a reporter *ran* a tool, not whether the
  data passed, so it is reported and never used as a filter. The reporting
  population grows from 534 buildings in 2018 to 6,739 in 2024, so year-to-year
  movement in the medians is partly a changing sample.
- **The provincial pipeline gap was re-tested against CMHC's own portal**
  (2026-08-27). Requesting Ontario under-construction for July 2026 from HMIP's
  `ExportTable` endpoint returns *"This data series is now archived."*, while the
  same request for December 2022 returns real data (162,813 units) and Ontario
  *starts* for July 2026 returns real data. So the gap is a genuine CMHC
  discontinuation, not a StatCan publication decision — the earlier hypothesis that
  HMIP might still carry it is now disproved, and the caveat stays.
- **Greener Homes and CHBA figures are hand-transcribed, not scraped.** NRCan publishes no data
  file, and on the progress page each province's *name follows its numbers* in document
  order — a positional parser pairs them off by one and silently mis-assigns every
  province. So the figures live in `Python/cited_figures.json` on `main`, and
  `cited_figures_verify.py` asserts each one still appears verbatim on its live page
  before publishing. It runs `continue-on-error` in the monthly workflow: when a
  publisher posts an update the check should raise a warning to act on, not take the
  data refresh down with it. **No CaGBC count is published** — CaGBC shows no running
  total on its public pages and its project database is behind a sign-in, so there is
  no figure that could be verified this way. Getting one means asking CaGBC.
- **EnerGuide new-home ratings** cover only the evaluated share of new construction.
  Years with fewer than 30 evaluations are suppressed, sections with fewer than three
  usable years are hidden entirely (Quebec, which has two), and the card states that the
  two panels are not a like-for-like ratio. The note reports the latest year's median and
  its sample size rather than a first-to-last change, because these medians are not
  monotonic and an endpoint delta would imply a trend the data does not show.

## Regenerating / refresh

```bash
cd Python
python construction_etl.py            # cached downloads; --refresh to force
python construction_context_etl.py    # writes context.json AND bcpi.json
python municipal_permits_etl.py       # writes municipal.json (live portals)
python ewrb_etl.py                    # writes ewrb.json; --refresh re-downloads
python cited_figures_verify.py        # writes programs.json; exits 1 if stale
python cagbc_leed_etl.py              # writes cagbc.json from a MANUAL export,
                                      #   project_profile.csv at the repo root
                                      #   (gitignored; re-export by hand from
                                      #   leed.cagbc.org — no API, no sign-in)
```

`.github/workflows/construction-refresh.yml` does this monthly (20th, 14:00 UTC)
and commits `construction_json/` only when all fetches succeed and data changed.
