"""
construction_etl.py

Phase-1 ETL for the Construction Activity Dashboard (see
C:\\Energy\\docs\\archive\\CONSTRUCTION_PLAN.md, sections 1.1 and 2).

Pulls the core monthly building-activity tables from the Statistics Canada
Web Data Service (WDS) REST API and writes compact per-geography JSON for a
static, precomputed dashboard (same pattern as ceud_etl.py -> ceud_json/).

TABLES (product id -> what we keep)
    34-10-0292  Building permits, by type of structure and type of work
                  value (SA current + SA constant $), dwelling units
                  created / lost / demolished, permit count.
    34-10-0293  Investment in building construction
                  value (SA current + SA constant $), work = new / renovation
                  / conversion / total.
    34-10-0151  CMHC housing starts / under construction / completions
                  (Canada + provinces), UNADJUSTED, 5 dwelling types.
                  (Replaced 34-10-0143, whose under-construction and
                  completions series dead-end in 2002/2022.)
    34-10-0154  Same pipeline measures for selected CMAs, UNADJUSTED.
    34-10-0148  Housing starts by intended market (homeowner / rental /
                  condo / co-op / other), Canada + provinces + CMAs.
    34-10-0158  Housing starts, SEASONALLY ADJUSTED AT ANNUAL RATES (SAAR),
                  monthly, Canada + provinces (total units only).

PLAN DIVERGENCE (verified live via getCubeMetadata on 2026-07-09):
    The plan asked for "both SAAR and unadjusted" from 34-10-0151 / 0154, but
    those two tables have NO seasonal-adjustment dimension — they publish
    unadjusted monthly actuals only. The SAAR headline series lives in a
    separate table, 34-10-0158 (Canada + provinces, total starts only), which
    is added here to satisfy the SAAR requirement. CMA-level SAAR is not
    published monthly in these tables, so CMA files carry unadjusted starts
    only. "Semi-detached" in the permits/investment tables is StatCan's
    "Double" structure type.

FETCH
    WDS getFullTableDownloadCSV returns a URL to a zip of the full-table CSV;
    we download, unzip, and filter with pandas. Rows are selected by the
    CSV's COORDINATE column (dot-separated member ids, one per dimension, in
    dimension order) rather than by member NAME — this sidesteps the mojibake
    in accented CMA names (Montreal, Quebec, Trois-Rivieres) entirely. All
    member ids below were confirmed against getCubeMetadata on 2026-07-09.

OUTPUT (construction_json/)
    constr_ca.json, constr_on.json, ... constr_bc.json   (Canada + 10 provinces)
    cma_ottawa.json (ON+QC combined), cma_ottawa_on.json, cma_ottawa_qc.json,
    cma_toronto.json, cma_montreal.json, cma_vancouver.json, cma_calgary.json,
    cma_edmonton.json, cma_winnipeg.json, cma_halifax.json
    meta.json   (per-table last reference month, series start, uom/scalar,
                 the key scheme, and source attribution)

SERIES FORMAT
    {series_key: {"start": "YYYY-MM", "freq": "m", "values": [...]}}
    values is a contiguous monthly array from `start` to the file's latest
    month; missing months are null. Stored values are NORMALIZED, not raw
    StatCan numbers (see store_value / SERIES_UNITS):
      - every dollar series (permits.value.*, invest.*) is stored in MILLIONS
        of current or constant dollars, rounded to 2 decimals;
      - every unit-count series (starts, permits counts, units created/lost/
        demolished) is stored as integer units — including starts_saar.total,
        which StatCan publishes in thousands and we multiply out.

SIZE BUDGET
    Only series a planned chart actually reads are written (see the allowed_*
    builders), and at write time the redundant unadjusted variant of any
    series that also publishes a seasonally adjusted variant is dropped
    (prune_redundant_nsa). Together with integer/2-decimal storage this keeps
    each geography file well under ~100 KB.

SERIES KEY SCHEME
    permits.<var>.<building>.<work>.<adj>
        var       = value | created | lost | demolished | count
        building  = total | residential | non_residential (aggregates: all
                    work types) | single | semi | row | apartment | industrial
                    | commercial | institutional (detail: work=total only)
        work      = total | new | renovation
        adj       = whichever regime survives the prune: aggregates keep
                    sa_current + sa_constant, detail rows exist only as
                    nsa_current (StatCan does not adjust them); counts keep
                    sa (or nsa where no sa is published)
        e.g. permits.value.residential.total.sa_constant
    invest.<structure>.<work>.<adj>
        structure = total | residential | non_residential (all work types) |
                    single | semi | row | apartment | industrial | commercial
                    | institutional (work=total only)
        work      = total | new | renovation | conversion
        adj       = sa_* where published, else nsa_* (post-prune)
    starts_unadj.<estimate>.<unit>
        estimate  = starts | under_construction | completions
        unit      = total | single | semi | row | apartment
                    ('multiples' dropped — recomputable as total - single)
    starts_saar.total                 (SAAR total starts, provinces + Canada)
    starts_market.total.<market>
        market    = homeowner | rental | condo | coop | other
                    (per-dwelling-type market splits dropped — no chart uses them)

USAGE
    pip install requests pandas
    python construction_etl.py            # uses cached downloads if present
    python construction_etl.py --refresh  # force re-download of every table

The script exits non-zero if any table fetch fails, so a scheduled refresh
can skip committing on a partial pull.
"""

import io
import sys
import json
import zipfile
import argparse
from pathlib import Path
from datetime import datetime

import requests
import pandas as pd

# =============================================================================
# CONFIG
# =============================================================================

WDS = "https://www150.statcan.gc.ca/t1/wds/rest"
HEADERS = {"Content-Type": "application/json"}

# repo-relative so the GitHub Action (ubuntu) and local Windows runs both work
REPO_ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = REPO_ROOT / "Python" / "construction_cache"
OUTPUT_DIR = REPO_ROOT / "construction_json"

FLOOR_MONTH = "1990-01"   # trim long CMHC history to keep files small

# --- dimension member subsets (memberId -> canonical label), per table -------
# Geography is always dimension 1 and is handled separately (GEO_* maps below);
# the maps here cover the value/breakdown dimensions in dimension order.

# 34-10-0292 Building permits: dims = geo, building, work, variable, adjustment
P292_BUILDING = {
    1: "total", 4: "residential", 10: "single", 18: "semi", 21: "row",
    24: "apartment", 33: "non_residential", 36: "industrial",
    49: "commercial", 73: "institutional",
}
# Aggregates get the full work-type breakdown; detail building types are kept
# at work=total only (the planned charts never split detail types by work).
P292_AGG = (1, 4, 33)                       # total, residential, non_residential
P292_DETAIL = (10, 18, 21, 24, 36, 49, 73)  # single..apartment, ind/com/inst
P292_WORK = {1: "total", 5: "new", 12: "renovation"}   # 5 = "New ... constructions, total"
P292_VAR = {1: "value", 2: "created", 3: "lost", 4: "demolished", 5: "count"}
# Adjustment/value type. StatCan only publishes the seasonally adjusted and
# constant-dollar series for the *aggregate* building totals at work=total;
# the single/semi/row/apartment and new/renovation breakdowns exist only as
# UNADJUSTED CURRENT dollars. We therefore request all four members and let
# empty combinations drop, so each cell keeps whatever regime it publishes
# (aggregates get all four; detail rows get nsa_current only). Verified 2026-07-09.
P292_ADJ = {1: "nsa_current", 2: "sa_current", 3: "nsa_constant", 4: "sa_constant"}
P292_ADJ_COUNT = {1: "nsa", 2: "sa"}   # counts are current-$ only (constant N/A)

# 34-10-0293 Investment: dims = geo, structure, work, investment-value
P293_STRUCT = {
    1: "total", 2: "residential", 3: "single", 9: "semi", 10: "row",
    11: "apartment", 13: "non_residential", 14: "industrial",
    19: "commercial", 28: "institutional",
}
P293_WORK = {1: "total", 2: "new", 3: "renovation", 4: "conversion"}
P293_AGG = (1, 2, 13)                        # total, residential, non_residential
P293_DETAIL = (3, 9, 10, 11, 14, 19, 28)     # single..apartment, ind/com/inst
# Same availability caveat as permits: SA / constant $ exist for some
# structure x work cells (notably new construction) but not all, so we request
# every regime and drop the empties. Member order differs from 0292.
P293_ADJ = {1: "nsa_current", 2: "nsa_constant", 3: "sa_current", 4: "sa_constant"}

# 34-10-0151 starts/uc/completions (Canada+prov, monthly, all centres):
# dims = geo, estimate, unit. NOTE: originally 34-10-0143 per the plan, but
# 0143's under-construction series dead-ends in 2002-06 and completions in
# 2022-12 for Canada/provinces (verified 2026-07-09); 0151 carries all three
# estimates current. Unit 5 = "Apartment and other units".
P151_EST = {1: "starts", 2: "under_construction", 3: "completions"}
P151_UNIT = {1: "total", 2: "single", 3: "semi", 4: "row", 5: "apartment"}

# 34-10-0154 starts/uc/completions (CMAs): dims = geo, estimate, unit
P154_EST = {1: "starts", 2: "under_construction", 3: "completions"}
P154_UNIT = {1: "total", 2: "single", 3: "semi", 4: "row", 5: "apartment"}

# NOTE — provincial under-construction / completions END AT 2022 by CMHC's
# choice, not ours. Verified live 2026-07-09 against every candidate table:
# 34-10-0151 (monthly) has them to 2022-12, 34-10-0136 (quarterly) to 2022-10,
# 34-10-0139 (quarterly UC) and even annual 34-10-0126 are null after 2022.
# Only starts continue monthly at the provincial level; current UC/completions
# exist only for the selected CMAs (34-10-0154). Do not re-add a "fix" table —
# there isn't one. The dashboard annotates the provincial gap instead.

# 34-10-0148 starts by market: dims = geo, dwelling, market. Only dwelling
# unit=total (member 1) is kept — the market-split chart doesn't break out
# dwelling types.
P148_MARKET = {1: "homeowner", 2: "rental", 3: "condo", 4: "coop", 5: "other"}

# --- geography member ids per table ------------------------------------------
PROV_CODES = ["ca", "nl", "pe", "ns", "nb", "qc", "on", "mb", "sk", "ab", "bc"]

GEO_292 = {  # also used for 0293 (identical geography member ids)
    "ca": 1, "nl": 2, "pe": 3, "ns": 4, "nb": 5, "qc": 6, "on": 7, "mb": 8,
    "sk": 9, "ab": 10, "bc": 11,
    "ottawa_on": 41, "ottawa_qc": 25, "toronto": 45, "montreal": 24,
    "vancouver": 59, "calgary": 53, "edmonton": 54, "winnipeg": 48, "halifax": 19,
}
GEO_151 = {"ca": 1, "nl": 2, "pe": 3, "ns": 4, "nb": 5, "qc": 6, "on": 7,
           "mb": 8, "sk": 9, "ab": 10, "bc": 11}
GEO_158 = {"ca": 1, "nl": 3, "pe": 4, "ns": 5, "nb": 6, "qc": 7, "on": 8,
           "mb": 10, "sk": 11, "ab": 12, "bc": 13}
GEO_154 = {"ottawa": 11, "ottawa_on": 12, "ottawa_qc": 13, "toronto": 23,
           "montreal": 29, "vancouver": 25, "calgary": 2, "edmonton": 4,
           "winnipeg": 28, "halifax": 5}
GEO_148 = {"ca": 1, "nl": 2, "pe": 3, "ns": 4, "nb": 5, "qc": 6, "on": 7,
           "mb": 8, "sk": 9, "ab": 10, "bc": 11,
           "ottawa": 23, "ottawa_on": 24, "ottawa_qc": 25, "toronto": 35,
           "montreal": 21, "vancouver": 37, "calgary": 13, "edmonton": 15,
           "winnipeg": 40, "halifax": 16}

# CMA output files. Each entry lists how to source that geo from the two
# permits/investment members (summed if two) — everything else keys off the
# GEO_154 / GEO_148 native member for that CMA.
CMA_FILES = ["ottawa", "ottawa_on", "ottawa_qc", "toronto", "montreal",
             "vancouver", "calgary", "edmonton", "winnipeg", "halifax"]

# For permits (0292) and investment (0293): CMA -> list of member ids to sum.
# Ottawa-Gatineau has no native combined member in these two tables, so the
# combined file sums the Ontario part (41) and Quebec part (25).
CMA_292_MEMBERS = {
    "ottawa": [41, 25], "ottawa_on": [41], "ottawa_qc": [25],
    "toronto": [45], "montreal": [24], "vancouver": [59], "calgary": [53],
    "edmonton": [54], "winnipeg": [48], "halifax": [19],
}

# Units of the STORED values, keyed by series-key prefix (longest match wins).
# StatCan mixes scalars across tables (permit values in thousands of $,
# investment in $, SAAR starts in thousands of units); store_value() normalizes
# everything at write time so the dashboard never has to special-case a table:
# dollar series -> millions of dollars, unit counts -> plain integer units.
# 'scale' is the multiplier from stored value to base units.
SERIES_UNITS = {
    "permits.value": {"unit": "dollars", "scale": 1_000_000, "stored": "millions"},
    "permits.count": {"unit": "permits", "scale": 1},
    "permits.created": {"unit": "dwelling_units", "scale": 1},
    "permits.lost": {"unit": "dwelling_units", "scale": 1},
    "permits.demolished": {"unit": "dwelling_units", "scale": 1},
    "invest": {"unit": "dollars", "scale": 1_000_000, "stored": "millions"},
    "starts_unadj": {"unit": "dwelling_units", "scale": 1},
    "starts_saar": {"unit": "dwelling_units", "scale": 1},
    "starts_market": {"unit": "dwelling_units", "scale": 1},
}

DISPLAY = {
    "ca": "Canada", "nl": "Newfoundland and Labrador", "pe": "Prince Edward Island",
    "ns": "Nova Scotia", "nb": "New Brunswick", "qc": "Quebec", "on": "Ontario",
    "mb": "Manitoba", "sk": "Saskatchewan", "ab": "Alberta", "bc": "British Columbia",
    "ottawa": "Ottawa-Gatineau (Ontario/Quebec)",
    "ottawa_on": "Ottawa-Gatineau, Ontario part",
    "ottawa_qc": "Ottawa-Gatineau, Quebec part",
    "toronto": "Toronto, Ontario", "montreal": "Montreal, Quebec",
    "vancouver": "Vancouver, British Columbia", "calgary": "Calgary, Alberta",
    "edmonton": "Edmonton, Alberta", "winnipeg": "Winnipeg, Manitoba",
    "halifax": "Halifax, Nova Scotia",
}


# =============================================================================
# HTTP + caching
# =============================================================================

def get_cube_metadata(pid):
    """Return the cube metadata object for a product id (used to confirm the
    dimension/member layout the id maps below assume)."""
    r = requests.post(f"{WDS}/getCubeMetadata", data=json.dumps([{"productId": pid}]),
                      headers=HEADERS, timeout=60)
    r.raise_for_status()
    payload = r.json()[0]
    if payload.get("status") != "SUCCESS":
        raise RuntimeError(f"getCubeMetadata {pid}: {payload.get('status')}")
    return payload["object"]


def download_full_zip(pid, refresh=False):
    """getFullTableDownloadCSV -> download the CSV zip -> return the local path
    to the cached ZIP. We cache the *compressed* zip (a couple hundred MB even
    for the biggest cubes) rather than the unzipped CSV — 34-10-0292 alone
    unzips to ~9 GB — and stream the CSV out of it in chunks (see
    extract_table). Reruns skip the re-download unless refresh=True."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    zip_path = CACHE_DIR / f"{pid}.zip"
    if not refresh and zip_path.exists() and zip_path.stat().st_size > 0:
        return zip_path

    r = requests.get(f"{WDS}/getFullTableDownloadCSV/{pid}/en", timeout=60)
    r.raise_for_status()
    meta = r.json()
    if meta.get("status") != "SUCCESS":
        raise RuntimeError(f"getFullTableDownloadCSV {pid}: {meta.get('status')}")
    zip_url = meta["object"]

    with requests.get(zip_url, timeout=600, stream=True) as z:
        z.raise_for_status()
        with open(zip_path, "wb") as out:
            for block in z.iter_content(chunk_size=1 << 20):
                out.write(block)
    return zip_path


def open_data_csv(zip_path):
    """Return (open ZipFile, name of the data CSV member) for a cached table
    zip. The data CSV is '<pid>.csv'; the sibling '<pid>_MetaData.csv' is
    skipped."""
    zf = zipfile.ZipFile(zip_path)
    data_name = next(n for n in zf.namelist()
                     if n.lower().endswith(".csv") and "metadata" not in n.lower())
    return zf, data_name


# =============================================================================
# CSV -> per-member series extraction
# =============================================================================

def parse_value(v):
    if v is None:
        return None
    v = str(v).strip()
    if v == "" or v.lower() == "nan":
        return None
    try:
        return float(v)
    except ValueError:
        return None


CHUNK_ROWS = 500_000
USE_COLS = ["REF_DATE", "COORDINATE", "VALUE", "UOM", "SCALAR_FACTOR"]


def extract_table(zip_path, ndims, allowed, geo_ids):
    """
    Stream the (possibly multi-GB) table CSV out of its zip in chunks, keeping
    only the exact rows we want, matched on the COORDINATE column.

    We pre-compute the full set of wanted COORDINATE strings — the cross
    product of the requested geography member ids and `allowed`'s non-geo
    member-id tuples — so each chunk is filtered with a single vectorized
    isin() against a few thousand strings, rather than parsing every one of
    the tens/hundreds of millions of coordinates in the file.

    allowed : {tuple(non-geo member ids in dim order) -> series key}
    geo_ids : iterable of geography (dim 1) member ids to keep.

    Returns (series, uom, scalar) where
        series : {geo_member_id: {series_key: {"YYYY-MM": value}}}
        uom    : the unit-of-measure string(s) seen ("; "-joined if >1)
        scalar : the SCALAR_FACTOR string(s) seen ("; "-joined if >1)
    """
    # full coordinate string -> (geo id, series key)
    coord_map = {}
    for geo in geo_ids:
        for rest, key in allowed.items():
            coord = ".".join(str(x) for x in (geo,) + rest)
            coord_map[coord] = (geo, key)
    wanted = set(coord_map)

    series = {}
    uoms, scalars = set(), set()

    zf, data_name = open_data_csv(zip_path)
    rows_seen = 0
    try:
        with zf.open(data_name) as f:
            for chunk in pd.read_csv(f, dtype=str, usecols=USE_COLS,
                                     chunksize=CHUNK_ROWS):
                rows_seen += len(chunk)
                if rows_seen % (CHUNK_ROWS * 20) == 0:
                    print(f"    ...{rows_seen:,} rows scanned", flush=True)
                sub = chunk[chunk["COORDINATE"].isin(wanted)]
                if sub.empty:
                    continue
                for coord, month, raw, uom, scal in zip(
                        sub["COORDINATE"], sub["REF_DATE"], sub["VALUE"],
                        sub["UOM"], sub["SCALAR_FACTOR"]):
                    if month < FLOOR_MONTH:
                        continue
                    val = parse_value(raw)
                    if val is None:
                        continue
                    geo, key = coord_map[coord]
                    series.setdefault(geo, {}).setdefault(key, {})[month] = val
                    uoms.add(str(uom))
                    scalars.add(str(scal))
    finally:
        zf.close()

    join = lambda s: "; ".join(sorted(x for x in s if x and x != "nan")) or None
    return series, join(uoms), join(scalars)


# --- allowed-tuple builders (encode the per-table keep rules) ----------------

def allowed_292():
    """permits.<var>.<building>.<work>.<adj>, whitelisted to what the plan's
    charts read (docs/archive/CONSTRUCTION_PLAN.md section 3). Value: aggregates get every
    work x adjustment (empties drop; StatCan publishes SA/constant for
    aggregates only), detail building types get work=total only. nsa_constant
    is never requested — no chart deflates an unadjusted series. The redundant
    nsa variants that survive alongside an sa sibling are dropped at write
    time by prune_redundant_nsa()."""
    a = {}
    for b_id in P292_AGG:
        b = P292_BUILDING[b_id]
        for w_id, w in P292_WORK.items():
            for adj_id, adj in P292_ADJ.items():
                if adj == "nsa_constant":
                    continue
                a[(b_id, w_id, 1, adj_id)] = f"permits.value.{b}.{w}.{adj}"
    for b_id in P292_DETAIL:
        b = P292_BUILDING[b_id]
        # detail types publish nsa_current only; request sa_current too in
        # case StatCan starts adjusting them, and let the empty drop
        for adj_id, adj in P292_ADJ.items():
            if adj in ("nsa_constant", "sa_constant"):
                continue
            a[(b_id, 1, 1, adj_id)] = f"permits.value.{b}.total.{adj}"
    # count (number of permits): totals + res/non-res split, work=total
    for b_id in P292_AGG:
        b = P292_BUILDING[b_id]
        for adj_id, adj in P292_ADJ_COUNT.items():
            a[(b_id, 1, 5, adj_id)] = f"permits.count.{b}.total.{adj}"
    # units created: total + residential only (pipeline + net-supply charts);
    # per-dwelling-type creation is not charted — starts cover that split
    for b_id in (1, 4):
        b = P292_BUILDING[b_id]
        for w_id in (1, 5):
            w = P292_WORK[w_id]
            for adj_id, adj in P292_ADJ_COUNT.items():
                a[(b_id, w_id, 2, adj_id)] = f"permits.created.{b}.{w}.{adj}"
    # units lost / demolished: total + residential, work total
    for var_id, var in ((3, "lost"), (4, "demolished")):
        for b_id in (1, 4):
            b = P292_BUILDING[b_id]
            for adj_id, adj in P292_ADJ_COUNT.items():
                a[(b_id, 1, var_id, adj_id)] = f"permits.{var}.{b}.total.{adj}"
    return a


def allowed_293():
    """Same whitelist idea as permits: aggregates x every work type, detail
    structures at work=total only. All four regimes are requested (investment
    publishes constant $ more widely than permits); redundant nsa variants are
    pruned at write time."""
    a = {}
    for s_id in P293_AGG:
        s = P293_STRUCT[s_id]
        for w_id, w in P293_WORK.items():
            for adj_id, adj in P293_ADJ.items():
                a[(s_id, w_id, adj_id)] = f"invest.{s}.{w}.{adj}"
    for s_id in P293_DETAIL:
        s = P293_STRUCT[s_id]
        for adj_id, adj in P293_ADJ.items():
            a[(s_id, 1, adj_id)] = f"invest.{s}.total.{adj}"
    return a


def allowed_pipeline(est_map, unit_map, prefix="starts_unadj"):
    a = {}
    for e_id, e in est_map.items():
        for u_id, u in unit_map.items():
            a[(e_id, u_id)] = f"{prefix}.{e}.{u}"
    return a


def allowed_148():
    """Market split at dwelling unit=total (member 1) only."""
    return {(1, m_id): f"starts_market.total.{m}"
            for m_id, m in P148_MARKET.items()}


# =============================================================================
# assembly
# =============================================================================

def merge_add(dst, src):
    """Add src's {month: value} into dst (per-series summation for combined
    geographies like Ottawa-Gatineau = Ontario part + Quebec part)."""
    for month, v in src.items():
        dst[month] = dst.get(month, 0.0) + v


def collect_geo(*member_series_lists):
    """Merge several {series_key: {month: value}} dicts (one per source table)
    into a single flat series dict for one output geography. Keys never collide
    across tables (distinct prefixes), so a plain update suffices; the summing
    of multiple members within one table is done by the caller via add_members."""
    out = {}
    for d in member_series_lists:
        for key, months in d.items():
            out.setdefault(key, {})
            merge_add(out[key], months)
    return out


def add_members(table_series, member_ids):
    """Sum one table's series across a list of geo member ids -> a single
    {series_key: {month: value}} dict."""
    combined = {}
    for mid in member_ids:
        for key, months in table_series.get(mid, {}).items():
            combined.setdefault(key, {})
            merge_add(combined[key], months)
    return combined


def month_range(start, end):
    """Inclusive list of 'YYYY-MM' from start to end."""
    sy, sm = int(start[:4]), int(start[5:7])
    ey, em = int(end[:4]), int(end[5:7])
    out = []
    y, m = sy, sm
    while (y, m) <= (ey, em):
        out.append(f"{y:04d}-{m:02d}")
        m += 1
        if m > 12:
            m = 1
            y += 1
    return out


# nsa adjustment suffix -> the sa sibling that makes it redundant
_NSA_TO_SA = {"nsa_current": "sa_current", "nsa_constant": "sa_constant",
              "nsa": "sa"}


def prune_redundant_nsa(geo_series):
    """Drop any unadjusted series whose seasonally adjusted sibling is also
    present — the dashboard always prefers SA, so shipping both is waste.
    Detail rows that only publish nsa_* keep it (their fallback)."""
    keys = set(geo_series)
    for key in list(keys):
        base, _, adj = key.rpartition(".")
        sa = _NSA_TO_SA.get(adj)
        if sa and f"{base}.{sa}" in keys:
            del geo_series[key]


def store_value(key, v):
    """Normalize a raw StatCan value to its stored form (see SERIES_UNITS):
    dollar series -> millions of dollars (2 decimals, int when whole), unit
    counts -> integer units. permits.value is published in thousands of $,
    invest in $, starts_saar in thousands of units."""
    if key.startswith("permits.value"):
        v = v / 1_000.0
    elif key.startswith("invest."):
        v = v / 1_000_000.0
    elif key.startswith("starts_saar"):
        return int(round(v * 1000))
    else:
        return int(round(v))
    v = round(v, 2)
    return int(v) if v == int(v) else v


def finalize(geo_series):
    """Convert {series_key: {month: value}} -> {series_key: {start, freq,
    values[]}}. Each series runs from its own first month to the file's global
    last month, with nulls for interior/trailing gaps. Prunes redundant nsa
    variants and normalizes stored values (see store_value)."""
    prune_redundant_nsa(geo_series)
    all_months = set()
    for months in geo_series.values():
        all_months.update(months)
    if not all_months:
        return {}
    global_last = max(all_months)

    out = {}
    for key in sorted(geo_series):
        months = geo_series[key]
        if not months:
            continue
        start = min(months)
        idx = month_range(start, global_last)
        values = [store_value(key, months[m]) if m in months else None
                  for m in idx]
        out[key] = {"start": start, "freq": "m", "values": values}
    return out


# =============================================================================
# metadata helpers
# =============================================================================

def table_span(series):
    """(earliest month, latest month) across every member/series in one
    extracted table, honoring the FLOOR_MONTH trim already applied."""
    months = set()
    for by_key in series.values():
        for m in by_key.values():
            months.update(m)
    if not months:
        return None, None
    return min(months), max(months)


# =============================================================================
# main
# =============================================================================

TABLE_IDS = {
    "permits": 34100292,
    "invest": 34100293,
    "starts_prov": 34100151,
    "starts_cma": 34100154,
    "starts_saar": 34100158,
    "starts_market": 34100148,
}

# Expected (dimension count, first non-geo dimension name) used to sanity-check
# the live cube against the member-id maps above before we trust them.
EXPECTED_DIMS = {
    34100292: 5, 34100293: 4, 34100151: 3, 34100154: 3, 34100158: 1,
    34100148: 3,
}


def verify_layout(pid, refresh_meta=True):
    """Confirm the live cube still has the dimension count our id maps assume.
    Cheap insurance against StatCan restructuring a table under our feet."""
    meta = get_cube_metadata(pid)
    ndims = len(meta["dimension"])
    if ndims != EXPECTED_DIMS[pid]:
        raise RuntimeError(
            f"{pid}: live cube has {ndims} dimensions, expected "
            f"{EXPECTED_DIMS[pid]} — member-id maps need review")
    return meta


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--refresh", action="store_true",
                        help="ignore cached CSVs and re-download every table")
    args = parser.parse_args()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # --- fetch + extract each table --------------------------------------
    print("=== fetching + extracting tables ===")
    extracted = {}     # name -> (series, uom, scalar)
    spans = {}         # pid -> (first_month, last_month)
    try:
        for name, pid in TABLE_IDS.items():
            verify_layout(pid)
            zip_path = download_full_zip(pid, refresh=args.refresh)
            if name == "permits":
                res = extract_table(zip_path, 5, allowed_292(), GEO_292.values())
            elif name == "invest":
                res = extract_table(zip_path, 4, allowed_293(), GEO_292.values())
            elif name == "starts_prov":
                res = extract_table(zip_path, 3, allowed_pipeline(P151_EST, P151_UNIT),
                                    GEO_151.values())
            elif name == "starts_cma":
                res = extract_table(zip_path, 3, allowed_pipeline(P154_EST, P154_UNIT),
                                    GEO_154.values())
            elif name == "starts_saar":
                res = extract_table(zip_path, 1, {(): "starts_saar.total"},
                                    GEO_158.values())
            elif name == "starts_market":
                res = extract_table(zip_path, 3, allowed_148(), GEO_148.values())
            extracted[name] = res
            spans[pid] = table_span(res[0])
            lo, hi = spans[pid]
            print(f"  {pid} {name}: {sum(len(v) for v in res[0].values())} series "
                  f"across {len(res[0])} geos, {lo}..{hi}")
    except Exception as e:
        print(f"\n!! fetch/extract failed: {e}", file=sys.stderr)
        sys.exit(1)

    permits_s = extracted["permits"][0]
    invest_s = extracted["invest"][0]
    startsp_s = extracted["starts_prov"][0]
    startscma_s = extracted["starts_cma"][0]
    saar_s = extracted["starts_saar"][0]
    market_s = extracted["starts_market"][0]

    # --- write province + Canada files -----------------------------------
    print("\n=== writing geography files ===")
    written = []

    for code in PROV_CODES:
        parts = [
            add_members(permits_s, [GEO_292[code]]),
            add_members(invest_s, [GEO_292[code]]),
            add_members(startsp_s, [GEO_151[code]]),
            add_members(saar_s, [GEO_158[code]]),
            add_members(market_s, [GEO_148[code]]),
        ]
        geo_series = collect_geo(*parts)
        payload = {"geo": code, "name": DISPLAY[code],
                   "series": finalize(geo_series)}
        out_path = OUTPUT_DIR / f"constr_{code}.json"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))
        written.append(out_path)

    # --- write CMA files -------------------------------------------------
    for code in CMA_FILES:
        parts = [
            add_members(permits_s, CMA_292_MEMBERS[code]),
            add_members(invest_s, CMA_292_MEMBERS[code]),
            add_members(market_s, [GEO_148[code]]) if code in GEO_148 else {},
        ]
        # pipeline: 0154 has a native combined Ottawa member; other CMAs single
        if code in GEO_154:
            parts.append(add_members(startscma_s, [GEO_154[code]]))
        geo_series = collect_geo(*parts)
        payload = {"geo": code, "name": DISPLAY[code],
                   "series": finalize(geo_series)}
        out_path = OUTPUT_DIR / f"cma_{code}.json"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))
        written.append(out_path)

    for p in written:
        kb = p.stat().st_size / 1024
        flag = "  !! over 300 KB budget" if kb > 300 else ""
        print(f"  wrote {p.name} ({kb:.1f} KB){flag}")

    # --- meta.json -------------------------------------------------------
    def uom_scalar(name):
        _, uom, scalar = extracted[name]
        return {"uom": uom, "scalar_factor": scalar}

    meta = {
        "source": "Statistics Canada, Web Data Service (WDS)",
        "source_url": "https://www150.statcan.gc.ca/t1/wds/rest",
        "retrieved": datetime.now().strftime("%Y-%m-%d"),
        "note": (
            "Stored values are normalized: dollar series (permits.value.*, "
            "invest.*) are in MILLIONS of dollars; all unit counts are integer "
            "units (starts_saar already multiplied out from StatCan's "
            "thousands). The uom/scalar fields record what StatCan publishes, "
            "not what is stored. "
            "Rows selected by COORDINATE member ids, not member names. "
            "34-10-0151/0154 are UNADJUSTED; SAAR (starts_saar.*) comes from "
            "34-10-0158 (provinces + Canada, total starts only). "
            "Ottawa-Gatineau combined = Ontario part + Quebec part for permits "
            "and investment; native combined member for starts. "
            "'semi' = StatCan 'Double' in permits/investment. "
            "Permit VALUE and investment: seasonally adjusted (sa_*) and "
            "constant-dollar (*_constant) series are published only for certain "
            "cells — the aggregate building totals at work=total for permits, "
            "and select structure x work cells (e.g. new construction) for "
            "investment. Unadjusted (nsa_*) series are shipped ONLY where no "
            "seasonally adjusted sibling exists (detail building/structure "
            "types); when both existed, the nsa variant was pruned. Use sa_* "
            "for headline figures and whatever adj suffix a detail series "
            "carries for the breakdowns."
        ),
        "series_key_scheme": {
            "permits": "permits.<var>.<building>.<work>.<adj>  "
                       "(var=value|created|lost|demolished|count; aggregates "
                       "total/residential/non_residential carry all work types, "
                       "detail types carry work=total only; adj is sa_* where "
                       "published, else nsa_*)",
            "invest": "invest.<structure>.<work>.<adj>  (same aggregate/detail "
                      "split and adj rule as permits)",
            "starts_unadj": "starts_unadj.<estimate>.<unit>  (unit=total|single|"
                            "semi|row|apartment)",
            "starts_saar": "starts_saar.total",
            "starts_market": "starts_market.total.<market>",
        },
        "provincial_pipeline_gap": (
            "CMHC discontinued PROVINCIAL under-construction and completions "
            "publication after 2022 in every table (34-10-0151/0136/0139/0126 "
            "all null from 2023). starts_unadj.under_construction.* and "
            ".completions.* therefore end 2022-12 in province/Canada files but "
            "are current in CMA files (34-10-0154). Verified 2026-07-09."
        ),
        "tables": {
            "34-10-0292": {
                "role": "permits", "last_month": spans[34100292][1],
                "series_start": spans[34100292][0], **uom_scalar("permits"),
            },
            "34-10-0293": {
                "role": "invest", "last_month": spans[34100293][1],
                "series_start": spans[34100293][0], **uom_scalar("invest"),
            },
            "34-10-0151": {
                "role": "starts_unadj (Canada + provinces)",
                "last_month": spans[34100151][1],
                "series_start": spans[34100151][0], **uom_scalar("starts_prov"),
            },
            "34-10-0154": {
                "role": "starts_unadj (CMAs)", "last_month": spans[34100154][1],
                "series_start": spans[34100154][0], **uom_scalar("starts_cma"),
            },
            "34-10-0158": {
                "role": "starts_saar (SAAR, total starts)",
                "last_month": spans[34100158][1],
                "series_start": spans[34100158][0], **uom_scalar("starts_saar"),
            },
            "34-10-0148": {
                "role": "starts_market", "last_month": spans[34100148][1],
                "series_start": spans[34100148][0], **uom_scalar("starts_market"),
            },
        },
        "series_units": SERIES_UNITS,
        "series_units_note": (
            "Stored values are normalized at write time. Dollar series "
            "(permits.value.*, invest.*) are stored in millions of dollars — "
            "multiply by the 'scale' (1e6) of the longest-matching prefix in "
            "series_units to get dollars. All unit-count series, including "
            "starts_saar.total, are stored as plain integer units (scale 1)."
        ),
        "geographies": DISPLAY,
    }
    meta_path = OUTPUT_DIR / "meta.json"
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    print(f"  wrote {meta_path.name}")

    # --- summary ---------------------------------------------------------
    print("\n=== summary ===")
    total_kb = sum(p.stat().st_size for p in written) / 1024
    print(f"  {len(written)} geography files + meta.json, {total_kb:.1f} KB total")
    for pid in sorted(spans):
        lo, hi = spans[pid]
        print(f"  {pid}: {lo} .. {hi}")


if __name__ == "__main__":
    main()
