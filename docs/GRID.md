# Live Grid Dashboard (ETL shipped; page not built yet)

"What's powering the grid right now / this month" for ON and AB — a public
explainer of grid mix and emissions intensity, and of the **average vs marginal
emissions** methodology the Heat Pump Explorer uses.

**Status:** the data layer is done and auto-refreshing; the page (`grid.html`)
is queued — see [ROADMAP.md](../ROADMAP.md) item 6 for the build prompt.

## Pipeline

```
Python/grid_etl.py                     # -> grid_json/{grid_on,grid_ab,grid_qc,meta}.json
HeatPump/pipeline/grid_common.py       # shared fetch/parse/EF logic (also used by
                                       #   the Heat Pump tool's Phase-1 scripts)
.github/workflows/grid-refresh.yml     # weekly, Mondays 13:00 UTC
                                       #   (first scheduled run green 2026-07-13)
```

Coverage:

- **ON (IESO)** — fully live; the per-year XML report is re-fetched every run.
- **AB (AESO)** — parse-only from manually placed CSD zips in
  `HeatPump/data/raw/aeso/` (no scriptable recent AESO source; their API needs a
  registered key). Staleness doesn't block the ON refresh.
- **QC** — static flat-EF context card (Hydro-Québec's export is likewise a
  manually placed file).

Each province JSON carries hourly resolution for the last 14 days and daily
min/mean/max beyond, over a rolling ~12-month window. Validation and
source-reference notes are in the script's docstring; the emission-factor
methodology is documented in [HeatPump/METHODOLOGY.md](../HeatPump/METHODOLOGY.md).
