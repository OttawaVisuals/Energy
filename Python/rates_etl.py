"""
rates_etl.py

Builds prices_json/ — compact residential energy-price files for the launch
provinces (ON, QC, AB) — from two sources:

1. MaxPr1me/canada-utility-rates: site/data/rates.json committed to that
   repo's main branch by its monthly scrape workflow (cron: 1st of month).
   Full tariff objects with per-charge components; we reduce each launch
   city's residential tariffs to what the Heat Pump tool needs — fixed
   monthly charges, non-energy volumetric adders, and an energy price plan
   (flat / tiered / TOU with a machine-usable calendar). See
   Python/rates_source_notes.md for the scouting report and every reduction
   decision.

2. StatCan table 18-10-0001 (WDS full-table CSV): monthly average retail
   price of household heating fuel (¢/L) by city — the heating-oil price
   canada-utility-rates doesn't carry. Latest non-null month per city, with
   a documented fallback chain (city -> same-province city -> mean of all
   reporting cities).

Reduction rules (documented in meta.json too):
- Only the latest effective_date per (utility, tariff name) is kept.
- component_type == "carbon" rows are EXCLUDED: the federal consumer fuel
  charge was set to zero on 2025-04-01, after the upstream seed data's
  2024-10-01 effective date; QC's cap-and-trade cost is embedded in
  Énergir's commodity price, never a separate line.
- $/GJ -> $/m³ at 0.03798 GJ/m³ (10.55 kWh/m³ HHV — the same constant
  heatpump.html's engine uses; keep them in lockstep).
- $/day fixed charges -> monthly at x 365/12.
- Alberta supplements (both flagged in the output's notes/confidence):
  the upstream exports omit the transmission + local-access volumetric
  charges on AB electricity and the default gas supply (commodity) rate on
  AB gas. Omitting them entirely would bias AB electricity ~15% low and
  make AB gas look nearly free per-m³, so screening-grade constants are
  added (AB_ELEC_TRANSMISSION_EST, AB_GAS_COMMODITY_EST below) with
  confidence downgraded to "low" and the estimate surfaced in notes.

Validation: prints a reconstructed monthly bill for a 1,000 kWh + 200 m³
Ottawa household plus QC/AB sanity bills, and checks each against a
documented plausibility band (see VALIDATION_BANDS). Exits non-zero on any
failure or missing expected tariff, so the scheduled workflow never commits
a partial/garbled pull (same contract as construction_etl.py).

Usage:
    pip install requests pandas
    python rates_etl.py            # uses cached downloads if present
    python rates_etl.py --refresh  # force re-download of both sources
"""

import argparse
import io
import json
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import requests
import pandas as pd

# =============================================================================
# CONFIG
# =============================================================================

REPO_ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = REPO_ROOT / "Python" / "rates_cache"
OUTPUT_DIR = REPO_ROOT / "prices_json"

RATES_URL = ("https://raw.githubusercontent.com/MaxPr1me/canada-utility-rates/"
             "main/site/data/rates.json")

WDS = "https://www150.statcan.gc.ca/t1/wds/rest"
OIL_PID = 18100001  # Monthly average retail prices, gasoline & fuel oil, by city

GJ_PER_M3 = 0.03798        # 10.55 kWh/m3 HHV — matches heatpump.html's engine
DAYS_PER_MONTH = 365 / 12

# --- Alberta screening-grade supplements (see module docstring) --------------
# Residential transmission + local-access volumetric charges, absent from the
# upstream AB distribution tariffs. AUC-approved 2024-25 residential
# transmission charges run ~1.5-2.0 c/kWh (ENMAX D110 / EPCOR D100 schedules).
AB_ELEC_TRANSMISSION_EST = 0.017   # $/kWh
# Default (regulated) gas supply rate, absent from the upstream AB gas
# tariffs. The AUC default rate has ranged ~$1-4/GJ over 2024-26; midpoint.
AB_GAS_COMMODITY_EST = 2.25        # $/GJ

# --- which upstream tariffs feed which city ----------------------------------
# electricity: list of (utility_name, tariff-name substring) to merge; the
# first entry is the "primary" (its plans/source_url/effective_date win).
ELEC_SOURCES = {
    "ottawa":   [("Hydro Ottawa Ltd.", "Residential")],
    "toronto":  [("Toronto Hydro-Electric System Ltd.", "Residential")],
    "montreal": [("Hydro-Québec", "Rate D")],
    "calgary":  [("ENMAX Energy Corporation", "Regulated Rate"),
                 ("ENMAX Power", "Residential Distribution")],
    "edmonton": [("EPCOR Energy Alberta", "Regulated Rate"),
                 ("EPCOR Distribution", "Residential Distribution")],
}
GAS_SOURCES = {
    "ottawa":   ("Enbridge Gas", "Rate 1"),
    "toronto":  ("Enbridge Gas", "Rate 1"),
    "montreal": ("Energir", "Rate D1"),
    "calgary":  ("ATCO Gas", "South"),
    "edmonton": ("ATCO Gas", "North"),
}
CITY_PROVINCE = {"ottawa": "on", "toronto": "on", "montreal": "qc",
                 "calgary": "ab", "edmonton": "ab"}

# 18-10-0001 geography labels (matched by prefix, accents stripped upstream
# of the compare) per city, plus the fallback chain.
OIL_GEO = {
    "ottawa":   "Ottawa",     # "Ottawa–Gatineau, Ontario part..."
    "toronto":  "Toronto",
    "montreal": "Montr",      # Montréal
    "calgary":  "Calgary",
    "edmonton": "Edmonton",
}
OIL_PRODUCT_SUBSTR = "household heating fuel"

# --- OEB price-plan calendars (hardcoded; the upstream tou_hours strings are
# free text). Rules are evaluated in order; first match wins; otherwise
# default_period. Holidays are treated as weekends by consumers that track
# them; treating them as weekdays instead shifts annual cost by well under 1%.
WINTER = [11, 12, 1, 2, 3, 4]
SUMMER = [5, 6, 7, 8, 9, 10]
TOU_CALENDAR = {
    "rules": [
        {"period": "on",  "months": WINTER, "days": "weekday", "hours": [7, 8, 9, 10, 17, 18]},
        {"period": "mid", "months": WINTER, "days": "weekday", "hours": [11, 12, 13, 14, 15, 16]},
        {"period": "on",  "months": SUMMER, "days": "weekday", "hours": [11, 12, 13, 14, 15, 16]},
        {"period": "mid", "months": SUMMER, "days": "weekday", "hours": [7, 8, 9, 10, 17, 18]},
    ],
    "default_period": "off",
}
ULO_CALENDAR = {
    "rules": [
        {"period": "ulo", "days": "all",     "hours": [23, 0, 1, 2, 3, 4, 5, 6]},
        {"period": "on",  "days": "weekday", "hours": [16, 17, 18, 19, 20]},
        {"period": "mid", "days": "weekday", "hours": [7, 8, 9, 10, 11, 12, 13, 14, 15, 21, 22]},
    ],
    "default_period": "off",
}
# OEB tiered thresholds are seasonal; upstream exports only the winter one.
TIERED_SEASONS = {"winter_months": WINTER, "winter_tier1_kwh": 1000,
                  "summer_tier1_kwh": 600}

# --- validation bands (documented plausibility ranges, NOT derived from this
# script's own outputs; sources in rates_source_notes.md §Phase-1 decisions
# and the printout). Each is (lo, hi) in CAD.
VALIDATION_BANDS = {
    # Ottawa 1,000 kWh month on TOU at OEB's typical 63/18/19 off/mid/on split,
    # pre-rebate pre-tax. OEB/Hydro Ottawa bill examples land ~$170-200.
    "ottawa_elec_1000kwh": (160.0, 215.0),
    # Ottawa/Enbridge 200 m3 month, carbon excluded: ~$50 volumetric + ~$28 fixed.
    "ottawa_gas_200m3": (60.0, 95.0),
    # HQ Rate D, 1,500 kWh month (30-day): mostly tier 1 -> ~10-11 c/kWh all-in.
    "montreal_elec_1500kwh": (120.0, 185.0),
    # Calgary 600 kWh month, RRO: published all-in RRO bills 2024-25 ~ 22-33 c/kWh.
    "calgary_elec_600kwh": (130.0, 200.0),
    # Calgary 10 GJ month of gas (~263 m3): fixed-charge dominated.
    "calgary_gas_10gj": (55.0, 95.0),
}


# =============================================================================
# Fetch + cache
# =============================================================================

def fetch_rates_json(refresh=False):
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = CACHE_DIR / "rates.json"
    if not refresh and path.exists() and path.stat().st_size > 0:
        return json.loads(path.read_text(encoding="utf-8"))
    r = requests.get(RATES_URL, timeout=120)
    r.raise_for_status()
    data = r.json()
    if not isinstance(data, list) or len(data) < 100:
        raise RuntimeError(f"rates.json looks wrong: type={type(data)} len={len(data) if isinstance(data, list) else 'n/a'}")
    path.write_text(json.dumps(data), encoding="utf-8")
    return data


def fetch_oil_table(refresh=False):
    """18-10-0001 full CSV (it's tiny — a few MB) via the WDS zip endpoint."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    zip_path = CACHE_DIR / f"{OIL_PID}.zip"
    if refresh or not zip_path.exists() or zip_path.stat().st_size == 0:
        r = requests.get(f"{WDS}/getFullTableDownloadCSV/{OIL_PID}/en", timeout=60)
        r.raise_for_status()
        meta = r.json()
        if meta.get("status") != "SUCCESS":
            raise RuntimeError(f"getFullTableDownloadCSV {OIL_PID}: {meta.get('status')}")
        z = requests.get(meta["object"], timeout=300)
        z.raise_for_status()
        zip_path.write_bytes(z.content)
    zf = zipfile.ZipFile(zip_path)
    name = next(n for n in zf.namelist()
                if n.lower().endswith(".csv") and "metadata" not in n.lower())
    with zf.open(name) as f:
        df = pd.read_csv(io.TextIOWrapper(f, encoding="utf-8"),
                         usecols=["REF_DATE", "GEO", "Type of fuel", "VALUE"])
    return df


# =============================================================================
# Tariff reduction
# =============================================================================

def latest_residential(rates, utility_substr, name_substr):
    """All residential tariffs matching utility+name substrings, deduped to
    the latest effective_date per tariff name."""
    hits = [t for t in rates
            if t.get("customer_class") == "residential"
            and utility_substr.lower() in (t.get("utility_name") or "").lower()
            and name_substr.lower() in (t.get("name") or "").lower()]
    by_name = {}
    for t in hits:
        k = t["name"]
        if k not in by_name or (t.get("effective_date") or "") > (by_name[k].get("effective_date") or ""):
            by_name[k] = t
    return list(by_name.values())


def comps(t, *types):
    return [c for c in t["components"] if c["component_type"] in types]


def monthly_fixed(tariffs):
    """Sum every fixed charge across the given tariffs, $/day -> monthly."""
    total = 0.0
    for t in tariffs:
        for c in comps(t, "fixed"):
            if c["charge_unit"] == "$/month":
                total += c["charge_value"]
            elif c["charge_unit"] == "$/day":
                total += c["charge_value"] * DAYS_PER_MONTH
            else:
                raise RuntimeError(f"unexpected fixed unit {c['charge_unit']} in {t['name']}")
    return round(total, 2)


def kwh_adders(tariffs):
    """Non-energy volumetric $/kWh lines (distribution/transmission/regulatory/
    rider/delivery), summed across tariffs. Carbon excluded by design."""
    total = 0.0
    for t in tariffs:
        for c in comps(t, "distribution", "transmission", "regulatory", "rider", "delivery"):
            if c["charge_unit"] != "$/kWh":
                raise RuntimeError(f"unexpected adder unit {c['charge_unit']} in {t['name']}")
            total += c["charge_value"]
    return round(total, 6)


def tou_prices(tariff, mapping):
    """{output_period: price} from energy components' tou_period labels."""
    out = {}
    for c in comps(tariff, "energy"):
        p = (c.get("tou_period") or "").lower()
        for label, key in mapping.items():
            if p == label:
                out[key] = c["charge_value"]
    return out


def build_on_city(rates, city, sources):
    util, _ = sources[0]
    tariffs = latest_residential(rates, util, "Residential")
    by_kind = {}
    for t in tariffs:
        n = t["name"].lower()
        if "time-of-use" in n:
            by_kind["tou"] = t
        elif "ultra-low" in n:
            by_kind["ulo"] = t
        elif "tiered" in n:
            by_kind["tiered"] = t
    missing = {"tou", "ulo", "tiered"} - set(by_kind)
    if missing:
        raise RuntimeError(f"{city}: missing ON price plans {missing}")

    tou_t, ulo_t, tier_t = by_kind["tou"], by_kind["ulo"], by_kind["tiered"]
    # adders/fixed are identical across the three OEB plans; take them from TOU
    plans = {
        "tou": {
            "type": "tou",
            "prices_cad_per_kwh": tou_prices(tou_t, {"on-peak": "on", "mid-peak": "mid", "off-peak": "off"}),
            "calendar": TOU_CALENDAR,
        },
        "ulo": {
            "type": "tou",
            "prices_cad_per_kwh": tou_prices(ulo_t, {"ultra-low-overnight": "ulo", "on-peak": "on",
                                                     "mid-peak": "mid", "off-peak": "off"}),
            "calendar": ULO_CALENDAR,
        },
        "tiered": {
            "type": "tiered", "period": "monthly",
            "tiers": sorted(
                [{"limit_kwh": c["tier_threshold"] if c["tier_number"] == 1 else None,
                  "price_cad_per_kwh": c["charge_value"], "tier": c["tier_number"]}
                 for c in comps(tier_t, "energy")],
                key=lambda x: x["tier"]),
            "seasonal_tier1": TIERED_SEASONS,
        },
    }
    for k in ("tou", "ulo"):
        need = 3 if k == "tou" else 4
        if len(plans[k]["prices_cad_per_kwh"]) != need:
            raise RuntimeError(f"{city}: {k} expected {need} TOU prices, got {plans[k]['prices_cad_per_kwh']}")
    return {
        "utility": tou_t["utility_name"],
        "effective_date": tou_t["effective_date"],
        "confidence": tou_t["confidence"],
        "source_url": tou_t["source_url"],
        "fixed_monthly_cad": monthly_fixed([tou_t]),
        "volumetric_adders_cad_per_kwh": kwh_adders([tou_t]),
        "plans": plans,
        "default_plan": "tou",
        "notes": ["Ontario Electricity Rebate (a % credit on the pre-tax bill) not modelled; "
                  "it scales all scenarios equally."],
    }


def build_qc_city(rates, city, sources):
    util, name = sources[0]
    tariffs = latest_residential(rates, util, name)
    if not tariffs:
        raise RuntimeError(f"{city}: no {util} {name} tariff found")
    t = tariffs[0]
    tiers = sorted(
        [{"limit_kwh": c["tier_threshold"] if c["tier_number"] == 1 else None,
          "price_cad_per_kwh": c["charge_value"], "tier": c["tier_number"]}
         for c in comps(t, "energy")],
        key=lambda x: x["tier"])
    if len(tiers) != 2:
        raise RuntimeError(f"{city}: expected 2 HQ tiers, got {tiers}")
    return {
        "utility": t["utility_name"],
        "effective_date": t["effective_date"],
        "confidence": t["confidence"],
        "source_url": t["source_url"],
        "fixed_monthly_cad": monthly_fixed([t]),
        "volumetric_adders_cad_per_kwh": 0.0,
        "plans": {"tiered": {"type": "tiered", "period": "daily", "tiers": tiers}},
        "default_plan": "tiered",
        "notes": [],
    }


def build_ab_city(rates, city, sources):
    (rro_util, rro_name), (dist_util, dist_name) = sources
    rro = latest_residential(rates, rro_util, rro_name)
    dist = latest_residential(rates, dist_util, dist_name)
    if not rro or not dist:
        raise RuntimeError(f"{city}: missing AB tariff ({rro_util}: {bool(rro)}, {dist_util}: {bool(dist)})")
    rro, dist = rro[0], dist[0]
    energy = comps(rro, "energy")
    if len(energy) != 1 or energy[0]["charge_unit"] != "$/kWh":
        raise RuntimeError(f"{city}: unexpected RRO energy components {energy}")
    adders = kwh_adders([dist]) + AB_ELEC_TRANSMISSION_EST
    return {
        "utility": f"{rro['utility_name']} (RRO) + {dist['utility_name']} (wires)",
        "effective_date": rro["effective_date"],
        "confidence": "low",
        "source_url": rro["source_url"],
        "fixed_monthly_cad": round(monthly_fixed([rro, dist]), 2),
        "volumetric_adders_cad_per_kwh": round(adders, 6),
        "plans": {"flat": {"type": "flat", "price_cad_per_kwh": energy[0]["charge_value"]}},
        "default_plan": "flat",
        "notes": [
            "RRO energy rate varies monthly; this is the upstream scrape's snapshot.",
            f"Transmission + local-access charges absent upstream; screening estimate of "
            f"{AB_ELEC_TRANSMISSION_EST} $/kWh added (AUC-approved 2024-25 residential "
            f"transmission runs ~0.015-0.020 $/kWh).",
        ],
    }


def build_gas_city(rates, city):
    util, name = GAS_SOURCES[city]
    tariffs = latest_residential(rates, util, name)
    if not tariffs:
        raise RuntimeError(f"{city}: no gas tariff {util} {name}")
    t = tariffs[0]
    marginal_m3 = 0.0
    notes, carbon_dropped = [], 0.0
    for c in t["components"]:
        ctype, unit, val = c["component_type"], c["charge_unit"], c["charge_value"]
        if ctype == "fixed":
            continue
        per_m3 = val if unit == "$/m³" else (val * GJ_PER_M3 if unit == "$/GJ" else None)
        if per_m3 is None:
            raise RuntimeError(f"{city}: unexpected gas unit {unit} in {t['name']}")
        if ctype == "carbon":
            carbon_dropped += per_m3
            continue
        marginal_m3 += per_m3
    confidence = t["confidence"]
    if CITY_PROVINCE[city] == "ab":
        marginal_m3 += AB_GAS_COMMODITY_EST * GJ_PER_M3
        confidence = "low"
        notes.append(f"Default gas supply rate absent upstream; screening estimate of "
                     f"{AB_GAS_COMMODITY_EST} $/GJ added (AUC default rate ranged ~$1-4/GJ 2024-26).")
    if carbon_dropped:
        notes.append(f"Federal carbon charge ({carbon_dropped:.4f} $/m³ in source) excluded — "
                     "consumer fuel charge set to zero 2025-04-01.")
    if city in ("ottawa", "toronto"):
        notes.append("Enbridge 'Union South' rate-zone tariff (only residential gas tariff "
                     "exported for ON); Ottawa/Toronto are in the former-EGD zone with "
                     "somewhat higher delivery charges.")
    return {
        "utility": t["utility_name"],
        "effective_date": t["effective_date"],
        "confidence": confidence,
        "source_url": t["source_url"],
        "fixed_monthly_cad": monthly_fixed([t]),
        "marginal_cad_per_m3": round(marginal_m3, 4),
        "carbon_excluded": True,
        "notes": notes,
    }


# =============================================================================
# Heating oil (StatCan 18-10-0001)
# =============================================================================

def heating_oil_by_city(df):
    """{city: {cad_per_litre, ref_month, geo_used}} with fallback chain."""
    oil = df[df["Type of fuel"].str.lower().str.contains(OIL_PRODUCT_SUBSTR, na=False)].copy()
    if oil.empty:
        raise RuntimeError("18-10-0001: no household-heating-fuel rows found")
    oil = oil.dropna(subset=["VALUE"])
    latest_all = oil[oil["REF_DATE"] == oil["REF_DATE"].max()]

    def city_latest(geo_substr):
        rows = oil[oil["GEO"].str.contains(geo_substr, na=False)]
        if rows.empty:
            return None
        row = rows.sort_values("REF_DATE").iloc[-1]
        return {"cad_per_litre": round(row["VALUE"] / 100.0, 3),
                "ref_month": row["REF_DATE"], "geo_used": row["GEO"]}

    national_mean = {"cad_per_litre": round(latest_all["VALUE"].mean() / 100.0, 3),
                     "ref_month": latest_all["REF_DATE"].max(),
                     "geo_used": f"mean of {latest_all['GEO'].nunique()} reporting cities"}

    out = {}
    for city, substr in OIL_GEO.items():
        hit = city_latest(substr)
        if hit is None:  # same-province city, then national mean
            prov = CITY_PROVINCE[city]
            sibling = next((c for c, s in OIL_GEO.items()
                            if CITY_PROVINCE[c] == prov and c != city and city_latest(s)), None)
            hit = city_latest(OIL_GEO[sibling]) if sibling else dict(national_mean)
        # stale-guard: if a city's series stopped years ago, prefer the mean
        if hit["ref_month"] < str(int(latest_all["REF_DATE"].max()[:4]) - 2):
            hit = dict(national_mean)
        hit["source"] = "StatCan 18-10-0001, household heating fuel"
        out[city] = hit
    return out


# =============================================================================
# Validation
# =============================================================================

def check(name, value, results):
    lo, hi = VALIDATION_BANDS[name]
    ok = lo <= value <= hi
    results.append(ok)
    print(f"  {'PASS' if ok else 'FAIL':4s}  {name:26s} ${value:8.2f}  (band ${lo:.0f}-${hi:.0f})")
    return ok


def validate(provinces):
    print("\nValidation (reconstructed monthly bills, pre-tax):")
    results = []
    on, qc, ab = provinces["on"], provinces["qc"], provinces["ab"]

    e = on["electricity"]["ottawa"]
    tou = e["plans"]["tou"]["prices_cad_per_kwh"]
    energy = 1000 * (0.63 * tou["off"] + 0.18 * tou["mid"] + 0.19 * tou["on"])
    bill = energy + 1000 * e["volumetric_adders_cad_per_kwh"] + e["fixed_monthly_cad"]
    check("ottawa_elec_1000kwh", bill, results)

    g = on["natural_gas"]["ottawa"]
    check("ottawa_gas_200m3", 200 * g["marginal_cad_per_m3"] + g["fixed_monthly_cad"], results)

    m = qc["electricity"]["montreal"]
    tiers = m["plans"]["tiered"]["tiers"]
    t1_kwh = min(1500, tiers[0]["limit_kwh"] * 30)
    bill = (t1_kwh * tiers[0]["price_cad_per_kwh"]
            + (1500 - t1_kwh) * tiers[1]["price_cad_per_kwh"] + m["fixed_monthly_cad"])
    check("montreal_elec_1500kwh", bill, results)

    c = ab["electricity"]["calgary"]
    bill = 600 * (c["plans"]["flat"]["price_cad_per_kwh"] + c["volumetric_adders_cad_per_kwh"]) \
        + c["fixed_monthly_cad"]
    check("calgary_elec_600kwh", bill, results)

    cg = ab["natural_gas"]["calgary"]
    m3 = 10 / GJ_PER_M3  # 10 GJ in m3
    check("calgary_gas_10gj", m3 * cg["marginal_cad_per_m3"] + cg["fixed_monthly_cad"], results)

    if not all(results):
        raise RuntimeError("validation failed — see FAIL lines above")


# =============================================================================
# Main
# =============================================================================

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true", help="force re-download of both sources")
    args = ap.parse_args()

    print("Fetching canada-utility-rates exports…")
    rates = fetch_rates_json(refresh=args.refresh)
    print(f"  {len(rates)} tariffs")
    print("Fetching StatCan 18-10-0001 (heating oil)…")
    oil_df = fetch_oil_table(refresh=args.refresh)
    oil = heating_oil_by_city(oil_df)
    for city, o in oil.items():
        print(f"  {city:9s} {o['cad_per_litre']:.3f} $/L  ({o['ref_month']}, {o['geo_used']})")

    provinces = {p: {"province": p, "electricity": {}, "natural_gas": {}, "heating_oil": {}}
                 for p in ("on", "qc", "ab")}
    builders = {"on": build_on_city, "qc": build_qc_city, "ab": build_ab_city}
    for city, prov in CITY_PROVINCE.items():
        provinces[prov]["electricity"][city] = builders[prov](rates, city, ELEC_SOURCES[city])
        provinces[prov]["natural_gas"][city] = build_gas_city(rates, city)
        provinces[prov]["heating_oil"][city] = oil[city]

    validate(provinces)

    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for p, obj in provinces.items():
        obj["generated"] = generated
        path = OUTPUT_DIR / f"{p}.json"
        path.write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":")),
                        encoding="utf-8")
        print(f"wrote {path} ({path.stat().st_size/1024:.1f} KB)")

    meta = {
        "generated": generated,
        "sources": {
            "tariffs": {"name": "MaxPr1me/canada-utility-rates (aggregates official "
                                "utility/regulator rate pages; per-entry source_url is the "
                                "originating page)",
                        "url": RATES_URL, "cadence": "monthly (1st)"},
            "heating_oil": {"name": "StatCan table 18-10-0001, household heating fuel, ¢/L by city",
                            "cadence": "monthly"},
        },
        "units": {"electricity": "CAD/kWh volumetric; CAD/month fixed",
                  "natural_gas": "CAD/m³ marginal (all volumetric lines summed); CAD/month fixed",
                  "heating_oil": "CAD/L"},
        "method": {
            "dedupe": "latest effective_date per (utility, tariff)",
            "carbon": "carbon components excluded (federal consumer fuel charge zero since 2025-04-01)",
            "gj_to_m3": GJ_PER_M3,
            "fixed_day_to_month": round(DAYS_PER_MONTH, 4),
            "tou_calendars": "OEB seasonal TOU/ULO calendars hardcoded (upstream hours are free text); "
                             "holidays follow the weekend rule; consumers ignoring holidays err <1%",
            "ab_supplements": {
                "elec_transmission_cad_per_kwh": AB_ELEC_TRANSMISSION_EST,
                "gas_commodity_cad_per_gj": AB_GAS_COMMODITY_EST,
                "why": "absent from upstream exports; screening estimates, confidence set to 'low'",
            },
        },
        "files": {"on.json / qc.json / ab.json":
                  "per-province: electricity{city}, natural_gas{city}, heating_oil{city}"},
    }
    (OUTPUT_DIR / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1),
                                          encoding="utf-8")
    print(f"wrote {OUTPUT_DIR / 'meta.json'}")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\nERROR: {e}", file=sys.stderr)
        sys.exit(1)
