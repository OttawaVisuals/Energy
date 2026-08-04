"""
NEEP product-page extract for the 9 tier-cell units (companion to build_cell_curves.py).

WHY THIS EXISTS
----------------
build_cell_curves.py digitizes each tier-cell unit's manufacturer datasheet --
mostly the MAX-speed/output column (see its UNITS[...]["source"] notes), not
AHRI's own "Rated" (nameplate) column. To show that Rated-vs-Max gap on the
tier_scatter.html spec table, we need real AHRI-certified Min/Rated/Max points
at more than the two temperatures hp_units_joined.csv carries (cop @5F,
c47 @47F). NEEP's own product pages republish the AHRI directory's full
Heating performance table (Min/Rated/Max x Btu/h/kW/COP at 47F, 17F, 5F, and
one colder extreme per unit) -- richer, and it's the same AHRI certificate
data, not a third-party estimate.

INPUT
-----
  data/raw/neep/neep_extract_tier_units_2026-08-04.xlsx
      Manually pulled from neep.org product pages (one page per unit, pasted
      into one sheet back-to-back) -- 8 of the 9 tier-cell units have a NEEP
      listing; Cooper & Hunter (low_<18k, AHRI 205263878) does not.

OUTPUT
------
  data/interim/neep_extract.json   keyed by AHRI certificate number:
      brand, outdoor_model, indoor_model,
      capacity_maintenance: {rated_17_47, rated_5_47, max_5_47}
      heating: [ {outdoor_F, outdoor_C, min:{btuh,kw,cop}, rated:{...}, max:{...}} ... ]
      (rated/min/max sub-dict values are None where NEEP shows "-")

METHOD
------
Each product page is a flat run of (label, value, ...) rows. We anchor on
"AHRI Certificate #" rows to split pages apart, then read forward to the
"Performance Specs" table and take only the Heating blocks (each: one Btu/h
row + one kW row + one COP row, in that fixed order) up to the next page's
brand row or EOF.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import openpyxl

HERE = Path(__file__).resolve().parent
SRC = HERE.parent / "data" / "raw" / "neep" / "neep_extract_tier_units_2026-08-04.xlsx"
OUT = HERE.parent / "data" / "interim" / "neep_extract.json"

F_TO_C = lambda f: round((f - 32) * 5 / 9, 2)


def _num(v):
    if v is None or v == "-":
        return None
    return float(v)


def main():
    wb = openpyxl.load_workbook(SRC, data_only=True)
    ws = wb["Sheet1"]
    rows = [[c for c in row] for row in ws.iter_rows(values_only=True)]

    # find each page's start: the summary "AHRI Cert #+:<num>" row at the top
    # of the page (NOT "AHRI Certificate #+" -- that's a later info-table row,
    # anchoring on it would cut off Brand/Series which appear before it).
    page_starts = [i for i, r in enumerate(rows)
                    if isinstance(r[0], str) and r[0].startswith("AHRI Cert #")]

    units = {}
    for n, start in enumerate(page_starts):
        end = page_starts[n + 1] if n + 1 < len(page_starts) else len(rows)
        block = rows[start:end]
        ahri = str(int(re.search(r"\d+", block[0][0]).group()))

        def field(label):
            for r in block:
                if r[0] == label:
                    return r[1]
            return None

        cm = {
            "rated_17_47": _num(field("Capacity Maintenance (Rated 17°F/Rated 47°F)")),
            "rated_5_47": _num(field("Capacity Maintenance (Rated 5°F/Rated 47°F)")),
            "max_5_47": _num(field("Capacity Maintenance (Max 5°F/Rated 47°F)")),
        }

        # Performance Specs table: header row then repeating
        # ('Heating'/'Cooling', outdoor_F, indoor_F, 'Btu/h+', min, rated, max)
        # (None,None,None,'kW',min,rated,max)  (None,None,None,'COP',min,rated,max)
        heating = []
        i = 0
        while i < len(block):
            r = block[i]
            if r[0] == "Heating" and isinstance(r[1], str):
                outdoor_f = float(re.match(r"-?\d+", r[1].replace("℉", "")).group())
                btuh = block[i][4:7]
                kw = block[i + 1][4:7]
                cop = block[i + 2][4:7]
                heating.append({
                    "outdoor_F": outdoor_f,
                    "outdoor_C": F_TO_C(outdoor_f),
                    "min": {"btuh": _num(btuh[0]), "kw": _num(kw[0]), "cop": _num(cop[0])},
                    "rated": {"btuh": _num(btuh[1]), "kw": _num(kw[1]), "cop": _num(cop[1])},
                    "max": {"btuh": _num(btuh[2]), "kw": _num(kw[2]), "cop": _num(cop[2])},
                })
                i += 3
            else:
                i += 1

        units[ahri] = {
            "brand": field("Brand"),
            "outdoor_model": field("Outdoor Unit Model #⁺"),
            "indoor_model": field("Indoor Model #⁺"),
            "capacity_maintenance": cm,
            "heating": heating,
        }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"units": units}, indent=2), encoding="utf-8")
    print(f"wrote {OUT} -- {len(units)} units")
    for ahri, u in units.items():
        temps = [h["outdoor_F"] for h in u["heating"]]
        print(f"  {ahri}  {u['brand']:10s} {u['outdoor_model']:22s} heating pts: {temps}")


if __name__ == "__main__":
    main()
