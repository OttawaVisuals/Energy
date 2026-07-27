"""
refresh_ahri_lookup.py

Weekly CI refresh for lookup/ahri_numbers.json — see .github/workflows/
ahri-refresh.yml. Two things this does that build_ahri_lookup_full.py
doesn't:

  1. Runs without the raw ERS CSVs (8+ GB, local-only, never committed).
     The candidate list instead comes from Python/ahri_numbers_all.json,
     which IS committed — it's the full-corpus candidate scan that
     build_ahri_lookup_full.py already wrote out, generated locally
     whenever the ERS pipeline is refreshed (see docs/RETROFITS.md).
  2. Re-checks entries ALREADY in the lookup, not just new ones.
     build_ahri_lookup_full.py's `todo` list skips any code already present
     in lookup/ahri_numbers.json, which is correct for its one-time backfill
     job but means an entry, once resolved, is never looked at again — AHRI
     does amend individual certificates after the fact (confirmed 2026-07-22:
     AHRI 211644151's ColdClimateDesignationSearch flipped No -> Yes on
     AHRI's site while two sibling certs with the identical outdoor+indoor
     model string stayed No — see retrofit-insights.html Methodology). This
     script tags every entry it fetches with a `_checked` date and rotates
     through the oldest-checked entries so drift like that gets caught.

Priority per run, within a fixed request budget (courtesy-paced, so this
also bounds wall-clock time):
  1. Candidates from ahri_numbers_all.json never yet fetched (highest
     install-count first — same ordering build_ahri_lookup_full.py uses).
  2. Existing lookup entries whose `_checked` date is oldest (or missing
     entirely -- pre-dates this script, so due immediately).

Entries are written back with the same schema build_ahri_lookup.py /
build_ahri_lookup_full.py already use, plus one new field: `_checked`
(ISO date the entry was last verified against AHRI's API). No consumer
needs to change — decodeAhri() in retrofits.html and the tree builder in
retrofit-insights.html already only read the specific keys they need and
ignore unknown ones.

Usage:
    pip install requests
    python refresh_ahri_lookup.py
"""

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

REPO_ROOT = Path(__file__).resolve().parent.parent
CANDIDATES_PATH = REPO_ROOT / "Python" / "ahri_numbers_all.json"
LOOKUP_PATH = REPO_ROOT / "lookup" / "ahri_numbers.json"

# Request budget for one CI run: at the 1 req/sec courtesy pace below, 3000
# requests is ~50 minutes -- comfortably inside GitHub's 6h job limit for a
# weekly schedule, without hammering an undocumented internal API. Override
# via env var for a manual workflow_dispatch run with a different budget.
MAX_REQUESTS = int(os.environ.get("AHRI_REFRESH_MAX_REQUESTS", "3000"))
# How long a successfully-resolved entry is trusted before it's due for
# re-verification. Delisted-only placeholders are re-checked too (a
# certificate can be relisted), same cadence.
STALE_AFTER_DAYS = int(os.environ.get("AHRI_REFRESH_STALE_DAYS", "180"))

DELAY_SECONDS = 1.0  # be polite -- see build_ahri_lookup_full.py's docstring

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

# Identical to build_ahri_lookup_full.py's maps -- kept in sync so entries
# written by either script share one schema.
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
    # --- Added 2026-07-26 (Phase 3c). Keep in sync with the identical map in
    # build_ahri_lookup.py / build_ahri_lookup_full.py.
    "SoldIn": "sold_in",
    "SplitOrPackaged": "split_or_packaged",
    "Phase": "phase",
    "IsRerated": "is_rerated",
    "IsHSVTC": "is_hsvtc",
    "EnergyGuideLabel": "energy_guide_label",
    "manufacturertype": "manufacturer_type",
    "IndoorUnitBrandNameSearch": "indoor_brand",
    "TotalCoolingFullLoadAirVolumeRateM1": "airflow_cfm",
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


def today_iso():
    return datetime.now(timezone.utc).date().isoformat()


def days_since(iso_date):
    try:
        d = datetime.fromisoformat(iso_date).date()
    except (TypeError, ValueError):
        return None
    return (datetime.now(timezone.utc).date() - d).days


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


def build_queue(lookup, candidates):
    """Returns an ordered list of AHRI numbers to (re)fetch this run:
    never-seen candidates first (highest install count first), then
    existing entries oldest-checked-first (missing _checked sorts first)."""
    new_codes = [c["number"] for c in candidates if c["number"] not in lookup]

    existing = [num for num in lookup if num not in set(new_codes)]
    existing.sort(key=lambda num: days_since(lookup[num].get("_checked")) or 10**9, reverse=True)
    stale = [num for num in existing
             if (days_since(lookup[num].get("_checked")) or 10**9) >= STALE_AFTER_DAYS]

    return new_codes + stale


def main():
    if not CANDIDATES_PATH.exists():
        print(f"!! {CANDIDATES_PATH} not found -- run build_ahri_lookup_full.py "
              f"locally at least once to seed it (needs the raw ERS CSVs).")
        return
    candidates = json.loads(CANDIDATES_PATH.read_text(encoding="utf-8"))["ahri_numbers"]

    lookup = {}
    if LOOKUP_PATH.exists():
        lookup = json.loads(LOOKUP_PATH.read_text(encoding="utf-8"))
    print(f"{len(lookup):,} entries currently in {LOOKUP_PATH.name}, "
          f"{len(candidates):,} known candidates")

    queue = build_queue(lookup, candidates)[:MAX_REQUESTS]
    print(f"processing {len(queue):,} numbers this run "
          f"(budget {MAX_REQUESTS:,}, stale-after {STALE_AFTER_DAYS}d)\n")

    t0 = time.time()
    n_new = n_refreshed = n_changed = n_delisted = n_errors = 0
    with requests.Session() as session:
        for i, num in enumerate(queue, 1):
            was_new = num not in lookup
            prev = lookup.get(num)

            try:
                details, err = fetch_one(session, num)
            except Exception as ex:  # network blips must not kill the run
                err = f"exception: {ex}"
                details = None

            if err:
                if err == "not_found" or err.startswith("quicksearch_error: empty_response"):
                    lookup[num] = {"model_status": "Delisted", "_checked": today_iso()}
                    if was_new:
                        n_new += 1
                    else:
                        n_refreshed += 1
                        if prev and prev.get("model_status") != "Delisted":
                            n_changed += 1
                    n_delisted += 1
                    status = "delisted"
                else:
                    n_errors += 1
                    status = f"ERROR ({err}) -- will retry next run"
            else:
                fields = extract_fields(details)
                if fields.get("brand") or fields.get("model"):
                    fields["_checked"] = today_iso()
                    changed = was_new or any(prev.get(k) != v for k, v in fields.items() if k != "_checked")
                    lookup[num] = fields
                    if was_new:
                        n_new += 1
                    else:
                        n_refreshed += 1
                        if changed:
                            n_changed += 1
                    status = f"ok ({fields.get('brand')} {fields.get('model')})" + (" [CHANGED]" if changed and not was_new else "")
                else:
                    n_errors += 1
                    status = "ERROR (no brand/model found) -- will retry next run"

            if status.startswith("ok") or status == "delisted":
                atomic_write_json(LOOKUP_PATH, lookup)

            elapsed = time.time() - t0
            rate = elapsed / i
            eta_min = rate * (len(queue) - i) / 60
            print(f"[{i}/{len(queue)}] {num}: {status}  (ETA {eta_min:.0f} min)", flush=True)

            time.sleep(DELAY_SECONDS)

    print(f"\ndone. {len(lookup):,} total entries. "
          f"{n_new} new, {n_refreshed} re-checked, {n_changed} changed value, "
          f"{n_delisted} delisted, {n_errors} errors (will retry next run).")
    # Machine-readable summary line for the workflow to fold into the commit
    # message -- deliberately last, single line, stable prefix.
    print(f"AHRI_REFRESH_SUMMARY new={n_new} refreshed={n_refreshed} "
          f"changed={n_changed} delisted={n_delisted} errors={n_errors}")


if __name__ == "__main__":
    main()
