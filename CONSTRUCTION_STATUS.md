# Construction Dashboard — Build Status

Companion to CONSTRUCTION_PLAN.md. Updated as work progresses so any session
(human or Claude Code) can resume from the last completed milestone.
**If resuming: read CONSTRUCTION_PLAN.md first, then this file, then start at
the first unchecked item.**

## Milestones

- [x] **Phase 1 — Core ETL** (`Python/construction_etl.py` → `construction_json/`)
  - 6 StatCan tables, 21 geography files + meta.json, 64–95 KB each.
  - 2026-07-09: slimmed output (chart whitelist, dollars in millions, ints,
    NSA-pruning). Conventions documented in plan §2.5 and the script header.
  - Known quirk: permits/investment history starts 2017–2018 only; starts
    series run from 1990. Charts must handle mixed history.
- [x] **Phase 4a — Context ETL** (`Python/construction_context_etl.py` → `construction_json/context.json`)
  - All six sources fetched incl. BCPI 18-10-0289. 52 series, 77 KB.
  - BoC overnight (V39079) only reaches back to 2009 — acceptable.
- [x] **Phase 2+3 — construction.html** (single file, ceud.html design system)
  - All core sections built. Chart-pair pattern (shared x + linked hover)
    instead of dual axes (dataviz rule). Palette validated: series "navy" is
    #245A96 (brand #0B2545 fails data-color checks; UI chrome keeps brand navy).
- [x] **Phase 4b — Advanced sections** (rate pair, net new supply, construction labour)
- [x] **Verification** — browser preview: zero console errors; Canada and
  Ottawa views checked against published StatCan figures (SAAR 261,377;
  permits $12.5B; UC 347,543 at its Dec 2022 discontinuation); geography
  switch, simple/advanced toggle, share/real/MA toggles, sortable CMA table,
  crosshair tooltips and linked chart-pair hover all exercised. (Preview
  screenshot tool timed out — capture bug, page responsive throughout.)
- [x] **Phase 5 — Automation + docs**
  - `.github/workflows/construction-refresh.yml` (monthly 20th 14:00 UTC, no
    commit on fetch failure); ETL paths made repo-relative for ubuntu runner;
    cache dir gitignored. Readme.MD "Construction Tracker" section added.

## The provincial pipeline-gap saga (2026-07-09, resolved)

Three findings, in order:
1. 34-10-0143's UC series ends **2002**; swapped the ETL to 34-10-0151.
2. 0151's UC/completions still end **2022-12** for provinces (starts continue).
   Tried quarterly 34-10-0136 as a supplement.
3. Queried the live cubes: 0136, 0139 and annual 0126 are ALL null after 2022 —
   **CMHC discontinued province-level under-construction and completions
   entirely.** Only CMAs (34-10-0154) carry them currently. 0136 wiring
   removed again; the dashboard annotates the gap instead (KPI tile note +
   pipeline chart caveat), and meta.json documents it under
   `provincial_pipeline_gap`. Do not go looking for a replacement table.

## Decisions log

- Dollar series stored in **millions**; counts as **ints**; SAAR in units.
  (see meta.json series_units)
- `starts_market` kept at unit=total only; `multiples` dropped.
- Data fetched from `construction_json/` relative path locally; `BASE_URL`
  constant at top of construction.html script block switches to
  raw.githubusercontent.com for deployment (same pattern as retrofits.html).

## Resume notes

(nothing yet)
