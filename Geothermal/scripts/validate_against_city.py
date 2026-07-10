"""
validate_against_city.py

Cross-validate the WWIS-derived open-loop screen against the City of Ottawa's
own "Open Loop Geothermal Potential" polygons (Planning/122, fetched by
fetch_municipal_layers.py).

Method: spatial-join every well (ottawa_geothermal.gpkg wells layer) to the
city polygon it falls in, then cross-tabulate:

    rows    our per-well open_loop screen   (viable / possible / unlikely)
    cols    the city's polygon rating       (High / Average / Low / None,
                                             plus "outside" = no polygon)

Also reports mean well yield and mean estimated conductivity per city class,
as a sanity check that the classes order the way they should.

Output: printed report + Data/processed/city_validation.csv (the crosstab).

Usage:
    python Geothermal/scripts/validate_against_city.py
"""

from pathlib import Path

import geopandas as gpd
import pandas as pd

HERE = Path(__file__).resolve().parents[1]              # Geothermal/
GPKG = HERE / "Data" / "processed" / "ottawa_geothermal.gpkg"
CITY = HERE / "Data" / "processed" / "city_open_loop_potential.geojson"
OUT = HERE / "Data" / "processed" / "city_validation.csv"

BBOX = (-76.36, 44.96, -75.24, 45.61)
CITY_ORDER = ["High", "Average", "Low", "None", "outside"]
OURS_ORDER = ["viable", "possible", "unlikely"]


def main():
    wells = gpd.read_file(GPKG, layer="wells")
    wells = wells[wells.geometry.notna()].cx[BBOX[0]:BBOX[2], BBOX[1]:BBOX[3]]
    wells["well_yield_lpm"] = pd.to_numeric(wells["well_yield_lpm"], errors="coerce")

    city = gpd.read_file(CITY)[["POTENTIAL_EN", "geometry"]]

    joined = gpd.sjoin(wells, city, how="left", predicate="within")
    # a well can sit in overlapping polygons -> keep the most optimistic rating
    rank = {"High": 0, "Average": 1, "Low": 2, "None": 3}
    joined["_rank"] = joined["POTENTIAL_EN"].map(rank).fillna(4)
    joined = (joined.sort_values("_rank")
                    .drop_duplicates("WELL_ID"))
    joined["city"] = joined["POTENTIAL_EN"].fillna("outside")

    n_outside = (joined["city"] == "outside").sum()
    print(f"wells: {len(joined):,}  (outside any city polygon: {n_outside:,})")

    ct = pd.crosstab(joined["open_loop"], joined["city"])
    ct = ct.reindex(index=OURS_ORDER, columns=[c for c in CITY_ORDER if c in ct])
    print("\n== crosstab: our screen (rows) x city rating (cols) ==")
    print(ct.to_string())

    pct = ct.div(ct.sum(axis=0), axis=1).mul(100).round(1)
    print("\n== column %: share of wells rated viable/possible/unlikely, per city class ==")
    print(pct.to_string())

    print("\n== per city class: well evidence ==")
    stats = (joined.groupby("city")
             .agg(wells=("WELL_ID", "count"),
                  mean_yield_lpm=("well_yield_lpm", "mean"),
                  median_yield_lpm=("well_yield_lpm", "median"),
                  mean_conductivity=("estimated_conductivity_wm", "mean"))
             .reindex([c for c in CITY_ORDER if c in joined["city"].unique()])
             .round(2))
    print(stats.to_string())

    ct.to_csv(OUT)
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
