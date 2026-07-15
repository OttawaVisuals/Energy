"""
combine_wells.py

Combine the Ottawa WWIS "extracted well data" into a single multi-layer
GeoPackage, ottawa_geothermal.gpkg, following the plan in
Ottawa_Geothermal_Project_Summary.md.

This is the *rich* dataset: it keeps the Access database's relational detail
(every formation interval, water strike, pump test, construction element) as
separate layers, plus a one-row-per-well summary layer whose geometry, total
depth, depth-to-bedrock and static level come from the (clean, metric) WWIS
shapefile.

The column names, code tables and units below were all derived from the actual
Ottawa exports in Geothermal/Data (tbl*_Ottawa.csv + wwis_out.shp), not from
the generic WWIS docs -- so it should run against your files as-is.

Layers produced:
    wells         one row per WELL_ID: geometry + depths + summary + derived fields
    formations    one row per formation interval (decoded lithology, metres)
    water         one row per water strike (decoded kind, metres)
    pump_tests    one row per pump test (metres, L/min)
    construction  casing + screen + hole intervals, stacked (metres)

--------------------------------------------------------------------------
UNITS.  The Access tables store depths in a mix of ft / m / cm / inch and
pumping rates in GPM / LPM, with a *_UOM column naming the unit per row.
Everything is converted to metres and L/min. The shapefile (DEPTH, DP_BEDROCK,
STATIC_LEV) is already in metres and is treated as authoritative for the
per-well summary values.

CODE TABLES.  USE_1ST, FINAL_STA, MAT1-3, water kind, casing material, colour
etc. are numeric/letter codes. The _code_* lookup tables were NOT in the
export, so this script ships with the codes confirmed from the data preview /
project summary as a built-in fallback, and will PREFER real _code_*.csv files
if you drop them next to the data (see --access). Any code it can't resolve is
passed through as "code:NN" rather than silently mislabelled -- so if you see
those in the output, export the matching _code_* table and rerun.
--------------------------------------------------------------------------

Inputs:
    --access   Folder holding the exported tbl*_Ottawa.csv files
               (default: Geothermal/Data). If you also export the lookup
               tables (_code_formation_Material.csv, _code_water_kind.csv,
               _codeWaterUse.csv, _code_final_status.csv, _codeColor.csv,
               _code_casing_material.csv, _code_construct_method.csv) into the
               same folder, they override the built-in defaults.
               A .mdb/.accdb file also works if pandas_access + mdbtools are
               installed.
    --shp      wwis_out.shp  (default: Geothermal/Data/wwis_out.shp)
    --out      output .gpkg  (default: Geothermal/Data/processed/ottawa_geothermal.gpkg)

Dependencies:
    pip install geopandas pandas shapely pyproj
    # only if --access points at a .mdb instead of CSVs:
    pip install pandas_access          # plus system 'mdbtools'

Usage:
    python Geothermal/scripts/combine_wells.py
    # or explicit:
    python Geothermal/scripts/combine_wells.py \
        --access Geothermal/Data --shp Geothermal/Data/wwis_out.shp
"""

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

try:
    import geopandas as gpd
except ImportError:
    sys.exit("geopandas is required: pip install geopandas pandas shapely pyproj")

from conductivity import load_reference

# Ottawa area only ever needs NAD83 UTM zone 17 or 18 (tblBore_Hole ZONE column
# occasionally has a stray 16 or 43 -- location errors, dropped per §3.1).
UTM_EPSG = {17: 26917, 18: 26918}

# GSC national bedrock geology (mapped-geology fallback for wells with no
# usable formation record). SUBRXTP is the finer rock-type field; RXTP is the
# coarse fallback when SUBRXTP isn't one of the values seen in the Ottawa area.
# Mapping documented in README.md §3.1 "Lithology fallback from mapped geology".
GSC_SUBRXTP_BUCKET = {
    "paragneiss": "gneiss",
    "marble": "limestone",
    "undivided granitoid rocks": "granite",
    "syenite, monzodiorite": "granite",
    "undivided sedimentary rocks": "limestone",  # St. Lawrence Platform Paleozoic
}
GSC_RXTP_BUCKET = {
    "metamorphic rocks": "gneiss",
    "intrusive rocks": "granite",
    "sedimentary rocks": "limestone",
}
GSC_GDB = Path(__file__).resolve().parents[1] / "Data" / "Raw" / "GSC" / "gsc_bedrock_geology.gdb.zip"


# --------------------------------------------------------------------------
# Built-in code lookups (confirmed from the Ottawa export preview + summary).
# Real _code_*.csv files, if present, override/extend these at load time.
# Keys are stored both zero-padded ("05") and bare ("5").
# --------------------------------------------------------------------------

BUILTIN = {
    "formation_material": {
        "00": "UNKNOWN TYPE", "01": "FILL", "02": "TOPSOIL", "03": "MUCK",
        "04": "PEAT", "05": "CLAY", "08": "FINE SAND", "09": "MEDIUM SAND",
        "10": "COARSE SAND", "11": "GRAVEL", "12": "STONES",
        "15": "LIMESTONE", "16": "DOLOMITE", "17": "SHALE", "18": "SANDSTONE",
    },
    "water_kind": {
        "1": "FRESH", "2": "SALTY", "3": "SULPHUR", "4": "MINERAL",
        "6": "GAS", "7": "IRON",
    },
    "water_use": {
        "1": "Domestic", "2": "Livestock", "3": "Irrigation", "4": "Industrial",
    },
    "final_status": {
        "1": "Water Supply", "2": "Observation Well", "3": "Test Hole",
        "4": "Recharge Well",
    },
    "colour": {
        "1": "WHITE", "2": "GREY", "3": "BLUE", "4": "GREEN",
    },
    "casing_material": {
        "1": "STEEL", "2": "GALVANIZED", "3": "CONCRETE", "4": "OPEN HOLE",
        "5": "PLASTIC",
    },
    "construct_method": {
        "0": "Not Known", "1": "Cable Tool", "2": "Rotary (Convent.)",
        "3": "Rotary (Reverse)", "4": "Rotary (Air)",
    },
}

# Which _code_*.csv (by table name stem) feeds which lookup.
CODE_FILE = {
    "formation_material": "_code_formation_Material",
    "water_kind": "_code_water_kind",
    "water_use": "_codeWaterUse",
    "final_status": "_code_final_status",
    "colour": "_codeColor",
    "casing_material": "_code_casing_material",
    "construct_method": "_code_construct_method",
}

# lithology bucket -> approximate mid-range thermal conductivity (W/m.K).
# Literature-sourced values live in Data/conductivity_reference.csv (VDI 4640
# Blatt 1:2010 ranges; see conductivity.py + README "Conductivity assumptions &
# sources"); the built-in dict in conductivity.py is only a fallback.
# ESTIMATES from lithology words, not measured.
CONDUCTIVITY_WM, _COND_REF = load_reference()

# decoded material word -> lithology bucket used above.
BUCKET = {
    "limestone": "limestone", "dolomite": "dolostone", "dolostone": "dolostone",
    "sandstone": "sandstone", "shale": "shale", "slate": "shale",
    "granite": "granite", "greenstone": "granite", "quartzite": "granite",
    "gneiss": "gneiss",
    "clay": "clay", "silt": "silt",
    "fine sand": "sand", "medium sand": "sand", "coarse sand": "sand", "sand": "sand",
    "gravel": "gravel", "stones": "gravel", "boulders": "gravel",
    "till": "till", "hardpan": "till", "overburden": "till",
    "fill": "fill", "topsoil": "fill", "muck": "fill", "peat": "fill",
    # full _code_formation_Material table (codes 06-48) additions:
    "quicksand": "sand", "marl": "clay",
    "conglomerate": "sandstone", "greywacke": "sandstone",
    "marble": "limestone", "schist": "gneiss", "quartz": "granite",
    "basalt": "basalt", "gypsum": "shale", "chert": "granite",
    "feldspar": "granite", "flint": "granite", "soapstone": "gneiss",
    "rock": "rock",
}

BEDROCK = {"limestone", "dolostone", "sandstone", "shale", "granite", "gneiss",
           "basalt", "rock"}

# Length units -> metres; rate units -> litres/min.
LEN_TO_M = {"ft": 0.3048, "m": 1.0, "cm": 0.01, "inch": 0.0254, "in": 0.0254}
RATE_TO_LPM = {"gpm": 3.785411784, "igpm": 4.54609, "lpm": 1.0, "l/min": 1.0}


# --------------------------------------------------------------------------
# Table loading (CSV folder or .mdb)
# --------------------------------------------------------------------------

class Source:
    def __init__(self, path: Path):
        self.path = path
        self.is_mdb = path.is_file() and path.suffix.lower() in (".mdb", ".accdb")
        if self.is_mdb:
            try:
                import pandas_access as mdb
            except ImportError:
                sys.exit("Reading a .mdb needs: pip install pandas_access (+ system mdbtools). "
                         "Or export the tables to CSV and point --access at the folder.")
            self._mdb = mdb
            self._store = {t.lower(): t for t in mdb.list_tables(str(path))}
        else:
            if not path.is_dir():
                sys.exit(f"--access must be a .mdb file or a folder of CSVs: {path}")
            self._store = {p.stem.lower(): p for p in path.glob("*.csv")}

    def _resolve(self, name):
        key = name.lower()
        for c in (key, key + "_ottawa"):
            if c in self._store:
                return self._store[c]
        for k, v in self._store.items():          # loose prefix match
            if k.startswith(key):
                return v
        return None

    def table(self, name, required=False):
        found = self._resolve(name)
        if found is None:
            if required:
                sys.exit(f"  [table] {name}: NOT FOUND (required)")
            return None
        if self.is_mdb:
            df = self._mdb.read_table(str(self.path), found)
            df.columns = [str(c) for c in df.columns]
        else:
            df = pd.read_csv(found, dtype=str, low_memory=False)
        print(f"  [table] {name}: {len(df):,} rows")
        return df


def col(df, *names):
    """First matching column name, case-insensitive."""
    lower = {c.lower(): c for c in df.columns}
    for n in names:
        if n.lower() in lower:
            return lower[n.lower()]
    return None


# --------------------------------------------------------------------------
# Lookups
# --------------------------------------------------------------------------

def _norm_key(code):
    s = str(code).strip()
    return s.zfill(2) if s.isdigit() else s


def load_lookups(src: Source) -> dict:
    lut = {}
    for key, builtin in BUILTIN.items():
        table = {}
        for c, d in builtin.items():
            table[_norm_key(c)] = d
        df = src.table(CODE_FILE[key])          # real _code_* overrides builtin
        if df is not None:
            code_c = col(df, "CODE", "code", df.columns[0])
            des_c = col(df, "DES", "DESCRIPTION", "des", "name", df.columns[1])
            n = 0
            for _, r in df.iterrows():
                if pd.isna(r[code_c]):
                    continue
                desc = str(r[des_c]).strip()
                if not desc or desc.lower() == "nan":   # e.g. final_status code 0: blank DES
                    desc = "Not specified"
                if desc == "Commerical":          # typo in the source _codeWaterUse table
                    desc = "Commercial"
                table[_norm_key(r[code_c])] = desc
                n += 1
            print(f"    -> {key}: loaded {n} codes from {CODE_FILE[key]}")
        else:
            print(f"    -> {key}: using {len(table)} built-in codes "
                  f"(export {CODE_FILE[key]}.csv for the full list)")
        lut[key] = table
    return lut


def decode(code, table):
    if code is None or (isinstance(code, float) and pd.isna(code)):
        return None
    s = str(code).strip()
    if s == "" or s.lower() == "nan":
        return None
    hit = table.get(_norm_key(s)) or table.get(s)
    return hit if hit is not None else f"code:{s}"


def to_bucket(material):
    if not material or pd.isna(material):
        return "unknown"
    m = str(material).lower()
    for word, bucket in BUCKET.items():
        if word in m:
            return bucket
    return "unknown"


# --------------------------------------------------------------------------
# Unit conversion (vectorised, per-row UOM)
# --------------------------------------------------------------------------

def num(series):
    return pd.to_numeric(series, errors="coerce")


def to_metres(value_col, uom_col):
    v = num(value_col)
    factor = uom_col.astype(str).str.strip().str.lower().map(LEN_TO_M) if uom_col is not None else 1.0
    if uom_col is not None:
        factor = factor.fillna(0.3048)          # WWIS default is feet
    return v * factor


def to_lpm(value_col, uom_col):
    v = num(value_col)
    if uom_col is None:
        return v * 3.785411784                  # assume GPM
    factor = uom_col.astype(str).str.strip().str.lower().map(RATE_TO_LPM).fillna(3.785411784)
    return v * factor


# --------------------------------------------------------------------------
# Layer builders
# --------------------------------------------------------------------------

def build_formations(src, lut):
    df = src.table("tblFormation", required=True)
    top, bot, uom = col(df, "FORMATION_TOP_DEPTH"), col(df, "FORMATION_END_DEPTH"), col(df, "FORMATION_END_DEPTH_UOM")
    out = pd.DataFrame({
        "WELL_ID": df[col(df, "WELL_ID")].astype(str).str.strip(),
        "layer": num(df[col(df, "LAYER")]) if col(df, "LAYER") else None,
        "top_depth_m": to_metres(df[top], df[uom]) if top else None,
        "bottom_depth_m": to_metres(df[bot], df[uom]) if bot else None,
        "material1": df[col(df, "MAT1")].map(lambda x: decode(x, lut["formation_material"])) if col(df, "MAT1") else None,
        "material2": df[col(df, "MAT2")].map(lambda x: decode(x, lut["formation_material"])) if col(df, "MAT2") else None,
        "material3": df[col(df, "MAT3")].map(lambda x: decode(x, lut["formation_material"])) if col(df, "MAT3") else None,
        "colour": df[col(df, "COLOR")].map(lambda x: decode(x, lut["colour"])) if col(df, "COLOR") else None,
    })
    out["lithology"] = out["material1"].map(to_bucket)
    out["thermal_conductivity_wm"] = out["lithology"].map(CONDUCTIVITY_WM)
    return out


def build_water(src, lut):
    df = src.table("tblWater")
    if df is None:
        return None
    d, u = col(df, "WATER_FOUND_DEPTH"), col(df, "WATER_FOUND_DEPTH_UOM")
    return pd.DataFrame({
        "WELL_ID": df[col(df, "WELL_ID")].astype(str).str.strip(),
        "water_found_depth_m": to_metres(df[d], df[u]) if d else None,
        "water_kind": df[col(df, "kind", "KIND")].map(lambda x: decode(x, lut["water_kind"])) if col(df, "kind", "KIND") else None,
    })


def build_pump_tests(src):
    df = src.table("tblPump_Test")
    if df is None:
        return None
    lu, ru = col(df, "LEVELS_UOM"), col(df, "RATE_UOM")
    stat, fin = col(df, "Static_lev", "STATIC_LEV"), col(df, "Final_lev_after_pumping")
    pr, fr = col(df, "Pumping_rate", "PUMPING_RATE"), col(df, "Flowing_rate", "FLOWING_RATE")
    hr, mn = col(df, "PUMPING_DURATION_HR"), col(df, "PUMPING_DURATION_MIN")
    dur = (num(df[hr]).fillna(0) * 60 if hr else 0) + (num(df[mn]).fillna(0) if mn else 0)
    return pd.DataFrame({
        "WELL_ID": df[col(df, "WELL_ID")].astype(str).str.strip(),
        "static_level_m": to_metres(df[stat], df[lu]) if stat else None,
        "final_level_m": to_metres(df[fin], df[lu]) if fin else None,
        "pump_rate_lpm": to_lpm(df[pr], df[ru]) if pr else None,
        "flowing_rate_lpm": to_lpm(df[fr], df[ru]) if fr else None,
        "duration_min": dur if isinstance(dur, pd.Series) else None,
    })


def build_construction(src, lut):
    parts = []

    casing = src.table("tblCasing")
    if casing is not None:
        u = col(casing, "CASING_DEPTH_UOM")
        parts.append(pd.DataFrame({
            "WELL_ID": casing[col(casing, "WELL_ID")].astype(str).str.strip(),
            "element": "casing",
            "depth_from_m": to_metres(casing[col(casing, "DEPTH_FROM")], casing[u]) if col(casing, "DEPTH_FROM") else None,
            "depth_to_m": to_metres(casing[col(casing, "DEPTH_TO")], casing[u]) if col(casing, "DEPTH_TO") else None,
            "diameter": num(casing[col(casing, "CASING_DIAMETER")]) if col(casing, "CASING_DIAMETER") else None,
            "material": casing[col(casing, "MATERIAL")].map(lambda x: decode(x, lut["casing_material"])) if col(casing, "MATERIAL") else None,
        }))

    screen = src.table("tblScreen")
    if screen is not None:
        u = col(screen, "SCRN_DEPTH_UOM")
        parts.append(pd.DataFrame({
            "WELL_ID": screen[col(screen, "WELL_ID")].astype(str).str.strip(),
            "element": "screen",
            "depth_from_m": to_metres(screen[col(screen, "SCRN_TOP_DEPTH")], screen[u]) if col(screen, "SCRN_TOP_DEPTH") else None,
            "depth_to_m": to_metres(screen[col(screen, "SCRN_END_DEPTH")], screen[u]) if col(screen, "SCRN_END_DEPTH") else None,
            "diameter": num(screen[col(screen, "SCRN_DIAMETER")]) if col(screen, "SCRN_DIAMETER") else None,
            "material": screen[col(screen, "SCRN_MATERIAL")] if col(screen, "SCRN_MATERIAL") else None,
        }))

    hole = src.table("tblHole")
    if hole is not None:
        u = col(hole, "HOLE_DEPTH_UOM")
        parts.append(pd.DataFrame({
            "WELL_ID": hole[col(hole, "WELL_ID")].astype(str).str.strip(),
            "element": "hole",
            "depth_from_m": to_metres(hole[col(hole, "Depth_from", "DEPTH_FROM")], hole[u]) if col(hole, "Depth_from", "DEPTH_FROM") else None,
            "depth_to_m": to_metres(hole[col(hole, "Depth_to", "DEPTH_TO")], hole[u]) if col(hole, "Depth_to", "DEPTH_TO") else None,
            "diameter": num(hole[col(hole, "Diameter", "DIAMETER")]) if col(hole, "Diameter", "DIAMETER") else None,
            "material": None,
        }))

    return pd.concat(parts, ignore_index=True) if parts else None


# --------------------------------------------------------------------------
# Wells (one row per well) with geometry + depths from the shapefile
# --------------------------------------------------------------------------

def read_shapefile(shp_path: Path) -> gpd.GeoDataFrame:
    print(f"  [shp] reading {shp_path} (this is the full-Ontario file, ~1M rows)")
    shp = gpd.read_file(shp_path)
    wid = col(shp, "WELL_ID", "WELLID")
    keep = {wid: "WELL_ID"}
    for logical, *aliases in [("depth_m", "DEPTH"),
                              ("bedrock_depth_m", "DP_BEDROCK"),
                              ("static_level_m", "STATIC_LEV"),
                              ("date_completed", "COMPLETED")]:
        c = col(shp, *aliases)
        if c:
            keep[c] = logical
    shp = shp[list(keep) + ["geometry"]].rename(columns=keep)
    shp = shp.to_crs(4326)
    shp["WELL_ID"] = shp["WELL_ID"].astype(str).str.strip()
    for c in ("depth_m", "bedrock_depth_m", "static_level_m"):
        if c in shp:
            shp[c] = num(shp[c])
    return shp.drop_duplicates("WELL_ID")


def load_borehole_coords(src) -> pd.DataFrame | None:
    """WELL_ID -> lon/lat recovered from tblBore_Hole's ZONE/EAST83/NORTH83
    (NAD83 UTM) for wells the shapefile has no geometry for."""
    df = src.table("tblBore_Hole")
    if df is None:
        return None
    wid, zone, east, north = (col(df, "WELL_ID"), col(df, "ZONE"),
                              col(df, "EAST83"), col(df, "NORTH83"))
    if not (wid and zone and east and north):
        return None
    out = pd.DataFrame({
        "WELL_ID": df[wid].astype(str).str.strip(),
        "ZONE": num(df[zone]),
        "EAST83": num(df[east]),
        "NORTH83": num(df[north]),
    }).dropna(subset=["ZONE", "EAST83", "NORTH83"])
    out = out[out["ZONE"].astype(int).isin(UTM_EPSG)].drop_duplicates("WELL_ID")
    return out


def load_gsc_geology(path: Path):
    """GSC national bedrock geology, bucketed to combine_wells.py's lithology
    buckets and reprojected to 4326. Returns None if the file is missing."""
    if not path.exists():
        return None
    gdf = gpd.read_file(path, layer="Wheeler_Bedrock")

    def bucket_row(r):
        st = str(r.get("SUBRXTP") or "").strip().lower()
        if st in GSC_SUBRXTP_BUCKET:
            return GSC_SUBRXTP_BUCKET[st]
        rt = str(r.get("RXTP") or "").strip().lower()
        return GSC_RXTP_BUCKET.get(rt)

    gdf["gsc_bucket"] = gdf.apply(bucket_row, axis=1)
    gdf = gdf[gdf["gsc_bucket"].notna()][["gsc_bucket", "geometry"]].to_crs(4326)
    print(f"  [gsc] {path.name}: {len(gdf):,} mapped polygons bucketed "
          f"(of the national layer)")
    return gdf


def gsc_lithology_lookup(gsc_gdf, wells_needing_lith: gpd.GeoDataFrame) -> dict:
    """WELL_ID -> GSC-mapped lithology bucket, for wells with geometry but no
    well-log-derived lithology, via point-in-polygon spatial join."""
    if gsc_gdf is None or wells_needing_lith.empty:
        return {}
    joined = gpd.sjoin(wells_needing_lith[["WELL_ID", "geometry"]], gsc_gdf,
                       how="left", predicate="within")
    joined = joined.dropna(subset=["gsc_bucket"]).drop_duplicates("WELL_ID")
    return dict(zip(joined["WELL_ID"], joined["gsc_bucket"]))


def build_wells(src, lut, shp, formations, water, pump_tests):
    wwr = src.table("tblWWR", required=True)
    use1 = (wwr[col(wwr, "USE_1ST")].map(lambda x: decode(x, lut["water_use"]))
            if col(wwr, "USE_1ST") else pd.Series([None] * len(wwr)))
    if col(wwr, "USE_2ND"):
        use2 = wwr[col(wwr, "USE_2ND")].map(lambda x: decode(x, lut["water_use"]))
        well_use = use1.fillna(use2)
        print(f"  [wells] well_use: recovered {(use1.isna() & well_use.notna()).sum():,} "
              f"from USE_2ND fallback")
    else:
        well_use = use1
    wells = pd.DataFrame({
        "WELL_ID": wwr[col(wwr, "WELL_ID")].astype(str).str.strip(),
        "county": wwr[col(wwr, "COUNTY")] if col(wwr, "COUNTY") else None,
        "well_use": well_use,
        "status": wwr[col(wwr, "FINAL_STA")].map(lambda x: decode(x, lut["final_status"])) if col(wwr, "FINAL_STA") else None,
    }).drop_duplicates("WELL_ID")

    # geometry + authoritative metric depths from the shapefile
    wells = wells.merge(shp, on="WELL_ID", how="left")
    wells["geometry_source"] = np.where(wells["geometry"].notna(), "shp", None)

    # ---- geometry recovery from tblBore_Hole (ZONE/EAST83/NORTH83, NAD83 UTM)
    bh = load_borehole_coords(src)
    if bh is not None:
        missing = wells.loc[wells["geometry"].isna(), ["WELL_ID"]]
        cand = missing.merge(bh, on="WELL_ID", how="inner")
        recovered = {}
        for zone, grp in cand.groupby("ZONE"):
            pts = gpd.GeoSeries(gpd.points_from_xy(grp["EAST83"], grp["NORTH83"]),
                                crs=UTM_EPSG[int(zone)]).to_crs(4326)
            recovered.update(dict(zip(grp["WELL_ID"], pts)))
        if recovered:
            hit = wells["WELL_ID"].isin(recovered)
            wells.loc[hit, "geometry"] = wells.loc[hit, "WELL_ID"].map(recovered)
            wells.loc[hit, "geometry_source"] = "borehole"
        print(f"  [wells] geometry: recovered {len(recovered):,} of {len(missing):,} "
              f"missing-geometry wells from tblBore_Hole")

    # ---- formation-derived per-well fields
    f = formations.dropna(subset=["WELL_ID"]).copy()
    f["_thick"] = f["bottom_depth_m"] - f["top_depth_m"]
    f = f.sort_values(["WELL_ID", "top_depth_m"])

    def summarise(g):
        bits = []
        for _, r in g.iterrows():
            mat = r["material1"] or "?"
            if pd.notna(r["top_depth_m"]) and pd.notna(r["bottom_depth_m"]):
                bits.append(f"{mat} {r['top_depth_m']:.1f}-{r['bottom_depth_m']:.1f}m")
            else:
                bits.append(str(mat))
        return " / ".join(bits[:10])

    try:                                          # include_groups kwarg is pandas >=2.2
        summary = f.groupby("WELL_ID").apply(summarise, include_groups=False)
    except TypeError:
        summary = f.groupby("WELL_ID").apply(summarise)
    summary = summary.rename("formation_summary")

    # thickest *bucketable* layer; a well whose thickest layer has no material
    # recorded still gets a lithology from its other layers
    fk = f[f["lithology"] != "unknown"]
    primary = (fk.sort_values("_thick", ascending=False)
                 .drop_duplicates("WELL_ID").set_index("WELL_ID")["lithology"]
                 .rename("primary_lithology"))

    fb = f[f["lithology"].isin(BEDROCK)]
    bedrock_lith = (fb.sort_values("_thick", ascending=False)
                      .drop_duplicates("WELL_ID").set_index("WELL_ID")["lithology"]
                      .rename("bedrock_lithology"))
    bedrock_top = fb.groupby("WELL_ID")["top_depth_m"].min().rename("bedrock_depth_formations")

    wells = (wells.merge(summary, on="WELL_ID", how="left")
                  .merge(primary, on="WELL_ID", how="left")
                  .merge(bedrock_lith, on="WELL_ID", how="left")
                  .merge(bedrock_top, on="WELL_ID", how="left"))

    # ---- bedrock depth fallback: shapefile DP_BEDROCK is authoritative;
    # where null, use the shallowest bedrock-bucket formation interval
    wells["bedrock_depth_source"] = np.where(wells["bedrock_depth_m"].notna(), "shp", None)
    both = wells[wells["bedrock_depth_m"].notna() & wells["bedrock_depth_formations"].notna()]
    if not both.empty:
        diff = (both["bedrock_depth_m"] - both["bedrock_depth_formations"]).abs()
        print(f"  [wells] bedrock depth: median |shp - formations| = {diff.median():.2f} m "
              f"(n={len(both):,} wells with both)")
    fill = wells["bedrock_depth_m"].isna() & wells["bedrock_depth_formations"].notna()
    wells.loc[fill, "bedrock_depth_m"] = wells.loc[fill, "bedrock_depth_formations"]
    wells.loc[fill, "bedrock_depth_source"] = "formations"
    print(f"  [wells] bedrock_depth_m: recovered {fill.sum():,} from formations fallback")
    wells = wells.drop(columns=["bedrock_depth_formations"])

    # ---- pump-test-derived yield (max pumping rate per well)
    if pump_tests is not None:
        y = pump_tests.groupby("WELL_ID")["pump_rate_lpm"].max().rename("well_yield_lpm")
        wells = wells.merge(y, on="WELL_ID", how="left")
    else:
        wells["well_yield_lpm"] = pd.NA

    # ---- derived screening fields (summary section 6)
    cond_source = wells["bedrock_lithology"].fillna(wells["primary_lithology"])

    # lithology fallback: for wells with no well-log lithology but real
    # geometry, spatial-join to the GSC mapped bedrock geology (weaker
    # evidence than a well log -- flagged via lithology_source)
    gsc = load_gsc_geology(GSC_GDB)
    need = cond_source.isna() & wells["geometry"].notna()
    gsc_map = {}
    if need.any():
        subset = gpd.GeoDataFrame(wells.loc[need, ["WELL_ID"]],
                                  geometry=wells.loc[need, "geometry"], crs=4326)
        gsc_map = gsc_lithology_lookup(gsc, subset)
        print(f"  [wells] lithology: recovered {len(gsc_map):,} of {need.sum():,} "
              f"unknown-lithology wells from GSC mapped geology")
    gsc_lith = wells["WELL_ID"].map(gsc_map)

    final_lithology = cond_source.fillna(gsc_lith)
    wells["lithology_source"] = None
    wells.loc[cond_source.notna(), "lithology_source"] = "well_log"
    wells.loc[cond_source.isna() & gsc_lith.notna(), "lithology_source"] = "gsc_map"

    wells["lithology"] = final_lithology.fillna("unknown")   # well_log, else gsc_map, else unknown
    wells["estimated_conductivity_wm"] = final_lithology.map(CONDUCTIVITY_WM)
    wells["estimated_conductivity_class"] = wells["estimated_conductivity_wm"].map(
        lambda v: "unknown" if pd.isna(v) else ("low" if v < 2.0 else ("medium" if v <= 2.8 else "high")))
    wells["bedrock_indicator"] = wells["bedrock_lithology"].notna() | wells.get("bedrock_depth_m").notna()
    has_water = water is not None and not water.empty
    water_ids = set(water["WELL_ID"]) if has_water else set()
    wells["groundwater_indicator"] = wells.get("static_level_m").notna() | wells["WELL_ID"].isin(water_ids)

    # open-loop screen (kept consistent with the existing guide pipeline)
    def open_loop(r):
        swl = r.get("static_level_m")
        y = r.get("well_yield_lpm")
        if pd.notna(swl) and pd.notna(y) and y >= 15:
            return "viable"
        if pd.notna(swl):
            return "possible"
        return "unlikely"
    wells["open_loop"] = wells.apply(open_loop, axis=1)

    gdf = gpd.GeoDataFrame(wells, geometry="geometry", crs=4326)
    no_geom = gdf.geometry.isna().sum()
    print(f"  [wells] {len(gdf):,} wells; {no_geom:,} without shapefile geometry")
    return gdf


# --------------------------------------------------------------------------
# Write
# --------------------------------------------------------------------------

def write_table_layer(df, out, layer):
    """Non-spatial layer -> geometry-less GPKG layer."""
    gdf = gpd.GeoDataFrame(df.copy(), geometry=[None] * len(df), crs=4326)
    gdf.to_file(out, layer=layer, driver="GPKG")


def main():
    here = Path(__file__).resolve().parents[1]        # Geothermal/
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--access", type=Path, default=here / "Data",
                    help="folder of tbl*_Ottawa.csv (and optional _code_*.csv), or a .mdb")
    ap.add_argument("--shp", type=Path, default=here / "Data" / "wwis_out.shp")
    ap.add_argument("--out", type=Path, default=here / "Data" / "processed" / "ottawa_geothermal.gpkg")
    args = ap.parse_args()

    src = Source(args.access)

    print("\n== Lookup tables ==")
    lut = load_lookups(src)

    print("\n== Building relational layers ==")
    formations = build_formations(src, lut)
    water = build_water(src, lut)
    pump_tests = build_pump_tests(src)
    construction = build_construction(src, lut)

    print("\n== Wells layer (+ shapefile geometry) ==")
    shp = read_shapefile(args.shp)
    wells = build_wells(src, lut, shp, formations, water, pump_tests)

    print("\n== Writing GeoPackage ==")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    if args.out.exists():
        args.out.unlink()
    wells.to_file(args.out, layer="wells", driver="GPKG")
    for name, df in [("formations", formations), ("water", water),
                     ("pump_tests", pump_tests), ("construction", construction)]:
        if df is None or df.empty:
            print(f"  skip empty layer: {name}")
            continue
        write_table_layer(df, args.out, name)

    print(f"\nDone -> {args.out}")
    for name, df in [("wells", wells), ("formations", formations), ("water", water),
                     ("pump_tests", pump_tests), ("construction", construction)]:
        print(f"  {name:13} {0 if df is None else len(df):>8,}")
    # quick geothermal readout
    vc = wells["estimated_conductivity_class"].value_counts(dropna=False)
    print("\n  conductivity class:", dict(vc))
    print("  open_loop:", dict(wells["open_loop"].value_counts()))


if __name__ == "__main__":
    main()
