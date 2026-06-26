"""
list_ahri_numbers.py

Lists every distinct AHRI number that can actually appear on the website,
for manual brand/model lookup (no public AHRI directory file exists yet —
see Python/build_window_lookup.py's window-code equivalent, which used
Support.xlsx; there's no AHRI analogue of that file).

"Appears on the website" = the union of:
  - every province_json/<PROV>.json's top_ahri_numbers (province-wide view)
  - every fsa_json/<PROV>/<FSA>.json's Pre_HPAHRI/Post_HPAHRI values
    (FSA-level view — these are already masked to each province's own top 5
    by split_fsa_json.py, so in practice this is a subset of the province
    list above, but both are scanned directly rather than assumed, in case
    that masking logic ever changes)
CA.json is excluded from the union scan (it's a derived aggregate of the
12 provinces, not a new source of numbers) but used to confirm the national
top 5 separately, included in the output for reference.

For each distinct number, the total occurrence count is summed from each
province's own (full, not top-N) ahri_counts field — excluding CA.json,
to avoid double-counting since CA's counts are already a sum of the rest.

OUTPUT: ahri_numbers_seen.json — a list of {number, total_count}, sorted by
count descending, plus a separate "canada_top_5" field for reference.
"""

import glob
import json
import os

PROVINCE_JSON_DIR = "province_json"
FSA_JSON_DIR = "fsa_json"
OUT_PATH = "ahri_numbers_seen.json"


def main():
    province_files = sorted(glob.glob(os.path.join(PROVINCE_JSON_DIR, "*.json")))
    seen = set()
    total_counts = {}
    canada_top_5 = []

    for pf in province_files:
        with open(pf, encoding="utf-8") as f:
            data = json.load(f)
        slice_ = data.get("by_type", {}).get("All types", {})
        is_canada = data.get("province") == "CA"

        for entry in slice_.get("top_ahri_numbers", []):
            seen.add(entry["code"])
        if is_canada:
            canada_top_5 = slice_.get("top_ahri_numbers", [])
            continue  # don't fold CA's counts into the province total

        for code, count in slice_.get("ahri_counts", {}).items():
            total_counts[code] = total_counts.get(code, 0) + count

    fsa_files = glob.glob(os.path.join(FSA_JSON_DIR, "*", "*.json"))
    fsa_files = [p for p in fsa_files if not p.endswith("_index.json")]
    for ff in fsa_files:
        with open(ff, encoding="utf-8") as f:
            data = json.load(f)
        cols = data.get("columns", [])
        idxs = [cols.index(c) for c in ("Pre_HPAHRI", "Post_HPAHRI") if c in cols]
        if not idxs:
            continue
        for row in data.get("rows", []):
            for i in idxs:
                v = row[i]
                if v is not None and v != "":
                    seen.add(str(v))

    print(f"scanned {len(province_files)} province files + {len(fsa_files)} FSA files")
    print(f"{len(seen)} distinct AHRI numbers appear on the site")

    out_list = [
        {"number": code, "total_count": round(total_counts.get(code, 0))}
        for code in sorted(seen, key=lambda c: -total_counts.get(c, 0))
    ]

    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump({"ahri_numbers": out_list, "canada_top_5": canada_top_5}, f, indent=2)
    print(f"wrote {OUT_PATH}")


if __name__ == "__main__":
    main()
