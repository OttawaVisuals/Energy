#!/usr/bin/env bash
# Publish the site + generated data to the gh-pages branch.
#
# gh-pages is rebuilt as a SINGLE commit and force-pushed every time, so the
# data never accumulates history. main keeps the source, the pipelines and the
# decision history; this branch is a disposable snapshot of the current bytes.
#
# Usage:  ./deploy.sh ["optional commit note"]
#
# IMPLEMENTATION NOTE (2026-08-04): this used to build the snapshot with
# `git checkout --orphan gh-pages-tmp` IN THIS WORKING DIRECTORY, commit, push,
# then `git checkout -f "$START_BRANCH"` to switch back. That last checkout is
# destructive: every path in PATHS becomes "tracked" the moment it's committed
# to gh-pages-tmp, and switching back to main -- where those same paths are
# gitignored/untracked -- makes git DELETE them from disk (a file tracked in
# the branch you're leaving but absent from the branch you're entering is
# removed, not merely unstaged). This deleted fsa_json, province_json,
# insights_json, lookup and every other generated tree from local disk the
# first time this ran end-to-end. Recovered that time only because the data
# had just been force-pushed to origin/gh-pages moments before
# (`git checkout origin/gh-pages -- <paths>`) -- not guaranteed in general
# (e.g. a deploy note typo caught by the PATHS-exist check above would still
# have run this far in an earlier version of the script).
#
# Fixed by never touching the working tree's branch/HEAD at all: the orphan
# commit is built with plumbing (git add -f against a throwaway
# GIT_INDEX_FILE, then write-tree/commit-tree/push-by-hash), the same
# technique CLAUDE.md documents for the incremental single-file gh-pages
# update. `git add -f` still reads file CONTENT from this working directory
# (so PATHS must exist here, same as before), but it never runs `git
# checkout`, so nothing in the working directory or on the current branch is
# ever added, removed or switched.
set -euo pipefail
cd "$(dirname "$0")"

NOTE="${1:-}"
STAMP="$(date +%Y-%m-%d)"

# Pages content: every page, the shared assets, and each generated data tree.
# Keep this list in sync with the generated-data block in .gitignore.
#
# tier-scatter.html is TEMPORARY — a generated discussion aid for the heat-pump
# tier rework (HeatPump/pipeline/build_tier_scatter.py). It is gitignored on
# main, unlinked from every page, and should be dropped from this list once the
# tier cells are chosen.
PATHS=(
  .nojekyll
  index.html ceud.html construction.html districtenergy.html grid.html heatpump.html
  newhomes.html permits.html project-atlas.html retrofit-insights.html retrofits.html
  tier-scatter.html
  assets
  functions
  fsa_json newhomes_fsa newhomes_json province_json insights_json
  retrofit_costs_json
  ceud_json construction_json permits_json grid_json prices_json geo_json census_json
  districtenergy_json
  lookup FSA_Maps GridCapacity
  HeatPump/data/processed
  Geothermal/output
  utility_rates_reference.json utility_rates_reference.csv
)

# .nojekyll is required: the data trees contain _index.json files, and Jekyll
# strips underscore-prefixed paths.
touch .nojekyll

for p in "${PATHS[@]}"; do
  [[ -e "$p" ]] || { echo "deploy: missing $p — run its pipeline first" >&2; exit 1; }
done

# Build the orphan snapshot entirely via plumbing, against a throwaway index
# file -- current branch/HEAD/working tree are never touched, so there is
# nothing for a later `git checkout` to disturb (see note above; this script
# intentionally contains no `git checkout` at all anymore).
# `mktemp -u` only reserves a NAME, not a file: git initializes a fresh index
# the first time GIT_INDEX_FILE is written to, and chokes ("index file
# smaller than expected") if the path already exists as an empty file.
IDX="$(mktemp -u)"
trap 'rm -f "$IDX"' EXIT
export GIT_INDEX_FILE="$IDX"

git add -f "${PATHS[@]}"
TREE="$(git write-tree)"
COMMIT="$(git commit-tree "$TREE" -m "Deploy site + data ($STAMP)${NOTE:+ — $NOTE}

Rebuilt and force-pushed as a single commit; this branch intentionally has
no history. Source, pipelines and decision history live on main.")"

unset GIT_INDEX_FILE

git push -f origin "$COMMIT:refs/heads/gh-pages"

echo "deploy: published to gh-pages — https://ottawavisuals.github.io/Energy/"
