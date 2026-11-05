"""
hmip_catalogue.py

Builds a catalogue of every table CMHC's Housing Market Information Portal
(HMIP, https://www03.cmhc-schl.gc.ca/hmip-pimh/) offers, so we can see what
CMHC publishes that Statistics Canada's CMHC-sourced tables (34-10-0096 ..
34-10-0162) do not. Research tool: it lists tables, it does not download data.

WHY
    HMIP has no public API and no published table list. The only catalogue
    found elsewhere (the `cmhc` R package's R/cmhc_tables.R) covers just the
    tables its author wrapped. The portal's own "Full View" menu is the
    authoritative list, but it changes with geography level (59 measures at
    Canada/province/CMA, ~42 at CSD/zone/neighbourhood/tract, checked
    2026-11-05), and each measure splits further into "By" breakdowns and
    "Display Options". This script walks that tree.

INPUT (public HTML pages only, the same ones a browser renders)
    /hmip-pimh/en/TableMapChart?id=<geoId>&t=<typeCode>
        Full View page; menu links carry data-category-link="true" and the
        query params categoryLevel1/2/3.
    /hmip-pimh/en/TableMapChart/TableCategory?...
    /hmip-pimh/en/TableMapChart/TableMatchingCriteria?...
        Table pages. The "By:" and "Display Options:" lists give the
        breakdowns; the share link (data-url, base64 of the table URL) gives
        TableId / Survey / DefaultDataField / BreakdownGeographyTypeId; the
        hidden <div data-year> list gives the years the table covers.
    No JSON or export endpoints are called. No data values are kept.

GEOGRAPHY
    HMIP type codes: 1 Country, 2 Province, 3 MetropolitanMajorArea (CMAs,
    CAs and some towns), 4 CensusSubDivision, 5 SurveyZone, 6 Neighbourhood,
    7 CensusTract. The menu is structural, so by default we crawl ONE
    representative geography per level (Canada -> Ontario -> Toronto ->
    zone/CSD -> neighbourhood -> tract), plus one small centre (Bracebridge)
    to show what a small place loses. Add more with --geo TYPE:ID:LABEL.
    Drill-down ids come from /Navigation/MetsByProvince/<id>,
    /SurveyZonesAndCSDsByMet/<id>, /NeighbourhoodsBySurveyZone/<id>,
    /CensusTractsByNeighbourhood/<id>.

OUTPUT (cmhc_json/, gitignored, local only)
    hmip_catalogue.json         meta + one row per fetched table page
    hmip_catalogue.csv          same rows, flat
    hmip_catalogue_matrix.csv   one row per (category, measure, By, Display)
                                with the TableId found at each geography,
                                so availability by level reads across

POLITENESS / CACHE
    1 request per second by default (--delay). Every page is cached in
    Python/hmip_cache/ (scratch, never a deliverable); re-runs read the cache
    unless --refresh. The default run on 2026-11-05 was 859 pages (~15 min cold).

LIMITATIONS
    - Representative geographies only: a measure present for Toronto may be
      suppressed or absent for a smaller CMA. The matrix says "offered at
      this level for this place", not "available everywhere at this level".
    - "Years" are the portal's year selector for the default view, not a
      check that every cell has data (CMHC suppresses small-n cells, `**`).
    - Option sections other than "By" and "Display Options" (if any) are
      recorded by label but not expanded.

USAGE
    python Python/hmip_catalogue.py                      # default geographies
    python Python/hmip_catalogue.py --geos Canada --limit-categories 3   # smoke test
    python Python/hmip_catalogue.py --geo 3:1265:Ottawa  # add a geography
"""

from __future__ import annotations

import argparse
import base64
import csv
import hashlib
import json
import sys
import time
from datetime import date
from pathlib import Path
from urllib.parse import parse_qs, unquote, urljoin, urlparse

import requests
from bs4 import BeautifulSoup

HOST = "https://www03.cmhc-schl.gc.ca"
BASE = HOST + "/hmip-pimh/en"
UA = "energy-madeclear-hmip-catalogue/1.0 (research; reads public HTML pages only)"

ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = ROOT / "Python" / "hmip_cache"
OUT_DIR = ROOT / "cmhc_json"

GEO_TYPES = {1: "Country", 2: "Province", 3: "MetropolitanMajorArea",
             4: "CensusSubDivision", 5: "SurveyZone", 6: "Neighbourhood",
             7: "CensusTract"}

# (type code, HMIP id, label). Ids resolved via the Navigation pages on
# 2026-11-05; see module docstring.
DEFAULT_GEOS = [
    (1, "1", "Canada"),
    (2, "35", "Ontario"),
    (3, "2270", "Toronto (CMA)"),
    (3, "6035", "Bracebridge T (small centre)"),
    (4, "3519046", "Aurora (T) (CSD, Toronto CMA)"),
    (5, "227026", "Aurora, Newmkt, Whit-St. (zone, Toronto CMA)"),
    (6, "2270760", "Aurora (neighbourhood, Toronto CMA)"),
    (7, "22707600440.00", "Tract 0440.00 (Aurora)"),
]


class Fetcher:
    def __init__(self, delay: float, refresh: bool):
        self.delay = delay
        self.refresh = refresh
        self.session = requests.Session()
        self.session.headers["User-Agent"] = UA
        self.last = 0.0
        self.network = 0
        self.cached = 0
        CACHE_DIR.mkdir(parents=True, exist_ok=True)

    def get(self, url: str) -> str | None:
        key = hashlib.sha1(url.encode()).hexdigest()
        path = CACHE_DIR / f"{key}.html"
        if path.exists() and not self.refresh:
            self.cached += 1
            return path.read_text(encoding="utf-8")
        for attempt in range(3):
            wait = self.delay - (time.time() - self.last)
            if wait > 0:
                time.sleep(wait)
            self.last = time.time()
            try:
                r = self.session.get(url, timeout=60)
            except requests.RequestException as e:
                print(f"  ! {e.__class__.__name__} on {url} (try {attempt + 1})", file=sys.stderr)
                time.sleep(5 * (attempt + 1))
                continue
            self.network += 1
            if r.status_code == 200:
                path.write_text(r.text, encoding="utf-8")
                return r.text
            print(f"  ! HTTP {r.status_code} on {url} (try {attempt + 1})", file=sys.stderr)
            if r.status_code < 500:
                return None
            time.sleep(5 * (attempt + 1))
        return None


def qparams(href: str) -> dict:
    q = parse_qs(urlparse(href).query)
    return {k.lower(): v[0] for k, v in q.items()}


def parse_menu(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    out, seen = [], set()
    for a in soup.select('a[data-category-link="true"]'):
        href = urljoin(HOST, a["href"])
        if href in seen:
            continue
        seen.add(href)
        p = qparams(href)
        out.append({"cat1": p.get("categorylevel1", ""),
                    "cat2": p.get("categorylevel2", ""),
                    "cat3": p.get("categorylevel3", ""),
                    "label": a.get_text(" ", strip=True),
                    "url": href})
    return out


def decode_share(data_url: str) -> dict:
    """Share link tid= is base64 of the table URL (double-percent-encoded)."""
    tid = qparams(data_url).get("tid", "")
    if not tid:
        return {}
    raw = unquote(unquote(tid))
    raw += "=" * (-len(raw) % 4)
    try:
        table_url = base64.b64decode(raw).decode("utf-8", "replace")
    except ValueError:
        return {}
    return qparams(table_url)


def parse_table_page(html: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    sections = {}
    content = soup.select_one(".refine-table-content") or soup
    for h4 in content.find_all("h4"):
        name = h4.get_text(" ", strip=True).rstrip(":")
        ol = h4.find_next_sibling("ol")
        if not ol or name.lower().startswith("note"):
            continue
        opts = []
        for li in ol.find_all("li"):
            a = li.find("a")
            if a and a.get("href"):
                opts.append({"label": a.get_text(" ", strip=True),
                             "url": urljoin(HOST, a["href"]),
                             "selected": "selected" in (li.get("class") or [])})
        sections[name] = opts

    title_el = soup.select_one("h1.table-title")
    title = " ".join(title_el.get_text(" ", strip=True).split()) if title_el else ""

    share = soup.select_one("#share-section")
    meta = decode_share(share["data-url"]) if share and share.get("data-url") else {}

    years = [int(d["data-year"]) for d in soup.select("div[data-year]")
             if d["data-year"].isdigit()]
    quarterly = any(d.get("data-has-quarterly") == "true" for d in soup.select("div[data-year]"))

    source = ""
    for el in soup.find_all(string=lambda s: s and "Source:" in s):
        source = " ".join(el.parent.get_text(" ", strip=True).split())
        break

    return {"sections": sections, "title": title,
            "table_id": meta.get("tableid", ""), "survey": meta.get("survey", ""),
            "data_field": meta.get("defaultdatafield", ""),
            "breakdown_geo_type": meta.get("breakdowngeographytypeid", ""),
            "year_first": min(years) if years else None,
            "year_last": max(years) if years else None,
            "quarterly": quarterly, "source": source}


def selected_label(opts: list[dict]) -> str:
    for o in opts:
        if o["selected"]:
            return o["label"]
    return opts[0]["label"] if opts else ""


def crawl_geo(f: Fetcher, code: int, gid: str, label: str, limit: int | None) -> list[dict]:
    menu_html = f.get(f"{BASE}/TableMapChart?id={gid}&t={code}")
    if menu_html is None:
        print(f"  ! no menu for {label}", file=sys.stderr)
        return []
    menu = parse_menu(menu_html)
    if limit:
        menu = menu[:limit]
    print(f"{label}: {len(menu)} measures")
    rows, done = [], set()

    def record(item, url, page, by, display, status="ok"):
        rows.append({"geo_type_code": code, "geo_type": GEO_TYPES.get(code, str(code)),
                     "geo_id": gid, "geo_label": label,
                     "cat1": item["cat1"], "cat2": item["cat2"], "cat3": item["cat3"],
                     "by": by, "display": display,
                     "table_id": page.get("table_id", ""), "survey": page.get("survey", ""),
                     "data_field": page.get("data_field", ""),
                     "breakdown_geo_type": page.get("breakdown_geo_type", ""),
                     "year_first": page.get("year_first"), "year_last": page.get("year_last"),
                     "quarterly": page.get("quarterly", False),
                     "other_sections": "; ".join(f"{k}: {', '.join(o['label'] for o in v)}"
                                                 for k, v in page.get("sections", {}).items()
                                                 if k not in ("By", "Display Options")),
                     "title": page.get("title", ""), "source": page.get("source", ""),
                     "url": url, "status": status})

    for i, item in enumerate(menu, 1):
        if i % 10 == 0:
            print(f"  {i}/{len(menu)} measures, {len(rows)} tables "
                  f"(network {f.network}, cache {f.cached})")
        html = f.get(item["url"])
        if html is None:
            record(item, item["url"], {}, "", "", "fetch_failed")
            continue
        page = parse_table_page(html)
        by_opts = page["sections"].get("By", [])
        if not by_opts:  # measure with no breakdown choice
            disp = page["sections"].get("Display Options", [])
            record(item, item["url"], page, "", selected_label(disp))
            continue
        for by in by_opts:
            by_page = page if by["selected"] else None
            if by_page is None:
                h = f.get(by["url"])
                if h is None:
                    record(item, by["url"], {}, by["label"], "", "fetch_failed")
                    continue
                by_page = parse_table_page(h)
            disp_opts = by_page["sections"].get("Display Options", [])
            if not disp_opts:
                record(item, by["url"], by_page, by["label"], "")
                continue
            for d in disp_opts:
                key = (by["label"], d["label"], item["url"])
                if key in done:
                    continue
                done.add(key)
                if d["selected"]:
                    record(item, d["url"], by_page, by["label"], d["label"])
                    continue
                h = f.get(d["url"])
                if h is None:
                    record(item, d["url"], {}, by["label"], d["label"], "fetch_failed")
                    continue
                record(item, d["url"], parse_table_page(h), by["label"], d["label"])
    return rows


def write_outputs(rows: list[dict], geos: list[tuple], args) -> None:
    OUT_DIR.mkdir(exist_ok=True)
    fields = list(rows[0].keys()) if rows else []
    meta = {"crawled": date.today().isoformat(),
            "source": BASE + "/TableMapChart",
            "geographies": [{"type_code": c, "type": GEO_TYPES.get(c), "id": g, "label": l}
                            for c, g, l in geos],
            "rows": len(rows),
            "fetch_failed": sum(r["status"] != "ok" for r in rows),
            "notes": "Catalogue of table options only; no data values. "
                     "Representative geography per level; see Python/hmip_catalogue.py."}
    (OUT_DIR / "hmip_catalogue.json").write_text(
        json.dumps({"meta": meta, "rows": rows}, indent=1, ensure_ascii=False), encoding="utf-8")
    with open(OUT_DIR / "hmip_catalogue.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)

    # matrix: one row per combo, a column per geography holding its TableId
    geo_cols = [l for _, _, l in geos]
    matrix: dict[tuple, dict] = {}
    for r in rows:
        k = (r["cat1"], r["cat2"], r["cat3"], r["by"], r["display"])
        m = matrix.setdefault(k, {"survey": r["survey"], "years": "", **{g: "" for g in geo_cols}})
        m[r["geo_label"]] = r["table_id"] or ("FAILED" if r["status"] != "ok" else "?")
        if r["year_first"] and not m["years"]:
            m["years"] = f"{r['year_first']}-{r['year_last']}"
        if r["survey"] and not m["survey"]:
            m["survey"] = r["survey"]
    with open(OUT_DIR / "hmip_catalogue_matrix.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["category", "measure", "sub_measure", "by", "display", "survey", "years", *geo_cols])
        for k in sorted(matrix):
            m = matrix[k]
            w.writerow([*k, m["survey"], m["years"], *(m[g] for g in geo_cols)])

    print(f"\nwrote {len(rows)} rows, {len(matrix)} distinct combos -> {OUT_DIR}")
    print(f"fetch failures: {meta['fetch_failed']}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--geo", action="append", default=[],
                    help="extra geography TYPE:ID:LABEL (e.g. 3:1265:Ottawa)")
    ap.add_argument("--geos", help="comma list of default-geo label prefixes to keep (e.g. Canada,Toronto)")
    ap.add_argument("--limit-categories", type=int, help="first N measures per geography (smoke test)")
    ap.add_argument("--delay", type=float, default=1.0, help="seconds between network requests")
    ap.add_argument("--refresh", action="store_true", help="ignore the page cache")
    args = ap.parse_args()

    geos = list(DEFAULT_GEOS)
    if args.geos:
        keep = [s.strip().lower() for s in args.geos.split(",")]
        geos = [g for g in geos if any(g[2].lower().startswith(k) for k in keep)]
    for spec in args.geo:
        code, gid, label = spec.split(":", 2)
        geos.append((int(code), gid, label))

    f = Fetcher(args.delay, args.refresh)
    rows = []
    for code, gid, label in geos:
        rows += crawl_geo(f, code, gid, label, args.limit_categories)
    if not rows:
        sys.exit("no rows collected")
    write_outputs(rows, geos, args)
    print(f"requests: network {f.network}, cache {f.cached}")


if __name__ == "__main__":
    main()
