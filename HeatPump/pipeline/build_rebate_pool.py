"""
build_rebate_pool.py

How many households could qualify for the federal National Heat Pump Rebate,
per FSA?  Two numbers per FSA:

  * ANY REBATE ($2,000 tier): every owner household.  The program page
    (ECCC, read 2026-11-10) has no income test for the base rebate, no
    primary-residence rule, and accepts any heating fuel.
  * HIGHER TIER (up to $10,000): owner households whose after-tax household
    income is at or below the program's threshold for their province and
    household size.  UPPER-BOUND ESTIMATE, see "Method and limits".

INPUTS
  HeatPump/data/raw/nrcan/program_page_2026-11-10.html
      ECCC program page; the income-threshold table (province x household
      size, 2025 dollars) is parsed from it.
  HeatPump/data/raw/statcan/98100056_en.zip
      StatCan 2021 Census table 98-10-0056-01, household after-tax income
      group by household size (2020 incomes), provinces/territories slice.
      Download: https://www150.statcan.gc.ca/n1/tbl/csv/98100056-eng.zip
  census_json/fsa_census.json
      Per-FSA owner/renter households (extract_fsa_census.py).

OUTPUTS
  HeatPump/data/interim/rebate_income_by_prov.csv    provincial slice of 0056
  newheatpumps_json/rebate_pool.json                 per-FSA + per-province

METHOD AND LIMITS
  0. Put thresholds and incomes in the same year.  Program thresholds are
     2025 dollars; census incomes are 2020.  The program says its thresholds are
     the 2021 Census median after-tax household income by province and size,
     inflation-adjusted.  The census table itself carries those medians (row
     "Median after-tax income of household"), so the inflation factor is read
     back from the data: threshold / census median.  It is 1.198-1.199 in every
     one of the 65 cells (checked in main(); the run stops if the spread
     exceeds 0.002).  Thresholds are divided by that factor, so households are
     compared with the 2020 median they were derived from.  Without this step
     the share below the threshold is about 64% instead of about 50%.
  1. Per province and household size (1, 2, 3, 4, 5+): share of households with
     after-tax income <= threshold.  The threshold sits inside an income
     bracket; households are assumed uniform within it (linear interpolation).
  2. Province share = sum over sizes of (households <= threshold) / all
     households.  This uses the province's own size mix.
  3. The size-specific thresholds cannot be applied inside an FSA (the FSA
     income table has no household-size split).  Instead one income level per
     province, "cut_2020", is found where the province's ALL-household after-tax
     distribution reaches the province share from step 2.  Each FSA's own share
     of households at or below cut_2020 comes from the Census Profile income
     brackets (characteristic IDs 281-300), interpolated within a bracket.
     FSA higher-tier estimate = FSA owner households x that FSA share.
     Rich FSAs thus score low, poor FSAs high.  Still an upper bound (no
     owner/renter income split in the FSA table either).
  Limits (also shown on the page):
   - The census table has NO owner/renter split, so step 2 uses ALL
     households.  Owners earn more than renters, so this OVERSTATES the owner
     count under the threshold: an upper bound.
   - FSAs differ from their province's average, and the estimate ignores that.
   - Households' 2025 incomes differ from 2020 incomes in ways a single
     inflation factor does not capture (the program also tests 2025 tax
     returns).  Step 0 aligns the scale, not the real 2025 distribution.
   - Program rules can still change (ECCC: criteria not final).
   - Households, not people.  Counts are not applicants or sales.
   - Census rounding: counts are randomly rounded to multiples of 5.
  Nothing is dropped silently: FSAs whose province cannot be assigned or whose
  owner count is missing are listed in the output under "dropped".
"""
import csv
import html
import io
import json
import os
import re
import zipfile

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
PAGE = os.path.join(ROOT, "HeatPump/data/raw/nrcan/program_page_2026-11-10.html")
ZIP = os.path.join(ROOT, "HeatPump/data/raw/statcan/98100056_en.zip")
FSA_CENSUS = os.path.join(ROOT, "census_json/fsa_census.json")
INTERIM = os.path.join(ROOT, "HeatPump/data/interim/rebate_income_by_prov.csv")
OUT = os.path.join(ROOT, "newheatpumps_json/rebate_pool.json")

PROVS = ["Newfoundland and Labrador", "Prince Edward Island", "Nova Scotia",
         "New Brunswick", "Quebec", "Ontario", "Manitoba", "Saskatchewan",
         "Alberta", "British Columbia", "Nunavut", "Northwest Territories",
         "Yukon"]
SIZES = ["1 person", "2 persons", "3 persons", "4 persons", "5 or more persons"]
# (label, lower bound, upper bound exclusive).  The "$100,000 and over" parent
# row is skipped; its four children cover it.  Open top bracket stays open.
BRACKETS = [("Under $5,000", 0, 5000), ("$5,000 to $9,999", 5000, 10000),
            ("$10,000 to $14,999", 10000, 15000), ("$15,000 to $19,999", 15000, 20000),
            ("$20,000 to $24,999", 20000, 25000), ("$25,000 to $29,999", 25000, 30000),
            ("$30,000 to $34,999", 30000, 35000), ("$35,000 to $39,999", 35000, 40000),
            ("$40,000 to $44,999", 40000, 45000), ("$45,000 to $49,999", 45000, 50000),
            ("$50,000 to $59,999", 50000, 60000), ("$60,000 to $69,999", 60000, 70000),
            ("$70,000 to $79,999", 70000, 80000), ("$80,000 to $89,999", 80000, 90000),
            ("$90,000 to $99,999", 90000, 100000), ("$100,000 to $124,999", 100000, 125000),
            ("$125,000 to $149,999", 125000, 150000), ("$150,000 to $199,999", 150000, 200000),
            ("$200,000 and over", 200000, None)]
TOTAL = "Total - After-tax income of household"


def fsa_province(f):
    c = f[0]
    if c == "A": return "Newfoundland and Labrador"
    if c == "B": return "Nova Scotia"
    if c == "C": return "Prince Edward Island"
    if c == "E": return "New Brunswick"
    if c in "GHJ": return "Quebec"
    if c in "KLMNP": return "Ontario"
    if c == "R": return "Manitoba"
    if c == "S": return "Saskatchewan"
    if c == "T": return "Alberta"
    if c == "V": return "British Columbia"
    if c == "Y": return "Yukon"
    if c == "X":  # X0A/X0B/X0C = Nunavut; X0E/X0G/X1A = Northwest Territories
        return "Nunavut" if f[:3] in ("X0A", "X0B", "X0C") else (
            "Northwest Territories" if f[:3] in ("X0E", "X0G", "X1A") else None)
    return None


def read_thresholds():
    t = open(PAGE, encoding="utf-8").read()
    i = t.lower().index("<table")
    j = t.lower().index("</table>", i)
    out = {}
    for r in re.findall(r"<tr.*?</tr>", t[i:j], flags=re.S):
        c = [html.unescape(re.sub("<[^>]+>", "", x)).strip()
             for x in re.findall(r"<t[hd][^>]*>(.*?)</t[hd]>", r, flags=re.S)]
        if c[0] in PROVS:
            out[c[0]] = dict(zip(SIZES, [int(x.replace(",", "")) for x in c[1:6]]))
    assert set(out) == set(PROVS), set(PROVS) - set(out)
    return out


def extract_slice():
    if os.path.exists(INTERIM):
        return
    os.makedirs(os.path.dirname(INTERIM), exist_ok=True)
    keep = set(PROVS) | {"Canada"}
    n_in = n_out = n_skip = 0
    tmp = INTERIM + ".part"
    with zipfile.ZipFile(ZIP) as z, z.open("98100056.csv") as f, \
            open(tmp, "w", encoding="utf-8", newline="") as o:
        w = csv.writer(o)
        w.writerow(["geo", "size", "income_group", "households"])
        t = io.TextIOWrapper(f, encoding="utf-8-sig")
        next(t)
        for line in t:
            n_in += 1
            parts = line.split(",", 2)
            if len(parts) < 3:  # blank / footer lines at end of file
                n_skip += 1
                continue
            geo = parts[1]
            if geo not in keep or ",Total" not in line:
                continue
            r = next(csv.reader([line]))
            # type, ages and earners must be the 'Total' rows
            if not (r[3].startswith("Total") and r[5].startswith("Total")
                    and r[6].startswith("Total")):
                continue
            n_out += 1
            w.writerow([r[1], r[4], r[7], r[9]])
    os.replace(tmp, INTERIM)  # only a complete scan becomes the cache
    print(f"scanned {n_in:,} rows, kept {n_out:,}, short lines skipped {n_skip}")


def load_counts():
    d = {}
    for r in csv.DictReader(open(INTERIM, encoding="utf-8")):
        v = r["households"]
        d[(r["geo"], r["size"], r["income_group"])] = int(v) if v.strip() else None
    return d


def share_below(counts, geo, size, thr):
    """Households <= thr (linear within bracket) and size total."""
    tot = counts[(geo, size, TOTAL)]
    s = 0.0
    for lab, lo, hi in BRACKETS:
        c = counts[(geo, size, lab)]
        if c is None:
            raise ValueError(f"suppressed cell {geo}/{size}/{lab}")
        if hi is None or thr >= hi:
            if hi is not None:
                s += c
            elif thr >= lo:  # open bracket: no upper bound known; not used here
                raise ValueError("threshold in open bracket")
        elif thr >= lo:
            s += c * (thr - lo + 1) / (hi - lo)
    return s, tot


CENSUS_CSV = os.path.join(ROOT, "Census", "98-401-X2021013_English_CSV_data.csv")
FSA_INC = os.path.join(ROOT, "HeatPump/data/interim/fsa_income_brackets.json")
# Census Profile CHARACTERISTIC_ID -> bracket.  281 = total households; 297 is
# the "$100,000 and over" parent (skipped); 300 = "$150,000 and over" (open).
FSA_IDS = list(range(282, 297)) + [298, 299, 300]
FSA_BR = [(0, 5000), (5000, 10000), (10000, 15000), (15000, 20000), (20000, 25000),
          (25000, 30000), (30000, 35000), (35000, 40000), (40000, 45000),
          (45000, 50000), (50000, 60000), (60000, 70000), (70000, 80000),
          (80000, 90000), (90000, 100000), (100000, 125000), (125000, 150000),
          (150000, None)]


def extract_fsa_income():
    """FSA x after-tax income bracket counts (all households) from the Census Profile."""
    if os.path.exists(FSA_INC):
        return json.load(open(FSA_INC, encoding="utf-8"))
    want = {281: 0}
    want.update({cid: i + 1 for i, cid in enumerate(FSA_IDS)})
    out = {}
    with open(CENSUS_CSV, encoding="latin-1", newline="") as f:
        rd = csv.reader(f)
        next(rd)
        for row in rd:
            try:
                cid = int(row[8])
            except (ValueError, IndexError):
                continue
            if cid in want:
                fsa = row[2]
                v = row[11].strip()
                try:
                    v = int(float(v))
                except ValueError:
                    v = None  # StatCan suppression symbol -> gap, not zero
                out.setdefault(fsa, [None] * 19)[want[cid]] = v
    json.dump(out, open(FSA_INC, "w"), separators=(",", ":"))
    return out


def cum_at(vals, t):
    """Households <= t from bracket counts vals (18 entries), linear in bracket.
    Returns None if a bracket needed is suppressed."""
    s = 0.0
    for (lo, hi), c in zip(FSA_BR, vals):
        if hi is None or t < lo:
            break
        if c is None:
            return None
        s += c if t >= hi else c * (t - lo + 1) / (hi - lo)
    return s


def prov_cut(counts, p, target_share):
    """Income level T where the province's all-household distribution reaches
    target_share (bisection on the interpolated cumulative)."""
    tot = counts[(p, "Total - Households by household size", TOTAL)]
    vals = [counts[(p, "Total - Households by household size", lab)] for lab, _, _ in BRACKETS[:15]]
    # provincial table has $100-125k etc. in the same layout; align to FSA_BR
    vals = [counts[(p, "Total - Households by household size", lab)] for lab, _, _ in BRACKETS[:17]]
    vals.append(sum(counts[(p, "Total - Households by household size", lab)] for lab, _, _ in BRACKETS[17:]))
    lo, hi = 0.0, 149999.0
    for _ in range(40):
        mid = (lo + hi) / 2
        if cum_at(vals, mid) / tot < target_share:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def main():
    thr25 = read_thresholds()
    extract_slice()
    counts = load_counts()
    ratios = []
    for p in PROVS:
        for sz in SIZES:
            med = counts[(p, sz, "Median after-tax income of household ($)")]
            ratios.append(thr25[p][sz] / med)
    factor = sorted(ratios)[len(ratios) // 2]
    spread = max(ratios) - min(ratios)
    assert spread < 0.002, f"threshold/median not uniform: spread {spread:.4f}"
    print(f"inflation factor {factor:.4f} (spread {spread:.4f}, {len(ratios)} cells)")
    thr = {p: {sz: thr25[p][sz] / factor for sz in SIZES} for p in PROVS}
    prov = {}
    for p in PROVS:
        below = tot = 0.0
        sizes = {}
        for sz in SIZES:
            b, t = share_below(counts, p, sz, thr[p][sz])
            sizes[sz] = {"threshold_2025": thr25[p][sz], "threshold_2020": round(thr[p][sz]), "median_2020": counts[(p, sz, "Median after-tax income of household ($)")], "households": t,
                         "at_or_below": round(b), "share": round(b / t, 4)}
            below += b
            tot += t
        # cross-check: size rows sum to the province total (census rounding)
        grand = counts[(p, "Total - Households by household size", TOTAL)]
        prov[p] = {"share": round(below / tot, 4), "households": grand,
                   "size_rows_sum": int(tot), "sizes": sizes}
    fsa_inc = extract_fsa_income()
    cut = {p: prov_cut(counts, p, prov[p]["share"]) for p in PROVS}
    for p in PROVS:
        prov[p]["cut_2020"] = round(cut[p])
    census = json.load(open(FSA_CENSUS, encoding="utf-8"))
    fsa, dropped = {}, []
    for f, v in census.items():
        p = fsa_province(f)
        ten = v.get("tenure") or {}
        own, ren = ten.get("owner"), ten.get("renter")
        if p is None or own is None or ren is None:
            dropped.append({"fsa": f, "reason": "no province" if p is None else "tenure missing"})
            continue
        hh = own + ren
        br = fsa_inc.get(f)
        tot_i = br[0] if br else None
        c = cum_at(br[1:], cut[p]) if br and tot_i else None
        if c is None:
            dropped.append({"fsa": f, "reason": "income brackets missing/suppressed"})
            continue
        sh = c / tot_i
        est = own * sh
        fsa[f] = [p, own, hh, round(own / hh, 4) if hh else None, round(est),
                  round(est / hh, 4) if hh else None, round(sh, 4)]
    out = {
        "generated": "2026-11-10",
        "columns": ["province", "owner_households", "households", "owner_share",
                    "higher_tier_upper_bound", "higher_tier_share_of_households", "fsa_share_under_cut"],
        "thresholds": thr25, "inflation_factor": round(factor, 4), "provinces": prov, "fsa": fsa, "dropped": dropped,
        "totals": {"fsas": len(fsa), "owners": sum(x[1] for x in fsa.values()),
                   "households": sum(x[2] for x in fsa.values()),
                   "higher_tier_upper_bound": sum(x[4] for x in fsa.values())},
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump(out, open(OUT, "w", encoding="utf-8"), separators=(",", ":"))
    print(json.dumps(out["totals"]), "dropped:", len(dropped))
    for p in PROVS:
        print(f"{p:28s} share={prov[p]['share']:.3f} hh={prov[p]['households']:>10,} "
              f"sum_sizes={prov[p]['size_rows_sum']:>10,}")


if __name__ == "__main__":
    main()
