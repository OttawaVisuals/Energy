"""
idw.py

Shared inverse-distance-weighting helpers for the geothermal grids. Both
interpolate_conductivity.py (conductivity surface) and build_difficulty.py
(drilling-difficulty surface) grid per-well values onto the same 500 m grid
with identical conventions (k=12 neighbours, power 2, 2 km coverage cutoff),
so the two layers line up cell-for-cell.

Conventions (guide step 6):
    CELL_M        500 m grid resolution, in the metric CRS (UTM 18N)
    IDW_K         12 nearest wells per cell
    IDW_POWER     inverse-distance exponent (2)
    MASK_DIST_M   emit a cell only if the nearest well is within 2 km
    CONF_DIST_M   count wells within 1.5 km for the confidence flag
    CONF_MIN_WELLS  >= this many nearby wells -> "high" confidence

The estimate is linear in the per-well values, which is what lets
interpolate_conductivity.py precompute exact per-bucket weight shares; keep
that in mind before changing the weighting here.
"""

import numpy as np
from scipy.spatial import cKDTree

CELL_M = 500
IDW_K = 12
IDW_POWER = 2
MASK_DIST_M = 2000
CONF_DIST_M = 1500
CONF_MIN_WELLS = 5


def make_grid(bounds, cell_m=CELL_M):
    """Regular cell-centre grid covering `bounds` (xmin, ymin, xmax, ymax).

    Returns (centers, xs, ys, shape):
        centers  (N, 2) cell-centre coordinates, row-major (matches meshgrid)
        xs, ys   the cell lower-left edges along each axis
        shape    the 2-D grid shape (len(ys), len(xs)) for reshaping/rasters
    """
    xmin, ymin, xmax, ymax = bounds
    xs = np.arange(xmin, xmax + cell_m, cell_m)
    ys = np.arange(ymin, ymax + cell_m, cell_m)
    cx, cy = np.meshgrid(xs + cell_m / 2, ys + cell_m / 2)
    centers = np.column_stack([cx.ravel(), cy.ravel()])
    return centers, xs, ys, cx.shape


def idw_weights(well_xy, centers, k=IDW_K, power=IDW_POWER, mask_dist_m=MASK_DIST_M):
    """Nearest-neighbour indices and raw IDW weights for every grid cell.

    Returns (tree, dist, idx, near, w):
        tree   the cKDTree over the wells (reuse for radius counts)
        dist   (N, k) distances to the k nearest wells
        idx    (N, k) those wells' row indices
        near   (N,) coverage mask -- nearest well within mask_dist_m
        w      (N, k) raw weights 1 / max(dist, 1)^power
    """
    tree = cKDTree(well_xy)
    dist, idx = tree.query(centers, k=k)
    near = dist[:, 0] <= mask_dist_m
    w = 1.0 / np.maximum(dist, 1.0) ** power
    return tree, dist, idx, near, w


def estimate(values, idx, w):
    """IDW estimate at every cell: (w . values[idx]) / w.sum, per row."""
    values = np.asarray(values, dtype=float)
    return (w * values[idx]).sum(axis=1) / w.sum(axis=1)


def count_within(tree, centers, radius=CONF_DIST_M):
    """Number of wells within `radius` of each cell centre (for confidence)."""
    return np.asarray(tree.query_ball_point(centers, radius, return_length=True))
