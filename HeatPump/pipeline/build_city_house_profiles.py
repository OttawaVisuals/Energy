"""
Per-house design load, annual heating energy, and balance point (0-heat
point) for every ERS home in each heatpump.html dropdown city -- ships the
FULL population per city (no sampling), for a page section that lets a
user filter by house category and see the worst/best/representative homes
within the filtered set.

COOLING SIDE ADDED 2026-08-31 (input to the "potential AC" scenario)
---------------------------------------------------------------------
Same population, same method, mirrored for cooling. This replaces the
inferred-prevalence approach in Python/heatpump_cooling_calibration.py
(Phase 0: backs out AC prevalence from NRCan CEUD + an assumed SEER) with
real per-house ERS fields: `ERSDesCoolLoss` (design/peak cooling load, W)
and `ERSSPACECOOLENERGY` (annual cooling energy, MJ) are recorded directly
on the audit, the same way `EGHDESHTLOSS`/`Pre_HeatEnergy` are on the
heating side -- no calibration needed.

Method, exactly mirrored from the heating solve below:
  UA_cool  = ERSDesCoolLoss / (design_cooling_db_C - ThermostatCooling)
  CDH(Tc)  = sum over TMY hours of max(T_hour - Tc, 0)   [[cooling]] degree-
             hours -- monotonically DEcreasing in Tc (opposite direction
             from heating's DDH, which increases in T0), computed once per
             city on a fine Tc grid, then every house's balance point is a
             single vectorized `np.interp` against its own target
             CDH = annual_cool_kWh / UA_cool.

`design_cooling_db_C` (NBC design cooling dry-bulb per weather station) is
already sitting unused in `reference/nbc_station_design_temps.csv` --
`build_city_design_temps.py` only ever read the heating column from it.
Rather than touch that script's output for one extra field, this script
re-derives the city's cooling design temperature itself: it reuses the
same `houseid_city.parquet` cache (HOUSEID -> WEATHERLOC) that script
built, joins each home in THIS script's own FSA-defined city population to
its station's `design_cooling_db_C`, and takes the plain mean over that
population. This is deliberately a different (FSA-based) population from
`city_design_temps.json`'s (CLIENTCITY-text-based) one, so the two city
design temperatures are not expected to match to the decimal -- both are
house-weighted means of the same underlying NBC station table, just over
slightly different city membership rules.

INDOOR ANCHOR -- CONFIRMED FIXED, NOT AUDITED (2026-08-31): `ThermostatCooling`
looked at first like a real per-house field (44.7% ERS fill implied it might
vary the way an audited setting would). It does not: checked against the raw
cache, all 620,107 non-null values across the entire matched-pair universe
are exactly **25.0 C, zero variance**. The data dictionary's own description
("based on standard operating conditions") says the same thing directly.
So `ThermostatCooling` is a HOT2000 program constant, structurally identical
to the heating side's fixed 21 C indoor design setpoint (see "UA from design
heat loss" in METHODOLOGY.md) -- NOT an assumption stood in for a missing
constant, as this docstring originally (incorrectly) described it. UA_cool's
denominator is therefore just as fixed as UA_heat's; the 44.7% fill only says
how often HOT2000 computed the standard-operating-conditions cooling block at
all (tracks whether a cooling system existed to size), not how often a
homeowner's setpoint was captured.

CONSEQUENCE FOR THE CHART: because every home shares the same 25 C anchor,
solved balance points clustering tightly (22-24 C almost everywhere,
regardless of a city's design temperature) is a partly MECHANICAL result of
that shared constant, not solely a finding about real cooling behaviour --
same as how heating balance points across a city are shaped by sharing one
fixed 21 C anchor. The within-city SPREAD (worst vs. best homes) still comes
from real per-house ERSDesCoolLoss/ERSSPACECOOLENERGY variation and remains
informative; the near-identical MEDIAN across climates should not be read as
a surprising cross-climate behavioural finding.

`ERSDesCoolLoss`/`ERSSPACECOOLENERGY`/`ThermostatCooling`/`AIRCOP` are not in
the shipped `ers_web_<PROV>.parquet` (same gap as the AHRI/HP fields -- see
memory ers-heatpump-fields), so they're pulled from the raw `C:\\ERS\\*.csv`
once and cached to `data/interim/houseid_cooling.parquet`, restricted to
the same matched-pair universe `build_city_design_temps.py` uses.

CONSUMED vs. DELIVERED COOLING ENERGY (fixed 2026-08-31, found while
cross-checking correlations with Simon): `ERSSPACECOOLENERGY` is, per its
own dictionary description ("Energy Consumption"), electricity CONSUMED by
the AC unit -- the cooling-side twin of `Pre_HeatEnergy`/`EGHFURNACEAEC`,
not a delivered/thermal quantity. Using it directly against `ERSDesCoolLoss`
(a thermal peak load, same category as `EGHDESHTLOSS`) mixed bases exactly
the way an early, uncorrected version of the heating solve would have.
`AIRCOP` ("Coefficient of performance for A/C system") fixes this: 94.2%
overall fill, and confirmed **100% fill among homes that actually consume
cooling energy** (`ERSSPACECOOLENERGY > 0`) in this matched-pair universe --
essentially no gap. It is a real per-unit value (not a constant like
`ThermostatCooling`): correctly 0 wherever `AIRCONDTYPE == 'Not installed'`,
and a plausible, varying 2.5-3.7ish range for real AC types. So, exactly
mirroring `Pre_HeatDelivered = Pre_HeatEnergy * Pre_HeatSeasonalCOP/100`:

    cool_delivered_kWh = (ERSSPACECOOLENERGY / 3.6) * AIRCOP

`annual_cool_energy_kWh` in this script's output is this delivered figure,
not raw consumption -- consistent with the heating column's basis. This
also fixes the balance-point solve itself: `target_cdh = annual_cool_kWh /
UA_cool` now divides a thermal energy by a thermal UA on both sides, where
before it divided a thermal UA into an electrical consumption figure,
silently overweighting the influence of low-COP units on the solved Tc.

Cooling rows are attached to the SAME heating-solved population ("ok"
below) rather than a separately screened set, so each house in the output
carries both a heating and a cooling profile where both solve -- the
gating population, and every additional cooling-specific drop (missing
fields, implausible thermostat, energy outside the solvable range), is
counted and reported per city, never silently dropped.

POTENTIAL AC SCENARIO added 2026-08-31 (folded in alongside the real
cooling solve, at Simon's request): the real cooling fields above only
solve for 20-40% of a city's heating-solved homes (higher in ON/AB, lower
in BC/NS) -- coverage tracks whether ERSDesCoolLoss/ERSSPACECOOLENERGY
were ever computed for that audit, not necessarily AC ownership (see
memory ers-heatpump-fields-style investigation, 2026-08-31 session). For
the remaining homes -- including every home with NO installed AC at all,
which is the actual population a "what would adding AC cost/emit" scenario
needs -- there is no real cooling data to solve from. Two correlations,
found and confirmed this session, let every heating-solved home get an
ESTIMATED cooling profile instead, with no separate AC-sizing dropdown:

1. Peak heat loss correlates with peak cool loss, r=0.683 (R^2=0.467,
   n=209,272 homes with both fields, pooled across all 14 cities;
   per-city range 0.54-0.87). Both are driven by the same envelope (UA,
   floor area), so this is a real physical relationship, not noise.
   Linear fit: cool_peak_kW = 0.2789 * heat_peak_kW + 1.3254.
2. Peak cool loss correlates with annual cool energy MUCH more strongly
   than annual heat and annual cool energy correlate with each other
   (r=0.778, R^2=0.605 pooled here, vs. only r~0.2-0.25 for the
   heat-energy-vs-cool-energy comparison -- annual energy is dominated by
   climate-hours and occupant behaviour, which heating and cooling don't
   share, but PEAK load in both is dominated by the shared envelope).
   Used as a through-origin ratio (median, more robust to a few outlier
   high-COP low-ambient-cooling homes than the pooled linear fit's
   intercept term): annual_cool_kWh = 838.3 * cool_peak_kW.

Method: cool_peak_est_kW from (1) applied to the home's OWN Pre_HeatLoss;
cool_energy_est_kWh from (2) applied to that estimated peak; then the
IDENTICAL CDH-inversion solve already built for the real cooling data
(same tc_grid/cdh_grid, same fixed 25C indoor anchor) finds a
balance_point_Tc_est_C. This reuses the real solve's machinery end to end
-- the only substitution is where the peak and energy numbers come from.

FLAGGED, NOT HIDDEN: this is now two levels removed from measurement --
a correlation-estimated peak, run through a ratio-estimated energy, run
through the same balance-point inversion used for real data. Do not present
`_est` fields with the same confidence as the real `design_cool_loss_kW` /
`annual_cool_energy_kWh` / `balance_point_Tc_C` columns -- they are
carried as separately named columns for exactly this reason, and both sets
are shipped side by side (real fields null where unsolved; `_est` fields
populated for every heating-solved home except where the estimated energy
itself falls outside the city's solvable CDH range).

WHY THIS EXISTS
----------------
Follow-up on check_balance_point_k1s.py (single FSA, K1S) and
build_city_fsa_list.py (clean per-city FSA lists via Canada Post). User
wants, per city: every home's peak load (kW) + annual heating energy (kWh)
+ implied balance point, tagged with type/size/vintage/storeys, shipped to
the page so worst/best/representative selection can run client-side on
whatever subset the user's filters narrow down to.

CONSUMED vs. DELIVERED ENERGY (fixed 2026-08-11 -- see below)
----------------------------------------------------------------
Pre_HeatEnergy (EGHFURNACEAEC) is fuel/electricity CONSUMED by the primary
heating system, not heat DELIVERED to the building -- those only match for
electric-resistance heat (COP 1). The first version of this script used
Pre_HeatEnergy directly, which is thermally inconsistent with Pre_HeatLoss
(a delivered-heat quantity) for any home whose pre-retrofit system already
has a COP or AFUE away from 1. Caught when an Ottawa home with a
pre-retrofit ground-source heat pump (Pre_HPCOP 3.0) ranked as the city's
"best" home purely because its 10,587 kWh consumed looked tiny next to its
19.1 kW peak -- the model-implied heat actually delivered is ~3x that.
Fixed using the exact conversion already validated in build_archetypes.py:
`Pre_HeatDelivered = Pre_HeatEnergy * (Pre_HeatSeasonalCOP / 100)`
(EGHFURSEASEFF: an AFUE-style seasonal efficiency percentage for combustion
equipment, and >100 for heat pumps), screened to the same plausible 30-400
range that script uses. Below 30 is missing/junk data; above 400 is a
mis-scaled record. All balance-point solving and the annual-energy field
shipped to the page now use Pre_HeatDelivered, not raw Pre_HeatEnergy.

METHOD -- vectorized balance-point solve
------------------------------------------
A per-house scipy.brentq loop (as in check_balance_point_k1s.py) does not
scale to ~800k homes across 14 cities in reasonable time. Reformulated so
an entire city solves in one vectorized pass:
  DDH(T0) = sum over TMY hours of max(T0 - T_hour, 0)      [degree-hours]
  UA      = HeatLoss(design) / (T_INDOOR - T_design)          [kW/C, per house]
  predicted annual energy = UA * DDH(T0) = HeatLoss(design) * DDH(T0) / (T_INDOOR - T_design)

T_INDOOR = 21 C, fixed -- the program default indoor setpoint EGHDESHTLOSS
is actually computed at (METHODOLOGY.md "UA from design heat loss --
indoor/outdoor design temperature"), NOT the balance point being solved
for. DDH(T0) depends only on the city's own TMY, not on any one house --
computed ONCE per city on a fine T0 grid (monotonic increasing in T0 by
construction), then every house's balance point is a single vectorized
`np.interp` against its own target DDH = HeatEnergy / HeatLoss * (T_INDOOR
- T_design). A house whose target falls outside the grid's DDH range is
unsolvable in this no-gains model (implausible energy for its design load)
-- reported per city, not silently dropped.

FIXED 2026-08-12 (was: `h(T0) = DDH(T0) / (T0 - T_design)`, anchoring UA on
the unknown T0 itself instead of the fixed 21 C indoor setpoint). Because
T0 < 21 C always, that anchor inflated UA and biased every solved T0 low by
3-4 C on a 10-home Toronto sample -- worse for higher-loss homes, which is
why the "worst house" balance points looked implausibly cold. The old
`h(T0)` also had a spurious non-monotonic dip just above T_design that
needed a monotonic-branch workaround; that dip was itself an artifact of
the wrong anchor and is gone under the fixed formula (DDH(T0) is
monotonic by construction, since raising T0 can only add positive terms to
the degree-hour sum). See METHODOLOGY.md "Real-homes balance-point fix
(2026-08-12)".

Toronto (289,656 homes, largest dropdown city) solves end-to-end in ~5s.

WORST/BEST SELECTION (documented here; computed client-side, not baked in)
-----------------------------------------------------------------------------
Peak load and annual energy correlate strongly across a city (Pearson
r=0.89 for Toronto) but NOT perfectly -- the single highest-peak home is
not the single highest-energy home (confirmed: Toronto's top-peak house is
at the 100th energy percentile but isn't literally the max). So "worst" is
defined as the home maximizing min(peak_percentile, energy_percentile) --
bad on BOTH axes simultaneously, not just one -- and "best" as the home
minimizing max(peak_percentile, energy_percentile). Percentiles are
recomputed within whatever filtered subset the page's dropdowns select, so
this file ships raw values only; no worst/best is precomputed here.
Outlier guard (confirmed with user 2026-08-11): a literal min/max of that
score picked up at least one implausible row (a 288.7 m^2 Toronto detached
home somehow at 189.8 kW design loss, ~0.66 kW/m^2 -- 4-10x a normal
detached home's 0.05-0.15 kW/m^2 range, almost certainly a data-entry
error). The page must therefore treat "worst"/"best" as the 99th/1st
percentile of that combined score within the filtered subset, not the
literal extreme, so one bad ERS row can't stretch the displayed range.

CATEGORIES (from ERS fields already in ers_web_<PROV>.parquet)
----------------------------------------------------------------
BldgType   -> canonical: detached / semi_duplex / row_end / row_middle /
              apartment / mobile / triplex (source has case-duplicated and
              near-duplicate labels, e.g. "Single detached" vs "Single
              Detached" -- folded together, see BLDGTYPE_MAP)
Storeys    -> canonical: 1 / 1.5 / 2 / 2.5 / 3 / split / split_entry
YearBuilt  -> decade bucket (pre-1946 pooled as "pre1946")
FloorArea  -> kept as the raw m^2 value -- size buckets are a page-side
              filter choice, not baked into the data

INPUT:  HeatPump/data/processed/city_fsa_list.json
        C:\\ERS\\web\\ers_web_<PROV>.parquet
        HeatPump/data/processed/city_design_temps.json
        HeatPump/data/processed/tmy_temps.json
OUTPUT: HeatPump/data/processed/house_profiles_<city_slug>.json, one per city
        printed per-city solve stats + size report (raw + gzip), and a
        combined total across all 14 cities

LIMITATIONS
-----------
- Pre-retrofit (Pre_HeatLoss / Pre_HeatEnergy) only, same as
  check_balance_point_k1s.py -- the home's ORIGINAL condition, not any
  retrofit outcome.
- balance_point_T0_C inherits check_balance_point_k1s.py's caveat: a
  no-gains straight-line model, so T0 is an "effective" balance point
  absorbing real internal/solar gains, occupant behaviour and TMY-vs-actual-
  year weather deviation, not a physical measurement.
- City design temp is a single city-wide constant (house-weighted mean over
  real ERS homes' own weather stations), not a per-house station join.
"""
from __future__ import annotations

import glob
import gzip
import json
import os
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "processed"
INTERIM = ROOT / "data" / "interim"
OUT_DIR = ROOT / "data" / "processed"
ERS_WEB_DIR = Path(r"C:\ERS\web")

# -- cooling addition --
NBC_CSV = ROOT / "reference" / "nbc_station_design_temps.csv"
HOUSEID_CITY_CACHE = INTERIM / "houseid_city.parquet"  # built by build_city_design_temps.py
COOLING_CACHE = INTERIM / "houseid_cooling.parquet"
ERS_RAW_GLOB = r"C:\ERS\*.csv"
ERS_WEB_GLOB = r"C:\ERS\web\ers_web_*.parquet"
COOL_CHUNK = 250_000
COOL_WANT = ["HOUSEID", "ERSDesCoolLoss", "ERSSPACECOOLENERGY", "ThermostatCooling", "AIRCOP"]
TC_GRID_MIN_C = 0.0  # floor for the cooling balance-point search grid
THERMOSTAT_COOLING_RANGE = (15.0, 30.0)  # plausibility screen, degrees C

# -- potential-AC scenario (estimated cooling for homes with no real cooling
# data) -- see module docstring "POTENTIAL AC SCENARIO" for the correlation
# analysis these came from (n=209,272 ERS homes with both real fields, 2026-08-31)
HEAT_TO_COOL_PEAK_SLOPE = 0.2789        # cool_peak_kW = SLOPE*heat_peak_kW + INTERCEPT
HEAT_TO_COOL_PEAK_INTERCEPT = 1.3254    # pooled linear fit, r=0.683, R^2=0.467
COOL_RATIO_KWH_PER_KW = 838.3           # median annual_cool_kWh / design_cool_loss_kW
                                         # (through-origin ratio, r=0.778, R^2=0.605 pooled)
COOL_INDOOR_ANCHOR_C = 25.0             # ThermostatCooling: confirmed fixed HOT2000
                                         # constant, hardcoded here since the real field
                                         # is absent on exactly the homes this estimate
                                         # is for (no real cooling data at all)

CITY_PROV = {
    "Ottawa": "ON", "Toronto": "ON", "Hamilton": "ON", "London": "ON", "Windsor": "ON",
    "Montreal": "QC", "Quebec City": "QC",
    "Calgary": "AB", "Edmonton": "AB",
    "Vancouver": "BC", "Winnipeg": "MB", "Halifax": "NS",
    "Saskatoon": "SK", "Regina": "SK",
}
CITY_TO_DESIGNTEMP_KEY = {"Ottawa": "Ottawa-Gatineau"}  # everything else matches verbatim
T0_MAX = 30.0
T_INDOOR = 21.0  # HOT2000 default indoor design setpoint EGHDESHTLOSS is computed
                  # at -- fixed UA anchor, see METHODOLOGY.md "UA from design heat
                  # loss -- indoor/outdoor design temperature"

BLDGTYPE_MAP = {
    "single detached": "detached",
    "double/semi-detached": "semi_duplex",
    "double/semi detached": "semi_duplex",
    "detached duplex": "semi_duplex",
    "attached duplex": "semi_duplex",
    "duplex (non-murb)": "semi_duplex",
    "row house, end unit": "row_end",
    "row, end unit": "row_end",
    "row house, middle unit": "row_middle",
    "row, middle unit": "row_middle",
    "apartment": "apartment",
    "apartment row": "apartment",
    "mobile home": "mobile",
    "detached triplex": "triplex",
    "attached triplex": "triplex",
    "triplex (non-murb)": "triplex",
}
STOREYS_MAP = {
    "one storey": "1",
    "one and a half": "1.5",
    "two storeys": "2",
    "two and a half": "2.5",
    "three storeys": "3",
    "split level": "split",
    "split entry / raised basement": "split_entry",
    "split entry/raised base.": "split_entry",
}


def load_json(name):
    return json.loads((DATA / name).read_text(encoding="utf-8"))


def fold_lookup(series, mapping, label):
    low = series.str.strip().str.lower()
    mapped = low.map(mapping)
    unmapped = series[mapped.isna()].unique()
    if len(unmapped):
        print(f"  [unmapped {label}] {list(unmapped)[:10]}")
    return mapped.fillna("other")


def build_cooling_universe():
    """Every HOUSEID in the matched-pair web parquets -- same universe
    build_city_design_temps.py's houseid_city.parquet was built over."""
    universe = set()
    for p in sorted(glob.glob(ERS_WEB_GLOB)):
        universe |= set(pd.read_parquet(p, columns=["HOUSEID"])["HOUSEID"].astype(str))
    return universe


def build_cooling_cache():
    """HOUSEID -> (ERSDesCoolLoss, ERSSPACECOOLENERGY, ThermostatCooling).
    Cached; the 7.7 GB raw scan runs once, same pattern as
    build_city_design_temps.py's houseid_city.parquet."""
    if COOLING_CACHE.exists():
        print(f"reusing {COOLING_CACHE}")
        return pd.read_parquet(COOLING_CACHE)

    universe = build_cooling_universe()
    print(f"cooling cache universe: {len(universe):,} matched-pair HOUSEIDs", flush=True)

    seen, frames, skipped = set(), [], []
    for path in sorted(glob.glob(ERS_RAW_GLOB)):
        name = os.path.basename(path)
        head = pd.read_csv(path, encoding="utf-8-sig", nrows=0, low_memory=False)
        cols = [c for c in COOL_WANT if c in head.columns]
        if "HOUSEID" not in cols:
            skipped.append(name)
            print(f"{name}: MISSING HOUSEID -- skipped", flush=True)
            continue
        for chunk in pd.read_csv(path, encoding="utf-8-sig", usecols=cols,
                                 dtype=str, chunksize=COOL_CHUNK, low_memory=False):
            chunk = chunk[chunk["HOUSEID"].isin(universe) & ~chunk["HOUSEID"].isin(seen)]
            chunk = chunk.drop_duplicates("HOUSEID")
            if chunk.empty:
                continue
            frames.append(chunk)
            seen |= set(chunk["HOUSEID"])
        print(f"{name}: cumulative {len(seen):,}", flush=True)

    out = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=COOL_WANT)
    COOLING_CACHE.parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(COOLING_CACHE, index=False)
    print(f"wrote {COOLING_CACHE} ({len(out):,} rows); "
          f"matched {len(seen):,}/{len(universe):,} "
          f"({len(seen)/len(universe)*100:.1f}%)")
    if skipped:
        print(f"year files skipped (no HOUSEID column): {skipped}")
    return out


def load_cooling_design_map():
    """WEATHERLOC -> NBC design_cooling_db_C, plus the houseid_city cache
    (HOUSEID -> WEATHERLOC) build_city_design_temps.py already built."""
    if not HOUSEID_CITY_CACHE.exists():
        raise FileNotFoundError(
            f"{HOUSEID_CITY_CACHE} not found -- run build_city_design_temps.py "
            "first, it builds this HOUSEID->WEATHERLOC cache.")
    houseid_city = pd.read_parquet(HOUSEID_CITY_CACHE, columns=["HOUSEID", "WEATHERLOC"])
    nbc = pd.read_csv(NBC_CSV)
    cool_design = dict(zip(nbc["WEATHERLOC"], nbc["design_cooling_db_C"]))
    return houseid_city, cool_design


def process_city(city, ers_cache, houseid_city_df, cool_design_map, cooling_df):
    prov = CITY_PROV[city]
    fsa_list = load_json("city_fsa_list.json")["cities"][city]
    fsas = {r["fsa"] for r in fsa_list}

    design_temps = load_json("city_design_temps.json")["cities"]
    designtemp_key = CITY_TO_DESIGNTEMP_KEY.get(city, city)
    t_design = design_temps[designtemp_key]["design_temp_C"]

    tmy_all = load_json("tmy_temps.json")
    tmy = np.array(tmy_all[city], dtype=float)

    print(f"\n=== {city} ({prov}) === {len(fsas)} FSAs, design temp {t_design:.1f}C")

    if prov not in ers_cache:
        cols = ["HOUSEID", "FSA", "YearBuilt", "FloorArea", "BldgType", "Storeys",
                "Pre_HeatLoss", "Pre_HeatEnergy", "Pre_HeatSeasonalCOP"]
        ers_cache[prov] = pd.read_parquet(ERS_WEB_DIR / f"ers_web_{prov}.parquet", columns=cols)
    df = ers_cache[prov]
    sub = df[df["FSA"].isin(fsas)].copy()
    n_city = len(sub)
    print(f"{n_city:,} ERS homes in {city}'s FSAs")

    sub["Pre_HeatLoss"] = pd.to_numeric(sub["Pre_HeatLoss"], errors="coerce")
    sub["Pre_HeatEnergy"] = pd.to_numeric(sub["Pre_HeatEnergy"], errors="coerce")
    sub["Pre_HeatSeasonalCOP"] = pd.to_numeric(sub["Pre_HeatSeasonalCOP"], errors="coerce")
    sub["FloorArea"] = pd.to_numeric(sub["FloorArea"], errors="coerce")

    # Pre_HeatEnergy (EGHFURNACEAEC) is fuel/electricity CONSUMED by the primary
    # heating system, not heat delivered -- for a home whose pre-retrofit system
    # is itself a heat pump (Pre_HeatSeasonalCOP well above 100), treating
    # consumed kWh as delivered kWh understates its true thermal load and can
    # make an ordinary envelope look like the most efficient home in the city
    # (confirmed 2026-08-11 on an Ottawa GSHP home, Pre_HPCOP 3.0: consumed
    # 10,587 kWh read as "best in the city" by peak+energy, when the model-
    # implied delivered figure is closer to 3x that). Same conversion already
    # validated in build_archetypes.py: delivered = consumed x (seasonal
    # efficiency / 100). Screened to the same plausible range (30-400) that
    # script uses -- below is missing/junk, above is a mis-scaled record.
    n_before_cop_screen = len(sub)
    sub = sub[sub["Pre_HeatSeasonalCOP"].between(30, 400)]
    n_dropped_bad_cop = n_before_cop_screen - len(sub)
    sub["Pre_HeatDelivered"] = sub["Pre_HeatEnergy"] * (sub["Pre_HeatSeasonalCOP"] / 100.0)

    valid = sub[(sub["Pre_HeatLoss"] > 0) & (sub["Pre_HeatDelivered"] > 0) & (sub["FloorArea"] > 0)].copy()
    n_dropped_invalid = n_city - n_dropped_bad_cop - len(valid)
    print(f"dropped (no plausible seasonal efficiency, 30-400%): {n_dropped_bad_cop:,}")

    grid = np.arange(t_design + 0.02, T0_MAX, 0.02)
    ddh_grid = np.clip(grid[:, None] - tmy[None, :], 0, None).sum(axis=1)
    assert np.all(np.diff(ddh_grid) >= -1e-9), f"{city}: DDH(T0) not monotonic"
    ddh_min, ddh_max = ddh_grid[0], ddh_grid[-1]

    denom = T_INDOOR - t_design
    # target DDH(T0) implied by each house's own UA (fixed at the 21C anchor,
    # not at T0) and observed delivered energy
    target_ddh = (valid["Pre_HeatDelivered"].values / valid["Pre_HeatLoss"].values) * denom
    too_low = target_ddh < ddh_min
    too_high = target_ddh > ddh_max
    solvable = ~too_low & ~too_high

    t0 = np.full(len(valid), np.nan)
    t0[solvable] = np.interp(target_ddh[solvable], ddh_grid, grid)
    valid["T0"] = t0

    n_too_low = int(too_low.sum())
    n_too_high = int(too_high.sum())
    ok = valid[solvable].copy()

    print(f"dropped (missing/nonpositive fields): {n_dropped_invalid:,}")
    print(f"energy too low for the model (target DDH < {ddh_min:.1f}): {n_too_low:,}")
    print(f"energy too high for the model (target DDH > {ddh_max:.1f}): {n_too_high:,}")
    print(f"solved: {len(ok):,} ({100*len(ok)/n_city:.1f}% of {city}'s ERS homes)")

    # ---- cooling: mirrors the heating solve above, see module docstring ----
    ok = ok.merge(houseid_city_df, on="HOUSEID", how="left")
    ok["design_cool_C"] = ok["WEATHERLOC"].map(cool_design_map)
    n_no_cool_station = int(ok["design_cool_C"].isna().sum())
    cool_design_city = ok["design_cool_C"].mean()

    ok = ok.merge(cooling_df, on="HOUSEID", how="left")
    ok["ERSDesCoolLoss"] = pd.to_numeric(ok["ERSDesCoolLoss"], errors="coerce")
    ok["ERSSPACECOOLENERGY"] = pd.to_numeric(ok["ERSSPACECOOLENERGY"], errors="coerce")
    ok["ThermostatCooling"] = pd.to_numeric(ok["ThermostatCooling"], errors="coerce")
    ok["AIRCOP"] = pd.to_numeric(ok["AIRCOP"], errors="coerce")
    # delivered thermal cooling, matching Pre_HeatDelivered's basis -- see
    # module docstring "CONSUMED vs. DELIVERED COOLING ENERGY"
    ok["cool_delivered_kWh"] = (ok["ERSSPACECOOLENERGY"] / 3.6) * ok["AIRCOP"]

    if pd.isna(cool_design_city):
        print(f"cooling: SKIPPED -- no home in {city} matched an NBC cooling-design station")
        cool_design_city = float("nan")
        ok["design_cool_loss_kW"] = np.nan
        ok["annual_cool_energy_kWh"] = np.nan
        ok["balance_point_Tc_C"] = np.nan
        ok["cool_peak_est_kW"] = np.nan
        ok["cool_energy_est_kWh"] = np.nan
        ok["balance_point_Tc_est_C"] = np.nan
        n_dropped_cool_missing = n_cool_too_low = n_cool_too_high = n_cool_solved = 0
        n_est_too_low = n_est_too_high = n_est_solved = 0
    else:
        cool_design_city = float(cool_design_city)
        cool_ok_mask = (
            (ok["ERSDesCoolLoss"] > 0) & (ok["ERSSPACECOOLENERGY"] > 0)
            & (ok["AIRCOP"] > 0)
            & ok["ThermostatCooling"].between(*THERMOSTAT_COOLING_RANGE)
            & ok["design_cool_C"].notna()
            & (ok["design_cool_C"] > ok["ThermostatCooling"])
        )
        n_dropped_cool_missing = int((~cool_ok_mask).sum())

        tc_grid = np.arange(TC_GRID_MIN_C, cool_design_city - 0.02, 0.02)
        cdh_grid = np.clip(tmy[None, :] - tc_grid[:, None], 0, None).sum(axis=1)
        assert np.all(np.diff(cdh_grid) <= 1e-9), f"{city}: CDH(Tc) not monotonic"
        xp, fp = cdh_grid[::-1], tc_grid[::-1]  # CDH falls as Tc rises -- flip to ascending x for np.interp
        cdh_min, cdh_max = cdh_grid[-1], cdh_grid[0]

        ua_cool = ok["ERSDesCoolLoss"] / 1000.0 / (ok["design_cool_C"] - ok["ThermostatCooling"])
        annual_cool_kwh = ok["cool_delivered_kWh"]
        target_cdh = annual_cool_kwh / ua_cool

        cool_too_low = cool_ok_mask & (target_cdh < cdh_min)
        cool_too_high = cool_ok_mask & (target_cdh > cdh_max)
        cool_solvable = cool_ok_mask & ~cool_too_low & ~cool_too_high

        tc = np.full(len(ok), np.nan)
        tc[cool_solvable.values] = np.interp(target_cdh[cool_solvable].values, xp, fp)
        ok["balance_point_Tc_C"] = tc
        ok["design_cool_loss_kW"] = np.where(cool_ok_mask, ok["ERSDesCoolLoss"] / 1000.0, np.nan)
        ok["annual_cool_energy_kWh"] = np.where(cool_ok_mask, annual_cool_kwh, np.nan)

        n_cool_too_low = int(cool_too_low.sum())
        n_cool_too_high = int(cool_too_high.sum())
        n_cool_solved = int(cool_solvable.sum())
        print(f"cooling: city design cooling temp {cool_design_city:.1f}C "
              f"({n_no_cool_station:,} homes with no NBC cooling-station match, excluded from that mean)")
        print(f"cooling: dropped (missing/implausible ERSDesCoolLoss, "
              f"ERSSPACECOOLENERGY, AIRCOP or ThermostatCooling): {n_dropped_cool_missing:,}")
        print(f"cooling: energy too low for the model (target CDH < {cdh_min:.1f}): {n_cool_too_low:,}")
        print(f"cooling: energy too high for the model (target CDH > {cdh_max:.1f}): {n_cool_too_high:,}")
        print(f"cooling: solved: {n_cool_solved:,} "
              f"({100*n_cool_solved/len(ok):.1f}% of {city}'s heating-solved homes)")

        # ---- potential-AC scenario: estimate a cooling profile for EVERY
        # heating-solved home, no real cooling data needed -- see module
        # docstring "POTENTIAL AC SCENARIO". Reuses this same tc_grid/cdh_grid.
        cool_peak_est = np.maximum(
            HEAT_TO_COOL_PEAK_SLOPE * ok["Pre_HeatLoss"].values + HEAT_TO_COOL_PEAK_INTERCEPT, 0.0)
        cool_energy_est = COOL_RATIO_KWH_PER_KW * cool_peak_est
        ua_cool_est = cool_peak_est / (cool_design_city - COOL_INDOOR_ANCHOR_C)
        target_cdh_est = cool_energy_est / ua_cool_est

        est_too_low = target_cdh_est < cdh_min
        est_too_high = target_cdh_est > cdh_max
        est_solvable = ~est_too_low & ~est_too_high

        tc_est = np.full(len(ok), np.nan)
        tc_est[est_solvable] = np.interp(target_cdh_est[est_solvable], xp, fp)

        ok["cool_peak_est_kW"] = cool_peak_est
        ok["cool_energy_est_kWh"] = np.where(est_solvable, cool_energy_est, np.nan)
        ok["balance_point_Tc_est_C"] = tc_est

        n_est_too_low = int(est_too_low.sum())
        n_est_too_high = int(est_too_high.sum())
        n_est_solved = int(est_solvable.sum())
        print(f"cooling (potential-AC estimate, from heat peak + ratio): solved "
              f"{n_est_solved:,} ({100*n_est_solved/len(ok):.1f}% of {city}'s "
              f"heating-solved homes); too_low={n_est_too_low:,} too_high={n_est_too_high:,}")

    ok["bldg_code"] = fold_lookup(ok["BldgType"], BLDGTYPE_MAP, "BldgType")
    ok["storeys_code"] = fold_lookup(ok["Storeys"], STOREYS_MAP, "Storeys")
    ok["decade"] = pd.to_numeric(ok["YearBuilt"], errors="coerce").apply(
        lambda y: "pre1946" if pd.notna(y) and y < 1946 else (int(y // 10 * 10) if pd.notna(y) else None)
    )

    BLDG_CODES = sorted(ok["bldg_code"].unique())
    STOREYS_CODES = sorted(ok["storeys_code"].unique())
    bldg_idx = {c: i for i, c in enumerate(BLDG_CODES)}
    storeys_idx = {c: i for i, c in enumerate(STOREYS_CODES)}

    def n(v):
        return None if pd.isna(v) else round(float(v), 2)

    rows = [
        [
            int(float(r.HOUSEID)),
            bldg_idx[r.bldg_code],
            storeys_idx[r.storeys_code],
            r.decade if r.decade is not None else None,
            round(float(r.FloorArea), 1),
            round(float(r.Pre_HeatLoss), 2),
            round(float(r.Pre_HeatDelivered), 0),
            round(float(r.T0), 2),
            n(r.design_cool_loss_kW),
            n(r.annual_cool_energy_kWh),
            n(r.balance_point_Tc_C),
            n(r.cool_peak_est_kW),
            n(r.cool_energy_est_kWh),
            n(r.balance_point_Tc_est_C),
        ]
        for r in ok.itertuples(index=False)
    ]

    payload = {
        "meta": {
            "city": city, "province": prov, "design_temp_C": t_design,
            "design_cooling_temp_C": None if pd.isna(cool_design_city) else round(cool_design_city, 1),
            "n_homes": len(rows),
            "columns": ["houseid", "bldg_code", "storeys_code", "decade_built",
                        "floor_area_m2", "design_heat_loss_kW", "annual_heat_delivered_kWh",
                        "balance_point_T0_C", "design_cool_loss_kW",
                        "annual_cool_energy_kWh", "balance_point_Tc_C",
                        "cool_peak_est_kW", "cool_energy_est_kWh",
                        "balance_point_Tc_est_C"],
            "bldg_codes": BLDG_CODES,
            "storeys_codes": STOREYS_CODES,
            "method": "no-gains linear load model anchored on Pre_HeatLoss "
                      "(EGHDESHTLOSS, design/peak) and Pre_HeatDelivered "
                      "(EGHFURNACEAEC consumed x EGHFURSEASEFF/100 seasonal "
                      "efficiency, converting consumed to delivered heat); "
                      "UA = Pre_HeatLoss / (21C - T_design), fixed at HOT2000's "
                      "indoor design setpoint, NOT at the solved balance point "
                      "-- see check_balance_point_k1s.py and this script's docstring",
            "n_dropped_bad_efficiency": int(n_dropped_bad_cop),
            "n_dropped_missing_fields": int(n_dropped_invalid),
            "n_dropped_too_low": n_too_low,
            "n_dropped_too_high": n_too_high,
            "cooling_method": "mirrors the heating method above: UA_cool = "
                      "ERSDesCoolLoss / (design_cooling_db_C - ThermostatCooling); "
                      "ThermostatCooling is confirmed a fixed HOT2000 standard-"
                      "operating-condition constant (25.0C, zero variance across "
                      "620,107 non-null records, checked 2026-08-31), structurally "
                      "the same kind of anchor as the heating side's fixed 21C "
                      "indoor design setpoint, not an audited per-house value -- "
                      "see module docstring 'INDOOR ANCHOR'. annual_cool_energy_kWh "
                      "is DELIVERED thermal cooling, not raw consumption: "
                      "(ERSSPACECOOLENERGY/3.6) * AIRCOP, mirroring "
                      "Pre_HeatDelivered's basis exactly -- AIRCOP is a real "
                      "per-unit COP field (100% fill among homes with nonzero "
                      "cooling consumption, checked 2026-08-31), not a guess. "
                      "Cooling fields null where unsolved; null does not imply "
                      "no AC, only that this model could not solve a balance "
                      "point for that house.",
            "n_dropped_cool_missing_or_implausible": n_dropped_cool_missing,
            "n_cool_too_low": n_cool_too_low,
            "n_cool_too_high": n_cool_too_high,
            "n_cool_solved": n_cool_solved,
            "n_cool_no_station_match": n_no_cool_station,
            "cool_estimate_method": "potential-AC scenario, FLAGGED as two levels "
                      "removed from measurement (see module docstring 'POTENTIAL "
                      "AC SCENARIO'): cool_peak_est_kW = 0.2789*Pre_HeatLoss + "
                      "1.3254 (heat-peak-to-cool-peak correlation, r=0.683, "
                      "n=209,272 ERS homes pooled across 14 cities); "
                      "cool_energy_est_kWh = 838.3*cool_peak_est_kW (through-origin "
                      "ratio, r=0.778); balance_point_Tc_est_C solved by the SAME "
                      "CDH inversion as the real balance_point_Tc_C, just fed these "
                      "estimated peak/energy numbers instead of "
                      "ERSDesCoolLoss/ERSSPACECOOLENERGY. Computed for every "
                      "heating-solved home (not gated on real cooling data), so "
                      "homes with no AC at all still get a 'what would adding AC "
                      "look like' estimate -- do not treat these fields with the "
                      "same confidence as the real (non-'_est') cooling columns.",
            "n_cool_est_too_low": n_est_too_low,
            "n_cool_est_too_high": n_est_too_high,
            "n_cool_est_solved": n_est_solved,
        },
        "rows": rows,
    }

    slug = city.lower().replace(" ", "_")
    out_path = OUT_DIR / f"house_profiles_{slug}.json"
    text = json.dumps(payload, separators=(",", ":"))
    out_path.write_text(text, encoding="utf-8")
    raw_bytes = len(text.encode("utf-8"))
    gz_bytes = len(gzip.compress(text.encode("utf-8"), compresslevel=9))
    print(f"[out] {out_path.name}: {raw_bytes/1e6:.2f} MB raw, {gz_bytes/1e6:.2f} MB gzip")
    return raw_bytes, gz_bytes, len(rows)


def main():
    t_start = time.time()
    ers_cache = {}
    cooling_df = build_cooling_cache()
    houseid_city_df, cool_design_map = load_cooling_design_map()

    total_raw = total_gz = total_rows = 0
    for city in CITY_PROV:
        raw, gz, n = process_city(city, ers_cache, houseid_city_df, cool_design_map, cooling_df)
        total_raw += raw
        total_gz += gz
        total_rows += n

    print(f"\n=== TOTAL: {total_rows:,} homes across 14 cities ===")
    print(f"combined raw: {total_raw/1e6:.2f} MB   combined gzip: {total_gz/1e6:.2f} MB")
    print(f"elapsed: {time.time()-t_start:.1f}s")


if __name__ == "__main__":
    main()
