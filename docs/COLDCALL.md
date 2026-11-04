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
| 6 | $ savings (balance scale of yearly costs) | $1,889 a year |

Real values, simple maths, metric units. Each line ends with a debrief explaining the
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
  ≈ 70 g CO₂e/kWh; 78% AFUE furnace; COP 2.8 at −2 °C.
- **`noindex`:** kept while unlisted.

## Limitations

- Prices and the grid factor are rounded single values; real bills vary with supplier,
  winter and year.
- Seasonal COP is read at the average heating-season temperature (a simplification).
- Laptop-first layout; phone and tablet layouts are not tuned yet.
