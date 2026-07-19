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
(nominal or constant $), investment by work type (new / renovation / conversion),
per-capita provincial comparisons, and a sortable CMA table. Advanced mode adds the
rate cycle (starts vs BoC overnight + 5-yr mortgage), net new supply (units created
vs lost on permits), and construction employment vs backlog.

## Data pipeline

```
Python/construction_etl.py          # core: StatCan 34-10-0292 (permits),
                                    #   34-10-0293 (investment), 34-10-0151 +
                                    #   34-10-0154 (starts/UC/completions),
                                    #   34-10-0158 (SAAR), 34-10-0148 (market)
Python/construction_context_etl.py  # context: 18-10-0205 NHPI, 17-10-0009 pop,
                                    #   14-10-0355 construction employment,
                                    #   34-10-0145 5-yr mortgage, 18-10-0289 BCPI,
                                    #   Bank of Canada Valet (overnight rate)
        → construction_json/        # one compact JSON per geography + context.json
                                    #   + meta.json (key scheme, units, dates)
```

Conventions: dollar series stored in **millions**; unit counts as **integers**;
unadjusted variants shipped only where no seasonally adjusted sibling exists.
Permits & investment history begins 2017–2018 (StatCan's redesigned programs);
CMHC series run from 1990. **Known data gap:** CMHC discontinued province-level
under-construction and completions after 2022 in every table (verified against
34-10-0151/0136/0139/0126); those series end Dec 2022 for provinces/Canada and
the page annotates this. Metro areas (34-10-0154) carry all pipeline stages to
the current month.

## Regenerating / refresh

```bash
cd Python
python construction_etl.py            # cached downloads; --refresh to force
python construction_context_etl.py
```

`.github/workflows/construction-refresh.yml` does this monthly (20th, 14:00 UTC)
and commits `construction_json/` only when all fetches succeed and data changed.
