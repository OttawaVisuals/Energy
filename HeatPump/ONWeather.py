# ONGrid_Weather.py
# Downloads hourly weather data from the ECCC MSC Datamart for one station
# per Ontario grid region, covering Jan 1 2020 to present.
#
# Source: https://dd.weather.gc.ca/today/climate/observations/hourly/csv/ON/
# Files are one per year per station — much simpler than the old monthly portal.
#
# Output: Weather.csv
#   Columns: HourIndex, Region, Temperature_C, WindSpeed_kmh, Humidity_pct, SolarRad_MJm2
#
# Skips files already downloaded. Sporadic missing values are interpolated;
# months with excessive gaps are flagged in Weather_Flags.csv.
#
# pip install pandas requests

import os
import time
import requests
import pandas as pd
from io import StringIO
from datetime import datetime

# ─── CONFIG ───────────────────────────────────────────────────────────────────

DIR         = r"C:\_IESO"
WEATHER_DIR = os.path.join(DIR, "Weather")
OUT_CSV     = os.path.join(DIR, "Weather.csv")
FLAGS_CSV   = os.path.join(DIR, "Weather_Flags.csv")
START_DATE  = pd.Timestamp("2020-01-01")

# If more than this fraction of hours in a month are missing temperature,
# flag it instead of interpolating silently
MISSING_THRESHOLD = 0.10  # 10% — ~72 hours in a 30-day month

# ─── STATION CONFIG ───────────────────────────────────────────────────────────
# One representative ECCC station per grid region.
# East and Bruce intentionally share the same station (Kingston / Kitchener).
# Station IDs are ECCC Climate IDs (7-digit).

STATIONS = {
    "Toronto":   {"station_id": "6158731", "name": "Toronto"},
    "Ottawa":    {"station_id": "6106001", "name": "Ottawa"},
    "West":      {"station_id": "6144473", "name": "London"},
    "Southwest": {"station_id": "6144239", "name": "Kitchener"},
    "East":      {"station_id": "6104152", "name": "Kingston"},
    "Essa":      {"station_id": "6117700", "name": "Barrie"},
    "Bruce":     {"station_id": "6144239", "name": "Kitchener"},
    "Northeast": {"station_id": "6068153", "name": "Sudbury"},
    "Northwest": {"station_id": "6048262", "name": "Thunder Bay"},
    "Niagara":   {"station_id": "6137304", "name": "St. Catharines"},
}

# MSC Datamart base URL for Ontario hourly climate CSVs
DATAMART_BASE = "https://dd.weather.gc.ca/today/climate/observations/hourly/csv/ON"

# ECCC Datamart column name fragments → our output names.
# Files are tab-separated, Latin-1 encoded, with human-readable headers including units.
# We use partial string matching so minor variations between stations/years still match.
# Solar radiation is not available in ECCC hourly files — that column will be all NaN.
COLUMN_MAP = {
    "Temp (":        "Temperature_C",    # matches "Temp (°C)"
    "Wind Spd":      "WindSpeed_kmh",    # matches "Wind Spd (km/h)"
    "Rel Hum":       "Humidity_pct",     # matches "Rel Hum (%)"
}

WEATHER_COLS = ["Temperature_C", "WindSpeed_kmh", "Humidity_pct", "SolarRad_MJm2"]

# ─── HELPERS ──────────────────────────────────────────────────────────────────

def datamart_url(station_id: str, year: int) -> str:
    """MSC Datamart URL for one station's annual hourly CSV."""
    return f"{DATAMART_BASE}/climate_hourly_ON_{station_id}_{year}_P1H.csv"


def local_path(station_id: str, year: int) -> str:
    os.makedirs(WEATHER_DIR, exist_ok=True)
    return os.path.join(WEATHER_DIR, f"ECCC_{station_id}_{year}.csv")


def download_if_missing(station_id: str, year: int) -> str:
    """Download annual hourly CSV if not already cached. Returns local path.
    If the cached file is an HTML error page (from the old broken URL), delete it
    and re-download."""
    path = local_path(station_id, year)
    if os.path.exists(path):
        # Peek at first bytes — HTML files start with '<', valid CSVs start with a letter/digit
        with open(path, 'rb') as fh:
            first_bytes = fh.read(10)
        if first_bytes.lstrip().startswith(b'<'):
            print(f"   🗑️  {year} cached file is HTML (stale) — deleting and re-downloading")
            os.remove(path)
        else:
            print(f"   ⏭️  {year} already cached")
            return path
    url = datamart_url(station_id, year)
    print(f"   ⬇️  Downloading {year} ... ", end="", flush=True)
    r = requests.get(url, timeout=60)
    if r.status_code == 404:
        print("not found (404)")
        return None
    r.raise_for_status()
    with open(path, "wb") as fh:
        fh.write(r.content)
    time.sleep(0.3)  # be polite to the server
    print("done")
    return path


def parse_datamart_csv(path: str) -> pd.DataFrame:
    """Parse an MSC Datamart hourly CSV into a clean DataFrame.

    Confirmed file format (ECCC MSC Datamart):
    - Tab-separated
    - Latin-1 / Windows-1252 encoding (degree symbol 0xB0 in "Temp (°C)")
    - Single header row, no metadata prefix
    - Datetime: "Date/Time (LST)" column, format M/D/YYYY H:MM, hours 0-23
    - Columns: Temp (°C), Wind Spd (km/h), Rel Hum (%)
    - Solar radiation not available in ECCC hourly files
    """
    df = pd.read_csv(path, dtype=str, encoding="latin-1", sep=",",
                     na_values=["", " ", "M"])  # "M" = missing in ECCC convention

    # Strip quotes and whitespace from column names
    df.columns = df.columns.str.strip().str.strip('"')

    # Find the datetime column
    date_col = next((c for c in df.columns if "Date/Time" in c), None)
    if date_col is None:
        return pd.DataFrame()

    # ECCC LST format: M/D/YYYY H:MM (e.g. "1/1/2020 0:00")
    # Try zero-padded month first, fall back to non-padded
    df['_datetime'] = pd.to_datetime(df[date_col], format="%m/%d/%Y %H:%M", errors='coerce')
    if df['_datetime'].isna().all():
        df['_datetime'] = pd.to_datetime(df[date_col], errors='coerce')
    df = df.dropna(subset=['_datetime'])

    if df.empty:
        return pd.DataFrame()

    # Map ECCC column names to our standard names using partial matching.
    # The degree symbol in "Temp (°C)" is Latin-1 encoded so we match on "Temp ("
    # to avoid any encoding-dependent comparison.
    result = pd.DataFrame({'_datetime': df['_datetime']})
    for eccc_key, our_col in COLUMN_MAP.items():
        match = next((c for c in df.columns if eccc_key in c), None)
        if match:
            result[our_col] = pd.to_numeric(df[match], errors='coerce')
        else:
            result[our_col] = float('nan')  # variable not reported at this station

    # Solar radiation not in ECCC hourly files — always NaN
    result['SolarRad_MJm2'] = float('nan')

    return result


def check_and_interpolate(df: pd.DataFrame, region: str, year: int) -> tuple:
    """Check each month for missing temperature values.
    Interpolate if sporadic; flag if excessive. Returns (cleaned df, list of flag dicts)."""
    flags = []

    for month in range(1, 13):
        mask = df['_datetime'].dt.month == month
        if not mask.any():
            continue

        month_slice = df.loc[mask].copy()
        missing_temp = month_slice['Temperature_C'].isna().sum()
        expected_hrs = (pd.Timestamp(year=year, month=month, day=1)
                        + pd.offsets.MonthEnd(1)).day * 24
        missing_frac = missing_temp / max(len(month_slice), 1)

        if missing_temp == 0:
            continue
        elif missing_frac > MISSING_THRESHOLD:
            flags.append({
                "Region": region, "Year": year, "Month": month,
                "MissingTemp": missing_temp,
                "Issue": f"{missing_frac:.0%} of hours missing — not interpolated, review manually"
            })
            print(f"   ⚠️  {year}-{month:02d}: {missing_temp} missing temp values "
                  f"({missing_frac:.0%}) — flagged")
        else:
            # Interpolate linearly for sporadic gaps, fill edges with nearest value
            df.loc[mask, WEATHER_COLS] = (
                df.loc[mask, WEATHER_COLS]
                .interpolate(method='linear', limit_direction='both')
                .ffill().bfill()
            )
            print(f"   ℹ️  {year}-{month:02d}: {missing_temp} missing value(s) interpolated")

    return df, flags

# ─── MAIN ─────────────────────────────────────────────────────────────────────

current_year = datetime.now().year
years = list(range(START_DATE.year, current_year + 1))

all_frames  = []
flag_report = []

for region, info in STATIONS.items():
    station_id   = info['station_id']
    station_name = info['name']
    print(f"\n{'─'*50}")
    print(f"📍 {region} — {station_name} (ID {station_id})")

    region_frames = []

    for year in years:
        path = download_if_missing(station_id, year)
        if path is None:
            flag_report.append({"Region": region, "Year": year, "Month": "all",
                                 "MissingTemp": "N/A", "Issue": "file not found on Datamart (404)"})
            continue

        df_year = parse_datamart_csv(path)
        if df_year.empty:
            print(f"   ⚠️  {year}: could not parse file — check column names")
            flag_report.append({"Region": region, "Year": year, "Month": "all",
                                 "MissingTemp": "N/A", "Issue": "unparseable file"})
            continue

        # Filter to START_DATE onward (relevant for the first year)
        df_year = df_year[df_year['_datetime'] >= START_DATE].copy()

        df_year, year_flags = check_and_interpolate(df_year, region, year)
        flag_report.extend(year_flags)

        n = len(df_year)
        expected = (366 if year % 4 == 0 else 365) * 24
        print(f"   ✅ {year}: {n:,} hours loaded"
              + (f" (expected ~{expected})" if abs(n - expected) > 24 else ""))

        region_frames.append(df_year)

    if not region_frames:
        print(f"   ⚠️  No data loaded for {region}")
        continue

    region_df = pd.concat(region_frames, ignore_index=True)
    region_df = region_df.sort_values('_datetime').drop_duplicates(subset='_datetime')

    # ECCC Datamart uses UTC or LST depending on the file vintage.
    # Hours are 0-based (0–23); add 1 to align with IESO convention (1–24).
    region_df['Delivery Date'] = region_df['_datetime'].dt.normalize()
    region_df['Hour']          = region_df['_datetime'].dt.hour + 1
    region_df['HourIndex']     = (
        (region_df['Delivery Date'] - START_DATE).dt.days * 24 + region_df['Hour']
    )
    region_df['Region'] = region

    all_frames.append(region_df[['HourIndex', 'Region'] + WEATHER_COLS])

# ─── WRITE OUTPUTS ────────────────────────────────────────────────────────────

print(f"\n{'='*60}")
if all_frames:
    out = pd.concat(all_frames, ignore_index=True)
    out = out.sort_values(['HourIndex', 'Region']).reset_index(drop=True)
    out.to_csv(OUT_CSV, index=False, encoding='utf-8')
    print(f"✅ Weather.csv: {len(out):,} rows → {OUT_CSV}")
    print(f"   HourIndex range: {out['HourIndex'].min()} → {out['HourIndex'].max()}")
    print(f"   Regions: {sorted(out['Region'].unique())}")
    print(f"   Columns: {list(out.columns)}")
else:
    print("⚠️  No weather data written.")

if flag_report:
    pd.DataFrame(flag_report).to_csv(FLAGS_CSV, index=False, encoding='utf-8')
    print(f"\n⚠️  {len(flag_report)} issue(s) flagged → {FLAGS_CSV}")
    print("   Review and re-download or source alternative data for flagged months.")
else:
    print("\n✅ No data quality issues flagged.")