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
quiz.html              # fetches quiz_json/*, plays 10-question rounds; no logic about the data
```

`quiz_json/` is gitignored on `main` and listed in `deploy.sh` `PATHS`. Regenerate with
`python Python/build_quiz.py` after any refresh of the source trees (about 1 s).
Bank on 2026-11-07: CEUD 2,376 questions (822 KB), construction 627 (216 KB).

## Question styles (6 of Atlas Play's 9)

| Style | What the player does | Right when |
|---|---|---|
| Head to head (`compare`) | pick the larger of two | value is the max |
| Put in order (`rank`) | order four, highest first | exact order |
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
- **2026-11-07 — rank/insert capped at 60 sampled questions per measure** to keep the CEUD
  bank under 1 MB.

## Ideas, not committed

Retrofit and heat-pump topics; map "pin the province" style; a daily seeded question;
share-result card.
