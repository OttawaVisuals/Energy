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

    # ---- GHG (mirrors render() + renderGHG()) ----
    ghg_pre = num(df.get('Pre_GHG')).dropna().to_numpy()
    ghg_post = num(df.get('Post_GHG')).dropna().to_numpy()
    ghg_pre_med = median(ghg_pre)
    ghg_post_med = median(ghg_post)
    out['ghg_pre_median'] = ghg_pre_med
    out['ghg_post_median'] = ghg_post_med
    out['ghg_saving'] = (round(ghg_pre_med - ghg_post_med, 1)
                          if ghg_pre_med is not None and ghg_post_med is not None else None)
    out['ghg_pre_bins'] = bin_counts(ghg_pre, step=1, max_val=30)
    out['ghg_post_bins'] = bin_counts(ghg_post, step=1, max_val=30)

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

    # ---- Heat loss (mirrors renderHeatLoss(): 5-unit bins, 0 < v <= 150) ----
    hl_pre = num(df.get('Pre_HeatLoss'))
    hl_post = num(df.get('Post_HeatLoss'))
    hl_pre = hl_pre[(hl_pre > 0) & (hl_pre <= 150)].dropna().to_numpy()
    hl_post = hl_post[(hl_post > 0) & (hl_post <= 150)].dropna().to_numpy()
    out['heatloss_pre_bins'] = bin_counts(hl_pre, step=5)
    out['heatloss_post_bins'] = bin_counts(hl_post, step=5)

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
    pre_fuel = df.get('Pre_HeatFuel')
    post_fuel = df.get('Post_HeatFuel')
    flows = {}
    if pre_fuel is not None and post_fuel is not None:
        tmp = pd.DataFrame({
            'pf': pre_fuel, 'qf': post_fuel,
            'pre_e': pre_e.fillna(0), 'post_e': post_e.fillna(0),
        })
        tmp = tmp[(tmp['pf'].notna()) & (tmp['pf'] != '') & (tmp['qf'].notna()) & (tmp['qf'] != '')]
        grouped = tmp.groupby(['pf', 'qf'], as_index=False).agg(
            pre=('pre_e', 'sum'), post=('post_e', 'sum'))
        for _, row in grouped.iterrows():
            flows[f"{row['pf']}|||{row['qf']}"] = {
                'pre': float(row['pre']), 'post': float(row['post'])}
    out['sankey_flows'] = flows

    # ---- Waterfall (mirrors renderWaterfall(): median per fuel column, pre/post) ----
    waterfall = []
    for key, label in WATERFALL_FUELS:
        pre_col = num(df.get(f'Pre_{key}')).fillna(0).to_numpy()
        post_col = num(df.get(f'Post_{key}')).fillna(0).to_numpy()
        pm = round(median(pre_col) or 0)
        qm = round(median(post_col) or 0)
        if pm == 0 and qm == 0:
            continue
        waterfall.append({'fuel': label, 'pre': pm, 'post': qm})
    total_pre = round(median(pre_e.fillna(0).to_numpy()) or 0)
    total_post = round(median(post_e.fillna(0).to_numpy()) or 0)
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

    return out


# =============================================================================
# Top-level: one province parquet -> one JSON with all house-type slices
# =============================================================================

def build_province_json(parquet_path, out_dir):
    province = Path(parquet_path).stem.replace('ers_web_', '')
    print(f"\n--- {province} ---")
    df = pd.read_parquet(parquet_path)
    df = normalize_categoricals(df)
    print(f"  loaded {len(df):,} rows")

    types = sorted(t for t in df['BldgType'].dropna().unique() if t)
    print(f"  house types: {types}")

    by_type = {'All types': compute_slice(df)}
    for t in types:
        sub = df[df['BldgType'] == t]
        by_type[t] = compute_slice(sub)
        print(f"    {t}: {len(sub):,} rows")

    payload = {
        'province': province,
        'total_rows': len(df),
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
    for pf in parquet_files:
        build_province_json(pf, PROVINCE_JSON_DIR)
    print(f"\ndone. {len(parquet_files)} province JSON files written to {PROVINCE_JSON_DIR}")


if __name__ == '__main__':
    main()
