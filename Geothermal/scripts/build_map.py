"""
build_map.py  (guide step 8)

Build a single self-contained interactive map, Geothermal/output/index.html,
from the processed layers. Leaflet comes from a CDN; all data is embedded
inline so the file opens straight from disk.

To keep the file size sane the two big layers are embedded as compact arrays
instead of GeoJSON (the full-fidelity GeoJSON deliverables remain in
Data/processed/):

    conductivity grid  [w, s, e, n, conductivity, high_confidence] per cell
    wells              [lon, lat, open_loop, conductivity, yield_lpm,
                        static_m, depth_m, bedrock_m, lithology_idx, well_id]
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

HERE = Path(__file__).resolve().parents[1]              # Geothermal/
GRID = HERE / "Data" / "processed" / "thermal_conductivity_grid.geojson"
GPKG = HERE / "Data" / "processed" / "ottawa_geothermal.gpkg"
CAPACITY = HERE.parent / "GridCapacity" / "ottawa_capacity.geojson"
OUT = HERE / "output" / "index.html"

BBOX = (-76.36, 44.96, -75.24, 45.61)
OPEN_LOOP = {"viable": 2, "possible": 1, "unlikely": 0}


def jnum(v, nd):
    return None if pd.isna(v) else round(float(v), nd)


def build_grid():
    g = gpd.read_file(GRID)
    cells = []
    for geom, cond, conf in zip(g.geometry, g["conductivity_wm"], g["confidence"]):
        w, s, e, n = geom.bounds
        cells.append([round(w, 4), round(s, 4), round(e, 4), round(n, 4),
                      round(float(cond), 2), 1 if conf == "high" else 0])
    return cells


def build_wells():
    w = gpd.read_file(GPKG, layer="wells")
    w = w[w.geometry.notna()].cx[BBOX[0]:BBOX[2], BBOX[1]:BBOX[3]]
    lith = w["bedrock_lithology"].fillna(w["primary_lithology"]).fillna("unknown")
    lith_values = sorted(lith.unique())
    lith_idx = {v: i for i, v in enumerate(lith_values)}
    rows = []
    for geom, ol, cond, yld, stat, dep, bed, li, wid in zip(
            w.geometry, w["open_loop"], w["estimated_conductivity_wm"],
            w["well_yield_lpm"], w["static_level_m"], w["depth_m"],
            w["bedrock_depth_m"], lith, w["WELL_ID"]):
        rows.append([round(geom.x, 5), round(geom.y, 5), OPEN_LOOP.get(ol, 0),
                     jnum(cond, 2), jnum(yld, 0), jnum(stat, 1),
                     jnum(dep, 1), jnum(bed, 1), lith_idx[li], str(wid)])
    return rows, lith_values


def slim_geojson(gdf):
    gj = json.loads(gdf.to_json())
    for f in gj["features"]:
        f.pop("id", None)

        def rnd(c):
            return [rnd(x) for x in c] if isinstance(c, list) else round(c, 5)
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


def main():
    grid = build_grid()
    wells, lith_values = build_wells()
    capacity = build_capacity()

    empty_fc = {"type": "FeatureCollection", "features": []}
    blobs = {
        "GRID": json.dumps(grid, separators=(",", ":")),
        "WELLS": json.dumps(wells, separators=(",", ":")),
        "LITH": json.dumps(lith_values, separators=(",", ":")),
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
