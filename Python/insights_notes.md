# Retrofit Insights — findings memo

Grounding notes for the Phase 2 page copy (`retrofit-insights.html`). Every
number here comes from `insights_json/` built by `build_insights.py` on
2026-07-19 over the 1,451,433 matched before/after ERS pairs. **Read the
honesty rails in `meta.json` before writing copy** — several of the strongest
"findings" below are composition artifacts, flagged explicitly.

Cross-checks that passed: national matched total = **1,451,433** (== sum of
province parquet rows == the 1.45M Gate-A pairing number); L3R / K2P / M5V median
saving % identical to `fsa_json/ON/_index.json`; national dwelling-weighted
median household income **≈ $82,000** vs StatCan 2020 published ≈ $84k.

---

## 1. The 30-second national picture

- **Savings rise cleanly with the number of measures**, and this is the
  single most robust relationship in the data:

  | # measures | n | median saving % |
  |---|---|---|
  | 0 | 118,282 | 3.3 |
  | 1 | 439,293 | 16.2 |
  | 2 | 438,306 | 19.8 |
  | 3 | 227,828 | 25.4 |
  | 4 | 96,977 | 33.5 |
  | 5 | 36,702 | 43.2 |
  | 6 | 10,394 | 53.8 |
  | 7–8 | 1,523 | ~62–69 |

  This is close to mechanical (more measures → more modelled savings) but it is
  the honest headline: depth pays, and most homes (64%) did only 1–2 measures.
- **Zero-measure pairs = 118,282 (8.6% of all pairs)** with a median "saving"
  of 3.3%. This is the audit-noise population the methodology warns about — a
  re-audit with no tracked upgrade. They are **excluded from every "what
  worked" statistic** (bundles, top-decile, climate/equity saving medians) and
  reported only as a count. Copy should say the "what worked" panel is built on
  the **1,251,023 nonzero-measure pairs**.

## 2. What actually worked (nonzero-measure pairs)

- **Heat pump alone** is the single most common upgrade (141,677 pairs) and a
  strong performer on its own: **25.5% median saving**, well above the
  2-measure average. "Heating system change alone" (114,307 pairs) delivers
  20.1%. By contrast **windows alone** (66,744 pairs) delivers only **6.1%**,
  and **air-sealing alone** 7.9% — the classic "shell tweak without a mechanical
  change barely moves modelled energy" result. Good pull-quote material: *the
  same effort spent on a heat pump saves ~4× what windows-only saves.*
- **Top-decile savers (≥ 40.6% saving, 125,103 pairs) vs the rest**:

  | | top decile | rest |
  |---|---|---|
  | median pre-EUI (kWh/m²) | 271 | 199 |
  | median year built | 1960 | 1976 |
  | mean measure count | 3.5 | 2.0 |
  | fuel-switch share | **26.8%** | 6.2% |
  | heat-pump share | **57.9%** | 22.7% |
  | air-sealing share | 66.2% | 49.5% |

  The profile of a big saver is consistent and worth stating plainly: **an
  older, worse-performing home (built ~1960, high starting EUI) that did more
  measures, switched fuel, and added a heat pump.** Starting-EUI headroom +
  fuel switch + heat pump is the recipe. Floor insulation is rare everywhere
  (~2%) and not part of the story.

## 3. Geography — who leads each metric (min n = 30)

- **Worst starting stock (pre-EUI):** Winnipeg core dominates — **R3B (475),
  R3A (446), R3G, R3E, R3L** — plus Regina S4P (403). Old, cold, gas/electric
  prairie stock. R3B's 475 kWh/m² is an extreme; sanity-noted, not dropped.
- **Highest pre-retrofit GHG:** almost entirely **Nova Scotia** — B3H (18.6),
  B2H, B3K, B0R… — because NS pairs oil heat (63% of NS homes) with a
  coal-heavy grid. This is a **grid + fuel composition** effect, not "NS homes
  waste the most energy." Flag on-page.
- **Highest heat-pump adoption:** Saguenay / rural Quebec (**G7T 0.97, G6A,
  G5Z, G6S**) and coastal BC/NL. See §5 — this is provincial, not local.
- **Highest median saving %:** small northern/rural FSAs — V0T (45.7, northern
  BC), P0W/P9A (northern ON), A1C/A1Y (St. John's NL). Small-n, deep-retrofit-
  heavy; keep the min-n note visible.
- **Lowest participation:** downtown high-rise cores — **M5V, M4Y, M5B, M5J
  (downtown Toronto), V5H, H3S** — where "dwellings" are condo units that never
  get an EnerGuide house audit. Expected denominator effect, not apathy.

## 4. Timeline — the two peaks map onto the two big programs

- **Initial (D) audits peak in 2009 (233,117)**, with 2008–2010 all >100k —
  the **ecoENERGY Retrofit–Homes** era (2007–2012, up to $5,000/home, pre+post
  audit mandatory).
- **Completed retrofits (E-year) peak in 2023 (150,798) and 2024 (144,817)** —
  the **Canada Greener Homes Grant** era (launched May 2021, closed to new
  applicants 31 Mar 2024). The post-2024 fall-off is already visible (2025
  72,870; 2026 partial).
- The **1998–2007 EnerGuide-for-Houses** ramp and the **2012–2021 provincial/
  utility gap** (no single national program — deliberately *not* annotated with
  a fabricated program) are both visible as lower-volume stretches. Annotations
  + source URLs are in `timeline.json`.

## 5. Correlations that are COMPOSITION, not causal — flag every one

These read like findings but are provincial mix effects. The page must caveat
them (the ecological-fallacy rail):

- **"Lower-income FSAs adopt more heat pumps."** Income Q1 HP rate 34.7% vs Q5
  19.0%; dwelling-value Q1 39.2% vs Q5 18.8%. This is **entirely provincial
  composition**: HP adoption by province is NB 50%, QC 45%, NL 43%, NS/BC 35%
  vs ON 14.5%, MB 8%, AB 3%, SK 2%. The cheap-housing quintiles are
  Atlantic/Quebec-heavy — regions with electric/oil heat, cheap hydro, and
  aggressive provincial HP rebates. It is **not** evidence that poorer
  *households* buy more heat pumps. Same mechanism inflates Q1 fuel-switch and
  Atlantic pre-GHG.
- **"Participation rises with income."** Income Q1 11.6% → Q5 16.4%. Real
  direction but weak and partly a denominator/tenure effect (higher-income FSAs
  = more owner-occupied detached homes eligible for a house audit). State as
  suggestive, not strong.
- **HDD band vs heat-pump adoption is non-monotonic** (0.29 at <3500, 0.20 at
  3500–4500, **0.34 at 4500–5500**, 0.12 at 5500–6500). The 4500–5500 bump is
  the **Quebec** band; the 5500–6500 trough is the **prairies** (AB/SK/MB). Do
  **not** present as "colder → more/fewer heat pumps" — it tracks province, not
  temperature. Same for the CDD gradient (high-CDD = southern-ON gas country →
  low HP).
- **Starting EUI falls as income rises** (Q1 220 → Q5 172 kWh/m²): plausible
  (newer, better-maintained stock in richer FSAs) but still ecological.

## 6. Artifacts / data-quality notes

- **J5N (QC) participation = 6.19** — extreme outlier. Census total_dwellings
  = 83 but 514 audited homes. A tiny-denominator FSA (likely a small rural
  postal area whose 2021 dwelling count badly undercounts the audited stock).
  Participation > 1 also occurs legitimately for L0N (0.95), V7Z (0.92), B1W
  (0.71) — cumulative ~20yr audits over a one-year snapshot. **The map should
  cap/annotate participation, not show a raw 6.19.** Recommend clipping the
  choropleth colour scale at ~1.0 and flagging >1 explicitly.
- **1,684 FSAs have matched pairs but only 1,646 have census and 1,634 have
  climate** — ~40–50 FSAs (mostly territorial / retired postal codes) carry
  null participation/income/HDD. All fields are null-safe; the page must
  threshold on `n` and skip nulls.
- **Participation denominator mixes geographies**: ERS audits a *house*; census
  `total_dwellings` includes condo/apartment units that never get one. Dense
  urban FSAs therefore read artificially low (see M5V 0.002). This is the
  single biggest interpretation trap on the participation metric.
- Every saving/EUI/GHG number is a **modelled HOT2000/EnerGuide estimate**, not
  a metered bill. Never call it "measured."

## 7. Missed-opportunity ranking (composite; weights in `opportunity.json`)

Score = 100·(0.30·pctile(pre-EUI) + 0.25·pctile(pre-GHG) + 0.20·pctile(pre-1980
share) + 0.25·(1−pctile(participation))), over 1,553 FSAs with n ≥ 30. Top of
the list is **old urban cores that have barely participated**: R3B/R3A/R3C
(Winnipeg, 92.0/88.5/89.6), E2L (Saint John, 91.1), T5G/T5B (Edmonton core,
90.5/89.0), P2N (Kirkland Lake, 90.0), S4P (Regina, 89.6), M4X (downtown
Toronto, 87.9). These are defensible "where programs should look next"
candidates — worst stock + lowest uptake. **Screening-tool caveat:** high
pre-EUI is a modelled screening signal, and low participation partly reflects
the condo-denominator issue above, so this is a prioritisation heuristic, not a
verdict on individual homes. Per-FSA factor breakdowns are emitted so the page
can show *why* an FSA ranks where it does.

---

### Suggested section "so what" lines (from the numbers above)

- **Success:** "Depth beats breadth — a heat pump alone saves 25%, windows
  alone 6%, and each added measure lifts the median another 5–10 points."
- **Climate:** "What looks like a climate effect is mostly a provincial one —
  Quebec's heat-pump boom, not colder winters, drives the mid-HDD spike."
- **Equity:** "Cheaper neighbourhoods show more heat pumps — but that's
  Atlantic Canada and Quebec in the data, not lower-income households; read it
  as geography."
- **Opportunity:** "The worst-performing, least-touched stock clusters in
  Winnipeg, Edmonton, Saint John and Regina's older cores."
