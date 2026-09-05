# Energy Suite — Project Tracker & Roadmap

The single source of truth for what's shipped, what's in flight, and what's next.
Updated **2026-09-05** (**Potential AC Explorer** — Simon's call: the RESNET
HERS Addendum 82 synthetic model added to `heatpumpAC.html` (badge SEER2/EER2
reconstruction, min/full/max variable-speed dispatch, part-load-fraction
cycling) went further than his confidence level in the underlying badge-data
supports. Reverted to the same convention the Heat Pump Explorer's heating
side has always used: real spec-sheet points, linearly interpolated, flat
outside the published range — no synthetic curve shape, one speed. The whole
HERS apparatus (`buildHersEquip`, `hersCoolingModel`, `hersBiquad`, the
SEER2/EER2 lookup tables) was deleted from `heatpumpAC.html`, and
`simulateCooling()` in both `HeatPump/app/engine.js` and `heatpumpAC.html`'s
own inline copy went back to a single-curve dispatch — the two copies are
back in sync (they'd drifted apart while the inline copy grew multi-speed
logic the standalone file never got). Equipment objects now read directly
from the curves already sitting in `ac_curves.json` / `hp_cell_curves.json`'s
per-cell `cooling.curve` — data that existed and was already correctly
digitized, just unused since the HERS rewrite. Net effect is a **bonus, not
just a simplification**: those pre-built curves cover all 9 tier cells, while
the badge-lookup table the HERS model needed only had 6 entries — 3 cells
(`low_<18k`, `low_18-30k`, `mid_<18k`) that showed "no data" for heat-pump
cooling mode now show real numbers. Kept in the methodology as an explicit
caveat, not silently smoothed over: 3 of the 9 cells' cooling curves are
digitized from an "Extended Ratings" table reporting MAX OUTPUT (compressor
flat-out, not necessarily the rated operating point) — the same limitation,
and the same source convention, the heating side has used for those units
all along.)

Prior update **2026-09-05** (**Heat Pump Explorer** — closed the two remaining
cooling-curve gaps in the live `hp_cell_curves.json`, and gave every one of
the 9 tier cells a real datasheet-measured cooling curve for the first time.
`mid_<18k` was **swapped, not supplemented**: LG LSU120HSV5 (w=4,182, a 4-pt
heating table with no cooling curve at all and a 2-anchor straight-line COP
interpolation) is out, replaced by **GE Appliances ASH115PRDWA/ASYW15PRDWB**
(w=868) — a ~4.8x drop in ERS install-count representativeness, traded for a
real 5-pt heating curve and a real 6-pt cooling curve, both with power draw
at every point, digitized from the same GE Altitude Series submittal already
vetted for `low_<18k`. The three higher-w candidates in that exact band
(GREE GWH12QC-D3DNA1D/O w=2,113, Tosot TW12HQ2C2DO w=906, ACD OCD12KCH22S-O
w=804) have no known datasheet; the representativeness-vs-completeness
trade-off was put to Simon explicitly rather than assumed, same convention
as every other cell swap this project has made. `high_18-30k` (Moovair
DMA24HOS20230E7) keeps its existing 15-pt heating curve and gains a real
19-pt cooling curve, digitized from page 1 of the same `MOOVAIR_M20_perf.pdf`
already on disk for its heating data — a table that had simply gone
unread before Simon pointed it out. Cross-checked against the AHRI cert
(212361759): 95°F capacity 1.125x rated (well inside the tolerance other
cells already pass at) and COP 3.243 vs. EER2-derived 3.135 (3.4% gap).
**All 9 of 9 live cells now have real cooling data** — up from 7 of 9 last
pass and 5 of 9 the pass before that. Both curves were rebuilt with
`build_cell_curves.py`/`build_hp_tier_selection.py` and verified live in
`heatpump.html`'s "Show potential AC" toggle for both swapped cells (cooling
chart, solved balance point, and cooling-peak KPI all render with no
fallback and no console errors) before publishing. Also added
[HeatPump/reference/spec_sheets/](HeatPump/reference/spec_sheets/) — the 8
manufacturer PDFs backing all 9 cells' curves, tracked on `main` (unlike the
gitignored `data/raw/spec_sheets/` working cache) with a README mapping each
file to the cell/table/AHRI cert it backs, so the primary source for every
digitized point stays visible and reproducible without depending on Simon's
local disk. See `pipeline/build_cell_curves.py`'s `mid_<18k` and
`high_18-30k` entries for the full point-by-point sourcing.)

Same-day follow-up **2026-09-05** (**Heat Pump Explorer** — a full indoor-
condition audit of all 9 cells' spec-sheet sources caught one real bug, and a
new NEEP-based cooling cross-check table shipped to make this kind of error
visible on the page itself, not just in chat.

**The bug**: `mid_<18k` (GE ASH115PRDWA)'s cooling curve, added earlier today,
had been read off the datasheet's 70°F indoor-set-temperature column — the
same convention used for heating — but AHRI's cooling standard is 80°F
indoor, and the sibling `low_<18k` cell (same spec sheet) already used the
correct 80°F column. Caught by cross-checking against fresh NEEP data Simon
pulled for this AHRI cert: the wrong column gave 18,200 Btu/h / COP 2.947 at
95°F against a 15,000 Btu/h AHRI-certified rating (1.213x, plausible-looking
enough not to have been obviously wrong on its own); the correct 80°F column
gives 16,500 Btu/h / COP 3.301 (1.10x vs. AHRI, 9.8% COP gap vs. NEEP's
directly-measured 3.66) — both a materially different number and a
tighter match. Fixed in `pipeline/build_cell_curves.py`, regenerated,
re-verified live.

**The audit**: rather than assume the bug was isolated, re-extracted every
single heating and cooling point for the other 8 cells directly from their
source PDFs (GE, Tosot ×2, GREE ×2, Fujitsu ×2, Moovair) and confirmed an
exact match against what's committed — not a tolerance check, the actual
digit. All 8 were already correct; the GE `mid_<18k` cooling column was the
only place a wrong table got read. `mid_18-30k`'s cooling ratio (1.42x
against its own 24k-rated AHRI cert) looked like an outlier on the summary
table but is the already-documented, deliberate GREE 24k/36k shared-hardware
reuse, not a second bug.

**The NEEP cooling table**: Simon asked to add NEEP as a permanent, visible
three-way cross-check (spec sheet vs. AHRI vs. NEEP) for cooling, mirroring
the heating "Spec-sheet table" already on the page — both so this class of
error surfaces on the page itself next time, and so the two remaining
cooling gaps closed today have the same paper trail as everything else.
Pulled all 9 units' NEEP "Performance Specs" pages by browsing
ashp.neep.org's rendered product pages (search by AHRI #, click VIEW DETAIL)
— never the site's API, per standing instruction. This also filled two
long-standing gaps in `data/interim/neep_extract.json`: `low_<18k` and
`mid_<18k` had no NEEP listing at all in the 2026-08-04 pull, and none of the
9 units' *cooling* tables had ever been extracted (the old
`build_neep_extract.py` discarded Cooling blocks entirely, heating-only by
design at the time). `build_neep_extract.py` rewritten against a fresh raw
pull (`data/raw/neep/neep_pages_2026-09-05.json`) to keep both blocks;
`build_tier_curves.py` gained `build_cooling_table_data()` (AHRI's cooling
anchor comes from `lookup/ahri_numbers.json` instead of
`hp_units_joined.csv`, which has no cooling columns); `heatpump.html` gained
a "Cooling spec-sheet table" details block next to the existing heating one.
Verified live: switching to `mid_<18k` on the new table shows the corrected
16,500 Btu/h next to AHRI's 15,000 and NEEP's 15,000, and the existing
heating table was re-checked for regressions (9 units, 51 rows, AHRI/NEEP
columns still populate) — none found. See `HeatPump/METHODOLOGY.md`
"Cooling gaps closed" and its NEEP-cross-check follow-on for full detail.)

Same-day follow-up **2026-09-05** (**Heat Pump Explorer** — one more finding
out of the NEEP cross-check work above: `high_<18k`'s (Fujitsu AOUG15LZAH1)
design & technical manual captions both its heating and cooling tables
"Model: ASUG15LZAS" — internally consistent with each other — but NEEP's own
listing for this exact AHRI certificate (206597213) gives the indoor model
as **ASUG15LZBS**, a different suffix. Recorded in the cell's `flags` in
`pipeline/build_cell_curves.py` rather than silently reconciled or ignored:
the outdoor unit (AOUG15LZAH1, which governs capacity/COP) matches exactly,
and NEEP's own capacity/COP figures sit in the same ballpark as this cell's
already-documented 9.4% COP gap, so this reads as a manufacturer
indoor-unit revision variant, not a wrong-unit mismatch — but it's flagged,
not assumed. Regenerated and published.)

Prior update **2026-09-04** (**District Energy Explorer** — restructured twice in one
day on user feedback, ending at a five-section page. Recorded as one entry
because it's one arc.

**Pass 1 — content and labels.** (1) *Layout* — pure-text descriptions lost
their card boxes; boxes reserved for the diagram, charts, tables and the
interactive generation ladder. (2) *Labels* — generation badges/legends/
tooltips read "1st Gen"–"4th Gen" instead of "1G"–"4G" everywhere a general
reader sees them; advanced-mode methodology keeps IEA's own shorthand
alongside. Diagram gained solar thermal, waste heat and geothermal source
icons feeding the plant. (3) *New sections* — cost/emissions, a Vancouver
policy subsection, and a World Leaders section.

**Pass 2 — layout, on the feedback that the page was "all over the place".**
Four measured problems, three of them self-inflicted in pass 1: body text
capped at 820px inside a 1,140px column (**72% of the width** — the pass-1
override was written `.plain .prose`, a descendant selector, against markup
that is `class="prose plain"` on one element, so it never matched); text in
two columns; the decarb chart rendering **869×623px** because a 460-wide
viewBox got stretched full-width when it left its two-up grid; and country
boxes not matching the project-box style. Fixes: `.prose` now 1000px / 15px,
all text single-column, decarb re-authored at a 900-wide viewBox (now
869×290), country profiles rebuilt on the `.proj` pattern.

**Restructured to five sections** (user chose this over a seven-section split):
01 What it is · 02 What Canada has built and what's coming · 03 Policy and why
it isn't scaling · 04 World leaders · 05 Method. Page runs ~17,900px, so a
**sticky pill nav** was added, reusing project-atlas's pattern —
**rect-based, not IntersectionObserver**, since IO callbacks never fire in this
repo's preview renderer (see [preview-renderer-no-raf] in memory).

**The BDA/Dunsky white paper finally extracted** (it returned binary through
WebFetch on 2026-09-03; `pymupdf` on the cached download worked), which is
what made §03 possible: only the **BCUC** has a provincial thermal-utility
framework vs **15 US states** with legislation passed or developing; the
national model code counts network heat as *purchased energy at an assumed
COP of 1.0*, penalising a plant-side heat pump against an identical
basement-side one; and a 2022 UK survey of 2,244 heat-network customers found
a **lower average bill (£600 vs £960) but 1 in 10 paying £2,000+**, more
outages, 39% satisfied with complaint handling — the honest counterweight the
page lacked. The paper's own hedging ("not inherently low carbon"; "may not
always reduce energy costs compared to the current fossil-fired status quo")
replaced pass 1's weaker framing. Two corrections: the 70%-of-Canadians figure
is **McMaster's**, cited by BDA, not BDA's own; Denmark's box now explains
*why* cost-based pricing regulation matters here rather than just reciting
coverage. See
[docs/DISTRICT_ENERGY.md → Non-CEEDC content](docs/DISTRICT_ENERGY.md#non-ceedc-content-added-2026-09-04)
for the full source list. Verified in-browser at 1200/1400/375px: no console
errors, no empty charts, prose at 88% of column, nav sticky and highlighting,
no mobile overflow, all three themes and both modes re-render.

Updated **2026-09-03** (**District Energy Explorer** — new tool shipped:
`districtenergy.html` + `Python/district_energy_etl.py` + `districtenergy_json/`
+ [docs/DISTRICT_ENERGY.md](docs/DISTRICT_ENERGY.md). Trigger: user asked for a
district energy page covering definitions (generations, single/double pipe,
fuels, equipment), the Simon Fraser dataset, project news and any other usable
stats.

The dataset turned out to be **CEEDC**'s (Canadian Energy and Emissions Data
Centre, SFU, funded by CanmetENERGY-Ottawa) Innovative Energy Facilities
database. `sfu.ca/ceedc/databases.html` only embeds a Tableau dashboard — the
actual **public download links are inside the rendered viz**
(`CEEDC_IEF_district energy.xlsx`, 254 systems; `CEEDC_IEF_public.xlsx`, 3,644
IEF facilities; plus the `.twbx`). Licensing: CEEDC states no terms anywhere
(their `contact/terms-conditions.html` 404s); user confirmed he works with
people at CEEDC, no problem using it, **reference the source** — done in the
header badge, footer, both methodologies and the sources panel.

**Three findings shaped the build.** (1) *The public file does not reproduce the
published report's totals* — respondent-confidential values were withheld, so
file totals come out lower on a smaller n (steam capacity 3,757 MW n=50 vs
3,990 MW n=57; steam production 4.05M vs 5.13M MWh). Both are correct; the
pipeline **computes** the delta into `meta.json` rather than asserting it, the
page shows it as a table in Advanced, and report figures vs file figures are
never mixed. (2) *Coverage is far thinner than "238 systems" implies* — 38 of
238 completed the 2023 survey (21%), and **90 operating systems report zero
quantitative fields**; `year_reported` runs 2014–2023 per row (82 rows are
2017), so "the 2023 inventory" is a decade of snapshots. Both are charted as
first-class content in §06 rather than buried in a caveat. (3) *IEA generation
classification is possible but only for n=26* — `de_hw_supply` is populated for
27 systems spanning 8 °C to 200 °C.

Generation methodology decided explicitly with the user: use the **IEA DHC
Feb-2024** ladder (1G steam by carrier · 2G >100 °C · 3G 70–100 °C · 4G ≤70 °C),
follow IEA's own recommendation **against the term "5G"** in favour of *thermal
source network* as a 4G subclass, and **do not** inflate n by inferring 1G from
the steam flag — that conflates "uses steam" with "is a 1G network" and
mislabels hybrids. So the ladder shows n=26 (2G 5, 3G 17, 4G 4, one TSN: UBC
Okanagan at 8 °C supply) with an explicit "illustrative, not representative"
callout, and the 94 steam systems are reported separately as 1G-by-definition.
Two hot-water supply temperatures ≥150 °C (Confederation Heights 175 °C, Cape
Breton University 200 °C) are almost certainly steam values in the wrong field —
kept, ringed on the chart, and flagged in `meta.json`, not dropped.

Map: all 254 systems have source coordinates, so the page plots them on a
**Lambert conformal conic** (49°N/77°N, −96°) against province outlines unioned
from the repo's own `geo_json/` — with Yukon reprojected from
`lfsa000b21a_e.json` via `canada_boundary.py`'s inverse-Lambert, imported rather
than copied, since `geo_json/` still has no YT file. User chose to include the
**full IEF superset as a context layer** — 3,390 non-district-energy facilities
drawn behind the district energy points, Advanced mode only.

Nice accident worth keeping: the inventory records **Confederation Heights** as
a 175 °C hot-water system, and Confederation Heights is one of the four energy
centres in the **NCR DES**, which launched 2026-06-23 as a $3.4B steam→
low-temperature-hot-water conversion. The data's staleness demonstrates itself.

Verified live at localhost:8123 — no console errors, all 11 charts paint, 254
map points, LCC projection sanity-checked by east/west and north/south ordering
of known cities, filters/search/sort/detail-panel all exercised, and all three
themes plus both detail modes re-render. Previous entry below.

Updated **2026-09-03** (**Grid Dashboard** — deep-history section added: six new
charts (generation mix by fuel, capacity factor by fuel, demand, HOEP wholesale
price, intertie imports/exports, Global Adjustment) covering years of real IESO/
AESO history rather than the page's existing recent/live layer (last 24h + ~12mo).
Trigger: user wanted "a lot more detail about generation type and potential usage
(% of capacity)" and, told the first capacity-data source found (`GenOutputCapability`,
~90 days retained) didn't look complete, asked to look deeper — that pushback led to
finding `GenOutputCapabilityMonth` (per-generator hourly Output+Capability back to
2019-05, no fuel-level pre-aggregation, so `Python/grid_history_etl.py` does the
fuel rollup) and, browsing the full IESO reports directory, five more usable sources
(`GenOutputbyFuelMonthly`, `Demand`, `PriceHOEPAverage`, `IntertieScheduleFlowYear`,
`GlobalAdjustment`) discovered simply by reading `reports-public.ieso.ca/public/`'s
own directory listing, not documented anywhere else.

Each chart's history starts wherever its own source's real archive starts, stated
plainly rather than padded to match the others: ON generation mix from 2015-01
(`GenOutputbyFuelMonthly`, a year earlier than the hourly report the live layer
uses), capacity from 2019-05, demand/HOEP from 2002-05, interties from 2018-01.
Global Adjustment is the one exception worth flagging on its own: its endpoint
retains only a rolling ~13-14 month window with no yearly archive at all — checked
live twice (the user pushed back once on "no deeper history exists," asking to look
harder at the parent directory; the second check confirmed the same limit, just via
the correct per-month files instead of one wrongly-assumed rolling document) — so
it ships as a short trailing-window chart, explicitly not part of the same historical
array as the other five, so the page can't accidentally imply years of GA history
that don't exist at the source.

One live bug caught before shipping: the first parse of `GlobalAdjustment` assumed
its un-suffixed `PUB_GlobalAdjustment.xml` was a multi-month rolling document (it
looked that way from one sample fetch) — it's actually just the *current* month,
and the ~13 "months" seen in the directory listing are 13 separate per-month files.
Produced 1 GA month instead of 14 until caught by checking the output row count
against the directory listing rather than assuming the parse matched the source.

Capacity-factor methodology required a real decision, not a rename: Ontario's
`GenOutputCapabilityMonth` gives dispatchable fuels (GAS/HYDRO/NUCLEAR/BIOFUEL) a
registered `Capability` figure, but WIND/SOLAR have no such row — only `Available
Capacity`, IESO's own weather-adjusted forecast of what those assets could produce
that hour. So ON's wind/solar capacity-factor answers "share of available wind/sun
actually used" (typically high), not "share of nameplate capacity ran" (typically
low) — a different question from every other fuel on the same chart, stated on the
page rather than blurred together. Checked live whether Alberta's AESO data has the
same split before assuming it did: it doesn't — `Maximum Capability` is a fixed,
nameplate-like figure per asset for every fuel including wind (confirmed constant
across ~4,300 hourly readings for a sample wind asset), so AB's wind/solar
capacity-factor and ON's aren't directly comparable without accounting for that.

Shipped as a new manual/occasional script (`Python/grid_history_etl.py`, not on the
weekly Action — ~120MB of IESO capacity CSVs cache to `HeatPump/data/raw/
ieso_history/` on first run) rather than growing `grid_etl.py`, since the two have
different fetch volumes and cadences. Outputs `grid_json/grid_{on,ab}_history.json`
(80.9 KB / 33.6 KB, well under the 300KB budget). `grid.html` gained six new chart
sections plus two new generic chart-engine functions (`monthStackedShare`,
`monthLineChart` — month-indexed, arbitrary row count, `monthLineChart` supports
negative values for intertie net-flow and the occasional negative GA rate) built
alongside the existing hour-indexed ones rather than replacing them, since the
recent/live layer still needs its fixed 1-24-hour axis. Verified live via a local
static server: all six charts render with real data, ON/AB toggle correctly hides
the four ON-only sections (demand/HOEP/intertie/GA) for Alberta, Simple/Advanced
toggle correctly gates the intertie section, zero console errors after fixing one
bug caught in testing (chart methods referenced `g.fuels`/`g.sources` when the
payload actually nests those under `g.meta`). See [docs/GRID.md](docs/GRID.md) for
the full source-to-chart mapping.)

Prior update **2026-09-02** (**Permits Explorer** — new page `permits.html`, splitting
the municipal permit data out of the Construction Tracker. The trigger was a
usability problem that turned out to be a data problem: "Inside one city" was
`data-mode="advanced"` *and* filtered to cities matching the selected geography,
so nine cities' permit desks rendered as nothing at all on a Canada or provincial
view, and what did render was a summary — one line, an all-time top-12 list, a
top-15 name table.

New `Python/permits_detail_etl.py` (imports its transport/paging helpers from
`municipal_permits_etl.py` rather than re-implementing nine portal integrations;
that script is unmodified and stays the single producer of the processing /
build-time / unit-economics / quality panels, which the new page reads from
`municipal.json`). Adds full per-city history, category×year matrices, a
0.004° density grid, a 120-deep filer list, and Toronto's two interval panels.

**Five data-quality finds, each of which would have shipped a wrong chart:**
(1) **CKAN silently truncates `datastore_search_sql` at 32,000 rows** — Montreal's
grid covered 60,394 of 540,855 geocoded permits, an 89% loss with no error and a
map that looked complete; now paged and *reconciled against the source count*,
raising on mismatch. (2) **Toronto's pre-2017 rows are a survivorship sample**,
not history — only permits still open when the dataset was cut, rising smoothly
94 (1990) → 33,017 (2016) → 45,431 (2017); floored at 2017-01 with the 173,236
excluded permits disclosed and still counted in totals, and a `check_leading_ramp()`
guard now screens every city on every run. (3) **The current month is always
partial** — Vancouver's showed 14 against a ~330 norm, reading as a collapse;
dropped, with the record labelled as ending at the last complete month.
(4) **Vancouver's `propertyuse` is multi-valued**, producing 153 combination
pseudo-categories; first-listed use taken as primary so column totals still
equal the permit count, with the limit stated on the card. (5) **The issue-date
gate was dropping 66,481 rows silently** — every series is keyed on that date,
and Toronto (45,652, 8.0%), Calgary (18,340, 3.7%), Halifax (2,478, 13.2%) and
Ottawa (11) publish permits without one. Now counted per city, printed by the
run, and named on each card and on the roster, per the repo's own
never-silently-drop rule.

Also corrected two claims in `docs/CONSTRUCTION.md` that live checks disproved:
Toronto *does* have a `BUILDER_NAME` field (2.2% populated, mostly individuals —
so still no concentration panel, but the field exists), and Montreal's record
starts **1990**, not 1997. `construction.html` keeps its summary cards, drops the
advanced-only gate on that section, and always shows a cross-reference card.
`permits_json/` (~4.9 MB, 9 cities) is gitignored on `main`, added to `deploy.sh` and to the monthly `construction-refresh.yml` workflow.)

Previously **2026-09-02** (**Heat Pump Explorer** — heating-curve refresh for three
of the 9 live `hp_cell_curves.json` cells, prompted by new manufacturer spec
sheets added to `data/raw/spec_sheets/NewSelection/`. `high_<18k` (Fujitsu
AOUG15LZAH1) and `mid_18-30k`/`mid_30-42k` (GREE GUD36W/A-D(U)) already had
real datasheet heating curves wired into `build_cell_curves.py` from earlier
work — the generated JSON had just drifted 28 minutes stale against its own
source script, fixed with a rebuild, no code change needed. `low_18-30k`
(Tosot TUD24W2/D-D(U)) was a genuine gap: its 3-point heating transcription is
now a full 17-point curve (5–75°F), and it gains a real 23-point cooling curve
it previously lacked entirely — both digitized from
`TOSOT_TUD24W2DDU_Specification_Sheet.pdf`'s extended-ratings tables (read via
rendered PNG pages, not `pdftotext`, which badly mangles this table's
multi-line cells). Also added the Fujitsu AOUG15LZAH1/ASUG15LZAS real cooling
extended-ratings table to `heatpumpAC.html` as a sourcing/verification
display — its 95°F rated point (COP 4.09) exactly matches NEEP's
independently republished figure for the same AHRI certificate. Published:
code + doc changes to `main` ([f3d29de](https://github.com/OttawaVisuals/Energy/commit/f3d29de)),
regenerated `hp_cell_curves.json` to `gh-pages` via the incremental-update
path (only that one file touched). See
[HeatPump/METHODOLOGY.md](HeatPump/METHODOLOGY.md) "`hp_cell_curves.json`
heating refresh, and Tosot 24k upgraded to a full curve".)

Same-day follow-up **2026-09-02** (**Heat Pump Explorer** — `low_<18k` swapped
from Cooper & Hunter CH-12SPH-230VO to **GE Appliances ASH112PRDWA**, the
first of three cells found to have no cooling curve at all (the other two,
`mid_<18k` LG and `high_18-30k` Moovair, remain open). Queried
`hp_units_joined.csv`/`hp_buckets.csv` — the real ERS install-count data —
for plausible alternates in each of the three gaps before asking Simon to
go spec-sheet hunting, rather than guessing candidates. Simon found and
added GE's Altitude Series submittal (`data/raw/AC/`), covering the exact
model already flagged as a lead. This is a **swap, not a supplement**: GE
and Cooper & Hunter are different physical hardware, so the decision (GE
is ~7x more ERS-representative, w=846 vs. 123, and has richer data on
both heating and cooling) was put to Simon explicitly rather than assumed,
since it changes which real-world unit the cell claims to represent. One
thing flagged, not hidden: the datasheet's own max heating capacity at
47°F is 1.67x the AHRI-certified rated capacity used for normalization —
recorded in the cell's own `flags` array, the same review-not-reject
convention `build_unit_curves.py` already uses for high ratios. Published
to `gh-pages` (regenerated `hp_cell_curves.json` only). See
[HeatPump/METHODOLOGY.md](HeatPump/METHODOLOGY.md) "`low_<18k` swapped to
GE Appliances ASH112PRDWA".)

Prior update **2026-09-01** (**Construction Tracker** — added Calgary to the "Inside
one city" municipal-permits card, after re-evaluating the earlier "two cities,
deliberately" call against Ottawa, Montreal and Edmonton. Calgary (Socrata SoQL)
cleared the bar the other three didn't: a real permit-status field, a clean cost
field (`estprojectcost` ~92-95% populated since 2016, no Toronto-style
placeholder corruption), dwelling units, full community-level geography, and
daily refresh with cheap server-side aggregation. Its city boundary is also
unusually close to its CMA — ≈88% of the Calgary CMA's population per the 2021
Census, versus ≈24-28% for Vancouver and Toronto — so its cross-check line
tracks the metro series far more closely, though the card still states the
live ratio rather than assuming it. Montreal (CKAN, `datastore_search_sql`
works) was ruled out for now: no cost or status field on individual permit
rows, cost only exists pre-aggregated by year/borough, and Lachine +
Saint-Léonard are currently missing from an in-progress system migration.
Edmonton (Socrata) was ruled out for having several overlapping/redundant
permit datasets to reconcile first and no status or postal/ward field. Ottawa
was ruled out outright: the earlier "reachable via ArcGIS" note in
`Python/municipal_permits_etl.py`'s docstring was **wrong** — there is no
ArcGIS feature layer, only ~10+ separate annual `.xlsx` bulk-download
workbooks with no API and no server-side aggregation. One live bug caught
before shipping: Socrata sorts `NULL` as the *largest* value under
`ORDER BY ... DESC`, so an unordered `$limit`-bounded pull silently dropped
Calgary's single largest community by permit value (Downtown Commercial Core,
$9.1B) before the fix — sort by parsed value client-side over the full
distinct-value count (317 communities), never trust the API's own order when
nulls are present. See [docs/CONSTRUCTION.md](docs/CONSTRUCTION.md) and
`Python/municipal_permits_etl.py`'s module docstring for the full writeup.

Same day, second pass: **two new Vancouver-only panels** in "Inside one city",
because Vancouver's schema (unlike Toronto's or Calgary's) carries a
per-permit elapsed-days field and a fully-populated applicant field. **Time to
get a permit** shows median days from permit-number assignment to issuance —
by work type (new buildings and demolitions take months; additions/temporary
structures move in weeks) and by year issued. Median, not mean: the
distribution is right-skewed by large projects, and the mean runs 40-70 days
higher. **Applicant/contractor concentration** shows who files and who builds
the most permits, thresholded to 20+ permits: 420 of 11,155 distinct
applicants (3.8%) clear that bar and account for 48.9% of every permit issued;
311 of 4,363 named contractors (7.1%) clear it and cover 56.9% of permits that
name one (`buildingcontractor` is populated on only ~62% of rows — often not
yet chosen at issuance). The 20-permit threshold is a deliberate editorial
choice, not a legal one: `applicant` is "often the design professional or
their firm" per the field's own description, and no private homeowner
personally files dozens of permits, so the threshold keeps the published list
to genuine repeat filers rather than naming an individual over a one-off
renovation. Calgary and Edmonton have equivalent applicant/contractor fields
and could support this later; Toronto and Montreal do not.

Same day, third pass: **Calgary gets four more panels**, since its schema
turned out to carry everything Vancouver's does plus a `completeddate` and a
`totalsqft` field Vancouver lacks. **Time to get a permit** and
**applicant/contractor concentration** reuse Vancouver's exact panels and
20-permit threshold, with lower field coverage stated on the card (applicant
~66%, contractor ~60%, versus Vancouver's ~100%/~62%). Two are new: **time to
build** (issuance to the permit's completed date — an administrative closure
date, not necessarily physical completion, but the best available proxy) and
**$/unit, $/sqft and average unit size** for residential new-construction
permits with dwelling units — `totalsqft` is recorded on 0% of non-residential
rows and only ~38% of residential rows dataset-wide, but checked live within
that exact scope (residential + new + units>0) it is ~91% populated, so it's
usable there even though it isn't usable dataset-wide. One bug caught before
shipping: Calgary's dataset runs back to 1999, not 2017 like Vancouver's —
its areas/work/concentration/processing queries were unfiltered, so a card
that says "since 2017" everywhere else was silently pulling in 27 years of
history for Calgary alone. Now explicitly floored to 2017, mirroring
Toronto's existing `d >= FLOOR` filter. See
[docs/CONSTRUCTION.md](docs/CONSTRUCTION.md) for the full writeup.)

Same day, fourth pass: **Edmonton added as a fourth city**, reversing this
same day's own "ruled out" call above after the user pointed at the specific
dataset (`24uj-dj8v`, "General Building Permits") and it was re-checked live
rather than trusted from memory. What actually changed the verdict: this
dataset is explicitly labelled the city's **"Primary Dataset or View"** —
deduplicated, verified for accuracy, daily updates, clean history back to
2009 — which resolves the "several overlapping/redundant datasets" reason it
was excluded earlier that same day. Two real limits confirmed live, not
assumed: **no concentration panel** — Edmonton's own dataset description
states applicant/contractor names were deliberately excluded as a privacy
measure (a private individual's name, and by extension address, would
otherwise become searchable), which is the city making the right call, not a
gap to route around — and **no processing-time panel** — the portal's UI
mislabels its own columns (the one displayed as "PERMIT_DATE" is actually the
API's `issue_date`; "REPORT_PERMIT_DATE" is actually `permit_date`), and
checked live the two are identical on every one of 143,693 rows since 2017,
so there is no application-to-issuance interval to measure at all, unlike
Vancouver and Calgary. It does get Calgary's other two panels — **time to
build** (permit date to `occupancy_granted_date`) and **$/unit, $/sqft,
average unit size** for residential new construction (99% floor-area
coverage in that exact scope) — but build time carries a real coverage
caveat the card states plainly: Edmonton only began systematically recording
occupancy dates for residential permits finalized 2022-01-01 forward
(non-residential: 2024-01-01), so only 22,543 of 45,374 residential-new
permits since 2017 have one. One implementation snag: `occupancy_granted_date`
is stored as TEXT rather than a proper `calendar_date`, so Socrata's
`date_diff_d` (which works fine for Calgary) 400s on it — those ~22.5k rows
are pulled raw and diffed client-side in Python instead. Also caught and
fixed a labelling bug before shipping: the shared "Time to build" panel
originally hardcoded "by work category" in its title and note text, correct
for Calgary but wrong for Edmonton, whose `by_type` breakdown is actually
grouped by **building type** (Calgary's own `work_type` is constant
"New" within the residential-new scope, so building type is the informative
dimension instead) — both cities' build-time payloads now carry an explicit
`group_label` the page reads rather than assuming Calgary's wording fits
everywhere. A second fix: the areas-card undercount note was hardcoded to
Toronto's specific "placeholder text" wording; now reads each city's own
`quality.note` instead, so Edmonton's genuinely-different reason (74.8% cost
coverage, blank rather than corrupted) displays correctly. Verified live via
a local static server across all four cities: zero console errors, Edmonton's
processing/concentration cards correctly hidden, build-time/unit-economics
cards correctly shown with accurate per-city labels. See
[docs/CONSTRUCTION.md](docs/CONSTRUCTION.md) for the full writeup.)

Same day, fifth pass: **Mississauga added as a fifth city**, on the exact
schema the user described a session earlier — that field list (STATUS,
FILE_TYPE, BLDG_TYPE, STOREYS, EST_CON_VALUE, RES_UNITS, coordinates,
application/issue/completion dates) had been paired with Edmonton by
mistake; it's Mississauga's actual ArcGIS FeatureServer schema, confirmed
live once the user supplied the real dataset link. It's the richest schema
of any city here — a real STATUS field, three genuinely distinct dates
(only 488 of 34,615 rows share an application and issue date, unlike
Edmonton's identical pair) — so it's the only city with both a
processing-time panel and a build-time panel; no concentration panel, since
this schema never had an applicant/contractor field at all. The bigger
change: **Mississauga is not its own StatCan CMA** — it's part of the
Toronto CMA — so it can't be a standalone selectable geo without every
StatCan-driven section of the page (KPIs, pipeline, dwelling types, ...)
having nothing to show for a "Mississauga" geo that doesn't exist in
StatCan's tables. Asked the user how to handle this rather than guessing;
they chose nesting it under the Toronto CMA view over a standalone section.
`renderMunicipal()` was refactored from one-city-per-geo to
possibly-multiple-cities-per-geo: it now matches every city whose own key
*or* `cma` field equals the selected geo, generates a full card block per
match (`muniCityBlockHTML()`, ids suffixed by city key), and runs the
existing per-city render logic (`renderOneMuniCity()`) against each —
selecting Toronto now shows both the City of Toronto's card and the City of
Mississauga's card together. Two data-quality problems caught live before
shipping, both in the unit-economics panel. **(1)** `APPL_AREA` is recorded
in **square metres**, per its own field description — every other city's
floor-area field on this page is sqft, and treating it the same way
produced a physically impossible ~100 sqft "average unit size" and
$2,000+/sqft. **(2)** Scoping to every RESIDENTIAL permit with units added
(no further filter) mixes new subdivisions with ALTERATION/ADDITION permits
that merely add a secondary suite; restricting to `SCOPE = 'NEW BUILDING'`
alongside the unit fix brought $/sqft down to a plausible $223-253 for
2018-2023. The resulting 2024-2026 jump to a $2.7M+ median $/unit was
checked row-by-row rather than assumed away: a real run of ~$7-10M custom
detached-home permits (990-1,143 sqm each, individually verified), not an
error — with only ~140-190 qualifying permits a year, a handful of genuine
luxury builds can swing the median, and the card's note says so. Unit
economics also switched from a sum(cost)/sum(units) aggregate to the
median of each permit's own ratio, after checking Calgary's equivalent
distribution was tame enough (median $285K vs p90 $439K) to keep its
existing simpler aggregate — this is a Mississauga-data problem, not a
reason to change the general method everywhere. Verified live across all
five cities: zero console errors, Toronto view renders both cities' full
card sets, Ontario (a province, no CMA match) correctly hides the section
entirely. See [docs/CONSTRUCTION.md](docs/CONSTRUCTION.md) for the full
writeup.)

Same day, sixth pass: **Ottawa added as a sixth city — the only one with no
API at all.** An earlier evaluation (this same session, earlier today) had
ruled Ottawa out entirely, on record in this file and in the module
docstring. Re-checked live anyway, on the reasoning that the Edmonton
rejection earlier in this same session had *also* turned out to be wrong
once actually re-verified rather than trusted from memory — and this one
was too, partially: there is genuinely no API (confirmed live: 15 annual
XLSX workbooks, `item.type == "Microsoft Excel"`, no queryable `url` on any
of them), but the underlying data itself is rich, not the "just bulk
downloads" dead end the old rejection implied. Discovered live from
open.ottawa.ca's DCAT feed (not a hardcoded item-id list) rather than
scraping the catalog page, so a newly published year is picked up on the
next run automatically. Real per-permit **contractor** names (55.7% of
rows; the rest are `CONTRACTOR UNKNOWN`/`***CONTRACTOR***` placeholders the
city itself substitutes when the contractor is the property owner) support
a genuine concentration panel — no applicant field exists in this schema at
all, so only half of that card's usual pair renders. The concentration
card's two halves (applicants/contractors) were previously assumed to
always come as a pair; fixed to show or hide each independently, and gave
the contractor note a per-city `coverage_reason` field instead of Vancouver/
Calgary's hardcoded "not yet chosen at issuance" wording, which would have
been wrong for Ottawa's real reason (privacy redaction, not timing). No
processing-time or build-time panel: only one date (issuance) exists in
this data.

Two schema eras exist, detected **per sheet**, not assumed by year: 2011-
2025 files carry `CONTRACTOR`/`APPL. TYPE` columns and area already in
square feet; the current in-progress 2026 file drops both and reports area
in square metres (converted, same SQM_TO_SQFT lesson as Mississauga). A
live-caught bug reshaped the whole parsing strategy: the first working
version picked "the" full-year detail sheet per file by name priority
(`Sheet1`/`Details`/`Detail`/`Permits`), and it broke silently on the
2024-2025 combined workbook — its named "Permits" rollup sheet turned out
to be **stale**, covering only Jan-Aug 2024, while Sep 2024 through Dec
2025 existed only in that file's monthly sheets, which the priority-pick
logic was skipping as presumed-redundant. Caught by cross-checking the
output's monthly series and finding 2025 almost entirely empty. Fixed by
reading and parsing *every* sheet in every file unconditionally instead of
picking one — a pivot "Summary" sheet, or any sheet with no real per-permit
rows, correctly parses to nothing on its own (there's no cell reading
exactly `WARD` to build a header from), so concatenating everything and
de-duplicating by permit number is robust to whichever sheet(s) in a given
file actually hold the data, without needing to know in advance. A second
finding shaped a caveat rather than the logic: checked live, a large share
of the declared `VALUE` field for residential permits clusters tightly on a
handful of near-identical $/sqft rates (hundreds of permits within cents of
$167.22/sqft or $185.87/sqft in a single year — not seen on office/retail/
institutional permits in the same file), consistent with a standard
municipal fee-assessment schedule rather than each builder's independently
reported project cost. Rather than strip or "correct" it (no reliable way
to separate schedule-driven from real declared values row by row), the
unit-economics scope note says so plainly: $/sqft here likely tracks
Ottawa's own rate table more than the real market, and $/unit inherits the
same caveat since it depends on the same field. Verified live across all
six cities: zero console errors, Ottawa's applicants panel correctly
hidden while contractors renders, unit-economics and areas/work/use panels
populated and plausible. See [docs/CONSTRUCTION.md](docs/CONSTRUCTION.md)
and `Python/municipal_permits_etl.py`'s module docstring for the full
writeup.)

Same day, seventh pass: **Montreal added as a seventh city**, this time on
a field list the user supplied directly from `donnees.montreal.ca` (not a
memory mix-up like Mississauga's fields were) — CKAN `datastore_search_sql`,
server-side aggregation over 558,874 rows since 1997, the largest dataset
of any city here. Real signal for a processing-time panel (only 27%
same-day, zero negative-day rows, unlike Edmonton's identical-date dead
end), computed entirely server-side via `percentile_cont` for the median —
the endpoint blocks the `CAST` function outright ("Not authorized to call
function CAST") but allows PostgreSQL's `::type` shorthand, so no client-
side date-diffing was needed at all, a first for this card's processing-
time panels. **No cost field anywhere in this resource's schema**, matching
an earlier evaluation's finding, re-confirmed live rather than assumed
still true — so areas and work panels are ranked and labelled by permit
count, not dollar value, the only city on this page where that's true.
Added a `"value_basis": "count"` flag the page reads to switch the areas
panel's title/format, rather than hardcoding a dollar assumption across
every city as the code had done up to now. No concentration panel (no
contractor/applicant field), no build-time or unit-economics panel (no
completion date, no cost).

The other half of that earlier evaluation — Lachine and Saint-Léonard
boroughs excluded over an in-progress system migration — turned out to be
**stale**, the same pattern as Ottawa's rejection the pass before it: the
dataset's own methodology page still says their data "n'est pas disponible
actuellement", but checked live, both boroughs have permits dated exactly
as recently (2026-08-24) as an actively-updated borough like Le
Plateau-Mont-Royal. The migration evidently finished and nobody updated the
caveat text; both boroughs are included here. One data-quality note carried
into the docstring rather than silently worked around:
`description_type_batiment` carries real casing duplicates across boroughs
(`"Commercial"`/`"commercial"`/`"Commerce"` all appear as separate values,
since each borough's service counter enters data somewhat independently,
per the dataset's own methodology text) — normalized to uppercase for
grouping rather than picking one casing arbitrarily. Also used this pass to
fill in two gaps in the module docstring's top-level city roster and
per-city SOURCES list that Ottawa's own addition had left behind — its
SOURCES entry and full seven-city count were missing, added now alongside
Montreal's. Verified live across all seven cities plus Quebec (a province,
no CMA match): zero console errors, Montreal's areas panel renders as
"Permits by borough" in plain counts rather than "$M", processing panel
populated, concentration/build-time/econ correctly absent. See
[docs/CONSTRUCTION.md](docs/CONSTRUCTION.md) and
`Python/municipal_permits_etl.py`'s module docstring for the full writeup.)

Same day, eighth pass: **Halifax added as an eighth city**, again on a field
list the user supplied directly from the source
(`data-hrm.hub.arcgis.com`). This turned out to be the cleanest dataset of
any city built this session: a plain Esri TABLE (no geometry at all —
`Community` is the only geography, unlike every other city here, which all
have at least lat/long), 18,817 rows since 2020-12, small enough to page
raw like Mississauga. `Estimated_Project_Value` is populated on 99.3% of
rows with none of Ottawa's fee-schedule clustering or Mississauga's need
for a scope filter to fix physically-impossible figures — the cleanest cost
field found across all eight cities. `Net_New_Units` is pre-computed and
100% populated, so unlike Mississauga's RES_UNITS or Calgary's
housingunits, no derivation was needed. A genuine three-date chain
(submission/issuance/completed, zero negative-day rows on either interval,
checked live) gives Halifax both a processing-time and a build-time panel
on top of a real unit-economics table — Mississauga's combination, but
built on materially cleaner underlying data, so unlike every other city's
unit-economics panel this session, this one needed no data-quality caveat
in its scope note.

`Occupancy_Type = 'Residential Use'` was used to scope unit economics
instead of `Type_of_Structure` alone after checking live and finding a
permit with `Type_of_Structure = 'Dwelling - Single Detached'` and
`Occupancy_Type = 'Garage'` — an accessory structure on a residential lot,
not a home, which the occupancy field correctly excludes and the structure
field alone would not have. `Building_Footprint_Area` turned out to be in
square metres, the same unit-mixing trap hit on Mississauga and Ottawa's
2026 file — caught the same way, by checking sample rows' magnitudes
against known real building sizes before trusting the field, not after.
The user also flagged `Most_Recent_Inspection`/`Inspection_Outcome` as
worth checking for a richer external dataset; checked live and it's just
this same permit's own current inspection stage/result, no external
inspections table found — not built into a panel, since a status snapshot
doesn't trend the way a date interval or dollar figure does, and forcing
one would manufacture insight the data doesn't support. No concentration
panel: no applicant/contractor field exists in this schema at all.

One geography note worth keeping: Halifax Regional Municipality's boundary
is unusually close to its full CMA (the amalgamated former cities of
Halifax and Dartmouth plus surrounding county), so its cross-check line
should track the metro figures elsewhere on the page far more closely than
most cities here — closer to Calgary's ≈88%-of-CMA case than to
Vancouver's or Toronto's fraction-of-CMA case. Verified live across all
eight cities plus Nova Scotia (a province, no CMA match): zero console
errors, Halifax's areas panel correctly dollar-ranked (unlike Montreal's
count-only panel from the pass before it), processing/build-time/econ
panels all populated, concentration correctly absent. See
[docs/CONSTRUCTION.md](docs/CONSTRUCTION.md) and
`Python/municipal_permits_etl.py`'s module docstring for the full writeup.)

Same day, ninth pass: **Winnipeg added as a ninth city**, again on a field
list the user supplied directly from the source
(`data.winnipeg.ca/.../it4w-cpf4`). This is the last of the eight CMAs this
page tracks to get a matching city-level permit desk — Montreal was passed
over in an earlier evaluation and added anyway earlier this same day, so
Mississauga (inside the Toronto CMA) is now the only city here without its
own CMA. Socrata SoQL, server-side aggregation like Calgary, 162,558 rows
since 2010 — the deepest history of any city here besides Montreal.

**No cost field at all**, disclosed plainly in the dataset's own
description ("containing most information about the permit WITH THE
EXCEPTION OF declared construction value"), matching it to a separate
aggregate dataset (by year, neighbourhood and permit type; single-permit
cells have their value stripped for privacy and rolled into a "WINNIPEG
OMITTED CONSTRUCTION VALUE" bucket) with no permit-level key to join back
to individual rows — same reasoning as Montreal not using its own separate
stats file, so areas/work/use panels here are ranked by permit count, the
second city on this page where that's true. What's unusually clean instead:
`applicant_business_name` carries real, unredacted business names (Qualico
Developments, A&S Homes, Randall Homes, Kensington Homes, all genuine
Winnipeg builders) with none of Ottawa's placeholder-redaction pattern
(`CONTRACTOR UNKNOWN`/`***CONTRACTOR***`) — checked live, the only
non-name value found was a genuine blank, so the concentration panel here
needed no placeholder-string filtering at all, unlike every other city
with one. A genuine three-date chain (application received/issued/final,
100%/100%/91.6% populated, only 3 and 30 negative-day rows respectively out
of 162,558) gives both a processing-time and a build-time panel, computed
entirely server-side via SoQL's `median()` and `date_diff_d()` — the same
mechanism Calgary already used, so no new query pattern was needed.

One caveat disclosed on the dataset's own page, not found by inspecting the
data itself: the city revised its dwelling-unit counting methodology and
states plainly that "data before November 14, 2022 has not been updated"
to match, so `dwelling_units_created` before and after that date may not be
perfectly comparable. Stated in the card's quality note rather than
silently plotted as one continuous series implying full comparability.
Verified live across all nine cities plus Manitoba (a province, no CMA
match): zero console errors, Winnipeg's areas panel correctly count-ranked,
applicants panel populated with contractors correctly absent (Winnipeg has
an applicant field but no separate contractor field), processing/build-time
panels populated and plausible, unit-economics correctly absent (no cost
data). See [docs/CONSTRUCTION.md](docs/CONSTRUCTION.md) and
`Python/municipal_permits_etl.py`'s module docstring for the full writeup.)

Prior update **2026-08-31** (**Heat Pump Explorer** — the "potential AC" cooling
scenario, built end to end: what a home without AC would emit/cost if it got
one, and how a standard AC compares to a heat pump for cooling specifically.
**Now wired into the live page**, not just the data layer: an opt-in "Show
potential AC" toggle adds a cooling section (load-vs-temperature chart,
estimated peak/energy/balance-point KPIs, and a standard-AC-vs-selected-unit
kWh/GHG/$ comparison, with an honest "no cooling curve for this unit"
fallback for the 4 of 9 cells without one) plus matching Simple/Advanced
methodology copy stating the SEER-badge caveat in plain language. `engine.js`
gained `solveCoolingBalancePoint()` (a live, in-browser port of the Python
CDH-inversion solve, run against the actual TMY series rather than a
precomputed grid) and `simulateCooling()` (the cooling-side hourly
load→capacity→COP→kWh/GHG/$ pass, mirroring `simulate()`'s heating pass).
One chart-scaling fix during testing: a mild-summer city's design cooling
temperature sits close enough to the fixed 25°C indoor anchor (Vancouver:
25.7°C) that `UA_cool` — inversely proportional to that gap — blows up, so
the chart's hot-end axis is now capped near each city's own design cooling
temperature rather than a fixed ceiling, instead of extrapolating into a
climatically-meaningless range.

Real ERS fields did almost all the work, replacing Phase 0's assumed-SEER
calibration for the peak/energy inputs. **Peak heat loss correlates with peak
cool loss** (r=0.683, R²=0.467, n=209,272 homes pooled across 14 cities) —
`cool_peak_kW = 0.2789 × heat_peak_kW + 1.3254` — which is what removes the
need for a separate AC-sizing control. **Peak cool loss correlates with
annual cool energy** far more strongly than annual heat and cool energy
correlate with each other (r=0.778 vs. only ~0.2–0.25) — used as a
through-origin ratio, `annual_cool_kWh = 838.3 × cool_peak_kW`. Both,
plus the same CDH-inversion balance-point solve already built for real
cooling data, are folded into `build_city_house_profiles.py` as new
`cool_peak_est_kW`/`cool_energy_est_kWh`/`balance_point_Tc_est_C` columns —
populated for every heating-solved home, not gated on real cooling fields,
so a no-AC home still gets a "what would adding AC do" estimate. Along the
way, confirmed `AIRCOP` (Coefficient of performance for A/C system) is a
real, 100%-filled-among-cooling-users field the earlier cooling-energy basis
had missed, fixing an inconsistent (consumption vs. delivered) energy
comparison; and confirmed `ThermostatCooling` is a fixed 25.0°C HOT2000
constant (zero variance across 620,107 records), not an audited value.

A standard-AC baseline (Goodman GLXS4B 3-ton, `build_ac_curves.py` →
`ac_curves.json`) covers 92–99.5% of real homes across all 14 cities at
their own design temperature. Real cooling curves now exist for **5 of 8**
`hp_curves.json` heat pump models and **5 of 9** live `hp_cell_curves.json`/
`hp_tier_selection.json` cells (a separate, newer pipeline the live page
actually reads — cooling data added to one file does not reach the other).
Two vocabulary misses were caught and fixed same-day: Carrier's cooling
tables are titled "DETAILED COOLING CAPACITIES" (indexed by "condenser
entering air temperature"), and Daikin's don't say "Outdoor Ambient
Temperature" either — both were initially reported as having no cooling
data, which was wrong.

**Headline finding: SEER/SEER2 badges don't predict which unit actually uses
less electricity in a real climate.** GREE (SEER 18) and Tosot (SEER2 15.5)
both carry a higher badge than the Goodman AC (SEER2 13.8–14.5) but sit
*below* it in COP across most of the hot range once plotted against real
measured points — confirmed on three independent real units (Fujitsu
ducted, Tosot, GREE), not a one-off. Reconciled with an actual AHRI
210/240 bin-method reconstruction: the standard's published temperature
bins barely sample above 35°C (the hottest bin, 102°F, is only 0.4% of
assumed cooling hours), while a real TMY-integrated calculation is
dominated by the hottest hours near each city's own design temperature —
exactly where these curves diverge from their badges. Also caught and
fixed same-day: an early chart showing a heat pump beating the Goodman AC
below ~22°C turned out to be an artifact of flat-clamping Goodman's curve
below its published floor instead of extrapolating its own real (rising)
trend — linear-extrapolating instead puts Goodman ahead at every checked
temperature. See
[HeatPump/METHODOLOGY.md](HeatPump/METHODOLOGY.md) "Cooling / potential AC
scenario" and "Cooling curve library expanded, and SEER2 badges don't
predict real-TMY performance.")

Prior update **2026-08-31** (**Construction Tracker** — new **"Builder confidence"**
card: CHBA's Housing Market Index, a quarterly builder-sentiment survey (0–100
scale, 50 = neutral), national single-family and multi-family lines from
Q1 2021 to the current quarter, plus a regional tile for Ontario/BC/Prairies/
Atlantic views. Same cite-only, hand-transcribed pattern as Greener Homes and
CHBA Net Zero, added to `Python/cited_figures.json` as a new `chba_hmi` source
— `cited_figures_verify.py` needed no code change, since it already loops
generically over every source. Two findings shaped the build. **(1)** CHBA's
HMI page publishes only static chart images, no data file; a check of their
auto-generated alt text (an obvious shortcut around reading 21 quarters of
prose) found it unreliable — one chart's alt text swapped which
selling-condition category a percentage belonged to (a 46% "average"/Fair
reading mislabelled as "Good"), another mislabelled a quarter's index value
by a full year. The card is built entirely from the page's own "Key Findings"
narrative text instead, cross-checked quarter to quarter for
self-consistency. **(2)** CHBA's only regional cuts are Ontario, British
Columbia, Prairies (Alberta+Saskatchewan+Manitoba combined) and Atlantic
Canada (NB+NS+PE+NL combined) — no Quebec, no territories, no per-province
split within the two aggregate regions. An early draft labelled the regional
tile with this page's own (single-province) geo label, e.g. "Nova Scotia
single-family HMI," when the figure underneath is really the four-province
Atlantic aggregate — caught in browser verification, fixed by labelling the
tile with the actual CHBA region ("Atlantic Canada (NB+NS+PE+NL)") and adding
a note whenever a Prairies/Atlantic province is selected. Regional index
figures also only go back to 2024 Q2, since CHBA reported them as qualitative
description (not index numbers) before that quarter, and multi-family
Atlantic Canada is never reported in any quarter checked — both gaps are
shown as `null`/"not reported" rather than interpolated or omitted silently.
Verified live via a local static server across Canada/Ontario/Quebec/Nova
Scotia/Alberta/Toronto: card renders, hides its regional tile correctly for
Quebec with an explanatory note, shows "not reported" for multi-family
Atlantic, zero console errors. Pre-existing and unrelated: `chba_net_zero`'s
transcription is now stale against CHBA's live page (3 of 7 verify strings no
longer match) — flagged, not fixed, since it wasn't part of this pass. See
[docs/CONSTRUCTION.md](docs/CONSTRUCTION.md).)

Same-day follow-up **2026-08-31** (**Construction Tracker** — the flagged
`chba_net_zero` staleness fixed: CHBA updated the page 2026-08-28 (3,979 →
**3,982** labels, all three new labels single-detached houses; every other
figure unchanged). Re-transcribed and re-verified live. Along the way,
evaluated CHBA's other Net Zero page (chba.ca/net-zero/) at the user's
request — it embeds a Power BI report with a per-builder map/table (units,
province, city, and a **named contact with personal email and phone**, one
row per company). Declined to build against it: extracting name/contact-level
rows would cross the same line this project already held for CaGBC's project
database, more so — it's individual people's contact details, not an
aggregate. Also spent real effort trying to drive the report's custom filter
dropdown via browser automation to get *only* a per-province unit total (no
names); the slicer proved too unreliable to trust — two different automated
attempts at the same province (BC) returned two different numbers on
different tries, so nothing from that report shipped. `chba_net_zero`'s
`note` field now documents the Power BI report and why it's excluded, for
the next time this comes up.)

Prior update **2026-08-28** (**Construction Tracker** — reversal of a Tier-3 "not
built" call. Tier 3 (2026-08-27) declined to build a CaGBC LEED/Zero Carbon
count on the assumption that their project database required a sign-in and
carried a licence restriction. Both premises turned out to be wrong on closer
check: the project-search tool at `leed.cagbc.org` needs **no sign-in** and
exports its full national list, and CaGBC's actual Terms and Conditions page
plus their Member Terms & Conditions PDF — both read in full, not just
searched — say nothing about the project database, scraping, or data reuse.
The Member Terms PDF turned out to be entirely about certification-*mark*
misuse (a builder falsely claiming certification), not data. The generic
"All rights reserved" site footer is the same boilerplate on every page,
including the Privacy Policy — not a term attached to the export function.

Built a new **"Certified green buildings"** card from a manual export
(`project_profile.csv`, 10,670 rows, gitignored — no API exists, so this is a
point-in-time snapshot re-exported by hand): 9,952 LEED-family registrations
(7,541 certified) and 461 certified Zero Carbon Buildings, nationally, with a
per-province breakdown as ranked bars and a province-specific stat tile. One
data-quality finding worth keeping: "certified" means *has a certification
date*, not *has a certification level* — 152 rows carry a date but a blank
level, and every one of them is Zero Carbon (which is pass/fail and never
issues a Gold/Silver/Platinum-style level). Filtering on level would have
silently zeroed out every Zero Carbon certification. A second: one row
declares a 399,420,000 sq ft floor area (a waterfront redevelopment, clearly
a unit or entry error) — excluded from the floor-area sum via a 10M sq ft
plausibility gate, counted and reported, never silently dropped.

Published as **aggregates only** — province/program/year counts and a floor-
area sum, never a project name or address — deliberately more conservative
than the licence question alone required, because a compiled list of names
and addresses sits closer to what CaGBC actually built than any single fact
in it does. Verified in the browser on desktop and mobile across
ca/on/pe/toronto: card renders, hides its province tile correctly for Canada
(no province code to key into), and a run of the apostrophe through a
double-escaping bug (`\u2019` written literally into the page instead of
being interpreted) was caught and fixed before shipping. See
[docs/CONSTRUCTION.md](docs/CONSTRUCTION.md) and `Python/cagbc_leed_etl.py`'s
module docstring for the full terms-of-use walkthrough.)

Prior update **2026-08-27** (**Construction Tracker** — Tier 3, the last tier of the
data-sources expansion. Three new pipelines and one settled question.

**Inside one city** (new advanced section, Vancouver and Toronto): permit-desk
data straight from the city portals — value by neighbourhood/FSA, work-type
split, and a city-vs-metro cross-check against the StatCan CMA series. Two
cities on purpose; Calgary and Ottawa are reachable and deliberately skipped,
because four schemas is maintenance rather than insight. **Large buildings,
measured** (Ontario/Toronto only): Ontario's EWRB disclosure — median
weather-normalized energy intensity by building type for every Ontario building
over 100,000 sq ft, about half of it multifamily, which is the MURB stock the
Retrofit Explorer models from the other side. **CHBA Net Zero labels** join the
Greener Homes card as cited figures.

Four findings worth keeping. **(1)** The provincial under-construction gap is
settled: CMHC's own HMIP `ExportTable` endpoint returns *"This data series is
now archived."* for Ontario July 2026, while December 2022 returns real data
(162,813 units) and Ontario *starts* for July 2026 returns real data. So it is a
genuine CMHC discontinuation, not a StatCan publication decision — the Tier-1
hypothesis that HMIP might still carry it is disproved and the caveat stays.
**(2)** Toronto's `EST_CONST_COST` is the literal string `DO NOT UPDATE OR
DELETE THIS INFO FIELD` on ~45% of rows, so its dollar totals are an undercount
of unknown size; its counts and dwelling-unit series are sound, so the
cross-check compares Toronto on units created and Vancouver on permit value —
each city on what its data can actually support. **(3)** Toronto needs *both*
permit sets: "cleared" means closed, so alone it is badly right-censored (74
permits in the final month against ~375 two months earlier); active + cleared
gives a steady ~3,000/month. **(4)** EWRB is self-reported and published
uncleansed — 27,685 of 30,693 rows usable, with every gate counted on the card,
and the Data Quality Checker flag reported but never used as a filter because it
records that a reporter ran a tool, not that the data passed.

Deliberately **not** shipped: any CaGBC LEED or Zero Carbon count. CaGBC
publishes no running total and its project database is behind a sign-in, so
there is no figure that could be verified the way the CHBA and NRCan ones are —
getting one means asking CaGBC. The Efficiency Canada code-stringency column
proposed in Tier 2 is also still unbuilt for the same reason. `greener_homes_*`
generalised to `cited_figures_*` now that two publishers use the pattern.
Verified in the browser on desktop and mobile across ca/on/bc/toronto/vancouver:
20 charts, no console errors, no horizontal overflow, and each new card
correctly hidden where its data does not exist. See
[docs/CONSTRUCTION.md](docs/CONSTRUCTION.md).)

Prior update **2026-08-27** (**Construction Tracker** — Tier 2 of the data-sources
expansion, same day as Tier 1. Four additions: a **"Did it sell?"** card
(34-10-0149 absorptions vs unsold inventory, with a months-of-inventory mode)
closing the pipeline past completions; **"The cost of a building, by trade"**
(18-10-0289 BCPI by CSI division — envelope, windows/doors, HVAC, electrical,
concrete, wood — with a building-type picker); a **rental vacancy column** on
the CMA table (34-10-0127); and a **Greener Homes program card** showing grants,
per-province totals and the top-5 retrofit *measure counts*, which are directly
comparable with the ERS-derived measure counts on the Retrofit Explorer.

Three findings shaped the build. **(1)** The BCPI divisions all share one
reference period, **2023 = 100** — verified, the 2023 quarterly mean is 100.00
for composite, wood, concrete and envelope alike. A first draft re-based every
line to 2017 = 100; that was wrong and was removed, because it amplified
whichever series started lowest (wood, off a lumber-cycle trough) and read as a
claim about the trades rather than about their starting points. Plotted as
published, the interesting result is that **HVAC** has run furthest above the
all-trades average since 2023 — which bears directly on heat-pump economics.
**(2)** 34-10-0149 and 34-10-0127 are **CMA tables with no provincial members**,
so the absorptions card shows metros directly, shows the all-CMA aggregate for
Canada (labelled, since it excludes smaller centres and rural areas), and hides
itself on a provincial view rather than inventing a number. **(3)** NRCan's
Greener Homes page publishes no data file, and each province's *name follows its
numbers* in document order — a positional parser pairs them off by one and
silently mis-assigns every province. So those figures are **hand-transcribed**
into `Python/greener_homes_data.json` on `main`, and a new
`greener_homes_verify.py` asserts every one still appears verbatim on the live
page before publishing; it runs `continue-on-error` in the monthly workflow so a
newer NRCan update raises a warning instead of taking the data refresh down.

BCPI division detail ships as a **separate `construction_json/bcpi.json`**
(170.6 KB, 630 series) that the page lazy-loads, because it outweighs the whole
of context.json and only one advanced card reads it. `context.json` 160 KB →
201 KB, 320 series. Verified in the browser on desktop and mobile across
ca/on/pe/ns/toronto: absorptions correctly hidden for provinces, BCPI falling
back to the 15-CMA composite for PEI and Canada, vacancy column sorting, and the
verifier negative-tested to confirm it exits non-zero on a stale figure. See
[docs/CONSTRUCTION.md](docs/CONSTRUCTION.md).)

Prior update **2026-08-27** (**Construction Tracker** — Tier 1 of the data-sources
expansion. Three new StatCan series join the context ETL and two new page
sections are built on them, plus one section that needed no fetch at all.
**"What it costs"**: the old trailing-12-month investment-by-work-type chart
(2017-start, nominal-only) is replaced by the **Housing Economic Account**
(36-10-0677) — new construction vs renovations vs ownership transfer costs,
annual from **1961**, with a nominal/real toggle; and a new **renovation price
index by project** (18-10-0286) showing heat pump, furnace, windows, solar
panels and roofing against the all-projects composite. **"How green is what we
build"**: housing starts against the median EnerGuide rating of new homes
evaluated in the same province and year, read straight from the existing
`newhomes_json/` — no new pipeline. Advanced mode gains **construction job
vacancies and average offered wage** (14-10-0442) beside the employment-vs-
backlog chart, because employment alone can't separate a labour shortage from a
demand slump.

Two coverage rules drove real UI decisions rather than footnotes: 18-10-0286
publishes its 45 project types for **CMAs only** (provinces and the national
composite carry the composite alone; PEI has no member), so that card has its
own metro picker instead of following the page geography into an empty cell;
and EnerGuide covers only the evaluated share of new construction, so years
under 30 evaluations are suppressed, provinces with fewer than three usable
years are hidden outright (Quebec, which has two), and the note reports the
latest median with its sample size rather than a first-to-last delta — these
medians are not monotonic and an endpoint change would imply a trend the data
doesn't show. Also re-verified the documented provincial pipeline gap against
34-10-0136 and 34-10-0143 through 2026-07: still null for every province *and*
Canada, including the Toronto and Montréal members inside 0143. The caveat
stands. One shared-helper change: `extract_table()` takes an optional `floor`
and normalizes annual `REF_DATE` from bare `YYYY` to `YYYY-01` before the floor
comparison — without it the 1990 default trim would have silently dropped a
year of the annual cube. `context.json` 79 KB → 160 KB, 287 series. Verified in
the browser on desktop and mobile across ca/bc/qc/pe/toronto, no console errors.
See [docs/CONSTRUCTION.md](docs/CONSTRUCTION.md).)

Prior update **2026-08-27** (**Heat Pump Explorer** — new collapsible "The 8,760
hours behind these numbers" section, immediately before the methodology
accordion: a 16-column, row-per-hour readout of the full simulated year
(outdoor temp, load, run status, and COP/capacity/energy/GHG/cost split by
baseline/heat pump/backup), with a month filter and a full-year CSV export.
No new calculation — the heat pump's per-hour COP and capacity were already
computed inside the dispatch loop and discarded after use, now captured
into the engine's returned `hourly` object; per-hour cost reuses the
existing `buildHourlyCostSeries()` the cost chart already relies on, so the
table can't drift from it. Building it surfaced a real bug, fixed same
pass: the sticky header's tinted group-background colours were low-alpha
`rgba()` with nothing opaque behind them, so scrolled body rows showed
through the header on scroll; fixed by compositing the tint over an opaque
base in the same `background` shorthand. See `HeatPump/METHODOLOGY.md`'s
2026-08-27 "Full hourly data table" entry.)

Same-day follow-up **2026-08-27** (**Retrofit Insights** §10 reworked from user
feedback: a **building-type multi-select filter** (pills, all on by default)
now drives every chart/table in the section; the old "all cases" table became
a **project summary table** (Project, Location, Year Built, Status, Building
Type, Energy Saving, Retrofit Type, Performance Level); and a new **R-value
slopegraph** — one small chart per envelope component (attic/roof, wall,
foundation wall, each on its own R-value axis since the scales don't share
well), pre-retrofit axis on the left and post on the right, one line per
project coloured by that project's overall energy saving % — sits above a
matching **envelope-values table** (the chart's data, in table form, limited
to the ~34 cases reporting at least one envelope R-value). Hand-built inline
SVG for the slopegraph, same pattern as the choropleth map elsewhere on this
page (colours resolved from `readPalette()` and baked in at render time, so
the section re-renders on every theme change rather than relying on CSS
`var()` inside the SVG string). Filter state persists across a theme toggle.)

Same-day follow-up **2026-08-27** (**Heat Pump Explorer** — performance fix
for the new hourly table, reported live within hours of shipping: the table
was rebuilding all 8,760 rows of DOM on **every recompute** while its
section stayed open, not just once when opened, so leaving it expanded
turned every slider drag or dropdown change into a 5–10s stall. Fixed with
virtualized rendering — only the ~30–40 rows inside the scroll viewport
are ever in the DOM, via two spacer `<tr>`s sizing the rest of the
scrollbar for it; row *data* (`hdtRows`, plain JS objects) still rebuilds
in full every time, only the DOM render is windowed. Measured live on the
deployed page: table-render cost dropped from ~780ms to ~60ms, and the
added cost of having the section open during a recompute dropped from
~780ms+ to ~190ms (on top of the page's pre-existing ~440ms recompute cost
from its own chart redraws, unrelated to this feature and unchanged).
Verified against the exact reported scenario — table open, then a real UI
dropdown change (baseline fuel) — with no perceptible lag and correct
table contents. See `HeatPump/METHODOLOGY.md`'s 2026-08-27 "Full hourly
data table" entry, updated in place.)

Prior update **2026-08-25** (**Retrofit Insights** — new §10 "One house at a time":
a second, external dataset alongside the ERS-derived numbers. Scraped Retrofit
Canada's case-study library (48 self-submitted deep/net-zero home retrofits,
shared under their site's open-content terms) via new
`Python/retrofit_casestudies_scrape.py` into `retrofit_casestudies_json/_all.json`,
filtering out 7 non-residential/non-Canadian cases (documented, not silently
dropped) to 41. Shows min–median–max ranges (R-values, ACH50, EUI, GHG/energy
savings) by performance-level bucket, plus a sortable table linking out to each
source; kept deliberately separate from and never averaged with the ERS numbers
elsewhere on the page. See `docs/RETROFITS.md`'s 2026-08-25 changelog entry.)

Prior update **2026-08-24** (**Heat Pump Explorer** — Ontario grid-EF surface
temperature proxy switched from Toronto to London. Toronto's 2020–2026
weather record only reaches −22.6 °C (5 hours colder than −22 °C), so the
surface's coldest `coarse_t` bins were thin/absent and Step 5's grid-carbon
chart flatlined below −22 °C (fell through every thin-bin fallback to the
flat global-mean shape ratio). Checked against IESO's hourly generation
data first: London tracks province-wide gas output as tightly as Toronto
does (winter `corr(temp, gas MW)` = −0.420 vs −0.419; both track within
1–3 °C of Toronto at the actual top-30 gas-output hours 2020–2026) while
reaching −24.8 °C with 44 hours below −22 °C — Ottawa was also checked and
rejected as colder but a worse demand proxy (runs 5–10 °C colder than
Toronto/London at the same peak-demand hours). `ef_surface_on.json`
regenerated (`build_ef_surface.py`, `PROVINCES["ON"]` now `London`);
reconstruction validation still passes (worst per-year diff 5.2%, within
the ±10% tolerance). Separately, added cold/warm-tail **extrapolation** to
the browser engine (`extrapolateShape()` in heatpump.html) so any
temperature beyond the surface's thin-bin edge — for any province, not just
ON — gets a least-squares trend fit through the tail's 6 most extreme
sufficiently-sampled `coarse_t` bins instead of snapping to the flat global
mean; a naive 2-point edge slope was tried first and rejected as too noisy
(outermost bins have the fewest hours). `METHODOLOGY.md` "Province vs. city
temperature" and "Thin-bin fallback" sections updated with the correlation
check and the extrapolation method.)

Prior update **2026-08-21** (**Heat Pump Explorer** — four UI/methodology fixes
from user testing. (1) **Month/week zoom** added to all 7 "Full year"
charts (weather, load, equipment, energy, grid GHG, emissions, cost): a
per-chart month dropdown (day-by-day view) and week dropdown (hour-by-hour
view), independent per chart, built on a shared `sliceRange()` helper so
axis ticks and hover tooltips report the real calendar date even when
zoomed. (2) **Propane backup** added to the "Backup heat" dropdown — the
simulation engine already supported it (90% AFUE) but it wasn't selectable;
also fixed a latent `stepCurves().isFuel` bug that would have shown propane
backup as if it were electric (no switch-over line/label) had it shipped
without the check. Backup AFUE (gas 95% / oil 85% / propane 90%, fixed, not
user-adjustable) documented in the methodology under "Energy purchased" for
the first time. (3) **Two backup colors**: fossil-fuel backup (gas/oil/
propane combustion) and electric-resistance backup now render in distinct
colors (new `--backup-fossil` / `--backup-elec` tokens in
`assets/site-theme.css`, themed for light/dark/colour-blind) instead of
sharing one amber swatch, with the fuel name threaded through every legend
("Backup — propane") instead of a bare "Backup". (4) **Upstream-methane
hourly bug fixed**: the "Upstream losses" toggle's methane-equivalent adder
was only ever added to the *annual* total (`m_base_ch4`/`m_proj_ch4`), never
to the *hourly* emissions arrays (`h_base_ghg`/`h_bk_ghg`) that every
temperature/weighted/full-year chart reads — so those charts showed only
line-loss's effect on electricity when the toggle was flipped, never
methane's effect on gas, even though the annual total was already correct.
Fixed by folding each hour's methane contribution into the hourly series
too; verified live that `sum(hourly.base_ghg_kg) === base.ghg.total` exactly
(no double-count) and that toggling upstream now moves the hourly sum
(+4,428 kg/yr on a gas baseline in Ottawa). Also added the switch-over/
hard-cutoff reference lines and a green/backup-color stacked split to the
emissions "By temperature" view, matching the equipment chart's convention.
Verified live via a local static server (screenshots render blank in this
sandbox's preview pane per the known no-rAF quirk — confirmed via DOM/JS
inspection instead): engine self-test still passes, zero console errors
across all 7 charts' daily/hourly/week/month combinations.) Same-day follow-up
(**Heat Pump Explorer** — chart-readability pass, also from user testing.
**(a)** Y-axis titles shortened across every chart to a plain `<unit> <what>`
(e.g. "kg CO₂e/hr", "kWh purchased"), with the fuller explanation left to
each chart's existing note paragraph rather than crammed into the axis
label. **(b)** Every axis/label now says *which* quantity it is — "heat
needed" (load, Step 2), "heat delivered" (equipment, Step 3), or "purchased"
(electricity/fuel bought, Step 4) — so the three are never ambiguous against
each other. **(c)** Full-year day-by-day views for the three *quantity*
charts (Step 4 energy, Step 6 emissions, Step 7 cost — kWh/kg/$) now show
each day's **total**, not its mean; the three *rate* charts (Step 2 load,
Step 3 equipment, Step 5 grid intensity — kW/°C/g-per-kWh) correctly keep
the daily mean, since summing a rate isn't meaningful. New `toDailySum()`
alongside the existing `toDaily()`, selected via a `sumMode` flag on
`sliceRange()`. **(d)** Step 6's "By temperature" view was missing the
zero-heat/design/switch-off reference lines that Steps 1, 2 and 5 already
draw — it turned out a shared `drawStepRefLines()` helper already existed
(built for Step 5) and Step 6 just wasn't calling it; now it does, replacing
the equipment-style switch-over/HP-cutoff pair that didn't belong on a
weather-exposure chart. **(e)** Final numbers section tidied: the
before/after bar rows (`.beforeafter`/`.ba-row`) were each their own
independent CSS grid, so sibling rows' label columns sized to their own
text and the bars started at different x-offsets row to row — moved the
grid to the shared parent with `.ba-row{display:contents}` so all rows
share one set of column tracks. The "Annual operating cost" card also
repeated the same two dollar figures twice (once in the bar chart, again in
a text list below) — the text list is gone, the bars gained a third
"Saves/Costs" delta row (matching the emissions card's existing three-row
convention) and each bar's sub-detail (kWh/m³ breakdown) moved into a
`<small>` under its label instead. **(f)** Added a "Download one-page
summary" button (Final numbers section) that populates a dedicated
`#print-summary` block — scenario recap (every dropdown/slider's current
value, read live from the DOM), the verdict headline, the KPI tile strip,
the energy chart rasterized to a PNG via `canvas.toDataURL()`, and the
emissions/cost bars, with page CSS vars force-overridden to light-theme
values so it prints correctly regardless of the page's current theme — then
calls `window.print()`. No PDF library, no server round-trip: the browser's
own print-to-PDF is the only dependency-free option under this repo's "no
build step, no external runtime deps" rule, so that's what "download" means
here (Save as PDF in the print dialog). Verified live: all DOM content
populates correctly (selections table, 7 KPI tiles, verdict text, rasterized
chart image, both bar sets), the `@media print` rule is present and scoped
to `#print-summary`, zero console errors.) Prior pass
**2026-08-19** (**Heat Pump Explorer** — three result-affecting
defects fixed, found by an external methodology audit and each verified
against the code before acting (the same audit's three "P0" retrofit findings
were checked and rejected as false positives — already-correct behaviour it
couldn't see because the reviewer had no access to `assets/retrofits.js` or
the Python). (1) **Upstream-oil adder removed**: `buildOpts()` passed
`oilUpstreamFrac: 0.12` unconditionally, so "Upstream & grid losses: **No**"
never zeroed it, despite the page stating that switch zeroed every upstream
term; the 12% had no source anywhere in the repo and no propane equivalent.
Removed outright — option, accumulator and `upstream_oil` output field — not
merely defaulted to zero, so it cannot be silently reinstated. (2) **Fuel
constants reconciled with the retrofit pipeline**: combustion factors were
181 / 275 / 214 g CO2e/kWh against `Python/ghg_factors.py`'s
185.4 / 255.4 / 213.6 for the same fuels, each hardcoded beside its own
inconsistent energy content (gas 10.55 kWh/m³, oil 10.0 kWh/L) — and the gas
entry did not reproduce its own stated basis (1.921 ÷ 10.55 = 182.1, not
181). Factors are now *derived* from volumetric factor ÷ energy content, with
both tools reading one set of conversions, and the cost layer's separately
hardcoded oil conversion now reads the engine's exported constant. (3)
**Default grid-basis contradiction resolved**: the page (in two places) and
`HeatPump/METHODOLOGY.md` all described marginal as the default, but
`state.efBasis` has always initialised to `'average'`. Aligned docs to code
by user decision — the tool opens on hourly average, the like-for-like basis
with the studies it benchmarks against, with marginal one click away in
Advanced. Impact: an **oil-heated baseline falls ≈17%** (7.7% from the
factor, the rest from the dropped adder), taking the oil savings headline
from ~46% to **35%**; gas baseline rises ≈2.4% (savings 47→48%); propane
−0.2%. The TAF +65% methane calibration was re-checked under the new
constants and survives (+64.8% → +64.4%); an exact re-solve would give 2.152%
rather than the shipped 2.14%, deliberately left un-retuned rather than churn
every published figure for a rounding-level gain. Verified live: all 15
engine self-test vectors pass (two expected values moved with the constants),
zero console errors, oil path exercised end-to-end through the UI.) Prior
pass **2026-08-12** (**Heat Pump Explorer** — in-page methodology section
rebuilt: reordered to follow the page's own Step 1–7 sequence (was drifting
from it as sections were added over time), all "previously X, now Y" /
dated-correction narrative removed (page states only what's currently
true — the chronological history stays in `HeatPump/METHODOLOGY.md`), long
paragraphs replaced with bullets/tables, every assumption paired with its
source. Three previously-separate analyses folded into the step they
actually support: the ERS per-house balance-point derivation into Step 2
(Heat load), the AHRI/ERS tier-selection method into Step 3 (Equipment),
and the methane leakage map into Step 6 (Emissions) as part of the
upstream-methane term it backs. The three `data-method` info-button jump
anchors (`m-grid`, `m-lifecycle`, `m-methane-map`) were preserved. No
calculation changed — presentation only. Verified live: correct step
order, zero console errors, all jump links resolve.) Prior pass **2026-08-12**
(**Heat Pump Explorer** — line loss made
province-specific, replacing the flat 5%. User's original ask was to apply
ENERGY STAR's 1.83 "source-site" ratio (reasoning: IESO data is generation,
not purchase) — investigated first rather than implemented blind, since 1.83
is dominated by generation *thermal-conversion* inefficiency (already baked
into the grid EF's g/kWh figure) not delivery loss, and applying it would
have double-counted; IESO's own transmission loss is only ~2%, nowhere near
83%. The legitimate version of the concern (generation-basis EF vs.
delivered-electricity purchase) is the existing line-loss term — re-derived
with real province-specific regulator data instead of a flat Canada-wide
estimate: **ON 7.4%** (OEB's audited distributor Total Loss Factor +
IESO's own transmission loss, compounded), **AB 7.68%** and **QC 7.5%**
(both already-blended CEA/Régie de l'énergie figures) — all higher than the
old flat 5%, all dated 2002–2008 sources (best available, flagged as such).
BC/MB/NS/SK keep the 5% fallback (no province-specific source found, no
hourly grid pipeline either). Small impact on already-published benchmark
figures (+2.3–2.6% on the electricity-GHG term only, flagged in the
Phase 7 validation section rather than silently left stale). New standing
rule from this pass: flag inaccessible/unverified sources and shaky
premises before building on them (project memory
`source-access-and-assumption-transparency`).) Prior pass **2026-08-12**
(**Heat Pump Explorer** — tiered electricity pricing
removed by user request: correctly pricing the added heating load within a
tiered plan required assuming a non-heating household baseline (750 kWh/mo
ON, 25 kWh/day QC) this tool has no way to know for a real household.
Removed from `heatpump.html` (tier cost functions, baseline constants,
`tiered` plan-selector entry) and `Python/rates_etl.py` (ON no longer
collects the OEB tiered tariff; regenerated `prices_json/on.json`). Quebec
had no non-tiered plan at all (Hydro-Québec Rate D has no flat residential
option), so rather than leave Quebec's cost card broken, its plan is now
priced at Rate D's tier-2 marginal rate applied to all modelled
electricity — needs no baseline assumption, since any home with a material
electric heating load pushes daily usage past the 40 kWh/day first-tier
threshold regardless of its other draws. `rates_etl.py`'s Montreal
self-check band updated ($150–200, was $120–185) to match. Verified live:
ON shows only TOU/ULO, Quebec's cost card renders with "marginal (top-tier)
plan" and no console errors.) Prior pass **2026-08-12** (**Heat Pump
Explorer** — refrigerant charge mass
replaced with real manufacturer data: found that the spec-sheet PDFs
already on file for capacity/COP curve work (`data/raw/spec_sheets/`) also
list factory refrigerant charge — extracted 6 R-410A and 4 R-454B
data points (model, rated capacity, factory charge, all cited in
`HeatPump/reference/refrigerant_charge_datapoints.csv`) and fit a linear
`charge_kg = a + b × capacity_kW` model per refrigerant, replacing the
prior flat, unsourced 0.250 kg/kW R-410A baseline. Real units run 15–142%
higher than that baseline across the sampled capacity range, and show
smaller units carrying *more* charge per kW — a shape a flat ratio can't
express. R-32/R-290 (no manufacturer data found) still fall back to a
peer-tool ratio, now applied to the new curve's shape rather than a flat
number. Also corrected how the prior GWP sourcing pass was reported: the
primary IPCC AR6 table had returned HTTP 403 to the fetch tool and was
never actually opened, though the writeup at the time said "confirmed" —
user added the PDF to the repo directly, it was read in full, and every
GWP20/GWP100 figure already shipped matches the primary table exactly, to
the decimal. New standing rule saved to always flag inaccessible sources
and weak corroboration explicitly going forward (project memory
`source-access-and-assumption-transparency`).) Prior pass **2026-08-12**
(**Heat Pump Explorer** — refrigerant GWP20 added as a
user toggle: the refrigerant leak term previously only ever used GWP100; a
new "GWP horizon" segmented control (100-yr default / 20-yr) lets a reader
see the near-term-forcing view, matching the horizon the upstream-methane
term already uses. GWP100 values independently reproduced from AR6's own
per-molecule table (GHG Protocol's AR6 reprint); GWP20 values (sourced from
BDA's peer-tool review) cross-checked against a second independent source, a
refrigerant-industry compliance table built for NY State's AR6-20yr mandate
— both confirm the same blend-weighted figures almost exactly. Charge-mass
ratios also spot-checked against generic HVAC density-based line-set-charge
guidance (R-32/R-454B ratios land within ~1-2 points of independent
industry figures). `heatpump.html`, `METHODOLOGY.md` and
`BDA_COMPARISON.md` updated; engine self-tests unaffected (18/18 Python
mirror assertions pass).) Prior pass **2026-08-12** (**Heat Pump Explorer** — real-homes balance-point bug
fix: the per-house "0-heat" balance point in the real-homes explorer
(`house_profiles_<city>.json`) was anchoring its UA calculation on the balance
point being solved for, instead of HOT2000's fixed 21°C indoor design
setpoint — inflating UA and biasing every solved balance point 3-4°C too low
(confirmed on a 10-home Toronto sample), worst for high-loss "worst" homes,
which is why Toronto's worst-house figure (11.5°C) read far colder than
NRCan/CanmetENERGY's comparable published figures (~10-16°C). A regression of
a bug already caught once at the archetype level (see METHODOLOGY.md "UA from
design heat loss"). Fixed in `check_balance_point_k1s.py` and
`build_city_house_profiles.py`; all 14 cities' `house_profiles_*.json`
regenerated (747,829 homes, drop rates unchanged); `heatpump.html`'s
real-homes advanced-methodology text and a new `METHODOLOGY.md` "Real-homes
balance-point fix" section document the before/after math. The fix closes
roughly a third to a half of the gap to CanmetENERGY's figures — the rest is
an already-documented, not fully closable, steady-state/occupant-behaviour
modelling gap, unaffected by this change.) Prior pass **2026-08-12** (**Heat Pump Explorer**: new "Where upstream methane
comes from" section — a Canada map of fugitive oil/gas/coal methane
(NASA GES DISC's Global Fuel Exploitation Inventory, 2016, the newest vintage
at this scope) grounding the page's existing 2.14% upstream-methane lever in
real geography. Shipped, then refined same day across two follow-up passes:
native 0.1° resolution rendered to a canvas pixel buffer (not SVG rects —
doesn't scale to ~115k cells) with oil/gas/coal/total toggle; "background"
cells flagged and shown flat-gray, distinct from the real amber log-ramp
signal, after checking the raw data directly (56–78% of nonzero *gas* cells
share an exact value with other cells — a shared regional proxy rate GFEI
applies where it can't spatially resolve, not real per-cell detail — vs.
~1% for oil), with a toggle to hide them; cropped to a unioned Canada
boundary polygon (built from the existing FSA choropleth geometry plus
Yukon, which was missing from it) instead of a raw bbox that bled into the
US, with a simplified version of the same polygon drawn as a reference
outline; and a sinusoidal (Sanson-Flamsteed) projection replacing the flat,
unnaturally-wide-at-the-north raw grid, itself swapped same day for an
**Albers Equal-Area Conic** projection (Canada's standard thematic-map
parameters) after comparing six candidates side by side — Albers over the
more familiar Lambert Conformal Conic specifically because this map's
colour encodes emissions *per km²*, and Albers (unlike Lambert) keeps
on-screen area proportional to real land area. A conic projection needs a
real per-pixel inverse-project-and-sample remap rather than Sinusoidal's
per-row scale; that lookup table is built once per data load and reused by
every re-render and by hover (~60ms build, ~15-20ms per toggle, measured
in-browser). Section (and "What real homes in \<city\> look like") now
`<details>`-collapsed by default, with the map's ~3MB JSON fetch deferred
to first expand; default view is gas + background hidden, the most
legible combination. New `Python/gfei_ch4_extract.py` +
`Python/canada_boundary.py` pipeline steps. Explicitly labelled as a bundled
oil+gas+coal fugitive-emissions layer, not a pipeline-only one, despite
starting as "pipeline GIS data" in an earlier session — see
`HeatPump/METHODOLOGY.md`'s "Methane leakage map — GFEI 2016" entry and its
two same-day follow-ups.) Prior pass **2026-08-09** (**Heat Pump Explorer** — theme parity: brought the
page onto the shared `assets/site-theme.css` system so it finally carries the
light/dark/colour-blind toggle every other advanced page already had. Deleted
its duplicated, drifted light-only chrome (reset, `:root`, header, hero,
`.info-btn`, footer) in favour of the shared file; reclassified every legacy
`var(--white)` to `--card` (surfaces that must invert) or `--on-navy` (text on
navy), added a themed `--brown`, and pinned the spec-table's fixed-pale legend
cells to dark text so dark mode stays legible; restructured the header to the
shared `.header-left`/`.header-title` pattern plus the 3-icon theme pill; and
added the pre-paint theme script + `setTheme`/`syncThemeButtons`/
`redrawAllCharts` (charts already read colours through a `css()` helper, so a
toggle just rebuilds them). The bespoke "Advanced settings" disclosure was kept
as an intentional exception rather than swapped for the shared Simple/Advanced
pill. Verified in-browser across all three themes — chrome inverts, the SVG
charts re-theme (surface `#E8EDF4`↔`#1B2735`), the lazy tier-viz canvases
rebuild without error, and there were zero console errors; the "CEUD Explorer"
header link was dropped to make room for the theme pill (still reachable via
"All tools"). CSS/markup only — no pipeline or data change. This was the last
interactive tool still off the shared theme.) Prior pass **2026-08-07**
(**Heat Pump Explorer**, later same day: extended the
Step 1 KPI-rail/toggle-in-title-row layout to every step (2 through 7),
flattened the top verdict KPI row from 3 tier-grouped rows to one 7-column
row, and reworked several steps' KPIs and chart content while auditing them
— Step 1's set changed to HDD/hours-below-zero-heat/hours-below-switch-off/
hours-below-−20°C/hours-below-−10°C; Step 2 lost the redundant "By month"
toggle, gained design-temp/switch-off reference lines and an average-load
KPI, and fixed a mislabeled "Heat delivered" legend that should have read
"Heat needed"; Step 3 dropped COP (now redundant with Step 4's dedicated
chart) and gained a "Hours it could run" upper-bound KPI. That Step 3 audit
surfaced two real rendering bugs, now fixed: the by-temperature chart's
delivered-heat line sloped across the last 0.5°C step at the cutoff instead
of dropping vertically (implied output that wasn't real), and the full-year
hourly chart's backup-heat polygon closed with a single straight line
between the year's first and last hour instead of tracing every hour
in between, self-intersecting with the load curve and painting spurious
backup-heat slivers in summer months with zero heating load.) Earlier that
day: Step 1's weather chart now marks
the zero-heat and switch-off temperatures on both the by-temperature and
hour-by-hour views, with collision-avoiding label placement so the two don't
overlap when they land close together (common with an electric-backup tier,
where the switch-off temperature is the tier hard-stop rather than a fuel
switchover). Controls box condensed: now sticky below the header on scroll
(same pattern as `retrofits.html`'s filter bar, labels drop once scrolled),
grid widened to 5 columns, "Grid emissions basis" converted from a 3-button
segmented control to a dropdown, and "Methane leak" + "Line losses" collapsed
into a single "Upstream & grid losses" Yes/No toggle (Yes = methane 1.5%, line
loss 5% — fixed representative values, not independently adjustable; **flagged
as a to-do** below to reinstate per-term control). The old "All years" weather
comparison button and its chart section were removed — fully superseded by
the new Step 1 chart, which already overlays every year as backdrop with
TMY/coldest/mildest/selected highlighted. Controls condensed further same day:
grid widened again to 7 columns (2 tidy rows), several labels shortened to
fit ("Zero-heat temp.", "Emissions basis", "Upstream losses") with a
nowrap+ellipsis safety net so a too-long label clips instead of wrapping and
throwing sibling controls out of vertical alignment, the switch-over
auto-reset button shrunk to an icon, and the "Selected heat pump" model-name
readout removed again — it only existed to fill a slot that's no longer
free.) Then, on 2026-08-06: (**Retrofit
Explorer**: re-measured the `HPCAP`-vs-AHRI
sizing claim and resolved the `COP` rating-condition question raised while prepping
the NRCan/EnerGuide demo. `HPCAP` (auditor-entered capacity) still runs unreliable —
median 1.6× the certified 47°F capacity over 318,585 rows, 1×/2×/4× clustering, 63%
of repeated AHRI codes inconsistent row-to-row — but the generic `COP` field turned
out not to be an error at all: a NEEP performance-table cross-check for the site's
most common installed unit (AHRI 211644151) shows the ERS `COP` median (2.99)
matches NEEP's **47°F**-rated COP (3.00), not the certificate's 5°F COP (1.80) it was
being compared against. AHRI's own search API has no 47°F COP field to validate
against directly (confirmed by enumerating all 40 fields it returns). The
cold-climate-ASHP-only fields `CCASHPCOP` and `CCASHPCAPACITYMAINTENANCE` already
carry a same-condition comparison and track the certificate closely (median 0.0pp
difference on capacity maintenance, 85% within ±10pp) — not yet used on the page.
Removed the old "1.55×" figure from `retrofits.html`'s sizing-chart note and added
a full writeup to the AHRI-enrichment methodology section. Also added, to the
pairing-gates methodology note: a full gate-by-gate breakdown of the ~177,880
nationally-dropped D&E pairs (roughly two-fifths Gate B date-order, one-fifth Gate C
floor-area, one-third Gate D structural), extending the existing Gate A/B
measurement to Gates C/D. New diagnostics: `Python/diagnose_hpcap_vs_ahri.py`,
`Python/diagnose_ccashp_vs_ahri.py`; `Python/diagnose_pairing_drops.py` updated to
match the shipped pipeline (it had gone stale after the 2026-07-18/-24 gate fixes
below). See `docs/RETROFITS.md`'s 2026-08-06 changelog entry.
Then, on 2026-08-05: new CEUD-sourced
**energy impact KPI card** — kWh/GWh saved, priced $ saved, a "homes powered for a
year" equivalent, and an EV-km equivalent, plus icons on both the GHG and energy
equivalency grids — and a **cumulative-audits-vs-housing-stock line** on the Retrofit
Insights timeline chart. Also fixed: the scorecard table's max-value bars used to run
edge-to-edge and blend into the next column; and `Heating_Change`/`HeatPump_Addition`
were double-counting the same homes in every aggregate measure-mix chart on **both**
pages (a heat pump addition is itself a furnace type/fuel change) — `Heating_Change`
now excludes heat pump additions downstream, no ERS pipeline rerun needed. Also new:
a **peak-demand card** — design/peak heat-loss decrease, by province, for the 388,842
matched pairs that were electrically heated pre-retrofit (732,283 kW national total,
42% of which added a heat pump), with a dropdown pricing the avoided kW against any of
the 12 resources in IESO's 2024 generation resource-cost table. See
`docs/RETROFITS.md`'s 2026-08-05 changelog entry.
Then, on 2026-08-04: new
**"Program era" filter** — ecoENERGY (2007–2012) / no program / Greener Homes
(2021–2024), classified by each home's initial audit year — in Retrofit Explorer's
FSA, province and Canada views, plus a companion "what did each era build" measure-mix
chart on Retrofit Insights. See `docs/RETROFITS.md`'s 2026-08-04 changelog entry.
Then, on 2026-08-03: new
**pipeline-overview diagram** at the top of `retrofits.html`'s advanced
methodology — the CSV → parquet → JSON → page flow as hoverable/focusable SVG
boxes, each tooltip carrying the real numbers, filters and datasets behind that
stage, including the emission-factor and retrofit-cost branches. Then a
**documentation and deploy audit across both retrofit pages**, which turned up
one live-site break and several drifted claims. Fixed: `deploy.sh`'s `PATHS`
was missing `retrofit_costs_json`, so the next full deploy would have silently
deleted the entire cost feature from the published site (it was live only via
an earlier incremental push); Retrofit Insights §06B was **already dead on the
live site** because `insights_json/hp_ahri_scatter.json` and `cchp_screen.json`
were never generated into the deployed tree —
`Python/build_hp_equipment_insights.py` is a separate script from
`build_insights.py` and had been missed, now re-run and documented as its own
step; every relative `docs/`/`ROADMAP.md`/`HeatPump/` link on both pages 404'd
(those paths aren't deployed to `gh-pages`) and now point at the `main` blob;
Retrofit Insights' NRCan open-data footer link was a dead dataset ID. Corrected
on the pages: the cost POC's coverage is **10 provinces + NT/NU**, not "12
provinces + 2 territories"; its 1,420,044-record input is now explained
(apartments/duplexes/triplexes excluded, 31,389 records) instead of silently
contradicting the 1,451,433 matched-pair figure beside it; **solar PV and
HRV/ERV** were priced and rendered but documented in neither methodology
section; REMDB and the ECCC emission factors added to Sources.
`docs/RETROFITS.md` corrected in seven places — stale oil/wood conversion
factors, the superseded exactly-one-D-and-E pairing rule, three sections still
describing `raw.githubusercontent.com` fetches from `main`, the "no dollar
figures are possible" caveat, and the audit range. Full detail:
[docs/RETROFITS.md changelog](docs/RETROFITS.md#changelog).
**Then a local-checkout audit, which found the deploy hazard was far wider
than the cost tree**: 1,429 of the 4,903 files published on `gh-pages` were
absent from this working copy — the whole of `newhomes_fsa/` (1,311 files),
`ceud_json/`, `construction_json/`, `newhomes_json/`, `geo_json/`,
`FSA_Maps/`, `grid_json/`, `Geothermal/output/index.html` and two `lookup/`
files. Since `./deploy.sh` builds `gh-pages` from the working tree, running
it from this machine would have wiped the New Homes Explorer, CEUD, the
Construction Tracker, the grid dashboard, every FSA map and the geothermal
page. All 1,429 restored from `origin/gh-pages` (188.7 MB); `deploy.sh`'s
preflight now passes all 31 paths. **Ottawa Case Study Phase 4's feeder half
is unblocked as a result** — `GridCapacity/Hydro.py` and
`ottawa_capacity.geojson` (3,884 feeder polygons with capacity attributes)
were both recovered intact from the 2026-07-27 deploy snapshot, which was the
only place `Hydro.py` had ever existed. Root cause: `/GridCapacity/` was
gitignored wholesale, so unlike every other pipeline script it had no home on
the decision-record branch. `.gitignore` now excludes the directory's
*contents* and re-includes `Hydro.py`, which is committed to `main` here; the
8MB geojson stays ignored. Caveat carried forward: `Hydro.py` is the original
working script, not a cleaned-up one — its `WHERE` clause still matches every
LDC whose name contains "Ottawa" (a `# tighten after you see the distinct
names` note was never actioned) and it writes its output to the current
directory rather than to `GridCapacity/`. It ran and produced the geojson we
hold, so it works; it just hasn't been tidied.) Prior pass
2026-08-02 (**Retrofit Insights + Retrofit Explorer**: GHG
emissions overhaul, in two parts. **Part 1** — new Retrofit Insights section
02 "The climate impact": national + per-province net tCO2e/yr saved (avg per
home and total), priced two ways (2024 federal carbon-tax rate $80/tCO2e;
ECCC's 2024 Social Cost of Carbon, $266/tCO2e C$2021 at 2% discount), plus an
equivalency-card strip (vehicles, flights, oil barrels, forest absorption,
propane cylinders) ported inline from Ottawa Visuals' `ghg_calculator.html`
(no iframe/cross-repo dependency). **Part 2** — building it surfaced that
`Pre_/Post_GHG` (raw `ERSGHG`) is only populated for **50.5%** of matched pairs
nationally (Quebec ~78%, Ontario ~43%, Saskatchewan ~9%), silently limiting
every GHG chart/median on **both** retrofit pages to half the data. Fixed with
a new **GHG basis** dropdown (4 scenarios: `reported` = raw ERSGHG;
`current`/`current_corrected` = flat 2026 official ECCC factor, corrected for
Alberta/Newfoundland; `as_audited` (default) = ERS-calibrated, matched to each
home's own audit year — validated to −0.66% national aggregate bias) on both
pages. Along the way, fixed a **survivorship-bias bug** in
`Python/ers_ghg_factors.py` (excluding true-zero-GHG rows from the factor
derivation had overstated the national aggregate by +12.8%; fixed to +0.16%),
and found the official ECCC electricity factor diverges 18–29% (Alberta) /
27–49% (Newfoundland) from what the ERS data itself implies — not a
within-province effect (see [ENERGUIDE_QUESTIONS.md §5.4](docs/ENERGUIDE_QUESTIONS.md),
a new open question for NRCan). New: `Python/ghg_factors.py`,
`Python/compute_ghg_scenarios.py` (Step 1c). Full pipeline rerun and both
pages verified in-browser this session — not just code-written-untested.
Full detail: [docs/RETROFITS.md "GHG scenarios"](docs/RETROFITS.md#ghg-scenarios).)
Prior pass 2026-07-31 (**Ottawa Case Study**: Phase 4's grid half shipped —
new `Geothermal/scripts/build_heat_demand.py` aggregates the 414k-building
stock onto the canonical 500 m grid; every summed column validated exact
against the building-level total, and city-wide totals independently
reconcile against Phase 2.5/Phase 3's already-published numbers with no
adjustment (6.68 TWh residential exactly; all three electrification policies'
added GWh/MW match to the reported digit). `build_suitability.py`'s existing
demand upgrade hook fired automatically once the file existed. Phase 4's
feeder half was recorded as **blocked** here — `GridCapacity/Hydro.py` and
`ottawa_capacity.geojson` both absent from the checkout, `Hydro.py` never
committed to `main` — **unblocked 2026-08-03**, see the top entry. Full
detail: [Geothermal/README.md §3.13](Geothermal/README.md),
[GEOTHERMAL_STATUS.md](GEOTHERMAL_STATUS.md).) Prior pass same day
(**Retrofit Costs**: like-for-like ASHP heating BAU
(was a uniform gas-furnace assumption — now the home's own pre-audit
equipment, mapped to REMDB, with two self-derived REMDB rows for Oil Furnace
and Electric Boiler REMDB never fit); POC moved from session scratchpad to a
permanent, committed pipeline (`Python/retrofit_cost_extract_fields.py`,
`retrofit_cost_estimate.py`); scaled to full national coverage, all 10
provinces + NT/NU (1.42M paired records, 1.24M priced); electricity
utility-rate source swapped after catching a stale "high confidence"
Saskatchewan rate (~67% understated, over a year stale) in the prior source —
new source is a third-party blog, flagged for further verification, not yet
trusted as settled; natural gas rates found similarly stale (~21 months,
every province) but left as-is pending a replacement source. Full detail:
[docs/RETROFIT_COSTS.md](docs/RETROFIT_COSTS.md).) Prior pass 2026-07-30
(**Retrofit Costs** POC: audited each priced measure's
REMDB area basis directly against the raw REMDB data sheets (air sealing =
house floor area, windows = window's own area, wall/roof = surface area —
all confirmed, not assumed); confirmed REMDB has a real, unused `Air
Sealing` regression driven by measured leakage reduction, flagged as the
next measure to add; checked the NRCan open-data dictionary and confirmed
ERS has no wall-construction-type field (Wood/Steel Stud + Batt stays a
stated assumption); added window frame-material classification from ERS's
`UGRWINDOWCODE` (via `Support.xlsx`'s `Frame` sheet) mapped to REMDB's
Vinyl/Metal classes — 82% of PEI window-change records now get a reported
class instead of a blanket Vinyl guess. Full methodology:
[docs/RETROFIT_COSTS.md](docs/RETROFIT_COSTS.md).) Prior pass same day
(new project **Retrofit Costs** started: a PEI-scoped proof of concept
pairing ERS retrofit records against PNNL/DOE's REMDB ($/measure cost
regressions, committed under `retrofits/USCosts/`) to estimate retrofit cost
per home. Confirmed no per-component envelope area exists anywhere in the
public NRCan ERS extract, so envelope costing runs on documented
rectangle-footprint area proxies; `Python/join_hp_capacity.py` extended to
surface `cooling_capacity_btuh`/`seer2` (already in `lookup/ahri_numbers.json`,
previously unused) enabling ASHP costing with an explicit reported-vs-assumed
ductless/ducted classification. 8,535 / 12,554 PEI records (68%) now have at
least one priced measure.) Prior pass same day
(Retrofit Insights: new section 06 "Cold-climate
equipment" — AHRI COP-vs-capacity-maintenance scatter + the US DOE CCHP
Challenge screen, resolving the "where does this go" decision left open
2026-07-27. New pipeline step `Python/build_hp_equipment_insights.py`; see
[docs/archive/ROADMAP_COMPLETED.md](docs/archive/ROADMAP_COMPLETED.md) item
14.) Prior pass same day (heat-pump **page re-organised** on the retrofit-page
pattern: outcome-first 7-section flow — 01 The verdict (one consolidated block
with KPI tiers: Emissions / Cost & energy / Equipment), 02 Where your emissions
come from (new before→after emissions bar beside the by-category bars), 03 Why:
heat needed vs delivered (was "How the model works"), 04 Across the year (the two
by-outdoor-temperature charts removed as redundant with §03), 05 What it costs to
run (new before→after cost bar; promoted above sensitivity), 06 How confident
should you be? (was "Sensitivity lenses"), 07 methodology. Single-view (no
Simple/Advanced toggle). Prior pass 2026-07-29 (heat-pump engine rebuild
**implemented**: design-load +
balance-point sliders replace archetype auto-sizing, tier × capacity-band
dropdowns pin one of 9 real AHRI-certified cell curves from the new
`build_cell_curves.py` pipeline, backup switchover is derived from backup type
instead of a manual control-strategy dropdown, and the propane
efficiency/methane-leak engine bugs are fixed in both `engine.js` and the
inlined copy. `validate_engine.py` passes.) Prior pass 2026-07-28 (heat-pump
engine rebuild redirected: F280 excludes gains so the ERS design heat loss
stands, sizing moves to a user-set design load, NRCan archetypes parked,
selection becomes tier × capacity — tier-selection scatter built). Same day:
BDA Heat Pump Lifecycle Emissions Explorer reviewed;
lifecycle-update candidates logged — see
[HeatPump/BDA_COMPARISON.md](HeatPump/BDA_COMPARISON.md). Prior pass
2026-07-27: heat-pump load-model rebuild started: city design temperatures step shipped; CCHP Challenge screen added; earlier 2026-07-24 pass verified against the repo and commit history — GitHub Actions run status not directly queried, inferred from bot-authored commits).

- 📦 Full record of completed items (prompts + build notes): [docs/archive/ROADMAP_COMPLETED.md](docs/archive/ROADMAP_COMPLETED.md)
- 🗺️ Visual status page: [project-atlas.html](project-atlas.html) — <https://ottawavisuals.github.io/Energy/project-atlas>
- 📖 Main readme (all links): [README.md](README.md)

---

## 📊 Status board

### Shipped & live ✅

| Tool | Live | Docs | Notes |
|---|---|---|---|
| 🏠 **Retrofit Explorer** | [/retrofits](https://ottawavisuals.github.io/Energy/retrofits) | [docs/RETROFITS.md](docs/RETROFITS.md) | v1 + post-launch additions, audit funnel, pairing fixes (matched 538k → 1.37M → 1.45M), bill card, visual polish, program-era filter (2026-08-04), `Heating_Change`/`HeatPump_Addition` double-count fixed (2026-08-05), HPCAP/COP/CCASHP validated against AHRI+NEEP + full pairing-gate breakdown (2026-08-06) |
| 📈 **Retrofit Insights** | [/retrofit-insights](https://ottawavisuals.github.io/Energy/retrofit-insights) | [docs/archive/ROADMAP_COMPLETED.md](docs/archive/ROADMAP_COMPLETED.md) (item 13) | national big-picture page: leaderboards, choropleth, success analysis, climate/equity linkage, missed-opportunity ranking, program-era timeline; shipped 2026-07-19; measure-mix-by-era chart added 2026-08-04; energy-impact KPI card + cumulative-audits timeline line (CEUD-sourced), electric-pre-retrofit peak-demand card (IESO-priced), and scorecard/`Heating_Change` fixes added 2026-08-05; §10 "One house at a time" added 2026-08-25 — Retrofit Canada case-study ranges (41 residential Canadian cases), kept separate from the ERS numbers; reworked 2026-08-27 — building-type filter, project summary table, and a per-component R-value slopegraph (pre→post, coloured by energy saving %) with its backing table |
| 🏡 **New Homes Explorer** | [/newhomes](https://ottawavisuals.github.io/Energy/newhomes) | [docs/NEWHOMES.md](docs/NEWHOMES.md) | EnerGuide new-construction slice (plan/as-built); shipped 2026-07-15; pipeline reworked 2026-07-22/23 (P/N column-fill, `ers_pn_column_fill.csv`) |
| 📊 **CEUD Explorer** | [/ceud](https://ottawavisuals.github.io/Energy/ceud) | [docs/CEUD.md](docs/CEUD.md) | all 5 sectors live |
| 🏗️ **Construction Tracker** | [/construction](https://ottawavisuals.github.io/Energy/construction) | [docs/CONSTRUCTION.md](docs/CONSTRUCTION.md) | monthly auto-refresh; **first scheduled run 2026-07-20 — watch it go green** |
| 🌍 **Ottawa Geothermal Map** | [/Geothermal/output/](https://ottawavisuals.github.io/Energy/Geothermal/output/) | [Geothermal/README.md](Geothermal/README.md) | v2 complete: conductivity sensitivity, drilling difficulty, segment suitability |
| 🔥 **Heat Pump Explorer** | [/heatpump](https://ottawavisuals.github.io/Energy/heatpump) | [HeatPump/METHODOLOGY.md](HeatPump/METHODOLOGY.md) | v2 complete: 14 cities, weather-year lens, sizing sweep, lifecycle sourcing, operating costs; page re-organised 2026-07-30 (outcome-first 7-section flow, KPI tiers, before→after bars); Step 1 chart gets zero-heat/switch-off markers + controls box condensed to a sticky, 7-col bar (2026-08-07); migrated onto shared `assets/site-theme.css` with light/dark/colour-blind toggle, matching every other advanced page (2026-08-09); propane backup + per-chart month/week zoom on all 7 full-year charts + two-color backup (fossil vs. electric) + hourly-methane bug fix; axis-label cleanup, daily-sum vs. daily-mean split, Step 6 reference lines, Final-numbers tidy-up, one-page PDF summary button (2026-08-21); ON grid-EF proxy city Toronto→London + cold/warm-tail extrapolation (2026-08-24); full 8,760-hour data table with CSV export, before the methodology section, virtualized same-day after a live perf report (2026-08-27) |
| 🧱 **Permits Explorer** | [/permits](https://ottawavisuals.github.io/Energy/permits) | [docs/PERMITS.md](docs/PERMITS.md) | shipped 2026-09-02 — nine municipal permit desks at permit level, lifted out of the Construction Tracker's advanced-only "Inside one city" section (which rendered as *nothing* on a Canada or provincial view). Full history per city from its own first month (Montreal 1990, Calgary 1999-06, Edmonton 2009, Winnipeg 2010, Ottawa 2011) instead of the shared 2017 floor; a 0.004° permit-density map with a year slider for the six cities that publish coordinates; category×year matrices; a filer word cloud (4 cities, 20+ permit threshold kept); and Toronto's approval/build intervals, which `municipal.json` has no panel for. Four data-quality finds shaped it — see docs |
| ⚡ **Grid Dashboard** | [/grid](https://ottawavisuals.github.io/Energy/grid) | [docs/GRID.md](docs/GRID.md) | ON/AB generation mix + emissions intensity, average-vs-marginal explainer, Advanced typical-day-by-season panel; shipped 2026-07-24 |
| 🏙️ **District Energy Explorer** | [/districtenergy](https://ottawavisuals.github.io/Energy/districtenergy) | [docs/DISTRICT_ENERGY.md](docs/DISTRICT_ENERGY.md) | shipped 2026-09-03 — definitions (IEA 1G→4G ladder incl. their objection to "5G", carriers, single/two-pipe/ambient loops, fuels, plant equipment) + CEEDC's full national inventory: 254 systems mapped on a Lambert conic with the 3,390-facility IEF superset as an Advanced context layer, filterable by province/source/service/status/era, per-system detail panel. Data-honesty content is a first-class section, not a footnote: 21% response rate, 90 of 238 operating systems with zero quantitative data, `year_reported` spanning 2014–2023, and a computed file-vs-report delta table. Static data — CEEDC surveys periodically; no auto-refresh |
| 🚪 **Landing page** | [/](https://ottawavisuals.github.io/Energy/) | — | one card per tool, cross-linked from every tool's header (`↳ All tools`); shipped 2026-07-24 |
| 🗺️ **Project Atlas** | [/project-atlas](https://ottawavisuals.github.io/Energy/project-atlas) | — | internal status/assumptions page — keep in sync when items ship |

**Data layers behind the tools (all built, all auto-refreshing):**

| Layer | Refresh | Status |
|---|---|---|
| Energy prices (`prices_json/`) | monthly, 3rd — `rates-refresh.yml` | ✅ built; first scheduled run **2026-08-03** (not yet happened) |
| Grid mix ETL (`grid_json/`) | weekly, Mon — `grid-refresh.yml` | ✅ first scheduled run went **green 2026-07-13** |
| AHRI cert lookup (`lookup/ahri_numbers.json`) | weekly, Mon 15:00 UTC — `ahri-refresh.yml` | ✅ shipped 2026-07-22; replaces manual `build_ahri_lookup.py` reruns |
| Construction data (`construction_json/`) | monthly, 20th — `construction-refresh.yml` | ✅ first scheduled run confirmed **green 2026-07-20** |
| Municipal permits detail (`permits_json/`) | monthly, 20th — `construction-refresh.yml` | ✅ shipped 2026-09-02; ~4.9 MB across 9 cities, `gh-pages` only; wired into `construction-refresh.yml` (monthly, 20th) alongside `construction_json/`; first scheduled run **2026-09-20** |
| Utility rates for bill cards (`utility_rates_reference.json`) | manual (`Python/utility_rates_reference.py`) | ✅ shipped 2026-07-18 |

### In flight 🔨

| Project | Progress | Next step |
|---|---|---|
| 🏙️ **Ottawa Case Study** (heat demand → electrification → grid) | `██████▓░░` Phase 4 grid half done, feeder half unblocked 2026-08-03 | **Phase 4 (feeder half):** both inputs recovered from the 2026-07-27 `gh-pages` snapshot — `GridCapacity/Hydro.py` (now committed to `main`) and `ottawa_capacity.geojson` (3,884 feeder polygons, `capacity`/`capacityrange`/voltage/`ldc_name`). Next: build `feeder_demand.geojson` by intersecting the Phase 4 grid against those polygons, then derive the coincidence/diversity factor from real feeder loading → [item 7](#7-ottawa-case-study--heat-demand-electrification-grid-in-progress) |
| 💰 **Retrofit Costs** (ERS × REMDB cost pairing) | `███████░░` live in `retrofits.html` behind a "Proof of concept" tag — band dropdown, per-measure breakdown, view totals, payback, national data (all 10 provinces + NT/NU; Yukon has no ERS records) | Verify province-mode UI once deployed (local checkout lacks `province_json`/`geo_json`); band-specific payback (currently mid-band only); investigate utility-rate source further (electricity just swapped after catching a stale rate, unverified beyond SK; gas found ~21mo stale, unresolved); source a real footprint-aspect-ratio dataset → [docs/RETROFIT_COSTS.md](docs/RETROFIT_COSTS.md) |

### Queued 🆕

- 🔀 **Heat pump tool — reinstate adjustable upstream methane / line-loss
  rates** (added 2026-08-07). The "Upstream & grid losses" Yes/No toggle on
  `heatpump.html` collapsed two previously-independent sliders (methane leak
  0–5%, line loss 0–12%) into one switch that applies a single fixed value to
  each when on (methane 1.5%, line loss 5%) — done to fit the condensed
  controls box, at the cost of losing the ability to reason about the two
  independently (e.g. a high-leakage gas region on an average-loss grid).
  **Next step:** either bring back per-term adjustability in a more compact
  form (e.g. one combined low/mid/high preset instead of two full sliders),
  or confirm the fixed values are an acceptable permanent simplification.

- ♨️ **Heat pump tool — Phase 3c bucket rework, 36-cell candidate table**
  (spec done, curves outstanding; **superseded as the user-facing priority**
  by the engine rebuild below, which shipped 2026-07-29 with 9 real cells
  wired into `heatpump.html` — see that bullet). Equipment selection rebuilt
  on **AHRI as sampling frame / manufacturer datasheets as measurement**: a
  3×3 grid of COP @ 5 °F × capacity maintenance, 36 representatives chosen by
  real Canadian installation frequency from 439,975 EnerGuide record
  appearances. Spec: [HeatPump/TIER_SPEC.md](HeatPump/TIER_SPEC.md). The live
  tool already selects one of 9 real, individually AHRI-certified units (3
  tiers × 3 capacity bands) with datasheet-sourced curves — no scaling, no
  interpolation — so this bullet now tracks only the **full 36-cell
  candidate table** (for future tier/band boundary decisions and the CCHP
  screen), which remains gated on the `hp_units_joined.csv` reproducibility
  gap below. **Next step, if picked up:** hand-fetch the remaining priority
  units' performance data (datasheets give capacity + lockout; NEEP needed
  for power/COP), then extend `hp_curves.json`.

- 🌡️ **Heat pump tool — heating-load model rebuild** (started 2026-07-27,
  step 1 shipped). The load model is being rebuilt from scratch so the design
  load and load curve are explainable and defensible end to end.

  **Step 1 done: city design temperatures from the station HOT2000 actually
  used.** `HeatPump/pipeline/build_city_design_temps.py` →
  `data/processed/city_design_temps.json`. The raw ERS files carry `WEATHERLOC`
  and `WTHDATA`, which were never carried into `ers_web_*.parquet`; recovering
  them lets each home's `EGHDESHTLOSS` be divided by the design temperature it
  was actually computed at, instead of the 2.5%-ile proxy in
  `build_archetypes.py`. Scanned 1,430,221 matched pairs — **100% matched, 0
  unmatched** — and joined to NBC Appendix C via the new committed
  `HeatPump/reference/nbc_station_design_temps.csv`. **84 cities, 1,020,246
  homes (71.3%), zero homes without a design temperature.** Method + caveats in
  [HeatPump/METHODOLOGY.md](HeatPump/METHODOLOGY.md) "City design temperatures
  from HOT2000 weather stations".

  **Step 2 done: archetypes rebuilt on NRCan's published loads.**
  `HeatPump/pipeline/build_archetypes_nrcan.py` →
  `data/processed/archetypes_nrcan.json`. Decision taken 2026-07-27: **stop
  fitting a balance point to our own data and take both quantities from one
  published source** — NRCan CanmetENERGY *Cold-Climate ASHPs*
  (Cat. M154-149/2022E-PDF) Table 1 + Figure 1. Because each NRCan archetype is
  one house relocated to 16 cities, regressing the 16 published peaks against
  the 16 NBC design temperatures recovers UA and T_balance per archetype
  (R² 0.90–0.93), and independently reproduces the Figure 1 intercepts within
  0.5 °C for archetypes A and B — which also **settles that Table 1 is a
  design-condition load, not a TMY-series peak** (a 16% difference in UA).
  UA is taken **per city** from the published peak, preserving a real
  wind-infiltration effect the single fit discards (archetype A: 389 W/K in
  St. John's vs 291 in Kamloops). **Scope is NRCan's 16 cities for now**;
  TMY covers 11 of them. Full method + limitations in
  [HeatPump/METHODOLOGY.md](HeatPump/METHODOLOGY.md) "NRCan-published archetypes".

  **⚠️ Redirected 2026-07-28 — see "engine rebuild" below.** Decisions taken
  after discussion with a colleague supersede the archetype approach entirely:
  `EGHDESHTLOSS` is a CSA F280 design heat loss and **F280 takes no credit for
  solar or internal gains**, so the ERS heat loss was correct for sizing all
  along and the balance-point worry was the wrong frame for the sizing question.
  Sizing moves to a **user-set design heat load** plus a **distribution chart of
  local design heat loss**, and the **NRCan report and archetypes are parked as
  reference, not used for the methodology**. Step 1 below is therefore
  **cancelled, not outstanding**. Full reasoning in
  [HeatPump/METHODOLOGY.md](HeatPump/METHODOLOGY.md) "Design-heat-load &
  selection rework — decisions taken 2026-07-28".

  **Steps outstanding:**
  1. ~~**Wire `heatpump.html` onto `archetypes_nrcan.json`**~~ — **cancelled
     2026-07-28.** This had in fact been *written* (uncommitted working-tree
     changes to `heatpump.html` and `project-atlas.html`: fetch
     `archetypes_nrcan.json`, city list cut to NRCan's 11, archetypes A–D). It
     was **never committed and never deployed**, and was **reverted on
     2026-07-28** rather than shipped, since decision 2 replaces archetype
     sizing altogether. The live tool continues to run the ERS
     `archetypes.json` / 14 cities until the rebuild lands.
     `build_archetypes_nrcan.py` is committed, so the analysis is reproducible
     if it is ever wanted.
  2. ~~**Commit an explicit peak-load field on a stated percentile**~~ —
     **superseded 2026-07-29.** Moot once sizing moved to a user-set design
     load + balance point (decision 2 in the engine rebuild below): there is
     no computed peak-load field to pin a percentile to anymore, since the
     number comes from the user's own EnerGuide/HOT2000 figure rather than
     a fitted TMY statistic. The 4-point reference display beside the slider
     still uses archetype-vintage medians, not a stated percentile — leave
     as-is unless it causes confusion in practice.
  3. **Decide whether to credit the night setback when sizing.** ERS SOC drops
     to 18 °C for 8 h and the sizing hour falls inside it; CSA F280 takes no
     setback credit because the system must recover. Simulate with, size without,
     and say so.
  4. **Display gross vs net** design load with both definitions stated, and say
     which one sizes the equipment.
  5. **Send the NRCan question list.** All open EnerGuide/HOT2000 questions
     across every ERS-based tool are now consolidated in
     [docs/ENERGUIDE_QUESTIONS.md](docs/ENERGUIDE_QUESTIONS.md) — the blocking
     one is the four monthly HOT2000 fields (`energy_loadGJ`, `solar_gainsGJ`,
     `internal_gainsGJ`, `aux_energy_GJ`) or, failing that, the SOC solar gain
     per city. Answering it would let us return to ERS-derived archetypes and
     recover the population sample, floor areas, local construction practice
     and the townhouse archetype. Also collects the design-temperature /
     weather-library questions, `EGHDESHTLOSS` semantics, `HPCAP` vs
     `CCASHPCAP`, `ERSRating=0`, the pairing-key question, and the ON/QC NBC
     tier gap.

  **Superseded:** the ERS design-temperature rewiring of `build_archetypes.py`
  (step 1's original purpose). `city_design_temps.json` is still the input for
  any future ERS-based work, and the 84-city table stands.

  **Two engine bugs — fixed 2026-07-29** in both `HeatPump/app/engine.js` and
  the inlined copy in `heatpump.html`: propane backup now defaults to 90%
  AFUE instead of falling through to 100%, and the upstream-methane leak
  adder is restricted to `fuel/backup.type === "gas"` only (was misapplied to
  propane using natural-gas density/energy constants). Propane gets no leak
  adder rather than reusing gas's number — no defensible propane
  upstream-loss constant exists yet. Still open, lower priority: no
  part-load/cycling degradation (curves are steady-state, so mild hours are
  optimistic) and no defrost penalty.

- 🔧 **Heat pump tool — engine rebuild: user-set design load + tier/capacity
  selection — implemented 2026-07-29.** Supersedes the archetype sizing path
  above. Four decisions, recorded with their reasoning in
  [HeatPump/METHODOLOGY.md](HeatPump/METHODOLOGY.md) "Design-heat-load &
  selection rework":
  1. **The ERS heat loss was right for sizing.** CSA F280 excludes solar and
     internal gains by design, so `EGHDESHTLOSS` needs no repair as a *design
     load*. The gains question stays open for the *energy* simulation only.
  2. **Sizing moved to the user** — a design-heat-load slider plus a balance-
     point slider, with `UA_W_per_K` derived from both against
     `city_design_temps.json` (84 cities, 1,020,246 homes). A lightweight
     4-point reference display (this city's archetype-vintage medians) sits
     beside the slider for calibration only.
  3. **NRCan report + archetypes parked** as reference; not used for the
     methodology.
  4. **Heat-pump selection = two dropdowns** (performance tier, capacity
     band), replacing auto-sizing. `HeatPump/pipeline/build_cell_curves.py`
     ships `hp_cell_curves.json` — 9 cells (3 tiers × <18k/18–30k/30–42k Btu/h),
     each pinned to exactly one real AHRI-certified unit, no scaling.
     `build_tier_curves.py` now imports `UNITS` from this module.
  5. **Backup dispatch derived from backup type**, not a manual dropdown:
     electric resistance tops up capacity shortfall; gas/oil is a temperature
     switchover via a repurposed switch-over-temperature slider. The existing
     hour-by-hour `simulate()` already implemented both dispatch modes
     correctly, so it was not rewritten — only how the UI derives
     `control.strategy` changed.
  6. A quick ERS check (`HeatPump/pipeline/check_hp_sizing_correlation.py`,
     finding in `HeatPump/TIER_SPEC.md` §6.1) found real installs scattered
     widely against design load (median ratio 0.66, only 24% within ±20%),
     so the UI implies no "correct" sizing ratio.

  Done: the tier-selection scatter (`build_tier_scatter.py` →
  `data/interim/tier_scatter.html`), `build_cell_curves.py`, the ERS sizing
  check, and the full `heatpump.html`/`engine.js` rewiring above.
  `validate_engine.py` passes against the rebuilt engine wiring.

  **Still open:** the `hp_units_joined.csv` reproducibility gap (no producer
  script) still gates the 36-cell candidate table / CCHP screen specifically —
  it does not affect the 9 cells actually shipped, which now have a real
  producer script (`build_cell_curves.py`). The ≥42k Btu/h band is identified
  in the 36-cell table but not yet wired into the simulation (only the 9
  cells across <18k/18–30k/30–42k are simulated).

- 🔬 **Heat pump tool — lifecycle updates from the BDA comparison** (reviewed
  2026-07-28, nothing implemented yet). The Building Decarbonization Alliance
  shipped a [Heat Pump Lifecycle Emissions
  Explorer](https://buildingdecarbonization.ca/report/heat-pump-lifecycle-emissions-explorer/)
  in June 2026 — a single-equation scalar tool with no weather or dispatch, so
  no threat to our load/performance model, but **ahead of us on refrigerants and
  on a forward-looking grid**. Full review, their constants, and where each tool
  wins: [HeatPump/BDA_COMPARISON.md](HeatPump/BDA_COMPARISON.md). Candidate work,
  in priority order:
  1. **Refrigerant GWPs → IPCC AR6, blend-weighted.** Ours are AR4/AR5-era
     (R-410A 2088, R-32 675, R-454B 467, R-290 3) vs AR6 2256 / 771 / 531 / 0.02,
     and the UI's 2088 **contradicts the engine test vector's 2256** for the same
     refrigerant. Correctness fix.
  2. **AC counterfactual credit** — if the household would have installed AC
     anyway, that AC's refrigerant and electricity belong to the baseline. We
     omit it entirely. Should ship as a toggle, not a default.
  3. **Per-refrigerant charge mass** — our single capacity-scaled `charge_kg`
     gives the R-290 option an R-410A-sized charge.
  4. **Forward grid trajectory** from CER *Canada's Energy Future 2026* Current
     Measures, alongside (not replacing) the existing three EF bases. Closes the
     "does not forecast future levels" limitation already flagged in
     METHODOLOGY.md — the one place BDA genuinely leads us.
  5. **Freed-kWh displacement framing** for clean-grid provinces (their QC
     answer). Undecided whether it is in scope.

  Explicitly **not** copying their scalar seasonal COPs (their weakest link,
  our strongest) or their `skeptic`/`central`/`best` preset naming (advocacy
  framing, fails the two-audience test).

- ✅ **US DOE CCHP Challenge screen — shipped on Retrofit Insights (2026-07-30).**
  `HeatPump/pipeline/screen_cchp.py` screens all 15,148 models against
  the [Challenge specifications](https://www.energy.gov/cmei/buildings/cchp-technology-challenge-specifications)
  Table II-3. Headline: **4 models, 8 of 439,975 ERS appearances (0.00%)** clear
  every checkable criterion, and three of the four sit *exactly* on the
  threshold. 34.4% of the base is `out_of_scope` (<24,000 Btu/h, which the
  Challenge deliberately does not address). Surfaced as its own section
  (06 — "Cold-climate equipment") on
  [retrofit-insights.html](retrofit-insights.html), alongside an AHRI
  COP-vs-capacity-maintenance scatter, rather than folded into the 3×3 tier
  grid (no qualifying unit is a cell representative). New pipeline step:
  `Python/build_hp_equipment_insights.py`. Full build note:
  [docs/archive/ROADMAP_COMPLETED.md](docs/archive/ROADMAP_COMPLETED.md) item 14.
  Method in [HeatPump/METHODOLOGY.md](HeatPump/METHODOLOGY.md) "US DOE Cold
  Climate Heat Pump Challenge screen"; caveats in
  [HeatPump/TIER_SPEC.md](HeatPump/TIER_SPEC.md) §6.7.

- 🧾 **Reproducibility gap: two Phase 3c inputs cannot be regenerated**
  (found 2026-07-27). `HeatPump/data/interim/hp_units_joined.csv` — the joined
  15,148-model universe that the bucket grid *and* the CCHP screen both read —
  **has no producer script anywhere in the repo**; it was built ad hoc in an
  earlier session. And `lookup/ahri_numbers.json`, the AHRI scrape itself, is
  not on local disk. Both are gitignored, so the "process, not bytes" rule does
  not currently hold for them: losing `hp_units_joined.csv` would strand Phase
  3c. **Fix:** write the join as a real pipeline step, and confirm the weekly
  `ahri-refresh.yml` still restores `lookup/`.

- 🔧 **Tech debt: consolidate the two heat-pump engines** (deferred, do later).
  `HeatPump/app/engine.js` and the copy inlined verbatim in `heatpump.html`
  (~line 743 onward) are the same ~600-line engine maintained twice — any logic
  change has to be applied to both by hand or they silently diverge, and only
  the inlined copy is what users actually run. Target: one source of truth
  (build step that injects `app/engine.js` into the page, or ship it as a
  separate `<script>` and drop the inline copy), keeping `engine.test.js` and
  `pipeline/validate_engine.py` pointed at it. **Not part of the current
  heat-pump-selection rework — flagged now, scheduled later.**

Otherwise nothing queued — next up is finishing the in-flight Ottawa Case Study
(below), then picking from the project ideas.

---

## 🎯 What's next — recommended order

1. **Ottawa Case Study Phases 4 → 5 → 6** (item 7). The only thing left on the
   board. Phase 4 is the defensibility step (coincidence factor — Phase 3
   proved the undiversified sums are upper bounds); Phase 6 is the public
   narrative page the whole project builds toward.
2. Once Phase 6 ships, pick from **Project ideas** below — nothing queued
   ahead of it.

**Site-wide polish pass — 2026-07-24:**

- [x] Social previews: `assets/og/*.png` (1200×630, generated by
      `Python/build_og_images.py`) + `og:image`/`og:url`/`twitter:card` on all
      nine pages. Rerun the script when a page's title or pitch changes.
- [x] Google Fonts made non-blocking everywhere (`rel="preload"` + onload swap,
      `<noscript>` fallback).
- [x] Analytics (`G-3QLS1Q554N`) now on all nine pages; the loader on
      retrofits.html had been requesting a placeholder `G-XXXXXXXXXX` ID.
- [x] `retrofits.html` CSS/JS extracted to `assets/retrofits.css` +
      `assets/retrofits.js` — repeat-visit transfer 93 KB → 26 KB gzipped.
- [x] New Homes: explicit empty state for the code-tier section, which was
      showing a heading over blank space in ON/QC (0 of 70,568 ON evaluations
      carry a tier). See [docs/NEWHOMES.md](docs/NEWHOMES.md).
- [x] Retrofit Explorer: new aggregate "Where the heat escapes" chart, the
      per-FSA/province twin of the per-home heat-loss breakdown.
- [x] **Pairing Gate A recovered — matched sample 1,369,305 → 1,451,433
      (+82,128, +6.0%).** `build_pairs_index()` now reduces each home to
      oldest-D + newest-E instead of requiring exactly one of each. The pair
      stage gained the predicted +148,155; the structural/floor-area gates then
      removed proportionally more of the recovered multi-audit homes (they span
      longer gaps), netting +82,128. Matched share of homes with both a D and an
      E audit rises 84.0% → 89.1%. Headline figures barely move — median saving
      stays 20%, whole-home heat loss −12% — which is the evidence the recovered
      homes are representative rather than a distortion. Full chain rerun and all
      JSON regenerated. Previous build artifacts backed up at `C:\ERS\web_prev\`.
- [ ] **Gate B — still open, and the ordering argument favours changing it.**
      84,755 pairs are dropped for "E not dated after D". None have unparseable
      dates and 99.4% are exact same-day ties; `ENTRYDATE` is month-precision
      throughout (all first-of-month). Since `EVALTYPE` already says which audit
      is the initial and which the follow-up, **the date test is only a guard
      against genuine reversals** — so `E > D` → `E >= D` would be correct and
      recovers ~84,253, leaving the 502 real reversals excluded. Not applied:
      surfaced as an open question on the page for the EnerGuide team to confirm
      first. (An earlier framing in this session — that same-day ties carry "no
      recoverable ordering" — was wrong; ordering comes from `EVALTYPE`, not the
      date.)

**Small loose ends (fold into any session):**

- [x] ~~`Geothermal/scripts/build_building_demand.py` parquet-metadata clobbering
      bug~~ — fixed 2026-07-24. Both phase writers now call the shared
      `Geothermal/scripts/parquet_meta.py:write_with_meta()`, which carries
      every `heatdemand_*` note across a rewrite. **Phase 4 must use it too.**
- [ ] Watch first scheduled run: rates **2026-08-03**. (Construction's first run
      went green 2026-07-20; AHRI lookup is now a weekly automated refresh as of
      2026-07-22 — both resolved, no longer loose ends.)

---

## 7. Ottawa Case Study — heat demand, electrification, grid (in progress)

The end product is the **Ottawa Case Study**: a six-step narrative (grid
constraints → ground resource → building heat loads → electrified share →
electrification peak vs grid → candidate areas), delivered as a case-study page
with the interactive geothermal map as the expert explorer. Full plan + prompts:
**[HEATDEMAND_PLAN.md](HEATDEMAND_PLAN.md)** (§0 narrative, §5 paste-able
prompts). Build log: [GEOTHERMAL_STATUS.md](GEOTHERMAL_STATUS.md).

| Phase | What | Status |
|---|---|---|
| 0 | Source scouting memo | ✅ 2026-07-16 |
| 1 | Canonical building stock (414k buildings, height/type/vintage) | ✅ 2026-07-16 |
| 2 | Per-building current heat load + fuel | ✅ 2026-07-16 |
| 2.5 | Stock reconciliation — implied dwellings 1.005× census, sums defensible over `in_ottawa_cd` | ✅ 2026-07-17 |
| 3 | Electrified load per building (validated 0.00% vs shipped engine) | ✅ 2026-07-17 |
| **4** | **Grid half:** ✅ 2026-07-31 — `heat_demand_grid.geojson`, 6,722/13,778 cells, validated exact against Phase 2.5/3's own totals; `build_suitability.py`'s demand upgrade hook now fires for real. **Feeder half: 🔓 unblocked 2026-08-03** — `Hydro.py` + `ottawa_capacity.geojson` recovered from the 2026-07-27 deploy snapshot (the only place the script had ever existed); `Hydro.py` now committed to `main` and `.gitignore` narrowed so it stays there. feeder_demand.geojson and the coincidence factor are still unstarted | 🔨 **feeder half next** |
| 5 | New map layers (demand, grid stress, intervention score) | 🆕 |
| 6 | The case-study page — the narrative deliverable | 🆕 |

Key Phase-3 findings that shape Phase 4 (details in GEOTHERMAL_STATUS.md):
the "average installed" ccASHP locks out at −15 °C so policy (a)'s design peak
is an equipment problem (Tier 1 halves it); the ~90% hybrid target is
unreachable with that curve (stalls at 81–84%); **the peak columns are
undiversified** — already-electric stock alone sums to 1,275 MW ≈ 98% of Hydro
Ottawa's system peak, so Phase 4 must derive a coincidence factor from real
feeder loading rather than quote raw sums. That derivation was blocked on the
missing `GridCapacity/Hydro.py`; both it and `ottawa_capacity.geojson` were
recovered 2026-08-03, so the feeder loading data is now in hand — see
GEOTHERMAL_STATUS.md's 2026-07-31 and 2026-08-03 entries.

---

## 💡 Project ideas (not committed — pick when the queue clears)

1. **EWRB Large-Buildings Explorer.** Ontario's Energy & Water Reporting
   Benchmark publishes *actual reported* energy + floor area + property type for
   every building ≥ 50k ft². Already identified as a heat-demand input
   (HEATDEMAND_PLAN §3.2); a standalone benchmarking page ("how does this
   office/MURB compare to its peers?") would be the suite's first
   *measured-data* tool and reuses the whole design system.
2. **Solar PV layer / explorer.** The ERS data already tracks PV adoption
   (retrofits.html measure flag); NRCan publishes municipal photovoltaic
   potential. Per-FSA adoption vs potential = "who's leaving sun on the table" —
   a natural sibling of the Retrofit Insights choropleths.
3. **Case-study template → second city.** Once Ottawa Case Study Phase 6 ships,
   the pipeline (footprints → stock → load → electrified peak vs feeders) is
   reusable wherever a utility publishes feeder capacity maps (several ON LDCs
   do under the same OEB CCIM mandate). A second city would prove the method
   generalizes.
4. **Bill comparator standalone.** The rates layer (`prices_json/` +
   `utility_rates_reference.json`) + heat pump engine could back a simple
   "what would switching cost *me*" page — narrower and more shareable than the
   full Heat Pump Explorer.
5. **EV charging load layer.** Same grid-stress framing as the case study's
   Phase 4: per-feeder added MW from EV adoption scenarios. Complements the
   heat-pump electrification story on the same GridCapacity polygons.

---

## ✅ Completed items (full record in [docs/archive/ROADMAP_COMPLETED.md](docs/archive/ROADMAP_COMPLETED.md))

| # | Item | Done |
|---|---|---|
| 1 | Ship the Geothermal map | 2026-07-10 |
| 2 | Repo housekeeping — AHRI legacy files | 2026-07-12 |
| 3 | Heat Pump tool, all 7 phases | 2026-07-10 |
| 4 | Energy prices layer, all 3 phases | 2026-07-12 |
| 8 | Geothermal v2 (4 phases) | 2026-07-15 |
| 9 | Heat Pump v2 (6 workstreams) | 2026-07-17 |
| 10 | Retrofit Explorer post-launch additions | 2026-07-17 |
| 11 | Retrofit audit funnel + pairing-filter fix | 2026-07-18 |
| 12 | Retrofit EnerGuide-demo visual polish | 2026-07-18 |
| 13 | Retrofit Insights — national "big picture" page | 2026-07-19 |
| 6 | Live grid dashboard — ETL + page (`grid.html`) | 2026-07-12 (ETL) / 2026-07-24 (page) |
| 5 | Landing page hub (`index.html`) | 2026-07-24 |
| — | New Homes Explorer (built outside the roadmap) | 2026-07-15 |
| 14 | Heat Pump — methodology-audit fixes (upstream-oil, fuel constants, default basis) | 2026-08-19 |
| — | District Energy Explorer (built outside the roadmap, from a direct request) | 2026-09-03 |

---

## Session hygiene

- Each prompt is self-contained; run in a fresh session, in order within an item.
- After each session: update the project's STATUS/METHODOLOGY file, flip the
  status board here, and commit.
- Opus for methodology-heavy or design-heavy work (silent-error risk); Sonnet
  for data plumbing with clear validation criteria.
- When an item completes: move its full text to
  [docs/archive/ROADMAP_COMPLETED.md](docs/archive/ROADMAP_COMPLETED.md) and
  keep one line in the Completed table.
