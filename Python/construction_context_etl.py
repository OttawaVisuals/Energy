"""
construction_context_etl.py

Phase-4a context ETL for the Construction Activity Dashboard (see
CONSTRUCTION_PLAN.md section 1.2). Produces construction_json/context.json —
the small shared file of driver/context series the dashboard overlays on the
core activity data. Reuses the fetch/extract machinery of construction_etl.py.

SOURCES (all verified live 2026-07-09)
    18-10-0205  New housing price index (monthly, total house+land)
                  Canada + the dashboard CMAs
    17-10-0009  Population estimates (quarterly), Canada + provinces
    14-10-0355  LFS employment, NAICS 6 = Construction, seasonally adjusted
                  estimate (monthly, thousands -> stored as persons), Canada
                  + provinces
    34-10-0145  CMHC 5-year conventional mortgage lending rate (monthly, %)
    18-10-0289  Building construction price indexes (quarterly): residential
                  and non-residential composites, 15-CMA composite + CMAs
                  (Ottawa = Ontario part; no Gatineau/combined member exists)
    BoC Valet   Overnight target rate V39079 (daily -> month-end value, %)

OUTPUT  construction_json/context.json
    {"retrieved": "...", "series": {key: {start, freq('m'|'q'), values[]}}}
    Keys:
      nhpi.<geo>               monthly index, geo = ca | CMA codes
      pop.<geo>                quarterly persons (int), geo = ca | province
      emp_construction.<geo>   monthly persons (int), geo = ca | province
      rate.mortgage5y          monthly %, 2 decimals
      rate.overnight           monthly % (month-end), 2 decimals
      bcpi.<geo>.res|nonres    quarterly index, geo = composite | CMA codes
    Index and rate values keep StatCan/BoC precision (<= 2 decimals); person
    counts are ints. Same start/values/null-gap contract as the core files.

USAGE
    python construction_context_etl.py [--refresh]
Exits non-zero on any fetch failure (safe for the scheduled refresh).
"""

import sys
import json
import argparse
from datetime import datetime

import requests

from construction_etl import (
    OUTPUT_DIR, FLOOR_MONTH, download_full_zip, extract_table, month_range,
    verify_layout, EXPECTED_DIMS, get_cube_metadata,
)

# extend the layout sanity-check map for the context cubes
EXPECTED_DIMS.update({
    18100205: 2,   # geo, index type
    17100009: 1,   # geo
    14100355: 4,   # geo, NAICS, statistics, data type
    34100145: 1,   # geo
    18100289: 3,   # geo, building type, division
})

# --- geography member ids (verified via getCubeMetadata 2026-07-09) ----------
PROVS = ["ca", "nl", "pe", "ns", "nb", "qc", "on", "mb", "sk", "ab", "bc"]
GEO_PROV_1TO11 = dict(zip(PROVS, range(1, 12)))   # 17-10-0009 and 14-10-0355

GEO_205 = {"ca": 1, "halifax": 8, "montreal": 15, "ottawa_qc": 16,
           "ottawa_on": 18, "toronto": 20, "winnipeg": 30, "calgary": 35,
           "edmonton": 36, "vancouver": 39}

GEO_289 = {"composite": 1, "halifax": 5, "montreal": 10, "ottawa_on": 12,
           "toronto": 13, "winnipeg": 16, "calgary": 21, "edmonton": 22,
           "vancouver": 24}

BOC_URL = ("https://www.bankofcanada.ca/valet/observations/V39079/json"
           "?start_date=1990-01-01")


def fetch_boc_overnight():
    """BoC Valet daily overnight target rate -> {YYYY-MM: month-end value}."""
    r = requests.get(BOC_URL, timeout=120)
    r.raise_for_status()
    obs = r.json()["observations"]
    monthly = {}
    for o in obs:                       # observations are date-ascending
        v = o.get("V39079", {}).get("v")
        if v in (None, ""):
            continue
        monthly[o["d"][:7]] = float(v)  # last write per month wins = month-end
    return monthly


def series_from_months(months, freq):
    """{YYYY-MM: value} -> {start, freq, values[]} with null gaps. Monthly
    steps by 1 month; quarterly steps by 3 (StatCan quarterly REF_DATEs are
    the first month of each quarter)."""
    if not months:
        return None
    start, last = min(months), max(months)
    idx = month_range(start, last)
    step = 3 if freq == "q" else 1
    idx = idx[::step]
    return {"start": start, "freq": freq,
            "values": [months.get(m) for m in idx]}


def rnd(months, nd=2, as_int=False, mult=1):
    return {m: (int(round(v * mult)) if as_int else round(v * mult, nd))
            for m, v in months.items()}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--refresh", action="store_true")
    args = parser.parse_args()

    series = {}
    try:
        # --- NHPI (monthly, index type 1 = total house and land) ----------
        verify_layout(18100205)
        zp = download_full_zip(18100205, refresh=args.refresh)
        s, _, _ = extract_table(zp, 2, {(1,): "nhpi"}, GEO_205.values())
        by_id = {v: k for k, v in GEO_205.items()}
        for gid, keys in s.items():
            series[f"nhpi.{by_id[gid]}"] = series_from_months(
                rnd(keys["nhpi"], nd=1), "m")
        print(f"  nhpi: {sum(1 for k in series if k.startswith('nhpi'))} geos")

        # --- population (quarterly, single-dimension cube) -----------------
        verify_layout(17100009)
        zp = download_full_zip(17100009, refresh=args.refresh)
        s, _, _ = extract_table(zp, 1, {(): "pop"}, GEO_PROV_1TO11.values())
        by_id = {v: k for k, v in GEO_PROV_1TO11.items()}
        for gid, keys in s.items():
            series[f"pop.{by_id[gid]}"] = series_from_months(
                rnd(keys["pop"], as_int=True), "q")
        print(f"  pop: {sum(1 for k in series if k.startswith('pop'))} geos")

        # --- construction employment (monthly; NAICS 6 = Construction,
        #     statistic 1 = estimate, data type 1 = seasonally adjusted;
        #     published in thousands -> stored as persons) ------------------
        verify_layout(14100355)
        zp = download_full_zip(14100355, refresh=args.refresh)
        s, _, _ = extract_table(zp, 4, {(6, 1, 1): "emp"},
                                GEO_PROV_1TO11.values())
        for gid, keys in s.items():
            series[f"emp_construction.{by_id[gid]}"] = series_from_months(
                rnd(keys["emp"], as_int=True, mult=1000), "m")
        print(f"  emp_construction: "
              f"{sum(1 for k in series if k.startswith('emp'))} geos")

        # --- 5-year mortgage rate (monthly %, geo-only cube) ---------------
        verify_layout(34100145)
        zp = download_full_zip(34100145, refresh=args.refresh)
        s, _, _ = extract_table(zp, 1, {(): "rate"}, [1])
        series["rate.mortgage5y"] = series_from_months(
            rnd(s[1]["rate"], nd=2), "m")
        print("  rate.mortgage5y: ok")

        # --- BCPI (quarterly; building 1 = residential, 7 = non-res;
        #     division 1 = composite) ---------------------------------------
        verify_layout(18100289)
        zp = download_full_zip(18100289, refresh=args.refresh)
        s, _, _ = extract_table(zp, 3, {(1, 1): "res", (7, 1): "nonres"},
                                GEO_289.values())
        by_id = {v: k for k, v in GEO_289.items()}
        for gid, keys in s.items():
            for kind, months in keys.items():
                series[f"bcpi.{by_id[gid]}.{kind}"] = series_from_months(
                    rnd(months, nd=1), "q")
        print(f"  bcpi: {sum(1 for k in series if k.startswith('bcpi'))} series")

        # --- BoC overnight rate --------------------------------------------
        series["rate.overnight"] = series_from_months(
            rnd(fetch_boc_overnight(), nd=2), "m")
        print("  rate.overnight: ok")

    except Exception as e:
        print(f"\n!! context fetch failed: {e}", file=sys.stderr)
        sys.exit(1)

    payload = {
        "retrieved": datetime.now().strftime("%Y-%m-%d"),
        "sources": {
            "nhpi": "StatCan 18-10-0205 (total house and land)",
            "pop": "StatCan 17-10-0009 (quarterly estimates, persons)",
            "emp_construction": "StatCan 14-10-0355 (LFS, NAICS Construction, "
                                "SA, persons)",
            "rate.mortgage5y": "StatCan 34-10-0145 (CMHC 5-yr conventional, %)",
            "rate.overnight": "Bank of Canada Valet V39079 (month-end, %)",
            "bcpi": "StatCan 18-10-0289 (division composite; Ottawa = Ontario "
                    "part; 'composite' = 15-CMA composite)",
        },
        "series": series,
    }
    out = OUTPUT_DIR / "context.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))
    print(f"\nwrote {out.name} ({out.stat().st_size/1024:.1f} KB, "
          f"{len(series)} series)")


if __name__ == "__main__":
    main()
