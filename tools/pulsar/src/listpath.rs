//! `pulsar listpath` — liste adımı düşen katalog kaynağı için doğru liste
//! yolunu arar.
//!
//! `pulsar probe` yalnız kayıtlı `config.listPath` adresini dener; yol
//! yanlışsa kaynak "http404/empty" görünür. Bu komut ana sayfadaki bağlantı
//! kalıplarından ve sabit adaylardan yol üretip her birini ölçer, en çok
//! manga bağlantısı vereni `--write` ile `data/catalogue.json`'a yazar.

use serde_json::Value;
use std::collections::BTreeSet;
use std::path::Path;
use std::process::{Command, ExitCode};
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::{Arc, Mutex};

const DATA_REL: &str = "pulsar-v2/data/catalogue.json";
const OUT_REL: &str = "pulsar-v2/data/listpath-report.csv";
const SEGMENTS: [&str; 9] = [
    "manga", "seri", "series", "serie", "comic", "manhwa", "title", "title-detail", "webtoon",
];
const FIXED: [&str; 14] = [
    "/manga",
    "/manga/",
    "/manga-list",
    "/seri",
    "/seriler",
    "/series",
    "/comic",
    "/comics",
    "/manhwa",
    "/webtoon",
    "/title",
    "/manga-list.html",
    "/manga/page/1",
    "/",
];
static SEQ: AtomicU64 = AtomicU64::new(0);

fn usage(msg: &str) -> ExitCode {
    eprintln!("{msg}");
    eprintln!(
        "kullanım: pulsar listpath [--only d1,d2] [--lang tr] [--nsfw 0|1] [--write] [--timeout sn]"
    );
    ExitCode::from(2)
}

fn fetch(url: &str, timeout: u64) -> Option<String> {
    let tmp = std::env::temp_dir().join(format!(
        "pulsar-listpath-{}-{}.html",
        std::process::id(),
        SEQ.fetch_add(1, Ordering::Relaxed)
    ));
    let ua = "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Mobile Safari/537.36";
    let out = Command::new("curl")
        .args(["-sS", "-L", "--max-time", &timeout.to_string()])
        .args(["-A", ua, "-o"])
        .arg(&tmp)
        .arg(url)
        .output()
        .ok()?;
    let html = std::fs::read_to_string(&tmp).unwrap_or_default();
    let _ = std::fs::remove_file(&tmp);
    if !out.status.success() && html.is_empty() {
        return None;
    }
    Some(html)
}

fn hrefs(html: &str) -> Vec<String> {
    let mut out = Vec::new();
    let mut rest = html;
    while let Some(pos) = rest.find("href=\"") {
        rest = &rest[pos + 6..];
        let Some(end) = rest.find('"') else { break };
        out.push(rest[..end].to_string());
        rest = &rest[end..];
    }
    out
}

fn path_of(href: &str) -> Option<String> {
    let after_scheme = match href.find("://") {
        Some(i) => &href[i + 3..],
        None => href,
    };
    let slash = after_scheme.find('/')?;
    let path = after_scheme[slash..].split(['?', '#']).next().unwrap_or("");
    let path = path.trim_end_matches('/');
    if path.is_empty() {
        None
    } else {
        Some(path.to_string())
    }
}

fn is_asset(last: &str) -> bool {
    let low = last.to_lowercase();
    [
        ".css", ".js", ".mjs", ".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg", ".ico", ".woff",
        ".woff2", ".ttf", ".xml", ".json", ".webmanifest", ".map", ".txt",
    ]
    .iter()
    .any(|e| low.ends_with(e))
}

/// Adayın altındaki tek kademeli bağlantılar ("/manga" -> "/manga/slug").
/// Kök "/" ise iki segmentli her yol sayılır.
fn count_scoped(html: &str, root: &str) -> usize {
    let root = root.trim_end_matches('/');
    let mut seen: BTreeSet<String> = BTreeSet::new();
    for href in hrefs(html) {
        let Some(path) = path_of(&href) else { continue };
        let rest = if root.is_empty() {
            path.as_str()
        } else {
            let Some(r) = path.strip_prefix(root) else { continue };
            if !r.is_empty() && !r.starts_with('/') {
                continue;
            }
            r
        };
        let segs: Vec<&str> = rest.split('/').filter(|s| !s.is_empty()).collect();
        if segs.len() != 1 {
            continue;
        }
        if segs[0].len() < 3 || is_asset(segs[0]) {
            continue;
        }
        seen.insert(path);
    }
    seen.len()
}

/// Sayfadaki en kalabalık yol kökü ("/en/comic/<id>" -> 24, "/t/<slug>" -> 129).
/// Liste sayfasının öğeleri liste yolunun altında olmayabildiği için (dil
/// öneki, farklı öğe kökü) her derinlikteki önek ayrı ayrı sayılır.
fn dominant_root_count(html: &str) -> usize {
    prefix_counts(html).values().copied().max().unwrap_or(0)
}

/// Her öneğin altındaki AYRI bağlantı sayısı (köke göre gruplu).
fn prefix_counts(html: &str) -> std::collections::BTreeMap<String, usize> {
    let mut groups: std::collections::BTreeMap<String, BTreeSet<String>> = Default::default();
    for href in hrefs(html) {
        let Some(path) = path_of(&href) else { continue };
        let segs: Vec<&str> = path.split('/').filter(|s| !s.is_empty()).collect();
        if segs.len() < 2 {
            continue;
        }
        let last = *segs.last().unwrap();
        if last.len() < 3 || is_asset(last) {
            continue;
        }
        for depth in 1..segs.len().min(4) {
            let root = format!("/{}", segs[..depth].join("/"));
            groups.entry(root).or_default().insert(path.clone());
        }
    }
    groups.into_iter().map(|(k, v)| (k, v.len())).collect()
}

/// Kayıtlı sayaçla aynı ölçüt: iki segmentli, ilk segmenti bilinen kalıp.
#[allow(dead_code)]
fn count_links(html: &str) -> usize {
    let mut seen: BTreeSet<String> = BTreeSet::new();
    for href in hrefs(html) {
        let Some(path) = path_of(&href) else { continue };
        let parts: Vec<&str> = path.trim_matches('/').split('/').collect();
        if parts.len() != 2 || parts[1].len() < 3 {
            continue;
        }
        let seg = parts[0].to_lowercase();
        if SEGMENTS.contains(&seg.as_str()) {
            seen.insert(format!("/{}/{}", seg, parts[1]));
        }
    }
    seen.len()
}

/// Ana sayfadaki bağlantılardan liste sayfası adayları.
///
/// İki kaynak: (1) öğe bağlantılarının yol kökleri — sık geçen önce,
/// (2) tek segmentli menü yolları (ör. `/browse`) ve bilinen kalıplar.
fn candidates_from(home: &str) -> Vec<String> {
    // Öğe bağlantılarının yol kökleri: "/t/<slug>" -> "/t",
    // "/Tr/Manga/<slug>" -> "/Tr/Manga". Sık geçen önce.
    let mut ranked: Vec<(String, usize)> = prefix_counts(home).into_iter().collect();
    ranked.sort_by(|a, b| b.1.cmp(&a.1).then(a.0.cmp(&b.0)));

    // Sayfa olarak gezilen ama öğe kökü olmayan bağlantılar (ör. "/browse",
    // "/en/xxx"). Yalnız 1–2 segmentli olanlar; menü gürültüsü 2 ile sınırlı.
    let mut nav: BTreeSet<String> = BTreeSet::new();
    for href in hrefs(home) {
        let Some(path) = path_of(&href) else { continue };
        let parts: Vec<&str> = path.split('/').filter(|s| !s.is_empty()).collect();
        if parts.is_empty() || parts.len() > 2 {
            continue;
        }
        let last = *parts.last().unwrap();
        if last.len() < 2 || is_asset(last) {
            continue;
        }
        nav.insert(format!("/{}", parts.join("/")));
    }

    let mut out: Vec<String> = Vec::new();
    for (p, _) in ranked.into_iter().take(10) {
        if !out.contains(&p) {
            out.push(p);
        }
    }
    for p in nav {
        if out.len() >= 20 {
            break;
        }
        if !out.contains(&p) {
            out.push(p);
        }
    }
    out
}

/// Aday sayfanın öğe listeleme gücü: kendi altındaki bağlantılar, sayfadaki
/// en kalabalık yol kökü ve bilinen kalıp sayacı — en büyüğü.
fn score(html: &str, cand: &str) -> usize {
    count_scoped(html, cand)
        .max(dominant_root_count(html))
        .max(count_links(html))
}

fn base_of(src: &Value) -> String {
    let base = src.get("baseUrl").and_then(|v| v.as_str()).unwrap_or("");
    if base.trim().is_empty() {
        format!(
            "https://{}",
            src.get("domain").and_then(|v| v.as_str()).unwrap_or("")
        )
    } else {
        base.trim().trim_end_matches('/').to_string()
    }
}

fn current_path(src: &Value) -> String {
    src.get("config")
        .and_then(|c| c.get("listPath"))
        .and_then(|v| v.as_str())
        .unwrap_or("/manga")
        .trim()
        .to_string()
}

fn join(base: &str, path: &str) -> String {
    if path == "/" || path.is_empty() {
        format!("{base}/")
    } else if path.starts_with('/') {
        format!("{base}{path}")
    } else {
        format!("{base}/{path}")
    }
}

fn main_one(src: &Value, timeout: u64) -> (String, String, Vec<(String, usize)>) {
    let domain = src.get("domain").and_then(|v| v.as_str()).unwrap_or("").to_string();
    let base = base_of(src);
    let cur = current_path(src);
    let home_url = format!("{base}/");
    let home = fetch(&home_url, timeout).unwrap_or_default();

    let mut cands: Vec<String> = candidates_from(&home);
    if !cands.iter().any(|c| c == &cur) {
        cands.insert(0, cur.clone());
    }
    // Sabit adaylar yalnız ana sayfa ipucu vermediyse denenir: her aday bir
    // HTTP çağrısı, ölü sitelerde 14 çağrı boşa gidiyor.
    let mut scored: Vec<(String, usize)> = Vec::new();
    let mut seen: BTreeSet<String> = BTreeSet::new();
    for phase in 0..2 {
        if phase == 1 && scored.iter().any(|(_, n)| *n >= 3) {
            break;
        }
        let list: Vec<String> = if phase == 0 {
            cands.clone()
        } else {
            FIXED.iter().map(|f| (*f).to_string()).collect()
        };
        for c in list {
            if !seen.insert(c.clone()) {
                continue;
            }
            let url = join(&base, &c);
            let Some(html) = fetch(&url, timeout) else { continue };
            let n = score(&html, &c);
            scored.push((c, n));
            if n >= 40 {
                break;
            }
        }
    }
    // En çok öğe veren önce; eşitlikte kısa yol (öğe sayfası değil liste).
    scored.sort_by(|a, b| b.1.cmp(&a.1).then(a.0.len().cmp(&b.0.len())).then(a.0.cmp(&b.0)));
    (domain, cur, scored)
}

pub fn run(root: &Path, argv: &[String]) -> ExitCode {
    let mut only: Vec<String> = Vec::new();
    let mut lang: Option<String> = None;
    let mut nsfw: Option<i32> = None;
    let mut timeout: u64 = 20;
    let mut write = false;
    let mut all = false;
    let mut sets: Vec<(String, String)> = Vec::new();
    let mut i = 0;
    while i < argv.len() {
        match argv[i].as_str() {
            "--only" => {
                i += 1;
                let Some(v) = argv.get(i) else { return usage("--only değeri yok") };
                only = v.split(',').map(|s| s.trim().to_lowercase()).filter(|s| !s.is_empty()).collect();
            }
            "--lang" => {
                i += 1;
                lang = argv.get(i).map(|s| s.to_lowercase());
            }
            "--nsfw" => {
                i += 1;
                nsfw = argv.get(i).and_then(|s| s.parse().ok());
            }
            "--timeout" => {
                i += 1;
                timeout = argv.get(i).and_then(|s| s.parse().ok()).unwrap_or(20);
            }
            "--write" => write = true,
            "--all" => all = true,
            "--set" => {
                i += 1;
                let Some(v) = argv.get(i) else { return usage("--set değeri yok") };
                for pair in v.split(',') {
                    let pair = pair.trim();
                    let Some((d, p)) = pair.split_once('=') else {
                        return usage(&format!("--set biçimi domain=/yol: {pair}"));
                    };
                    if p.is_empty() || !p.starts_with('/') {
                        return usage(&format!("yol / ile başlamalı: {pair}"));
                    }
                    sets.push((d.trim().to_lowercase(), p.trim().to_string()));
                }
            }
            other => return usage(&format!("bilinmeyen argüman: {other}")),
        }
        i += 1;
    }

    let path = root.join(DATA_REL);
    let text = match std::fs::read_to_string(&path) {
        Ok(t) => t,
        Err(e) => return usage(&format!("{} okunamadı: {e}", path.display())),
    };
    let mut doc: Value = match serde_json::from_str(&text) {
        Ok(v) => v,
        Err(e) => return usage(&format!("catalogue.json geçersiz: {e}")),
    };
    let Some(list) = doc.get_mut("sources").and_then(|v| v.as_array_mut()) else {
        return usage("catalogue.json içinde sources dizisi yok");
    };

    let targets: Vec<Value> = list
        .iter()
        .filter(|s| {
            let d = s.get("domain").and_then(|v| v.as_str()).unwrap_or("").to_lowercase();
            let l = s.get("lang").and_then(|v| v.as_str()).unwrap_or("").to_lowercase();
            let n = s.get("nsfw").and_then(|v| v.as_i64()).unwrap_or(0) as i32;
            (only.is_empty() || only.iter().any(|o| o == &d))
                && lang.as_ref().map(|x| x == &l).unwrap_or(true)
                && nsfw.map(|x| x == n).unwrap_or(true)
        })
        .cloned()
        .collect();

    if targets.is_empty() {
        return usage("seçime uyan kaynak yok");
    }

    let n_targets = targets.len();
    let results: Arc<Mutex<Vec<(String, String, Vec<(String, usize)>)>>> =
        Arc::new(Mutex::new(Vec::new()));
    let queue = Arc::new(Mutex::new(targets.into_iter()));
    let workers = 6.max(1);
    std::thread::scope(|scope| {
        for _ in 0..workers {
            let queue = Arc::clone(&queue);
            let results = Arc::clone(&results);
            scope.spawn(move || loop {
                let next = { queue.lock().map(|mut q| q.next()).ok().flatten() };
                let Some(src) = next else { break };
                let row = main_one(&src, timeout);
                if let Ok(mut r) = results.lock() {
                    r.push(row);
                }
            });
        }
    });

    let mut rows = results.lock().map(|r| r.clone()).unwrap_or_default();
    rows.sort_by(|a, b| {
        let an = a.2.first().map(|x| x.1).unwrap_or(0);
        let bn = b.2.first().map(|x| x.1).unwrap_or(0);
        bn.cmp(&an).then(a.0.cmp(&b.0))
    });

    let mut csv = String::from("domain,mevcut_yol,en_iyi_yol,link\n");
    for (d, cur, scored) in &rows {
        let (best, n) = scored.first().cloned().unwrap_or((cur.clone(), 0));
        csv.push_str(&format!("{d},{cur},{best},{n}\n"));
    }
    let out = root.join(OUT_REL);
    if let Some(p) = out.parent() {
        let _ = std::fs::create_dir_all(p);
    }
    let _ = std::fs::write(&out, csv);

    for (d, cur, scored) in &rows {
        let (best, n) = scored.first().cloned().unwrap_or((cur.clone(), 0));
        println!("{d:<30} {cur:<16} -> {best:<18} {n} link");
        if all {
            for (c, k) in scored.iter().skip(1).take(4) {
                println!("{:<30} {:<16}    {c:<18} {k} link", "", "");
            }
        }
    }

    if write {
        let mut pairs: Vec<(String, String)> = sets.clone();
        if pairs.is_empty() {
            for (d, _cur, scored) in &rows {
                if let Some((best, n)) = scored.first() {
                    if *n >= 3 {
                        pairs.push((d.clone(), best.clone()));
                    }
                }
            }
        }
        let mut changed = 0usize;
        for (d, p) in &pairs {
            for s in list.iter_mut() {
                if s.get("domain").and_then(|v| v.as_str()) != Some(d.as_str()) {
                    continue;
                }
                let Some(obj) = s.as_object_mut() else { continue };
                let cfg = obj
                    .entry("config")
                    .or_insert_with(|| Value::Object(Default::default()));
                if let Some(c) = cfg.as_object_mut() {
                    c.insert("listPath".to_string(), Value::String(p.clone()));
                    changed += 1;
                }
            }
        }
        let pretty = format_doc(&doc);
        if let Err(e) = std::fs::write(&path, pretty) {
            eprintln!("yazılamadı: {e}");
            return ExitCode::FAILURE;
        }
        println!("yazıldı: {changed} kaynak -> {}", path.display());
    }

    println!("rapor: {} ({} kaynak)", out.display(), n_targets);
    ExitCode::SUCCESS
}

/// 1 boşluk girintili çıktı — dosyanın mevcut biçimini korur.
fn format_doc(v: &Value) -> String {
    let mut out = Vec::new();
    let fmt = serde_json::ser::PrettyFormatter::with_indent(b" ");
    let mut ser = serde_json::Serializer::with_formatter(&mut out, fmt);
    serde::Serialize::serialize(v, &mut ser).ok();
    let mut s = String::from_utf8(out).unwrap_or_default();
    s.push('\n');
    s
}
