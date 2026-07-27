"""
fetch_energystar.py — Phase 3c source #2: ENERGY STAR certified product list.

Downloads the EPA's ENERGY STAR Certified Central Air Conditioners and
Air-Source Heat Pumps dataset (Socrata open data, free bulk CSV, no API key)
and reduces it to a tidy per-AHRI-number attribute table.

WHY THIS SOURCE
---------------
NOT for performance data. Verified 2026-07-26 against our own AHRI Directory
scrape: on 3,447 models present in both, the 5F capacity values agree to
within 2% on 100% of rows (zero disagreements). ENERGY STAR republishes the
same AHRI certification figures — same four heating points (47F/17F/5F
capacity + COP at 5F), no 17F COP, no minimum operating temperature.

What it DOES add, that the AHRI Directory API does not expose:

  - Compressor Staging  (Continuously variable / Two-stage / Single stage)
    — a real equipment-architecture field. Validates capacity maintenance:
    median (Max5F/Rated47F) is 0.82 for continuously variable vs 0.51
    single-stage on our installed base.
  - Markets              (United States / Canada) — market availability.
  - Date Certified / Date Available on Market — vintage, for cohort analysis.
  - Meets ENERGY STAR Most Efficient criteria, CVP test type.

COVERAGE CAVEAT: this is a list of CURRENTLY CERTIFIED products. It joins to
only ~23% of the AHRI numbers in the ERS installed base (~45% by install
count), and recovers a 5F capacity for just 59 of the 7,610 models missing
one — because that missing group is 99.5% Discontinued/Delisted by volume.
It adds attributes; it does not fill coverage gaps. See METHODOLOGY.md
"Heat pump tiers (Phase 3c)".

Usage:
    pip install pandas requests
    python pipeline/fetch_energystar.py

Output:
    data/raw/energystar/es_heat_pumps.csv   raw bulk download (~115 MB, gitignored)
    data/interim/energystar_by_ahri.csv     tidy, one row per AHRI number
"""

import sys
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw" / "energystar"
INTERIM_DIR = ROOT / "data" / "interim"

# Socrata dataset 83eb-xbyy — "ENERGY STAR Certified Heat Pumps".
DATASET_ID = "83eb-xbyy"
CSV_URL = f"https://data.energystar.gov/api/views/{DATASET_ID}/rows.csv?accessType=DOWNLOAD"

# Columns worth keeping. The performance columns are kept ONLY as a cross-check
# against our AHRI scrape (they are the same underlying numbers) -- the reason
# this file exists is the attribute columns.
KEEP = {
    "AHRI Reference Number": "ahri_number",
    "Compressor Staging": "compressor_staging",
    "Markets": "markets",
    "Product Type": "es_product_type",
    "Cold Climate": "es_cold_climate",
    "Date Certified": "date_certified",
    "Date Available on Market": "date_available",
    "Refrigerant Type": "es_refrigerant",
    "Meets ENERGY STAR Most Efficient 2025 Criteria": "es_most_efficient",
    "Controls Verification Procedure (CVP) Test": "cvp_test",
    "SEER2 (Btu/Wh)": "es_seer2",
    "EER2 (Btu/Wh)": "es_eer2",
    "HSPF2 (Btu/Wh)": "es_hspf2",
    "Heating Capacity at 47°F (Btu/h)": "es_cap_47f",
    "Heating Capacity at 17°F (Btu/h)": "es_cap_17f",
    "Heating Capacity at 5°F (Btu/h)": "es_cap_5f",
    "COP at 5°F": "es_cop_5f",
}

# Preference order when one AHRI number maps to several ENERGY STAR rows
# (same outdoor unit certified with different indoor coils / furnaces).
# Variable-speed beats staged beats single, so a de-duplicated row describes
# the most capable configuration the outdoor unit was certified in.
STAGING_RANK = {"Continuously variable": 0, "Two-stage": 1, "Single stage": 2}


def download(dest: Path):
    """Stream the bulk CSV to disk (it is ~115 MB)."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    print(f"Downloading ENERGY STAR dataset {DATASET_ID}...")
    with requests.get(CSV_URL, stream=True, timeout=600) as r:
        r.raise_for_status()
        total = 0
        with open(dest, "wb") as f:
            for chunk in r.iter_content(chunk_size=1 << 20):
                f.write(chunk)
                total += len(chunk)
        print(f"  wrote {dest} ({total / 1e6:.1f} MB)")


def main():
    INTERIM_DIR.mkdir(parents=True, exist_ok=True)
    raw = RAW_DIR / "es_heat_pumps.csv"
    if not raw.exists():
        download(raw)
    else:
        print(f"Using cached {raw} (delete it to re-download)")

    df = pd.read_csv(raw, low_memory=False, usecols=list(KEEP)).rename(columns=KEEP)
    print(f"  {len(df)} raw rows")

    df = df.dropna(subset=["ahri_number"])
    # AHRI ref comes through Socrata as a float; normalise to the same string
    # key the rest of the pipeline uses.
    df["ahri_number"] = df["ahri_number"].astype("int64").astype(str)

    df["_rank"] = df["compressor_staging"].map(STAGING_RANK).fillna(9)
    df = df.sort_values("_rank").drop_duplicates(subset=["ahri_number"], keep="first")
    df = df.drop(columns=["_rank"])

    dest = INTERIM_DIR / "energystar_by_ahri.csv"
    df.to_csv(dest, index=False, encoding="utf-8")
    print(f"Wrote {dest} — {len(df)} distinct AHRI numbers")
    print(df["compressor_staging"].value_counts(dropna=False).to_string())
    return 0


if __name__ == "__main__":
    sys.exit(main())
