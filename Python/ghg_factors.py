"""
ghg_factors.py

GHG emission-factor constants and lookups shared by Python/compute_ghg_scenarios.py.
Not a standalone pipeline step — a constants/lookup module imported by that script.

Backs the 4 GHG scenarios on retrofits.html and retrofit-insights.html (see
docs/RETROFITS.md "GHG scenarios" and docs/ENERGUIDE_QUESTIONS.md §5.4):

  1. current            -- official OBPS factors, flat at the latest published
                           year (2026), same for every audit regardless of
                           when it happened.
  2. current_corrected   -- same, but Alberta and Newfoundland & Labrador use
                           the ERS-calibrated factor instead of the official
                           one (see WHY THE AB/NF CORRECTION below).
  3. as_audited          -- ERS-calibrated factor matched to each home's own
                           audit year, every province (no official source
                           covers years before 2023, so this scenario never
                           uses OBPS electricity at all).
  4. reported            -- raw ERSGHG, unchanged, wherever it exists (~50.5%
                           of matched pairs). Handled entirely in the parquet's
                           existing Pre_GHG/Post_GHG columns; this module does
                           not touch it.

Combustion (natural gas, oil, propane) is FIXED (official OBPS constants) for
scenarios 1/2 (current, current_corrected) but YEAR-VARYING ERS-calibrated
for scenario 3 (as_audited) -- see WHY SCENARIO 3 NEEDS YEAR-VARYING
COMBUSTION below. Wood is always 0 (biogenic-neutral) in every scenario --
see ErsCombustionFactors' class docstring.

WHY SCENARIO 3 NEEDS YEAR-VARYING COMBUSTION, NOT THE FIXED OFFICIAL
CONSTANTS (found 2026-08-02, building this module): the official gas/oil/
propane factors validate well against ERSGHG in aggregate and for RECENT
audit years, but Ontario's own `ERSNGASGHG` runs near-zero for 2006-2016
despite substantial real gas consumption in that era (n=54,967 in 2016
alone -- a large-sample, real data characteristic, not noise; see
docs/ENERGUIDE_QUESTIONS.md SS5.4). Applying today's flat official gas factor
(~185 g/kWh) to that population overstates historical gas GHG badly --
Ontario's scenario-3 aggregate bias against real ERSGHG went from -0.02%
(year-varying ERS-calibrated combustion) to +15.2% (flat official
combustion) once this was substituted in, confirming this is not
noise. Scenarios 1/2 are unaffected because they deliberately do NOT claim
historical accuracy -- they price every retrofit at today's rate on purpose,
to compare retrofits on equal footing regardless of when they happened.

SOURCE for OBPS_ELECTRICITY and OFFICIAL_COMBUSTION: ECCC, "Emission factors
and reference values" (Output-Based Pricing System / federal GHG offset
system), fetched 2026-08-02:
https://www.canada.ca/en/environment-climate-change/services/climate-change/
pricing-pollution-how-it-will-work/output-based-pricing-system/
federal-greenhouse-gas-offset-system/emission-factors-reference-values.html
Electricity: Table 5.1 (2023/2024), 5.2 (2025), 5.3 (2026), "Consumption
intensity", g CO2e/kWh electricity consumed.
Natural gas CO2: Table 1.1/1.2/1.3, "Marketable", g CO2/m3 -- province values
barely move year to year, so one value per province is used for all years.
Natural gas CH4/N2O: Table 2.x, "Residential, Construction, Commercial/
Institutional, Agriculture" row, g GHG/m3 (already CO2e-weighted).
Propane / Light Fuel Oil: Table 3.x / 4.x, "residential" rows, g GHG/L.

WHY THE AB/NF CORRECTION (measured 2026-08-02, see
docs/ENERGUIDE_QUESTIONS.md §5.4 for the full write-up): applying the
official OBPS electricity factor to real ERS consumption and comparing the
result to the real reported ERSGHG, every province agrees within about
+/-15% except Alberta (official runs 18-29% low, every year 2023-2026, at
40,000-50,000 homes/year -- not noise) and Newfoundland & Labrador (official
runs 27-49% low, at 300-6,400 homes/year). We could not find NRCan
documentation of what HOT2000 uses internally (open question, see
ENERGUIDE_QUESTIONS.md), so for these two provinces the ERS-calibrated
factor -- which by construction reproduces what HOT2000 actually computed
for these same audits -- is substituted for the official one.
"""

import os
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ERS_FACTOR_TABLE = os.path.join(HERE, "ers_ghg_factors_by_province_year.csv")

# Provinces where the official OBPS electricity factor is known (validated
# 2026-08-02) to diverge materially from what the ERS data itself implies.
# See the module docstring "WHY THE AB/NF CORRECTION".
CORRECTED_PROVINCES = {"AB", "NF"}

# ---------------------------------------------------------------------------
# Official electricity consumption intensity, g CO2e/kWh electricity consumed.
# ECCC OBPS reference values, Tables 5.1-5.3. 2024 shares 2023's table.
# ---------------------------------------------------------------------------
OBPS_ELECTRICITY = {
    "2023": {"BC": 15.0, "AB": 540.0, "SK": 730.0, "MB": 2.0, "ON": 30.0, "QC": 1.7,
             "NB": 300.0, "NS": 690.0, "PE": 300.0, "NF": 17.0, "YK": 80.0, "NT": 170.0, "NU": 840.0},
    "2024": {"BC": 15.0, "AB": 540.0, "SK": 730.0, "MB": 2.0, "ON": 30.0, "QC": 1.7,
             "NB": 300.0, "NS": 690.0, "PE": 300.0, "NF": 17.0, "YK": 80.0, "NT": 170.0, "NU": 840.0},
    "2025": {"BC": 15.0, "AB": 490.0, "SK": 670.0, "MB": 1.4, "ON": 38.0, "QC": 1.7,
             "NB": 350.0, "NS": 700.0, "PE": 350.0, "NF": 18.0, "YK": 70.0, "NT": 190.0, "NU": 820.0},
    "2026": {"BC": 18.0, "AB": 438.0, "SK": 631.0, "MB": 2.5, "ON": 59.0, "QC": 1.9,
             "NB": 234.0, "NS": 581.0, "PE": 234.0, "NF": 17.0, "YK": 74.0, "NT": 420.0, "NU": 800.0},
}
OBPS_LATEST_YEAR = "2026"
OBPS_YEARS_SORTED = sorted(int(y) for y in OBPS_ELECTRICITY.keys())

# ---------------------------------------------------------------------------
# Official combustion factors, converted to g CO2e/kWh of *fuel input* using
# ers_web_pipeline.py's own native-unit -> kWh conversion factors, so a
# consumption column already in kWh can be multiplied directly without a
# second, inconsistent conversion.
#   gas:      10.3611 kWh/m3   (ers_web_pipeline.py)
#   oil:      10.7778 kWh/L
#   propane:   7.0917 kWh/L
# Natural gas CO2 varies slightly by province (Table 1.x, "Marketable");
# CH4+N2O (Table 2.x, residential row) = 0.037+0.035 = 0.072 g/m3, added to
# every province. Oil and propane CO2/CH4/N2O are single national values
# (Table 3.x/4.x, residential rows).
# ---------------------------------------------------------------------------
_NG_CO2_G_PER_M3 = {"BC": 1966, "AB": 1962, "SK": 1920, "MB": 1915, "ON": 1921, "QC": 1926,
                    "NB": 1919, "NS": 1919, "PE": 1919, "NF": 1919, "YK": 1966, "NT": 1966, "NU": 1966}
_NG_RESIDENTIAL_CH4_N2O_G_PER_M3 = 0.037 + 0.035
_NG_KWH_PER_M3 = 10.3611
OFFICIAL_NATURAL_GAS_G_PER_KWH = {
    p: (co2 + _NG_RESIDENTIAL_CH4_N2O_G_PER_M3) / _NG_KWH_PER_M3
    for p, co2 in _NG_CO2_G_PER_M3.items()
}

_LFO_CO2_CH4_N2O_G_PER_L = 2753 + 0.026 + 0.006   # "Light Fuel Oil - Residential"
_LFO_KWH_PER_L = 10.7778
OFFICIAL_OIL_G_PER_KWH = _LFO_CO2_CH4_N2O_G_PER_L / _LFO_KWH_PER_L

_PROPANE_CO2_CH4_N2O_G_PER_L = 1515 + 0.027 + 0.108   # "Propane - Residential"
_PROPANE_KWH_PER_L = 7.0917
OFFICIAL_PROPANE_G_PER_KWH = _PROPANE_CO2_CH4_N2O_G_PER_L / _PROPANE_KWH_PER_L

OFFICIAL_WOOD_G_PER_KWH = 0.0   # biogenic-neutral; see module docstring.

_DEFAULT_NG_G_PER_KWH = (1921 + _NG_RESIDENTIAL_CH4_N2O_G_PER_M3) / _NG_KWH_PER_M3  # ON as fallback


def official_combustion_g_per_kwh(province):
    """(natural_gas, oil, propane, wood) g CO2e/kWh-of-fuel-input for a province."""
    return (
        OFFICIAL_NATURAL_GAS_G_PER_KWH.get(province, _DEFAULT_NG_G_PER_KWH),
        OFFICIAL_OIL_G_PER_KWH,
        OFFICIAL_PROPANE_G_PER_KWH,
        OFFICIAL_WOOD_G_PER_KWH,
    )


# ---------------------------------------------------------------------------
# ERS-calibrated electricity factor lookup (bias-fixed -- see
# ers_ghg_factors.py). Per (province, year), falling back to a national
# n-weighted pooled value for that year when the province/year cell has
# fewer than MIN_N audits, and to the nearest available year when a
# province/year combination is entirely absent.
# ---------------------------------------------------------------------------
MIN_N = 30


class _ErsFuelFactors:
    """Per-(province, year) ERS-calibrated factor lookup for one fuel, with a
    national n-weighted pooled-by-year fallback for small-n cells."""

    def __init__(self, fuel, csv_path=ERS_FACTOR_TABLE):
        df = pd.read_csv(csv_path)
        df = df[df["fuel"] == fuel].copy()
        df["year"] = df["year"].astype(str)
        self._by_prov_year = {
            (r["province"], r["year"]): (r["factor_kwh"], int(r["n"]))
            for _, r in df.iterrows()
        }
        pooled = df.groupby("year").apply(
            lambda g: (g["n"] * g["factor_kwh"]).sum() / g["n"].sum() if g["n"].sum() else None,
            include_groups=False,
        )
        self._pooled_by_year = {y: v for y, v in pooled.items() if v is not None}
        self._years_sorted = sorted(int(y) for y in self._pooled_by_year.keys())

    def _nearest_pooled_year(self, year):
        y = int(year)
        if not self._years_sorted:
            return None
        nearest = min(self._years_sorted, key=lambda yy: abs(yy - y))
        return self._pooled_by_year[str(nearest)]

    def factor_g_per_kwh(self, province, year):
        """ERS-calibrated factor, g CO2e/kWh, for (province, year)."""
        year = str(year)
        cell = self._by_prov_year.get((province, year))
        if cell is not None and cell[1] >= MIN_N:
            return cell[0] * 1000.0   # factor_kwh in ers_ghg_factors_by_province_year.csv is kg/kWh
        return (self._nearest_pooled_year(year) or 0.0) * 1000.0


class ErsElectricityFactors(_ErsFuelFactors):
    def __init__(self, csv_path=ERS_FACTOR_TABLE):
        super().__init__("Electricity", csv_path)


class ErsCombustionFactors:
    """Per-(fuel, province, year) ERS-calibrated combustion factor lookup,
    for scenario 3 (as_audited) only -- see module docstring "WHY SCENARIO 3
    NEEDS YEAR-VARYING COMBUSTION, NOT THE FIXED OFFICIAL CONSTANTS".

    Wood is deliberately excluded and always returns 0: the ERS-implied wood
    ratio (pooled across all years/provinces) comes out to ~358 kg CO2e/kg,
    not physically plausible for a combustion factor -- see
    ers_ghg_factors.py's module docstring. Official convention (biogenic-
    neutral) is used for wood in every scenario, not just 1/2.
    """

    def __init__(self, csv_path=ERS_FACTOR_TABLE):
        self._by_fuel = {
            fuel: _ErsFuelFactors(fuel, csv_path)
            for fuel in ("NaturalGas", "Oil", "Propane")
        }

    def factors_g_per_kwh(self, province, year):
        """(natural_gas, oil, propane, wood) g CO2e/kWh, ERS-calibrated for
        (province, year); wood is always 0 (see class docstring)."""
        return (
            self._by_fuel["NaturalGas"].factor_g_per_kwh(province, year),
            self._by_fuel["Oil"].factor_g_per_kwh(province, year),
            self._by_fuel["Propane"].factor_g_per_kwh(province, year),
            0.0,
        )


# ---------------------------------------------------------------------------
# Scenario-level electricity factor selection
# ---------------------------------------------------------------------------

def official_electricity_g_per_kwh(province, year):
    """Official OBPS factor for a specific audit year, clamped to the
    published 2023-2026 range (nearest published year outside it)."""
    y = int(year)
    y_clamped = min(max(y, OBPS_YEARS_SORTED[0]), OBPS_YEARS_SORTED[-1])
    table = OBPS_ELECTRICITY[str(y_clamped)]
    return table.get(province, table.get("ON"))


def current_electricity_g_per_kwh(province, ers_factors: "ErsElectricityFactors"):
    """Scenario 1: flat latest-year (2026) official factor, uncorrected."""
    return OBPS_ELECTRICITY[OBPS_LATEST_YEAR].get(province,
                                                    OBPS_ELECTRICITY[OBPS_LATEST_YEAR]["ON"])


def current_corrected_electricity_g_per_kwh(province, ers_factors: "ErsElectricityFactors"):
    """Scenario 2: flat latest-year, with AB/NF substituted from ERS-calibrated."""
    if province in CORRECTED_PROVINCES:
        return ers_factors.factor_g_per_kwh(province, OBPS_LATEST_YEAR)
    return OBPS_ELECTRICITY[OBPS_LATEST_YEAR].get(province,
                                                    OBPS_ELECTRICITY[OBPS_LATEST_YEAR]["ON"])


def as_audited_electricity_g_per_kwh(province, year, ers_factors: "ErsElectricityFactors"):
    """Scenario 3: ERS-calibrated, matched to the home's own audit year,
    every province (official has no pre-2023 coverage at all)."""
    return ers_factors.factor_g_per_kwh(province, year)
