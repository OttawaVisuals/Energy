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
"""
from __future__ import annotations

from pathlib import Path

from build_cell_curves import UNITS, build_segments, WARM_MAX_C

HERE = Path(__file__).resolve().parent

F_TO_C = lambda f: (f - 32) * 5 / 9

# Colour by COP tier, consistent hue family per tier so the legend reads at a
# glance; light/mid/dark within a tier marks <18k / 18-30k / 30-42k.
COLOURS = {
    "low_<18k": "#E8834C", "low_18-30k": "#C4574C", "low_30-42k": "#8E3A3A",
    "mid_<18k": "#5BA383", "mid_18-30k": "#3D8065", "mid_30-42k": "#245C46",
    "high_<18k": "#4C9BE8", "high_18-30k": "#3C74B8", "high_30-42k": "#274D80",
}


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
</style>
<script>
document.querySelectorAll('.ucb').forEach(cb => cb.onchange = () => {{
  const u = cb.dataset.u, on = cb.checked;
  document.querySelectorAll(`[data-u="${{u}}"]`).forEach(el => el.style.display = on ? '' : 'none');
}});
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
