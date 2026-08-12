"""
Builds a single unioned Canada land-boundary polygon from the FSA
geometry already committed for the choropleth maps (geo_json/*.json,
lon/lat, produced by build_fsa_geometry.py), for use as (a) a point-in-
polygon mask to crop other gridded datasets to Canada and (b) a
lightweight outline for a map background.

geo_json/*.json covers every province except Yukon (never generated --
see repo state at time of writing). Yukon FSAs (CFSAUID starting "Y")
are pulled instead from the raw national file at the repo root,
lfsa000b21a_e.json, which is still in its source CRS (NAD83 Statistics
Canada Lambert, a 2-standard-parallel Lambert Conformal Conic -- confirmed
in Python/build_fsa_geometry.py's docstring) and reprojected here with
the same hand-derived inverse formula that script uses, copied rather
than imported so this module has no dependency on that one-off script.
"""
import glob
import json
import math
import os

from shapely.geometry import Polygon
from shapely.ops import unary_union

GEO_JSON_DIR = "geo_json"
LFSA_ROOT = "lfsa000b21a_e.json"

# ── Inverse NAD83 Statistics Canada Lambert (2 standard parallels) ─────────
# Copied from Python/build_fsa_geometry.py, round-trip-verified there.
_A = 6378137.0
_F = 1 / 298.257222101
_E2 = _F * (2 - _F)
_E = math.sqrt(_E2)
_PHI1, _PHI2, _PHI0 = math.radians(49), math.radians(77), math.radians(63.390675)
_LAM0 = math.radians(-91.86666666666666)
_X0, _Y0 = 6200000.0, 3000000.0


def _m(phi):
    return math.cos(phi) / math.sqrt(1 - _E2 * math.sin(phi) ** 2)


def _t(phi):
    s = math.sin(phi)
    return math.tan(math.pi / 4 - phi / 2) / (((1 - _E * s) / (1 + _E * s)) ** (_E / 2))


_M1, _M2 = _m(_PHI1), _m(_PHI2)
_T1, _T2, _T0 = _t(_PHI1), _t(_PHI2), _t(_PHI0)
_N = (math.log(_M1) - math.log(_M2)) / (math.log(_T1) - math.log(_T2))
_FF = _M1 / (_N * _T1 ** _N)
_RHO0 = _A * _FF * _T0 ** _N


def inverse_lambert(x, y):
    xp = x - _X0
    yp = _RHO0 - (y - _Y0)
    rho = math.copysign(math.sqrt(xp * xp + yp * yp), _N)
    theta = math.atan2(xp, yp) if _N >= 0 else math.atan2(-xp, -yp)
    tt = (rho / (_A * _FF)) ** (1 / _N)
    lam = theta / _N + _LAM0
    phi = math.pi / 2 - 2 * math.atan(tt)
    for _ in range(10):
        s = math.sin(phi)
        phi_new = math.pi / 2 - 2 * math.atan(tt * (((1 - _E * s) / (1 + _E * s)) ** (_E / 2)))
        if abs(phi_new - phi) < 1e-12:
            phi = phi_new
            break
        phi = phi_new
    return math.degrees(lam), math.degrees(phi)


def _valid_polygon(ring):
    if len(ring) < 4:
        return None
    p = Polygon(ring)
    if not p.is_valid:
        p = p.buffer(0)
    return p if not p.is_empty else None


def build_canada_geometry():
    """Returns a single unioned shapely (Multi)Polygon covering all of Canada."""
    polys = []
    for path in glob.glob(os.path.join(GEO_JSON_DIR, "*.json")):
        d = json.load(open(path))
        for feat in d["features"]:
            for poly_coords in feat["geometry"]["coordinates"]:
                p = _valid_polygon(poly_coords[0])
                if p is not None:
                    polys.append(p)

    lfsa = json.load(open(LFSA_ROOT))
    for feat in lfsa["features"]:
        if not feat["properties"]["CFSAUID"].startswith("Y"):
            continue
        geom = feat["geometry"]
        rings = geom["coordinates"] if geom["type"] == "MultiPolygon" else [geom["coordinates"]]
        for poly_coords in rings:
            ring = [inverse_lambert(x, y) for x, y in poly_coords[0]]
            p = _valid_polygon(ring)
            if p is not None:
                polys.append(p)

    return unary_union(polys)


def simplified_rings(geom, tolerance_deg, min_area_deg2=0.0):
    """Exterior rings only (holes/lakes ignored -- irrelevant at this
    scale), simplified and area-filtered, as plain [[lon,lat],...] lists."""
    geoms = list(geom.geoms) if geom.geom_type == "MultiPolygon" else [geom]
    rings = []
    for g in geoms:
        if g.area < min_area_deg2:
            continue
        s = g.simplify(tolerance_deg, preserve_topology=True)
        if s.is_empty:
            continue
        ext = list(s.exterior.coords)
        if len(ext) >= 4:
            rings.append([[round(x, 3), round(y, 3)] for x, y in ext])
    return rings
