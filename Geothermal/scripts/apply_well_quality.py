"""
apply_well_quality.py

Adds `well_quality` (good | medium | bad) and `lith_logged_cov` to the `wells`
layer of Data/processed/ottawa_geothermal.gpkg using the rule in
combine_wells.add_well_quality (README s3.1b).

Why a separate step: combine_wells.py also calls add_well_quality when it
builds the GeoPackage from the raw WWIS tables. This script applies the same
function to an EXISTING GeoPackage, so the band can be refreshed without the
raw tbl*_Ottawa.csv exports or Data/conductivity_reference.csv being present.
Idempotent: re-running just recomputes the two columns.

Input : Data/processed/ottawa_geothermal.gpkg  (layers `wells`, `formations`)
Output: same GeoPackage, `wells` layer rewritten with the two new columns
        (all other layers are left untouched; a .bak copy is made first).

Usage:
    python Geothermal/scripts/apply_well_quality.py
"""

import shutil
import sys
from pathlib import Path

import geopandas as gpd
import pyogrio

sys.path.insert(0, str(Path(__file__).resolve().parent))
from combine_wells import add_well_quality  # noqa: E402

GPKG = Path(__file__).resolve().parents[1] / "Data" / "processed" / "ottawa_geothermal.gpkg"


def main():
    layers_before = {name: pyogrio.read_info(GPKG, layer=name)["features"]
                     for name, _ in pyogrio.list_layers(GPKG)}
    wells = gpd.read_file(GPKG, layer="wells")
    formations = pyogrio.read_dataframe(GPKG, layer="formations", read_geometry=False)
    out = add_well_quality(wells, formations)

    shutil.copy2(GPKG, GPKG.with_suffix(".gpkg.bak"))
    out.to_file(GPKG, layer="wells", driver="GPKG", mode="w")

    layers_after = {name: pyogrio.read_info(GPKG, layer=name)["features"]
                    for name, _ in pyogrio.list_layers(GPKG)}
    assert layers_before == layers_after, (layers_before, layers_after)
    mapped = out[out.geometry.notna() & ~out.geometry.is_empty]
    print("well_quality, all wells :", dict(out["well_quality"].value_counts()))
    print("well_quality, mapped    :", dict(mapped["well_quality"].value_counts()))
    print("layers unchanged        :", layers_after)


if __name__ == "__main__":
    main()
