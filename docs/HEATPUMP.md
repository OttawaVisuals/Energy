# Heat Pump Explorer

**Live:** [/heatpump](https://ottawavisuals.github.io/Energy/heatpump) ·
**Page:** [heatpump.html](../heatpump.html) ·
**Method:** [HeatPump/METHODOLOGY.md](../HeatPump/METHODOLOGY.md)

## What it is

An hour-by-hour simulation of switching a Canadian home from its existing
heating system to an air-source heat pump. Pick a city, a design heat load, a
performance tier and capacity, and a backup arrangement; the tool runs 8,760
hours of a typical year in the browser and reports energy, emissions, operating
cost and how much of the winter the heat pump can actually carry.

It covers **14 cities** across seven provinces, and it is a **screening tool** —
good for direction and rough magnitude, not a substitute for a heat-loss
assessment or a contractor's quote.

## Who it is for

**Homeowners and associations** get plain-language answers to the questions that
actually decide a retrofit: will it cut emissions here, what happens on the
coldest nights, and what does it do to the bill.

**Practitioners** — NRCan, EnerGuide and HOT2000 users, energy engineers — get
the derivation behind every number: field names, published sources with
vintages, the formulas, the validation tables, and an explicit list of what is
assumed rather than measured.

Both audiences are served on the same page: a plain-language methodology section
and, behind it, the full technical expansion.

## What it is built from

| Input | Source |
|---|---|
| Hourly weather, typical and historical | ECCC CWEC2020, CWEEDS 2020, MSC Datamart |
| Design temperatures | ~24-year station record; NBC 2020 Table C-2 shown as reference |
| Home heat load | User-set design load; EnerGuide/ERS audits for the on-screen reference and the real-homes explorer |
| Heat pump performance | Nine AHRI-certified units, curves digitized from manufacturer datasheets |
| Grid emissions | IESO and AESO hourly generation; TAF's NIR-derived gas intensity; StatCan/ECCC inventory averages |
| Lifecycle terms | TAF *Fugitive Methane*; IPCC AR6 refrigerant GWPs; manufacturer charge-mass data |
| Operating cost | Published residential tariffs; StatCan heating-oil prices |

Full derivations, assumptions and validation:
[HeatPump/METHODOLOGY.md](../HeatPump/METHODOLOGY.md).

## How it is put together

The repo-wide pattern: an offline Python pipeline writes compact JSON, and one
self-contained HTML page reads it. No backend, no build step, no runtime
dependencies.

```
HeatPump/pipeline/*.py   →   HeatPump/data/processed/*.json   →   heatpump.html
```

`HeatPump/app/engine.js` holds the simulation itself as a single dependency-free
function, mirrored in Python for testing so the browser and the test harness
cannot drift apart. Pipeline order and the commands to regenerate everything are
in METHODOLOGY.md §11.

**Shared with the grid dashboard.** `HeatPump/pipeline/grid_common.py` carries
the fetch, parse and emission-factor logic used by both this tool and
[grid.html](../grid.html). Changing an emission factor there changes both, and
both data trees need regenerating.

## Related

- [grid.html](../grid.html) — what's powering the grid right now, same grid data
- [retrofits.html](../retrofits.html) — EnerGuide retrofit outcomes, same ERS source
- [ROADMAP.md](../ROADMAP.md) — current work and the decision record
