"""
construction_context_etl.py

Phase-4a context ETL for the Construction Activity Dashboard (see
docs/archive/CONSTRUCTION_PLAN.md section 1.2). Produces construction_json/context.json —
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

TIER-1 ADDITIONS (verified live 2026-08-27)
    18-10-0286  Residential renovation price indexes, by project (quarterly).
                  Shares 18-10-0289's geography dimension exactly, so GEO_289
                  is reused. COVERAGE RULE, measured against the full table:
                  the 45 detail project types are published for CMAs ONLY —
                  all 8 dashboard CMAs carry every kept project from 2017-01.
                  Provinces and the 15-CMA composite carry the composite
                  project type and nothing else. Prince Edward Island has no
                  member in this table at all. The page must therefore offer a
                  CMA picker for the project-level chart rather than following
                  the page geography blindly.
    36-10-0677  Housing Economic Account (annual, 1961+): residential
                  investment split new construction / renovations / ownership
                  transfer costs, in current AND constant dollars. Replaces the
                  2017-start nominal-only work-type split from 34-10-0293.
                  Fetched with floor="1961-01" — the default 1990 trim exists
                  to keep the monthly CMHC files small and costs 29 years of
                  history on a series that is only 65 points long.
    14-10-0442  Job vacancies, payroll employees, vacancy rate and average
                  offered hourly wage by industry sub-sector (quarterly,
                  UNADJUSTED), Canada + provinces. Chosen over the monthly
                  14-10-0406 because that table is Canada-only, and this page
                  is driven by a geography selector.

OUTPUT  construction_json/context.json
    {"retrieved": "...", "series": {key: {start, freq('m'|'q'|'a'), values[]}}}
    Keys:
      nhpi.<geo>               monthly index, geo = ca | CMA codes
      pop.<geo>                quarterly persons (int), geo = ca | province
      emp_construction.<geo>   monthly persons (int), geo = ca | province
      rate.mortgage5y          monthly %, 2 decimals
      rate.overnight           monthly % (month-end), 2 decimals
      bcpi.<geo>.res|nonres    quarterly index, geo = composite | CMA codes
      reno_price.<geo>.<proj>  quarterly index; <proj> = composite everywhere,
                               plus the 12 detail projects for CMAs only
      housing_acct.<geo>.<asset>.<price>
                               ANNUAL $ millions; asset = new | reno |
                               transfer | total; price = current | constant
      vac.<geo>.<stat>         quarterly; stat = count (int jobs) |
                               rate (%, 1 dp) | wage ($/h, 2 dp)
      absorb.<cma>.absorbed|unabsorbed
                               monthly units (int); CMA-ONLY, cma_total = the
                               all-CMA aggregate
      vacancy.<cma>            ANNUAL rental vacancy rate %; CMA-ONLY

TIER-2 ADDITIONS (verified live 2026-08-27)
    18-10-0289  Division detail (envelope / openings / HVAC / electrical /
                  concrete / wood) for 5 building types across 18 geographies.
                  Written to a SEPARATE construction_json/bcpi.json, lazy-
                  loaded by the page, because it outweighs the whole of
                  context.json and only one advanced section reads it.
                  Division detail starts 2017-01 for EVERY building type; the
                  1981 history in this cube is non-residential composites only.
    34-10-0149  Absorptions and unabsorbed inventory of newly completed
                  dwellings (monthly). CMA-ONLY — no provincial members, so
                  the page shows this for metro views and for Canada (via the
                  all-CMA aggregate) and hides it for provinces.
    34-10-0127  Rental vacancy rate, apartments of 6+ units (annual October
                  survey). CMA-ONLY, same rule.

OUTPUT  construction_json/bcpi.json
    {"retrieved", "sources", "buildings", "divisions",
     "series": {"bcpi_div.<geo>.<building>.<division>": {start, freq, values}}}

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
    18100286: 2,   # geo, project type
    36100677: 7,   # geo, sector, asset, dwelling, housing type, prices, est
    14100442: 3,   # geo, NAICS, statistics
    34100149: 3,   # geo, completed dwelling units, type of dwelling unit
    34100127: 1,   # geo
})

# --- geography member ids (verified via getCubeMetadata 2026-07-09) ----------
PROVS = ["ca", "nl", "pe", "ns", "nb", "qc", "on", "mb", "sk", "ab", "bc"]
GEO_PROV_1TO11 = dict(zip(PROVS, range(1, 12)))   # 17-10-0009 and 14-10-0355

GEO_205 = {"ca": 1, "halifax": 8, "montreal": 15, "ottawa_qc": 16,
           "ottawa_on": 18, "toronto": 20, "winnipeg": 30, "calgary": 35,
           "edmonton": 36, "vancouver": 39}

# 18-10-0286 and 18-10-0289 share ONE geography dimension, member-for-member
# (verified 2026-08-27), so a single pair of maps serves both price tables.
# There is no Prince Edward Island member in either. "composite" is the
# 15-CMA composite, which is the closest thing either table has to a national
# figure — it is NOT Canada, and the page says so.
GEO_PRICE_CMA = {"halifax": 5, "montreal": 10, "ottawa_on": 12, "toronto": 13,
                 "winnipeg": 16, "calgary": 21, "edmonton": 22, "vancouver": 24}
GEO_PRICE_PROV = {"composite": 1, "nl": 2, "ns": 4, "nb": 6, "qc": 8, "on": 11,
                  "mb": 15, "sk": 17, "ab": 20, "bc": 23}
GEO_289 = dict(composite=1, **GEO_PRICE_CMA)
GEO_286_CMA, GEO_286_PROV = GEO_PRICE_CMA, GEO_PRICE_PROV

# 18-10-0286 project types kept: the composite plus the measures this suite
# already models elsewhere (heat pump / windows / envelope / solar). Ids from
# getCubeMetadata 2026-08-27.
PROJ_286 = {1: "composite", 14: "hvac", 16: "heatpump", 18: "furnace",
            49: "windows_doors", 55: "windows", 51: "ext_doors",
            8: "solar", 45: "roofing", 7: "siding", 23: "basement",
            2: "ext_add", 19: "int_add"}

# 36-10-0677 geography runs Canada + provinces as ids 1..11, same order as
# PROVS — identical to GEO_PROV_1TO11.
ASSET_677 = {1: "total", 2: "new", 3: "reno", 4: "transfer"}
PRICE_677 = {1: "current", 2: "constant"}

# 14-10-0442: NAICS 5 = Construction; geography Canada + provinces as 1..11.
STAT_442 = {1: "count", 4: "rate", 5: "wage"}

# --- Tier 2 -----------------------------------------------------------------
# 18-10-0289 division detail. Building types and divisions are trimmed to the
# ones that carry a story for this suite: the envelope ("Thermal and moisture
# protection", "Openings") against the mechanical and structural trades. All
# 24 divisions exist, but shipping every division x building type x geography
# would triple the payload for lines nobody plots.
BLDG_289 = {1: "res", 5: "single", 4: "lowrise", 3: "highrise", 7: "nonres"}
DIV_289 = {1: "composite", 9: "envelope", 10: "openings", 17: "hvac",
           19: "electrical", 4: "concrete", 8: "wood"}
# COVERAGE: division detail begins 2017-01 for EVERY building type. The 1981
# history in this cube belongs to the non-residential composites only
# (commercial/industrial/institutional/office/school/warehouse); residential
# and all division-level series start 2017. Verified against the full table
# 2026-08-27.
DIV_289_FLOOR = "2017-01"

# 34-10-0149 absorptions / unabsorbed inventory and 34-10-0127 vacancy rates
# are BOTH census-metropolitan-area tables — no provincial members at all.
# Member id 1 is the all-CMA aggregate, which is what a Canada view shows.
GEO_149 = {"cma_total": 1, "calgary": 2, "edmonton": 4, "halifax": 5,
           "montreal": 10, "ottawa": 13, "ottawa_qc": 14, "ottawa_on": 15,
           "toronto": 24, "vancouver": 26, "winnipeg": 29}
GEO_127 = {"cma_total": 1, "calgary": 2, "edmonton": 4, "halifax": 5,
           "montreal": 9, "ottawa": 11, "ottawa_on": 12, "ottawa_qc": 13,
           "toronto": 23, "vancouver": 25, "winnipeg": 28}
ABSORB_149 = {(1, 1): "absorbed", (2, 1): "unabsorbed"}

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


STEP = {"m": 1, "q": 3, "a": 12}


def series_from_months(months, freq):
    """{YYYY-MM: value} -> {start, freq, values[]} with null gaps. Monthly
    steps by 1 month; quarterly steps by 3 and annual by 12 (StatCan quarterly
    REF_DATEs are the first month of each quarter, annual ones the first month
    of the year — extract_table normalizes a bare 'YYYY' to 'YYYY-01')."""
    if not months:
        return None
    start, last = min(months), max(months)
    idx = month_range(start, last)[::STEP[freq]]
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
    bcpi_series = {}
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
        zp_289 = download_full_zip(18100289, refresh=args.refresh)
        s, _, _ = extract_table(zp_289, 3, {(1, 1): "res", (7, 1): "nonres"},
                                GEO_289.values())
        by_id = {v: k for k, v in GEO_289.items()}
        for gid, keys in s.items():
            for kind, months in keys.items():
                series[f"bcpi.{by_id[gid]}.{kind}"] = series_from_months(
                    rnd(months, nd=1), "q")
        print(f"  bcpi: {sum(1 for k in series if k.startswith('bcpi'))} series")

        # --- renovation price index by project (quarterly) -----------------
        #     Detail projects exist for CMAs only; provinces and the 15-CMA
        #     composite carry the composite project type alone. Requesting the
        #     detail for a province is not an error, it just yields nothing —
        #     so ask for exactly what each geography publishes and count what
        #     comes back, rather than silently shipping empty keys.
        verify_layout(18100286)
        zp = download_full_zip(18100286, refresh=args.refresh)
        allowed_cma = {(pid,): name for pid, name in PROJ_286.items()}
        s_cma, _, _ = extract_table(zp, 2, allowed_cma, GEO_286_CMA.values())
        s_prov, _, _ = extract_table(zp, 2, {(1,): "composite"},
                                     GEO_286_PROV.values())
        by_id = {v: k for k, v in
                 {**GEO_286_CMA, **GEO_286_PROV}.items()}
        n_detail = 0
        for src in (s_cma, s_prov):
            for gid, keys in src.items():
                for proj, months in keys.items():
                    series[f"reno_price.{by_id[gid]}.{proj}"] = \
                        series_from_months(rnd(months, nd=1), "q")
                    n_detail += proj != "composite"
        print(f"  reno_price: "
              f"{sum(1 for k in series if k.startswith('reno_price'))} series "
              f"({n_detail} CMA project-level, "
              f"{len(GEO_286_PROV)} composite-only geographies)")

        # --- Housing Economic Account (annual, 1961+) ----------------------
        #     sector 1 = total economy, dwelling 1 = all types, housing type
        #     1 = all. Published in millions already, so no rescaling: stored
        #     to 0 dp as the dashboard's other dollar series are in millions.
        verify_layout(36100677)
        zp = download_full_zip(36100677, refresh=args.refresh)
        allowed_677 = {(1, a, 1, 1, p, 1): f"{ASSET_677[a]}.{PRICE_677[p]}"
                       for a in ASSET_677 for p in PRICE_677}
        s, uom_677, scal_677 = extract_table(
            zp, 7, allowed_677, GEO_PROV_1TO11.values(), floor="1961-01")
        by_id = {v: k for k, v in GEO_PROV_1TO11.items()}
        for gid, keys in s.items():
            for kind, months in keys.items():
                series[f"housing_acct.{by_id[gid]}.{kind}"] = \
                    series_from_months(rnd(months, nd=0), "a")
        print(f"  housing_acct: "
              f"{sum(1 for k in series if k.startswith('housing_acct'))} "
              f"series  [uom={uom_677}, scalar={scal_677}]")

        # --- construction job vacancies (quarterly, NAICS 5) ---------------
        #     Unadjusted — this table has no SA variant. The monthly SA
        #     sibling (14-10-0406) is Canada-only, which does not fit a
        #     geography-driven page.
        verify_layout(14100442)
        zp = download_full_zip(14100442, refresh=args.refresh)
        allowed_442 = {(5, st): name for st, name in STAT_442.items()}
        s, _, _ = extract_table(zp, 3, allowed_442, GEO_PROV_1TO11.values())
        for gid, keys in s.items():
            for kind, months in keys.items():
                nd, as_int = (0, True) if kind == "count" else \
                             ((1, False) if kind == "rate" else (2, False))
                series[f"vac.{by_id[gid]}.{kind}"] = series_from_months(
                    rnd(months, nd=nd, as_int=as_int), "q")
        print(f"  vac: {sum(1 for k in series if k.startswith('vac.'))} series")

        # --- BCPI division detail (quarterly) -> its own file --------------
        #     Reuses the 18-10-0289 zip already downloaded above. Kept out of
        #     context.json because it is ~5x the size of everything else in
        #     there combined and only one advanced section reads it; the page
        #     lazy-loads bcpi.json the same way it lazy-loads newhomes_json.
        allowed_div = {(b, d): f"{bn}.{dn}"
                       for b, bn in BLDG_289.items()
                       for d, dn in DIV_289.items()}
        geos_289 = dict(GEO_PRICE_PROV, **GEO_PRICE_CMA)
        s_div, _, _ = extract_table(zp_289, 3, allowed_div, geos_289.values(),
                                    floor=DIV_289_FLOOR)
        by_id = {v: k for k, v in geos_289.items()}
        for gid, keys in s_div.items():
            for kind, months in keys.items():
                bcpi_series[f"bcpi_div.{by_id[gid]}.{kind}"] =                     series_from_months(rnd(months, nd=1), "q")
        print(f"  bcpi_div: {len(bcpi_series)} series "
              f"({len(s_div)} geographies x {len(BLDG_289)} building types "
              f"x {len(DIV_289)} divisions)")

        # --- absorptions / unabsorbed inventory (monthly, CMA-only) --------
        verify_layout(34100149)
        zp = download_full_zip(34100149, refresh=args.refresh)
        s, _, _ = extract_table(zp, 3, ABSORB_149, GEO_149.values())
        by_id = {v: k for k, v in GEO_149.items()}
        for gid, keys in s.items():
            for kind, months in keys.items():
                series[f"absorb.{by_id[gid]}.{kind}"] = series_from_months(
                    rnd(months, as_int=True), "m")
        print(f"  absorb: {sum(1 for k in series if k.startswith('absorb'))} series")

        # --- rental vacancy rate (annual, CMA-only) ------------------------
        verify_layout(34100127)
        zp = download_full_zip(34100127, refresh=args.refresh)
        s, _, _ = extract_table(zp, 1, {(): "vacancy"}, GEO_127.values())
        by_id = {v: k for k, v in GEO_127.items()}
        for gid, keys in s.items():
            series[f"vacancy.{by_id[gid]}"] = series_from_months(
                rnd(keys["vacancy"], nd=1), "a")
        print(f"  vacancy: {sum(1 for k in series if k.startswith('vacancy'))} series")

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
            "reno_price": "StatCan 18-10-0286 (residential renovation price "
                          "index; project-level detail is published for CMAs "
                          "only — provinces and the 15-CMA composite carry "
                          "the 8-project composite alone; no PEI member)",
            "housing_acct": "StatCan 36-10-0677 (Housing Economic Account, "
                            "investment, total economy, all dwelling and "
                            "housing types; $ millions, annual from 1961)",
            "vac": "StatCan 14-10-0442 (job vacancies, NAICS 23 Construction, "
                   "quarterly, UNADJUSTED; count = jobs, rate = %, "
                   "wage = average offered $/hour)",
            "absorb": "StatCan 34-10-0149 (absorptions and unabsorbed "
                      "inventory of newly completed dwellings, monthly; "
                      "CENSUS METROPOLITAN AREAS ONLY — no provincial "
                      "members. 'cma_total' is the all-CMA aggregate)",
            "vacancy": "StatCan 34-10-0127 (rental vacancy rate, apartment "
                       "structures of six units and over, annual October "
                       "survey; CMA-only, same caveat as absorb)",
        },
        "series": series,
    }
    out = OUTPUT_DIR / "context.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))
    print(f"\nwrote {out.name} ({out.stat().st_size/1024:.1f} KB, "
          f"{len(series)} series)")

    # BCPI division detail ships separately: only one advanced section reads
    # it, and it outweighs everything in context.json put together, so the
    # page lazy-loads this file the way it lazy-loads newhomes_json.
    bcpi_payload = {
        "retrieved": payload["retrieved"],
        "sources": {
            "bcpi_div": "StatCan 18-10-0289 (building construction price "
                        "index by division). Division detail begins 2017-01 "
                        "for every building type — the 1981 history in this "
                        "cube belongs to the non-residential composites only. "
                        "'composite' geography = 15-CMA composite, NOT Canada; "
                        "no Prince Edward Island member.",
        },
        "buildings": BLDG_289,
        "divisions": DIV_289,
        "series": bcpi_series,
    }
    out2 = OUTPUT_DIR / "bcpi.json"
    with open(out2, "w", encoding="utf-8") as f:
        json.dump(bcpi_payload, f, ensure_ascii=False, separators=(",", ":"))
    print(f"wrote {out2.name} ({out2.stat().st_size/1024:.1f} KB, "
          f"{len(bcpi_series)} series)")


if __name__ == "__main__":
    main()
