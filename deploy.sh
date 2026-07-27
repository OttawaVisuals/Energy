#!/usr/bin/env bash
# Publish the site + generated data to the gh-pages branch.
#
# gh-pages is rebuilt as a SINGLE commit and force-pushed every time, so the
# data never accumulates history. main keeps the source, the pipelines and the
# decision history; this branch is a disposable snapshot of the current bytes.
#
# Usage:  ./deploy.sh ["optional commit note"]
set -euo pipefail
cd "$(dirname "$0")"

NOTE="${1:-}"
STAMP="$(date +%Y-%m-%d)"

# Pages content: every page, the shared assets, and each generated data tree.
# Keep this list in sync with the generated-data block in .gitignore.
PATHS=(
  .nojekyll
  index.html ceud.html construction.html grid.html heatpump.html
  newhomes.html project-atlas.html retrofit-insights.html retrofits.html
  assets
  fsa_json newhomes_fsa newhomes_json province_json insights_json
  ceud_json construction_json grid_json prices_json geo_json census_json
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

START_BRANCH="$(git rev-parse --abbrev-ref HEAD)"
trap 'git checkout -f "$START_BRANCH" >/dev/null 2>&1 || true' EXIT

git checkout -q --orphan gh-pages-tmp
git reset -q
git add -f "${PATHS[@]}"
git commit -q -m "Deploy site + data ($STAMP)${NOTE:+ — $NOTE}

Rebuilt and force-pushed as a single commit; this branch intentionally has
no history. Source, pipelines and decision history live on main."

git push -f origin gh-pages-tmp:gh-pages
git checkout -f "$START_BRANCH" >/dev/null
git branch -D gh-pages-tmp >/dev/null

echo "deploy: published to gh-pages — https://ottawavisuals.github.io/Energy/"
