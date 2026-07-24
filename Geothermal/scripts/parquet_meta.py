"""
parquet_meta.py

Shared writer for the heat-demand pipeline's shared parquet
(Data/processed/buildings_ottawa.parquet), which every phase augments IN PLACE.

Each phase stamps its methodology note into the parquet's custom schema
metadata under a `heatdemand_phaseN` key. geopandas does NOT round-trip custom
schema metadata through the GeoDataFrame: gpd.read_parquet() drops it, so a
later gdf.to_parquet() writes a fresh schema and every key not explicitly
re-attached is silently destroyed -- the file still loads and the columns still
look fine, only the provenance is gone. Each phase must therefore carry its
predecessors' notes forward, and phases can be re-run in any order.

write_with_meta() is that carry-forward, in one place, so a new phase gets it
by construction rather than by remembering.
"""

import json
from pathlib import Path

import pyarrow.parquet as pq

# Custom metadata keys under this prefix are pipeline provenance and are
# preserved across every phase's rewrite.
META_PREFIX = b"heatdemand_"


def write_with_meta(gdf, path, key, meta):
    """Write `gdf` to `path`, stamping `meta` under `key` and preserving the
    heatdemand_* notes any earlier phase left on the existing file.

    key  -- phase key, with or without the heatdemand_ prefix ("phase2").
    meta -- JSON-serialisable dict; the phase's methodology note.

    Returns the sorted list of heatdemand_* keys present on the written file.
    """
    path = Path(path)
    full_key = key.encode() if isinstance(key, str) else key
    if not full_key.startswith(META_PREFIX):
        full_key = META_PREFIX + full_key

    # Read the EXISTING notes before rewriting -- to_parquet() below discards them.
    prior = {}
    if path.exists():
        prior = {k: v for k, v in (pq.read_schema(path).metadata or {}).items()
                 if k.startswith(META_PREFIX)}

    gdf.to_parquet(path)

    t = pq.read_table(path)
    md = dict(t.schema.metadata or {})   # geo metadata from the fresh write
    md.update(prior)                     # upstream phases' notes
    md[full_key] = json.dumps(meta).encode()
    pq.write_table(t.replace_schema_metadata(md), path)

    return sorted(k.decode() for k in md if k.startswith(META_PREFIX))
