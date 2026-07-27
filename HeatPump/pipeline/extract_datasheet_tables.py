"""
extract_datasheet_tables.py — Phase 3c: manufacturer "extended ratings" tables.

Parses the HEATING PERFORMANCE / EXTENDED RATINGS table out of a hand-fetched
manufacturer submittal PDF into the per-unit points format the curve builder
consumes, keyed by AHRI certified reference number.

WHY THIS EXISTS
---------------
Some manufacturers publish a full heating performance table -- capacity, COP AND
power input at 20+ outdoor temperatures, at maximum output. That is exactly what
the engine needs and it is strictly better than anything AHRI, ENERGY STAR or
NRCan carry (AHRI publishes 3 capacity points and ONE COP). Where such a table
exists, no other source is required for that unit.

A caution learned the hard way (2026-07-26): these tables are easy to MISS.
In the GREE FLEXX Ultra submittal the table extracts as bare numbers with the
column headers detached at the foot of the page, so a keyword scan for
"Power Input" or "COP" against the page text finds nothing useful and the
document looks like it has no performance data. ALWAYS dump the full text of
every page before concluding a datasheet lacks a table.

LAYOUT NOTE
-----------
The GREE-family sheets interleave two tables on one page -- cooling on the left,
heating on the right -- so a row reads:

    5°F 36000 68.5% 16.29 2210   -22°F 18400 1.30 4150
    <-------- cooling -------->  <----- heating ----->

The heating quadruple is (outdoor °F, total capacity Btu/h, COP, power input W).
Cooling rows carry a percent sign (SHR) and an EER instead, so matching a strict
"int F / int / x.xx / int" quadruple selects heating rows only. The extracted COP
is cross-checked against capacity / (3.412 x power); a mismatch means the columns
were misread and the unit is rejected rather than silently written out.

Usage:
    python pipeline/extract_datasheet_tables.py <pdf> --ahri <number> \
        --model <outdoor model> --brand <brand> [--page N] [--min-op-temp-f F]

Output:
    data/interim/datasheet_points_v2.json   merged, one entry per AHRI number
"""

import argparse
import json
import re
import sys
from pathlib import Path

from pypdf import PdfReader

ROOT = Path(__file__).resolve().parent.parent
OUT_PATH = ROOT / "data" / "interim" / "datasheet_points_v2.json"

BTU_PER_KWH = 3412.14
# COP = capacity(Btu/h) / (3.412 x power(W)). Tolerance for datasheet rounding.
COP_CHECK_TOL = 0.03

# (outdoor F) (capacity Btu/h) (COP) (power W)
ROW_RE = re.compile(r"(-?\d+)F (\d{4,6}) (\d\.\d\d) (\d{3,5})")


def f_to_c(f):
    return (f - 32.0) * 5.0 / 9.0


def extract_rows(pdf_path, page=None):
    """Return sorted [(F, Btu/h, COP, W)] from the first page that yields rows."""
    reader = PdfReader(pdf_path)
    pages = [reader.pages[page - 1]] if page else reader.pages
    for p in pages:
        text = (p.extract_text() or "").replace("°", "")  # strip degree sign
        flat = re.sub(r"\s+", " ", text)
        rows = sorted({
            (int(a), int(b), float(c), int(d))
            for a, b, c, d in ROW_RE.findall(flat)
        })
        # Plausible heating table: several points, spanning sub-freezing weather.
        if len(rows) >= 5 and rows[0][0] <= 32:
            return rows
    return []


def validate(rows):
    """Reject a parse whose COP column is inconsistent with capacity and power."""
    bad = []
    for f, cap, cop, w in rows:
        recomputed = cap / (BTU_PER_KWH / 1000.0 * w)
        if abs(recomputed - cop) > COP_CHECK_TOL:
            bad.append((f, cop, round(recomputed, 3)))
    return bad


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf")
    ap.add_argument("--ahri", required=True)
    ap.add_argument("--model", required=True)
    ap.add_argument("--brand", required=True)
    ap.add_argument("--doc", default="", help="citation string for the source PDF")
    ap.add_argument("--page", type=int, default=None)
    ap.add_argument("--refrigerant", default=None)
    ap.add_argument("--min-op-temp-f", type=float, default=None,
                    help="published heating lock-out, deg F (e.g. -22)")
    ap.add_argument("--defrost-inclusive", action="store_true")
    args = ap.parse_args()

    rows = extract_rows(args.pdf, args.page)
    if not rows:
        print("No heating performance table found. Dump every page's text before "
              "concluding the datasheet has none -- these tables often extract as "
              "bare numbers with detached headers.", file=sys.stderr)
        return 1

    bad = validate(rows)
    if bad:
        print(f"COP column failed the capacity/power cross-check at {len(bad)} "
              f"point(s), e.g. {bad[:3]} (stated vs recomputed). Columns were "
              f"probably misread; not writing.", file=sys.stderr)
        return 1

    cap47 = next((c for f, c, _, _ in rows if f == 47), None)
    entry = {
        "ahri_number": args.ahri,
        "outdoor_model": args.model,
        "brand": args.brand,
        "refrigerant": args.refrigerant,
        "doc": args.doc or Path(args.pdf).name,
        "defrost_inclusive": bool(args.defrost_inclusive),
        "basis": "maximum heating output",
        "rated_cap_47_kW": round(cap47 / BTU_PER_KWH, 4) if cap47 else None,
        "min_op_temp_C": (round(f_to_c(args.min_op_temp_f), 2)
                          if args.min_op_temp_f is not None
                          else round(f_to_c(rows[0][0]), 2)),
        "points": [
            {
                "T_C": round(f_to_c(f), 2),
                "cap_kW": round(cap / BTU_PER_KWH, 4),
                "COP": cop,
                "power_kW": round(w / 1000.0, 4),
                "src": f"datasheet {f}F: {cap} Btu/h, COP {cop}, {w} W",
            }
            for f, cap, cop, w in rows
        ],
    }

    data = {}
    if OUT_PATH.exists():
        data = json.loads(OUT_PATH.read_text(encoding="utf-8"))
    data.setdefault("note", (
        "Heating performance digitized from PRIMARY public manufacturer "
        "datasheets (submittal / extended ratings), at MAXIMUM heating output. "
        "Keyed by AHRI certified reference number. Capacity kW, temps C, power kW. "
        "COP cross-checked against capacity/(3.412*power) on load."
    ))
    data.setdefault("units", {})
    data["units"][args.ahri] = entry

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(data, indent=1), encoding="utf-8")

    lo, hi = rows[0], rows[-1]
    print(f"AHRI {args.ahri} — {args.brand} {args.model}")
    print(f"  {len(rows)} points, {lo[0]}F..{hi[0]}F "
          f"({f_to_c(lo[0]):.1f}..{f_to_c(hi[0]):.1f} C)")
    print(f"  COP cross-check passed on all {len(rows)} points")
    print(f"  min_op_temp_C = {entry['min_op_temp_C']}")
    print(f"  wrote {OUT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
