"""
bioheat_etl.py

Parses the NRCan Commercial and Institutional Bioheat Database 2023 (public
version) into grid_json/bioheat.json for the Grid page's biomass-heat section.

INPUT
    Bioheat_Database_2023_Public-1.pdf -- an Excel sheet printed to PDF
    (18 pages, 643 numbered rows). Download from
    https://torchlightbioresources.com/canadian-bioheat-database ("Data"),
    which the NRCan page
    https://natural-resources.canada.ca/energy-sources/renewable-energy/bioenergy-systems
    links to. Created in 2014 under CanmetENERGY's biomass standards project.
    Usage:  python Python/bioheat_etl.py [path/to/Bioheat_Database_2023_Public-1.pdf]

OUTPUT
    grid_json/bioheat.json -- facility rows + summaries + parse report.

WHAT THIS DATA IS (and is not)
    Installed thermal capacity (kWth) of commercial / institutional / light
    industrial / agricultural biomass heat and CHP systems. It is a facility
    list: NO fuel volumes, NO production, NO imports/exports, and NO
    residential wood heat. Capacity is as-reported/surveyed, not measured
    output.

LICENCE
    No licence text on the Torchlight page or in the PDF. Treated as public
    NRCan data on the project owner's decision (2026-11-26), because NRCan
    links to it. Cite NRCan / CanmetENERGY.

PARSING (honesty rails)
    Each row: "<n> <PROV> <city...> <sector> <fuel type> [<source>] <year>
    <Heat Only|CHP> <kWth> <Yes|No>". City, fuel type and source are free text
    with spaces, so the sector is found from a closed vocabulary and the
    fuel type / source are matched against closed vocabularies. Anything that
    does not fit is KEPT (never dropped) and listed under parse_report.
    Row numbers 1..N must be contiguous; a gap fails the run.
    Blank fuel source is kept as null (the source file leaves it blank).
    Fixes to source typos: 'Herbaceaous' -> 'Herbaceous'; 'Hogfuel sawmill'
    (one row where the source was typed into the fuel-type cell) -> fuel
    'Hogfuel', source 'Sawmill'; Yes/No/no case-normalised.
"""

import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

import pypdf

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PDF = Path.home() / "Downloads" / "Bioheat_Database_2023_Public-1.pdf"
OUT = ROOT / "grid_json" / "bioheat.json"

SECTORS = ["Multi Unit Residential", "Light Industrial", "Institutional",
           "Commercial", "Agricultural"]
# longest first so "Wood Pellets" is tried before shorter overlaps
FUELS = {"wood chips": "Wood Chips", "wood pellets": "Wood Pellets",
         "hogfuel": "Hogfuel", "briquettes": "Briquettes",
         "firewood": "Firewood", "herbaceaous": "Herbaceous",
         "herbaceous": "Herbaceous"}
SOURCES = {"management or silviculture": "Management or silviculture",
           "secondary manufacturer": "Secondary manufacturer",
           "urban wood waste": "Urban wood waste",
           "pellet producer": "Pellet producer",
           "energy crop": "Energy crop",
           "crop residue": "Crop residue",
           "sawmill": "Sawmill",
           "other": "Other",
           "farm - manure": "Farm - manure",
           "food processing residue": "Food processing residue",
           # source cell holds a fuel descriptor on this row; kept as stated
           "torrefied wood pellets": "Torrefied wood pellets"}
PROVINCES = {"AB", "BC", "MB", "NB", "NL", "NS", "NT", "NU", "ON", "PE", "QC",
             "SK", "YT"}

TAIL = re.compile(r"^(?P<mid>.*?)\s+(?P<year>\d{4})\s+(?P<type>Heat Only|CHP)"
                  r"\s+(?P<kw>[\d,]+)\s+(?P<multi>Yes|No)\s*$", re.I)
HEAD = re.compile(r"^(?P<n>\d+)\s+(?P<prov>[A-Z]{2})\s+(?P<rest>.*)$")


def read_lines(pdf):
    reader = pypdf.PdfReader(str(pdf))
    lines = []
    for p in reader.pages:
        lines += (p.extract_text() or "").splitlines()
    return len(reader.pages), lines


def parse_mid(rest):
    """rest = '<city> <sector> <fuel> [<source>]' -> dict or None."""
    for sec in SECTORS:
        m = re.search(r"(?:^|\s)" + re.escape(sec) + r"\s+", rest + " ")
        if not m:
            continue
        city = rest[:m.start()].strip()
        after = rest[m.end():].strip()
        low = after.lower()
        for key in sorted(FUELS, key=len, reverse=True):
            if low.startswith(key):
                fuel = FUELS[key]
                src_txt = after[len(key):].strip()
                src = None
                if src_txt:
                    src = SOURCES.get(src_txt.lower())
                    if src is None:
                        return {"city": city, "sector": sec, "fuel": fuel,
                                "source": None, "unparsed": src_txt}
                return {"city": city, "sector": sec, "fuel": fuel,
                        "source": src}
        return {"city": city, "sector": sec, "fuel": None,
                "source": None, "unparsed": after}
    return None


def main():
    pdf = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_PDF
    n_pages, lines = read_lines(pdf)

    rows, problems = [], []
    for line in lines:
        h = HEAD.match(line)
        if not h or h["prov"] not in PROVINCES:
            continue  # header / page-break lines
        n = int(h["n"])
        t = TAIL.match(h["rest"])
        if not t:
            problems.append({"n": n, "raw": line, "why": "tail not matched"})
            continue
        mid = parse_mid(t["mid"])
        if mid is None:
            problems.append({"n": n, "raw": line, "why": "sector not found"})
            continue
        row = {"n": n, "prov": h["prov"], "city": mid["city"],
               "sector": mid["sector"], "fuel": mid["fuel"],
               "source": mid["source"], "year": int(t["year"]),
               "type": "CHP" if t["type"].upper() == "CHP" else "Heat Only",
               "kwth": int(t["kw"].replace(",", "")),
               "multi": t["multi"].lower() == "yes"}
        if mid.get("unparsed"):
            problems.append({"n": n, "raw": line,
                             "why": "unrecognised: " + mid["unparsed"]})
        rows.append(row)

    nums = sorted(r["n"] for r in rows if r["n"] not in
                  {p["n"] for p in problems if p["why"] == "tail not matched"
                   or p["why"] == "sector not found"})         + [p["n"] for p in problems
           if p["why"] in ("tail not matched", "sector not found")]
    expected = list(range(1, max(nums) + 1))
    missing = sorted(set(expected) - set(nums))
    dupes = [k for k, v in Counter(nums).items() if v > 1]

    # one source row typed "Hogfuel sawmill" in the fuel cell was handled by
    # the vocabulary (fuel=Hogfuel, source=Sawmill) -- count it for the report
    kept = {r["n"] for r in rows}
    summary = {
        "rows_in_source": max(nums),
        "rows_parsed": len(rows),
        "rows_with_problems": len(problems),
        "rows_missing_numbers": missing,
        "duplicate_numbers": dupes,
        "rows_blank_fuel_source": sum(1 for r in rows if r["source"] is None),
        "unparsed_rows_kept_out_of_summaries": [p["n"] for p in problems
                                                if p["n"] not in kept],
    }

    def agg(keyfn):
        d = defaultdict(lambda: {"systems": 0, "kwth": 0})
        for r in rows:
            k = keyfn(r)
            d[k]["systems"] += 1
            d[k]["kwth"] += r["kwth"]
        return {str(k): v for k, v in sorted(d.items(), key=lambda x: str(x[0]))}

    out = {
        "source": {
            "title": "Commercial and Institutional Bioheat Database 2023, "
                     "Public Version",
            "publisher": "Natural Resources Canada / CanmetENERGY",
            "hosted_at": "https://torchlightbioresources.com/"
                         "canadian-bioheat-database",
            "nrcan_page": "https://natural-resources.canada.ca/"
                          "energy-sources/renewable-energy/bioenergy-systems",
            "vintage": 2023,
            "kind": "installed thermal capacity (kWth), facility list",
            "not_included": ["fuel volumes", "production", "imports/exports",
                             "residential wood heat"],
            "licence_note": "No licence text on source; treated as public "
                            "NRCan data (owner decision 2026-11-26).",
        },
        "parse_report": {**summary, "problems": problems},
        "totals": {"systems": len(rows),
                   "kwth": sum(r["kwth"] for r in rows)},
        "by_province": agg(lambda r: r["prov"]),
        "by_fuel": agg(lambda r: r["fuel"]),
        "by_source": agg(lambda r: r["source"] or "Not stated"),
        "by_sector": agg(lambda r: r["sector"]),
        "by_type": agg(lambda r: r["type"]),
        "by_install_year": agg(lambda r: r["year"]),
        "rows": rows,
    }
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")),
                   encoding="utf-8")

    print(f"{pdf.name}: {n_pages} pages")
    print(json.dumps(summary, indent=1))
    for p in problems:
        print("PROBLEM", p)
    print("total", out["totals"])
    print("wrote", OUT, f"({OUT.stat().st_size // 1024} KB)")
    if missing or dupes or problems:
        sys.exit(1)


if __name__ == "__main__":
    main()
