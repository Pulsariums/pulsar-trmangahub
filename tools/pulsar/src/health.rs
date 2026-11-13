use serde::{Deserialize, Serialize};
use std::collections::BTreeMap;
use std::path::Path;
use std::process::{Command, ExitCode};
use std::sync::{Arc, Mutex};

#[derive(Deserialize, Clone, Debug)]
struct SourceEntry {
    id: i64,
    #[serde(default)]
    kind: String,
    #[serde(default)]
    name: String,
    #[serde(default)]
    title: String,
    #[serde(default)]
    lang: String,
    #[serde(default)]
    nsfw: i32,
    #[serde(default)]
    domain: String,
}

#[derive(Deserialize)]
struct SourceMap {
    #[serde(default)]
    engine: Vec<SourceEntry>,
    #[serde(default)]
    catalogue: Vec<SourceEntry>,
}

#[derive(Serialize, Clone, Debug)]
pub struct HealthRow {
    pub id: i64,
    pub kind: String,
    pub title: String,
    pub lang: String,
    pub nsfw: i32,
    pub domain: String,
    pub url: String,
    pub status: String,
    pub http_code: String,
    pub ms: u128,
    pub detail: String,
}

#[derive(Serialize, Debug)]
struct Report {
    generated: String,
    selected: usize,
    ok: usize,
    failed: usize,
    by_reason: BTreeMap<String, usize>,
    sources: Vec<HealthRow>,
}

pub(crate) fn now_iso() -> String {
    let secs = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_secs())
        .unwrap_or(0);
    let days = (secs / 86400) as i64;
    let rem = secs % 86400;
    let (y, m, d) = civil_from_days(days);
    format!(
        "{:04}-{:02}-{:02}T{:02}:{:02}:{:02}Z",
        y, m, d, rem / 3600, (rem % 3600) / 60, rem % 60
    )
}

fn civil_from_days(z: i64) -> (i64, u32, u32) {
    let z = z + 719468;
    let era = if z >= 0 { z } else { z - 146096 } / 146097;
    let doe = (z - era * 146097) as u64;
    let yoe = (doe - doe / 1460 + doe / 36524 - doe / 146096) / 365;
    let y = yoe as i64 + era * 400;
    let doy = doe - (365 * yoe + yoe / 4 - yoe / 100);
    let mp = (5 * doy + 2) / 153;
    let d = (doy - (153 * mp + 2) / 5 + 1) as u32;
    let m = if mp < 10 { mp + 3 } else { mp - 9 } as u32;
    (if m <= 2 { y + 1 } else { y }, m, d)
}

fn test_one(s: &SourceEntry, timeout_secs: u64) -> HealthRow {
    let url = format!("https://{}/", s.domain);
    let null = if cfg!(windows) { "NUL" } else { "/dev/null" };
    let ua = "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Mobile Safari/537.36";
    let started = std::time::Instant::now();
    let output = Command::new("curl")
        .args(["-sS", "-o", null, "-w", "%{http_code}", "-L", "--max-time"])
        .arg(timeout_secs.to_string())
        .args(["-A", ua])
        .arg(&url)
        .output();
    let ms = started.elapsed().as_millis();

    let (status, http_code, detail) = match output {
        Err(e) => ("curl_error".to_string(), String::new(), format!("curl çalıştırılamadı: {e}")),
        Ok(o) => {
            let http = String::from_utf8_lossy(&o.stdout).trim().to_string();
            let err = String::from_utf8_lossy(&o.stderr).trim().to_string();
            let lower = err.to_lowercase();
            if o.status.success() {
                let st = match http.as_str() {
                    "403" => "cloudflare",
                    "404" => "http404",
                    "" => "ok",
                    c if c.starts_with('2') => "ok",
                    c if c.starts_with('5') => "http5xx",
                    _ => "http",
                };
                (st.to_string(), http, err)
            } else {
                let code = o.status.code().unwrap_or(-1);
                let st = match code {
                    6 => "dns",
                    7 => "refused",
                    28 => "timeout",
                    35 | 60 => {
                        if lower.contains("certificate") || lower.contains("issuer") || lower.contains("self signed") {
                            "ssl_trust"
                        } else {
                            "ssl"
                        }
                    }
                    52 => "empty",
                    56 => "reset",
                    _ => "curl_error",
                };
                (st.to_string(), http, err)
            }
        }
    };

    HealthRow {
        id: s.id,
        kind: s.kind.clone(),
        title: if s.title.is_empty() { s.name.clone() } else { s.title.clone() },
        lang: s.lang.clone(),
        nsfw: s.nsfw,
        domain: s.domain.clone(),
        url,
        status,
        http_code,
        ms,
        detail: detail.chars().take(180).collect(),
    }
}

pub fn run(root: &Path, argv: &[String]) -> ExitCode {
    let mut lang: Option<String> = None;
    let mut nsfw: Option<i32> = None;
    let mut limit: Option<usize> = None;
    let mut jobs: usize = 8;
    let mut timeout_secs: u64 = 20;
    let mut i = 0;
    while i < argv.len() {
        match argv[i].as_str() {
            "--lang" => {
                i += 1;
                match argv.get(i) {
                    Some(v) => lang = Some(v.clone()),
                    None => { eprintln!("HATA: --lang için değer gerekli"); return ExitCode::from(64); }
                }
            }
            "--nsfw" => {
                i += 1;
                match argv.get(i).and_then(|v| v.parse::<i32>().ok()) {
                    Some(v) => nsfw = Some(v),
                    None => { eprintln!("HATA: --nsfw 0|1 gerekli"); return ExitCode::from(64); }
                }
            }
            "--limit" => {
                i += 1;
                match argv.get(i).and_then(|v| v.parse::<usize>().ok()) {
                    Some(v) => limit = Some(v),
                    None => { eprintln!("HATA: --limit sayı gerekli"); return ExitCode::from(64); }
                }
            }
            "--jobs" => {
                i += 1;
                match argv.get(i).and_then(|v| v.parse::<usize>().ok()) {
                    Some(v) => jobs = v.clamp(1, 32),
                    None => { eprintln!("HATA: --jobs sayı gerekli"); return ExitCode::from(64); }
                }
            }
            "--timeout" => {
                i += 1;
                match argv.get(i).and_then(|v| v.parse::<u64>().ok()) {
                    Some(v) => timeout_secs = v.clamp(5, 120),
                    None => { eprintln!("HATA: --timeout saniye gerekli"); return ExitCode::from(64); }
                }
            }
            other => { eprintln!("HATA: bilinmeyen argüman: {other}"); return ExitCode::from(64); }
        }
        i += 1;
    }

    let map_path = root.join("pulsar-v2/repo/source_map.json");
    let text = match std::fs::read_to_string(&map_path) {
        Ok(t) => t,
        Err(e) => { eprintln!("HATA: {} okunamadı: {e}", map_path.display()); return ExitCode::FAILURE; }
    };
    let map: SourceMap = match serde_json::from_str(&text) {
        Ok(m) => m,
        Err(e) => { eprintln!("HATA: source_map.json geçersiz: {e}"); return ExitCode::FAILURE; }
    };

    let mut list: Vec<SourceEntry> = map.engine.into_iter().chain(map.catalogue).collect();
    list.retain(|s| !s.domain.trim().is_empty());
    if let Some(l) = &lang {
        list.retain(|s| &s.lang == l);
    }
    if let Some(n) = nsfw {
        list.retain(|s| s.nsfw == n);
    }
    if let Some(l) = limit {
        list.truncate(l);
    }
    if list.is_empty() {
        eprintln!("HATA: seçim boş (filtreleri kontrol et)");
        return ExitCode::FAILURE;
    }

    let selected = list.len();
    println!("TEST: {selected} kaynak, {jobs} paralel, {timeout_secs}s zaman aşımı");
    let queue = Arc::new(Mutex::new(list));
    let collected: Arc<Mutex<Vec<HealthRow>>> = Arc::new(Mutex::new(Vec::new()));
    let mut handles = Vec::new();
    for _ in 0..jobs {
        let q = queue.clone();
        let c = collected.clone();
        handles.push(std::thread::spawn(move || loop {
            let item = { q.lock().unwrap().pop() };
            let Some(s) = item else { break };
            let row = test_one(&s, timeout_secs);
            println!(
                "[{:<10}] {:<28} {}",
                row.status,
                row.title.chars().take(28).collect::<String>(),
                row.domain
            );
            c.lock().unwrap().push(row);
        }));
    }
    for h in handles {
        let _ = h.join();
    }

    let rows = Arc::try_unwrap(collected).ok().map(|m| m.into_inner().unwrap()).unwrap_or_default();
    let mut by_reason: BTreeMap<String, usize> = BTreeMap::new();
    for r in &rows {
        *by_reason.entry(r.status.clone()).or_insert(0) += 1;
    }
    let ok = rows.iter().filter(|r| r.status == "ok").count();
    let report = Report {
        generated: now_iso(),
        selected,
        ok,
        failed: selected - ok,
        by_reason: by_reason.clone(),
        sources: rows.clone(),
    };

    println!("\nÖZET: {} test | ok={} başarısız={}", report.selected, report.ok, report.failed);
    for (k, v) in &by_reason {
        println!("  {k:<12} {v}");
    }

    let out_path = root.join("pulsar-v2/data/health-report.json");
    if let Some(parent) = out_path.parent() {
        let _ = std::fs::create_dir_all(parent);
    }
    match serde_json::to_string_pretty(&report) {
        Ok(t) => {
            if let Err(e) = std::fs::write(&out_path, t + "\n") {
                eprintln!("HATA: rapor yazılamadı: {e}");
                return ExitCode::FAILURE;
            }
            println!("RAPOR: {}", out_path.display());
        }
        Err(e) => {
            eprintln!("HATA: rapor serileştirilemedi: {e}");
            return ExitCode::FAILURE;
        }
    }
    if let Err(e) = crate::status::record_health(root, &report.sources) {
        eprintln!("UYARI: durum dosyası güncellenemedi: {e}");
    } else {
        println!("DURUM: {}", crate::status::STATUS_REL);
    }
    ExitCode::SUCCESS
}
