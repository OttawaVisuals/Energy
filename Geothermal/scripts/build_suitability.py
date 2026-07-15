"""
build_suitability.py  (v2 Phase D)

Per-segment GSHP suitability scores on the existing 500 m conductivity grid.
The map's single "suitability" reading is replaced by three 0-100 scores that
reflect how differently the three market segments use the ground:

    (1) residential & small commercial (~1-10 tons, 1-3 boreholes ~100-200 m)
    (2) large buildings (50+ tons, borefields)
    (3) district energy (needs demand density + a big resource)

Each score is a weighted sum of normalised 0-1 factors. Because the
conductivity factor is derived from the Phase B per-cell bucket weight-shares
(and IDW is linear in the per-well conductivities), the composites can be
recomputed *exactly* in the browser when a user edits a bucket's conductivity
in the "Conductivity assumptions" panel. So this script emits the per-cell
*factor* values (0-100), and the map computes composites in JS from the
published weight table (map_template.html SEGMENTS) -- the conductivity factor
recomputed live from the shares, everything else static.

Grid basis: the canonical cells are the conductivity grid cells
(thermal_conductivity_grid.geojson), read in file order and emitted in the same
order, so suitability_grid.geojson[i] lines up with the conductivity grid[i]
(and hence the map's GRID[i]/its shares) cell-for-cell.

Factors (each normalised to 0-1 with a documented transform; see README):

    cond      conductivity desirability   (κ_cell - COND_LO)/(COND_HI - COND_LO)
              -- DYNAMIC: recomputed in JS from the bucket shares + edited κ.
              Higher λ -> fewer borehole metres (metres ~ 1/λ).
    drill     drilling ease               1 - difficulty_score/100  (Phase C)
              -- thin overburden + soft/!hard rock = cheaper boreholes.
    openloop  neighbourhood open-loop      viable_share / OPENLOOP_FULL
              -- share of wells within NBR_RADIUS_M that screen open-loop
              "viable" (static level + yield >= 15 L/min): a modest-yield
              groundwater option for small loads.
    yield     neighbourhood aquifer yield  p75(well_yield) / YIELD_FULL_LPM
              -- 75th-pct nearby pump-test/well yield: a *big* groundwater
              resource for district-scale open-loop / standing-column.
    feeder    electrical feeder headroom   capacity_mva / FEEDER_FULL_MVA
              -- Hydro Ottawa feeder available capacity at the cell (GridCapacity).
    zone      employment-land bonus        1 if cell in industrial/employment
              zoning else 0 -- land availability for a borefield/plant.
    sewer     trunk-sewer proximity        1 - dist_to_trunk_sewer / SEWER_FULL_M
              -- wastewater heat-recovery option for district energy.
    demand    heat-demand density (proxy)  1 if cell in the City's serviced
              urban area (Planning/122 potential polygons) else 0.
              *** Coarse proxy *** until Data/processed/heat_demand_grid.geojson
              (ROADMAP item 7) exists -- see DEMAND_SOURCE below (upgrade hook).

Segment weight table (sums to 1 per segment; mirrored in map_template.html):

    residential : drill .55  cond .30  openloop .15
    large       : cond  .45  drill .25  feeder   .20  zone .10
    district    : demand .35 yield .20  sewer    .20  feeder .15  zone .10

Output:
    Data/processed/suitability_grid.geojson
        polygon grid (== conductivity cells) with the 8 factor columns
        (f_* as 0-1) plus s_res / s_large / s_district composites (0-100, from
        default κ) and confidence -- the map re-derives composites in JS.

Usage:
    python Geothermal/scripts/build_suitability.py
"""

import json
from pathlib import Path

import numpy as np
import geopandas as gpd
import pandas as pd
from scipy.spatial import cKDTree

from conductivity import load_reference, BUCKET_ORDER

HERE = Path(__file__).resolve().parents[1]              # Geothermal/
COND = HERE / "Data" / "processed" / "thermal_conductivity_grid.geojson"
DIFF = HERE / "Data" / "processed" / "difficulty_grid.geojson"
GPKG = HERE / "Data" / "processed" / "ottawa_geothermal.gpkg"
CAPACITY = HERE.parent / "GridCapacity" / "ottawa_capacity.geojson"
ZONING = HERE / "Data" / "processed" / "zoning_industrial.geojson"
SEWERS = HERE / "Data" / "processed" / "sewer_lines.geojson"
CITYPOT = HERE / "Data" / "processed" / "city_open_loop_potential.geojson"
HEATDEMAND = HERE / "Data" / "processed" / "heat_demand_grid.geojson"   # ROADMAP item 7
OUT = HERE / "Data" / "processed" / "suitability_grid.geojson"

BBOX = (-76.36, 44.96, -75.24, 45.61)
CRS_METRIC = 32618                        # UTM 18N

# --- factor transforms (documented in README §3.9) -----------------------
COND_LO, COND_HI = 1.2, 3.2      # κ (W/m·K) mapped to 0..1 (observed surface 1.4-3.2)
NBR_RADIUS_M = 1500              # neighbourhood radius for well-derived factors
OPENLOOP_FULL = 0.5             # viable-share at/above which the open-loop factor maxes
YIELD_FULL_LPM = 100.0          # neighbourhood p75 yield at/above which yield maxes
FEEDER_FULL_MVA = 5.0           # feeder headroom at/above which the feeder factor maxes
SEWER_FULL_M = 1000.0           # trunk-sewer distance at/beyond which the factor is 0

# --- segment weight table (sums to 1; mirror of map_template.html SEGMENTS) ---
WEIGHTS = {
    "res":      {"drill": 0.55, "cond": 0.30, "openloop": 0.15},
    "large":    {"cond": 0.45, "drill": 0.25, "feeder": 0.20, "zone": 0.10},
    "district": {"demand": 0.35, "yield": 0.20, "sewer": 0.20,
                 "feeder": 0.15, "zone": 0.10},
}
FACTORS = ["cond", "drill", "openloop", "yield", "feeder", "zone", "sewer", "demand"]


def clip01(a):
    return np.clip(a, 0.0, 1.0)


def load_grid():
    """Conductivity grid cells (canonical), in file order. Returns the GeoDataFrame
    plus projected centroids and a default-κ conductivity per cell (for sanity /
    the stored composite; the map recomputes cond live from the shares)."""
    g = gpd.read_file(COND)
    print(f"  conductivity grid: {len(g):,} cells (canonical suitability cells)")
    defaults, _ = load_reference()
    kappa = {b: defaults[b] for b in BUCKET_ORDER}
    cond = np.empty(len(g))
    for i, sj in enumerate(g["bucket_shares"].to_numpy()):
        pairs = sj if isinstance(sj, list) else json.loads(sj)
        cond[i] = sum(s * kappa[BUCKET_ORDER[idx]] for idx, s in pairs)
    cen = g.geometry.centroid                      # lon/lat centroids (fine at this scale)
    cen_m = cen.to_crs(CRS_METRIC)
    xy = np.column_stack([cen_m.x.to_numpy(), cen_m.y.to_numpy()])
    return g, cen, cen_m, xy, cond


def f_drill(cen_m):
    """1 - difficulty_score/100, joined from the Phase C difficulty grid by
    point-in-cell (cond centroid within a difficulty cell); nearest cell within
    750 m as a fallback, else the grid-wide median ease. All in projected CRS."""
    d = gpd.read_file(DIFF)[["difficulty_score", "geometry"]].to_crs(CRS_METRIC)
    pts = gpd.GeoDataFrame({"_row": np.arange(len(cen_m))},
                           geometry=cen_m.values, crs=CRS_METRIC)
    j = gpd.sjoin(pts, d, how="left", predicate="within")
    score = np.array(j.groupby("_row")["difficulty_score"].first()
                     .reindex(range(len(cen_m))).to_numpy(float))
    miss = np.isnan(score)
    if miss.any():                                 # nearest difficulty cell <= 750 m
        jn = gpd.sjoin_nearest(pts[miss], d, how="left", max_distance=750)
        near = jn.groupby("_row")["difficulty_score"].first()
        score[near.index.to_numpy()] = near.to_numpy(float)
    n_med = int(np.isnan(score).sum())
    med = np.nanmedian(score)
    score = np.where(np.isnan(score), med, score)
    print(f"  drill: joined difficulty to {len(score) - n_med:,} cells; "
          f"{n_med:,} fell back to median ease ({med:.0f})")
    return clip01(1.0 - score / 100.0)


def f_well_factors(xy):
    """Neighbourhood open-loop (viable share) and aquifer-yield (p75) factors."""
    w = gpd.read_file(GPKG, layer="wells")
    w = w[w.geometry.notna()].cx[BBOX[0]:BBOX[2], BBOX[1]:BBOX[3]].to_crs(CRS_METRIC)
    wxy = np.column_stack([w.geometry.x, w.geometry.y])
    viable = (w["open_loop"].to_numpy() == "viable").astype(float)
    yld = pd.to_numeric(w["well_yield_lpm"], errors="coerce").to_numpy(float)

    tree = cKDTree(wxy)
    nbrs = tree.query_ball_point(xy, NBR_RADIUS_M)
    vshare = np.zeros(len(xy))
    p75 = np.zeros(len(xy))
    for i, nb in enumerate(nbrs):
        if not nb:
            continue
        vshare[i] = viable[nb].mean()
        yy = yld[nb]
        yy = yy[~np.isnan(yy)]
        if yy.size:
            p75[i] = np.percentile(yy, 75)
    print(f"  wells: {len(w):,} in bbox; neighbourhood radius {NBR_RADIUS_M} m "
          f"(mean {np.mean([len(nb) for nb in nbrs]):.0f} wells/cell)")
    return clip01(vshare / OPENLOOP_FULL), clip01(p75 / YIELD_FULL_LPM)


def f_from_polys(cen, path, value_col=None, agg="max"):
    """Point-in-polygon join of cell centroids to a polygon layer. Returns the
    joined numeric `value_col` (NaN where no polygon) or a 0/1 membership array
    when value_col is None. `agg` handles overlapping polygons."""
    if not path.exists():
        print(f"  [warn] {path.name} missing -> factor all-zero")
        return np.zeros(len(cen))
    poly = gpd.read_file(path)
    cols = ["geometry"] + ([value_col] if value_col else [])
    pts = gpd.GeoDataFrame(geometry=cen.values, crs=cen.crs)
    pts["_row"] = np.arange(len(pts))
    j = gpd.sjoin(pts, poly[cols], how="left", predicate="within")
    matched = j.dropna(subset=["index_right"])     # left join keeps non-matches
    if value_col:
        v = pd.to_numeric(matched[value_col], errors="coerce")
        s = v.groupby(matched["_row"]).agg(agg).reindex(range(len(cen)))
        return s.to_numpy(float)
    hit = matched.groupby("_row").size().reindex(range(len(cen))).fillna(0)
    return (hit.to_numpy() > 0).astype(float)


def f_sewer(xy):
    """1 - dist(cell, nearest trunk sewer)/SEWER_FULL_M. Trunk = combined sewers +
    non-LOCAL sanitary (same subset the map embeds)."""
    if not SEWERS.exists():
        print(f"  [warn] {SEWERS.name} missing -> sewer factor all-zero")
        return np.zeros(len(xy))
    with open(SEWERS, encoding="utf-8") as f:
        feats = json.load(f)["features"]
    pts = []
    for ft in feats:
        p = ft["properties"]
        if p.get("kind") == "sanitary" and (p.get("FUNCTION") or "LOCAL") == "LOCAL":
            continue
        g = ft["geometry"]
        if g is None:
            continue
        lines = [g["coordinates"]] if g["type"] == "LineString" else g["coordinates"]
        for ln in lines:
            pts.extend(ln)
    if not pts:
        return np.zeros(len(xy))
    sew = gpd.GeoSeries(gpd.points_from_xy([p[0] for p in pts], [p[1] for p in pts]),
                        crs=4326).to_crs(CRS_METRIC)
    sxy = np.column_stack([sew.x.to_numpy(), sew.y.to_numpy()])
    dist, _ = cKDTree(sxy).query(xy, k=1)
    print(f"  sewer: {len(sxy):,} trunk/combined vertices; "
          f"{int((dist <= SEWER_FULL_M).sum()):,} cells within {SEWER_FULL_M:.0f} m")
    return clip01(1.0 - dist / SEWER_FULL_M)


def composites(F):
    """0-100 composite per segment from the factor dict F (default-κ cond)."""
    out = {}
    for seg, wts in WEIGHTS.items():
        out[seg] = 100.0 * sum(wts[f] * F[f] for f in wts)
    return out


def validate(F, comp, cen):
    print("\n== Validation ==")
    lon = np.array([c.x for c in cen])
    S = {k: np.asarray(v) for k, v in comp.items()}

    # (1) inter-segment correlations -- all > 0.95 == redundant weights
    print("(1) inter-segment score correlations (want NOT all > 0.95):")
    names = {"res": "residential", "large": "large", "district": "district"}
    for a, b in [("res", "large"), ("res", "district"), ("large", "district")]:
        r = np.corrcoef(S[a], S[b])[0, 1]
        flag = "  <-- REDUNDANT" if r > 0.95 else ""
        print(f"    {names[a]:11s} vs {names[b]:11s}: {r:+.3f}{flag}")

    # (2) top-decile district cells: should sit in the serviced urban area, near
    #     trunk sewers
    dcut = np.percentile(S["district"], 90)
    top = S["district"] >= dcut
    print(f"\n(2) district-energy top decile (score >= {dcut:.0f}, n={top.sum():,}):")
    print(f"    in serviced urban area (demand proxy): "
          f"{100 * F['demand'][top].mean():.0f}% (all cells {100 * F['demand'].mean():.0f}%)")
    print(f"    mean trunk-sewer proximity factor: "
          f"{F['sewer'][top].mean():.2f} (all cells {F['sewer'].mean():.2f})")
    print(f"    mean feeder-headroom factor: "
          f"{F['feeder'][top].mean():.2f} (all cells {F['feeder'].mean():.2f})")

    # (3) top-decile residential cells: should NOT concentrate downtown
    rcut = np.percentile(S["res"], 90)
    rtop = S["res"] >= rcut
    # downtown ~ within ~4 km of Parliament (-75.70, 45.42) -> here just check the
    # dense urban core longitude/lat box and the serviced-area share
    core = (np.abs(lon + 75.70) < 0.05) & \
           (np.abs(np.array([c.y for c in cen]) - 45.41) < 0.04)
    print(f"\n(3) residential top decile (score >= {rcut:.0f}, n={rtop.sum():,}):")
    print(f"    share inside the downtown core box: "
          f"{100 * (rtop & core).sum() / rtop.sum():.1f}% "
          f"(downtown is {100 * core.mean():.1f}% of all cells)")
    print(f"    in serviced urban area: {100 * F['demand'][rtop].mean():.0f}% "
          f"(all cells {100 * F['demand'].mean():.0f}%) -- expect at/below baseline")
    print(f"    mean drilling-ease factor: {F['drill'][rtop].mean():.2f} "
          f"(all cells {F['drill'].mean():.2f}) -- expect above baseline")


def main():
    print("== Building per-segment suitability ==")
    g, cen, cen_m, xy, cond = load_grid()

    F = {}
    F["cond"] = clip01((cond - COND_LO) / (COND_HI - COND_LO))
    F["drill"] = f_drill(cen_m)
    F["openloop"], F["yield"] = f_well_factors(xy)
    mva = f_from_polys(cen, CAPACITY, "capacity", agg="max")
    F["feeder"] = clip01(np.nan_to_num(mva, nan=0.0) / FEEDER_FULL_MVA)
    F["zone"] = f_from_polys(cen, ZONING)
    F["sewer"] = f_sewer(xy)

    if HEATDEMAND.exists():
        print("  demand: using heat_demand_grid.geojson (ROADMAP item 7)")
        # upgrade hook: normalise per-cell kWh/yr to 0-1. Left unimplemented until
        # the layer exists; fall through to the proxy below if columns differ.
        dm = f_from_polys(cen, HEATDEMAND, "kwh_yr", agg="max")
        F["demand"] = clip01(np.nan_to_num(dm, nan=0.0) /
                             max(np.nanpercentile(dm, 95), 1.0))
        demand_src = "heat_demand_grid.geojson"
    else:
        print("  demand: heat_demand_grid.geojson absent -> City serviced-area proxy "
              "(upgrade hook, README §3.9)")
        F["demand"] = f_from_polys(cen, CITYPOT)     # 1 inside any Planning/122 polygon
        demand_src = "city_open_loop_potential (proxy)"

    for f in FACTORS:
        F[f] = np.asarray(F[f], float)
        print(f"  factor {f:9s}: mean {F[f].mean():.2f}  "
              f">0 in {int((F[f] > 0).sum()):,}/{len(F[f]):,} cells")

    comp = composites(F)
    for seg in WEIGHTS:
        s = comp[seg]
        print(f"  score {seg:9s}: min {s.min():.0f}  median {np.median(s):.0f}  "
              f"mean {s.mean():.1f}  max {s.max():.0f}")

    validate(F, comp, cen)

    # --- emit (same order/geometry as the conductivity grid) ---
    out = g[["geometry", "confidence"]].copy()
    for f in FACTORS:
        out["f_" + f] = np.round(F[f], 3)
    out["s_res"] = np.round(comp["res"]).astype(int)
    out["s_large"] = np.round(comp["large"]).astype(int)
    out["s_district"] = np.round(comp["district"]).astype(int)
    out.attrs["demand_source"] = demand_src
    OUT.parent.mkdir(parents=True, exist_ok=True)
    out.to_file(OUT, driver="GeoJSON")
    print(f"\nwrote {OUT} ({OUT.stat().st_size / 1e6:.1f} MB), demand source: {demand_src}")


if __name__ == "__main__":
    main()
