"""
build_difficulty.py  (v2 Phase C)

Per-well *drilling-difficulty* score for vertical closed-loop GSHP boreholes,
gridded onto the same 500 m surface as the conductivity layer (idw.py).

This is a **screening heuristic**, not a drilling quote: it ranks where a
vertical borehole is likely to be cheaper vs. harder to drill, from what the
WWIS water-well logs record. Four components, each scaled to 0-1 and given a
documented point weight (they sum to 100):

    overburden thickness   40 pts  bedrock_depth_m (incl. Phase A's formations
                                   fallback) / OVERBURDEN_FULL_M, capped at 1.
                                   Deeper overburden = more casing to advance to
                                   stable bedrock = cost. 0 pts at 0 m (bedrock
                                   at surface) rising to the full 40 at >= 30 m.
    problem layers         20 pts  count of formation intervals whose primary
                                   material is boulders / stones / quicksand /
                                   hardpan, / PROBLEM_FULL_N, capped at 1.
                                   Casing-advance & lost-circulation risk.
    rock hardness          25 pts  HARDNESS[lithology]: granite/gneiss hardest
                                   (slow penetration, bit wear), limestone/
                                   dolostone the carbonate baseline, shale/
                                   sandstone easiest.
    artesian               15 pts  neighbourhood share of flowing-artesian wells
                                   within ARTESIAN_RADIUS_M / ARTESIAN_FULL_SHARE,
                                   capped at 1. Flowing conditions complicate
                                   grouting/completion. Sparse (503 flowing
                                   wells), so it's a neighbourhood indicator, not
                                   a per-well flag.

difficulty_score = Σ component points (0-100), rounded to the nearest 5 (the
inputs don't justify finer precision), with a 3-class label:

    easy       score <  CLASS_EASY_MAX
    moderate   CLASS_EASY_MAX <= score < CLASS_DIFFICULT_MIN
    difficult  score >= CLASS_DIFFICULT_MIN

Only wells with a **known depth-to-bedrock** are scored: overburden thickness is
the dominant driver and is not imputed. Each component is gridded separately with
the shared IDW conventions, so a cell carries the full breakdown (for the popup)
and its dominant driver = the largest of the four gridded contributions.

Output:
    Data/processed/difficulty_grid.geojson
        polygon grid with difficulty_score, difficulty_class, driver,
        overburden_pts / problem_pts / hardness_pts / artesian_pts,
        n_wells, confidence (high/low)

Usage:
    python Geothermal/scripts/build_difficulty.py
"""

from pathlib import Path

import numpy as np
import geopandas as gpd
import pandas as pd
from scipy.spatial import cKDTree
from shapely.geometry import box

from idw import (make_grid, idw_weights, estimate, count_within,
                 CELL_M, MASK_DIST_M, CONF_DIST_M, CONF_MIN_WELLS)

HERE = Path(__file__).resolve().parents[1]              # Geothermal/
GPKG = HERE / "Data" / "processed" / "ottawa_geothermal.gpkg"
OUT = HERE / "Data" / "processed" / "difficulty_grid.geojson"
METHOD_CSV = HERE / "Data" / "tblMethod_Construction_Ottawa.csv"
METHOD_CODE_CSV = HERE / "Data" / "_code_construct_method.csv"

BBOX = (-76.36, 44.96, -75.24, 45.61)   # Ottawa (drops mis-located wells)
CRS_METRIC = 32618                        # UTM 18N

# --- component weights (points; sum to 100) ------------------------------
W_OVERBURDEN = 40
W_PROBLEM = 20
W_HARDNESS = 25
W_ARTESIAN = 15
COMPONENTS = ["overburden", "problem layers", "rock hardness", "artesian"]

# --- factor transforms ----------------------------------------------------
OVERBURDEN_FULL_M = 30.0      # bedrock depth at/above which overburden scores max
PROBLEM_FULL_N = 2            # this many problem intervals -> max problem points
ARTESIAN_RADIUS_M = 1000      # neighbourhood radius for the flowing-well share
ARTESIAN_FULL_SHARE = 0.10    # local flowing share at/above which artesian maxes

# formation intervals whose *primary* material flags casing/circulation trouble
# (material1 only -- the interval's dominant material; matches the 2026-07-15
# audit's 7,395-well count. "STONES"/"BOULDERS" as a secondary modifier of a
# clay/till layer is far more common and far less of a drilling problem.)
PROBLEM_MATERIALS = {"BOULDERS", "STONES", "STONEY", "QUICKSAND", "HARDPAN"}

# lithology bucket -> hardness factor (0 easy .. 1 hardest). Overburden-only
# buckets (no bedrock logged) and unknown default to the limestone baseline:
# under Ottawa's clay plain a vertical borehole reaches the Paleozoic platform
# (limestone/dolostone-dominant), so "no bedrock logged" is not "soft".
HARDNESS = {
    "granite": 1.0, "gneiss": 1.0, "basalt": 0.7,
    "rock": 0.5,                                  # generic undifferentiated bedrock
    "limestone": 0.4, "dolostone": 0.4,           # carbonate baseline
    "sandstone": 0.25, "shale": 0.15,             # softest sedimentary
    "clay": 0.4, "silt": 0.4, "sand": 0.4,
    "gravel": 0.4, "till": 0.4, "fill": 0.4, "unknown": 0.4,
}
HARDNESS_DEFAULT = HARDNESS["unknown"]

# 3-class thresholds on the 0-100 score (tuned to the score distribution -- see
# README §4). Kept as round numbers; the score itself is rounded to 5.
CLASS_EASY_MAX = 25
CLASS_DIFFICULT_MIN = 45


def difficulty_class(score):
    return np.where(score < CLASS_EASY_MAX, "easy",
                    np.where(score < CLASS_DIFFICULT_MIN, "moderate", "difficult"))


def load_problem_counts():
    """WELL_ID -> number of formation intervals with a problem primary material."""
    f = gpd.read_file(GPKG, layer="formations")
    m1 = f["material1"].astype("string").str.upper().str.strip()
    hits = f.loc[m1.isin(PROBLEM_MATERIALS), "WELL_ID"]
    counts = hits.value_counts()
    print(f"  problem overburden: {counts.size:,} wells log >= 1 "
          f"boulders/stones/quicksand/hardpan primary layer")
    return counts


def load_flowing_ids():
    """WELL_IDs with a flowing-artesian pump test (flowing_rate_lpm > 0)."""
    pt = gpd.read_file(GPKG, layer="pump_tests")
    fr = pd.to_numeric(pt["flowing_rate_lpm"], errors="coerce")
    ids = set(pt.loc[fr > 0, "WELL_ID"])
    print(f"  artesian: {len(ids):,} wells with a flowing pump test")
    return ids


def load_methods():
    """WELL_ID -> decoded construction method (first recorded per well)."""
    if not METHOD_CSV.exists() or not METHOD_CODE_CSV.exists():
        return None
    codes = pd.read_csv(METHOD_CODE_CSV, dtype=str).set_index("CODE")["DES"]
    m = pd.read_csv(METHOD_CSV, dtype=str).dropna(subset=["METHOD_CONSTRUCTION_CODE"])
    m["method"] = m["METHOD_CONSTRUCTION_CODE"].map(codes).fillna("Not Known")
    m["WELL_ID"] = m["WELL_ID"].astype(str).str.strip()
    return m.drop_duplicates("WELL_ID").set_index("WELL_ID")["method"]


def score_wells():
    problem = load_problem_counts()
    flowing = load_flowing_ids()

    w = gpd.read_file(GPKG, layer="wells")
    n_all = len(w)
    w = w[w.geometry.notna() & w["bedrock_depth_m"].notna()]
    w = w.cx[BBOX[0]:BBOX[2], BBOX[1]:BBOX[3]].copy()
    print(f"  scoring {len(w):,} wells (of {n_all:,}) with geometry + "
          f"known depth-to-bedrock, in bbox")
    w["WELL_ID"] = w["WELL_ID"].astype(str).str.strip()
    w = w.to_crs(CRS_METRIC)
    xy = np.column_stack([w.geometry.x, w.geometry.y])

    # --- component factors (0-1) ---
    ov_f = np.clip(w["bedrock_depth_m"].to_numpy(float) / OVERBURDEN_FULL_M, 0, 1)

    n_prob = w["WELL_ID"].map(problem).fillna(0).to_numpy(float)
    pr_f = np.clip(n_prob / PROBLEM_FULL_N, 0, 1)

    hd_f = w["lithology"].map(HARDNESS).fillna(HARDNESS_DEFAULT).to_numpy(float)

    is_flow = w["WELL_ID"].isin(flowing).to_numpy()
    wtree = cKDTree(xy)
    nbrs = wtree.query_ball_point(xy, ARTESIAN_RADIUS_M)
    share = np.array([is_flow[nb].mean() if nb else 0.0 for nb in nbrs])
    ar_f = np.clip(share / ARTESIAN_FULL_SHARE, 0, 1)

    # --- component points ---
    ov = W_OVERBURDEN * ov_f
    pr = W_PROBLEM * pr_f
    hd = W_HARDNESS * hd_f
    ar = W_ARTESIAN * ar_f
    score = ov + pr + hd + ar

    w["ov"], w["pr"], w["hd"], w["ar"] = ov, pr, hd, ar
    w["score"] = score
    print(f"  per-well score: min {score.min():.0f}  median "
          f"{np.median(score):.0f}  mean {score.mean():.1f}  max {score.max():.0f}")
    return w, xy


def validate(w):
    """Three sanity checks the prompt asks for, printed before gridding."""
    print("\n== Validation (pre-gridding) ==")
    cls = pd.Series(difficulty_class(w["score"].to_numpy()), index=w.index)

    # (a) class vs decoded construction method
    methods = load_methods()
    if methods is not None:
        mm = w["WELL_ID"].map(methods)
        ct = pd.crosstab(cls, mm, normalize="index").mul(100).round(1)
        # keep the columns that actually matter for the hard-rock signal
        cols = [c for c in ["Cable Tool", "Air Percussion", "Rotary (Air)",
                            "Diamond", "Rotary (Convent.)", "Boring"]
                if c in ct.columns]
        ct = ct.reindex(columns=cols)
        print("\n(a) construction method by difficulty class (row %):")
        print(ct.reindex(["easy", "moderate", "difficult"]).to_string())
        print("    expect: difficult -> air-percussion / rotary-air / diamond;"
              " easy -> cable-tool")

    # (b) score vs total depth
    d = pd.to_numeric(w["depth_m"], errors="coerce")
    ok = d.notna()
    pear = np.corrcoef(w.loc[ok, "score"], d[ok])[0, 1]
    spear = pd.Series(w.loc[ok, "score"].to_numpy()).corr(
        pd.Series(d[ok].to_numpy()), method="spearman")
    print(f"\n(b) score vs total depth (n={ok.sum():,}): "
          f"Pearson {pear:.2f}, Spearman {spear:.2f}")
    print("    expect: positive (deeper wells cost more; overburden & hard rock"
          " both add metres)")

    # (c) spatial pattern -- mean score + dominant driver over west/central/east
    lon = w.to_crs(4326).geometry.x
    band = pd.cut(lon, bins=[-76.36, -75.97, -75.61, -75.24],
                  labels=["west (Shield edge)", "central", "east (clay plain)"])
    comp = w[["ov", "pr", "hd", "ar"]].rename(
        columns=dict(zip(["ov", "pr", "hd", "ar"], COMPONENTS)))
    print("\n(c) mean score & mean component points by longitude band:")
    g = comp.assign(score=w["score"], band=band.values).groupby("band", observed=True)
    print(g[["score"] + COMPONENTS].mean().round(1).to_string())
    print("    expect: east clay plain overburden-driven; west Shield edge"
          " hardness-driven")


def grid(w, xy):
    print("\n== Gridding ==")
    centers, xs, ys, shape = make_grid(w.total_bounds)
    print(f"  grid: {len(xs)} x {len(ys)} = {len(centers):,} candidate cells")
    tree, dist, idx, near, wt = idw_weights(xy, centers)

    ov = estimate(w["ov"].to_numpy(), idx, wt)[near]
    pr = estimate(w["pr"].to_numpy(), idx, wt)[near]
    hd = estimate(w["hd"].to_numpy(), idx, wt)[near]
    ar = estimate(w["ar"].to_numpy(), idx, wt)[near]
    n_near = count_within(tree, centers[near], CONF_DIST_M)

    raw = ov + pr + hd + ar
    score = np.clip(np.round(raw / 5.0) * 5.0, 0, 100).astype(int)
    cls = difficulty_class(score)
    driver = np.array(COMPONENTS)[np.argmax(np.column_stack([ov, pr, hd, ar]), axis=1)]

    cells = [box(x - CELL_M / 2, y - CELL_M / 2, x + CELL_M / 2, y + CELL_M / 2)
             for (x, y) in centers[near]]
    gdf = gpd.GeoDataFrame({
        "difficulty_score": score,
        "difficulty_class": cls,
        "driver": driver,
        "overburden_pts": np.round(ov).astype(int),
        "problem_pts": np.round(pr).astype(int),
        "hardness_pts": np.round(hd).astype(int),
        "artesian_pts": np.round(ar).astype(int),
        "n_wells": n_near,
        "confidence": np.where(n_near >= CONF_MIN_WELLS, "high", "low"),
    }, geometry=cells, crs=CRS_METRIC).to_crs(4326)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    gdf.to_file(OUT, driver="GeoJSON")

    print(f"  kept {len(gdf):,} cells with a well within {MASK_DIST_M} m")
    print("  class:", pd.Series(cls).value_counts().reindex(
        ["easy", "moderate", "difficult"]).to_dict())
    print("  dominant driver:", pd.Series(driver).value_counts().to_dict())
    print(f"  score range: {score.min()} - {score.max()} (rounded to 5)")
    print(f"  confidence: {pd.Series(gdf['confidence']).value_counts().to_dict()}")
    print(f"  wrote {OUT}")


def main():
    print("== Scoring wells ==")
    w, xy = score_wells()
    validate(w)
    grid(w, xy)


if __name__ == "__main__":
    main()
