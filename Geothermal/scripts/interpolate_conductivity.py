"""
interpolate_conductivity.py  (guide step 6)

Interpolate a continuous thermal-conductivity surface across Ottawa from the
per-well estimates in ottawa_geothermal.gpkg (wells layer,
estimated_conductivity_wm), using inverse-distance weighting on a 500 m grid.

Cells are only emitted where there is real well coverage (nearest well within
MASK_DIST_M); each cell carries a confidence flag based on how many wells sit
within CONF_DIST_M, so sparsely constrained areas are visibly low-confidence
rather than silently smoothed.

Output:
    Data/processed/thermal_conductivity_grid.geojson
        polygon grid with: conductivity_wm, label (low/medium/high),
        confidence (high/low), n_wells
    Data/processed/thermal_conductivity_grid.tif
        same surface as a single-band GeoTIFF (EPSG:32618, NaN = no coverage);
        skipped with a warning if rasterio is not installed

Usage:
    python Geothermal/scripts/interpolate_conductivity.py
"""

from pathlib import Path

import numpy as np
import geopandas as gpd
from scipy.spatial import cKDTree
from shapely.geometry import box

HERE = Path(__file__).resolve().parents[1]          # Geothermal/
GPKG = HERE / "Data" / "processed" / "ottawa_geothermal.gpkg"
OUT = HERE / "Data" / "processed" / "thermal_conductivity_grid.geojson"
OUT_TIF = HERE / "Data" / "processed" / "thermal_conductivity_grid.tif"

BBOX = (-76.36, 44.96, -75.24, 45.61)   # Ottawa (guide step 2); drops mis-located wells
CRS_METRIC = 32618        # UTM 18N — Ottawa
CELL_M = 500              # guide: 500 m resolution
IDW_K = 12                # neighbours used per cell
IDW_POWER = 2
MASK_DIST_M = 2000        # no cell if nearest well is farther than this
CONF_DIST_M = 1500        # confidence counts wells within this radius
CONF_MIN_WELLS = 5        # >= this many nearby wells -> high confidence


def label(v):
    return "low" if v < 2.0 else ("medium" if v <= 2.8 else "high")


def write_geotiff(est, near, shape, xs, ys):
    try:
        import rasterio
        from rasterio.transform import from_origin
    except ImportError:
        print("rasterio not installed -- skipping GeoTIFF output")
        return
    arr = np.where(near, est, np.nan).reshape(shape).astype("float32")
    arr = np.flipud(arr)                       # rows north -> south
    transform = from_origin(xs[0], ys[-1] + CELL_M, CELL_M, CELL_M)
    with rasterio.open(OUT_TIF, "w", driver="GTiff", height=arr.shape[0],
                       width=arr.shape[1], count=1, dtype="float32",
                       crs=f"EPSG:{CRS_METRIC}", transform=transform,
                       nodata=float("nan"), compress="deflate") as dst:
        dst.write(arr, 1)
    print(f"wrote {OUT_TIF}")


def main():
    wells = gpd.read_file(GPKG, layer="wells")
    wells = wells[wells.geometry.notna() & wells["estimated_conductivity_wm"].notna()]
    n0 = len(wells)
    wells = wells.cx[BBOX[0]:BBOX[2], BBOX[1]:BBOX[3]]
    print(f"dropped {n0 - len(wells)} wells outside Ottawa bbox")
    wells = wells.to_crs(CRS_METRIC)
    print(f"wells with conductivity estimate + geometry: {len(wells):,}")

    xy = np.column_stack([wells.geometry.x, wells.geometry.y])
    vals = wells["estimated_conductivity_wm"].to_numpy(float)
    tree = cKDTree(xy)

    xmin, ymin, xmax, ymax = wells.total_bounds
    xs = np.arange(xmin, xmax + CELL_M, CELL_M)
    ys = np.arange(ymin, ymax + CELL_M, CELL_M)
    cx, cy = np.meshgrid(xs + CELL_M / 2, ys + CELL_M / 2)
    centers = np.column_stack([cx.ravel(), cy.ravel()])
    print(f"grid: {len(xs)} x {len(ys)} = {len(centers):,} candidate cells")

    # IDW over k nearest wells
    dist, idx = tree.query(centers, k=IDW_K)
    near = dist[:, 0] <= MASK_DIST_M           # coverage mask
    w = 1.0 / np.maximum(dist, 1.0) ** IDW_POWER
    est = (w * vals[idx]).sum(axis=1) / w.sum(axis=1)

    # confidence: number of wells within CONF_DIST_M of the cell centre
    n_near = np.array(tree.query_ball_point(centers[near], CONF_DIST_M,
                                            return_length=True))

    cells, keep_est = [], est[near]
    kept_centers = centers[near]
    for (x, y) in kept_centers:
        cells.append(box(x - CELL_M / 2, y - CELL_M / 2,
                         x + CELL_M / 2, y + CELL_M / 2))

    gdf = gpd.GeoDataFrame({
        "conductivity_wm": np.round(keep_est, 2),
        "n_wells": n_near,
        "confidence": np.where(n_near >= CONF_MIN_WELLS, "high", "low"),
    }, geometry=cells, crs=CRS_METRIC)
    gdf["label"] = gdf["conductivity_wm"].map(label)
    gdf = gdf.to_crs(4326)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    gdf.to_file(OUT, driver="GeoJSON")
    write_geotiff(est, near, cx.shape, xs, ys)

    print(f"kept {len(gdf):,} cells with a well within {MASK_DIST_M} m")
    print("label:", gdf["label"].value_counts().to_dict())
    print("confidence:", gdf["confidence"].value_counts().to_dict())
    print(f"conductivity range: {gdf['conductivity_wm'].min():.2f}"
          f" - {gdf['conductivity_wm'].max():.2f} W/m.K")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
