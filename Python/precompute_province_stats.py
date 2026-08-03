"""
precompute_province_stats.py

Generates one JSON file per province containing precomputed chart data for
the "province-wide" (no FSA selected) view of Retrofit Explorer.

Why this exists: the province-wide view only allows filtering by house type
(FSA + fuel + depth filters are FSA-view-only — see retrofits.html). Because
the filter surface is small and fixed (~6 house types + "All types"), we can
precompute every chart's binned/aggregated data exactly in Python, once,
instead of shipping 600k+ raw rows to the browser for client-side aggregation.

INPUT:  the per-province parquet written by ers_web_pipeline.py Step 3
        (e.g. C:\\ERS\\web\\ers_web_ON.parquet) — BEFORE dictionary encoding,
        so columns hold their original human-readable strings.

OUTPUT: <OUTPUT_DIR>/province_json/<PROVINCE>.json
        Shape:
        {
          "province": "ON",
          "total_rows": 600123,
          "by_type": {
            "All types": { ...precomputed chart payload... },
            "Single Detached": { ... },
            ...
          }
        }

IMPORTANT: every bin width / threshold / formula below is copied verbatim
from the matching function in retrofits.html. If you change a bin width or
threshold in one place, you MUST change it in the other, or the precomputed
charts will silently stop matching what the FSA-level (raw-row) charts show
for the same province. Each section below is tagged with the JS function
name it mirrors, to make that link explicit.
"""

import os
import glob
import json
import math
from pathlib import Path

import pandas as pd
import numpy as np

# =============================================================================
# CONFIG
# =============================================================================

OUTPUT_DIR = r"C:\ERS\web"                                   # same as pipeline OUTPUT_DIR
PROVINCE_JSON_DIR = os.path.join(OUTPUT_DIR, "province_json")

# Audit-composition sidecar (build_fsa_audit_totals.py). Its `by_province` block
# supplies the fixed left-hand stages of the audit-funnel Sankey for the
# province-wide view. Optional: if missing, the payload's `funnel` is null and
# the front end falls back to matched-pairs-only.
AUDIT_TOTALS_PATH = os.path.join(OUTPUT_DIR, "fsa_audit_totals.json")

# Columns whose raw string values can vary in casing/whitespace across years
# (e.g. 'Single detached' vs 'Single Detached') and must be normalized to one
# canonical display string BEFORE any grouping/aggregation — otherwise the
# same real-world category gets silently split into multiple slices.
# This mirrors what the old ers_web_pipeline.py dictionary-encoding step used
# to do for free via str.strip().str.lower() + buildDecoders() in retrofits.html.
CATEGORICAL_COLS = [
    'FSA', 'BldgType', 'Storeys', 'FoundationType',
    'Pre_HeatFuel', 'Post_HeatFuel', 'Pre_HeatType', 'Post_HeatType',
    'Pre_HPType', 'Post_HPType',
]


def title_case(s):
    """Mirrors norm(t) in retrofits.html: trim + title-case each word."""
    if not isinstance(s, str) or not s.strip():
        return s
    import re
    return re.sub(r'\b\w', lambda m: m.group().upper(), s.strip())


def normalize_categoricals(df):
    """
    Apply the same per-column display-casing rules retrofits.html's
    buildDecoders() used to apply at decode time, so two rows that mean the
    same real-world value ('single detached' / 'Single Detached') collapse
    to one canonical string before we group/aggregate by it.
    """
    df = df.copy()
    for col in CATEGORICAL_COLS:
        if col not in df.columns:
            continue
        if col == 'FSA':
            df[col] = df[col].astype(str).str.strip().str.upper()
        elif col in ('Pre_HeatFuel', 'Post_HeatFuel'):
            df[col] = df[col].astype(str).str.strip().map(title_case)
        elif col == 'Storeys':
            df[col] = df[col].astype(str).str.strip().map(
                lambda s: (s[:1].upper() + s[1:].lower()) if s else s)
        elif col in ('Pre_HPType', 'Post_HPType'):
            df[col] = df[col].astype(str).str.strip().map(
                lambda s: '' if (not isinstance(s, str) or s == '0' or s.lower().startswith('n/a'))
                else title_case(s))
        else:
            df[col] = df[col].astype(str).str.strip().map(title_case)
        # restore actual NaN for empty/placeholder strings so downstream
        # .dropna() / value_counts() behave as before normalization
        df[col] = df[col].replace({'': np.nan, 'Nan': np.nan, 'None': np.nan})
    return df

# Measures shown in the measures bar + spider chart.
# Mirrors the MEASURES array in retrofits.html — keep label/order in sync.
MEASURES = [
    ('Air_Tightness_Upgrade',        'Air sealing'),
    ('Roof_Insulation_Upgrade',      'Roof insulation'),
    ('Foundation_Insulation_Upgrade','Foundation insulation'),
    ('Wall_Insulation_Upgrade',      'Wall insulation'),
    ('HeatPump_Addition',            'Heat pump added'),
    ('Heating_Change',               'Heating system changed'),
    ('Windows_Change',               'Windows changed'),
    ('Floor_Insulation_Upgrade',     'Floor insulation'),
]

# Storey label normalization. Mirrors renderStoreyDonut()'s MAP in retrofits.html.
STOREY_MAP = {
    'split entry / raised basement': 'Split entry',
    'two and a half': '2.5 storeys',
    'three storeys': '3 storeys',
    'two storeys': '2 storeys',
    'one storey': '1 storey',
    'one and a half': '1.5 storeys',
    'split level': 'Split level',
    'split entry/raised base.': 'Split entry',
}

# Envelope components in the annual heat-loss chart. Mirrors
# HL_COMPONENT_FIELDS in assets/retrofits.js — labels included, since they
# ship in the JSON and are drawn verbatim.
HEATLOSS_COMPONENTS = [
    ('HeatLossWindowDoor', 'Windows & doors'),
    ('HeatLossWall',       'Walls'),
    ('HeatLossFoundation', 'Foundation'),
    ('HeatLossRoof',       'Roof'),
    ('HeatLossFloor',      'Exposed floor'),
    ('HeatLossAir',        'Air leakage'),
]

# Fuels shown in the waterfall chart. Mirrors the FUELS array in renderWaterfall().
WATERFALL_FUELS = [
    ('Electricity', 'Electricity'),
    ('NaturalGas',  'Natural Gas'),
    ('Oil',         'Oil'),
    ('Propane',     'Propane'),
    ('Wood',        'Wood'),
]


# =============================================================================
# Small helpers (mirror the JS helpers of the same name in retrofits.html)
# =============================================================================

def num(s):
    """Mirrors num(v) in JS: coerce to float, NaN -> None."""
    return pd.to_numeric(s, errors='coerce')


# =============================================================================
# ENERGY-COST PRICING (mirrors retrofits.html's priceVec/homeCost — keep in sync)
# =============================================================================
# Prices the per-fuel annual energy (kWh) each home used before/after against
# current residential rates, so the page can show "$ saved" beside energy and
# GHG. Rates come from utility_rates_reference.json — one blended
# province-level number per fuel (electricity, gas, heating oil, propane,
# heating wood), covering all 13 provinces/territories. Wood has no
# per-species breakdown in that dataset (a single flat $/kWh), and the
# retrofit rows only carry one combined Wood energy column anyway, so the
# same rate is applied to wood heating of any kind.
#
# IMPORTANT: every constant and formula in this block is duplicated in
# retrofits.html (search "priceVec" / "homeCost" / "fetchPriceVec"). Change
# one, change the other, or the precomputed province $-charts silently stop
# matching the raw-row FSA $-charts for the same province.
#
# Simplifications (footnoted on the page): volumetric energy only (no fixed
# monthly charges — they largely cancel pre-vs-post); one blended $/kWh per
# province (retrofit rows carry annual kWh, not an hourly shape); today's
# rates applied to audits spanning 2004-2025 ("what these homes would save
# now", not a historical bill).

UTILITY_RATES_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "utility_rates_reference.json")

# retrofit province code -> utility_rates_reference.json code
PROV_ALIAS = {'NF': 'NL'}

# Invert the exact fuel->kWh factors ers_web_pipeline.py used to build the
# Pre_/Post_ per-fuel columns, to recover m³/L for volumetric pricing.
KWH_PER_M3_GAS = 10.3611
KWH_PER_L_OIL = 10.7778
KWH_PER_L_PROP = 7.0917

COST_BIN = 250        # $/yr histogram bin width (mirrors BINS.cost in retrofits.html)
COST_CAP = 8000       # clip pre/post annual bills above this, for scale
COST_DELTA_CAP = 6000  # clip per-home savings above this, for scale

_UTILITY_RATES = None


def _load_utility_rates():
    global _UTILITY_RATES
    if _UTILITY_RATES is None:
        with open(UTILITY_RATES_PATH, encoding='utf-8') as f:
            _UTILITY_RATES = json.load(f)
    return _UTILITY_RATES


def price_vec_for(province):
    """{elec,gas,oil,propane,wood} $/unit for a province, or None if unpriced."""
    code = PROV_ALIAS.get(province, province)
    p = _load_utility_rates()['provinces'].get(code)
    if not p:
        return None
    gas = p.get('natural_gas')
    oil = p.get('heating_oil')
    propane = p.get('propane')
    wood = p.get('heating_wood')
    return {
        'elec': p['electricity']['cents_per_kwh'] / 100,
        'gas': gas['dollars_per_m3'] if gas else 0.0,
        'oil': oil['cad_per_litre'] if oil else 0.0,
        'propane': propane['cad_per_litre'] if propane else 0.0,
        'wood': wood['cad_per_kwh'] if wood else 0.0,
    }


def add_cost_columns(df, pv):
    """Attach _CostPre/_CostPost: annual energy $ (volumetric only) per home."""
    def bill(prefix):
        e = num(df.get(f'{prefix}_Electricity')).fillna(0)
        g = num(df.get(f'{prefix}_NaturalGas')).fillna(0)
        o = num(df.get(f'{prefix}_Oil')).fillna(0)
        p = num(df.get(f'{prefix}_Propane')).fillna(0)
        w = num(df.get(f'{prefix}_Wood')).fillna(0)
        return (e * pv['elec']
                + g / KWH_PER_M3_GAS * pv['gas']
                + o / KWH_PER_L_OIL * pv['oil']
                + p / KWH_PER_L_PROP * pv['propane']
                + w * pv['wood'])
    df = df.copy()
    df['_CostPre'] = bill('Pre')
    df['_CostPost'] = bill('Post')
    return df


def median(arr):
    """Mirrors median(arr) in JS: None if empty, else statistical median."""
    arr = np.asarray(arr, dtype=float)
    arr = arr[~np.isnan(arr)]
    if arr.size == 0:
        return None
    return float(np.median(arr))


def bin_counts(values, step, max_val=None, min_val=None):
    """
    Generic fixed-width binning, mirrors the repeated `bins()`/`mkBins()`
    pattern used across renderYearHist, renderAreaHist, renderEUI, renderGHG,
    renderHeatLoss, insulHist in retrofits.html:
        k = floor(v / step) * step ; bins[k]++
    Returns {bin_start: count}, bin_start as native Python number (int if
    step is an int, float otherwise) to keep JSON keys clean.
    """
    values = np.asarray(values, dtype=float)
    values = values[~np.isnan(values)]
    if max_val is not None:
        values = values[values <= max_val]
    if min_val is not None:
        values = values[values >= min_val]
    if values.size == 0:
        return {}
    bin_starts = np.floor(values / step) * step
    out = {}
    is_int_step = float(step).is_integer()
    for b in bin_starts:
        key = int(b) if is_int_step else round(float(b), 2)
        out[key] = out.get(key, 0) + 1
    return out


def flag_series(df, col):
    """Mirrors flag(r,k) in JS: True/'True'/1/'1' all count as truthy."""
    if col not in df.columns:
        return pd.Series(False, index=df.index)
    s = df[col]
    return s.astype(str).isin(['True', 'true', '1']) | (s == True) | (s == 1)


# =============================================================================
# Per-slice (one province, one house-type filter) chart computation
# =============================================================================

def compute_slice(df):
    """
    df: rows already filtered to (province, house type) — or the full
    province if house type == 'All types'.
    Returns the full precomputed chart payload for this slice.
    """
    n = len(df)
    out = {'row_count': n}
    if n == 0:
        return out

    # ---- headline stat cards (mirrors render()) ----
    savings = num(df.get('EnergySavingPct')).dropna().to_numpy()
    med_saving = median(savings)
    out['median_saving_pct'] = med_saving

    deep = int(flag_series(df, 'Deep_Retrofit').sum())
    hp   = int(flag_series(df, 'HeatPump_Addition').sum())
    fs   = int(flag_series(df, 'FuelSwitch').sum())
    out['deep_retrofit_count'] = deep
    out['heat_pump_count'] = hp
    out['fuel_switch_count'] = fs

    # ---- EUI (mirrors render()'s preEUIs/postEUIs + renderEUI()) ----
    area = num(df.get('FloorArea'))
    pre_e = num(df.get('Pre_TotalEnergy'))
    post_e = num(df.get('Post_TotalEnergy'))
    valid_area = area.notna() & (area > 0)
    pre_euis = (pre_e[valid_area & pre_e.notna()] / area[valid_area & pre_e.notna()]).to_numpy()
    post_euis = (post_e[valid_area & post_e.notna()] / area[valid_area & post_e.notna()]).to_numpy()
    eui_pre_med = median(pre_euis)
    eui_post_med = median(post_euis)
    out['eui_pre_median'] = eui_pre_med
    out['eui_post_median'] = eui_post_med
    out['eui_saving'] = (round(eui_pre_med - eui_post_med)
                          if eui_pre_med is not None and eui_post_med is not None else None)
    out['eui_pre_bins'] = bin_counts(pre_euis, step=20, max_val=500)
    out['eui_post_bins'] = bin_counts(post_euis, step=20, max_val=500)

    # ---- GHG, 4 scenarios (mirrors render() + renderGHG()) ----
    # "reported" is raw ERSGHG (only ~50.5% of matched pairs have it -- see
    # docs/RETROFITS.md); "current"/"current_corrected"/"as_audited" are
    # calculated from each home's own fuel consumption by
    # Python/compute_ghg_scenarios.py (~100% coverage) -- see that script and
    # Python/ghg_factors.py for the 4 scenarios' definitions and citations.
    # "reported" stays under the original flat keys (ghg_pre_median, etc.) for
    # backward compatibility with aggregate_canada.py's CA.json rollup and any
    # other consumer that reads them directly; the other 3 live under
    # ghg_scenarios. n/coverage_pct ship alongside so the front end can show
    # how much of the population each scenario actually describes.
    def ghg_scenario_block(pre_col, post_col):
        pre = num(df.get(pre_col))
        post = num(df.get(post_col))
        pair = pd.DataFrame({'pre': pre, 'post': post}).dropna()
        pre_v = pair['pre'].to_numpy()
        post_v = pair['post'].to_numpy()
        pre_med = median(pre_v)
        post_med = median(post_v)
        deltas = (pair['pre'] - pair['post'])
        deltas = deltas[(deltas > 0) & (deltas <= 30)].to_numpy()
        return {
            'n': int(len(pair)),
            'coverage_pct': round(len(pair) / n, 3) if n else None,
            'pre_median': pre_med,
            'post_median': post_med,
            'saving': (round(pre_med - post_med, 1)
                       if pre_med is not None and post_med is not None else None),
            'pre_bins': bin_counts(pre_v, step=1, max_val=30),
            'post_bins': bin_counts(post_v, step=1, max_val=30),
            'delta_bins': bin_counts(deltas, step=1),
        }

    reported = ghg_scenario_block('Pre_GHG', 'Post_GHG')
    out['ghg_pre_median'] = reported['pre_median']
    out['ghg_post_median'] = reported['post_median']
    out['ghg_saving'] = reported['saving']
    out['ghg_pre_bins'] = reported['pre_bins']
    out['ghg_post_bins'] = reported['post_bins']
    out['ghg_delta_bins'] = reported['delta_bins']
    out['ghg_reported_n'] = reported['n']
    out['ghg_reported_coverage_pct'] = reported['coverage_pct']

    out['ghg_scenarios'] = {
        'reported': reported,
        'current': ghg_scenario_block('Pre_GHG_current', 'Post_GHG_current'),
        'current_corrected': ghg_scenario_block('Pre_GHG_current_corrected', 'Post_GHG_current_corrected'),
        'as_audited': ghg_scenario_block('Pre_GHG_as_audited', 'Post_GHG_as_audited'),
    }

    # ---- Energy cost $ (mirrors renderCost() in retrofits.html) ----
    # Only present when this province was priced (ON/QC/AB); other provinces
    # skip these fields and the front end hides the $-card entirely.
    if '_CostPre' in df.columns:
        cpre = df['_CostPre'].to_numpy(dtype=float)
        cpost = df['_CostPost'].to_numpy(dtype=float)
        valid = cpre > 0  # drop homes with no priced energy (all-zero fuel data)
        cpre_v, cpost_v = cpre[valid], cpost[valid]
        cdelta_all = cpre_v - cpost_v
        out['cost_pre_median'] = median(cpre_v)
        out['cost_post_median'] = median(cpost_v)
        # median of each home's OWN pre-post change (incl. increases), matching
        # the s-cost-saving KPI and the EUI/GHG "median saving" convention.
        out['cost_saving_median'] = median(cdelta_all)
        out['cost_pre_bins'] = bin_counts(cpre_v, step=COST_BIN, max_val=COST_CAP)
        out['cost_post_bins'] = bin_counts(cpost_v, step=COST_BIN, max_val=COST_CAP)
        cdelta = cdelta_all[(cdelta_all > 0) & (cdelta_all <= COST_DELTA_CAP)]
        out['cost_delta_bins'] = bin_counts(cdelta, step=COST_BIN)

    # ---- Solar (mirrors renderSolar()) ----
    pre_solar = num(df.get('Pre_SolarPV'))
    post_solar = num(df.get('Post_SolarPV'))
    pre_adopt_n = int((pre_solar > 0).sum())
    post_adopt_mask = post_solar > 0
    post_adopt_n = int(post_adopt_mask.sum())
    solar_sizes = post_solar[post_adopt_mask].dropna().to_numpy()
    out['solar_pre_pct'] = round(pre_adopt_n / n * 100) if n else 0
    out['solar_post_pct'] = round(post_adopt_n / n * 100) if n else 0
    out['solar_post_count'] = post_adopt_n
    out['solar_median_kw'] = median(solar_sizes)

    # ---- Year built histogram (mirrors renderYearHist(): decade bins, 1850-2030) ----
    years = num(df.get('YearBuilt'))
    years = years[(years >= 1850) & (years <= 2030)].dropna().to_numpy()
    decade_bins = np.floor(years / 10) * 10
    yb = {}
    for d in decade_bins:
        k = int(d)
        yb[k] = yb.get(k, 0) + 1
    out['year_built_bins'] = yb

    # ---- Floor area histogram (mirrors renderAreaHist(): 50 m² bins, <=700) ----
    out['floor_area_bins'] = bin_counts(area.dropna().to_numpy(), step=50, max_val=700)

    # ---- Type / storey donuts (mirrors renderTypeDonut/renderStoreyDonut) ----
    type_counts = df['BldgType'].dropna()
    type_counts = type_counts[type_counts != '']
    out['type_counts'] = type_counts.value_counts().to_dict()

    storeys_raw = df.get('Storeys', pd.Series(dtype=str)).fillna('').astype(str).str.lower()
    storey_labels = storeys_raw.map(lambda s: STOREY_MAP.get(s, s if s else 'Unknown'))
    # Preserve original casing fallback like JS (r.Storeys) when not in MAP and non-empty
    orig_storeys = df.get('Storeys', pd.Series(dtype=str)).fillna('Unknown').astype(str)
    storey_final = [
        STOREY_MAP.get(low, orig if orig else 'Unknown')
        for low, orig in zip(storeys_raw, orig_storeys)
    ]
    out['storey_counts'] = pd.Series(storey_final).value_counts().to_dict()

    # ---- Design heat loss (mirrors renderHeatLoss(): BINS.heatloss=2 kW bins,
    # 0 < v <= 150). Values are kW (design/peak heating demand, from
    # EGHDESHTLOSS W*0.001 in ers_web_pipeline.py) — NOT annual GJ. ----
    hl_pre_s = num(df.get('Pre_HeatLoss'))
    hl_post_s = num(df.get('Post_HeatLoss'))
    hl_pre = hl_pre_s[(hl_pre_s > 0) & (hl_pre_s <= 150)].dropna().to_numpy()
    hl_post = hl_post_s[(hl_post_s > 0) & (hl_post_s <= 150)].dropna().to_numpy()
    out['heatloss_pre_bins'] = bin_counts(hl_pre, step=2)
    out['heatloss_post_bins'] = bin_counts(hl_post, step=2)

    # Per-home improvement histogram (mirrors renderHeatLoss()'s deltaBins:
    # d = pre - post, kept where 0 < d <= 150, same 2 kW step).
    hl_pair = pd.DataFrame({'pre': hl_pre_s, 'post': hl_post_s}).dropna()
    hl_pair = hl_pair[(hl_pair['pre'] > 0) & (hl_pair['post'] > 0)]
    hl_deltas = (hl_pair['pre'] - hl_pair['post'])
    hl_deltas = hl_deltas[(hl_deltas > 0) & (hl_deltas <= 150)].to_numpy()
    out['heatloss_delta_bins'] = bin_counts(hl_deltas, step=2)

    # ---- Annual heat loss by envelope component (mirrors
    # renderHeatLossComponents() / HL_COMPONENT_FIELDS in assets/retrofits.js).
    # Per-home MEANS in kWh/yr, for the same reason the waterfall uses means:
    # the FSA view sums raw rows and divides by n, and the chart's "share of
    # total" column only makes sense if the six components add to the whole.
    # These are EGHHL* annual energies, NOT the EGHDESHTLOSS design-day kW
    # binned immediately above — different quantity, same English name.
    hl_components = []
    for key, label in HEATLOSS_COMPONENTS:
        pre_arr = num(df.get(f'Pre_{key}')).fillna(0).to_numpy()
        post_arr = num(df.get(f'Post_{key}')).fillna(0).to_numpy()
        pre_mean = float(pre_arr.mean()) if pre_arr.size else 0.0
        post_mean = float(post_arr.mean()) if post_arr.size else 0.0
        if pre_mean == 0 and post_mean == 0:
            continue
        hl_components.append({
            'label': label,
            'pre': round(pre_mean, 1),
            'post': round(post_mean, 1),
        })
    out['heatloss_components'] = hl_components

    # ---- Savings histogram (mirrors renderHist(): 1% bins on EnergySavingPct) ----
    if savings.size:
        pct_bins = {}
        for v in savings:
            b = round(v * 100)
            pct_bins[b] = pct_bins.get(b, 0) + 1
        out['savings_pct_bins'] = pct_bins
    else:
        out['savings_pct_bins'] = {}

    # ---- Sankey (mirrors renderSankey(): fuel flow totals, pre/post energy GWh) ----
    # Wood species (Softwood/Hardwood/Mixed Wood/Wood Pellets) collapsed into
    # one 'Wood' node -- each individually too small to read on the Sankey
    # and cluttering it with near-duplicate nodes. Matches sankeyFuelLabel()
    # in retrofits.html's client-side (FSA-mode) renderSankey().
    def sankey_fuel_label(s):
        # .str.contains(na=False) leaves genuine NaNs as NaN (not stringified),
        # so the notna()/!='' filter below still drops them same as before.
        return s.where(~s.str.contains('wood', case=False, na=False), 'Wood')
    pre_fuel = df.get('Pre_HeatFuel')
    post_fuel = df.get('Post_HeatFuel')
    flows = {}
    if pre_fuel is not None and post_fuel is not None:
        tmp = pd.DataFrame({
            'pf': sankey_fuel_label(pre_fuel), 'qf': sankey_fuel_label(post_fuel),
            'pre_e': pre_e.fillna(0), 'post_e': post_e.fillna(0),
        })
        tmp = tmp[(tmp['pf'].notna()) & (tmp['pf'] != '') & (tmp['qf'].notna()) & (tmp['qf'] != '')]
        grouped = tmp.groupby(['pf', 'qf'], as_index=False).agg(
            pre=('pre_e', 'sum'), post=('post_e', 'sum'))
        for _, row in grouped.iterrows():
            flows[f"{row['pf']}|||{row['qf']}"] = {
                'pre': float(row['pre']), 'post': float(row['post'])}
    out['sankey_flows'] = flows

    # ---- Waterfall (per-home MEANS per fuel column, pre/post) ----
    # MEANS, not medians: renderProvinceWaterfall() multiplies these by
    # row_count to recover group totals (mean*n == sum exactly), matching the
    # FSA view which sums raw rows. A median here would also zero out any
    # fuel used by fewer than half the homes, silently dropping minority
    # fuels (oil, wood, propane) from the chart entirely — the exact flaw
    # the JS `mean` helper's comment documents.
    waterfall = []
    for key, label in WATERFALL_FUELS:
        pre_col = num(df.get(f'Pre_{key}')).fillna(0).to_numpy()
        post_col = num(df.get(f'Post_{key}')).fillna(0).to_numpy()
        pm = round(float(pre_col.mean())) if pre_col.size else 0
        qm = round(float(post_col.mean())) if post_col.size else 0
        if pm == 0 and qm == 0:
            continue
        waterfall.append({'fuel': label, 'pre': pm, 'post': qm})
    total_pre_arr = pre_e.fillna(0).to_numpy()
    total_post_arr = post_e.fillna(0).to_numpy()
    total_pre = round(float(total_pre_arr.mean())) if total_pre_arr.size else 0
    total_post = round(float(total_post_arr.mean())) if total_post_arr.size else 0
    waterfall.append({'fuel': 'TOTAL', 'pre': total_pre, 'post': total_post})
    out['waterfall'] = waterfall

    # ---- Insulation KPI cards (mirrors renderKPI()) ----
    kpi_defs = [
        ('Roof insulation', 'Pre_RoofInsulation', 'Post_RoofInsulation', 'RSI', True),
        ('Wall insulation', 'Pre_WallInsulation', 'Post_WallInsulation', 'RSI', True),
        ('Foundation ins.', 'Pre_FoundationInsulation', 'Post_FoundationInsulation', 'RSI', True),
        ('Air leakage', 'Pre_AirLeakage', 'Post_AirLeakage', 'ACH50', False),
    ]
    kpis = []
    for label, pre_col, post_col, unit, higher_is_better in kpi_defs:
        pv = num(df.get(pre_col))
        qv = num(df.get(post_col))
        pv = pv[pv > 0].dropna().to_numpy()
        qv = qv[qv > 0].dropna().to_numpy()
        pm, qm = median(pv), median(qv)
        if pm is None or qm is None:
            continue
        kpis.append({'label': label, 'pre': round(pm, 1), 'post': round(qm, 1),
                      'unit': unit, 'higher_is_better': higher_is_better})
    out['insulation_kpis'] = kpis

    # ---- Insulation pre/post histograms + delta histograms (mirrors insulHist/deltaHist) ----
    insul_defs = [
        ('roof', 'Pre_RoofInsulation', 'Post_RoofInsulation', 14, 0.5, 'RSI', False, 12),
        ('air',  'Pre_AirLeakage',     'Post_AirLeakage',     20, 0.5, 'ACH50', True, 15),
        ('wall', 'Pre_WallInsulation', 'Post_WallInsulation', 7,  0.25, 'RSI', False, 5),
        ('fnd',  'Pre_FoundationInsulation', 'Post_FoundationInsulation', 6, 0.25, 'RSI', False, 5),
    ]
    insulation = {}
    for key, pre_col, post_col, max_val, step, unit, invert, max_delta in insul_defs:
        pv = num(df.get(pre_col))
        qv = num(df.get(post_col))
        pv_valid = pv[(pv > 0) & (pv <= max_val)].dropna().to_numpy()
        qv_valid = qv[(qv > 0) & (qv <= max_val)].dropna().to_numpy()
        pre_bins = bin_counts(pv_valid, step=step)
        post_bins = bin_counts(qv_valid, step=step)

        # delta histogram: pairwise per-row delta where both pre/post > 0
        pair = pd.DataFrame({'pre': pv, 'post': qv}).dropna()
        pair = pair[(pair['pre'] > 0) & (pair['post'] > 0)]
        deltas = (pair['pre'] - pair['post']) if invert else (pair['post'] - pair['pre'])
        deltas = deltas[(deltas > 0) & (deltas <= max_delta)].to_numpy()
        delta_bins = bin_counts(deltas, step=step)

        insulation[key] = {
            'unit': unit,
            'pre_bins': pre_bins,
            'post_bins': post_bins,
            'delta_bins': delta_bins,
        }
    out['insulation_histograms'] = insulation

    # ---- EUI delta histogram (mirrors euiDeltaHist(): step 10, 0 < d <= 500) ----
    pair = pd.DataFrame({'pre': pre_e, 'post': post_e, 'area': area}).dropna()
    pair = pair[pair['area'] > 0]
    eui_deltas = (pair['pre'] - pair['post']) / pair['area']
    eui_deltas = eui_deltas[(eui_deltas > 0) & (eui_deltas <= 500)].to_numpy()
    out['eui_delta_bins'] = bin_counts(eui_deltas, step=10)

    # ---- Measures bar + spider chart (mirrors renderMeasures/renderSpider) ----
    measures = []
    for key, label in MEASURES:
        c = int(flag_series(df, key).sum())
        pct = round(c / n * 100) if n else 0
        measures.append({'key': key, 'label': label, 'count': c, 'pct': pct})
    out['measures'] = measures

    # ---- Heat pump sizing + backup fuel ----
    # "Has a heat pump" = Post_HPType present. normalize_categoricals() already
    # collapsed 'N/A {no Heat Pump}' variants (and '0') to NaN for this column,
    # so a plain notna() check is the clean presence flag.
    hp_mask = (df['Post_HPType'].notna() if 'Post_HPType' in df.columns
               else pd.Series(False, index=df.index))
    n_hp = int(hp_mask.sum())
    out['hp_home_count'] = n_hp

    if n_hp:
        # Sizing = AHRI-certificate-verified capacity (join_hp_capacity.py) ÷
        # design heat loss. NOT the raw auditor-entered HPCAP field -- that
        # was validated against real certificates and runs a median 1.55x
        # high, unreliable for a sizing claim. 47F = mild-day rated capacity;
        # 5F (~-15C) is a Canadian design-day proxy for whether the heat
        # pump alone can carry the full load or is deliberately undersized
        # against backup. Both are computed independently (a home can have
        # one without the other) -- see join_hp_capacity.py's docstring.
        hl = num(df.get('Post_HeatLoss'))
        valid_hl = hl > 0
        for key, cap_col in (('47', 'Post_HPCapacity47'), ('5', 'Post_HPCapacity5')):
            cap = num(df.get(cap_col))
            mask = hp_mask & cap.notna() & valid_hl
            sizing = (cap[mask] / hl[mask]).to_numpy()
            out[f'hp_sizing{key}_bins'] = bin_counts(sizing, step=0.1, max_val=3.0)
            out[f'hp_sizing{key}_median'] = median(sizing)

        # Backup fuel among heat-pump homes. Post_HeatFuel/Post_HeatType is
        # NOT the heat pump -- HOT2000 models it as a separate component, so
        # for a heat-pump home this column is the companion/backup system
        # (the "Heat Pump + backup" pairing).
        backup_fuel = df.loc[hp_mask, 'Post_HeatFuel'].dropna()
        backup_fuel = backup_fuel[backup_fuel != '']
        out['backup_fuel_counts'] = backup_fuel.value_counts().to_dict()

        # "Backup actually used" -- restricted to Natural Gas/Oil/Propane,
        # the fuels with a 1:1 label-to-consumption-column mapping.
        # Excluded: Electricity (Post_HeatElectricity can't distinguish the
        # heat pump's own electricity from an electric-baseboard backup's --
        # both are the same column) and the wood species (Mixed Wood/
        # Hardwood/Wood Pellets/Softwood all share one Post_HeatWood
        # consumption column, so a per-species check isn't meaningful). Both
        # still appear in backup_fuel_counts above.
        # IMPORTANT: the denominator here is homes whose OWN backup_fuel is
        # this fuel, not every heat-pump home -- otherwise this can exceed
        # backup_fuel_counts[fuel] (some other-fuel-backup homes show trace
        # nonzero consumption in an unrelated fuel channel) and read as a
        # nonsensical >100%.
        backup_used = {}
        for fuel, col in [('Natural Gas', 'Post_HeatNaturalGas'), ('Oil', 'Post_HeatOil'),
                          ('Propane', 'Post_HeatPropane')]:
            fuel_mask = hp_mask & (df.get('Post_HeatFuel') == fuel)
            v = num(df.loc[fuel_mask, col]) if col in df.columns else pd.Series(dtype=float)
            backup_used[fuel] = int((v > 0).sum())
        out['backup_used_counts'] = backup_used

        # Electricity (the heat pump's own heating draw) vs. backup-fuel
        # energy, mean kWh/yr per home, for the "Heat pump + backup" card's
        # comparison chart (mirrors renderHPBackupFsa in retrofits.html).
        # Post_HeatElectricity is safe to use as "the heat pump's own
        # electricity" here specifically because this is restricted to
        # combustion-backup homes -- no electric backup coexists in that
        # case (see the exclusion note on backup_used above).
        backup_energy = {}
        for fuel, col in [('Natural Gas', 'Post_HeatNaturalGas'), ('Oil', 'Post_HeatOil'),
                          ('Propane', 'Post_HeatPropane')]:
            fuel_mask = hp_mask & (df.get('Post_HeatFuel') == fuel)
            fuel_v = num(df.loc[fuel_mask, col]) if col in df.columns else pd.Series(dtype=float)
            elec_v = num(df.loc[fuel_mask, 'Post_HeatElectricity']) if 'Post_HeatElectricity' in df.columns else pd.Series(dtype=float)
            paired = pd.concat([fuel_v, elec_v], axis=1).dropna()
            if len(paired):
                backup_energy[fuel] = {
                    'elec_mean': float(paired.iloc[:, 1].mean()),
                    'fuel_mean': float(paired.iloc[:, 0].mean()),
                    'n': int(len(paired)),
                }
        out['backup_energy_means'] = backup_energy
    else:
        out['hp_sizing47_bins'] = {}
        out['hp_sizing5_bins'] = {}
        out['hp_sizing47_median'] = None
        out['hp_sizing5_median'] = None
        out['backup_fuel_counts'] = {}
        out['backup_used_counts'] = {}
        out['backup_energy_means'] = {}

    # ---- Heat pump AHRI numbers + window codes ----
    # Full counts are stored (not just the top N) so aggregate_canada.py can
    # sum them across provinces and re-rank for an accurate NATIONAL top N —
    # truncating to top N here first would silently drop a code/number that's
    # locally #6 everywhere but nationally #1. The *_top fields below are a
    # display-ready convenience slice of this same province's own counts.
    def code_counts(series, min_digits=0):
        s = series.dropna().astype(str).str.strip()
        # Defensive: some source AHRI values carry a stray trailing '.0'
        # (same model double-counted under two keys) — normalize even though
        # ers_web_pipeline.py now does this too, in case the parquet being
        # read here predates that fix.
        s = s.str.replace(r'\.0+$', '', regex=True)
        if min_digits:
            s = s[s.str.count(r'\d') >= min_digits]
        s = s[s != '']
        return s.value_counts().to_dict()

    def top_n(counts, n):
        return [{'code': k, 'count': v} for k, v in
                sorted(counts.items(), key=lambda kv: -kv[1])[:n]]

    ahri_vals = pd.concat([df.get('Pre_HPAHRI', pd.Series(dtype=str)),
                           df.get('Post_HPAHRI', pd.Series(dtype=str))])
    out['ahri_counts'] = code_counts(ahri_vals, min_digits=4)
    out['top_ahri_numbers'] = top_n(out['ahri_counts'], 5)

    out['window_pre_counts'] = code_counts(df.get('Pre_WindowCode', pd.Series(dtype=str)))
    out['window_post_counts'] = code_counts(df.get('Post_WindowCode', pd.Series(dtype=str)))
    out['window_pre_top'] = top_n(out['window_pre_counts'], 5)
    out['window_post_top'] = top_n(out['window_post_counts'], 5)

    # ---- Audit-year histograms (mirrors renderAuditYearChart()) ----
    # Each matched pair contributes an initial (D = Pre_Date year) and a
    # follow-up (E = Post_Date year) audit; one bin per calendar year in
    # 1990-2035. Per-slice so the province view can render the chart with the
    # selected house type solid and the rest faded (same as the FSA view). The
    # parquet carries the full date strings (Pre_Date/Post_Date); the shipped
    # FSA files keep only the year (see split_fsa_json.add_year_columns).
    def year_counts(col):
        if col not in df.columns:
            return {}
        yrs = pd.to_datetime(df[col], errors='coerce').dt.year
        yrs = yrs[(yrs >= 1990) & (yrs <= 2035)].dropna().astype(int)
        return {int(k): int(v) for k, v in yrs.value_counts().items()}
    out['d_year_bins'] = year_counts('Pre_Date')
    out['e_year_bins'] = year_counts('Post_Date')

    return out


# =============================================================================
# Top-level: one province parquet -> one JSON with all house-type slices
# =============================================================================

def load_audit_totals():
    """Audit-composition sidecar, or {} if not built. Shape:
    {"by_fsa": {...}, "by_province": {PROV: {t,de,d,e,nc}}}."""
    if not os.path.exists(AUDIT_TOTALS_PATH):
        print(f"  -- no {os.path.basename(AUDIT_TOTALS_PATH)} found; funnel -> null"
              f" (run build_fsa_audit_totals.py to populate it)")
        return {}
    with open(AUDIT_TOTALS_PATH, 'r', encoding='utf-8') as f:
        return json.load(f)


def build_province_json(parquet_path, out_dir, prov_composition=None):
    province = Path(parquet_path).stem.replace('ers_web_', '')
    print(f"\n--- {province} ---")
    df = pd.read_parquet(parquet_path)
    df = normalize_categoricals(df)
    print(f"  loaded {len(df):,} rows")

    # Price per-fuel energy against current rates (utility_rates_reference.json
    # covers all provinces/territories now). Adds _CostPre/_CostPost, which
    # compute_slice bins into the $-saved chart; unpriced provinces (shouldn't
    # happen) skip it and the card stays hidden.
    pv = price_vec_for(province)
    if pv:
        df = add_cost_columns(df, pv)
        print(f"  priced: elec {pv['elec']:.3f} $/kWh, gas {pv['gas']:.3f} $/m³, "
              f"oil {pv['oil']:.2f} $/L, propane {pv['propane']:.2f} $/L, "
              f"wood {pv['wood']:.3f} $/kWh")

    types = sorted(t for t in df['BldgType'].dropna().unique() if t)
    print(f"  house types: {types}")

    by_type = {'All types': compute_slice(df)}
    for t in types:
        sub = df[df['BldgType'] == t]
        by_type[t] = compute_slice(sub)
        print(f"    {t}: {len(sub):,} rows")

    # Audit-funnel fixed stages: composition of the province's audited population
    # (all eval types, from the sidecar) plus the total matched-pair count
    # (matched = every shipped row, i.e. len(df)). The dynamic last stage
    # (homes meeting the current house-type filter) is derived client-side from
    # each slice's row_count. null composition -> front end shows matched only.
    funnel = None
    if prov_composition:
        funnel = dict(prov_composition)
        funnel['matched'] = len(df)

    payload = {
        'province': province,
        'total_rows': len(df),
        'funnel': funnel,
        'by_type': by_type,
    }

    Path(out_dir).mkdir(parents=True, exist_ok=True)
    out_path = os.path.join(out_dir, f"{province}.json")
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(payload, f, ensure_ascii=False, separators=(',', ':'))
    size_kb = os.path.getsize(out_path) / 1024
    print(f"  wrote {out_path} ({size_kb:.1f} KB)")
    return out_path


def main():
    parquet_files = sorted(glob.glob(os.path.join(OUTPUT_DIR, "ers_web_*.parquet")))
    if not parquet_files:
        print(f"!! no province parquets found in {OUTPUT_DIR}")
        return
    by_province = load_audit_totals().get('by_province', {})
    for pf in parquet_files:
        province = Path(pf).stem.replace('ers_web_', '')
        build_province_json(pf, PROVINCE_JSON_DIR, by_province.get(province))
    print(f"\ndone. {len(parquet_files)} province JSON files written to {PROVINCE_JSON_DIR}")


if __name__ == '__main__':
    main()
