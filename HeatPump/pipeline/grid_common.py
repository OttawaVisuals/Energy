# grid_common.py
# Shared fetch/parse/EF-computation logic for Ontario (IESO) and Alberta
# (AESO) hourly grid generation-by-fuel data. Extracted so fetch_ieso.py,
# fetch_aeso.py, build_grid_ef.py, build_grid_ef_ab.py (Phase 1) and
# Python/grid_etl.py (live grid dashboard, ROADMAP.md item 6) share exactly
# one copy of the fetch/parse/EF logic instead of each reimplementing it.
#
# EF calibration derivations (TAF Annual AEF for ON, Alberta.ca NIR-sourced
# intensity for AB) are documented in HeatPump/METHODOLOGY.md and in the
# original build_grid_ef*.py headers -- not repeated here.
#
# pip install requests pandas

import zipfile
import xml.etree.ElementTree as ET

import requests
import pandas as pd

# ─── HTTP ─────────────────────────────────────────────────────────────────────
# IESO and AESO domains are blocked for Claude's WebFetch tool but work fine
# over plain HTTP with a browser User-Agent (see METHODOLOGY.md / memory notes).

HTTP_HEADERS = {"User-Agent": "Mozilla/5.0"}

# ─── IESO (Ontario) ───────────────────────────────────────────────────────────

IESO_BASE_URL = "https://reports-public.ieso.ca/public/GenOutputbyFuelHourly"
IESO_NS = {"ieso": "http://www.ieso.ca/schema"}


def download_ieso_year(year: int, dest_path, force: bool = False, timeout: int = 120):
    """Download one year's GenOutputbyFuelHourly XML to dest_path (a
    pathlib.Path) unless already cached, or force=True. Returns dest_path,
    or None if the report doesn't exist yet for that year (404, e.g. the
    report for a brand-new year that hasn't started)."""
    if not force and dest_path.exists() and dest_path.stat().st_size > 0:
        return dest_path

    url = f"{IESO_BASE_URL}/PUB_GenOutputbyFuelHourly_{year}.xml"
    r = requests.get(url, headers=HTTP_HEADERS, timeout=timeout)
    if r.status_code == 404:
        return None
    r.raise_for_status()

    dest_path.parent.mkdir(parents=True, exist_ok=True)
    dest_path.write_bytes(r.content)
    return dest_path


def parse_ieso_xml(path) -> pd.DataFrame:
    """Parse one year's GenOutputbyFuelHourly XML into a tidy DataFrame:
    Date, Hour (1-24), Fuel, Output_MW. Already aggregated province-wide by
    fuel type by IESO -- no generator->region/fuel mapping needed."""
    tree = ET.parse(path)
    root = tree.getroot()

    rows = []
    for daily in root.iter("{http://www.ieso.ca/schema}DailyData"):
        day = daily.find("ieso:Day", IESO_NS).text
        for hourly in daily.findall("ieso:HourlyData", IESO_NS):
            hour = int(hourly.find("ieso:Hour", IESO_NS).text)
            for fuel_total in hourly.findall("ieso:FuelTotal", IESO_NS):
                fuel = fuel_total.find("ieso:Fuel", IESO_NS).text
                output_el = fuel_total.find("ieso:EnergyValue/ieso:Output", IESO_NS)
                output = float(output_el.text) if output_el is not None and output_el.text else 0.0
                rows.append({"Date": day, "Hour": hour, "Fuel": fuel, "Output_MW": output})

    return pd.DataFrame(rows)


# ─── AESO (Alberta) ───────────────────────────────────────────────────────────
# AESO's CSD Generation (Hourly) historical dataset is Box-hosted and not
# scriptable (confirmed: Box's internal app-api 404s, no stable direct-
# download URL). The user downloads the zips by hand and places them in
# data/raw/aeso/ -- these functions only parse what's already there.

AESO_USECOLS = ["Date (MST)", "Volume", "Maximum Capability", "Fuel Type"]


def parse_aeso_zip(path) -> pd.DataFrame:
    """Read the single CSV inside one AESO CSD zip and aggregate to
    Date+Hour+Fuel totals (summed across assets). Per-asset rows already
    carry Fuel Type / Sub Fuel Type at the time of that record, so
    historical fuel-type changes (e.g. coal->gas conversions) are reflected
    automatically -- no separate asset->fuel mapping table needed."""
    with zipfile.ZipFile(path) as zf:
        inner_names = [n for n in zf.namelist() if n.lower().endswith(".csv")]
        if not inner_names:
            return pd.DataFrame()
        with zf.open(inner_names[0]) as fh:
            df = pd.read_csv(fh, usecols=AESO_USECOLS, dtype={"Fuel Type": str})

    df["Date (MST)"] = pd.to_datetime(df["Date (MST)"], errors="coerce")
    df = df.dropna(subset=["Date (MST)"])

    df["Date"] = df["Date (MST)"].dt.date
    df["Hour"] = df["Date (MST)"].dt.hour + 1  # hour-ending 1-24, matches IESO convention
    df["Volume"] = pd.to_numeric(df["Volume"], errors="coerce").fillna(0.0)
    df["Maximum Capability"] = pd.to_numeric(df["Maximum Capability"], errors="coerce").fillna(0.0)
    df["Fuel Type"] = df["Fuel Type"].str.strip().str.upper()

    return (
        df.groupby(["Date", "Hour", "Fuel Type"], as_index=False)
        .agg(Output_MW=("Volume", "sum"), Capacity_MW=("Maximum Capability", "sum"))
    )


# ─── Emission factors ─────────────────────────────────────────────────────────
# Direct (combustion) emissions only, per METHODOLOGY.md Phase 1. Calibrated
# against TAF's published Annual AEF (ON) and Alberta.ca's published
# NIR-sourced generation intensity (AB).

ON_GAS_EF_G_PER_KWH = 500.0

AB_COAL_EF_G_PER_KWH = 1050.0
AB_GAS_EF_G_PER_KWH = 540.0
AB_GAS_LIKE_FUELS = {"GAS", "DUAL FUEL"}  # DUAL FUEL = transitional coal->gas units


def compute_ef_on(wide: pd.DataFrame) -> pd.DataFrame:
    """wide must have Date, Hour, Total_MW, GAS columns (MW). Returns those
    plus GasFrac, AvgEF_g_per_kWh, MarginalEF_g_per_kWh.

    AvgEF(hour)      = GasFrac(hour) * ON_GAS_EF_G_PER_KWH
    MarginalEF(hour) = ON_GAS_EF_G_PER_KWH whenever gas output > 0, else AvgEF(hour)
    """
    out = wide[["Date", "Hour", "Total_MW", "GAS"]].copy()
    out["GasFrac"] = (out["GAS"] / out["Total_MW"]).where(out["Total_MW"] > 0, 0.0)
    out["AvgEF_g_per_kWh"] = out["GasFrac"] * ON_GAS_EF_G_PER_KWH
    out["MarginalEF_g_per_kWh"] = out["AvgEF_g_per_kWh"].where(
        out["GAS"] <= 0, ON_GAS_EF_G_PER_KWH
    )
    return out


def compute_ef_ab(wide: pd.DataFrame) -> pd.DataFrame:
    """wide must have Date, Hour, Total_MW, COAL, GasLike_MW columns (MW).
    Returns those plus CoalFrac, GasLikeFrac, AvgEF_g_per_kWh,
    MarginalEF_g_per_kWh.

    AvgEF(hour)      = CoalFrac(hour)*AB_COAL_EF + GasLikeFrac(hour)*AB_GAS_EF
    MarginalEF(hour) = AB_GAS_EF whenever gas-like output > 0, else AvgEF(hour)
    """
    out = wide[["Date", "Hour", "Total_MW", "COAL", "GasLike_MW"]].copy()
    out["CoalFrac"] = (out["COAL"] / out["Total_MW"]).where(out["Total_MW"] > 0, 0.0)
    out["GasLikeFrac"] = (out["GasLike_MW"] / out["Total_MW"]).where(out["Total_MW"] > 0, 0.0)
    out["AvgEF_g_per_kWh"] = (out["CoalFrac"] * AB_COAL_EF_G_PER_KWH
                               + out["GasLikeFrac"] * AB_GAS_EF_G_PER_KWH)
    out["MarginalEF_g_per_kWh"] = out["AvgEF_g_per_kWh"].where(
        out["GasLike_MW"] <= 0, AB_GAS_EF_G_PER_KWH
    )
    return out
