"""
build_fsa_climate.py

Assigns per-FSA Heating/Cooling Degree Days (base 18 degC) from ECCC
Canadian Climate Normals station data, for the Retrofit Insights page
(ROADMAP.md item 13, Phase 0 -- climate linkage section needs an HDD/CDD
per FSA that the ERS pairing data doesn't carry).

STATION DATA SOURCES (ECCC), preferred-then-fallback per station:
  - Preferred: 1991-2020 Climate Normals. There is no bulk API for this
    period as of 2026-07 (verified: api.weather.gc.ca/collections lists
    only "climate-normals" = 1981-2010; querying it with
    PERIOD_BEGIN=1991 returns zero rows). Instead this scrapes
    climate.weather.gc.ca/climate_normals: the official composite-station
    inventory CSV (station_inventory_e.html?yr=1991 -- yes, that URL
    serves a CSV, not HTML) lists 448 composite stations with lat/lon and
    each member station's CLIMATE_ID, but not the internal `stnID` that
    bulk_data_e.html needs. That id is recovered with ONE request per
    composite station: results_1991_2020_e.html?climate_id=<any member
    CLIMATE_ID>&dispBack=1 returns a page with exactly one hidden
    <form id="dl-data"> block (lang/prov/stnname/yr/stnID/climate_id),
    which is then used to fetch the per-station "all elements" Normals
    CSV from bulk_data_e.html. Both requests are cached under
    climate_cache/ (raw pulls), one pair of files per composite station,
    so a re-run only fetches stations missing from the cache.
  - Fallback: 1981-2010 Climate Normals via the GeoMet OGC API
    (api.weather.gc.ca/collections/climate-normals/items). That API's
    server-side filtering on E_NORMAL_ELEMENT_NAME silently no-ops
    (tested: adding it doesn't change numberMatched at all) so instead
    all ~47.7k MONTH=13 (annual) rows are pulled paginated (5 pages of
    10k, cached under climate_cache/eccc_1981_2010/) and filtered
    client-side for the two Degree Days elements. Yields ~661 stations.
  - WebFetch is blocked for some ECCC hosts (see memory notes); this uses
    requests with a browser User-Agent throughout, same as elsewhere in
    this repo.
  - Each results_1991_2020_e.html / bulk_data_e.html request takes ~15-20s
    server-side regardless of payload size (measured directly, not a
    fluke) -- sequential fetching of all 448 stations would take hours,
    so that stage runs on a small thread pool (12 workers -> ~20-30 min).

HDD/CDD DEFINITION: ECCC's standard annual "degree days below 18 degC"
(HDD) / "degree days Above 18 degC" (CDD). 1991-2020 bulk CSV: row under
ELEMENT_GROUP "Degree Days", NORMALS_ELEMENT "Degree Days Below/Above
18 °C", "Year" column. 1981-2010 API: E_NORMAL_ELEMENT_NAME "Total
degree-days below/Above 18 deg C", MONTH=13 (13 = annual, 1-12 = months).

FSA GEOMETRY: FSA centroids computed from FSA_Maps/<PROV>.geojson
(unweighted average of all polygon/multipolygon vertices -- adequate for
nearest-station assignment, not meant to be a true area centroid). The
file is named NL.geojson but downstream fsa_json/ and province_json/ use
the code NF -- normalized here. Only 10 provinces have a FSA_Maps
geojson (PE included); the territories (NT/NU/YT) have none, so their
FSAs are simply absent from the output -- there's no geometry to compute
a centroid from, regardless of station coverage.

ASSIGNMENT: each FSA's HDD/CDD is inverse-distance-weighted (weight =
1/dist_km) over the 3 nearest stations within 200 km of its centroid; if
fewer than 3 are within 200 km, whatever is inside 200 km is used
weighted; if none are within 200 km, the single nearest station is used
unweighted (dist_km recorded regardless of the 200 km cutoff). Straight-
line haversine distance to the station coordinate, not FSA shape/area.
Per station, 1991-2020 normals are preferred; a station only has
1981-2010 data if it wasn't resolved in the 1991-2020 scrape.

OUTPUT: climate_json/fsa_climate.json ->
  { "<FSA>": { "hdd": float, "cdd": float,
               "station": str | [str, ...],
               "dist_km": float | [float, ...],
               "normals_period": "1991-2020" | "1981-2010" } }
Station/dist_km are scalars when only one station qualified, else lists
in the same order (IDW cases).
"""

import csv
import io
import json
import math
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

CACHE_DIR = "climate_cache"
FSA_MAPS_DIR = "FSA_Maps"
OUT_DIR = "climate_json"
OUT_PATH = os.path.join(OUT_DIR, "fsa_climate.json")

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

STATION_INVENTORY_URL = "https://climate.weather.gc.ca/climate_normals/station_inventory_e.html?yr=1991"
RESULTS_URL = "https://climate.weather.gc.ca/climate_normals/results_1991_2020_e.html"
BULK_DATA_URL = "https://climate.weather.gc.ca/climate_normals/bulk_data_e.html"
GEOMET_NORMALS_URL = "https://api.weather.gc.ca/collections/climate-normals/items"

# FSA_Maps/province_json provincial code mismatch.
GEOJSON_TO_CODE = {
    "AB": "AB", "BC": "BC", "MB": "MB", "NB": "NB", "NL": "NF",
    "NS": "NS", "ON": "ON", "PE": "PE", "QC": "QC", "SK": "SK",
}

IDW_K = 3
IDW_RADIUS_KM = 200.0


def _cache_path(*parts):
    return os.path.join(CACHE_DIR, *parts)


def _fetch(url, cache_file, params=None, is_json=False):
    path = _cache_path(cache_file)
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f) if is_json else f.read()
    resp = requests.get(url, params=params, headers=HEADERS, timeout=60)
    resp.raise_for_status()
    text = resp.text
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    time.sleep(0.2)
    return json.loads(text) if is_json else text


def haversine_km(lat1, lon1, lat2, lon2):
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


# ---------------------------------------------------------------------------
# Step 1: 1991-2020 composite station inventory (lat/lon, member CLIMATE_IDs)
# ---------------------------------------------------------------------------

def load_1991_2020_inventory():
    text = _fetch(STATION_INVENTORY_URL, "station_inventory_1991.csv").lstrip("﻿")
    reader = csv.DictReader(io.StringIO(text))
    composites = {}
    for row in reader:
        name = row["COMPOSITE_STATION_NAME"]
        c = composites.setdefault(name, {"climate_ids": [], "lats": [], "lons": []})
        c["climate_ids"].append(row["CLIMATE_ID"])
        c["lats"].append(float(row["LATITUDE"]))
        c["lons"].append(float(row["LONGITUDE"]))
    return composites


# ---------------------------------------------------------------------------
# Step 2: resolve each composite station's bulk_data form fields, then its
# "all elements" Normals CSV -> annual HDD/CDD.
# ---------------------------------------------------------------------------

FORM_RE = re.compile(r'<form action="bulk_data_e\.html".*?</form>', re.S)
INPUT_RE = re.compile(r'name="(\w+)"\s*/?>|name="(\w+)"')


def _parse_hidden_inputs(form_html):
    # Attribute order on this page is `value="..." name="..."`, not the more
    # common `name` first -- match each <input> tag then pull both attrs out
    # independently instead of assuming an order.
    fields = {}
    for tag in re.findall(r"<input[^>]*/>", form_html):
        nm = re.search(r'name="(\w+)"', tag)
        val = re.search(r'value="([^"]*)"', tag)
        if nm and val:
            fields[nm.group(1)] = val.group(1)
    return fields


def safe_name(name):
    return re.sub(r"[^A-Za-z0-9]+", "_", name).strip("_")


def resolve_1991_2020_station(composite_name, climate_ids):
    cache_name = f"1991_form_{safe_name(composite_name)}.html"
    html = None
    for cid in climate_ids:
        html = _fetch(RESULTS_URL, cache_name, params={"climate_id": cid, "dispBack": 1})
        forms = FORM_RE.findall(html)
        if forms:
            break
    if not html or not forms:
        return None
    fields = _parse_hidden_inputs(forms[0])
    required = {"lang", "prov", "stnname", "yr", "stnID", "climate_id"}
    if not required.issubset(fields):
        return None
    return fields


def fetch_1991_2020_normals_csv(composite_name, fields):
    cache_name = f"1991_csv_{safe_name(composite_name)}.csv"
    return _fetch(BULK_DATA_URL, cache_name, params={
        "lang": fields["lang"], "prov": fields["prov"], "stnname": fields["stnname"],
        "yr": fields["yr"], "stnID": fields["stnID"], "climate_id": fields["climate_id"],
        "submit": "Download Data",
    })


def parse_annual_hdd_cdd_from_bulk_csv(csv_text):
    reader = csv.DictReader(io.StringIO(csv_text))
    hdd = cdd = None
    for row in reader:
        element = (row.get("NORMALS_ELEMENT") or "").strip()
        if element == "Degree Days Below 18 °C":
            hdd = row.get("Year")
        elif element == "Degree Days Above 18 °C":
            cdd = row.get("Year")
    if hdd is None or cdd is None:
        return None
    try:
        return float(hdd), float(cdd)
    except ValueError:
        return None


def _resolve_one(name, info):
    fields = resolve_1991_2020_station(name, info["climate_ids"])
    if not fields:
        return name, None
    try:
        csv_text = fetch_1991_2020_normals_csv(name, fields)
    except requests.RequestException:
        return name, None
    parsed = parse_annual_hdd_cdd_from_bulk_csv(csv_text)
    if not parsed:
        return name, None
    hdd, cdd = parsed
    lat = sum(info["lats"]) / len(info["lats"])
    lon = sum(info["lons"]) / len(info["lons"])
    return name, {"station": name, "lat": lat, "lon": lon, "hdd": hdd, "cdd": cdd,
                  "normals_period": "1991-2020"}


def build_1991_2020_stations(composites, workers=12):
    # Each request to results_1991_2020_e.html / bulk_data_e.html takes ~15-20s
    # server-side (verified), so this is threaded -- sequential would be hours.
    stations = {}
    n_ok, n_fail = 0, 0
    items = sorted(composites.items())
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futures = {ex.submit(_resolve_one, name, info): name for name, info in items}
        done = 0
        for fut in as_completed(futures):
            name, rec = fut.result()
            done += 1
            if rec:
                stations[name] = rec
                n_ok += 1
            else:
                n_fail += 1
            if done % 25 == 0 or done == len(items):
                print(f"    ...{done}/{len(items)} composite stations processed "
                      f"({n_ok} ok, {n_fail} failed)", flush=True)
    print(f"  1991-2020: resolved {n_ok}/{len(composites)} composite stations ({n_fail} failed/skipped)")
    return stations


# ---------------------------------------------------------------------------
# Step 3: 1981-2010 fallback via GeoMet API, paginated + filtered client-side
# ---------------------------------------------------------------------------

def build_1981_2010_stations():
    stations = {}
    offset = 0
    limit = 10000
    page = 0
    while True:
        cache_name = os.path.join("eccc_1981_2010", f"month13_{offset}.json")
        data = _fetch(GEOMET_NORMALS_URL, cache_name,
                       params={"MONTH": 13, "limit": limit, "offset": offset, "f": "json"},
                       is_json=True)
        feats = data.get("features", [])
        for feat in feats:
            p = feat["properties"]
            name = p["E_NORMAL_ELEMENT_NAME"]
            if name not in ("Total degree-days below 18 deg C", "Total degree-days Above 18 deg C"):
                continue
            cid = p["CLIMATE_IDENTIFIER"]
            rec = stations.setdefault(cid, {
                "station": p["STATION_NAME"], "lat": feat["geometry"]["coordinates"][1],
                "lon": feat["geometry"]["coordinates"][0], "normals_period": "1981-2010",
            })
            if "below" in name.lower():
                rec["hdd"] = p["VALUE"]
            else:
                rec["cdd"] = p["VALUE"]
        page += 1
        if len(feats) < limit:
            break
        offset += limit
    stations = {k: v for k, v in stations.items() if "hdd" in v and "cdd" in v}
    print(f"  1981-2010: {len(stations)} stations with annual HDD+CDD (fallback pool)")
    return stations


# ---------------------------------------------------------------------------
# Step 4: FSA centroids from FSA_Maps/<PROV>.geojson
# ---------------------------------------------------------------------------

def _iter_coords(geom):
    t = geom["type"]
    coords = geom["coordinates"]
    if t == "Polygon":
        for ring in coords:
            for lon, lat in ring:
                yield lon, lat
    elif t == "MultiPolygon":
        for poly in coords:
            for ring in poly:
                for lon, lat in ring:
                    yield lon, lat


def fsa_centroids():
    centroids = {}
    for fname in os.listdir(FSA_MAPS_DIR):
        if not fname.endswith(".geojson"):
            continue
        prov_geo = fname[:-len(".geojson")]
        with open(os.path.join(FSA_MAPS_DIR, fname), encoding="utf-8") as f:
            gj = json.load(f)
        for feat in gj["features"]:
            props = feat["properties"]
            fsa = props.get("CFSAUID") or props.get("FSA") or props.get("fsa")
            if not fsa:
                continue
            lons, lats = [], []
            for lon, lat in _iter_coords(feat["geometry"]):
                lons.append(lon)
                lats.append(lat)
            if not lons:
                continue
            centroids[fsa] = (sum(lats) / len(lats), sum(lons) / len(lons))
    return centroids


# ---------------------------------------------------------------------------
# Step 5: assign HDD/CDD per FSA via IDW over nearest stations
# ---------------------------------------------------------------------------

def assign_climate(centroids, all_stations):
    station_list = list(all_stations.values())
    out = {}
    for fsa, (flat, flon) in centroids.items():
        dists = sorted(
            ((haversine_km(flat, flon, s["lat"], s["lon"]), s) for s in station_list),
            key=lambda x: x[0],
        )
        within = [d for d in dists if d[0] <= IDW_RADIUS_KM][:IDW_K]
        if not within:
            within = dists[:1]
        if len(within) == 1:
            dist, s = within[0]
            out[fsa] = {"hdd": round(s["hdd"], 1), "cdd": round(s["cdd"], 1),
                        "station": s["station"], "dist_km": round(dist, 1),
                        "normals_period": s["normals_period"]}
        else:
            weights = [1.0 / max(d, 0.1) for d, _ in within]
            wsum = sum(weights)
            hdd = sum(w * s["hdd"] for w, (_, s) in zip(weights, within)) / wsum
            cdd = sum(w * s["cdd"] for w, (_, s) in zip(weights, within)) / wsum
            periods = sorted({s["normals_period"] for _, s in within})
            out[fsa] = {
                "hdd": round(hdd, 1), "cdd": round(cdd, 1),
                "station": [s["station"] for _, s in within],
                "dist_km": [round(d, 1) for d, _ in within],
                "normals_period": periods[0] if len(periods) == 1 else "mixed:" + ",".join(periods),
            }
    return out


def main():
    os.makedirs(CACHE_DIR, exist_ok=True)
    os.makedirs(OUT_DIR, exist_ok=True)

    print("Loading 1991-2020 composite station inventory...")
    composites = load_1991_2020_inventory()
    print(f"  {len(composites)} composite stations")

    print("Resolving 1991-2020 normals (preferred)...")
    stations_9120 = build_1991_2020_stations(composites)

    print("Building 1981-2010 fallback pool...")
    stations_8110 = build_1981_2010_stations()

    all_stations = dict(stations_8110)
    all_stations.update(stations_9120)  # 1991-2020 takes priority where both resolved by name key
    print(f"Total usable stations: {len(all_stations)} "
          f"({len(stations_9120)} at 1991-2020, {len(all_stations) - len(stations_9120)} fallback-only)")

    print("Computing FSA centroids from FSA_Maps geojsons...")
    centroids = fsa_centroids()
    print(f"  {len(centroids)} FSAs with geometry")

    print("Assigning HDD/CDD via IDW of nearest stations...")
    result = assign_climate(centroids, all_stations)

    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(result, f, separators=(",", ":"))
    size_kb = os.path.getsize(OUT_PATH) / 1024
    print(f"wrote {OUT_PATH} -- {len(result):,} FSAs ({size_kb:.0f} KB)")

    # --- validation ---
    def band(fsas):
        vals = [result[f]["hdd"] for f in fsas if f in result]
        return vals

    print("\nSpot checks:")
    spot = ["K1A", "K2P", "V6B", "V5K", "R3C", "R2C", "M5V", "H2Y", "T2P", "B3H"]
    print(f"{'FSA':<6}{'HDD':>8}{'CDD':>8}  {'period':<26}station")
    for fsa in spot:
        r = result.get(fsa)
        if not r:
            print(f"{fsa:<6}  (no data)")
            continue
        st = r["station"] if isinstance(r["station"], str) else "+".join(r["station"])
        print(f"{fsa:<6}{r['hdd']:>8.0f}{r['cdd']:>8.1f}  {r['normals_period']:<26}{st}")

    all_hdd = [r["hdd"] for r in result.values()]
    all_hdd.sort()
    n = len(all_hdd)
    print(f"\nNational HDD distribution (n={n}): "
          f"min={all_hdd[0]:.0f} p10={all_hdd[n // 10]:.0f} p50={all_hdd[n // 2]:.0f} "
          f"p90={all_hdd[9 * n // 10]:.0f} max={all_hdd[-1]:.0f}")


if __name__ == "__main__":
    main()
