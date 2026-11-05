"""
construction_time_etl.py

Average length of construction (months from start to completion) for new
homes, monthly since January 1990, for Canada, the ten provinces and every
Census Metropolitan Area (CMA). Feeds the "How long it takes to build" chart
on construction.html. Source: CMHC Starts and Completions Survey (SCSS),
read from CMHC's Housing Market Information Portal (HMIP). This series is
NOT in any Statistics Canada table (checked 2026-11-05, see
docs/HMIP_CATALOGUE.md), so the WDS route used by construction_etl.py
doesn't apply.

WHAT IS PULLED (per geography, 4 HMIP "Historical Time Periods" tables)
    Length of Construction (in months)  by Dwelling Type    (TableId 1.2.7.x)
    Length of Construction (in months)  by Intended Market  (TableId 1.2.8.x)
    Completions (units)                 by Dwelling Type
    Completions (units)                 by Intended Market
    Dwelling types: Single, Semi-Detached, Row, Apartment, All.
    Intended markets: Homeowner, Rental, Condo, Co-Op, All.
    Completions are pulled with the SAME coverage as the construction-time
    tables (MetType=Cmas) so they can serve as (a) the sample size behind
    each monthly average and (b) weights for a 12-month average.

COVERAGE (CMHC's choice, not ours)
    "In Census Metropolitan Areas": a province or Canada value is the
    average over that area's CMAs only, not all of its territory. Prince
    Edward Island has no CMA, so every PEI value is suppressed (**). CMHC has
    collected completions only in CMAs since 2023-01-01.

GEOGRAPHY
    Canada (HMIP Country 1), 10 provinces (HMIP Province ids 10..59), and
    the CMAs listed in HMIP's own per-centre table (TableId 1.1.7.3, For =
    CMAs), resolved to HMIP ids through /Navigation/MetsByProvince/<id>.
    HMIP's "Ottawa" is the Ontario part of Ottawa-Gatineau and "Gatineau"
    the Quebec part; they get the page's existing codes ottawa_on/ottawa_qc.

INPUT
    Public, server-rendered HTML pages only (the same pages a browser shows):
        /hmip-pimh/en/TableMapChart/TableMatchingCriteria?...&RowField=TIMESERIES
    One page = every month 1990-01..latest for one geography x one breakdown.
    No JSON or export endpoints. 1 request/second.

OUTPUT (construction_json/ctime/, gitignored on main, published on gh-pages)
    index.json      retrieved date, coverage note, month range, geography
                    list, category labels, per-geography suppression counts
    <code>.json     {"code","name","series":{key:{start,freq:"m",values}}}
                    keys: loc_dt_<type>, loc_im_<market>, cmp_dt_<type>,
                    cmp_im_<market>; values in months (loc) or units (cmp);
                    null = suppressed (**) or not available (..)

VALIDATION (printed; the run fails on structural problems)
    - every table must be month-contiguous and start 1990-01 or later; a
      later start (Brantford: 2007-01) is front-padded with nulls and the
      geography's first_month is recorded in index.json
    - completions: All/Total must equal the sum of its categories
    - construction time: "All" must lie within its categories' min..max
      (it's a weighted average); out-of-range months are counted, not fixed

LIMITATIONS
    - 0.0 months is nulled as a "not recorded" placeholder (all of 1992-1993
      everywhere, plus scattered CMA months). CMHC's published province and
      Canada values DO average those zeros in, so in the affected months they
      are biased low (e.g. Ontario rental 2021-12: published 15.9 vs 17.6 from
      its CMAs without Hamilton's 0.0). Rare after 1993; we keep CMHC's
      values rather than recomputing them, and document it.
    - CMHC publishes no formal definition of this measure. We read it as the
      mean months from start (footings poured) to completion (all, or all but
      10%, of the work done) over units completed in the month. Unverified.
    - Small categories (semis, co-ops, small CMAs) can swing month to month;
      HMIP shows no reliability codes for this table. Use the completions
      count to judge n.

USAGE
    python Python/construction_time_etl.py               # fresh pull (~4 min)
    python Python/construction_time_etl.py --use-cache   # dev: reuse cached pages
    python Python/construction_time_etl.py --only on,toronto
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
import tempfile
import time
import unicodedata
from datetime import date
from pathlib import Path
from urllib.parse import quote

import requests
from bs4 import BeautifulSoup

HOST = "https://www03.cmhc-schl.gc.ca"
BASE = HOST + "/hmip-pimh/en"
UA = "energy-madeclear-construction-time/1.0 (research; reads public HTML pages only)"

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "construction_json" / "ctime"
CACHE_DIR = ROOT / "Python" / "hmip_cache"

START = "1990-01"

PROVINCES = [  # (page code, HMIP id, name) — codes match construction.html
    ("nl", "10", "Newfoundland and Labrador"), ("pe", "11", "Prince Edward Island"),
    ("ns", "12", "Nova Scotia"), ("nb", "13", "New Brunswick"), ("qc", "24", "Quebec"),
    ("on", "35", "Ontario"), ("mb", "46", "Manitoba"), ("sk", "47", "Saskatchewan"),
    ("ab", "48", "Alberta"), ("bc", "59", "British Columbia"),
]
# HMIP CMA name -> page code where construction.html already has one
CMA_CODES = {"Ottawa": "ottawa_on", "Gatineau": "ottawa_qc", "Toronto": "toronto",
             "Montréal": "montreal", "Vancouver": "vancouver", "Calgary": "calgary",
             "Edmonton": "edmonton", "Winnipeg": "winnipeg", "Halifax": "halifax"}

TABLES = [  # (series prefix, CategoryLevel2, ColumnField)
    ("loc_dt", "Length of Construction (in months)", "1"),
    ("loc_im", "Length of Construction (in months)", "18"),
    ("cmp_dt", "Completions", "1"),
    ("cmp_im", "Completions", "18"),
]
CATEGORY_KEYS = {  # HMIP column header -> key
    "Single": "single", "Semi-Detached": "semi", "Row": "row", "Apartment": "apartment",
    "Homeowner": "homeowner", "Rental": "rental", "Condo": "condo", "Co-Op": "coop",
    "All": "all", "Total": "all",
}
LABELS = {"dt": {"single": "Single-detached", "semi": "Semi-detached", "row": "Row (townhouse)",
                 "apartment": "Apartment & other", "all": "All dwelling types"},
          "im": {"homeowner": "Homeowner", "rental": "Rental", "condo": "Condo",
                 "coop": "Co-op", "all": "All markets"}}
MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}


class Fetcher:
    def __init__(self, use_cache: bool, delay: float = 1.0):
        self.use_cache, self.delay = use_cache, delay
        self.s = requests.Session()
        self.s.headers["User-Agent"] = UA
        self.last = 0.0
        self.network = 0

    def get(self, url: str) -> str:
        path = CACHE_DIR / (hashlib.sha1(url.encode()).hexdigest() + ".html")
        if self.use_cache and path.exists():
            return path.read_text(encoding="utf-8")
        for attempt in range(3):
            wait = self.delay - (time.time() - self.last)
            if wait > 0:
                time.sleep(wait)
            self.last = time.time()
            try:
                r = self.s.get(url, timeout=60)
                self.network += 1
                if r.status_code == 200:
                    text = r.content.decode("utf-8", "replace")
                    CACHE_DIR.mkdir(parents=True, exist_ok=True)
                    path.write_text(text, encoding="utf-8")
                    return text
                print(f"  ! HTTP {r.status_code} (try {attempt + 1}) {url}", file=sys.stderr)
            except requests.RequestException as e:
                print(f"  ! {e.__class__.__name__} (try {attempt + 1}) {url}", file=sys.stderr)
            time.sleep(5 * (attempt + 1))
        raise RuntimeError(f"fetch failed: {url}")


def table_url(geo_type: str, geo_id: str, cat2: str, column: str, row: str = "TIMESERIES") -> str:
    # MetType (coverage) only exists above the CMA level; a CMA page given
    # MetType returns HTTP 500 (seen 2026-11-05).
    met = "&MetType=Cmas" if geo_type in ("Country", "Province") else ""
    return (f"{BASE}/TableMapChart/TableMatchingCriteria?GeographyType={geo_type}"
            f"&GeographyId={geo_id}&CategoryLevel1={quote('New Housing Construction')}"
            f"&CategoryLevel2={quote(cat2)}&ColumnField={column}&RowField={row}{met}")


# Fallback: a few CMAs' history pages (Windsor, 2026-11-05) open on a short
# default range with no table, because of a CMHC data gap (Windsor: no data
# 2023-01..2025-06). The same table with an explicit 1990..latest range comes
# from /TableMapChart/Table (the page's own "Apply" target), keyed by the
# CMA-level historical TableIds below.
FALLBACK_TABLE_IDS = {"loc_dt": "1.2.7", "loc_im": "1.2.8", "cmp_dt": "1.2.2", "cmp_im": "1.16.2"}
GEO_TYPE_IDS = {"Country": 1, "Province": 2, "MetropolitanMajorArea": 3}


def ranged_url(prefix: str, geo_type: str, geo_id: str, end: str) -> str:
    return (f"{BASE}/TableMapChart/Table?TableId={FALLBACK_TABLE_IDS[prefix]}"
            f"&GeographyId={geo_id}&GeographyTypeId={GEO_TYPE_IDS[geo_type]}"
            f"&DisplayAs=Table&Ytd=False&Survey=Scss"
            f"&ForTimePeriod.Year={START[:4]}&ForTimePeriod.Month={int(START[5:])}"
            f"&ToTimePeriod.Year={end[:4]}&ToTimePeriod.Month={int(end[5:])}")


def norm(name: str) -> str:
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def slug(name: str) -> str:
    return norm(name.split("/")[0]).replace(" ", "_")


def parse_period(label: str) -> str | None:
    """'Jan 1990' or '1990 January' -> '1990-01'."""
    parts = label.lower().split()
    if len(parts) != 2:
        return None
    a, b = parts
    if a.isdigit():
        a, b = b, a
    m = MONTHS.get(a[:3])
    return f"{int(b):04d}-{m:02d}" if m and b.isdigit() else None


def parse_num(cell: str):
    cell = cell.replace(",", "").strip()
    if cell in ("**", "..", "", "-"):
        return None
    try:
        return float(cell)
    except ValueError:
        return None


def parse_timeseries(html: str) -> tuple[str, dict[str, list]]:
    soup = BeautifulSoup(html, "html.parser")
    title_el = soup.select_one("h1.table-title")
    title = " ".join(title_el.get_text(" ", strip=True).split()) if title_el else ""
    table = soup.find("table")
    if table is None:
        raise ValueError("no table on page")
    rows = [[c.get_text(" ", strip=True) for c in tr.find_all(["th", "td"])]
            for tr in table.find_all("tr")]
    header = rows[0][1:]
    keys = [CATEGORY_KEYS.get(h) for h in header]
    if None in keys:
        raise ValueError(f"unknown column(s) {header}")
    months, cols = [], {k: [] for k in keys}
    for r in rows[1:]:
        p = parse_period(r[0]) if r else None
        if p is None:
            continue
        months.append(p)
        for k, cell in zip(keys, r[1:]):
            cols[k].append(parse_num(cell))
    return title, {"months": months, **cols}


def month_index(s: str) -> int:
    return int(s[:4]) * 12 + int(s[5:7]) - 1


def check_months(months: list[str], where: str) -> int:
    """Contiguity check; returns how many leading months (from START) are
    missing. Some CMAs' HMIP history starts later than 1990 (Brantford:
    2007-01), so the series is front-padded with nulls, shown as a gap."""
    if not months or month_index(months[0]) < month_index(START):
        raise ValueError(f"{where}: starts {months[:1]}, expected {START} or later")
    for a, b in zip(months, months[1:]):
        if month_index(b) - month_index(a) != 1:
            raise ValueError(f"{where}: gap between {a} and {b}")
    return month_index(months[0]) - month_index(START)


def resolve_cmas(f: Fetcher) -> list[tuple[str, str, str, str]]:
    """HMIP's own CMA list -> (code, hmip_id, name, province code)."""
    html = f.get(table_url("Country", "1", "Length of Construction (in months)", "1", "25"))
    rows = BeautifulSoup(html, "html.parser").find("table").find_all("tr")
    names = [r.find(["th", "td"]).get_text(" ", strip=True) for r in rows[1:]]
    names = [n for n in names if n and n != "Canada"]
    lookup = {}
    for pcode, pid, _ in PROVINCES:
        nav = BeautifulSoup(f.get(f"{BASE}/Navigation/MetsByProvince/{pid}"), "html.parser")
        for a in nav.select("a.option[data-id]"):
            lookup.setdefault(norm(a.get_text(strip=True)), []).append((a["data-id"], pcode))
    out, missing = [], []
    for n in names:
        hits = lookup.get(norm(n), [])
        if len(hits) != 1:
            missing.append((n, hits))
            continue
        hid, pcode = hits[0]
        out.append((CMA_CODES.get(n, slug(n)), hid, n, pcode))
    if missing:
        raise RuntimeError(f"could not resolve CMA ids uniquely: {missing}")
    return out


def validate(code: str, series: dict, report: dict) -> None:
    for grp in ("dt", "im"):
        cmp_keys = [k for k in series if k.startswith(f"cmp_{grp}_") and not k.endswith("_all")]
        tot = series.get(f"cmp_{grp}_all")
        if tot and cmp_keys:
            bad = 0
            for i, t in enumerate(tot["values"]):
                parts = [series[k]["values"][i] for k in cmp_keys]
                if t is not None and all(p is not None for p in parts) and abs(sum(parts) - t) > 0.5:
                    bad += 1
            report.setdefault("completions_sum_mismatch", {})[f"{code}/{grp}"] = bad
        loc_keys = [k for k in series if k.startswith(f"loc_{grp}_") and not k.endswith("_all")]
        allv = series.get(f"loc_{grp}_all")
        if allv and loc_keys:
            out = 0
            for i, a in enumerate(allv["values"]):
                parts = [series[k]["values"][i] for k in loc_keys if series[k]["values"][i] is not None]
                if a is not None and parts and not (min(parts) - 0.05 <= a <= max(parts) + 0.05):
                    out += 1
            report.setdefault("loc_all_outside_range", {})[f"{code}/{grp}"] = out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--use-cache", action="store_true", help="reuse cached pages (development)")
    ap.add_argument("--only", help="comma list of codes to pull (e.g. on,toronto)")
    args = ap.parse_args()

    f = Fetcher(args.use_cache)
    geos = [("ca", "Country", "1", "Canada", None)]
    geos += [(c, "Province", i, n, c) for c, i, n in PROVINCES]
    cmas = resolve_cmas(f)
    geos += [(c, "MetropolitanMajorArea", i, n, p) for c, i, n, p in cmas]
    if args.only:
        keep = set(args.only.split(","))
        geos = [g for g in geos if g[0] in keep]
    print(f"{len(geos)} geographies ({len(cmas)} CMAs resolved)")

    # Write to a temp folder; swap into OUT_DIR only after every geography
    # succeeded. A CMHC outage mid-run (the monthly workflow runs this as a
    # non-blocking step) then leaves last month's files untouched, and no
    # half-written folder can be published. --only writes its files straight
    # into OUT_DIR and leaves index.json alone.
    stage = Path(tempfile.mkdtemp(prefix="ctime_")) if not args.only else OUT_DIR
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    report, index_geos, last_month, fallbacks = {}, [], None, []
    for code, gtype, gid, name, prov in geos:
        series, nulls, first, zeros = {}, {}, {}, {}
        for prefix, cat2, col in TABLES:
            url = table_url(gtype, gid, cat2, col)
            try:
                title, data = parse_timeseries(f.get(url))
            except ValueError as err:
                if gtype != "MetropolitanMajorArea" or not last_month:
                    raise
                print(f"  {code}/{prefix}: {err}; retrying with explicit range "
                      f"{START}..{last_month}")
                title, data = parse_timeseries(f.get(ranged_url(prefix, gtype, gid, last_month)))
                fallbacks.append(f"{code}/{prefix}")
            pad = check_months(data["months"], f"{code}/{prefix}")
            first[prefix] = data["months"][0]
            last_month = max(last_month or "", data["months"][-1])
            for k, vals in data.items():
                if k == "months":
                    continue
                vals = [None] * pad + vals
                key = f"{prefix}_{k}"
                if prefix.startswith("loc"):
                    # 0.0 months is CMHC's placeholder for "not recorded", not a
                    # duration: every geography shows 0.0 for all of 1992-1993,
                    # plus scattered CMA months, often with hundreds of
                    # completions. Nulled and counted (zero_months_nulled).
                    zeros[key] = sum(v == 0.0 for v in vals)
                    vals = [None if v is None or v == 0.0 else round(v, 1) for v in vals]
                else:
                    vals = [None if v is None else int(v) for v in vals]
                series[key] = {"start": START, "freq": "m", "values": vals}
                nulls[key] = sum(v is None for v in vals)
        validate(code, series, report)
        n_months = len(series["loc_dt_all"]["values"])
        # first month with any construction-time value (Montréal and London
        # have rows for 1990-1997 but every cell is "..")
        has = [i for i in range(n_months)
               if any(s["values"][i] is not None for k, s in series.items() if k.startswith("loc_"))]
        first_data = None
        if has:
            m = month_index(START) + has[0]
            first_data = f"{m // 12:04d}-{m % 12 + 1:02d}"
        (stage / f"{code}.json").write_text(
            json.dumps({"code": code, "name": name, "series": series}, separators=(",", ":")),
            encoding="utf-8")
        index_geos.append({"code": code, "name": name, "type": gtype, "hmip_id": gid,
                           "province": prov, "months": n_months,
                           "first_month": first_data,
                           "zero_months_nulled": {k: v for k, v in zeros.items() if v},
                           "null_months": {k: v for k, v in nulls.items() if v}})
        print(f"  {code:22s} {name[:30]:30s} all-types null months: "
              f"{nulls['loc_dt_all']}/{n_months}")

    index = {
        "retrieved": date.today().isoformat(),
        "source": "CMHC Starts and Completions Survey, via the Housing Market Information Portal",
        "source_url": BASE + "/TableMapChart",
        "coverage": "In Census Metropolitan Areas (MetType=Cmas). Province and Canada values "
                    "cover their CMAs only. PEI has no CMA, so its values are all suppressed.",
        "measure": "Average length of construction, months from start to completion, "
                   "for units completed in the month (CMHC publishes no formal definition).",
        "start": START, "end": last_month,
        "labels": LABELS,
        "geographies": index_geos,
        "validation": report,
        "ranged_fallbacks": fallbacks,
    }
    if args.only:
        print(f"--only: wrote {len(index_geos)} files into {OUT_DIR}; index.json not touched")
        return
    old_index = OUT_DIR / "index.json"
    if old_index.exists():
        prev = len(json.loads(old_index.read_text(encoding="utf-8"))["geographies"])
        if len(index_geos) < prev:
            shutil.rmtree(stage, ignore_errors=True)
            sys.exit(f"refusing to publish: {len(index_geos)} geographies < {prev} last time "
                     f"(HMIP layout change?); previous files left in place")
    (stage / "index.json").write_text(json.dumps(index, indent=1, ensure_ascii=False),
                                      encoding="utf-8")
    shutil.rmtree(OUT_DIR)
    shutil.move(str(stage), str(OUT_DIR))
    zt = sum(sum(g["zero_months_nulled"].values()) for g in index_geos)
    print(f"0.0-month placeholders nulled: {zt} cells across "
          f"{sum(1 for g in index_geos if g['zero_months_nulled'])} geographies")
    size = sum(p.stat().st_size for p in OUT_DIR.glob("*.json"))
    print(f"\nwrote {len(index_geos)} files + index.json ({size / 1e6:.2f} MB) -> {OUT_DIR}")
    print(f"months {START}..{last_month}; network requests {f.network}")
    for k, v in report.items():
        flagged = {g: n for g, n in v.items() if n}
        print(f"validation {k}: {len(flagged)} series with issues {flagged if flagged else ''}")


if __name__ == "__main__":
    main()
