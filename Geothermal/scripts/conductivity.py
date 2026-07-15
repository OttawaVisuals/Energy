"""
conductivity.py

Shared thermal-conductivity reference for the geothermal pipeline. Reads the
literature-sourced per-bucket table Geothermal/Data/conductivity_reference.csv
(VDI 4640 Blatt 1:2010 ranges + ASHRAE / Banks corroboration -- see the CSV's
`source` column and README "Conductivity assumptions & sources").

CONDUCTIVITY_WM_FALLBACK below is the built-in used only if the CSV is missing;
the CSV is authoritative when present. BUCKET_ORDER fixes the canonical bucket
index (0-13) used across interpolate_conductivity.py, merge_layers.py,
build_map.py and the map UI, so an index means the same bucket everywhere.
"""

import csv
from pathlib import Path

REF_CSV = Path(__file__).resolve().parents[1] / "Data" / "conductivity_reference.csv"

# Canonical bucket order == the row order of conductivity_reference.csv, which in
# turn matches combine_wells.py's original CONDUCTIVITY_WM dict. Index into this
# list is the bucket id embedded in the map's compact tuples.
BUCKET_ORDER = ["limestone", "dolostone", "sandstone", "shale", "granite",
                "gneiss", "clay", "silt", "sand", "gravel", "till", "fill",
                "basalt", "rock"]

# Fallback only (used when the CSV can't be read). Mirrors the CSV defaults.
CONDUCTIVITY_WM_FALLBACK = {
    "limestone": 2.8, "dolostone": 3.0, "sandstone": 2.3, "shale": 1.9,
    "granite": 3.2, "gneiss": 3.0, "clay": 1.4, "silt": 1.5, "sand": 2.4,
    "gravel": 2.0, "till": 1.8, "fill": 1.5, "basalt": 2.0, "rock": 2.5,
}


def load_reference(path: Path = REF_CSV):
    """Return (defaults, ref).

    defaults : {bucket: default_wmk}  -- the CONDUCTIVITY_WM map, from the CSV
               when present else CONDUCTIVITY_WM_FALLBACK.
    ref      : {bucket: {default,min,max,notes,source}} or None if no CSV.
    """
    if not path.exists():
        print(f"  [conductivity] {path.name} not found -- using built-in fallback")
        return dict(CONDUCTIVITY_WM_FALLBACK), None
    ref = {}
    with open(path, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            b = r["bucket"].strip()
            ref[b] = {
                "default": float(r["default_wmk"]),
                "min": float(r["min_wmk"]),
                "max": float(r["max_wmk"]),
                "notes": r.get("notes", ""),
                "source": r.get("source", ""),
            }
    defaults = {b: ref[b]["default"] for b in ref}
    # keep any fallback-only buckets that somehow aren't in the CSV
    for b, v in CONDUCTIVITY_WM_FALLBACK.items():
        defaults.setdefault(b, v)
    print(f"  [conductivity] loaded {len(ref)} buckets from {path.name}")
    return defaults, ref
