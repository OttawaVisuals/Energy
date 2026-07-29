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
- **Commits**: only when asked — but "commit and push" means *both branches*, and
  I handle the split without asking which is which (see below).

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

## Two branches — never commit data to `main`

| Branch | Holds | History |
|---|---|---|
| `main` | HTML, `assets/`, `Python/`, per-tool `pipeline/`, docs, trackers | Full — this is the decision record |
| `gh-pages` | The published site: pages + every generated data tree | **One commit, force-pushed each deploy.** No history, by design |

GitHub Pages publishes `gh-pages`, so data is same-origin with the pages —
`BASE_URL` is `'./'` everywhere; never reintroduce raw.githubusercontent URLs.
`.nojekyll` is mandatory (data trees contain `_index.json`; Jekyll drops
underscore paths).

Every generated tree is gitignored on `main` and lives on local disk only.
Losing it is fine — re-run the pipeline. **What must be defensible is the
process, not the bytes**, and the process is versioned on `main`.

"Commit and push" therefore means: commit code/docs/decisions to `main`, then
publish to `gh-pages`. Two ways to do the publish half:

- **Full `./deploy.sh`** — rebuilds `gh-pages` from scratch as a single
  orphan commit. Requires *every* path in its `PATHS` list to exist on local
  disk (all generated trees: `fsa_json`, `census_json`, `grid_json`, etc.),
  since it reads from the working tree, not from what's already published.
  Use this when you actually have the full local data checkout, or when
  something genuinely needs a from-scratch rebuild.
- **Incremental single/few-file update** — when only a handful of paths
  changed (e.g. one tool's HTML + its own `data/processed` tree) and the rest
  of the local data trees aren't present (a fresh checkout, a different
  machine, a sandboxed session): build a new commit **on top of the current
  remote `gh-pages` tree** instead of the working tree, touching only the
  changed paths. This needs no local copy of the untouched trees at all.
  Precedent: commits `cd454e7`, `3a0145f`, `874ad2f`/`d989fe0` on `gh-pages`.

  ```bash
  git fetch origin gh-pages -q
  BASE=origin/gh-pages
  IDX=$(mktemp)
  export GIT_INDEX_FILE="$IDX"
  git read-tree "$BASE"
  git add -f <changed-path-1> <changed-path-2> ...   # -f: paths under
                                                       # HeatPump/data/** etc.
                                                       # are gitignored on main
  TREE=$(git write-tree)
  COMMIT=$(git commit-tree "$TREE" -p "$BASE" -m "…")
  git push origin "$COMMIT:gh-pages"
  unset GIT_INDEX_FILE; rm -f "$IDX"
  ```

  `git add` silently skips gitignored paths without `-f` — always pass `-f`
  explicitly for anything under a generated-data directory, and afterwards
  confirm with `git ls-tree -r <commit> -- <path>` that what you meant to add
  actually landed, since a silent skip leaves the page fetching a 404 with no
  local error to catch it.

  The next full `./deploy.sh` resets `gh-pages` to a single squashed commit
  as usual — this path is a stopgap between full rebuilds, not a replacement
  for one. GitHub Pages can take 1-2 minutes to redeploy after either kind of
  push; verify with `curl` or a browser check before declaring it live.

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
