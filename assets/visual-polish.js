/* Presentation only: no data transformations or filter/value changes. */
(function(){
  'use strict';
  const tool=document.body.dataset.energyTool;
  if(!tool)return;
  // Keep floating SVG tooltips fully inside the viewport, including after touch.
  document.querySelectorAll('.chart-tip').forEach(tip=>{
    let pending=false;
    new MutationObserver(()=>{
      if(pending)return;pending=true;
      requestAnimationFrame(()=>{
        pending=false;
        if(getComputedStyle(tip).display==='none')return;
        const r=tip.getBoundingClientRect();
        const x=Math.max(12,Math.min(r.left,innerWidth-r.width-12));
        const y=Math.max(12,Math.min(r.top,innerHeight-r.height-12));
        if(Math.abs(x-r.left)>1)tip.style.left=x+'px';
        if(Math.abs(y-r.top)>1)tip.style.top=y+'px';
      });
    }).observe(tip,{attributes:true,attributeFilter:['style','class'],childList:true,subtree:true});
  });
  const scrolls='.data-tbl-wrap,.tbl-wrap,.city-tbl-wrap,.hdt-scroll,.tv-tblwrap,.scorecard-wrap,.table-scroll,.scroll-x,.flow-scroll';
  const markScrolls=()=>document.querySelectorAll(scrolls).forEach(el=>{
    if(el.dataset.scrollRegion)return;
    el.dataset.scrollRegion='true';el.tabIndex=0;el.setAttribute('role','region');
    el.setAttribute('aria-label',el.querySelector('table')?'Scrollable data table':'Scrollable diagram');
  });
  markScrolls();
  // Async tables are rendered after the initial document. Observe only their mounts.
  const mounts=[...document.querySelectorAll('main,.main')];
  let timer;
  mounts.forEach(el=>new MutationObserver(()=>{clearTimeout(timer);timer=setTimeout(markScrolls,150)}).observe(el,{childList:true,subtree:true}));
  if(typeof Chart==='function'){
    Chart.defaults.font.family="'Inter',system-ui,sans-serif";
    Chart.register({id:'energyReadability',beforeUpdate(chart){
      const scales=chart.options.scales||{};
      Object.values(scales).forEach(axis=>{
        if(!axis.ticks)return;
        const font=axis.ticks.font||{};
        if(typeof font!=='function')axis.ticks.font={...font,family:"'Inter',system-ui,sans-serif",size:Math.max(11,Number(font.size)||11)};
      });
      const tip=chart.options.plugins?.tooltip;
      if(tip&&tip.enabled!==false){
        tip.backgroundColor='#0B2545';tip.cornerRadius=8;tip.padding=10;
        tip.titleFont={...tip.titleFont,size:12};tip.bodyFont={...tip.bodyFont,size:12};
      }
      if(matchMedia('(prefers-reduced-motion: reduce)').matches)chart.options.animation=false;
    }});
    Object.values(Chart.instances||{}).forEach(chart=>chart.update('none'));
  }
  // Only redraw when width changes, not when a phone keyboard changes height.
  if(tool==='ceud'||tool==='heatpump'){
    let width=innerWidth,resizeTimer;
    window.addEventListener('resize',()=>{
      if(innerWidth===width)return;width=innerWidth;
      clearTimeout(resizeTimer);resizeTimer=setTimeout(()=>{
        if(tool==='ceud'&&typeof renderAll==='function'&&typeof currentData!=='undefined'&&currentData)renderAll();
        if(tool==='heatpump'&&typeof redrawAllCharts==='function')redrawAllCharts();
      },180);
    });
  }
  if(tool==='heatpump'){
    // Some chart panels are initially hidden. Lay them out once they have width.
    const widths=new WeakMap();let layoutTimer;
    const chartResize=new ResizeObserver(entries=>{
      let changed=false;
      entries.forEach(({target,contentRect})=>{
        const w=Math.round(contentRect.width);
        if(w>0&&w!==widths.get(target)){widths.set(target,w);changed=true;}
      });
      if(changed){clearTimeout(layoutTimer);layoutTimer=setTimeout(()=>{if(typeof redrawAllCharts==='function')redrawAllCharts()},80);}
    });
    document.querySelectorAll('.keychart-wrap').forEach(el=>chartResize.observe(el));
  }
  if(tool==='geothermal'){
    const mobile=matchMedia('(max-width:640px)');
    ['legend','segsel'].forEach(id=>{
      const panel=document.getElementById(id);if(!panel)return;
      const content=document.createElement('div');content.className='geo-panel-content';content.id=id+'-content';
      while(panel.firstChild)content.appendChild(panel.firstChild);
      const button=document.createElement('button');button.type='button';button.className='geo-panel-toggle';
      button.textContent=id==='legend'?'Map legend':'Building type';
      button.setAttribute('aria-label',button.textContent);
      button.setAttribute('aria-expanded','false');button.setAttribute('aria-controls',content.id);
      button.addEventListener('click',()=>{
        const open=!panel.classList.contains('geo-panel-open');panel.classList.toggle('geo-panel-open',open);button.setAttribute('aria-expanded',String(open));
        if(open&&mobile.matches){
          document.getElementById('assumptions')?.classList.remove('open');
          const other=document.getElementById(id==='legend'?'segsel':'legend');
          other?.classList.remove('geo-panel-open');other?.querySelector('button')?.setAttribute('aria-expanded','false');
        }
      });
      panel.append(button,content);
    });
    const title=document.getElementById('title'),segment=document.getElementById('segsel');
    const align=()=>{
      if(title&&segment)segment.style.top=(title.offsetTop+title.offsetHeight+8)+'px';
      const layers=document.querySelector('.leaflet-top.leaflet-right');
      if(layers&&segment)layers.style.top=mobile.matches?(segment.offsetTop+segment.offsetHeight+8)+'px':'';
    };
    if(title)new ResizeObserver(align).observe(title);
    if(segment)new ResizeObserver(align).observe(segment);
    window.addEventListener('resize',align);align();
    const head=document.getElementById('asmHead'),assumptions=document.getElementById('assumptions');
    if(head&&assumptions){
      head.tabIndex=0;head.setAttribute('role','button');head.setAttribute('aria-controls','asmBody');
      head.setAttribute('aria-expanded',String(assumptions.classList.contains('open')));
      head.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();head.click()}});
      new MutationObserver(()=>head.setAttribute('aria-expanded',String(assumptions.classList.contains('open')))).observe(assumptions,{attributes:true,attributeFilter:['class']});
      head.addEventListener('click',()=>{
        if(mobile.matches)document.querySelectorAll('.geo-panel-open').forEach(el=>{el.classList.remove('geo-panel-open');el.querySelector('button')?.setAttribute('aria-expanded','false')});
      });
    }
  }
})();
