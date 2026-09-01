"""
municipal_permits_etl.py

Permit-level open data from eight city portals/APIs plus one no-API
workbook pipeline, aggregated into construction_json/municipal.json for the
Construction Tracker's municipal deep-dive card. These nine cities cover
all eight of the CMAs used elsewhere on this page except Montreal was
initially passed over and later added anyway, so in practice every major
CMA this page tracks now has a matching city-level permit desk.

WHY THESE NINE CITIES
    Every other source on this page is a national aggregate on one schema.
    Municipal permits are the opposite: one schema, refresh cadence and set of
    coverage caveats per city. Vancouver has the cleanest schema and
    refreshes daily; Toronto is the only portal found that publishes
    dedicated GREEN ROOF and SOLAR HOT WATER permit datasets (the one
    municipal energy signal in the country); Calgary is both the richest
    schema of any Socrata city evaluated (a real status field, a clean cost
    field, dwelling units, full community-level geography) and the only one
    where the city boundary is close to its CMA (see below); Edmonton has the
    longest clean history of any city here (back to 2009, though this ETL
    floors it to 2017 like the rest) on a dataset the city explicitly labels
    its "Primary" building permits view; Mississauga has a real STATUS field
    and three genuinely distinct dates (application/issue/complete), and is
    the only city where "Inside one city" shows more than one city at once —
    it sits inside the Toronto CMA alongside the City of Toronto's own permit
    desk, so both render together when Toronto is the selected geo; Ottawa is
    the only city here reachable through no API at all, just 15 annual XLSX
    workbooks, and still clears the bar because the underlying data is rich
    (real contractor names among them); Montreal has the largest single
    dataset by row count (558,874 rows since 1997) and, alongside Vancouver
    and Calgary, a genuine processing-time signal, despite having no cost
    field whatsoever — one of two cities on this page ranked by permit count
    rather than dollar value; Halifax has the cleanest cost field of any
    city here (Estimated_Project_Value populated on 99.3% of rows, no fee-
    schedule artifact like Ottawa's, no scope-mixing problem like
    Mississauga's) plus a genuine three-date chain like Mississauga's,
    giving it both a processing-time AND a build-time panel on top of a
    real unit-economics table, and it is the only city whose own boundary
    is close enough to its full CMA that the two are nearly the same city;
    and Winnipeg is the second no-cost-field city (its own dataset
    description says so plainly) but has the cleanest APPLICANT data of any
    city here — real, unredacted business names with none of Ottawa's
    placeholder-redaction pattern — plus a genuine three-date chain giving
    it both a processing-time and a build-time panel, computed entirely
    server-side via Socrata's own `median()`/`date_diff_d()`, same as
    Calgary.

    Three of these seven were rejected in an earlier pass and only shipped
    after being RE-evaluated live, each time because a previous rejection
    elsewhere in this same investigation had already turned out to be wrong
    once actually re-checked rather than trusted from memory:

    Edmonton (re-evaluated 2026-09-01): the earlier pass called its dataset
    "several overlapping/redundant" — wrong; the real dataset is explicitly
    the city's "Primary Dataset or View" (deduplicated, verified, daily
    updates). What IS genuinely true, checked live: no applicant or
    contractor field, and not because the data is missing — the city's own
    dataset description states plainly that applicant information was
    deliberately excluded as a privacy measure. So Edmonton gets no
    concentration panel, and that is the right call on the city's part, not
    a gap to work around. Its two date columns are also confusingly
    inverted (the UI's "PERMIT_DATE" is actually the API's `issue_date`,
    and "REPORT_PERMIT_DATE" is actually `permit_date`) and, checked live,
    IDENTICAL on every row since 2017 — no processing-time panel either.

    Ottawa (added 2026-09-01): the earlier pass was right that there is no
    API (confirmed live: every resource is `type: "Microsoft Excel"`, no
    queryable url), but wrong that this made the data a dead end — it just
    meant a different pipeline (15 annual workbooks, discovered live from
    the DCAT feed, cached locally). See the Ottawa section below for the
    live-caught stale-rollup-sheet bug this uncovered.

    Montreal (added 2026-09-01): the earlier pass was right that there is no
    cost field (still true, re-confirmed against the live schema) but wrong
    that two boroughs (Lachine, Saint-Léonard) were unavailable — the
    dataset's own methodology text still claims this, but checked live, both
    boroughs have permits dated as recently as any actively-updated borough.
    The migration evidently finished and the caveat text was never updated;
    both are included here.

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
    Mississauga  Esri ArcGIS FeatureServer (`Issued_Building_Permits`,
               services6.arcgis.com), not Socrata — a different query
               mechanism (`outStatistics`/`groupByFieldsForStatistics`
               instead of SoQL `$select`/`$group`). Terms of Use (linked from
               the item's `licenseInfo`) grant a "world-wide, royalty-free,
               non-exclusive... licence to use, modify, and distribute" with
               attribution optional. Only 34,615 rows since 2018-01-02 — an
               order of magnitude smaller than the Socrata cities — so this
               pages raw records (`page_arcgis()`, 2000/request, the
               service's `maxRecordCount`) and aggregates client-side in
               Python, the same shape as Toronto's approach, rather than
               building ArcGIS `outStatistics` calls for every cut this card
               needs. Has three genuinely distinct dates
               (APPLICATION_DATE/ISSUE_DATE/COMPLETE_DATE, confirmed live:
               only 488 of 34,615 rows share the same application and issue
               date), so it gets both a processing-time panel (like Vancouver
               and Calgary) and a build-time panel (like Calgary and
               Edmonton) — the only city with both. No applicant/contractor
               field exists in this schema at all (not excluded for privacy
               like Edmonton — it was simply never collected), so no
               concentration panel.
    Ottawa     No API. 15 annual XLSX workbooks (2011-present) on
               open.ottawa.ca, discovered live from the DCAT feed and cached
               locally (Python/ottawa_cache/, gitignored). Two schema eras
               detected per SHEET, not per year — see the dedicated Ottawa
               section below for the full parsing strategy and the live-
               caught stale-rollup-sheet bug that shaped it. City of Ottawa
               Open Data Terms of Use.
    Montreal   CKAN `datastore_search_sql`, server-side SQL aggregation —
               558,874 rows since 1997 is too many to page raw the way
               Toronto's smaller dataset is. The endpoint blocks the `CAST`
               function outright ("Not authorized to call function CAST")
               but allows the `::type` shorthand and `percentile_cont` for
               server-side medians. No cost field anywhere in this resource's
               schema (a separate pre-aggregated stats CSV exists but isn't
               joinable back to individual permits), so areas/work panels
               here are ranked by permit count, not dollar value — see the
               dedicated Montreal section below. Creative Commons Attribution
               4.0 International (Ville de Montréal).
    Halifax    Esri ArcGIS FeatureServer, a plain TABLE with no geometry at
               all (no lat/long anywhere in this resource, unlike every
               other city here) — `Community` is the only geography.
               18,817 rows since 2020-12, small enough to page raw like
               Mississauga. Richest cost/unit data of any city on this
               page: Estimated_Project_Value populated on 99.3% of rows,
               Net_New_Units pre-computed and 100% populated (no need to
               derive it from separate existing/end-unit counts), and a
               genuine three-date chain (submission/issuance/completed)
               with zero negative-day rows on either interval. See the
               dedicated Halifax section below. Open Government Licence -
               Halifax.
    Winnipeg   Socrata SODA API, dataset `Detailed Building Permit Data`
               (Open Government Licence - Winnipeg). 162,558 rows since
               2010, server-side SoQL aggregation like Calgary, including
               `median()`/`date_diff_d()` for the processing-time and
               build-time panels. No cost field at all (the dataset's own
               description says so), matching it to a separate aggregate
               dataset (by year/neighbourhood/permit type, single-permit
               cells privacy-redacted) that has no permit-level key to join
               back to individual rows — not used, same reasoning as
               Montreal. `applicant_business_name` carries real, unredacted
               business names (no placeholder-redaction pattern like
               Ottawa's), so the concentration panel here needed no string
               filtering beyond excluding blanks. See the dedicated
               Winnipeg section below.

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

    Mississauga's APPL_AREA field is recorded in SQUARE METRES, per its own
    field description ("Applicable permit area of work in square metres") —
    every other city's floor-area field on this page is sqft, and this one
    was initially treated the same way by mistake, producing a physically
    impossible ~100 sqft "average unit size" before the conversion was added
    (SQM_TO_SQFT = 10.7639). Separately, scoping unit economics to every
    RESIDENTIAL permit with RES_UNITS > 0 (no further filter) mixes genuine
    new subdivisions in with ALTERATION/ADDITION permits that merely add a
    secondary suite — checked live, that broader population's $/sqft came out
    over $2,000, another physical impossibility. Restricting to
    SCOPE = 'NEW BUILDING' fixed both problems at once (median $223-253/sqft
    for 2018-2023, in a normal range for Ontario residential construction).
    The resulting 2024-2026 jump to $750K+ over $2.7M median $/unit was
    checked row-by-row rather than assumed away: it tracks a real run of
    ~$7-10M custom detached-home permits (990-1,143 sqm each, verified
    individually), not a data error — with only ~140-190 qualifying permits a
    year in this narrower scope, a handful of genuine luxury builds can swing
    the annual median noticeably, and the card's note says so.

USAGE
    python municipal_permits_etl.py [--refresh]
Exits non-zero on any fetch failure (safe for the scheduled refresh).
"""

import re
import sys
import json
import argparse
from pathlib import Path
from datetime import datetime
from collections import defaultdict

import requests
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = REPO_ROOT / "construction_json"
OTT_CACHE = REPO_ROOT / "Python" / "ottawa_cache"

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


# =============================================================================
# Mississauga — Esri ArcGIS FeatureServer, not Socrata. No server-side
# GROUP BY on date-truncated expressions available on this hosted layer, and
# the row count (34,615 since 2018) is small enough that paging raw records
# and aggregating in Python (like Toronto) is simpler and just as cheap as
# building ArcGIS `outStatistics`/`groupByFieldsForStatistics` calls for
# every cut this card needs.
# =============================================================================

MIS_API = ("https://services6.arcgis.com/hM5ymMLbxIyWTjn2/arcgis/rest/"
          "services/Issued_Building_Permits/FeatureServer/0/query")
MIS_FIELDS = ["STATUS", "FILE_TYPE", "BLDG_TYPE", "SCOPE", "WARD",
             "EST_CON_VALUE", "RES_UNITS", "APPL_AREA", "APPLICATION_DATE",
             "ISSUE_DATE", "COMPLETE_DATE"]
SQM_TO_SQFT = 10.7639

HFX_API = ("https://services2.arcgis.com/11XBiaBYA9Ep0yNJ/arcgis/rest/"
          "services/PPLC_Issued_Building_Permits/FeatureServer/0/query")
HFX_FIELDS = ["Work_Type", "Permit_Status", "Community", "Type_of_Structure",
             "Occupancy_Type", "Estimated_Project_Value", "Net_New_Units",
             "Building_Footprint_Area", "Date_of_Submission",
             "Date_of_Permit_Issuance", "Completed_Date"]


def page_arcgis(url, out_fields, page=2000):
    """Yield feature attribute dicts, paging an Esri FeatureServer query
    with resultOffset/resultRecordCount (maxRecordCount on this service is
    2000)."""
    offset = 0
    while True:
        d = get(url, {"where": "1=1", "outFields": ",".join(out_fields),
                      "orderByFields": "OBJECTID", "resultOffset": offset,
                      "resultRecordCount": page, "f": "json"})
        feats = d.get("features", [])
        if not feats:
            break
        for f in feats:
            yield f["attributes"]
        offset += len(feats)
        print(f"    ...{offset:,}", flush=True)
        if len(feats) < page:
            break


def edate(ms):
    """Esri epoch-millisecond date -> 'YYYY-MM-DD', or None."""
    if ms is None:
        return None
    from datetime import date as _date, timezone as _tz, datetime as _dt
    return _dt.fromtimestamp(ms / 1000, tz=_tz.utc).date().isoformat()


def fetch_mississauga():
    from collections import defaultdict as _dd
    from datetime import date as _date

    def _dateobj(s):
        return _date.fromisoformat(s)

    def median(vals):
        vals = sorted(vals)
        n = len(vals)
        if n == 0:
            return None
        return vals[n // 2] if n % 2 else (vals[n // 2 - 1] + vals[n // 2]) / 2

    rows = list(page_arcgis(MIS_API, MIS_FIELDS))
    total = len(rows)

    by_month_n, by_month_v, by_month_u = _dd(int), _dd(float), _dd(int)
    areas_n, areas_v = _dd(int), _dd(float)
    work_n, work_v = _dd(int), _dd(float)   # BLDG_TYPE (fine-grained)
    use_n, use_v = _dd(int), _dd(float)     # FILE_TYPE (broad category)

    app_to_issue_by_type, app_to_issue_by_year = _dd(list), _dd(list)
    issue_to_complete_by_type, issue_to_complete_by_year = _dd(list), _dd(list)
    econ_by_year = _dd(lambda: {"per_unit": [], "per_sqft": [], "unit_size": []})
    neg_app_issue, neg_issue_complete = 0, 0

    for r in rows:
        val = float(r.get("EST_CON_VALUE") or 0)
        iss = edate(r.get("ISSUE_DATE"))
        app = edate(r.get("APPLICATION_DATE"))
        comp = edate(r.get("COMPLETE_DATE"))
        bldg, use = r.get("BLDG_TYPE"), r.get("FILE_TYPE")
        ward = r.get("WARD")

        if iss and iss >= FLOOR:
            ym = iss[:7]
            by_month_n[ym] += 1
            by_month_v[ym] += val / 1e6
            by_month_u[ym] += int(r.get("RES_UNITS") or 0)
            if ward:
                areas_n[f"Ward {ward}"] += 1
                areas_v[f"Ward {ward}"] += val / 1e6
            if bldg:
                work_n[bldg] += 1
                work_v[bldg] += val / 1e6
            if use:
                use_n[use] += 1
                use_v[use] += val / 1e6

        if app and iss and app >= FLOOR:
            d = (_dateobj(iss) - _dateobj(app)).days
            if d < 0:
                neg_app_issue += 1
            else:
                app_to_issue_by_type[bldg or "(unspecified)"].append(d)
                app_to_issue_by_year[app[:4]].append(d)

        if iss and comp and iss >= FLOOR:
            d = (_dateobj(comp) - _dateobj(iss)).days
            if d < 0:
                neg_issue_complete += 1
            else:
                issue_to_complete_by_type[bldg or "(unspecified)"].append(d)
                issue_to_complete_by_year[iss[:4]].append(d)

        # Unit economics: NEW-BUILDING residential permits with dwelling
        # units added. Two live findings shaped this scope. (1) APPL_AREA's
        # own field description reads "Applicable permit area of work in
        # SQUARE METRES" -- easy to miss, since every other city's floor-area
        # field on this page is in sqft; converted via SQM_TO_SQFT below. (2)
        # Scoping to FILE_TYPE='RESIDENTIAL' and RES_UNITS>0 alone (no SCOPE
        # filter) mixes genuine new subdivisions in with ALTERATION/ADDITION
        # permits that merely add a secondary suite -- checked live, that
        # broader population's $/unit and $/sqft came out physically
        # impossible (median area/unit ~100 sqft, $/sqft over $2,000).
        # Restricting to SCOPE='NEW BUILDING' fixes it: median $902K/unit,
        # 3,264 sqft/unit, $247/sqft -- all in a plausible range for new
        # Mississauga construction. Even within that cleaner population the
        # tail is real (p90 $/unit is still $3.2M, custom/luxury builds), so
        # this still medians per-row ratios rather than summing cost/units,
        # same reasoning as the rest of this project's right-skewed fields.
        if (use == "RESIDENTIAL" and r.get("SCOPE") == "NEW BUILDING"
                and (r.get("RES_UNITS") or 0) > 0 and iss and iss >= FLOOR):
            yr = iss[:4]
            units = int(r["RES_UNITS"])
            if val > 0:
                econ_by_year[yr]["per_unit"].append(val / units)
            sqft_m2 = r.get("APPL_AREA")
            sqft = sqft_m2 * SQM_TO_SQFT if sqft_m2 is not None else None
            if sqft is not None and sqft > 0 and val > 0:
                econ_by_year[yr]["per_sqft"].append(val / sqft)
                econ_by_year[yr]["unit_size"].append(sqft / units)

    def top(n_map, v_map, limit=None):
        out = [[k, n_map[k], round(v_map[k], 1)] for k in n_map]
        out.sort(key=lambda row: -row[2])
        return out[:limit] if limit else out

    def stage(by_type, by_year):
        return {
            "by_type": [[k, len(v), round(median(v), 1)]
                       for k, v in sorted(by_type.items(), key=lambda kv: -len(kv[1]))[:12]],
            "by_year": [[y, len(v), round(median(v), 1)]
                       for y, v in sorted(by_year.items())],
        }

    unit_economics = {
        "scope_note": ("New-building residential permits with dwelling "
                      f"units added (SCOPE = 'NEW BUILDING', RES_UNITS > 0), "
                      f"{FLOOR} forward -- broadening the scope to every "
                      "RESIDENTIAL permit with units (including additions "
                      "and secondary-suite alterations) was checked live and "
                      "produced physically impossible figures (median area "
                      "under 100 sqft), so this is restricted to genuine new "
                      "construction. Figures are the MEDIAN of each permit's "
                      "own $/unit, $/sqft and sqft/unit, not a sum(cost)/"
                      "sum(units) aggregate -- even within this narrower "
                      "scope the tail is real (90th percentile $/unit is "
                      "still ~3.5x the median, custom/luxury builds). "
                      "APPL_AREA is recorded in square METRES on the source "
                      "portal, not square feet like every other city's floor-"
                      "area field on this page -- converted here. 2024 "
                      "onward's higher $/unit was checked row by row, not "
                      "assumed: it tracks a real run of ~$7-10M custom "
                      "detached-home permits (990-1,143 sqm / ~10,600-12,300 "
                      "sqft each), not a data error -- with only ~140-190 "
                      "qualifying permits a year, a handful of these can "
                      "swing the annual median noticeably."),
        "by_year": [],
    }
    for yr in sorted(econ_by_year):
        e = econ_by_year[yr]
        row = [yr, len(e["per_unit"]), median(e["per_unit"]), None, None, None]
        if row[2] is not None:
            row[2] = round(row[2])
        if e["per_sqft"]:
            row[3] = round(median(e["per_sqft"]), 1)
            row[4] = round(median(e["unit_size"])) if e["unit_size"] else None
            row[5] = len(e["per_sqft"])
        unit_economics["by_year"].append(row)

    return {
        "label": "City of Mississauga",
        "cma": "toronto",
        "coverage": ("City of Mississauga only, part of the Toronto CMA "
                    "(not its own metro area) — compare cautiously against "
                    "the Toronto CMA figures elsewhere on this page."),
        "licence": "City of Mississauga Terms of Use (open licence — "
                  "use, modify and redistribute permitted)",
        "count": months_to_series(dict(by_month_n)),
        "value": months_to_series({k: round(v, 2) for k, v in by_month_v.items()}),
        "units_created": months_to_series(dict(by_month_u)),
        "areas": top(areas_n, areas_v, TOP_AREAS),
        "areas_label": "ward",
        "work": top(work_n, work_v)[:8],
        "use": top(use_n, use_v)[:8],
        "quality": {
            "rows": total,
            "note": ("Only ISSUED permits are published here (dataset title: "
                    "\"Issued Building Permits\") — applications that were "
                    "refused or withdrawn before issuance are not included, "
                    "so this is not a full application-to-outcome funnel."),
        },
        "processing": dict(
            {"unit_note": ("Days from application to issuance (APPLICATION_DATE "
                          "to ISSUE_DATE). Median, not mean, since the "
                          f"distribution is right-skewed. {neg_app_issue} rows "
                          "with a negative day-count excluded, not zeroed.")},
            **stage(app_to_issue_by_type, app_to_issue_by_year)),
        "build_time": dict(
            {"group_label": "building type",
             "unit_note": ("Days from issuance to completion (ISSUE_DATE to "
                          "COMPLETE_DATE, populated once STATUS reaches "
                          "'COMPLETED - ALL INSP SIGNED OFF'). Median, not "
                          f"mean. {neg_issue_complete} rows with a negative "
                          "day-count excluded, not zeroed.")},
            **stage(issue_to_complete_by_type, issue_to_complete_by_year)),
        "unit_economics": unit_economics,
    }


# =============================================================================
# Ottawa — no API at all. 15 annual XLSX workbooks (2011-present) on
# open.ottawa.ca, discovered live from the DCAT feed (not a hardcoded item-id
# list, so a newly published year is picked up automatically) and cached
# locally like ewrb_etl.py's XLSX pattern. Two real schema eras, detected per
# SHEET rather than assumed by year or by sheet name:
#   - 2011-2025 ("rich"): CONTRACTOR and APPL. TYPE columns the 2026 format
#     lacks, area already in square FEET. Most years carry one full-year
#     detail sheet ("Sheet1"/"Details"/"Detail"/"Permits"/"Permits 2020"
#     depending on the year) alongside redundant monthly sheets that are
#     pivot/summary tables, not per-permit rows.
#   - 2026 (current, in-progress year): no full-year sheet at all, only
#     monthly detail sheets. No contractor, no appl. type, area in square
#     METRES (converted via SQM_TO_SQFT).
# Every sheet in every file is read and parsed; a sheet with no per-permit
# WARD column (a pivot "Summary" table, or -- checked live -- a normal-
# looking monthly sheet that just has none) correctly parses to nothing and
# contributes zero rows, so there is no need to pick "the right sheet" by
# name at all. This was NOT the original design: an earlier version tried to
# prefer a named full-year sheet over the monthly ones, and broke silently
# on the "2024 to 2025" combined workbook, whose "Permits" rollup sheet
# turned out to be STALE -- it only covers Jan-Aug 2024, while Sep 2024
# through Dec 2025 exist only in that file's monthly sheets. Concatenating
# every parseable sheet and dropping duplicate permit numbers is robust to
# that kind of per-file inconsistency without needing to know about it in
# advance. Every sheet is read via a header-row FINDER (scans for a cell
# that is exactly "WARD"), not a fixed skiprows count -- checked live, at
# least one rich-era file (2017's "Detail" sheet) also carries a banner
# offset, so a fixed offset would have broken silently on that year alone.
# =============================================================================

OTT_DCAT = "https://open.ottawa.ca/api/feed/dcat-us/1.1.json"
OTT_ITEM_DATA = "https://www.arcgis.com/sharing/rest/content/items/{id}/data"

# Raw header text (after stripping to [A-Z0-9]) -> canonical field. Built
# from every header variant actually seen across the 15 files, e.g.
# "ST # "->address (dropped, not needed), "D.U."->"DU", "FT2"->"FT2",
# "PERMIT#"->"PERMIT", "Permit Number"->"PERMITNUMBER".
OTT_COLMAP = {
    "WARD": "ward",
    "CONTRACTOR": "contractor",
    "BLGTYPE": "building_type", "BUILDINGTYPE": "building_type",
    "MUNICIPALITY": "community", "COMMUNITY": "community",
    "DU": "units",
    "VALUE": "value",
    "FT2": "area_sqft", "SQFT": "area_sqft",
    "SQUAREMETRES": "area_sqm", "SQUAREMETRE": "area_sqm",
    "PERMIT": "permit_number", "PERMITNUMBER": "permit_number",
    "APPLTYPE": "appl_type", "APPLICATIONTYPE": "appl_type",
    "ISSUEDDATE": "issued_date", "PERMITISSUEDDATE": "issued_date",
}
# Contractor values that mean "not disclosed", not a real filer -- excluded
# from the concentration panel, not counted as a distinct contractor.
OTT_CONTRACTOR_PLACEHOLDERS = {"CONTRACTOR UNKNOWN", "***CONTRACTOR***", "NAN", ""}


def discover_ottawa_files():
    """Query the DCAT feed live for every "Construction, demolition..."
    annual workbook and return [(item_id, title)]. Not hardcoded: a newly
    published year is picked up automatically on the next run."""
    d = get(OTT_DCAT)
    out = []
    for ds in d.get("dataset", []):
        title = ds.get("title") or ""
        if "construction, demolition" not in title.lower():
            continue
        m = re.search(r"id=([a-f0-9]{32})", ds.get("identifier") or "")
        if m:
            out.append((m.group(1), title))
    return out


def download_ottawa_file(item_id, refresh=False):
    OTT_CACHE.mkdir(parents=True, exist_ok=True)
    path = OTT_CACHE / f"{item_id}.xlsx"
    if refresh or not path.exists() or path.stat().st_size == 0:
        r = requests.get(OTT_ITEM_DATA.format(id=item_id), headers=HEADERS, timeout=300)
        r.raise_for_status()
        path.write_bytes(r.content)
    return path


def find_header_row(raw_rows, max_scan=15):
    """Row index containing a cell that is exactly 'WARD' -- the one column
    label present, unchanged, in every schema era and every file checked,
    and never present in the report-banner prose above it (which says
    'WARDS: All', not 'WARD')."""
    for i, row in enumerate(raw_rows[:max_scan]):
        for cell in row:
            if isinstance(cell, str) and cell.strip().upper() == "WARD":
                return i
    return None


def parse_ottawa_sheet(df_raw):
    """One raw (header=None) sheet -> a DataFrame with canonical columns
    only. Returns None if no header row (e.g. a 'Summary' pivot sheet with
    no 'WARD' column) is found."""
    rows = df_raw.values.tolist()
    hdr = find_header_row(rows)
    if hdr is None:
        return None
    header = [re.sub(r"[^A-Z0-9]", "", str(c).upper()) for c in rows[hdr]]
    colmap = {i: OTT_COLMAP[h] for i, h in enumerate(header) if h in OTT_COLMAP}
    if "ward" not in colmap.values():
        return None
    data = rows[hdr + 1:]
    out = {canon: [] for canon in set(colmap.values())}
    for row in data:
        if all(pd.isna(v) for v in row):
            continue
        for i, canon in colmap.items():
            out[canon].append(row[i] if i < len(row) else None)
    return pd.DataFrame(out)


def load_ottawa_year(item_id, refresh=False, force=False):
    """Read and concatenate EVERY sheet in the workbook, not just an assumed
    full-year rollup sheet -- checked live, the "2024 to 2025" combined
    workbook's "Permits" rollup sheet is stale (only Jan-Aug 2024), while
    its monthly sheets separately cover Sep 2024 through Dec 2025; trusting
    the rollup alone would have silently dropped 16 months. Most years' non-
    detail sheets (pivot "Summary" tables, or a stale rollup's own gaps)
    correctly parse to nothing -- no WARD column to find a header on -- so
    concatenating everything and dropping duplicate permit numbers is robust
    to whichever sheet(s) in a given file actually hold the real data."""
    path = download_ottawa_file(item_id, refresh or force)
    xl = pd.ExcelFile(path)
    frames = []
    for s in xl.sheet_names:
        raw = pd.read_excel(path, sheet_name=s, header=None)
        parsed = parse_ottawa_sheet(raw)
        if parsed is not None and len(parsed):
            frames.append(parsed)
    if not frames:
        return pd.DataFrame()
    df = pd.concat(frames, ignore_index=True)
    if "permit_number" in df:
        df = df.drop_duplicates(subset="permit_number", keep="first")
    return df


def fetch_ottawa(refresh=False):
    files = discover_ottawa_files()
    print(f"  ottawa: discovered {len(files)} annual workbooks")
    cur_year = str(datetime.now().year)
    frames = []
    for item_id, title in files:
        # A closed historical year's workbook never changes once published,
        # so it's cached indefinitely and only re-fetched with --refresh.
        # The CURRENT calendar year's workbook is a moving target -- it
        # updates monthly at the source (per the dataset's own "Update
        # Frequency: Monthly" note) -- so it's always re-downloaded
        # regardless of --refresh, or the scheduled monthly CI run (which
        # never passes --refresh) would cache it once and go stale forever.
        force = cur_year in title
        print(f"    ...{title}{' (current year, forcing re-download)' if force else ''}", flush=True)
        frames.append(load_ottawa_year(item_id, refresh, force))
    df = pd.concat(frames, ignore_index=True)

    df["issued_date"] = pd.to_datetime(df.get("issued_date"), errors="coerce")
    df["value"] = pd.to_numeric(df.get("value"), errors="coerce")
    df["units"] = pd.to_numeric(df.get("units"), errors="coerce").fillna(0)
    if "area_sqft" not in df:
        df["area_sqft"] = None
    if "area_sqm" in df:
        need = df["area_sqft"].isna() & df["area_sqm"].notna()
        df.loc[need, "area_sqft"] = pd.to_numeric(df.loc[need, "area_sqm"], errors="coerce") * SQM_TO_SQFT
    df["area_sqft"] = pd.to_numeric(df["area_sqft"], errors="coerce")

    df = df[df["issued_date"].notna()]
    df["ym"] = df["issued_date"].dt.strftime("%Y-%m")
    df["yr"] = df["issued_date"].dt.strftime("%Y")
    scoped = df[df["ym"] >= FLOOR]

    by_month_n = scoped.groupby("ym").size().to_dict()
    by_month_v = (scoped.groupby("ym")["value"].sum() / 1e6).round(2).to_dict()

    def top(field, limit=None):
        g = scoped.dropna(subset=[field])
        g = g[g[field].astype(str).str.strip() != ""]
        agg = g.groupby(field).agg(n=("value", "size"), val=("value", "sum"))
        agg = agg.sort_values("val", ascending=False)
        out = [[k, int(r["n"]), round(r["val"] / 1e6, 1)] for k, r in agg.iterrows()]
        return out[:limit] if limit else out

    areas = top("community", TOP_AREAS)
    # "work" = building type (fine-grained, matches other cities' convention
    # for that panel); "use" = application type (Construction/Demolition/
    # Pool Enclosure/..., the broad category, absent for 2026's in-progress
    # rows since that format dropped the column).
    work = top("building_type")[:8]
    use = top("appl_type")[:8] if "appl_type" in scoped else []

    # Concentration: real contractor names only, placeholder values (a
    # redacted "contractor is the owner", or genuinely blank) excluded from
    # both the ranking and the distinct-filer count. Not available for 2026
    # rows (no contractor column that year) -- those rows simply don't
    # contribute, same as any other missing-field row elsewhere on this page.
    conc = None
    if "contractor" in scoped:
        c = scoped.dropna(subset=["contractor"]).copy()
        c["contractor"] = c["contractor"].astype(str).str.strip()
        named = c[~c["contractor"].str.upper().isin(OTT_CONTRACTOR_PLACEHOLDERS)]
        has_field = len(c)
        agg = named.groupby("contractor").agg(n=("value", "size"), val=("value", "sum"))
        threshold = 20
        qualifying = agg[agg["n"] >= threshold].sort_values("n", ascending=False)
        conc = {
            "contractors": {
                "threshold": threshold,
                "coverage_reason": ("the city redacts this field to "
                                    "\"CONTRACTOR UNKNOWN\" or "
                                    "\"***CONTRACTOR***\" when the "
                                    "contractor is the property owner, or "
                                    "leaves it blank"),
                "field_coverage_pct": round(len(named) / has_field * 100, 1) if has_field else 0,
                "total_distinct": agg.shape[0],
                "qualifying": qualifying.shape[0],
                "permits_covered": int(qualifying["n"].sum()),
                "pct_of_field_permits": round(qualifying["n"].sum() / len(named) * 100, 1) if len(named) else 0,
                "top": [[k, int(r["n"]), round(r["val"] / 1e6, 1)]
                       for k, r in qualifying.head(15).iterrows()],
            },
        }

    # Unit economics: residential building types with dwelling units added.
    # Ottawa has no "new construction only" flag the way Mississauga's SCOPE
    # or Calgary's workclass do -- checked live, appl_type='Construction' is
    # the broadest category (covers additions and alterations too, not just
    # new builds), so units>0 on a residential building type is the closest
    # available proxy and is stated as such, not presented as more precise
    # than it is. Learned from Mississauga: medians of each permit's own
    # ratio, not sum(cost)/sum(units), and floor area already in sqft for
    # every era except 2026 (converted above).
    RES_TYPES = {"SINGLE", "SEMI-DETACHED", "SEMI", "ROWHOUSE", "ROW", "DUPLEX",
                "TRIPLEX", "APARTMENT", "TOWNHOUSE"}
    econ_scope = scoped[scoped["units"] > 0].copy()
    if "building_type" in econ_scope:
        econ_scope = econ_scope[econ_scope["building_type"].astype(str).str.upper()
                                .str.strip().isin(RES_TYPES)]
    econ_scope = econ_scope[econ_scope["value"] > 0]
    unit_economics = {
        "scope_note": ("Residential building types (single/semi/row/duplex/"
                      f"triplex/apartment/townhouse) with dwelling units "
                      f"added, {FLOOR} forward. Ottawa has no 'new "
                      "construction only' flag the way other cities' data "
                      "does -- units added on a residential permit is the "
                      "closest available proxy, and may include some large "
                      "additions/conversions alongside new builds. Figures "
                      "are the MEDIAN of each permit's own $/unit, $/sqft "
                      "and sqft/unit, not a sum(cost)/sum(units) aggregate, "
                      "the same reasoning as Mississauga's equivalent panel. "
                      "Floor area is recorded in square feet for 2011-2025 "
                      "and square metres for 2026 (converted here). "
                      "IMPORTANT, checked live: a large share of this "
                      "declared VALUE clusters tightly on a small number of "
                      "near-identical $/sqft rates (hundreds of permits "
                      "within cents of $167.22/sqft or $185.87/sqft in a "
                      "single year) -- not seen on office/retail/"
                      "institutional permits in the same file -- consistent "
                      "with a standard municipal fee-assessment schedule for "
                      "new residential construction rather than each "
                      "builder's independently reported project cost. So "
                      "$/sqft here likely tracks Ottawa's own rate table "
                      "more than the real market, and $/unit (which depends "
                      "on the same VALUE field) inherits the same caveat."),
        "by_year": [],
    }
    for yr, grp in econ_scope.groupby("yr"):
        per_unit = (grp["value"] / grp["units"]).tolist()
        row = [yr, len(grp), round(pd.Series(per_unit).median()) if per_unit else None,
              None, None, None]
        sq = grp.dropna(subset=["area_sqft"])
        sq = sq[sq["area_sqft"] > 0]
        if len(sq):
            row[3] = round((sq["value"] / sq["area_sqft"]).median(), 1)
            row[4] = round((sq["area_sqft"] / sq["units"]).median())
            row[5] = len(sq)
        unit_economics["by_year"].append(row)
    unit_economics["by_year"].sort(key=lambda r: r[0])

    total = len(scoped)
    has_value = int(scoped["value"].notna().sum())

    result = {
        "label": "City of Ottawa",
        "cma": "ottawa",
        "coverage": ("Full City of Ottawa (post-amalgamation boundary), "
                    "which is very close to the Ottawa-Gatineau CMA's "
                    "Ontario side -- but the CMA also includes Gatineau and "
                    "other Quebec municipalities this data does not cover."),
        "licence": "City of Ottawa Open Data Terms of Use",
        "count": months_to_series(by_month_n),
        "value": months_to_series(by_month_v),
        "areas": areas,
        "areas_label": "community",
        "work": work,
        "use": use,
        "quality": {
            "rows": total,
            "has_value": has_value,
            "value_coverage_pct": round(has_value / total * 100, 1) if total else 0,
            "note": ("No live API -- 15 annual Excel workbooks with two "
                    "schema eras (see Python/municipal_permits_etl.py). No "
                    "processing-time or build-time panel: only one date "
                    "(issuance) exists in this data, unlike cities with "
                    "application/completion dates too."),
        },
        "unit_economics": unit_economics,
    }
    if conc:
        result["concentration"] = conc
    return result


# =============================================================================
# Montreal — CKAN datastore_search_sql, server-side SQL aggregation (like
# Calgary/Edmonton) rather than paging raw records (Toronto's approach):
# 558,874 rows is too many to page economically, and this portal's SQL
# endpoint handles GROUP BY, percentile_cont (server-side median) and date
# arithmetic on the TEXT-typed date columns via `::date` casts fine -- just
# not the `CAST(...AS...)` function form, which the endpoint blocks outright
# ("Not authorized to call function CAST"; the `::type` shorthand works).
#
# NO COST FIELD AT ALL -- re-confirmed live 2026-09-01, matching an earlier
# evaluation: this resource's schema has no per-permit value/cost column of
# any kind (the separate "Statistiques..." CSV has cost, but only
# pre-aggregated by year/borough/type, not joinable back to an individual
# permit). So Montreal gets no $-based cross-chart (falls back to dwelling
# units created, like Toronto), no unit-economics table, and its areas/work/
# use panels are ranked and formatted by PERMIT COUNT rather than dollar
# value -- the only city on this page where that's true, signalled via
# "value_basis": "count" for the page to read instead of assuming dollars.
#
# The other half of that earlier evaluation -- Lachine and Saint-Léonard
# excluded due to an in-progress system migration -- turned out to be STALE:
# the dataset's own methodology text still says their data "n'est pas
# disponible actuellement", but checked live, both boroughs have permits
# with the exact same most-recent date (2026-08-24) as an actively-updated
# borough like Le Plateau-Mont-Royal. The migration evidently finished and
# nobody updated the caveat text; both boroughs are included here.
# =============================================================================

MTL_SQL_API = "https://donnees.montreal.ca/api/3/action/datastore_search_sql"
MTL_RID = "5232a72d-235a-48eb-ae20-bb9d501300ad"

# code_type_base_demande -> human label (confirmed against the live data's
# own distinct values: TR dominates at 345,588 of 558,874 rows).
MTL_WORK_LABELS = {
    "TR": "Transformation",
    "CA": "Certificat d'autorisation",
    "CO": "Construction",
    "DE": "Démolition",
}


def mtl_sql(sql):
    return get(MTL_SQL_API, {"sql": sql})["result"]["records"]


def fetch_montreal():
    since_floor = f"date_emission >= '{FLOOR}-01'"

    monthly_n = mtl_sql(f'SELECT substr(date_emission,1,7) as ym, count(*) as n '
                       f'FROM "{MTL_RID}" WHERE {since_floor} GROUP BY ym')
    by_month_n = {r["ym"]: int(r["n"]) for r in monthly_n if r.get("ym")}

    # nb_logements is TEXT; '^[0-9]+$' excludes blanks and non-numeric junk
    # (checked live: the field is otherwise clean, no placeholder strings).
    monthly_u = mtl_sql(f"SELECT substr(date_emission,1,7) as ym, "
                       f"sum(nb_logements::integer) as units "
                       f'FROM "{MTL_RID}" WHERE {since_floor} '
                       f"AND nb_logements ~ '^[0-9]+$' GROUP BY ym")
    by_month_u = {r["ym"]: int(float(r["units"] or 0)) for r in monthly_u if r.get("ym")}

    areas_raw = mtl_sql(f'SELECT arrondissement, count(*) as n FROM "{MTL_RID}" '
                       f"WHERE {since_floor} AND arrondissement IS NOT NULL "
                       f"GROUP BY arrondissement ORDER BY n DESC")
    work_raw = mtl_sql(f'SELECT code_type_base_demande, count(*) as n FROM "{MTL_RID}" '
                      f"WHERE {since_floor} GROUP BY code_type_base_demande ORDER BY n DESC")
    # description_type_batiment carries real casing duplicates across
    # boroughs (checked live: "Commercial"/"commercial"/"Commerce" all
    # appear separately) -- upper()'d here rather than picking one casing
    # arbitrarily, so the grouping is honest about being normalized.
    use_raw = mtl_sql(f"SELECT upper(description_type_batiment) as bt, count(*) as n "
                     f'FROM "{MTL_RID}" WHERE {since_floor} '
                     f"AND description_type_batiment IS NOT NULL "
                     f"GROUP BY bt ORDER BY n DESC LIMIT 8")

    def tidy_count(rows, key):
        # val = n (count), same convention as every other city's [name,n,val]
        # tuple, but here val IS the count -- see "value_basis" below.
        return [[r[key], int(r["n"]), int(r["n"])] for r in rows if r.get(key)]

    areas = tidy_count(areas_raw, "arrondissement")[:TOP_AREAS]
    work = [[MTL_WORK_LABELS.get(r["code_type_base_demande"], r["code_type_base_demande"]),
            int(r["n"]), int(r["n"])] for r in work_raw if r.get("code_type_base_demande")]
    use = [[r["bt"], int(r["n"]), int(r["n"])] for r in use_raw if r.get("bt")]

    # Processing time: date_debut -> date_emission, median via server-side
    # percentile_cont. Real signal (checked live: only 27% same-day, zero
    # negative-day rows), unlike Edmonton's identical-date dead end.
    proc_type = mtl_sql(f"SELECT code_type_base_demande, "
                       f"percentile_cont(0.5) within group "
                       f"(order by (date_emission::date - date_debut::date)) as med, "
                       f"count(*) as n FROM \"{MTL_RID}\" WHERE {since_floor} "
                       f"AND date_emission::date >= date_debut::date "
                       f"GROUP BY code_type_base_demande")
    proc_year = mtl_sql(f"SELECT substr(date_debut,1,4) as yr, "
                       f"percentile_cont(0.5) within group "
                       f"(order by (date_emission::date - date_debut::date)) as med, "
                       f"count(*) as n FROM \"{MTL_RID}\" WHERE {since_floor} "
                       f"AND date_emission::date >= date_debut::date "
                       f"GROUP BY yr ORDER BY yr")

    total = int(mtl_sql(f'SELECT count(*) as n FROM "{MTL_RID}" '
                       f"WHERE {since_floor}")[0]["n"])

    return {
        "label": "City of Montreal",
        "cma": "montreal",
        "coverage": ("Full City of Montreal (all 19 boroughs, including "
                    "Lachine and Saint-Léonard), which is close to but not "
                    "the same as the Montréal CMA -- the CMA also includes "
                    "Laval, Longueuil and dozens of off-island municipalities "
                    "this data does not cover."),
        "licence": "Creative Commons Attribution 4.0 International "
                  "(Ville de Montréal)",
        "count": months_to_series(by_month_n),
        "units_created": months_to_series(by_month_u),
        "areas": areas,
        "areas_label": "borough",
        "work": work,
        "use": use,
        "value_basis": "count",
        "quality": {
            "rows": total,
            "unparseable_cost_pct": 100.0,
            "note": ("This resource has no cost/value field at all -- "
                    "confirmed against its own schema, not an undercount "
                    "like Toronto's. Montréal separately publishes a "
                    "PRE-AGGREGATED cost statistics file (by year, borough "
                    "and permit type), but it cannot be joined back to "
                    "individual permits, so it is not used here. Areas, work "
                    "type and building-type panels are therefore ranked by "
                    "PERMIT COUNT, not dollar value, unlike every other city "
                    "on this page."),
        },
        "processing": {
            "unit_note": ("Days from application to issuance (date_debut to "
                          "date_emission). Median, not mean. Rows where "
                          "issuance precedes application (a data-entry "
                          "artifact, none found live as of this build) would "
                          "be excluded, not zeroed."),
            "by_type": [[MTL_WORK_LABELS.get(r["code_type_base_demande"], r["code_type_base_demande"]),
                        int(r["n"]), round(float(r["med"]), 1)]
                       for r in proc_type if r.get("med") is not None],
            "by_year": [[r["yr"], int(r["n"]), round(float(r["med"]), 1)]
                       for r in proc_year if r.get("yr") and r.get("med") is not None],
        },
    }


# =============================================================================
# Halifax (HRM) — Esri ArcGIS FeatureServer, small enough (18,817 rows since
# 2020-12) to page raw like Mississauga rather than build outStatistics
# calls. This is a TABLE, not a feature layer -- no geometry, no lat/long at
# all, unlike every other city here, so Community stands in as the only
# geography. Richest cost/unit data of any city on this page: a real
# THREE-date chain (submission/issuance/completed, all populated and none of
# Edmonton's identical-dates trap -- checked live, zero negative-day rows on
# either interval) giving both a processing-time and a build-time panel, a
# clean 3-value Work_Type field ('New Building' is a real new-construction
# scope filter, unlike Mississauga's messier SCOPE or Ottawa's total lack of
# one), Estimated_Project_Value populated on 99.3% of rows (the cleanest cost
# field of any city here), and Net_New_Units pre-computed and 100% populated
# -- no need to derive it from separate existing/end-unit counts the way
# Mississauga's RES_UNITS or Calgary's housingunits are used directly.
# Building_Footprint_Area is in square METRES (confirmed live from sample
# rows' magnitudes, same trap as Mississauga/Ottawa's 2026 file -- converted
# via SQM_TO_SQFT). Occupancy_Type='Residential Use' scopes unit economics
# more precisely than Type_of_Structure alone: checked live, a permit can
# carry Type_of_Structure='Dwelling - Single Detached' with
# Occupancy_Type='Garage' (an accessory structure on a residential lot, not
# a home), which Occupancy_Type correctly excludes.
#
# Most_Recent_Inspection / Inspection_Outcome (the user flagged these as
# "interesting to see if there's more data on that somewhere else") turned
# out to be a workflow-status snapshot, not a separate dataset or a
# meaningfully aggregable metric -- checked live, they're just this same
# permit's own most recent inspection stage/result (e.g. "Building - Part 9 -
# Final" / "Passed"), no external inspections table found. Not built into a
# panel: a status snapshot doesn't trend the way a date interval or a dollar
# figure does, and forcing one would manufacture insight the data doesn't
# actually support.
# =============================================================================

def fetch_halifax():
    from collections import defaultdict as _dd
    from datetime import date as _date

    def _dateobj(s):
        return _date.fromisoformat(s)

    def median(vals):
        vals = sorted(vals)
        n = len(vals)
        if n == 0:
            return None
        return vals[n // 2] if n % 2 else (vals[n // 2 - 1] + vals[n // 2]) / 2

    rows = list(page_arcgis(HFX_API, HFX_FIELDS))

    by_month_n, by_month_v, by_month_u = _dd(int), _dd(float), _dd(int)
    areas_n, areas_v = _dd(int), _dd(float)
    work_n, work_v = _dd(int), _dd(float)

    sub_to_issue_by_type, sub_to_issue_by_year = _dd(list), _dd(list)
    issue_to_complete_by_type, issue_to_complete_by_year = _dd(list), _dd(list)
    econ_by_year = _dd(lambda: {"per_unit": [], "per_sqft": [], "unit_size": []})
    neg_sub_issue = neg_issue_complete = 0
    issued_total = 0

    for r in rows:
        val = float(r.get("Estimated_Project_Value") or 0)
        iss = edate(r.get("Date_of_Permit_Issuance"))
        sub = edate(r.get("Date_of_Submission"))
        comp = edate(r.get("Completed_Date"))
        work, area = r.get("Work_Type"), r.get("Community")
        units = r.get("Net_New_Units")

        # Only ISSUED permits (a real Date_of_Permit_Issuance) count toward
        # the main series -- this dataset also carries applications still in
        # review, withdrawn or expired before issuance, unlike every other
        # city's "issued permits" framing on this page.
        if iss and iss >= FLOOR:
            issued_total += 1
            ym = iss[:7]
            by_month_n[ym] += 1
            by_month_v[ym] += val / 1e6
            by_month_u[ym] += int(units or 0)
            if area:
                areas_n[area] += 1
                areas_v[area] += val / 1e6
            if work:
                work_n[work] += 1
                work_v[work] += val / 1e6

        if sub and iss and sub >= FLOOR:
            d = (_dateobj(iss) - _dateobj(sub)).days
            if d < 0:
                neg_sub_issue += 1
            else:
                sub_to_issue_by_type[work or "(unspecified)"].append(d)
                sub_to_issue_by_year[sub[:4]].append(d)

        if iss and comp and iss >= FLOOR:
            d = (_dateobj(comp) - _dateobj(iss)).days
            if d < 0:
                neg_issue_complete += 1
            else:
                issue_to_complete_by_type[work or "(unspecified)"].append(d)
                issue_to_complete_by_year[iss[:4]].append(d)

        if (work == "New Building" and r.get("Occupancy_Type") == "Residential Use"
                and (units or 0) > 0 and iss and iss >= FLOOR):
            yr = iss[:4]
            if val > 0:
                econ_by_year[yr]["per_unit"].append(val / units)
            sqft_m2 = r.get("Building_Footprint_Area")
            sqft = sqft_m2 * SQM_TO_SQFT if sqft_m2 is not None else None
            if sqft is not None and sqft > 0 and val > 0:
                econ_by_year[yr]["per_sqft"].append(val / sqft)
                econ_by_year[yr]["unit_size"].append(sqft / units)

    def top(n_map, v_map, limit=None):
        out = [[k, n_map[k], round(v_map[k], 1)] for k in n_map]
        out.sort(key=lambda row: -row[2])
        return out[:limit] if limit else out

    def stage(by_type, by_year):
        return {
            "by_type": [[k, len(v), round(median(v), 1)]
                       for k, v in sorted(by_type.items(), key=lambda kv: -len(kv[1]))[:12]],
            "by_year": [[y, len(v), round(median(v), 1)]
                       for y, v in sorted(by_year.items())],
        }

    unit_economics = {
        "scope_note": ("New-building residential permits with net new units "
                      f"added (Work_Type = 'New Building', Occupancy_Type = "
                      f"'Residential Use', Net_New_Units > 0), {FLOOR} "
                      "forward. Occupancy_Type rather than Type_of_Structure "
                      "alone excludes accessory structures like garages that "
                      "share a residential structure type but are not "
                      "dwellings. Figures are the MEDIAN of each permit's "
                      "own $/unit, $/sqft and sqft/unit, the same reasoning "
                      "as every other right-skewed field on this page. "
                      "Building_Footprint_Area is recorded in square metres "
                      "on the source portal, not square feet -- converted "
                      "here."),
        "by_year": [],
    }
    for yr in sorted(econ_by_year):
        e = econ_by_year[yr]
        row = [yr, len(e["per_unit"]), median(e["per_unit"]), None, None, None]
        if row[2] is not None:
            row[2] = round(row[2])
        if e["per_sqft"]:
            row[3] = round(median(e["per_sqft"]), 1)
            row[4] = round(median(e["unit_size"])) if e["unit_size"] else None
            row[5] = len(e["per_sqft"])
        unit_economics["by_year"].append(row)

    return {
        "label": "Halifax Regional Municipality",
        "cma": "halifax",
        "coverage": ("Halifax Regional Municipality, which -- unusually for "
                    "this page -- IS essentially the whole Halifax CMA "
                    "(HRM's boundary is the amalgamated former cities of "
                    "Halifax and Dartmouth plus surrounding county area, "
                    "close to StatCan's CMA definition), so this series "
                    "should track the metro figures elsewhere on this page "
                    "more closely than most other cities here."),
        "licence": "Open Government Licence - Halifax",
        "count": months_to_series(dict(by_month_n)),
        "value": months_to_series({k: round(v, 2) for k, v in by_month_v.items()}),
        "units_created": months_to_series(dict(by_month_u)),
        "areas": top(areas_n, areas_v, TOP_AREAS),
        "areas_label": "community",
        "work": top(work_n, work_v),
        "quality": {
            "rows": issued_total,
            "note": ("Only permits with a real issuance date count toward "
                    "these figures -- this dataset also carries applications "
                    "still in review, withdrawn, expired or cancelled before "
                    "issuance, unlike most other cities' data here."),
        },
        "processing": dict(
            {"unit_note": ("Days from submission to issuance. Median, not "
                          f"mean. {neg_sub_issue} rows with a negative "
                          "day-count excluded, not zeroed.")},
            **stage(sub_to_issue_by_type, sub_to_issue_by_year)),
        "build_time": dict(
            {"group_label": "work type",
             "unit_note": ("Days from issuance to the Completed_Date field. "
                          f"Median, not mean. {neg_issue_complete} rows with "
                          "a negative day-count excluded, not zeroed. Only "
                          "58% of issued permits have a completion date -- "
                          "many are still in progress.")},
            **stage(issue_to_complete_by_type, issue_to_complete_by_year)),
        "unit_economics": unit_economics,
    }


# =============================================================================
# Winnipeg — Socrata SoQL, server-side aggregation like Calgary/Edmonton.
# 162,558 rows since 2010 (deepest history bar Montreal). NO cost field —
# the dataset's own description says so plainly ("containing most
# information about the permit WITH THE EXCEPTION OF declared construction
# value"), matching it to a separate "Aggregate Building Permit Data"
# dataset that sums declared value by year/neighbourhood/permit_group only
# (single-permit-count cells have their value stripped for privacy and
# rolled into a 'WINNIPEG OMITTED CONSTRUCTION VALUE' bucket) — not
# joinable back to individual permits, same reasoning as Montreal's separate
# stats file, so not used here. value_basis:'count', like Montreal.
#
# What IS unusually clean here: `applicant_business_name` carries real,
# unredacted business names (Qualico Developments, A&S Homes, Randall
# Homes...) with NO placeholder-redaction pattern like Ottawa's `CONTRACTOR
# UNKNOWN` — checked live, the only non-name value is a genuine blank, so
# the concentration panel here needs no placeholder-string filtering at
# all, just excluding nulls. A genuine three-date chain
# (application_received_date/issue_date/final_date, 100%/100%/91.6%
# populated, only 3 and 30 negative-day rows respectively out of 162,558)
# gives both a processing-time and a build-time panel, computed entirely
# server-side via SoQL's `median()` + `date_diff_d()`, the same mechanism
# as Calgary.
#
# One caveat disclosed on the dataset's own page, not discovered by
# inspection: "the detailed and aggregate building permit data has been
# revised because of a minor over-statement of approved dwelling units, and
# the counting methodology has been updated... Data before November 14,
# 2022 has not been updated" -- so dwelling_units_created before that date
# uses an older, less precise counting method than the same field after it.
# Stated in the quality note rather than silently plotted as one continuous
# series.
# =============================================================================

WPG_API = "https://data.winnipeg.ca/resource/it4w-cpf4.json"


def fetch_winnipeg():
    def agg(select, group_by=None, order_by=None, where=None, limit=200):
        params = {"$select": select, "$limit": limit}
        if group_by:
            params["$group"] = group_by
        if order_by:
            params["$order"] = order_by
        if where:
            params["$where"] = where
        return get(WPG_API, params)

    since_floor = f"issue_date >= '{FLOOR}-01'"

    monthly = agg("date_trunc_ym(issue_date) as ym,count(*) as n,"
                 "sum(dwelling_units_created) as units",
                 "ym", "ym", where=since_floor, limit=250)
    by_month_n = {r["ym"][:7]: int(r["n"]) for r in monthly if r.get("ym")}
    by_month_u = {r["ym"][:7]: int(float(r.get("units") or 0))
                 for r in monthly if r.get("ym")}

    areas_raw = agg("neighbourhood_name,count(*) as n", "neighbourhood_name",
                   order_by="n desc", where=since_floor, limit=500)
    work_raw = agg("permit_type,count(*) as n", "permit_type",
                  order_by="n desc", where=since_floor, limit=50)
    use_raw = agg("permit_group,count(*) as n", "permit_group",
                 order_by="n desc", where=since_floor, limit=10)

    def tidy_count(rows, key):
        return [[r[key], int(r["n"]), int(r["n"])] for r in rows if r.get(key)]

    areas = tidy_count(areas_raw, "neighbourhood_name")[:TOP_AREAS]
    work = tidy_count(work_raw, "permit_type")
    use = tidy_count(use_raw, "permit_group")

    # Processing and build time: server-side median via date_diff_d, same
    # mechanism as Calgary. Negative-day rows (3 of 162,558 for submission
    # -> issuance, 30 for issuance -> completion, checked live) excluded in
    # the WHERE clause rather than zeroed.
    proc_where = (f"{since_floor} and application_received_date is not null "
                 f"and date_diff_d(issue_date,application_received_date) >= 0")
    proc_type = agg("permit_type,median(date_diff_d(issue_date,application_received_date)) "
                   "as med,count(*) as n", "permit_type", where=proc_where, limit=50)
    proc_year = agg("date_trunc_y(application_received_date) as yr,"
                   "median(date_diff_d(issue_date,application_received_date)) as med,"
                   "count(*) as n", "yr", "yr", where=proc_where, limit=30)

    bt_where = (f"{since_floor} and final_date is not null "
               f"and date_diff_d(final_date,issue_date) >= 0")
    bt_type = agg("permit_type,median(date_diff_d(final_date,issue_date)) "
                 "as med,count(*) as n", "permit_type", where=bt_where, limit=50)
    bt_year = agg("date_trunc_y(issue_date) as yr,"
                 "median(date_diff_d(final_date,issue_date)) as med,"
                 "count(*) as n", "yr", "yr", where=bt_where, limit=30)

    # Concentration: real business names, no placeholder redaction found
    # live -- just excluding blanks.
    conc_where = f"{since_floor} and applicant_business_name is not null"
    total = int(agg("count(*) as n", where=since_floor, limit=1)[0]["n"])
    conc_rows = agg("applicant_business_name,count(*) as n",
                    "applicant_business_name", order_by="n desc",
                    where=conc_where, limit=15000)
    has_field = sum(int(r["n"]) for r in conc_rows)
    threshold = 20
    qualifying = [r for r in conc_rows if int(r["n"]) >= threshold]
    covered = sum(int(r["n"]) for r in qualifying)

    return {
        "label": "City of Winnipeg",
        "cma": "winnipeg",
        "coverage": ("City of Winnipeg proper. The Winnipeg CMA also "
                    "includes several surrounding rural municipalities and "
                    "towns this data does not cover, though the city itself "
                    "makes up the large majority of the CMA's population."),
        "licence": "Open Government Licence - Winnipeg",
        "count": months_to_series(by_month_n),
        "units_created": months_to_series(by_month_u),
        "areas": areas,
        "areas_label": "neighbourhood",
        "work": work,
        "use": use,
        "value_basis": "count",
        "quality": {
            "rows": total,
            "unparseable_cost_pct": 100.0,
            "note": ("This dataset has no cost/value field at all, per its "
                    "own description. Winnipeg separately publishes an "
                    "aggregate declared-value dataset (by year, "
                    "neighbourhood and permit type; single-permit cells have "
                    "their value stripped for privacy), but it has no "
                    "permit-level key to join back to individual rows, so "
                    "it is not used here. Areas, work type and use panels "
                    "are therefore ranked by PERMIT COUNT, not dollar "
                    "value, like Montreal. Separately: the city revised its "
                    "dwelling-unit counting methodology and states plainly "
                    "that data before 2022-11-14 was not updated to match, "
                    "so dwelling_units_created before and after that date "
                    "may not be perfectly comparable."),
        },
        "processing": {
            "unit_note": ("Days from application to issuance. Median, not "
                          "mean, computed server-side (SoQL median() over "
                          "date_diff_d()). 3 rows with a negative day-count "
                          "(of 162,558) excluded, not zeroed."),
            "by_type": [[r["permit_type"], int(r["n"]), round(float(r["med"]), 1)]
                       for r in proc_type if r.get("med") is not None],
            "by_year": [[r["yr"][:4], int(r["n"]), round(float(r["med"]), 1)]
                       for r in proc_year if r.get("yr") and r.get("med") is not None],
        },
        "build_time": {
            "group_label": "permit type",
            "unit_note": ("Days from issuance to the Final Date field. "
                          "Median, not mean, computed server-side. 30 rows "
                          "with a negative day-count excluded, not zeroed. "
                          "91.6% of permits have a final date; the rest are "
                          "still open."),
            "by_type": [[r["permit_type"], int(r["n"]), round(float(r["med"]), 1)]
                       for r in bt_type if r.get("med") is not None],
            "by_year": [[r["yr"][:4], int(r["n"]), round(float(r["med"]), 1)]
                       for r in bt_year if r.get("yr") and r.get("med") is not None],
        },
        "concentration": {
            "applicants": {
                "threshold": threshold,
                "field_coverage_pct": round(has_field / total * 100, 1) if total else 0,
                "total_distinct": len(conc_rows),
                "qualifying": len(qualifying),
                "permits_covered": covered,
                "pct_of_field_permits": round(covered / has_field * 100, 1) if has_field else 0,
                "top": [[r["applicant_business_name"], int(r["n"]), int(r["n"])]
                       for r in qualifying[:15]],
            },
        },
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true",
                    help="Vancouver/Toronto/Calgary/Edmonton/Mississauga are "
                         "always queried live and never cached, so this flag "
                         "only affects Ottawa: force re-download every "
                         "cached historical-year XLSX workbook, not just the "
                         "current year (which is always re-downloaded "
                         "regardless, since it updates monthly at the "
                         "source and closed years never change)")
    args = ap.parse_args()

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
        print("fetching Mississauga (Esri ArcGIS FeatureServer, paged)...")
        cities["mississauga"] = fetch_mississauga()
        print(f"  mississauga: {len(cities['mississauga']['areas'])} wards, "
              f"{len(cities['mississauga']['work'])} building types")
        print("fetching Ottawa (15 annual XLSX workbooks, no API)...")
        cities["ottawa"] = fetch_ottawa(args.refresh)
        print(f"  ottawa: {len(cities['ottawa']['areas'])} communities, "
              f"{len(cities['ottawa']['work'])} building types")
        print("fetching Montreal (CKAN datastore_search_sql, server-side aggregation)...")
        cities["montreal"] = fetch_montreal()
        print(f"  montreal: {len(cities['montreal']['areas'])} boroughs, "
              f"{len(cities['montreal']['work'])} work types")
        print("fetching Halifax (Esri ArcGIS FeatureServer, paged)...")
        cities["halifax"] = fetch_halifax()
        print(f"  halifax: {len(cities['halifax']['areas'])} communities, "
              f"{len(cities['halifax']['work'])} work types")
        print("fetching Winnipeg (Socrata SoQL, server-side aggregation)...")
        cities["winnipeg"] = fetch_winnipeg()
        print(f"  winnipeg: {len(cities['winnipeg']['areas'])} neighbourhoods, "
              f"{len(cities['winnipeg']['work'])} permit types")
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
            "mississauga": "City of Mississauga open data, Issued Building "
                          "Permits (Esri ArcGIS FeatureServer)",
            "ottawa": "City of Ottawa open data, Construction/Demolition/Pool "
                     "Permits (15 annual XLSX workbooks, no API)",
            "montreal": "Ville de Montréal open data, Permis de construction, "
                       "transformation et démolition (CKAN datastore_search_sql)",
            "halifax": "Halifax Regional Municipality open data, PPL&C "
                      "Building Permits (Esri ArcGIS FeatureServer)",
            "winnipeg": "City of Winnipeg open data, Detailed Building "
                       "Permit Data (Socrata SODA API)",
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
