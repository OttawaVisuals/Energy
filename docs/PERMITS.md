# Permits Explorer

`permits.html` — nine Canadian municipal permit desks at permit-level detail:
the full record back to each city's own first month, a density map of where
building actually happens, who files the permits, how long approval takes, and
what a unit costs to build.

**Live:** https://ottawavisuals.github.io/Energy/permits

## Why this is its own page

The Construction Tracker counts whole metro areas. Its municipal data lived in
an *"Inside one city"* section that was `data-mode="advanced"` **and** filtered
to `k === state.geo || c.cma === state.geo` — so on a Canada view, or any
provincial view, nine cities' permit desks rendered as nothing at all. What did
render was one monthly total line, a static all-time top-12 area list and a
top-15 name table: the summary, never the record.

This page is the record. `construction.html` keeps its summary cards unchanged
and links here.

## What it shows

- **Nine permit desks** — every city in one sortable table (record span, permits,
  trailing 12 months, y/y, a sparkline, and capability chips for map / names /
  cost / timing). Nothing on the page is gated behind picking a city first.
- **The whole record** — KPIs plus every month a city publishes, as permits,
  declared value or dwelling units, raw or 12-month averaged.
- **Where the building actually happens** — a density map: every geocoded permit
  binned to a fixed 0.004° cell, per year, with a year slider and a play control.
  Six cities; three have no coordinates and say so.
- **Busiest areas / where building moved** — a ranked area bar chart per year plus
  an area-share-by-year band chart.
- **What's being permitted** — work-type and building-type matrices by year.
- **Who builds the city** — a word cloud of top filers with the ranked table
  beneath it. Four cities.
- **How long it takes** — approval interval and build interval, by type and by year.
- **What a new home costs to build** — $/unit, $/sq ft and average unit size.
- **What this data can't tell you** — a per-city limitations table.

## Data pipeline

```
Python/permits_detail_etl.py    # nine portals; imports its transport and
                                #   paging helpers from municipal_permits_etl.py
                                #   rather than re-implementing them
        → permits_json/_index.json        city roster + capability flags
        → permits_json/<city>.json        detail payload
        → permits_json/<city>_grid.json   density grid (six cities)

construction_json/municipal.json  # read directly by the page for the
                                  #   processing / build-time / unit-economics /
                                  #   quality / coverage panels. Produced by
                                  #   municipal_permits_etl.py, which stays the
                                  #   single producer for those.
```

**The two scripts do not overlap.** `municipal_permits_etl.py` produces a
*summary* card per city, floored at 2017 so all nine are comparable and
cross-checkable against the StatCan CMA series on the Construction Tracker.
`permits_detail_etl.py` produces the *record*: full history, category×year
matrices, the grid, a 120-deep name list, and Toronto's two interval panels.
Panels that already exist and are correct are read from `municipal.json`, not
recomputed.

## Decisions and caveats

These shape the UI, so they are not footnotes.

### Three cities get no map, and it is not worked around

Six publish per-permit coordinates: Vancouver (`geo_point_2d`), Calgary and
Edmonton (`latitude`/`longitude`), Winnipeg (`location`), Montreal
(`longitude`/`latitude`), Mississauga (`LATITUDE`/`LONGITUDE`).

- **Toronto** has no coordinate field at all. `POSTAL` is populated on 90.8% of
  rows (checked live on a 6,000-row sample), so an FSA choropleth against the
  `FSA_Maps/ON.geojson` this repo already ships is technically possible — but
  that is a ~100× coarser map answering a different question, and placing it
  beside six real density grids would read as the same product. Not built.
- **Ottawa** — annual XLSX workbooks; ward and community are the only geography.
- **Halifax** — the source is a plain Esri *table* with no geometry anywhere.

Each city's payload carries a `map` object with `available` and, when false, the
reason, which the page prints.

### The grid holds no addresses, deliberately

Cells hold a permit count and, where the city has a cost field, a dollar total.
Never an address, permit number or name. Individual permit points would put
private residential renovation addresses on a public map — the same concern the
20+ permit name threshold already exists to avoid.

**0.004° was chosen by measurement.** On Calgary (~499k rows, 28 years): 0.002° → 156,695 cell-year rows / 3.04 MB; 0.004° → 81,454 / 1.61 MB;
0.008° → 29,890 / 0.59 MB. 0.004° is the coarsest that still resolves individual
city blocks at the zoom the map opens at. Colour breaks are quantiles of the
*displayed* year's non-empty cells and the break values are printed in the
legend, because a colour then means different absolute numbers between two years.

### Two cities' series are floored, and the reason is on the page

Screened on every run by `check_leading_ramp()`, which warns when a city's first
three full years average under a quarter of its median year. Two failed:

- **Toronto — floored at 2017-01.** Its resource is titled *"Cleared Building
  Permits since 2017"*, and rows dated earlier are only the permits that were
  still **open** when the dataset was cut — a survivorship sample. Plotted as
  history they rise smoothly from 94 permits in 1990 to 33,017 in 2016 and then
  jump to 45,431 in 2017, which would read as a 350-fold increase in Toronto's
  building that never happened. **173,236 permits** carry earlier dates; they
  remain in the all-time total and in every category matrix, and are excluded
  only from the time series. The page shows the in-series count in the roster and
  KPIs, with the excluded count disclosed beside it.
- **Ottawa — floored at 2011-01.** The workbooks begin in 2011; exactly one row
  is dated 2003-07.

Seven cities passed and are published from their own first month: Montreal 1990,
Calgary 1999-06, Edmonton 2009, Winnipeg 2010, Vancouver 2017, Mississauga 2018,
Halifax 2020-12. **Montreal genuinely starts 1990**, not 1997 as
`docs/CONSTRUCTION.md` states — checked live, 1990–1996 run 7,000–9,300 permits a
year, a normal level, not a tail.

### The current month is dropped

Every portal updates continuously, so on any run day the newest month holds only
the permits issued so far — Vancouver's showed 14 against a ~330 monthly norm.
Plotted as-is it reads as a collapse rather than as a month three days old, and a
12-month average carries the dip for a year. The month is removed, not zeroed or
extrapolated, and the page states the record ends at the last *complete* month.
The newest **year** column in the matrices is annotated as year-to-date rather
than dropped, since dropping it would discard up to eleven real months.

### CKAN silently truncates at 32,000 rows

Montreal's grid query is a server-side `GROUP BY` over 558,874 rows. Unpaged, the
endpoint returned 32,000 grouped rows covering **60,394 of 540,855** geocoded
permits — an 89% loss, with no error and a map that looked complete. It is now
paged with a deterministic `ORDER BY` and **reconciled against the source count**;
a mismatch raises rather than ships. (`datastore_search_sql` also blocks `CAST`
outright but allows `::numeric` and `percentile_cont`.)

### The date gate is real, and it is counted

Every series on the page is keyed on the permit's issue date, so a row without
one cannot be placed on any chart. That gate is not small — **66,481 published
rows across four cities** carry no usable issue date:

| City | Undated | Of source rows |
|---|---:|---:|
| Toronto | 45,652 | 8.0% of 571,296 |
| Calgary | 18,340 | 3.7% of 498,889 |
| Halifax | 2,478 | 13.2% of 18,838 |
| Ottawa | 11 | <0.1% |

The other five drop none. Halifax's share is the largest proportionally and its
dataset is the smallest, so it matters most there. (Calgary's *coordinates*, by
contrast, are 100% populated — it is only the date that is missing.)

Each city's payload reports `source_rows` (what the portal holds) beside `rows`
(what carries a usable date), the run prints the drop as it happens, and the page
names it on that city's card and totals it on the roster. Quantify the drop and
name the gate; never let it pass silently.

### Socrata has no `round()`

Verified live: `400 query.soql.no-such-function`. So coordinate binning cannot be
pushed server-side for Calgary, Edmonton or Winnipeg the way Montreal's SQL
endpoint allows. Those three page raw coordinates ordered by `:id` (Socrata's
stable row handle — ordering by date is not unique and would repeat or skip rows
across page boundaries) and bin in Python.

### Vancouver's `propertyuse` is multi-valued

A mixed-use tower legitimately carries *Dwelling Uses*, *Parking Uses* and
*Retail Uses* at once. Stringifying the list produced **153 combination
pseudo-categories** instead of ~15 real ones. Counting a permit once per use
would instead break every column total, so the **first-listed use** is taken as
primary — one permit, one category, columns sum to the true permit count — and
the card states that secondary uses on mixed-use projects are not represented.

### A field can start later than the record

Winnipeg only began recording `type_of_structure` in 2020 on a series running
from 2010. A chart that simply starts late reads as *nothing was built*, so the
page compares each matrix's first year against the city's record start and says
so when they differ.

### Weighting basis

**Montreal and Winnipeg publish no cost field at all** (Winnipeg's own dataset
description says so). Everything for them is weighted by permit count, the page
says so per card, and the Value toggles are disabled rather than showing an empty
axis. Toronto's `EST_CONST_COST` carries a literal placeholder string on ~45% of
rows; those are counted and excluded, never coerced to zero.

### Names: the 20-permit floor is editorial, not technical

Unchanged from `municipal_permits_etl.py` and for the same reason: `applicant` is
often the design professional or their firm, no private homeowner personally
files dozens of permits, and a **cloud makes a name more prominent than a table
row does, not less**. The list is deepened to 120 entries, not loosened. Names
are available for Vancouver (applicants + contractors), Calgary (both), Ottawa
(contractors) and Winnipeg (applicants).

Edmonton excludes applicant identity deliberately as a stated privacy measure —
a publisher's choice, not a gap. Mississauga, Halifax and Montreal never
collected the field.

**Toronto's `BUILDER_NAME` exists** — `docs/CONSTRUCTION.md` says it has no
applicant/contractor field, which is imprecise. Checked live on a 6,000-row
sample it is populated on **2.2%** of rows and is mostly individuals rather than
firms, so the practical conclusion (no concentration panel) stands.

### Toronto gains two panels it did not have

`APPLICATION_DATE`, `ISSUED_DATE` and `COMPLETED_DATE` are each **100%
populated** on the cleared resource (same live sample), so both an approval
interval and a build interval are measurable — neither exists in
`municipal.json`. The build interval is **right-censored by construction**:
"cleared" means closed, so a permit only enters this population once it has
completed, and recent years contain only the projects that finished fast. The
page says so on the card.

### The word cloud is the weaker chart, and is treated as such

A sized-text cloud cannot be read precisely and cannot be compared across terms.
It is the visual headline; the ranked table sits directly beneath it and is what
the page tells the reader to quote. Where names don't all fit the available
space, the count that fitted is stated — the rest are in the table, not dropped.

### A city is not its CMA

The City of Toronto excludes Peel, York, Durham and Halton; the City of Vancouver
is a fraction of its CMA. These series cannot be reconciled with the CMA figures
on the Construction Tracker, and every card says so. Halifax Regional
Municipality is the near-exception — its boundary is close to its full CMA.
Mississauga is not its own CMA at all (it sits inside Toronto's).

## Regenerating / refresh

```bash
cd Python
python permits_detail_etl.py                      # all nine cities
python permits_detail_etl.py --only calgary,toronto   # a subset
python permits_detail_etl.py --refresh            # Ottawa: re-download workbooks
```

`--only` preserves the roster entries of cities it doesn't rebuild. The run exits
non-zero on any fetch failure, so a scheduled refresh fails loudly rather than
publishing a half-built tree. Ottawa's workbooks cache under
`Python/ottawa_cache/` (gitignored); the current calendar year's workbook is
always re-downloaded, closed years only with `--refresh`.

`permits_json/` is gitignored on `main` and published only to `gh-pages`, like
every other generated tree.
