"""
rollup_census.py

Aggregates census_json/fsa_census.json (per-FSA 2021 Census housing stock,
built by extract_fsa_census.py) up to province and Canada level, writing
census_json/region_census.json keyed by the same province codes the site
uses (AB, BC, ... SK) plus "CA".

Why roll up rather than download the province-level Census Profile: FSAs
tile the country exactly — every private dwelling sits in exactly one FSA —
so the count characteristics sum to the province and national totals without
fetching StatCan's 98-401-X2021001 file. The only cost is StatCan's random
rounding to base 5, which is applied per FSA and averages out to noise at
province scale (a few hundred dwellings on millions).

FSA -> province comes from geo_json/<PROV>.json (the site's own split of
StatCan's 2021 FSA boundary file, so it agrees with the map). Six FSAs in
the census file have no 2021 polygon — three Yukon FSAs (the site has no YT
view, but they still belong in the Canada total) and three FSAs created
after the boundary vintage — so those fall back to the postal first-letter
mapping in LETTER_TO_PROV.

Aggregation rules, by field type:
  - Counts (population, dwellings, dwelling type, tenure, period of
    construction, condition, owner_households_total) are SUMMED. Exact.
  - Rates and averages (pct_with_mortgage, average_dwelling_value, ...) are
    WEIGHTED MEANS over the FSAs that report them, weighted by the
    denominator each rate is actually a share of: owner households for the
    owner_stats fields, population for the low-income rate, and total
    dwellings for average household size. Exact up to the suppressed FSAs.
  - MEDIANS are set to null. A median of medians is not a median, and the
    per-FSA distributions needed to compute a real one are not in the source.
    The frontend swaps in the corresponding average field at rollup level
    rather than printing a dash.

Suppressed cells are already null in the input; they are skipped (they drop
out of both numerator and denominator) rather than counted as zero, so a
weighted mean describes only the FSAs that reported.

INPUT:  census_json/fsa_census.json, geo_json/<PROV>.json
OUTPUT: census_json/region_census.json

Usage:
    python Python/rollup_census.py
"""

import json
import os
from collections import defaultdict

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FSA_CENSUS = os.path.join(REPO_ROOT, "census_json", "fsa_census.json")
GEO_DIR = os.path.join(REPO_ROOT, "geo_json")
OUT_PATH = os.path.join(REPO_ROOT, "census_json", "region_census.json")

# Fallback for FSAs with no 2021 boundary polygon. Only the unambiguous
# letters are listed: X is shared by NT and NU, so an X FSA missing from
# geo_json is left unassigned (reported, not guessed) rather than being
# silently attributed to one territory.
LETTER_TO_PROV = {
    "A": "NF", "B": "NS", "C": "PE", "E": "NB",
    "G": "QC", "H": "QC", "J": "QC",
    "K": "ON", "L": "ON", "M": "ON", "N": "ON", "P": "ON",
    "R": "MB", "S": "SK", "T": "AB", "V": "BC",
}
# Yukon has no province view on the site, but its dwellings are still part
# of Canada — mapped to a sentinel that only feeds the CA total.
YT_SENTINEL = "_YT"

# Nested count blocks: summed key-by-key.
COUNT_BLOCKS = ["dwelling_type", "tenure", "period_of_construction", "condition"]
# Top-level counts.
COUNT_SCALARS = ["population", "total_dwellings"]

# (block, field, weight_source) — weight_source names the count this rate or
# average is a share/mean over.
WEIGHTED = [
    ("owner_stats", "pct_with_mortgage", "owner"),
    ("owner_stats", "pct_spending_30pct_shelter", "owner"),
    ("owner_stats", "pct_core_housing_need", "owner"),
    ("owner_stats", "average_shelter_cost", "owner"),
    ("owner_stats", "average_dwelling_value", "owner"),
    ("income", "pct_low_income_lim_at", "population"),
    ("income", "average_household_size", "dwellings"),
]
# Set to null in every rollup — see module docstring.
MEDIANS = [
    ("owner_stats", "median_shelter_cost"),
    ("owner_stats", "median_dwelling_value"),
    ("income", "median_total_income"),
    ("income", "median_after_tax_income"),
]


def build_fsa_prov_map():
    """FSA code -> province code, from the site's own geo_json split."""
    m = {}
    for fname in sorted(os.listdir(GEO_DIR)):
        if not fname.endswith(".json"):
            continue
        prov = fname[:-5]
        with open(os.path.join(GEO_DIR, fname), encoding="utf-8") as fh:
            geo = json.load(fh)
        for feat in geo.get("features", []):
            props = feat.get("properties", {})
            fsa = props.get("fsa") or props.get("CFSAUID")
            if fsa:
                m[fsa] = prov
    return m


def resolve_province(fsa, geo_map):
    if fsa in geo_map:
        return geo_map[fsa]
    letter = fsa[:1].upper()
    if letter == "Y":
        return YT_SENTINEL
    return LETTER_TO_PROV.get(letter)


def new_acc():
    return {
        "counts": defaultdict(float),
        "blocks": defaultdict(lambda: defaultdict(float)),
        "owner_households_total": 0.0,
        # field -> [weighted_sum, weight_total]
        "weighted": defaultdict(lambda: [0.0, 0.0]),
        "n_fsa": 0,
    }


def accumulate(acc, c):
    acc["n_fsa"] += 1
    for k in COUNT_SCALARS:
        v = c.get(k)
        if v is not None:
            acc["counts"][k] += v
    for blk in COUNT_BLOCKS:
        for k, v in (c.get(blk) or {}).items():
            if v is not None:
                acc["blocks"][blk][k] += v

    owner_total = (c.get("owner_stats") or {}).get("owner_households_total")
    if owner_total:
        acc["owner_households_total"] += owner_total

    weights = {
        "owner": owner_total,
        "population": c.get("population"),
        "dwellings": c.get("total_dwellings"),
    }
    for blk, field, wsrc in WEIGHTED:
        val = (c.get(blk) or {}).get(field)
        w = weights.get(wsrc)
        # Both the value and its weight must be present, or the term is
        # meaningless — skip rather than treating a suppressed cell as 0.
        if val is None or not w:
            continue
        slot = acc["weighted"][f"{blk}.{field}"]
        slot[0] += val * w
        slot[1] += w


def finalize(acc):
    out = {k: int(round(v)) for k, v in acc["counts"].items()}
    for blk in COUNT_BLOCKS:
        if acc["blocks"].get(blk):
            out[blk] = {k: int(round(v)) for k, v in acc["blocks"][blk].items()}

    owner_stats = {"owner_households_total": int(round(acc["owner_households_total"]))}
    income = {}
    targets = {"owner_stats": owner_stats, "income": income}
    for blk, field, _ in WEIGHTED:
        wsum, wtot = acc["weighted"].get(f"{blk}.{field}", [0.0, 0.0])
        if wtot:
            mean = wsum / wtot
            # Match the source file's precision: rates/household size to one
            # decimal, dollar amounts to whole dollars.
            targets[blk][field] = (
                round(mean, 1) if field.startswith("pct_") or field == "average_household_size"
                else int(round(mean))
            )
        else:
            targets[blk][field] = None
    for blk, field in MEDIANS:
        targets[blk][field] = None

    out["owner_stats"] = owner_stats
    out["income"] = income
    out["fsa_count"] = acc["n_fsa"]
    return out


def main():
    with open(FSA_CENSUS, encoding="utf-8") as fh:
        fsa_census = json.load(fh)
    geo_map = build_fsa_prov_map()
    print(f"FSA->province map: {len(geo_map):,} FSAs from geo_json")

    prov_acc = defaultdict(new_acc)
    canada = new_acc()
    unassigned = []

    for fsa, c in fsa_census.items():
        prov = resolve_province(fsa, geo_map)
        if prov is None:
            unassigned.append(fsa)
            continue
        accumulate(canada, c)
        if prov != YT_SENTINEL:
            accumulate(prov_acc[prov], c)

    if unassigned:
        print(f"  !! {len(unassigned)} FSA(s) with no province mapping "
              f"(excluded from all totals): {', '.join(sorted(unassigned))}")

    out = {prov: finalize(acc) for prov, acc in sorted(prov_acc.items())}
    out["CA"] = finalize(canada)

    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as fh:
        json.dump(out, fh, separators=(",", ":"))

    for code in sorted(out):
        r = out[code]
        print(f"  {code:>2}  {r['fsa_count']:>5} FSAs  "
              f"{r['total_dwellings']:>10,} dwellings  "
              f"pop {r['population']:>11,}")
    size = os.path.getsize(OUT_PATH)
    print(f"wrote {OUT_PATH} ({size:,} bytes)")


if __name__ == "__main__":
    main()
