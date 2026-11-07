# Energy Quiz

`quiz.html` — a ten-question quiz built from the site's own data, so people learn
how Canada uses energy and builds homes by guessing, then seeing the real number.
Design and question styles adapted from **Atlas Play** (geography quiz, SimpleViz repo,
`scripts/atlas-play/`, commit `d2dd242`, 2026-11-07).

**Status (2026-11-07):** built and tested locally, **not yet published**. Pending: landing
tile + icon, OG card, feedback/author footer parity with other pages, a first look by a
non-expert player.

## Pipeline

```
Python/build_quiz.py   # reads ceud_json/ + construction_json/
                       #  -> quiz_json/meta.json, quiz_json/ceud.json, quiz_json/construction.json
Python/build_quiz_shapes.py  # province / region outlines -> quiz_json/shapes.json (shapely + numpy;
                       #   run automatically at the end of build_quiz.py, skipped if geo_json/ is missing)
Python/build_quiz_icons.py   # item icons (fuels, end uses, sectors, modes...) -> quiz_json/icons.json;
                       #   run automatically at the end of build_quiz.py; prints any bank item with
                       #   neither an outline nor an icon
Python/fetch_lucide_icons.py # ONE-OFF: vendors the Lucide SVGs into assets/vendor/lucide/ (no network at build)
Python/check_quiz.py   # invariant checks on the generated banks (run after build_quiz.py; exit 1 on failure)
quiz.html              # fetches quiz_json/*, plays 10-question rounds; no logic about the data
```

`quiz_json/` is gitignored on `main` and listed in `deploy.sh` `PATHS`. Regenerate with
`python Python/build_quiz.py` after any refresh of the source trees (about 1 s).
Bank on 2026-11-07: CEUD 2,376 questions (822 KB), construction 627 (216 KB).

## Question styles (6 of Atlas Play's 9)

| Style | What the player does | Right when |
|---|---|---|
| Head to head (`compare`) | pick the larger of two | value is the max |
| Put in order (`rank`) | drag three cards onto a podium (tall step = highest) | exact order |
| Find its place (`insert`) | slot one item into four ordered others | correct gap |
| Guess the gap (`gap`) | pick the ratio (4 options from a fixed scale) | nearest scale value to the true ratio |
| Guess a share (`estimate`) | slider 0–100% | within ±15 / ±8 / ±3 pp (easy / medium / hard) |
| Then vs now (`history`) | which rose more (or fell less) between two years | larger % change |

Not ported: World cities, Pin the city, Odd one out (geography-specific). A map style
(pin the province) is a possible later addition.

## Topics and measures

**CEUD** (NRCan, 2023 release, data 2000–2023, *modelled*): residential energy and direct GHG
by region; national residential mix by fuel / use / home type; commercial, industrial and
transport by subsector / mode / fuel; energy by sector; provincial natural-gas, electricity
and space-heating shares of home energy.
**Construction** (CMHC via StatCan 34-10-0151, calendar 2025 vs 2000, *measured*): starts by
province, by home type; apartment and single-detached share of starts by province.

Adding a topic: write `build_<topic>()` returning measures (see `build_ceud`), add it to
`TOPICS`. The page needs no change.

## Rules (data honesty)

- Every number is read from the source trees; nothing typed by hand. One year per question.
- Missing values are dropped, not filled (e.g. PEI/NL have no natural-gas home-heating cell).
- A pair is usable only if values differ after display rounding **and** relative gap
  `|A−B| / max(|A|,|B|)` ≥ 3%. Both gates counted per measure (`quiz_json/meta.json` →
  `guards`, shown in the page's advanced notes).
- Difficulty is a **heuristic**, not measured from players: compare on wide-range measures
  uses fixed cuts (≤25% hard, ≥65% easy); all other styles use thirds of that measure × style
  bank. Estimates take their difficulty from the tolerance.
- Banks are seeded per measure × style, so regeneration on unchanged data is reproducible.
- Each question carries a *modelled* or *measured* badge (CEUD vs CMHC counts).

## Limitations

- *Can't tell us:* anything about an individual building; CEUD is NRCan's model, not metering.
  GHG is **direct (on-site) only**, so hydro-heated provinces look near zero.
- *Assumed:* 3% gap = a real difference at the precision shown; gap-based difficulty tracks
  perceived difficulty. Neither tested with players.
- *Would change the answer:* new CEUD release or revised CMHC counts (regenerate); different
  tie/gap thresholds.
- Regions in CEUD industrial / commercial / transport are NRCan's groupings (Atlantic;
  BC + Territories), not like-for-like with single provinces. The construction table has no
  territories, so provinces sum to slightly less than Canada.
- **Dropped:** CMHC intended-market starts (homeowner / condo / rental) — the series ends
  early in our extract, so only 0–1 usable categories remained for 2025. Removed rather than
  using stale years.
- Best score and nothing else is stored, in the browser (`localStorage`), never sent.

## Decisions

- **2026-11-07 — vanilla JS, no React/npm** (Atlas Play uses React + a build). Repo invariant:
  no build step, no framework. The bank is pre-generated in Python so the page stays dumb.
- **2026-11-07 — second topic = Construction** (clean annual series, supports Then-vs-Now),
  not Retrofits (ERS data is noisier; see the negative-savings finding).
- **2026-11-07 — province outline icons.** Rank, compare, gap, insert, history and estimate show a
  region outline when the item is a province or CEUD region (Atlantic, Territories, BC & Territories
  Atlantic and Territories drawn as one outline each; BC & Territories drawn as two outlines side by side, because their union read as a confusing blob). Built from the Statistics Canada FSA boundaries already in `geo_json/`
  (+ Yukon from `lfsa000b21a_e.json`), unioned, Lambert-projected, parts under 0.5% of area dropped
  (max ~5%, BC & Territories), each fitted to its own 100×100 frame, so shapes do **not** show
  relative size. The page says so; it still works without `shapes.json`. 15 outlines, 97 KB.
  After answering, rank-row outlines fill amber in proportion to the value. Rank, Guess the gap and
  Find its place now put the explanation beside the question on screens ≥1100 / 1200 px wide so
  everything stays above the fold at 1366×768 (stacked below that, where it may scroll).
- **2026-11-07 — item icons (Lucide, tinted by category).** Fuels, end uses, home types, sectors,
  commercial/industrial subsectors and transport modes get an icon on a tinted chip; provinces keep
  their outlines (outlines win). Source: a hand-picked subset of [Lucide](https://lucide.dev)
  v1.70.0 (ISC licence, vendored in `assets/vendor/lucide/` with its LICENSE, so the page loads
  nothing from a CDN). Mapping name → icon + tint lives in `ICON_MAP` / `TINT` in
  `build_quiz_icons.py`; the build prints coverage (every item in the bank is covered, 48 icons for 57
  names, 15 KB). Tint is a category colour (gas amber, electricity blue, wood green...), never a value:
  label and number always show. Page works without `icons.json`.
  Bug found and fixed while verifying: a CSS class `.ghost` (drag clone) collided with `.btn.ghost`
  and made "New round" fixed-position; drag clone is now `.drag-ghost`.
  Limits: one icon per item, so similar items (trucks, house types) rely on labels; Row/townhouse
  (`rows-3`) is the weakest metaphor; no "technologies" icons yet because heat-pump/retrofit
  topics are not in the bank (see Ideas).
- **2026-11-07 — compared with Atlas Play (SimpleViz repo), borrowed two ideas.** (1) `check_quiz.py`
  enforces the page's promises on all 3,003 questions (unique ids, ≥3% gaps, no display-rounding
  ties, gap answer = closest option, every item has an icon/outline); a deliberate corruption test
  confirmed it fails when it should. (2) Head-to-head and Then-vs-now tiles now say "Your choice ·
  Correct / Incorrect" or "Correct answer" next to the value. Not borrowed: React/Anime.js/npm build
  (repo invariant), CI-overlap guards (CEUD/CMHC have no intervals). Candidates still open: 3-place
  a reference marker on the estimate slider, light/dark toggle.
- **2026-11-07 — rank is now a three-place podium** (borrowed from Atlas Play). Banks regenerate with
  3 items per rank question (was 4; adjacent-gap guard unchanged, now 2 gaps). Cards sit in a bank and
  go onto Highest (tall, centre) / Middle / Lowest steps by pointer drag (mouse + touch), tap a card
  then a step, or keyboard (Enter/Space). Dropping on an occupied step swaps; dragging back to the
  bank removes. Check needs all three placed; after answering each step shows ✓/✗, the value and
  where a wrong card belonged. Replaces the HTML5 drag list and ▲▼ arrows (the 34×30 px arrow
  touch-target gap is gone; cards are ~40 px, holes 44 px). Verified at 1366×768 (fits, reveal beside
  the podium) and 375 px (no horizontal overflow); the bank is now 3,037 questions.
- **2026-11-07 — rank/insert capped at 60 sampled questions per measure** to keep the CEUD
  bank under 1 MB.
- **2026-11-07 — design critique applied** (`design:design-critique`): Guess-the-gap shows the two
  compared items as named cards; right/wrong marked with ✓/✗ not colour alone; muted grey and control
  borders darkened to meet WCAG contrast (text ≥4.5:1, borders ≥3:1); end screen lists all 10 questions
  with the true answer and a chart link; changing Topic/Difficulty/Style mid-round no longer resets the
  round (notice offers "Start new round now"; difficulty is snapshotted at round start); "Check answer"
  /"Next" bar is sticky; New round is a quiet button. Known gap: rank arrows (34×30 px) and slots
  (26 px) are under 44 px touch targets, kept small to fit 1366×768 without scrolling.

## Ideas, not committed

Retrofit and heat-pump topics; map "pin the province" style; a daily seeded question;
share-result card.
