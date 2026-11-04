# The Cold Call — HVAC escape room (training tool)

**Status (2026-11-04):** unlisted playtest at
[ottawavisuals.github.io/Energy/coldcall.html](https://ottawavisuals.github.io/Energy/coldcall.html).
No landing-page tile and no Project Atlas entry yet: add them after the playtest.

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
