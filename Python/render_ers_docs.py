"""
Renders the two ERS column-availability tables from ers_column_tables.json:
  1. docs/ERS_DATA_DICTIONARY.md   -- all 433 raw ERS columns (full reference)
  2. a retrofits.html-ready HTML fragment for the ~48 columns actually used
     (printed to stdout / written to Python/_used_table_fragment.html for a
     manual paste into retrofits.html's methodology section)

One-off doc-generation helper, not part of the regular data pipeline.
"""

import html
import json
from pathlib import Path

DATA = json.loads(Path(r"C:\Energy\Python\ers_column_tables.json").read_text(encoding="utf-8"))
DOCS_OUT = Path(r"C:\Energy\docs\ERS_DATA_DICTIONARY.md")
FRAGMENT_OUT = Path(r"C:\Energy\Python\_used_table_fragment.html")


def md_escape(s):
    s = (s or "").replace("|", "\\|").replace("\n", " ")
    return s.replace("<", "&lt;").replace(">", "&gt;")


def build_markdown():
    lines = []
    lines.append("# ERS Data Dictionary — Full Column Reference")
    lines.append("")
    lines.append(
        "Every column NRCan publishes in the EnerGuide/ERS open-data CSV extracts "
        "(433 columns, audit years 2004–2026), with its NRCan-authored description, "
        "how completely it's populated, and its cardinality. This is the full raw "
        "dataset — see [RETROFITS.md](RETROFITS.md) for the ~48 columns the "
        "[Retrofit Explorer](../retrofits.html) actually reads and how each is used."
    )
    lines.append("")
    lines.append(
        "**Updated 2026-07-31.** Fill rate and unique-value count are measured "
        "across **all 4,542,544 raw audit records** (every `D`/`E` evaluation in "
        "every yearly CSV, `C:\\ERS\\2004-2006.csv` … `2026.csv`) — this is the "
        "*unpaired* audit stream, not the smaller before/after-matched sample the "
        "Retrofit Explorer charts show, so these figures read a little more "
        "complete than what a single matched retrofit record has filled in. "
        "Descriptions are NRCan's own open-data column dictionary, unedited. "
        "Unique-value counts are capped at 20,000 distinct strings per column "
        "(shown as `>20000`) to keep a full-column-set scan bounded — exact "
        "cardinality isn't meaningful for near-unique identifier fields like "
        "`HOUSEID` or `EVALUATIONSID` anyway."
    )
    lines.append("")
    lines.append("| Column | Description | % filled | Unique values |")
    lines.append("|---|---|---:|---:|")
    for r in DATA["all_columns"]:
        pct = f"{r['pct']:.1f}%" if r["pct"] is not None else "—"
        lines.append(
            f"| `{r['column']}` | {md_escape(r['description']) or '—'} | {pct} | {r['unique']} |"
        )
    lines.append("")
    DOCS_OUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {DOCS_OUT} ({len(DATA['all_columns'])} rows)")


def fmt_pct(pct):
    if pct is None:
        return "—"
    return f"{pct:.1f}%"


def build_used_fragment():
    rows = DATA["used_columns"]
    out = []
    out.append('<section class="methodology" aria-label="ERS data availability">')
    out.append('  <details>')
    out.append('    <summary>Data availability — every ERS column vs. what this page uses</summary>')
    out.append('    <div class="method-body">')
    out.append(
        "      <p>The public EnerGuide/ERS extract carries <strong>433 columns</strong> "
        "per audit record. This page reads <strong>48</strong> of them. The table below "
        "is every one of those 48, grouped in pipeline order, with its % filled "
        "(measured across all 4,542,544 raw audit records — see caveat below), the "
        "unit conversion applied if any, and exactly what it's used for. The full "
        "433-column reference, with the same fill-rate methodology, is in "
        '<a href="https://github.com/OttawaVisuals/Energy/blob/main/docs/ERS_DATA_DICTIONARY.md" '
        'target="_blank" rel="noopener">ERS_DATA_DICTIONARY.md</a>.</p>'
    )
    out.append('      <div class="method-table-wrap"><table>')
    out.append(
        "        <thead><tr><th>ERS source column</th><th>Used as</th>"
        "<th>% filled</th><th>Conversion</th><th>Used for</th></tr></thead>"
    )
    out.append("        <tbody>")
    current_group = None
    for r in rows:
        if r["group"] != current_group:
            current_group = r["group"]
            out.append(
                f'          <tr><td colspan="5" style="padding-top:.85rem;'
                f'font-size:10.5px;font-weight:600;letter-spacing:.06em;'
                f'text-transform:uppercase;color:var(--muted);border-bottom:none">'
                f'{current_group}</td></tr>'
            )
        raw_friendly = r["friendly"] or ""
        if raw_friendly and not raw_friendly.startswith("("):
            friendly = f"<code>{html.escape(raw_friendly)}</code>"
        else:
            friendly = f'<span class="caveats" style="border:none;padding:0">{html.escape(raw_friendly) or "&mdash;"}</span>'
        conv = html.escape(r["conversion"]) if r["conversion"] else "&mdash;"
        used_for = html.escape(r["used_for"]) if r["used_for"] else "&mdash;"
        out.append(
            f'          <tr><td><code>{html.escape(r["source"])}</code></td>'
            f'<td>{friendly}</td>'
            f'<td>{fmt_pct(r["pct"])}</td>'
            f'<td>{conv}</td>'
            f'<td>{used_for}</td></tr>'
        )
    out.append("        </tbody>")
    out.append("      </table></div>")
    out.append(
        '      <p class="caveats"><strong>% filled</strong> is measured across all '
        "raw D/E audit records, not the smaller before/after-matched sample the "
        "charts above use, so it reads a little higher than what a single matched "
        "retrofit record has filled in. <code>EVALTYPE</code>, <code>AIRCONDTYPE</code> "
        "and <code>NUMDWELLINGUNITS</code> are used only to split before/after "
        "records or gate the same-home pairing match (section A above) — they never "
        "appear as a displayed value, so they carry no conversion factor and no "
        "\"used as\" name.</p>"
    )
    out.append("    </div>")
    out.append("  </details>")
    out.append("</section>")
    frag = "\n".join(out)
    FRAGMENT_OUT.write_text(frag, encoding="utf-8")
    print(f"Wrote {FRAGMENT_OUT} ({len(rows)} rows)")


if __name__ == "__main__":
    build_markdown()
    build_used_fragment()
