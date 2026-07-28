"""
match_spec_sheets.py — fill the `Spec sheet` / `page` / `note` columns in
cell_candidates.csv from the PDFs actually held in data/raw/spec_sheets/.

EVIDENCE, NOT BRAND GUESSING
----------------------------
A candidate is linked to a PDF only when one of these strings is found in the
document's own text layer, in this order of confidence:

  1. the AHRI certified reference number   -> `ahri` (strongest: the sheet names
                                              the exact certified combination)
  2. the outdoor model, exact              -> `model_exact`
  3. the outdoor model, normalized         -> `model_norm` (case-folded, with
                                              (), *, /, -, spaces stripped --
                                              GWHD(24)ND3MO vs GWHD24ND3MO)
  4. the indoor model, normalized          -> `indoor_norm` (weakest)

Brand agreement alone is NEVER a match. Rebadged platforms (GREE/KINGHOME/TOSOT,
MDV/MOOVAIR/Bladex/Senville) share ratings but not documents, so a brand-level
guess would attach the wrong sheet to a unit with identical certified numbers --
undetectable downstream, because the ratings would agree.

WHY THIS DOES NOT SETTLE THE BAND ISSUE
---------------------------------------
Finding a model string in a PDF proves the document mentions the model. It does
NOT prove the document's performance table describes the *certified combination*
carried by that AHRI number (DATASHEET_INVENTORY.md 5b). Only `match=ahri` is
combination-level evidence. Everything else stays provisional until the ratio
check in build_unit_curves.py runs on digitized points. The note column says so
per row.

MANUAL EDITS ARE PRESERVED
--------------------------
Rows whose `Spec sheet` is already filled are left untouched, including the
hand-entered page numbers. Only blank rows are populated. Run with --force to
re-derive every row (destroys manual work -- avoid).

Usage:
    python HeatPump/pipeline/match_spec_sheets.py [--force]

Rewrites data/interim/cell_candidates.csv in place (a .bak copy is written
first).
"""

import argparse
import csv
import io
import json
import re
import shutil
import sys
from pathlib import Path

from pypdf import PdfReader

ROOT = Path(__file__).resolve().parent.parent
SPEC_DIR = ROOT / "data" / "raw" / "spec_sheets"
TARGET = ROOT / "data" / "interim" / "cell_candidates.csv"
CACHE = ROOT / "data" / "interim" / "_spec_sheet_text_cache.json"

MIN_MODEL_LEN = 5  # shorter strings match noise

# Verdicts come from probe_datasheets.probe(), NOT from a local copy of its
# regexes. An earlier version reimplemented them and silently disagreed: probe
# flattens whitespace (`re.sub(r"\s+", " ", ...)`) before matching, the copy did
# not, so documents probe correctly calls FULL scored zero table hits here. One
# implementation, imported.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from probe_datasheets import probe  # noqa: E402

# Best-first: when several held PDFs mention the same model, link the one that
# actually carries a performance table rather than whichever sorts first.
SHAPE_RANK = {
    "DIGITIZED": -1,
    "FULL": 0,
    "FULL_COP_SUSPECT": 1,
    "MATRIX": 2,
    "CAP_POWER": 3,
    "SPARSE": 4,
    "IMAGE_ONLY": 5,
    "UNREADABLE": 6,
}

SHAPE_NOTE = {
    "DIGITIZED": "points already digitized",
    "FULL": "has full cap+COP+power table",
    "FULL_COP_SUSPECT": "has a full table but its COP column fails the cross-check",
    "MATRIX": "has a matrix table — parse with extract_matrix_datasheet.py",
    "CAP_POWER": "has cap+power table, COP derivable",
    "SPARSE": "rated points only — NOT a curve",
    "IMAGE_ONLY": "no text layer — may be a scan, needs OCR",
    "UNREADABLE": "PDF could not be parsed",
}


# Provenance for the held PDFs, keyed by path relative to spec_sheets/.
#
# The binaries are NOT in git: they are third-party manufacturer documents
# (copyright), and 120 MB besides. This mapping is what makes the set
# reconstructible on another machine -- `curl -sL -o <path> <url>`.
#
# ONLY URLs actually used to fetch the file belong here. Most of the corpus was
# hand-fetched in earlier sessions with no URL recorded; those stay blank rather
# than being guessed. A plausible-looking wrong URL is worse than an empty cell:
# it would fetch a different document, and the rebadge families share ratings,
# so the substitution would not show up in any downstream check.
SOURCE_URLS = {
    "mdv/MDV_MOD30-24_MitsAir_casedcoil_submittal.pdf":
        "https://www.mitsair.com/wp-content/uploads/2025/06/"
        "Mits-Air-Cased-Coil-Hyper-Heat-Submittal_MOD30-24_MAC24.pdf",
    "lg/LG_LSU120HSV5_submittal_ajmadison.pdf":
        "https://assets.ajmadison.com/ajmadison/itemdocs/D5b84511d22570.pdf",
    "gree/GREE_GWHD24ND3MO_GEN2_submittal.pdf":
        "https://greehvac.ca/wp-content/uploads/2024/03/"
        "GEN2-Heap-Pump-Submittal-GWHD24ND3MO.pdf",
    "gree/GREE_multizone_freematch_brochure_2024.pdf":
        "https://petroleleger.ca/wp-content/uploads/2024/05/"
        "GREE-BROCHURE-MULTI-ZONE-FREEMATCH-M-SERIES-EN-WEB.pdf",
    "tosot/TOSOT_heatpump_catalogue_2022.pdf":
        "https://tosotamerica.com/wp-content/uploads/2022/05/TOSOTCAT22_EN_1mai.pdf",
}


def normalize(text):
    return re.sub(r"[^A-Z0-9]", "", (text or "").upper())


def load_texts():
    """Per-page text for every held PDF, cached (extraction is slow)."""
    cache = {}
    if CACHE.exists():
        try:
            cache = json.loads(CACHE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            cache = {}

    docs = {}
    changed = False
    for path in sorted(SPEC_DIR.rglob("*.pdf")):
        rel = path.relative_to(SPEC_DIR).as_posix()
        stamp = f"{path.stat().st_size}:{int(path.stat().st_mtime)}"
        entry = cache.get(rel)
        if not entry or entry.get("stamp") != stamp:
            pages = []
            try:
                reader = PdfReader(str(path))
            except Exception as exc:  # noqa: BLE001 - a broken PDF must not stop the sweep
                print(f"  unreadable: {rel} ({exc})", file=sys.stderr)
                reader = None
            if reader is not None:
                # Per-page, because a single bad font entry ('/DescendantFonts')
                # otherwise discards a document whose other pages read fine --
                # it cost us both GREE GWHD24ND3MO submittals on the first run.
                for page in reader.pages:
                    try:
                        pages.append(page.extract_text() or "")
                    except Exception:  # noqa: BLE001
                        pages.append("")
            verdict, _, _ = probe(str(path))
            entry = {"stamp": stamp, "pages": pages, "shape": verdict}
            cache[rel] = entry
            changed = True
        docs[rel] = entry

    if changed:
        CACHE.write_text(json.dumps(cache), encoding="utf-8")
    return docs


def find(docs, needle, normalized=False):
    """Best document containing needle: richest table first, then earliest page."""
    if not needle or len(needle) < MIN_MODEL_LEN:
        return None
    hits = []
    for rel, entry in docs.items():
        for i, page in enumerate(entry["pages"], start=1):
            haystack = normalize(page) if normalized else page
            if needle in haystack:
                hits.append((SHAPE_RANK.get(entry["shape"], 9), i, rel, entry["shape"]))
                break
    if not hits:
        return None
    rank, page, rel, shape = min(hits)
    return rel, page, shape


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true",
                        help="re-derive rows that already have a Spec sheet (destroys manual edits)")
    args = parser.parse_args()

    if not TARGET.exists():
        sys.exit(f"missing {TARGET}")

    with io.open(TARGET, encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        rows = list(reader)
        fields = reader.fieldnames

    for col in ("Spec sheet", "page", "note"):
        if col not in fields:
            sys.exit(f"expected column '{col}' not found — is this the edited CSV?")

    # Appended, never inserted, so hand-added columns keep their positions.
    if "source_url" not in fields:
        fields = list(fields) + ["source_url"]

    docs = load_texts()
    print(f"indexed {len(docs)} PDFs")

    # Units whose points are already digitized, with the source document string
    # recorded at digitization time (datasheet_points_v2.json `doc`).
    digitized = {}
    points_path = ROOT / "data" / "interim" / "datasheet_points_v2.json"
    if points_path.exists():
        for key, unit in json.loads(points_path.read_text(encoding="utf-8")).get("units", {}).items():
            digitized[key] = unit.get("doc", "") or "(source not recorded)"
    print(f"already digitized: {len(digitized)} units")

    filled = kept = 0
    for row in rows:
        if row.get("Spec sheet", "").strip() and not args.force:
            kept += 1
            continue

        ahri = row["ahri_number"].strip()
        outdoor = row["outdoor_model"].strip()
        indoor = row["indoor_model"].strip()

        hit, kind = None, None
        if ahri in digitized:
            # Already digitized: the source document is recorded per unit, so use
            # it rather than re-deriving. Without this the search can land on a
            # weaker document that merely mentions the model -- 211644151 linked
            # to the GREE *service manual* and read "rated points only" despite
            # having a 23-point curve built from the submittal.
            kind = "digitized"
            # Prefer a real file path over the prose citation recorded at
            # digitization time -- the column is meant to be followable.
            located = find(docs, ahri) or (find(docs, outdoor) if outdoor else None)
            if located:
                hit = (located[0], located[1], "DIGITIZED")
            else:
                hit = (digitized[ahri], "", "DIGITIZED")
        elif (hit := find(docs, ahri)):
            kind = "ahri"
        elif outdoor and (hit := find(docs, outdoor)):
            kind = "model_exact"
        elif outdoor and (hit := find(docs, normalize(outdoor), normalized=True)):
            kind = "model_norm"
        elif indoor and (hit := find(docs, normalize(indoor), normalized=True)):
            kind = "indoor_norm"

        if not hit:
            row["Spec sheet"] = ""
            row["page"] = ""
            row["note"] = "no held PDF mentions this model"
            continue

        rel, page, shape = hit
        row["Spec sheet"] = rel
        row["page"] = str(page)

        if kind == "digitized":
            row["note"] = ("ALREADY DIGITIZED — points in datasheet_points_v2.json; "
                           "no manual search needed")
            row["_kind"] = kind
            row["_shape"] = "DIGITIZED"
            filled += 1
            continue

        if kind == "ahri":
            evidence = "AHRI number printed in doc — combination confirmed"
        elif kind == "model_exact":
            evidence = "exact outdoor model string in doc — combination NOT confirmed"
        elif kind == "model_norm":
            evidence = "normalized outdoor model match — combination NOT confirmed"
        else:
            evidence = "indoor model match only — weak, verify before use"

        row["note"] = f"{evidence}; {SHAPE_NOTE.get(shape, shape)}"
        row["_kind"] = kind
        row["_shape"] = shape
        filled += 1

    # Provenance is keyed on the linked document, so it applies to manually
    # linked rows too -- and is refreshed every run, including for rows whose
    # Spec sheet was hand-entered and therefore skipped above.
    for row in rows:
        row["source_url"] = SOURCE_URLS.get(row.get("Spec sheet", "").strip(), "")

    shutil.copy2(TARGET, TARGET.with_suffix(".csv.bak"))
    with io.open(TARGET, "w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

    linked = [r for r in rows if r["Spec sheet"].strip()]
    print(f"filled {filled} rows, preserved {kept} manual rows")
    print(f"linked: {len(linked)}/{len(rows)}")
    for kind, label in (("ahri", "combination confirmed"),
                        ("model_exact", "model-level only"),
                        ("model_norm", "model-level only"),
                        ("indoor_norm", "weak — verify")):
        n = sum(1 for r in rows if r.get("_kind") == kind)
        if n:
            print(f"  {kind:12} {n:3}  ({label})")
    print("  document shape:")
    for shape in SHAPE_RANK:
        n = sum(1 for r in rows if r.get("_shape") == shape)
        if n:
            print(f"    {shape:18} {n:3}  {SHAPE_NOTE[shape]}")
    print(f"\nrewrote {TARGET.relative_to(ROOT)} (backup at {TARGET.name}.bak)")


if __name__ == "__main__":
    main()
