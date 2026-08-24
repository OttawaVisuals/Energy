"""
build_ef_surface.py -- Phase 2 of the Heat Pump tool.

Builds the temperature x hour-of-day x season grid-emissions-factor (EF)
lookup surface that PLAN.md methodology decision #2 called for, and that
was deferred out of Phase 1 until hourly weather existed. Weather now
exists (data/interim/weather_hourly.csv), so this unblocks the join.

Why a surface, not "bin EF by temperature alone" (PLAN.md #2)
------------------------------------------------------------
Grid intensity is not a function of temperature alone -- hour-of-day
(morning/evening gas peaks), season (hydro conditions, AC vs heating load)
and outages all move it. Binning EF purely by temperature and applying a
TMY temperature series would smear morning-peak gas hours into mild
afternoons. So we bin the historical hourly EF by
**temperature (2 C bins) x hour-of-day (1-24) x season (DJF/MAM/JJA/SON)**
over the full overlapping history. The browser engine then looks up a cell
by (T, hour, season) from a city's TMY/historical temperature series.

Shape x level decomposition (the key modelling choice)
------------------------------------------------------
The provincial grids are *not stationary* over the available history: the
Ontario average EF roughly tripled 2020->2025 (~32 -> ~97 g/kWh) as gas
generation grew, and Alberta's fell by a third (~650 -> ~414 g/kWh) as coal
retired. That year-to-year drift is driven by fleet/policy change, NOT by
weather, so a single pooled temperature x hour x season climatology of
*absolute* EF reconstructs the multi-year *mean* well but cannot reproduce
any individual year's level (pooling smears a rising series to its midpoint).

So we decompose each hourly EF into

    EF(hour) = annual_level(year) * shape(temp, hour, season)

where `annual_level(year)` is that calendar year's mean EF and `shape` is
the multiplicative climatology (mean of EF/annual_level per bin, ~1 on
average). The physical driver -- gas (and, in AB, coal) fraction -- scales
the whole level, so a cold winter-evening hour carries roughly the same
*ratio* to the annual mean whether the year's grid is clean or dirty; the
ratio is the stationary part, the level is the trending part. We store the
shape cells plus the per-year levels and a `reference_level` (the most
recent complete calendar year = the current grid). The engine multiplies
shape x reference_level to get a typical-year EF for today's grid, and can
swap in any stored year's level to reproduce the historical band (PLAN.md
#2's second sub-point). Provinces whose EF is essentially zero (QC,
~0.02 g/kWh) skip the ratio (unstable near zero) and carry a neutral
shape == 1 -- their level is negligible either way.

Province vs. city temperature
------------------------------
The grid EF is province-wide, so the surface is per province, keyed on the
temperature of a single proxy city's weather record. IESO's generation-by-
fuel report has no regional breakdown -- Ontario's grid is one integrated
pool, so every location sees the identical province-wide EF for a given
hour. The proxy city choice therefore doesn't select a different fuel mix,
only whose temperature gets used to time-align the bins against province-
wide demand:

    ON -> London    (see below)
    QC -> Montreal
    AB -> Calgary

ON was originally keyed on Toronto (GTA dominates Ontario demand), but
Toronto's 2020-2026 record only reaches -22.6 C (n=5 hours colder than
-22 C), so the surface's coldest bins were thin/absent and design-load-cold
temperatures fell straight through every fallback to the flat global mean
(shape ratio 1.0). Checked against IESO's hourly generation data, London
tracks province-wide gas output just as tightly as Toronto does (winter
corr(temp, gas MW) = -0.420 vs Toronto's -0.419; at the actual top-30
gas-output hours 2020-2026, London/Toronto/Hamilton track within 1-3 C of
each other) while reaching -24.8 C with 44 hours below -22 C -- real
cold-tail coverage instead of a flatline. Ottawa is colder still but is a
worse demand proxy: at those same peak-demand hours it runs 5-10 C colder
than Toronto/London, which would overstate how cold Ontario needs to get
before the grid gets dirty.

The engine applies the resulting provincial surface to each launch city's
own temperature series (e.g. Ottawa temps against the ON surface); for a
screening tool the small inter-city temperature offset within a province is
acceptable and is documented in METHODOLOGY.md. Below the coldest (or
above the warmest) bin the surface actually has data for, the browser
engine fits a least-squares line through the tail's 6 most extreme
sufficiently-sampled coarse_t bins and extends it, rather than falling back
to the flat global mean at the first missing bin -- a 2-point edge slope
was tried first and rejected as too noisy (the outermost bin has the fewest
hours of any bin clearing the thin-bin threshold). See the
`extrapolateShape` cold/warm-tail extrapolation in heatpump.html.

Thin-bin fallback
-----------------
A 2 C x 24 h x 4-season grid has ~3000+ cells; the tails (very cold / very
warm hours at odd times of day) are thin. Rather than trust a mean built
from a handful of hours, we store, alongside the fine cells, three
progressively coarser aggregates so the engine (and the validation below)
can fall back when a fine cell has < 20 samples:

    fine     : temperature x hour x season           (preferred)
    coarse_ts: temperature x season   (all hours)     (fallback 1)
    coarse_t : temperature            (all hours/seasons) (fallback 2)
    global   : overall mean                            (fallback 3)

Every cell carries its sample count so the fallback is explicit.

Output
------
One compact JSON per province into data/processed/:
    ef_surface_on.json, ef_surface_ab.json, ef_surface_qc.json
Each holds the mean average-EF and marginal-EF *shape ratio* per bin plus
counts, the per-year annual levels, and the reference (latest complete
year) level. Target < 100 KB each (only populated cells stored; rounded).

Validation
----------
Reconstruct each year's annual average intensity by applying the surface
(shape x that year's stored level, with the thin-bin fallback) to the
historical temperature series it was built from, and compare to the annual
figure computed directly from the Phase-1 hourly series. Must land within
+/-10%. Printed per year and overall.

Run:
    python HeatPump/pipeline/build_ef_surface.py
"""

from __future__ import annotations

import json
import os
from collections import defaultdict

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PROCESSED = os.path.join(ROOT, "data", "processed")
INTERIM = os.path.join(ROOT, "data", "interim")

WEATHER_CSV = os.path.join(INTERIM, "weather_hourly.csv")

TEMP_BIN_WIDTH = 2.0        # deg C
THIN_BIN_MIN = 20           # < this many hours in a cell -> fall back coarser
ZERO_LEVEL_EPS = 1.0        # provinces with mean EF below this (g/kWh) skip the
                            # ratio decomposition (unstable near zero) -> shape==1
FULL_YEAR_HOURS = 8000      # a calendar year with >= this many joined hours is
                            # "complete" and eligible to be the reference level

# province -> (grid EF json, temperature-proxy weather city)
# ON: London, not Toronto -- see "Province vs. city temperature" above for
# the correlation check and cold-tail rationale.
PROVINCES = {
    "ON": ("grid_ef_on.json", "London"),
    "AB": ("grid_ef_ab.json", "Calgary"),
    "QC": ("grid_ef_qc.json", "Montreal"),
}

SEASON_BY_MONTH = {
    12: "winter", 1: "winter", 2: "winter",
    3: "spring", 4: "spring", 5: "spring",
    6: "summer", 7: "summer", 8: "summer",
    9: "fall", 10: "fall", 11: "fall",
}


def temp_bin_left(temp_c: float) -> int:
    """Left edge (inclusive) of the 2 C bin containing temp_c, as an int."""
    return int(np.floor(temp_c / TEMP_BIN_WIDTH) * TEMP_BIN_WIDTH)


def load_grid_ef(fname: str) -> pd.DataFrame:
    with open(os.path.join(PROCESSED, fname), "r", encoding="utf-8") as fh:
        blob = json.load(fh)
    df = pd.DataFrame(blob["hourly"])
    return df[["Date", "Hour", "AvgEF_g_per_kWh", "MarginalEF_g_per_kWh"]].copy()


def load_weather(city: str) -> pd.DataFrame:
    df = pd.read_csv(WEATHER_CSV, usecols=["City", "Date", "Hour", "Temperature_C"])
    df = df[df["City"] == city].drop(columns="City")
    return df


def build_surface(prov: str, ef_fname: str, city: str):
    """Join EF with the load-centre weather, bin, and return (surface, joined)."""
    ef = load_grid_ef(ef_fname)
    wx = load_weather(city)

    # Inner join on the shared hourly key (both use Date=YYYY-MM-DD, Hour=1..24).
    j = ef.merge(wx, on=["Date", "Hour"], how="inner")
    j = j.dropna(subset=["Temperature_C", "AvgEF_g_per_kWh", "MarginalEF_g_per_kWh"])

    dt = pd.to_datetime(j["Date"])
    j["Year"] = dt.dt.year
    j["Season"] = dt.dt.month.map(SEASON_BY_MONTH)
    j["TBin"] = j["Temperature_C"].map(temp_bin_left)

    # ---- per-year annual levels (the trending part) ----
    year_stats = j.groupby("Year").agg(
        avg=("AvgEF_g_per_kWh", "mean"),
        marg=("MarginalEF_g_per_kWh", "mean"),
        n=("AvgEF_g_per_kWh", "size"),
    )
    avg_level = year_stats["avg"].to_dict()
    marg_level = year_stats["marg"].to_dict()

    grid_is_zero = year_stats["avg"].mean() < ZERO_LEVEL_EPS

    # ---- hourly shape ratios EF/annual_level (the stationary part) ----
    # For a ~zero grid the ratio is unstable, so carry a neutral shape == 1
    # and let the (negligible) level do the work.
    if grid_is_zero:
        j["RAvg"] = 1.0
        j["RMarg"] = 1.0
    else:
        j["RAvg"] = j["AvgEF_g_per_kWh"] / j["Year"].map(avg_level)
        # MarginalEF can be 0 in a year whose marginal level is ~0; guard it.
        marg_denom = j["Year"].map(marg_level).replace(0.0, np.nan)
        j["RMarg"] = (j["MarginalEF_g_per_kWh"] / marg_denom).fillna(1.0)

    def agg(group_cols):
        g = j.groupby(group_cols)
        m = g[["RAvg", "RMarg"]].mean()
        c = g.size().rename("n")
        return m.join(c)

    fine = agg(["Season", "Hour", "TBin"])
    coarse_ts = agg(["Season", "TBin"])
    coarse_t = agg(["TBin"])
    global_shape = (round(float(j["RAvg"].mean()), 4),
                    round(float(j["RMarg"].mean()), 4), int(len(j)))

    # ---- compact nested dict, populated cells only, ratios rounded ----
    def cell(row):
        return [round(float(row["RAvg"]), 4),
                round(float(row["RMarg"]), 4),
                int(row["n"])]

    fine_d: dict = defaultdict(lambda: defaultdict(dict))
    for (season, hour, tbin), row in fine.iterrows():
        fine_d[season][str(int(hour))][str(int(tbin))] = cell(row)

    coarse_ts_d: dict = defaultdict(dict)
    for (season, tbin), row in coarse_ts.iterrows():
        coarse_ts_d[season][str(int(tbin))] = cell(row)

    coarse_t_d: dict = {}
    for tbin, row in coarse_t.iterrows():
        coarse_t_d[str(int(tbin))] = cell(row)

    # ---- reference level = most recent complete calendar year ----
    complete = year_stats[year_stats["n"] >= FULL_YEAR_HOURS]
    ref_year = int(complete.index.max()) if len(complete) else int(year_stats.index.max())

    levels = {str(int(y)): [round(avg_level[y], 3), round(marg_level[y], 3),
                            int(year_stats.loc[y, "n"])]
              for y in year_stats.index}

    surface = {
        "meta": {
            "province": prov,
            "temperature_proxy_city": city,
            "temp_bin_width_c": TEMP_BIN_WIDTH,
            "thin_bin_min_hours": THIN_BIN_MIN,
            "seasons": {"winter": "DJF", "spring": "MAM", "summer": "JJA", "fall": "SON"},
            "hour_convention": "1..24 (matches grid EF + weather CSV)",
            "model": "EF(hour) = level[year] * shape(temp,hour,season); "
                     "engine uses reference_level for a typical current-grid year",
            "cell_format": "[mean_AvgEF_ratio, mean_MarginalEF_ratio, n_hours]",
            "grid_is_zero": bool(grid_is_zero),
            "fallback_order": ["fine (season/hour/tbin)", "coarse_ts (season/tbin)",
                               "coarse_t (tbin)", "global"],
            "date_range": [j["Date"].min(), j["Date"].max()],
            "n_hours_joined": int(len(j)),
            "n_fine_cells": int(len(fine)),
            "reference_year": ref_year,
        },
        "levels_g_per_kWh": levels,          # per calendar year [avg, marg, n_hours]
        "reference_level_g_per_kWh": [levels[str(ref_year)][0], levels[str(ref_year)][1]],
        "fine": {s: dict(h) for s, h in fine_d.items()},
        "coarse_ts": {s: d for s, d in coarse_ts_d.items()},
        "coarse_t": coarse_t_d,
        "global": list(global_shape),
    }
    return surface, j


def lookup_shape(surface: dict, season: str, hour: int, tbin: int, field: int):
    """Thin-bin fallback -> shape ratio (field: 0=avg, 1=marg)."""
    thin = surface["meta"]["thin_bin_min_hours"]
    h = str(int(hour))
    tb = str(int(tbin))

    c = surface["fine"].get(season, {}).get(h, {}).get(tb)
    if c and c[2] >= thin:
        return c[field]
    c = surface["coarse_ts"].get(season, {}).get(tb)
    if c and c[2] >= thin:
        return c[field]
    c = surface["coarse_t"].get(tb)
    if c and c[2] >= thin:
        return c[field]
    return surface["global"][field]


def validate(prov: str, surface: dict, joined: pd.DataFrame):
    """Reconstruct annual avg intensity from the surface; compare to direct.

    Reconstruction = each year's stored level x the weather shape (with
    thin-bin fallback), applied hour-by-hour over that year's temperatures.
    """
    df = joined.copy()
    shape = np.array([
        lookup_shape(surface, s, hh, tb, 0)
        for s, hh, tb in zip(df["Season"], df["Hour"], df["TBin"])
    ])
    levels = surface["levels_g_per_kWh"]
    year_level = df["Year"].map(lambda y: levels[str(int(y))][0]).to_numpy()
    df["PredAvgEF"] = shape * year_level

    print(f"\n=== {prov}: surface reconstruction vs Phase-1 direct "
          f"(temperature proxy: {surface['meta']['temperature_proxy_city']}) ===")
    print(f"{'Year':>6} {'Direct':>10} {'Surface':>10} {'Diff %':>9} {'hours':>8}")
    rows = []
    worst = 0.0
    for year, g in df.groupby("Year"):
        direct = g["AvgEF_g_per_kWh"].mean()
        recon = g["PredAvgEF"].mean()
        diff = (recon - direct) / direct * 100 if direct else 0.0
        worst = max(worst, abs(diff))
        rows.append((year, direct, recon, diff, len(g)))
        print(f"{year:>6} {direct:>10.2f} {recon:>10.2f} {diff:>8.1f}% {len(g):>8}")

    direct_all = df["AvgEF_g_per_kWh"].mean()
    recon_all = df["PredAvgEF"].mean()
    diff_all = (recon_all - direct_all) / direct_all * 100 if direct_all else 0.0
    worst = max(worst, abs(diff_all))
    print(f"{'ALL':>6} {direct_all:>10.2f} {recon_all:>10.2f} {diff_all:>8.1f}% "
          f"{len(df):>8}")
    status = "PASS" if worst <= 10.0 else "FAIL"
    print(f"  -> worst |diff| = {worst:.1f}%  (tolerance +/-10%)  [{status}]")
    return worst <= 10.0


def main():
    all_pass = True
    for prov, (ef_fname, city) in PROVINCES.items():
        surface, joined = build_surface(prov, ef_fname, city)
        out_path = os.path.join(PROCESSED, f"ef_surface_{prov.lower()}.json")
        with open(out_path, "w", encoding="utf-8") as fh:
            json.dump(surface, fh, separators=(",", ":"))
        size_kb = os.path.getsize(out_path) / 1024
        flag = "OK" if size_kb < 100 else "OVER 100 KB"
        print(f"[{prov}] wrote {os.path.relpath(out_path, ROOT)}  "
              f"({size_kb:.1f} KB, {surface['meta']['n_fine_cells']} fine cells) [{flag}]")
        ok = validate(prov, surface, joined)
        all_pass = all_pass and ok

    print("\n" + ("ALL PROVINCES PASS (+/-10%)" if all_pass
                  else "!!! SOME PROVINCES FAILED VALIDATION"))


if __name__ == "__main__":
    main()
