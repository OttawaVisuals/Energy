"""
One-off scrape of Retrofit Canada's case-study library (retrofitcanada.com/case-studies)
into a compact JSON companion for the Retrofit Insights page.

Why this exists: the ERS pipeline (ers_web_pipeline.py etc.) is a population-scale but
*shallow* dataset -- most homes in it did one or two measures. Retrofit Canada's library
is the opposite: a small, self-submitted set of deep/net-zero showcase retrofits, each
with a real before/after HOT2000-style breakdown (envelope R-values, ACH50, EUI, heat
loss by component, GHG by fuel). It's not a random sample -- it answers "what does the
deep end actually look like", not "what's typical". Never merge its numbers into the
ERS-derived aggregates; keep it a clearly-labelled, separately-rendered panel.

Site structure (checked 2026-08-25): both the listing page and every case-study page are
server-rendered plain HTML (WordPress + Interactivity API for the "Show more" toggle,
but no XHR involved -- the full card list ships in the initial response). Cloudflare
bot-scoring scripts are present but did not block a plain `requests` GET with a normal
browser User-Agent. If that changes, this will start returning short/challenge pages --
check response length before trusting a parse.

Every case-study page has two data shapes we care about:
  1. A summary key/value table (Location, Year Built, Annual Energy Savings, ...).
  2. A set of "Before & After" tables, one per category (General, Envelope,
     Mechanical & Electrical, Annual Energy Usage, Carbon Emissions), each row a
     (field label, before value, after value) triple in a fixed <tr class="child-row">
     structure -- see parse_before_after().
Plus an "Upgrades" checklist (categorical, not a before/after number).

Usage:
    python retrofit_casestudies_scrape.py

Output:
    C:\\Energy\\retrofit_casestudies_json\\_all.json
    {
      "scraped_at": "2026-08-25",
      "source": "https://retrofitcanada.com/case-studies",
      "license_note": "...",
      "n": 41,
      "cases": [ { "slug", "title", "url", "summary": {...},
                   "performance_level_bucket", "before_after": {...},
                   "upgrades": {...} }, ... ],
      "excluded_n": 7,
      "excluded": [ {...same shape, plus "exclude_reason"} ]   # non-residential / non-Canadian,
                                                                 # see exclusion_reason()
    }

Values are parsed into {"raw": <original text>, "value": <float|null>, "unit": <str|null>}
so downstream code can tell a real number from descriptive text ("Vinyl Triple Low E...")
without re-parsing. R-value fields ("R-33.66") get unit "R"; everything else takes
whatever trails the leading number (e.g. "ACH50", "kWh/m2/a", "%", "tCO2eq/y").

Polite by design: this is a manual one-off, not a scheduled pipeline step. Re-run it
by hand when you want a refresh -- the library only grows via their submission form,
there's no bulk API (they say so on the page: "To access our case study library
through an API, please contact us").
"""

import json
import re
import time
import urllib.request
from datetime import date
from pathlib import Path

from bs4 import BeautifulSoup

BASE = "https://retrofitcanada.com"
LISTING_URL = f"{BASE}/case-studies"
OUT_DIR = Path(__file__).resolve().parent.parent / "retrofit_casestudies_json"
OUT_FILE = OUT_DIR / "_all.json"
DELAY_S = 1.5
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")

LICENSE_NOTE = (
    "Retrofit Canada's Terms of Use (retrofitcanada.com/terms-of-use, checked "
    "2026-08-25): \"The content on this site is provided under an open-source "
    "license. You can view, download, and share it freely, including for "
    "commercial purposes, provided you give credit to Retrofit Canada.\""
)


def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", "ignore")


def discover_case_studies() -> list[dict]:
    html = fetch(LISTING_URL)
    soup = BeautifulSoup(html, "html.parser")
    seen, out = set(), []
    for a in soup.select('a[href^="/case-studies/"]'):
        href = a.get("href", "")
        if href in ("/case-studies/", "/case-studies"):
            continue
        if href in seen:
            continue
        seen.add(href)
        title = a.get_text(" ", strip=True)
        out.append({"slug": href.rsplit("/", 1)[-1], "title": title, "url": BASE + href})
    return out


_NUM_R = re.compile(r"^R-(-?[\d,]+\.?\d*)\s*(.*)$")
_NUM_PLAIN = re.compile(r"^(-?[\d,]+(?:\.\d+)?)\s*(.*)$")


def parse_value(raw: str) -> dict:
    raw = (raw or "").strip()
    if raw in ("", "N/A", "NA", "None", "-", "–"):
        return {"raw": raw, "value": None, "unit": None}
    m = _NUM_R.match(raw)
    if m:
        try:
            return {"raw": raw, "value": float(m.group(1).replace(",", "")), "unit": "R"}
        except ValueError:
            pass
    m = _NUM_PLAIN.match(raw)
    if m:
        try:
            unit = m.group(2).strip() or None
            return {"raw": raw, "value": float(m.group(1).replace(",", "")), "unit": unit}
        except ValueError:
            pass
    return {"raw": raw, "value": None, "unit": None}


def parse_summary_table(soup: BeautifulSoup) -> dict:
    """The top key/value table: Location, Year Built, Annual Energy Savings, ..."""
    out = {}
    container = soup.select_one(".case-study-project-info table")
    if not container:
        return out
    for strong in container.select("strong"):
        label = strong.get_text(" ", strip=True)
        val_td = strong.find_parent("td").find_next_sibling("td")
        if not val_td:
            continue
        raw = val_td.get_text(strip=True)  # no separator: keeps "183.1m2" from <sup>2</sup> intact
        out[label] = parse_value(raw)
    return out


def parse_before_after(soup: BeautifulSoup) -> dict:
    """Each category is its own <div class="responsive-table"><table>...</table></div>
    under the "Before & After" block: a parent-row (category name) then child-rows of
    (field label, before, after)."""
    out = {}
    ba_root = soup.select_one(".case-study-before-after-table")
    if not ba_root:
        return out
    for table in ba_root.select("div.responsive-table > table"):
        rows = table.find_all("tr")
        if not rows:
            continue
        category = rows[0].get_text(" ", strip=True)
        fields = {}
        for tr in rows[1:]:
            tds = tr.find_all("td")
            if len(tds) != 3:
                continue
            label = tds[0].get_text(" ", strip=True)
            if not label:
                continue  # the bare "Before"/"After" header row
            # strip the <h4>Before</h4>/<h4>After</h4> label out, then read the rest with
            # no join separator (a bare " " separator would insert a space inside values
            # split across nodes, e.g. "183.1m" + <sup>2</sup> -> "183.1m 2" instead of "183.1m2")
            for td in (tds[1], tds[2]):
                h4 = td.find("h4")
                if h4:
                    h4.extract()
            before_raw = tds[1].get_text(strip=True)
            after_raw = tds[2].get_text(strip=True)
            fields[label] = {"before": parse_value(before_raw), "after": parse_value(after_raw)}
        if fields:
            out[category] = fields
    return out


def parse_upgrades(soup: BeautifulSoup) -> dict:
    out = {}
    root = soup.select_one(".case_study_upgrades")
    if not root:
        return out
    category = None
    for el in root.find_all(["h4", "ul"]):
        if el.name == "h4":
            category = el.get_text(" ", strip=True)
        elif el.name == "ul" and category:
            out[category] = [li.get_text(" ", strip=True) for li in el.find_all("li")]
    return out


def bucket_performance_level(raw: str | None) -> str:
    """The free-text 'Performance Level' field is inconsistent -- most homeowners pick
    Net Zero / Net-Zero Ready, but some get a long descriptive sentence, a stray
    intervention name ("Oil to Heat Pump"), or the unfilled placeholder ("Please
    Select"). Bucket into the 4 groups worth charting; 'raw' stays in summary for
    anyone who wants the original text."""
    if not raw:
        return "Unknown"
    r = raw.strip().lower()
    if r in ("", "please select", "n/a", "na"):
        return "Unknown"
    if "not yet" in r:
        return "Partial / Other"
    if "ready" in r and "net" in r:
        return "Net-Zero Ready"
    if "net zero" in r or "net-zero" in r or "netzero" in r:
        return "Net Zero"
    return "Partial / Other"


CA_PROVINCES = {
    "AB": "Alberta", "BC": "British Columbia", "MB": "Manitoba", "NB": "New Brunswick",
    "NL": "Newfoundland and Labrador", "NF": "Newfoundland and Labrador", "NS": "Nova Scotia",
    "NT": "Northwest Territories", "NU": "Nunavut", "ON": "Ontario", "PE": "Prince Edward Island",
    "QC": "Quebec", "SK": "Saskatchewan", "YT": "Yukon",
}
CA_PROVINCE_TOKENS = {k.lower() for k in CA_PROVINCES} | {v.lower() for v in CA_PROVINCES.values()}
NON_RESIDENTIAL_TYPES = {"part 3", "municipal water utility", "office"}


def exclusion_reason(case: dict) -> str | None:
    """The library also carries commercial/institutional feasibility studies (schools,
    community centres, a water utility building) and at least one non-Canadian project
    (Harka Architecture HQ, Portland OR) -- out of scope for a page about Canadian home
    retrofits, and their R-values/EUI aren't comparable to a house's anyway. Filtered
    here (once, documented) rather than silently mixed into the residential ranges."""
    loc = (case["summary"].get("Location") or {}).get("raw", "")
    prov_token = loc.rsplit(",", 1)[-1].strip().lower() if "," in loc else ""
    if prov_token and prov_token not in CA_PROVINCE_TOKENS:
        return f"non-Canadian location ({loc})"
    bt = ((case["summary"].get("Building Type") or {}).get("raw") or "").strip().lower()
    if bt in NON_RESIDENTIAL_TYPES:
        return f"non-residential building type ({bt})"
    return None


def scrape_case(entry: dict) -> dict:
    html = fetch(entry["url"])
    soup = BeautifulSoup(html, "html.parser")
    summary = parse_summary_table(soup)
    return {
        **entry,
        "summary": summary,
        "performance_level_bucket": bucket_performance_level(
            (summary.get("Performance Level") or {}).get("raw")
        ),
        "before_after": parse_before_after(soup),
        "upgrades": parse_upgrades(soup),
    }


def main():
    print(f"Discovering case studies from {LISTING_URL} ...")
    entries = discover_case_studies()
    print(f"Found {len(entries)} case studies.")

    cases, excluded = [], []
    for i, entry in enumerate(entries, 1):
        print(f"  [{i}/{len(entries)}] {entry['slug']}")
        try:
            case = scrape_case(entry)
        except Exception as e:  # noqa: BLE001 -- one bad page shouldn't kill the run
            print(f"    FAILED: {e}")
            time.sleep(DELAY_S)
            continue
        reason = exclusion_reason(case)
        if reason:
            print(f"    excluded: {reason}")
            excluded.append({**case, "exclude_reason": reason})
        else:
            cases.append(case)
        time.sleep(DELAY_S)

    OUT_DIR.mkdir(exist_ok=True)
    payload = {
        "scraped_at": date.today().isoformat(),
        "source": LISTING_URL,
        "license_note": LICENSE_NOTE,
        "n": len(cases),
        "cases": cases,
        "excluded_n": len(excluded),
        "excluded": excluded,
    }
    OUT_FILE.write_text(json.dumps(payload, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {OUT_FILE} ({len(cases)} cases, {len(excluded)} excluded).")


if __name__ == "__main__":
    main()
