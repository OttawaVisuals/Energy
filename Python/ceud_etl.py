"""
ceud_etl.py

Downloads and parses NRCan's Comprehensive Energy Use Database (CEUD),
residential sector, for all 11 provinces/territories + Canada, into tidy
long-format JSON for the CEUD Explorer web page.

See C:\\Energy\\docs\\archive\\CEUD_PLAN.md (plan) and C:\\Energy\\Python\\ceud_source_notes.md
(Phase 0 findings) for full background — source URLs, table layout, the
excluding-electricity GHG convention, and why table numbers aren't aligned
between Canada and the provinces.

USAGE (rerun any time; already-downloaded .xls files are cached and skipped):
    pip install requests pandas xlrd
    python ceud_etl.py

    Add --refresh to force re-download of everything (ignore the cache):
    python ceud_etl.py --refresh

OUTPUT:
    C:\\Energy\\ceud_json\\res_<region>.json   one per region (12 files)
    C:\\Energy\\ceud_json\\meta.json           shared metadata

To pick up a new NRCan release (new latest year), bump RELEASE_YEAR below —
the site keeps prior-year folders live, so this is safe to change without
breaking anything; rerun with --refresh to force re-download under the new
folder.
"""

import os
import re
import sys
import json
import html
import argparse
from pathlib import Path
from math import log10, floor

import requests
import pandas as pd

# =============================================================================
# CONFIG
# =============================================================================

BASE = "https://oee.nrcan.gc.ca/corporate/statistics/neud/dpa"
SECTOR = "res"
RELEASE_YEAR = "2023"  # NRCan's Excel download folder; bump when a new release ships

CACHE_DIR = Path(r"C:\Energy\Python\ceud_cache")
OUTPUT_DIR = Path(r"C:\Energy\ceud_json")

# region_code -> (display name, index-page slug). The slug differs from the
# jurisdiction code used in downstream URLs for two regions (nl -> "nf" page,
# pe -> "pei" page) — see ceud_source_notes.md "Gotcha" — don't unify these.
REGIONS = {
    "ca": ("Canada", "ca"),
    "nl": ("Newfoundland and Labrador", "nf"),
    "pe": ("Prince Edward Island", "pei"),
    "ns": ("Nova Scotia", "ns"),
    "nb": ("New Brunswick", "nb"),
    "qc": ("Quebec", "qc"),
    "on": ("Ontario", "on"),
    "mb": ("Manitoba", "mb"),
    "sk": ("Saskatchewan", "sk"),
    "ab": ("Alberta", "ab"),
    "bc": ("British Columbia", "bc"),
    "tr": ("Territories", "tr"),
}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
}

BUILDING_TYPES = ["Single Detached", "Single Attached", "Apartments", "Mobile Homes"]

# Table-title -> role patterns. Matched against the index page's plain-text
# table titles (HTML-unescaped, tags stripped). One role can match multiple
# tables per region (the 4 building-type variants of the two energy tables).
ROLE_PATTERNS = [
    (re.compile(r"^Secondary Energy Use and GHG Emissions by Energy Source$"),
     "energy_by_source", None),
    (re.compile(r"^Secondary Energy Use and GHG Emissions by End-Use$"),
     "energy_by_end_use", None),
    (re.compile(r"^(Single Detached|Single Attached|Apartments|Mobile Homes) "
                r"Secondary Energy Use and GHG Emissions by Energy Source$"),
     "energy_by_source", "bt"),
    (re.compile(r"^(Single Detached|Single Attached|Apartments|Mobile Homes) "
                r"Secondary Energy Use and GHG Emissions by End-Use$"),
     "energy_by_end_use", "bt"),
    (re.compile(r"^Total Households by Building Type and "
                r"(Principal Heating Energy Source|Energy Source)$"),
     "households", None),
    (re.compile(r"^Heating System Stock by Building Type and Heating System Type$"),
     "heating_system_stock", None),
    (re.compile(r"^Appliance Stock by Appliance Type and Energy Source$"),
     "appliance_stock", None),
]

ENERGY_SOURCE_MAP = {
    "electricity": "electricity",
    "natural gas": "natural_gas",
    "heating oil": "heating_oil",
    "other": "other",   # footnote digits ("Other1"/"Other2") stripped before lookup
    "wood": "wood",
}

END_USE_MAP = {
    "space heating": "space_heating",
    "water heating": "water_heating",
    "appliances": "appliances",
    "lighting": "lighting",
    "space cooling": "space_cooling",
}

BUILDING_TYPE_MAP = {
    "single detached": "single_detached",
    "single attached": "single_attached",
    "apartments": "apartments",
    "mobile homes": "mobile_homes",
}

# Section headers that are sub-headings *within* a table's current top-level
# section (not new sections themselves) — encountering one must NOT reset
# "current section", or subsequent rows (e.g. "Wood/Electric" under "Dual
# Systems") would lose the section context that names their variable.
SUBSECTION_HEADERS = {"dual systems"}

YEAR_MIN, YEAR_MAX = 1990, 2035


# =============================================================================
# HTTP + caching
# =============================================================================

def cached_get(url, cache_path, refresh=False, binary=True):
    """GET url, caching the raw bytes/text at cache_path. Skips the request
    entirely on a rerun unless refresh=True or the cache file is empty."""
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    if not refresh and cache_path.exists() and cache_path.stat().st_size > 0:
        return cache_path.read_bytes() if binary else cache_path.read_text(encoding="utf-8")
    resp = requests.get(url, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    content = resp.content if binary else resp.text
    if binary:
        cache_path.write_bytes(content)
    else:
        cache_path.write_text(content, encoding="utf-8")
    return content


# =============================================================================
# Table discovery (index page -> table number/title/role per region)
# =============================================================================

TITLE_ROW_RE = re.compile(
    r'title="Table \d+" href="[^"]*[?&]rn=(\d+)[^"]*"[^>]*>Table \d+:</a></div>\s*'
    r'<div[^>]*>(.*?)</div>',
    re.DOTALL,
)


def clean_title(raw_html_fragment):
    text = re.sub(r"<[^>]*>", "", raw_html_fragment)
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    # normalize the two dash variants NRCan uses inconsistently ("&ndash;" / "-")
    text = text.replace("–", "-")
    return text


def discover_tables(region, slug, refresh=False, sector=None):
    """Returns list of (table_number:int, title:str) for a region's index page.

    table_number is parsed from the download link's rn= query param, NOT the
    cosmetic "Table N" label shown on the page — those two can diverge (seen
    for agriculture provinces, e.g. Ontario agriculture displays "Table 7" but
    the actual download/rn number is 1). Verified zero divergence for every
    residential region, so this is a strict fix with no behavior change there.
    """
    sec = sector or SECTOR
    url = f"{BASE}/menus/trends/comprehensive/trends_{sec}_{slug}.cfm"
    cache_path = CACHE_DIR / "index_pages" / f"{sec}_{region}.html"
    text = cached_get(url, cache_path, refresh=refresh, binary=False)
    out = []
    for m in TITLE_ROW_RE.finditer(text):
        num = int(m.group(1))
        title = clean_title(m.group(2))
        out.append((num, title))
    out.sort(key=lambda t: t[0])
    return out


def match_role(title):
    """Returns (role, building_type_or_None) if title matches a known role, else None."""
    for pattern, role, kind in ROLE_PATTERNS:
        m = pattern.match(title)
        if not m:
            continue
        if kind == "bt":
            return role, m.group(1)  # building type name as scraped, e.g. "Single Detached"
        return role, None
    return None


def build_table_plan(region, slug, refresh=False):
    """
    Returns dict: role_key -> table_number
      role_key is 'energy_by_source' / 'energy_by_end_use' for the region-wide
      tables, or 'energy_by_source:<building_type>' / 'energy_by_end_use:<building_type>'
      for the per-building-type variants, or the bare role name for the three
      explanatory tables (households, heating_system_stock, appliance_stock).
    """
    tables = discover_tables(region, slug, refresh=refresh)
    plan = {}
    for num, title in tables:
        matched = match_role(title)
        if not matched:
            continue
        role, bt = matched
        key = f"{role}:{BUILDING_TYPE_MAP[bt.lower()]}" if bt else role
        plan[key] = num
    return plan


# =============================================================================
# .xls download + generic row parsing
# =============================================================================

def download_table_xls(region, table_num, refresh=False, sector=None):
    sec = sector or SECTOR
    url = f"{BASE}/data_e/downloads/comprehensive/Excel/{RELEASE_YEAR}/{sec}_{region}_e_{table_num}.xls"
    cache_path = CACHE_DIR / "xls" / RELEASE_YEAR / f"{sec}_{region}_e_{table_num}.xls"
    cached_get(url, cache_path, refresh=refresh, binary=True)
    return cache_path


def find_year_header(df):
    """Locate the row holding year column headers (a float in [1990,2035] at column 2)."""
    for r in range(min(20, df.shape[0])):
        if df.shape[1] <= 2:
            continue
        v = df.iat[r, 2]
        if isinstance(v, (int, float)) and not pd.isna(v) and YEAR_MIN <= float(v) <= YEAR_MAX:
            years = {}
            for c in range(2, df.shape[1]):
                yv = df.iat[r, c]
                if pd.notna(yv):
                    years[c] = int(yv)
            return r, years
    raise ValueError("year header row not found")


def parse_table_rows(xls_path):
    """
    Generic section-aware row extraction, shared by every table role.
    Returns list of {'section': str|None, 'label': str, 'values': {year:int -> raw cell}}.
    A row with all-NaN data cells is a section header (updates 'section',
    never yielded); a row with any non-NaN data cell is a data row (yielded,
    tagged with whichever section currently applies). Rows inside a "Shares
    (%)" section are dropped entirely — percentages aren't part of the schema.
    """
    df = pd.read_excel(xls_path, sheet_name=0, header=None)
    year_row, year_cols = find_year_header(df)

    rows = []
    section = None
    in_shares = False
    for r in range(year_row + 2, df.shape[0]):
        label = df.iat[r, 1] if df.shape[1] > 1 else None
        if not isinstance(label, str) or not label.strip():
            # Blank separator row. Always ends a "Shares (%)" block — those
            # spans run straight from the header to the next blank line with
            # no closing header of their own, so in_shares must reset here,
            # not just on the next header (a data row like "Total GHG
            # Emissions Excluding Electricity" can follow immediately after
            # a blank with no intervening header, and must not be dropped).
            in_shares = False
            continue  # blank separator row, or a footnote line (text sits in column 0)
        label = label.strip()

        values = {}
        any_data = False
        for c, yr in year_cols.items():
            v = df.iat[r, c]
            if pd.isna(v):
                continue
            any_data = True
            values[yr] = v

        if not any_data:
            # header row
            if label.lower() not in SUBSECTION_HEADERS:
                section = label
                in_shares = bool(re.match(r"^shares\b", label, re.I))
            continue

        if in_shares:
            continue

        rows.append({"section": section, "label": label, "values": values})
    return rows


def clean_cell(v):
    """Numeric cell -> float. Non-numeric placeholder cells (en-dash 'not
    applicable' markers, or any other stray string) -> None, never 0."""
    if isinstance(v, str):
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f


def normalize_label(label):
    """'Heating Oil - Normal Efficiency' -> 'heating_oil_normal_efficiency'."""
    s = label.strip()
    s = re.sub(r"\d+$", "", s)  # strip trailing footnote digit, e.g. "Other1" -> "Other"
    s = s.replace("–", "-").replace("—", "-")
    s = re.sub(r"[^A-Za-z0-9]+", "_", s).strip("_").lower()
    return s


def round_sig(x, sig=3):
    if x is None:
        return None
    if x == 0:
        return 0.0
    d = sig - int(floor(log10(abs(x)))) - 1
    return round(x, d)


# =============================================================================
# Role-specific extractors
# =============================================================================

def extract_energy_table(rows, dim_kind, building_type):
    """
    dim_kind: 'energy_source' or 'end_use' — which dimension this table
    breaks totals down by. building_type: canonical building-type string,
    or 'all' for the region-wide (not building-type-specific) table.

    Only the excluding-electricity GHG convention is kept (see
    ceud_source_notes.md): it's the one both Canada and every province
    report, so it's the only one that supports cross-region comparison.
    """
    dim_map = ENERGY_SOURCE_MAP if dim_kind == "energy_source" else END_USE_MAP

    total_energy = {}
    total_ghg_excl = {}
    breakdown_energy = {}   # segment label -> {year: value}
    breakdown_ghg_excl = {}

    ghg_state = None  # None | 'incl' | 'excl' — which GHG total block we're currently inside

    for row in rows:
        section, label, values = row["section"], row["label"], row["values"]

        # These "Total ..." lines are standalone data rows with no header of
        # their own — they sit right after a *different* preceding section
        # (Activity, or nothing at all for the very first row), so they must
        # be recognized by label text, not by section context.
        if re.match(r"^Total .*Energy Use \(PJ\)$", label):
            total_energy = values
            continue
        if re.search(r"GHG Emissions Including Electricity", label):
            ghg_state = "incl"
            continue
        if re.search(r"GHG Emissions Excluding Electricity", label):
            total_ghg_excl = values
            ghg_state = "excl"
            continue

        if section is None:
            continue

        if re.match(r"^Energy Use by (Energy Source|End-Use)", section, re.I):
            breakdown_energy.setdefault(label, {}).update(values)
        elif re.match(r"^GHG Emissions by (Energy Source|End-Use)", section, re.I):
            if ghg_state == "excl":
                breakdown_ghg_excl.setdefault(label, {}).update(values)
            # 'incl' breakdown intentionally discarded — see docstring
        # Activity / Energy Intensity / GHG Intensity / degree-day sections
        # handled by extract_explanatory_from_energy_table(), not here.

    segments = set(breakdown_energy) | set(breakdown_ghg_excl)
    records = []

    all_years = set(total_energy) | set(total_ghg_excl)
    for yr in all_years:
        e = clean_cell(total_energy.get(yr))
        g = clean_cell(total_ghg_excl.get(yr))
        if e is None and g is None:
            continue
        rec = {"year": yr, "energy_source": "all", "end_use": "all",
               "building_type": building_type, "energy_PJ": round_sig(e), "ghg_Mt": round_sig(g)}
        rec[dim_kind] = "all"  # no-op for clarity; both dims already 'all' above
        records.append(rec)

    for seg_label in segments:
        canon = dim_map.get(normalize_label(seg_label).replace("_", " "))
        if canon is None:
            continue  # unmapped label (shouldn't happen given the 5-source/5-end-use vocabulary)
        e_vals = breakdown_energy.get(seg_label, {})
        g_vals = breakdown_ghg_excl.get(seg_label, {})
        for yr in set(e_vals) | set(g_vals):
            e = clean_cell(e_vals.get(yr))
            g = clean_cell(g_vals.get(yr))
            if e is None and g is None:
                continue
            rec = {"year": yr, "energy_source": "all", "end_use": "all",
                   "building_type": building_type, "energy_PJ": round_sig(e), "ghg_Mt": round_sig(g)}
            rec[dim_kind] = canon
            records.append(rec)

    return records


def extract_explanatory_from_energy_table(rows, building_type):
    """Activity (floor space, households) + degree-day indices — present in
    every energy table, scoped to that table's building_type ('all' for the
    region-wide table). Deduped later across tables by (year,variable,segment)."""
    out = []
    for row in rows:
        section, label, values = row["section"], row["label"], row["values"]
        if section == "Activity" and label.startswith("Total Floor Space"):
            for yr, v in values.items():
                val = clean_cell(v)
                if val is not None:
                    out.append({"year": yr, "variable": "floor_space", "segment": building_type,
                                "value": round_sig(val), "unit": "million_m2"})
        elif section == "Activity" and label.startswith("Total Households"):
            for yr, v in values.items():
                val = clean_cell(v)
                if val is not None:
                    out.append({"year": yr, "variable": "households", "segment": building_type,
                                "value": round_sig(val), "unit": "thousands"})
        elif label == "Heating Degree-Day Index" and building_type == "all":
            for yr, v in values.items():
                val = clean_cell(v)
                if val is not None:
                    out.append({"year": yr, "variable": "heating_degree_day_index", "segment": "all",
                                "value": round_sig(val), "unit": "index"})
        elif label == "Cooling Degree-Day Index" and building_type == "all":
            for yr, v in values.items():
                val = clean_cell(v)
                if val is not None:
                    out.append({"year": yr, "variable": "cooling_degree_day_index", "segment": "all",
                                "value": round_sig(val), "unit": "index"})
    return out


def extract_households_table(rows):
    out = []
    for row in rows:
        section, label, values = row["section"], row["label"], row["values"]
        if section is None and label.startswith("Total Households"):
            variable, segment = "households", "all"
        elif section and re.match(r"^Households by Building Type", section, re.I):
            variable = "households_by_building_type"
            segment = BUILDING_TYPE_MAP.get(label.lower())
            if segment is None:
                continue
        elif section and re.search(r"Energy Source", section, re.I) and \
                re.match(r"^Households by", section, re.I):
            variable = "households_by_heating_fuel"
            segment = ENERGY_SOURCE_MAP.get(normalize_label(label).replace("_", " "))
            if segment is None:
                continue
        else:
            continue
        for yr, v in values.items():
            val = clean_cell(v)
            if val is not None:
                out.append({"year": yr, "variable": variable, "segment": segment,
                            "value": round_sig(val), "unit": "thousands"})
    return out


def extract_heating_system_stock_table(rows):
    out = []
    for row in rows:
        section, label, values = row["section"], row["label"], row["values"]
        if section is None and label.startswith("Total Heating System Stock"):
            variable, segment = "heating_system_stock", "all"
        elif section and re.match(r"^Heating System Stock by Building Type", section, re.I):
            variable = "heating_system_stock_by_building_type"
            segment = BUILDING_TYPE_MAP.get(label.lower())
            if segment is None:
                continue
        elif section and re.match(r"^Heating System Stock by Heating System Type", section, re.I):
            variable = "heating_system_stock_by_system_type"
            segment = normalize_label(label)
        else:
            continue
        for yr, v in values.items():
            val = clean_cell(v)
            if val is not None:
                out.append({"year": yr, "variable": variable, "segment": segment,
                            "value": round_sig(val), "unit": "thousands"})
    return out


def extract_appliance_stock_table(rows):
    out = []
    for row in rows:
        section, label, values = row["section"], row["label"], row["values"]
        if section and re.match(r"^Appliance Stock by Appliance Type", section, re.I):
            variable = "appliance_stock"
            segment = normalize_label(label)
        else:
            continue
        for yr, v in values.items():
            val = clean_cell(v)
            if val is not None:
                out.append({"year": yr, "variable": variable, "segment": segment,
                            "value": round_sig(val), "unit": "thousands"})
    return out


# =============================================================================
# Phase 4 — generic multi-sector pipeline (Commercial/Institutional,
# Transportation, Industrial, Agriculture)
#
# Unlike residential (hand-mapped table roles + closed vocabularies), these
# four sectors are handled by ONE sector-agnostic pipeline:
#   1. Discover every "role" table for a region — any top-level ('all'-scope)
#      breakdown table matching TABLE_ROLE_RE, e.g. "Secondary Energy Use and
#      GHG Emissions by Energy Source" or "GHG Emissions by Industry -
#      Excluding Electricity-Related Emissions". Per-activity/per-industry/
#      per-mode drill-down tables (title has a prefix like "Wholesale Trade
#      Secondary Energy Use...") are intentionally excluded by requiring the
#      title to START with the verb phrase — v1 scope is 'all'-level
#      breakdowns only (energy_source / end_use / segment2 each on their
#      own), not full cross-tabs between them.
#   2. Download + parse every matched table with the existing generic
#      parse_table_rows(), then concatenate all rows for the region.
#   3. For each of energy_source/end_use/segment2, scan the merged rows for
#      "Energy Use by X (PJ)" / "GHG Emissions by X (Mt of CO2e)" sections,
#      infer which of the three dims X is via SECTION_DIM_ALIASES, and pull
#      out only the sections matching the dim currently being extracted.
#      Segment labels are canonicalized via normalize_label() directly (open
#      vocabulary discovered from the data) rather than a hardcoded map,
#      since each sector's source/end-use/segment2 vocabulary differs.
#      Some sectors use only a subset of the three dims (e.g. industrial has
#      no end_use; agriculture has no segment2) — dims with no matching
#      sections anywhere simply produce zero records, which is correct.
# =============================================================================

# region_code -> display name, for the 8-region set NRCan uses for these four
# sectors (coarser than residential's 12 — confirmed by probing every region:
# NL/PE/NS/NB only publish an aggregate "Atlantic" table, and BC/Territories
# only publish an aggregate "BC & Territories" table, for commercial,
# industrial and agriculture; transportation happens to publish NL/PE/NS/NB
# individually too but BC/Territories still only as the aggregate — the 8-
# region set is used uniformly across all four new sectors for a consistent
# region selector rather than branching UI per sector).
REGIONS_8 = {
    "ca": "Canada",
    "atl": "Atlantic (NL, PE, NS, NB)",
    "qc": "Quebec",
    "on": "Ontario",
    "mb": "Manitoba",
    "sk": "Saskatchewan",
    "ab": "Alberta",
    "bct": "British Columbia & Territories",
}

# file_prefix -> (display label, NRCan url sector code). url sector code is
# what NRCan uses in its own URLs/filenames; file_prefix is what we use for
# our own output filenames (kept distinct only for "ind", which NRCan calls
# "agg" — short for "aggregated industries" — on their site).
NEW_SECTORS = {
    "com": ("Commercial/Institutional", "com"),
    "tran": ("Transportation", "tran"),
    "ind": ("Industrial", "agg"),
    "agr": ("Agriculture", "agr"),
}

TABLE_ROLE_RE = re.compile(
    r"^(?P<verb>Secondary Energy Use(?: and GHG Emissions)?|GHG Emissions) by "
    r"(?P<dim>[A-Za-z][A-Za-z \-]*?)\d*"
    r"(?:\s*-\s*(?P<conv>Including|Excluding) Electricity-Related Emissions)?$"
)

SECTION_DIM_RE = re.compile(r"^(Energy Use|GHG Emissions) by (.+?)\s*\((?:PJ|Mt of CO2e)\)$")
SECTION_DIM_ALIASES = {
    "energy source": "energy_source",
    "end-use": "end_use", "end use": "end_use",
    "activity type": "segment2",
    "transportation mode": "segment2",
    "industry": "segment2",
}

GHG_INCL_RE = re.compile(r"GHG Emissions.*Including Electricity")
GHG_EXCL_RE = re.compile(r"GHG Emissions.*Excluding Electricity")
GHG_PLAIN_RE = re.compile(r"^Total .*GHG Emissions.*\(Mt")
TOTAL_ENERGY_RE = re.compile(r"^Total .*Energy Use.*\(PJ\)$")

# Trailing standalone metric rows (GHG Intensity, Heating/Cooling Degree-Day
# Index) sometimes follow a breakdown section with no blank separator row
# between them, so parse_table_rows() tags them with the stale, still-open
# section from the preceding breakdown — e.g. "GHG Emissions by Energy
# Source" — rather than resetting to None. Residential's extractor never hit
# this because its segment lookup is a closed vocabulary (unknown labels are
# silently dropped); this extractor's open vocabulary has no such guard, so
# these labels must be excluded explicitly regardless of section.
NON_SEGMENT_LABEL_RE = re.compile(r"Intensity|Degree-Day", re.I)


def discover_role_tables(sector_prefix, url_sector, region, refresh=False):
    """Returns sorted list of table numbers whose title matches TABLE_ROLE_RE
    (an 'all'-scope breakdown table), excluding by-Region tables."""
    tables = discover_tables(region, region, refresh=refresh, sector=url_sector)
    nums = []
    for num, title in tables:
        m = TABLE_ROLE_RE.match(title)
        if not m:
            continue
        if re.search(r"\bregion\b", m.group("dim"), re.I):
            continue
        nums.append(num)
    return sorted(set(nums))


def infer_section_dim(section_title):
    """'Energy Use by Activity Type1 (PJ)' -> ('energy', 'segment2'). None if
    the section isn't a recognized X-breakdown section (e.g. 'Activity',
    'Shares (%)' — already dropped by parse_table_rows — or an unmapped X)."""
    if not section_title:
        return None
    m = SECTION_DIM_RE.match(section_title.strip())
    if not m:
        return None
    kind = "energy" if m.group(1) == "Energy Use" else "ghg"
    raw = re.sub(r"\d+$", "", m.group(2)).strip().lower()
    dim_kind = SECTION_DIM_ALIASES.get(raw)
    if dim_kind is None:
        return None
    return kind, dim_kind


def extract_generic_dim(rows, dim_kind):
    """Same shape as residential's extract_energy_table, generalized to an
    open segment vocabulary and a third possible dim ('segment2') alongside
    energy_source/end_use. Only the excl-electricity GHG convention is kept
    (or the sector's single convention, if it doesn't report incl/excl at
    all — e.g. transportation) — mirrors the residential rule."""
    total_energy = {}
    total_ghg = {}
    breakdown_energy = {}
    breakdown_ghg = {}
    ghg_state = None

    for row in rows:
        section, label, values = row["section"], row["label"], row["values"]

        if NON_SEGMENT_LABEL_RE.search(label):
            continue
        if TOTAL_ENERGY_RE.match(label):
            total_energy = values
            continue
        if label.startswith("Total") and GHG_INCL_RE.search(label):
            ghg_state = "incl"
            continue
        if label.startswith("Total") and GHG_EXCL_RE.search(label):
            total_ghg = values
            ghg_state = "excl"
            continue
        if GHG_PLAIN_RE.match(label) and "Including" not in label and "Excluding" not in label:
            total_ghg = values
            ghg_state = "plain"
            continue

        if section is None:
            continue
        inferred = infer_section_dim(section)
        if inferred is None:
            continue
        kind, inferred_dim = inferred
        if inferred_dim != dim_kind:
            continue
        if kind == "energy":
            breakdown_energy.setdefault(label, {}).update(values)
        elif kind == "ghg" and ghg_state in ("excl", "plain"):
            breakdown_ghg.setdefault(label, {}).update(values)

    def blank_dims():
        return {"energy_source": "all", "end_use": "all", "segment2": "all"}

    records = []
    all_years = set(total_energy) | set(total_ghg)
    for yr in all_years:
        e = clean_cell(total_energy.get(yr))
        g = clean_cell(total_ghg.get(yr))
        if e is None and g is None:
            continue
        rec = blank_dims()
        rec.update({"year": yr, "energy_PJ": round_sig(e), "ghg_Mt": round_sig(g)})
        records.append(rec)

    segments = set(breakdown_energy) | set(breakdown_ghg)
    for seg_label in segments:
        canon = normalize_label(seg_label)
        e_vals = breakdown_energy.get(seg_label, {})
        g_vals = breakdown_ghg.get(seg_label, {})
        for yr in set(e_vals) | set(g_vals):
            e = clean_cell(e_vals.get(yr))
            g = clean_cell(g_vals.get(yr))
            if e is None and g is None:
                continue
            rec = blank_dims()
            rec[dim_kind] = canon
            rec.update({"year": yr, "energy_PJ": round_sig(e), "ghg_Mt": round_sig(g)})
            records.append(rec)

    return records


ACTIVITY_UNIT_RE = re.compile(r"\(([^)]+)\)\s*$")


def extract_generic_activity(rows):
    """Whatever's in the 'Activity' section — floor space (commercial), GDP
    (industrial/agriculture), passenger-km/tonne-km (transportation) — kept
    generically rather than sector-specific, same normalize_label() approach
    as the segment vocabulary above."""
    out = []
    for row in rows:
        section, label, values = row["section"], row["label"], row["values"]
        if section != "Activity":
            continue
        # Same stale-section issue as extract_generic_dim: a trailing "Total
        # GHG Emissions..."/Intensity line sometimes follows Activity's real
        # rows (floor space, GDP, ...) with no blank separator to reset
        # section — exclude anything that isn't a genuine activity variable.
        if NON_SEGMENT_LABEL_RE.search(label) or TOTAL_ENERGY_RE.match(label) or \
                (label.startswith("Total") and "GHG Emissions" in label):
            continue
        m = ACTIVITY_UNIT_RE.search(label)
        unit = normalize_label(m.group(1)) if m else "unknown"
        varname = normalize_label(ACTIVITY_UNIT_RE.sub("", label))
        for yr, v in values.items():
            val = clean_cell(v)
            if val is not None:
                out.append({"year": yr, "variable": varname, "segment": "all",
                            "value": round_sig(val), "unit": unit})
    return out


def build_generic_region(sector_prefix, url_sector, region, refresh=False):
    print(f"\n--- {sector_prefix}/{region} ---")
    table_nums = discover_role_tables(sector_prefix, url_sector, region, refresh=refresh)
    if not table_nums:
        print(f"  !! no role tables found (sector/region combination may not be published)")
        return None

    all_rows = []
    for num in table_nums:
        xls_path = download_table_xls(region, num, refresh=refresh, sector=url_sector)
        all_rows.extend(parse_table_rows(xls_path))

    records = []
    for dim_kind in ("energy_source", "end_use", "segment2"):
        records.extend(extract_generic_dim(all_rows, dim_kind))
    explanatory = extract_generic_activity(all_rows)

    seen = set()
    dedup_records = []
    for r in records:
        key = (r["year"], r["energy_source"], r["end_use"], r["segment2"])
        if key in seen:
            continue
        seen.add(key)
        dedup_records.append(r)

    seen_exp = set()
    dedup_explanatory = []
    for e in explanatory:
        key = (e["year"], e["variable"], e["segment"])
        if key in seen_exp:
            continue
        seen_exp.add(key)
        dedup_explanatory.append(e)

    dedup_records.sort(key=lambda r: (r["year"], r["segment2"], r["energy_source"], r["end_use"]))
    dedup_explanatory.sort(key=lambda e: (e["variable"], e["segment"], e["year"]))

    print(f"  {len(table_nums)} role tables, {len(dedup_records)} records, "
          f"{len(dedup_explanatory)} explanatory rows")
    return {"region": region, "records": dedup_records, "explanatory": dedup_explanatory}


def compact_record_generic(r):
    out = {"year": r["year"]}
    for k in ("energy_source", "end_use", "segment2"):
        if r[k] != "all":
            out[k] = r[k]
    out["energy_PJ"] = r["energy_PJ"]
    out["ghg_Mt"] = r["ghg_Mt"]
    return out


def discover_sector_vocab(payload):
    """Union of segment labels actually seen for each dim, in this region's
    payload — used to build meta.json's per-sector dimension value lists."""
    vocab = {"energy_source": set(), "end_use": set(), "segment2": set()}
    for r in payload["records"]:
        for k in vocab:
            if r.get(k, "all") != "all":
                vocab[k].add(r[k])
    return vocab


# =============================================================================
# Per-region build
# =============================================================================

def build_region(region, slug, refresh=False):
    print(f"\n--- {region} ({REGIONS[region][0]}) ---")
    plan = build_table_plan(region, slug, refresh=refresh)

    expected_keys = (
        ["energy_by_source", "energy_by_end_use", "households",
         "heating_system_stock", "appliance_stock"]
        + [f"energy_by_source:{bt}" for bt in BUILDING_TYPE_MAP.values()]
        + [f"energy_by_end_use:{bt}" for bt in BUILDING_TYPE_MAP.values()]
    )
    missing = [k for k in expected_keys if k not in plan]
    if missing:
        print(f"  !! missing expected tables: {missing}")

    records = []
    explanatory = []

    for key in ("energy_by_source", "energy_by_end_use"):
        if key not in plan:
            continue
        table_num = plan[key]
        xls_path = download_table_xls(region, table_num, refresh=refresh)
        rows = parse_table_rows(xls_path)
        dim_kind = "energy_source" if key == "energy_by_source" else "end_use"
        records.extend(extract_energy_table(rows, dim_kind, "all"))
        explanatory.extend(extract_explanatory_from_energy_table(rows, "all"))

    for role in ("energy_by_source", "energy_by_end_use"):
        for bt in BUILDING_TYPE_MAP.values():
            key = f"{role}:{bt}"
            if key not in plan:
                continue
            table_num = plan[key]
            xls_path = download_table_xls(region, table_num, refresh=refresh)
            rows = parse_table_rows(xls_path)
            dim_kind = "energy_source" if role == "energy_by_source" else "end_use"
            records.extend(extract_energy_table(rows, dim_kind, bt))
            explanatory.extend(extract_explanatory_from_energy_table(rows, bt))

    if "households" in plan:
        xls_path = download_table_xls(region, plan["households"], refresh=refresh)
        explanatory.extend(extract_households_table(parse_table_rows(xls_path)))

    if "heating_system_stock" in plan:
        xls_path = download_table_xls(region, plan["heating_system_stock"], refresh=refresh)
        explanatory.extend(extract_heating_system_stock_table(parse_table_rows(xls_path)))

    if "appliance_stock" in plan:
        xls_path = download_table_xls(region, plan["appliance_stock"], refresh=refresh)
        explanatory.extend(extract_appliance_stock_table(parse_table_rows(xls_path)))

    # Dedupe records: the region-wide 'all/all/all' totals row is emitted by
    # both energy_by_source and energy_by_end_use tables (same underlying
    # total, sourced twice) — keep the first occurrence.
    seen = set()
    dedup_records = []
    for r in records:
        key = (r["year"], r["energy_source"], r["end_use"], r["building_type"])
        if key in seen:
            continue
        seen.add(key)
        dedup_records.append(r)

    seen_exp = set()
    dedup_explanatory = []
    for e in explanatory:
        key = (e["year"], e["variable"], e["segment"])
        if key in seen_exp:
            continue
        seen_exp.add(key)
        dedup_explanatory.append(e)

    dedup_records.sort(key=lambda r: (r["year"], r["building_type"], r["energy_source"], r["end_use"]))
    dedup_explanatory.sort(key=lambda e: (e["variable"], e["segment"], e["year"]))

    print(f"  {len(dedup_records)} records, {len(dedup_explanatory)} explanatory rows")
    return {"region": region, "records": dedup_records, "explanatory": dedup_explanatory}


def compact_record(r):
    """Drop dimension keys equal to 'all' to hit the size budget — see the
    'compact form' note in meta.json. A missing energy_source/end_use/
    building_type key means 'all' for that dimension, same as if it were
    present and set to the string 'all'."""
    out = {"year": r["year"]}
    for k in ("energy_source", "end_use", "building_type"):
        if r[k] != "all":
            out[k] = r[k]
    out["energy_PJ"] = r["energy_PJ"]
    out["ghg_Mt"] = r["ghg_Mt"]
    return out


# =============================================================================
# Validation
# =============================================================================

def validate(region_payloads):
    print("\n" + "=" * 60)
    print("VALIDATION REPORT")
    print("=" * 60)
    warnings = 0

    # --- no negative values ---
    for region, payload in region_payloads.items():
        for r in payload["records"]:
            for f in ("energy_PJ", "ghg_Mt"):
                if r[f] is not None and r[f] < 0:
                    print(f"  !! {region}: negative {f}={r[f]} at {r}")
                    warnings += 1
        for e in payload["explanatory"]:
            if e["value"] is not None and e["value"] < 0:
                print(f"  !! {region}: negative explanatory value {e}")
                warnings += 1

    # --- sum of provinces ~ Canada total, per year, at the 'all/all/all' aggregate ---
    provinces = [r for r in region_payloads if r != "ca"]
    if "ca" in region_payloads:
        ca_totals = {r["year"]: r["energy_PJ"] for r in region_payloads["ca"]["records"]
                     if r["energy_source"] == "all" and r["end_use"] == "all"
                     and r["building_type"] == "all" and r["energy_PJ"] is not None}
        prov_sums = {}
        for p in provinces:
            for r in region_payloads[p]["records"]:
                if r["energy_source"] == "all" and r["end_use"] == "all" and \
                        r["building_type"] == "all" and r["energy_PJ"] is not None:
                    prov_sums[r["year"]] = prov_sums.get(r["year"], 0) + r["energy_PJ"]
        for yr in sorted(set(ca_totals) & set(prov_sums)):
            ca_val, prov_val = ca_totals[yr], prov_sums[yr]
            if ca_val == 0:
                continue
            pct_off = abs(ca_val - prov_val) / ca_val * 100
            if pct_off > 2:
                print(f"  !! {yr}: sum(provinces)={prov_val:.1f} PJ vs Canada={ca_val:.1f} PJ "
                      f"({pct_off:.1f}% off)")
                warnings += 1
        print(f"  checked province-sum-vs-Canada for {len(set(ca_totals) & set(prov_sums))} years"
              f" (energy_PJ, all/all/all)")

    # --- sum of end-uses ~ sector total (energy_source='all' rows), per region/year ---
    for region, payload in region_payloads.items():
        by_bt_year_total = {}
        by_bt_year_enduse_sum = {}
        for r in payload["records"]:
            if r["energy_source"] != "all":
                continue
            key = (r["building_type"], r["year"])
            if r["end_use"] == "all" and r["energy_PJ"] is not None:
                by_bt_year_total[key] = r["energy_PJ"]
            elif r["end_use"] != "all" and r["energy_PJ"] is not None:
                by_bt_year_enduse_sum[key] = by_bt_year_enduse_sum.get(key, 0) + r["energy_PJ"]
        checked = 0
        for key in set(by_bt_year_total) & set(by_bt_year_enduse_sum):
            total, summed = by_bt_year_total[key], by_bt_year_enduse_sum[key]
            if total == 0:
                continue
            pct_off = abs(total - summed) / total * 100
            checked += 1
            if pct_off > 2:
                bt, yr = key
                print(f"  !! {region} {bt} {yr}: sum(end-uses)={summed:.1f} PJ vs "
                      f"total={total:.1f} PJ ({pct_off:.1f}% off)")
                warnings += 1
        if checked:
            print(f"  {region}: checked end-use-sum-vs-total for {checked} (building_type,year) pairs")

    print("=" * 60)
    if warnings == 0:
        print("no issues found")
    else:
        print(f"{warnings} warning(s) — see above")
    print("=" * 60)


def validate_generic(sector_prefix, region_payloads):
    """Same checks as validate(), generalized to segment2 instead of
    building_type, and skipping the end-use-sum-vs-total check for sectors
    that have no end_use dimension at all (industrial, transportation)."""
    print("\n" + "=" * 60)
    print(f"VALIDATION REPORT — {sector_prefix}")
    print("=" * 60)
    warnings = 0

    for region, payload in region_payloads.items():
        for r in payload["records"]:
            for f in ("energy_PJ", "ghg_Mt"):
                if r[f] is not None and r[f] < 0:
                    print(f"  !! {region}: negative {f}={r[f]} at {r}")
                    warnings += 1
        for e in payload["explanatory"]:
            if e["value"] is not None and e["value"] < 0:
                print(f"  !! {region}: negative explanatory value {e}")
                warnings += 1

    provinces = [r for r in region_payloads if r != "ca"]
    if "ca" in region_payloads:
        ca_totals = {r["year"]: r["energy_PJ"] for r in region_payloads["ca"]["records"]
                     if r["energy_source"] == "all" and r["end_use"] == "all"
                     and r["segment2"] == "all" and r["energy_PJ"] is not None}
        prov_sums = {}
        for p in provinces:
            for r in region_payloads[p]["records"]:
                if r["energy_source"] == "all" and r["end_use"] == "all" and \
                        r["segment2"] == "all" and r["energy_PJ"] is not None:
                    prov_sums[r["year"]] = prov_sums.get(r["year"], 0) + r["energy_PJ"]
        checked = 0
        for yr in sorted(set(ca_totals) & set(prov_sums)):
            ca_val, prov_val = ca_totals[yr], prov_sums[yr]
            if ca_val == 0:
                continue
            checked += 1
            pct_off = abs(ca_val - prov_val) / ca_val * 100
            if pct_off > 2:
                print(f"  !! {yr}: sum(regions)={prov_val:.1f} PJ vs Canada={ca_val:.1f} PJ "
                      f"({pct_off:.1f}% off)")
                warnings += 1
        print(f"  checked region-sum-vs-Canada for {checked} years (energy_PJ, all/all/all)")

    for region, payload in region_payloads.items():
        has_end_use = any(r["end_use"] != "all" for r in payload["records"])
        if not has_end_use:
            continue
        total_by_year, sum_by_year = {}, {}
        for r in payload["records"]:
            if r["energy_source"] != "all" or r["segment2"] != "all" or r["energy_PJ"] is None:
                continue
            if r["end_use"] == "all":
                total_by_year[r["year"]] = r["energy_PJ"]
            else:
                sum_by_year[r["year"]] = sum_by_year.get(r["year"], 0) + r["energy_PJ"]
        checked = 0
        for yr in set(total_by_year) & set(sum_by_year):
            total, summed = total_by_year[yr], sum_by_year[yr]
            if total == 0:
                continue
            checked += 1
            pct_off = abs(total - summed) / total * 100
            if pct_off > 2:
                print(f"  !! {region} {yr}: sum(end-uses)={summed:.1f} PJ vs total={total:.1f} PJ "
                      f"({pct_off:.1f}% off)")
                warnings += 1
        if checked:
            print(f"  {region}: checked end-use-sum-vs-total for {checked} years")

    print("=" * 60)
    if warnings == 0:
        print("no issues found")
    else:
        print(f"{warnings} warning(s) — see above")
    print("=" * 60)
    return warnings


SEGMENT2_LABELS = {
    "com": "Activity type",
    "tran": "Transportation mode",
    "ind": "Industry",
    "agr": None,  # agriculture has no third dimension
}

GENERIC_SECTOR_GHG_CAVEAT = (
    "ghg_Mt values use the EXCLUDING-electricity-related-emissions convention "
    "where the source table offers that split; a few sub-national tables only "
    "report a single GHG convention with no incl/excl distinction (e.g. "
    "transportation, which is almost entirely direct combustion), in which "
    "case that single reported value is used as-is."
)

SMALL_WORDS = {"and", "of", "or", "the", "for"}


def title_case_label(canon):
    words = canon.split("_")
    out = []
    for i, w in enumerate(words):
        out.append(w if (i > 0 and w in SMALL_WORDS) else w.capitalize())
    return " ".join(out)


def build_dim_block(label, vocab_set):
    return {"label": label, "values": {v: title_case_label(v) for v in sorted(vocab_set)}}


def build_meta(generic_payloads):
    """generic_payloads: {file_prefix: {region_code: payload_or_None}}"""
    sectors = {
        "residential": {
            "label": "Residential",
            "file_prefix": "res",
            "regions": {code: name for code, (name, _slug) in REGIONS.items()},
            "year_range": [2000, int(RELEASE_YEAR)],
            "dims": {
                "energy_source": build_dim_block("Energy source", set(ENERGY_SOURCE_MAP.values())),
                "end_use": build_dim_block("End-use", set(END_USE_MAP.values())),
                "building_type": build_dim_block("Building type", set(BUILDING_TYPE_MAP.values())),
            },
            "has_equipment_stock": True,
            "ghg_caveat": (
                "All ghg_Mt values use the EXCLUDING-electricity-related-emissions "
                "convention. NRCan reports an additional INCLUDING-electricity total "
                "for Canada and each building type's region-wide table, but not for "
                "individual provinces, so it's dropped here to keep the schema "
                "comparable across regions."
            ),
        }
    }

    for prefix, (label, _url_sector) in NEW_SECTORS.items():
        region_payloads = {r: p for r, p in generic_payloads.get(prefix, {}).items() if p}
        vocab = {"energy_source": set(), "end_use": set(), "segment2": set()}
        for payload in region_payloads.values():
            seen = discover_sector_vocab(payload)
            for k in vocab:
                vocab[k] |= seen[k]

        dims = {}
        if vocab["energy_source"]:
            dims["energy_source"] = build_dim_block("Energy source", vocab["energy_source"])
        if vocab["end_use"]:
            dims["end_use"] = build_dim_block("End-use", vocab["end_use"])
        if vocab["segment2"]:
            dims["segment2"] = build_dim_block(SEGMENT2_LABELS[prefix], vocab["segment2"])

        sectors[prefix] = {
            "label": label,
            "file_prefix": prefix,
            "regions": {code: REGIONS_8[code] for code in region_payloads},
            "year_range": [2000, int(RELEASE_YEAR)],
            "dims": dims,
            "has_equipment_stock": False,
            "ghg_caveat": GENERIC_SECTOR_GHG_CAVEAT,
        }

    return {
        "source": "NRCan Office of Energy Efficiency — Comprehensive Energy Use Database",
        "source_url": f"{BASE}/menus/trends/comprehensive_tables/list.cfm",
        "release_year_folder": RELEASE_YEAR,
        "retrieved": pd.Timestamp.now().strftime("%Y-%m-%d"),
        "sectors": sectors,
        "units": {
            "energy_PJ": "petajoules",
            "ghg_Mt": "megatonnes CO2e",
            "households": "thousands",
            "floor_space": "million m2",
            "heating_system_stock": "thousands",
            "appliance_stock": "thousands",
        },
        "records_compact_form": (
            "Each record in <prefix>_<region>.json omits any dimension key "
            "(energy_source/end_use/building_type|segment2) whose value would be "
            "'all' — a MISSING key means 'all' for that dimension. Every record "
            "always has year, energy_PJ, ghg_Mt."
        ),
        "notes": (
            "Suppressed/not-applicable source cells (en-dash/'n.a.'/'X' placeholders) "
            "are mapped to null, never 0. Table numbering differs by region — matched "
            "by table title (or by the download link's rn= parameter, which is "
            "authoritative and occasionally diverges from the table's displayed "
            "number), not by the displayed number. Values rounded to 3 significant "
            "digits. Residential covers 12 regions (NRCan publishes each province/"
            "territory individually); Commercial, Transportation, Industrial and "
            "Agriculture cover 8 regions (Canada, Quebec, Ontario, Manitoba, "
            "Saskatchewan, Alberta, and two NRCan-published aggregates — 'Atlantic' "
            "for NL/PE/NS/NB and 'BC & Territories' for BC/YT/NT/NU — since NRCan "
            "doesn't publish those provinces/territories individually for these "
            "sectors). Commercial/Transportation/Industrial/Agriculture v1 scope is "
            "'all'-level breakdowns only (energy_source, end_use, segment2 each on "
            "their own) — full cross-tabs between these dimensions, and equipment/"
            "appliance stock, are residential-only for now."
        ),
    }


# =============================================================================
# main
# =============================================================================

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--refresh", action="store_true",
                         help="ignore the local cache and re-download everything")
    parser.add_argument("--only", choices=["residential", "new", "all"], default="all",
                         help="residential = Phase 1 sector only; new = the four Phase 4 "
                              "sectors only; all = everything (default)")
    args = parser.parse_args()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    region_payloads = {}
    if args.only in ("residential", "all"):
        for region, (name, slug) in REGIONS.items():
            payload = build_region(region, slug, refresh=args.refresh)
            region_payloads[region] = payload

            out_path = OUTPUT_DIR / f"res_{region}.json"
            compact_payload = {
                "region": payload["region"],
                "records": [compact_record(r) for r in payload["records"]],
                "explanatory": payload["explanatory"],
            }
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(compact_payload, f, ensure_ascii=False, separators=(",", ":"))
            size_kb = out_path.stat().st_size / 1024
            flag = "  !! over 200 KB budget" if size_kb > 200 else ""
            print(f"  wrote {out_path} ({size_kb:.1f} KB){flag}")

    generic_payloads = {}
    if args.only in ("new", "all"):
        for prefix, (label, url_sector) in NEW_SECTORS.items():
            print(f"\n{'#' * 60}\n# {label} ({prefix})\n{'#' * 60}")
            sector_region_payloads = {}
            for region in REGIONS_8:
                payload = build_generic_region(prefix, url_sector, region, refresh=args.refresh)
                if payload is None:
                    continue
                sector_region_payloads[region] = payload

                out_path = OUTPUT_DIR / f"{prefix}_{region}.json"
                compact_payload = {
                    "region": payload["region"],
                    "records": [compact_record_generic(r) for r in payload["records"]],
                    "explanatory": payload["explanatory"],
                }
                with open(out_path, "w", encoding="utf-8") as f:
                    json.dump(compact_payload, f, ensure_ascii=False, separators=(",", ":"))
                size_kb = out_path.stat().st_size / 1024
                flag = "  !! over 200 KB budget" if size_kb > 200 else ""
                print(f"  wrote {out_path} ({size_kb:.1f} KB){flag}")
            generic_payloads[prefix] = sector_region_payloads

    meta_path = OUTPUT_DIR / "meta.json"
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(build_meta(generic_payloads), f, ensure_ascii=False, indent=2)
    print(f"\nwrote {meta_path}")

    if region_payloads:
        validate(region_payloads)
    total_warnings = 0
    for prefix, sector_region_payloads in generic_payloads.items():
        total_warnings += validate_generic(prefix, sector_region_payloads) or 0


if __name__ == "__main__":
    main()
