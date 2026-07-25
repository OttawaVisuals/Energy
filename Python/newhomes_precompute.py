"""
newhomes_precompute.py

Turns the per-province parquet from newhomes_pipeline.py into the web-ready
JSON the New Homes Explorer (newhomes.html) fetches:

  newhomes_json/<PROV>.json     province-wide precomputed payload, per house type
  newhomes_json/CA.json         all-Canada aggregate (computed on the concat)
  newhomes_fsa/<PROV>/<FSA>.json raw rows (array-of-arrays) for the FSA view
  newhomes_fsa/<PROV>/_index.json  [{fsa,row_count,median_ers,median_tier,median_ach}]

BIN WIDTHS / THRESHOLDS below MUST match the BINS object in newhomes.html, so
the precomputed province view and the raw-row FSA view show identically-shaped
histograms for the same data. (Same contract as precompute_province_stats.py.)
"""

import os
import glob
import json
from pathlib import Path

import pandas as pd
import numpy as np

OUTPUT_DIR       = r"C:\ERS\web_nc"
PROVINCE_JSON_DIR = os.path.join(OUTPUT_DIR, "province_json")
FSA_JSON_DIR      = os.path.join(OUTPUT_DIR, "fsa_json")

# --- bin widths (mirror BINS in newhomes.html) ---
B_ERS  = 10     # ERS rating GJ/yr
B_GHG  = 1      # tonnes CO2e/yr
B_ACH  = 0.5    # air changes / hr @ 50 Pa
B_AREA = 25     # m2
B_EUI  = 10     # kWh/m2/yr
B_GAP  = 5      # EUI design gap kWh/m2/yr (as-built - designed)
B_DENS = 10     # designed-vs-as-built 2D scatter density cell (kWh/m2/yr)

# clip ranges (values outside stay in medians/counts, dropped from histograms)
C_ERS, C_GHG, C_ACH, C_AREA, C_EUI = 300, 30, 10, 700, 400

# Insulation histograms, in R-value (imperial) to match retrofits.html's
# convention -- RoofInsulation etc. are RSI in the source data, converted
# with the same factor retrofits.html uses (RSI_TO_R=5.678). Bin widths/max
# mirror the ranges retrofits.html already charts for the same components.
RSI_TO_R = 5.678
B_ROOF_R, C_ROOF_R = 2, 80
B_WALL_R, C_WALL_R = 2, 40
B_FND_R,  C_FND_R  = 2, 35
B_FLR_R,  C_FLR_R  = 2, 40

NO_HP = 'N/A {no Heat Pump}'

FUEL_GROUPS = {  # collapse the long fuel tail into 3 series for trend charts
    'Natural Gas': 'Gas', 'Electricity': 'Electricity',
}
def fuel_group(f):
    if not isinstance(f, str) or not f.strip():
        return None
    return FUEL_GROUPS.get(f.strip(), 'Other')


def null_ers_placeholders(df):
    """ERSRating/Designed_ERSRating == 0 is "not rated on the ERS scale", not a
    net-zero house -- null it out before anything downstream reads the column.

    These are files rated on the older EnerGuide 0-100 scale instead: the two
    scales are mutually exclusive per record. Of the 14,151 as-built rows with
    ERSRating == 0, 96.3% carry a real EGHRating (median 82) while only 0.2% of
    ERSRating > 0 rows do. It is a vintage artifact, not a regional one -- 100%
    of 2015-and-earlier files are EGH-scale, decaying to ~0.5% from 2023 on, so
    the provincial spread (ON 29.4% vs PE 0.2%) just tracks how old each
    province's file mix is. The residual post-2023 zeros carry no EGHRating
    either, i.e. genuinely missing.

    RatingGap is as-built minus design, so it is meaningless once either side is
    a placeholder -- drop it on those rows too.
    """
    for c in ('ERSRating', 'Designed_ERSRating'):
        if c in df.columns:
            df.loc[pd.to_numeric(df[c], errors='coerce') == 0, c] = np.nan
    if 'RatingGap' in df.columns:
        miss = False
        for c in ('ERSRating', 'Designed_ERSRating'):
            if c in df.columns:
                miss = miss | df[c].isna()
        if miss is not False:
            df.loc[miss, 'RatingGap'] = np.nan
    return df


def num(s):
    return pd.to_numeric(s, errors='coerce')

def median(a):
    a = np.asarray(a, dtype=float); a = a[~np.isnan(a)]
    return float(np.median(a)) if a.size else None

def bins(values, step, lo=None, hi=None):
    v = np.asarray(values, dtype=float); v = v[~np.isnan(v)]
    if lo is not None: v = v[v >= lo]
    if hi is not None: v = v[v <= hi]
    if not v.size: return {}
    starts = np.floor(v / step) * step
    out = {}
    is_int = float(step).is_integer()
    for b in starts:
        k = int(b) if is_int else round(float(b), 2)
        out[k] = out.get(k, 0) + 1
    return out

def counts(series):
    s = series.dropna().astype(str).str.strip()
    s = s[s != '']
    return s.value_counts().to_dict()

def code_counts(series, min_digits=0):
    """Mirrors precompute_province_stats.py's code_counts: full counts (not
    top-N) so the client can group by outdoor model itself; '.0'-suffix
    normalized defensively even though newhomes_pipeline.py's clean_ahri
    already strips it."""
    s = series.dropna().astype(str).str.strip()
    s = s.str.replace(r'\.0+$', '', regex=True)
    if min_digits:
        s = s[s.str.count(r'\d') >= min_digits]
    s = s[s != '']
    return s.value_counts().to_dict()


def compute_slice(df):
    n = len(df)
    out = {'row_count': n}
    if n == 0:
        return out

    ers  = num(df.get('ERSRating'))
    area = num(df.get('FloorArea'))
    ghg  = num(df.get('GHG'))
    ach  = num(df.get('AirLeakage'))
    eui  = num(df.get('EUI'))
    tier = num(df.get('Tier'))
    impr = num(df.get('Improvement'))
    # Plan-file (P) counterparts. On new construction the "before" audit is the
    # design model, not a pre-retrofit house — see the airtightness note below.
    dach  = num(df.get('Designed_AirLeakage'))
    dtier = num(df.get('Designed_Tier'))

    # ---- headline stats ----
    out['median_ers']  = median(ers[ers > 0])
    out['median_area'] = median(area)
    out['median_ghg']  = median(ghg)
    out['median_ach']  = median(ach)
    out['median_designed_ach'] = median(dach)
    out['median_eui']  = median(eui[(eui > 0) & (eui <= C_EUI)])
    out['median_improvement'] = median(impr)
    out['pct_solar'] = round(float((num(df.get('SolarPV')) > 0).mean()) * 100, 1) if n else 0

    # ---- heat pump ----
    hp_type = df.get('HPType')
    if hp_type is not None:
        hp_s = hp_type.astype(str).str.strip()
        has_hp = hp_type.notna() & (hp_s != '') & (hp_s != NO_HP)
        out['heat_pump_count'] = int(has_hp.sum())
    else:
        out['heat_pump_count'] = 0

    # As-built (installed) heat pump AHRI certificate numbers only -- not
    # Designed_HPAHRI, matching heat_pump_count's as-built-only framing.
    out['ahri_counts'] = code_counts(df.get('HPAHRI', pd.Series(dtype=str)), min_digits=4)

    # ---- insulation (RSI -> R-value, matching retrofits.html's convention) ----
    roof_r  = num(df.get('RoofInsulation')) * RSI_TO_R
    wall_r  = num(df.get('WallInsulation')) * RSI_TO_R
    fnd_r   = num(df.get('FoundationInsulation')) * RSI_TO_R
    floor_r = num(df.get('FloorInsulation')) * RSI_TO_R
    out['median_roof_r']  = median(roof_r[roof_r > 0])
    out['median_wall_r']  = median(wall_r[wall_r > 0])
    out['median_fnd_r']   = median(fnd_r[fnd_r > 0])
    out['median_floor_r'] = median(floor_r[floor_r > 0])
    out['roof_ins_bins']  = bins(roof_r,  B_ROOF_R, lo=0, hi=C_ROOF_R)
    out['wall_ins_bins']  = bins(wall_r,  B_WALL_R, lo=0, hi=C_WALL_R)
    out['fnd_ins_bins']   = bins(fnd_r,   B_FND_R,  lo=0, hi=C_FND_R)
    out['floor_ins_bins'] = bins(floor_r, B_FLR_R,  lo=0, hi=C_FLR_R)

    # ---- distributions ----
    out['ers_bins']  = bins(ers, B_ERS, lo=1, hi=C_ERS)
    out['ghg_bins']  = bins(ghg, B_GHG, lo=0, hi=C_GHG)
    out['ach_bins']  = bins(ach, B_ACH, lo=0, hi=C_ACH)
    out['designed_ach_bins'] = bins(dach, B_ACH, lo=0, hi=C_ACH)
    out['area_bins'] = bins(area, B_AREA, lo=0, hi=C_AREA)
    out['eui_bins']  = bins(eui, B_EUI, lo=0, hi=C_EUI)

    # ---- as-built NBC tier mix (recent years) ----
    out['tier_counts'] = {int(k): int(v) for k, v in
                          tier.dropna().astype(int).value_counts().sort_index().items()}
    out['designed_tier_counts'] = {int(k): int(v) for k, v in
                                   dtier.dropna().astype(int).value_counts().sort_index().items()}
    # Designed -> as-built tier movement, as [designed, as_built, homes] triples.
    # Roughly half of homes land on a different tier than their plan file, in
    # both directions, so the two mixes above can't be read as a before/after.
    tpair = pd.DataFrame({'d': dtier, 'a': tier}).dropna()
    if len(tpair):
        tp = tpair.astype(int).groupby(['d', 'a']).size()
        out['tier_transition'] = [[int(d), int(a), int(c)] for (d, a), c in tp.items()]
        same = int((tpair['d'] == tpair['a']).sum())
        out['tier_move'] = {
            'n': len(tpair),
            'pct_same':  round(same / len(tpair) * 100, 1),
            'pct_up':    round(float((tpair['a'] > tpair['d']).mean()) * 100, 1),
            'pct_down':  round(float((tpair['a'] < tpair['d']).mean()) * 100, 1),
        }
    else:
        out['tier_transition'] = []
        out['tier_move'] = {'n': 0}

    # ---- fuel + type breakdown ----
    out['fuel_counts'] = counts(df.get('HeatFuel', pd.Series(dtype=str)))
    out['type_counts'] = counts(df.get('BldgType', pd.Series(dtype=str)))
    out['compliance_counts'] = counts(df.get('CompliancePath', pd.Series(dtype=str)))

    # ---- trends by evaluation year ----
    yr = num(df.get('Year'))
    tmp = pd.DataFrame({'yr': yr, 'ach': ach, 'dach': dach, 'ers': ers, 'tier': tier,
                        'fuel': df.get('HeatFuel').map(fuel_group) if 'HeatFuel' in df else None})
    tmp = tmp[tmp['yr'].notna()]
    tmp['yr'] = tmp['yr'].astype(int)

    ach_by_year, dach_by_year, ers_by_year, tier_by_year, fuel_by_year = {}, {}, {}, {}, {}
    for y, g in tmp.groupby('yr'):
        if y < 2004 or y > 2030:
            continue
        m_ach = median(g['ach'])
        if m_ach is not None:
            ach_by_year[int(y)] = round(m_ach, 2)
        m_dach = median(g['dach'])
        if m_dach is not None:
            dach_by_year[int(y)] = round(m_dach, 2)
        m_ers = median(g['ers'][g['ers'] > 0])
        if m_ers is not None:
            ers_by_year[int(y)] = round(m_ers, 1)
        tc = g['tier'].dropna()
        if len(tc):
            tier_by_year[int(y)] = {int(k): int(v) for k, v in
                                    tc.astype(int).value_counts().sort_index().items()}
        fc = g['fuel'].dropna()
        if len(fc):
            fuel_by_year[int(y)] = fc.value_counts().to_dict()
    out['ach_by_year']  = ach_by_year
    out['designed_ach_by_year'] = dach_by_year
    out['ers_by_year']  = ers_by_year
    out['tier_by_year'] = tier_by_year
    out['fuel_by_year'] = fuel_by_year

    # ---- designed vs as-built, in EUI (as-built - designed; <0 beats design) ----
    # EUI rather than the ERS GJ/yr rating for two reasons. It is floor-area
    # normalised, so a big house and a small one are on the same scale -- a raw
    # GJ/yr gap is partly just a size difference. And coverage is far better:
    # both ERS ratings are present on 42.3% of records (the GJ/yr scale only
    # started in 2019), against 99.4% for EUI, which is derived from
    # TotalEnergy / FloorArea and carried on essentially every file.
    d_energy = num(df.get('Designed_TotalEnergy'))
    deui = (d_energy / area).replace([np.inf, -np.inf], np.nan)
    pair = pd.DataFrame({'d': deui, 'a': eui}).dropna()
    pair = pair[(pair['d'] > 0) & (pair['a'] > 0) & (pair['d'] <= C_EUI) & (pair['a'] <= C_EUI)]
    pair['g'] = pair['a'] - pair['d']
    npair = len(pair)
    gap_stats = {'n': npair}
    if npair:
        g = pair['g']
        gap_stats['median_gap'] = round(float(g.median()), 1)
        gap_stats['pct_beat']  = round(float((g <= 0).mean()) * 100, 1)   # tested <= design
        gap_stats['pct_worse'] = round(float((g > 0).mean()) * 100, 1)
        out['gap_bins'] = bins(g.to_numpy(), B_GAP, lo=-100, hi=60)
        # 2D density for the scatter (designed x, as-built y), cell = B_DENS
        dx = (np.floor(pair['d'] / B_DENS) * B_DENS).astype(int)
        dy = (np.floor(pair['a'] / B_DENS) * B_DENS).astype(int)
        dens = pd.Series(1, index=pd.MultiIndex.from_arrays([dx, dy])).groupby(level=[0, 1]).sum()
        out['gap_density'] = [[int(x), int(y), int(c)] for (x, y), c in dens.items()
                              if x <= C_EUI and y <= C_EUI]
    else:
        out['gap_bins'] = {}
        out['gap_density'] = []
    out['gap_stats'] = gap_stats

    # ---- airtightness: modelled at design vs measured on the finished house ----
    # AirGap = as-built - designed; <0 means the blower door beat the design
    # assumption. Most plan files carry a round assumed value (3.6, 4.5, 2.5
    # ACH50 dominate) rather than a per-house target, so read this as
    # "assumption vs measurement", not as two independent measurements.
    agap = num(df.get('AirGap'))
    apair = pd.DataFrame({'d': dach, 'a': ach, 'g': agap}).dropna()
    air_stats = {'n': len(apair)}
    if len(apair):
        g = apair['g']
        air_stats['median_gap']   = round(float(g.median()), 2)
        air_stats['pct_tighter']  = round(float((g < 0).mean()) * 100, 1)
        air_stats['pct_leakier']  = round(float((g > 0).mean()) * 100, 1)
        out['air_gap_bins'] = bins(g.to_numpy(), B_ACH, lo=-8, hi=8)
    else:
        out['air_gap_bins'] = {}
    out['air_stats'] = air_stats

    # ---- Top 20 lowest-EUI homes (most efficient, real as-built houses) ----
    # Powers the "most efficient new homes" table at the bottom of
    # newhomes.html, including its per-home expandable detail (insulation,
    # airtightness, NBC tier, heating equipment, emissions). FSA mode
    # computes the equivalent client-side from its own raw rows (see
    # topEuiFromRows() in newhomes.html) -- this precomputed list is only
    # needed for the province-wide view, which has no raw rows on the client.
    valid_eui = eui[eui > 0].dropna()
    if len(valid_eui):
        idx = valid_eui.sort_values().index[:20]
        top = df.loc[idx]
        hp_col = top.get('HPType')
        year_col = num(top.get('Year'))
        area_col = num(top.get('FloorArea'))
        ach_col = num(top.get('AirLeakage'))
        tier_col = num(top.get('Tier'))
        roof_col = num(top.get('RoofInsulation'))
        wall_col = num(top.get('WallInsulation'))
        fnd_col = num(top.get('FoundationInsulation'))
        floor_col = num(top.get('FloorInsulation'))
        ghg_col = num(top.get('GHG'))
        solar_col = num(top.get('SolarPV'))

        def rval(col, i):
            v = col.at[i] if col is not None else None
            return round(float(v) * RSI_TO_R, 1) if pd.notna(v) else None

        top20 = []
        for i in idx:
            hp_val = hp_col.at[i] if hp_col is not None else None
            hp_s = str(hp_val).strip() if pd.notna(hp_val) else ''
            top20.append({
                'eui': round(float(eui.at[i]), 1),
                'fsa': top.at[i, 'FSA'] if 'FSA' in top.columns and pd.notna(top.at[i, 'FSA']) else None,
                'type': top.at[i, 'BldgType'] if 'BldgType' in top.columns and pd.notna(top.at[i, 'BldgType']) else None,
                'year': int(year_col.at[i]) if pd.notna(year_col.at[i]) else None,
                'area': round(float(area_col.at[i]), 0) if pd.notna(area_col.at[i]) else None,
                'fuel': top.at[i, 'HeatFuel'] if 'HeatFuel' in top.columns and pd.notna(top.at[i, 'HeatFuel']) else None,
                'hp': bool(hp_s and hp_s != NO_HP),
                'ach': round(float(ach_col.at[i]), 2) if pd.notna(ach_col.at[i]) else None,
                'tier': int(tier_col.at[i]) if pd.notna(tier_col.at[i]) else None,
                'roofR': rval(roof_col, i), 'wallR': rval(wall_col, i),
                'fndR': rval(fnd_col, i), 'floorR': rval(floor_col, i),
                'heatType': top.at[i, 'HeatType'] if 'HeatType' in top.columns and pd.notna(top.at[i, 'HeatType']) else None,
                'hpType': hp_s or None,
                'hpAhri': top.at[i, 'HPAHRI'] if 'HPAHRI' in top.columns and pd.notna(top.at[i, 'HPAHRI']) else None,
                'ghg': round(float(ghg_col.at[i]), 2) if pd.notna(ghg_col.at[i]) else None,
                'solar': round(float(solar_col.at[i]), 1) if pd.notna(solar_col.at[i]) else None,
                'compliance': top.at[i, 'CompliancePath'] if 'CompliancePath' in top.columns and pd.notna(top.at[i, 'CompliancePath']) else None,
            })
        out['top20_lowest_eui'] = top20
    else:
        out['top20_lowest_eui'] = []

    return out


def build_province_json(df, province, out_dir):
    types = sorted(t for t in df['BldgType'].dropna().unique() if t)
    by_type = {'All types': compute_slice(df)}
    for t in types:
        by_type[t] = compute_slice(df[df['BldgType'] == t])
    payload = {'province': province, 'total_rows': len(df), 'by_type': by_type}
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    p = os.path.join(out_dir, f"{province}.json")
    with open(p, 'w', encoding='utf-8') as f:
        json.dump(payload, f, ensure_ascii=False, separators=(',', ':'))
    print(f"  {province}: {len(df):,} rows, {len(types)} types -> {os.path.getsize(p)/1024:.0f} KB")


# raw-row columns shipped to the FSA view
FSA_COLS = [
    'Year', 'BldgType', 'Storeys', 'FloorArea', 'ERSRating', 'EGHRating',
    'Tier', 'InScopeNBC', 'Improvement', 'CompliancePath', 'GHG', 'GHGI',
    'AirLeakage', 'EUI', 'HeatFuel', 'HeatType', 'SolarPV',
    'Designed_ERSRating', 'Designed_AirLeakage', 'Designed_Tier',
    'RatingGap', 'AirGap',

    # --- energy per fuel (whole-house, kWh) ---
    'TotalEnergy', 'Designed_TotalEnergy',
    'Electricity', 'Designed_Electricity',
    'NaturalGas', 'Designed_NaturalGas',
    'Oil', 'Designed_Oil',
    'Propane', 'Designed_Propane',
    'Wood', 'Designed_Wood',

    # --- space heating energy per fuel (kWh) ---
    'HeatElectricity', 'Designed_HeatElectricity',
    'HeatNaturalGas', 'Designed_HeatNaturalGas',
    'HeatOil', 'Designed_HeatOil',
    'HeatPropane', 'Designed_HeatPropane',
    'HeatWood', 'Designed_HeatWood',

    # --- heat loss: total (kW, design/peak) + by component (kWh, annual) ---
    'HeatLoss', 'Designed_HeatLoss',
    'HeatLossAir', 'Designed_HeatLossAir',
    'HeatLossRoof', 'Designed_HeatLossRoof',
    'HeatLossWall', 'Designed_HeatLossWall',
    'HeatLossFoundation', 'Designed_HeatLossFoundation',
    'HeatLossFloor', 'Designed_HeatLossFloor',
    'HeatLossWindowDoor', 'Designed_HeatLossWindowDoor',

    # --- GHG per fuel (tonnes/yr) ---
    'GHGElectricity', 'Designed_GHGElectricity',
    'GHGNaturalGas', 'Designed_GHGNaturalGas',
    'GHGOil', 'Designed_GHGOil',
    'GHGPropane', 'Designed_GHGPropane',
    'GHGWood', 'Designed_GHGWood',

    # --- envelope: insulation levels (RSI) + window code ---
    'RoofInsulation', 'Designed_RoofInsulation',
    'WallInsulation', 'Designed_WallInsulation',
    'FoundationInsulation', 'Designed_FoundationInsulation',
    'FloorInsulation', 'Designed_FloorInsulation',
    'WindowCode', 'Designed_WindowCode',

    # --- ventilation ---
    'VentType', 'Designed_VentType',

    # --- heating equipment efficiency ---
    'HeatAFUE', 'Designed_HeatAFUE',
    'HeatSeasonalCOP', 'Designed_HeatSeasonalCOP',

    # --- heat pump specifics ---
    'HPType', 'Designed_HPType',
    'HPCOP', 'Designed_HPCOP',
    'HPEquipType', 'Designed_HPEquipType',
    'CCASHP', 'Designed_CCASHP',
    'CCASHPCapacity', 'Designed_CCASHPCapacity',
    'CCASHPHSPF', 'Designed_CCASHPHSPF',
    'ASHPHSPF', 'Designed_ASHPHSPF',
    'ASHPSEER', 'Designed_ASHPSEER',

    # --- AHRI certificate number ---
    'HPAHRI', 'Designed_HPAHRI',
]

def jval(v, col):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return None
    try:
        if pd.isna(v): return None
    except (TypeError, ValueError):
        pass
    if isinstance(v, (np.bool_, bool)): return bool(v)
    if isinstance(v, (np.integer,)): return int(v)
    if isinstance(v, (np.floating, float)):
        f = float(v)
        return int(f) if f.is_integer() else round(f, 2)
    return v

def split_fsa(df, province, out_root):
    cols = [c for c in FSA_COLS if c in df.columns]
    prov_dir = os.path.join(out_root, province)
    Path(prov_dir).mkdir(parents=True, exist_ok=True)
    index = []
    for fsa, g in df.groupby('FSA'):
        if not fsa or pd.isna(fsa) or str(fsa).strip() == '' or len(str(fsa)) != 3:
            continue
        rows = [[jval(v, c) for c, v in zip(cols, row)]
                for row in g[cols].itertuples(index=False, name=None)]
        with open(os.path.join(prov_dir, f"{fsa}.json"), 'w', encoding='utf-8') as f:
            json.dump({'columns': cols, 'rows': rows}, f, ensure_ascii=False, separators=(',', ':'))
        ers = num(g['ERSRating']); tier = num(g['Tier']); ach = num(g['AirLeakage'])
        index.append({
            'fsa': fsa, 'row_count': len(rows),
            'median_ers': round(median(ers[ers > 0]), 1) if median(ers[ers > 0]) is not None else None,
            'median_tier': round(median(tier), 1) if median(tier) is not None else None,
            'median_ach': round(median(ach), 2) if median(ach) is not None else None,
        })
    index.sort(key=lambda d: d['fsa'])
    with open(os.path.join(prov_dir, '_index.json'), 'w', encoding='utf-8') as f:
        json.dump(index, f, ensure_ascii=False, indent=2)
    print(f"  {province}: {len(index)} FSA files")


def main():
    parquets = sorted(glob.glob(os.path.join(OUTPUT_DIR, "nc_*.parquet")))
    if not parquets:
        print(f"!! no parquets in {OUTPUT_DIR}"); return

    print("=== province_json + fsa_json ===")
    ca_frames = []
    for pq in parquets:
        province = Path(pq).stem.replace('nc_', '')
        df = null_ers_placeholders(pd.read_parquet(pq))
        build_province_json(df, province, PROVINCE_JSON_DIR)
        split_fsa(df, province, FSA_JSON_DIR)
        ca_frames.append(df)

    print("=== CA aggregate ===")
    ca = pd.concat(ca_frames, ignore_index=True)
    payload = {'province': 'CA', 'total_rows': len(ca),
               'by_type': {'All types': compute_slice(ca)}}
    with open(os.path.join(PROVINCE_JSON_DIR, 'CA.json'), 'w', encoding='utf-8') as f:
        json.dump(payload, f, ensure_ascii=False, separators=(',', ':'))
    print(f"  CA: {len(ca):,} rows -> {os.path.getsize(os.path.join(PROVINCE_JSON_DIR,'CA.json'))/1024:.0f} KB")
    print("done.")


if __name__ == '__main__':
    main()
