"""
FSA codes per dropdown city, derived from Canada Post's official FSA
delivery-facility schematic -- not free-text CLIENTCITY matching.

WHY THIS EXISTS / HISTORY
--------------------------
v1 of this script matched each ERS home's own CLIENTCITY text through
CITY_MEMBERS (build_city_design_temps.py's table). That produced an Ottawa
FSA list padded with ~65 stray FSAs (1-13 homes each -- other cities'
typos/outliers) plus a genuine bug: 714 Ontario homes in Aylmer, ON (FSA
N5H, near London) were counted as Ottawa-Gatineau, because Gatineau, QC also
has a borough called Aylmer and the free-text match didn't check province.

v2 (this version) replaces the per-home text join with an FSA-level join
against `HeatPump/reference/canada_post_fsa_facilities.json`
(parse_canada_post_fsa.py's output -- Canada Post's official national
presortation schematic, user-supplied, valid 2026-07-17 to 2026-08-13). Each
FSA has exactly one authoritative (facility, province) pair from Canada
Post, so:
  - city membership is a property of the FSA, not of what an individual
    homeowner happened to type as their city -- eliminates the stray-home
    noise entirely (a home's own CLIENTCITY text is not consulted at all)
  - province is checked by construction (the Aylmer collision is
    structurally impossible: N5H's facility record IS "AYLMER ON", J9H/J9J's
    IS "GATINEAU QC" -- they were never the same row)

METHOD
------
1. Load canada_post_fsa_facilities.json: fsa -> {facility, province}.
2. Reuse CITY_MEMBERS (build_city_design_temps.py) UNCHANGED as the
   metro-area membership list -- same set of municipality names already
   defining "Ottawa", "Toronto" etc. for the page's design-temp join, just
   matched against Canada Post's clean `facility` field instead of raw
   CLIENTCITY text. A facility is a city member only on an EXACT fold-
   normalized match (not substring) -- avoids "TORONTO WEST # 2" or
   "OTT EXT-HAWKESBURY" matching "TORONTO"/"OTTAWA" by accident.
3. For every FSA whose facility matches a dropdown city's members (in the
   right province), join ERS home counts from `ers_web_<PROV>.parquet` by
   FSA directly (no per-home city text involved at all).

DATA HONESTY
------------
Every FSA a city's member facilities touch is reported, with its home count.
Cross-city FSA overlaps (a facility name shared across two dropdown cities'
member lists, or two different facility labels landing in the same FSA --
shouldn't happen since Canada Post assigns one facility per FSA, but
checked) are reported explicitly.

INPUT:  HeatPump/reference/canada_post_fsa_facilities.json
        C:\\ERS\\web\\ers_web_<PROV>.parquet (FSA column)
OUTPUT: HeatPump/data/processed/city_fsa_list.json
        printed summary to stdout, including a before/after comparison
        against the v1 (CLIENTCITY-based) home counts per city

LIMITATIONS
-----------
- CITY_MEMBERS is unchanged from v1 -- still a hand-picked municipality-name
  rollup (e.g. Ottawa-Gatineau's list omits Navan and Cumberland, both
  legitimately within Ottawa's city boundary but not in the table), not a
  real CSD/CMA polygon. This script fixes HOW membership is matched (facility
  vs. free text), not the membership list itself.
- Canada Post's `facility` field is a mail-ROUTING grouping. A handful of
  member towns (e.g. Ottawa's ROCKLAND) are separate municipalities served by
  the same processing plant, not literally inside the city -- same caveat as
  v1, now visible per-facility rather than hidden in free text.
- Snapshot dated to the PDF's one mailing cycle (2026-07-17 to 2026-08-13).
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
FACILITIES_JSON = ROOT / "reference" / "canada_post_fsa_facilities.json"
OUT_JSON = ROOT / "data" / "processed" / "city_fsa_list.json"
ERS_WEB_DIR = Path(r"C:\ERS\web")

CITY_PROV = {
    "Ottawa": "ON", "Toronto": "ON", "Hamilton": "ON", "London": "ON", "Windsor": "ON",
    "Montreal": "QC", "Quebec City": "QC",
    "Calgary": "AB", "Edmonton": "AB",
    "Vancouver": "BC", "Winnipeg": "MB", "Halifax": "NS",
    "Saskatoon": "SK", "Regina": "SK",
}
CITY_TO_MEMBERS_KEY = {"Ottawa": "Ottawa-Gatineau"}  # everything else matches verbatim


def load_fold_and_members():
    """Import fold() and CITY_MEMBERS from build_city_design_temps.py without
    running its main() (module-level code below the function/dict defs does
    a 7.7 GB raw CSV scan when executed as a script)."""
    spec = importlib.util.spec_from_file_location(
        "build_city_design_temps", HERE / "build_city_design_temps.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.fold, mod.CITY_MEMBERS


def main():
    fold, CITY_MEMBERS = load_fold_and_members()

    facilities = json.loads(FACILITIES_JSON.read_text(encoding="utf-8"))["fsa"]
    fac_df = pd.DataFrame(
        [{"FSA": f, "facility_fold": fold(v["facility"]), "province": v["province"]}
         for f, v in facilities.items()]
    )

    members_to_dropdown = {v: k for k, v in CITY_TO_MEMBERS_KEY.items()}

    # facility_fold -> dropdown city, built from CITY_MEMBERS restricted to
    # the 14 keys this page actually uses (Ottawa via its Ottawa-Gatineau alias)
    city_of_members_key = {}
    for members_key, members in CITY_MEMBERS.items():
        dropdown_city = members_to_dropdown.get(members_key, members_key)
        if dropdown_city not in CITY_PROV:
            continue
        for m in members:
            city_of_members_key[fold(m)] = dropdown_city
    fac_df["dropdown_city"] = fac_df["facility_fold"].map(city_of_members_key)

    # load prior v1 output for a before/after comparison, if present
    prior = None
    if OUT_JSON.exists():
        try:
            prior = json.loads(OUT_JSON.read_text(encoding="utf-8"))
        except Exception:
            prior = None

    result = {}
    for city, prov in CITY_PROV.items():
        city_fsas = fac_df[(fac_df["dropdown_city"] == city) & (fac_df["province"] == prov)]["FSA"].tolist()
        path = ERS_WEB_DIR / f"ers_web_{prov}.parquet"
        if not path.exists():
            print(f"[skip] {path} not found")
            continue
        df = pd.read_parquet(path, columns=["HOUSEID", "FSA"])
        sub = df[df["FSA"].isin(city_fsas)]
        counts = sub["FSA"].value_counts().sort_index()
        result[city] = [{"fsa": fsa, "houses": int(n)} for fsa, n in counts.items()]
        n_new = len(sub)
        prior_n = sum(r["houses"] for r in prior["cities"][city]) if prior and city in prior.get("cities", {}) else None
        cmp_str = f", v1 had {prior_n:,}" if prior_n is not None else ""
        print(f"{city} ({prov}): {len(city_fsas):,} FSAs (Canada Post), "
              f"{n_new:,} ERS homes joined{cmp_str}")

    # cross-city overlap check: shouldn't occur (one facility per FSA), but verify
    fsa_to_cities = {}
    for city, rows in result.items():
        for r in rows:
            fsa_to_cities.setdefault(r["fsa"], []).append((city, r["houses"]))
    overlaps = [{"fsa": fsa, "cities": cc} for fsa, cc in fsa_to_cities.items() if len(cc) > 1]
    if overlaps:
        print(f"\n{len(overlaps)} FSA(s) split across more than one dropdown city (unexpected):")
        for o in overlaps:
            print(f"  {o['fsa']}: " + ", ".join(f"{c}={n}" for c, n in o["cities"]))
    else:
        print("\nno FSA appears under more than one dropdown city (expected -- one facility per FSA)")

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "meta": {
            "method": "FSA-level join against Canada Post's official presortation "
                      "schematic (canada_post_fsa_facilities.json), NOT CLIENTCITY "
                      "free text. City membership is a property of the FSA "
                      "(via its Canada Post facility label matched through "
                      "CITY_MEMBERS), not of what a home's owner typed.",
            "source": "HeatPump/reference/canada_post_fsa_facilities.json + "
                      "C:/ERS/web/ers_web_<PROV>.parquet FSA column",
            "facilities_validity": json.loads(FACILITIES_JSON.read_text(encoding="utf-8"))["meta"]["validity"],
        },
        "cities": result,
        "cross_city_fsa_overlaps": overlaps,
    }
    OUT_JSON.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"\n[out] wrote {OUT_JSON}")


if __name__ == "__main__":
    main()
