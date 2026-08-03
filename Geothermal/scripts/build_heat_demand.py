"""
build_heat_demand.py  --  Heat Demand Phase 4, grid half (HEATDEMAND_PLAN.md S4)

Aggregates Data/processed/buildings_ottawa.parquet (Phases 1-3: stock, current
load, electrified load) onto the canonical 500 m grid
(thermal_conductivity_grid.geojson, 13,778 cells, idw.py conventions) so
build_suitability.py's existing "demand" upgrade hook (README S3.9) has real
per-cell heat demand instead of the City-serviced-area proxy.

Scope note: this is the GRID half of Phase 4 only. The FEEDER half
(feeder_demand.geojson, stress = added electrified MW / available MVA) is
blocked -- GridCapacity/ottawa_capacity.geojson and the GridCapacity/Hydro.py
fetch script that produces it are both absent from this checkout, and Hydro.py
was never committed to main (the whole GridCapacity/ directory is gitignored,
unlike every other pipeline script in the repo). build_suitability.py's own
"feeder" factor is unrunnable here for the same reason. See ROADMAP item 7 /
GEOTHERMAL_STATUS.md for the follow-up.

Aggregation is over in_ottawa_cd == True only (Phase 2.5's convention -- every
city-wide sum in this pipeline takes that subset). Buildings outside it are
also where grid_cell_id is null (85% of the ~78k non-CD buildings; the 500 m
grid's coverage was built around the CD), so restricting to in_ottawa_cd both
matches convention and sidesteps that gap -- checked, not assumed: every
in_ottawa_cd building has a grid_cell_id (0 nulls).

Per-cell fields (only cells with >=1 building are emitted -- no invented
demand in empty cells):
    kwh_yr                    current annual space-heat delivered kWh (all
                               fuels; the field name f_from_polys expects)
    design_kw                 sum of design-day heat loss (kW @ -22.8 C)
    elec_kw_peak_now          current electric-heated stock's design kW
                               (already-electric only; NOT added load)
    elec_kwh_electrified / elec_kw_peak_electrified   policy (a): full
                               electrification, resistance backup, UNDIVERSIFIED
    elec_kwh_hybrid / elec_kw_peak_hybrid             policy (b): hybrid,
                               fossil backup retained, UNDIVERSIFIED
    elec_kwh_gshp / elec_kw_peak_gshp                 GSHP counterfactual,
                               UNDIVERSIFIED
    waste_heat_kwh             reserved, always null (no source yet)
    dominant_fuel               modal heat_fuel among heated buildings
    n_buildings, n_heated       counts (heated = annual_kwh > 0)
    class_counts                 JSON dict, building count by class

*_kw_peak_* columns are undiversified per-building coincident-design-condition
sums (Phase 3's caveat carries forward unchanged -- see README S3.12): they are
an upper bound on added feeder load, not a load-flow result, and Phase 3 showed
summing them directly can exceed the whole system's real peak. Do not treat
elec_kw_peak_electrified etc. here as MW headroom without the coincidence
factor that the (blocked) feeder half of Phase 4 was meant to derive.

Usage:
    python Geothermal/scripts/build_heat_demand.py
"""

import json
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parents[1]              # Geothermal/
BUILDINGS = HERE / "Data" / "processed" / "buildings_ottawa.parquet"
COND_GRID = HERE / "Data" / "processed" / "thermal_conductivity_grid.geojson"
OUT = HERE / "Data" / "processed" / "heat_demand_grid.geojson"

SUM_COLS = [
    "annual_kwh", "design_kw",
    "elec_kw_peak_now",
    "elec_kwh_electrified", "elec_kw_peak_electrified",
    "elec_kwh_hybrid", "elec_kw_peak_hybrid",
    "elec_kwh_gshp", "elec_kw_peak_gshp",
]

RENAME = {"annual_kwh": "kwh_yr"}   # f_from_polys(..., "kwh_yr", ...) expects this name


def load_grid():
    g = gpd.read_file(COND_GRID)
    print(f"  canonical grid: {len(g):,} cells ({COND_GRID.name})")
    return g


def load_buildings():
    gdf = gpd.read_parquet(BUILDINGS)
    n_all = len(gdf)
    cd = gdf[gdf["in_ottawa_cd"]].copy()
    print(f"  {n_all:,} buildings loaded; {len(cd):,} in_ottawa_cd (Phase 2.5 convention)")
    missing = cd["grid_cell_id"].isna().sum()
    print(f"  grid_cell_id null within in_ottawa_cd: {missing:,} "
          f"({'OK, none expected' if missing == 0 else 'UNEXPECTED -- investigate'})")
    cd = cd.dropna(subset=["grid_cell_id"])
    cd["cell_idx"] = cd["grid_cell_id"].str.replace("cell_", "", regex=False).astype(int)
    return cd


def aggregate(cd):
    heated = cd["annual_kwh"] > 0

    sums = cd.groupby("cell_idx")[SUM_COLS].sum()
    sums = sums.rename(columns=RENAME)

    counts = cd.groupby("cell_idx").size().rename("n_buildings")
    n_heated = cd[heated].groupby("cell_idx").size().reindex(sums.index, fill_value=0) \
                          .rename("n_heated")

    dominant_fuel = (
        cd[heated].groupby("cell_idx")["heat_fuel"]
        .agg(lambda s: s.value_counts().idxmax() if len(s) else None)
        .reindex(sums.index)
        .rename("dominant_fuel")
    )

    class_counts = (
        cd.groupby("cell_idx")["class"]
        .apply(lambda s: json.dumps(s.value_counts().to_dict()))
        .reindex(sums.index)
        .rename("class_counts")
    )

    out = pd.concat([sums, counts, n_heated, dominant_fuel, class_counts], axis=1)
    out["waste_heat_kwh"] = np.nan   # reserved -- no source yet (HEATDEMAND_PLAN.md S4)
    out.index.name = "cell_idx"
    return out.reset_index()


def validate(cd, agg_df):
    print("\n== Validation ==")
    for src_col, dst_col in [("annual_kwh", "kwh_yr"), ("design_kw", "design_kw"),
                              ("elec_kw_peak_electrified", "elec_kw_peak_electrified")]:
        bldg_sum = cd[src_col].sum()
        cell_sum = agg_df[dst_col].sum()
        rel = abs(bldg_sum - cell_sum) / max(bldg_sum, 1e-9)
        status = "OK" if rel < 1e-6 else f"MISMATCH ({rel:.2%})"
        print(f"  {dst_col}: buildings sum {bldg_sum:,.0f} == cells sum {cell_sum:,.0f}  [{status}]")
        assert rel < 1e-6, f"grid-cell sum does not equal building-level sum for {dst_col}"

    assert (agg_df["n_buildings"] > 0).all(), "a zero-building cell was emitted"
    print(f"  no zero-building cells emitted: OK ({len(agg_df):,} cells, all n_buildings > 0)")


def main():
    print("=" * 74)
    print("Heat Demand Phase 4 (grid half) -- build_heat_demand.py")
    print("=" * 74)

    print("\nLoading canonical grid ...")
    grid = load_grid()

    print("\nLoading buildings ...")
    cd = load_buildings()

    print("\nAggregating to 500 m cells ...")
    agg_df = aggregate(cd)
    print(f"  {len(agg_df):,} cells have >=1 building "
          f"({len(agg_df) / len(grid):.1%} of the {len(grid):,}-cell canonical grid)")

    validate(cd, agg_df)

    out_gdf = grid.iloc[agg_df["cell_idx"].to_numpy()].reset_index(drop=True)
    out_gdf = pd.concat([out_gdf.drop(columns=["bucket_shares", "label"], errors="ignore"),
                          agg_df.drop(columns=["cell_idx"])], axis=1)
    out_gdf = gpd.GeoDataFrame(out_gdf, geometry="geometry", crs=grid.crs)

    RES_CLASSES = ["detached", "row", "lowrise_murb", "highrise_murb", "accessory"]
    res_kwh = cd.loc[cd["class"].isin(RES_CLASSES), "annual_kwh"].sum()

    print("\n== Summary ==")
    print(f"  total current space-heat (all classes): {out_gdf['kwh_yr'].sum() / 1e9:.2f} TWh/yr")
    print(f"  residential-only subset: {res_kwh / 1e9:.2f} TWh/yr "
          f"(Phase 2.5 reported 6.68 TWh residential over the same in_ottawa_cd subset)")
    print(f"  total design heat load: {out_gdf['design_kw'].sum() / 1e3:.0f} MW")
    print(f"  policy (a) added (undiversified): "
          f"{out_gdf['elec_kwh_electrified'].sum() / 1e9:.2f} TWh/yr, "
          f"{out_gdf['elec_kw_peak_electrified'].sum() / 1e3:.0f} MW design-day "
          f"(Phase 3 reported +4,613 GWh / +5,264 MW)")
    print(f"  policy (b) hybrid added (undiversified): "
          f"{out_gdf['elec_kwh_hybrid'].sum() / 1e9:.2f} TWh/yr, "
          f"{out_gdf['elec_kw_peak_hybrid'].sum() / 1e3:.0f} MW design-day "
          f"(Phase 3 reported +3,410 GWh / +0 MW at design)")
    print(f"  GSHP counterfactual (undiversified): "
          f"{out_gdf['elec_kwh_gshp'].sum() / 1e9:.2f} TWh/yr, "
          f"{out_gdf['elec_kw_peak_gshp'].sum() / 1e3:.0f} MW design-day "
          f"(Phase 3 reported +2,515 GWh / +1,482 MW)")
    print(f"  dominant fuel across cells (unweighted, cell count): "
          f"{out_gdf['dominant_fuel'].value_counts().to_dict()}")
    print(f"  heated-building count by fuel (population-weighted): "
          f"{cd.loc[cd['annual_kwh'] > 0, 'heat_fuel'].value_counts().to_dict()}")

    top = out_gdf.nlargest(10, "kwh_yr")[["kwh_yr", "n_buildings", "dominant_fuel"]]
    print("\n  top-10 cells by annual heat demand:")
    print(top.to_string())

    OUT.parent.mkdir(parents=True, exist_ok=True)
    out_gdf.to_file(OUT, driver="GeoJSON")
    print(f"\n  wrote {OUT}  ({len(out_gdf):,} cells, {len(out_gdf.columns)} cols)")
    print("\n  NOTE: feeder_demand.geojson (feeder half of Phase 4) not built --")
    print("  GridCapacity/ottawa_capacity.geojson and Hydro.py are both absent")
    print("  from this checkout. See module docstring / GEOTHERMAL_STATUS.md.")


if __name__ == "__main__":
    main()
