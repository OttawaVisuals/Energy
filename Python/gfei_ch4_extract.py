"""
Subsets NASA's Global Fuel Exploitation Inventory (GFEI) CH4 v1 2016 grid
(0.1 x 0.1 deg, global, native resolution -- no aggregation) to Canada for
a map on the Heat Pump Explorer page.

Input:  HeatPump/data/raw/Nasa/Global_Fuel_Exploitation_Inventory_GFEI_CH4_v1_2016.nc
        (NASA GES DISC, DOI 10.5067/Q28GFYJYFZ7H, Scarpelli et al. 2020,
        https://doi.org/10.5194/essd-12-563-2020 — public-domain US federal
        data product)
Output: HeatPump/data/processed/gfei_ch4_canada_2016.json

Layers: oil, gas, coal, total fugitive-methane emissions from IPCC 2006
category 1B2 (fuel exploitation) -- wells, pipelines, compressor stations,
storage, processing plants and refineries are all bundled into one number
per fuel type. This is NOT a pipeline-only or transmission-only layer.

Resolved vs background split (per layer, independently): GFEI spreads a
country/region's reported total across cells it can't spatially resolve
using a single shared modelled rate (a proxy mask -- basin extent, well
density, etc.), rather than an independently-estimated per-cell value.
Empirically in Canada this is overwhelmingly a GAS phenomenon: 56% of
nonzero gas cells share an exact float32 value with >=1 other cell (one
value alone repeats across 10,620 cells) -- a coincidence at that scale is
essentially impossible, so a repeated value means "this whole area got one
shared rate," not "we resolved this location." Oil (99.3% unique values)
and coal (86.2% unique) are almost entirely locally resolved by contrast.
A cell is flagged "background" for a given layer if its exact emission
value there is shared by >=1 other nonzero cell of that same layer within
the Canada subset; everything else is "resolved." This is what lets the
page draw resolved cells on the real colour ramp and background cells as a
flat, muted, optionally-hidden wash instead of drowning the map in noise.

Canada cropping: the lat/lon bounding box used to subset the NetCDF still
includes a strip of US territory (Great Lakes south shore, North Dakota,
Maine, etc.) along the border. Cells whose center falls outside a unioned
Canada land-boundary polygon (built in Python/canada_boundary.py from the
FSA geometry already committed for the choropleth maps, plus Yukon
reprojected from the raw national file) are dropped entirely, and a
separately-simplified, much lighter version of the same polygon is shipped
as "canada_outline" for the page to draw as a background reference shape.
"""
import json
import os
import numpy as np
import netCDF4 as nc
import matplotlib.path as mpath
from shapely.geometry import box

import canada_boundary as cb

SRC = "HeatPump/data/raw/Nasa/Global_Fuel_Exploitation_Inventory_GFEI_CH4_v1_2016.nc"
OUT = "HeatPump/data/processed/gfei_ch4_canada_2016.json"

# Masking tolerance/buffer: simplified to roughly the grid's own 0.1deg
# resolution (no point keeping coastline detail finer than the data can
# show), buffered outward slightly so a real Canadian cell right at the
# border/coast isn't dropped just because its center sits a hair outside
# the vector boundary -- favours leniency over pixel-perfect exclusion.
MASK_SIMPLIFY_DEG = 0.02
MASK_BUFFER_DEG = 0.05
MASK_MIN_AREA_DEG2 = 0.005
# Outline tolerance is coarser again -- this is a decorative backdrop, not
# the mask, so small islands and fine coastline detail are dropped to keep
# the shipped JSON small.
OUTLINE_SIMPLIFY_DEG = 0.12
OUTLINE_MIN_AREA_DEG2 = 0.4


def build_canada_mask_path():
    """Path (matplotlib) for point-in-polygon testing, and the lighter
    outline rings for display -- both derived from the same unioned
    Canada geometry, cropped to this script's bbox."""
    geom = cb.build_canada_geometry()
    bbox = box(LON_MIN, LAT_MIN, LON_MAX, LAT_MAX)
    cropped = geom.intersection(bbox)
    mask_geom = cropped.simplify(MASK_SIMPLIFY_DEG, preserve_topology=True).buffer(MASK_BUFFER_DEG)
    mask_rings = cb.simplified_rings(mask_geom, MASK_SIMPLIFY_DEG, min_area_deg2=MASK_MIN_AREA_DEG2)
    outline_rings = cb.simplified_rings(cropped, OUTLINE_SIMPLIFY_DEG, min_area_deg2=OUTLINE_MIN_AREA_DEG2)

    verts, codes = [], []
    for ring in mask_rings:
        verts.append(ring[0]); codes.append(mpath.Path.MOVETO)
        for pt in ring[1:]:
            verts.append(pt); codes.append(mpath.Path.LINETO)
        codes[-1] = mpath.Path.CLOSEPOLY
    path = mpath.Path(np.array(verts), codes)
    return path, outline_rings

LAT_MIN, LAT_MAX = 41.0, 79.0
LON_MIN, LON_MAX = -142.0, -50.0
CELL_DEG = 0.1
FILL = 1e14
LAYERS = ["oil", "gas", "coal", "total"]
LAYER_VAR = {
    "oil": "oil_emis_ch4",
    "gas": "gas_emis_ch4",
    "coal": "coal_emis_ch4",
    "total": "total_fuel_exploitation_emis_ch4",
}
BG_BIT = {"oil": 1, "gas": 2, "coal": 4, "total": 8}
SIG_FIGS = 4


def round_sig(v, sig=SIG_FIGS):
    """Round to N significant figures, not fixed decimal places -- fixed
    decimals (e.g. round(v, 6)) silently zero out ~20% of gas-layer cells,
    whose values span down to ~1e-10: a real, previously undetected drop of
    real records, not a rendering quirk. See METHODOLOGY.md."""
    if v == 0:
        return 0.0
    d = sig - int(np.floor(np.log10(abs(v)))) - 1
    return round(v, d)


def background_mask(arr):
    """True where a nonzero cell's exact value is shared by >=1 other nonzero cell."""
    flat = arr.ravel()
    nz_idx = np.flatnonzero(flat > 0)
    vals = flat[nz_idx]
    _, inverse, counts = np.unique(vals, return_inverse=True, return_counts=True)
    is_bg_nz = counts[inverse] > 1
    bg = np.zeros(flat.shape, dtype=bool)
    bg[nz_idx] = is_bg_nz
    return bg.reshape(arr.shape)


def main():
    ds = nc.Dataset(SRC)
    lat = ds.variables["lat"][:]
    lon = ds.variables["lon"][:]
    lat_mask = (lat >= LAT_MIN) & (lat <= LAT_MAX)
    lon_mask = (lon >= LON_MIN) & (lon <= LON_MAX)
    sub_lat = lat[lat_mask]
    sub_lon = lon[lon_mask]

    def sub(varname):
        a = ds.variables[varname][:][np.ix_(lat_mask, lon_mask)]
        return np.where(a >= FILL, 0.0, a).astype(np.float64)

    layer_arr = {k: sub(LAYER_VAR[k]) for k in LAYERS}
    nrows, ncols = layer_arr["total"].shape

    print("building Canada boundary (one-time, ~2-3 min: FSA union + simplify + buffer)...")
    canada_path, canada_outline = build_canada_mask_path()
    lon_centers = sub_lon[None, :].repeat(nrows, axis=0)
    lat_centers = sub_lat[:, None].repeat(ncols, axis=1)
    pts = np.column_stack([lon_centers.ravel(), lat_centers.ravel()])
    in_canada = canada_path.contains_points(pts).reshape(nrows, ncols)
    dropped_us = 0
    for k in LAYERS:
        before = int((layer_arr[k] > 0).sum())
        layer_arr[k] = np.where(in_canada, layer_arr[k], 0.0)
        after = int((layer_arr[k] > 0).sum())
        if k == "total":
            dropped_us = before - after
    print(f"  {dropped_us} cells outside Canada (mostly US) dropped from 'total'")

    layer_bg = {k: background_mask(layer_arr[k]) for k in LAYERS}
    cells = []
    bg_counts = {k: 0 for k in LAYERS}
    resolved_counts = {k: 0 for k in LAYERS}
    for i in range(nrows):
        for j in range(ncols):
            t = layer_arr["total"][i, j]
            if t <= 0:
                continue
            bitmask = 0
            row = [i, j]
            for k in LAYERS:
                v = layer_arr[k][i, j]
                row.append(round_sig(float(v)) if v > 0 else 0)
                if v > 0:
                    if layer_bg[k][i, j]:
                        bitmask |= BG_BIT[k]
                        bg_counts[k] += 1
                    else:
                        resolved_counts[k] += 1
            row.append(bitmask)
            cells.append(row)

    out = {
        "source": "NASA GES DISC — Global Fuel Exploitation Inventory (GFEI) CH4 v1, 2016",
        "doi": "10.5067/Q28GFYJYFZ7H",
        "reference": "Scarpelli et al. 2020, https://doi.org/10.5194/essd-12-563-2020",
        "vintage_year": 2016,
        "units": "Mg CH4 yr-1 km-2",
        "cell_size_deg": CELL_DEG,
        "lat0": round(float(sub_lat[0]), 4),
        "lon0": round(float(sub_lon[0]), 4),
        "columns": ["row", "col", "oil", "gas", "coal", "total", "bg_bits"],
        "bg_bits": {"oil": BG_BIT["oil"], "gas": BG_BIT["gas"], "coal": BG_BIT["coal"], "total": BG_BIT["total"]},
        "note": (
            "Fugitive methane from oil/gas/coal fuel exploitation (IPCC 2006 cat 1B2), "
            "not combustion. Allocated to infrastructure including mines, wells, "
            "pipelines, compressor stations, storage, processing plants and refineries "
            "-- this is a sector total, not a pipeline-only layer. "
            "lat = lat0 + row*cell_size_deg, lon = lon0 + col*cell_size_deg. "
            "bg_bits: a set bit means that layer's value at this cell is a shared "
            "background/proxy rate (identical to >=1 other cell), not independently "
            "spatially resolved -- see Python/gfei_ch4_extract.py docstring. "
            "canada_outline: simplified [[lon,lat],...] exterior rings (from "
            "geo_json/*.json + Yukon, see Python/canada_boundary.py) for a map "
            "background -- decorative only, not the boundary used to crop cells "
            "to Canada (that uses a separately, more leniently buffered version "
            "of the same geometry)."
        ),
        "canada_outline": canada_outline,
        "cells": cells,
    }

    os.makedirs("HeatPump/data/processed", exist_ok=True)
    with open(OUT, "w") as f:
        json.dump(out, f, separators=(",", ":"))

    print(f"{len(cells)} nonzero cells written to {OUT}")
    for k in LAYERS:
        tot = bg_counts[k] + resolved_counts[k]
        pct = 100 * resolved_counts[k] / tot if tot else 0
        print(f"  {k}: {resolved_counts[k]} resolved / {bg_counts[k]} background ({pct:.1f}% resolved)")
    print(f"file size: {os.path.getsize(OUT)/1024/1024:.2f} MB")


if __name__ == "__main__":
    main()
