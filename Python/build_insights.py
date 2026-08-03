"""
build_insights.py

Offline precompute for the Retrofit Insights national "big picture" page
(retrofit-insights.html, ROADMAP.md item 13, Phase 1). Reads the row-level
ERS matched-pair parquets and the three static context layers, and writes a
compact set of national/stratified JSON files that the page fetches lazily.

INPUTS
  C:\\ERS\\web\\ers_web_<PROV>.parquet   matched before/after audit pairs — the
        SAME rows retrofits.html serves (1,369,305 rows across 12 provinces/
        territories). Pre-dictionary-encoding: categorical cols are strings.
        Many numeric cols (FloorArea, YearBuilt, Pre_Electricity, insulation)
        are stored as strings; coerced with pd.to_numeric here.
  C:\\ERS\\web\\fsa_audit_totals.json    audit composition incl. UNMATCHED
        homes (build_fsa_audit_totals.py). by_fsa[PROV][FSA] = {t,de,d,e,nc};
        the audited count used here is dore = de+d+e (homes with any initial-D
        or follow-up-E audit), matching split_fsa_json.py's dore_count.
  census_json/fsa_census.json            2021 Census Profile per FSA, incl. the
        Phase-0 income group (median_total_income, median_after_tax_income,
        pct_low_income_lim_at, average_household_size) and owner_stats
        (median_dwelling_value) and period_of_construction bands.
  climate_json/fsa_climate.json          per-FSA HDD/CDD base-18 degC from ECCC
        climate normals (build_fsa_climate.py).

OUTPUTS  insights_json/ (compact, ensure_ascii=False, separators=(',',':')):
  fsa_metrics.json   one record per FSA with matched/audited counts,
                     participation, savings, EUI, GHG, HP/deep/fuel-switch
                     rates, measure-mix shares, climate, income quintile,
                     dwelling value, pre-1980 share. n included for thresholds.
  success.json       national stratified "what worked" analysis (bundles,
                     measure count, vintage x HDD, top-decile vs rest).
  climate.json       HDD-band and CDD-band aggregates.
  equity.json        income-quintile and dwelling-value-quintile aggregates.
  opportunity.json   missed-opportunity composite ranking + per-FSA factors.
  timeline.json      national + per-province audits/yr (D and E) + matched
                     retrofits by E-year, with cited program-era annotations.
  ghg_impact.json    national + per-province avg/total modelled GHG saved
                     (tCO2e/yr), priced two ways (2024 federal carbon-tax rate,
                     ECCC 2024 Social Cost of Carbon) — see CARBON_TAX_RATE /
                     SCC_RATE below for citations.
  meta.json          sources, build date, thresholds, formulas, band defs.

HONESTY RAILS baked into the numbers (each also stated on-page, ROADMAP item
13): savings are MODELLED EnerGuide estimates, not measured bills; negative
savings are dominated by audit noise (zero-measure pairs — reported but
excluded from "what worked"); participation mixes ~20 years of cumulative
audits over a single 2021 dwelling snapshot, so it is suppressed entirely
where the denominator can't carry the ratio (MIN_DWELLINGS_FOR_PARTICIPATION)
and is relative, not absolute, everywhere else; FSA income
correlations are ECOLOGICAL (rich FSA != rich participant); ERS is
self-selected, not a random sample.

REFRESH ORDER: runs AFTER ers_web_pipeline.py (parquets) and
build_fsa_audit_totals.py (audit sidecar); independent of split_fsa_json.py
and precompute_province_stats.py. The census + climate inputs are STATIC
(2021 Census / climate normals) and do NOT join the refresh cadence.

Conventions (bin/flag helpers, categorical normalization) mirror
precompute_province_stats.py and split_fsa_json.py — see those files.
"""

import os
import glob
import json
import math
import bisect
import datetime
from pathlib import Path
from collections import Counter, defaultdict

import pandas as pd
import numpy as np

# =============================================================================
# CONFIG
# =============================================================================

ERS_DIR = r"C:\ERS\web"
AUDIT_TOTALS_PATH = os.path.join(ERS_DIR, "fsa_audit_totals.json")

REPO_ROOT = Path(__file__).resolve().parent.parent
CENSUS_PATH = REPO_ROOT / "census_json" / "fsa_census.json"
CLIMATE_PATH = REPO_ROOT / "climate_json" / "fsa_climate.json"
FSA_INDEX_DIR = os.path.join(ERS_DIR, "fsa_json")       # for validation only
OUT_DIR = REPO_ROOT / "insights_json"

BUILD_DATE = datetime.date.today().isoformat()

# Minimum matched pairs before an FSA appears on leaderboards / the opportunity
# ranking, so tiny-n FSAs don't dominate. fsa_metrics.json keeps ALL FSAs
# (with n) so the page can threshold differently if it wants.
MIN_N = 30

# Minimum 2021 census dwellings before participation is reported at all.
#
# Participation divides ~20 years of cumulative audits (numerator, carrying the
# FSA code in force at audit time) by a single 2021 dwelling snapshot
# (denominator). Where Canada Post redrew or largely retired an FSA, two decades
# of audits accumulate under a code whose 2021 remnant is tiny, and the ratio
# becomes meaningless rather than merely noisy — L0N ON reported 94.5% (845
# audits / 894 dwellings) and L4V ON 1400% (14 / 1). StatCan's numbers are
# correct in both cases; the two sides just describe different geographies.
#
# 1,000 is chosen to cut that structurally-broken tail (80 FSAs, ~5.8k pairs,
# 0.4% of matched retrofits) without suppressing the genuinely high uptake in
# Nova Scotia and New Brunswick, where long-running provincial programs put
# real participation in the 40-47% band. Suppressed FSAs get participation=None,
# which also drops them from the opportunity ranking (see build_opportunity).
MIN_DWELLINGS_FOR_PARTICIPATION = 1000

# The 8 measure flags (same set + order as precompute_province_stats.MEASURES).
# key -> short label used in bundle strings and the success payload.
MEASURES = [
    ("Air_Tightness_Upgrade",         "Air sealing"),
    ("Roof_Insulation_Upgrade",       "Roof"),
    ("Foundation_Insulation_Upgrade", "Foundation"),
    ("Wall_Insulation_Upgrade",       "Wall"),
    ("HeatPump_Addition",             "Heat pump"),
    ("Heating_Change",                "Heating system"),
    ("Windows_Change",                "Windows"),
    ("Floor_Insulation_Upgrade",      "Floor"),
]
MEASURE_KEYS = [k for k, _ in MEASURES]
MEASURE_LABEL = dict(MEASURES)

# Columns pulled from each parquet (a trimmed national frame is concatenated
# from these; keeps memory ~a few hundred MB for all 1.37M rows).
READ_COLS = (
    ["FSA", "EnergySavingPct", "FloorArea", "YearBuilt",
     "Pre_TotalEnergy", "Post_TotalEnergy", "Pre_GHG", "Post_GHG",
     "Pre_GHG_current", "Post_GHG_current",
     "Pre_GHG_current_corrected", "Post_GHG_current_corrected",
     "Pre_GHG_as_audited", "Post_GHG_as_audited",
     "Pre_Date", "Post_Date", "Deep_Retrofit", "FuelSwitch"]
    + MEASURE_KEYS
)

# ---- band definitions (documented in meta.json) ----
# HDD base-18 degC annual. Bands span mild coastal (Victoria/Vancouver) to cold
# prairie/northern stock. CDD base-18 degC is small in Canada.
HDD_BANDS = [
    ("< 3500",      -math.inf, 3500),
    ("3500–4500",   3500,      4500),
    ("4500–5500",   4500,      5500),
    ("5500–6500",   5500,      6500),
    ("≥ 6500",      6500,      math.inf),
]
CDD_BANDS = [
    ("< 100",    -math.inf, 100),
    ("100–200",  100,       200),
    ("200–350",  200,       350),
    ("≥ 350",    350,       math.inf),
]
# Dwelling vintage from YearBuilt (year the home was built).
VINTAGE_BANDS = [
    ("pre-1946", -math.inf, 1946),
    ("1946–1960", 1946,     1961),
    ("1961–1980", 1961,     1981),
    ("1981–2000", 1981,     2001),
    ("2001+",     2001,     math.inf),
]

QUINTILE_LABELS = ["Q1 (lowest)", "Q2", "Q3", "Q4", "Q5 (highest)"]

# §GHG impact — two ways of pricing the same modelled tCO2e/yr saved.
# CARBON_TAX_RATE: federal fuel charge / OBPS benchmark price for 2024 ($/tCO2e,
# nominal). The last full year before the federal consumer fuel charge was
# removed 2025-04-01 — applied as a single flat rate to every matched pair
# regardless of its own audit year, so this is illustrative, not a
# reconstruction of the phased $20 (2019) -> $80 (2024) schedule.
CARBON_TAX_RATE = 80.0
# SCC_RATE: ECCC's Social Cost of Carbon (SC-CO2), 2024 estimate, C$2021,
# 2% near-term Ramsey discount rate — the central/recommended rate in
# ECCC, "Social Cost of Greenhouse Gas Estimates - Interim Updated Guidance"
# (Table 1): canada.ca/en/environment-climate-change/services/climate-change/
# science-research-data/social-cost-ghg.html
SCC_RATE = 266.0


# =============================================================================
# small helpers
# =============================================================================

def num(s):
    return pd.to_numeric(s, errors="coerce")


def med(arr):
    """statistical median, None if empty/all-NaN."""
    a = np.asarray(arr, dtype=float)
    a = a[~np.isnan(a)]
    return float(np.median(a)) if a.size else None


def r1(x):
    return None if x is None or (isinstance(x, float) and math.isnan(x)) else round(x, 1)


def r0(x):
    return None if x is None or (isinstance(x, float) and math.isnan(x)) else round(x)


def r3(x):
    return None if x is None or (isinstance(x, float) and math.isnan(x)) else round(x, 3)


def band_of(value, bands):
    """Return the label of the first band whose [lo, hi) contains value; None if NaN."""
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    for label, lo, hi in bands:
        if lo <= value < hi:
            return label
    return None


def weighted_quintile_cuts(pairs):
    """
    Dwelling-weighted quintile cut points. pairs: iterable of (value, weight).
    Sort by value, accumulate weight, return the 4 value thresholds at the
    20/40/60/80% cumulative-weight marks. Assign a value v to quintile q
    (1..5) with bisect against these cuts.
    """
    pairs = [(float(v), float(w)) for v, w in pairs
             if v is not None and not (isinstance(v, float) and math.isnan(v))
             and w and w > 0]
    if not pairs:
        return None
    pairs.sort(key=lambda p: p[0])
    total = sum(w for _, w in pairs)
    cuts, targets, ti = [], [0.2, 0.4, 0.6, 0.8], 0
    cum = 0.0
    for v, w in pairs:
        cum += w
        while ti < len(targets) and cum >= targets[ti] * total:
            cuts.append(v)
            ti += 1
    while len(cuts) < 4:                      # degenerate: <5 distinct weighted groups
        cuts.append(pairs[-1][0])
    return cuts


def quintile_of(value, cuts):
    """1..5 for value given 4 cut points, or None."""
    if value is None or (isinstance(value, float) and math.isnan(value)) or cuts is None:
        return None
    return bisect.bisect_right(cuts, float(value)) + 1


def pctile_rank(series):
    """0..1 percentile rank of each value among non-null values (ties -> average)."""
    return series.rank(pct=True, method="average")


# =============================================================================
# load static context layers
# =============================================================================

def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def census_derived(census):
    """
    Per-FSA scalars used across the outputs:
      total_dwellings, median_income (median_total_income),
      median_dwelling_value, pre_1980_share (fraction of period-of-construction
      dwellings built 1980 or earlier).
    """
    out = {}
    for fsa, rec in census.items():
        poc = rec.get("period_of_construction") or {}
        poc_vals = [v for v in poc.values() if isinstance(v, (int, float))]
        poc_sum = sum(poc_vals) if poc_vals else 0
        pre80 = 0
        for k in ("1960_or_before", "1961_1980"):
            v = poc.get(k)
            if isinstance(v, (int, float)):
                pre80 += v
        pre_1980_share = (pre80 / poc_sum) if poc_sum else None
        inc = rec.get("income") or {}
        own = rec.get("owner_stats") or {}
        out[fsa] = {
            "total_dwellings": rec.get("total_dwellings"),
            "median_income": inc.get("median_total_income"),
            "median_after_tax_income": inc.get("median_after_tax_income"),
            "pct_low_income": inc.get("pct_low_income_lim_at"),
            "median_dwelling_value": own.get("median_dwelling_value"),
            "pre_1980_share": pre_1980_share,
        }
    return out


# =============================================================================
# read + trim one province parquet into the national frame
# =============================================================================

def load_province_frame(parquet_path):
    prov = Path(parquet_path).stem.replace("ers_web_", "")
    cols = [c for c in READ_COLS if c]
    df = pd.read_parquet(parquet_path, columns=cols)
    df["PROV"] = prov
    df["FSA"] = df["FSA"].astype(str).str.strip().str.upper()

    # numeric coercions (several source cols are strings)
    df["saving_pct"] = num(df["EnergySavingPct"]) * 100.0
    area = num(df["FloorArea"])
    year = num(df["YearBuilt"])
    pre_e = num(df["Pre_TotalEnergy"])
    post_e = num(df["Post_TotalEnergy"])
    df["YearBuiltNum"] = year
    valid_area = area.notna() & (area > 0)
    df["pre_eui"] = np.where(valid_area & pre_e.notna(), pre_e / area, np.nan)
    df["post_eui"] = np.where(valid_area & post_e.notna(), post_e / area, np.nan)
    df["ghg_pre"] = num(df["Pre_GHG"])
    df["ghg_post"] = num(df["Post_GHG"])
    df["ghg_pre_current"] = num(df["Pre_GHG_current"])
    df["ghg_post_current"] = num(df["Post_GHG_current"])
    df["ghg_pre_current_corrected"] = num(df["Pre_GHG_current_corrected"])
    df["ghg_post_current_corrected"] = num(df["Post_GHG_current_corrected"])
    df["ghg_pre_as_audited"] = num(df["Pre_GHG_as_audited"])
    df["ghg_post_as_audited"] = num(df["Post_GHG_as_audited"])

    for k in MEASURE_KEYS + ["Deep_Retrofit", "FuelSwitch"]:
        df[k] = df[k].astype(bool)
    df["n_measures"] = df[MEASURE_KEYS].sum(axis=1).astype(int)

    df["d_year"] = pd.to_datetime(df["Pre_Date"], errors="coerce").dt.year
    df["e_year"] = pd.to_datetime(df["Post_Date"], errors="coerce").dt.year

    keep = (["FSA", "PROV", "saving_pct", "pre_eui", "post_eui",
             "ghg_pre", "ghg_post",
             "ghg_pre_current", "ghg_post_current",
             "ghg_pre_current_corrected", "ghg_post_current_corrected",
             "ghg_pre_as_audited", "ghg_post_as_audited",
             "YearBuiltNum", "n_measures",
             "d_year", "e_year", "Deep_Retrofit", "FuelSwitch"] + MEASURE_KEYS)
    return prov, df[keep]


# =============================================================================
# per-FSA metrics
# =============================================================================

def participation_or_none(audited, dwellings):
    """
    Participation (audited homes / 2021 census dwellings), or None when the
    denominator can't carry the ratio. See MIN_DWELLINGS_FOR_PARTICIPATION.

    Returns (value, suppressed_reason). suppressed_reason is None when the value
    is reported, otherwise a short code the frontend can show instead of a rate:
      "no_census"    FSA code absent from the 2021 census (retired/changed code)
      "tiny_area"    fewer than MIN_DWELLINGS_FOR_PARTICIPATION dwellings
      "impossible"   ratio > 1.0; defensive, tiny_area should catch these first
    """
    if not audited or not dwellings:
        return None, "no_census"
    if dwellings < MIN_DWELLINGS_FOR_PARTICIPATION:
        return None, "tiny_area"
    value = audited / dwellings
    if value > 1.0:
        return None, "impossible"
    return value, None


def build_fsa_metrics(nat, by_fsa_audit, cdrv, climate, income_q, dv_q):
    """One record per FSA present in the matched data."""
    records = {}
    g = nat.groupby("FSA", sort=True)

    for fsa, grp in g:
        prov = grp["PROV"].iloc[0]
        n = len(grp)
        audited = None
        cell = by_fsa_audit.get(prov, {}).get(fsa)
        if cell:
            audited = cell["de"] + cell["d"] + cell["e"]
        cd = cdrv.get(fsa, {})
        dwellings = cd.get("total_dwellings")
        participation, part_suppressed = participation_or_none(audited, dwellings)
        matched_retrofit_rate = (n / audited) if audited else None

        shares = {MEASURE_LABEL[k]: r3(float(grp[k].mean())) for k in MEASURE_KEYS}
        clim = climate.get(fsa, {})

        records[fsa] = {
            "fsa": fsa,
            "prov": prov,
            "n": n,
            "audited": audited,
            "participation": r3(participation),
            "participation_suppressed": part_suppressed,
            "matched_retrofit_rate": r3(matched_retrofit_rate),
            "median_saving_pct": r1(med(grp["saving_pct"])),
            "eui_pre_median": r0(med(grp["pre_eui"])),
            "eui_post_median": r0(med(grp["post_eui"])),
            "ghg_pre_median": r1(med(grp["ghg_pre"])),
            "ghg_post_median": r1(med(grp["ghg_post"])),
            "hp_rate": r3(float(grp["HeatPump_Addition"].mean())),
            "deep_rate": r3(float(grp["Deep_Retrofit"].mean())),
            "fuel_switch_rate": r3(float(grp["FuelSwitch"].mean())),
            "measure_shares": shares,
            "hdd": clim.get("hdd"),
            "cdd": clim.get("cdd"),
            "income_q": income_q.get(fsa),
            "median_income": cd.get("median_income"),
            "median_dwelling_value": cd.get("median_dwelling_value"),
            "pre_1980_share": r3(cd.get("pre_1980_share")),
        }
    return records


# =============================================================================
# success.json — national stratified "what worked"
# =============================================================================

def build_success(nat):
    out = {}
    nz = nat[nat["n_measures"] > 0]
    out["zero_measure_count"] = int((nat["n_measures"] == 0).sum())
    out["nonzero_count"] = int(len(nz))
    out["total_count"] = int(len(nat))

    # (a) savings distribution by measure bundle — top 15 combos of the 8 flags
    #     among nonzero-measure pairs.
    bundle_key = nz[MEASURE_KEYS].apply(
        lambda r: tuple(k for k in MEASURE_KEYS if r[k]), axis=1)
    nz = nz.assign(_bundle=bundle_key)
    counts = Counter(nz["_bundle"])
    top = counts.most_common(15)
    bundles = []
    for combo, cnt in top:
        sub = nz[nz["_bundle"] == combo]
        bundles.append({
            "measures": [MEASURE_LABEL[k] for k in combo],
            "n_measures": len(combo),
            "n": int(cnt),
            "median_saving_pct": r1(med(sub["saving_pct"])),
            "median_pre_eui": r0(med(sub["pre_eui"])),
        })
    out["bundles"] = bundles

    # (b) median savings vs number of measures 0..8 (0 kept for context: it is
    #     the audit-noise population — flagged, not part of "what worked").
    by_count = []
    for c in range(0, 9):
        sub = nat[nat["n_measures"] == c]
        by_count.append({
            "n_measures": c,
            "n": int(len(sub)),
            "median_saving_pct": r1(med(sub["saving_pct"])),
            "audit_noise": c == 0,
        })
    out["by_measure_count"] = by_count

    # (c) savings by vintage band x HDD band (nonzero-measure pairs).
    nz2 = nz.copy()
    nz2["vintage"] = nz2["YearBuiltNum"].map(lambda v: band_of(v, VINTAGE_BANDS))
    nz2["hdd_band"] = nz2["hdd"].map(lambda v: band_of(v, HDD_BANDS)) if "hdd" in nz2 else None
    matrix = []
    for vlabel, _, _ in VINTAGE_BANDS:
        for hlabel, _, _ in HDD_BANDS:
            sub = nz2[(nz2["vintage"] == vlabel) & (nz2["hdd_band"] == hlabel)]
            if len(sub) == 0:
                continue
            matrix.append({
                "vintage": vlabel, "hdd_band": hlabel, "n": int(len(sub)),
                "median_saving_pct": r1(med(sub["saving_pct"])),
                "median_pre_eui": r0(med(sub["pre_eui"])),
            })
    out["vintage_x_hdd"] = matrix

    # (d) top-decile savers vs the rest (nonzero-measure pairs).
    sv = nz["saving_pct"].dropna()
    thr = float(np.percentile(sv, 90)) if len(sv) else None
    out["top_decile_threshold_pct"] = r1(thr)

    def profile(sub):
        yrs = sub["YearBuiltNum"].dropna()
        return {
            "n": int(len(sub)),
            "measure_prevalence": {MEASURE_LABEL[k]: r3(float(sub[k].mean())) for k in MEASURE_KEYS},
            "median_pre_eui": r0(med(sub["pre_eui"])),
            "median_year_built": r0(med(yrs)) if len(yrs) else None,
            "pre_1980_share": r3(float((yrs < 1980).mean())) if len(yrs) else None,
            "fuel_switch_share": r3(float(sub["FuelSwitch"].mean())),
            "mean_measure_count": r1(float(sub["n_measures"].mean())),
            "median_saving_pct": r1(med(sub["saving_pct"])),
        }

    if thr is not None:
        top_sub = nz[nz["saving_pct"] >= thr]
        rest_sub = nz[nz["saving_pct"] < thr]
        out["top_decile"] = profile(top_sub)
        out["rest"] = profile(rest_sub)
    return out


# =============================================================================
# climate.json — HDD-band + CDD-band aggregates
# =============================================================================

def _band_aggregate(nat, col, bands):
    rows = []
    tmp = nat.copy()
    tmp["_band"] = tmp[col].map(lambda v: band_of(v, bands))
    for label, _, _ in bands:
        sub = tmp[tmp["_band"] == label]
        if len(sub) == 0:
            rows.append({"band": label, "n": 0})
            continue
        nz = sub[sub["n_measures"] > 0]
        shares = {MEASURE_LABEL[k]: r3(float(sub[k].mean())) for k in MEASURE_KEYS}
        rows.append({
            "band": label,
            "n": int(len(sub)),
            "median_pre_eui": r0(med(sub["pre_eui"])),
            "median_saving_pct": r1(med(nz["saving_pct"])),   # nonzero-measure
            "hp_rate": r3(float(sub["HeatPump_Addition"].mean())),
            "fuel_switch_rate": r3(float(sub["FuelSwitch"].mean())),
            "deep_rate": r3(float(sub["Deep_Retrofit"].mean())),
            "measure_shares": shares,
        })
    return rows


def build_climate(nat):
    return {
        "note": "median_saving_pct is over nonzero-measure pairs; other rates over all matched pairs in the band.",
        "hdd_bands": _band_aggregate(nat, "hdd", HDD_BANDS),
        "cdd_bands": _band_aggregate(nat, "cdd", CDD_BANDS),
    }


# =============================================================================
# equity.json — income + dwelling-value quintile aggregates
# =============================================================================

def _quintile_aggregate(nat, qcol, fsa_audit_dwellings):
    """
    qcol: per-row quintile 1..5 (already joined onto nat).
    fsa_audit_dwellings: {fsa: (audited, dwellings, q)} for participation, which
    must aggregate audited/dwellings at the FSA level (row-level would double
    count). Participation per quintile = sum(audited) / sum(dwellings) over
    FSAs in that quintile.
    """
    # participation from FSA-level audited/dwellings grouped by that FSA's quintile
    part_num = defaultdict(float)
    part_den = defaultdict(float)
    for fsa, (audited, dwellings, q) in fsa_audit_dwellings.items():
        if q is None or audited is None or not dwellings:
            continue
        part_num[q] += audited
        part_den[q] += dwellings

    rows = []
    for q in range(1, 6):
        sub = nat[nat[qcol] == q]
        nz = sub[sub["n_measures"] > 0]
        part = (part_num[q] / part_den[q]) if part_den[q] else None
        rows.append({
            "quintile": q,
            "label": QUINTILE_LABELS[q - 1],
            "n": int(len(sub)),
            "participation": r3(part),
            "median_saving_pct": r1(med(nz["saving_pct"])),
            "hp_rate": r3(float(sub["HeatPump_Addition"].mean())) if len(sub) else None,
            "deep_rate": r3(float(sub["Deep_Retrofit"].mean())) if len(sub) else None,
            "fuel_switch_rate": r3(float(sub["FuelSwitch"].mean())) if len(sub) else None,
            "median_pre_eui": r0(med(sub["pre_eui"])),
        })
    return rows


def build_equity(nat, income_cuts, dv_cuts, income_fad, dv_fad):
    return {
        "note": ("Ecological, not household-level: an FSA's income quintile "
                 "describes the neighbourhood, not the individual participants. "
                 "median_saving_pct over nonzero-measure pairs; participation = "
                 "sum(audited)/sum(dwellings) over FSAs in the quintile."),
        "income_quintiles": {
            "cut_points": [r0(c) for c in income_cuts] if income_cuts else None,
            "metric": "median_total_household_income_2020",
            "rows": _quintile_aggregate(nat, "income_q", income_fad),
        },
        "dwelling_value_quintiles": {
            "cut_points": [r0(c) for c in dv_cuts] if dv_cuts else None,
            "metric": "median_dwelling_value_2021",
            "rows": _quintile_aggregate(nat, "dv_q", dv_fad),
        },
    }


# =============================================================================
# opportunity.json — missed-opportunity composite ranking
# =============================================================================

# Composite weights (documented on-page). Each factor is percentile-ranked
# 0..1 across eligible FSAs (n >= MIN_N and has census); "low participation"
# uses (1 - participation percentile). Score = 100 * weighted sum, so higher =
# worse stock AND lower uptake = higher priority for programs to look next.
# Expressed on the same ordinal scale the page's priority controls use
# (Off/Low/Medium/High = 0/1/2/3, normalised to sum 1), so the shipped default
# is reproducible from the UI rather than being a weighting the reader cannot
# reach. High EUI / Medium GHG / Low age / Medium participation = 3/2/1/2.
# The previous 0.30/0.25/0.20/0.25 was not expressible on that scale; the two
# rank 18 of the same top 20, same #1, median shift 22 places out of 1,509.
OPP_WEIGHTS = {
    "pre_eui": 0.375,         # High   — worst-performing stock (high pre-retrofit EUI)
    "pre_ghg": 0.25,          # Medium — highest emissions
    "pre_1980_share": 0.125,  # Low    — oldest housing
    "low_participation": 0.25,  # Medium — least program uptake so far
    "low_income": 0.0,        # Off    — lowest-income neighbourhoods; see note below
}

# low_income ships at weight 0, so the default ranking is exactly what it was
# before the factor existed. It is emitted per FSA regardless, because the page
# lets the reader re-weight all five factors live and re-sort the table (the
# stored percentiles are the whole input to that; nothing is recomputed server
# side). Unlike the income lens in the equity section, weighting an AREA's
# income to decide where a PROGRAM should look is an area-level decision about
# areas, which is what this data supports.


def build_opportunity(metrics):
    elig = []
    for fsa, m in metrics.items():
        if m["n"] < MIN_N:
            continue
        if (m["eui_pre_median"] is None or m["ghg_pre_median"] is None
                or m["pre_1980_share"] is None or m["participation"] is None):
            continue
        elig.append(m)
    if not elig:
        return {"weights": OPP_WEIGHTS, "min_n": MIN_N, "n_fsas": 0, "ranking": []}

    df = pd.DataFrame([{
        "fsa": m["fsa"], "prov": m["prov"], "n": m["n"],
        "pre_eui": m["eui_pre_median"], "pre_ghg": m["ghg_pre_median"],
        "pre_1980_share": m["pre_1980_share"], "participation": m["participation"],
        "median_income": m["median_income"],
    } for m in elig])

    df["f_pre_eui"] = pctile_rank(df["pre_eui"])
    df["f_pre_ghg"] = pctile_rank(df["pre_ghg"])
    df["f_pre_1980"] = pctile_rank(df["pre_1980_share"])
    df["f_low_part"] = 1.0 - pctile_rank(df["participation"])
    df["f_low_income"] = 1.0 - pctile_rank(df["median_income"])

    df["score"] = 100.0 * (
        OPP_WEIGHTS["pre_eui"] * df["f_pre_eui"]
        + OPP_WEIGHTS["pre_ghg"] * df["f_pre_ghg"]
        + OPP_WEIGHTS["pre_1980_share"] * df["f_pre_1980"]
        + OPP_WEIGHTS["low_participation"] * df["f_low_part"]
        + OPP_WEIGHTS["low_income"] * df["f_low_income"]
    )
    df = df.sort_values("score", ascending=False)

    ranking = []
    for _, r in df.iterrows():
        ranking.append({
            "fsa": r["fsa"], "prov": r["prov"], "n": int(r["n"]),
            "score": round(float(r["score"]), 1),
            # 4dp, not 2: the page re-scores the ranking from THESE percentiles
            # when the reader re-weights, so coarse rounding would make the
            # default weighting disagree with the "score" stored right above.
            "factors": {
                "pre_eui": round(float(r["f_pre_eui"]), 4),
                "pre_ghg": round(float(r["f_pre_ghg"]), 4),
                "pre_1980_share": round(float(r["f_pre_1980"]), 4),
                "low_participation": round(float(r["f_low_part"]), 4),
                "low_income": round(float(r["f_low_income"]), 4),
            },
            "values": {
                "pre_eui": r0(float(r["pre_eui"])),
                "pre_ghg": r1(float(r["pre_ghg"])),
                "pre_1980_share": r3(float(r["pre_1980_share"])),
                "participation": r3(float(r["participation"])),
                "median_income": (None if pd.isna(r["median_income"])
                                  else int(r["median_income"])),
            },
        })
    return {
        "weights": OPP_WEIGHTS,
        "min_n": MIN_N,
        "formula": ("score = 100 * (0.375*pctile(pre_EUI) + 0.25*pctile(pre_GHG) "
                    "+ 0.125*pctile(pre-1980 share) + 0.25*(1 - pctile(participation)) "
                    "+ 0*pctile(low income)); each factor percentile-ranked across "
                    "eligible FSAs. Weights are reader-configurable on the page; "
                    "these are the shipped defaults."),
        "n_fsas": len(ranking),
        "ranking": ranking,
    }


# =============================================================================
# timeline.json — audits/yr (D and E) + matched retrofits by E-year
# =============================================================================

PROGRAM_ANNOTATIONS = [
    {
        "year_start": 1998, "year_end": 2007,
        "label": "EnerGuide for Houses — national home-energy rating launched Apr 1998 (retrofit incentive 2003–2006)",
        "source_url": "https://natural-resources.canada.ca/energy-efficiency/home-energy-efficiency/energy-efficiency-housing-initiatives",
    },
    {
        "year_start": 2007, "year_end": 2012,
        "label": "ecoENERGY Retrofit – Homes (Apr 2007 – Jun 2012; up to $5,000/home, pre + post audit required)",
        "source_url": "https://www.iea.org/policies/2259-ecoenergy-retrofit-homes",
    },
    {
        "year_start": 2021, "year_end": 2024,
        "label": "Canada Greener Homes Grant (launched May 2021; closed to new applicants 31 Mar 2024)",
        "source_url": "https://natural-resources.canada.ca/energy-efficiency/home-energy-efficiency/canada-greener-homes-initiative/closed-canada-greener-homes-grant-0",
    },
]


def build_timeline(nat):
    def year_hist(series):
        s = series.dropna().astype(int)
        s = s[(s >= 1990) & (s <= 2035)]
        return {int(k): int(v) for k, v in sorted(Counter(s).items())}

    national = {
        "d_year": year_hist(nat["d_year"]),          # initial (pre) audits
        "e_year": year_hist(nat["e_year"]),          # follow-up (post) audits
        "matched_by_e_year": year_hist(nat["e_year"]),  # matched retrofits dated by E
    }
    per_prov = {}
    for prov, grp in nat.groupby("PROV"):
        per_prov[prov] = {
            "d_year": year_hist(grp["d_year"]),
            "e_year": year_hist(grp["e_year"]),
            "matched_by_e_year": year_hist(grp["e_year"]),
        }
    return {
        "note": ("Matched-pair audits only (unmatched D-only / E-only homes are "
                 "not in the row-level data). Each matched pair contributes one "
                 "initial-D year and one follow-up-E year; matched_by_e_year "
                 "dates the completed retrofit by its post-audit."),
        "national": national,
        "by_province": per_prov,
        "annotations": PROGRAM_ANNOTATIONS,
    }


GHG_SCENARIO_COLS = {
    "reported": ("ghg_pre", "ghg_post"),
    "current": ("ghg_pre_current", "ghg_post_current"),
    "current_corrected": ("ghg_pre_current_corrected", "ghg_post_current_corrected"),
    "as_audited": ("ghg_pre_as_audited", "ghg_post_as_audited"),
}


def build_ghg_impact(nat):
    """
    Average + total GHG (tCO2e/yr) saved, nationally and per province, under
    4 scenarios (mirrors retrofits.html/precompute_province_stats.py — keep
    in sync):
      reported            raw ERSGHG. Only ~50.5% of matched pairs have it
                           (measured 2026-08-02; Quebec ~78%, Ontario ~43%,
                           Saskatchewan ~9%) — NOT scaled up to the full
                           matched count. matched_total/coverage_pct ship
                           alongside n so this is never hidden.
      current              flat 2026 official ECCC/OBPS factor, same for
                           every retrofit regardless of audit year.
      current_corrected    same, Alberta/Newfoundland use the ERS-calibrated
                           factor instead (see docs/ENERGUIDE_QUESTIONS.md
                           SS5.4 for why).
      as_audited            ERS-calibrated, matched to each home's own audit
                           year — the historically-accurate one, validated to
                           -0.66% national aggregate bias against reported
                           ERSGHG (measured 2026-08-02).
    current/current_corrected/as_audited are calculated by
    Python/compute_ghg_scenarios.py from each home's own fuel consumption
    (~100% coverage) — see that script and Python/ghg_factors.py.

    NET, not clipped: a home whose modelled GHG rose (common with an
    electric-heat-pump fuel switch in a high-emission-grid province) pulls the
    total down rather than being dropped — n_increased reports how many, so the
    total's sign is never a silent assumption.

    Two $ figures are the same tCO2e total priced two different ways — see
    CARBON_TAX_RATE / SCC_RATE for what each represents and cites.
    """
    def stats(grp, pre_col, post_col):
        matched_total = int(len(grp))
        d = (num(grp[pre_col]) - num(grp[post_col])).dropna()
        n = int(d.size)
        if n == 0:
            return None
        total = float(d.sum())
        return {
            "n": n,
            "matched_total": matched_total,
            "ghg_coverage_pct": r3(n / matched_total) if matched_total else None,
            "n_increased": int((d < 0).sum()),
            "avg_ghg_saved_tco2e": r1(total / n),
            "total_ghg_saved_tco2e": r0(total),
            "carbon_tax_value_cad": r0(total * CARBON_TAX_RATE),
            "scc_value_cad": r0(total * SCC_RATE),
        }

    scenarios = {}
    for scen, (pre_col, post_col) in GHG_SCENARIO_COLS.items():
        national = stats(nat, pre_col, post_col)
        by_province = {}
        for prov, grp in nat.groupby("PROV"):
            s = stats(grp, pre_col, post_col)
            if s:
                by_province[prov] = s
        scenarios[scen] = {"national": national, "by_province": by_province}

    return {
        "carbon_tax_rate": {
            "value": CARBON_TAX_RATE, "unit": "CAD/tCO2e", "year": 2024,
            "note": ("Federal fuel charge / OBPS benchmark price for 2024. Applied as a single flat "
                     "rate to every matched pair's saving regardless of its own audit year — the federal "
                     "consumer fuel charge was removed 2025-04-01, so this is illustrative, not a live charge "
                     "or a reconstruction of the phased $20 (2019) to $80 (2024) schedule."),
        },
        "scc_rate": {
            "value": SCC_RATE, "unit": "CAD2021/tCO2e", "year": 2024, "discount_rate": "2% near-term Ramsey",
            "source": ("ECCC, \"Social Cost of Greenhouse Gas Estimates - Interim Updated Guidance\", Table 1 "
                       "(SC-CO2, C$2021, 2% discount rate). https://www.canada.ca/en/environment-climate-change/"
                       "services/climate-change/science-research-data/social-cost-ghg.html"),
        },
        "scenarios": scenarios,
    }


# =============================================================================
# validation printouts
# =============================================================================

def load_index_median(prov, fsa):
    path = os.path.join(FSA_INDEX_DIR, prov, "_index.json")
    if not os.path.exists(path):
        return None
    for e in load_json(path):
        if e["fsa"] == fsa:
            return e
    return None


def validate(metrics, nat, prov_totals):
    print("\n" + "=" * 70)
    print("VALIDATION")
    print("=" * 70)

    # 1) national matched total == sum of province parquet rows == 1,369,305-era
    tot = len(nat)
    print(f"\nNational matched total: {tot:,}")
    by_prov = nat.groupby("PROV").size().to_dict()
    print("  by province: " + ", ".join(f"{p}={n:,}" for p, n in sorted(by_prov.items())))
    print(f"  sum check: {sum(by_prov.values()):,} (expect 1,369,305)")

    # 2) 3 known FSAs cross-checked vs fsa_json/_index.json
    print("\nfsa_metrics vs fsa_json/<PROV>/_index.json (median saving %):")
    print(f"  {'FSA':<6}{'prov':<5}{'n(mine)':>9}{'n(idx)':>9}"
          f"{'med%(mine)':>12}{'med%(idx*100)':>15}")
    for prov, fsa in [("ON", "L3R"), ("ON", "K2P"), ("ON", "M5V")]:
        m = metrics.get(fsa)
        idx = load_index_median(prov, fsa)
        if not m or not idx:
            print(f"  {fsa}: missing"); continue
        idx_med = round(idx["median_saving_pct"] * 100, 1) if idx["median_saving_pct"] is not None else None
        print(f"  {fsa:<6}{prov:<5}{m['n']:>9,}{idx['row_count']:>9,}"
              f"{str(m['median_saving_pct']):>12}{str(idx_med):>15}")

    # 3) leaderboard top-10s by each metric (min-n)
    elig = [m for m in metrics.values() if m["n"] >= MIN_N]
    def top(metric, rev=True, fmt=str):
        vals = [m for m in elig if m.get(metric) is not None]
        vals.sort(key=lambda m: m[metric], reverse=rev)
        return ", ".join(f"{m['fsa']}({fmt(m[metric])})" for m in vals[:10])
    print(f"\nLeaderboards (min n={MIN_N}, {len(elig)} eligible FSAs):")
    print("  Top participation:  ", top("participation"))
    print("  Top median saving%: ", top("median_saving_pct"))
    print("  Worst pre-EUI:      ", top("eui_pre_median"))
    print("  Worst pre-GHG:      ", top("ghg_pre_median"))
    print("  Top HP adoption:    ", top("hp_rate"))
    print("  Bottom participation:", top("participation", rev=False))


# =============================================================================
# main
# =============================================================================

def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    print("Loading static context layers...")
    census = load_json(CENSUS_PATH)
    climate = load_json(CLIMATE_PATH)
    audit = load_json(AUDIT_TOTALS_PATH)
    by_fsa_audit = audit.get("by_fsa", {})
    prov_totals = audit.get("by_province", {})
    cdrv = census_derived(census)
    print(f"  census: {len(census):,} FSAs | climate: {len(climate):,} FSAs "
          f"| audit by_fsa provinces: {len(by_fsa_audit)}")

    # ---- national dwelling-weighted quintile cut points (income + dwelling value) ----
    income_pairs = [(cd["median_income"], cd["total_dwellings"])
                    for cd in cdrv.values()
                    if cd["median_income"] and cd["total_dwellings"]]
    dv_pairs = [(cd["median_dwelling_value"], cd["total_dwellings"])
                for cd in cdrv.values()
                if cd["median_dwelling_value"] and cd["total_dwellings"]]
    income_cuts = weighted_quintile_cuts(income_pairs)
    dv_cuts = weighted_quintile_cuts(dv_pairs)
    income_q = {fsa: quintile_of(cd["median_income"], income_cuts) for fsa, cd in cdrv.items()}
    dv_q = {fsa: quintile_of(cd["median_dwelling_value"], dv_cuts) for fsa, cd in cdrv.items()}
    print(f"\nIncome quintile cut points (dwelling-weighted): "
          f"{[r0(c) for c in income_cuts] if income_cuts else None}")
    print(f"Dwelling-value quintile cut points (dwelling-weighted): "
          f"{[r0(c) for c in dv_cuts] if dv_cuts else None}")

    # ---- national dwelling-weighted median income vs StatCan sanity ----
    if income_pairs:
        ip = sorted(income_pairs)
        tw = sum(w for _, w in ip); cum = 0; natmed = None
        for v, w in ip:
            cum += w
            if cum >= 0.5 * tw:
                natmed = v; break
        print(f"National dwelling-weighted median household income: ~${natmed:,.0f} "
              f"(StatCan 2020 Canada median ~$84k before-tax)")

    # ---- read all parquets into one trimmed national frame ----
    parquet_files = sorted(glob.glob(os.path.join(ERS_DIR, "ers_web_*.parquet")))
    frames = []
    print("\nReading province parquets...")
    for pf in parquet_files:
        prov, fr = load_province_frame(pf)
        frames.append(fr)
        print(f"  {prov}: {len(fr):,} rows")
    nat = pd.concat(frames, ignore_index=True)
    print(f"  national frame: {len(nat):,} rows")

    # join per-FSA climate + quintiles onto the national frame (for stratified aggs)
    nat["hdd"] = nat["FSA"].map(lambda f: climate.get(f, {}).get("hdd"))
    nat["cdd"] = nat["FSA"].map(lambda f: climate.get(f, {}).get("cdd"))
    nat["income_q"] = nat["FSA"].map(income_q)
    nat["dv_q"] = nat["FSA"].map(dv_q)

    # ---- per-FSA metrics ----
    print("\nComputing per-FSA metrics...")
    metrics = build_fsa_metrics(nat, by_fsa_audit, cdrv, climate, income_q, dv_q)
    print(f"  {len(metrics):,} FSAs")

    # FSA-level (audited, dwellings, quintile) for participation-by-quintile.
    # FSAs whose participation was suppressed are left out entirely: a denominator
    # we won't divide by per-FSA is also one we shouldn't add into a quintile sum
    # (a tiny-remnant FSA contributes a full 20 years of audits against a 2021
    # remnant, inflating its quintile's numerator).
    income_fad = {}
    dv_fad = {}
    for fsa, m in metrics.items():
        if m["participation_suppressed"]:
            continue
        dwellings = cdrv.get(fsa, {}).get("total_dwellings")
        income_fad[fsa] = (m["audited"], dwellings, income_q.get(fsa))
        dv_fad[fsa] = (m["audited"], dwellings, dv_q.get(fsa))

    # ---- build the rest ----
    print("Building success / climate / equity / opportunity / timeline...")
    success = build_success(nat)
    climate_out = build_climate(nat)
    equity = build_equity(nat, income_cuts, dv_cuts, income_fad, dv_fad)
    opportunity = build_opportunity(metrics)
    timeline = build_timeline(nat)
    ghg_impact = build_ghg_impact(nat)

    # so the methodology section can state the suppression counts without
    # re-deriving them in the browser
    part_sup = Counter(m["participation_suppressed"] for m in metrics.values())

    meta = {
        "build_date": BUILD_DATE,
        "national_matched_total": int(len(nat)),
        "n_fsas_matched": len(metrics),
        "participation_coverage": {
            "reported": part_sup.get(None, 0),
            "suppressed_tiny_area": part_sup.get("tiny_area", 0),
            "suppressed_no_census": part_sup.get("no_census", 0),
            "suppressed_impossible": part_sup.get("impossible", 0),
        },
        "sources": {
            "ers_parquets": "C:/ERS/web/ers_web_<PROV>.parquet (matched before/after audit pairs; same rows retrofits.html serves)",
            "audit_totals": "C:/ERS/web/fsa_audit_totals.json (audit composition incl. unmatched; build_fsa_audit_totals.py)",
            "census": "census_json/fsa_census.json (2021 Census Profile FSA; static)",
            "climate": "climate_json/fsa_climate.json (ECCC climate normals HDD/CDD base 18C; static)",
        },
        "thresholds": {
            "min_n_leaderboard_and_opportunity": MIN_N,
            "min_dwellings_for_participation": MIN_DWELLINGS_FOR_PARTICIPATION,
            "top_decile_percentile": 90,
        },
        "definitions": {
            "matched_count": "rows in the matched-pair parquet for the FSA (a completed before/after retrofit pair)",
            "audited_count": "dore = de+d+e from fsa_audit_totals (homes with any initial-D or follow-up-E audit, matched or not)",
            "participation": (
                "audited / 2021-census total_dwellings. The numerator is ~20yr of cumulative audits "
                "carrying the FSA code in force at audit time; the denominator is a single 2021 snapshot. "
                f"Suppressed (null) where the FSA is absent from the 2021 census, has fewer than "
                f"{MIN_DWELLINGS_FOR_PARTICIPATION} dwellings, or the ratio exceeds 1.0 — see "
                "participation_suppressed for which. Read the reported values as RELATIVE, not absolute (honesty rail)"),
            "participation_suppressed": "null when participation is reported, else no_census | tiny_area | impossible",
            "matched_retrofit_rate": "matched_count / audited_count (share of an FSA's audited homes that became a completed matched pair)",
            "median_saving_pct": "median of EnergySavingPct*100 over the FSA's matched pairs (MODELLED EnerGuide estimate, not a measured bill)",
            "eui": "Pre/Post_TotalEnergy / FloorArea, kWh/m2/yr, area>0 only",
            "measure_shares": "share of the FSA's matched pairs carrying each of the 8 tracked measure flags",
            "income_quintile": "national dwelling-weighted quintile of median_total_income (Q1 lowest); ECOLOGICAL (neighbourhood, not participant)",
        },
        "bands": {
            "hdd": [b[0] for b in HDD_BANDS],
            "cdd": [b[0] for b in CDD_BANDS],
            "vintage": [b[0] for b in VINTAGE_BANDS],
        },
        "quintile_cut_points": {
            "income_total_household_2020": [r0(c) for c in income_cuts] if income_cuts else None,
            "median_dwelling_value_2021": [r0(c) for c in dv_cuts] if dv_cuts else None,
        },
        "opportunity_formula": opportunity.get("formula"),
        "opportunity_weights": OPP_WEIGHTS,
        "honesty_rails": [
            "Savings are modelled EnerGuide estimates, not measured utility bills.",
            "Negative / zero savings are dominated by audit noise; zero-measure pairs are reported but excluded from 'what worked' stats.",
            "Participation mixes ~20 years of cumulative audits over a single 2021 dwelling snapshot, so it is "
            "reported as a relative measure and suppressed entirely where the dwelling count is too small to divide by.",
            "FSA-level income/value correlations are ecological, not household-level (a 'rich FSA' is not a 'rich participant').",
            "ERS is a self-selected sample of homes that sought an audit, not a random sample of Canadian housing.",
        ],
        "program_annotations": PROGRAM_ANNOTATIONS,
    }

    # ---- write ----
    def write(name, obj):
        path = OUT_DIR / name
        with open(path, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False, separators=(",", ":"))
        kb = os.path.getsize(path) / 1024
        print(f"  wrote {path.name} ({kb:.1f} KB)")

    print("\nWriting insights_json/...")
    write("fsa_metrics.json", {"min_n": MIN_N, "records": list(metrics.values())})
    write("success.json", success)
    write("climate.json", climate_out)
    write("equity.json", equity)
    write("opportunity.json", opportunity)
    write("timeline.json", timeline)
    write("ghg_impact.json", ghg_impact)
    write("meta.json", meta)
    total_kb = sum(os.path.getsize(OUT_DIR / n) for n in os.listdir(OUT_DIR)
                   if n.endswith(".json")) / 1024
    print(f"  total insights_json/: {total_kb:.1f} KB (budget < 2048 KB)")

    validate(metrics, nat, prov_totals)

    # stash a few numbers for the notes memo
    return metrics, nat, success, climate_out, equity, opportunity, timeline, ghg_impact, income_cuts, dv_cuts


if __name__ == "__main__":
    main()
