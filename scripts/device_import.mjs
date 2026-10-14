// Kototoro "Tumunu test et" ciktisini data/live/device.json icine birlestirir.
// Kullanim: DEVICE_JSON='<json>' node scripts/device_import.mjs
import fs from 'node:fs';
const p = 'data/live/device.json';
let inc;
try { inc = JSON.parse(process.env.DEVICE_JSON || ''); } catch (e) { console.error('JSON okunamadi:', e.message); process.exit(1); }
const list = Array.isArray(inc) ? inc : (inc.sources || inc.results || []);
const norm = (x) => {
  const name = x.name || x.source || x.parser; if (!name) return null;
  const steps = x.steps || undefined;
  let status = x.status || x.result;
  if (!status && steps) status = Object.values(steps).every((v) => v === 'pass') ? 'pass' : 'fail';
  if (!status) return null;
  status = /^(pass|ok|success|true)$/i.test(String(status)) ? 'pass' : 'fail';
  return steps ? { name, status, steps } : { name, status };
};
const fresh = list.map(norm).filter(Boolean);
if (!fresh.length) { console.error('gecerli kayit yok'); process.exit(1); }
let cur = { sources: [] };
try { cur = JSON.parse(fs.readFileSync(p, 'utf8')); } catch {}
const by = new Map((cur.sources || []).map((s) => [s.name, s]));
for (const s of fresh) by.set(s.name, s);
cur.sources = [...by.values()];
cur.generated = new Date().toISOString();
fs.mkdirSync('data/live', { recursive: true });
fs.writeFileSync(p, JSON.stringify(cur, null, 2));
console.log('birlestirilen:', fresh.length, 'toplam:', cur.sources.length, 'gecen:', fresh.filter((s) => s.status === 'pass').length);
