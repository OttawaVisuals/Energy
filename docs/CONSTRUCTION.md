# Construction Tracker

2026-11-12: **Calgary project timelines** and a dedicated **construction length page**
(`buildtime.html`): building permit, inspections and HVAC / plumbing / electrical / gas permits
on one clock for 2018-2026 new construction, with a year selector; **Winnipeg** added the same day (2011-2018). See
[Calgary project timelines](#calgary-project-timelines-building--trade-permits-on-one-clock).

2026-11-06: **CMHC vs city permit records** added under "How long it takes to build":
new-home build time from six cities' permits (new residential only, by completion year,
unit-weighted) beside CMHC's, plus a house-size / apartment-building-size chart. See
[City permit records beside CMHC](#city-permit-records-beside-cmhc-new-home-build-time-and-size).

2026-11-05: **"How long it takes to build"** card added (local, not yet published).
It shows CMHC's average construction time in months, monthly since 1990, with
dropdowns for geography (Canada, provinces, all 42 CMAs) and breakdown (dwelling type or
intended market), and a Monthly / 12-month toggle. See
[How long it takes to build](#how-long-it-takes-to-build-construction-time) below.

2026-10-31: shared artwork/header and chart polish, with narrow-screen chart
grids and KPI cards; see [Visual polish](VISUAL_POLISH.md). Publication pending.

2026-10-30: matching tab icon and social preview added; see [branding](BRANDING.md).

2026-10-30: approved landing-page icon option 1 uses a crane, buildings and a
schematic chart (`assets/icons/construction.png`). Bars convey tracking, not
actual values or a growth claim. Applied locally; Published 2026-10-30.

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

**Permits Explorer (added 2026-09-02):** the municipal permit data on this page
is the *summary* -- nine cities floored at 2017 so they stay comparable with each
other and with the metro figures above. The record itself now lives on its own
page, [`permits.html`](PERMITS.md): each city back to its own first month
(Montreal 1990, Calgary 1999-06), a 0.004-degree density map of where building
actually happens, category-by-year matrices, a filer word cloud, and Toronto's
approval/build intervals. "Inside one city" is **no longer advanced-only and no
longer renders as nothing** when the selected geography has no matching permit
desk; it always shows a cross-reference card to the full page.

## How long it takes to build (construction time)

Added 2026-11-05. First series on the page that comes from CMHC's Housing Market
Information Portal (HMIP) rather than StatCan: no StatCan table carries it (checked
2026-11-05, see [HMIP_CATALOGUE.md](HMIP_CATALOGUE.md)).

**Plain language.** It shows how many months new homes took from the foundation being
poured to being finished, for homes finished each month since 1990. Across Canada's metro
areas, single-detached houses went from about 5 months (1990) to about 9 (2025), and
apartment buildings from about 11 to about 23. The "all homes" line rose faster (about 8 →
19), partly because the mix shifted toward apartments.

**Controls.** Geography dropdown: Canada, 10 provinces and 42 CMAs, grouped by province.
It defaults to the page's own geography selector and resets when that changes. Breakdown
dropdown: dwelling type (single, semi, row, apartment & other, all) or intended market
(homeowner, condo, rental, co-op, all). Toggle: Monthly or 12-month average (default).

**Method (advanced).**
- Source tables: HMIP "Historical Time Periods" view of *Average Length of Construction
  (in months)* (TableId 1.2.7 by dwelling type, 1.2.8 by intended market) and *Completions*
  (same breakdowns). Every table is pulled at **"For: Census Metropolitan Areas"**
  (`MetType=Cmas` on Canada and province pages; CMA pages take no `MetType` and return
  HTTP 500 if given one).
- Definition: CMHC publishes none for this measure. We read it as the mean months from
  *start* (footings poured for the whole structure) to *completion* (all work done, or all
  but 10%) over units completed in the month. Unverified.
- 12-month average = Σ(months_t × completions_t) ÷ Σ completions_t over the trailing 12
  months, so it's completion-weighted, not a plain average of averages.
- Small-n rule: a point needs ≥ 20 completions (that month, or in the 12-month window),
  and a 12-month point needs ≥ 6 months with data; otherwise it is dropped and shows as a
  gap. The hover tip shows n for each point.
- **0.0 = not recorded.** CMHC shows 0.0 months for all of 1992–1993 in every geography,
  plus scattered CMA months (Toronto to 1999, Edmonton to 2001, Ottawa as late as 2025),
  often with hundreds of completions. That's 8,660 cells across 51 geographies, nulled
  in the ETL and counted per series in `index.json` (`zero_months_nulled`). Precedent:
  the EnerGuide `ERSRating=0` placeholder. **CMHC's province, Canada and "All" figures
  still average those zeros in.** Example: Ontario rental, Dec 2021, is published at
  15.9 months vs 17.6 from its CMAs without Hamilton's 0.0. The ETL flags 230 months
  across 49 series where "All" sits below every one of its non-zero categories. We show
  CMHC's figures as published rather than recomputing them.
- **Shorter or broken histories:** Brantford and Sherbrooke start 2007-01; Montréal and
  London have rows for 1990–1997 but no values (start 1998-01). Windsor has no data
  2023-01 to 2025-06 (CMHC notice), and its history page opens with no table, so the ETL
  re-requests it with an explicit 1990..latest range from `/TableMapChart/Table`
  (logged in `index.json` → `ranged_fallbacks`).
- Annual figures in the plain-language text: the same completion-weighted average over
  a calendar year, Canada (CMAs), from the 2026-11-05 pull.

**Validation (2026-11-05).** Toronto completions from HMIP equal StatCan 34-10-0154
completions in all 438 overlapping months. All 53 geographies pass the ETL's
month-continuity and completions-sum checks (0 mismatches). The "All within its categories"
check flags 230 months, all explained by CMHC's 0.0 placeholders (above).

**Limitations.**
- *What the data can't tell us:* rural areas and towns. Province and Canada values average
  their CMAs only, and **PEI has no CMA, so it has no data**. CMHC has collected completions
  only in CMAs since 2023-01-01. No reliability codes are published, and single months for
  small categories swing a lot.
- *Shorter histories:* see above. Earlier months are left empty (a gap, not zeros), and
  the card's note says when a CMA's history starts.
- *What we assumed:* the start-to-completion reading above. HMIP's "Ottawa" is the
  Ontario part of Ottawa-Gatineau (page code `ottawa_on`) and "Gatineau" the Quebec part
  (`ottawa_qc`). The combined Ottawa-Gatineau view shows the Ontario part.
- *What would change the answer:* a CMHC definition note, a different coverage choice
  (CMAs + 50k CAs adds PEI via Charlottetown), or a different small-n threshold.

**Refresh.** `Python/construction_time_etl.py` reads public HMIP HTML pages only (1 req/s).
The server takes ~1.5 min per geography, so a full pull runs ~80 min. Since 2026-11-05 it
runs monthly in `construction-refresh.yml` as a **non-blocking, 150-minute-capped step**
after the EWRB ETL. The script writes to a temp folder and swaps it into
`construction_json/ctime/` only when all geographies succeed. It also refuses to publish if
it finds fewer geographies than last time (a sign HMIP's layout changed). On any failure,
last month's files (seeded from gh-pages) stay in place and the rest of the refresh still
publishes. **Caveat:** the step sits after the municipal permits step, which failed the
whole job on 2026-09-20 and 2026-10-20 (Calgary portal read timeout), so until that's fixed
neither this step nor the publish runs.

## City permit records beside CMHC (new-home build time and size)

2026-11-06. When the "How long it takes to build" geography is a CMA containing a city with
permit completion dates, two more charts appear under the CMHC chart: **CMHC vs the city's
own permit records** (one dwelling type at a time, Median / Average toggle) and **Are new
homes getting bigger?** (house floor area, or apartment building size). Cities: Calgary,
Edmonton, Winnipeg, Halifax, Toronto and Mississauga (the last two both inside the Toronto
CMA, with a city picker). Vancouver, Ottawa and Montréal publish no completion date.

**Plain language.** The city line uses each city's building permits for new homes, from the
day the permit was issued to the day the city closed it (Edmonton: occupancy granted). CMHC
times foundation to finished home. The two clocks differ, so read them for whether they move
together. CMHC publishes no floor area, so size comes from the permits.

**Why a new series, not the existing per-city build-time panels.** Those (from
`municipal_permits_etl.py`) mix every permit type, group by the year *issued* (so recent
years hold only fast projects) and are unweighted. The new series is new residential
construction only, grouped by **completion year** like CMHC, and **weighted by dwelling
units** like CMHC (a 200-unit building counts 200 times). The old panels now link to it.

**Method.**
- *Scope per city* (checked live 2026-11-06): Calgary `workclass='New'`, residential, units
  > 0, `statuscurrent='Completed'`, end `completeddate`. Edmonton new work types, units > 0,
  end `occupancy_granted_date`. Winnipeg `work_type='Construct New'`, units > 0,
  `status='Closed'`, end `final_date`. Mississauga `SCOPE='NEW BUILDING'`, units > 0, `STATUS`
  all-inspections-signed-off, end `COMPLETE_DATE`. Halifax new residential building, net units
  > 0, `Permit_Status='Completed'`, end `Completed_Date`. Toronto cleared permits, `New
  Houses` / `New Building`, units created > 0, `STATUS='Closed'`, end `COMPLETED_DATE`.
- *Status filter:* Calgary, Halifax and Toronto also stamp an end date on cancelled,
  expired, withdrawn or dormant permits (1,990 / 303 / 1,446). Those are excluded and counted.
  Winnipeg's 1,704 "closed with an incomplete inspection process" are excluded too.
- *Dwelling types* map onto CMHC's four. Duplexes, multiplexes and stacked townhouses go to
  apartment, as CMHC classes them. Homes in mixed-use buildings count as apartments: Toronto
  has 226 such permits holding 61,421 homes, more than its apartment-building permits.
  Suites, backyard houses and non-residential types are left out and counted.
- *Statistic:* months = days ÷ 30.4375. The unit-weighted median is the default, because
  permit files have long administrative tails. The unit-weighted average is CMHC's own
  statistic and sits on the toggle. CMHC's line is its monthly CMA figure, averaged over the
  calendar year and weighted by completions (≥ 20 completions, ≥ 6 months with data).
- *Small n:* cells with < 20 permits keep their count but show no value.
- *"All types" guard:* an "all" cell shows only when every type holding ≥ 10% of that year's
  homes is publishable on its own. Without it, Mississauga's 2026 "all" read 47 months off 2
  apartment permits carrying hundreds of homes.
- *First year shown* = first full year of issue records + the 95th-percentile build time
  (whole years, over files closed within 5 years). Before that only fast builds could
  appear. Edmonton starts at 2022, when it began recording occupancy dates.
- *Clean-up years:* a year where more than a third of closures came over 5 years after issue
  is hidden, with its count and share kept in the table. Those closures date paperwork, not
  builds. Toronto: 53% of 2025 single-detached closures were 5+ years old (2017–2024: 7–25%),
  and 84–93% of 2024–2026 apartment closures. Toronto singles hide 2025–26 and apartments
  2024–26. Winnipeg's row homes hide 2026. Size values are hidden in the same years.
- *Size:* median floor area per single-detached home (Calgary `totalsqft`, Edmonton
  `floor_area`, Mississauga `APPL_AREA` m², Toronto `RESIDENTIAL` m²; 400–15,000 sq ft kept).
  Toronto's field is read as gross floor area from its magnitudes, which is an inference.
  Halifax records only the footprint and Winnipeg no area, so neither has a house-size chart.
  Apartment building size is the median homes per apartment permit with 5+ homes. The floor
  keeps Toronto's one-unit stacked-townhouse permits from reading as one-home "buildings".

**What it shows (2025, single-detached, permit median vs CMHC CMA average).** Calgary 6.6 vs
7.5 months and Edmonton 7.2 vs 7.1 months: the city clock tracks CMHC closely. Halifax 11.9
vs 8.8, Winnipeg 15.0 vs 8.4 and Mississauga 24.3 vs CMHC Toronto's 13.6 run much longer,
because those permits close at a final inspection that can come long after move-in. Calgary
single-detached homes grew from a median 1,766 sq ft (2003 completions) to 2,115 (2025),
while build time stayed around 6–9 months.

**Limitations.**
- *Can't tell us:* when the home was physically finished in cities whose permits close late,
  or why the gap to CMHC differs by city (inspection practice, not construction, is the
  likeliest reason, but the data can't separate them).
- *Assumed:* CMHC's dwelling-type definitions apply to each city's labels as mapped; Toronto's
  `RESIDENTIAL` is gross floor area; a city is a fair stand-in for part of its CMA (Toronto and
  Mississauga are two pieces of one CMA).
- *Would change the answer:* a city publishing an occupancy date (as Edmonton does), a
  different clean-up threshold, or using permit issue years instead of completion years.

**Refresh.** `Python/city_build_time_etl.py` → `construction_json/city_build.json` (17 KB).
Runs monthly in `construction-refresh.yml` as a **non-blocking, 30-minute-capped step** after
the construction-time step (about 5 minutes; Calgary pages ~157k rows). A city that fails
keeps its previous block, with its own older `retrieved` date, and the script exits 1. Same
Calgary-timeout caveat as above until that fix lands.

## Calgary project timelines (building + trade permits on one clock)

2026-11-12. First look at **how long each part of a build runs**, not just the whole thing:
the building permit, its inspections and the separate HVAC, plumbing, electrical and gas
permits, all placed on one timeline (day 0 = building permit issued). Calgary only, new
construction permitted **2018 to 2026** (first published for 2022 only; extended to every
year the data allows the same day). Shown on `buildtime.html`, with a year selector.

**Plain language.** For large residential buildings (3+ homes) permitted 2019 to 2024, the
median project took about 372 days from permit to close. The HVAC permits run about 148
days of that, roughly 45%, starting around day 174, after the framing inspection (median
day 200). Plumbing starts first (day 29), then electrical (69), gas (147) and HVAC last.
Single houses almost never show their trade permits in the open data, so they can't be timed
the same way.

| Building class (2019-2024, new) | Buildings | With all 4 trades closed | Build (days) | HVAC span (days) | HVAC share |
|---|---|---|---|---|---|
| Residential 3+ homes (MURB) | 2,697 | 2,254 | 372 | 148 | 45% |
| Residential 2 homes | 97 | 70 | 410 | 190 | 52% |
| Residential 1 home or blank | 47,127 | 336 | 225 | 124 | 65% |
| Non-residential | 865 | 301 | 417 | 180 | 46% |

Medians are per measure, so they do not add up to one real project's schedule. The 1-home
row rests on 336 of 47,127 buildings (0.7%) and should not be read as typical houses.

**By year (MURB).** Build length (days) / HVAC share by year the building permit was issued:
2018 365 / 43%, 2019 341 / 46%, 2020 320 / 50%, 2021 383 / 41%, 2022 432 / 36%, 2023 363 /
46%, 2024 373 / 49%, 2025 312 / 54%, 2026 179 / 63%. The HVAC share moves 36% to 54% across
2019-2025 with no steady trend; 2018, 2025 and 2026 are flagged (below).

**Why the default is 2019-2024.** Calgary's trade-permit datasets start between 2017-10 and
2018-08 (HVAC 2018-05-31), so 2018 trade coverage is incomplete (MURB HVAC match 46%, against
80-97% from 2019 on). 2025 and 2026 are **right-censored**: only buildings already completed
are counted, so slow builds are missing and the lengths read short (2026 median 179 days). A
single year can still be picked on the page, with those notes shown.

**Why Calgary first.** It is the one city found (checked live 2026-11-12) that publishes
trade permits as separate datasets *and* building-inspection results keyed to the building
permit. Winnipeg is added below. Toronto's Mechanical(MS) and Plumbing(PS) permits are
separate records, but 95% of a 3,000-row Mechanical sample were "Building Permit
Related(MS)", which close with the building permit, so they give no independent trade
length. Edmonton, Vancouver, Ottawa, Halifax and Mississauga were not checked.

**Method.** `Python/calgary_project_timelines.py` → `construction_json/calgary_project_timelines.json`.
- *Buildings:* `c2es-76ed` Building Permits, `workclass='New'`, `statuscurrent='Completed'`,
  issued 2018 to 2026. Class from `housingunits` and `permitclassmapped`.
- *Trades:* `cdrc-r4u8` (HVAC; has Rough / Final inspection dates), `5pvv-k7hn` (plumbing),
  `vxgy-id5s` (electrical), `tg24-jt7r` (gas), `workclassgroup='New'`.
- *Inspections:* `8ced-xbvn`, joined on `externalfilenum` = building `permitnum`
  (foundation, framing, final, occupancy; first and last date per type).
- *Join of trade to building:* by address. The trade permit's `originaladdress` against the
  building's `originaladdress` and every address in `locationaddresses`, issue dates within
  +-450 days; nearest wins. `locationaddresses` matters: new-construction HVAC match went from
  16% to 67% once it was used, because the building permit often carries a lot or parcel
  address in `originaladdress`.
- *Per building and trade:* permits matched, first issued day, last closed day, span = last
  closed - first issued across all matched permits (a MURB has a median of about 5 HVAC permits).
- *Summary:* per period (2019-2024 and each single year) and class, only buildings with all
  four trades matched and closed. A trade missing from the open data is a gap, not zero days.
  Cells under 10 buildings are suppressed.
- *File:* 2.4 MB. Only the 3,936 buildings with all four trades closed are listed (for the
  page's "one building" view); the other 67,396 are counted in `coverage_pct` and `summary`
  but not listed.

**Gates and drops (all in the file's `meta`).** 71,343 building permits, 11 dropped for
missing or inverted dates. Trade permits matched to a building: HVAC 20,549 of 30,540,
plumbing 48,804 of 73,194, electrical 127,894 of 207,610, gas 63,095 of 98,608 (the rest
belong to buildings outside the set, e.g. alterations). Ambiguous matches (several buildings
qualified; nearest chosen): 1,547 / 4,574 / 20,949 / 7,159. 427 buildings have a trade
milestone over 1,500 days from day 0 (kept). 6,765 of 71,332 buildings have no inspection
rows. Match counts from the first 2022-only run differ slightly from the all-years run
(2022 MURB all-four 401 then, 392 now) because more candidate buildings are in play.

**Early-flagged buildings.** A trade permit issued more than 60 days before the building
permit, or an inspection dated before its issue date, suggests a re-issued or amended permit
(e.g. `BP2018-...` issued in 2022). They stay in; 395 of 2,254 MURBs are flagged. Without
them the MURB build is 381 days and the HVAC share 41.9%, so the finding is not sensitive
to them.

**Limitations.**
- *Can't tell us:* when work was physically done. Calgary's inspection dates are when the
  city inspected; closing dates are administrative (an HVAC permit often closes long after
  the building does, so an HVAC span can even exceed the build). There is no insulation /
  air-barrier / envelope milestone in the data.
- *Can't tell us (coverage):* single houses. Only about 3% / 3% / 26% / 15% have HVAC /
  plumbing / electrical / gas permits matched in the open data, so houses are not
  representable; the reason is unknown (lot-address filing, blanket permits or dataset gaps
  are possible, untested).
- *Assumed:* the address join is right (not hand-checked); +-450 days is our choice, not
  validated; buildings with all four trades resemble those without (they may not).
- *Would change the answer:* a city key linking trade permits to building permits, another
  city publishing the same structure, or the 2025-2026 buildings finishing.

**Refresh.** Manual for now (not in any workflow). A few minutes for 2022 alone from a cold
cache; the 2018-2026 run (about 71k buildings, 400k trade permits, about 180 inspection
queries) took several minutes (not timed). Raw pages cache in
`Python/calgary_timeline_cache/` (gitignored, scratch); a rerun from cache takes under 2
minutes. Output is gitignored on `main` and published to `gh-pages` with the other data trees.

## Winnipeg project timelines (added 2026-11-12)

Same idea as Calgary, on `buildtime.html` (city selector). `Python/winnipeg_project_timelines.py`
-> `construction_json/winnipeg_project_timelines.json` (5.7 MB; 14,913 listed buildings).

**What Winnipeg has.** Building permits `it4w-cpf4` (`work_type='Construct New'`, closed with a
final date) and Trade Permits `urbd-qygv` (378,656 rows 2010-2026; electrical and plumbing for
houses and commercial, mechanical for commercial only). **No inspection dates, no gas permits,
no HVAC permits for houses.** So houses show plumbing and electrical only; multi-residential
and non-residential also show mechanical.

**Join.** Street address (number + name + type), +-450 days, nearest wins (ambiguous counted).
Two filters were needed after the first test: (1) accessory structures (garages, sheds) and
other residential types are excluded from the buildings (20,664 counted); (2) trade permits are
limited to **new-build work types** (`SFD New`, `Plumb New SFD`, `Wire New Bldg`...). Without (2)
electrical spans were about 300 days on a 520-day build because later work at the same address
(additional wiring, air conditioner, rewire) was being matched.

**Findings (issued 2011-2018, median).** Single-detached 484 days permit length, electrical span
254 days (68% share; plumbing alongside); with attached garage 575 / 279; duplex 515 / 231.
Multi-residential 531 days, mechanical 332 days (68%), 209 of 301 buildings have every trade
closed. Non-residential 348 days, mechanical 225 (269 of 683). Plumbing and electrical coverage
is 97-99% for houses; mechanical 0% for houses by design of the data, 79% / 61% for multi-
residential / non-residential.

**Why 2011-2018 only.** The open data has a final date for 91-97% of electrical and plumbing
permits issued 2010-2018, **82% for 2019, 40% for 2020 and about 1% from 2021**
(`meta.trade_closure_pct_by_year`). Later buildings cannot be timed and the few that can are
not typical, so the default is 2011-2018 and every later year is selectable with a note. We
do not know whether the city stopped recording or stopped publishing the dates.

**Row housing is not summarised.** Several building permits share one street address (a permit
per unit, probably) and a trade permit attaches to only one of them; only 21% of the 2,701
row-housing buildings show any trade although 98.9% of their addresses have trade permits at
some date. Coverage is shown, durations are suppressed. A grouping-by-address approach could
fix it; not done.

**Limitations.** *Can't tell us:* when work was physically done (closing is administrative;
no inspections); envelope work. *Assumed:* the address join is right (not hand-checked);
+-450 days; buildings with every trade resemble those without. *Would change the answer:* a
city key between trade and building permits, final dates for post-2019 trade permits, or
per-unit grouping for row housing. Licence: building permits Open Government Licence –
Winnipeg; trade permits Canada Open Government Licence (dataset metadata). Refresh: manual;
raw pages cache in `Python/winnipeg_timeline_cache/` (gitignored, scratch).

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

Python/construction_time_etl.py     # CMHC HMIP (not StatCan): average length
                                    #   of construction + completions, monthly
                                    #   1990-01.., by dwelling type and by
                                    #   intended market, Canada + 10 provinces
                                    #   + 42 CMAs, CMA-only coverage (MetType=Cmas)
        → construction_json/ctime/  # index.json + one <code>.json per geography

Python/city_build_time_etl.py       # six city permit desks: new-home build
                                    #   time by completion year, unit-weighted,
                                    #   + house floor area / apt building size
        → construction_json/city_build.json

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
  that coverage rate stated on the card. Toronto has a `BUILDER_NAME` field, but checked live on a
  6,000-row sample it is populated on only **2.2%** of rows and is mostly
  individuals rather than firms, so it supports no concentration panel either;
  Montreal has no such field at all.
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
  here likely tracks Ottawa's own rate table more than the real market.
- **Montreal (added 2026-09-01)** joins as a seventh city, on the field list
  the user gave directly from `donnees.montreal.ca` (date_debut, date_emission,
  code_type_base_demande, nb_logements, longitude/latitude). CKAN
  `datastore_search_sql` server-side aggregation — 558,874 rows is the largest dataset of any
  city here, running back to **1990** (the "since 1997" in an earlier draft
  was wrong -- checked live 2026-09-02, 1990-1996 carry 7,000-9,300 permits a
  year, a normal level, not a sparse tail), too many to page raw. The endpoint
  blocks the `CAST` function outright but allows PostgreSQL's `::type`
  shorthand and `percentile_cont` for server-side medians, so processing time
  (date_debut → date_emission, real signal: only 27% same-day, zero negative
  rows) needed no client-side date-diffing at all, unlike every other city
  with that panel. **No cost field anywhere in this resource's schema** —
  re-confirmed live, not an undercount like Toronto's — so areas and work
  panels are ranked and labelled by **permit count**, not dollar value, the
  only city on this page where that's true (`"value_basis": "count"`, which
  the page reads to switch the areas panel's title/format instead of
  assuming every city has a $ figure to rank by). No concentration panel (no
  contractor/applicant field) and no build-time or unit-economics panel (no
  completion date, no cost). An earlier evaluation had rejected Montreal
  outright over two findings; re-checked live and one turned out to be
  **stale**: the dataset's own methodology page still says Lachine and
  Saint-Léonard borough data "n'est pas disponible actuellement" pending an
  in-progress system migration, but checked live, both boroughs have permits
  dated exactly as recently (2026-08-24) as an actively-updated borough like
  Le Plateau-Mont-Royal — the migration evidently finished and nobody updated
  the caveat text, so both are included. The no-cost-field half of the
  rejection held up on re-check. `description_type_batiment` (used for the
  page's unused-but-computed `use` field) carries real casing duplicates
  across boroughs (`"Commercial"`/`"commercial"`/`"Commerce"` all appear
  separately) — normalized to uppercase for grouping rather than picking one
  casing arbitrarily.
- **Halifax (added 2026-09-01)** joins as an eighth city, on the field list
  the user gave directly from `data-hrm.hub.arcgis.com` (submission/issuance/
  completed dates, Permit_Name, Work_Type, Permit_Status,
  Estimated_Project_Value, Most_Recent_Inspection, Type_of_Structure,
  Occupancy_Type, residential unit counts, Building_Footprint_Area, storeys,
  Inspection_Outcome, building height, Net_New_Units). This resource is a
  plain Esri TABLE with **no geometry at all** — no lat/long anywhere,
  unlike every other city here — so `Community` is the only geography.
  18,817 rows since 2020-12, small enough to page raw like Mississauga
  rather than build ArcGIS `outStatistics` calls. The **cleanest cost data
  of any city on this page**: `Estimated_Project_Value` populated on 99.3%
  of rows (no Ottawa-style fee-schedule clustering, no Mississauga-style
  scope-mixing problem needing a fix), and `Net_New_Units` pre-computed and
  100% populated — no need to derive it from separate existing/end-unit
  counts. A genuine three-date chain (submission/issuance/completed, zero
  negative-day rows checked live on either interval) gives it **both** a
  processing-time and a build-time panel, on top of a real unit-economics
  table — the same combination Mississauga has, but with materially cleaner
  underlying data. `Occupancy_Type = 'Residential Use'` scopes the
  unit-economics panel more precisely than `Type_of_Structure` alone:
  checked live, a permit can carry `Type_of_Structure = 'Dwelling - Single
  Detached'` with `Occupancy_Type = 'Garage'` (an accessory structure on a
  residential lot, not a home), which the occupancy field correctly
  excludes. `Building_Footprint_Area` is in square **metres**, the same
  unit-mixing trap as Mississauga and Ottawa's 2026 file, caught the same
  way (checked live against sample rows' magnitudes) before it could ship
  wrong. The user separately flagged `Most_Recent_Inspection`/
  `Inspection_Outcome` as worth checking for a richer external dataset —
  checked live, they're just this same permit's own current inspection
  stage/result (e.g. "Building - Part 9 - Final" / "Passed"), no external
  inspections table found, and not built into a panel: a status snapshot
  doesn't trend the way a date interval or a dollar figure does. No
  concentration panel (no applicant/contractor field in this schema at
  all). Halifax Regional Municipality's boundary is unusually close to its
  full CMA (the amalgamated former cities of Halifax and Dartmouth plus
  surrounding county), so unlike most cities here its series should track
  the metro figures elsewhere on the page closely rather than being a small
  fraction of them.
- **Winnipeg (added 2026-09-01)** joins as a ninth city — the last of the
  eight CMAs this page tracks to get a matching city-level permit desk
  (Montreal was passed over in an earlier evaluation and added anyway
  later the same day, so Mississauga is the only city here without its
  own CMA). Socrata SoQL, server-side aggregation like Calgary, 162,558
  rows since 2010. **No cost field at all** — the dataset's own
  description says so plainly ("containing most information about the
  permit WITH THE EXCEPTION OF declared construction value") — matching
  it to a separate aggregate dataset (by year, neighbourhood and permit
  type; single-permit cells have their value stripped for privacy and
  rolled into a `WINNIPEG OMITTED CONSTRUCTION VALUE` bucket) with no
  permit-level key to join back to individual rows, so areas/work/use
  panels here are ranked by permit count, the second city on this page
  where that's true after Montreal. What IS unusually clean:
  `applicant_business_name` carries real, unredacted business names
  (Qualico Developments, A&S Homes, Randall Homes, Kensington Homes...)
  with none of Ottawa's placeholder-redaction pattern, so the
  concentration panel needed no string filtering beyond excluding blanks.
  A genuine three-date chain (application received/issued/final, 100%/
  100%/91.6% populated, only 3 and 30 negative-day rows respectively out
  of 162,558) gives both a processing-time and a build-time panel,
  computed entirely server-side via SoQL's `median()` and `date_diff_d()`.
  One caveat disclosed on the dataset's own page rather than found by
  inspection: the city revised its dwelling-unit counting methodology and
  states plainly that data before November 14, 2022 was not updated to
  match, so `dwelling_units_created` before and after that date may not
  be perfectly comparable — stated in the card's quality note rather than
  silently plotted as one continuous series. See
  `Python/municipal_permits_etl.py`'s module docstring for the full
  writeup on all nine cities.
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
python construction_time_etl.py       # writes ctime/ from CMHC HMIP pages
python city_build_time_etl.py         # writes city_build.json (~5 min; --only city,...)
                                      #   (~80 min: slow server; --use-cache for dev;
                                      #   monthly in the workflow, non-blocking)
python cagbc_leed_etl.py              # writes cagbc.json from a MANUAL export,
                                      #   project_profile.csv at the repo root
                                      #   (gitignored; re-export by hand from
                                      #   leed.cagbc.org — no API, no sign-in)
```

`.github/workflows/construction-refresh.yml` does this monthly (20th, 14:00 UTC)
and commits `construction_json/` only when all fetches succeed and data changed.
