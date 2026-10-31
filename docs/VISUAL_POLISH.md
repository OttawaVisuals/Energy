# Shared visual polish

Updated 2026-10-31. Implemented and verified locally; not yet published.

## What changed

- Homepage tiles use the ten approved illustrations, trimmed and balanced by
  visible area on identical 512×216 canvases. Compact WebP files total 133,174
  bytes versus 7,222,332 bytes for the original PNGs. Original artwork is kept
  for social cards and other large uses.
- Artwork sits in a soft neutral panel, with a muted backing in dark mode.
  Each of the ten tools reuses its illustration beside the main title; the
  Geothermal map uses a compact image in its title panel.
- Shared chart presentation aligns legend text, tooltip typography, download
  controls, keyboard focus and scrollable table access. Chart colours and
  data meanings remain owned by each tool.
- Insights and Grid headers wrap on phones. Heat Pump labels and controls
  no longer clip. New Homes keeps usable minimum widths for postal-area
  selectors. Narrow layouts use one-column chart grids where needed.
- CEUD and Heat Pump SVGs draw in screen-sized coordinates on phones instead
  of compressing a fixed 740–920px drawing. Axis-label density follows the
  available plot width; no observations are removed. Heat Pump panels redraw
  when they first become visible and after width changes.
- On phones, Geothermal's building-type selector and legend are expandable
  panels. The layers menu starts collapsed. Conductivity assumptions support
  keyboard activation; competing panels close to keep the map usable. Desktop
  retains its expanded controls. No map data was rebuilt.

## Implementation

`assets/visual-polish.css` and `assets/visual-polish.js` are a shared,
presentation-only layer loaded after each tool's own styles. Static title images
remain present without JavaScript. The map's tracked template includes the same
markup as its generated HTML.

`Python/build_visual_polish.py` prepares `assets/icons/web/*.webp` from the
approved PNGs and adds the presentation markup. It requires Pillow at build
time; no new browser dependency is introduced. CEUD and Heat Pump keep their
own inline chart geometry helpers.

## Verification, 2026-10-31

Automated checks used installed Chrome via Playwright against a local static
server, with the actual local datasets. Evidence is saved outside the repository
at `C:/Ottawa_Visuals/output/visual-polish/`.

- 58 cases passed: homepage plus ten tools at 320, 375, 768 and 1440px; dark
  and colour-blind mode at 375px on the seven pages that already support themes.
  No page-level horizontal overflow, missing artwork, clipped selectors or
  uncaught script errors were found in those cases.
- 11 interactions passed: legend expansion, mutually exclusive map controls,
  building-type change, keyboard assumptions toggle, CEUD sector change, CSV
  download, Grid province/theme changes, tooltip containment, Heat Pump input
  update and keyboard table scrolling.
- 16 additional Heat Pump chart cases passed: all four load-chart views
  (temperature, weighted, daily and hourly) at 320, 375, 768 and 1440px.
- The full default Heat Pump simulation result and CEUD's displayed KPI values
  were compared with the previous committed pages: both matched exactly.
- Phone chart screenshots confirmed readable SVG axes. Homepage light/dark
  artwork and the map's collapsed/expanded controls were visually inspected.
- `git diff --check` passed.

Limits: this is a representative browser/layout review, not an exhaustive test
of every data filter, chart view, mobile browser or assistive technology. CEUD,
Construction and Permits retain their existing light-only interfaces; Geothermal
retains its light map controls. Wide data tables and technical diagrams scroll
inside their containers. Existing data/source limitations remain unchanged.

Published 2026-10-31. Landing-page author card was reworded the same day (portfolio statement: credentials, skill bullets, feedback invitation). The unrelated author-contact script was not edited.
