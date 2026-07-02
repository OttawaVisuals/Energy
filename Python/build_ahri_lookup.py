"""
build_ahri_lookup.py

Fetches AHRI Directory data for every AHRI number that actually appears on
the site (from ahri_numbers_seen.json, see list_ahri_numbers.py) and writes
lookup/ahri_numbers.json in the format retrofits.html's decodeAhri() expects:
  { "<ahri_number>": {"brand": "...", "model": "...", ...} }

Adapted from ahri_extract_data.py's fetch approach (quick search + detail
only, no PDF download/parsing needed) -- but instead of dumping every field
for manual review, this pulls a fixed set of fields relevant to heat pumps
straight into the site's lookup file, replacing the old workflow of
downloading certificate PDFs into ahri_certificates/ and parsing them with
parse_ahri_certificates.py.

Numbers that no longer resolve on the AHRI Directory (a clean empty
quicksearch result, or an empty HTTP 200 body -- per check_ahri_directory.py,
both genuinely mean delisted/expired, not a fetch failure) still get a
minimal entry of {"model_status": "Delisted"}, so the site can flag them
even though no brand/model is available anymore.

decodeAhri() in retrofits.html renders brand + model, plus a status badge
(model_status, e.g. "Active" / "Delisted" / "Production Stopped") and a
"Cold Climate" badge when cold_climate is "Yes". The rest of the fields
(efficiency ratings, capacities, etc.) are stored for a future pass at
surfacing them in the UI.

Usage:
    pip install requests
    python build_ahri_lookup.py
"""

import json
import time
from pathlib import Path
import requests

BASE = "https://beta-ahrisearch.ahridirectory.org/SearchConfiguration"
QUICK_SEARCH_URL = f"{BASE}/GetQuickSearchByReferenceId"
DETAIL_URL = f"{BASE}/GetSearchDetailResults"

DELAY_SECONDS = 1.0
NUMBERS_SEEN_PATH = Path("ahri_numbers_seen.json")
OUT_PATH = Path("lookup") / "ahri_numbers.json"

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

# AzureUniqueName -> output key, for the current (2023+) DOE test procedure
# ("Appendix M1" fields). Preferred over the legacy fields below when both
# are present.
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
# Legacy "Appendix M" fields, used only to fill in a value the M1 map
# didn't find -- some older certifications predate the M1 test procedure
# and only carry these.
FIELD_MAP_LEGACY = {
    "Capacity95FHighM": "cooling_capacity_btuh",
    "EER95FM": "eer2",
    "SEERM": "seer2",
    "HighHeat47FM": "heating_capacity_47f_btuh",
    "HSPFM": "hspf2",
    "Heating_Capacity_at_17F_M": "heating_capacity_17f_btuh",
    "Heating_Capacity_at_5F_M": "heating_capacity_5f_btuh",
}


def safe_json(r: requests.Response):
    if not r.text.strip():
        return None, f"empty_response(status={r.status_code})"
    try:
        return r.json(), None
    except ValueError:
        snippet = r.text[:150].replace("\n", " ")
        return None, f"non_json_response(status={r.status_code}, body_start={snippet!r})"


def fetch_one(session: requests.Session, ahri_number: str):
    """Returns (list_of_field_rows, status_note). status_note is None on success."""
    r = session.post(
        QUICK_SEARCH_URL, json={"ReferenceId": ahri_number}, headers=HEADERS, timeout=15
    )
    quick, err = safe_json(r)
    if err:
        return None, f"quicksearch_error: {err}"
    if not quick:
        return None, "not_found"

    program_id = quick[0].get("ProgramId")
    if program_id is None:
        return None, "no_program_id"

    r = session.post(
        DETAIL_URL,
        json={"ProgramId": str(program_id), "ReferenceId": ahri_number},
        headers=HEADERS,
        timeout=15,
    )
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
            continue  # M1 value already filled this in
        val = by_name.get(azure_name)
        if val not in (None, ""):
            out[out_key] = val
    return out


def main():
    numbers = [
        x["number"]
        for x in json.loads(NUMBERS_SEEN_PATH.read_text(encoding="utf-8"))["ahri_numbers"]
    ]

    lookup = {}
    with requests.Session() as session:
        for i, num in enumerate(numbers, 1):
            print(f"[{i}/{len(numbers)}] {num}...", end=" ", flush=True)
            details, err = fetch_one(session, num)
            if err:
                # Both a clean "not found" and an empty-body 200 mean the
                # number is genuinely delisted, not a transient fetch error
                # -- flag it so the site can still show a status badge.
                if err == "not_found" or err.startswith("quicksearch_error: empty_response"):
                    lookup[num] = {"model_status": "Delisted"}
                    print("delisted")
                else:
                    print(err)
            else:
                fields = extract_fields(details)
                if fields.get("brand") or fields.get("model"):
                    lookup[num] = fields
                    print(f"ok ({fields.get('brand')} {fields.get('model')})")
                else:
                    print("no brand/model found")
            time.sleep(DELAY_SECONDS)

    OUT_PATH.parent.mkdir(exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(lookup, f, ensure_ascii=False, separators=(",", ":"))

    print(f"\nwrote {OUT_PATH} -- {len(lookup)}/{len(numbers)} numbers resolved")


if __name__ == "__main__":
    main()
