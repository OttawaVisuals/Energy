"""
build_grid_seasonal.py

Compact seasonal typical-day emission-intensity profiles for grid.html's
Advanced "typical day, by season" panel (ROADMAP.md item 6).

WHY THIS EXISTS
    grid_json/{grid_on,grid_ab}.json (grid_etl.py) only carry a rolling
    14-day hourly window plus ~12 months of daily min/mean/max -- there is
    no way to reconstruct "what does a typical winter hour look like" from
    them; the underlying hourly history simply isn't kept there (by design,
    to keep those files small and fast-refreshing).
    That history DOES exist: HeatPump/data/processed/grid_ef_{on,ab}.json,
    the Heat Pump tool's own Phase-1 output (see HeatPump/METHODOLOGY.md),
    already carries every hour from 2020-01-01 (ON) / 2015-01-01 (AB)
    through the present. Reusing it (not re-fetching or reimplementing
    anything) rather than shipping those 6-9 MB files to a browser, this
    script pre-aggregates them into one ~10 KB file per province: mean
    AvgEF, MarginalEF and fossil-generation share per (season, hour-of-day).

    ON's file has no per-fuel breakdown beyond GasFrac (gas is ON's only
    direct-emission fuel in this model); AB's has CoalFrac + GasLikeFrac
    (its two direct-emission sources). Both are summed into one
    "fossil_share" field so the page can show one comparable curve per
    province without pretending AB's coal/gas split exists for ON.

    Meteorological seasons (not astronomical): Dec-Jan-Feb winter,
    Mar-Apr-May spring, Jun-Jul-Aug summer, Sep-Oct-Nov fall -- calendar
    months, so December groups with Jan/Feb, not the following year.

OUTPUT (grid_json/, repo root)
    typical_day_on.json, typical_day_ab.json --
      {province, date_range, n_hours: {season: N}, methodology,
       seasons: {winter|spring|summer|fall: [
         {hour, avg_ef_mean, marginal_ef_mean, fossil_share_mean}, ...24
       ]}}

USAGE
    python build_grid_seasonal.py
"""

import json
from pathlib import Path
from collections import defaultdict

REPO_ROOT = Path(__file__).resolve().parent.parent
HP_PROC = REPO_ROOT / "HeatPump" / "data" / "processed"
OUT_DIR = REPO_ROOT / "grid_json"

SEASON_BY_MONTH = {
    12: "winter", 1: "winter", 2: "winter",
    3: "spring", 4: "spring", 5: "spring",
    6: "summer", 7: "summer", 8: "summer",
    9: "fall", 10: "fall", 11: "fall",
}
SEASONS = ["winter", "spring", "summer", "fall"]


def build(province, src_name, fossil_fn, methodology_extra):
    src = HP_PROC / src_name
    with open(src, "r", encoding="utf-8") as f:
        data = json.load(f)
    rows = data["hourly"]
    date_range = data["meta"]["date_range"]

    # bucket[(season, hour)] -> running sums
    buckets = defaultdict(lambda: {"n": 0, "avg_ef": 0.0, "marg_ef": 0.0, "fossil": 0.0})
    for r in rows:
        month = int(r["Date"][5:7])
        season = SEASON_BY_MONTH[month]
        hour = r["Hour"]
        b = buckets[(season, hour)]
        b["n"] += 1
        b["avg_ef"] += r["AvgEF_g_per_kWh"]
        b["marg_ef"] += r["MarginalEF_g_per_kWh"]
        b["fossil"] += fossil_fn(r)

    n_hours = {s: 0 for s in SEASONS}
    seasons_out = {s: [] for s in SEASONS}
    for season in SEASONS:
        for hour in range(1, 25):
            b = buckets.get((season, hour))
            if not b or b["n"] == 0:
                continue
            n_hours[season] += b["n"]
            seasons_out[season].append({
                "hour": hour,
                "avg_ef_mean": round(b["avg_ef"] / b["n"], 1),
                "marginal_ef_mean": round(b["marg_ef"] / b["n"], 1),
                "fossil_share_mean": round(b["fossil"] / b["n"], 4),
            })
        seasons_out[season].sort(key=lambda r: r["hour"])

    out = {
        "province": province,
        "date_range": date_range,
        "n_hours": n_hours,
        "methodology": (
            "Mean AvgEF/MarginalEF/fossil-generation-share per (meteorological "
            "season, hour-of-day), averaged over every hour in date_range -- "
            "not a single representative day, a multi-year hourly average. "
            "Source: HeatPump/data/processed/" + src_name + " (Heat Pump tool "
            "Phase-1 output, direct-combustion-only EF model, already "
            "calibrated -- see HeatPump/METHODOLOGY.md). " + methodology_extra
        ),
        "seasons": seasons_out,
    }

    out_path = OUT_DIR / f"typical_day_{province.lower()}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, separators=(",", ":"))
    size_kb = out_path.stat().st_size / 1024
    print(f"{out_path.name}: {sum(n_hours.values())} hours -> "
          f"{sum(len(v) for v in seasons_out.values())} (season,hour) buckets, "
          f"{size_kb:.1f} KB")
    for season in SEASONS:
        rows_s = seasons_out[season]
        if not rows_s:
            print(f"  WARNING: {season} has no data")
            continue
        peak = max(rows_s, key=lambda r: r["avg_ef_mean"])
        trough = min(rows_s, key=lambda r: r["avg_ef_mean"])
        print(f"  {season:6s} n={n_hours[season]:6d}  AvgEF hour{trough['hour']:2d}="
              f"{trough['avg_ef_mean']:6.1f} .. hour{peak['hour']:2d}={peak['avg_ef_mean']:6.1f} g/kWh")


def main():
    build("ON", "grid_ef_on.json", lambda r: r["GasFrac"],
          "fossil_share = GasFrac (ON's only direct-emission source in this model).")
    build("AB", "grid_ef_ab.json", lambda r: r["CoalFrac"] + r["GasLikeFrac"],
          "fossil_share = CoalFrac + GasLikeFrac (AB's two direct-emission sources).")


if __name__ == "__main__":
    main()
