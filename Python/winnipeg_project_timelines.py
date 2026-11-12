"""
winnipeg_project_timelines.py

Per-building construction timelines for Winnipeg new construction: the building
permit and the separate electrical, plumbing and (commercial) mechanical trade
permits on one clock (day 0 = building permit issued). Then, per building type,
how long each trade runs. Same method and file shape as
calgary_project_timelines.py, so buildtime.html reads both.

Exploratory (started 2026-11-12). Shown on buildtime.html next to Calgary.

WHAT WINNIPEG HAS AND LACKS (checked live 2026-11-12)
    Has: electrical and plumbing permits for houses AND commercial/multi-
    residential, separate from the building permit, with issue and final dates
    and a street address (NOT a permit number link).
    Mechanical permits exist for commercial and multi-residential only
    (mechanical matches 0% of houses): there is no residential HVAC permit
    in the open data, so the HVAC share of a house build can't be computed.
    No gas permits. No building-inspection dataset (only an aggregate one,
    "Housing Permit Inspection Statistics", not used), so no foundation /
    framing / final milestones: this file has permits only.

INPUTS (City of Winnipeg open data, Socrata, data.winnipeg.ca)
    it4w-cpf4  Detailed Building Permit Data   (Open Government Licence -
               Winnipeg, as in municipal_permits_etl.py): issue_date,
               final_date, status, permit_type, sub_type, permit_group,
               dwelling_units_created, street_number / street_name / street_type
    urbd-qygv  Trade Permits (Canada Open Government Licence per the
               dataset's own metadata): permit_type (Electrical / Plumbing /
               Mechanical), issue_date, final_date, status, street_*

OUTPUT
    construction_json/winnipeg_project_timelines.json   (gitignored on main)
        meta        sources, parameters, gates and every drop count, period
                    notes, plus the page contract: trades, classes,
                    class_labels, class_trades (trades REQUIRED per class),
                    share_trade, has_inspections
        coverage_pct  per period x class x trade: share of buildings with a match
        summary     per period x class, over buildings with ALL the class's
                    required trades matched and closed (cells under MIN_N are
                    suppressed). Periods: "2011-2024" and each single year.
        buildings   one compact record (no addresses) per such building.
    Raw API pages are cached in Python/winnipeg_timeline_cache/ (scratch).

METHOD
    1. Buildings: work_type 'Construct New', status 'Closed' with a final date
       on/after the issue date, issued in the chosen years. Gates (counted):
       not closed / "closed with an incomplete inspection process" / missing
       or inverted dates / no address.
       Type: Housing by sub_type (single-detached with attached garage,
       single-detached, duplex / side by side, row housing), Multi-Residential,
       and all non-residential. ACCESSORY STRUCTURES (garages, sheds) and other
       residential types are excluded and counted: they are not what the
       trade-permit comparison is about (plumbing matches only 17% of them).
    2. Trade permits: electrical and plumbing (residential + commercial) and
       mechanical (commercial, work type "M1 - HVAC"), NEW-BUILD work types only
       (electrical "SFD New" / "Wire New Bldg" / "New Multi-family Dwelling"
       etc.; plumbing "Plumb New SFD" / "Plumb New Building" etc.). Later work at
       the same address ("Additional Wiring", "Air Conditioner", "Rewire",
       "Lower Level"...), annual and sign-only electrical permits, and fire-
       sprinkler / high-hazard mechanical permits are excluded and counted.
       A first run without the work-type filter gave electrical spans of ~300
       days on a ~520-day build; that was later work being matched.
    3. Match trade -> building by ADDRESS (street number + name + type), issue
       dates within +-WINDOW_DAYS, nearest building wins (ambiguous counted).
    4. Per building and trade: permits matched, first issued day, last closed
       day, span = last closed - first issued across all matched permits.
    5. Summary only over buildings with every trade REQUIRED for their type
       (electrical + plumbing for housing; plus mechanical for multi-
       residential and non-residential). A trade missing from the open data is
       a gap, never zero days.

LIMITATIONS
    - Measured, not modelled. Winnipeg's permit clock runs long (final dates
      are administrative; the city's permit median ran ~15 months against CMHC's
      8.4 in 2025), so spans include closing lag.
    - No inspections, no gas, no residential HVAC.
    - Winnipeg's open data has no final date for almost every trade permit from about 2020
      (91-97% closed for 2010-2018, 82% for 2019, 40% for 2020, ~1% from
      2021), so only buildings issued through 2018 can be timed (the default
      period); the rate by year is in meta.trade_closure_pct_by_year.
    - Row housing is not summarised: several building permits share one street
      address and each trade permit attaches to only one of them.
    - Address join is ours, not a city key.
    - Buildings with the full trade set may differ from those without.
    - Recent years hold only buildings already closed (right-censored).
    - One city, not representative of Canada.

RUN
    python Python/winnipeg_project_timelines.py [--years 2010-2026] [--no-cache]
"""
import argparse
import collections
import hashlib
import json
import os
import re
import statistics
import sys
import urllib.parse
import urllib.request
from datetime import date

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "construction_json", "winnipeg_project_timelines.json")
CACHE = os.path.join(ROOT, "Python", "winnipeg_timeline_cache")
D = "https://data.winnipeg.ca/resource/"
PAGE = 50000
WINDOW_DAYS = 450
MIN_N = 10
OUTLIER_DAYS = 1500
EARLY_DAYS = 60
COMPLETE_YEARS = (2011, 2018)   # 2010: trade data starts 2010-01. From 2019 the open data has few
                                # final dates on trade permits (82% closed for 2019, 40% for 2020,
                                # ~1% from 2021), so spans cannot be measured; 2011-2018 are 91-97%.
CLOSURE_MIN_PCT = 90            # a year below this share of trade permits with a final date gets a note

TRADES = ["Plumbing", "Electrical", "Mechanical"]
TRADE_LABELS = {"Mechanical": "Mechanical / HVAC (commercial only)"}
CLASSES = [
    "Housing: single-detached with attached garage",
    "Housing: single-detached",
    "Housing: duplex / side by side",
    "Housing: row housing",
    "Multi-residential",
    "Non-residential",
]
HOUSING_SUB = {
    "SFD & Att. Gar.": CLASSES[0],
    "SFD": CLASSES[1],
    "Duplex / Side by Side": CLASSES[2],
    "Row Housing": CLASSES[3],
}
ROW_HOUSING_REASON = ("Several building permits share one street address (a permit per unit, probably), and each trade "
                      "permit can attach to only one of them, so most row-housing buildings show no trades. "
                      "Not summarised; coverage is shown.")
CLASS_TRADES = {c: (["Plumbing", "Electrical"] if c.startswith("Housing") else TRADES) for c in CLASSES}
SHARE_TRADE = {c: ("Electrical" if c.startswith("Housing") else "Mechanical") for c in CLASSES}


def get(ds, where, select, use_cache=True):
    key = hashlib.sha1((ds + where + select).encode()).hexdigest()
    path = os.path.join(CACHE, key + ".json")
    if use_cache and os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    rows, off = [], 0
    while True:
        p = {"$select": select, "$where": where, "$order": ":id", "$limit": PAGE, "$offset": off}
        with urllib.request.urlopen(D + ds + ".json?" + urllib.parse.urlencode(p), timeout=180) as r:
            b = json.load(r)
        rows += b
        print(f"  {ds} {len(rows)}", flush=True)
        if len(b) < PAGE:
            break
        off += PAGE
    os.makedirs(CACHE, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(rows, f)
    return rows


def key(r):
    return re.sub(r"\s+", " ", " ".join((r.get(k) or "") for k in ("street_number", "street_name", "street_type")).upper()).strip()


def pd(s):
    y, m, d = map(int, s[:10].split("-"))
    return date(y, m, d)


def med(v):
    return int(round(statistics.median(v))) if v else None


def klass(r):
    if r["permit_group"] != "Residential":
        return CLASSES[5]
    if r["permit_type"] == "Housing":
        return HOUSING_SUB.get(r.get("sub_type"))     # None = other housing sub-type
    if r["permit_type"] == "Multi-Residential":
        return CLASSES[4]
    return None                                        # accessory structures etc.


# Only NEW-BUILD work counts (Calgary's trade files are filtered to workclassgroup='New'
# the same way). Left in, "Additional Wiring", "Air Conditioner", "Rewire", "Lower
# Level" etc. at the same address inflate coverage and spans (found 2026-11-12).
NEW_WORK = {
    "Electrical": {"SFD New", "Single-Family Dwelling New", "Wire New Bldg", "New Multi-family Dwelling"},
    "Plumbing": {"Plumb New SFD", "Plumb New Single-Family Dwelling", "Plumb New Building",
                 "New Multi-family Dwelling"},
    "Mechanical": {"M1 - HVAC"},    # work_type cannot separate new from alteration here;
                                    # M2 fire sprinkler and M3 high-hazard are not HVAC
}


def trade_of(r):
    """(trade, reason): trade is None when excluded; reason names the gate."""
    t = r["permit_type"]
    tr = ("Electrical" if t in ("Electrical Residential", "Electrical Commercial") else
          "Plumbing" if t in ("Plumbing Residential", "Plumbing Commercial") else
          "Mechanical" if t == "Mechanical Commercial" else None)
    if tr is None:
        return None, "permit_type_" + t
    if r.get("work_type") not in NEW_WORK[tr]:
        return None, "not_new_build_work_" + tr
    return tr, None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--years", default="2010-2026")
    ap.add_argument("--no-cache", action="store_true")
    a = ap.parse_args()
    y0, _, y1 = a.years.partition("-")
    y0, y1 = int(y0), int(y1 or y0)
    uc = not a.no_cache
    drops = collections.OrderedDict()

    # 1. buildings ---------------------------------------------------------
    rows = get("it4w-cpf4",
               f"work_type='Construct New' and issue_date between '{y0}-01-01' and '{y1}-12-31T23:59:59'",
               "permit_number,permit_group,permit_type,sub_type,issue_date,final_date,status,"
               "dwelling_units_created,neighbourhood_name,street_number,street_name,street_type", uc)
    drops["G0_new_construction_building_permits"] = len(rows)
    g = collections.Counter()
    bld = {}
    for r in rows:
        if r.get("status") != "Closed":
            g["not_closed_" + ("incomplete_inspection" if "incomplete" in (r.get("status") or "") else "still_open")] += 1
            continue
        if not r.get("issue_date") or not r.get("final_date") or pd(r["final_date"]) < pd(r["issue_date"]):
            g["missing_or_inverted_dates"] += 1
            continue
        if not key(r):
            g["no_address"] += 1
            continue
        c = klass(r)
        if c is None:
            g["excluded_accessory_or_other_residential"] += 1
            continue
        r["_class"] = c
        bld[r["permit_number"]] = r
    for k, v in g.items():
        drops["G1_" + k] = v
    print(f"buildings kept {len(bld)} of {len(rows)}: {dict(g)}", flush=True)

    idx = collections.defaultdict(list)
    for p, r in bld.items():
        idx[key(r)].append(p)

    # 2-3. trade permits ---------------------------------------------------
    lo, hi = f"{y0 - 1}-10-01", f"{y1 + 1}-12-31T23:59:59"
    t = get("urbd-qygv", f"issue_date between '{lo}' and '{hi}'",
            "permit_number,permit_type,work_type,issue_date,final_date,status,street_number,street_name,street_type", uc)
    drops["G2_trade_permits_pulled"] = len(t)
    tl = collections.defaultdict(lambda: collections.defaultdict(dict))
    ex = collections.Counter(); matched = collections.Counter(); ambiguous = collections.Counter()
    for x in t:
        tr, why = trade_of(x)
        if tr is None:
            ex[why] += 1
            continue
        if not x.get("issue_date") or not key(x):
            ex["no_date_or_address"] += 1
            continue
        c = [(abs((pd(x["issue_date"]) - pd(bld[p]["issue_date"])).days), p) for p in idx.get(key(x), [])]
        c = [z for z in c if z[0] <= WINDOW_DAYS]
        if not c:
            continue
        matched[tr] += 1
        ambiguous[tr] += len(c) > 1
        tl[min(c)[1]][tr][x["permit_number"]] = x
    closure = collections.defaultdict(lambda: [0, 0])
    for x in t:
        if trade_of(x)[0] in ("Electrical", "Plumbing") and x.get("issue_date"):
            c_ = closure[x["issue_date"][:4]]
            c_[0] += 1
            c_[1] += bool(x.get("final_date"))
    closure_pct = {y: round(100 * v[1] / v[0]) for y, v in sorted(closure.items()) if v[0]}
    for k, v in ex.items():
        drops["G2_excluded_" + re.sub(r"\W+", "_", k)] = v
    for tr in TRADES:
        n = sum(1 for x in t if trade_of(x)[0] == tr)
        drops[f"G3_{tr}_trade_permits_in_scope"] = n
        drops[f"G3_{tr}_matched_to_a_building"] = matched[tr]
        drops[f"G3_{tr}_matched_ambiguously_nearest_chosen"] = ambiguous[tr]
        print(f"{tr}: in scope {n}, matched {matched[tr]} (ambiguous {ambiguous[tr]})", flush=True)

    # 4. per-building records ----------------------------------------------
    def day(s, t0):
        return (pd(s) - t0).days if s else None

    out, outliers = [], 0
    for p, r in sorted(bld.items()):
        t0 = pd(r["issue_date"])
        rec = {"permit": p, "class": r["_class"], "units": int(float(r.get("dwelling_units_created") or 0)),
               "community": (r.get("neighbourhood_name") or "").title() or None,
               "issued": r["issue_date"][:10], "build_days": day(r["final_date"], t0),
               "inspections": {}, "trades": {}}
        for name in TRADES:
            ps = tl.get(p, {}).get(name)
            if not ps:
                continue
            first = min(day(x["issue_date"], t0) for x in ps.values())
            closes = [day(x["final_date"], t0) for x in ps.values() if x.get("final_date")]
            e = {"permits": len(ps), "first_issued": first,
                 "last_closed": max(closes) if closes else None, "open_permits": len(ps) - len(closes)}
            e["span"] = e["last_closed"] - first if closes else None
            rec["trades"][name] = e
            if abs(first) > OUTLIER_DAYS or abs(e["last_closed"] or 0) > OUTLIER_DAYS:
                outliers += 1
        rec["early"] = any(v["first_issued"] < -EARLY_DAYS for v in rec["trades"].values())
        out.append(rec)
    drops["flag_trade_milestones_beyond_%d_days_kept" % OUTLIER_DAYS] = outliers

    # coverage + summary, per period x class --------------------------------
    def is_full(r):
        need = CLASS_TRADES[r["class"]]
        return bool(r["build_days"]) and all(
            n in r["trades"] and r["trades"][n]["span"] is not None for n in need)

    def summarize(rs, c):
        n = len(rs)
        if c == CLASSES[3]:
            cov_ = {"buildings": n, **{tr: round(100 * sum(tr in r["trades"] for r in rs) / n, 1) if n else None
                                       for tr in TRADES}}
            return cov_, {"all_four_trades_closed": sum(1 for r in rs if is_full(r)), "buildings": n,
                          "suppressed": ROW_HOUSING_REASON}
        cov = {"buildings": n, **{tr: round(100 * sum(tr in r["trades"] for r in rs) / n, 1) if n else None
                                  for tr in TRADES}}
        full = [r for r in rs if is_full(r)]
        s = {"all_four_trades_closed": len(full), "buildings": n}   # key name shared with the Calgary file
        if len(full) >= MIN_N:
            st_ = SHARE_TRADE[c]
            s["build_days_median"] = med([r["build_days"] for r in full])
            for tr in CLASS_TRADES[c]:
                s[tr + "_first_issued_median"] = med([r["trades"][tr]["first_issued"] for r in full])
                s[tr + "_span_median"] = med([r["trades"][tr]["span"] for r in full])
            sh = [100 * r["trades"][st_]["span"] / r["build_days"] for r in full]
            s[st_ + "_span_share_of_build_pct_median"] = round(statistics.median(sh), 1)
            ok = [r for r in full if not r["early"]]
            s["early_flagged_n"] = len(full) - len(ok)
            if len(ok) >= MIN_N:
                s["build_days_median_excl_early"] = med([r["build_days"] for r in ok])
                s[st_ + "_span_share_excl_early_pct_median"] = round(statistics.median(
                    100 * r["trades"][st_]["span"] / r["build_days"] for r in ok), 1)
        else:
            s["suppressed"] = f"fewer than {MIN_N} buildings with every required trade closed"
        return cov, s

    cy0, cy1 = COMPLETE_YEARS
    periods = collections.OrderedDict()
    periods[f"{cy0}-{cy1}"] = lambda y: cy0 <= y <= cy1
    for yy in range(y0, y1 + 1):
        periods[str(yy)] = (lambda v: (lambda y: y == v))(yy)
    cov, summ = {}, {}
    for pk, pred in periods.items():
        cov[pk], summ[pk] = {}, {}
        for c in CLASSES:
            rs = [r for r in out if r["class"] == c and pred(int(r["issued"][:4]))]
            cov[pk][c], summ[pk][c] = summarize(rs, c)

    keep = [r for r in out if is_full(r)]
    drops["buildings_total"] = len(out)
    drops["buildings_listed_all_required_trades_closed"] = len(keep)

    doc = {"meta": {
        "title": "Winnipeg new-construction project timelines",
        "generated": date.today().isoformat(), "city": "Winnipeg",
        "issue_years": [y0, y1], "complete_years": [cy0, cy1], "day_zero": "building permit issued",
        "trades": TRADES, "trade_labels": TRADE_LABELS, "classes": CLASSES,
        "class_labels": {c: c for c in CLASSES}, "class_trades": CLASS_TRADES,
        "share_trade": SHARE_TRADE, "has_inspections": False,
        "trade_closure_pct_by_year": closure_pct,
        "period_notes": {
            **{str(yy): f"Only {closure_pct[str(yy)]}% of electrical and plumbing permits issued in {yy} have a final date "
                        "(the open data has none for almost every trade permit issued from about 2020), so most buildings cannot be timed and the ones that can "
                        "are not typical."
               for yy in range(y0, y1 + 1) if closure_pct.get(str(yy), 100) < CLOSURE_MIN_PCT},
            str(y0): "Winnipeg's trade permits start 2010-01, so buildings issued early in 2010 may have trade permits we cannot see."},
        "match": f"street address (number + name + type), issue dates within +-{WINDOW_DAYS} days, nearest wins",
        "min_n_for_summary": MIN_N, "gates_and_drops": drops,
        "sources": {"building_permits": "it4w-cpf4", "trade_permits": "urbd-qygv"},
        "licence": "Building permits: Open Government Licence - Winnipeg (as used in municipal_permits_etl.py). "
                   "Trade permits: Canada Open Government Licence (dataset metadata).",
        "basis": "measured from city records; final dates are administrative",
        "limitations": [
            "No inspection dataset, no gas permits and no residential HVAC permits in Winnipeg's open data.",
            "Winnipeg's permit clock runs long; spans include administrative closing lag.",
            "Trade permits issued from about 2020 almost never have a final date (82% closed for 2019, 40% for 2020, ~1% after), so only buildings issued through 2018 can be timed.",
            "Row housing is not summarised: several building permits share one address and a trade permit attaches to only one.",
            "Recent issue years only contain buildings already closed (right-censored).",
            "Address join is ours, not a city key; one city only."]},
        "coverage_pct": cov, "summary": summ, "buildings": keep}
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(doc, f, separators=(",", ":"))
    print(f"\nwrote {OUT} ({os.path.getsize(OUT) / 1e6:.1f} MB)")
    print(json.dumps(drops, indent=1))
    print(json.dumps(summ[f"{cy0}-{cy1}"], indent=1))


if __name__ == "__main__":
    sys.exit(main())
