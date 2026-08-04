"""
Heat-pump tier-selection curves (companion to build_tier_scatter.py).

WHY THIS EXISTS
----------------
build_tier_scatter.py plots every AHRI-certified unit as a single point
(COP @ 5 F x capacity maintenance). Once real cells are picked off that
scatter, the next question is what the actual heating curve looks like
across temperature -- this module draws those curves as line charts,
appended into the same working page (tier_scatter.html).

STATUS: the 9-cell point transcription itself has been promoted into a real
producer script, build_cell_curves.py (2026-07-29 selection chat data,
digitized from primary manufacturer datasheets) -- this module now imports
UNITS and build_segments() from there rather than defining them, so this
preview page and the shipped engine curve (data/processed/hp_cell_curves.json)
provably read the same source.

METHOD
------
Two independent point series per unit: capacity(T) and COP(T), each list only
as long as the datasheet actually published values for that metric (LG and
the low/18-30k Tosot pick are missing COP at one interior point; MDV-style
2-point units just have 47 F and 5 F).

- Between two published points of the SAME metric: solid line, true
  interpolation.
- Below the coldest published point down to the unit's lockout temperature:
  DOTTED. Capacity is extrapolated linearly (slope of the coldest published
  segment, floored at 0). COP is extrapolated to (coldest published COP -
  0.3) at lockout, i.e. the same floor rule build_hp_curves.py already uses
  for the shipped curve library.
- Above the warmest published point up to a shared chart ceiling (20 C):
  DOTTED, held flat at the warmest published value (not a real claim about
  behaviour above the coldest-climate use case -- just keeps every unit's
  line visible on a common axis, and the dotting says so).
- Where no lockout was confirmed (flagged per unit below), the coldest
  PUBLISHED point is used as a stand-in floor, so no dotted segment is drawn
  and no unconfirmed lockout is implied.

Run standalone for a quick look: python pipeline/build_tier_curves.py
Normally imported by build_tier_scatter.py, which appends CURVES_HTML into
the same tier_scatter.html / tier-scatter.html output.
STATUS ADDENDUM (2026-08-04): a per-unit spec table was appended below the
curve charts -- calculated COP/capacity at 1C steps (same interpolation as
the charts, with cells flagged where a digitized datasheet point rounds to
that integer temperature) next to the two independent real-world anchors:
  - AHRI: hp_units_joined.csv's cop/c47/cm (2 points -- max COP+cap @5F,
    rated cap @47F; that CSV has no Min/Rated/Max split, see its own
    reproducibility-gap note in build_tier_scatter.py)
  - NEEP: data/interim/neep_extract.json (build_neep_extract.py), which
    republishes AHRI's own Min/Rated/Max Heating table at 47F/17F/5F/one
    colder extreme -- richer, and it's what most of this page's "AHRI"
    cross-checks were already quoting. Missing for Cooper & Hunter
    (low_<18k, AHRI 205263878 -- no NEEP listing).
The point: most digitized curves above are the datasheet's MAX-speed column
(see UNITS[...]["source"]), not AHRI's "Rated" (nameplate) column -- the two
diverge most at the cold end. This table makes that gap visible per unit.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

from build_cell_curves import UNITS, build_segments, WARM_MAX_C

HERE = Path(__file__).resolve().parent
INTERIM = HERE.parent / "data" / "interim"

F_TO_C = lambda f: (f - 32) * 5 / 9

# Colour by COP tier, consistent hue family per tier so the legend reads at a
# glance; light/mid/dark within a tier marks <18k / 18-30k / 30-42k.
COLOURS = {
    "low_<18k": "#E8834C", "low_18-30k": "#C4574C", "low_30-42k": "#8E3A3A",
    "mid_<18k": "#5BA383", "mid_18-30k": "#3D8065", "mid_30-42k": "#245C46",
    "high_<18k": "#4C9BE8", "high_18-30k": "#3C74B8", "high_30-42k": "#274D80",
}

TABLE_T_MIN, TABLE_T_MAX = -30, 20   # integer C grid for the spec table


def _load_ahri():
    """k (AHRI #) -> {cop, c47, cm} from hp_units_joined.csv."""
    path = INTERIM / "hp_units_joined.csv"
    out = {}
    with path.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            out[row["k"]] = {
                "cop": float(row["cop"]) if row["cop"] else None,
                "c47": float(row["c47"]) if row["c47"] else None,
                "cm": float(row["cm"]) if row["cm"] else None,
            }
    return out


def _load_neep():
    path = INTERIM / "neep_extract.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))["units"]


def _eval_segments(segs, t):
    for (t0, v0, t1, v1, _solid) in segs:
        if t0 - 1e-6 <= t <= t1 + 1e-6:
            frac = 0.0 if t1 == t0 else (t - t0) / (t1 - t0)
            return v0 + frac * (v1 - v0)
    return None


def build_table_data():
    ahri_by_k = _load_ahri()
    neep_by_ahri = _load_neep()
    grid = list(range(TABLE_T_MIN, TABLE_T_MAX + 1))

    out = {}
    for uid, u in UNITS.items():
        cap_segs = build_segments(u["cap_points"], u["lockout_C"], is_cop=False)
        cop_segs = build_segments(u["cop_points"], u["lockout_C"], is_cop=True)
        cap_pub = {round(t) for t, _ in u["cap_points"]}
        cop_pub = {round(t) for t, _ in u["cop_points"]}

        ahri = ahri_by_k.get(u["ahri"])
        neep = neep_by_ahri.get(u["ahri"])
        neep_by_T = {}
        if neep:
            for h in neep["heating"]:
                neep_by_T[round(h["outdoor_C"])] = h

        rows = []
        for t in grid:
            below_lockout = t < u["lockout_C"] - 1e-6
            calc_cop = None if below_lockout else _eval_segments(cop_segs, t)
            calc_cap = None if below_lockout else _eval_segments(cap_segs, t)

            ahri_cop = ahri_cap = None
            if ahri:
                if t == -15:
                    ahri_cop = ahri["cop"]
                    ahri_cap = round(ahri["cm"] * ahri["c47"]) if ahri["cm"] and ahri["c47"] else None
                elif t == 8:
                    ahri_cap = ahri["c47"]

            h = neep_by_T.get(t)
            neep_min_cop = h["min"]["cop"] if h else None
            neep_rated_cop = h["rated"]["cop"] if h else None
            neep_max_cop = h["max"]["cop"] if h else None
            neep_min_cap = h["min"]["btuh"] if h else None
            neep_rated_cap = h["rated"]["btuh"] if h else None
            neep_max_cap = h["max"]["btuh"] if h else None

            rows.append({
                "t": t,
                "cc": None if calc_cop is None else round(calc_cop, 2),
                "ccp": t in cop_pub,
                "ca": None if calc_cap is None else round(calc_cap),
                "cap": t in cap_pub,
                "ac": ahri_cop, "aa": ahri_cap,
                "nmc": neep_min_cop, "nrc": neep_rated_cop, "nxc": neep_max_cop,
                "nma": neep_min_cap, "nra": neep_rated_cap, "nxa": neep_max_cap,
            })
        out[uid] = rows
    return out


def render_curves_html():
    W, H = 1120, 380
    PAD_L, PAD_R, PAD_T, PAD_B = 62, 20, 16, 34
    X_MIN, X_MAX = -32.0, WARM_MAX_C
    px_w = W - PAD_L - PAD_R
    px_h = H - PAD_T - PAD_B

    def sx(v):
        return PAD_L + (v - X_MIN) / (X_MAX - X_MIN) * px_w

    cap_y_max = 60000
    cop_y_max = 5.0

    def sy(v, y_max):
        return PAD_T + (1 - v / y_max) * px_h

    def chart(metric_key, y_max, y_step, y_fmt, title):
        xticks = "".join(
            f'<line x1="{sx(t):.1f}" y1="{PAD_T}" x2="{sx(t):.1f}" y2="{H-PAD_B}" class="cg"/>'
            f'<text x="{sx(t):.1f}" y="{H-PAD_B+16}" class="ctk" text-anchor="middle">{t:.0f}</text>'
            for t in range(-30, 21, 5))
        yticks = "".join(
            f'<line x1="{PAD_L}" y1="{sy(v,y_max):.1f}" x2="{W-PAD_R}" y2="{sy(v,y_max):.1f}" class="cg"/>'
            f'<text x="{PAD_L-8}" y="{sy(v,y_max)+4:.1f}" class="ctk" text-anchor="end">{y_fmt(v)}</text>'
            for v in [v * y_step for v in range(0, int(y_max / y_step) + 1)])
        paths = []
        for uid, u in UNITS.items():
            pts = u["cap_points"] if metric_key == "cap" else u["cop_points"]
            segs = build_segments(pts, u["lockout_C"], is_cop=(metric_key == "cop"))
            for (t0, v0, t1, v1, solid) in segs:
                paths.append(
                    f'<line class="curve {"solid" if solid else "dashed"}" data-u="{uid}" '
                    f'x1="{sx(t0):.1f}" y1="{sy(min(v0,y_max),y_max):.1f}" '
                    f'x2="{sx(t1):.1f}" y2="{sy(min(v1,y_max),y_max):.1f}" '
                    f'stroke="{COLOURS[uid]}"/>')
            for (t, v) in pts:
                paths.append(f'<circle class="curvept" data-u="{uid}" cx="{sx(t):.1f}" '
                             f'cy="{sy(min(v,y_max),y_max):.1f}" r="3.2" fill="{COLOURS[uid]}"/>')
        return f'''<div class="curvechart">
  <h3>{title}</h3>
  <svg viewBox="0 0 {W} {H}" class="cplot">
    <rect x="{PAD_L}" y="{PAD_T}" width="{px_w}" height="{px_h}" fill="#fff" stroke="#D9E1EA"/>
    {xticks}{yticks}
    <g id="pathsG-{metric_key}">{''.join(paths)}</g>
    <text x="{PAD_L+px_w/2}" y="{H-4}" class="cax" text-anchor="middle">Outdoor temperature (C)</text>
  </svg>
</div>'''

    cap_chart = chart("cap", cap_y_max, 10000, lambda v: f"{v/1000:.0f}k", "Heating capacity (Btu/h)")
    cop_chart = chart("cop", cop_y_max, 0.5, lambda v: f"{v:.1f}", "COP")

    legend_items = []
    for uid, u in UNITS.items():
        cell_label = uid.replace("_", " ").replace("<", "&lt;")
        flags_html = "".join(f"<li>{f}</li>" for f in u["flags"])
        legend_items.append(f'''<label class="ulg">
      <input type="checkbox" class="ucb" data-u="{uid}" checked>
      <span class="usw" style="background:{COLOURS[uid]}"></span>
      <span class="ult"><b>{cell_label}</b> -- {u["brand_model"]}
        <em>AHRI {u["ahri"]} &middot; {u["w"]:,} appearances &middot; {u["rank"]}</em>
        <span class="usrc">{u["source"]}</span>
        {f'<ul class="uflags">{flags_html}</ul>' if u["flags"] else ''}
      </span></label>''')

    table_data = build_table_data()
    unit_options = "".join(
        f'<option value="{uid}">{uid.replace("_"," ").replace("<","&lt;")} -- {u["brand_model"]}</option>'
        for uid, u in UNITS.items())
    first_uid = next(iter(UNITS))

    return f'''
<h2>Tier-cell heating curves (2026-07-29)</h2>
<p class="sub">The 9 units picked off the scatter above, digitized from their own manufacturer
datasheets where one could be found. <b>Solid</b> = interpolated between two published points.
<b>Dashed</b> = extrapolated beyond the published range (linear for capacity, floored at
published-COP&minus;0.3 for COP, down to the unit's lockout temperature; held flat above the
warmest published point, purely so every line stays visible on a shared axis). Toggle units on
or off below each chart's own legend.</p>
<div class="card">
  <div class="curverow">{cap_chart}{cop_chart}</div>
  <div class="ulegend">{"".join(legend_items)}</div>
</div>

<h2>Spec-sheet table -- calculated vs. AHRI-certified vs. NEEP ({TABLE_T_MIN}&deg;C to {TABLE_T_MAX}&deg;C)</h2>
<p class="sub">One row per whole-degree C. <b>Calculated</b> is this page's own digitized curve --
shaded cells are temperatures where a real datasheet point (not interpolation/extrapolation) rounds
to that degree. <b>AHRI</b> is <code>hp_units_joined.csv</code>'s two certified anchors (COP+capacity
at max compressor speed, 5&deg;F; rated capacity, 47&deg;F -- that source carries no Min/Rated/Max
split). <b>NEEP</b> republishes AHRI's own Min/Rated/Max Heating table at 47&deg;F/17&deg;F/5&deg;F and
one colder extreme -- richer, and it's the same certificate, not a third-party estimate. Blank cells
are not zero -- no source publishes a value there.
Cooper &amp; Hunter (low &lt;18k) has no NEEP listing.</p>
<div class="card">
  <label class="ctl" style="display:block;margin:0 0 12px">Unit:
    <select id="unitSel">{unit_options}</select>
  </label>
  <div class="tblwrap">
    <table id="specTbl">
      <thead>
        <tr>
          <th rowspan="2">T (&deg;C)</th>
          <th colspan="5">COP</th>
          <th colspan="5">Capacity (Btu/h)</th>
        </tr>
        <tr>
          <th>Calc.</th><th>AHRI</th><th>NEEP min</th><th>NEEP rated</th><th>NEEP max</th>
          <th>Calc.</th><th>AHRI</th><th>NEEP min</th><th>NEEP rated</th><th>NEEP max</th>
        </tr>
      </thead>
      <tbody id="specTblBody"></tbody>
    </table>
  </div>
  <p class="ctl"><span class="swatch pub"></span> from a digitized datasheet point &middot;
  <span class="swatch src"></span> from AHRI/NEEP certified data</p>
</div>
<style>
  .curverow {{ display:flex; gap:18px; flex-wrap:wrap }}
  .curvechart {{ flex:1 1 480px; min-width:320px }}
  .curvechart h3 {{ font-size:13px; margin:0 0 6px; color:var(--dim); font-weight:600 }}
  .cplot {{ display:block; width:100%; height:auto }}
  .cg {{ stroke:#EDF1F5; stroke-width:1 }}
  .ctk {{ font-size:10.5px; fill:var(--dim) }}
  .cax {{ font-size:11px; fill:var(--dim) }}
  .curve {{ stroke-width:2.2; fill:none }}
  .curve.dashed {{ stroke-dasharray:5 4; stroke-width:1.8; opacity:.85 }}
  .curvept {{ stroke:#fff; stroke-width:.6 }}
  .ulegend {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(320px,1fr));
              gap:10px 18px; margin-top:16px; border-top:1px solid var(--line); padding-top:14px }}
  .ulg {{ display:flex; gap:8px; align-items:flex-start; font-size:12.5px; cursor:pointer }}
  .usw {{ width:11px; height:11px; border-radius:3px; flex:0 0 auto; margin-top:3px }}
  .ult em {{ display:block; color:var(--dim); font-style:normal; font-size:11px; margin-top:1px }}
  .usrc {{ display:block; color:#8797A6; font-size:10.5px; margin-top:2px }}
  .uflags {{ margin:4px 0 0; padding-left:16px; color:#9A6B2E; font-size:10.5px; line-height:1.5 }}
  .tblwrap {{ overflow-x:auto }}
  #specTbl {{ border-collapse:collapse; font-size:12.5px; white-space:nowrap }}
  #specTbl th, #specTbl td {{ border:1px solid var(--line); padding:4px 9px; text-align:right }}
  #specTbl thead th {{ background:#EDF2F7; text-align:center }}
  #specTbl td:first-child, #specTbl th:first-child {{ text-align:center; background:#EDF2F7; font-weight:600 }}
  #specTbl td.pub {{ background:#FFF4D6; font-weight:600 }}
  #specTbl td.src {{ background:#E7F1FC; font-weight:600 }}
  #specTbl td.blank {{ color:#C3CCD4 }}
  .swatch {{ display:inline-block; width:11px; height:11px; border-radius:2px; vertical-align:-1px; margin-right:3px }}
  .swatch.pub {{ background:#FFF4D6; border:1px solid #E8C86A }}
  .swatch.src {{ background:#E7F1FC; border:1px solid #A9CBEA }}
</style>
<script>
document.querySelectorAll('.ucb').forEach(cb => cb.onchange = () => {{
  const u = cb.dataset.u, on = cb.checked;
  document.querySelectorAll(`[data-u="${{u}}"]`).forEach(el => el.style.display = on ? '' : 'none');
}});

const TABLE_DATA = {json.dumps(table_data, separators=(",", ":"))};
const fmtCOP = v => v === null ? '' : v.toFixed(2);
const fmtCap = v => v === null ? '' : Math.round(v).toLocaleString();
function renderSpecTable(uid) {{
  const body = document.getElementById('specTblBody');
  body.innerHTML = TABLE_DATA[uid].map(r => `<tr>
    <td>${{r.t}}</td>
    <td class="${{r.ccp ? 'pub' : (r.cc===null?'blank':'')}}">${{r.cc===null?'&ndash;':fmtCOP(r.cc)}}</td>
    <td class="${{r.ac===null?'blank':'src'}}">${{r.ac===null?'&ndash;':fmtCOP(r.ac)}}</td>
    <td class="${{r.nmc===null?'blank':'src'}}">${{r.nmc===null?'&ndash;':fmtCOP(r.nmc)}}</td>
    <td class="${{r.nrc===null?'blank':'src'}}">${{r.nrc===null?'&ndash;':fmtCOP(r.nrc)}}</td>
    <td class="${{r.nxc===null?'blank':'src'}}">${{r.nxc===null?'&ndash;':fmtCOP(r.nxc)}}</td>
    <td class="${{r.cap ? 'pub' : (r.ca===null?'blank':'')}}">${{r.ca===null?'&ndash;':fmtCap(r.ca)}}</td>
    <td class="${{r.aa===null?'blank':'src'}}">${{r.aa===null?'&ndash;':fmtCap(r.aa)}}</td>
    <td class="${{r.nma===null?'blank':'src'}}">${{r.nma===null?'&ndash;':fmtCap(r.nma)}}</td>
    <td class="${{r.nra===null?'blank':'src'}}">${{r.nra===null?'&ndash;':fmtCap(r.nra)}}</td>
    <td class="${{r.nxa===null?'blank':'src'}}">${{r.nxa===null?'&ndash;':fmtCap(r.nxa)}}</td>
  </tr>`).join('');
}}
document.getElementById('unitSel').value = "{first_uid}";
document.getElementById('unitSel').onchange = e => renderSpecTable(e.target.value);
renderSpecTable("{first_uid}");
</script>
'''


CURVES_HTML = render_curves_html()

if __name__ == "__main__":
    out = HERE.parent / "data/interim/tier_curves_preview.html"
    out.write_text(f"<!doctype html><meta charset=utf-8><title>curves preview</title>"
                    f"<body style='font:14px sans-serif;max-width:1200px;margin:20px auto'>"
                    f"{CURVES_HTML}</body>", encoding="utf-8")
    print(f"wrote {out}")
    for uid, u in UNITS.items():
        print(uid, u["brand_model"], "cap pts:", len(u["cap_points"]), "cop pts:", len(u["cop_points"]))
