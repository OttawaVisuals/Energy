# BDA Heat Pump Lifecycle Emissions Explorer — review and what we take from it

Reviewed **2026-07-28**.

Their tool: <https://buildingdecarbonization.ca/report/heat-pump-lifecycle-emissions-explorer/>
(Building Decarbonization Alliance; page last modified 2026-06-11.)

The linked page is a WordPress wrapper. The actual tool is an iframe at
`https://buildingdecarbonization.ca/wp-content/uploads/2026/06/hp-ghg-explorer.html`
— one self-contained ~3,800-line HTML file, no build step, no external runtime
dependency. Same architecture philosophy as ours; EN/FR bilingual; state
shareable by URL parameter.

---

## What their tool is

A **single-equation lifecycle GHG explorer**, not a heat-pump performance model.
It exists to answer one rhetorical question — stated in its own H1, *"Refrigerant
leaks do not erase the climate benefit of a heat pump"* — and every input is a
user-selected scalar. No weather, no hourly simulation, no capacity/load
matching, no dispatch.

The engine, in full:

```
HP    = (Load × coverage × 277.78 / COP + cooling_kWh) × EF_grid × 16 yr
        + charge_kg × leak_fraction × GWP_refrigerant
        + backup furnace share (fuel + upstream CH4)
Base  = (Load / AFUE) × EF_fuel × 16 yr
        + upstream CH4
        + counterfactual AC electricity + counterfactual AC refrigerant
```

Inputs: 3 provinces (QC/ON/AB), 3 baseline fuels, 4 refrigerants, 3 leak
scenarios, 3 seasonal COPs, GWP-20/100 toggle, methane 0 / 0.7 / 2 / 5 %, annual
load in GJ, and 3 named presets (`skeptic` / `central` / `best`).

### Their constants (as shipped)

| Quantity | Their value | Source they cite |
|---|---|---|
| Refrigerant GWP₁₀₀ / GWP₂₀ | R-410A 2256 / 4715 · R-454B 531 / 1854 · R-32 771 / 2690 · R-290 0.02 / 0.072 | IPCC **AR6** WG1 Ch. 7 Table 7.SM.7, blend-weighted from constituents |
| Refrigerant charge | R-410A 3.6 · R-454B 3.4 · R-32 2.3 · R-290 0.5 kg | per-refrigerant, not a single value |
| Lifetime leak | 50 % / 100 % / 150 % of charge | IPCC 2019 + EU F-gas · Eunomia 2014 (UK DECC) · CPUC 2022 (CARB-informed) |
| CH₄ GWP | 29.8 (100-yr) / 82.5 (20-yr), fossil | AR6 |
| Gas combustion | 49.9 kg CO₂/GJ @ 95 % AFUE | Canada Energy Efficiency Regulations 2016 s.259 |
| Heating oil | 73.6 kg CO₂/GJ @ 82 % AFUE | — |
| Grid EF, current | QC 2 · ON 65 · AB 335 g/kWh | ECCC **NIR 1990–2024 Annex 7**, 2024 generation intensity |
| Grid EF, forecast | QC 2 · ON 95 · AB 245 g/kWh | 16-yr average 2026–2041, **CER Canada's Energy Future 2026** Current Measures, calibrated to the NIR 2024 anchor |
| Equipment lifetime | 16 yr | — |
| Seasonal COP | full 2.0 / 2.5 / 3.0 · hybrid 2.8 / 3.2 / 3.6 | "derived from" Ferguson & Sager 2022 instantaneous COPs |
| AC counterfactual | charge = 0.70 × HP charge, 100 % lifetime leak, cooling 5 GJ @ COP 3.4 | — |

---

## Where they are better than us

**1. Refrigerants — their core subject, and it shows.**

- Their GWPs are **AR6, blend-weighted from constituent molecules**, with the
  arithmetic in a code comment (R-410A = 50 % R-32 + 50 % R-125 → 2256).
  **Ours are AR4/AR5-era** (`heatpump.html` refrigerant selector: R-410A 2088,
  R-32 675, R-454B 467, R-290 3) — and we are **internally inconsistent**: the
  engine test vector in METHODOLOGY.md § Validation uses **2256** for the same
  refrigerant the UI labels 2088.
- They carry a **per-refrigerant charge mass**. R-32 and R-290 systems genuinely
  hold less refrigerant; our single `charge_kg` scaled by nominal capacity is
  refrigerant-agnostic, so our R-290 option carries an R-410A-sized charge and
  overstates it.
- They model an **AC counterfactual**: if the household would have bought AC
  anyway, that AC's refrigerant *and* electricity belong to the baseline, not to
  the heat pump. **We have no equivalent.** It is a legitimate and sourced credit.
- Framing leak as a **lifetime fraction of charge** (50/100/150 %) with a named
  study per option is more legible than our annual-rate + amortized-EOL form,
  even though ours is mechanically finer.

**2. A forward-looking grid.** Their `current` vs `forecast` trajectory is a
16-year 2026–2041 average from CER Energy Future 2026 Current Measures, anchored
to NIR 2024 — ON rising 65 → 95 g/kWh (Pickering retirement, gas growth before
refurbishments land) then falling post-2035 under the Clean Electricity
Regulations; AB 335 → 245. Our METHODOLOGY.md § "Not yet done / limitations"
flags exactly this gap: *"it does not forecast future levels… Ontario's level is
actively rising, so a forward year could differ."* **They have closed it and we
have not**, and for a question posed over a 16-year lifetime it matters more than
hourly resolution does.

**3. The QC "systems-level displacement" framing.** On a near-zero grid the
direct saving from resistance → HP is negligible, which makes the tool look
pointless in Québec. They value the **freed kWh** against three anchors —
resistance electrification (0.189 kg CO₂/kWh gross), HP electrification at the
user's COP, BEV transport (0.924) — each reported **net of the freed kWh's own
grid cost**, so on coal-leaning grids the low anchor can legitimately go
negative. They pre-empt the double-counting objection by pointing at
Hydro-Québec's Action Plan 2035, which counts HP conversions as the mechanism
freeing kWh for transport and industry. Novel, and we have nothing like it.

**4. Bilingual EN/FR** with a complete I18N dictionary.

---

## Where we are substantially better

**1. Heat-pump physics.** Their entire performance model is **three seasonal COP
scalars per configuration**, self-described as *"derived values consistent with"*
Ferguson & Sager's instantaneous COPs *"integrated against Canadian climate
hour-counts"* — with the integration never shown. That is an assumption presented
as a calculation. We compute seasonal COP from 8,760 hourly TMY temperatures
against per-tier capacity(T)/COP(T) curves taken from primary datasheets, with
balance-point dispatch, backup switchover, lockout/derate modes, and 15 engine
self-test vectors mirrored byte-for-byte in Python. Our Ottawa Tier-1 seasonal
COP of **2.32 is derived**; their 2.5 is **chosen**.

**2. Hybrid coverage is circular in theirs.** Coverage (50/65/80 %) and hybrid
COP (2.8/3.2/3.6) are independent dropdowns, so a user can select 80 % coverage
at COP 3.6 — physically inconsistent, since more coverage means colder hours
means lower COP. Nothing in the tool prevents it. In ours the coverage falls out
of the dispatch and cannot contradict the COP.

**3. Grid EF resolution.** One flat annual AEF per province, three provinces.
Their coldest Ontario winter evening is priced at the same 65 g/kWh as a mild
August afternoon — which **systematically understates** heat-pump emissions,
because HP electricity is concentrated in exactly the hours our EF surface shows
at ~2× the annual mean (METHODOLOGY.md § "Why a surface, not temperature-only
binning": −18 °C ON winter 19h ≈ 194 g/kWh on the 2025 grid).

They address average-vs-marginal head-on and it is their strongest
methodological argument, worth recording in their own terms. They stay with AEF
because (a) over 16 years the relevant signal is the build margin, not the
dispatch margin; (b) their forecast trajectory already operationalizes a soft
long-run margin; (c) *"Asserting one MEF per province would publish a position
rather than a calculation."*

That third point is a fair shot at anyone shipping a single MEF. **It does not
defend a flat AEF against an hourly AEF surface**, which is what we have — our
hourly-average basis has none of the MEF-singularity problem and still captures
the winter-evening concentration. That is the gap in their reasoning and the
cleanest statement of our advantage.

**4. Load model.** Theirs is a geography-free GJ/yr slider (default 95 GJ). Ours
is now NRCan Table 1 + Figure 1: 4 archetypes with UA recovered **per city** from
the 16 published peaks against NBC Appendix C design temperatures (R² 0.90–0.93),
independently reproducing the Figure 1 intercepts within 0.5 °C. Note this is a
**shared source** — their COP curves and our load model both come from
CanmetENERGY's cold-climate ASHP work, so the two tools are closer in provenance
than the surface comparison suggests.

**5. No counterpart at all** on their side to our weather-year lens, sizing
sweep, operating-cost card, or 14-city scope.

---

## Numbers worth flagging

- **Their gas factor corroborates ours.** 49.9 kg CO₂/GJ × 0.0036 GJ/kWh =
  **179.6 g/kWh** vs our **181 g/kWh** (HHV). Independent agreement within 1 %.
- **But theirs looks like CO₂, not CO₂e.** The constant is labelled kg CO₂ and
  sourced to an *efficiency* regulation. If it excludes combustion CH₄/N₂O their
  gas baseline is marginally understated — which cuts *against* their own thesis,
  so it is conservative, but it is undocumented.
- **CH₄ GWP-100:** theirs 29.8 (AR6) vs ours 28 (AR5). Theirs is the newer
  figure; METHODOLOGY.md § "Methane global-warming potential" already records our
  edition mix as a known wart. GWP-20 is 82.5 in both tools.

---

## Candidate updates to our tool

Ranked by value per unit of effort. **None of these are done; none change the
load model**, which stays on the NRCan archetypes pending the EnerGuide/HOT2000
discussion (see ROADMAP § heating-load model rebuild and
[docs/ENERGUIDE_QUESTIONS.md](../docs/ENERGUIDE_QUESTIONS.md)).

1. **Update refrigerant GWPs to AR6 blend-weighted values** and resolve the
   2088-vs-2256 inconsistency between the UI selector and the engine test
   vector. Straight correctness fix, small.
2. **Add the AC counterfactual credit.** A legitimate credit we omit entirely;
   we already track charge and leak rate, so the marginal cost is low. Should be
   a user toggle, not a default, and labelled as a counterfactual assumption.
3. **Per-refrigerant charge factors**, so the R-290 and R-32 options stop
   carrying an R-410A charge.
4. **A forward grid trajectory** from CER Energy Future 2026 Current Measures.
   This is the one place they have a real methodological lead over us, and it
   bears directly on a claim made over a 16-year horizon. Largest of the four;
   needs its own sourcing pass and must sit alongside — not replace — the
   existing three EF bases.
5. **Consider the freed-kWh displacement framing** for QC/BC/MB, with
   attribution to BDA. Solves a presentation problem we have not solved. Bigger
   conceptual commitment than the rest; not obviously in scope.

**Not to copy:**

- **Their scalar-COP approach.** It is the weakest link in their tool and the
  strongest in ours.
- **Their preset names.** `skeptic` / `central` / `best` is advocacy framing.
  Per CLAUDE.md's two-audience requirement, a skeptical NRCan reader will read it
  as such, and our defensibility rests on not doing that.

---

## Limitations of this review

Read from their **shipped engine only** — the constants, the calculation, and the
in-page methodology text. Where they say a value is "derived from" a source we
can see the endpoint but not the derivation (most consequentially the seasonal
COPs). The same criticism would apply to us in reverse, and it is the reason our
own derived quantities carry a pipeline script and a validation table.

We have **not** contacted BDA, and nothing here has been checked against a
backing report if one exists.
