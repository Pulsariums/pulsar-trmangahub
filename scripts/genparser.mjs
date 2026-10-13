#!/usr/bin/env node
// Kullanim: node scripts/genparser.mjs <spec.json> [--name Ad] [--nsfw 0|1] [--out dir]
// Cikti: <out>/<domain>/jar/<Ad>.kt (varsayilan out = generated/). --out verildiginde kayit dosyasi degismez.
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const TEMPLATE = path.join(ROOT, 'scripts/templates/jar_html.kt.tmpl');
const REGISTRY = path.join(ROOT, 'sources/custom/sources.json');
const PARSER_REGISTRIES = ['sources/tr/sources.json', 'sources/global/sources.json'];

const die = (msg) => {
	console.error(`genparser: ${msg}`);
	process.exit(1);
};

function parseArgs(argv) {
	const opts = { spec: null, name: null, nsfw: '0', out: null };
	for (let i = 0; i < argv.length; i++) {
		const a = argv[i];
		if (a === '--name' || a === '--nsfw' || a === '--out') {
			const v = argv[++i];
			if (v === undefined || v.startsWith('--')) die(`${a} bir değer ister`);
			opts[a.slice(2)] = v;
		} else if (a.startsWith('--')) {
			die(`bilinmeyen seçenek: ${a}`);
		} else if (opts.spec === null) {
			opts.spec = a;
		} else {
			die(`fazla argüman: ${a}`);
		}
	}
	if (!opts.spec) die('kullanım: node scripts/genparser.mjs <spec.json> [--name Ad] [--nsfw 0|1] [--out dir]');
	if (opts.nsfw !== '0' && opts.nsfw !== '1') die('--nsfw 0 veya 1 olmalı');
	return opts;
}

// Kotlin string literali: \, ", $ kacirilir.
const kstr = (s) =>
	'"' + String(s).replace(/\\/g, '\\\\').replace(/"/g, '\\"').replace(/\$/g, '\\$').replace(/\n/g, '\\n') + '"';

// 'css' | 'css@attr' | 'attr:alt' (attr:alt = mevcut elemanin ozniteligi)
function parseSel(raw, label) {
	if (raw === undefined || raw === null || raw === '') return null;
	if (typeof raw !== 'string') die(`${label}: seçici metin olmalı`);
	const s = raw.trim();
	let m = /^attr:([\w:-]+)$/.exec(s);
	if (m) return { css: null, attr: m[1] };
	m = /^(.+?)\s*\|\s*attr:([\w:-]+)$/.exec(s);
	if (m) return { css: m[1].trim(), attr: m[2] };
	m = /^(.+)@([\w:-]+)$/.exec(s);
	if (m) return { css: m[1].trim(), attr: m[2] };
	return { css: s, attr: null };
}

const selExpr = (sel) =>
	sel === null ? 'null' : `Sel(${sel.css === null ? 'null' : kstr(sel.css)}, ${sel.attr === null ? 'null' : kstr(sel.attr)})`;

const cssOnly = (sel, label) => {
	if (sel === null) die(`${label} eksik`);
	return sel.css ?? die(`${label}: CSS seçici gerekli`);
};

const FOLD = { ı: 'i', İ: 'I', ğ: 'g', Ğ: 'G', ş: 's', Ş: 'S', ç: 'c', Ç: 'C', ö: 'o', Ö: 'O', ü: 'u', Ü: 'U' };
const asciiIdent = (s) => s.replace(/[ıİğĞşŞçÇöÖüÜ]/g, (c) => FOLD[c]).replace(/[^A-Za-z0-9]/g, '');

function clashes(id) {
	for (const rel of PARSER_REGISTRIES) {
		const file = path.join(ROOT, rel);
		if (!fs.existsSync(file)) continue;
		const j = JSON.parse(fs.readFileSync(file, 'utf8'));
		for (const s of j.sources ?? []) {
			const p = s.formats?.jar?.parser;
			if (p && p.toUpperCase() === id) return true;
		}
	}
	return false;
}

const nowIso = () => new Date().toISOString().replace(/\.\d{3}Z$/, '+00:00');

function main() {
	const opts = parseArgs(process.argv.slice(2));

	let spec;
	try {
		spec = JSON.parse(fs.readFileSync(opts.spec, 'utf8'));
	} catch (e) {
		die(`spec okunamadı: ${e.message}`);
	}

	if (spec.mode !== 'html') die(`desteklenmeyen mode: ${spec.mode} (yalnızca "html")`);
	const domain = String(spec.domain ?? '')
		.trim()
		.toLowerCase()
		.replace(/^https?:\/\//, '')
		.replace(/\/.*$/, '');
	if (!/^[a-z0-9-]+(\.[a-z0-9-]+)+$/.test(domain)) die(`geçersiz domain: "${spec.domain}"`);

	const list = spec.list ?? {};
	const detail = spec.detail ?? {};
	const reader = spec.reader ?? {};

	const ident = asciiIdent(domain.split('.')[0]).toLowerCase();
	if (!ident || /^\d/.test(ident)) die('domainin ilk etiketi harfle başlamalı');

	let className;
	if (opts.name !== null) {
		className = asciiIdent(opts.name);
		if (!/^[A-Za-z]/.test(className)) die(`--name geçersiz: "${opts.name}"`);
		className = className[0].toUpperCase() + className.slice(1);
	} else {
		className = ident[0].toUpperCase() + ident.slice(1);
	}

	// Uzun site basliklarindan kisa gorunen ad cikar: "Ad - slogan" / "Ad | slogan" -> "Ad"
	const shortTitle = (t) => {
		const first = String(t ?? '').split(/\s+[-|–—:]\s+/)[0].trim();
		return first.length > 32 ? first.slice(0, 32).trim() : first;
	};
	const title = (opts.name ? String(opts.name) : shortTitle(spec.title)) || className;

	let parserId = ident.toUpperCase();
	if (clashes(parserId)) parserId += '_TR';
	if (clashes(parserId)) die(`parser kimliği çakışıyor: ${parserId}`);

	const listPath = list.path ?? '/';
	const listItem = cssOnly(parseSel(list.item, 'list.item'), 'list.item');
	const listLink = parseSel(list.link, 'list.link');
	if (listLink === null) die('list.link eksik');
	const chapterItem = cssOnly(parseSel(detail.chapterItem, 'detail.chapterItem'), 'detail.chapterItem');
	const chapterLink = parseSel(detail.chapterLink, 'detail.chapterLink');
	if (chapterLink === null) die('detail.chapterLink eksik');
	const readerImages = parseSel(reader.images, 'reader.images');
	if (readerImages === null || !readerImages.css) die('reader.images eksik');

	const readerAttrs = [...new Set([readerImages.attr ?? reader.attr, 'data-src', 'src'].filter(Boolean))];
	const searchSupported = list.search === true;

	const vars = {
		PKG: ident,
		LANG: 'tr',
		ID: parserId,
		CLASS: className,
		TITLE_LIT: kstr(title),
		ANNOTATION_EXTRA: opts.nsfw === '1' ? ', ContentType.HENTAI' : '',
		DOMAIN_LIT: kstr(domain),
		SEARCH_SUPPORTED: String(searchSupported),
		LIST_PATH_LIT: kstr(listPath),
		PAGE_PARAM_LIT: list.pageParam ? kstr(list.pageParam) : 'null',
		LIST_ITEM_LIT: kstr(listItem),
		CHAPTER_ITEM_LIT: kstr(chapterItem),
		READER_IMAGES_LIT: kstr(readerImages.css),
		READER_ATTRS: 'listOf(' + readerAttrs.map(kstr).join(', ') + ')',
		SEL_LIST_LINK: selExpr(listLink),
		SEL_LIST_TITLE: selExpr(parseSel(list.title, 'list.title')),
		SEL_LIST_COVER: selExpr(parseSel(list.cover, 'list.cover')),
		SEL_DETAIL_TITLE: selExpr(parseSel(detail.title, 'detail.title')),
		SEL_DETAIL_COVER: selExpr(parseSel(detail.cover, 'detail.cover')),
		SEL_DETAIL_DESCRIPTION: selExpr(parseSel(detail.description, 'detail.description')),
		SEL_DETAIL_GENRES: selExpr(parseSel(detail.genres, 'detail.genres')),
		SEL_DETAIL_STATUS: selExpr(parseSel(detail.status, 'detail.status')),
		SEL_CHAPTER_LINK: selExpr(chapterLink),
		SEL_CHAPTER_TITLE: selExpr(parseSel(detail.chapterTitle, 'detail.chapterTitle')),
	};

	const template = fs.readFileSync(TEMPLATE, 'utf8');
	const code = template.replace(/\{\{([A-Z_]+)\}\}/g, (m, key) => {
		if (!(key in vars)) die(`şablon yer tutucusu bilinmiyor: ${key}`);
		return vars[key];
	});

	const base = opts.out ? path.resolve(opts.out) : path.join(ROOT, 'generated');
	const dir = path.join(base, domain, 'jar');
	fs.mkdirSync(dir, { recursive: true });
	const outFile = path.join(dir, `${className}.kt`);
	fs.writeFileSync(outFile, code, 'utf8');
	console.log(`yazildi: ${outFile} (parser ${parserId}, itemCount ${list.itemCount ?? '-'}, count ${reader.count ?? '-'})`);

	if (opts.out) {
		console.log('--out kullanıldığı için sources/custom/sources.json değiştirilmedi');
		return;
	}

	const registry = fs.existsSync(REGISTRY) ? JSON.parse(fs.readFileSync(REGISTRY, 'utf8')) : [];
	const entry = {
		id: domain,
		name: title,
		domain,
		baseUrl: `https://${domain}`,
		engine: 'custom',
		scope: 'tr_native',
		verdict: 'scaffolded',
		scaffold: [`generated/${domain}/jar/${className}.kt`],
		addedAt: nowIso(),
	};
	const idx = registry.findIndex((e) => e.id === domain);
	if (idx >= 0) registry[idx] = entry;
	else registry.push(entry);
	fs.writeFileSync(REGISTRY, JSON.stringify(registry, null, 2) + '\n', 'utf8');
	console.log(`kayit: ${path.relative(ROOT, REGISTRY)} (${idx >= 0 ? 'güncellendi' : 'eklendi'})`);
}

main();
