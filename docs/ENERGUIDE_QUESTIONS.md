# Questions for the NRCan EnerGuide / HOT2000 team

Consolidated open questions arising from building public-facing tools on the
**EnerGuide Rating System open dataset**
(`0a7619fd-2ffe-44b5-9027-3dfcec0866fd`, open.canada.ca) and on HOT2000 outputs.

Maintained at [docs/ENERGUIDE_QUESTIONS.md](ENERGUIDE_QUESTIONS.md).
Last updated **2026-08-02**.

**Context.** We publish free, open-source tools presenting Canadian energy and
retrofit data to two audiences at once — homeowners and technical practitioners
(NRCan, EnerGuide/HOT2000 advisors, energy engineers). Every source, assumption
and calculation is stated on the page. Repo: <https://github.com/OttawaVisuals/Energy>.
Tools currently built on ERS data: Retrofit Explorer (1.45M matched pre/post
pairs), New Homes Explorer, Heat Pump Explorer.

**What we are asking for.** Mostly *confirmation* rather than new data — in
several places we have inferred a field's meaning from its behaviour and would
rather cite an authoritative answer than publish an inference. Where we do ask
for new fields, section 1 is the one that matters most.

---

## 1. Monthly HOT2000 outputs in the ERS extract — the blocking one

**Question:** could the ERS extract carry the four monthly HOT2000 energy-balance
fields, or could they be made available some other way?

| Field (HTAP naming) | What it is |
|---|---|
| `energy_loadGJ` | monthly conduction/envelope loss |
| `solar_gainsGJ` | monthly utilized solar gain |
| `internal_gainsGJ` | monthly utilized internal gain |
| `aux_energy_GJ` | monthly auxiliary heat required |

**Why.** We model hourly heating load to simulate heat-pump performance across
8,760 hours. CanmetENERGY's own HTAP
(<https://github.com/canmet-energy/htap>, LGPL-3.0, `inc/hourly.rb`) builds
hourly load shapes from exactly these four monthly fields — the "load fitting
technique" referenced in *Cold-Climate Air Source Heat Pumps*
(Cat. M154-149/2022E-PDF) §3.2. The public ERS extract carries annual figures
and `EGHDESHTLOSS` only, so we cannot run that method on real homes.

**What we did instead.** We abandoned ERS-derived archetypes and rebuilt on the
four published archetypes in that report's Table 1. That works, but it costs us
the population sample (1.45M audited homes → 4 houses), floor areas, the
townhouse/row archetype, and any ability to show that local construction
practice differs between cities — which the ERS medians showed clearly
(Edmonton's audited stock is measurably better built per m² than Toronto's).

**Minimum viable alternative.** If monthly fields are impractical, the single
number that would unblock us is the **standard-operating-conditions solar gain
per city (or per weather station)**. It is the only house- and climate-specific
term we cannot derive. We already have UA (from `EGHDESHTLOSS` ÷ station design
temperature), the SOC setpoint schedule, and the SOC internal-gains constant —
all verified against a real `.h2k` file.

---

## 2. Design temperatures and the HOT2000 weather library

`EGHDESHTLOSS` is computed at the design temperature of the home's own weather
station, from HOT2000's weather library. `WEATHERLOC` and `WTHDATA` identify
both, but neither appears in the published extract — we recovered them by
scanning the raw year files.

1. **Is there a published station → design-temperature table per weather library
   version?** We joined `WEATHERLOC` to NBC Appendix C by station *name*, which
   is exact for only ~53% of homes; the rest go through alias/prefix/proximity
   matches. Our two highest-volume stations are both approximate:
   `TORONTO MET RES STN` (455k evaluations) and `TORONTO` (377k), and they
   differ by 3.5 °C.
2. **Which percentile is it — 1% or 2.5% January dry-bulb?** Value-matching
   against published NBC figures suggests 2.5%, but we would rather cite than
   infer.
3. **Which NBC edition backs each library version?** Across our universe:
   `WTH100` 56.3%, `Wth2020` 35.4%, `Wth110` 8.0%. We currently apply one
   NBC-2020-vintage value to all three, which we estimate costs ~2–3% on peak
   load. Is that estimate reasonable?
4. **Could `WEATHERLOC` and `WTHDATA` be added to the published extract?** They
   are present in the raw files, and without them the design basis of
   `EGHDESHTLOSS` is not recoverable by a downstream user.

---

## 3. `EGHDESHTLOSS` semantics

We have inferred the following and would like confirmation:

1. It is in **watts**, and is a **gross** design heat loss — envelope +
   infiltration at design conditions with **no credit for internal or solar
   gains**. (Evidenced by `designHeatLossRate` sitting in `<Other>` in the h2k
   XML, entirely outside the monthly gains balance.)
2. The indoor basis is the **21 °C main-floor heating setpoint**. How is the
   **19 °C basement** setpoint handled in the design-heat-loss figure —
   is the whole house computed at 21 °C, or is the basement at 19 °C?
3. Does it include **ventilation** load, or conduction + infiltration only?
4. Is any **night setback** credited? (We assume not, consistent with CSA F280.)

---

## 4. Standard operating conditions — is there a citable published source?

We needed the SOC internal-gain and setpoint values. The **HOT2000 User Guide
v15.8 §7.12** only says *"Do not change any values/selections in the Base Loads,
Water Usage or Electrical Use screens"*, and none of the guide's 22 Technical
Procedures cross-references covers them (all 22 concern envelope or mechanical
data collection). We ultimately read them out of a CanmetENERGY `.h2k` file:

- setpoints 21 °C day / 18 °C night for 8 h / basement 19 °C,
  `basementFractionOfInternalGains = 0.15`
- occupancy 2 adults + 1 child, each `atHome = 50%`
- interior electrical base load 18.6 kWh/day (appliances 6.2997 + lighting 2.6 +
  other 9.7), exterior 0.9 excluded
- utilized internal gains ≈ **0.88 kW, near-constant** across heating months

**Question:** is there a published document stating these, that we can cite
instead of a `.h2k` file? If not, would NRCan consider publishing the SOC
constants as a short reference table? They are program defaults, so they are
effectively a public modelling assumption behind every EnerGuide rating.

---

## 5. Field semantics we inferred from behaviour

Each of these we worked out empirically and would like confirmed or corrected.

### 5.1 `EGHFURNACEAEC` — primary system only?
We read it as annual fuel/electricity input to the **primary** space-heating
system, excluding supplementary heating, and convert to delivered heat with
`EGHFURSEASEFF`. Correct? Where a home has a significant wood stove or basement
baseboards, is that load absent from this field?

### 5.2 Heat-pump capacity fields
- **`HPCAP` (W) appears unreliable for sizing.** Validated against AHRI
  certificates, median `HPCAP` = **1.55×** the certified heating capacity at
  47 °F, and the *same* AHRI number yields 1×/2×/4× values. Is it intended as a
  system total across multiple indoor heads, or is this data-entry noise?
- **`CCASHPCAP` (kW) matches AHRI certificates almost exactly** (median ratio
  1.000) but is populated only when `CCASHP` is true and only for 2021+. Is
  there any path to equivalent capacity data for non-cold-climate units or
  earlier years?
- **`FURNACETYPE` / `FURNACEFUEL`** never take a heat-pump value; for a
  heat-pump home they describe the companion/backup system. Is that intended?
  It makes "primary heating fuel" misleading for heat-pump homes.
- **`SUPPHTGTYPE1` / `SUPPHTGFUEL1`** is not the heat-pump backup — it is
  dominated by wood stoves and fireplaces. Confirm it is a third-tier
  supplementary appliance rather than the heat pump's backup?

### 5.3 `ERSRating == 0`
We treat `0` as a **missing-value placeholder** meaning "not rated on the GJ/yr
scale" (the file was rated on the older EnerGuide 0–100 scale): 96.3% of such
rows carry a real `EGHRating`, and the share falls from 100% of pre-2015 files
to ~0.5% from 2023 on. Taken at face value it reads as a net-zero house and
poisons medians. Confirm — and is there a documented sentinel convention?

### 5.4 `ERSGHG` — what emission factors does HOT2000 use, and at what granularity?

**Question:** is there published documentation of the emission-factor table
HOT2000 applies internally to compute `ERSGHG` — specifically, is electricity
priced at one factor per province/territory, or something more granular (a
utility service territory, a regional grid zone, a postal-code/FSA lookup)?
We could not find this stated in any public NRCan document (the HOT2000 User
Guide sections we can access, and the EnerGuide Rating System Technical
Procedures, do not cover it), so we do not know if `ERSGHG` is even intended
to be comparable at the province level, let alone finer.

**Why it matters.** `ERSGHG` is only populated for **50.5%** of matched
retrofit pairs (733,107 of 1,451,433) — see [RETROFITS.md](RETROFITS.md) — so
we are building a calculated fallback from each home's own fuel consumption
(already ~100% complete) times an emission factor, to reach full coverage.
Validated against the 50.5% of pairs that do have a reported `ERSGHG`:

- **Natural gas, oil, propane**: a factor derived from the ERS data itself
  (ratio of reported per-fuel GHG to reported per-fuel consumption) agrees with
  ECCC's published Output-Based Pricing System reference values to within
  0.1–3.5% — no material disagreement.
- **Wood**: ECCC's OBPS reference values have no residential wood-combustion
  factor at all (consistent with biogenic CO2 being excluded from official
  accounting). The ERS-implied ratio, by contrast, comes out to an implausible
  ~358 kg CO2e/kg — evidence that whatever `ERSWOODGHG` records for wood-heated
  homes does not correspond to a simple combustion-factor model. We are
  treating wood as 0 (biogenic-neutral), matching official convention.
- **Electricity**: this is where a real gap shows up, and only in specific
  provinces. Most agree with ECCC's published provincial consumption-intensity
  figures within about ±15%. **Alberta runs 18–29% higher** in the ERS data
  than ECCC's published figure, consistently across 2023–2026 audit years and
  at large sample sizes (42,000–50,000 homes/year) — not noise. Newfoundland
  and Labrador runs 27–49% higher, at smaller sample sizes (292–6,400/year).
  We checked whether this is FSA-level/regional variation within the province
  and found: for NL, no — the province's audited homes are almost entirely on
  the island, and the official province-wide figure is diluted by Labrador's
  near-zero-carbon Churchill Falls hydro, which the audited population barely
  represents; for AB, we can't test it at all, since fewer than 200 of 85,771
  Alberta homes are pure-electric-heated (nowhere near enough per FSA to
  measure), and Alberta's AESO grid is a single province-wide pool with no
  published zonal split (unlike Ontario, which does have one). So the
  Alberta gap remains unexplained by geography, and we suspect it traces back
  to whatever emission-factor vintage or methodology HOT2000 uses internally —
  which is exactly what this question is asking about.

---

## 6. Matched pre/post pairs — is there an intended pairing key?

We construct retrofit pairs by matching a D (pre) audit to an E (post) audit on
`HOUSEID`. Two issues:

1. **`ENTRYDATE` is month-precision** (every value is the first of a month), so
   a D and E entered in the same month tie and cannot be ordered by date. We
   order by `EVALTYPE` instead. Is there a finer-grained date, or a documented
   intended ordering?
2. **Multiple D and/or E records per `HOUSEID`** are common (re-audits). We take
   the oldest D and newest E. Is there a documented convention, or a field that
   groups records into an intended before/after episode?

For scale: of ~2.38M homes with any evaluation, ~1.63M have both a D and an E,
and our filters yield ~1.45M usable pairs. Getting the pairing rule right moved
that number by a factor of 2.5, so it materially changes published statistics.

---

## 7. NBC 9.36 tier data missing for Ontario and Quebec

In `newhomes_json`, NBC energy-tier fields are essentially empty for ON and QC
province-wide — **ON 0 of 70,568** homes and **QC 1 of 2,577** — while other
provinces are well populated (AB 16,638/67,181, BC 12,024/54,073). The same
extraction populates every other province, so we believe this is a genuine
source gap rather than our mis-mapping, presumably because both provinces
regulate under their own energy codes rather than NBC 9.36's tier ladder.

**Question:** is that the correct explanation? We currently show an empty-state
card explaining it, and would like to state the reason accurately.

---

## 8. Smaller items

1. **Record-level access.** The only access is whole per-year CSV downloads
   (~8.3 GB); the GraphQL `energuide_api` is self-host-your-own-Mongo, not a
   hosted endpoint. Is a hosted query endpoint planned? File-level incremental
   refresh works but is coarse.
2. **Update cadence** — we observe biannual. Is that the intended schedule?
3. **Redistribution.** We would like to confirm the licence terms for
   republishing derived aggregates and small extracts of the ERS data, and
   separately for the NBC Appendix C climatic design values.

---

## Where our current answers live

| Topic | Written up in |
|---|---|
| Design temperatures, station join, 84-city table | [HeatPump/METHODOLOGY.md](../HeatPump/METHODOLOGY.md) "City design temperatures from HOT2000 weather stations" |
| SOC gains and setpoints read from an `.h2k` | [HeatPump/METHODOLOGY.md](../HeatPump/METHODOLOGY.md) "HOT2000 standard operating conditions" |
| NRCan Table 1 archetypes (current approach) | [HeatPump/METHODOLOGY.md](../HeatPump/METHODOLOGY.md) "NRCan-published archetypes" |
| Balance-point / gains issue that started this | [HeatPump/METHODOLOGY.md](../HeatPump/METHODOLOGY.md) "Balance-point calibration" |
| Pairing gates and their measured impact | [docs/RETROFITS.md](RETROFITS.md) |
| New-construction slice, tier coverage | [docs/NEWHOMES.md](NEWHOMES.md) |
