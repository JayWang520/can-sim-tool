const fs = require('node:fs'), vm = require('node:vm'), assert = require('node:assert/strict');
const source = fs.readFileSync('web/app.js', 'utf8');
const nodes = new Map();
const $ = id => { if (!nodes.has(id)) nodes.set(id, {value:'D:/old.json'}); return nodes.get(id); };
let selected = null;
const calls = [];
const context = {$, toast(){}, async api(path, method, body) {
  calls.push({path, method, body});
  return path.startsWith('/api/filepicker') ? {path:selected} : {path:body.path};
}};
vm.createContext(context);
vm.runInContext(source.slice(source.indexOf('async function pickFile('), source.indexOf('$("btn-preset-load2").onclick')), context);
vm.runInContext(source.slice(source.indexOf('$("btn-trig-save2").onclick'), source.indexOf('$("btn-trig-load2").onclick')), context);
(async()=>{
  for (const [button, endpoint] of [['btn-preset-save2','/api/presets/save_to'],['btn-trig-save2','/api/triggers/save_to']]) {
    selected=null; calls.length=0;
    await $(button).onclick();
    assert.equal(calls.length,1); // cancel never saves to stale path
    selected='D:/new.json'; calls.length=0;
    await $(button).onclick();
    assert.equal(calls[0].path,'/api/filepicker?mode=save&ext=json');
    assert.equal(calls[1].path,endpoint);
    assert.equal(calls[1].body.path,selected);
  }
  console.log('PASS: save always opens picker; cancel never writes; chosen path used');
})().catch(e=>{console.error(e);process.exitCode=1;});
