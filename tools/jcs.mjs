#!/usr/bin/env node
/* RFC 8785-style JSON canonicalization for CBAP replay fingerprints.
 *
 * Usage:
 *   node tools/jcs.mjs --canonical '{"b":1,"a":2}'
 *   node tools/jcs.mjs --hash '{"b":1,"a":2}'
 *   echo '{"b":1,"a":2}' | node tools/jcs.mjs --hash
 */
import crypto from 'node:crypto';
import fs from 'node:fs';

function canonical(value) {
  if (value === null) return 'null';
  if (value === true) return 'true';
  if (value === false) return 'false';
  if (typeof value === 'number') {
    if (!Number.isFinite(value)) throw new Error('JCS does not allow NaN/Infinity');
    return String(value);
  }
  if (typeof value === 'string') return JSON.stringify(value);
  if (Array.isArray(value)) return '[' + value.map(canonical).join(',') + ']';
  if (typeof value === 'object') {
    const keys = Object.keys(value).sort();
    return '{' + keys.map(k => JSON.stringify(k) + ':' + canonical(value[k])).join(',') + '}';
  }
  throw new Error('not a JSON value: ' + typeof value);
}

const args = process.argv.slice(2);
const asHash = args.includes('--hash');
const asCanonical = args.includes('--canonical');
let raw = args.find(a => !a.startsWith('--'));
if (raw !== undefined && fs.existsSync(raw)) raw = fs.readFileSync(raw, 'utf8');
if (raw === undefined) raw = fs.readFileSync(0, 'utf8');
const value = JSON.parse(raw);
const out = canonical(value);
if (asCanonical) console.log(out);
else if (asHash) console.log(crypto.createHash('sha256').update(out, 'utf8').digest('hex'));
else { console.log(out); console.log(crypto.createHash('sha256').update(out, 'utf8').digest('hex')); }
