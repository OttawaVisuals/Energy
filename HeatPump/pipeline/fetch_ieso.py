# fetch_ieso.py
# Downloads IESO "Generator Output by Fuel Type Hourly" reports and parses them
# into a tidy hourly CSV: Date, Hour, Fuel, Output_MW.
#
# Source: https://reports-public.ieso.ca/public/GenOutputbyFuelHourly/
# One XML file per year, already aggregated province-wide by fuel type —
# no generator->region/fuel mapping needed (unlike the older
# GenOutputCapabilityMonth report).
#
# Output: data/raw/ieso/PUB_GenOutputbyFuelHourly_<year>.xml (cached)
#         data/interim/ieso_hourly_by_fuel.csv (tidy, all years combined)
#
# pip install requests pandas

import os
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from grid_common import download_ieso_year, parse_ieso_xml, HTTP_HEADERS  # noqa: E402

if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

# ─── CONFIG ───────────────────────────────────────────────────────────────────

HERE        = os.path.dirname(os.path.abspath(__file__))
RAW_DIR     = os.path.join(HERE, "..", "data", "raw", "ieso")
INTERIM_DIR = os.path.join(HERE, "..", "data", "interim")
OUT_CSV     = os.path.join(INTERIM_DIR, "ieso_hourly_by_fuel.csv")

YEARS = list(range(2020, 2027))  # 2020 through current year; adjust as needed

HEADERS = HTTP_HEADERS  # kept as a module attribute for backward compatibility

# ─── FETCH ────────────────────────────────────────────────────────────────────

def download_if_missing(year: int) -> str | None:
    """Download one year's XML report if not already cached. Returns local path,
    or None if the file doesn't exist yet (e.g. future year)."""
    path = Path(RAW_DIR) / f"PUB_GenOutputbyFuelHourly_{year}.xml"
    if path.exists():
        print(f"   [skip] {year} already cached")
        return str(path)

    print(f"   [fetch] Downloading {year} ... ", end="", flush=True)
    result = download_ieso_year(year, path, force=False)
    if result is None:
        print("not found (404)")
        return None
    print(f"done ({result.stat().st_size / 1e6:.1f} MB)")
    return str(result)


# ─── PARSE ────────────────────────────────────────────────────────────────────

def parse_xml(path: str) -> pd.DataFrame:
    """Parse one year's GenOutputbyFuelHourly XML into a tidy DataFrame:
    Date, Hour (1-24), Fuel, Output_MW."""
    return parse_ieso_xml(path)


# ─── MAIN ─────────────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("IESO hourly generation by fuel — fetch + parse")
    print("=" * 60)

    frames = []
    for year in YEARS:
        path = download_if_missing(year)
        if path is None:
            continue
        df = parse_xml(path)
        if df.empty:
            print(f"   [warn] {year}: no rows parsed")
            continue
        print(f"   [ok] {year}: {len(df):,} rows parsed")
        frames.append(df)

    if not frames:
        print("\n[warn] No data parsed — nothing written.")
        return

    out = pd.concat(frames, ignore_index=True)
    out["Date"] = pd.to_datetime(out["Date"]).dt.date
    out = out.sort_values(["Date", "Hour", "Fuel"]).reset_index(drop=True)

    os.makedirs(INTERIM_DIR, exist_ok=True)
    out.to_csv(OUT_CSV, index=False, encoding="utf-8")

    print(f"\n[ok] {len(out):,} rows → {OUT_CSV}")
    print(f"   Date range: {out['Date'].min()} → {out['Date'].max()}")
    print(f"   Fuels: {sorted(out['Fuel'].unique())}")


if __name__ == "__main__":
    main()
