# CMHC HMIP table catalogue

Research note, not a tool. It answers one question: **what does CMHC publish
on its Housing Market Information Portal (HMIP) that Statistics Canada's
CMHC-sourced tables don't?** Nothing is built on it yet. It's here so the next
tool that needs CMHC data starts from a list, not a guess.

- Script: [`Python/hmip_catalogue.py`](../Python/hmip_catalogue.py)
- Output: `cmhc_json/` (gitignored, local only; regenerate from the page cache in seconds)
- Crawled: **2026-11-05**, 859 network requests, 885 table pages, 1 failure

## Plain-language summary

CMHC runs two kinds of public housing statistics. A slice of them is copied
into Statistics Canada's tables, which have a proper API. Most of the detail
stays on CMHC's own website (HMIP), which has no API and no published list of
what's there. We read the website's own menus to build that list.

HMIP has about **60 measures**. Split by breakdown (bedroom count, building
age and so on), that makes **79 tables**. Splitting again by geography level
gives **489 combinations**. StatCan carries **36 active** CMHC tables. Those
stop at the city level and cover only starts and completions, purpose-built
rental vacancy and rents, new-home absorption, and a mortgage rate.

What only HMIP has:

1. **Rental market down to census tract**: vacancy, availability, average and
   median rent, and number of units, by bedroom count, **year of
   construction** or building size, from 1990 on.
2. **Housing starts, completions and under-construction down to census
   tract**, plus construction time and new-home absorption (units, share sold
   at completion, prices).
3. **Secondary rental market** (from 2007): condos rented out and other
   rented dwellings.
4. **Seniors' rental housing** (from 2009).
5. **Census-based household and core-housing-need tables by tract.** The
   underlying census data is StatCan's, but these cuts aren't in StatCan's
   CMHC tables.

## Is there a CMHC API? (checked 2026-11-05)

- **No public, documented API** for housing-market statistics was found.
- `https://lt-ext-api.cmhc-schl.gc.ca/` is real: a Microsoft Azure API
  Management developer portal titled "CMHC Connect Developer Portal". It sits
  behind a login, `/apis` returns 404 without one, and logging in accepts
  CMHC's Terms of Use. CMHC Connect is CMHC's partner sign-in (lenders,
  program applicants), so this portal **probably serves partner business
  functions, not market statistics**. That is an inference: we did not sign in
  and could not see its API list.
- HMIP itself has an undocumented CSV export (`ExportTable`) behind each
  table. The `cmhc` R package (mountainMath) wraps it. The Construction
  Tracker used it once, on 2026-08-27, to confirm that Ontario
  under-construction data is archived (see ROADMAP). This catalogue does
  **not** call it.
- StatCan WDS remains the documented, supported route for the slice it
  carries.

## Advanced methodology

### Sources

| Side | What we read | Vintage |
|---|---|---|
| StatCan | `getAllCubesListLite` (WDS). Every cube whose `cubeTitleEn` contains "Canada Mortgage and Housing Corporation": 55 tables, 36 with `archived=2` (active), 34-10-0125 to 34-10-0162 | 2026-11-05 |
| HMIP | Server-rendered HTML pages (below) | 2026-11-05 |
| Cross-check | `cmhc` R package `R/cmhc_tables.R` table codes | GitHub master, 2026-11-05 |

### Pages the crawler reads (HTML only, as a browser renders them)

| Page | Gives |
|---|---|
| `/hmip-pimh/en/TableMapChart?id=<geoId>&t=<typeCode>` | Full View menu: `a[data-category-link=true]`, query params `categoryLevel1/2/3` |
| `/TableMapChart/TableCategory?...` and `/TableMatchingCriteria?...` | `By:` and `Display Options:` lists. The share link `#share-section[data-url]` holds a base64 table URL with `TableId`, `Survey`, `DefaultDataField`, `BreakdownGeographyTypeId`. `div[data-year]` holds the year selector. The note line gives the source survey |
| `/Navigation/ProvincesByCountry`, `/MetsByProvince/<id>`, `/SurveyZonesAndCSDsByMet/<id>`, `/NeighbourhoodsBySurveyZone/<id>`, `/CensusTractsByNeighbourhood/<id>` | Geography drill-down (used once to pick the sample ids) |

Requests go out 1 per second, with a descriptive User-Agent that carries no
personal contact. Every page is cached in `Python/hmip_cache/` (scratch).

### Geography

HMIP type codes: 1 Country, 2 Province, 3 MetropolitanMajorArea (CMAs, CAs
and some towns), 4 CensusSubDivision, 5 SurveyZone, 6 Neighbourhood,
7 CensusTract. The menu is structural, so we crawl **one representative per
level**, plus one small centre:

| Level | Sample | Measures | Tables (By × Display) |
|---|---|---|---|
| Country | Canada (1) | 59 | 122 |
| Province | Ontario (35) | 59 | 108 |
| CMA | Toronto (2270) | 59 | 197 |
| Small centre | Bracebridge T (6035) | 37 | 75 |
| CSD | Aurora (T) (3519046) | 43 | 92 |
| Survey zone | Aurora, Newmkt, Whit-St. (227026) | 43 | 117 |
| Neighbourhood | Aurora (2270760) | 42 | 87 |
| Census tract | 0440.00 (22707600440.00) | 42 | 86 |

### Surveys behind the tables (`Survey` field)

`Scss` Starts and Completions Survey, incl. Market Absorption Survey ·
`Rms` Rental Market Survey · `Srms` Secondary Rental Market Survey ·
`Seniors` Seniors' Housing Survey · `CensusPopulationHouseholdsHousingStock`
and `CensusCoreHousingNeed` (CMHC adaptations of the Census / NHS).

### Outputs

- `hmip_catalogue.json` / `.csv`: one row per fetched table page. Fields:
  `geo_*`, `cat1..3`, `by`, `display`, `table_id`, `survey`, `data_field`,
  `breakdown_geo_type`, `year_first`, `year_last`, `quarterly`, `title`,
  `source`, `url`, `status`.
- `hmip_catalogue_matrix.csv`: one row per (category, measure, By, Display),
  with one column per sample geography holding the `TableId` found there.
  A blank cell means not offered at that place.

### Validation

- Table IDs match the R package's hand-built list where both cover a table,
  e.g. starts/completions by census tract `1.1.1.11` / `1.1.2.11`, by survey
  zone `1.1.1.8`.
- Re-running from cache gives identical counts (0 network requests).

### Data-quality notes (for any tool built on this later)

- RMS cells carry **reliability codes a–d** (a = excellent, d = poor, use with
  caution) and `**` for suppressed. A tool must show these, not strip them.
- HMIP's own notice (2026-11-05): unabsorbed inventory in Ontario is under a
  CMHC methodology review. Use with caution.
- Ontario under-construction is archived at HMIP (finding of 2026-08-27).

## Limitations

**What the data can't tell us.** The catalogue lists table *options*, not
data. A table offered at a level can still be mostly `**` for small places.
The years are the portal's year selector, not a check that each year has
values, and historical-series pages show none. One page failed: tract
"Summary Statistics" returned HTTP 500 on all 3 tries. It's marked `FAILED`.

**What we assumed.** That one place per level is enough to show that level's
menu. Bracebridge (37 measures against Toronto's 59) shows that smaller
places get less, so availability "at CMA level" really means "for Toronto".
We also assumed that sections other than By / Display Options don't change
the table set. They're recorded by label but not expanded.

**What would change the answer.** Crawling more places per level (use
`--geo TYPE:ID:LABEL`), a CMHC redesign of HMIP (the parser depends on its
HTML), or CMHC moving more series to StatCan.

## Licensing

HMIP data falls under the CMHC Data License Agreement. Required credit:
"Source: Canada Mortgage and Housing Corporation (CMHC), <product>,
<reference date>", or "Adapted from…" for derived work. **Read the full
licence before embedding any HMIP data in a page.** This catalogue holds
table names and IDs only, no data values.

## Re-running

```bash
python Python/hmip_catalogue.py                       # default 8 geographies, ~15 min cold
python Python/hmip_catalogue.py --geo 3:1265:Ottawa   # add a place
python Python/hmip_catalogue.py --refresh             # ignore the page cache
```
