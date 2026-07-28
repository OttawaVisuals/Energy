"""
build_unit_curves.py — Phase 3c: normalized per-unit capacity and COP curves.

Turns the digitized datasheet points (data/interim/datasheet_points_v2.json,
written by extract_datasheet_tables.py and extract_matrix_datasheet.py) into the
compact normalized curve the browser engine already consumes:

    { T_C[], cap_frac_of_rated47[], COP[], min_op_temp_C }

resampled onto the engine's uniform 0.5 °C grid. Keyed by AHRI number, so a
scenario in the tool selects a real certified unit rather than an averaged tier.

DESIGN NOTES
------------
* **Normalized on rated-47 °F capacity**, matching the existing hp_curves.json
  contract: the engine multiplies `cap_frac_of_rated47` by the user's nominal
  capacity, so the fractional shape is size-independent. `cap_frac` can exceed
  1.0 below 47 °F — that is real, not a bug: the datasheet points are MAXIMUM
  output, and a variable-speed compressor boosts above its rated point in the
  cold. See TIER_SPEC.md §2.

* **Linear interpolation between published points, no extrapolation beyond
  them.** These are measured data with 15–23 points; fitting a smooth functional
  form would invent structure the measurement does not support and would smear
  the defrost region. Outside the published range the curve is clamped to the
  end points and the engine's own lock-out logic takes over at `min_op_temp_C`.

* **No defrost derate is applied.** Whether a table is already defrost-inclusive
  is manufacturer-specific and recorded per unit as `defrost_inclusive`; the
  consumer decides. (The Phase 3b curves applied a blanket 7% derate between
  −7 and +4 °C to non-inclusive tables — do that downstream if wanted, not here,
  so the stored curve stays a faithful record of the datasheet.)

Usage:
    python pipeline/build_unit_curves.py [--step 0.5]

Output:
    data/processed/hp_unit_curves.json
"""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "data" / "interim" / "datasheet_points_v2.json"
DEST = ROOT / "data" / "processed" / "hp_unit_curves.json"


def interp(x, xs, ys):
    """Linear interpolation with clamping outside the measured range."""
    if x <= xs[0]:
        return ys[0]
    if x >= xs[-1]:
        return ys[-1]
    for i in range(1, len(xs)):
        if x <= xs[i]:
            x0, x1, y0, y1 = xs[i - 1], xs[i], ys[i - 1], ys[i]
            if x1 == x0:
                return y0
            return y0 + (y1 - y0) * (x - x0) / (x1 - x0)
    return ys[-1]


def build(unit, step, ahri_rated47_kW=None, max_ratio=1.35):
    pts = sorted(unit["points"], key=lambda p: p["T_C"])
    if len(pts) < 4:
        return None, f"only {len(pts)} points"

    # The datasheet's own 47 F figure is a MAXIMUM-output capacity; the engine's
    # `cap_frac_of_rated47` contract is normalized on the RATED 47 F capacity
    # (what the user's nominal-capacity input means). Normalizing on the
    # datasheet max instead understates every fraction -- by 6% for the GREE
    # sheet but 43% for the MOOVAIR chart. So normalize on the AHRI certificate's
    # rated 47 F wherever we have it, and fall back to the datasheet only when we
    # do not. cap_frac then legitimately exceeds 1.0 (max boost above rated).
    ds47 = unit.get("rated_cap_47_kW") or interp(
        8.33, [p["T_C"] for p in pts], [p["cap_kW"] for p in pts])
    if not ds47:
        return None, "no 47F capacity in datasheet"

    ratio, review = None, None
    if ahri_rated47_kW:
        ratio = ds47 / ahri_rated47_kW
        # A datasheet 47 F max well above the certified RATED 47 F has two very
        # different causes and they cannot be told apart automatically:
        #   (a) a genuine mismatch -- the sheet is for a different certified
        #       combination (same outdoor unit, different indoor coil/AHU).
        #       GREE 206249116 is a 24,000 Btu/h certificate; the 36,000 Btu/h
        #       extended-ratings table does not describe it.
        #   (b) a legitimately wide boost range -- LG's inverter units really do
        #       reach ~1.6x their rated point at 47 F.
        # So this is FLAGGED FOR REVIEW, not rejected: rejecting would silently
        # drop valid LG data, and accepting silently would ship a wrong curve.
        if ratio > max_ratio:
            review = (f"datasheet 47F max is {ratio:.2f}x the certificate's rated 47F — "
                      f"verify this sheet is the right certified combination")
        rated47, basis = ahri_rated47_kW, "AHRI certificate rated 47F"
    else:
        rated47, basis = ds47, "datasheet 47F (no certificate value available)"

    xs = [p["T_C"] for p in pts]
    caps = [p["cap_kW"] for p in pts]
    cops = [p["COP"] for p in pts]
    if any(c is None for c in cops):
        return None, "one or more points lack a COP"

    lo, hi = xs[0], xs[-1]
    n = int(round((hi - lo) / step))
    grid = [round(lo + i * step, 2) for i in range(n + 1)]

    curve = {
        "ahri_number": unit["ahri_number"],
        "brand": unit.get("brand"),
        "outdoor_model": unit.get("outdoor_model"),
        "refrigerant": unit.get("refrigerant"),
        "doc": unit.get("doc"),
        "basis": unit.get("basis"),
        "defrost_inclusive": unit.get("defrost_inclusive", False),
        "rated_cap_47_kW": round(rated47, 4),
        "normalization_basis": basis,
        "datasheet_max_47_kW": round(ds47, 4),
        "datasheet_to_rated_47_ratio": round(ratio, 3) if ratio else None,
        "review_flag": review,
        "min_op_temp_C": unit.get("min_op_temp_C"),
        "n_source_points": len(pts),
        "source_range_C": [lo, hi],
        "T_C": grid,
        "cap_frac_of_rated47": [round(interp(t, xs, caps) / rated47, 4) for t in grid],
        "COP": [round(interp(t, xs, cops), 3) for t in grid],
    }
    return curve, None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--step", type=float, default=0.5)
    args = ap.parse_args()

    if not SRC.exists():
        print(f"missing {SRC}", file=sys.stderr)
        return 1
    units = json.loads(SRC.read_text(encoding="utf-8")).get("units", {})

    # AHRI certificate rated 47F capacity, the correct normalization denominator.
    #
    # Two sources, because the scrape is not always on disk. If BOTH are absent
    # we must not quietly fall back to the datasheet's own 47F figure: that is
    # TIER_SPEC.md 5 trap 1, it inflates every cap_frac, and -- worse -- it
    # disables the combination-mismatch ratio check entirely, so a datasheet for
    # the wrong certified combination would be accepted in silence.
    lookup_path = ROOT.parent / "lookup" / "ahri_numbers.json"
    joined_path = ROOT / "data" / "interim" / "hp_units_joined.csv"
    certs, cert_source = {}, None
    if lookup_path.exists():
        raw = json.loads(lookup_path.read_text(encoding="utf-8"))
        for k, v in raw.items():
            try:
                certs[k] = float(str(v.get("heating_capacity_47f_btuh")).replace(",", "")) / 3412.14
            except (TypeError, ValueError):
                pass
        cert_source = "lookup/ahri_numbers.json"
    elif joined_path.exists():
        # Derived copy of the same certificate figures (column c47, Btu/h).
        import csv
        with joined_path.open(encoding="utf-8", errors="replace", newline="") as fh:
            for row in csv.DictReader(fh):
                try:
                    certs[row["k"].strip()] = float(row["c47"]) / 3412.14
                except (TypeError, ValueError, KeyError):
                    pass
        cert_source = f"{joined_path.name} (derived; lookup/ absent)"
    print(f"certificate rated-47F source: {cert_source or 'NONE'} ({len(certs)} entries)",
          file=sys.stderr)
    if not certs:
        print("REFUSING TO BUILD: no certificate rated-47F capacities available, so "
              "curves cannot be normalized correctly and the combination-mismatch "
              "check cannot run. See TIER_SPEC.md 7, 'Reproducibility gap'.",
              file=sys.stderr)
        return 1
    if not units:
        print("no units in source", file=sys.stderr)
        return 1

    out, skipped = {}, []
    for ahri, unit in units.items():
        curve, err = build(unit, args.step, certs.get(ahri))
        if err:
            skipped.append((ahri, err))
            continue
        out[ahri] = curve

    DEST.parent.mkdir(parents=True, exist_ok=True)
    DEST.write_text(json.dumps({
        "note": ("Per-unit normalized heat pump curves, Phase 3c. Digitized from "
                 "primary manufacturer datasheets at MAXIMUM heating output, "
                 "normalized on rated 47F capacity, linearly interpolated onto a "
                 "uniform grid with no extrapolation. cap_frac > 1.0 below 47F is "
                 "real (variable-speed boost), not an error. Keyed by AHRI number."),
        "step_C": args.step,
        "units": out,
    }, indent=1), encoding="utf-8")

    print(f"{'AHRI':<11} {'brand':<9} {'model':<20} {'pts':>4} {'range C':>14} "
          f"{'cap@-15':>8} {'COP@-15':>8} {'lockout':>8}")
    for a, c in sorted(out.items()):
        i = c["T_C"].index(min(c["T_C"], key=lambda t: abs(t + 15)))
        print(f"{a:<11} {str(c['brand'])[:9]:<9} {str(c['outdoor_model'])[:20]:<20} "
              f"{c['n_source_points']:>4} {str(c['source_range_C']):>14} "
              f"{c['cap_frac_of_rated47'][i]:>8.3f} {c['COP'][i]:>8.2f} "
              f"{c['min_op_temp_C']:>8}")
    if skipped:
        print("\nskipped:")
        for a, e in skipped:
            print(f"  {a}: {e}")
    print(f"\nwrote {DEST} — {len(out)} unit curves")
    return 0


if __name__ == "__main__":
    sys.exit(main())
