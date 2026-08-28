"""
cagbc_leed_etl.py

Aggregates CaGBC's LEED + Zero Carbon Building (ZCB) project profile export
into construction_json/cagbc.json.

INPUT
    project_profile.csv, at the repo root, gitignored. This is a manual export
    from https://leed.cagbc.org/LEED/projectprofile_EN.aspx — that tool needs
    no sign-in and its "export a list of projects after a search" feature
    produces the full national list with no filter applied. Re-exporting is a
    manual step (there is no API), so this script has no --refresh; it reads
    whatever copy of the file is present and reports its own retrieval date
    against the newest date it finds inside the data.

WHY AGGREGATE ONLY, NOT THE RAW EXPORT
    Investigated 2026-08-27/28: CaGBC's site has no Terms of Use addressing the
    project database, scraping, or data reuse. The Member Terms & Conditions
    PDF is entirely about certification-MARK misuse (a builder falsely
    claiming certification), not data. The only site-wide "Terms and
    Conditions" page covers commercial matters (event refunds, course access)
    and is silent on content reuse. The generic "(c) CAGBC 2022. All rights
    reserved." footer is the same boilerplate on every page including the
    Privacy Policy — it is not a term attached to the export function, and
    Canada has no EU-style database right, so a plain factual field (a
    project's city, certification level, date) is not the kind of thing
    copyright protects in the first place.
    That said, "no restriction found" is not the same as "definitely fine to
    republish wholesale" — a compiled LIST of project names and addresses is
    closer to the compilation CaGBC actually built than any individual fact in
    it is. So this script publishes counts, medians and sums grouped by
    province / rating system / certification level / year — never a
    project-level row, name, or address. That mirrors how this repo already
    treats CHBA's figures: cited aggregate statistics with attribution, not a
    republished dataset.

DATA QUALITY, HANDLED EXPLICITLY
    "Certified" means the row HAS a certification_date, not that it has a
    certification_level. Confirmed by inspection: 152 rows have a
    certification_date but a blank certification_level, and every one of them
    is a ZCB-Design or ZCB-Performance row — the Zero Carbon Building program
    is pass/fail and never issues a Gold/Silver/Platinum-style level. Filtering
    on certification_level would silently drop every Zero Carbon certification
    from the "certified" count.

    project_size (declared building floor area) has one absurd outlier
    (399,420,000 — almost 400 million sq ft, for a waterfront redevelopment
    that is obviously a site-area or unit-conversion error, not a building)
    and 12 zeros. A plausibility gate drops anything <=0 or above
    SIZE_MAX_SQFT (10,000,000 sq ft — well above the next-largest real entry,
    ~1.7M sq ft) from the floor-area sum only; it does not affect project
    counts, which use every row regardless of size.

USAGE
    python cagbc_leed_etl.py
Exits non-zero if project_profile.csv is missing, so a monthly refresh does
not silently publish stale (or absent) CaGBC figures without a human noticing
the file needs re-exporting by hand.
"""

import sys
import csv
import json
from pathlib import Path
from datetime import datetime
from collections import defaultdict, Counter

REPO_ROOT = Path(__file__).resolve().parents[1]
CSV_PATH = REPO_ROOT / "project_profile.csv"
OUTPUT_DIR = REPO_ROOT / "construction_json"

SIZE_MAX_SQFT = 10_000_000

# Collapse the many historical rating-system labels (LEED Canada for New
# Construction, LEED BD+C: New Construction, LEED v1 pilot, ...) into the
# families the page actually needs to tell apart. Zero Carbon is its own
# program, not a LEED variant, and gets kept separate throughout.
def program_of(rating_system):
    rs = (rating_system or "").strip()
    if rs.startswith("ZCB-Design"):
        return "zcb_design"
    if rs.startswith("ZCB-Performance"):
        return "zcb_performance"
    if rs:
        return "leed"
    return "other"


PROV_CODE = {
    "Ontario": "on", "Quebec": "qc", "British Columbia": "bc", "Alberta": "ab",
    "Manitoba": "mb", "Nova Scotia": "ns", "Saskatchewan": "sk",
    "New Brunswick": "nb", "Newfoundland and Labrador": "nl",
    "Prince Edward Island": "pe", "Yukon": "yt",
    "Northwest Territories": "nt", "Nunavut": "nu",
}


def num(v):
    v = (v or "").strip()
    if not v:
        return None
    try:
        return float(v)
    except ValueError:
        return None


def main():
    if not CSV_PATH.exists():
        print(f"\n!! {CSV_PATH.name} not found at the repo root.", file=sys.stderr)
        print("   This is a manual export from https://leed.cagbc.org/LEED/"
              "projectprofile_EN.aspx (no sign-in needed; search with no "
              "filter, then export). Place it at the repo root and re-run.",
              file=sys.stderr)
        sys.exit(1)

    with open(CSV_PATH, encoding="latin-1", newline="") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        print(f"\n!! {CSV_PATH.name} is empty.", file=sys.stderr)
        sys.exit(1)

    registered = certified = 0
    by_prog = Counter()
    by_prog_certified = Counter()
    by_prov = defaultdict(lambda: Counter())     # prov -> {registered, certified}
    by_level = Counter()                          # LEED only; ZCB has no level
    by_year = defaultdict(Counter)                # year -> {prog: n}, by cert date
    floor_area = defaultdict(float)               # prog -> sum of plausible sizes
    floor_area_dropped = 0
    newest_seen = ""

    for r in rows:
        prog = program_of(r.get("rating_system"))
        registered += 1
        by_prog[prog] += 1
        is_certified = bool((r.get("certification_date") or "").strip())
        if is_certified:
            certified += 1
            by_prog_certified[prog] += 1
            y = r["certification_date"][:4]
            if y.isdigit():
                by_year[y][prog] += 1
                newest_seen = max(newest_seen, r["certification_date"])
            level = (r.get("certification_level") or "").strip()
            if level:                     # blank for every ZCB row, by design
                by_level[level] += 1

        prov = PROV_CODE.get((r.get("project_province") or "").strip())
        if prov:
            by_prov[prov]["registered"] += 1
            if is_certified:
                by_prov[prov]["certified"] += 1

        size = num(r.get("project_size"))
        if size is not None and 0 < size <= SIZE_MAX_SQFT:
            floor_area[prog] += size
        elif size is not None and size > 0:
            floor_area_dropped += 1

        newest_seen = max(newest_seen, (r.get("registration_date") or ""))

    payload = {
        "retrieved": datetime.now().strftime("%Y-%m-%d"),
        "newest_date_in_data": newest_seen,
        "source": "CaGBC LEED + Zero Carbon Building project profile export",
        "source_url": "https://leed.cagbc.org/LEED/projectprofile_EN.aspx",
        "access_note": ("Exported manually via CAGBC's own project-search "
                        "export feature; no sign-in required and no filter "
                        "applied. There is no API, so this is a point-in-time "
                        "snapshot, re-exported by hand — not a live feed."),
        "licence_note": ("CAGBC's site carries no Terms of Use addressing "
                         "this database, scraping, or data reuse; the "
                         "'All rights reserved' footer is generic site-wide "
                         "boilerplate, not a term attached to the export "
                         "function. Published here as AGGREGATE counts only "
                         "— no project name or address is included."),
        "totals": {"registered": registered, "certified": certified},
        "by_program": {
            "leed": {"registered": by_prog["leed"],
                    "certified": by_prog_certified["leed"]},
            "zcb_design": {"registered": by_prog["zcb_design"],
                          "certified": by_prog_certified["zcb_design"]},
            "zcb_performance": {"registered": by_prog["zcb_performance"],
                                "certified": by_prog_certified["zcb_performance"]},
        },
        "by_province": {p: dict(c) for p, c in sorted(by_prov.items())},
        "leed_certification_level": dict(by_level.most_common()),
        "certified_by_year": {
            y: dict(c) for y, c in sorted(by_year.items())
            if y >= "2010"          # thin early years are noise, not signal
        },
        "certified_floor_area_sqft": {
            k: round(v) for k, v in floor_area.items()
        },
        "floor_area_gate": {
            "max_sqft": SIZE_MAX_SQFT,
            "dropped_rows": floor_area_dropped,
            "note": ("Rows with a declared size above this or <=0 are "
                     "excluded from the floor-area sum only, never from "
                     "project counts. One entry (399,420,000 sq ft, a "
                     "waterfront-redevelopment project) is an obvious unit "
                     "or data-entry error, not a real building."),
        },
    }
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUTPUT_DIR / "cagbc.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))
    print(f"wrote {out.name} ({out.stat().st_size/1024:.1f} KB) from "
          f"{len(rows):,} rows, newest date in data: {newest_seen}")
    print(f"  registered: {registered:,}  certified: {certified:,}")
    print(f"  by program: {dict(by_prog)}")


if __name__ == "__main__":
    main()
