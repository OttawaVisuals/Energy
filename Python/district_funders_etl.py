"""
District Energy Explorer — public funders pipeline (GMF + CIB).

PURPOSE
  Collect the *facts* about projects funded by two public funders so the District
  Energy page can show them next to the CEEDC facility inventory:
    GMF  Green Municipal Fund (FCM)      https://info.gmf-fmv.ca  (all 1,165+ projects)
    CIB  Canada Infrastructure Bank      https://cib-bic.ca       (all projects)
  Per the 2026-11-25 decision we pull EVERYTHING and let the page filter.

LICENSING (decided 2026-11-25: "facts + links only")
  CIB terms of use bar republishing site content without written consent; GMF terms
  returned 403 and could not be read, so rights are unconfirmed. We therefore keep
  only bare facts (name, place, sector, status, amounts, years) and a link back to
  each source page. NO descriptions, summaries, testimonies, images or other prose
  are copied. This is a judgment call, not legal clearance.

INPUTS
  GMF  /en-US/ProjectSearch/?page=N  server-rendered HTML, 10 cards per page ->
       project ids + card facts; then /projectdetails/?id=<guid> for the money fields
       (Project value / Grant amount / Loan amount). No API exists (Power Pages
       portal, /_odata not exposed). Polite delay between requests.
  CIB  GraphQL  POST https://cib-bic.ca/admin/actions/graphql/api
       entries(type:"project") — section handle is "projects" (not "project").

OUTPUT (districtenergy_json/, gitignored on main, published to gh-pages)
  funded_projects.json   {meta, gmf:[...], cib:[...]}; meta carries counts + drops
  Derived fields on each GMF row: stage (study|project, from GMF's `type`), fuel_gmf
  (GMF's own District Energy sub-sector label), capacity (hand-entered, from
  districtenergy/curated/gmf_capacity.json: only 3 projects state a plant MW).
  Python/gmf_cache/      raw detail-page cache (scratch, never a deliverable)

HONESTY
  Amounts are as reported by the funder (not measured). Nothing is dropped
  silently: records whose detail page fails keep their search-card facts with
  money fields null, and meta.drops counts every such case by gate.

RUN   python Python/district_funders_etl.py            (resumable; ~10-15 min first run)
"""
import json, os, re, sys, time, random, datetime
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OUT_DIR = os.path.join(ROOT, "districtenergy_json")
CACHE = os.path.join(HERE, "gmf_cache")
GMF = "https://info.gmf-fmv.ca"
CIB_API = "https://cib-bic.ca/admin/actions/graphql/api"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/140.0 Safari/537.36"}

sess = requests.Session()
sess.headers.update(UA)


def get(url, tries=4):
    for i in range(tries):
        try:
            r = sess.get(url, timeout=(10, 40))
            if r.status_code in (429, 500, 502, 503, 504):
                raise requests.RequestException(f"HTTP {r.status_code}")
            r.raise_for_status()
            return r.content
        except requests.RequestException as e:
            if i == tries - 1:
                raise
            time.sleep(2 ** i)


def money(s):
    """'$1,234,567' -> 1234567.0 ; blank/unparseable -> None."""
    if not s:
        return None
    m = re.search(r"[\d,]+(?:\.\d+)?", s.replace("$", ""))
    return float(m.group(0).replace(",", "")) if m else None


def val_of(card, label):
    for blk in card.select("div.col-lg-4"):
        h = blk.find("span", class_="heading")
        if h and h.get_text(strip=True).lower() == label.lower():
            v = blk.find("span", class_="value")
            return v.get_text(" ", strip=True) if v else None
    return None


def gmf_search():
    """Walk every search page; return {guid: card facts}. Stops when a page adds nothing."""
    cards, page, total = {}, 1, None
    while True:
        html = get(f"{GMF}/en-US/ProjectSearch/?page={page}")
        soup = BeautifulSoup(html, "lxml")
        if total is None:
            m = re.search(r"([\d,]+)\s+results found", soup.get_text(" "))
            total = int(m.group(1).replace(",", "")) if m else None
        rows = soup.select("div.results-row")
        new = 0
        for row in rows:
            a = row.select_one("a.project-name")
            if not a:
                continue
            m = re.search(r"id=([0-9a-f-]{36})", a.get("href", ""), re.I)
            if not m:
                continue
            gid = m.group(1).lower()
            if gid in cards:
                continue
            new += 1
            cards[gid] = {
                "id": gid,
                "name": a.get_text(" ", strip=True),
                "type": val_of(row, "Type"),
                "sector": val_of(row, "Sector"),
                "status": val_of(row, "Status"),
                "municipality": val_of(row, "Municipality"),
                "subsector": val_of(row, "Sub Sector"),
                "timeline": val_of(row, "Project Timeline"),
            }
        print(f"  GMF search page {page}: +{new} (total {len(cards)}/{total})", flush=True)
        if new == 0:
            break
        page += 1
        time.sleep(random.uniform(0.2, 0.5))
    return cards, total


def gmf_detail(gid):
    """Money fields from the detail page (cached). Returns dict or None on failure."""
    os.makedirs(CACHE, exist_ok=True)
    fp = os.path.join(CACHE, gid + ".json")
    if os.path.exists(fp):
        with open(fp, encoding="utf-8") as f:
            return json.load(f)
    html = get(f"{GMF}/projectdetails/?id={gid}")
    soup = BeautifulSoup(html, "lxml")
    info = {}
    for blk in soup.select(".details-values .col-md-4.col-6"):
        h = blk.find("span", class_="heading")
        if not h:
            continue
        label = h.get_text(" ", strip=True).replace(":", "").strip()
        h.extract()
        info[label] = blk.get_text(" ", strip=True)
    out = {
        "project_value": money(info.get("Project value")),
        "grant": money(info.get("Grant amount")),
        "loan": money(info.get("Loan amount")),
        "project_number": info.get("Project number"),
        "population": money(info.get("Population")),
        "found_fields": len(info),
    }
    with open(fp, "w", encoding="utf-8") as f:
        json.dump(out, f)
    time.sleep(random.uniform(0.2, 0.5))
    return out


def cib_projects():
    q = """{ entries(type:"project") { title slug url dateUpdated
      ... on project_Entry { location provinces { title } sector { title }
      commitment partner } } }"""
    r = requests.post(CIB_API, json={"query": q}, headers=UA, timeout=60)
    r.raise_for_status()
    j = r.json()
    if "errors" in j:
        raise SystemExit(f"CIB GraphQL errors: {j['errors']}")
    return j["data"]["entries"]


def cib_amount_musd(s):
    """'$218 million (financial close)' -> 218.0 ; billions -> x1000 ; else None."""
    if not s:
        return None
    m = re.search(r"\$\s*([\d,.]+)\s*(million|billion)?", s, re.I)
    if not m:
        return None
    try:
        v = float(m.group(1).replace(",", ""))
    except ValueError:
        return None
    unit = (m.group(2) or "").lower()
    return v * 1000 if unit == "billion" else v if unit == "million" else v / 1e6


STUDY_TYPES = {"Feasibility Study", "Plan", "Program Design Study", "Program Evaluation Study"}


def stage_of(gmf_type):
    """'study' = feasibility study / plan / design or evaluation study (nothing built);
    'project' = capital project, pilot, monitoring or recommissioning work."""
    return "study" if gmf_type in STUDY_TYPES else "project"


def fuel_of(subsector):
    """GMF's own sub-sector label for district energy ('District Energy - Biomass' -> 'Biomass').
    This is GMF's category, not ours; None for non-district-energy rows."""
    m = re.match(r"District Energy\s*-\s*(.+)$", subsector or "")
    return m.group(1).strip() if m else None


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    cap_fp = os.path.join(ROOT, "districtenergy", "curated", "gmf_capacity.json")
    capacity = json.load(open(cap_fp, encoding="utf-8")) if os.path.exists(cap_fp) else {}
    drops = {"gmf_detail_failed": 0, "gmf_search_count_mismatch": 0,
             "cib_no_amount_parsed": 0}

    print("CIB ...")
    cib = []
    for e in cib_projects():
        amt = cib_amount_musd(e.get("commitment"))
        if amt is None:
            drops["cib_no_amount_parsed"] += 1
        cib.append({
            "name": e["title"], "url": e["url"], "location": e.get("location"),
            "provinces": [p["title"] for p in e.get("provinces") or []],
            "sectors": [s["title"] for s in e.get("sector") or []],
            "commitment_raw": " ".join((e.get("commitment") or "").split()) or None,
            "commitment_musd": amt,
            "partner": e.get("partner"),
            "updated": (e.get("dateUpdated") or "")[:10] or None,
        })
    print(f"  CIB: {len(cib)} projects")

    print("GMF search ...")
    cards, total = gmf_search()
    if total and len(cards) != total:
        drops["gmf_search_count_mismatch"] = total - len(cards)
        print(f"  WARNING: site says {total}, collected {len(cards)}")

    print("GMF details ...")
    gmf = []
    for i, (gid, c) in enumerate(cards.items(), 1):
        try:
            d = gmf_detail(gid)
        except Exception as e:
            print(f"  [detail failed] {gid}: {e}")
            d = None
            drops["gmf_detail_failed"] += 1
        row = dict(c)
        row["url"] = f"{GMF}/projectdetails/?id={gid}"
        row["stage"] = stage_of(c["type"])
        row["fuel_gmf"] = fuel_of(c["subsector"])
        row["capacity"] = capacity.get(gid)
        row.update({k: (d or {}).get(k) for k in
                    ("project_value", "grant", "loan", "project_number", "population")})
        gmf.append(row)
        if i % 100 == 0:
            print(f"  {i}/{len(cards)}", flush=True)

    meta = {
        "generated": datetime.date.today().isoformat(),
        "licensing": "Facts + links only (decided 2026-11-25). No descriptions or "
                     "prose copied. CIB terms bar republishing without written "
                     "consent; GMF terms unreadable (403).",
        "gmf_site_total": total, "gmf_collected": len(gmf), "cib_collected": len(cib),
        "drops": drops,
        "amounts": "As reported by each funder; GMF in CAD, CIB commitment in CAD millions "
                   "parsed from free text (commitment_raw kept).",
    }
    with open(os.path.join(OUT_DIR, "funded_projects.json"), "w", encoding="utf-8") as f:
        json.dump({"meta": meta, "gmf": gmf, "cib": cib}, f, ensure_ascii=False,
                  separators=(",", ":"))
    print(json.dumps(meta, indent=2))


if __name__ == "__main__":
    main()
