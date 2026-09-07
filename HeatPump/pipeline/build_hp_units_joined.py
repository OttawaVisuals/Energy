"""
build_hp_units_joined.py -- Phase 3c source join: AHRI + NRCan + ERS appearances.

WHY THIS EXISTS
---------------
`data/interim/hp_units_joined.csv` -- the one-row-per-AHRI-certified-unit table
that `build_cell_candidates.py`, `build_cell_curves.py`, `build_tier_curves.py`,
`build_tier_scatter.py`, `build_hp_tier_selection.py` and `screen_cchp.py` all
read -- had no producer script anywhere in the repo (TIER_SPEC.md Section 7,
"Reproducibility gap", flagged 2026-07-27; ROADMAP.md, Queued). It was built ad
hoc in an earlier session and the join logic was never written down. This
script reconstructs that join from its three still-reproducible inputs, traced
and verified field-by-field against the existing committed CSV before writing
this file (session 2026-09-07): every non-w column round-tripped exactly for
the units checked, and `cm`'s AHRI-over-NRCan precedence was confirmed live
(k=211644151: cm_ahri 0.72222.. wins over cm_nrcan 0.72).

INPUTS
------
  lookup/ahri_numbers.json            AHRI Directory scrape, dict keyed on AHRI
                                       certified reference number (`k`). Source
                                       of truth for cop, c47, cc, h4, cm_ahri.
                                       Built by Python/build_ahri_lookup_full.py.
  Python/ahri_numbers_all.json        Every AHRI-shaped value seen anywhere in
                                       the raw ERS CSVs, with total occurrence
                                       counts -- source of `w`. Same script.
  data/interim/nrcan_spl.csv          NRCan Searchable Product List, tidy union
                                       of the ashp1_gh/ashp2_gh segments (one
                                       row per segment x AHRI number, so
                                       heavily duplicated -- see DEDUP below).
                                       Source of pg, h5, cm_nrcan.
                                       Built by fetch_nrcan_spl.py.

COLUMN PROVENANCE (verified against the committed CSV, not assumed)
---------------------------------------------------------------
  k         AHRI certified reference number -- the join key, and the universe:
            every key in lookup/ahri_numbers.json (this file is already scoped
            to AHRI numbers observed in the ERS raw CSVs, not the full AHRI
            directory).
  w         Python/ahri_numbers_all.json's `total_count` for this k (0 if the
            AHRI scrape resolved a candidate that ahri_numbers_all.json's own
            list doesn't carry -- shouldn't happen since the scrape is driven
            by that same candidate list, but not assumed).
  cop       AHRI `heating_cop_5f`.
  c47       AHRI `heating_capacity_47f_btuh`.
  cc        AHRI `cold_climate` (Yes/No) -- NOT cooling capacity, despite the
            name; verified against a "Yes" row before trusting this.
  h4        AHRI `hspf2` (AHRI's own HSPF2 field; its docstring calls this
            "Region IV" since that's the AHRI/DOE default test region).
  cm_ahri   heating_capacity_5f_btuh / heating_capacity_47f_btuh, computed
            here (AHRI does not publish the ratio directly).
  pg        NRCan `PRODUCT_GROUP` (ccASHP / ASHP). AHRI has no equivalent
            field -- this is NRCan-only.
  h5        NRCan `HSPF2_Region_V` -- the cold-climate HSPF2 region AHRI does
            not carry at all. The entire reason NRCan is joined in.
  cm_nrcan  NRCan `Capacity_Maintenance_Max_5FRated_47F`, published as a bare
            integer percentage ("72" = 72%) -- divided by 100 here. "-" is
            NRCan's missing-value sentinel -> null.
  cm        cm_ahri if present, else cm_nrcan. AHRI is authoritative and NRCan
            only fills gaps (TIER_SPEC.md Section 1: "AHRI is authoritative;
            NRCan fills gaps (+448 models, +23,615 appearances), never
            overrides") -- confirmed live on k=211644151 above.

DEDUP
-----
nrcan_spl.csv carries one row per (grant segment, AHRI number) -- a unit
appearing in both ashp1_gh and ashp2_gh, or under more than one grant amount
tier, gets multiple identical rows. Checked before deduping (2026-09-07): of
162,183 distinct AHRI numbers in the file, zero groups disagree on
PRODUCT_GROUP, HSPF2_Region_V or Capacity_Maintenance_Max_5FRated_47F -- every
duplicate is a true duplicate, not a conflicting re-listing. Safe to
drop_duplicates(keep="first") on the AHRI number with no data loss.

OUTPUT
------
  data/interim/hp_units_joined.csv    k,w,cm,cm_ahri,cm_nrcan,h5,pg,h4,cop,cc,c47
                                       -- same column order as the file this
                                       replaces, so every downstream script
                                       needs no changes.

NOTE ON REPRODUCING THE EXACT OLD FILE
---------------------------------------
This will NOT byte-for-byte reproduce the 15,148-row file already committed:
lookup/ahri_numbers.json is a live, merge-only cache (build_ahri_lookup_full.py
never removes entries, and checkpointed runs keep adding to it), so a rerun
today picks up whatever has been resolved since the original ad hoc build --
one additional unit (AHRI 214606517, CHAMPION HEATING AND COOLING HH836E2S11)
was already found sitting in the cache but absent from the old CSV when this
script was written. That is the expected, correct behaviour of a real producer
script, not a bug to chase.

Run: python pipeline/build_hp_units_joined.py
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent          # HeatPump/
REPO_ROOT = ROOT.parent                                  # Energy/
INTERIM = ROOT / "data" / "interim"

AHRI_JSON = REPO_ROOT / "lookup" / "ahri_numbers.json"
AHRI_ALL_JSON = REPO_ROOT / "Python" / "ahri_numbers_all.json"
NRCAN_SPL = INTERIM / "nrcan_spl.csv"
OUT = INTERIM / "hp_units_joined.csv"

COLUMNS = ["k", "w", "cm", "cm_ahri", "cm_nrcan", "h5", "pg", "h4", "cop", "cc", "c47"]


def _num(v):
    """AHRI/NRCan numeric fields arrive as strings, with '-' as NRCan's null."""
    if v is None:
        return None
    s = str(v).strip()
    if s == "" or s == "-":
        return None
    try:
        return float(s)
    except ValueError:
        return None


def load_ahri():
    with open(AHRI_JSON, encoding="utf-8") as f:
        ahri = json.load(f)

    rows = []
    for k, rec in ahri.items():
        c47 = _num(rec.get("heating_capacity_47f_btuh"))
        c5 = _num(rec.get("heating_capacity_5f_btuh"))
        cm_ahri = (c5 / c47) if (c5 is not None and c47) else None
        rows.append({
            "k": str(k),
            "cop": _num(rec.get("heating_cop_5f")),
            "c47": c47,
            "cc": rec.get("cold_climate", ""),
            "h4": _num(rec.get("hspf2")),
            "cm_ahri": cm_ahri,
        })
    df = pd.DataFrame(rows)
    print(f"AHRI directory: {len(df):,} certified units (lookup/ahri_numbers.json)")
    return df


def load_ers_weights():
    with open(AHRI_ALL_JSON, encoding="utf-8") as f:
        data = json.load(f)
    w = pd.DataFrame(data["ahri_numbers"])
    w = w.rename(columns={"number": "k", "total_count": "w"})
    w["k"] = w["k"].astype(str)
    print(f"ERS appearance counts: {len(w):,} candidate AHRI numbers "
          f"({data.get('generated_from', 'source unrecorded')})")
    return w[["k", "w"]]


def load_nrcan():
    df = pd.read_csv(NRCAN_SPL, dtype=str)
    before = len(df)
    df = df.drop_duplicates(subset="AHRI_Certified_Reference_Number", keep="first")
    print(f"NRCan SPL: {before:,} rows -> {len(df):,} distinct AHRI numbers after dedup")

    out = pd.DataFrame({
        "k": df["AHRI_Certified_Reference_Number"].astype(str),
        "pg": df["PRODUCT_GROUP"].fillna(""),
        "h5": df["HSPF2_Region_V"].map(_num),
    })
    cm_pct = df["Capacity_Maintenance_Max_5FRated_47F"].map(_num)
    out["cm_nrcan"] = cm_pct.map(lambda v: v / 100.0 if v is not None else None)
    return out


def main():
    ahri = load_ahri()
    weights = load_ers_weights()
    nrcan = load_nrcan()

    df = ahri.merge(weights, on="k", how="left")
    n_no_w = df["w"].isna().sum()
    if n_no_w:
        print(f"  {n_no_w:,} AHRI-resolved units have no ERS appearance count "
              f"(candidate list and AHRI scrape have drifted) -- set to 0, not dropped")
    df["w"] = df["w"].fillna(0).astype(int)

    df = df.merge(nrcan, on="k", how="left")
    df["cm"] = df["cm_ahri"].where(df["cm_ahri"].notna(), df["cm_nrcan"])

    n_ahri_only = (df["cm_ahri"].notna()).sum()
    n_nrcan_fill = (df["cm_ahri"].isna() & df["cm_nrcan"].notna()).sum()
    n_neither = (df["cm_ahri"].isna() & df["cm_nrcan"].isna()).sum()
    print(f"cm resolution: {n_ahri_only:,} from AHRI, {n_nrcan_fill:,} filled from NRCan, "
          f"{n_neither:,} have neither (left null, not dropped)")

    df = df[COLUMNS]
    INTERIM.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT, index=False)
    print(f"Wrote {len(df):,} rows to {OUT}")


if __name__ == "__main__":
    main()
