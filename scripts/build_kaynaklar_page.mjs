// GH Pages: site/kaynaklar.html (+ site/kaynaklar.json) - depo tablosu, repo kokeni ve evre
import fs from 'node:fs';

const src = 'pulsar-v2/depo/kaynaklar.json';
fs.mkdirSync('site', { recursive: true });
if (!fs.existsSync(src)) { console.log('kaynaklar.json yok, sayfa atlandi'); process.exit(0); }
fs.copyFileSync(src, 'site/kaynaklar.json');

const html = `<!doctype html>
<html lang="tr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Pulsar Manga Hub - Kaynaklar</title>
<style>
  :root { --bg:#f6f7f9; --card:#ffffff; --line:#d9dde3; --fg:#1d2330; --mut:#5d6677; --pri:#2f6fed; }
  * { box-sizing:border-box; margin:0; padding:0; }
  body { background:var(--bg); color:var(--fg); font-family:"Nunito","Segoe UI",Roboto,sans-serif; line-height:1.45; padding:20px 14px 60px; }
  .w { max-width:1200px; margin:0 auto; }
  h1 { font-size:1.5rem; margin-bottom:4px; }
  .alt { color:var(--mut); margin-bottom:16px; }
  .bar { display:flex; flex-wrap:wrap; gap:8px; margin-bottom:12px; }
  input,select { border:1px solid var(--line); border-radius:12px; padding:9px 12px; font:inherit; background:var(--card); color:var(--fg); }
  input { flex:1 1 220px; }
  .sayac { color:var(--mut); margin:6px 0 10px; }
  table { width:100%; border-collapse:separate; border-spacing:0; background:var(--card); border:1px solid var(--line); border-radius:14px; overflow:hidden; }
  th,td { text-align:left; padding:9px 12px; border-bottom:1px solid var(--line); vertical-align:top; font-size:.92rem; }
  th { background:#eef0f4; font-weight:700; }
  tr:last-child td { border-bottom:none; }
  .e { display:inline-block; padding:2px 10px; border-radius:99px; font-size:.8rem; font-weight:700; border:1px solid var(--line); background:#eef0f4; }
  .e.gecti { background:#dff3e4; border-color:#9ad3a8; }
  .e.imkansiz { background:#f6dcdc; border-color:#e0a1a1; }
  .e.tamir-edilebilir,.e.yeniden-test,.e.cloudflare,.e.alan-adi-aranacak { background:#fbeccc; border-color:#e6c377; }
  .m { color:var(--mut); font-size:.85rem; }
  .tabwrap { overflow-x:auto; }
</style>
</head>
<body>
<div class="w">
  <h1>Kaynaklar</h1>
  <p class="alt">Her kaynağın geldiği repolar, bizdeki evresi, yayın grubu ve tamir durumu. <a href="index.html">Kurulum sayfası</a></p>
  <div class="bar">
    <input id="q" placeholder="Ad veya alan adı ara">
    <select id="fe"><option value="">Evre: hepsi</option></select>
    <select id="fg"><option value="">Grup: hepsi</option></select>
    <select id="fl"><option value="">Etiket: hepsi</option></select>
    <select id="fr"><option value="">Repo: hepsi</option></select>
    <select id="ft"><option value="">Tamir: hepsi</option><option value="1">Tamir edildi</option><option value="0">Tamir edilmedi</option></select>
  </div>
  <div class="sayac" id="s"></div>
  <div class="tabwrap"><table>
    <thead><tr><th>Kaynak</th><th>Geldiği repolar</th><th>Yayında</th><th>Evre</th><th>Grup</th><th>Etiket</th><th>Tamir</th><th>Son hata</th></tr></thead>
    <tbody id="t"></tbody>
  </table></div>
</div>
<script>
const $ = (i) => document.getElementById(i);
const esc = (v) => String(v == null ? '' : v).replace(/[&<>"]/g, (c) => ({ '&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;' }[c]));
let K = [];
function doldur(sel, vals) { [...new Set(vals)].filter(Boolean).sort().forEach((v) => { const o = document.createElement('option'); o.value = v; o.textContent = v; sel.appendChild(o); }); }
function ciz() {
  const q = $('q').value.toLowerCase(), fe = $('fe').value, fg = $('fg').value, fl = $('fl').value, fr = $('fr').value, ft = $('ft').value;
  const r = K.filter((k) => (!q || (k.ad + ' ' + k.alan_adi).toLowerCase().includes(q)) && (!fe || k.evre === fe) && (!fg || k.grup === fg) && (!fl || k.etiket === fl) && (!fr || k.repolar.includes(fr) || k.kokenler.includes(fr)) && (!ft || (ft === '1') === !!k.tamir_edildi));
  $('s').textContent = r.length + ' / ' + K.length + ' kaynak';
  $('t').innerHTML = r.slice(0, 1500).map((k) => '<tr><td><b>' + esc(k.ad) + '</b><div class="m">' + esc(k.alan_adi) + ' · ' + esc(k.dil) + (k.nsfw ? ' · 18+' : '') + '</div></td>'
    + '<td>' + esc((k.repolar.length ? k.repolar : k.kokenler).join(', ') || '-') + '</td>'
    + '<td>' + (k.yayinda ? 'evet' : 'hayır') + '</td>'
    + '<td>' + esc(k.evre) + '</td><td>' + esc(k.grup) + '</td>'
    + '<td><span class="e ' + esc(k.etiket) + '">' + esc(k.etiket) + '</span></td>'
    + '<td>' + (k.tamir_edildi ? 'edildi' : '-') + (k.tamir_kayitlari.length ? '<div class="m">' + esc(k.tamir_kayitlari.join(', ')) + '</div>' : '') + '</td>'
    + '<td class="m">' + esc(k.hata_adimi ? k.hata_adimi + ': ' : '') + esc((k.hata_mesaji || '').slice(0, 120)) + '</td></tr>').join('');
}
fetch('kaynaklar.json').then((r) => r.json()).then((d) => {
  K = d.kayitlar;
  doldur($('fe'), K.map((k) => k.evre)); doldur($('fg'), K.map((k) => k.grup)); doldur($('fl'), K.map((k) => k.etiket));
  doldur($('fr'), K.flatMap((k) => k.repolar.concat(k.kokenler)));
  ['q', 'fe', 'fg', 'fl', 'fr', 'ft'].forEach((i) => $(i).addEventListener('input', ciz));
  ciz();
});
</script>
</body>
</html>
`;
fs.writeFileSync('site/kaynaklar.html', html);
console.log('site/kaynaklar.html yazildi');
