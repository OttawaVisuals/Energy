"""
Per-house design load, annual heating energy, and balance point (0-heat
point) for every ERS home in each heatpump.html dropdown city -- ships the
FULL population per city (no sampling), for a page section that lets a
user filter by house category and see the worst/best/representative homes
within the filtered set.

WHY THIS EXISTS
----------------
Follow-up on check_balance_point_k1s.py (single FSA, K1S) and
build_city_fsa_list.py (clean per-city FSA lists via Canada Post). User
wants, per city: every home's peak load (kW) + annual heating energy (kWh)
+ implied balance point, tagged with type/size/vintage/storeys, shipped to
the page so worst/best/representative selection can run client-side on
whatever subset the user's filters narrow down to.

CONSUMED vs. DELIVERED ENERGY (fixed 2026-08-11 -- see below)
----------------------------------------------------------------
Pre_HeatEnergy (EGHFURNACEAEC) is fuel/electricity CONSUMED by the primary
heating system, not heat DELIVERED to the building -- those only match for
electric-resistance heat (COP 1). The first version of this script used
Pre_HeatEnergy directly, which is thermally inconsistent with Pre_HeatLoss
(a delivered-heat quantity) for any home whose pre-retrofit system already
has a COP or AFUE away from 1. Caught when an Ottawa home with a
pre-retrofit ground-source heat pump (Pre_HPCOP 3.0) ranked as the city's
"best" home purely because its 10,587 kWh consumed looked tiny next to its
19.1 kW peak -- the model-implied heat actually delivered is ~3x that.
Fixed using the exact conversion already validated in build_archetypes.py:
`Pre_HeatDelivered = Pre_HeatEnergy * (Pre_HeatSeasonalCOP / 100)`
(EGHFURSEASEFF: an AFUE-style seasonal efficiency percentage for combustion
equipment, and >100 for heat pumps), screened to the same plausible 30-400
range that script uses. Below 30 is missing/junk data; above 400 is a
mis-scaled record. All balance-point solving and the annual-energy field
shipped to the page now use Pre_HeatDelivered, not raw Pre_HeatEnergy.

METHOD -- vectorized balance-point solve
------------------------------------------
A per-house scipy.brentq loop (as in check_balance_point_k1s.py) does not
scale to ~800k homes across 14 cities in reasonable time. Reformulated so
an entire city solves in one vectorized pass:
  DDH(T0) = sum over TMY hours of max(T0 - T_hour, 0)      [degree-hours]
  h(T0)   = DDH(T0) / (T0 - T_design)
  predicted annual energy = HeatLoss(design) * h(T0)

h(T0) depends only on the city's own TMY + design temp, not on any one
house -- computed ONCE per city on a fine T0 grid, then every house's
balance point is a single vectorized `np.interp` against its own
target = HeatEnergy / HeatLoss. h(T0) has a small non-monotonic dip
immediately above T_design (verified numerically, e.g. Ottawa dips from
~141 at T_design+0.5C to a minimum near T_design+4C before rising
monotonically to ~3700 by 30C); solving is restricted to the monotonic
branch from that minimum upward. A house whose target falls outside that
branch's range is unsolvable in this no-gains model (implausible energy
for its design load) -- reported per city, not silently dropped.

Toronto (289,656 homes, largest dropdown city) solves end-to-end in ~5s.

WORST/BEST SELECTION (documented here; computed client-side, not baked in)
-----------------------------------------------------------------------------
Peak load and annual energy correlate strongly across a city (Pearson
r=0.89 for Toronto) but NOT perfectly -- the single highest-peak home is
not the single highest-energy home (confirmed: Toronto's top-peak house is
at the 100th energy percentile but isn't literally the max). So "worst" is
defined as the home maximizing min(peak_percentile, energy_percentile) --
bad on BOTH axes simultaneously, not just one -- and "best" as the home
minimizing max(peak_percentile, energy_percentile). Percentiles are
recomputed within whatever filtered subset the page's dropdowns select, so
this file ships raw values only; no worst/best is precomputed here.
Outlier guard (confirmed with user 2026-08-11): a literal min/max of that
score picked up at least one implausible row (a 288.7 m^2 Toronto detached
home somehow at 189.8 kW design loss, ~0.66 kW/m^2 -- 4-10x a normal
detached home's 0.05-0.15 kW/m^2 range, almost certainly a data-entry
error). The page must therefore treat "worst"/"best" as the 99th/1st
percentile of that combined score within the filtered subset, not the
literal extreme, so one bad ERS row can't stretch the displayed range.

CATEGORIES (from ERS fields already in ers_web_<PROV>.parquet)
----------------------------------------------------------------
BldgType   -> canonical: detached / semi_duplex / row_end / row_middle /
              apartment / mobile / triplex (source has case-duplicated and
              near-duplicate labels, e.g. "Single detached" vs "Single
              Detached" -- folded together, see BLDGTYPE_MAP)
Storeys    -> canonical: 1 / 1.5 / 2 / 2.5 / 3 / split / split_entry
YearBuilt  -> decade bucket (pre-1946 pooled as "pre1946")
FloorArea  -> kept as the raw m^2 value -- size buckets are a page-side
              filter choice, not baked into the data

INPUT:  HeatPump/data/processed/city_fsa_list.json
        C:\\ERS\\web\\ers_web_<PROV>.parquet
        HeatPump/data/processed/city_design_temps.json
        HeatPump/data/processed/tmy_temps.json
OUTPUT: HeatPump/data/processed/house_profiles_<city_slug>.json, one per city
        printed per-city solve stats + size report (raw + gzip), and a
        combined total across all 14 cities

LIMITATIONS
-----------
- Pre-retrofit (Pre_HeatLoss / Pre_HeatEnergy) only, same as
  check_balance_point_k1s.py -- the home's ORIGINAL condition, not any
  retrofit outcome.
- balance_point_T0_C inherits check_balance_point_k1s.py's caveat: a
  no-gains straight-line model, so T0 is an "effective" balance point
  absorbing real internal/solar gains, occupant behaviour and TMY-vs-actual-
  year weather deviation, not a physical measurement.
- City design temp is a single city-wide constant (house-weighted mean over
  real ERS homes' own weather stations), not a per-house station join.
"""
from __future__ import annotations

import gzip
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "processed"
OUT_DIR = ROOT / "data" / "processed"
ERS_WEB_DIR = Path(r"C:\ERS\web")

CITY_PROV = {
    "Ottawa": "ON", "Toronto": "ON", "Hamilton": "ON", "London": "ON", "Windsor": "ON",
    "Montreal": "QC", "Quebec City": "QC",
    "Calgary": "AB", "Edmonton": "AB",
    "Vancouver": "BC", "Winnipeg": "MB", "Halifax": "NS",
    "Saskatoon": "SK", "Regina": "SK",
}
CITY_TO_DESIGNTEMP_KEY = {"Ottawa": "Ottawa-Gatineau"}  # everything else matches verbatim
T0_MAX = 30.0

BLDGTYPE_MAP = {
    "single detached": "detached",
    "double/semi-detached": "semi_duplex",
    "double/semi detached": "semi_duplex",
    "detached duplex": "semi_duplex",
    "attached duplex": "semi_duplex",
    "duplex (non-murb)": "semi_duplex",
    "row house, end unit": "row_end",
    "row, end unit": "row_end",
    "row house, middle unit": "row_middle",
    "row, middle unit": "row_middle",
    "apartment": "apartment",
    "apartment row": "apartment",
    "mobile home": "mobile",
    "detached triplex": "triplex",
    "attached triplex": "triplex",
    "triplex (non-murb)": "triplex",
}
STOREYS_MAP = {
    "one storey": "1",
    "one and a half": "1.5",
    "two storeys": "2",
    "two and a half": "2.5",
    "three storeys": "3",
    "split level": "split",
    "split entry / raised basement": "split_entry",
    "split entry/raised base.": "split_entry",
}


def load_json(name):
    return json.loads((DATA / name).read_text(encoding="utf-8"))


def fold_lookup(series, mapping, label):
    low = series.str.strip().str.lower()
    mapped = low.map(mapping)
    unmapped = series[mapped.isna()].unique()
    if len(unmapped):
        print(f"  [unmapped {label}] {list(unmapped)[:10]}")
    return mapped.fillna("other")


def process_city(city, ers_cache):
    prov = CITY_PROV[city]
    fsa_list = load_json("city_fsa_list.json")["cities"][city]
    fsas = {r["fsa"] for r in fsa_list}

    design_temps = load_json("city_design_temps.json")["cities"]
    designtemp_key = CITY_TO_DESIGNTEMP_KEY.get(city, city)
    t_design = design_temps[designtemp_key]["design_temp_C"]

    tmy_all = load_json("tmy_temps.json")
    tmy = np.array(tmy_all[city], dtype=float)

    print(f"\n=== {city} ({prov}) === {len(fsas)} FSAs, design temp {t_design:.1f}C")

    if prov not in ers_cache:
        cols = ["HOUSEID", "FSA", "YearBuilt", "FloorArea", "BldgType", "Storeys",
                "Pre_HeatLoss", "Pre_HeatEnergy", "Pre_HeatSeasonalCOP"]
        ers_cache[prov] = pd.read_parquet(ERS_WEB_DIR / f"ers_web_{prov}.parquet", columns=cols)
    df = ers_cache[prov]
    sub = df[df["FSA"].isin(fsas)].copy()
    n_city = len(sub)
    print(f"{n_city:,} ERS homes in {city}'s FSAs")

    sub["Pre_HeatLoss"] = pd.to_numeric(sub["Pre_HeatLoss"], errors="coerce")
    sub["Pre_HeatEnergy"] = pd.to_numeric(sub["Pre_HeatEnergy"], errors="coerce")
    sub["Pre_HeatSeasonalCOP"] = pd.to_numeric(sub["Pre_HeatSeasonalCOP"], errors="coerce")
    sub["FloorArea"] = pd.to_numeric(sub["FloorArea"], errors="coerce")

    # Pre_HeatEnergy (EGHFURNACEAEC) is fuel/electricity CONSUMED by the primary
    # heating system, not heat delivered -- for a home whose pre-retrofit system
    # is itself a heat pump (Pre_HeatSeasonalCOP well above 100), treating
    # consumed kWh as delivered kWh understates its true thermal load and can
    # make an ordinary envelope look like the most efficient home in the city
    # (confirmed 2026-08-11 on an Ottawa GSHP home, Pre_HPCOP 3.0: consumed
    # 10,587 kWh read as "best in the city" by peak+energy, when the model-
    # implied delivered figure is closer to 3x that). Same conversion already
    # validated in build_archetypes.py: delivered = consumed x (seasonal
    # efficiency / 100). Screened to the same plausible range (30-400) that
    # script uses -- below is missing/junk, above is a mis-scaled record.
    n_before_cop_screen = len(sub)
    sub = sub[sub["Pre_HeatSeasonalCOP"].between(30, 400)]
    n_dropped_bad_cop = n_before_cop_screen - len(sub)
    sub["Pre_HeatDelivered"] = sub["Pre_HeatEnergy"] * (sub["Pre_HeatSeasonalCOP"] / 100.0)

    valid = sub[(sub["Pre_HeatLoss"] > 0) & (sub["Pre_HeatDelivered"] > 0) & (sub["FloorArea"] > 0)].copy()
    n_dropped_invalid = n_city - n_dropped_bad_cop - len(valid)
    print(f"dropped (no plausible seasonal efficiency, 30-400%): {n_dropped_bad_cop:,}")

    grid = np.arange(t_design + 0.02, T0_MAX, 0.02)
    ddh = np.clip(grid[:, None] - tmy[None, :], 0, None).sum(axis=1)
    h_grid = ddh / (grid - t_design)

    dip_idx = int(np.argmin(h_grid))
    mono_grid = grid[dip_idx:]
    mono_h = h_grid[dip_idx:]
    assert np.all(np.diff(mono_h) >= -1e-6), f"{city}: h(T0) not monotonic past the dip"
    h_min, h_max = mono_h[0], mono_h[-1]

    target = valid["Pre_HeatDelivered"].values / valid["Pre_HeatLoss"].values
    too_low = target < h_min
    too_high = target > h_max
    solvable = ~too_low & ~too_high

    t0 = np.full(len(valid), np.nan)
    t0[solvable] = np.interp(target[solvable], mono_h, mono_grid)
    valid["T0"] = t0

    n_too_low = int(too_low.sum())
    n_too_high = int(too_high.sum())
    ok = valid[solvable].copy()

    print(f"dropped (missing/nonpositive fields): {n_dropped_invalid:,}")
    print(f"energy too low for the model (target < {h_min:.1f}): {n_too_low:,}")
    print(f"energy too high for the model (target > {h_max:.1f}): {n_too_high:,}")
    print(f"solved: {len(ok):,} ({100*len(ok)/n_city:.1f}% of {city}'s ERS homes)")

    ok["bldg_code"] = fold_lookup(ok["BldgType"], BLDGTYPE_MAP, "BldgType")
    ok["storeys_code"] = fold_lookup(ok["Storeys"], STOREYS_MAP, "Storeys")
    ok["decade"] = pd.to_numeric(ok["YearBuilt"], errors="coerce").apply(
        lambda y: "pre1946" if pd.notna(y) and y < 1946 else (int(y // 10 * 10) if pd.notna(y) else None)
    )

    BLDG_CODES = sorted(ok["bldg_code"].unique())
    STOREYS_CODES = sorted(ok["storeys_code"].unique())
    bldg_idx = {c: i for i, c in enumerate(BLDG_CODES)}
    storeys_idx = {c: i for i, c in enumerate(STOREYS_CODES)}

    rows = [
        [
            int(float(r.HOUSEID)),
            bldg_idx[r.bldg_code],
            storeys_idx[r.storeys_code],
            r.decade if r.decade is not None else None,
            round(float(r.FloorArea), 1),
            round(float(r.Pre_HeatLoss), 2),
            round(float(r.Pre_HeatDelivered), 0),
            round(float(r.T0), 2),
        ]
        for r in ok.itertuples(index=False)
    ]

    payload = {
        "meta": {
            "city": city, "province": prov, "design_temp_C": t_design,
            "n_homes": len(rows),
            "columns": ["houseid", "bldg_code", "storeys_code", "decade_built",
                        "floor_area_m2", "design_heat_loss_kW", "annual_heat_delivered_kWh",
                        "balance_point_T0_C"],
            "bldg_codes": BLDG_CODES,
            "storeys_codes": STOREYS_CODES,
            "method": "no-gains linear load model anchored on Pre_HeatLoss "
                      "(EGHDESHTLOSS, design/peak) and Pre_HeatDelivered "
                      "(EGHFURNACEAEC consumed x EGHFURSEASEFF/100 seasonal "
                      "efficiency, converting consumed to delivered heat) "
                      "-- see check_balance_point_k1s.py and this script's docstring",
            "n_dropped_bad_efficiency": int(n_dropped_bad_cop),
            "n_dropped_missing_fields": int(n_dropped_invalid),
            "n_dropped_too_low": n_too_low,
            "n_dropped_too_high": n_too_high,
        },
        "rows": rows,
    }

    slug = city.lower().replace(" ", "_")
    out_path = OUT_DIR / f"house_profiles_{slug}.json"
    text = json.dumps(payload, separators=(",", ":"))
    out_path.write_text(text, encoding="utf-8")
    raw_bytes = len(text.encode("utf-8"))
    gz_bytes = len(gzip.compress(text.encode("utf-8"), compresslevel=9))
    print(f"[out] {out_path.name}: {raw_bytes/1e6:.2f} MB raw, {gz_bytes/1e6:.2f} MB gzip")
    return raw_bytes, gz_bytes, len(rows)


def main():
    t_start = time.time()
    ers_cache = {}
    total_raw = total_gz = total_rows = 0
    for city in CITY_PROV:
        raw, gz, n = process_city(city, ers_cache)
        total_raw += raw
        total_gz += gz
        total_rows += n

    print(f"\n=== TOTAL: {total_rows:,} homes across 14 cities ===")
    print(f"combined raw: {total_raw/1e6:.2f} MB   combined gzip: {total_gz/1e6:.2f} MB")
    print(f"elapsed: {time.time()-t_start:.1f}s")


if __name__ == "__main__":
    main()
