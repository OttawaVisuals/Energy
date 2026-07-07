# fetch_hq.py
# Parses Hydro-Quebec's hourly generation-by-source CSV into a tidy hourly
# file: Date, Hour, Fuel, Output_MW.
#
# Does NOT download anything -- the user downloaded this file manually
# (source: HQ's open-data / historical production export) and placed it in
# data/raw/hq/historique-production-electricite-quebec.csv.
#
# Source columns: Date (ISO8601 with UTC offset, e.g. 2025-01-01T00:00:00-05:00),
# Hydroelectric, Wind, Other renewables, Solar, Thermal, Total.
#
# KNOWN DATA GAP: the source file has no rows at all for 2021 (and the first
# ~3 weeks of Jan 2022) -- confirmed by the user to be a genuine gap in the
# source, not a download error. Separately, 7,307 rows scattered through the
# file have a BLANK Date field (3 distinct blocks, each spliced oddly between
# a 2022-12-31 row and a 2022-01-0x row) -- these are dropped here rather
# than guessed at. See METHODOLOGY.md for full detail.
#
# Output: data/interim/hq_hourly_by_fuel.csv
#
# pip install pandas

import os
import sys
import pandas as pd

if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

# ─── CONFIG ───────────────────────────────────────────────────────────────────

HERE        = os.path.dirname(os.path.abspath(__file__))
IN_CSV      = os.path.join(HERE, "..", "data", "raw", "hq",
                            "historique-production-electricite-quebec.csv")
INTERIM_DIR = os.path.join(HERE, "..", "data", "interim")
OUT_CSV     = os.path.join(INTERIM_DIR, "hq_hourly_by_fuel.csv")

FUEL_COLS = {
    "Hydroelectric": "HYDRO",
    "Wind": "WIND",
    "Other renewables": "OTHER_RENEWABLES",
    "Solar": "SOLAR",
    "Thermal": "THERMAL",
}

# ─── MAIN ─────────────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("Hydro-Quebec hourly generation by fuel -- parse local file")
    print("=" * 60)

    df = pd.read_csv(IN_CSV, encoding="utf-8-sig")
    df.columns = [c.strip() for c in df.columns]
    print(f"\nRaw rows: {len(df):,}")

    blank_dates = df["Date"].isna().sum()
    df = df[df["Date"].notna()].copy()
    print(f"Dropped {blank_dates:,} rows with blank Date "
          f"(known source gap -- see METHODOLOGY.md)")

    df["dt"] = pd.to_datetime(df["Date"], utc=True)
    before_dedup = len(df)
    df = df.drop_duplicates(subset="dt", keep="first")
    if before_dedup != len(df):
        print(f"Dropped {before_dedup - len(df)} duplicate timestamp(s) "
              f"(DST fall-back repeated hour)")

    df["Date_local"] = df["dt"].dt.tz_convert("America/Montreal")
    df["Date"] = df["Date_local"].dt.date
    df["Hour"] = df["Date_local"].dt.hour + 1  # hour-ending 1-24, matches IESO/AESO convention

    melted = df.melt(
        id_vars=["Date", "Hour"],
        value_vars=list(FUEL_COLS.keys()),
        var_name="Fuel", value_name="Output_MW",
    )
    melted["Fuel"] = melted["Fuel"].map(FUEL_COLS)
    melted = melted.sort_values(["Date", "Hour", "Fuel"]).reset_index(drop=True)

    os.makedirs(INTERIM_DIR, exist_ok=True)
    melted.to_csv(OUT_CSV, index=False, encoding="utf-8")

    print(f"\n[ok] {len(melted):,} rows -> {OUT_CSV}")
    print(f"   Date range: {melted['Date'].min()} -> {melted['Date'].max()}")
    print(f"   Fuels: {sorted(melted['Fuel'].unique())}")

    years_present = sorted(pd.to_datetime(melted["Date"]).dt.year.unique())
    years_missing = [y for y in range(years_present[0], years_present[-1] + 1)
                     if y not in years_present]
    if years_missing:
        print(f"   [warn] Years with no data at all: {years_missing}")


if __name__ == "__main__":
    main()
