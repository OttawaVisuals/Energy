"""
parse_ahri_certificates.py

Parses a folder of downloaded AHRI "Certificate of Product Ratings" PDFs
(www.ahridirectory.org -> a certificate's "Download Certificate" button)
into one CSV row per certificate.

Each certificate is mostly one "Label : Value" pair per line, EXCEPT the
top line which glues three fields together with no separator, e.g.:
  "AHRI Certified Reference Number : 206249117 Model Status : ActiveDate : 06-26-2026"
That line is parsed with a dedicated regex; every other line is parsed
generically (split on the first colon), so this handles whatever rating
fields a given AHRI Type has (heat pump vs. AC-only vs. furnace, etc.)
without hardcoding a fixed field list — those go into the `all_fields`
JSON column. A handful of commonly-wanted fields (brand, model numbers,
AHRI type) are additionally pulled into their own named columns via
fuzzy (substring) key matching, so they survive minor label-wording
differences across certificate templates/years.

Requires: pip install pypdf

INPUT:  a folder of .pdf files (default: ahri_certificates/)
OUTPUT: ahri_certificates_parsed.csv
"""

import csv
import glob
import json
import os
import re
import sys

from pypdf import PdfReader

CERT_DIR = "ahri_certificates"
OUT_PATH = "ahri_certificates_parsed.csv"

# The one consistently-glued line at the top of every certificate.
TOP_LINE_RE = re.compile(
    r"AHRI Certified Reference Number\s*:\s*(?P<ref>\d+)\s*"
    r"Model Status\s*:\s*(?P<status>[A-Za-z]+?)\s*"
    r"Date\s*:\s*(?P<date>[\d/-]+)"
)

# Core fields pulled into named columns, matched by substring (case-
# insensitive) against the generic per-line label, in priority order.
CORE_FIELD_MATCHERS = {
    "ahri_type": "ahri type",
    "series": "series",
    "brand": "outdoor unit brand name",
    "outdoor_model": "outdoor unit model number",
    "indoor_model": "indoor unit model number",
}


def normalize_key(s):
    return re.sub(r"\s+", " ", s).strip()


def parse_pdf(path):
    reader = PdfReader(path)
    text = "\n".join(page.extract_text() or "" for page in reader.pages)
    lines = text.split("\n")

    fields = {}
    ref_number = model_status = date = None

    for line in lines:
        m = TOP_LINE_RE.search(line)
        if m:
            ref_number, model_status, date = m.group("ref"), m.group("status"), m.group("date")
            continue
        if ":" not in line:
            continue
        label, _, value = line.partition(":")
        label, value = normalize_key(label), value.strip()
        # Boilerplate paragraphs sometimes contain a colon too (e.g. "...third
        # party testing:") — real label lines are short; skip long "labels".
        if not label or not value or len(label) > 90:
            continue
        fields[label] = value

    core = {}
    lower_fields = {k.lower(): v for k, v in fields.items()}
    for out_key, needle in CORE_FIELD_MATCHERS.items():
        for k, v in lower_fields.items():
            if needle in k:
                core[out_key] = v
                break
        else:
            core[out_key] = None

    return {
        "file": os.path.basename(path),
        "ahri_number": ref_number,
        "model_status": model_status,
        "date": date,
        **core,
        "all_fields": json.dumps(fields, ensure_ascii=False),
    }


def main():
    cert_dir = sys.argv[1] if len(sys.argv) > 1 else CERT_DIR
    pdfs = sorted(glob.glob(os.path.join(cert_dir, "*.pdf")))
    if not pdfs:
        print(f"!! no PDFs found in {cert_dir}/")
        return

    rows = []
    for p in pdfs:
        try:
            rows.append(parse_pdf(p))
            print(f"  parsed {os.path.basename(p)} -> AHRI {rows[-1]['ahri_number']}, "
                  f"{rows[-1]['brand']} {rows[-1]['outdoor_model']}")
        except Exception as e:
            print(f"  !! failed on {os.path.basename(p)}: {e}")

    fieldnames = ["file", "ahri_number", "model_status", "date", "ahri_type", "series",
                  "brand", "outdoor_model", "indoor_model", "all_fields"]
    with open(OUT_PATH, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)
    print(f"\nwrote {OUT_PATH} — {len(rows)} certificates parsed")


if __name__ == "__main__":
    main()
