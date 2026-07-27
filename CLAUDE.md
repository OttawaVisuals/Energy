# CLAUDE.md — how to work in this repo

Project docs live elsewhere and are the source of truth for *what* each tool is:
[README.md](README.md) (hub) · [ROADMAP.md](ROADMAP.md) (tracker) · `docs/<TOOL>.md` (per project).
This file is *how we work*. Don't duplicate the docs here.

## Purpose

Present Canadian energy / retrofit / construction data — tools, visualizations,
scenarios — to **two audiences at once**:

- **General**: homeowners, curious people, associations.
- **Technical**: NRCan, EnerGuide/HOT2000 practitioners, energy engineers.

Every source, assumption, calculation and process must be stated in the
methodology sections. **Every page carries two**: a *simple* methodology (plain
language, no jargon, no per-m² units) and an *advanced* one (formulas, raw field
names like `NUMDWELLINGUNITS` / `CCASHPCAP`, data vintages, caveats), cross-linked
to `docs/<TOOL>.md`.

## Working agreement

- **Confirm in chat before writing scripts or editing documents.** Propose the
  change, wait for a yes. Reading, searching and analysis need no confirmation.
- **Ask clarification questions.** Prefer one good question over a confident
  guess when readings diverge materially.
- **State limitations** — of the analysis *and* of the prompt. If a request rests
  on a shaky premise or the data can't answer it, say so before building.
- **Keep the trackers current.** When something ships, changes, or a decision
  gets made: update `ROADMAP.md` (and its `Updated YYYY-MM-DD` line),
  `project-atlas.html`, and the relevant `docs/<TOOL>.md`. Completed items move
  to `docs/archive/ROADMAP_COMPLETED.md`. Decisions get recorded with their *why*.
- **Absolute dates everywhere.** Never "last week" / "recently" in docs.
- **Commits**: only when asked. Never push a regenerated data tree without first
  reporting the size delta.

## Don't overcomplicate

Simple and clear beats sophisticated and unfalsifiable — our position has to be
defensible to a skeptical engineer. Precedent: AHRI buckets use plain COP and
capacity-maintenance values rather than detailed tier calculations. Prefer the
method you can explain in two sentences on the page itself.

## Architecture (invariant)

Offline Python pipeline → compact committed JSON → one self-contained HTML page.
**No backend, no build step, no npm, no CDN or external runtime dependencies.**
Don't propose a framework.

Where things go:

| Thing | Location |
|---|---|
| ETL / pipeline script | `Python/` — module docstring explaining inputs, outputs, sources |
| Generated data | `<tool>_json/` |
| Page | root `<tool>.html` |
| Shared theme / CSS / JS / OG cards | `assets/` |
| Project doc | `docs/<TOOL>.md` |
| Tracker line | `ROADMAP.md` |

`Python/*.log`, `Python/*_cache/`, `climate_cache/` are scratch — never deliverables.

## Data honesty rails

- **Never silently drop records.** Quantify drops, name the gate that caused
  them, document it. (See the ERS pairing gates for the pattern.)
- Show a gap rather than interpolate one away.
- Label sample sizes; suppress small-n cells.
- Distinguish **measured vs modelled vs assumed** in the display, not just the docs.
- **Check redistribution rights before embedding any third-party dataset.** Some
  sources (NRCan's heat-pump tool EULA, NEEP) restrict republishing.
- Limitations template: *what the data can't tell us · what we assumed · what
  would change the answer.*

## Repo hygiene

Large JSON trees are committed (`fsa_json`, `newhomes_fsa` — hundreds of MB).
Don't regenerate a whole tree casually: check first what a refresh actually
rewrites, prefer file-incremental refresh, and report the repo-size impact.

## Verification traps

The preview renderer has **no requestAnimationFrame**. Chart.js paints blank and
screenshots time out. Use `animation: false` plus a forced draw, and verify by
sampling canvas pixels rather than by screenshot. Smooth scrolling never moves —
use `behavior: 'instant'`.
