// SPA/JS siteleri icin ag kesfi: gercek tarayici ile sayfalari gezer, JSON/API isteklerini ve
// gorsel adreslerini kaydeder. Kullanim: node scripts/recon.mjs https://site/ [...]
// Cikti: stdout'a "RECON {json}" satirlari (site basina bir tane) ve recon-out/<host>.json.
import { chromium } from 'playwright';
import fs from 'node:fs';

const UA = 'Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 Chrome/124.0 Mobile Safari/537.36';
const sites = process.argv.slice(2);
fs.mkdirSync('recon-out', { recursive: true });

function pickLinks(links, origin) {
  const same = [...new Set(links.filter((h) => h.startsWith(origin)).map((h) => h.split('#')[0].split('?')[0]))];
  const groups = {};
  for (const h of same) {
    const segs = new URL(h).pathname.split('/').filter(Boolean);
    if (segs.length >= 2) (groups[segs[0]] ||= []).push(h);
  }
  const best = Object.entries(groups).sort((a, b) => b[1].length - a[1].length)[0];
  return { series: best ? best[1][0] : undefined, prefix: best ? best[0] : null };
}

function browserExtract(req) {
  const ok = (s) => /^[A-Za-z][\w-]*$/.test(s);
  const sigOf = (el) => el.tagName.toLowerCase() + [...el.classList].filter(ok).slice(0, 3).map((c) => '.' + CSS.escape(c)).join('');
  const uniqueSel = (el) => {
    const s = sigOf(el);
    if (document.querySelectorAll(s).length === 1) return s;
    const parts = [];
    for (let n = el; n && n.nodeType === 1 && n !== document.documentElement; n = n.parentElement) {
      if (n.id && ok(n.id)) { parts.unshift('#' + n.id); break; }
      const sibs = n.parentElement ? [...n.parentElement.children].filter((c) => c.tagName === n.tagName) : [];
      parts.unshift(n.tagName.toLowerCase() + (sibs.length > 1 ? ':nth-of-type(' + (sibs.indexOf(n) + 1) + ')' : ''));
    }
    return parts.join(' > ');
  };
  const hrefOf = (c) => { const a = c.querySelector('a[href]'); return a ? a.href : ''; };

  if (req.op === 'list') {
    const out = [];
    for (const P of document.querySelectorAll('body, body *')) {
      const groups = new Map();
      for (const c of P.children) {
        const s = sigOf(c);
        if (!groups.has(s)) groups.set(s, []);
        groups.get(s).push(c);
      }
      for (const [s, arr] of groups) {
        const items = arr.filter((c) => c.querySelector('a[href]') && c.querySelector('img'));
        if (items.length < 6) continue;
        const segs = {};
        for (const c of items) {
          try {
            const u = new URL(hrefOf(c));
            const sg = u.origin === location.origin ? u.pathname.split('/').filter(Boolean)[0] : '';
            if (sg) segs[sg] = (segs[sg] || 0) + 1;
          } catch {}
        }
        const top = Object.entries(segs).sort((a, b) => b[1] - a[1])[0];
        const it = items[0];
        const im = it.querySelector('img');
        const alt = (im.getAttribute('alt') || '').trim();
        const src = im.getAttribute('src') || '';
        const lazy = ['data-src', 'data-lazy-src', 'data-original'].find((a) => im.getAttribute(a));
        const attr = src && !src.startsWith('data:') ? 'src' : (lazy || 'src');
        const hd = it.querySelector('h1,h2,h3,h4,h5,h6');
        let title = 'a';
        if (alt) title = 'img|attr:alt';
        else if (hd) title = hd.tagName.toLowerCase();
        else if (it.querySelector('[class*="title"]')) title = '[class*="title"]';
        out.push({
          item: s, count: items.length, link: 'a', title, cover: 'img@' + attr,
          prefix: top && top[1] >= items.length * 0.6 ? top[0] : '', path: location.pathname, url: location.href,
        });
      }
    }
    return out;
  }

  if (req.op === 'hrefs') {
    try { return [...document.querySelectorAll(req.item)].map(hrefOf).filter(Boolean); } catch { return []; }
  }

  if (req.op === 'detail') {
    const out = { title: '', cover: '', description: '', genres: '', status: '', chapters: null };
    const h1 = document.querySelector('h1');
    if (h1 && h1.textContent.trim()) out.title = uniqueSel(h1);
    const og = document.querySelector('meta[property="og:image"]');
    if (og && og.content) out.cover = 'meta[property="og:image"]@content';
    else {
      let best = null, area = 0;
      for (const im of document.images) {
        const r = im.getBoundingClientRect();
        if (r.width * r.height > area) { area = r.width * r.height; best = im; }
      }
      if (best) {
        const src = best.getAttribute('src') || '';
        out.cover = uniqueSel(best) + '@' + (src && !src.startsWith('data:') ? 'src' : 'data-src');
      }
    }
    const dEl = [...document.querySelectorAll('[class],[id]')].find((e) =>
      /desc|summary|synopsis/i.test((e.getAttribute('class') || '') + ' ' + (e.id || '')) && e.textContent.trim().length > 40);
    if (dEl) out.description = uniqueSel(dEl);
    else if (document.querySelector('meta[name="description"]')) out.description = 'meta[name="description"]@content';
    const gEl = [...document.querySelectorAll('[class]')].find((e) => /genre/i.test(e.getAttribute('class')) && e.textContent.trim());
    if (gEl) out.genres = uniqueSel(gEl);
    const sEl = [...document.querySelectorAll('[class]')].find((e) => /status/i.test(e.getAttribute('class')) && e.textContent.trim());
    if (sEl) out.status = uniqueSel(sEl);

    const sp = req.seriesPath || '';
    const anchors = [];
    for (const a of document.querySelectorAll('a[href]')) {
      let u;
      try { u = new URL(a.href); } catch { continue; }
      if (u.origin !== location.origin || u.pathname.replace(/\/$/, '') === sp) continue;
      if ((sp && u.pathname.startsWith(sp + '/')) || /bolum|chapter|bölüm|episode/i.test(u.href)) anchors.push(a);
    }
    const byParent = new Map();
    for (const a of anchors) {
      const k = a.parentElement ? sigOf(a.parentElement) : '';
      if (!k) continue;
      if (!byParent.has(k)) byParent.set(k, []);
      byParent.get(k).push(a);
    }
    let pick = null;
    for (const [k, arr] of byParent) {
      if (arr.length >= 3 && new Set(arr.map((a) => a.parentElement)).size >= 3 && (!pick || arr.length > pick.arr.length)) pick = { k, arr, mode: 'parent' };
    }
    if (!pick) {
      const bySelf = new Map();
      for (const a of anchors) {
        const k = sigOf(a);
        if (!bySelf.has(k)) bySelf.set(k, []);
        bySelf.get(k).push(a);
      }
      for (const [k, arr] of bySelf) {
        if (arr.length >= 3 && (!pick || arr.length > pick.arr.length)) pick = { k, arr, mode: 'self' };
      }
    }
    if (pick) {
      out.chapters = pick.mode === 'parent'
        ? { item: pick.k, link: 'a@href', title: 'a', count: pick.arr.length, mode: 'parent' }
        : { item: pick.k, link: '@href', title: '', count: pick.arr.length, mode: 'self' };
    }
    return out;
  }

  if (req.op === 'reader') {
    const imgs = [...document.images].filter((im) => im.getBoundingClientRect().width >= 300);
    if (!imgs.length) return null;
    let anc = imgs[0].parentElement;
    while (anc && anc !== document.body && !imgs.every((im) => anc.contains(im))) anc = anc.parentElement;
    anc = anc || document.body;
    let attr = 'src', bestN = -1;
    for (const a of ['src', 'data-src', 'data-lazy-src', 'data-original']) {
      const n = imgs.filter((im) => { const v = im.getAttribute(a); return v && !v.startsWith('data:'); }).length;
      if (n > bestN) { bestN = n; attr = a; }
      if (n === imgs.length) break;
    }
    return { images: uniqueSel(anc) + ' img', attr, count: imgs.length };
  }
  return null;
}

const evalDom = (page, req) => page.evaluate(browserExtract, req).catch(() => null);
const bestOf = (cands) => cands.reduce((b, c) => (!b || c.count > b.count ? c : b), null);

async function checkPagination(page, best) {
  try {
    await page.goto(best.url, { waitUntil: 'domcontentloaded', timeout: 30000 });
    await page.waitForTimeout(1000);
  } catch {}
  const first = (await evalDom(page, { op: 'hrefs', item: best.item })) || [];
  if (!first.length) return null;
  const q = new URL(best.url);
  q.searchParams.set('page', '2');
  const p = new URL(best.url);
  p.pathname = p.pathname.replace(/\/$/, '') + '/page/2';
  for (const [kind, u] of [['query', q.href], ['path', p.href]]) {
    try {
      await page.goto(u, { waitUntil: 'domcontentloaded', timeout: 30000 });
      await page.waitForTimeout(1000);
    } catch { continue; }
    const second = (await evalDom(page, { op: 'hrefs', item: best.item })) || [];
    if (second.length && second.some((h) => !first.includes(h))) return { kind };
  }
  return null;
}

function classify(u) {
  const s = u.toLowerCase();
  if (/chapters(\?|\/?$)/.test(s)) return 'detail';
  if (/chapter|reader|image|img|\/read\b/.test(s)) return 'reader';
  if (/list|browse|search|popular|latest|catalog|filter|page=|series(\?|$)|manga(\?|$)/.test(s)) return 'list';
  if (/detail|info|series\/|manga\/|novel\//.test(s)) return 'detail';
  return 'other';
}

const hostOf = (u) => { try { return new URL(u).host; } catch { return ''; } };

function buildSpec({ site, log, best, pag, detailSpec, readerSpec }) {
  const domain = new URL(site).host;
  const notes = [];
  const L = best
    ? { path: new URL(best.url).pathname, pageParam: pag && pag.kind === 'query' ? 'page' : '', item: best.item, link: best.link, title: best.title, cover: best.cover, itemCount: best.count }
    : { path: '', pageParam: '', item: '', link: '', title: '', cover: '', itemCount: 0 };
  if (best) {
    notes.push(`list: ${best.count} items at ${L.path}`);
    if (best.prefix) notes.push('list link prefix: ' + best.prefix);
    notes.push(pag ? (pag.kind === 'query' ? 'pagination: ?page=N' : 'pagination: /page/N (pageParam empty)') : 'pagination: not detected');
  } else notes.push('list: no repeated card group (>=6) found');
  const D = detailSpec || {};
  const ch = D.chapters || null;
  const detail = {
    title: D.title || '', cover: D.cover || '', description: D.description || '', genres: D.genres || '', status: D.status || '',
    chapterItem: ch ? ch.item : '', chapterLink: ch ? ch.link : '', chapterTitle: ch ? ch.title : '',
  };
  if (!detailSpec) notes.push('detail: series page not found');
  else if (!ch) notes.push('detail: no chapter group (>=3) found');
  else if (ch.mode === 'self') notes.push('chapterLink "@href": item is the link itself');
  const R = readerSpec || {};
  const reader = { images: R.images || '', attr: R.attr || '', count: R.count || 0 };
  if (!readerSpec) notes.push('reader: no chapter image >=300px found');
  const apiCalls = log.calls.filter((c) => c.url);
  apiCalls.sort((a, b) => Number(hostOf(a.url) !== domain) - Number(hostOf(b.url) !== domain));
  const seen = new Set();
  const api = [];
  for (const c of apiCalls) {
    const key = c.method + ' ' + c.url.split('?')[0];
    if (seen.has(key)) continue;
    seen.add(key);
    api.push({ url: c.url, method: c.method, kind: classify(c.url) });
    if (api.length >= 30) break;
  }
  const frac = (vals, n) => Math.round((vals.filter(Boolean).length / n) * 100) / 100;
  return {
    domain,
    title: log.title || '',
    mode: best || !api.some((a) => a.kind === 'list') ? 'html' : 'json',
    list: L,
    detail,
    reader,
    api,
    confidence: {
      list: frac([L.item, L.link, L.title, L.cover], 4),
      detail: frac([detail.title, detail.cover, detail.description, detail.genres, detail.status, detail.chapterItem, detail.chapterLink, detail.chapterTitle], 8),
      reader: frac([reader.images, reader.attr, reader.count > 0], 3),
    },
    notes,
  };
}

async function visit(page, url, log, tag) {
  const calls = [];
  const onResp = async (r) => {
    try {
      const u = r.url();
      const ct = (r.headers()['content-type'] || '').toLowerCase();
      const req = r.request();
      if (ct.includes('json')) {
        let body = '';
        try { body = (await r.text()).slice(0, 700); } catch {}
        calls.push({ tag, method: req.method(), url: u, status: r.status(), ct, post: (req.postData() || '').slice(0, 200), body });
      } else if (/\.(jpe?g|png|webp|avif)(\?|$)/i.test(u) && req.resourceType() === 'image') {
        calls.push({ tag, image: u });
      }
    } catch {}
  };
  page.on('response', onResp);
  let status = 0;
  try {
    const resp = await page.goto(url, { waitUntil: 'networkidle', timeout: 45000 });
    status = resp ? resp.status() : 0;
  } catch (e) {
    log.errors.push(`${tag}: ${String(e).slice(0, 120)}`);
  }
  await page.waitForTimeout(1500);
  try { fs.writeFileSync('recon-out/' + new URL(url).host + '.' + tag + '.html', (await page.content()).slice(0, 200000)); } catch {}
  page.off('response', onResp);
  log.calls.push(...calls);
  return status;
}

const browser = await chromium.launch({ args: ['--no-sandbox'] });
for (const raw of sites) {
  const site = /^https?:\/\//.test(raw) ? raw : "https://" + raw;
  const origin = new URL(site).origin;
  const log = { site, calls: [], errors: [], frameworks: [], links: {} };
  const ctx = await browser.newContext({ userAgent: UA, viewport: { width: 412, height: 915 } });
  const page = await ctx.newPage();
  const cands = [];
  const st = await visit(page, site, log, 'home');
  cands.push(...((await evalDom(page, { op: 'list' })) || []));
  log.homeStatus = st;
  log.title = await page.title().catch(() => '');
  const html = await page.content().catch(() => '');
  for (const [k, re] of Object.entries({
    next: /__NEXT_DATA__|_next\/static/, nuxt: /__NUXT__|_nuxt\//, wordpress: /wp-content|wp-json/,
    madara: /wp-manga|madara/, vue: /data-v-[0-9a-f]{6}/, react: /data-reactroot|id="root"/, cloudflare: /just a moment|challenge-platform/i,
  })) if (re.test(html)) log.frameworks.push(k);
  for (const p of ['series', 'manga', 'webtoon', 'webtoons', 'browse', 'search?q=a', 'api/series', 'api/manga']) {
    await visit(page, origin + '/' + p, log, 'list:' + p.replace(/[^a-z]/g, ''));
    cands.push(...((await evalDom(page, { op: 'list' })) || []));
  }
  await page.goto(site, { waitUntil: 'domcontentloaded', timeout: 30000 }).catch(() => {});
  const links = await page.$$eval('a[href]', (as) => as.map((a) => a.href)).catch(() => []);
  const { series } = pickLinks(links, origin);
  log.links.series = series || null;
  let detailSpec = null, readerSpec = null;
  if (series) {
    await visit(page, series, log, 'detail');
    const sp = new URL(series).pathname.replace(/\/$/, '');
    detailSpec = await evalDom(page, { op: 'detail', seriesPath: sp });
    const links2 = await page.$$eval('a[href]', (as) => as.map((a) => a.href)).catch(() => []);
    const chap = links2.map((h) => h.split('#')[0]).filter((h) => h.startsWith(origin)).find((h) => new URL(h).pathname.startsWith(sp + '/') || /(bolum|chapter|episode)/i.test(h));
    log.links.chapter = chap || null;
    if (chap) {
      await visit(page, chap, log, 'reader');
      readerSpec = await evalDom(page, { op: 'reader' });
    }
  }
  const bytag = {};
  for (const c of log.calls) (bytag[c.tag] ||= []).push(c);
  console.log(`RECON ${log.site} status=${log.homeStatus} title=[${(log.title || '').slice(0, 60)}] fw=${log.frameworks.join(',')}`);
  console.log(`  series=${log.links.series} chapter=${log.links.chapter}`);
  for (const [tag, cs] of Object.entries(bytag)) {
    const seen = new Set();
    for (const c of cs) {
      const key = (c.url || c.image).split('?')[0];
      if (seen.has(key)) continue;
      seen.add(key);
      if (seen.size > 8) break;
      console.log(c.image ? `  [${tag}] IMG ${c.image.slice(0, 140)}` : `  [${tag}] ${c.method} ${c.status} ${c.url.slice(0, 160)} ${c.post ? 'POST=' + c.post : ''}\n      ${c.body.replace(/\s+/g, ' ').slice(0, 260)}`);
    }
  }
  if (log.errors.length) console.log('  errors: ' + log.errors.join(' | '));
  fs.writeFileSync(`recon-out/${new URL(site).host}.json`, JSON.stringify(log, null, 1));
  const best = bestOf(cands);
  const pag = best ? await checkPagination(page, best) : null;
  const spec = buildSpec({ site, log, best, pag, detailSpec, readerSpec });
  fs.writeFileSync(`recon-out/${spec.domain}.spec.json`, JSON.stringify(spec, null, 1));
  await ctx.close();
}
await browser.close();
