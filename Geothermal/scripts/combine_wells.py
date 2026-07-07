"""
combine_wells.py

Combine the Ottawa WWIS "extracted well data" into a single multi-layer
GeoPackage, ottawa_geothermal.gpkg, following the plan in
Ottawa_Geothermal_Project_Summary.md.

This is the *rich* dataset: instead of one bucketed lithology per well (which
is what Data/processed/wwis_ottawa.geojson already gives you), it keeps the
Access database's relational detail -- every formation interval, every water
strike, every pump test -- as separate layers, plus a one-row-per-well summary
layer with geometry joined from the WWIS shapefile.

Layers produced:
    wells         one row per WELL_ID: geometry + summary + derived fields
    formations    one row per formation interval (decoded lithology)
    water         one row per water strike (decoded kind)
    pump_tests    one row per pump test
    construction  casing + screen + hole intervals, stacked

Inputs (all live on your machine, none are committed to the repo):
    --access   Either a FOLDER of exported Ottawa tables (CSV), or the .mdb
               file itself. Expected tables (the *_Ottawa suffix is optional):
                   tblWWR, tblBore_Hole, tblFormation, tblWater,
                   tblPump_Test, tblCasing, tblScreen, tblHole
               plus lookup tables:  _code_formation_Material, _code_water_kind,
                   _codeWaterUse, _code_final_status, _codeColor,
                   _code_construct_method, _code_casing_material
    --shp      wwis_out.shp (the WWIS shapefile, for geometry)
    --out      output .gpkg path (default: Data/processed/ottawa_geothermal.gpkg)

Dependencies:
    pip install geopandas pandas shapely pyproj
    # only if you point --access at a .mdb instead of exported CSVs:
    pip install pandas_access        # and system 'mdbtools' (apt/brew install mdbtools)

Usage:
    # from a folder of CSV exports:
    python combine_wells.py --access ../Data/Raw/WWIS/ottawa_tables \
        --shp ../Data/Raw/WWIS/wwis_out.shp

    # or straight from the Access file:
    python combine_wells.py --access "../Data/Raw/WWIS/Data2024Q4  250723 181853.mdb" \
        --shp ../Data/Raw/WWIS/wwis_out.shp

The script is deliberately chatty: for every table it prints how many rows it
loaded and which expected columns it could/couldn't find, so you can see what
matched before trusting the output.
"""

import argparse
import sys
from pathlib import Path

import pandas as pd

try:
    import geopandas as gpd
    from shapely.geometry import Point
except ImportError:
    sys.exit("geopandas is required: pip install geopandas pandas shapely pyproj")


# --------------------------------------------------------------------------
# Reference lookups (used for derived fields, independent of the DB lookups)
# --------------------------------------------------------------------------

# Approximate mid-range thermal conductivity (W/m.K) from published GSHP design
# literature. Keyed by the lithology bucket we normalise decoded materials to.
# These are ESTIMATES from lithology, NOT measured values -- WWIS has no TRT data.
CONDUCTIVITY_WM = {
    "limestone": 2.8, "dolostone": 3.0, "dolomite": 3.0, "sandstone": 2.3,
    "shale": 1.9, "granite": 3.2, "gneiss": 3.0, "clay": 1.4, "silt": 1.5,
    "sand": 2.4, "gravel": 2.0, "till": 1.8, "limestone/shale": 2.3,
}

# Map raw decoded material words -> normalised lithology bucket used above.
LITHOLOGY_BUCKET = {
    "limestone": "limestone", "lmsn": "limestone",
    "dolomite": "dolostone", "dolostone": "dolostone", "dlst": "dolostone",
    "sandstone": "sandstone", "snds": "sandstone",
    "shale": "shale", "shle": "shale",
    "granite": "granite", "grnt": "granite",
    "gneiss": "gneiss",
    "clay": "clay",
    "silt": "silt",
    "fine sand": "sand", "medium sand": "sand", "coarse sand": "sand",
    "sand": "sand",
    "gravel": "gravel", "stones": "gravel",
    "till": "till", "hardpan": "till",
}


def conductivity_class(value):
    if value is None or pd.isna(value):
        return "unknown"
    if value < 2.0:
        return "low"
    if value <= 2.8:
        return "medium"
    return "high"


# --------------------------------------------------------------------------
# Loading Access exports (folder of CSVs) or the .mdb directly
# --------------------------------------------------------------------------

class Source:
    """Uniform table loader over either a CSV folder or an .mdb file."""

    def __init__(self, path: Path):
        self.path = path
        self.is_mdb = path.is_file() and path.suffix.lower() in (".mdb", ".accdb")
        if self.is_mdb:
            try:
                import pandas_access as mdb
            except ImportError:
                sys.exit(
                    "Reading a .mdb needs: pip install pandas_access "
                    "(and system 'mdbtools'). Or export the tables to CSV and "
                    "point --access at the folder instead."
                )
            self._mdb = mdb
            self._tables = {t.lower(): t for t in mdb.list_tables(str(path))}
        else:
            if not path.is_dir():
                sys.exit(f"--access must be a .mdb file or a folder of CSVs: {path}")
            self._csvs = {p.stem.lower(): p for p in path.glob("*.csv")}

    def _resolve(self, name: str):
        """Find a table whether or not it carries the _Ottawa suffix / case."""
        key = name.lower()
        candidates = [key, key + "_ottawa"]
        store = self._tables if self.is_mdb else self._csvs
        for c in candidates:
            if c in store:
                return store[c]
        # loose contains-match as a last resort
        for k in store:
            if k.startswith(key):
                return store[k]
        return None

    def table(self, name: str, required=False) -> pd.DataFrame:
        found = self._resolve(name)
        if found is None:
            msg = f"  [table] {name}: NOT FOUND"
            if required:
                sys.exit(msg + " (required)")
            print(msg + " (skipping)")
            return pd.DataFrame()
        if self.is_mdb:
            df = self._mdb.read_table(str(self.path), found)
        else:
            df = pd.read_csv(found, dtype=str, low_memory=False)
        print(f"  [table] {name}: {len(df):,} rows  <- {found}")
        return df


def col(df: pd.DataFrame, *names):
    """Return the first matching column name (case-insensitive) or None."""
    lower = {c.lower(): c for c in df.columns}
    for n in names:
        if n.lower() in lower:
            return lower[n.lower()]
    return None


def report_cols(df, wanted: dict):
    """wanted = {logical_name: actual_or_None}; print what matched."""
    got = [k for k, v in wanted.items() if v]
    missing = [k for k, v in wanted.items() if not v]
    if got:
        print(f"    matched: {', '.join(got)}")
    if missing:
        print(f"    MISSING: {', '.join(missing)}")


def as_num(series):
    return pd.to_numeric(series, errors="coerce")


# --------------------------------------------------------------------------
# Lookup-dictionary builder from _code_* tables
# --------------------------------------------------------------------------

def build_lookup(src: Source, table_name: str) -> dict:
    """Return {code(str) -> description} from a two-column _code_* table."""
    df = src.table(table_name)
    if df.empty:
        return {}
    code_c = col(df, "code", "id", df.columns[0])
    desc_c = col(df, "description", "descr", "name", "value", df.columns[-1])
    out = {}
    for _, r in df.iterrows():
        code = str(r[code_c]).strip()
        # normalise "5" and "05" to the same key
        out[code] = str(r[desc_c]).strip()
        if code.isdigit():
            out[str(int(code))] = str(r[desc_c]).strip()
            out[code.zfill(2)] = str(r[desc_c]).strip()
    return out


def decode(code, lookup: dict):
    if code is None or (isinstance(code, float) and pd.isna(code)):
        return None
    s = str(code).strip()
    if s == "" or s.lower() == "nan":
        return None
    return lookup.get(s) or lookup.get(s.lstrip("0")) or lookup.get(s.zfill(2)) or s


# --------------------------------------------------------------------------
# Layer builders
# --------------------------------------------------------------------------

def build_formations(src, mat_lookup, color_lookup):
    df = src.table("tblFormation", required=True)
    c = {
        "well_id": col(df, "WELL_ID", "WELLID"),
        "top": col(df, "FORMATION_TOP_DEPTH", "TOP_DEPTH", "DEPTH_FROM"),
        "bottom": col(df, "FORMATION_END_DEPTH", "END_DEPTH", "DEPTH_TO"),
        "mat1": col(df, "MAT1", "MATERIAL1"),
        "mat2": col(df, "MAT2", "MATERIAL2"),
        "mat3": col(df, "MAT3", "MATERIAL3"),
        "color": col(df, "COLOR", "COLOUR"),
    }
    report_cols(df, c)
    out = pd.DataFrame({
        "WELL_ID": df[c["well_id"]],
        "top_depth": as_num(df[c["top"]]) if c["top"] else None,
        "bottom_depth": as_num(df[c["bottom"]]) if c["bottom"] else None,
        "material1": df[c["mat1"]].map(lambda x: decode(x, mat_lookup)) if c["mat1"] else None,
        "material2": df[c["mat2"]].map(lambda x: decode(x, mat_lookup)) if c["mat2"] else None,
        "material3": df[c["mat3"]].map(lambda x: decode(x, mat_lookup)) if c["mat3"] else None,
        "color": df[c["color"]].map(lambda x: decode(x, color_lookup)) if c["color"] else None,
    })
    out["lithology"] = out["material1"].map(_to_bucket)
    return out


def _to_bucket(material):
    if material is None or pd.isna(material):
        return "unknown"
    m = str(material).strip().lower()
    for key, bucket in LITHOLOGY_BUCKET.items():
        if key in m:
            return bucket
    return "unknown"


def build_water(src, kind_lookup):
    df = src.table("tblWater")
    if df.empty:
        return df
    c = {
        "well_id": col(df, "WELL_ID"),
        "depth": col(df, "WATER_FOUND_DEPTH", "DEPTH"),
        "kind": col(df, "KIND", "WATER_KIND"),
    }
    report_cols(df, c)
    return pd.DataFrame({
        "WELL_ID": df[c["well_id"]],
        "water_found_depth": as_num(df[c["depth"]]) if c["depth"] else None,
        "water_kind": df[c["kind"]].map(lambda x: decode(x, kind_lookup)) if c["kind"] else None,
    })


def build_pump_tests(src):
    df = src.table("tblPump_Test")
    if df.empty:
        return df
    c = {
        "well_id": col(df, "WELL_ID"),
        "static": col(df, "STATIC_LEV", "STATIC_LEVEL"),
        "final": col(df, "FINAL_LEV_AFTER_PUMPING", "FINAL_LEVEL"),
        "pump_rate": col(df, "PUMPING_RATE", "RECOM_RATE"),
        "flow_rate": col(df, "FLOWING_RATE"),
        "dur_hr": col(df, "PUMPING_DURATION_HR"),
        "dur_min": col(df, "PUMPING_DURATION_MIN"),
    }
    report_cols(df, c)
    dur = (as_num(df[c["dur_hr"]]).fillna(0) * 60 if c["dur_hr"] else 0) + \
          (as_num(df[c["dur_min"]]).fillna(0) if c["dur_min"] else 0)
    return pd.DataFrame({
        "WELL_ID": df[c["well_id"]],
        "static_level": as_num(df[c["static"]]) if c["static"] else None,
        "final_level": as_num(df[c["final"]]) if c["final"] else None,
        "pump_rate": as_num(df[c["pump_rate"]]) if c["pump_rate"] else None,
        "flowing_rate": as_num(df[c["flow_rate"]]) if c["flow_rate"] else None,
        "duration_min": dur if isinstance(dur, pd.Series) else None,
    })


def build_construction(src, casing_mat_lookup):
    """Stack casing, screen and hole intervals into one long table."""
    parts = []
    casing = src.table("tblCasing")
    if not casing.empty:
        c = {"well_id": col(casing, "WELL_ID"),
             "frm": col(casing, "DEPTH_FROM"), "to": col(casing, "DEPTH_TO"),
             "dia": col(casing, "CASING_DIAMETER", "DIAMETER"),
             "mat": col(casing, "MATERIAL")}
        parts.append(pd.DataFrame({
            "WELL_ID": casing[c["well_id"]], "element": "casing",
            "depth_from": as_num(casing[c["frm"]]) if c["frm"] else None,
            "depth_to": as_num(casing[c["to"]]) if c["to"] else None,
            "diameter": as_num(casing[c["dia"]]) if c["dia"] else None,
            "material": casing[c["mat"]].map(lambda x: decode(x, casing_mat_lookup)) if c["mat"] else None,
        }))
    screen = src.table("tblScreen")
    if not screen.empty:
        c = {"well_id": col(screen, "WELL_ID"),
             "frm": col(screen, "SCRN_TOP_DEPTH"), "to": col(screen, "SCRN_END_DEPTH"),
             "dia": col(screen, "SCRN_DIAMETER"), "mat": col(screen, "SCRN_MATERIAL")}
        parts.append(pd.DataFrame({
            "WELL_ID": screen[c["well_id"]], "element": "screen",
            "depth_from": as_num(screen[c["frm"]]) if c["frm"] else None,
            "depth_to": as_num(screen[c["to"]]) if c["to"] else None,
            "diameter": as_num(screen[c["dia"]]) if c["dia"] else None,
            "material": screen[c["mat"]] if c["mat"] else None,
        }))
    hole = src.table("tblHole")
    if not hole.empty:
        c = {"well_id": col(hole, "WELL_ID"),
             "frm": col(hole, "DEPTH_FROM"), "to": col(hole, "DEPTH_TO"),
             "dia": col(hole, "DIAMETER")}
        parts.append(pd.DataFrame({
            "WELL_ID": hole[c["well_id"]], "element": "hole",
            "depth_from": as_num(hole[c["frm"]]) if c["frm"] else None,
            "depth_to": as_num(hole[c["to"]]) if c["to"] else None,
            "diameter": as_num(hole[c["dia"]]) if c["dia"] else None,
            "material": None,
        }))
    if not parts:
        return pd.DataFrame()
    return pd.concat(parts, ignore_index=True)


def build_wells(src, formations, water, pump_tests, use_lookup, status_lookup):
    """One row per well, with a formation summary + derived screening fields."""
    wwr = src.table("tblWWR", required=True)
    c = {
        "well_id": col(wwr, "WELL_ID"),
        "county": col(wwr, "COUNTY"),
        "use": col(wwr, "USE_1ST", "WELL_USE", "USE"),
        "status": col(wwr, "FINAL_STA", "FINAL_STATUS", "STATUS"),
    }
    report_cols(wwr, c)
    wells = pd.DataFrame({
        "WELL_ID": wwr[c["well_id"]],
        "well_use": wwr[c["use"]].map(lambda x: decode(x, use_lookup)) if c["use"] else None,
        "status": wwr[c["status"]].map(lambda x: decode(x, status_lookup)) if c["status"] else None,
    }).drop_duplicates("WELL_ID")

    # --- aggregate formations per well: summary string + primary lithology + bedrock depth
    f = formations.copy()
    f["_order"] = as_num(f["top_depth"])
    f = f.sort_values(["WELL_ID", "_order"])

    def summarise(g):
        rows = []
        for _, r in g.iterrows():
            lith = r["material1"] or "?"
            top = r["top_depth"]
            rows.append(f"{lith} {top:g}m" if pd.notna(top) else str(lith))
        return " / ".join(rows[:8])

    summary = f.groupby("WELL_ID").apply(summarise).rename("formation_summary")
    # primary lithology = thickest interval's bucket
    f["_thick"] = as_num(f["bottom_depth"]) - as_num(f["top_depth"])
    primary = (f.sort_values("_thick", ascending=False)
                 .drop_duplicates("WELL_ID").set_index("WELL_ID")["lithology"]
                 .rename("primary_lithology"))
    # bedrock depth ~ top of first bedrock lithology
    bedrock_liths = {"limestone", "dolostone", "sandstone", "shale", "granite", "gneiss"}
    fb = f[f["lithology"].isin(bedrock_liths)]
    bedrock = (fb.groupby("WELL_ID")["top_depth"].min()
                 .rename("bedrock_depth_m"))

    wells = (wells.merge(summary, on="WELL_ID", how="left")
                  .merge(primary, on="WELL_ID", how="left")
                  .merge(bedrock, on="WELL_ID", how="left"))

    # --- water + pump aggregates
    if not water.empty:
        w = water.groupby("WELL_ID").agg(
            water_found_depth=("water_found_depth", "min")).reset_index()
        wells = wells.merge(w, on="WELL_ID", how="left")
    if not pump_tests.empty:
        p = pump_tests.groupby("WELL_ID").agg(
            static_level_m=("static_level", "min"),
            well_yield_lpm=("pump_rate", "max")).reset_index()
        wells = wells.merge(p, on="WELL_ID", how="left")

    # --- derived screening fields
    wells["estimated_conductivity_wm"] = wells["primary_lithology"].map(CONDUCTIVITY_WM)
    wells["estimated_conductivity_class"] = wells["estimated_conductivity_wm"].map(conductivity_class)
    wells["bedrock_indicator"] = wells.get("bedrock_depth_m").notna()
    gw = wells.get("static_level_m")
    wells["groundwater_indicator"] = gw.notna() if gw is not None else False
    return wells


# --------------------------------------------------------------------------
# Geometry
# --------------------------------------------------------------------------

def attach_geometry(wells: pd.DataFrame, shp_path: Path) -> gpd.GeoDataFrame:
    print(f"  [shp] reading {shp_path}")
    shp = gpd.read_file(shp_path)
    wid = col(shp, "WELL_ID", "WELLID")
    if wid is None:
        sys.exit(f"  shapefile has no WELL_ID column; columns = {list(shp.columns)}")
    shp = shp[[wid, "geometry"]].rename(columns={wid: "WELL_ID"})
    shp = shp.to_crs(4326)
    shp["WELL_ID"] = shp["WELL_ID"].astype(str)
    wells["WELL_ID"] = wells["WELL_ID"].astype(str)
    merged = wells.merge(shp, on="WELL_ID", how="left")
    gdf = gpd.GeoDataFrame(merged, geometry="geometry", crs=4326)
    missing = gdf.geometry.isna().sum()
    print(f"  [shp] joined geometry; {missing:,} of {len(gdf):,} wells have no match")
    return gdf


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--access", required=True, type=Path,
                    help=".mdb file OR folder of exported *_Ottawa CSV tables")
    ap.add_argument("--shp", required=True, type=Path, help="wwis_out.shp")
    ap.add_argument("--out", type=Path,
                    default=Path(__file__).resolve().parents[1]
                    / "Data" / "processed" / "ottawa_geothermal.gpkg")
    args = ap.parse_args()

    src = Source(args.access)

    print("\n== Building lookup dictionaries ==")
    mat_lookup = build_lookup(src, "_code_formation_Material")
    kind_lookup = build_lookup(src, "_code_water_kind")
    use_lookup = build_lookup(src, "_codeWaterUse")
    status_lookup = build_lookup(src, "_code_final_status")
    color_lookup = build_lookup(src, "_codeColor")
    casing_mat_lookup = build_lookup(src, "_code_casing_material")

    print("\n== Building layers ==")
    formations = build_formations(src, mat_lookup, color_lookup)
    water = build_water(src, kind_lookup)
    pump_tests = build_pump_tests(src)
    construction = build_construction(src, casing_mat_lookup)
    wells = build_wells(src, formations, water, pump_tests, use_lookup, status_lookup)

    print("\n== Attaching geometry ==")
    wells_gdf = attach_geometry(wells, args.shp)

    print("\n== Writing GeoPackage ==")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    wells_gdf.to_file(args.out, layer="wells", driver="GPKG")
    for name, df in [("formations", formations), ("water", water),
                     ("pump_tests", pump_tests), ("construction", construction)]:
        if df is None or df.empty:
            print(f"  skip empty layer: {name}")
            continue
        df.to_file(args.out, layer=name, driver="GPKG") if isinstance(df, gpd.GeoDataFrame) \
            else _write_table_layer(df, args.out, name)
    print(f"\nDone -> {args.out}")
    print(f"  wells:        {len(wells_gdf):,}")
    print(f"  formations:   {len(formations):,}")
    print(f"  water:        {len(water):,}")
    print(f"  pump_tests:   {len(pump_tests):,}")
    print(f"  construction: {len(construction):,}")


def _write_table_layer(df: pd.DataFrame, out: Path, layer: str):
    """Non-spatial layers still go in the .gpkg (geometry-less)."""
    gdf = gpd.GeoDataFrame(df.copy(), geometry=[None] * len(df), crs=4326)
    gdf.to_file(out, layer=layer, driver="GPKG")


if __name__ == "__main__":
    main()
