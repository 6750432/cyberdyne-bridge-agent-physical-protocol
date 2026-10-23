#!/usr/bin/env node
/**
 * Voyager HTTP bridge -> CBAP line-JSON adapter.
 * Exposes state, exec (JS), say, forward, stop.  No LLM here.
 */
import net from 'net';
import fs from 'fs';

const args = Object.fromEntries(process.argv.slice(2).reduce((a, x, i, arr) => {
  if (x.startsWith('--')) a.push([x.slice(2), arr[i + 1]]);
  return a;
}, []));
const BRIDGE = args.bridge || 'http://127.0.0.1:3000';
const SOCKET = args.socket || '/tmp/voyager-cbap.sock';
const PORT = Number(args.port || 25565);

let seq = 0, latest = null, stopped = false;
const clients = new Set();

function decode(v) {
  while (typeof v === 'string') v = JSON.parse(v);
  return v;
}
async function jpost(path, payload) {
  const r = await fetch(BRIDGE + path, {
    method: 'POST', headers: {'content-type': 'application/json'},
    body: JSON.stringify(payload || {})
  });
  const text = await r.text();
  let data; try { data = decode(JSON.parse(text)); } catch { data = text; }
  return {status: r.status, data};
}
async function state() {
  try {
    const r = await fetch(BRIDGE + '/state');
    if (!r.ok) return null;
    const text = await r.text();
    const arr = decode(JSON.parse(text));
    const obs = arr.find(e => e[0] === 'observe');
    if (!obs) return null;
    const d = obs[1] || {};
    const st = d.status || {};
    const p = st.position || {};
    return {
      type: 'state', seq: ++seq, t: Date.now(),
      pos: [Number(p.x || 0), Number(p.y || 0), Number(p.z || 0)],
      hp: Number(st.health ?? 20), food: Number(st.food ?? 20),
      onGround: !!st.onGround, held: st.equipment?.[4] || null,
      items: d.inventory || {}, chat: [],
      acting: null, bot: st.name || 'bot'
    };
  } catch (e) { return null; }
}
function send(s, o) { try { s.write(JSON.stringify(o) + '\n'); } catch {} }
function broadcast(st) {
  latest = st;
  for (const c of clients) send(c, st);
}
async function runCode(code) {
  const r = await jpost('/step', {code, programs: ''});
  return r;
}
const timer = setInterval(async () => {
  if (stopped || !clients.size) return;
  const st = await state();
  if (st) broadcast(st);
}, 1000);

try { fs.unlinkSync(SOCKET); } catch {}
const server = net.createServer((sock) => {
  clients.add(sock);
  if (latest) send(sock, latest);
  let buf = '';
  sock.on('data', async (chunk) => {
    buf += chunk.toString('utf8');
    let i;
    while ((i = buf.indexOf('\n')) >= 0) {
      const line = buf.slice(0, i); buf = buf.slice(i + 1);
      if (!line.trim()) continue;
      let msg; try { msg = JSON.parse(line); } catch { continue; }
      const cmd = msg.cmd;
      try {
        if (cmd === 'state') {
          const st = await state();
          if (st) { latest = st; send(sock, st); }
          else send(sock, {type:'event', kind:'cmdResult', cmd:'state', ok:false, why:'no bot state'});
        } else if (cmd === 'watch_items' || cmd === 'watch' || cmd === 'watch_blocks') {
          send(sock, {type:'event', kind:'cmdResult', cmd, ok:true});
        } else if (cmd === 'exec') {
          const r = await runCode(String(msg.code || ''));
          send(sock, {type:'event', kind:'cmdResult', cmd:'exec', ok:r.status===200, why:r.status===200?undefined:`HTTP ${r.status}`});
          const st = await state(); if (st) broadcast(st);
        } else if (cmd === 'say') {
          const text = String(msg.text || '');
          const code = `bot.chat(${JSON.stringify(text)});`;
          const r = await runCode(code);
          send(sock, {type:'event', kind:'cmdResult', cmd:'say', ok:r.status===200, why:r.status===200?undefined:`HTTP ${r.status}`});
          const st = await state(); if (st) broadcast(st);
        } else if (cmd === 'forward') {
          const code = "bot.setControlState('forward', true); await bot.waitForTicks(20); bot.setControlState('forward', false);";
          const r = await runCode(code);
          send(sock, {type:'event', kind:'cmdResult', cmd:'forward', ok:r.status===200, why:r.status===200?undefined:`HTTP ${r.status}`});
          const st = await state(); if (st) broadcast(st);
        } else if (cmd === 'stop') {
          stopped = true;
          await jpost('/stop', {});
          send(sock, {type:'event', kind:'cmdResult', cmd:'stop', ok:true});
          setTimeout(() => { for (const c of clients) { try { c.end(); } catch {} } try { server.close(); } catch {} }, 300);
          setTimeout(() => process.exit(0), 900);
        } else {
          send(sock, {type:'event', kind:'cmdResult', cmd:cmd || 'unknown', ok:false, why:'unsupported'});
        }
      } catch (e) {
        send(sock, {type:'event', kind:'cmdResult', cmd, ok:false, why:String(e)});
      }
    }
  });
  sock.on('error', () => clients.delete(sock));
  sock.on('close', () => clients.delete(sock));
});
server.listen(SOCKET, () => console.log('listening', SOCKET, 'bridge', BRIDGE));
process.on('SIGTERM', () => { clearInterval(timer); process.exit(0); });
process.on('SIGINT', () => { clearInterval(timer); process.exit(0); });
