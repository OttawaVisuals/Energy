# Ottawa Geothermal Feasibility — Process Documentation

An end-to-end pipeline that turns Ontario's water-well archive and City of
Ottawa open data into an interactive ground-source-heat-pump (GSHP)
feasibility map for Ottawa: estimated ground thermal conductivity, a
drilling-difficulty screening surface, open-loop (groundwater) system
screening, electrical grid capacity, and the municipal siting context
(zoning, sewers, the City's own geothermal potential rating).

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
gpkg wells ───────────────▶ [3] interpolate_conductivity.py ─┐ (share idw.py:
gpkg wells ───────────────▶ [3b] build_difficulty.py ────────┘  500 m IDW grid)
   [3]  └▶ thermal_conductivity_grid.geojson + .tif
   [3b] └▶ difficulty_grid.geojson
conductivity grid + [3b] ─▶ [3c] build_suitability.py
+ wells/capacity/zoning/        └▶ suitability_grid.geojson (3 segment scores +
  sewers/city potential            8 per-cell factors, on the conductivity cells)
everything above ─────────▶ [4] merge_layers.py
+ ottawa_capacity.geojson       └▶ combined_layers.geojson (8 tagged layers)
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
python Geothermal/scripts/build_difficulty.py         # drilling-difficulty grid
python Geothermal/scripts/build_suitability.py        # per-segment suitability scores
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
  A **blank/NaN description** in a code table (e.g. `_code_final_status`'s
  code 0) now decodes to `"Not specified"` instead of falling through to
  `code:NN` — 464 wells recovered. The `_codeWaterUse` table's "Commerical"
  typo is normalized to "Commercial" at decode time (the raw CSV is left
  untouched).
- **`well_use` fallback.** `tblWWR.USE_1ST` is blank for 8,123 wells; where it
  is, `USE_2ND` is decoded and used instead — recovers 36 wells (most of the
  8,123 are blank in *both* columns, i.e. genuinely not recorded, not a
  decoding bug).
- **Geometry recovery.** 5,068 wells have no shapefile geometry. Of those, 67
  have usable coordinates in `tblBore_Hole`'s `ZONE`/`EAST83`/`NORTH83`
  (NAD83 UTM; reprojected EPSG:26917/26918→4326 per-row `ZONE`, dropping the
  dozen rows whose zone is neither 17 nor 18 — stray values 16 and 43 in the
  export). Every well carries `geometry_source` (`shp` | `borehole`); the
  remaining 5,001 wells have no coordinates anywhere in the export and are
  irreducible from this dataset (see §5).
- **Bedrock depth fallback.** `bedrock_depth_m` (from the shapefile's
  `DP_BEDROCK`) is missing for 27,428 wells. Where a well has at least one
  bedrock-bucket formation interval (limestone/dolostone/sandstone/shale/
  granite/gneiss/basalt/"rock"), the shallowest such interval's
  `top_depth_m` fills the gap — recovers 10,885 wells. On the 28,415 wells
  where both values exist, the median absolute difference is **0.02 m**
  (negligible — the two sources agree closely, as expected since both derive
  from the same driller's log). Every well carries `bedrock_depth_source`
  (`shp` | `formations` | none); 16,543 wells remain without a bedrock depth
  from either source.
- **Lithology fallback from mapped geology.** 9,180 wells had no well-log
  lithology (`bedrock_lithology`/`primary_lithology` both null); of those,
  8,444 have usable geometry (the rest are in the irreducible no-geometry
  set). `combine_wells.py` spatial-joins those wells to the GSC national
  bedrock geology (`Data/Raw/GSC/gsc_bedrock_geology.gdb.zip`, layer
  `Wheeler_Bedrock`, read directly from the zip via pyogrio — no manual
  unzip needed) and buckets the match's rock-type attribute:

  | GSC `SUBRXTP` (fallback: `RXTP`) | lithology bucket |
  |---|---|
  | paragneiss | gneiss |
  | marble | limestone |
  | undivided granitoid rocks | granite |
  | syenite, monzodiorite | granite |
  | undivided sedimentary rocks | limestone (St. Lawrence Platform Paleozoic — Ottawa's Paleozoic cover is limestone/dolostone-dominated; the GSC's national layer doesn't distinguish formations at this generalization level) |
  | *(RXTP fallback)* metamorphic rocks | gneiss |
  | *(RXTP fallback)* intrusive rocks | granite |
  | *(RXTP fallback)* sedimentary rocks | limestone |

  Recovers 8,438 of the 8,444 candidates (6 fall outside every mapped
  polygon — edge-of-coverage points). This is **weaker evidence than a well
  log** (a national-scale generalized polygon vs. an actual driller's
  observation at that point) — every well now carries `lithology_source`
  (`well_log` | `gsc_map` | none), and `merge_layers.py` / `build_map.py`
  carry the flag through to the well popup so it's visible, not silently
  blended in. `estimated_conductivity_wm`/`_class` are computed from
  whichever lithology won (well_log first, gsc_map only when well_log is
  absent) — kept consistent with the un-flagged wells.
- **Lithology buckets → thermal conductivity.** Decoded materials map to
  buckets, each with a mid-range conductivity (W/m·K) — **estimates from
  drillers' logs, not measurements**. The per-bucket values, their literature
  min–max ranges and sources now live in
  `Data/conductivity_reference.csv` (loaded via `scripts/conductivity.py`;
  the built-in dict is only a fallback) — see §3.7 "Conductivity assumptions
  & sources" for the table and citations. Defaults: limestone 2.8,
  dolostone 3.0, sandstone 2.3, shale 1.9, granite 3.2, gneiss 3.0, clay 1.4,
  silt 1.5, sand 2.4, gravel 2.0, till 1.8, fill 1.5, basalt 2.0, generic
  "ROCK" 2.5. Metamorphics fold in (marble→limestone, schist→gneiss,
  quartzite/quartz/chert→granite), sediments likewise (marl→clay,
  conglomerate/greywacke→sandstone, quicksand→sand, overburden→till).
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
Per-well conductivity comes from `Data/conductivity_reference.csv` via
`conductivity.py` (the built-in dict is only a fallback). Outputs both a
GeoJSON polygon grid (what the map uses) and a GeoTIFF (EPSG:32618,
NaN = no coverage).

**Per-cell bucket weight shares (Phase B).** Because IDW is *linear* in the
per-well values and each well's value is just its lithology bucket's
conductivity, every cell's interpolated value can be written exactly as
`κ_cell = Σ_bucket share_bucket × κ_bucket`, where `share_bucket` is the sum of
that cell's **normalised** IDW weights over the neighbour wells in that bucket
(shares sum to 1). The script emits these shares per cell (`bucket_shares`
column: sparse `[[bucket_idx, share], …]`, indices per
`conductivity.BUCKET_ORDER`), quantised to 3 decimals with shares < 0.001
dropped and renormalised. It verifies the reconstruction against the exact
surface (max error **0.0034 W/m·K** < 0.01 in the current build; avg 2.6
buckets/cell) before writing. This is what lets the map recompute the whole
surface **exactly and instantly** when a user edits a bucket's conductivity —
no server, no re-interpolation (see §3.5, §3.7).

### 3.4 `merge_layers.py` — one FeatureCollection

Concatenates all eight layers into `combined_layers.geojson`, every feature
tagged with a `layer` property (`conductivity_grid`, `difficulty_grid`,
`suitability_grid`, `wells`, `grid_capacity`, `zoning_industrial`,
`sewer_lines`, `city_open_loop_potential`). Wells are
slimmed to popup fields; capacity polygons simplified ~10 m; coordinates
rounded to 5 decimals. Step-5 layers are skipped gracefully if not fetched.

### 3.5 `build_map.py` + `map_template.html` — the map

Generates `output/index.html`: a single self-contained Leaflet page (only the
CDN Leaflet library and OSM basemap tiles need internet). Size is kept down
by embedding the two big layers as compact arrays instead of GeoJSON —
grid cells as `[w,s,e,n,high_confidence,shares]` (shares = sparse
`[[bucket_idx,share],…]`; the cell conductivity is recomputed in-browser as
`Σ share×κ`), wells as flat tuples carrying a `bucket_idx` (0–13 per
`BUCKET_ORDER`, −1 = unknown) instead of a raw conductivity — and by
embedding only the **trunk** sewer network (sanitary `FUNCTION <> LOCAL` +
all combined; local laterals stay in the processed GeoJSON). Everything
renders on canvas (`preferCanvas`), so ~51k well points stay responsive.
Eight toggleable layers, popups on every feature, fixed legend, a
**suitability segment selector** (top-left radio buttons — §3.9) restyling the
one suitability layer, and the **Conductivity assumptions** panel (§3.7).
Current size **7.9 MB** (≤ 8 MB budget). `build_map.py` also embeds the
reference table (`CONDREF`) and
`BUCKET_ORDER` (`BUCKETS`) for the panel. The **drilling-difficulty grid**
(§3.8) is embedded as compact `[w,s,e,n,high_confidence,score,overburden_pts,
problem_pts,hardness_pts,artesian_pts]` tuples — static per-cell values (no
client-side recompute); the class and dominant driver are derived in-browser.
The **per-segment suitability grid** (§3.9) is embedded as a parallel `SUIT`
array — one `[drill,openloop,yield,feeder,zone,sewer,demand]` tuple of 0–100
factor values per cell, **index-aligned with `GRID`** (the suitability cells are
the conductivity cells, same order; `build_map.py` asserts equal length). The
eighth factor, conductivity, is *not* stored — it is recomputed live from the
cell's bucket shares, so the three segment composites (weights in
`map_template.html`'s `SEGMENTS`, mirroring `build_suitability.py`) respond to
conductivity-panel edits. Coordinate precision on the (already ~10 m-simplified)
capacity / zoning / potential polygons was trimmed from 5 → 4 dp to hold the file
within the 8 MB budget with `SUIT` added (no visible change on a 500 m map).

**Conductivity assumptions panel.** A collapsible bottom-right panel lists all
14 buckets, each with an editable numeric input clamped to its literature
`[min, max]`, the default value + range, and a hover tooltip citing the
source. Editing a value recomputes every grid cell exactly
(`Σ share×κ`), restyles the canvas choropleth (with a **forced synchronous
redraw** — this preview environment doesn't fire `requestAnimationFrame`),
refreshes the legend's live per-class cell counts, and updates each well's
popup conductivity (recomputed from its bucket when the popup opens).
A **Reset all** button restores the VDI 4640 defaults. **Well marker colours
encode open-loop feasibility, not conductivity**, so they deliberately stay
fixed when κ is edited (changing them would conflate two independent
variables on one symbol); only the conductivity choropleth and the popups'
conductivity fields respond to edits.

### 3.6 `validate_against_city.py` — cross-validation

Spatial-joins every well to the City's potential polygon it falls in (most
optimistic rating wins where polygons overlap) and cross-tabulates the
WWIS-derived screen against the City's High/Average/Low/None rating, plus
yield/conductivity statistics per class. See §4.

### 3.7 Conductivity assumptions & sources

The per-bucket conductivities are the biggest single assumption in the map, so
they are pulled out into a versioned, literature-sourced table —
`Data/conductivity_reference.csv` — read by `combine_wells.py`,
`interpolate_conductivity.py` and `build_map.py` through the shared
`scripts/conductivity.py` loader (the hard-coded dict is only a fallback if the
CSV is missing). Each row carries a `default_wmk`, a literature `min_wmk` /
`max_wmk` (which also clamp the map's editable inputs), a `notes` field, and a
`source` field.

**Primary source: VDI 4640 Blatt 1:2010** *"Thermal use of the underground —
Fundamentals"*, the standard GSHP design reference. Its recommended /
minimum / maximum thermal-conductivity table is reproduced with exact figures
in Busby (2011), *Provision of thermal properties data for ground collector
loop design*, British Geological Survey (Cambridge GSHP seminar) — used here as
the transcription. Corroborating sources: **ASHRAE** — Kavanaugh & Rafferty
(2014), *Geothermal Heating and Cooling* (Tables 3.3 soils / 3.4 rocks) — and
**Banks (2012)**, *An Introduction to Thermogeology*, 2nd ed.

| bucket | default | range | notes |
|---|---|---|---|
| limestone | 2.8 | 2.5–4.0 | VDI recommended 2.8; low porosity, weak dry/sat effect |
| dolostone | 3.0 | 2.8–4.3 | VDI 'dolomite' rec 3.2; default 3.0 within range |
| sandstone | 2.3 | 1.3–5.1 | VDI rec 2.3; wide range with quartz content/cementation |
| shale | 1.9 | 1.1–3.5 | VDI 'claystone/siltstone' rec 2.2; fissile mudrock |
| granite | 3.2 | 2.1–4.1 | VDI rec 3.4; crystalline, negligible dry/sat effect |
| gneiss | 3.0 | 1.9–4.0 | VDI rec 2.9; anisotropic (foliation) |
| clay | 1.4 | 0.9–2.3 | VDI clay/silt **saturated** rec 1.7; **dry 0.4–1.0** |
| silt | 1.5 | 0.9–2.3 | same VDI clay/silt category; dry as low as 0.4 |
| sand | 2.4 | 1.5–4.0 | VDI sand **saturated** rec 2.4; **dry only 0.3–0.8** |
| gravel | 2.0 | 1.6–2.0 | VDI gravel **saturated** rec 1.8; **dry ~0.4** |
| till | 1.8 | 1.1–2.9 | glacial till/moraine (saturated); VDI rec 2.0 |
| fill | 1.5 | 0.5–2.0 | made-ground, **no standard category** — screening placeholder |
| basalt | 2.0 | 1.3–2.3 | VDI rec 1.7; default 2.0 = denser/less-vesicular end |
| rock | 2.5 | 1.9–3.5 | generic undifferentiated bedrock — screening placeholder |

**Saturated vs. dry.** For the soil buckets (clay, silt, sand, gravel, till,
fill) conductivity depends strongly on water content — dry values are far lower
than saturated (sand is the extreme: ~0.4 dry vs 2.4 saturated). Ottawa's wells
sit below the water table, so the **saturated** value is used as the default and
the quoted range is the saturated range; the `notes` column records the dry
sensitivity. One default per bucket is kept (the map lets a user override it).

**Default validation.** A cross-check confirmed **all 14 current defaults fall
within their VDI 4640 (2010) ranges** — none sat outside the literature and none
needed changing (the original hand-picked GSHP mid-ranges were already
literature-consistent). `fill` and `rock` are the two buckets with no direct
GSHP-literature category; their ranges are documented screening placeholders
bracketed by the VDI unconsolidated-soil / bedrock ranges rather than a single
cited value.

**Client-side sensitivity.** Because these values enter the interpolation
linearly, the map ships each cell's per-bucket IDW weight shares (§3.3) and
recomputes the surface exactly when a value is edited — the "Conductivity
assumptions" panel (§3.5). This turns the map's biggest assumption into
something a user can interrogate live (e.g. "what if Shield granite is really
2.6, not 3.2?").

### 3.8 `build_difficulty.py` — drilling-difficulty screening layer

A per-well **drilling-difficulty** score for vertical closed-loop GSHP
boreholes, gridded onto the same 500 m surface as conductivity (both scripts
share the IDW grid + weighting via `scripts/idw.py` — 500 m, k=12, power 2,
2 km coverage cutoff, so the two grids line up cell-for-cell). It ranks where a
borehole is likely cheaper vs. harder to drill from what the WWIS logs record —
a **screening heuristic, not a drilling quote** (caveat §5).

**Four components, each scaled to 0–1 and weighted (points sum to 100):**

| component | weight | factor (0→1) | rationale |
|---|---:|---|---|
| Overburden thickness | 40 | `bedrock_depth_m / 30`, capped at 1 | Unconsolidated overburden must be cased through to reach stable bedrock; deeper overburden = more casing = the dominant cost driver. 0 pts at bedrock-at-surface, full 40 at ≥ 30 m. Uses the shapefile `DP_BEDROCK` with Phase A's formations fallback (§3.1). |
| Problem overburden layers | 20 | `n_problem_intervals / 2`, capped at 1 | Count of formation intervals whose **primary** material is boulders / stones / quicksand / hardpan (7,395 wells) — casing-advance & lost-circulation risk. One such layer = 10 pts, ≥ 2 = full 20. Primary material only: "stoney" as a secondary modifier of a clay/till layer is far more common and far less of a problem. |
| Rock hardness | 25 | `HARDNESS[lithology]` | Granite/gneiss = 1.0 (slow penetration, bit wear), basalt 0.7, generic "rock" 0.5, limestone/dolostone 0.4 (carbonate baseline), sandstone 0.25, shale 0.15 (easiest). Overburden-only & unknown lithologies default to the limestone baseline (0.4) — under Ottawa's clay plain a borehole reaches the Paleozoic platform, so "no bedrock logged" is not "soft". |
| Artesian risk | 15 | `local_flowing_share / 0.10`, capped at 1 | Flowing-artesian conditions complicate grouting/completion. Only 503 wells have a flowing pump test (`flowing_rate_lpm > 0`), so it's treated as a **neighbourhood indicator** — the share of wells within 1 km that flow — not a per-well flag; full 15 pts where ≥ 10 % of nearby wells flow. |

`difficulty_score = Σ points` (0–100), **rounded to the nearest 5** (the inputs
don't justify finer precision), with a 3-class label: **easy** < 25, **moderate**
25–44, **difficult** ≥ 45 (thresholds tuned to the score distribution — see §4).
Only wells with a **known depth-to-bedrock** are scored (overburden is the
dominant driver and is not imputed). Each component is gridded separately with
the shared IDW, so every cell carries the full breakdown for its popup and its
**dominant driver** is the largest of the four gridded contributions.

**Validation (printed before gridding, all three checks pass):**

- **(a) Class × decoded construction method.** Isolating the rock-hardness
  signal, **granite/gneiss wells skew hard to air methods** — Air Percussion
  50.9 % + Rotary (Air) 19.2 % ≈ 70 %, vs 24 % Cable Tool — exactly as expected
  (air/rotary for hard rock, cable-tool for soft/overburden). The *composite*
  "difficult" class is overburden-weighted, so it also captures deep clay-plain
  wells (drilled by cable tool: overburden-only wells are 59 % cable-tool),
  which is why the raw composite crosstab shows cable-tool *rising* into the
  "difficult" class — two genuine difficulty regimes, not a bug. Diamond coring
  rises monotonically easy→difficult (4.6 %→11.8 %) either way.
- **(b) Score × total depth.** Weak positive (Pearson ≈ 0.10, Spearman ≈ 0.12);
  each component alone correlates ≈ 0.15 with depth. Total well depth is set
  mainly by where adequate yield is found (hydrogeology), not by drilling
  difficulty — a deep, easy limestone well is common (median depth 38.7 m for
  deep-overburden wells vs 31.1 m for shallow). Direction is as expected;
  difficulty is deliberately *not* a depth proxy.
- **(c) Spatial pattern.** Textbook: the **east clay plain is overburden-driven**
  (mean overburden 14.2 pts vs hardness 9.1) and the **west Shield edge is
  hardness-driven** (hardness 12.0 vs overburden 7.9).

### 3.9 `build_suitability.py` — per-segment suitability scores

The other layers answer "what is the ground like here?"; this one answers "how
well does *this kind of project* fit here?" A single feasibility reading is
misleading because the three GSHP market segments trade off depth, land, load
balancing, groundwater yield and grid draw completely differently. So the script
produces **three 0–100 suitability scores per cell** on the existing 500 m
conductivity grid (the canonical cells — it reads them in file order and emits in
the same order, so every layer lines up):

- **Residential & small commercial (~1–10 tons, 1–3 boreholes ~100–200 m).**
  A house needs little borehole metreage, so **drilling difficulty / thin
  overburden dominate the cost** and conductivity matters only moderately; a
  neighbourhood open-loop (groundwater) option is a real bonus for small loads;
  the electrical feeder is irrelevant (a heat pump is a small residential load).
- **Large buildings (50+ tons, borefields).** Borehole metres scale roughly with
  **1/λ**, so **conductivity weighs heaviest**; Ottawa's heating-dominant loads
  risk long-term ground thermal depletion, worst in low-conductivity clay — the
  heavy conductivity weight *penalises* those cells (a clay cell scores near-zero
  on the factor that carries 45 % of the weight). A large electrical service
  means **feeder headroom matters**, and industrial/employment zoning is a
  land-availability bonus for the borefield.
- **District energy.** Needs **demand density _and_ a big resource**: a
  high-yield aquifer (open-loop / standing-column at scale), trunk-sewer
  proximity (wastewater heat recovery), feeder headroom, and land.

Each score is a weighted sum of **factors normalised to 0–1** (documented
transforms below). Because the conductivity factor derives from the Phase B
per-cell bucket weight-shares (§3.3) and IDW is linear, the composites recompute
**exactly** in the browser when a user edits a bucket's conductivity — so the
script emits per-cell *factor* values and the **map computes the composites in
JS** from the published weight table, the conductivity factor recomputed live.

**Factors (0–1) and their transforms** (constants in `build_suitability.py`):

| factor | transform (→ 0–1) | source / notes |
|---|---|---|
| `cond` | `(κ_cell − 1.2)/(3.2 − 1.2)` | conductivity surface (§3.3); **recomputed live** from bucket shares + edited κ. Higher λ → fewer borehole metres. |
| `drill` | `1 − difficulty_score/100` | Phase C drilling difficulty (§3.8), joined to each cell by point-in-cell (nearest ≤ 750 m fallback; grid-median for the 252 cells with no difficulty cell). |
| `openloop` | `viable_share / 0.5` | share of wells within 1.5 km screening open-loop **viable** (static level + yield ≥ 15 L/min) — a modest-yield groundwater option. |
| `yield` | `p75(well_yield) / 100 L·min⁻¹` | 75th-percentile nearby well/pump-test yield — a *big* groundwater resource for district scale. |
| `feeder` | `capacity_mva / 5` | Hydro Ottawa feeder available capacity at the cell (GridCapacity / OEB CCIM), 0 where outside the serviced feeders. |
| `zone` | `1` in industrial/employment zoning else `0` | land-availability proxy (City Zoning IL/IG/IH/IP/RG/RH). |
| `sewer` | `1 − dist_to_trunk_sewer / 1000 m` | proximity to a trunk/combined sewer (heat-recovery option). |
| `demand` | `1` in the City's serviced urban area else `0` | **coarse demand-density proxy** (City Planning/122 potential polygons, which cover exactly the serviced urban/suburban area). **Upgrade hook:** if `Data/processed/heat_demand_grid.geojson` (ROADMAP item 7) exists, the script uses per-cell modelled kWh/yr instead. |

**Segment weight table** (sums to 1 per segment; mirrored in `map_template.html`):

| segment | cond | drill | openloop | yield | feeder | zone | sewer | demand |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| **Residential / small commercial** | 0.30 | **0.55** | 0.15 | — | — | — | — | — |
| **Large buildings (borefields)** | **0.45** | 0.25 | — | — | 0.20 | 0.10 | — | — |
| **District energy** | — | — | — | 0.20 | 0.15 | 0.10 | 0.20 | **0.35** |

The weights are screening judgements grounded in GSHP sizing practice (CSA C448 /
IGSHPA borehole-metre-per-load conventions — borefield length ∝ load and ∝ 1/λ,
which is why conductivity dominates the large-building weight and barely enters
the residential one) and district-energy siting literature (demand density +
recoverable-resource proximity). They are **not** calibrated against installed
system costs — this is a *screening* ranking, not an engineering feasibility study
(caveat §5). Each cell carries all eight factor values so the map popup can show
the active segment's full breakdown.

**Sanity checks (printed before writing, all pass):**

- **(1) Inter-segment correlations** — residential↔large **+0.56**,
  residential↔district **−0.18**, large↔district **+0.32**. None approaches the
  ">0.95 = redundant weights" line, so the three scores genuinely say different
  things (residential and district are even mildly *anti*-correlated — easy rural
  drilling vs dense serviced urban).
- **(2) District-energy top decile** (score ≥ 60) — **100 %** sit in the serviced
  urban area (vs 18 % of all cells), with mean sewer-proximity factor 0.63 (vs
  0.09) and feeder-headroom 0.65 (vs 0.13): exactly the "dense + big-resource +
  grid-headroom" cells district energy needs.
- **(3) Residential top decile** (score ≥ 86) — **does not concentrate downtown**
  (0 % in the downtown core box, which is 2.1 % of cells; only 5 % in the
  serviced urban area vs 18 % baseline) and has above-baseline drilling ease
  (0.88 vs 0.74): thin-overburden, easier-drilling suburban/rural cells, as
  expected for small closed-loop systems.

### 3.10 `build_building_stock.py` — canonical building stock (Heat Demand Phase 1)

Companion pipeline for [HEATDEMAND_PLAN.md](../HEATDEMAND_PLAN.md) §3–4 — a
per-building layer feeding future heat-demand/electrification work, kept
alongside the geothermal-suitability pipeline because it reuses the same
500 m grid, feeder polygons, and Ottawa bbox conventions. Phase 0's scouting
memo is [`Data/heatdemand_source_notes.md`](Data/heatdemand_source_notes.md)
— read that first for source verdicts; this section documents what Phase 1
(`build_building_stock.py`) actually built from those verdicts.

**Output:** `Data/processed/buildings_ottawa.parquet` (+ `.gpkg` for QGIS),
one row per building, columns `bldg_id, footprint_m2, height_m, storeys,
height_source, class, vintage, grid_cell_id, feeder_id, da_id, fsa, geometry`
(WGS84). **414,111 rows** after the `footprint_m2 > 40` filter (from
467,379 Canada-Structures features in the Ottawa bbox — 88.6% kept). This is
a *screening* layer: vintage and the ambiguous-type class split are
probabilistic per building (meaningful in aggregate, not for a single
address — see the vintage sub-section below).

**Footprint + height + type backbone.** Canada Structures' Ontario gpkg
(`Data/Raw/CanadaStructures/on_structures_en.gpkg`) is the sole footprint
source, exactly as Phase 0 recommended — bbox-clipped in its native Lambert
CRS (transformed via the embedded WKT, not an EPSG lookup) rather than
loaded whole. `Area` is used directly as `footprint_m2` (it's already in m²
in that projected CRS; spot-checked against geometry-computed area, matches
to a few m²). `Height` (nonzero/non-null) is the primary height value.
Where it's null/zero, height is backfilled from the NRCan Ottawa-Gatineau
LiDAR tile (`Data/Raw/NRCanBuildings/...`, `heightmax`) by nearest-centroid
join (≤15 m). Because the backfill only ever fills in a value for a building
that already exists in the Ontario-only Canada Structures backbone, this
implicitly keeps the whole output Ontario-side — no separate Ottawa River
boundary clip of the NRCan tile was needed (Phase 0 had flagged the river
isn't straight; sidestepped rather than solved). Result: **84.1% height from
Canada Structures, 1.4% from NRCan backfill, 14.5% still needed the
type-based storeys default** (lower than Phase 0's raw 85%/100% coverage
figures on the two sources individually — the NRCan backfill's 15 m
match radius and centroid-only join miss some buildings Phase 0's raw
per-file numbers implied would be recoverable; a wider match radius or
polygon-overlap join would likely improve this, left as a documented
opportunity, not pursued further here since 14.5% relying on the type
default is an acceptable screening-layer error rate).

**Storeys / defaults.** Where height is known, `storeys = max(1,
round(height_m / 3.0))` (3 m per storey). Where it's still missing after
both sources, storeys default **by class** (`STOREY_DEFAULT` in the script):
detached/row 2, lowrise_murb 4, highrise_murb 10, commercial 1,
institutional 2, industrial 1 — and `height_m` is back-filled from that
default (`height_source = 'default_by_type'`) so every row has a usable
height. The visible spike at storeys = 10 in the histogram is this default
firing for highrise MURBs with no height evidence, not a real cluster of
identical towers — documented so a future reader doesn't misread it.

**Classification (`class`).** Priority order, per building:
1. **Canada Structures `OSM_Type` direct map** — unambiguous tags resolve
   immediately: `detached/house/bungalow/static_caravan/cabin → detached`;
   `semidetached_house/semi/terrace → row`; a `commercial` set (retail,
   office, hotel, warehouse, bank, restaurant, kiosk, storage_tank,
   service); an `industrial` set (industrial, barn, farm(_auxiliary),
   stable, cowshed, silo, greenhouse, riding_hall, hangar); an
   `institutional` set (school/university/college/kindergarten, civic,
   public, fire_station, hospital, train_station, transportation, the
   various places of worship, embassy, military, stadium/grandstand/
   sports_centre, toilets, bunker, portable_classroom). Accessory/unclear
   tags (garage, shed, roof, ruins, hut, canopy, carport, boathouse,
   parking, `residential`, or no tag at all) carry no usable signal and
   fall through exactly like a missing `OSM_Type`.
2. **MURB tier tiebreak** for `apartments`/`Condominiums`/`dormitory`:
   height ≥ 15 m → `highrise_murb`; 9–15 m → `lowrise_murb`; below that (no
   height evidence) → probabilistic draw between the two, weighted by the
   building's DA's `apt_low_rise` vs `apt_high_rise` dwelling counts
   (city-wide 70/30 fallback if the DA has no apartment dwellings on
   record).
3. **Full zoning fallback** for everything still unresolved: the City's
   full `Zoning/MapServer/3` layer (`Data/Raw/zoning_full.geojson`,
   `fetch_zoning_full.py`, no `ZONE_MAIN` filter this time — 14,089
   polygons, 41 distinct `ZONE_MAIN` codes) is joined by building-centroid
   point-in-polygon (82.8% match rate; unzoned/rural gaps fall through to
   the residential path below). Mapping, after inspecting every code's
   `ZNAME_EN`:
   - **industrial**: `IL, IG, IH, IP, RG, RH` (kept identical to
     `fetch_municipal_layers.py`'s existing industrial filter for
     consistency with the rest of the geothermal pipeline) plus
     `ME, MR` (mineral extraction) and `T1, T2` (transportation), the
     latter two flagged low-confidence — real buildings on
     transportation-zoned land are rare and usually accessory.
   - **institutional**: `I1, I2` (Institutional Zones), `RI` (Rural
     Institutional), `L1, L2, L3` (Community Leisure Facility — folded in
     as public recreation buildings).
   - **commercial**: `AM, GM, LC, MC, MD, TD, TM, VM` (the Mainstreet /
     Mixed-Use-Commercial family) and `RC` (Rural Commercial).
   - **residential** (routes to step 4 below): `R1–R5, RR, RU, V1–V3, RM`.
   - **no signal** (routes to step 4 below, same as unzoned):
     `AG` (Agricultural), `DR` (Development Reserve), `EP`
     (Environmental), `O1` (Open Space), `*_`. Agricultural-zoned parcels
     commonly carry a farmhouse, so treating `AG` as "no signal" rather
     than forcing it non-residential was a deliberate choice — an
     agricultural zoning code alone doesn't mean "no building," it means
     "zoning doesn't tell us the building's use."
4. **Residential probabilistic tiebreak** (zoning residential, or no
   zoning/OSM signal at all): height ≥ 15 m / 9–15 m still short-circuit to
   highrise/lowrise MURB directly (deterministic — real height evidence
   beats the census-mix guess). Otherwise, a categorical draw over
   `{detached, row, lowrise_murb, highrise_murb}` weighted by the
   building's DA dwelling-type mix from `da_census.json`: `detached ←
   single_detached`; `row ← semi_detached + row_house +
   other_single_attached + movable` (semi-detached shares a party wall
   like a row house, so it's folded in rather than kept separate — the
   `class` enum has no `semi` bucket); `lowrise_murb ← duplex_apt +
   apt_low_rise`; `highrise_murb ← apt_high_rise`. If the footprint is
   large (> 250 m²) with no height evidence, the two MURB weights are
   tripled before renormalising (a big footprint with no height data is
   more likely a low apartment block than a mansion). DAs with no
   dwelling-type record (or buildings whose DA join failed — 18.8% of
   buildings; rural/edge-of-bbox areas without a DA/zoning match) fall
   back to Ottawa-wide dwelling-type shares.

**Vintage (`vintage`, 8 bands, same as `Python/extract_fsa_census.py`'s
period-of-construction bands).** Assigned **probabilistically per building**
by a categorical draw from its DA's period-of-construction mix
(`da_census.json`), falling back to the Ottawa-wide mix where the DA join
failed or the DA's record is empty/suppressed. Fixed seed `20260716`
(`np.random.default_rng`, one draw per building, in building order) —
rerunning the script reproduces the exact same vintage assignment.
**Method inspiration** (conceptual only, no code copied — AGPL,
per HEATDEMAND_PLAN.md's instruction): `canmet-energy/
community-energy-orchestrator` assigns each of its 139 remote communities'
required housing stock (dwelling counts by type × 3 construction eras, from
inter-census dwelling-count deltas) to representative EnerGuide archetype
files, duplicating archetypes at random with a fixed seed when a community
needs more homes of a type than the archetype library has. This building
stock's vintage draw borrows the same shape of idea — go from a census-
derived categorical distribution to a per-unit assignment via a seeded
random draw rather than a deterministic rule — scaled down from
community-level dwelling requirements to per-building draws from a much
finer (DA-level, 8-band) distribution, since Ottawa has real building
footprints to assign vintages *to*, unlike the orchestrator's synthetic
per-community housing lists.

**Joins:**
- **`grid_cell_id`** — point-in-polygon against the *existing*
  `Data/processed/thermal_conductivity_grid.geojson` polygons (not a
  rebuilt grid — the conductivity/difficulty/suitability grid is masked to
  cells within 2 km of a well, per `idw.py`'s `MASK_DIST_M`, so it isn't a
  complete regular lattice over the city). That file carries no native cell
  ID, so this script assigns a stable synthetic ID (`"cell_" + row-index-
  in-file`) rather than inventing new grid geometry — spatially consistent
  with every other geothermal layer, just newly labelled. **84.0%** of
  buildings fall inside a grid cell; the rest sit outside the well-coverage
  mask (expected, not a bug — those areas have no conductivity estimate
  either).
- **`feeder_id`** — point-in-polygon against `GridCapacity/
  ottawa_capacity.geojson`'s `objectid`. **66.0%** match — Hydro Ottawa's
  3,884 feeder polygons don't tile the full bbox (same caveat the
  suitability layer already documents: CCIM coverage is a connection-
  screening product, not exhaustive).
- **`da_id`** — point-in-polygon against `Data/processed/
  da_boundaries_ottawa.geojson` (StatCan 2021 DA cartographic boundary
  file, national `lda_000b21a_e.zip`, filtered to `DAUID LIKE '3506%'`
  — Ottawa's census-division code — 1,392 DAs). **81.2%** match; the rest
  are buildings near the bbox edge that fall outside Ottawa's CD (the bbox
  is a rectangle bigger than the city, consistent with the rest of the
  pipeline).
- **`fsa`** — point-in-polygon against `FSA_Maps/ON.geojson`. **99.8%**
  match.

**New fetches this phase** (raw pulls cached under `Data/Raw/` /
`Geothermal/Data/Raw/StatCanDA/` per convention):
- `fetch_zoning_full.py` → `Data/Raw/zoning_full.geojson` (14,089 features,
  35.9 MB) — same paginated-ArcGIS pattern as `fetch_municipal_layers.py`,
  `where="1=1"` instead of the industrial-only filter.
- `fetch_da_census.py` → `Data/processed/da_census.json` (1,392 Ottawa DAs,
  493 KB) — DA-level 2021 Census Profile. No CD/CSD-scoped bulk CSV exists
  (confirmed by testing `GK=CSD&GC=3506008` query params against the
  download endpoint — ignored, same file returned every time); the fetched
  zip (`98-401-X2021006_eng_CSV.zip`, 2.25 GB) turned out to already be
  split **by StatCan region** (Ontario alone is an 8.78 GB CSV) and, more
  usefully, ships a `..._Geo_starting_row_Ontario.CSV` index (Geo Code,
  Geo Name, starting line number) — used to jump straight to Ottawa's 1,392
  DA blocks (rows ~1,070,819–4,733,170) and stop reading there, instead of
  streaming the full 8.78 GB Ontario file to the end. Same
  `CHARACTERISTIC_ID` map as `extract_fsa_census.py` (period-of-construction
  1441–1448, dwelling-type 42–49) — StatCan keeps characteristic IDs
  consistent across geography levels within the 98-401-X2021 product
  family, as HEATDEMAND_PLAN.md's brief predicted.
- DA boundary geometries: StatCan's national 2021 DA Digital Boundary File
  (`lda_000b21a_e.zip`, 198 MB), filtered to Ottawa's CD and reprojected —
  no separate script, done inline in this session and cached at
  `Data/Raw/StatCanDA/lda_000b21a_e/`.
- No WAF/Referer quirks were hit this phase — both `www12.statcan.gc.ca`
  bulk-download endpoints (Census Profile CSV and the DA boundary file)
  worked with a plain `curl -L`, unlike Phase 0's `open.canada.ca` Canada
  Structures download.

**Validation** (printed by the script; see also GEOTHERMAL_STATUS.md for
the dated entry):
- **detached buildings vs census detached dwellings**: 258,013 vs 269,020
  (**−4.1%**) — well within the ±15% target; detached houses are ~1:1
  building:dwelling, so this is the cleanest check.
- **row/semi buildings vs census semi+row dwellings**: 99,054 vs 118,770
  (**−16.6%**) — just outside the ±15% target. Investigated: the OSM
  `house`/`detached` tags almost certainly catch some real semi-detached
  and duplex units that Canada Structures' `OSM_Type` doesn't distinguish
  from a standalone house (there's no reliable geometric signal —a party
  wall between two footprints digitised as separate polygons looks
  identical to two nearby detached houses without parcel data), pulling
  count from `row` into `detached` (whose own delta, −4.1%, is
  correspondingly *less* negative than it would be otherwise). Not
  corrected here — flagged as a known building:dwelling attribution
  softness at the detached/row boundary rather than silently forced to fit,
  per the brief's instruction to investigate rather than ship a bad number
  quietly.
- **apartment buildings vs census apartment dwellings**: 35,580 buildings
  vs 140,690 dwellings — **not** a ±15% check (a MURB is one building with
  many units; the plan's ±15% target only makes sense for the ~1:1
  detached/row comparison, so this ratio — ~4.0 dwellings per MURB
  building — is reported for context, not validated against a target).
- **Storeys**: mean 2.29, median 2 (25th/75th percentile both 2) — the
  overwhelming majority of Ottawa's building stock is 1–3 storeys, with a
  visible downtown-highrise tail out to 35 storeys, matching the known
  shape of the city's stock. The storeys = 10 spike is the highrise-MURB
  default firing (see above), not a real cluster.
- **Height source**: 84.1% Canada Structures, 1.4% NRCan LiDAR backfill,
  14.5% defaulted by type.

**Deviations from the brief / open risks that mattered:**
- Phase 0's "City LOD1 3D buildings" stretch goal (per-neighbourhood
  MultiPatch GDBs) was **not** attempted — the NRCan LiDAR + Canada
  Structures combination already gets height coverage to 85.5%, and the
  116-file MultiPatch linearization effort documented as a stretch goal in
  `heatdemand_source_notes.md` §4 was judged not worth it for a screening
  layer's remaining 14.5% (all covered by the documented type default
  instead).
- The NRCan backfill only recovered 1.4 percentage points of the 14.6%
  gap Canada Structures' `Height` left open (upper bound was 100% per
  Phase 0's scouting numbers) — the nearest-centroid join with a 15 m
  cutoff is conservative; a polygon-overlap join would likely close more
  of the gap, left as a follow-up rather than reworked mid-Phase-1.
- `da_id`/`grid_cell_id`/`feeder_id` coverage sits at 81–85% (not
  near-100%) because none of those three source layers tile the entire
  Ottawa bbox (DA boundaries stop at the CD line; the conductivity grid is
  well-coverage-masked; feeder polygons are a connection-screening
  product, not universal coverage) — expected given how each layer was
  built, not a join bug; downstream Phase 4 aggregation will need to treat
  buildings with a null `grid_cell_id`/`feeder_id` as "off-grid for this
  layer" rather than dropping them.

#### 3.10.1 Stock reconciliation (Heat Demand Phase 2.5)

The Phase 2 validation surfaced a **stock-count over-attribution**: the raw
Phase 1 stock implied **808k residential dwellings vs the 427,113 census
households** in the 2021 census (1.89×), so every city-wide heat sum ran
~+36% high even though the per-*unit* intensities matched CEUD to <1%.
`build_building_stock.py`'s `reconcile_stock()` fixes the **stock**, not the
intensities. Diagnosis first (printed by the script as a class × `assign_path`
× inside/outside-CD decomposition), then three documented, seeded levers:

**Diagnosis — what carried the excess.** Implied dwellings (detached/row = 1,
MURB = `round(gross floor area / 106.7 m²)`, non-res/accessory = 0), broken
down:
- **The bbox extends well beyond the city (dominant).** The Ottawa analysis
  bbox is a rectangle larger than the City of Ottawa census division (CD); it
  catches ~19% of buildings in surrounding townships. Those buildings carried
  **~353k of the 808k implied dwellings** — nearly half the total — yet the
  census households they were being compared against are **city-only**. This
  was an apples-to-oranges geography mismatch more than a modelling error.
- **MURB no-height unit inflation (secondary).** A building with no height at
  classification time could be drawn probabilistically as `highrise_murb` and
  then given the 10-storey `STOREY_DEFAULT`, multiplying its floor area and
  (downstream) its unit estimate with zero evidence. This produced ~200k
  bbox-wide implied units from default-height "highrises".
- **Accessory structures (minor).** Only ~1.5% of `detached` have a footprint
  ≤ 50 m²; the genuinely-accessory garages/sheds are a small carrier, living
  in the unsignalled `residential_draw` pool, not the main story.

**Fix — three levers (all in `reconcile_stock()`, run after class assignment):**
1. **`in_ottawa_cd` flag.** `True` iff the building centroid fell in one of the
   1,392 Ottawa-CD dissemination areas (`da_id` not null; the DA boundaries
   tile the CD exactly). **Every city-wide sum is taken over `in_ottawa_cd`
   only** — this is the dominant correction and it is just correct geography.
2. **Rule R1 — a highrise MURB requires real height evidence.** In the
   probabilistic residential draw and the ambiguous-`apartments` path, a
   building with no `Height` (Canada Structures / NRCan) can be drawn as
   detached/row/**lowrise**, never highrise. This removed the default-10-storey
   inflation at its root (bbox `highrise_murb` fell 16,691 → 1,074; the
   remaining highrises are height-evidenced). `assign_path` records provenance
   (`osm_direct`, `osm_murb_height`, `osm_murb_nohgt_lowrise`, `zoning_nonres`,
   `height_highrise/lowrise`, `residential_draw`, `reconcile_accessory`).
3. **Per-DA implied-dwelling cap → `accessory`.** Within each Ottawa DA, the
   modelled implied dwellings may exceed the DA's 2021 census `total_dwellings`
   by at most `DA_IMPLIED_TOLERANCE = 0.15`. The excess is reclassified to a new
   non-dwelling **`accessory`** class, taking the **smallest-footprint buildings
   first and only from the unsignalled `residential_draw` path** — the probable
   garages/sheds/secondary structures. OSM-tagged and height-evidenced buildings
   are **never** reclassified, so real dwellings are preserved; DAs that remain
   over cap after exhausting their soft pool (121 DAs, all real OSM/height stock)
   are left honestly over rather than force-fit. This reassigned **17,791
   buildings across 247 DAs**. `GROSS_M2_PER_UNIT = 106.7` and the seed match
   Phase 2, so the whole step is reproducible.

**Result (validated by re-running `build_building_demand.py`, city sums on the
CD):**
- **Implied dwellings 429,282 = 1.005× census** (was 1.89×) — within ±10%.
- **Residential space heat 6.68 TWh vs CEUD-scaled 7.38 TWh (−10%)** — within
  ±20% (was +36% bbox-wide).
- **Detached per-unit mean 22,655 kWh vs CEUD 22,520 (+1%)** — essentially
  unchanged, confirming the fix is stock, not intensity.
- **Modelled space-heat emissions 80% of the Energy Evolution 2024 buildings
  inventory** (was 104%) — a plausible space-heat share (<100%).
- **Fuel shares gas 59.1% / electric 21.0%** — on the StatCan 38-10-0286
  Ottawa-CMA target. (Phase 2.5 also fixed the fuel rake geography: the IPF is
  fitted over the **CD** residential subset that the CMA target describes, not
  the bbox — raking bbox-wide had hit 59/21 across the whole bbox while leaving
  the city subset too gassy, ~74%.)

The detached/row *split* stays soft (inside-CD detached +23% / row −27% vs
census, but their **sum** is only +3.4%): semi-detached and duplex halves
digitised as separate footprints are counted `detached`, the known §3.10
building:dwelling attribution softness — a labelling issue that does not move
the dwelling total or (materially) the heat sum, and is out of scope for the
stock-count fix.

**New/changed columns:** `in_ottawa_cd` (bool), `assign_path` (class
provenance), and the `accessory` class (18k-ish buildings, `annual_kwh = 0` in
Phase 2 — treated as unheated for this screening layer). Downstream Phase 4/5
must sum over `in_ottawa_cd` for any quotable city-wide figure.

### 3.11 `build_building_demand.py` — per-building heat load (Heat Demand Phase 2)

Adds a **screening estimate** of annual space-heat energy, design-day heat
loss, effective envelope UA, and heating fuel to every building in
`buildings_ottawa.parquet` (HEATDEMAND_PLAN.md §2–4). New columns:
`floor_area_m2, annual_kwh, design_kw, ua_w_per_k, units_est, heat_fuel,
demand_method, demand_confidence`. This is a **screening layer, not a set of
building audits** — it says so in the parquet metadata (`heatdemand_phase2`
key) — because vintage and the ambiguous-type class split are probabilistic
per building (Phase 1, §3.10), the intensities are population medians, and the
fuel is a raked probabilistic draw. Numbers are meaningful in aggregate (the
500 m cell / feeder rollups of Phase 4), **not for a single address**.

**Floor area.** `floor_area_m2 = footprint_m2 × storeys` (gross external). For
the archetype (house) method this is converted to ERS-comparable *heated*
interior area with a documented factor `HEATED_FRACTION_HOUSE = 0.80` (≈ 15%
attached-garage/wall-thickness + 5% roof-pitch storey over-count — Canada
Structures footprints include the garage, and `storeys = round(height/3)`
rounds steep-roofed houses up). The non-residential intensities are per *gross*
floor area (that's how EWRB/CEUD report EUI), so they use `floor_area_m2`
directly.

**Residential houses (`detached`, `row`).** Ottawa ERS archetypes
(`HeatPump/data/processed/archetypes.json`, vintage × type, per
HeatPump/METHODOLOGY.md Phase 4). `annual_kwh`, `design_kw` and `ua_w_per_k`
are the archetype's values scaled by `clip(heated_area / archetype_floor_area,
0.5, 2.5)`. Phase 1's 8 census vintage bands map to the 3 archetype detached
bins (`1960_or_before`/`1961_1980 → pre_1980`; `1981_1990`/`1991_2000`/
`2001_2005 → 1980_2005`; the three post-2005 bands → `post_2005`).
**Semi/duplex treatment:** Phase 1's `class` enum has no `semi` bucket — semi/
duplex are folded into `row` and use the `townhouse_row` archetype. This is
validated against CEUD ON `single_attached` (which is *exactly* row + semi +
attached: 47.1 GJ/hh in 2021), whose per-household energy (13,083 kWh) matches
the `townhouse_row` archetype (13,438 kWh) to ~3% — so the row archetype
already represents the semi/duplex population without a separate rule.

**Apartments / MURBs (`lowrise_murb`, `highrise_murb`).** Ottawa apartment
space-heat intensity per m² is built by transferring the **CEUD Ontario
apartment ÷ single-attached per-m² ratio** (0.251 / 0.318 = 0.789 in 2021)
onto the Ottawa `townhouse_row` archetype per-m² intensity (75.6 kWh/m²) →
**59.7 kWh/m²**. This keeps apartments internally consistent with — and more
efficient per m² than — the Ottawa row house, and needs **no external HDD
guess** (the row archetype is already the Ottawa-climate anchor); it is
preferred over applying the raw CEUD provincial apartment intensity with an
Ottawa/Ontario HDD uplift (the alternative, which would double-count climate
against the row archetype and produce an implausible apartment > row per-m²).
Both MURB tiers use the same intensity (CEUD doesn't split apartments by rise).
`units_est` is a rough reported column only (`floor_area / 106.7 m² gross per
household`, from CEUD); MURB *energy* is `floor_area × intensity`, independent
of the unit estimate. `design_kw = annual_kwh / EFLH` (below).

**Non-residential (`commercial`, `institutional`, `industrial`).** The plan
called for CEUD ON commercial GJ/m² by activity, but this CEUD extract carries
per-activity *total* energy with only *aggregate* floor space (no per-activity
GJ/m²) and its provincial commercial intensity (1.49 GJ/m² total) is **~1.9×
the EWRB Ottawa actual** (0.85 GJ/m²) — the well-known CEUD commercial
floor-space undercount, confirmed here. So, exactly as the plan intended EWRB
to *"calibrate the commercial intensity table"*, the base intensity is the
**EWRB-2024 Ottawa actual median `Site_EUI` by property-type group** (GJ/m²,
total all-end-use) and the space-heat portion is isolated with the **CEUD ON
commercial space-heat share** (~0.574). Result: commercial ≈ 137 kWh/m²,
institutional ≈ 125 kWh/m². `institutional` maps to the CEUD/EWRB commercial
sector (education, health, public services live there). `industrial` is a
**clearly-flagged low-confidence placeholder** (`demand_confidence =
very_low`): EWRB warehouse actuals × a lower 0.40 space-heat share ≈ 63 kWh/m²,
because this class is dominated by agricultural/small-industrial footprints
(barns, silos) whose energy is process- or barely-space-heat.

**Design kW.** Houses use the archetype `design_heat_loss_kW × scale` directly.
Every other class uses `design_kw = annual_kwh / EFLH`, where the equivalent
full-load heating hours are computed from the **Ottawa TMY** at a per-class
balance point (`EFLH = Σ max(0, Tbal − T) / (21 − (−22.8))`): apartment/
industrial Tbal 10/8 °C → 1358/1143 h, commercial/institutional Tbal 12 °C →
1592 h. This is TMY-consistent by construction — the Tbal = 10 °C EFLH (1358 h)
reproduces the detached archetypes' own annual/design ratio (1340–1408 h).
`ua_w_per_k = design_kw × 1000 / 43.8` for the non-house classes (feeds Phase 3
electrification).

**Fuel (`heat_fuel`).** Per-FSA pre-retrofit `Pre_HeatFuel` shares from the ERS
Ontario parquet (K-prefix FSAs; ≥ 30 records else an Ottawa-wide fallback) are
**raked by iterative proportional fitting** to the StatCan 38-10-0286
Ottawa-ON-part 2023 shares (**gas 59%, electric 21%**; the oil/propane/wood
tail is suppressed at that geography — source notes §2.2 — so its 20% is split
internally by the ERS relative proportions), under a **rural no-natural-gas
constraint** (buildings whose representative point falls outside the City
serviced-area layer `city_open_loop_potential.geojson` get gas probability 0;
an all-gas rural FSA falls back to the city non-gas mix so it isn't silently
drawn as gas). A seeded per-building categorical draw (seed `20260716`, as
Phase 1) then assigns the fuel. Non-residential classes are not covered by the
dwelling-only StatCan table, so they use a documented serviced→{gas 0.85,
electric 0.15} / rural→{oil 0.45, propane 0.45, electric 0.10} prior instead of
the rake. Result: residential gas 59.1% / electric 21.0% (on target).

**EWRB / actuals override.** Phase 0 (`heatdemand_source_notes.md` §2.1) found
**EWRB has no street address** (only city + FSA-prefix) and **no floor area**,
so the plan's "geocode EWRB rows → footprint match → replace modelled with
actuals" step is **not possible** and is not attempted; EWRB is used only as
the FSA/property-type intensity *calibration* described above. Better Buildings
Ottawa 2022 (452 rows, has lat/long) was identified by Phase 0 as the viable
per-building actuals source but was not downloaded this phase — a documented
follow-up if a per-building override is wanted later.

**Validation (printed by the script; investigated, not force-fit).**
- **(a) Residential vs CEUD-scaled:** modelled **10.07 TWh** vs CEUD ON
  space-heat per household scaled to Ottawa's 427,113 census households × a 1.13
  Ottawa/Ontario HDD uplift = **7.38 TWh** → **+36%**, marginally outside the
  ±30% band. **Investigated:** this is a *stock-count* artifact, not a
  per-building error. The modelled stock implies **808,422 residential dwellings
  vs 427,113 census households (1.89×)** because Phase 1 over-attributes
  detached (OSM tags fold semi/duplex into `house`, §3.10) and the MURB
  footprints carry generous floor area. The **per-unit** intensity is sound: the
  modelled detached mean (**22,534 kWh**) matches CEUD ON `single_detached`
  (**22,520 kWh**) to **<1%**. Per-building values are therefore kept **as
  modelled** (Phase 3 electrifies actual buildings and needs the correct
  per-building load); **city-wide sums should be read as upper estimates** until
  Phase 1 classification is refined, and Phase 4/5 should carry this caveat.
- **(b) Gas-heated share vs StatCan:** residential gas **59.1%**, electric
  **21.0%** — on the 38-10-0286 targets by construction of the rake.
- **(c) Community energy inventory:** the Energy Evolution 2024 inventory
  publishes **emissions** ("Buildings" = 2,738,852 tCO₂e), not raw GWh/PJ
  (source notes §1.4), so the check is via emission factors (gas 0.186, ON grid
  0.030 kg CO₂e/kWh input). Modelled space-heat emissions **2.84 Mt = 104%** of
  the buildings inventory; since space heat should be only ~55–70% of building
  energy, the >100% reflects the **same ~1.36× residential stock inflation as
  (a)** — dividing it out lands at ~76% of inventory, a plausible space-heat
  share. Modelled natural-gas *input* for space heat ≈ 9.9 TWh/yr.
- **(d) EWRB cross-check:** EWRB Ottawa median total `Site_EUI` — commercial
  0.86, institutional 0.78, industrial 0.57 GJ/m² — vs CEUD's 1.73× higher
  provincial commercial intensity; confirms EWRB actuals as the commercial base.
  No per-building override (no addresses, above).
- **(e) Independent intensity cross-checks (HDD-normalised):** modelled
  detached/row per-*heated*-m² (85 / 71 kWh/m²) sit ~30% below CEUD ON
  single_detached/attached (125 / 100) **because the ERS archetypes carry
  larger-than-provincial-average floor areas** (audit homes skew large) — the
  same fact as the per-unit *match* in (a): same energy per home spread over
  more m². Against **TaNDM Kelowna 2021** (github.com/canmet-energy/tandm,
  analysis-ready xlsx cached at `Data/Raw/references/`), Kelowna single-detached
  gas-per-gas-metered-unit → implied delivered space heat, HDD-normalised from
  Kelowna (~3000) up to Ottawa (4407), is **29,462 kWh vs our 22,534 (−24%)**;
  the gap is expected (Kelowna gas includes water heating, an 78% space-fraction
  assumption, and milder-climate normalisation is approximate) and confirms the
  order of magnitude. A full extraction of the `canmet-energy/housing-archetypes`
  H2K library EUIs was deprioritised for this screening layer (its national
  medians are the same EnerGuide/SHEU lineage our ERS archetypes and CEUD both
  derive from); the two quantitative cross-checks above (CEUD ON, TaNDM) cover
  the independent-reference requirement.

**New reference cached this phase:** `Data/Raw/references/
TaNDM_Kelowna_2021_AnalysisReady.xlsx` (126 KB, github.com/canmet-energy/tandm,
LGPL) — for the (e) cross-check.

**Known limitations / open risks.**
- **City-wide totals run high** (validation (a)) — a Phase 1 stock-count issue,
  documented above; the single most valuable upgrade before the map is trusted
  quantitatively is tightening Phase 1's detached/row/MURB classification.
- **Vintage & fuel are probabilistic per building** — fine for 500 m cells,
  meaningless for one address (same caveat as Phase 1's vintage).
- **Non-residential is the weakest tier** (`demand_confidence` low/very_low):
  EWRB's disclosed buildings skew large and efficient, per-activity resolution
  isn't available, and `industrial` is an explicit placeholder.

## 4. Results (2026-07-15 build, v2 Phase A)

**GeoPackage:** 55,903 wells (50,902 with geometry, up from 50,835 — 67
recovered from `tblBore_Hole`) · 144,719 formation intervals · 62,324 water
strikes · 44,026 pump tests · 125,495 construction elements.

**Conductivity coverage:** the GSC mapped-geology fallback (§3.1) cut
unknown-conductivity wells from **9,180 → 742**:
medium 45,963 (was 37,671) / low 7,351 (unchanged) / high 1,847 (was 1,701) /
unknown 742. Of the remaining 742 unknowns, all are wells with no formation
record *and* no usable geometry (so no GSC join was possible) or fell
outside every mapped GSC polygon — genuinely irreducible from these two
sources.

**Surface:** 13,778 cells at 500 m (was 13,383); range 1.40–3.20 W/m·K; 87%
of cells high-confidence. `medium` 12,051, `high` 1,138 over Shield
granite/gneiss in the west and north-west, `low` 589 (clay/silt-dominated —
down from 1,102 now that more wells resolve to a real lithology instead of
sitting out of the interpolation entirely).

**Open-loop screen:** 31,775 viable / 3,602 possible / 15,469 unlikely (wells
with geometry, in-bbox — up from 50,808 to 50,846 total with the geometry
recovery).

**Drilling-difficulty surface (v2 Phase C, §3.8):** 35,702 wells scored (those
with geometry + a known depth-to-bedrock, in bbox); per-well score min 4 /
median 24 / mean 25.3 / max 88. Gridded to **13,403 cells** at 500 m (score
range 5–75 after rounding to 5): **easy 5,750 / moderate 6,264 / difficult
1,389** (≈ 43 % / 47 % / 10 %). Dominant driver per cell: overburden 6,911,
rock hardness 6,091, artesian 366, problem layers 35 — i.e. cost is driven
mostly by casing-through-overburden in the east and hard-rock penetration along
the western Shield edge; problem layers and artesian are modifiers that rarely
dominate but show in the popup breakdown. 87 % of cells high-confidence.

**Per-segment suitability (v2 Phase D, §3.9):** three 0–100 scores on the 13,778
conductivity cells. **Residential/small-commercial** min 34 / median 76 / mean
74.6 / max 90 — broadly feasible across Ottawa, best in easier-drilling,
higher-conductivity suburban/rural cells and explicitly *not* concentrated
downtown. **Large buildings** min 19 / median 54 / mean 53.2 / max 87 — pulled
down over the low-conductivity eastern clay plain (depletion-risk penalty) and up
over the higher-λ west, with a feeder/zoning bump in employment areas.
**District energy** min 0 / median 15 / mean 22.3 / max 95 — deliberately bimodal:
near-zero across the rural majority and high only in the serviced urban core near
trunk sewers with feeder headroom (the demand proxy is binary urban/rural until a
heat-demand layer exists — see the upgrade hook in §3.9 and caveat §5). The
demand factor is a **coarse proxy**; all other factors are continuous. Sanity
checks (inter-segment correlations, district top-decile location, residential
not-downtown) all pass — see §3.9.

**Data-quality fixes (v2 Phase A, 2026-07-15):** `status` "code:0" (464
wells) → "Not specified"; `well_use` recovered 36 wells via `USE_2ND`
fallback (8,123 → 8,087 still unrecorded); geometry recovered for 67 wells
via `tblBore_Hole`; `bedrock_depth_m` recovered for 10,885 wells via the
formations fallback (16,543 still missing); lithology recovered for 8,438
wells via the GSC mapped-geology fallback. See §3.1 for method detail.

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
7. **GSC-mapped lithology is weaker evidence than a well log** (§3.1) — a
   national-scale generalized polygon, not a point observation. 8,438 wells'
   conductivity estimates rest on it; check `lithology_source` (well popups
   and the `combined_layers.geojson`/gpkg `lithology_source` field) before
   treating a specific well's conductivity as log-derived.
8. **5,001 wells have no recoverable geometry** (no coordinates anywhere in
   the export, not even `tblBore_Hole`) and **16,543 have no bedrock depth**
   from either the shapefile or the formations fallback — both irreducible
   from this dataset as exported.
9. **Drilling difficulty is *relative screening*, not a drilling quote**
   (§3.8). The score ranks cells against each other from four proxies in the
   water-well logs (overburden thickness, problem layers, rock hardness,
   neighbourhood artesian) with hand-set weights; it is not a cost estimate,
   a metres-of-casing figure, or a substitute for a site investigation. Only
   wells with a logged depth-to-bedrock are scored, so difficulty cells lean
   on the same overburden coverage as everything else — check the confidence
   flag. Artesian is a 1 km neighbourhood share of a sparse (503-well) signal,
   so it flags *areas* to check, not individual boreholes.
10. **Segment suitability is a weighted screening ranking, not a feasibility
    study** (§3.9). The three scores combine the same screening proxies (all the
    caveats above flow through) with **hand-set, uncalibrated weights**; they rank
    cells *relative to each other for a given segment*, not against installed
    system costs or performance. The **district-energy demand factor is a coarse
    binary proxy** (in/out of the City's serviced urban area) until a modelled
    heat-demand layer (`heat_demand_grid.geojson`, ROADMAP item 7) exists — the
    script already has the upgrade hook, so district scores will sharpen
    considerably once that layer lands. Treat all three as "where to look first",
    then do a site-specific load calc + thermal-conductivity test.

## 6. Next steps

> **v2 rework in progress:** ROADMAP.md item 8 has the full plan and prompts
> — well-data fixes (**Phase A — done 2026-07-15**), a sourced & user-editable
> conductivity table (**Phase B — done 2026-07-15**), a drilling-difficulty
> layer (**Phase C — done 2026-07-15**, §3.8), and per-segment suitability
> scores (**Phase D — done 2026-07-15**, §3.9). Item 5 below (GSC bedrock
> fallback) was absorbed into Phase A and is now done — see §3.1.

1. **Publish the map** on the GitHub Pages site alongside
   `retrofits.html` / `construction.html` (it's one file; needs only a commit
   and a link).
2. **Closed-loop depth economics:** combine depth-to-bedrock + conductivity
   to estimate required borehole metres per kW by cell — turns the map from
   "where is it good" into "what would it cost".
3. **Building footprints / heat demand:** fetch TopographicMapping/3 in tiles
   and join to the conductivity grid for a demand-vs-resource view (the
   original guide's motivation for footprints). This directly upgrades the
   **district-energy suitability demand factor** (§3.9), which currently uses a
   coarse binary serviced-area proxy — `build_suitability.py` already reads
   `heat_demand_grid.geojson` when present.
4. **Sewer heat recovery screening:** the trunk-sewer layer + zoning is
   already in the map; adding pipe diameter-based flow estimates would rank
   wastewater heat-recovery sites.
5. ~~**Bedrock geology overlay**~~ — done 2026-07-15 (v2 Phase A): the GSC
   layer now backs the lithology (and hence conductivity) fallback for
   wells with no formation record. See §3.1.
6. **Data refresh cadence:** WWIS updates quarterly; municipal layers change
   rarely. A yearly manual rerun of the chain (§2) is adequate — no
   scheduled job needed.
