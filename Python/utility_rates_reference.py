"""
utility_rates_reference.py

Builds a standalone, all-provinces "rough savings calc" reference table of
average residential electricity ($/kWh) and natural gas ($/m3) prices, plus
average fixed monthly charges, from MaxPr1me/canada-utility-rates'
site/data/rates.json (the same upstream source Python/rates_etl.py uses for
prices_json/{on,qc,ab}.json — see that file's docstring for the full scouting
report).

This is deliberately simpler than prices_json: one blended number per
province (not per city/plan), averaged across every residential utility the
upstream export carries for that province — good enough for order-of-
magnitude "what would this retrofit save" math, not for billing accuracy.

Reduction rules (mirrors rates_etl.py where the situations overlap):
- Only residential (customer_class == "residential") tariffs are used.
- Duplicate scrapes of the same (utility, tariff name) are deduped to the
  latest effective_date; if effective_date ties, the record with more
  populated components wins (the upstream export has some empty-component
  duplicates from earlier scrape runs).
- A utility offering multiple residential plans (e.g. Ontario's Time-of-Use
  / Ultra-Low-Overnight / Tiered) contributes ONE plan, chosen by priority
  time-of-use > tiered > flat/market > ultra-low-overnight, then blended to
  a single $/kWh using the OEB-typical 63/18/19 off/mid/on split (same
  constant rates_etl.py's blended_elec_price() uses) or the tier-1 rate.
- component_type == "carbon" is EXCLUDED (federal consumer fuel charge is
  zero since 2025-04-01).
- $/GJ -> $/m3 at 0.03798 GJ/m3; $/day fixed -> $/month at x 365/12.
- Alberta is deregulated: energy (RRO retailers) and wires (distribution
  utilities) are separate tariffs/bills. They're averaged within their own
  group, then SUMMED (both bills are real) rather than blended into one
  tariff-level average like every other (bundled-monopoly) province. The
  upstream AB export also omits the transmission volumetric charge and the
  default gas commodity/supply charge outright; the same screening
  estimates rates_etl.py uses (0.017 $/kWh elec transmission, 2.25 $/GJ gas
  commodity) are applied here too, flagged low-confidence, so this table
  doesn't silently disagree with prices_json/ab.json.

Every number in the output is traceable: each province entry carries a
"sources" list of the individual utility tariffs averaged into it (utility
name, tariff name, rate structure, the $/kWh or $/m3 value pulled out of it,
effective date, confidence, and source_url).

Usage:
    pip install requests
    python utility_rates_reference.py            # uses cached download if present
    python utility_rates_reference.py --refresh   # force re-download
"""

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

REPO_ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = REPO_ROOT / "Python" / "rates_cache"
OUTPUT_JSON = REPO_ROOT / "utility_rates_reference.json"
OUTPUT_CSV = REPO_ROOT / "utility_rates_reference.csv"

RATES_URL = ("https://raw.githubusercontent.com/MaxPr1me/canada-utility-rates/"
             "main/site/data/rates.json")

GJ_PER_M3 = 0.03798          # 10.55 kWh/m3 HHV — matches rates_etl.py / heatpump.html
DAYS_PER_MONTH = 365 / 12
TOU_SPLIT = {"off": 0.63, "mid": 0.18, "on": 0.19}  # OEB-typical; matches precompute_province_stats.py

# Screening-grade supplements for gaps in AB's upstream export (see docstring).
# Kept identical to rates_etl.py's AB_ELEC_TRANSMISSION_EST / AB_GAS_COMMODITY_EST.
AB_ELEC_TRANSMISSION_EST = 0.017   # $/kWh
AB_GAS_COMMODITY_EST = 2.25        # $/GJ

ADDER_TYPES = ("distribution", "transmission", "regulatory", "rider", "delivery")


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
        raise RuntimeError(f"rates.json looks wrong: type={type(data)} "
                           f"len={len(data) if isinstance(data, list) else 'n/a'}")
    path.write_text(json.dumps(data), encoding="utf-8")
    return data


# =============================================================================
# Dedupe + plan selection
# =============================================================================

def dedupe_latest(tariffs):
    """One tariff per (utility_name, name): latest effective_date wins;
    ties broken by whichever record has more populated components (the
    upstream export has some empty-component duplicates from stale scrapes)."""
    best = {}
    for t in tariffs:
        k = (t["utility_name"], t["name"])
        cur = best.get(k)
        if cur is None:
            best[k] = t
            continue
        t_date, c_date = t.get("effective_date") or "", cur.get("effective_date") or ""
        if (t_date, len(t["components"])) > (c_date, len(cur["components"])):
            best[k] = t
    return list(best.values())


def comps(t, *types):
    return [c for c in t["components"] if c["component_type"] in types]


PLAN_PRIORITY = ("time-of-use", "tiered", "flat_or_market", "ultra-low")


def plan_rank(t):
    name = (t["name"] or "").lower()
    if "ultra-low" in name or "ulo" in name:
        return 3
    if "time-of-use" in name or t["rate_structure"] == "tou":
        return 0
    if t["rate_structure"] == "tiered":
        return 1
    return 2  # flat / market


# Longest phrases first so e.g. "tiered pricing" is consumed whole before
# the bare "tiered"/"pricing" tokens would otherwise leave a stray remainder.
PLAN_KEYWORDS = ("ultra-low overnight", "ultra low overnight", "time-of-use", "time of use",
                 "tiered pricing", "tiered", "pricing", "ultra-low", "ultra low", "ulo", "tou")


def normalize_for_grouping(name):
    """Strip plan-type keywords/abbreviations (Time-of-Use / Tiered /
    Ultra-Low-Overnight / "(TOU)" / "(ULO)") so that e.g. 'Residential --
    Time-of-Use (TOU)' and 'Residential -- Tiered Pricing' normalize to the
    same key (same underlying offer, different price plan) — while
    distinct rate zones like 'Residential Service – Diesel Zone' vs
    '– Yellowknife Zone' do NOT collapse together, since those are
    different customer bases that should each be counted."""
    n = (name or "").lower()
    n = re.sub(r"\([^)]*\)", " ", n)  # drop parenthetical abbreviations
    for kw in PLAN_KEYWORDS:
        n = n.replace(kw, " ")
    n = re.sub(r"[-–—]", " ", n)
    return re.sub(r"\s+", " ", n).strip()


def pick_one_plan_per_utility(tariffs):
    """Collapse same-offer multi-plan tariffs (TOU/tiered/ULO variants of one
    residential offer) to the single best-priority plan. Tariffs for
    genuinely different rate zones under the same utility are NOT collapsed
    — each is kept and contributes to the province average separately."""
    by_key = {}
    for t in tariffs:
        k = (t["utility_name"], normalize_for_grouping(t["name"]))
        cur = by_key.get(k)
        if cur is None or plan_rank(t) < plan_rank(cur):
            by_key[k] = t
    return list(by_key.values())


# =============================================================================
# Per-tariff $/kWh and $/m3 extraction
# =============================================================================

def monthly_fixed(t):
    total = 0.0
    for c in comps(t, "fixed"):
        if c["charge_unit"] == "$/month":
            total += c["charge_value"]
        elif c["charge_unit"] == "$/day":
            total += c["charge_value"] * DAYS_PER_MONTH
        else:
            raise RuntimeError(f"unexpected fixed unit {c['charge_unit']} in {t['name']}")
    return round(total, 2)


def kwh_adders(t):
    """Sum of $/kWh adder components. Percentage riders (charge_unit ==
    'fraction', e.g. BC Hydro's small rate-rider credit) are skipped —
    they're a rounding error next to the volumetric rate and not worth the
    complexity of a multiplicative model in a rough-calc table."""
    total = 0.0
    for c in comps(t, *ADDER_TYPES):
        if c["charge_unit"] == "fraction":
            continue
        if c["charge_unit"] != "$/kWh":
            raise RuntimeError(f"unexpected adder unit {c['charge_unit']} in {t['name']}")
        total += c["charge_value"]
    return total


def energy_rate_elec(t):
    """Blended $/kWh energy rate from a tariff's 'energy' components, or
    None if the tariff has no energy component (AB wires-only distribution).
    Branches on the actual shape of the components rather than the
    declared rate_structure — a few upstream tariffs (e.g. Manitoba Hydro)
    are labelled "flat" but carry a 2-block tiered energy structure."""
    energy = comps(t, "energy")
    if not energy:
        return None
    if any(c.get("tou_period") for c in energy):
        prices = {}
        for c in energy:
            p = (c.get("tou_period") or "").lower()
            if p == "on-peak":
                prices["on"] = c["charge_value"]
            elif p == "mid-peak":
                prices["mid"] = c["charge_value"]
            elif p == "off-peak":
                prices["off"] = c["charge_value"]
        if set(prices) != set(TOU_SPLIT):
            raise RuntimeError(f"expected on/mid/off TOU prices in {t['name']}, got {prices}")
        return sum(TOU_SPLIT[k] * prices[k] for k in TOU_SPLIT)
    if len(energy) > 1:
        tier1 = min(energy, key=lambda c: c.get("tier_number") or 999)
        return tier1["charge_value"]
    if energy[0]["charge_unit"] != "$/kWh":
        raise RuntimeError(f"unexpected energy unit in {t['name']}: {energy}")
    return energy[0]["charge_value"]


def gas_marginal_per_m3(t):
    """Sum of every non-carbon volumetric gas component, $/m3 (GJ converted).
    Also returns the excluded carbon $/m3 for documentation."""
    marginal, carbon = 0.0, 0.0
    for c in t["components"]:
        ctype, unit, val = c["component_type"], c["charge_unit"], c["charge_value"]
        if ctype == "fixed":
            continue
        if unit == "$/m³" or unit == "$/m3":
            per_m3 = val
        elif unit == "$/GJ":
            per_m3 = val * GJ_PER_M3
        else:
            raise RuntimeError(f"unexpected gas unit {unit} in {t['name']}")
        if ctype == "carbon":
            carbon += per_m3
        else:
            marginal += per_m3
    return marginal, carbon


# =============================================================================
# Per-province aggregation
# =============================================================================

def source_record(t, value, unit, extra=None):
    rec = {
        "utility": t["utility_name"],
        "tariff_name": t["name"],
        "rate_structure": t["rate_structure"],
        "value": round(value, 6),
        "unit": unit,
        "effective_date": t["effective_date"],
        "confidence": t["confidence"],
        "source_url": t["source_url"],
    }
    if extra:
        rec.update(extra)
    return rec


def build_electricity(province_tariffs, province):
    tariffs = pick_one_plan_per_utility(dedupe_latest(province_tariffs))
    bundled = [t for t in tariffs if comps(t, "energy")]
    wires_only = [t for t in tariffs if not comps(t, "energy")]

    sources = []
    energy_vals, energy_fixed = [], []
    for t in bundled:
        rate = energy_rate_elec(t)
        adders = kwh_adders(t)
        fixed = monthly_fixed(t)
        energy_vals.append(rate + adders)
        energy_fixed.append(fixed)
        sources.append(source_record(t, rate + adders, "$/kWh (energy+adders)",
                                      {"fixed_monthly_cad": fixed}))

    wires_vals, wires_fixed = [], []
    for t in wires_only:
        adders = kwh_adders(t)
        fixed = monthly_fixed(t)
        wires_vals.append(adders)
        wires_fixed.append(fixed)
        sources.append(source_record(t, adders, "$/kWh (wires-only adders)",
                                      {"fixed_monthly_cad": fixed}))

    notes = []
    if wires_only and bundled:
        # Deregulated market (AB): energy retailer + wires utility are separate
        # bills; sum the two group averages instead of blending all tariffs.
        elec_rate = (sum(energy_vals) / len(energy_vals)) + (sum(wires_vals) / len(wires_vals))
        elec_fixed = (sum(energy_fixed) / len(energy_fixed)) + (sum(wires_fixed) / len(wires_fixed))
        elec_rate += AB_ELEC_TRANSMISSION_EST
        confidence = "low"
        notes.append(f"Deregulated market: {len(bundled)} energy retailer(s) averaged + "
                     f"{len(wires_only)} wires utility(ies) averaged, summed as separate bills.")
        notes.append(f"Upstream distribution tariffs omit the transmission volumetric charge; "
                     f"a screening estimate of {AB_ELEC_TRANSMISSION_EST} $/kWh is added "
                     f"(same constant as prices_json/ab.json), confidence downgraded to low.")
    elif wires_only:  # shouldn't happen without a matching energy group, but guard anyway
        elec_rate = sum(wires_vals) / len(wires_vals)
        elec_fixed = sum(wires_fixed) / len(wires_fixed)
        confidence = "low"
        notes.append("Only wires-only (no energy component) tariffs found; incomplete.")
    else:
        elec_rate = sum(energy_vals) / len(energy_vals)
        elec_fixed = sum(energy_fixed) / len(energy_fixed)
        confidences = {t["confidence"] for t in bundled}
        confidence = "high" if confidences == {"high"} else ("medium" if "low" not in confidences else "low")

    return {
        "cents_per_kwh": round(elec_rate * 100, 3),
        "fixed_monthly_cad": round(elec_fixed, 2),
        "n_utilities": len(tariffs),
        "confidence": confidence,
        "notes": notes,
        "sources": sources,
    }


def build_gas(province_tariffs, province):
    tariffs = pick_one_plan_per_utility(dedupe_latest(province_tariffs))
    if not tariffs:
        return None

    sources = []
    vals, fixed_vals = [], []
    for t in tariffs:
        marginal, carbon = gas_marginal_per_m3(t)
        fixed = monthly_fixed(t)
        is_ab = province == "AB"
        if is_ab:
            marginal += AB_GAS_COMMODITY_EST * GJ_PER_M3
        vals.append(marginal)
        fixed_vals.append(fixed)
        extra = {"fixed_monthly_cad": fixed, "carbon_excluded_dollars_per_m3": round(carbon, 4)}
        if is_ab:
            extra["ab_commodity_estimate_added_dollars_per_gj"] = AB_GAS_COMMODITY_EST
        sources.append(source_record(t, marginal, "$/m3 (marginal, carbon excluded)", extra))

    notes = ["Federal carbon charge excluded (consumer fuel charge set to zero 2025-04-01)."]
    confidence = "high" if all(t["confidence"] == "high" for t in tariffs) else "medium"
    if province == "AB":
        notes.append(f"Upstream tariffs omit the default gas commodity/supply charge; a screening "
                     f"estimate of {AB_GAS_COMMODITY_EST} $/GJ is added (same constant as "
                     f"prices_json/ab.json), confidence downgraded.")
        confidence = "low"

    return {
        "dollars_per_m3": round(sum(vals) / len(vals), 4),
        "fixed_monthly_cad": round(sum(fixed_vals) / len(fixed_vals), 2),
        "n_utilities": len(tariffs),
        "confidence": confidence,
        "notes": notes,
        "sources": sources,
    }


# =============================================================================
# Main
# =============================================================================

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true", help="force re-download of rates.json")
    args = ap.parse_args()

    print("Fetching canada-utility-rates export…")
    rates = fetch_rates_json(refresh=args.refresh)
    print(f"  {len(rates)} tariffs")

    residential = [t for t in rates if t.get("customer_class") == "residential"]
    provinces = sorted({t["province"] for t in residential})

    out = {}
    for p in provinces:
        elec_t = [t for t in residential if t["province"] == p and t["utility_type"] == "electricity"]
        gas_t = [t for t in residential if t["province"] == p and t["utility_type"] == "gas"]
        entry = {}
        if elec_t:
            entry["electricity"] = build_electricity(elec_t, p)
            e = entry["electricity"]
            print(f"  {p} electricity: {e['cents_per_kwh']:.2f} c/kWh + "
                  f"${e['fixed_monthly_cad']:.2f}/mo  ({e['n_utilities']} utilities, {e['confidence']})")
        gas_entry = build_gas(gas_t, p)
        if gas_entry:
            entry["natural_gas"] = gas_entry
            g = gas_entry
            print(f"  {p} gas:         ${g['dollars_per_m3']:.4f}/m3 + "
                  f"${g['fixed_monthly_cad']:.2f}/mo  ({g['n_utilities']} utilities, {g['confidence']})")
        if entry:
            out[p] = entry

    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    doc = {
        "generated": generated,
        "purpose": "Standalone province-level reference table for rough savings estimates. "
                   "For precise per-city/per-plan bill math see prices_json/ (built by rates_etl.py).",
        "source": {
            "name": "MaxPr1me/canada-utility-rates",
            "url": RATES_URL,
            "cadence": "monthly (1st)",
        },
        "method": {
            "scope": "residential tariffs only",
            "plan_selection": "one plan per utility: time-of-use > tiered > flat/market > ultra-low-overnight",
            "tou_blend": TOU_SPLIT,
            "tiered_blend": "tier-1 (lowest-tier) rate only",
            "dedupe": "latest effective_date per (utility, tariff name); ties broken by most-populated record",
            "carbon": "excluded (federal consumer fuel charge zero since 2025-04-01)",
            "gj_to_m3": GJ_PER_M3,
            "fixed_day_to_month": round(DAYS_PER_MONTH, 4),
            "alberta": "deregulated energy (RRO retailer) + wires (distribution utility) tariffs "
                       "averaged within their own group, then summed as separate bills, plus "
                       "screening estimates for upstream gaps (see per-province notes).",
        },
        "units": {
            "electricity": "cents_per_kwh (blended energy+adders); fixed_monthly_cad",
            "natural_gas": "dollars_per_m3 (marginal, carbon excluded); fixed_monthly_cad",
        },
        "provinces": out,
    }

    OUTPUT_JSON.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\nwrote {OUTPUT_JSON} ({OUTPUT_JSON.stat().st_size/1024:.1f} KB)")

    csv_lines = ["province,elec_cents_per_kwh,elec_fixed_monthly_cad,elec_n_utilities,elec_confidence,"
                 "gas_dollars_per_m3,gas_fixed_monthly_cad,gas_n_utilities,gas_confidence"]
    for p in provinces:
        e = out.get(p, {}).get("electricity")
        g = out.get(p, {}).get("natural_gas")
        csv_lines.append(",".join([
            p,
            f"{e['cents_per_kwh']:.3f}" if e else "",
            f"{e['fixed_monthly_cad']:.2f}" if e else "",
            str(e["n_utilities"]) if e else "",
            e["confidence"] if e else "",
            f"{g['dollars_per_m3']:.4f}" if g else "",
            f"{g['fixed_monthly_cad']:.2f}" if g else "",
            str(g["n_utilities"]) if g else "",
            g["confidence"] if g else "",
        ]))
    OUTPUT_CSV.write_text("\n".join(csv_lines) + "\n", encoding="utf-8")
    print(f"wrote {OUTPUT_CSV}")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\nERROR: {e}", file=sys.stderr)
        sys.exit(1)
