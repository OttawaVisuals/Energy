# Ottawa Geothermal — Build Log & Status

Companion to [ottawa-geothermal-guide.md](ottawa-geothermal-guide.md) (the 8-step
pipeline plan). This file records what has actually been built and run.

*Last session: 2026-07-10.*

**Live:** https://ottawavisuals.github.io/Energy/Geothermal/output/

## 2026-07-10 session — committed and published

All pipeline outputs and scripts committed to `main` (commit `cf1c862`), including
the `_code_*.csv` lookup tables, the rebuilt `ottawa_geothermal.gpkg`, all six
processed GeoJSON/TIFF layers, and `output/index.html`. Nothing needed
gitignoring — even the largest processed file (`combined_layers.geojson`, 40 MB)
is well under GitHub's 100 MB hard limit.

Published via the same GitHub Pages setup already serving `retrofits.html` /
`ceud.html` / `construction.html` from the repo root: GitHub Pages resolves
extensionless URLs by trying `path`, then `path.html`, then `path/index.html`, so
`Geothermal/output/index.html` is reachable directly at
`.../Energy/Geothermal/output/`. (In the process, found the `retrofits.html` live
link documented in `Readme.MD` pointed at a repo name — `Ottawa-Visuals` — that
404s; the working one is `.../Energy/retrofits`. Fixed both links.)

Verified live in a browser preview: page loads with no console or network errors,
all six layer checkboxes toggle, zoom controls work, and a well marker's popup
renders real data (ID, open-loop status, lithology, conductivity, yield, static
water level, depth).

## Pipeline status

| Guide step | Status | Output |
|---|---|---|
| 1. WWIS quality audit | done (June 2026) | `Geothermal/Data/Raw/WWIS/analyze*.py`, scatter PNGs, `wwis_data_quality_comparison_v2.xlsx` |
| 2. Clean & filter WWIS | done | `Geothermal/Data/processed/wwis_ottawa.geojson` |
| 3. Thermal conductivity per well | done | `Geothermal/Data/processed/thermal_conductivity.geojson` |
| 4. Open-loop feasibility | done | `Geothermal/Data/processed/open_loop_feasibility.geojson` |
| — Rich relational build (supersedes 2–4) | done, rebuilt 2026-07-09 with full code tables | `Geothermal/Data/processed/ottawa_geothermal.gpkg` via `combine_wells.py` |
| 5. Ottawa municipal layers | done 2026-07-09 (footprints & city-owned properties deferred — see below) | `zoning_industrial.geojson`, `sewer_lines.geojson`, `city_open_loop_potential.geojson` via `fetch_municipal_layers.py` |
| 6. Interpolated conductivity surface | done 2026-07-09, incl. GeoTIFF | `thermal_conductivity_grid.geojson` + `.tif` via `interpolate_conductivity.py` |
| 7. Merge layers | done 2026-07-09, 6 layers | `Geothermal/Data/processed/combined_layers.geojson` via `merge_layers.py` |
| 8. Interactive HTML map | done 2026-07-09, 6 toggleable layers | `Geothermal/output/index.html` via `build_map.py` |
| — Grid capacity (OEB CCIM) | done (July 2026) | `GridCapacity/ottawa_capacity.geojson` via `GridCapacity/Hydro.py` |

## 2026-07-09 session — steps 6–8 built and run

Environment: installed `geopandas 1.1.4`, `shapely 2.1.2`, `scipy 1.18.0`,
`pyogrio` into the system Python 3.14 (pandas/numpy/pyproj were already there).

### 1) `combine_wells.py` re-run (verify gpkg matches the rewritten script)

Rebuilt `ottawa_geothermal.gpkg` cleanly. Layer counts:

| layer | rows |
|---|---|
| wells | 55,903 (5,068 without shapefile geometry) |
| formations | 144,719 |
| water | 62,324 |
| pump_tests | 44,026 |
| construction | 125,495 |

Derived screening: conductivity class medium 35,183 / unknown 14,000 / low 6,535 /
high 185; open-loop viable 31,783 / possible 3,603 / unlikely 20,517.
All code lookups used the built-in fallbacks (no `_code_*.csv` exported yet —
exporting them from the Access db would upgrade the ~14k "unknown" lithologies).

### 2) New script: `Geothermal/scripts/interpolate_conductivity.py` (step 6)

IDW (k=12, power 2) on a 500 m grid in UTM 18N, from the gpkg wells layer
(37,916 wells with a conductivity estimate after clipping to the guide's Ottawa
bbox — the clip drops 17 mis-located wells that otherwise scattered 734 stray
cells across Ontario). Cells only emitted where the nearest well is ≤ 2 km;
confidence = high when ≥ 5 wells sit within 1.5 km.

Result: **13,376 cells** — medium 11,777 / low 1,379 / high 220; confidence
high 11,777 / low 1,599; range 1.40–2.99 W/m·K.
Not produced: the guide's optional GeoTIFF twin (needs `rasterio`; the GeoJSON
grid is what the map consumes).

### 3) New script: `Geothermal/scripts/merge_layers.py` (step 7)

Merges into one FeatureCollection with a `layer` property per feature
(`conductivity_grid`, `wells`, `grid_capacity`). Wells come from the gpkg
(bbox-clipped, slimmed to popup fields); capacity polygons are simplified
(~10 m) and slimmed; coordinates rounded to 5 decimals.

Result: `combined_layers.geojson`, **68,068 features, 24.1 MB**
(13,376 grid cells + 50,808 wells + 3,884 feeder polygons).

### 4) New scripts: `build_map.py` + `map_template.html` (step 8)

`Geothermal/output/index.html` — single self-contained Leaflet map (5.9 MB).
To keep it small the grid is embedded as `[w,s,e,n,cond,confidence]` tuples and
wells as compact arrays; only feeder capacity stays as GeoJSON. Full-fidelity
GeoJSON remains in `Data/processed/`. Three toggleable canvas-rendered layers
(conductivity choropleth, wells coloured by open-loop status, feeder capacity
red→green by MVA), popups on everything, fixed legend. OSM basemap from CDN —
the only part needing internet.

Verified in a local browser preview: all 50,808 well markers render, popups show
correct values for all three layers, no console errors, wells layer adds in
~190 ms. (Quebec side of the river is empty by construction — WWIS is
Ontario-only.)

### Grid capacity data (already fetched, now integrated)

`GridCapacity/ottawa_capacity.geojson`: 3,884 Hydro Ottawa feeder polygons from
the OEB Centralized Capacity Information Map ArcGIS service. Available capacity
0–16.4 MVA; range buckets: 0–1 MVA ×1,348, 1.1–3 ×1,655, 3.1–5 ×420,
5.1–10 ×288, 10+ ×34, unknown ×139. `last_update` in the data ≈ 2026-05-01;
re-run `GridCapacity/Hydro.py` to refresh.

## Gap-closure session (2026-07-09, second pass)

All three data gaps from the first pass were addressed:

### 1) WWIS lithology code tables exported → ~4,300 wells recovered

Exported the seven `_code_*.csv` lookup tables from the Access db
(`Data2024Q4 250723 181853.mdb`, via pyodbc) into `Geothermal/Data/`, where
`combine_wells.py` auto-prefers them over its built-ins. The formation-material
table has **82 codes vs the 15 built-ins** (codes 60–92 are texture modifiers,
correctly left unbucketed). Also extended `combine_wells.py`'s lithology
buckets (marl→clay, conglomerate/greywacke→sandstone, marble→limestone,
schist/soapstone→gneiss, quartz/chert/feldspar/flint→granite, basalt new bucket
at 2.0 W/m·K, overburden→till, quicksand→sand, gypsum→shale).

Result: conductivity-class unknowns **14,000 → 9,680**; high 185 → **1,700**
(Shield granite/gneiss wells now decoded); medium 36,965; low 7,558.
Downstream, the interpolation now uses 41,921 wells (was 37,916) and
high-conductivity cells rose 220 → **1,137**; surface range 1.40–3.20 W/m·K.

### 2) Step 5 municipal layers fetched (`fetch_municipal_layers.py`)

From the City's ArcGIS server (maps.ottawa.ca/arcgis/rest/services):

| output | source layer | features |
|---|---|---|
| `zoning_industrial.geojson` | Zoning/3, `ZONE_MAIN IN (IL,IG,IH,IP,RG,RH)` | 618 |
| `sewer_lines.geojson` | WastewaterInfrastructure/7 (sanitary) + /14 (combined) | 63,300 (17.3 MB) |
| `city_open_loop_potential.geojson` | Planning/122 — the City's own **Open Loop Geothermal Potential** layer (High/Average/Low/None) | 158 |

Gotchas recorded for reruns:
- `f=geojson` returns HTTP 400 on the WastewaterInfrastructure layers — the
  script uses esriJSON + a converter for those.
- The Zoning layer's `ZNAME_EN` mislabels IG as "Transportation Zones";
  By-law 2008-250 Part 11 defines IG = General Industrial. `build_map.py`
  ships canonical names from its own `ZONE_NAME` table.

**Deferred, deliberately:** building footprints (TopographicMapping/3 is 392k
polygons ≈ 0.5 GB; nothing consumes them yet) and city-owned properties (the
guide's dataset no longer exists on open.ottawa.ca — searched 2026-07-09).

### 3) GeoTIFF export added

`interpolate_conductivity.py` now also writes
`thermal_conductivity_grid.tif` (EPSG:32618, 500 m, NaN = no coverage;
requires `rasterio`, installed).

### Rebuilt outputs

- `combined_layers.geojson`: now **132,151 features / 41.2 MB** across six
  layers (conductivity_grid 13,383 · wells 50,808 · grid_capacity 3,884 ·
  zoning_industrial 618 · sewer_lines 63,300 · city_open_loop_potential 158).
- `output/index.html`: **6.7 MB**, six toggleable layers. Only trunk sanitary
  (`FUNCTION <> LOCAL`) + all combined sewers are embedded (5,491 polylines,
  0.5 MB) — local laterals stay in the processed GeoJSON. Verified in a live
  browser: no console errors, popups correct on all six layers (incl. the IG
  fix), municipal layers render where expected (combined sewers cluster in the
  old core; city potential covers the urban area).

## Third pass (2026-07-09): documentation + validation + lithology polish

- **Process documentation** consolidated into `Geothermal/README.md` — data
  sources, method details per script, results, caveats, next steps. This file
  stays the session-by-session build log.
- **New script `validate_against_city.py`** — spatial join of all wells to the
  City's Planning/122 potential polygons, crosstab + per-class yield stats
  (output: `Data/processed/city_validation.csv`). Findings: 32,807 of 50,808
  wells are outside the City layer (it only rates the serviced urban area —
  complementary coverage, not disagreement); within it, mean pump-test yield
  orders the City's classes correctly (High 76 L/min → Average 37 → Low/None
  27); our "unlikely" wells inside High/Average polygons are mostly
  missing-data cases, not contradictions.
- **Lithology recovery, round 2** in `combine_wells.py`: primary lithology now
  comes from the thickest *bucketable* layer (a well whose thickest interval
  has no recorded material no longer gives up), and generic "ROCK" (code 26)
  became its own bucket at 2.5 W/m·K (counts as bedrock). Unknowns
  9,680 → **9,180**; 7,872 of those have no formation record at all
  (checked — irreducible). Wells class mix now: medium 37,671 / low 7,351 /
  high 1,701.
- **Full chain re-run** (combine → interpolate → merge → build_map →
  validate): grid 13,383 cells (medium 11,174 / high 1,107 / low 1,102,
  1.40–3.20 W/m·K); `combined_layers.geojson` 132,151 features / 41.2 MB;
  `output/index.html` 6.8 MB. Map template unchanged from the verified build;
  only embedded data values changed.

## Remaining ideas / next steps

See `Geothermal/README.md` §6 for the full list. Highlights: publish the map
on GitHub Pages; closed-loop borehole-metres-per-kW economics per cell;
building footprints for heat demand; sewer heat-recovery ranking; GSC bedrock
geology as a conductivity fallback where wells are sparse.

## Regenerating everything

```bash
python Geothermal/scripts/combine_wells.py             # gpkg from WWIS exports (+ _code_*.csv)
python Geothermal/scripts/fetch_municipal_layers.py    # step 5 city layers (zoning/sewers/potential)
python Geothermal/scripts/interpolate_conductivity.py  # step 6 surface (geojson + tif)
python Geothermal/scripts/merge_layers.py              # step 7 combined layers
python Geothermal/scripts/build_map.py                 # step 8 output/index.html
python GridCapacity/Hydro.py                           # refresh feeder capacity
```
