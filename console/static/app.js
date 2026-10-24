"use strict";

const token = document.querySelector('meta[name="cbap-console-token"]').content;
const $ = (id) => document.getElementById(id);
let loading = false;

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
  const headers = Object.assign({"X-CBAP-Token": token}, options.headers || {});
  const res = await fetch(path, Object.assign({}, options, {headers}));
  let body = null;
  try { body = await res.json(); } catch (_) {}
  if (!res.ok || !body || body.ok === false) {
    throw new Error((body && body.error) || `HTTP ${res.status}`);
  }
  return body;
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
    card.appendChild(actions);
    root.appendChild(card);
  }
}

function auditDetail(row) {
  const parts = [];
  for (const [k, v] of Object.entries(row)) {
    if (k === "t" || k === "event") continue;
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
  if (loading) return;
  loading = true;
  try {
    const [status, audit] = await Promise.all([api("/api/status"), api("/api/audit?limit=80")]);
    setConnection(true, "kernel connected");
    renderDevices(status.devices || []);
    renderAudit(audit.rows || []);
  } catch (e) {
    setConnection(false, "kernel unavailable");
    toast(String(e.message || e), true);
  } finally {
    loading = false;
  }
}

async function doEstop(fd, name) {
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

$("refresh").addEventListener("click", load);
$("global-estop").addEventListener("click", () => doEstop(null, "all devices"));
load();
setInterval(() => { if (!document.hidden) load(); }, 2000);
