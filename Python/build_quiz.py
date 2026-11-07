#!/usr/bin/env python3
"""build_quiz.py - generate the Energy Quiz question banks.

INPUTS (committed-pipeline outputs, read-only; all on local disk, gitignored on main)
  ceud_json/*.json          NRCan Comprehensive Energy Use Database (ceud_etl.py)
  construction_json/*.json  StatCan/CMHC housing starts (construction_etl.py)

OUTPUTS  (quiz_json/, gitignored on main, published to gh-pages by deploy.sh)
  quiz_json/meta.json           topic list, measures, per-measure guard counts
  quiz_json/<topic>.json        measures + pre-generated, seeded question bank

DESIGN (adapted from the Atlas Play geography quiz in the SimpleViz repo)
  * Every number a question shows is read from the data trees above, never typed.
  * Same year inside every question; missing values are dropped, never zero-filled.
  * A pair of items is only usable if (a) their values differ after display
    rounding and (b) the relative gap |A-B| / max(|A|,|B|) is >= MIN_GAP (3%).
    Both gates are counted per measure in meta.json ("guards").
  * Difficulty is a HEURISTIC from the relative gap (small gap = hard), not
    measured from players. Compare questions on wide-range "ratio" measures use
    fixed cuts (<=25% hard, >=65% easy); everything else uses within-measure
    x style thirds of the generated bank. Estimate questions have no fixed
    difficulty: their tolerance (percentage points) changes with the setting.
  * Styles: compare, insert (find its place), rank, gap (guess the ratio),
    estimate (guess a share), history (then vs now).
  * Questions are seeded per measure x style so the bank is reproducible.

Run:  python Python/build_quiz.py
Adding a topic: write a build_<topic>() returning a topic dict of measures
(see build_ceud) and register it in TOPICS.
"""
import json
import random
from datetime import date
from itertools import combinations
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "quiz_json"
MIN_GAP = 0.03
CAP = 60             # max sampled questions per measure x style (rank / insert)
TOL = {"easy": 15, "medium": 8, "hard": 3}   # estimate tolerance, percentage points
BASE = {"year", "energy_PJ", "ghg_Mt"}

# CEUD labels that read badly in a quiz
RENAME = {
    "diesel_fuel_oil_light_fuel_oil_and_kerosene": "Diesel and light fuel oil",
    "mining_quarrying_and_oil_and_gas_extraction": "Mining, quarrying, oil & gas",
    "wood_waste_and_pulping_liquor": "Wood waste and pulping liquor",
    "coke_and_coke_oven_gas": "Coke and coke-oven gas",
    "lpg_and_gas_plant_ngl": "LPG and gas-plant NGL",
    "still_gas_and_petroleum_coke": "Still gas and petroleum coke",
    "light_fuel_oil_and_kerosene": "Light fuel oil and kerosene",
    "aviation_turbo_fuel": "Jet fuel (aviation turbo)",
    "info_cultural": "Information and cultural industries",
}


# ------------------------------------------------------------------ helpers
def fmtv(fmt, v):
    if fmt == "pj":
        return f"{v:,.0f} PJ" if abs(v) >= 10 else f"{v:,.1f} PJ"
    if fmt == "mt":
        return f"{v:.2f} Mt" if abs(v) < 10 else f"{v:.1f} Mt"
    if fmt == "pct":
        return f"{v:.1f}%"
    return f"{v:,.0f}"


def rel(a, b):
    d = max(abs(a), abs(b))
    return 0.0 if d == 0 else abs(a - b) / d


def item(iid, name, value, hist=None):
    return {"id": iid, "name": name, "value": value, "hist": hist}


# ------------------------------------------------------------------ CEUD
class Ceud:
    def __init__(self):
        d = ROOT / "ceud_json"
        self.meta = json.load(open(d / "meta.json", encoding="utf-8"))
        self.dir = d
        self.cache = {}

    def idx(self, prefix, reg):
        key = (prefix, reg)
        if key not in self.cache:
            f = self.dir / f"{prefix}_{reg}.json"
            ix = {}
            if f.exists():
                for x in json.load(open(f, encoding="utf-8"))["records"]:
                    extra = set(x) - BASE
                    if len(extra) > 1:
                        continue
                    dim = next(iter(extra), None)
                    ix[(x["year"], dim, x.get(dim) if dim else None)] = x
            self.cache[key] = ix
        return self.cache[key]

    def get(self, prefix, reg, year, dim=None, key=None, field="energy_PJ"):
        x = self.idx(prefix, reg).get((year, dim, key))
        return None if x is None else x.get(field)

    def label(self, sector, dim, key):
        return RENAME.get(key) or self.meta["sectors"][sector]["dims"][dim]["values"][key]

    def regions(self, sector):
        return {k: v for k, v in self.meta["sectors"][sector]["regions"].items() if k != "ca"}


def build_ceud():
    c = Ceud()
    Y0, Y1 = 2000, 2023
    S = c.meta["sectors"]
    ms = []

    def M(**kw):
        kw.setdefault("hist_years", [Y0, Y1])
        kw.setdefault("topic", "ceud")
        kw.setdefault("basis", "modelled")
        kw.setdefault("year", Y1)
        ms.append(kw)

    # --- regional totals --------------------------------------------------
    for sector, pfx, noun, grp, page in [
        ("residential", "res", "residential energy use", "Homes", "ceud.html"),
        ("commercial", "com", "commercial and institutional energy use", "Buildings", "ceud.html"),
        ("industrial", "ind", "industrial energy use", "Industry", "ceud.html"),
        ("transportation", "tran", "transportation energy use", "Transport", "ceud.html"),
    ]:
        sk = "residential" if pfx == "res" else pfx
        regs = c.regions(sk)
        items = []
        for r, name in regs.items():
            v1, v0 = c.get(pfx, r, Y1), c.get(pfx, r, Y0)
            if v1 is not None and v1 > 0:
                items.append(item(r, name, v1, v0))
        M(id=f"{pfx}_region_energy", group=grp, label=noun, fmt="pj", kind="ratio", items=items,
          total=c.get(pfx, "ca", Y1),
          est="What share of Canada's " + noun + " happens in {name}?",
          note="Regions follow NRCan's grouping; 'Atlantic' and 'British Columbia & Territories' are combined regions, so sizes are not like-for-like with a single province." if pfx != "res" else "Territories are reported as one group.",
          page=page)
    # residential GHG by province (direct emissions only)
    items = []
    for r, name in c.regions("residential").items():
        v1, v0 = c.get("res", r, Y1, field="ghg_Mt"), c.get("res", r, Y0, field="ghg_Mt")
        if v1 is not None and v1 > 0:
            items.append(item(r, name, v1, v0))
    M(id="res_region_ghg", group="Homes", label="greenhouse-gas emissions from homes", fmt="mt", kind="ratio",
      items=items, total=c.get("res", "ca", Y1, field="ghg_Mt"),
      est="What share of Canada's home emissions come from {name}?",
      note="Direct (on-site) emissions only: burning gas, oil or wood in the home. Emissions from generating electricity are not counted, so provinces that heat with hydro look very low.",
      page="ceud.html")

    # --- national mixes (shares of a national total) ----------------------
    def mix(sector, pfx, dim, mid, label, noun, est, grp, only=None, minshare=0.0):
        sector = "residential" if pfx == "res" else pfx
        tot = c.get(pfx, "ca", Y1)
        items = []
        for key in S[sector]["dims"][dim]["values"]:
            v1, v0 = c.get(pfx, "ca", Y1, dim, key), c.get(pfx, "ca", Y0, dim, key)
            if v1 is None or v1 <= 0 or (tot and v1 / tot < minshare):
                continue
            items.append(item(key, c.label(sector, dim, key), v1, v0))
        M(id=mid, group=grp, label=label, fmt="pj", kind="ratio", items=items, total=tot, est=est,
          note=S[sector]["label"] + " sector, Canada. " + (only or ""), page="ceud.html")

    mix("residential", "res", "energy_source", "res_fuel", "residential energy by fuel", "fuel",
        "What share of Canada's home energy comes from {name}?", "Homes")
    mix("residential", "res", "end_use", "res_enduse", "residential energy by use", "use",
        "What share of Canada's home energy goes to {name}?", "Homes")
    mix("residential", "res", "building_type", "res_bldg", "residential energy by home type", "type",
        "What share of Canada's home energy is used in {name} homes?", "Homes")
    mix("commercial", "com", "segment2", "com_subsector", "energy use by commercial subsector", "subsector",
        "What share of commercial and institutional energy is used by {name}?", "Buildings")
    mix("industrial", "ind", "segment2", "ind_subsector", "industrial energy by industry", "industry",
        "What share of industrial energy is used by {name}?", "Industry")
    mix("transportation", "tran", "segment2", "tran_mode", "transportation energy by mode", "mode",
        "What share of transportation energy is used by {name}?", "Transport", minshare=0.01)
    mix("transportation", "tran", "energy_source", "tran_fuel", "transportation energy by fuel", "fuel",
        "What share of transportation energy comes from {name}?", "Transport", minshare=0.01)

    # sectors compared
    sec = []
    names = {"res": "Homes", "com": "Commercial and institutional", "ind": "Industry",
             "tran": "Transportation", "agr": "Agriculture"}
    for pfx, nm in names.items():
        v1, v0 = c.get(pfx, "ca", Y1), c.get(pfx, "ca", Y0)
        if v1:
            sec.append(item(pfx, nm, v1, v0))
    M(id="sector_energy", group="Canada", label="energy use by sector", fmt="pj", kind="ratio", items=sec,
      total=sum(i["value"] for i in sec),
      est="What share of Canada's end-use energy goes to {name}?",
      note="The five CEUD end-use sectors. Shares are of their sum; electricity generation and oil & gas production fuel are outside these tables except where counted under industry.",
      page="ceud.html")

    # --- bounded measures by province (percent of that province's home energy) ---
    for key, dim, mid, label, est in [
        ("natural_gas", "energy_source", "res_gas_share", "natural-gas share of home energy",
         "What share of {name}'s home energy comes from natural gas?"),
        ("electricity", "energy_source", "res_elec_share", "electricity share of home energy",
         "What share of {name}'s home energy comes from electricity?"),
        ("space_heating", "end_use", "res_heat_share", "space-heating share of home energy",
         "What share of {name}'s home energy goes to space heating?"),
    ]:
        items = []
        for r, name in c.regions("residential").items():
            tot, v = c.get("res", r, Y1), c.get("res", r, Y1, dim, key)
            if tot and v is not None:
                items.append(item(r, name, v / tot * 100))
        M(id=mid, group="Homes", label=label, fmt="pct", kind="bounded", items=items, est=est,
          note="Share of each region's own residential energy use.", page="ceud.html")

    return {
        "id": "ceud", "label": "How Canada uses energy", "page": "ceud.html",
        "basis": "modelled",
        "source": {
            "label": "NRCan Comprehensive Energy Use Database (CEUD)",
            "url": c.meta["source_url"],
            "vintage": f"{c.meta['release_year_folder']} release, data to {Y1}",
            "retrieved": c.meta["retrieved"],
            "note": "Modelled by NRCan from surveys and energy balances - estimates, not meter readings.",
        },
        "measures": ms,
    }


# ------------------------------------------------------------------ Construction
def build_construction():
    d = ROOT / "construction_json"
    meta = json.load(open(d / "meta.json", encoding="utf-8"))
    Y0, Y1 = 2000, 2025
    files = {}
    for p in ["ca", "on", "qc", "bc", "ab", "mb", "sk", "ns", "nb", "nl", "pe"]:
        f = d / f"constr_{p}.json"
        if f.exists():
            files[p] = json.load(open(f, encoding="utf-8"))

    def annual(geo, key, year):
        s = files[geo]["series"].get(key)
        if not s:
            return None
        y, m = map(int, s["start"].split("-"))
        i = (year - y) * 12 - (m - 1)
        if i < 0 or i + 12 > len(s["values"]):
            return None
        v = s["values"][i:i + 12]
        return None if any(x is None for x in v) else float(sum(v))

    ms = []

    def M(**kw):
        kw.update(topic="construction", basis="measured", year=Y1, hist_years=[Y0, Y1],
                  page="construction.html")
        ms.append(kw)

    provs = [p for p in files if p != "ca"]
    tot1, tot0 = annual("ca", "starts_unadj.starts.total", Y1), annual("ca", "starts_unadj.starts.total", Y0)
    items = []
    for p in provs:
        v1, v0 = annual(p, "starts_unadj.starts.total", Y1), annual(p, "starts_unadj.starts.total", Y0)
        if v1:
            items.append(item(p, files[p]["name"], v1, v0))
    M(id="starts_prov", group="New homes", label="housing starts", fmt="units", kind="ratio",
      items=items, total=tot1, est="What share of Canada's housing starts happen in {name}?",
      note="Calendar-year totals of unadjusted monthly starts. The three territories are not in this table, so provinces sum to slightly less than Canada.")

    types = {"single": "Single-detached", "semi": "Semi-detached", "row": "Row / townhouse", "apartment": "Apartment"}
    items = []
    for k, nm in types.items():
        v1, v0 = annual("ca", f"starts_unadj.starts.{k}", Y1), annual("ca", f"starts_unadj.starts.{k}", Y0)
        if v1:
            items.append(item(k, nm, v1, v0))
    M(id="starts_type", group="New homes", label="housing starts by home type", fmt="units", kind="ratio",
      items=items, total=tot1, est="What share of Canada's new homes started were {name}?",
      note="Canada, calendar-year totals.")

    for k, nm, mid in [("apartment", "apartments", "apt_share_prov"), ("single", "single-detached homes", "single_share_prov")]:
        items = []
        for p in provs:
            a, t = annual(p, f"starts_unadj.starts.{k}", Y1), annual(p, "starts_unadj.starts.total", Y1)
            if a is not None and t:
                items.append(item(p, files[p]["name"], a / t * 100))
        M(id=mid, group="New homes", label=f"{nm[:-1] if nm.endswith('s') and False else nm} as a share of starts",
          fmt="pct", kind="bounded", items=items, est="What share of {name}'s new homes started were " + nm + "?",
          note="Share of that province's own housing starts.")

    return {
        "id": "construction", "label": "Building Canada's homes", "page": "construction.html",
        "basis": "measured",
        "source": {
            "label": "CMHC housing starts via Statistics Canada tables 34-10-0151 and 34-10-0148",
            "url": "https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=3410015101",
            "vintage": f"calendar year {Y1}, compared with {Y0}",
            "retrieved": meta.get("retrieved", ""),
            "note": "Counts of homes started (CMHC survey), summed from unadjusted monthly values.",
        },
        "measures": ms,
    }


# ------------------------------------------------------------------ generation
def thirds(qs, fixed=None):
    if not qs:
        return
    scores = sorted(q["g"] for q in qs)
    c0, c1 = fixed or (scores[len(scores) // 3], scores[len(scores) * 2 // 3])
    for q in qs:
        q["d"] = "hard" if q["g"] <= c0 else "easy" if q["g"] >= c1 else "medium"


def row(m, i, shown=None):
    v = i["value"] if shown is None else shown
    return [i["name"], round(v, 4), fmtv(m["fmt"], v)]


def gen_measure(m):
    """Return (questions, guard_counts) for one measure."""
    its = [i for i in m["items"] if i["value"] is not None and i["value"] > 0]
    stats = {"items": len(m["items"]), "usable": len(its), "pairs": 0, "tied": 0, "too_close": 0}
    for i in its:
        i["disp"] = fmtv(m["fmt"], i["value"])
    valid = {}
    for a, b in combinations(range(len(its)), 2):
        stats["pairs"] += 1
        x, y = its[a], its[b]
        if x["disp"] == y["disp"]:
            stats["tied"] += 1
            valid[(a, b)] = False
        elif rel(x["value"], y["value"]) < MIN_GAP:
            stats["too_close"] += 1
            valid[(a, b)] = False
        else:
            valid[(a, b)] = True
    ok = lambda idxs: all(valid[(a, b)] for a, b in combinations(sorted(idxs), 2))
    pre = f"{m['topic']}:{m['id']}"
    qs = []

    def base(style, qid, g, **kw):
        q = {"id": f"{pre}:{style}:{qid}", "t": m["topic"], "m": m["id"], "s": style, "g": round(g, 4)}
        q.update(kw)
        return q

    # compare ------------------------------------------------------------
    cmp_qs = []
    rng = random.Random(pre + ":compare")
    for a, b in combinations(range(len(its)), 2):
        if not valid[(a, b)]:
            continue
        pair = [its[a], its[b]]
        rng.shuffle(pair)
        hi, lo = sorted(pair, key=lambda i: -i["value"])
        if m["fmt"] == "pct":
            ex = f"{hi['name']}: {hi['disp']}. {lo['name']}: {lo['disp']}. A gap of {hi['value'] - lo['value']:.1f} percentage points."
        else:
            ex = f"{hi['name']}: {hi['disp']}. {lo['name']}: {lo['disp']}. {hi['name']} is {hi['value'] / lo['value']:.2f}x as much."
        cmp_qs.append(base("compare", f"{pair[0]['id']}-{pair[1]['id']}", rel(hi["value"], lo["value"]),
                           it=[row(m, i) for i in pair], ex=ex))
    thirds(cmp_qs, (0.25, 0.65) if m["kind"] == "ratio" else None)
    qs += cmp_qs

    # rank ---------------------------------------------------------------
    rng = random.Random(pre + ":rank")
    combos = [c for c in combinations(range(len(its)), 4) if ok(c)]
    if len(combos) > CAP:
        combos = rng.sample(combos, CAP)
    rq = []
    for c in combos:
        grp = sorted((its[k] for k in c), key=lambda i: -i["value"])
        g = min(rel(grp[k]["value"], grp[k + 1]["value"]) for k in range(3))
        shuffled = grp[:]
        rng.shuffle(shuffled)
        rq.append(base("rank", "-".join(i["id"] for i in sorted(grp, key=lambda i: i["id"])), g,
                       it=[row(m, i) for i in shuffled],
                       ex="Highest to lowest: " + " > ".join(f"{i['name']} ({i['disp']})" for i in grp) + "."))
    thirds(rq)
    qs += rq

    # insert ---------------------------------------------------------------
    rng = random.Random(pre + ":insert")
    combos = [c for c in combinations(range(len(its)), 5) if ok(c)]
    if len(combos) > CAP:
        combos = rng.sample(combos, CAP)
    iq = []
    for c in combos:
        t = its[rng.choice(c)]
        anchors = sorted((its[k] for k in c if its[k] is not t), key=lambda i: -i["value"])
        pos = sum(1 for a in anchors if a["value"] > t["value"])
        g = min(rel(a["value"], t["value"]) for a in anchors)
        where = ("above " + anchors[0]["name"]) if pos == 0 else ("below " + anchors[-1]["name"]) if pos == 4 else \
            f"between {anchors[pos - 1]['name']} and {anchors[pos]['name']}"
        iq.append(base("insert", f"{t['id']}@" + "-".join(sorted(its[k]["id"] for k in c)), g,
                       tg=row(m, t), it=[row(m, a) for a in anchors],
                       ex=f"{t['name']} ({t['disp']}) belongs {where}."))
    thirds(iq)
    qs += iq

    # gap (ratio measures only) --------------------------------------------
    if m["kind"] == "ratio":
        scale = [1, 1.2, 1.5, 2, 3, 5, 10, 20, 30, 50, 100]
        rng = random.Random(pre + ":gap")
        gq = []
        for a, b in combinations(range(len(its)), 2):
            if not valid[(a, b)]:
                continue
            hi, lo = sorted((its[a], its[b]), key=lambda i: -i["value"])
            r = hi["value"] / lo["value"]
            if not (1.15 <= r <= 100):
                continue
            closest = min(scale, key=lambda n: abs(n - r))
            s = max(0, min(scale.index(closest) - 1, len(scale) - 4))
            opts = scale[s:s + 4]
            pair = [hi, lo]
            rng.shuffle(pair)
            gq.append(base("gap", f"{hi['id']}-{lo['id']}", rel(hi["value"], lo["value"]),
                           it=[row(m, i) for i in pair], op=opts, an=opts.index(closest),
                           ex=f"{hi['name']} ({hi['disp']}) is {r:.2f}x {lo['name']} ({lo['disp']}). {closest}x was the closest option offered."))
        thirds(gq)
        qs += gq

    # estimate -------------------------------------------------------------
    eq = []
    for i in its:
        if m["kind"] == "bounded":
            val = i["value"]
        elif m.get("total"):
            val = i["value"] / m["total"] * 100
        else:
            continue
        if m["kind"] == "ratio" and not (1 <= val <= 99):
            continue
        eq.append(base("estimate", i["id"], 0, d=None,
                       it=[[i["name"], round(val, 2), f"{val:.1f}%"]],
                       pr=m["est"].replace("{name}", i["name"]), tol=TOL,
                       ex=f"{i['name']}: {val:.1f}%" + (f" ({i['disp']} of {fmtv(m['fmt'], m['total'])})." if m["kind"] == "ratio" else ".")))
    qs += eq

    # history (then vs now) ------------------------------------------------
    if m["kind"] == "ratio":
        y0, y1 = m["hist_years"]
        hq = []
        hist_items = [i for i in its if i.get("hist") and i["hist"] > 0]
        for a, b in combinations(hist_items, 2):
            ga, gb = (a["value"] / a["hist"] - 1) * 100, (b["value"] / b["hist"] - 1) * 100
            if abs(ga - gb) < 2 or f"{ga:+.1f}" == f"{gb:+.1f}":
                continue
            rng = random.Random(pre + f":history:{a['id']}:{b['id']}")
            pair = [(a, ga), (b, gb)]
            rng.shuffle(pair)
            win = max(pair, key=lambda p: p[1])
            los = min(pair, key=lambda p: p[1])
            hq.append(base("history", f"{a['id']}-{b['id']}", rel(100 + ga, 100 + gb),
                           it=[[i["name"], round(g, 3), f"{g:+.1f}%", fmtv(m["fmt"], i["hist"]), fmtv(m["fmt"], i["value"])] for i, g in pair],
                           yr=[y0, y1],
                           ex=f"{win[0]['name']}: {win[1]:+.1f}% ({fmtv(m['fmt'], win[0]['hist'])} to {fmtv(m['fmt'], win[0]['value'])}). "
                              f"{los[0]['name']}: {los[1]:+.1f}% ({fmtv(m['fmt'], los[0]['hist'])} to {fmtv(m['fmt'], los[0]['value'])})."))
        thirds(hq)
        qs += hq
    return qs, stats


def main():
    OUT.mkdir(exist_ok=True)
    topics_meta, report = [], []
    for build in TOPICS:
        t = build()
        bank, mdefs, guards = [], {}, {}
        for m in t["measures"]:
            if len(m["items"]) < 2:
                print(f"  skip {m['id']}: <2 items")
                continue
            qs, st = gen_measure(m)
            bank += qs
            guards[m["id"]] = st
            mdefs[m["id"]] = {k: m[k] for k in ("id", "group", "label", "fmt", "kind", "year", "note", "page") if k in m}
            mdefs[m["id"]]["hist_years"] = m["hist_years"]
        for q in bank:
            q.pop("hist", None)
        counts = {}
        for q in bank:
            k = q["s"]
            counts[k] = counts.get(k, 0) + 1
        data = {"topic": {k: t[k] for k in ("id", "label", "page", "basis", "source")},
                "measures": mdefs, "questions": bank}
        path = OUT / f"{t['id']}.json"
        path.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        topics_meta.append({"id": t["id"], "label": t["label"], "page": t["page"], "basis": t["basis"],
                            "file": f"{t['id']}.json", "questions": len(bank), "by_style": counts,
                            "measures": len(mdefs), "source": t["source"], "guards": guards})
        report.append(f"{t['id']}: {len(bank)} questions, {len(mdefs)} measures, {path.stat().st_size / 1024:.0f} KB  {counts}")
    (OUT / "meta.json").write_text(json.dumps({
        "generated": date.today().isoformat(), "min_gap": MIN_GAP, "estimate_tolerance_pp": TOL,
        "styles": ["compare", "insert", "rank", "gap", "estimate", "history"],
        "topics": topics_meta}, ensure_ascii=False, indent=1), encoding="utf-8")
    print("\n".join(report))
    for tm in topics_meta:
        for mid, g in tm["guards"].items():
            print(f"  {tm['id']}/{mid}: items {g['usable']}/{g['items']}, pairs {g['pairs']}, tied {g['tied']}, <3% gap {g['too_close']}")


TOPICS = [build_ceud, build_construction]

if __name__ == "__main__":
    main()
