(() => {
  const el = id => document.getElementById(`analysis-${id}`);
  const tr = (zh, en) => globalThis.canI18n?.text(zh, en) || zh;
  let result = null, page = 0;
  const size = 100;
  const fmt = n => n == null ? '—' : Number(n.toFixed(6)).toString();
  const label = g => `${g.channel || tr('默认','Default')} / ${g.id} / ${g.ext ? tr('扩展','Extended') : tr('标准','Standard')} / ${g.dir}`;
  const cells = values => `<tr>${values.map(v => `<td>${esc(String(v))}</td>`).join('')}</tr>`;
  function render() {
    if (!result) return;
    const selected = el('group').value;
    const group = selected === '' ? null : result.stats[Number(selected)];
    const frames = group ? result.frames.filter(f => f.id === group.id && f.ext === group.ext && f.dir === group.dir && f.channel === group.channel) : result.frames;
    const pages = Math.max(1, Math.ceil(frames.length / size));
    page = Math.min(page, pages - 1);
    el('page').textContent = tr(`${page + 1} / ${pages} 页，共 ${frames.length} 帧`, `${page + 1} / ${pages} pages, ${frames.length} frames`);
    el('prev').disabled = page === 0;
    el('next').disabled = page === pages - 1;
    el('stats').innerHTML = (group ? [group] : result.stats).map(g => cells([label(g), g.count, fmt(g.period_mean_ms), fmt(g.period_min_ms), fmt(g.period_max_ms), g.changes, g.backwards])).join('');
    el('frames').innerHTML = frames.slice(page * size, (page + 1) * size).map(f => cells([f.row, f.ts, f.channel, f.id, f.ext ? tr('扩展','Extended') : tr('标准','Standard'), f.dir, f.dlc, f.data.match(/../g)?.join(' ') || ''])).join('');
    el('bytes').textContent = group ? group.bytes.map(b => tr(`Byte${b.byte}：最小 ${b.min ?? '—'}，最大 ${b.max ?? '—'}，变化 ${b.changes} 次`, `Byte${b.byte}: min ${b.min ?? '—'}, max ${b.max ?? '—'}, changes ${b.changes}`)).join('; ') : tr('选择一个报文分组查看各字节统计（十进制）。');
  }
  function summary() {
    if (!result) return;
    const d = result;
    el('status').textContent = tr(`${d.file}：有效 ${d.count} / 总记录 ${d.total}，无效 ${d.errors.length}，时长 ${fmt(d.duration_s)} s。`, `${d.file}: valid ${d.count} / total ${d.total}, invalid ${d.errors.length}, duration ${fmt(d.duration_s)} s.`) + (d.sheets.length ? tr(` 工作表：${d.sheets.join('、')}；当前：${d.sheet}`, ` Sheets: ${d.sheets.join(', ')}; current: ${d.sheet}`) : '');
    el('errors').textContent = d.errors.map(e => tr(`第 ${e.row} 行：${e.error}`, `Row ${e.row}: ${e.error}`)).join('\n') || tr('无');
  }
  globalThis.addEventListener?.('can-language-change', () => {
    if (!result) return;
    for (let i = 0; i < result.stats.length; i++) el('group').options[i+1].textContent = label(result.stats[i]);
    el('group').options[0].textContent = tr('全部','All');
    summary(); render();
  });
  el('open').onclick = async () => {
    const file = el('file').files[0];
    if (!file) { el('status').textContent = '请先选择文件'; return; }
    if (file.size > 20 * 1024 * 1024) { el('status').textContent = '文件超过 20 MiB，请先拆分'; return; }
    el('open').disabled = true;
    el('export').disabled = true;
    result = null;
    ['stats', 'frames', 'bytes', 'errors', 'page'].forEach(id => el(id).textContent = '');
    el('group').innerHTML = '<option value="">全部</option>';
    el('status').textContent = '正在读取和分析…';
    try {
      const body = new FormData();
      body.append('file', file);
      body.append('sheet', el('sheet').value.trim());
      body.append('id_base', el('base').value);
      body.append('time_unit', el('unit').value);
      const response = await fetch('/api/files/analyze', {method: 'POST', body});
      const data = await response.json();
      if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail));
      result = data; page = 0;
      summary();
      data.stats.forEach((g, i) => el('group').add(new Option(label(g), String(i))));
      el('export').disabled = false;
      render();
    } catch (error) { el('status').textContent = `分析失败：${error.message}`; }
    finally { el('open').disabled = false; }
  };
  el('group').onchange = () => { page = 0; render(); };
  el('prev').onclick = () => { page = Math.max(0, page - 1); render(); };
  el('next').onclick = () => { page++; render(); };
  el('export').onclick = () => {
    if (!result) return;
    const url = URL.createObjectURL(new Blob([JSON.stringify(result, null, 2)], {type:'application/json'}));
    const a = document.createElement('a'); a.href = url; a.download = `${result.file}.analysis.json`; a.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  };
})();
