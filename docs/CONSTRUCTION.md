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
`newhomes_json/` — the only section on the page that needs no fetch of its own.

Advanced mode also gains construction job vacancies and the average offered hourly
wage, alongside the existing employment-vs-backlog chart.

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
python construction_context_etl.py
```

`.github/workflows/construction-refresh.yml` does this monthly (20th, 14:00 UTC)
and commits `construction_json/` only when all fetches succeed and data changed.
