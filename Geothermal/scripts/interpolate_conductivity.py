"""
interpolate_conductivity.py  (guide step 6)

Interpolate a continuous thermal-conductivity surface across Ottawa from the
per-well estimates in ottawa_geothermal.gpkg (wells layer,
estimated_conductivity_wm), using inverse-distance weighting on a 500 m grid.

Cells are only emitted where there is real well coverage (nearest well within
MASK_DIST_M); each cell carries a confidence flag based on how many wells sit
within CONF_DIST_M, so sparsely constrained areas are visibly low-confidence
rather than silently smoothed.

Because IDW is *linear* in the per-well conductivity values, and every well's
value is just its lithology bucket's conductivity, each cell's interpolated
conductivity can be written exactly as a weighted sum over the 14 buckets:

    cell_kappa = Σ_bucket  share_bucket × kappa_bucket

where share_bucket is the sum of that cell's *normalised* IDW weights over the
neighbour wells belonging to that bucket (the shares sum to 1). We emit these
per-cell bucket shares so the map can recompute the whole surface exactly and
instantly when a user edits a bucket's conductivity -- no server, no
re-interpolation. Bucket conductivities come from Data/conductivity_reference.csv
(conductivity.py); CONDUCTIVITY_WM is only a fallback.

Output:
    Data/processed/thermal_conductivity_grid.geojson
        polygon grid with: conductivity_wm, label (low/medium/high),
        confidence (high/low), n_wells, bucket_shares (JSON [[idx,share],..]
        sparse over the 14 buckets, indices per conductivity.BUCKET_ORDER)
    Data/processed/thermal_conductivity_grid.tif
        same surface as a single-band GeoTIFF (EPSG:32618, NaN = no coverage);
        skipped with a warning if rasterio is not installed

Usage:
    python Geothermal/scripts/interpolate_conductivity.py
"""

import json
from pathlib import Path

import numpy as np
import geopandas as gpd
from shapely.geometry import box

from conductivity import load_reference, BUCKET_ORDER
from idw import (make_grid, idw_weights, estimate, count_within,
                 CELL_M, MASK_DIST_M, CONF_DIST_M, CONF_MIN_WELLS)

HERE = Path(__file__).resolve().parents[1]          # Geothermal/
GPKG = HERE / "Data" / "processed" / "ottawa_geothermal.gpkg"
OUT = HERE / "Data" / "processed" / "thermal_conductivity_grid.geojson"
OUT_TIF = HERE / "Data" / "processed" / "thermal_conductivity_grid.tif"

SHARE_MIN = 0.001        # drop bucket shares below this, then renormalise
SHARE_DP = 3             # quantise shares to this many decimals

BBOX = (-76.36, 44.96, -75.24, 45.61)   # Ottawa (guide step 2); drops mis-located wells
CRS_METRIC = 32618        # UTM 18N — Ottawa
# grid + IDW conventions (CELL_M, IDW_K, IDW_POWER, MASK_DIST_M, CONF_DIST_M,
# CONF_MIN_WELLS) are shared with build_difficulty.py via idw.py.


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


def bucket_shares(idx_near, w_near, well_bucket, n_buckets):
    """Per-cell normalised IDW weight share per bucket.

    idx_near   (M, k) neighbour-well indices for the M kept cells
    w_near     (M, k) raw IDW weights
    well_bucket(N,)   bucket index (0..n_buckets-1) of every well
    returns    (M, n_buckets) shares, each row summing to 1.
    """
    s = w_near / w_near.sum(axis=1, keepdims=True)      # (M,k) normalised
    nb = well_bucket[idx_near]                           # (M,k) neighbour buckets
    shares = np.zeros((idx_near.shape[0], n_buckets))
    rows = np.repeat(np.arange(idx_near.shape[0]), idx_near.shape[1])
    np.add.at(shares, (rows, nb.ravel()), s.ravel())
    return shares


def quantise_shares(shares):
    """Round to SHARE_DP, drop shares < SHARE_MIN, renormalise, round again.
    Returns (q, sparse) where q is the dense stored matrix and sparse is a list
    of [[idx, share], ..] per cell (only non-zero buckets)."""
    q = np.round(shares, SHARE_DP)
    q[q < SHARE_MIN] = 0.0
    rowsum = q.sum(axis=1, keepdims=True)
    rowsum[rowsum == 0] = 1.0
    q = np.round(q / rowsum, SHARE_DP)
    sparse = [[[int(b), float(q[i, b])] for b in np.nonzero(q[i])[0]]
              for i in range(q.shape[0])]
    return q, sparse


def main():
    defaults, _ref = load_reference()
    bucket_kappa = np.array([defaults[b] for b in BUCKET_ORDER], float)
    bucket_index = {b: i for i, b in enumerate(BUCKET_ORDER)}

    wells = gpd.read_file(GPKG, layer="wells")
    wells = wells[wells.geometry.notna() & wells["estimated_conductivity_wm"].notna()]
    n0 = len(wells)
    wells = wells.cx[BBOX[0]:BBOX[2], BBOX[1]:BBOX[3]]
    print(f"dropped {n0 - len(wells)} wells outside Ottawa bbox")
    wells = wells.to_crs(CRS_METRIC)
    print(f"wells with conductivity estimate + geometry: {len(wells):,}")

    # every well's bucket (all are known here -- conductivity is notna)
    lith = wells["lithology"].astype(str)
    unknown = ~lith.isin(bucket_index)
    if unknown.any():   # shouldn't happen; a bucketed well always has a kappa
        raise ValueError(f"{unknown.sum()} wells have conductivity but an "
                         f"unmapped lithology: {sorted(lith[unknown].unique())}")
    well_bucket = lith.map(bucket_index).to_numpy(int)
    # conductivity straight from the bucket table -> surface & shares stay
    # exactly consistent (sanity: must match the gpkg column)
    vals = bucket_kappa[well_bucket]
    gpkg_vals = wells["estimated_conductivity_wm"].to_numpy(float)
    if not np.allclose(vals, gpkg_vals, atol=1e-9):
        raise ValueError("bucket-derived conductivity disagrees with the gpkg "
                         "estimated_conductivity_wm -- rerun combine_wells.py "
                         "against the same conductivity_reference.csv")

    xy = np.column_stack([wells.geometry.x, wells.geometry.y])

    centers, xs, ys, shape = make_grid(wells.total_bounds)
    cx = centers[:, 0].reshape(shape)          # for the GeoTIFF writer
    print(f"grid: {len(xs)} x {len(ys)} = {len(centers):,} candidate cells")

    # IDW over k nearest wells (shared conventions in idw.py)
    tree, dist, idx, near, w = idw_weights(xy, centers)
    est = estimate(vals, idx, w)

    # confidence: number of wells within CONF_DIST_M of the cell centre
    n_near = count_within(tree, centers[near], CONF_DIST_M)

    # exact per-bucket weight shares for the kept cells
    shares = bucket_shares(idx[near], w[near], well_bucket, len(BUCKET_ORDER))
    exact_recon = shares @ bucket_kappa
    err_exact = np.abs(exact_recon - est[near]).max()
    print(f"shares reconstruction (pre-quantise) max error: {err_exact:.2e} W/m.K")

    q, sparse = quantise_shares(shares)
    quant_recon = q @ bucket_kappa
    err_quant = np.abs(quant_recon - est[near]).max()
    avg_pairs = np.mean([len(p) for p in sparse])
    print(f"shares reconstruction (quantised, stored) max error: "
          f"{err_quant:.4f} W/m.K  (avg {avg_pairs:.2f} buckets/cell)")
    assert err_quant < 0.01, f"quantised share error {err_quant:.4f} >= 0.01 W/m.K"

    cells, keep_est = [], est[near]
    kept_centers = centers[near]
    for (x, y) in kept_centers:
        cells.append(box(x - CELL_M / 2, y - CELL_M / 2,
                         x + CELL_M / 2, y + CELL_M / 2))

    gdf = gpd.GeoDataFrame({
        "conductivity_wm": np.round(keep_est, 2),
        "n_wells": n_near,
        "confidence": np.where(n_near >= CONF_MIN_WELLS, "high", "low"),
        "bucket_shares": [json.dumps(p, separators=(",", ":")) for p in sparse],
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
