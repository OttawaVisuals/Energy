"""
fetch_municipal_layers.py  (guide step 5)

Pull the Ottawa municipal layers from the City of Ottawa ArcGIS REST server
(maps.ottawa.ca) and save them as GeoJSON in Data/processed/:

    zoning_industrial.geojson    Zoning/3, ZONE_MAIN in IL/IG/IH/IP/RG/RH
                                 (industrial + rural industrial, bylaw 2008-250)
    sewer_lines.geojson          WastewaterInfrastructure/7 (sanitary) + /14
                                 (combined), tagged with kind
    city_open_loop_potential.geojson
                                 Planning/122 — the City's own "Open Loop
                                 Geothermal Potential" polygons (High/Average/
                                 Low/None)

Not fetched (documented decisions):
    building footprints   TopographicMapping/3 is 392k polygons (~0.5 GB);
                          nothing in the pipeline consumes them yet.
    city-owned properties the guide's dataset no longer exists on
                          open.ottawa.ca (searched 2026-07-09).

Usage:
    python Geothermal/scripts/fetch_municipal_layers.py
"""

import json
import time
from pathlib import Path

import requests

HERE = Path(__file__).resolve().parents[1]              # Geothermal/
OUT = HERE / "Data" / "processed"
BASE = "https://maps.ottawa.ca/arcgis/rest/services"

INDUSTRIAL = "('IL','IG','IH','IP','RG','RH')"

PULLS = [
    {
        "name": "zoning_industrial",
        "layer": "Zoning/MapServer/3",
        "where": f"ZONE_MAIN IN {INDUSTRIAL}",
        "fields": "ZONE_CODE,ZONE_MAIN,ZNAME_EN,LABEL",
    },
    {
        # f=geojson 400s on the WastewaterInfrastructure layers; use esrijson
        "name": "sewer_sanitary",
        "layer": "WastewaterInfrastructure/MapServer/7",
        "where": "1=1",
        "fields": "STRUCT_ID,FUNCTION,MATERIAL,WIDTH,INSTALL_YEAR",
        "format": "esrijson",
    },
    {
        "name": "sewer_combined",
        "layer": "WastewaterInfrastructure/MapServer/14",
        "where": "1=1",
        "fields": "STRUCT_ID,FUNCTION,MATERIAL,WIDTH,INSTALL_YEAR",
        "format": "esrijson",
    },
    {
        "name": "city_open_loop_potential",
        "layer": "Planning/MapServer/122",
        "where": "1=1",
        "fields": "POTENTIAL_EN,CRITERIA_P",
    },
]


def esri_to_geojson(feat):
    """esriJSON feature -> GeoJSON feature (points, polylines, polygons)."""
    g = feat.get("geometry") or {}
    if "paths" in g:
        p = g["paths"]
        geom = ({"type": "LineString", "coordinates": p[0]} if len(p) == 1
                else {"type": "MultiLineString", "coordinates": p})
    elif "rings" in g:
        geom = {"type": "Polygon", "coordinates": g["rings"]}
    elif "x" in g:
        geom = {"type": "Point", "coordinates": [g["x"], g["y"]]}
    else:
        geom = None
    return {"type": "Feature", "geometry": geom,
            "properties": feat.get("attributes", {})}


def fetch_layer(layer, where, fields, fmt="geojson", page=1000):
    url = f"{BASE}/{layer}/query"
    count = requests.get(url, params={
        "where": where, "returnCountOnly": "true", "f": "json"}, timeout=120
    ).json()["count"]

    features, offset = [], 0
    while True:
        r = requests.get(url, params={
            "where": where, "outFields": fields, "returnGeometry": "true",
            "outSR": "4326", "f": "json" if fmt == "esrijson" else "geojson",
            "resultOffset": offset, "resultRecordCount": page,
        }, timeout=300)
        r.raise_for_status()
        data = r.json()
        if "error" in data:
            raise RuntimeError(f"{layer}: {data['error']}")
        batch = data.get("features", [])
        if fmt == "esrijson":
            batch = [esri_to_geojson(f) for f in batch]
        features.extend(batch)
        print(f"    {len(features):,}/{count:,}")
        if len(batch) < page:
            break
        offset += page
        time.sleep(0.2)
    return features


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    results = {}
    for p in PULLS:
        print(f"[{p['name']}] {p['layer']} where {p['where']}")
        results[p["name"]] = fetch_layer(p["layer"], p["where"], p["fields"],
                                         p.get("format", "geojson"))

    # sanitary + combined -> one sewer file, tagged
    sewers = []
    for kind in ("sanitary", "combined"):
        for f in results.pop(f"sewer_{kind}"):
            f["properties"]["kind"] = kind
            sewers.append(f)
    results["sewer_lines"] = sewers

    for name, feats in results.items():
        path = OUT / f"{name}.geojson"
        path.write_text(json.dumps(
            {"type": "FeatureCollection", "features": feats},
            separators=(",", ":")), encoding="utf-8")
        print(f"wrote {path.name}: {len(feats):,} features "
              f"({path.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
