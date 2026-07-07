# fetch_weather.py
# Downloads hourly historical weather from the ECCC MSC Datamart for the
# launch cities, covering the same years as the grid EF data (2020-present).
# Same source/pattern as Weather/ottawa_weather_fetch_hourly.py and the
# reference ONWeather.py, generalized to 5 cities instead of 10 ON subregions.
#
# Source: https://dd.weather.gc.ca/today/climate/observations/hourly/csv/<PROV>/
# Files are one per year per station.
#
# Output: data/interim/weather_hourly.csv
#   City, Date, Hour, Temperature_C, WindSpeed_kmh, Humidity_pct
#
# Skips files already downloaded. Sporadic missing values are interpolated;
# months with excessive gaps are flagged in weather_flags.csv.
#
# pip install pandas requests

import os
import sys
import time
import requests
import pandas as pd
from datetime import datetime

if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

# ─── CONFIG ───────────────────────────────────────────────────────────────────

HERE        = os.path.dirname(os.path.abspath(__file__))
RAW_DIR     = os.path.join(HERE, "..", "data", "raw", "eccc", "hourly")
INTERIM_DIR = os.path.join(HERE, "..", "data", "interim")
OUT_CSV     = os.path.join(INTERIM_DIR, "weather_hourly.csv")
FLAGS_CSV   = os.path.join(INTERIM_DIR, "weather_flags.csv")

START_YEAR = 2019  # covers the earliest grid data (QC) onward

# If more than this fraction of hours in a month are missing temperature,
# flag it instead of interpolating silently
MISSING_THRESHOLD = 0.10

# city -> (ECCC province code for the Datamart URL, 7-digit climate ID)
STATIONS = {
    "Ottawa":   ("ON", "6106001"),
    "Toronto":  ("ON", "6158731"),
    "Montreal": ("QC", "7025251"),
    "Calgary":  ("AB", "3031092"),
    "Edmonton": ("AB", "3012216"),
}

DATAMART_BASE = "https://dd.weather.gc.ca/today/climate/observations/hourly/csv"

COLUMN_MAP = {
    "Temp (":   "Temperature_C",
    "Wind Spd": "WindSpeed_kmh",
    "Rel Hum":  "Humidity_pct",
}
WEATHER_COLS = ["Temperature_C", "WindSpeed_kmh", "Humidity_pct"]

HEADERS = {"User-Agent": "Mozilla/5.0"}

# ─── HELPERS ──────────────────────────────────────────────────────────────────

def datamart_url(prov: str, station_id: str, year: int) -> str:
    return f"{DATAMART_BASE}/{prov}/climate_hourly_{prov}_{station_id}_{year}_P1H.csv"


def local_path(station_id: str, year: int) -> str:
    os.makedirs(RAW_DIR, exist_ok=True)
    return os.path.join(RAW_DIR, f"ECCC_{station_id}_{year}.csv")


def download_if_missing(prov: str, station_id: str, year: int):
    path = local_path(station_id, year)
    if os.path.exists(path):
        with open(path, "rb") as fh:
            first_bytes = fh.read(10)
        if first_bytes.lstrip().startswith(b"<"):
            os.remove(path)
        else:
            return path
    url = datamart_url(prov, station_id, year)
    r = requests.get(url, headers=HEADERS, timeout=60)
    if r.status_code == 404:
        return None
    r.raise_for_status()
    with open(path, "wb") as fh:
        fh.write(r.content)
    time.sleep(0.2)
    return path


def parse_datamart_csv(path: str) -> pd.DataFrame:
    df = pd.read_csv(path, dtype=str, encoding="latin-1", sep=",",
                      na_values=["", " ", "M"])
    df.columns = df.columns.str.strip().str.strip('"')

    date_col = next((c for c in df.columns if "Date/Time" in c), None)
    if date_col is None:
        return pd.DataFrame()

    df["_datetime"] = pd.to_datetime(df[date_col], format="%m/%d/%Y %H:%M", errors="coerce")
    if df["_datetime"].isna().all():
        df["_datetime"] = pd.to_datetime(df[date_col], errors="coerce")
    df = df.dropna(subset=["_datetime"])
    if df.empty:
        return pd.DataFrame()

    result = pd.DataFrame({"_datetime": df["_datetime"]})
    for eccc_key, our_col in COLUMN_MAP.items():
        match = next((c for c in df.columns if eccc_key in c), None)
        result[our_col] = pd.to_numeric(df[match], errors="coerce") if match else float("nan")
    return result


def check_and_interpolate(df: pd.DataFrame, city: str, year: int):
    flags = []
    for month in range(1, 13):
        mask = df["_datetime"].dt.month == month
        if not mask.any():
            continue
        month_slice = df.loc[mask]
        missing = month_slice["Temperature_C"].isna().sum()
        frac = missing / max(len(month_slice), 1)
        if missing == 0:
            continue
        elif frac > MISSING_THRESHOLD:
            flags.append({"City": city, "Year": year, "Month": month,
                           "MissingTemp": missing,
                           "Issue": f"{frac:.0%} missing -- not interpolated"})
        else:
            df.loc[mask, WEATHER_COLS] = (
                df.loc[mask, WEATHER_COLS]
                .interpolate(method="linear", limit_direction="both")
                .ffill().bfill()
            )
    return df, flags


# ─── MAIN ─────────────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("ECCC hourly weather -- launch cities")
    print("=" * 60)

    current_year = datetime.now().year
    years = list(range(START_YEAR, current_year + 1))

    all_frames = []
    flag_report = []

    for city, (prov, station_id) in STATIONS.items():
        print(f"\n{city} ({prov} {station_id})")
        city_frames = []
        for year in years:
            path = download_if_missing(prov, station_id, year)
            if path is None:
                continue
            df_year = parse_datamart_csv(path)
            if df_year.empty:
                continue
            df_year = df_year[df_year["_datetime"] >= pd.Timestamp(f"{START_YEAR}-01-01")].copy()
            df_year, year_flags = check_and_interpolate(df_year, city, year)
            flag_report.extend(year_flags)
            city_frames.append(df_year)
            print(f"   [ok] {year}: {len(df_year):,} hours")

        if not city_frames:
            print(f"   [warn] no data for {city}")
            continue

        city_df = pd.concat(city_frames, ignore_index=True)
        city_df = city_df.sort_values("_datetime").drop_duplicates(subset="_datetime")
        city_df["Date"] = city_df["_datetime"].dt.date
        city_df["Hour"] = city_df["_datetime"].dt.hour + 1
        city_df["City"] = city
        all_frames.append(city_df[["City", "Date", "Hour"] + WEATHER_COLS])

    if not all_frames:
        print("\n[warn] No weather data written.")
        return

    out = pd.concat(all_frames, ignore_index=True)
    out = out.sort_values(["City", "Date", "Hour"]).reset_index(drop=True)
    os.makedirs(INTERIM_DIR, exist_ok=True)
    out.to_csv(OUT_CSV, index=False, encoding="utf-8")
    print(f"\n[ok] {len(out):,} rows -> {OUT_CSV}")

    if flag_report:
        pd.DataFrame(flag_report).to_csv(FLAGS_CSV, index=False, encoding="utf-8")
        print(f"[warn] {len(flag_report)} issue(s) flagged -> {FLAGS_CSV}")
    else:
        print("[ok] no data quality issues flagged")


if __name__ == "__main__":
    main()
