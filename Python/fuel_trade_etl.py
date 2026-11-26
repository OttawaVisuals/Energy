"""
fuel_trade_etl.py

Production, imports, exports and transfers between provinces for the fuels
that matter to heating, by province and territory, for the District Energy
page's "Where Canada's fuels come from" section.

INPUTS (Statistics Canada full-table CSV downloads, cached in
Python/fueltrade_cache/ -- scratch, never a deliverable)
    25-10-0029  Supply and demand of primary and secondary energy, TJ, annual
                -> natural gas, light fuel oil, heavy fuel oil
    25-10-0021  Electric power, annual supply and disposition, MWh
                -> electricity (generation, US imports/exports, interprovincial)
    25-10-0081  Petroleum products by supply and disposition, monthly, m3
                -> propane (summed to calendar years; only years with all 12
                   months for every flow are kept)
    Download URL pattern:
    https://www150.statcan.gc.ca/n1/tbl/csv/<pid>-eng.zip

OUTPUT
    districtenergy_json/fuel_trade.json
    data[fuel][geo][year] = [production, imports, exports, net_transfer_in]
    in petajoules (PJ), null where StatCan has no value.

CONVERSIONS (stated, not hidden)
    TJ -> PJ        / 1000
    MWh -> PJ       x 3.6 GJ/MWh / 1e6
    propane m3 -> PJ  x 25.60 GJ/m3 / 1e6   (25.60 MJ/L, the HOT2000-internal
                    factor used elsewhere in this repo; ASSUMED, labelled so)

WHAT THIS IS NOT
    Not consumption, not a supply balance. Imports/exports are StatCan's own
    labels (international trade); transfers between provinces are a separate
    slot (net receipts; electricity = receipts - deliveries). Biomass is absent:
    StatCan's "Renewable fuels" row is biofuels, not wood, and there is no wood
    volume or trade series.

HONESTY RAILS
    Suppressed / missing cells stay null (never 0). Aggregate geographies
    ("Atlantic provinces", "Yukon, Northwest Territories and Nunavut") are left
    out so nothing is double counted. Checks are written to meta.checks:
    electricity 0029 vs 0021, and provinces summed vs the Canada row.
"""

import csv
import io
import json
import sys
import urllib.request
import zipfile
from collections import defaultdict
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CACHE = Path(__file__).resolve().parent / "fueltrade_cache"
OUT = ROOT / "districtenergy_json" / "fuel_trade.json"
UA = "energy-suite-etl/1.0 (+https://github.com/OttawaVisuals/Energy)"
URL = "https://www150.statcan.gc.ca/n1/tbl/csv/{pid}-eng.zip"

GEOS = ["Canada", "Newfoundland and Labrador", "Prince Edward Island",
        "Nova Scotia", "New Brunswick", "Quebec", "Ontario", "Manitoba",
        "Saskatchewan", "Alberta", "British Columbia", "Yukon",
        "Northwest Territories", "Nunavut"]
FIRST_YEAR = 2005
TJ_PER_PJ = 1000.0
MWH_TO_PJ = 3.6 / 1e6
PROPANE_GJ_PER_M3 = 25.60
SLOTS = ["production", "imports", "exports", "net_transfer_in"]


def fetch(pid):
    CACHE.mkdir(exist_ok=True)
    p = CACHE / f"{pid}.csv"
    if not p.exists():
        req = urllib.request.Request(URL.format(pid=pid),
                                     headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=180) as r:
            z = zipfile.ZipFile(io.BytesIO(r.read()))
        p.write_bytes(z.read(f"{pid}.csv"))
    return list(csv.DictReader(open(p, encoding="utf-8-sig")))


def num(r):
    v = (r.get("VALUE") or "").strip()
    return float(v) if v else None


def empty():
    return {s: None for s in SLOTS}


def build():
    data = defaultdict(lambda: defaultdict(dict))   # fuel -> geo -> year -> slots
    missing = defaultdict(int)
    src = {}

    # ---- 25-10-0029: gas, light fuel oil, heavy fuel oil -------------------
    rows = fetch(25100029)
    src["25-10-0029"] = {"title": "Supply and demand of primary and secondary "
                         "energy in terajoules, annual", "last_year": max(
                             r["REF_DATE"] for r in rows)}
    fmap = {"Natural gas": "gas", "Light fuel oil": "light_fuel_oil",
            "Heavy fuel oil": "heavy_fuel_oil"}
    cmap = {"Production": "production", "Imports": "imports",
            "Exports": "exports", "Inter-regional transfers": "net_transfer_in"}
    for r in rows:
        f = fmap.get(r["Fuel type"]); s = cmap.get(r["Supply and demand characteristics"])
        if not f or not s or r["GEO"] not in GEOS or int(r["REF_DATE"]) < FIRST_YEAR:
            continue
        v = num(r)
        cell = data[f][r["GEO"]].setdefault(int(r["REF_DATE"]), empty())
        if v is None:
            missing[f] += 1
        else:
            cell[s] = v / TJ_PER_PJ
    # kept for the electricity cross-check
    prim_exp = {}
    for r in rows:
        if (r["Fuel type"].startswith("Primary electricity")
                and r["Supply and demand characteristics"] == "Exports"
                and r["GEO"] in GEOS and num(r) is not None):
            prim_exp[(r["GEO"], int(r["REF_DATE"]))] = num(r)

    # ---- 25-10-0021: electricity ------------------------------------------
    rows = fetch(25100021)
    src["25-10-0021"] = {"title": "Electric power, electric utilities and "
                         "industry, annual supply and disposition",
                         "last_year": max(r["REF_DATE"] for r in rows)}
    emap = {"Total generation of electricity": "production",
            "Total imports of electricity from the United States": "imports",
            "Total exports of electricity to the United States": "exports",
            "Total interprovincial receipts of electricity": "rec",
            "Total interprovincial deliveries of electricity": "dlv"}
    raw = defaultdict(dict)
    for r in rows:
        k = emap.get(r["Electric power, components"])
        if (not k or r["Estimates"] != "Electricity quantity"
                or r["GEO"] not in GEOS or int(r["REF_DATE"]) < FIRST_YEAR):
            continue
        v = num(r)
        raw[(r["GEO"], int(r["REF_DATE"]))][k] = v
        if v is None:
            missing["electricity"] += 1
    for (g, y), d in raw.items():
        cell = empty()
        for s in ("production", "imports", "exports"):
            if d.get(s) is not None:
                cell[s] = d[s] * MWH_TO_PJ
        if d.get("rec") is not None and d.get("dlv") is not None:
            cell["net_transfer_in"] = (d["rec"] - d["dlv"]) * MWH_TO_PJ
        data["electricity"][g][y] = cell

    # ---- 25-10-0081: propane (monthly m3 -> calendar years) ----------------
    rows = fetch(25100081)
    src["25-10-0081"] = {"title": "Petroleum products by supply and "
                         "disposition, monthly", "last_month": max(
                             r["REF_DATE"] for r in rows)}
    pmap = {"Field production, supply": "production",
            "Refinery and blender net production, supply": "production",
            "Imports, supply": "imports", "Exports, disposition": "exports",
            "Net inter-regional receipts, supply": "net_transfer_in"}
    acc = defaultdict(lambda: defaultdict(dict))  # (geo,year)->slot->month->val
    bad_cells = 0
    for r in rows:
        if r["Products"] != "Propane" or r["GEO"] not in GEOS:
            continue
        s = pmap.get(r["Supply and disposition"])
        if not s:
            continue
        y, m = r["REF_DATE"].split("-")
        v = num(r)
        key = (r["GEO"], int(y))
        slot = acc[key][s]
        if v is None:
            bad_cells += 1
            slot.setdefault((m, r["Supply and disposition"]), None)
        else:
            slot[(m, r["Supply and disposition"])] = v
    dropped_years = []
    for (g, y), slots in acc.items():
        cell = empty()
        for s, d in slots.items():
            kinds = {k[1] for k in d}
            ok = all(sum(1 for kk, vv in d.items() if kk[1] == kind
                         and vv is not None) == 12 for kind in kinds)
            if not ok:
                if (y, "incomplete") not in dropped_years:
                    dropped_years.append((y, "incomplete"))
                continue
            cell[s] = sum(v for v in d.values() if v is not None) \
                * PROPANE_GJ_PER_M3 / 1e6
        if any(v is not None for v in cell.values()):
            data["propane"][g][y] = cell
    propane_years = sorted({y for g in data["propane"].values() for y in g})
    missing["propane"] = bad_cells

    # ---- checks -----------------------------------------------------------
    checks = {}
    n = 0
    off = []
    for (g, y), tj in sorted(prim_exp.items()):
        e = data["electricity"].get(g, {}).get(y, {}).get("exports")
        if e is None or tj == 0:
            continue
        n += 1
        diff = abs(tj / TJ_PER_PJ - e) / (tj / TJ_PER_PJ)
        if diff > 0.02:
            off.append([g, y, round(tj / TJ_PER_PJ, 2), round(e, 2)])
    checks["electricity_exports_0029_vs_0021"] = {
        "cells_compared": n, "cells_differing_over_2pct": len(off),
        "latest_year_differing": max((o[1] for o in off), default=None),
        "differing_cells_[geo,year,0029_PJ,0021_PJ]": off,
        "note": "electricity on the page uses 0021 throughout"}
    sums = {}
    for fuel, geos in data.items():
        worst_gap = 0.0
        for y in geos.get("Canada", {}):
            for s in ("production", "imports", "exports"):
                c = geos["Canada"][y][s]
                parts = [geos[g][y][s] for g in GEOS[1:]
                         if y in geos.get(g, {}) and geos[g][y][s] is not None]
                if c and parts:
                    worst_gap = max(worst_gap, abs(sum(parts) - c) / abs(c))
        sums[fuel] = round(worst_gap, 3)
    checks["provinces_sum_vs_canada_max_relative_gap"] = sums

    out = {
        "meta": {
            "generated": date.today().isoformat(),
            "units": "petajoules (PJ)",
            "slots": SLOTS,
            "geos": GEOS,
            "fuels": {
                "gas": "Natural gas",
                "electricity": "Electricity",
                "light_fuel_oil": "Light fuel oil (closest to home heating oil)",
                "heavy_fuel_oil": "Heavy fuel oil",
                "propane": "Propane"},
            "years": {f: sorted({y for g in data[f].values() for y in g})
                      for f in data},
            "sources": src,
            "conversions": {"TJ_to_PJ": "/1000",
                            "MWh_to_PJ": "x 3.6 GJ/MWh / 1e6",
                            "propane": f"m3 x {PROPANE_GJ_PER_M3} GJ/m3 / 1e6 "
                                       "(assumed HOT2000 factor)"},
            "missing_cells": dict(missing),
            "propane_years_kept": propane_years,
            "checks": checks,
            "not_included": ["biomass / wood volumes or trade (no StatCan "
                             "series; 'Renewable fuels' is biofuels)",
                             "consumption", "aggregate regions"],
        },
        "data": {f: {g: {str(y): [None if c[s] is None else round(c[s], 3)
                                  for s in SLOTS]
                         for y, c in sorted(ys.items())}
                     for g, ys in geos.items()}
                 for f, geos in data.items()},
    }
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")),
                   encoding="utf-8")
    print("wrote", OUT, f"({OUT.stat().st_size // 1024} KB)")
    print(json.dumps({"missing_cells": out["meta"]["missing_cells"],
                      "checks": out["meta"]["checks"]}, indent=1))


if __name__ == "__main__":
    sys.exit(build())
