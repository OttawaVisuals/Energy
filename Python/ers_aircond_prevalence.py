"""
Air-conditioning prevalence in the ERS housing stock, by province and year.

PHASE 1 INPUT to the Heat Pump Explorer cooling work. This is the independent
check on the AC-prevalence figures that Phase 0 INFERRED
(Python/heatpump_cooling_calibration.py).

WHY THIS EXISTS
---------------
Phase 0 calibrated a cooling balance point against NRCan CEUD published cooling
energy and, at a common balance point of 17 C, backed out implied AC prevalence:
ON ~69-82% flat, QC 72% -> 102% rising, AB 9% -> 24% rising. Those are NOT
measurements -- they are conditional on an assumed SEER of 12 and assumed latent
multipliers, and they would all move together if either assumption is wrong.

AIRCONDTYPE is an actual observed field, so it can confirm or contradict them
independently. In particular Phase 0's central claim -- that QC/AB residuals are
AC ADOPTION GROWTH rather than a broken load model -- predicts a rising
prevalence trend here. If ERS shows flat prevalence, that explanation dies and
the load model's scale factors need revisiting before anything is built on them.

ers_web_pipeline.py already reads AIRCONDTYPE but uses it only to set the
Cooling_Change flag; the value itself is discarded and never reaches any output.

POPULATION
----------
EVALTYPE 'D' only -- the as-found audit record, i.e. the home before any
retrofit. 'E' is post-retrofit, 'P' is a plan, 'N' is new construction; none of
those describe existing stock as found. Single-detached only, to match the CEUD
and census slices Phase 0 compared against. Deduplicated by HOUSEID within each
year, so a home audited in two different years counts once per year (which is
what a per-year trend wants) but never twice in the same year.

DATA HONESTY
------------
AIRCONDTYPE is blank on a large minority of records (~27% in a 2015 spot check).
Blanks are NOT dropped: they are carried as their own 'unknown' category and
prevalence is reported as a RANGE -- a low bound counting every unknown as
no-AC, and a high bound excluding unknowns from the denominator. The truth is
between. Any narrower number would be invented.

SELECTION BIAS -- READ BEFORE CITING
------------------------------------
ERS households opted into an energy audit. They are not a random sample of the
housing stock, and are plausibly skewed toward older/leakier homes and toward
owners already contemplating upgrades. These figures describe the ERS universe,
not the Canadian housing stock. StatCan's Households and the Environment Survey
is the population-representative source and has not been consulted here.

INPUTS
------
  C:\\ERS\\<year>.csv    raw ERS extracts (same files ers_web_pipeline.py reads)

OUTPUTS
-------
  HeatPump/data/interim/ers_aircond_prevalence.csv   province x year x category
  stdout report
"""

import collections
import csv
import os

import pyarrow.csv as pacsv

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INPUT_DIR = r"C:\ERS"

CSV_FILES = [
    '2004-2006.csv', '2007.csv', '2008.csv', '2009.csv', '2010.csv',
    '2011.csv', '2012.csv', '2013.csv', '2014.csv', '2015.csv',
    '2016.csv', '2017.csv', '2018.csv', '2019.csv', '2020.csv',
    '2021.csv', '2022.csv', '2023.csv', '2024.csv', '2025.csv',
    '2026.csv',
]

NEEDED = ['HOUSEID', 'AIRCONDTYPE', 'EVALTYPE', 'PROVINCE', 'TYPEOFHOUSE']
PROVINCES = ['ON', 'QC', 'AB']          # the three the tool covers
DETACHED = {'single detached'}          # normalised lower-case

# AIRCONDTYPE raw value -> bucket. Anything unseen falls to 'other_ac' rather
# than being silently treated as no-AC.
#
# THE VOCABULARY CHANGED AROUND 2019. Older files say 'Conventional A/C' /
# 'Window A/C'; newer ones say 'Central split system', 'Mini-split ductless',
# 'Central single package system', 'Ductless Mini- or Multi-split system'.
# Both vocabularies are mapped here. Consequence: TOTAL has-AC is comparable
# across the whole period, but the TYPE split is not strictly apples-to-apples
# across the 2019 boundary -- window units all but vanish from the coding then,
# which is far more likely a coding change than a real disappearance.
CENTRAL = {
    'conventional a/c',
    'conventional a/c: with vent. cooling',
    'a/c with economizer',
    'central split system',
    'central single package system',
}
# Ductless: real cooling, but NO DUCTWORK. Called out separately because the
# engine's "assume central AC" baseline implies ducts that these homes lack.
DUCTLESS = {
    'mini-split ductless',
    'ductless mini- or multi-split system',
}
WINDOW = {
    'window a/c',
    'window a/c w/vent cooling',
    'window a/c w/ economizer',
}
NONE_AC = {'not installed'}

AC_BUCKETS = ('central', 'ductless', 'window', 'other_ac')


def bucket(raw):
    v = (raw or '').strip().lower()
    if v == '':
        return 'unknown'
    if v in CENTRAL:
        return 'central'
    if v in DUCTLESS:
        return 'ductless'
    if v in WINDOW:
        return 'window'
    if v in NONE_AC:
        return 'none'
    return 'other_ac'


def scan_file(path, counts, seen):
    """Stream one CSV, accumulating counts[(prov, year)][bucket]."""
    year = os.path.basename(path).replace('.csv', '')
    read_opts = pacsv.ReadOptions(block_size=1 << 24)
    conv_opts = pacsv.ConvertOptions(
        include_columns=NEEDED,
        column_types={c: 'string' for c in NEEDED},
    )
    try:
        reader = pacsv.open_csv(path, read_options=read_opts,
                                convert_options=conv_opts)
    except Exception as exc:                      # column absent in old years
        print("  !! %s: %s" % (year, str(exc)[:110]))
        return 0
    kept = 0
    while True:
        try:
            batch = reader.read_next_batch()
        except StopIteration:
            break
        d = batch.to_pydict()
        for hid, ac, ev, prov, typ in zip(d['HOUSEID'], d['AIRCONDTYPE'],
                                          d['EVALTYPE'], d['PROVINCE'],
                                          d['TYPEOFHOUSE']):
            if ev != 'D':
                continue
            if prov not in PROVINCES:
                continue
            if (typ or '').strip().lower() not in DETACHED:
                continue
            key = (prov, year)
            if hid in seen[key]:
                continue
            seen[key].add(hid)
            counts[key][bucket(ac)] += 1
            kept += 1
    print("  %s: %s detached D-records" % (year, f"{kept:,}"))
    return kept


def main():
    counts = collections.defaultdict(collections.Counter)
    seen = collections.defaultdict(set)

    print("=" * 78)
    print("ERS AIR-CONDITIONING PREVALENCE  (EVALTYPE D, single detached)")
    print("=" * 78)
    total = 0
    for fname in CSV_FILES:
        path = os.path.join(INPUT_DIR, fname)
        if not os.path.exists(path):
            print("  !! missing: %s" % path)
            continue
        total += scan_file(path, counts, seen)
    print("\ntotal records: %s" % f"{total:,}")

    rows = []
    print("\n" + "=" * 78)
    print("PREVALENCE BY PROVINCE AND YEAR")
    print("=" * 78)
    print("  'has AC' low  = unknowns counted as no-AC   (lower bound)")
    print("  'has AC' high = unknowns excluded entirely  (upper bound)\n")

    for prov in PROVINCES:
        years = sorted(y for (p, y) in counts if p == prov)
        if not years:
            continue
        print("  %s" % prov)
        print("    %-10s %8s %8s %8s %7s %7s %8s %6s   %s" %
              ("year", "n", "central", "ductless", "window", "other",
               "none", "unk", "has AC (low-high)"))
        for y in years:
            c = counts[(prov, y)]
            n = sum(c.values())
            if not n:
                continue
            ac = sum(c[b] for b in AC_BUCKETS)
            unk = c['unknown']
            known = n - unk
            # Self-check: every record must land in exactly one printed bucket.
            assert ac + c['none'] + unk == n, "bucket leak in %s %s" % (prov, y)
            low = 100.0 * ac / n
            high = (100.0 * ac / known) if known else 0.0
            print("    %-10s %8s %8d %8d %7d %7d %8d %6d   %5.1f%% - %5.1f%%" %
                  (y, f"{n:,}", c['central'], c['ductless'], c['window'],
                   c['other_ac'], c['none'], unk, low, high))
            rows.append({
                "province": prov, "year": y, "n_records": n,
                "central": c['central'], "ductless": c['ductless'],
                "window": c['window'], "other_ac": c['other_ac'],
                "none": c['none'], "unknown": unk,
                "has_ac_pct_low": round(low, 1), "has_ac_pct_high": round(high, 1),
                "central_pct_of_known": round(100.0 * c['central'] / known, 1) if known else "",
                "ducted_pct_of_known": round(100.0 * c['central'] / known, 1) if known else "",
            })
        print("")

    out = os.path.join(REPO, "HeatPump", "data", "interim", "ers_aircond_prevalence.csv")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=[
            "province", "year", "n_records", "central", "ductless", "window",
            "other_ac", "none", "unknown", "has_ac_pct_low", "has_ac_pct_high",
            "central_pct_of_known", "ducted_pct_of_known"])
        w.writeheader()
        w.writerows(rows)
    print("wrote %s" % os.path.relpath(out, REPO))


if __name__ == "__main__":
    main()
