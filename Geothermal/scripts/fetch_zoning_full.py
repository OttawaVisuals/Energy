"""
fetch_zoning_full.py

Pulls the FULL Ottawa zoning layer (Zoning/MapServer/3, no ZONE_MAIN filter --
contrast with fetch_municipal_layers.py's industrial-only pull) using the same
paginated-ArcGIS-REST pattern (f=geojson, esriJSON fallback if geojson 400s).

Used by build_building_stock.py to classify buildings residential /
commercial / institutional / industrial from ZONE_MAIN prefixes.

Output:
    Geothermal/Data/Raw/zoning_full.geojson   (raw cache, all fields kept)

Usage:
    python Geothermal/scripts/fetch_zoning_full.py
"""

import json
import time
from pathlib import Path

import requests

HERE = Path(__file__).resolve().parents[1]              # Geothermal/
RAW = HERE / "Data" / "Raw"
BASE = "https://maps.ottawa.ca/arcgis/rest/services"

LAYER = "Zoning/MapServer/3"
FIELDS = "ZONE_CODE,ZONE_MAIN,ZNAME_EN,LABEL"
OUT = RAW / "zoning_full.geojson"


def esri_to_geojson(feat):
    g = feat.get("geometry") or {}
    if "rings" in g:
        geom = {"type": "Polygon", "coordinates": g["rings"]}
    elif "paths" in g:
        p = g["paths"]
        geom = ({"type": "LineString", "coordinates": p[0]} if len(p) == 1
                else {"type": "MultiLineString", "coordinates": p})
    elif "x" in g:
        geom = {"type": "Point", "coordinates": [g["x"], g["y"]]}
    else:
        geom = None
    return {"type": "Feature", "geometry": geom,
            "properties": feat.get("attributes", {})}


def fetch_layer(layer, where, fields, page=1000):
    url = f"{BASE}/{layer}/query"
    count = requests.get(url, params={
        "where": where, "returnCountOnly": "true", "f": "json"}, timeout=120
    ).json()["count"]
    print(f"  server reports {count:,} features")

    features, offset = [], 0
    fmt = "geojson"
    while True:
        r = requests.get(url, params={
            "where": where, "outFields": fields, "returnGeometry": "true",
            "outSR": "4326", "f": fmt,
            "resultOffset": offset, "resultRecordCount": page,
        }, timeout=300)
        if fmt == "geojson" and r.status_code == 400:
            print("  f=geojson 400'd -- falling back to esrijson")
            fmt = "json"
            continue
        r.raise_for_status()
        data = r.json()
        if "error" in data:
            raise RuntimeError(f"{layer}: {data['error']}")
        batch = data.get("features", [])
        if fmt == "json":
            batch = [esri_to_geojson(f) for f in batch]
        features.extend(batch)
        print(f"    {len(features):,}/{count:,}")
        if len(batch) < page:
            break
        offset += page
        time.sleep(0.2)
    return features


def main():
    RAW.mkdir(parents=True, exist_ok=True)
    print(f"[zoning_full] {LAYER} where 1=1")
    feats = fetch_layer(LAYER, "1=1", FIELDS)
    OUT.write_text(json.dumps(
        {"type": "FeatureCollection", "features": feats},
        separators=(",", ":")), encoding="utf-8")
    print(f"wrote {OUT}: {len(feats):,} features ({OUT.stat().st_size / 1e6:.1f} MB)")

    # quick ZONE_MAIN distribution for the classification-mapping doc step
    from collections import Counter
    c = Counter((f["properties"].get("ZONE_MAIN") or "")[:2] for f in feats)
    print("ZONE_MAIN 2-char prefixes:", c.most_common(30))


if __name__ == "__main__":
    main()
