"""
fetch_da_census.py

Dissemination-Area (DA) level 2021 Census Profile for Ottawa, mirroring
Python/extract_fsa_census.py's FSA-level extraction but at DA granularity
(needed for building_stock.py's probabilistic vintage/type assignment --
FSA is too coarse per HEATDEMAND_PLAN.md).

Source: StatCan dataset 98-401-X2021006 ("Census Profile, 2021 Census of
Population" -- Dissemination Areas), fetched via the same bulk-CSV endpoint
extract_fsa_census.py's memory note describes (GetFile.cfm?...&GEONO=006).
No CSD-scoped bulk file exists -- the zip is split by StatCan *region*
(Ontario, Quebec, ...), each still province-wide (Ontario alone is an
8.78 GB CSV). Rather than a raw sequential stream over that whole file, this
uses the zip's own `..._Geo_starting_row_Ontario.CSV` index (Geo Code, Geo
Name, Line Number) to find exactly where Ottawa's (CD 3506) 1,392 DA blocks
start, and stream-reads only up through the last one (~4.7M of the file's
rows, not all of it) -- same "stream it, don't load whole file" discipline
as construction_etl.py's 9 GB permits CSV.

Each DA is a fixed 2,631-row block (CHARACTERISTIC_ID 1..~2712, one row per
characteristic), identical structure to the FSA file, so ROWS_PER_FSA/
CHAR_MAP carry over unchanged from extract_fsa_census.py -- StatCan keeps
characteristic IDs consistent across geography levels within the 98-401-X2021
product family.

Also requires the DA boundary geometries (2021 Digital Boundary File,
`lda_000b21a_e.zip`, national, ~198 MB) -- already fetched and clipped to
Ottawa (DAUID LIKE '3506%') at Geothermal/Data/processed/da_boundaries_ottawa.geojson
by this same session (see GEOTHERMAL_STATUS.md); this script only handles the
attribute (census profile) side.

INPUT:
    Geothermal/Data/Raw/StatCanDA/98-401-X2021006_eng_CSV.zip
        (member: 98-401-X2021006_English_CSV_data_Ontario.csv,
         98-401-X2021006_Geo_starting_row_Ontario.CSV)
OUTPUT:
    Geothermal/Data/processed/da_census.json -> { "<DAUID>": {...}, ... }
    (same field structure as census_json/fsa_census.json)

Usage:
    python Geothermal/scripts/fetch_da_census.py
"""

import csv
import io
import json
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]                       # Geothermal/
RAW = HERE / "Data" / "Raw" / "StatCanDA"
ZIP_PATH = RAW / "98-401-X2021006_eng_CSV.zip"
GEO_INDEX = RAW / "98-401-X2021006_Geo_starting_row_Ontario.CSV"
DATA_MEMBER = "98-401-X2021006_English_CSV_data_Ontario.csv"
OUT = HERE / "Data" / "processed" / "da_census.json"

ROWS_PER_BLOCK = 2631
OTTAWA_CD_PREFIX = "3506"

# Same CHARACTERISTIC_ID -> (group, field) map as Python/extract_fsa_census.py
CHAR_MAP = {
    1: (None, "population"),
    4: (None, "total_dwellings"),
    42: ("dwelling_type", "single_detached"),
    43: ("dwelling_type", "semi_detached"),
    44: ("dwelling_type", "row_house"),
    45: ("dwelling_type", "duplex_apt"),
    46: ("dwelling_type", "apt_low_rise"),
    47: ("dwelling_type", "apt_high_rise"),
    48: ("dwelling_type", "other_single_attached"),
    49: ("dwelling_type", "movable"),
    1441: ("period_of_construction", "1960_or_before"),
    1442: ("period_of_construction", "1961_1980"),
    1443: ("period_of_construction", "1981_1990"),
    1444: ("period_of_construction", "1991_2000"),
    1445: ("period_of_construction", "2001_2005"),
    1446: ("period_of_construction", "2006_2010"),
    1447: ("period_of_construction", "2011_2015"),
    1448: ("period_of_construction", "2016_2021"),
}
GROUPS = ["dwelling_type", "period_of_construction"]


def parse_value(s):
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


def load_ottawa_da_lines():
    """DAUID -> 1-based start line number, from the Geo_starting_row index."""
    das = {}
    with open(GEO_INDEX, encoding="latin-1", newline="") as f:
        r = csv.reader(f)
        next(r)
        for row in r:
            geoname = row[1]
            if geoname.isdigit() and len(geoname) == 8 and geoname.startswith(OTTAWA_CD_PREFIX):
                das[geoname] = int(row[2])
    return das


def main():
    da_lines = load_ottawa_da_lines()
    print(f"Ottawa (CD {OTTAWA_CD_PREFIX}) DAs in geo index: {len(da_lines):,}")
    last_line = max(da_lines.values()) + ROWS_PER_BLOCK  # stop reading past this
    print(f"streaming Ontario CSV up to row {last_line:,} (of an 8.78 GB file, "
          f"not read in full)")

    out = {}
    with zipfile.ZipFile(ZIP_PATH) as z, z.open(DATA_MEMBER) as raw:
        tw = io.TextIOWrapper(raw, encoding="latin-1", newline="")
        reader = csv.reader(tw)
        header = next(reader)
        assert header[2] == "ALT_GEO_CODE" and header[8] == "CHARACTERISTIC_ID"

        block = []
        line_no = 1  # header was line 1
        for row in reader:
            line_no += 1
            block.append(row)
            if len(block) < ROWS_PER_BLOCK:
                if line_no >= last_line:
                    break
                continue

            geo = block[0][2]  # ALT_GEO_CODE
            if geo in da_lines:
                rec = empty_record()
                for r in block:
                    try:
                        cid = int(r[8])
                    except (ValueError, IndexError):
                        continue
                    mapping = CHAR_MAP.get(cid)
                    if not mapping:
                        continue
                    group, field = mapping
                    value = parse_value(r[11])
                    if group is None:
                        rec[field] = value
                    else:
                        rec[group][field] = value
                out[geo] = rec

            block = []
            if line_no >= last_line:
                break

    missing = set(da_lines) - set(out)
    print(f"extracted {len(out):,} / {len(da_lines):,} Ottawa DAs"
          + (f"  (missing: {sorted(missing)[:10]}{'...' if len(missing) > 10 else ''})"
             if missing else ""))

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, separators=(",", ":"))
    print(f"wrote {OUT} ({OUT.stat().st_size / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
