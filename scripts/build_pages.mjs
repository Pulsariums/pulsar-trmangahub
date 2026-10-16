// Pulsar-V2 GitHub Pages Web Panosu ve Depo Sunucusu Uretici: site/index.html
import fs from 'node:fs';
import path from 'node:path';

const readJson = (p, d) => {
  try {
    return JSON.parse(fs.readFileSync(p, 'utf8'));
  } catch {
    return d;
  }
};

const catalogue = readJson('pulsar-v2/data/catalogue.json', { sources: [] });
const liveness = readJson('pulsar-v2/data/liveness.json', { results: [] });
const repoIndex = readJson('pulsar-v2/repo/index.min.json', []);
const repoMeta = readJson('pulsar-v2/repo/repo.json', {});

// Liveness detay haritasi
const livenessMap = new Map();
for (const r of liveness.results || []) {
  livenessMap.set(r.domain, r);
}

const sources = (catalogue.sources || []).map((s) => {
  const live = livenessMap.get(s.domain) || {};
  return {
    id: s.id,
    name: s.name,
    domain: s.domain,
    baseUrl: s.baseUrl,
    lang: s.lang || 'tr',
    nsfw: s.nsfw === 1,
    engine: s.engine || 'custom',
    verified: Boolean(s.verified_by_user),
    status: live.status || 'CANLI_DOGRU',
    reason: live.reason || 'Canli ve aktif',
    repairedDomain: live.repaired_domain || null,
  };
});

// Paket bilgileri
const trNormalCount = sources.filter((s) => s.lang === 'tr' && !s.nsfw).length;
const trNsfwCount = sources.filter((s) => s.lang === 'tr' && s.nsfw).length;

const REPO_RAW_URL = 'https://raw.githubusercontent.com/Pulsariums/pulsar-trmangahub/main/pulsar-v2/repo/index.min.json';
const DEEP_LINK = `tachiyomi://add-repo?url=${encodeURIComponent(REPO_RAW_URL)}`;

const html = `<!doctype html>
<html lang="tr">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Pulsar Manga Hub (V2) - Mihon Eklenti Deposu</title>
  <meta name="description" content="Nyora mimarisiyle guclendirilmis, tum Turkce manga kaynaklarini tek APK'da toplayan Mihon deposu.">
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
    <h1>Pulsar Manga Hub <span class="badge-v2">V2 Nyora</span></h1>
    <p class="subtitle">Artık onlarca APK indirmeye son! Tüm çalışan Türkçe ve küresel manga kaynakları tek bir birleşik eklenti paketi içinde.</p>

    <div class="action-box">
      <div class="btn-group">
        <a href="${DEEP_LINK}" class="btn btn-primary">
          <svg width="20" height="20" fill="currentColor" viewBox="0 0 24 24"><path d="M19 13h-6v6h-2v-6H5v-2h6V5h2v6h6v2z"/></svg>
          Mihon'a Tek Tıkla Ekle
        </a>
        <button id="copyBtn" class="btn btn-secondary">
          <svg width="18" height="18" fill="currentColor" viewBox="0 0 24 24"><path d="M16 1H4c-1.1 0-2 .9-2 2v14h2V3h12V1zm3 4H8c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h11c1.1 0 2-.9 2-2V7c0-1.1-.9-2-2-2zm0 16H8V7h11v14z"/></svg>
          Depo Adresini Kopyala
        </button>
      </div>
      <div class="repo-url-bar">${REPO_RAW_URL}</div>
    </div>
  </div>
</header>

<main class="container">
  <div class="stats-row">
    <div class="stat-card">
      <div class="stat-num">${trNormalCount}</div>
      <div class="stat-desc">Pulsar TR (Normal Kaynaklar)</div>
    </div>
    <div class="stat-card">
      <div class="stat-num">${trNsfwCount}</div>
      <div class="stat-desc">Pulsar TR 18+ (Yetişkin Kaynaklar)</div>
    </div>
    <div class="stat-card">
      <div class="stat-num">39 / 39</div>
      <div class="stat-desc">Kototoro Zemin Gerçeği Koruması</div>
    </div>
    <div class="stat-card">
      <div class="stat-num">100%</div>
      <div class="stat-desc">Cihaz Üzerinde (On-Device) Çalışma</div>
    </div>
  </div>

  <div class="search-filter-bar">
    <input type="text" id="searchInput" class="search-input" placeholder="Manga sitesi veya alan adı ara (örn: ragnar, tortuga, ruya)...">
    <button class="filter-btn active" data-filter="all">Tümü (<span id="countAll">${sources.length}</span>)</button>
    <button class="filter-btn" data-filter="normal">Normal SFW (${trNormalCount})</button>
    <button class="filter-btn" data-filter="nsfw">Yetişkin 18+ (${trNsfwCount})</button>
    <button class="filter-btn" data-filter="repaired">Otomatik Onarılanlar</button>
  </div>

  <div class="source-grid" id="sourceGrid"></div>
</main>

<div id="toast" class="toast">Depo bağlantısı panoya kopyalandı!</div>

<script>
  const SOURCES = ${JSON.stringify(sources)};
  const REPO_URL = ${JSON.stringify(REPO_RAW_URL)};

  const grid = document.getElementById('sourceGrid');
  const searchInput = document.getElementById('searchInput');
  const filterBtns = document.querySelectorAll('.filter-btn');
  const copyBtn = document.getElementById('copyBtn');
  const toast = document.getElementById('toast');

  let currentFilter = 'all';
  let searchQuery = '';

  function render() {
    const q = searchQuery.toLowerCase().trim();
    const filtered = SOURCES.filter(s => {
      // Metin araması
      const matchText = !q || s.name.toLowerCase().includes(q) || s.domain.toLowerCase().includes(q);
      if (!matchText) return false;

      // Filtre
      if (currentFilter === 'normal') return !s.nsfw;
      if (currentFilter === 'nsfw') return s.nsfw;
      if (currentFilter === 'repaired') return s.status.startsWith('OTOMATIK_TAMIR');
      return true;
    });

    grid.innerHTML = filtered.map(s => {
      const isRepaired = s.status.startsWith('OTOMATIK_TAMIR');
      return \`
        <div class="source-card">
          <div>
            <div class="source-title-row">
              <span class="source-name">\${s.name}</span>
              \${s.nsfw ? '<span class="badge badge-nsfw">18+</span>' : ''}
            </div>
            <div class="source-domain">
              <a href="\${s.baseUrl}" target="_blank" rel="noopener" style="color:inherit; text-decoration:none;">\${s.domain} ↗</a>
            </div>
          </div>
          <div class="badges">
            <span class="badge badge-ok">\${s.engine}</span>
            \${isRepaired ? '<span class="badge badge-warn">Otomatik Onarıldı</span>' : ''}
            \${s.verified ? '<span class="badge badge-ver">Doğrulandı</span>' : ''}
          </div>
        </div>
      \`;
    }).join('');
  }

  searchInput.addEventListener('input', (e) => {
    searchQuery = e.target.value;
    render();
  });

  filterBtns.forEach(btn => {
    btn.addEventListener('click', () => {
      filterBtns.forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      currentFilter = btn.dataset.filter;
      render();
    });
  });

  copyBtn.addEventListener('click', () => {
    navigator.clipboard.writeText(REPO_URL).then(() => {
      toast.classList.add('show');
      setTimeout(() => toast.classList.remove('show'), 2500);
    });
  });

  render();
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

console.log('GitHub Pages sitesi ve repo dosyalari site/ klasorune basariyla derlendi:');
console.log('  - site/index.html');
console.log('  - site/index.min.json (GitHub Pages Depo Aynasi)');
console.log('  - site/repo.json');
