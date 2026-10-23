#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Live dashboard: CBAP Kernel controlling a real external MCP Minecraft agent."""

from __future__ import annotations

import argparse
import json
import os
import signal
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from drivers.mcp.driver import MCPDriver
from kernel.legacy_runtime.client import CBAPClient
from kernel.legacy_runtime.server import KernelServer

KEEPALIVE: list = []
RUNTIME: dict = {"lock": threading.RLock(), "driver": None,
                 "kernel": None, "client": None, "fd": None}
DASH: dict = {
    "started_at": int(time.time() * 1000),
    "phase": "booting",
    "error": None,
    "device": None,
    "health": None,
    "state": None,
    "cbap": [],
    "tool_history": [],
    "planner": [],
    "stats": {},
}


def now_ms() -> int:
    return int(time.time() * 1000)


def add_cbap(kind: str, **kw) -> None:
    rec = {"t": now_ms(), "kind": kind}
    rec.update(kw)
    DASH["cbap"] = (DASH["cbap"] + [rec])[-24:]


def record_result(rid: str, result: dict, label: str) -> None:
    DASH["cbap"] = [
        (dict(x, ok=bool(result.get("ok")),
              result=result.get("payload") or result.get("error")))
        if x.get("id") == rid else x
        for x in DASH["cbap"]
    ]
    add_cbap("result", label=label, id=rid, ok=bool(result.get("ok")),
             result=result.get("payload") or result.get("error"))


def refresh(driver: MCPDriver, state=None) -> None:
    try:
        DASH["health"] = driver.health()
        DASH["stats"] = dict(driver.stats)
        DASH["tool_history"] = list(driver.stats.get("tool_history") or [])[-10:]
        if state is None:
            state = driver.wait_state(0.05)
        if state:
            DASH["state"] = state
    except Exception as e:
        DASH["error"] = str(e)


HTML = r"""<!doctype html>
<html lang="zh">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Cyberdyne // CBAP MCP Peripheral</title>
<style>
  :root{
    --bg:#070b0d; --panel:#0c1519; --line:#1d3a42; --text:#d7f7ef;
    --dim:#6f9a97; --green:#59f2b2; --cyan:#53d9ff; --amber:#ffcf6a;
    --red:#ff6b6b;
  }
  *{box-sizing:border-box}
  body{
    margin:0;background:
      radial-gradient(1200px 600px at 20% -10%,#0c2b2d 0,transparent 55%),
      radial-gradient(900px 500px at 100% 0%,#102b3a 0,transparent 50%),
      var(--bg);
    color:var(--text);font-family:"SFMono-Regular",Consolas,"Liberation Mono",monospace;
    min-height:100vh;
  }
  body:before{
    content:"";position:fixed;inset:0;pointer-events:none;opacity:.18;
    background:repeating-linear-gradient(0deg,transparent 0 3px,#000 3px 4px);
  }
  .wrap{max-width:1440px;margin:0 auto;padding:30px 34px 24px;position:relative}
  header{display:flex;justify-content:space-between;align-items:flex-start;gap:20px}
  .eyebrow{color:var(--cyan);letter-spacing:.22em;font-size:11px;text-transform:uppercase}
  h1{font-size:32px;line-height:1.15;margin:8px 0 7px;letter-spacing:-.02em}
  h1 span{color:var(--green)}
  .sub{color:var(--dim);font-size:12px;line-height:1.7}
  .badge{
    border:1px solid #2b6b5b;background:#0d2b25;color:var(--green);
    padding:9px 13px;border-radius:999px;font-size:11px;letter-spacing:.12em;
    white-space:nowrap;box-shadow:0 0 22px #1aff9a18;
  }
  .dot{display:inline-block;width:7px;height:7px;border-radius:50%;
    background:var(--green);box-shadow:0 0 10px var(--green);margin-right:7px}
  .grid{display:grid;grid-template-columns:1.05fr .95fr;gap:16px;margin-top:24px}
  .panel{
    background:linear-gradient(180deg,#0c171b,#0a1114);
    border:1px solid var(--line);border-radius:10px;padding:17px 18px;
    box-shadow:0 18px 50px #0008;position:relative;overflow:hidden;
  }
  .panel:before{content:"";position:absolute;left:0;right:0;top:0;height:1px;
    background:linear-gradient(90deg,transparent,var(--green),transparent);opacity:.6}
  .panel h2{font-size:11px;letter-spacing:.18em;color:var(--dim);
    margin:0 0 13px;font-weight:500;text-transform:uppercase}
  .device{display:flex;justify-content:space-between;gap:12px;align-items:center}
  .device .id{font-size:18px;color:var(--cyan)}
  .pill{font-size:10px;border:1px solid #29505a;color:var(--green);
    padding:4px 8px;border-radius:4px;background:#0b2524}
  .kv{display:grid;grid-template-columns:110px 1fr;gap:8px 12px;margin-top:15px;font-size:12px}
  .kv .k{color:var(--dim)} .kv .v{color:var(--text)}
  .metrics{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-top:15px}
  .metric{border:1px solid #173139;background:#091216;border-radius:7px;padding:10px}
  .metric .n{font-size:20px;color:var(--green)} .metric .l{font-size:9px;color:var(--dim);margin-top:4px;letter-spacing:.08em}
  .panel.wide{grid-column:1/-1}
  .log{height:300px;overflow:auto;font-size:11px;line-height:1.55}
  .row{display:grid;grid-template-columns:66px 1fr 44px;gap:9px;padding:7px 0;border-bottom:1px solid #11252a}
  .row:last-child{border-bottom:0}.t{color:#4e7777}.ok{color:var(--green)}.bad{color:var(--red)}
  .muted{color:var(--dim)} .mono{font-family:inherit}
  .flow{display:flex;align-items:center;gap:8px;margin-top:12px;flex-wrap:wrap;font-size:10px;color:var(--dim)}
  .node{border:1px solid #24525a;background:#0a1c20;border-radius:5px;padding:6px 9px;color:var(--text)}
  .arrow{color:var(--green)}
  .footer{margin-top:17px;color:#426568;font-size:10px;display:flex;justify-content:space-between;gap:12px}
  .state-line{display:flex;gap:10px;align-items:baseline;margin-top:14px}
  .state-line .big{font-size:25px;color:#eafff8}
  .state-line .unit{color:var(--dim);font-size:11px}
  .blocks{display:flex;gap:6px;flex-wrap:wrap;margin-top:10px}
  .block{font-size:10px;color:var(--cyan);border:1px solid #1b4652;background:#081c24;padding:4px 7px;border-radius:4px}
  .empty{color:#34575a;font-size:11px;padding:16px 0}
  @media(max-width:1000px){.grid{grid-template-columns:1fr}.wrap{padding:20px}}
</style>
</head>
<body><div class="wrap">
  <header>
    <div>
      <div class="eyebrow">Cyberdyne Bridge / CBAP-D</div>
      <h1>REAL MCP PERIPHERAL <span>ONLINE</span></h1>
      <div class="sub">Kernel → CBAP-D → external MCP server → real Mineflayer bot<br>
      small MCP place patch (block + hotbar); everything else via public MCP tools.</div>
    </div>
    <div class="badge"><span class="dot"></span>LIVE / KERNEL ATTACHED</div>
  </header>

  <div class="grid">
    <section class="panel">
      <h2>01 · Peripheral</h2>
      <div class="device">
        <div class="id" id="device-id">mcp://mc/MCPBody</div>
        <div class="pill" id="device-type">minecraft-mcp-agent</div>
      </div>
      <div class="kv">
        <div class="k">transport</div><div class="v">MCP stdio · JSON-RPC 2.0</div>
        <div class="k">backend</div><div class="v" id="backend">mineflayer-mcp 0.2.0</div>
        <div class="k">health</div><div class="v" id="health"><span class="ok">ok</span></div>
        <div class="k">state age</div><div class="v" id="age">—</div>
      </div>
      <div class="metrics">
        <div class="metric"><div class="n" id="m-health">—</div><div class="l">HEALTH</div></div>
        <div class="metric"><div class="n" id="m-food">—</div><div class="l">FOOD</div></div>
        <div class="metric"><div class="n" id="m-tools">0</div><div class="l">MCP TOOL CALLS</div></div>
        <div class="metric"><div class="n" id="m-seq">0</div><div class="l">STATE SEQ</div></div>
      </div>
      <div class="state-line"><span class="big" id="pos">connecting…</span><span class="unit">feet position</span></div>
      <div class="blocks" id="blocks"></div>
      <div class="flow" style="margin-top:10px">
        <span class="node" id="inventory">inventory · —</span>
      </div>
      <div class="flow" style="margin-top:10px">
        <span class="node" id="last-write">last CBAP write · —</span>
        <span class="node" id="last-tool">last MCP tool · —</span>
      </div>
      <div class="flow" style="margin-top:10px">
        <span class="node" id="planner-line">external planner · waiting</span>
      </div>
    </section>

    <section class="panel">
      <h2>02 · CBAP Syscalls</h2>
      <div class="flow">
        <span class="node">Agent</span><span class="arrow">→</span>
        <span class="node">Kernel</span><span class="arrow">→</span>
        <span class="node">CBAP-D</span><span class="arrow">→</span>
        <span class="node">MCP stdio</span>
      </div>
      <div class="log" id="cbap-log"><div class="empty">waiting for syscalls…</div></div>
    </section>

    <section class="panel">
      <h2>03 · MCP Tool Traffic</h2>
      <div class="log" id="tool-log"><div class="empty">waiting for tool calls…</div></div>
    </section>

    <section class="panel">
      <h2>04 · Contract</h2>
      <div class="kv">
        <div class="k">read</div><div class="v">observe / status / inventory</div>
        <div class="k">write</div><div class="v">move / dig / place / chat / attack / use</div>
        <div class="k">poll</div><div class="v">CBAP state frames, 500 ms</div>
        <div class="k">estop</div><div class="v">terminate MCP process + disconnect bot</div>
        <div class="k">side effects</div><div class="v">only public MCP tools</div>
      </div>
      <div class="flow" style="margin-top:18px">
        <span class="node">MCP place patch (block + hotbar)</span>
        <span class="node">no bridge.py edit</span>
        <span class="node">no node/server.js edit</span>
      </div>
      <div class="footer"><span>CBAP / v1 draft</span><span id="clock">—</span></div>
    </section>

    <section class="panel wide">
      <h2>05 · External LLM Planner</h2>
      <div class="flow">
        <span class="node">model · Qwen3-4B-Instruct</span>
        <span class="node">planner · independent process</span>
        <span class="node">executor · CBAP dashboard</span>
      </div>
      <div class="log" id="planner-log" style="margin-top:10px;height:150px">
        <div class="empty">waiting for external planner…</div>
      </div>
    </section>
  </div>
</div>
<script>
async function tick(){
  try{
    const r=await fetch('/api/state',{cache:'no-store'}); const s=await r.json();
    const st=s.state||{}, body=st.body||{};
    const pos=st.pos||[];
    if(pos.length===3) document.getElementById('pos').textContent =
      `x ${Number(pos[0]).toFixed(2)}   y ${Number(pos[1]).toFixed(2)}   z ${Number(pos[2]).toFixed(2)}`;
    document.getElementById('m-health').textContent = st.hp ?? '—';
    document.getElementById('m-food').textContent = st.food ?? '—';
    document.getElementById('m-tools').textContent = (s.stats&&s.stats.tool_calls)||0;
    document.getElementById('m-seq').textContent = st.seq ?? '—';
    document.getElementById('age').textContent = (s.health&&s.health.state_age_ms!=null)?`${s.health.state_age_ms} ms`:'—';
    const h=s.health||{};
    document.getElementById('health').innerHTML = h.ok ? '<span class="ok">ok · watchdog within bounds</span>' : '<span class="bad">not ok</span>';
    document.getElementById('device-id').textContent=(s.device&&s.device.device_id)||'—';
    document.getElementById('device-type').textContent=(s.device&&s.device.type)||'—';
    const writes=(s.cbap||[]).filter(x=>x.kind==='result' && x.label);
    if(writes.length){
      const w=writes[writes.length-1];
      document.getElementById('last-write').textContent=`last CBAP write · ${w.label} · ${w.ok?'ok':'error'}`;
    }
    const th=(s.tool_history||[]); if(th.length){
      const t=th[th.length-1];
      document.getElementById('last-tool').textContent=`last MCP tool · ${t.tool} · ${t.ok?'ok':'error'}`;
    }
    const items=st.items||{};
    const inv=Object.entries(items).map(([k,v])=>`${k} × ${v}`).join('  ·  ');
    document.getElementById('inventory').textContent = `inventory · ${inv || 'empty'}`;
    const pl=s.planner||[];
    if(pl.length){
      const p=pl[pl.length-1];
      document.getElementById('planner-line').textContent=
        `external planner · ${p.model||'LLM'} · step ${p.step ?? '—'} · ${p.action||'—'}`;
    }
    document.getElementById('planner-log').innerHTML = pl.length?pl.slice().reverse().map(p=>
      `<div class="row"><span class="t">${new Date(p.t).toLocaleTimeString()}</span>
       <span><span class="muted">step ${p.step ?? '—'}</span> · <b>${p.action||'—'}</b>
       ${p.reason?`<span class="muted"> — ${String(p.reason).slice(0,120)}</span>`:''}
       ${p.result?`<span class="muted"> · ${String(p.result).slice(0,100)}</span>`:''}</span>
       <span class="${p.ok?'ok':'bad'}">${p.ok?'ok':'—'}</span></div>`
    ).join(''):'<div class="empty">waiting for external planner…</div>';
    const blocks=st.blocks||[];
    document.getElementById('blocks').innerHTML = blocks.slice(0,6).map(b=>{
      const p=b.position||{}; return `<span class="block">${b.name} · ${p.x},${p.y},${p.z}</span>`;
    }).join('') || '<span class="empty">no block scan yet</span>';
    const log=s.cbap||[];
    document.getElementById('cbap-log').innerHTML = log.length?log.map(x=>{
      const ok=x.ok===true?'ok':x.ok===false?'bad':'';
      return `<div class="row"><span class="t">${new Date(x.t).toLocaleTimeString()}</span>
        <span><span class="muted">${x.kind}</span> ${x.op?`· <b>${x.op}</b>`:''} ${x.label?`· ${x.label}`:''}
        ${x.id?`<span class="muted"> ${x.id}</span>`:''}</span>
        <span class="${ok}">${ok}</span></div>`;
    }).join(''):'<div class="empty">waiting for syscalls…</div>';
    const tl=s.tool_history||[];
    document.getElementById('tool-log').innerHTML = tl.length?tl.slice().reverse().map(x=>{
      const args=JSON.stringify(x.args||{}).slice(0,70);
      return `<div class="row"><span class="t">${new Date(x.t).toLocaleTimeString()}</span>
        <span><b>${x.tool}</b> <span class="muted">${args}</span></span>
        <span class="${x.ok?'ok':'bad'}">${x.ok?'ok':'err'}</span></div>`;
    }).join(''):'<div class="empty">waiting for tool calls…</div>';
    document.getElementById('clock').textContent=new Date().toLocaleString();
  }catch(e){}
}
tick(); setInterval(tick,500);
</script>
</body></html>"""


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.startswith("/api/state"):
            data = json.dumps(DASH, ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        data = HTML.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _json(self, obj, status=200):
        data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        try:
            body = json.loads(self.rfile.read(n).decode("utf-8") or "{}")
        except Exception:
            self._json({"ok": False, "error": "bad json"}, 400)
            return
        c = RUNTIME.get("client")
        fd = RUNTIME.get("fd")
        if c is None or fd is None:
            self._json({"ok": False, "error": "runtime not ready"}, 503)
            return
        try:
            with RUNTIME["lock"]:
                if self.path.startswith("/api/planner"):
                    rec = {"t": now_ms()}
                    for k in ("step", "model", "action", "reason", "ok",
                              "result", "thought"):
                        if k in body:
                            rec[k] = body.get(k)
                    DASH["planner"] = (DASH["planner"] + [rec])[-24:]
                    self._json({"ok": True})
                    return
                if self.path.startswith("/api/act"):
                    lease = c.lease(fd, ttl_ms=120000)
                    if not lease.get("ok"):
                        self._json({"ok": False, "stage": "lease",
                                    "error": lease.get("error")}, 409)
                        return
                    frame = body.get("frame") or body
                    rid, ack, result = c.write(fd, frame, deadline_ms=120000)
                    label = str(frame.get("op") or "action")
                    add_cbap("write", label=label, op=frame.get("op"), id=rid)
                    record_result(rid, result, label)
                    refresh(RUNTIME.get("driver"))
                    self._json({"ok": bool(result.get("ok")),
                                "id": rid, "ack": ack, "result": result})
                    return
                if self.path.startswith("/api/tool"):
                    driver = RUNTIME.get("driver")
                    name = body.get("name") or "status"
                    out = driver.tool(name, body.get("args") or {})
                    self._json({"ok": True, "result": out})
                    return
                if self.path.startswith("/api/observe"):
                    driver = RUNTIME.get("driver")
                    target = body.get("target") or "blocks"
                    kwargs = {k: v for k, v in body.items()
                              if k not in ("target",)}
                    out = driver.observe(target, **kwargs)
                    self._json({"ok": True, "result": out})
                    return
                if self.path.startswith("/api/read"):
                    channel = body.get("channel")
                    out = c.read(fd, channel=channel, timeout_ms=5000)
                    self._json({"ok": bool(out.get("ok")), "result": out})
                    return
                if self.path.startswith("/api/estop"):
                    out = c.estop(fd, reason=body.get("reason") or "dashboard")
                    self._json({"ok": bool(out.get("ok")), "result": out})
                    return
            self._json({"ok": False, "error": "unknown endpoint"}, 404)
        except Exception as e:
            self._json({"ok": False, "error": str(e)}, 500)

    def log_message(self, fmt, *args):
        pass


def run_demo(args) -> None:
    DASH["phase"] = "starting external MCP server"
    driver = MCPDriver(
        server_path=args.server_path,
        host=args.mc_host, port=args.mc_port,
        username=args.username, version=args.mc_version,
        node_bin=args.node,
        lock_path=args.lock or f"/tmp/cbap-mcp-dashboard-{os.getpid()}.lock",
        poll_interval=0.5, connect_timeout=45.0,
    )
    driver.connect()
    DASH["device"] = driver.describe()
    refresh(driver)
    DASH["phase"] = "starting CBAP kernel"
    tmp = tempfile.mkdtemp(prefix="cbap-mcp-dash-")
    kernel = KernelServer(drivers=[driver],
                          socket_path=os.path.join(tmp, "cbap.sock"),
                          audit_path=os.path.join(tmp, "audit.jsonl"))
    if not kernel.start():
        raise RuntimeError("kernel did not start")
    client = CBAPClient(os.path.join(tmp, "cbap.sock"), agent_id="mcp-dashboard")
    client.connect(); client.hello()
    add_cbap("hello", label="real MCP agent registered")

    devices = client.device_list()["payload"]["devices"]
    add_cbap("device_list", result=devices)
    fd = client.open(args.device_id)["payload"]["fd"]
    add_cbap("open", label=args.device_id, result={"fd": fd})
    read = client.read(fd, "body", 3000)
    add_cbap("read", label="body", result=read.get("payload") or read.get("error"))
    lease = client.lease(fd)
    add_cbap("lease", result=lease.get("payload") or lease.get("error"))

    # Real writes: a chat line and a real relative move through the MCP server.
    actions = [
        ("say", {"channel": "chat", "op": "say",
                 "args": {"text": "CBAP collar attached to real MCP agent"}}),
        ("move", {"channel": "body", "op": "move",
                  "args": {"dir": [2, 0], "ms": 1000}}),
    ]
    for label, frame in actions:
        rid = client.request("write", {"fd": fd, "frame": frame,
                                       "deadline_ms": 60000})
        add_cbap("write", label=label, op=frame["op"], id=rid)
        ack = client.wait_ack(rid, 10)
        add_cbap("ack", label=label, id=rid, result={"state": ack.get("state")})
        res = client.wait(rid, 60000)
        record_result(rid, res, label)
        refresh(driver)

    DASH["phase"] = "live"
    refresh(driver)
    add_cbap("state", label="live CBAP state frames")
    KEEPALIVE.extend([driver, kernel, client])
    RUNTIME.update(driver=driver, kernel=kernel, client=client, fd=fd)
    threading.Thread(target=_refresh_loop, args=(driver,), daemon=True).start()


def _refresh_loop(driver: MCPDriver) -> None:
    while True:
        refresh(driver)
        time.sleep(0.4)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--server-path", default=os.environ.get("CBAP_MCP_SERVER", ""))
    ap.add_argument("--node", default=os.environ.get("CBAP_NODE_BIN", "node"))
    ap.add_argument("--mc-host", default="127.0.0.1")
    ap.add_argument("--mc-port", type=int, default=25565)
    ap.add_argument("--mc-version", default="1.21.1")
    ap.add_argument("--username", default="MCPBody")
    ap.add_argument("--device-id", default="mcp://mc/MCPBody")
    ap.add_argument("--lock", default=None)
    ap.add_argument("--http-port", type=int, default=8099)
    args = ap.parse_args()
    if not args.server_path:
        print("--server-path or CBAP_MCP_SERVER is required", file=sys.stderr)
        return 2
    try:
        run_demo(args)
    except Exception as e:
        DASH["phase"] = "error"
        DASH["error"] = str(e)
        print(f"demo setup failed: {e}", file=sys.stderr)
        return 1
    srv = ThreadingHTTPServer(("127.0.0.1", args.http_port), Handler)
    print(f"dashboard: http://127.0.0.1:{args.http_port}", flush=True)

    def stop(*_):
        # HTTPServer.shutdown() must not be called from the serve_forever thread.
        threading.Thread(target=srv.shutdown, daemon=True).start()
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    srv.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
