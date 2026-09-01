"""
municipal_permits_etl.py

Permit-level open data from two city portals, aggregated into
construction_json/municipal.json for the Construction Tracker's municipal
deep-dive card.

WHY ONLY FOUR CITIES
    Every other source on this page is a national aggregate on one schema.
    Municipal permits are the opposite: one schema, refresh cadence and set of
    coverage caveats per city. Vancouver, Toronto, Calgary and Edmonton earn
    their keep — Vancouver has the cleanest schema and refreshes daily,
    Toronto is the only portal found that publishes dedicated GREEN ROOF and
    SOLAR HOT WATER permit datasets (the one municipal energy signal in the
    country), Calgary is both the richest schema of any city evaluated (a
    real status field, a clean cost field, dwelling units, full
    community-level geography) and the only one where the city boundary is
    close to its CMA (see below), and Edmonton has the longest clean history
    of any city here (back to 2009, though this ETL floors it to 2017 like
    the rest) on a dataset the city explicitly labels its "Primary" building
    permits view — deduplicated, verified for accuracy, updated daily.

    Edmonton was re-evaluated 2026-09-01 after an earlier pass (see below)
    wrongly rejected it. What's genuinely different about Edmonton, checked
    live: it has NO applicant or contractor field, and NOT because the data
    is missing — the city's own dataset description states plainly that
    applicant information was deliberately excluded as a privacy measure
    (naming a permit applicant would make a private individual's name and,
    by extension, address, searchable). So Edmonton gets no concentration
    panel, full stop, and that is the right call on the city's part, not a
    gap to work around. Edmonton's two date columns are also confusingly
    inverted: the UI displays a column labelled "PERMIT_DATE" that is
    actually the API's `issue_date` field, and one labelled
    "REPORT_PERMIT_DATE" that is actually `permit_date`. Checked live: the
    two are IDENTICAL on every single row (143,693 of 143,693 since 2017) —
    there is no separate application-to-issuance interval to measure, so
    Edmonton gets no processing-time panel either, unlike Vancouver and
    Calgary. It does have `occupancy_granted_date`, which supports a
    Calgary-style build-time panel, but with much narrower coverage: the city
    only started populating it for residential permits finalized on/after
    2022-01-01 and non-residential completed on/after 2024-01-01 — the card
    states this rather than implying full history.

    Montreal (CKAN, `datastore_search_sql` works there) was evaluated and is
    reachable, but was left out: its per-permit rows carry no cost or status
    field (cost only exists pre-aggregated by year/borough, not joinable back
    to individual permits) and two boroughs are currently missing from an
    in-progress system migration. Ottawa was assumed reachable via ArcGIS in
    an earlier pass of this evaluation — that was wrong. Ottawa's open-data
    portal publishes permits only as ~10+ separate annual .xlsx bulk-download
    workbooks with no API and no server-side aggregation at all. More schemas
    is maintenance, not insight, unless a city's data clears a real bar —
    Calgary and Edmonton did; these did not, yet.

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
    Edmonton   Socrata SODA API, dataset `General Building Permits`
               (`24uj-dj8v`, "Primary Dataset or View") (Open Government
               Licence - Edmonton). Server-side SoQL aggregation like Calgary,
               with one exception: `occupancy_granted_date` is stored as a
               TEXT column, not a proper calendar_date, so Socrata's
               `date_diff_d` 400s on it — the build-time rows are pulled raw
               (permit_date, occupancy_granted_date, building_type, scoped to
               ~22,500 rows) and diffed client-side in Python instead.
               `construction_value` is populated on ~74.8% of rows since 2017
               (checked live) — no placeholder-string corruption like
               Toronto's, just genuinely blank on permit types that don't
               require a cost estimate (e.g. hot tubs) — so it is a real,
               stated undercount rather than a data-quality defect.

DATA QUALITY
    Toronto's EST_CONST_COST column contains a literal placeholder string,
    "DO NOT UPDATE OR DELETE THIS INFO FIELD", on a large share of rows. Those
    rows are counted, reported, and excluded from cost sums — never silently
    dropped. The run prints a drop report and it is echoed into the output so
    the page can state it. The share is large enough (about half of all rows)
    that Toronto's DOLLAR series is an undercount of unknown size and must not
    be compared with the StatCan CMA permit values; its COUNT and DWELLING-UNIT
    series are sound, so those are what the page plots for Toronto.

    Edmonton's `work_type` column carries overlapping/duplicate-looking labels
    for the same underlying concept — e.g. "(01) New" (54,230 rows since 2009)
    and "(01) Building - New" (47,018 rows) both mean new construction, most
    likely from a schema change at some point rather than two real categories.
    Both are matched explicitly wherever "new construction" scoping matters
    (unit economics, build time) rather than silently picking one.

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
EDM_API = "https://data.edmonton.ca/resource/24uj-dj8v.json"

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

    # PermitElapsedDays: number-assignment to issuance, 100% populated,
    # right-skewed (median ~70-90d vs mean ~120-160d checked live), so median
    # is what is reported, not mean.
    by_type_days = agg("typeofwork,median(permitelapseddays) as med,count(*) as n",
                       "typeofwork", "med desc", 20)
    by_year_days = agg("issueyear,median(permitelapseddays) as med,count(*) as n",
                       "issueyear", "issueyear", 20)

    total = agg("count(*) as n", None, None, 1)[0]["n"]

    # Concentration: who files the most permits / builds the most of them.
    # `applicant` is 100% populated and is "often the design professional or
    # their firm" per the field's own description (checked live: the highest-
    # volume names are architecture/design firms, not homeowners — a private
    # individual does not personally file dozens of permits). `threshold=20`
    # keeps the published list to genuine repeat filers rather than one-off
    # individual applicants, even though nothing here is legally restricted.
    # `buildingcontractor` is populated on only ~62% of rows (contractor often
    # not yet chosen at issuance), so its concentration stats are scoped to
    # permits that name one, with that coverage rate stated on the card.
    def concentration(field, threshold=20):
        rows = agg(f"{field},count(*) as n,sum(projectvalue) as val",
                   field, "n desc", 12000)
        rows = [r for r in rows if r.get(field)]
        has_field = sum(r["n"] for r in rows)
        qualifying = [r for r in rows if r["n"] >= threshold]
        covered = sum(r["n"] for r in qualifying)
        return {
            "threshold": threshold,
            "field_coverage_pct": round(has_field / total * 100, 1),
            "total_distinct": len(rows),
            "qualifying": len(qualifying),
            "permits_covered": covered,
            "pct_of_field_permits": round(covered / has_field * 100, 1) if has_field else 0,
            "top": [[r[field], r["n"], round((r["val"] or 0) / 1e6, 1)]
                    for r in qualifying[:15]],
        }

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
        "processing": {
            "unit_note": ("Measured from permit-number assignment to "
                          "issuance (PermitElapsedDays), not from "
                          "application submission. Median, not mean, since "
                          "the distribution is right-skewed by large "
                          "projects — the mean runs 40-70 days higher."),
            "by_type": [[r["typeofwork"], r["n"], round(r["med"], 1)]
                        for r in by_type_days if r.get("typeofwork")],
            "by_year": [[r["issueyear"], r["n"], round(r["med"], 1)]
                        for r in by_year_days if r.get("issueyear")],
        },
        "concentration": {
            "applicants": concentration("applicant"),
            "contractors": concentration("buildingcontractor"),
        },
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
    # Calgary's dataset runs back to 1999 (checked live), unlike Vancouver's
    # (which genuinely starts 2017-01-03, so needs no filter) — every query
    # below is explicitly floored to FLOOR so it actually matches the "since
    # 2017" wording already on the page, mirroring Toronto's `d >= FLOOR`
    # filter rather than silently including 18 extra years under that label.
    since_floor = f"issueddate >= '{FLOOR}-01'"
    areas = agg("communityname,count(*) as n,sum(estprojectcost) as val",
                "communityname", where=since_floor, limit=500)
    # `workclass` (New/Alteration/Addition/Repair/...) is far finer-grained
    # than `workclassgroup` or `workclassmapped`, which only split New vs
    # Existing — checked live against the API before picking this field.
    work = agg("workclass,count(*) as n,sum(estprojectcost) as val",
               "workclass", where=since_floor, limit=50)
    use = agg("permitclassmapped,count(*) as n,sum(estprojectcost) as val",
              "permitclassmapped", where=since_floor, limit=50)

    def tidy(rows, k):
        out = [[r[k], int(r["n"]), round(float(r.get("val") or 0) / 1e6, 1)]
               for r in rows if r.get(k)]
        out.sort(key=lambda row: -row[2])
        return out

    def stage_days(diff_expr, date_floor, group_field):
        # `date_diff_d` can go negative on a small number of rows (checked
        # live: 1 of ~480k applied->issued, 31 of ~465k issued->completed) —
        # data-entry artifacts, not real time travel. Excluded, not zeroed.
        where = (f"{date_floor[0]} is not null and {date_floor[1]} is not null "
                f"and {diff_expr} >= 0 and {since_floor}")
        by_type = agg(f"{group_field},median({diff_expr}) as med,count(*) as n",
                     group_field, where=where, limit=50)
        by_year = agg(f"date_trunc_y({date_floor[1]}) as yr,"
                     f"median({diff_expr}) as med,count(*) as n",
                     "yr", "yr", where=where, limit=30)
        return {
            "by_type": [[r[group_field], int(r["n"]), round(float(r["med"]), 1)]
                        for r in by_type if r.get(group_field)],
            "by_year": [[r["yr"][:4], int(r["n"]), round(float(r["med"]), 1)]
                        for r in by_year if r.get("yr")],
        }

    apply_to_issue = stage_days("date_diff_d(issueddate,applieddate)",
                                ("applieddate", "issueddate"), "workclass")
    issue_to_complete = stage_days("date_diff_d(completeddate,issueddate)",
                                   ("issueddate", "completeddate"), "workclass")

    # `applicantname`/`contractorname` mirror Vancouver's applicant/contractor
    # concentration panel: same 20+ threshold and same reasoning (a private
    # homeowner does not personally file dozens of permits), but Calgary's
    # coverage is lower — ~70%/~60% populated versus Vancouver's ~100%/~62% —
    # so both get a stated coverage rate here, not just the contractor one.
    def concentration(field, threshold=20):
        rows = agg(f"{field},count(*) as n,sum(estprojectcost) as val",
                  field, where=since_floor, limit=25000)
        rows = [r for r in rows if r.get(field)]
        has_field = sum(int(r["n"]) for r in rows)
        qualifying = sorted([r for r in rows if int(r["n"]) >= threshold],
                            key=lambda r: -int(r["n"]))
        covered = sum(int(r["n"]) for r in qualifying)
        return {
            "threshold": threshold,
            "field_coverage_pct": round(has_field / total_permits * 100, 1),
            "total_distinct": len(rows),
            "qualifying": len(qualifying),
            "permits_covered": covered,
            "pct_of_field_permits": round(covered / has_field * 100, 1) if has_field else 0,
            "top": [[r[field], int(r["n"]), round(float(r.get("val") or 0) / 1e6, 1)]
                    for r in qualifying[:15]],
        }

    total_permits = int(agg("count(*) as n", where=since_floor, limit=1)[0]["n"])

    # $/unit, $/sqft and average unit size, scoped to residential new-build
    # permits with dwelling units (the only population where these ratios
    # mean anything). `totalsqft` is recorded on 0% of non-residential rows
    # and only ~38% of all residential rows — but checked live within this
    # exact scope (residential + new + units>0) it is ~91% populated, so it
    # is usable here even though it is not usable dataset-wide. Two separate
    # sums, not one query with a CASE: cost/unit uses every qualifying row
    # (housingunits is 100% populated); cost/sqft and avg unit size use only
    # the subset that also has totalsqft, so a row missing sqft never
    # silently drags down the per-sqft or unit-size figures.
    econ_where = (f"housingunits > 0 and workclass = 'New' and "
                 f"permitclassmapped = 'Residential' and issueddate >= '{FLOOR}-01'")
    econ_all = agg("date_trunc_y(issueddate) as yr,sum(estprojectcost) as cost,"
                  "sum(housingunits) as units,count(*) as n",
                  "yr", "yr", where=econ_where, limit=30)
    econ_sqft = agg("date_trunc_y(issueddate) as yr,sum(estprojectcost) as cost,"
                    "sum(housingunits) as units,sum(totalsqft) as sqft,count(*) as n",
                    "yr", "yr",
                    where=econ_where + " and totalsqft is not null and totalsqft >= 0",
                    limit=30)
    sqft_by_yr = {r["yr"][:4]: r for r in econ_sqft if r.get("yr")}
    unit_economics = {
        "scope_note": ("Residential new-construction permits with dwelling "
                      f"units, {FLOOR} forward. totalsqft is recorded on "
                      "~91% of this exact population even though it is "
                      "recorded on almost none of the dataset overall (0% "
                      "of non-residential permits), so $/sqft and average "
                      "unit size use only the rows that have it — a "
                      "separate, slightly smaller row count than $/unit, "
                      "which uses every row since housingunits is always "
                      "populated."),
        "by_year": [],
    }
    for r in econ_all:
        yr = r.get("yr", "")[:4]
        if not yr:
            continue
        cost, units, n = float(r.get("cost") or 0), float(r.get("units") or 0), int(r["n"])
        row = [yr, n, round(cost / units) if units else None, None, None, None]
        sq = sqft_by_yr.get(yr)
        if sq:
            sqft, sq_cost, sq_units = (float(sq.get("sqft") or 0), float(sq.get("cost") or 0),
                                       float(sq.get("units") or 0))
            if sqft:
                row[3] = round(sq_cost / sqft, 1)
                row[4] = round(sqft / sq_units) if sq_units else None
            row[5] = int(sq["n"])
        unit_economics["by_year"].append(row)

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
        "processing": {
            "unit_note": ("Days from application to issuance (applieddate to "
                          "issueddate). Median, not mean, since the "
                          "distribution is right-skewed by large projects."),
            "by_type": apply_to_issue["by_type"],
            "by_year": apply_to_issue["by_year"],
        },
        "build_time": {
            "group_label": "work category",
            "unit_note": ("Days from issuance to the permit's completed date "
                          "(issueddate to completeddate). This is when the "
                          "permit record is administratively closed — it "
                          "should track physical construction completion "
                          "closely, but may lag it for final-inspection or "
                          "paperwork reasons on some permits. Median, not "
                          "mean, for the same right-skew reason as above."),
            "by_type": issue_to_complete["by_type"],
            "by_year": issue_to_complete["by_year"],
        },
        "concentration": {
            "applicants": concentration("applicantname"),
            "contractors": concentration("contractorname"),
        },
        "unit_economics": unit_economics,
    }


# =============================================================================
# Edmonton — Socrata SoQL, like Calgary, but no applicant/contractor field
# (deliberately excluded by the city for privacy) and no processing-time
# panel (its two date columns are identical on every row — see module
# docstring). occupancy_granted_date is TEXT, not calendar_date, so its
# build-time rows are diffed client-side rather than via date_diff_d.
# =============================================================================

def fetch_edmonton():
    def agg(select, group_by=None, order_by=None, where=None, limit=200):
        params = {"$select": select, "$limit": limit}
        if group_by:
            params["$group"] = group_by
        if order_by:
            params["$order"] = order_by
        if where:
            params["$where"] = where
        return get(EDM_API, params)

    since_floor = f"permit_date >= '{FLOOR}-01'"

    monthly = agg("date_trunc_ym(permit_date) as ym,count(*) as n,"
                 "sum(construction_value) as val",
                 "ym", "ym", where=since_floor, limit=200)
    by_month_n = {r["ym"][:7]: int(r["n"]) for r in monthly if r.get("ym")}
    by_month_v = {r["ym"][:7]: round(float(r.get("val") or 0) / 1e6, 2)
                 for r in monthly if r.get("ym")}

    # Same null-sorts-first-in-descending trap as Calgary (see its comment
    # above) — client-side sort, limit set above the true distinct-value
    # count rather than trusting an unordered truncation.
    areas = agg("neighbourhood,count(*) as n,sum(construction_value) as val",
               "neighbourhood", where=since_floor, limit=500)
    work = agg("work_type,count(*) as n,sum(construction_value) as val",
              "work_type", where=since_floor, limit=50)
    use = agg("building_type,count(*) as n,sum(construction_value) as val",
             "building_type", where=since_floor, limit=500)

    def tidy(rows, k):
        out = [[r[k], int(r["n"]), round(float(r.get("val") or 0) / 1e6, 1)]
               for r in rows if r.get(k)]
        out.sort(key=lambda row: -row[2])
        return out

    total_permits = int(agg("count(*) as n", where=since_floor, limit=1)[0]["n"])
    has_cost = int(agg("count(*) as n",
                       where=since_floor + " and construction_value is not null "
                                          "and construction_value > 0",
                       limit=1)[0]["n"])

    # Unit economics: residential new-construction permits with units added,
    # mirroring Calgary's scope exactly. "(01) New" and "(01) Building - New"
    # both mean new construction (see DATA QUALITY in the module docstring).
    NEW_WORK_TYPES = "'(01) Building - New','(01) New'"
    econ_where = (f"units_added > 0 and work_type in({NEW_WORK_TYPES}) and {since_floor}")
    econ_all = agg("date_trunc_y(permit_date) as yr,sum(construction_value) as cost,"
                  "sum(units_added) as units,count(*) as n",
                  "yr", "yr", where=econ_where, limit=30)
    econ_sqft = agg("date_trunc_y(permit_date) as yr,sum(construction_value) as cost,"
                    "sum(units_added) as units,sum(floor_area) as sqft,count(*) as n",
                    "yr", "yr",
                    where=econ_where + " and floor_area is not null and floor_area >= 0",
                    limit=30)
    sqft_by_yr = {r["yr"][:4]: r for r in econ_sqft if r.get("yr")}
    unit_economics = {
        "scope_note": ("Residential new-construction permits with dwelling "
                      f"units added, {FLOOR} forward (work_type '(01) New' "
                      "or '(01) Building - New'). floor_area is recorded on "
                      "~99% of this exact population, so $/sqft and average "
                      "unit size use almost the same row count as $/unit."),
        "by_year": [],
    }
    for r in econ_all:
        yr = r.get("yr", "")[:4]
        if not yr:
            continue
        cost, units, n = float(r.get("cost") or 0), float(r.get("units") or 0), int(r["n"])
        row = [yr, n, round(cost / units) if units else None, None, None, None]
        sq = sqft_by_yr.get(yr)
        if sq:
            sqft, sq_cost, sq_units = (float(sq.get("sqft") or 0), float(sq.get("cost") or 0),
                                       float(sq.get("units") or 0))
            if sqft:
                row[3] = round(sq_cost / sqft, 1)
                row[4] = round(sqft / sq_units) if sq_units else None
            row[5] = int(sq["n"])
        unit_economics["by_year"].append(row)

    # Build time: occupancy_granted_date to permit_date, same residential-new
    # scope. Pulled raw (not server-side date_diff_d — see module docstring)
    # and diffed in Python; negative diffs (data-entry artifacts, checked
    # live: 62 of 22,543, 0.3%) excluded, not zeroed, same as Calgary's.
    from collections import defaultdict as _dd
    from datetime import date as _date
    bt_rows = agg("permit_date,occupancy_granted_date,building_type",
                 where=econ_where + " and occupancy_granted_date is not null",
                 limit=30000)

    def _median(vals):
        vals = sorted(vals)
        n = len(vals)
        if n == 0:
            return None
        return vals[n // 2] if n % 2 else (vals[n // 2 - 1] + vals[n // 2]) / 2

    by_type_diffs, by_year_diffs, neg = _dd(list), _dd(list), 0
    for r in bt_rows:
        try:
            pd_ = _date.fromisoformat(r["permit_date"][:10])
            od = _date.fromisoformat(r["occupancy_granted_date"][:10])
        except (ValueError, KeyError, TypeError):
            continue
        d = (od - pd_).days
        if d < 0:
            neg += 1
            continue
        by_type_diffs[r.get("building_type") or "(unspecified)"].append(d)
        by_year_diffs[str(pd_.year)].append(d)

    build_time = {
        "group_label": "building type",
        "unit_note": ("Days from permit issuance to occupancy "
                     "(occupancy_granted_date). Median, not mean. "
                     f"{neg} rows with a negative day-count (occupancy date "
                     "before permit date — a data-entry artifact) excluded, "
                     "not zeroed."),
        "coverage_note": ("Edmonton only began systematically recording "
                         "occupancy dates for residential permits finalized "
                         "on/after 2022-01-01 (non-residential: 2024-01-01 "
                         "and only where an occupancy record exists), per "
                         "the dataset's own documentation — so this panel "
                         "covers a recent subset, not the full 2017+ "
                         f"history the rest of this card uses ({len(bt_rows)} "
                         f"of {sum(int(r['n']) for r in econ_all)} "
                         "residential-new permits since 2017 have an "
                         "occupancy date)."),
        "by_type": [[k, len(v), round(_median(v), 1)]
                   for k, v in sorted(by_type_diffs.items(), key=lambda kv: -len(kv[1]))[:12]],
        "by_year": [[y, len(v), round(_median(v), 1)]
                   for y, v in sorted(by_year_diffs.items())],
    }

    return {
        "label": "City of Edmonton",
        "cma": "edmonton",
        "coverage": ("City of Edmonton only. Compare cautiously against the "
                    "Edmonton CMA figures elsewhere on this page — the city "
                    "boundary is not the CMA boundary."),
        "licence": "Open Government Licence - Edmonton",
        "count": months_to_series(by_month_n),
        "value": months_to_series(by_month_v),
        "areas": tidy(areas, "neighbourhood")[:TOP_AREAS],
        "work": tidy(work, "work_type"),
        "use": tidy(use, "building_type")[:8],
        "quality": {
            "rows": total_permits,
            "has_cost": has_cost,
            "cost_coverage_pct": round(has_cost / total_permits * 100, 1),
            "unparseable_cost_pct": round(100 - has_cost / total_permits * 100, 1),
            "note": ("construction_value is populated on only "
                    f"{round(has_cost/total_permits*100,1)}% of permits since "
                    f"{FLOOR} — genuinely blank on permit types that don't "
                    "require a cost estimate (e.g. hot tubs, some alterations), "
                    "not placeholder-corrupted like Toronto's. Dollar totals "
                    "are therefore a real undercount; counts are sound."),
        },
        "unit_economics": unit_economics,
        "build_time": build_time,
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
        print("fetching Edmonton (Socrata SoQL, server-side aggregation)...")
        cities["edmonton"] = fetch_edmonton()
        print(f"  edmonton: {len(cities['edmonton']['areas'])} neighbourhoods, "
              f"{len(cities['edmonton']['work'])} work types")
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
            "edmonton": "City of Edmonton open data, General Building Permits "
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
