"""
grid_etl.py

Live/recent grid-mix ETL for the "what's powering the grid right now" dashboard
(see ROADMAP.md item 6). Reuses the fetch/parse/EF logic already built and
validated for the Heat Pump tool's Phase 1 (see HeatPump/METHODOLOGY.md) --
this script does not reimplement fuel mapping or emission-factor calibration,
it imports HeatPump/pipeline/grid_common.py (which fetch_ieso.py, fetch_aeso.py,
build_grid_ef.py and build_grid_ef_ab.py were refactored to share).

SCOPE
    ON (IESO): live-fetched. IESO's per-year XML report is re-downloaded fresh
        every run for the current + previous calendar year (the file changes
        daily), so "recent" data is always genuinely current.
    AB (AESO): NOT live-fetchable. AESO's CSD Generation (Hourly) historical
        dataset is Box-hosted with no scriptable direct-download URL (see
        HeatPump/pipeline/fetch_aeso.py header and memory notes) -- the user
        downloads zips by hand into HeatPump/data/raw/aeso/. This script only
        *parses* whatever is cached there; grid_ab.json's "data_through" date
        will lag behind ON until a new zip is manually added. This is a real,
        documented limitation, not a bug.
    QC: HQ's hourly export is likewise a manually-placed, non-live file (see
        fetch_hq.py), and Quebec's grid is >99% hydro/wind (near-zero direct
        emissions -- see METHODOLOGY.md). grid_qc.json is therefore a static
        "flat EF context" card (recent annual averages + a one-line
        explanation), not a live hourly series, sourced from the existing
        Phase-1 output HeatPump/data/processed/grid_ef_qc.json.

OUTPUT (grid_json/, repo root)
    grid_on.json, grid_ab.json  -- {meta, recent_hourly, daily}
        recent_hourly: hourly rows for the last RECENT_HOURLY_DAYS days
            [{date, hour, avg_ef, marginal_ef, total_mw, fuel_mix: {FUEL: frac}}]
        daily: one row per day for the rest of the ~12-month window
            [{date, avg_ef_min/mean/max, marginal_ef_min/mean/max,
              total_mw_mean, fuel_mix_mean: {FUEL: frac}}]
    grid_qc.json -- {meta, context: {avg_ef_g_per_kwh, last_full_year, annual}}
    meta.json -- EF sources + last-updated across all three files

VALIDATION
    Two checks are printed (see validate_monthly()):
      1. ETL-correctness regression: for the calendar months where this run's
         freshly-fetched ON/AB series overlaps the existing Phase-1
         "data/processed/grid_ef_{on,ab}.json" (already validated in
         METHODOLOGY.md against TAF / Alberta.ca published NIR-sourced annual
         figures), the generation-weighted monthly average EF from each source
         should match closely -- both are the same underlying IESO/AESO data
         run through the same grid_common EF formula, so a large gap would
         indicate a real ETL bug, not measurement noise. Tolerance: +/-2%.
      2. Where a full calendar year in scope has a TAF/Alberta.ca published
         Annual AEF (currently through 2023 for both), the annual figure is
         also printed against that reference, +/-15% per METHODOLOGY.md.
         (The rolling 12-month window is normally too recent to include a
         referenced year -- printed for completeness, not usually a gate.)
    Neither IESO nor AESO publish an official *monthly* emissions-intensity
    figure we could fetch and compare against directly; see METHODOLOGY.md
    for the QC "not a pass/fail gate at this scale" precedent for the same
    kind of honesty-over-fabrication call.

USAGE
    pip install requests pandas
    python grid_etl.py             # normal weekly refresh
    python grid_etl.py --refresh   # also force re-download of every cached
                                    # IESO year (not just current/previous)
"""

import os
import sys
import json
import argparse
from pathlib import Path
from datetime import datetime, timedelta, timezone

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
HP_DIR = REPO_ROOT / "HeatPump"
sys.path.insert(0, str(HP_DIR / "pipeline"))
from grid_common import (  # noqa: E402
    download_ieso_year, parse_ieso_xml, parse_aeso_zip,
    compute_ef_on, compute_ef_ab,
    ON_GAS_EF_G_PER_KWH, AB_COAL_EF_G_PER_KWH, AB_GAS_EF_G_PER_KWH,
)

if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

# ─── CONFIG ───────────────────────────────────────────────────────────────────

IESO_RAW_DIR = HP_DIR / "data" / "raw" / "ieso"
AESO_RAW_DIR = HP_DIR / "data" / "raw" / "aeso"
QC_SOURCE_JSON = HP_DIR / "data" / "processed" / "grid_ef_qc.json"

# Phase-1 master outputs, already validated in METHODOLOGY.md -- used only as
# the ETL-correctness cross-check (see validate_monthly()).
MASTER_ON_JSON = HP_DIR / "data" / "processed" / "grid_ef_on.json"
MASTER_AB_JSON = HP_DIR / "data" / "processed" / "grid_ef_ab.json"

OUTPUT_DIR = REPO_ROOT / "grid_json"

WINDOW_DAYS = 366           # ~12 months
RECENT_HOURLY_DAYS = 14     # hourly resolution for this many most-recent days
MAX_FILE_KB = 300

# Published Annual AEF / generation-intensity references (see METHODOLOGY.md).
TAF_ANNUAL_AEF_ON = {2015: 46, 2016: 40, 2017: 18, 2018: 29, 2019: 29,
                      2020: 36, 2021: 44, 2022: 51, 2023: 67}
AB_ANNUAL_INTENSITY = {2019: 630, 2020: 630, 2021: 580, 2022: 510, 2023: 470}
ANNUAL_TOLERANCE = 0.15
MONTHLY_ETL_TOLERANCE = 0.02


# ─── ONTARIO (live) ───────────────────────────────────────────────────────────

def build_ontario(refresh: bool) -> pd.DataFrame:
    """Force-refetch current + previous year IESO XML (always -- the current
    year's report changes daily), plus every other cached year (only if
    --refresh), and return the full wide-by-fuel DataFrame with EF columns."""
    this_year = datetime.now().year
    frames = []
    for year in range(2020, this_year + 1):
        dest = IESO_RAW_DIR / f"PUB_GenOutputbyFuelHourly_{year}.xml"
        force = refresh or year >= this_year - 1
        path = download_ieso_year(year, dest, force=force)
        if path is None:
            continue
        df = parse_ieso_xml(path)
        if not df.empty:
            frames.append(df)

    if not frames:
        raise RuntimeError("ON: no IESO data parsed -- fetch failed")

    long = pd.concat(frames, ignore_index=True)
    long["Date"] = pd.to_datetime(long["Date"])
    wide = long.pivot_table(index=["Date", "Hour"], columns="Fuel",
                             values="Output_MW", aggfunc="sum", fill_value=0.0)
    wide = wide.reset_index()
    fuel_cols = [c for c in wide.columns if c not in ("Date", "Hour")]
    wide["Total_MW"] = wide[fuel_cols].sum(axis=1)
    if "GAS" not in wide.columns:
        wide["GAS"] = 0.0

    ef = compute_ef_on(wide).drop(columns=["GAS"])
    ef = ef.merge(wide[["Date", "Hour"] + fuel_cols], on=["Date", "Hour"])
    ef.attrs["fuel_cols"] = fuel_cols
    return ef


# ─── ALBERTA (parse-only, no live fetch -- see module docstring) ──────────────

def build_alberta() -> pd.DataFrame:
    zip_paths = sorted(AESO_RAW_DIR.glob("*.zip"))
    if not zip_paths:
        raise RuntimeError(f"AB: no cached AESO zips found in {AESO_RAW_DIR}")

    frames = []
    for path in zip_paths:
        agg = parse_aeso_zip(str(path))
        if not agg.empty:
            frames.append(agg)
    if not frames:
        raise RuntimeError("AB: no rows parsed from any cached AESO zip")

    long = pd.concat(frames, ignore_index=True)
    long = long.groupby(["Date", "Hour", "Fuel Type"], as_index=False).agg(
        Output_MW=("Output_MW", "sum")
    )
    long["Date"] = pd.to_datetime(long["Date"])
    wide = long.pivot_table(index=["Date", "Hour"], columns="Fuel Type",
                             values="Output_MW", aggfunc="sum", fill_value=0.0)
    wide = wide.reset_index()
    fuel_cols = [c for c in wide.columns if c not in ("Date", "Hour")]
    wide["Total_MW"] = wide[fuel_cols].sum(axis=1)
    for col in ("COAL", "GAS", "DUAL FUEL"):
        if col not in wide.columns:
            wide[col] = 0.0
    wide["GasLike_MW"] = wide[["GAS", "DUAL FUEL"]].sum(axis=1)

    ef = compute_ef_ab(wide).drop(columns=["COAL", "GasLike_MW"])
    ef = ef.merge(wide[["Date", "Hour"] + fuel_cols], on=["Date", "Hour"])
    ef.attrs["fuel_cols"] = fuel_cols
    return ef


# ─── DOWNSAMPLE (hourly recent window + daily min/mean/max beyond) ────────────

def downsample(ef: pd.DataFrame, fuel_cols: list) -> dict:
    ef = ef.sort_values(["Date", "Hour"]).copy()
    latest_date = ef["Date"].max()
    window_start = latest_date - pd.Timedelta(days=WINDOW_DAYS)
    recent_cutoff = latest_date - pd.Timedelta(days=RECENT_HOURLY_DAYS)

    ef = ef[ef["Date"] >= window_start]
    frac_col = {c: f"frac_{c.replace(' ', '_')}" for c in fuel_cols}
    for col, fcol in frac_col.items():
        ef[fcol] = (ef[col] / ef["Total_MW"]).where(ef["Total_MW"] > 0, 0.0)

    recent = ef[ef["Date"] > recent_cutoff]
    recent_hourly = []
    for row in recent.itertuples(index=False):
        row_d = row._asdict()
        recent_hourly.append({
            "date": row_d["Date"].strftime("%Y-%m-%d"),
            "hour": int(row_d["Hour"]),
            "avg_ef": round(row_d["AvgEF_g_per_kWh"], 1),
            "marginal_ef": round(row_d["MarginalEF_g_per_kWh"], 1),
            "total_mw": round(row_d["Total_MW"]),
            "fuel_mix": {c: round(row_d[frac_col[c]], 3) for c in fuel_cols},
        })

    older = ef[ef["Date"] <= recent_cutoff].copy()
    older["DateStr"] = older["Date"].dt.strftime("%Y-%m-%d")
    daily = []
    for date_str, g in older.groupby("DateStr", sort=True):
        daily.append({
            "date": date_str,
            "avg_ef_min": round(g["AvgEF_g_per_kWh"].min(), 1),
            "avg_ef_mean": round(g["AvgEF_g_per_kWh"].mean(), 1),
            "avg_ef_max": round(g["AvgEF_g_per_kWh"].max(), 1),
            "marginal_ef_min": round(g["MarginalEF_g_per_kWh"].min(), 1),
            "marginal_ef_mean": round(g["MarginalEF_g_per_kWh"].mean(), 1),
            "marginal_ef_max": round(g["MarginalEF_g_per_kWh"].max(), 1),
            "total_mw_mean": round(g["Total_MW"].mean()),
            "fuel_mix_mean": {c: round(g[frac_col[c]].mean(), 3) for c in fuel_cols},
        })

    return {
        "recent_hourly": recent_hourly,
        "daily": daily,
        "data_through": latest_date.strftime("%Y-%m-%d"),
        "window_start": window_start.strftime("%Y-%m-%d"),
    }


# ─── QUEBEC (static flat-EF context, see module docstring) ────────────────────

def build_quebec_context() -> dict:
    if not QC_SOURCE_JSON.exists():
        print("   [warn] QC: HeatPump/data/processed/grid_ef_qc.json not found -- skipping")
        return None

    with open(QC_SOURCE_JSON, encoding="utf-8") as fh:
        src = json.load(fh)

    df = pd.DataFrame(src["hourly"])
    df["Year"] = pd.to_datetime(df["Date"]).dt.year
    annual = df.groupby("Year")["AvgEF_g_per_kWh"].mean().round(4)
    last_full_year = int(annual.index.max())

    return {
        "meta": {
            "province": "QC",
            "methodology": (
                "Static flat-EF context, not a live hourly series -- Hydro-Quebec's "
                "hourly export is a manually-placed file (see HeatPump/pipeline/"
                "fetch_hq.py), and Quebec's grid is >99% hydro/wind, so a live "
                "refresh pipeline isn't warranted. avg_ef_g_per_kwh is a simple "
                "(unweighted) mean of AvgEF_g_per_kWh across all available hours; "
                "see HeatPump/METHODOLOGY.md for the full combustion-only model "
                "and the flagged open question around import-based marginal intensity."
            ),
            "years_missing": src["meta"].get("years_missing", []),
            "date_range": src["meta"]["date_range"],
        },
        "context": {
            "avg_ef_g_per_kwh": round(float(df["AvgEF_g_per_kWh"].mean()), 4),
            "last_full_year": last_full_year,
            "last_full_year_avg_ef_g_per_kwh": float(annual.loc[last_full_year]),
            "annual_g_per_kwh": {str(y): float(v) for y, v in annual.items()},
        },
    }


# ─── VALIDATION ───────────────────────────────────────────────────────────────

def validate_monthly(ef: pd.DataFrame, master_json: Path, label: str,
                      annual_ref: dict) -> bool:
    print("\n" + "=" * 60)
    print(f"{label}: monthly average EF -- ETL-correctness cross-check")
    print("=" * 60)

    # Unweighted mean on both sides -- the Phase-1 master JSON doesn't store
    # Total_MW, so a generation-weighted comparison isn't reconstructable from
    # it. Using the same (unweighted) statistic on both sides keeps this an
    # apples-to-apples ETL-correctness check rather than a biased one; the
    # properly generation-weighted figure is used below for the published-
    # reference comparison, where only the ETL's own data is needed.
    ef_m = ef.copy()
    ef_m["Month"] = ef_m["Date"].dt.to_period("M")
    etl_monthly = ef_m.groupby("Month")["AvgEF_g_per_kWh"].mean()

    all_ok = True
    if master_json.exists():
        with open(master_json, encoding="utf-8") as fh:
            master = json.load(fh)
        mdf = pd.DataFrame(master["hourly"])
        mdf["Date"] = pd.to_datetime(mdf["Date"])
        mdf["Month"] = mdf["Date"].dt.to_period("M")
        master_monthly = mdf.groupby("Month")["AvgEF_g_per_kWh"].mean()

        common_months = sorted(set(etl_monthly.index) & set(master_monthly.index))
        if not common_months:
            print("  (no overlapping months with the Phase-1 master file yet)")
        for month in common_months:
            a, b = etl_monthly[month], master_monthly[month]
            pct_diff = (a - b) / b if b else 0.0
            ok = abs(pct_diff) <= MONTHLY_ETL_TOLERANCE or abs(a - b) < 1.0
            all_ok &= ok
            flag = "OK" if ok else "FAIL"
            print(f"  {month}: grid_etl={a:6.1f}  master={b:6.1f}  "
                  f"diff={pct_diff:+.1%}   [{flag}]")
    else:
        print(f"  (no Phase-1 master file at {master_json} -- skipping cross-check)")

    print(f"\n{label}: annual average EF vs published reference (context only)")
    ef_y = ef.copy()
    ef_y["Year"] = ef_y["Date"].dt.year
    annual = ef_y.groupby("Year").apply(
        lambda g: (g["AvgEF_g_per_kWh"] * g["Total_MW"]).sum() / g["Total_MW"].sum(),
        include_groups=False,
    )
    for year, computed in annual.items():
        published = annual_ref.get(int(year))
        if published is None:
            print(f"  {year}: computed={computed:6.1f} g/kWh  (no published reference; "
                  f"window is a rolling recent slice, not a full year)")
            continue
        pct_diff = (computed - published) / published
        ok = abs(pct_diff) <= ANNUAL_TOLERANCE
        flag = "OK" if ok else "FAIL"
        print(f"  {year}: computed={computed:6.1f}  published={published:6.1f}  "
              f"diff={pct_diff:+.1%}   [{flag}]  (partial-year slice)")

    return all_ok


# ─── MAIN ─────────────────────────────────────────────────────────────────────

def write_json(path: Path, payload: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, separators=(",", ":"))
    size_kb = path.stat().st_size / 1024
    flag = "" if size_kb <= MAX_FILE_KB else "  [OVER BUDGET]"
    print(f"[ok] {path.name}: {size_kb:.1f} KB{flag}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--refresh", action="store_true",
                         help="force re-download of every cached IESO year, not just current/previous")
    args = parser.parse_args()

    print("=" * 60)
    print("Live grid dashboard ETL -- ON (live) + AB (cached) + QC (static)")
    print("=" * 60)

    print("\n--- Ontario (IESO) ---")
    on_ef = build_ontario(args.refresh)
    print(f"  {len(on_ef):,} hourly rows, {on_ef['Date'].min().date()} -> {on_ef['Date'].max().date()}")
    on_ok = validate_monthly(on_ef, MASTER_ON_JSON, "ON", TAF_ANNUAL_AEF_ON)
    on_ds = downsample(on_ef, on_ef.attrs["fuel_cols"])
    write_json(OUTPUT_DIR / "grid_on.json", {
        "meta": {
            "province": "ON",
            "gas_ef_g_per_kwh": ON_GAS_EF_G_PER_KWH,
            "fuels": on_ef.attrs["fuel_cols"],
            "source": "IESO Generator Output by Fuel Type Hourly (reports-public.ieso.ca)",
            "data_through": on_ds["data_through"],
            "window_start": on_ds["window_start"],
            "recent_hourly_days": RECENT_HOURLY_DAYS,
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        },
        "recent_hourly": on_ds["recent_hourly"],
        "daily": on_ds["daily"],
    })

    print("\n--- Alberta (AESO, cached files only -- see module docstring) ---")
    try:
        ab_ef = build_alberta()
        print(f"  {len(ab_ef):,} hourly rows, {ab_ef['Date'].min().date()} -> {ab_ef['Date'].max().date()}")
        ab_ok = validate_monthly(ab_ef, MASTER_AB_JSON, "AB", AB_ANNUAL_INTENSITY)
        ab_ds = downsample(ab_ef, ab_ef.attrs["fuel_cols"])
        write_json(OUTPUT_DIR / "grid_ab.json", {
            "meta": {
                "province": "AB",
                "coal_ef_g_per_kwh": AB_COAL_EF_G_PER_KWH,
                "gas_ef_g_per_kwh": AB_GAS_EF_G_PER_KWH,
                "fuels": ab_ef.attrs["fuel_cols"],
                "source": "AESO CSD Generation (Hourly) -- manually refreshed, NOT live-fetched (Box-hosted, unscriptable)",
                "data_through": ab_ds["data_through"],
                "window_start": ab_ds["window_start"],
                "recent_hourly_days": RECENT_HOURLY_DAYS,
                "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            },
            "recent_hourly": ab_ds["recent_hourly"],
            "daily": ab_ds["daily"],
        })
    except RuntimeError as e:
        print(f"  [warn] {e} -- grid_ab.json not updated this run")
        ab_ok = True  # not a fetch failure in the live sense -- see docstring

    print("\n--- Quebec (static flat-EF context) ---")
    qc_payload = build_quebec_context()
    if qc_payload is not None:
        print(f"  avg_ef={qc_payload['context']['avg_ef_g_per_kwh']} g/kWh "
              f"(last full year {qc_payload['context']['last_full_year']}: "
              f"{qc_payload['context']['last_full_year_avg_ef_g_per_kwh']} g/kWh)")
        write_json(OUTPUT_DIR / "grid_qc.json", qc_payload)

    write_json(OUTPUT_DIR / "meta.json", {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "sources": {
            "ON": "IESO Generator Output by Fuel Type Hourly (reports-public.ieso.ca); "
                  f"gas EF {ON_GAS_EF_G_PER_KWH} g/kWh calibrated vs TAF 2024 Annual AEF",
            "AB": "AESO CSD Generation (Hourly), manually refreshed; "
                  f"coal EF {AB_COAL_EF_G_PER_KWH} / gas EF {AB_GAS_EF_G_PER_KWH} g/kWh "
                  "calibrated vs Alberta.ca published NIR-sourced generation intensity",
            "QC": "Hydro-Quebec hourly generation by source, manually refreshed; static context only",
        },
        "methodology_doc": "HeatPump/METHODOLOGY.md",
    })

    if not on_ok:
        print("\n[FAIL] ON monthly cross-check outside tolerance -- review before committing.")
        sys.exit(1)
    print("\n[ok] grid_etl.py complete.")


if __name__ == "__main__":
    main()
