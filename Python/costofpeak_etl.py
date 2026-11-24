"""costofpeak_etl.py — build costofpeak_json/costofpeak.json for costofpeak.html.

WHAT IT DOES
    Reads published IESO and NREL workbooks plus the Grid page's own history file,
    and writes one compact JSON the page draws from. No cost is invented here: every
    number is copied from a source workbook, and every sheet it came from is named in
    `meta.sources`. Anything we *derive* (load factor, effective-capacity ratios, the
    build-out capital estimate) is computed on the page and labelled "ours".

INPUTS  (download once into Python/costofpeak_cache/ — gitignored, regenerable)
    IESO 2026 Annual Planning Outlook (APO), base URL
    https://www.ieso.ca/-/media/Files/IESO/Document-Library/planning-forecasts/apo/2026/
        2026-Annual-Planning-Outlook-Data-Tables.xlsx
            Fig 2 peak demand · Fig 5-7 installed / effective capacity · Fig 8 2026 stock
        2026-APO-Capacity-Expansion-Scenario-and-Outcomes-Data.xlsx
            Fig 1-3 2050 build-out · 'Levelized Cost and Components' (2025 CAD)
            'Elec Cost by Component' and 'Gen Cost by Resource Type' (nominal $B)
        2026-APO-Marginal-Energy-Costs-and-Capacity-Costs.xlsx
            Table 1 annual capacity cost ($/kW-yr, 2025 CAD) · Table 2 cumulative additions
        2026-APO-Fuel-Cost.xlsx           Dawn gas price and IESO's own USD/CAD
    NREL 2024 Annual Technology Baseline, v4 workbook (data.openei.org/submissions/6006,
        CC BY 4.0): 'Summary_CAPEX', 'Summary_FOM', 'Summary_VOM' sheets, 2022 USD.
    grid_json/grid_on_history.json (from grid_history_etl.py): monthly Ontario demand.

OUTPUT   costofpeak_json/costofpeak.json

LICENCE  IESO content is covered by IESO's website Terms of Use; the page carries the
         required copyright notice. NREL ATB is CC BY 4.0. Fortis figures are quoted
         from a public regulatory filing and cited.

Run:  python Python/costofpeak_etl.py
"""
import json
import os
import statistics
import datetime
import openpyxl

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(ROOT, "Python", "costofpeak_cache")
OUT = os.path.join(ROOT, "costofpeak_json")


def wb(name):
    return openpyxl.load_workbook(os.path.join(CACHE, name), read_only=True, data_only=True)


def clean(v):
    if isinstance(v, float):
        return round(v, 4)
    if isinstance(v, str):
        return v.replace("\xa0", " ").strip()
    return v


def rows(ws):
    return [[clean(c) for c in r] for r in ws.iter_rows(values_only=True)]


def table_by_header(ws, first_header):
    """Rows after the header row whose first cell == first_header, until 'Back to main menu'/blank."""
    R = rows(ws)
    hi = next(i for i, r in enumerate(R) if r and r[0] == first_header)
    hdr = R[hi]
    out = {}
    for r in R[hi + 1:]:
        if not r or r[0] in (None, "") or str(r[0]).startswith("Back to"):
            break
        out[r[0]] = {str(h): v for h, v in zip(hdr[1:], r[1:]) if h not in (None, "")}
    return out


# ---------------------------------------------------------------- IESO
def ieso():
    dt = wb("2026-Annual-Planning-Outlook-Data-Tables.xlsx")
    cx = wb("2026-APO-Capacity-Expansion-Scenario-and-Outcomes-Data.xlsx")
    mc = wb("2026-APO-Marginal-Energy-Costs-and-Capacity-Costs.xlsx")
    fc = wb("2026-APO-Fuel-Cost.xlsx")
    o = {}

    o["installed_2026_gw"] = {k: v["2026 Installed Capacity (GW)"]
                             for k, v in table_by_header(dt["Figure 8"], "Fuel").items() if k != "Total"}
    o["installed_by_year_gw"] = table_by_header(dt["Figure 5"], "Fuel")
    o["summer_effective_gw"] = table_by_header(dt["Figure 6"], "Fuel")
    o["winter_effective_gw"] = table_by_header(dt["Figure 7"], "Fuel")

    R = rows(dt["Figure 2"])
    hdr = next(r for r in R if r and r[1] == 2026)
    o["peak_demand_gw"] = {r[0]: {str(y): v for y, v in zip(hdr[1:], r[1:]) if y}
                           for r in R if r and r[0] and "Peak" in str(r[0])}

    o["buildout_2050_mw"] = {}
    for key, sheet in (("reference", "Figure 1"), ("high", "Figure 2"), ("low", "Figure 3")):
        t = table_by_header(cx[sheet], "Installed Capacity, by Fuel Type (MW)")
        o["buildout_2050_mw"][key] = {k: {"existing_committed": v.get("Existing and Committed Capacity Remaining in 2050"),
                                          "new": v.get("New Capacity Online by 2050"),
                                          "total": v.get("Total Capacity in 2050")} for k, v in t.items()}

    # system cost (nominal $B)
    R = rows(cx["Elec Cost by Component"])
    sys_cost, cur = {}, None
    for r in R:
        if r and isinstance(r[0], str) and r[0].endswith("Scenario"):
            cur = r[0].replace(" Scenario", "")
            years = [y for y in r[1:] if y]
            sys_cost[cur] = {}
        elif cur and r and r[0] and not str(r[0]).startswith("Back"):
            sys_cost[cur][r[0].strip()] = {str(y): v for y, v in zip(years, r[1:]) if v is not None}
    o["system_cost_nominal_bn"] = sys_cost

    R = rows(cx["Gen Cost by Resource Type"])
    hi = next(i for i, r in enumerate(R) if r and r[0] == "Reference Scenario")
    years = [y for y in R[hi][1:] if y]
    gen = {}
    for r in R[hi + 1:]:
        if not r or not r[0] or str(r[0]).startswith("Back"):
            break
        gen[r[0]] = {str(y): v for y, v in zip(years, r[1:]) if v is not None}
    o["generation_cost_by_resource_nominal_bn"] = gen

    # levelized cost components (2025 CAD, per nameplate kW)
    R = rows(cx["Levelized Cost and Components"])
    hi = next(i for i, r in enumerate(R) if r and r[0] == "Resource Type")
    years = [y for y in R[hi][4:] if isinstance(y, int)]
    keep = {"occ": ("Overnight Capital Cost",), "fom": ("FOM",), "life": ("Economic Life",),
            "levelized": ("Levelized Cost",), "vom": ("VOM",), "fuel": ("Fuel Cost",),
            "tx": ("Transmission Cost",)}
    lev, rt, sub = {}, None, None
    for r in R[hi + 1:]:
        if r[0]:
            rt = r[0]
        if r[1]:
            sub = r[1]
        if not r[2]:
            continue
        label = r[2]
        for k, pats in keep.items():
            if any(label.startswith(p) for p in pats) and not (k == "occ" and "with Transmission" in label):
                series = {str(y): v for y, v in zip(years, r[4:]) if v is not None}
                lev.setdefault(rt, {}).setdefault(sub, {})[k] = series
    o["levelized_cad2025"] = lev

    # IESO's own annual capacity cost + marginal energy
    R = rows(mc["Table 1"])
    cap = {}
    for r in R:
        if r and isinstance(r[0], int):
            cap[str(r[0])] = {"capacity_cost_kw_yr": r[10], "system_need": r[11],
                              "winter_on_peak_mwh": r[1], "annual_energy_mwh": r[9]}
    o["capacity_cost_cad2025"] = cap
    R = rows(mc["Table 2"])
    hdr = next(r for r in R if r and r[1] and "BESS" in str(r[1]))
    o["cumulative_additions_ref_mw"] = {str(r[0]): {h.replace("\n", " "): v for h, v in zip(hdr[1:], r[1:]) if h}
                                        for r in R if r and isinstance(r[0], int)}

    R = rows(fc["Table 2"])
    o["fx_ieso"] = {str(r[0]): {"usd_per_cad": r[2], "henry_hub_usd": r[1], "dawn_cad": r[4]}
                    for r in R if r and r[0] in (2026, "2027 onward")}
    return o


# ---------------------------------------------------------------- NREL
NREL_PICK = {  # label -> (Technology, TechDetail)
    "Gas combustion turbine (F-frame)": ("NaturalGas_FE", "CTAvgCF"),
    "Gas combined cycle (F-frame)": ("NaturalGas_FE", "CCAvgCF"),
    "Battery, 4-hour (utility)": ("Utility-Scale Battery Storage", "4Hr Battery Storage"),
    "Battery, 2-hour (utility)": ("Utility-Scale Battery Storage", "2Hr Battery Storage"),
    "Solar PV (utility, class 5)": ("UtilityPV", "Class5"),
    "Wind (land-based, class 4)": ("LandbasedWind", "Class4"),
    "Nuclear (large)": ("Nuclear", "Nuclear"),
    "Nuclear (small modular)": ("Nuclear", "NuclearSMR"),
    "Hydropower (NPD 1)": ("Hydropower", "NPD1"),
}


def nrel():
    w = wb("NREL-ATB-2024-v4-Workbook.xlsx")
    out = {}
    for field, sheet in (("capex", "Summary_CAPEX"), ("fom", "Summary_FOM"), ("vom", "Summary_VOM")):
        R = rows(w[sheet])
        hdr = R[0]
        yrs = [(i, h) for i, h in enumerate(hdr) if isinstance(h, int)]
        for label, (tech, det) in NREL_PICK.items():
            for r in R[1:]:
                if r[4] == tech and r[5] == det and r[2] == "Moderate" and r[1] in ("RD", "R&D", "*"):
                    out.setdefault(label, {})[field] = {str(y): (round(r[i], 1) if isinstance(r[i], (int, float)) else None)
                                                        for i, y in yrs if y in (2025, 2030, 2035, 2040, 2045, 2050)}
                    break
    return out



# ---------------------------------------------------------------- hand-copied tables
# These come from PDFs, not workbooks, so they are typed here with their citation.
# Each was read from the source document on the date in `read`.
FORTIS = {
    "source": "FortisBC Energy Inc., Kelowna Electrification Case Study, filed with the BC Utilities Commission "
              "2023-02-24 (FEI 2022 LTGRP, Project No. 1599324), Tables 4-2, 4-3, 4-4 and Section 4.3",
    "url": "https://www.cdn.fortisbc.com/libraries/docs/default-source/about-us-documents/regulatory-affairs-documents/"
           "gas-utility/230224-fei-2022-ltgrp-fortisbc-additional-evidence-ff.pdf",
    "read": "2026-11-24",
    "currency": "CAD millions; land in 2021 dollars; system-upgrade dollar year not stated",
    "baseline_peak_mw_2040_no_electrification": 472,
    "cases": [
        {"label": "25% of gas heat electrified", "peak_mw": 711, "system_upgrades_m": 930,
         "land_low_m": 345, "land_high_m": 776},
        {"label": "50%", "peak_mw": 950, "system_upgrades_m": 1550, "land_low_m": 605, "land_high_m": 1361},
        {"label": "100%", "peak_mw": 1429, "system_upgrades_m": 1890, "land_low_m": 680, "land_high_m": 1531},
    ],
    "generation_in_same_filing": {
        "local_gas_and_battery_mw": 173, "cost_m": 350,
        "note": "2 RNG simple-cycle gas turbines + 25 MW battery, excludes land and O&M",
        "bc_hydro_capacity_kw_yr": 103.86,
    },
    "excludes": ["upgrades to BC Hydro's own system", "Indigenous consultation costs", "cost of energy",
                 "mitigation programs (demand response, EV charging shifting)"],
}

TD_OTHER = [
    {"id": "elmallah", "label": "PG&E planned distribution upgrades, by size of need (median $/kW, USD, dollar year not stated)",
     "source": "Elmallah, Brockway & Callaway (2022), Environ. Res.: Infrastruct. Sustain. 2, 045005, Table 3",
     "url": "https://escholarship.org/uc/item/8kt4g6cb", "scope": "distribution only (feeders + substation banks); no transmission, no land",
     "rows": [["< 1 MW", 1875, 18863], ["1-2 MW", 1369, 4740], ["2-4 MW", 673, 3978], ["4-8 MW", 438, 2005], [">= 8 MW", 368, 888]],
     "columns": ["Circuit / feeder", "Substation bank"]},
    {"id": "dunsky", "label": "Ontario avoided (deferred) capacity value, 2023, 2021 CAD",
     "source": "Dunsky Energy + Climate Advisors for IESO, Ontario DER Potential Study Vol. 2 (2022-09-30), Table C-2",
     "url": "https://ieso.ca/-/media/Files/IESO/Document-Library/engage/derps/derps-20220930-final-report-volume-2.pdf",
     "scope": "annualized deferral value, NOT capital cost per kW; the distribution value is a proxy (10-20% of OEB system-service capex)",
     "transmission_per_mw_day": 116.80, "distribution_per_mw_day": 4.46},
    {"id": "priyadarshan", "label": "US-wide distribution reinforcement for full housing + EV electrification",
     "source": "Priyadarshan, Crozier, Baker & Kircher (2024), arXiv:2410.04540",
     "url": "https://arxiv.org/abs/2410.04540", "scope": "distribution only, USD, dollar year not stated; $350-790 billion for ~600 GW "
     "(ours: about $580-1,300 per kW)", "low_kw": 580, "high_kw": 1300},
]

# Lifecycle greenhouse gases, gCO2e per kWh. NREL 2021 harmonization gives medians only;
# the IPCC AR5 table gives min / median / max over published studies. Neither reports
# simple-cycle gas separately, and neither covers batteries except NREL (median only).
GHG = {
    "unit": "g CO2e per kWh, full life cycle (incl. upstream fuel and methane)",
    "sources": [
        {"id": "nrel2021", "name": "NREL, Life Cycle GHG Emissions from Electricity Generation: Update (NREL/FS-6A50-80580, 2021)",
         "url": "https://www.nrel.gov/docs/fy21osti/80580.pdf", "stat": "median"},
        {"id": "ipcc", "name": "IPCC AR5 WG3 Annex III, Table A.III.2 (2014)",
         "url": "https://www.ipcc.ch/site/assets/uploads/2018/02/ipcc_wg3_ar5_annex-iii.pdf", "stat": "min / median / max"},
    ],
    "rows": {
        "Gas, combined cycle": {"nrel": 486, "ipcc": [410, 490, 650]},
        "Gas, simple cycle": {"nrel": None, "ipcc": None, "note": "not reported by either source; less efficient than combined cycle, so likely higher"},
        "Nuclear": {"nrel": 13, "ipcc": [3.7, 12, 110]},
        "Hydropower": {"nrel": 21, "ipcc": [1.0, 24, 2200]},
        "Wind (onshore)": {"nrel": 13, "ipcc": [7.0, 11, 56]},
        "Solar PV (utility)": {"nrel": 43, "ipcc": [18, 48, 180]},
        "Battery (Li-ion)": {"nrel": 33, "ipcc": None, "note": "per kWh delivered over lifetime; excludes the energy used to charge it"},
        "Biomass": {"nrel": 52, "ipcc": [130, 230, 420], "note": "the two sources differ about 4x; scope not reconciled"},
    },
}

# ---------------------------------------------------------------- load factor
def load_factor():
    d = json.load(open(os.path.join(ROOT, "grid_json", "grid_on_history.json"), encoding="utf-8"))
    by = {}
    for r in d["monthly"]:
        if r.get("demand_mw_mean") and r.get("demand_mw_peak"):
            by.setdefault(r["month"][:4], []).append(r)
    out = {}
    for y, rs in sorted(by.items()):
        if len(rs) < 12:   # only full years; a partial year would bias peak/mean
            continue
        mean = statistics.mean(r["demand_mw_mean"] for r in rs)
        pk = max(r["demand_mw_peak"] for r in rs)
        winter = [r for r in rs if r["month"][5:] in ("12", "01", "02", "03")]
        out[y] = {"mean_mw": round(mean), "peak_mw": pk, "load_factor": round(mean / pk, 3),
                  "winter_mean_mw": round(statistics.mean(r["demand_mw_mean"] for r in winter)),
                  "winter_peak_mw": max(r["demand_mw_peak"] for r in winter)}
    return out


def main():
    os.makedirs(OUT, exist_ok=True)
    data = {
        "meta": {
            "generated": datetime.date.today().isoformat(),
            "ieso_publication": "2026 Annual Planning Outlook (March 2026; capacity-expansion modules September 2026)",
            "dollars": {"ieso_levelized": "2025 CAD", "ieso_capacity_cost": "2025 CAD",
                        "ieso_system_cost": "nominal CAD billions", "nrel": "2022 USD"},
            "nrel_cost_case": "Moderate cost case, R&D financial case (no tax credits), 30-year recovery period",
            "ieso_notice": "Copyright © 2004-2026 Independent Electricity System Operator, all rights reserved. "
                           "This information is subject to the Terms of Use set out in the IESO's website.",
        },
        "ieso": ieso(),
        "nrel": nrel(),
        "load_factor_on": load_factor(),
        "fortis": FORTIS,
        "td_other": TD_OTHER,
        "ghg": GHG,
    }
    path = os.path.join(OUT, "costofpeak.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, separators=(",", ":"), ensure_ascii=False)
    print("wrote", path, os.path.getsize(path), "bytes")
    print("NREL techs:", {k: sorted(v) for k, v in data["nrel"].items()})
    print("load factor:", {y: v["load_factor"] for y, v in list(data["load_factor_on"].items())[-5:]})


if __name__ == "__main__":
    main()
