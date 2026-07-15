"""
merge_layers.py  (guide step 7)

Merge the processed layers into a single FeatureCollection where every feature
carries a `layer` property naming its source dataset:

    conductivity_grid          Data/processed/thermal_conductivity_grid.geojson
    difficulty_grid            Data/processed/difficulty_grid.geojson
    suitability_grid           Data/processed/suitability_grid.geojson
    wells                      ottawa_geothermal.gpkg wells layer (points, slimmed)
    grid_capacity              ../GridCapacity/ottawa_capacity.geojson (slimmed +
                               simplified geometry)
    zoning_industrial          Data/processed/zoning_industrial.geojson (step 5)
    sewer_lines                Data/processed/sewer_lines.geojson (step 5)
    city_open_loop_potential   Data/processed/city_open_loop_potential.geojson
                               (City of Ottawa Planning/122 layer)

Wells are clipped to the Ottawa bbox (drops the handful of mis-located
records) and carry only the fields the map popup needs. Grid-capacity
polygons are simplified (~10 m tolerance) and stripped to the capacity
fields; coordinates everywhere are rounded to 5 decimals (~1 m).

Output:
    Data/processed/combined_layers.geojson

Usage:
    python Geothermal/scripts/merge_layers.py
"""

import json
from pathlib import Path

import geopandas as gpd
import pandas as pd

HERE = Path(__file__).resolve().parents[1]              # Geothermal/
GRID = HERE / "Data" / "processed" / "thermal_conductivity_grid.geojson"
DIFF = HERE / "Data" / "processed" / "difficulty_grid.geojson"
SUIT = HERE / "Data" / "processed" / "suitability_grid.geojson"
GPKG = HERE / "Data" / "processed" / "ottawa_geothermal.gpkg"
CAPACITY = HERE.parent / "GridCapacity" / "ottawa_capacity.geojson"
OUT = HERE / "Data" / "processed" / "combined_layers.geojson"

BBOX = (-76.36, 44.96, -75.24, 45.61)

WELL_COLS = {                       # source column -> output property
    "WELL_ID": "well_id",
    "depth_m": "depth_m",
    "bedrock_depth_m": "bedrock_depth_m",
    "static_level_m": "static_level_m",
    "well_yield_lpm": "well_yield_lpm",
    "bedrock_lithology": "bedrock_lithology",
    "primary_lithology": "primary_lithology",
    "lithology": "lithology",
    "estimated_conductivity_wm": "conductivity_wm",
    "estimated_conductivity_class": "conductivity_class",
    "open_loop": "open_loop",
    "geometry_source": "geometry_source",
    "bedrock_depth_source": "bedrock_depth_source",
    "lithology_source": "lithology_source",
}

CAP_COLS = {
    "capacity": "capacity_mva",
    "capacityrange": "capacity_range",
    "configuration": "configuration",
    "feeder_ltl_voltage_3ph": "voltage_kv_3ph",
}


def round_coords(obj, nd=5):
    if isinstance(obj, float):
        return round(obj, nd)
    if isinstance(obj, list):
        return [round_coords(v, nd) for v in obj]
    return obj


def to_features(gdf, layer):
    feats = json.loads(gdf.to_json())["features"]
    for f in feats:
        f["properties"]["layer"] = layer
        f["geometry"]["coordinates"] = round_coords(f["geometry"]["coordinates"])
        f.pop("id", None)
    return feats


def main():
    features = []

    grid = gpd.read_file(GRID)
    features += to_features(grid, "conductivity_grid")
    print(f"conductivity_grid: {len(grid):,} cells")

    if DIFF.exists():
        diff = gpd.read_file(DIFF)
        features += to_features(diff, "difficulty_grid")
        print(f"difficulty_grid: {len(diff):,} cells")
    else:
        print(f"difficulty_grid: missing, skipped ({DIFF.name} not found)")

    if SUIT.exists():
        suit = gpd.read_file(SUIT)
        features += to_features(suit, "suitability_grid")
        print(f"suitability_grid: {len(suit):,} cells")
    else:
        print(f"suitability_grid: missing, skipped ({SUIT.name} not found)")

    wells = gpd.read_file(GPKG, layer="wells")
    wells = wells[wells.geometry.notna()].cx[BBOX[0]:BBOX[2], BBOX[1]:BBOX[3]]
    wells = wells[list(WELL_COLS) + ["geometry"]].rename(columns=WELL_COLS)
    for c in ("depth_m", "bedrock_depth_m", "static_level_m",
              "well_yield_lpm", "conductivity_wm"):
        wells[c] = pd.to_numeric(wells[c], errors="coerce").round(1)
    features += to_features(wells, "wells")
    print(f"wells: {len(wells):,} points "
          f"({wells['open_loop'].value_counts().to_dict()})")

    cap = gpd.read_file(CAPACITY)
    cap = cap[list(CAP_COLS) + ["geometry"]].rename(columns=CAP_COLS)
    cap["capacity_mva"] = pd.to_numeric(cap["capacity_mva"], errors="coerce").round(2)
    cap["geometry"] = cap.geometry.simplify(0.0001, preserve_topology=True)
    features += to_features(cap, "grid_capacity")
    print(f"grid_capacity: {len(cap):,} polygons")

    # step-5 municipal layers (fetch_municipal_layers.py); skip any not fetched
    for name, simplify in [("zoning_industrial", None),
                           ("sewer_lines", None),
                           ("city_open_loop_potential", 0.0001)]:
        path = HERE / "Data" / "processed" / f"{name}.geojson"
        if not path.exists():
            print(f"{name}: missing, skipped ({path.name} not found)")
            continue
        g = gpd.read_file(path)
        if simplify:
            g["geometry"] = g.geometry.simplify(simplify, preserve_topology=True)
        features += to_features(g, name)
        print(f"{name}: {len(g):,} features")

    out = {"type": "FeatureCollection", "features": features}
    OUT.write_text(json.dumps(out, separators=(",", ":"), allow_nan=False),
                   encoding="utf-8")
    print(f"\ntotal features: {len(features):,}")
    print(f"wrote {OUT} ({OUT.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
