// GitHub Pages icin mobil test sayfasi uretir: site/index.html
// Kaynaklar: sources/tr/sources.json + data/live/history.json + data/live/device.json
import fs from 'node:fs';

const read = (p, d) => { try { return JSON.parse(fs.readFileSync(p, 'utf8')); } catch { return d; } };
const raw = read('sources/tr/sources.json', []);
const entries = Array.isArray(raw) ? raw : raw.sources;
const hist = read('data/live/history.json', {});
const dev = read('data/live/device.json', { sources: [] });
const devBy = Object.fromEntries((dev.sources || []).map((s) => [s.name, s.status]));

const rows = entries.map((e) => {
  const parser = e.formats?.jar?.parser || null;
  const h = parser ? hist[parser] : null;
  let ci = 'yok';
  if (h) ci = h.ok_streak > 0 ? 'ok' : (h.error_class || 'fail');
  return {
    id: e.id, name: e.name || e.domain, domain: e.domain, url: e.baseUrl || `https://${e.domain}`,
    status: e.status, nsfw: !!e.nsfw, parser, jar: !!e.formats?.jar, mihon: !!e.formats?.mihon,
    ci, device: parser ? (devBy[parser] || 'yok') : 'yok',
    up: (e.upstreams || []).join(','),
  };
}).sort((a, b) => a.name.localeCompare(b.name, 'tr'));

const html = `<!doctype html><html lang="tr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Kaynak testi</title>
<style>
:root{color-scheme:light dark;--bg:#fff;--fg:#1a1a1a;--card:#f2f3f5;--mut:#667;--ok:#1a7f37;--bad:#cf222e;--warn:#9a6700;--line:#d0d7de}
@media(prefers-color-scheme:dark){:root{--bg:#0d1117;--fg:#e6edf3;--card:#161b22;--mut:#8b949e;--ok:#3fb950;--bad:#f85149;--warn:#d29922;--line:#30363d}}
body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.4 system-ui,sans-serif}
header{position:sticky;top:0;background:var(--bg);border-bottom:1px solid var(--line);padding:10px 16px;z-index:2}
h1{font-size:17px;margin:0 0 6px}
.bar{display:flex;gap:6px;flex-wrap:wrap}
input,select,button{font:inherit;padding:7px 10px;border-radius:8px;border:1px solid var(--line);background:var(--card);color:var(--fg)}
input{flex:1;min-width:140px}
main{padding:8px 16px 80px}
.row{background:var(--card);border-radius:12px;padding:10px 12px;margin:8px 0}
.top{display:flex;justify-content:space-between;gap:8px;align-items:baseline}
.name{font-weight:600}
.meta{color:var(--mut);font-size:12.5px;margin:2px 0 8px;word-break:break-all}
.tag{display:inline-block;padding:1px 7px;border-radius:99px;font-size:11.5px;border:1px solid var(--line);margin-right:4px}
.ok{color:var(--ok)}.bad{color:var(--bad)}.warn{color:var(--warn)}
.act{display:flex;gap:6px}
.act a,.act button{flex:1;text-align:center;text-decoration:none;color:var(--fg)}
.sel{outline:2px solid currentColor}
#out{position:fixed;bottom:0;left:0;right:0;padding:10px 16px;background:var(--bg);border-top:1px solid var(--line);display:flex;gap:8px;align-items:center}
</style></head><body>
<header><h1>Türkçe kaynak testi (<span id="cnt"></span>)</h1>
<div class="bar"><input id="q" placeholder="Ara: ad veya alan adı">
<select id="f"><option value="">Hepsi</option><option value="todo">Test etmediklerim</option><option value="up">Bizde çalışan</option><option value="down">Çalışmayan</option><option value="jar">JAR var</option><option value="mihon">Mihon var</option></select></div>
<div class="bar" style="margin-top:6px"><button id="auto" style="flex:1;font-weight:700">▶ Oto test (JAR'lar)</button><button id="tok">Anahtar</button></div>
<div id="st" class="meta" style="margin:6px 0 0"></div></header>
<main id="list"></main>
<div id="out"><span id="sum" style="flex:1"></span><button id="copy">Listeyi kopyala</button></div>
<script>
const ROWS=${JSON.stringify(rows)};
const KEY='kaynak-test-v1';
let saved={};try{saved=JSON.parse(localStorage.getItem(KEY)||'{}')}catch{}
const save=()=>{try{localStorage.setItem(KEY,JSON.stringify(saved))}catch{}};
const cls=(s)=>s==='ok'||s==='pass'?'ok':(s==='yok'?'warn':'bad');
function render(){
  const q=document.getElementById('q').value.toLowerCase(),f=document.getElementById('f').value;
  const list=ROWS.filter(r=>{
    if(q&&!(r.name+r.domain).toLowerCase().includes(q))return false;
    if(f==='todo')return !saved[r.id];
    if(f==='up')return r.status==='published'||r.status==='cf_protected_published';
    if(f==='down')return r.status==='quarantined';
    if(f==='jar')return r.jar; if(f==='mihon')return r.mihon; return true;});
  document.getElementById('cnt').textContent=list.length+'/'+ROWS.length;
  document.getElementById('list').innerHTML=list.map(r=>\`<div class="row">
  <div class="top"><span class="name">\${r.name}</span><span>\${r.nsfw?'<span class="tag">+18</span>':''}<span class="tag">\${r.status}</span></span></div>
  <div class="meta">\${r.domain} · CI: <b class="\${cls(r.ci)}">\${r.ci}</b> · cihaz: <b class="\${cls(r.device)}">\${r.device}</b>\${r.jar?' · JAR':''}\${r.mihon?' · Mihon':''}</div>
  <div class="act">\${r.parser?'<button data-t="'+r.parser+'">▶ JAR testi</button>':'<span class="meta">JAR yok</span>'}
  <button data-id="\${r.id}" data-v="ok" class="ok \${saved[r.id]==='ok'?'sel':''}">✔ Çalışıyor</button>
  <button data-id="\${r.id}" data-v="bad" class="bad \${saved[r.id]==='bad'?'sel':''}">✖ Çalışmıyor</button></div></div>\`).join('');
  const n=Object.values(saved);document.getElementById('sum').textContent='Çalışıyor '+n.filter(x=>x==='ok').length+' · Çalışmıyor '+n.filter(x=>x==='bad').length;
}
document.getElementById('list').addEventListener('click',e=>{const b=e.target.closest('button[data-id]');if(!b)return;
  const id=b.dataset.id;saved[id]=saved[id]===b.dataset.v?undefined:b.dataset.v;if(!saved[id])delete saved[id];save();render();});
document.getElementById('q').oninput=render;document.getElementById('f').onchange=render;
document.getElementById('copy').onclick=async()=>{
  const out=ROWS.filter(r=>saved[r.id]).map(r=>({id:r.id,name:r.name,domain:r.domain,parser:r.parser,sonuc:saved[r.id]==='ok'?'calisiyor':'calismiyor'}));
  const t=JSON.stringify(out,null,1);try{await navigator.clipboard.writeText(t);alert(out.length+' kayıt kopyalandı')}catch{prompt('Kopyala:',t)}};
const REPO='Pulsariums/pulsar-trmangahub',API='https://api.github.com/repos/'+REPO;
const st=(t)=>document.getElementById('st').textContent=t;
const tk=()=>{try{return localStorage.getItem('gh-tok')||''}catch{return ''}};
document.getElementById('tok').onclick=()=>{const v=prompt('GitHub anahtarı (fine-grained, bu repo, Actions: Read and write). Bir kez girilir, telefonda saklanır:',tk());if(v!==null){try{localStorage.setItem('gh-tok',v.trim())}catch{}st(v.trim()?'Anahtar kaydedildi':'Anahtar silindi')}};
const gh=(p,o={})=>fetch(API+p,{...o,headers:{Authorization:'Bearer '+tk(),Accept:'application/vnd.github+json','Content-Type':'application/json'}});
async function refresh(){try{const r=await fetch('https://raw.githubusercontent.com/'+REPO+'/main/data/live/history.json?'+Date.now());const h=await r.json();
  ROWS.forEach(x=>{const e=x.parser&&h[x.parser];if(e)x.ci=e.ok_streak>0?'ok':(e.error_class||'fail')});render()}catch(e){st('Sonuç okunamadı: '+e)}}
async function run(inputs,label){
  if(!tk()){st('Önce "Anahtar" ile GitHub anahtarını gir');return}
  const t0=new Date(Date.now()-5000).toISOString();
  const r=await gh('/actions/workflows/live-check.yml/dispatches',{method:'POST',body:JSON.stringify({ref:'main',inputs})});
  if(r.status!==204){st('Başlatılamadı ('+r.status+'): anahtarı/izni kontrol et');return}
  st(label+' başlatıldı, sonuç bekleniyor…');let id=null;
  for(let i=0;i<120;i++){await new Promise(z=>setTimeout(z,10000));
    const l=await(await gh('/actions/workflows/live-check.yml/runs?event=workflow_dispatch&per_page=5')).json();
    const w=(l.workflow_runs||[]).find(x=>x.created_at>=t0);if(!w)continue;id=w.id;
    st(label+': '+w.status+' ('+(i*10)+' sn)');
    if(w.status==='completed'){await refresh();const ok=ROWS.filter(x=>x.ci==='ok').length;st(label+' bitti ('+w.conclusion+'). JAR testinden geçen: '+ok+'/'+ROWS.filter(x=>x.jar).length);return}}
  st('Zaman aşımı; Actions sayfasından bak')}
document.getElementById('auto').onclick=()=>run({bolum:'tr'},'Oto test (tr)');
document.getElementById('list').addEventListener('click',e=>{const b=e.target.closest('button[data-t]');if(b)run({bolum:'tr',only:b.dataset.t},b.dataset.t)});
render();refresh();
</script></body></html>`;
fs.mkdirSync('site', { recursive: true });
fs.writeFileSync('site/index.html', html);
console.log('satir:', rows.length);
