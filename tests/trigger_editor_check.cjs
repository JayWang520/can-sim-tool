const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const source = fs.readFileSync('web/app.js', 'utf8');
const elements = new Map();
function $(id) {
  if (!elements.has(id)) elements.set(id, {
    value: '', innerHTML: '', textContent: '', hidden: false,
    focus() {}, querySelectorAll() { return this.inputs || []; },
  });
  return elements.get(id);
}
const rule = { id: 'rule1', name: 'old', match_id: '123', match_pgn: 1,
  data_contains: 'AA', data_cond: [{ type: 'byte', index: 0, value: 170 }],
  action: 'send', send_id: '456', send_data: '12AB', send_extended: false, hits: 5, enabled: false };
const calls = [];
const context = { $, window: {}, setInterval() {}, esc: String, hexGroup: String, toast() {},
  renderByteEditor(el) { el.inputs = Array.from({length: 8}, () => ({value: '00'})); },
  getByteHex(el) { return el.inputs.map(i => i.value).join(''); },
  async api(path, method = 'GET', body) { calls.push({path, method, body}); return method === 'GET' ? [rule] : {}; },
};
vm.createContext(context);
vm.runInContext(source.slice(source.indexOf('let trConds = []'), source.indexOf('// ------------------------------------------------------------- 触发规则保存/读取')), context);
(async () => {
  await vm.runInContext('refreshTriggers()', context);
  context.window.trEdit('rule1');
  context.window.trCondEdit(0);
  assert.equal($('tc-v').value, 'AA');
  $('tc-v').value = '12';
  $('tc-op').value = '!=';
  $('btn-tr-cond-add').onclick();
  assert.equal(vm.runInContext('trConds.length', context), 1);
  assert.equal(vm.runInContext('trConds[0].value', context), 18);
  assert.equal(vm.runInContext('trConds[0].op', context), '!=');
  context.window.trCondEdit(0);
  $('tc-v').value = '34';
  $('btn-tr-cond-cancel').onclick();
  assert.equal(vm.runInContext('trConds[0].value', context), 18);
  $('tr-cond-mode').value = 'or';
  assert.equal($('tr-name').value, 'old');
  assert.deepEqual($('tr-send-bytes').inputs.map(i => i.value), ['12','AB','','','','','','']);
  assert.equal($('tr-send-ext').checked, false);
  $('tr-name').value = 'edited';
  $('tr-id').value = ''; $('tr-pgn').value = ''; $('tr-data').value = '';
  context.window.trCondDel(0);
  await vm.runInContext('refreshTriggers()', context);
  assert.equal($('tr-name').value, 'edited'); // periodic refresh must not discard draft
  await $('btn-tr-add').onclick();
  const saved = calls.find(c => c.method === 'PUT');
  assert.equal(saved.path, '/api/triggers/rule1');
  assert.equal(saved.body.name, 'edited');
  assert.equal(saved.body.data_cond_mode, 'or');
  assert.equal(saved.body.match_id, null); assert.equal(saved.body.match_pgn, null);
  assert.equal(saved.body.data_contains, null); assert.equal(saved.body.data_cond.length, 0);
  assert.equal(saved.body.send_data, '12AB'); assert.equal(saved.body.send_extended, false);
  assert.equal(calls.filter(c => c.method === 'POST').length, 0);
  context.window.trEdit('rule1');
  const before = calls.length;
  $('btn-tr-cancel').onclick();
  assert.equal(calls.length, before);
  assert.equal($('btn-tr-add').textContent, '添加规则');
  for (const condition of [
    {type:'bytes',start:0,end:2,op:'>=',value:0x123456},
    {type:'bit',index:13,value:1},
    {type:'bits',byte:2,start:1,end:3,value:5},
  ]) {
    vm.runInContext(`trConds = [${JSON.stringify(condition)}]`, context);
    context.window.trCondEdit(0);
    $('btn-tr-cond-add').onclick();
    assert.equal(vm.runInContext('trConds.length', context), 1);
    assert.deepEqual(JSON.parse(vm.runInContext('JSON.stringify(trConds[0])', context)),condition);
  }
  vm.runInContext('trConds = [{type:"byte",index:0,value:1},{type:"byte",index:1,value:2}]',context);
  context.window.trCondEdit(1);
  context.window.trCondDel(0);
  $('tc-v').value='56'; $('tc-op').value='==';
  $('btn-tr-cond-add').onclick();
  assert.equal(vm.runInContext('trConds.length',context),1);
  assert.equal(vm.runInContext('trConds[0].value',context),86);
  console.log('PASS: edit, exact short-frame refill, draft survives refresh, PUT original, clear conditions, cancel');
})().catch(error => { console.error(error); process.exitCode = 1; });
