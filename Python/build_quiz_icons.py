#!/usr/bin/env python3
"""build_quiz_icons.py - item icons (fuels, end uses, sectors, building types, modes...)
for the Energy Quiz.

INPUTS
  assets/vendor/lucide/*.svg   vendored Lucide icons (ISC; see LICENSE there;
                               fetched once by Python/fetch_lucide_icons.py)
  quiz_json/<topic>.json       the generated question banks (to report uncovered items)

OUTPUT
  quiz_json/icons.json  {"icons": {name: inner SVG markup}, "items": {display name: {"i": icon, "c": tint}}}

DESIGN
  * One icon per item name, chosen by hand in ICON_MAP below (a judgement call about
    what a lay reader recognises: flame = natural gas, zap = electricity, ...).
  * The tint is a CATEGORY colour (fuel type, end use, sector...), secondary to the label
    and value. Tints were picked to reach roughly 3:1 or better against white.
  * Province / region items are NOT here: they use outlines from build_quiz_shapes.py,
    which take priority on the page.
  * Only these SVG tags are kept, so the markup the page injects is plain geometry:
    path, circle, rect, line, polyline, polygon, ellipse.
  * Every name that appears in the bank but is neither mapped here nor a region outline is
    printed, so a silent gap is impossible.
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LUCIDE = ROOT / "assets" / "vendor" / "lucide"
OUT = ROOT / "quiz_json"

TINT = {
    "elec": "#1F6FB5", "gas": "#B8760F", "oil": "#6B4F3A", "wood": "#2E7D4F", "other": "#5C6E82",
    "heat": "#C0392B", "cool": "#3B82C4", "water": "#1A8A9E", "light": "#B8760F", "appl": "#5C6E82",
    "home": "#0B2545", "bldg": "#533AB7", "ind": "#5C6E82", "move": "#0E7490", "agri": "#2E7D4F",
}

# display name (exactly as it appears in the question bank) -> (lucide icon, tint category)
ICON_MAP = {
    # fuels / energy sources
    "Electricity": ("zap", "elec"), "Natural Gas": ("flame", "gas"), "Heating Oil": ("droplet", "oil"),
    "Wood": ("tree-pine", "wood"), "Other": ("ellipsis", "other"),
    "Motor Gasoline": ("fuel", "oil"), "Diesel Fuel Oil": ("barrel", "oil"),
    "Heavy Fuel Oil": ("container", "oil"), "Jet fuel (aviation turbo)": ("plane", "oil"),
    # residential end uses
    "Space Heating": ("heater", "heat"), "Space Cooling": ("snowflake", "cool"),
    "Water Heating": ("shower-head", "water"), "Appliances": ("refrigerator", "appl"),
    "Lighting": ("lightbulb", "light"),
    # home types (CEUD) and housing-start types (CMHC)
    "Apartments": ("building-2", "home"), "Mobile Homes": ("caravan", "home"),
    "Single Attached": ("houses", "home"), "Single Detached": ("house", "home"),
    "Apartment": ("building-2", "home"), "Single-detached": ("house", "home"),
    "Semi-detached": ("houses", "home"), "Row / townhouse": ("rows-3", "home"),
    # sectors
    "Homes": ("house", "home"), "Commercial and institutional": ("building-2", "bldg"),
    "Industry": ("factory", "ind"), "Transportation": ("bus", "move"), "Agriculture": ("wheat", "agri"),
    # commercial subsectors
    "Accommodation and Food Services": ("utensils", "bldg"), "Arts Entertainment and Recreation": ("drama", "bldg"),
    "Educational Services": ("graduation-cap", "bldg"), "Health Care and Social Assistance": ("stethoscope", "bldg"),
    "Information and Cultural Industries": ("newspaper", "bldg"), "Offices": ("briefcase", "bldg"),
    "Other Services": ("wrench", "bldg"), "Retail Trade": ("store", "bldg"),
    "Transportation and Warehousing": ("warehouse", "bldg"), "Wholesale Trade": ("boxes", "bldg"),
    # industry
    "Cement": ("brick-wall", "ind"), "Chemicals": ("flask-conical", "ind"), "Construction": ("hard-hat", "ind"),
    "Forestry": ("trees", "wood"), "Iron and Steel": ("anvil", "ind"),
    "Mining, quarrying, oil & gas": ("pickaxe", "ind"), "Other Manufacturing": ("factory", "ind"),
    "Petroleum Refining": ("cylinder", "ind"), "Pulp and Paper": ("scroll-text", "ind"),
    "Smelting and Refining": ("flame-kindling", "ind"),
    # transport modes
    "Cars": ("car", "move"), "Passenger Light Trucks": ("car-front", "move"), "Freight Light Trucks": ("van", "move"),
    "Medium Trucks": ("truck", "move"), "Heavy Trucks": ("container", "move"), "Freight Rail": ("train-front", "move"),
    "Marine": ("ship", "move"), "Off Road": ("tractor", "move"), "Passenger Air": ("plane", "move"),
    "Urban Transit": ("bus", "move"),
}

KEEP = {"path", "circle", "rect", "line", "polyline", "polygon", "ellipse"}


def inner_markup(svg_text, name):
    body = re.sub(r"<!--.*?-->", "", svg_text, flags=re.S)
    m = re.search(r"<svg\b[^>]*>(.*)</svg>", body, flags=re.S)
    if not m:
        raise ValueError(f"{name}: no <svg> element")
    inner = re.sub(r"\s+", " ", m.group(1)).strip()
    tags = set(re.findall(r"<\s*([a-zA-Z][\w-]*)", inner))
    bad = tags - KEEP
    if bad:
        raise ValueError(f"{name}: unexpected SVG tags {sorted(bad)}")
    if re.search(r"\son\w+\s*=|javascript:|<script", inner, flags=re.I):
        raise ValueError(f"{name}: unsafe attribute")
    return inner


def build():
    icons, items, missing_files = {}, {}, []
    for disp, (icon, cat) in ICON_MAP.items():
        f = LUCIDE / f"{icon}.svg"
        if not f.exists():
            missing_files.append(icon)
            continue
        if icon not in icons:
            icons[icon] = inner_markup(f.read_text(encoding="utf-8"), icon)
        items[disp] = {"i": icon, "c": TINT[cat]}
    if missing_files:
        print("ERROR: icons not vendored (add to fetch_lucide_icons.py):", sorted(set(missing_files)))
        sys.exit(1)
    OUT.mkdir(exist_ok=True)
    (OUT / "icons.json").write_text(json.dumps({"icons": icons, "items": items, "version": (LUCIDE / "VERSION").read_text().strip(),
                                                "licence": "Lucide, ISC licence (assets/vendor/lucide/LICENSE)"},
                                               ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    kb = (OUT / "icons.json").stat().st_size / 1024
    print(f"icons: {len(icons)} icons for {len(items)} item names, {kb:.0f} KB")

    # coverage report: every item name in the bank should have a region outline or an icon
    have = set(items)
    sp = OUT / "shapes.json"
    if sp.exists():
        have |= set(json.load(open(sp, encoding="utf-8"))["names"])
    unc = {}
    for f in OUT.glob("*.json"):
        if f.stem in ("meta", "icons", "shapes"):
            continue
        for q in json.load(open(f, encoding="utf-8"))["questions"]:
            for r in q["it"] + ([q["tg"]] if "tg" in q else []):
                if r[0] not in have:
                    unc.setdefault(q["m"], set()).add(r[0])
    if unc:
        print("  items with neither icon nor outline:", {k: sorted(v) for k, v in unc.items()})
    else:
        print("  coverage: every item in the bank has an outline or an icon")
    return items


if __name__ == "__main__":
    build()
