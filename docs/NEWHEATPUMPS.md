# New Heat Pumps (`newheatpumps.html`)

What is on the federal National Heat Pump Rebate eligible list, and how do those
products rate? Built and published 2026-11-10 (incremental `gh-pages` update: page + `newheatpumps_json/summary.json`).

## Data flow

```
NRCan SPL "Download all (CSV)" (HP_NHPR)      ENERGY STAR Socrata w7cv-9xjt (CSV export)
HeatPump/data/raw/nrcan/nhpr_eligible_products_2026-11-10.csv     HeatPump/data/raw/energystar/es_heat_pumps_2026-11-10.csv
                       \                         /
              HeatPump/pipeline/build_nhpr_eligible.py   (join on AHRI number)
                       |                         \
   HeatPump/data/interim/nhpr_eligible_joined.csv   newheatpumps_json/summary.json  -> newheatpumps.html
```

Raw files and both outputs are gitignored (`/HeatPump/data/**`, `/newheatpumps_json/`);
`deploy.sh` ships `newheatpumps_json`. The process is what is versioned.

## Sources and rights

- **Eligible list:** NRCan Searchable Product List. A list of product identifiers, not
  the engineered heat-pump calculator (whose EULA is restrictive, see
  `docs/HEATPUMP.md`). Simon's decision 2026-11-10: use freely, cite the source.
  The page shows no reuse terms, only an accuracy disclaimer.
- **Ratings:** ENERGY STAR Certified Air-Source Heat Pumps, open government data.
  The dataset page shows no licence; ENERGY STAR terms not yet read. Cite the source.
- **AHRI Directory: not used.** Its terms bar using public-site data in software or
  databases (bulk data is a paid licence) and it now serves its API behind a
  Cloudflare bot check (403). No AHRI data was scraped for this page. Existing
  `lookup/ahri_numbers.json` is untouched and frozen (see ROADMAP 2026-11-10).

## Numbers (2026-11-10)

- List: 179,620 rows, 178,954 distinct AHRI numbers; 163,692 ccASHP, 15,262 GSHP;
  112,413 Active, 66,541 Archived. No brand/group/status conflicts across rows.
- ENERGY STAR: 284,449 rows, 12 with blank AHRI number (excluded, counted).
- Match (air-source only): Active 92,815 of 97,151 (95.5%); Archived 12,099 of 66,541
  (18.2%); all 104,914 of 163,692 (64.1%). GSHP out of scope (air-source dataset).
- Active matched medians: 32,400 BTU/h at 47 °F, COP 1.96 at 5 °F, HSPF2 9.0.

## Charts (revised 2026-11-10)

Histogram buckets: capacity 3,000 BTU/h, COP 0.1, HSPF2 0.5, open-ended at both ends. Scatter:
COP at 5 °F vs capacity maintenance (`Heating Capacity at 5°F` ÷ `at 47°F`), one dot per
distinct (capacity at 47 °F, maintenance, COP, compressor type), sized by AHRI-number count;
screened like `HeatPump/METHODOLOGY.md` (maintenance > 1.30 or COP > 3.0 excluded and
counted). Data: `newheatpumps_json/summary.json` + `scatter.json`.

## Honesty rails

- **Lab-rated, not measured:** values are AHRI-certified ratings republished by ENERGY
  STAR. Earlier check (2026-07-26, `fetch_energystar.py`): 5 °F capacities agree within
  2% on 3,447 models present in both AHRI and ENERGY STAR.
- Unmatched list entries stay in counts with no rating; nothing is dropped silently.
- Counts are per **AHRI number** (a certified outdoor+indoor combination), not units
  sold. Rebadged brands each carry thousands of numbers (about 5,967 each for Airquest,
  Arcoaire, Comfortmaker, Day & Night, Heil, Keeprite), so the brand chart uses
  **distinct outdoor models** instead, and says so.
- The comparison line (all ENERGY STAR sold in Canada) includes non-cold-climate models.
- The "Include archived" view leans toward products ENERGY STAR still certifies.
- Whether archived products stay rebate-eligible is not stated on the program page.

## Limits

*What the data can't tell us:* sales, installed base, real-world efficiency, which
products households pick. *What we assumed:* ENERGY STAR's figures equal the AHRI
certificate (sampled, not verified for every row). *What would change the answer:* a
refreshed NRCan list (it changes as products are added or archived), or a rule that
excludes archived products.

## Open items

- Refresh both raw files and rerun `build_nhpr_eligible.py` when the NRCan list changes.
- Read ENERGY STAR data terms before publishing.
- Landing-page tile and art; OG image; `project-atlas.html` section (not done).
- Possible next views: filter by capacity band, ducted vs ductless, brand family
  grouping (needs a manufacturer map).
- The existing `Python/nhpr_ahri_pilot.py` cannot run (AHRI API closed); delete or keep.

Program facts (ECCC page dated 2026-11-05): $2,000 flat; up to $10,000 below median
income; retroactive from 2026-11-01; portal early 2027; closes March 2034; parameters
not final.
