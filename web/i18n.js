/* UI-only localization. Never translate input values, file names or frame data. */
(() => {
  const en = {
    'CAN 模拟收发工具':'CAN Test Workbench', '主题':'Theme', '语言':'Language', '版本':'Version',
    '深色':'Dark', '浅色':'Light', '跟随系统':'System', '主导航':'Main navigation',
    '未连接':'Disconnected', '已连接':'Connected', '总线':'Bus', '接收':'Receive', '发送':'Transmit',
    '故障模拟':'Fault simulation', '日志':'Files & logs', '触发':'Triggers',
    '连接':'Connect', '后端':'Interface', '通道':'Channel', '波特率':'Bit rate', '断开':'Disconnect',
    '文件保存路径（重启后仍生效）':'Storage locations', '日志目录':'Log folder', '配置目录':'Preset folder',
    '选择文件夹…':'Choose folder…', '应用':'Apply', '恢复默认':'Reset defaults',
    '点击“选择文件夹”后点“应用”。日志和配置存到新目录；旧文件保留在原目录。取消选择不改变路径。':'Choose a folder, then Apply. Existing files stay in their original folder. Cancel keeps the current path.',
    'DBC 报文库':'DBC database', '加载':'Load', '卸载':'Unload',
    '过滤：多节点用空格/逗号分隔（任一命中显示）；可限定字段如 sa:00 sa:49 pgn:FECA data:FFFF':'Filter by space/comma-separated terms (OR), e.g. sa:00 sa:49 pgn:FECA data:FFFF',
    '录制':'Record', '停止录制':'Stop recording', '锁定画面':'Freeze view', '解锁实时':'Resume live view',
    '清空':'Clear', '导出当前显示':'Export visible frames', '缓存':'Buffer', '实时接收缓存帧数':'Live receive buffer size',
    '退出回看':'Return to live', '时间':'Time', '方向':'Direction', '帧型':'Frame type', '优先级':'Priority', '数据':'Data', '解析':'Decoded',
    '报文统计（当前连接）':'Frame statistics · current connection',
    '按帧 ID 统计次数和相邻帧间隔；断开重连后自动清零。':'Counts and inter-frame intervals by ID. Reset when reconnecting.',
    '次数':'Count', '平均周期(ms)':'Mean period (ms)', '最小(ms)':'Min (ms)', '最大(ms)':'Max (ms)',
    '手动发送':'Single-frame transmission', '扩展帧':'Extended frame', '数据(按字节)':'Data bytes',
    '输满 2 位自动跳下一格；尾部留空 = 发短帧':'Two hex digits advance to the next byte. Leave trailing bytes empty for a short frame.',
    '周期发送任务':'Periodic transmitters', '名称':'Name', '周期(ms)':'Period (ms)', '模式':'Mode',
    '固定':'Fixed', '递增':'Increment', '列表循环':'Sequence', '随机／掩码随机':'Random / masked', '有界斜坡':'Bounded ramp',
    '递增字节(起~止)':'Byte range (start–end)', '步长':'Step', '添加并启动':'Add & start', '数据(hex)':'Data (hex)',
    '周期ms':'Period (ms)', '递增字节(起~止)/步长':'Byte range / step', '状态':'Status', '已发':'Sent', '操作':'Actions',
    '表格内可直接改数据/周期/模式（保存后生效，运行中修改下一周期生效）；递增模式 = 指定字节按步长自增，用于模拟计数器或变化的数值':'Edit data, period or mode in the table, then Save. Running tasks apply changes on the next cycle. Increment mode updates the selected bytes by the configured step.',
    '配置保存 / 读取（周期任务 + 故障模拟现场）':'Save & load · transmitters and fault setup',
    '自定义路径':'Selected file', '通过系统对话框选择文件':'Choose a file using the system dialog',
    '另存为…':'Save as…', '选择文件…':'Choose file…', '读取该文件':'Load selected file',
    '或存到配置目录':'Quick save to preset folder', '配置名':'Preset name', '保存到配置目录':'Save to preset folder',
    '读取':'Load', '删除':'Delete', '另存为：弹出系统窗口选择目录和文件名（本机运行可用）':'Save as opens the native dialog to choose a folder and file name (local use only).',
    '故障报文（节点 → DTC → 多包传输 → 打包预览 → 发送）':'Fault message setup', '节点 ID(hex)':'Node ID (hex)',
    '完整 29bit 仲裁 ID':'Full 29-bit arbitration ID',
    '下拉选模板或直接改 8 位 hex，各段含义见预览第一行':'Select a template or enter an 8-digit hex ID. Field meanings appear in the preview.',
    '发生次数':'Occurrence count', '+ 添加 DTC':'+ Add DTC',
    '1 个 DTC → 单包直发；≥ 2 个 DTC → J1939 TP.BAM 多包':'One DTC uses a single frame. Two or more use J1939 TP.BAM.',
    '多包 CM 节点 ID':'TP.CM node ID', 'DT 节点 ID':'TP.DT node ID',
    'TP.CM 通告帧完整 29bit ID':'Full 29-bit TP.CM announcement ID', 'TP.DT 数据帧完整 29bit ID':'Full 29-bit TP.DT data ID',
    '留空 = 自动跟随节点 ID（标准 TP：EC/ED + 优先级 + SA）':'Blank follows the node ID automatically (standard TP: EC/ED + priority + SA).',
    'MIL 灯':'MIL', '红灯':'Red lamp', '黄灯':'Amber lamp', '保护灯':'Protect lamp', 'OC 自动递增':'Auto-increment OC',
    '勾选后每个广播周期 DTC 发生次数 +1，数据随时间变化':'When enabled, each broadcast cycle increments DTC occurrence counts by one.',
    'J1939 打包结果预览':'J1939 frame preview', '单次发送':'Send once', '启动周期广播':'Start broadcast',
    '停止广播':'Stop broadcast', '预置场景':'Scenarios', '加载场景':'Load scenario',
    '打开文件与离线分析':'File analysis', '工作表（空=第一张）':'Sheet (blank = first)', 'ID 进制':'ID base',
    '十六进制':'Hexadecimal', '十进制':'Decimal', '时间单位':'Time unit', '打开并分析':'Open & analyze',
    '导出 JSON 分析报告':'Export JSON report',
    'CSV / TSV / XLSX / JSON：必需列 ts、id、data；可选 extended、dir、dlc、channel。data 为十六进制文本，默认 RX；未指定帧类型时按 ID 范围推断（低 ID 扩展帧须填写 extended=1）。Excel 不执行公式，请先转成值。ASC 支持经典 CAN 数据帧、hex/absolute。上限 20 MiB / 10 万行。不发送报文，不修改原文件。':'CSV / TSV / XLSX / JSON require ts, id and data; optional: extended, dir, dlc, channel. Data is hex text; direction defaults to RX. Frame type is inferred from ID unless specified (low-ID extended frames require extended=1). Convert Excel formulas to values first. ASC: classic CAN data frames, hex/absolute. Limit: 20 MiB / 100,000 rows. Import does not transmit or modify the source file.',
    '请选择文件。':'Choose a file to begin.', '报文分组':'Frame group', '全部':'All',
    '通道 / ID / 类型 / 方向':'Channel / ID / type / direction', '帧数':'Frames', '周期均值 ms':'Mean period (ms)',
    '最小 ms':'Min (ms)', '最大 ms':'Max (ms)', '数据变化次数':'Data changes', '时间倒退次数':'Backward timestamps',
    '周期按同通道、ID、帧类型、方向的文件顺序计算；负间隔计入时间倒退，不参与周期统计。变化次数是相邻有效报文的比较，不代表故障判定。':'Periods follow file order within each channel, ID, type and direction. Negative intervals count as backward timestamps and are excluded from period statistics. Changes compare adjacent valid frames; they are not fault diagnoses.',
    '上一页':'Previous', '下一页':'Next', '原始行':'Source row', '时间 s':'Time (s)', '类型':'Type',
    '无效记录（不参与统计）':'Invalid records (excluded from statistics)', '记录':'Recording', '格式':'Format',
    'CSV（支持回放）':'CSV (replay supported)', '开始记录':'Start recording', '停止记录':'Stop recording',
    '打开任意路径的日志（回看）':'View a log file', '完整 CSV 文件路径':'Full CSV file path', '浏览…':'Browse…', '查看':'View',
    '加载到接收页离线分析，不限日志目录':'View in the Receive page; files may be outside the log folder.',
    '日志文件':'Log files', '回放倍速':'Replay speed', '停止回放':'Stop replay',
    '回放会按记录的时间间隔把帧重新发到总线':'Replay transmits frames to the bus at the recorded intervals.',
    '文件':'File', '大小':'Size', '新建触发规则':'New trigger rule', '修改触发规则':'Edit trigger rule',
    'PGN(十进制)':'PGN (decimal)', '数据含(hex)':'Contains data (hex)', '动作':'Action', '高亮显示':'Highlight',
    '计数':'Count', '自动发帧':'Send response', '数据条件(字节/位)':'Byte / bit conditions',
    '多条件关系':'Condition operator', '全部满足 AND':'AND · all conditions', '任一满足 OR':'OR · any condition',
    '无':'None', '单字节 比较值':'Byte comparison', '字节区间(小端) 比较':'Byte range (little-endian)',
    '单个 bit = 0/1':'Single bit = 0/1', '位段(字节内) = 值':'Bit field = value',
    '+ 添加条件':'+ Add condition', '取消条件修改':'Cancel condition edit', '回应 ID(hex)':'Response ID (hex)',
    '添加规则':'Add rule', '取消修改':'Cancel edit', '回应数据(按字节)':'Response bytes', '规则列表':'Trigger rules',
    '匹配':'Match', '命中':'Hits', '启用':'Enable', '全部启用':'Enable all', '全部禁用':'Disable all',
    '清零命中计数':'Reset hit counts', '规则保存 / 读取':'Save & load rules', '规则集名':'Rule set name',
    '读取 = 整体替换当前规则列表':'Loading replaces the current rule list.', '保存':'Save', '保存修改':'Save changes',
    '保存条件修改':'Save condition changes', '编辑':'Edit', '禁用':'Disable', '复制':'Duplicate', '启动':'Start', '停止':'Stop',
    '运行中':'Running', '发送失败':'Transmit failed', '暂无周期任务':'No periodic transmitters', '暂无统计数据':'No statistics yet',
    '暂无规则':'No trigger rules', '暂无日志':'No log files', '暂无保存的配置':'No saved presets', '暂无保存的规则集':'No saved rule sets',
    '扩展':'Extended', '标准':'Standard', '是':'Yes', '否':'No', '高亮':'Highlight', '下载':'Download', '回放':'Replay',
    '灭':'Off', '亮':'On', '闪烁':'Blink', '不可用':'Unavailable', '自定义':'Custom',
    '实时接收已连接':'Live stream connected', '已锁定当前画面（后台仍在接收）':'View frozen; reception continues in the background',
    '实时接收连接已断开，正在重连…':'Live stream disconnected; reconnecting…', '已断开':'Disconnected',
    '先选择 DBC 文件':'Choose a DBC file first', '加载失败':'Load failed', '已保存，下一周期生效':'Saved; applies on the next cycle',
    '已复制任务（副本默认停止）':'Transmitter duplicated (stopped)', '已删除':'Deleted', '未回放':'No replay', '已停止回放':'Replay stopped',
    '已恢复实时接收':'Live reception resumed', '规则已不存在，请刷新后重试':'Rule no longer exists. Refresh and retry.',
    '先选择条件类型':'Choose a condition type first', '条件数值不能为空或无效':'Enter valid condition values',
    '请先保存或取消当前条件修改':'Save or cancel the condition edit first', '规则已修改':'Rule updated', '规则已添加':'Rule added',
    '已全部启用触发器':'All triggers enabled', '已全部禁用触发器':'All triggers disabled',
    '已清零触发器命中计数':'Trigger hit counts reset', '已恢复默认路径':'Default folders restored',
    '没有可读取的配置':'No preset to load', '没有可读取的规则集':'No rule set to load',
    '选择一个报文分组查看各字节统计（十进制）。':'Select a frame group to inspect byte statistics (decimal).',
    '请先选择文件':'Choose a file first', '文件超过 20 MiB，请先拆分':'File exceeds 20 MiB. Split it first.',
    '正在读取和分析…':'Reading and analyzing…', '无匹配条件':'No match filters', '○ 未运行':'○ Stopped',
    '数据列表（每行一帧，空帧写 -）':'Sequence (one frame per line; - for an empty frame)', '循环数据列表':'Frame sequence',
    '种子':'Seed', '掩码(hex)':'Mask (hex)', '空=全部随机，1位随机化':'Blank: randomize all bits; 1 bits are randomized',
    '下限':'Minimum', '上限':'Maximum',
    '字节[':'Byte [', '起[':'Start [', ']~止[':']–end [', '值(hex)[':'Value (hex) [',
    'bit序号0-63[':'Bit index 0–63 [', '] 位[':'] bits [', '] = 值[':'] = value [',
    'OR 任一满足':'OR · any condition', 'AND 全部满足':'AND · all conditions', '默认':'Default',
    '发动机#1 · DM1 当前故障（18FECA00）':'Engine #1 · DM1 active faults (18FECA00)',
    '发动机#1 · DM2 历史故障（18FECB00）':'Engine #1 · DM2 previously active faults (18FECB00)',
    '尾气后处理#1 · DM1（18FECA49）':'Aftertreatment #1 · DM1 (18FECA49)',
    '发动机#1 · 私有B 广播（18FF0000）':'Engine #1 · Proprietary B (18FF0000)',
    '发动机#1 → 仪表 · 私有A 点对点（0CEF1700）':'Engine #1 → instrument · Proprietary A (0CEF1700)',
    'DA 目标地址':'DA destination', 'PS/GE 组扩展':'PS/GE group extension', 'SA 源地址（':'SA source (',
    'PDU1 点对点':'PDU1 peer-to-peer', 'PDU2 广播':'PDU2 broadcast',
    '无 DTC 时发送"无故障"DM1（FF FF FF FF ...）':'Without DTCs, sends a no-fault DM1 (FF FF FF FF ...)',
    '多包 BAM：优先级':'Multi-packet BAM: priority', '已生效':'applied', '；CM 通告帧':'; CM announcement',
    '原始 PGN':'Original PGN', '在 CM 通告字节中传输，接收端重组后还原为完整报文':'is carried in CM bytes and reconstructed at the receiver.',
  };
  // Captures are opaque user data, never recursively translated.
  const patterns = [
    [/^后端: (.*)  通道: (.*)\n接收: (.*)  发送: (.*)  错误帧: (.*)  在线: (.*)s$/, (_,a,b,c,d,e,f) => `Interface: ${a}  Channel: ${b}\nRX: ${c}  TX: ${d}  Error frames: ${e}  Uptime: ${f}s`],
    [/^收 (\d+) \/ 发 (\d+)(.*)$/, (_,a,b,c) => `RX ${a} / TX ${b}${c.replace('错误','Errors').replace('回放','Replay')}`],
    [/^发(扩展|标准)帧 (.*)$/, (_,a,b) => `Send ${a === '扩展' ? 'extended' : 'standard'} frame ${b}`],
    [/^数据含 (.*)$/, (_,a) => `Data contains ${a}`],
    [/^条件 (.*)$/, (_,a) => `Conditions ${a.replaceAll(' 且 ',' AND ').replaceAll(' 或 ',' OR ')}`],
    [/^显示 (\d+) \/ 已冻结 (\d+)（实时缓存 (\d+)）$/, (_,a,b,c) => `Showing ${a} / frozen ${b} (live buffer ${c})`],
    [/^显示 (\d+) \/ 缓冲 (\d+)$/, (_,a,b) => `Showing ${a} / buffered ${b}`],
    [/^已加条件（(OR 任一满足|AND 全部满足)；字节序号从 0 开始）：$/, (_,a) => `Conditions (${a.startsWith('OR') ? 'OR · any' : 'AND · all'}; byte indices start at 0):`],
    [/^(\d+) \/ (\d+) 页，共 (\d+) 帧$/, (_,a,b,c) => `${a} / ${b} pages, ${c} frames`],
    [/^已连接 (.*)$/, (_,a) => `Connected to ${a}`],
    [/^无法连接后端：(.*)$/, (_,a) => `Cannot connect to backend: ${a}`],
    [/^已加载 (.*)（(\d+) 条报文）$/, (_,a,b) => `Loaded ${a} (${b} messages)`],
    [/^已导出 (\d+) 帧$/, (_,a) => `Exported ${a} frames`],
    [/^已记录 (\d+) 帧$/, (_,a) => `Recorded ${a} frames`],
    [/^已保存 (.*)（(\d+) 帧）→ 日志页可查看\/下载$/, (_,a,b) => `Saved ${a} (${b} frames). View on Files & logs.`],
    [/^(开始录制 → |开始记录：|记录中 → )(.*)$/, (_,a,b) => `Recording → ${b}`],
    [/^已保存到 (.*)（(\d+) 任务 \+ 故障配置）$/, (_,a,b) => `Saved to ${a} (${b} transmitters + fault setup)`],
    [/^已保存「(.*)」：(\d+) 个任务 \+ 故障配置$/, (_,a,b) => `Saved “${a}”: ${b} transmitters + fault setup`],
    [/^已从文件恢复 (\d+) 个任务 \+ 故障配置$/, (_,a) => `Loaded ${a} transmitters + fault setup from file`],
    [/^已恢复 (\d+) 个周期任务 \+ 故障配置$/, (_,a) => `Loaded ${a} transmitters + fault setup`],
    [/^已保存到 (.*)（(\d+) 条规则）$/, (_,a,b) => `Saved to ${a} (${b} rules)`],
    [/^已保存「(.*)」：(\d+) 条规则$/, (_,a,b) => `Saved “${a}”: ${b} rules`],
    [/^已从文件恢复 (\d+) 条规则$/, (_,a) => `Loaded ${a} rules from file`],
    [/^已恢复 (\d+) 条规则$/, (_,a) => `Loaded ${a} rules`],
    [/^已加载场景：(.*)$/, (_,a) => `Loaded scenario: ${a}`],
    [/^已按 J1939 打包发送 (\d+) 帧$/, (_,a) => `Transmitted ${a} J1939 frames`],
    [/^● 周期广播中（已发 (\d+) 帧）$/, (_,a) => `● Broadcasting (${a} frames sent)`],
    [/^错误：(.*)$/, (_,a) => `Error: ${a}`],
    [/^回放中 (\d+)\/(\d+)$/, (_,a,b) => `Replaying ${a}/${b}`],
    [/^已停止 (\d+)\/(\d+)$/, (_,a,b) => `Stopped ${a}/${b}`],
    [/^已完成 (\d+)\/(\d+)$/, (_,a,b) => `Completed ${a}/${b}`],
    [/^回放 (\d+) 帧（(.*)x）$/, (_,a,b) => `Replaying ${a} frames (${b}x)`],
    [/^回看 (.*)（(\d+) 帧，已停实时更新）$/, (_,a,b) => `Viewing ${a} (${b} frames; live updates off)`],
    [/^已加载 (\d+) 帧到接收页$/, (_,a) => `Loaded ${a} frames into Receive`],
    [/^已删除日志：(.*)$/, (_,a) => `Deleted log: ${a}`],
    [/^路径已应用并保存：日志 → (.*)$/, (_,a) => `Folders saved. Logs → ${a}`],
    [/^分析失败：(.*)$/, (_,a) => `Analysis failed: ${a}`],
  ];
  function englishText(source) {
    if (en[source]) return en[source];
    for (const [pattern, replacement] of patterns) if (pattern.test(source)) return source.replace(pattern, replacement);
    return source;
  }
  let language = 'zh-CN';
  try { language = localStorage.getItem('can-sim-language') === 'en' ? 'en' : 'zh-CN'; } catch (_) {}
  const bindings = new WeakMap();
  const attributes = new WeakMap();
  // Dynamic cells contain user-controlled names and decoded data. Only UI controls
  // and explicitly marked UI spans inside these cells are eligible for translation.
  function excluded(el) {
    if (!el || el.closest('script,style,textarea,[data-user-content],#language-select,#dbc-msgs,#analysis-errors,#scn-desc,#iface-desc')) return true;
    if (el.closest('#analysis-group') && !el.matches('option[value=""]')) return true;
    if (el.closest('#preset-select,#trig-preset-select,#scn-select')) return true;
    return !!el.closest('tbody') && !el.closest('button,a,select,label,[data-ui]');
  }
  function translateText(node) {
    if (excluded(node.parentElement)) return;
    const current = node.nodeValue;
    let record = bindings.get(node);
    if (!record || current !== record.output) record = {source: current};
    const trimmed = record.source.trim();
    const translated = language === 'en' ? englishText(trimmed) : undefined;
    const output = translated ? record.source.replace(trimmed, translated) : record.source;
    record.output = output;
    bindings.set(node, record);
    if (current !== output) node.nodeValue = output;
  }
  function translateElement(el) {
    if (excluded(el)) return;
    let records = attributes.get(el);
    if (!records) { records = {}; attributes.set(el, records); }
    for (const key of ['placeholder','title','aria-label']) {
      const value = el.getAttribute(key);
      if (value === null) continue;
      let record = records[key];
      if (!record || value !== record.output) record = {source:value};
      record.output = language === 'en' ? en[record.source] || record.source : record.source;
      records[key] = record;
      if (value !== record.output) el.setAttribute(key, record.output);
    }
  }
  function translate(root) {
    if (root.nodeType === 3) { translateText(root); return; }
    if (root.nodeType !== 1 && root.nodeType !== 9) return;
    if (root.nodeType === 1) translateElement(root);
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_ELEMENT | NodeFilter.SHOW_TEXT, {
      acceptNode: node => node.nodeType === 1 && node.matches('script,style,textarea,#rx-body,#analysis-frames') ? NodeFilter.FILTER_REJECT : NodeFilter.FILTER_ACCEPT,
    });
    while (walker.nextNode()) {
      const node = walker.currentNode;
      if (node.nodeType === 3) translateText(node); else translateElement(node);
    }
  }
  // Observe changed UI fragments only; never traverse the high-rate receive body.
  const observer = new MutationObserver(records => {
    observer.disconnect();
    for (const record of records) {
      const target = record.target.nodeType === 1 ? record.target : record.target.parentElement;
      if (target?.closest('#rx-body,#analysis-frames')) continue;
      if (record.type === 'childList') record.addedNodes.forEach(translate);
      else if (record.type === 'characterData') translateText(record.target);
      else translateElement(record.target);
    }
    observe();
  });
  function observe() { observer.observe(document.body, {childList:true, subtree:true, characterData:true, attributes:true, attributeFilter:['placeholder','title','aria-label']}); }
  window.canI18n = {
    en,
    dispose() { observer.disconnect(); },
    get language() { return language; },
    text(zh, english) { return language === 'en' ? english || englishText(zh) : zh; },
    setLanguage(value) {
      if (!['zh-CN','en'].includes(value)) return;
      language = value;
      try { localStorage.setItem('can-sim-language', language); } catch (_) {}
      observer.disconnect(); translate(document.documentElement); observe();
      document.documentElement.lang = language;
      document.getElementById('language-select').value = language;
      document.querySelectorAll('[data-frame-type]').forEach(el => {
        el.textContent = window.canI18n.text(el.dataset.frameType === 'extended' ? '扩展' : '标准');
      });
      window.dispatchEvent(new Event('can-language-change'));
    },
  };
  document.getElementById('language-select').addEventListener('change', e => window.canI18n.setLanguage(e.target.value));
  // Scrolling belongs to tables, not the entire page. Do not recreate their inputs.
  document.querySelectorAll('.card > table').forEach(table => {
    const wrap = document.createElement('div'); wrap.className = 'table-scroll';
    table.before(wrap); wrap.append(table);
  });
  document.querySelectorAll('.form-row > label').forEach(label => {
    const control = label.nextElementSibling;
    if (label.querySelector('input,select') || !control?.matches('input[id],select[id]')) return;
    label.htmlFor = control.id;
    const field = document.createElement('div'); field.className = 'field';
    label.before(field); field.append(label, control);
  });
  window.canI18n.setLanguage(language);
})();
