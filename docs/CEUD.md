# CEUD Explorer

`ceud.html` — NRCan's **Comprehensive Energy Use Database** (the government's own
"how Canada uses energy" tables) turned into one browsable page: all 5 sectors
(residential, commercial/institutional, industrial, transportation, agriculture),
national + provincial, energy use / GHG / intensities / drivers, with
plain-language explainers.

**Live:** https://ottawavisuals.github.io/Energy/ceud

## Pipeline

```
Python/ceud_etl.py        # scrapes NRCan CEUD HTML tables (cached in
                          #   Python/ceud_cache/) -> ceud_json/ (one compact
                          #   JSON per sector x region)
```

- Original plan & build prompts: [archive/CEUD_PLAN.md](archive/CEUD_PLAN.md)
- Source quirks and table-numbering notes: `Python/ceud_source_notes.md`

CEUD is updated by NRCan roughly annually — refresh is manual (rerun the ETL
when a new data year appears; no scheduled workflow).
