"""
Retrofit Costs POC — prices ERS retrofit records against REMDB.

Methodology: docs/RETROFIT_COSTS.md. This is the POC's permanent home (it
previously lived only in a session scratchpad and was lost between sessions —
see that doc's Files section / 2026-07-31 changelog entry for this move).

Pipeline:
  1. Parse retrofits/USCosts/REMDB_2024.12.23.xlsx "Machine Read" sheet into a
     {(component, class): row} price-regression table, plus two self-derived
     rows REMDB itself never fit (Oil Furnace, Electric Boiler — see
     SELF_DERIVED_REMDB_ROWS below).
  2. Load C:\\ERS\\web\\ers_web_<PROVINCE>.parquet (ers_web_pipeline.py output)
     and left-join retrofits/data/<PROVINCE>_extra_fields.parquet (raw fields
     BASE_MAPPING doesn't carry — see retrofit_cost_extract_fields.py).
  3. Derive geometric area proxies, window/ASHP classification, and the BAU
     heating baseline (see classify_bau_heating), then price each measure's
     *incremental* cost (extra over business-as-usual) at REMDB's Low/Mid/High
     quantile coefficients.
  4. Write retrofits/data/<PROVINCE>_priced.json for the review pages.

Run: python Python/retrofit_cost_estimate.py
"""

import json
import math
import os
import zipfile
import xml.etree.ElementTree as ET

import numpy as np
import openpyxl
import pandas as pd

# All 12 provinces + 2 territories are extracted and priced (2026-07-31).
# Re-running all of them here adds the payback field.
PROVINCES_TO_RUN = ['PE', 'ON', 'QC', 'AB', 'BC', 'MB', 'NB', 'NF', 'NS', 'NT', 'NU', 'SK']

REMDB_XLSX = os.path.join("retrofits", "USCosts", "REMDB_2024.12.23.xlsx")
SUPPORT_XLSX = "Support.xlsx"
UTILITY_RATES_JSON = "utility_rates_reference.json"

# retrofit province code -> utility_rates_reference.json code (mirrors
# precompute_province_stats.py's PROV_ALIAS)
RATE_PROV_ALIAS = {'NF': 'NL'}

# Screening-grade national fallbacks, used ONLY if utility_rates_reference.json
# lacks that fuel for a province (currently true for oil/propane/wood
# everywhere locally — add_oil_propane_rates.py needs a manual NRCan download
# that wasn't available this session). Real per-province data always wins
# when present. FLAGGED — see docs/RETROFIT_COSTS.md "Utility rates".
FALLBACK_OIL_CAD_PER_L = 2.00       # cross-checked: GlobalPetrolPrices 2026-07-27 ($2.11/L)
                                     # vs StatCan-linked Halifax NS 2026-06 ($1.956/L)
FALLBACK_PROPANE_CAD_PER_L = 1.10   # GlobalPetrolPrices LPG 2026-07-06 ($1.26/L, pump/auto-propane
                                     # price used as a residential-heating proxy, same convention
                                     # add_oil_propane_rates.py uses); rounded down toward NRCan's
                                     # own long-run average (~$1.03/L 2016-2026) — weaker source, wider band.
FALLBACK_WOOD_CAD_PER_KWH = 0.0600  # matches add_oil_propane_rates.py's own WOOD_CAD_PER_KWH
                                     # (Canadian Biomass Magazine, single flat national estimate)

KWH_PER_M3_GAS = 10.3611
KWH_PER_L_OIL = 10.7778
KWH_PER_L_PROPANE = 7.0917


def load_utility_rates():
    if not os.path.exists(UTILITY_RATES_JSON):
        return {}
    with open(UTILITY_RATES_JSON, encoding='utf-8') as f:
        return json.load(f)['provinces']


def price_vec_for(province, rates):
    """{elec,gas,oil,propane,wood} $/unit + a 'flags' list of what's a
    screening fallback vs real per-province data, or None if electricity
    (the one fuel every priced ASHP home has on the post side) is missing."""
    code = RATE_PROV_ALIAS.get(province, province)
    p = rates.get(code)
    if not p or 'electricity' not in p:
        return None
    flags = []
    elec = p['electricity']
    if elec.get('confidence') in ('low', 'unverified'):
        flags.append(f"electricity:{elec.get('confidence')}")
    gas = p.get('natural_gas')
    if gas and gas.get('confidence') in ('low',):
        flags.append('gas:low_confidence')
    if gas:
        flags.append('gas:source_frozen_2024-10')  # see docs/RETROFIT_COSTS.md — every province identical
    oil = p.get('heating_oil')
    if not oil:
        flags.append('oil:national_screening_fallback')
    propane = p.get('propane')
    if not propane:
        flags.append('propane:national_screening_fallback')
    wood = p.get('heating_wood')
    if not wood:
        flags.append('wood:national_screening_fallback')
    return {
        'elec': elec['cents_per_kwh'] / 100,
        'gas': gas['dollars_per_m3'] if gas else 0.0,
        'oil': oil['cad_per_litre'] if oil else FALLBACK_OIL_CAD_PER_L,
        'propane': propane['cad_per_litre'] if propane else FALLBACK_PROPANE_CAD_PER_L,
        'wood': wood['cad_per_kwh'] if wood else FALLBACK_WOOD_CAD_PER_KWH,
        'flags': flags,
    }


def annual_dollar_savings(pv, pre_elec, post_elec, pre_gas, post_gas,
                           pre_oil, post_oil, pre_prop, post_prop, pre_wood, post_wood):
    """Annual $ saved = pre bill - post bill, volumetric energy only (mirrors
    precompute_province_stats.py's add_cost_columns / this pipeline's own
    'today's rates, not a historical bill' convention)."""
    def bill(e, g, o, pp, w):
        e = e or 0; g = g or 0; o = o or 0; pp = pp or 0; w = w or 0
        return (e * pv['elec']
                + g / KWH_PER_M3_GAS * pv['gas']
                + o / KWH_PER_L_OIL * pv['oil']
                + pp / KWH_PER_L_PROPANE * pv['propane']
                + w * pv['wood'])
    pre_bill = bill(pre_elec, pre_gas, pre_oil, pre_prop, pre_wood)
    post_bill = bill(post_elec, post_gas, post_oil, post_prop, post_wood)
    return pre_bill - post_bill


def ers_web_parquet(province):
    return rf"C:\ERS\web\ers_web_{province}.parquet"


def extra_fields_parquet(province):
    return os.path.join("retrofits", "data", f"{province}_extra_fields.parquet")


def out_json(province):
    return os.path.join("retrofits", "data", f"{province}_priced.json")

RECT_ASPECT_RATIO = 2 / 3          # short:long side ratio, stated assumption — see docs/RETROFIT_COSTS.md
STOREY_HEIGHT_M = 2.44             # 8 ft
FOUNDATION_INSUL_HEIGHT_M = 2.0    # interior-coverage assumption, not full wall height
WINDOW_AREA_M2 = 1.4               # average window unit size, assumed
BTU_PER_KW = 3412.14
M2_PER_SQFT = 0.092903

BANDS = ['low', 'mid', 'high']


# =============================================================================
# 1. REMDB price table
# =============================================================================

def load_remdb():
    wb = openpyxl.load_workbook(REMDB_XLSX, read_only=True, data_only=True)
    ws = wb['Machine Read']
    rows = list(ws.iter_rows(values_only=True))
    table = {}
    for r in rows[2:]:
        if not r[0]:
            continue
        name, cls = r[0], r[1]
        row = {
            'coef1': r[4:7], 'metric1': r[7], 'lb1': r[9], 'ub1': r[10],
            'coef2': r[11:14], 'metric2': r[14], 'lb2': r[16], 'ub2': r[17],
            'intercept': r[18:21],
            'mult': r[21:23], 'adder': r[23:25],
            'self_derived': False,
        }
        table[(name, cls)] = row
    return table


# REMDB's official "Furnace Analysis" / "Boiler Analysis" sheets never fit a
# regression for an Oil Furnace or an Electric Boiler class (the raw-data
# sheets have real line items for both — HVACdirect/RSMeans oil furnace
# prices, Viessmann/Argo electric-boiler prices — but REMDB's own quantile
# regression was only run on Gas Furnace / Gas+Oil Boiler / Electric
# Baseboard). Since ~80% of PEI's pre-ASHP homes were oil-heated, "assume gas
# furnace for everyone" was throwing away the one baseline that matters most.
# These two rows are *our* regression, fit the same simple way, from the raw
# rows Simon flagged directly out of the workbooks:
#   Oil Furnace  — Non-Envelope Measures 7-18-24.xlsx, "Furnace Data": 6
#     RSMeans "Installed Cost (O&P)" line items (already fully-loaded retail
#     price, so no REMDB installation adder is layered on top), 56,000-
#     200,000 BTU/hr. $/BTU ratios' 10th/50th/90th percentile -> Low/Mid/High.
#   Electric Boiler — same workbook, "Boiler Data": 10 Viessmann/Argo
#     material-price line items, 13,652-54,600 BTU/hr (material price only,
#     so REMDB's own Boiler/Oil retrofit installation adder — the nearest
#     fitted boiler class — is added on top; borrowed, not measured).
# Both are flagged self_derived=True and carry a BAUHeatingSource of
# 'like_for_like' in the output, same as any REMDB-fitted match — they are a
# real price for the actual pre-retrofit equipment, just not REMDB's own fit.
SELF_DERIVED_REMDB_ROWS = {
    ('Furnaces', 'Oil Furnace'): {
        'coef1': (0.031138, 0.040108, 0.064289), 'metric1': 'Heating Capacity', 'lb1': 56000, 'ub1': 200000,
        'coef2': (0, 0, 0), 'metric2': 'N/A', 'lb2': 0, 'ub2': 0,
        'intercept': (0, 0, 0),
        'mult': (1, 1), 'adder': (0, 0),   # ratio already IS installed $/BTU — no separate adder
        'self_derived': True,
        'source': "6 RSMeans installed-cost oil furnace line items, 56,000-200,000 BTU/hr "
                   "(Non-Envelope Measures 7-18-24.xlsx, Furnace Data)",
    },
    ('Boiler', 'Electric'): {
        'coef1': (0.053240, 0.065918, 0.125334), 'metric1': 'Heating Capacity', 'lb1': 13652, 'ub1': 54600,
        'coef2': (0, 0, 0), 'metric2': 'N/A', 'lb2': 0, 'ub2': 0,
        'intercept': (0, 0, 0),
        # borrowed: REMDB's own Boiler/Oil retrofit installation adder (nearest fitted boiler class)
        'mult': (1, 1), 'adder': (3450.345405, 4040.345405),
        'self_derived': True,
        'source': "10 Viessmann/Argo electric-boiler material-price line items, 13,652-54,600 BTU/hr "
                   "(Non-Envelope Measures 7-18-24.xlsx, Boiler Data); installation adder borrowed "
                   "from REMDB's fitted Boiler/Oil class (nearest boiler analog)",
    },
}


def clamp(value, lb, ub):
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return value
    if lb == 0 and ub == 0:
        return value
    return min(max(value, lb), ub)


def price_component(remdb, component, cls, metric1_val, metric2_val=None, band_idx=None):
    """installed_cost per REMDB's own mechanics (docs/RETROFIT_COSTS.md #REMDB-pricing-mechanics).
    Returns [low, mid, high] unless band_idx given (then a single float)."""
    row = remdb.get((component, cls))
    if row is None:
        return None
    m1 = clamp(metric1_val, row['lb1'], row['ub1']) if metric1_val is not None else 0
    m2 = clamp(metric2_val, row['lb2'], row['ub2']) if metric2_val is not None else 0
    out = []
    for i in range(3):
        material = row['coef1'][i] * (m1 or 0) + row['coef2'][i] * (m2 or 0) + row['intercept'][i]
        # New Construction / Retrofit are the only two multiplier/adder columns REMDB
        # carries (not per-band) — always use Retrofit (index 1) per docs' scope.
        mult_retrofit = row['mult'][1]
        adder_retrofit = row['adder'][1]
        if mult_retrofit != 1:
            installed = material * mult_retrofit
        else:
            installed = material + adder_retrofit
        out.append(installed)
    if band_idx is not None:
        return out[band_idx]
    return out


def out_of_bounds(remdb, component, cls, metric1_val, metric2_val=None):
    row = remdb.get((component, cls))
    if row is None:
        return False
    oob = False
    if metric1_val is not None and not (isinstance(metric1_val, float) and math.isnan(metric1_val)):
        if not (row['lb1'] == 0 and row['ub1'] == 0):
            oob = oob or not (row['lb1'] <= metric1_val <= row['ub1'])
    if metric2_val is not None and not (isinstance(metric2_val, float) and math.isnan(metric2_val)):
        if not (row['lb2'] == 0 and row['ub2'] == 0):
            oob = oob or not (row['lb2'] <= metric2_val <= row['ub2'])
    return oob


# =============================================================================
# 2. Window frame decode (Support.xlsx Frame sheet) — same table/digit
#    build_window_lookup.py uses for the Retrofit Explorer.
# =============================================================================

def load_frame_table():
    NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    with zipfile.ZipFile(SUPPORT_XLSX) as z:
        strings_root = ET.fromstring(z.read("xl/sharedStrings.xml"))
        strings = ["".join(t.text or "" for t in si.findall(".//m:t", NS))
                   for si in strings_root.findall("m:si", NS)]
        wb = ET.fromstring(z.read("xl/workbook.xml"))
        rels = ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
        rid_to_target = {rel.get("Id"): rel.get("Target") for rel in
                          rels.findall("{http://schemas.openxmlformats.org/package/2006/relationships}Relationship")}
        sheet_path = None
        for sheet in wb.findall(".//m:sheets/m:sheet", NS):
            if sheet.get("name") == "Frame":
                rid = sheet.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id")
                sheet_path = "xl/" + rid_to_target[rid].lstrip("/")
        root = ET.fromstring(z.read(sheet_path))
        table = {}
        for row in root.findall(".//m:sheetData/m:row", NS)[1:]:
            cells = []
            for c in row.findall("m:c", NS):
                t = c.get("t")
                v = c.find("m:v", NS)
                val = v.text if v is not None else ""
                if t == "s" and val != "":
                    val = strings[int(val)]
                cells.append(val)
            if len(cells) >= 2 and cells[0] != "":
                table[str(cells[0]).strip()] = cells[1].strip()
    return table


def window_class(window_code, frame_table):
    """digit 6 (rightmost) of the 6-digit HOT2000 code -> REMDB Vinyl/Metal."""
    if window_code is None or (isinstance(window_code, float) and math.isnan(window_code)):
        return None, None
    s = str(window_code).strip()
    if s.endswith('.0'):
        s = s[:-2]
    s = s.zfill(6)
    if len(s) != 6 or not s.isdigit():
        return 'Vinyl', 'assumed_default'
    frame = frame_table.get(s[5])
    if frame in ('Vinyl', 'Reinforced Vinyl'):
        return 'Vinyl', 'reported'
    if frame in ('Aluminum', 'Aluminum Thermal Break'):
        return 'Metal', 'reported'
    return 'Vinyl', 'assumed_default'   # Wood / Aluminum Clad Wood / undecodable — no REMDB Wood class


def pane_count(window_code):
    if window_code is None or (isinstance(window_code, float) and math.isnan(window_code)):
        return None
    s = str(window_code).strip()
    if s.endswith('.0'):
        s = s[:-2]
    s = s.zfill(6)
    if len(s) != 6 or not s.isdigit():
        return None
    d = int(s[0])
    return {1: 'single', 2: 'double', 3: 'triple'}.get(d)


# Trimmed-median Vinyl/Metal $/window prices from REMDB's raw Windows Data
# sheet (docs/RETROFIT_COSTS.md "Windows — standard vs efficient"), at the
# default 1.4 m^2 (15.1 sqft) window size. {frame: {class: {pane: $}}}
WINDOW_PRICES = {
    'Vinyl': {
        'standard_double': 352, 'efficient_double': 801, 'efficient_triple': 1678,
    },
    'Metal': {
        # Metal (n=22, no separate std/eff split available) — use REMDB's flat
        # Window/Metal intercepts (mid=206.57/sqft) at the default window size,
        # for both standard and efficient (no glazing-class split exists for Metal).
        'standard_double': round(112.075 * 15.1), 'efficient_double': round(206.565 * 15.1),
        'efficient_triple': round(401.5 * 15.1),
    },
}


# =============================================================================
# 3. BAU heating classification (the fix in this run — see chat context)
# =============================================================================

def classify_bau_heating(pre_type, pre_fuel, pre_afue):
    """Returns ((component, class), source) where source is 'like_for_like'
    (a REMDB row — official or self-derived — matches the pre-audit
    equipment) or 'assumed_default' (falls back to Gas Furnace because
    REMDB has no row for that fuel/type combination at all)."""
    type_l = (str(pre_type) if pre_type is not None else '').lower()
    fuel = (str(pre_fuel) if pre_fuel is not None else '').strip()

    is_boiler = 'boiler' in type_l
    is_baseboard = ('baseboard' in type_l) or ('hydronic' in type_l) or ('plenum' in type_l)

    if fuel == 'Natural Gas':
        if is_boiler:
            afue = pre_afue if (pre_afue is not None and not (isinstance(pre_afue, float) and math.isnan(pre_afue))) else 0.83
            cls = 'Gas (Condensing)' if afue >= 0.90 else 'Gas (Non-Condensing)'
            return ('Boiler', cls), 'like_for_like'
        return ('Furnaces', 'Gas Furnace'), 'like_for_like'

    if fuel == 'Oil':
        if is_boiler:
            return ('Boiler', 'Oil'), 'like_for_like'
        return ('Furnaces', 'Oil Furnace'), 'like_for_like'

    if fuel == 'Electricity':
        if is_baseboard:
            return ('Electric Baseboard', None), 'like_for_like'
        if is_boiler:
            return ('Boiler', 'Electric'), 'like_for_like'
        # electric furnace / electric forced-air heater — no REMDB row for this
        return ('Furnaces', 'Gas Furnace'), 'assumed_default'

    # Propane, Wood (mixed/hard/pellets), unknown/missing — no REMDB row
    return ('Furnaces', 'Gas Furnace'), 'assumed_default'


def price_bau_heating(remdb, component, cls, pre_heatloss_kw, pre_afue):
    btu = (pre_heatloss_kw or 0) * BTU_PER_KW
    if component == 'Electric Baseboard':
        return price_component(remdb, 'Electric Baseboard', None, btu)
    afue = pre_afue if (pre_afue is not None and not (isinstance(pre_afue, float) and math.isnan(pre_afue))) else \
        (0.83 if component == 'Boiler' else 0.80)
    return price_component(remdb, component, cls, btu, afue)


# =============================================================================
# 4. ASHP classification + cooling credit
# =============================================================================

def classify_ashp(hp_equip_type, num_heads, fallback_class):
    t = (str(hp_equip_type) if hp_equip_type is not None else '').strip()
    if t == 'Central split system':
        return 'Centrally ducted', 'reported'
    if 'Ductless' in t:
        heads = pd.to_numeric(num_heads, errors='coerce')
        if pd.notna(heads) and heads >= 2:
            return 'Non-ducted, multi-zone', 'reported'
        return 'Non-ducted, single-zone', 'reported'
    # No HPEquipType at all (pre-2025 majority) — fall back to this province's
    # own observed dominant class among its reported records (see
    # province_ashp_fallback below), not a hardcoded national constant.
    return fallback_class, 'assumed_default'


def province_ashp_fallback(df):
    """This province's own most-common REPORTED ASHP class, used as the
    fallback for the pre-2025 majority with no HPEquipType at all. Was
    hardcoded to PEI's ~15:1 ductless dominance before this ran on other
    provinces — provinces with more existing forced-air furnace stock
    (ON, QC) plausibly skew more centrally-ducted, so this is now computed
    per province instead of assumed."""
    hp = df[df['HeatPump_Addition'] == True]
    t = hp['Post_HPEquipType'].astype(str)
    heads = pd.to_numeric(hp['Post_NUMBEROFHEADS'], errors='coerce')
    reported = pd.Series(index=hp.index, dtype='object')
    reported[t == 'Central split system'] = 'Centrally ducted'
    ductless = t.str.contains('Ductless', na=False)
    reported[ductless & (heads >= 2)] = 'Non-ducted, multi-zone'
    reported[ductless & ~(heads >= 2)] = 'Non-ducted, single-zone'
    counts = reported.value_counts()
    if counts.empty:
        return 'Non-ducted, single-zone'   # no reported data at all — PEI-era default
    return counts.idxmax()


def ac_credit(remdb, accentestar, acwindnum, spacecoolenergy, descoolloss, ashp_tons, ashp_seer1, ducted):
    """Which A/C (if any) the home already had, credited at the ASHP's own
    cooling capacity/SEER1 (docs/RETROFIT_COSTS.md 'ASHP — vs a furnace/boiler
    plus a central A/C')."""
    had_central = str(accentestar).strip() not in ('', 'nan', 'None', '0', '0.0')
    win_n = pd.to_numeric(acwindnum, errors='coerce')
    had_window = pd.notna(win_n) and win_n > 0
    energy = pd.to_numeric(spacecoolenergy, errors='coerce')
    loss = pd.to_numeric(descoolloss, errors='coerce')
    had_any_cooling = had_central or had_window or (pd.notna(energy) and energy > 0) or (pd.notna(loss) and loss > 0)

    if had_central or not had_any_cooling:
        # had central, OR had none (still credit central — the canonical furnace+A/C pair)
        return price_component(remdb, 'Air Conditioner', 'Centrally ducted', ashp_tons, ashp_seer1)
    # had window units, or ASHP itself is ductless
    ceer = ashp_seer1 * 0.85 if ashp_seer1 else None   # rough SEER1->CEER; small line item, not load-bearing
    return price_component(remdb, 'Air Conditioner', 'Room AC (window or through-wall)', ashp_tons, ceer)


# =============================================================================
# 5. Geometry proxies
# =============================================================================

def rect_perimeter(area_m2):
    if area_m2 is None or (isinstance(area_m2, float) and math.isnan(area_m2)) or area_m2 <= 0:
        return None
    long_side = math.sqrt(area_m2 / RECT_ASPECT_RATIO)
    short_side = RECT_ASPECT_RATIO * long_side
    return 2 * (long_side + short_side)


def m2_to_sqft(m2):
    return None if m2 is None else m2 / M2_PER_SQFT


# =============================================================================
# 6. Main
# =============================================================================

def run_province(province, remdb, frame_table, rates):
    print(f"\n=== {province} ===")
    print("Loading ERS data...")
    df = pd.read_parquet(ers_web_parquet(province))
    extra = pd.read_parquet(extra_fields_parquet(province))
    df = df.merge(extra, on='HOUSEID', how='left')
    for c in ['Post_FOOTPRINT', 'Post_NUMWINDOWS', 'Post_NUMDOORS', 'Post_BASEMENTFLOORAR',
              'Post_NUMBEROFHEADS', 'Pre_ACWINDNUM', 'Pre_ERSSPACECOOLENERGY', 'Pre_ERSDesCoolLoss',
              'Pre_RoofInsulation', 'Post_RoofInsulation', 'Pre_WallInsulation', 'Post_WallInsulation',
              'Pre_FoundationInsulation', 'Post_FoundationInsulation', 'FloorArea',
              'Pre_AirLeakage', 'Post_AirLeakage', 'Pre_SolarPV', 'Post_SolarPV',
              'Pre_HeatLoss', 'Post_HeatLoss', 'Pre_HeatAFUE', 'Post_HeatAFUE',
              'Post_HPCoolingCapacityTons', 'Post_HPSEER1Est',
              'Pre_Electricity', 'Post_Electricity', 'Pre_NaturalGas', 'Post_NaturalGas',
              'Pre_Oil', 'Post_Oil', 'Pre_Propane', 'Post_Propane', 'Pre_Wood', 'Post_Wood']:
        df[c] = pd.to_numeric(df[c], errors='coerce')

    pv = price_vec_for(province, rates)
    if pv:
        print(f"Utility rates for {province}: elec ${pv['elec']:.3f}/kWh, gas ${pv['gas']:.3f}/m3 "
              f"— flags: {pv['flags'] or 'none'}")
    else:
        print(f"No utility rates for {province} — payback will not be computed.")

    # Multi-dwelling exclusion (docs/RETROFIT_COSTS.md "Measures explicitly NOT priced")
    multi = df['BldgType'].astype(str).str.contains(
        'Apartment|Duplex|Triplex', case=False, na=False)
    df = df[~multi].copy()
    print(f"{len(df)} single-dwelling paired records ({multi.sum()} multi-dwelling excluded)")

    ashp_fallback = province_ashp_fallback(df)
    print(f"ASHP class fallback for {province}: '{ashp_fallback}' (this province's own most-common reported class)")

    records = []
    n_bau_reported = n_bau_assumed = 0

    for row in df.itertuples():
        rec = {'id': row.HOUSEID, 'fsa': row.FSA, 'measures': {}}
        priced_any = False

        # ---- Roof / attic insulation ----
        if row.Roof_Insulation_Upgrade and pd.notna(row.Post_FOOTPRINT) and row.Post_FOOTPRINT > 0:
            roof_area_sqft = m2_to_sqft(row.Post_FOOTPRINT)
            d_rsi = (row.Post_RoofInsulation or 0) - (row.Pre_RoofInsulation or 0) \
                if pd.notna(row.Post_RoofInsulation) and pd.notna(row.Pre_RoofInsulation) else None
            if d_rsi and d_rsi > 0:
                r_added = d_rsi * 5.678
                price = [price_component(remdb, 'Unfinished Attic (Ceiling)', 'Batt', r_added, band_idx=i) * roof_area_sqft
                         for i in range(3)]
                rec['measures']['Roof'] = price
                priced_any = True

        # ---- Wall insulation ----
        if row.Wall_Insulation_Upgrade and pd.notna(row.Post_FOOTPRINT) and row.Post_FOOTPRINT > 0 \
                and pd.notna(row.Storeys):
            storeys_n = {'One storey': 1, 'Two storeys': 2, 'Split level': 1.5,
                         'One and a half storeys': 1.5, 'Three storeys': 3}.get(str(row.Storeys), 1)
            perim = rect_perimeter(row.Post_FOOTPRINT)
            wall_area_m2 = (perim or 0) * storeys_n * STOREY_HEIGHT_M
            wall_area_sqft = m2_to_sqft(wall_area_m2)
            d_rsi = (row.Post_WallInsulation or 0) - (row.Pre_WallInsulation or 0) \
                if pd.notna(row.Post_WallInsulation) and pd.notna(row.Pre_WallInsulation) else None
            if d_rsi and d_rsi > 0 and wall_area_sqft:
                r_added = d_rsi * 5.678
                price = [price_component(remdb, 'Wood/Steel Stud', 'Batt', r_added, band_idx=i) * wall_area_sqft
                         for i in range(3)]
                rec['measures']['Wall'] = price
                priced_any = True

        # ---- Foundation wall insulation ----
        if row.Foundation_Insulation_Upgrade and str(row.FoundationType).find('B') >= 0 \
                and pd.notna(row.Post_BASEMENTFLOORAR) and row.Post_BASEMENTFLOORAR > 0:
            perim = rect_perimeter(row.Post_BASEMENTFLOORAR)
            fnd_area_m2 = (perim or 0) * FOUNDATION_INSUL_HEIGHT_M
            fnd_area_sqft = m2_to_sqft(fnd_area_m2)
            d_rsi = (row.Post_FoundationInsulation or 0) - (row.Pre_FoundationInsulation or 0) \
                if pd.notna(row.Post_FoundationInsulation) and pd.notna(row.Pre_FoundationInsulation) else None
            if d_rsi and d_rsi > 0 and fnd_area_sqft:
                r_added = d_rsi * 5.678
                price = [price_component(remdb, 'Unfinished Basement (Wall)', 'Batt', r_added, band_idx=i) * fnd_area_sqft
                         for i in range(3)]
                rec['measures']['Foundation'] = price
                priced_any = True

        # ---- Windows (incremental: efficient(post pane) - standard(pre pane)) ----
        wc_pre_raw = str(row.Pre_WindowCode).strip() if pd.notna(row.Pre_WindowCode) else ''
        wc_post_raw = str(row.Post_WindowCode).strip() if pd.notna(row.Post_WindowCode) else ''

        def norm_code(s):
            return s[:-2] if s.endswith('.0') else s

        if row.Windows_Change and norm_code(wc_pre_raw) != norm_code(wc_post_raw) \
                and pd.notna(row.Post_NUMWINDOWS) and row.Post_NUMWINDOWS > 0:
            cls, wsrc = window_class(row.Post_WindowCode, frame_table)
            pre_pane = pane_count(row.Pre_WindowCode)
            post_pane = pane_count(row.Post_WindowCode)
            if cls and pre_pane and post_pane:
                prices = WINDOW_PRICES.get(cls, WINDOW_PRICES['Vinyl'])
                std_pre = prices['standard_double']       # only double-pane standard priced (rare single-pane BAU)
                eff_post = prices['efficient_triple'] if post_pane == 'triple' else prices['efficient_double']
                incr = max(0, eff_post - std_pre)
                total = incr * row.Post_NUMWINDOWS
                rec['measures']['Window'] = [total, total, total]   # single-point REMDB raw-sheet price, no L/M/H band
                rec['window_class'] = cls
                rec['window_class_source'] = wsrc
                priced_any = True

        # ---- Air sealing ----
        if pd.notna(row.Pre_AirLeakage) and pd.notna(row.Post_AirLeakage) and row.Pre_AirLeakage > 0 \
                and pd.notna(row.FloorArea) and row.FloorArea > 0:
            reduction = (row.Pre_AirLeakage - row.Post_AirLeakage) / row.Pre_AirLeakage
            if reduction > 0.03:
                cls = '>40% Reduction' if reduction > 0.40 else '<40% Reduction'
                floor_sqft = m2_to_sqft(row.FloorArea)
                # Air Sealing's metric is "Leakage Reduction, Percent" (0-1 scale,
                # REMDB's own bounds are 0.03-0.92) applied to whole-house floor area.
                price = [price_component(remdb, 'Air Sealing', cls, reduction, band_idx=i) * floor_sqft
                         for i in range(3)]
                rec['measures']['AirSeal'] = price
                priced_any = True

        # ---- Solar PV ----
        if pd.notna(row.Post_SolarPV) and pd.notna(row.Pre_SolarPV):
            add_kw = (row.Post_SolarPV or 0) - (row.Pre_SolarPV or 0)
            if 0.1 < add_kw <= 20:   # >20kW is almost certainly a unit/data artifact, not a residential system
                watts = add_kw * 1000
                # REMDB's Solar PV row is priced in $/Watt, not a flat $ total —
                # multiply the regression's per-watt output by system size.
                price = [price_component(remdb, 'Solar PV', None, watts, band_idx=i) * watts for i in range(3)]
                rec['measures']['PV'] = price
                priced_any = True

        # ---- HRV/ERV addition ----
        pre_vent = str(row.Pre_VentType) if pd.notna(row.Pre_VentType) else ''
        post_vent = str(row.Post_VentType) if pd.notna(row.Post_VentType) else ''
        if 'HRV' not in pre_vent and 'ERV' not in pre_vent and ('HRV' in post_vent or 'ERV' in post_vent):
            # No SRE/CFM survive the web pipeline — price at REMDB's mid-bound
            # midpoint metrics as a flat placeholder (flagged, not a per-home fit).
            sre_mid, cfm_mid = 0.70, 150
            price = [price_component(remdb, 'Mechanical Ventilation', 'ERV/HRV', sre_mid, cfm_mid, band_idx=i)
                     for i in range(3)]
            rec['measures']['HRV'] = price
            rec['hrv_source'] = 'flat_placeholder_metrics'
            priced_any = True

        # ---- ASHP (incremental) ----
        if row.HeatPump_Addition and pd.notna(row.Post_HPCoolingCapacityTons) and pd.notna(row.Post_HPSEER1Est):
            ashp_cls, ashp_src = classify_ashp(row.Post_HPEquipType, row.Post_NUMBEROFHEADS, ashp_fallback)
            ducted = (ashp_cls == 'Centrally ducted')
            ashp_price = price_component(remdb, 'Air Source Heat Pump', ashp_cls,
                                          row.Post_HPCoolingCapacityTons, row.Post_HPSEER1Est)

            bau_component, bau_source = classify_bau_heating(row.Pre_HeatType, row.Pre_HeatFuel, row.Pre_HeatAFUE)
            bau_heat_price = price_bau_heating(remdb, bau_component[0], bau_component[1], row.Pre_HeatLoss, row.Pre_HeatAFUE)

            bau_cool_price = ac_credit(remdb, row.Pre_ACCENTESTAR, row.Pre_ACWINDNUM,
                                        row.Pre_ERSSPACECOOLENERGY, row.Pre_ERSDesCoolLoss,
                                        row.Post_HPCoolingCapacityTons, row.Post_HPSEER1Est, ducted)

            if ashp_price and bau_heat_price and bau_cool_price:
                incremental = [ashp_price[i] - bau_heat_price[i] - bau_cool_price[i] for i in range(3)]
                rec['measures']['ASHP'] = incremental
                rec['ashp_class'] = ashp_cls
                rec['ashp_class_source'] = ashp_src
                rec['bau_heating'] = f"{bau_component[0]}" + (f" / {bau_component[1]}" if bau_component[1] else "")
                rec['bau_heating_source'] = bau_source
                rec['bau_self_derived'] = remdb.get(bau_component, {}).get('self_derived', False)
                priced_any = True
                if bau_source == 'like_for_like':
                    n_bau_reported += 1
                else:
                    n_bau_assumed += 1

        if priced_any:
            total = [sum(v[i] for v in rec['measures'].values()) for i in range(3)]
            rec['total'] = total

            if pv:
                saved = annual_dollar_savings(
                    pv, row.Pre_Electricity, row.Post_Electricity,
                    row.Pre_NaturalGas, row.Post_NaturalGas,
                    row.Pre_Oil, row.Post_Oil, row.Pre_Propane, row.Post_Propane,
                    row.Pre_Wood, row.Post_Wood)
                rec['annual_dollar_saved'] = round(saved, 2)
                if saved > 1:   # avoid a near-zero denominator producing a meaningless huge/negative payback
                    rec['payback_years'] = round(total[1] / saved, 1)
                fuel_flags = list(pv['flags'])
                if (row.Pre_Oil or 0) > (row.Pre_Electricity or 0) * 0.1:  # oil was a meaningful pre-fuel
                    fuel_flags.append('home_pre_fuel_oil_screening_rate')
                if (row.Pre_Propane or 0) > 0:
                    fuel_flags.append('home_pre_fuel_propane_screening_rate')
                if (row.Pre_Wood or 0) > 0:
                    fuel_flags.append('home_pre_fuel_wood_screening_rate')
                rec['payback_flags'] = fuel_flags

            records.append(rec)

    print(f"{len(records)} / {len(df)} priced ({len(records) / len(df):.0%})")
    print(f"BAU heating: {n_bau_reported} like-for-like, {n_bau_assumed} assumed-default gas furnace fallback")

    path = out_json(province)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    out = {
        'generated': pd.Timestamp.now().strftime('%Y-%m-%d %H:%M'),
        'province': province,
        'n_paired': len(df),
        'n_priced': len(records),
        'ashp_class_fallback': ashp_fallback,
        'bau_heating_reported': n_bau_reported,
        'bau_heating_assumed': n_bau_assumed,
        'homes': records,
    }
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(out, f, default=lambda x: None if isinstance(x, float) and math.isnan(x) else x)
    print(f"wrote {path}")


def main():
    print("Loading REMDB...")
    remdb = load_remdb()
    remdb.update(SELF_DERIVED_REMDB_ROWS)
    frame_table = load_frame_table()
    rates = load_utility_rates()

    for province in PROVINCES_TO_RUN:
        run_province(province, remdb, frame_table, rates)


if __name__ == '__main__':
    main()
