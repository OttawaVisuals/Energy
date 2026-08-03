// NOTE: PapaParse/pako removed — data now ships as pre-split JSON, no CSV
// parsing or gzip decompression needed client-side.
// Data ships on the gh-pages branch alongside these pages, so it is always
// same-origin: identical relative paths on localhost and in production.
const BASE_URL='./';
const FSA_JSON_BASE=`${BASE_URL}fsa_json/`;       // fsa_json/<PROV>/<FSA>.json + _index.json
const PROVINCE_JSON_BASE=`${BASE_URL}province_json/`; // province_json/<PROV>.json

const PROVINCES={
  CA:{name:'All of Canada',short:'CA'},
  AB:{name:'Alberta',short:'AB'},
  BC:{name:'British Columbia',short:'BC'},
  MB:{name:'Manitoba',short:'MB'},
  NB:{name:'New Brunswick',short:'NB'},
  NF:{name:'Newfoundland & Labrador',short:'NF'},
  NT:{name:'Northwest Territories',short:'NT'},
  NS:{name:'Nova Scotia',short:'NS'},
  NU:{name:'Nunavut',short:'NU'},
  ON:{name:'Ontario',short:'ON'},
  PE:{name:'Prince Edward Island',short:'PE'},
  QC:{name:'Quebec',short:'QC'},
  SK:{name:'Saskatchewan',short:'SK'},
};

let PROVINCE_CODE='CA'; // landing default — see #province-sel's selected option
let SELECTED_FSA='';          // '' = province-wide view, else FSA-view
let SELECTED_TYPE='';         // house-type filter, used by BOTH views (province dropdown
                               // drives the precomputed slice; FSA view filters FILTERED as before)
let MODE='none';              // 'none' | 'province' | 'fsa'

// Fixed hex per fuel so a given fuel always reads the same colour across the
// heating-fuel Sankey, the waterfall and the fuel-breakdown chart. Colours are
// neutral fuel identifiers, not outcome judgements — green/red are reserved
// for performance metrics (saved/used more) elsewhere in the UI, so a fuel
// switch here reads as "changed fuel", not "got better" or "got worse".
const FUEL_COLORS={
  'Oil':'#D85A30','Electricity':'#378ADD','Propane':'#B79A6A',
  'Mixed Wood':'#6B4C2A','Mixed wood':'#6B4C2A','Hardwood':'#8B6343',
  'Natural Gas':'#C8881A','Wood Pellets':'#A07040','Wood':'#6B4C2A'
};

const MEASURES=[
  {key:'Air_Tightness_Upgrade',        label:'Air sealing',           color:'#C8881A', ck:'secondary',
    tip:'Counted when air leakage dropped by more than 10% between the two audits.'},
  {key:'Roof_Insulation_Upgrade',       label:'Roof insulation',       color:'#0B2545', ck:'primary',
    tip:'Counted when roof/attic insulation value rose by more than 10% between the two audits.'},
  {key:'Foundation_Insulation_Upgrade', label:'Foundation insulation', color:'#1A7A55', ck:'pos',
    tip:'Counted when foundation insulation value rose by more than 10% between the two audits.'},
  {key:'Wall_Insulation_Upgrade',       label:'Wall insulation',       color:'#378ADD', ck:'blue',
    tip:'Counted when wall insulation value rose by more than 10% between the two audits.'},
  {key:'HeatPump_Addition',            label:'Heat pump added',        color:'#D85A30', ck:'fOil',
    tip:'Counted when no heat pump was recorded at the initial audit but one appears at the follow-up audit.'},
  {key:'Heating_Change',              label:'Heating system changed',  color:'#533AB7', ck:'purple',
    tip:'Counted when the recorded heating fuel or equipment type differs between the two audits.'},
  {key:'Windows_Change',              label:'Windows changed',         color:'#8A9BB0', ck:'tick',
    tip:'Counted when the recorded window code differs between the two audits.'},
  {key:'Floor_Insulation_Upgrade',     label:'Floor insulation',       color:'#5C6E82', ck:'axis',
    tip:'Counted when exposed-floor insulation value rose by more than 10% between the two audits.'},
];

// ── Section / measure icons ───────────────────────────────────────
// Hand-crafted minimal line-icons (viewBox 0 0 20 20, currentColor stroke,
// no fill). Kept as bare inner markup; icon() wraps them in the sized <svg
// class="ic">. injectIcons() (called on load) drops the right icon into every
// element carrying data-icon="<key>", so the static HTML stays free of SVG.
const ICONS={
  // measure / envelope categories
  roof:      '<path d="M2 10.5 10 4l8 6.5"/><path d="M5 9.7V16h10V9.7"/>',
  wall:      '<rect x="3" y="4" width="14" height="12" rx="1"/><path d="M3 8h14M3 12h14M8 4v4M12 8v4M8 12v4"/>',
  foundation:'<path d="M3 7h14v7H3z"/><path d="M3.5 17l1-2.2M8 17l1-2.2M12.5 17l1-2.2"/>',
  air:       '<path d="M2 6.5h9a2 2 0 1 0-2-2"/><path d="M2 10.5h12a2 2 0 1 1-2 2"/><path d="M2 14.5h6"/>',
  window:    '<rect x="4" y="3" width="12" height="14" rx="1"/><path d="M10 3v14M4 10h12"/>',
  heatpump:  '<rect x="2.5" y="5" width="15" height="10" rx="1"/><circle cx="10" cy="10" r="3"/><path d="M10 10l2-1"/>',
  heating:   '<path d="M10 2.5c.6 2.6 4 4 4 7.6a4 4 0 0 1-8 0c0-1.8 1-3 1.8-3.8.2 1 .9 1.8 1.8 2C9.4 6 9.4 4.2 10 2.5z"/>',
  floor:     '<path d="M3 6h14M3 10h14M3 14h14"/>',
  solar:     '<path d="M4.5 13h11l-1-6H5.5z"/><path d="M8 7v6M12 7v6M4 10h12"/><circle cx="15.5" cy="4" r="1.4"/>',
  // section headings
  results:   '<circle cx="10" cy="10" r="7.5"/><path d="M6.4 10.4l2.3 2.3 4.7-5.1"/>',
  energy:    '<path d="M11 2 4 11h5l-1 7 7-9h-5z"/>',
  upgraded:  '<path d="M15.6 4.4a3 3 0 0 1-4 4l-6.5 6.5a1.4 1.4 0 0 1-2-2L9.6 6.4a3 3 0 0 1 4-4l-2 2 1.9 1.9z"/>',
  homes:     '<path d="M3 10l7-6 7 6"/><path d="M5 9v7h10V9"/><path d="M9 16v-4h2v4"/>',
  equipment: '<circle cx="10" cy="10" r="2.7"/><path d="M10 2.5v2.2M10 15.3v2.2M2.5 10h2.2M15.3 10h2.2M4.7 4.7l1.6 1.6M13.7 13.7l1.6 1.6M15.3 4.7l-1.6 1.6M6.3 13.7l-1.6 1.6"/>',
  individual:'<path d="M6 5h11M6 10h11M6 15h11"/><circle cx="3" cy="5" r=".9"/><circle cx="3" cy="10" r=".9"/><circle cx="3" cy="15" r=".9"/>',
};
function icon(key){
  const inner=ICONS[key];
  return inner?`<svg class="ic" viewBox="0 0 20 20" aria-hidden="true">${inner}</svg>`:'';
}
function injectIcons(){
  document.querySelectorAll('[data-icon]').forEach(el=>{
    if(el.dataset.iconDone)return;
    const svg=icon(el.dataset.icon);
    if(svg){el.insertAdjacentHTML('afterbegin',svg);el.dataset.iconDone='1';}
  });
}

// ── Bin widths (single source of truth) ───────────────────────────
// FSA-mode renderers bin raw rows on the fly; these widths MUST match the
// ones used in precompute_province_stats.py, or the province-wide view and
// the FSA view will show differently-shaped histograms for the same data.
// Keeping them in one object makes that contract explicit and editable in
// one place instead of scattered as magic numbers across ~6 renderers.
const BINS={
  year:10,        // year-built decade buckets
  area:50,        // floor-area buckets (m²)
  eui:20,         // energy-use-intensity buckets (kWh/m²)
  ghg:1,          // GHG buckets (tCO2e/yr)
  heatloss:2,     // design heat loss buckets (kW — peak demand, not GJ/yr)
  savingsPct:1,   // energy-saving histogram (whole %)
  cost:250,       // annual energy-cost buckets ($/yr)
  hpSizing:0.1    // heat-pump sizing ratio buckets (capacity ÷ design heat loss)
};

// ── GHG scenarios (mirrors Python/ghg_factors.py / compute_ghg_scenarios.py —
// keep in sync) ── 4 ways of computing GHG: "reported" is the raw ERSGHG
// field (only ~50.5% of matched pairs have it); the other 3 are calculated
// from each home's own fuel consumption (~100% coverage). See Methodology,
// "GHG scenarios".
let GHG_SCENARIO='as_audited';
const GHG_SCENARIO_FIELDS={
  reported:['Pre_GHG','Post_GHG'],
  current:['Pre_GHG_current','Post_GHG_current'],
  current_corrected:['Pre_GHG_current_corrected','Post_GHG_current_corrected'],
  as_audited:['Pre_GHG_as_audited','Post_GHG_as_audited'],
};

// ── Energy-cost pricing (mirrors precompute_province_stats.py — keep in sync) ──
// Prices each home's per-fuel annual energy (the Pre_/Post_ *_Electricity /
// NaturalGas / Oil / Propane / Wood kWh columns) against current residential
// rates, so the page can show "$ saved" beside energy and GHG. Rates come from
// utility_rates_reference.json — one blended province-level number per fuel
// (electricity, gas, heating oil, propane, heating wood), covering all 13
// provinces/territories. Wood has no per-species breakdown in that dataset (a
// single flat $/kWh, cited "no province-level wood price source found"), and
// the retrofit rows only carry one combined Wood energy column anyway, so the
// same rate is applied to wood heating of any kind.
//
// IMPORTANT: every constant/formula here is duplicated in
// precompute_province_stats.py (search "priceVec"/"price_vec_for"). Change
// one, change the other, or the raw-row FSA $-chart stops matching the
// precomputed province $-chart for the same province.
//
// Simplifications (footnoted on the card): volumetric energy only (fixed
// monthly charges largely cancel pre-vs-post and are excluded); one blended
// $/kWh per province (rows carry annual kWh, not an hourly shape); today's
// rates applied to audits spanning 2004-2026 — "what these homes would save
// at current rates", not a historical bill.
const COST_RATES_URL=`${BASE_URL}utility_rates_reference.json`;
const COST_PROV_ALIAS={NF:'NL'}; // retrofit province code -> reference-dataset code
// invert the exact fuel->kWh factors ers_web_pipeline.py used to build the
// per-fuel columns, to recover m³/L for volumetric pricing
const KWH_PER_M3_GAS=10.3611,KWH_PER_L_OIL=10.7778,KWH_PER_L_PROP=7.0917;
const COST_CAP=8000,COST_DELTA_CAP=6000;          // clip for scale (match precompute)
const COST_PRICE_CACHE=new Map();                 // province code -> price vector | null
let COST_RATES_PROMISE=null;
function loadCostRates(){
  if(!COST_RATES_PROMISE)COST_RATES_PROMISE=fetchJSON(COST_RATES_URL).catch(()=>null);
  return COST_RATES_PROMISE;
}
// {elec,gas,oil,propane,wood} $/unit for a province, or null if not priced.
// Cached; fetched lazily from utility_rates_reference.json (single shared file).
function fetchPriceVec(prov){
  if(COST_PRICE_CACHE.has(prov))return Promise.resolve(COST_PRICE_CACHE.get(prov));
  return loadCostRates().then(data=>{
    const code=COST_PROV_ALIAS[prov]||prov;
    const p=data&&data.provinces&&data.provinces[code];
    const pv=p?{
      elec:p.electricity.cents_per_kwh/100,
      gas:p.natural_gas?p.natural_gas.dollars_per_m3:0,
      oil:p.heating_oil?p.heating_oil.cad_per_litre:0,
      propane:p.propane?p.propane.cad_per_litre:0,
      wood:p.heating_wood?p.heating_wood.cad_per_kwh:0}:null;
    COST_PRICE_CACHE.set(prov,pv);
    return pv;
  });
}
// Annual energy $ (volumetric only) for one home row at prefix 'Pre'|'Post'.
function homeCost(r,prefix,pv){
  const k=key=>num(r[`${prefix}_${key}`])||0;
  return k('Electricity')*pv.elec
       + k('NaturalGas')/KWH_PER_M3_GAS*pv.gas
       + k('Oil')/KWH_PER_L_OIL*pv.oil
       + k('Propane')/KWH_PER_L_PROP*pv.propane
       + k('Wood')*pv.wood;
}
let COST_PV=null; // price vector for the current province, or null (card hidden)
const fmtMoney=n=>'$'+Math.round(n).toLocaleString('en-CA');

// Imperial R-value = metric RSI × 5.678263 (1 RSI = 1 m²·K/W).
const RSI_TO_R=5.678;

// Pre/post bar palette. Pre = navy, Post = green — a colour-blind-safe pair
// (the old pre=red / post=green pairing is the classic red–green confusion
// case). Used by every pre/post comparison histogram.
// `let`, not `const`, and assigned by readPalette() rather than here: these
// are read at chart-build time, so rebinding them on a theme change is what
// carries the new palette into every pre/post histogram. Declaring them
// const at module scope would freeze the light-mode values (and, being above
// the PAL block, would read PAL in its temporal dead zone).
let PRE_LINE, POST_LINE;
// Shared Simple/Advanced sub-label fragments for the JS-built stat subs —
// same cap-simple/cap-advanced CSS pattern the static markup uses.
const OF_MATCHED='% of <span class="cap-simple">homes shown</span><span class="cap-advanced">matched homes</span>';



// ── Theme palette ─────────────────────────────────────────────────
// Single source of truth for every colour drawn into a canvas or SVG.
// Chart code must read PAL.* and never a hex literal, otherwise the
// colour-blind theme silently fails to reach the data (the page chrome
// recolours, the charts stay put) — that was the state before this.
//
// PAL is repopulated from the CSS custom properties on every theme
// change, so the themes stay defined in exactly one place: the :root
// blocks at the top of this file.
const PAL={};
// Alpha variants. Theme values are all 6-digit hex, so appending a
// 2-digit alpha is safe; the guard just means a malformed var degrades
// to an opaque colour rather than painting garbage.
function al(hex,aa){return(typeof hex==='string'&&hex[0]==='#'&&hex.length===7)?hex+aa:hex;}
// Choropleth ramps interpolate in RGB space and need triplets, not hex.
function hexToRgb(hex){
  const h=(hex||'').replace('#','');
  return h.length>=6?[parseInt(h.slice(0,2),16),parseInt(h.slice(2,4),16),parseInt(h.slice(4,6),16)]:[128,128,128];
}
function readPalette(){
  const cs=getComputedStyle(document.documentElement);
  const g=n=>cs.getPropertyValue(n).trim();
  Object.assign(PAL,{
    primary:g('--d-primary'),secondary:g('--d-secondary'),
    pos:g('--d-pos'),neg:g('--d-neg'),blue:g('--d-blue'),purple:g('--d-purple'),
    track:g('--d-track'),axis:g('--d-axis'),tick:g('--d-tick'),grid:g('--d-grid'),
    text:g('--text'),muted:g('--muted'),light:g('--light'),
    card:g('--card'),border:g('--border'),surface:g('--surface'),
    amber2:g('--amber2'),
    fElec:g('--f-elec'),fGas:g('--f-gas'),fOil:g('--f-oil'),
    fPropane:g('--f-propane'),fWood:g('--f-wood')
  });
  // Derived shades used by the Sankey and the map ramps.
  PAL.greyL=mix(PAL.tick,PAL.card,.45);
  PAL.pale=mix(PAL.track,PAL.card,.35);
  PAL.amberFaint=mix(PAL.secondary,PAL.card,.72);
  PAL.mapBase=mix(PAL.primary,PAL.card,.90);   // near-empty end of the count ramp
  PAL.mapNull=mix(PAL.tick,PAL.card,.55);      // "no data" shapes
  // Diverging saving-rate ramp: one neutral midpoint both directions fade
  // from, so "saves nothing" looks identical whether it is read as the top
  // of the negative ramp or the bottom of the positive one.
  PAL.rampBase=hexToRgb(mix(PAL.card,PAL.track,.35));
  PAL.rampPos=hexToRgb(PAL.pos);
  PAL.rampNeg=hexToRgb(PAL.neg);
  PAL.rampCountLo=hexToRgb(PAL.mapBase);
  PAL.rampCountHi=hexToRgb(PAL.primary);
  // MEASURES and FUEL_COLORS are module-level consts built before any theme
  // is resolved, so their literal hex values are light-mode defaults only.
  // Both are re-pointed at the live palette here, via the explicit `ck` key
  // rather than array position, so `m.color` keeps working at every existing
  // call site without those sites knowing a theme exists.
  MEASURES.forEach(m=>{if(m.ck&&PAL[m.ck])m.color=PAL[m.ck];});
  // Pre/post bar pair — see the declaration note above. Colour is red vs
  // green in light/dark (PAL.neg/PAL.pos); the cb theme repoints those same
  // vars at a blue/orange pair instead (see site-theme.css) since pre/post
  // is also told apart by point shape now, not colour alone.
  PRE_LINE=PAL.neg;
  POST_LINE=PAL.pos;
  // Fuel lookup rebuilt per theme — see FUEL_COLORS note above.
  Object.assign(FUEL_COLORS,{
    'Oil':PAL.fOil,'Electricity':PAL.fElec,'Propane':PAL.fPropane,
    'Mixed Wood':PAL.fWood,'Mixed wood':PAL.fWood,'Hardwood':mix(PAL.fWood,PAL.card,.25),
    'Natural Gas':PAL.fGas,'Wood Pellets':mix(PAL.fWood,PAL.card,.4)
  });
}
// Blend two hex colours; t is the share of `b`. Used to derive tints that
// track the theme instead of being frozen light-mode greys.
function mix(a,b,t){
  const A=hexToRgb(a),B=hexToRgb(b);
  return'#'+A.map((v,i)=>Math.round(v+(B[i]-v)*t).toString(16).padStart(2,'0')).join('');
}

const THEMES=['light','dark','cb'];
function initTheme(){
  let t=null;
  try{t=localStorage.getItem('theme');}catch(e){}
  if(!THEMES.includes(t)){
    t=(window.matchMedia&&window.matchMedia('(prefers-color-scheme: dark)').matches)?'dark':'light';
  }
  document.documentElement.dataset.theme=t;
  readPalette();
  syncThemeButtons(t);
}
function syncThemeButtons(t){
  document.querySelectorAll('.theme-btn').forEach(b=>{
    const on=b.dataset.theme===t;
    b.classList.toggle('active',on);
    b.setAttribute('aria-pressed',on?'true':'false');
  });
}
function setTheme(t){
  if(!THEMES.includes(t))t='light';
  document.documentElement.dataset.theme=t;
  try{localStorage.setItem('theme',t);}catch(e){}
  readPalette();
  syncThemeButtons(t);
  redrawAllCharts();
}
// Charts bake their colours in at construction time, so a theme change has
// to rebuild them from whatever data is already cached — never re-fetch.
function redrawAllCharts(){
  try{
    if(MODE==='province'&&typeof _lastProvincePayload!=='undefined'&&_lastProvincePayload){
      renderProvince(_lastProvincePayload);
    }else if(MODE==='fsa'&&ALL.length){
      render();
    }
    if(typeof paintFsaMap==='function'&&document.getElementById('fsa-map-svg'))paintFsaMap();
  }catch(e){console.error('theme redraw',e);}
}

let ALL=[],FILTERED=[],SORT='saving';
const charts={};
const FSA_CACHE=new Map();        // `${prov}|${fsa}` -> reconstructed row objects
const PROVINCE_SUMMARY_CACHE=new Map(); // prov -> parsed province_json payload
const FSA_INDEX_CACHE=new Map();  // prov -> [{fsa,row_count}, ...] from _index.json
let LOAD_TOKEN=0; // guards against a slow stale fetch landing after a newer one started
let _lastProvinceSlice=null; // last rendered province slice, for re-rendering equipment lists when lookups arrive
let _lastProvincePayload=null; // full province payload, for re-running Advanced-only renderers on mode switch

// 2021 Census housing-stock data, one ~1.1MB file keyed by FSA code (see
// Python/extract_fsa_census.py) — small enough to fetch once and keep
// entirely in memory, no per-FSA splitting needed like fsa_json/ has.
const CENSUS_JSON_URL=`${BASE_URL}census_json/fsa_census.json`;
// Province/Canada rollup of the same characteristics — see the header of
// Python/rollup_census.py for how each field is aggregated. Kept as its own
// (12 KB) file so the province view never pulls the 1.4 MB per-FSA payload.
const REGION_CENSUS_URL=`${BASE_URL}census_json/region_census.json`;
let REGION_CENSUS_DATA=null, REGION_CENSUS_FETCH=null;
function fetchRegionCensus(){
  if(REGION_CENSUS_DATA)return Promise.resolve(REGION_CENSUS_DATA);
  if(!REGION_CENSUS_FETCH)REGION_CENSUS_FETCH=fetchJSON(REGION_CENSUS_URL).then(d=>{REGION_CENSUS_DATA=d;return d;});
  return REGION_CENSUS_FETCH;
}
let CENSUS_DATA=null, CENSUS_FETCH=null;
function fetchCensusData(){
  if(CENSUS_DATA)return Promise.resolve(CENSUS_DATA);
  if(!CENSUS_FETCH)CENSUS_FETCH=fetchJSON(CENSUS_JSON_URL).then(d=>{CENSUS_DATA=d;return d;});
  return CENSUS_FETCH;
}

// ── Equipment code lookups (optional, fail-soft) ────────────────────
// Two small JSON dictionaries decode raw NRCan codes into readable names.
// Both are fetched once at startup; if either is missing (404) or hasn't
// landed yet, decoding silently falls back to the raw code, so the page
// works with or without these files present on the server.
//   lookup/ahri_numbers.json : { "<ahri>": "Brand \u00b7 Model" }
//                           or { "<ahri>": {"brand":"\u2026","model":"\u2026"} }
//   lookup/window_codes.json : { "<code>": "Description" }
//                           or { "<code>": {"description":"\u2026"} }
const AHRI_LOOKUP_URL=`${BASE_URL}lookup/ahri_numbers.json`;
const WINDOW_LOOKUP_URL=`${BASE_URL}lookup/window_codes.json`;
// Per-digit value->category tables (glazing/coating/fill/spacer/window_type/
// frame), separate from WINDOW_LOOKUP's whole-code descriptions — lets the
// frontend decode a code into named parts and compare pre vs post
// attribute-by-attribute (see renderWindowChanges).
const WINDOW_COMPONENTS_URL=`${BASE_URL}lookup/window_components.json`;
let AHRI_LOOKUP=null, WINDOW_LOOKUP=null, WINDOW_COMPONENTS=null;
function fetchLookups(){
  fetchJSON(AHRI_LOOKUP_URL).then(d=>{AHRI_LOOKUP=d;reRenderEquipmentLists();}).catch(()=>{AHRI_LOOKUP={};});
  fetchJSON(WINDOW_LOOKUP_URL).then(d=>{WINDOW_LOOKUP=d;reRenderEquipmentLists();}).catch(()=>{WINDOW_LOOKUP={};});
  fetchJSON(WINDOW_COMPONENTS_URL).then(d=>{WINDOW_COMPONENTS=d;reRenderEquipmentLists();}).catch(()=>{WINDOW_COMPONENTS={};});
}
function decodeAhri(code){
  const c=String(code).trim();
  // Verified pattern (see Python/check_ahri_directory.py): program 99 is the
  // ASHP program every number in the lookup was checked against. Always
  // built, even when the number hasn't resolved to cert data locally \u2014 we
  // know the reference number either way, so the directory page is always
  // reachable.
  const link=`<a href="https://www.ahridirectory.org/details/99/${encodeURIComponent(c)}" target="_blank" rel="noopener">AHRI ${c} \u2197</a>`;
  const hit=AHRI_LOOKUP&&AHRI_LOOKUP[c];
  if(!hit)return{main:c,sub:link,badges:[],brand:null,model:null};
  const isObj=typeof hit==='object';
  const name=typeof hit==='string'?hit:[hit.brand,hit.model].filter(Boolean).join(' \u00b7 ');
  const badges=[];
  const status=isObj?hit.model_status:null;
  if(status)badges.push({label:status,cls:/^active$/i.test(status)?'badge-deep':'badge-neg'});
  if(isObj){
    const cc=String(hit.cold_climate).toLowerCase();
    if(cc==='yes')badges.push({label:'Cold Climate',cls:'badge-medium'});
    else if(cc==='no')badges.push({label:'Not cold climate',cls:'badge-shallow'});
  }
  // Spec line straight off the archived AHRI certificate: heating capacity
  // at 47\u00b0F and 5\u00b0F outdoor, HSPF2 (seasonal heating efficiency) and COP at
  // 5\u00b0F when present \u2014 the numbers that matter for a Canadian winter.
  const specs=[];
  if(isObj){
    const btu=v=>{const n=parseFloat(v);return isNaN(n)?null:(n>=10000?Math.round(n/1000)+'k':Math.round(n).toLocaleString());};
    const h47=btu(hit.heating_capacity_47f_btuh),h5=btu(hit.heating_capacity_5f_btuh);
    if(h47)specs.push(`heats ${h47} BTU/h @ 47\u00b0F${h5?`, ${h5} @ 5\u00b0F`:''}`);
    const hspf=parseFloat(hit.hspf2);
    if(!isNaN(hspf))specs.push(`HSPF2 ${hspf}`);
    const cop5=parseFloat(hit.heating_cop_5f);
    if(!isNaN(cop5))specs.push(`COP ${cop5.toFixed(1)} @ 5\u00b0F`);
  }
  const sub=[link,...specs].join(' \u00b7 ');
  return name?{main:name,sub,badges,brand:isObj?hit.brand:null,model:isObj?hit.model:null}
             :{main:c,sub:link,badges,brand:null,model:null};
}
// Groups a list of {code,count} AHRI entries by outdoor unit (brand+model) --
// one outdoor unit is certified under many AHRI reference numbers (different
// indoor coil pairings, refrigerant lines, or test-procedure revisions can
// each certify differently, including on cold-climate status), so a single
// representative certificate per group would be arbitrary. Unresolved codes
// (no local cert data) each stand alone, since their true model is unknown.
function groupAhriByModel(items){
  const groups=new Map();
  for(const{code,count}of items){
    const c=String(code).trim();
    const d=decodeAhri(c);
    const key=(d.brand&&d.model)?`${d.brand}${d.model}`:`code:${c}`;
    let g=groups.get(key);
    if(!g){g={name:d.model?[d.brand,d.model].filter(Boolean).join(' \u00b7 '):c,total:0,certs:[]};groups.set(key,g);}
    g.total+=count;
    g.certs.push({code:c,count,...d});
  }
  for(const g of groups.values())g.certs.sort((a,b)=>b.count-a.count);
  return[...groups.values()].sort((a,b)=>b.total-a.total);
}
function decodeWindow(code){
  const c=String(code).trim();
  const hit=WINDOW_LOOKUP&&WINDOW_LOOKUP[c];
  if(!hit)return{main:c,sub:null};
  const desc=typeof hit==='string'?hit:(hit.description||hit.desc||'');
  return desc?{main:desc,sub:`Code ${c}`}:{main:c,sub:null};
}
// Re-render just the AHRI/window lists in the current mode (called when a
// lookup file resolves after the initial paint).
function reRenderEquipmentLists(){
  if(!isAdvancedMode())return; // not visible yet — renderAdvancedSections() covers it on switch
  if(MODE==='fsa'){renderAhriWindowFsa();renderWindowChanges();}
  else if(MODE==='province'&&_lastProvinceSlice)renderAhriWindowProvince(_lastProvinceSlice);
}

const WINDOW_ATTRS=[
  {key:'glazing',label:'Glazing (panes/coats)'},
  {key:'coating',label:'Coating/tint'},
  {key:'fill',label:'Gas fill'},
  {key:'spacer',label:'Spacer'},
  {key:'window_type',label:'Window type'},
  {key:'frame',label:'Frame material'},
];
// Decode a WINDOWCODE into its 6 named parts using window_components.json.
// Returns null if components haven't loaded yet, or the code doesn't
// cleanly decode (non-6-digit, or a digit value outside the standard table
// — i.e. a "user defined" code per NRCan's own column description).
function decodeWindowParts(code){
  if(!WINDOW_COMPONENTS||!code)return null;
  const s=String(code).trim().padStart(6,'0');
  if(s.length!==6)return null;
  const out={};
  for(let i=0;i<WINDOW_ATTRS.length;i++){
    const{key}=WINDOW_ATTRS[i];
    const table=WINDOW_COMPONENTS[key];
    const cat=table&&table[s[i]];
    if(!cat)return null;
    out[key]=cat;
  }
  return out;
}

const $=id=>document.getElementById(id);
// Dim the dashboard while a new selection's data is in flight (see the
// main.is-loading CSS rule). Set by the three load*() entry points, cleared
// at the end of render()/renderProvince() and on fetch failure.
const setLoading=on=>document.querySelector('main').classList.toggle('is-loading',!!on);
const flag=(r,k)=>r[k]==='True'||r[k]===true||r[k]==='1'||r[k]===1;
const num=v=>{const n=parseFloat(v);return v===null||v===undefined||isNaN(n)?null:n;};
const norm=t=>t?t.trim().replace(/\b\w/g,c=>c.toUpperCase()):'';
// Same +/− convention (with a real minus glyph U+2212) as the KPI blocks.
const fmtPct=v=>v>=0?`+${Math.round(v*100)}%`:`−${Math.round(-v*100)}%`;
const median=arr=>{
  const s=[...arr].filter(v=>v!=null).sort((a,b)=>a-b);
  if(!s.length)return null;
  const m=Math.floor(s.length/2);
  return s.length%2?s[m]:(s[m-1]+s[m])/2;
};
// Used only by the fuel waterfall: medians per fuel aren't additive (and a
// fuel used by <50% of homes medians to zero, hiding it entirely), whereas
// mean(Pre_Electricity)+mean(Pre_NaturalGas)+... == mean(Pre_TotalEnergy)
// exactly, which is what a cascading waterfall needs to stay internally
// consistent and keep minority fuels visible.
const mean=arr=>{
  const v=arr.filter(x=>x!=null);
  return v.length?v.reduce((s,x)=>s+x,0)/v.length:null;
};
function dc(key){if(charts[key]){charts[key].destroy();delete charts[key];}}

// Wire a Sankey flow path for interaction across input types:
//  - mouse: hover shows the floating tip and tracks the cursor
//  - touch: tap shows the tip near the finger (mobile had no tooltip before)
//  - keyboard: the path is focusable; focus shows the tip, blur hides it
//  - screen readers: the same text is exposed as an aria-label
// `anchorXY` returns {x,y} in client coords for positioning on touch/focus.
function attachFlowTip(el,tipText){
  el.style.cursor='pointer';
  el.setAttribute('tabindex','0');
  el.setAttribute('role','img');
  el.setAttribute('aria-label',tipText.replace(/ \| /g,', '));
  const tip=$('sankey-tip');
  const showAt=(x,y)=>{tip.textContent=tipText;tip.style.display='block';tip.style.left=(x+14)+'px';tip.style.top=(y-10)+'px';};
  const hide=()=>{tip.style.display='none';};
  el.addEventListener('mouseenter',e=>showAt(e.clientX,e.clientY));
  el.addEventListener('mousemove',e=>showAt(e.clientX,e.clientY));
  el.addEventListener('mouseleave',hide);
  el.addEventListener('touchstart',e=>{
    const t=e.touches[0];if(t)showAt(t.clientX,t.clientY);
    e.stopPropagation();
  },{passive:true});
  el.addEventListener('focus',()=>{
    const r=el.getBoundingClientRect();
    showAt(r.left+r.width/2,r.top+r.height/2);
  });
  el.addEventListener('blur',hide);
}
// One document-level tap outside any flow dismisses an open touch tip.
document.addEventListener('touchstart',e=>{
  if(!(e.target instanceof SVGPathElement))$('sankey-tip').style.display='none';
},{passive:true});

// ── Info "?" buttons ──────────────────────────────────────────────
// One shared floating tip for every .info-btn on the page; each button's
// text lives in its data-info attribute, so buttons can sit in static HTML
// or in re-rendered innerHTML without any per-button wiring (event
// delegation below survives innerHTML replacement).
let _infoTipEl=null,_infoTipFor=null,_infoHideTimer=null;
function cancelInfoHide(){if(_infoHideTimer){clearTimeout(_infoHideTimer);_infoHideTimer=null;}}
// Hide is deferred a beat so the pointer can travel from the "?" onto the tip
// (to click the methodology link) without the tip vanishing underneath it.
function scheduleInfoHide(){cancelInfoHide();_infoHideTimer=setTimeout(hideInfoTip,160);}
function showInfoTip(btn){
  cancelInfoHide();
  if(!_infoTipEl){
    _infoTipEl=document.createElement('div');_infoTipEl.id='info-tip';document.body.appendChild(_infoTipEl);
    // Hovering onto the tip keeps it open; leaving it schedules the hide.
    _infoTipEl.addEventListener('mouseenter',cancelInfoHide);
    _infoTipEl.addEventListener('mouseleave',scheduleInfoHide);
  }
  // textContent (not innerHTML) for the body so a data-info string can't inject
  // markup; the optional methodology link is appended as a real element.
  _infoTipEl.textContent='';
  const body=document.createElement('span');
  body.textContent=btn.dataset.info||'';
  _infoTipEl.appendChild(body);
  const method=btn.dataset.method;
  if(method){
    const a=document.createElement('a');
    a.className='info-tip-link';a.href='#'+method;
    a.textContent='Full details in methodology →';
    a.addEventListener('click',ev=>openMethodology(ev,method));
    _infoTipEl.appendChild(a);
  }
  _infoTipEl.style.display='block';
  const r=btn.getBoundingClientRect();
  const tw=_infoTipEl.offsetWidth,th=_infoTipEl.offsetHeight;
  const x=Math.min(Math.max(8,r.left+r.width/2-tw/2),window.innerWidth-tw-8);
  let y=r.bottom+8;
  if(y+th>window.innerHeight-8)y=r.top-th-8; // flip above if no room below
  _infoTipEl.style.left=x+'px';_infoTipEl.style.top=y+'px';
  if(_infoTipFor)_infoTipFor.classList.remove('open');
  btn.classList.add('open');_infoTipFor=btn;
}
function hideInfoTip(){
  cancelInfoHide();
  if(_infoTipEl)_infoTipEl.style.display='none';
  if(_infoTipFor)_infoTipFor.classList.remove('open');
  _infoTipFor=null;
}
// Opens the methodology <details> containing the target heading, scrolls to
// it and flashes it — so an info-tip link reliably lands on the right spot
// even though the section starts collapsed.
function openMethodology(e,id){
  if(e)e.preventDefault();
  hideInfoTip();
  const el=document.getElementById(id);
  if(!el)return;
  const det=el.closest('details');
  if(det&&!det.open)det.open=true;
  el.scrollIntoView({behavior:'smooth',block:'start'});
  el.classList.remove('method-flash');
  void el.offsetWidth; // restart the animation if it's already been flashed
  el.classList.add('method-flash');
}
// Click toggles (touch devices have no hover); clicking anywhere else closes.
document.addEventListener('click',e=>{
  if(e.target.closest('#info-tip'))return; // let clicks inside the tip (the link) through
  const b=e.target.closest('.info-btn');
  if(b){(_infoTipFor===b)?hideInfoTip():showInfoTip(b);return;}
  hideInfoTip();
});
document.addEventListener('mouseover',e=>{
  const b=e.target.closest('.info-btn');
  if(b&&_infoTipFor!==b)showInfoTip(b);
});
document.addEventListener('mouseout',e=>{
  if(e.target.closest&&e.target.closest('.info-btn'))scheduleInfoHide();
});
window.addEventListener('scroll',hideInfoTip,{passive:true});

// Filter bar compaction: once the page has scrolled past the hero, hide the
// field labels (Province, Your postal code, ...) to reclaim vertical space —
// desktop/laptop only (gated in CSS), mobile already stacks fields.
let _filterCompact=false;
function updateFilterCompact(){
  const compact=window.scrollY>72;
  if(compact===_filterCompact)return;
  _filterCompact=compact;
  const el=document.querySelector('.filter-sticky');
  if(el)el.classList.toggle('is-compact',compact);
}
window.addEventListener('scroll',updateFilterCompact,{passive:true});

// ── Load ──────────────────────────────────────────────────────────
// NOTE: the FSA JSON now ships already-decoded (human-readable BldgType,
// fuel, etc.), so the old ers_web_keys.json lookup table and CODED_COLS
// decode step have been removed — they were dead code and the keys file
// no longer exists on the server.

function fetchJSON(url){
  return fetch(url).then(r=>{
    if(!r.ok)throw new Error(`fetch failed (${r.status}): ${url}`);
    return r.json();
  });
}

// Reconstruct row objects from the {columns,rows} array-of-arrays format
// the split_fsa_json.py pipeline emits (saves ~75% bytes vs array-of-objects
// by not repeating ~50 key names on every row over the wire).
function reconstructRows(payload){
  const cols=payload.columns;
  return payload.rows.map(row=>{
    const obj={};
    for(let i=0;i<cols.length;i++)obj[cols[i]]=row[i];
    return obj;
  });
}

function fetchFsaIndex(prov){
  if(FSA_INDEX_CACHE.has(prov))return Promise.resolve(FSA_INDEX_CACHE.get(prov));
  return fetchJSON(`${FSA_JSON_BASE}${prov}/_index.json`)
    .then(idx=>{FSA_INDEX_CACHE.set(prov,idx);return idx;});
}

// Full audited population of the currently-selected FSA — unique HOUSEIDs with
// ANY D or E audit (matched or not), the denominator for the "retrofits
// selected" KPI. Read from the cached _index.json entry (dore_count). null when
// no single FSA is selected or the field is absent (older data).
function doreCountForSelectedFsa(){
  if(MODE!=='fsa'||!SELECTED_FSA)return null;
  const idx=FSA_INDEX_CACHE.get(PROVINCE_CODE);
  const e=idx&&idx.find(x=>x.fsa===SELECTED_FSA);
  return e&&e.dore_count!=null?e.dore_count:null;
}

// Audit-type composition {t,de,d,e,nc} of the selected FSA, from its
// _index.json entry — the fixed left-hand stages of the audit funnel. null when
// no FSA is selected or the field is absent (data built before the funnel).
function compositionForSelectedFsa(){
  if(MODE!=='fsa'||!SELECTED_FSA)return null;
  const idx=FSA_INDEX_CACHE.get(PROVINCE_CODE);
  const e=idx&&idx.find(x=>x.fsa===SELECTED_FSA);
  return e&&e.composition?e.composition:null;
}

function fetchFsaRows(prov,fsa){
  const key=`${prov}|${fsa}`;
  if(FSA_CACHE.has(key))return Promise.resolve(FSA_CACHE.get(key));
  console.time(`[load] fsa fetch ${fsa}`);
  return fetchJSON(`${FSA_JSON_BASE}${prov}/${fsa}.json`)
    .then(payload=>{
      const rows=reconstructRows(payload);
      FSA_CACHE.set(key,rows);
      console.timeEnd(`[load] fsa fetch ${fsa}`);
      return rows;
    });
}

function fetchProvinceSummary(prov){
  if(PROVINCE_SUMMARY_CACHE.has(prov))return Promise.resolve(PROVINCE_SUMMARY_CACHE.get(prov));
  console.time(`[load] province summary ${prov}`);
  return fetchJSON(`${PROVINCE_JSON_BASE}${prov}.json`)
    .then(payload=>{
      PROVINCE_SUMMARY_CACHE.set(prov,payload);
      console.timeEnd(`[load] province summary ${prov}`);
      return payload;
    });
}

// Populate the FSA dropdown for the current province from its _index.json.
// Replaces the old hardcoded PEI-only <option> list.
function populateFsaDropdown(prov,fsaIndex){
  const sel=$('fsa-sel');
  sel.innerHTML='<option value="">All areas (province-wide)</option>';
  fsaIndex.forEach(e=>{
    const o=document.createElement('option');
    o.value=e.fsa;
    o.textContent=`${e.fsa} (${e.row_count.toLocaleString()} homes)`;
    sel.appendChild(o);
  });
}

// Populate the house-type dropdown. Source of truth differs by mode:
// province mode -> keys of by_type in the precomputed summary (fixed, ~6 types)
// fsa mode -> distinct BldgType values actually present in that FSA's rows
function populateTypeDropdown(types){
  const sel=$('type-sel');
  const prevValue=sel.value;
  sel.innerHTML='<option value="">All types</option>';
  types.forEach(t=>{
    if(t==='All types')return; // already represented by the blank option
    const o=document.createElement('option');o.value=t;o.textContent=t;sel.appendChild(o);
  });
  if([...sel.options].some(o=>o.value===prevValue))sel.value=prevValue;
}

function load(){
  if(!PROVINCE_CODE)return;
  const prov=PROVINCES[PROVINCE_CODE];
  const myToken=++LOAD_TOKEN;
  setLoading(true);

  $('logo-province').textContent=prov.short;
  $('header-title').textContent=`${prov.name} · home energy retrofits`;
  $('footer-province').textContent=`${prov.name} audits`;
  $('header-badge').textContent=`EnerGuide data · ${prov.name} · loading…`;

  // Set the province's energy-price vector for the $-saved card. Use the cache
  // synchronously if warm (revisits render the card right away); otherwise
  // start null (card hidden) and fill it in when the fetch resolves. All 13
  // provinces/territories are priced now; only the synthetic "All of Canada"
  // aggregate (PROVINCE_CODE 'CA', no matching entry) stays unpriced.
  COST_PV=COST_PRICE_CACHE.has(PROVINCE_CODE)?COST_PRICE_CACHE.get(PROVINCE_CODE):null;
  fetchPriceVec(PROVINCE_CODE).then(pv=>{if(myToken!==LOAD_TOKEN)return;COST_PV=pv;refreshCostCard();});

  // Retrofit-cost province/national summary (proof of concept — separate
  // tree from fsa_json, see docs/RETROFIT_COSTS.md). Warmed the same way as
  // COST_PV above; the per-FSA per-house data is fetched separately in
  // loadFsaView(), only once an FSA is actually selected.
  loadRetroDict();
  RETRO_PROVINCE_SUMMARY=PROVINCE_CODE==='CA'?RETRO_CANADA_SUMMARY
    :(RETRO_SUMMARY_CACHE.has(PROVINCE_CODE)?RETRO_SUMMARY_CACHE.get(PROVINCE_CODE):null);
  const retroSummaryFetch=PROVINCE_CODE==='CA'?fetchRetroCanada():fetchRetroSummary(PROVINCE_CODE);
  retroSummaryFetch.then(s=>{if(myToken!==LOAD_TOKEN)return;RETRO_PROVINCE_SUMMARY=s;if(MODE==='province')renderRetrofitCost();});

  // "All of Canada" is a synthetic aggregate (see aggregate_canada.py) with
  // no per-FSA breakdown — fsa_json has no CA/ folder, so skip straight to
  // the province-wide (here, country-wide) summary view.
  if(PROVINCE_CODE==='CA'){
    SELECTED_FSA='';
    $('fsa-sel').innerHTML='<option value="">Not available for All of Canada</option>';
    $('fsa-sel').disabled=true;
    setMapAvailable(false); // no combined Canada-wide map yet — hide the Explore button
    loadProvinceView(myToken);
    return;
  }
  $('fsa-sel').disabled=false;

  // Warm the province-summary cache in parallel with the index fetch — the
  // two are independent, and province mode needs both, so fetching them
  // sequentially (the old behaviour) added a full round trip for nothing.
  if(!SELECTED_FSA)fetchProvinceSummary(PROVINCE_CODE).catch(()=>{});

  // Always (re)build the FSA dropdown for the selected province first —
  // needed whether the user ends up in province or FSA mode.
  fetchFsaIndex(PROVINCE_CODE).then(idx=>{
    if(myToken!==LOAD_TOKEN)return;
    populateFsaDropdown(PROVINCE_CODE,idx);
    // SELECTED_FSA may have been set before the dropdown existed (deep link
    // or postal-code jump): validate it against the index and sync the UI
    // (and the share URL, in case an invalid ?fsa= was dropped).
    if(SELECTED_FSA&&!idx.some(e=>e.fsa===SELECTED_FSA)){SELECTED_FSA='';updateShareUrl();}
    $('fsa-sel').value=SELECTED_FSA;
    loadFsaMap(PROVINCE_CODE,idx);
    if(SELECTED_FSA){
      loadFsaView(myToken);
    }else{
      loadProvinceView(myToken);
    }
  }).catch(err=>{
    if(myToken!==LOAD_TOKEN)return;
    console.error(err);
    setLoading(false);
    document.querySelector('main').innerHTML=
      `<div class="state-msg"><strong>Could not load data</strong>Could not fetch the FSA index for ${prov.name}.</div>`;
  });
}

function loadFsaView(myToken){
  MODE='fsa';
  const prov=PROVINCES[PROVINCE_CODE];
  setLoading(true);
  $('result-count').textContent='…';
  // Retrofit-cost companion fetch, in parallel with the row fetch — a
  // separate file/tree (retrofit_costs_json/), not part of fsa_json (see
  // docs/RETROFIT_COSTS.md). Joined to ALL rows by HOUSEID once both land;
  // a 404 (province/FSA not yet priced) resolves to an empty map, not an
  // error — the retrofit-cost card just stays hidden.
  RETRO_COST_MAP=new Map();
  const retroFetch=fetchRetroFsa(PROVINCE_CODE,SELECTED_FSA);
  fetchFsaRows(PROVINCE_CODE,SELECTED_FSA).then(rows=>{
    if(myToken!==LOAD_TOKEN)return;
    ALL=rows;
    const types=[...new Set(ALL.map(r=>r.BldgType).filter(Boolean))].sort();
    const fuels=[...new Set(ALL.map(r=>r.Pre_HeatFuel).filter(Boolean))].sort();
    populateTypeDropdown(types);
    const fuelEl=$('fuel-sel');fuelEl.innerHTML='<option value="">All fuels</option>';
    fuels.forEach(f=>{const o=document.createElement('option');o.value=f;o.textContent=f;fuelEl.appendChild(o);});
    showFsaFilterControls(true);
    updateAreaChip();
    $('header-badge').textContent=`EnerGuide data · ${prov.name} · ${SELECTED_FSA} · ${ALL.length.toLocaleString()} matched homes`;
    retroFetch.then(payload=>{
      if(myToken!==LOAD_TOKEN)return;
      const m=new Map();
      (payload.rows||[]).forEach(row=>m.set(String(row[0]),row));
      RETRO_COST_MAP=m;
      // This typically resolves AFTER the applyFilters()->render() call below
      // (retrofit_costs_json is a separate, independently-timed fetch), so
      // the initial renderTable() runs with an empty map — re-render both
      // once the join data actually lands.
      renderRetrofitCost();
      if(isAdvancedMode())renderTable();
    });
    applyFilters(); // re-applies type/fuel/depth on top of the freshly loaded FSA rows; render() -> renderAdvancedSections() covers census
  }).catch(err=>{
    if(myToken!==LOAD_TOKEN)return;
    console.error(err);
    setLoading(false);
    document.querySelector('main').innerHTML=
      `<div class="state-msg"><strong>Could not load data</strong>Could not fetch data for FSA ${SELECTED_FSA}.</div>`;
  });
}

function loadProvinceView(myToken){
  MODE='province';
  const prov=PROVINCES[PROVINCE_CODE];
  setLoading(true);
  $('result-count').textContent='…';
  fetchProvinceSummary(PROVINCE_CODE).then(payload=>{
    if(myToken!==LOAD_TOKEN)return;
    const types=Object.keys(payload.by_type);
    populateTypeDropdown(types);
    showFsaFilterControls(false);
    updateAreaChip();
    renderCensusRegion(PROVINCE_CODE,payload.total_rows);
    toggleHeatWaterfallCard(false); // no heating-only per-fuel figures in the province precompute
    toggleVintageCard(false); // needs row-level YearBuilt + measure flags, province view has none
    toggleWindowChangesCard(false); // needs paired per-home pre/post codes, province view has none
    $('header-badge').textContent=`EnerGuide data · ${prov.name} · ${payload.total_rows.toLocaleString()} matched homes`;
    renderProvince(payload);
  }).catch(err=>{
    if(myToken!==LOAD_TOKEN)return;
    console.error(err);
    setLoading(false);
    document.querySelector('main').innerHTML=
      `<div class="state-msg"><strong>Could not load data</strong>Could not fetch the province summary for ${prov.name}.</div>`;
  });
}

// Current-area pill: shows which FSA is selected and offers a one-click way
// back to the province-wide view (the job the FSA dropdown's "All areas"
// option used to do, now that the dropdown is gone).
function updateAreaChip(){
  const chip=$('area-chip');
  if(!chip)return;
  if(SELECTED_FSA){
    const prov=PROVINCES[PROVINCE_CODE];
    chip.style.display='';
    chip.innerHTML=`Area <strong>${SELECTED_FSA}</strong><button type="button" class="area-clear" onclick="clearArea()" aria-label="Show ${prov?prov.name:'province'}-wide instead">✕ show all of ${prov?prov.name:'the province'}</button>`;
  }else{
    chip.style.display='none';
    chip.innerHTML='';
  }
}
// Clear the selected area and fall back to the province-wide view. Routes
// through the hidden #fsa-sel so it runs the same path as any other
// area change (province render + map de-select).
function clearArea(){
  const fs=$('fsa-sel');
  fs.value='';
  fs.dispatchEvent(new Event('change',{bubbles:true}));
  $('pc-input').value='';showPcHint('');
}

// Fuel + depth filters are FSA-view only (see project notes): province-wide
// view only exposes FSA + house type. Hide/show the two extra controls
// and the reset button's behaviour accordingly.
function showFsaFilterControls(show){
  const display=show?'':'none';
  $('fuel-sel').closest('.filter-group').style.display=display;
  $('depth-sel').closest('.filter-group').style.display=display;
  $('measures-dd').closest('.filter-group').style.display=display;
}

function applyFilters(){
  // Only meaningful in FSA mode — province mode re-fetches/re-slices via
  // loadProvinceView()+renderProvince() instead.
  if(MODE!=='fsa'){return;}
  const type=$('type-sel').value,
        fuel=$('fuel-sel').value,depth=$('depth-sel').value,
        meas=selectedMeasures(); // AND semantics: home did at least all checked measures
  FILTERED=ALL.filter(r=>
    (!type||r.BldgType===type)&&
    (!fuel||r.Pre_HeatFuel===fuel)&&(!depth||flag(r,depth))&&
    meas.every(m=>flag(r,m)));
  render();
}
function resetFilters(){
  ['type-sel','fuel-sel','depth-sel'].forEach(id=>$(id).value='');
  clearMeasures();
  if(MODE==='fsa'){
    FILTERED=[...ALL];render();
  }else if(MODE==='province'){
    SELECTED_TYPE='';
    loadProvinceView(++LOAD_TOKEN);
  }
}

// ── Render ────────────────────────────────────────────────────────
function render(){
  $('table-card').style.display='';
  $('sec-individual').style.display='';
  const n=FILTERED.length;
  $('result-count').textContent=n.toLocaleString();
  $('small-n-warn').style.display=(n>0&&n<30)?'':'none';
  // Match-count line: matched homes fitting the current filters, and what
  // share that is of every HOUSEID in this FSA with ANY D or E audit
  // (matched or not) — dore_count comes from the _index.json entry.
  const dore=doreCountForSelectedFsa();
  $('match-count-extra').innerHTML=dore
    ?` · ${Math.round(n/dore*100)}% of ${dore.toLocaleString()} homes audited here`
    :'';
  const savings=FILTERED.map(r=>num(r.EnergySavingPct)).filter(v=>v!==null);
  const med=median(savings);
  $('s-median').textContent=med!==null?Math.round(med*100)+'%':'—';
  $('s-median-sub').innerHTML=med!==null?(med>=0?'<span class="cap-simple">typical energy saved</span><span class="cap-advanced">median energy saved</span>':'<span class="cap-simple">typical energy increase</span><span class="cap-advanced">median energy increased</span>'):'';
  const deep=FILTERED.filter(r=>flag(r,'Deep_Retrofit')).length;
  const hp=FILTERED.filter(r=>flag(r,'HeatPump_Addition')).length;
  const fs=FILTERED.filter(r=>flag(r,'FuelSwitch')).length;
  $('s-deep').textContent=deep.toLocaleString();
  $('s-deep-sub').innerHTML=n?`${Math.round(deep/n*100)}${OF_MATCHED}`:'';
  $('s-hp').textContent=hp.toLocaleString();
  $('s-hp-sub').innerHTML=n?`${Math.round(hp/n*100)}${OF_MATCHED}`:'';
  $('s-fs').textContent=fs.toLocaleString();
  $('s-fs-sub').innerHTML=n?`${Math.round(fs/n*100)}${OF_MATCHED}`:'';

  // Compute EUIs once here and pass to all consumers
  const preEUIs=FILTERED.map(r=>{const e=num(r.Pre_TotalEnergy),a=num(r.FloorArea);return(e&&a&&a>0)?e/a:null;}).filter(v=>v!==null);
  const postEUIs=FILTERED.map(r=>{const e=num(r.Post_TotalEnergy),a=num(r.FloorArea);return(e&&a&&a>0)?e/a:null;}).filter(v=>v!==null);
  // Headline "median saving" = median of each home's OWN (pre-post) change,
  // not median(pre)-median(post). The latter is the gap between two separate
  // medians, a figure no individual home experienced, and it wouldn't match
  // the per-home delta histogram drawn lower down. Same fix for GHG below.
  const euiDeltas=FILTERED.map(r=>{
    const e0=num(r.Pre_TotalEnergy),e1=num(r.Post_TotalEnergy),a=num(r.FloorArea);
    return(e0!=null&&e1!=null&&a&&a>0)?(e0-e1)/a:null;
  }).filter(v=>v!==null);
  const euiSave=median(euiDeltas);
  $('s-eui-saving').textContent=euiSave!=null?Math.round(euiSave):'—';
  window._euiMedianPre=Math.round(median(preEUIs)||0);
  window._euiMedianPost=Math.round(median(postEUIs)||0);

  const solarPost=FILTERED.filter(r=>num(r.Post_SolarPV)>0).length;
  $('s-solar').textContent=solarPost.toLocaleString();
  $('s-solar-sub').innerHTML=n?`${Math.round(solarPost/n*100)}${OF_MATCHED}`:'';

  const totalMeasureFlags=MEASURES.reduce((s,m)=>s+FILTERED.filter(r=>flag(r,m.key)).length,0);
  $('s-avg-measures').textContent=n?(totalMeasureFlags/n).toFixed(1):'—';

  toggleVintageCard(true);
  toggleWindowChangesCard(true);
  renderEUI(preEUIs,postEUIs,euiSave);renderGHG();renderCost();renderRetrofitCost();
  renderKPI(n,fs);renderInsulDist();renderMeasures(n);
  renderHist(savings);renderHeatLossComponents();
  renderAdvancedSections();
  setLoading(false);
}

// Renderers for cards/sections that are Advanced-only (see the data-mode=
// "advanced" attribute in the HTML — this is the JS-side half of the same
// split: visibility is CSS-driven, but there's no reason to spend Chart.js
// draw time on a chart nobody can see in Simple mode). Called from the end
// of render()/renderProvince() (gated, so a no-op while in Simple) and again
// from setViewMode() when switching into Advanced, using whichever data is
// currently cached — that's what makes the switch itself feel instant
// rather than re-fetching anything.
function renderAdvancedSections(){
  if(!isAdvancedMode())return;
  if(MODE==='fsa'){
    renderYearHist();renderAreaHist();renderTypeDonut();renderStoreyDonut();
    renderSankey();renderSolar(FILTERED.length);renderWaterfall();renderWaterfallHeating();renderAhriWindowFsa();
    renderVintageMeasures();renderWindowChanges();renderTable();
    renderHeatLoss();renderAuditYearChart();renderHPBackupFsa();renderHPSizing();
    const comp=compositionForSelectedFsa();
    renderFunnel(comp?{total:comp.t,de:comp.de,d:comp.d,e:comp.e,nc:comp.nc,
      matched:ALL.length,selected:FILTERED.length}:null);
    if(SELECTED_FSA)renderCensus(SELECTED_FSA,ALL.length);
  }else if(MODE==='province'){
    if(!_lastProvincePayload||!_lastProvinceSlice)return;
    renderProvinceHeatLoss(_lastProvinceSlice);
    renderProvinceYearHist(_lastProvincePayload);
    renderProvinceAreaHist(_lastProvincePayload);
    renderProvinceTypeDonut(_lastProvincePayload);
    renderProvinceStoreyDonut(_lastProvinceSlice);
    renderProvinceSankey(_lastProvinceSlice);
    renderProvinceSolar(_lastProvinceSlice);
    renderProvinceWaterfall(_lastProvinceSlice);
    renderAhriWindowProvince(_lastProvinceSlice);
    renderHPBackupProvince(_lastProvinceSlice);renderProvinceHPSizing(_lastProvinceSlice);
    renderProvinceAuditYearChart(_lastProvincePayload);
    const f=_lastProvincePayload.funnel;
    renderFunnel(f?{total:f.t,de:f.de,d:f.d,e:f.e,nc:f.nc,
      matched:f.matched,selected:_lastProvinceSlice.row_count||0}:null);
  }
}

// ── Year built histogram ──────────────────────────────────────────
// Inline legend rendered next to the card title (instead of Chart.js's own
// legend row) so stacked-bar charts don't need extra vertical space for it.
function setChartLegend(id,items){
  $(id).innerHTML=items.map(it=>`<div class="chart-legend-item"><span class="chart-legend-dot" style="background:${it.color}"></span>${it.label}</div>`).join('');
}

// Same boundaries as the census period_of_construction buckets, so the
// audited-homes histogram and the FSA-wide census line share one x-axis —
// needed to judge whether the audited sample is representative (see
// renderYearHist). "2022_plus" exists only on the audited side; the 2021
// census obviously has no data past 2021.
const CENSUS_PERIOD_BUCKETS=[
  {key:'1960_or_before',label:'1960 or before',test:y=>y<=1960},
  {key:'1961_1980',label:'1961–1980',test:y=>y>=1961&&y<=1980},
  {key:'1981_1990',label:'1981–1990',test:y=>y>=1981&&y<=1990},
  {key:'1991_2000',label:'1991–2000',test:y=>y>=1991&&y<=2000},
  {key:'2001_2005',label:'2001–2005',test:y=>y>=2001&&y<=2005},
  {key:'2006_2010',label:'2006–2010',test:y=>y>=2006&&y<=2010},
  {key:'2011_2015',label:'2011–2015',test:y=>y>=2011&&y<=2015},
  {key:'2016_2021',label:'2016–2021',test:y=>y>=2016&&y<=2021},
  {key:'2022_plus',label:'2022+',test:y=>y>=2022},
];

function renderYearHist(){
  dc('year');
  const counts=CENSUS_PERIOD_BUCKETS.map(()=>0);
  let n=0;
  FILTERED.forEach(r=>{
    const y=parseInt(r.YearBuilt);
    if(!y||y<1850||y>2030)return;
    const i=CENSUS_PERIOD_BUCKETS.findIndex(b=>b.test(y));
    if(i<0)return;
    counts[i]++;n++;
  });
  const labels=CENSUS_PERIOD_BUCKETS.map(b=>b.label);
  const auditedPct=counts.map(c=>n?Math.round(c/n*1000)/10:0);

  const draw=censusPct=>{
    setChartLegend('year-legend',censusPct
      ?[{label:'Audited homes',color:al(PAL.primary,'CC')},{label:'All FSA dwellings (census)',color:PAL.secondary}]
      :[{label:'Audited homes',color:al(PAL.primary,'CC')}]);
    const datasets=[{type:'bar',label:'Audited homes',data:auditedPct,backgroundColor:al(PAL.primary,'CC'),borderWidth:0,borderRadius:2,order:2}];
    if(censusPct)datasets.push({type:'line',label:'All FSA dwellings (census)',data:censusPct,borderColor:PAL.secondary,backgroundColor:PAL.secondary,pointRadius:3,borderWidth:2,tension:0.2,fill:false,order:1});
    dc('year');
    charts['year']=new Chart($('year-chart').getContext('2d'),{
      type:'bar',
      data:{labels,datasets},
      options:{responsive:true,maintainAspectRatio:false,
        plugins:{legend:{display:false},tooltip:{callbacks:{label:i=>`${i.dataset.label}: ${i.raw}%`}}},
        scales:{x:{ticks:{font:{size:10},color:PAL.tick,maxRotation:45},grid:{display:false}},
                y:{ticks:{font:{size:10},color:PAL.tick,callback:v=>v+'%'},grid:{color:PAL.track}}}}
    });
  };

  draw(null);
  if(!SELECTED_FSA)return;
  fetchCensusData().then(data=>{
    const c=data[SELECTED_FSA];
    if(!c||!c.period_of_construction)return;
    const totalDwellings=Object.values(c.period_of_construction).reduce((s,v)=>s+(v||0),0)||1;
    const censusPct=CENSUS_PERIOD_BUCKETS.map(b=>{
      const v=c.period_of_construction[b.key];
      return v!=null?Math.round(v/totalDwellings*1000)/10:null;
    });
    draw(censusPct);
  }).catch(()=>{});
}

// ── Floor area histogram ──────────────────────────────────────────
function renderAreaHist(){
  dc('area');
  const sdBins={},atBins={};
  FILTERED.forEach(r=>{
    const a=parseFloat(r.FloorArea);
    if(!a||a>700)return;
    const b=Math.floor(a/BINS.area)*BINS.area;
    const bins=r.BldgType==='Single Detached'?sdBins:atBins;
    bins[b]=(bins[b]||0)+1;
  });
  const labels=[...new Set([...Object.keys(sdBins),...Object.keys(atBins)])].map(Number).sort((a,b)=>a-b);
  setChartLegend('area-legend',[{label:'Single detached',color:al(PAL.primary,'CC')},{label:'Attached',color:al(PAL.blue,'CC')}]);
  charts['area']=new Chart($('area-chart').getContext('2d'),{
    type:'bar',
    data:{labels,datasets:[
      {label:'Single detached',data:labels.map(k=>sdBins[k]||0),backgroundColor:al(PAL.primary,'CC'),borderWidth:0,borderRadius:2},
      {label:'Attached',data:labels.map(k=>atBins[k]||0),backgroundColor:al(PAL.blue,'CC'),borderWidth:0,borderRadius:2},
    ]},
    options:{responsive:true,maintainAspectRatio:false,
      plugins:{legend:{display:false},tooltip:{callbacks:{title:i=>`${i[0].label}–${+i[0].label+50} m²`,label:i=>`${i.dataset.label}: ${i.raw.toLocaleString()} homes`}}},
      scales:{x:{stacked:true,ticks:{font:{size:10},color:PAL.tick,maxRotation:45},grid:{display:false}},
              y:{stacked:true,ticks:{font:{size:10},color:PAL.tick},grid:{color:PAL.track}}}}
  });
}

// ── Audits per year & type (D / E), selected vs filtered-out ──────────
// Every audit in the loaded FSA, counted by the year it was carried out: each
// matched pair contributes an initial (D, Pre_Year) and a follow-up (E,
// Post_Year) audit. Two stacked bars per year (D then E); the solid segment is
// homes in the current FILTERED selection, the faded segment the ones filtered
// out — so the reader sees when the selected retrofits happened against all
// audit activity. Recomputes on every render(), i.e. whenever filters change.
// Shared chart builder for the audits-per-year chart. `dSel/dUn/eSel/eUn` are
// {year: count} maps: selected vs filtered-out, for initial (D) and follow-up
// (E). Used by both the FSA view (from raw rows) and the province/Canada view
// (from precomputed d_year_bins/e_year_bins) so the two produce identical bars.
function drawAuditYearChart(dSel,dUn,eSel,eUn){
  dc('auditYear');
  const years=[...new Set([...Object.keys(dSel),...Object.keys(dUn),
    ...Object.keys(eSel),...Object.keys(eUn)].map(Number))].sort((a,b)=>a-b);
  const anyUnselected=years.some(y=>(dUn[y]||0)+(eUn[y]||0)>0);
  const NAVY=PAL.primary,GREEN=PAL.pos,NAVY_F=al(PAL.primary,'30'),GREEN_F=al(PAL.pos,'30');
  setChartLegend('audit-year-legend',[
    {label:'Initial (D)',color:NAVY},
    {label:'Follow-up (E)',color:GREEN},
    ...(anyUnselected?[{label:'Faded = filtered out',color:PAL.greyL}]:[]),
  ]);
  charts['auditYear']=new Chart($('audit-year-chart').getContext('2d'),{
    type:'bar',
    data:{labels:years,datasets:[
      {label:'Initial (D) · selected',    data:years.map(y=>dSel[y]||0),backgroundColor:NAVY,   stack:'D',borderWidth:0,borderRadius:2},
      {label:'Initial (D) · filtered out',data:years.map(y=>dUn[y]||0), backgroundColor:NAVY_F, stack:'D',borderWidth:0,borderRadius:2},
      {label:'Follow-up (E) · selected',    data:years.map(y=>eSel[y]||0),backgroundColor:GREEN,  stack:'E',borderWidth:0,borderRadius:2},
      {label:'Follow-up (E) · filtered out',data:years.map(y=>eUn[y]||0), backgroundColor:GREEN_F,stack:'E',borderWidth:0,borderRadius:2},
    ]},
    options:{responsive:true,maintainAspectRatio:false,animation:false,
      plugins:{legend:{display:false},tooltip:{filter:i=>i.raw>0,callbacks:{label:i=>`${i.dataset.label}: ${i.raw.toLocaleString()}`}}},
      scales:{x:{stacked:true,ticks:{font:{size:10},color:PAL.tick,maxRotation:45},grid:{display:false}},
              y:{stacked:true,ticks:{font:{size:10},color:PAL.tick},grid:{color:PAL.track}}}}
  });
}

function renderAuditYearChart(){
  const sel=new Set(FILTERED);
  const dSel={},dUn={},eSel={},eUn={};
  const bump=(o,y)=>{o[y]=(o[y]||0)+1;};
  ALL.forEach(r=>{
    const inSel=sel.has(r);
    const py=parseInt(r.Pre_Year),qy=parseInt(r.Post_Year);
    if(py>=1990&&py<=2035)bump(inSel?dSel:dUn,py);
    if(qy>=1990&&qy<=2035)bump(inSel?eSel:eUn,qy);
  });
  drawAuditYearChart(dSel,dUn,eSel,eUn);
}

// Province/Canada audits-per-year: precomputed per-slice year bins. The selected
// house type is solid, the rest of the province faded (mirrors the FSA view's
// selected-vs-filtered split). "All types" -> nothing faded. This is what makes
// the chart work province-wide and for All of Canada (the FSA path needs
// row-level Pre/Post_Year, which those views don't ship).
function renderProvinceAuditYearChart(payload){
  const allSlice=payload.by_type['All types']||{};
  const selSlice=payload.by_type[SELECTED_TYPE||'All types']||allSlice;
  const dAll=allSlice.d_year_bins||{},eAll=allSlice.e_year_bins||{};
  const dSelB=selSlice.d_year_bins||{},eSelB=selSlice.e_year_bins||{};
  const dSel={},dUn={},eSel={},eUn={};
  const split=(all,selB,outSel,outUn)=>{
    Object.keys(all).forEach(y=>{
      const s=selB[y]||0;outSel[y]=s;
      const u=(all[y]||0)-s;if(u>0)outUn[y]=u;
    });
  };
  split(dAll,dSelB,dSel,dUn);
  split(eAll,eSelB,eSel,eUn);
  drawAuditYearChart(dSel,dUn,eSel,eUn);
}

// ── Donut helper ──────────────────────────────────────────────────
// Draws category labels ("Name – 57%") on leader lines pointing out from
// each slice instead of a separate legend, so the donut is self-contained.
const donutLeaderLines={
  id:'donutLeaderLines',
  afterDraw(chart,args,opts){
    const meta=chart.getDatasetMeta(0);
    if(!meta||!meta.data.length)return;
    const narrow=opts&&opts.narrow;
    const {ctx,chartArea}=chart;
    const data=chart.data.datasets[0].data;
    const labels=chart.data.labels;
    const total=data.reduce((s,v)=>s+v,0);
    if(!total)return;
    const cx=(chartArea.left+chartArea.right)/2;
    const cy=(chartArea.top+chartArea.bottom)/2;
    const pts=meta.data.map((arc,i)=>{
      const {startAngle,endAngle,outerRadius}=arc;
      const mid=(startAngle+endAngle)/2;
      const side=Math.cos(mid)>=0?1:-1;
      return{
        ex:cx+Math.cos(mid)*outerRadius,ey:cy+Math.sin(mid)*outerRadius,
        outerRadius,side,
        pct:Math.round(data[i]/total*100),label:labels[i]
      };
    });
    const minGap=14;
    // 3-pass relaxation: push down for overlaps, pull up against the bottom
    // edge, then re-settle — keeps each label close to its slice's natural
    // angle (so spacing tracks the actual value split) instead of always
    // cascading every label toward the bottom of the chart.
    function layout(side){
      const arr=pts.filter(p=>p.side===side).sort((a,b)=>a.ey-b.ey);
      const n=arr.length;
      if(!n)return;
      const top=chartArea.top+8,bottom=chartArea.bottom-8;
      arr[0].labelY=Math.max(arr[0].ey,top);
      for(let i=1;i<n;i++)arr[i].labelY=Math.max(arr[i].ey,arr[i-1].labelY+minGap);
      arr[n-1].labelY=Math.min(arr[n-1].labelY,bottom);
      for(let i=n-2;i>=0;i--)arr[i].labelY=Math.min(arr[i].labelY,arr[i+1].labelY-minGap);
      arr[0].labelY=Math.max(arr[0].labelY,top);
      for(let i=1;i<n;i++)arr[i].labelY=Math.max(arr[i].labelY,arr[i-1].labelY+minGap);
    }
    layout(-1);layout(1);
    ctx.save();
    ctx.font=narrow?'9px Inter, sans-serif':'11px Inter, sans-serif';
    ctx.lineWidth=1;
    pts.forEach(p=>{
      const elbowX=cx+p.side*(p.outerRadius+(narrow?5:10));
      const labelX=cx+p.side*(p.outerRadius+(narrow?16:32));
      ctx.strokeStyle=PAL.pale;
      ctx.beginPath();
      ctx.moveTo(p.ex,p.ey);
      ctx.lineTo(elbowX,p.labelY);
      ctx.lineTo(labelX-p.side*4,p.labelY);
      ctx.stroke();
      ctx.fillStyle=PAL.text;
      ctx.textAlign=p.side>=0?'left':'right';
      ctx.textBaseline='middle';
      ctx.fillText(`${p.label} – ${p.pct}%`,labelX,p.labelY);
    });
    ctx.restore();
  }
};
function donut(canvasId,countMap,chartKey,n){
  dc(chartKey);
  const entries=Object.entries(countMap).sort((a,b)=>b[1]-a[1]);
  const top=entries.slice(0,5);
  const other=entries.slice(5).reduce((s,[,v])=>s+v,0);
  if(other>0)top.push(['Other',other]);
  const COLS=[PAL.primary,PAL.pos,PAL.secondary,PAL.blue,PAL.fOil,PAL.tick];
  // Leader-line labels need side padding to sit in; on a narrow phone
  // screen 95px each side would swallow the whole canvas, so shrink it
  // (and the plugin's own offsets) when the viewport is small.
  const narrow=window.innerWidth<480;
  const padX=narrow?40:95;
  charts[chartKey]=new Chart($(canvasId).getContext('2d'),{
    type:'doughnut',
    plugins:[donutLeaderLines],
    data:{labels:top.map(e=>e[0]),datasets:[{data:top.map(e=>e[1]),backgroundColor:COLS,borderWidth:2,borderColor:'#fff',hoverOffset:6}]},
    options:{responsive:true,maintainAspectRatio:false,cutout:'55%',
      layout:{padding:{left:padX,right:padX,top:8,bottom:8}},
      plugins:{legend:{display:false},donutLeaderLines:{narrow},
        tooltip:{callbacks:{label:i=>`${i.label}: ${i.raw.toLocaleString()} (${Math.round(i.raw/n*100)}%)`}}}}
  });
}
// Best-effort cross-walk from EnerGuide BldgType strings to the census's
// 8 dwelling_type buckets, so the two can be compared on one chart. The two
// taxonomies don't line up exactly (e.g. a "Detached Duplex" — a standalone
// building with 2 units — has no clean census equivalent; "Apartment" could
// be low- or high-rise) — this is an approximation, not an exact mapping.
const BLDG_TO_CENSUS_TYPE={
  'Single Detached':'single_detached',
  'Double/Semi-Detached':'semi_detached','Double/Semi Detached':'semi_detached',
  'Attached Duplex':'semi_detached','Duplex (Non-MURB)':'semi_detached',
  'Row House, End Unit':'row_house','Row House, Middle Unit':'row_house',
  'Row, End Unit':'row_house','Row, Middle Unit':'row_house',
  'Apartment Row':'row_house','Attached Triplex':'row_house',
  'Apartment':'apt_low_rise','Detached Triplex':'apt_low_rise','Triplex (Non-MURB)':'apt_low_rise',
  'Detached Duplex':'duplex_apt',
  'Mobile Home':'movable',
};

function renderTypeDonut(){
  const c={};FILTERED.forEach(r=>{if(r.BldgType)c[r.BldgType]=(c[r.BldgType]||0)+1;});

  if(!SELECTED_FSA){
    setChartLegend('type-legend',[]);
    donut('type-chart',c,'type',FILTERED.length);
    return;
  }
  fetchCensusData().then(data=>{
    const census=data[SELECTED_FSA]&&data[SELECTED_FSA].dwelling_type;
    if(!census){
      setChartLegend('type-legend',[]);
      donut('type-chart',c,'type',FILTERED.length);
      return;
    }
    const auditedByCensusType={};
    Object.entries(c).forEach(([bldg,n])=>{
      const k=BLDG_TO_CENSUS_TYPE[bldg]||'other_single_attached';
      auditedByCensusType[k]=(auditedByCensusType[k]||0)+n;
    });
    const auditedTotal=Object.values(auditedByCensusType).reduce((s,v)=>s+v,0)||1;
    const censusTotal=Object.values(census).reduce((s,v)=>s+(v||0),0)||1;
    const keys=Object.keys(DWELLING_TYPE_LABELS).filter(k=>(auditedByCensusType[k]||0)+(census[k]||0)>0);

    // Grouped bars (not a 2nd donut ring) — easier to actually compare two
    // distributions' shapes than two concentric rings of similar hue.
    dc('type');
    setChartLegend('type-legend',[
      {label:'Audited homes',color:al(PAL.primary,'CC')},
      {label:'All FSA dwellings (census)',color:PAL.secondary},
    ]);
    keys.sort((a,b)=>(census[b]||0)/censusTotal-(census[a]||0)/censusTotal);
    charts['type']=new Chart($('type-chart').getContext('2d'),{
      type:'bar',
      data:{labels:keys.map(k=>DWELLING_TYPE_LABELS[k]),datasets:[
        {label:'Audited homes',data:keys.map(k=>Math.round((auditedByCensusType[k]||0)/auditedTotal*1000)/10),
          backgroundColor:al(PAL.primary,'CC'),borderWidth:0,borderRadius:2},
        {label:'All FSA dwellings',data:keys.map(k=>Math.round((census[k]||0)/censusTotal*1000)/10),
          backgroundColor:PAL.secondary,borderWidth:0,borderRadius:2},
      ]},
      options:{responsive:true,maintainAspectRatio:false,
        plugins:{legend:{display:false},tooltip:{callbacks:{label:i=>`${i.dataset.label}: ${i.raw}%`}}},
        scales:{x:{ticks:{font:{size:10},color:PAL.tick,maxRotation:45},grid:{display:false}},
                y:{ticks:{font:{size:10},color:PAL.tick,callback:v=>v+'%'},grid:{color:PAL.track}}}}
    });
  }).catch(()=>{
    setChartLegend('type-legend',[]);
    donut('type-chart',c,'type',FILTERED.length);
  });
}
function renderStoreyDonut(){
  const MAP={'split entry / raised basement':'Split entry','two and a half':'2.5 storeys',
    'three storeys':'3 storeys','two storeys':'2 storeys','one storey':'1 storey',
    'one and a half':'1.5 storeys','split level':'Split level','split entry/raised base.':'Split entry'};
  const c={};
  FILTERED.forEach(r=>{const key=(r.Storeys||'').toLowerCase();const s=MAP[key]||r.Storeys||'Unknown';c[s]=(c[s]||0)+1;});
  donut('storey-chart',c,'storey',FILTERED.length);
}

// ── Sankey ────────────────────────────────────────────────────────
// Wood species (Softwood/Hardwood/Mixed Wood/Wood Pellets) each individually
// too small to read on the Sankey and cluttering it with near-duplicate
// nodes -- collapsed into one 'Wood' node. Matches the same collapse
// precompute_province_stats.py applies to sankey_flows for province/CA mode.
function sankeyFuelLabel(f){
  return/wood/i.test(f)?'Wood':f;
}
function renderSankey(){
  const svg=$('sankey-svg');svg.innerHTML='';
  if(!FILTERED.length)return;
  const flows={};
  FILTERED.forEach(r=>{
    const pf=sankeyFuelLabel(r.Pre_HeatFuel),qf=sankeyFuelLabel(r.Post_HeatFuel);
    if(!pf||!qf)return;
    const k=`${pf}|||${qf}`;
    if(!flows[k])flows[k]={pre:0,post:0};
    flows[k].pre+=(num(r.Pre_TotalEnergy)||0);
    flows[k].post+=(num(r.Post_TotalEnergy)||0);
  });
  const preMap={},postMap={};
  Object.entries(flows).forEach(([k,v])=>{
    const [a,b]=k.split('|||');
    preMap[a]=(preMap[a]||0)+v.pre;
    postMap[b]=(postMap[b]||0)+v.post;
  });
  const preFuels=Object.entries(preMap).sort((a,b)=>b[1]-a[1]).map(e=>e[0]);
  const postFuels=Object.entries(postMap).sort((a,b)=>b[1]-a[1]).map(e=>e[0]);
  const totalPre=Object.values(preMap).reduce((s,v)=>s+v,0);
  const totalPost=Object.values(postMap).reduce((s,v)=>s+v,0);
  const cw=svg.parentElement.clientWidth||700;
  const W=Math.max(cw,500),H=420,PAD=10,BAR=14,LX=145,RX=W-145;
  svg.setAttribute('viewBox',`0 0 ${W} ${H}`);
  svg.setAttribute('height',H);
  // Gap reserved between stacked category bars on each side.
  const GAP=20;
  const usablePre=H-PAD*2-20-(preFuels.length-1)*GAP;
  const usablePost=H-PAD*2-20-(postFuels.length-1)*GAP;
  // One shared GWh-per-pixel scale for BOTH sides, so bar heights stay
  // absolutely comparable across pre vs post (a 17.6 GWh bar should look
  // bigger than a 13.0 GWh bar no matter which side it's on) — using each
  // side's own total independently, as before, normalizes each side to
  // its own 100%, which hides any difference in total energy between
  // sides. The scale is capped by whichever side is tighter on room so
  // neither stack overflows its half of the chart.
  const scale=Math.min(usablePre/totalPre,usablePost/totalPost);

  function layoutNodes(fuels,map,x){
    let y=PAD;
    return fuels.map(f=>{
      const h=Math.max(3,map[f]*scale);
      const node={f,x,y,h};y+=h+GAP;return node;
    });
  }
  const preNodes=layoutNodes(preFuels,preMap,LX);
  const postNodes=layoutNodes(postFuels,postMap,RX);
  const preNM={},postNM={};
  preNodes.forEach(n=>preNM[n.f]=n);
  postNodes.forEach(n=>postNM[n.f]=n);
  const preUsed={},postUsed={};
  preNodes.forEach(n=>{preUsed[n.f]=0;});
  postNodes.forEach(n=>{postUsed[n.f]=0;});

  // Each flow's ribbon is a trapezoid: width on the left is v.pre*scale
  // (so all flows out of a pre-node sum exactly to that node's height),
  // width on the right is v.post*scale (same for the post-node) — using
  // the same shared scale as the bars above so flow widths stay
  // consistent with them.
  const flowList=Object.entries(flows).sort((a,b)=>b[1].pre-a[1].pre);
  flowList.forEach(([k,v])=>{
    const [a,b]=k.split('|||');
    const pn=preNM[a],qn=postNM[b];if(!pn||!qn)return;
    const fhPre=Math.max(2,v.pre*scale);
    const fhPost=Math.max(2,v.post*scale);
    const py=pn.y+preUsed[a],qy=qn.y+postUsed[b];
    preUsed[a]+=fhPre;postUsed[b]+=fhPost;
    const same=a===b;
    const col=same?PAL.pale:(FUEL_COLORS[a]||PAL.tick);
    const mx=(LX+BAR+RX)/2;
    const path=`M${LX+BAR},${py} C${mx},${py} ${mx},${qy} ${RX},${qy} L${RX},${qy+fhPost} C${mx},${qy+fhPost} ${mx},${py+fhPre} ${LX+BAR},${py+fhPre}Z`;
    const el=document.createElementNS('http://www.w3.org/2000/svg','path');
    el.setAttribute('d',path);
    el.setAttribute('fill',col);
    el.setAttribute('opacity',same?'0.45':'0.7');
    const tipText=`${a} → ${b} | Pre: ${(v.pre/1e6).toFixed(2)} GWh | Post: ${(v.post/1e6).toFixed(2)} GWh | Change: ${((v.post-v.pre)/1e6).toFixed(2)} GWh`;
    attachFlowTip(el,tipText);
    svg.appendChild(el);
  });

  function drawNodes(nodes,isLeft){
    nodes.forEach(n=>{
      const rect=document.createElementNS('http://www.w3.org/2000/svg','rect');
      rect.setAttribute('x',n.x);rect.setAttribute('y',n.y);
      rect.setAttribute('width',BAR);rect.setAttribute('height',Math.max(3,n.h));
      rect.setAttribute('fill',FUEL_COLORS[n.f]||PAL.tick);rect.setAttribute('rx',2);
      svg.appendChild(rect);
      const t=document.createElementNS('http://www.w3.org/2000/svg','text');
      const tx=isLeft?n.x-6:n.x+BAR+6;
      t.setAttribute('x',tx);t.setAttribute('y',n.y+Math.max(3,n.h)/2+4);
      t.setAttribute('text-anchor',isLeft?'end':'start');
      t.setAttribute('font-size','11');t.setAttribute('fill',PAL.text);
      t.setAttribute('font-family','Inter,sans-serif');
      const ghw=isLeft?(preMap[n.f]||0):(postMap[n.f]||0);
      t.textContent=`${n.f} (${(ghw/1e6).toFixed(1)} GWh)`;
      svg.appendChild(t);
    });
  }
  drawNodes(preNodes,true);drawNodes(postNodes,false);
}

// ── Audit funnel ───────────────────────────────────────────────────
// A left→right funnel from an area's FULL audited population down to the
// matched homes matching the current filters. Four stages:
//   1  All audited homes (any D/E/P/N evaluation)
//   2  by composition: Both D&E (continues), D only, E only, New build (P/N)
//   3  Both D&E → Matched pairs (+ Not paired: >1 audit / E not after D / a
//      structural change disqualified the pair)
//   4  Matched pairs → Meets filters (+ Filtered out)
// Stages 1-3 are FIXED for the area (recomputed only on area switch); only the
// last split tracks the filters. `cfg` carries the raw stage counts:
//   {total, de, d, e, nc, matched, selected}
// derived leaks (notpaired = de-matched, filteredout = matched-selected) are
// computed here so callers only pass what they measure directly.
function renderFunnel(cfg){
  const card=$('funnel-card');
  const svg=$('funnel-svg');svg.innerHTML='';
  if(!cfg||!(cfg.total>0)){if(card)card.style.display='none';return;}
  if(card)card.style.display='';

  const total=cfg.total;
  const de=Math.min(cfg.de||0,total);
  const dOnly=cfg.d||0,eOnly=cfg.e||0,nc=cfg.nc||0;
  const matched=Math.min(cfg.matched||0,de);
  const notpaired=Math.max(0,de-matched);
  const selected=Math.min(cfg.selected!=null?cfg.selected:matched,matched);
  const filteredout=Math.max(0,matched-selected);

  // AMBER/AMBERF give column 3 (your selection) its own hue distinct from
  // column 2's green (matched pairs) — previously both "kept" nodes shared
  // GREEN, so the 2nd and 3rd columns were hard to tell apart at a glance.
  const NAVY=PAL.primary,BLUE=PAL.blue,GREEN=PAL.pos,GREY=PAL.tick,
        GREYL=PAL.greyL,TAN=PAL.fPropane,PALE=PAL.pale,
        AMBER=PAL.amber2,AMBERF=PAL.amberFaint;

  const cw=svg.parentElement.clientWidth||700;
  const W=Math.max(cw,520),H=360,PAD=18,BAR=13;
  svg.setAttribute('viewBox',`0 0 ${W} ${H}`);svg.setAttribute('height',H);
  const usableH=H-PAD*2,GAP=7;
  // The composition column (Both D&E / D-only / E-only / New build) stacks the
  // most nodes, so its inter-node gaps are the binding constraint — bake that
  // gap budget into the scale (up to 3 gaps for 4 nodes) so no column overflows
  // the canvas. Zero-count nodes just leave a little slack.
  const scale=(usableH-3*GAP)/total;

  const X0=8,X1=Math.round(W*0.30),X2=Math.round(W*0.56),X3=W-104;
  const nodes={};
  const place=(key,x,y,count,color,label,side)=>{
    const h=count>0?Math.max(2,count*scale):0;
    nodes[key]={x,y,h,count,color,label,side};return h;
  };
  // col0
  place('total',X0,PAD,total,NAVY,'All audited homes','right');
  // col1: de, d, e, nc (trunk 'de' on top so the continuing flow hugs the top)
  let y=PAD;
  y+=place('de',X1,y,de,BLUE,'Both D & E','right')+GAP;
  y+=place('d',X1,y,dOnly,GREY,'Initial (D) only','right')+GAP;
  y+=place('e',X1,y,eOnly,GREYL,'Follow-up (E) only','right')+GAP;
  place('nc',X1,y,nc,TAN,'New build (P/N)','right');
  // col2: matched, notpaired — stacked from the 'de' node's top
  y=nodes.de.y;
  y+=place('matched',X2,y,matched,GREEN,'Matched pairs','right')+GAP;
  place('notpaired',X2,y,notpaired,PALE,'Not paired','right');
  // col3: selected, filteredout — stacked from the 'matched' node's top
  y=nodes.matched.y;
  y+=place('selected',X3,y,selected,AMBER,'Meets filters','left')+GAP;
  place('filteredout',X3,y,filteredout,AMBERF,'Filtered out','left');

  const NS='http://www.w3.org/2000/svg';
  const pct=c=>Math.round(c/total*100);
  // Ribbons first, so node bars + labels paint on top.
  const drawRibbons=(pk,order)=>{
    const p=nodes[pk];let off=0;
    order.forEach(ck=>{
      const c=nodes[ck];if(!c||c.count<=0)return;
      const x1=p.x+BAR,x2=c.x,y1=p.y+off,y2=c.y,h=c.h,mx=(x1+x2)/2;
      const path=`M${x1},${y1} C${mx},${y1} ${mx},${y2} ${x2},${y2} L${x2},${y2+h} C${mx},${y2+h} ${mx},${y1+h} ${x1},${y1+h}Z`;
      const el=document.createElementNS(NS,'path');
      el.setAttribute('d',path);el.setAttribute('fill',c.color);el.setAttribute('opacity','0.5');
      attachFlowTip(el,`${c.label} · ${c.count.toLocaleString()} homes (${pct(c.count)}% of all audited)`);
      svg.appendChild(el);
      off+=h;
    });
  };
  drawRibbons('total',['de','d','e','nc']);
  drawRibbons('de',['matched','notpaired']);
  drawRibbons('matched',['selected','filteredout']);

  // Node bars + haloed labels.
  Object.values(nodes).forEach(n=>{
    if(n.count<=0)return;
    const rect=document.createElementNS(NS,'rect');
    rect.setAttribute('x',n.x);rect.setAttribute('y',n.y);
    rect.setAttribute('width',BAR);rect.setAttribute('height',n.h);
    rect.setAttribute('fill',n.color);rect.setAttribute('rx',2);
    attachFlowTip(rect,`${n.label} · ${n.count.toLocaleString()} homes (${pct(n.count)}% of all audited)`);
    svg.appendChild(rect);
    const t=document.createElementNS(NS,'text');
    const tx=n.side==='left'?n.x-6:n.x+BAR+6;
    t.setAttribute('x',tx);t.setAttribute('y',n.y+n.h/2+4);
    t.setAttribute('text-anchor',n.side==='left'?'end':'start');
    t.setAttribute('font-size','11');t.setAttribute('font-family','Inter,sans-serif');
    t.setAttribute('fill',PAL.text);t.setAttribute('stroke',PAL.card);
    t.setAttribute('stroke-width','3');t.setAttribute('paint-order','stroke');
    t.textContent=`${n.label} · ${n.count.toLocaleString()}`;
    svg.appendChild(t);
  });

  setChartLegend('funnel-legend',[
    {label:'Both D & E',color:BLUE},
    {label:'Matched pairs',color:GREEN},
    {label:"Can't be paired",color:GREY},
    {label:'New build (P/N)',color:TAN},
    {label:'Meets your filters',color:AMBER},
  ]);
}

// ── EUI ───────────────────────────────────────────────────────────
function renderEUI(preEUIs,postEUIs,saveMedian){
  const preM=median(preEUIs),postM=median(postEUIs);
  const sv=saveMedian!=null?Math.round(saveMedian):null;
  const svStr=sv!=null?(sv>=0?`−${sv}`:`+${-sv}`):null; // reduction shown as −, increase as +
  $('eui-kpis').innerHTML=`
    <div class="eui-stat"><div class="eui-val eui-pre-val">${preM?Math.round(preM):'—'}</div><div class="eui-lbl"><span class="cap-simple">Before, typical home</span><span class="cap-advanced">Pre-retrofit median</span><br>kWh/m²</div></div>
    <div class="eui-arrow-big">→</div>
    <div class="eui-stat"><div class="eui-val eui-post-val">${postM?Math.round(postM):'—'}</div><div class="eui-lbl"><span class="cap-simple">After, typical home</span><span class="cap-advanced">Post-retrofit median</span><br>kWh/m²</div></div>
    ${svStr!=null?`<div style="margin-left:auto;text-align:right"><div class="eui-saving">${svStr}</div><div style="font-size:12px;color:var(--muted)">kWh/m² · <span class="cap-simple">typical home</span><span class="cap-advanced">median home</span></div></div>`:''}`;
  function euiBins(vals,step=BINS.eui){
    const b={};
    vals.forEach(v=>{if(v>500)return;const k=Math.floor(v/step)*step;b[k]=(b[k]||0)+1;});
    return b;
  }
  const preBins=euiBins(preEUIs),postBins=euiBins(postEUIs);
  const deltaBins={};
  FILTERED.forEach(r=>{
    const pre=num(r.Pre_TotalEnergy),post=num(r.Post_TotalEnergy),area=num(r.FloorArea);
    if(!pre||!post||!area||area<=0)return;
    const d=(pre-post)/area;
    if(d>0&&d<=500){const k=Math.floor(d/BINS.eui)*BINS.eui;deltaBins[k]=(deltaBins[k]||0)+1;}
  });
  drawComboChart('eui-chart','eui',preBins,postBins,deltaBins,'kWh/m²');
}

// ── (removed) EUI slopegraph "Every home, pre → post EUI" ──
// The per-home slopegraph was dropped — it read as a dense band rather than a
// clear comparison. The EUI distribution card above covers pre/post EUI.

// ── GHG emissions ─────────────────────────────────────────────────
// See GHG_SCENARIO / GHG_SCENARIO_FIELDS above: 4 bases, switched by the
// #ghg-scenario-sel dropdown (redrawGHG()). "reported" = raw ERSGHG (~50.5%
// coverage nationally); the other 3 are calculated, ~100% coverage.
function renderGHG(){
  const [preCol,postCol]=GHG_SCENARIO_FIELDS[GHG_SCENARIO];
  const ghgPre=FILTERED.map(r=>num(r[preCol])).filter(v=>v!==null);
  const ghgPost=FILTERED.map(r=>num(r[postCol])).filter(v=>v!==null);
  const preM=median(ghgPre),postM=median(ghgPost);
  const ghgDeltas=FILTERED.map(r=>{
    const g0=num(r[preCol]),g1=num(r[postCol]);
    return(g0!=null&&g1!=null)?(g0-g1):null;
  }).filter(v=>v!==null);
  const sv=median(ghgDeltas);
  $('s-ghg-saving').textContent=sv!=null?sv.toFixed(1):'—';
  const svStr=sv!=null?(sv>=0?`−${sv.toFixed(1)}`:`+${(-sv).toFixed(1)}`):null;
  $('ghg-kpis').innerHTML=`
    <div class="eui-stat"><div class="eui-val eui-pre-val">${preM!==null?preM.toFixed(1):'—'}</div><div class="eui-lbl"><span class="cap-simple">Before, typical home</span><span class="cap-advanced">Pre-retrofit median</span><br><span class="cap-simple">tonnes CO₂/yr</span><span class="cap-advanced">tCO2e/yr</span></div></div>
    <div class="eui-arrow-big">→</div>
    <div class="eui-stat"><div class="eui-val eui-post-val">${postM!==null?postM.toFixed(1):'—'}</div><div class="eui-lbl"><span class="cap-simple">After, typical home</span><span class="cap-advanced">Post-retrofit median</span><br><span class="cap-simple">tonnes CO₂/yr</span><span class="cap-advanced">tCO2e/yr</span></div></div>
    ${svStr!=null?`<div style="margin-left:auto;text-align:right"><div class="eui-saving">${svStr}</div><div style="font-size:12px;color:var(--muted)"><span class="cap-simple">tonnes CO₂/yr</span><span class="cap-advanced">tCO2e/yr</span> · <span class="cap-simple">typical home</span><span class="cap-advanced">median home</span></div></div>`:''}`;
  const covNote=$('ghg-coverage-note');
  if(covNote)covNote.textContent=GHG_SCENARIO==='reported'?`${ghgPre.length.toLocaleString()} of ${FILTERED.length.toLocaleString()} homes have this field`:'';
  function ghgBins(vals,step=BINS.ghg){
    const b={};
    vals.forEach(v=>{if(v>30)return;const k=Math.floor(v/step)*step;b[k]=(b[k]||0)+1;});
    return b;
  }
  const preBins=ghgBins(ghgPre),postBins=ghgBins(ghgPost);
  const deltaBins={};
  FILTERED.forEach(r=>{
    const pre=num(r[preCol]),post=num(r[postCol]);
    if(pre===null||post===null)return;
    const d=pre-post;
    if(d>0&&d<=30){const k=Math.floor(d/BINS.ghg)*BINS.ghg;deltaBins[k]=(deltaBins[k]||0)+1;}
  });
  drawComboChart('ghg-chart','ghg',preBins,postBins,deltaBins,'tCO2e/yr');
}
function redrawGHG(){
  if(MODE==='fsa')renderGHG();
  else if(MODE==='province'&&_lastProvinceSlice)renderProvinceGHG(_lastProvinceSlice);
}
$('ghg-scenario-sel').addEventListener('change',function(){GHG_SCENARIO=this.value;redrawGHG();});

// ── Energy bill $ (FSA mode — prices raw rows) ──────────────────────
// Shows/hides the whole card + headline stat based on COST_PV (null for
// provinces without rate data). Mirrors renderGHG(): pre/post distributions
// as lines, amber Improvement bars for homes whose bill fell.
function setCostCardVisible(show){
  $('cost-card').style.display=show?'':'none';
  $('s-cost-card').style.display=show?'':'none';
}
// Re-render just the $-card in the current mode, using already-cached data —
// called when the price vector arrives after the main render (first visit to a
// priced province). A no-op in modes/provinces where the card stays hidden.
function refreshCostCard(){
  if(MODE==='province'){if(_lastProvinceSlice)renderProvinceCost(_lastProvinceSlice);}
  else if(MODE==='fsa'){renderCost();}
}
function renderCost(){
  if(!COST_PV){setCostCardVisible(false);return;}
  setCostCardVisible(true);
  const pv=COST_PV;
  const pre=[],post=[],deltas=[];
  FILTERED.forEach(r=>{
    const cp=homeCost(r,'Pre',pv);
    if(!(cp>0))return;                 // no priced energy for this home — skip
    const cq=homeCost(r,'Post',pv);
    pre.push(cp);post.push(cq);deltas.push(cp-cq);
  });
  const preM=median(pre),postM=median(post),svM=median(deltas);
  $('s-cost-saving').textContent=svM!=null?fmtMoney(Math.round(svM)):'—';
  const svStr=svM!=null?(svM>=0?`−${fmtMoney(Math.round(svM))}`:`+${fmtMoney(Math.round(-svM))}`):null;
  $('cost-kpis').innerHTML=`
    <div class="eui-stat"><div class="eui-val eui-pre-val">${preM!=null?fmtMoney(Math.round(preM)):'—'}</div><div class="eui-lbl"><span class="cap-simple">Before, typical home</span><span class="cap-advanced">Pre-retrofit median</span><br>$/yr</div></div>
    <div class="eui-arrow-big">→</div>
    <div class="eui-stat"><div class="eui-val eui-post-val">${postM!=null?fmtMoney(Math.round(postM)):'—'}</div><div class="eui-lbl"><span class="cap-simple">After, typical home</span><span class="cap-advanced">Post-retrofit median</span><br>$/yr</div></div>
    ${svStr!=null?`<div style="margin-left:auto;text-align:right"><div class="eui-saving">${svStr}</div><div style="font-size:12px;color:var(--muted)">$/yr · <span class="cap-simple">typical home</span><span class="cap-advanced">median home</span></div></div>`:''}`;
  const costBins=vals=>{const b={};vals.forEach(v=>{if(v>COST_CAP)return;const k=Math.floor(v/BINS.cost)*BINS.cost;b[k]=(b[k]||0)+1;});return b;};
  const preBins=costBins(pre),postBins=costBins(post);
  const deltaBins={};
  deltas.forEach(d=>{if(d>0&&d<=COST_DELTA_CAP){const k=Math.floor(d/BINS.cost)*BINS.cost;deltaBins[k]=(deltaBins[k]||0)+1;}});
  drawComboChart('cost-chart','cost',preBins,postBins,deltaBins,'$/yr');
}

// ── Retrofit cost estimate (proof of concept) ───────────────────────
// Separate tree (retrofit_costs_json/), NOT part of fsa_json — see
// docs/RETROFIT_COSTS.md "retrofit_costs_json companion tree". Per-FSA files
// are the same {columns,rows} array-of-arrays shape fsa_json uses, joined to
// ALL/FILTERED by HOUSEID (String(r.HOUSEID) === row[0], both normalized the
// same way — see build_retrofit_costs_json.py's clean_id()).
const RETRO_COST_JSON_BASE=`${BASE_URL}retrofit_costs_json/`;
const RETRO_MEASURES=[
  {key:'Roof',abbr:'Roof',label:'Roof / attic insulation'},
  {key:'Wall',abbr:'Wall',label:'Wall insulation'},
  {key:'Foundation',abbr:'Fnd',label:'Foundation insulation'},
  {key:'Window',abbr:'Win',label:'Windows'},
  {key:'ASHP',abbr:'ASHP',label:'Air source heat pump'},
  {key:'AirSeal',abbr:'Seal',label:'Air sealing'},
  {key:'PV',abbr:'PV',label:'Solar PV'},
  {key:'HRV',abbr:'HRV',label:'HRV / ERV'},
];
const RETRO_COLS=['id'];
RETRO_MEASURES.forEach(m=>RETRO_COLS.push(`${m.abbr}_l`,`${m.abbr}_m`,`${m.abbr}_h`));
RETRO_COLS.push('Tot_l','Tot_m','Tot_h','ac','acs','bh','bhs','bsd','wc','wcs','sav','pbY','pbFuel');
const RETRO_COL_IDX={};RETRO_COLS.forEach((c,i)=>RETRO_COL_IDX[c]=i);

let RETRO_BAND=1; // 0=low(p10), 1=mid(p50), 2=high(p90)
let RETRO_COST_MAP=new Map();     // FSA mode: HOUSEID string -> row array
let RETRO_PROVINCE_SUMMARY=null;  // province/national mode: _summary.json / _canada.json payload
let RETRO_DICT=null,RETRO_DICT_PROMISE=null;
function loadRetroDict(){
  if(!RETRO_DICT_PROMISE)RETRO_DICT_PROMISE=fetchJSON(`${RETRO_COST_JSON_BASE}_dictionary.json`).then(d=>{RETRO_DICT=d;return d;}).catch(()=>null);
  return RETRO_DICT_PROMISE;
}
const RETRO_FSA_CACHE=new Map();
function fetchRetroFsa(prov,fsa){
  const key=`${prov}|${fsa}`;
  if(RETRO_FSA_CACHE.has(key))return Promise.resolve(RETRO_FSA_CACHE.get(key));
  return fetchJSON(`${RETRO_COST_JSON_BASE}${prov}/${fsa}.json`)
    .then(payload=>{RETRO_FSA_CACHE.set(key,payload);return payload;})
    .catch(()=>{const empty={columns:RETRO_COLS,rows:[]};RETRO_FSA_CACHE.set(key,empty);return empty;});
}
const RETRO_SUMMARY_CACHE=new Map();
function fetchRetroSummary(prov){
  if(RETRO_SUMMARY_CACHE.has(prov))return Promise.resolve(RETRO_SUMMARY_CACHE.get(prov));
  return fetchJSON(`${RETRO_COST_JSON_BASE}${prov}/_summary.json`)
    .then(d=>{RETRO_SUMMARY_CACHE.set(prov,d);return d;})
    .catch(()=>{RETRO_SUMMARY_CACHE.set(prov,null);return null;});
}
let RETRO_CANADA_SUMMARY=null,RETRO_CANADA_PROMISE=null;
function fetchRetroCanada(){
  if(!RETRO_CANADA_PROMISE)RETRO_CANADA_PROMISE=fetchJSON(`${RETRO_COST_JSON_BASE}_canada.json`).then(d=>{RETRO_CANADA_SUMMARY=d;return d;}).catch(()=>null);
  return RETRO_CANADA_PROMISE;
}
function retroRowFor(houseId){return RETRO_COST_MAP.get(String(houseId));}
function retroVal(row,col){return row?row[RETRO_COL_IDX[col]]:null;}

function setRetroBand(b){
  RETRO_BAND=b;
  document.querySelectorAll('#retro-band-seg .sort-btn').forEach(btn=>btn.classList.toggle('active',+btn.dataset.band===b));
  renderRetrofitCost();
  if(MODE==='fsa'&&isAdvancedMode())renderTable(); // table's cost/payback column follows the band too
}
function setRetroCostCardVisible(show){
  const el=$('retro-cost-card');if(el)el.style.display=show?'':'none';
}
function toggleRetroTableCols(show){
  const a=$('th-retro-cost'),b=$('th-retro-payback');
  if(a)a.style.display=show?'':'none';
  if(b)b.style.display=show?'':'none';
}

function retroMeasureTable(rows){ // rows: [{label,n,sum}]
  const body=rows.filter(r=>r.n).map(r=>
    `<tr><td style="padding:4px 8px;border-top:1px solid var(--border)">${r.label}</td>`+
    `<td style="text-align:right;padding:4px 8px;border-top:1px solid var(--border)">${r.n.toLocaleString()}</td>`+
    `<td style="text-align:right;padding:4px 8px;border-top:1px solid var(--border)">${r.sum!=null?fmtMoney(Math.round(r.sum)):'—'}</td></tr>`
  ).join('');
  return `<div style="overflow-x:auto"><table style="width:100%;font-size:13px;border-collapse:collapse;margin-top:.6rem">
    <thead><tr>
      <th style="text-align:left;padding:4px 8px;color:var(--muted);font-weight:500">Measure</th>
      <th style="text-align:right;padding:4px 8px;color:var(--muted);font-weight:500">Homes priced</th>
      <th style="text-align:right;padding:4px 8px;color:var(--muted);font-weight:500">Total est. cost</th>
    </tr></thead><tbody>${body}</tbody></table></div>`;
}

function renderRetrofitCost(){
  const bandKey=['l','m','h'][RETRO_BAND],bandName=['low','mid','high'][RETRO_BAND];
  if(MODE==='fsa'){
    if(!RETRO_COST_MAP.size){setRetroCostCardVisible(false);toggleRetroTableCols(false);return;}
    const totals=[],paybacks=[];
    let sumTot=0,nPriced=0;
    const mSum={};RETRO_MEASURES.forEach(m=>mSum[m.key]={n:0,sum:0});
    FILTERED.forEach(r=>{
      const row=retroRowFor(r.HOUSEID);
      if(!row)return;
      const tot=retroVal(row,`Tot_${bandKey}`);
      if(tot!=null){totals.push(tot);sumTot+=tot;nPriced++;}
      const pb=retroVal(row,'pbY');
      if(pb!=null&&pb>0&&pb<100)paybacks.push(pb);
      RETRO_MEASURES.forEach(m=>{
        const v=retroVal(row,`${m.abbr}_${bandKey}`);
        if(v!=null){mSum[m.key].n++;mSum[m.key].sum+=v;}
      });
    });
    if(!nPriced){setRetroCostCardVisible(false);toggleRetroTableCols(false);return;}
    setRetroCostCardVisible(true);toggleRetroTableCols(true);
    const medTot=median(totals),medPb=median(paybacks);
    $('retro-cost-kpis').innerHTML=`
      <div class="eui-stat"><div class="eui-val">${fmtMoney(Math.round(sumTot))}</div><div class="eui-lbl">Total est. cost<br>this view, priced homes</div></div>
      <div class="eui-stat"><div class="eui-val">${medTot!=null?fmtMoney(Math.round(medTot)):'—'}</div><div class="eui-lbl"><span class="cap-simple">Typical home</span><span class="cap-advanced">Median per home</span></div></div>
      <div class="eui-stat"><div class="eui-val">${medPb!=null?medPb.toFixed(1)+'y':'—'}</div><div class="eui-lbl"><span class="cap-simple">Typical payback</span><span class="cap-advanced">Median payback</span></div></div>
      <div style="margin-left:auto;text-align:right;align-self:center"><div style="color:var(--muted);font-size:13px">${nPriced.toLocaleString()} of ${FILTERED.length.toLocaleString()} homes priced (${bandName} band)</div></div>`;
    $('retro-cost-measures').innerHTML=retroMeasureTable(RETRO_MEASURES.map(m=>({label:m.label,n:mSum[m.key].n,sum:mSum[m.key].sum})));
  }else if(MODE==='province'){
    const s=RETRO_PROVINCE_SUMMARY;
    if(!s||!s.n_priced){setRetroCostCardVisible(false);return;}
    setRetroCostCardVisible(true);
    const tot=s.total&&s.total[bandName];
    $('retro-cost-kpis').innerHTML=`
      <div class="eui-stat"><div class="eui-val">${tot&&tot.sum!=null?fmtMoney(Math.round(tot.sum)):'—'}</div><div class="eui-lbl">Total est. cost<br>this view, priced homes</div></div>
      <div class="eui-stat"><div class="eui-val">${tot&&tot.median!=null?fmtMoney(Math.round(tot.median)):'—'}</div><div class="eui-lbl"><span class="cap-simple">Typical home</span><span class="cap-advanced">Median per home</span></div></div>
      <div class="eui-stat"><div class="eui-val">${s.payback_years_median!=null?s.payback_years_median.toFixed(1)+'y':'—'}</div><div class="eui-lbl"><span class="cap-simple">Typical payback</span><span class="cap-advanced">Median payback</span></div></div>
      <div style="margin-left:auto;text-align:right;align-self:center"><div style="color:var(--muted);font-size:13px">${s.n_priced.toLocaleString()} homes priced (${bandName} band) · not filtered by house type</div></div>`;
    $('retro-cost-measures').innerHTML=retroMeasureTable(RETRO_MEASURES.map(m=>{
      const md=s.measures&&s.measures[m.key];
      return {label:m.label,n:md?md.n:0,sum:md&&md[bandName]?md[bandName].sum:null};
    }));
  }
}

// ── Design heat loss (kW — see ers_web_pipeline.py: EGHDESHTLOSS W→kW) ──
function renderHeatLoss(){
  const pre=FILTERED.map(r=>num(r.Pre_HeatLoss)).filter(v=>v!==null&&v>0&&v<=150);
  const post=FILTERED.map(r=>num(r.Post_HeatLoss)).filter(v=>v!==null&&v>0&&v<=150);
  function bins(vals,step=BINS.heatloss){
    const b={};
    vals.forEach(v=>{const k=Math.floor(v/step)*step;b[k]=(b[k]||0)+1;});
    return b;
  }
  const preBins=bins(pre),postBins=bins(post);
  const deltaBins={};
  FILTERED.forEach(r=>{
    const pre=num(r.Pre_HeatLoss),post=num(r.Post_HeatLoss);
    if(pre===null||post===null||pre<=0||post<=0)return;
    const d=pre-post;
    if(d>0&&d<=150){const k=Math.floor(d/BINS.heatloss)*BINS.heatloss;deltaBins[k]=(deltaBins[k]||0)+1;}
  });
  drawComboChart('heatloss-chart','heatloss',preBins,postBins,deltaBins,'kW');
}

// ── Annual heat loss by envelope component (kWh/yr) ────────────────
// The aggregate twin of the per-home heat-loss chart in the expanded row
// detail, and deliberately drawn the same way (one shared track per row,
// split pre on top / post below) so the two read identically.
//
// MEANS, not medians, for the same reason the waterfall uses means: the six
// components have to sum to the whole-home total for the "share of total"
// column to mean anything, and mean*n == sum exactly. Medians would not add
// up and would flatten Exposed floor — zero for most homes — to nothing.
//
// Note this is ANNUAL energy (EGHHL*, kWh/yr), not the design-day peak power
// (EGHDESHTLOSS, kW) shown by renderHeatLoss(). Same words, different units.
const HL_COMPONENT_FIELDS=[
  {key:'HeatLossWindowDoor',label:'Windows & doors'},
  {key:'HeatLossWall',label:'Walls'},
  {key:'HeatLossFoundation',label:'Foundation'},
  {key:'HeatLossRoof',label:'Roof'},
  {key:'HeatLossFloor',label:'Exposed floor'},
  {key:'HeatLossAir',label:'Air leakage'},
];

function drawHeatLossComponents(items,n){
  const panel=$('hlcomp-panel');
  if(!panel)return;
  const usable=items.filter(it=>it.pre>0||it.post>0);
  if(!usable.length||!n){
    panel.innerHTML='<div class="state-msg" style="padding:1rem"><strong>No data</strong><span>No modelled heat-loss breakdown for this selection.</span></div>';
    return;
  }
  const preTotal=usable.reduce((s,i)=>s+i.pre,0);
  const postTotal=usable.reduce((s,i)=>s+i.post,0);
  const max=Math.max(...usable.map(i=>Math.max(i.pre,i.post)),1);
  // Biggest loss first — the question the chart answers is "where does it go?",
  // so ranking by size beats keeping a fixed component order.
  const rows=[...usable].sort((a,b)=>b.pre-a.pre);

  const W=760,labelW=132,barW=330,rowH=34,barH=15,padR=140;
  const svgH=rows.length*rowH+14;
  let svg=`<svg viewBox="0 0 ${W} ${svgH}" style="width:100%;max-width:${W}px;display:block" role="img" aria-label="Mean annual heat loss per home by envelope component, before and after retrofit">`;
  rows.forEach((it,i)=>{
    const y=i*rowH+8;
    const preW=it.pre>0?Math.max(2,it.pre/max*barW):0;
    const postW=it.post>0?Math.max(2,it.post/max*barW):0;
    const share=preTotal?Math.round(it.pre/preTotal*100):0;
    const cut=it.pre>0?(it.pre-it.post)/it.pre*100:0;
    svg+=`<text x="${labelW-8}" y="${y+barH/2+4}" text-anchor="end" font-size="12" fill="${PAL.axis}" font-family="Inter,sans-serif">${it.label}</text>`;
    svg+=`<rect x="${labelW}" y="${y}" width="${barW}" height="${barH}" fill="${PAL.track}" rx="3"/>`;
    svg+=`<rect x="${labelW}" y="${y}" width="${preW}" height="${barH/2}" fill="${al(PAL.primary,'99')}" rx="2"><title>${it.label} before: ${Math.round(it.pre).toLocaleString()} kWh/yr</title></rect>`;
    svg+=`<rect x="${labelW}" y="${y+barH/2}" width="${postW}" height="${barH/2}" fill="${al(PAL.pos,'99')}" rx="2"><title>${it.label} after: ${Math.round(it.post).toLocaleString()} kWh/yr</title></rect>`;
    svg+=`<text x="${labelW+barW+10}" y="${y+barH/2+4}" font-size="11" fill="${PAL.axis}" font-family="Inter,sans-serif" font-variant-numeric="tabular-nums">${Math.round(it.pre).toLocaleString()} → <tspan fill="${it.post<it.pre?PAL.pos:PAL.neg}">${Math.round(it.post).toLocaleString()}</tspan></text>`;
    svg+=`<text x="${W-8}" y="${y+barH/2+4}" text-anchor="end" font-size="11" fill="${PAL.tick}" font-family="Inter,sans-serif" font-variant-numeric="tabular-nums">${share}% of loss · ${cut>0.5?'−'+Math.round(cut)+'%':'—'}</text>`;
  });
  svg+=`</svg>`;

  const totalCut=preTotal?Math.round((preTotal-postTotal)/preTotal*100):0;
  panel.innerHTML=`${svg}
    <div style="display:flex;flex-wrap:wrap;gap:14px;align-items:center;margin-top:10px;font-size:11px;color:var(--muted)">
      <span style="display:inline-flex;align-items:center;gap:5px"><span style="display:inline-block;width:18px;height:5px;background:${al(PAL.primary,'99')};border-radius:2px"></span>Before</span>
      <span style="display:inline-flex;align-items:center;gap:5px"><span style="display:inline-block;width:18px;height:5px;background:${al(PAL.pos,'99')};border-radius:2px"></span>After</span>
      <span style="margin-left:auto;color:var(--text)">Whole home: <strong>${Math.round(preTotal).toLocaleString()}</strong> → <strong style="color:var(--green)">${Math.round(postTotal).toLocaleString()}</strong> kWh/yr (−${totalCut}%), mean of ${n.toLocaleString()} homes</span>
    </div>`;
}

function renderHeatLossComponents(){
  const n=FILTERED.length;
  const items=HL_COMPONENT_FIELDS.map(c=>{
    let pre=0,post=0;
    FILTERED.forEach(r=>{pre+=num(r['Pre_'+c.key])||0;post+=num(r['Post_'+c.key])||0;});
    return{label:c.label,pre:n?pre/n:0,post:n?post/n:0};
  });
  drawHeatLossComponents(items,n);
}

function renderProvinceHeatLossComponents(slice){
  drawHeatLossComponents(slice.heatloss_components||[],slice.row_count||0);
}

// ── Solar PV ──────────────────────────────────────────────────────
function renderSolar(n){
  const preAdopt=FILTERED.filter(r=>num(r.Pre_SolarPV)>0);
  const postAdopt=FILTERED.filter(r=>num(r.Post_SolarPV)>0);
  const prePct=n?Math.round(preAdopt.length/n*100):0;
  const postPct=n?Math.round(postAdopt.length/n*100):0;
  const sizes=postAdopt.map(r=>num(r.Post_SolarPV)).filter(v=>v!==null&&v>0);
  const medSize=median(sizes);
  $('solar-kpis').innerHTML=`
    <div class="eui-stat"><div class="eui-val eui-pre-val">${prePct}%</div><div class="eui-lbl">Pre-retrofit<br>with solar PV</div></div>
    <div class="eui-arrow-big">→</div>
    <div class="eui-stat"><div class="eui-val eui-post-val">${postPct}%</div><div class="eui-lbl">Post-retrofit<br>with solar PV</div></div>
    ${medSize?`<div style="margin-left:auto;text-align:right"><div class="eui-saving" style="color:var(--amber)">${medSize.toFixed(1)}</div><div style="font-size:12px;color:var(--muted)">median kW among adopters</div></div>`:''}`;
}

// ── Heat pump AHRI numbers + window codes ──────────────────────────
function barListHTML(items){
  if(!items||!items.length)return '<div class="state-msg" style="padding:1rem"><strong>No data</strong></div>';
  const max=Math.max(...items.map(i=>i.count))||1;
  return items.map(i=>{
    const main=i.main!=null?i.main:i.code;
    const sub=i.sub?`<span class="ml-sub">${i.sub}</span>`:'';
    const badges=(i.badges&&i.badges.length)?`<span class="ml-badges">${i.badges.map(b=>`<span class="badge ${b.cls}">${b.label}</span>`).join('')}</span>`:'';
    return `<div class="measure-row"><div class="measure-label"><span class="ml-code">${main}</span>${sub}${badges}</div><div class="bar-track"><div class="bar-fill" style="width:${Math.round(i.count/max*100)}%;background:#C8881A"></div></div><div class="bar-pct">${Math.round(i.count).toLocaleString()}</div></div>`;
  }).join('');
}
// Outdoor-model groups (see groupAhriByModel): a header bar per outdoor unit
// (name + total installs), with every certificate behind it listed
// underneath — link, spec line, status/cold-climate badges, install count.
function ahriModelGroupsHTML(groups,capCerts=8){
  if(!groups||!groups.length)return '<div class="state-msg" style="padding:1rem"><strong>No data</strong></div>';
  const max=Math.max(...groups.map(g=>g.total))||1;
  return groups.map(g=>{
    const shown=g.certs.slice(0,capCerts);
    const rest=g.certs.length-shown.length;
    const restCount=g.certs.slice(capCerts).reduce((a,c)=>a+c.count,0);
    const certRows=shown.map(c=>{
      const badges=(c.badges&&c.badges.length)?`<span class="ml-badges">${c.badges.map(b=>`<span class="badge ${b.cls}">${b.label}</span>`).join('')}</span>`:'';
      return `<div class="ahri-cert-row"><span class="ml-sub">${c.sub}</span>${badges}<span class="ahri-cert-count">${Math.round(c.count).toLocaleString()}</span></div>`;
    }).join('');
    const more=rest>0?`<div class="ahri-cert-more">+${rest} more certificate${rest>1?'s':''} (${Math.round(restCount).toLocaleString()} installs)</div>`:'';
    return `<div class="ahri-model-group">`+
      `<div class="measure-row"><div class="measure-label"><span class="ml-code">${g.name}</span></div>`+
      `<div class="bar-track"><div class="bar-fill" style="width:${Math.round(g.total/max*100)}%;background:#C8881A"></div></div>`+
      `<div class="bar-pct">${Math.round(g.total).toLocaleString()}</div></div>`+
      `<div class="ahri-cert-list">${certRows}${more}</div></div>`;
  }).join('');
}

// Mirrors the AHRI/window top-N logic in precompute_province_stats.py /
// split_fsa_json.py, but client-side over whatever rows are currently
// FILTERED — used only in FSA mode, where raw per-home AHRI/WindowCode
// values are available (province mode uses the precomputed ahri_counts/
// window_pre_top/window_post_top fields instead, see renderAhriWindowProvince).
// n=Infinity for AHRI (full counts needed so grouping by outdoor model
// captures a model's true total, not just whichever individual certificates
// happened to already be in a pre-truncated top-N — see groupAhriByModel).
function topCounts(rows,cols,n,minDigits){
  const counts={};
  rows.forEach(r=>cols.forEach(c=>{
    const v=r[c];
    if(v===null||v===undefined||v==='')return;
    const s=String(v).trim();
    if(minDigits&&(s.match(/\d/g)||[]).length<minDigits)return;
    counts[s]=(counts[s]||0)+1;
  }));
  return Object.entries(counts).map(([code,count])=>({code,count})).sort((a,b)=>b.count-a.count).slice(0,n);
}
function renderAhriWindowFsa(){
  const dec=(cols,n,minDigits,decoder)=>topCounts(FILTERED,cols,n,minDigits)
    .map(i=>{const d=decoder(i.code);return{...d,count:i.count};});
  // Full AHRI counts (no top-N truncation) so grouping by outdoor model
  // below reflects each model's true total, then take the top 5 models.
  const ahriAll=topCounts(FILTERED,['Pre_HPAHRI','Post_HPAHRI'],Infinity,4);
  $('ahri-list').innerHTML=ahriModelGroupsHTML(groupAhriByModel(ahriAll).slice(0,5));
  $('window-pre-list').innerHTML=barListHTML(dec(['Pre_WindowCode'],5,0,decodeWindow));
  $('window-post-list').innerHTML=barListHTML(dec(['Post_WindowCode'],5,0,decodeWindow));
}
function renderAhriWindowProvince(slice){
  const toItems=(list,decoder)=>(list||[]).slice(0,5).map(x=>{const d=decoder(x.code);return{...d,count:Math.round(x.count)};});
  // ahri_counts carries every code seen in this province (not just a top-N
  // slice), same reasoning as renderAhriWindowFsa above.
  const ahriAll=Object.entries(slice.ahri_counts||{}).map(([code,count])=>({code,count}));
  $('ahri-list').innerHTML=ahriModelGroupsHTML(groupAhriByModel(ahriAll).slice(0,5));
  $('window-pre-list').innerHTML=barListHTML(toItems(slice.window_pre_top,decodeWindow));
  $('window-post-list').innerHTML=barListHTML(toItems(slice.window_post_top,decodeWindow));
}

// ── Heat pump + backup pairing, and sizing vs. design heat loss ──────
// Post_HeatFuel/Post_HeatType is NOT the heat pump — HOT2000 models it as a
// separate component, so for a heat-pump home this column is the companion/
// backup system (see join_hp_capacity.py / docs/RETROFITS.md). Sizing uses
// AHRI-certificate-verified capacity (Post_HPCapacity47/5), not the raw
// auditor-entered HPCAP field, which was validated against real certificates
// and runs a median 1.55x high.
function hasHeatPump(r){
  const t=r.Post_HPType;
  return !!(t&&String(t).trim()&&!String(t).toLowerCase().startsWith('n/a'));
}
// Natural Gas/Oil/Propane only -- Electricity can't be split from the heat
// pump's own electricity use, and the wood species (Mixed Wood/Hardwood/
// Wood Pellets/Softwood) all share one Post_HeatWood column, so a
// per-species check isn't meaningful (see precompute_province_stats.py).
const HP_BACKUP_USED_COLS={'Natural Gas':'Post_HeatNaturalGas','Oil':'Post_HeatOil',
  'Propane':'Post_HeatPropane'};
function renderHPBackupDonut(counts){
  const total=Object.values(counts||{}).reduce((a,b)=>a+b,0);
  donut('hp-backup-donut',counts||{},'hpBackupDonut',total);
}
// Electricity (the heat pump's own heating draw, Post_HeatElectricity) vs.
// backup-fuel energy, mean kWh/yr per home — restricted to combustion-backup
// homes, so Post_HeatElectricity unambiguously means the heat pump's own
// draw (no electric backup coexists in that case; see the note on
// HP_BACKUP_USED_COLS/backup_energy_means for why electric backup itself
// can't be split out this way).
function renderHPBackupEnergyChart(energyMeans){
  dc('hpBackupEnergy');
  const fuels=Object.keys(HP_BACKUP_USED_COLS).filter(f=>energyMeans&&energyMeans[f]&&energyMeans[f].n>0);
  if(!fuels.length)return;
  const elecVals=fuels.map(f=>Math.round(energyMeans[f].elec_mean));
  const fuelVals=fuels.map(f=>Math.round(energyMeans[f].fuel_mean));
  charts['hpBackupEnergy']=new Chart($('hp-backup-energy-chart').getContext('2d'),{
    type:'bar',
    data:{labels:fuels,datasets:[
      {label:'Electricity (heat pump)',data:elecVals,backgroundColor:al(PAL.blue,'CC'),borderWidth:0,borderRadius:2},
      {label:'Backup fuel',data:fuelVals,backgroundColor:al(PAL.secondary,'CC'),borderWidth:0,borderRadius:2},
    ]},
    options:{responsive:true,maintainAspectRatio:false,
      plugins:{legend:{position:'top',labels:{font:{size:11},boxWidth:12}},
        tooltip:{callbacks:{label:i=>`${i.dataset.label}: ${i.raw.toLocaleString()} kWh/yr`}}},
      scales:{x:{ticks:{font:{size:11},color:PAL.tick},grid:{display:false}},
              y:{ticks:{font:{size:10},color:PAL.tick},grid:{color:PAL.track},title:{display:true,text:'kWh/yr (mean)',font:{size:10},color:PAL.axis}}}}
  });
}
function renderHPBackupFsa(){
  const hp=FILTERED.filter(hasHeatPump);
  const counts={};
  hp.forEach(r=>{const f=r.Post_HeatFuel;if(f&&String(f).trim())counts[f]=(counts[f]||0)+1;});
  renderHPBackupDonut(counts);
  const energy={};
  Object.entries(HP_BACKUP_USED_COLS).forEach(([fuel,col])=>{
    const pairs=hp.filter(r=>r.Post_HeatFuel===fuel)
      .map(r=>({fuel:num(r[col]),elec:num(r.Post_HeatElectricity)}))
      .filter(p=>p.fuel!=null&&p.elec!=null);
    if(pairs.length)energy[fuel]={
      fuel_mean:pairs.reduce((s,p)=>s+p.fuel,0)/pairs.length,
      elec_mean:pairs.reduce((s,p)=>s+p.elec,0)/pairs.length,
      n:pairs.length,
    };
  });
  renderHPBackupEnergyChart(energy);
}
function renderHPBackupProvince(slice){
  renderHPBackupDonut(slice.backup_fuel_counts);
  renderHPBackupEnergyChart(slice.backup_energy_means);
}
// Bin key rounded to 2dp to match precompute_province_stats.py's
// bin_counts() rounding for fractional steps (the bin-width contract) —
// otherwise floating-point drift (0.30000000000000004) splits one real bin
// into two between FSA and province views.
function hpSizingBins(rows,capCol){
  const b={};
  rows.forEach(r=>{
    const cap=num(r[capCol]),hl=num(r.Post_HeatLoss);
    if(cap===null||hl===null||hl<=0)return;
    const ratio=cap/hl;
    if(ratio>3)return;
    const k=Math.round(Math.floor(ratio/BINS.hpSizing)*BINS.hpSizing*100)/100;
    b[k]=(b[k]||0)+1;
  });
  return b;
}
// Selected outdoor temperature for the sizing chart -- '47' (8.3°C) or '5'
// (−15°C), set by #hpsizing-temp-sel. One line at a time (not both
// overlaid): at FSA scale two overlapping ratio histograms were hard to
// read as anything but "which is bigger", and the plain °C label (no
// "mild day"/"design day" framing) is the temperature, not a claim about
// what day that temperature represents.
let HP_SIZING_TEMP='47';
const HP_SIZING_LABEL={'47':'8.3°C','5':'−15°C'};
function renderHPSizing(){
  const hp=FILTERED.filter(hasHeatPump);
  const capCol=HP_SIZING_TEMP==='5'?'Post_HPCapacity5':'Post_HPCapacity47';
  drawComboChart('hpsizing-chart','hpsizing',
    hpSizingBins(hp,capCol),null,{},
    'sizing ratio',HP_SIZING_LABEL[HP_SIZING_TEMP]);
}
function renderProvinceHPSizing(slice){
  const bins=HP_SIZING_TEMP==='5'?(slice.hp_sizing5_bins||{}):(slice.hp_sizing47_bins||{});
  drawComboChart('hpsizing-chart','hpsizing',
    bins,null,{},
    'sizing ratio',HP_SIZING_LABEL[HP_SIZING_TEMP]);
}
function redrawHPSizing(){
  if(!isAdvancedMode())return;
  if(MODE==='fsa')renderHPSizing();
  else if(MODE==='province'&&_lastProvinceSlice)renderProvinceHPSizing(_lastProvinceSlice);
}
$('hpsizing-temp-sel').addEventListener('change',function(){HP_SIZING_TEMP=this.value;redrawHPSizing();});

// ── Most common window changes (FSA mode only — needs paired per-home
// Pre/Post window codes; province mode only ships independent pre/post
// frequency counts, not paired, so this comparison isn't possible there) ──
function toggleWindowChangesCard(show){
  $('window-changes-card').style.display=show?'':'none';
}
function renderWindowChanges(){
  if(!WINDOW_COMPONENTS){$('window-changes-list').innerHTML='<div class="state-msg" style="padding:1rem"><strong>Loading…</strong></div>';return;}
  const changeCounts={},transitionCounts={};
  let nDecoded=0;
  FILTERED.forEach(r=>{
    const pre=decodeWindowParts(r.Pre_WindowCode),post=decodeWindowParts(r.Post_WindowCode);
    if(!pre||!post)return;
    nDecoded++;
    WINDOW_ATTRS.forEach(({key})=>{
      if(pre[key]===post[key])return;
      changeCounts[key]=(changeCounts[key]||0)+1;
      const tKey=key+'|||'+pre[key]+'|||'+post[key];
      transitionCounts[tKey]=(transitionCounts[tKey]||0)+1;
    });
  });

  if(!nDecoded){
    $('window-changes-list').innerHTML='<div class="state-msg" style="padding:1rem"><strong>No decodable window codes for this selection</strong></div>';
    return;
  }

  const items=WINDOW_ATTRS.map(({key,label})=>{
    const changed=changeCounts[key]||0;
    let topTransition=null,topCount=0;
    Object.entries(transitionCounts).forEach(([tKey,c])=>{
      if(!tKey.startsWith(key+'|||'))return;
      if(c>topCount){topCount=c;topTransition=tKey;}
    });
    const sub=topTransition?(()=>{const[,from,to]=topTransition.split('|||');return`Most often: ${from} → ${to}`;})():null;
    return{main:label,sub,count:Math.round(changed/nDecoded*100)};
  }).sort((a,b)=>b.count-a.count).slice(0,5);

  $('window-changes-list').innerHTML=items.map(i=>{
    const sub=i.sub?`<span class="ml-sub">${i.sub}</span>`:'';
    return`<div class="measure-row"><div class="measure-label"><span class="ml-code">${i.main}</span>${sub}</div><div class="bar-track"><div class="bar-fill" style="width:${i.count}%;background:#C8881A"></div></div><div class="bar-pct">${i.count}%</div></div>`;
  }).join('');
}

// ── Neighbourhood housing stock (2021 Census, FSA-level) ────────────
const DWELLING_TYPE_LABELS={single_detached:'Single-detached',semi_detached:'Semi-detached',row_house:'Row house',duplex_apt:'Duplex apt',apt_low_rise:'Apt (<5 storeys)',apt_high_rise:'Apt (5+ storeys)',other_single_attached:'Other attached',movable:'Movable'};

function toggleCensusCard(show){
  $('census-card').style.display=show?'':'none';
}

const CENSUS_NOTE_FSA='Statistics Canada 2021 Census Profile, FSA level — describes <strong>all</strong> private dwellings in this FSA, not just the homes that got an EnerGuide audit. The gauge compares the two; see also the Building type and Year built charts above, which overlay this same census data for direct comparison. Tenure and dwelling condition are census counts for the whole FSA, so they describe the neighbourhood, not the audited homes. Owner stats (mortgage/shelter-cost/core-housing-need/dwelling-value) are 25%-sample-data estimates and may be suppressed (—) for small FSAs.';
const CENSUS_NOTE_REGION=scope=>`Statistics Canada 2021 Census Profile, aggregated from FSA level to ${scope} — describes <strong>all</strong> private dwellings, not just the homes that got an EnerGuide audit. Counts (dwellings, tenure, condition, building type, period of construction) are exact sums: FSAs tile the country, so they add up to the published totals. Rates and averages are weighted means over the FSAs that reported them. <strong>Medians cannot be aggregated</strong> from FSA medians, so dwelling value is shown here as an owner-household-weighted <em>average</em>, which is not comparable to the median shown in the single-FSA view.`;

// FSA view and province/Canada view share one painter; they differ only in
// which census block they hand it and what the scope is called. The rollup
// block (census_json/region_census.json, built by Python/rollup_census.py)
// carries the same field names as an FSA block, except every median is null
// — a median of FSA medians is not a median — so paintCensus() shows the
// corresponding *average* instead when isRollup is set.
function renderCensus(fsa,auditedCount){
  censusLoading();
  fetchCensusData().then(data=>{
    paintCensus(data[fsa],auditedCount,{scope:'this FSA',noun:'FSA'});
  }).catch(censusFailed);
}
function renderCensusRegion(provCode,auditedCount){
  censusLoading();
  fetchRegionCensus().then(data=>{
    const label=provCode==='CA'?'Canada':(PROVINCES[provCode]||{}).name||provCode;
    paintCensus(data[provCode],auditedCount,{scope:label,noun:'region',isRollup:true});
  }).catch(censusFailed);
}
function censusLoading(){
  toggleCensusCard(true);
  $('census-coverage-kpis').innerHTML='<div class="kpi-item"><div class="kpi-name">Loading…</div></div>';
}
function censusFailed(err){
  console.error(err);
  $('census-coverage-kpis').innerHTML='<div class="kpi-item"><div class="kpi-name">Could not load census data</div></div>';
}
function paintCensus(c,auditedCount,opts){
    if(!c){
      $('census-coverage-kpis').innerHTML=`<div class="kpi-item"><div class="kpi-name">No census data for this ${opts.noun}</div></div>`;
      $('census-owner-kpis').innerHTML='';
      return;
    }
    const coverage=c.total_dwellings?Math.round(auditedCount/c.total_dwellings*100):null;
    // Coverage can legitimately exceed 100%: this is ~20 years of cumulative
    // audits measured against a single 2021 dwelling snapshot, and a home can
    // be audited more than once. The bar clamps to 100 (it cannot show more)
    // while the printed number stays truthful, and the unit line says why
    // rather than letting ">100%" read as a bug.
    const covTile=coverage==null
      ?`<div class="kpi-item kpi-coverage"><div class="kpi-name">Audit coverage</div><div class="kpi-values"><div class="kpi-pct">—</div></div><div class="kpi-unit">no dwelling count</div></div>`
      :`<div class="kpi-item kpi-coverage">
          <div class="kpi-name">Audit coverage</div>
          <div class="kpi-values"><div class="kpi-pct">${coverage}%</div></div>
          <div class="kpi-bar"><span style="width:${Math.min(coverage,100)}%;background:${coverage>=100?PAL.pos:PAL.primary}"></span></div>
          <div class="kpi-unit">${coverage>100?'over 100%: ~20 yrs of audits vs a 2021 count':'of all private dwellings'}</div>
        </div>`;

    const ten=c.tenure||{};
    const tenTotal=(ten.owner||0)+(ten.renter||0);
    const ownerPct=tenTotal?Math.round(ten.owner/tenTotal*100):null;
    const cond=c.condition||{};
    const condTotal=(cond.minor_repairs||0)+(cond.major_repairs||0);
    const majorPct=condTotal?Math.round(cond.major_repairs/condTotal*100):null;

    $('census-coverage-kpis').innerHTML=`
      ${covTile}
      <div class="kpi-item"><div class="kpi-name">Total private dwellings</div><div class="kpi-values"><div class="kpi-pct">${c.total_dwellings!=null?c.total_dwellings.toLocaleString():'—'}</div></div><div class="kpi-unit">2021 Census</div></div>
      <div class="kpi-item"><div class="kpi-name">Audited homes (${opts.scope})</div><div class="kpi-values"><div class="kpi-pct">${auditedCount.toLocaleString()}</div></div><div class="kpi-unit">EnerGuide</div></div>
      <div class="kpi-item"><div class="kpi-name">Owner-occupied</div><div class="kpi-values"><div class="kpi-pct">${ownerPct!=null?ownerPct+'%':'—'}</div></div><div class="kpi-unit">${ownerPct!=null?`${(100-ownerPct)}% rented`:'tenure'}</div></div>
      <div class="kpi-item"><div class="kpi-name">Need major repairs<button type="button" class="info-btn" aria-label="What counts as needing major repairs?" data-info="StatCan's 2021 Census 'dwelling condition' question — self-reported by the household, not an inspection. Major repairs means defective plumbing or electrical wiring, or structural repairs to walls, floors or ceilings; routine upkeep and minor repairs don't count.">?</button></div><div class="kpi-values"><div class="kpi-pct">${majorPct!=null?majorPct+'%':'—'}</div></div><div class="kpi-unit">dwelling condition</div></div>`;

    const o=c.owner_stats||{};
    // Medians don't aggregate, so the rollup file nulls them; the mean of
    // FSA means weighted by owner households IS exact, so show that instead
    // of a dash — with the label changed so the two aren't confused.
    const valLabel=opts.isRollup?'Average dwelling value':'Median dwelling value';
    const valNum=opts.isRollup?o.average_dwelling_value:o.median_dwelling_value;
    $('census-owner-kpis').innerHTML=`
      <div class="kpi-item"><div class="kpi-name">Owners with a mortgage</div><div class="kpi-values"><div class="kpi-pct">${o.pct_with_mortgage!=null?o.pct_with_mortgage+'%':'—'}</div></div></div>
      <div class="kpi-item"><div class="kpi-name">Spending 30%+ on shelter</div><div class="kpi-values"><div class="kpi-pct">${o.pct_spending_30pct_shelter!=null?o.pct_spending_30pct_shelter+'%':'—'}</div></div></div>
      <div class="kpi-item"><div class="kpi-name">In core housing need</div><div class="kpi-values"><div class="kpi-pct">${o.pct_core_housing_need!=null?o.pct_core_housing_need+'%':'—'}</div></div></div>
      <div class="kpi-item"><div class="kpi-name">${valLabel}</div><div class="kpi-values"><div class="kpi-pct">${valNum!=null?'$'+valNum.toLocaleString():'—'}</div></div></div>`;
    $('census-note').innerHTML=opts.isRollup?CENSUS_NOTE_REGION(opts.scope):CENSUS_NOTE_FSA;
    $('census-title').textContent=opts.isRollup
      ?`Housing stock, ${opts.scope} — 2021 Census`
      :'Neighbourhood housing stock — 2021 Census';
}

// ── Fuel breakdown: per-fuel pre/post boxes (sized to max(pre,post), filled
// to the actual value) plus a per-fuel savings/increase row underneath ──
function renderWaterfall(){
  // NOTE: fuel column names are hardcoded (Pre_Electricity, Pre_NaturalGas, etc.)
  // If new fuel types are added to the CSV, add them here. Key = CSV column suffix, lbl = display name.
  const FUELS=[['Electricity','Electricity'],['NaturalGas','Natural Gas'],['Oil','Oil'],['Propane','Propane'],['Wood','Wood']];
  const fuelLabels=[],preVals=[],postVals=[];
  FUELS.forEach(([key,lbl])=>{
    const pre=FILTERED.map(r=>num(r[`Pre_${key}`])||0);
    const post=FILTERED.map(r=>num(r[`Post_${key}`])||0);
    const pt=Math.round(pre.reduce((s,v)=>s+v,0));
    const qt=Math.round(post.reduce((s,v)=>s+v,0));
    if(pt===0&&qt===0)return;
    fuelLabels.push(lbl);preVals.push(pt);postVals.push(qt);
  });
  drawFuelBreakdown(fuelLabels,preVals,postVals);
}

// Same chart, space-heating consumption only (Pre_Heat*/Post_Heat* — the
// portion HOT2000 attributes to heating, excluding DHW and appliances). FSA
// mode only: the province precompute ships whole-house per-fuel means but no
// heating-only equivalent, so there is nothing to draw province-wide.
function renderWaterfallHeating(){
  const FUELS=[['Electricity','Electricity'],['NaturalGas','Natural Gas'],['Oil','Oil'],['Propane','Propane'],['Wood','Wood']];
  const fuelLabels=[],preVals=[],postVals=[];
  let anyData=false;
  FUELS.forEach(([key,lbl])=>{
    // A selection with no heating breakdown at all must not read as a row of
    // zeroes — track whether any row actually carried a value.
    let pt=0,qt=0;
    FILTERED.forEach(r=>{
      const a=num(r[`Pre_Heat${key}`]),b=num(r[`Post_Heat${key}`]);
      if(a!==null){pt+=a;anyData=true;}
      if(b!==null){qt+=b;anyData=true;}
    });
    pt=Math.round(pt);qt=Math.round(qt);
    if(pt===0&&qt===0)return;
    fuelLabels.push(lbl);preVals.push(pt);postVals.push(qt);
  });
  const show=anyData&&fuelLabels.length>0;
  toggleHeatWaterfallCard(show);
  if(!show)return;
  drawFuelBreakdown(fuelLabels,preVals,postVals,'waterfall-heat-chart','waterfall-heat-legend');
}
function toggleHeatWaterfallCard(show){
  $('waterfall-heat-card').style.display=show?'':'none';
}

// ── Custom canvas chart (not Chart.js — the partial-fill boxes are bespoke) ──
// Two instances exist (whole-house and heating-only), so the per-chart state
// — last args, resize observer, hit boxes — is keyed by canvas id rather
// than held in single module-level slots.
let _fuelTooltipEl=null;
const _fuelState=new Map(); // canvasId -> {args, ro, boxes}
function fuelState(canvasId){
  if(!_fuelState.has(canvasId))_fuelState.set(canvasId,{args:null,ro:null,boxes:[]});
  return _fuelState.get(canvasId);
}

function drawFuelBreakdown(fuelLabels,preVals,postVals,canvasId,legendId){
  canvasId=canvasId||'waterfall-chart';legendId=legendId||'waterfall-legend';
  const st=fuelState(canvasId);
  st.args=[fuelLabels,preVals,postVals,canvasId];
  const canvas=$(canvasId);
  setChartLegend(legendId,fuelLabels.map(lbl=>({label:lbl,color:FUEL_COLORS[lbl]||PAL.tick})));
  if(!st.ro){
    st.ro=new ResizeObserver(()=>{ if(st.args)paintFuelBreakdown(...st.args); });
    st.ro.observe(canvas.parentElement);
    canvas.addEventListener('mousemove',e=>onFuelBreakdownHover(e,canvasId));
    canvas.addEventListener('mouseleave',hideFuelTooltip);
  }
  paintFuelBreakdown(fuelLabels,preVals,postVals,canvasId);
}

function roundRectPath(ctx,x,y,w,h,r){
  r=Math.max(0,Math.min(r,w/2,h/2));
  ctx.beginPath();
  ctx.moveTo(x+r,y);
  ctx.arcTo(x+w,y,x+w,y+h,r);
  ctx.arcTo(x+w,y+h,x,y+h,r);
  ctx.arcTo(x,y+h,x,y,r);
  ctx.arcTo(x,y,x+w,y,r);
  ctx.closePath();
}

function paintFuelBreakdown(fuelLabels,preVals,postVals,canvasId){
  canvasId=canvasId||'waterfall-chart';
  const canvas=$(canvasId);
  const _fuelBoxes=fuelState(canvasId).boxes;
  const wrap=canvas.parentElement;
  const wCss=wrap.clientWidth||300,hCss=wrap.clientHeight||280;
  const dpr=window.devicePixelRatio||1;
  canvas.width=wCss*dpr;canvas.height=hCss*dpr;
  canvas.style.width=wCss+'px';canvas.style.height=hCss+'px';
  const ctx=canvas.getContext('2d');
  ctx.setTransform(dpr,0,0,dpr,0,0);
  ctx.clearRect(0,0,wCss,hCss);
  _fuelBoxes.length=0;

  if(!fuelLabels.length){
    ctx.fillStyle=PAL.tick;ctx.font='13px Inter, sans-serif';ctx.textAlign='center';
    ctx.fillText('No fuel data for this selection',wCss/2,hCss/2);
    return;
  }

  const leftLabelW=96,rightPad=12,topPad=8,rowGap=20,rowH=54,gapPx=4;
  const drawW=wCss-leftLabelW-rightPad;
  const colors=fuelLabels.map(l=>FUEL_COLORS[l]||PAL.tick);

  function drawValueLabel(x,bw,yTop,text,light){
    ctx.font='600 11px Inter, sans-serif';ctx.textAlign='center';
    if(ctx.measureText(text).width>bw-6)return; // skip if it would overflow the box
    ctx.fillStyle=light?'#fff':PAL.text;
    ctx.fillText(text,x+bw/2,yTop+rowH/2+4);
  }
  // Compact form (5.9B / 21M / 1.2k) for boxes too narrow for the full number.
  const fmt=v=>Math.abs(v)>=1000?new Intl.NumberFormat('en',{notation:'compact',maximumFractionDigits:1}).format(v):Math.round(v).toLocaleString();
  function drawRowLabel(text,yTop){
    ctx.font='600 11px Inter, sans-serif';ctx.fillStyle=PAL.axis;ctx.textAlign='right';
    ctx.fillText(text,leftLabelW-10,yTop+rowH/2+4);
  }

  // Pre/post rows: each fuel's box width = its max(pre,post) share of the total;
  // the same box widths/positions are reused for both rows so they align.
  const maxVals=fuelLabels.map((_,i)=>Math.max(preVals[i],postVals[i],1));
  const totalMax=maxVals.reduce((s,v)=>s+v,0)||1;
  const usableW=drawW-gapPx*(fuelLabels.length-1);
  const boxWidths=maxVals.map(v=>(v/totalMax)*usableW);

  function drawPrePostRow(vals,label,yTop){
    let x=leftLabelW;
    drawRowLabel(label,yTop);
    fuelLabels.forEach((lbl,i)=>{
      const bw=boxWidths[i];
      const ratio=Math.max(0,Math.min(1,vals[i]/maxVals[i]));
      ctx.fillStyle=colors[i]+'22';ctx.strokeStyle=colors[i];ctx.lineWidth=1.25;
      roundRectPath(ctx,x,yTop,bw,rowH,4);ctx.fill();ctx.stroke();
      if(ratio>0){
        ctx.save();
        roundRectPath(ctx,x,yTop,bw,rowH,4);ctx.clip();
        ctx.fillStyle=colors[i];
        ctx.fillRect(x,yTop,bw*ratio,rowH);
        ctx.restore();
      }
      drawValueLabel(x,bw,yTop,fmt(vals[i]),ratio>0.55);
      _fuelBoxes.push({x,y:yTop,w:bw,h:rowH,fuel:lbl,rowLabel:label,value:vals[i]});
      x+=bw+gapPx;
    });
  }

  const row1Y=topPad,row2Y=row1Y+rowH+rowGap;
  drawPrePostRow(preVals,'Pre-retrofit',row1Y);
  drawPrePostRow(postVals,'Post-retrofit',row2Y);

  // Savings row: ONE bar for total savings, on the same px-per-kWh scale as
  // the pre/post rows above (totalMax/usableW), not its own independent scale.
  const row3Y=row2Y+rowH+rowGap+8;
  const totalSaved=preVals.reduce((s,v)=>s+v,0)-postVals.reduce((s,v)=>s+v,0);
  const sx=usableW/totalMax;
  const savedBw=Math.max(Math.abs(totalSaved)*sx,2);
  drawRowLabel('Savings',row3Y);
  ctx.fillStyle=totalSaved>=0?PAL.pos:PAL.neg;
  roundRectPath(ctx,leftLabelW,row3Y,savedBw,rowH,4);ctx.fill();
  drawValueLabel(leftLabelW,savedBw,row3Y,`${totalSaved>=0?'−':'+'}${fmt(Math.abs(totalSaved))}`,true);
  _fuelBoxes.push({x:leftLabelW,y:row3Y,w:savedBw,h:rowH,fuel:'Total',rowLabel:'Savings',value:totalSaved});

  ctx.font='600 11px Inter, sans-serif';ctx.textAlign='left';ctx.fillStyle=PAL.text;
  ctx.fillText(`${totalSaved>=0?'Total saved':'Total increased'}: ${Math.abs(Math.round(totalSaved)).toLocaleString()} kWh`,leftLabelW,row3Y+rowH+18);
}

function ensureFuelTooltip(){
  if(_fuelTooltipEl)return _fuelTooltipEl;
  const el=document.createElement('div');
  el.style.cssText='position:fixed;pointer-events:none;background:var(--navy);color:var(--on-navy);font-size:12px;padding:6px 9px;border-radius:6px;box-shadow:0 4px 12px rgba(11,37,69,.25);z-index:1000;display:none;font-family:Inter,sans-serif;line-height:1.4';
  document.body.appendChild(el);
  return (_fuelTooltipEl=el);
}
function hideFuelTooltip(){ if(_fuelTooltipEl)_fuelTooltipEl.style.display='none'; }
function onFuelBreakdownHover(e,canvasId){
  canvasId=canvasId||'waterfall-chart';
  const rect=$(canvasId).getBoundingClientRect();
  const x=e.clientX-rect.left,y=e.clientY-rect.top;
  const hit=fuelState(canvasId).boxes.find(b=>x>=b.x&&x<=b.x+b.w&&y>=b.y&&y<=b.y+b.h);
  const tip=ensureFuelTooltip();
  if(!hit){tip.style.display='none';return;}
  tip.innerHTML=hit.rowLabel==='Savings'
    ?`<strong>${hit.fuel}</strong><br>${hit.value>=0?'Saved':'Increased'}: ${Math.abs(Math.round(hit.value)).toLocaleString()} kWh`
    :`<strong>${hit.fuel}</strong> — ${hit.rowLabel}<br>${Math.round(hit.value).toLocaleString()} kWh`;
  tip.style.display='block';
  tip.style.left=(e.clientX+12)+'px';
  tip.style.top=(e.clientY+12)+'px';
}

// ── Insulation KPI ────────────────────────────────────────────────
function renderKPI(n,fs){
  const KPIs=[
    {label:'Roof insulation',pre:'Pre_RoofInsulation',post:'Post_RoofInsulation',unit:'RSI',hi:true,toR:true},
    {label:'Wall insulation',pre:'Pre_WallInsulation',post:'Post_WallInsulation',unit:'RSI',hi:true,toR:true},
    {label:'Foundation ins.',pre:'Pre_FoundationInsulation',post:'Post_FoundationInsulation',unit:'RSI',hi:true,toR:true},
    {label:'Air leakage',pre:'Pre_AirLeakage',post:'Post_AirLeakage',unit:'ACH50',hi:false},
  ];
  let html=KPIs.map(k=>{
    const pv=FILTERED.map(r=>num(r[k.pre])).filter(v=>v!==null&&v>0);
    const qv=FILTERED.map(r=>num(r[k.post])).filter(v=>v!==null&&v>0);
    const pm=median(pv),qm=median(qv);
    if(pm===null||qm===null)return'';
    const d=qm-pm,imp=k.hi?d>0:d<0;
    if(k.toR){
      const pR=pm*RSI_TO_R,qR=qm*RSI_TO_R,dR=d*RSI_TO_R;
      return `<div class="kpi-item">
        <div class="kpi-name">${k.label}</div>
        <div class="kpi-values"><div class="kpi-pre">${pR.toFixed(1)}</div><div class="kpi-arrow">→</div><div class="kpi-post">${qR.toFixed(1)}</div></div>
        <div class="kpi-unit">R-value <span class="kpi-rsi cap-advanced">(${pm.toFixed(1)} → ${qm.toFixed(1)} RSI)</span></div>
        <div class="kpi-delta ${Math.abs(dR)<0.05?'flat':imp?'good':'bad'}">${Math.abs(dR)<0.05?'no change':`${dR>=0?'+':''}${dR.toFixed(1)} R ${imp?'▲ improved':'▼ declined'}`}</div>
      </div>`;
    }
    return `<div class="kpi-item">
      <div class="kpi-name">${k.label}</div>
      <div class="kpi-values"><div class="kpi-pre">${pm.toFixed(1)}</div><div class="kpi-arrow">→</div><div class="kpi-post">${qm.toFixed(1)}</div></div>
      <div class="kpi-unit"><span class="cap-simple">air changes per hour (ACH50)</span><span class="cap-advanced">${k.unit}</span></div>
      <div class="kpi-delta ${Math.abs(d)<0.05?'flat':imp?'good':'bad'}">${Math.abs(d)<0.05?'no change':`${d>=0?'+':''}${d.toFixed(1)} ${k.unit} ${imp?'▲ improved':'▼ declined'}`}</div>
    </div>`;
  }).join('');
  const fsPct=n?Math.round(fs/n*100):0;
  html+=`<div class="kpi-item">
    <div class="kpi-name">Fuel switching</div>
    <div class="kpi-values"><div class="kpi-pct">${fsPct}%</div></div>
    <div class="kpi-unit">of <span class="cap-simple">homes shown</span><span class="cap-advanced">matched homes</span></div>
  </div>`;
  $('kpi-grid').innerHTML=html;
}

// Draws a small canvas swatch for the combo-chart legend so it shows the
// dataset's real line style (dash pattern + thickness) and point shape,
// not just a flat colour box — Chart.js's own legend can't render a dash
// pattern when usePointStyle is on, so we hand it a pre-rendered icon per
// dataset via generateLabels instead.
function legendLineIcon(ds){
  const w=26,h=14,cv=document.createElement('canvas');
  cv.width=w;cv.height=h;
  const ctx=cv.getContext('2d'),cy=h/2;
  if(ds.type==='bar'){
    ctx.fillStyle=ds.backgroundColor;ctx.strokeStyle=ds.borderColor;ctx.lineWidth=1.25;
    ctx.fillRect(2,3,w-4,h-6);ctx.strokeRect(2,3,w-4,h-6);
    return cv;
  }
  ctx.strokeStyle=ds.borderColor;ctx.lineWidth=ds.borderWidth||2;
  ctx.setLineDash(ds.borderDash||[]);
  ctx.beginPath();ctx.moveTo(1,cy);ctx.lineTo(w-1,cy);ctx.stroke();
  ctx.setLineDash([]);
  const cx=w/2,r=ds.pointStyle==='circle'?3.5:4;
  ctx.fillStyle=ds.borderColor;
  if(ds.pointStyle==='circle'){
    ctx.beginPath();ctx.arc(cx,cy,r,0,Math.PI*2);ctx.fill();
  }else if(ds.pointStyle==='crossRot'){
    ctx.strokeStyle=ds.borderColor;ctx.lineWidth=2;
    ctx.beginPath();
    ctx.moveTo(cx-r,cy-r);ctx.lineTo(cx+r,cy+r);
    ctx.moveTo(cx+r,cy-r);ctx.lineTo(cx-r,cy+r);
    ctx.stroke();
  }
  return cv;
}
// ── Insulation pre/post histogram ─────────────────────────────────
// Shared by FSA and province modes, and by EUI/GHG/heat-loss above: one
// combined chart per measure — Pre/Post as filled area lines, Improvement
// as bars — all on the same axis, so no value/reduction toggle is needed.
// The Improvement dataset is simply omitted when deltaBins is empty (some
// province-precomputed measures don't ship a delta histogram).
function drawComboChart(canvasId,chartKey,preBins,postBins,deltaBins,unit,preLabel='Before retrofit',postLabel='After retrofit',deltaLabel='Improvement'){
  dc(chartKey);
  // postBins=null means "single-series mode" (e.g. hpsizing's one-temperature
  // view) -- omit the second line entirely rather than drawing a flat zero.
  const allKeys=[...new Set([...Object.keys(preBins||{}),...Object.keys(postBins||{}),...Object.keys(deltaBins||{})])].map(Number).sort((a,b)=>a-b);
  const datasets=[];
  // Chart.js draws LOWER order values on top — bars need order:1 (front) so
  // they paint over the area fills, and the lines order:2 (behind). Verified
  // empirically (opaque test chart) since Chart.js's own docs are ambiguous
  // on this point.
  if(deltaBins&&Object.keys(deltaBins).length){
    datasets.push({type:'bar',label:deltaLabel,data:allKeys.map(k=>deltaBins[k]||0),backgroundColor:al(PAL.secondary,'99'),borderColor:'#000',borderWidth:1.5,borderRadius:2,order:1,pointStyle:'rect'});
  }
  // Pre/post are told apart three ways, not colour alone: point shape (x vs
  // dot), line style (dashed vs solid), and thickness (post is 1.25x pre).
  // No area fill — overlapping pre/post lines never blend into a third
  // colour.
  datasets.push(
    {type:'line',label:preLabel,data:allKeys.map(k=>(preBins||{})[k]||0),borderColor:PRE_LINE,pointRadius:4,pointStyle:'crossRot',pointBorderWidth:2,borderWidth:2,borderDash:[7,4],tension:0.25,fill:false,order:2},
  );
  if(postBins){
    datasets.push({type:'line',label:postLabel,data:allKeys.map(k=>postBins[k]||0),borderColor:POST_LINE,pointRadius:3,pointStyle:'circle',borderWidth:2.5,tension:0.25,fill:false,order:2});
  }
  charts[chartKey]=new Chart($(canvasId).getContext('2d'),{
    type:'bar',
    data:{labels:allKeys,datasets},
    options:{responsive:true,maintainAspectRatio:false,
      plugins:{legend:{position:'top',labels:{font:{size:12},boxWidth:12,usePointStyle:true,pointStyleWidth:24,
        generateLabels:c=>c.data.datasets.map((ds,i)=>({text:ds.label,datasetIndex:i,hidden:!c.isDatasetVisible(i),pointStyle:legendLineIcon(ds),fillStyle:ds.borderColor,strokeStyle:ds.borderColor,lineWidth:1,fontColor:PAL.axis}))}},
        tooltip:{callbacks:{title:i=>`${i[0].label} ${unit}`,label:i=>`${i.dataset.label}: ${i.raw.toLocaleString()} homes`}}},
      scales:{x:{title:{display:true,text:unit,font:{size:11},color:PAL.axis},ticks:{font:{size:10},color:PAL.tick,maxTicksLimit:20},grid:{display:false}},
              y:{title:{display:true,text:'Homes',font:{size:11},color:PAL.axis},ticks:{font:{size:11},color:PAL.tick},grid:{color:PAL.track}}}}
  });
}

// Builds pre/post/delta bins straight from FILTERED rows. `toR` converts
// RSI source columns to R-value buckets (insulation); air leakage (ACH50)
// passes toR=false and is left as-is. `invert` flips which direction counts
// as "improved" (lower is better for air leakage, higher for insulation).
function fsaMeasureBins(preCol,postCol,maxVal,step,toR,invert){
  const conv=v=>toR?v*RSI_TO_R:v;
  function mk(col){
    const b={};
    FILTERED.forEach(r=>{
      const raw=num(r[col]);if(raw===null||raw<=0)return;
      const v=conv(raw);if(v>maxVal)return;
      const k=Math.floor(v/step)*step;b[k]=(b[k]||0)+1;
    });
    return b;
  }
  const preBins=mk(preCol),postBins=mk(postCol);
  const deltaBins={};
  FILTERED.forEach(r=>{
    const preRaw=num(r[preCol]),postRaw=num(r[postCol]);
    if(preRaw===null||postRaw===null||preRaw<=0||postRaw<=0)return;
    const d=invert?(preRaw-postRaw):(postRaw-preRaw);
    if(d<=0)return;
    const dv=conv(d);if(dv>maxVal)return;
    const k=Math.floor(dv/step)*step;deltaBins[k]=(deltaBins[k]||0)+1;
  });
  return{preBins,postBins,deltaBins};
}

function renderInsulDist(){
  let b=fsaMeasureBins('Pre_RoofInsulation','Post_RoofInsulation',80,2,true,false);
  drawComboChart('roof-chart','roof',b.preBins,b.postBins,b.deltaBins,'R-value');
  b=fsaMeasureBins('Pre_WallInsulation','Post_WallInsulation',40,2,true,false);
  drawComboChart('wall-chart','wall',b.preBins,b.postBins,b.deltaBins,'R-value');
  b=fsaMeasureBins('Pre_FoundationInsulation','Post_FoundationInsulation',35,2,true,false);
  drawComboChart('fnd-chart','fnd',b.preBins,b.postBins,b.deltaBins,'R-value');
  b=fsaMeasureBins('Pre_AirLeakage','Post_AirLeakage',20,1,false,true);
  drawComboChart('air-chart','air',b.preBins,b.postBins,b.deltaBins,'ACH50');
}

// ── Measures bar ──────────────────────────────────────────────────
function renderMeasures(n){
  if(!n){$('measures-list').innerHTML='<div class="state-msg"><strong>No matches</strong></div>';return;}
  $('measures-list').innerHTML=MEASURES.map(m=>{
    const c=FILTERED.filter(r=>flag(r,m.key)).length,p=Math.round(c/n*100);
    return{m,p};
  }).sort((a,b)=>b.p-a.p).map(({m,p})=>
    `<div class="measure-row"><div class="measure-label">${m.label}<button type="button" class="info-btn" aria-label="How is ${m.label} counted?" data-info="${m.tip}">?</button></div><div class="bar-track"><div class="bar-fill" style="width:${p}%;background:${m.color}"></div></div><div class="bar-pct">${p}%</div></div>`
  ).join('');
}

// ── Measures by vintage (FSA mode only) ─────────────────────────────
function toggleVintageCard(show){
  $('vintage-card').style.display=show?'':'none';
}

function renderVintageMeasures(){
  dc('vintage');
  const buckets={}; // decade -> {total, [measureKey]: count}
  FILTERED.forEach(r=>{
    const yr=parseInt(r.YearBuilt);
    if(!yr||yr<1850||yr>2030)return;
    const d=Math.floor(yr/BINS.year)*BINS.year;
    if(!buckets[d])buckets[d]={total:0};
    buckets[d].total++;
    MEASURES.forEach(m=>{ if(flag(r,m.key))buckets[d][m.key]=(buckets[d][m.key]||0)+1; });
  });
  const labels=Object.keys(buckets).map(Number).sort((a,b)=>a-b)
    .filter(d=>buckets[d].total>=20); // drop noisy small buckets

  if(!labels.length){
    drawEmptyCanvasMsg('vintage-chart','Not enough homes per vintage to show this breakdown');
    return;
  }

  charts['vintage']=new Chart($('vintage-chart').getContext('2d'),{
    type:'bar',
    data:{labels:labels.map(d=>`${d}s`),datasets:MEASURES.map(m=>({
      label:m.label,
      data:labels.map(d=>Math.round((buckets[d][m.key]||0)/buckets[d].total*100)),
      backgroundColor:m.color,borderWidth:0,borderRadius:2,
    }))},
    options:{responsive:true,maintainAspectRatio:false,
      plugins:{legend:{position:'top',labels:{font:{size:11},boxWidth:10}},
        tooltip:{callbacks:{
          title:i=>`Built ${i[0].label}`,
          label:i=>`${i.dataset.label}: ${i.raw}% (n=${buckets[labels[i.dataIndex]].total})`,
        }}},
      scales:{x:{ticks:{font:{size:11},color:PAL.axis},grid:{display:false}},
              y:{ticks:{font:{size:11},color:PAL.tick,callback:v=>v+'%'},grid:{color:PAL.track},max:100}}}
  });
}

function drawEmptyCanvasMsg(canvasId,msg){
  dc(canvasId.replace('-chart',''));
  const canvas=$(canvasId);
  const wrap=canvas.parentElement;
  const wCss=wrap.clientWidth||300,hCss=wrap.clientHeight||200;
  const dpr=window.devicePixelRatio||1;
  canvas.width=wCss*dpr;canvas.height=hCss*dpr;
  canvas.style.width=wCss+'px';canvas.style.height=hCss+'px';
  const ctx=canvas.getContext('2d');
  ctx.setTransform(dpr,0,0,dpr,0,0);
  ctx.clearRect(0,0,wCss,hCss);
  ctx.fillStyle=PAL.tick;ctx.font='13px Inter, sans-serif';ctx.textAlign='center';
  ctx.fillText(msg,wCss/2,hCss/2);
}

// ── Energy saving histogram (1% bins) ────────────────────────────
function renderHist(savings){
  dc('hist');
  if(!savings.length)return;
  // Avoid Math.min(...savings)/Math.max(...savings): spreading 600k+ elements
  // as call arguments overflows the engine's call stack. Plain loop has no such limit.
  let minRaw=savings[0],maxRaw=savings[0];
  for(let i=1;i<savings.length;i++){
    const v=savings[i];
    if(v<minRaw)minRaw=v;
    if(v>maxRaw)maxRaw=v;
  }
  const minV=Math.floor(minRaw*100);
  const maxV=Math.ceil(maxRaw*100);
  const bins={};
  for(let i=minV;i<=maxV;i++)bins[i]=0;
  savings.forEach(v=>{const b=Math.round(v*100);if(bins[b]!==undefined)bins[b]++;});
  const labels=Object.keys(bins).map(Number).sort((a,b)=>a-b);
  charts['hist']=new Chart($('hist-chart').getContext('2d'),{
    type:'bar',
    data:{labels:labels.map(k=>`${k}%`),datasets:[{
      data:labels.map(k=>bins[k]),
      backgroundColor:labels.map(k=>k<0?al(PAL.neg,'B3'):al(PAL.pos,'B3')),
      borderColor:labels.map(k=>k<0?PAL.neg:PAL.pos),
      borderWidth:0.5,borderRadius:0,barPercentage:1.0,categoryPercentage:1.0
    }]},
    options:{responsive:true,maintainAspectRatio:false,
      plugins:{legend:{display:false},tooltip:{callbacks:{title:i=>`${i[0].label} saving`,label:i=>`${i.raw.toLocaleString()} homes`}}},
      scales:{
        x:{title:{display:true,text:'Energy saving %',font:{size:11},color:PAL.axis},
          ticks:{font:{size:9},color:PAL.tick,maxTicksLimit:30,
            callback:function(v,i){const l=labels[i];return l%10===0?`${l}%`:''}},
          grid:{display:false}},
        y:{title:{display:true,text:'Homes',font:{size:11},color:PAL.axis},ticks:{font:{size:11},color:PAL.tick},grid:{color:PAL.track}}
      }
    }
  });
}

// ════════════════════════════════════════════════════════════════
// PROVINCE-WIDE VIEW (no FSA selected) — reads precomputed bins/medians
// from province_json/<PROV>.json instead of scanning raw rows. Kept
// separate from the FSA-mode renderers above by design: FSA mode is
// proven/working code operating on real rows, this operates on a fixed,
// limited filter surface (house type only — see project notes on why
// fuel/depth aren't available province-wide) precomputed in Python.
// Bin widths/thresholds here MUST match precompute_province_stats.py
// exactly or the two views will show different numbers for the same data.
// ════════════════════════════════════════════════════════════════

function renderProvince(payload){
  const slice=payload.by_type[SELECTED_TYPE||'All types'];
  if(!slice){
    $('result-count').textContent='0';
    return;
  }
  _lastProvinceSlice=slice;
  _lastProvincePayload=payload;
  const n=slice.row_count||0;
  $('result-count').textContent=n.toLocaleString();
  $('small-n-warn').style.display=(n>0&&n<30)?'':'none';
  // No per-FSA audited-population denominator in the province rollup, so the
  // match-count line has no % suffix here (the % is FSA-view only).
  $('match-count-extra').innerHTML='';

  const med=slice.median_saving_pct;
  $('s-median').textContent=med!=null?Math.round(med*100)+'%':'—';
  $('s-median-sub').innerHTML=med!=null?(med>=0?'<span class="cap-simple">typical energy saved</span><span class="cap-advanced">median energy saved</span>':'<span class="cap-simple">typical energy increase</span><span class="cap-advanced">median energy increased</span>'):'';

  $('s-deep').textContent=(slice.deep_retrofit_count||0).toLocaleString();
  $('s-deep-sub').innerHTML=n?`${Math.round((slice.deep_retrofit_count||0)/n*100)}${OF_MATCHED}`:'';
  $('s-hp').textContent=(slice.heat_pump_count||0).toLocaleString();
  $('s-hp-sub').innerHTML=n?`${Math.round((slice.heat_pump_count||0)/n*100)}${OF_MATCHED}`:'';
  $('s-fs').textContent=(slice.fuel_switch_count||0).toLocaleString();
  $('s-fs-sub').innerHTML=n?`${Math.round((slice.fuel_switch_count||0)/n*100)}${OF_MATCHED}`:'';

  $('s-eui-saving').textContent=slice.eui_saving!=null?slice.eui_saving:'—';
  window._euiMedianPre=Math.round(slice.eui_pre_median||0);
  window._euiMedianPost=Math.round(slice.eui_post_median||0);

  $('s-solar').textContent=(slice.solar_post_count||0).toLocaleString();
  $('s-solar-sub').innerHTML=n?`${slice.solar_post_pct||0}${OF_MATCHED}`:'';

  const totalMeasureFlags=(slice.measures||[]).reduce((s,m)=>s+(m.count||0),0);
  $('s-avg-measures').textContent=n?(totalMeasureFlags/n).toFixed(1):'—';

  renderProvinceEUI(slice);
  renderProvinceGHG(slice);
  renderProvinceCost(slice);
  renderRetrofitCost();
  renderProvinceKPI(slice);
  renderProvinceInsulDist(slice);
  renderProvinceMeasures(slice);
  renderProvinceHist(slice);
  renderProvinceHeatLossComponents(slice);
  renderAdvancedSections();
  $('table-card').style.display='none';
  $('sec-individual').style.display='none';
  setLoading(false);
}

// Bin objects from precompute_province_stats.py have integer/numeric keys
// already (e.g. {"1990":42}); this turns one into Chart.js-ready
// sorted [labels, data] arrays, mirroring how each FSA-mode renderer
// builds `allKeys` from its own bins{} object.
function sortedBinArrays(bins){
  const keys=Object.keys(bins).map(Number).sort((a,b)=>a-b);
  return [keys, keys.map(k=>bins[k]||0)];
}

// When no specific house type is filtered, split "All types" into Single
// detached vs Attached (every other type summed) so the histogram carries
// a legend; once a single type is selected the split is meaningless (it's
// all one bucket), so fall back to the plain per-type bins.
function splitSingleVsAttached(payload,binKey){
  const sdSlice=payload.by_type['Single Detached'];
  if(!sdSlice)return null;
  const sdBins=sdSlice[binKey]||{};
  const atBins={};
  Object.entries(payload.by_type).forEach(([t,s])=>{
    if(t==='All types'||t==='Single Detached')return;
    Object.entries(s[binKey]||{}).forEach(([k,v])=>{atBins[k]=(atBins[k]||0)+v;});
  });
  return {sdBins,atBins};
}

function renderProvinceYearHist(payload){
  dc('year');
  const slice=payload.by_type[SELECTED_TYPE||'All types'];
  const split=!SELECTED_TYPE&&splitSingleVsAttached(payload,'year_built_bins');
  let labels,datasets;
  if(split){
    labels=[...new Set([...Object.keys(split.sdBins),...Object.keys(split.atBins)])].map(Number).sort((a,b)=>a-b);
    datasets=[
      {label:'Single detached',data:labels.map(k=>split.sdBins[k]||0),backgroundColor:al(PAL.primary,'CC'),borderWidth:0,borderRadius:2},
      {label:'Attached',data:labels.map(k=>split.atBins[k]||0),backgroundColor:al(PAL.blue,'CC'),borderWidth:0,borderRadius:2},
    ];
  }else{
    const [keys,data]=sortedBinArrays(slice.year_built_bins||{});
    labels=keys;
    datasets=[{label:SELECTED_TYPE||'All types',data,backgroundColor:al(PAL.primary,'CC'),borderWidth:0,borderRadius:2}];
  }
  setChartLegend('year-legend',split?
    [{label:'Single detached',color:al(PAL.primary,'CC')},{label:'Attached',color:al(PAL.blue,'CC')}]:
    [{label:SELECTED_TYPE||'All types',color:al(PAL.primary,'CC')}]);
  charts['year']=new Chart($('year-chart').getContext('2d'),{
    type:'bar',
    data:{labels,datasets},
    options:{responsive:true,maintainAspectRatio:false,
      plugins:{legend:{display:false},tooltip:{callbacks:{title:i=>`${i[0].label}s`,label:i=>`${i.dataset.label}: ${i.raw.toLocaleString()} homes`}}},
      scales:{x:{stacked:true,ticks:{font:{size:10},color:PAL.tick,maxRotation:45},grid:{display:false}},
              y:{stacked:true,ticks:{font:{size:10},color:PAL.tick},grid:{color:PAL.track}}}}
  });
}

function renderProvinceAreaHist(payload){
  dc('area');
  const slice=payload.by_type[SELECTED_TYPE||'All types'];
  const split=!SELECTED_TYPE&&splitSingleVsAttached(payload,'floor_area_bins');
  let labels,datasets;
  if(split){
    labels=[...new Set([...Object.keys(split.sdBins),...Object.keys(split.atBins)])].map(Number).sort((a,b)=>a-b);
    datasets=[
      {label:'Single detached',data:labels.map(k=>split.sdBins[k]||0),backgroundColor:al(PAL.primary,'CC'),borderWidth:0,borderRadius:2},
      {label:'Attached',data:labels.map(k=>split.atBins[k]||0),backgroundColor:al(PAL.blue,'CC'),borderWidth:0,borderRadius:2},
    ];
  }else{
    const [keys,data]=sortedBinArrays(slice.floor_area_bins||{});
    labels=keys;
    datasets=[{label:SELECTED_TYPE||'All types',data,backgroundColor:al(PAL.pos,'CC'),borderWidth:0,borderRadius:2}];
  }
  setChartLegend('area-legend',split?
    [{label:'Single detached',color:al(PAL.primary,'CC')},{label:'Attached',color:al(PAL.blue,'CC')}]:
    [{label:SELECTED_TYPE||'All types',color:al(PAL.pos,'CC')}]);
  charts['area']=new Chart($('area-chart').getContext('2d'),{
    type:'bar',
    data:{labels,datasets},
    options:{responsive:true,maintainAspectRatio:false,
      plugins:{legend:{display:false},tooltip:{callbacks:{title:i=>`${i[0].label}–${+i[0].label+50} m²`,label:i=>`${i.dataset.label}: ${i.raw.toLocaleString()} homes`}}},
      scales:{x:{stacked:true,ticks:{font:{size:10},color:PAL.tick,maxRotation:45},grid:{display:false}},
              y:{stacked:true,ticks:{font:{size:10},color:PAL.tick},grid:{color:PAL.track}}}}
  });
}

// Same donut() helper used by FSA mode — it already takes a precomputed
// countMap, so no province-specific variant needed for the drawing itself.
function renderProvinceTypeDonut(payload){
  // When a specific house type is selected the full-mix donut is misleading
  // (it stays unchanged while the result count drops). Show the selected
  // type as a single slice instead, so the donut matches the active filter.
  if(SELECTED_TYPE && payload.by_type[SELECTED_TYPE]){
    const slice=payload.by_type[SELECTED_TYPE];
    donut('type-chart',{[SELECTED_TYPE]:slice.row_count||0},'type',slice.row_count||0);
  }else{
    const allSlice=payload.by_type['All types'];
    donut('type-chart',allSlice.type_counts||{},'type',allSlice.row_count||0);
  }
}
function renderProvinceStoreyDonut(slice){
  donut('storey-chart',slice.storey_counts||{},'storey',slice.row_count||0);
}

function renderProvinceSankey(slice){
  const svg=$('sankey-svg');svg.innerHTML='';
  const rawFlows=slice.sankey_flows||{};
  if(!Object.keys(rawFlows).length)return;
  // Re-group through sankeyFuelLabel client-side too, not just server-side
  // in precompute_province_stats.py -- keeps this correct even against an
  // older province_json that predates that aggregation, and is a no-op once
  // the server-side data is already collapsed to 'Wood'.
  const flows={};
  Object.entries(rawFlows).forEach(([k,v])=>{
    const [a,b]=k.split('|||');
    const key=`${sankeyFuelLabel(a)}|||${sankeyFuelLabel(b)}`;
    if(!flows[key])flows[key]={pre:0,post:0};
    flows[key].pre+=v.pre;flows[key].post+=v.post;
  });
  const preMap={},postMap={};
  Object.entries(flows).forEach(([k,v])=>{
    const [a,b]=k.split('|||');
    preMap[a]=(preMap[a]||0)+v.pre;
    postMap[b]=(postMap[b]||0)+v.post;
  });
  const preFuels=Object.entries(preMap).sort((a,b)=>b[1]-a[1]).map(e=>e[0]);
  const postFuels=Object.entries(postMap).sort((a,b)=>b[1]-a[1]).map(e=>e[0]);
  const totalPre=Object.values(preMap).reduce((s,v)=>s+v,0);
  const totalPost=Object.values(postMap).reduce((s,v)=>s+v,0);
  const cw=svg.parentElement.clientWidth||700;
  const W=Math.max(cw,500),H=420,PAD=10,BAR=14,LX=145,RX=W-145;
  svg.setAttribute('viewBox',`0 0 ${W} ${H}`);
  svg.setAttribute('height',H);
  const GAP=20;
  const usablePre=H-PAD*2-20-(preFuels.length-1)*GAP;
  const usablePost=H-PAD*2-20-(postFuels.length-1)*GAP;
  // One shared GWh-per-pixel scale for both sides — see renderSankey for
  // why (keeps bar heights absolutely comparable across pre vs post).
  const scale=Math.min(usablePre/totalPre,usablePost/totalPost);

  function layoutNodes(fuels,map,x){
    let y=PAD;
    return fuels.map(f=>{
      const h=Math.max(3,map[f]*scale);
      const node={f,x,y,h};y+=h+GAP;return node;
    });
  }
  const preNodes=layoutNodes(preFuels,preMap,LX);
  const postNodes=layoutNodes(postFuels,postMap,RX);
  const preNM={},postNM={};
  preNodes.forEach(n=>preNM[n.f]=n);
  postNodes.forEach(n=>postNM[n.f]=n);
  const preUsed={},postUsed={};
  preNodes.forEach(n=>{preUsed[n.f]=0;});
  postNodes.forEach(n=>{postUsed[n.f]=0;});

  const flowList=Object.entries(flows).sort((a,b)=>b[1].pre-a[1].pre);
  flowList.forEach(([k,v])=>{
    const [a,b]=k.split('|||');
    const pn=preNM[a],qn=postNM[b];if(!pn||!qn)return;
    const fhPre=Math.max(2,v.pre*scale);
    const fhPost=Math.max(2,v.post*scale);
    const py=pn.y+preUsed[a],qy=qn.y+postUsed[b];
    preUsed[a]+=fhPre;postUsed[b]+=fhPost;
    const same=a===b;
    const col=same?PAL.pale:(FUEL_COLORS[a]||PAL.tick);
    const mx=(LX+BAR+RX)/2;
    const path=`M${LX+BAR},${py} C${mx},${py} ${mx},${qy} ${RX},${qy} L${RX},${qy+fhPost} C${mx},${qy+fhPost} ${mx},${py+fhPre} ${LX+BAR},${py+fhPre}Z`;
    const el=document.createElementNS('http://www.w3.org/2000/svg','path');
    el.setAttribute('d',path);
    el.setAttribute('fill',col);
    el.setAttribute('opacity',same?'0.45':'0.7');
    const tipText=`${a} → ${b} | Pre: ${(v.pre/1e6).toFixed(2)} GWh | Post: ${(v.post/1e6).toFixed(2)} GWh | Change: ${((v.post-v.pre)/1e6).toFixed(2)} GWh`;
    attachFlowTip(el,tipText);
    svg.appendChild(el);
  });

  function drawNodes(nodes,isLeft){
    nodes.forEach(n=>{
      const rect=document.createElementNS('http://www.w3.org/2000/svg','rect');
      rect.setAttribute('x',n.x);rect.setAttribute('y',n.y);
      rect.setAttribute('width',BAR);rect.setAttribute('height',Math.max(3,n.h));
      rect.setAttribute('fill',FUEL_COLORS[n.f]||PAL.tick);rect.setAttribute('rx',2);
      svg.appendChild(rect);
      const t=document.createElementNS('http://www.w3.org/2000/svg','text');
      const tx=isLeft?n.x-6:n.x+BAR+6;
      t.setAttribute('x',tx);t.setAttribute('y',n.y+Math.max(3,n.h)/2+4);
      t.setAttribute('text-anchor',isLeft?'end':'start');
      t.setAttribute('font-size','11');t.setAttribute('fill',PAL.text);
      t.setAttribute('font-family','Inter,sans-serif');
      const ghw=isLeft?(preMap[n.f]||0):(postMap[n.f]||0);
      t.textContent=`${n.f} (${(ghw/1e6).toFixed(1)} GWh)`;
      svg.appendChild(t);
    });
  }
  drawNodes(preNodes,true);drawNodes(postNodes,false);
}

function renderProvinceEUI(slice){
  const preM=slice.eui_pre_median,postM=slice.eui_post_median;
  const saving=slice.eui_saving;
  $('eui-kpis').innerHTML=`
    <div class="eui-stat"><div class="eui-val eui-pre-val">${preM!=null?Math.round(preM):'—'}</div><div class="eui-lbl"><span class="cap-simple">Before, typical home</span><span class="cap-advanced">Pre-retrofit median</span><br>kWh/m²</div></div>
    <div class="eui-arrow-big">→</div>
    <div class="eui-stat"><div class="eui-val eui-post-val">${postM!=null?Math.round(postM):'—'}</div><div class="eui-lbl"><span class="cap-simple">After, typical home</span><span class="cap-advanced">Post-retrofit median</span><br>kWh/m²</div></div>
    ${saving?`<div style="margin-left:auto;text-align:right"><div class="eui-saving">−${saving}</div><div style="font-size:12px;color:var(--muted)">kWh/m² · <span class="cap-simple">typical home</span><span class="cap-advanced">median home</span></div></div>`:''}`;
  const preBins=slice.eui_pre_bins||{},postBins=slice.eui_post_bins||{};
  // eui_delta_bins ships at a 10 kWh/m² step (see precompute_province_stats.py);
  // re-bucket to the 20 kWh/m² step used here so it can share the same x-axis.
  const rawDelta=slice.eui_delta_bins||{};
  const deltaBins={};
  Object.entries(rawDelta).forEach(([k,v])=>{
    const k2=Math.floor(Number(k)/BINS.eui)*BINS.eui;
    deltaBins[k2]=(deltaBins[k2]||0)+v;
  });
  drawComboChart('eui-chart','eui',preBins,postBins,deltaBins,'kWh/m²');
}

function renderProvinceGHG(slice){
  // slice.ghg_scenarios[GHG_SCENARIO] ships from precompute_province_stats.py
  // (national CA.json rollup via aggregate_canada.py). Falls back to the
  // flat ghg_pre_median/etc ("reported") for older cached payloads that
  // predate ghg_scenarios.
  const scen=(slice.ghg_scenarios&&slice.ghg_scenarios[GHG_SCENARIO])||{
    pre_median:slice.ghg_pre_median,post_median:slice.ghg_post_median,saving:slice.ghg_saving,
    pre_bins:slice.ghg_pre_bins,post_bins:slice.ghg_post_bins,delta_bins:slice.ghg_delta_bins,
    n:slice.ghg_reported_n,coverage_pct:slice.ghg_reported_coverage_pct,
  };
  const preM=scen.pre_median,postM=scen.post_median,saving=scen.saving;
  $('s-ghg-saving').textContent=saving!=null?saving.toFixed(1):'—';
  $('ghg-kpis').innerHTML=`
    <div class="eui-stat"><div class="eui-val eui-pre-val">${preM!=null?preM.toFixed(1):'—'}</div><div class="eui-lbl"><span class="cap-simple">Before, typical home</span><span class="cap-advanced">Pre-retrofit median</span><br><span class="cap-simple">tonnes CO₂/yr</span><span class="cap-advanced">tCO2e/yr</span></div></div>
    <div class="eui-arrow-big">→</div>
    <div class="eui-stat"><div class="eui-val eui-post-val">${postM!=null?postM.toFixed(1):'—'}</div><div class="eui-lbl"><span class="cap-simple">After, typical home</span><span class="cap-advanced">Post-retrofit median</span><br><span class="cap-simple">tonnes CO₂/yr</span><span class="cap-advanced">tCO2e/yr</span></div></div>
    ${saving!=null?`<div style="margin-left:auto;text-align:right"><div class="eui-saving">−${saving.toFixed(1)}</div><div style="font-size:12px;color:var(--muted)"><span class="cap-simple">tonnes CO₂/yr</span><span class="cap-advanced">tCO2e/yr</span> · <span class="cap-simple">typical home</span><span class="cap-advanced">median home</span></div></div>`:''}`;
  const covNote=$('ghg-coverage-note');
  if(covNote)covNote.textContent=(GHG_SCENARIO==='reported'&&scen.n!=null)?`${scen.n.toLocaleString()} homes (${Math.round((scen.coverage_pct||0)*100)}%) have this field`:'';
  const preBins=scen.pre_bins||{},postBins=scen.post_bins||{};
  drawComboChart('ghg-chart','ghg',preBins,postBins,scen.delta_bins||{},'tCO2e/yr');
}

// Energy bill $ — province mode reads precomputed cost bins/medians. Hidden
// when the slice carries no cost fields (province wasn't priced) or COST_PV
// is null (belt-and-suspenders with the s-cost-card gate).
function renderProvinceCost(slice){
  const has=COST_PV&&slice.cost_pre_median!=null;
  setCostCardVisible(!!has);
  if(!has)return;
  const preM=slice.cost_pre_median,postM=slice.cost_post_median,svM=slice.cost_saving_median;
  $('s-cost-saving').textContent=svM!=null?fmtMoney(Math.round(svM)):'—';
  const svStr=svM!=null?(svM>=0?`−${fmtMoney(Math.round(svM))}`:`+${fmtMoney(Math.round(-svM))}`):null;
  $('cost-kpis').innerHTML=`
    <div class="eui-stat"><div class="eui-val eui-pre-val">${preM!=null?fmtMoney(Math.round(preM)):'—'}</div><div class="eui-lbl"><span class="cap-simple">Before, typical home</span><span class="cap-advanced">Pre-retrofit median</span><br>$/yr</div></div>
    <div class="eui-arrow-big">→</div>
    <div class="eui-stat"><div class="eui-val eui-post-val">${postM!=null?fmtMoney(Math.round(postM)):'—'}</div><div class="eui-lbl"><span class="cap-simple">After, typical home</span><span class="cap-advanced">Post-retrofit median</span><br>$/yr</div></div>
    ${svStr!=null?`<div style="margin-left:auto;text-align:right"><div class="eui-saving">${svStr}</div><div style="font-size:12px;color:var(--muted)">$/yr · <span class="cap-simple">typical home</span><span class="cap-advanced">median home</span></div></div>`:''}`;
  drawComboChart('cost-chart','cost',slice.cost_pre_bins||{},slice.cost_post_bins||{},slice.cost_delta_bins||{},'$/yr');
}

function renderProvinceHeatLoss(slice){
  // Design heat loss in kW (peak demand), 2 kW bins — must match both
  // BINS.heatloss and precompute_province_stats.py's step=2.
  const preBins=slice.heatloss_pre_bins||{},postBins=slice.heatloss_post_bins||{};
  drawComboChart('heatloss-chart','heatloss',preBins,postBins,slice.heatloss_delta_bins||{},'kW');
}

function renderProvinceSolar(slice){
  const prePct=slice.solar_pre_pct||0,postPct=slice.solar_post_pct||0;
  const medSize=slice.solar_median_kw;
  $('solar-kpis').innerHTML=`
    <div class="eui-stat"><div class="eui-val eui-pre-val">${prePct}%</div><div class="eui-lbl">Pre-retrofit<br>with solar PV</div></div>
    <div class="eui-arrow-big">→</div>
    <div class="eui-stat"><div class="eui-val eui-post-val">${postPct}%</div><div class="eui-lbl">Post-retrofit<br>with solar PV</div></div>
    ${medSize?`<div style="margin-left:auto;text-align:right"><div class="eui-saving" style="color:var(--amber)">${medSize.toFixed(1)}</div><div style="font-size:12px;color:var(--muted)">median kW among adopters</div></div>`:''}`;
}

function renderProvinceWaterfall(slice){
  // slice.waterfall ships pre-computed per-home MEANS (not totals — the raw
  // rows aren't shipped to the browser in province mode). Multiply by the
  // matched row count to approximate the group total; exact in FSA mode
  // (renderWaterfall), where raw rows are available to sum directly.
  const waterfall=(slice.waterfall||[]).filter(w=>w.fuel!=='TOTAL');
  const n=slice.row_count||0;
  const fuelLabels=waterfall.map(w=>w.fuel);
  const preVals=waterfall.map(w=>Math.round(w.pre*n));
  const postVals=waterfall.map(w=>Math.round(w.post*n));
  drawFuelBreakdown(fuelLabels,preVals,postVals);
}

function renderProvinceKPI(slice){
  const kpis=slice.insulation_kpis||[];
  let html=kpis.map(k=>{
    const d=k.post-k.pre,imp=k.higher_is_better?d>0:d<0;
    if(k.unit==='RSI'){
      const pR=k.pre*RSI_TO_R,qR=k.post*RSI_TO_R,dR=d*RSI_TO_R;
      return `<div class="kpi-item">
        <div class="kpi-name">${k.label}</div>
        <div class="kpi-values"><div class="kpi-pre">${pR.toFixed(1)}</div><div class="kpi-arrow">→</div><div class="kpi-post">${qR.toFixed(1)}</div></div>
        <div class="kpi-unit">R-value <span class="kpi-rsi cap-advanced">(${k.pre.toFixed(1)} → ${k.post.toFixed(1)} RSI)</span></div>
        <div class="kpi-delta ${Math.abs(dR)<0.05?'flat':imp?'good':'bad'}">${Math.abs(dR)<0.05?'no change':`${dR>=0?'+':''}${dR.toFixed(1)} R ${imp?'▲ improved':'▼ declined'}`}</div>
      </div>`;
    }
    return `<div class="kpi-item">
      <div class="kpi-name">${k.label}</div>
      <div class="kpi-values"><div class="kpi-pre">${k.pre.toFixed(1)}</div><div class="kpi-arrow">→</div><div class="kpi-post">${k.post.toFixed(1)}</div></div>
      <div class="kpi-unit"><span class="cap-simple">air changes per hour (ACH50)</span><span class="cap-advanced">${k.unit}</span></div>
      <div class="kpi-delta ${Math.abs(d)<0.05?'flat':imp?'good':'bad'}">${Math.abs(d)<0.05?'no change':`${d>=0?'+':''}${d.toFixed(1)} ${k.unit} ${imp?'▲ improved':'▼ declined'}`}</div>
    </div>`;
  }).join('');
  const n=slice.row_count||0,fs=slice.fuel_switch_count||0;
  const fsPct=n?Math.round(fs/n*100):0;
  html+=`<div class="kpi-item">
    <div class="kpi-name">Fuel switching</div>
    <div class="kpi-values"><div class="kpi-pct">${fsPct}%</div></div>
    <div class="kpi-unit">of <span class="cap-simple">homes shown</span><span class="cap-advanced">matched homes</span></div>
  </div>`;
  $('kpi-grid').innerHTML=html;
}

// The precomputed bins arrive fine-grained in RSI units (0.25–0.5 RSI per
// bin, matching precompute_province_stats.py). For R-value measures we
// convert each bin's start value to R and re-bucket into coarser, rounder
// R-value steps; for air leakage (toR=false) this just re-buckets to a
// coarser ACH50 step. Re-bucketing by summing source bins is valid since
// we only ever widen bins here, never split them.
function provinceMeasureBins(histData,maxVal,step,toR){
  function rebucket(bins){
    const out={};
    Object.entries(bins||{}).forEach(([k,v])=>{
      const dv=toR?Number(k)*RSI_TO_R:Number(k);
      if(dv>maxVal)return;
      const bucket=Math.floor(dv/step)*step;
      out[bucket]=(out[bucket]||0)+v;
    });
    return out;
  }
  return{
    preBins:rebucket(histData.pre_bins),
    postBins:rebucket(histData.post_bins),
    deltaBins:rebucket(histData.delta_bins)
  };
}

function renderProvinceInsulDist(slice){
  const ih=slice.insulation_histograms||{};
  if(ih.roof){const b=provinceMeasureBins(ih.roof,80,2,true);drawComboChart('roof-chart','roof',b.preBins,b.postBins,b.deltaBins,'R-value');}
  if(ih.wall){const b=provinceMeasureBins(ih.wall,40,2,true);drawComboChart('wall-chart','wall',b.preBins,b.postBins,b.deltaBins,'R-value');}
  if(ih.fnd){const b=provinceMeasureBins(ih.fnd,35,2,true);drawComboChart('fnd-chart','fnd',b.preBins,b.postBins,b.deltaBins,'R-value');}
  if(ih.air){const b=provinceMeasureBins(ih.air,20,1,false);drawComboChart('air-chart','air',b.preBins,b.postBins,b.deltaBins,'ACH50');}
}

function renderProvinceMeasures(slice){
  const n=slice.row_count||0;
  const measures=slice.measures||[];
  if(!n){$('measures-list').innerHTML='<div class="state-msg"><strong>No matches</strong></div>';return;}
  $('measures-list').innerHTML=[...measures].sort((a,b)=>b.pct-a.pct).map(m=>{
    const def=MEASURES.find(x=>x.key===m.key);
    return `<div class="measure-row"><div class="measure-label">${m.label}<button type="button" class="info-btn" aria-label="How is ${m.label} counted?" data-info="${def?.tip||''}">?</button></div><div class="bar-track"><div class="bar-fill" style="width:${m.pct}%;background:${def?.color||PAL.tick}"></div></div><div class="bar-pct">${m.pct}%</div></div>`;
  }).join('');
}

function renderProvinceHist(slice){
  dc('hist');
  const bins=slice.savings_pct_bins||{};
  const keys=Object.keys(bins).map(Number).sort((a,b)=>a-b);
  if(!keys.length)return;
  charts['hist']=new Chart($('hist-chart').getContext('2d'),{
    type:'bar',
    data:{labels:keys.map(k=>`${k}%`),datasets:[{
      data:keys.map(k=>bins[k]),
      backgroundColor:keys.map(k=>k<0?al(PAL.neg,'B3'):al(PAL.pos,'B3')),
      borderColor:keys.map(k=>k<0?PAL.neg:PAL.pos),
      borderWidth:0.5,borderRadius:0,barPercentage:1.0,categoryPercentage:1.0
    }]},
    options:{responsive:true,maintainAspectRatio:false,
      plugins:{legend:{display:false},tooltip:{callbacks:{title:i=>`${i[0].label} saving`,label:i=>`${i.raw.toLocaleString()} homes`}}},
      scales:{
        x:{title:{display:true,text:'Energy saving %',font:{size:11},color:PAL.axis},
          ticks:{font:{size:9},color:PAL.tick,maxTicksLimit:30,
            callback:function(v,i){const l=keys[i];return l%10===0?`${l}%`:''}},
          grid:{display:false}},
        y:{title:{display:true,text:'Homes',font:{size:11},color:PAL.axis},ticks:{font:{size:11},color:PAL.tick},grid:{color:PAL.track}}
      }
    }
  });
}

// (Table card is hidden entirely in province mode — see renderProvince() —
// since no row-level data is shipped province-wide.)

// ── EUI gradient bar for table ────────────────────────────────────
// `big` renders the same bar at ~2x for the expanded detail panel, where it
// sits in a column beside the envelope and heat-loss charts and needs the
// height to match them. Table rows keep the compact default.
function makeEUIBar(preEUI,postEUI,medPre,medPost,big){
  const MAX=750,W=big?250:120,H=big?44:18,MH=big?30:10;
  const R=big?8:4,FS=big?11:8;
  if(!preEUI&&!postEUI)return '—';
  const px=v=>Math.min(W,Math.max(0,Math.round(v/MAX*W)));
  const preX=preEUI?px(preEUI):null;
  const postX=postEUI?px(postEUI):null;
  const medPreX=medPre?px(medPre):null;
  const medPostX=medPost?px(medPost):null;
  // Use shared #eui-grad defined once in static HTML — no random IDs needed
  let s=`<svg viewBox="0 0 ${W} ${H+14}" width="${W}" height="${H+14}" style="display:block;overflow:visible">
    <rect x="0" y="4" width="${W}" height="${MH}" fill="url(#eui-grad)" rx="3" opacity="0.25"/>`;
  if(medPreX!==null)s+=`<line x1="${medPreX}" y1="2" x2="${medPreX}" y2="${4+MH+2}" stroke="${PAL.primary}" stroke-width="1" stroke-dasharray="2,1" opacity="0.5"/>`;
  if(medPostX!==null)s+=`<line x1="${medPostX}" y1="2" x2="${medPostX}" y2="${4+MH+2}" stroke="${PAL.pos}" stroke-width="1" stroke-dasharray="2,1" opacity="0.5"/>`;
  if(preX!==null)s+=`<circle cx="${preX}" cy="${4+MH/2}" r="${R}" fill="${PAL.primary}" stroke="${PAL.card}" stroke-width="1.5"><title>Pre: ${preEUI} kWh/m²</title></circle>`;
  if(postX!==null)s+=`<circle cx="${postX}" cy="${4+MH/2}" r="${R}" fill="${PAL.pos}" stroke="${PAL.card}" stroke-width="1.5"><title>Post: ${postEUI} kWh/m²</title></circle>`;
  if(preX!==null)s+=`<text x="${preX}" y="${4+MH+FS+3}" text-anchor="middle" font-size="${FS}" fill="${PAL.primary}" font-family="Inter,sans-serif">${preEUI}</text>`;
  if(postX!==null)s+=`<text x="${postX}" y="${4+MH+FS+3}" text-anchor="middle" font-size="${FS}" fill="${PAL.pos}" font-family="Inter,sans-serif">${postEUI}</text>`;
  s+=`</svg>`;
  return s;
}

// ── Table ─────────────────────────────────────────────────────────
function sortBy(key){
  SORT=key;
  document.querySelectorAll('.sort-btn').forEach(b=>b.classList.remove('active'));
  $('sb-'+key).classList.add('active');
  renderTable();
}

function makeInlineSVG(r){
  // ── EUI, promoted above the envelope measures box ──
  const preEUI=num(r.Pre_TotalEnergy)&&num(r.FloorArea)?Math.round(num(r.Pre_TotalEnergy)/num(r.FloorArea)):null;
  const postEUI=num(r.Post_TotalEnergy)&&num(r.FloorArea)?Math.round(num(r.Post_TotalEnergy)/num(r.FloorArea)):null;
  // ── Panel layout: measure chips as a full-width banner, then EUI /
  // envelope / heat loss side by side in one row, then the HVAC table at
  // full width underneath. ──
  let html='';

  // ── Envelope measures (R-value bars) + which measures were applied ──
  const KPIs=[
    {label:'Roof',pre:num(r.Pre_RoofInsulation),post:num(r.Post_RoofInsulation),max:12,hi:true},
    {label:'Wall',pre:num(r.Pre_WallInsulation),post:num(r.Post_WallInsulation),max:6,hi:true},
    {label:'Foundation',pre:num(r.Pre_FoundationInsulation),post:num(r.Post_FoundationInsulation),max:4,hi:true},
    {label:'Air ACH50',pre:num(r.Pre_AirLeakage),post:num(r.Post_AirLeakage),max:20,hi:false,noR:true},
  ];
  const barW=160,barH=12,gap=28,startX=78;
  const svgH=KPIs.length*gap+10;

  // Measure chips, promoted out of the envelope column into a full-width
  // banner at the top — they describe the whole home, not just the envelope.
  const pills=MEASURES.filter(m=>flag(r,m.key))
    .map(m=>`<span class="measure-chip" style="background:${m.color}">${m.label}</span>`).join('');
  html+=`<div class="detail-measures">
    <div class="detail-h">Measures applied</div>
    <div class="measure-chips">${pills||'<span style="font-size:11px;color:var(--light)">No measures flagged</span>'}</div>
  </div>`;

  // Three charts side by side; auto-fit collapses them to fewer columns on
  // narrow screens rather than squeezing all three.
  html+=`<div class="detail-charts">
  <div style="min-width:0">
    <div class="detail-h">Energy use intensity (EUI), kWh/m²</div>
    ${makeEUIBar(preEUI,postEUI,window._euiMedianPre,window._euiMedianPost,true)}
  </div>
  <div style="min-width:0">
    <div class="detail-h">Envelope measures</div>
    <svg viewBox="0 0 ${startX+barW+70} ${svgH}" style="width:${startX+barW+70}px;max-width:100%;display:block">`;
  KPIs.forEach((k,i)=>{
    const y=i*gap+8;
    html+=`<text x="${startX-6}" y="${y+barH/2+4}" text-anchor="end" font-size="10" fill="${PAL.axis}" font-family="Inter,sans-serif">${k.label}${k.noR?'':' R'}</text>`;
    const preW=k.pre?Math.max(2,Math.min(barW,k.pre/k.max*barW)):0;
    const postW=k.post?Math.max(2,Math.min(barW,k.post/k.max*barW)):0;
    html+=`<rect x="${startX}" y="${y}" width="${barW}" height="${barH}" fill="${PAL.track}" rx="3"/>`;
    html+=`<rect x="${startX}" y="${y}" width="${preW}" height="${barH/2}" fill="${al(PAL.primary,'99')}" rx="2"/>`;
    html+=`<rect x="${startX}" y="${y+barH/2}" width="${postW}" height="${barH/2}" fill="${al(PAL.pos,'99')}" rx="2"/>`;
    const pStr=k.pre?(k.noR?k.pre.toFixed(1):(k.pre*RSI_TO_R).toFixed(0)):'—';
    const qStr=k.post?(k.noR?k.post.toFixed(1):(k.post*RSI_TO_R).toFixed(0)):'—';
    const imp=k.hi?(k.post||0)>(k.pre||0):(k.post||0)<(k.pre||0);
    html+=`<text x="${startX+barW+6}" y="${y+barH/2+4}" font-size="10" fill="${PAL.axis}" font-family="Inter,sans-serif">${pStr}→<tspan fill="${imp?PAL.pos:PAL.neg}">${qStr}</tspan></text>`;
  });
  html+=`</svg>
    <div style="display:flex;gap:12px;margin-top:4px">
      <span style="display:inline-flex;align-items:center;gap:4px;font-size:11px;color:var(--muted)"><span style="display:inline-block;width:16px;height:4px;background:${al(PAL.primary,'99')};border-radius:2px"></span>Pre</span>
      <span style="display:inline-flex;align-items:center;gap:4px;font-size:11px;color:var(--muted)"><span style="display:inline-block;width:16px;height:4px;background:${al(PAL.pos,'99')};border-radius:2px"></span>Post</span>
    </div>
  </div>`;

  // ── HVAC & energy: separate Measure / Pre / Post / Savings columns.
  // A changed value gets a small round arrow badge (.td-arrow) straddling
  // the Pre/Post border instead of an inline arrow inside a merged cell —
  // visible at a glance without reading both cells.
  const th=t=>`<th style="text-align:left;font-size:10px;font-weight:500;text-transform:uppercase;letter-spacing:.04em;color:var(--light);padding:0 10px 4px 0">${t}</th>`;
  const changeArrow=()=>`<span class="td-arrow" style="background:${PAL.secondary}">→</span>`;
  function textRow(lbl,pre,post){
    const changed=!!(pre&&post&&pre!==post);
    return `<tr>
      <td style="padding:3px 10px 3px 0;color:var(--muted);white-space:nowrap">${lbl}</td>
      <td style="padding:3px 10px 3px 0;color:var(--text)">${pre||'—'}</td>
      <td style="padding:3px 10px 3px 12px;color:var(--text);position:relative">${changed?changeArrow():''}${post||'—'}</td>
      <td style="padding:3px 0;color:${changed?PAL.secondary:'var(--light)'}">${changed?'Changed':'—'}</td>
    </tr>`;
  }
  // AHRI-certificate-verified heat pump capacity/efficiency (join_hp_capacity.py).
  // Post-only, and only present when the AHRI reference resolved — most
  // homes with a heat pump but no row here simply lack a usable AHRI number.
  // colspan=3 (Pre + Post + Savings) since this post-only figure doesn't
  // belong under any single one of those columns.
  function hpCertRow(r){
    const cap47=num(r.Post_HPCapacity47),cap5=num(r.Post_HPCapacity5),hspf=num(r.Post_HPHSPF2);
    if(cap47===null&&cap5===null&&hspf===null)return'';
    const parts=[];
    if(cap47!==null)parts.push(`${cap47.toFixed(1)} kW @ 47°F`);
    if(cap5!==null)parts.push(`${cap5.toFixed(1)} kW @ 5°F`);
    if(hspf!==null)parts.push(`HSPF2 ${hspf.toFixed(1)}`);
    const hl=num(r.Post_HeatLoss);
    const sizing=(cap47!==null&&hl!==null&&hl>0)?` · sized to ${Math.round(cap47/hl*100)}% of design heat loss`:'';
    return `<tr>
      <td style="padding:3px 10px 3px 0;color:var(--muted);white-space:nowrap">&nbsp;&nbsp;· Cert. capacity</td>
      <td colspan="3" style="padding:3px 0;color:var(--text)">${parts.join(' · ')}${sizing}</td>
    </tr>`;
  }
  function numRow(lbl,pre,post,unit,higherIsBetter,decimals){
    if(pre===null&&post===null)return `<tr><td style="padding:3px 10px 3px 0;color:var(--muted);white-space:nowrap">${lbl}</td><td colspan="3" style="padding:3px 0;color:var(--light)">—</td></tr>`;
    const d=pre!==null&&post!==null?(higherIsBetter?post-pre:pre-post):null;
    const good=d!==null&&d>=0;
    const changed=d!==null&&Math.abs(d)>1e-9;
    const fmt=v=>v===null?'—':(decimals?v.toFixed(decimals):Math.round(v).toLocaleString());
    const unitStr=unit?` ${unit}`:'';
    return `<tr>
      <td style="padding:3px 10px 3px 0;color:var(--muted);white-space:nowrap">${lbl}</td>
      <td style="padding:3px 10px 3px 0;color:var(--text);white-space:nowrap">${pre!==null?fmt(pre)+unitStr:'—'}</td>
      <td style="padding:3px 10px 3px 12px;color:var(--text);white-space:nowrap;position:relative">${changed?changeArrow():''}${post!==null?fmt(post)+unitStr:'—'}</td>
      <td style="padding:3px 0;color:${d===null?'var(--light)':good?PAL.pos:PAL.neg};white-space:nowrap">${d===null?'—':`${d>=0?'+':''}${fmt(d)}${unitStr}`}</td>
    </tr>`;
  }
  // Windows: one row per element (glazing, coating, gas fill, spacer, window
  // type, frame material) — always shown, so the Pre/Post cells hold a short
  // per-attribute value instead of one long combined description. The change
  // arrow only appears on rows where that specific attribute differs (e.g.
  // "Double/double with 1 coat glazing" in both columns gets no arrow).
  const wPreCode=r.Pre_WindowCode,wPostCode=r.Post_WindowCode;
  const wp=decodeWindowParts(wPreCode),wq=decodeWindowParts(wPostCode);
  let windowRows;
  if(wp&&wq){
    windowRows=WINDOW_ATTRS.map(({key,label})=>{
      const changed=wp[key]!==wq[key];
      return `<tr>
      <td style="padding:3px 10px 3px 0;color:var(--muted);white-space:nowrap">Window – ${label}</td>
      <td style="padding:3px 10px 3px 0;color:var(--text)">${wp[key]}</td>
      <td style="padding:3px 10px 3px 12px;color:var(--text);position:relative">${changed?changeArrow():''}${wq[key]}</td>
      <td style="padding:3px 0;color:${changed?PAL.secondary:'var(--light)'}">${changed?'Changed':'—'}</td>
    </tr>`;
    }).join('');
  }else{
    // Codes didn't decode cleanly (non-standard/user-defined code, or the
    // lookup table hasn't loaded) — fall back to the raw/main decoded string.
    const wPre=wPreCode?decodeWindow(wPreCode).main:null;
    const wPost=wPostCode?decodeWindow(wPostCode).main:null;
    const windowChanged=!!(wPre&&wPost&&wPre!==wPost);
    windowRows=`<tr>
    <td style="padding:3px 10px 3px 0;color:var(--muted);white-space:nowrap;vertical-align:top">Windows</td>
    <td style="padding:3px 10px 3px 0;color:var(--text)">${wPre||'—'}</td>
    <td style="padding:3px 10px 3px 12px;color:var(--text);position:relative">${windowChanged?changeArrow():''}${wPost||'—'}</td>
    <td style="padding:3px 0;color:${windowChanged?PAL.secondary:'var(--light)'}">${windowChanged?'Changed':'—'}</td>
  </tr>`;
  }
  // Whole-house consumption by fuel (all end uses — heating, DHW,
  // appliances). Only fuels the home actually used pre or post are listed.
  const FUEL_FIELDS=[
    ['Electricity','Electricity'],['Natural gas','NaturalGas'],['Oil','Oil'],
    ['Propane','Propane'],['Wood','Wood']
  ];
  const fuelBreakdownRows=FUEL_FIELDS.map(([label,key])=>{
    const pre=num(r['Pre_'+key]),post=num(r['Post_'+key]);
    if(!pre&&!post)return'';
    return numRow(`&nbsp;&nbsp;· ${label}`,pre,post,'kWh',false,0);
  }).join('');
  // Heating-only consumption by fuel (subset of the above — just the
  // portion HOT2000 attributes to space heating, not DHW/appliances).
  const heatFuelVals=FUEL_FIELDS.map(([,key])=>({pre:num(r['Pre_Heat'+key]),post:num(r['Post_Heat'+key])}));
  const heatPreTotal=heatFuelVals.some(v=>v.pre!=null)?heatFuelVals.reduce((s,v)=>s+(v.pre||0),0):null;
  const heatPostTotal=heatFuelVals.some(v=>v.post!=null)?heatFuelVals.reduce((s,v)=>s+(v.post||0),0):null;
  const heatFuelBreakdownRows=FUEL_FIELDS.map(([label],i)=>{
    const{pre,post}=heatFuelVals[i];
    if(!pre&&!post)return'';
    return numRow(`&nbsp;&nbsp;· ${label}`,pre,post,'kWh',false,0);
  }).join('');
  // Annual heat loss by building component — same pre/post-bar-per-category
  // pattern as "Envelope measures" above (one shared track per row, split
  // top/bottom into a pre segment and a post segment), rather than a
  // separate flow diagram, so the two panels read the same way. All six
  // components share one scale (not each its own, unlike the R-value KPIs
  // above) so bar length stays a fair comparison of which component loses
  // the most heat. This is the ANNUAL loss (EGHHL*), not the peak/design-day
  // "Design heat loss" row in the HVAC table below (EGHDESHTLOSS) — the two
  // aren't the same quantity, hence the separate chart rather than a shared row.
  const HL_COMPONENTS=[
    {key:'HeatLossWindowDoor',label:'Windows/doors'},
    {key:'HeatLossWall',label:'Walls'},
    {key:'HeatLossFoundation',label:'Foundation'},
    {key:'HeatLossRoof',label:'Roof'},
    {key:'HeatLossFloor',label:'Exposed floor'},
    {key:'HeatLossAir',label:'Air leakage'},
  ];
  const hlPre=HL_COMPONENTS.map(c=>num(r['Pre_'+c.key]));
  const hlPost=HL_COMPONENTS.map(c=>num(r['Post_'+c.key]));
  let heatLossBlock='';
  if(hlPre.some(v=>v!==null)||hlPost.some(v=>v!==null)){
    const hlMax=Math.max(...hlPre.map(v=>v||0),...hlPost.map(v=>v||0),1);
    const hlBarW=160,hlBarH=12,hlGap=28,hlStartX=94;
    const hlSvgH=HL_COMPONENTS.length*hlGap+10;
    let hlSvg=`<svg viewBox="0 0 ${hlStartX+hlBarW+70} ${hlSvgH}" style="width:${hlStartX+hlBarW+70}px;max-width:100%;display:block">`;
    HL_COMPONENTS.forEach((c,i)=>{
      const y=i*hlGap+8;
      const pre=hlPre[i],post=hlPost[i];
      hlSvg+=`<text x="${hlStartX-6}" y="${y+hlBarH/2+4}" text-anchor="end" font-size="10" fill="${PAL.axis}" font-family="Inter,sans-serif">${c.label}</text>`;
      const preW=pre?Math.max(2,Math.min(hlBarW,pre/hlMax*hlBarW)):0;
      const postW=post?Math.max(2,Math.min(hlBarW,post/hlMax*hlBarW)):0;
      hlSvg+=`<rect x="${hlStartX}" y="${y}" width="${hlBarW}" height="${hlBarH}" fill="${PAL.track}" rx="3"/>`;
      hlSvg+=`<rect x="${hlStartX}" y="${y}" width="${preW}" height="${hlBarH/2}" fill="${al(PAL.primary,'99')}" rx="2"/>`;
      hlSvg+=`<rect x="${hlStartX}" y="${y+hlBarH/2}" width="${postW}" height="${hlBarH/2}" fill="${al(PAL.pos,'99')}" rx="2"/>`;
      const pStr=pre!==null?Math.round(pre).toLocaleString():'—';
      const qStr=post!==null?Math.round(post).toLocaleString():'—';
      const imp=(post||0)<(pre||0); // lower heat loss is the improvement
      hlSvg+=`<text x="${hlStartX+hlBarW+6}" y="${y+hlBarH/2+4}" font-size="10" fill="${PAL.axis}" font-family="Inter,sans-serif">${pStr}→<tspan fill="${imp?PAL.pos:PAL.neg}">${qStr}</tspan></text>`;
    });
    hlSvg+=`</svg>`;
    heatLossBlock=`<div style="min-width:0">
      <div class="detail-h">Annual heat loss by component, kWh/yr</div>
      ${hlSvg}
      <div style="display:flex;gap:12px;margin-top:4px">
        <span style="display:inline-flex;align-items:center;gap:4px;font-size:11px;color:var(--muted)"><span style="display:inline-block;width:16px;height:4px;background:${al(PAL.primary,'99')};border-radius:2px"></span>Pre</span>
        <span style="display:inline-flex;align-items:center;gap:4px;font-size:11px;color:var(--muted)"><span style="display:inline-block;width:16px;height:4px;background:${al(PAL.pos,'99')};border-radius:2px"></span>Post</span>
      </div>
    </div>`;
  }
  const py=r.Pre_Year?parseInt(r.Pre_Year):null,qy=r.Post_Year?parseInt(r.Post_Year):null;
  const yearGap=(py&&qy)?qy-py:null;
  const auditYearRow=`<tr>
    <td style="padding:3px 10px 3px 0;color:var(--muted);white-space:nowrap">Audit year</td>
    <td style="padding:3px 10px 3px 0;color:var(--text)">${r.Pre_Year||'—'}</td>
    <td style="padding:3px 10px 3px 12px;color:var(--text);position:relative">${yearGap!==null?changeArrow():''}${r.Post_Year||'—'}</td>
    <td style="padding:3px 0;color:var(--light)">${yearGap!==null?`${yearGap} yr apart`:'—'}</td>
  </tr>`;

  // Third chart column, then close the charts row and give the table the
  // full panel width.
  html+=heatLossBlock;
  html+=`</div>
  <div style="min-width:0">
    <div class="detail-h">HVAC &amp; energy</div>
    <div style="overflow-x:auto"><table style="font-size:12px;border-collapse:collapse;width:100%">
      <colgroup><col style="width:18%"><col style="width:26%"><col style="width:28%"><col style="width:28%"></colgroup>
      <thead><tr>${th('Measure')}${th('Pre')}${th('Post')}${th('Savings')}</tr></thead>
      <tbody>
        ${auditYearRow}
        ${textRow(hasHeatPump(r)?'Backup fuel':'Heating fuel',r.Pre_HeatFuel,r.Post_HeatFuel)}
        ${textRow(hasHeatPump(r)?'Backup type':'Heating type',r.Pre_HeatType,r.Post_HeatType)}
        ${textRow('Heat pump',r.Pre_HPType,r.Post_HPType)}
        ${hpCertRow(r)}
        ${textRow('Ventilation',r.Pre_VentType,r.Post_VentType)}
        ${windowRows}
        ${numRow('Energy',num(r.Pre_TotalEnergy),num(r.Post_TotalEnergy),'kWh',false,0)}
        ${fuelBreakdownRows}
        ${numRow('Heating energy',heatPreTotal,heatPostTotal,'kWh',false,0)}
        ${heatFuelBreakdownRows}
        ${numRow('GHG (as reported)',num(r.Pre_GHG),num(r.Post_GHG),'tCO2e/yr',false,1)}
        ${numRow('Design heat loss',num(r.Pre_HeatLoss),num(r.Post_HeatLoss),'kW',false,1)}
        ${numRow('Solar PV',num(r.Pre_SolarPV),num(r.Post_SolarPV),'kW',true,1)}
      </tbody>
    </table></div>
  </div>`;

  // ── Retrofit cost estimate (proof of concept), per-measure — only if this
  // home has a priced row in the retrofit_costs_json companion tree. ──
  const retroRow=retroRowFor(r.HOUSEID);
  if(retroRow){
    const bandKey=['l','m','h'][RETRO_BAND];
    const mRows=RETRO_MEASURES.map(m=>{
      const v=retroVal(retroRow,`${m.abbr}_${bandKey}`);
      return v!=null?`<tr><td style="padding:3px 10px 3px 0;color:var(--muted)">${m.label}</td><td style="padding:3px 0;color:${v<0?'var(--pos)':'var(--text)'}">${fmtMoney(Math.round(v))}</td></tr>`:'';
    }).join('');
    const tot=retroVal(retroRow,`Tot_${bandKey}`);
    const pbY=retroVal(retroRow,'pbY');
    const ac=RETRO_DICT&&RETRO_DICT.ac[String(retroVal(retroRow,'ac'))];
    const bh=RETRO_DICT&&RETRO_DICT.bh[String(retroVal(retroRow,'bh'))];
    const bhs=retroVal(retroRow,'bhs');
    html+=`<div class="detail-charts" style="margin-top:.8rem">
      <div style="min-width:0">
        <div class="detail-h">Estimated retrofit cost <span class="badge badge-medium" style="margin-left:4px">POC</span></div>
        <table style="font-size:12px;border-collapse:collapse">${mRows}
          <tr><td style="padding:5px 10px 3px 0;color:var(--text);font-weight:600;border-top:1px solid var(--border)">Total</td><td style="padding:5px 0 3px;font-weight:600;border-top:1px solid var(--border);color:${tot<0?'var(--pos)':'var(--text)'}">${tot!=null?fmtMoney(Math.round(tot)):'—'}</td></tr>
        </table>
      </div>
      <div style="min-width:0">
        <div class="detail-h">Payback &amp; classification</div>
        <table style="font-size:12px;border-collapse:collapse">
          <tr><td style="padding:3px 10px 3px 0;color:var(--muted)">Payback</td><td style="padding:3px 0;color:var(--text)">${pbY!=null?pbY.toFixed(1)+' years':'—'}</td></tr>
          ${ac?`<tr><td style="padding:3px 10px 3px 0;color:var(--muted)">ASHP class</td><td style="padding:3px 0;color:var(--text)">${ac}</td></tr>`:''}
          ${bh?`<tr><td style="padding:3px 10px 3px 0;color:var(--muted)">BAU heating replaced</td><td style="padding:3px 0;color:var(--text)">${bh}${bhs===2?' <span style="color:var(--light);font-size:11px">(assumed)</span>':''}</td></tr>`:''}
        </table>
      </div>
    </div>`;
  }

  return html;
}

function renderTable(){
  const MAX=100;
  let rows=[...FILTERED];
  if(SORT==='saving')rows.sort((a,b)=>(num(b.EnergySavingPct)||0)-(num(a.EnergySavingPct)||0));
  else if(SORT==='year')rows.sort((a,b)=>parseInt(a.YearBuilt||9999)-parseInt(b.YearBuilt||9999));
  else if(SORT==='area')rows.sort((a,b)=>(num(b.FloorArea)||0)-(num(a.FloorArea)||0));
  const shown=rows.slice(0,MAX);
  const tbody=$('tbl-body');
  const hasRetro=RETRO_COST_MAP.size>0;
  const colspan=hasRetro?10:8;
  if(!shown.length){
    tbody.innerHTML=`<tr><td colspan="${colspan}"><div class="state-msg"><strong>No matching retrofits</strong></div></td></tr>`;
    $('tbl-footer').textContent='';return;
  }
  const bandKey=['l','m','h'][RETRO_BAND];
  tbody.innerHTML=shown.map((r,idx)=>{
    const sv=num(r.EnergySavingPct);
    const svCell=sv!==null?`<span class="${sv>=0?'saving-pos':'saving-neg'}">${fmtPct(sv)}</span>`:'—';
    let badge='';
    if(flag(r,'Deep_Retrofit'))badge='<span class="badge badge-deep">Deep</span>';
    else if(flag(r,'Medium_Retrofit'))badge='<span class="badge badge-medium">Medium</span>';
    else if(flag(r,'Shallow_Retrofit'))badge='<span class="badge badge-shallow">Shallow</span>';
    else if(sv!==null&&sv<0)badge='<span class="badge badge-neg">Increased</span>';
    const fuelCell=flag(r,'FuelSwitch')
      ?`<span class="fuel-chip">${r.Pre_HeatFuel||'?'}</span><span class="fuel-arrow"> → </span><span class="fuel-chip">${r.Post_HeatFuel||'?'}</span>`
      :`<span class="fuel-chip">${r.Pre_HeatFuel||'?'}</span>`;
    const preEUI=num(r.Pre_TotalEnergy)&&num(r.FloorArea)?Math.round(num(r.Pre_TotalEnergy)/num(r.FloorArea)):null;
    const postEUI=num(r.Post_TotalEnergy)&&num(r.FloorArea)?Math.round(num(r.Post_TotalEnergy)/num(r.FloorArea)):null;
    let retroCells='';
    if(hasRetro){
      const rr=retroRowFor(r.HOUSEID);
      const tot=rr?retroVal(rr,`Tot_${bandKey}`):null;
      const pbY=rr?retroVal(rr,'pbY'):null;
      retroCells=`<td>${tot!=null?fmtMoney(Math.round(tot)):'—'}</td><td>${pbY!=null?pbY.toFixed(1)+'y':'—'}</td>`;
    }
    return `<tr class="data-row" onclick="toggleRow(${idx})" onkeydown="if(event.key==='Enter'||event.key===' '){event.preventDefault();toggleRow(${idx});}" tabindex="0" role="button" aria-expanded="false" id="row-${idx}">
      <td>${r.FSA||'—'}</td><td>${r.BldgType||'—'}</td><td>${r.YearBuilt||'—'}</td>
      <td>${r.FloorArea?Math.round(parseFloat(r.FloorArea)):'—'}</td>
      <td>${makeEUIBar(preEUI,postEUI,window._euiMedianPre,window._euiMedianPost)}</td>
      <td>${fuelCell}</td><td>${svCell}</td><td>${badge}</td>${retroCells}
    </tr>
    <tr class="detail-row" id="detail-${idx}"><td colspan="${colspan}"><div class="detail-inner" id="detail-inner-${idx}"></div></td></tr>`;
  }).join('');
  window._tableRows=shown;
  $('tbl-footer').textContent=rows.length>MAX
    ?`Showing top ${MAX} of ${rows.length.toLocaleString()} matching retrofits`
    :`${rows.length.toLocaleString()} matching retrofits`;
}

function toggleRow(idx){
  const dataRow=$(`row-${idx}`),detailRow=$(`detail-${idx}`),inner=$(`detail-inner-${idx}`);
  const isOpen=dataRow.classList.contains('open');
  document.querySelectorAll('.data-row.open').forEach(r=>{r.classList.remove('open');r.setAttribute('aria-expanded','false');});
  document.querySelectorAll('.detail-row.open').forEach(r=>r.classList.remove('open'));
  if(!isOpen){
    dataRow.classList.add('open');detailRow.classList.add('open');
    dataRow.setAttribute('aria-expanded','true');
    if(!inner.dataset.rendered){
      inner.innerHTML=makeInlineSVG(window._tableRows[idx]);
      inner.dataset.rendered='1';
    }
  }
}

// ── FSA map — visual companion to the "Your FSA" dropdown ──────────
// Polygons come from StatCan's 2021 FSA cartographic boundary file,
// reprojected to plain lon/lat and simplified with mapshaper (see
// Python/build_fsa_geometry.py's docstring for why — no GDAL/mapshaper
// install on the data-prep machine, so this used the StatCan source +
// mapshaper.org directly instead). Some newer FSAs (created/split after
// the 2021 census) have no polygon and simply won't appear on the map —
// they're still selectable via the dropdown as before.
const GEO_JSON_BASE=`${BASE_URL}geo_json/`;
const GEO_CACHE=new Map();
function fetchGeoJSON(prov){
  if(GEO_CACHE.has(prov))return Promise.resolve(GEO_CACHE.get(prov));
  return fetchJSON(`${GEO_JSON_BASE}${prov}.json`).then(d=>{GEO_CACHE.set(prov,d);return d;});
}

// Standard slippy-map (Web Mercator) tile pixel projection — needed so the
// FSA polygons line up with real OpenStreetMap raster tiles drawn behind
// them. lon2x/lat2y give the pixel position of a lon/lat at a given integer
// zoom level, in the same 256px/tile grid OSM tile servers use.
function lon2x(lon,z){return(lon+180)/360*Math.pow(2,z)*256;}
function lat2y(lat,z){
  const rad=lat*Math.PI/180;
  return(1-Math.log(Math.tan(rad)+1/Math.cos(rad))/Math.PI)/2*Math.pow(2,z)*256;
}
// Inverse of lon2x/lat2y — needed to turn a feature's pixel-space bbox (in
// MAP_STATE's coordinate system) back into lon/lat so a sharper zoom level
// can be picked and fetched just for that bbox (see loadSharpTiles).
function x2lon(x,z){return x/(256*Math.pow(2,z))*360-180;}
function y2lat(y,z){
  const n=Math.PI-2*Math.PI*y/(256*Math.pow(2,z));
  return 180/Math.PI*Math.atan((Math.exp(n)-Math.exp(-n))/2);
}
// Highest integer zoom whose bbox still fits inside targetW x targetH, so
// the initial view is as sharp as possible without fetching tiles outside
// the visible area.
function pickTileZoom(minLon,maxLon,minLat,maxLat,targetW,targetH){
  for(let z=15;z>=2;z--){
    const w=lon2x(maxLon,z)-lon2x(minLon,z);
    const h=lat2y(minLat,z)-lat2y(maxLat,z);
    if(w<=targetW&&h<=targetH)return z;
  }
  return 2;
}
// Opposite search direction from pickTileZoom: smallest zoom whose bbox is
// already AT LEAST targetW x targetH, so a small FSA's basemap tiles are
// genuinely higher-resolution rather than just the province tiles stretched
// via viewBox zoom (which is what made zoomed-in FSAs look blurry).
function pickSharperZoom(minLon,maxLon,minLat,maxLat,targetW,targetH,maxZoom){
  for(let z=2;z<=maxZoom;z++){
    const w=lon2x(maxLon,z)-lon2x(minLon,z);
    const h=lat2y(minLat,z)-lat2y(maxLat,z);
    if(w>=targetW&&h>=targetH)return z;
  }
  return maxZoom;
}
// CARTO "light_all" basemap instead of standard OSM tiles: a near-greyscale
// style with far less visual detail, so the choropleth colours stay readable
// on top of it (the full OSM style fought the data for attention). Same
// slippy-map tile grid, so nothing else changes. Free tier requires the
// OSM + CARTO attribution kept below the map.
const TILE_URL_SUBDOMAINS=['a','b','c','d'];
function tileUrl(z,x,y){
  const sub=TILE_URL_SUBDOMAINS[(x+y)%TILE_URL_SUBDOMAINS.length];
  return`https://${sub}.basemaps.cartocdn.com/light_all/${z}/${x}/${y}.png`;
}

let MAP_STATE=null; // {prov, z, origin:[ox,oy], features:[{fsa,d,bbox}], fullViewBox, indexByFsa, tilesD}
let _mapTipEl=null;

function toggleFsaMapCard(show){
  $('fsa-map-card').style.display=show?'':'none';
}

// ── Explore-the-map toggle ──────────────────────────────────────────
// The FSA map is collapsed by default; the "Explore the map" button in the
// filter bar reveals it. The map is still built (hidden) whenever a province
// loads, so opening it is instant and no data is fetched on click.
let MAP_OPEN=false;      // is the map card currently expanded?
let MAP_AVAILABLE=false; // does the current province have a usable map?
function syncExploreBtn(){
  const btn=$('explore-btn');
  btn.classList.toggle('is-open',MAP_OPEN);
  btn.setAttribute('aria-expanded',MAP_OPEN?'true':'false');
  $('explore-btn-text').textContent=MAP_OPEN?'Hide the map':'Explore the map';
}
// Provinces with no boundary file (and "All of Canada") have no map: hide the
// button and force the card closed.
function setMapAvailable(avail){
  MAP_AVAILABLE=avail;
  $('explore-btn').style.display=avail?'':'none';
  if(!avail)MAP_OPEN=false;
  toggleFsaMapCard(avail&&MAP_OPEN);
  syncExploreBtn();
}
function toggleExploreMap(){
  if(!MAP_AVAILABLE)return;
  MAP_OPEN=!MAP_OPEN;
  toggleFsaMapCard(MAP_OPEN);
  syncExploreBtn();
  if(MAP_OPEN){
    $('fsa-map-card').scrollIntoView({behavior:'smooth',block:'nearest'});
    if(SELECTED_FSA)zoomFsaMapTo(SELECTED_FSA);
  }
}

function projectRing(ring,originX,originY,z){
  return ring.map(([lon,lat])=>[lon2x(lon,z)-originX,lat2y(lat,z)-originY]);
}

function ringsToPathD(rings){
  return rings.map(pts=>'M'+pts.map(p=>p.join(',')).join('L')+'Z').join(' ');
}

function loadFsaMap(prov,fsaIndex){
  setMapAvailable(true); // enables the Explore button; the card stays collapsed until the user opens it
  $('fsa-map-svg').innerHTML='<text x="300" y="300" text-anchor="middle" fill=PAL.tick font-size="13" font-family="Inter, sans-serif">Loading map…</text>';
  resetFsaMapZoom();
  // Census is only used here for the tooltip's population line, so don't
  // block painting 500+ polygons on that ~1.2MB fetch — paint now, then
  // patch population into indexByFsa in place once census resolves (the
  // tooltip reads indexByFsa live on hover, so no repaint is needed).
  fetchGeoJSON(prov).then(geojson=>{
    if(PROVINCE_CODE!==prov)return; // user already switched province before this resolved
    const census={};
    let minLon=Infinity,maxLon=-Infinity,minLat=Infinity,maxLat=-Infinity;
    geojson.features.forEach(ft=>{
      const polys=ft.geometry.type==='Polygon'?[ft.geometry.coordinates]:ft.geometry.coordinates;
      polys.forEach(rings=>rings.forEach(ring=>ring.forEach(([lon,lat])=>{
        if(lon<minLon)minLon=lon;if(lon>maxLon)maxLon=lon;
        if(lat<minLat)minLat=lat;if(lat>maxLat)maxLat=lat;
      })));
    });
    // Target a bit larger than the final on-screen size so zooming in with
    // the +/- buttons stays reasonably sharp before tile pixelation kicks in.
    const z=pickTileZoom(minLon,maxLon,minLat,maxLat,1400,1400);
    const originX=lon2x(minLon,z),originY=lat2y(maxLat,z);
    const W=lon2x(maxLon,z)-originX,H=lat2y(minLat,z)-originY;

    const indexByFsa={};
    (fsaIndex||[]).forEach(e=>{
      const pop=census[e.fsa]&&census[e.fsa].population!=null?census[e.fsa].population:null;
      indexByFsa[e.fsa]={...e,population:pop};
    });

    const features=geojson.features.map(ft=>{
      const polys=ft.geometry.type==='Polygon'?[ft.geometry.coordinates]:ft.geometry.coordinates;
      const allRings=[];
      let fMinX=Infinity,fMaxX=-Infinity,fMinY=Infinity,fMaxY=-Infinity;
      polys.forEach(rings=>rings.forEach(ring=>{
        const pts=projectRing(ring,originX,originY,z);
        pts.forEach(([x,y])=>{
          if(x<fMinX)fMinX=x;if(x>fMaxX)fMaxX=x;
          if(y<fMinY)fMinY=y;if(y>fMaxY)fMaxY=y;
        });
        allRings.push(pts);
      }));
      return{fsa:ft.properties.CFSAUID,d:ringsToPathD(allRings),bbox:[fMinX,fMinY,fMaxX,fMaxY]};
    });

    // One tile of buffer beyond the bbox on each side so panning/zooming
    // near the edges doesn't immediately show empty gaps.
    const tileMinX=Math.floor(originX/256)-1,tileMaxX=Math.floor((originX+W)/256)+1;
    const tileMinY=Math.floor(originY/256)-1,tileMaxY=Math.floor((originY+H)/256)+1;
    let tilesMarkup='';
    for(let ty=tileMinY;ty<=tileMaxY;ty++){
      for(let tx=tileMinX;tx<=tileMaxX;tx++){
        const x=tx*256-originX,y=ty*256-originY;
        tilesMarkup+=`<image href="${tileUrl(z,tx,ty)}" x="${x}" y="${y}" width="256" height="256"></image>`;
      }
    }

    MAP_STATE={prov,z,origin:[originX,originY],features,fullViewBox:[0,0,W,H],indexByFsa,tilesMarkup};
    paintFsaMap();
    fetchCensusData().then(c=>{
      if(!MAP_STATE||MAP_STATE.prov!==prov)return;
      Object.keys(MAP_STATE.indexByFsa).forEach(f=>{
        if(c[f]&&c[f].population!=null)MAP_STATE.indexByFsa[f].population=c[f].population;
      });
    }).catch(()=>{});
  }).catch(err=>{
    console.error(err);
    $('fsa-map-svg').innerHTML='<text x="300" y="300" text-anchor="middle" fill=PAL.tick font-size="13" font-family="Inter, sans-serif">Map not available for this province</text>';
    MAP_STATE=null;
    setMapAvailable(false); // no boundary file for this province — drop the Explore button
  });
}

// Sequential (audit count) or diverging (median saving %, centred on 0)
// single-pass colour scale, built fresh per province since the
// interesting range differs province to province.
// Continuous gradient legend bar with end (and optional middle) labels —
// mirrors the actual lerpColor ramp used to fill the shapes.
function setMapGradientLegend(gradientCss,leftLabel,midLabel,rightLabel){
  $('map-legend').innerHTML=
    `<div class="map-grad-wrap"><div class="map-grad" style="background:${gradientCss}"></div>`+
    `<div class="map-grad-labels"><span>${leftLabel}</span>${midLabel!=null?`<span>${midLabel}</span>`:''}<span>${rightLabel}</span></div></div>`;
}
function lerpColor(lo,hi,t){
  t=Math.max(0,Math.min(1,t));
  const c=lo.map((v,i)=>Math.round(v+(hi[i]-v)*t));
  return`rgb(${c.join(',')})`;
}
// Gamma-corrected lerp (t^GAMMA before mixing): a plain linear mix from a
// near-white base spends most of its range still looking pale, so common
// low-end values (e.g. 0-20% saved) barely differ from each other — which
// was the original complaint ("0% and 40%+ look the same"). Raising t to a
// power < 1 pushes colour away from the base faster at low t, so the low
// end of the range separates visually while the far end still tops out at
// the same saturated colour.
const MAP_COLOR_GAMMA=0.55;
function lerpColorGamma(lo,hi,t){
  return lerpColor(lo,hi,Math.pow(Math.max(0,Math.min(1,t)),MAP_COLOR_GAMMA));
}
function buildFsaColorScale(state){
  const vals=state.features.map(f=>state.indexByFsa[f.fsa]).filter(Boolean);
  const haveSavings=vals.some(e=>e.median_saving_pct!=null);
  if(haveSavings){
    const savings=vals.map(e=>e.median_saving_pct).filter(v=>v!=null);
    const lo=Math.min(...savings,0),hi=Math.max(...savings,0);
    $('map-color-meaning').textContent='median energy saving';
    const BASE=PAL.rampBase,POS=PAL.rampPos,NEG=PAL.rampNeg;
    const posColor=t=>lerpColorGamma(BASE,POS,t);
    const negColor=t=>lerpColorGamma(BASE,NEG,t);
    const colorOf=e=>{
      if(!e||e.median_saving_pct==null)return PAL.mapNull;
      const v=e.median_saving_pct;
      return v>=0?posColor(hi>0?v/hi:0):negColor(lo<0?v/lo:0);
    };
    // Sample the actual (gamma-corrected) ramp at several stops so the
    // legend bar — a CSS linear-gradient, which is inherently linear — still
    // matches the non-linear fill above, instead of a flat 2-stop gradient
    // that would misrepresent the real per-shape contrast.
    const steps=10,stops=[];
    for(let i=0;i<=steps;i++){
      const t=i/steps,v=lo+t*(hi-lo);
      stops.push(`${v>=0?posColor(hi>0?v/hi:0):negColor(lo<0?v/lo:0)} ${Math.round(t*100)}%`);
    }
    const gradientCss=`linear-gradient(90deg,${stops.join(',')})`;
    if(lo>=0){
      setMapGradientLegend(gradientCss,'0%',null,`+${Math.round(hi*100)}%<br>saved`);
    }else{
      setMapGradientLegend(gradientCss,`${Math.round(lo*100)}%<br>uses more`,'0%',`+${Math.round(hi*100)}%<br>saved`);
    }
    return colorOf;
  }
  const counts=vals.map(e=>e.row_count||0);
  const maxCount=Math.max(...counts,1);
  $('map-color-meaning').textContent='audited homes';
  setMapGradientLegend(`linear-gradient(90deg,${PAL.mapBase},${PAL.primary})`,'0 homes',null,`${maxCount.toLocaleString()} homes`);
  return e=>e?lerpColor(PAL.rampCountLo,PAL.rampCountHi,Math.sqrt((e.row_count||0)/maxCount)):PAL.mapNull;
}

function paintFsaMap(){
  if(!MAP_STATE)return;
  const svg=$('fsa-map-svg');
  const colorOf=buildFsaColorScale(MAP_STATE);
  svg.setAttribute('viewBox',MAP_STATE.fullViewBox.join(' '));
  const shapesMarkup=MAP_STATE.features.map(f=>{
    const entry=MAP_STATE.indexByFsa[f.fsa];
    const cls='fsa-shape'+(!entry?' no-data':'')+(f.fsa===SELECTED_FSA?' is-selected':'');
    return`<path class="${cls}" d="${f.d}" fill="${colorOf(entry)}" data-fsa="${f.fsa}" vector-effect="non-scaling-stroke"></path>`;
  }).join('');
  // #fsa-map-sharp-tiles sits between the base (province-wide) tiles and the
  // FSA shapes — loadSharpTiles fills it with a higher-zoom tile set scoped
  // to whichever FSA is zoomed into, so that view isn't just the base tiles
  // stretched blurry by the viewBox zoom. Empty at full-province zoom.
  // Per-shape % labels were dropped (cluttered the map) — colour scale +
  // legend + hover tooltip (onFsaMapHover) still carry the same info.
  svg.innerHTML=MAP_STATE.tilesMarkup+'<g id="fsa-map-sharp-tiles"></g>'+shapesMarkup;
  if(!svg.dataset.wired){
    svg.addEventListener('mousemove',onFsaMapHover);
    svg.addEventListener('mouseleave',hideFsaMapTip);
    svg.addEventListener('click',onFsaMapClick);
    wireFsaMapPan(svg);
    svg.dataset.wired='1';
  }
  // If an FSA was already selected before the map finished loading (deep
  // link or postal-code jump), zoom straight to it — the usual zoom happens
  // in the fsa-sel change handler, which fired before MAP_STATE existed.
  if(SELECTED_FSA)zoomFsaMapTo(SELECTED_FSA);
}

// Fetches a higher-zoom OSM tile set scoped to pixelBbox (in MAP_STATE's
// existing zoom-z coordinate system) and positions those tiles in that same
// coordinate system by scaling — i.e. "overzooming" the tile request without
// having to reproject MAP_STATE's polygons (which already look fine at any
// zoom since they're vector paths; only the raster basemap needed this).
function loadSharpTiles(pixelBbox){
  const g=document.getElementById('fsa-map-sharp-tiles');
  if(!g)return;
  if(!MAP_STATE){g.innerHTML='';return;}
  const{z:baseZ,prov}=MAP_STATE;
  const[ox,oy]=MAP_STATE.origin||[0,0];
  const[px0,py0,px1,py1]=pixelBbox;
  const minLon=x2lon(px0+ox,baseZ),maxLon=x2lon(px1+ox,baseZ);
  const maxLat=y2lat(py0+oy,baseZ),minLat=y2lat(py1+oy,baseZ);
  const z2=pickSharperZoom(minLon,maxLon,minLat,maxLat,900,900,17);
  if(z2<=baseZ){g.innerHTML='';return;}
  const scale=Math.pow(2,baseZ-z2); // <1 — size of one z2 tile in base-z units
  const worldX0=lon2x(minLon,z2),worldX1=lon2x(maxLon,z2);
  const worldY0=lat2y(maxLat,z2),worldY1=lat2y(minLat,z2);
  const tileMinX=Math.floor(worldX0/256)-1,tileMaxX=Math.floor(worldX1/256)+1;
  const tileMinY=Math.floor(worldY0/256)-1,tileMaxY=Math.floor(worldY1/256)+1;
  let markup='';
  for(let ty=tileMinY;ty<=tileMaxY;ty++){
    for(let tx=tileMinX;tx<=tileMaxX;tx++){
      const x=tx*256*scale-ox,y=ty*256*scale-oy,size=256*scale;
      markup+=`<image href="${tileUrl(z2,tx,ty)}" x="${x}" y="${y}" width="${size}" height="${size}"></image>`;
    }
  }
  if(MAP_STATE&&MAP_STATE.prov===prov)g.innerHTML=markup;
}

function onFsaMapHover(e){
  const el=e.target.closest('.fsa-shape');
  if(!_mapTipEl)_mapTipEl=$('map-tip');
  if(!el){hideFsaMapTip();return;}
  const fsa=el.dataset.fsa,entry=MAP_STATE.indexByFsa[fsa];
  const lines=[`<strong>${fsa}</strong>`];
  if(entry){
    if(entry.population!=null)lines.push(`${entry.population.toLocaleString()} population`);
    lines.push(`${entry.row_count.toLocaleString()} audited homes`);
    if(entry.median_saving_pct!=null)lines.push(`${Math.round(entry.median_saving_pct*100)}% median saving`);
  }else{
    lines.push('No audit data');
  }
  _mapTipEl.innerHTML=lines.join('<br>');
  _mapTipEl.style.display='block';
  _mapTipEl.style.left=(e.clientX+14)+'px';
  _mapTipEl.style.top=(e.clientY+14)+'px';
}
function hideFsaMapTip(){
  if(_mapTipEl)_mapTipEl.style.display='none';
}

let _mapDragged=false; // set by wireFsaMapPan, suppresses the click that follows a drag

function onFsaMapClick(e){
  if(_mapDragged){_mapDragged=false;return;}
  const el=e.target.closest('.fsa-shape');
  if(!el||!MAP_STATE)return;
  const fsa=el.dataset.fsa;
  if(!MAP_STATE.indexByFsa[fsa])return; // no audit data for this FSA — nothing to select
  const fsaSel=$('fsa-sel');
  fsaSel.value=fsa;
  fsaSel.dispatchEvent(new Event('change',{bubbles:true}));
  zoomFsaMapTo(fsa);
}

// Called both from the map's own click handler and from the FSA dropdown's
// change listener, so the map stays in sync regardless of which control
// the user actually used.
function zoomFsaMapTo(fsa){
  if(!MAP_STATE)return;
  const f=MAP_STATE.features.find(x=>x.fsa===fsa);
  document.querySelectorAll('#fsa-map-svg .fsa-shape').forEach(p=>p.classList.toggle('is-selected',p.dataset.fsa===fsa));
  if(!f)return;
  const[x0,y0,x1,y1]=f.bbox;
  const padX=(x1-x0)*0.25+4,padY=(y1-y0)*0.25+4;
  const box=[x0-padX,y0-padY,(x1-x0)+padX*2,(y1-y0)+padY*2];
  $('fsa-map-svg').setAttribute('viewBox',box.join(' '));
  $('map-reset-btn').style.display='';
  loadSharpTiles([box[0],box[1],box[0]+box[2],box[1]+box[3]]);
}
function resetFsaMapZoom(){
  if(MAP_STATE)$('fsa-map-svg').setAttribute('viewBox',MAP_STATE.fullViewBox.join(' '));
  $('map-reset-btn').style.display='none';
  const g=document.getElementById('fsa-map-sharp-tiles');
  if(g)g.innerHTML='';
}
// +/- zoom buttons: scale the current viewBox around its own centre.
// factor<1 zooms in, factor>1 zooms out. Clamped between the full province
// extent (can't zoom out past it) and a small fraction of it, low enough to
// tell apart adjacent small FSAs. loadSharpTiles re-fetches a higher-zoom
// basemap for the new view each time, so going this far in doesn't just
// stretch the original blurry province-level tiles.
function zoomFsaMapBy(factor){
  if(!MAP_STATE)return;
  const svg=$('fsa-map-svg');
  const[x0,y0,w,h]=svg.getAttribute('viewBox').split(' ').map(Number);
  const[,,fullW]=MAP_STATE.fullViewBox;
  const cx=x0+w/2,cy=y0+h/2;
  const newW=Math.max(fullW*0.0015,Math.min(fullW,w*factor));
  const scale=newW/w,newH=h*scale;
  const newX0=cx-newW/2,newY0=cy-newH/2;
  svg.setAttribute('viewBox',`${newX0} ${newY0} ${newW} ${newH}`);
  $('map-reset-btn').style.display=(newW<fullW-0.5)?'':'none';
  loadSharpTiles([newX0,newY0,newX0+newW,newY0+newH]);
}
// Distinct from resetFsaMapZoom: that's just "zoom back out" (used by the
// Reset view button) and keeps the FSA highlighted. This additionally
// clears the highlight — used when the dropdown goes back to "All areas".
function clearFsaMapSelection(){
  document.querySelectorAll('#fsa-map-svg .fsa-shape.is-selected').forEach(p=>p.classList.remove('is-selected'));
  resetFsaMapZoom();
}

// Drag-to-pan: translates the current viewBox by the same screen-pixel
// delta the pointer moved, converted into viewBox units via the SVG's
// rendered size. Panning is clamped so the view can't drift away from the
// province entirely. A small movement threshold distinguishes a pan from a
// plain click (which still needs to reach onFsaMapClick to select an FSA).
function wireFsaMapPan(svg){
  let dragging=false,moved=false,startX=0,startY=0,startBox=null;
  const DRAG_THRESHOLD=4;
  svg.addEventListener('pointerdown',e=>{
    if(!MAP_STATE)return;
    dragging=true;moved=false;_mapDragged=false;
    startX=e.clientX;startY=e.clientY;
    startBox=svg.getAttribute('viewBox').split(' ').map(Number);
    // Pointer capture is deferred until a drag is confirmed (see pointermove)
    // — capturing immediately on every pointerdown redirects the resulting
    // click event's target to the svg itself instead of the path actually
    // under the cursor, which broke FSA selection on plain clicks entirely.
  });
  svg.addEventListener('pointermove',e=>{
    if(!dragging||!MAP_STATE)return;
    const dx=e.clientX-startX,dy=e.clientY-startY;
    if(!moved&&Math.hypot(dx,dy)<DRAG_THRESHOLD)return;
    if(!moved)svg.setPointerCapture(e.pointerId);
    moved=true;_mapDragged=true;
    hideFsaMapTip();
    const rect=svg.getBoundingClientRect();
    const[,,w,h]=startBox;
    const unitsPerPxX=w/rect.width,unitsPerPxY=h/rect.height;
    const[fx0,fy0,fw,fh]=MAP_STATE.fullViewBox;
    let x0=startBox[0]-dx*unitsPerPxX,y0=startBox[1]-dy*unitsPerPxY;
    // Clamp so the viewBox can drift at most half its own size past the
    // full province extent on any side — keeps panning bounded without
    // forcing it to stay fully inside (panning right up to an edge FSA
    // should still be comfortable).
    x0=Math.max(fx0-w*0.5,Math.min(fx0+fw-w*0.5,x0));
    y0=Math.max(fy0-h*0.5,Math.min(fy0+fh-h*0.5,y0));
    svg.setAttribute('viewBox',`${x0} ${y0} ${w} ${h}`);
    $('map-reset-btn').style.display='';
  });
  function endDrag(e){
    if(!dragging)return;
    dragging=false;
    if(svg.hasPointerCapture&&svg.hasPointerCapture(e.pointerId))svg.releasePointerCapture(e.pointerId);
    if(moved){
      const box=svg.getAttribute('viewBox').split(' ').map(Number);
      loadSharpTiles([box[0],box[1],box[0]+box[2],box[1]+box[3]]);
    }
  }
  svg.addEventListener('pointerup',endDrag);
  svg.addEventListener('pointercancel',endDrag);
}

// ── Shareable URLs ──────────────────────────────────────────────────
// Keeps ?prov=&fsa= in the address bar in sync with the current selection
// (replaceState — no history spam), so a view can be copied and sent to
// someone else. parseDeepLink() is the read side, run once before the
// initial load(). The existing ?view= param is preserved untouched.
function updateShareUrl(){
  const p=new URLSearchParams(location.search);
  p.delete('prov');p.delete('fsa');
  if(PROVINCE_CODE&&PROVINCE_CODE!=='CA')p.set('prov',PROVINCE_CODE);
  if(SELECTED_FSA)p.set('fsa',SELECTED_FSA);
  const q=p.toString();
  history.replaceState(null,'',location.pathname+(q?'?'+q:''));
  // Keep the tab/bookmark title in step with the shared view.
  const prov=PROVINCES[PROVINCE_CODE];
  const where=SELECTED_FSA?`${SELECTED_FSA}, ${prov?prov.name:''}`:(prov&&PROVINCE_CODE!=='CA'?prov.name:'');
  document.title=where?`Retrofit Explorer — ${where}`:'Retrofit Explorer — real Canadian home energy retrofits';
}
function parseDeepLink(){
  const p=new URLSearchParams(location.search);
  const prov=(p.get('prov')||'').toUpperCase();
  const fsa=(p.get('fsa')||'').toUpperCase();
  if(PROVINCES[prov]&&prov!=='CA'){
    PROVINCE_CODE=prov;
    $('province-sel').value=prov;
    // Validated for real against the province's _index.json inside load().
    if(/^[A-Z]\d[A-Z]$/.test(fsa))SELECTED_FSA=fsa;
  }
}

// ── Postal-code quick find ──────────────────────────────────────────
// People know their postal code, not the term "FSA" — the first letter
// pins the province (postal district), the first three characters are the
// FSA. X covers both territories, so try each index until one contains it.
const POSTAL_PROV={A:['NF'],B:['NS'],C:['PE'],E:['NB'],G:['QC'],H:['QC'],J:['QC'],
  K:['ON'],L:['ON'],M:['ON'],N:['ON'],P:['ON'],R:['MB'],S:['SK'],T:['AB'],V:['BC'],X:['NT','NU'],Y:[]};
function showPcHint(msg,ok){
  const el=$('pc-hint');
  el.textContent=msg||'';
  el.style.display=msg?'':'none';
  el.style.color=ok?'var(--green)':'var(--red)';
}
function goToPostal(raw){
  const m=String(raw||'').trim().toUpperCase().replace(/\s+/g,'').match(/^([A-Z]\d[A-Z])/);
  if(!m){showPcHint('Enter a valid Canadian postal code, e.g. K1A 0B1.');return;}
  const fsa=m[1];
  const provs=POSTAL_PROV[fsa[0]];
  if(!provs){showPcHint(`No Canadian postal code starts with "${fsa[0]}" — check the first letter.`);return;}
  if(!provs.length){showPcHint('Yukon has too few matched audits to appear in this dataset.');return;}
  showPcHint('');
  (function tryNext(i){
    if(i>=provs.length){
      showPcHint(`No matched retrofits recorded for ${fsa} — try the province-wide view instead.`);
      return;
    }
    fetchFsaIndex(provs[i]).then(idx=>{
      if(!idx.some(e=>e.fsa===fsa)){tryNext(i+1);return;}
      PROVINCE_CODE=provs[i];
      SELECTED_FSA=fsa;
      SELECTED_TYPE='';
      $('province-sel').value=PROVINCE_CODE;
      ['type-sel','fuel-sel','depth-sel'].forEach(id=>$(id).value='');
      clearMeasures();
      updateShareUrl();
      showPcHint(''); // area-chip pill already shows the selected FSA
      load(); // syncs the FSA dropdown + map zoom itself once the index re-resolves (cached)
    }).catch(()=>tryNext(i+1));
  })(0);
}
$('pc-input').addEventListener('keydown',e=>{if(e.key==='Enter')goToPostal(e.target.value);});
$('pc-input').addEventListener('change',e=>{if(e.target.value.trim())goToPostal(e.target.value);});

// Wire province selector
$('province-sel').addEventListener('change',function(){
  PROVINCE_CODE=this.value;
  if(!PROVINCE_CODE)return;
  // Reset filters when province changes
  SELECTED_FSA='';SELECTED_TYPE='';
  ['type-sel','fuel-sel','depth-sel'].forEach(id=>$(id).value='');
  clearMeasures();
  $('fsa-sel').value='';
  $('pc-input').value='';showPcHint('');
  updateShareUrl();
  load();
});

// FSA dropdown switches between province-wide and FSA-level view.
// Listener is attached once here (not rebuilt per-load like type/fuel/depth
// used to be) since #fsa-sel itself is never replaced, only its <option>s.
$('fsa-sel').addEventListener('change',function(){
  SELECTED_FSA=this.value;
  // Any area change not initiated by the postal box (map click, ✕ chip)
  // invalidates a lingering "✓ Showing postal area …" hint.
  showPcHint('');
  if(!PROVINCE_CODE)return;
  ['type-sel','fuel-sel','depth-sel'].forEach(id=>$(id).value='');
  clearMeasures();
  updateShareUrl();
  // Mint a fresh token so a slow fetch from a previously-selected FSA that
  // lands after this one is discarded by the myToken!==LOAD_TOKEN guard.
  const myToken=++LOAD_TOKEN;
  if(SELECTED_FSA){
    loadFsaView(myToken);
    zoomFsaMapTo(SELECTED_FSA);
  }else{
    loadProvinceView(myToken);
    clearFsaMapSelection();
  }
});

// House-type dropdown: behaviour differs by mode (see applyFilters/renderProvince).
$('type-sel').addEventListener('change',function(){
  SELECTED_TYPE=this.value;
  if(MODE==='fsa'){
    applyFilters();
  }else if(MODE==='province'){
    const payload=PROVINCE_SUMMARY_CACHE.get(PROVINCE_CODE);
    if(payload)renderProvince(payload);
  }
});
$('fuel-sel').addEventListener('change',applyFilters);
$('depth-sel').addEventListener('change',applyFilters);

// ── Measures multi-select (FSA view only, like fuel/depth) ──────────
// Checkboxes over the MEASURES list; a home matches when it did ALL the
// checked measures (it may have done more), so checking nothing = no filter.
function populateMeasuresPanel(){
  const panel=$('measures-panel');
  panel.innerHTML='<div class="multi-select-note">Homes that did at least the checked measures</div>'+
    MEASURES.map(m=>`<label><input type="checkbox" value="${m.key}"> ${m.label}</label>`).join('');
  panel.querySelectorAll('input').forEach(cb=>
    cb.addEventListener('change',()=>{updateMeasuresBtn();applyFilters();}));
}
function selectedMeasures(){
  return[...document.querySelectorAll('#measures-panel input:checked')].map(cb=>cb.value);
}
function updateMeasuresBtn(){
  const sel=selectedMeasures();
  $('measures-btn-text').textContent=
    sel.length===0?'Any measures':
    sel.length===1?MEASURES.find(m=>m.key===sel[0]).label:
    `${sel.length} measures`;
  $('measures-btn').classList.toggle('has-selection',sel.length>0);
}
function clearMeasures(){
  document.querySelectorAll('#measures-panel input:checked').forEach(cb=>cb.checked=false);
  updateMeasuresBtn();
}
function closeMeasuresPanel(){
  $('measures-dd').classList.remove('open');
  $('measures-btn').setAttribute('aria-expanded','false');
}
$('measures-btn').addEventListener('click',function(){
  const open=$('measures-dd').classList.toggle('open');
  this.setAttribute('aria-expanded',open);
});
document.addEventListener('click',e=>{if(!e.target.closest('#measures-dd'))closeMeasuresPanel();});
document.addEventListener('keydown',e=>{if(e.key==='Escape')closeMeasuresPanel();});
populateMeasuresPanel();

// ── Simple / Advanced mode ──────────────────────────────────────────
// body.mode-simple/.mode-advanced (set as early as possible, in the inline
// script right after <body>, to avoid a flash of the wrong mode) is the
// single source of truth for visibility — every Advanced-only section just
// has data-mode="advanced" and a CSS rule hides it in Simple. This is the
// JS-side counterpart: which mode is active right now, and re-running the
// Advanced-only renderers (using whatever's already cached — no re-fetch)
// when the user switches into Advanced, since render()/renderProvince()
// skip them entirely while in Simple to save the Chart.js draw cost.
function isAdvancedMode(){return document.body.classList.contains('mode-advanced');}
function setViewMode(mode){
  if(mode!=='advanced')mode='simple';
  document.body.className='mode-'+mode;
  try{localStorage.setItem('viewMode',mode);}catch(e){}
  document.querySelectorAll('.mode-btn').forEach(b=>b.classList.toggle('active',b.dataset.view===mode));
  renderAdvancedSections();
}

// Landing default: load "All of Canada" immediately instead of waiting on
// an empty page until the user picks a province (matches province-sel's
// pre-selected option).
// Must run before anything draws: the <head> bootstrap already set
// data-theme to avoid a flash, but PAL is still empty until readPalette()
// reads those vars back out, and every chart colour comes from PAL.
initTheme();
fetchLookups();
injectIcons(); // drop the hand-crafted line-icons into every data-icon element
document.querySelectorAll('.mode-btn').forEach(b=>b.classList.toggle('active',b.dataset.view===(isAdvancedMode()?'advanced':'simple')));
parseDeepLink(); // ?prov=&fsa= override the CA landing default when present
updateShareUrl(); // canonicalise the params + set the tab title to match
load();

// ── Pipeline flow diagram tooltips (methodology section E overview) ──
// The SVG is static markup, not drawn by JS, so this just wires each
// .flow-tip box's data-tip to one shared floating tooltip -- same visual
// pattern as ensureFuelTooltip above, kept separate since it's plain text
// on hover/focus rather than hit-boxes on a canvas.
let _pipeTipEl=null;
function ensurePipeTooltip(){
  if(_pipeTipEl)return _pipeTipEl;
  const el=document.createElement('div');
  el.id='pipe-tip';
  document.body.appendChild(el);
  return (_pipeTipEl=el);
}
function initPipelineTooltips(){
  const svg=$('pipeline-svg');
  if(!svg)return;
  const tip=ensurePipeTooltip();
  const hide=()=>{tip.style.display='none';};
  svg.querySelectorAll('.flow-tip[data-tip]').forEach(el=>{
    const text=el.getAttribute('data-tip');
    el.addEventListener('mousemove',e=>{
      tip.textContent=text;
      tip.style.display='block';
      const pad=14,tw=280;
      let left=e.clientX+pad, top=e.clientY+pad;
      if(left+tw>window.innerWidth-10)left=e.clientX-tw-pad;
      if(top+140>window.innerHeight-10)top=Math.max(10,e.clientY-140);
      tip.style.left=left+'px';
      tip.style.top=top+'px';
    });
    el.addEventListener('mouseleave',hide);
    el.addEventListener('focus',()=>{
      const r=el.getBoundingClientRect();
      tip.textContent=text;
      tip.style.display='block';
      tip.style.left=Math.min(r.left,window.innerWidth-290)+'px';
      tip.style.top=(r.bottom+8)+'px';
    });
    el.addEventListener('blur',hide);
  });
}
initPipelineTooltips();
