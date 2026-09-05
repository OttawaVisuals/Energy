# Spec sheets — sources for the 9 live tier-cell curves

Tracked here (unlike the working `data/raw/spec_sheets/` cache, which is
gitignored/local-only) so the primary source for every point in
`hp_cell_curves.json` stays visible and reproducible on `main`. These are
manufacturer-published installer/submittal documents — added 2026-09-05.

| File | Brand / model(s) | Used for | AHRI cert(s) |
|---|---|---|---|
| `Altitude_Series_Spec_Sheet.pdf` | GE Appliances ASH112PRDWA/ASYW12PRDWB, ASH115PRDWA/ASYW15PRDWB | `low_<18k` (p.6, heat+cool), `mid_<18k` (p.8-9, heat+cool) | 202588311, 202588312 |
| `TOSOT_TUD24W2DDU_Specification_Sheet.pdf` | Tosot TUD24W2/D-D(U) | `low_18-30k` (p.4-5, heat+cool) | — |
| `TOSOT_TUD36.pdf` | Tosot TUD36W2/D-D(U) | `low_30-42k` (p.4, heat+cool) | — |
| `GREE_FLEXX_Ultra18_GUD36W-A-DU_submittal.pdf` | GREE GUD36W/A-D(U) | `mid_18-30k` + `mid_30-42k` heating (p.4 EXTENDED RATINGS) | 211644151, 206249116, 206249117 |
| `GREE_FLEXX_extended_ratings.pdf` | GREE FLEXX36HP230V1BH/AO | `mid_18-30k` + `mid_30-42k` cooling (p.4, 80F/67F column) | — |
| `FUJITSU_AOUG09-15LZAH1_designtech.pdf` | Fujitsu AOUG15LZAH1 / ASUG15LZAS (doc DR_AS117EF_03) | `high_<18k` heat+cool | 206597213 |
| `FUJITSU_AMUG24-48LMAS_designtech.pdf` | Fujitsu AOUG36LMAS1 / AMUG36LMAS (doc DR_AR048EF_13) | `high_30-42k` heat+cool | — |
| `MOOVAIR_M20_perf.pdf` | Moovair DMA24HOS20230E7 (badge-engineered Midea platform, also sold as Master FMA24HIAHUU230X7) | `high_18-30k` heat (matrix table, indoor 70F row) + cool (p.1, 80F/67F row) | 212361759 |

`mid_<18k` was swapped from LG LSU120HSV5 (w=4,182, 4-pt heating only, no
cooling) to GE ASH115PRDWA (w=868) on 2026-09-05 — see
`pipeline/build_cell_curves.py`'s `mid_<18k` entry for the full rationale.

Every extracted point, table location, and cross-check against the AHRI
certificate is recorded in `pipeline/build_cell_curves.py`'s `UNITS` dict
(`source`/`cool_source`/`flags` per cell) — this table is an index into that,
not a replacement for it.
