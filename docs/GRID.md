# Live Grid Dashboard

`grid.html` — years of real generation-mix, capacity-utilization, demand,
price and intertie history for Ontario and Alberta, plus a recent/live layer
("what's powering the grid right now") and the **average vs marginal
emissions** explainer the Heat Pump Explorer's default assumption rests on.

**Live:** https://ottawavisuals.github.io/Energy/grid — shipped 2026-07-24,
deep-history section added 2026-09-03.

## Pipeline

```
Python/grid_etl.py                     # -> grid_json/{grid_on,grid_ab,grid_qc,meta}.json
                                       #   recent/live layer: last 14 days hourly +
                                       #   ~12mo daily min/mean/max. Weekly.
HeatPump/pipeline/grid_common.py       # shared fetch/parse/EF logic (also used by
                                       #   the Heat Pump tool's Phase-1 scripts)
.github/workflows/grid-refresh.yml     # weekly, Mondays 13:00 UTC
                                       #   (first scheduled run green 2026-07-13)

Python/grid_history_etl.py             # -> grid_json/grid_{on,ab}_history.json
                                       #   deep-history layer: monthly generation
                                       #   mix, capacity factor by fuel, demand,
                                       #   HOEP price, intertie flows, Global
                                       #   Adjustment (ON only for the last four --
                                       #   see script docstring for exactly which
                                       #   of six further IESO reports backs each
                                       #   metric, and why each starts in a
                                       #   different year). NOT on the weekly
                                       #   Action -- run manually, occasionally;
                                       #   ~120MB of IESO capacity CSVs get cached
                                       #   to HeatPump/data/raw/ieso_history/ on
                                       #   first run, then only the current
                                       #   still-open month re-fetches.

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

### Deep-history section (2026-09-03)

Six charts, each backed by its own IESO report discovered by browsing
`reports-public.ieso.ca/public/`'s open directory listing (not documented
anywhere else — see `Python/grid_history_etl.py`'s docstring for the full
inventory of what else lives there and was deliberately not built):

| Chart | Report | ON history from | AB history from |
|---|---|---|---|
| Generation mix | `GenOutputbyFuelMonthly` | 2015-01 | 2015-01 (cached AESO CSD zips) |
| Capacity factor by fuel | `GenOutputCapabilityMonth` | 2019-05 | 2015-01 (same AESO source, `Maximum Capability` column) |
| Demand | `Demand` | 2002-05 | — (no AB equivalent) |
| HOEP price | `PriceHOEPAverage` | 2002-05 | — |
| Intertie flows (Advanced) | `IntertieScheduleFlowYear` | 2018-01 | — |
| Global Adjustment | `GlobalAdjustment` | 2025-08 (14 months — source's own retention limit, confirmed live, no yearly archive exists) | — |

Each chart's start date is real, not padded or truncated to match the
others — a `null` gap before a metric's own start date shows as an actual
gap in the chart, per the honesty-rails "show a gap rather than interpolate
one away" rule, not a zero or an extrapolation.

**Capacity-factor methodology, the one non-obvious part:** Ontario's
`GenOutputCapabilityMonth` report gives dispatchable fuels (GAS, HYDRO,
NUCLEAR, BIOFUEL) a real registered `Capability` figure, but WIND and SOLAR
have no such row at all — only `Available Capacity`, IESO's own
weather-adjusted forecast of what those assets could produce that hour. So
Ontario's wind/solar capacity-factor answers "what share of the wind/sun
actually available did we use" (typically high), not "what share of
nameplate capacity ran" (which would be low, by the nature of an
intermittent resource) — a genuinely different question from every other
fuel on the same chart, stated on the page rather than blurred together.
Alberta's AESO data doesn't have this split — `Maximum Capability` is a
fixed, nameplate-like figure per asset for every fuel type including wind
(confirmed live: constant across ~4,300 hourly readings for a sample wind
asset) — so AB's wind/solar capacity-factor and ON's are not directly
comparable without accounting for that difference.

Alberta has no equivalent to Ontario's demand/HOEP/intertie/Global-Adjustment
reports — those are IESO-specific market mechanisms with no AESO analogue
fetched by this project.

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
