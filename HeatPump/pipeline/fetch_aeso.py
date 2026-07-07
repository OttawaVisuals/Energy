# fetch_aeso.py
# Parses AESO's "CSD Generation (Hourly)" historical dataset into a tidy
# hourly CSV: Date, Hour, Fuel, Output_MW, Capacity_MW, Utilization.
#
# Unlike fetch_ieso.py, this does NOT download anything -- the CSD
# historical dataset is hosted on AESO's Box portal, which isn't
# scriptable (confirmed in a prior session: no stable direct-download
# URL, requires manual export). The user downloads the zip files by hand
# from https://www.aeso.ca/market/market-and-system-reporting/data-requests/historical-generation-data/
# and places them in data/raw/aeso/ -- this script just parses what's there.
#
# Source format: one zip per ~6-month period, each containing one CSV with
# columns: Date (MST), Date (MPT), Asset Short Name, Asset Name,
# Asset Grouping, Volume, Maximum Capability, System Capability, Fuel Type,
# Sub Fuel Type, Planning Area, Region.
#
# This is per-ASSET, per-hour -- already fuel-tagged at the time of each
# record, so historical fuel-type changes (e.g. coal->gas conversions) are
# reflected automatically. No separate asset->fuel mapping table needed,
# unlike the older AESO CSD-asset-list approach.
#
# Output: data/interim/aeso_hourly_by_fuel.csv
#   Output_MW    = summed Volume (actual output) across assets of that fuel
#   Capacity_MW  = summed Maximum Capability (available capacity right now,
#                  accounts for outages/derates) across assets of that fuel
#   Utilization  = Output_MW / Capacity_MW (null if Capacity_MW <= 0 or > 1)
#
# pip install pandas

import os
import sys
import glob
import zipfile
import pandas as pd

if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

# ─── CONFIG ───────────────────────────────────────────────────────────────────

HERE        = os.path.dirname(os.path.abspath(__file__))
RAW_DIR     = os.path.join(HERE, "..", "data", "raw", "aeso")
INTERIM_DIR = os.path.join(HERE, "..", "data", "interim")
OUT_CSV     = os.path.join(INTERIM_DIR, "aeso_hourly_by_fuel.csv")

USECOLS = ["Date (MST)", "Volume", "Maximum Capability", "Fuel Type"]

# ─── PARSE ONE ZIP ────────────────────────────────────────────────────────────

def parse_zip(path: str) -> pd.DataFrame:
    """Read the single CSV inside one CSD zip and aggregate to
    Date+Hour+Fuel totals (summed across assets)."""
    with zipfile.ZipFile(path) as zf:
        inner_names = [n for n in zf.namelist() if n.lower().endswith(".csv")]
        if not inner_names:
            print(f"   [warn] no CSV found in {os.path.basename(path)}")
            return pd.DataFrame()
        with zf.open(inner_names[0]) as fh:
            df = pd.read_csv(fh, usecols=USECOLS, dtype={"Fuel Type": str})

    df["Date (MST)"] = pd.to_datetime(df["Date (MST)"], errors="coerce")
    df = df.dropna(subset=["Date (MST)"])

    df["Date"] = df["Date (MST)"].dt.date
    df["Hour"] = df["Date (MST)"].dt.hour + 1  # hour-ending 1-24, matches IESO convention
    df["Volume"] = pd.to_numeric(df["Volume"], errors="coerce").fillna(0.0)
    df["Maximum Capability"] = pd.to_numeric(df["Maximum Capability"], errors="coerce").fillna(0.0)
    df["Fuel Type"] = df["Fuel Type"].str.strip().str.upper()

    agg = (
        df.groupby(["Date", "Hour", "Fuel Type"], as_index=False)
        .agg(Output_MW=("Volume", "sum"), Capacity_MW=("Maximum Capability", "sum"))
    )
    return agg


# ─── MAIN ─────────────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("AESO hourly generation by fuel -- parse local CSD files")
    print("=" * 60)

    zip_paths = sorted(glob.glob(os.path.join(RAW_DIR, "*.zip")))
    if not zip_paths:
        print(f"\n[warn] No zip files found in {RAW_DIR}")
        print("       Download the CSD Generation (Hourly) zips from AESO's")
        print("       data-requests page and place them there.")
        return

    frames = []
    for path in zip_paths:
        name = os.path.basename(path)
        try:
            agg = parse_zip(path)
        except Exception as e:
            print(f"   [warn] {name}: failed to parse -> {e}")
            continue
        if agg.empty:
            print(f"   [warn] {name}: no rows parsed")
            continue
        print(f"   [ok] {name}: {len(agg):,} rows "
              f"({agg['Date'].min()} -> {agg['Date'].max()})")
        frames.append(agg)

    if not frames:
        print("\n[warn] No data parsed -- nothing written.")
        return

    out = pd.concat(frames, ignore_index=True)
    # Overlapping months across consecutive zip files (if any) would double-count --
    # re-aggregate across all files to be safe.
    out = out.groupby(["Date", "Hour", "Fuel Type"], as_index=False).agg(
        Output_MW=("Output_MW", "sum"), Capacity_MW=("Capacity_MW", "sum")
    )
    out["Utilization"] = (out["Output_MW"] / out["Capacity_MW"]).where(
        (out["Capacity_MW"] > 0) & (out["Output_MW"] / out["Capacity_MW"] <= 1)
    )
    out = out.rename(columns={"Fuel Type": "Fuel"})
    out = out.sort_values(["Date", "Hour", "Fuel"]).reset_index(drop=True)

    os.makedirs(INTERIM_DIR, exist_ok=True)
    out.to_csv(OUT_CSV, index=False, encoding="utf-8")

    print(f"\n[ok] {len(out):,} rows -> {OUT_CSV}")
    print(f"   Date range: {out['Date'].min()} -> {out['Date'].max()}")
    print(f"   Fuels: {sorted(out['Fuel'].unique())}")


if __name__ == "__main__":
    main()
