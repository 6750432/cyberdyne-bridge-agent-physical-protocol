"use strict";

const $ = (id) => document.getElementById(id);
let loading = false;
let authed = false;
let operatorName = "operator";

function el(tag, cls, text) {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (text !== undefined && text !== null) n.textContent = String(text);
  return n;
}

function toast(message, isError = false) {
  const t = $("toast");
  t.textContent = message;
  t.className = "toast show" + (isError ? " err" : "");
  clearTimeout(toast._timer);
  toast._timer = setTimeout(() => { t.className = "toast"; }, 5000);
}

async function api(path, options = {}) {
  const res = await fetch(path, Object.assign({credentials: "same-origin"}, options));
  let body = null;
  try { body = await res.json(); } catch (_) {}
  if (res.status === 401) {
    showLogin();
    throw new Error("operator login required");
  }
  if (!res.ok || !body || body.ok === false) {
    throw new Error((body && body.error) || `HTTP ${res.status}`);
  }
  return body;
}

function showLogin() {
  authed = false;
  $("login").classList.remove("hidden");
  $("login-token").focus();
}

function hideLogin() {
  authed = true;
  $("login").classList.add("hidden");
  $("login-error").textContent = "";
}

function setOperator(name) {
  operatorName = name || "operator";
  $("operator-name").textContent = operatorName;
}

async function refreshSession() {
  try {
    const s = await fetch("/api/session", {credentials: "same-origin"}).then(r => r.json());
    if (s.operator) setOperator(s.operator);
  } catch (_) {}
}

function setConnection(ok, text) {
  const n = $("connection");
  n.className = "pill " + (ok ? "online" : "offline");
  n.textContent = text;
}

function fmtTime(ms) {
  if (!ms) return "—";
  const d = new Date(Number(ms));
  if (Number.isNaN(d.getTime())) return String(ms);
  return d.toLocaleString();
}

function leaseText(lease) {
  if (!lease) return "free";
  const owner = lease.agent_id || lease.owner || lease.lease_id || "held";
  const exp = lease.expires_at ? ` · expires ${fmtTime(Number(lease.expires_at) * 1000)}` : "";
  return owner + exp;
}

function renderDevices(devices) {
  const root = $("devices");
  root.replaceChildren();
  $("device-count").textContent = String(devices.length);
  if (!devices.length) {
    root.appendChild(el("div", "empty", "No devices reported by the Kernel."));
    return;
  }
  for (const d of devices) {
    const card = el("article", "device" + (d.online ? "" : " offline") + (d.safe ? " safe" : ""));
    const head = el("div", "device-head");
    const left = el("div");
    left.appendChild(el("div", "device-name", d.device_id || "unknown device"));
    left.appendChild(el("div", "device-type", d.type || "unknown type"));
    const badges = el("div");
    badges.appendChild(el("span", "badge " + (d.online ? "ready" : ""), d.online ? "online" : "offline"));
    if (d.safe) badges.appendChild(el("span", "badge safe", "LATCHED SAFE"));
    head.append(left, badges);
    card.appendChild(head);

    const kv = el("dl", "kv");
    const add = (k, v) => { kv.appendChild(el("dt", null, k)); kv.appendChild(el("dd", null, v)); };
    add("fd", d.fd || "—");
    add("lease", leaseText(d.lease));
    add("fencing", d.lease && d.lease.fencing_token !== undefined ? d.lease.fencing_token : "—");
    add("pending", d.pending === null || d.pending === undefined ? "—" : d.pending);
    add("health", d.health ? (d.health.ok ? "ok" : "not ok") : "—");
    if (d.facts_error) add("state", d.facts_error);
    card.appendChild(kv);

    const facts = el("details", "facts");
    facts.appendChild(el("summary", null, "facts"));
    const pre = el("pre", null, d.facts ? JSON.stringify(d.facts, null, 2) : "no state buffered");
    facts.appendChild(pre);
    card.appendChild(facts);

    const actions = el("div", "device-actions");
    const stop = el("button", "btn danger", d.safe ? "LATCHED" : "STOP THIS DEVICE");
    stop.disabled = !d.fd || Boolean(d.safe);
    stop.addEventListener("click", () => doEstop(d.fd, d.device_id));
    actions.appendChild(stop);
    if (d.lease && d.lease.lease_id) {
      const rel = el("button", "btn", "Release lease");
      rel.addEventListener("click", () => doRelease(d.device_id, d.lease));
      actions.appendChild(rel);
    }
    if (d.safe) {
      const resume = el("button", "btn", "RESUME DEVICE");
      resume.addEventListener("click", () => doResume(d.device_id, false));
      actions.appendChild(resume);
    }
    card.appendChild(actions);
    root.appendChild(card);
  }
}

function renderNotifications(rows, unread) {
  const root = $("notifications");
  root.replaceChildren();
  $("notify-count").textContent = String(unread || 0);
  $("notify-summary").textContent = `${unread || 0} unread`;
  if (!rows.length) {
    root.appendChild(el("div", "empty", "No notifications."));
    return;
  }
  for (const n of rows.slice().reverse()) {
    const row = el("div", "notification-row" + (n.read ? " read" : ""));
    row.appendChild(el("div", "notification-title", `${n.type || "notification"} · ${n.device_id || ""}`));
    row.appendChild(el("div", "notification-detail",
      `agent=${n.agent_id || "?"} op=${n.op || "?"} age=${n.age_ms || 0}ms sla=${n.sla_ms || 0}ms`));
    root.appendChild(row);
  }
}

function renderApprovals(rows) {
  const root = $("approvals");
  root.replaceChildren();
  $("approval-count").textContent = `${rows.length} pending`;
  if (!rows.length) {
    root.appendChild(el("div", "empty", "No pending high-risk actions."));
    return;
  }
  for (const a of rows) {
    const row = el("div", "approval-row");
    const left = el("div", "approval-main");
    left.appendChild(el("div", "approval-title", `${a.op || "action"} · ${a.device_id}`));
    left.appendChild(el("div", "muted", `agent=${a.agent_id || "?"} channel=${a.channel || "?"} approvals=${(a.approvals || []).length}/${a.required || 1} expires=${fmtTime(a.expires)}`));
    left.appendChild(el("div", "approval-args", JSON.stringify(a.args || {})));
    const actions = el("div", "approval-actions");
    const ok = el("button", "btn", "Approve");
    ok.addEventListener("click", () => doApproval(a.approval_id, true));
    const no = el("button", "btn danger", "Deny");
    no.addEventListener("click", () => doApproval(a.approval_id, false));
    actions.append(ok, no);
    row.append(left, actions);
    root.appendChild(row);
  }
}

async function loadApprovals() {
  try {
    const res = await api("/api/approvals");
    renderApprovals(res.approvals || []);
  } catch (e) {
    renderApprovals([]);
  }
}

async function doApproval(id, approve) {
  if (!confirm(approve ? "Approve this high-risk action?" : "Deny this high-risk action?")) return;
  try {
    const res = await api(approve ? "/api/approvals/approve" : "/api/approvals/deny", {
      method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({approval_id: id})
    });
    renderApprovals(res.approvals || []);
    if (approve && (res.result || {}).pending) {
      toast(`Approval recorded · ${(res.result.approvals || []).length}/${res.result.required || 2} · waiting for second operator`);
    } else {
      toast(approve ? "Approved" : "Denied");
    }
    await load();
  } catch (e) {
    toast("Approval failed: " + (e.message || e), true);
  }
}

async function doRelease(deviceId, lease) {
  if (!confirm(`Release lease on ${deviceId}?\n\nThe agent will need to acquire a new lease.`)) return;
  try {
    const res = await api("/api/lease/release", {
      method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({device_id: deviceId})
    });
    toast(`Lease released · canceled=${(res.result || {}).canceled || 0}`);
    if (res.status) renderDevices(res.status.devices || []);
    await loadApprovals();
    await load();
  } catch (e) {
    toast("Release failed: " + (e.message || e), true);
  }
}

function auditDetail(row) {
  const parts = [];
  for (const [k, v] of Object.entries(row)) {
    if (k === "t" || k === "event" || k === "hash" || k === "prev") continue;
    if (v === null || v === undefined || v === "") continue;
    parts.push(`${k}=${typeof v === "object" ? JSON.stringify(v) : v}`);
  }
  return parts.join("  ");
}

function renderAudit(rows) {
  const root = $("audit");
  root.replaceChildren();
  if (!rows.length) {
    root.appendChild(el("div", "empty", "No audit rows yet."));
    return;
  }
  for (const row of rows.slice().reverse()) {
    const r = el("div", "audit-row");
    r.appendChild(el("div", "audit-time", fmtTime(row.t)));
    r.appendChild(el("div", "audit-event", row.event || "event"));
    r.appendChild(el("div", "audit-detail", auditDetail(row)));
    root.appendChild(r);
  }
}

async function load() {
  if (loading || !authed) return;
  loading = true;
  try {
    const [status, audit, approvals, notifications] = await Promise.all([
      api("/api/status"), api("/api/audit?limit=80"), api("/api/approvals"),
      api("/api/notifications")
    ]);
    setConnection(true, "kernel connected");
    renderDevices(status.devices || []);
    renderAudit(audit.rows || []);
    renderApprovals(approvals.approvals || []);
    renderNotifications(notifications.notifications || [], notifications.unread || 0);
    updateHistoryDevices(status.devices || []);
    await loadHistory();
  } catch (e) {
    setConnection(false, "kernel unavailable");
    toast(String(e.message || e), true);
  } finally {
    loading = false;
  }
}

async function doResume(deviceId, all) {
  if (!authed) { showLogin(); return; }
  const scope = all ? "ALL DEVICES" : `device ${deviceId}`;
  const reason = prompt(`Resume ${scope}.\n\nReason (required):`, "operator recovery");
  if (reason === null) return;
  if (!reason.trim()) { toast("resume reason required", true); return; }
  if (!confirm(`RESUME ${scope}?\n\nOnly do this after the physical cause is cleared.`)) return;
  try {
    const res = await api("/api/resume", {
      method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({device_id: all ? null : deviceId, all: Boolean(all), reason: reason.trim()})
    });
    toast(`Resume accepted · ${(res.result.devices || []).join(", ")}`);
    if (res.status) renderDevices(res.status.devices || []);
    await load();
  } catch (e) {
    toast("Resume failed: " + (e.message || e), true);
  }
}

async function doEstop(fd, name) {
  if (!authed) { showLogin(); return; }
  const scope = fd ? `device ${name}` : "ALL DEVICES";
  if (!confirm(`EMERGENCY STOP: ${scope}\n\nThis is latched in the Kernel until it is restarted by an operator. Continue?`)) return;
  try {
    const res = await api("/api/estop", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({fd, reason: "operator-console"})
    });
    const p = res.result || {};
    toast(`ESTOP accepted · safe_state=${p.safe_state || "unknown"} · driver_ok=${p.driver_ok}`);
    if (res.status) {
      setConnection(true, "kernel connected");
      renderDevices(res.status.devices || []);
    }
    const audit = await api("/api/audit?limit=80");
    renderAudit(audit.rows || []);
  } catch (e) {
    toast("ESTOP failed: " + (e.message || e), true);
  }
}

let obTools = [];

function parseJSONInput(id, fallback) {
  const raw = $(id).value.trim();
  if (!raw) return fallback;
  return JSON.parse(raw);
}

function renderOnboardTools(tools) {
  obTools = tools;
  const root = $("ob-tools");
  root.replaceChildren();
  if (!tools.length) {
    root.appendChild(el("div", "empty", "No tools advertised."));
    return;
  }
  for (const t of tools) {
    const row = el("div", "tool-row");
    const label = el("label");
    const cb = document.createElement("input");
    cb.type = "checkbox";
    cb.checked = true;
    cb.dataset.tool = t.name;
    label.append(cb, document.createTextNode(" " + t.name));
    const op = document.createElement("input");
    op.className = "tool-op";
    op.value = t.name;
    op.dataset.tool = t.name;
    op.title = "CBAP op name";
    const desc = el("span", "tool-desc", t.description || "");
    row.append(label, op, desc);
    root.appendChild(row);
  }
  $("ob-options").classList.remove("hidden");
}

async function onboardScan() {
  let cmd;
  try { cmd = parseJSONInput("ob-command", null); }
  catch (_) { toast("command must be a JSON argv array", true); return; }
  if (!Array.isArray(cmd) || !cmd.length) { toast("command must be a JSON argv array", true); return; }
  $("ob-scan-status").textContent = "starting MCP…";
  try {
    const res = await api("/api/onboard/scan", {
      method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({command: cmd, cwd: $("ob-cwd").value.trim() || null})
    });
    renderOnboardTools(res.tools || []);
    $("ob-scan-status").textContent = `${(res.tools || []).length} tools · ${JSON.stringify(res.server || {})}`;
    toast("MCP scanned");
  } catch (e) {
    $("ob-scan-status").textContent = "";
    toast("Scan failed: " + (e.message || e), true);
  }
}

async function onboardCreate() {
  const selected = [];
  document.querySelectorAll("#ob-tools .tool-row").forEach((row) => {
    const cb = row.querySelector("input[type=checkbox]");
    const op = row.querySelector(".tool-op");
    if (cb && cb.checked) selected.push({cbap_op: op.value.trim(), tool: cb.dataset.tool, args: {}});
  });
  if (!selected.length) { toast("select at least one tool", true); return; }
  let facts = {};
  const src = $("ob-facts-source").value;
  const ref = $("ob-facts-ref").value.trim();
  if (src === "tool") facts = {source: "tool", tool: ref, independent: false};
  else if (src === "resource") facts = {source: "resource", uri: ref, independent: false};
  let estop = {};
  const et = $("ob-estop-tool").value.trim();
  if (et) {
    let expect;
    try { expect = parseJSONInput("ob-estop-expect", {}); }
    catch (_) { toast("estop expected JSON is invalid", true); return; }
    estop = {tool: et, expect};
  }
  let cmd;
  try { cmd = parseJSONInput("ob-command", null); }
  catch (_) { toast("command must be a JSON argv array", true); return; }
  if (!Array.isArray(cmd) || !cmd.length) { toast("command must be a JSON argv array", true); return; }
  try {
    const res = await api("/api/onboard/create", {
      method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({
        device_id: $("ob-device-id").value.trim(),
        display_name: $("ob-display").value.trim() || $("ob-device-id").value.trim(),
        command: cmd, cwd: $("ob-cwd").value.trim() || null,
        tools: selected, facts, estop
      })
    });
    $("ob-create-status").textContent = res.path || "created";
    toast("Manifest written");
    await onboardList();
  } catch (e) {
    toast("Create failed: " + (e.message || e), true);
  }
}

async function onboardList() {
  try {
    const res = await api("/api/onboard/list");
    const sel = $("ob-list");
    sel.replaceChildren();
    const none = document.createElement("option");
    none.value = ""; none.textContent = "none"; sel.appendChild(none);
    const root = $("ob-registry");
    root.replaceChildren();
    if (!(res.devices || []).length) {
      root.appendChild(el("div", "empty", "No onboarded devices."));
    }
    for (const d of res.devices || []) {
      const o = document.createElement("option");
      o.value = d.name;
      o.textContent = `${d.device_id || d.name}${d.enabled ? "" : " (disabled)"}`;
      sel.appendChild(o);
      const row = el("div", "registry-row" + (d.enabled ? "" : " disabled"));
      const left = el("div");
      left.appendChild(el("div", "registry-name", d.device_id || d.name));
      left.appendChild(el("div", "registry-meta",
        `${d.signed ? "signed" : "unsigned"} · ${d.pinned ? "pinned" : "unpinned"} · ` +
        `${d.tools} tools · ${d.estop ? "estop evidence" : "no estop evidence"}`));
      const meta = el("div", "registry-meta", d.enabled ? "enabled" : "disabled");
      const actions = el("div", "registry-actions");
      const toggle = el("button", "btn", d.enabled ? "Disable" : "Enable");
      toggle.addEventListener("click", () => onboardToggle(d.name, !d.enabled));
      const sign = el("button", "btn", d.signed ? "Re-sign" : "Sign");
      sign.addEventListener("click", () => onboardSign(d.name));
      const probe = el("button", "btn", "Probe");
      probe.addEventListener("click", () => { sel.value = d.name; onboardProbe(); });
      actions.append(toggle, sign, probe);
      row.append(left, meta, actions);
      root.appendChild(row);
    }
  } catch (_) {}
}

async function onboardProbe() {
  const name = $("ob-list").value;
  if (!name) { toast("select an onboarded device", true); return; }
  $("ob-probe-result").textContent = "probing…";
  try {
    const res = await api("/api/onboard/probe", {
      method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({name})
    });
    $("ob-probe-result").textContent = JSON.stringify(res, null, 2);
    toast(res.ok ? "Probe completed" : "Probe failed", !res.ok);
  } catch (e) {
    $("ob-probe-result").textContent = String(e.message || e);
    toast("Probe failed: " + (e.message || e), true);
  }
}

async function reloadRegistry() {
  $("ob-reload-status").textContent = "reloading…";
  try {
    const res = await api("/api/registry/reload", {
      method: "POST", headers: {"Content-Type": "application/json"}, body: "{}"
    });
    const r = res.report || {};
    $("ob-reload-status").textContent =
      `loaded=${(r.loaded || []).length} unloaded=${(r.unloaded || []).length} ` +
      `kept=${(r.kept || []).length} errors=${(r.errors || []).length}`;
    toast("Kernel registry reloaded");
    await load();
  } catch (e) {
    $("ob-reload-status").textContent = "";
    toast("Registry reload failed: " + (e.message || e), true);
  }
}

async function onboardToggle(name, enabled) {
  try {
    const res = await api("/api/onboard/toggle", {
      method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({name, enabled})
    });
    toast(`${name}: ${res.enabled ? "enabled" : "disabled"}`);
    await onboardList();
  } catch (e) {
    toast("Registry update failed: " + (e.message || e), true);
  }
}

async function onboardSign(name) {
  if (!confirm(`Sign manifest ${name} with CBAP_MANIFEST_KEY?`)) return;
  try {
    const res = await api("/api/onboard/sign", {
      method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({name})
    });
    toast("Manifest signed");
    $("ob-probe-result").textContent = JSON.stringify(res, null, 2);
    await onboardList();
  } catch (e) {
    toast("Sign failed: " + (e.message || e), true);
  }
}

let historyDevice = "";

function updateHistoryDevices(devices) {
  const sel = $("history-device");
  const wanted = historyDevice || sel.value;
  sel.replaceChildren();
  const none = document.createElement("option");
  none.value = ""; none.textContent = "no device"; sel.appendChild(none);
  for (const d of devices) {
    const o = document.createElement("option");
    o.value = d.device_id || "";
    o.textContent = d.device_id || "unknown";
    sel.appendChild(o);
  }
  if (wanted && [...sel.options].some(o => o.value === wanted)) sel.value = wanted;
  historyDevice = sel.value;
}

function svgEl(tag, attrs) {
  const n = document.createElementNS("http://www.w3.org/2000/svg", tag);
  for (const [k, v] of Object.entries(attrs || {})) n.setAttribute(k, String(v));
  return n;
}

function renderHistory(samples) {
  const root = $("history-chart");
  root.replaceChildren();
  if (!samples.length) {
    root.appendChild(el("div", "empty", "No history samples yet."));
    return;
  }
  const width = 1000, height = 150, pad = 10;
  const svg = svgEl("svg", {viewBox: `0 0 ${width} ${height}`, preserveAspectRatio: "none"});
  svg.appendChild(svgEl("line", {x1: pad, y1: height - pad, x2: width - pad, y2: height - pad,
                                 stroke: "#334155", "stroke-width": 1}));
  const n = samples.length;
  const maxPending = Math.max(1, ...samples.map(s => Number(s.pending) || 0));
  const x = (i) => pad + (width - pad * 2) * (n === 1 ? 0.5 : i / (n - 1));
  const y = (v) => height - pad - (height - pad * 2) * Math.max(0, Math.min(1, v));
  const lines = [
    {key: "online", color: "#4ade80", label: "online", scale: v => v ? 1 : 0},
    {key: "lease", color: "#fbbf24", label: "lease", scale: v => v ? 1 : 0},
    {key: "pending", color: "#fb7185", label: "pending", scale: v => (Number(v) || 0) / maxPending},
    {key: "health", color: "#2dd4bf", label: "health", scale: v => v ? 1 : 0},
  ];
  for (const line of lines) {
    const pts = samples.map((s, i) => `${x(i)},${y(line.scale(s[line.key]))}`).join(" ");
    svg.appendChild(svgEl("polyline", {
      points: pts, fill: "none", stroke: line.color,
      "stroke-width": line.key === "pending" ? 1.4 : 2, opacity: line.key === "pending" ? 0.8 : 0.95
    }));
  }
  root.appendChild(svg);
  const legend = el("div", "history-legend");
  for (const line of lines) {
    const item = el("span");
    const swatch = el("i");
    swatch.style.background = line.color;
    item.append(swatch, document.createTextNode(line.label));
    legend.appendChild(item);
  }
  root.appendChild(legend);
}

async function loadHistory() {
  const sel = $("history-device");
  const dev = sel.value;
  historyDevice = dev;
  if (!dev) { renderHistory([]); return; }
  try {
    const res = await api(`/api/history?device_id=${encodeURIComponent(dev)}&limit=180`);
    renderHistory(res.samples || []);
  } catch (e) {
    renderHistory([]);
  }
}

$("notify-read").addEventListener("click", async () => {
  try {
    await api("/api/notifications/read", {method: "POST",
      headers: {"Content-Type": "application/json"}, body: "{}"});
    await load();
  } catch (e) { toast("Notification update failed: " + (e.message || e), true); }
});
$("notify-bell").addEventListener("click", () => {
  $("notifications").scrollIntoView({behavior: "smooth", block: "center"});
});

$("history-device").addEventListener("change", loadHistory);
$("ob-reload").addEventListener("click", reloadRegistry);
$("ob-scan").addEventListener("click", onboardScan);
$("ob-create").addEventListener("click", onboardCreate);
$("ob-refresh-list").addEventListener("click", onboardList);
$("ob-probe").addEventListener("click", onboardProbe);

$("refresh").addEventListener("click", load);
$("global-estop").addEventListener("click", () => doEstop(null, "all devices"));
$("resume-all").addEventListener("click", () => doResume(null, true));
$("logout").addEventListener("click", async () => {
  try { await api("/api/logout", {method: "POST", headers: {"Content-Type": "application/json"}, body: "{}"}); } catch (_) {}
  showLogin();
});
$("login-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const token = $("login-token").value;
  $("login-token").value = "";
  try {
    const res = await fetch("/api/login", {
      method: "POST",
      credentials: "same-origin",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({token})
    });
    const body = await res.json().catch(() => ({}));
    if (!res.ok || !body.ok) throw new Error(body.error || `HTTP ${res.status}`);
    hideLogin();
    await refreshSession();
    await load();
  } catch (e) {
    $("login-error").textContent = String(e.message || e);
  }
});

(async () => {
  try {
    const s = await fetch("/api/session", {credentials: "same-origin"}).then(r => r.json());
    if (s.authenticated) { hideLogin(); setOperator(s.operator); await load(); await onboardList(); }
    else showLogin();
  } catch (_) {
    showLogin();
  }
  setInterval(() => { if (!document.hidden && authed) load(); }, 2000);
})();
