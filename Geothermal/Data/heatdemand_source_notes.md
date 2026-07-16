# Heat-demand building-stock scouting — decision memo

Phase 0 of [HEATDEMAND_PLAN.md](../../HEATDEMAND_PLAN.md) §3. Scouting only —
no pipeline built. All raw files fetched into `Geothermal/Data/Raw/` (paths
below); counts/schemas verified live 2026-07-16 via curl/python (sqlite3,
duckdb, pyogrio, openpyxl), not from documentation.

## 1. Building footprint / height / type sources

### 1.1 Canada Structures — Ontario (`Raw/CanadaStructures/on_structures_en.gpkg`, 1.45 GB)

- **Download**: `open.canada.ca` dataset `3829eee9-f898-4643-9ad8-f48575b8873d`.
  The CKAN API (`/data/api/action/package_show`) and a bare `curl` GET on the
  resource download URL both get WAF-rejected ("Request Rejected", 244-byte
  HTML body) — **the fix is a `Referer` header** pointing at the dataset page
  (`-H "Referer: https://open.canada.ca/data/en/dataset/<id>"`), not just a
  `User-Agent`. This is a new quirk beyond the memory note ("CKAN API rejects
  curl") — the HTML *page* fetches fine with just a UA; only the resource
  *download* endpoint needs the Referer.
- **Schema**: single layer `ON_Structures_en`, 4,732,798 features province-wide.
  Columns: `CS_ID, Province, OSM, OSM_ID, OSM_Name, OSM_Type, ODB, ODB_ID,
  ODB_Source, MSB, OSM_LC, LC_Name, Area, Perimeter, Height`. CRS is a custom
  Lambert (`srs_id 100000`, GRS80, not an EPSG-registered code — transform via
  the embedded WKT, not by srs_id lookup) but has an **`rtree` spatial index**,
  so bbox queries are fast without loading the whole layer.
- **Ottawa bbox count** (rtree candidates, `combine_wells.py` bbox
  `(-76.36, 44.96, -75.24, 45.61)`): **467,379** — same order as the City's
  ~392k (bbox is a rectangle larger than city limits, so a higher count is
  expected, not a discrepancy).
- **Attribute fill in the Ottawa clip**: `Height` non-null/non-zero
  **396,656 (84.9%)**; `OSM_Type` (a real structure-type field — `detached`
  166,808 / `terrace` 74,420 / `house` 40,906 / `garage` 7,096 / `commercial`
  4,858 / `retail` 3,454 / `apartments` 3,358 / `barn`, `industrial`,
  `residential`, `roof`, etc.) non-null **313,776 (67.2%)**; `OSM` flag set
  86.1%, `ODB` (Open Database of Buildings) flag set 68.6%, `MSB` (Microsoft
  Building Footprints) flag only 2.9%. `LC_Name` is **not** land cover — it's
  Ottawa neighbourhood name (Bridlewood, The Glebe, Stonebridge, …), useful for
  spatial QA, not classification. Height range 1.0–104.4 m, mean 6.35 m
  (plausible — mean is dominated by the ~150k detached/terrace houses).
- **Licence**: Open Government Licence – Canada.
- **Verdict**: **best single source for footprint + height + type together.**
  85% height coverage and 67% type coverage from one province-wide file beats
  stitching NRCan (height only) + Overture (weaker height) + zoning (type
  only) for most of the stock. Still need zoning + census DA mix to fill the
  ~33% untyped and to split `house`/`detached`/`residential` into the plan's
  detached/row/lowrise-MURB/highrise-MURB scheme (Canada Structures' OSM_Type
  doesn't distinguish storeys or unit count).

### 1.2 NRCan Automatically Extracted Buildings — Ottawa-Gatineau tile (`Raw/NRCanBuildings/`, 55 MB zip → 152 MB gpkg)

- **Download**: dataset `7a5cda52-c7df-427f-9ced-26f19a8a64d6` is not one
  national file — it's tiled by LiDAR acquisition project, listed at
  `download-telecharger.services.geo.ca/pub/nrcan_rncan/extraction/auto_building/gpkg`
  (plain directory listing, no WAF issue, no Referer needed). Ottawa has a
  **dedicated tile**: `Autobuilding_ON_Ottawa_Gatineau_2020_gpkg.zip`.
- **Schema**: `304,860` features covering **both** Ottawa and Gatineau (CRS
  EPSG:4617 ≈ WGS84 for practical purposes; bounds
  `(-76.29, 45.00, -75.24, 45.70)` span the river). Columns:
  `feature_id, md_id, acqtech(_en/_fr), provider(en/fr), datemin/datemax,
  haccmin/haccmax, vaccmin/vaccmax, heightmin, heightmax, elevmin, elevmax,
  bldgarea, comment, qltylvl(_en/_fr)`. **No type/class field at all.**
- **Height**: **100% filled** (`heightmin`/`heightmax` both non-null on every
  row), source LiDAR flown 2020-04-18 to 2020-05-21, all `acqtech=Lidar`,
  `provider=Municipal` (i.e. City of Ottawa's own LiDAR, re-packaged by
  NRCan). Range 0–147.6 m min / 2.1–148.6 m max, mean ~3.6/7.5 m.
  `qltylvl_en` is uniformly `"Poor"` across all 304,860 rows — this is a
  codelist tied to the *acquisition method* (Lidar-derived polygons default to
  "Poor" in NRCan's schema; per the catalogue doc it's "estimated quality
  according to the source dataset", not a per-building accuracy flag) — not a
  usability red flag, but undocumented on the portal page, worth footnoting.
- **Coverage caveat**: this file mixes ON (Ottawa) and QC (Gatineau) sides;
  needs a spatial clip against the City boundary (or the ON-only Canada
  Structures footprints) before use, consistent with the project's
  Ontario-only convention.
- **Verdict**: **excellent height-only enrichment source**, 100% coverage vs
  Canada Structures' 85%, same underlying City LiDAR. But no type attribute
  and needs the ON/QC clip. Best used as the height override where Canada
  Structures' `Height` is null/zero, not as the primary source.

### 1.3 Overture Maps buildings — Ottawa bbox (`Raw/Overture/ottawa_buildings.parquet`, 88 MB, 528,129 rows)

- **Download**: `pip install overturemaps`, then
  `overturemaps download --bbox=-76.36,44.96,-75.24,45.61 -f geoparquet -t building`
  — no WebFetch/curl issues, straightforward.
- **Attribute fill**: `height` non-null **224,726/528,129 (42.6%)**,
  `num_floors` non-null only **16,784 (3.2%)**, `subtype`/`class` non-null
  ~74% each with the **same OSM-derived categories** as Canada Structures
  (`detached, terrace, house, residential, apartments, commercial, retail,
  industrial, …` — makes sense, same upstream OSM tags). Height range 1–118 m,
  mean 4.95 m.
- **Verdict**: **weaker than Canada Structures on every axis that matters**
  (43% height vs 85%, near-zero floor count) for the same underlying tag
  vocabulary. Not worth using as primary or even fallback for height; Canada
  Structures already captures the OSM contribution Overture would add. Drop
  from the pipeline — no enrichment role left once Canada Structures + NRCan
  are in.

### 1.4 City of Ottawa footprints, address points, 3D buildings (open.ottawa.ca)

- **Building Footprints** (`open.ottawa.ca/datasets/ottawa::building-footprints`,
  ArcGIS item confirms this **is** `TopographicMapping/3`, ~392k polygons,
  aerial photos **2014**, "update frequency currently unknown" — i.e. stale
  relative to Canada Structures' 2026-04 refresh and NRCan's 2020 LiDAR).
  Geometry only, as the plan already found.
- **Municipal Address Points** (`Address_Information/MapServer/0`):
  **403,096** points, fields include `UNIT` (non-null on **40,131**, 10.0%).
  Grouping by `(ADDRNUM, ROAD_NAME)` with distinct `UNIT` values is a workable
  units-per-building proxy for MURBs, confirming the plan's hope — but only
  10% of points carry a unit number, so it will only resolve unit counts for
  buildings that already have per-unit municipal addressing (most purpose-built
  MURBs), not converted/informal multi-unit houses.
- **"3D Buildings LOD1"** (`open.ottawa.ca/datasets/ottawa::3d-buildings-lod1`):
  **the ArcGIS FeatureServer layer behind this listing is NOT the buildings**
  — it's 116 Ottawa Neighbourhood Study (ONS) zone polygons, each carrying a
  `DXF` and `GDB` short-link (`arcg.is/...`) to a **per-neighbourhood City
  LiDAR-derived LOD1 building geodatabase**. Confirmed by downloading one
  (`TREND-ARLINGTON.zip`, 810 KB) — it contains a **MultiPatch (3D solid)
  geometry layer** (OGR geometry type 1016), which GDAL's default OGR read
  path (`pyogrio`) refuses to open even for attribute-only reads ("Geometry
  type is not supported: 1016"); needs `ogr2ogr -nlt MULTIPOLYGON25D` or
  similar linearization, or GDAL's OpenFileGDB driver directly, to extract.
  Per the dataset description the attributes are exactly what's wanted —
  Footprint Area, Ground Elevation, Top Elevation, Total Height — authored by
  the City's own Right-of-Way/Heritage/Urban Design team, created 2023,
  updated yearly. **This is the City's own high-quality height source**, but
  it is a 116-file fetch-and-reproject job (each ~1 MB judging by the sample,
  so a few hundred MB total), not a single download — real work, deferred to
  Phase 1, not attempted further here.
- **Better Buildings Ottawa 2022** (`Better_Buildings_Ottawa_2022/FeatureServer/0`):
  **452** benchmarked properties (municipal energy-benchmarking program,
  ENERGY STAR Portfolio Manager data) with `address, property_type,
  year_built, Longitude, Latitude, energy_star, site_eui, source_eui,
  total_ghgs, ghg_intensity, water_use_intensity` — **has lat/long directly**,
  no geocoding needed, unlike EWRB (§2 below). Smaller sample than EWRB (452
  vs 512 Ottawa rows) but likely overlaps EWRB's Ottawa population (same >2000
  m² disclosure bylaw) with the advantage of ready-made coordinates and named
  addresses — **worth using instead of, or to cross-check, EWRB rows that fail
  geocoding.**
- **Greenhouse gas (GHG) emissions inventories 2024**
  (`Greenhouse_gas_(GHG)_emissions_inventories_2024/FeatureServer/0`): the
  Energy Evolution inventory the plan asked for. 11 rows, wide format
  (`F2012...F2024` columns), corporate + community sectors. **Key calibration
  number: community "Buildings" sector = 2,738,852 tCO2e in 2024** (community
  total across all sectors 6,629,980 tCO2e; corporate/City-operations total
  273,631 tCO2e). This is **emissions, not raw electricity/gas kWh or GJ** —
  the plan's Phase 4 validation needs an emissions-to-energy conversion (via
  published grid-electricity and Enbridge-gas emission factors) rather than a
  direct total, or a different top-level number if a raw-energy figure exists
  elsewhere in Ottawa's Energy Evolution reporting (not found in this scouting
  pass — the FeatureServer table only has the GHG rollup, not the underlying
  GWh/PJ). Table is explicitly "beta ... structure and content may change".
  Source: `open.ottawa.ca/datasets/ottawa::greenhouse-gas-ghg-emissions-inventories-2024`.

## 2. Building consumption sources

### 2.1 Ontario EWRB — 2024 (`Raw/EWRB_2024.xlsx`, 1.68 MB, 6,740 rows province-wide)

- **Download**: `data.ontario.ca` (not `open.canada.ca` this time) — its CKAN
  API (`/api/3/action/package_show`) works fine with a plain UA, no Referer
  trick needed (contrast with §1.1). Latest year is **2024**
  (`odc_final_dataset_2024.xlsx`, English; a separate French file also
  exists). Years back to 2018 are all present as separate resources.
- **Ottawa rows**: **512** of 6,740 (`City == 'Hawkesbury'` etc. shows the
  `City` field is free-text, not restricted to CMA names — filtering on
  `'ottawa' in City.lower()` is adequate here since Ottawa isn't a substring
  of any other city in the sheet).
- **Columns** (31 total): `EWRB_ID, City, Postal_Code, PrimPropTypCalc,
  PrimPropTypSelf, Largest_PropTyp, All_Prop_Types, Thrd_Party_Cert,
  WN_Sit_Elc_Int1/2, WN_Sit_Gas_Int1/2/3, All_Water_Int1/2, Ind_Water_Int1/2,
  Site_EUI1/2, Source_EUI1/2, WN_Site_EUI1/2, WN_Source_EUI1/2,
  GHG_Emiss_Int1/2, Ener_Star_Score, Ener_Star_Certs, Data_Qual_Check,
  Data_Qual_Date`. **Every energy/water/GHG field is an intensity (per m² or
  per m³), not an absolute value** — no floor area, no raw kWh/GJ/m³ column at
  all in the public release.
- **Address quality — the critical finding**: **there is no street address
  column.** Only `City` (free text) and `Postal_Code`, and `Postal_Code` here
  is the **3-character FSA prefix** (e.g. `K6A`), not a full postal code.
  **Geocoding to a specific footprint is not possible from this file.** This
  contradicts the plan's assumption of an "address → footprint match" Phase-2
  step for EWRB.
- **Verdict**: EWRB-2024 is useful only as an **FSA-level, property-type-level
  calibration table** (median/typical EUI by `PrimPropTypCalc` × FSA) — it can
  bias-correct the CEUD commercial intensity table the way the plan intended,
  but the per-building "actuals override modelled values where an address
  matches" step in Phase 2 **cannot use EWRB** and should instead use **Better
  Buildings Ottawa 2022** (§1.4), which does carry address + lat/long for its
  452 Ottawa rows.

### 2.2 StatCan 38-10-0286 — primary heating systems (`Raw/38100286.csv` via full-table CSV, WDS)

- **Fetch note**: the WDS `getDataFromCubePidCoordAndLatestNPeriods` endpoint
  rejected coordinate strings for this 2-dimension cube ("One or more
  co-ordinate(s) provided is not valid") — the full-table CSV route
  (`getFullTableDownloadCSV` → small 154 KB zip here, unlike the 9 GB permits
  table) was simpler and is the same pattern `construction_etl.py` already
  uses as a fallback; recommend going straight to full-CSV for this cube
  rather than debugging per-coordinate calls.
- **Geography member**: `Ottawa-Gatineau (Ontario part)` (member id 24) is the
  correct ON-only cut; `Ottawa-Gatineau, Ontario/Quebec` (22) is the combined
  CMA; there is no city-of-Ottawa-only member (CMA-level table, as the plan
  expected).
- **Latest year**: **2023** (table covers 2013–2023 annually).
- **2023 Ottawa (ON part) shares**: All primary heating systems captured
  **93%** (7% suppressed for data quality/confidentiality — expect this, not
  100%); of dwellings, **Natural gas 59%**, **Electricity 21%**; Oil, wood,
  propane, "other fuel", and the heat-pump/mini-split rows are all
  **suppressed (NaN)** at this geography — StatCan doesn't publish those
  splits below a threshold for Ottawa-Gatineau ON-part. System type: forced
  air furnace 69% (of which 81% gas, 11% electric), electric baseboard 10%,
  boiler w/ hot water or steam 6%.
- **Verdict**: usable for the plan's gas/electric raking target (59%/21%),
  but the oil/wood/propane/heat-pump tail that the fuel-assignment step needs
  is not published at Ottawa-CMA granularity — Phase 2 will have to source
  the rural oil/wood minority from the ERS per-FSA mix alone, with StatCan
  only constraining the top two.

## 3. Recommendation

**Footprint backbone**: Canada Structures ON gpkg (§1.1) — richer attributes
than the City's own 2014 footprint layer, current to 2026-04, and already
Ontario-clipped. Use the City's 392k TopographicMapping/3 polygons only as a
geometry cross-check/QA layer, not as backbone (it's 12 years stale and
attribute-free).

**Height**: layer Canada Structures' `Height` (85% coverage) as the primary
value; backfill nulls/zeros from NRCan's Ottawa-Gatineau tile (§1.2, 100%
coverage, same underlying City LiDAR, needs an ON-side spatial clip first).
Skip Overture entirely (§1.3) — strictly weaker on both axes. Treat the City's
own LOD1 3D buildings (§1.4) as a **Phase 1 stretch goal**: highest-quality
and most current (2023, City-authored) but requires handling 116 per-
neighbourhood MultiPatch GDBs and a linearization step GDAL doesn't do by
default — worth the effort eventually (it would let height beat both other
sources), but shouldn't block Phase 1's first pass.

**Type/class**: Canada Structures' `OSM_Type` (67% coverage, real
detached/terrace/house/apartments/commercial/retail/industrial categories) as
the primary signal, reconciled with the full zoning layer + census DA
dwelling-type mix for the ~33% untyped and to resolve storeys/MURB-tier
ambiguity that `OSM_Type` alone can't carry (a "house" tag doesn't say
low-rise vs high-rise apartment).

**Units-per-building (MURBs)**: municipal address points (§1.4), grouping by
`(ADDRNUM, ROAD_NAME)` with distinct `UNIT` — expect it to resolve only the
~10% of address points that already carry a unit number; document the
fallback (CEUD per-household intensity × a documented m²/unit assumption) as
the default, not the exception.

**Non-residential actuals override (Phase 2)**: use **Better Buildings
Ottawa 2022** (452 rows, has lat/long) as the primary actuals source, not
EWRB — EWRB has no street address and cannot be geocoded from the public
file. Use EWRB-2024 (512 Ottawa rows) only as an FSA × property-type
intensity calibration table, exactly the role CEUD already plays, i.e. as a
second independent check rather than a building-level override.

**Fuel assignment (Phase 2)**: rake ERS per-FSA fuel mix to StatCan
38-10-0286's Ottawa-ON-part 2023 shares (gas 59%, electric 21%) as the plan
specifies; the oil/wood/propane tail isn't published at this geography, so
those shares must come from ERS alone, flagged lower-confidence.

**City-wide calibration target (Phase 4)**: use the Energy Evolution GHG
inventory's community-buildings figure — **2,738,852 tCO2e in 2024**
(`open.ottawa.ca/datasets/ottawa::greenhouse-gas-ghg-emissions-inventories-2024`)
— converting through published electricity/gas emission factors to back out
an implied energy total, since no raw GWh/PJ figure was found in this table.
Treat it as provisional: the dataset is explicitly labelled beta.

## 4. Open risks

- **City LOD1 3D buildings (§1.4)** is the best possible height source but
  needs MultiPatch→polygon linearization across 116 files before it's usable;
  not attempted here beyond confirming the format. If Phase 1 budget allows,
  prioritize it over the NRCan LiDAR fallback.
- **EWRB has no addresses** — the plan's Phase 2 prompt explicitly assumes an
  "address → footprint match" for EWRB; that step must be redirected to
  Better Buildings Ottawa 2022 instead, and the EWRB paragraph in
  HEATDEMAND_PLAN.md §4 Phase 2 should be corrected before that prompt runs.
- **NRCan tile mixes Ottawa + Gatineau** (QC side) — needs a boundary clip;
  the Ottawa River is not a straight line, so a simple longitude cut will
  mis-assign riverside buildings — clip against the City boundary or the
  ON-only Canada Structures extent instead.
- **StatCan 38-10-0286 suppresses the fuel tail** (oil/wood/propane/heat pump)
  at Ottawa-CMA granularity — the plan's reconciliation step has less to
  reconcile against than assumed; document that ERS carries the tail
  unconstrained.
- **GHG inventory has no raw energy total** — Phase 4's "validate against
  community energy inventory numbers" will need an emissions→energy
  back-calculation (documented conversion factors) rather than a direct
  kWh/GJ comparison; flag this in Phase 4's validation methodology up front
  so it isn't a surprise mid-build.
- **Canada Structures' quality flags are undocumented on the portal** —
  `OSM`/`ODB`/`MSB` source flags and `qltylvl`-style provenance aren't spelled
  out anywhere public; NRCan's "Poor" qltylvl on 100% of the auto-extracted
  tile is a codelist artifact of the Lidar acquisition method, not a red flag,
  per the catalogue PDF — worth a short footnote in Phase 1's README so a
  future reader doesn't misread it as low quality.
- **WebFetch/WAF quirks for this session** (new, append to memory): open.
  canada.ca's resource *download* URLs (not just its CKAN API) need a
  `Referer` header aimed at the dataset page to avoid a WAF rejection —
  User-Agent alone is not enough for those specific URLs, even though the
  dataset HTML page itself loads fine with UA alone. data.ontario.ca's CKAN
  API has no such issue.
