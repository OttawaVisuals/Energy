"""
build_building_stock.py  (HEATDEMAND_PLAN.md Phase 1)

Builds the canonical per-building stock for Ottawa (Ontario side only):
    Data/processed/buildings_ottawa.parquet   (geopandas/pyarrow, one row/bldg)
    Data/processed/buildings_ottawa.gpkg      (same rows, for QGIS spot-checks)

Pipeline (see Geothermal/README.md "Building stock (Phase 1)" section for the
full method writeup):

  1. FOOTPRINT + HEIGHT + TYPE backbone: Canada Structures ON gpkg
     (Data/Raw/CanadaStructures/on_structures_en.gpkg), bbox-clipped to Ottawa
     and read via its embedded Lambert WKT (not an EPSG code -- pyogrio bbox
     filter is applied in the *layer's* CRS, so the Ottawa lon/lat bbox is
     transformed to that CRS first). Height backfilled from the NRCan
     Ottawa-Gatineau LiDAR tile (Data/Raw/NRCanBuildings/...) by nearest
     spatial join -- restricted implicitly to the Ontario side because we only
     backfill buildings that already exist in the ON-only Canada Structures
     backbone (no separate river-boundary clip needed).
  2. CLASS: OSM_Type (direct map for unambiguous residential/commercial/
     institutional/industrial tags) + full zoning ZONE_MAIN (fallback/
     confirmation) + DA dwelling-type mix (probabilistic tiebreak for
     ambiguous/missing tags), weighted by height/footprint evidence.
  3. VINTAGE: probabilistic draw from the building's DA period-of-construction
     mix (da_census.json), fixed seed for reproducibility.
  4. JOINS: 500 m conductivity grid cell (existing thermal_conductivity_grid
     .geojson polygons -- point-in-polygon, no grid rebuild), Hydro Ottawa
     feeder polygon, census DA, FSA.
  5. Filter to footprint_m2 > 40, write outputs, print validation.

Usage:
    python Geothermal/scripts/build_building_stock.py
"""

import json
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import geopandas as gpd
import pyogrio
from pyproj import Transformer
from shapely.geometry import box

warnings.filterwarnings("ignore", category=UserWarning)

HERE = Path(__file__).resolve().parents[1]                    # Geothermal/
RAW = HERE / "Data" / "Raw"
PROC = HERE / "Data" / "processed"
PROC.mkdir(parents=True, exist_ok=True)

CS_GPKG = RAW / "CanadaStructures" / "on_structures_en.gpkg"
NRCAN_GPKG = (RAW / "NRCanBuildings" / "Autobuilding_ON_Ottawa_Gatineau_2020_gpkg"
              / "Autobuilding_ON_Ottawa_Gatineau_2020.gpkg")
ZONING_PATH = RAW / "zoning_full.geojson"
GRID_PATH = PROC / "thermal_conductivity_grid.geojson"
FEEDER_PATH = HERE.parent / "GridCapacity" / "ottawa_capacity.geojson"
DA_BOUNDARY_PATH = PROC / "da_boundaries_ottawa.geojson"
DA_CENSUS_PATH = PROC / "da_census.json"
FSA_PATH = HERE.parent / "FSA_Maps" / "ON.geojson"
FSA_CENSUS_PATH = HERE.parent / "census_json" / "fsa_census.json"

OUT_PARQUET = PROC / "buildings_ottawa.parquet"
OUT_GPKG = PROC / "buildings_ottawa.gpkg"

BBOX_WGS84 = (-76.36, 44.96, -75.24, 45.61)   # same Ottawa bbox as the rest of Geothermal/scripts
CRS_METRIC = 32618                             # UTM 18N
FOOTPRINT_MIN_M2 = 40
SEED = 20260716                                # documented reproducibility seed (today's session date)

# ---------------------------------------------------------------- classes --
CLASSES = ["detached", "row", "lowrise_murb", "highrise_murb",
           "commercial", "institutional", "industrial"]
RESIDENTIAL_CLASSES = ["detached", "row", "lowrise_murb", "highrise_murb"]

# OSM_Type -> direct class (unambiguous)
OSM_DIRECT = {
    "detached": "detached", "house": "detached", "bungalow": "detached",
    "static_caravan": "detached", "cabin": "detached",
    "semidetached_house": "row", "semi": "row", "terrace": "row",
    "commercial": "commercial", "retail": "commercial", "office": "commercial",
    "hotel": "commercial", "warehouse": "commercial", "bank": "commercial",
    "restaurant": "commercial", "kiosk": "commercial", "storage_tank": "commercial",
    "service": "commercial",
    "industrial": "industrial", "barn": "industrial", "farm": "industrial",
    "farm_auxiliary": "industrial", "stable": "industrial", "cowshed": "industrial",
    "silo": "industrial", "greenhouse": "industrial", "riding_hall": "industrial",
    "hangar": "industrial",
    "school": "institutional", "university": "institutional", "college": "institutional",
    "kindergarten": "institutional", "civic": "institutional", "public": "institutional",
    "fire_station": "institutional", "hospital": "institutional",
    "train_station": "institutional", "transportation": "institutional",
    "church": "institutional", "chapel": "institutional", "mosque": "institutional",
    "temple": "institutional", "synagogue": "institutional", "cathedral": "institutional",
    "convent": "institutional", "embassy": "institutional", "military": "institutional",
    "stadium": "institutional", "grandstand": "institutional",
    "sports_centre": "institutional", "toilets": "institutional", "bunker": "institutional",
    "portable_classroom": "institutional", "Former college": "institutional",
}
# ambiguous MURB tags -- height/DA-mix tiebreak decides lowrise vs highrise
OSM_MURB_AMBIGUOUS = {"apartments", "Condominiums", "dormitory"}
# everything else (garage, garages, shed, roof, ruins, no, construction, hut,
# canopy, carport, boathouse, parking, residential, null) carries no usable
# type signal -- falls through to zoning + DA-mix like a missing OSM_Type.

# Zoning ZONE_MAIN -> class (documented after inspecting the full layer's
# 41 distinct values, Geothermal/Data/Raw/zoning_full.geojson; see README)
ZONING_INDUSTRIAL = {"IL", "IG", "IH", "IP", "RG", "RH"}          # per fetch_municipal_layers.py's existing convention
ZONING_INSTITUTIONAL = {"I1", "I2", "RI", "L1", "L2", "L3"}       # institutional + community leisure facility
ZONING_COMMERCIAL = {"AM", "GM", "LC", "MC", "MD", "TD", "TM", "VM", "RC"}
ZONING_RESIDENTIAL = {"R1", "R2", "R3", "R4", "R5", "RR", "RU", "V1", "V2", "V3", "RM"}
ZONING_OTHER_NONRES = {"ME", "MR", "T1", "T2"}                    # extraction/transportation -> industrial, low confidence
# AG, DR, EP, O1, '*_' (agricultural/reserve/open space) are treated as
# "no zoning signal" -> falls through to the residential probabilistic path
# (farmsteads/rural dwellings are common on AG-zoned parcels).

STOREY_DEFAULT = {                       # storeys used when height is fully missing
    "detached": 2, "row": 2, "lowrise_murb": 4, "highrise_murb": 10,
    "commercial": 1, "institutional": 2, "industrial": 1,
}
HEIGHT_PER_STOREY = 3.0                  # m; used both height->storeys and storeys->height


def log(msg):
    print(msg, flush=True)


# --------------------------------------------------------------------------
# 1. Canada Structures backbone
# --------------------------------------------------------------------------
def load_canada_structures():
    log("[1/7] loading Canada Structures backbone (bbox-clipped)...")
    info = pyogrio.read_info(str(CS_GPKG))
    tr = Transformer.from_crs("EPSG:4326", info["crs"], always_xy=True)
    xs, ys = [], []
    for lon in (BBOX_WGS84[0], BBOX_WGS84[2]):
        for lat in (BBOX_WGS84[1], BBOX_WGS84[3]):
            x, y = tr.transform(lon, lat)
            xs.append(x); ys.append(y)
    bbox_native = (min(xs), min(ys), max(xs), max(ys))
    gdf = pyogrio.read_dataframe(str(CS_GPKG), bbox=bbox_native)
    log(f"  {len(gdf):,} features in Ottawa bbox (Province values: "
        f"{gdf['Province'].value_counts().to_dict()})")
    gdf = gdf.to_crs(CRS_METRIC)
    gdf["footprint_m2"] = gdf["Area"].astype(float)
    gdf["height_cs"] = gdf["Height"].astype(float)
    gdf.loc[gdf["height_cs"] <= 0, "height_cs"] = np.nan
    gdf["osm_type"] = gdf["OSM_Type"]
    gdf = gdf.reset_index(drop=True)
    gdf["bldg_id"] = "CS" + gdf["CS_ID"].astype(str)
    return gdf[["bldg_id", "footprint_m2", "height_cs", "osm_type", "geometry"]]


# --------------------------------------------------------------------------
# 2. NRCan LiDAR height backfill
# --------------------------------------------------------------------------
def backfill_height_nrcan(bld):
    log("[2/7] backfilling height from NRCan LiDAR tile (nearest join)...")
    nrcan = pyogrio.read_dataframe(str(NRCAN_GPKG), columns=["heightmax"])
    nrcan = nrcan.to_crs(CRS_METRIC)
    nrcan["height_nrcan"] = nrcan["heightmax"].astype(float)
    nrcan.loc[nrcan["height_nrcan"] <= 0, "height_nrcan"] = np.nan
    nrcan_c = nrcan.copy()
    nrcan_c["geometry"] = nrcan_c.geometry.centroid

    bld_c = bld.copy()
    bld_c["geometry"] = bld.geometry.centroid
    joined = gpd.sjoin_nearest(bld_c[["bldg_id", "geometry"]], nrcan_c[["height_nrcan", "geometry"]],
                                max_distance=15, how="left")
    joined = joined.drop_duplicates("bldg_id")
    bld = bld.merge(joined[["bldg_id", "height_nrcan"]], on="bldg_id", how="left")

    height_m = bld["height_cs"].copy()
    src = np.where(height_m.notna(), "canada_structures", None)
    need = height_m.isna() & bld["height_nrcan"].notna()
    height_m[need] = bld.loc[need, "height_nrcan"]
    src = np.where(bld["height_cs"].notna(), "canada_structures",
          np.where(need, "nrcan_lidar", "default_by_type"))
    bld["height_m"] = height_m
    bld["height_source"] = src
    n_cs = (src == "canada_structures").sum()
    n_nrcan = (src == "nrcan_lidar").sum()
    n_def = (src == "default_by_type").sum()
    tot = len(bld)
    log(f"  height source: canada_structures {n_cs:,} ({n_cs/tot:.1%}), "
        f"nrcan_lidar {n_nrcan:,} ({n_nrcan/tot:.1%}), "
        f"default_by_type (pending class) {n_def:,} ({n_def/tot:.1%})")
    return bld.drop(columns=["height_nrcan"])


# --------------------------------------------------------------------------
# 3. Zoning join
# --------------------------------------------------------------------------
def zoning_class(zone_main):
    if pd.isna(zone_main):
        return None
    z = str(zone_main)
    if z in ZONING_INDUSTRIAL or z in ZONING_OTHER_NONRES:
        return "industrial"
    if z in ZONING_INSTITUTIONAL:
        return "institutional"
    if z in ZONING_COMMERCIAL:
        return "commercial"
    if z in ZONING_RESIDENTIAL:
        return "residential"
    return None   # AG/DR/EP/O1/ME/MR-already-handled/etc -> no signal


def join_zoning(bld):
    log("[3/7] joining full zoning layer (point-in-polygon)...")
    zon = gpd.read_file(ZONING_PATH, columns=["ZONE_MAIN"]).to_crs(CRS_METRIC)
    cent = bld.copy()
    cent["geometry"] = bld.geometry.centroid
    joined = gpd.sjoin(cent[["bldg_id", "geometry"]], zon[["ZONE_MAIN", "geometry"]],
                        predicate="within", how="left")
    joined = joined.drop_duplicates("bldg_id")
    bld = bld.merge(joined[["bldg_id", "ZONE_MAIN"]], on="bldg_id", how="left")
    bld["zoning_class"] = bld["ZONE_MAIN"].map(zoning_class)
    matched = bld["ZONE_MAIN"].notna().sum()
    log(f"  {matched:,}/{len(bld):,} buildings matched a zoning polygon "
        f"({matched/len(bld):.1%})")
    return bld.drop(columns=["ZONE_MAIN"])


# --------------------------------------------------------------------------
# 4. DA join + DA census mix
# --------------------------------------------------------------------------
def join_da(bld):
    log("[4/7] joining census Dissemination Areas...")
    da = gpd.read_file(DA_BOUNDARY_PATH, columns=["DAUID"]).to_crs(CRS_METRIC)
    cent = bld.copy()
    cent["geometry"] = bld.geometry.centroid
    joined = gpd.sjoin(cent[["bldg_id", "geometry"]], da[["DAUID", "geometry"]],
                        predicate="within", how="left")
    joined = joined.drop_duplicates("bldg_id")
    bld = bld.merge(joined[["bldg_id", "DAUID"]], on="bldg_id", how="left")
    bld = bld.rename(columns={"DAUID": "da_id"})
    matched = bld["da_id"].notna().sum()
    log(f"  {matched:,}/{len(bld):,} buildings matched a DA ({matched/len(bld):.1%})")
    return bld


def join_fsa(bld):
    log("[5/7] joining FSA layer...")
    fsa = gpd.read_file(FSA_PATH, columns=["CFSAUID"]).to_crs(CRS_METRIC)
    cent = bld.copy()
    cent["geometry"] = bld.geometry.centroid
    joined = gpd.sjoin(cent[["bldg_id", "geometry"]], fsa[["CFSAUID", "geometry"]],
                        predicate="within", how="left")
    joined = joined.drop_duplicates("bldg_id")
    bld = bld.merge(joined[["bldg_id", "CFSAUID"]], on="bldg_id", how="left")
    bld = bld.rename(columns={"CFSAUID": "fsa"})
    matched = bld["fsa"].notna().sum()
    log(f"  {matched:,}/{len(bld):,} buildings matched an FSA ({matched/len(bld):.1%})")
    return bld


def join_grid_and_feeder(bld):
    log("[6/7] joining conductivity grid cells + Hydro Ottawa feeders...")
    grid = gpd.read_file(GRID_PATH, columns=[]).to_crs(CRS_METRIC)
    grid["grid_cell_id"] = "cell_" + grid.index.astype(str)
    cent = bld.copy()
    cent["geometry"] = bld.geometry.centroid
    joined = gpd.sjoin(cent[["bldg_id", "geometry"]], grid[["grid_cell_id", "geometry"]],
                        predicate="within", how="left")
    joined = joined.drop_duplicates("bldg_id")
    bld = bld.merge(joined[["bldg_id", "grid_cell_id"]], on="bldg_id", how="left")
    matched = bld["grid_cell_id"].notna().sum()
    log(f"  {matched:,}/{len(bld):,} buildings matched a grid cell "
        f"({matched/len(bld):.1%} -- grid is masked to well-covered areas, "
        f"gaps expected outside those)")

    feeder = gpd.read_file(FEEDER_PATH, columns=["objectid"]).to_crs(CRS_METRIC)
    feeder = feeder.rename(columns={"objectid": "feeder_id"})
    joined2 = gpd.sjoin(cent[["bldg_id", "geometry"]], feeder[["feeder_id", "geometry"]],
                         predicate="within", how="left")
    joined2 = joined2.drop_duplicates("bldg_id")
    bld = bld.merge(joined2[["bldg_id", "feeder_id"]], on="bldg_id", how="left")
    matched2 = bld["feeder_id"].notna().sum()
    log(f"  {matched2:,}/{len(bld):,} buildings matched a feeder polygon "
        f"({matched2/len(bld):.1%})")
    return bld


# --------------------------------------------------------------------------
# class + vintage assignment
# --------------------------------------------------------------------------
def load_da_mixes():
    da_census = json.loads(DA_CENSUS_PATH.read_text(encoding="utf-8"))

    dwelling_fields = ["single_detached", "semi_detached", "row_house", "duplex_apt",
                        "apt_low_rise", "apt_high_rise", "other_single_attached", "movable"]
    poc_fields = ["1960_or_before", "1961_1980", "1981_1990", "1991_2000",
                  "2001_2005", "2006_2010", "2011_2015", "2016_2021"]

    dwell_rows, poc_rows, daids = [], [], []
    for daid, rec in da_census.items():
        dt = rec.get("dwelling_type") or {}
        poc = rec.get("period_of_construction") or {}
        dwell_rows.append([dt.get(f) or 0 for f in dwelling_fields])
        poc_rows.append([poc.get(f) or 0 for f in poc_fields])
        daids.append(daid)

    dwell = pd.DataFrame(dwell_rows, columns=dwelling_fields, index=daids)
    poc = pd.DataFrame(poc_rows, columns=poc_fields, index=daids)

    # city-wide fallback shares (for buildings whose DA join failed, or whose
    # DA has an all-zero/suppressed record)
    city_dwell = dwell.sum()
    city_dwell = (city_dwell / city_dwell.sum()) if city_dwell.sum() else city_dwell
    city_poc = poc.sum()
    city_poc = (city_poc / city_poc.sum()) if city_poc.sum() else city_poc

    return dwell, poc, city_dwell, city_poc, dwelling_fields, poc_fields


def dwelling_mix_to_class_weights(dwell_row, city_dwell):
    """single-DA (or city fallback) dwelling-type counts -> 4-way class weight
    vector [detached, row, lowrise_murb, highrise_murb].
    Mapping: detached<-single_detached; row<-semi_detached+row_house+
    other_single_attached+movable (semi-detached shares a wall like a row
    house; other_single_attached/movable are rare, folded in); lowrise_murb<-
    duplex_apt+apt_low_rise; highrise_murb<-apt_high_rise."""
    row = dwell_row if dwell_row.sum() > 0 else city_dwell
    detached = row["single_detached"]
    rowh = row["semi_detached"] + row["row_house"] + row["other_single_attached"] + row["movable"]
    low = row["duplex_apt"] + row["apt_low_rise"]
    high = row["apt_high_rise"]
    w = np.array([detached, rowh, low, high], dtype=float)
    if w.sum() <= 0:
        w = np.array([0.55, 0.25, 0.15, 0.05])   # last-resort Ottawa-ish default
    return w / w.sum()


def assign_class_and_vintage(bld):
    log("[7/7] assigning class (OSM/zoning/DA-mix) and vintage (DA period-of-construction draw)...")
    dwell, poc, city_dwell, city_poc, dwell_fields, poc_fields = load_da_mixes()

    rng = np.random.default_rng(SEED)
    n = len(bld)

    osm = bld["osm_type"]
    direct_class = osm.map(OSM_DIRECT)
    is_murb_ambiguous = osm.isin(OSM_MURB_AMBIGUOUS)
    zoning_cls = bld["zoning_class"]

    height = bld["height_m"].to_numpy(float)  # may still have NaN for defaulted ones
    footprint = bld["footprint_m2"].to_numpy(float)

    # precompute per-building class-weight vectors from DA mix (only needed
    # where class isn't already resolved by OSM_Type)
    da_ids = bld["da_id"].fillna("").to_numpy()
    weight_cache = {}

    def weights_for_da(daid):
        if daid in weight_cache:
            return weight_cache[daid]
        if daid and daid in dwell.index:
            w = dwelling_mix_to_class_weights(dwell.loc[daid], city_dwell)
        else:
            w = dwelling_mix_to_class_weights(pd.Series(0, index=dwell.columns), city_dwell)
        weight_cache[daid] = w
        return w

    final_class = np.empty(n, dtype=object)
    murb_weight_cache = {}

    def murb_weights_for_da(daid):
        if daid in murb_weight_cache:
            return murb_weight_cache[daid]
        if daid and daid in dwell.index:
            row = dwell.loc[daid]
        else:
            row = city_dwell
        low = (row["duplex_apt"] + row["apt_low_rise"]) if row.sum() else city_dwell["duplex_apt"] + city_dwell["apt_low_rise"]
        high = row["apt_high_rise"] if row.sum() else city_dwell["apt_high_rise"]
        w = np.array([low, high], dtype=float)
        if w.sum() <= 0:
            w = np.array([0.7, 0.3])
        w = w / w.sum()
        murb_weight_cache[daid] = w
        return w

    for i in range(n):
        h = height[i]
        fp = footprint[i]
        daid = da_ids[i]

        dc = direct_class[i]
        if pd.notna(dc):
            final_class[i] = dc
            continue

        if is_murb_ambiguous[i]:
            if pd.notna(h) and h >= 15:
                final_class[i] = "highrise_murb"
            elif pd.notna(h) and h >= 9:
                final_class[i] = "lowrise_murb"
            else:
                w = murb_weights_for_da(daid)
                u = rng.random()
                final_class[i] = "lowrise_murb" if u < w[0] else "highrise_murb"
            continue

        zc = zoning_cls[i]
        if zc in ("industrial", "institutional", "commercial"):
            final_class[i] = zc
            continue

        # residential fallback (zoning residential, or no usable zoning signal)
        if pd.notna(h) and h >= 15:
            final_class[i] = "highrise_murb"
            continue
        if pd.notna(h) and h >= 9:
            final_class[i] = "lowrise_murb"
            continue

        w = weights_for_da(daid).copy()
        if fp > 250:   # large footprint with no height evidence -> bias toward MURB tiers
            w[2] *= 3.0
            w[3] *= 3.0
            w = w / w.sum()
        cw = np.cumsum(w)
        u = rng.random()
        idx = int(np.searchsorted(cw, u))
        idx = min(idx, 3)
        final_class[i] = RESIDENTIAL_CLASSES[idx]

    bld["class"] = final_class
    log("  class counts: " + str(pd.Series(final_class).value_counts().to_dict()))

    # ---- storeys / final height (defaults now that class is known) ----
    height_m = bld["height_m"].to_numpy(float).copy()
    height_source = bld["height_source"].to_numpy(object).copy()
    storeys = np.empty(n, dtype=float)
    for i in range(n):
        if pd.notna(height_m[i]):
            storeys[i] = max(1, round(height_m[i] / HEIGHT_PER_STOREY))
        else:
            d = STOREY_DEFAULT[final_class[i]]
            storeys[i] = d
            height_m[i] = d * HEIGHT_PER_STOREY
            height_source[i] = "default_by_type"
    bld["storeys"] = storeys.astype(int)
    bld["height_m"] = height_m
    bld["height_source"] = height_source

    # ---- vintage: probabilistic draw from the DA's period-of-construction mix
    vintage = np.empty(n, dtype=object)
    poc_weight_cache = {}

    def poc_weights_for_da(daid):
        if daid in poc_weight_cache:
            return poc_weight_cache[daid]
        if daid and daid in poc.index and poc.loc[daid].sum() > 0:
            w = poc.loc[daid].to_numpy(float)
        else:
            w = city_poc.to_numpy(float)
        w = w / w.sum()
        poc_weight_cache[daid] = w
        return w

    for i in range(n):
        w = poc_weights_for_da(da_ids[i])
        cw = np.cumsum(w)
        u = rng.random()
        idx = int(np.searchsorted(cw, u))
        idx = min(idx, len(poc_fields) - 1)
        vintage[i] = poc_fields[idx]
    bld["vintage"] = vintage

    return bld


# --------------------------------------------------------------------------
# validation
# --------------------------------------------------------------------------
def validate(bld):
    log("\n=== VALIDATION ===")

    log("\n-- class counts vs census dwelling-type totals --")
    class_counts = bld["class"].value_counts()
    log(class_counts.to_string())

    fsa_census_all = json.loads(FSA_CENSUS_PATH.read_text(encoding="utf-8"))
    # fsa_census.json is keyed by FSA across ALL of Canada/Ontario -- restrict
    # to the FSAs that actually intersect our building set (Ottawa-area FSAs),
    # not the whole province, or the census totals are >30x too large.
    ottawa_fsas = set(bld["fsa"].dropna().unique())
    fsa_census = {k: v for k, v in fsa_census_all.items() if k in ottawa_fsas}
    log(f"cross-checking against {len(fsa_census)} Ottawa-area FSAs "
        f"(of {len(fsa_census_all)} in fsa_census.json)")
    census_detached = sum((v.get("dwelling_type") or {}).get("single_detached") or 0 for v in fsa_census.values())
    census_row = sum(((v.get("dwelling_type") or {}).get("semi_detached") or 0)
                      + ((v.get("dwelling_type") or {}).get("row_house") or 0)
                      for v in fsa_census.values())
    census_apt = sum(((v.get("dwelling_type") or {}).get("duplex_apt") or 0)
                      + ((v.get("dwelling_type") or {}).get("apt_low_rise") or 0)
                      + ((v.get("dwelling_type") or {}).get("apt_high_rise") or 0)
                      for v in fsa_census.values())
    log(f"note: census dwelling COUNTS (occupied private dwellings) are not the "
        f"same denominator as building COUNTS (a MURB is 1 building but many "
        f"dwellings) -- detached/row are ~1:1 building:dwelling so those two are "
        f"the meaningful ±15% checks; apartment buildings vs apartment DWELLINGS "
        f"is expected to differ by roughly the average units/building and is "
        f"reported for context only, not as a ±15% target.")
    bldg_detached = class_counts.get("detached", 0)
    bldg_row = class_counts.get("row", 0)
    bldg_apt = class_counts.get("lowrise_murb", 0) + class_counts.get("highrise_murb", 0)
    for label, b, c in [("detached", bldg_detached, census_detached),
                         ("row/semi", bldg_row, census_row),
                         ("apartment (lowrise+highrise)", bldg_apt, census_apt)]:
        if c:
            pct = (b - c) / c * 100
            log(f"  {label}: buildings={b:,}  census_dwellings={c:,}  delta={pct:+.1f}%")

    log("\n-- storeys distribution --")
    log(bld["storeys"].describe().to_string())
    log(bld["storeys"].value_counts().sort_index().head(20).to_string())

    log("\n-- height source shares --")
    hs = bld["height_source"].value_counts()
    for k, v in hs.items():
        log(f"  {k}: {v:,} ({v/len(bld):.1%})")

    log("\n-- vintage distribution --")
    log(bld["vintage"].value_counts().to_string())

    log("\n-- join coverage --")
    for col in ["grid_cell_id", "feeder_id", "da_id", "fsa"]:
        n_ok = bld[col].notna().sum()
        log(f"  {col}: {n_ok:,}/{len(bld):,} ({n_ok/len(bld):.1%})")


def main():
    bld = load_canada_structures()
    bld = backfill_height_nrcan(bld)
    bld = join_zoning(bld)
    bld = join_da(bld)
    bld = join_fsa(bld)
    bld = join_grid_and_feeder(bld)
    bld = assign_class_and_vintage(bld)

    n0 = len(bld)
    bld = bld[bld["footprint_m2"] > FOOTPRINT_MIN_M2].copy()
    log(f"\nfilter footprint_m2 > {FOOTPRINT_MIN_M2}: {n0:,} -> {len(bld):,} "
        f"({len(bld)/n0:.1%} kept)")

    bld = bld[["bldg_id", "footprint_m2", "height_m", "storeys", "height_source",
               "class", "vintage", "grid_cell_id", "feeder_id", "da_id", "fsa",
               "geometry"]].reset_index(drop=True)

    validate(bld)

    OUT_PARQUET.parent.mkdir(parents=True, exist_ok=True)
    bld_wgs = bld.to_crs(4326)
    bld_wgs.to_parquet(OUT_PARQUET)
    log(f"\nwrote {OUT_PARQUET} ({OUT_PARQUET.stat().st_size/1e6:.1f} MB, {len(bld):,} rows)")
    bld_wgs.to_file(OUT_GPKG, driver="GPKG", layer="buildings")
    log(f"wrote {OUT_GPKG} ({OUT_GPKG.stat().st_size/1e6:.1f} MB)")


if __name__ == "__main__":
    main()
