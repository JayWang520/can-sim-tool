/* CAN 模拟收发工具 前端逻辑（原生 JS，无构建） */
"use strict";

const $ = (id) => document.getElementById(id);
const LAMP_OPTS = [["off", "灭"], ["on", "亮"], ["blink", "闪烁"], ["na", "不可用"]];

// ---------------------------------------------------------------- utils
function toast(msg, isError = false) {
  const el = $("toast");
  el.textContent = msg;
  el.className = "toast show" + (isError ? " error" : "");
  clearTimeout(el._t);
  el._t = setTimeout(() => (el.className = "toast"), 2500);
}

async function api(path, method = "GET", body = null) {
  const opts = { method };
  if (body !== null) opts.body = JSON.stringify(body);
  if (body !== null) opts.headers = { "Content-Type": "application/json" };
  let r;
  try {
    r = await fetch(path, opts);
  } catch (err) {
    toast(`无法连接后端：${err.message || "网络错误"}`, true);
    throw err;
  }
  const data = await r.json().catch(() => ({}));
  if (!r.ok) {
    const msg = data.detail || r.statusText;
    toast(`${path}: ${msg}`, true);
    throw new Error(msg);
  }
  return data;
}

function hexGroup(hex) {
  return (hex || "").replace(/(..)/g, "$1 ").trim();
}
function esc(s) {
  return String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
}

// ------------------------------------------------ 按字节编辑器
function renderByteEditor(el, value = "0000000000000000", onChange = null) {
  el.classList.add("byte-editor");
  const hex = value.padEnd(16, "0");
  el.innerHTML = Array.from({ length: 8 }, (_, i) =>
    `<div class="byte-cell"><input data-i="${i}" maxlength="2" value="${hex.substr(i * 2, 2).toUpperCase()}"><label>${i}</label></div>`
  ).join("");
  el.querySelectorAll("input").forEach((inp) => {
    if (onChange) inp.addEventListener("change", onChange);
  });
}

// 所有动态生成的 byte 输入统一在事件委托中处理，避免触发器表格里的输入框漏绑逻辑。
document.addEventListener("focusin", (e) => {
  if (e.target.matches(".byte-editor input")) e.target.select();
});
document.addEventListener("pointerup", (e) => {
  if (!e.target.matches(".byte-editor input")) return;
  // 鼠标默认动作可能覆盖 focusin 的全选，抬键后再次全选当前 byte。
  e.preventDefault();
  e.target.select();
});
function insertByteText(inp, text) {
  const start = inp.selectionStart ?? inp.value.length;
  const end = inp.selectionEnd ?? start;
  const value = (inp.value.slice(0, start) + text + inp.value.slice(end)).slice(0, 2);
  inp.value = value;
  inp.setSelectionRange(value.length, value.length);
  // 第二位已经写入当前 byte 后，才移动光标；字符本身绝不进入下一个 byte。
  if (text && value.length === 2) {
    const editor = inp.closest(".byte-editor");
    const next = editor && editor.querySelector(`input[data-i="${+inp.dataset.i + 1}"]`);
    if (next) {
      next.focus();
      next.select();
      return next;
    }
  }
  return inp;
}
function insertByteSequence(inp, text) {
  const chars = text.replace(/[^0-9a-fA-F]/g, "").toUpperCase();
  for (const char of chars) inp = insertByteText(inp, char);
}
document.addEventListener("keydown", (e) => {
  if (!e.target.matches(".byte-editor input") || !/^[0-9a-fA-F]$/.test(e.key)) return;
  // 一次物理按键只写一个字符；阻止后续 beforeinput/input 再次重复写入。
  e.preventDefault();
  if (e.repeat) return;
  // 部分浏览器在 preventDefault 后仍派发 beforeinput，用标记避免同一按键处理两次。
  e.target._byteKeyHandled = true;
  setTimeout(() => { e.target._byteKeyHandled = false; }, 0);
  insertByteSequence(e.target, e.key);
});
document.addEventListener("beforeinput", (e) => {
  if (!e.target.matches(".byte-editor input") || !e.inputType.startsWith("insert")) return;
  e.preventDefault();
  if (e.target._byteKeyHandled) return;
  insertByteSequence(e.target, e.data || "");
});
document.addEventListener("paste", (e) => {
  if (!e.target.matches(".byte-editor input")) return;
  e.preventDefault();
  insertByteSequence(e.target, e.clipboardData.getData("text"));
});
document.addEventListener("input", (e) => {
  if (!e.target.matches(".byte-editor input")) return;
  // 移动端/输入法兜底：同样只保留当前 byte 的前两位。
  e.target.value = e.target.value.replace(/[^0-9a-fA-F]/g, "").toUpperCase().slice(0, 2);
});

function getByteHex(el) {
  const vals = [...el.querySelectorAll("input")].map((i) => i.value.trim());
  while (vals.length && vals[vals.length - 1] === "") vals.pop();  // 尾部空 = 短帧
  return vals.map((v) => (v || "0").padStart(2, "0")).join("");
}

function byteInputsHtml(hex) {
  const h = (hex || "").padEnd(16, "0");
  return `<div class="byte-editor compact">` + Array.from({ length: 8 }, (_, i) =>
    `<div class="byte-cell"><input data-i="${i}" maxlength="2" value="${h.substr(i * 2, 2).toUpperCase()}"></div>`
  ).join("") + `</div>`;
}

// ---------------------------------------------------------------- tabs
document.querySelectorAll(".tab").forEach((btn) => {
  btn.onclick = () => {
    document.querySelectorAll(".tab,.panel").forEach((el) => el.classList.remove("active"));
    btn.classList.add("active");
    $(btn.dataset.tab).classList.add("active");
  };
});

// ---------------------------------------------------------------- 总线
const CHANNEL_HINTS = {
  virtual: "test", socketcan: "can0", pcan: "PCAN_USBBUS1",
  canalystii: "0", slcan: "COM3 或 /dev/ttyUSB0", kvaser: "0", ixxat: "0",
};

async function loadInterfaces() {
  const ifs = await api("/api/interfaces");
  const sel = $("bus-iface");
  sel.innerHTML = Object.entries(ifs).map(([k, v]) => `<option value="${k}">${k} — ${v}</option>`).join("");
  sel.onchange = () => {
    $("bus-channel").value = CHANNEL_HINTS[sel.value] || "";
    $("iface-desc").textContent = ifs[sel.value] || "";
  };
  try {
    const saved = JSON.parse(localStorage.getItem("can-sim-connection") || "null");
    if (saved && ifs[saved.interface]) {
      sel.value = saved.interface;
      $("bus-channel").value = saved.channel || CHANNEL_HINTS[sel.value] || "";
      $("bus-bitrate").value = saved.bitrate || 250000;
    }
  } catch (e) { /* 忽略损坏的本地配置 */ }
  $("iface-desc").textContent = ifs[sel.value];
}

$("btn-connect").onclick = async () => {
  try {
    const info = await api("/api/connect", "POST", {
      interface: $("bus-iface").value,
      channel: $("bus-channel").value,
      bitrate: parseInt($("bus-bitrate").value) || 250000,
    });
    localStorage.setItem("can-sim-connection", JSON.stringify({
      interface: $("bus-iface").value,
      channel: $("bus-channel").value,
      bitrate: parseInt($("bus-bitrate").value) || 250000,
    }));
    toast(`已连接 ${$("bus-iface").value}/${$("bus-channel").value}`);
    renderBusInfo(info);
  } catch (e) { /* toast 已提示 */ }
};

$("btn-disconnect").onclick = async () => {
  await api("/api/disconnect", "POST");
  toast("已断开");
};

function renderBusInfo(info) {
  const s = info.stats || {};
  $("bus-info").textContent =
    `后端: ${info.interface || "-"}  通道: ${info.channel || "-"}\n` +
    `接收: ${s.received ?? 0}  发送: ${s.sent ?? 0}  错误帧: ${s.error_frames ?? 0}  在线: ${s.uptime_s ?? 0}s`;
}

// DBC
$("btn-dbc-load").onclick = async () => {
  const f = $("dbc-file").files[0];
  if (!f) return toast("先选择 DBC 文件", true);
  const fd = new FormData();
  fd.append("file", f);
  const r = await fetch("/api/dbc", { method: "POST", body: fd });
  const data = await r.json();
  if (!r.ok) return toast(data.detail || "加载失败", true);
  $("dbc-status").textContent = `已加载 ${data.file}（${data.messages.length} 条报文）`;
  $("dbc-msgs").innerHTML = data.messages.map((m) =>
    `<div class="msg"><b>${m.name}</b> ${m.id_hex} (${m.length}B)：` +
    m.signals.map((s) => `${s.name}${s.unit ? "(" + s.unit + ")" : ""}`).join(", ") + "</div>"
  ).join("");
};
$("btn-dbc-unload").onclick = async () => {
  await api("/api/dbc", "DELETE");
  $("dbc-status").textContent = "";
  $("dbc-msgs").innerHTML = "";
};

// 接收页录制快捷开关（与日志页"记录"同一功能）
$("btn-rx-rec").onclick = async () => {
  if (window._recording) {
    const info = await api("/api/log/stop", "POST");
    window._recording = false;
    toast(`已保存 ${info.file}（${info.frames} 帧）→ 日志页可查看/下载`);
    refreshLogs();
  } else {
    const info = await api("/api/log/start", "POST", { format: "csv" });
    window._recording = true;
    toast(`开始录制 → ${info.file}`);
  }
  syncRecButton();
};
function syncRecButton() {
  const b = $("btn-rx-rec");
  b.textContent = window._recording ? "停止录制" : "录制";
  b.classList.toggle("on", !!window._recording);
  b.classList.toggle("danger", !!window._recording);
}

// ---------------------------------------------------------------- 接收 WS
let paused = false;
let frames = [];          // 环形缓冲
let frozenFrames = null;  // 暂停查看时的固定快照
let offlineView = null;   // 日志回看模式：文件名；null=实时
let maxFrames = 800;
let rxSocket = null;
let rxReconnectTimer = null;

function setReceiveBufferSize(value, persist = true) {
  maxFrames = Math.min(10000, Math.max(100, parseInt(value, 10) || 800));
  $("rx-buffer-size").value = maxFrames;
  if (persist) localStorage.setItem("can-sim-rx-buffer", String(maxFrames));
  if (frames.length > maxFrames) frames = frames.slice(-maxFrames);
  dirty = true;
}

const savedRxBuffer = localStorage.getItem("can-sim-rx-buffer");
if (savedRxBuffer) setReceiveBufferSize(savedRxBuffer, false);
$("rx-buffer-size").addEventListener("change", (e) => setReceiveBufferSize(e.target.value));

function connectWs() {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  if (rxSocket && (rxSocket.readyState === WebSocket.OPEN || rxSocket.readyState === WebSocket.CONNECTING)) return;
  const ws = new WebSocket(`${proto}://${location.host}/ws`);
  rxSocket = ws;
  ws.onopen = () => {
    if (!offlineView) $("rx-mode").textContent = paused ? "已锁定当前画面（后台仍在接收）" : "实时接收已连接";
  };
  ws.onmessage = (ev) => {
    if (offlineView) return;  // 回看时不混入实时帧
    const f = JSON.parse(ev.data);
    frames.push(f);
    if (frames.length > maxFrames) frames.splice(0, frames.length - maxFrames);
    dirty = true;
  };
  ws.onclose = () => {
    if (rxSocket !== ws) return;
    rxSocket = null;
    if (!offlineView) $("rx-mode").textContent = "实时接收连接已断开，正在重连…";
    if (!rxReconnectTimer) {
      rxReconnectTimer = setTimeout(() => {
        rxReconnectTimer = null;
        connectWs();
      }, 1500);
    }
  };
}

let dirty = true;
setInterval(() => {
  if (!dirty || paused) return;
  dirty = false;
  renderFrames();
}, 150);

function decodedText(f) {
  const tpText = f.tp && f.tp.complete ? `TP重组 PGN${f.tp.pgn}，${f.tp.length}字节` : "";
  const fault = f.dm1 || f.dm2;
  if (fault) {
    const lamps = fault.lamps;
    const lampStr = ["mil", "red", "amber", "protect"]
      .filter((k) => lamps[k] > 0).map((k) => `${k}=${lamps[k]}`).join(" ") || "无灯";
    const dtcs = fault.dtcs.map((d) => `SPN${d.spn}/FMI${d.fmi}×${d.oc}`).join(" ");
    return `${tpText ? tpText + "；" : ""}${f.dm2 ? "DM2" : "DM1"}: ${lampStr} ${dtcs}`;
  }
  if (f.decoded && f.decoded.signals) {
    const sigs = Object.entries(f.decoded.signals).map(([k, v]) => `${k}=${v}`).join(" ");
    return `${tpText ? tpText + "；" : ""}${f.decoded.message}: ${sigs}`;
  }
  return tpText;
}

// 多关键字过滤：空格/逗号/分号分隔，任一命中即显示；支持 id:/pgn:/sa:/da:/data: 限定字段
function frameMatches(f, raw) {
  let field = null, kw = raw;
  const m = kw.match(/^(id|pgn|sa|da|data):(.+)$/i);
  if (m) { field = m[1].toUpperCase(); kw = m[2]; }
  kw = kw.replace(/^0x/i, "").replace(/\s/g, "").toUpperCase();
  if (!kw) return true;
  const pgnHex = f.pgn != null ? f.pgn.toString(16).toUpperCase() : "";
  const saHex = f.sa != null ? f.sa.toString(16).toUpperCase().padStart(2, "0") : "";
  const daHex = f.da != null ? f.da.toString(16).toUpperCase().padStart(2, "0") : "";
  const cand = {
    ID: [f.id], PGN: [String(f.pgn ?? ""), pgnHex],
    SA: [String(f.sa ?? ""), saHex], DA: [String(f.da ?? ""), daHex],
    DATA: [f.data],
  }[field] || [f.id, String(f.pgn ?? ""), pgnHex, String(f.sa ?? ""), saHex, String(f.da ?? ""), daHex, f.data];
  return cand.some((v) => v && v.includes(kw));
}

function renderFrames() {
  const keywords = $("rx-filter").value.split(/[,，;；\s]+/).filter(Boolean);
  const body = $("rx-body");
  const source = frozenFrames || frames;
  const view = source.filter((f) => !keywords.length || keywords.some((k) => frameMatches(f, k)));
  const rows = view.slice(-300).reverse().map((f) => {
    const hl = f.highlight && f.highlight.length ? ' class="hl"' : "";
    const dec = decodedText(f);
    return `<tr${hl}><td>${(f.ts || 0).toFixed(3)}</td>` +
      `<td class="dir-${f.dir}">${f.dir.toUpperCase()}</td>` +
      `<td>${f.ext ? "扩展" : "标准"}</td>` +
      `<td>${f.id}</td><td>${f.pgn ?? "-"}</td><td>${f.sa ?? "-"}</td>` +
      `<td>${f.da ?? "-"}</td><td>${f.prio ?? "-"}</td><td>${f.dlc}</td>` +
      `<td>${hexGroup(f.data)}</td>` +
      `<td class="hint">${esc(dec)}${f.error ? '<span class="err"> ERROR</span>' : ""}</td></tr>`;
  });
  body.innerHTML = rows.join("");
  $("rx-count").textContent = frozenFrames
    ? `显示 ${Math.min(view.length, 300)} / 已冻结 ${frozenFrames.length}（实时缓存 ${frames.length}）`
    : `显示 ${Math.min(view.length, 300)} / 缓冲 ${frames.length}`;
}

$("btn-rx-pause").onclick = () => {
  paused = !paused;
  $("btn-rx-pause").textContent = paused ? "解锁实时" : "锁定画面";
  $("btn-rx-pause").classList.toggle("on", paused);
  if (paused) {
    frozenFrames = frames.slice();
    renderFrames();
    $("rx-mode").textContent = "已锁定当前画面（后台仍在接收）";
  } else {
    frozenFrames = null;
    $("rx-mode").textContent = "";
    dirty = true;
  }
};
$("btn-rx-clear").onclick = () => { frames = []; if (paused) frozenFrames = []; renderFrames(); };
$("rx-filter").addEventListener("input", () => renderFrames());
$("btn-rx-export").onclick = () => {
  const keywords = $("rx-filter").value.split(/[,，;；\s]+/).filter(Boolean);
  const source = frozenFrames || frames;
  const view = source.filter((f) => !keywords.length || keywords.some((k) => frameMatches(f, k)));
  const csvCell = (v) => {
    const s = String(v ?? "");
    return /[,"\r\n]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s;
  };
  const rows = [
    ["ts", "direction", "extended", "id", "pgn", "sa", "da", "priority", "dlc", "data"],
    ...view.map((f) => [f.ts, f.dir, f.ext ? 1 : 0, f.id, f.pgn, f.sa, f.da, f.prio, f.dlc, f.data]),
  ];
  const blob = new Blob(["\uFEFF" + rows.map((r) => r.map(csvCell).join(",")).join("\r\n")], {type: "text/csv;charset=utf-8"});
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "can_frames_" + new Date().toISOString().replace(/[:.]/g, "-") + ".csv";
  a.click();
  URL.revokeObjectURL(url);
  toast("已导出 " + view.length + " 帧");
};

// ---------------------------------------------------------------- 发送
$("btn-tx-send").onclick = async () => {
  await api("/api/send", "POST", {
    id: $("tx-id").value.trim(), data: getByteHex($("tx-bytes")),
    extended: $("tx-ext").checked,
  });
};

const SENDER_MODES = [["fixed", "固定"], ["increment", "递增"], ["list", "列表循环"],
  ["random", "随机／掩码随机"], ["ramp", "有界斜坡"]];
function generatorFields(s = {}) {
  return `<label data-gen="list">数据列表（每行一帧，空帧写 -）<textarea class="g-list" rows="3" aria-label="循环数据列表">${esc((s.data_list || []).map(x => x || "-").join("\n"))}</textarea></label>` +
    `<label data-gen="random">种子 <input class="g-seed" type="number" step="1" value="${s.random_seed ?? 0}" size="7"></label>` +
    `<label data-gen="random">掩码(hex) <input class="g-mask" value="${esc(s.random_mask || "")}" size="18" placeholder="空=全部随机，1位随机化"></label>` +
    `<label data-gen="ramp">下限 <input class="g-min" type="number" step="1" value="${s.ramp_min ?? 0}"></label>` +
    `<label data-gen="ramp">上限 <input class="g-max" type="number" step="1" value="${s.ramp_max ?? 255}"></label>`;
}
function showGeneratorFields(root, mode) {
  root.querySelectorAll("[data-gen]").forEach(el => { el.hidden = el.dataset.gen !== mode; });
}
function readGeneratorFields(root) {
  return {
    data_list: root.querySelector(".g-list").value.split(/\r?\n/).map(x => x.trim()).filter(Boolean).map(x => x === "-" ? "" : x),
    random_seed: Number(root.querySelector(".g-seed").value),
    random_mask: root.querySelector(".g-mask").value.trim(),
    ramp_min: Number(root.querySelector(".g-min").value),
    ramp_max: Number(root.querySelector(".g-max").value),
  };
}
$("ps-generator").innerHTML = generatorFields();
showGeneratorFields($("ps-generator"), $("ps-mode").value);
$("ps-mode").addEventListener("change", () => showGeneratorFields($("ps-generator"), $("ps-mode").value));
$("ps-body").addEventListener("change", e => {
  if (!e.target.matches(".e-mode")) return;
  const row = e.target.closest("tr");
  showGeneratorFields(row, e.target.value);
  row.querySelectorAll(".e-byte,.e-byte-end,.e-step").forEach(el => {
    el.disabled = !["increment", "ramp"].includes(e.target.value);
  });
});

$("btn-ps-add").onclick = async () => {
  await api("/api/senders", "POST", {
    name: $("ps-name").value, id: $("ps-id").value.trim(),
    data: getByteHex($("ps-bytes")),
    period_ms: parseInt($("ps-period").value) || 100,
    extended: $("ps-ext").checked,
    mode: $("ps-mode").value,
    ...readGeneratorFields($("ps-generator")),
    inc_byte: parseInt($("ps-byte").value) || 0,
    inc_end: parseInt($("ps-byte-end").value) || parseInt($("ps-byte").value) || 0,
    inc_step: parseInt($("ps-step").value) || 1,
  });
  refreshSenders();
};

// 表格内嵌字节编辑的输入过滤；任何编辑都标记"脏"，暂停自动刷新防止改动被吞
let psDirty = false;
$("ps-body").addEventListener("input", (e) => {
  if (e.target.matches(".byte-editor input"))
    e.target.value = e.target.value.replace(/[^0-9a-fA-F]/g, "").toUpperCase();
});
["input", "change"].forEach((ev) => $("ps-body").addEventListener(ev, () => { psDirty = true; }));

async function refreshSenders() {
  const list = await api("/api/senders");
  $("ps-body").innerHTML = list.map((s) => {
    const inc = ["increment", "ramp"].includes(s.mode);
    const idHex = s.arbitration_id.toString(16).toUpperCase()
      .padStart(s.is_extended_id ? 8 : 3, "0");
    return `<tr data-sid="${s.id}">` +
      `<td>${esc(s.name)}</td><td>${idHex}</td>` +
      `<td><select class="e-ext"><option value="1" ${s.is_extended_id ? "selected" : ""}>扩展</option><option value="0" ${s.is_extended_id ? "" : "selected"}>标准</option></select></td>` +
      `<td>${byteInputsHtml(s.data_hex)}</td>` +
      `<td><input class="e-period" value="${s.period_ms}" size="5"></td>` +
      `<td><select class="e-mode">${SENDER_MODES.map(([value, label]) => `<option value="${value}"${s.mode === value ? " selected" : ""}>${label}</option>`).join("")}</select>` +
      `<div class="generator-fields">${generatorFields(s)}</div></td>` +
      `<td><input class="e-byte" value="${s.inc_byte ?? 0}" size="2" ${inc ? "" : "disabled"}>~` +
      `<input class="e-byte-end" value="${s.inc_end ?? s.inc_byte ?? 0}" size="2" ${inc ? "" : "disabled"}>` +
      ` / <input class="e-step" value="${s.inc_step ?? 1}" size="3" ${inc ? "" : "disabled"}></td>` +
      `<td>${s.running ? "运行中" : s.error ? `<span class="err" title="${esc(s.error)}">发送失败</span>` : "停止"}</td><td>${s.sent}</td>` +
      `<td><button class="small primary" onclick="psSave('${s.id}')">保存</button>` +
      ` <button class="small" onclick="psToggle('${s.id}', ${s.running ? 0 : 1})">${s.running ? "停止" : "启动"}</button>` +
      ` <button class="small" onclick="psDup('${s.id}')">复制</button>` +
      ` <button class="small" onclick="psDel('${s.id}')">删除</button></td></tr>`;
  }).join("") || '<tr><td colspan="10" class="hint">暂无周期任务</td></tr>';
  $("ps-body").querySelectorAll("tr[data-sid]").forEach(row => showGeneratorFields(row, row.querySelector(".e-mode").value));
}
window.psSave = async (id) => {
  const tr = document.querySelector(`tr[data-sid="${id}"]`);
  await api(`/api/senders/${id}`, "PUT", {
    is_extended_id: tr.querySelector(".e-ext").value === "1",
    data: getByteHex(tr.querySelector(".byte-editor")),
    period_ms: parseInt(tr.querySelector(".e-period").value) || 100,
    mode: tr.querySelector(".e-mode").value,
    ...readGeneratorFields(tr),
    inc_byte: parseInt(tr.querySelector(".e-byte").value) || 0,
    inc_end: parseInt(tr.querySelector(".e-byte-end").value) || parseInt(tr.querySelector(".e-byte").value) || 0,
    inc_step: parseInt(tr.querySelector(".e-step").value) || 1,
  });
  toast("已保存，下一周期生效");
  psDirty = false;
  refreshSenders();
};
window.psToggle = async (id, on) => { await api(`/api/senders/${id}/${on ? "start" : "stop"}`, "POST"); refreshSenders(); };
window.psDel = async (id) => { await api(`/api/senders/${id}`, "DELETE"); refreshSenders(); };
window.psDup = async (id) => {
  await api(`/api/senders/${id}/duplicate`, "POST");
  refreshSenders();
  toast("已复制任务（副本默认停止）");
};
setInterval(() => {
  if (!$("tab-tx").classList.contains("active")) return;
  if (psDirty) return;  // 有未保存的编辑，跳过刷新
  const focusInTable = document.activeElement && $("ps-body").contains(document.activeElement);
  if (!focusInTable) refreshSenders();
}, 2000);

// ---------------------------------------------------------------- 故障模拟
// 节点模板：完整 29bit ID 一站式设定（下拉模板 + 自定义 8 位 hex）
const NODE_TEMPLATES = [
  ["18FECA00", "发动机#1 · DM1 当前故障（18FECA00）"],
  ["18FECB00", "发动机#1 · DM2 历史故障（18FECB00）"],
  ["18FECA49", "尾气后处理#1 · DM1（18FECA49）"],
  ["18FF0000", "发动机#1 · 私有B 广播（18FF0000）"],
  ["0CEF1700", "发动机#1 → 仪表 · 私有A 点对点（0CEF1700）"],
  ["custom", "自定义"],
];

function parseHexOrNull(v) {
  v = String(v).trim().replace(/^0x/i, "");
  if (!v) return null;
  const n = parseInt(v, 16);
  return isNaN(n) ? null : n;
}

// 从完整 ID 拆出 J1939 各字段（供预览标注）
function j1939Info(idHex) {
  const cid = parseInt(idHex, 16);
  const prio = (cid >>> 26) & 7;
  const pf = (cid >>> 16) & 0xff;
  const ps = (cid >>> 8) & 0xff;
  const sa = cid & 0xff;
  const pdu1 = pf <= 0xef;
  const pgn = ((cid >>> 8) & 0x3ffff) & (pdu1 ? 0x3ff00 : 0x3ffff);
  return {
    prio: String(prio),
    pgn: pgn.toString(16).toUpperCase().padStart(4, "0"),
    ps: ps.toString(16).toUpperCase().padStart(2, "0"),
    sa: sa.toString(16).toUpperCase().padStart(2, "0"),
    pdu1,
  };
}

// 由 sa/da/priority/pgn 组出完整 ID（场景回填用）
function composeId(cfg) {
  const prio = cfg.priority ?? 6, pgn = cfg.pgn ?? 65226, sa = cfg.sa ?? 0;
  const pf = (pgn >>> 8) & 0xff;
  const ps = pf <= 0xef ? (cfg.da ?? 0xff) : (pgn & 0xff);
  return (((prio << 26) | ((pgn & 0x3ff00) << 8) | (ps << 8) | sa) >>> 0)
    .toString(16).toUpperCase().padStart(8, "0");
}

function linkSelectInput(selId, inputId, presets, onChange) {
  const sel = $(selId), input = $(inputId);
  sel.innerHTML = presets.map(([v, t]) => `<option value="${v}">${t}</option>`).join("");
  const sync = () => {
    const v = input.value.trim().replace(/^0x/i, "").toUpperCase();
    sel.value = presets.some(([a]) => a === v) ? v : "custom";
  };
  input._sync = sync;
  sel.onchange = () => { if (sel.value !== "custom") input.value = sel.value; onChange(); };
  input.onchange = () => { sync(); onChange(); };
}

function fillLampSelects() {
  for (const id of ["lamp-mil", "lamp-red", "lamp-amber", "lamp-protect"]) {
    $(id).innerHTML = LAMP_OPTS.map(([v, t]) => `<option value="${v}">${t}</option>`).join("");
  }
}

async function refreshFrameStatistics() {
  if (offlineView) return;
  const rows = await api("/api/stats/frames");
  $("rx-stats-body").innerHTML = rows.map((s) =>
    `<tr><td>${s.extended ? "扩展" : "标准"}</td><td>${s.id}</td><td>${s.count}</td>` +
    `<td>${s.avg_period_ms == null ? "-" : s.avg_period_ms}</td>` +
    `<td>${s.min_period_ms == null ? "-" : s.min_period_ms}</td>` +
    `<td>${s.max_period_ms == null ? "-" : s.max_period_ms}</td></tr>`
  ).join("") || '<tr><td colspan="6" class="hint">暂无统计数据</td></tr>';
}

setInterval(() => {
  if ($("tab-rx").classList.contains("active") && !paused) refreshFrameStatistics();
}, 1000);

function dm1ConfigFromForm() {
  return {
    lamps: {
      mil: $("lamp-mil").value, red: $("lamp-red").value,
      amber: $("lamp-amber").value, protect: $("lamp-protect").value,
    },
    arb_id: parseHexOrNull($("dm1-id").value),  // 完整 29bit ID，空则不修改
    tp_cm_id: parseHexOrNull($("tp-cm-id").value),  // 多包通告帧完整 ID，空=跟随节点
    tp_dt_id: parseHexOrNull($("tp-dt-id").value),  // 多包数据帧完整 ID，空=跟随节点
    oc_auto_inc: $("oc-inc").checked,  // DTC 发生次数每周期 +1
    period_ms: parseInt($("dm1-period").value) || 1000,
  };
}

function dtcRows() {
  return [...document.querySelectorAll("#dtc-body tr")].map((tr) => ({
    spn: parseInt(tr.querySelector(".d-spn").value) || 0,
    fmi: parseInt(tr.querySelector(".d-fmi").value) || 0,
    oc: parseInt(tr.querySelector(".d-oc").value) || 1,
  }));
}

function addDtcRow(dtc = { spn: 110, fmi: 0, oc: 1 }) {
  const tr = document.createElement("tr");
  tr.innerHTML =
    `<td><input class="d-spn" value="${dtc.spn}" size="8"></td>` +
    `<td><input class="d-fmi" value="${dtc.fmi}" size="4"></td>` +
    `<td><input class="d-oc" value="${dtc.oc}" size="4"></td>` +
    `<td><button class="small" onclick="this.closest('tr').remove(); pushDm1()">删除</button></td>`;
  $("dtc-body").appendChild(tr);
  tr.querySelectorAll("input").forEach((i) => (i.onchange = pushDm1));
}
window.addDtc = () => { addDtcRow(); pushDm1(); };
$("btn-dtc-add").onclick = window.addDtc;

async function pushDm1() {
  const cfg = { ...dm1ConfigFromForm(), dtcs: dtcRows() };
  const st = await api("/api/dm1", "PUT", cfg);
  renderDm1Status(st);
}
document.querySelectorAll("#tab-dm1 input, #tab-dm1 select").forEach((el) => {
  el.onchange = pushDm1;
});

function renderDm1Status(st) {
  const p = st.preview || {};
  const frames = p.frames || [];
  const cfg = st.config || {};
  let head = "";
  if (frames.length === 1) {
    const info = j1939Info(frames[0].id);
    head = `<div class="pf"><span class="pid">${info.prio}</span>优先级` +
      ` ｜ <span class="pid">${info.pgn}</span>PGN` +
      ` ｜ <span class="pid">${info.ps}</span>${info.pdu1 ? "DA 目标地址" : "PS/GE 组扩展"}` +
      ` ｜ <span class="pid">${info.sa}</span>SA 源地址（${info.pdu1 ? "PDU1 点对点" : "PDU2 广播"}）</div>`;
  } else if (frames.length > 1) {
    // 多包：从 TP.CM 通告字节（第6-8字节，小端）取回原始 PGN
    const b = (frames[0].data.match(/../g) || []).map((h) => parseInt(h, 16));
    const pgn = ((b[5] | 0) | ((b[6] | 0) << 8) | ((b[7] | 0) << 16))
      .toString(16).toUpperCase().padStart(4, "0");
    const i0 = j1939Info(frames[0].id);
    head = `<div class="pf">多包 BAM：优先级 <span class="pid">${i0.prio}</span>、SA <span class="pid">${i0.sa}</span> 已生效` +
      `；CM 通告帧 <span class="pid">${frames[0].id}</span>（PF ${frames[0].id.slice(2, 4)}）、DT 数据帧 <span class="pid">${frames[1].id}</span>（PF ${frames[1].id.slice(2, 4)}）</div>` +
      `<div class="pf">原始 PGN <span class="pid">${pgn}</span> 在 CM 通告字节中传输，接收端重组后还原为完整报文</div>`;
  }
  $("dm1-preview").innerHTML = frames.length
    ? head + frames.map((fr) =>
        `<div class="pf"><span class="pid">${fr.id}</span>` +
        `<span class="pdata">${hexGroup(fr.data)}</span>` +
        `<span class="hint">${esc(fr.desc)}</span></div>`
      ).join("")
    : '<span class="hint">无 DTC 时发送"无故障"DM1（FF FF FF FF ...）</span>';
  $("dm1-state").textContent = st.running
    ? `● 周期广播中（已发 ${st.sent_frames} 帧）`
    : st.last_error ? `错误：${st.last_error}` : "○ 未运行";
  $("btn-dm1-start").disabled = st.running;
}

$("btn-dm1-once").onclick = async () => {
  const r = await api("/api/dm1/send_once", "POST");
  toast(`已按 J1939 打包发送 ${r.sent} 帧`);
};
$("btn-dm1-start").onclick = async () => { await pushDm1(); renderDm1Status(await api("/api/dm1/start", "POST")); };
$("btn-dm1-stop").onclick = async () => renderDm1Status(await api("/api/dm1/stop", "POST"));

async function loadScenarios() {
  const list = await api("/api/scenarios");
  $("scn-select").innerHTML = list.map((s) => `<option value="${s.file}">${s.name}（${s.file}）</option>`).join("");
  window._scenarios = list;
}
// 把 DM1 配置（场景/保存的现场）回填到故障模拟表单
function backfillDm1Form(cfg) {
  for (const [k, id] of Object.entries({
    mil: "lamp-mil", red: "lamp-red", amber: "lamp-amber", protect: "lamp-protect",
  })) $(id).value = (cfg.lamps || {})[k] || "off";
  $("dm1-id").value = composeId(cfg);
  $("dm1-id")._sync && $("dm1-id")._sync();
  $("tp-cm-id").value = cfg.tp_cm_id == null ? "" : cfg.tp_cm_id.toString(16).toUpperCase().padStart(8, "0");
  $("tp-dt-id").value = cfg.tp_dt_id == null ? "" : cfg.tp_dt_id.toString(16).toUpperCase().padStart(8, "0");
  $("oc-inc").checked = !!cfg.oc_auto_inc;
  $("dm1-period").value = cfg.period_ms ?? 1000;
  $("dtc-body").innerHTML = "";
  (cfg.dtcs || []).forEach((d) => addDtcRow(d));
}

$("btn-scn-apply").onclick = async () => {
  const file = $("scn-select").value;
  const st = await api(`/api/scenarios/${file}/apply`, "POST");
  backfillDm1Form(st.config);
  const scn = window._scenarios.find((s) => s.file === file);
  $("scn-desc").textContent = scn ? scn.config.description || "" : "";
  renderDm1Status(st);
  toast(`已加载场景：${scn ? scn.name : file}`);
};

// ------------------------------------------------------------- 配置保存/读取
async function refreshPresets() {
  const list = await api("/api/presets");
  window._presets = list;
  $("preset-select").innerHTML = list.length
    ? list.map((p) => `<option value="${p.file}">${p.name}（${p.saved_at}，${p.tasks} 任务）</option>`).join("")
    : '<option value="">暂无保存的配置</option>';
}

// ------------------------------------------------- 文件选择对话框（本机运行时弹系统窗口）
async function pickFile(mode, ext, intoId) {
  const r = await api(`/api/filepicker?mode=${mode}&ext=${ext}`);
  if (r.path) $(intoId).value = r.path;
}

$("btn-preset-save2").onclick = async () => {
  const r = await api("/api/presets/save_to", "POST", { path: $("preset-path").value.trim() });
  toast(`已保存到 ${r.path}（${r.tasks} 任务 + 故障配置）`);
};
$("btn-preset-load2").onclick = async () => {
  const r = await api("/api/presets/load_from", "POST", { path: $("preset-path").value.trim() });
  backfillDm1Form(r.dm1.config);
  renderDm1Status(r.dm1);
  refreshSenders();
  toast(`已从文件恢复 ${r.tasks} 个任务 + 故障配置`);
};
$("btn-pick-save").onclick = () => pickFile("save", "json", "preset-path");
$("btn-pick-open").onclick = () => pickFile("open", "json", "preset-path");
$("btn-log-pick").onclick = () => pickFile("open", "csv", "log-path");
$("btn-log-view2").onclick = async () => {
  const r = await api("/api/log/read_file", "POST", { path: $("log-path").value.trim() });
  enterOfflineView(r.file, r.frames, r.count);
};

$("btn-preset-save").onclick = async () => {
  const r = await api("/api/presets", "POST", { name: $("preset-name").value.trim() });
  toast(`已保存「${r.name}」：${r.tasks} 个任务 + 故障配置`);
  $("preset-name").value = "";
  refreshPresets();
};

$("btn-preset-load").onclick = async () => {
  const file = $("preset-select").value;
  if (!file) return toast("没有可读取的配置", true);
  const r = await api(`/api/presets/${file}/load`, "POST");
  backfillDm1Form(r.dm1.config);
  renderDm1Status(r.dm1);
  refreshSenders();
  toast(`已恢复 ${r.tasks} 个周期任务 + 故障配置`);
};

$("btn-preset-del").onclick = async () => {
  const file = $("preset-select").value;
  if (!file) return;
  await api(`/api/presets/${file}`, "DELETE");
  toast("已删除");
  refreshPresets();
};

// ---------------------------------------------------------------- 日志
$("btn-log-start").onclick = async () => {
  const info = await api("/api/log/start", "POST", { format: $("log-format").value });
  $("log-state").textContent = `记录中 → ${info.file}`;
  toast(`开始记录：${info.file}`);
};
$("btn-log-stop").onclick = async () => {
  const info = await api("/api/log/stop", "POST");
  $("log-state").textContent = `已记录 ${info.frames} 帧`;
  refreshLogs();
};

async function refreshLogs() {
  const files = await api("/api/log/files");
  $("log-body").innerHTML = files.map((f) =>
    `<tr><td>${f.name}</td><td>${(f.size / 1024).toFixed(1)} KB</td>` +
    `<td><a href="/api/log/download/${f.name}" target="_blank">下载</a> ` +
    `<button class="small" onclick="logView('${f.name}')">查看</button>` +
    `<button class="small" onclick="replay('${f.name}')">回放</button>` +
    `<button class="small" onclick="logDelete('${f.name}')">删除</button></td></tr>`
  ).join("") || '<tr><td colspan="3" class="hint">暂无日志</td></tr>';
}
window.replay = async (name) => {
  const st = await api("/api/log/replay", "POST", { file: name, speed: parseFloat($("replay-speed").value) || 1 });
  $("replay-state").textContent = `回放中 0/${st.frames}`;
  toast(`回放 ${st.frames} 帧（${st.speed}x）`);
};
$("btn-replay-stop").onclick = async () => {
  const st = await api("/api/log/replay/stop", "POST");
  $("replay-state").textContent = st.total ? `已停止 ${st.current}/${st.total}` : "未回放";
  toast("已停止回放");
};
function enterOfflineView(name, loaded, count) {
  frames = loaded;
  frozenFrames = null;
  offlineView = name;
  paused = false;
  $("btn-rx-pause").textContent = "锁定画面";
  $("btn-rx-pause").classList.remove("on");
  dirty = true;
  document.querySelector('button.tab[data-tab="tab-rx"]').click();
  $("rx-mode").textContent = `回看 ${name}（${count} 帧，已停实时更新）`;
  $("btn-rx-live").style.display = "";
  toast(`已加载 ${count} 帧到接收页`);
}
window.logView = async (name) => {
  const r = await api(`/api/log/read/${name}`);
  enterOfflineView(r.file, r.frames, r.count);
};
window.logDelete = async (name) => {
  if (!confirm(`确定删除日志“${name}”吗？`)) return;
  await api(`/api/log/${encodeURIComponent(name)}`, "DELETE");
  toast(`已删除日志：${name}`);
  refreshLogs();
};
$("btn-rx-live").onclick = () => {
  offlineView = null;
  frames = [];
  frozenFrames = null;
  dirty = true;
  $("rx-mode").textContent = "";
  $("btn-rx-live").style.display = "none";
  toast("已恢复实时接收");
};
setInterval(async () => {
  if ($("tab-log").classList.contains("active")) {
    refreshLogs();
    const st = await api("/api/log/replay/status");
    $("replay-state").textContent = st.replaying
      ? `回放中 ${st.current}/${st.total}`
      : st.total ? `已完成 ${st.current}/${st.total}` : "未回放";
  }
}, 1000);

// ---------------------------------------------------------------- 触发
// 数据条件编辑（字节/字节区间/单bit/位段，多条件 AND）
let trConds = [];
const COND_OPS = ["==", "!=", ">", "<", ">=", "<="];
function renderCondInputs() {
  const t = $("tr-cond-type").value;
  const box = $("tr-cond-inputs");
  const opSel = `<select id="tc-op">${COND_OPS.map((o) => `<option${o === "==" ? " selected" : ""}>${o}</option>`).join("")}</select>`;
  if (t === "byte")
    box.innerHTML = `字节[<input id="tc-i" size="2" value="1">] ${opSel} 值(hex)[<input id="tc-v" size="4" value="1E">]`;
  else if (t === "bytes")
    box.innerHTML = `起[<input id="tc-s" size="2" value="1">]~止[<input id="tc-e" size="2" value="2">] ${opSel} 值(hex)[<input id="tc-v" size="6" value="07D0">]`;
  else if (t === "bit")
    box.innerHTML = `bit序号0-63[<input id="tc-i" size="3" value="13">] = [<select id="tc-v"><option>0</option><option>1</option></select>]`;
  else if (t === "bits")
    box.innerHTML = `字节[<input id="tc-b" size="2" value="0">] 位[<input id="tc-s" size="2" value="2">]~[<input id="tc-e" size="2" value="5">] = 值[<input id="tc-v" size="3" value="9">]`;
  else box.innerHTML = "";
}
$("tr-cond-type").onchange = renderCondInputs;
function condText(c) {
  if (c.type === "byte") return `B${c.index}${c.op || "=="}${c.value}`;
  if (c.type === "bytes") return `B${c.start}~${c.end}${c.op || "=="}${c.value}`;
  if (c.type === "bit") return `bit${c.index}=${c.value}`;
  return `B${c.byte}[${c.start}-${c.end}]=${c.value}`;
}
function renderCondList() {
  $("tr-cond-list").innerHTML = trConds.length
    ? "已加条件（多条件为 AND）：" + trConds.map((c, i) =>
        `[${condText(c)} <a href="javascript:void(0)" onclick="trCondDel(${i})">删</a>]`).join(" ")
    : "";
}
window.trCondDel = (i) => { trConds.splice(i, 1); renderCondList(); };
$("btn-tr-cond-add").onclick = () => {
  const t = $("tr-cond-type").value;
  if (!t) return toast("先选择条件类型", true);
  const hx = (id) => parseInt($(id).value, 16);
  let c;
  if (t === "byte") c = { type: "byte", index: parseInt($("tc-i").value), op: $("tc-op").value, value: hx("tc-v") };
  else if (t === "bytes") c = { type: "bytes", start: parseInt($("tc-s").value), end: parseInt($("tc-e").value), op: $("tc-op").value, value: hx("tc-v") };
  else if (t === "bit") c = { type: "bit", index: parseInt($("tc-i").value), value: parseInt($("tc-v").value) };
  else c = { type: "bits", byte: parseInt($("tc-b").value), start: parseInt($("tc-s").value), end: parseInt($("tc-e").value), value: hx("tc-v") };
  trConds.push(c);
  renderCondList();
};

$("btn-tr-add").onclick = async () => {
  const body = { name: $("tr-name").value || "规则" };
  if ($("tr-id").value.trim()) body.match_id = $("tr-id").value.trim();
  if ($("tr-pgn").value.trim()) body.match_pgn = parseInt($("tr-pgn").value);
  if ($("tr-data").value.trim()) body.data_contains = $("tr-data").value.replace(/\s/g, "");
  if (trConds.length) body.data_cond = trConds;
  body.action = $("tr-action").value;
  if (body.action === "send") {
    body.send_id = $("tr-send-id").value.trim();
    body.send_data = getByteHex($("tr-send-bytes")) || "00";
    body.send_extended = $("tr-send-ext").checked;
  }
  await api("/api/triggers", "POST", body);
  trConds = [];
  renderCondList();
  refreshTriggers();
};

async function refreshTriggers() {
  const rules = await api("/api/triggers");
  $("tr-body").innerHTML = rules.map((r) => {
    const conds = (r.data_cond || []).map(condText).join(" 且 ");
    const match = [
      r.match_id ? `ID ${r.match_id}` : "",
      r.match_pgn ? `PGN ${r.match_pgn}` : "",
      r.data_contains ? `数据含 ${r.data_contains}` : "",
      conds ? `条件 ${conds}` : "",
    ].filter(Boolean).join(" + ") || "无匹配条件";
    const action = r.action === "send" ? `发${r.send_extended ? "扩展" : "标准"}帧 ${r.send_id || ""} ${hexGroup(r.send_data || "")}` : r.action === "count" ? "计数" : "高亮";
    return `<tr><td>${esc(r.name)}</td><td>${match}</td><td>${action}</td><td>${r.hits}</td>` +
      `<td>${r.enabled ? "是" : "否"}</td>` +
      `<td><button class="small" onclick="trToggle('${r.id}', ${r.enabled ? 0 : 1})">${r.enabled ? "禁用" : "启用"}</button>` +
      ` <button class="small" onclick="trDel('${r.id}')">删除</button></td></tr>`;
  }).join("") || '<tr><td colspan="6" class="hint">暂无规则</td></tr>';
}
window.trToggle = async (id, en) => { await api(`/api/triggers/${id}`, "PUT", { enabled: !!en }); refreshTriggers(); };
window.trDel = async (id) => { await api(`/api/triggers/${id}`, "DELETE"); refreshTriggers(); };
async function setAllTriggersEnabled(enabled) {
  await api("/api/triggers/set_enabled", "POST", { enabled });
  refreshTriggers();
  toast(enabled ? "已全部启用触发器" : "已全部禁用触发器");
}
$("btn-tr-enable-all").onclick = () => setAllTriggersEnabled(true);
$("btn-tr-disable-all").onclick = () => setAllTriggersEnabled(false);
$("btn-tr-reset-hits").onclick = async () => {
  await api("/api/triggers/reset_hits", "POST");
  refreshTriggers();
  toast("已清零触发器命中计数");
};
setInterval(() => { if ($("tab-trig").classList.contains("active")) refreshTriggers(); }, 3000);

// ------------------------------------------------------------- 触发规则保存/读取
async function refreshTrigPresets() {
  const list = await api("/api/triggers/presets");
  $("trig-preset-select").innerHTML = list.length
    ? list.map((p) => `<option value="${p.file}">${p.name}（${p.saved_at}，${p.rules} 条）</option>`).join("")
    : '<option value="">暂无保存的规则集</option>';
}
$("btn-trig-save").onclick = async () => {
  const r = await api("/api/triggers/presets", "POST", { name: $("trig-name").value.trim() });
  toast(`已保存「${r.name}」：${r.rules} 条规则`);
  $("trig-name").value = "";
  refreshTrigPresets();
};
$("btn-trig-load").onclick = async () => {
  const file = $("trig-preset-select").value;
  if (!file) return toast("没有可读取的规则集", true);
  const r = await api(`/api/triggers/presets/${file}/load`, "POST");
  refreshTriggers();
  toast(`已恢复 ${r.rules} 条规则`);
};
$("btn-trig-del").onclick = async () => {
  const file = $("trig-preset-select").value;
  if (!file) return;
  await api(`/api/triggers/presets/${file}`, "DELETE");
  toast("已删除");
  refreshTrigPresets();
};
$("btn-trig-save2").onclick = async () => {
  const r = await api("/api/triggers/save_to", "POST", { path: $("trig-path").value.trim() });
  toast(`已保存到 ${r.path}（${r.rules} 条规则）`);
};
$("btn-trig-load2").onclick = async () => {
  const r = await api("/api/triggers/load_from", "POST", { path: $("trig-path").value.trim() });
  refreshTriggers();
  toast(`已从文件恢复 ${r.rules} 条规则`);
};
$("btn-trig-pick-save").onclick = () => pickFile("save", "json", "trig-path");
$("btn-trig-pick-open").onclick = () => pickFile("open", "json", "trig-path");

// ---------------------------------------------------------------- 文件路径设置
async function loadSettings() {
  const s = await api("/api/settings");
  $("set-logs").value = s.logs_dir;
  $("set-presets").value = s.presets_dir;
  window._defaultDirs = { logs: s.default_logs_dir, presets: s.default_presets_dir };
}
$("btn-settings").onclick = async () => {
  const r = await api("/api/settings", "PUT", {
    logs_dir: $("set-logs").value.trim(), presets_dir: $("set-presets").value.trim(),
  });
  toast(`路径已应用并保存：日志 → ${r.logs_dir}`);
  refreshLogs();
  refreshPresets();
};
$("btn-settings-reset").onclick = async () => {
  const d = window._defaultDirs || {};
  const r = await api("/api/settings", "PUT", { logs_dir: d.logs, presets_dir: d.presets });
  $("set-logs").value = r.logs_dir;
  $("set-presets").value = r.presets_dir;
  toast("已恢复默认路径");
  refreshLogs();
  refreshPresets();
};

// ---------------------------------------------------------------- 状态轮询
setInterval(async () => {
  try {
    const st = await api("/api/status");
    const badge = $("conn-badge");
    badge.textContent = st.connected ? "已连接" : "未连接";
    badge.className = "badge " + (st.connected ? "on" : "off");
    $("stats").textContent =
      `收 ${st.stats.received} / 发 ${st.stats.sent}` +
      (st.stats.error_frames ? ` / 错误 ${st.stats.error_frames}` : "") +
      (st.recording ? " / ●REC" : "") +
      (st.replay && st.replay.replaying ? " / ▶回放" : "") +
      (st.dbc_loaded ? " / DBC" : "");
    renderBusInfo(st);
    if (window._recording !== st.recording) {  // 他在日志页开/停时同步按钮
      window._recording = st.recording;
      syncRecButton();
    }
  } catch (e) { /* 服务不可达时静默 */ }
}, 1000);

// ---------------------------------------------------------------- init
(async function init() {
  fillLampSelects();
  linkSelectInput("dm1-node", "dm1-id", NODE_TEMPLATES, pushDm1);
  renderByteEditor($("tx-bytes"));
  renderByteEditor($("ps-bytes"), "645A000000000000");
  renderByteEditor($("tr-send-bytes"));
  addDtcRow({ spn: 110, fmi: 0, oc: 1 });
  await loadInterfaces();
  await loadScenarios();
  await loadSettings();
  await refreshSenders();
  await refreshPresets();
  await refreshLogs();
  await refreshTriggers();
  await refreshTrigPresets();
  await pushDm1();
  connectWs();
})();
