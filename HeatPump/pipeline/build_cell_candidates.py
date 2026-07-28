"""
build_cell_candidates.py — top-3 candidate models per bucket cell, for the
manual datasheet hunt.

The Phase 3c grid picks ONE representative per cell (TIER_SPEC.md 4). When that
representative turns out to have no public performance table -- which the
2026-07-27 fetch pass showed is the common case -- the cell stalls. This emits
the top THREE candidates per cell instead, so a manual search that fails on the
first can move to the next without re-deriving the ranking.

36 cells x 3 = up to 108 rows, long format (one row per candidate, `rank` 1-3).

RANKING RULE
------------
Most ERS record appearances, **preferring `Active` certification status** --
the same rule TIER_SPEC.md 4 uses to pick representatives. So `rank == 1` is
always the current cell representative, and ranks 2-3 are the fallbacks. Active
units are preferred because a discontinued unit rarely has a live datasheet.
Cells with fewer than 3 models emit fewer rows.

WORDING DISCIPLINE (TIER_SPEC.md 1)
-----------------------------------
The count column is `ers_appearances`, NOT "installs". It counts occurrences of
an AHRI value in the ERS `AHRI` column across all audit rows: a home audited
twice counts twice, pre-/post-upgrade fields are not separated, and retrofit and
new-construction records are pooled. A sound popularity weight, a poor unit
count. Do not rename this column to "installs" in any downstream use.

INDOOR MODEL
------------
From the NRCan Searchable Product List (`Indoor_Model_Numbers`), joined on AHRI
number -- the AHRI scrape that would otherwise carry it is not on disk
(TIER_SPEC.md 7). Coverage is partial: ~76% of bucketed appearances. A blank
means "not listed by NRCan", NOT "no indoor unit". `Furnace_Model_Number` is
carried alongside because NRCan reports "Coils Only" there for coil-only
combinations, which is itself a useful signal when matching a submittal.

Usage:
    python HeatPump/pipeline/build_cell_candidates.py [--top 3]

Output:
    data/interim/cell_candidates.csv
"""

import argparse
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INTERIM = ROOT / "data" / "interim"

BUCKETS = INTERIM / "hp_buckets.csv"
JOINED = INTERIM / "hp_units_joined.csv"
NRCAN = INTERIM / "nrcan_spl.csv"
ENERGYSTAR = INTERIM / "energystar_by_ahri.csv"
DEST = INTERIM / "cell_candidates.csv"

# TIER_SPEC.md 6.2 -- screened as implausible, flagged rather than dropped.
IMPLAUSIBLE_COP = 3.0
IMPLAUSIBLE_CM = 1.30

COP_BANDS = ["COP<=1.8", "1.8<COP<=2.0", "COP>2.0"]
CM_BANDS = ["cm<0.60", "0.60<=cm<0.80", "cm>=0.80"]
CAP_BANDS = ["<18k", "18-30k", "30-42k", ">=42k"]


def read_csv(path):
    if not path.exists():
        sys.exit(f"missing input: {path}")
    with path.open(encoding="utf-8", errors="replace", newline="") as fh:
        return list(csv.DictReader(fh))


def capacity_band(cap_47):
    if cap_47 < 18000:
        return "<18k"
    if cap_47 < 30000:
        return "18-30k"
    if cap_47 < 42000:
        return "30-42k"
    return ">=42k"


def num(value):
    if value is None:
        return None
    value = value.strip()
    if not value or value == "-":
        return None
    try:
        return float(value)
    except ValueError:
        return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--top", type=int, default=3)
    args = parser.parse_args()

    buckets = [r for r in read_csv(BUCKETS) if r.get("c47")]
    total = sum(int(r["w"]) for r in read_csv(BUCKETS))

    spl = {}
    for row in read_csv(NRCAN):
        key = row.get("ahri_number", "").strip()
        if key and key not in spl:
            spl[key] = row

    es = {r["ahri_number"].strip(): r for r in read_csv(ENERGYSTAR)}

    extra = {r["k"].strip(): r for r in read_csv(JOINED)}

    cells = {}
    for row in buckets:
        key = (row["COP band"], row["CM band"], capacity_band(float(row["c47"])))
        cells.setdefault(key, []).append(row)

    out = []
    for cop_band in COP_BANDS:
        for cm_band in CM_BANDS:
            for cap_band in CAP_BANDS:
                members = cells.get((cop_band, cm_band, cap_band), [])
                if not members:
                    continue
                cell_weight = sum(int(m["w"]) for m in members)
                # Active first, then by appearances -- TIER_SPEC.md 4.
                ranked = sorted(
                    members,
                    key=lambda m: (m.get("status") != "Active", -int(m["w"])),
                )[: args.top]

                for rank, unit in enumerate(ranked, start=1):
                    ahri = unit["k"].strip()
                    nrcan = spl.get(ahri, {})
                    es_row = es.get(ahri, {})
                    joined = extra.get(ahri, {})

                    cop = num(unit.get("cop"))
                    cm = num(unit.get("cm"))
                    cap47 = num(unit.get("c47"))

                    implausible = bool(
                        (cop is not None and cop > IMPLAUSIBLE_COP)
                        or (cm is not None and cm > IMPLAUSIBLE_CM)
                    )

                    indoor = (nrcan.get("Indoor_Model_Numbers") or "").strip()
                    furnace = (nrcan.get("Furnace_Model_Number_if_applicable") or "").strip()

                    out.append({
                        "cop_band": cop_band,
                        "cm_band": cm_band,
                        "capacity_band": cap_band,
                        "cell_appearances": cell_weight,
                        "cell_share_pct": round(100 * cell_weight / total, 2),
                        "cell_models": len(members),
                        "rank": rank,
                        "ahri_number": ahri,
                        "ers_appearances": int(unit["w"]),
                        "brand": unit.get("brand", ""),
                        "outdoor_model": unit.get("model", ""),
                        "indoor_model": indoor if indoor not in ("-",) else "",
                        "furnace_model": furnace if furnace not in ("-",) else "",
                        "ahri_cop_5f": "" if cop is None else f"{cop:.2f}",
                        "ahri_capacity_maintenance": "" if cm is None else f"{cm:.4f}",
                        "ahri_rated_cap_47f_btuh": "" if cap47 is None else f"{cap47:.0f}",
                        "hspf2_region_iv": joined.get("h4", ""),
                        "hspf2_region_v": joined.get("h5", ""),
                        "cert_status": unit.get("status", ""),
                        "ahri_cold_climate": unit.get("cc", ""),
                        "ahri_product_group": joined.get("pg", ""),
                        "nrcan_listed": "yes" if nrcan else "no",
                        "nrcan_brand": (nrcan.get("BrandName") or "").strip(),
                        "es_listed": "yes" if es_row else "no",
                        "es_most_efficient": es_row.get("es_most_efficient", ""),
                        "es_cold_climate": es_row.get("es_cold_climate", ""),
                        "es_refrigerant": es_row.get("es_refrigerant", ""),
                        "compressor_staging": es_row.get("compressor_staging", ""),
                        "implausible_rating": "True" if implausible else "",
                    })

    with DEST.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(out[0].keys()))
        writer.writeheader()
        writer.writerows(out)

    cells_covered = len({(r["cop_band"], r["cm_band"], r["capacity_band"]) for r in out})
    with_indoor = sum(1 for r in out if r["indoor_model"])
    print(f"{len(out)} candidate rows across {cells_covered} cells (top {args.top} per cell)")
    print(f"  indoor model present: {with_indoor}/{len(out)} "
          f"({100 * with_indoor / len(out):.0f}%)")
    print(f"  NRCan listed:         {sum(1 for r in out if r['nrcan_listed'] == 'yes')}/{len(out)}")
    print(f"  ENERGY STAR listed:   {sum(1 for r in out if r['es_listed'] == 'yes')}/{len(out)}")
    print(f"  Active status:        {sum(1 for r in out if r['cert_status'] == 'Active')}/{len(out)}")
    print(f"  implausible flagged:  {sum(1 for r in out if r['implausible_rating'])}")
    print(f"\nwrote {DEST.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
