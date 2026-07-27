# Datasheet inventory — the 36 representatives (Phase 3c)

**Snapshot 2026-07-26.** Working record of the hand-fetch sweep: which
manufacturer performance data was found for each bucket representative, what
shape it was in, whether a curve was built, and what is outstanding.

Raw PDFs are kept in `data/raw/spec_sheets/` (gitignored — local only).
Re-triage any time with `python pipeline/probe_datasheets.py`.

---

## 1. Curves built — 7 of 36

`data/processed/hp_unit_curves.json`, from `data/interim/datasheet_points_v2.json`.

| AHRI | Brand / model | Pts | Range °C | cap@−15 | COP@−15 | Lockout | Ratio¹ | Review |
|---|---|---:|---|---:|---:|---:|---:|---|
| 211644151 | GREE GUD36W/A-D(U) | 23 | −30 → +24 | 0.833 | 1.83 | −30 | 1.06 | ok |
| 206249117 | GREE GUD36W/A-D(U) | 23 | −30 → +24 | 0.857 | 1.83 | −30 | 1.09 | ok |
| 206249116 | GREE GUD36W/A-D(U) | 23 | −30 → +24 | 1.250 | 1.83 | −30 | **1.58** | ⚠️ likely wrong combination — cert is 24,000 Btu/h, table is 36,000 |
| 207706562 | MOOVAIR DMA48HOS20230E7 | 15 | −30 → +14 | 0.941 | 1.94 | −30 | 1.25 | ok |
| 207706561 | MOOVAIR DMA36HOS20230E7 | 15 | −30 → +14 | 0.972 | 1.82 | −30 | **1.43** | ⚠️ verify combination |
| 204825178 | LG LAU120HYV3 | 19 | −24.4 → +24 | 0.989 | 2.90 | −25 | **1.63** | ⚠️ probably genuine LG boost range |
| 204825179 | LG LAU150HYV3 | 19 | −24.4 → +24 | 1.042 | 2.54 | −25 | **1.40** | ⚠️ probably genuine LG boost range |

¹ datasheet 47 °F max ÷ certificate rated 47 °F. >1.35 is flagged, not rejected —
it has two causes that cannot be separated automatically (wrong certified
combination vs. a genuinely wide inverter boost range). **These four need a human
call.** See TIER_SPEC.md §5.

**Verified:** LG curves cross-checked against the manual's own published
maximum-heating figures (LAU120HYV3 = 13,600 Btu/h at 5 °F, LAU150HYV3 = 18,950)
after a caption-ordering bug initially returned the next model's table. GREE COP
column cross-checked against capacity ÷ (3.412 × power) on all 23 points.

---

## 2. Documents found but not usable as curves

| File | Model(s) | Verdict | Why |
|---|---|---|---|
| `GREE_FLEXX_extended_ratings.pdf` | FLEXX24/36/48/60HP | **FULL, 92 pts** | Data is excellent but these are **US model codes**; mapping to the Canadian GUD##W2 numbering is unconfirmed. **Best single lead outstanding.** |
| `GREE_GUD48W2.pdf` | GUD48W2/D-D(U) | SPARSE | rated 47/17 only |
| `GREE_GWHD24ND3MO.pdf` | GWHD(24)ND3MO | SPARSE | rated only |
| `GREE_GWHD30ND3MO.pdf` | GWHD(30)ND3MO | SPARSE | rated only |
| `GREE_GWHD42ND3MO.pdf` | GWHD(42)ND3**MO** | SPARSE | ⚠️ **wrong series** — our unit is GWHD(42)ND3**JO** (Free Match Extreme J) |
| `TOSOT_TUD36.pdf` | TUD36W2/D-D(U) | SPARSE | rated only — but prints **AHRI 211078855** (ours) and lockout −15 °C |
| `TOSOT_APEX_2-3ton.pdf` | TU36-24WADU etc. | SPARSE | brochure |
| `LG_ArtCoolPremier_HYV3_engmanual.pdf` | LAU120/150HYV3 | **used** | source of the two LG curves (probe says SPARSE — its tables need the LG parser) |
| `LG_MultiF_engmanual.pdf` | LMU-series | SPARSE in probe | 101 pp; covers LMU18/24/30/36CHV — **not** LMU363HV. Wrong manual. |
| `FUJITSU_AOUH12KZAH1_designtech.pdf` | ASUH/AOUH KZAH1 | **has tables** | Design & Technical Manual p.20+ has TC/IP capacity tables by outdoor × indoor temp. **Parseable — needs the heating table for ASUH12KZAS.** |
| `FUJITSU_AOUH12KZAH1_spec.pdf` | AOUH12KZAH1 | SPARSE | rated points |
| `MITSUBISHI_PUMY-HP48_sub.pdf` | PUMY-HP48NKMU2 | SPARSE | rated only |
| `MITSUBISHI_PUMY_databook.pdf` | PUMY-(H)P series | SPARSE | 57 pp, no temp table in text layer; may be graphical |
| `RHEEM_RP15AZ_productdata.pdf` | RP15AZ series | SPARSE | 47 °F and 17 °F COP only |
| `LENNOX_ML14KP1_ehb.pdf` | ML14KP1 | SPARSE | engineering handbook, rated only |
| `TRANE_Resolute_brochure.pdf` | 4TXD20 | SPARSE | marketing brochure; product data not public |
| `MOOVAIR_M20_perf.pdf` | DMA18/24/30/36/48 | **MATRIX, used** | source of both MOOVAIR curves |
| `MOOVAIR_36k_sub.pdf`, `MOOVAIR_techspecs.pdf` | — | SPARSE | superseded by the perf chart |

---

## 3. Not yet fetched — 17 models

| AHRI | Brand / model | Note |
|---|---|---|
| 10570123 | LG LSU120HSV5 | submittal is rated-only; needs the **LG single-zone HSV5 engineering manual** |
| 208131890 | LG LMU363HV | needs the **Multi F MAX** manual (the one fetched covers LMU-CHV only) |
| 205788777 | LG LUU480HHV | commercial single-zone; try LG product data book |
| 208101910 | MDV MOD30-24HFN1-MW | Mits Air submittal found earlier cites **AHRI 211911381**, not ours — wrong certified combination |
| 212387098 | RHEEM RP15AZ30AJ2N | same series as the fetched RP15AZ product data → expect SPARSE |
| 211291741 | RHEEM RP15AZ36AJ2N | as above |
| 215746601 | LENNOX ML14KP1-048-230A** | EHB fetched, SPARSE |
| 208106642 | LENNOX MHB012S4S-1L | not searched |
| 213248972 | Mitsubishi PUMY-HP48NKMU2*** | both docs SPARSE; try the City Multi *service* manual |
| 214888802 | FUJITSU AOUH12KZAH1 | D&TM has the table — **closest to done of the outstanding set** |
| 215218828 | GOODMAN GLZS4BA3010A* | no public spec PDF located; retailer data only |
| 215471366 | MIDEA MO1BS-H12B-1A | not searched |
| 212396764 | TRANE 4TXD2060A10NU** | brochure only; Trane product data is dealer-gated |
| 202557963 | GREE GWHD(42)ND3JO | **J series** — different from the ND3MO sheet fetched |
| 214931588 | GREE GWHD(30)ND6MO | ND6MO variant not fetched |
| 206335358 | GREE GMV-60WL/C-T(U) | VRF-class, not searched |
| 210421036 | GREE GUD48W2/D-D(U) | fetched, SPARSE |
| 207657395 | KERR A-KMH12SV-1 | niche Canadian brand |
| 207036468 | HAXXAIR HVHD-36E2D2 | niche |
| 212916824 | Bladex BX24-HP15ECO | niche |
| 207641274 | NOVAIR LEA27MZ-3P-25SK-O | niche |
| 213265553 | Gridless O-AYD12SD-1 | niche |
| 217115269 | Gridless GRID48OC | niche |
| 211078853 | TOSOT TUD24W2/D-D(U) | expect same format as TUD36 (SPARSE) |
| 211078855 | TOSOT TUD36W2/D-D(U) | fetched, SPARSE |
| 10062019 | TOSOT TW12HQ3D6DO | submittal listed on tosot.com/resources, not yet retrieved |

---

## 4. What the sweep established about formats

Four distinct layouts, each needing its own parser. **A document that looks
empty to a keyword search usually is not** — every parser here was written after
a first pass wrongly concluded the data was absent.

| Layout | Publisher | Parser |
|---|---|---|
| **ROW** — one line per outdoor temp, `<T>F <Btu/h> <COP> <W>` | GREE | `extract_datasheet_tables.py` |
| **MATRIX** — temps as columns, TC/Input rows | Midea platform (MOOVAIR/Master, MDV) | `extract_matrix_datasheet.py` |
| **LG** — outdoor temp rows × indoor temp column groups, TC/PI pairs; caption **follows** its table | LG engineering manuals | `extract_lg_tables.py` |
| **FUJITSU** — as LG but TC/IP with a separate cooling SHC column | Fujitsu Design & Technical Manuals | *not yet written* |

**Brand-level pattern:** GREE, Midea-platform and LG publish full
capacity-and-power tables. Rheem, Lennox, Trane, Mitsubishi and Goodman publish
rated points only in anything public — for those, NEEP is the realistic fallback.
Niche Canadian rebadge brands (KERR, HAXXAIR, Bladex, Gridless, NOVAIR) are
untested and least likely to publish.

---

## 5. Suggested next actions

1. **Resolve the 4 review flags** — decide per unit whether the ratio is a wrong
   combination or a real boost range. 206249116 is near-certainly wrong.
2. **Write the Fujitsu parser** — the D&TM table is already in hand.
3. **Settle the GREE FLEXX US↔CA model mapping** — one answer unlocks 92 verified
   points across several GREE units.
4. **Find the right LG manuals** for LSU120HSV5, LMU363HV, LUU480HHV.
5. **Concede the rated-only brands to NEEP** rather than hunting further.
