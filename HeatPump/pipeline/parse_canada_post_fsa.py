"""
Parse Canada Post's official FSA delivery-facility schematic into a flat
FSA -> facility/province lookup.

WHY THIS EXISTS
----------------
build_city_fsa_list.py's original approach (CLIENTCITY free-text matched
through CITY_MEMBERS) produced an Ottawa FSA list padded with ~65 stray
FSAs (1-13 homes each, mostly other cities' typos) plus a genuine bug: 714
Ontario homes in Aylmer, ON (FSA N5H, near London) were misclassified as
Ottawa-Gatineau because Gatineau, QC also has a borough called Aylmer, and
the matching didn't check province. User supplied Canada Post's official
"LETTERMAIL & NON-LETTERMAIL NATIONAL PRESORTATION SCHEMATIC" PDF (valid
July 17-Aug 13 2026) as ground truth -- confirmed the diagnosis (page 9
lists N5H AYLMER ON explicitly, a different town from Gatineau's Aylmer)
and gives an authoritative FSA -> delivery facility mapping to replace the
free-text join with.

SOURCE
------
User-supplied PDF: "nonlettermail_fsa_list_june_2026.pdf" -- Canada Post
Corporation's national presortation schematic, valid for mailings deposited
2026-07-17 to 2026-08-13. Three-column layout per page: FSA code, facility
name, province, then a designation (STN/LCD/PDF/SUCC/CDP/DCF) and often a
named substation. `*` prefix marks an FSA whose facility assignment changed
this cycle (transfer) -- carried through as a flag, not filtered.

METHOD
------
pdfplumber, one page at a time. Each page is laid out in 3 side-by-side
columns; cropping to each column's bounding box and extracting text
per-column (rather than reading left-to-right across the whole page) avoids
interleaving unrelated columns. Within a column, most facility records are
a single line ("K1S OTTAWA ON LCD S. FLEMING"); some wrap the substation
name onto a second line with no leading FSA code (e.g. G3A's "PDF
BUREAU-CHEF" continuation) -- those are detected (line doesn't start with
an FSA-code pattern) and appended to the previous record.

FSA pattern: optional leading `*`, then letter-digit-letter (Canada Post's
format, e.g. K1S, A1A). Row format after the FSA code: one or more words of
facility name, a 2-letter province code, then designation words (STN/LCD/
PDF/SUCC/CDP/DCF and whatever follows) -- the province code is the anchor
used to split facility name from designation.

OUTPUT
------
HeatPump/reference/canada_post_fsa_facilities.csv
  columns: fsa, facility, province, designation, transferred_flag
HeatPump/reference/canada_post_fsa_facilities.json
  meta (source, validity window) + the same rows

LIMITATIONS
-----------
- This is a MAIL-ROUTING facility grouping, not a municipal boundary. A
  facility label can be a separate municipality served by the same plant
  (e.g. Ottawa's K0B/K0C/K0E/K0G/K0J are "OTT EXT-<town>" -- Hawkesbury,
  Cornwall, Brockville, Smiths Falls, Pembroke -- all well outside city
  limits; K4K/K4R are ROCKLAND/RUSSELL, separate municipalities adjacent to
  Ottawa). Grouping these facility labels into a "city" for the heatpump.html
  dropdown is still a judgement call, made explicit in build_city_fsa_list.py.
- Snapshot dated to one ~4-week mailing cycle; Canada Post revises FSA
  facility assignments periodically (that's what the `*` transfer flag
  tracks). Re-parse from a fresh PDF if this goes stale.
- Some province codes appear parenthesized for special routing zones
  (e.g. "X0A MONTREAL (QC) NU DCF" -- Nunavut mail routed via Montreal);
  kept as recorded, both province tokens preserved in `facility` text.
"""
from __future__ import annotations

import csv
import json
import re
from pathlib import Path

import pdfplumber

PDF_PATH = Path(
    r"C:\Users\simon\.claude\uploads\074e7289-78d1-4788-bb8c-44d1fb75b4f2"
    r"\14fe57e2-nonlettermail_fsa_list_june_2026.pdf"
)
OUT_DIR = Path(__file__).resolve().parent.parent / "reference"
OUT_CSV = OUT_DIR / "canada_post_fsa_facilities.csv"
OUT_JSON = OUT_DIR / "canada_post_fsa_facilities.json"

FSA_RE = re.compile(r"^\*?[A-Z]\d[A-Z]$")
PROV_CODES = {"NL", "NS", "PE", "NB", "QC", "ON", "MB", "SK", "AB", "BC", "YT", "NT", "NU"}
DESIGNATIONS = {"STN", "LCD", "PDF", "SUCC", "CDP", "DCF"}
# columns of interest only; skip the header/legend rows entirely
SKIP_PREFIXES = ("FSA", "RTA", "ONF9761B", "LETTERMAIL", "SCHEMA", "VALID", "VALIDE",
                  "---", "(+)", "(-", "(*)")


def parse_row(line: str):
    """Parse one facility-record line into (fsa, facility, province, designation, transferred)."""
    tokens = line.split()
    if not tokens or not FSA_RE.match(tokens[0]):
        return None
    raw_fsa = tokens[0]
    transferred = raw_fsa.startswith("*")
    fsa = raw_fsa.lstrip("*")
    rest = tokens[1:]

    # find the province code (possibly parenthesized, e.g. "(QC)")
    prov_idx = None
    province = None
    for i, tok in enumerate(rest):
        bare = tok.strip("()")
        if bare in PROV_CODES:
            prov_idx = i
            province = bare
            break
    if prov_idx is None:
        return None  # unparseable line; caller reports these

    facility = " ".join(rest[:prov_idx])
    designation = " ".join(rest[prov_idx + 1:])
    return {
        "fsa": fsa,
        "facility": facility,
        "province": province,
        "designation": designation,
        "transferred_flag": transferred,
    }


def extract_page_rows(page):
    width = page.width
    height = page.height
    # column anchors (FSA-code x0) sit at ~19, ~273, ~526 on a 792pt-wide
    # landscape page; boundaries must fall in the gaps between columns'
    # text (empirically ~265 and ~520), NOT at the midpoint between anchors
    # -- a naive midpoint (e.g. 0.665*width) lands almost on the column-3
    # anchor itself and truncates its leading character.
    b1 = width * (265 / 792)
    b2 = width * (520 / 792)
    col_bounds = [(0, 0, b1, height),
                  (b1, 0, b2, height),
                  (b2, 0, width, height)]
    rows = []
    unparsed = []
    for bbox in col_bounds:
        crop = page.within_bbox(bbox)
        text = crop.extract_text() or ""
        current = None
        for raw_line in text.split("\n"):
            line = raw_line.strip()
            if not line or line.startswith(SKIP_PREFIXES):
                continue
            parsed = parse_row(line)
            if parsed:
                if current:
                    rows.append(current)
                current = parsed
            else:
                # continuation of the previous row's facility/designation
                # (wrapped substation name, e.g. G3A's second line), or
                # genuinely unparseable noise -- only keep as continuation
                # if a row is open.
                if current:
                    current["designation"] = (current["designation"] + " " + line).strip()
                else:
                    unparsed.append(line)
        if current:
            rows.append(current)
    return rows, unparsed


def main():
    all_rows = []
    all_unparsed = []
    with pdfplumber.open(PDF_PATH) as pdf:
        meta_text = pdf.pages[1].extract_text()
        for page in pdf.pages[1:]:
            rows, unparsed = extract_page_rows(page)
            all_rows.extend(rows)
            all_unparsed.extend(unparsed)

    seen = {}
    dupes = []
    for r in all_rows:
        key = r["fsa"]
        if key in seen and seen[key] != r:
            dupes.append((key, seen[key], r))
        seen[key] = r

    print(f"Parsed {len(all_rows)} FSA rows ({len(seen)} distinct FSA codes)")
    print(f"Unparsed lines (no open row to attach to): {len(all_unparsed)}")
    for u in all_unparsed[:20]:
        print(f"  [unparsed] {u!r}")
    if dupes:
        print(f"\n{len(dupes)} FSA codes appeared more than once with different facility text:")
        for fsa, first, second in dupes[:20]:
            print(f"  {fsa}: {first['facility']}/{first['province']} vs {second['facility']}/{second['province']}")

    validity_line = next((l for l in meta_text.split("\n") if l.startswith("VALID FOR")), "")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUT_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["fsa", "facility", "province", "designation", "transferred_flag"])
        w.writeheader()
        for fsa in sorted(seen):
            w.writerow(seen[fsa])
    print(f"\n[out] wrote {OUT_CSV}")

    payload = {
        "meta": {
            "source": "Canada Post Corporation, national LETTERMAIL & NON-LETTERMAIL "
                      "presortation schematic (user-supplied PDF, "
                      "nonlettermail_fsa_list_june_2026.pdf)",
            "validity": validity_line,
            "n_fsa": len(seen),
            "n_unparsed_lines": len(all_unparsed),
            "note": "facility is a mail-routing delivery/distribution centre grouping, "
                    "not a municipal boundary -- see docstring limitations",
        },
        "fsa": seen,
    }
    OUT_JSON.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"[out] wrote {OUT_JSON}")


if __name__ == "__main__":
    main()
