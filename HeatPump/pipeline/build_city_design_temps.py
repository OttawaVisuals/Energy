"""
City design temperatures from the HOT2000 weather station each ERS home
actually used (heat-pump tool, load-model rebuild step 1).

WHY THIS EXISTS
---------------
`build_archetypes.py` backs UA out of `EGHDESHTLOSS` using a *proxy* design
temperature: the 2.5th-percentile January temperature from our own 2019-2026
ECCC record, one value per city. But `EGHDESHTLOSS` was computed by HOT2000 at
the design temperature of the home's own weather station, from HOT2000's
weather library -- a different quantity, off by ~2-4 C on spot-check.

The raw ERS CSVs carry `WEATHERLOC` (the station) and `WTHDATA` (the library
version), so the real design temperature is recoverable. This step recovers it.

INPUTS
------
  C:\\ERS\\*.csv                      raw ERS year files (HOUSEID, CLIENTCITY,
                                      WEATHERLOC, WTHDATA)
  C:\\ERS\\web\\ers_web_*.parquet     the retrofit-page universe (HOUSEID) --
                                      defines which homes count
  ../reference/nbc_station_design_temps.csv
                                      station -> NBC Appendix C design heating
                                      dry-bulb, with match provenance

OUTPUTS
-------
  ../data/processed/city_design_temps.json   city -> design temp + provenance
  ../data/interim/city_design_temps.csv      same, flat
  ../data/interim/houseid_city.parquet       HOUSEID -> city/station cache, so
                                             the 7.7 GB raw scan runs once

METHOD
------
1. Universe = every HOUSEID in the web parquets (paired, gated homes).
2. One pass over the raw year files, first-hit-wins per HOUSEID (a home
   re-evaluated in a later year keeps its earliest station).
3. `CLIENTCITY` is operator-entered free text: fold accents/mojibake and
   punctuation, then roll municipalities up into metro areas via the explicit
   CITY_MEMBERS table below.
4. Design temperature per city = the HOUSE-WEIGHTED MEAN of the NBC design
   temperature of whatever station each home actually used -- not the modal
   station's value. Homes inside one city spread across many stations (Toronto:
   55 stations, top one only 42%), so the mode is not representative.

DATA HONESTY
------------
Nothing is silently dropped. The output records, per city: how many homes, how
many distinct stations, the modal station and its share, the min-max spread of
design temperatures, and the NBC name-match provenance (`matched_via`). Homes
whose CLIENTCITY maps to no listed city are counted and reported, not discarded
quietly. `CITY_MEMBERS` is a judgement call, written out in full so it can be
argued with.

KNOWN LIMITATIONS
-----------------
- The NBC table is joined by station NAME. Across the retrofit universe only
  ~53% of homes match `exact`; the rest go through alias/prefix/proxy matches
  (the two largest stations, ~19% of homes, are `alias:nearest` and
  `alias:downtown approx`). `matched_via` is carried through so this is visible.
- `WTHDATA` shows only ~35% of homes were modelled on the `Wth2020` library;
  56% are on `WTH100` and 8% on `Wth110`. We hold one NBC-vintage design
  temperature per station and apply it to all of them. Library revisions
  typically move a station by 1-2 C, which propagates to roughly 2-3% on peak
  load (see METHODOLOGY.md "Design-temperature sensitivity").
- The percentile behind `design_heating_db_C` (NBC 1% vs 2.5% January) is not
  stated in the source file; value-matching against published NBC figures
  indicates 2.5%. Confirm before citing.
"""

import glob
import json
import os
import re
import unicodedata
from collections import Counter

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
NBC_CSV = os.path.join(ROOT, "reference", "nbc_station_design_temps.csv")
CACHE = os.path.join(ROOT, "data", "interim", "houseid_city.parquet")
OUT_JSON = os.path.join(ROOT, "data", "processed", "city_design_temps.json")
OUT_CSV = os.path.join(ROOT, "data", "interim", "city_design_temps.csv")

ERS_RAW_GLOB = r"C:\ERS\*.csv"
ERS_WEB_GLOB = r"C:\ERS\web\ers_web_*.parquet"
CHUNK = 250_000
WANT = ["HOUSEID", "CLIENTCITY", "WEATHERLOC", "WTHDATA"]

# Metro area -> member municipality names as they appear in CLIENTCITY, in
# folded form (accents stripped, no periods/apostrophes, upper case).
# Judgement call, deliberately explicit. Ordered roughly by size.
CITY_MEMBERS = {
    "Toronto": ["TORONTO", "MISSISSAUGA", "BRAMPTON", "MARKHAM", "SCARBOROUGH",
                "VAUGHAN", "RICHMOND HILL", "OAKVILLE", "BURLINGTON", "OSHAWA",
                "WHITBY", "AJAX", "PICKERING", "NORTH YORK", "ETOBICOKE",
                "THORNHILL", "MILTON", "NEWMARKET", "AURORA", "WOODBRIDGE",
                "MAPLE", "GEORGETOWN", "STOUFFVILLE", "BOWMANVILLE", "CALEDON",
                "COURTICE", "BOLTON", "UNIONVILLE", "KESWICK", "YORK",
                "EAST YORK", "CONCORD", "KLEINBURG", "NOBLETON"],
    "Montreal": ["MONTREAL", "LAVAL", "LONGUEUIL", "TERREBONNE", "REPENTIGNY",
                 "BROSSARD", "BLAINVILLE", "BOUCHERVILLE", "CHATEAUGUAY",
                 "MASCOUCHE", "SAINT-EUSTACHE", "MIRABEL", "POINTE-CLAIRE",
                 "SAINTE-JULIE", "BEACONSFIELD", "BOISBRIAND", "LASALLE",
                 "SAINT-JEROME", "VERDUN", "DOLLARD-DES-ORMEAUX", "KIRKLAND",
                 "SAINT-LAURENT", "ANJOU", "LACHINE", "SAINT-LEONARD"],
    "Ottawa-Gatineau": ["OTTAWA", "GATINEAU", "NEPEAN", "ORLEANS", "KANATA",
                        "GLOUCESTER", "STITTSVILLE", "HULL", "AYLMER",
                        "BARRHAVEN", "ROCKLAND", "MANOTICK"],
    "Vancouver": ["VANCOUVER", "SURREY", "RICHMOND", "BURNABY", "COQUITLAM",
                  "DELTA", "LANGLEY", "NORTH VANCOUVER", "MAPLE RIDGE",
                  "PORT COQUITLAM", "WEST VANCOUVER", "NEW WESTMINSTER",
                  "PORT MOODY", "WHITE ROCK", "PITT MEADOWS"],
    "London": ["LONDON", "ST THOMAS", "STRATHROY", "DORCHESTER"],
    "Calgary": ["CALGARY", "AIRDRIE", "COCHRANE", "CHESTERMERE", "OKOTOKS"],
    "Kitchener-Waterloo": ["KITCHENER", "WATERLOO", "CAMBRIDGE", "ELMIRA", "AYR"],
    "Hamilton": ["HAMILTON", "STONEY CREEK", "DUNDAS", "ANCASTER", "WATERDOWN",
                 "GRIMSBY", "BINBROOK", "FLAMBOROUGH"],
    "Quebec City": ["QUEBEC", "LEVIS", "STE-FOY", "SAINTE-FOY", "BEAUPORT",
                    "CHARLESBOURG", "SAINT-AUGUSTIN-DE-DESMAURES",
                    "ANCIENNE-LORETTE"],
    "Edmonton": ["EDMONTON", "SHERWOOD PARK", "ST ALBERT", "SPRUCE GROVE",
                 "LEDUC", "FORT SASKATCHEWAN", "STONY PLAIN", "BEAUMONT"],
    "Windsor": ["WINDSOR", "TECUMSEH", "AMHERSTBURG", "LEAMINGTON",
                "KINGSVILLE", "ESSEX"],
    "Winnipeg": ["WINNIPEG", "STEINBACH", "SELKIRK"],
    "Halifax": ["HALIFAX", "DARTMOUTH", "LOWER SACKVILLE", "BEDFORD",
                "SACKVILLE", "COLE HARBOUR", "TANTALLON"],
    "St. Catharines-Niagara": ["ST CATHARINES", "NIAGARA FALLS", "WELLAND",
                               "FORT ERIE", "THOROLD", "PORT COLBORNE",
                               "NIAGARA-ON-THE-LAKE"],
    "Victoria": ["VICTORIA", "SAANICH", "SIDNEY", "SOOKE", "COLWOOD",
                 "LANGFORD", "ESQUIMALT", "OAK BAY"],
    "Saskatoon": ["SASKATOON", "WARMAN", "MARTENSVILLE"],
    "Moncton": ["MONCTON", "DIEPPE", "RIVERVIEW", "SHEDIAC"],
    "Regina": ["REGINA", "WHITE CITY"],
    "Guelph": ["GUELPH", "FERGUS", "ROCKWOOD"],
    "Trois-Rivieres": ["TROIS-RIVIERES", "SHAWINIGAN", "BECANCOUR"],
    "Barrie": ["BARRIE", "INNISFIL", "ORILLIA", "ALLISTON"],
    "Sherbrooke": ["SHERBROOKE", "MAGOG", "LENNOXVILLE"],
    "Saguenay": ["SAGUENAY", "CHICOUTIMI", "JONQUIERE", "ALMA"],
    "Brantford": ["BRANTFORD", "PARIS"],
    "Saint John": ["SAINT JOHN", "QUISPAMSIS", "ROTHESAY", "GRAND BAY-WESTFIELD"],
    "Kingston": ["KINGSTON", "AMHERSTVIEW", "NAPANEE"],
    "Chatham-Kent": ["CHATHAM", "WALLACEBURG", "TILBURY", "BLENHEIM"],
    "Cape Breton": ["SYDNEY", "GLACE BAY", "NORTH SYDNEY", "SYDNEY MINES",
                    "NEW WATERFORD"],
    "Sarnia": ["SARNIA", "POINT EDWARD", "CORUNNA"],
    "Kelowna": ["KELOWNA", "WEST KELOWNA", "PEACHLAND", "LAKE COUNTRY"],
    "Nanaimo": ["NANAIMO", "LANTZVILLE", "PARKSVILLE", "QUALICUM BEACH"],
    "Fredericton": ["FREDERICTON", "OROMOCTO", "NEW MARYLAND"],
    "Woodstock": ["WOODSTOCK", "INGERSOLL", "TILLSONBURG"],
    "Thunder Bay": ["THUNDER BAY"],
    "Sudbury": ["SUDBURY", "GREATER SUDBURY", "VAL CARON"],
    "St. John's": ["ST JOHNS", "MOUNT PEARL", "PARADISE", "CONCEPTION BAY SOUTH"],
    "Sault Ste. Marie": ["SAULT STE MARIE"],
    "Peterborough": ["PETERBOROUGH", "LAKEFIELD"],
    "Kamloops": ["KAMLOOPS"],
    "Abbotsford-Mission": ["ABBOTSFORD", "MISSION"],
    "Courtenay": ["COURTENAY", "COMOX", "CUMBERLAND"],
    "Stratford": ["STRATFORD", "ST MARYS"],
    "Belleville": ["BELLEVILLE", "TRENTON", "QUINTE WEST"],
    "Prince George": ["PRINCE GEORGE"],
    "Cornwall": ["CORNWALL"],
    "Victoriaville": ["VICTORIAVILLE"],
    "Drummondville": ["DRUMMONDVILLE"],
    "Granby": ["GRANBY"],
    "Lethbridge": ["LETHBRIDGE"],
    "Charlottetown": ["CHARLOTTETOWN"],
    "North Bay": ["NORTH BAY", "CALLANDER"],
    "Saint-Jean-sur-Richelieu": ["SAINT-JEAN-SUR-RICHELIEU"],
    "Chilliwack": ["CHILLIWACK", "SARDIS"],
    "Medicine Hat": ["MEDICINE HAT"],
    "Red Deer": ["RED DEER", "SYLVAN LAKE"],
    "Vernon": ["VERNON", "COLDSTREAM"],
    "Penticton": ["PENTICTON", "SUMMERLAND"],
    "Rimouski": ["RIMOUSKI"],
    "Orangeville": ["ORANGEVILLE", "SHELBURNE"],
    "Owen Sound": ["OWEN SOUND", "MEAFORD"],
    "Truro": ["TRURO", "BIBLE HILL"],
    "Bathurst": ["BATHURST"],
    "Miramichi": ["MIRAMICHI"],
    "Prince Albert": ["PRINCE ALBERT"],
    "Moose Jaw": ["MOOSE JAW"],
    "Brandon": ["BRANDON"],
    "Timmins": ["TIMMINS"],
    "Grande Prairie": ["GRANDE PRAIRIE"],
    "Fort McMurray": ["FORT MCMURRAY", "WOOD BUFFALO"],
    "Saint-Georges": ["SAINT-GEORGES"],
    "Thetford Mines": ["THETFORD MINES"],
    "Duncan": ["DUNCAN", "NORTH COWICHAN"],
    "Campbell River": ["CAMPBELL RIVER"],
    "Salaberry-de-Valleyfield": ["SALABERRY-DE-VALLEYFIELD", "VALLEYFIELD"],
    "Sorel-Tracy": ["SOREL-TRACY", "SOREL"],
    "Saint-Hyacinthe": ["SAINT-HYACINTHE"],
    "Joliette": ["JOLIETTE"],
    "Rouyn-Noranda": ["ROUYN-NORANDA"],
    "Val-d'Or": ["VAL-DOR"],
    "Sept-Iles": ["SEPT-ILES"],
    "Baie-Comeau": ["BAIE-COMEAU"],
    "Matane": ["MATANE"],
    "Yellowknife": ["YELLOWKNIFE"],
    "Whitehorse": ["WHITEHORSE"],
}


def fold(s):
    """Normalise operator-entered free text: mojibake, accents, punctuation."""
    s = str(s).replace("\ufffd", "")
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.upper().strip()
    s = re.sub(r"\s+", " ", s)
    s = s.replace(".", "").replace("'", "")
    return re.sub(r"[,;]+$", "", s)


def build_house_cache():
    """HOUSEID -> (CLIENTCITY, WEATHERLOC, WTHDATA). Cached; scan runs once."""
    if os.path.exists(CACHE):
        print(f"reusing {CACHE}")
        return pd.read_parquet(CACHE)

    universe = set()
    for p in sorted(glob.glob(ERS_WEB_GLOB)):
        universe |= set(pd.read_parquet(p, columns=["HOUSEID"])["HOUSEID"].astype(str))
    print(f"universe: {len(universe):,} matched-pair HOUSEIDs", flush=True)

    seen, frames, skipped = set(), [], []
    for path in sorted(glob.glob(ERS_RAW_GLOB)):
        name = os.path.basename(path)
        head = pd.read_csv(path, encoding="utf-8-sig", nrows=0, low_memory=False)
        cols = [c for c in WANT if c in head.columns]
        if "HOUSEID" not in cols or "WEATHERLOC" not in cols:
            skipped.append(name)
            print(f"{name}: MISSING required columns -- skipped", flush=True)
            continue
        for chunk in pd.read_csv(path, encoding="utf-8-sig", usecols=cols,
                                 dtype=str, chunksize=CHUNK, low_memory=False):
            chunk = chunk[chunk["HOUSEID"].isin(universe) & ~chunk["HOUSEID"].isin(seen)]
            chunk = chunk.drop_duplicates("HOUSEID")
            if chunk.empty:
                continue
            frames.append(chunk)
            seen |= set(chunk["HOUSEID"])
        print(f"{name}: cumulative {len(seen):,}", flush=True)

    out = pd.concat(frames, ignore_index=True)
    os.makedirs(os.path.dirname(CACHE), exist_ok=True)
    out.to_parquet(CACHE, index=False)
    print(f"\nwrote {CACHE} ({len(out):,} rows)")
    print(f"matched {len(seen):,}/{len(universe):,} "
          f"({len(seen)/len(universe)*100:.1f}%); "
          f"UNMATCHED {len(universe)-len(seen):,}")
    if skipped:
        print(f"year files skipped: {skipped}")
    return out


def main():
    print("=== City design temperatures from HOT2000 weather stations ===\n")
    df = build_house_cache()
    total = len(df)

    nbc = pd.read_csv(NBC_CSV)
    design = dict(zip(nbc["WEATHERLOC"], nbc["design_heating_db_C"]))
    via = dict(zip(nbc["WEATHERLOC"], nbc["matched_via"]))

    df["design_C"] = df["WEATHERLOC"].map(design)
    no_temp = int(df["design_C"].isna().sum())
    print(f"\nhomes with no NBC design temperature: {no_temp:,} "
          f"({no_temp/total*100:.2f}%)")

    lib = Counter(df["WTHDATA"].fillna("(blank)"))
    print("HOT2000 weather library mix:")
    for k, v in lib.most_common(5):
        print(f"  {k:<12} {v:>9,}  {v/total*100:5.1f}%")

    df["fold"] = df["CLIENTCITY"].map(fold)
    lookup = {}
    for city, members in CITY_MEMBERS.items():
        for m in members:
            lookup[fold(m)] = city
    df["city"] = df["fold"].map(lookup)

    rows = []
    for city in CITY_MEMBERS:
        sub = df[df["city"] == city]
        if sub.empty:
            continue
        sv = sub["WEATHERLOC"].value_counts()
        top = sv.index[0]
        rows.append({
            "city": city,
            "houses": int(len(sub)),
            "pct_of_universe": round(len(sub) / total * 100, 3),
            "design_temp_C": round(float(sub["design_C"].mean()), 1),
            "design_temp_C_modal_station": design.get(top),
            "top_station": top,
            "top_station_share_pct": round(float(sv.iloc[0] / len(sub) * 100), 1),
            "n_stations": int(sub["WEATHERLOC"].nunique()),
            "design_temp_spread_C": round(float(sub["design_C"].max()
                                                - sub["design_C"].min()), 1),
            "top_station_matched_via": via.get(top, "unknown"),
            "pct_wth2020": round(float((sub["WTHDATA"] == "Wth2020").mean() * 100), 1),
        })

    res = (pd.DataFrame(rows).sort_values("houses", ascending=False)
           .reset_index(drop=True))
    res.insert(0, "rank", res.index + 1)

    assigned = int(res["houses"].sum())
    unassigned = df[df["city"].isna()]
    print(f"\n{len(res)} cities; {assigned:,} homes assigned "
          f"({assigned/total*100:.1f}%)")
    print(f"UNASSIGNED: {len(unassigned):,} ({len(unassigned)/total*100:.1f}%) "
          f"across {unassigned['fold'].nunique():,} distinct names")
    print("\nlargest unassigned names:")
    print(unassigned["fold"].value_counts().head(10).to_string())

    print(f"\n--- top 50 ---\n{res.head(50).to_string(index=False)}")

    os.makedirs(os.path.dirname(OUT_JSON), exist_ok=True)
    os.makedirs(os.path.dirname(OUT_CSV), exist_ok=True)
    res.to_csv(OUT_CSV, index=False, encoding="utf-8-sig")

    payload = {
        "meta": {
            "source_design_temps": "NBC Appendix C climatic design data, joined "
                                   "to HOT2000 WEATHERLOC by station name "
                                   "(reference/nbc_station_design_temps.csv)",
            "percentile": "believed 2.5% January dry-bulb (inferred by "
                          "value-matching published NBC figures; not stated in "
                          "the source file -- confirm before citing)",
            "universe": "ERS matched pre/post pairs reaching the retrofit page",
            "n_homes_universe": total,
            "n_homes_assigned": assigned,
            "n_homes_unassigned": int(len(unassigned)),
            "homes_without_design_temp": no_temp,
            "weather_library_mix": {k: int(v) for k, v in lib.most_common()},
            "method": "house-weighted mean of each home's own station design "
                      "temperature; NOT the modal station's value",
        },
        "cities": {r["city"]: {k: v for k, v in r.items() if k != "city"}
                   for r in res.to_dict("records")},
    }
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)

    print(f"\nwrote {OUT_JSON}")
    print(f"wrote {OUT_CSV}")


if __name__ == "__main__":
    main()
