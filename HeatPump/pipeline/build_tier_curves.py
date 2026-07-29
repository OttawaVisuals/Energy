"""
Heat-pump tier-selection curves (companion to build_tier_scatter.py).

WHY THIS EXISTS
----------------
build_tier_scatter.py plots every AHRI-certified unit as a single point
(COP @ 5 F x capacity maintenance). Once real cells are picked off that
scatter, the next question is what the actual heating curve looks like
across temperature -- this module digitizes the manufacturer datasheet
points gathered for the 9 candidate cells (3 COP tiers x 3 capacity bands,
per the 2026-07-28 tier-selection rework) and draws them as line charts,
appended into the same working page (tier_scatter.html).

STATUS: working document, not a pipeline in the ROADMAP sense -- there is no
raw-data input file. Every point below was hand-transcribed from a manufacturer
submittal / design & technical manual, opened directly, during selection
chat with Simon on 2026-07-29. Sources are recorded per unit in SOURCE below.
This module exists so the transcription is captured in the repo rather than
living only in chat history -- if `hp_curves.json` is rebuilt from these 9
units, this is the file to promote into a real pipeline script (with the PDFs
themselves committed or logged in a fetch manifest, following the
cell_candidates.csv / match_spec_sheets.py pattern already in this directory).

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

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent

F_TO_C = lambda f: (f - 32) * 5 / 9

# Colour by COP tier, consistent hue family per tier so the legend reads at a
# glance; light/mid/dark within a tier marks <18k / 18-30k / 30-42k.
COLOURS = {
    "low_<18k": "#E8834C", "low_18-30k": "#C4574C", "low_30-42k": "#8E3A3A",
    "mid_<18k": "#5BA383", "mid_18-30k": "#3D8065", "mid_30-42k": "#245C46",
    "high_<18k": "#4C9BE8", "high_18-30k": "#3C74B8", "high_30-42k": "#274D80",
}

# --------------------------------------------------------------------------
# The 9 selected cells. Every point below was read directly off a manufacturer
# document by Simon or Claude during chat on 2026-07-29 -- see `source`.
# T in Celsius throughout; capacity in Btu/h; COP dimensionless.
# --------------------------------------------------------------------------
UNITS = {
    "low_<18k": {
        "brand_model": "Cooper & Hunter CH-12SPH-230VO", "ahri": "205263878", "w": 123,
        "rank": "#7 of 158 (Lennox/Panasonic/Zephyr/Elios/Moovair/Napoleon all lacked datasheets)",
        "source": "C&H submittal, indoor 70F, MAX-speed column of a min/rated/max table",
        "cap_points": [(-15.0, 8611), (-8.33, 11225), (8.33, 13764)],
        "cop_points": [(-15.0, 1.83), (-8.33, 2.28), (8.33, 3.57)],
        "lockout_C": -15.0,
        "flags": ["Lockout not published; using coldest tested point (5F) as the floor -- no "
                  "dotted extrapolation drawn below it.",
                  "COP peaks at the RATED (mid) speed at 17F (2.67), not at max speed (2.28) -- "
                  "the only unit in this set where that's true. Using max-speed points throughout "
                  "for consistency with every other cell."],
    },
    "low_18-30k": {
        "brand_model": "Tosot TUD24W2/D-D(U)", "ahri": "211078853", "w": 122,
        "rank": "#9 of 178 (ACD/GREE/Tosot-18k/Samsung/KingHome all lacked datasheets)",
        "source": "Tosot UNIX 24K submittal (tosotclima.com), indoor 70F implied, 3-pt",
        "cap_points": [(-15.0, 13100), (-8.33, 14600), (8.33, 23000)],
        "cop_points": [(-15.0, 1.8), (8.33, 3.1)],   # no COP published at 17F
        "lockout_C": -15.0,
        "flags": ["Lockout confirmed from spec page: 'Heating Temperature Range 5-75F'."],
    },
    "low_30-42k": {
        "brand_model": "Tosot TUD36W2/D-D(U)", "ahri": "211078855", "w": 156,
        "rank": "#4 of 173 (KingHome #1 lacked a datasheet)",
        "source": "TOSOT_TUD36.pdf p.4 EXTENDED RATINGS, indoor 70F, MAX OUTPUT column, 17-pt",
        "cap_points": [(-15.0, 18700), (-12.22, 18700), (-9.44, 18800), (-8.33, 19000),
                        (-6.67, 22150), (-3.89, 24180), (-1.11, 26320), (1.67, 28560),
                        (4.44, 30100), (7.22, 31800), (8.33, 34000), (10.0, 34900),
                        (12.78, 35900), (15.56, 37000), (18.33, 37000), (21.11, 37000),
                        (23.89, 37000)],
        "cop_points": [(-15.0, 1.76), (-12.22, 1.85), (-9.44, 1.96), (-8.33, 2.10),
                        (-6.67, 2.06), (-3.89, 2.24), (-1.11, 2.45), (1.67, 2.67),
                        (4.44, 2.73), (7.22, 2.82), (8.33, 2.93), (10.0, 2.99),
                        (12.78, 3.06), (15.56, 3.14), (18.33, 3.30), (21.11, 3.48),
                        (23.89, 3.66)],
        "lockout_C": -15.0,
        "flags": ["Lockout confirmed from spec page: 'Heating Temperature Range 5-75F'. "
                  "COP@5F=1.76 is an exact match to the AHRI record -- best agreement of any unit."],
    },
    "mid_<18k": {
        "brand_model": "LG LSU120HSV5", "ahri": "10570123", "w": 4182,
        "rank": "#1 of 344",
        "source": "LG submittal (ajmadison) 4-pt capacity; COP only published at rated 47F "
                  "(backed out from power draw) -- 5F COP is the AHRI record, not an independent "
                  "datasheet measurement",
        "cap_points": [(-19.44, 10360), (-14.44, 11930), (-7.22, 13810), (8.33, 13600)],
        "cop_points": [(-15.0, 1.80), (8.33, 3.83)],
        "lockout_C": -20.0,
        "flags": ["Lockout approximated from LG's stated Heating (WB) -4F operating floor "
                  "(wet-bulb, not dry-bulb -- treated as roughly equivalent here).",
                  "COP curve between 47F and 5F is a straight interpolation between two anchors, "
                  "not measured at the intermediate submittal capacity points (19F/6F/-3F)."],
    },
    "mid_18-30k": {
        "brand_model": "GREE GUD36W/A-D(U) (24k-rated pairing)", "ahri": "206249116", "w": 2253,
        "rank": "#2 of 1,024 (Daikin 3MXL24WMVJU* #1 lacked a datasheet)",
        "source": "GREE FLEXX Ultra18 Extended Ratings (digitized, datasheet_points_v2.json)",
        "flags": ["Same physical outdoor unit (FLEXX36HP230V1AO) as mid/30-42k below -- GREE's own "
                  "extended-ratings doc groups the 24k- and 36k-rated systems under one identical "
                  "table (confirmed against GREE_FLEXX_extended_ratings.pdf, which explicitly pairs "
                  "FLEXX24HP230V1BH and FLEXX36HP230V1AO in the same table). Not a digitization "
                  "error."],
        "reuse_from": "mid_30-42k",
    },
    "mid_30-42k": {
        "brand_model": "GREE GUD36W/A-D(U)", "ahri": "211644151", "w": 11555,
        "rank": "#1 of 916 -- the single most-installed unit in the whole dataset",
        "source": "GREE FLEXX Ultra18 Extended Ratings (digitized, datasheet_points_v2.json), 23-pt",
        "cap_points": None, "cop_points": None,  # filled from datasheet_points_v2.json below
        "lockout_C": -30.0,
        "flags": [],
    },
    "high_<18k": {
        "brand_model": "Fujitsu AOUG15LZAH1", "ahri": "206597213", "w": 1918,
        "rank": "#3 of 445 (Panasonic #1 lacked a datasheet; LG #2 excluded -- COP 5.97 data error)",
        "source": "Fujitsu design & technical manual, indoor 21.1C DB, MAX output, 10-pt",
        "cap_points": [(-26.1, 16275), (-20.6, 18630), (-15.0, 20984), (-10.0, 21598),
                        (-5.0, 22246), (0.0, 22860), (5.0, 23475), (8.3, 23884),
                        (10.0, 24873), (15.0, 25897)],
        "cop_points": [(-26.1, 1.66), (-20.6, 1.89), (-15.0, 2.12), (-10.0, 2.28),
                        (-5.0, 2.45), (0.0, 2.64), (5.0, 3.03), (8.3, 3.20),
                        (10.0, 3.56), (15.0, 4.17)],
        "lockout_C": -26.1,
        "flags": ["Lockout not published in the excerpt reviewed; using the coldest tested point "
                  "(-26.1C) as the floor -- no dotted extrapolation below it.",
                  "Cross-check at 5F: curve gives COP 2.12 vs. the AHRI record's 2.34 (9.4% gap) -- "
                  "the widest mismatch of any unit in this set, right at the pipeline's 10% "
                  "cross-check tolerance."],
    },
    "high_18-30k": {
        "brand_model": "Moovair DMA24HOS20230E7", "ahri": "212361759", "w": 4206,
        "rank": "#2 of 1,741 (MDV MOD30-24 #1 also has real data -- 2-pt only, swapped out for "
                "this richer 15-pt curve)",
        "source": "Moovair M20 Heat+ Central Moov -30C Performance Data, indoor 70F row, 15-pt",
        "cap_points": [(-30.0, 17380), (-25.0, 19980), (-20.0, 22200), (-17.8, 23200),
                        (-15.0, 24130), (-12.2, 24250), (-8.3, 24390), (-6.7, 25150),
                        (-3.9, 25900), (0.0, 26630), (1.7, 27300), (4.4, 29290),
                        (8.3, 31230), (10.0, 31740), (13.9, 32170)],
        "cop_points": [(-30.0, 1.23), (-25.0, 1.40), (-20.0, 1.63), (-17.8, 1.75),
                        (-15.0, 1.86), (-12.2, 1.98), (-8.3, 2.11), (-6.7, 2.21),
                        (-3.9, 2.31), (0.0, 2.40), (1.7, 2.51), (4.4, 2.82),
                        (8.3, 3.16), (10.0, 3.23), (13.9, 3.32)],
        "lockout_C": -30.0,
        "flags": ["Cross-check at 5F: curve gives COP 1.86 vs. the AHRI record's 1.95 (4.6% gap)."],
    },
    "high_30-42k": {
        "brand_model": "Fujitsu AOUG36LMAS1", "ahri": "205123809", "w": 1795,
        "rank": "#1 of 1,302",
        "source": "Fujitsu design & technical manual, indoor 21.1C DB, MAX output, 9-pt",
        "cap_points": [(-20.6, 28831), (-15.0, 32960), (-10.0, 36747), (-5.0, 40705),
                        (0.0, 44834), (5.0, 49099), (8.3, 51999), (10.0, 53500), (15.0, 58072)],
        "cop_points": [(-20.6, 1.97), (-15.0, 2.03), (-10.0, 2.11), (-5.0, 2.24),
                        (0.0, 2.41), (5.0, 2.64), (8.3, 2.83), (10.0, 2.93), (15.0, 3.32)],
        "lockout_C": -20.6,   # Simon's -20C call, clamped to the coldest tested point (-20.6C)
        "flags": ["Cross-check at 5F: curve gives COP 2.03 vs. the AHRI record's 2.00 (1.3% gap) -- "
                  "the anchor unit for this tier."],
    },
}

# GREE's real 23-pt curve, shared by mid_18-30k and mid_30-42k (see reuse_from above).
_ds2 = json.loads((HERE.parent / "data/interim/datasheet_points_v2.json").read_text(encoding="utf-8"))
_gree_pts = _ds2["units"]["211644151"]["points"]
_gree_cap = [(p["T_C"], round(p["cap_kW"] * 3412)) for p in _gree_pts]
_gree_cop = [(p["T_C"], p["COP"]) for p in _gree_pts]
UNITS["mid_30-42k"]["cap_points"] = _gree_cap
UNITS["mid_30-42k"]["cop_points"] = _gree_cop
UNITS["mid_18-30k"]["cap_points"] = _gree_cap
UNITS["mid_18-30k"]["cop_points"] = _gree_cop
UNITS["mid_18-30k"]["lockout_C"] = -30.0

WARM_MAX_C = 20.0


def build_segments(points, lockout_C, is_cop):
    """(T,V) list -> list of (T0,V0,T1,V1,solid) covering lockout..WARM_MAX_C."""
    pts = sorted(points)
    segs = []
    cold_T, cold_V = pts[0]
    warm_T, warm_V = pts[-1]
    if lockout_C < cold_T - 1e-6:
        if is_cop:
            lock_V = max(cold_V - 0.3, 0.1)
        else:
            if len(pts) >= 2:
                (t0, v0), (t1, v1) = pts[0], pts[1]
                slope = (v1 - v0) / (t1 - t0)
            else:
                slope = 0.0
            lock_V = max(cold_V + slope * (lockout_C - cold_T), 0.0)
        segs.append((lockout_C, lock_V, cold_T, cold_V, False))
    for i in range(len(pts) - 1):
        segs.append((pts[i][0], pts[i][1], pts[i + 1][0], pts[i + 1][1], True))
    if warm_T < WARM_MAX_C - 1e-6:
        segs.append((warm_T, warm_V, WARM_MAX_C, warm_V, False))
    return segs


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
