# New Homes Explorer

`newhomes.html` — how energy-efficient Canada's **new** homes actually are, built
from the same NRCan EnerGuide/ERS open data as the Retrofit Explorer, but using
the **new-construction** evaluation types instead of the retrofit ones:

- **P ("Plan")** — the home *as designed*, evaluated from architectural plans
  before construction;
- **N ("As-built")** — the home *as built*, evaluated and blower-door tested
  after construction.

One row per finished, tested new home (N), with its matching plan record (P)
left-joined so as-designed vs as-built can be compared. Homes with a plan file
but no as-built record are excluded. New construction is small (~30k homes/yr,
~300k total), so the pipeline pairs everything in memory.

**Live:** https://ottawavisuals.github.io/Energy/newhomes

## Pipeline

```
Python/newhomes_pipeline.py     # ERS raw CSVs (C:\ERS\<year>.csv), filtered to
                                #   P/N -> per-province parquet
Python/newhomes_precompute.py   # parquet -> newhomes_json/ (province summaries)
                                #          + newhomes_fsa/ (per-FSA drill-down)
```

Same architecture as the Retrofit Explorer (see [RETROFITS.md](RETROFITS.md) for
the shared conventions: FSA handling, unit conversions, BASE_URL fetch pattern).
Data trees are fully separate: `newhomes_json/` + `newhomes_fsa/` vs the
retrofit `province_json/` + `fsa_json/`.

## Notes

- Tier / ACH / ERS-rating availability varies by audit year — the page states
  year coverage per metric.
- Refreshes with the same ERS CSV drops as the Retrofit Explorer (no separate
  download); rerun the two scripts above after `ers_web_pipeline.py`'s source
  files update.
