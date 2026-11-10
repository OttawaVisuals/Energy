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

# Plain-language bins (open-ended top and bottom).
BINS = {
    "cap47": ([0, 12000, 18000, 24000, 30000, 36000, 48000, 60000, 1e9],
              ["<12k", "12-18k", "18-24k", "24-30k", "30-36k", "36-48k", "48-60k", "60k+"]),
    "cop5": ([0, 1.5, 1.75, 2.0, 2.25, 2.5, 99],
             ["<1.5", "1.5-1.75", "1.75-2.0", "2.0-2.25", "2.25-2.5", "2.5+"]),
    "hspf2": ([0, 7.5, 8.0, 8.5, 9.0, 10.0, 99],
              ["<7.5", "7.5-8", "8-8.5", "8.5-9", "9-10", "10+"]),
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
