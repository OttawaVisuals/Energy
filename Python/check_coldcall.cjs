// Regression checks for the embedded game logic; no browser or dependencies.
// Run: node Python/check_coldcall.cjs
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const path = require('node:path');
const html = fs.readFileSync(path.join(__dirname, '../coldcall.html'), 'utf8');
const script = html.match(/<script>\s*([\s\S]*?)<\/script>/)[1];
new vm.Script(script); // Check the entire embedded script, not just extracted functions.
const judges = {};
for (const match of script.matchAll(/setupPuzzle\((\d), \{[\s\S]*?judge\(raw\) \{([\s\S]*?)\n  \}\n\}\);/g)) {
  judges[match[1]] = new Function('ctx', 'raw', `with(ctx) { ${match[2]} }`);
}
assert.equal(Object.keys(judges).length, 6);
const near = (a,b,t) => Math.abs(a-b)<=t;
const ctx = {near, TRUE_L:3200, KWH_PER_L:7.09, order:[5,2,7,0,3,6,1,4],
  sealed:new Set(), LEAKS:Array(5), rulesKept:()=>false, rushPeak:()=>54, BEST_A:54, running5:false};
for (const [n,answer] of [[2,'22690'],[3,'5.8'],[4,'13'],[5,'3.8']]) {
  assert.notEqual(judges[n](ctx,answer),null, `Line ${n} must reject an unfinished activity`);
}
ctx.order=[0,1,2,3,4,5,6,7]; ctx.sealed=new Set([0,1,2,3,4]);
ctx.rulesKept=()=>true; ctx.running5=true;
for (const [n,answer] of [[2,'22688'],[3,'5.8'],[4,'13'],[5,'3.8']]) {
  assert.equal(judges[n](ctx,answer),null, `Line ${n} must accept a completed activity`);
}
ctx.rushPeak=()=>58;
assert.notEqual(judges[4](ctx,'13'),null,'Reject a claimed optimum when the board has a higher peak');
ctx.rushPeak=()=>54;
const costs = vm.runInNewContext(script.match(/const COSTS = (\[[\s\S]*?\n\]);/)[1]);
const right = vm.runInNewContext(script.match(/const RIGHT6 = (\[[^;]+\]);/)[1]);
ctx.RIGHT6=right;
ctx.saved6=()=>costs.filter(c=>ctx.onPan6.has(c.k)).reduce((s,c)=>s+(c.side==='furnace'?1:-1)*c.$,0);
let accepted=0;
for(let mask=0;mask<2**costs.length;mask++) {
  ctx.onPan6=new Set(costs.filter((_,i)=>mask & (1<<i)).map(c=>c.k));
  const ok=judges[6](ctx,'1885')===null;
  if(ok) { accepted++; assert.deepEqual([...ctx.onPan6].sort(),[...right].sort()); }
}
assert.equal(accepted,1,'Only the exact job-summary selection may pass');
ctx.onPan6=new Set(right);
assert.equal(ctx.saved6(),1885);
assert.notEqual(judges[6](ctx,'1889'),null,'Reject the previous incorrect savings');
assert.equal(costs.find(c=>c.k==='water').$,460*.75);
assert.equal(Math.round(4870*(.5*.039+.4*.157+.1*.391)*.765),452);
// A pointer within an hour must resolve to that hour, preserving the grabbed tile hour.
const dropColumn = new Function('return (' + script.match(/function scheduleDropColumn\([^)]*\) \{[\s\S]*?\n\}/)[0] + ')')();
let snapChecks = 0;
for (const duration of [2,4,6]) {
  for (let start=0; start<=24-duration; start++) {
    for (let grab=0; grab<duration; grab++) {
      for (const fraction of [.1,.5,.9]) {
        for (const left of [0,-312,470]) {
          const step=28.125;
          assert.equal(dropColumn(left+(start+grab+fraction)*step,left,step,grab,duration),start);
          snapChecks++;
        }
      }
    }
  }
  assert.equal(dropColumn(-1000,0,28,0,duration),0);
  assert.equal(dropColumn(10000,0,28,duration-1,duration),24-duration);
}
console.log(`PASS: ${snapChecks} hour-snap cases, including scrolled tracks and every grabbed hour; boundary clamping.`);
console.log('PASS: full script syntax; gates and completed answers for lines 2–5; all 2,048 cost selections; corrected costs and historical electricity calculation.');
