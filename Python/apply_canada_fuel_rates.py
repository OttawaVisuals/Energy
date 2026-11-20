"""
apply_canada_fuel_rates.py

Fills heating oil, propane and heating wood in utility_rates_reference.json/.csv
with ONE national figure per fuel, applied to every province.

Why: the 2026-11-19 check of the retrofits.html "Energy bill" card found ON/QC/AB
(and every other province) had NO oil / propane / wood price -- the columns were
empty, so homeCost() silently priced those fuels at $0. This script restores them
without the manual per-city NRCan Excel exports that add_oil_propane_rates.py needs.

Inputs (hard-coded below, copied by hand from NRCan "Prices by City", "Canada" column):
  Furnace oil  230.4 c/L, week ending 2026-11-17  (productID=7; NRCan: "Prices include taxes")
  Auto propane 129.1 c/L, week ending 2026-11-17  (productID=6)
  Wood pellets $0.0600/kWh -- the flat figure from add_oil_propane_rates.py
               (Canadian Biomass Magazine 2Q 2025; currency/ton/BTU are ASSUMPTIONS).
  https://www2.nrcan.gc.ca/eneene/sources/pripri/prices_bycity_e.cfm

Output: patches utility_rates_reference.json and .csv in place (both gitignored,
published via gh-pages). Everything is tagged low-confidence "canada_average_nrcan":
a national average, NOT a provincial price. Oil is volatile (2026: 157 c/L in Jan,
231 in Mar, 230 now); the latest week is used because the card says "current rates".

Run order: utility_rates_reference.py -> (add_oil_propane_rates.py OR this) ->
override_electricity_rates.py. Does not touch electricity or natural gas.
"""

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_JSON = REPO_ROOT / "utility_rates_reference.json"
OUTPUT_CSV = REPO_ROOT / "utility_rates_reference.csv"

PERIOD = "2026-11-17"
OIL_CENTS_PER_L = 230.4
PROPANE_CENTS_PER_L = 129.1
WOOD_CAD_PER_KWH = 0.0600  # = round(290 / (16.5e6 / 3412.14), 4); see add_oil_propane_rates.py

NOTE = ("National average (NRCan 'Canada' column, week ending %s), applied to every province -- "
        "not a provincial price.")

WOOD_ASSUMPTIONS = (
    "Price assumed CAD per short ton (2,000 lb); source is a chart image, not machine-readable.",
    "Energy content assumed 16.5 million BTU/ton HHV (premium wood pellets).",
    "$290/ton / 4,835.7 kWh/ton = $0.0600/kWh. May be wholesale, not residential retail.",
)


def fuel_entry(cents):
    return {
        "cad_per_litre": round(cents / 100.0, 4),
        "n_cities": 0,
        "source": "canada_average_nrcan",
        "confidence": "low",
        "notes": [NOTE % PERIOD],
        "sources": [{"city": "Canada (national average)", "cents_per_litre": cents, "period": PERIOD}],
    }


def main():
    doc = json.loads(OUTPUT_JSON.read_text(encoding="utf-8"))
    for p, entry in doc["provinces"].items():
        entry["heating_oil"] = fuel_entry(OIL_CENTS_PER_L)
        entry["propane"] = fuel_entry(PROPANE_CENTS_PER_L)
        entry["heating_wood"] = {
            "cad_per_kwh": WOOD_CAD_PER_KWH,
            "source": "canadian_biomass_magazine_flat",
            "confidence": "low",
            "notes": list(WOOD_ASSUMPTIONS),
        }

    src = doc.setdefault("source", {})
    src["heating_oil_propane"] = {
        "name": "NRCan Prices by City -- 'Canada' national-average column (Furnace Oil / Auto Propane)",
        "url": "https://www2.nrcan.gc.ca/eneene/sources/pripri/prices_bycity_e.cfm",
        "vintage": f"week ending {PERIOD}, hand-copied 2026-11-19",
        "method": "one national figure per fuel applied to every province; latest week, taxes included",
        "caveat": "Oil is volatile (157 c/L Jan 2026, 231 Mar, 230 Nov). Not provincial.",
    }
    src["heating_wood"] = {
        "name": "Canadian Biomass Magazine -- North America heating wood pellet market update, 2Q 2025",
        "url": "https://www.canadianbiomassmagazine.ca/north-america-heating-wood-pellet-market-update-2q-2025/",
        "method": "single flat $290/ton figure applied to every province",
        "assumptions": list(WOOD_ASSUMPTIONS),
    }
    units = doc.setdefault("units", {})
    units["heating_oil"] = "cad_per_litre"
    units["propane"] = "cad_per_litre"
    units["heating_wood"] = "cad_per_kwh (delivered heat content)"
    OUTPUT_JSON.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"wrote {OUTPUT_JSON}")

    def f(v, nd):
        return f"{v:.{nd}f}" if v is not None else ""

    lines = ["province,elec_cents_per_kwh,elec_source,elec_confidence,"
             "gas_dollars_per_m3,gas_source,"
             "heating_oil_cad_per_litre,heating_oil_source,"
             "propane_cad_per_litre,propane_source,"
             "heating_wood_cad_per_kwh"]
    for p in sorted(doc["provinces"]):
        e = doc["provinces"][p].get("electricity", {})
        g = doc["provinces"][p].get("natural_gas", {})
        o, pr, w = (doc["provinces"][p][k] for k in ("heating_oil", "propane", "heating_wood"))
        lines.append(",".join([
            p, f(e.get("cents_per_kwh"), 3), e.get("source", ""), e.get("confidence", ""),
            f(g.get("dollars_per_m3"), 4), g.get("source", ""),
            f(o["cad_per_litre"], 4), o["source"], f(pr["cad_per_litre"], 4), pr["source"],
            f(w["cad_per_kwh"], 4),
        ]))
    OUTPUT_CSV.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {OUTPUT_CSV}")


if __name__ == "__main__":
    main()
