#!/usr/bin/env node
// Asama 3 - otomatik onarim denemesi. Girdi: data/triage_stage2.json (fail/selector_broken olan,
// kind=="generated" kayitlar). Her domain icin recon.mjs (Playwright, JS-render DOM) ile yeniden
// tarar, ONERILEN SELECTOR'LERI DUZ FETCH ILE CEKILEN STATIK HTML'E KARSI DOGRULAR (ragnarscans
// kok nedeni: recon JS-render DOM'dan selector cikariyor, ama Jsoup/parser statik HTML okur; bu
// adim runtime-only class'lari -orn. UIkit'in uk-grid-margin gibi JS'le ekledigi class'lari-
// elemek icin var). Dogrulanan spec ile genparser.mjs calistirilir.
//
// kind=="override"/"upstream" olanlar icin KOD DEGISTIRILMEZ (base-class parametreli upstream
// parser'lari regex ile guvenilir sekilde yamalayamayiz) - sadece "manuel inceleme" raporu yazilir.
//
// Kullanim: npm init -y >/dev/null; npm i playwright@1.49.1 cheerio@1.0.0 >/dev/null
//           npx playwright install chromium >/dev/null
//           node scripts/repair_stage3.mjs [--only=domain1,domain2]
// Cikti: data/triage_stage3.json, degisen generated/*/jar/*.kt dosyalari (commit edilmemis)
import { execSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import * as cheerio from 'cheerio';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const STAGE2_PATH = path.join(ROOT, 'data/triage_stage2.json');
const TRIAGE_PATH = path.join(ROOT, 'data/triage.json');
const OUT_PATH = path.join(ROOT, 'data/triage_stage3.json');

function readJson(p) { return JSON.parse(fs.readFileSync(p, 'utf8')); }

async function fetchStatic(url) {
	try {
		const res = await fetch(url, {
			headers: { 'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36' },
			signal: AbortSignal.timeout(15000),
		});
		if (!res.ok) return null;
		return await res.text();
	} catch {
		return null;
	}
}

// recon.mjs'in onerdigi CSS secici, statik HTML'de GERCEKTEN en az 1 element esliyor mu. cheerio
// (gercek CSS secici motoru) kullanilir - regex tabanli class-varlik kontrolu id/nth-of-type
// seciciler icin yanlislikla "gecerli" diyebiliyordu (hic class'i olmayan secici otomatik gecerdi).
function selectorLooksPresent(html, css) {
	if (!css) return false;
	try {
		const $ = cheerio.load(html);
		return $(css).length > 0;
	} catch {
		return false; // cheerio'nun ayristiramadigi secici: guvenli taraf, gecersiz say
	}
}

function validateSpecAgainstStatic(spec, htmlByTag) {
	// recon.mjs ayni domain icin recon-out/<host>.<tag>.html dosyalarini (home/list:*/detail/reader)
	// Playwright ile cekip kaydeder - bunlar JS calismis DOM degil, PAGE.CONTENT() ciktisidir, yani
	// "statik" sayilmaz (JS render sonrasi DOM serialize edilir). Bu yuzden secici dogrulamasini
	// AYRICA duz fetch() ile cekilen gercek statik HTML'e karsi yapiyoruz (fetchStatic ile).
	const notes = [];
	let ok = true;
	const checkField = (label, css, html) => {
		if (!css || !html) return;
		if (!selectorLooksPresent(html, css)) {
			ok = false;
			notes.push(`${label} "${css}" statik (duz fetch) HTML'de yok (runtime-only class olasi)`);
		}
	};
	checkField('list.item', spec.list?.item, htmlByTag.list);
	checkField('detail.chapterItem', spec.detail?.chapterItem, htmlByTag.detail);
	checkField('reader.images', spec.reader?.images, htmlByTag.reader);
	return { ok, notes };
}

async function reconAndRepair(domain, nsfw) {
	const outDir = path.join(ROOT, 'recon-out');
	fs.rmSync(outDir, { recursive: true, force: true });
	try {
		execSync(`node scripts/recon.mjs "https://${domain}"`, { cwd: ROOT, stdio: 'pipe', timeout: 120000 });
	} catch (e) {
		return { domain, repaired: false, reason: `recon basarisiz: ${String(e).slice(0, 200)}` };
	}
	const specPath = path.join(outDir, `${domain}.spec.json`);
	if (!fs.existsSync(specPath)) {
		return { domain, repaired: false, reason: 'recon spec.json uretmedi (site analiz edilemedi)' };
	}
	const spec = readJson(specPath);
	const logPath = path.join(outDir, `${domain}.json`);
	const log = fs.existsSync(logPath) ? readJson(logPath) : {};

	// Statik dogrulama: list/detay/bolum sayfalarini DUZ fetch ile cek (Playwright/JS DEGIL),
	// onerilen selector'lerin orada da var olup olmadigina bak. Bu, ragnarscans tipi hatayi
	// (secici JS-render DOM'dan cikarilmis ama Jsoup/parser statik HTML okur) yakalar.
	const htmlByTag = {};
	const urls = { list: spec.list?.url, detail: log.links?.series, reader: log.links?.chapter };
	for (const [tag, url] of Object.entries(urls)) {
		if (!url) continue;
		const html = await fetchStatic(url);
		if (html) htmlByTag[tag] = html;
	}
	const validation = validateSpecAgainstStatic(spec, htmlByTag);
	if (!validation.ok) {
		return { domain, repaired: false, reason: `aday selector statik HTML'de dogrulanamadi: ${validation.notes.join('; ')}`, spec_notes: spec.notes };
	}

	const genDir = path.join(ROOT, 'generated', domain, 'jar');
	let oldCode = null;
	if (fs.existsSync(genDir)) {
		const files = fs.readdirSync(genDir).filter((f) => f.endsWith('.kt'));
		if (files.length) oldCode = fs.readFileSync(path.join(genDir, files[0]), 'utf8');
	}

	try {
		execSync(`node scripts/genparser.mjs "recon-out/${domain}.spec.json" --nsfw ${nsfw ? 1 : 0}`, { cwd: ROOT, stdio: 'pipe', timeout: 30000 });
	} catch (e) {
		return { domain, repaired: false, reason: `genparser basarisiz: ${String(e).slice(0, 200)}` };
	}

	const files = fs.existsSync(genDir) ? fs.readdirSync(genDir).filter((f) => f.endsWith('.kt')) : [];
	const newCode = files.length ? fs.readFileSync(path.join(genDir, files[0]), 'utf8') : null;
	if (oldCode !== null && newCode === oldCode) {
		return { domain, repaired: false, reason: 'yeniden uretim ayni sonucu verdi (site yapisi spec ile uyumsuz, veya zaten dogruydu)' };
	}
	fs.mkdirSync(path.join(ROOT, 'data/recon'), { recursive: true });
	fs.copyFileSync(specPath, path.join(ROOT, 'data/recon', `${domain}.spec.json`));
	return { domain, repaired: true, reason: 'parser yeniden uretildi ve statik HTML ile dogrulandi', file: files[0] ? `generated/${domain}/jar/${files[0]}` : null };
}

async function main() {
	const onlyArg = process.argv.find((a) => a.startsWith('--only='));
	const only = onlyArg ? new Set(onlyArg.slice('--only='.length).split(',').filter(Boolean)) : null;

	const stage2 = readJson(STAGE2_PATH).results;
	const triage = {};
	for (const e of readJson(TRIAGE_PATH).entries) triage[e.domain] = e;

	let targets = Object.values(stage2)
		.filter((r) => (r.stage2 === 'fail' || r.stage2 === 'selector_broken'))
		.map((r) => r.domain)
		.filter((d) => triage[d]?.kind === 'generated');
	if (only) targets = targets.filter((d) => only.has(d));

	console.log(`Onarim denenecek (kind=generated, fail/selector_broken): ${targets.length}`);

	const results = [];
	for (const domain of targets) {
		console.log(`== ${domain}`);
		const r = await reconAndRepair(domain, triage[domain]?.nsfw);
		console.log(`   -> ${r.repaired ? 'ONARILDI' : 'onarilamadi'}: ${r.reason}`);
		results.push(r);
	}

	// kind == override/upstream olanlar icin otomatik kod degisikligi yapilmaz; manuel inceleme notu.
	const manualReview = Object.values(stage2)
		.filter((r) => (r.stage2 === 'fail' || r.stage2 === 'selector_broken'))
		.map((r) => r.domain)
		.filter((d) => triage[d] && triage[d].kind !== 'generated')
		.map((d) => ({ domain: d, kind: triage[d].kind, code_path: triage[d].code_path,
			reason: 'upstream/override parser: otomatik selector yamasi guvenilir degil, manuel inceleme gerekli' }));

	const out = { generated_from: 'triage_stage2.json', repaired: results.filter((r) => r.repaired).length,
		attempted: results.length, manual_review_count: manualReview.length,
		results, manual_review: manualReview };
	fs.mkdirSync(path.dirname(OUT_PATH), { recursive: true });
	fs.writeFileSync(OUT_PATH, JSON.stringify(out, null, 2) + '\n', 'utf8');
	console.log(`\nOutput: ${OUT_PATH}`);
	console.log(`  onarildi=${out.repaired}/${out.attempted}  manuel_inceleme=${out.manual_review_count}`);
}

main();
