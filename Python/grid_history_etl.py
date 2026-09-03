"""
grid_history_etl.py

Deep-history ETL for the Grid Dashboard's "Historical generation mix &
capacity" section (see ROADMAP.md, grid.html update 2026-09-02). Unlike
grid_etl.py (weekly, rolling ~12-month window for the "what's powering the
grid right now" view), this script pulls IESO/AESO reports that go back
years, at monthly resolution, and is run manually/occasionally -- the raw
files it caches don't change once a month has closed, so there's nothing to
re-fetch on a weekly cadence.

WHY A SEPARATE SCRIPT
    grid_etl.py's job (rolling recent window, weekly refresh) and this
    script's job (full history, occasional refresh) have different fetch
    volumes (a handful of small files vs. ~115 MB of cached IESO capacity
    CSVs) and different cadences. Splitting keeps the weekly Action fast and
    keeps this script's one-time backfill cost out of it. Both import
    HTTP_HEADERS from HeatPump/pipeline/grid_common.py to share the one
    fetch convention (IESO/AESO block Claude's WebFetch tool but work fine
    over plain requests.get with a browser User-Agent).

SOURCES (all reports-public.ieso.ca/public/, discovered by browsing the
open directory listing -- see docs/GRID.md for the full inventory of what
else lives there and was deliberately not built)
    GenOutputbyFuelMonthly   ON fuel-mix, IESO-pre-aggregated by month,
                             2015-present (one year earlier than the hourly
                             report grid_etl.py uses, which only archives
                             from 2020).
    GenOutputCapabilityMonth ON per-generator hourly Output + Capability,
                             2019-05-present. No fuel-level pre-aggregation
                             -- this script does that. Dispatchable fuels
                             (GAS/HYDRO/NUCLEAR/BIOFUEL) report a
                             "Capability" row (registered capacity); WIND
                             and SOLAR have no such row and instead report
                             "Available Capacity" (IESO's own weather-
                             adjusted forecast of what those assets could
                             produce that hour). The two are NOT the same
                             kind of number -- see CAPACITY_METHODOLOGY_NOTE
                             below, which ships in the output JSON so the
                             page can state the distinction rather than
                             blur it into one undifferentiated "% of
                             capacity".
    Demand                   ON real published hourly demand, 2002-present.
                             Uses the "Ontario Demand" column (what the
                             province actually consumes) rather than
                             "Market Demand" (which also includes scheduled
                             exports) -- the more relevant comparator for a
                             generation-mix page.
    PriceHOEPAverage         ON Hourly Ontario Energy Price, monthly
                             arithmetic + generation-weighted averages,
                             2002-present. Tiny files, real IESO-published
                             statistic, no client-side averaging needed.
    IntertieScheduleFlowYear ON imports/exports by interconnection,
                             2018-present. Individual tie-lines (14+ of
                             them, e.g. PQ.H4Z, PQ.X2Y) are grouped to their
                             parent jurisdiction (all "PQ.*" -> QUEBEC, all
                             "MANITOBA*" -> MANITOBA, etc.) dynamically from
                             each file's own two-row header, since the exact
                             set of named tie-lines has changed over the
                             years -- hardcoding a column list would have
                             silently dropped newer/renamed interconnections.
    GlobalAdjustment         ON Global Adjustment Class B rate. This
                             endpoint only retains ~13 months live (no
                             yearly archive exists, unlike every other
                             report above) -- confirmed by listing the
                             directory, not assumed. Shipped as a short
                             trailing-window object, explicitly NOT part of
                             the "monthly" historical array, so the page
                             can't accidentally imply years of GA history
                             that don't exist at this source.

    Alberta has no equivalent authority for any of Demand/HOEP/Intertie/GA
    (those are IESO-specific market mechanisms) -- AB's contribution here is
    fuel-mix + capacity-factor only, both already fully available in the
    AESO CSD zips grid_etl.py's build_alberta() already parses (Maximum
    Capability per asset, cached back to 2015 -- see grid_common.py). No new
    fetch needed for AB; this script just aggregates what's already cached
    to monthly resolution instead of the ~12-month window grid_etl.py keeps.

OUTPUT (grid_json/, repo root)
    grid_on_history.json -- {meta, monthly: [...], global_adjustment_monthly: [...]}
        monthly: one row per calendar month, ON-wide-union of every source's
            own start date (2002-01 for demand/price, 2015-01 for fuel mix,
            2018-01 for intertie, 2019-05 for capacity) through the present.
            Fields are null before their source's own start -- a real gap,
            not an interpolated or zero-filled one (see CLAUDE.md "Data
            honesty rails").
    grid_ab_history.json -- {meta, monthly: [...]}
        monthly: fuel_mix + capacity_factor only, 2015-01-present.

USAGE
    pip install requests pandas
    python grid_history_etl.py             # normal run, cache what's missing
    python grid_history_etl.py --refresh    # also re-download the current
                                             # (still-open) month's files
"""

import sys
import json
import argparse
import zipfile
from pathlib import Path
from datetime import datetime, timezone
from collections import defaultdict

import requests
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
HP_DIR = REPO_ROOT / "HeatPump"
sys.path.insert(0, str(HP_DIR / "pipeline"))
from grid_common import HTTP_HEADERS, parse_aeso_zip  # noqa: E402

if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

# ─── CONFIG ────────────────────────────────────────────────────────────────

IESO_BASE = "https://reports-public.ieso.ca/public"
RAW_DIR = HP_DIR / "data" / "raw" / "ieso_history"
AESO_RAW_DIR = HP_DIR / "data" / "raw" / "aeso"
OUTPUT_DIR = REPO_ROOT / "grid_json"

FUEL_MONTHLY_START_YEAR = 2015     # GenOutputbyFuelMonthly archive start
CAPABILITY_MONTH_START = (2019, 5)  # GenOutputCapabilityMonth archive start
DEMAND_HOEP_START_YEAR = 2002       # Demand / PriceHOEPAverage archive start
INTERTIE_START_YEAR = 2018          # IntertieScheduleFlowYear archive start

# WIND/SOLAR have no "Capability" (registered capacity) row in
# GenOutputCapabilityMonth -- only "Available Capacity" (weather-adjusted
# forecast). Every other fuel in that report uses "Capability".
CAPABILITY_MEASUREMENT_BY_FUEL = defaultdict(lambda: "Capability")
CAPABILITY_MEASUREMENT_BY_FUEL.update({"WIND": "Available Capacity", "SOLAR": "Available Capacity"})

CAPACITY_METHODOLOGY_NOTE = (
    "Capacity-factor % = actual output / capacity, summed across all "
    "generators of that fuel type for the month, from IESO's Generator "
    "Output and Capability Month report. For GAS, HYDRO, NUCLEAR and "
    "BIOFUEL, 'capacity' is each generator's registered Capability "
    "(nameplate-like, roughly fixed). WIND and SOLAR report no such figure "
    "at all -- IESO's own denominator for them is 'Available Capacity', a "
    "weather-adjusted forecast of what those assets could produce that "
    "hour. So a wind/solar capacity-factor here answers 'what share of the "
    "wind/sun actually available did we use' (typically high, since "
    "there's little reason to curtail), not 'what share of installed "
    "nameplate capacity ran' (which would be low most hours by the nature "
    "of an intermittent resource) -- the two questions are genuinely "
    "different and this page answers the first one for those two fuels."
)

# ─── HTTP helpers ────────────────────────────────────────────────────────────


def fetch(url: str, dest: Path, force: bool = False, timeout: int = 120) -> Path | None:
    if not force and dest.exists() and dest.stat().st_size > 0:
        return dest
    r = requests.get(url, headers=HTTP_HEADERS, timeout=timeout)
    if r.status_code == 404:
        return None
    r.raise_for_status()
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(r.content)
    return dest


def month_range(start_year: int, start_month: int, end_year: int, end_month: int):
    y, m = start_year, start_month
    while (y, m) <= (end_year, end_month):
        yield y, m
        m += 1
        if m > 12:
            m = 1
            y += 1


# ─── ON: fuel mix (GenOutputbyFuelMonthly) ─────────────────────────────────


def fetch_on_fuel_monthly(this_year: int, refresh: bool) -> dict:
    """Returns {'YYYY-MM': {fuel: energy_GWh}}."""
    import xml.etree.ElementTree as ET
    ns = {"i": "http://www.ieso.ca/schema"}
    out = {}
    for year in range(FUEL_MONTHLY_START_YEAR, this_year + 1):
        dest = RAW_DIR / "fuel_monthly" / f"PUB_GenOutputbyFuelMonthly_{year}.xml"
        force = refresh or year == this_year
        path = fetch(f"{IESO_BASE}/GenOutputbyFuelMonthly/PUB_GenOutputbyFuelMonthly_{year}.xml", dest, force)
        if path is None:
            continue
        root = ET.parse(path).getroot()
        month_num = {m: i + 1 for i, m in enumerate(
            ["January", "February", "March", "April", "May", "June", "July",
             "August", "September", "October", "November", "December"])}
        for md in root.iter("{http://www.ieso.ca/schema}MonthData"):
            mname = md.find("i:Month", ns).text
            key = f"{year}-{month_num[mname]:02d}"
            fuels = {}
            for ft in md.findall("i:FuelTotal", ns):
                fuel = ft.find("i:Fuel", ns).text
                gwh = float(ft.find("i:EnergyGW", ns).text)
                fuels[fuel] = gwh
            out[key] = fuels
    return out


# ─── ON: capacity (GenOutputCapabilityMonth) ───────────────────────────────


def fetch_on_capacity_monthly(this_year: int, this_month: int, refresh: bool) -> dict:
    """Returns {'YYYY-MM': {fuel: {'output': MWh_ish, 'capacity': MWh_ish}}}."""
    out = {}
    for y, m in month_range(*CAPABILITY_MONTH_START, this_year, this_month):
        key = f"{y}-{m:02d}"
        fname = f"PUB_GenOutputCapabilityMonth_{y}{m:02d}.csv"
        dest = RAW_DIR / "capability_month" / fname
        force = refresh or (y, m) == (this_year, this_month)
        path = fetch(f"{IESO_BASE}/GenOutputCapabilityMonth/{fname}", dest, force)
        if path is None:
            continue
        df = pd.read_csv(path, skiprows=3, index_col=False)
        hour_cols = [c for c in df.columns if c.startswith("Hour ")]
        df[hour_cols] = df[hour_cols].apply(pd.to_numeric, errors="coerce")
        long = df.melt(id_vars=["Fuel Type", "Measurement"], value_vars=hour_cols, value_name="MW")
        long = long.dropna(subset=["MW"])
        sums = long.groupby(["Fuel Type", "Measurement"])["MW"].sum()

        fuels = {}
        for fuel in df["Fuel Type"].dropna().unique():
            cap_measure = CAPABILITY_MEASUREMENT_BY_FUEL[fuel]
            output = float(sums.get((fuel, "Output"), 0.0))
            capacity = float(sums.get((fuel, cap_measure), 0.0))
            fuels[fuel] = {"output": output, "capacity": capacity}
        out[key] = fuels
        print(f"  [capacity] {key}: {len(fuels)} fuels")
    return out


# ─── ON: demand ─────────────────────────────────────────────────────────────


def fetch_on_demand_monthly(this_year: int, refresh: bool) -> dict:
    """Returns {'YYYY-MM': {'mean_mw': x, 'peak_mw': x}}."""
    out = {}
    for year in range(DEMAND_HOEP_START_YEAR, this_year + 1):
        dest = RAW_DIR / "demand" / f"PUB_Demand_{year}.csv"
        force = refresh or year == this_year
        path = fetch(f"{IESO_BASE}/Demand/PUB_Demand_{year}.csv", dest, force)
        if path is None:
            continue
        df = pd.read_csv(path, skiprows=3, index_col=False)
        df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
        df = df.dropna(subset=["Date"])
        df["Month"] = df["Date"].dt.strftime("%Y-%m")
        df["Ontario Demand"] = pd.to_numeric(df["Ontario Demand"], errors="coerce")
        g = df.groupby("Month")["Ontario Demand"].agg(["mean", "max"])
        for month, row in g.iterrows():
            out[month] = {"mean_mw": round(row["mean"]), "peak_mw": round(row["max"])}
    return out


# ─── ON: HOEP ────────────────────────────────────────────────────────────────


def fetch_on_hoep_monthly(this_year: int, refresh: bool) -> dict:
    """Returns {'YYYY-MM': {'arithmetic_avg': x, 'weighted_avg': x}} ($/MWh)."""
    import xml.etree.ElementTree as ET
    ns = {"i": "http://www.ieso.ca/schema"}
    out = {}
    month_num = {m: i + 1 for i, m in enumerate(
        ["January", "February", "March", "April", "May", "June", "July",
         "August", "September", "October", "November", "December"])}
    for year in range(DEMAND_HOEP_START_YEAR, this_year + 1):
        dest = RAW_DIR / "hoep" / f"PUB_PriceHOEPAverage_{year}.xml"
        force = refresh or year == this_year
        path = fetch(f"{IESO_BASE}/PriceHOEPAverage/PUB_PriceHOEPAverage_{year}.xml", dest, force)
        if path is None:
            continue
        root = ET.parse(path).getroot()
        for hoep in root.iter("{http://www.ieso.ca/schema}HOEP"):
            mname = hoep.find("i:Month", ns).text
            key = f"{year}-{month_num[mname]:02d}"
            arith = hoep.find("i:ArithmeticAve", ns)
            weighted = hoep.find("i:WeightedAve", ns)
            out[key] = {
                "arithmetic_avg": float(arith.text) if arith is not None and arith.text else None,
                "weighted_avg": float(weighted.text) if weighted is not None and weighted.text else None,
            }
    return out


# ─── ON: intertie flows ─────────────────────────────────────────────────────


def classify_region(name: str) -> str:
    name = name.strip().upper()
    if name.startswith("PQ"):
        return "QUEBEC"
    if name.startswith("MANITOBA"):
        return "MANITOBA"
    if name.startswith("MICHIGAN"):
        return "MICHIGAN"
    if name.startswith("MINNESOTA"):
        return "MINNESOTA"
    if name.startswith("NEW-YORK") or name.startswith("NEW YORK"):
        return "NEW_YORK"
    return "OTHER"


def fetch_on_intertie_monthly(this_year: int, refresh: bool) -> dict:
    """Returns {'YYYY-MM': {region: net_flow_mw_mean}} (+ >0 = net import)."""
    out_hourly = defaultdict(list)  # region -> list of (month_key, flow)
    for year in range(INTERTIE_START_YEAR, this_year + 1):
        dest = RAW_DIR / "intertie" / f"PUB_IntertieScheduleFlowYear_{year}.csv"
        force = refresh or year == this_year
        path = fetch(f"{IESO_BASE}/IntertieScheduleFlowYear/PUB_IntertieScheduleFlowYear_{year}.csv", dest, force)
        if path is None:
            continue

        with open(path, encoding="utf-8") as fh:
            lines = fh.readlines()
        region_line = lines[3].rstrip("\n").split(",")
        metric_line = lines[4].rstrip("\n").split(",")
        # columns 0,1 = Date, Hour; remaining columns come in (Imp,Exp,Flow) triplets
        col_region = {}
        for i in range(2, len(metric_line)):
            if metric_line[i].strip() == "Flow":
                region = region_line[i].strip()
                if region and region.upper() != "TOTAL":
                    col_region[i] = classify_region(region)

        df = pd.read_csv(path, skiprows=5, header=None, index_col=False)
        df[0] = pd.to_datetime(df[0], errors="coerce")
        df = df.dropna(subset=[0])
        df["Month"] = df[0].dt.strftime("%Y-%m")

        for col_idx, region in col_region.items():
            vals = pd.to_numeric(df[col_idx], errors="coerce")
            tmp = pd.DataFrame({"Month": df["Month"], "Flow": vals}).dropna()
            for month, g in tmp.groupby("Month"):
                out_hourly[(month, region)].append(g["Flow"].mean())

    out = defaultdict(dict)
    for (month, region), means in out_hourly.items():
        out[month][region] = round(sum(means) / len(means), 1)
    return dict(out)


# ─── ON: Global Adjustment (short trailing window only, see docstring) ────


def fetch_on_global_adjustment(this_year: int, this_month: int, refresh: bool) -> list:
    """PUB_GlobalAdjustment.xml (no suffix) is only the CURRENT month's
    document -- each month is its own separate file
    (PUB_GlobalAdjustment_YYYYMM.xml), and the endpoint keeps roughly the
    last 13-14 of them with no deeper per-year archive (confirmed by
    directory listing, 2026-09-02). So this loops back a generous 18 months
    from today and lets 404s (fetch() returning None) mark where the
    archive actually ends, rather than assuming a fixed count."""
    import xml.etree.ElementTree as ET
    ns = {"i": "http://www.ieso.ca/schema"}
    rows = []
    y, m = this_year, this_month
    for _ in range(18):
        fname = f"PUB_GlobalAdjustment_{y}{m:02d}.xml"
        dest = RAW_DIR / "global_adjustment" / fname
        force = refresh or (y, m) == (this_year, this_month)
        path = fetch(f"{IESO_BASE}/GlobalAdjustment/{fname}", dest, force)
        m -= 1
        if m < 1:
            m, y = 12, y - 1
        if path is None:
            continue
        root = ET.parse(path).getroot()
        body = root.find("i:DocBody", ns)
        if body is None:
            continue
        trade_month = body.find("i:TradeMonth", ns)
        gav = body.find("i:GAValues", ns)
        if trade_month is None or gav is None:
            continue
        actual = gav.find("i:ActualRate", ns)
        second = gav.find("i:SecondEstimateRate", ns)
        first = gav.find("i:FirstEstimateRate", ns)
        if actual is not None and actual.text:
            rate, rate_type = float(actual.text), "actual"
        elif second is not None and second.text:
            rate, rate_type = float(second.text), "second_estimate"
        elif first is not None and first.text:
            rate, rate_type = float(first.text), "first_estimate"
        else:
            continue
        rows.append({"month": trade_month.text, "rate_cad_per_mwh": rate, "rate_type": rate_type})
    return sorted(rows, key=lambda r: r["month"])


# ─── AB: fuel mix + capacity (already-cached AESO zips) ───────────────────


def build_ab_monthly() -> dict:
    """Returns {'YYYY-MM': {'fuel_mix': {fuel: frac}, 'capacity_factor': {fuel: frac}}}."""
    zip_paths = sorted(AESO_RAW_DIR.glob("*.zip"))
    if not zip_paths:
        print("  [warn] AB: no cached AESO zips found -- skipping AB history")
        return {}

    frames = []
    for path in zip_paths:
        agg = parse_aeso_zip(str(path))
        if not agg.empty:
            frames.append(agg)
    long = pd.concat(frames, ignore_index=True)
    long["Date"] = pd.to_datetime(long["Date"])
    long["Month"] = long["Date"].dt.strftime("%Y-%m")
    monthly = long.groupby(["Month", "Fuel Type"], as_index=False).agg(
        Output_MW=("Output_MW", "sum"), Capacity_MW=("Capacity_MW", "sum")
    )

    out = {}
    for month, g in monthly.groupby("Month"):
        total_output = g["Output_MW"].sum()
        fuel_mix, cap_factor = {}, {}
        for row in g.itertuples(index=False):
            fuel_mix[row._1] = round(row.Output_MW / total_output, 4) if total_output > 0 else 0.0
            # ENERGY STORAGE nets charge/discharge -- "capacity factor" isn't
            # a meaningful concept for it (can be negative), so it's excluded
            # from the capacity side only; it still counts in fuel_mix above.
            if row._1 not in ("ENERGY STORAGE",) and row.Capacity_MW > 0:
                cap_factor[row._1] = round(row.Output_MW / row.Capacity_MW, 4)
        out[month] = {"fuel_mix": fuel_mix, "capacity_factor": cap_factor}
    return out


# ─── ASSEMBLE + WRITE ───────────────────────────────────────────────────────


def write_json(path: Path, payload: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, separators=(",", ":"))
    size_kb = path.stat().st_size / 1024
    print(f"[ok] {path.name}: {size_kb:.1f} KB")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true",
                     help="also re-fetch the current (still-open) period for every source")
    args = ap.parse_args()

    now = datetime.now()
    this_year, this_month = now.year, now.month

    print("=" * 60)
    print("Grid Dashboard deep-history ETL -- ON (IESO) + AB (cached AESO)")
    print("=" * 60)

    print("\n--- ON fuel mix (GenOutputbyFuelMonthly, 2015-present) ---")
    fuel_mix_raw = fetch_on_fuel_monthly(this_year, args.refresh)
    print(f"  {len(fuel_mix_raw)} months")

    print("\n--- ON capacity (GenOutputCapabilityMonth, 2019-05-present) ---")
    capacity_raw = fetch_on_capacity_monthly(this_year, this_month, args.refresh)
    print(f"  {len(capacity_raw)} months")

    print("\n--- ON demand (Demand, 2002-present) ---")
    demand_raw = fetch_on_demand_monthly(this_year, args.refresh)
    print(f"  {len(demand_raw)} months")

    print("\n--- ON HOEP (PriceHOEPAverage, 2002-present) ---")
    hoep_raw = fetch_on_hoep_monthly(this_year, args.refresh)
    print(f"  {len(hoep_raw)} months")

    print("\n--- ON intertie flows (IntertieScheduleFlowYear, 2018-present) ---")
    intertie_raw = fetch_on_intertie_monthly(this_year, args.refresh)
    print(f"  {len(intertie_raw)} months")

    print("\n--- ON Global Adjustment (trailing window only) ---")
    ga_rows = fetch_on_global_adjustment(this_year, this_month, args.refresh)
    print(f"  {len(ga_rows)} months (source retains no deeper archive)")

    all_months = sorted(set(fuel_mix_raw) | set(capacity_raw) | set(demand_raw)
                         | set(hoep_raw) | set(intertie_raw))

    fuel_names_on = sorted({f for fuels in fuel_mix_raw.values() for f in fuels})

    monthly_rows = []
    for month in all_months:
        row = {"month": month}
        fm = fuel_mix_raw.get(month)
        if fm:
            total = sum(fm.values())
            row["fuel_mix"] = {f: round(fm.get(f, 0.0) / total, 4) for f in fuel_names_on} if total > 0 else None
        else:
            row["fuel_mix"] = None

        cap = capacity_raw.get(month)
        if cap:
            row["capacity_factor"] = {
                f: round(v["output"] / v["capacity"], 4) if v["capacity"] > 0 else None
                for f, v in cap.items()
            }
        else:
            row["capacity_factor"] = None

        dem = demand_raw.get(month)
        row["demand_mw_mean"] = dem["mean_mw"] if dem else None
        row["demand_mw_peak"] = dem["peak_mw"] if dem else None

        hoep = hoep_raw.get(month)
        row["hoep_arith_avg"] = hoep["arithmetic_avg"] if hoep else None
        row["hoep_weighted_avg"] = hoep["weighted_avg"] if hoep else None

        row["intertie_net_mw"] = intertie_raw.get(month) or None

        monthly_rows.append(row)

    on_payload = {
        "meta": {
            "province": "ON",
            "fuels": fuel_names_on,
            "sources": {
                "fuel_mix": "IESO Generator Output by Fuel Type Monthly, 2015-present",
                "capacity_factor": "IESO Generator Output and Capability Month, 2019-05-present",
                "demand": "IESO Hourly Demand Report (Ontario Demand column), 2002-present",
                "hoep": "IESO HOEP Monthly Averages Report, 2002-present",
                "intertie_net_mw": "IESO Yearly Intertie Schedule and Flow Report, 2018-present, "
                                    "tie-lines grouped to parent jurisdiction; positive = net import to ON",
                "global_adjustment": "IESO Global Adjustment Class B Rates -- source retains only a "
                                      "rolling ~13-month window, no yearly archive; see global_adjustment_monthly",
            },
            "capacity_methodology": CAPACITY_METHODOLOGY_NOTE,
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        },
        "monthly": monthly_rows,
        "global_adjustment_monthly": ga_rows,
    }
    write_json(OUTPUT_DIR / "grid_on_history.json", on_payload)

    print("\n--- AB fuel mix + capacity (cached AESO zips, 2015-present) ---")
    ab_monthly_raw = build_ab_monthly()
    fuel_names_ab = sorted({f for v in ab_monthly_raw.values() for f in v["fuel_mix"]})
    ab_rows = [
        {"month": m, "fuel_mix": v["fuel_mix"], "capacity_factor": v["capacity_factor"]}
        for m, v in sorted(ab_monthly_raw.items())
    ]
    ab_payload = {
        "meta": {
            "province": "AB",
            "fuels": fuel_names_ab,
            "sources": {
                "fuel_mix": "AESO CSD Generation (Hourly), manually refreshed, cached 2015-present",
                "capacity_factor": "Same source, 'Maximum Capability' column per asset; "
                                    "ENERGY STORAGE excluded from capacity_factor only (net charge/"
                                    "discharge makes a capacity-factor % meaningless for it), still "
                                    "counted in fuel_mix",
            },
            "capacity_methodology": (
                "capacity_factor % = sum(Output)/sum(Maximum Capability) across all assets of that "
                "fuel type for the month, from AESO's per-asset CSD data. Unlike Ontario, this figure "
                "exists uniformly for every fuel type including wind and solar (AESO reports Maximum "
                "Capability per asset per hour directly, not split into a separate weather-adjusted "
                "series the way IESO's report is) -- so AB's wind/solar capacity-factor and ON's are "
                "not directly comparable without accounting for that difference."
            ),
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        },
        "monthly": ab_rows,
    }
    write_json(OUTPUT_DIR / "grid_ab_history.json", ab_payload)

    print("\n[ok] grid_history_etl.py complete.")


if __name__ == "__main__":
    main()
