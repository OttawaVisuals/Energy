"""
pipeline_etl.py -- CER pipeline incidents + throughput/capacity key points
for the District Energy page's points map.

INPUTS (all Canada Energy Regulator open data, Open Government Licence - Canada;
downloaded to Python/pipeline_cache/, gitignored scratch):
  * Pipeline incidents       open.canada.ca dataset fd17f08f-f14d-433f-91df-c90a34e1e9a6
      https://www.cer-rec.gc.ca/open/incident/pipeline-incidents-data.csv  (cp1252)
  * Throughput and capacity  open.canada.ca dataset dc343c43-a592-4a27-8ee7-c77df56afb34
      23 per-pipeline CSVs under https://www.cer-rec.gc.ca/open/energy/throughput-capacity/
      Gas pipelines report DAILY, oil/liquids pipelines report MONTHLY.
      Not used: apportionment.csv (nominations, not flow), archived-trans-mountain
      (superseded by the current Trans Mountain file; would double-count 2006-2024).

OUTPUT: districtenergy_json/pipelines.json
  meta       sources, retrieval date, counts, every drop/gap quantified
  incidents  columnar rows (see meta.incident_fields)
  flows      one record per (pipeline, key point, direction, trade type) with
             per-year mean throughput and capacity (1000 m3/d)
  no_coords  key points the pipeline reports WITHOUT latitude/longitude. They are
             kept (with their latest flow) so the page can list them, never
             silently dropped and never given invented coordinates.

WHAT IT IS NOT
  * Route geometry. The CER publishes no open pipeline-line dataset that we found;
    the interactive map's line layer is a WMS with no licence statement, so it is
    deliberately not used. This is a POINTS map.
  * Only CER-regulated (federal, interprovincial/international) systems.
  * Throughput is measured at reporting key points, not along the whole line.
    Never sum key points of one pipeline: the same molecule is counted at each.
  * Gas and oil volumes are both '1000 m3/d' but are not energy-comparable.

DATA-HONESTY RAILS
  * Required columns are asserted; any missing column aborts the run.
  * Volumes 'Not Provided' / 'Not Applicable' stay null (shown as such), never 0.
  * Per-year n (days for gas, months for oil) is stored; a year is only called
    'full' when n >= 360 days (gas) / 12 months (oil).
  * Conflicting coordinates for one key point: the most common pair is used and
    the count of disagreeing rows is reported in meta.

Run:  python -I Python/pipeline_etl.py            (downloads if cache is empty)
      python -I Python/pipeline_etl.py --refresh  (re-download everything)
"""
import csv, json, os, sys, glob, datetime, urllib.request, collections, statistics

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(ROOT, "Python", "pipeline_cache")
OUT = os.path.join(ROOT, "districtenergy_json", "pipelines.json")
UA = {"User-Agent": "energy-suite-etl/1.0 (+https://github.com/OttawaVisuals/Energy)"}
INC_URL = "https://www.cer-rec.gc.ca/open/incident/pipeline-incidents-data.csv"
PKG = "https://open.canada.ca/data/api/action/package_show?id=dc343c43-a592-4a27-8ee7-c77df56afb34"
SKIP = {"apportionment.csv", "archived-trans-mountain-throughput-and-capacity.csv"}

PROV = {"Alberta": "AB", "British Columbia": "BC", "Manitoba": "MB", "New Brunswick": "NB",
        "Newfoundland and Labrador": "NL", "Nova Scotia": "NS", "Northwest Territories": "NT",
        "Nunavut": "NU", "Ontario": "ON", "Prince Edward Island": "PE", "Quebec": "QC",
        "Saskatchewan": "SK", "Yukon": "YT"}


FIXES = []


def get(url):
    return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=180).read()


def download(refresh):
    os.makedirs(CACHE, exist_ok=True)
    targets = [(INC_URL, "incidents.csv")]
    pkg = json.loads(get(PKG))["result"]
    for r in pkg["resources"]:
        u = r["url"]
        if "/open/energy/throughput-capacity/" in u and u.endswith(".csv") and "dictionary" not in u:
            targets.append((u, os.path.basename(u)))
    for u, f in targets:
        p = os.path.join(CACHE, f)
        if refresh or not os.path.exists(p) or os.path.getsize(p) == 0:
            print("download", f)
            open(p, "wb").write(get(u))
    return pkg.get("metadata_modified")


def read_csv(path):
    raw = open(path, "rb").read()
    try:
        txt = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        txt = raw.decode("cp1252")
    return list(csv.DictReader(txt.splitlines()))


def num(s):
    try:
        return float(s)
    except (TypeError, ValueError):
        return None


def need(rows, cols, name):
    missing = [c for c in cols if c not in rows[0]]
    if missing:
        sys.exit(f"ABORT {name}: missing columns {missing}")


# ---------------------------------------------------------------- incidents
def build_incidents():
    rows = read_csv(os.path.join(CACHE, "incidents.csv"))
    need(rows, ["Incident Number", "Incident Types", "Reported Date", "Nearest Populated Centre",
                "Province", "Company", "Status", "Latitude", "Longitude",
                "Approximate Volume Released (m3)", "Substance", "Release Type", "Significant",
                "Year", "What Happened", "Why It Happened"], "incidents")
    q = {"rows_in": len(rows), "no_coords": 0, "dup_numbers": 0, "volume_numeric": 0,
         "volume_not_provided": 0, "volume_not_applicable": 0, "other_province": []}
    seen, out = set(), []
    for r in rows:
        n = r["Incident Number"].strip()
        if n in seen:
            q["dup_numbers"] += 1
            continue
        seen.add(n)
        lat, lon = num(r["Latitude"]), num(r["Longitude"])
        if lat is None or lon is None:
            q["no_coords"] += 1
            continue
        v = r["Approximate Volume Released (m3)"].strip()
        vol = num(v)
        if vol is not None:
            q["volume_numeric"] += 1
        elif v == "Not Provided":
            q["volume_not_provided"] += 1
        elif v == "Not Applicable":
            q["volume_not_applicable"] += 1
        else:
            sys.exit(f"ABORT: unexpected volume value {v!r} in {n}")
        prov = PROV.get(r["Province"].strip())
        if prov is None:
            q["other_province"].append(r["Province"].strip())
            prov = r["Province"].strip()
        out.append([n, int(r["Year"]), round(lat, 4), round(lon, 4), prov,
                    r["Company"].strip(), r["Substance"].strip(), r["Release Type"].strip(),
                    vol, 1 if r["Significant"].strip() == "Yes" else 0, r["Status"].strip(),
                    r["Incident Types"].strip(), r["What Happened"].strip(),
                    r["Why It Happened"].strip(), r["Nearest Populated Centre"].strip()])
    q["rows_out"] = len(out)
    out.sort(key=lambda x: (x[1], x[0]))
    return out, q


# -------------------------------------------------------------------- flows
def build_flows():
    files = sorted(glob.glob(os.path.join(CACHE, "*throughput-and-capacity.csv")))
    files = [f for f in files if os.path.basename(f) not in SKIP]
    flows, nocoord, q = [], [], {"files": 0, "rows_in": 0, "groups": 0, "coord_conflict_rows": 0,
                                 "groups_without_coords": 0}
    for f in files:
        rows = read_csv(f)
        base = os.path.basename(f)
        gas = "Throughput (GJ/d)" in rows[0]
        need(rows, ["Date", "Year", "Company", "Pipeline", "Key Point", "Latitude", "Longitude",
                    "Direction Of Flow", "Trade Type", "Throughput (1000 m3/d)"], base)
        q["files"] += 1
        q["rows_in"] += len(rows)
        groups = collections.defaultdict(list)
        for r in rows:
            groups[(r["Pipeline"].strip(), r["Key Point"].strip(),
                    r["Direction Of Flow"].strip(), r["Trade Type"].strip())].append(r)
        for (pipe, kp, d, trade), rs in groups.items():
            # per date: sum products (oil); capacity repeated per product row -> take once
            bydate = collections.OrderedDict()
            for r in rs:
                t = num(r["Throughput (1000 m3/d)"])
                if gas:
                    cap, cap2 = num(r["Capacity (1000 m3/d)"]), None
                else:
                    cap, cap2 = num(r.get("Nameplate Capacity (1000 m3/d)")), num(r.get("Available Capacity (1000 m3/d)"))
                e = bydate.setdefault(r["Date"], {"tp": None, "cap": cap, "avail": cap2, "y": int(r["Year"])})
                if t is not None:
                    e["tp"] = (e["tp"] or 0) + t
            yr = collections.defaultdict(lambda: {"tp": [], "cap": [], "avail": []})
            for e in bydate.values():
                if e["tp"] is not None:
                    yr[e["y"]]["tp"].append(e["tp"])
                if e["cap"] is not None:
                    yr[e["y"]]["cap"].append(e["cap"])
                if e["avail"] is not None:
                    yr[e["y"]]["avail"].append(e["avail"])
            yrs = {}
            for y, v in sorted(yr.items()):
                if not v["tp"]:
                    continue
                full_n = 360 if gas else 12
                rec = {"tp": round(statistics.mean(v["tp"]), 2), "n": len(v["tp"]),
                       "full": 1 if len(v["tp"]) >= full_n else 0}
                if v["cap"]:
                    rec["cap"] = round(statistics.mean(v["cap"]), 2)
                if v["avail"]:
                    rec["avail"] = round(statistics.mean(v["avail"]), 2)
                yrs[y] = rec
            coords = collections.Counter((num(r["Latitude"]), num(r["Longitude"])) for r in rs
                                         if num(r["Latitude"]) is not None and num(r["Longitude"]) is not None)
            rec = {"pipeline": pipe, "company": rs[0]["Company"].strip(), "kp": kp,
                   "commodity": "gas" if gas else "oil", "dir": d, "trade": trade,
                   "years": {str(k): v for k, v in yrs.items()}}
            q["groups"] += 1
            if coords:
                (lat, lon), c = coords.most_common(1)[0]
                if lon > 0:
                    # Source sign error: Suffield key points are reported at +110.x
                    # (Asia). Southern Alberta is -110.x. Fixed explicitly and logged.
                    FIXES.append(f"{pipe} / {kp}: longitude {lon} -> {-lon} (positive in source; Canada is west)")
                    lon = -lon
                q["coord_conflict_rows"] += sum(coords.values()) - c
                rec["lat"], rec["lon"] = round(lat, 4), round(lon, 4)
                flows.append(rec)
            else:
                q["groups_without_coords"] += 1
                nocoord.append(rec)
    return flows, nocoord, q


def main():
    refresh = "--refresh" in sys.argv
    modified = download(refresh)
    inc, iq = build_incidents()
    flows, nocoord, fq = build_flows()
    all_years = sorted({int(y) for r in flows + nocoord for y in r["years"]})
    meta = {
        "built": datetime.date.today().isoformat(),
        "source_modified": modified,
        "licence": "Open Government Licence - Canada",
        "sources": {
            "incidents": "https://open.canada.ca/data/en/dataset/fd17f08f-f14d-433f-91df-c90a34e1e9a6",
            "throughput": "https://open.canada.ca/data/en/dataset/dc343c43-a592-4a27-8ee7-c77df56afb34"},
        "incident_fields": ["number", "year", "lat", "lon", "prov", "company", "substance", "release_type",
                            "volume_m3", "significant", "status", "types", "what", "why", "centre"],
        "incident_quality": iq,
        "flow_quality": fq,
        "coordinate_fixes": FIXES,
        "flow_years": [all_years[0], all_years[-1]],
        "units": "1000 m3/d (gas and oil are NOT energy-comparable)",
        "notes": [
            "Points map: no route geometry (no open CER line dataset found).",
            "Gas = daily reporting, oil = monthly; n is days or months with a value.",
            "Key points are measurement locations, not the whole pipeline; do not sum them.",
            "Dictionary describes gas capacity as GJ/d but the column is 1000 m3/d; the column name is used.",
        ],
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump({"meta": meta, "incidents": inc, "flows": flows, "no_coords": nocoord},
              open(OUT, "w"), separators=(",", ":"))
    print(json.dumps({"incident_quality": iq, "flow_quality": fq}, indent=1))
    print("flows with coords:", len(flows), "| without:", len(nocoord), "| bytes:", os.path.getsize(OUT))


if __name__ == "__main__":
    main()
