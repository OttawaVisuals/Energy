"""
Builds retrofits/review/pei_retrofit_costs_review.html from
retrofits/data/PE_priced.json (retrofit_cost_estimate.py's output).

Single-method version (no more Original/Corrected toggle — that question is
settled per docs/RETROFIT_COSTS.md's 2026-07-31 (4) changelog entry: base-case
post-audit fields, not the UGR* upgrade-case fields).
"""

import json
import os

DATA_PATH = os.path.join("retrofits", "data", "PE_priced.json")
OUT_PATH = os.path.join("retrofits", "review", "pei_retrofit_costs_review.html")

TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>PEI retrofit cost estimates — per-home review (POC)</title>
<style>
  :root{
    --bg:#0f1419; --panel:#161d24; --panel2:#1c242d; --line:#2a3540;
    --ink:#e6edf3; --muted:#8b9aa8; --dim:#6b7a88;
    --accent:#4a9eff; --warn:#e0a458; --bad:#e06c6c; --good:#5fb87a;
  }
  *{box-sizing:border-box}
  body{margin:0;background:var(--bg);color:var(--ink);
       font:14px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif}
  a{color:var(--accent)}
  .wrap{max-width:1500px;margin:0 auto;padding:24px 20px 80px}
  h1{font-size:22px;margin:0 0 4px;font-weight:650}
  .sub{color:var(--muted);font-size:13px;margin-bottom:20px}
  .tag{display:inline-block;background:var(--warn);color:#1a1207;font-weight:700;
       font-size:11px;padding:2px 8px;border-radius:3px;letter-spacing:.04em;
       text-transform:uppercase;vertical-align:middle;margin-left:8px}

  .note{background:var(--panel);border:1px solid var(--line);border-left:3px solid var(--warn);
        border-radius:5px;padding:14px 16px;margin-bottom:20px;font-size:13px;color:var(--muted)}
  .note b{color:var(--ink)}
  .note ul{margin:8px 0 0;padding-left:18px}
  .note li{margin:4px 0}

  .controls{position:sticky;top:0;z-index:20;background:var(--bg);
            border-bottom:1px solid var(--line);padding:12px 0;margin-bottom:0;
            display:flex;flex-wrap:wrap;gap:16px;align-items:flex-end}
  .grp{display:flex;flex-direction:column;gap:5px}
  .grp label{font-size:11px;color:var(--dim);text-transform:uppercase;letter-spacing:.05em}
  .seg{display:flex;border:1px solid var(--line);border-radius:5px;overflow:hidden}
  .seg button{background:var(--panel);color:var(--muted);border:0;padding:7px 14px;
              cursor:pointer;font-size:13px;font-family:inherit;border-right:1px solid var(--line)}
  .seg button:last-child{border-right:0}
  .seg button:hover{background:var(--panel2);color:var(--ink)}
  .seg button.on{background:var(--accent);color:#06121f;font-weight:650}
  input[type=search],select{background:var(--panel);color:var(--ink);border:1px solid var(--line);
        border-radius:5px;padding:7px 10px;font-size:13px;font-family:inherit;min-width:150px}

  .stats{display:flex;flex-wrap:wrap;gap:0;border:1px solid var(--line);border-top:0;
         border-radius:0 0 6px 6px;background:var(--panel);margin-bottom:22px}
  .stat{flex:1 1 130px;padding:12px 16px;border-right:1px solid var(--line)}
  .stat:last-child{border-right:0}
  .stat .k{font-size:11px;color:var(--dim);text-transform:uppercase;letter-spacing:.05em}
  .stat .v{font-size:19px;font-weight:650;margin-top:3px;font-variant-numeric:tabular-nums}

  table{width:100%;border-collapse:collapse;font-variant-numeric:tabular-nums}
  thead th{position:sticky;top:57px;background:var(--panel2);z-index:10;
           text-align:right;padding:9px 10px;font-size:11px;color:var(--muted);
           text-transform:uppercase;letter-spacing:.04em;border-bottom:1px solid var(--line);
           white-space:nowrap;cursor:pointer;user-select:none}
  thead th:hover{color:var(--ink)}
  thead th.l{text-align:left}
  thead th.nos{cursor:default}
  thead th.nos:hover{color:var(--muted)}
  tbody td{padding:8px 10px;text-align:right;border-bottom:1px solid #1e262f;white-space:nowrap}
  tbody td.l{text-align:left}
  tbody tr.row{cursor:pointer}
  tbody tr.row:hover{background:var(--panel)}
  tbody tr.row.open{background:var(--panel2)}
  .z{color:#3d4a56}
  .tot{font-weight:700}
  .neg{color:var(--bad)}
  .chips{display:flex;gap:3px;flex-wrap:wrap}
  .chip{font-size:10px;padding:1px 5px;border-radius:3px;background:#243040;color:#9fb4c9;
        letter-spacing:.02em}
  .chip.hp{background:#1f3a2c;color:#7fc99a}
  .chip.win{background:#3a2f1f;color:#d9b57a}
  .chip.seal{background:#1e3340;color:#84bcd9}
  .chip.pv{background:#3d3520;color:#e0c06a}
  .chip.hrv{background:#2f2740;color:#b79ee0}
  .arrow{color:var(--dim);width:14px;display:inline-block}

  tr.detail td{background:#121920;padding:0;border-bottom:1px solid var(--line)}
  .dwrap{padding:16px 18px;display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:18px}
  .dsec h4{margin:0 0 8px;font-size:11px;color:var(--dim);text-transform:uppercase;letter-spacing:.05em}
  .dsec table{font-size:12.5px}
  .dsec td{padding:3px 0;border:0;text-align:left;white-space:normal}
  .dsec td:last-child{text-align:right;color:var(--ink);padding-left:12px}
  .dsec td:first-child{color:var(--muted)}
  .pill{font-size:10px;padding:1px 6px;border-radius:3px;background:#243040;color:#9fb4c9}
  .pill.rep{background:#1f3a2c;color:#7fc99a}
  .pill.ass{background:#3a2f1f;color:#d9b57a}

  .pager{display:flex;gap:10px;align-items:center;justify-content:center;padding:20px 0;
         color:var(--muted);font-size:13px}
  .pager button{background:var(--panel);color:var(--ink);border:1px solid var(--line);
                border-radius:5px;padding:6px 14px;cursor:pointer;font-family:inherit;font-size:13px}
  .pager button:disabled{opacity:.35;cursor:default}
  .empty{padding:40px;text-align:center;color:var(--dim)}
  code{background:#1c242d;padding:1px 5px;border-radius:3px;font-size:12px;color:#b9cbdb}
</style>
</head>
<body>
<div class="wrap">

<h1>PEI retrofit cost estimates — per-home review<span class="tag">POC</span></h1>
<div class="sub" id="sub"></div>

<div class="note">
  <b>What this page is.</b> Every ERS-paired PEI single-dwelling retrofit record with at
  least one measure REMDB can price, shown individually. All figures are <b>2023 USD</b> —
  no CAD conversion and no Canadian-labour adjustment has been applied, so these are US
  prices applied to a Canadian house, not Canadian costs.
  <br><b>Figures are <span style="color:#e0a458">incremental</span></b> — the extra over the
  business-as-usual choice, not the full invoice. Insulation and air sealing have no BAU
  equivalent (incremental = full cost); windows are the efficient-minus-standard premium;
  an ASHP is netted against <b>the home's own pre-audit heating system</b> (like-for-like —
  e.g. an oil boiler credited as an oil boiler, not a generic gas furnace) plus the A/C it
  replaces, and can be negative. See the
  <a href="retrofit_cost_methodology.html" style="color:#5fb8ff">methodology page</a> for
  the full model.
  <ul>
    <li><b>Cost level</b> switches between REMDB's 10th / 50th / 90th percentile quantile regressions.</li>
    <li>A <span class="pill ass">assumed</span> pill means REMDB has no matching row at all for
      that home's actual equipment/window frame, so the model fell back to a generic
      default (gas furnace / Vinyl) — flagged, not hidden.</li>
    <li>Two ASHP heating baselines (Oil Furnace, Electric Boiler) are priced from raw REMDB
      workbook line items REMDB itself never fit a regression for — see the methodology page.</li>
  </ul>
</div>

<div class="controls">
  <div class="grp">
    <label>Cost level</label>
    <div class="seg" id="segBand">
      <button data-v="0">Low (p10)</button>
      <button data-v="1" class="on">Mid (p50)</button>
      <button data-v="2">High (p90)</button>
    </div>
  </div>
  <div class="grp">
    <label>Measure present</label>
    <select id="fMeasure">
      <option value="">Any priced measure</option>
      <option value="Roof">Roof / attic insulation</option>
      <option value="Wall">Wall insulation</option>
      <option value="Foundation">Foundation insulation</option>
      <option value="Window">Windows</option>
      <option value="ASHP">Air source heat pump</option>
      <option value="AirSeal">Air sealing</option>
      <option value="PV">Solar PV</option>
      <option value="HRV">HRV / ERV</option>
    </select>
  </div>
  <div class="grp">
    <label>ASHP BAU heating</label>
    <select id="fBau">
      <option value="">All records</option>
      <option value="like_for_like">Like-for-like (real match)</option>
      <option value="assumed_default">Assumed gas furnace (no REMDB match)</option>
    </select>
  </div>
  <div class="grp">
    <label>Search</label>
    <input type="search" id="fSearch" placeholder="HOUSEID or FSA">
  </div>
</div>

<div class="stats" id="stats"></div>

<table>
  <thead><tr>
    <th class="l nos" style="width:22px"></th>
    <th class="l" data-s="id">House ID</th>
    <th class="l" data-s="fsa">FSA</th>
    <th class="l nos">Measures</th>
    <th data-s="Roof">Roof</th>
    <th data-s="Wall">Wall</th>
    <th data-s="Foundation">Foundation</th>
    <th data-s="Window">Windows</th>
    <th data-s="ASHP">Heat pump</th>
    <th data-s="AirSeal">Air sealing</th>
    <th data-s="PV">Solar PV</th>
    <th data-s="HRV">HRV/ERV</th>
    <th data-s="Total">Total est.</th>
  </tr></thead>
  <tbody id="tb"></tbody>
</table>
<div class="pager" id="pager"></div>

</div>
<script id="data" type="application/json">__DATA_JSON__</script>
<script>
(function(){
  var DATA = JSON.parse(document.getElementById('data').textContent);
  var HOMES = DATA.homes;
  var MEASURES = ['Roof','Wall','Foundation','Window','ASHP','AirSeal','PV','HRV'];
  var LABEL = {Roof:'Roof / attic insulation', Wall:'Wall insulation',
               Foundation:'Foundation wall insulation', Window:'Windows',
               ASHP:'Air source heat pump', AirSeal:'Air sealing',
               PV:'Solar PV', HRV:'HRV / ERV'};
  var PAGE = 100;

  var st = {band:1, measure:'', bau:'', q:'', sort:'Total', dir:-1, page:0, open:null};

  document.getElementById('sub').innerHTML =
    DATA.n_priced.toLocaleString() + ' of ' + DATA.n_paired.toLocaleString() +
    ' paired PEI single-dwelling retrofit records have at least one priceable measure &middot; ' +
    DATA.bau_heating_reported.toLocaleString() + ' of ' +
    (DATA.bau_heating_reported + DATA.bau_heating_assumed).toLocaleString() +
    ' ASHP records get a like-for-like heating BAU match &middot; ' +
    'REMDB 2024.12.23 &middot; generated ' + DATA.generated;

  function money(v){
    if(v===null||v===undefined) return null;
    return (v<0?'-$':'$') + Math.round(Math.abs(v)).toLocaleString();
  }
  function cell(v){
    if(v===undefined||v===null) return '<td class="z">—</td>';
    return '<td class="'+(v<0?'neg':'')+'">'+money(v)+'</td>';
  }
  function val(h, m){
    var b = h.measures[m];
    return b ? b[st.band] : undefined;
  }

  function filtered(){
    var q = st.q.trim().toLowerCase();
    return HOMES.filter(function(h){
      if(st.measure && val(h, st.measure)===undefined) return false;
      if(q && (h.id||'').toLowerCase().indexOf(q) < 0 &&
              (h.fsa||'').toLowerCase().indexOf(q) < 0) return false;
      if(st.bau && h.bau_heating_source !== st.bau) return false;
      return true;
    });
  }

  function sorted(rows){
    var s = st.sort, d = st.dir;
    return rows.slice().sort(function(a,b){
      var x, y;
      if(s === 'id'){ x = +a.id || a.id; y = +b.id || b.id; }
      else if(s === 'fsa'){ x = a.fsa||''; y = b.fsa||''; }
      else if(s === 'Total'){ x = a.total?a.total[st.band]:-1e12; y = b.total?b.total[st.band]:-1e12; }
      else { x = val(a,s); x = x===undefined?-1e12:x; y = val(b,s); y = y===undefined?-1e12:y; }
      if(x < y) return -1*d;
      if(x > y) return 1*d;
      return 0;
    });
  }

  function quantile(arr, p){
    if(!arr.length) return 0;
    var i = (arr.length-1)*p, lo = Math.floor(i), hi = Math.ceil(i);
    return arr[lo] + (arr[hi]-arr[lo])*(i-lo);
  }

  function renderStats(rows){
    var totals = rows.map(function(h){ return h.total?h.total[st.band]:null; })
                     .filter(function(v){ return v !== null; })
                     .sort(function(a,b){ return a-b; });
    var sum = totals.reduce(function(a,b){ return a+b; }, 0);
    var bauN = rows.filter(function(h){ return h.bau_heating_source==='assumed_default'; }).length;
    var winN = rows.filter(function(h){ return h.window_class_source==='assumed_default'; }).length;
    var cards = [
      ['Homes shown', rows.length.toLocaleString()],
      ['Median total', money(quantile(totals,.5))],
      ['p10 – p90', money(quantile(totals,.1)) + ' – ' + money(quantile(totals,.9))],
      ['Mean total', money(totals.length ? sum/totals.length : 0)],
      ['ASHP BAU assumed', bauN.toLocaleString()],
      ['Window class assumed', winN.toLocaleString()]
    ];
    document.getElementById('stats').innerHTML = cards.map(function(c){
      return '<div class="stat"><div class="k">'+c[0]+'</div><div class="v">'+c[1]+'</div></div>';
    }).join('');
  }

  function chips(h){
    var out = [];
    if(val(h,'Roof')!==undefined) out.push('<span class="chip">roof</span>');
    if(val(h,'Wall')!==undefined) out.push('<span class="chip">wall</span>');
    if(val(h,'Foundation')!==undefined) out.push('<span class="chip">fnd</span>');
    if(val(h,'Window')!==undefined) out.push('<span class="chip win">win</span>');
    if(val(h,'ASHP')!==undefined) out.push('<span class="chip hp">ASHP</span>');
    if(val(h,'AirSeal')!==undefined) out.push('<span class="chip seal">air seal</span>');
    if(val(h,'PV')!==undefined) out.push('<span class="chip pv">PV</span>');
    if(val(h,'HRV')!==undefined) out.push('<span class="chip hrv">HRV</span>');
    return '<div class="chips">'+out.join('')+'</div>';
  }

  function srcPill(s){
    if(s === 'reported' || s === 'like_for_like') return '<span class="pill rep">'+s.replace('_',' ')+'</span>';
    if(s === 'assumed_default') return '<span class="pill ass">assumed</span>';
    return '';
  }

  function kv(list){
    return '<table>'+list.map(function(r){
      return '<tr><td>'+r[0]+'</td><td>'+r[1]+'</td></tr>';
    }).join('')+'</table>';
  }

  function detail(h){
    var sec = [];
    if(val(h,'ASHP')!==undefined){
      sec.push('<div class="dsec"><h4>Heat pump</h4>'+kv([
        ['ASHP class', (h.ashp_class||'—') + ' ' + srcPill(h.ashp_class_source)],
        ['BAU heating replaced', (h.bau_heating||'—') + ' ' + srcPill(h.bau_heating_source)],
        ['Self-derived REMDB row', h.bau_self_derived ? 'yes (REMDB never fit this class)' : 'no (REMDB-fitted)']
      ])+'</div>');
    }
    if(val(h,'Window')!==undefined){
      sec.push('<div class="dsec"><h4>Windows</h4>'+kv([
        ['Frame class', (h.window_class||'—') + ' ' + srcPill(h.window_class_source)]
      ])+'</div>');
    }
    if(val(h,'HRV')!==undefined){
      sec.push('<div class="dsec"><h4>Ventilation</h4>'+kv([
        ['SRE / airflow metrics', 'flat placeholder (not per-home — see methodology)']
      ])+'</div>');
    }
    var m = MEASURES.map(function(k){
      var v = val(h,k);
      return v===undefined ? '' : '<tr><td>'+LABEL[k]+'</td><td>'+money(v)+'</td></tr>';
    }).join('');
    sec.unshift('<div class="dsec"><h4>Priced measures (this band)</h4><table>'+m+'</table></div>');
    return '<tr class="detail"><td colspan="13"><div class="dwrap">'+sec.join('')+'</div></td></tr>';
  }

  function render(){
    var rows = sorted(filtered());
    renderStats(rows);
    var pages = Math.max(1, Math.ceil(rows.length/PAGE));
    if(st.page >= pages) st.page = pages-1;
    var slice = rows.slice(st.page*PAGE, st.page*PAGE+PAGE);

    var html = slice.map(function(h){
      var tr = '<tr class="row'+(st.open===h.id?' open':'')+'" data-id="'+h.id+'">'+
        '<td class="l"><span class="arrow">'+(st.open===h.id?'▾':'▸')+'</span></td>'+
        '<td class="l">'+h.id+'</td>'+
        '<td class="l">'+(h.fsa||'—')+'</td>'+
        '<td class="l">'+chips(h)+'</td>'+
        MEASURES.map(function(m){ return cell(val(h,m)); }).join('')+
        '<td class="tot">'+(h.total?money(h.total[st.band]):'—')+'</td></tr>';
      return tr + (st.open===h.id ? detail(h) : '');
    }).join('');

    document.getElementById('tb').innerHTML = html ||
      '<tr><td colspan="13" class="empty">No records match these filters.</td></tr>';

    document.getElementById('pager').innerHTML =
      '<button id="prev"'+(st.page===0?' disabled':'')+'>← Prev</button>'+
      '<span>Page '+(st.page+1)+' of '+pages.toLocaleString()+
      ' &middot; '+rows.length.toLocaleString()+' homes</span>'+
      '<button id="next"'+(st.page>=pages-1?' disabled':'')+'>Next →</button>';
    var p = document.getElementById('prev'), n = document.getElementById('next');
    if(p) p.onclick = function(){ if(st.page>0){ st.page--; render(); window.scrollTo(0,0); } };
    if(n) n.onclick = function(){ if(st.page<pages-1){ st.page++; render(); window.scrollTo(0,0); } };
  }

  function seg(id, key, cast){
    var el = document.getElementById(id);
    el.addEventListener('click', function(e){
      var b = e.target.closest('button');
      if(!b) return;
      [].forEach.call(el.querySelectorAll('button'), function(x){ x.classList.remove('on'); });
      b.classList.add('on');
      st[key] = cast ? cast(b.dataset.v) : b.dataset.v;
      render();
    });
  }
  seg('segBand', 'band', Number);

  document.getElementById('fMeasure').onchange = function(){ st.measure=this.value; st.page=0; render(); };
  document.getElementById('fBau').onchange     = function(){ st.bau=this.value;     st.page=0; render(); };
  document.getElementById('fSearch').oninput   = function(){ st.q=this.value;       st.page=0; render(); };

  document.querySelector('thead').addEventListener('click', function(e){
    var th = e.target.closest('th');
    if(!th || !th.dataset.s) return;
    if(st.sort === th.dataset.s) st.dir = -st.dir;
    else { st.sort = th.dataset.s; st.dir = -1; }
    st.page = 0; render();
  });

  document.getElementById('tb').addEventListener('click', function(e){
    var tr = e.target.closest('tr.row');
    if(!tr) return;
    st.open = (st.open === tr.dataset.id) ? null : tr.dataset.id;
    render();
  });

  render();
})();
</script>
</body>
</html>
"""


def main():
    with open(DATA_PATH, encoding='utf-8') as f:
        data_json = f.read()
    html = TEMPLATE.replace('__DATA_JSON__', data_json)
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f"wrote {OUT_PATH} ({len(html):,} bytes)")


if __name__ == '__main__':
    main()
