"""
fsa_json_codec.py

Lossless dictionary encoding for the per-FSA files in fsa_json/.

WHY (decided 2026-11-06): the published site had grown to 1.76 GB, over
GitHub Pages' documented 1 GB limit, and every Pages deploy repackaged all of
it (a 410 MB upload that timed out at 10 minutes on 2026-11-06). fsa_json was
1,113 MB of that. Text columns such as Pre_HeatType, Post_VentType, BldgType
and FSA repeat the same few strings on every one of a file's rows; storing each
distinct string once and an integer code per row cut the largest file
(ON/L3R) to 74% of its size. split_fsa_json.py's docstring records the earlier
decision NOT to do this (files were small then); total size is what changed.

FORMAT — the {columns, rows} array-of-arrays shape is unchanged, plus an
optional "dict" key:

    {"columns": ["FSA", "BldgType", ...],
     "dict":    {"FSA": ["L3R"], "BldgType": ["Row House", "Single Detached"], ...},
     "rows":    [[0, 1, ...], ...]}

  For a column named in "dict", each row cell holds an index into that list
  (or null, which stays null). Other columns are untouched. A file without
  "dict" is a plain, unencoded file, so readers handle both.

  A column is encoded only when every non-null value is a string AND encoding
  makes the file smaller (near-unique strings such as model names stay as-is).
  decode(encode(p)) == p exactly, which main() below checks on every file.

READERS that must call decode() (or mirror it): assets/retrofits.js
reconstructRows(), Python/list_ahri_numbers.py.

USAGE
  Imported by split_fsa_json.py, which encodes each file as it writes it.
  Standalone, to re-encode an existing tree in place (idempotent: already-
  encoded files are skipped; each file is verified lossless before writing):

      python Python/fsa_json_codec.py fsa_json
"""

import glob
import json
import os
import sys


def _dumps(obj):
    return json.dumps(obj, ensure_ascii=False, separators=(',', ':'))


def _cell_len(v):
    return len(_dumps(v))


def encode(payload):
    """Return a new payload with string columns dictionary-encoded where it saves bytes."""
    if 'dict' in payload:
        return payload
    cols, rows = payload['columns'], payload['rows']
    lookups = {}
    for j, col in enumerate(cols):
        values = [r[j] for r in rows]
        non_null = [v for v in values if v is not None]
        if not non_null or not all(isinstance(v, str) for v in non_null):
            continue
        table = sorted(set(non_null))
        code = {v: i for i, v in enumerate(table)}
        before = sum(_cell_len(v) for v in non_null)
        after = sum(len(str(code[v])) for v in non_null) + len(_dumps(table)) + len(_dumps(col)) + 2
        if after < before:
            lookups[j] = (col, table, code)
    if not lookups:
        return payload
    new_rows = [
        [lookups[j][2][v] if j in lookups and v is not None else v for j, v in enumerate(r)]
        for r in rows
    ]
    out = {'columns': cols, 'dict': {col: table for col, table, _ in lookups.values()}, 'rows': new_rows}
    return out


def decode(payload):
    """Inverse of encode(); a payload without 'dict' is returned unchanged."""
    d = payload.get('dict')
    if not d:
        return payload
    cols = payload['columns']
    tables = [d.get(c) for c in cols]
    rows = [
        [tables[j][v] if tables[j] is not None and v is not None else v for j, v in enumerate(r)]
        for r in payload['rows']
    ]
    return {'columns': cols, 'rows': rows}


def main(root):
    files = [p for p in glob.glob(os.path.join(root, '*', '*.json'))
             if not os.path.basename(p).startswith('_')]
    before = after = skipped = 0
    for path in sorted(files):
        with open(path, encoding='utf-8') as f:
            raw = f.read()
        payload = json.loads(raw)
        before += len(raw.encode('utf-8'))
        if 'dict' in payload:
            skipped += 1
            after += len(raw.encode('utf-8'))
            continue
        enc = encode(payload)
        if decode(enc) != payload:
            raise SystemExit(f'lossless check failed: {path}')
        text = _dumps(enc)
        after += len(text.encode('utf-8'))
        with open(path, 'w', encoding='utf-8', newline='\n') as f:
            f.write(text)
    print(f'{len(files)} files ({skipped} already encoded): '
          f'{before / 1048576:,.1f} MB -> {after / 1048576:,.1f} MB')


if __name__ == '__main__':
    if len(sys.argv) != 2:
        raise SystemExit('usage: python Python/fsa_json_codec.py <fsa_json dir>')
    main(sys.argv[1])
