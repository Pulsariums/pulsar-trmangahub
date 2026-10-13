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
  const st = await visit(page, site, log, 'home');
  log.homeStatus = st;
  log.title = await page.title().catch(() => '');
  const html = await page.content().catch(() => '');
  for (const [k, re] of Object.entries({
    next: /__NEXT_DATA__|_next\/static/, nuxt: /__NUXT__|_nuxt\//, wordpress: /wp-content|wp-json/,
    madara: /wp-manga|madara/, vue: /data-v-[0-9a-f]{6}/, react: /data-reactroot|id="root"/, cloudflare: /just a moment|challenge-platform/i,
  })) if (re.test(html)) log.frameworks.push(k);
  for (const p of ['series', 'manga', 'webtoon', 'webtoons', 'browse', 'search?q=a', 'api/series', 'api/manga']) {
    await visit(page, origin + '/' + p, log, 'list:' + p.replace(/[^a-z]/g, ''));
  }
  await page.goto(site, { waitUntil: 'domcontentloaded', timeout: 30000 }).catch(() => {});
  const links = await page.$eval('a[href]', (as) => as.map((a) => a.href)).catch(() => []);
  const { series } = pickLinks(links, origin);
  log.links.series = series || null;
  if (series) {
    await visit(page, series, log, 'detail');
    const links2 = await page.$$eval('a[href]', (as) => as.map((a) => a.href)).catch(() => []);
    const sp = new URL(series).pathname.replace(/\/$/, '');
    const chap = links2.map((h) => h.split('#')[0]).filter((h) => h.startsWith(origin)).find((h) => new URL(h).pathname.startsWith(sp + '/') || /(bolum|chapter|episode)/i.test(h));
    log.links.chapter = chap || null;
    if (chap) await visit(page, chap, log, 'reader');
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
  await ctx.close();
}
await browser.close();
