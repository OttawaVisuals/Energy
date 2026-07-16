"""
build_datasheet_points.py — Phase 3b (re-sourced).

Encodes the AHRI-certified / manufacturer-published heating performance of the
representative heat pump per tier, digitized from each unit's PRIMARY PUBLIC
datasheet (submittal / product data), and emits
`data/interim/datasheet_points.json` — the public, license-clean replacement
for the NEEP-derived backbone (`neep_points_selected.json`), consumed by
`build_hp_curves.py`.

Convention (matches the prior NEEP backbone so results stay comparable, see
METHODOLOGY.md "Heat pump performance curves (Phase 3b)"):
- MAX-output heating operation (what a cold home calling for full heat draws).
- Per point: (T_C, capacity kW, COP).  COP may be null for a CAPACITY-ONLY
  point (e.g. a published low-temperature capacity-retention figure whose
  max-speed COP the manufacturer does not publish); build_hp_curves builds the
  COP curve from the non-null points and extrapolates/floors below the coldest
  one, exactly as before.
- COP computed from the datasheet as  cap_BTU x 0.29307107 / power_W, or taken
  directly where the datasheet prints a COP (Daikin), or from the Mitsubishi
  headline COPs. Capacities in BTU/h converted to kW; Carrier/Daikin tables are
  in MBtuh (thousand BTU/h).
- `defrost_inclusive`: Carrier "Integrated" capacities are defrost-adjusted
  (True -> build skips the 7% derate); Mitsubishi/Daikin points are steady-state
  (False -> 7% derate applied in the frost band, as before).

Tiers are the SAME premium/mid/baseline structure. NEEP is used ONLY as a local
tier-DEFINITION reference (Phase 3a) and is never shipped. `average_installed`
is mapped to the Tier-3 curve downstream (per project decision).

Every number below is traceable to a downloaded PDF in
`data/raw/spec_sheets/<brand>/` (see `doc`). Run: python pipeline/build_datasheet_points.py
"""
from __future__ import annotations
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HP = ROOT / "HeatPump"
OUT = HP / "data/interim/datasheet_points.json"

BTU_TO_KW = 0.29307107 / 1000.0     # BTU/h -> kW
MBH_TO_KW = 0.29307107              # MBtuh (1000 BTU/h) -> kW


def cop_from_power(cap_btu, power_w):
    """COP = thermal kW / electrical kW."""
    return round(cap_btu * BTU_TO_KW / (power_w / 1000.0), 3)


# --------------------------------------------------------------------------
# Representative model per tier, from PRIMARY manufacturer datasheets.
# Each `points` entry: (T_C, cap_kW, COP_or_None, src).
# --------------------------------------------------------------------------
def P(T_C, cap_kW, cop, src):
    return {"T_C": T_C, "cap_kW": round(cap_kW, 4), "COP": cop, "src": src}


MODELS = {
    1: [
        {
            "outdoor_model": "MUZ-FH12NAH", "brand": "Mitsubishi Electric",
            "brand_owner": "Mitsubishi Electric", "refrigerant": "R-410A",
            "label": "Mitsubishi MUZ-FH12NAH (H2i cold-climate ductless)",
            "doc": "Mitsubishi Electric Submittal SB_MSZ-FH12NA_&_MUZ-FH12NAH(-1)_201910, p.1",
            "defrost_inclusive": False, "rated_cap_47_kW": 13600 * BTU_TO_KW,
            "min_op_temp_C": -25.0,
            # 47F/17F rated & max cap+power published; 5F max cap (100% retention);
            # -13F 62% retention (published %). Max-speed COP@5F/-13F not published.
            "points": [
                P(8.33, 13600 * BTU_TO_KW, cop_from_power(13600, 950), "datasheet 47F rated (13600 BTU / 950 W)"),
                P(-8.33, 13600 * BTU_TO_KW, cop_from_power(13600, 1900), "datasheet 17F max (13600 BTU / 1900 W)"),
                P(-15.0, 13600 * BTU_TO_KW, None, "datasheet 5F max cap (100% retention)"),
                P(-25.0, 0.62 * 13600 * BTU_TO_KW, None, "datasheet -13F 62% retention"),
            ],
        },
        {
            "outdoor_model": "PUZ-HA36NKA", "brand": "Mitsubishi Electric",
            "brand_owner": "Mitsubishi Electric", "refrigerant": "R-410A",
            "label": "Mitsubishi P-series PUZ-HA36NKA (hyper-heat ducted)",
            "doc": "Mitsubishi Electric Submittal SB_PVA-A36AA7_PUZ-HA36NKA_202401, p.1",
            "defrost_inclusive": False, "rated_cap_47_kW": 38000 * BTU_TO_KW,
            "min_op_temp_C": -25.0,
            # All points published (cap + COP). COP@47 rated; 17/5/-13 max-capacity COPs.
            "points": [
                P(8.33, 38000 * BTU_TO_KW, 3.90, "datasheet 47F COP 3.90"),
                P(-8.33, 38000 * BTU_TO_KW, 2.27, "datasheet 17F max COP 2.27"),
                P(-15.0, 38000 * BTU_TO_KW, 2.17, "datasheet 5F max COP 2.17"),
                P(-25.0, 30400 * BTU_TO_KW, 1.50, "datasheet -13F max COP 1.50"),
            ],
        },
    ],
    2: [
        {
            "outdoor_model": "25HNB9", "brand": "Carrier", "brand_owner": "Carrier",
            "refrigerant": "R-410A", "label": "Carrier Infinity 19 25HNB9 (2-stage ducted)",
            "doc": "Carrier Product Data 25HNB9-2PD, Heating Performance 25HNB936 High stage (defrost-integrated)",
            "defrost_inclusive": True, "rated_cap_47_kW": 36.48 * MBH_TO_KW,
            "min_op_temp_C": -19.4,
            # High-stage integrated capacity (MBtuh) + system kW, per outdoor temp.
            "points": [
                P(8.33, 36.48 * MBH_TO_KW, round(36.48 * MBH_TO_KW / 2.51, 3), "datasheet 47F 36.48 MBh / 2.51 kW"),
                P(2.78, 28.64 * MBH_TO_KW, round(28.64 * MBH_TO_KW / 2.33, 3), "datasheet 37F 28.64/2.33"),
                P(-2.78, 23.86 * MBH_TO_KW, round(23.86 * MBH_TO_KW / 2.17, 3), "datasheet 27F 23.86/2.17"),
                P(-8.33, 19.64 * MBH_TO_KW, round(19.64 * MBH_TO_KW / 2.01, 3), "datasheet 17F 19.64/2.01"),
                P(-13.9, 15.49 * MBH_TO_KW, round(15.49 * MBH_TO_KW / 1.88, 3), "datasheet 7F 15.49/1.88"),
                P(-19.4, 11.42 * MBH_TO_KW, round(11.42 * MBH_TO_KW / 1.75, 3), "datasheet -3F 11.42/1.75"),
            ],
        },
        {
            "outdoor_model": "DZ20VC", "brand": "Daikin", "brand_owner": "Daikin",
            "refrigerant": "R-410A", "label": "Daikin DZ20VC (inverter variable-speed ducted)",
            "doc": "Daikin Product Data SS-DZ20VC, Expanded Heating Data High Stage, DZ20VC0361 (steady-state)",
            "defrost_inclusive": False, "rated_cap_47_kW": 35.0 * MBH_TO_KW,
            "min_op_temp_C": -23.3,
            # High-stage MBtuh + published COP; real mode-shift boost below 35F.
            "points": [
                P(8.33, 35.0 * MBH_TO_KW, 4.14, "datasheet 47F COP 4.14"),
                P(1.67, 29.1 * MBH_TO_KW, 3.61, "datasheet 35F COP 3.61"),
                P(-1.11, 35.9 * MBH_TO_KW, 2.65, "datasheet 30F COP 2.65 (mode shift)"),
                P(-8.33, 28.8 * MBH_TO_KW, 2.27, "datasheet 17F COP 2.27"),
                P(-15.0, 22.1 * MBH_TO_KW, 1.86, "datasheet 5F COP 1.86"),
                P(-23.3, 13.4 * MBH_TO_KW, 1.24, "datasheet -10F COP 1.24"),
            ],
        },
    ],
    3: [
        {
            "outdoor_model": "25HNB5", "brand": "Carrier", "brand_owner": "Carrier",
            "refrigerant": "R-410A", "label": "Carrier Infinity 15 25HNB5 (single-stage ducted)",
            "doc": "Carrier Product Data 25HNB5-3PD, Heating Performance 25HNB536 (defrost-integrated)",
            "defrost_inclusive": True, "rated_cap_47_kW": 35.11 * MBH_TO_KW,
            "min_op_temp_C": -19.4,
            "points": [
                P(8.33, 35.11 * MBH_TO_KW, round(35.11 * MBH_TO_KW / 2.52, 3), "datasheet 47F 35.11/2.52"),
                P(2.78, 27.29 * MBH_TO_KW, round(27.29 * MBH_TO_KW / 2.39, 3), "datasheet 37F 27.29/2.39"),
                P(-2.78, 21.68 * MBH_TO_KW, round(21.68 * MBH_TO_KW / 2.26, 3), "datasheet 27F 21.68/2.26"),
                P(-8.33, 17.88 * MBH_TO_KW, round(17.88 * MBH_TO_KW / 2.15, 3), "datasheet 17F 17.88/2.15"),
                P(-13.9, 14.09 * MBH_TO_KW, round(14.09 * MBH_TO_KW / 2.06, 3), "datasheet 7F 14.09/2.06"),
                P(-19.4, 10.52 * MBH_TO_KW, round(10.52 * MBH_TO_KW / 1.97, 3), "datasheet -3F 10.52/1.97"),
            ],
        },
        {
            "outdoor_model": "MUZ-HM12NA2", "brand": "Mitsubishi Electric",
            "brand_owner": "Mitsubishi Electric", "refrigerant": "R-410A",
            "label": "Mitsubishi MUZ-HM12NA2 (standard ductless)",
            "doc": "Mitsubishi Electric MSZ-HM12NA-U1 & MUZ-HM12NA2-U8 Product Data Sheet",
            "defrost_inclusive": False, "rated_cap_47_kW": 12200 * BTU_TO_KW,
            "min_op_temp_C": -15.0,
            # Standard (non cold-climate) minisplit: capacity falls off, warmer lockout.
            "points": [
                P(8.33, 12200 * BTU_TO_KW, cop_from_power(12200, 990), "datasheet 47F rated (12200 BTU / 990 W) COP 3.61"),
                P(-8.33, 9000 * BTU_TO_KW, 2.78, "datasheet 17F max cap 9000 BTU, COP 2.78"),
                P(-15.0, 7500 * BTU_TO_KW, None, "datasheet 5F max cap 7500 BTU"),
            ],
        },
    ],
}


def main():
    out = {
        "note": "Max-output heating points digitized from PRIMARY public "
                "manufacturer datasheets (submittal / product data). Capacity kW, "
                "temps C, COP dimensionless (null = capacity-only point). Replaces "
                "the NEEP backbone; NEEP is used only as a local tier-definition "
                "reference and is never shipped.",
        "tiers": {},
    }
    for tier, mlist in MODELS.items():
        out["tiers"][str(tier)] = mlist
        for m in mlist:
            m["rated_cap_47_kW"] = round(m["rated_cap_47_kW"], 4)
            npts = len(m["points"])
            ncop = sum(1 for p in m["points"] if p["COP"] is not None)
            print(f"  T{tier} {m['outdoor_model']}: {npts} pts ({ncop} with COP), "
                  f"rated47={m['rated_cap_47_kW']}kW min_op={m['min_op_temp_C']}C "
                  f"defrost_incl={m['defrost_inclusive']}")
    OUT.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"[out] wrote {OUT}")


if __name__ == "__main__":
    main()
