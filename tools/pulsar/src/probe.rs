//! `pulsar probe` — katalog kaynaklarının LİSTE adımını yerelde dener.
//!
//! `pulsar health` yalnız kök domaine (https://domain/) HTTP kodu soruyordu.
//! Site 200 dönse bile /manga 404 olabiliyor, sayfa açılsa da seçiciler kart
//! bulamıyor. Cihaz raporu 39 kaynağın 39'unda "fail" derken bizim test 39'unda
//! "ok" dedi; sebep buydu. Bu komut eklentinin kullandığı URL'i
//! (baseUrl + config.listPath) çeker ve slug linklerini sayar.

use serde::{Deserialize, Serialize};
use std::collections::{BTreeMap, BTreeSet};
use std::path::Path;
use std::process::{Command, ExitCode};
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::{Arc, Mutex};

use crate::health::now_iso;
use crate::status::{recompute_state, StatusFile, Probe as StatusProbe, STATUS_REL};

const CAT_REL: &str = "pulsar-v2/extension/src/main/assets/catalogue.json";
const OUT_REL: &str = "pulsar-v2/data/probe-report.json";
const SEGMENTS: [&str; 9] = ["manga", "seri", "series", "serie", "comic", "manhwa", "title", "title-detail", "webtoon"];
static SEQ: AtomicU64 = AtomicU64::new(0);

#[derive(Deserialize)]
struct Catalogue {
    #[serde(default)]
    sources: Vec<CatSource>,
}

#[derive(Deserialize)]
struct CatSource {
    #[serde(default)]
    id: serde_json::Value,
    #[serde(default)]
    name: String,
    #[serde(default)]
    domain: String,
    #[serde(rename = "baseUrl", default)]
    base_url: String,
    #[serde(default)]
    lang: String,
    #[serde(default)]
    nsfw: i32,
    #[serde(default)]
    config: serde_json::Value,
}

#[derive(Serialize, Clone, Debug)]
struct Row {
    id: String,
    title: String,
    lang: String,
    nsfw: i32,
    url: String,
    status: String,
    http_code: String,
    links: usize,
    detail: String,
}

#[derive(Serialize)]
struct Report {
    selected: usize,
    ok: usize,
    by_status: BTreeMap<String, usize>,
    sources: Vec<Row>,
}

fn id_of(s: &CatSource) -> String {
    // Eklenti id'yi domain+dil'den üretir (PulsarSource.id): pulsar/{domain}/{lang}.
    // catalogue.json'daki "id" alanı katalog anahtarıdır, kaynak id'si değildir
    // (ör. MangaDex'te eski bir sayı duruyor). Cihaz raporu MIHON_<bu hash> yazar.
    let key = format!("pulsar/{}/{}", s.domain, s.lang);
    let mut h: i64 = 1_125_899_906_842_597;
    for ch in key.chars() {
        h = h.wrapping_mul(31).wrapping_add(ch as i64);
    }
    (h & i64::MAX).to_string()
}

fn listing_url(s: &CatSource) -> String {
    let base = if s.base_url.trim().is_empty() {
        format!("https://{}", s.domain)
    } else {
        s.base_url.trim().trim_end_matches('/').to_string()
    };
    let raw = s
        .config
        .get("listPath")
        .and_then(|v| v.as_str())
        .unwrap_or("/manga")
        .trim();
    if raw.is_empty() {
        format!("{base}/")
    } else if raw.starts_with('/') {
        format!("{base}{raw}")
    } else {
        format!("{base}/{raw}")
    }
}

fn count_slug_links(html: &str) -> usize {
    let mut seen: BTreeSet<String> = BTreeSet::new();
    let mut rest = html;
    while let Some(pos) = rest.find("href=\"") {
        rest = &rest[pos + 6..];
        let Some(end) = rest.find('"') else { break };
        let href = &rest[..end];
        rest = &rest[end..];
        let after_scheme = match href.find("://") {
            Some(i) => &href[i + 3..],
            None => href,
        };
        let path = match after_scheme.find('/') {
            Some(j) => &after_scheme[j..],
            None => continue,
        };
        let path = path.split(['?', '#']).next().unwrap_or("");
        let parts: Vec<&str> = path.trim_matches('/').split('/').collect();
        if parts.len() != 2 {
            continue;
        }
        let seg = parts[0].to_lowercase();
        if !SEGMENTS.contains(&seg.as_str()) {
            continue;
        }
        if parts[1].len() < 3 {
            continue;
        }
        seen.insert(format!("/{seg}/{}", parts[1]));
    }
    seen.len()
}

fn probe_one(s: &CatSource, timeout: u64) -> Row {
    let url = listing_url(s);
    let tmp = std::env::temp_dir().join(format!(
        "pulsar-probe-{}-{}.html",
        std::process::id(),
        SEQ.fetch_add(1, Ordering::Relaxed)
    ));
    let ua = "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Mobile Safari/537.36";
    let out = Command::new("curl")
        .args(["-sS", "-L", "--max-time"])
        .arg(timeout.to_string())
        .args(["-A", ua, "-o"])
        .arg(&tmp)
        .args(["-w", "%{http_code}"])
        .arg(&url)
        .output();
    let (code, detail) = match out {
        Err(e) => (String::new(), format!("curl çalıştırılamadı: {e}")),
        Ok(o) => (
            String::from_utf8_lossy(&o.stdout).trim().to_string(),
            String::from_utf8_lossy(&o.stderr)
                .trim()
                .chars()
                .take(160)
                .collect::<String>(),
        ),
    };
    let html = std::fs::read_to_string(&tmp).unwrap_or_default();
    let _ = std::fs::remove_file(&tmp);
    let links = count_slug_links(&html);
    let status = if code == "404" {
        "http404"
    } else if code == "403" || code == "429" || code == "436" {
        "blocked"
    } else if !code.starts_with('2') {
        "http"
    } else if links == 0 {
        "empty"
    } else {
        "ok"
    };
    Row {
        id: id_of(s),
        title: s.name.clone(),
        lang: s.lang.clone(),
        nsfw: s.nsfw,
        url,
        status: status.to_string(),
        http_code: code,
        links,
        detail: if status == "ok" { String::new() } else { detail },
    }
}

fn compare(rows: &[Row], device_path: &str) {
    let text = match std::fs::read_to_string(device_path) {
        Ok(t) => t,
        Err(e) => {
            eprintln!("HATA: {device_path} okunamadı: {e}");
            return;
        }
    };
    let dev: serde_json::Value = match serde_json::from_str(&text) {
        Ok(v) => v,
        Err(e) => {
            eprintln!("HATA: cihaz raporu geçersiz: {e}");
            return;
        }
    };
    let by_id: BTreeMap<String, &Row> = rows.iter().map(|r| (r.id.clone(), r)).collect();
    let total = dev.get("total").and_then(|v| v.as_u64()).unwrap_or(0);
    let mut agree = 0usize;
    let mut disagree = 0usize;
    let mut missing = 0usize;
    let mut lines: Vec<String> = Vec::new();
    if let Some(list) = dev.get("sources").and_then(|v| v.as_array()) {
        for e in list {
            let name = e.get("name").and_then(|v| v.as_str()).unwrap_or("");
            let id = name.strip_prefix("MIHON_").unwrap_or(name);
            let step = e
                .get("steps")
                .and_then(|s| s.get("list"))
                .and_then(|l| l.get("status"))
                .and_then(|v| v.as_str())
                .unwrap_or("");
            let Some(row) = by_id.get(id) else {
                missing += 1;
                continue;
            };
            let ours_ok = row.status == "ok";
            if step == "fail" && !ours_ok {
                agree += 1;
            } else if step == "fail" && ours_ok {
                disagree += 1;
                lines.push(format!(
                    "  AYRIŞIYOR  {:<28} cihaz=list-fail  biz={} links={}",
                    row.title, row.status, row.links
                ));
            }
        }
    }
    println!(
        "KARŞILAŞTIRMA cihaz list-hataları: uyuşan {agree}, ayrışan {disagree}, eşleşmeyen {missing} (cihaz toplam {total})"
    );
    for l in lines.iter().take(40) {
        println!("{l}");
    }
}

fn write_status_file(root: &Path, rows: &[Row], clear_device: bool) -> Result<(usize, usize), String> {
    let path = root.join(STATUS_REL);
    let text = std::fs::read_to_string(&path).map_err(|e| format!("{}: {e}", path.display()))?;
    let mut file: StatusFile =
        serde_json::from_str(&text).map_err(|e| format!("geçersiz durum dosyası: {e}"))?;
    let now = now_iso();
    let mut updated = 0usize;
    let mut missing = 0usize;
    for r in rows {
        let Ok(id) = r.id.parse::<i64>() else {
            missing += 1;
            continue;
        };
        let Some(entry) = file.sources.get_mut(&id.to_string()) else {
            missing += 1;
            continue;
        };
        entry.health = Some(StatusProbe {
            status: r.status.clone(),
            http_code: r.http_code.clone(),
            ms: 0,
            detail: format!("liste: {} link", r.links),
            at: now.clone(),
        });
        if clear_device {
            entry.device = None;
            entry.device_step = None;
        }
        recompute_state(entry);
        updated += 1;
    }
    file.generated = now;
    let out = serde_json::to_string_pretty(&file).map_err(|e| e.to_string())?;
    std::fs::write(&path, out + "\n").map_err(|e| e.to_string())?;
    Ok((updated, missing))
}

fn usage(msg: &str) -> ExitCode {
    eprintln!("HATA: {msg}");
    eprintln!("kullanım: pulsar probe [--lang tr] [--nsfw 0|1] [--compare <cihaz.json>] [--write-status] [--clear-device] [--timeout sn] [--jobs n]");
    ExitCode::from(64)
}

pub fn run(root: &Path, argv: &[String]) -> ExitCode {
    let mut lang: Option<String> = None;
    let mut nsfw: Option<i32> = None;
    let mut compare_path: Option<String> = None;
    let mut timeout: u64 = 25;
    let mut jobs: usize = 6;
    let mut write_status = false;
    let mut clear_device = false;
    let mut i = 0;
    while i < argv.len() {
        match argv[i].as_str() {
            "--lang" => {
                i += 1;
                match argv.get(i) {
                    Some(v) => lang = Some(v.clone()),
                    None => return usage("--lang için değer gerekli"),
                }
            }
            "--nsfw" => {
                i += 1;
                match argv.get(i).and_then(|v| v.parse::<i32>().ok()) {
                    Some(v) => nsfw = Some(v),
                    None => return usage("--nsfw 0|1 gerekli"),
                }
            }
            "--compare" => {
                i += 1;
                match argv.get(i) {
                    Some(v) => compare_path = Some(v.clone()),
                    None => return usage("--compare için dosya yolu gerekli"),
                }
            }
            "--timeout" => {
                i += 1;
                match argv.get(i).and_then(|v| v.parse::<u64>().ok()) {
                    Some(v) => timeout = v.clamp(5, 120),
                    None => return usage("--timeout saniye gerekli"),
                }
            }
            "--jobs" => {
                i += 1;
                match argv.get(i).and_then(|v| v.parse::<usize>().ok()) {
                    Some(v) => jobs = v.clamp(1, 32),
                    None => return usage("--jobs sayı gerekli"),
                }
            }
            "--write-status" => write_status = true,
            "--clear-device" => clear_device = true,
            other => return usage(&format!("bilinmeyen argüman: {other}")),
        }
        i += 1;
    }

    let cat_path = root.join(CAT_REL);
    let text = match std::fs::read_to_string(&cat_path) {
        Ok(t) => t,
        Err(e) => {
            eprintln!("HATA: {} okunamadı: {e}", cat_path.display());
            return ExitCode::FAILURE;
        }
    };
    let cat: Catalogue = match serde_json::from_str(&text) {
        Ok(c) => c,
        Err(e) => {
            eprintln!("HATA: catalogue.json geçersiz: {e}");
            return ExitCode::FAILURE;
        }
    };
    let mut list: Vec<CatSource> = cat
        .sources
        .into_iter()
        .filter(|s| !s.domain.trim().is_empty())
        .collect();
    if let Some(l) = &lang {
        list.retain(|s| &s.lang == l);
    }
    if let Some(n) = nsfw {
        list.retain(|s| s.nsfw == n);
    }
    if list.is_empty() {
        eprintln!("HATA: seçim boş (filtreleri kontrol et)");
        return ExitCode::FAILURE;
    }

    let selected = list.len();
    println!("PROBE: {selected} katalog kaynağı, {jobs} paralel, {timeout}s zaman aşımı");
    let queue = Arc::new(Mutex::new(list));
    let collected: Arc<Mutex<Vec<Row>>> = Arc::new(Mutex::new(Vec::new()));
    let mut handles = Vec::new();
    for _ in 0..jobs {
        let q = queue.clone();
        let c = collected.clone();
        handles.push(std::thread::spawn(move || loop {
            let item = { q.lock().unwrap().pop() };
            let Some(s) = item else { break };
            let row = probe_one(&s, timeout);
            println!(
                "[{:<8}] {:<28} links={:<3} {}",
                row.status,
                row.title.chars().take(28).collect::<String>(),
                row.links,
                row.url
            );
            c.lock().unwrap().push(row);
        }));
    }
    for h in handles {
        let _ = h.join();
    }

    let rows = Arc::try_unwrap(collected)
        .ok()
        .map(|m| m.into_inner().unwrap())
        .unwrap_or_default();
    let mut by_status: BTreeMap<String, usize> = BTreeMap::new();
    for r in &rows {
        *by_status.entry(r.status.clone()).or_insert(0) += 1;
    }
    let ok = rows.iter().filter(|r| r.status == "ok").count();
    let report = Report {
        selected,
        ok,
        by_status: by_status.clone(),
        sources: rows.clone(),
    };
    let out_path = root.join(OUT_REL);
    if let Some(parent) = out_path.parent() {
        let _ = std::fs::create_dir_all(parent);
    }
    match serde_json::to_string_pretty(&report) {
        Ok(json) => {
            if let Err(e) = std::fs::write(&out_path, json) {
                eprintln!("HATA: {} yazılamadı: {e}", out_path.display());
            } else {
                println!("rapor: {}", out_path.display());
            }
        }
        Err(e) => eprintln!("HATA: rapor serileştirilemedi: {e}"),
    }
    println!("SONUÇ: {ok}/{selected} liste adımı geçti");
    for (k, v) in &by_status {
        println!("  {k:<8} {v}");
    }
    if write_status {
        match write_status_file(root, &rows, clear_device) {
            Ok((updated, missing)) => {
                println!("DURUM: {updated} kayıt güncellendi, {missing} eşleşmedi (clear_device={clear_device})")
            }
            Err(e) => eprintln!("HATA: durum dosyası yazılamadı: {e}"),
        }
    }
    if let Some(p) = &compare_path {
        compare(&rows, p);
    }
    ExitCode::SUCCESS
}
