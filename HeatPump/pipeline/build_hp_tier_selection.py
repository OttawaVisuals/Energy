"""
Consolidated JSON for heatpump.html's live "Heat-pump selection: the
underlying data" section (scatter + tier-cell curves + spec table).

WHY THIS EXISTS
---------------
build_tier_scatter.py's own output (tier_scatter.html) is a temporary working
document -- ~1MB of inline SVG/script, not meant to ship on the live tool.
heatpump.html needs the same underlying data (which 9 units were picked, why,
and how their curves compare to the AHRI certificate and NEEP) but as compact
JSON it can lazy-fetch only when a user actually expands that section, and
render with Chart.js (already loaded on the page) instead of raw SVG.

INPUTS
------
  Reuses, rather than re-derives, everything from the three working scripts:
    build_tier_scatter.py   SIZE_BANDS, weighted_quantile, plot bounds, the
                             9-unit AHRI selection set
    build_cell_curves.py    UNITS (digitized datasheet points), build_segments
    build_tier_curves.py    COLOURS, build_table_data() (AHRI/NEEP/calculated
                             spec table)

OUTPUT
------
  data/processed/hp_tier_selection.json
    scatter: { pts[] (raw cm/cop/w/band/ahri, NOT pixel-projected -- Chart.js
                       does its own scaling), bands[], cop_terciles,
                       cm_terciles, bounds, gate }
    curves:  { uid -> { brand_model, ahri, w, rank, source, flags, colour,
                          lockout_C, rated_cap_47f_btuh,
                          cap_segments[[t0,v0,t1,v1,solid]...],
                          cop_segments[...], cap_points[[t,v]...],
                          cop_points[...] } }
    table:   { uid -> rows[] }   (build_tier_curves.build_table_data() as-is)
"""
import json
from pathlib import Path

import pandas as pd

from build_tier_scatter import SIZE_BANDS, SELECTED_AHRI, X_MIN, X_MAX, Y_MIN, Y_MAX, weighted_quantile
from build_cell_curves import UNITS, build_segments
from build_tier_curves import COLOURS, build_table_data

HERE = Path(__file__).resolve().parent
INTERIM = HERE.parent / "data" / "interim"
OUT = HERE.parent / "data" / "processed" / "hp_tier_selection.json"


def build_scatter():
    df = pd.read_csv(INTERIM / "hp_units_joined.csv")
    total_units = len(df)
    total_app = int(df["w"].sum())
    miss = {
        "capacity maintenance (cm)": int(df["cm"].isna().sum()),
        "COP @ 5 F (cop)": int(df["cop"].isna().sum()),
        "rated capacity @47 F (c47)": int(df["c47"].isna().sum()),
    }
    d = df.dropna(subset=["cm", "cop", "c47"]).copy()
    kept_units, kept_app = len(d), int(d["w"].sum())

    try:
        b = pd.read_csv(INTERIM / "hp_buckets.csv")[["k", "brand", "model"]].drop_duplicates("k")
        d = d.merge(b, on="k", how="left")
    except Exception:
        d["brand"], d["model"] = None, None

    def band_of(c47):
        for i, (_lab, lo, hi, _col) in enumerate(SIZE_BANDS):
            if lo <= c47 < hi:
                return i
        return len(SIZE_BANDS) - 1

    d["band"] = d["c47"].apply(band_of)
    cop_t = [weighted_quantile(d["cop"], d["w"], q) for q in (1 / 3, 2 / 3)]
    cm_t = [weighted_quantile(d["cm"], d["w"], q) for q in (1 / 3, 2 / 3)]

    pts = []
    for r in d.itertuples():
        name = " ".join(str(x) for x in (r.brand, r.model) if isinstance(x, str))
        pts.append({
            "cm": round(float(r.cm), 3), "cop": round(float(r.cop), 2),
            "w": int(r.w), "b": int(r.band), "c47": int(r.c47),
            "k": int(r.k), "n": name or f"AHRI {int(r.k)}",
            "sel": 1 if int(r.k) in SELECTED_AHRI else 0,
        })

    band_stats = []
    for i, (lab, _lo, _hi, col) in enumerate(SIZE_BANDS):
        sub = d[d["band"] == i]
        band_stats.append({
            "label": lab, "colour": col, "units": int(len(sub)),
            "app": int(sub["w"].sum()),
            "pct": round(100 * sub["w"].sum() / kept_app, 1) if kept_app else 0.0,
        })

    return {
        "pts": pts,
        "bands": band_stats,
        "cop_terciles": [round(v, 2) for v in cop_t],
        "cm_terciles": [round(v, 3) for v in cm_t],
        "bounds": {"x_min": X_MIN, "x_max": X_MAX, "y_min": Y_MIN, "y_max": Y_MAX},
        "gate": {
            "total_units": total_units, "total_app": total_app,
            "kept_units": kept_units, "kept_app": kept_app,
            "app_pct": round(100 * kept_app / total_app, 1),
            "missing": miss,
        },
    }


def build_curves():
    out = {}
    for uid, u in UNITS.items():
        cap_segs = build_segments(u["cap_points"], u["lockout_C"], is_cop=False)
        cop_segs = build_segments(u["cop_points"], u["lockout_C"], is_cop=True)
        out[uid] = {
            "brand_model": u["brand_model"], "ahri": u["ahri"], "w": u["w"],
            "rank": u["rank"], "source": u["source"], "flags": u["flags"],
            "colour": COLOURS[uid], "lockout_C": u["lockout_C"],
            "cap_segments": [[round(v, 3) if isinstance(v, float) else v for v in s] for s in cap_segs],
            "cop_segments": [[round(v, 3) if isinstance(v, float) else v for v in s] for s in cop_segs],
            "cap_points": [[t, v] for t, v in u["cap_points"]],
            "cop_points": [[t, v] for t, v in u["cop_points"]],
        }
    return out


def main():
    data = {
        "meta": {
            "generated_from": "build_hp_tier_selection.py, reusing "
                              "build_tier_scatter.py / build_cell_curves.py / "
                              "build_tier_curves.py -- see those for method.",
        },
        "scatter": build_scatter(),
        "curves": build_curves(),
        "table": build_table_data(),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(data, separators=(",", ":")), encoding="utf-8")
    kb = OUT.stat().st_size / 1024
    print(f"wrote {OUT} ({kb:.0f} KB)")
    print(f"  scatter: {len(data['scatter']['pts']):,} points")
    print(f"  curves: {len(data['curves'])} units")
    print(f"  table: {sum(len(v) for v in data['table'].values()):,} rows total")


if __name__ == "__main__":
    main()
