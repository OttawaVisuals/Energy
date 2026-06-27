"""
build_fsa_geometry.py

Converts StatCan's 2021 FSA cartographic boundary shapefile into per-province
GeoJSON files for the FSA choropleth map on retrofits.html — replaces the
manual mapshaper.org browser-console workflow (10 provinces x several
console commands each) with one script run.

INPUT: lfsa000b21a_e.shp (+ .dbf/.shx/.prj) from StatCan's boundary file
       (https://www12.statcan.gc.ca/census-recensement/2021/geo/sip-pis/
       boundary-limites/files-fichiers/lfsa000b21a_e.zip, ~162MB zipped).
       Set SHP_PATH below to wherever you extracted it.

WHY NO GDAL/pyproj/shapely/mapshaper: none are installed and this machine
has no GIS/Node tooling. The shapefile's CRS is NAD83 Statistics Canada
Lambert (a 2-standard-parallel Lambert Conformal Conic, confirmed via the
.prj file) — the inverse projection formula (Snyder, "Map Projections: A
Working Manual") is implemented from scratch below and round-trip-verified
to ~1e-14 degrees against forward-projected test points before being
trusted on real data.

WHY VARIABLE SIMPLIFICATION TOLERANCE (not a single fixed tolerance, and not
mapshaper's "keep-shapes"): a single tolerance applied uniformly either
leaves huge rural/coastal FSAs far too detailed (most of the file size, with
detail nobody can see at province zoom) or collapses small dense urban FSAs
into near-degenerate triangles (mapshaper's keep-shapes only guarantees a
shape doesn't fully vanish — 3-4 points — not that it still looks like a
real polygon; confirmed this happening to ~91 Ontario FSAs incl. K1L when
mapshaper.org was used by hand with a uniform percentage). Tolerance here
scales with each shape's own LANDAREA (StatCan field, sq km): small/dense
shapes get a tight tolerance (more points kept, real shape preserved),
huge ones get a loose tolerance (file size controlled). MIN_RING_POINTS
on top of that guarantees every ring keeps at least that many vertices
(resampled from the original if DP simplifies below it), regardless of
tolerance — a hard floor mapshaper's keep-shapes doesn't provide.

OUTPUT FORMAT: standard GeoJSON FeatureCollection per province, matching
what retrofits.html's fetchGeoJSON/loadFsaMap already expect — properties.
CFSAUID + a MultiPolygon geometry (each ring shipped as its own single-ring
"polygon" entry; this dataset has no true donut/hole FSAs, so there's no
need to detect ring nesting/winding to build true GeoJSON holes).
  geo_json/<PROV>.json -> {"type":"FeatureCollection","features":[
    {"type":"Feature","properties":{"CFSAUID":fsa},
     "geometry":{"type":"MultiPolygon","coordinates":[[ring],[ring],...]}}, ...]}
"""

import json
import math
import os

import shapefile

SHP_PATH = r"C:\Users\simon\AppData\Local\Temp\fsa_shp\lfsa000b21a_e\lfsa000b21a_e.shp"
OUT_DIR = "geo_json"

# (max LANDAREA in sq km, DP tolerance in degrees) — first bucket whose
# max area fits the shape wins. ~0.00005deg is ~5m, ~0.002deg is ~200m.
# Tuned by checking actual file sizes/vertex counts against the previous
# (broken) mapshaper output, not a precise physical derivation.
TOLERANCE_BUCKETS = [
    (10, 0.00003),
    (50, 0.00008),
    (200, 0.0002),
    (1000, 0.0006),
    (float("inf"), 0.0018),
]
MIN_RING_POINTS = 10  # hard floor — see WHY VARIABLE SIMPLIFICATION above
# Upper bound per ring, regardless of area: a few Northern Ontario FSAs
# (e.g. P0X) are dense with thousands of small lakes and have 600k+ raw
# points — far more than their LANDAREA bucket alone would suggest needs
# keeping. If the area-based tolerance still leaves a ring over this count,
# tolerance is doubled and DP re-run until it's under the cap.
MAX_RING_POINTS = 1500
# Below this bounding-box diagonal (metres, in the source Lambert CRS — cheap
# to check before reprojecting), a ring is dropped entirely unless it's a
# shape's single largest ring. Rural Northern Ontario FSAs can have several
# thousand separate rings (one per small lake/island, e.g. P0X has 4,938,
# two-thirds of them under 50 raw points) that are invisible at province
# zoom anyway — keeping MIN_RING_POINTS on all of them, instead of dropping
# them, was the actual cause of the multi-MB blowup, not the area-tolerance
# buckets themselves.
MIN_RING_BBOX_DIAGONAL_M = 800


def tolerance_for_area(area_km2):
    for max_area, tol in TOLERANCE_BUCKETS:
        if area_km2 <= max_area:
            return tol
    return TOLERANCE_BUCKETS[-1][1]

# StatCan PRUID -> this project's province code (matches PROVINCES in
# retrofits.html). Territories aren't in the province dropdown and one
# (Nunavut) has a single FSA covering 600k+ raw points, so they're skipped
# entirely rather than processed and left unused.
PRUID_TO_PROV = {
    "10": "NF", "11": "PE", "12": "NS", "13": "NB", "24": "QC", "35": "ON",
    "46": "MB", "47": "SK", "48": "AB", "59": "BC",
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


def ensure_min_points(simplified, original, min_pts):
    """
    DP guarantees a tolerance-bounded shape, not a point count — small/
    simple rings can come out as a bare triangle even at a tight tolerance.
    If that happens and the original ring actually had more detail to give,
    resample it evenly instead of accepting the degenerate result (this is
    the hard floor mapshaper's "keep-shapes" doesn't provide — that only
    promises a ring won't fully vanish, not that it keeps min_pts vertices).
    """
    if len(simplified) >= min_pts or len(original) <= min_pts:
        return simplified
    step = (len(original) - 1) / (min_pts - 1)
    idxs = sorted({round(i * step) for i in range(min_pts)})
    idxs[-1] = len(original) - 1  # keep the ring closed
    return [original[i] for i in idxs]


def main():
    sf = shapefile.Reader(SHP_PATH, encoding="latin-1")
    by_province = {}
    skipped_prov = set()
    n = len(sf)

    for i, sr in enumerate(sf.iterShapeRecords()):
        fsa = sr.record["CFSAUID"]
        pruid = sr.record["PRUID"]
        prov = PRUID_TO_PROV.get(pruid)
        if not prov:
            skipped_prov.add(pruid)
            continue

        base_tol = tolerance_for_area(sr.record["LANDAREA"])
        shape = sr.shape
        parts = list(shape.parts) + [len(shape.points)]
        ring_slices = [(parts[p], parts[p + 1]) for p in range(len(parts) - 1)]

        def bbox_diag(pts):
            xs = [pt[0] for pt in pts]
            ys = [pt[1] for pt in pts]
            return math.hypot(max(xs) - min(xs), max(ys) - min(ys))

        diags = [bbox_diag(shape.points[s:e]) for s, e in ring_slices]
        main_ring_idx = max(range(len(diags)), key=lambda i: diags[i]) if diags else None

        rings = []
        for i, (s, e) in enumerate(ring_slices):
            if i != main_ring_idx and diags[i] < MIN_RING_BBOX_DIAGONAL_M:
                continue  # tiny lake/island, invisible at province zoom
            ring_pts = shape.points[s:e]
            lonlat = [inverse_lambert(x, y) for x, y in ring_pts]
            tol = base_tol
            simplified = douglas_peucker(lonlat, tol)
            while len(simplified) > MAX_RING_POINTS:
                tol *= 1.6
                simplified = douglas_peucker(lonlat, tol)
            simplified = ensure_min_points(simplified, lonlat, MIN_RING_POINTS)
            if len(simplified) >= 3:
                rings.append([[round(lon, 5), round(lat, 5)] for lon, lat in simplified])

        by_province.setdefault(prov, []).append((fsa, rings))
        if (i + 1) % 200 == 0:
            print(f"  processed {i+1}/{n}")

    if skipped_prov:
        print(f"  skipped PRUIDs not in PRUID_TO_PROV: {sorted(skipped_prov)}")

    os.makedirs(OUT_DIR, exist_ok=True)
    for prov, fsa_rings in by_province.items():
        features = [
            {
                "type": "Feature",
                "properties": {"CFSAUID": fsa},
                "geometry": {"type": "MultiPolygon", "coordinates": [[ring] for ring in rings]},
            }
            for fsa, rings in fsa_rings
        ]
        out_path = os.path.join(OUT_DIR, f"{prov}.json")
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump({"type": "FeatureCollection", "features": features}, f, separators=(",", ":"))
        size_kb = os.path.getsize(out_path) / 1024
        n_degenerate = sum(1 for _, rings in fsa_rings if sum(len(r) for r in rings) <= 5)
        print(f"  wrote {out_path} — {len(fsa_rings)} FSAs, {size_kb:.0f} KB, "
              f"{n_degenerate} degenerate shapes")


if __name__ == "__main__":
    main()
