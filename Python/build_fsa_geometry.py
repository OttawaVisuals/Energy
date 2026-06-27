"""
build_fsa_geometry.py

Converts StatCan's 2021 FSA cartographic boundary shapefile into small
per-province JSON files of simplified polygon rings in lon/lat, for the
FSA choropleth map on retrofits.html.

INPUT: lfsa000b21a_e.shp (+ .dbf/.shx/.prj) from StatCan's boundary file
       (https://www12.statcan.gc.ca/census-recensement/2021/geo/sip-pis/
       boundary-limites/files-fichiers/lfsa000b21a_e.zip, ~162MB zipped).
       Set SHP_PATH below to wherever you extracted it.

WHY NO GDAL/pyproj/shapely: none are installed and this machine has no
GIS tooling (no GDAL, no mapshaper/node). The shapefile's CRS is NAD83
Statistics Canada Lambert (a 2-standard-parallel Lambert Conformal Conic,
confirmed via the .prj file) — the inverse projection formula (Snyder,
"Map Projections: A Working Manual") is implemented from scratch below
and round-trip-verified to ~1e-14 degrees against forward-projected test
points before being trusted on real data.

OUTPUT FORMAT — deliberately NOT GeoJSON: each FSA's geometry is just a
list of closed rings in [lon,lat] pairs, meant to be drawn as one SVG
<path> per FSA with fill-rule:evenodd. This sidesteps GeoJSON's outer-
ring/hole winding-order rules entirely (evenodd fill handles holes
correctly regardless of winding) — not needed for a filled choropleth.
  geo_json/<PROV>.json -> { "<FSA>": [ [[lon,lat],...], [[lon,lat],...] ], ... }

Polygons are simplified with a pure-Python Douglas-Peucker implementation
(tolerance in degrees, ~DP_TOLERANCE) since the source shapefile is far too
detailed for a web map (e.g. one mid-sized FSA alone had 34,000+ points).
"""

import json
import math
import os

import shapefile

SHP_PATH = r"C:\Users\simon\AppData\Local\Temp\fsa_shp\lfsa000b21a_e\lfsa000b21a_e.shp"
OUT_DIR = "geo_json"
DP_TOLERANCE = 0.0008  # degrees, ~80-90m — tuned for file size vs. visible shape fidelity

# StatCan PRUID -> this project's province code (matches PROVINCES in
# retrofits.html). Territories (60/61/62) are included even though they're
# not in the province dropdown, in case they're wanted later — harmless if
# unused.
PRUID_TO_PROV = {
    "10": "NF", "11": "PE", "12": "NS", "13": "NB", "24": "QC", "35": "ON",
    "46": "MB", "47": "SK", "48": "AB", "59": "BC", "60": "YT", "61": "NT", "62": "NU",
}

# ── Inverse NAD83 Statistics Canada Lambert (2 standard parallels) ─────────
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


# ── Pure-Python Douglas-Peucker ─────────────────────────────────────────
def _perp_dist(p, a, b):
    if a == b:
        return math.hypot(p[0] - a[0], p[1] - a[1])
    x1, y1 = a
    x2, y2 = b
    num = abs((x2 - x1) * (p[1] - y1) - (p[0] - x1) * (y2 - y1))
    den = math.hypot(x2 - x1, y2 - y1)
    return num / den


def douglas_peucker(points, tol):
    if len(points) < 3:
        return points
    dmax, idx = 0, 0
    for i in range(1, len(points) - 1):
        d = _perp_dist(points[i], points[0], points[-1])
        if d > dmax:
            dmax, idx = d, i
    if dmax > tol:
        left = douglas_peucker(points[:idx + 1], tol)
        right = douglas_peucker(points[idx:], tol)
        return left[:-1] + right
    return [points[0], points[-1]]


def main():
    sf = shapefile.Reader(SHP_PATH, encoding="latin-1")
    by_province = {}
    skipped_prov = set()

    for i, sr in enumerate(sf.iterShapeRecords()):
        fsa = sr.record["CFSAUID"]
        pruid = sr.record["PRUID"]
        prov = PRUID_TO_PROV.get(pruid)
        if not prov:
            skipped_prov.add(pruid)
            continue

        shape = sr.shape
        parts = list(shape.parts) + [len(shape.points)]
        rings = []
        for p in range(len(parts) - 1):
            ring_pts = shape.points[parts[p]:parts[p + 1]]
            lonlat = [inverse_lambert(x, y) for x, y in ring_pts]
            simplified = douglas_peucker(lonlat, DP_TOLERANCE)
            if len(simplified) >= 3:
                rings.append([[round(lon, 5), round(lat, 5)] for lon, lat in simplified])

        by_province.setdefault(prov, {})[fsa] = rings
        if (i + 1) % 200 == 0:
            print(f"  processed {i+1}/{len(sf)}")

    if skipped_prov:
        print(f"  skipped PRUIDs not in PRUID_TO_PROV: {sorted(skipped_prov)}")

    os.makedirs(OUT_DIR, exist_ok=True)
    for prov, fsas in by_province.items():
        out_path = os.path.join(OUT_DIR, f"{prov}.json")
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(fsas, f, separators=(",", ":"))
        size_kb = os.path.getsize(out_path) / 1024
        print(f"  wrote {out_path} — {len(fsas)} FSAs, {size_kb:.0f} KB")


if __name__ == "__main__":
    main()
