"""
build_nhpr_eligible.py -- National Heat Pump Rebate (NHPR) eligible products,
joined to ENERGY STAR ratings by AHRI number.

WHY
---
The federal National Heat Pump Rebate (ECCC, program page dated 2026-11-05)
pays by product: a heat pump qualifies if its AHRI number is on NRCan's
eligible list. That list has model names but no ratings. ENERGY STAR's open
dataset republishes the AHRI-certified ratings (capacity at 47/17/5 F, COP at
5 F, HSPF2, SEER2) for the models it certifies, keyed on the same AHRI number.
Joining the two gives rating distributions for the part of the eligible list
that ENERGY STAR also certifies. (AHRI's own directory is not used: its terms
bar reuse of public-site data and it now blocks automated access.)

INPUTS
------
  data/raw/nrcan/nhpr_eligible_products_2026-11-10.csv
      NRCan Search Product List, filter HP_NHPR, "Download all (CSV)", saved
      2026-11-10. No header row. Columns: 0 outside model, 1 brand,
      2 inside model, 3 furnace model, 4 AHRI number, 5 product group
      (ccASHP / GSHP), 6 system type, 7 status (Active / Archived).
      One row per model combination, so ~179,620 rows for ~178,954 AHRI
      numbers. Gitignored.
  data/raw/energystar/es_heat_pumps_2026-11-10.csv
      ENERGY STAR Certified Air-Source Heat Pumps (Socrata w7cv-9xjt), CSV
      export, saved 2026-11-10. Gitignored.

OUTPUTS (data/interim/, gitignored)
-------
  nhpr_eligible_joined.csv    one row per eligible AHRI number: list fields +
                              `in_es` flag + ENERGY STAR ratings where matched.
  nhpr_eligible_summary.json  counts, match rates, distributions. Everything a
                              page would need; nothing else is read at load.
  ../newheatpumps_json/scatter.json   one row per distinct (capacity at 47 F,
                              capacity maintenance, COP at 5 F, compressor type)
                              with how many Active / all AHRI numbers share it.
  ../newheatpumps_json/summary.json   the same summary, published to the site
                              (newheatpumps.html reads it; gitignored on main,
                              shipped via deploy.sh like every generated tree).

HONESTY GATES (nothing is dropped silently)
-------------------------------------------
  * Rows with a blank AHRI number are counted and reported, not joined.
  * Several list rows per AHRI number are collapsed to one (first row); the
    number of AHRI numbers whose rows disagree on brand/group/status is reported.
  * Several ENERGY STAR rows per AHRI number are collapsed to one; the number
    whose 5 F capacity or COP disagrees across rows is reported.
  * Eligible AHRI numbers with no ENERGY STAR match stay in the table with
    in_es=False. Ratings are only ever shown for matched rows.
  * Ratings that are blank or non-numeric are counted as missing per field.
  * Ground-source (GSHP) products are not in the air-source ENERGY STAR
    dataset; they are reported as out of scope, not as failed matches.

LIMITS
------
  * ENERGY STAR lists certified products only, so matched rows are the
    ENERGY STAR-certified subset of the eligible list, not all of it.
  * ENERGY STAR republishes AHRI certification values; it is not an
    independent measurement.
  * The NRCan list was downloaded once (2026-11-10); the rebate parameters
    were still being finalized when the program page was dated.

Usage:  python HeatPump/pipeline/build_nhpr_eligible.py
"""
import csv
import json
import re
from collections import Counter
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
NRCAN_CSV = ROOT / "data/raw/nrcan/nhpr_eligible_products_2026-11-10.csv"
ES_CSV = ROOT / "data/raw/energystar/es_heat_pumps_2026-11-10.csv"
OUT_CSV = ROOT / "data/interim/nhpr_eligible_joined.csv"
OUT_JSON = ROOT / "data/interim/nhpr_eligible_summary.json"
PUB_JSON = ROOT.parent / "newheatpumps_json/summary.json"
PUB_SCATTER = ROOT.parent / "newheatpumps_json/scatter.json"
CM_MAX = 1.30     # same screen as METHODOLOGY.md "Implausible ratings": flagged, counted, not plotted
COP_MAX = 3.0

ES_COLS = {
    "AHRI Reference Number": "ahri",
    "Outdoor Unit Brand Name": "es_brand",
    "Cold Climate": "es_cold_climate",
    "Compressor Staging": "es_staging",
    "Markets": "es_markets",
    "SEER2 (Btu/Wh)": "seer2",
    "HSPF2 (Btu/Wh)": "hspf2",
    "Heating Capacity at 47°F (Btu/h)": "cap47",
    "Heating Capacity at 17°F (Btu/h)": "cap17",
    "Heating Capacity at 5°F (Btu/h)": "cap5",
    "COP at 5°F": "cop5",
}
NUM = ["seer2", "hspf2", "cap47", "cap17", "cap5", "cop5"]

# Fixed bins, open-ended at both ends (revised 2026-11-10: finer buckets).
# Capacity 3,000 BTU/h steps; COP at 5 F in 0.1 steps (certified floor is 1.75,
# and 8.7% of Active matched units sit at exactly 1.80, the lowest-reported
# value, which the 0.1 bins make visible); HSPF2 in 0.5 steps (values are
# reported at whole/half numbers, so 0.25 steps leave alternating empty bars).
def _mk(edges, fmt, lo_label, hi_label):
    labels = [lo_label] + [fmt(a, b) for a, b in zip(edges[:-1], edges[1:])] + [hi_label]
    return [-1e9] + edges + [1e9], labels

_cap_e = list(range(9000, 63001, 3000))
_cop_e = [round(1.7 + 0.1 * i, 1) for i in range(0, 9)]          # 1.7 .. 2.5
_hsp_e = [round(8.0 + 0.5 * i, 1) for i in range(0, 9)]           # 8.0 .. 12.0
BINS = {
    "cap47": _mk(_cap_e, lambda a, b: f"{a//1000}-{b//1000}k", "<9k", "63k+"),
    "cop5": _mk(_cop_e, lambda a, b: f"{a:.1f}", "<1.7", "2.5+"),   # "1.7" = 1.7 up to under 1.8
    "hspf2": _mk(_hsp_e, lambda a, b: f"{a:g}", "<8", "12+"),
}


def norm_id(x):
    return re.sub(r"\.0+$", "", str(x).strip())


def load_nrcan():
    with open(NRCAN_CSV, encoding="utf-8-sig", newline="") as f:
        raw = [r for r in csv.reader(f) if r and any(c.strip() for c in r)]
    rows = [r for r in raw if len(r) >= 8]
    short = len(raw) - len(rows)
    df = pd.DataFrame(rows, columns=["outside_model", "brand", "inside_model",
                                     "furnace_model", "ahri", "product_group",
                                     "system_type", "status"][:8])
    df["ahri"] = df["ahri"].map(norm_id)
    blank = int((df["ahri"] == "").sum())
    df = df[df["ahri"] != ""]
    n_rows = len(df)
    # Collapse to one row per AHRI number; count disagreements.
    g = df.groupby("ahri")
    conflict = {c: int((g[c].nunique() > 1).sum()) for c in ["brand", "product_group", "status"]}
    one = g.agg(brand=("brand", "first"), product_group=("product_group", "first"),
                system_type=("system_type", "first"), status=("status", "first"),
                outside_model=("outside_model", "first"),
                n_list_rows=("ahri", "size")).reset_index()
    gates = {"list_rows_with_unexpected_shape": short, "list_rows_blank_ahri": blank,
             "list_rows_used": n_rows, "distinct_ahri": len(one),
             "ahri_with_conflicting_fields_across_rows": conflict}
    return one, gates


def load_es():
    df = pd.read_csv(ES_CSV, usecols=list(ES_COLS), dtype=str).rename(columns=ES_COLS)
    n_raw = len(df)
    df["ahri"] = df["ahri"].fillna("").map(norm_id)
    blank = int((df["ahri"] == "").sum())
    df = df[df["ahri"] != ""].copy()
    for c in NUM:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    g = df.groupby("ahri")
    conflict = {c: int((g[c].nunique(dropna=True) > 1).sum()) for c in ["cap5", "cop5"]}
    rank = {"Continuously variable": 0, "Two-stage": 1, "Single stage": 2}
    df["_r"] = df["es_staging"].map(rank).fillna(9)
    one = df.sort_values("_r").drop_duplicates("ahri").drop(columns="_r")
    gates = {"es_rows": n_raw, "es_rows_blank_ahri": blank, "es_distinct_ahri": len(one),
             "es_ahri_with_conflicting_5F_values": conflict}
    return one, gates


def hist(series, key):
    edges, labels = BINS[key]
    s = pd.cut(series.dropna(), bins=edges, labels=labels, right=False)
    c = s.value_counts().reindex(labels).fillna(0).astype(int)
    return {"labels": labels, "counts": c.tolist(), "n": int(c.sum())}


def dist_block(df):
    out = {"n_units": len(df)}
    for k in BINS:
        out[k] = hist(df[k], k)
    out["missing"] = {k: int(df[k].isna().sum()) for k in ["cap47", "cop5", "hspf2"]}
    out["median"] = {k: (None if df[k].dropna().empty else round(float(df[k].median()), 2))
                     for k in ["cap47", "cop5", "hspf2"]}
    out["compressor_staging"] = df["es_staging"].fillna("blank").value_counts().to_dict()
    out["cold_climate"] = df["es_cold_climate"].fillna("blank").value_counts().to_dict()
    out["top_brands"] = df["brand"].value_counts().head(15).to_dict()
    return out


def main():
    nr, g1 = load_nrcan()
    es, g2 = load_es()
    m = nr.merge(es, on="ahri", how="left", indicator=True)
    m["in_es"] = m["_merge"] == "both"
    m = m.drop(columns="_merge")
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    m.to_csv(OUT_CSV, index=False, encoding="utf-8")

    air = m[m["product_group"] == "ccASHP"]
    summary = {
        "built_from": {"nrcan_list": NRCAN_CSV.name, "energystar": ES_CSV.name},
        "gates": {**g1, **g2},
        "eligible_distinct_ahri": len(m),
        "by_product_group": m["product_group"].value_counts().to_dict(),
        "by_status": m["status"].value_counts().to_dict(),
        "by_system_type": m["system_type"].value_counts().to_dict(),
        "match": {},
    }
    for label, sub in [("air_source_all", air),
                       ("air_source_active", air[air["status"] == "Active"]),
                       ("air_source_archived", air[air["status"] == "Archived"])]:
        summary["match"][label] = {"n": len(sub), "in_es": int(sub["in_es"].sum()),
                                   "pct": round(100 * sub["in_es"].mean(), 1) if len(sub) else None}
    summary["ground_source_out_of_scope"] = int((m["product_group"] == "GSHP").sum())

    matched = air[air["in_es"]].copy()
    summary["dist_matched_air_source"] = dist_block(matched)
    summary["dist_matched_active"] = dist_block(matched[matched["status"] == "Active"])
    # Comparison: all ENERGY STAR units sold in Canada, matched or not.
    es_ca = es[es["es_markets"].fillna("").str.contains("Canada")].rename(columns={"es_brand": "brand"})
    summary["dist_all_es_canada_market"] = dist_block(es_ca)
    # ES units that are NOT on the eligible list (the rebate list is narrower or older).
    summary["es_canada_units_not_on_list"] = int((~es_ca["ahri"].isin(set(nr["ahri"]))).sum())
    # Brand view: distinct OUTDOOR MODELS per brand (Active air-source), not AHRI
    # numbers. One outdoor model pairs with many indoor units, so AHRI-number
    # counts mostly measure how many pairings a maker certified. Rebadged brands
    # (same outdoor model sold under several names) still each count it once.
    act_air = air[air["status"] == "Active"].copy()
    act_air["brand_u"] = act_air["brand"].str.strip().str.upper()
    bm = act_air.groupby("brand_u")["outside_model"].nunique().sort_values(ascending=False)
    summary["brands_active_air_source"] = {
        "distinct_brands": int(len(bm)),
        "top_by_outdoor_models": {k: int(v) for k, v in bm.head(15).items()},
        "measure": "distinct outdoor model strings on the NRCan list",
    }
    # --- COP floor spike, for the COP histogram footnote ---
    ma = matched[matched["status"] == "Active"]
    summary["cop5_floor"] = {
        "active_matched": int(ma["cop5"].notna().sum()),
        "exactly_1_80": int((ma["cop5"].round(2) == 1.80).sum()),
        "below_1_80": int((ma["cop5"].round(2) < 1.80).sum()),
    }
    # --- scatter: capacity maintenance (cap5 / cap47) vs COP at 5 F ---
    sc = matched.copy()
    sc["cm"] = sc["cap5"] / sc["cap47"]
    gate = {}
    for label, sub_ in [("active", sc[sc["status"] == "Active"]), ("all", sc)]:
        n = len(sub_)
        no_cm = int(sub_["cm"].isna().sum())
        hi_cm = int((sub_["cm"] > CM_MAX).sum())
        hi_cop = int((sub_["cop5"] > COP_MAX).sum())
        gate[label] = {"matched_units": n, "missing_capacity_47_or_5": no_cm,
                       "capacity_maintenance_above_1_30_excluded": hi_cm,
                       "cop_above_3_0_excluded": hi_cop}
    ok = sc[sc["cm"].notna() & (sc["cm"] <= CM_MAX) & sc["cop5"].notna() & (sc["cop5"] <= COP_MAX)].copy()
    ok["cmr"] = ok["cm"].round(3)
    ok["stg"] = ok["es_staging"].fillna("Unknown")
    ok["act"] = (ok["status"] == "Active").astype(int)
    g = ok.groupby(["cap47", "cmr", "cop5", "stg"], dropna=False).agg(
        n_all=("ahri", "size"), n_active=("act", "sum")).reset_index()
    stg_codes = ["Continuously variable", "Two-stage", "Single stage", "Unknown"]
    pts = [[round(float(r.cmr), 3), round(float(r.cop5), 2), int(r.cap47),
            int(r.n_active), int(r.n_all), stg_codes.index(r.stg) if r.stg in stg_codes else 3]
           for r in g.itertuples()]
    gate["distinct_points"] = len(pts)
    summary["scatter_gate"] = gate
    PUB_SCATTER.write_text(json.dumps(
        {"columns": ["capacity_maintenance", "cop_5f", "capacity_47f_btuh", "n_active", "n_all", "stage_code"],
         "stage_codes": stg_codes, "generated": "2026-11-10", "points": pts},
        separators=(",", ":")), encoding="utf-8")
    summary["generated"] = "2026-11-10"
    OUT_JSON.write_text(json.dumps(summary, indent=1, ensure_ascii=False), encoding="utf-8")
    PUB_JSON.parent.mkdir(parents=True, exist_ok=True)
    PUB_JSON.write_text(json.dumps(summary, separators=(",", ":"), ensure_ascii=False), encoding="utf-8")

    print(json.dumps({k: summary[k] for k in
                      ["gates", "eligible_distinct_ahri", "by_product_group", "by_status", "match",
                       "ground_source_out_of_scope", "es_canada_units_not_on_list"]}, indent=1))
    for k in ["dist_matched_active", "dist_all_es_canada_market"]:
        d = summary[k]
        print(f"\n{k}: n={d['n_units']} median={d['median']} missing={d['missing']}")
        print("  cap47", dict(zip(d["cap47"]["labels"], d["cap47"]["counts"])))
        print("  cop5 ", dict(zip(d["cop5"]["labels"], d["cop5"]["counts"])))
        print("  hspf2", dict(zip(d["hspf2"]["labels"], d["hspf2"]["counts"])))
        print("  staging", d["compressor_staging"], "| brands", list(d["top_brands"].items())[:6])


if __name__ == "__main__":
    main()
