# Cost of Peak

`costofpeak.html` — what one new kilowatt of winter peak costs in Ontario if every
added kW is met with new generation plus new wires and land, set against the IESO's
own plan. Built 2026-11-24. Local only until published.

## Question and rule

If heating electrifies, what does the added peak cost, and what does it cost per kWh
sold? Rule: **every added kW is met by new capacity** (sensitivity across plant
types). Not a forecast of anyone's bill.

## Pipeline

```
Python/costofpeak_etl.py   # -> costofpeak_json/costofpeak.json  (gitignored, regenerate)
Python/costofpeak_cache/   # input workbooks (gitignored); URLs in the script docstring
```

Inputs: five IESO/NREL workbooks plus `grid_json/grid_on_history.json`. PDF-sourced
tables (FortisBC, PG&E, Dunsky, GHG) are typed into the script with citations and the
date read (2026-11-24).

## Sources

| Piece | Source | Basis |
|---|---|---|
| Fleet today, winter effective capacity, peak demand | IESO 2026 APO Data Tables, Figs 2, 7, 8 | planning data |
| 2050 build-out by scenario | IESO Capacity Expansion module, Figs 1-3 | planning data |
| Plant costs (Ontario) | IESO `Levelized Cost and Components`, 2025 CAD per nameplate kW | planning data |
| Plant costs (US) | NREL ATB 2024 v4, Moderate cost case, R&D financial case, 2022 USD; CC BY 4.0 | literature |
| Wires and land | FortisBC Kelowna Electrification Case Study (2023-02-24), Tables 4-2, 4-3, 4-4 | utility estimate, preliminary |
| Other wires estimates | Elmallah et al. 2022 (PG&E); Dunsky for IESO 2022; Priyadarshan et al. 2024 | published studies |
| System cost, capacity cost | IESO `Elec Cost by Component`; Marginal Energy and Capacity Costs Table 1 | planning data |
| Lifecycle GHG | NREL 2021 fact sheet (medians); IPCC AR5 Annex III (min/median/max) | literature |
| Load factor | `grid_on_history.json`: mean / peak of IESO monthly demand, full years | measured |

## Calculations

- `CRF = r / (1 - (1+r)^-n)`. NREL annual per nameplate kW = `CAPEX x FX x CRF(r, 30) + FOM x FX`.
  IESO annual = its published levelized cost (embeds its own financing assumptions,
  and includes transmission to remote wind/hydro zones; its overnight figure does not).
- Winter-peak cost per kW = `plant cost per nameplate kW / winter share + wires and land per kW`.
  Winter share default = IESO winter effective 2026-27 / installed 2026, by fuel (editable).
- Fortis per added kW = `(upgrades + land) / (case peak - 472 MW)`; 472 MW is Kelowna's
  2040 winter peak with zero electrification. **Our arithmetic**: $5,335-7,138 (25%),
  $4,508-6,090 (50%), $2,685-3,575 (100%) per kW. Costs step at 550 and 950 MW.
- Peak cost per MWh = `annual $/kW-yr / (8.76 x load factor)`.
- Build-out estimate (ours) = new MW by 2050 x IESO overnight cost in the chosen year;
  capital only, undiscounted, constant 2025 CAD.

Measured: Ontario load factor (0.66-0.70, 2021-2025). Assumed: winter shares,
annualizing rate and life, the 35% heating-only load factor (illustrative).

## Limitations (what the data can't tell us / what we assumed / what would change it)

- **Can't tell us:** hourly load of electrified homes; real cold-climate heat pump
  performance; any Ontario-specific wires cost per kW (none found).
- **Assumed:** Kelowna's wires costs transfer (a capacity-short city, agricultural-land
  limits, prepared by a gas utility); winter shares from the existing fleet; the cost of
  *having* capacity only (no fuel or O&M).
- **Would change it:** hourly utility data, lab heat pump curves, an Ontario distribution
  cost per kW, a different marginal plant.
- IESO capacity-need seasons are mostly summer until 2042; heating loads the winter.
- Simple-cycle gas lifecycle GHG is not reported by NREL or IPCC. NREL battery value is per
  kWh delivered and excludes charging energy. Biomass sources disagree about 4x.
- FortisBC figures exclude BC Hydro system upgrades and Indigenous consultation.

## Licence

IESO content is under the IESO website Terms of Use (limited licence to use and
reproduce, copyright notice required; the page carries it in its footer and uses no
IESO marks). No open-data licence was found, so commercial reuse is not assumed.
NREL ATB is CC BY 4.0. Checked 2026-11-24 from ieso.ca/en/Terms-of-Use; not legal advice.

## Open items

- No page icon/OG card of its own; the index tile and favicon reuse Grid's artwork.
- Not yet published (deploy.sh lists it). Run the pipeline, then deploy.
- Add NREL-based sensitivity for more resource classes; add hourly data when partner data exists.
