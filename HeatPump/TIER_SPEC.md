# Heat pump performance tiers — specification (Phase 3c)

**Status:** specified 2026-07-26. Replaces the Phase 3a/3b NEEP-bucket tiers
(`pipeline/neep_buckets.py` → `pipeline/build_hp_curves.py`).

---

## 0. The design in one line

**AHRI certification is the sampling frame; manufacturer datasheets are the
measurement.**

The AHRI Directory tells us *which* heat pumps Canadians actually install and
lets us bucket them on certified ratings. It does **not** carry enough points
to simulate one — so the units it selects are then modelled from their own
published performance tables. Three independently-sourced, independently
checkable layers:

| Layer | Source | Answers |
|---|---|---|
| **Which models matter** | ERS/EnerGuide audit records | what Canadians install |
| **How to bucket them** | AHRI certificates + published program specs | which performance class |
| **How they behave** | manufacturer datasheets (NEEP fallback) | capacity & power vs. temperature |

The answer to *"why these models?"* is **because these are what Canadians
bought** — not because a vendor list said so. That is the core defensibility
claim, and it is why the AHRI layer exists at all.

---

## 1. Data sources

| Source | Role | Script |
|---|---|---|
| ERS/EnerGuide raw CSVs (`C:\ERS`) | selection weights | `Python/build_ahri_lookup_full.py` → `Python/ahri_numbers_all.json` |
| AHRI Directory API | certified ratings for bucketing | `Python/build_ahri_lookup_full.py` → `lookup/ahri_numbers.json` |
| NRCan Searchable Product List | HSPF2 **Region V**, ccASHP grouping, Canadian eligibility | `HeatPump/pipeline/fetch_nrcan_spl.py` |
| ENERGY STAR (Socrata `83eb-xbyy`) | compressor staging, market, vintage | `HeatPump/pipeline/fetch_energystar.py` |
| **Manufacturer datasheets** | **performance curves** | hand-fetched → `pipeline/build_datasheet_points.py` |
| **NEEP ccASHP listing** | **performance-curve fallback** | hand-fetched, per model, cited individually |

**Selection universe: 439,975 AHRI-number appearances in EnerGuide audit
records, across 15,148 distinct certified models.**

> **Wording discipline.** These are **record appearances**, not installed units.
> The count is occurrences of an AHRI value in the ERS `AHRI` column across all
> audit rows: a home audited twice counts twice, pre-/post-upgrade fields are
> not separated, and retrofit and new-construction records are pooled. It is a
> sound *popularity weight* and a poor *unit count*. Never write "installs".

### Source verification (2026-07-26)

- **ENERGY STAR carries no independent performance data.** On 3,447 models in
  both it and our AHRI scrape, 5 °F capacity agrees within 2% on **100%** of
  rows. It republishes AHRI figures; used for attributes only.
- **NRCan agrees closely but not perfectly.** On 4,435 models with capacity
  maintenance from both, median absolute difference **0.0047** (0.5 pp), but
  **17.0%** differ by >2 pp. AHRI is authoritative; NRCan *fills* gaps
  (+448 models, +23,615 appearances), never overrides.
- **Neither closes the coverage gap** — see §6.

---

## 2. The two bucketing axes

### Axis A — COP at 5 °F

| Band | Meaning |
|---|---|
| ≤ 1.8 | at the certification floor |
| 1.8 – 2.0 | modestly above |
| > 2.0 | well above |

1.75 is the shared floor across ENERGY STAR, CEE and NEEP, and **54.8% of
appearances report exactly 1.80** (81% fall in 1.7–2.1). Treating this as a
three-band ordinal is the honest reading of a floor-bunched variable; treating
it as continuous is not.

**Do not read this axis as "better".** COP > 2.0 holds the most models but the
fewest appearances (57,802 vs 144,754), and is the band most concentrated in the
*worst* capacity column. High reported COP tends to flag older or conservatively
rated units.

### Axis B — capacity maintenance

```
capacity_maintenance = Heating capacity at 5°F (MAXIMUM) ÷ Heating capacity at 47°F (RATED)
```

Bands: **< 0.60**, **0.60–0.80**, **≥ 0.80**.

Not invented here — it is the ratio ENERGY STAR v6.2, CEE and NRCan Greener
Homes all define, the last stating it as `(Max −15 °C [5 °F]) / (Rated 8.3 °C
[47 °F]) ≥ 70%`.

### Why the pairing works

- **Near-independent.** corr(COP, capacity maintenance) = **−0.168**, so the
  nine cells are genuinely distinct and all are populated.
- **Same measurement basis.** Both come from the max-capacity H4 test at 5 °F,
  so the pairing is internally coherent.
- **Shared error mode (caveat).** Because both derive from that one test point,
  an optimistically reported max point moves a unit diagonally up-right. Errors
  are correlated across the axes, not independent.
- **Little size skew.** Median rated capacity is 26–33 kBtu across all nine
  cells.

### The mixed-basis point (critical)

The 5 °F rating is at **maximum** capacity; 47 °F and 17 °F are **rated** points.
NEEP ccASHP Specification v4.0 is explicit ("COP at 5°F ≥ 1.75 at maximum
capacity operation"; 47/17 °F in the "Rated" reporting column, 5 °F in
"Maximum"). Consequence: **47.7% of models report 5 °F capacity above their
17 °F capacity** — correct and expected. A monotonicity filter would silently
discard ~180,000 appearances of valid data. **Do not filter on `cap5F ≤ cap17F`.**

Using datasheets for the actual curves dissolves this problem at simulation
time: datasheets publish capacity *and* power at both rated and maximum speed.

### Rejected

- **HSPF2 Region IV as an axis.** *Anti-correlated* with cold performance here:
  the ≥10 band retains less capacity (0.68) than the 9–10 band (0.77). It is a
  mild-climate seasonal average.
- **HSPF2 Region V** — the correct cold-climate seasonal metric (corr 0.508 vs
  0.449), NRCan-only, 68.9% coverage. Not an axis; used as a validation and as
  a COP-curve constraint where datasheets are unavailable.
- **Compressor staging** — directionally right (0.82 variable vs 0.51
  single-stage) but 99.1% of the base is continuously variable, so it does not
  separate. Validation only.
- **AHRI's `cold_climate` flag as a cut** — 99.8% precise but under-reports
  badly: **91,431 appearances** meet ≥70% while flagged `No`, because the
  designation post-dates their certificates. Kept as a reported attribute.

---

## 3. The grid

Record appearances, screened to COP ≤ 3.0 and cm ≤ 1.30 (see §6):

| | cm < 0.60 | 0.60 ≤ cm < 0.80 | cm ≥ 0.80 | **Total** |
|---|---:|---:|---:|---:|
| **COP ≤ 1.8** | 3,542 | 72,647 | 68,565 | **144,754** |
| **1.8 < COP ≤ 2.0** | 2,949 | 29,017 | 82,534 | **114,500** |
| **COP > 2.0** | 6,428 | 20,711 | 30,663 | **57,802** |
| **Total** | **12,919** | **122,375** | **181,762** | **317,056** |

72.1% of the 439,975-appearance universe; the rest lack a 5 °F point (§6).

---

## 4. Representative selection

Per cell × capacity band (`<18k`, `18–30k`, `30–42k`, `≥42k` Btu/h rated at
47 °F): **the most-frequent model in the ERS records, preferring `Active`
certification status.** All 36 resolve to Active units.

Selection quality: **30 of 36 sit within 0.08 of their cell's
appearance-weighted median cm.** Six are off-centre; the ones worth re-picking
are in high-volume cells (notably `1.8–2.0 × ≥0.80 × 18–30k`, a 41,463-appearance
cell whose rep sits at 0.80 vs a 0.89 median). Five cells are thin (<500
appearances), all in the `cm < 0.60` column.

**Substitution:** `>2.0 × <0.60 × <18k` originally selected 210727629 (COSTWAY
FP10293US-12WH). Its cm of 0.20 is not a credible rating and the brand is
unlisted. Use **212387098** (RHEEM RP15AZ30AJ2N, cm 0.57, ccASHP + NRCan listed).

### Which value governs

Datasheet figures will not exactly match the certificate. The rule:

- **AHRI governs bucket assignment** — keeps selection reproducible and
  traceable to a public certificate; a unit cannot silently migrate buckets when
  better data arrives.
- **Datasheet governs simulation** — it is the measurement.
- **Record the delta per unit** so a reviewer can see it.

Stated claim: *"selected as the most-installed model in its bucket per AHRI
certification; simulated using the manufacturer's published performance table."*

---

## 5. Curve sourcing — what datasheets actually provide

Audited 2026-07-26 against real submittals.

**The best datasheets give everything needed, and more than any ratings
database.** Manufacturers who publish an **EXTENDED RATINGS / HEATING
PERFORMANCE** table give capacity, COP *and* power input at 20+ outdoor
temperatures at maximum output. Confirmed for the GREE FLEXX Ultra submittal
covering GUD36W/A-D(U) (AHRI 211644151 / 206249117 / 206249116):

- **23 heating points from −22 °F to 75 °F (−30.0 °C to +23.9 °C)** — capacity
  (Btu/h), COP, and power input (W) at every point
- **COP is internally consistent**: stated COP matches capacity ÷ (3.412 × power)
  to 2 dp on all 23 points
- **Minimum operating temperature**: "Heating Temperature Range −22 – 75 °F"
- The **AHRI reference number is printed on the sheet**, confirming the
  certificate↔datasheet mapping directly rather than by inference

That is strictly richer than AHRI (3 capacity points, 1 COP), ENERGY STAR or
NRCan, and it resolves `min_op_temp_C` — previously the outstanding blocker.
For units with such a table, **no other source is required.**

> ⚠️ **These tables are easy to miss.** In the GREE sheet the table extracts as
> bare numbers with the column headers detached at the foot of the page, so a
> keyword scan for "Power Input" or "COP" against the page text returns nothing
> useful and the document looks like it has no performance data. An earlier pass
> of this spec wrongly concluded that manufacturer submittals do not publish
> power-vs-temperature and that NEEP would be needed for every unit. **Always
> dump the full text of every page before concluding a datasheet lacks a table.**
> `pipeline/extract_datasheet_tables.py` automates the parse and cross-checks the
> COP column against capacity/power, refusing to write on a mismatch.

**Coverage is manufacturer-dependent.** Three observed levels:

| Level | Example | What you get |
|---|---|---|
| **Full extended ratings** | GREE FLEXX Ultra (GUD36W/A-D(U)) | cap + COP + power at 23 temps; nothing else needed |
| **Partial** | Mits Air / MDV MOD30-24 | COP at 47 °F (3.32) and 5 °F (1.95), min/rated/max capacity at both, HSPF2 Region IV **and V**, lock-out −22 °F |
| **Rated only** | LG LSU120HSV5 submittal | capacity at 17/5/−4 °F as % of rated, single rated power input — no COP curve |

Order of preference per unit:
1. **Manufacturer extended-ratings table** — capacity + COP + power. Preferred.
2. **Manufacturer engineering manual / product data book** — LG, Daikin and
   Mitsubishi publish full tables here even when the 2-page submittal does not.
   Check this before falling back.
3. **Submittal (capacity + lock-out) + NEEP (power/COP)** — hand-fetched per
   model, cited individually.

**Watch the certificate variant.** The Mits Air submittal for MOD30-24HFN1-MW
cites AHRI **211911381**, not 208101910 — the same model certified in a different
combination. Match the sheet to the AHRI number actually in the ERS records, or
record which variant was used.

### Datasheet-vs-certificate delta (worked example)

GREE GUD36W/A-D(U), AHRI 206249117:

| | Datasheet | AHRI certificate |
|---|---:|---:|
| capacity maintenance (5 °F ÷ 47 °F) | 30,000 / 38,000 = **0.789** | **0.80** |
| COP @ 5 °F | **1.83** | **1.80** |

Small and in the same direction — consistent with the §4 rule (certificate
governs bucket, datasheet governs simulation) rather than a contradiction.

### Status

| AHRI | Model | Appearances | Curve data |
|---|---|---:|---|
| 211644151 | GREE GUD36W/A-D(U) | 11,555 | ✅ **complete** — 23 pts, extracted |
| 206249117 | GREE GUD36W/A-D(U) | 9,146 | ✅ **complete** — 23 pts, extracted |
| 206249116 | GREE GUD36W/A-D(U) 24k | 2,253 | ✅ **complete** — 23 pts, extracted |
| 208101910 | MDV MOD30-24HFN1-MW | 4,389 | ⚠️ partial — 2 COP pts + lock-out; check cert variant |
| 10570123 | LG LSU120HSV5 | 4,182 | ❌ try LG engineering manual, then NEEP |
| 204825178 | LG LAU120HYV3 | 2,089 | ❌ try LG engineering manual, then NEEP |

The three GREE entries share one submittal and are written to
`data/interim/datasheet_points_v2.json`.

**LG note:** the LSU120HSV5 submittal's "built-in low ambient standard, down to
14 °F" is qualified **(cooling mode)** — it is *not* the heating lock-out. Do not
use it as `min_op_temp_C`.

### Two traps found while building the first curves (2026-07-26)

**1. Normalize on the certificate's rated 47 °F, not the datasheet's.** The
datasheet 47 °F figure is a *maximum-output* capacity; `cap_frac_of_rated47`
means fraction of the *rated* point, which is what the user's nominal-capacity
input represents. Normalizing on the datasheet value understates every fraction
— by 6% for the GREE sheet but **43% for the MOOVAIR chart**.
`build_unit_curves.py` now uses the AHRI certificate's rated 47 °F as the
denominator, falling back to the datasheet only when no certificate value
exists. `cap_frac` consequently exceeds 1.0 near 47 °F, which is correct:
maximum output is above the rated point.

**2. One model name can span several certified combinations.** The same outdoor
unit certified against different indoor coils gets different AHRI numbers *and
different rated capacities*. AHRI 206249116 is a GUD36W/A-D(U) rated 24,000
Btu/h — applying the 36,000 Btu/h extended-ratings table to it is simply wrong.
The builder now rejects any unit whose datasheet 47 °F max exceeds **1.35×** the
certificate's rated 47 °F as a probable combination mismatch. This caught 2 of
the first 5 units. **Match the sheet to the certified combination, not just the
model string.**

### Sourcing outlook for the 36

| Outlook | Count | Basis |
|---|---:|---|
| **Good** — ccASHP-flagged + NRCan-listed, near-certainly on NEEP | 20 | includes both volume leaders |
| **OK** — not ccASHP, but a major brand publishing submittals | 13 | Lennox, Trane, Mitsubishi, Rheem, Goodman, Midea, LG, TOSOT, GREE |
| **Risk** — niche brand, no ccASHP listing | 3 | NOVAIR LEA27MZ, Bladex BX24-HP15ECO, COSTWAY (substituted out) |

**Structural constraint:** the entire `cm < 0.60` column is non-ccASHP. NEEP
lists only cold-climate-qualifying products, so by construction the worst
performance band can never be NEEP-covered — those four cells depend entirely on
manufacturer submittals. Three of the four are major brands.

### Fetch priority

1. **211644151** (GREE GUD36W/A-D(U), 11,555) and **206249117** (same family,
   9,146) — anchor the COP ≤ 1.8 row holding 46% of the base
2. **208101910** (MDV, 4,389), **10570123** (LG LSU120HSV5, 4,182),
   **206249116** (GREE, 2,253), **204825178** (LG LAU120HYV3, 2,089)
3. Remaining 14 Good-outlook units
4. The 13 major-brand submittals, `cm < 0.60` column last

A working 6-unit tool covering the dominant scenarios needs only steps 1–2.

---

## 6. Known limitations

1. **27.9% of the universe has no 5 °F point** and cannot be bucketed. This
   group is **99.2% Discontinued/Delisted, 0.0% ccASHP-flagged, 0.0% on new
   refrigerants** — genuinely pre-designation equipment. It is a market-vintage
   problem, not a source-selection one: neither ENERGY STAR (recovers 59 models)
   nor NRCan (350 models) can cover units that left the market. Report it as a
   coverage statement, not as a tier.
2. **Implausible ratings exist and are screened**, not silently kept: COP > 3.0
   (6 models, 1,975 appearances — the LG LAU120HYV family reports 5.97) and
   cm > 1.30 (21 models, 3,040 appearances — FUJITSU AOUG09LZAH1 reports 1.71).
3. **Refrigerant is not a usable scenario lever from this selection.** The 36 are
   29 R-410A / 4 R-32 / 3 R-454B, mirroring a base that is ~1.5% R-32 and ~1.3%
   R-454B — and refrigerant is confounded with vintage and performance
   (R-32/R-454B show cm 0.83–0.86 vs 0.68 for R-410A). Any "refrigerant effect"
   extracted here is a modernity effect. A refrigerant axis needs a deliberately
   **matched** set (same capacity, same staging, different refrigerant).
4. **Bucket assignment is scrape-date dependent.** AHRI amends certificates
   retroactively (confirmed 2026-07-22: 211644151's cold-climate designation
   flipped No→Yes). Entries carry a `_checked` date; rotated by
   `Python/refresh_ahri_lookup.py`.
5. **Appearance counts are not split by retrofit vs. new construction.** The scan
   reads a single `AHRI` column across all ERS rows. Splitting needs the
   evaluation-type column added to `scan_candidates()` and a re-scan.
6. **The `cm < 0.60` column is historical.** Only 6–24% of its models are Active
   and several cells have <10 appearances on the top unit. Valid as scenarios,
   not as "typical Canadian install".
7. **This grid does not describe the frontier.** Screened against the **US DOE
   Cold Climate Heat Pump Challenge** specifications (2026-07-27,
   `pipeline/screen_cchp.py`), **4 models — 8 of 439,975 appearances — clear
   every checkable criterion**, and none of the four is a cell representative.
   The grid is a description of the *installed* base, which is a historical
   record; it is not evidence about what today's best equipment can do. Method,
   caveats and the four qualifying units: METHODOLOGY.md, "US DOE Cold Climate
   Heat Pump Challenge screen".
8. **The rep is a thin proxy in most cells.** In the largest cell (13.1% of the
   screened base) the representative carries ~11% of its own cell's appearances,
   chosen from 748 models; in the four `1.8–2.0 × cm<0.60` cells the reps carry
   **6 to 16 appearances each**. Those are the least-arbitrary pick available,
   not representatives in any statistical sense. The page must not present all
   36 as equivalent.
9. **396 bucketed models have no rated 47 °F capacity** and so get a COP×cm cell
   but no capacity band — **10,738 appearances, 3.39% of the screened base**,
   absent from the 36-cell table. Named here per the never-silently-drop rule.

---

## 6.1 Real installs vs. design load — does a sizing default make sense?

Quick check (`HeatPump/pipeline/check_hp_sizing_correlation.py`, 2026-07-29)
ahead of adding a tier x capacity-band dropdown pair to the engine: does
installed capacity track the home's own design heat loss closely enough to
suggest a default?

Of 311,535 ERS homes that added a heat pump this retrofit (7 provinces),
178,263 (57.2%) have both a post-retrofit design heat loss (`Post_HeatLoss`)
and an AHRI-certified installed capacity at 47F (`Post_HPCapacity47` —
the validated field; the auditor-entered `HPCAP` runs a median ~1.6x high and
is not used here — see docs/RETROFITS.md's Step 1b for the full validation,
including the finding that the ERS `COP` field is rated at 47F rather than
5F). Capacity/design-load ratio: **median 0.66**, IQR [0.50, 0.86],
10–90th percentile [0.37, 1.11].

- **68.7%** of installs are undersized (ratio < 0.8) against the home's own
  design load — the heat pump is deliberately (or by installer habit) smaller
  than what would cover the coldest design day alone, leaning on backup.
- **24.0%** land within ±20% of the design load.
- **7.2%** are oversized (ratio > 1.2).

**Conclusion for the engine UI:** real installs do not cluster near "capacity
= design load." A single suggested-default ratio would misrepresent the
market — the tier/capacity-band dropdowns should let a user freely pick above
or below their design load without an implied "correct" answer, and any
default shown should be framed as the median (0.66x, i.e. undersized) rather
than 1.0x, or left unset. Chart: `data/interim/hp_sizing_correlation.png`.

**Caveat:** 42.8% of HP-addition homes are excluded for a missing
`Post_HPCapacity47` (AHRI lookup didn't resolve their `Post_HPAHRI`) — the
same lookup-coverage gap documented elsewhere in this file. Not necessarily
representative of the excluded homes' true sizing.

---

## 7. Reproducing

```bash
python HeatPump/pipeline/fetch_nrcan_spl.py
python HeatPump/pipeline/fetch_energystar.py
python Python/build_ahri_lookup_full.py --no-scan --backfill-field sold_in
```

The third backfills newly-mapped AHRI fields into already-resolved entries (the
default run skips them). ~12,500 fetches at 1 req/s, checkpointed after every
fetch, safe to interrupt. `atomic_write_json` retries the rename with backoff —
a long run previously died on a transient Windows file lock at 5,564/12,562.

### ⚠️ Reproducibility gap — this spec is not currently reproducible (2026-07-27)

Two inputs the repo's *"what must be defensible is the process, not the bytes"*
rule does **not** currently cover:

1. **`data/interim/hp_units_joined.csv`** — the joined 15,148-model universe
   (`k,w,cm,cm_ahri,cm_nrcan,h5,pg,h4,cop,cc,c47`) that the §3 grid, the §4
   representative selection **and** `pipeline/screen_cchp.py` all read. **No
   producer script exists anywhere in the repo** — grepping the filename returns
   nothing. It was built ad hoc in an earlier session.
2. **`lookup/ahri_numbers.json`** — the AHRI scrape itself. Gitignored *and*
   absent from local disk. Only the derived `Python/ahri_numbers_all.json`
   survives, and that carries bare appearance counts with no certified ratings.

Every other generated tree here is safe to lose because a script rebuilds it.
These two are not: deleting `hp_units_joined.csv` would strand Phase 3c, and the
§7 commands above do **not** regenerate it.

**Fix before the next refresh:** write the join as a real pipeline step under
`HeatPump/pipeline/`, and confirm the weekly `ahri-refresh.yml` Action still
restores `lookup/`. Tracked in [ROADMAP.md](../ROADMAP.md), Queued.
