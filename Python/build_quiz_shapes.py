#!/usr/bin/env python3
"""build_quiz_shapes.py - province / region outline icons for the Energy Quiz.

INPUTS (local, gitignored; same sources as Python/canada_boundary.py)
  geo_json/<PROV>.json     Statistics Canada FSA boundaries per province (lon/lat)
  lfsa000b21a_e.json       national FSA file; used only for Yukon (not in geo_json/)
  ceud_json/meta.json, construction_json/constr_*.json   region names

OUTPUT
  quiz_json/shapes.json    {"shapes": {code: "<svg path d>"}, "names": {display name: code},
                            "omitted": {code: share of area dropped}}

METHOD (kept simple on purpose)
  * Union each province's FSA polygons, project with a spherical Lambert
    conformal conic (standard parallels 49 N / 77 N, central meridian 91.87 W,
    the same family StatCan uses) so shapes look like a normal map of Canada.
  * Composite codes follow CEUD's groupings: tr = YT+NT+NU, atl = NL+PE+NS+NB,
    bct = BC+YT+NT+NU.
  * Drop parts smaller than MIN_PART (0.5%) of that region's area (tiny islands),
    simplify, drop lakes (interior rings), then FIT TO A 100x100 FRAME.
  * Each outline is fitted to its own frame: shapes do NOT show relative size.
    The quiz says so. The share of area dropped is recorded under "omitted".

Called from build_quiz.py; can also be run alone:  python Python/build_quiz_shapes.py
Needs shapely + numpy (only this step; the quiz page itself needs neither).
"""
import glob
import json
import math
import os
import sys
from pathlib import Path

import numpy as np
import shapely
from shapely.geometry import Polygon
from shapely.ops import unary_union

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "Python"))

MIN_PART = 0.005          # drop parts under 0.5% of the region's area
SIMPLIFY = 0.0035         # of the frame (fraction of the longer side)
GEO_FILES = {"AB": "ab", "BC": "bc", "MB": "mb", "NB": "nb", "NF": "nl", "NS": "ns",
             "NT": "nt", "NU": "nu", "ON": "on", "PE": "pe", "QC": "qc", "SK": "sk"}
COMPOSITES = {"tr": ["yt", "nt", "nu"], "atl": ["nl", "pe", "ns", "nb"], "bct": ["bc", "yt", "nt", "nu"]}

_P1, _P2, _P0, _L0 = map(math.radians, (49.0, 77.0, 63.390675, -91.86666666666666))
_N = math.log(math.cos(_P1) / math.cos(_P2)) / math.log(math.tan(math.pi / 4 + _P2 / 2) / math.tan(math.pi / 4 + _P1 / 2))
_F = math.cos(_P1) * math.tan(math.pi / 4 + _P1 / 2) ** _N / _N
_R0 = _F / math.tan(math.pi / 4 + _P0 / 2) ** _N


def project(arr):
    lon, lat = np.radians(arr[:, 0]), np.radians(arr[:, 1])
    rho = _F / np.tan(np.pi / 4 + lat / 2) ** _N
    th = _N * (lon - _L0)
    return np.column_stack([rho * np.sin(th), _R0 - rho * np.cos(th)])


def _poly(ring):
    if len(ring) < 4:
        return None
    p = Polygon(ring)
    if not p.is_valid:
        p = p.buffer(0)
    return None if p.is_empty else p


def load_provinces():
    import canada_boundary as cb
    os.chdir(ROOT)
    out = {}
    for f, code in GEO_FILES.items():
        path = ROOT / "geo_json" / f"{f}.json"
        if not path.exists():
            continue
        polys = []
        for feat in json.load(open(path))["features"]:
            for pc in feat["geometry"]["coordinates"]:
                p = _poly(pc[0])
                if p is not None:
                    polys.append(p)
        out[code] = unary_union(polys)
    lfsa = ROOT / "lfsa000b21a_e.json"
    if lfsa.exists():
        polys = []
        for feat in json.load(open(lfsa))["features"]:
            if not feat["properties"]["CFSAUID"].startswith("Y"):
                continue
            g = feat["geometry"]
            rings = g["coordinates"] if g["type"] == "MultiPolygon" else [g["coordinates"]]
            for pc in rings:
                p = _poly([cb.inverse_lambert(x, y) for x, y in pc[0]])
                if p is not None:
                    polys.append(p)
        out["yt"] = unary_union(polys)
    return out


def to_path(geom):
    """Project, drop small parts, simplify, fit to 100x100, return (path d, omitted share)."""
    g = shapely.transform(geom, project)
    parts = [q.buffer(0) for q in (list(g.geoms) if g.geom_type == "MultiPolygon" else [g])]
    parts = [q for q in parts if not q.is_empty]
    total = sum(p.area for p in parts)
    keep = [p for p in parts if p.area >= MIN_PART * total]
    omitted = 1 - sum(p.area for p in keep) / total
    bs = [p.bounds for p in keep]
    minx, miny = min(b[0] for b in bs), min(b[1] for b in bs)
    maxx, maxy = max(b[2] for b in bs), max(b[3] for b in bs)
    side = max(maxx - minx, maxy - miny)
    scale = 100.0 / side
    ox, oy = (100 - (maxx - minx) * scale) / 2, (100 - (maxy - miny) * scale) / 2
    d = []
    for p in keep:
        s = p.simplify(SIMPLIFY * side, preserve_topology=True)
        for q in (list(s.geoms) if s.geom_type == "MultiPolygon" else [s]):
            if q.is_empty or q.area < (MIN_PART / 4) * total:
                continue
            pts = [(ox + (x - minx) * scale, oy + (maxy - y) * scale) for x, y in q.exterior.coords]
            d.append("M" + "L".join(f"{x:.1f} {y:.1f}" for x, y in pts[:-1]) + "Z")
    return "".join(d), omitted


def region_names():
    names = {}
    meta = json.load(open(ROOT / "ceud_json" / "meta.json", encoding="utf-8"))
    for sec in meta["sectors"].values():
        for code, name in sec["regions"].items():
            if code != "ca":
                names[name] = code
    for f in glob.glob(str(ROOT / "construction_json" / "constr_*.json")):
        code = Path(f).stem.split("_")[1]
        if code != "ca":
            names[json.load(open(f, encoding="utf-8"))["name"]] = code
    return names


def build():
    prov = load_provinces()
    geoms = dict(prov)
    for code, parts in COMPOSITES.items():
        have = [prov[p] for p in parts if p in prov]
        if len(have) == len(parts):
            geoms[code] = unary_union(have)
    shapes, omitted = {}, {}
    for code, g in geoms.items():
        d, om = to_path(g)
        shapes[code] = d
        omitted[code] = round(om, 4)
    names = {n: c for n, c in region_names().items() if c in shapes}
    out = ROOT / "quiz_json"
    out.mkdir(exist_ok=True)
    (out / "shapes.json").write_text(json.dumps({"shapes": shapes, "names": names, "omitted": omitted},
                                                ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    kb = (out / "shapes.json").stat().st_size / 1024
    print(f"shapes: {len(shapes)} outlines, {kb:.0f} KB; names mapped {len(names)}; "
          f"area omitted (tiny islands) max {max(omitted.values()) * 100:.1f}% ({max(omitted, key=omitted.get)})")
    return shapes


if __name__ == "__main__":
    build()
