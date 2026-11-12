"""
calgary_project_timelines.py

Per-building construction timelines for Calgary new construction: the building
permit, its inspections (foundation / framing / final / occupancy) and the
separate HVAC, plumbing, electrical and gas permits, all placed on one clock
(day 0 = building permit issued). Then, per building class, how long each trade
runs and how big a share of the full build the HVAC span is.

Exploratory (started 2026-11-12). Not yet wired into a page.

WHY CALGARY ONLY
    Calgary is the one city we found (checked live 2026-11-12) that publishes
    trade permits as separate datasets AND building-inspection results keyed to
    the building permit number. Toronto's mechanical/plumbing permits mostly
    close with the building permit, so they give no independent trade length.

INPUTS (City of Calgary open data, Socrata, Open Government Licence - Calgary)
    c2es-76ed  Building Permits               (issue / completed dates, class,
                                               housing units, locationaddresses)
    8ced-xbvn  Building Inspections Results   (externalfilenum = building
                                               permitnum; inspectiontype +
                                               inspectioncompleteddate)
    cdrc-r4u8  Mechanical (HVAC) Permits and Inspections
                                              (permitissueddate,
                                               permitcompleteddate, Rough /
                                               Final inspection dates)
    5pvv-k7hn  Plumbing Permits               (issueddate, completeddate)
    vxgy-id5s  Electrical Permits             (issueddate, completeddate)
    tg24-jt7r  Gas Permits                    (issueddate, completeddate)

OUTPUT
    construction_json/calgary_project_timelines.json   (gitignored on main)
        meta        sources, parameters, gates and every drop count
        coverage    per building class x trade: share of buildings with a match
        summary     per building class, buildings that have ALL FOUR trades:
                    median days for the build, each trade's span, HVAC share
                    (cells with fewer than MIN_N buildings are suppressed)
        buildings   one compact record per building permit (no addresses)
    Raw API pages are cached in Python/calgary_timeline_cache/ (scratch).

METHOD
    1. Buildings: workclass 'New', statuscurrent 'Completed', issued in the
       chosen year(s). Class from housing units: Residential 1 unit/none,
       2 units, 3+ units (MURB), or Non-residential.
       Gate G1: drop if issue/completed date missing or completed < issued.
    2. Trade permits (workclassgroup 'New' only), one row per permit.
    3. Match trade -> building by ADDRESS: the trade permit's originaladdress
       against the building's originaladdress and every address in its
       locationaddresses, with issue dates within +-WINDOW_DAYS. When several
       buildings qualify the nearest issue date wins (counted as ambiguous).
       The building set has a parcel/lot address on many new projects, which is
       why locationaddresses is needed (16% -> 67% for new HVAC, 2026-11-12).
    4. Per building and trade: permits matched, first issue day, last close
       day, span = last close - first issue. HVAC adds first Rough and last
       Final inspection day.
    5. Summary only over buildings with all four trades (a trade missing from
       the open data is a data gap, not zero days).

LIMITATIONS (also stated on any page that uses this)
    - Measured, not modelled: every number is a date difference from the city's
      records. But closing dates are administrative and can lag physical work
      (an HVAC permit often closes long after the building does).
    - Single-unit houses almost never have HVAC / plumbing / gas permits in the
      open data (4% / 4% / 14% for 2022), so houses are NOT represented in the
      all-four summary; coverage is reported instead of hidden.
    - Buildings with all four trades may differ from those without.
    - A building can hold many trade permits (per unit or phase). Span = first
      issue to last close across them; the count is kept.
    - Re-issued or amended permits: a trade permit issued >60 days before the
      building permit, or an inspection dated before it, flags the building
      ("early"). Flagged buildings stay in; the summary also gives the medians
      without them.
    - Address matching is our join, not a city key. Mismatches show as
      extreme days; none are screened out, outliers are counted in meta.
    - One city, so not representative of Canada.
    - No envelope / insulation / air-barrier milestone exists in the data.

RUN
    python Python/calgary_project_timelines.py [--years 2022] [--no-cache]
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
OUT = os.path.join(ROOT, "construction_json", "calgary_project_timelines.json")
CACHE = os.path.join(ROOT, "Python", "calgary_timeline_cache")
D = "https://data.calgary.ca/resource/"
PAGE = 50000
WINDOW_DAYS = 450      # trade permit issue within +- this of building issue
MIN_N = 10             # suppress summary cells below this many buildings
OUTLIER_DAYS = 1500    # flag (not drop) any milestone this far from day 0
EARLY_DAYS = 60        # flag a building if a trade permit predates it by more than this,
                       # or an inspection predates its issue date (re-issued / amended permits)

TRADES = [  # name, dataset, issue field, close field
    ("HVAC", "cdrc-r4u8", "permitissueddate", "permitcompleteddate"),
    ("Plumbing", "5pvv-k7hn", "issueddate", "completeddate"),
    ("Electrical", "vxgy-id5s", "issueddate", "completeddate"),
    ("Gas", "tg24-jt7r", "issueddate", "completeddate"),
]
CLASSES = ["Residential 1 unit/none", "Residential 2 units",
           "Residential 3+ units (MURB)", "Non-residential"]


def get(ds, params, use_cache=True):
    """One Socrata query, all pages, cached on disk by query hash."""
    key = hashlib.sha1((ds + json.dumps(params, sort_keys=True)).encode()).hexdigest()
    path = os.path.join(CACHE, key + ".json")
    if use_cache and os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    rows, offset = [], 0
    while True:
        p = dict(params)
        p["$limit"], p["$offset"] = PAGE, offset
        url = D + ds + ".json?" + urllib.parse.urlencode(p)
        with urllib.request.urlopen(url, timeout=180) as r:
            batch = json.load(r)
        rows += batch
        if len(batch) < PAGE:
            break
        offset += PAGE
    os.makedirs(CACHE, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(rows, f)
    return rows


def norm(a):
    return re.sub(r"\s+", " ", (a or "").upper().replace(",", " ")).strip()


def pd(s):
    y, m, d = map(int, s[:10].split("-"))
    return date(y, m, d)


def klass(r):
    try:
        u = float(r.get("housingunits") or 0)
    except ValueError:
        u = 0
    if r.get("permitclassmapped") == "Residential":
        return CLASSES[0] if u <= 1 else CLASSES[1] if u == 2 else CLASSES[2]
    return CLASSES[3]


def med(v):
    return int(round(statistics.median(v))) if v else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--years", default="2022", help="issue year(s), e.g. 2022 or 2021-2022")
    ap.add_argument("--no-cache", action="store_true")
    a = ap.parse_args()
    y0, _, y1 = a.years.partition("-")
    y0, y1 = int(y0), int(y1 or y0)
    uc = not a.no_cache
    drops = collections.OrderedDict()

    # 1. buildings ---------------------------------------------------------
    rows = get("c2es-76ed", {
        "$select": "permitnum,originaladdress,locationaddresses,permitclassmapped,"
                   "permitclass,housingunits,issueddate,completeddate,communityname",
        "$where": f"issueddate between '{y0}-01-01' and '{y1}-12-31' and "
                  "workclass='New' and statuscurrent='Completed'",
        "$order": "permitnum"}, uc)
    drops["G0_new_completed_building_permits"] = len(rows)
    bld = {}
    bad = 0
    for r in rows:
        if not r.get("issueddate") or not r.get("completeddate") or \
           pd(r["completeddate"]) < pd(r["issueddate"]):
            bad += 1
            continue
        bld[r["permitnum"]] = r
    drops["G1_dropped_missing_or_inverted_dates"] = bad
    print(f"buildings kept {len(bld)} of {len(rows)} (G1 dropped {bad})", flush=True)

    idx = collections.defaultdict(list)
    for p, r in bld.items():
        for ad in set((r.get("locationaddresses") or "").split(";")) | {r["originaladdress"]}:
            if ad:
                idx[norm(ad)].append(p)

    # 2-3. trade permits, matched by address ------------------------------
    lo, hi = f"{y0 - 1}-10-01", f"{y1 + 1}-12-31"
    tl = collections.defaultdict(lambda: collections.defaultdict(dict))
    for name, ds, fi, fc in TRADES:
        t = get(ds, {
            "$select": f"permitnum,originaladdress,{fi} as i,{fc} as c",
            "$where": f"{fi} between '{lo}' and '{hi}' and workclassgroup='New'",
            "$group": "permitnum,originaladdress,i,c", "$order": "permitnum"}, uc)
        matched = ambiguous = 0
        for x in t:
            if not x.get("i") or not x.get("originaladdress"):
                continue
            cands = [(abs((pd(x["i"]) - pd(bld[p]["issueddate"])).days), p)
                     for p in idx.get(norm(x["originaladdress"]), [])]
            cands = [c for c in cands if c[0] <= WINDOW_DAYS]
            if not cands:
                continue
            matched += 1
            ambiguous += len(cands) > 1
            tl[min(cands)[1]][name][x["permitnum"]] = x
        drops[f"G2_{name}_trade_permits_pulled"] = len(t)
        drops[f"G2_{name}_matched_to_a_2022_building"] = matched
        drops[f"G2_{name}_matched_ambiguously_nearest_chosen"] = ambiguous
        print(f"{name}: pulled {len(t)}, matched {matched} (ambiguous {ambiguous})", flush=True)

    # HVAC rough / final inspections ---------------------------------------
    hv = {}
    hperm = sorted({k for p in tl for k in tl[p].get("HVAC", {})})
    for i in range(0, len(hperm), 400):
        ch = hperm[i:i + 400]
        for x in get("cdrc-r4u8", {
                "$select": "permitnum,inspectiontype,min(inspectioncompleteddate) as d,"
                           "max(inspectioncompleteddate) as e",
                "$where": "permitnum in (%s)" % ",".join(f"'{k}'" for k in ch),
                "$group": "permitnum,inspectiontype", "$order": "permitnum"}, uc):
            hv[(x["permitnum"], x["inspectiontype"])] = x

    # building inspections --------------------------------------------------
    ib = collections.defaultdict(dict)
    ids = sorted(bld)
    for i in range(0, len(ids), 400):
        ch = ids[i:i + 400]
        for x in get("8ced-xbvn", {
                "$select": "externalfilenum,inspectiontype,min(inspectioncompleteddate) as d,"
                           "max(inspectioncompleteddate) as e",
                "$where": "externalfilenum in (%s)" % ",".join(f"'{k}'" for k in ch),
                "$group": "externalfilenum,inspectiontype", "$order": "externalfilenum"}, uc):
            ib[x["externalfilenum"]][x["inspectiontype"]] = x
    print(f"building inspections found for {len(ib)} of {len(bld)} buildings", flush=True)

    # 4. per-building records ----------------------------------------------
    def day(s, t0):
        return (pd(s) - t0).days if s else None

    out, outliers = [], 0
    for p, r in sorted(bld.items()):
        t0 = pd(r["issueddate"])
        rec = {"permit": p, "class": klass(r), "units": int(float(r.get("housingunits") or 0)),
               "community": r.get("communityname"),
               "issued": r["issueddate"][:10], "build_days": day(r["completeddate"], t0),
               "inspections": {}, "trades": {}}
        for k in ("Foundation", "Framing", "Final", "Occupancy"):
            x = ib.get(p, {}).get(k)
            if x and x.get("d"):
                rec["inspections"][k] = {"first": day(x["d"], t0), "last": day(x["e"], t0)}
        for name in ("HVAC", "Plumbing", "Electrical", "Gas"):
            ps = tl.get(p, {}).get(name)
            if not ps:
                continue
            first = min(day(x["i"], t0) for x in ps.values())
            closes = [day(x["c"], t0) for x in ps.values() if x.get("c")]
            e = {"permits": len(ps), "first_issued": first,
                 "last_closed": max(closes) if closes else None,
                 "open_permits": len(ps) - len(closes)}
            e["span"] = e["last_closed"] - first if closes else None
            if name == "HVAC":
                rd = [hv[(k, "Rough")]["d"] for k in ps if hv.get((k, "Rough"), {}).get("d")]
                fd = [hv[(k, "Final")]["e"] for k in ps if hv.get((k, "Final"), {}).get("e")]
                e["rough_first"] = day(min(rd), t0) if rd else None
                e["final_last"] = day(max(fd), t0) if fd else None
            rec["trades"][name] = e
            if any(abs(v) > OUTLIER_DAYS for v in (first, e["last_closed"] or 0)):
                outliers += 1
        rec["early"] = any(v["first_issued"] < -EARLY_DAYS for v in rec["trades"].values()) or             any(v["first"] < 0 for v in rec["inspections"].values())
        out.append(rec)
    drops["flag_trade_milestones_beyond_%d_days_kept" % OUTLIER_DAYS] = outliers

    # coverage + summary -----------------------------------------------------
    cov, summ = {}, {}
    for c in CLASSES:
        rs = [r for r in out if r["class"] == c]
        n = len(rs)
        cov[c] = {"buildings": n,
                  **{t: round(100 * sum(t in r["trades"] for r in rs) / n, 1) if n else None
                     for t, *_ in TRADES},
                  "with_inspections": round(100 * sum(bool(r["inspections"]) for r in rs) / n, 1) if n else None}
        full = [r for r in rs if len(r["trades"]) == 4 and
                all(v["span"] is not None for v in r["trades"].values()) and r["build_days"]]
        s = {"all_four_trades_closed": len(full), "buildings": n}
        if len(full) >= MIN_N:
            s["build_days_median"] = med([r["build_days"] for r in full])
            for t, *_ in TRADES:
                s[t + "_first_issued_median"] = med([r["trades"][t]["first_issued"] for r in full])
                s[t + "_span_median"] = med([r["trades"][t]["span"] for r in full])
            sh = [100 * r["trades"]["HVAC"]["span"] / r["build_days"] for r in full]
            s["HVAC_span_share_of_build_pct_median"] = round(statistics.median(sh), 1)
            ok = [r for r in full if not r["early"]]
            s["early_flagged_n"] = len(full) - len(ok)
            if len(ok) >= MIN_N:
                s["build_days_median_excl_early"] = med([r["build_days"] for r in ok])
                s["HVAC_span_share_excl_early_pct_median"] = round(statistics.median(
                    100 * r["trades"]["HVAC"]["span"] / r["build_days"] for r in ok), 1)
            for k in ("Foundation", "Framing", "Final"):
                v = [r["inspections"][k]["first"] for r in full if k in r["inspections"]]
                if len(v) >= MIN_N:
                    s[k.lower() + "_inspection_first_median"] = med(v)
                    s[k.lower() + "_inspection_n"] = len(v)
        else:
            s["suppressed"] = f"fewer than {MIN_N} buildings with all four trades closed"
        summ[c] = s

    doc = {"meta": {
        "title": "Calgary new-construction project timelines",
        "generated": date.today().isoformat(), "city": "Calgary",
        "issue_years": [y0, y1], "day_zero": "building permit issued",
        "match": f"address (originaladdress + locationaddresses), issue dates within +-{WINDOW_DAYS} days, nearest wins",
        "min_n_for_summary": MIN_N, "gates_and_drops": drops,
        "sources": {"building_permits": "c2es-76ed", "building_inspections": "8ced-xbvn",
                    "HVAC": "cdrc-r4u8", "Plumbing": "5pvv-k7hn", "Electrical": "vxgy-id5s", "Gas": "tg24-jt7r"},
        "licence": "City of Calgary Open Data, Open Government Licence - Calgary",
        "basis": "measured from city records; closing dates are administrative",
        "limitations": [
            "Single-unit houses rarely have HVAC/plumbing/gas permits in the open data; summary excludes buildings missing any trade.",
            "Buildings with all four trades may differ from those without.",
            "Span = first trade permit issued to last closed across all matched permits.",
            "Address join is ours, not a city key; one city only; no envelope milestone exists."]},
        "coverage_pct": cov, "summary": summ, "buildings": out}
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(doc, f, separators=(",", ":"))
    print(f"\nwrote {OUT} ({os.path.getsize(OUT) / 1e6:.1f} MB)")
    print(json.dumps(drops, indent=1))
    print(json.dumps(summ, indent=1))


if __name__ == "__main__":
    sys.exit(main())
