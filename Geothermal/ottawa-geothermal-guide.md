# Ottawa Geothermal Case Study — Data & Pipeline Guide

---

## 1. Data to Collect

### Provincial / National

| Dataset | Source | Link | Format |
|---|---|---|---|
| Ontario Water Well Information System (WWIS) | Ontario Ministry of Natural Resources | [Download](https://www.ontario.ca/data/well-records) | CSV / GDB |
| NRCan Geothermal Maps of Canada | Natural Resources Canada | [Download](https://ostrnrcan-dostrncan.canada.ca/entities/publication/d608e62b-d0a1-46db-aa04-e863f018a256) | Raster / PDF |
| GSC Bedrock Geology (Ottawa area) | Geological Survey of Canada | [Download](https://geoscan.nrcan.gc.ca) | Shapefile |
| OEB Centralized Capacity Information Map (CCIM) | Ontario Energy Board | [View / Export](https://www.oeb.ca/ontarios-energy-sector/centralized-capacity-information-map) | GeoJSON / API |
| IESO Ontario System Map | Independent Electricity System Operator | [View](https://www.ieso.ca/power-data/supply-overview/ontario-system-maps) | Interactive |

### Ottawa Municipal (Ottawa Open Data Portal — [data.ottawa.ca](https://data.ottawa.ca))

| Dataset | Notes | Format |
|---|---|---|
| City-Owned Properties | Search "city owned properties" | Shapefile / GeoJSON |
| Zoning / Land Use | Filter for industrial/employment zones | Shapefile / GeoJSON |
| Sewer Infrastructure | Combined and sanitary sewer lines | Shapefile / GeoJSON |
| Building Footprints | Useful for heat demand estimation | Shapefile / GeoJSON |
| Hydro Ottawa Capacity Map | Check Hydro Ottawa site directly | GeoJSON / PDF |

### Conservation Authority / Groundwater

| Dataset | Source | Link | Format |
|---|---|---|
| Groundwater / Aquifer Data | Rideau Valley Conservation Authority | [rvca.ca](https://www.rvca.ca) | Shapefile / PDF |
| Water Well Records (Ottawa subset) | Already in WWIS above | — | — |

---

## 2. GitHub Folder Structure

```
ottawa-geothermal/
│
├── README.md
│
├── data/
│   ├── raw/                        # Untouched downloads — never edit these
│   │   ├── wwis/                   # Ontario well records
│   │   ├── nrcan/                  # Geothermal maps
│   │   ├── gsc/                    # GSC bedrock geology
│   │   ├── oeb_ccim/               # Grid capacity
│   │   ├── ottawa_open_data/       # All Ottawa municipal layers
│   │   └── rvca/                   # Groundwater data
│   │
│   └── processed/                  # Outputs from transformation scripts
│       ├── wwis_cleaned.csv
│       ├── wwis_ottawa.geojson
│       ├── thermal_conductivity.geojson
│       ├── open_loop_feasibility.geojson
│       ├── grid_capacity_ottawa.geojson
│       └── combined_layers.geojson
│
├── scripts/
│   ├── 01_wwis_quality_check.py
│   ├── 02_wwis_clean_filter.py
│   ├── 03_formation_to_conductivity.py
│   ├── 04_open_loop_feasibility.py
│   ├── 05_clip_to_ottawa.py
│   ├── 06_interpolate_grid.py
│   ├── 07_merge_layers.py
│   └── 08_export_for_html.py
│
├── output/
│   └── index.html                  # Final interactive map
│
└── notebooks/                      # Optional — exploratory analysis
    └── exploration.ipynb
```

---

## 3. Transformation Pipeline & Claude Code Prompts

Work through these in order. Each step feeds the next.

---

### Step 1 — Audit WWIS Data Quality

**Prompt:**
```
I've downloaded the Ontario Water Well Information System (WWIS) dataset.
The file is at [path].

Please analyze it and give me a data quality report focused on GSHP
feasibility mapping. Specifically:

1. What columns are present and completeness rate for each
2. For fields relevant to GSHP (depth to bedrock, formation description,
   static water level, well yield, coordinates) — what % of records have
   usable values
3. How messy are the formation description fields — show me a sample of
   the most common values and flag inconsistencies
4. Geographic distribution — are records clustered or spread across Ontario
5. Date range of records
6. Flag any data quality issues before I build the pipeline

Don't clean or transform anything yet. Output a summary report and a
quick scatter plot of well locations.
```

---

### Step 2 — Clean & Filter WWIS

**Prompt:**
```
Using the WWIS dataset at [path], clean and filter it:

1. Drop records missing coordinates, depth to bedrock, or formation description
2. Clip to Ottawa area using bounding box:
   lat 44.96 to 45.61, lon -76.36 to -75.24
3. Standardize formation descriptions using fuzzy matching — bucket into:
   limestone, dolostone, sandstone, shale, granite, gneiss, clay, till, unknown
4. Flag records where static water level is present (open-loop candidates)
5. Save output as data/processed/wwis_ottawa.geojson with columns:
   well_id, lat, lon, depth_to_bedrock_m, formation_type, static_water_level_m,
   well_yield_lpm, year_drilled

Report how many records survived each filter step.
```

---

### Step 3 — Map Formations to Thermal Conductivity

**Prompt:**
```
Using data/processed/wwis_ottawa.geojson, add a thermal_conductivity_wm column
using this lookup table:

limestone: 2.8, dolostone: 3.0, sandstone: 2.3, shale: 1.9,
granite: 3.2, gneiss: 3.0, clay: 1.4, till: 1.8, unknown: 2.0

These are approximate mid-range values in W/m·K from published GSHP design
literature. Add a conductivity_confidence column: high if formation_type is
not unknown, low otherwise.

Save as data/processed/thermal_conductivity.geojson.
```

---

### Step 4 — Flag Open-Loop Feasibility

**Prompt:**
```
Using data/processed/thermal_conductivity.geojson, add an open_loop column:

- "viable" if static_water_level_m is present AND well_yield_lpm >= 15
- "possible" if static_water_level_m is present but well_yield_lpm is missing
- "unlikely" otherwise

15 lpm is a conservative minimum threshold for a small open-loop GSHP system.
Save as data/processed/open_loop_feasibility.geojson.
```

---

### Step 5 — Load & Clip Ottawa Municipal Layers

**Prompt:**
```
I have the following Ottawa Open Data files in data/raw/ottawa_open_data/:
[list your actual filenames]

For each file:
1. Load and check the CRS — reproject everything to EPSG:4326 if needed
2. Clip to Ottawa bounding box (lat 44.96–45.61, lon -76.36–-75.24)
3. For the zoning layer, filter to industrial/employment land use categories only
4. Save each as a separate GeoJSON in data/processed/:
   city_properties.geojson, zoning_industrial.geojson, sewer_lines.geojson,
   building_footprints.geojson

Report feature counts for each output.
```

---

### Step 6 — Interpolate Thermal Conductivity Surface

**Prompt:**
```
Using data/processed/thermal_conductivity.geojson, create a continuous
raster surface of thermal conductivity across Ottawa using IDW interpolation:

1. Use scipy.interpolate or pykrige for interpolation
2. Grid resolution: 500m
3. Clip output to Ottawa boundary
4. Export as both a GeoTIFF (data/processed/thermal_conductivity_grid.tif)
   and as a GeoJSON grid of polygons for use in HTML mapping
   (data/processed/thermal_conductivity_grid.geojson)
5. Add a human-readable label column: low (<2.0), medium (2.0–2.8), high (>2.8)

Flag areas with sparse well coverage where interpolation confidence is low.
```

---

### Step 7 — Merge All Layers

**Prompt:**
```
Merge the following processed layers into a single GeoJSON for the HTML map:

- data/processed/thermal_conductivity_grid.geojson (polygon grid)
- data/processed/open_loop_feasibility.geojson (points)
- data/processed/city_properties.geojson (polygons)
- data/processed/zoning_industrial.geojson (polygons)
- data/processed/sewer_lines.geojson (lines)
- data/processed/grid_capacity_ottawa.geojson (if available)

Don't dissolve them — keep as separate named layers in a single output
GeoJSON FeatureCollection with a layer property on each feature indicating
which dataset it came from.

Save as data/processed/combined_layers.geojson.
Confirm total feature count and layer breakdown.
```

---

### Step 8 — Build HTML Map

**Prompt:**
```
Using data/processed/combined_layers.geojson, build a single self-contained
HTML file at output/index.html using Leaflet.js (load from CDN).

The map should:
1. Default view: Ottawa, zoom level 11
2. Toggleable layers via a layer control panel:
   - Thermal conductivity grid (choropleth: green=high, yellow=medium, red=low)
   - Open-loop feasibility points (color by viable/possible/unlikely)
   - City-owned properties (blue outline)
   - Industrial/employment zones (purple fill, semi-transparent)
   - Sewer lines (grey lines)
   - Grid capacity (if available — red/amber/green by capacity)
3. Click any feature to show a popup with its key attributes
4. Add a legend for each active layer
5. Embed all GeoJSON data inline in the HTML so it runs without a server

The output should be a single file I can open in a browser and share.
```

---

*Last updated: June 2026*
