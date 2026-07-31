# Build brief — national incremental retrofit-cost pipeline

*A prompt for a Claude Sonnet coding agent. Hand this whole file to the agent as
its task. It is written to be self-contained, but the authoritative methodology
is [`docs/RETROFIT_COSTS.md`](RETROFIT_COSTS.md) — read that first and treat it as
the spec; this brief is the productionisation plan around it.*

---

## Your objective

Take the **PEI proof-of-concept** that attaches an **incremental** dollar cost to
every ERS/EnerGuide retrofit record, and turn it into a **production pipeline that
runs for all of Canada** (all 12 provinces/territories present in the ERS extract),
wired into this repo's standard architecture, with one self-contained HTML page and
committed JSON, plus the two-audience methodology.

"Incremental" = the *extra* cost over the business-as-usual (BAU) choice a homeowner
would have made anyway — not the full invoice. The model is already designed and
documented; your job is mostly generalisation, productionisation, and the open
decisions below — **not** re-inventing the method.

## Where things stand (read before touching anything)

- **Methodology (source of truth):** [`docs/RETROFIT_COSTS.md`](RETROFIT_COSTS.md).
  Read the *Incremental cost model* section end to end. It defines, per measure,
  the BAU baseline and the exact formula (insulation & air sealing = full cost;
  windows = efficient(post pane) − standard(pre pane) per window on vinyl, floored
  at 0; ASHP = ASHP − gas furnace − A/C, may be negative).
- **POC scripts** (PEI only, working reference implementation) live in a scratchpad
  from an earlier session:
  `…/Temp/claude/C--Energy/df574aff-…/scratchpad/` — `pei_extract_fields.py`,
  `pei_price_audit.py`, `build_methodology_data.py`, `build_review_page.py`,
  `methodology_template.html`, `review_template.html`.
  **If that path is gone**, reconstruct from `docs/RETROFIT_COSTS.md` — the method
  is fully specified there. Either way, do **not** ship the scratchpad scripts
  as-is; re-home them into `Python/` per the architecture rules below.
- **Inputs that already exist on disk:**
  - `C:\ERS\web\ers_web_<PROV>.parquet` — the paired pre/post retrofit records for
    every province (output of `Python/ers_web_pipeline.py`; already regenerated after
    the `join_hp_capacity.py` capacity/SEER change).
  - `C:\ERS\*.csv` — the raw per-year ERS extracts (433 columns) needed for the extra
    fields the pipeline doesn't surface (footprint, window/pane codes, pre-heating,
    cooling presence, etc.).
  - `retrofits/USCosts/REMDB_2024.12.23.xlsx` (`Machine Read` sheet) and
    `Envelope Measures_Active_7-12-24.xlsx` (`Windows Data` sheet — the raw rows the
    standard/efficient window premium is built from).
  - `Support.xlsx` → `WindowCodes` / `Frame` sheets decode the 6-digit window code
    (digit 1 = glazing/pane, digit 6 = frame material).
- **Pattern to follow for a national page:** the existing **Retrofit Explorer**
  (`retrofits.html` + the `fsa_json` tree) already renders national ERS retrofit
  data aggregated by FSA/province. Mirror that shape — see "Aggregation" below.

## Architecture invariants (non-negotiable — from `CLAUDE.md`)

- **Offline Python pipeline → compact committed JSON → one self-contained HTML page.**
  No backend, no build step, no npm, no CDN, no external runtime deps. Don't propose
  a framework.
- **Where things go:** ETL in `Python/` (module docstring naming inputs/outputs/
  sources); generated data in `retrofit_cost_json/` (or a name matching the page);
  page at repo root (e.g. `retrofit_cost.html`); shared theme/CSS in `assets/`; doc
  at `docs/RETROFIT_COSTS.md`; a tracker line in `ROADMAP.md` + `project-atlas.html`.
- **Two branches.** Code/docs on `main`; the published site + every generated data
  tree on `gh-pages` (one force-pushed orphan commit). Generated trees are
  **gitignored on `main`** and live on local disk only — losing them is fine, you
  re-run the pipeline. `BASE_URL` is `'./'` everywhere; `.nojekyll` is mandatory.
- **Every page carries two methodologies:** a *simple* one (plain language, no
  jargon, no per-m² units) and an *advanced* one (formulas, raw field names like
  `NUMDWELLINGUNITS`/`Pre_HeatLoss`, vintages, caveats), cross-linked to the doc.
- **Data-honesty rails:** never silently drop records — quantify every drop and name
  the gate. Distinguish **measured vs modelled vs assumed** in the display. Label
  sample sizes; suppress small-n cells. Show gaps rather than interpolate.
- **Don't overcomplicate.** Simple and defensible to a skeptical energy engineer
  beats sophisticated and unfalsifiable. Prefer a method you can explain in two
  sentences on the page itself.

## What "national" actually changes (the real work)

1. **Run for all provinces, not just PE.** Loop `ers_web_*.parquet`; stream the raw
   `C:\ERS\*.csv` once, keeping all provinces (the POC filtered `PROVINCE == 'PE'`).
   Expect **millions** of paired records — vectorise the pricing (the POC uses
   per-row Python loops that are fine for 12k PEI rows but will not scale). Watch the
   DataFrame-fragmentation warnings the POC already emits.

2. **Kill the PEI-specific assumptions.** Several POC choices were tuned to PEI and
   must be generalised or made province-aware — see "Decisions to confirm" (they are
   material, so confirm with the user before building, per the repo working agreement):
   - **ASHP fallback class** defaulted to `Non-ducted, single-zone` because PEI is
     ~15:1 ductless. Other provinces differ. Derive the fallback **per province** from
     each province's own recorded `HPEquipType` mix, or handle explicitly.
   - **Gas-furnace BAU** is a uniform assumption. On PEI (72% oil) it's already a
     national-convention proxy; nationally, fuel availability and dominant heating
     type vary a lot (QC electric, ON/AB gas, Atlantic oil). Decide: keep uniform gas,
     or make the BAU heating province/fuel-aware.
   - **A/C credit type** is driven by ducted-vs-ductless because PEI has ~no recorded
     central A/C (`ACCENTESTAR` empty province-wide). Other provinces *do* record
     central A/C — use `ACCENTESTAR`/`ACWINDNUM` where populated, fall back to the
     ducted/ductless rule otherwise.

3. **Aggregation, not per-home.** The PEI review page embedded ~11k homes at 12.6 MB.
   A national per-home payload would be hundreds of MB — do **not** ship that. The
   production page should aggregate to **FSA and province** (counts, medians,
   p10–p90 per measure and total, incremental), matching the Retrofit Explorer's
   `fsa_json` shape, with small-n suppression. Keep a per-home export as an optional
   local artifact only.

4. **The USD→CAD gap is now front-and-centre.** REMDB is **2023 US dollars**, US
   retail/contractor pricing, with **no** CAD conversion and **no** Canadian-labour
   adjustment anywhere in the POC. That was tolerable for a PEI sketch; for a national
   tool "defensible to a skeptical Canadian engineer" it is the single biggest
   credibility gap. This must be decided and, if applied, documented as measured vs
   assumed (see decisions).

## Decisions to confirm with the user *before* building

Surface these first (the working agreement requires confirming material choices):

1. **Currency & labour.** Apply a USD→CAD conversion and/or a Canadian-labour/market
   adjustment, or keep 2023 USD with a loud caveat? If adjusting, what source
   (Bank of Canada FX for the vintage; a labour-cost differential — cite it)?
2. **BAU heating fuel.** Keep the uniform gas-furnace baseline nationally, or make it
   province/fuel-aware (e.g. baseboard where electric dominates, oil where oil
   dominates)? REMDB has Gas Furnace, Gas/Oil Boiler, Electric Baseboard rows but
   **no** oil-furnace/electric-furnace/wood rows.
3. **ASHP fallback class** per province: derive from each province's recorded mix, or
   a single national default?
4. **Aggregation grain** for the page: FSA + province (recommended), province only, or
   FSA + province + optional per-home drill-down?
5. **Fix `Windows_Change` at source.** The pipeline flags window changes by comparing
   `WINDOWCODE` as raw text, so `201030.0` vs `201030` reads as a change (22% of PEI
   "changes" are this artifact). The POC fixes it downstream only. For a national build
   fix it properly at `Python/ers_web_pipeline.py:591` (normalise before `!=`) — this
   also corrects the **Retrofit Explorer**. Confirm you may touch the shared pipeline
   and plan the 12-province re-pair.

## Build plan / deliverables

Produce, all following the architecture rules:

- **`Python/` modules** (replacing the scratchpad scripts), each with a docstring
  naming inputs/outputs/sources:
  - a national **field extractor** (raw ERS → the extra columns: footprint, window
    codes, `NUMWINDOWS`, `BASEMENTFLOORAR`, pre-heating `Pre_HeatLoss`/type/fuel,
    cooling `ACCENTESTAR`/`ACWINDNUM`/`ERSSPACECOOLENERGY`), keyed on the pair
    `(HOUSEID, Pre_Date, Post_Date)` as the POC does;
  - a **pricing** module implementing the incremental model (vectorised), emitting
    per-record low/mid/high per measure + total, with explicit `{measure}_priced`
    masks (incremental values can be ≤ 0, so never key off `>0`);
  - a **window price-table** builder (trimmed median $/ft² by frame/pane/class from
    the raw `Windows Data` sheet, triple-pane pooled — already specified in the doc);
  - an **aggregator** → the committed `retrofit_cost_json/` tree (FSA + province
    stats), small-n suppressed;
  - a **page-data** builder feeding the HTML.
- **One self-contained HTML page** at repo root, theme-consistent with the other
  tools, with the two methodologies (simple + advanced) and a measured/modelled/
  assumed legend. Port and finish the methodology explainer — **including rewriting
  its interactive calculator to compute the *incremental* value live for windows and
  ASHP** (the POC page's calculator still shows full component pricing behind a
  "one component vs incremental" clarifier; production should show the real
  increment).
- **`docs/RETROFIT_COSTS.md`** updated from POC to production status (national numbers,
  final decisions, changelog entry with the *why*).
- **`ROADMAP.md`** line (+ `Updated YYYY-MM-DD`) and **`project-atlas.html`** entry.
- **Deploy** to `gh-pages` per `CLAUDE.md` (full `./deploy.sh` if you have all data
  trees locally, else the documented incremental single-tool `gh-pages` update). Verify
  live with `curl`/browser before declaring done.

## Data-honesty & QA requirements

- Report, per province and nationally: paired records, records priced (per measure and
  any-measure), and every **drop** with the gate that caused it (multi-dwelling
  exclusion, phantom window changes, missing capacity, unrecognised heating type, etc.).
- Keep the existing gates: exclude multi-dwelling `BldgType` (Apartment/Duplex/Triplex);
  drop phantom `Windows_Change` (numeric-equal codes); floor the window premium at 0.
- Tag every assumed vs reported value (frame/pane fallbacks, ASHP class source, BAU
  fuel) so the display can distinguish them — mirror the POC's `*Source` columns.
- Sanity gates to check before shipping: window incremental median in a believable band
  (~$6k on PEI, expect provincial variation); ASHP incremental sensible and only
  negative where the ASHP genuinely beats furnace+A/C; insulation/air-sealing unchanged
  from full cost; national totals not dominated by any one province artifact.

## Known traps (save yourself the debugging)

- **Preview renderer has no `requestAnimationFrame`.** Chart.js paints blank and
  screenshots time out; use `animation:false` + a forced draw and verify by sampling
  canvas pixels, not screenshots. Smooth scroll never moves — use `behavior:'instant'`.
  Files outside the project folder render as static (non-scripted) snapshots — serve the
  repo over `http://localhost` (there's a `static` launch config) to run page JS.
- `Pre_HeatLoss` is design heat loss in **kW** (median ~13) — convert ×3412 to BTU/hr
  for REMDB's Gas Furnace metric; it is not the furnace's actual nameplate capacity.
- Window/heat-pump `UGR*` fields are the *proposed* upgrade, not as-built — price from
  the base-case `WINDOWCODE`/`HPEquipType` (the E-row), as the POC's variant B does.
- REMDB's non-vinyl window rows are sparse and commercial-grade (an aluminum "standard"
  prices ~$3,000/window) — the incremental premium is deliberately priced on vinyl only.
- Generated data trees are large and gitignored on `main`; don't commit them there, and
  don't regenerate a whole tree casually — report the repo-size impact.

## Definition of done

- Pipeline runs for all provinces from a clean invocation, documented commands.
- One committed JSON tree + one self-contained page, no external deps, `BASE_URL './'`.
- Both methodologies present and cross-linked; measured/modelled/assumed distinguished.
- Every drop quantified; assumptions tagged; the four/five decisions above resolved with
  the user and recorded with their *why* in the doc.
- `ROADMAP.md`, `project-atlas.html`, `docs/RETROFIT_COSTS.md` updated; deployed to
  `gh-pages` and verified live.
- **Confirm the open decisions with the user before writing the pipeline** — do not
  guess the currency/fuel/aggregation choices.
