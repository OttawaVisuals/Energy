"""
extract_fsa_census.py

Pulls a small set of housing-stock characteristics per FSA out of the
StatCan 2021 Census Profile FSA-level CSV (Census/98-401-X2021013_English_
CSV_data.csv — long format, one row per (FSA, characteristic), ~2,631
characteristics x 1,646 FSAs) and writes one compact JSON keyed by FSA code.

Selected characteristics (see CHAR_MAP below for the exact CHARACTERISTIC_ID
-> output-field mapping):
  - Total private dwellings
  - Dwelling type (single-detached, semi, row, duplex apt, low/high-rise
    apt, other single-attached, movable)
  - Tenure (owner / renter)
  - Period of construction (8 bands, 1960-or-before .. 2016-2021)
  - Dwelling condition (minor vs major repairs needed)
  - Owner stats (% with mortgage, % spending 30%+ on shelter, % in core
    housing need, median/average shelter cost, median/average dwelling value)

INPUT:  Census/98-401-X2021013_English_CSV_data.csv  (latin-1 encoded)
OUTPUT: census_json/fsa_census.json  -> { "<FSA>": { ...fields... }, ... }

Each FSA's block is a fixed 2,631 consecutive rows (verified: 1,646 FSAs x
2,631 rows + 1 header row = 4,330,627 total lines), so this reads the file
once sequentially rather than doing 1,646 random-access seeks.

Suppressed/unavailable cells (StatCan symbols x, F, E, r, rE, "..", "...",
or blank) become JSON null rather than a string sentinel, so the frontend's
existing num()-style helpers can treat them like any other missing value.
"""

import csv
import json
import os

CENSUS_CSV = os.path.join("Census", "98-401-X2021013_English_CSV_data.csv")
OUT_DIR = "census_json"
OUT_PATH = os.path.join(OUT_DIR, "fsa_census.json")

ROWS_PER_FSA = 2631

# CHARACTERISTIC_ID -> (group, field). Group=None means top-level field.
CHAR_MAP = {
    4: (None, "total_dwellings"),
    42: ("dwelling_type", "single_detached"),
    43: ("dwelling_type", "semi_detached"),
    44: ("dwelling_type", "row_house"),
    45: ("dwelling_type", "duplex_apt"),
    46: ("dwelling_type", "apt_low_rise"),
    47: ("dwelling_type", "apt_high_rise"),
    48: ("dwelling_type", "other_single_attached"),
    49: ("dwelling_type", "movable"),
    1415: ("tenure", "owner"),
    1416: ("tenure", "renter"),
    1441: ("period_of_construction", "1960_or_before"),
    1442: ("period_of_construction", "1961_1980"),
    1443: ("period_of_construction", "1981_1990"),
    1444: ("period_of_construction", "1991_2000"),
    1445: ("period_of_construction", "2001_2005"),
    1446: ("period_of_construction", "2006_2010"),
    1447: ("period_of_construction", "2011_2015"),
    1448: ("period_of_construction", "2016_2021"),
    1450: ("condition", "minor_repairs"),
    1451: ("condition", "major_repairs"),
    1482: ("owner_stats", "owner_households_total"),
    1483: ("owner_stats", "pct_with_mortgage"),
    1484: ("owner_stats", "pct_spending_30pct_shelter"),
    1485: ("owner_stats", "pct_core_housing_need"),
    1486: ("owner_stats", "median_shelter_cost"),
    1487: ("owner_stats", "average_shelter_cost"),
    1488: ("owner_stats", "median_dwelling_value"),
    1489: ("owner_stats", "average_dwelling_value"),
}

GROUPS = ["dwelling_type", "tenure", "period_of_construction", "condition", "owner_stats"]


def parse_value(s):
    """StatCan suppression/availability symbols (x, F, E, r, rE, .., ...) and
    blanks all become None; everything else is a plain int or float."""
    if s is None:
        return None
    s = s.strip()
    if s == "" or s in {"x", "F", "E", "r", "rE", "..", "..."}:
        return None
    try:
        f = float(s)
    except ValueError:
        return None
    return int(f) if f.is_integer() else round(f, 2)


def empty_record():
    rec = {field: None for group, field in CHAR_MAP.values() if group is None}
    for g in GROUPS:
        rec[g] = {field: None for grp, field in CHAR_MAP.values() if grp == g}
    return rec


def main():
    out = {}
    with open(CENSUS_CSV, encoding="latin-1", newline="") as f:
        reader = csv.reader(f)
        next(reader)  # header

        block = []
        for row in reader:
            block.append(row)
            if len(block) < ROWS_PER_FSA:
                continue

            fsa = block[0][2]  # ALT_GEO_CODE, e.g. "A0A"
            rec = empty_record()
            for row in block:
                try:
                    cid = int(row[8])
                except (ValueError, IndexError):
                    continue
                mapping = CHAR_MAP.get(cid)
                if not mapping:
                    continue
                group, field = mapping
                value = parse_value(row[11])
                if group is None:
                    rec[field] = value
                else:
                    rec[group][field] = value
            out[fsa] = rec
            block = []

        if block:
            print(f"  !! trailing partial block of {len(block)} rows ignored (expected multiple of {ROWS_PER_FSA})")

    os.makedirs(OUT_DIR, exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(out, f, separators=(",", ":"))
    size_kb = os.path.getsize(OUT_PATH) / 1024
    print(f"wrote {OUT_PATH} — {len(out):,} FSAs ({size_kb:.0f} KB)")


if __name__ == "__main__":
    main()
