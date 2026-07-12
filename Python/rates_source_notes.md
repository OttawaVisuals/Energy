# Energy-price source notes — `MaxPr1me/canada-utility-rates`

*Phase 0 scouting report (ROADMAP.md item 4), 2026-07-12. Investigated via a
shallow clone of <https://github.com/MaxPr1me/canada-utility-rates> (README,
`schema/create_tables.sql`, `pipeline/export_json.py`, `site/data/` exports,
workflows).*

## 1. What the exports are and where they live

The project scrapes official utility rate pages into SQLite, then
`pipeline/export_json.py` writes JSON to `site/data/`, which is **committed to
`main`** by the monthly workflow (`scrape.yml`, cron `0 8 1 * *` — 08:00 UTC on
the 1st of each month) and also deployed to GitHub Pages via `deploy.yml`.

**Stable raw URL pattern (verified 200, ~3.65 MB):**

```
https://raw.githubusercontent.com/MaxPr1me/canada-utility-rates/main/site/data/rates.json
```

Sibling files, same pattern: `utilities.json` (metadata), `summary.json`
(province rollups), `market_pricing_ontario.json` (IESO HOEP+GA, 576 hourly
bins — 12 months × 2 day types × 24 h; commercial Class B market pricing, not
needed for residential), `market_structure_notes.json`, `missing.json`.

The clone's exports were generated 2026-07-01 — i.e. the monthly automation is
alive and current.

## 2. Schema

`rates.json` is a flat **list of 504 tariff objects**, each with:

- Tariff-level fields: `utility_name`, `province`, `utility_type`
  (`electricity`|`gas`), `customer_class` (`residential`|`commercial`|…),
  `name`, `tariff_code`, `rate_structure` (`flat`|`tiered`|`tou`|`market`),
  `effective_date`, `end_date`, `source_url`, `confidence`
  (`high`|`medium`|`low`), `notes`.
- `components[]`: one row per charge line —
  `component_type` (`fixed`|`energy`|`commodity`|`distribution`|`delivery`|
  `transmission`|`regulatory`|`rider`|`carbon`|`demand`|`market`),
  `charge_value`, `charge_unit` (`$/kWh`, `$/month`, `$/day`, `$/GJ`, `$/m³`),
  `tier_number`/`tier_threshold`/`tier_unit` for tiered,
  `tou_period` (`on-peak`|`mid-peak`|`off-peak`|`ulo` …) + `tou_hours`
  (free text) for TOU, `season`, plus per-component `source_url`/`confidence`.

Multiple `effective_date` snapshots of a tariff can coexist (the site
deduplicates to the most recent) — the ETL must do the same: **keep only the
max `effective_date` per (utility, tariff name)**.

## 3. Coverage of our launch cities

All five launch cities are covered for the fuels that matter:

| City | Electricity (residential) | Natural gas (residential) |
|---|---|---|
| Ottawa | Hydro Ottawa Ltd. — TOU, Tiered, ULO (eff 2025-11-01, high conf, full stack: energy + distribution + transmission + regulatory + fixed) | Enbridge Gas Rate 1 (eff 2024-10-01, high conf) — but labelled *Union South* rate zone, see caveats |
| Toronto | Toronto Hydro — TOU, Tiered, ULO (same OEB structure) | Enbridge Gas Rate 1 (same file) |
| Montreal | Hydro-Québec Rate D (eff **2026-04-01**, high conf; 40 kWh/day tier + daily fixed) | Énergir Rate D1 (eff 2024-10-01, medium conf, $/GJ) |
| Calgary | ENMAX Power D110 distribution (high) + ENMAX Energy RRO energy (market, medium) | ATCO Gas South (medium, $/GJ) |
| Edmonton | EPCOR D100 distribution (high) + EPCOR Energy RRO (market, medium) | ATCO Gas North (medium, $/GJ) |

### Gaps / data-quality caveats found

1. **Carbon components are stale.** ON/QC/AB gas tariffs all carry a
   "Federal Carbon Charge" line (eff 2024-10-01), but the federal consumer
   fuel charge was set to zero on **2025-04-01**. The ETL must **exclude
   `component_type == "carbon"`** rows and document why. (QC's cap-and-trade
   cost is embedded in Énergir's commodity price anyway, never a separate
   federal line.)
2. **Alberta electricity is split across two tariff objects** (wires utility
   + RRO retailer) and is missing the **transmission volumetric charge and
   local-access fee** (distribution tariffs have only 2 components). AB
   marginal $/kWh will be understated by roughly 2–4 ¢/kWh; the RRO energy
   rate is also a monthly-varying number frozen at its 2024-10 scrape
   (16.84 ¢/kWh ENMAX). Treat AB as **screening-grade**, flag
   `confidence: "medium-low"` in our output, and lead with the *delta*
   between scenarios, not absolute bills.
3. **Enbridge rate zone**: only one residential gas tariff is exported for
   ON, labelled Union South. Ottawa/Toronto are in the (former EGD) zone whose
   delivery charge is somewhat higher. Acceptable for screening; caveat in
   `meta.json`.
4. **ON TOU calendar**: `tou_hours` is free text and reflects the winter
   arrangement only. The OEB TOU *prices* don't vary by season but the
   period *definitions* do (winter Nov–Apr: on-peak 7–11 & 17–19; summer
   May–Oct: on-peak 11–17; weekends/holidays off-peak). Our ETL hardcodes
   the OEB seasonal calendar and emits it in machine-usable form.
5. **Ontario Electricity Rebate** (a % credit on the whole pre-tax bill) is
   not in the exports. It scales both the baseline and heat-pump scenario
   equally, so deltas are only mildly affected; documented, not modelled.
6. **No heating oil or propane** anywhere in the repo (electricity + natural
   gas only) — see §5.

## 4. Tariff reduction — what our tools need

The heat pump engine is hourly, so TOU can be applied **exactly**; everything
else reduces to marginal volumetric rates + fixed charges:

- **Electricity**: `fixed_monthly` = Σ fixed charges ($/day × 365/12);
  `volumetric_adders` = Σ non-energy $/kWh lines (distribution + transmission
  + regulatory); energy price = flat, tier schedule, or TOU period schedule +
  calendar. Effective marginal $/kWh = energy(t) + adders.
- **Natural gas**: everything except the monthly fixed charge is volumetric —
  `marginal_cad_per_m3` = Σ (commodity + delivery + transportation + riders),
  excluding carbon (see caveat 1). $/GJ lines convert at **0.03798 GJ/m³**
  (10.55 kWh/m³ HHV — the same constant heatpump.html's engine uses;
  corrected from 0.03843 during Phase 1 to keep the ETL and its consumer in
  lockstep).
- **Heating oil**: $/L from the StatCan fallback (§5); the engine converts
  via 38.2 MJ/L × furnace efficiency.

### Proposed `prices_json/` shape (consumed by heatpump.html Phase 2)

One file per province (`prices_json/ON.json`, `QC.json`, `AB.json`) +
`meta.json`:

```jsonc
{
  "province": "ON",
  "generated": "2026-07-12",
  "electricity": {
    "ottawa": {                       // key = launch-city slug
      "utility": "Hydro Ottawa Ltd.",
      "effective_date": "2025-11-01",
      "confidence": "high",
      "source_url": "https://www.oeb.ca/…",
      "fixed_monthly_cad": 7.53,
      "volumetric_adders_cad_per_kwh": 0.0546,   // dist+trans+regulatory
      "plans": {
        "tou":    { "prices": {"on": 0.203, "mid": 0.157, "off": 0.098},
                    "calendar": { "winter_months": [11,12,1,2,3,4],
                                  "weekday_periods_winter": {"on": [7,8,9,10,17,18], "mid": [11,12,13,14,15,16], "off": "rest"},
                                  "weekday_periods_summer": {"on": [11,…,16], "mid": [7,…,10,17,18], "off": "rest"},
                                  "weekend_holiday": "off" } },
        "tiered": { "tiers": [{"limit_kwh_per_month": 600, "price": …},
                              {"limit_kwh_per_month": null, "price": …}],
                    "winter_tier1_kwh": 1000 },
        "ulo":    { "prices": …, "calendar": … }
      },
      "default_plan": "tou"
    }
  },
  "natural_gas": {
    "ottawa": { "utility": "Enbridge Gas", "fixed_monthly_cad": 28.44,
                "marginal_cad_per_m3": 0.2429, "effective_date": "2024-10-01",
                "confidence": "high", "carbon_excluded": true, "source_url": "…" }
  },
  "heating_oil": { "cad_per_litre": …, "ref_month": "2026-05",
                   "source": "StatCan 18-10-0001, household heating fuel, <city>" }
}
```

AB electricity appears as a single merged entry per city
(RRO energy + wires volumetric, fixed = admin fee + basic charge), flagged
`"confidence": "medium-low"`, `"notes": "transmission/local-access charges not
included; RRO varies monthly"`. QC keeps its 40 kWh/day tier as
`tiers_per_day` so the hourly engine can track a daily accumulator.

## 5. Heating-oil fallback (not in canada-utility-rates)

StatCan **table 18-10-0001** (monthly average retail prices for gasoline and
*household heating fuel*, by city, ¢/L) covers Ottawa–Gatineau, Toronto,
Montréal, Calgary and Edmonton (western cities are sometimes blank — fall back
to the province's available city, then to the national average, and record
which was used). Fetch via the same WDS `getDataFromVectorsAndLatestNPeriods`
pattern `construction_etl.py` already uses. Propane is out of scope: the heat
pump tool's fuel options are gas / oil / electric only.

## 6. Licensing / attribution

The upstream repo republishes publicly available utility rates with source
URLs and says it's for informational purposes. Our `meta.json` and the tool's
attribution line credit both the originating utility/regulator page (carried
through per-tariff `source_url`) and `MaxPr1me/canada-utility-rates` as the
aggregation layer, with each entry's `effective_date` shown in the UI.

## Phase-1 decisions this scouting locks in

1. Fetch `rates.json` (+ `utilities.json` for metadata) from the raw URL
   above; cache under `Python/rates_cache/`; `--refresh` re-downloads.
2. Reduce per §4; **drop carbon components**; dedupe to latest
   `effective_date`; convert $/GJ → $/m³ at 0.03843 GJ/m³; $/day → monthly
   × 365/12.
3. Emit `prices_json/{ON,QC,AB}.json` + `meta.json` per the shape above
   (only launch provinces; BC etc. can be added when a tool needs them).
4. StatCan 18-10-0001 for heating oil, WDS vector fetch, latest month.
5. Validation: reconstruct an Ottawa 1,000 kWh (TOU-weighted) + 200 m³ month
   and compare against Hydro Ottawa's and Enbridge's published bill examples
   (±10%); print QC/AB sanity bills too.
6. Monthly refresh workflow on the **3rd** of each month (upstream scrapes on
   the 1st; give it 2 days), no commit on fetch failure.
