"""
build_hp_equipment_insights.py

Offline precompute for two heat-pump equipment panels on the Retrofit Insights
page (retrofit-insights.html, section after "The geography of heat pumps"):
  1. the AHRI cold-climate scatter (COP @ 5 F vs capacity maintenance)
  2. the US DOE Cold Climate Heat Pump (CCHP) Technology Challenge screen

Both panels consume the SAME two Phase-3c interim CSVs already used by
HeatPump/pipeline/build_tier_scatter.py and HeatPump/pipeline/screen_cchp.py.
This script does not recompute the screen or the scatter geometry — it reads
their outputs and repackages them as compact JSON for a browser fetch.

INPUTS (all local, gitignored — see the reproducibility-gap note below)
  HeatPump/data/interim/hp_units_joined.csv   one row per AHRI-certified unit
        k    AHRI reference number
        w    ERS appearances (occurrences in the retrofit data)
        cm   capacity maintenance = max cap @5F / rated cap @47F
        cop  COP @ 5 F, max-compressor-speed
        c47  rated capacity @ 47 F, BTU/h
  HeatPump/data/interim/hp_buckets.csv        brand / model, joined on k
  HeatPump/data/interim/cchp_screen.csv       every model's per-criterion
        DOE CCHP Challenge screen result (built by screen_cchp.py)
  HeatPump/data/interim/cchp_qualifying.csv   the screen_pass subset

  NOTE (reproducibility gap, carried from HeatPump/METHODOLOGY.md):
  hp_units_joined.csv has no producer script in this repo. It is consumed
  here as given, same as build_tier_scatter.py and screen_cchp.py do.

OUTPUTS  insights_json/ (compact, ensure_ascii=False, separators=(',',':'))
  hp_ahri_scatter.json   scatter points + size bands + gate counts, for a
                         bespoke inline-SVG scatter (ported from
                         tier-scatter.html's circle/legend/tooltip pattern)
  cchp_screen.json       verdict tally, checkable/not-checkable criteria
                         table, the qualifying rows, and the three basis
                         caveats — all counts computed from the CSVs

HONESTY RAILS
  - Wording on the page must say "screened against the DOE Challenge
    specifications", never "meets"/"certified"/"qualifies for" the Challenge.
    The passing verdict value is screen_pass.
  - Only ~4 of 8 Table II-3 criteria are checkable from published AHRI/
    ENERGY STAR ratings (COP @ 5F, capacity ratio, HSPF2 floor, refrigerant
    GWP). The uncheckable ones are carried through into cchp_screen.json as
    explicit "not_checkable" entries, not dropped.
  - Distinct-model count is smaller than qualifying-row count: one physical
    unit (GREE GUD60W2/NHE-D(U)) is AHRI-certified under two reference
    numbers, so the same model contributes two rows.

Usage:
    python Python/build_hp_equipment_insights.py
"""

import csv
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
INTERIM = REPO_ROOT / "HeatPump" / "data" / "interim"
OUT_DIR = REPO_ROOT / "insights_json"

UNITS = INTERIM / "hp_units_joined.csv"
BUCKETS = INTERIM / "hp_buckets.csv"
CCHP_FULL = INTERIM / "cchp_screen.csv"
CCHP_QUALIFY = INTERIM / "cchp_qualifying.csv"

# Same nominal size bands as build_tier_scatter.py, BTU/h @47F.
SIZE_BANDS = [
    ("<18k  (~1.5 ton)", 0, 18000, "#4C9BE8"),
    ("18-24k (~2 ton)", 18000, 24000, "#5BA383"),
    ("24-30k (~2.5 ton)", 24000, 30000, "#E8B94C"),
    ("30-36k (~3 ton)", 30000, 36000, "#E8834C"),
    ("36-48k (~3.5-4 ton)", 36000, 48000, "#C4574C"),
    (">=48k  (5 ton+)", 48000, 10**9, "#7A5AA8"),
]


def band_of(c47):
    for i, (_lab, lo, hi, _col) in enumerate(SIZE_BANDS):
        if lo <= c47 < hi:
            return i
    return len(SIZE_BANDS) - 1


def num(value):
    if value is None or value == "":
        return None
    try:
        return float(value)
    except ValueError:
        return None


def read_csv(path):
    with path.open(encoding="utf-8", errors="replace", newline="") as fh:
        return list(csv.DictReader(fh))


def write(name, obj):
    path = OUT_DIR / name
    with path.open("w", encoding="utf-8") as fh:
        json.dump(obj, fh, ensure_ascii=False, separators=(",", ":"))
    print(f"  wrote {path.relative_to(REPO_ROOT)} ({path.stat().st_size / 1024:.1f} KB)")


# =============================================================================
# 1. AHRI cold-climate scatter
# =============================================================================

def build_scatter():
    units = read_csv(UNITS)
    total_units = len(units)
    total_app = sum(int(num(r["w"]) or 0) for r in units)

    miss = {"cm": 0, "cop": 0, "c47": 0}
    names = {}
    for r in read_csv(BUCKETS):
        k = r.get("k", "").strip()
        if k and k not in names:
            names[k] = (r.get("brand") or "", r.get("model") or "")

    pts = []
    kept_app = 0
    for r in units:
        cm, cop, c47 = num(r["cm"]), num(r["cop"]), num(r["c47"])
        if cm is None:
            miss["cm"] += 1
        if cop is None:
            miss["cop"] += 1
        if c47 is None:
            miss["c47"] += 1
        if cm is None or cop is None or c47 is None:
            continue
        w = int(num(r["w"]) or 0)
        kept_app += w
        brand, model = names.get(r["k"].strip(), ("", ""))
        name = " ".join(x for x in (brand, model) if x) or f"AHRI {r['k'].strip()}"
        pts.append({
            "k": int(r["k"]), "n": name, "w": w,
            "cm": round(cm, 3), "cop": round(cop, 2), "c47": int(c47),
            "b": band_of(c47),
        })
    pts.sort(key=lambda p: -p["w"])
    kept_units = len(pts)

    band_stats = []
    for i, (lab, _lo, _hi, col) in enumerate(SIZE_BANDS):
        sub = [p for p in pts if p["b"] == i]
        app = sum(p["w"] for p in sub)
        band_stats.append({
            "label": lab, "colour": col, "units": len(sub), "app": app,
            "pct": round(100 * app / kept_app, 1) if kept_app else 0.0,
        })

    meta = {
        "total_units": total_units, "total_app": total_app,
        "kept_units": kept_units, "kept_app": kept_app,
        "app_pct": round(100 * kept_app / total_app, 1) if total_app else 0.0,
        "missing": miss,
    }

    write("hp_ahri_scatter.json", {"pts": pts, "bands": band_stats, "meta": meta})


# =============================================================================
# 2. CCHP Challenge screen
# =============================================================================

CHECKABLE = [
    {"key": "check_capacity_ratio", "label": "Capacity ratio at 5 °F ≥ 100%",
     "basis_key": "ratio_basis"},
    {"key": "check_cop_5f", "label": "COP at 5 °F ≥ 2.4 / 2.1 by capacity band",
     "basis_key": "band_basis"},
    {"key": "check_hspf2_floor", "label": "HSPF2 ≥ 8.5 (floor test only)",
     "basis_key": None},
    {"key": "check_gwp", "label": "Refrigerant GWP ≤ 750 (AR4, 100-year)",
     "basis_key": None},
]

NOT_CHECKABLE = [
    {"key": "turndown_ratio", "label": "Minimum turndown ratio ≥ 30%",
     "reason": "needs minimum capacity; not published in AHRI certificates"},
    {"key": "compressor_cutout_cutin", "label": "Compressor cut-out / cut-in at 5 °F and −15 °F",
     "reason": "not in AHRI or ENERGY STAR; manufacturer datasheets give a lock-out temperature only"},
    {"key": "electric_heat_staging", "label": "Electric heat staging (Table II-1)",
     "reason": "not published in any dataset we hold"},
    {"key": "energystar_cachp_sections", "label": "ENERGY STAR CACHP §3C/4B/4C/4D",
     "reason": "partially proxied by the ENERGY STAR cold-climate flag, not evaluated"},
]

VERDICT_ORDER = ["screen_pass", "near", "fail", "out_of_scope", "unknown"]


def build_cchp():
    full = read_csv(CCHP_FULL)
    qualifying = read_csv(CCHP_QUALIFY)

    total_models = len(full)
    total_app = sum(int(r["ers_appearances"]) for r in full)

    tally = []
    for v in VERDICT_ORDER:
        rows = [r for r in full if r["verdict"] == v]
        app = sum(int(r["ers_appearances"]) for r in rows)
        tally.append({
            "verdict": v, "models": len(rows), "appearances": app,
            "pct": round(100 * app / total_app, 2) if total_app else 0.0,
        })

    qualifying_out = [{
        "ahri_number": r["ahri_number"], "brand": r["brand"], "model": r["model"],
        "ers_appearances": int(r["ers_appearances"]),
        "capacity_band": r["capacity_band"], "cap_47f_btuh": r["cap_47f_btuh"],
        "cop_5f": r["cop_5f"], "cop_threshold": r["cop_threshold"],
        "capacity_ratio": r["capacity_ratio"],
        "hspf2_region_iv": r["hspf2_region_iv"], "refrigerant": r["refrigerant"],
        "gwp_ar4_100yr": r["gwp_ar4_100yr"],
    } for r in sorted(qualifying, key=lambda r: -int(r["ers_appearances"]))]

    qualifying_appearances = sum(r["ers_appearances"] for r in qualifying_out)
    distinct_models = len({(r["brand"], r["model"]) for r in qualifying_out})

    # per-criterion basis text, pulled straight from the CSV so it can't drift
    # from screen_cchp.py's own strings
    basis = {}
    if full:
        basis["band_basis"] = full[0]["band_basis"]
        basis["ratio_basis"] = full[0]["ratio_basis"]
        basis["hspf2_floor_only"] = full[0]["hspf2_floor_only"] == "True"

    out_of_scope = next(t for t in tally if t["verdict"] == "out_of_scope")

    meta = {
        "total_models": total_models,
        "total_appearances": total_app,
        "qualifying_rows": len(qualifying_out),
        "qualifying_models": distinct_models,
        "qualifying_appearances": qualifying_appearances,
        "qualifying_appearances_pct": round(100 * qualifying_appearances / total_app, 4) if total_app else 0.0,
        "out_of_scope_pct": out_of_scope["pct"],
        "spec_url": full[0]["spec_source"] if full else "",
    }

    write("cchp_screen.json", {
        "tally": tally,
        "qualifying": qualifying_out,
        "checkable": CHECKABLE,
        "not_checkable": NOT_CHECKABLE,
        "basis": basis,
        "meta": meta,
    })


def main():
    OUT_DIR.mkdir(exist_ok=True)
    print("build_hp_equipment_insights.py")
    build_scatter()
    build_cchp()


if __name__ == "__main__":
    main()
