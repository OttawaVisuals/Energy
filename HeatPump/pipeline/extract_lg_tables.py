"""
extract_lg_tables.py — Phase 3c: LG engineering-manual performance tables.

Third of the datasheet parsers. LG publishes full performance data in its
Engineering Manuals (NOT in the 2-3 page submittals, which carry rated points
only -- an easy and costly thing to conclude too early). The layout is a third
distinct shape:

    Table 26: LAN090HYV3/LAU090HYV3 Maximum Heating Capacities.
    Outdoor Air Temp.        Indoor Air Temperature (°F DB)
    °F DB  °F WB     60      64      68      70      72      75      86
                   TC  PI  TC  PI  TC  PI  TC  PI  TC  PI  TC  PI  TC  PI
      -12    -13  7.94 0.91 7.97 0.91 8.00 0.92 8.03 0.92 ...

Outdoor temperature is the ROW (given as dry-bulb and wet-bulb), indoor
temperature is a COLUMN GROUP, and each group is a (TC, PI) pair -- total
capacity in kBtu/h and power input in kW. COP is derived as TC/(3.412 x PI).

Two things that will bite:

  1. **Several models share a page.** Page 42 of the Art Cool Premier manual
     holds LA090HYV3 *and* LA120HYV3 tables back to back. Selection is by the
     `Table NN: <models> Maximum Heating Capacities` caption that PRECEDES each
     block, so `--model-caption LAU120HYV3` picks the right one. Taking the
     first table on the page silently gives you the wrong unit.
  2. **The manual's body font is custom-encoded**, so much of the surrounding
     prose extracts as mojibake. The tables themselves are fine -- do not take
     unreadable page text as evidence that the data is absent.

Indoor 70 °F DB is the default column: the standard heating rating condition,
matching the other extractors and AHRI's own basis.

Usage:
    python pipeline/extract_lg_tables.py <pdf> --ahri <n> --model-caption LAU120HYV3
        --outdoor-model LAU120HYV3 --brand LG [--indoor-temp-f 70] [--min-op-temp-f -13]

Output: merged into data/interim/datasheet_points_v2.json.
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

INDOOR_COLUMNS = [60, 64, 68, 70, 72, 75, 86]
# <outdoor DB> <outdoor WB> then 7 (TC, PI) pairs = 14 decimals
ROW_RE = re.compile(r"^\s*(-?\d+)\s+(-?\d+)\s+((?:-?\d+\.\d+\s+){13}-?\d+\.\d+)\s*$")
CAPTION_RE = re.compile(r"Table\s+\d+:\s*([^\n]*?)\s*Maximum Heating Capacit", re.I)


def parse(pdf_path, model_caption, indoor_temp_f):
    try:
        col = INDOOR_COLUMNS.index(indoor_temp_f)
    except ValueError:
        return [], f"indoor {indoor_temp_f}F is not one of {INDOOR_COLUMNS}"

    text = "\n".join((p.extract_text() or "") for p in PdfReader(pdf_path).pages)

    # Split into caption-delimited blocks and keep the one naming our model.
    marks = [(m.start(), m.group(1)) for m in CAPTION_RE.finditer(text)]
    if not marks:
        return [], "no 'Maximum Heating Capacities' table captions found"

    # CAPTION FOLLOWS ITS TABLE. Verified on the Art Cool Premier manual p.42:
    # the LA090 data rows come first, then "Table 26: LAN090HYV3/LAU090HYV3
    # Maximum Heating Capacities.", then the LA120 rows, then Table 27's caption.
    # Reading the text AFTER a caption therefore returns the NEXT model's table --
    # which silently produced LA150 data for LAU120HYV3 until this was caught by
    # checking the 5 F capacity against the model's published max (13,600 Btu/h).
    # The block for caption i runs from the end of caption i-1 to the start of i.
    block = None
    for i, (pos, caption) in enumerate(marks):
        if model_caption.upper() in caption.upper():
            start = marks[i - 1][0] if i > 0 else 0
            block = text[start:pos]
            break
    if block is None:
        found = "; ".join(c for _, c in marks)[:200]
        return [], f"model {model_caption} not in any caption. Captions: {found}"

    rows = []
    for line in block.splitlines():
        m = ROW_RE.match(line)
        if not m:
            continue
        odb = int(m.group(1))
        vals = [float(x) for x in m.group(3).split()]
        tc, pi = vals[col * 2], vals[col * 2 + 1]
        if pi > 0:
            cap_btu = tc * 1000.0
            rows.append((odb, cap_btu, cap_btu / (BTU_PER_KWH * pi), pi))
    rows.sort()
    if len(rows) < 5:
        return [], f"only {len(rows)} data rows parsed from the matched block"
    return rows, None


def f_to_c(f):
    return (f - 32.0) * 5.0 / 9.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf")
    ap.add_argument("--ahri", required=True)
    ap.add_argument("--model-caption", required=True,
                    help="model string as it appears in the table caption")
    ap.add_argument("--outdoor-model", required=True)
    ap.add_argument("--brand", default="LG")
    ap.add_argument("--indoor-temp-f", type=int, default=70)
    ap.add_argument("--min-op-temp-f", type=float, default=None)
    ap.add_argument("--refrigerant", default=None)
    ap.add_argument("--doc", default="")
    args = ap.parse_args()

    rows, err = parse(args.pdf, args.model_caption, args.indoor_temp_f)
    if err:
        print(f"FAILED: {err}", file=sys.stderr)
        return 1

    cap47 = next((c for f, c, _, _ in rows if f == 47), None)
    entry = {
        "ahri_number": args.ahri,
        "outdoor_model": args.outdoor_model,
        "brand": args.brand,
        "refrigerant": args.refrigerant,
        "doc": args.doc or Path(args.pdf).name,
        "defrost_inclusive": False,
        "basis": f"engineering manual max heating, indoor {args.indoor_temp_f}F DB",
        "rated_cap_47_kW": round(cap47 / BTU_PER_KWH, 4) if cap47 else None,
        "min_op_temp_C": (round(f_to_c(args.min_op_temp_f), 2)
                          if args.min_op_temp_f is not None
                          else round(f_to_c(rows[0][0]), 2)),
        "points": [
            {
                "T_C": round(f_to_c(f), 2),
                "cap_kW": round(cap / BTU_PER_KWH, 4),
                "COP": round(cop, 3),
                "power_kW": round(pi, 4),
                "src": f"eng manual {f}F DB: {cap/1000:.2f} kBtu/h, {pi} kW (COP derived)",
            }
            for f, cap, cop, pi in rows
        ],
    }

    data = {}
    if OUT_PATH.exists():
        data = json.loads(OUT_PATH.read_text(encoding="utf-8"))
    data.setdefault("units", {})[args.ahri] = entry
    OUT_PATH.write_text(json.dumps(data, indent=1), encoding="utf-8")

    print(f"AHRI {args.ahri} — {args.brand} {args.outdoor_model}")
    print(f"  {len(rows)} points, {rows[0][0]}F..{rows[-1][0]}F "
          f"({f_to_c(rows[0][0]):.1f}..{f_to_c(rows[-1][0]):.1f} C)")
    print(f"  COP derived, range {min(r[2] for r in rows):.2f}..{max(r[2] for r in rows):.2f}")
    print(f"  min_op_temp_C = {entry['min_op_temp_C']}   wrote {OUT_PATH.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
