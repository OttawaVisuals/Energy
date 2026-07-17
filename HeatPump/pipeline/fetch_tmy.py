# fetch_tmy.py
# Downloads and parses CWEC2020 (Canadian Weather year for Energy Calculation)
# TMY station files for the launch cities, into a tidy 8760-hour-per-city CSV.
#
# Source: https://collaboration.cmc.ec.gc.ca/cmc/climate/Engineer_Climate/CWEC_FMCCE/CWEC_FMCCE_v_2020/
# One big all-Canada zip, containing one zip per province, each containing
# one CSV per station. This script downloads only the province zips needed
# and extracts only the 5 launch-city station files -- not the full ~190 MB
# archive's worth of unrelated stations.
#
# Each station file is a "typical year": 8760 hours built by splicing
# together 12 "typical meteorological months" chosen from a multi-decade
# record, per station. Column units, per the file's own header: dry bulb
# temperature in 0.1 C, wind speed in 0.1 m/s.
#
# Output: data/interim/tmy_hourly.csv
#   City, MonthDayHour (MMDDHH), Month, Day, Hour, Temperature_C, WindSpeed_ms
#
# pip install pandas requests

import os
import sys
import zipfile
import io
import requests
import pandas as pd

if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

# ─── CONFIG ───────────────────────────────────────────────────────────────────

HERE        = os.path.dirname(os.path.abspath(__file__))
RAW_DIR     = os.path.join(HERE, "..", "data", "raw", "eccc", "tmy")
INTERIM_DIR = os.path.join(HERE, "..", "data", "interim")
OUT_CSV     = os.path.join(INTERIM_DIR, "tmy_hourly.csv")

# The CWEC2020 release is now distributed as ONE combined by-province CSV zip
# (the old per-province URLs CWEC-FMCCE_by-par_prov.CSV/CWEC_2020_<prov>.zip
# 404 as of 2026-07). The combined archive's filename carries an export
# timestamp, so we discover it from the version directory listing rather than
# hard-coding it.
CWEC_DIR_URL = ("https://collaboration.cmc.ec.gc.ca/cmc/climate/Engineer_Climate/"
                "CWEC_FMCCE/CWEC_FMCCE_v_2020/")
COMBINED_ZIP = os.path.join(RAW_DIR, "cwec_all.zip")

# city -> (province, station file name inside the province zip, without .csv).
# Primary international airport per city; climate ID embedded in the stem.
STATIONS = {
    # original launch cities
    "Ottawa":       ("ON", "CAN_ON_OTTAWA-INTL-A_6106001_CWEC"),
    "Toronto":      ("ON", "CAN_ON_TORONTO-INTL-A_6158731_CWEC"),
    "Montreal":     ("QC", "CAN_QC_MONTREAL-INTL-A_7025251_CWEC"),
    "Calgary":      ("AB", "CAN_AB_CALGARY-INTL-A_3031092_CWEC"),
    "Edmonton":     ("AB", "CAN_AB_EDMONTON-INTL-A_3012216_CWEC"),
    # v2 additions (ROADMAP item 9 workstream A)
    "Vancouver":    ("BC", "CAN_BC_VANCOUVER-INTL-A_1108395_CWEC"),
    "Winnipeg":     ("MB", "CAN_MB_WINNIPEG-INTL-A_5023227_CWEC"),
    "Quebec City":  ("QC", "CAN_QC_QUEBEC-INTL-A_7016293_CWEC"),
    "Halifax":      ("NS", "CAN_NS_HALIFAX-INTL-A_8202251_CWEC"),
    "Saskatoon":    ("SK", "CAN_SK_SASKATOON-INTL-A_4057152_CWEC"),
    "Regina":       ("SK", "CAN_SK_REGINA-INTL-A_4016566_CWEC"),
    "Hamilton":     ("ON", "CAN_ON_HAMILTON-A_6153193_CWEC"),
    "London":       ("ON", "CAN_ON_LONDON-A_6144473_CWEC"),
    "Windsor":      ("ON", "CAN_ON_WINDSOR-A_6139527_CWEC"),
}

HEADERS = {"User-Agent": "Mozilla/5.0"}

# ─── FETCH ────────────────────────────────────────────────────────────────────

def ensure_combined_zip() -> str:
    """Download the combined by-province CSV zip (~195 MB) once, cached."""
    if os.path.exists(COMBINED_ZIP) and os.path.getsize(COMBINED_ZIP) > 1_000_000:
        return COMBINED_ZIP
    os.makedirs(RAW_DIR, exist_ok=True)
    listing = requests.get(CWEC_DIR_URL, headers=HEADERS, timeout=120).text
    import re
    m = re.search(r'href="(CWEC-FMCCE_by-par_prov\.CSV-[^"]+\.zip)"', listing)
    if not m:
        raise RuntimeError("Could not find combined CSV zip in CWEC dir listing")
    url = CWEC_DIR_URL + m.group(1)
    print(f"   [fetch] combined CWEC zip {m.group(1)} ... ", end="", flush=True)
    r = requests.get(url, headers=HEADERS, timeout=600)
    r.raise_for_status()
    with open(COMBINED_ZIP, "wb") as fh:
        fh.write(r.content)
    print(f"done ({len(r.content) / 1e6:.0f} MB)")
    return COMBINED_ZIP


def ensure_station_csv(city: str, prov: str, stem: str) -> str:
    """Extract one station's CSV from the combined zip (via its inner
    per-province zip). Returns local path to the station CSV."""
    os.makedirs(RAW_DIR, exist_ok=True)
    out_path = os.path.join(RAW_DIR, f"{stem}.csv")
    if os.path.exists(out_path):
        print(f"   [skip] {city}: already cached")
        return out_path

    import io, re
    with zipfile.ZipFile(ensure_combined_zip()) as outer:
        inner_name = next(
            (n for n in outer.namelist()
             if re.search(rf"CWEC_2020_{prov}[._]", n) and n.lower().endswith(".zip")),
            None)
        if inner_name is None:
            raise RuntimeError(f"No inner province zip for {prov} in combined archive")
        with zipfile.ZipFile(io.BytesIO(outer.read(inner_name))) as zf:
            csv_name = next((n for n in zf.namelist()
                             if n.endswith(f"{stem}.csv")), None)
            if csv_name is None:
                raise RuntimeError(f"{stem}.csv not found in {inner_name}")
            with zf.open(csv_name) as src, open(out_path, "wb") as dst:
                dst.write(src.read())
    print(f"   [ok] {city}: extracted {stem}.csv")
    return out_path


# ─── PARSE ────────────────────────────────────────────────────────────────────

def parse_station(path: str) -> pd.DataFrame:
    # Data rows have one more field than the header row (the header omits a
    # label for the leading "ECCC station identifier" column) -- index_col=False
    # keeps pandas from mistaking that column for a row index.
    df = pd.read_csv(path, skiprows=2, dtype=str, index_col=False)
    df.columns = [c.strip() for c in df.columns]
    dt_col = "Year Month Day Hour (YYYYMMDDHH)"

    out = pd.DataFrame()
    out["_ymdh"] = df[dt_col].str.strip()
    bad = out["_ymdh"].isna() | (out["_ymdh"].str.len() != 10)
    if bad.any():
        print(f"      [warn] dropping {bad.sum()} row(s) with malformed timestamp")
        out = out[~bad]
        df = df[~bad.values]
    out["Month"] = out["_ymdh"].str[4:6].astype(int)
    out["Day"] = out["_ymdh"].str[6:8].astype(int)
    out["Hour"] = out["_ymdh"].str[8:10].astype(int)  # 1-24, CWEEDS convention (hour-ending)

    temp_col = next(c for c in df.columns if c.startswith("Dry bulb temperature"))
    wind_col = next(c for c in df.columns if c.startswith("Wind speed"))
    out["Temperature_C"] = pd.to_numeric(df[temp_col], errors="coerce") / 10.0
    out["WindSpeed_ms"] = pd.to_numeric(df[wind_col], errors="coerce") / 10.0

    return out[["Month", "Day", "Hour", "Temperature_C", "WindSpeed_ms"]]


# ─── MAIN ─────────────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("CWEC2020 TMY -- fetch + parse launch-city stations")
    print("=" * 60)

    frames = []
    for city, (prov, stem) in STATIONS.items():
        path = ensure_station_csv(city, prov, stem)
        df = parse_station(path)
        df.insert(0, "City", city)
        print(f"   [ok] {city}: {len(df):,} hours parsed "
              f"(mean temp {df['Temperature_C'].mean():.1f} C, "
              f"min {df['Temperature_C'].min():.1f} C)")
        frames.append(df)

    out = pd.concat(frames, ignore_index=True)
    os.makedirs(INTERIM_DIR, exist_ok=True)
    out.to_csv(OUT_CSV, index=False, encoding="utf-8")

    print(f"\n[ok] {len(out):,} rows -> {OUT_CSV}")


if __name__ == "__main__":
    main()
