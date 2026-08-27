"""
ewrb_etl.py

Ontario's Energy and Water Reporting and Benchmarking (EWRB) disclosure —
building-level energy intensity for every Ontario building over 100,000 sq ft —
aggregated into construction_json/ewrb.json.

WHY THIS IS ON A CONSTRUCTION PAGE
    Everything else on the page counts buildings or prices them. This is the
    only source in the suite that says how the existing large-building stock
    actually performs, and roughly half of it is multifamily housing — the MURB
    stock the Retrofit Explorer and Heat Pump Explorer model from the other
    direction. It is Ontario-only, so the card only appears on Ontario and
    Toronto views.

WHAT THE PUBLISHER SAYS ABOUT ITS OWN DATA
    Ontario states plainly that the data is "not cleansed" and is "reported by
    building owners or their agents", so it may contain errors. That is not a
    footnote here: the gates below are explicit, counted, and reported into the
    output so the page can show what was dropped and why.

    Data_Qual_Check records whether the reporter RAN Portfolio Manager's Data
    Quality Checker — not whether the data passed anything. It is carried
    through as a coverage statistic, never used as a filter, because "ran a
    tool" is not a quality guarantee and filtering on it would silently halve
    the sample on a self-declared flag.

UNITS (confirmed against the published data dictionary, 2026-08-27)
    WN_Site_EUI1   weather-normalized site energy use intensity, GJ/m2
    Site_EUI1      site energy use intensity, GJ/m2, NOT weather-normalized
    GHG_Emiss_Int1 GHG emissions intensity, kgCO2e/m2
    The *2 / *3 siblings are the same figures in imperial units and are ignored.

SOURCE
    data.ontario.ca dataset `energy-and-water-usage-of-large-buildings-in-ontario`
    Open Government Licence - Ontario. One XLSX per year, English and French
    copies of each; the French ones are skipped by URL.

USAGE
    python ewrb_etl.py [--refresh]
Exits non-zero on any fetch failure (safe for the scheduled refresh).
"""

import io
import sys
import json
import argparse
from pathlib import Path
from datetime import datetime
from collections import defaultdict

import requests
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
CACHE_DIR = REPO_ROOT / "Python" / "ewrb_cache"
OUTPUT_DIR = REPO_ROOT / "construction_json"
PACKAGE = ("https://data.ontario.ca/api/3/action/package_show"
           "?id=energy-and-water-usage-of-large-buildings-in-ontario")
HEADERS = {"User-Agent": "OttawaVisuals-EnergySuite/1.0 (construction tracker)"}

# Plausibility gate. 20 GJ/m2 is about 5,600 kWh/m2 — an order of magnitude
# beyond any real building, so anything above it is a reporting error, not a
# very inefficient building. Deliberately loose: the job is to remove
# impossibilities, not to quietly tidy the distribution.
EUI_MAX = 20.0
MIN_N = 20          # suppress a property type thinner than this in a given year


def fetch_resources(refresh=False):
    """Return {year: local xlsx path} for the English files only."""
    meta = requests.get(PACKAGE, headers=HEADERS, timeout=120).json()["result"]
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    out = {}
    for r in meta["resources"]:
        name = (r.get("name") or "").strip()
        url = r.get("url") or ""
        if not name.isdigit() or r.get("format") != "XLSX":
            continue                                  # skip the dictionaries
        if "energie_eau" in url:
            continue                                  # skip the French copies
        year = int(name)
        path = CACHE_DIR / f"ewrb_{year}.xlsx"
        if refresh or not path.exists() or path.stat().st_size == 0:
            print(f"  downloading {year}...", flush=True)
            resp = requests.get(url, headers=HEADERS, timeout=600)
            resp.raise_for_status()
            path.write_bytes(resp.content)
        out[year] = path
    return dict(sorted(out.items()))


def quantiles(vals):
    s = pd.Series(vals)
    return {"n": int(s.size),
            "p25": round(float(s.quantile(.25)), 3),
            "median": round(float(s.median()), 3),
            "p75": round(float(s.quantile(.75)), 3)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true")
    args = ap.parse_args()

    try:
        files = fetch_resources(args.refresh)
    except Exception as e:
        print(f"\n!! could not list EWRB resources: {e}", file=sys.stderr)
        sys.exit(1)
    if not files:
        print("\n!! no EWRB year files found", file=sys.stderr)
        sys.exit(1)

    by_year = {}
    drops = defaultdict(int)
    totals = defaultdict(int)

    for year, path in files.items():
        try:
            df = pd.read_excel(path)
        except Exception as e:
            print(f"\n!! could not read {path.name}: {e}", file=sys.stderr)
            sys.exit(1)

        rows = len(df)
        totals["rows"] += rows
        eui = pd.to_numeric(df.get("WN_Site_EUI1"), errors="coerce")
        ghg = pd.to_numeric(df.get("GHG_Emiss_Int1"), errors="coerce")
        ptype = df.get("PrimPropTypCalc").astype(str).str.strip()

        missing = int(eui.isna().sum())
        nonpos = int((eui <= 0).sum())
        extreme = int((eui > EUI_MAX).sum())
        drops["missing_eui"] += missing
        drops["non_positive_eui"] += nonpos
        drops["above_plausibility_gate"] += extreme

        ran_checker = df.get("Data_Qual_Check")
        ran = int((ran_checker.astype(str).str.strip().str.lower() == "yes").sum()) \
            if ran_checker is not None else 0

        keep = eui.notna() & (eui > 0) & (eui <= EUI_MAX)
        totals["kept"] += int(keep.sum())

        types = {}
        for t, idx in ptype[keep].groupby(ptype[keep]).groups.items():
            vals = eui.loc[idx]
            if len(vals) < MIN_N:
                drops["suppressed_small_n_rows"] += len(vals)
                continue
            entry = quantiles(vals)
            g = ghg.loc[idx].dropna()
            entry["ghg_median"] = round(float(g.median()), 1) if len(g) else None
            types[t] = entry

        by_year[str(year)] = {
            "rows": rows,
            "kept": int(keep.sum()),
            "ran_quality_checker": ran,
            "all": quantiles(eui[keep]) if keep.any() else None,
            "types": dict(sorted(types.items(),
                                 key=lambda kv: -kv[1]["n"])[:14]),
        }
        print(f"  {year}: {rows:,} rows -> {int(keep.sum()):,} usable "
              f"({missing:,} no EUI, {nonpos:,} non-positive, {extreme:,} above "
              f"{EUI_MAX} GJ/m2), {ran:,} ran the quality checker")

    payload = {
        "retrieved": datetime.now().strftime("%Y-%m-%d"),
        "source": "Ontario Energy and Water Reporting and Benchmarking (EWRB)",
        "source_url": ("https://data.ontario.ca/dataset/"
                       "energy-and-water-usage-of-large-buildings-in-ontario"),
        "licence": "Open Government Licence - Ontario",
        "scope": ("Ontario buildings over 100,000 sq ft: commercial, "
                  "multifamily, warehousing and light industrial. Manufacturing, "
                  "heavy industrial and agricultural buildings are excluded by "
                  "the regulation."),
        "metric": "Weather-normalized site energy use intensity, GJ/m2",
        "gates": {
            "plausibility_max_gj_m2": EUI_MAX,
            "min_rows_per_type": MIN_N,
            "note": ("Ontario publishes this data uncleansed and self-reported. "
                     "Rows are dropped only for a missing, zero/negative or "
                     "impossible intensity, and property types thinner than "
                     f"{MIN_N} rows in a year are suppressed rather than shown. "
                     "Every count is in `drops`. The Data Quality Checker flag "
                     "is reported, never used as a filter — it records whether "
                     "the reporter ran a tool, not whether the data passed."),
        },
        "drops": dict(drops),
        "totals": dict(totals),
        "years": by_year,
    }
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUTPUT_DIR / "ewrb.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))
    pct = drops["missing_eui"] / totals["rows"] * 100 if totals["rows"] else 0
    print(f"\nwrote {out.name} ({out.stat().st_size/1024:.1f} KB, "
          f"{len(by_year)} years, {totals['kept']:,} of {totals['rows']:,} rows "
          f"usable; {pct:.1f}% had no weather-normalized intensity)")


if __name__ == "__main__":
    main()
