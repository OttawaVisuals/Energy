# Live Grid Dashboard

`grid.html` — "what's powering the grid right now" for Ontario and Alberta, plus
the **average vs marginal emissions** explainer the Heat Pump Explorer's default
assumption rests on.

**Live:** https://ottawavisuals.github.io/Energy/grid — shipped 2026-07-24.

## Pipeline

```
Python/grid_etl.py                     # -> grid_json/{grid_on,grid_ab,grid_qc,meta}.json
HeatPump/pipeline/grid_common.py       # shared fetch/parse/EF logic (also used by
                                       #   the Heat Pump tool's Phase-1 scripts)
.github/workflows/grid-refresh.yml     # weekly, Mondays 13:00 UTC
                                       #   (first scheduled run green 2026-07-13)

Python/build_grid_seasonal.py          # -> grid_json/typical_day_{on,ab}.json
                                       #   one-off/manual: reuses the Heat Pump
                                       #   tool's own multi-year hourly Phase-1
                                       #   output (HeatPump/data/processed/
                                       #   grid_ef_{on,ab}.json) to build the
                                       #   page's Advanced "typical day by
                                       #   season" panel. Not on the weekly
                                       #   schedule -- rerun manually whenever
                                       #   the Phase-1 files are refreshed.
```

Coverage:

- **ON (IESO)** — fully live; the per-year XML report is re-fetched every run.
- **AB (AESO)** — parse-only from manually placed CSD zips in
  `HeatPump/data/raw/aeso/` (no scriptable recent AESO source; their API needs a
  registered key). Staleness doesn't block the ON refresh; the page shows a
  banner when Alberta is selected.
- **QC** — static flat-EF context card (Hydro-Québec's export is likewise a
  manually placed file), shown on the page regardless of the ON/AB toggle.

Each province JSON carries hourly resolution for the last 14 days and daily
min/mean/max beyond, over a rolling ~12-month window. Validation and
source-reference notes are in the script's docstring; the emission-factor
methodology is documented in [HeatPump/METHODOLOGY.md](../HeatPump/METHODOLOGY.md).

## The page

Chrome/theme (header, hero, Simple/Advanced toggle, light/dark/colour-blind
theme) reuses `assets/site-theme.css`, same as retrofits.html/newhomes.html/
retrofit-insights.html. Charts are hand-rolled SVG (ported from
construction.html's chart-pair engine — `svgEl`/`niceTicks`/linked-hover
tooltips), not Chart.js: no external chart library, no animation-frame
dependency, and the "chart pair" (stacked generation mix above, intensity line
below, same x-axis, linked crosshair) the ROADMAP prompt called for falls out
of the same primitive construction.html already uses for permits-vs-starts.

Sections: KPI row (latest hour) · last-24-hours chart pair · last-12-months
daily min/mean/max band · the average-vs-marginal interactive explainer
(links to heatpump.html) · Advanced-only typical-day-by-season chart (see
`build_grid_seasonal.py` above) · Alberta staleness banner · Quebec static
context card · sources accordion. Reciprocal link added from heatpump.html's
header back to grid.html.
