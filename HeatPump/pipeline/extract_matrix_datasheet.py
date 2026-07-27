"""
extract_matrix_datasheet.py — Phase 3c: matrix-layout performance charts.

Second of the two datasheet parsers. Where `extract_datasheet_tables.py` handles
the ROW layout (one line per outdoor temperature, as GREE publishes it), this
handles the MATRIX layout used by Midea-platform brands (MOOVAIR / Master, and
commonly MDV and other rebadges of the same hardware):

    HEATING  Outdoor conditions (DB)
    Model  Indoor Conditions   -22°F  -13°F  -4°F  ...  47°F  50°F  57°F
    <indoor model>
    <outdoor model>
      60°F (15.6°C)   TC     13.88  15.82  17.69  ...
                      Input   2.65   2.67   2.55  ...
      70°F (21.1°C)   TC     ...
                      Input  ...

Temperatures are column headers; TC (total capacity, kBtu/h) and Input (kW) are
rows, repeated per indoor return-air temperature. There is no COP column -- COP
is derived as TC / (3.412 x Input), which is exactly how the row-layout sheets
compute the COP they print, so the two sources stay consistent.

The 70 °F (21.1 °C) indoor block is selected by default: it is the standard
heating rating condition and matches the return-air basis of the row-layout
sheets and of AHRI's own 47/17/5 °F ratings.

Usage:
    python pipeline/extract_matrix_datasheet.py <pdf> --ahri <n> --outdoor-model <M>
        --brand <B> [--indoor-temp-f 70] [--min-op-temp-f -22] [--doc "..."]

Output: merged into data/interim/datasheet_points_v2.json (same schema as the
row-layout extractor, so downstream curve fitting sees one format).
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


def f_to_c(f):
    return (f - 32.0) * 5.0 / 9.0


def load_heating_section(pdf_path):
    text = "\n".join((p.extract_text() or "") for p in PdfReader(pdf_path).pages)
    idx = text.upper().find("HEATING")
    if idx < 0:
        return None
    return text[idx:]


def parse(pdf_path, outdoor_model, indoor_temp_f=70):
    sec = load_heating_section(pdf_path)
    if not sec:
        return [], "no HEATING section in text layer"

    # Column headers: the first line carrying several <n>°F tokens.
    temps = []
    for line in sec.splitlines():
        found = re.findall(r"(-?\d+)\s*°F", line)
        if len(found) >= 5:
            temps = [int(x) for x in found]
            break
    if not temps:
        return [], "could not read the outdoor-temperature header row"

    # Locate this outdoor unit's block, bounded by the next model code.
    mpos = sec.find(outdoor_model)
    if mpos < 0:
        return [], f"model {outdoor_model} not present in this document"
    rest = sec[mpos + len(outdoor_model):]
    nxt = re.search(r"\n\s*[A-Z]{2,}[A-Z0-9]*\d{2}[A-Z0-9]{3,}\s*\n", rest)
    block = rest[: nxt.start()] if nxt else rest

    # Within the block, find the requested indoor-temperature sub-block.
    ipos = block.find(f"{indoor_temp_f}°F")
    if ipos < 0:
        return [], f"indoor condition {indoor_temp_f}°F not found for this model"
    sub = block[ipos:]

    tc = re.search(r"TC((?:\s+-?\d+(?:\.\d+)?)+)", sub)
    inp = re.search(r"Input((?:\s+-?\d+(?:\.\d+)?)+)", sub)
    if not (tc and inp):
        return [], "TC / Input rows not found in the indoor block"

    caps = [float(x) for x in tc.group(1).split()]
    pwr = [float(x) for x in inp.group(1).split()]

    n = min(len(temps), len(caps), len(pwr))
    if n < 5:
        return [], f"only {n} aligned columns (temps={len(temps)}, TC={len(caps)}, Input={len(pwr)})"

    rows = []
    for f, cap_kbtu, kw in zip(temps[:n], caps[:n], pwr[:n]):
        if kw <= 0:
            continue
        cap_btu = cap_kbtu * 1000.0
        rows.append((f, cap_btu, cap_btu / (BTU_PER_KWH * kw), kw))
    rows.sort()
    return rows, None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf")
    ap.add_argument("--ahri", required=True)
    ap.add_argument("--outdoor-model", required=True)
    ap.add_argument("--brand", required=True)
    ap.add_argument("--indoor-temp-f", type=int, default=70)
    ap.add_argument("--min-op-temp-f", type=float, default=None)
    ap.add_argument("--refrigerant", default=None)
    ap.add_argument("--doc", default="")
    args = ap.parse_args()

    rows, err = parse(args.pdf, args.outdoor_model, args.indoor_temp_f)
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
        "basis": f"performance chart, indoor {args.indoor_temp_f}F return air",
        "rated_cap_47_kW": round(cap47 / BTU_PER_KWH, 4) if cap47 else None,
        "min_op_temp_C": (round(f_to_c(args.min_op_temp_f), 2)
                          if args.min_op_temp_f is not None
                          else round(f_to_c(rows[0][0]), 2)),
        "points": [
            {
                "T_C": round(f_to_c(f), 2),
                "cap_kW": round(cap / BTU_PER_KWH, 4),
                "COP": round(cop, 3),
                "power_kW": round(kw, 4),
                "src": f"perf chart {f}F: {cap/1000:.2f} kBtu/h, {kw} kW (COP derived)",
            }
            for f, cap, cop, kw in rows
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
    print(f"  COP derived from TC/(3.412*Input), range "
          f"{min(r[2] for r in rows):.2f}..{max(r[2] for r in rows):.2f}")
    print(f"  min_op_temp_C = {entry['min_op_temp_C']}   wrote {OUT_PATH.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
