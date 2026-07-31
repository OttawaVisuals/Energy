"""
override_electricity_rates.py

Replaces the 'electricity' block in utility_rates_reference.json (built by
utility_rates_reference.py, then add_oil_propane_rates.py) with rates from
a secondary source, after the primary source (a scrape of
MaxPr1me/canada-utility-rates) was caught giving a stale Saskatchewan rate:
9.28 c/kWh dated 2025-01-01, when SaskPower's own published rate schedule
(verified directly against their PDF) is 15.476 c/kWh effective 2026-02-01 —
a ~67% understatement that the pipeline had flagged "high confidence". A
forced re-download of the upstream source reproduced the same stale number,
confirming the gap is in canada-utility-rates itself, not a local cache.

New source: https://offgridsolarsystem.ca/blog/Canada-electricity-rates.html
("Updated: July 1, 2026"), a third-party rate-aggregation blog, not a
government or utility-primary source. Chosen because it was independently
verifiable (spot-checked SK against SaskPower's own PDF and it matched
exactly) and gives full national coverage in one place — but it is NOT a
utility-tariff-level source like the one it replaces, and most entries here
have NOT been independently re-verified against each province's own utility
the way SK was. FLAGGED FOR FURTHER INVESTIGATION — see docs/RETROFIT_COSTS.md.

Rate selection per province: where the blog separately states an energy-only
commodity/delivery rate (SK, NS), that figure is used — matching this
pipeline's existing "volumetric energy only" methodology (fixed monthly
charges are deliberately excluded everywhere else because they largely
cancel in a pre/post retrofit delta; a blended rate that folds an assumed
usage level's fixed-charge share INTO the c/kWh figure would NOT cancel
correctly the same way). Everywhere else, the blog only publishes an
all-in blended headline rate, which is used as-is — a known limitation,
since it embeds the blog's own assumed "typical usage", not each ERS home's
actual usage. BC/YT/NT are ranges in the source; the range midpoint (BC
uses BC Hydro's own Step 1) is used as the point estimate, full range kept
in notes.

Natural gas, heating oil, propane, and heating wood are UNCHANGED — still
from canada-utility-rates / NRCan (see utility_rates_reference.py,
add_oil_propane_rates.py). Gas has the same staleness risk pattern (SK gas's
own effective_date is 2024-10-01, ~2 years stale) but was not independently
re-verified this round — flagged, not fixed, per the same "investigate more"
note.

Usage:
    python override_electricity_rates.py
    (run after utility_rates_reference.py + add_oil_propane_rates.py)
"""

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_JSON = REPO_ROOT / "utility_rates_reference.json"
OUTPUT_CSV = REPO_ROOT / "utility_rates_reference.csv"

SOURCE_URL = "https://offgridsolarsystem.ca/blog/Canada-electricity-rates.html"
SOURCE_VINTAGE = "2026-07-01 (page's own 'Updated' date)"

# {province: (cents_per_kwh, note)}
# cents_per_kwh is the energy-only rate where the blog breaks one out (SK, NS),
# else the blog's own all-in blended headline figure (see module docstring).
NEW_ELECTRICITY = {
    "QC": (8.30,  "Hydro-Québec, blog's blended/tiered-average headline figure."),
    "MB": (10.60, "Manitoba Hydro, standard residential; blog notes a 4% increase effective 2026-01-01."),
    "BC": (10.97, "BC Hydro Step 1 (blog's headline choice) — BC Hydro Step 2 is 14.08c, "
                  "flat option 12.63c, FortisBC ~15.80c; not independently reconciled which "
                  "best represents a typical ERS home's usage."),
    "NB": (15.40, "NB Power standard residential, effective 2026-04-14, blog's blended headline "
                  "(includes an annual VAR surcharge per the source)."),
    "ON": (17.00, "OEB Regulated Price Plan, blog's blended TOU/tiered headline, effective 2025-11-01 "
                  "commodity update, includes delivery."),
    "NL": (15.80, "NL Hydro/Newfoundland Power, blog's blended average."),
    "NS": (19.128, "NS Power energy rate only (blog separately states $20.08/month base charge, "
                   "excluded here per this pipeline's volumetric-only convention), effective 2026-05-01."),
    "PE": (19.70, "Maritime Electric/IRAC, blog's blended tiered-residential headline; "
                  "no general rate increase filed for 2026 per the source."),
    "YT": (21.00, "Yukon Energy/ATCO Electric Yukon — blog gives an 18.0-24.0c/kWh tiered range "
                  "with riders included; 21.0 is the range MIDPOINT, not a directly published single rate."),
    "SK": (15.476, "SaskPower energy charge only (basic monthly charge $31.16/mo excluded per this "
                   "pipeline's volumetric-only convention), effective 2026-02-01 — independently "
                   "verified against SaskPower's own published rate PDF, exact match."),
    "AB": (22.90, "Regulated Rate Option, blog's blended headline (~12.0c/kWh RoLR commodity, fixed "
                  "through Dec 2026, + distribution/transmission) — replaces this pipeline's prior "
                  "screening-constant workaround for AB's missing transmission/commodity components."),
    "NT": (29.50, "NTPC/Naka Power — blog gives a 25.0-34.0c/kWh range 'after subsidy' (Territorial "
                  "Power Support Program subsidizes the first ~1,000 kWh/month in winter); 29.5 is the "
                  "range MIDPOINT. This is a post-subsidy effective rate, a different quantity than "
                  "this pipeline's other entries (pre-subsidy published tariffs)."),
    "NU": (35.40, "Qulliq Energy Corp., diesel generation, blog states this already includes subsidies "
                  "— same post-subsidy caveat as NT."),
}


def main():
    doc = json.loads(OUTPUT_JSON.read_text(encoding="utf-8"))

    for prov, (cents, note) in NEW_ELECTRICITY.items():
        if prov not in doc["provinces"]:
            doc["provinces"][prov] = {}
        old = doc["provinces"][prov].get("electricity")
        doc["provinces"][prov]["electricity"] = {
            "cents_per_kwh": cents,
            "n_utilities": None,
            "confidence": "unverified" if prov != "SK" else "verified_against_primary",
            "source": "offgridsolarsystem_blog",
            "notes": [note, "FLAGGED: secondary/blog source, not independently re-verified for "
                             "this province — see docs/RETROFIT_COSTS.md changelog 2026-07-31."],
            "sources": [{"note": "see NEW_ELECTRICITY in override_electricity_rates.py"}],
            "superseded": old,   # keep the old canada-utility-rates entry for reference/rollback
        }

    doc.setdefault("source", {})["electricity_override"] = {
        "name": "offgridsolarsystem.ca — Canada electricity rates by province",
        "url": SOURCE_URL,
        "vintage": SOURCE_VINTAGE,
        "reason": "Primary source (canada-utility-rates scrape) caught giving a stale SK rate "
                  "(9.28 c/kWh dated 2025-01-01 vs SaskPower's own current 15.476 c/kWh effective "
                  "2026-02-01, ~67% understated, was flagged 'high confidence'). Re-fetching the "
                  "primary source did not fix it, confirming the gap is upstream, not a cache issue.",
        "status": "Electricity only. Not independently re-verified province-by-province (SK is the "
                  "one exception — matches SaskPower's own PDF exactly). Needs further investigation "
                  "before this confidence should be raised.",
    }
    doc.setdefault("units", {})["electricity"] = "cents_per_kwh (energy-only where available, else " \
                                                  "blog's all-in blended headline — see per-province notes)"

    OUTPUT_JSON.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"wrote {OUTPUT_JSON}")

    # Regenerate the CSV's electricity columns (mirrors add_oil_propane_rates.py's writer)
    lines = ["province,elec_cents_per_kwh,elec_source,elec_confidence,"
             "gas_dollars_per_m3,gas_source,"
             "heating_oil_cad_per_litre,heating_oil_source,"
             "propane_cad_per_litre,propane_source,"
             "heating_wood_cad_per_kwh"]
    for p in sorted(doc["provinces"]):
        e = doc["provinces"][p].get("electricity", {})
        g = doc["provinces"][p].get("natural_gas", {})
        o = doc["provinces"][p].get("heating_oil", {})
        pr = doc["provinces"][p].get("propane", {})
        w = doc["provinces"][p].get("heating_wood", {})
        lines.append(",".join([
            p,
            f"{e.get('cents_per_kwh', ''):.3f}" if e.get('cents_per_kwh') is not None else "",
            e.get("source", ""),
            e.get("confidence", ""),
            f"{g.get('dollars_per_m3', ''):.4f}" if g.get('dollars_per_m3') is not None else "",
            g.get("source", ""),
            f"{o.get('cad_per_litre', ''):.4f}" if o.get('cad_per_litre') is not None else "",
            o.get("source", ""),
            f"{pr.get('cad_per_litre', ''):.4f}" if pr.get('cad_per_litre') is not None else "",
            pr.get("source", ""),
            f"{w.get('cad_per_kwh', ''):.4f}" if w.get('cad_per_kwh') is not None else "",
        ]))
    OUTPUT_CSV.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {OUTPUT_CSV}")

    print("\nNew electricity rates:")
    for p in sorted(NEW_ELECTRICITY):
        cents, _ = NEW_ELECTRICITY[p]
        print(f"  {p}: {cents:.3f} c/kWh")


if __name__ == "__main__":
    main()
