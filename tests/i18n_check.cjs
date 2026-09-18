const fs = require('node:fs');
const assert = require('node:assert/strict');
const {JSDOM} = require('../build/ui-test-tools/node_modules/jsdom');
const dom = new JSDOM(fs.readFileSync('web/index.html','utf8'), {url:'http://localhost', runScripts:'outside-only'});
const w = dom.window, d = w.document;
w.eval(fs.readFileSync('web/i18n.js','utf8'));
const tick = () => new Promise(resolve => setTimeout(resolve,0));
(async()=>{
  const input = d.getElementById('tr-name');
  input.value = '删除'; input.focus(); input.setSelectionRange(1,1);
  const byte = d.createElement('input'); byte.value='12';
  d.getElementById('tr-send-bytes').append(byte);
  d.getElementById('tr-body').innerHTML='<tr><td>删除</td><td>数据含 FFFF</td><td>计数</td><td>2</td><td data-ui>是</td><td><button>编辑</button></td></tr>';
  w.canI18n.setLanguage('en'); await tick();
  assert.equal(d.documentElement.lang,'en');
  assert.equal(d.getElementById('btn-connect').textContent,'Connect');
  assert.equal(d.getElementById('tr-body').querySelector('td').textContent,'删除');
  assert.equal(d.getElementById('tr-body').querySelector('button').textContent,'Edit');
  assert.equal(d.getElementById('tr-body').querySelector('[data-ui]').textContent,'Yes');
  assert.equal(input.value,'删除'); assert.equal(d.activeElement,input); assert.equal(input.selectionStart,1);
  assert.equal(d.getElementById('tr-send-bytes').firstChild,byte); assert.equal(byte.value,'12');
  d.getElementById('btn-tr-add').textContent='保存修改'; await tick();
  assert.equal(d.getElementById('btn-tr-add').textContent,'Save changes');
  d.getElementById('toast').textContent='已保存到 D:/删除.json（2 条规则）'; await tick();
  assert.equal(d.getElementById('toast').textContent,'Saved to D:/删除.json (2 rules)');
  assert.equal(w.localStorage.getItem('can-sim-language'),'en');
  w.canI18n.setLanguage('unsupported');
  assert.equal(w.canI18n.language,'en');
  assert.equal(d.getElementById('tr-cond-mode').value,'and');
  assert.equal(d.getElementById('ps-mode').value,'fixed');
  assert.equal(d.getElementById('theme-select').value,'dark');
  const missing=[];
  const walker=d.createTreeWalker(d.body,w.NodeFilter.SHOW_TEXT);
  while(walker.nextNode()) {
    const n=walker.currentNode;
    if(n.parentElement.closest('script,style,tbody,#language-select,#toast')) continue;
    if(/[\u4e00-\u9fff]/.test(n.nodeValue)) missing.push(n.nodeValue.trim());
  }
  assert.deepEqual(missing,[],`Untranslated static UI: ${missing.join('\n')}`);
  const missingAttrs=[];
  d.querySelectorAll('[placeholder],[title],[aria-label]').forEach(el=>{
    if(el.closest('#language-select')) return;
    for(const key of ['placeholder','title','aria-label']) {
      const value=el.getAttribute(key);
      if(value && /[\u4e00-\u9fff]/.test(value)) missingAttrs.push(value);
    }
  });
  assert.deepEqual(missingAttrs,[]);
  w.canI18n.setLanguage('zh-CN'); await tick();
  assert.equal(d.getElementById('btn-connect').textContent,'连接');
  assert.equal(d.getElementById('btn-tr-add').textContent,'保存修改');
  assert.equal(d.getElementById('toast').textContent,'已保存到 D:/删除.json（2 条规则）');
  assert.equal(d.querySelectorAll('.table-scroll').length,d.querySelectorAll('.table-scroll > table').length);
  console.log('PASS: complete static UI, dynamic labels, language roundtrip, focus, byte values and user content');
  w.canI18n.dispose(); w.close();
})().catch(e=>{console.error(e);w.canI18n.dispose();w.close();process.exitCode=1;});
