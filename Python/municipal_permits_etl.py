"""
municipal_permits_etl.py

Permit-level open data from two city portals, aggregated into
construction_json/municipal.json for the Construction Tracker's municipal
deep-dive card.

WHY ONLY THREE CITIES
    Every other source on this page is a national aggregate on one schema.
    Municipal permits are the opposite: one schema, refresh cadence and set of
    coverage caveats per city. Vancouver, Toronto and Calgary earn their
    keep — Vancouver has the cleanest schema and refreshes daily, Toronto is
    the only portal found that publishes dedicated GREEN ROOF and SOLAR HOT
    WATER permit datasets (the one municipal energy signal in the country),
    and Calgary is both the richest schema of any city evaluated (a real
    status field, a clean cost field, dwelling units, full community-level
    geography) and the only one where the city boundary is close to its CMA
    (see below), so its series is the most directly comparable to the
    StatCan figures already on the page.

    Montreal (CKAN, `datastore_search_sql` works there) and Edmonton (Socrata)
    were evaluated and are reachable, but were left out: Montreal's per-permit
    rows carry no cost or status field (cost only exists pre-aggregated by
    year/borough, not joinable back to individual permits) and two boroughs
    are currently missing from an in-progress system migration; Edmonton has
    several overlapping/redundant permit datasets that would need reconciling
    first and no status or postal/ward field. Ottawa was assumed reachable via
    ArcGIS in an earlier pass of this evaluation — that was wrong. Ottawa's
    open-data portal publishes permits only as ~10+ separate annual .xlsx
    bulk-download workbooks with no API and no server-side aggregation at all.
    More schemas is maintenance, not insight, unless a city's data clears a
    real bar — Calgary did; these did not, yet.

THE COVERAGE CAVEAT THAT MATTERS
    A city is not its census metropolitan area. The City of Vancouver is a
    fraction of the Vancouver CMA, and the City of Toronto excludes Peel, York,
    Durham and Halton. These series therefore CANNOT be reconciled with the
    StatCan CMA permit values already on the page, and the card says so and
    plots the ratio rather than pretending they measure the same thing.
    Calgary is the exception that proves the rule useful: per the 2021 Census,
    the City of Calgary (1,306,784) is about 88% of the Calgary CMA
    (1,481,806, which also covers Airdrie, Cochrane, Chestermere and Rocky
    View County), so its series tracks the CMA figures far more closely than
    Vancouver's or Toronto's city series do — but it is still not identical,
    and the card states the live ratio rather than assuming it.

SOURCES
    Vancouver  Opendatasoft Explore API v2.1, dataset `issued-building-permits`
               (Open Government Licence - Vancouver). Server-side aggregation,
               so this costs a handful of small requests.
    Toronto    CKAN datastore: BOTH the "Cleared Building Permits since 2017"
               and "Active Permits" resources (Open Government Licence -
               Toronto), plus the green-roof and solar-hot-water permit sets.
               Cleared means CLOSED, so on its own it is badly right-censored
               at the recent end; active + cleared = every permit issued.
               `datastore_search_sql` is NOT enabled on this portal (404), and
               the bulk CSV is 146 MB, so this pages `datastore_search` with an
               explicit field list: ~20 requests, ~6 MB each.
    Calgary    Socrata SODA API, dataset `Building Permits` (Open Calgary Terms
               of Use — redistribution permitted, attribution not required).
               Server-side SoQL aggregation (`$select`/`$group`/`$order`), same
               cost profile as Vancouver. `estprojectcost` is populated on
               ~92-95% of rows since 2016 (no Toronto-style placeholder-string
               corruption found), so it is treated as a normal, usable cost
               field rather than flagged as an undercount.

DATA QUALITY
    Toronto's EST_CONST_COST column contains a literal placeholder string,
    "DO NOT UPDATE OR DELETE THIS INFO FIELD", on a large share of rows. Those
    rows are counted, reported, and excluded from cost sums — never silently
    dropped. The run prints a drop report and it is echoed into the output so
    the page can state it. The share is large enough (about half of all rows)
    that Toronto's DOLLAR series is an undercount of unknown size and must not
    be compared with the StatCan CMA permit values; its COUNT and DWELLING-UNIT
    series are sound, so those are what the page plots for Toronto.

USAGE
    python municipal_permits_etl.py [--refresh]
Exits non-zero on any fetch failure (safe for the scheduled refresh).
"""

import sys
import json
import argparse
from pathlib import Path
from datetime import datetime
from collections import defaultdict

import requests

REPO_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = REPO_ROOT / "construction_json"

VAN_API = ("https://opendata.vancouver.ca/api/explore/v2.1/catalog/datasets/"
           "issued-building-permits/records")
TOR_DS = ("https://ckan0.cf.opendata.inter.prod-toronto.ca/api/3/action/"
          "datastore_search")
# BOTH permit sets are needed. "Cleared" means CLOSED, so on its own it is
# badly right-censored at the recent end — a permit issued last month has not
# been closed yet, which made the last few months of the series collapse
# (74 permits in the final month, against ~375 two months earlier). Active +
# cleared together = every permit issued.
TOR_PERMITS_CLEARED = "a96c0ba4-3026-402b-b09d-5b1268b8f810"
TOR_PERMITS_ACTIVE = "6d0229af-bc54-46de-9c2b-26759b01dd05"
TOR_GREEN_ROOF = "936ea65d-2ed3-4243-8cf5-10d1c28194c6"
TOR_SOLAR_HW = "220001bd-0279-477f-bb22-1379077aac6f"
CAL_API = "https://data.calgary.ca/resource/c2es-76ed.json"

HEADERS = {"User-Agent": "OttawaVisuals-EnergySuite/1.0 (construction tracker)"}
FLOOR = "2017-01"          # both portals' usable history starts here
TOP_AREAS = 12


def get(url, params=None, timeout=180):
    r = requests.get(url, params=params, headers=HEADERS, timeout=timeout)
    r.raise_for_status()
    return r.json()


def months_to_series(by_month, key=None):
    """{'YYYY-MM': v} -> {start, freq:'m', values[]} with null gaps, matching
    the contract every other file on this page uses."""
    ms = sorted(m for m in by_month if m >= FLOOR)
    if not ms:
        return None
    y0, m0 = int(ms[0][:4]), int(ms[0][5:7])
    y1, m1 = int(ms[-1][:4]), int(ms[-1][5:7])
    out, y, m = [], y0, m0
    while (y, m) <= (y1, m1):
        out.append(by_month.get(f"{y:04d}-{m:02d}"))
        m += 1
        if m > 12:
            m, y = 1, y + 1
    return {"start": ms[0], "freq": "m", "values": out}


# =============================================================================
# Vancouver — server-side aggregation, so this is cheap
# =============================================================================

def fetch_vancouver():
    def agg(select, group_by, order_by, limit=200):
        d = get(VAN_API, {"select": select, "group_by": group_by,
                          "order_by": order_by, "limit": limit})
        return d.get("results", [])

    monthly = agg("yearmonth,count(*) as n,sum(projectvalue) as val",
                  "yearmonth", "yearmonth", 400)
    by_month_n = {r["yearmonth"]: r["n"] for r in monthly if r.get("yearmonth")}
    by_month_v = {r["yearmonth"]: round((r["val"] or 0) / 1e6, 2)
                  for r in monthly if r.get("yearmonth")}

    areas = agg("geolocalarea,count(*) as n,sum(projectvalue) as val",
                "geolocalarea", "val desc", 40)
    work = agg("typeofwork,count(*) as n,sum(projectvalue) as val",
               "typeofwork", "val desc", 20)
    use = agg("propertyuse,count(*) as n,sum(projectvalue) as val",
              "propertyuse", "val desc", 20)

    tidy = lambda rows, k: [[r[k], r["n"], round((r["val"] or 0) / 1e6, 1)]
                            for r in rows if r.get(k)]
    return {
        "label": "City of Vancouver",
        "cma": "vancouver",
        "coverage": ("City of Vancouver only. The Vancouver CMA contains 20+ "
                     "other municipalities, so this is a fraction of the CMA "
                     "figures elsewhere on this page."),
        "licence": "Open Government Licence - Vancouver",
        "count": months_to_series(by_month_n),
        "value": months_to_series(by_month_v),
        "areas": tidy(areas, "geolocalarea")[:TOP_AREAS],
        "work": tidy(work, "typeofwork"),
        "use": tidy(use, "propertyuse")[:8],
        "quality": None,
    }


# =============================================================================
# Toronto — paged datastore, plus the two energy-measure permit sets
# =============================================================================

def page_datastore(resource_id, fields, page=32000):
    """Yield records, paging datastore_search with an explicit field list."""
    offset, total = 0, None
    while True:
        d = get(TOR_DS, {"resource_id": resource_id, "limit": page,
                         "offset": offset, "fields": ",".join(fields)})
        res = d["result"]
        total = res["total"] if total is None else total
        recs = res["records"]
        if not recs:
            break
        for r in recs:
            yield r
        offset += len(recs)
        print(f"    ...{offset:,}/{total:,}", flush=True)
        if offset >= total:
            break


def num(v):
    """Parse a numeric cell, returning None for blanks AND for Toronto's
    literal placeholder strings. Callers count what this rejects."""
    if v is None:
        return None
    s = str(v).strip().replace(",", "").replace("$", "")
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def fetch_toronto():
    fields = ["ISSUED_DATE", "WORK", "PERMIT_TYPE", "EST_CONST_COST",
              "DWELLING_UNITS_CREATED", "DWELLING_UNITS_LOST", "POSTAL"]
    n_month = defaultdict(int)
    v_month = defaultdict(float)
    created = defaultdict(float)
    lost = defaultdict(float)
    by_fsa = defaultdict(lambda: [0, 0.0])
    by_work = defaultdict(lambda: [0, 0.0])
    rows = bad_date = bad_cost = 0
    junk_cost = defaultdict(int)

    def consume(r):
        nonlocal bad_date, bad_cost
        d = (r.get("ISSUED_DATE") or "")[:7]
        if len(d) != 7 or d[4] != "-":
            bad_date += 1
            return
        cost = num(r.get("EST_CONST_COST"))
        if cost is None and r.get("EST_CONST_COST"):
            bad_cost += 1
            junk_cost[str(r["EST_CONST_COST"])[:60]] += 1
        n_month[d] += 1
        if cost:
            v_month[d] += cost / 1e6
        for key, acc in (("DWELLING_UNITS_CREATED", created),
                         ("DWELLING_UNITS_LOST", lost)):
            u = num(r.get(key))
            if u:
                acc[d] += u
        if d >= FLOOR:
            fsa = (r.get("POSTAL") or "").strip().upper()[:3]
            if len(fsa) == 3:
                by_fsa[fsa][0] += 1
                by_fsa[fsa][1] += (cost or 0) / 1e6
            w = (r.get("WORK") or "").strip() or "Unspecified"
            by_work[w][0] += 1
            by_work[w][1] += (cost or 0) / 1e6

    for label, rid in (("cleared", TOR_PERMITS_CLEARED),
                       ("active", TOR_PERMITS_ACTIVE)):
        print(f"  toronto: paging {label} permits...")
        for r in page_datastore(rid, fields):
            rows += 1
            consume(r)

    def by_year(resource_id, extra=None):
        out = defaultdict(int)
        area = defaultdict(float)
        for r in page_datastore(resource_id,
                                ["ISSUED_DATE"] + ([extra] if extra else [])):
            y = (r.get("ISSUED_DATE") or "")[:4]
            if len(y) == 4 and y.isdigit():
                out[y] += 1
                if extra:
                    a = num(r.get(extra))
                    if a:
                        area[y] += a
        return dict(sorted(out.items())), dict(sorted(area.items()))

    print("  toronto: green roof permits...")
    gr_n, gr_area = by_year(TOR_GREEN_ROOF, "GREEN_ROOF_AREA")
    print("  toronto: solar hot water permits...")
    sh_n, _ = by_year(TOR_SOLAR_HW)

    top_fsa = sorted(by_fsa.items(), key=lambda kv: -kv[1][1])[:TOP_AREAS]
    top_work = sorted(by_work.items(), key=lambda kv: -kv[1][1])[:10]
    pct = (bad_cost / rows * 100) if rows else 0
    print(f"  toronto: {rows:,} rows | {bad_date:,} unusable dates | "
          f"{bad_cost:,} unparseable cost cells ({pct:.1f}%)")
    for k, v in sorted(junk_cost.items(), key=lambda kv: -kv[1])[:3]:
        print(f"      placeholder: {k!r} x{v:,}")

    return {
        "label": "City of Toronto",
        "cma": "toronto",
        "coverage": ("City of Toronto only. The Toronto CMA also covers Peel, "
                     "York, Durham and Halton, so this is well under half the "
                     "CMA figures elsewhere on this page."),
        "licence": "Open Government Licence - Toronto",
        "count": months_to_series(n_month),
        "value": months_to_series({k: round(v, 2) for k, v in v_month.items()}),
        "units_created": months_to_series({k: int(v) for k, v in created.items()}),
        "units_lost": months_to_series({k: int(v) for k, v in lost.items()}),
        "areas": [[k, v[0], round(v[1], 1)] for k, v in top_fsa],
        "areas_label": "forward sortation area",
        "work": [[k, v[0], round(v[1], 1)] for k, v in top_work],
        "use": [],
        "energy": {
            "green_roof_permits": gr_n,
            "green_roof_area_m2": {k: round(v) for k, v in gr_area.items()},
            "solar_hot_water_permits": sh_n,
        },
        "quality": {
            "rows": rows,
            "unusable_dates": bad_date,
            "unparseable_cost_cells": bad_cost,
            "unparseable_cost_pct": round(pct, 1),
            "note": ("Toronto's EST_CONST_COST column carries literal "
                     "placeholder text on some rows (e.g. 'DO NOT UPDATE OR "
                     "DELETE THIS INFO FIELD'). Those rows still count as "
                     "permits but contribute nothing to the value sums, so "
                     "Toronto's dollar totals are an UNDERCOUNT by an unknown "
                     "amount. Counts are sound; values are not."),
        },
    }


# =============================================================================
# Calgary — Socrata SoQL, server-side aggregation like Vancouver
# =============================================================================

def fetch_calgary():
    def agg(select, group_by=None, order_by=None, where=None, limit=200):
        params = {"$select": select, "$limit": limit}
        if group_by:
            params["$group"] = group_by
        if order_by:
            params["$order"] = order_by
        if where:
            params["$where"] = where
        return get(CAL_API, params)

    monthly = agg("date_trunc_ym(issueddate) as ym,count(*) as n,"
                  "sum(estprojectcost) as val,sum(housingunits) as units",
                  "ym", "ym", limit=400)
    by_month_n = {r["ym"][:7]: int(r["n"]) for r in monthly if r.get("ym")}
    by_month_v = {r["ym"][:7]: round(float(r.get("val") or 0) / 1e6, 2)
                  for r in monthly if r.get("ym")}
    by_month_u = {r["ym"][:7]: int(float(r.get("units") or 0))
                  for r in monthly if r.get("ym")}

    # No `$order=val DESC` here: Socrata sorts NULL as the largest value in
    # descending order, so null-cost groups (e.g. Demolition, which records
    # almost no cost data) would otherwise float to the top. Sorting
    # client-side instead means `$limit` must be >= the true distinct-value
    # count (checked live: 317 communities, 10 workclasses, 3 use classes),
    # or an unordered result can silently truncate before a high-value group
    # is ever returned — confirmed live: an unordered limit=40 pull dropped
    # Downtown Commercial Core (Calgary's single largest community by value).
    areas = agg("communityname,count(*) as n,sum(estprojectcost) as val",
                "communityname", limit=500)
    # `workclass` (New/Alteration/Addition/Repair/...) is far finer-grained
    # than `workclassgroup` or `workclassmapped`, which only split New vs
    # Existing — checked live against the API before picking this field.
    work = agg("workclass,count(*) as n,sum(estprojectcost) as val",
               "workclass", limit=50)
    use = agg("permitclassmapped,count(*) as n,sum(estprojectcost) as val",
              "permitclassmapped", limit=50)

    def tidy(rows, k):
        out = [[r[k], int(r["n"]), round(float(r.get("val") or 0) / 1e6, 1)]
               for r in rows if r.get(k)]
        out.sort(key=lambda row: -row[2])
        return out
    return {
        "label": "City of Calgary",
        "cma": "calgary",
        "coverage": ("City of Calgary only, but the City is about 88% of the "
                     "Calgary CMA's population (2021 Census: 1,306,784 of "
                     "1,481,806) — the CMA also covers Airdrie, Cochrane, "
                     "Chestermere and Rocky View County. This tracks the CMA "
                     "figures far more closely than Vancouver's or Toronto's "
                     "city series do, but it is still not the same boundary."),
        "licence": "Open Calgary Terms of Use",
        "count": months_to_series(by_month_n),
        "value": months_to_series(by_month_v),
        "units_created": months_to_series(by_month_u),
        "areas": tidy(areas, "communityname")[:TOP_AREAS],
        "areas_label": "community",
        "work": tidy(work, "workclass"),
        "use": tidy(use, "permitclassmapped")[:8],
        "quality": None,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true",
                    help="accepted for symmetry with the other ETLs; these "
                         "portals are queried live and never cached")
    ap.parse_args()

    cities = {}
    try:
        print("fetching Vancouver (Opendatasoft, server-side aggregation)...")
        cities["vancouver"] = fetch_vancouver()
        print(f"  vancouver: {len(cities['vancouver']['areas'])} local areas, "
              f"{len(cities['vancouver']['work'])} work types")
        print("fetching Toronto (CKAN datastore, paged)...")
        cities["toronto"] = fetch_toronto()
        print("fetching Calgary (Socrata SoQL, server-side aggregation)...")
        cities["calgary"] = fetch_calgary()
        print(f"  calgary: {len(cities['calgary']['areas'])} communities, "
              f"{len(cities['calgary']['work'])} work classes")
    except Exception as e:
        print(f"\n!! municipal fetch failed: {e}", file=sys.stderr)
        sys.exit(1)

    payload = {
        "retrieved": datetime.now().strftime("%Y-%m-%d"),
        "sources": {
            "vancouver": "City of Vancouver open data, issued-building-permits "
                         "(Opendatasoft Explore API v2.1)",
            "toronto": "City of Toronto open data, Cleared Building Permits "
                       "since 2017, plus green-roof and solar-hot-water permit "
                       "datasets (CKAN datastore)",
            "calgary": "City of Calgary open data, Building Permits "
                       "(Socrata SODA API)",
        },
        "caveat": ("City boundaries, not census metropolitan areas. These "
                   "series are a SUBSET of the CMA figures elsewhere on this "
                   "page and cannot be reconciled with them."),
        "cities": cities,
    }
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUTPUT_DIR / "municipal.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))
    print(f"\nwrote {out.name} ({out.stat().st_size/1024:.1f} KB, "
          f"{len(cities)} cities)")


if __name__ == "__main__":
    main()
