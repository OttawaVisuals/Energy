# The Cold Call — HVAC escape room (training tool)

**Status (2026-11-05):** playtest at
[ottawavisuals.github.io/Energy/coldcall.html](https://ottawavisuals.github.io/Energy/coldcall.html),
listed on the landing page (last tile) and in the Project Atlas progress bars. The page itself
keeps `noindex` for now. No favicon or social card yet.

## What it is

A ~30-minute online escape room. The player is an HVAC technician called out in
mid-winter to a rural house whose propane furnace has broken down, and replaces it with
a heat pump. A "service call" sheet tracks six lines, one puzzle each:

| Line | Step | Result |
|---|---|---|
| 1 | Furnace age (match the furnace to its model sheet) | Made 1992 · 34 years old |
| 2 | Total heating need (rebuild a shredded propane statement) | 22,690 kWh of propane a year |
| 3 | Peak heating demand (blower door + thermal camera, seal the leaks) | 5.8 kW after air sealing |
| 4 | Managing the peak (schedule EV, laundry, water heater… on Ontario ULO rates) | 13.0 kW peak |
| 5 | Energy and GHG savings (build the refrigerant loop) | 14,530 kWh and 3.8 t CO₂e a year |
| 6 | $ savings (balance scale of yearly costs) | $1,885 a year |

Fictional training scenario, simple maths, metric units. Published rates inform the scenario; building, performance and cost allowances are assumptions. Each line ends with a debrief explaining the
concept (UA × ΔT, ACH50, COP, time-of-use, propane vs heat-pump cost per kWh).

## Where the source lives

- **Source of truth:** `C:\EscapeBackpack\Cold-Call\cold-call.html` (the designer's
  escape-room workspace, with puzzle records in `Cold-Call\records\`).
- **This repo's copy:** `coldcall.html`, built by `Cold-Call\make-energy-copy.py`. It
  swaps the branding (Energy Suite kicker, `⌂ All tools` link, `assets/author-footer.js`)
  and tags feedback `cold-call-energy`. Don't edit `coldcall.html` by hand: edit the
  source, re-run the script, then commit to `main` and publish to `gh-pages`.
- A second copy with Escape Backpack branding stays live at
  `escapepack.ca/play/cold-call/` (designer's decision, 2026-11-04: keep both links).

## Exceptions to the house rules (decided 2026-11-04)

The designer approved these as a **playtest exception**; revisit when it becomes a
listed tool:

- **External runtime dependencies:** Google Fonts (Barlow, Barlow Condensed, B612 Mono,
  Caveat) and a Formspree form (the Escape Backpack feedback form) for the in-game
  feedback button. Why: the feedback form carries per-line time, hints and wrong tries,
  which is the point of the playtest.
- **No simple/advanced methodology sections:** the explanations are in each line's
  debrief. Sources: Ontario Ultra-Low Overnight plan (OEB, from 2025-11-01: 3.9 / 15.7 /
  39.1 ¢/kWh, Ontario Electricity Rebate 23.5%); propane ≈ $0.75/L delivered (third-party
  guide, no official residential series), 7.09 kWh/L, ≈ 1.5 kg CO₂e/L; Ontario grid
  ≈ 70 g CO₂e/kWh; 78% AFUE furnace; assumed seasonal COP 2.8; illustrative operating point at −2 °C.
- **`noindex`:** kept while unlisted.

## Limitations

- Prices and the grid factor are rounded single values; real bills vary with supplier,
  winter and year.
- Seasonal COP 2.8 and the 10% annual heat-demand reduction are assumed, not calculated from average outdoor temperature. The camera does not measure UA. Equipment selection, defrost and backup heat are outside the game.
- Responsive stacked layouts and keyboard controls are provided; the 24-hour schedule scrolls horizontally on narrow screens. Physical touch devices and screen-reader applications have not been tested.

## Review fixes — 2026-11-04 (published 2026-11-04)

- Keyboard activation for refrigerant parts and cost cards; explicit Add buttons on both cost pans.
- Lines 2–6 require the completed activity, including the actual optimal schedule and exact job-summary costs.
- Corrected 460 L × $0.75 from $349 to $345: propane year $2,805, electric year $920, package operating savings $1,885.
- Completed endings reopen after reload; each solved line has a Review button. Puzzle arrangements and per-visit times are not restored.
- Responsive headers, stacked work areas, stable cost lists and scrollable timeline replace clipped phone layouts.
- Scenario heat-loss and seasonal performance assumptions are visible. The final debrief links primary OEB/NRCan guidance and distinguishes package savings from heat-pump-only savings.
- Heating cost: round(4,870 × (0.50 × 0.039 + 0.40 × 0.157 + 0.10 × 0.391) × 0.765) = $452. Usage shares are assumed; not derived from line 4. Excludes delivery, regulatory charges and taxes. Rebate application to commodity only is a teaching simplification. Other electricity, maintenance and rental costs, including $618 unprogrammed heating, remain fixed scenario allowances.
- Regression command: `node Python/check_coldcall.cjs` (syntax, activity gates, optimum-board check, all 2,048 cost selections and cost arithmetic).

Validation (2026-11-04): complete keyboard walkthrough of all six lines; incomplete-activity rejection; cost arithmetic and all 2,048 selections; reload, close and Review controls; 18 layouts across six lines at 320/390/1280px, plus targeted readable statement/timeline checks. No browser errors observed. No feedback sent. Physical touch devices and screen-reader applications remain unverified.

## Visual refinement — 2026-11-04 (published 2026-11-04)

- Retained the slate/copper/paper workbench with a quieter grid, consistent borders, clearer type hierarchy and six inline section icons. No new dependencies or generated image assets.
- Added completion count/bar from the actual solved lines; moved the active answer above the task history. On narrow screens the answer leads the service-call area below the puzzle.
- Separated the furnace model key from chart legend styles, restoring readable dark text on paper; polished furnace shading without changing clue-bearing colour, flue, louvres, latches or window absence.
- Standardized documents, selectable parts, cost cards, instruments, notes and debriefs. Appliance labels have readable tray widths; compact Add controls retain their explicit accessible names. Reset keeps its second-click confirmation.
- Stacked layouts at widths up to 1,180px or heights up to 680px; statement/timeline retain their own horizontal scrolling. Balance trays moved inside the work area, with feedback above the beam and scrolling available for short desktop work areas.
- Validation: 42 page/viewport checks (all six lines at 320, 390, 768, 1024, 1180, 1181 and 1280px); no page/header/heading/answer overflow or browser warnings/errors. Targeted keyboard part assembly, filled cost selection, completion progress, debrief and Reset checks; the 2,048-selection logic regression still passes. Physical touch and screen-reader applications remain unverified.

## Service-call briefing and blank model guide — 2026-11-04 (published)

- Moved the winter breakdown/replacement story to the service-call panel. Per-line On site notes follow the active puzzle and Review navigation; each workspace heading now has only its short task instruction.
- Replaced the completed example model number with four blank groups (`_ _ | _ _ | _ | _`). Each group points down to its possible values: BC series; 18/24/30 kW input; L/M/H efficiency definitions; A–F years. Full model identifiers remain on the six comparison cards, where they are part of the puzzle.
- Four connected columns on desktop, two columns on narrow phones, with explicit accessible group order. No calculation or answer changes.
- Validation: correct one-note-per-line switching on all six steps at 390/1280px; 320px diagram inspection, no full model in the key or page overflow; existing calculation/selection regression passes. Physical devices remain untested.

Publication: the reviewed game, visual refinement and service-call/model-guide changes were released to Energy GitHub Pages on 2026-11-04. The game remains an unlisted playtest. This release does not deploy the separate escapepack.ca copy.

## Teaching layer — 2026-11-04 (published 2026-11-05)

Four evidence-led cards now appear after lines 1, 3, 5 and 6. The original solution explanation remains under **How this puzzle works**. Readers can revisit cards through the existing Review buttons. Educational inputs never alter puzzle answers or annual scenario totals.

### Data and scope

- **Heating mix (line 1):** reuse `ceud_json/res_ca.json`, NRCan CEUD Canada residential Table 27, 2000–2023. All 14 detailed equipment categories are retained and grouped identically to CEUD Explorer. Shares use their summed rounded counts, not residential energy use or equipment sales. In 2023: 1,340,000 primary heat-pump systems / 16,866,722 summed systems = 7.944638%. CEUD's separately rounded total is 16,900,000; both totals are shown in the card's data table. Primary stock can omit secondary heat pumps. A year selector and counts table expose the series; link to CEUD Explorer in advanced view.
- **Airtightness (line 3):** read-only extraction from `C:/ERS/2025.csv`. Sequential gates: 230,609 records → 107,260 initial D audits → 22,167 Ontario → 17,485 single detached → 17,485 House building type → 16,909 with ENTRYDATE in 2025. Keep the earliest eligible initial audit per HOUSEID (21 repeats removed), then require positive finite AIR50P and LEAKAR (0 removed). Final n=16,888. No household IDs, addresses or row-level records are output. Initial-audit median ACH50=4.79815, Q1=3.465175, Q3=7.047325. This is a selected audit sample, not a representative Canadian or Ontario housing estimate; no follow-up audit is required by this cohort.
- **Equivalent opening:** use the same cohort's measured LEAKAR field, cm² at 10 Pa. Median area=1190.07765 cm²; diameter=√(4×area/π)=38.92626 cm. A diagram represents a single circle with equivalent flow, not an actual hole or everyday ventilation. It is not inferred from ACH50; median ACH50 and median area need not describe one home. Game markers 7.0 and 4.2 ACH50 are explicitly scenario values. Link to Retrofit Explorer and the original NRCan dataset/CGSB standard.
- **Fuel emissions (line 5):** ECCC **Emission factors and reference values**, v4.0, September 2026, tables 1.3/2.3/3.3/4.3/5.3, reference year 2026. Component factors are CO₂, CH₄ and N₂O; convert with GWP100 1/28/265 before dividing by native energy content and efficiency. Residential native totals: gas (Ontario) 1,931.311 g CO₂e/m³, oil 2,755.318 g/L, propane 1,544.376 g/L. Grid consumption-reference factors: ON 59, QC 1.9, AB 438 g CO₂e/kWh. Provincial selection changes electricity only; the gas factor remains Ontario's. Reference factors are neither a measured 2026 annual-average outcome nor hourly marginal intensities. Excludes upstream fuels, manufacture and refrigerant loss. No extra T&D multiplier is applied to consumption-side factors. Links to Heat Pump Explorer, Grid Dashboard, ECCC factor and GWP tables. The cards calculate CO₂e directly from gas components; they do not inherit the companion engine's unweighted trace-gas addition. Game rounded inputs (70 g electricity/kWh, ~1.5 kg propane/L) remain unchanged and separate.
- **Useful-heat costs (line 6):** reuse the saved `prices_json/on.json` inputs, generated 2026-07-12, with explicit per-fuel dates. Electricity 18.317¢/kWh: Hydro Ottawa November 2025 TOU snapshot, assumed 63% off / 18% mid / 19% on plus 5.46¢ variable adders. Gas $0.2429/m³: October 2024 Ontario **Union South**, not an Ottawa tariff. Oil $2.432/L: Ottawa-Gatineau Ontario part, May 2026 (StatCan 18-10-0001). Propane $0.75/L: an unverified game assumption, not observed price data. These mixed-date/region references teach unit conversion and are not current quotes or a same-date fuel-price survey. Readers can enter their own prices. Excludes fixed charges, taxes and OER, and is separate from the game’s annual package calculation. A table exposes purchased-energy versus delivered-heat costs.

### Assumptions and formulas

- Gas efficiency 0.95, oil 0.85, propane 0.78, resistance 1.00; seasonal heat-pump COP defaults to the game's assumed 2.8, with 2/3/4 sensitivity options. These are not national equipment-average estimates.
- Energy content: gas 10.3611 kWh/m³, oil 10.7778 kWh/L, propane 7.0917 kWh/L, matching Heat Pump Explorer's conversion constants.
- Fuel cost (¢/kWh heat) = 100 × native-unit price ÷ native-unit kWh ÷ efficiency. Electricity cost = cents/kWh ÷ COP (or ÷1 for resistance).
- Fuel GHG (g CO₂e/kWh heat) = (CO₂ + 28 CH₄ + 265 N₂O) ÷ native-unit kWh ÷ efficiency. Electricity = consumption-reference factor ÷ COP.
- Dataset-level metadata and SHA-256 input fingerprints accompany the compact snapshot. The original public datasets supply the data; narrative, diagrams and aggregations are ours. No CGSB tables/text or identifiable audit records are redistributed.

### Build, deployment and validation

`python Python/build_coldcall_teaching.py` reads only the existing CEUD/rate snapshots and the single raw ERS file. It writes `coldcall_json/teaching.json` (10,645 bytes) plus a copy beside the original game at `C:/EscapeBackpack/Cold-Call/coldcall_json/teaching.json`. No collector or existing generated tree is modified. Pandas is needed only for the offline build, not in the browser.

The JSON tree is ignored on `main`. Publish **coldcall.html and coldcall_json/teaching.json together** on `gh-pages`; both are now in the full deploy path list. The Escape Backpack deployment also needs its own adjacent JSON copy. Existing `make-energy-copy.py` still generates the branded Energy HTML. No new runtime library or external API is used; one same-origin JSON request loads the lessons. Missing data offers a retry and the Energy Suite link while the original puzzles keep working.

Checks: `python Python/test_coldcall_teaching.py` (five source/arithmetic/privacy checks, including every CEUD year); `node Python/check_coldcall.cjs` (existing six-puzzle syntax/gates and all 2,048 cost selections). Browser: 16 lesson/viewport cases at 320/390/768/1280px; four additional open-source-disclosure checks at 320px; stock-year, provincial reference and COP changes; custom price edits, invalid/empty input and restore; actual puzzle-1 success, Review cards and missing-data retry/navigation. No overflow or normal-page browser errors observed. Physical touch devices and actual screen-reader applications remain unverified.

Primary references:
- [NRCan CEUD Table 27](https://oee.nrcan.gc.ca/corporate/statistics/neud/dpa/showTable.cfm?type=CP&sector=res&juris=ca&year=2023&rn=27&page=0)
- [NRCan EnerGuide open dataset](https://open.canada.ca/data/en/dataset/0a7619fd-2ffe-44b5-9027-3dfcec0866fd)
- [CAN/CGSB-149.10-2019](https://publications.gc.ca/collections/collection_2019/ongc-cgsb/P29-149-010-2019-eng.pdf)
- [ECCC factors](https://www.canada.ca/en/environment-climate-change/services/climate-change/pricing-pollution-how-it-will-work/output-based-pricing-system/federal-greenhouse-gas-offset-system/emission-factors-reference-values.html) and [GWP100](https://www.canada.ca/en/environment-climate-change/services/climate-change/greenhouse-gas-emissions/quantification-guidance/global-warming-potentials.html)
- [OEB November 2025 tariffs](https://www.oeb.ca/newsroom/2025/ontario-energy-board-announces-changes-electricity-prices-households-small-businesses) and [StatCan oil-price table](https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=1810000101)


## Puzzle navigation and scheduler — 2026-11-04 (published 2026-11-05)

- Every checklist title opens that puzzle's workbench, including completed puzzles. Previous/Next buttons allow free browsing; the Answer & teaching button and existing Review links open completed explanations. Browsing does not mark activities complete or bypass their checks.
- A prominent Calculator button appears in the workbench navigation. The pad has larger keys, stays inside the viewport and returns keyboard focus to its launcher when closed.
- Appliance tiles have fixed widths derived from duration × the actual hour pitch. Removing a tile no longer stretches the others. A snapped drag preview shows the exact start/finish hours and marks overlap; preview and drop use the same hour mapping, retaining the hour grabbed within the tile.
- Appliance/start–finish selectors plus Place/Move and Remove provide precise placement without dragging. Occupied times are labelled, and overlap attempts leave the schedule intact. The timeline scrolls sideways on narrow workbenches; its chart retains a readable height.
- In-progress activities and appliance positions survive navigation within the current tab. Reload still restores completed answers, but does not save unfinished component arrangements.

Validation: placed/removed a water heater and compared all remaining tile widths; placed all five appliances for the valid 54 A / 13.0 kW schedule; rejected an overlap; navigated away/back with all positions retained; reopened puzzle 1's workbench and teaching card; calculated 126 × 46 = 5,796 and verified close-focus return. An actual pointer drag placed the water heater at 7–11 am as intended. Layout checks at 320/390/768/1280px found no page overflow and retained the 200px chart. The regression script adds 2,196 hour-snap cases across every valid start/grabbed hour, fractional pointer positions and scrolled coordinates, plus edge clamping. Existing game and five teaching-data checks pass. Physical touch devices and screen-reader applications remain unverified.


## Concise teaching copy — 2026-11-04 (published 2026-11-05)

Removed “game” language from teaching cards and labelled the house’s before/after ACH50 as assumed values. Shortened visible ACH, equipment-share, emissions and cost text; retained the audit sample boundary and essential input caveats, with detailed exclusions and methodology under Sources. Data, calculations and puzzle answers are unchanged. Embedded-script/regression checks pass; ACH card reviewed in the browser.


## Service sheet and compact header — 2026-11-05 (published)

The workbench groups Previous, Next, review and Calculator beside the scene title. Each active line on the service sheet explains why the work matters and gives a short instruction above the answer. Line 3 connects sealing air leaks before installing the heat pump to lowering peak demand.

Checked all six line notes and headers, calculator access and layout at 320, 390, 768 and 1280px. The game regression checks pass.

Layout refinement (2026-11-05). Reduced outer padding and gaps. Replaced decorative outlines and rounding with flat sections and dividers on the service sheet, workbench and teaching cards. Checked all six puzzles at four widths and the teaching card at 320px.

## Line order enforced — 2026-11-05 (published 2026-11-05)

- The "Next →" button, the service-call step buttons and `#lineN` links could open any line, so a player could skip to line 6 unsolved. `show()` now opens only solved lines and the first unsolved one; Next and later step buttons stay disabled (with a "Locked" tooltip) until the current line is solved. A finished game can still revisit every line.
- Validation: fresh start with `#line6`, Next and sheet clicks stay on line 1; solving line 1 unlocks line 2 only; a fully solved save reaches all six; `node Python/check_coldcall.cjs` passes.

## Landing-page tile — 2026-11-05 (published 2026-11-05)

- Designer asked for a tile and approved the art and text. Art: snowflake (winter breakdown), service-call clipboard (two lines ticked, one in progress) and padlock (escape room), in the suite's navy `#0B2545`, teal `#009D9D` and amber `#E8A124`.
- Drawn with Pillow (no AI image generation) by `C:\EscapeBackpack\Cold-Call\make-tile-art.py`: `assets/icons/cold-call.png` (1942×809, transparent) and `assets/icons/web/cold-call.webp` (512×216, balanced like `Python/build_visual_polish.py`). Not added to `build_visual_polish.py` / `build_brand_assets.py` SPECS, so rerunning those leaves it alone.
- Tile text: "A 30-minute HVAC escape room: a furnace fails mid-winter and you install the heat pump, solving six puzzles on real heating maths." Footer "Training game · playtest", CTA "Play →".
- Validation: tile height matches its neighbours in the 4-column grid at 1366px; art legible in light and dark themes.


## Emergency dispatch briefing — 2026-11-06 (published)

A fresh service call opens with a short dispatch briefing. Start service call opens Line 1 and starts the timer. Reset and Play again return to the briefing. Saved progress and direct puzzle links enter the workbench with existing unlock rules.

## Heat-loss formula note — 2026-11-09 (published 2026-11-09)

Line 3's scenario heat-loss report ends with a handwritten sticky note: **Peak heat loss — UA × ΔT** (designer's request: "the formula and its name"). It appears with the report, once all five leaks are sealed, and helps players turn the report's Total UA and temperatures into the answer. Checked at 1440×900 (the right-hand column does not overflow) and 375 px wide; `Python/check_coldcall.cjs` passes. Published to the Energy Suite and escapepack.ca; the escapepack.ca sync also brought that copy up to date with the 2026-11-06 changes.

## Calculator brackets and movable heat pump parts — 2026-11-09 (published 2026-11-09)

Designer playtest feedback: the calculator refused `126*(21+25)`, and on Line 5 a placed part could not be dragged to another socket.

- **Calculator:** `calcEval()` is now a small recursive-descent parser: + − × ÷ with precedence, brackets (nested), a leading or nested minus, and a number or `)` before `(` read as multiplication (`126(21+25)`). Still accepts `*`, `x`, `/` and thousands commas. An unbalanced bracket says "Close every bracket you open". The keypad gains ( ) keys in a standard 5-row layout (C ( ) ÷ / 7 8 9 × / 4 5 6 − / 1 2 3 + / 0 . ⌫ =).
- **Line 5:** a placed part can be dragged to another socket (swapping if that socket is full) or onto the parts list to take it out. Dropping elsewhere leaves it in place with a hint. A plain click still takes the part back; parts lock once the loop runs.
- **Checks:** 22 calculator expressions (node), typed and keypad input in the browser; real mouse drags for swap, move, return and the solved loop; `Python/check_coldcall.cjs` passes; no console errors. Touch dragging uses the same pointer events but was not tested on a real phone.

## Line 6 cost list starts in two columns — 2026-11-09 (published 2026-11-09)

Designer feedback: the yearly-cost list began as one long column, then switched to two once a few costs were on the pans. Cause: while all 11 costs are listed the side column scrolls, and its scrollbar (15 px) left too little width for two 130 px flex cards. `.weights` is now a grid (`repeat(auto-fill, minmax(110px, 1fr))`), so it shows two columns from the start, with or without the scrollbar. Checked at 1440×900 (start and after loading pans) and 375 px wide.
