"""
probe_datasheets.py — Phase 3c triage for hand-fetched manufacturer PDFs.

Scans every PDF in data/raw/spec_sheets/ and reports, per file, whether a usable
heating performance table can be recovered from its text layer -- so the
hand-fetching effort can be aimed at the documents that actually lack data
rather than at ones whose table simply did not survive a naive keyword search.

Recognises four shapes, in decreasing order of usefulness:

  FULL      capacity + COP + power at many outdoor temperatures, one row per
            temperature (the GREE "EXTENDED RATINGS" layout:
            `<T>F <Btu/h> <COP> <W>`) -- parse with extract_datasheet_tables.py
  MATRIX    temperatures as column headers with TC / Input data rows
            (Midea-platform: MOOVAIR/Master, MDV) -- parse with
            extract_matrix_datasheet.py
  CAP_POWER capacity + power, COP derivable as cap / (3.412 * W)
  SPARSE    only a handful of rated points (47/17/5 F) -- not a curve

Everything is reported, including failures, with the reason. A PDF whose text
layer is empty is flagged IMAGE_ONLY: the table may well be there as a scan,
and needs OCR or manual transcription rather than being written off.

Usage:
    python pipeline/probe_datasheets.py [--dir DIR]
"""

import argparse
import re
import sys
from pathlib import Path

from pypdf import PdfReader

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DIR = ROOT / "data" / "raw" / "spec_sheets"

BTU_PER_KWH = 3412.14

# <T>F <capacity Btu/h> <COP x.xx> <power W>
FULL_RE = re.compile(r"(-?\d+)F (\d{4,6}) (\d\.\d\d) (\d{3,5})")
# <T>F <capacity Btu/h> <power W>  (no COP column)
CAP_POWER_RE = re.compile(r"(-?\d+)F (\d{4,6}) (\d{3,5})(?!\d)")
# a bare mention of the rated points
SPARSE_RE = re.compile(r"\b(47|17|5)\s*°?F\b")


def probe(path):
    try:
        reader = PdfReader(path)
    except Exception as exc:
        return "UNREADABLE", 0, str(exc)[:60]

    text = ""
    for p in reader.pages:
        try:
            text += (p.extract_text() or "") + "\n"
        except Exception:
            pass

    if len(text.strip()) < 200:
        return "IMAGE_ONLY", 0, "no text layer — needs OCR or manual transcription"

    flat = re.sub(r"\s+", " ", text.replace("°", ""))

    full = sorted({r for r in FULL_RE.findall(flat)}, key=lambda r: int(r[0]))
    heating = [r for r in full if -30 <= int(r[0]) <= 80]
    if len(heating) >= 5:
        # verify the COP column against capacity/power
        ok = 0
        for f, cap, cop, w in heating:
            if abs(int(cap) / (BTU_PER_KWH / 1000 * int(w)) - float(cop)) <= 0.05:
                ok += 1
        lo, hi = int(heating[0][0]), int(heating[-1][0])
        note = f"{len(heating)} pts {lo}F..{hi}F, COP check {ok}/{len(heating)}"
        return ("FULL" if ok >= 0.8 * len(heating) else "FULL_COP_SUSPECT"), len(heating), note

    # MATRIX layout (Midea-platform: MOOVAIR/Master, MDV and rebadges) --
    # temperatures as column headers, TC / Input as rows. The row-layout regexes
    # never fire on these, so without this branch a perfectly good performance
    # chart is reported SPARSE. Parse it with extract_matrix_datasheet.py.
    if "HEATING" in text.upper():
        heat = text[text.upper().find("HEATING"):]
        header = next((ln for ln in heat.splitlines()
                       if len(re.findall(r"-?\d+\s*°F", ln)) >= 5), None)
        # Require actual DATA rows -- a line that is literally `TC <n> <n> ...`
        # and one that is `Input <n> <n> ...`, each with at least 5 numbers.
        # Matching bare "TC"/"Input" anywhere in the section produced a false
        # MATRIX on the TOSOT submittal, which only carries rated 47/17 F points.
        tc_row = re.search(r"\bTC((?:\s+-?\d+(?:\.\d+)?){5,})", heat)
        in_row = re.search(r"\bInput((?:\s+-?\d+(?:\.\d+)?){5,})", heat)
        if header and tc_row and in_row:
            ncols = min(len(re.findall(r"-?\d+\s*°F", header)),
                        len(tc_row.group(1).split()), len(in_row.group(1).split()))
            return "MATRIX", ncols, (f"{ncols} aligned temperature columns with TC/Input "
                                     f"rows; use extract_matrix_datasheet.py")

    cp = sorted({r for r in CAP_POWER_RE.findall(flat)}, key=lambda r: int(r[0]))
    cp = [r for r in cp if -30 <= int(r[0]) <= 80]
    if len(cp) >= 5:
        return "CAP_POWER", len(cp), f"{len(cp)} pts {cp[0][0]}F..{cp[-1][0]}F, COP derivable"

    n = len(set(SPARSE_RE.findall(flat)))
    return "SPARSE", n, f"only rated points found ({n} of 47/17/5 F)"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default=str(DEFAULT_DIR))
    args = ap.parse_args()

    pdfs = sorted(Path(args.dir).glob("*.pdf"))
    if not pdfs:
        print(f"No PDFs in {args.dir}", file=sys.stderr)
        return 1

    rows = [(p.name, *probe(p)) for p in pdfs]
    order = {"FULL": 0, "MATRIX": 1, "FULL_COP_SUSPECT": 2, "CAP_POWER": 3,
             "SPARSE": 4, "IMAGE_ONLY": 5, "UNREADABLE": 6}
    rows.sort(key=lambda r: (order.get(r[1], 9), -r[2]))

    print(f"{'file':<46} {'verdict':<17} {'pts':>4}  note")
    for name, verdict, n, note in rows:
        print(f"{name[:46]:<46} {verdict:<17} {n:>4}  {note}")

    print()
    for v in order:
        c = sum(1 for r in rows if r[1] == v)
        if c:
            print(f"  {v}: {c}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
