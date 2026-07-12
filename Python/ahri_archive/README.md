# AHRI archive — superseded certificate-PDF workflow

Archived 2026-07-12 (ROADMAP.md item 2). Everything in this folder belongs to
the **legacy** AHRI lookup workflow: manually downloading "Certificate of
Product Ratings" PDFs from ahridirectory.org and parsing them with
[`../parse_ahri_certificates.py`](../parse_ahri_certificates.py).

It was superseded by [`../build_ahri_lookup.py`](../build_ahri_lookup.py),
which queries the AHRI Directory's search API directly for every AHRI number
seen in the ERS data (`../ahri_numbers_seen.json`, produced by
`../list_ahri_numbers.py`) and writes `lookup/ahri_numbers.json` — the file
retrofits.html actually consumes. That live-site dependency is **not** in this
archive and must not be moved.

Contents:

| File | What it is |
|---|---|
| `ahri_certificates/` (38 PDFs) | Manually downloaded certificates, the old workflow's input |
| `ahri_certificates_parsed.csv` | Output of `parse_ahri_certificates.py` over those PDFs |
| `ahri_directory_check.csv` | One-off audit from `check_ahri_directory.py` confirming that "not found" on the directory means delisted/expired (that finding is now baked into `build_ahri_lookup.py`'s Delisted handling) |

Still-current relatives that intentionally live in `Python/`, not here:
`ahri_numbers_seen.json` (input to `build_ahri_lookup.py` /
`check_ahri_directory.py`) and `ahri_numbers_seen.csv` (popularity ranking of
heat pump models in the ERS data — input to
`HeatPump/pipeline/neep_buckets.py`, see ROADMAP.md item 3a).
