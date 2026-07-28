"""
screen_cchp.py — screen the installed base against the US DOE Cold Climate Heat
Pump (CCHP) Technology Challenge specifications.

Source of the thresholds:
  https://www.energy.gov/cmei/buildings/cchp-technology-challenge-specifications
  Table II-3, "Summary of the Challenge specifications".

WHAT THIS IS NOT
----------------
This is a **screen against published rating data**, not a determination that a
unit met the Challenge. The Challenge is a verification programme with its own
H11/H1N laboratory test protocol; we hold AHRI certificate ratings. A unit that
passes here has rating-consistent performance and nothing more. The output
column is called `verdict`, its passing value is `screen_pass`, and no column in
this file is named "meets" or "certified". Do not relabel them.

WHICH CRITERIA ARE CHECKABLE
----------------------------
Table II-3 sets eight-ish requirements. Four are checkable from the ratings we
hold, four are not:

  checkable
    * nominal capacity band          -> selects the COP threshold
    * COP at 5 F  >= 2.4 / 2.1       -> by capacity band
    * capacity ratio at 5 F >= 100%
    * HSPF2 >= 8.5                   -> FLOOR ONLY, see caveat below
    * refrigerant GWP <= 750         -> AR4 100-year, from the ENERGY STAR list

  not checkable, recorded as such
    * minimum turndown ratio 30%     -> needs minimum capacity; not in AHRI
    * low-temperature compressor cut-out / cut-in at 5 F and -15 F
                                     -> not in AHRI or ENERGY STAR; manufacturer
                                        datasheets give a lock-out only
    * electric heat staging (Table II-1)
    * ENERGY STAR CACHP sections 3C, 4B, 4C, 4D
                                     -> partially proxied by es_cold_climate,
                                        not evaluated here

THREE MEASUREMENT CAVEATS, CARRIED AS COLUMNS NOT FOOTNOTES
-----------------------------------------------------------
1. **Capacity band basis.** Table II-3 note 1 defines nominal capacity by the
   *A2 test of Appendix M1* (a cooling test) for a heating/cooling heat pump.
   We hold the AHRI **heating rated capacity at 47 F**. These are close but not
   the same test, so a unit near a band edge (24,000 / 36,000 / 48,000 Btu/h)
   could be assigned the wrong COP threshold. `band_basis` records this.

2. **Capacity ratio basis.** Ours is `Max 5 F / Rated 47 F` -- the ratio
   ENERGY STAR v6.2, CEE and NRCan Greener Homes all define (TIER_SPEC.md 2).
   The Challenge states "Capacity Ratio 100%" without naming the two points.
   If it intends rated-to-rated, our figure is the more generous of the two.

3. **HSPF2 is a floor test only.** The Challenge threshold is
   `8.5 * (1 + capacity factor) * (1 + COP factor)`, where both factors come
   from H11/H1N verification-test results we do not have. We can only test
   `HSPF2 >= 8.5`. Any unit passing here may still fail the real, higher bar.
   `hspf2_floor_only` is True on every row for exactly this reason.

<24,000 Btu/h IS OUT OF SCOPE BY DESIGN
---------------------------------------
Table II-3's smallest row is ">= 24,000". Units below it are marked
`out_of_scope` and given no verdict. They are not failures -- the Challenge
deliberately does not address them. Roughly a third of the installed base sits
here; that is a statement about the Challenge's scope, not about the equipment.

NOTHING IS DROPPED
------------------
Implausible ratings (COP > 3.0, capacity ratio > 1.30 -- TIER_SPEC.md 6) are
flagged in `implausible` and still written. A screen that silently discarded
them would hide the units most likely to pass on bad data.

Inputs (all local, gitignored):
    data/interim/hp_units_joined.csv     universe + AHRI/NRCan ratings
    data/interim/energystar_by_ahri.csv  refrigerant, Most Efficient, staging
    data/interim/nrcan_spl.csv           brand / model names
    data/interim/hp_buckets.csv          brand / model names (screened subset)

Usage:
    python HeatPump/pipeline/screen_cchp.py

Outputs:
    data/interim/cchp_qualifying.csv   units passing every checkable criterion
    data/interim/cchp_screen.csv       every unit with its per-criterion result
"""

import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INTERIM = ROOT / "data" / "interim"

UNITS = INTERIM / "hp_units_joined.csv"
ENERGYSTAR = INTERIM / "energystar_by_ahri.csv"
NRCAN = INTERIM / "nrcan_spl.csv"
BUCKETS = INTERIM / "hp_buckets.csv"

OUT_QUALIFY = INTERIM / "cchp_qualifying.csv"
OUT_FULL = INTERIM / "cchp_screen.csv"

SPEC_URL = "https://www.energy.gov/cmei/buildings/cchp-technology-challenge-specifications"

# Table II-3: (lower bound exclusive, upper bound inclusive, COP at 5 F).
# The smallest Challenge row starts at 24,000 Btu/h; below that is out of scope.
CAPACITY_BANDS = [
    (24000, 36000, 2.4),   # >= 24,000 and <= 36,000
    (36000, 48000, 2.4),   # >  36,000 and <= 48,000
    (48000, None, 2.1),    # >  48,000
]

MIN_CAPACITY_RATIO = 1.00
MIN_HSPF2_FLOOR = 8.5
MAX_GWP = 750

# AR4 100-year GWP, as the Challenge specifies. Refrigerants absent here resolve
# to None -> the GWP criterion is "unknown", never silently "pass".
GWP_AR4 = {
    "R-410A": 2088,
    "R-32": 675,
    "R-454B": 466,
    "R-452B": 698,
    "R-466A": 733,
    "R-454C": 148,
    "R-455A": 148,
    "R-134a": 1430,
    "R-407C": 1774,
    "R-22": 1810,
    "R-404A": 3922,
    "R-513A": 631,
    "R-448A": 1387,
    "R-449A": 1397,
    "R-1234yf": 4,
    "R-290": 3,
    "R-744": 1,
    "R-717": 0,
}

IMPLAUSIBLE_COP = 3.0
IMPLAUSIBLE_RATIO = 1.30


def read_csv(path, encoding="utf-8"):
    if not path.exists():
        sys.exit(f"missing input: {path}\nrun the Phase 3c fetchers first (TIER_SPEC.md 7)")
    with path.open(encoding=encoding, errors="replace", newline="") as fh:
        return list(csv.DictReader(fh))


def num(value):
    """Parse a numeric cell; blanks and NRCan's '-' placeholder become None."""
    if value is None:
        return None
    value = value.strip()
    if not value or value == "-":
        return None
    try:
        return float(value)
    except ValueError:
        return None


def capacity_band(cap_47):
    """Return (band_label, cop_threshold). None threshold means out of scope."""
    if cap_47 is None:
        return "unknown", None
    if cap_47 < CAPACITY_BANDS[0][0]:
        return "<24k", None
    for low, high, cop in CAPACITY_BANDS:
        if high is None or cap_47 <= high:
            label = f">{low//1000}k" if high is None else f"{low//1000}-{high//1000}k"
            return label, cop
    return "unknown", None


def tri(condition):
    """Three-valued result: 'pass', 'fail', or 'unknown' when the input is absent."""
    return "unknown" if condition is None else ("pass" if condition else "fail")


def main():
    units = read_csv(UNITS)

    es = {r["ahri_number"].strip(): r for r in read_csv(ENERGYSTAR)}

    names = {}
    for row in read_csv(NRCAN):
        key = row.get("ahri_number", "").strip()
        if key and key not in names:
            names[key] = (row.get("BrandName", ""), row.get("ModelNumber", ""))
    # hp_buckets carries the brand/model actually used elsewhere in Phase 3c;
    # prefer it so names match the tier tables.
    for row in read_csv(BUCKETS):
        key = row.get("k", "").strip()
        if key:
            names[key] = (row.get("brand", ""), row.get("model", ""))

    results = []
    for row in units:
        ahri = row["k"].strip()
        weight = int(num(row.get("w")) or 0)
        cap_47 = num(row.get("c47"))
        ratio = num(row.get("cm"))
        cop_5f = num(row.get("cop"))
        hspf2_iv = num(row.get("h4"))
        hspf2_v = num(row.get("h5"))

        es_row = es.get(ahri, {})
        refrigerant = (es_row.get("es_refrigerant") or "").strip()
        gwp = GWP_AR4.get(refrigerant)

        band, cop_threshold = capacity_band(cap_47)

        c_ratio = tri(None if ratio is None else ratio >= MIN_CAPACITY_RATIO)
        c_cop = tri(
            None if (cop_5f is None or cop_threshold is None) else cop_5f >= cop_threshold
        )
        c_hspf2 = tri(None if hspf2_iv is None else hspf2_iv >= MIN_HSPF2_FLOOR)
        c_gwp = tri(None if gwp is None else gwp <= MAX_GWP)

        checks = [c_ratio, c_cop, c_hspf2, c_gwp]

        if cop_threshold is None:
            verdict = "out_of_scope" if band == "<24k" else "unknown"
        elif all(c == "pass" for c in checks):
            verdict = "screen_pass"
        elif "fail" in checks:
            # 'near' = every checkable criterion that resolved passed, and only
            # one gate failed. Useful for reading what the binding constraint is.
            verdict = "near" if sum(c == "fail" for c in checks) == 1 else "fail"
        else:
            verdict = "unknown"

        implausible = bool(
            (cop_5f is not None and cop_5f > IMPLAUSIBLE_COP)
            or (ratio is not None and ratio > IMPLAUSIBLE_RATIO)
        )

        brand, model = names.get(ahri, ("", ""))

        results.append({
            "ahri_number": ahri,
            "brand": brand,
            "model": model,
            "ers_appearances": weight,
            "verdict": verdict,
            "capacity_band": band,
            "cap_47f_btuh": "" if cap_47 is None else f"{cap_47:.0f}",
            "cop_5f": "" if cop_5f is None else f"{cop_5f:.2f}",
            "cop_threshold": "" if cop_threshold is None else f"{cop_threshold:.1f}",
            "capacity_ratio": "" if ratio is None else f"{ratio:.4f}",
            "hspf2_region_iv": "" if hspf2_iv is None else f"{hspf2_iv:.2f}",
            "hspf2_region_v": "" if hspf2_v is None else f"{hspf2_v:.2f}",
            "refrigerant": refrigerant,
            "gwp_ar4_100yr": "" if gwp is None else gwp,
            "check_capacity_ratio": c_ratio,
            "check_cop_5f": c_cop,
            "check_hspf2_floor": c_hspf2,
            "check_gwp": c_gwp,
            "hspf2_floor_only": "True",
            "band_basis": "AHRI heating rated 47F (spec asks A2 test, Appendix M1)",
            "ratio_basis": "Max 5F / Rated 47F",
            "turndown_ratio": "not_checkable",
            "compressor_cutout_cutin": "not_checkable",
            "electric_heat_staging": "not_checkable",
            "energystar_cachp_sections": "not_checkable",
            "es_cold_climate": es_row.get("es_cold_climate", ""),
            "es_most_efficient": es_row.get("es_most_efficient", ""),
            "compressor_staging": es_row.get("compressor_staging", ""),
            "ahri_product_group": row.get("pg", ""),
            "ahri_cold_climate": row.get("cc", ""),
            "implausible_rating": "True" if implausible else "",
            "spec_source": SPEC_URL,
        })

    fields = list(results[0].keys())

    with OUT_FULL.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        writer.writerows(sorted(results, key=lambda r: -r["ers_appearances"]))

    qualifying = [r for r in results if r["verdict"] == "screen_pass"]
    with OUT_QUALIFY.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        writer.writerows(sorted(qualifying, key=lambda r: -r["ers_appearances"]))

    total_weight = sum(r["ers_appearances"] for r in results)
    print(f"screened {len(results)} models / {total_weight} ERS appearances")
    for verdict in ("screen_pass", "near", "fail", "out_of_scope", "unknown"):
        rows = [r for r in results if r["verdict"] == verdict]
        weight = sum(r["ers_appearances"] for r in rows)
        share = 100 * weight / total_weight if total_weight else 0
        print(f"  {verdict:13} {len(rows):6} models  {weight:8} appearances  {share:5.2f}%")

    # Which single gate is binding, among units in scope that failed exactly one.
    print("\nbinding constraint for 'near' units:")
    for check in ("check_capacity_ratio", "check_cop_5f", "check_hspf2_floor", "check_gwp"):
        rows = [r for r in results if r["verdict"] == "near" and r[check] == "fail"]
        weight = sum(r["ers_appearances"] for r in rows)
        print(f"  {check:22} {len(rows):6} models  {weight:8} appearances")

    flagged = [r for r in qualifying if r["implausible_rating"]]
    if flagged:
        print(f"\nWARNING: {len(flagged)} qualifying unit(s) carry implausible ratings")

    print(f"\nwrote {OUT_QUALIFY.relative_to(ROOT)} ({len(qualifying)} rows)")
    print(f"wrote {OUT_FULL.relative_to(ROOT)} ({len(results)} rows)")


if __name__ == "__main__":
    main()
