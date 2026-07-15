"""
build_map.py  (guide step 8)

Build a single self-contained interactive map, Geothermal/output/index.html,
from the processed layers. Leaflet comes from a CDN; all data is embedded
inline so the file opens straight from disk.

To keep the file size sane the two big layers are embedded as compact arrays
instead of GeoJSON (the full-fidelity GeoJSON deliverables remain in
Data/processed/):

    conductivity grid  [w, s, e, n, high_confidence, shares] per cell, where
                       shares is a sparse [[bucket_idx, weight_share], ..] list
                       (bucket_idx per conductivity.BUCKET_ORDER, 0-13). The
                       cell conductivity is recomputed in the browser as
                       Σ share × κ(bucket), so editing a bucket's κ in the
                       "Conductivity assumptions" panel updates the whole
                       surface exactly and instantly.
    wells              [lon, lat, open_loop, yield_lpm, static_m, depth_m,
                        bedrock_m, bucket_idx, well_id, geometry_source_idx,
                        bedrock_depth_source_idx, lithology_source_idx]
                        (bucket_idx 0-13 per BUCKET_ORDER, -1 = unknown; the
                        well's conductivity is recomputed from κ(bucket) at
                        popup-open time. source idx 0/1/2 -> GS/BS/LS in
                        map_template.html)
    sewers             [kind, function, material, width_mm, year, [[x,y],..]]
                       - only trunk sanitary (FUNCTION <> LOCAL) + all combined
                       sewers are embedded; the full network incl. local
                       laterals stays in Data/processed/sewer_lines.geojson

Grid capacity, industrial zoning and the City's open-loop-potential layer stay
as (simplified) GeoJSON since the polygons are irregular. Step-5 layers are
skipped gracefully if fetch_municipal_layers.py hasn't been run.

Usage:
    python Geothermal/scripts/build_map.py
"""

import json
from pathlib import Path

import geopandas as gpd
import pandas as pd

from conductivity import load_reference, BUCKET_ORDER

HERE = Path(__file__).resolve().parents[1]              # Geothermal/
GRID = HERE / "Data" / "processed" / "thermal_conductivity_grid.geojson"
DIFF = HERE / "Data" / "processed" / "difficulty_grid.geojson"
SUIT = HERE / "Data" / "processed" / "suitability_grid.geojson"
GPKG = HERE / "Data" / "processed" / "ottawa_geothermal.gpkg"
CAPACITY = HERE.parent / "GridCapacity" / "ottawa_capacity.geojson"
OUT = HERE / "output" / "index.html"

BBOX = (-76.36, 44.96, -75.24, 45.61)
OPEN_LOOP = {"viable": 2, "possible": 1, "unlikely": 0}
GEOM_SRC = {"shp": 0, "borehole": 1}
BEDROCK_SRC = {None: 0, "shp": 1, "formations": 2}
LITH_SRC = {None: 0, "well_log": 1, "gsc_map": 2}


def jnum(v, nd):
    return None if pd.isna(v) else round(float(v), nd)


def build_grid():
    g = gpd.read_file(GRID)
    cells = []
    for geom, conf, shares_json in zip(g.geometry, g["confidence"], g["bucket_shares"]):
        w, s, e, n = geom.bounds
        # GDAL's GeoJSON reader may auto-parse the JSON-string field into a list
        shares = shares_json if isinstance(shares_json, list) else json.loads(shares_json)
        cells.append([round(w, 4), round(s, 4), round(e, 4), round(n, 4),
                      1 if conf == "high" else 0, shares])
    return cells


# difficulty grid: static per-cell screening score + component breakdown.
# [w, s, e, n, high_confidence, score, overburden_pts, problem_pts,
#  hardness_pts, artesian_pts] -- class and dominant driver are derived in the
# browser (see map_template.html), so nothing here is recomputed client-side.
def build_difficulty():
    if not DIFF.exists():
        return None
    g = gpd.read_file(DIFF)
    cells = []
    for geom, conf, sc, ov, pr, hd, ar in zip(
            g.geometry, g["confidence"], g["difficulty_score"],
            g["overburden_pts"], g["problem_pts"], g["hardness_pts"],
            g["artesian_pts"]):
        w, s, e, n = geom.bounds
        cells.append([round(w, 4), round(s, 4), round(e, 4), round(n, 4),
                      1 if conf == "high" else 0, int(sc),
                      int(ov), int(pr), int(hd), int(ar)])
    return cells


# per-segment suitability: 7 STATIC factors per cell (0-100), index-aligned with
# GRID (suitability cells == conductivity cells, same file order). The 8th factor,
# conductivity, is recomputed live in the browser from GRID's bucket shares, so
# it isn't stored here. Order == map_template.html SUIT_FACTORS.
# [drill, openloop, yield, feeder, zone, sewer, demand]
SUIT_FACTORS = ["f_drill", "f_openloop", "f_yield", "f_feeder", "f_zone",
                "f_sewer", "f_demand"]


def build_suitability(n_grid):
    if not SUIT.exists():
        return None
    g = gpd.read_file(SUIT)
    if len(g) != n_grid:
        raise ValueError(f"suitability grid ({len(g)}) != conductivity grid "
                         f"({n_grid}) -- rerun build_suitability.py so they align")
    rows = []
    for tup in zip(*[g[c].to_numpy() for c in SUIT_FACTORS]):
        rows.append([int(round(float(v) * 100)) for v in tup])
    return rows


def build_wells():
    w = gpd.read_file(GPKG, layer="wells")
    w = w[w.geometry.notna()].cx[BBOX[0]:BBOX[2], BBOX[1]:BBOX[3]]
    bidx = {b: i for i, b in enumerate(BUCKET_ORDER)}
    lith = w["lithology"].fillna("unknown")
    rows = []
    for geom, ol, yld, stat, dep, bed, li, wid, gs, bs, ls in zip(
            w.geometry, w["open_loop"], w["well_yield_lpm"], w["static_level_m"],
            w["depth_m"], w["bedrock_depth_m"], lith, w["WELL_ID"],
            w["geometry_source"], w["bedrock_depth_source"], w["lithology_source"]):
        rows.append([round(geom.x, 5), round(geom.y, 5), OPEN_LOOP.get(ol, 0),
                     jnum(yld, 0), jnum(stat, 1), jnum(dep, 1), jnum(bed, 1),
                     bidx.get(li, -1), str(wid),
                     GEOM_SRC.get(gs, 0), BEDROCK_SRC.get(bs, 0), LITH_SRC.get(ls, 0)])
    return rows


def slim_geojson(gdf):
    # 4 dp (~10 m) matches the ~10 m geometry simplification applied to these
    # polygon layers, so the extra 5th-decimal digit is noise -- dropping it
    # trims the embedded size with no visible change on a 500 m screening map.
    gj = json.loads(gdf.to_json())
    for f in gj["features"]:
        f.pop("id", None)

        def rnd(c):
            return [rnd(x) for x in c] if isinstance(c, list) else round(c, 4)
        f["geometry"]["coordinates"] = rnd(f["geometry"]["coordinates"])
    return gj


def build_capacity():
    cap = gpd.read_file(CAPACITY)
    keep = {"capacity": "mva", "capacityrange": "range",
            "configuration": "config", "feeder_ltl_voltage_3ph": "kv"}
    cap = cap[list(keep) + ["geometry"]].rename(columns=keep)
    cap["mva"] = pd.to_numeric(cap["mva"], errors="coerce").round(2)
    cap["geometry"] = cap.geometry.simplify(0.0001, preserve_topology=True)
    return slim_geojson(cap)


# canonical bylaw 2008-250 names; the service's ZNAME_EN group label is wrong
# for IG (says "Transportation Zones"; Part 11 s.199 defines IG as industrial)
ZONE_NAME = {
    "IL": "Light Industrial", "IG": "General Industrial",
    "IH": "Heavy Industrial", "IP": "Business Park Industrial",
    "RG": "Rural General Industrial", "RH": "Rural Heavy Industrial",
}


def build_zoning():
    path = HERE / "Data" / "processed" / "zoning_industrial.geojson"
    if not path.exists():
        return None
    z = gpd.read_file(path)[["ZONE_CODE", "ZONE_MAIN", "geometry"]]
    z["name"] = z["ZONE_MAIN"].map(ZONE_NAME).fillna("Industrial")
    z = z[["ZONE_CODE", "name", "geometry"]].rename(columns={"ZONE_CODE": "code"})
    z["geometry"] = z.geometry.simplify(0.00005, preserve_topology=True)
    return slim_geojson(z)


def build_city_potential():
    path = HERE / "Data" / "processed" / "city_open_loop_potential.geojson"
    if not path.exists():
        return None
    p = gpd.read_file(path)[["POTENTIAL_EN", "geometry"]]
    p.columns = ["potential", "geometry"]
    p["geometry"] = p.geometry.simplify(0.0001, preserve_topology=True)
    return slim_geojson(p)


def build_sewers():
    path = HERE / "Data" / "processed" / "sewer_lines.geojson"
    if not path.exists():
        return None
    with open(path, encoding="utf-8") as f:
        feats = json.load(f)["features"]
    rows = []
    for f in feats:
        p = f["properties"]
        if p["kind"] == "sanitary" and (p.get("FUNCTION") or "LOCAL") == "LOCAL":
            continue                    # laterals: too many to embed
        g = f["geometry"]
        if g is None:
            continue
        paths = [g["coordinates"]] if g["type"] == "LineString" else g["coordinates"]
        for path_coords in paths:
            rows.append([
                0 if p["kind"] == "sanitary" else 1,
                p.get("FUNCTION") or "?",
                p.get("MATERIAL") or "?",
                jnum(p.get("WIDTH"), 0),
                jnum(p.get("INSTALL_YEAR"), 0),
                [[round(x, 5), round(y, 5)] for x, y in path_coords],
            ])
    return rows


def build_cond_ref():
    """Literature-sourced per-bucket conductivity table for the map UI, in
    canonical BUCKET_ORDER (so index == the bucket id used in GRID/WELLS)."""
    defaults, ref = load_reference()
    out = []
    for b in BUCKET_ORDER:
        r = ref[b] if ref and b in ref else {
            "default": defaults[b], "min": defaults[b], "max": defaults[b],
            "source": "", "notes": ""}
        out.append({"bucket": b, "default": r["default"], "min": r["min"],
                    "max": r["max"], "source": r["source"], "notes": r["notes"]})
    return out


def main():
    grid = build_grid()
    wells = build_wells()
    capacity = build_capacity()

    empty_fc = {"type": "FeatureCollection", "features": []}
    blobs = {
        "GRID": json.dumps(grid, separators=(",", ":")),
        "DIFF": json.dumps(build_difficulty() or [], separators=(",", ":")),
        "SUIT": json.dumps(build_suitability(len(grid)) or [], separators=(",", ":")),
        "WELLS": json.dumps(wells, separators=(",", ":")),
        "BUCKETS": json.dumps(BUCKET_ORDER, separators=(",", ":")),
        "CONDREF": json.dumps(build_cond_ref(), separators=(",", ":")),
        "CAPACITY": json.dumps(capacity, separators=(",", ":")),
        "ZONING": json.dumps(build_zoning() or empty_fc, separators=(",", ":")),
        "CITYPOT": json.dumps(build_city_potential() or empty_fc, separators=(",", ":")),
        "SEWERS": json.dumps(build_sewers() or [], separators=(",", ":")),
    }
    for k, v in blobs.items():
        print(f"{k}: {len(v) / 1e6:.1f} MB")

    template = (HERE / "scripts" / "map_template.html").read_text(encoding="utf-8")
    html = template
    for k, v in blobs.items():
        html = html.replace(f"/*__{k}__*/", v)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(html, encoding="utf-8")
    print(f"wrote {OUT} ({OUT.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
