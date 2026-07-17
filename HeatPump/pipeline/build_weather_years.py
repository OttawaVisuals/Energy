# build_weather_years.py
# Weather-lens data (ROADMAP item 9 workstream C): a multi-decade per-city
# hourly-temperature record, tagged by heating-degree-days into
# typical/coldest/mildest years, for heatpump.html's "weather year" selector,
# weather-file plot, and the headline min-max band across years.
#
# SOURCES (both already fetched):
#   - CWEEDS 2020 (Canadian Weather Energy and Engineering Data Sets), the
#     multi-decade hourly record per station, 1998-2017 (some stations start
#     2000/2003). Same CMC tree as the CWEC TMY. Downloaded per-province zip
#     under data/raw/eccc/cweeds/. Dry-bulb temperature is column index 30
#     ("Dry bulb temperature / 0.1 C") in the data rows; datetime is field 2
#     (YYYYMMDDHH). Station files match the CWEC climate IDs exactly.
#   - MSC Datamart hourly (data/interim/weather_hourly.csv, fetch_weather.py),
#     for recent complete years (2019-present). 2018 falls between the two
#     sources and is left as a gap (flagged in meta.years_missing).
#
# OUTPUT: data/processed/weather_<slug>.json per city, e.g.
#   { meta: { city, station_id, sources, years:[...], years_missing:[...],
#             tmy_hdd18, design_temp_computed_2p5, nbc_2020, tags:{...} },
#     years: { "2001": { hdd18, min_C, mean_C, n_hours, temps_tenthsC:[...] }, ... } }
# temps are quantized to integer tenths of a degree C (e.g. -229 = -22.9 C),
# JSON emitted with no whitespace, to keep each file about 1 MB (lazy-loaded).
#
# pip install pandas

import os
import io
import re
import sys
import json
import zipfile

import numpy as np
import pandas as pd

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

HERE = os.path.dirname(os.path.abspath(__file__))
CWEEDS_DIR = os.path.join(HERE, "..", "data", "raw", "eccc", "cweeds")
WEATHER_CSV = os.path.join(HERE, "..", "data", "interim", "weather_hourly.csv")
TMY_TEMPS = os.path.join(HERE, "..", "data", "processed", "tmy_temps.json")
OUT_DIR = os.path.join(HERE, "..", "data", "processed")

MIN_HOURS = 8000          # a "complete" year
MAX_YEARS = 24            # cap kept years (newest-first) to keep files ~1 MB
CWEEDS_TEMP_COL = 30      # "Dry bulb temperature / 0.1 C"

# city -> (province, climate ID). Matches the CWEC TMY / CWEEDS station IDs
# (Windsor's CWEEDS/CWEC station is 6139527, older than its live Datamart 6139530).
CITY_STATION = {
    "Ottawa":      ("ON", "6106001"),
    "Toronto":     ("ON", "6158731"),
    "Montreal":    ("QC", "7025251"),
    "Calgary":     ("AB", "3031092"),
    "Edmonton":    ("AB", "3012216"),
    "Vancouver":   ("BC", "1108395"),
    "Winnipeg":    ("MB", "5023227"),
    "Quebec City": ("QC", "7016293"),
    "Halifax":     ("NS", "8202251"),
    "Saskatoon":   ("SK", "4057152"),
    "Regina":      ("SK", "4016566"),
    "Hamilton":    ("ON", "6153193"),
    "London":      ("ON", "6144473"),
    "Windsor":     ("ON", "6139527"),
}

# NBC 2020 Division B Appendix C, Table C-2, January design temperatures
# (deg C, 2.5% / 1% dry-bulb heating). Commonly-published Table C-2 values for
# the primary station of each city; shown in the UI alongside the tool's own
# multi-decade computed 2.5%-ile. Where NBC lists several stations per city the
# principal airport is used. Cite: NBC 2020, Appendix C, Table C-2.
NBC_2020 = {
    "Ottawa":      {"jan_2p5": -24, "jan_1p": -25},
    "Toronto":     {"jan_2p5": -18, "jan_1p": -20},
    "Montreal":    {"jan_2p5": -23, "jan_1p": -24},
    "Calgary":     {"jan_2p5": -30, "jan_1p": -31},
    "Edmonton":    {"jan_2p5": -30, "jan_1p": -32},
    "Vancouver":   {"jan_2p5": -7,  "jan_1p": -9},
    "Winnipeg":    {"jan_2p5": -31, "jan_1p": -33},
    "Quebec City": {"jan_2p5": -25, "jan_1p": -27},
    "Halifax":     {"jan_2p5": -16, "jan_1p": -18},
    "Saskatoon":   {"jan_2p5": -31, "jan_1p": -33},
    "Regina":      {"jan_2p5": -31, "jan_1p": -34},
    "Hamilton":    {"jan_2p5": -17, "jan_1p": -19},
    "London":      {"jan_2p5": -16, "jan_1p": -18},
    "Windsor":     {"jan_2p5": -16, "jan_1p": -18},
}


def slug(city):
    return re.sub(r"[^a-z]", "", city.lower())


def cweeds_station_years(prov, climate_id):
    """Return {year: np.array(hourly temps C)} from the CWEEDS station file,
    plus {year: month_array} so we can compute a January design temp. Missing
    values (9999 / blank) become NaN."""
    zpath = os.path.join(CWEEDS_DIR, f"CWEEDS_2020_{prov}.zip")
    if not os.path.exists(zpath):
        print(f"   [warn] no CWEEDS zip for {prov}")
        return {}, {}
    with zipfile.ZipFile(zpath) as z:
        name = next((n for n in z.namelist()
                     if n.lower().endswith(".csv") and climate_id in n), None)
        if name is None:
            print(f"   [warn] station {climate_id} not in CWEEDS_{prov}")
            return {}, {}
        raw = z.read(name).decode("latin-1", errors="replace").splitlines()

    years, months = {}, {}
    for line in raw[3:]:                 # skip 2 meta rows + 1 header row
        f = line.split(",")
        if len(f) <= CWEEDS_TEMP_COL:
            continue
        ymdh = f[2]
        if len(ymdh) != 10 or not ymdh.isdigit():
            continue
        yr = int(ymdh[:4]); mo = int(ymdh[4:6])
        raw_t = f[CWEEDS_TEMP_COL].strip()
        t = np.nan if raw_t in ("", "9999", "-9999") else int(raw_t) / 10.0
        if t is not np.nan and (t < -60 or t > 55):
            t = np.nan
        years.setdefault(yr, []).append(t)
        months.setdefault(yr, []).append(mo)
    return ({y: np.array(v, dtype=float) for y, v in years.items()},
            {y: np.array(v, dtype=int) for y, v in months.items()})


def datamart_years(city):
    """Return {year: np.array(temps)} and {year: month_array} for a city from
    the MSC Datamart interim CSV (2019+)."""
    df = pd.read_csv(WEATHER_CSV, parse_dates=["Date"])
    df = df[df["City"] == city].sort_values(["Date", "Hour"])
    if df.empty:
        return {}, {}
    df["Year"] = df["Date"].dt.year
    df["Month"] = df["Date"].dt.month
    years, months = {}, {}
    for yr, sub in df.groupby("Year"):
        years[int(yr)] = sub["Temperature_C"].to_numpy(dtype=float)
        months[int(yr)] = sub["Month"].to_numpy(dtype=int)
    return years, months


def hdd18(temps):
    t = temps[~np.isnan(temps)]
    return float(np.clip(18.0 - t, 0, None).sum() / 24.0)


def build_city(city, tmy_series):
    prov, cid = CITY_STATION[city]
    cw_t, cw_m = cweeds_station_years(prov, cid)
    dm_t, dm_m = datamart_years(city)

    # datamart wins where both exist (won't overlap: CWEEDS<=2017, datamart>=2019)
    temps = dict(cw_t); months = dict(cw_m)
    temps.update(dm_t); months.update(dm_m)

    complete = {y: v for y, v in temps.items()
                if np.count_nonzero(~np.isnan(v)) >= MIN_HOURS}
    all_years = sorted(complete)
    if not all_years:
        print(f"   [warn] {city}: no complete years")
        return None

    # keep the newest MAX_YEARS to bound file size
    kept = sorted(all_years)[-MAX_YEARS:]
    span = range(kept[0], kept[-1] + 1)
    missing = [y for y in span if y not in complete]

    # January design temp (2.5%-ile) from the full multi-decade record
    jan_vals = []
    for y in complete:
        m = months[y]; t = temps[y]
        jan = t[(m == 1) & ~np.isnan(t)]
        jan_vals.append(jan)
    jan_all = np.concatenate(jan_vals) if jan_vals else np.array([])
    design_2p5 = float(np.percentile(jan_all, 2.5)) if jan_all.size else None

    tmy_h = hdd18(np.array(tmy_series, dtype=float))

    years_out = {}
    hdds = {}
    for y in kept:
        t = temps[y]
        # forward/back fill isolated NaNs so the array is plottable & simulable
        s = pd.Series(t).interpolate(limit_direction="both")
        arr = np.rint(s.to_numpy() * 10).astype(int)   # tenths of a degree
        years_out[str(y)] = {
            "hdd18": round(hdd18(t), 0),
            "min_C": round(float(np.nanmin(t)), 1),
            "mean_C": round(float(np.nanmean(t)), 1),
            "n_hours": int(len(t)),
            "temps_tenthsC": arr.tolist(),
        }
        hdds[y] = hdd18(t)

    representative = min(hdds, key=lambda y: abs(hdds[y] - tmy_h))
    coldest = max(hdds, key=lambda y: hdds[y])
    mildest = min(hdds, key=lambda y: hdds[y])

    meta = {
        "city": city,
        "station_id": cid,
        "sources": "CWEEDS 2020 (1998-2017) + MSC Datamart (2019+)",
        "years": kept,
        "years_missing": missing,
        "tmy_hdd18": round(tmy_h, 0),
        "design_temp_computed_2p5_C": round(design_2p5, 1) if design_2p5 is not None else None,
        "design_temp_note": ("2.5%-ile January temperature over the full "
                             "multi-decade record above; NBC values are the "
                             "commonly-published NBC 2020 Table C-2 figures."),
        "nbc_2020_table_c2": NBC_2020.get(city),
        "tags": {"representative": representative, "coldest": coldest, "mildest": mildest},
    }
    return {"meta": meta, "years": years_out}


def main():
    with open(TMY_TEMPS, encoding="utf-8") as fh:
        tmy = json.load(fh)

    os.makedirs(OUT_DIR, exist_ok=True)
    print("=== Weather-lens: multi-decade per-city temperature record ===\n")
    summary = []
    for city in CITY_STATION:
        if city not in tmy:
            print(f"[skip] {city}: not in tmy_temps.json"); continue
        out = build_city(city, tmy[city])
        if out is None:
            continue
        path = os.path.join(OUT_DIR, f"weather_{slug(city)}.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(out, fh, separators=(",", ":"))
        kb = os.path.getsize(path) / 1024
        m = out["meta"]
        print(f"[ok] {city:12s} {len(m['years'])} yrs {m['years'][0]}-{m['years'][-1]} "
              f"design2.5%={m['design_temp_computed_2p5_C']}C (NBC {m['nbc_2020_table_c2']['jan_2p5']}) "
              f"tags rep={m['tags']['representative']} cold={m['tags']['coldest']} "
              f"mild={m['tags']['mildest']}  {kb:.0f} KB")
        summary.append((city, kb))

    big = [c for c, kb in summary if kb > 1100]
    if big:
        print(f"\n[warn] files over ~1.1 MB: {big} — consider lowering MAX_YEARS")
    print(f"\n[ok] wrote {len(summary)} weather_<city>.json files to {OUT_DIR}")


if __name__ == "__main__":
    main()
