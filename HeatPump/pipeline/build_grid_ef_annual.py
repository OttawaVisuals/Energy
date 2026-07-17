# build_grid_ef_annual.py
# Builds data/processed/grid_ef_annual.json: one PUBLISHED annual-average grid
# emissions intensity (g CO2e/kWh) per province per year, plus a single flat
# "marginal estimate" per province. This is the tool's THIRD EF basis (ROADMAP
# item 9 workstream B) -- distinct from the hourly average/marginal surface
# (ef_surface_*.json, ON/QC/AB only). It is:
#   - the ONLY grid EF available for provinces with no hourly pipeline
#     (BC/MB/SK/NS/NB/NL/PE), and
#   - an "official inventory average" alternative for ON/QC/AB, whose
#     difference from the tool's own hourly-surface average is itself
#     informative (see METHODOLOGY.md "Third EF basis" section).
#
# SOURCE (both machine-readable via the StatCan WDS full-table CSV endpoint --
# canada.ca / open.canada.ca CKAN are WAF-blocked in this environment, StatCan
# WDS is not):
#   - GHG numerator: StatCan table 38-10-0097 "Physical flow account for
#     greenhouse gas emissions", sector "Electric power generation,
#     transmission and distribution [BS22110]" (kt CO2e), by province, 2009-2023.
#     This is ECCC National Inventory Report data as carried in StatCan's
#     environmental-economic accounts.
#   - Generation denominator: StatCan table 25-10-0015 "Electric power
#     generation, monthly generation by type of electricity", class
#     "Electricity producers, electric utilities", type "Total all types",
#     summed to annual, by province (MWh).
#
#   intensity_g_per_kWh = kt_CO2e * 1e6 / utility_generation_MWh
#
# WHY the utility-only denominator: the GHG numerator (BS22110) is the utility
# INDUSTRY's emissions; large industrial cogeneration (e.g. Alberta oil-sands
# self-generation) is booked under its host industry (oil & gas), not BS22110.
# Dividing utility-industry emissions by TOTAL generation (incl. that
# industrial self-gen) would deflate the intensity. Using utility-only
# generation keeps numerator and denominator on the same scope and makes the
# NATIONAL result validate almost exactly against ECCC's published headline
# (see cross-check below): 101 g/kWh (2022) vs ECCC's published 100 g/kWh.
#
# DOCUMENTED deviations from the tool's other ON/AB anchors (NOT errors --
# scope differences, explained in METHODOLOGY.md):
#   - Ontario runs ~10-20% below TAF's Annual AEF (TAF attributes ALL grid
#     emissions to gas and uses a year-specific NIR gas intensity; this uses
#     the inventory's actual electric-utility emissions over utility
#     generation).
#   - Alberta runs ~20% below Alberta.ca Figure 7 (~408 vs 510 g/kWh, 2022):
#     Alberta's NIR grid-intensity figure allocates industrial cogeneration
#     emissions to electricity, which BS22110 does not. Flagged, not "fixed".
#
# MARGINAL ESTIMATES for provinces with no hourly surface: a single flat value
# with a per-province rationale (see MARGINAL_ESTIMATES below). These are
# screening estimates only; the UI labels them as such.
#
# pip install requests pandas
#
# Re-run: python build_grid_ef_annual.py   (downloads are cached under
# data/raw/statcan_grid/; pass --force to re-download).

import os
import sys
import json
import zipfile
import argparse

import requests
import pandas as pd

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

HERE = os.path.dirname(os.path.abspath(__file__))
RAW_DIR = os.path.join(HERE, "..", "data", "raw", "statcan_grid")
OUT_JSON = os.path.join(HERE, "..", "data", "processed", "grid_ef_annual.json")

GHG_PID = 38100097   # Physical flow account for GHG emissions
GEN_PID = 25100015   # Electric power generation, monthly, by type

HTTP_HEADERS = {"User-Agent": "Mozilla/5.0"}

# StatCan GEO string -> province key used by heatpump.html (CITY_PROV values).
GEO_TO_PROV = {
    "Newfoundland and Labrador": "nl",
    "Prince Edward Island": "pe",
    "Nova Scotia": "ns",
    "New Brunswick": "nb",
    "Quebec": "qc",
    "Ontario": "on",
    "Manitoba": "mb",
    "Saskatchewan": "sk",
    "Alberta": "ab",
    "British Columbia": "bc",
}

# Flat marginal-intensity screening estimates (g CO2e/kWh) for provinces with
# NO hourly marginal surface, each with a short rationale. ON/QC/AB are NOT
# here -- they carry a real hourly marginal channel in ef_surface_*.json.
MARGINAL_ESTIMATES = {
    "sk": (750.0, "SaskPower fleet is coal- and gas-heavy; coal or gas CCGT "
                  "is typically the marginal unit serving new winter load."),
    "ns": (800.0, "Nova Scotia's grid still leans on coal/petcoke; the "
                  "marginal unit for new winter load is usually a thermal "
                  "(coal or gas) plant."),
    "nb": (550.0, "New Brunswick's mixed fleet (nuclear/hydro/coal/oil/gas) "
                  "meets incremental winter load mostly from gas/oil "
                  "thermal units."),
    "bc": (None, "Hydro-dominant. Domestic margin is flexible hydro "
                 "(near-zero), but incremental winter demand is frequently "
                 "served by imports or gas (FortisBC/US). Import-margin "
                 "intensity is contested and unmodeled -- marginal is set "
                 "equal to the annual average here, with this caveat "
                 "(same treatment as Quebec in the hourly pipeline)."),
    "mb": (None, "Hydro-dominant (Manitoba Hydro). Domestic margin is hydro "
                 "(near-zero); winter-import margin higher but unmodeled. "
                 "Marginal set equal to the annual average, with this caveat."),
    "nl": (None, "Hydro-dominant (Churchill Falls / Muskrat Falls). Marginal "
                 "set equal to the annual average; thermal (Holyrood) or "
                 "import margin unmodeled."),
    "pe": (None, "Mostly wind plus imports from New Brunswick over the "
                 "Northumberland cables; effective marginal tracks the NB "
                 "import. Marginal set equal to the annual average as a "
                 "screening placeholder."),
}


def download(pid: int, force: bool) -> str:
    """Download a StatCan full-table CSV zip via the WDS endpoint; return the
    local zip path. Cached under RAW_DIR."""
    os.makedirs(RAW_DIR, exist_ok=True)
    dest = os.path.join(RAW_DIR, f"{pid}-eng.zip")
    if os.path.exists(dest) and os.path.getsize(dest) > 0 and not force:
        return dest
    meta = requests.get(
        f"https://www150.statcan.gc.ca/t1/wds/rest/getFullTableDownloadCSV/{pid}/en",
        headers=HTTP_HEADERS, timeout=60,
    ).json()
    if meta.get("status") != "SUCCESS":
        raise RuntimeError(f"WDS refused download URL for {pid}: {meta}")
    url = meta["object"]
    r = requests.get(url, headers=HTTP_HEADERS, timeout=180)
    r.raise_for_status()
    with open(dest, "wb") as fh:
        fh.write(r.content)
    return dest


def read_table(zip_path: str, pid: int) -> pd.DataFrame:
    with zipfile.ZipFile(zip_path) as zf:
        with zf.open(f"{pid}.csv") as fh:
            return pd.read_csv(fh, low_memory=False)


def compute_intensity(force: bool) -> pd.DataFrame:
    ghg = read_table(download(GHG_PID, force), GHG_PID)
    gen = read_table(download(GEN_PID, force), GEN_PID)

    ep = ghg[ghg["Sector"].str.startswith(
        "Electric power generation, transmission and distribution")].copy()
    ep["Year"] = ep["REF_DATE"].astype(int)
    ep = ep[["Year", "GEO", "VALUE"]].rename(columns={"VALUE": "kt"})

    g = gen[(gen["Class of electricity producer"]
             == "Electricity producers, electric utilities")
            & (gen["Type of electricity generation"]
               == "Total all types of electricity generation")].copy()
    g["Year"] = g["REF_DATE"].str[:4].astype(int)
    ga = (g.groupby(["Year", "GEO"], as_index=False)["VALUE"].sum()
          .rename(columns={"VALUE": "gen_MWh"}))

    m = ep.merge(ga, on=["Year", "GEO"])
    m = m[m["gen_MWh"] > 0].copy()
    m["g_per_kWh"] = m["kt"] * 1e6 / m["gen_MWh"]
    return m


def cross_check(m: pd.DataFrame) -> None:
    print("=" * 64)
    print("Cross-check vs known anchors (g CO2e/kWh)")
    print("=" * 64)
    anchors = {
        "Canada": {2022: ("ECCC headline", 100), 2023: ("ECCC/440Mt", 96)},
        "Ontario": {2022: ("TAF AEF", 51), 2023: ("TAF AEF", 67)},
        "Alberta": {2019: ("Alberta.ca Fig7", 630), 2022: ("Alberta.ca Fig7", 510),
                    2023: ("Alberta.ca Fig7", 470)},
    }
    for geo, yrs in anchors.items():
        for y, (src, val) in yrs.items():
            r = m[(m["GEO"] == geo) & (m["Year"] == y)]
            if len(r):
                got = r["g_per_kWh"].iloc[0]
                dev = (got - val) / val * 100
                print(f"  {geo:9s} {y}: computed {got:6.1f}  vs {src:16s} "
                      f"{val:4d}  ({dev:+.0f}%)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="re-download source zips")
    args = ap.parse_args()

    m = compute_intensity(args.force)
    years = sorted(m["Year"].unique())
    latest = int(years[-1])
    print(f"Loaded intensities for {m['GEO'].nunique()} geographies, "
          f"{years[0]}-{years[-1]}")
    cross_check(m)

    provinces = {}
    for geo, prov in GEO_TO_PROV.items():
        sub = m[m["GEO"] == geo].sort_values("Year")
        if sub.empty:
            continue
        avg = {int(r.Year): round(float(r.g_per_kWh), 2) for r in sub.itertuples()}
        latest_avg = avg[max(avg)]
        entry = {"avg_g_per_kWh": avg, "latest_year": max(avg)}
        # marginal
        if prov in ("on", "qc", "ab"):
            entry["marginal_note"] = (
                "This province has an hourly marginal surface "
                "(ef_surface_%s.json); use that for a real marginal basis. "
                "The ECCC yearly-average value here is average-basis only."
                % prov)
        elif prov in MARGINAL_ESTIMATES:
            val, note = MARGINAL_ESTIMATES[prov]
            if val is None:
                entry["marginal_estimate_g_per_kWh"] = latest_avg
                entry["marginal_equals_average"] = True
            else:
                entry["marginal_estimate_g_per_kWh"] = val
            entry["marginal_note"] = note
        provinces[prov] = entry

    payload = {
        "meta": {
            "title": "Published annual-average grid emissions intensity by province",
            "basis": "ECCC/NIR electric-utility emissions over electric-utility generation",
            "unit": "g_CO2e_per_kWh",
            "sources": {
                "ghg_numerator": ("StatCan 38-10-0097, sector 'Electric power "
                                  "generation, transmission and distribution "
                                  "[BS22110]' (ECCC NIR data), kt CO2e"),
                "generation_denominator": ("StatCan 25-10-0015, class "
                                           "'Electricity producers, electric "
                                           "utilities', annual sum, MWh"),
                "fetched_via": "StatCan WDS getFullTableDownloadCSV",
            },
            "formula": "g_per_kWh = kt_CO2e * 1e6 / utility_generation_MWh",
            "national_validation": ("Canada computes to ~101 g/kWh (2022) vs "
                                    "ECCC's published headline 100 g/kWh."),
            "scope_caveats": (
                "ON runs ~10-20% below TAF's Annual AEF (TAF attributes all "
                "grid emissions to gas). AB runs ~20% below Alberta.ca Fig.7 "
                "(cogeneration emission allocation). These are scope "
                "differences, documented in METHODOLOGY.md, not errors. This "
                "annual basis is DISTINCT from the tool's hourly EF surface."),
            "year_range": [int(years[0]), latest],
            "provinces_with_hourly_surface": ["on", "qc", "ab"],
        },
        "provinces": provinces,
    }

    os.makedirs(os.path.dirname(OUT_JSON), exist_ok=True)
    with open(OUT_JSON, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=None, separators=(",", ":"))

    print(f"\n[ok] {len(provinces)} provinces, {years[0]}-{latest} -> {OUT_JSON}")
    print("Latest-year averages (g/kWh):")
    for prov, e in sorted(provinces.items()):
        marg = e.get("marginal_estimate_g_per_kWh", "hourly")
        print(f"  {prov}: {e['avg_g_per_kWh'][e['latest_year']]:6.1f} "
              f"({e['latest_year']})   marginal={marg}")


if __name__ == "__main__":
    main()
