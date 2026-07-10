"""
extract_neep_points.py — Phase 3b helper.

Pulls the AHRI-certified heating performance points (capacity + COP at
47/17/5 F and the Lowest Cataloged Temperature, at max-compressor speed,
plus the rated-47 F capacity used for normalization) out of the NEEP
`HP Report` sheet for the specific models Phase 3b builds curves from, and
for the 10 AHRI-popularity-matched "average installed" units.

These four AHRI points (8.3 / -8.3 / -15 C + LCT) span the whole
Ottawa-relevant range and are *real certified data*, so they are the backbone
of the per-model capacity(T)/COP(T) curves. Manufacturer extended tables
(where openly published, e.g. Mitsubishi submittals) are digitized separately
and used to cross-check / add resolution — see METHODOLOGY.md.

The 60 MB workbook takes ~30 s to open; this script does a single pass and
writes HeatPump/data/interim/neep_points_selected.json.
"""
from __future__ import annotations
import json, re
from collections import defaultdict
from pathlib import Path
import numpy as np
import openpyxl

ROOT = Path(__file__).resolve().parents[2]
HP = ROOT / "HeatPump"
XLSX = sorted((HP / "data/raw/neep").glob("neep_air_source_heat_pump_*.xlsx"))[-1]
OUT = HP / "data/interim/neep_points_selected.json"

BTU_TO_KW = 0.29307107 / 1000.0

# Selected representative models per tier (outdoor model number, exact NEEP
# string) + the AHRI-popularity-matched units. `role` documents why each is in.
# When several brand-owners rebadge one chassis we keep the brand-owner whose
# combos we quote, chosen below by `prefer_owner` (else the modal combo).
SELECTED = {
    # tier -> list of (outdoor_model, label, prefer_owner_substr)
    1: [("PUZ-HA36NKA", "Mitsubishi P-series PUZ-HA36NKA (hyper-heat)", "Mitsubishi"),
        ("SL22KLV-036-230A**", "Lennox SL22KLV-036", "Lennox"),
        ("D5CUHAH18AAK", "Carrier/Midea D5F D5CUHAH18AAK", "Carrier")],
    2: [("D5CURAH24AAK", "Carrier/Midea Crossover D5CURAH24AAK", "Carrier"),
        ("DLCURAH24ABK", "Carrier/Midea DLF DLCURAH24ABK", "Carrier"),
        ("AM048FCMDCG", "Samsung DVM S Mini AM048FCMDCG", "Samsung")],
    3: [("GUD36W/A-D(U)", "Gree GUD36W/A-D(U) (most-installed)", "Gree"),
        ("MUZ-GS12NAH***", "Mitsubishi M-series MUZ-GS12NAH", "Mitsubishi"),
        ("MO1AE-H48B-2A", "Carrier/Midea MO1 MO1AE-H48B-2A", "Midea")],
}

# The 10 AHRI-popularity-matched outdoor units (report), with ERS occurrence
# weights, for the popularity-weighted "average installed" curve.
AHRI_MATCHED = [
    ("GUD36W/A-D(U)", 5465 + 5152, "Gree"),     # AHRI 206249117 + 211644151
    ("KU36UHO", 4820, "Kinghome"),               # 212361362
    ("38MARBQ24AA3", 3337, "Carrier"),           # 207098550
    ("LSU120HSV5", 2298, "LG"),                  # 10570123
    ("DMA24HOS20230E7", 2167, "Moovair"),        # 212361759
    ("TU36-24WADU", 2153 + 2063, "Tosot"),       # 206414273 + 212361366
    ("BX30-24HPHYHA", 1991, "Bladex"),           # 212367433
    ("3MXL24WMVJU*", 1791, "Daikin"),            # 205663358 (fuzzy)
]

WANTED = set()
for lst in SELECTED.values():
    for m, _, _ in lst:
        WANTED.add(m)
for m, _, _ in AHRI_MATCHED:
    WANTED.add(m)


def num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return np.nan


def main():
    print(f"[extract] opening {XLSX.name} (~30 s) ...", flush=True)
    wb = openpyxl.load_workbook(XLSX, read_only=True, data_only=True)
    ws = wb["HP Report"]
    it = ws.iter_rows(values_only=True)
    next(it)
    header = [(h or "").strip() for h in next(it)]
    col = {re.sub(r"[⁺⁻\+]+$", "", h): i for i, h in enumerate(header)}

    def c(n):
        return col[n]

    KO, KB, KBO = c("Outdoor Unit Model Number"), c("Brand Name"), c("Brand Owner")
    LCT = c("Lowest Cataloged Temperature (Outdoor Dry Bulb °F)")
    REF = c("Refrigerant")
    # capacity / cop columns (max-speed envelope + rated-47 for normalization)
    CAP = {"47r": c("Rated Capacity 47°F"), "47m": c("Max Capacity 47°F"),
           "17m": c("Max Capacity 17°F"), "5m": c("Max Capacity 5°F"),
           "lctm": c("Max Capacity LCT°F")}
    COP = {"47r": c("COP Rated 47°F"), "47m": c("COP Max 47°F"),
           "17m": c("COP Max 17°F"), "5m": c("COP Max 5°F"),
           "lctm": c("COP Max LCT°F")}

    rows = defaultdict(list)
    for r in it:
        if r[KO] in WANTED:
            rows[(r[KO], r[KBO], r[KB])].append(r)
    print(f"[extract] found {len(rows)} (model,owner,brand) groups", flush=True)

    def pick_combo(model, prefer):
        """Choose one representative combo group for a model: prefer a
        brand-owner matching `prefer`, then the group with the most combos."""
        cands = [(k, rs) for k, rs in rows.items() if k[0] == model]
        if not cands:
            return None
        if prefer:
            pl = prefer.lower()
            pref = [(k, rs) for k, rs in cands
                    if pl in f"{k[1]} {k[2]}".lower()]
            if pref:
                cands = pref
        # among remaining, the group with the most combos (modal certification)
        k, rs = max(cands, key=lambda kr: len(kr[1]))
        return k, rs

    def digitize(model, prefer):
        got = pick_combo(model, prefer)
        if got is None:
            return None
        (om, bo, bn), rs = got
        lcts = [num(x[LCT]) for x in rs if num(x[LCT]) == num(x[LCT])]
        lct_f = float(np.median(lcts)) if lcts else None
        lct_c = round((lct_f - 32) * 5 / 9, 1) if lct_f is not None else None

        def med(colmap, key):
            v = np.nanmedian([num(x[colmap[key]]) for x in rs])
            return None if v != v else float(v)

        rated47_btu = med(CAP, "47r")
        # capacity(T) points (max-speed) in kW, with temps in C
        pts = []
        for key, tC in [("47m", 8.33), ("17m", -8.33), ("5m", -15.0),
                        ("lctm", lct_c)]:
            cap = med(CAP, key)
            cop = med(COP, key)
            if cap is None or cop is None or tC is None:
                continue
            pts.append({"T_C": round(tC, 2), "cap_kW": round(cap * BTU_TO_KW, 4),
                        "COP": round(cop, 3), "src": f"NEEP {key}"})
        return {
            "outdoor_model": om, "brand_owner": bo, "brand": bn,
            "refrigerant": rs[0][REF], "n_combos": len(rs),
            "rated_cap_47_kW": round(rated47_btu * BTU_TO_KW, 4) if rated47_btu else None,
            "min_op_temp_C": lct_c if lct_c is not None else -15.0,
            "has_lct": lct_f is not None,
            "points": pts,
        }

    out = {"source": XLSX.name, "note": "AHRI-certified max-speed heating "
           "points from NEEP HP Report; capacity kW, temps C.",
           "tiers": {}, "ahri_matched": []}
    for tier, lst in SELECTED.items():
        out["tiers"][tier] = []
        for model, label, prefer in lst:
            d = digitize(model, prefer)
            if d is None:
                print(f"  !! not found: {model}")
                continue
            d["label"] = label
            out["tiers"][tier].append(d)
            print(f"  T{tier} {label}: {len(d['points'])} pts "
                  f"rated47={d['rated_cap_47_kW']}kW min_op={d['min_op_temp_C']}C")
    for model, weight, prefer in AHRI_MATCHED:
        d = digitize(model, prefer)
        if d is None:
            print(f"  !! matched not found: {model}")
            continue
        d["weight"] = weight
        out["ahri_matched"].append(d)
        print(f"  matched {model} w={weight}: {len(d['points'])} pts")

    OUT.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"[out] wrote {OUT}")


if __name__ == "__main__":
    main()
