#!/usr/bin/env node
/**
 * Mindcraft -> line-JSON CBAP adapter.
 *
 * Uses MindServer's public socket.io API:
 *   listen-to-agents -> state-update
 *   send-message     -> prompt the autonomous agent
 *   stop-agent       -> stop
 *
 * This adapter does NOT inject low-level actions. Mindcraft remains the
 * autonomous decision maker; CBAP gets state, prompt delivery, and stop.
 */
import net from 'net';
import fs from 'fs';
import { createRequire } from 'module';

const args = Object.fromEntries(process.argv.slice(2).reduce((a, x, i, arr) => {
  if (x.startsWith('--')) a.push([x.slice(2), arr[i + 1]]);
  return a;
}, []));
const PORT = Number(args.port || 8080);
const AGENT = args.agent || 'Mindy';
const SOCKET = args.socket || '/tmp/mindcraft-cbap.sock';
const MODULE_ROOT = args.moduleRoot || '/home/bzys17mintstart/external/mindcraft/package.json';
const require = createRequire(MODULE_ROOT);
const { io } = require('socket.io-client');

let seq = 0;
let latest = null;
const clients = new Set();
let stopping = false;

function send(sock, obj) {
  try { sock.write(JSON.stringify(obj) + '\n'); } catch {}
}
function broadcast(state) {
  latest = state;
  const line = JSON.stringify(state) + '\n';
  for (const c of clients) { try { c.write(line); } catch {} }
}
function transform(states) {
  const s = states && states[AGENT];
  if (!s || !s.gameplay) return null;
  const p = s.gameplay.position || {};
  const inv = s.inventory || {};
  const items = inv.counts || {};
  return {
    type: 'state', seq: ++seq, t: Date.now(),
    pos: [Number(p.x || 0), Number(p.y || 0), Number(p.z || 0)],
    hp: Number(s.gameplay.health ?? 20),
    food: Number(s.gameplay.hunger ?? 20),
    onGround: true,
    held: inv.equipment?.mainHand || null,
    items,
    chat: [],
    acting: s.action?.current || null,
    activity: s.action || null,
    mode: s.action?.kind || null,
    players: s.nearby?.humanPlayers || [],
    bot: AGENT
  };
}

const socket = io(`http://localhost:${PORT}`, { transports: ['websocket'] });
socket.on('connect', () => {
  console.log('adapter connected to MindServer');
  socket.emit('listen-to-agents');
});
socket.on('agents-status', (agents) => {
  console.log('agents', JSON.stringify(agents));
  const me = agents.find(a => a.name === AGENT);
  if (me && !me.in_game) {
    for (const c of clients) {
      send(c, {type: 'event', kind: 'device_offline', why: 'Mindcraft agent is not in game'});
      setTimeout(() => { try { c.end(); } catch {} }, 300);
    }
  }
});
socket.on('state-update', (states) => {
  const st = transform(states);
  if (st) broadcast(st);
});
socket.on('bot-output', (agent, message) => {
  console.log('bot-output', agent, String(message).slice(0, 300));
});
socket.on('connect_error', (e) => console.error('adapter connect_error', e.message));
socket.on('disconnect', () => console.log('adapter disconnected from MindServer'));

try { fs.unlinkSync(SOCKET); } catch {}
const server = net.createServer((sock) => {
  clients.add(sock);
  if (latest) send(sock, latest);
  let buf = '';
  sock.on('data', (chunk) => {
    buf += chunk.toString('utf8');
    let i;
    while ((i = buf.indexOf('\n')) >= 0) {
      const line = buf.slice(0, i); buf = buf.slice(i + 1);
      if (!line.trim()) continue;
      let msg;
      try { msg = JSON.parse(line); } catch { continue; }
      const cmd = msg.cmd;
      if (cmd === 'state') {
        if (latest) send(sock, latest);
        else send(sock, { type: 'event', kind: 'cmdResult', cmd: 'state', ok: false, why: 'no state yet' });
        continue;
      }
      if (cmd === 'watch_items' || cmd === 'watch' || cmd === 'watch_blocks') {
        send(sock, { type: 'event', kind: 'cmdResult', cmd, ok: true });
        continue;
      }
      if (cmd === 'prompt') {
        const text = String(msg.text || '');
        socket.emit('send-message', AGENT, { from: 'cbap', message: text });
        send(sock, { type: 'event', kind: 'cmdResult', cmd: 'prompt', ok: true,
                     delivered: true, why: 'delivered to Mindcraft autonomous planner' });
        continue;
      }
      if (cmd === 'stop') {
        stopping = true;
        socket.emit('stop-agent', AGENT);
        send(sock, { type: 'event', kind: 'cmdResult', cmd: 'stop', ok: true });
        setTimeout(() => {
          for (const c of clients) { try { c.end(); } catch {} }
          try { server.close(); } catch {}
        }, 500);
        setTimeout(() => process.exit(0), 1200);
        continue;
      }
      send(sock, { type: 'event', kind: 'cmdResult', cmd: cmd || 'unknown', ok: false, why: 'unsupported adapter command' });
    }
  });
  sock.on('error', () => clients.delete(sock));
  sock.on('close', () => clients.delete(sock));
});
server.listen(SOCKET, () => console.log('adapter listening', SOCKET));
process.on('SIGINT', () => { server.close(); process.exit(0); });
process.on('SIGTERM', () => { server.close(); process.exit(0); });
