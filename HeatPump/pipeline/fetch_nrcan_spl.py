"""
fetch_nrcan_spl.py — Phase 3c source #1: NRCan Searchable Product List (SPL).

Pulls NRCan's eligible-product lists for air-source heat pumps into a tidy CSV
keyed on AHRI certified reference number, so it can be joined against the ERS
installed-base counts (Python/ahri_numbers_all.json) and the AHRI Directory
scrape (lookup/ahri_numbers.json).

WHY THIS SOURCE, given we already scrape AHRI directly
------------------------------------------------------
Two things NRCan publishes that the AHRI Directory API does NOT expose:

  1. HSPF2_Region_V — the AHRI certificate (and therefore our scrape) only
     carries HSPF2 for Region IV. Region V is the COLD-climate rating region,
     which is the one that actually matters for Canadian heating analysis.
     This is the single best reason to fetch this list.
  2. Capacity_Maintenance_Max_5FRated_47F — NRCan's own precomputed
     (Max 5F / Rated 47F) capacity-maintenance percentage, i.e. an independent
     check on the ratio we compute ourselves from the two capacities.

Plus: PRODUCT_GROUP (ccASHP vs ASHP), a clean ducting-configuration string
(vs. AHRI's HRCU-A-CB type codes), and Canadian-market/Greener-Homes grant
eligibility, which is a genuine market filter our AHRI data has no way to
express.

CAVEAT: this is an ELIGIBILITY list of currently-listed products, not a
historical registry. It will not cover the Discontinued/Delisted units that
make up most of the ERS installed base by volume. It ADDS fields for the
models it does cover; it does not fill coverage gaps. See METHODOLOGY.md
"Heat pump tiers (Phase 3c)".

SOURCE / MECHANISM
------------------
https://spl-lpi.nrcan-rncan.gc.ca/en-US/product/?product=<segment>

The page renders client-side and its "Download all (CSV)" button posts to a
Power Automate workflow endpoint (paged JSON, not a static file). There is no
stable static CSV URL. The endpoint URL + signature below were read out of the
page's own inline JavaScript (`defaultCSVAPI`); if NRCan rotates the workflow
signature this script will start returning HTTP 401/403 and the constant must
be re-read from the page source. That fragility is why the raw pull is cached
to data/raw/nrcan/ and committed downstream as a tidy CSV.

Usage:
    pip install requests pandas
    python pipeline/fetch_nrcan_spl.py

Output:
    data/raw/nrcan/spl_<segment>.json    raw API rows, one file per segment
    data/interim/nrcan_spl.csv           tidy union, one row per (segment, AHRI number)
"""

import json
import sys
import time
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw" / "nrcan"
INTERIM_DIR = ROOT / "data" / "interim"

# Read from the SPL page's inline JS (`defaultCSVAPI`, production branch).
CSV_API = (
    "https://bbaf081944c6ec4c89b9863ca65aaa.f0.environment.api.powerplatform.com:443"
    "/powerautomate/automations/direct/workflows/454e5709322d4ee98060990f6a2610a3"
    "/triggers/manual/paths/invoke"
    "?api-version=1&sp=%2Ftriggers%2Fmanual%2Frun&sv=1.0"
    "&sig=IoNeq6ntJbEKCaDgRXMcN_isWY48arviGMy-qSXA-2w"
)

# Product segments worth pulling. 'ashp1_gh' is the Greener Homes ccASHP list
# (the one with HSPF2 Region V); 'ashp2_gh' covers the second eligibility group.
# Confirmed 2026-07-26: these are the only two ASHP segments the API serves --
# a bare 'ashp_gh' returns HTTP 502 (the segment does not exist), which the
# per-segment error handling below tolerates rather than aborting the run.
SEGMENTS = ["ashp1_gh", "ashp2_gh"]

PAGE = 100_000          # the site's own page size
DELAY_SECONDS = 2.0     # courtesy pace between pages
TIMEOUT = 300


def fetch_segment(session, segment):
    """Page through the CSV API for one product segment. Returns a list of dict rows."""
    rows, skip = [], 0
    while True:
        body = {"product": segment, "lang": "en-US", "skip": skip, "take": PAGE, "filters": {}}
        r = session.post(CSV_API, json=body, timeout=TIMEOUT)
        if r.status_code != 200:
            print(f"  {segment}: HTTP {r.status_code} at skip={skip} — "
                  f"the workflow signature may have rotated; re-read defaultCSVAPI "
                  f"from the SPL page source.", file=sys.stderr)
            break
        try:
            page = r.json().get("data") or []
        except ValueError:
            print(f"  {segment}: non-JSON response at skip={skip}", file=sys.stderr)
            break
        rows.extend(page)
        print(f"  {segment}: +{len(page)} rows (total {len(rows)})")
        if len(page) < PAGE:
            break
        skip += PAGE
        time.sleep(DELAY_SECONDS)
    return rows


def main():
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    INTERIM_DIR.mkdir(parents=True, exist_ok=True)

    session = requests.Session()
    frames = []
    for segment in SEGMENTS:
        print(f"Fetching NRCan SPL segment '{segment}'...")
        rows = fetch_segment(session, segment)
        if not rows:
            print(f"  {segment}: no rows, skipping")
            continue
        with open(RAW_DIR / f"spl_{segment}.json", "w", encoding="utf-8") as f:
            json.dump(rows, f)
        df = pd.DataFrame(rows)
        df["spl_segment"] = segment
        frames.append(df)

    if not frames:
        print("No data fetched.", file=sys.stderr)
        return 1

    out = pd.concat(frames, ignore_index=True)

    # Normalise the AHRI key to the same string form the rest of the pipeline
    # uses (see clean_ahri in Python/build_ahri_lookup_full.py).
    key = "AHRI_Certified_Reference_Number"
    if key in out.columns:
        out["ahri_number"] = (
            out[key].astype(str).str.strip().str.replace(r"\.0+$", "", regex=True)
        )
        # One product can be listed under several indoor/furnace combinations;
        # keep the first row per (segment, AHRI number) for the unit-level fields.
        out = out.drop_duplicates(subset=["spl_segment", "ahri_number"], keep="first")

    dest = INTERIM_DIR / "nrcan_spl.csv"
    out.to_csv(dest, index=False, encoding="utf-8")
    print(f"\nWrote {dest} — {len(out)} rows, {out['ahri_number'].nunique()} distinct AHRI numbers")
    print(f"Columns: {list(out.columns)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
