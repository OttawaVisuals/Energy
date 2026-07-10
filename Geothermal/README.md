# Ottawa Geothermal Feasibility — Process Documentation

An end-to-end pipeline that turns Ontario's water-well archive and City of
Ottawa open data into an interactive ground-source-heat-pump (GSHP)
feasibility map for Ottawa: estimated ground thermal conductivity, open-loop
(groundwater) system screening, electrical grid capacity, and the municipal
siting context (zoning, sewers, the City's own geothermal potential rating).

- **Live:** https://ottawavisuals.github.io/Energy/Geothermal/output/
- **Plan:** [`../ottawa-geothermal-guide.md`](../ottawa-geothermal-guide.md) (the original 8-step guide)
- **Build log:** [`../GEOTHERMAL_STATUS.md`](../GEOTHERMAL_STATUS.md) (what ran when, session by session)
- **Final product:** `output/index.html` — one self-contained file, open in any browser

---

## 1. Data sources

| Dataset | Source | How obtained | Files |
|---|---|---|---|
| Water Well Information System (WWIS) | Ontario MECP | Access db export + provincial shapefile | `Data/Raw/WWIS/Data2024Q4 250723 181853.mdb` (1.4 GB), `Data/wwis_out.shp` (~1M wells, Ontario-wide), `Data/tbl*_Ottawa.csv` (Ottawa exports) |
| WWIS code lookup tables | same Access db | exported via pyodbc (see §3.1) | `Data/_code*.csv` (7 tables) |
| Hydro Ottawa feeder capacity | OEB Centralized Capacity Information Map | ArcGIS REST paging (`../GridCapacity/Hydro.py`) | `../GridCapacity/ottawa_capacity.geojson` (3,884 polygons) |
| Industrial/employment zoning | City of Ottawa `maps.ottawa.ca` Zoning/3 | `scripts/fetch_municipal_layers.py` | `Data/processed/zoning_industrial.geojson` (618) |
| Sanitary + combined sewers | City of Ottawa WastewaterInfrastructure/7 + /14 | same | `Data/processed/sewer_lines.geojson` (63,300) |
| City "Open Loop Geothermal Potential" | City of Ottawa Planning/122 | same | `Data/processed/city_open_loop_potential.geojson` (158) |
| GSC bedrock geology, NRCan reports | GeoScan / NRCan | manual download (reference only, not yet in pipeline) | `Data/Raw/GSC/`, `Data/Raw/NRCan/`, `Data/M183-2-6914-eng.pdf` |

Datasets that **could not** be obtained: the guide's "City-Owned Properties"
layer no longer exists on open.ottawa.ca (searched 2026-07-09). Building
footprints (TopographicMapping/3) exist but are 392k polygons (~0.5 GB) and
nothing in the pipeline consumes them yet — deferred.

## 2. Pipeline overview

```
WWIS Access exports (tbl*_Ottawa.csv) ─┐
WWIS code tables (_code*.csv) ─────────┤
WWIS shapefile (wwis_out.shp) ─────────┴─▶ [1] combine_wells.py
                                              └▶ ottawa_geothermal.gpkg (5 layers)
maps.ottawa.ca ArcGIS ────▶ [2] fetch_municipal_layers.py
                                └▶ zoning_industrial / sewer_lines /
                                   city_open_loop_potential .geojson
gpkg wells ───────────────▶ [3] interpolate_conductivity.py
                                └▶ thermal_conductivity_grid.geojson + .tif
everything above ─────────▶ [4] merge_layers.py
+ ottawa_capacity.geojson       └▶ combined_layers.geojson (6 tagged layers)
everything above ─────────▶ [5] build_map.py + map_template.html
                                └▶ output/index.html  (self-contained map)
gpkg + city potential ────▶ [6] validate_against_city.py
                                └▶ city_validation.csv + printed report
```

Run order (each step reads the previous step's outputs):

```bash
python Geothermal/scripts/combine_wells.py
python Geothermal/scripts/fetch_municipal_layers.py   # network; rerun to refresh
python Geothermal/scripts/interpolate_conductivity.py
python Geothermal/scripts/merge_layers.py
python Geothermal/scripts/build_map.py
python Geothermal/scripts/validate_against_city.py    # optional analysis
python GridCapacity/Hydro.py                          # refresh feeder capacity
```

**Dependencies:** `pandas numpy pyproj geopandas shapely scipy pyogrio
rasterio requests` (+ `pyodbc` and the Microsoft Access ODBC driver only for
re-exporting the code tables).

## 3. Method details, step by step

### 3.1 `combine_wells.py` — relational WWIS → GeoPackage

Builds `Data/processed/ottawa_geothermal.gpkg` with five layers: `wells`
(one row per well, geometry + derived screening fields), `formations`,
`water`, `pump_tests`, `construction`.

Key decisions:

- **Units.** Access tables store depths in ft/m/cm/inch and rates in GPM/LPM
  with per-row `*_UOM` columns; everything is converted to metres and L/min
  (WWIS default is feet when the UOM is missing). The provincial shapefile's
  `DEPTH`/`DP_BEDROCK`/`STATIC_LEV` are already metric and are treated as
  authoritative for per-well summary values.
- **Code tables.** `USE_1ST`, `MAT1-3`, water kind, casing material etc. are
  numeric codes. The seven `_code*.csv` lookups exported from the Access db
  (82 formation materials; codes 60–92 are texture modifiers, deliberately
  not bucketed) override a small built-in fallback. Unresolvable codes pass
  through as `code:NN` rather than being silently mislabelled.
  To re-export: connect pyodbc with
  `DRIVER={Microsoft Access Driver (*.mdb, *.accdb)}` and dump
  `_code_formation_Material`, `_code_water_kind`, `_codeWaterUse`,
  `_code_final_status`, `_codeColor`, `_code_casing_material`,
  `_code_construct_method` to CSV next to the data.
- **Lithology buckets → thermal conductivity.** Decoded materials map to
  buckets, each with a mid-range conductivity (W/m·K) from GSHP design
  literature — **estimates from drillers' logs, not measurements**:
  limestone 2.8, dolostone 3.0, sandstone 2.3, shale 1.9, granite 3.2,
  gneiss 3.0, clay 1.4, silt 1.5, sand 2.4, gravel 2.0, till 1.8, fill 1.5,
  basalt 2.0, generic "ROCK" 2.5. Metamorphics fold in (marble→limestone,
  schist→gneiss, quartzite/quartz/chert→granite), sediments likewise
  (marl→clay, conglomerate/greywacke→sandstone, quicksand→sand,
  overburden→till).
- **Per-well lithology** = the thickest *bedrock* layer if any, else the
  thickest *bucketable* layer (a well whose thickest interval has no material
  recorded still gets a lithology from its other intervals).
- **Open-loop screen** (consistent with the guide): `viable` = static water
  level present AND yield ≥ 15 L/min; `possible` = static level present,
  yield unknown; `unlikely` otherwise. Note "unlikely" is dominated by
  *missing data*, not proven unsuitability.

### 3.2 `fetch_municipal_layers.py` — City of Ottawa ArcGIS layers

Generic paged puller against `maps.ottawa.ca/arcgis/rest/services` (1,000
records/page). Server quirks handled:

- `f=geojson` returns HTTP 400 on the WastewaterInfrastructure layers —
  those are fetched as esriJSON and converted locally.
- The Zoning layer's `ZNAME_EN` mislabels IG as "Transportation Zones";
  By-law 2008-250 Part 11 defines IG = General Industrial. The map ships
  canonical names from its own table.
- Industrial filter: `ZONE_MAIN IN ('IL','IG','IH','IP','RG','RH')`
  (urban light/general/heavy/business-park + rural general/heavy).

### 3.3 `interpolate_conductivity.py` — conductivity surface

IDW interpolation (k=12 neighbours, power 2) of per-well conductivity on a
**500 m grid** in UTM 18N (EPSG:32618). Wells are clipped to the Ottawa bbox
(lon −76.36…−75.24, lat 44.96…45.61) first — a handful of mis-located records
otherwise scatter cells across Ontario. Cells are only emitted where the
nearest well is **≤ 2 km**; confidence is `high` when ≥ 5 wells sit within
1.5 km, else `low`. Class labels: low < 2.0 ≤ medium ≤ 2.8 < high (W/m·K).
Outputs both a GeoJSON polygon grid (what the map uses) and a GeoTIFF
(EPSG:32618, NaN = no coverage).

### 3.4 `merge_layers.py` — one FeatureCollection

Concatenates all six layers into `combined_layers.geojson`, every feature
tagged with a `layer` property (`conductivity_grid`, `wells`, `grid_capacity`,
`zoning_industrial`, `sewer_lines`, `city_open_loop_potential`). Wells are
slimmed to popup fields; capacity polygons simplified ~10 m; coordinates
rounded to 5 decimals. Step-5 layers are skipped gracefully if not fetched.

### 3.5 `build_map.py` + `map_template.html` — the map

Generates `output/index.html`: a single self-contained Leaflet page (only the
CDN Leaflet library and OSM basemap tiles need internet). Size is kept down
by embedding the two big layers as compact arrays instead of GeoJSON —
grid cells as `[w,s,e,n,cond,confidence]`, wells as flat tuples — and by
embedding only the **trunk** sewer network (sanitary `FUNCTION <> LOCAL` +
all combined; local laterals stay in the processed GeoJSON). Everything
renders on canvas (`preferCanvas`), so ~51k well points stay responsive.
Six toggleable layers, popups on every feature, fixed legend.

### 3.6 `validate_against_city.py` — cross-validation

Spatial-joins every well to the City's potential polygon it falls in (most
optimistic rating wins where polygons overlap) and cross-tabulates the
WWIS-derived screen against the City's High/Average/Low/None rating, plus
yield/conductivity statistics per class. See §4.

## 4. Results (2026-07-09 build)

**GeoPackage:** 55,903 wells (50,835 with geometry) · 144,719 formation
intervals · 62,324 water strikes · 44,026 pump tests · 125,495 construction
elements.

**Conductivity coverage:** exporting the real code tables + the bucketing
fixes cut unknown-conductivity wells from 14,000 → **9,180**
(medium 37,671 / low 7,351 / high 1,701). Of the remaining unknowns, 7,872
have **no formation record at all** — irreducible from this dataset; the rest
have only non-informative entries ("PREV. DRILLED", "UNKNOWN TYPE", …).

**Surface:** 13,383 cells at 500 m; range 1.40–3.20 W/m·K; 89% of cells
high-confidence. Mostly `medium` 11,174 (Paleozoic limestone/dolostone
plain), `high` 1,107 over Shield granite/gneiss in the west and north-west,
`low` 1,102 (clay/silt-dominated).

**Open-loop screen:** 31,775 viable / 3,602 possible / 15,431 unlikely (wells
with geometry, in-bbox).

**Cross-validation vs the City's Planning/122 layer:**

- 32,807 of 50,808 wells fall **outside** any city polygon — the City layer
  only rates the serviced urban/suburban area, while most water wells are
  rural (that's *why* they have wells). The two products are largely
  complementary in coverage.
- Where they overlap, the well evidence orders the City's classes correctly
  on yield: mean pump-test yield **76 L/min in "High"**, 37 in "Average",
  27 in "Low"/"None".
- Our viable-share is higher in High/Average (38–50%) than Low/None (15–25%),
  as expected. The mismatch direction worth knowing: many wells inside
  "High"/"Average" polygons screen as "unlikely" — usually missing static
  level or no pump test, i.e. our screen is data-limited, not contradicting
  the City.

Full crosstab: `Data/processed/city_validation.csv`.

## 5. Caveats

1. **Conductivity is estimated from lithology words in drillers' logs** using
   literature mid-range values — suitable for screening/prioritisation, not
   for sizing a borefield. A real design needs a thermal conductivity test.
2. **"Unlikely" mostly means "no data"** (no static level / no pump test),
   not proven unsuitability.
3. **WWIS is Ontario-only** — the Gatineau side of the river is blank by
   construction.
4. **Well records are biased rural** — urban cores have few wells (municipal
   water), so urban conductivity cells lean on fewer, older records; check
   the confidence flag.
5. **Feeder capacity is a snapshot** (`last_update` ≈ 2026-05); rerun
   `Hydro.py` before using it for siting decisions.
6. **The City potential layer's criteria are not published in the layer** —
   only the rating; treat agreement/disagreement with our screen accordingly.

## 6. Next steps

1. **Publish the map** on the GitHub Pages site alongside
   `retrofits.html` / `construction.html` (it's one file; needs only a commit
   and a link).
2. **Closed-loop depth economics:** combine depth-to-bedrock + conductivity
   to estimate required borehole metres per kW by cell — turns the map from
   "where is it good" into "what would it cost".
3. **Building footprints / heat demand:** fetch TopographicMapping/3 in tiles
   and join to the conductivity grid for a demand-vs-resource view (the
   original guide's motivation for footprints).
4. **Sewer heat recovery screening:** the trunk-sewer layer + zoning is
   already in the map; adding pipe diameter-based flow estimates would rank
   wastewater heat-recovery sites.
5. **Bedrock geology overlay:** the GSC shapefile sits unused in
   `Data/Raw/GSC/` — rasterising formation polygons would let conductivity
   fall back to mapped geology where wells are sparse (the low-confidence
   cells).
6. **Data refresh cadence:** WWIS updates quarterly; municipal layers change
   rarely. A yearly manual rerun of the chain (§2) is adequate — no
   scheduled job needed.
