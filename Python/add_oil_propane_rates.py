"""
add_oil_propane_rates.py

Adds heating-oil and propane prices to utility_rates_reference.json/.csv
(built by utility_rates_reference.py) from two NRCan "Prices by City" Excel
exports:
  https://www2.nrcan.gc.ca/eneene/sources/pripri/prices_bycity_e.cfm
  (productID=7 "Furnace Oil", productID=6 "Auto Propane")

Unlike the electricity/gas source (a scraped JSON API), NRCan's by-city page
has no stable machine-readable endpoint — it's a manually-downloaded Excel
export per fuel. This script is therefore a manual-refresh step: re-download
both files from the URL above (same locationID query string selects "all
cities") and re-run whenever the reference table needs updating.

Both workbooks share one layout: a few title rows, a city-name header row
(each city spanning several columns — Price/Taxes[/Marketing/Refining
Margin]), a sub-header row, then one data row per period (monthly for
furnace oil, weekly for propane) with the most recent period last. Only the
"Price" column per city is used; the latest non-blank value per city is
taken (coverage varies — a city can have a blank latest week/month with
data in an earlier one), then averaged (simple mean, unweighted) across the
cities NRCan surveys in each province.

Cities NRCan surveys with no clear province mapping are flagged, not
guessed silently — see CITY_PROVINCE_NOTES.

Usage:
    python add_oil_propane_rates.py <furnace_oil.xlsx> <auto_propane.xlsx>
"""

import json
import sys
from pathlib import Path

import openpyxl

REPO_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_JSON = REPO_ROOT / "utility_rates_reference.json"
OUTPUT_CSV = REPO_ROOT / "utility_rates_reference.csv"

# NRCan's by-city page groups cities alphabetically with no province column;
# this maps every city in the current 72-city export to its province. Built
# from NRCan's known regional monitored-city sets (e.g. NB's 9 cities, NL's
# 5, Ontario's ~19) — see CITY_PROVINCE_NOTES for the one genuine ambiguity.
CITY_PROVINCE = {
    "Abbotsford": "BC", "Fort St. John": "BC", "Kamloops": "BC", "Kelowna": "BC",
    "Prince George": "BC", "Vancouver": "BC", "Victoria": "BC",
    "Calgary": "AB", "Edmonton": "AB", "Grande Prairie": "AB", "Lethbridge": "AB",
    "Lloydminster": "AB", "Red Deer": "AB",
    "Moose Jaw": "SK", "Prince Albert": "SK", "Regina": "SK", "Saskatoon": "SK",
    "Brandon": "MB", "Winnipeg": "MB",
    "Barrie": "ON", "Brantford": "ON", "Guelph": "ON", "Hamilton": "ON",
    "Kingston": "ON", "Kitchener": "ON", "London": "ON", "North Bay": "ON",
    "Oshawa": "ON", "Ottawa": "ON", "Peterborough": "ON", "Sarnia": "ON",
    "Sault Ste Marie": "ON", "St. Catharines": "ON", "Sudbury": "ON",
    "Thunder Bay": "ON", "Timmins": "ON", "Toronto": "ON", "Windsor": "ON",
    "Chicoutimi": "QC", "Drummondville": "QC", "Gaspé": "QC", "Gatineau": "QC",
    "Montreal": "QC", "Quebec": "QC", "Rimouski": "QC", "Sherbrooke": "QC",
    "Trois-Rivières": "QC", "Val d'Or": "QC",
    "Bathurst": "NB", "Campbellton": "NB", "Edmundston": "NB", "Fredericton": "NB",
    "Miramichi": "NB", "Moncton": "NB", "Saint John": "NB", "Sussex": "NB",
    "Woodstock": "NB",
    "Halifax": "NS", "Kentville": "NS", "New Glasgow": "NS", "Sydney": "NS",
    "Truro": "NS", "Yarmouth": "NS",
    "Charlottetown": "PE",
    "Corner Brook": "NL", "Gander": "NL", "Grand Falls": "NL",
    "Labrador City": "NL", "St. John's": "NL",
    "Whitehorse": "YT",
    "Yellowknife": "NT",
}
CITY_PROVINCE_NOTES = {
    "Lloydminster": "straddles the AB/SK border; assigned to AB here (unconfirmed against "
                    "NRCan's own convention) — treat this city's contribution as low-confidence.",
    "Grand Falls": "assumed to be Grand Falls-Windsor, NL (NL's standard 5-city monitored set), "
                   "not Grand Falls, NB.",
}


def latest_price_per_city(ws, header_row_idx, cols_per_city, first_price_col=1):
    """{city: (value_cents_per_l, period)} using the last non-blank 'Price'
    reading per city. header_row_idx/period rows are 0-based into
    ws.iter_rows(values_only=True))."""
    rows = list(ws.iter_rows(values_only=True))
    header = rows[header_row_idx]
    # city name repeats at the start of its column block; walk forward to
    # find each block's starting column.
    city_cols = []
    col = first_price_col
    while col < len(header):
        name = header[col]
        if name:
            city_cols.append((name, col))
        col += cols_per_city
    data_rows = [r for r in rows[header_row_idx + 2:] if isinstance(r[0], type(rows[header_row_idx + 2][0]))
                 and r[0] is not None]
    out = {}
    for city, col in city_cols:
        for r in reversed(data_rows):
            v = r[col]
            if isinstance(v, (int, float)):
                out[city] = (v, r[0].strftime("%Y-%m-%d"))
                break
    return out


def by_province(city_prices, unmapped):
    prov = {}
    for city, (cents, period) in city_prices.items():
        p = CITY_PROVINCE.get(city)
        if p is None:
            unmapped.add(city)
            continue
        prov.setdefault(p, []).append((city, cents, period))
    return prov


def build_fuel_entry(prov_cities, unit_label):
    cents_vals = [c for _, c, _ in prov_cities]
    dollars_per_l = round((sum(cents_vals) / len(cents_vals)) / 100.0, 4)
    return {
        "cad_per_litre": dollars_per_l,
        "n_cities": len(prov_cities),
        "sources": [
            {"city": city, "cents_per_litre": cents, "period": period}
            for city, cents, period in sorted(prov_cities)
        ],
    }


def main():
    if len(sys.argv) != 3:
        print("usage: python add_oil_propane_rates.py <furnace_oil.xlsx> <auto_propane.xlsx>",
              file=sys.stderr)
        sys.exit(1)
    oil_path, propane_path = sys.argv[1], sys.argv[2]

    if not OUTPUT_JSON.exists():
        raise RuntimeError(f"{OUTPUT_JSON} not found — run utility_rates_reference.py first")
    doc = json.loads(OUTPUT_JSON.read_text(encoding="utf-8"))

    unmapped = set()

    wb = openpyxl.load_workbook(oil_path, data_only=True)
    oil_prices = latest_price_per_city(wb["Sheet1"], header_row_idx=7, cols_per_city=4)
    oil_by_prov = by_province(oil_prices, unmapped)

    wb = openpyxl.load_workbook(propane_path, data_only=True)
    propane_prices = latest_price_per_city(wb["Sheet1"], header_row_idx=24, cols_per_city=2)
    propane_by_prov = by_province(propane_prices, unmapped)

    if unmapped:
        raise RuntimeError(f"unmapped cities (add to CITY_PROVINCE): {sorted(unmapped)}")

    for p, entry in doc["provinces"].items():
        if p in oil_by_prov:
            entry["heating_oil"] = build_fuel_entry(oil_by_prov[p], "cad_per_litre")
        if p in propane_by_prov:
            entry["propane"] = build_fuel_entry(propane_by_prov[p], "cad_per_litre")

    if "url" in doc.get("source", {}):  # first run after this script: flatten -> {tariffs: {...}}
        doc["source"] = {"tariffs": doc["source"]}
    doc["source"]["heating_oil_propane"] = {
        "name": "NRCan Prices by City (Furnace Oil / Auto Propane)",
        "url": "https://www2.nrcan.gc.ca/eneene/sources/pripri/prices_bycity_e.cfm",
        "cadence": "manual re-download (no stable API); furnace oil monthly, propane weekly",
        "method": "simple mean across NRCan-surveyed cities per province, latest available "
                  "reading per city (coverage varies by city)",
        "city_province_caveats": CITY_PROVINCE_NOTES,
    }
    doc["units"]["heating_oil"] = "cad_per_litre"
    doc["units"]["propane"] = "cad_per_litre"

    OUTPUT_JSON.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"wrote {OUTPUT_JSON}")

    provinces = sorted(doc["provinces"])
    csv_lines = ["province,elec_cents_per_kwh,elec_fixed_monthly_cad,elec_n_utilities,elec_confidence,"
                 "gas_dollars_per_m3,gas_fixed_monthly_cad,gas_n_utilities,gas_confidence,"
                 "heating_oil_cad_per_litre,heating_oil_n_cities,"
                 "propane_cad_per_litre,propane_n_cities"]
    for p in provinces:
        entry = doc["provinces"][p]
        e, g = entry.get("electricity"), entry.get("natural_gas")
        o, pr = entry.get("heating_oil"), entry.get("propane")
        csv_lines.append(",".join([
            p,
            f"{e['cents_per_kwh']:.3f}" if e else "",
            f"{e['fixed_monthly_cad']:.2f}" if e else "",
            str(e["n_utilities"]) if e else "",
            e["confidence"] if e else "",
            f"{g['dollars_per_m3']:.4f}" if g else "",
            f"{g['fixed_monthly_cad']:.2f}" if g else "",
            str(g["n_utilities"]) if g else "",
            g["confidence"] if g else "",
            f"{o['cad_per_litre']:.4f}" if o else "",
            str(o["n_cities"]) if o else "",
            f"{pr['cad_per_litre']:.4f}" if pr else "",
            str(pr["n_cities"]) if pr else "",
        ]))
    OUTPUT_CSV.write_text("\n".join(csv_lines) + "\n", encoding="utf-8")
    print(f"wrote {OUTPUT_CSV}")

    print("\nheating oil / propane by province ($/L):")
    for p in provinces:
        entry = doc["provinces"][p]
        o, pr = entry.get("heating_oil"), entry.get("propane")
        if o or pr:
            print(f"  {p}  oil={o['cad_per_litre'] if o else '—'}  "
                  f"propane={pr['cad_per_litre'] if pr else '—'}")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\nERROR: {e}", file=sys.stderr)
        sys.exit(1)
