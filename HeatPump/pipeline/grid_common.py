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

# --- Ontario natural gas -----------------------------------------------------
# TAF publishes the NIR-derived natural gas intensity directly, so it is used
# as published rather than backed out of their headline Annual AEF.
#
# Source: The Atmospheric Fund, "Ontario Electricity Emissions Factors and
# Guidelines" (2025 edition), data tables workbook, sheet 10 "Natural Gas
# Consumption Intensity". Values for 2015-2023 are NIR-derived; TAF estimates
# 2024-2025 as the mean of 2022 and 2023.
#
# These published values are CONSUMPTION-side: TAF's sheet title states they
# include "gas plants emission intensity and transmission & distribution
# losses". Both tools that consume this module apply line losses themselves
# (heatpump.html engine.js lineLossPct, default 5%), so the published value is
# divided by (1 + ON_TD_LOSS_FRAC) here to yield a GENERATION-side factor and
# avoid double-counting T&D.
#
# TAF does not publish the loss rate it used, so ON_TD_LOSS_FRAC is an
# assumption. It is set to 7.4% to MATCH the Ontario line-loss constant the
# heat pump tool re-applies downstream (heatpump.html LINELOSS_PCT_BY_PROV:
# IESO transmission ~2% compounded with the OEB's audited distributor Total
# Loss Factor ~5.31%, 1.02 x 1.0531 = 1.074).
#
# Matching the two matters more than the value itself. Emissions come out as
#   gas_share x published / (1 + strip) x (1 + re-add)
# so when strip == re-add the round trip is exactly neutral and the tool
# reproduces TAF's own published consumption-side AEF. A mismatch is a
# silent bias: stripping 5% while re-applying 7.4% over-counts by 2.3%.
# The generation-side factor reported on its own (grid.html, and the heat
# pump tool with upstream losses switched off) does move with this value:
# at 5% the 2024 factor would read 430 rather than 420 g/kWh.
#
# Cross-check: (gas share of IESO generation) x (published value) reproduces
# TAF's own published Annual AEF within 1% for 2020-2024, confirming both the
# identity and that our IESO denominator matches TAF's basis.

ON_TD_LOSS_FRAC = 0.074

ON_GAS_CONSUMPTION_INTENSITY_G_PER_KWH = {
    2015: 446.0, 2016: 459.0, 2017: 417.0, 2018: 435.0, 2019: 439.0,
    2020: 514.0, 2021: 482.0, 2022: 459.0, 2023: 442.0, 2024: 451.0,
    2025: 451.0,
}
ON_GAS_EF_LAST_YEAR = max(ON_GAS_CONSUMPTION_INTENSITY_G_PER_KWH)


def on_gas_ef(year: int) -> float:
    """Generation-side Ontario gas emission intensity (g CO2e/kWh) for `year`.

    Years past the published table carry the last available value forward,
    matching TAF's own practice of estimating recent years from prior ones.
    The alternative -- TAF's 2026+ forecast series, derived from the IESO APO
    2025 build-out -- is a projection of future plant mix, not a measurement,
    and is deliberately not used for observed generation.
    """
    published = ON_GAS_CONSUMPTION_INTENSITY_G_PER_KWH.get(
        int(year), ON_GAS_CONSUMPTION_INTENSITY_G_PER_KWH[ON_GAS_EF_LAST_YEAR]
    )
    return published / (1.0 + ON_TD_LOSS_FRAC)


# Backwards-compatible scalar: the most recent year's generation-side factor.
# Prefer on_gas_ef(year) -- this constant loses the year-to-year variation.
ON_GAS_EF_G_PER_KWH = on_gas_ef(ON_GAS_EF_LAST_YEAR)

AB_COAL_EF_G_PER_KWH = 1050.0
AB_GAS_EF_G_PER_KWH = 540.0
AB_GAS_LIKE_FUELS = {"GAS", "DUAL FUEL"}  # DUAL FUEL = transitional coal->gas units


def compute_ef_on(wide: pd.DataFrame) -> pd.DataFrame:
    """wide must have Date, Hour, Total_MW, GAS columns (MW). Returns those
    plus GasFrac, AvgEF_g_per_kWh, MarginalEF_g_per_kWh.

    AvgEF(hour)      = GasFrac(hour) * on_gas_ef(year)
    MarginalEF(hour) = on_gas_ef(year) whenever gas output > 0, else AvgEF(hour)
    """
    out = wide[["Date", "Hour", "Total_MW", "GAS"]].copy()
    out["GasFrac"] = (out["GAS"] / out["Total_MW"]).where(out["Total_MW"] > 0, 0.0)
    # Gas EF varies by year (see on_gas_ef). Held as a local Series, not a
    # returned column, so the frame shape stays identical for all callers.
    gas_ef = pd.to_datetime(out["Date"]).dt.year.map(on_gas_ef).astype(float)
    out["AvgEF_g_per_kWh"] = out["GasFrac"] * gas_ef
    out["MarginalEF_g_per_kWh"] = out["AvgEF_g_per_kWh"].where(out["GAS"] <= 0, gas_ef)
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
