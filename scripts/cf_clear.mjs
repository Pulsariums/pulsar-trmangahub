// Cloudflare "Just a moment" kapisini gercek Chromium ile gecip cf_clearance cerezlerini
// Netscape cookies.txt olarak yazar (canli test bunu /cookies.txt kaynagi olarak yukler).
// Kullanim: node scripts/cf_clear.mjs <cikis.txt> <UA> domain1 domain2 ...
import fs from 'node:fs';
import { chromium } from 'playwright';

const [out, ua, ...domains] = process.argv.slice(2);
const lines = ['# Netscape HTTP Cookie File'];
const report = [];
const browser = await chromium.launch({ args: ['--disable-blink-features=AutomationControlled'] });

async function one(domain) {
  const ctx = await browser.newContext({ userAgent: ua, viewport: { width: 412, height: 915 }, locale: 'tr-TR' });
  const page = await ctx.newPage();
  let state = 'fail';
  try {
    await page.goto(`https://${domain}/`, { waitUntil: 'domcontentloaded', timeout: 30000 });
    for (let i = 0; i < 12; i++) {
      const title = (await page.title().catch(() => '')) || '';
      const html = await page.content().catch(() => '');
      const challenge = /just a moment|bir dakika|checking your browser|cf-challenge|challenge-platform/i.test(title + html.slice(0, 4000));
      if (!challenge && html.length > 2000) { state = 'passed'; break; }
      if (/turnstile|cf-turnstile|g-recaptcha|hcaptcha/i.test(html)) state = 'interactive';
      await page.waitForTimeout(2500);
    }
    if (state !== 'passed' && state !== 'interactive') state = 'timeout';
    const cookies = await ctx.cookies();
    for (const c of cookies) {
      const host = c.domain.replace(/^\./, '');
      const exp = c.expires && c.expires > 0 ? Math.floor(c.expires) : Math.floor(Date.now() / 1000) + 3600;
      lines.push(`${c.httpOnly ? '#HttpOnly_' : ''}${host}\tTRUE\t${c.path || '/'}\t${c.secure ? 'TRUE' : 'FALSE'}\t${exp}\t${c.name}\t${c.value}`);
    }
    if (state === 'passed' && !cookies.some((c) => c.name === 'cf_clearance')) state = 'passed_nocookie';
  } catch (e) {
    state = 'error:' + String(e.message).slice(0, 60);
  }
  await ctx.close();
  report.push({ domain, state });
}

const queue = [...domains];
await Promise.all(Array.from({ length: 4 }, async () => { for (let d; (d = queue.shift());) await one(d); }));
await browser.close();
fs.writeFileSync(out, lines.join('\n') + '\n');
fs.writeFileSync(out + '.report.json', JSON.stringify(report, null, 1));
for (const r of report) console.log(`${r.state}\t${r.domain}`);
