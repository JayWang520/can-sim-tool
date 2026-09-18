const fs = require('node:fs');
const assert = require('node:assert/strict');
const {JSDOM} = require('../build/ui-test-tools/node_modules/jsdom');
const dom = new JSDOM('<div id="tx-bytes"></div><input id="tx-id" value="123"><input id="tx-ext" type="checkbox"><button id="btn-tx-send"></button>', {runScripts:'outside-only'});
const w = dom.window, d = w.document;
const source = fs.readFileSync(process.argv[2] || 'web/app.js', 'utf8');
w.eval(source.slice(source.indexOf('function renderByteEditor('),source.indexOf('// ---------------------------------------------------------------- tabs')));
const editor = d.getElementById('tx-bytes');
const sent=[];
w.$=id=>d.getElementById(id);
w.api=async(path,method,body)=>{sent.push({path,method,body});};
w.eval(source.slice(source.indexOf('$("btn-tx-send").onclick'),source.indexOf('const SENDER_MODES')));
const values = () => [...editor.querySelectorAll('input')].map(x=>x.value);
function reset() {editor._byteKeyHandled=false;w.renderByteEditor(editor);editor.firstElementChild.firstElementChild.focus();}
function key(key, extras={}) {
  const e = new w.KeyboardEvent('keydown', {key,bubbles:true,cancelable:true,...extras});
  d.activeElement.dispatchEvent(e); return e;
}
const failures=[];
function test(name, fn){try{fn();console.log('PASS',name);}catch(e){failures.push(name);console.error('FAIL',name,e.message);}}
test('continuous typing and exact outgoing bytes',()=>{
  reset(); for(const c of '1234567890ABCDEF')key(c);
  assert.deepEqual(values(),['12','34','56','78','90','AB','CD','EF']);
  assert.equal(w.getByteHex(editor),'1234567890ABCDEF');
  d.getElementById('btn-tx-send').click();
  assert.equal(sent.at(-1).path,'/api/send');
  assert.equal(sent.at(-1).body.data,'1234567890ABCDEF');
  assert.equal(sent.at(-1).body.extended,false);
});
test('Ctrl+A and Ctrl+C never insert data or cancel native shortcut',()=>{
  reset(); const before=values();
  assert.equal(key('a',{ctrlKey:true}).defaultPrevented,false);
  assert.equal(key('c',{ctrlKey:true}).defaultPrevented,false);
  assert.deepEqual(values(),before);
});
test('Mac shortcuts, Alt and composition do not insert hex',()=>{
  reset();const before=values();
  assert.equal(key('a',{metaKey:true}).defaultPrevented,false);
  assert.equal(key('f',{altKey:true}).defaultPrevented,false);
  assert.equal(key('a',{isComposing:true}).defaultPrevented,false);
  assert.deepEqual(values(),before);
});
test('paste fills all bytes without duplicating characters',()=>{
  reset();const e=new w.Event('paste',{bubbles:true,cancelable:true});
  Object.defineProperty(e,'clipboardData',{value:{getData:()=> '12 34 56 78 90 AB CD EF'}});
  d.activeElement.dispatchEvent(e);
  assert.equal(w.getByteHex(editor),'1234567890ABCDEF');
});
test('single digit and native deletion',()=>{
  reset();key('1');assert.equal(values()[0],'1');assert.equal(values()[1],'00');
  assert.equal(key('Backspace').defaultPrevented,false);
});
test('redundant beforeinput after focus advances must not duplicate second digit',()=>{
  reset();key('1');key('2');
  d.activeElement.dispatchEvent(new w.InputEvent('beforeinput',{inputType:'insertText',data:'2',bubbles:true,cancelable:true}));
  assert.deepEqual(values(),['12','00','00','00','00','00','00','00']);
});
w.close();
if(failures.length)process.exitCode=1;
