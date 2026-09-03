"""
permits_detail_etl.py

The DEEP per-city building-permit payload behind `permits.html`, written to
permits_json/. Nine municipal permit desks, at the granularity the summary
cards on construction.html deliberately don't carry.

RELATIONSHIP TO municipal_permits_etl.py
    That script is not replaced and is not modified by this one. It produces
    construction_json/municipal.json: one compact SUMMARY card per city,
    floored to 2017 so every city is on the same footing, cross-checkable
    against the StatCan CMA series on the same page. Panels it already ships
    correctly -- processing time, time to build, unit economics, quality and
    coverage notes -- are read straight from that file by permits.html rather
    than recomputed here, so there is exactly one producer for each of them.

    This script adds only what municipal.json deliberately does NOT hold,
    because none of it makes sense inside a summary card:

      1. FULL HISTORY. municipal.json floors every city at 2017-01 so the nine
         are comparable. That throws away real data: Montreal starts 1997,
         Calgary 1999-06, Edmonton 2009, Winnipeg 2010, Ottawa 2011. Here each
         city runs from its OWN first month and carries its own start date, so
         the page can label them individually instead of implying a shared one.
      2. CATEGORY x YEAR MATRICES. municipal.json ships one all-time top-12
         list per cut (areas, work type, use). That answers "where" but never
         "when" -- it cannot show a neighbourhood's building boom starting or
         ending. Here each cut is a full label x year matrix.
      3. A DENSITY GRID for the map (six cities; see MAP COVERAGE below).
      4. A WIDER NAME LIST. municipal.json ships top: 15, which is a table.
         A cloud needs more terms than that, so the same qualifying
         population is shipped 120 deep -- same 20+ permit threshold, same
         reasoning (see NAMES below).
      5. TORONTO's processing-time and build-time intervals, which
         municipal.json has no panel for at all -- see TORONTO below.

MAP COVERAGE -- three cities get no map, and that is not worked around
    Six of the nine publish per-permit coordinates: Vancouver
    (`geo_point_2d`), Calgary and Edmonton (`latitude`/`longitude`), Winnipeg
    (`location`), Montreal (`longitude`/`latitude`) and Mississauga
    (`LATITUDE`/`LONGITUDE`). Those six get a grid.

    Toronto, Ottawa and Halifax do not, and nothing here invents one:
      Toronto  no coordinate field of any kind. `POSTAL` is populated on
               90.8% of rows (checked live) so an FSA-level choropleth is
               technically possible against the FSA polygons this repo
               already ships, but that is a different map answering a
               different question at a 100x coarser grain, and mixing it in
               beside six real density grids would read as the same product.
               Not built; the card states the gap.
      Ottawa   annual XLSX workbooks; ward and community are the only
               geography in the files.
      Halifax  the source is a plain Esri TABLE with no geometry at all --
               `Community` is the only geography (see municipal_permits_etl's
               Halifax notes).
    Each city's payload carries an explicit `map` object saying available
    true/false and, when false, WHY -- so the page states the gap rather
    than silently rendering nothing.

THE GRID
    Permits are binned to a 0.004-degree cell -- about 445 m north-south and
    255-290 m east-west at these latitudes -- and counted per calendar year.
    Cells hold a count and, where the city has a cost field, a dollar total;
    they never hold an address, a permit number or a name. This is a
    deliberate choice, not a size optimisation: individual permit points
    would put private residential renovation addresses on a public map, which
    is the same concern the 20+ permit name threshold already exists to
    avoid.

    0.004 degrees was picked by measuring, not by taste. On Calgary (the
    largest at 498,889 geocoded rows over 28 years) the alternatives came out
    at 156,695 cell-year rows / 3.04 MB (0.002 deg), 81,454 / 1.61 MB
    (0.004 deg) and 29,890 / 0.59 MB (0.008 deg). 0.004 is the coarsest that
    still resolves individual city blocks at the zoom this map opens at.
    Grids are written to their own `<city>_grid.json` so the page loads one
    only when the map is actually opened.

NAMES / THE CONTRACTOR CLOUD
    Available for four cities only: Vancouver (applicants + contractors),
    Calgary (both), Ottawa (contractors) and Winnipeg (applicants). Edmonton
    excludes applicant identity deliberately as a stated privacy measure,
    Mississauga/Halifax/Montreal never collected the field, and Toronto's
    `BUILDER_NAME` exists but is populated on only 2.2% of rows (checked live
    on a 6,000-row sample) and is mostly individuals rather than firms, so it
    is reported as unusable rather than plotted thin.

    The 20+ permit threshold from municipal_permits_etl.py is kept unchanged
    and for the same reason: `applicant` is often the design professional or
    their firm, no private homeowner personally files dozens of permits, and
    a cloud makes a name MORE prominent than a table row does, not less. The
    list is deepened to 120 entries, not loosened.

TORONTO -- two panels it did not have
    Checked live on a 6,000-row sample of the cleared-permits resource:
    APPLICATION_DATE, ISSUED_DATE and COMPLETED_DATE are each 100% populated.
    So Toronto supports both a processing-time (application -> issue) and a
    build-time (issue -> completed) interval, neither of which exists in
    municipal.json. Both are computed here.

    The build-time figure is right-censored BY CONSTRUCTION and the page says
    so: "cleared" means closed, so a permit only appears in this population
    once it has completed. Recent years are therefore biased toward fast
    projects -- the slow ones are still open and not in this resource yet.
    The processing-time figure has no such problem; it is measured on permits
    that reached issuance, which all of these did.

THE DATE GATE, COUNTED
    Every series here is keyed on the permit's issue date, so a row without
    one cannot be placed on any chart. That gate is real and sizeable --
    18,340 Calgary permits (3.7%) carry no issue date -- so each city reports
    `source_rows` (what the portal holds) alongside `rows` (what carries a
    usable date), and the page states the difference on the city's card. The
    rule is the repo's: quantify the drop and name the gate, never let it
    pass silently.

CATEGORY MATRICES
    Each cut keeps the top 14 labels by all-time weight and rolls everything
    else into a single explicit "Other (N categories)" row, so a column still
    sums to the city's real total. Nothing is dropped silently.

OUTPUT
    permits_json/_index.json        city roster, capabilities, date ranges
    permits_json/<city>.json        the detail payload
    permits_json/<city>_grid.json   density grid (six cities only)

USAGE
    python permits_detail_etl.py [--refresh] [--only vancouver,calgary]
`--refresh` only affects Ottawa (forces re-download of every cached annual
workbook); every other city is queried live. Exits non-zero on any fetch
failure, so the scheduled refresh fails loudly rather than publishing a
half-built tree.
"""

import re
import sys
import json
import time
import argparse
from pathlib import Path
from datetime import datetime
from collections import defaultdict

import requests
import pandas as pd

# Low-level plumbing is imported, never re-implemented: one integration per
# portal, shared by both scripts.
from municipal_permits_etl import (
    get, num, page_datastore, edate,
    HEADERS, VAN_API, TOR_DS, TOR_PERMITS_CLEARED, TOR_PERMITS_ACTIVE,
    CAL_API, EDM_API, MIS_API, HFX_API, WPG_API,
    MTL_SQL_API, MTL_RID, MTL_WORK_LABELS,
    OTT_CONTRACTOR_PLACEHOLDERS,
    discover_ottawa_files, load_ottawa_year,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = REPO_ROOT / "permits_json"

# Two cities carry rows dated long before their data actually begins, and
# plotting them produces a chart that is not merely noisy but WRONG in
# direction. Both are floored explicitly, with the reason, rather than by a
# heuristic -- an explicit floor can be argued with; a magic threshold can't.
# `check_leading_ramp()` below screens every OTHER city on every run so a new
# instance of this surfaces loudly instead of shipping silently.
SERIES_FLOOR = {
    "toronto": ("2017-01",
                "Toronto's resource is titled \"Cleared Building Permits since "
                "2017\" and its coverage genuinely starts there. Rows dated "
                "earlier exist, but they are only the permits that were still "
                "OPEN when the dataset was cut -- a survivorship sample, not a "
                "record of what 1990 permitted. Plotted as history they rise "
                "smoothly from 94 permits in 1990 to 33,017 in 2016, which "
                "would read as a 350-fold increase in Toronto's building and "
                "is an artifact of which old permits stayed active."),
    "ottawa":  ("2011-01",
                "Ottawa's annual workbooks begin in 2011. A single permit "
                "dated 2003-07 appears in the files and is the only row "
                "before that."),
}

CELL_DEG = 0.004        # ~445 m N-S; see THE GRID in the module docstring
TOP_LABELS = 14         # per matrix, plus one explicit "Other" row
CLOUD_DEPTH = 120       # names shipped for the cloud (threshold unchanged)
NAME_THRESHOLD = 20     # permits, same as municipal_permits_etl.py


# =============================================================================
# transport
# =============================================================================

def rget(url, params=None, timeout=300, tries=5):
    """`get` with backoff. The Esri endpoints (Halifax, Mississauga) return
    intermittent 502/504s under the sustained paging these full-history pulls
    do -- observed live on Halifax at offset 6,000 -- and a whole city run is
    expensive to lose to one transient gateway error. Retries the transport,
    never a 4xx (that is a query bug, not a blip)."""
    for attempt in range(tries):
        try:
            r = requests.get(url, params=params, headers=HEADERS, timeout=timeout)
            # A 4xx is a bug in the query, not a blip. Retrying it four times
            # just delays the real error by half a minute and hides the
            # server's explanation, so it is raised immediately WITH the
            # response body -- CKAN in particular returns its SQL error there
            # under a 409, which is the only useful part of the failure.
            if 400 <= r.status_code < 500 and r.status_code != 429:
                raise requests.HTTPError(
                    f"{r.status_code} {r.reason} for {url} :: {r.text[:600]}")
            if r.status_code in (429, 500, 502, 503, 504) and attempt < tries - 1:
                raise requests.ConnectionError(f"{r.status_code} transient")
            r.raise_for_status()
            return r.json()
        except requests.HTTPError:
            raise
        except (requests.RequestException, ValueError) as e:
            if attempt == tries - 1:
                raise
            wait = 3 * (attempt + 1)
            print(f"      retry {attempt+1}/{tries-1} after {e.__class__.__name__} "
                  f"({wait}s)", flush=True)
            time.sleep(wait)


def page_esri(url, out_fields, page=2000):
    """page_arcgis with retries. Same contract, same OBJECTID ordering."""
    offset = 0
    while True:
        d = rget(url, {"where": "1=1", "outFields": ",".join(out_fields),
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


# =============================================================================
# shared shaping helpers
# =============================================================================

def apply_floor(monthly, floor_ym):
    """Trim every monthly series to start at `floor_ym`. Returns the number of
    months removed and the count of permits in them, so the caller can report
    exactly what was excluded -- these rows still exist in the all-time total
    and in the category matrices; only the TIME SERIES is floored."""
    removed = 0
    for key, ser in monthly.items():
        if not ser or not ser.get("values"):
            continue
        drop = (int(floor_ym[:4]) * 12 + int(floor_ym[5:7]) - 1) -                (int(ser["start"][:4]) * 12 + int(ser["start"][5:7]) - 1)
        if drop <= 0:
            continue
        drop = min(drop, len(ser["values"]))
        if key == "count":
            removed = sum(v or 0 for v in ser["values"][:drop])
        ser["values"] = ser["values"][drop:]
        ser["start"] = floor_ym
    return removed


def check_leading_ramp(key, monthly):
    """Warn when a city's first three full years average under a quarter of
    its median year. That shape is almost never real growth -- it is the
    signature of a dataset that only retained older records if they stayed
    open (see SERIES_FLOOR). Warns rather than acts: the fix is a documented
    floor, decided by a person, not an automatic trim."""
    ser = monthly.get("count")
    if not ser or not ser.get("values"):
        return
    y0, m0 = int(ser["start"][:4]), int(ser["start"][5:7])
    ann = defaultdict(int)
    for i, v in enumerate(ser["values"]):
        ann[(y0 * 12 + m0 - 1 + i) // 12] += v or 0
    yrs = sorted(ann)[:-1]                      # drop the partial current year
    if len(yrs) < 6:
        return
    vals = sorted(ann[y] for y in yrs)
    med = vals[len(vals) // 2]
    first3 = sum(ann[y] for y in yrs[:3]) / 3
    if med and first3 < 0.25 * med:
        print(f"  !! {key}: first 3 years average {first3:,.0f} against a median "
              f"year of {med:,.0f} ({first3/med*100:.1f}%). This looks like a "
              f"survivorship tail, not history -- consider a SERIES_FLOOR entry.",
              flush=True)


def month_end(start, n):
    """Last month of a series, given its start and length. Kept as its own
    function because the inline version got this off by one: month numbers
    here are 1-based, so the offset must be applied to (m0 - 1)."""
    tot = int(start[:4]) * 12 + (int(start[5:7]) - 1) + n - 1
    return f"{tot // 12:04d}-{tot % 12 + 1:02d}"


def trim_partial_month(monthly, cur_ym):
    """Drop the final month when it is the CURRENT calendar month.

    Every one of these portals updates continuously, so on any run day the
    newest month holds only the permits issued so far -- Vancouver's showed
    14 against a ~330 monthly norm. Plotted as-is it reads as a collapse in
    building rather than as a month that is three days old, and a 12-month
    average carries that dip for a year. The month is removed, not zeroed or
    extrapolated, and the caller records which month was dropped so the page
    can say the record ends at the last COMPLETE month."""
    dropped = None
    for key, s in list(monthly.items()):
        if not s or not s.get("values"):
            continue
        if month_end(s["start"], len(s["values"])) == cur_ym:
            s["values"].pop()
            dropped = cur_ym
            if not s["values"]:
                monthly[key] = None
    return dropped


def series_full(by_month):
    """{'YYYY-MM': v} -> {start, freq:'m', values[]} with null gaps.

    Same contract as municipal_permits_etl.months_to_series, minus its
    2017 floor -- that floor is the whole point of the summary file and the
    whole thing this file exists to lift."""
    ms = sorted(m for m in by_month if re.fullmatch(r"\d{4}-\d{2}", m or ""))
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


def matrix(cells, label, top=TOP_LABELS, caveat=None):
    """{(label, year): [n, value]} -> a dense label x year matrix.

    Keeps the `top` heaviest labels and rolls the rest into one explicit
    "Other (N categories)" row, so every year column still sums to the real
    city total. Weight is dollars where the city has a cost field and
    permits where it doesn't -- caller-independent, decided here by whether
    any value at all was recorded."""
    if not cells:
        return None
    years = sorted({y for _, y in cells})
    tot = defaultdict(lambda: [0, 0.0])
    for (lab, _y), (n, v) in cells.items():
        t = tot[lab]
        t[0] += n
        t[1] += v
    any_value = any(t[1] for t in tot.values())
    ranked = sorted(tot, key=lambda k: -(tot[k][1] if any_value else tot[k][0]))
    keep = ranked[:top]
    rest = ranked[top:]
    labels = list(keep)
    n_rows = [[cells.get((lab, y), (0, 0.0))[0] for y in years] for lab in keep]
    v_rows = [[round(cells.get((lab, y), (0, 0.0))[1] / 1e6, 2) for y in years]
              for lab in keep]
    if rest:
        labels.append(f"Other ({len(rest)} categories)")
        n_rows.append([sum(cells.get((lab, y), (0, 0.0))[0] for lab in rest)
                       for y in years])
        v_rows.append([round(sum(cells.get((lab, y), (0, 0.0))[1] for lab in rest) / 1e6, 2)
                       for y in years])
    out = {"label": label, "labels": labels, "years": years,
           "n": n_rows, "v": v_rows, "has_value": any_value,
           "distinct": len(tot)}
    if caveat:
        out["caveat"] = caveat
    return out


def grid_payload(points):
    """[(year, lat, lon, value)] -> {cell_deg, bounds, years, by_year}.

    by_year maps a year to [[latIdx, lonIdx, n, valueThousands], ...].
    Indices are integers against CELL_DEG so the page reconstructs the cell
    centre as idx * CELL_DEG -- shorter on the wire than repeating six
    decimal places on every row."""
    cells = defaultdict(lambda: defaultdict(lambda: [0, 0.0]))
    lat_lo = lon_lo = 1e9
    lat_hi = lon_hi = -1e9
    kept = 0
    for yr, la, lo, val in points:
        cell = cells[yr][(round(la / CELL_DEG), round(lo / CELL_DEG))]
        cell[0] += 1
        cell[1] += val or 0.0
        kept += 1
        lat_lo, lat_hi = min(lat_lo, la), max(lat_hi, la)
        lon_lo, lon_hi = min(lon_lo, lo), max(lon_hi, lo)
    if not kept:
        return None
    by_year = {y: sorted([[k[0], k[1], c[0], round(c[1] / 1000)]
                          for k, c in d.items()])
               for y, d in sorted(cells.items())}
    return {"cell_deg": CELL_DEG,
            "bounds": [round(lat_lo, 5), round(lon_lo, 5),
                       round(lat_hi, 5), round(lon_hi, 5)],
            "years": sorted(by_year),
            "permits": kept,
            "by_year": by_year}


def coord_ok(la, lo):
    """Reject the null-island and out-of-Canada rows every one of these
    portals carries a handful of. Counted by the caller, never silently
    dropped."""
    return (la is not None and lo is not None
            and 41.0 <= la <= 84.0 and -142.0 <= lo <= -52.0)


def cloud(rows, total_permits, coverage_pct, threshold=NAME_THRESHOLD):
    """[(name, n, value)] -> the concentration payload, deepened to
    CLOUD_DEPTH for the word cloud but on the SAME qualifying population
    municipal_permits_etl.py publishes. The threshold is not relaxed."""
    rows = [r for r in rows if r[0]]
    has_field = sum(r[1] for r in rows)
    qual = sorted([r for r in rows if r[1] >= threshold], key=lambda r: -r[1])
    covered = sum(r[1] for r in qual)
    return {
        "threshold": threshold,
        "field_coverage_pct": round(coverage_pct, 1),
        "total_distinct": len(rows),
        "qualifying": len(qual),
        "permits_covered": covered,
        "pct_of_field_permits": round(covered / has_field * 100, 1) if has_field else 0,
        "cloud": [[n, c, round(v / 1e6, 2)] for n, c, v in qual[:CLOUD_DEPTH]],
    }


def intervals(pairs, group_of):
    """[(days, group, year)] -> {by_type, by_year} medians, matching the
    shape municipal.json already uses so the page renders both with one
    function. Negative intervals are EXCLUDED and counted, never zeroed."""
    by_type, by_year = defaultdict(list), defaultdict(list)
    negative = 0
    for days, grp, yr in pairs:
        if days is None:
            continue
        if days < 0:
            negative += 1
            continue
        if grp:
            by_type[grp].append(days)
        by_year[yr].append(days)

    def med(v):
        v = sorted(v)
        n = len(v)
        return (v[n // 2] if n % 2 else (v[n // 2 - 1] + v[n // 2]) / 2)
    t = sorted(([k, len(v), round(med(v), 1)] for k, v in by_type.items()),
               key=lambda r: -r[1])[:14]
    y = sorted([str(k), len(v), round(med(v), 1)] for k, v in by_year.items())
    return {"by_type": t, "by_year": y, "negative_excluded": negative}


def ym(d):
    return d[:7] if d else None


def yr_of(d):
    return int(d[:4]) if d else None


# =============================================================================
# Vancouver -- one bulk export covers every cut, including the grid
# =============================================================================

def detail_vancouver():
    """Opendatasoft's /exports/json returns the whole dataset in one request
    (51,878 rows, ~6 MB with the three map fields), so every cut here comes
    from a single pull rather than a dozen server-side aggregations. The
    dataset genuinely starts 2017 -- unlike Calgary or Montreal, there is no
    earlier history being unlocked here."""
    fields = ("issuedate,projectvalue,geo_point_2d,typeofwork,propertyuse,"
              "geolocalarea,applicant,buildingcontractor")
    rows = rget(f"{VAN_API.rsplit('/', 1)[0]}/exports/json",
                {"select": fields, "limit": -1}, timeout=600)
    print(f"    ...{len(rows):,} rows")

    by_m_n, by_m_v = defaultdict(int), defaultdict(float)
    work, use, area = defaultdict(lambda: [0, 0.0]), defaultdict(lambda: [0, 0.0]), defaultdict(lambda: [0, 0.0])
    appl, contr = defaultdict(lambda: [0, 0.0]), defaultdict(lambda: [0, 0.0])
    pts, no_coord, n_appl, n_contr = [], 0, 0, 0
    for r in rows:
        d = r.get("issuedate")
        if not d:
            continue
        v = float(r.get("projectvalue") or 0)
        by_m_n[ym(d)] += 1
        by_m_v[ym(d)] += v / 1e6
        y = yr_of(d)
        # `propertyuse` is MULTI-VALUED on this portal -- the export returns a
        # list, and a mixed-use permit legitimately carries several ("Dwelling
        # Uses", "Parking Uses", "Retail Uses" on one tower). Stringifying the
        # list produced 153 combination pseudo-categories instead of the ~8
        # real ones. Counting a permit once per use would instead break every
        # column total. So the FIRST listed use is taken as the primary one --
        # one permit, one category, column sums exactly equal the permit count
        # -- and the page states that secondary uses are not counted.
        pu = r.get("propertyuse")
        if isinstance(pu, list):
            pu = pu[0] if pu else None
        for bag, key in ((work, r.get("typeofwork")), (use, pu),
                         (area, r.get("geolocalarea"))):
            if key:
                c = bag[(str(key).strip(), y)]
                c[0] += 1
                c[1] += v
        for bag, key, cnt in ((appl, r.get("applicant"), "a"),
                              (contr, r.get("buildingcontractor"), "c")):
            if key and str(key).strip():
                c = bag[str(key).strip()]
                c[0] += 1
                c[1] += v
                if cnt == "a":
                    n_appl += 1
                else:
                    n_contr += 1
        g = r.get("geo_point_2d") or {}
        la, lo = g.get("lat"), g.get("lon")
        if coord_ok(la, lo):
            pts.append((y, la, lo, v))
        else:
            no_coord += 1

    total = sum(by_m_n.values())
    return {
        "source_rows": len(rows),
        "monthly": {"count": series_full(by_m_n),
                    "value": series_full({k: round(v, 3) for k, v in by_m_v.items()})},
        "matrices": {"work": matrix(work, "type of work"),
                     "use": matrix(use, "property use", caveat=(
                         "Vancouver records SEVERAL uses on a mixed-use permit "
                         "(a tower can be dwelling, parking and retail at once). "
                         "Only the first-listed use is counted here, so each "
                         "permit lands in exactly one category and the column "
                         "totals equal the real permit count -- but secondary "
                         "uses on mixed-use projects are not represented.")),
                     "area": matrix(area, "local area")},
        "names": {
            "applicants": cloud([[k, v[0], v[1]] for k, v in appl.items()],
                                total, n_appl / total * 100),
            "contractors": cloud([[k, v[0], v[1]] for k, v in contr.items()],
                                 total, n_contr / total * 100),
        },
        "rows": total,
        "map": {"available": True, "geocoded": len(pts),
                "ungeocoded": no_coord},
    }, grid_payload(pts)


# =============================================================================
# Socrata cities -- aggregate server-side, page raw ONLY for the grid
# =============================================================================

def _socrata_agg(api, select, group=None, order=None, where=None, limit=50000):
    p = {"$select": select, "$limit": limit}
    if group:
        p["$group"] = group
    if order:
        p["$order"] = order
    if where:
        p["$where"] = where
    return rget(api, p)


def _socrata_grid_paged(api, date_f, lat_f, lon_f, val_f, total, page=50000):
    """Page raw coordinates for the density grid, 50k rows at a time.

    Socrata has no round() function -- checked live, it 400s with
    "No such function 'round'" -- so binning cannot be pushed server-side
    the way Montreal's SQL endpoint allows. The coordinates come down and
    are binned here. Paging is ordered by :id (Socrata's stable row handle)
    rather than by date, which is not unique and would repeat or skip rows
    across page boundaries."""
    sel = f"{date_f},{lat_f},{lon_f}" + (f",{val_f}" if val_f else "")
    pts, bad, off = [], 0, 0
    while True:
        b = rget(api, {"$select": sel, "$where": f"{lat_f} IS NOT NULL",
                       "$order": ":id", "$limit": page, "$offset": off})
        if not b:
            break
        for r in b:
            d = r.get(date_f)
            try:
                la, lo = float(r[lat_f]), float(r[lon_f])
            except (KeyError, TypeError, ValueError):
                bad += 1
                continue
            if not d or not coord_ok(la, lo):
                bad += 1
                continue
            pts.append((yr_of(d), la, lo, float(r.get(val_f) or 0) if val_f else 0.0))
        off += len(b)
        print(f"    ...grid {off:,}", flush=True)
        if len(b) < page:
            break
    return pts, bad


def _socrata_matrix(api, field, date_f, val_f, label, limit=50000):
    sel = f"{field},date_trunc_y({date_f}) as yr,count(*) as n"
    if val_f:
        sel += f",sum({val_f}) as val"
    rows = _socrata_agg(api, sel, group=f"{field},yr", order="yr", limit=limit)
    cells = {}
    for r in rows:
        k, y = r.get(field), r.get("yr")
        if not k or not y:
            continue
        cells[(str(k).strip(), int(y[:4]))] = [int(r["n"]),
                                               float(r.get("val") or 0)]
    return matrix(cells, label)


def _socrata_names(api, field, date_f, val_f, total):
    sel = f"{field},count(*) as n" + (f",sum({val_f}) as val" if val_f else "")
    rows = _socrata_agg(api, sel, group=field, limit=50000)
    out = [[str(r[field]).strip(), int(r["n"]), float(r.get("val") or 0)]
           for r in rows if r.get(field) and str(r[field]).strip()]
    covered = sum(r[1] for r in out)
    return cloud(out, total, covered / total * 100 if total else 0)


def detail_calgary():
    """Calgary's dataset runs to 1999-06 -- 18 years of history that
    municipal.json's 2017 floor discards. Every query here is unfloored on
    purpose; the page labels Calgary's own start rather than a shared one."""
    api = CAL_API
    monthly = _socrata_agg(api, "date_trunc_ym(issueddate) as ym,count(*) as n,"
                                "sum(estprojectcost) as val,sum(housingunits) as u",
                           group="ym", order="ym", limit=1000)
    n = {r["ym"][:7]: int(r["n"]) for r in monthly if r.get("ym")}
    v = {r["ym"][:7]: round(float(r.get("val") or 0) / 1e6, 3) for r in monthly if r.get("ym")}
    u = {r["ym"][:7]: int(float(r.get("u") or 0)) for r in monthly if r.get("ym")}
    total = sum(n.values())
    src = int(_socrata_agg(api, "count(*) as n", limit=1)[0]["n"])
    pts, bad = _socrata_grid_paged(api, "issueddate", "latitude", "longitude",
                                   "estprojectcost", total)
    return {
        "source_rows": src,
        "monthly": {"count": series_full(n), "value": series_full(v),
                    "units_created": series_full(u)},
        "matrices": {
            "work": _socrata_matrix(api, "workclass", "issueddate",
                                    "estprojectcost", "work class"),
            "use": _socrata_matrix(api, "permitclassmapped", "issueddate",
                                   "estprojectcost", "permit class"),
            "area": _socrata_matrix(api, "communityname", "issueddate",
                                    "estprojectcost", "community"),
        },
        "names": {
            "applicants": _socrata_names(api, "applicantname", "issueddate",
                                         "estprojectcost", total),
            "contractors": _socrata_names(api, "contractorname", "issueddate",
                                          "estprojectcost", total),
        },
        "rows": total,
        "map": {"available": True, "geocoded": len(pts), "ungeocoded": total - len(pts)},
    }, grid_payload(pts)


def detail_edmonton():
    """Back to 2009-01. No name panel: the city excludes applicant identity
    from this dataset as a stated privacy measure (see municipal_permits_etl),
    which is a deliberate publisher choice, not a gap to route around."""
    api = EDM_API
    monthly = _socrata_agg(api, "date_trunc_ym(issue_date) as ym,count(*) as n,"
                                "sum(construction_value) as val,sum(units_added) as u",
                           group="ym", order="ym", limit=1000)
    n = {r["ym"][:7]: int(r["n"]) for r in monthly if r.get("ym")}
    v = {r["ym"][:7]: round(float(r.get("val") or 0) / 1e6, 3) for r in monthly if r.get("ym")}
    u = {r["ym"][:7]: int(float(r.get("u") or 0)) for r in monthly if r.get("ym")}
    total = sum(n.values())
    src = int(_socrata_agg(api, "count(*) as n", limit=1)[0]["n"])
    pts, bad = _socrata_grid_paged(api, "issue_date", "latitude", "longitude",
                                   "construction_value", total)
    return {
        "source_rows": src,
        "monthly": {"count": series_full(n), "value": series_full(v),
                    "units_created": series_full(u)},
        "matrices": {
            "work": _socrata_matrix(api, "work_type", "issue_date",
                                    "construction_value", "work type"),
            "use": _socrata_matrix(api, "building_type", "issue_date",
                                   "construction_value", "building type"),
            "area": _socrata_matrix(api, "neighbourhood", "issue_date",
                                    "construction_value", "neighbourhood"),
        },
        "names": None,
        "names_gap": ("The City of Edmonton deliberately excludes applicant "
                      "and contractor names from this dataset as a stated "
                      "privacy measure. That is a publisher's choice, not a "
                      "missing field."),
        "rows": total,
        "map": {"available": True, "geocoded": len(pts), "ungeocoded": total - len(pts)},
    }, grid_payload(pts)


def detail_winnipeg():
    """Back to 2010-01. No cost field anywhere in this dataset (the dataset's
    own description says so), so every weighting here is by permit COUNT --
    the grid carries no dollar total for Winnipeg either."""
    api = WPG_API
    monthly = _socrata_agg(api, "date_trunc_ym(issue_date) as ym,count(*) as n,"
                                "sum(dwelling_units_created) as u,"
                                "sum(dwelling_units_lost) as l",
                           group="ym", order="ym", limit=1000)
    n = {r["ym"][:7]: int(r["n"]) for r in monthly if r.get("ym")}
    u = {r["ym"][:7]: int(float(r.get("u") or 0)) for r in monthly if r.get("ym")}
    l = {r["ym"][:7]: int(float(r.get("l") or 0)) for r in monthly if r.get("ym")}
    total = sum(n.values())
    src = int(_socrata_agg(api, "count(*) as n", limit=1)[0]["n"])

    # `location` is a Socrata point column: one field carrying lat/long as
    # strings. There is also x/y_coordinate_nad83, but those are projected
    # metres needing a reprojection dependency this repo does not carry.
    pts, off, bad = [], 0, 0
    while True:
        b = rget(api, {"$select": "issue_date,location",
                       "$where": "location IS NOT NULL", "$order": ":id",
                       "$limit": 50000, "$offset": off})
        if not b:
            break
        for r in b:
            g = r.get("location") or {}
            try:
                la, lo = float(g.get("latitude")), float(g.get("longitude"))
            except (TypeError, ValueError):
                bad += 1
                continue
            d = r.get("issue_date")
            if not d or not coord_ok(la, lo):
                bad += 1
                continue
            pts.append((yr_of(d), la, lo, 0.0))
        off += len(b)
        print(f"    ...grid {off:,}", flush=True)
        if len(b) < 50000:
            break
    return {
        "source_rows": src,
        "monthly": {"count": series_full(n), "units_created": series_full(u),
                    "units_lost": series_full(l)},
        "matrices": {
            "work": _socrata_matrix(api, "permit_type", "issue_date", None,
                                    "permit type"),
            "use": _socrata_matrix(api, "type_of_structure", "issue_date", None,
                                   "structure type"),
            "area": _socrata_matrix(api, "neighbourhood_name", "issue_date", None,
                                    "neighbourhood"),
        },
        "names": {
            "applicants": _socrata_names(api, "applicant_business_name",
                                         "issue_date", None, total),
            "contractors": None,
        },
        "value_basis": "count",
        "rows": total,
        "map": {"available": True, "geocoded": len(pts), "ungeocoded": total - len(pts)},
    }, grid_payload(pts)


# =============================================================================
# Montreal -- the only city where the grid is built server-side
# =============================================================================

def mtl_sql(sql):
    return rget(MTL_SQL_API, {"sql": sql}, timeout=600)["result"]["records"]


def detail_montreal():
    """558,874 rows back to 1997 -- far too many to page raw, but this CKAN
    endpoint allows PostgreSQL's round()/::numeric, so the 0.004-degree
    binning is pushed all the way to the server. The endpoint blocks CAST()
    outright; `::numeric` is the shorthand that works (checked live).

    No cost field exists anywhere in this resource, so everything here is
    weighted by permit count."""
    q = f'FROM "{MTL_RID}"'
    # nb_logements is a TEXT column (checked live: sum(text) 409s), and it
    # carries blanks and non-numeric junk, so units are summed in a SEPARATE
    # query behind the same `~ '^[0-9]+$'` guard municipal_permits_etl.py
    # uses. Folding the guard into the count query instead would silently
    # drop every permit with a blank unit count from the permit COUNT too.
    monthly = mtl_sql(f'SELECT substr(date_emission,1,7) as ym, count(*) as n {q} '
                      f"WHERE date_emission IS NOT NULL GROUP BY ym")
    n = {r["ym"]: int(r["n"]) for r in monthly if r.get("ym")}
    units = mtl_sql(f'SELECT substr(date_emission,1,7) as ym, '
                    f'sum(nb_logements::integer) as u {q} '
                    f"WHERE date_emission IS NOT NULL "
                    f"AND nb_logements ~ '^[0-9]+$' GROUP BY ym")
    u = {r["ym"]: int(float(r.get("u") or 0)) for r in units if r.get("ym")}
    total = sum(n.values())
    src = int(mtl_sql(f'SELECT count(*) as n {q}')[0]["n"])

    def mat(field, label):
        rows = mtl_sql(f'SELECT {field} as k, substr(date_emission,1,4) as yr, '
                       f'count(*) as n {q} WHERE date_emission IS NOT NULL '
                       f'AND {field} IS NOT NULL GROUP BY k,yr')
        cells = {}
        for r in rows:
            k = str(r["k"]).strip()
            if not k or not r.get("yr"):
                continue
            if field == "code_type_base_demande":
                k = MTL_WORK_LABELS.get(k, k)
            # description_type_batiment carries real casing duplicates across
            # boroughs ("Commercial"/"commercial"/"Commerce"); uppercased for
            # grouping rather than picking one casing arbitrarily.
            if field == "description_type_batiment":
                k = k.upper()
            key = (k, int(r["yr"]))
            cur = cells.get(key) or [0, 0.0]
            cur[0] += int(r["n"])
            cells[key] = cur
        return matrix(cells, label)

    # CKAN caps datastore_search_sql at 32,000 rows and SAYS NOTHING when it
    # truncates -- an unpaged version of this query returned 32,000 grouped
    # rows covering 60,394 of the 540,855 geocoded permits, an 89% silent
    # loss that looks like a complete map. Paged with a deterministic ORDER
    # BY and reconciled against the source count below.
    geo_total = int(mtl_sql(f'SELECT count(*) as n {q} WHERE latitude IS NOT NULL '
                            f'AND date_emission IS NOT NULL')[0]["n"])
    g, off, PAGE = [], 0, 30000
    while True:
        batch = mtl_sql(f'SELECT round(latitude::numeric,3) as la, '
                        f'round(longitude::numeric,3) as lo, '
                        f'substr(date_emission,1,4) as yr, count(*) as n {q} '
                        f'WHERE latitude IS NOT NULL AND date_emission IS NOT NULL '
                        f'GROUP BY la,lo,yr ORDER BY la,lo,yr '
                        f'LIMIT {PAGE} OFFSET {off}')
        g += batch
        off += len(batch)
        print(f"    ...grid {off:,} cells", flush=True)
        if len(batch) < PAGE:
            break
    got = sum(int(r["n"]) for r in g)
    if got != geo_total:
        raise RuntimeError(f"Montreal grid reconciliation failed: grouped rows "
                           f"cover {got:,} permits but {geo_total:,} have "
                           f"coordinates -- the endpoint truncated again")
    # Server-side rounding is to 3 decimals (the SQL endpoint's round() takes
    # a digit count, not an arbitrary step), so the grid is rebuilt from those
    # pre-binned centroids into the same CELL_DEG lattice every other city
    # uses -- one shared cell size across the whole map, not one per city.
    pts, bad = [], 0
    for r in g:
        try:
            la, lo, cnt = float(r["la"]), float(r["lo"]), int(r["n"])
        except (TypeError, ValueError):
            bad += 1
            continue
        if not coord_ok(la, lo) or not r.get("yr"):
            bad += 1
            continue
        pts.append((int(r["yr"]), la, lo, float(cnt)))
    grid = grid_payload([(y, la, lo, 0.0) for y, la, lo, _ in pts])
    # The server pre-aggregated, so each returned row is many permits. Re-add
    # the real counts rather than counting centroids as one permit each.
    if grid:
        recount = defaultdict(lambda: defaultdict(int))
        for y, la, lo, cnt in pts:
            recount[y][(round(la / CELL_DEG), round(lo / CELL_DEG))] += int(cnt)
        grid["by_year"] = {y: sorted([[k[0], k[1], c, 0]
                                      for k, c in d.items()])
                           for y, d in sorted(recount.items())}
        grid["permits"] = sum(sum(d.values()) for d in recount.values())

    return {
        "source_rows": src,
        "monthly": {"count": series_full(n), "units_created": series_full(u)},
        "matrices": {
            "work": mat("code_type_base_demande", "type of application"),
            "use": mat("description_type_batiment", "building type"),
            "area": mat("arrondissement", "borough"),
        },
        "names": None,
        "names_gap": ("This resource has no applicant or contractor field at "
                      "all."),
        "value_basis": "count",
        "rows": total,
        "map": {"available": True,
                "geocoded": grid["permits"] if grid else 0,
                "ungeocoded": total - (grid["permits"] if grid else 0),
                "note": ("Montreal's grid is aggregated on the server and "
                         "re-binned to the same cell size as every other "
                         "city, so cells are comparable across the map.")},
    }, grid


# =============================================================================
# Esri cities -- Mississauga (has coordinates) and Halifax (has none)
# =============================================================================

def detail_mississauga():
    fields = ["ISSUE_DATE", "EST_CON_VALUE", "RES_UNITS", "WARD", "BLDG_TYPE",
              "SCOPE", "FILE_TYPE", "LATITUDE", "LONGITUDE"]
    by_m_n, by_m_v, by_m_u = defaultdict(int), defaultdict(float), defaultdict(int)
    work, use, area = {}, {}, {}
    pts, total, bad, src = [], 0, 0, 0

    def bump(bag, k, y, v):
        if not k:
            return
        cur = bag.get((str(k).strip(), y)) or [0, 0.0]
        cur[0] += 1
        cur[1] += v
        bag[(str(k).strip(), y)] = cur

    for a in page_esri(MIS_API, fields):
        src += 1
        d = edate(a.get("ISSUE_DATE"))
        if not d:
            continue
        total += 1
        v = float(a.get("EST_CON_VALUE") or 0)
        y = yr_of(d)
        by_m_n[ym(d)] += 1
        by_m_v[ym(d)] += v / 1e6
        by_m_u[ym(d)] += int(a.get("RES_UNITS") or 0)
        bump(work, a.get("SCOPE"), y, v)
        bump(use, a.get("BLDG_TYPE"), y, v)
        bump(area, a.get("WARD"), y, v)
        try:
            la, lo = float(a.get("LATITUDE")), float(a.get("LONGITUDE"))
        except (TypeError, ValueError):
            bad += 1
            continue
        if coord_ok(la, lo):
            pts.append((y, la, lo, v))
        else:
            bad += 1
    return {
        "source_rows": src,
        "monthly": {"count": series_full(by_m_n),
                    "value": series_full({k: round(x, 3) for k, x in by_m_v.items()}),
                    "units_created": series_full(by_m_u)},
        "matrices": {"work": matrix(work, "scope of work"),
                     "use": matrix(use, "building type"),
                     "area": matrix(area, "ward")},
        "names": None,
        "names_gap": ("This schema has never carried an applicant or "
                      "contractor field."),
        "rows": total,
        "map": {"available": True, "geocoded": len(pts), "ungeocoded": bad},
    }, grid_payload(pts)


def detail_halifax():
    """No geometry anywhere in this resource -- it is a plain Esri TABLE, so
    Community is the only geography and there is no map."""
    fields = ["Issue_Date", "Estimated_Project_Value", "Net_New_Units",
              "Community", "Work_Type", "Type_of_Structure", "Permit_Name"]
    # Field names differ from municipal_permits_etl's HFX_FIELDS only where
    # that script needed extra columns; the date column name is confirmed
    # from the layer metadata at runtime below.
    meta = rget(HFX_API.rsplit("/query", 1)[0], {"f": "json"})
    have = {f["name"] for f in meta.get("fields", [])}
    date_f = next((c for c in ("Date_of_Permit_Issuance", "Issue_Date",
                               "Issued_Date", "Date_Issued") if c in have), None)
    if not date_f:
        raise RuntimeError(f"Halifax: no issuance date field found in {sorted(have)}")
    fields = [f for f in ([date_f] + fields[1:]) if f in have]

    by_m_n, by_m_v, by_m_u = defaultdict(int), defaultdict(float), defaultdict(int)
    work, use, area = {}, {}, {}
    total, src = 0, 0

    def bump(bag, k, y, v):
        if not k:
            return
        cur = bag.get((str(k).strip(), y)) or [0, 0.0]
        cur[0] += 1
        cur[1] += v
        bag[(str(k).strip(), y)] = cur

    for a in page_esri(HFX_API, fields):
        src += 1
        d = edate(a.get(date_f))
        if not d:
            continue
        total += 1
        v = float(a.get("Estimated_Project_Value") or 0)
        y = yr_of(d)
        by_m_n[ym(d)] += 1
        by_m_v[ym(d)] += v / 1e6
        by_m_u[ym(d)] += int(a.get("Net_New_Units") or 0)
        bump(work, a.get("Work_Type"), y, v)
        bump(use, a.get("Type_of_Structure"), y, v)
        bump(area, a.get("Community"), y, v)
    return {
        "source_rows": src,
        "monthly": {"count": series_full(by_m_n),
                    "value": series_full({k: round(x, 3) for k, x in by_m_v.items()}),
                    "units_created": series_full(by_m_u)},
        "matrices": {"work": matrix(work, "work type"),
                     "use": matrix(use, "structure type"),
                     "area": matrix(area, "community")},
        "names": None,
        "names_gap": "This schema has no applicant or contractor field.",
        "rows": total,
        "map": {"available": False,
                "reason": ("Halifax publishes these permits as a plain table "
                           "with no geometry at all -- no coordinates exist "
                           "in the source, so there is nothing to map. "
                           "Community is the only geography, shown in the "
                           "area breakdown instead.")},
    }, None


# =============================================================================
# Toronto -- no coordinates, but three complete dates
# =============================================================================

def detail_toronto():
    """Both permit resources are needed: "cleared" means CLOSED, so on its
    own it is badly right-censored at the recent end (see
    municipal_permits_etl). Active + cleared = every permit issued.

    Two intervals are computed here that municipal.json has no panel for.
    APPLICATION_DATE / ISSUED_DATE / COMPLETED_DATE are each 100% populated
    on the cleared resource (checked live on a 6,000-row sample), so both a
    processing time and a build time are measurable -- but ONLY on cleared
    permits, which is a population defined by having completed. The build
    time is therefore right-censored by construction and the page says so
    rather than reading it as a trend."""
    fields = ["PERMIT_NUM", "APPLICATION_DATE", "ISSUED_DATE", "COMPLETED_DATE",
              "WORK", "STRUCTURE_TYPE", "PERMIT_TYPE", "POSTAL",
              "EST_CONST_COST", "DWELLING_UNITS_CREATED", "DWELLING_UNITS_LOST",
              "BUILDER_NAME"]
    by_m_n, by_m_v, by_m_u, by_m_l = (defaultdict(int), defaultdict(float),
                                      defaultdict(int), defaultdict(int))
    work, use, area = {}, {}, {}
    proc, build = [], []
    seen, bad_cost, total, builder_rows, src = set(), 0, 0, 0, 0

    def bump(bag, k, y, v):
        if not k:
            return
        cur = bag.get((str(k).strip(), y)) or [0, 0.0]
        cur[0] += 1
        cur[1] += v
        bag[(str(k).strip(), y)] = cur

    def dpart(s):
        s = (s or "").strip()
        m = re.match(r"(\d{4})-(\d{2})-(\d{2})", s)
        return m.group(0) if m else None

    def days(a, b):
        if not a or not b:
            return None
        return (datetime.fromisoformat(b) - datetime.fromisoformat(a)).days

    for rid, cleared in ((TOR_PERMITS_CLEARED, True), (TOR_PERMITS_ACTIVE, False)):
        for r in page_datastore(rid, [f for f in fields]):
            pn = r.get("PERMIT_NUM")
            if pn and pn in seen:
                continue
            if pn:
                seen.add(pn)
            src += 1
            iss = dpart(r.get("ISSUED_DATE"))
            if not iss:
                continue
            total += 1
            c = num(r.get("EST_CONST_COST"))
            if c is None and (r.get("EST_CONST_COST") or "").strip():
                bad_cost += 1
            v = c or 0.0
            y = yr_of(iss)
            by_m_n[ym(iss)] += 1
            by_m_v[ym(iss)] += v / 1e6
            by_m_u[ym(iss)] += int(num(r.get("DWELLING_UNITS_CREATED")) or 0)
            by_m_l[ym(iss)] += int(num(r.get("DWELLING_UNITS_LOST")) or 0)
            bump(work, r.get("WORK"), y, v)
            bump(use, r.get("STRUCTURE_TYPE"), y, v)
            fsa = (r.get("POSTAL") or "").strip().upper()[:3]
            if len(fsa) == 3:
                bump(area, fsa, y, v)
            if (r.get("BUILDER_NAME") or "").strip():
                builder_rows += 1
            app = dpart(r.get("APPLICATION_DATE"))
            comp = dpart(r.get("COMPLETED_DATE"))
            grp = (r.get("PERMIT_TYPE") or "").strip() or None
            if app:
                proc.append((days(app, iss), grp, y))
            if cleared and comp:
                build.append((days(iss, comp), grp, yr_of(comp)))

    return {
        "source_rows": src,
        "monthly": {"count": series_full(by_m_n),
                    "value": series_full({k: round(x, 3) for k, x in by_m_v.items()}),
                    "units_created": series_full(by_m_u),
                    "units_lost": series_full(by_m_l)},
        "matrices": {"work": matrix(work, "work"),
                     "use": matrix(use, "structure type"),
                     "area": matrix(area, "forward sortation area")},
        "names": None,
        "names_gap": (f"Toronto's BUILDER_NAME field exists but is populated "
                      f"on only {builder_rows/total*100:.1f}% of permits, and "
                      f"is mostly individuals rather than firms — too thin "
                      f"and too personal to publish as a concentration "
                      f"panel."),
        "processing": intervals(proc, "PERMIT_TYPE"),
        "build_time": intervals(build, "PERMIT_TYPE"),
        "build_time_censored": True,
        "rows": total,
        "unparseable_cost": bad_cost,
        "map": {"available": False,
                "reason": ("Toronto's permit data carries no coordinates. "
                           "Postal codes are recorded on about 91% of rows, "
                           "which would support a forward-sortation-area "
                           "choropleth, but that is a far coarser map "
                           "answering a different question — it is shown as "
                           "the area breakdown below instead of being drawn "
                           "beside six real density grids.")},
    }, None


# =============================================================================
# Ottawa -- 15 annual XLSX workbooks, no API, no coordinates
# =============================================================================

def detail_ottawa(refresh=False):
    files = discover_ottawa_files()
    print(f"    discovered {len(files)} annual workbooks")
    cur = str(datetime.now().year)
    frames = []
    for item_id, title in files:
        force = cur in title
        print(f"    ...{title}", flush=True)
        frames.append(load_ottawa_year(item_id, refresh, force))
    df = pd.concat(frames, ignore_index=True)
    df["issued_date"] = pd.to_datetime(df.get("issued_date"), errors="coerce")
    df["value"] = pd.to_numeric(df.get("value"), errors="coerce")
    df["units"] = pd.to_numeric(df.get("units"), errors="coerce").fillna(0)
    src = int(len(df))
    df = df[df["issued_date"].notna()]

    by_m_n, by_m_v, by_m_u = defaultdict(int), defaultdict(float), defaultdict(int)
    work, use, area = {}, {}, {}
    names = defaultdict(lambda: [0, 0.0])
    name_rows = 0

    def bump(bag, k, y, v):
        if k is None or (isinstance(k, float) and pd.isna(k)):
            return
        k = str(k).strip()
        if not k or k.lower() == "nan":
            return
        cur = bag.get((k, y)) or [0, 0.0]
        cur[0] += 1
        cur[1] += v
        bag[(k, y)] = cur

    for row in df.itertuples(index=False):
        d = row.issued_date
        key, y = f"{d.year:04d}-{d.month:02d}", d.year
        v = float(row.value) if pd.notna(row.value) else 0.0
        by_m_n[key] += 1
        by_m_v[key] += v / 1e6
        by_m_u[key] += int(row.units or 0)
        bump(work, getattr(row, "building_type", None), y, v)
        bump(use, getattr(row, "appl_type", None), y, v)
        bump(area, getattr(row, "community", None), y, v)
        c = getattr(row, "contractor", None)
        c = str(c).strip().upper() if c is not None and pd.notna(c) else ""
        if c and c not in OTT_CONTRACTOR_PLACEHOLDERS:
            names[c][0] += 1
            names[c][1] += v
            name_rows += 1

    total = int(len(df))
    return {
        "source_rows": src,
        "monthly": {"count": series_full(by_m_n),
                    "value": series_full({k: round(x, 3) for k, x in by_m_v.items()}),
                    "units_created": series_full(by_m_u)},
        "matrices": {"work": matrix(work, "building type"),
                     "use": matrix(use, "application type"),
                     "area": matrix(area, "community")},
        "names": {"applicants": None,
                  "contractors": cloud([[k, v[0], v[1]] for k, v in names.items()],
                                       total, name_rows / total * 100)},
        "rows": total,
        "map": {"available": False,
                "reason": ("Ottawa publishes permits as annual spreadsheets "
                           "with no coordinates and no API. Ward and "
                           "community are the only geography in the files, "
                           "shown in the area breakdown instead.")},
    }, None


# =============================================================================
# roster
# =============================================================================

CITIES = {
    "vancouver":   ("City of Vancouver", "vancouver", "BC", detail_vancouver),
    "toronto":     ("City of Toronto", "toronto", "ON", detail_toronto),
    "calgary":     ("City of Calgary", "calgary", "AB", detail_calgary),
    "edmonton":    ("City of Edmonton", "edmonton", "AB", detail_edmonton),
    "mississauga": ("City of Mississauga", "toronto", "ON", detail_mississauga),
    "ottawa":      ("City of Ottawa", "ottawa", "ON", detail_ottawa),
    "montreal":    ("City of Montreal", "montreal", "QC", detail_montreal),
    "halifax":     ("Halifax Regional Municipality", "halifax", "NS", detail_halifax),
    "winnipeg":    ("City of Winnipeg", "winnipeg", "MB", detail_winnipeg),
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true",
                    help="Ottawa only: force re-download of every cached "
                         "annual XLSX workbook, not just the current year")
    ap.add_argument("--only", default="",
                    help="comma-separated city keys to rebuild (default: all)")
    args = ap.parse_args()

    want = [k.strip() for k in args.only.split(",") if k.strip()] or list(CITIES)
    unknown = [k for k in want if k not in CITIES]
    if unknown:
        print(f"unknown city key(s): {unknown}; known: {list(CITIES)}", file=sys.stderr)
        sys.exit(2)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    roster = {}
    idx_path = OUT_DIR / "_index.json"
    if idx_path.exists():          # keep untouched cities when --only is used
        try:
            roster = {c["key"]: c for c in
                      json.loads(idx_path.read_text(encoding="utf-8"))["cities"]}
        except Exception:
            roster = {}

    for key in want:
        label, cma, prov, fn = CITIES[key]
        print(f"\nfetching {label}...")
        try:
            detail, grid = (fn(args.refresh) if key == "ottawa" else fn())
        except Exception as e:
            print(f"\n!! {key} failed: {e}", file=sys.stderr)
            sys.exit(1)

        cur_ym = datetime.now().strftime("%Y-%m")
        partial = trim_partial_month(detail["monthly"], cur_ym)
        floored = None
        if key in SERIES_FLOOR:
            fl, reason = SERIES_FLOOR[key]
            n_excl = apply_floor(detail["monthly"], fl)
            floored = {"floor": fl, "permits_excluded": n_excl, "reason": reason}
            print(f"  floored series at {fl}: {n_excl:,} earlier permits excluded "
                  f"from the time series (still counted in totals)")
        else:
            check_leading_ramp(key, detail["monthly"])
        mo = detail["monthly"]["count"]
        start = mo["start"] if mo else None
        end = month_end(start, len(mo["values"])) if mo else None
        # The roster must not claim 525,644 permits beside a chart that starts
        # in 2017. `rows` stays the file's true all-time total; this is what
        # the PLOTTED record actually covers, summed from the series itself so
        # it accounts for both the floor and the dropped partial month rather
        # than only one of them. The page shows this figure and discloses the
        # difference.
        detail["rows_in_series"] = int(sum(v or 0 for v in mo["values"])) if mo else 0
        # Quantify the date gate rather than letting it pass silently: every
        # series here is keyed on the issue date, so an undated row appears
        # nowhere on the page. Counted here, reported on the city's card.
        src_rows = detail.pop("source_rows", None)
        if src_rows is not None:
            undated = max(src_rows - detail["rows"], 0)
            detail["source_rows"] = src_rows
            detail["undated_dropped"] = undated
            if undated:
                print(f"  date gate: {undated:,} of {src_rows:,} rows "
                      f"({undated/src_rows*100:.1f}%) carry no usable issue "
                      f"date and appear nowhere on the page")
        detail.update({"key": key, "label": label, "cma": cma, "province": prov,
                       "retrieved": datetime.now().strftime("%Y-%m-%d"),
                       "partial_month_dropped": partial,
                       "series_floor": floored,
                       "history": {"start": start, "end": end}})
        detail.setdefault("value_basis", "value")

        p = OUT_DIR / f"{key}.json"
        p.write_text(json.dumps(detail, ensure_ascii=False, separators=(",", ":")),
                     encoding="utf-8")
        print(f"  wrote {p.name} ({p.stat().st_size/1024:.0f} KB) "
              f"{start}..{end}, {detail['rows']:,} permits")

        gsize = 0
        if grid:
            gp = OUT_DIR / f"{key}_grid.json"
            gp.write_text(json.dumps(grid, separators=(",", ":")), encoding="utf-8")
            gsize = gp.stat().st_size
            print(f"  wrote {gp.name} ({gsize/1024:.0f} KB, "
                  f"{grid['permits']:,} mapped permits, "
                  f"{len(grid['years'])} years)")

        roster[key] = {
            "key": key, "label": label, "cma": cma, "province": prov,
            "start": start, "end": end,
            "rows": detail.get("rows_in_series", detail["rows"]),
            "rows_all_time": detail["rows"],
            "undated_dropped": detail.get("undated_dropped", 0),
            "excluded_before_floor": (floored or {}).get("permits_excluded", 0),
            "value_basis": detail["value_basis"],
            "has_map": bool(grid),
            "has_names": bool(detail.get("names") and
                              any(detail["names"].get(s) for s in
                                  ("applicants", "contractors"))),
            "grid_kb": round(gsize / 1024) if gsize else 0,
        }

    order = list(CITIES)
    idx = {
        "generated": datetime.now().strftime("%Y-%m-%d"),
        "cell_deg": CELL_DEG,
        "caveat": ("City boundaries, not census metropolitan areas. Every "
                   "series here is a SUBSET of the CMA figures on the "
                   "Construction Tracker and cannot be reconciled with them."),
        "cities": [roster[k] for k in order if k in roster],
    }
    idx_path.write_text(json.dumps(idx, ensure_ascii=False, indent=1),
                        encoding="utf-8")
    print(f"\nwrote _index.json ({len(idx['cities'])} cities)")


if __name__ == "__main__":
    main()
