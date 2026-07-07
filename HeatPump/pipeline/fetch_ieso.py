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
import requests
import pandas as pd
import xml.etree.ElementTree as ET

if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

# ─── CONFIG ───────────────────────────────────────────────────────────────────

HERE        = os.path.dirname(os.path.abspath(__file__))
RAW_DIR     = os.path.join(HERE, "..", "data", "raw", "ieso")
INTERIM_DIR = os.path.join(HERE, "..", "data", "interim")
OUT_CSV     = os.path.join(INTERIM_DIR, "ieso_hourly_by_fuel.csv")

BASE_URL = "https://reports-public.ieso.ca/public/GenOutputbyFuelHourly"
NS       = {"ieso": "http://www.ieso.ca/schema"}

YEARS = list(range(2020, 2027))  # 2020 through current year; adjust as needed

HEADERS = {"User-Agent": "Mozilla/5.0"}

# ─── FETCH ────────────────────────────────────────────────────────────────────

def download_if_missing(year: int) -> str | None:
    """Download one year's XML report if not already cached. Returns local path,
    or None if the file doesn't exist yet (e.g. future year)."""
    os.makedirs(RAW_DIR, exist_ok=True)
    path = os.path.join(RAW_DIR, f"PUB_GenOutputbyFuelHourly_{year}.xml")

    if os.path.exists(path):
        print(f"   [skip] {year} already cached")
        return path

    url = f"{BASE_URL}/PUB_GenOutputbyFuelHourly_{year}.xml"
    print(f"   [fetch] Downloading {year} ... ", end="", flush=True)
    r = requests.get(url, headers=HEADERS, timeout=120)
    if r.status_code == 404:
        print("not found (404)")
        return None
    r.raise_for_status()
    with open(path, "wb") as fh:
        fh.write(r.content)
    print(f"done ({len(r.content) / 1e6:.1f} MB)")
    return path


# ─── PARSE ────────────────────────────────────────────────────────────────────

def parse_xml(path: str) -> pd.DataFrame:
    """Parse one year's GenOutputbyFuelHourly XML into a tidy DataFrame:
    Date, Hour (1-24), Fuel, Output_MW."""
    tree = ET.parse(path)
    root = tree.getroot()

    rows = []
    for daily in root.iter("{http://www.ieso.ca/schema}DailyData"):
        day = daily.find("ieso:Day", NS).text
        for hourly in daily.findall("ieso:HourlyData", NS):
            hour = int(hourly.find("ieso:Hour", NS).text)
            for fuel_total in hourly.findall("ieso:FuelTotal", NS):
                fuel = fuel_total.find("ieso:Fuel", NS).text
                output_el = fuel_total.find("ieso:EnergyValue/ieso:Output", NS)
                output = float(output_el.text) if output_el is not None and output_el.text else 0.0
                rows.append({"Date": day, "Hour": hour, "Fuel": fuel, "Output_MW": output})

    return pd.DataFrame(rows)


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
