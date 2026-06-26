"""
build_window_lookup.py

Decodes HOT2000 WINDOWCODE values into readable descriptions using the
digit-position lookup tables in Support.xlsx (Frame/Window/Spacer/Fill/
Coating/Glazing sheets), and writes lookup/window_codes.json in the format
retrofits.html's decodeWindow() already expects: { "<code>": "Description" }.

WINDOWCODE digit layout (left to right, confirmed against real data — e.g.
code 200004 = Double-glazed, Clear, 13mm air, Metal spacer, Picture window,
Vinyl frame):
  digit 1 -> Glazing      (Glazing sheet)
  digit 2 -> Coating/Tint (Coating sheet)
  digit 3 -> Fill         (Fill sheet)
  digit 4 -> Spacer       (Spacer sheet)
  digit 5 -> Window type  (Window sheet)
  digit 6 -> Frame        (Frame sheet)

Only codes that actually appear in the site's data are decoded (collected
from every province_json/*.json's window_pre_counts/window_post_counts —
the "All types" slice already covers every code in that province, since
it's built from the same parquet fsa_json is split from), not the full
cartesian product of all possible codes.

Uses only the standard library (zipfile + ElementTree) — no openpyxl/pandas
dependency, consistent with extract_fsa_census.py.
"""

import glob
import json
import os
import zipfile
import xml.etree.ElementTree as ET

SUPPORT_XLSX = "Support.xlsx"
PROVINCE_JSON_DIR = "province_json"
OUT_PATH = os.path.join("lookup", "window_codes.json")
COMPONENTS_OUT_PATH = os.path.join("lookup", "window_components.json")

# Position -> attribute name, used as keys in window_components.json so the
# frontend can decode a code into named parts (for the "what changed
# pre->post" comparison) instead of just a single description string.
POSITION_NAMES = {1: "glazing", 2: "coating", 3: "fill", 4: "spacer", 5: "window_type", 6: "frame"}

NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
      "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships"}

# digit position (1-indexed) -> sheet name
DIGIT_SHEETS = {1: "Glazing", 2: "Coating", 3: "Fill", 4: "Spacer", 5: "Window", 6: "Frame"}


def load_shared_strings(z):
    root = ET.fromstring(z.read("xl/sharedStrings.xml"))
    out = []
    for si in root.findall("m:si", NS):
        out.append("".join(t.text or "" for t in si.findall(".//m:t", NS)))
    return out


def sheet_name_to_path(z):
    wb = ET.fromstring(z.read("xl/workbook.xml"))
    rels = ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
    rid_to_target = {
        rel.get("Id"): rel.get("Target")
        for rel in rels.findall("{http://schemas.openxmlformats.org/package/2006/relationships}Relationship")
    }
    out = {}
    for sheet in wb.findall(".//m:sheets/m:sheet", NS):
        rid = sheet.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id")
        target = rid_to_target.get(rid, "")
        out[sheet.get("name")] = "xl/" + target.lstrip("/")
    return out


def read_sheet_rows(z, path, strings):
    root = ET.fromstring(z.read(path))
    rows = []
    for row in root.findall(".//m:sheetData/m:row", NS):
        cells = []
        for c in row.findall("m:c", NS):
            t = c.get("t")
            v = c.find("m:v", NS)
            val = v.text if v is not None else ""
            if t == "s" and val != "":
                val = strings[int(val)]
            cells.append(val)
        rows.append(cells)
    return rows


def load_digit_table(z, strings, sheet_path):
    """Each of the 6 dedicated sheets is a simple Value/Category table."""
    rows = read_sheet_rows(z, sheet_path, strings)
    table = {}
    for row in rows[1:]:  # skip header row ("Value","Category")
        if len(row) >= 2 and row[0] != "":
            table[str(row[0]).strip()] = row[1].strip()
    return table


def collect_window_codes():
    codes = set()
    for pf in glob.glob(os.path.join(PROVINCE_JSON_DIR, "*.json")):
        with open(pf, encoding="utf-8") as f:
            data = json.load(f)
        slice_ = data.get("by_type", {}).get("All types", {})
        for key in ("window_pre_counts", "window_post_counts"):
            codes.update(slice_.get(key, {}).keys())
    return codes


def decode_code(code, tables):
    s = str(code).strip().zfill(6)
    if len(s) != 6:
        return None  # irregular/junk code — leave undecoded, frontend falls back to raw
    parts = []
    for pos in range(1, 7):
        digit = s[pos - 1]
        category = tables[pos].get(digit)
        if category is None:
            return None
        parts.append(category)
    glazing, coating, fill, spacer, window_type, frame = parts
    return f"{glazing} glazing, {coating} coating, {fill} fill, {spacer} spacer, {window_type.lower()}, {frame.lower()} frame"


def main():
    with zipfile.ZipFile(SUPPORT_XLSX) as z:
        strings = load_shared_strings(z)
        sheet_paths = sheet_name_to_path(z)
        tables = {
            pos: load_digit_table(z, strings, sheet_paths[name])
            for pos, name in DIGIT_SHEETS.items()
        }

    codes = collect_window_codes()
    print(f"found {len(codes)} distinct window codes across province_json/*.json")

    out = {}
    skipped = []
    for code in sorted(codes):
        desc = decode_code(code, tables)
        if desc:
            out[code] = desc
        else:
            skipped.append(code)

    if skipped:
        print(f"  could not decode {len(skipped)} code(s) (non-6-digit or unknown digit value): {skipped[:20]}")

    os.makedirs("lookup", exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
    print(f"wrote {OUT_PATH} — {len(out)} decoded codes")

    # Per-digit value->category tables, keyed by attribute name, so the
    # frontend can decode any code into its 6 named parts and compare two
    # codes (pre vs post) attribute-by-attribute, not just as whole strings.
    components = {POSITION_NAMES[pos]: table for pos, table in tables.items()}
    with open(COMPONENTS_OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(components, f, ensure_ascii=False, separators=(",", ":"))
    print(f"wrote {COMPONENTS_OUT_PATH}")


if __name__ == "__main__":
    main()
