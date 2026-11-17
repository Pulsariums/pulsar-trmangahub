// Pulsar-V2 GitHub Pages Durum Panosu ve Kurulum Sayfasi Uretici: site/index.html
import fs from 'node:fs';

const readJson = (p, d) => {
  try {
    return JSON.parse(fs.readFileSync(p, 'utf8'));
  } catch {
    return d;
  }
};

const repoIndex = readJson('pulsar-v2/repo/index.min.json', []);
const repoMeta = readJson('pulsar-v2/repo/repo.json', {});

// index.min.json: paket kayitlari dizisi
const packages = Array.isArray(repoIndex) ? repoIndex : (repoIndex.packages || []);

const sourceCountOf = (p) => (Array.isArray(p && p.sources) ? p.sources.length : 0);

// Sayi kartlari - hepsi index.min.json'dan okunur
const totalSources = packages.reduce((sum, p) => sum + sourceCountOf(p), 0);
const packageCount = Array.isArray(repoMeta.packages) ? repoMeta.packages.length : packages.length;
const widest = packages.reduce((best, p) => (sourceCountOf(p) > sourceCountOf(best) ? p : best), null);
const widestName = widest && widest.name ? widest.name : 'BULUNAMADI';
const nsfwPackages = packages.filter((p) => Number(p.nsfw || 0) !== 0).length;
const versionLabel = packages[0] && packages[0].version ? String(packages[0].version) : 'BULUNAMADI';

// Depo adresi: GITHUB_REPOSITORY > repo.json meta.website > sabit
const repoSlug = (() => {
  if (process.env.GITHUB_REPOSITORY) return process.env.GITHUB_REPOSITORY;
  const website = (repoMeta.meta && repoMeta.meta.website) || '';
  const match = website.match(/github\.com\/([^/]+)\/([^/?#]+)/i);
  if (match) return `${match[1]}/${match[2]}`;
  return 'pulsariums/pulsar-trmangahub';
})();
const REPO_RAW_URL = `https://raw.githubusercontent.com/${repoSlug}/main/pulsar-v2/repo/index.min.json`;

// Kaynaklar sayfasi baglantisi: sayi kaynaklar.json'daki toplam alanindan okunur
const kaynaklarMeta = readJson('pulsar-v2/depo/kaynaklar.json', {});
const kaynaklarTotal = Number(kaynaklarMeta && kaynaklarMeta.toplam);
const kaynaklarLabel = kaynaklarTotal > 0
  ? `Tüm kaynaklar ve durum (${kaynaklarTotal})`
  : 'Tüm kaynaklar ve durum';

const esc = (v) => String(v == null ? '' : v).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

const packageCards = packages.map((p) => {
  const nsfw = Number(p.nsfw || 0) !== 0;
  const apk = p.apk ? String(p.apk) : '';
  const badges = [
    `<span class="badge">${sourceCountOf(p)} kaynak</span>`,
    p.lang ? `<span class="badge">${esc(String(p.lang).toUpperCase())}</span>` : '',
    nsfw ? '<span class="badge badge-nsfw">18+</span>' : '',
  ].filter(Boolean).join('\n            ');

  return `
        <div class="source-card">
          <div class="source-title-row">
            <span class="source-name">${esc(p.name || 'BULUNAMADI')}</span>
          </div>
          <div class="source-domain">${esc(apk || p.version || 'BULUNAMADI')}</div>
          <div class="badges">
            ${badges}
          </div>
          ${apk ? `<a href="apk/${esc(apk)}" class="btn btn-primary" style="margin-top:10px">APK indir</a>` : ''}
        </div>`;
}).join('');

const html = `<!doctype html>
<html lang="tr">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Pulsar Manga Hub - Mihon / Kototoro Eklenti Deposu</title>
  <meta name="description" content="Mihon ve Kototoro icin cok kaynakli Turkce manga eklentisi. Depo adresi, paket listesi ve APK indirme baglantilari.">
  <style>
    :root {
      --bg: #0d1117;
      --card: #161b22;
      --card-border: #30363d;
      --fg: #e6edf3;
      --mut: #8b949e;
      --pri: #2f81f7;
      --pri-hover: #388bfd;
      --ok: #3fb950;
      --warn: #d29922;
      --nsfw: #f85149;
      --tag-bg: #21262d;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      background: var(--bg);
      color: var(--fg);
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
      line-height: 1.5;
      padding-bottom: 60px;
    }
    .container { max-width: 1100px; margin: 0 auto; padding: 0 16px; }
    header {
      background: linear-gradient(180deg, #161b22 0%, #0d1117 100%);
      border-bottom: 1px solid var(--card-border);
      padding: 40px 0 32px;
      text-align: center;
    }
    h1 { font-size: 2.2rem; font-weight: 800; margin-bottom: 10px; letter-spacing: -0.5px; }
    .badge-v2 {
      background: #388bfd26;
      color: var(--pri);
      padding: 4px 10px;
      border-radius: 99px;
      font-size: 0.85rem;
      font-weight: 600;
      vertical-align: middle;
      border: 1px solid #388bfd4d;
    }
    p.subtitle { color: var(--mut); font-size: 1.1rem; max-width: 680px; margin: 0 auto 24px; }
    .action-box {
      background: var(--card);
      border: 1px solid var(--card-border);
      border-radius: 12px;
      padding: 20px;
      max-width: 720px;
      margin: 0 auto 30px;
      box-shadow: 0 8px 24px rgba(0,0,0,0.4);
    }
    .btn-group { display: flex; gap: 12px; justify-content: center; flex-wrap: wrap; margin-bottom: 16px; }
    .btn {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      padding: 12px 24px;
      border-radius: 8px;
      font-size: 1rem;
      font-weight: 600;
      text-decoration: none;
      cursor: pointer;
      transition: all 0.15s ease;
      border: none;
    }
    .btn-primary { background: var(--pri); color: #fff; }
    .btn-primary:hover { background: var(--pri-hover); transform: translateY(-1px); }
    .btn-secondary { background: var(--tag-bg); color: var(--fg); border: 1px solid var(--card-border); }
    .btn-secondary:hover { background: #30363d; }
    .repo-url-bar {
      display: flex;
      background: #090d13;
      border: 1px solid var(--card-border);
      border-radius: 6px;
      padding: 8px 12px;
      align-items: center;
      font-family: monospace;
      font-size: 0.9rem;
      color: #7ee787;
      word-break: break-all;
    }
    .stats-row {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 16px;
      margin: 32px 0;
    }
    .stat-card {
      background: var(--card);
      border: 1px solid var(--card-border);
      border-radius: 10px;
      padding: 16px;
      text-align: center;
    }
    .stat-num { font-size: 1.8rem; font-weight: 800; color: var(--fg); }
    .stat-desc { color: var(--mut); font-size: 0.9rem; margin-top: 4px; }
    .search-filter-bar {
      display: flex;
      gap: 12px;
      margin: 24px 0 16px;
      flex-wrap: wrap;
    }
    .search-input {
      flex: 1;
      min-width: 250px;
      padding: 10px 16px;
      background: var(--card);
      border: 1px solid var(--card-border);
      border-radius: 8px;
      color: var(--fg);
      font-size: 0.95rem;
    }
    .filter-btn {
      padding: 8px 14px;
      background: var(--card);
      border: 1px solid var(--card-border);
      border-radius: 8px;
      color: var(--mut);
      cursor: pointer;
      font-size: 0.9rem;
    }
    .filter-btn.active {
      background: var(--pri);
      color: #fff;
      border-color: var(--pri);
    }
    .source-grid {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
      gap: 12px;
    }
    .source-card {
      background: var(--card);
      border: 1px solid var(--card-border);
      border-radius: 8px;
      padding: 14px;
      display: flex;
      flex-direction: column;
      justify-content: space-between;
      transition: border-color 0.15s;
    }
    .source-card:hover { border-color: var(--pri); }
    .source-title-row { display: flex; justify-content: space-between; align-items: flex-start; gap: 8px; margin-bottom: 6px; }
    .source-name { font-weight: 600; font-size: 1.05rem; }
    .source-domain { color: var(--mut); font-size: 0.85rem; font-family: monospace; word-break: break-all; margin-bottom: 10px; }
    .badges { display: flex; gap: 6px; flex-wrap: wrap; margin-top: auto; }
    .badge {
      font-size: 0.75rem;
      padding: 2px 8px;
      border-radius: 99px;
      background: var(--tag-bg);
      border: 1px solid var(--card-border);
      font-weight: 500;
    }
    .badge-ok { color: var(--ok); border-color: #3fb9504d; background: #3fb9501a; }
    .badge-warn { color: var(--warn); border-color: #d299224d; background: #d299221a; }
    .badge-nsfw { color: var(--nsfw); border-color: #f851494d; background: #f851491a; }
    .badge-ver { color: #a371f7; border-color: #a371f74d; background: #a371f71a; }
    .toast {
      position: fixed;
      bottom: 24px;
      left: 50%;
      transform: translateX(-50%);
      background: var(--ok);
      color: #000;
      padding: 10px 20px;
      border-radius: 8px;
      font-weight: 600;
      opacity: 0;
      pointer-events: none;
      transition: opacity 0.2s;
    }
    .toast.show { opacity: 1; }
  </style>
</head>
<body>

<header>
  <div class="container">
    <h1>Pulsar Manga Hub</h1>
    <p><span class="badge-v2">${esc(versionLabel)}</span></p>
    <p>Mihon / Kototoro için çok kaynaklı Türkçe manga eklentisi.</p>
  </div>
</header>

<main class="container">
  <div class="stats-row">
    <div class="stat-card">
      <div class="stat-num">${totalSources}</div>
      <div class="stat-desc">yayındaki kaynak</div>
    </div>
    <div class="stat-card">
      <div class="stat-num">${packageCount}</div>
      <div class="stat-desc">paket</div>
    </div>
    <div class="stat-card">
      <div class="stat-num">${esc(widestName)}</div>
      <div class="stat-desc">en geniş paket</div>
    </div>
    <div class="stat-card">
      <div class="stat-num">${nsfwPackages}</div>
      <div class="stat-desc">18+ paket</div>
    </div>
  </div>

  <h2>Kurulum</h2>
  <div class="action-box">
    <p>1. Mihon veya Kototoro'yu aç → Ayarlar → Eklentiler → Depolar.</p>
    <p>2. Depo ekle → aşağıdaki adresi yapıştır.</p>
    <p>3. Listeden paketini seç ve kur. Güncellemeler otomatik gelir.</p>
    <div class="repo-url-bar">${esc(REPO_RAW_URL)}</div>
    <button id="copyBtn" class="btn btn-secondary" style="margin-top:12px">
      <svg width="18" height="18" fill="currentColor" viewBox="0 0 24 24"><path d="M16 1H4c-1.1 0-2 .9-2 2v14h2V3h12V1zm3 4H8c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h11c1.1 0 2-.9 2-2V7c0-1.1-.9-2-2-2zm0 16H8V7h11v14z"/></svg>
      Depo Adresini Kopyala
    </button>
    <a class="btn btn-secondary" href="kaynaklar.html" style="margin-top:12px">${esc(kaynaklarLabel)}</a>
  </div>

  <h2>Paketler</h2>
  <div class="source-grid">${packageCards}
  </div>

  <p class="source-domain">Kaynaklar üçüncü taraf sitelerden okur; içerik Pulsar'a ait değildir.</p>
</main>

<div id="toast" class="toast">Depo bağlantısı panoya kopyalandı!</div>

<script>
  const REPO_URL = ${JSON.stringify(REPO_RAW_URL)};

  const copyBtn = document.getElementById('copyBtn');
  const toast = document.getElementById('toast');

  copyBtn.addEventListener('click', () => {
    navigator.clipboard.writeText(REPO_URL).then(() => {
      toast.classList.add('show');
      setTimeout(() => toast.classList.remove('show'), 2500);
    });
  });
</script>

</body>
</html>
`;

// 1. site/ klasorunu olustur ve dosyaları kopyala
fs.mkdirSync('site', { recursive: true });
fs.writeFileSync('site/index.html', html, 'utf8');

// 2. Mihon repo dosyalarini da site/ altina kopyala (GitHub Pages aynasi icin)
if (fs.existsSync('pulsar-v2/repo/index.min.json')) {
  fs.copyFileSync('pulsar-v2/repo/index.min.json', 'site/index.min.json');
}
if (fs.existsSync('pulsar-v2/repo/repo.json')) {
  fs.copyFileSync('pulsar-v2/repo/repo.json', 'site/repo.json');
}

console.log('GitHub Pages durum panosu site/ klasorune derlendi:');
console.log('  - site/index.html');
console.log('  - site/index.min.json (GitHub Pages Depo Aynasi)');
console.log('  - site/repo.json');
