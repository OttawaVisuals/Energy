"""
District Energy Explorer — data pipeline.

INPUTS (districtenergy/raw/, gitignored — re-download, don't commit):
  CEEDC_IEF_district_energy.xlsx   254 district energy systems (de == True)
  CEEDC_IEF_public.xlsx            3,644 Innovative Energy Facilities (the superset:
                                   district energy + cogeneration + renewable
                                   electricity + biofuel/biomass production)
  Both are published by CEEDC as public downloads from their own district energy
  dashboard (https://cieedacdb.rem.sfu.ca:8006/district-energy-inventory/ →
  "Download data"). Sheet layout: row 1 = units, row 2 = field names, row 3+ = data.

INPUTS (districtenergy/curated/, committed on main — hand-entered, not regenerable):
  report_2023.json   tables transcribed from CEEDC's published 2023 report
  projects.json      curated project/news list

INPUTS (already in the repo):
  geo_json/*.json          per-province FSA polygons (lon/lat) — unioned here into
                           province outlines for the facility map
  lfsa000b21a_e.json       national FSA file, source CRS — the only source of Yukon
                           geometry, since geo_json/ has no YT (same gap
                           Python/canada_boundary.py documents and works around)

OUTPUTS (districtenergy_json/, gitignored on main, published to gh-pages):
  facilities.json      254 district energy systems, full detail
  ief_context.json     3,390 non-district-energy IEF facilities, minimal — the map's
                       context layer
  aggregates.json      province / fuel / service / vintage / municipality rollups,
                       every one carrying its own n
  canada_outline.json  simplified province outlines
  report_2023.json     copy of the curated report tables
  projects.json        copy of the curated project list
  meta.json            provenance, QA counts, and the file-vs-report delta

THE ONE THING TO UNDERSTAND BEFORE READING THE NUMBERS
------------------------------------------------------
CEEDC's public download does NOT reproduce the totals in CEEDC's published report.
Respondent-confidential values were withheld from the public file, so every total
derived here comes out lower, on a smaller n, than the published analysis:

    steam capacity        file 3,757 MW (n=50)   report 3,990 MW (n=57)
    hot water capacity    file   932 MW (n=54)   report 1,024 MW (n=68)
    steam production      file 4.05M MWh (n=31)  report 5.13M MWh (n=57)
    electrical capacity   file   276 MW (n=25)   report   314 MW (n=26)

Both are correct; they answer different questions. This script therefore keeps them
in separate files and writes the delta into meta.json, so the page can show the gap
rather than average it away. Never present a file-derived total as the report's
figure, or vice versa.

Sources
  Griffin, B. (2023). District Energy in Canada. CEEDC, Simon Fraser University,
  prepared for CanmetENERGY-Ottawa, Natural Resources Canada.
  IEA DHC (2024). District heating network generation definitions. February 2024.

Usage:  python Python/district_energy_etl.py
"""

import glob
import json
import os
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone

import openpyxl

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from canada_boundary import _valid_polygon, inverse_lambert, simplified_rings  # noqa: E402
from shapely.ops import unary_union  # noqa: E402

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(REPO, "districtenergy", "raw")
CURATED = os.path.join(REPO, "districtenergy", "curated")
OUT = os.path.join(REPO, "districtenergy_json")
GEO_JSON_DIR = os.path.join(REPO, "geo_json")
LFSA_ROOT = os.path.join(REPO, "lfsa000b21a_e.json")

DE_XLSX = os.path.join(RAW, "CEEDC_IEF_district_energy.xlsx")
PUBLIC_XLSX = os.path.join(RAW, "CEEDC_IEF_public.xlsx")

# ── Fuel flags ────────────────────────────────────────────────────────────
# The workbook stores each fuel as a separate `<code>_used` column holding the
# string "Yes" or nothing at all. There is no "primary fuel" column: CEEDC's
# Tableau dashboard derives one upstream, inside its .hyper extract, and that
# derivation is not published. Rather than guess at their priority order we keep
# the FULL fuel set per system — which is the more interesting fact anyway, since
# the report's own headline is that 42% of systems are multi-energy.
#
# The label for each code comes from the workbook's Metadata sheet. Careful: that
# sheet's "Detail" column is misaligned from row 60 onward (it lags the "Field"
# column by exactly 4 rows), so `geo_used` reads as "Solid Biomass" and
# `waste_used` as "Spent Pulping Liquor" if taken at face value. The mapping
# below is the corrected one, cross-checked against the fuel legend CEEDC's own
# published dashboard renders.
FUELS = [
    ("ng", "Natural gas", "fossil"),
    ("hfo", "Heavy fuel oil", "fossil"),
    ("lfo", "Light fuel oil / diesel", "fossil"),
    ("biod", "Biodiesel", "renewable"),
    ("biog", "Biogas", "renewable"),
    ("biom", "Solid biomass", "renewable"),
    ("spl", "Spent pulping liquor", "renewable"),
    ("geo", "Geoexchange / geothermal", "renewable"),
    ("hr", "Heat recovery", "recovered"),
    ("cw", "Cooling water (sea / lake)", "recovered"),
    ("waste", "Waste (MSW / landfill gas)", "recovered"),
    ("solth", "Solar thermal", "renewable"),
    ("pg", "Process gas", "fossil"),
    ("steam", "Purchased steam", "purchased"),
    ("solpv", "Solar PV", "renewable"),
    ("hydro", "Hydroelectricity", "renewable"),
    ("wind", "Wind", "renewable"),
    ("elec", "Purchased electricity", "purchased"),
]
FUEL_LABEL = {c: lbl for c, lbl, _ in FUELS}
FUEL_CLASS = {c: cls for c, _, cls in FUELS}

SERVICES = [("hs", "Heat (steam)"), ("hw", "Heat (hot water)"), ("cw", "Cooling (water)")]

PROV_NAME = {
    "BC": "British Columbia", "AB": "Alberta", "SK": "Saskatchewan", "MB": "Manitoba",
    "ON": "Ontario", "QC": "Quebec", "NB": "New Brunswick", "NS": "Nova Scotia",
    "PE": "Prince Edward Island", "NL": "Newfoundland and Labrador",
    "YT": "Yukon", "NT": "Northwest Territories", "NU": "Nunavut",
}
# geo_json/ uses "NF" for Newfoundland; the CEEDC data uses "NL".
GEOFILE_TO_PROV = {"NF": "NL"}


# ── small helpers ─────────────────────────────────────────────────────────
def s(v):
    """Trimmed string, or None. The workbook carries stray double spaces and
    trailing spaces in facility/city names ('CFB Halifax  - Bedford',
    'Mississauga '), which would otherwise split identical cities into two
    buckets when grouped."""
    if v is None:
        return None
    t = " ".join(str(v).split())
    return t or None


def num(v):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if f != f else f  # drop NaN


def tri(v):
    """Tri-state flag: True / False / None.

    Preserving the None matters. `de_cw` is "No" for 98 operating systems and
    absent for 99 more — 'this system has no cooling' and 'nobody told us whether
    it has cooling' are different facts, and collapsing them to False would
    silently invent 99 confirmed no-cooling systems."""
    t = s(v)
    if t is None:
        return None
    t = t.lower()
    if t in ("yes", "true", "1", "y"):
        return True
    if t in ("no", "false", "0", "n"):
        return False
    return None


def read_ief(path):
    """Rows of the IEF sheet as dicts. Row 1 is units, row 2 is field names."""
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb["IEF"]
    rows = list(ws.iter_rows(values_only=True))
    wb.close()
    hdr = [s(c) or "" for c in rows[1]]
    out = []
    for r in rows[2:]:
        if not any(c not in (None, "") for c in r):
            continue
        out.append(dict(zip(hdr, r)))
    return hdr, out


# ── IEA DHC generation ladder ─────────────────────────────────────────────
# IEA DHC ExCo, "District heating network generation definitions", Feb 2024:
#   1G  steam as the heat carrier, INDEPENDENT OF TEMPERATURE
#   2G  liquid water above 100 C (superheated)
#   3G  between 100 C and 70 C
#   4G  maximum forward flow temperature of 70 C
#       (70 C is the threshold for thermal disinfection of domestic hot water)
#   5G  the ExCo explicitly recommends AGAINST the term. Networks used mainly as
#       a source for decentralised heat pumps should be called "thermal source
#       networks" and treated as a SUBCLASS of 4G, not an upgrade over it.
#
# Two deliberate choices:
#  * 1G is never inferred here from a temperature, because IEA defines it by
#    carrier. A system's steam flag makes it a 1G network by definition; that is
#    reported separately, with its own n, rather than folded into this ladder.
#  * Exactly 70 C is assigned to 4G. It sits inside both the 3G range ("between
#    100 and 70") and the 4G rule ("maximum of 70"); the 4G rule is the more
#    specific of the two, and 70 C is the physical threshold it names.
TSN_MAX_SUPPLY_C = 30.0   # at/near ambient — a thermal source network
SUSPECT_HW_SUPPLY_C = 150.0  # above this, almost certainly a steam temperature


def iea_generation(supply_c):
    if supply_c is None:
        return None
    if supply_c > 100:
        return "2G"
    if supply_c > 70:
        return "3G"
    return "4G"


# ── province outlines ─────────────────────────────────────────────────────
def build_province_outlines(tolerance_deg=0.06, min_area_deg2=0.02):
    """Union each province's FSA polygons into a simplified outline.

    Reuses canada_boundary.py's ring validation, Lambert inverse and
    simplification rather than re-deriving them — including its Yukon
    workaround, since geo_json/ has never had a YT file and 4 district energy
    systems sit in Yukon."""
    outlines = {}
    for path in sorted(glob.glob(os.path.join(GEO_JSON_DIR, "*.json"))):
        code = os.path.splitext(os.path.basename(path))[0]
        prov = GEOFILE_TO_PROV.get(code, code)
        polys = []
        with open(path, encoding="utf-8") as fh:
            d = json.load(fh)
        for feat in d["features"]:
            geom = feat["geometry"]
            parts = geom["coordinates"] if geom["type"] == "MultiPolygon" else [geom["coordinates"]]
            for poly_coords in parts:
                p = _valid_polygon(poly_coords[0])
                if p is not None:
                    polys.append(p)
        if polys:
            outlines[prov] = simplified_rings(unary_union(polys), tolerance_deg, min_area_deg2)
        print(f"    outline {prov}: {len(outlines.get(prov, []))} rings")

    if "YT" not in outlines and os.path.exists(LFSA_ROOT):
        polys = []
        with open(LFSA_ROOT, encoding="utf-8") as fh:
            lfsa = json.load(fh)
        for feat in lfsa["features"]:
            if not str(feat["properties"]["CFSAUID"]).startswith("Y"):
                continue
            geom = feat["geometry"]
            parts = geom["coordinates"] if geom["type"] == "MultiPolygon" else [geom["coordinates"]]
            for poly_coords in parts:
                ring = [inverse_lambert(x, y) for x, y in poly_coords[0]]
                p = _valid_polygon(ring)
                if p is not None:
                    polys.append(p)
        if polys:
            outlines["YT"] = simplified_rings(unary_union(polys), tolerance_deg, min_area_deg2)
            print(f"    outline YT: {len(outlines['YT'])} rings (from {os.path.basename(LFSA_ROOT)})")
    return outlines


# ── facility shaping ──────────────────────────────────────────────────────
def shape_facility(r, qa):
    fuels = [c for c, _, _ in FUELS if tri(r.get(c + "_used"))]
    quantities = {}
    for c, _, _ in FUELS:
        q = num(r.get(c + "_quantity"))
        if q is not None:
            quantities[c] = q

    services = {}
    for code, _ in SERVICES:
        services[code] = tri(r.get("de_" + code))

    det = {}
    for code, _ in SERVICES:
        d = {
            "buildings": num(r.get(f"de_{code}_bldg")),
            "floor_ft2": num(r.get(f"de_{code}_floor")),
            "pipe_ft": num(r.get(f"de_{code}_length")),
            "capacity_mw": num(r.get(f"de_{code}_capacity")),
            "production_mwh": num(r.get(f"de_{code}_production")),
            "supply_c": num(r.get(f"de_{code}_supply")),
            "return_c": num(r.get(f"de_{code}_return")),
            "metered": tri(r.get(f"de_{code}_meter")),
            "storage": tri(r.get(f"de_{code}_storage")),
        }
        if any(v is not None for v in d.values()):
            det[code] = {k: v for k, v in d.items() if v is not None}

    # Implied capacity factor, only where BOTH capacity and production are real.
    for code, _ in SERVICES:
        d = det.get(code)
        if not d:
            continue
        cap, prod = d.get("capacity_mw"), d.get("production_mwh")
        if cap and prod and cap > 0:
            cf = prod / (cap * 8760.0) * 100.0
            d["capacity_factor_pct"] = round(cf, 1)
            if cf > 100:
                qa["capacity_factor_over_100"].append(s(r.get("facility_name")))

    hw_supply = det.get("hw", {}).get("supply_c")
    gen = iea_generation(hw_supply)
    temp_suspect = hw_supply is not None and hw_supply >= SUSPECT_HW_SUPPLY_C
    if temp_suspect:
        qa["hw_supply_suspect"].append([s(r.get("facility_name")), hw_supply])

    users = [k[5:] for k in r if k.startswith("user_") and tri(r.get(k))]

    muni = s(r.get("municipality_type"))
    if muni:
        muni = muni.lower()   # workbook ships both 'large' and 'Large'
        if muni not in ("rural", "small", "medium", "large"):
            qa["municipality_unexpected"].append(muni)
            muni = None

    year_c = num(r.get("year_commission"))
    status = s(r.get("status"))
    if status == "Planned" and year_c and year_c < 2024:
        # e.g. University of Lethbridge: status Planned, commissioned 1970.
        # Almost certainly a planned expansion or conversion of an existing
        # system. Flagged, kept as-is — not silently reclassified.
        qa["planned_with_past_year"].append([s(r.get("facility_name")), year_c])

    return {
        "id": int(r["ID"]),
        "name": s(r.get("facility_name")),
        "owner": s(r.get("owner_1")),
        "owner_2": s(r.get("owner_2")),
        "operator": s(r.get("operator")),
        "city": s(r.get("city")),
        "prov": s(r.get("province")),
        "lat": num(r.get("latitude")),
        "lon": num(r.get("longitude")),
        "status": status,
        "year": int(year_c) if year_c else None,
        "year_reported": int(num(r.get("year_reported"))) if num(r.get("year_reported")) else None,
        "muni": muni,
        "naics": int(num(r.get("naics"))) if num(r.get("naics")) else None,
        "chp": tri(r.get("chp")) or False,
        "re": tri(r.get("re")) or False,
        "bio": tri(r.get("bio")) or False,
        "fuels": fuels,
        "fuel_gj": quantities or None,
        "services": services,
        "detail": det or None,
        "users": users or None,
        "iea_generation": gen,
        "iea_temp_suspect": temp_suspect or None,
        "is_tsn": (hw_supply is not None and hw_supply <= TSN_MAX_SUPPLY_C) or None,
        "elec_capacity_mw": num(r.get("system_elec_capacity")),
        "elec_production_mwh": num(r.get("system_elec_production")),
        "source": s(r.get("source_1")),
        "source_2": s(r.get("source_2")),
    }


def strip_nulls(d):
    return {k: v for k, v in d.items() if v is not None}


# ── aggregates ────────────────────────────────────────────────────────────
def det_of(f, code):
    """Per-service detail block, or {}. `detail` is None (not {}) on systems with
    no operating data at all — 90 of the 238 operating systems — so a plain
    .get('detail', {}) returns None for exactly the rows most likely to break a
    lookup chain."""
    return (f.get("detail") or {}).get(code) or {}


def build_aggregates(fac):
    """Every rollup carries its own n. Denominators differ field by field
    because coverage does — quoting one n for the page as a whole would be
    wrong for almost every chart on it."""
    op = [f for f in fac if f["status"] == "Operating"]
    n_op = len(op)

    def cap_sum(code):
        vals = [det_of(f, code)["capacity_mw"] for f in op
                if det_of(f, code).get("capacity_mw") is not None]
        return {"total_mw": round(sum(vals), 1), "n": len(vals)}

    def prod_sum(code):
        vals = [det_of(f, code)["production_mwh"] for f in op
                if det_of(f, code).get("production_mwh") is not None]
        return {"total_mwh": round(sum(vals)), "n": len(vals)}

    # province
    prov = defaultdict(lambda: {"systems": 0, "chp": 0, "renewable": 0,
                                "cap_mw": 0.0, "cap_n": 0, "fuels": Counter()})
    for f in op:
        p = prov[f["prov"]]
        p["systems"] += 1
        p["chp"] += 1 if f["chp"] else 0
        p["renewable"] += 1 if any(FUEL_CLASS[c] == "renewable" for c in f["fuels"]) else 0
        for code, _ in SERVICES:
            c = det_of(f, code).get("capacity_mw")
            if c is not None:
                p["cap_mw"] += c
                p["cap_n"] += 1
        for c in f["fuels"]:
            p["fuels"][c] += 1
    provinces = []
    for code, v in sorted(prov.items(), key=lambda kv: -kv[1]["systems"]):
        provinces.append({
            "prov": code, "name": PROV_NAME.get(code, code),
            "systems": v["systems"], "chp": v["chp"], "renewable": v["renewable"],
            "capacity_mw": round(v["cap_mw"], 1), "capacity_n": v["cap_n"],
            "top_fuels": [{"fuel": c, "label": FUEL_LABEL[c], "n": n}
                          for c, n in v["fuels"].most_common(4)],
        })

    # fuels — single vs multi, mirroring the report's own Table 8 split
    fuel_rows = []
    for c, lbl, cls in FUELS:
        single = sum(1 for f in op if f["fuels"] == [c])
        multi = sum(1 for f in op if c in f["fuels"] and len(f["fuels"]) > 1)
        if single or multi:
            fuel_rows.append({"fuel": c, "label": lbl, "class": cls,
                              "single": single, "multi": multi, "total": single + multi})
    fuel_rows.sort(key=lambda r: -r["total"])

    n_fuel_known = sum(1 for f in op if f["fuels"])
    fuel_mix = Counter(len(f["fuels"]) for f in op)

    # services (tri-state preserved)
    svc = {}
    for code, lbl in SERVICES:
        yes = sum(1 for f in op if f["services"].get(code) is True)
        no = sum(1 for f in op if f["services"].get(code) is False)
        unk = sum(1 for f in op if f["services"].get(code) is None)
        svc[code] = {"label": lbl, "yes": yes, "no": no, "unreported": unk}

    combos = Counter()
    for f in op:
        on = tuple(sorted(c for c, _ in SERVICES if f["services"].get(c) is True))
        if on:
            combos[on] += 1
    n_svc_known = sum(combos.values())

    # vintage
    decades = Counter()
    for f in op:
        if f["year"]:
            decades[(f["year"] // 10) * 10] += 1
    n_year = sum(decades.values())

    # renewables by vintage — the report's "since 2000 at least half of new
    # systems include renewables" claim, recomputed from the public file
    ren_by_era = []
    for lo, hi, lbl in [(0, 1939, "Pre-1940"), (1940, 1960, "1940–1960"),
                        (1961, 1980, "1961–1980"), (1981, 2000, "1981–2000"),
                        (2001, 2010, "2001–2010"), (2011, 9999, "2011–")]:
        era = [f for f in op if f["year"] and lo <= f["year"] <= hi]
        if not era:
            continue
        ren = sum(1 for f in era if any(FUEL_CLASS[c] in ("renewable", "recovered") for c in f["fuels"]))
        ren_by_era.append({"era": lbl, "systems": len(era), "with_renewable": ren,
                           "n_with_fuel": sum(1 for f in era if f["fuels"])})

    # data vintage — year_reported, the fact that makes "the 2023 inventory"
    # a decade of accumulated snapshots rather than one survey
    vintage = Counter(f["year_reported"] for f in op if f["year_reported"])

    # IEA generation ladder
    gen_rows = Counter(f["iea_generation"] for f in op if f["iea_generation"])
    gen_detail = [{
        "name": f["name"], "prov": f["prov"], "city": f["city"], "year": f["year"],
        "supply_c": det_of(f, "hw")["supply_c"],
        "return_c": det_of(f, "hw").get("return_c"),
        "gen": f["iea_generation"], "suspect": bool(f["iea_temp_suspect"]),
        "tsn": bool(f["is_tsn"]), "fuels": f["fuels"],
    } for f in op if f["iea_generation"]]
    gen_detail.sort(key=lambda r: r["supply_c"])

    # municipality size
    muni = Counter(f["muni"] for f in op if f["muni"])

    # customers served
    users = Counter()
    for f in op:
        for u in (f["users"] or []):
            users[u] += 1
    n_users = sum(1 for f in op if f["users"])

    # how much quantitative data each system actually has — the coverage story
    QUANT = [(code, k) for code, _ in SERVICES
             for k in ("capacity_mw", "production_mwh", "floor_ft2", "pipe_ft")]
    density = Counter()
    for f in op:
        density[sum(1 for code, k in QUANT if det_of(f, code).get(k) is not None)] += 1

    return {
        "n_operating": n_op,
        "n_planned": sum(1 for f in fac if f["status"] == "Planned"),
        "n_decommissioned": sum(1 for f in fac if f["status"] == "Decommissioned"),
        "capacity": {code: cap_sum(code) for code, _ in SERVICES},
        "production": {code: prod_sum(code) for code, _ in SERVICES},
        "electrical": {
            "capacity_mw": round(sum(f["elec_capacity_mw"] for f in op
                                     if f["elec_capacity_mw"] is not None), 1),
            "capacity_n": sum(1 for f in op if f["elec_capacity_mw"] is not None),
            "production_mwh": round(sum(f["elec_production_mwh"] for f in op
                                        if f["elec_production_mwh"] is not None)),
            "production_n": sum(1 for f in op if f["elec_production_mwh"] is not None),
        },
        "provinces": provinces,
        "fuels": {"rows": fuel_rows, "n_with_fuel": n_fuel_known,
                  "n_without_fuel": n_op - n_fuel_known,
                  "mix": [{"n_fuels": k, "systems": v} for k, v in sorted(fuel_mix.items())]},
        "services": {"by_type": svc, "n_with_any": n_svc_known,
                     "combos": [{"services": list(k), "systems": v}
                                for k, v in sorted(combos.items(), key=lambda kv: -kv[1])]},
        "vintage_built": {"decades": [{"decade": k, "systems": v} for k, v in sorted(decades.items())],
                          "n": n_year, "n_unknown": n_op - n_year,
                          "oldest": min((f["year"] for f in op if f["year"]), default=None)},
        "renewables_by_era": ren_by_era,
        "data_vintage": {"years": [{"year": k, "systems": v} for k, v in sorted(vintage.items())],
                         "n": sum(vintage.values()), "n_unknown": n_op - sum(vintage.values())},
        "iea_generation": {
            "counts": [{"gen": g, "systems": gen_rows[g]} for g in ("2G", "3G", "4G") if gen_rows[g]],
            "n": sum(gen_rows.values()),
            "n_steam_carrier": svc["hs"]["yes"],
            "systems": gen_detail,
        },
        "municipality": {"rows": [{"size": k, "systems": v}
                                  for k, v in sorted(muni.items(),
                                                     key=lambda kv: ["rural", "small", "medium", "large"].index(kv[0]))],
                         "n": sum(muni.values())},
        "customers": {"rows": [{"user": k, "systems": v} for k, v in users.most_common()],
                      "n": n_users},
        "data_density": {"rows": [{"fields": k, "systems": v} for k, v in sorted(density.items())],
                         "n_zero": density.get(0, 0), "n_quant_fields": len(QUANT)},
    }


def main():
    os.makedirs(OUT, exist_ok=True)
    qa = defaultdict(list)

    print("Reading CEEDC district energy workbook…")
    _, de_rows = read_ief(DE_XLSX)
    print(f"  {len(de_rows)} district energy facilities")

    facilities = [shape_facility(r, qa) for r in de_rows]
    facilities.sort(key=lambda f: (f["prov"] or "", f["name"] or ""))

    print("Reading full IEF workbook for the map context layer…")
    _, pub_rows = read_ief(PUBLIC_XLSX)
    de_ids = {f["id"] for f in facilities}
    context = []
    for r in pub_rows:
        rid = int(r["ID"])
        if rid in de_ids:
            continue
        lat, lon = num(r.get("latitude")), num(r.get("longitude"))
        if lat is None or lon is None:
            continue
        kinds = []
        if tri(r.get("chp")):
            kinds.append("chp")
        if tri(r.get("re")):
            kinds.append("re")
        if tri(r.get("bio")):
            kinds.append("bio")
        # Minimal by design: this layer is drawn at 0.28 opacity with
        # pointer-events disabled, purely to show district energy against the
        # whole innovative-energy fleet. Names and statuses would add ~40% to
        # the payload for something the page never renders. 3 dp ≈ 110 m,
        # far finer than a 900px national map can resolve.
        context.append({
            "id": rid, "prov": s(r.get("province")),
            "lat": round(lat, 3), "lon": round(lon, 3), "kind": kinds,
        })
    print(f"  {len(context)} non-district-energy IEF facilities for context")

    aggregates = build_aggregates(facilities)

    print("Building province outlines…")
    outlines = build_province_outlines()

    with open(os.path.join(CURATED, "report_2023.json"), encoding="utf-8") as fh:
        report = json.load(fh)
    with open(os.path.join(CURATED, "projects.json"), encoding="utf-8") as fh:
        projects = json.load(fh)

    # ── the file-vs-report delta, computed rather than asserted ────────────
    rep_cap = {r["type"]: r["capacity_mw"] for r in report["capacity_by_type"]["rows"]}
    rep_gen = {r["type"]: r["generation_gwh"] for r in report["generation_by_type"]["rows"]}
    delta = []
    for code, label, rep_key, gen_key in [
        ("hs", "Heating (Steam)", "Heating (Steam)", "Heating (Steam)"),
        ("hw", "Heating (Hot Water)", "Heating (Hot Water)", "Heating (Hot Water)"),
        ("cw", "Cooling", "Cooling", "Cooling"),
    ]:
        delta.append({
            "type": label,
            "file_capacity_mw": aggregates["capacity"][code]["total_mw"],
            "file_capacity_n": aggregates["capacity"][code]["n"],
            "report_capacity_mw": rep_cap.get(rep_key),
            "file_production_gwh": round(aggregates["production"][code]["total_mwh"] / 1000, 1),
            "file_production_n": aggregates["production"][code]["n"],
            "report_production_gwh": rep_gen.get(gen_key),
        })
    delta.append({
        "type": "Electricity",
        "file_capacity_mw": aggregates["electrical"]["capacity_mw"],
        "file_capacity_n": aggregates["electrical"]["capacity_n"],
        "report_capacity_mw": rep_cap.get("Electricity"),
        "file_production_gwh": round(aggregates["electrical"]["production_mwh"] / 1000, 1),
        "file_production_n": aggregates["electrical"]["production_n"],
        "report_production_gwh": rep_gen.get("Electricity"),
    })

    meta = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": {
            "name": "CEEDC Innovative Energy Facilities database — District Energy Inventory",
            "publisher": "Canadian Energy and Emissions Data Centre (CEEDC), Simon Fraser University",
            "funder": "CanmetENERGY-Ottawa, Natural Resources Canada",
            "databases_page": "https://www.sfu.ca/ceedc/databases.html",
            "dashboard": "https://cieedacdb.rem.sfu.ca:8006/district-energy-inventory/",
            "report": report["source"]["url"],
            "report_published": report["source"]["published"],
            "dashboard_last_updated": "2024-01-24",
            "files": ["CEEDC_IEF_district energy.xlsx", "CEEDC_IEF_public.xlsx"],
        },
        "counts": {
            "district_energy_facilities": len(facilities),
            "operating": aggregates["n_operating"],
            "planned": aggregates["n_planned"],
            "decommissioned": aggregates["n_decommissioned"],
            "ief_context_facilities": len(context),
            "ief_total": len(pub_rows),
        },
        "file_vs_report": {
            "note": ("CEEDC's public download does not reproduce the totals in CEEDC's "
                     "published report: respondent-confidential values were withheld from "
                     "the public file, so file totals are lower on a smaller n. Both are "
                     "correct. They are never mixed on the page."),
            "rows": delta,
        },
        "qa": {
            "hw_supply_suspect": qa["hw_supply_suspect"],
            "capacity_factor_over_100": qa["capacity_factor_over_100"],
            "planned_with_past_year": qa["planned_with_past_year"],
            "municipality_unexpected": sorted(set(qa["municipality_unexpected"])),
            "operating_with_no_fuel_recorded": aggregates["fuels"]["n_without_fuel"],
            "operating_with_no_quantitative_data": aggregates["data_density"]["n_zero"],
        },
        "known_source_quirks": [
            "Metadata sheet: the 'Detail' column is offset from the 'Field' column by 4 rows from row 60 onward, so geo_used reads as 'Solid Biomass' and waste_used as 'Spent Pulping Liquor'. Corrected in this pipeline's FUELS table.",
            "Metadata sheet lists an 'npri' field the IEF sheet does not have, and omits the 'operator' field it does have.",
            "municipality_type ships in mixed case ('large' and 'Large'); lowercased here.",
            "Facility and city names carry stray double and trailing spaces; whitespace-normalised here.",
            "No 'primary fuel' column exists in the workbook. CEEDC's dashboard derives one inside its Tableau .hyper extract, which is not published, so this pipeline keeps the full fuel set per system instead of guessing at a priority order.",
        ],
    }

    def dump(name, obj):
        path = os.path.join(OUT, name)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(obj, fh, ensure_ascii=False, separators=(",", ":"))
        print(f"  {name:24s} {os.path.getsize(path) / 1024:8.1f} KB")

    print("Writing…")
    dump("facilities.json", [strip_nulls(f) for f in facilities])
    dump("ief_context.json", context)
    dump("aggregates.json", aggregates)
    dump("canada_outline.json", outlines)
    dump("report_2023.json", report)
    dump("projects.json", projects)
    dump("meta.json", meta)

    print("\nQA")
    print(f"  operating systems                    {aggregates['n_operating']}")
    print(f"  …with no fuel recorded               {aggregates['fuels']['n_without_fuel']}")
    print(f"  …with zero quantitative fields       {aggregates['data_density']['n_zero']}")
    print(f"  …placed on the IEA ladder            {aggregates['iea_generation']['n']}")
    print(f"  …steam carrier (1G by definition)    {aggregates['iea_generation']['n_steam_carrier']}")
    for k in ("hw_supply_suspect", "capacity_factor_over_100", "planned_with_past_year"):
        if qa[k]:
            print(f"  {k}: {qa[k]}")
    print("\n  file vs report:")
    for d in delta:
        print(f"    {d['type']:22s} cap file {d['file_capacity_mw']:>8} (n={d['file_capacity_n']:>3})"
              f"  report {d['report_capacity_mw']}")


if __name__ == "__main__":
    main()
