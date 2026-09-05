"""
NEEP product-page extract for the 9 tier-cell units (companion to build_cell_curves.py).

WHY THIS EXISTS
----------------
build_cell_curves.py digitizes each tier-cell unit's manufacturer datasheet --
mostly the MAX-speed/output column (see its UNITS[...]["source"] notes), not
AHRI's own "Rated" (nameplate) column. To show that Rated-vs-Max gap on the
tier_scatter.html/heatpump.html spec tables, we need real AHRI-certified
Min/Rated/Max points at more than the two temperatures hp_units_joined.csv
carries (cop @5F, c47 @47F). NEEP's own product pages republish the AHRI
directory's full Heating AND Cooling performance tables (Min/Rated/Max x
Btu/h/kW/COP at several outdoor temperatures) -- richer, and it's the same
AHRI certificate data, not a third-party estimate.

INPUT
-----
  reference/neep/neep_pages_2026-09-05.json
      All 9 tier-cell units' NEEP "Performance Specs" tables, pulled by
      browsing the rendered ashp.neep.org product page per AHRI certificate
      (search by AHRI #, click VIEW DETAIL) -- never the site's API. Replaces
      the earlier data/raw/neep/neep_extract_tier_units_2026-08-04.xlsx
      (gitignored, local-disk-only like the rest of data/raw/ -- this file
      lives in reference/ instead so it's tracked on main, same reasoning as
      reference/spec_sheets/), which only covered heating and was missing 2
      of the 9 units (202588311 low_<18k, 202588312 mid_<18k).

OUTPUT
------
  data/interim/neep_extract.json   keyed by AHRI certificate number:
      brand, outdoor_model, indoor_model,
      capacity_maintenance: {rated_17_47, rated_5_47, max_5_47}
      heating: [ {outdoor_F, outdoor_C, min:{btuh,kw,cop}, rated:{...}, max:{...}} ... ]
      cooling: [ {outdoor_F, outdoor_C, min:{btuh,kw,cop}, rated:{...}, max:{...}} ... ]
      (rated/min/max sub-dict values are None where NEEP shows "-")

METHOD
------
Each unit's raw_specs is NEEP's Performance Specs table flattened to
tab-separated rows in on-page order: a "Heating"/"Cooling" row carrying
(outdoor_F, indoor_F, "Btu/h", min, rated, max), followed by a "kW" row and a
"COP" row in the same min/rated/max column order. Cooling blocks are read the
same way heating always was -- this script previously discarded them.
"""
from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
SRC = HERE.parent / "reference" / "neep" / "neep_pages_2026-09-05.json"
OUT = HERE.parent / "data" / "interim" / "neep_extract.json"

F_TO_C = lambda f: round((f - 32) * 5 / 9, 2)


def _num(v):
    if v is None or v == "-":
        return None
    return float(str(v).replace(",", ""))


def _parse_specs(raw_specs: str) -> dict[str, list[dict]]:
    lines = [line.split("\t") for line in raw_specs.splitlines() if line.strip()]
    out = {"heating": [], "cooling": []}
    i = 0
    while i < len(lines):
        r = lines[i]
        if r[0] in ("Heating", "Cooling"):
            kind = "heating" if r[0] == "Heating" else "cooling"
            outdoor_f = float(r[1])
            btuh = lines[i][4:7]
            kw = lines[i + 1][1:4]
            cop = lines[i + 2][1:4]
            out[kind].append({
                "outdoor_F": outdoor_f,
                "outdoor_C": F_TO_C(outdoor_f),
                "min": {"btuh": _num(btuh[0]), "kw": _num(kw[0]), "cop": _num(cop[0])},
                "rated": {"btuh": _num(btuh[1]), "kw": _num(kw[1]), "cop": _num(cop[1])},
                "max": {"btuh": _num(btuh[2]), "kw": _num(kw[2]), "cop": _num(cop[2])},
            })
            i += 3
        else:
            i += 1
    return out


def main():
    raw = json.loads(SRC.read_text(encoding="utf-8"))["units"]

    units = {}
    for ahri, u in raw.items():
        specs = _parse_specs(u["raw_specs"])
        units[ahri] = {
            "brand": u["brand"],
            "outdoor_model": u["outdoor_model"],
            "indoor_model": u["indoor_model"],
            "capacity_maintenance": u["capacity_maintenance"],
            "heating": specs["heating"],
            "cooling": specs["cooling"],
        }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"units": units}, indent=2), encoding="utf-8")
    print(f"wrote {OUT} -- {len(units)} units")
    for ahri, u in units.items():
        h_temps = [h["outdoor_F"] for h in u["heating"]]
        c_temps = [c["outdoor_F"] for c in u["cooling"]]
        print(f"  {ahri}  {u['brand']:14s} {u['outdoor_model']:22s} "
              f"heating: {h_temps}  cooling: {c_temps}")


if __name__ == "__main__":
    main()
