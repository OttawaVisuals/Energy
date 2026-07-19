"""
build_ahri_lookup_full.py

Full-universe replacement for build_ahri_lookup.py's number source.

build_ahri_lookup.py only ever fetches the ~40 AHRI numbers in
ahri_numbers_seen.json, which list_ahri_numbers.py derives from the
already-published province_json/fsa_json outputs -- and those are masked to
each province's top 5 AHRI numbers (retrofits.html only *displays* a top-5
list, "to avoid singling out near-unique installations"). That display-time
masking accidentally became the scrape-time number source too, so the vast
majority of installed heat pumps never got a certificate lookup.

This script scans the raw ERS CSVs directly (bypassing that masked chain)
for every distinct AHRI value that ever appears, keeps the ones that look
like real AHRI reference IDs, and fetches all of them. Confirmed against a
full corpus scan (2026-07-19): candidates are cleanly separated from
placeholder/junk values by being purely numeric with 7-10 digits -- '0' (the
"no heat pump" placeholder, ~1.2M occurrences) and short test-looking values
("12345", "210", "9250", ...) all fall outside that range; every real,
AHRI-certificate-matched code observed so far falls inside it.

Scale: ~15,700 candidates vs. the ~40 build_ahri_lookup.py fetches. At the
same 1 req/sec courtesy pace as the existing scripts (this hits the same
undocumented internal API -- see build_ahri_lookup.py's docstring) a full
run takes several hours. This script is checkpointed after every single
fetch (atomic write) and skips numbers already resolved in lookup/ahri_numbers.json,
so it is always safe to Ctrl+C and re-run later -- it picks up where it left off.

Usage:
    pip install pandas requests
    python build_ahri_lookup_full.py

Output:
    lookup/ahri_numbers.json      merged into (not overwritten) -- same format
                                   build_ahri_lookup.py produces, so retrofits.html
                                   needs no changes.
    Python/ahri_numbers_all.json  the full candidate list + counts, for reference/debugging
                                   (does NOT replace ahri_numbers_seen.json, which
                                   HeatPump/pipeline/neep_buckets.py also reads).
"""

import json
import os
import re
import time
from pathlib import Path

import pandas as pd
import requests

# =============================================================================
# CONFIG — edit these if your paths differ
# =============================================================================
INPUT_DIR = r"C:\ERS"
CSV_FILES = [
    '2004-2006.csv', '2007.csv', '2008.csv', '2009.csv', '2010.csv',
    '2011.csv', '2012.csv', '2013.csv', '2014.csv', '2015.csv',
    '2016.csv', '2017.csv', '2018.csv', '2019.csv', '2020.csv',
    '2021.csv', '2022.csv', '2023.csv', '2024.csv', '2025.csv',
    '2026.csv',
]
CHUNK_ROWS = 200_000

# Candidate filter: real AHRI reference IDs observed on-site are all 7-10
# purely-numeric digits. '0' is the HOT2000 "no heat pump" placeholder
# (dominates junk by volume); short numeric strings under 7 digits are
# overwhelmingly one-off test/typo values (confirmed: max ~111 occurrences
# vs. thousands for real codes).
MIN_DIGITS, MAX_DIGITS = 7, 10
CANDIDATE_RE = re.compile(rf'\d{{{MIN_DIGITS},{MAX_DIGITS}}}')

REPO_ROOT = Path(__file__).resolve().parent.parent
LOOKUP_PATH = REPO_ROOT / "lookup" / "ahri_numbers.json"
CANDIDATES_OUT = REPO_ROOT / "Python" / "ahri_numbers_all.json"

DELAY_SECONDS = 1.0  # be polite — this is an undocumented internal API, not a public one

BASE = "https://beta-ahrisearch.ahridirectory.org/SearchConfiguration"
QUICK_SEARCH_URL = f"{BASE}/GetQuickSearchByReferenceId"
DETAIL_URL = f"{BASE}/GetSearchDetailResults"
HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json, text/plain, */*",
    "Origin": "https://www.ahridirectory.org",
    "Referer": "https://www.ahridirectory.org/",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
}

# Same field mapping as build_ahri_lookup.py, kept identical so lookup/ahri_numbers.json
# stays one consistent schema regardless of which script wrote which entry.
FIELD_MAP_M1 = {
    "OutdoorUnitBrandName": "brand",
    "SeriesName": "series",
    "ModelNumber": "model",
    "CoilModelNumber": "indoor_model",
    "Capacity95FHighM1": "cooling_capacity_btuh",
    "EER95FM1": "eer2",
    "SEERM1": "seer2",
    "HighHeat47FM1": "heating_capacity_47f_btuh",
    "HSPFM1": "hspf2",
    "Heating_Capacity_at_17F_M1": "heating_capacity_17f_btuh",
    "Heating_Capacity_at_5F_M1": "heating_capacity_5f_btuh",
    "Heating_COP_at_5F_M1": "heating_cop_5f",
    "RefrigerantType": "refrigerant",
    "IsEnergyStarApprovedbyAHRI": "energy_star",
    "ColdClimateDesignationSearch": "cold_climate",
    "AHRIType": "ahri_type",
    "ModelStatusId": "model_status",
}
FIELD_MAP_LEGACY = {
    "Capacity95FHighM": "cooling_capacity_btuh",
    "EER95FM": "eer2",
    "SEERM": "seer2",
    "HighHeat47FM": "heating_capacity_47f_btuh",
    "HSPFM": "hspf2",
    "Heating_Capacity_at_17F_M": "heating_capacity_17f_btuh",
    "Heating_Capacity_at_5F_M": "heating_capacity_5f_btuh",
}


def clean_ahri(s):
    """Mirrors ers_web_pipeline.py's clean_ahri: strip, drop trailing '.0' from
    years that serialized the identifier as a float."""
    s = s.strip()
    return re.sub(r'\.0+$', '', s)


def scan_candidates():
    """Stream every raw ERS CSV and return {code: occurrence_count} for every
    distinct value that survives the numeric 7-10-digit filter."""
    counts = {}
    for name in CSV_FILES:
        path = os.path.join(INPUT_DIR, name)
        if not os.path.exists(path):
            print(f"  {name}: not found, skipping")
            continue
        try:
            header = pd.read_csv(path, nrows=0, low_memory=False).columns.tolist()
        except Exception as ex:
            print(f"  {name}: could not read header ({ex}), skipping")
            continue
        if 'AHRI' not in header:
            print(f"  {name}: no AHRI column")
            continue
        year_new = 0
        for chunk in pd.read_csv(path, usecols=['AHRI'], chunksize=CHUNK_ROWS,
                                  dtype=str, low_memory=False):
            vals = chunk['AHRI'].dropna().astype(str).map(clean_ahri)
            vals = vals[vals.map(lambda v: bool(CANDIDATE_RE.fullmatch(v)))]
            for code, n in vals.value_counts().items():
                if code not in counts:
                    year_new += 1
                counts[code] = counts.get(code, 0) + int(n)
        print(f"  {name}: {year_new} new candidate codes, {len(counts)} distinct so far")
    return counts


def safe_json(r: requests.Response):
    if not r.text.strip():
        return None, f"empty_response(status={r.status_code})"
    try:
        return r.json(), None
    except ValueError:
        snippet = r.text[:150].replace("\n", " ")
        return None, f"non_json_response(status={r.status_code}, body_start={snippet!r})"


def fetch_one(session, ahri_number):
    r = session.post(QUICK_SEARCH_URL, json={"ReferenceId": ahri_number},
                      headers=HEADERS, timeout=15)
    quick, err = safe_json(r)
    if err:
        return None, f"quicksearch_error: {err}"
    if not quick:
        return None, "not_found"

    program_id = quick[0].get("ProgramId")
    if program_id is None:
        return None, "no_program_id"

    r = session.post(DETAIL_URL, json={"ProgramId": str(program_id), "ReferenceId": ahri_number},
                      headers=HEADERS, timeout=15)
    details, err = safe_json(r)
    if err:
        return None, f"detail_error: {err}"
    if not details:
        return None, "details_empty"

    return details, None


def extract_fields(details):
    by_name = {row.get("AzureUniqueName"): row.get("COLUMN_VALUE") for row in details}
    out = {}
    for azure_name, out_key in FIELD_MAP_M1.items():
        val = by_name.get(azure_name)
        if val not in (None, ""):
            out[out_key] = val
    for azure_name, out_key in FIELD_MAP_LEGACY.items():
        if out_key in out:
            continue
        val = by_name.get(azure_name)
        if val not in (None, ""):
            out[out_key] = val
    return out


def atomic_write_json(path, data):
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    os.replace(tmp, path)


def main():
    print("Scanning raw ERS CSVs for every distinct AHRI value...")
    counts = scan_candidates()
    print(f"\n{len(counts)} candidate codes found (numeric, {MIN_DIGITS}-{MAX_DIGITS} digits)")

    candidates_sorted = sorted(counts.items(), key=lambda kv: -kv[1])
    atomic_write_json(CANDIDATES_OUT, {
        "generated_from": "raw ERS CSVs, all years, unmasked (build_ahri_lookup_full.py)",
        "min_digits": MIN_DIGITS, "max_digits": MAX_DIGITS,
        "ahri_numbers": [{"number": k, "total_count": v} for k, v in candidates_sorted],
    })
    print(f"wrote {CANDIDATES_OUT}")

    lookup = {}
    if LOOKUP_PATH.exists():
        lookup = json.loads(LOOKUP_PATH.read_text(encoding="utf-8"))
    print(f"{len(lookup)} numbers already resolved in {LOOKUP_PATH.name}")

    todo = [num for num, _ in candidates_sorted if num not in lookup]
    print(f"{len(todo)} numbers left to fetch\n")

    t0 = time.time()
    resolved = delisted = errors = 0
    with requests.Session() as session:
        for i, num in enumerate(todo, 1):
            try:
                details, err = fetch_one(session, num)
            except Exception as ex:  # network blips must not kill an overnight run
                err = f"exception: {ex}"
                details = None

            if err:
                if err == "not_found" or err.startswith("quicksearch_error: empty_response"):
                    lookup[num] = {"model_status": "Delisted"}
                    delisted += 1
                    status = "delisted"
                else:
                    errors += 1
                    status = f"ERROR ({err}) — will retry on next run"
            else:
                fields = extract_fields(details)
                if fields.get("brand") or fields.get("model"):
                    lookup[num] = fields
                    resolved += 1
                    status = f"ok ({fields.get('brand')} {fields.get('model')})"
                else:
                    errors += 1
                    status = "ERROR (no brand/model found) — will retry on next run"

            if status.startswith("ok") or status == "delisted":
                atomic_write_json(LOOKUP_PATH, lookup)

            elapsed = time.time() - t0
            rate = elapsed / i
            eta_min = rate * (len(todo) - i) / 60
            print(f"[{i}/{len(todo)}] {num}: {status}  "
                  f"(resolved={resolved} delisted={delisted} errors={errors}, "
                  f"ETA {eta_min:.0f} min)", flush=True)

            time.sleep(DELAY_SECONDS)

    print(f"\nDone. {len(lookup)} total numbers in {LOOKUP_PATH} "
          f"({resolved} newly resolved, {delisted} newly delisted, {errors} still pending — re-run to retry them)")


if __name__ == "__main__":
    main()
