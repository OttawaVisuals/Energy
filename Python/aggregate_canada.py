"""
Builds province_json/CA.json — an "All of Canada" aggregate, used as the
landing-page default so the site isn't empty before a province is picked.

Only the "All types" slice is aggregated (not a full by_type breakdown):
house-type labels are inconsistent across provinces (e.g. "Double/Semi
Detached" vs "Double/Semi-Detached", "Row, End Unit" vs "Row House, End
Unit"), so merging type-level data confidently isn't possible without
normalizing that taxonomy upstream. The Canada view therefore only offers
"All types" — its type filter dropdown will just have that one option.

Program era (ecoENERGY / no program / Greener Homes) IS fully aggregated,
unlike house type: it's a fixed 3-bucket classification defined here (ERA_KEYS/
ERA_LABELS, mirroring precompute_province_stats.py's ERA_DEFS), not a
province-supplied taxonomy that can drift, so there's no cross-province
labelling risk the way there is for house type. Each province's
by_type["All types"]["by_era"][era] slice is combined the same way as the
top-level slice (aggregate_slices(), called once per era) and shipped as
by_type["All types"]["by_era"] in CA.json.

No raw row-level data is available here, only each province's own
precomputed bins/medians/counts, so:
  - counts and histogram bins are additive -> summed directly (exact).
  - medians are NOT additive -> recomputed from the summed bins via a
    weighted-median estimate (walk cumulative counts to the 50th
    percentile bucket). This is an approximation bounded by bin width,
    not a recomputation from raw data.
  - the fuel waterfall ships per-home MEANS, not totals -> weight by
    row_count to recover each province's total before summing.
  - solar_median_kw has no underlying histogram shipped -> approximated
    as a weighted average across provinces (weighted by adopter count).
"""
import json
import glob
import os
from collections import defaultdict, OrderedDict

# Same OUTPUT_DIR as precompute_province_stats.py / ers_web_pipeline.py —
# this reads the province JSONs that script just wrote and writes CA.json
# back into that same province_json folder, right alongside them.
OUTPUT_DIR = r"C:\ERS\web"
PROVINCE_JSON_DIR = os.path.join(OUTPUT_DIR, "province_json")
CA_JSON_PATH = os.path.join(PROVINCE_JSON_DIR, "CA.json")

PROVINCE_FILES = sorted(
    f for f in glob.glob(os.path.join(PROVINCE_JSON_DIR, "*.json"))
    if not f.endswith("CA.json")
)

INSULATION_KPI_MAP = [
    ("Roof insulation", "roof", "RSI", True),
    ("Wall insulation", "wall", "RSI", True),
    ("Foundation ins.", "fnd", "RSI", True),
    ("Air leakage", "air", "ACH50", False),
]

# Program-era keys, MUST match precompute_province_stats.py's ERA_DEFS/
# ERA_LABELS exactly -- duplicated here (not imported) because this script
# only reads the province JSONs those constants already shaped, not the
# Python module itself.
ERA_KEYS = ['ecoenergy', 'none', 'greener']
ERA_LABELS = {'ecoenergy': 'ecoENERGY (2007–2012)', 'none': 'No program',
              'greener': 'Greener Homes (2021–2024)'}


def sum_bins(dicts):
    out = defaultdict(float)
    for d in dicts:
        for k, v in (d or {}).items():
            out[k] += v
    return dict(out)


def weighted_median_from_bins(bins):
    items = sorted(((float(k), v) for k, v in bins.items() if v > 0), key=lambda x: x[0])
    total = sum(v for _, v in items)
    if total == 0:
        return None
    half = total / 2
    cum = 0
    for k, v in items:
        cum += v
        if cum >= half:
            return k
    return items[-1][0]


def aggregate_slices(slices):
    """
    Combine a list of per-province compute_slice() payloads -- all the same
    house-type/program-era bucket, one entry per province -- into one
    national slice, via the additive-bins-then-weighted-median approach this
    module's docstring describes. Returns a dict shaped exactly like
    compute_slice()'s own output (no "funnel" key -- that's assembled
    separately in main(), only at the top level, since by_era sub-slices
    don't carry their own audit-funnel breakdown).
    """
    n_total = sum(s.get("row_count", 0) for s in slices)

    out = {}
    out["row_count"] = n_total

    # Additive bin/count fields.
    for key in [
        "eui_pre_bins", "eui_post_bins", "eui_delta_bins",
        "ghg_pre_bins", "ghg_post_bins", "ghg_delta_bins",
        "heatloss_pre_bins", "heatloss_post_bins", "heatloss_delta_bins",
        "floor_area_bins", "year_built_bins", "savings_pct_bins",
        "storey_counts", "type_counts",
        "ahri_counts", "window_pre_counts", "window_post_counts",
        "d_year_bins", "e_year_bins",
        "hp_sizing47_bins", "hp_sizing5_bins",
        "backup_fuel_counts", "backup_used_counts",
    ]:
        out[key] = sum_bins(s.get(key, {}) for s in slices)

    # Re-rank from the summed full counts (not from each province's own
    # top-N) so a code/number that's locally #6 everywhere but nationally
    # #1 isn't silently dropped — same reasoning as precompute_province_stats.py.
    def top_n(counts, n):
        return [{"code": k, "count": v} for k, v in
                sorted(counts.items(), key=lambda kv: -kv[1])[:n]]

    out["top_ahri_numbers"] = top_n(out["ahri_counts"], 5)
    out["window_pre_top"] = top_n(out["window_pre_counts"], 5)
    out["window_post_top"] = top_n(out["window_post_counts"], 5)

    for key in ["deep_retrofit_count", "fuel_switch_count", "heat_pump_count", "solar_post_count",
                "hp_home_count"]:
        out[key] = round(sum(s.get(key, 0) for s in slices))

    # Medians recomputed from the combined bins (see module docstring).
    out["eui_pre_median"] = weighted_median_from_bins(out["eui_pre_bins"])
    out["eui_post_median"] = weighted_median_from_bins(out["eui_post_bins"])
    out["eui_saving"] = (
        round(out["eui_pre_median"] - out["eui_post_median"])
        if out["eui_pre_median"] is not None and out["eui_post_median"] is not None
        else None
    )
    out["ghg_pre_median"] = weighted_median_from_bins(out["ghg_pre_bins"])
    out["ghg_post_median"] = weighted_median_from_bins(out["ghg_post_bins"])
    out["ghg_saving"] = (
        round(out["ghg_pre_median"] - out["ghg_post_median"], 1)
        if out["ghg_pre_median"] is not None and out["ghg_post_median"] is not None
        else None
    )
    out["ghg_reported_n"] = sum(s.get("ghg_reported_n", 0) or 0 for s in slices)
    out["ghg_reported_coverage_pct"] = (
        round(out["ghg_reported_n"] / n_total, 3) if n_total else None
    )

    # The 3 calculated GHG scenarios (current / current_corrected / as_audited)
    # -- same additive-bins-then-weighted-median approach, per scenario. Skips
    # "reported" (already handled above via the flat keys, for backward
    # compatibility -- see precompute_province_stats.py's ghg_scenario_block).
    out["ghg_scenarios"] = {"reported": {
        "n": out["ghg_reported_n"], "coverage_pct": out["ghg_reported_coverage_pct"],
        "pre_median": out["ghg_pre_median"], "post_median": out["ghg_post_median"],
        "saving": out["ghg_saving"], "pre_bins": out["ghg_pre_bins"],
        "post_bins": out["ghg_post_bins"], "delta_bins": out["ghg_delta_bins"],
    }}
    for scen in ("current", "current_corrected", "as_audited"):
        pre_bins = sum_bins(s.get("ghg_scenarios", {}).get(scen, {}).get("pre_bins", {}) for s in slices)
        post_bins = sum_bins(s.get("ghg_scenarios", {}).get(scen, {}).get("post_bins", {}) for s in slices)
        delta_bins = sum_bins(s.get("ghg_scenarios", {}).get(scen, {}).get("delta_bins", {}) for s in slices)
        pre_med = weighted_median_from_bins(pre_bins)
        post_med = weighted_median_from_bins(post_bins)
        scen_n = sum(s.get("ghg_scenarios", {}).get(scen, {}).get("n", 0) or 0 for s in slices)
        out["ghg_scenarios"][scen] = {
            "n": scen_n,
            "coverage_pct": round(scen_n / n_total, 3) if n_total else None,
            "pre_median": pre_med,
            "post_median": post_med,
            "saving": round(pre_med - post_med, 1) if pre_med is not None and post_med is not None else None,
            "pre_bins": pre_bins, "post_bins": post_bins, "delta_bins": delta_bins,
        }
    med_pct = weighted_median_from_bins(out["savings_pct_bins"])
    out["median_saving_pct"] = (med_pct / 100) if med_pct is not None else None

    out["hp_sizing47_median"] = weighted_median_from_bins(out["hp_sizing47_bins"])
    out["hp_sizing5_median"] = weighted_median_from_bins(out["hp_sizing5_bins"])

    # Insulation: histograms summed directly, KPI medians recomputed from them.
    ih = {}
    for _, hkey, unit, _ in INSULATION_KPI_MAP:
        ih[hkey] = {
            "unit": unit,
            "pre_bins": sum_bins(s.get("insulation_histograms", {}).get(hkey, {}).get("pre_bins", {}) for s in slices),
            "post_bins": sum_bins(s.get("insulation_histograms", {}).get(hkey, {}).get("post_bins", {}) for s in slices),
            "delta_bins": sum_bins(s.get("insulation_histograms", {}).get(hkey, {}).get("delta_bins", {}) for s in slices),
        }
    out["insulation_histograms"] = ih
    out["insulation_kpis"] = [
        {
            "label": label,
            "pre": weighted_median_from_bins(ih[hkey]["pre_bins"]),
            "post": weighted_median_from_bins(ih[hkey]["post_bins"]),
            "unit": unit,
            "higher_is_better": higher_is_better,
        }
        for label, hkey, unit, higher_is_better in INSULATION_KPI_MAP
    ]

    # Measures: counts additive, pct recomputed off the combined row count.
    measure_counts = defaultdict(lambda: {"label": "", "count": 0})
    for s in slices:
        for m in s.get("measures", []):
            mc = measure_counts[m["key"]]
            mc["label"] = m["label"]
            mc["count"] += m["count"]
    out["measures"] = [
        {"key": k, "label": v["label"], "count": v["count"],
         "pct": round(v["count"] / n_total * 100) if n_total else 0}
        for k, v in measure_counts.items()
    ]

    # Sankey flows ship as absolute totals already -> sum directly.
    flows = defaultdict(lambda: {"pre": 0.0, "post": 0.0})
    for s in slices:
        for k, v in s.get("sankey_flows", {}).items():
            flows[k]["pre"] += v.get("pre", 0)
            flows[k]["post"] += v.get("post", 0)
    out["sankey_flows"] = dict(flows)

    # Waterfall ships per-home MEANS -> weight by row_count to get totals,
    # sum totals across provinces, then divide back to a combined mean so
    # the shape (a list of {fuel,pre,post} means) matches every other file.
    fuel_totals = defaultdict(lambda: {"pre": 0.0, "post": 0.0})
    for s in slices:
        n = s.get("row_count", 0)
        for w in s.get("waterfall", []):
            fuel_totals[w["fuel"]]["pre"] += w["pre"] * n
            fuel_totals[w["fuel"]]["post"] += w["post"] * n
    out["waterfall"] = [
        {"fuel": fuel, "pre": round(t["pre"] / n_total) if n_total else 0,
         "post": round(t["post"] / n_total) if n_total else 0}
        for fuel, t in fuel_totals.items()
    ]

    # Heat-loss components ship per-home MEANS too -- same weight-by-n,
    # sum, divide-back treatment as the waterfall directly above. Order is
    # preserved from the first province that reports each component so the
    # national file lists them in the same order as a provincial one.
    hl_totals = OrderedDict()
    for s in slices:
        n = s.get("row_count", 0)
        for c in s.get("heatloss_components", []):
            t = hl_totals.setdefault(c["label"], {"pre": 0.0, "post": 0.0})
            t["pre"] += c["pre"] * n
            t["post"] += c["post"] * n
    out["heatloss_components"] = [
        {"label": label,
         "pre": round(t["pre"] / n_total, 1) if n_total else 0,
         "post": round(t["post"] / n_total, 1) if n_total else 0}
        for label, t in hl_totals.items()
    ]

    # Backup-fuel energy means (elec_mean/fuel_mean/n per fuel) aren't
    # additive -- weight each province's means by its own n, sum, divide back
    # to a combined mean, same approach as the waterfall combiner above.
    energy_totals = defaultdict(lambda: {"elec": 0.0, "fuel": 0.0, "n": 0})
    for s in slices:
        for fuel, v in s.get("backup_energy_means", {}).items():
            t = energy_totals[fuel]
            t["elec"] += v["elec_mean"] * v["n"]
            t["fuel"] += v["fuel_mean"] * v["n"]
            t["n"] += v["n"]
    out["backup_energy_means"] = {
        fuel: {"elec_mean": t["elec"] / t["n"], "fuel_mean": t["fuel"] / t["n"], "n": t["n"]}
        for fuel, t in energy_totals.items() if t["n"]
    }

    # Solar: post adopter count is additive; pre/post adopter counts are
    # derived from each province's own pct*row_count to recombine exactly,
    # rather than averaging percentages. solar_median_kw has no underlying
    # histogram shipped, so it's approximated as a weighted average across
    # provinces, weighted by adopter count (best available proxy).
    pre_adopters = sum(round(s.get("solar_pre_pct", 0) / 100 * s.get("row_count", 0)) for s in slices)
    out["solar_pre_pct"] = round(pre_adopters / n_total * 100) if n_total else 0
    out["solar_post_pct"] = round(out["solar_post_count"] / n_total * 100) if n_total else 0
    kw_weight = sum(s.get("solar_post_count", 0) for s in slices)
    # solar_median_kw is explicitly None (not just absent) whenever a slice has
    # n>0 but zero solar adopters -- .get(..., 0)'s default only covers the key
    # being MISSING, not present-and-None, so `or 0` is needed too. This was
    # always possible for a small province/type slice; era sub-slices make a
    # zero-adopter-but-nonzero-n bucket common enough to hit routinely.
    out["solar_median_kw"] = (
        round(sum((s.get("solar_median_kw") or 0) * s.get("solar_post_count", 0) for s in slices) / kw_weight, 1)
        if kw_weight else None
    )

    return out


def main():
    if not PROVINCE_FILES:
        print(f"!! no province JSONs found in {PROVINCE_JSON_DIR} — run precompute_province_stats.py first")
        return

    slices = []
    funnels = []
    era_slices = {k: [] for k in ERA_KEYS}
    total_rows = 0
    for path in PROVINCE_FILES:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        total_rows += data["total_rows"]
        base = data["by_type"]["All types"]
        slices.append(base)
        funnels.append(data.get("funnel"))
        # Program-era sub-slices (precompute_province_stats.py). A province
        # JSON built before the by_era field existed contributes an empty
        # (row_count 0) slice for each era rather than breaking the run --
        # the national by_era total would just under-count until that
        # province is rebuilt.
        by_era = base.get("by_era", {})
        for k in ERA_KEYS:
            era_slices[k].append(by_era.get(k, {"row_count": 0}))

    out = aggregate_slices(slices)

    # Audit-funnel: sum province composition + matched counts (all additive).
    # Provinces with a null funnel (sidecar not built when they were generated)
    # are skipped; if none carry one, the national funnel stays null.
    present = [f for f in funnels if f]
    out_funnel = (
        {k: sum(f.get(k, 0) for f in present) for k in ('t', 'de', 'd', 'e', 'nc', 'matched')}
        if present else None
    )

    # Same national-recombination logic, once per program era, so the
    # Canada view's "All of Canada" + a program-era filter reads from a real
    # cross-province aggregate rather than falling back to the unfiltered
    # total (see assets/retrofits.js renderProvince()'s by_era lookup).
    out["by_era"] = {k: aggregate_slices(v) for k, v in era_slices.items()}

    payload = {"province": "CA", "total_rows": total_rows,
               "funnel": out_funnel, "era_labels": ERA_LABELS,
               "by_type": {"All types": out}}
    with open(CA_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, separators=(",", ":"))
    print(f"Wrote {CA_JSON_PATH} — {total_rows:,} total rows across {len(PROVINCE_FILES)} provinces/territories")


if __name__ == "__main__":
    main()
