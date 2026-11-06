"""
city_build_time_etl.py

How long NEW HOMES take to build, from six cities' own permit records, on a
basis built to sit beside CMHC's "Average Length of Construction" (see
construction_time_etl.py) in the Construction Tracker's "How long it takes to
build" card.

    -> construction_json/city_build.json

WHY A SEPARATE SCRIPT
    municipal_permits_etl.py already publishes a per-city "build time" panel,
    but it answers a different question and cannot be compared with CMHC:
      1. it mixes every permit type (plumbing, HVAC, alterations, demolition)
         instead of new homes only;
      2. it is grouped by the year the permit was ISSUED, so recent years
         hold only the projects that finished fast (Mississauga 2026 = 59
         days) -- CMHC groups by the month the home was COMPLETED;
      3. it is unweighted, while CMHC averages over dwelling units, so a
         200-unit apartment building counts 200 times.
    This script fixes all three for new residential construction only, and
    leaves municipal.json (and its panels) untouched -- one producer per
    panel.

CITIES, SCOPE AND END DATE (each checked live 2026-11-06)
    Calgary      Socrata c2es-76ed. workclass='New', permitclassmapped=
                 'Residential', housingunits>0, statuscurrent='Completed'.
                 End date: completeddate. History from 1999.
    Edmonton     Socrata 24uj-dj8v. work_type '(01) New' / '(01) Building -
                 New', units_added>0. End date: occupancy_granted_date, which
                 the city only records systematically for permits finalized
                 on/after 2022-01-01 -- so completion years start in 2022.
    Winnipeg     Socrata it4w-cpf4. work_type='Construct New',
                 dwelling_units_created>0, status='Closed'. End date:
                 final_date. History from 2010.
    Mississauga  ArcGIS Issued_Building_Permits. SCOPE='NEW BUILDING',
                 RES_UNITS>0, STATUS='COMPLETED -ALL INSP SIGNED OFF'. End
                 date: COMPLETE_DATE. History from 2018-01.
    Halifax      ArcGIS PPLC_Issued_Building_Permits. Work_Type='New
                 Building', Occupancy_Type='Residential Use', Net_New_Units>0,
                 Permit_Status='Completed'. End date: Completed_Date. History
                 from 2020-12.
    Toronto      CKAN cleared-permits resource. PERMIT_TYPE 'New Houses' /
                 'New Building', WORK starting 'New Building',
                 DWELLING_UNITS_CREATED>0, STATUS='Closed'. End date:
                 COMPLETED_DATE.

    The STATUS filter matters: Calgary, Halifax and Toronto all stamp a
    "completed"/closed date on cancelled, expired, withdrawn or dormant
    permits too (Halifax: 303 of 4,391 dated in-scope permits). Those are
    excluded and counted, never read as finished homes.

    Vancouver, Ottawa and Montreal publish no completion date at all, so
    they cannot appear here.

DWELLING TYPES -- mapped onto CMHC's four
    single / semi / row / apartment, from each city's own type label (the
    CITY_MAP functions below). CMHC counts duplexes and stacked townhouses
    as "apartment and other", so they go there too. Secondary suites,
    backyard/garden suites and anything non-residential are left out of
    every class and counted as `unmapped_type`. The homes in mixed-use
    buildings count as apartments, as CMHC counts every dwelling unit
    (Toronto: 226 mixed-use permits, 61,421 homes -- more than its
    apartment-building permits). Toronto's newer "2 Unit" / "3+ Unit"
    multiplexes count as apartments too. "all" = the four classes together;
    an "all" cell is shown only when every type holding 10%+ of that year's
    homes is publishable on its own, so a thin, heavily weighted type cannot
    swamp it.

THE NUMBERS
    Months = (end date - issue date) days / 30.4375. Per city, class and
    COMPLETION year:
      median  -- unit-weighted median months (the headline: permit records
                 have long administrative tails -- a permit can stay open
                 for years after people move in -- and the median is not
                 dragged by them);
      mean    -- unit-weighted mean months (CMHC's own statistic is a mean,
                 so this is the like-for-like reading);
      n, units -- permits and dwelling units behind the cell.
    Cells with fewer than MIN_N permits keep n but get null values (same
    20-unit floor as the CMHC chart).

CLEAN-UP YEARS (stale permit files)
    Some cities close old permit files in bulk. Toronto's cleared-permits
    data shows it plainly: of single-detached permits closed in 2025, 53%
    had been issued more than 5 years earlier (2017-2024: 7-25%), and 84-93%
    of apartment closures in 2024-2026. Those closures date the paperwork,
    not the build. So a cell whose share of closures more than STALE_YEARS
    (5) years after issue exceeds STALE_SHARE (one third) is a "clean-up
    year": its n and that share are kept, its values are null, and the page
    says why. In non-clean-up years the long files stay in -- the median is
    not moved much by them; the average is, and the page offers both.

THE FIRST YEAR SHOWN (left truncation)
    Grouping by completion year has its own trap at the START of a city's
    history: a home finished in 2019 in a dataset that begins in 2018 can
    only be a fast one. So each class's first year shown is
        first full year of issue records + ceil(95th-percentile build years)
    i.e. a year appears only once the records reach back far enough to
    contain 95% of that year's homes. The 95th percentile is taken over
    files closed within STALE_YEARS of issue, so stale files cannot push a
    city's whole series years later. The current year is partial and is
    flagged as such.

GATES, COUNTED (never silent)
    excluded_status   end date present but status says cancelled / expired /
                      withdrawn / dormant / closed-with-incomplete-inspection
    negative_days     end date before issue date (data-entry artifact)
    unmapped_type     residential new-build permit outside the four classes
    no_issue_date     cannot be placed in time
    before_first_year completion year earlier than the class's first year

SIZE (are homes getting bigger?)
    CMHC publishes no floor area at all (checked against all 17 of its Starts
    and Completions measures). Two size measures from the same permits:
      house_sqft  -- median floor area per single-detached home, sq ft, by
                     completion year: Calgary totalsqft, Edmonton floor_area,
                     Mississauga APPL_AREA (m2 -> sq ft), Toronto RESIDENTIAL
                     (m2 -> sq ft; the field's magnitudes -- ~265 m2 for a new
                     two-storey house -- read as gross floor area, which is
                     an inference, not a documented definition). Values
                     outside 400-15,000 sq ft are excluded and counted.
                     Halifax only has Building_Footprint_Area (footprint, not
                     floor area -- a two-storey house is double it) and
                     Winnipeg has no area field, so neither has this panel.
      apt_units   -- median dwelling units per apartment permit with 5+
                     homes (building size), by completion year, every city.
                     The 5+ floor matters: Toronto permits stacked townhouses
                     one unit at a time (2,372 permits, median 1 home), which
                     would otherwise read as one-home "buildings".
    Clean-up years hide the size values too (same files, same problem).
    Size and build time rising together does not show that size is the
    cause; the page says so.

LIMITATIONS
    City, not CMA: each city is only part of its CMA (Mississauga and Toronto
    are both inside the Toronto CMA). Permit close is an administrative
    event -- it can trail move-in by months, or by years for a dormant file
    -- whereas CMHC records physical completion. Permit issue usually comes
    shortly BEFORE CMHC's "start" (footings poured), so city durations run
    a little longer for that reason too.

USAGE
    python city_build_time_etl.py               # all six cities
    python city_build_time_etl.py --only calgary,toronto

    A city that fails keeps its previous block (from the existing file),
    marked with its own older `retrieved` date, and the script exits 1 so
    the workflow step shows the failure without blocking the rest of the
    refresh. The file is written atomically (temp file + replace).
"""

import argparse
import json
import math
import os
import sys
import tempfile
import time
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path

import requests

REPO_ROOT = Path(__file__).resolve().parents[1]
OUT_FILE = REPO_ROOT / "construction_json" / "city_build.json"
HEADERS = {"User-Agent": "OttawaVisuals-EnergySuite/1.0 (construction tracker)"}
MIN_N = 20
DAYS_PER_MONTH = 30.4375
SQM_TO_SQFT = 10.7639
SIZE_RANGE = (400, 15000)
APT_BLDG_MIN = 5         # building-size chart: permits with 5+ homes only
ALL_SHARE = 0.10         # "all" needs every type with >= 10% of the year's homes publishable
STALE_YEARS = 5          # a file closed this long after issue is paperwork, not a build
STALE_SHARE = 1 / 3      # a year where this share of closures is stale = clean-up year
CLASSES = ["single", "semi", "row", "apartment"]

CAL_API = "https://data.calgary.ca/resource/c2es-76ed.json"
EDM_API = "https://data.edmonton.ca/resource/24uj-dj8v.json"
WPG_API = "https://data.winnipeg.ca/resource/it4w-cpf4.json"
MIS_API = ("https://services6.arcgis.com/hM5ymMLbxIyWTjn2/arcgis/rest/"
           "services/Issued_Building_Permits/FeatureServer/0/query")
HFX_API = ("https://services2.arcgis.com/11XBiaBYA9Ep0yNJ/arcgis/rest/"
           "services/PPLC_Issued_Building_Permits/FeatureServer/0/query")
TOR_DS = ("https://ckan0.cf.opendata.inter.prod-toronto.ca/api/3/action/"
          "datastore_search")
TOR_CLEARED = "a96c0ba4-3026-402b-b09d-5b1268b8f810"


# =============================================================================
# HTTP + paging
# =============================================================================

def get(url, params, timeout=300, tries=4):
    for i in range(tries):
        try:
            r = requests.get(url, params=params, headers=HEADERS, timeout=timeout)
            r.raise_for_status()
            return r.json()
        except (requests.RequestException, ValueError) as e:
            if i == tries - 1:
                raise
            wait = 10 * (i + 1)
            print(f"    retry {i+1} after {type(e).__name__}; waiting {wait}s", flush=True)
            time.sleep(wait)


def socrata_rows(api, select, where, order, page=50000):
    out, offset = [], 0
    while True:
        rows = get(api, {"$select": select, "$where": where, "$order": order,
                         "$limit": page, "$offset": offset})
        out.extend(rows)
        offset += len(rows)
        print(f"    ...{offset:,}", flush=True)
        if len(rows) < page:
            return out


def socrata_count(api, where):
    return int(get(api, {"$select": "count(*) as n", "$where": where})[0]["n"])


def arcgis_rows(api, fields, where, page=2000):
    out, offset = [], 0
    while True:
        d = get(api, {"where": where, "outFields": ",".join(fields),
                      "orderByFields": "OBJECTID", "resultOffset": offset,
                      "resultRecordCount": page, "f": "json"})
        if "error" in d:
            raise RuntimeError(f"ArcGIS error: {d['error']}")
        feats = d.get("features", [])
        out.extend(f["attributes"] for f in feats)
        offset += len(feats)
        print(f"    ...{offset:,}", flush=True)
        if len(feats) < page:
            return out


def esri_date(ms):
    if ms is None:
        return None
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).date()


def iso_date(s):
    s = (s or "").strip()[:10]
    try:
        return date.fromisoformat(s)
    except ValueError:
        return None


def fnum(v):
    if v is None:
        return None
    try:
        return float(str(v).replace(",", "").strip())
    except ValueError:
        return None


# =============================================================================
# Dwelling-type maps (city label -> CMHC class, or None = left out, counted)
# =============================================================================

def map_calgary(pc):
    s = (pc or "").lower()
    if "duplex" in s:
        return "apartment"            # CMHC: duplexes are "apartment and other"
    if "single family" in s and "improvement" not in s or "pre-fab house" in s:
        return "single"
    if "semi" in s:
        return "semi"
    if "townhouse" in s or "rowhouse" in s:
        return "row"
    if "apt" in s:
        return "apartment"
    return None                       # suites, garden suites, garages, unspecified


def map_edmonton(bt):
    s = (bt or "").lower()
    if s.startswith("single detached"):
        return "single"
    if s.startswith("semi-detached"):
        return "semi"
    if s.startswith("row house"):
        return "row"
    if s.startswith("apartment") or s.startswith("duplex") or s.startswith("mixed use"):
        return "apartment"            # mixed-use: its homes are apartments to CMHC
    return None                       # backyard houses, non-residential


def map_winnipeg(st):
    s = (st or "").lower()
    if s.startswith("sfd"):
        return "single"
    if s.startswith("duplex / side by side"):
        return "semi"                 # ~1.2 units/permit: side-by-side halves
    if s.startswith("row housing"):
        return "row"
    if s in ("apartments", "residential multi-use"):
        return "apartment"
    return None


def map_mississauga(bt):
    s = (bt or "").upper()
    if s == "DETACHED DWELLING":
        return "single"
    if s == "SEMI-DETACHED DWELLING":
        return "semi"
    if "ROW DWELLING" in s:
        return "row"
    if s.startswith("APARTMENT") or s.startswith("DUPLEX"):
        return "apartment"
    return None


def map_halifax(ts):
    s = (ts or "")
    if s == "Dwelling - Single Detached":
        return "single"
    if s == "Dwelling - Semi-Detached":
        return "semi"
    if s == "Dwelling - Townhouse":
        return "row"
    if s in ("Dwelling - Multiple Units", "Mixed Use - Residential & Other Use(s)"):
        return "apartment"
    return None                       # backyard suites, seasonal


def map_toronto(st):
    s = (st or "").strip().lower()
    if s == "sfd - detached":
        return "single"
    if s == "sfd - semi-detached":
        return "semi"
    if s == "sfd - townhouse":
        return "row"
    if ("apartment" in s or "stacked" in s or "duplex" in s or "plex" in s
            or "multiple unit" in s or s.startswith("mixed use/res")
            or s.startswith("2 unit") or s.startswith("3+ unit")):
        return "apartment"            # CMHC: stacked townhouses, duplexes and
                                      # multiplexes are "apartment and other";
                                      # mixed-use towers' homes are apartments
    return None


# =============================================================================
# Per-city pulls -> list of records + gate counts
#   record: {cls, issue: date, done: date, units: int, sqft: float|None}
# =============================================================================

def new_gates():
    return {"excluded_status": 0, "negative_days": 0, "unmapped_type": 0,
            "no_issue_date": 0, "size_out_of_range": 0}


def finish(rec_list, gates, cls, issue, done, units, sqft=None):
    if cls is None:
        gates["unmapped_type"] += 1
        return
    if issue is None:
        gates["no_issue_date"] += 1
        return
    if done < issue:
        gates["negative_days"] += 1
        return
    rec_list.append({"cls": cls, "issue": issue, "done": done,
                     "units": max(int(units or 1), 1), "sqft": sqft})


def per_unit_sqft(area, units, factor=1.0):
    a = fnum(area)
    if a is None or a <= 0:
        return None
    return a * factor / max(int(units or 1), 1)


def pull_calgary():
    base = ("workclass='New' and permitclassmapped='Residential' and "
            "housingunits > 0 and completeddate is not null")
    excluded = socrata_count(CAL_API, base + " and statuscurrent != 'Completed'")
    open_ = socrata_count(CAL_API, "workclass='New' and permitclassmapped="
                          "'Residential' and housingunits > 0 and "
                          "completeddate is null")
    rows = socrata_rows(CAL_API, "permitnum,issueddate,completeddate,"
                        "housingunits,totalsqft,permitclass",
                        base + " and statuscurrent = 'Completed'", "permitnum")
    recs, g = [], new_gates()
    g["excluded_status"] = excluded
    for r in rows:
        u = int(fnum(r.get("housingunits")) or 1)
        cls = map_calgary(r.get("permitclass"))
        finish(recs, g, cls, iso_date(r.get("issueddate")),
               iso_date(r.get("completeddate")), u,
               per_unit_sqft(r.get("totalsqft"), u) if cls == "single" else None)
    return recs, g, open_, {
        "label": "City of Calgary", "cma": "calgary",
        "end_field": "completeddate (statuscurrent = 'Completed')",
        "area_field": "totalsqft (sq ft)",
        "licence": "Open Calgary Terms of Use",
        "source": "data.calgary.ca, Building Permits (c2es-76ed)",
        "coverage": "City of Calgary, about 88% of the Calgary CMA's population (2021 Census)."}


def pull_edmonton():
    new = "work_type in('(01) Building - New','(01) New') and units_added > 0"
    # No open count: Edmonton has no status field, and a permit without an
    # occupancy date may be open OR finalized before occupancy dates were
    # recorded (2022) -- 58,618 such permits on 2026-11-06, mostly the latter.
    open_ = None
    rows = socrata_rows(EDM_API, "row_id,permit_date,occupancy_granted_date,"
                        "units_added,floor_area,building_type",
                        new + " and occupancy_granted_date is not null", "row_id")
    recs, g = [], new_gates()
    for r in rows:
        u = int(fnum(r.get("units_added")) or 1)
        cls = map_edmonton(r.get("building_type"))
        done = iso_date(r.get("occupancy_granted_date"))
        if done is None:
            continue
        finish(recs, g, cls, iso_date(r.get("permit_date")), done, u,
               per_unit_sqft(r.get("floor_area"), u) if cls == "single" else None)
    return recs, g, open_, {
        "label": "City of Edmonton", "cma": "edmonton",
        "end_field": "occupancy_granted_date (occupancy, not permit close)",
        "area_field": "floor_area (sq ft)",
        "licence": "Open Government Licence - Edmonton",
        "source": "data.edmonton.ca, General Building Permits (24uj-dj8v)",
        "coverage": "City of Edmonton only, not the whole Edmonton CMA.",
        "open_note": ("No still-open count: Edmonton has no permit status "
                      "field, and permits without an occupancy date mix open "
                      "files with ones finalized before 2022."),
        "min_completion_year": 2022,
        "min_year_reason": ("Edmonton only records occupancy dates "
                            "systematically for residential permits finalized "
                            "on or after 2022-01-01 (per the dataset's own "
                            "documentation).")}


def pull_winnipeg():
    base = ("work_type='Construct New' and dwelling_units_created > 0 and "
            "final_date is not null")
    excluded = socrata_count(WPG_API, base + " and status != 'Closed'")
    open_ = socrata_count(WPG_API, "work_type='Construct New' and "
                          "dwelling_units_created > 0 and final_date is null")
    rows = socrata_rows(WPG_API, "permit_number,issue_date,final_date,"
                        "dwelling_units_created,sub_type",
                        base + " and status = 'Closed'", "permit_number")
    recs, g = [], new_gates()
    g["excluded_status"] = excluded
    for r in rows:
        u = int(fnum(r.get("dwelling_units_created")) or 1)
        finish(recs, g, map_winnipeg(r.get("sub_type")), iso_date(r.get("issue_date")),
               iso_date(r.get("final_date")), u)
    return recs, g, open_, {
        "label": "City of Winnipeg", "cma": "winnipeg",
        "end_field": "final_date (status = 'Closed')",
        "area_field": None,
        "area_reason": "Winnipeg's permit data has no floor-area field.",
        "licence": "Open Government Licence - Winnipeg",
        "source": "data.winnipeg.ca, Detailed Building Permit Data (it4w-cpf4)",
        "coverage": "City of Winnipeg proper, the large majority of the Winnipeg CMA."}


def pull_mississauga():
    fields = ["BLDG_TYPE", "SCOPE", "STATUS", "RES_UNITS", "APPL_AREA",
              "ISSUE_DATE", "COMPLETE_DATE"]
    rows = arcgis_rows(MIS_API, fields, "SCOPE='NEW BUILDING' AND RES_UNITS>0")
    recs, g, open_ = [], new_gates(), 0
    for r in rows:
        done = esri_date(r.get("COMPLETE_DATE"))
        if done is None:
            open_ += 1
            continue
        if (r.get("STATUS") or "").strip() != "COMPLETED -ALL INSP SIGNED OFF":
            g["excluded_status"] += 1
            continue
        u = int(r.get("RES_UNITS") or 1)
        cls = map_mississauga(r.get("BLDG_TYPE"))
        finish(recs, g, cls, esri_date(r.get("ISSUE_DATE")), done, u,
               per_unit_sqft(r.get("APPL_AREA"), u, SQM_TO_SQFT) if cls == "single" else None)
    return recs, g, open_, {
        "label": "City of Mississauga", "cma": "toronto",
        "end_field": "COMPLETE_DATE (STATUS = 'COMPLETED -ALL INSP SIGNED OFF')",
        "area_field": "APPL_AREA (m², converted to sq ft)",
        "licence": "City of Mississauga Terms of Use (open licence)",
        "source": "City of Mississauga open data, Issued Building Permits",
        "coverage": "City of Mississauga only, one part of the Toronto CMA."}


def pull_halifax():
    fields = ["Type_of_Structure", "Permit_Status", "Net_New_Units",
              "Date_of_Permit_Issuance", "Completed_Date"]
    rows = arcgis_rows(HFX_API, fields, "Work_Type='New Building' AND "
                       "Occupancy_Type='Residential Use' AND Net_New_Units>0")
    recs, g, open_ = [], new_gates(), 0
    for r in rows:
        done = esri_date(r.get("Completed_Date"))
        if done is None:
            open_ += 1
            continue
        if (r.get("Permit_Status") or "").strip() != "Completed":
            g["excluded_status"] += 1
            continue
        finish(recs, g, map_halifax(r.get("Type_of_Structure")),
               esri_date(r.get("Date_of_Permit_Issuance")), done,
               int(r.get("Net_New_Units") or 1))
    return recs, g, open_, {
        "label": "Halifax Regional Municipality", "cma": "halifax",
        "end_field": "Completed_Date (Permit_Status = 'Completed')",
        "area_field": None,
        "area_reason": ("Halifax records only Building_Footprint_Area, the "
                        "ground footprint rather than floor area (a two-storey "
                        "house has about twice its footprint), so it is not "
                        "used as a size measure."),
        "licence": "Halifax Open Data licence",
        "source": "Halifax open data, PPLC Issued Building Permits",
        "coverage": "Halifax Regional Municipality, nearly the whole Halifax CMA."}


def pull_toronto():
    fields = ["PERMIT_NUM", "PERMIT_TYPE", "STRUCTURE_TYPE", "WORK", "STATUS",
              "ISSUED_DATE", "COMPLETED_DATE", "DWELLING_UNITS_CREATED",
              "RESIDENTIAL"]
    rows, offset, total = [], 0, None
    filt = json.dumps({"PERMIT_TYPE": ["New Houses", "New Building"]})
    while True:
        d = get(TOR_DS, {"resource_id": TOR_CLEARED, "filters": filt,
                         "fields": ",".join(fields), "limit": 32000,
                         "offset": offset})["result"]
        total = d["total"] if total is None else total
        rows.extend(d["records"])
        offset += len(d["records"])
        print(f"    ...{offset:,}/{total:,}", flush=True)
        if not d["records"] or offset >= total:
            break
    recs, g, seen = [], new_gates(), set()
    for r in rows:
        pn = r.get("PERMIT_NUM")
        if pn in seen:
            continue                  # revisions share PERMIT_NUM
        seen.add(pn)
        if not (r.get("WORK") or "").startswith("New Building"):
            continue                  # scope, not a gate
        u = int(fnum(r.get("DWELLING_UNITS_CREATED")) or 0)
        if u <= 0:
            continue                  # scope: creates no dwelling
        done = iso_date(r.get("COMPLETED_DATE"))
        if done is None:
            continue
        if (r.get("STATUS") or "").strip() != "Closed":
            g["excluded_status"] += 1
            continue
        cls = map_toronto(r.get("STRUCTURE_TYPE"))
        finish(recs, g, cls, iso_date(r.get("ISSUED_DATE")), done, u,
               per_unit_sqft(r.get("RESIDENTIAL"), u, SQM_TO_SQFT) if cls == "single" else None)
    return recs, g, None, {
        "label": "City of Toronto", "cma": "toronto",
        "end_field": "COMPLETED_DATE (STATUS = 'Closed', cleared-permits resource)",
        "area_field": "RESIDENTIAL (m², converted to sq ft; read as residential gross floor area)",
        "licence": "Open Government Licence - Toronto",
        "source": "City of Toronto open data, Building Permits - Cleared Permits",
        "coverage": "City of Toronto only, one part of the Toronto CMA.",
        "open_note": ("Toronto publishes still-open permits in a separate "
                      "resource; they enter this series in the year they close.")}


# Order matters: a CMA's first city is the page's default (Toronto before
# Mississauga inside the Toronto CMA).
PULLS = {"calgary": pull_calgary, "edmonton": pull_edmonton,
         "winnipeg": pull_winnipeg, "toronto": pull_toronto,
         "mississauga": pull_mississauga, "halifax": pull_halifax}


# =============================================================================
# Aggregation
# =============================================================================

def wquantile(pairs, q):
    """Weighted quantile of [(value, weight)]: smallest value whose
    cumulative weight reaches q of the total."""
    pairs = sorted(pairs)
    tot = sum(w for _, w in pairs)
    if not tot:
        return None
    acc = 0
    for v, w in pairs:
        acc += w
        if acc >= q * tot:
            return v
    return pairs[-1][0]


def quantile(vals, q):
    return wquantile([(v, 1) for v in vals], q)


def summarise(key, recs, gates, open_count, meta):
    today = date.today()
    first_issue = min(r["issue"] for r in recs)
    floor_year = first_issue.year + (0 if first_issue.month == 1 and first_issue.day <= 15 else 1)
    min_year = meta.pop("min_completion_year", None)
    min_reason = meta.pop("min_year_reason", None)

    for r in recs:
        r["mo"] = (r["done"] - r["issue"]).days / DAYS_PER_MONTH

    classes, before_first = {}, 0
    for cls in CLASSES + ["all"]:
        sub = [r for r in recs if cls == "all" or r["cls"] == cls]
        if not sub:
            classes[cls] = {"first_year": None, "rows": []}
            continue
        if cls == "all":
            k = max(classes[c]["p95_years"] for c in CLASSES if classes[c].get("p95_years") is not None)
        else:
            live = [r["mo"] / 12 for r in sub if r["mo"] / 12 <= STALE_YEARS]
            k = math.ceil(quantile(live, 0.95)) if live else STALE_YEARS
        first_year = floor_year + k
        if min_year:
            first_year = max(first_year, min_year)
        by_year = defaultdict(list)
        for r in sub:
            if r["done"].year < first_year:
                if cls == "all":
                    before_first += 1
                continue
            by_year[r["done"].year].append(r)
        rows, cleanup = [], []
        for y in sorted(by_year):
            cell = by_year[y]
            n, units = len(cell), sum(r["units"] for r in cell)
            stale = sum(1 for r in cell if r["mo"] / 12 > STALE_YEARS) / n
            if stale > STALE_SHARE:
                cleanup.append(y)
            ok_mix = True
            if cls == "all":
                # A weighted "all" can be swamped by a type that is too thin to
                # publish on its own (Mississauga: 2 apartment permits carrying
                # hundreds of homes). Require every type holding >= ALL_SHARE
                # of the year's homes to be publishable itself.
                for c2 in CLASSES:
                    u2 = sum(r["units"] for r in cell if r["cls"] == c2)
                    if u2 / units >= ALL_SHARE:
                        r2 = next((x for x in classes[c2]["rows"] if x[0] == y), None)
                        if r2 is None or r2[3] is None:
                            ok_mix = False
            if n >= MIN_N and stale <= STALE_SHARE and ok_mix:
                med = wquantile([(r["mo"], r["units"]) for r in cell], 0.5)
                mean = sum(r["mo"] * r["units"] for r in cell) / units
                rows.append([y, n, units, round(med, 1), round(mean, 1), round(stale * 100)])
            else:
                rows.append([y, n, units, None, None, round(stale * 100)])
        classes[cls] = {"first_year": first_year, "p95_years": k,
                        "cleanup_years": cleanup, "rows": rows}
    gates["before_first_year"] = before_first

    # Size: single-detached floor area per home, apartment units per permit
    size = {}
    if meta.get("area_field"):
        by_year = defaultdict(list)
        y0 = classes["single"]["first_year"]
        for r in recs:
            if r["cls"] != "single" or r["sqft"] is None or r["done"].year < y0:
                continue
            if not SIZE_RANGE[0] <= r["sqft"] <= SIZE_RANGE[1]:
                gates["size_out_of_range"] += 1
                continue
            by_year[r["done"].year].append(r["sqft"])
        hide = set(classes["single"].get("cleanup_years", []))
        singles = sum(1 for r in recs if r["cls"] == "single" and r["done"].year >= y0)
        with_area = sum(len(v) for v in by_year.values())
        size["house_sqft"] = {
            "coverage_pct": round(with_area / singles * 100, 1) if singles else None,
            "rows": [[y, len(v), round(quantile(v, 0.5))
                      if len(v) >= MIN_N and y not in hide else None]
                     for y, v in sorted(by_year.items())]}
    else:
        size["house_sqft"] = None
    by_year = defaultdict(list)
    y0 = classes["apartment"]["first_year"]
    for r in recs:
        if (r["cls"] == "apartment" and y0 and r["done"].year >= y0
                and r["units"] >= APT_BLDG_MIN):
            by_year[r["done"].year].append(r["units"])
    hide = set(classes["apartment"].get("cleanup_years", []))
    size["apt_units"] = {"rows": [[y, len(v), quantile(v, 0.5)
                                   if len(v) >= MIN_N and y not in hide else None]
                                  for y, v in sorted(by_year.items())]}

    last_done = max(r["done"] for r in recs)
    meta.update({
        "retrieved": today.isoformat(),
        "issue_history_start": first_issue.isoformat(),
        "latest_completion": last_done.isoformat(),
        "partial_year": last_done.year if last_done.month < 12 else None,
        "min_year_reason": min_reason,
        "completed_in_scope": len(recs),
        "still_open": open_count,
        "gates": gates,
        "classes": classes,
        "size": size,
    })
    return meta


def validate(key, block):
    """Sanity rails: fail loudly rather than publish nonsense."""
    if not any(sum(1 for r in c["rows"] if r[3] is not None) >= 2
               for c in block["classes"].values()):
        raise ValueError(f"{key}: no dwelling type has 2 publishable years")
    for cls, c in block["classes"].items():
        for y, n, u, med, mean, stale in c["rows"]:
            if med is not None and not (0.5 <= med <= 120):
                raise ValueError(f"{key}/{cls}/{y}: median {med} months out of range")


# =============================================================================

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", help="comma-separated city keys")
    args = ap.parse_args()
    keys = args.only.split(",") if args.only else list(PULLS)

    old = {}
    if OUT_FILE.exists():
        old = json.loads(OUT_FILE.read_text(encoding="utf-8")).get("cities", {})

    cities, failed = dict(old), []
    for key in keys:
        print(f"[{key}]", flush=True)
        try:
            recs, gates, open_, meta = PULLS[key]()
            block = summarise(key, recs, gates, open_, meta)
            validate(key, block)
            cities[key] = block
            pub = {c: [r[0] for r in v["rows"] if r[3] is not None]
                   for c, v in block["classes"].items()}
            print(f"    {len(recs):,} completed homes' permits; publishable "
                  f"years {({c: f'{y[0]}-{y[-1]} ({len(y)})' for c, y in pub.items() if y})}; "
                  f"gates {gates}", flush=True)
        except Exception as e:                     # keep last good block
            failed.append(key)
            print(f"    FAILED: {type(e).__name__}: {e}", flush=True)

    out = {
        "retrieved": date.today().isoformat(),
        "min_n": MIN_N,
        "classes": CLASSES + ["all"],
        "cma_cities": {},
        "cities": {k: cities[k] for k in PULLS if k in cities},
    }
    for k, c in out["cities"].items():
        out["cma_cities"].setdefault(c["cma"], []).append(k)
    out["failed"] = failed

    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=OUT_FILE.parent, suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
    os.replace(tmp, OUT_FILE)
    print(f"wrote {OUT_FILE} ({OUT_FILE.stat().st_size/1024:.0f} KB); failed: {failed or 'none'}")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
