const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const nodes = {};
for (const id of ['file','sheet','base','unit','open','export','group','status','stats','frames','bytes','errors','page','prev','next']) {
  nodes[`analysis-${id}`] = {value:'', textContent:'', innerHTML:'', disabled:false, add() {}};
}
const n = id => nodes[`analysis-${id}`];
n('file').files = [{size:20}]; n('base').value='16'; n('unit').value='s';
const frames = Array.from({length:201}, (_,i) => ({row:i+2,ts:i,id:'123',ext:false,dir:'rx',channel:'',dlc:2,data:'1234'}));
const result = {file:'a.csv', count:201,total:201,errors:[],duration_s:200,sheets:[],frames,
  stats:[{id:'123',ext:false,dir:'rx',channel:'',count:201,period_mean_ms:1000,period_min_ms:1000,period_max_ms:1000,changes:0,backwards:0,bytes:[{byte:1,min:18,max:18,changes:0}]}]};
let fail = false;
vm.runInNewContext(fs.readFileSync('web/analysis.js','utf8'), {
  document:{getElementById:id=>nodes[id]}, esc:s=>s.replaceAll('<','&lt;'),
  FormData:class {append(){}}, Option:class {},
  fetch:async () => ({ok:!fail,json:async()=>fail?{detail:'bad file'}:result}),
});
(async()=>{
  await n('open').onclick();
  assert.equal(n('frames').innerHTML.match(/<tr>/g).length,100);
  assert.match(n('page').textContent,/1 \/ 3/);
  n('next').onclick(); n('next').onclick();
  assert.equal(n('frames').innerHTML.match(/<tr>/g).length,1);
  assert.equal(n('next').disabled,true);
  n('group').value='0'; n('group').onchange();
  assert.match(n('page').textContent,/1 \/ 3/);
  assert.match(n('bytes').textContent,/Byte1/);
  fail=true; await n('open').onclick();
  assert.match(n('status').textContent,/bad file/);
  assert.equal(n('frames').textContent,'');
  assert.equal(n('export').disabled,true);
  console.log('Offline analysis UI: pagination, filtering, bytes and failure state passed');
})();
