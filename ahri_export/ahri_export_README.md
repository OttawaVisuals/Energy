# AHRI heat-pump records in the EnerGuide Rating System (ERS) database

Generated 2026-09-10 by `Python/ahri_export.py`.

Source: the NRCan EnerGuide Rating System audit corpus (`C:\ERS\*.csv`, 21 files
covering audit years 2003–2026), joined against the AHRI Directory of Certified
Product Performance.

The purpose of this extract is HVAC design analysis: **what heat pump was actually
selected, against what the house's design load and heating consumption were at that
same audit.**

---

## Files

| File | Rows | What it is |
|---|---|---|
| `ahri_by_year_<PT>.csv` | one per province/territory | Count of AHRI-bearing audit records by audit year × evaluation type, with the total-audits denominator |
| `ahri_detail_<PT>.csv` | one per province/territory | One row per audit record that names an AHRI certificate |
| `ahri_canada_directory.csv` | ~15.7k | One row per distinct AHRI number seen anywhere in Canada: national count, per-province counts, and the full certificate record |
| `ahri_column_availability.csv` | 40 | Per-audit-year fill rate of every source column, among AHRI-bearing rows |

Provinces present: AB, BC, MB, NB, NF, NS, NT, ON, PE, QC, SK, YK. (Nunavut has
audit records but none carrying an AHRI number.)

---

## Record universe

Every row of the raw corpus whose `AHRI` column matches `^\d{7,10}$` after stripping
a trailing `.0`. That gate was validated against a full-corpus scan: it cleanly
separates real certificate IDs from the `0` "no heat pump" placeholder (~1.2M rows)
and short junk entries (`12345`, `210`, `9250`, …).

**No records are dropped by any other filter.** In particular this is *not* the
pre/post-paired dataset behind the public Retrofit Explorer, which requires a home to
have both a pre- and a post-retrofit audit and loses roughly 30% of AHRI-bearing
records (and all of Yukon) as a result.

`EVALTYPE` distinguishes what kind of audit produced the row:

| Code | Meaning | For sizing analysis |
|---|---|---|
| `D` | Pre-retrofit audit | An **existing** heat pump found at the time of audit |
| `E` | Post-retrofit audit | The heat pump **installed** during the retrofit |
| `P` | New construction, plan | As-designed |
| `N` | New construction, as-built | As-built |

`E` dominates (roughly 85%). If you want "equipment chosen for this house", filter to
`E` and `N`. If you want "equipment already in the field", `D`.

**Audit year is taken from `ENTRYDATE`, not from the source filename** — a file named
`2024.csv` contains entries dated from 2003 to 2025. `ENTRYDATE` is month-precision
(`YYYY-MM-01`); the day is not meaningful.

---

## Detail file columns

### Identity

| Column | Notes |
|---|---|
| `HOUSEID` | Audit identifier. Not unique in this file — a home audited pre and post appears twice, once per `EVALTYPE`. Trailing `.0` float artifacts stripped. |
| `PT` | Province/territory |
| `FSA` | Forward sortation area (first 3 characters of the postal code) — the finest geography in the corpus |
| `EVALTYPE`, `ENTRYDATE`, `AuditYear` | See above |

### House

| Column | Unit | Notes |
|---|---|---|
| `TYPEOFHOUSE` | | Single Detached, Row house end/middle unit, Detached Duplex, Mobile Home, … |
| `FLOORAREA` | m² | Per NRCan's dictionary this is **volume ÷ 2.5**, not a measured floor area |
| `STOREYS`, `YEARBUILT`, `FNDTYPE` | | `FNDTYPE` is a semicolon-joined code list (e.g. `B1;B2`) |
| `NUMDWELLINGUNITS` | | Populated for MURBs only (~48% of the corpus). Blank does not mean 1. |
| `AIR50P` | ACH @ 50 Pa | Blower-door air leakage |

### Load and consumption

| Column | Unit | Notes |
|---|---|---|
| `EGHDESHTLOSS` | W | **Design heat loss — the peak load figure.** As recorded. See the caveat below. |
| `PeakLoad_kW` | kW | `EGHDESHTLOSS / 1000`, for convenience |
| `EGHFURNACEAEC` | MJ/yr | Annual energy consumption of the heating system |
| `HeatEnergy_kWh` | kWh/yr | `EGHFURNACEAEC × 0.27778` |
| `EGHFCONTOTAL` | MJ/yr | Whole-house total energy consumption, all end uses |
| `TotalEnergy_kWh` | kWh/yr | `EGHFCONTOTAL × 0.27778` |
| `HeatElectricity_kWh` … `HeatWood_kWh` | kWh/yr | HOT2000's own split of the heating total by fuel (`EGHHEATFCONS{E,G,O,P,W}`). Useful for checking whether a backup fuel is actually being consumed. |

These are **modelled** figures from HOT2000 under standard operating conditions, not
metered consumption. They are not billing data and will not match a utility bill.

### Heat pump as reported by the auditor

`AHRI`, `HPSOURCE`, `HPEquipType`, `HPCAP`, `CCASHP`, `CCASHPCAP`, `COP`, `CCASHPCOP`,
`CCASHPHSPF2`, `CCASHPSEER2`, `CCASHPCAPACITYMAINTENANCE`, `ASHPHSPF2`, `ASHPSEER2`,
`HPESTAR`, `AIRCONDTYPE`, `AIRCOP`.

Read the caveats section before using `HPCAP` or `COP`.

`HPSOURCE` (`Air` / `Ground` / `Water` / `N/A {no Heat Pump}`) is the clean heat-pump
presence flag. `CCASHP` has casing variants — `T`, `t`, `F`, `f` — normalise before
filtering.

### Backup heating

`FURNACETYPE`, `FURNACEFUEL`, `SUPPHTGTYPE1`, `SUPPHTGFUEL1`. See caveats.

### Certificate join (from the AHRI directory)

`Cert_Resolved`, `Cert_Brand`, `Cert_Model`, `Cert_IndoorModel`, `Cert_Cap47_btuh`,
`Cert_Cap17_btuh`, `Cert_Cap5_btuh`, `Cert_COP5`, `Cert_HSPF2`, `Cert_SEER2`,
`Cert_ColdClimate`, `Cert_Cap47_kW`, `Cert_Cap5_kW`.

`Cert_Resolved = No` means the AHRI number appears in the audit record but did not
resolve against the directory (517 of 15,666 observed codes — expired or withdrawn
certificates, or transcription errors). Those rows are **kept with blank certificate
fields, never dropped.** Occurrence-weighted certificate coverage is ~99.2%.

The full certificate record — including EER2, refrigerant, ENERGY STAR, AHRI type,
model status, split/packaged, phase, airflow — is in `ahri_canada_directory.csv`,
joinable on `AHRI` ↔ `AHRI_Number`.

### Sizing ratios

`SizingRatio_47F = Cert_Cap47_kW / PeakLoad_kW`
`SizingRatio_5F  = Cert_Cap5_kW  / PeakLoad_kW`

Certified heating capacity divided by the house's design heat loss. Blank where
design heat loss is zero, the certificate did not resolve, or the certificate
carries no rating at that temperature.

**`SizingRatio_5F` is available for a biased subset — read caveat 7 before using it.**
It is populated on 296,380 of the 439,976 certificate-resolved rows (67%), against
409,597 (93%) for `SizingRatio_47F`. The missing third is not random.

**A low ratio is usually not an undersized whole-home system.** Ductless mini-splits
installed as supplementary heat alongside retained electric baseboard or a fossil
furnace are extremely common in this dataset, and they correctly show ratios of
0.2–0.4. Segment by `HPEquipType` and by whether a backup fuel actually shows
consumption in the `Heat*_kWh` columns before drawing conclusions about sizing
practice.

---

## Caveats that matter

**1. `EGHDESHTLOSS` is gross of internal and solar gains.**
It is HOT2000's design heat loss at the ERS design temperature, with no credit for
internal or solar gains. That is the right basis for CSA F280-style equipment sizing,
which also excludes gains — but it is *not* the same quantity as a gains-inclusive
design load, and it runs materially higher. For scale, under ERS standard operating
conditions a reference house carries roughly 0.88 kW of constant internal gain and
around 1.05 kW of January solar gain (measured from a CanmetENERGY HTAP sample file).
Against a typical 10–12 kW design heat loss that is not a rounding error. The column
is shipped **as recorded**, with no adjustment applied.

**2. `HPCAP` should not be used as a capacity.**
Measured against AHRI certificates over 318,585 rows nationally, median `HPCAP` is
**1.6×** the certified heating capacity at 47 °F, values cluster near 1×, 2× and 4× of
the true value, and **63% of AHRI codes that appear more than once carry inconsistent
`HPCAP` values across rows for the same certified unit.** It may be intended as a
system total across multiple indoor heads, or it may be data-entry noise; NRCan has
not confirmed which. Use `Cert_Cap47_kW` / `Cert_Cap5_kW` instead.

**3. The generic `COP` column is rated at 47 °F, not 5 °F.**
This is the easiest serious mistake to make with this extract. Comparing `COP`
against `Cert_COP5` will make the field look systematically wrong; it is not — it is
a rating-condition mismatch. Established by cross-checking the corpus's most common
installed unit (AHRI 211644151) against NEEP's published performance table: NEEP
lists COP 3.00 at the 47 °F rated point and 1.80 at 5 °F, and the ERS `COP` median for
that exact unit is 2.99. AHRI's search API exposes no 47 °F COP field to validate
this across the whole dataset, so the finding rests on that single-unit NEEP
cross-check plus the population-level consistency it explains — solid, but not
independently confirmed by NRCan documentation.

**`CCASHPCOP` is the field that matches the certified 5 °F COP** almost exactly;
HOT2000 most likely auto-populates it from the AHRI number rather than taking it by
hand. Likewise `CCASHPCAP` (kW — note, *not* watts) matches the certified 47 °F
capacity at a median ratio of 1.000, and `CCASHPCAPACITYMAINTENANCE` (the 5 °F/47 °F
capacity ratio, %) has a median difference of 0.0 percentage points from the
certified equivalent across 210,243 rows, 85% within ±10 pp. All three are populated
only when `CCASHP` is true and only from 2021 onward, so they structurally exclude
non-cold-climate units and every earlier year.

**4. `FURNACETYPE` / `FURNACEFUEL` describe the backup, not the heat pump.**
HOT2000 models the heat pump as a separate component from the "primary" system, and
these fields never take a heat-pump value. For a heat-pump home they are the
companion or backup system. Treating `FURNACEFUEL` as "primary heating fuel" is
misleading for exactly the homes this extract is about.

**5. `SUPPHTGTYPE1` / `SUPPHTGFUEL1` is not the heat pump's backup either.**
It is a third-tier supplementary appliance, dominated by wood stoves and fireplaces.

**6. The certificate's 5 °F rating is missing in a way that correlates with the
answer you are looking for.**
AHRI does not publish a 5 °F heating rating on every certificate, and which
certificates carry one tracks the cold-climate designation almost perfectly:

| `cold_climate` on the certificate | Certificates | Share carrying a 5 °F rating |
|---|---|---|
| `Yes` | 2,733 | **100%** |
| `No` | 9,049 | 53% |
| blank (field absent from the record) | 3,367 | **0%** |

So filtering to rows where `SizingRatio_5F` exists quietly over-weights cold-climate
equipment, and any statement of the form "at 5 °F the average installed heat pump
covers X of design load" computed on that subset is a statement about cold-climate
units plus the better-documented half of the rest. `Cert_COP5` has the same shape
(68.5% of resolved rows).

`SizingRatio_47F` covers 93% of certificate-resolved rows with no comparable
selection effect, so it is the safer basis for a population-level claim — at the cost
of being the wrong temperature for a Canadian design day. Where a 5 °F conclusion
matters, state the subset it rests on. `Cert_Cap17_btuh` (93.6% coverage) is a useful
middle point that most certificates do carry.

**7. Field availability varies sharply by year.**
Every year's source CSV carries an identical 433-column header, so a missing value is
an unpopulated field, not an absent column. `ahri_column_availability.csv` gives the
per-year fill rate for every column in the detail file. Check it before building any
time series, or a field that simply was not being collected will read as a decline.

Three specifics that bite:

- **`HPEquipType` — the ductless-vs-central distinction — is effectively a 2025+
  field.** Fill runs about 1% for 2021–2023, 9.6% in 2024, then 83.7% in 2025 and
  97.9% in 2026. It is blank on 351,249 of the 443,415 rows. It is the single most
  useful column for interpreting a sizing ratio (median `SizingRatio_5F` is 0.41 for
  ductless mini-splits against 0.66 for central split systems), so segmenting by it
  means working almost entirely within the last two audit years.
- **`ASHPHSPF2` / `ASHPSEER2` are essentially never populated** — under 5% in every
  year. Use the certificate's `Cert_HSPF2` / `Cert_SEER2` instead.
- **`CCASHPCAP`, `CCASHPCOP` and `CCASHPCAPACITYMAINTENANCE` ramp in**: ~60% in 2021,
  ~79% in 2022, ~90% from 2023. `CCASHPHSPF2` / `CCASHPSEER2` are 2025+ only.

One reading note on that file: "populated" means non-blank **and not a bare zero**.
For the per-fuel heating columns (`EGHHEATFCONSG/O/P/W`) a zero is a true measurement
— the house does not burn that fuel — so their low percentages reflect a
predominantly electrically-heated population, not missing data.

---

## What this data cannot tell you

- **Whether the equipment was correctly sized.** There is no record of a CSA F280
  design calculation, no room-by-room load, no ductwork or distribution data, and no
  installer design intent. `SizingRatio_*` is capacity over modelled design heat
  loss — a screening indicator, not a design review.
- **Whether the system performed.** Every consumption figure is HOT2000-modelled
  under standard operating conditions. No metered or billing data exists in this
  corpus.
- **Whether the heat pump is the primary heating system.** The corpus does not state
  a control strategy or a switchover temperature. A large `SizingRatio` does not
  establish that the heat pump carries the house, and a small one does not establish
  that it does not.
- **Anything about homes that were never audited.** ERS participation is
  self-selected and program-driven; provincial totals track rebate programs, not the
  housing stock. Counts by year should not be read as market share.
- **Multi-unit buildings reliably.** `NUMDWELLINGUNITS` is populated for under half
  the corpus, and MURB records mix whole-building and per-unit conventions.

## What would change the answer

Access to the underlying HOT2000 `.h2k` files would supply the gains breakdown,
the room-by-room loads and the control/switchover settings that are all absent here —
which is what would turn a screening ratio into an actual sizing assessment.

---

## Provenance

- Audit data: NRCan EnerGuide Rating System, `C:\ERS\*.csv`.
- Certificate data: AHRI Directory of Certified Product Performance, retrieved by
  `Python/build_ahri_lookup_full.py` and kept current by `Python/refresh_ahri_lookup.py`
  (each entry carries a `_checked` date; AHRI does amend certificates after issue).
- Conversion factors: MJ → kWh at 0.27778; Btu/h → kW at 0.00029307107.
- Generating script: `ahri_export.py`, included alongside this README in this folder
  (canonical copy lives at `Python/ahri_export.py` in the Energy repository, which is
  version-controlled; this folder is a point-in-time export for sharing and is not
  itself tracked in git). Re-running it requires the raw ERS CSVs, which are local-only
  and not distributed with this export.
