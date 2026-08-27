# Energy Suite — Project Tracker & Roadmap

The single source of truth for what's shipped, what's in flight, and what's next.
Updated **2026-08-27** (**Construction Tracker** — Tier 2 of the data-sources
expansion, same day as Tier 1. Four additions: a **"Did it sell?"** card
(34-10-0149 absorptions vs unsold inventory, with a months-of-inventory mode)
closing the pipeline past completions; **"The cost of a building, by trade"**
(18-10-0289 BCPI by CSI division — envelope, windows/doors, HVAC, electrical,
concrete, wood — with a building-type picker); a **rental vacancy column** on
the CMA table (34-10-0127); and a **Greener Homes program card** showing grants,
per-province totals and the top-5 retrofit *measure counts*, which are directly
comparable with the ERS-derived measure counts on the Retrofit Explorer.

Three findings shaped the build. **(1)** The BCPI divisions all share one
reference period, **2023 = 100** — verified, the 2023 quarterly mean is 100.00
for composite, wood, concrete and envelope alike. A first draft re-based every
line to 2017 = 100; that was wrong and was removed, because it amplified
whichever series started lowest (wood, off a lumber-cycle trough) and read as a
claim about the trades rather than about their starting points. Plotted as
published, the interesting result is that **HVAC** has run furthest above the
all-trades average since 2023 — which bears directly on heat-pump economics.
**(2)** 34-10-0149 and 34-10-0127 are **CMA tables with no provincial members**,
so the absorptions card shows metros directly, shows the all-CMA aggregate for
Canada (labelled, since it excludes smaller centres and rural areas), and hides
itself on a provincial view rather than inventing a number. **(3)** NRCan's
Greener Homes page publishes no data file, and each province's *name follows its
numbers* in document order — a positional parser pairs them off by one and
silently mis-assigns every province. So those figures are **hand-transcribed**
into `Python/greener_homes_data.json` on `main`, and a new
`greener_homes_verify.py` asserts every one still appears verbatim on the live
page before publishing; it runs `continue-on-error` in the monthly workflow so a
newer NRCan update raises a warning instead of taking the data refresh down.

BCPI division detail ships as a **separate `construction_json/bcpi.json`**
(170.6 KB, 630 series) that the page lazy-loads, because it outweighs the whole
of context.json and only one advanced card reads it. `context.json` 160 KB →
201 KB, 320 series. Verified in the browser on desktop and mobile across
ca/on/pe/ns/toronto: absorptions correctly hidden for provinces, BCPI falling
back to the 15-CMA composite for PEI and Canada, vacancy column sorting, and the
verifier negative-tested to confirm it exits non-zero on a stale figure. See
[docs/CONSTRUCTION.md](docs/CONSTRUCTION.md).)

Prior update **2026-08-27** (**Construction Tracker** — Tier 1 of the data-sources
expansion. Three new StatCan series join the context ETL and two new page
sections are built on them, plus one section that needed no fetch at all.
**"What it costs"**: the old trailing-12-month investment-by-work-type chart
(2017-start, nominal-only) is replaced by the **Housing Economic Account**
(36-10-0677) — new construction vs renovations vs ownership transfer costs,
annual from **1961**, with a nominal/real toggle; and a new **renovation price
index by project** (18-10-0286) showing heat pump, furnace, windows, solar
panels and roofing against the all-projects composite. **"How green is what we
build"**: housing starts against the median EnerGuide rating of new homes
evaluated in the same province and year, read straight from the existing
`newhomes_json/` — no new pipeline. Advanced mode gains **construction job
vacancies and average offered wage** (14-10-0442) beside the employment-vs-
backlog chart, because employment alone can't separate a labour shortage from a
demand slump.

Two coverage rules drove real UI decisions rather than footnotes: 18-10-0286
publishes its 45 project types for **CMAs only** (provinces and the national
composite carry the composite alone; PEI has no member), so that card has its
own metro picker instead of following the page geography into an empty cell;
and EnerGuide covers only the evaluated share of new construction, so years
under 30 evaluations are suppressed, provinces with fewer than three usable
years are hidden outright (Quebec, which has two), and the note reports the
latest median with its sample size rather than a first-to-last delta — these
medians are not monotonic and an endpoint change would imply a trend the data
doesn't show. Also re-verified the documented provincial pipeline gap against
34-10-0136 and 34-10-0143 through 2026-07: still null for every province *and*
Canada, including the Toronto and Montréal members inside 0143. The caveat
stands. One shared-helper change: `extract_table()` takes an optional `floor`
and normalizes annual `REF_DATE` from bare `YYYY` to `YYYY-01` before the floor
comparison — without it the 1990 default trim would have silently dropped a
year of the annual cube. `context.json` 79 KB → 160 KB, 287 series. Verified in
the browser on desktop and mobile across ca/bc/qc/pe/toronto, no console errors.
See [docs/CONSTRUCTION.md](docs/CONSTRUCTION.md).)

Prior update **2026-08-27** (**Heat Pump Explorer** — new collapsible "The 8,760
hours behind these numbers" section, immediately before the methodology
accordion: a 16-column, row-per-hour readout of the full simulated year
(outdoor temp, load, run status, and COP/capacity/energy/GHG/cost split by
baseline/heat pump/backup), with a month filter and a full-year CSV export.
No new calculation — the heat pump's per-hour COP and capacity were already
computed inside the dispatch loop and discarded after use, now captured
into the engine's returned `hourly` object; per-hour cost reuses the
existing `buildHourlyCostSeries()` the cost chart already relies on, so the
table can't drift from it. Building it surfaced a real bug, fixed same
pass: the sticky header's tinted group-background colours were low-alpha
`rgba()` with nothing opaque behind them, so scrolled body rows showed
through the header on scroll; fixed by compositing the tint over an opaque
base in the same `background` shorthand. See `HeatPump/METHODOLOGY.md`'s
2026-08-27 "Full hourly data table" entry.)

Same-day follow-up **2026-08-27** (**Retrofit Insights** §10 reworked from user
feedback: a **building-type multi-select filter** (pills, all on by default)
now drives every chart/table in the section; the old "all cases" table became
a **project summary table** (Project, Location, Year Built, Status, Building
Type, Energy Saving, Retrofit Type, Performance Level); and a new **R-value
slopegraph** — one small chart per envelope component (attic/roof, wall,
foundation wall, each on its own R-value axis since the scales don't share
well), pre-retrofit axis on the left and post on the right, one line per
project coloured by that project's overall energy saving % — sits above a
matching **envelope-values table** (the chart's data, in table form, limited
to the ~34 cases reporting at least one envelope R-value). Hand-built inline
SVG for the slopegraph, same pattern as the choropleth map elsewhere on this
page (colours resolved from `readPalette()` and baked in at render time, so
the section re-renders on every theme change rather than relying on CSS
`var()` inside the SVG string). Filter state persists across a theme toggle.)

Same-day follow-up **2026-08-27** (**Heat Pump Explorer** — performance fix
for the new hourly table, reported live within hours of shipping: the table
was rebuilding all 8,760 rows of DOM on **every recompute** while its
section stayed open, not just once when opened, so leaving it expanded
turned every slider drag or dropdown change into a 5–10s stall. Fixed with
virtualized rendering — only the ~30–40 rows inside the scroll viewport
are ever in the DOM, via two spacer `<tr>`s sizing the rest of the
scrollbar for it; row *data* (`hdtRows`, plain JS objects) still rebuilds
in full every time, only the DOM render is windowed. Measured live on the
deployed page: table-render cost dropped from ~780ms to ~60ms, and the
added cost of having the section open during a recompute dropped from
~780ms+ to ~190ms (on top of the page's pre-existing ~440ms recompute cost
from its own chart redraws, unrelated to this feature and unchanged).
Verified against the exact reported scenario — table open, then a real UI
dropdown change (baseline fuel) — with no perceptible lag and correct
table contents. See `HeatPump/METHODOLOGY.md`'s 2026-08-27 "Full hourly
data table" entry, updated in place.)

Prior update **2026-08-25** (**Retrofit Insights** — new §10 "One house at a time":
a second, external dataset alongside the ERS-derived numbers. Scraped Retrofit
Canada's case-study library (48 self-submitted deep/net-zero home retrofits,
shared under their site's open-content terms) via new
`Python/retrofit_casestudies_scrape.py` into `retrofit_casestudies_json/_all.json`,
filtering out 7 non-residential/non-Canadian cases (documented, not silently
dropped) to 41. Shows min–median–max ranges (R-values, ACH50, EUI, GHG/energy
savings) by performance-level bucket, plus a sortable table linking out to each
source; kept deliberately separate from and never averaged with the ERS numbers
elsewhere on the page. See `docs/RETROFITS.md`'s 2026-08-25 changelog entry.)

Prior update **2026-08-24** (**Heat Pump Explorer** — Ontario grid-EF surface
temperature proxy switched from Toronto to London. Toronto's 2020–2026
weather record only reaches −22.6 °C (5 hours colder than −22 °C), so the
surface's coldest `coarse_t` bins were thin/absent and Step 5's grid-carbon
chart flatlined below −22 °C (fell through every thin-bin fallback to the
flat global-mean shape ratio). Checked against IESO's hourly generation
data first: London tracks province-wide gas output as tightly as Toronto
does (winter `corr(temp, gas MW)` = −0.420 vs −0.419; both track within
1–3 °C of Toronto at the actual top-30 gas-output hours 2020–2026) while
reaching −24.8 °C with 44 hours below −22 °C — Ottawa was also checked and
rejected as colder but a worse demand proxy (runs 5–10 °C colder than
Toronto/London at the same peak-demand hours). `ef_surface_on.json`
regenerated (`build_ef_surface.py`, `PROVINCES["ON"]` now `London`);
reconstruction validation still passes (worst per-year diff 5.2%, within
the ±10% tolerance). Separately, added cold/warm-tail **extrapolation** to
the browser engine (`extrapolateShape()` in heatpump.html) so any
temperature beyond the surface's thin-bin edge — for any province, not just
ON — gets a least-squares trend fit through the tail's 6 most extreme
sufficiently-sampled `coarse_t` bins instead of snapping to the flat global
mean; a naive 2-point edge slope was tried first and rejected as too noisy
(outermost bins have the fewest hours). `METHODOLOGY.md` "Province vs. city
temperature" and "Thin-bin fallback" sections updated with the correlation
check and the extrapolation method.)

Prior update **2026-08-21** (**Heat Pump Explorer** — four UI/methodology fixes
from user testing. (1) **Month/week zoom** added to all 7 "Full year"
charts (weather, load, equipment, energy, grid GHG, emissions, cost): a
per-chart month dropdown (day-by-day view) and week dropdown (hour-by-hour
view), independent per chart, built on a shared `sliceRange()` helper so
axis ticks and hover tooltips report the real calendar date even when
zoomed. (2) **Propane backup** added to the "Backup heat" dropdown — the
simulation engine already supported it (90% AFUE) but it wasn't selectable;
also fixed a latent `stepCurves().isFuel` bug that would have shown propane
backup as if it were electric (no switch-over line/label) had it shipped
without the check. Backup AFUE (gas 95% / oil 85% / propane 90%, fixed, not
user-adjustable) documented in the methodology under "Energy purchased" for
the first time. (3) **Two backup colors**: fossil-fuel backup (gas/oil/
propane combustion) and electric-resistance backup now render in distinct
colors (new `--backup-fossil` / `--backup-elec` tokens in
`assets/site-theme.css`, themed for light/dark/colour-blind) instead of
sharing one amber swatch, with the fuel name threaded through every legend
("Backup — propane") instead of a bare "Backup". (4) **Upstream-methane
hourly bug fixed**: the "Upstream losses" toggle's methane-equivalent adder
was only ever added to the *annual* total (`m_base_ch4`/`m_proj_ch4`), never
to the *hourly* emissions arrays (`h_base_ghg`/`h_bk_ghg`) that every
temperature/weighted/full-year chart reads — so those charts showed only
line-loss's effect on electricity when the toggle was flipped, never
methane's effect on gas, even though the annual total was already correct.
Fixed by folding each hour's methane contribution into the hourly series
too; verified live that `sum(hourly.base_ghg_kg) === base.ghg.total` exactly
(no double-count) and that toggling upstream now moves the hourly sum
(+4,428 kg/yr on a gas baseline in Ottawa). Also added the switch-over/
hard-cutoff reference lines and a green/backup-color stacked split to the
emissions "By temperature" view, matching the equipment chart's convention.
Verified live via a local static server (screenshots render blank in this
sandbox's preview pane per the known no-rAF quirk — confirmed via DOM/JS
inspection instead): engine self-test still passes, zero console errors
across all 7 charts' daily/hourly/week/month combinations.) Same-day follow-up
(**Heat Pump Explorer** — chart-readability pass, also from user testing.
**(a)** Y-axis titles shortened across every chart to a plain `<unit> <what>`
(e.g. "kg CO₂e/hr", "kWh purchased"), with the fuller explanation left to
each chart's existing note paragraph rather than crammed into the axis
label. **(b)** Every axis/label now says *which* quantity it is — "heat
needed" (load, Step 2), "heat delivered" (equipment, Step 3), or "purchased"
(electricity/fuel bought, Step 4) — so the three are never ambiguous against
each other. **(c)** Full-year day-by-day views for the three *quantity*
charts (Step 4 energy, Step 6 emissions, Step 7 cost — kWh/kg/$) now show
each day's **total**, not its mean; the three *rate* charts (Step 2 load,
Step 3 equipment, Step 5 grid intensity — kW/°C/g-per-kWh) correctly keep
the daily mean, since summing a rate isn't meaningful. New `toDailySum()`
alongside the existing `toDaily()`, selected via a `sumMode` flag on
`sliceRange()`. **(d)** Step 6's "By temperature" view was missing the
zero-heat/design/switch-off reference lines that Steps 1, 2 and 5 already
draw — it turned out a shared `drawStepRefLines()` helper already existed
(built for Step 5) and Step 6 just wasn't calling it; now it does, replacing
the equipment-style switch-over/HP-cutoff pair that didn't belong on a
weather-exposure chart. **(e)** Final numbers section tidied: the
before/after bar rows (`.beforeafter`/`.ba-row`) were each their own
independent CSS grid, so sibling rows' label columns sized to their own
text and the bars started at different x-offsets row to row — moved the
grid to the shared parent with `.ba-row{display:contents}` so all rows
share one set of column tracks. The "Annual operating cost" card also
repeated the same two dollar figures twice (once in the bar chart, again in
a text list below) — the text list is gone, the bars gained a third
"Saves/Costs" delta row (matching the emissions card's existing three-row
convention) and each bar's sub-detail (kWh/m³ breakdown) moved into a
`<small>` under its label instead. **(f)** Added a "Download one-page
summary" button (Final numbers section) that populates a dedicated
`#print-summary` block — scenario recap (every dropdown/slider's current
value, read live from the DOM), the verdict headline, the KPI tile strip,
the energy chart rasterized to a PNG via `canvas.toDataURL()`, and the
emissions/cost bars, with page CSS vars force-overridden to light-theme
values so it prints correctly regardless of the page's current theme — then
calls `window.print()`. No PDF library, no server round-trip: the browser's
own print-to-PDF is the only dependency-free option under this repo's "no
build step, no external runtime deps" rule, so that's what "download" means
here (Save as PDF in the print dialog). Verified live: all DOM content
populates correctly (selections table, 7 KPI tiles, verdict text, rasterized
chart image, both bar sets), the `@media print` rule is present and scoped
to `#print-summary`, zero console errors.) Prior pass
**2026-08-19** (**Heat Pump Explorer** — three result-affecting
defects fixed, found by an external methodology audit and each verified
against the code before acting (the same audit's three "P0" retrofit findings
were checked and rejected as false positives — already-correct behaviour it
couldn't see because the reviewer had no access to `assets/retrofits.js` or
the Python). (1) **Upstream-oil adder removed**: `buildOpts()` passed
`oilUpstreamFrac: 0.12` unconditionally, so "Upstream & grid losses: **No**"
never zeroed it, despite the page stating that switch zeroed every upstream
term; the 12% had no source anywhere in the repo and no propane equivalent.
Removed outright — option, accumulator and `upstream_oil` output field — not
merely defaulted to zero, so it cannot be silently reinstated. (2) **Fuel
constants reconciled with the retrofit pipeline**: combustion factors were
181 / 275 / 214 g CO2e/kWh against `Python/ghg_factors.py`'s
185.4 / 255.4 / 213.6 for the same fuels, each hardcoded beside its own
inconsistent energy content (gas 10.55 kWh/m³, oil 10.0 kWh/L) — and the gas
entry did not reproduce its own stated basis (1.921 ÷ 10.55 = 182.1, not
181). Factors are now *derived* from volumetric factor ÷ energy content, with
both tools reading one set of conversions, and the cost layer's separately
hardcoded oil conversion now reads the engine's exported constant. (3)
**Default grid-basis contradiction resolved**: the page (in two places) and
`HeatPump/METHODOLOGY.md` all described marginal as the default, but
`state.efBasis` has always initialised to `'average'`. Aligned docs to code
by user decision — the tool opens on hourly average, the like-for-like basis
with the studies it benchmarks against, with marginal one click away in
Advanced. Impact: an **oil-heated baseline falls ≈17%** (7.7% from the
factor, the rest from the dropped adder), taking the oil savings headline
from ~46% to **35%**; gas baseline rises ≈2.4% (savings 47→48%); propane
−0.2%. The TAF +65% methane calibration was re-checked under the new
constants and survives (+64.8% → +64.4%); an exact re-solve would give 2.152%
rather than the shipped 2.14%, deliberately left un-retuned rather than churn
every published figure for a rounding-level gain. Verified live: all 15
engine self-test vectors pass (two expected values moved with the constants),
zero console errors, oil path exercised end-to-end through the UI.) Prior
pass **2026-08-12** (**Heat Pump Explorer** — in-page methodology section
rebuilt: reordered to follow the page's own Step 1–7 sequence (was drifting
from it as sections were added over time), all "previously X, now Y" /
dated-correction narrative removed (page states only what's currently
true — the chronological history stays in `HeatPump/METHODOLOGY.md`), long
paragraphs replaced with bullets/tables, every assumption paired with its
source. Three previously-separate analyses folded into the step they
actually support: the ERS per-house balance-point derivation into Step 2
(Heat load), the AHRI/ERS tier-selection method into Step 3 (Equipment),
and the methane leakage map into Step 6 (Emissions) as part of the
upstream-methane term it backs. The three `data-method` info-button jump
anchors (`m-grid`, `m-lifecycle`, `m-methane-map`) were preserved. No
calculation changed — presentation only. Verified live: correct step
order, zero console errors, all jump links resolve.) Prior pass **2026-08-12**
(**Heat Pump Explorer** — line loss made
province-specific, replacing the flat 5%. User's original ask was to apply
ENERGY STAR's 1.83 "source-site" ratio (reasoning: IESO data is generation,
not purchase) — investigated first rather than implemented blind, since 1.83
is dominated by generation *thermal-conversion* inefficiency (already baked
into the grid EF's g/kWh figure) not delivery loss, and applying it would
have double-counted; IESO's own transmission loss is only ~2%, nowhere near
83%. The legitimate version of the concern (generation-basis EF vs.
delivered-electricity purchase) is the existing line-loss term — re-derived
with real province-specific regulator data instead of a flat Canada-wide
estimate: **ON 7.4%** (OEB's audited distributor Total Loss Factor +
IESO's own transmission loss, compounded), **AB 7.68%** and **QC 7.5%**
(both already-blended CEA/Régie de l'énergie figures) — all higher than the
old flat 5%, all dated 2002–2008 sources (best available, flagged as such).
BC/MB/NS/SK keep the 5% fallback (no province-specific source found, no
hourly grid pipeline either). Small impact on already-published benchmark
figures (+2.3–2.6% on the electricity-GHG term only, flagged in the
Phase 7 validation section rather than silently left stale). New standing
rule from this pass: flag inaccessible/unverified sources and shaky
premises before building on them (project memory
`source-access-and-assumption-transparency`).) Prior pass **2026-08-12**
(**Heat Pump Explorer** — tiered electricity pricing
removed by user request: correctly pricing the added heating load within a
tiered plan required assuming a non-heating household baseline (750 kWh/mo
ON, 25 kWh/day QC) this tool has no way to know for a real household.
Removed from `heatpump.html` (tier cost functions, baseline constants,
`tiered` plan-selector entry) and `Python/rates_etl.py` (ON no longer
collects the OEB tiered tariff; regenerated `prices_json/on.json`). Quebec
had no non-tiered plan at all (Hydro-Québec Rate D has no flat residential
option), so rather than leave Quebec's cost card broken, its plan is now
priced at Rate D's tier-2 marginal rate applied to all modelled
electricity — needs no baseline assumption, since any home with a material
electric heating load pushes daily usage past the 40 kWh/day first-tier
threshold regardless of its other draws. `rates_etl.py`'s Montreal
self-check band updated ($150–200, was $120–185) to match. Verified live:
ON shows only TOU/ULO, Quebec's cost card renders with "marginal (top-tier)
plan" and no console errors.) Prior pass **2026-08-12** (**Heat Pump
Explorer** — refrigerant charge mass
replaced with real manufacturer data: found that the spec-sheet PDFs
already on file for capacity/COP curve work (`data/raw/spec_sheets/`) also
list factory refrigerant charge — extracted 6 R-410A and 4 R-454B
data points (model, rated capacity, factory charge, all cited in
`HeatPump/reference/refrigerant_charge_datapoints.csv`) and fit a linear
`charge_kg = a + b × capacity_kW` model per refrigerant, replacing the
prior flat, unsourced 0.250 kg/kW R-410A baseline. Real units run 15–142%
higher than that baseline across the sampled capacity range, and show
smaller units carrying *more* charge per kW — a shape a flat ratio can't
express. R-32/R-290 (no manufacturer data found) still fall back to a
peer-tool ratio, now applied to the new curve's shape rather than a flat
number. Also corrected how the prior GWP sourcing pass was reported: the
primary IPCC AR6 table had returned HTTP 403 to the fetch tool and was
never actually opened, though the writeup at the time said "confirmed" —
user added the PDF to the repo directly, it was read in full, and every
GWP20/GWP100 figure already shipped matches the primary table exactly, to
the decimal. New standing rule saved to always flag inaccessible sources
and weak corroboration explicitly going forward (project memory
`source-access-and-assumption-transparency`).) Prior pass **2026-08-12**
(**Heat Pump Explorer** — refrigerant GWP20 added as a
user toggle: the refrigerant leak term previously only ever used GWP100; a
new "GWP horizon" segmented control (100-yr default / 20-yr) lets a reader
see the near-term-forcing view, matching the horizon the upstream-methane
term already uses. GWP100 values independently reproduced from AR6's own
per-molecule table (GHG Protocol's AR6 reprint); GWP20 values (sourced from
BDA's peer-tool review) cross-checked against a second independent source, a
refrigerant-industry compliance table built for NY State's AR6-20yr mandate
— both confirm the same blend-weighted figures almost exactly. Charge-mass
ratios also spot-checked against generic HVAC density-based line-set-charge
guidance (R-32/R-454B ratios land within ~1-2 points of independent
industry figures). `heatpump.html`, `METHODOLOGY.md` and
`BDA_COMPARISON.md` updated; engine self-tests unaffected (18/18 Python
mirror assertions pass).) Prior pass **2026-08-12** (**Heat Pump Explorer** — real-homes balance-point bug
fix: the per-house "0-heat" balance point in the real-homes explorer
(`house_profiles_<city>.json`) was anchoring its UA calculation on the balance
point being solved for, instead of HOT2000's fixed 21°C indoor design
setpoint — inflating UA and biasing every solved balance point 3-4°C too low
(confirmed on a 10-home Toronto sample), worst for high-loss "worst" homes,
which is why Toronto's worst-house figure (11.5°C) read far colder than
NRCan/CanmetENERGY's comparable published figures (~10-16°C). A regression of
a bug already caught once at the archetype level (see METHODOLOGY.md "UA from
design heat loss"). Fixed in `check_balance_point_k1s.py` and
`build_city_house_profiles.py`; all 14 cities' `house_profiles_*.json`
regenerated (747,829 homes, drop rates unchanged); `heatpump.html`'s
real-homes advanced-methodology text and a new `METHODOLOGY.md` "Real-homes
balance-point fix" section document the before/after math. The fix closes
roughly a third to a half of the gap to CanmetENERGY's figures — the rest is
an already-documented, not fully closable, steady-state/occupant-behaviour
modelling gap, unaffected by this change.) Prior pass **2026-08-12** (**Heat Pump Explorer**: new "Where upstream methane
comes from" section — a Canada map of fugitive oil/gas/coal methane
(NASA GES DISC's Global Fuel Exploitation Inventory, 2016, the newest vintage
at this scope) grounding the page's existing 2.14% upstream-methane lever in
real geography. Shipped, then refined same day across two follow-up passes:
native 0.1° resolution rendered to a canvas pixel buffer (not SVG rects —
doesn't scale to ~115k cells) with oil/gas/coal/total toggle; "background"
cells flagged and shown flat-gray, distinct from the real amber log-ramp
signal, after checking the raw data directly (56–78% of nonzero *gas* cells
share an exact value with other cells — a shared regional proxy rate GFEI
applies where it can't spatially resolve, not real per-cell detail — vs.
~1% for oil), with a toggle to hide them; cropped to a unioned Canada
boundary polygon (built from the existing FSA choropleth geometry plus
Yukon, which was missing from it) instead of a raw bbox that bled into the
US, with a simplified version of the same polygon drawn as a reference
outline; and a sinusoidal (Sanson-Flamsteed) projection replacing the flat,
unnaturally-wide-at-the-north raw grid, itself swapped same day for an
**Albers Equal-Area Conic** projection (Canada's standard thematic-map
parameters) after comparing six candidates side by side — Albers over the
more familiar Lambert Conformal Conic specifically because this map's
colour encodes emissions *per km²*, and Albers (unlike Lambert) keeps
on-screen area proportional to real land area. A conic projection needs a
real per-pixel inverse-project-and-sample remap rather than Sinusoidal's
per-row scale; that lookup table is built once per data load and reused by
every re-render and by hover (~60ms build, ~15-20ms per toggle, measured
in-browser). Section (and "What real homes in \<city\> look like") now
`<details>`-collapsed by default, with the map's ~3MB JSON fetch deferred
to first expand; default view is gas + background hidden, the most
legible combination. New `Python/gfei_ch4_extract.py` +
`Python/canada_boundary.py` pipeline steps. Explicitly labelled as a bundled
oil+gas+coal fugitive-emissions layer, not a pipeline-only one, despite
starting as "pipeline GIS data" in an earlier session — see
`HeatPump/METHODOLOGY.md`'s "Methane leakage map — GFEI 2016" entry and its
two same-day follow-ups.) Prior pass **2026-08-09** (**Heat Pump Explorer** — theme parity: brought the
page onto the shared `assets/site-theme.css` system so it finally carries the
light/dark/colour-blind toggle every other advanced page already had. Deleted
its duplicated, drifted light-only chrome (reset, `:root`, header, hero,
`.info-btn`, footer) in favour of the shared file; reclassified every legacy
`var(--white)` to `--card` (surfaces that must invert) or `--on-navy` (text on
navy), added a themed `--brown`, and pinned the spec-table's fixed-pale legend
cells to dark text so dark mode stays legible; restructured the header to the
shared `.header-left`/`.header-title` pattern plus the 3-icon theme pill; and
added the pre-paint theme script + `setTheme`/`syncThemeButtons`/
`redrawAllCharts` (charts already read colours through a `css()` helper, so a
toggle just rebuilds them). The bespoke "Advanced settings" disclosure was kept
as an intentional exception rather than swapped for the shared Simple/Advanced
pill. Verified in-browser across all three themes — chrome inverts, the SVG
charts re-theme (surface `#E8EDF4`↔`#1B2735`), the lazy tier-viz canvases
rebuild without error, and there were zero console errors; the "CEUD Explorer"
header link was dropped to make room for the theme pill (still reachable via
"All tools"). CSS/markup only — no pipeline or data change. This was the last
interactive tool still off the shared theme.) Prior pass **2026-08-07**
(**Heat Pump Explorer**, later same day: extended the
Step 1 KPI-rail/toggle-in-title-row layout to every step (2 through 7),
flattened the top verdict KPI row from 3 tier-grouped rows to one 7-column
row, and reworked several steps' KPIs and chart content while auditing them
— Step 1's set changed to HDD/hours-below-zero-heat/hours-below-switch-off/
hours-below-−20°C/hours-below-−10°C; Step 2 lost the redundant "By month"
toggle, gained design-temp/switch-off reference lines and an average-load
KPI, and fixed a mislabeled "Heat delivered" legend that should have read
"Heat needed"; Step 3 dropped COP (now redundant with Step 4's dedicated
chart) and gained a "Hours it could run" upper-bound KPI. That Step 3 audit
surfaced two real rendering bugs, now fixed: the by-temperature chart's
delivered-heat line sloped across the last 0.5°C step at the cutoff instead
of dropping vertically (implied output that wasn't real), and the full-year
hourly chart's backup-heat polygon closed with a single straight line
between the year's first and last hour instead of tracing every hour
in between, self-intersecting with the load curve and painting spurious
backup-heat slivers in summer months with zero heating load.) Earlier that
day: Step 1's weather chart now marks
the zero-heat and switch-off temperatures on both the by-temperature and
hour-by-hour views, with collision-avoiding label placement so the two don't
overlap when they land close together (common with an electric-backup tier,
where the switch-off temperature is the tier hard-stop rather than a fuel
switchover). Controls box condensed: now sticky below the header on scroll
(same pattern as `retrofits.html`'s filter bar, labels drop once scrolled),
grid widened to 5 columns, "Grid emissions basis" converted from a 3-button
segmented control to a dropdown, and "Methane leak" + "Line losses" collapsed
into a single "Upstream & grid losses" Yes/No toggle (Yes = methane 1.5%, line
loss 5% — fixed representative values, not independently adjustable; **flagged
as a to-do** below to reinstate per-term control). The old "All years" weather
comparison button and its chart section were removed — fully superseded by
the new Step 1 chart, which already overlays every year as backdrop with
TMY/coldest/mildest/selected highlighted. Controls condensed further same day:
grid widened again to 7 columns (2 tidy rows), several labels shortened to
fit ("Zero-heat temp.", "Emissions basis", "Upstream losses") with a
nowrap+ellipsis safety net so a too-long label clips instead of wrapping and
throwing sibling controls out of vertical alignment, the switch-over
auto-reset button shrunk to an icon, and the "Selected heat pump" model-name
readout removed again — it only existed to fill a slot that's no longer
free.) Then, on 2026-08-06: (**Retrofit
Explorer**: re-measured the `HPCAP`-vs-AHRI
sizing claim and resolved the `COP` rating-condition question raised while prepping
the NRCan/EnerGuide demo. `HPCAP` (auditor-entered capacity) still runs unreliable —
median 1.6× the certified 47°F capacity over 318,585 rows, 1×/2×/4× clustering, 63%
of repeated AHRI codes inconsistent row-to-row — but the generic `COP` field turned
out not to be an error at all: a NEEP performance-table cross-check for the site's
most common installed unit (AHRI 211644151) shows the ERS `COP` median (2.99)
matches NEEP's **47°F**-rated COP (3.00), not the certificate's 5°F COP (1.80) it was
being compared against. AHRI's own search API has no 47°F COP field to validate
against directly (confirmed by enumerating all 40 fields it returns). The
cold-climate-ASHP-only fields `CCASHPCOP` and `CCASHPCAPACITYMAINTENANCE` already
carry a same-condition comparison and track the certificate closely (median 0.0pp
difference on capacity maintenance, 85% within ±10pp) — not yet used on the page.
Removed the old "1.55×" figure from `retrofits.html`'s sizing-chart note and added
a full writeup to the AHRI-enrichment methodology section. Also added, to the
pairing-gates methodology note: a full gate-by-gate breakdown of the ~177,880
nationally-dropped D&E pairs (roughly two-fifths Gate B date-order, one-fifth Gate C
floor-area, one-third Gate D structural), extending the existing Gate A/B
measurement to Gates C/D. New diagnostics: `Python/diagnose_hpcap_vs_ahri.py`,
`Python/diagnose_ccashp_vs_ahri.py`; `Python/diagnose_pairing_drops.py` updated to
match the shipped pipeline (it had gone stale after the 2026-07-18/-24 gate fixes
below). See `docs/RETROFITS.md`'s 2026-08-06 changelog entry.
Then, on 2026-08-05: new CEUD-sourced
**energy impact KPI card** — kWh/GWh saved, priced $ saved, a "homes powered for a
year" equivalent, and an EV-km equivalent, plus icons on both the GHG and energy
equivalency grids — and a **cumulative-audits-vs-housing-stock line** on the Retrofit
Insights timeline chart. Also fixed: the scorecard table's max-value bars used to run
edge-to-edge and blend into the next column; and `Heating_Change`/`HeatPump_Addition`
were double-counting the same homes in every aggregate measure-mix chart on **both**
pages (a heat pump addition is itself a furnace type/fuel change) — `Heating_Change`
now excludes heat pump additions downstream, no ERS pipeline rerun needed. Also new:
a **peak-demand card** — design/peak heat-loss decrease, by province, for the 388,842
matched pairs that were electrically heated pre-retrofit (732,283 kW national total,
42% of which added a heat pump), with a dropdown pricing the avoided kW against any of
the 12 resources in IESO's 2024 generation resource-cost table. See
`docs/RETROFITS.md`'s 2026-08-05 changelog entry.
Then, on 2026-08-04: new
**"Program era" filter** — ecoENERGY (2007–2012) / no program / Greener Homes
(2021–2024), classified by each home's initial audit year — in Retrofit Explorer's
FSA, province and Canada views, plus a companion "what did each era build" measure-mix
chart on Retrofit Insights. See `docs/RETROFITS.md`'s 2026-08-04 changelog entry.
Then, on 2026-08-03: new
**pipeline-overview diagram** at the top of `retrofits.html`'s advanced
methodology — the CSV → parquet → JSON → page flow as hoverable/focusable SVG
boxes, each tooltip carrying the real numbers, filters and datasets behind that
stage, including the emission-factor and retrofit-cost branches. Then a
**documentation and deploy audit across both retrofit pages**, which turned up
one live-site break and several drifted claims. Fixed: `deploy.sh`'s `PATHS`
was missing `retrofit_costs_json`, so the next full deploy would have silently
deleted the entire cost feature from the published site (it was live only via
an earlier incremental push); Retrofit Insights §06B was **already dead on the
live site** because `insights_json/hp_ahri_scatter.json` and `cchp_screen.json`
were never generated into the deployed tree —
`Python/build_hp_equipment_insights.py` is a separate script from
`build_insights.py` and had been missed, now re-run and documented as its own
step; every relative `docs/`/`ROADMAP.md`/`HeatPump/` link on both pages 404'd
(those paths aren't deployed to `gh-pages`) and now point at the `main` blob;
Retrofit Insights' NRCan open-data footer link was a dead dataset ID. Corrected
on the pages: the cost POC's coverage is **10 provinces + NT/NU**, not "12
provinces + 2 territories"; its 1,420,044-record input is now explained
(apartments/duplexes/triplexes excluded, 31,389 records) instead of silently
contradicting the 1,451,433 matched-pair figure beside it; **solar PV and
HRV/ERV** were priced and rendered but documented in neither methodology
section; REMDB and the ECCC emission factors added to Sources.
`docs/RETROFITS.md` corrected in seven places — stale oil/wood conversion
factors, the superseded exactly-one-D-and-E pairing rule, three sections still
describing `raw.githubusercontent.com` fetches from `main`, the "no dollar
figures are possible" caveat, and the audit range. Full detail:
[docs/RETROFITS.md changelog](docs/RETROFITS.md#changelog).
**Then a local-checkout audit, which found the deploy hazard was far wider
than the cost tree**: 1,429 of the 4,903 files published on `gh-pages` were
absent from this working copy — the whole of `newhomes_fsa/` (1,311 files),
`ceud_json/`, `construction_json/`, `newhomes_json/`, `geo_json/`,
`FSA_Maps/`, `grid_json/`, `Geothermal/output/index.html` and two `lookup/`
files. Since `./deploy.sh` builds `gh-pages` from the working tree, running
it from this machine would have wiped the New Homes Explorer, CEUD, the
Construction Tracker, the grid dashboard, every FSA map and the geothermal
page. All 1,429 restored from `origin/gh-pages` (188.7 MB); `deploy.sh`'s
preflight now passes all 31 paths. **Ottawa Case Study Phase 4's feeder half
is unblocked as a result** — `GridCapacity/Hydro.py` and
`ottawa_capacity.geojson` (3,884 feeder polygons with capacity attributes)
were both recovered intact from the 2026-07-27 deploy snapshot, which was the
only place `Hydro.py` had ever existed. Root cause: `/GridCapacity/` was
gitignored wholesale, so unlike every other pipeline script it had no home on
the decision-record branch. `.gitignore` now excludes the directory's
*contents* and re-includes `Hydro.py`, which is committed to `main` here; the
8MB geojson stays ignored. Caveat carried forward: `Hydro.py` is the original
working script, not a cleaned-up one — its `WHERE` clause still matches every
LDC whose name contains "Ottawa" (a `# tighten after you see the distinct
names` note was never actioned) and it writes its output to the current
directory rather than to `GridCapacity/`. It ran and produced the geojson we
hold, so it works; it just hasn't been tidied.) Prior pass
2026-08-02 (**Retrofit Insights + Retrofit Explorer**: GHG
emissions overhaul, in two parts. **Part 1** — new Retrofit Insights section
02 "The climate impact": national + per-province net tCO2e/yr saved (avg per
home and total), priced two ways (2024 federal carbon-tax rate $80/tCO2e;
ECCC's 2024 Social Cost of Carbon, $266/tCO2e C$2021 at 2% discount), plus an
equivalency-card strip (vehicles, flights, oil barrels, forest absorption,
propane cylinders) ported inline from Ottawa Visuals' `ghg_calculator.html`
(no iframe/cross-repo dependency). **Part 2** — building it surfaced that
`Pre_/Post_GHG` (raw `ERSGHG`) is only populated for **50.5%** of matched pairs
nationally (Quebec ~78%, Ontario ~43%, Saskatchewan ~9%), silently limiting
every GHG chart/median on **both** retrofit pages to half the data. Fixed with
a new **GHG basis** dropdown (4 scenarios: `reported` = raw ERSGHG;
`current`/`current_corrected` = flat 2026 official ECCC factor, corrected for
Alberta/Newfoundland; `as_audited` (default) = ERS-calibrated, matched to each
home's own audit year — validated to −0.66% national aggregate bias) on both
pages. Along the way, fixed a **survivorship-bias bug** in
`Python/ers_ghg_factors.py` (excluding true-zero-GHG rows from the factor
derivation had overstated the national aggregate by +12.8%; fixed to +0.16%),
and found the official ECCC electricity factor diverges 18–29% (Alberta) /
27–49% (Newfoundland) from what the ERS data itself implies — not a
within-province effect (see [ENERGUIDE_QUESTIONS.md §5.4](docs/ENERGUIDE_QUESTIONS.md),
a new open question for NRCan). New: `Python/ghg_factors.py`,
`Python/compute_ghg_scenarios.py` (Step 1c). Full pipeline rerun and both
pages verified in-browser this session — not just code-written-untested.
Full detail: [docs/RETROFITS.md "GHG scenarios"](docs/RETROFITS.md#ghg-scenarios).)
Prior pass 2026-07-31 (**Ottawa Case Study**: Phase 4's grid half shipped —
new `Geothermal/scripts/build_heat_demand.py` aggregates the 414k-building
stock onto the canonical 500 m grid; every summed column validated exact
against the building-level total, and city-wide totals independently
reconcile against Phase 2.5/Phase 3's already-published numbers with no
adjustment (6.68 TWh residential exactly; all three electrification policies'
added GWh/MW match to the reported digit). `build_suitability.py`'s existing
demand upgrade hook fired automatically once the file existed. Phase 4's
feeder half was recorded as **blocked** here — `GridCapacity/Hydro.py` and
`ottawa_capacity.geojson` both absent from the checkout, `Hydro.py` never
committed to `main` — **unblocked 2026-08-03**, see the top entry. Full
detail: [Geothermal/README.md §3.13](Geothermal/README.md),
[GEOTHERMAL_STATUS.md](GEOTHERMAL_STATUS.md).) Prior pass same day
(**Retrofit Costs**: like-for-like ASHP heating BAU
(was a uniform gas-furnace assumption — now the home's own pre-audit
equipment, mapped to REMDB, with two self-derived REMDB rows for Oil Furnace
and Electric Boiler REMDB never fit); POC moved from session scratchpad to a
permanent, committed pipeline (`Python/retrofit_cost_extract_fields.py`,
`retrofit_cost_estimate.py`); scaled to full national coverage, all 10
provinces + NT/NU (1.42M paired records, 1.24M priced); electricity
utility-rate source swapped after catching a stale "high confidence"
Saskatchewan rate (~67% understated, over a year stale) in the prior source —
new source is a third-party blog, flagged for further verification, not yet
trusted as settled; natural gas rates found similarly stale (~21 months,
every province) but left as-is pending a replacement source. Full detail:
[docs/RETROFIT_COSTS.md](docs/RETROFIT_COSTS.md).) Prior pass 2026-07-30
(**Retrofit Costs** POC: audited each priced measure's
REMDB area basis directly against the raw REMDB data sheets (air sealing =
house floor area, windows = window's own area, wall/roof = surface area —
all confirmed, not assumed); confirmed REMDB has a real, unused `Air
Sealing` regression driven by measured leakage reduction, flagged as the
next measure to add; checked the NRCan open-data dictionary and confirmed
ERS has no wall-construction-type field (Wood/Steel Stud + Batt stays a
stated assumption); added window frame-material classification from ERS's
`UGRWINDOWCODE` (via `Support.xlsx`'s `Frame` sheet) mapped to REMDB's
Vinyl/Metal classes — 82% of PEI window-change records now get a reported
class instead of a blanket Vinyl guess. Full methodology:
[docs/RETROFIT_COSTS.md](docs/RETROFIT_COSTS.md).) Prior pass same day
(new project **Retrofit Costs** started: a PEI-scoped proof of concept
pairing ERS retrofit records against PNNL/DOE's REMDB ($/measure cost
regressions, committed under `retrofits/USCosts/`) to estimate retrofit cost
per home. Confirmed no per-component envelope area exists anywhere in the
public NRCan ERS extract, so envelope costing runs on documented
rectangle-footprint area proxies; `Python/join_hp_capacity.py` extended to
surface `cooling_capacity_btuh`/`seer2` (already in `lookup/ahri_numbers.json`,
previously unused) enabling ASHP costing with an explicit reported-vs-assumed
ductless/ducted classification. 8,535 / 12,554 PEI records (68%) now have at
least one priced measure.) Prior pass same day
(Retrofit Insights: new section 06 "Cold-climate
equipment" — AHRI COP-vs-capacity-maintenance scatter + the US DOE CCHP
Challenge screen, resolving the "where does this go" decision left open
2026-07-27. New pipeline step `Python/build_hp_equipment_insights.py`; see
[docs/archive/ROADMAP_COMPLETED.md](docs/archive/ROADMAP_COMPLETED.md) item
14.) Prior pass same day (heat-pump **page re-organised** on the retrofit-page
pattern: outcome-first 7-section flow — 01 The verdict (one consolidated block
with KPI tiers: Emissions / Cost & energy / Equipment), 02 Where your emissions
come from (new before→after emissions bar beside the by-category bars), 03 Why:
heat needed vs delivered (was "How the model works"), 04 Across the year (the two
by-outdoor-temperature charts removed as redundant with §03), 05 What it costs to
run (new before→after cost bar; promoted above sensitivity), 06 How confident
should you be? (was "Sensitivity lenses"), 07 methodology. Single-view (no
Simple/Advanced toggle). Prior pass 2026-07-29 (heat-pump engine rebuild
**implemented**: design-load +
balance-point sliders replace archetype auto-sizing, tier × capacity-band
dropdowns pin one of 9 real AHRI-certified cell curves from the new
`build_cell_curves.py` pipeline, backup switchover is derived from backup type
instead of a manual control-strategy dropdown, and the propane
efficiency/methane-leak engine bugs are fixed in both `engine.js` and the
inlined copy. `validate_engine.py` passes.) Prior pass 2026-07-28 (heat-pump
engine rebuild redirected: F280 excludes gains so the ERS design heat loss
stands, sizing moves to a user-set design load, NRCan archetypes parked,
selection becomes tier × capacity — tier-selection scatter built). Same day:
BDA Heat Pump Lifecycle Emissions Explorer reviewed;
lifecycle-update candidates logged — see
[HeatPump/BDA_COMPARISON.md](HeatPump/BDA_COMPARISON.md). Prior pass
2026-07-27: heat-pump load-model rebuild started: city design temperatures step shipped; CCHP Challenge screen added; earlier 2026-07-24 pass verified against the repo and commit history — GitHub Actions run status not directly queried, inferred from bot-authored commits).

- 📦 Full record of completed items (prompts + build notes): [docs/archive/ROADMAP_COMPLETED.md](docs/archive/ROADMAP_COMPLETED.md)
- 🗺️ Visual status page: [project-atlas.html](project-atlas.html) — <https://ottawavisuals.github.io/Energy/project-atlas>
- 📖 Main readme (all links): [README.md](README.md)

---

## 📊 Status board

### Shipped & live ✅

| Tool | Live | Docs | Notes |
|---|---|---|---|
| 🏠 **Retrofit Explorer** | [/retrofits](https://ottawavisuals.github.io/Energy/retrofits) | [docs/RETROFITS.md](docs/RETROFITS.md) | v1 + post-launch additions, audit funnel, pairing fixes (matched 538k → 1.37M → 1.45M), bill card, visual polish, program-era filter (2026-08-04), `Heating_Change`/`HeatPump_Addition` double-count fixed (2026-08-05), HPCAP/COP/CCASHP validated against AHRI+NEEP + full pairing-gate breakdown (2026-08-06) |
| 📈 **Retrofit Insights** | [/retrofit-insights](https://ottawavisuals.github.io/Energy/retrofit-insights) | [docs/archive/ROADMAP_COMPLETED.md](docs/archive/ROADMAP_COMPLETED.md) (item 13) | national big-picture page: leaderboards, choropleth, success analysis, climate/equity linkage, missed-opportunity ranking, program-era timeline; shipped 2026-07-19; measure-mix-by-era chart added 2026-08-04; energy-impact KPI card + cumulative-audits timeline line (CEUD-sourced), electric-pre-retrofit peak-demand card (IESO-priced), and scorecard/`Heating_Change` fixes added 2026-08-05; §10 "One house at a time" added 2026-08-25 — Retrofit Canada case-study ranges (41 residential Canadian cases), kept separate from the ERS numbers; reworked 2026-08-27 — building-type filter, project summary table, and a per-component R-value slopegraph (pre→post, coloured by energy saving %) with its backing table |
| 🏡 **New Homes Explorer** | [/newhomes](https://ottawavisuals.github.io/Energy/newhomes) | [docs/NEWHOMES.md](docs/NEWHOMES.md) | EnerGuide new-construction slice (plan/as-built); shipped 2026-07-15; pipeline reworked 2026-07-22/23 (P/N column-fill, `ers_pn_column_fill.csv`) |
| 📊 **CEUD Explorer** | [/ceud](https://ottawavisuals.github.io/Energy/ceud) | [docs/CEUD.md](docs/CEUD.md) | all 5 sectors live |
| 🏗️ **Construction Tracker** | [/construction](https://ottawavisuals.github.io/Energy/construction) | [docs/CONSTRUCTION.md](docs/CONSTRUCTION.md) | monthly auto-refresh; **first scheduled run 2026-07-20 — watch it go green** |
| 🌍 **Ottawa Geothermal Map** | [/Geothermal/output/](https://ottawavisuals.github.io/Energy/Geothermal/output/) | [Geothermal/README.md](Geothermal/README.md) | v2 complete: conductivity sensitivity, drilling difficulty, segment suitability |
| 🔥 **Heat Pump Explorer** | [/heatpump](https://ottawavisuals.github.io/Energy/heatpump) | [HeatPump/METHODOLOGY.md](HeatPump/METHODOLOGY.md) | v2 complete: 14 cities, weather-year lens, sizing sweep, lifecycle sourcing, operating costs; page re-organised 2026-07-30 (outcome-first 7-section flow, KPI tiers, before→after bars); Step 1 chart gets zero-heat/switch-off markers + controls box condensed to a sticky, 7-col bar (2026-08-07); migrated onto shared `assets/site-theme.css` with light/dark/colour-blind toggle, matching every other advanced page (2026-08-09); propane backup + per-chart month/week zoom on all 7 full-year charts + two-color backup (fossil vs. electric) + hourly-methane bug fix; axis-label cleanup, daily-sum vs. daily-mean split, Step 6 reference lines, Final-numbers tidy-up, one-page PDF summary button (2026-08-21); ON grid-EF proxy city Toronto→London + cold/warm-tail extrapolation (2026-08-24); full 8,760-hour data table with CSV export, before the methodology section, virtualized same-day after a live perf report (2026-08-27) |
| ⚡ **Grid Dashboard** | [/grid](https://ottawavisuals.github.io/Energy/grid) | [docs/GRID.md](docs/GRID.md) | ON/AB generation mix + emissions intensity, average-vs-marginal explainer, Advanced typical-day-by-season panel; shipped 2026-07-24 |
| 🚪 **Landing page** | [/](https://ottawavisuals.github.io/Energy/) | — | one card per tool, cross-linked from every tool's header (`↳ All tools`); shipped 2026-07-24 |
| 🗺️ **Project Atlas** | [/project-atlas](https://ottawavisuals.github.io/Energy/project-atlas) | — | internal status/assumptions page — keep in sync when items ship |

**Data layers behind the tools (all built, all auto-refreshing):**

| Layer | Refresh | Status |
|---|---|---|
| Energy prices (`prices_json/`) | monthly, 3rd — `rates-refresh.yml` | ✅ built; first scheduled run **2026-08-03** (not yet happened) |
| Grid mix ETL (`grid_json/`) | weekly, Mon — `grid-refresh.yml` | ✅ first scheduled run went **green 2026-07-13** |
| AHRI cert lookup (`lookup/ahri_numbers.json`) | weekly, Mon 15:00 UTC — `ahri-refresh.yml` | ✅ shipped 2026-07-22; replaces manual `build_ahri_lookup.py` reruns |
| Construction data (`construction_json/`) | monthly, 20th — `construction-refresh.yml` | ✅ first scheduled run confirmed **green 2026-07-20** |
| Utility rates for bill cards (`utility_rates_reference.json`) | manual (`Python/utility_rates_reference.py`) | ✅ shipped 2026-07-18 |

### In flight 🔨

| Project | Progress | Next step |
|---|---|---|
| 🏙️ **Ottawa Case Study** (heat demand → electrification → grid) | `██████▓░░` Phase 4 grid half done, feeder half unblocked 2026-08-03 | **Phase 4 (feeder half):** both inputs recovered from the 2026-07-27 `gh-pages` snapshot — `GridCapacity/Hydro.py` (now committed to `main`) and `ottawa_capacity.geojson` (3,884 feeder polygons, `capacity`/`capacityrange`/voltage/`ldc_name`). Next: build `feeder_demand.geojson` by intersecting the Phase 4 grid against those polygons, then derive the coincidence/diversity factor from real feeder loading → [item 7](#7-ottawa-case-study--heat-demand-electrification-grid-in-progress) |
| 💰 **Retrofit Costs** (ERS × REMDB cost pairing) | `███████░░` live in `retrofits.html` behind a "Proof of concept" tag — band dropdown, per-measure breakdown, view totals, payback, national data (all 10 provinces + NT/NU; Yukon has no ERS records) | Verify province-mode UI once deployed (local checkout lacks `province_json`/`geo_json`); band-specific payback (currently mid-band only); investigate utility-rate source further (electricity just swapped after catching a stale rate, unverified beyond SK; gas found ~21mo stale, unresolved); source a real footprint-aspect-ratio dataset → [docs/RETROFIT_COSTS.md](docs/RETROFIT_COSTS.md) |

### Queued 🆕

- 🔀 **Heat pump tool — reinstate adjustable upstream methane / line-loss
  rates** (added 2026-08-07). The "Upstream & grid losses" Yes/No toggle on
  `heatpump.html` collapsed two previously-independent sliders (methane leak
  0–5%, line loss 0–12%) into one switch that applies a single fixed value to
  each when on (methane 1.5%, line loss 5%) — done to fit the condensed
  controls box, at the cost of losing the ability to reason about the two
  independently (e.g. a high-leakage gas region on an average-loss grid).
  **Next step:** either bring back per-term adjustability in a more compact
  form (e.g. one combined low/mid/high preset instead of two full sliders),
  or confirm the fixed values are an acceptable permanent simplification.

- ♨️ **Heat pump tool — Phase 3c bucket rework, 36-cell candidate table**
  (spec done, curves outstanding; **superseded as the user-facing priority**
  by the engine rebuild below, which shipped 2026-07-29 with 9 real cells
  wired into `heatpump.html` — see that bullet). Equipment selection rebuilt
  on **AHRI as sampling frame / manufacturer datasheets as measurement**: a
  3×3 grid of COP @ 5 °F × capacity maintenance, 36 representatives chosen by
  real Canadian installation frequency from 439,975 EnerGuide record
  appearances. Spec: [HeatPump/TIER_SPEC.md](HeatPump/TIER_SPEC.md). The live
  tool already selects one of 9 real, individually AHRI-certified units (3
  tiers × 3 capacity bands) with datasheet-sourced curves — no scaling, no
  interpolation — so this bullet now tracks only the **full 36-cell
  candidate table** (for future tier/band boundary decisions and the CCHP
  screen), which remains gated on the `hp_units_joined.csv` reproducibility
  gap below. **Next step, if picked up:** hand-fetch the remaining priority
  units' performance data (datasheets give capacity + lockout; NEEP needed
  for power/COP), then extend `hp_curves.json`.

- 🌡️ **Heat pump tool — heating-load model rebuild** (started 2026-07-27,
  step 1 shipped). The load model is being rebuilt from scratch so the design
  load and load curve are explainable and defensible end to end.

  **Step 1 done: city design temperatures from the station HOT2000 actually
  used.** `HeatPump/pipeline/build_city_design_temps.py` →
  `data/processed/city_design_temps.json`. The raw ERS files carry `WEATHERLOC`
  and `WTHDATA`, which were never carried into `ers_web_*.parquet`; recovering
  them lets each home's `EGHDESHTLOSS` be divided by the design temperature it
  was actually computed at, instead of the 2.5%-ile proxy in
  `build_archetypes.py`. Scanned 1,430,221 matched pairs — **100% matched, 0
  unmatched** — and joined to NBC Appendix C via the new committed
  `HeatPump/reference/nbc_station_design_temps.csv`. **84 cities, 1,020,246
  homes (71.3%), zero homes without a design temperature.** Method + caveats in
  [HeatPump/METHODOLOGY.md](HeatPump/METHODOLOGY.md) "City design temperatures
  from HOT2000 weather stations".

  **Step 2 done: archetypes rebuilt on NRCan's published loads.**
  `HeatPump/pipeline/build_archetypes_nrcan.py` →
  `data/processed/archetypes_nrcan.json`. Decision taken 2026-07-27: **stop
  fitting a balance point to our own data and take both quantities from one
  published source** — NRCan CanmetENERGY *Cold-Climate ASHPs*
  (Cat. M154-149/2022E-PDF) Table 1 + Figure 1. Because each NRCan archetype is
  one house relocated to 16 cities, regressing the 16 published peaks against
  the 16 NBC design temperatures recovers UA and T_balance per archetype
  (R² 0.90–0.93), and independently reproduces the Figure 1 intercepts within
  0.5 °C for archetypes A and B — which also **settles that Table 1 is a
  design-condition load, not a TMY-series peak** (a 16% difference in UA).
  UA is taken **per city** from the published peak, preserving a real
  wind-infiltration effect the single fit discards (archetype A: 389 W/K in
  St. John's vs 291 in Kamloops). **Scope is NRCan's 16 cities for now**;
  TMY covers 11 of them. Full method + limitations in
  [HeatPump/METHODOLOGY.md](HeatPump/METHODOLOGY.md) "NRCan-published archetypes".

  **⚠️ Redirected 2026-07-28 — see "engine rebuild" below.** Decisions taken
  after discussion with a colleague supersede the archetype approach entirely:
  `EGHDESHTLOSS` is a CSA F280 design heat loss and **F280 takes no credit for
  solar or internal gains**, so the ERS heat loss was correct for sizing all
  along and the balance-point worry was the wrong frame for the sizing question.
  Sizing moves to a **user-set design heat load** plus a **distribution chart of
  local design heat loss**, and the **NRCan report and archetypes are parked as
  reference, not used for the methodology**. Step 1 below is therefore
  **cancelled, not outstanding**. Full reasoning in
  [HeatPump/METHODOLOGY.md](HeatPump/METHODOLOGY.md) "Design-heat-load &
  selection rework — decisions taken 2026-07-28".

  **Steps outstanding:**
  1. ~~**Wire `heatpump.html` onto `archetypes_nrcan.json`**~~ — **cancelled
     2026-07-28.** This had in fact been *written* (uncommitted working-tree
     changes to `heatpump.html` and `project-atlas.html`: fetch
     `archetypes_nrcan.json`, city list cut to NRCan's 11, archetypes A–D). It
     was **never committed and never deployed**, and was **reverted on
     2026-07-28** rather than shipped, since decision 2 replaces archetype
     sizing altogether. The live tool continues to run the ERS
     `archetypes.json` / 14 cities until the rebuild lands.
     `build_archetypes_nrcan.py` is committed, so the analysis is reproducible
     if it is ever wanted.
  2. ~~**Commit an explicit peak-load field on a stated percentile**~~ —
     **superseded 2026-07-29.** Moot once sizing moved to a user-set design
     load + balance point (decision 2 in the engine rebuild below): there is
     no computed peak-load field to pin a percentile to anymore, since the
     number comes from the user's own EnerGuide/HOT2000 figure rather than
     a fitted TMY statistic. The 4-point reference display beside the slider
     still uses archetype-vintage medians, not a stated percentile — leave
     as-is unless it causes confusion in practice.
  3. **Decide whether to credit the night setback when sizing.** ERS SOC drops
     to 18 °C for 8 h and the sizing hour falls inside it; CSA F280 takes no
     setback credit because the system must recover. Simulate with, size without,
     and say so.
  4. **Display gross vs net** design load with both definitions stated, and say
     which one sizes the equipment.
  5. **Send the NRCan question list.** All open EnerGuide/HOT2000 questions
     across every ERS-based tool are now consolidated in
     [docs/ENERGUIDE_QUESTIONS.md](docs/ENERGUIDE_QUESTIONS.md) — the blocking
     one is the four monthly HOT2000 fields (`energy_loadGJ`, `solar_gainsGJ`,
     `internal_gainsGJ`, `aux_energy_GJ`) or, failing that, the SOC solar gain
     per city. Answering it would let us return to ERS-derived archetypes and
     recover the population sample, floor areas, local construction practice
     and the townhouse archetype. Also collects the design-temperature /
     weather-library questions, `EGHDESHTLOSS` semantics, `HPCAP` vs
     `CCASHPCAP`, `ERSRating=0`, the pairing-key question, and the ON/QC NBC
     tier gap.

  **Superseded:** the ERS design-temperature rewiring of `build_archetypes.py`
  (step 1's original purpose). `city_design_temps.json` is still the input for
  any future ERS-based work, and the 84-city table stands.

  **Two engine bugs — fixed 2026-07-29** in both `HeatPump/app/engine.js` and
  the inlined copy in `heatpump.html`: propane backup now defaults to 90%
  AFUE instead of falling through to 100%, and the upstream-methane leak
  adder is restricted to `fuel/backup.type === "gas"` only (was misapplied to
  propane using natural-gas density/energy constants). Propane gets no leak
  adder rather than reusing gas's number — no defensible propane
  upstream-loss constant exists yet. Still open, lower priority: no
  part-load/cycling degradation (curves are steady-state, so mild hours are
  optimistic) and no defrost penalty.

- 🔧 **Heat pump tool — engine rebuild: user-set design load + tier/capacity
  selection — implemented 2026-07-29.** Supersedes the archetype sizing path
  above. Four decisions, recorded with their reasoning in
  [HeatPump/METHODOLOGY.md](HeatPump/METHODOLOGY.md) "Design-heat-load &
  selection rework":
  1. **The ERS heat loss was right for sizing.** CSA F280 excludes solar and
     internal gains by design, so `EGHDESHTLOSS` needs no repair as a *design
     load*. The gains question stays open for the *energy* simulation only.
  2. **Sizing moved to the user** — a design-heat-load slider plus a balance-
     point slider, with `UA_W_per_K` derived from both against
     `city_design_temps.json` (84 cities, 1,020,246 homes). A lightweight
     4-point reference display (this city's archetype-vintage medians) sits
     beside the slider for calibration only.
  3. **NRCan report + archetypes parked** as reference; not used for the
     methodology.
  4. **Heat-pump selection = two dropdowns** (performance tier, capacity
     band), replacing auto-sizing. `HeatPump/pipeline/build_cell_curves.py`
     ships `hp_cell_curves.json` — 9 cells (3 tiers × <18k/18–30k/30–42k Btu/h),
     each pinned to exactly one real AHRI-certified unit, no scaling.
     `build_tier_curves.py` now imports `UNITS` from this module.
  5. **Backup dispatch derived from backup type**, not a manual dropdown:
     electric resistance tops up capacity shortfall; gas/oil is a temperature
     switchover via a repurposed switch-over-temperature slider. The existing
     hour-by-hour `simulate()` already implemented both dispatch modes
     correctly, so it was not rewritten — only how the UI derives
     `control.strategy` changed.
  6. A quick ERS check (`HeatPump/pipeline/check_hp_sizing_correlation.py`,
     finding in `HeatPump/TIER_SPEC.md` §6.1) found real installs scattered
     widely against design load (median ratio 0.66, only 24% within ±20%),
     so the UI implies no "correct" sizing ratio.

  Done: the tier-selection scatter (`build_tier_scatter.py` →
  `data/interim/tier_scatter.html`), `build_cell_curves.py`, the ERS sizing
  check, and the full `heatpump.html`/`engine.js` rewiring above.
  `validate_engine.py` passes against the rebuilt engine wiring.

  **Still open:** the `hp_units_joined.csv` reproducibility gap (no producer
  script) still gates the 36-cell candidate table / CCHP screen specifically —
  it does not affect the 9 cells actually shipped, which now have a real
  producer script (`build_cell_curves.py`). The ≥42k Btu/h band is identified
  in the 36-cell table but not yet wired into the simulation (only the 9
  cells across <18k/18–30k/30–42k are simulated).

- 🔬 **Heat pump tool — lifecycle updates from the BDA comparison** (reviewed
  2026-07-28, nothing implemented yet). The Building Decarbonization Alliance
  shipped a [Heat Pump Lifecycle Emissions
  Explorer](https://buildingdecarbonization.ca/report/heat-pump-lifecycle-emissions-explorer/)
  in June 2026 — a single-equation scalar tool with no weather or dispatch, so
  no threat to our load/performance model, but **ahead of us on refrigerants and
  on a forward-looking grid**. Full review, their constants, and where each tool
  wins: [HeatPump/BDA_COMPARISON.md](HeatPump/BDA_COMPARISON.md). Candidate work,
  in priority order:
  1. **Refrigerant GWPs → IPCC AR6, blend-weighted.** Ours are AR4/AR5-era
     (R-410A 2088, R-32 675, R-454B 467, R-290 3) vs AR6 2256 / 771 / 531 / 0.02,
     and the UI's 2088 **contradicts the engine test vector's 2256** for the same
     refrigerant. Correctness fix.
  2. **AC counterfactual credit** — if the household would have installed AC
     anyway, that AC's refrigerant and electricity belong to the baseline. We
     omit it entirely. Should ship as a toggle, not a default.
  3. **Per-refrigerant charge mass** — our single capacity-scaled `charge_kg`
     gives the R-290 option an R-410A-sized charge.
  4. **Forward grid trajectory** from CER *Canada's Energy Future 2026* Current
     Measures, alongside (not replacing) the existing three EF bases. Closes the
     "does not forecast future levels" limitation already flagged in
     METHODOLOGY.md — the one place BDA genuinely leads us.
  5. **Freed-kWh displacement framing** for clean-grid provinces (their QC
     answer). Undecided whether it is in scope.

  Explicitly **not** copying their scalar seasonal COPs (their weakest link,
  our strongest) or their `skeptic`/`central`/`best` preset naming (advocacy
  framing, fails the two-audience test).

- ✅ **US DOE CCHP Challenge screen — shipped on Retrofit Insights (2026-07-30).**
  `HeatPump/pipeline/screen_cchp.py` screens all 15,148 models against
  the [Challenge specifications](https://www.energy.gov/cmei/buildings/cchp-technology-challenge-specifications)
  Table II-3. Headline: **4 models, 8 of 439,975 ERS appearances (0.00%)** clear
  every checkable criterion, and three of the four sit *exactly* on the
  threshold. 34.4% of the base is `out_of_scope` (<24,000 Btu/h, which the
  Challenge deliberately does not address). Surfaced as its own section
  (06 — "Cold-climate equipment") on
  [retrofit-insights.html](retrofit-insights.html), alongside an AHRI
  COP-vs-capacity-maintenance scatter, rather than folded into the 3×3 tier
  grid (no qualifying unit is a cell representative). New pipeline step:
  `Python/build_hp_equipment_insights.py`. Full build note:
  [docs/archive/ROADMAP_COMPLETED.md](docs/archive/ROADMAP_COMPLETED.md) item 14.
  Method in [HeatPump/METHODOLOGY.md](HeatPump/METHODOLOGY.md) "US DOE Cold
  Climate Heat Pump Challenge screen"; caveats in
  [HeatPump/TIER_SPEC.md](HeatPump/TIER_SPEC.md) §6.7.

- 🧾 **Reproducibility gap: two Phase 3c inputs cannot be regenerated**
  (found 2026-07-27). `HeatPump/data/interim/hp_units_joined.csv` — the joined
  15,148-model universe that the bucket grid *and* the CCHP screen both read —
  **has no producer script anywhere in the repo**; it was built ad hoc in an
  earlier session. And `lookup/ahri_numbers.json`, the AHRI scrape itself, is
  not on local disk. Both are gitignored, so the "process, not bytes" rule does
  not currently hold for them: losing `hp_units_joined.csv` would strand Phase
  3c. **Fix:** write the join as a real pipeline step, and confirm the weekly
  `ahri-refresh.yml` still restores `lookup/`.

- 🔧 **Tech debt: consolidate the two heat-pump engines** (deferred, do later).
  `HeatPump/app/engine.js` and the copy inlined verbatim in `heatpump.html`
  (~line 743 onward) are the same ~600-line engine maintained twice — any logic
  change has to be applied to both by hand or they silently diverge, and only
  the inlined copy is what users actually run. Target: one source of truth
  (build step that injects `app/engine.js` into the page, or ship it as a
  separate `<script>` and drop the inline copy), keeping `engine.test.js` and
  `pipeline/validate_engine.py` pointed at it. **Not part of the current
  heat-pump-selection rework — flagged now, scheduled later.**

Otherwise nothing queued — next up is finishing the in-flight Ottawa Case Study
(below), then picking from the project ideas.

---

## 🎯 What's next — recommended order

1. **Ottawa Case Study Phases 4 → 5 → 6** (item 7). The only thing left on the
   board. Phase 4 is the defensibility step (coincidence factor — Phase 3
   proved the undiversified sums are upper bounds); Phase 6 is the public
   narrative page the whole project builds toward.
2. Once Phase 6 ships, pick from **Project ideas** below — nothing queued
   ahead of it.

**Site-wide polish pass — 2026-07-24:**

- [x] Social previews: `assets/og/*.png` (1200×630, generated by
      `Python/build_og_images.py`) + `og:image`/`og:url`/`twitter:card` on all
      nine pages. Rerun the script when a page's title or pitch changes.
- [x] Google Fonts made non-blocking everywhere (`rel="preload"` + onload swap,
      `<noscript>` fallback).
- [x] Analytics (`G-3QLS1Q554N`) now on all nine pages; the loader on
      retrofits.html had been requesting a placeholder `G-XXXXXXXXXX` ID.
- [x] `retrofits.html` CSS/JS extracted to `assets/retrofits.css` +
      `assets/retrofits.js` — repeat-visit transfer 93 KB → 26 KB gzipped.
- [x] New Homes: explicit empty state for the code-tier section, which was
      showing a heading over blank space in ON/QC (0 of 70,568 ON evaluations
      carry a tier). See [docs/NEWHOMES.md](docs/NEWHOMES.md).
- [x] Retrofit Explorer: new aggregate "Where the heat escapes" chart, the
      per-FSA/province twin of the per-home heat-loss breakdown.
- [x] **Pairing Gate A recovered — matched sample 1,369,305 → 1,451,433
      (+82,128, +6.0%).** `build_pairs_index()` now reduces each home to
      oldest-D + newest-E instead of requiring exactly one of each. The pair
      stage gained the predicted +148,155; the structural/floor-area gates then
      removed proportionally more of the recovered multi-audit homes (they span
      longer gaps), netting +82,128. Matched share of homes with both a D and an
      E audit rises 84.0% → 89.1%. Headline figures barely move — median saving
      stays 20%, whole-home heat loss −12% — which is the evidence the recovered
      homes are representative rather than a distortion. Full chain rerun and all
      JSON regenerated. Previous build artifacts backed up at `C:\ERS\web_prev\`.
- [ ] **Gate B — still open, and the ordering argument favours changing it.**
      84,755 pairs are dropped for "E not dated after D". None have unparseable
      dates and 99.4% are exact same-day ties; `ENTRYDATE` is month-precision
      throughout (all first-of-month). Since `EVALTYPE` already says which audit
      is the initial and which the follow-up, **the date test is only a guard
      against genuine reversals** — so `E > D` → `E >= D` would be correct and
      recovers ~84,253, leaving the 502 real reversals excluded. Not applied:
      surfaced as an open question on the page for the EnerGuide team to confirm
      first. (An earlier framing in this session — that same-day ties carry "no
      recoverable ordering" — was wrong; ordering comes from `EVALTYPE`, not the
      date.)

**Small loose ends (fold into any session):**

- [x] ~~`Geothermal/scripts/build_building_demand.py` parquet-metadata clobbering
      bug~~ — fixed 2026-07-24. Both phase writers now call the shared
      `Geothermal/scripts/parquet_meta.py:write_with_meta()`, which carries
      every `heatdemand_*` note across a rewrite. **Phase 4 must use it too.**
- [ ] Watch first scheduled run: rates **2026-08-03**. (Construction's first run
      went green 2026-07-20; AHRI lookup is now a weekly automated refresh as of
      2026-07-22 — both resolved, no longer loose ends.)

---

## 7. Ottawa Case Study — heat demand, electrification, grid (in progress)

The end product is the **Ottawa Case Study**: a six-step narrative (grid
constraints → ground resource → building heat loads → electrified share →
electrification peak vs grid → candidate areas), delivered as a case-study page
with the interactive geothermal map as the expert explorer. Full plan + prompts:
**[HEATDEMAND_PLAN.md](HEATDEMAND_PLAN.md)** (§0 narrative, §5 paste-able
prompts). Build log: [GEOTHERMAL_STATUS.md](GEOTHERMAL_STATUS.md).

| Phase | What | Status |
|---|---|---|
| 0 | Source scouting memo | ✅ 2026-07-16 |
| 1 | Canonical building stock (414k buildings, height/type/vintage) | ✅ 2026-07-16 |
| 2 | Per-building current heat load + fuel | ✅ 2026-07-16 |
| 2.5 | Stock reconciliation — implied dwellings 1.005× census, sums defensible over `in_ottawa_cd` | ✅ 2026-07-17 |
| 3 | Electrified load per building (validated 0.00% vs shipped engine) | ✅ 2026-07-17 |
| **4** | **Grid half:** ✅ 2026-07-31 — `heat_demand_grid.geojson`, 6,722/13,778 cells, validated exact against Phase 2.5/3's own totals; `build_suitability.py`'s demand upgrade hook now fires for real. **Feeder half: 🔓 unblocked 2026-08-03** — `Hydro.py` + `ottawa_capacity.geojson` recovered from the 2026-07-27 deploy snapshot (the only place the script had ever existed); `Hydro.py` now committed to `main` and `.gitignore` narrowed so it stays there. feeder_demand.geojson and the coincidence factor are still unstarted | 🔨 **feeder half next** |
| 5 | New map layers (demand, grid stress, intervention score) | 🆕 |
| 6 | The case-study page — the narrative deliverable | 🆕 |

Key Phase-3 findings that shape Phase 4 (details in GEOTHERMAL_STATUS.md):
the "average installed" ccASHP locks out at −15 °C so policy (a)'s design peak
is an equipment problem (Tier 1 halves it); the ~90% hybrid target is
unreachable with that curve (stalls at 81–84%); **the peak columns are
undiversified** — already-electric stock alone sums to 1,275 MW ≈ 98% of Hydro
Ottawa's system peak, so Phase 4 must derive a coincidence factor from real
feeder loading rather than quote raw sums. That derivation was blocked on the
missing `GridCapacity/Hydro.py`; both it and `ottawa_capacity.geojson` were
recovered 2026-08-03, so the feeder loading data is now in hand — see
GEOTHERMAL_STATUS.md's 2026-07-31 and 2026-08-03 entries.

---

## 💡 Project ideas (not committed — pick when the queue clears)

1. **EWRB Large-Buildings Explorer.** Ontario's Energy & Water Reporting
   Benchmark publishes *actual reported* energy + floor area + property type for
   every building ≥ 50k ft². Already identified as a heat-demand input
   (HEATDEMAND_PLAN §3.2); a standalone benchmarking page ("how does this
   office/MURB compare to its peers?") would be the suite's first
   *measured-data* tool and reuses the whole design system.
2. **Solar PV layer / explorer.** The ERS data already tracks PV adoption
   (retrofits.html measure flag); NRCan publishes municipal photovoltaic
   potential. Per-FSA adoption vs potential = "who's leaving sun on the table" —
   a natural sibling of the Retrofit Insights choropleths.
3. **Case-study template → second city.** Once Ottawa Case Study Phase 6 ships,
   the pipeline (footprints → stock → load → electrified peak vs feeders) is
   reusable wherever a utility publishes feeder capacity maps (several ON LDCs
   do under the same OEB CCIM mandate). A second city would prove the method
   generalizes.
4. **Bill comparator standalone.** The rates layer (`prices_json/` +
   `utility_rates_reference.json`) + heat pump engine could back a simple
   "what would switching cost *me*" page — narrower and more shareable than the
   full Heat Pump Explorer.
5. **EV charging load layer.** Same grid-stress framing as the case study's
   Phase 4: per-feeder added MW from EV adoption scenarios. Complements the
   heat-pump electrification story on the same GridCapacity polygons.

---

## ✅ Completed items (full record in [docs/archive/ROADMAP_COMPLETED.md](docs/archive/ROADMAP_COMPLETED.md))

| # | Item | Done |
|---|---|---|
| 1 | Ship the Geothermal map | 2026-07-10 |
| 2 | Repo housekeeping — AHRI legacy files | 2026-07-12 |
| 3 | Heat Pump tool, all 7 phases | 2026-07-10 |
| 4 | Energy prices layer, all 3 phases | 2026-07-12 |
| 8 | Geothermal v2 (4 phases) | 2026-07-15 |
| 9 | Heat Pump v2 (6 workstreams) | 2026-07-17 |
| 10 | Retrofit Explorer post-launch additions | 2026-07-17 |
| 11 | Retrofit audit funnel + pairing-filter fix | 2026-07-18 |
| 12 | Retrofit EnerGuide-demo visual polish | 2026-07-18 |
| 13 | Retrofit Insights — national "big picture" page | 2026-07-19 |
| 6 | Live grid dashboard — ETL + page (`grid.html`) | 2026-07-12 (ETL) / 2026-07-24 (page) |
| 5 | Landing page hub (`index.html`) | 2026-07-24 |
| — | New Homes Explorer (built outside the roadmap) | 2026-07-15 |
| 14 | Heat Pump — methodology-audit fixes (upstream-oil, fuel constants, default basis) | 2026-08-19 |

---

## Session hygiene

- Each prompt is self-contained; run in a fresh session, in order within an item.
- After each session: update the project's STATUS/METHODOLOGY file, flip the
  status board here, and commit.
- Opus for methodology-heavy or design-heavy work (silent-error risk); Sonnet
  for data plumbing with clear validation criteria.
- When an item completes: move its full text to
  [docs/archive/ROADMAP_COMPLETED.md](docs/archive/ROADMAP_COMPLETED.md) and
  keep one line in the Completed table.
