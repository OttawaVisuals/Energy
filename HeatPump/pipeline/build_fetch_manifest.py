"""
build_fetch_manifest.py — Phase 3c: the datasheet hand-fetch worklist.

Regenerates, from data rather than by hand, the state of the datasheet sweep:
the 36 bucket representatives, what document we hold for each, whether a curve
was built, and what is blocking it. Replaces hand-maintenance of the tables in
DATASHEET_INVENTORY.md, which drift the moment a PDF is added.

Emits data/interim/datasheet_fetch_manifest.csv, one row per representative.

BAND ISSUE — the classification this exists to record
-----------------------------------------------------
"Band issue" is the failure mode that halted the first sweep. One outdoor model
name can be certified in several combinations, each paired with a different
indoor coil, and each combination gets its OWN AHRI number AND its OWN rated
capacity. The model string on a datasheet therefore does not identify the
certified combination.

Detection: compare the datasheet's 47 F maximum capacity against the AHRI
certificate's RATED 47 F capacity for the specific AHRI number.

    ratio = datasheet_47F_max / certificate_rated_47F

A variable-speed unit legitimately boosts above its rated point, so ratio > 1.0
is normal and expected. Beyond ~1.35 there are two causes that CANNOT be
separated automatically:

    (a) WRONG COMBINATION — the sheet describes a different, larger certified
        combination than the AHRI number in the ERS records. The curve is then
        simply wrong: applying a 36,000 Btu/h table to a 24,000 Btu/h
        certificate overstates output by half.
    (b) GENUINE BOOST RANGE — some inverters really do reach 1.4-1.6x rated.
        The curve is correct and the ratio is a real product characteristic.

Telling them apart needs a human reading the sheet's own model/AHRI printing.
`band_issue` records WHICH of these is suspected and why; `band_issue_basis`
records the evidence. Flagged, never auto-rejected -- silently dropping (a)
would also drop every legitimate (b).

The check only works when a certificate rated-47 F figure exists. Without one
the row is `unchecked`, which is NOT the same as `ok`.

Usage:
    python HeatPump/pipeline/build_fetch_manifest.py

Output:
    data/interim/datasheet_fetch_manifest.csv
"""

import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INTERIM = ROOT / "data" / "interim"
SPEC_DIR = ROOT / "data" / "raw" / "spec_sheets"

BUCKETS = INTERIM / "hp_buckets.csv"
JOINED = INTERIM / "hp_units_joined.csv"
POINTS = INTERIM / "datasheet_points_v2.json"
CURVES = ROOT / "data" / "processed" / "hp_unit_curves.json"
DEST = INTERIM / "datasheet_fetch_manifest.csv"

BTU_PER_KWH = 3412.14
MAX_RATIO = 1.35

# TIER_SPEC.md 4: the COSTWAY selection is not a credible rating; the RHEEM unit
# from the neighbouring cell is used instead.
SUBSTITUTIONS = {"210727629": "212387098"}


def capacity_band(cap_47):
    if cap_47 is None:
        return "unknown"
    if cap_47 < 18000:
        return "<18k"
    if cap_47 < 30000:
        return "18-30k"
    if cap_47 < 42000:
        return "30-42k"
    return ">=42k"


def read_csv(path):
    if not path.exists():
        sys.exit(f"missing input: {path}")
    with path.open(encoding="utf-8", errors="replace", newline="") as fh:
        return list(csv.DictReader(fh))


def pick_representatives(rows):
    """Most-frequent model per cell, preferring Active certification status."""
    cells = {}
    for row in rows:
        if not row.get("c47"):
            continue
        key = (row["COP band"], row["CM band"], capacity_band(float(row["c47"])))
        cells.setdefault(key, []).append(row)

    reps = {}
    for key, members in cells.items():
        active = [m for m in members if m.get("status") == "Active"]
        rep = max(active or members, key=lambda m: int(m["w"]))
        reps[key] = (rep, sum(int(m["w"]) for m in members), len(members))
    return reps


def main():
    buckets = read_csv(BUCKETS)
    reps = pick_representatives(buckets)
    total = sum(int(r["w"]) for r in buckets)

    certs = {}
    for row in read_csv(JOINED):
        try:
            certs[row["k"].strip()] = float(row["c47"])
        except (TypeError, ValueError, KeyError):
            pass

    points = {}
    if POINTS.exists():
        points = json.loads(POINTS.read_text(encoding="utf-8")).get("units", {})

    curves = {}
    if CURVES.exists():
        curves = json.loads(CURVES.read_text(encoding="utf-8")).get("units", {})

    held = sorted(p.name for p in SPEC_DIR.rglob("*.pdf")) if SPEC_DIR.exists() else []

    out = []
    for (cop_band, cm_band, cap_band), (rep, cell_weight, cell_models) in reps.items():
        ahri = SUBSTITUTIONS.get(rep["k"], rep["k"])
        substituted = ahri != rep["k"]

        unit = points.get(ahri)
        curve = curves.get(ahri)

        cert_47 = certs.get(ahri)
        ds_47_kw = (unit or {}).get("rated_cap_47_kW")

        ratio, band_issue, basis = None, "", ""
        if unit is None:
            band_issue = "not_fetched"
            basis = "no datasheet points digitized for this AHRI number"
        elif cert_47 is None:
            band_issue = "unchecked"
            basis = "no certificate rated 47F capacity available for comparison"
        elif ds_47_kw:
            ratio = ds_47_kw / (cert_47 / BTU_PER_KWH)
            if ratio > MAX_RATIO:
                band_issue = "flagged"
                basis = (f"datasheet 47F max {ds_47_kw * BTU_PER_KWH:,.0f} Btu/h is "
                         f"{ratio:.2f}x the certificate's rated {cert_47:,.0f} Btu/h — "
                         "wrong certified combination, or a genuine wide boost range; "
                         "needs a human reading of the sheet's own AHRI printing")
            else:
                band_issue = "ok"
                basis = f"ratio {ratio:.2f} within the {MAX_RATIO} threshold"

        out.append({
            "ahri_number": ahri,
            "brand": rep["brand"],
            "model": rep["model"],
            "cop_band": cop_band,
            "cm_band": cm_band,
            "capacity_band": cap_band,
            "cell_appearances": cell_weight,
            "cell_share_pct": round(100 * cell_weight / total, 2),
            "cell_models": cell_models,
            "rep_appearances": int(rep["w"]),
            "rep_share_of_cell_pct": round(100 * int(rep["w"]) / cell_weight, 1),
            "substituted_for": rep["k"] if substituted else "",
            "cert_rated_47f_btuh": "" if cert_47 is None else f"{cert_47:.0f}",
            "datasheet_47f_max_btuh": "" if not ds_47_kw else f"{ds_47_kw * BTU_PER_KWH:.0f}",
            "ratio": "" if ratio is None else f"{ratio:.3f}",
            "band_issue": band_issue,
            "band_issue_basis": basis,
            "curve_built": "yes" if curve else "no",
            "n_points": (unit or {}).get("points") and len(unit["points"]) or "",
            "min_op_temp_C": (unit or {}).get("min_op_temp_C", ""),
            "doc": (unit or {}).get("doc", ""),
        })

    out.sort(key=lambda r: -r["cell_share_pct"])
    with DEST.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(out[0].keys()))
        writer.writeheader()
        writer.writerows(out)

    covered = sum(r["cell_share_pct"] for r in out if r["curve_built"] == "yes")
    clean = sum(r["cell_share_pct"] for r in out if r["band_issue"] == "ok")
    print(f"{len(out)} representatives, {len(held)} PDFs held in spec_sheets/")
    print(f"curves built: {sum(1 for r in out if r['curve_built'] == 'yes')} "
          f"({covered:.1f}% of screened appearances)")
    print(f"band_issue ok: {sum(1 for r in out if r['band_issue'] == 'ok')} "
          f"({clean:.1f}%)")
    for issue in ("flagged", "unchecked", "not_fetched"):
        rows = [r for r in out if r["band_issue"] == issue]
        share = sum(r["cell_share_pct"] for r in rows)
        print(f"band_issue {issue}: {len(rows)} ({share:.1f}%)")
    print(f"\nwrote {DEST.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
