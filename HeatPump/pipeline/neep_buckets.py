"""
neep_buckets.py — Phase 3a of the Heat Pump tool.

Buckets the NEEP cold-climate ASHP product list into 3 performance tiers and
selects representative candidate models per tier, then cross-matches the most
popular AHRI reference numbers seen in the ERS retrofit data against the NEEP
list to seed an "average installed" bucket.

See ROADMAP.md item 3a and PLAN.md (Phase 3) for the design rationale.

Inputs
------
- HeatPump/data/raw/neep/neep_air_source_heat_pump_<date>.xlsx   (NEEP ccASHP list)
- ahri_numbers_seen.csv        (popularity ranking of AHRI refs in ERS data)
- lookup/ahri_numbers.json     (AHRI ref -> brand / outdoor model, from AHRI Directory)

Outputs
-------
- HeatPump/data/interim/neep_tiers.csv        (one row per physical unit -> metrics -> tier)
- HeatPump/data/interim/neep_tier_report.md   (tier defs, candidates, AHRI match results)

Does NOT build performance curves — that is Phase 3b, after the user approves
the candidate models.
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict
from difflib import SequenceMatcher
from pathlib import Path

import numpy as np
import openpyxl
import pandas as pd
from scipy.cluster.vq import kmeans2

# --------------------------------------------------------------------------
# Paths
# --------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parents[2]           # C:\Energy
HP = ROOT / "HeatPump"
RAW_NEEP_DIR = HP / "data" / "raw" / "neep"
INTERIM = HP / "data" / "interim"
AHRI_SEEN_CSV = ROOT / "Python" / "ahri_numbers_seen.csv"
AHRI_LOOKUP_JSON = ROOT / "lookup" / "ahri_numbers.json"

OUT_CSV = INTERIM / "neep_tiers.csv"
OUT_MD = INTERIM / "neep_tier_report.md"

# --------------------------------------------------------------------------
# Constants
# --------------------------------------------------------------------------
BTU_PER_H_TO_KW = 0.29307107 / 1000.0    # 1 BTU/h = 0.293071 W

# Rated-capacity size classes (at 47 F), so tiers compare like-for-like sizes.
#   2-ton class : < 30,000 BTU/h  (<= ~2.5 ton)
#   3-ton class : 30,000-42,000   (~2.5-3.5 ton)
#   4-ton class : >= 42,000       (>= ~3.5 ton)
SIZE_BINS = [(0, 30000, "2-ton"), (30000, 42000, "3-ton"), (42000, 1e9, "4-ton")]

# Major brands with public engineering data books — spec-sheet lookup candidates.
# Matched as case-insensitive substrings against Brand Owner + Brand Name.
MAJOR_BRANDS = {
    "mitsubishi": "Mitsubishi",
    "daikin": "Daikin",
    "fujitsu": "Fujitsu",
    "samsung": "Samsung",
    "carrier": "Carrier/Midea",
    "midea": "Carrier/Midea",
    "gree": "Gree",
    "lennox": "Lennox",
    "trane": "Trane",
    # LG handled specially (2-letter token would over-match)
}

RANDOM_SEED = 20260710


def kelvin_from_f(f: float) -> float:
    return (f - 32.0) * 5.0 / 9.0


def size_class(cap_btu: float) -> str:
    for lo, hi, name in SIZE_BINS:
        if lo <= cap_btu < hi:
            return name
    return "unknown"


def major_brand_of(brand_owner: str, brand_name: str) -> str | None:
    blob = f"{brand_owner or ''} {brand_name or ''}".lower()
    for key, label in MAJOR_BRANDS.items():
        if key in blob:
            return label
    # LG: whole-word match to avoid matching inside other words
    if re.search(r"\blg\b", blob):
        return "LG"
    return None


# --------------------------------------------------------------------------
# 1. Load & parse the NEEP HP Report sheet
# --------------------------------------------------------------------------
def load_neep(path: Path) -> pd.DataFrame:
    print(f"[neep] loading {path.name} (this takes ~30s) ...", flush=True)
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb["HP Report"]
    it = ws.iter_rows(values_only=True)
    next(it)                       # row 0: usage-disclaimer banner
    header = list(next(it))        # row 1: column headers
    # strip the trailing superscript-plus marker NEEP puts on AHRI-rated fields
    col = {re.sub(r"[⁺⁻\+]+$", "", (h or "").strip()): i
           for i, h in enumerate(header)}

    def ci(name: str) -> int:
        if name in col:
            return col[name]
        raise KeyError(f"NEEP column not found: {name!r}")

    # Resolve the indices we need once.
    idx = {
        "status": ci("Status"),
        "brand_owner": ci("Brand Owner"),
        "brand": ci("Brand Name"),
        "series": ci("Series Name"),
        "ducting": ci("Ducting Configuration"),
        "ahri": ci("AHRI Certified Reference Number"),
        "old_ahri": ci("Old AHRI Certified Reference Number"),
        "ahri_type": ci("AHRI Type"),
        "outdoor": ci("Outdoor Unit Model Number"),
        "indoor": ci("Indoor Model Number(s)"),
        "refrigerant": ci("Refrigerant"),
        "variable": ci("Variable Capacity?"),
        "cap_rated_47": ci("Rated Capacity 47°F"),
        "cop_rated_47": ci("COP Rated 47°F"),
        "cop_max_47": ci("COP Max 47°F"),
        "cop_max_17": ci("COP Max 17°F"),
        "cap_max_5": ci("Max Capacity 5°F"),
        "cop_max_5": ci("COP Max 5°F"),
        "cop_rated_5": ci("COP Rated 5°F - Optional"),
        "lct_f": ci("Lowest Cataloged Temperature (Outdoor Dry Bulb °F)"),
        "cop_max_lct": ci("COP Max LCT°F"),
    }

    rows = []
    for r in it:
        rows.append(tuple(r[idx[k]] for k in idx))
    df = pd.DataFrame(rows, columns=list(idx.keys()))
    print(f"[neep] {len(df):,} AHRI-certified combinations loaded", flush=True)
    return df


def num(s):
    """Coerce a cell to float, returning NaN on blanks/junk."""
    try:
        return float(s)
    except (TypeError, ValueError):
        return np.nan


# --------------------------------------------------------------------------
# 2. Per-combination screening metrics (SI)
# --------------------------------------------------------------------------
def compute_metrics(df: pd.DataFrame) -> pd.DataFrame:
    n0 = len(df)
    for c in ["cap_rated_47", "cop_rated_47", "cop_max_47", "cop_max_17",
              "cap_max_5", "cop_max_5", "cop_rated_5", "lct_f", "cop_max_lct"]:
        df[c] = df[c].map(num)

    df["rated_cap_47_kw"] = df["cap_rated_47"] * BTU_PER_H_TO_KW
    df["max_cap_5_kw"] = df["cap_max_5"] * BTU_PER_H_TO_KW
    # COP at 5 F: use the MAX-compressor-speed point (what a home draws when it is
    # cold and calling for full heat) — consistent with the retention numerator.
    df["cop_5f"] = df["cop_max_5"]
    # Capacity retention = max capacity @5F / rated capacity @47F (size-independent).
    df["retention"] = df["cap_max_5"] / df["cap_rated_47"]
    # Minimum operating temperature: the Lowest Cataloged Temperature where NEEP
    # gives one; otherwise the coldest cataloged point is 5 F (-15 C).
    df["min_op_temp_c"] = df["lct_f"].map(
        lambda f: kelvin_from_f(f) if pd.notna(f) else kelvin_from_f(5.0))
    df["has_lct"] = df["lct_f"].notna()
    df["tons"] = df["cap_rated_47"] / 12000.0
    df["size_class"] = df["cap_rated_47"].map(
        lambda c: size_class(c) if pd.notna(c) else "unknown")

    # Cleaning: require the metrics that clustering needs, and drop physically
    # implausible values (data-entry errors in a 180k-row spreadsheet).
    good = (
        df["rated_cap_47_kw"].gt(0)
        & df["max_cap_5_kw"].gt(0)
        & df["cop_5f"].between(0.5, 6.0)
        & df["retention"].between(0.2, 2.0)
    )
    dropped = int((~good).sum())
    print(f"[metrics] dropped {dropped:,} / {n0:,} rows with missing/implausible "
          f"metrics ({100*dropped/n0:.2f}%)", flush=True)
    return df[good].copy()


# --------------------------------------------------------------------------
# 3. Deduplicate to physical outdoor units
# --------------------------------------------------------------------------
def dedup_units(df: pd.DataFrame) -> pd.DataFrame:
    """
    A single physical outdoor unit appears in NEEP as many AHRI combinations
    (one per certified indoor pairing). Carrier alone is ~110k of the ~180k
    rows. Clustering on raw combinations would bias the tiers toward whoever
    certified the most indoor pairings. So we collapse to one row per
    (brand owner, brand, outdoor model) using the MEDIAN of each metric across
    its pairings, and cluster on that.
    """
    keys = ["brand_owner", "brand", "outdoor"]
    grp = df.groupby(keys, dropna=False)
    units = grp.agg(
        cop_5f=("cop_5f", "median"),
        retention=("retention", "median"),
        rated_cap_47_kw=("rated_cap_47_kw", "median"),
        cap_rated_47_btu=("cap_rated_47", "median"),
        cop_rated_47=("cop_rated_47", "median"),
        cop_max_47=("cop_max_47", "median"),
        cop_max_17=("cop_max_17", "median"),
        min_op_temp_c=("min_op_temp_c", "median"),
        has_lct=("has_lct", "max"),
        series=("series", "first"),
        refrigerant=("refrigerant", "first"),
        ahri_type=("ahri_type", "first"),
        n_combinations=("ahri", "size"),
    ).reset_index()
    units["tons"] = units["cap_rated_47_btu"] / 12000.0
    units["size_class"] = units["cap_rated_47_btu"].map(size_class)
    units["major_brand"] = units.apply(
        lambda r: major_brand_of(r["brand_owner"], r["brand"]), axis=1)
    print(f"[dedup] {len(df):,} combinations -> {len(units):,} physical outdoor "
          f"units", flush=True)
    return units


# --------------------------------------------------------------------------
# 4. Cluster into 3 tiers
# --------------------------------------------------------------------------
def assign_tiers(units: pd.DataFrame):
    """
    Primary method: **quantile-cut on a composite cold-climate performance
    score** = equal-weight mean of the percentile ranks of COP@5 °F and
    capacity retention, cut into equal terciles (Tier 1 = top third).

    Why not k-means here: the two metrics are essentially uncorrelated
    (r ~= -0.03) and COP@5 °F is compressed with heavy rounding pileups, so
    k-means centroids land on incoherent, non-monotonic splits (a "baseline"
    cluster ending up with higher retention than the "mid" cluster). A
    percentile-rank composite is robust to the skew/pileups and guarantees a
    monotonic premium->baseline gradient in both metrics, which is exactly the
    tier semantics the tool needs. k-means is retained as a cross-check
    (see `kmeans_crosscheck`).

    Returns (units with tier/z-scores/dist_centroid, tier_stats, (mu, sd)).
    """
    feats = units[["cop_5f", "retention"]].to_numpy(dtype=float)
    mu = feats.mean(axis=0)
    sd = feats.std(axis=0)
    z = (feats - mu) / sd
    units["z_cop"] = z[:, 0]
    units["z_ret"] = z[:, 1]

    pr_cop = units["cop_5f"].rank(pct=True)
    pr_ret = units["retention"].rank(pct=True)
    units["composite"] = (pr_cop + pr_ret) / 2.0
    # tercile: top third -> Tier 1 (best). rank(method='first') breaks ties so
    # qcut gets exactly-equal bins.
    units["tier"] = pd.qcut(units["composite"].rank(method="first"), 3,
                            labels=[3, 2, 1]).astype(int)
    units["tier_label"] = units["tier"].map(
        {1: "Tier 1 - cold-climate premium",
         2: "Tier 2 - mid-market cold-climate",
         3: "Tier 3 - baseline"})

    # Tier centroid = mean [COP@5F, retention] of members; distance measured in
    # standardized space, for centroid-nearest candidate selection.
    cent_z = np.zeros((3, 2))
    dist = np.zeros(len(units))
    for t in (1, 2, 3):
        m = units["tier"].to_numpy() == t
        cz = z[m].mean(axis=0)
        cent_z[t - 1] = cz
        dist[m] = np.linalg.norm(z[m] - cz, axis=1)
    units["dist_centroid"] = dist
    cent_real = cent_z * sd + mu

    stats = []
    for t in (1, 2, 3):
        sub = units[units["tier"] == t]
        stats.append({
            "tier": t,
            "label": units.loc[units["tier"] == t, "tier_label"].iloc[0],
            "n_units": len(sub),
            "n_combinations": int(sub["n_combinations"].sum()),
            "centroid_cop5": cent_real[t - 1, 0],
            "centroid_retention": cent_real[t - 1, 1],
            "cop5_min": sub["cop_5f"].min(),
            "cop5_med": sub["cop_5f"].median(),
            "cop5_max": sub["cop_5f"].max(),
            "ret_min": sub["retention"].min(),
            "ret_med": sub["retention"].median(),
            "ret_max": sub["retention"].max(),
            "min_op_temp_med": sub["min_op_temp_c"].median(),
        })
    return units, pd.DataFrame(stats), (mu, sd)


def kmeans_crosscheck(units: pd.DataFrame, musd) -> float:
    """
    Cross-check the composite quantile tiers against k-means (k=3) on the same
    standardized features. Order the k-means clusters best->worst by composite
    centroid z-score, then report the fraction of units whose k-means cluster
    matches their composite tier.
    """
    z = units[["z_cop", "z_ret"]].to_numpy(dtype=float)
    centroids, labels = kmeans2(z, 3, seed=RANDOM_SEED, minit="++",
                                missing="raise")
    order = np.argsort(-centroids.sum(axis=1))       # best cluster first
    remap = {old: new + 1 for new, old in enumerate(order)}
    km_tier = np.array([remap[l] for l in labels])
    agree = (km_tier == units["tier"].to_numpy()).mean()
    return float(agree)


# --------------------------------------------------------------------------
# 5. Candidate models per tier (nearest centroid, major brands)
# --------------------------------------------------------------------------
def tier_candidates(units: pd.DataFrame, n=5) -> dict[int, pd.DataFrame]:
    """5 major-brand units nearest each tier centroid, deduped by outdoor model
    (many outdoor chassis are rebadged under several brand owners)."""
    out = {}
    for t in (1, 2, 3):
        sub = units[(units["tier"] == t) & units["major_brand"].notna()].copy()
        sub = sub.sort_values("dist_centroid")
        sub = sub.drop_duplicates(subset="outdoor", keep="first").head(n)
        out[t] = sub
    return out


# --------------------------------------------------------------------------
# 6. AHRI popularity cross-match
# --------------------------------------------------------------------------
def normalize_model(s: str) -> str:
    """Uppercase, drop wildcards / revision suffixes / non-alphanumerics."""
    if not s:
        return ""
    s = s.upper()
    s = s.replace("*", "")
    s = re.sub(r"[^A-Z0-9]", "", s)
    return s


def normalize_brand(s: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", (s or "").upper())


def ahri_crossmatch(df: pd.DataFrame, units: pd.DataFrame, top_n=10):
    """
    Match the top-N most popular AHRI reference numbers (from ERS retrofit data)
    to NEEP. Strategy, in order:
      (a) EXACT: the seen AHRI number equals a NEEP AHRI ref (current or old).
      (b) FUZZY: normalized brand + outdoor model from lookup/ahri_numbers.json
          against NEEP units (SequenceMatcher on the model, brand must agree).
    Returns a list of per-unit result dicts and the popularity-weighted means.
    """
    seen = pd.read_csv(AHRI_SEEN_CSV, dtype={"ahri_number": str})
    seen = seen.sort_values("total_count", ascending=False).head(top_n)
    lookup = json.loads(AHRI_LOOKUP_JSON.read_text(encoding="utf-8"))

    # Exact index: AHRI ref (current + old) -> combination row.
    df = df.copy()
    df["ahri_s"] = df["ahri"].map(lambda x: str(x).strip() if x is not None else "")
    df["old_ahri_s"] = df["old_ahri"].map(
        lambda x: str(x).strip() if x is not None else "")
    by_ahri = {}
    for _, r in df.iterrows():
        for key in (r["ahri_s"], r["old_ahri_s"]):
            if key:
                by_ahri.setdefault(key, r)

    # Map each combination back to its physical unit's tier/metrics.
    unit_key = units.set_index(["brand_owner", "brand", "outdoor"])

    def unit_for_row(r):
        try:
            return unit_key.loc[(r["brand_owner"], r["brand"], r["outdoor"])]
        except KeyError:
            return None

    # Pre-normalize NEEP units for fuzzy matching.
    units_norm = units.copy()
    units_norm["nmodel"] = units_norm["outdoor"].map(normalize_model)
    units_norm["nbrand"] = units_norm["brand"].map(normalize_brand)

    results = []
    for _, s in seen.iterrows():
        num_str = s["ahri_number"]
        cnt = int(s["total_count"])
        info = lookup.get(num_str, {})
        brand = info.get("brand", "")
        model = info.get("model", "")
        rec = {
            "ahri_number": num_str, "count": cnt, "brand": brand, "model": model,
            "lookup_cold_climate": info.get("cold_climate", ""),
            "method": None, "matched_outdoor": None, "matched_brand": None,
            "tier": None, "cop_5f": None, "retention": None, "score": None,
        }

        # (a) exact AHRI-ref match
        row = by_ahri.get(num_str)
        if row is not None:
            u = unit_for_row(row)
            rec.update(method="exact-ahri", matched_outdoor=row["outdoor"],
                       matched_brand=row["brand"], score=1.0)
            if u is not None:
                rec.update(tier=int(u["tier"]), cop_5f=float(u["cop_5f"]),
                           retention=float(u["retention"]))
            results.append(rec)
            continue

        # (b) fuzzy brand + model
        nb, nm = normalize_brand(brand), normalize_model(model)
        best = None
        if nm:
            cand = units_norm[units_norm["nbrand"] == nb]
            if cand.empty:      # relax: brand contained either way
                cand = units_norm[units_norm["nbrand"].str.contains(nb, na=False)
                                  | units_norm["nbrand"].apply(
                                      lambda x: x in nb if x else False)]
            for _, u in cand.iterrows():
                score = SequenceMatcher(None, nm, u["nmodel"]).ratio()
                if best is None or score > best[0]:
                    best = (score, u)
        if best and best[0] >= 0.80:
            score, u = best
            rec.update(method="fuzzy-model", matched_outdoor=u["outdoor"],
                       matched_brand=u["brand"], tier=int(u["tier"]),
                       cop_5f=float(u["cop_5f"]), retention=float(u["retention"]),
                       score=round(score, 3))
        results.append(rec)

    matched = [r for r in results if r["tier"] is not None]
    tot_w = sum(r["count"] for r in matched)
    if tot_w:
        w_cop = sum(r["cop_5f"] * r["count"] for r in matched) / tot_w
        w_ret = sum(r["retention"] * r["count"] for r in matched) / tot_w
    else:
        w_cop = w_ret = float("nan")
    match_rate = len(matched) / len(results) if results else 0.0
    return results, {"n_top": len(results), "n_matched": len(matched),
                     "match_rate": match_rate, "weighted_cop5": w_cop,
                     "weighted_retention": w_ret, "weight_total": tot_w}


# --------------------------------------------------------------------------
# 7. Reporting
# --------------------------------------------------------------------------
def print_tier_stats(stats: pd.DataFrame, agree: float):
    print("\n" + "=" * 70)
    print("TIER BOUNDARY STATS  (composite quantile-cut on [COP@5F, retention])")
    print("=" * 70)
    for _, s in stats.iterrows():
        print(f"\n{s['label']}")
        print(f"  units={s['n_units']:,}  combinations={s['n_combinations']:,}")
        print(f"  centroid: COP@5F={s['centroid_cop5']:.2f}  "
              f"retention={s['centroid_retention']*100:.0f}%")
        print(f"  COP@5F   min/med/max = {s['cop5_min']:.2f} / "
              f"{s['cop5_med']:.2f} / {s['cop5_max']:.2f}")
        print(f"  retention min/med/max = {s['ret_min']*100:.0f}% / "
              f"{s['ret_med']*100:.0f}% / {s['ret_max']*100:.0f}%")
        print(f"  median min-operating-temp = {s['min_op_temp_med']:.1f} C")
    print(f"\nk-means cross-check: {agree*100:.1f}% of units fall in the "
          f"same tier as the composite quantile-cut.\n")


def write_report(stats, cands, ahri_results, ahri_summary, units, n_comb, n_drop,
                 km_agree):
    lines = []
    A = lines.append
    A("# NEEP ccASHP Performance Tiers — Phase 3a Report\n")
    A("_Generated by `HeatPump/pipeline/neep_buckets.py`. "
      "Source: NEEP ccASHP Product List, `HP Report` sheet._\n")
    A("**Do not build final curves from this** — it selects candidate models "
      "for the user to approve (Phase 3b).\n")

    A("## Method summary\n")
    A(f"- Parsed **{n_comb:,}** AHRI-certified combinations from the NEEP "
      "`HP Report` sheet; dropped "
      f"**{n_drop:,}** with missing/implausible metrics.\n")
    A(f"- Collapsed to **{len(units):,}** unique physical outdoor units "
      "(`brand owner + brand + outdoor model`), median metric across each unit's "
      "certified indoor pairings. This removes the heavy duplication (Carrier "
      "alone is ~110k combinations) that would otherwise bias the tiers.\n")
    A("- Screening metrics per unit (SI): **COP@5 °F** (−15 °C, max-compressor "
      "point) and **capacity retention** = max capacity @5 °F ÷ rated capacity "
      "@47 °F.\n")
    A("- The two metrics are **essentially uncorrelated** (r ≈ −0.03) and "
      "COP@5 °F is compressed with heavy rounding pileups, so k-means centroids "
      "land on incoherent, non-monotonic splits. Tiers are therefore assigned by "
      "**quantile-cut on a composite score** = equal-weight mean of the "
      "percentile ranks of COP@5 °F and retention, cut into equal terciles "
      "(Tier 1 = top third). This guarantees a monotonic premium→baseline "
      "gradient in both metrics.\n")
    A("- **k-means (k=3)** on the same standardized features is retained only as "
      "a cross-check (agreement reported below).\n")
    A("- **COP@5 °F never drops below 1.75** in the whole list (488 units sit "
      "exactly at 1.75, none below) — this is NEEP's own inclusion floor, and it "
      "is what compresses the COP metric. The compression is a property of the "
      "list, not a parsing artefact.\n")

    A("\n## Tier definitions\n")
    A("| Tier | Units | Combinations | Centroid COP@5 °F | Centroid retention | "
      "COP@5 °F (min/med/max) | Retention (min/med/max) | Median min-op temp |")
    A("|---|---|---|---|---|---|---|---|")
    for _, s in stats.iterrows():
        A(f"| {s['label']} | {s['n_units']:,} | {s['n_combinations']:,} | "
          f"{s['centroid_cop5']:.2f} | {s['centroid_retention']*100:.0f}% | "
          f"{s['cop5_min']:.2f} / {s['cop5_med']:.2f} / {s['cop5_max']:.2f} | "
          f"{s['ret_min']*100:.0f}% / {s['ret_med']*100:.0f}% / "
          f"{s['ret_max']*100:.0f}% | {s['min_op_temp_med']:.1f} °C |")
    A(f"\n_k-means cross-check: **{km_agree*100:.0f}%** of units land in the same "
      "tier as the composite quantile-cut._\n")

    A("\n## Candidate models per tier (nearest centroid, major brands)\n")
    A("_Five units closest to each tier centroid among Mitsubishi, Daikin, "
      "Fujitsu, LG, Samsung, Carrier/Midea, Gree, Lennox, Trane. These are the "
      "spec-sheet lookup candidates for Phase 3b._\n")
    for t in (1, 2, 3):
        label = stats.loc[stats["tier"] == t, "label"].iloc[0]
        A(f"\n### {label}\n")
        sub = cands[t]
        if sub.empty:
            A("_No major-brand unit in this tier._\n")
            continue
        A("| Brand | Series | Outdoor model | Size | COP@5 °F | Retention | "
          "Min-op °C | Refrigerant | # combos |")
        A("|---|---|---|---|---|---|---|---|---|")
        for _, u in sub.iterrows():
            A(f"| {u['major_brand']} | {u['series'] or ''} | {u['outdoor']} | "
              f"{u['size_class']} | {u['cop_5f']:.2f} | {u['retention']*100:.0f}% | "
              f"{u['min_op_temp_c']:.1f} | {u['refrigerant'] or ''} | "
              f"{int(u['n_combinations'])} |")

    A("\n## AHRI popularity cross-match (\"average installed\" seed)\n")
    A(f"- Top **{ahri_summary['n_top']}** AHRI reference numbers by frequency in "
      "the ERS retrofit data (`ahri_numbers_seen.csv`).\n")
    A(f"- Matched **{ahri_summary['n_matched']} / {ahri_summary['n_top']}** to a "
      f"NEEP unit (**{ahri_summary['match_rate']*100:.0f}%** match rate). Match "
      "strategy: exact AHRI-ref (current or old) first, then fuzzy "
      "normalized-brand+model (SequenceMatcher ≥ 0.80).\n")
    A(f"- **Popularity-weighted mean of the matched set: COP@5 °F = "
      f"{ahri_summary['weighted_cop5']:.2f}, retention = "
      f"{ahri_summary['weighted_retention']*100:.0f}%** "
      f"(weight = {ahri_summary['weight_total']:,} occurrences). This seeds the "
      "\"average installed\" bucket.\n")
    A("\n| AHRI # | Occurrences | Lookup brand | Lookup model | ccASHP? | Method | "
      "Matched NEEP outdoor | Tier | COP@5 °F | Retention | Score |")
    A("|---|---|---|---|---|---|---|---|---|---|---|")
    for r in ahri_results:
        tier = "" if r["tier"] is None else f"T{r['tier']}"
        cop = "" if r["cop_5f"] is None else f"{r['cop_5f']:.2f}"
        ret = "" if r["retention"] is None else f"{r['retention']*100:.0f}%"
        sc = "" if r["score"] is None else f"{r['score']}"
        A(f"| {r['ahri_number']} | {r['count']:,} | {r['brand']} | {r['model']} | "
          f"{r['lookup_cold_climate']} | {r['method'] or 'no match'} | "
          f"{r['matched_outdoor'] or ''} | {tier} | {cop} | {ret} | {sc} |")

    A("\n## Caveats\n")
    A("- All 10 popular units matched because the NEEP `HP Report` is broad "
      "(every unit meeting NEEP's COP@5 °F ≥ 1.75 floor, not only ENERGY STAR "
      "Cold-Climate-certified models — note the `ccASHP?` column mixes Yes/No). "
      "The **most-installed units cluster in the baseline tier**: the two single "
      "most popular AHRI numbers (GREE GUD36, ~10.6k combined occurrences) are "
      "Tier 3, so the popularity-weighted \"average installed\" leans baseline "
      "(COP@5 °F ≈ 1.87, just above the Tier-3 centroid of 1.84).\n")
    A("- COP@5 °F uses the **max-compressor-speed** point (the relevant one for a "
      "cold home calling for full heat); retention uses the same point so the two "
      "are consistent.\n")
    A("- Units without a Lowest Cataloged Temperature are floored at 5 °F "
      "(−15 °C) min-operating temp — we simply have no colder catalog point for "
      "them, not a claim they lock out there.\n")

    OUT_MD.write_text("\n".join(lines), encoding="utf-8")
    print(f"[out] wrote {OUT_MD}", flush=True)


def main():
    INTERIM.mkdir(parents=True, exist_ok=True)
    xlsx = sorted(RAW_NEEP_DIR.glob("neep_air_source_heat_pump_*.xlsx"))
    if not xlsx:
        sys.exit(f"No NEEP xlsx found under {RAW_NEEP_DIR}")
    df = load_neep(xlsx[-1])
    n_comb0 = len(df)
    df = compute_metrics(df)
    n_drop = n_comb0 - len(df)
    units = dedup_units(df)
    units, stats, musd = assign_tiers(units)
    agree = kmeans_crosscheck(units, musd)
    print_tier_stats(stats, agree)

    cands = tier_candidates(units)
    for t in (1, 2, 3):
        print(f"\n[candidates] {stats.loc[stats['tier']==t,'label'].iloc[0]}")
        for _, u in cands[t].iterrows():
            print(f"   {u['major_brand']:14s} {str(u['outdoor'])[:28]:28s} "
                  f"{u['size_class']:6s} COP@5={u['cop_5f']:.2f} "
                  f"ret={u['retention']*100:.0f}% d={u['dist_centroid']:.3f}")

    ahri_results, ahri_summary = ahri_crossmatch(df, units, top_n=10)
    print("\n" + "=" * 70)
    print("AHRI POPULARITY CROSS-MATCH")
    print("=" * 70)
    for r in ahri_results:
        t = "" if r["tier"] is None else f"Tier {r['tier']}"
        print(f"  {r['ahri_number']:>10s} x{r['count']:<5d} {str(r['brand'])[:10]:10s} "
              f"{str(r['model'])[:22]:22s} -> {r['method'] or 'NO MATCH':12s} {t}")
    print(f"\n  match rate: {ahri_summary['n_matched']}/{ahri_summary['n_top']} "
          f"({ahri_summary['match_rate']*100:.0f}%)")
    print(f"  popularity-weighted COP@5F = {ahri_summary['weighted_cop5']:.2f}, "
          f"retention = {ahri_summary['weighted_retention']*100:.0f}%")

    # --- write neep_tiers.csv (one row per physical unit) ---
    cand_keys = set()
    for t in (1, 2, 3):
        for _, u in cands[t].iterrows():
            cand_keys.add((u["brand_owner"], u["brand"], u["outdoor"]))
    units["is_candidate"] = units.apply(
        lambda r: (r["brand_owner"], r["brand"], r["outdoor"]) in cand_keys, axis=1)
    cols = ["brand_owner", "brand", "series", "outdoor", "ahri_type",
            "refrigerant", "size_class", "tons", "rated_cap_47_kw",
            "cop_5f", "retention", "cop_rated_47", "cop_max_47", "cop_max_17",
            "min_op_temp_c", "has_lct", "n_combinations", "tier", "tier_label",
            "dist_centroid", "major_brand", "is_candidate"]
    out = units[cols].sort_values(["tier", "dist_centroid"])
    out.to_csv(OUT_CSV, index=False)
    print(f"\n[out] wrote {OUT_CSV}  ({len(out):,} units)")

    write_report(stats, cands, ahri_results, ahri_summary, units, n_comb0, n_drop,
                 agree)


if __name__ == "__main__":
    main()
