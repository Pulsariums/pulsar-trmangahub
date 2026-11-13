//! `pulsar sweep` — Kototoro `source-host serve` sürecini sürer, katalogdaki
//! eklenti kaynaklarını adım adım gezer ve CSV basar.
//!
//! Adımlar: `sources` → her kaynak için `list` → `details` → ilk `chapter` →
//! `pages`. Süreçle JSONL konuşulur; her isteğe artan `requestId` verilir ve
//! yanıt `requestId` ile eşleştirilir.
//!
//! Harness arızası: `source-host` köprüsü (suwayomi sınıfları) yüzünden düşen
//! çağrılar `harness` diye işaretlenir. Ölçüt, çağrının stderr bloğundaki
//! `Caused by:` satırında `NoClassDefFoundError` / `CloudflareInterceptor` /
//! `suwayomi` geçmesidir; her yığın izinde görülen sıradan `suwayomi` çerçeveleri
//! bu yüzden sayılmaz.
//!
//! Kullanım:
//!   pulsar sweep --jar <yol> --java <yol> --app <dizin> --catalogue <yol>
//!     [--out <csv>] [--site <domain>]... [--limit <n>] [--timeout <sn>]
//!     [--package <ad>] [--version-code <n>]

use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::collections::{HashSet, VecDeque};
use std::io::{BufRead, BufReader, Write};
use std::path::{Path, PathBuf};
use std::process::{Child, ChildStdin, Command, ExitCode, Stdio};
use std::sync::mpsc::{self, Receiver, RecvTimeoutError};
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};

const PLATFORM_CLASS: &str = "org.skepsun.kototoro.desktop.compat.MihonDesktopPlatform";
const HOST_MAIN: &str = "org.skepsun.kototoro.source.host.SourceHostCliKt";
const DEFAULT_PACKAGE: &str = "eu.kanade.tachiyomi.extension.all.pulsar.tr";
const DEFAULT_VERSION_CODE: i64 = 35;

pub fn run(root: &Path, argv: &[String]) -> ExitCode {
    match sweep(root, argv) {
        Ok(()) => ExitCode::SUCCESS,
        Err(e) => {
            eprintln!("HATA: {e}");
            ExitCode::FAILURE
        }
    }
}

fn arg_value(argv: &[String], name: &str) -> Option<String> {
    argv.iter()
        .position(|a| a == name)
        .and_then(|i| argv.get(i + 1))
        .cloned()
}

fn resolve(root: &Path, p: &str) -> PathBuf {
    let path = PathBuf::from(p);
    if path.is_absolute() {
        path
    } else if root.join(&path).exists() {
        root.join(path)
    } else {
        std::env::current_dir()
            .map(|d| d.join(&path))
            .unwrap_or(path)
    }
}

/// Kotlin kuralı: `h = 1125899906842597; h = h*31 + ch; h & 0x7FFF_FFFF_FFFF_FFFF`
fn source_hash(text: &str) -> i64 {
    let mut h: i64 = 1_125_899_906_842_597;
    for ch in text.chars() {
        h = h.wrapping_mul(31).wrapping_add(ch as i64);
    }
    h & 0x7FFF_FFFF_FFFF_FFFF
}

#[derive(Clone, Copy, PartialEq)]
enum FailKind {
    Timeout,
    Response,
    Fatal,
}

struct Fail {
    kind: FailKind,
    msg: String,
    harness: bool,
}

struct Host {
    child: Child,
    stdin: ChildStdin,
    rx: Receiver<String>,
    err_buf: Arc<Mutex<VecDeque<String>>>,
    timeout: Duration,
}

impl Host {
    fn start(
        java: &str,
        app: &Path,
        config: &Path,
        timeout: Duration,
    ) -> Result<Host, String> {
        // Windows'ta JVM sınıf yolu joker karakterini kendisi açar.
        let classpath = app.join("*");
        let mut child = Command::new(java)
            // source-host, arıza yığınlarını yalnız bu özellik verilince
            // stderr'e basar (`reportFailure`); harness imzası bunsuz görünmez.
            .arg("-Dkototoro.source.diagnostics=stderr")
            .arg("-cp")
            .arg(&classpath)
            .arg(HOST_MAIN)
            .arg("serve")
            .arg(config)
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::piped())
            .spawn()
            .map_err(|e| format!("java başlatılamadı: {e}"))?;

        let stdin = child.stdin.take().ok_or("süreç stdin'i alınamadı")?;
        let stdout = child.stdout.take().ok_or("süreç stdout'u alınamadı")?;
        let stderr = child.stderr.take().ok_or("süreç stderr'i alınamadı")?;

        let (tx, rx) = mpsc::channel::<String>();
        std::thread::spawn(move || {
            let reader = BufReader::new(stdout);
            for line in reader.lines() {
                match line {
                    Ok(l) if !l.trim().is_empty() => {
                        if tx.send(l).is_err() {
                            break;
                        }
                    }
                    Ok(_) => {}
                    Err(_) => break,
                }
            }
        });

        let err_buf: Arc<Mutex<VecDeque<String>>> = Arc::new(Mutex::new(VecDeque::new()));
        let eb = err_buf.clone();
        std::thread::spawn(move || {
            let reader = BufReader::new(stderr);
            for line in reader.lines() {
                match line {
                    Ok(l) => {
                        // Tanı için geniş tutulur; ekrana basılırken son 40
                        // satır kullanılır. Uzun yığın izlerinde `Caused by:`
                        // satırı 40. satırdan sonra gelebilir.
                        let mut b = eb.lock().unwrap();
                        b.push_back(l);
                        while b.len() > 4096 {
                            b.pop_front();
                        }
                    }
                    Err(_) => break,
                }
            }
        });

        Ok(Host {
            child,
            stdin,
            rx,
            err_buf,
            timeout,
        })
    }

    fn tail(&self) -> String {
        let buf = self.err_buf.lock().unwrap();
        let start = buf.len().saturating_sub(40);
        buf.iter().skip(start).cloned().collect::<Vec<_>>().join("\n")
    }

/// Çağrının `SOURCE_FAILURE <rid> ...` bloğundaki `Caused by:` satırlarında
/// harness imzası ara. Sıradan `suwayomi` çerçeveleri (her yığın izinde var)
/// sayılmaz; yalnız kök sebep satırı sayılır.
fn stderr_has_harness(lines: &[String], rid: &str) -> bool {
    let start = lines
        .iter()
        .position(|l| l.starts_with("SOURCE_FAILURE ") && l.contains(rid));
    let block: Vec<&String> = match start {
        Some(i) => lines
            .iter()
            .skip(i + 1)
            .take_while(|l| !l.starts_with("SOURCE_FAILURE "))
            .collect(),
        None => lines.iter().collect(),
    };
    block.iter().any(|l| {
        let t = l.trim();
        t.contains("NoClassDefFoundError")
            || t.contains("CloudflareInterceptor")
            || (t.starts_with("Caused by:") && t.contains("suwayomi"))
    })
}

    /// Bir çağrının stderr bloğunda harness imzası var mı?
    fn is_harness(&self, rid: &str) -> bool {
        let buf = self.err_buf.lock().unwrap();
        let lines: Vec<String> = buf.iter().cloned().collect();
        Self::stderr_has_harness(&lines, rid)
    }

    fn err_log(&self) -> Vec<String> {
        self.err_buf.lock().unwrap().iter().cloned().collect()
    }

    fn request(&mut self, rid: &str, call: Value) -> Result<Value, Fail> {
        // Not: stderr arabelleği burada TEMİZLENMEZ. Yığın izleri yanıttan
        // sonra akabilir; çağrı eşleştirmesi `SOURCE_FAILURE <requestId>`
        // satırıyla yapılır, temizlik eski izleri kaybettirir.
        let line = json!({"version": 1, "requestId": rid, "call": call}).to_string();
        if let Err(e) = writeln!(self.stdin, "{line}").and_then(|_| self.stdin.flush()) {
            return Err(Fail {
                kind: FailKind::Fatal,
                msg: format!("stdin yazılamadı: {e}"),
                harness: false,
            });
        }

        let deadline = Instant::now() + self.timeout;
        loop {
            let left = deadline.saturating_duration_since(Instant::now());
            if left.is_zero() {
                return Err(Fail {
                    kind: FailKind::Timeout,
                    msg: format!("{} sn içinde yanıt yok", self.timeout.as_secs()),
                    harness: false,
                });
            }
            match self.rx.recv_timeout(left) {
                Ok(text) => {
                    let Ok(v) = serde_json::from_str::<Value>(&text) else {
                        continue;
                    };
                    if v.get("requestId").and_then(|x| x.as_str()) != Some(rid) {
                        continue;
                    }
                    if let Some(err) = v.get("error").filter(|e| !e.is_null()) {
                        std::thread::sleep(Duration::from_millis(300));
                        let harness = self.is_harness(rid);
                        let msg = err
                            .get("message")
                            .and_then(|m| m.as_str())
                            .unwrap_or("bilinmeyen hata")
                            .to_string();
                        let code = err.get("code").and_then(|c| c.as_str()).unwrap_or("");
                        let msg = if code.is_empty() || code == "RUNTIME_FAILURE" {
                            msg
                        } else {
                            format!("{code}: {msg}")
                        };
                        return Err(Fail {
                            kind: FailKind::Response,
                            msg,
                            harness,
                        });
                    }
                    return Ok(v);
                }
                Err(RecvTimeoutError::Timeout) => {
                    return Err(Fail {
                        kind: FailKind::Timeout,
                        msg: format!("{} sn içinde yanıt yok", self.timeout.as_secs()),
                        harness: false,
                    });
                }
                Err(RecvTimeoutError::Disconnected) => {
                    let tail = self.tail();
                    return Err(Fail {
                        kind: FailKind::Fatal,
                        msg: format!("source-host kapandı\n--- stderr (son 40) ---\n{tail}"),
                        harness: false,
                    });
                }
            }
        }
    }
}

impl Drop for Host {
    fn drop(&mut self) {
        let _ = self.child.kill();
        let _ = self.child.wait();
    }
}

struct Target {
    id: String,
    name: String,
    site: String,
}

struct Row {
    id: String,
    site: String,
    list: String,
    details: String,
    chapters: String,
    pages: String,
    stage: String,
    msg: String,
    fail_rid: String,
    eser: String,
}

fn csv_escape(s: &str) -> String {
    let s = s.replace('\r', " ").replace('\n', " ");
    if s.contains(',') || s.contains('"') {
        format!("\"{}\"", s.replace('"', "\"\""))
    } else {
        s
    }
}

fn sweep(root: &Path, argv: &[String]) -> Result<(), String> {
    let jar = arg_value(argv, "--jar").ok_or("--jar gerekli")?;
    let java = arg_value(argv, "--java").ok_or("--java gerekli")?;
    let app = arg_value(argv, "--app").ok_or("--app gerekli")?;
    let catalogue = arg_value(argv, "--catalogue").ok_or("--catalogue gerekli")?;
    let out = arg_value(argv, "--out").unwrap_or_else(|| "sweep.csv".to_string());
    let package = arg_value(argv, "--package").unwrap_or_else(|| DEFAULT_PACKAGE.to_string());
    let version_code = match arg_value(argv, "--version-code") {
        Some(v) => v
            .parse::<i64>()
            .map_err(|e| format!("--version-code geçersiz: {e}"))?,
        None => DEFAULT_VERSION_CODE,
    };
    let timeout_secs = match arg_value(argv, "--timeout") {
        Some(v) => v
            .parse::<u64>()
            .map_err(|e| format!("--timeout geçersiz: {e}"))?,
        None => 60,
    };
    let limit = match arg_value(argv, "--limit") {
        Some(v) => Some(
            v.parse::<usize>()
                .map_err(|e| format!("--limit geçersiz: {e}"))?,
        ),
        None => None,
    };
    let sites: Vec<String> = argv
        .iter()
        .enumerate()
        .filter(|(_, a)| a.as_str() == "--site")
        .filter_map(|(i, _)| argv.get(i + 1).cloned())
        .map(|s| s.trim().to_lowercase())
        .collect();

    let jar_path = resolve(root, &jar);
    let app_path = resolve(root, &app);
    let catalogue_path = resolve(root, &catalogue);
    let out_path = resolve(root, &out);

    let jar_bytes = std::fs::read(&jar_path)
        .map_err(|e| format!("{} okunamadı: {e}", jar_path.display()))?;
    let sha256 = format!("{:x}", Sha256::digest(&jar_bytes));

    // Geçici çalışma dizini: config ve boş çalışma klasörleri.
    let tmp = std::env::temp_dir().join(format!("pulsar-sweep-{}", std::process::id()));
    if tmp.exists() {
        let _ = std::fs::remove_dir_all(&tmp);
    }
    for sub in ["imageDirectory", "preferenceDirectory", "catalogDirectory"] {
        std::fs::create_dir_all(tmp.join(sub))
            .map_err(|e| format!("{} oluşturulamadı: {e}", tmp.join(sub).display()))?;
    }
    let config_path = tmp.join("config.json");
    let config = json!({
        "platformClass": PLATFORM_CLASS,
        "jars": [{
            "path": jar_path.to_string_lossy(),
            "identity": {
                "packageName": package,
                "versionCode": version_code,
                "sha256": sha256,
            }
        }],
        "imageDirectory": "imageDirectory",
        "preferenceDirectory": "preferenceDirectory",
        "catalogDirectory": "catalogDirectory",
    });
    std::fs::write(
        &config_path,
        serde_json::to_string_pretty(&config).map_err(|e| format!("config serileştirme: {e}"))? + "\n",
    )
    .map_err(|e| format!("{} yazılamadı: {e}", config_path.display()))?;

    let mut host = Host::start(
        &java,
        &app_path,
        &config_path,
        Duration::from_secs(timeout_secs.max(1)),
    )?;

    // 1) `sources` — harness'ın gerçekten oluşturduğu kaynaklar.
    let sources_resp = match host.request("sweep-sources", json!({"operation": "sources"})) {
        Ok(v) => v,
        Err(f) => {
            return Err(format!(
                "sources çağrısı başarısız: {}\n--- stderr (son 40) ---\n{}",
                f.msg,
                host.tail()
            ));
        }
    };
    let available: HashSet<String> = sources_resp
        .pointer("/result/sources")
        .and_then(|v| v.as_array())
        .into_iter()
        .flatten()
        .filter_map(|s| s.get("name").and_then(|v| v.as_str()).map(String::from))
        .collect();
    if available.is_empty() {
        return Err("sources yanıtı boş".to_string());
    }

    // 2) Katalog: üst düzey nesne + `sources` dizisi.
    let cat_text = std::fs::read_to_string(&catalogue_path)
        .map_err(|e| format!("{} okunamadı: {e}", catalogue_path.display()))?;
    let cat_doc: Value = serde_json::from_str(&cat_text)
        .map_err(|e| format!("{} geçersiz JSON: {e}", catalogue_path.display()))?;
    let cat_sources = cat_doc
        .get("sources")
        .and_then(|v| v.as_array())
        .ok_or("catalogue.json içinde 'sources' dizisi yok")?;

    let mut seen: HashSet<String> = HashSet::new();
    let mut targets: Vec<Target> = Vec::new();
    for s in cat_sources {
        let domain = s
            .get("domain")
            .and_then(|v| v.as_str())
            .or_else(|| s.get("id").and_then(|v| v.as_str()))
            .unwrap_or("");
        if domain.is_empty() {
            continue;
        }
        let site = domain.to_lowercase();
        if !sites.is_empty()
            && !sites
                .iter()
                .any(|x| x == &site || x == &format!("www.{site}"))
        {
            continue;
        }
        let lang = s.get("lang").and_then(|v| v.as_str()).unwrap_or("tr");
        let hash = source_hash(&format!("pulsar/{domain}/{lang}"));
        let name = format!("MIHON_{hash}");
        if !available.contains(&name) {
            continue;
        }
        if !seen.insert(name.clone()) {
            continue;
        }
        targets.push(Target {
            id: hash.to_string(),
            name,
            site: domain.to_string(),
        });
        if let Some(n) = limit {
            if targets.len() >= n {
                break;
            }
        }
    }
    if targets.is_empty() {
        return Err("eşleşen kaynak yok (catalogue ve sources kesişmiyor)".to_string());
    }

    // 3) Her kaynak: list → details → chapters → pages.
    let mut rows: Vec<Row> = Vec::with_capacity(targets.len());
    'targets: for t in &targets {
        let mut row = Row {
            id: t.id.clone(),
            site: t.site.clone(),
            list: String::new(),
            details: String::new(),
            chapters: String::new(),
            pages: String::new(),
            stage: String::new(),
            msg: String::new(),
            fail_rid: String::new(),
            eser: String::new(),
        };

        let list_rid = format!("s{}-list", t.id);
        let list_resp = match host.request(
            &list_rid,
            json!({"operation": "list", "sourceName": t.name, "offset": 0}),
        ) {
            Ok(v) => v,
            Err(f) => {
                if f.kind == FailKind::Fatal {
                    return Err(f.msg);
                }
                row.fail_rid = list_rid.clone();
                row.stage = if f.kind == FailKind::Timeout {
                    "zaman_asimi".to_string()
                } else if f.harness {
                    "harness".to_string()
                } else {
                    "list".to_string()
                };
                row.msg = f.msg;
                rows.push(row);
                continue;
            }
        };
        let content = list_resp
            .pointer("/result/content")
            .and_then(|v| v.as_array())
            .cloned()
            .unwrap_or_default();
        row.list = content.len().to_string();
        if content.is_empty() {
            row.stage = "list".to_string();
            row.msg = "liste boş".to_string();
            rows.push(row);
            continue;
        }

        // Bölümü olan eseri bul: ilk eser 0 bölüm dönerse listedeki sonraki
        // eserleri dene (en fazla 3). Diğer hata türleri (RUNTIME_FAILURE,
        // zaman aşımı) eski davranışla aynı: o kaynak o adımda biter.
        const MAX_ESER: usize = 3;
        let attempts = content.len().min(MAX_ESER);
        let mut detail_ok: Option<Value> = None;
        let mut attempted = 0usize;
        for (i, item) in content.iter().take(MAX_ESER).enumerate() {
            attempted = i + 1;
            if let Some(t) = item.get("title").and_then(|v| v.as_str()) {
                if !t.is_empty() {
                    row.eser = t.chars().take(60).collect();
                }
            }
            let details_rid = if i == 0 {
                format!("s{}-details", t.id)
            } else {
                format!("s{}-details{}", t.id, i)
            };
            let details_resp = match host.request(
                &details_rid,
                json!({"operation": "details", "content": item}),
            ) {
                Ok(v) => v,
                Err(f) => {
                    if f.kind == FailKind::Fatal {
                        return Err(f.msg);
                    }
                    // Harness arızası: eski davranış, sonraki esere geçme.
                    let harness = f.harness
                        || f.msg.contains("suwayomi")
                        || f.msg.contains("NoClassDefFoundError")
                        || f.msg.contains("CloudflareInterceptor");
                    if harness {
                        row.details = "hata".to_string();
                        row.fail_rid = details_rid.clone();
                        row.stage = "harness".to_string();
                        row.msg = f.msg;
                        rows.push(row);
                        continue 'targets;
                    }
                    // Diğer hatalar (RUNTIME_FAILURE, zaman aşımı): sonraki
                    // eseri dene; son denemede kaydı yaz.
                    if i + 1 >= attempts {
                        row.details = "hata".to_string();
                        row.fail_rid = details_rid.clone();
                        row.stage = "details".to_string();
                        row.msg = f.msg;
                        rows.push(row);
                        continue 'targets;
                    }
                    continue;
                }
            };
            let detail = details_resp.pointer("/result/content");
            let title = detail
                .and_then(|c| c.get("title"))
                .and_then(|v| v.as_str())
                .unwrap_or("");
            row.details = if title.is_empty() {
                "(başlıksız)".to_string()
            } else {
                title.chars().take(60).collect()
            };
            row.eser = title.chars().take(60).collect();
            let has_chapters = detail
                .and_then(|c| c.get("chapters"))
                .and_then(|v| v.as_array())
                .map(|a| !a.is_empty())
                .unwrap_or(false);
            if has_chapters {
                detail_ok = detail.cloned();
                break;
            }
        }

        let Some(detail) = detail_ok else {
            row.stage = "chapters".to_string();
            row.msg = if attempted >= MAX_ESER {
                "3 eserde de bölüm yok".to_string()
            } else if attempted <= 1 {
                "bölüm yok".to_string()
            } else {
                format!("{attempted} eserde de bölüm yok")
            };
            rows.push(row);
            continue;
        };

        let chapters = detail
            .get("chapters")
            .and_then(|v| v.as_array())
            .cloned()
            .unwrap_or_default();
        row.chapters = chapters.len().to_string();
        let first_chapter = chapters[0].clone();

        let pages_rid = format!("s{}-pages", t.id);
        match host.request(
            &pages_rid,
            json!({"operation": "pages", "chapter": first_chapter}),
        ) {
            Ok(v) => {
                let n = v
                    .pointer("/result/pages")
                    .and_then(|p| p.as_array())
                    .map(|a| a.len())
                    .unwrap_or(0);
                row.pages = n.to_string();
            }
            Err(f) => {
                if f.kind == FailKind::Fatal {
                    return Err(f.msg);
                }
                row.fail_rid = pages_rid.clone();
                row.pages = if f.harness {
                    "hata(harness)".to_string()
                } else {
                    "hata".to_string()
                };
                row.stage = if f.kind == FailKind::Timeout {
                    "zaman_asimi".to_string()
                } else if f.harness {
                    "harness".to_string()
                } else {
                    "pages".to_string()
                };
                row.msg = f.msg;
            }
        }
        rows.push(row);
    }

    // 3b) stderr yığınları yanıtlardan sonra akabilir; koşu bitince harness
    // sınıflandırmasını tüm log üzerinden tazele.
    std::thread::sleep(Duration::from_millis(800));
    let err_log = host.err_log();
    for r in rows.iter_mut() {
        if r.fail_rid.is_empty() || r.stage == "zaman_asimi" {
            continue;
        }
        if Host::stderr_has_harness(&err_log, &r.fail_rid) {
            if r.stage == "pages" {
                r.pages = "hata(harness)".to_string();
            }
            r.stage = "harness".to_string();
        }
    }

    // 4) CSV.
    let mut csv = String::from("id,site,list,details,chapters,pages,asama_hata,mesaj,eser\n");
    for r in &rows {
        csv.push_str(&format!(
            "{},{},{},{},{},{},{},{},{}\n",
            r.id,
            csv_escape(&r.site),
            r.list,
            csv_escape(&r.details),
            r.chapters,
            r.pages,
            r.stage,
            csv_escape(&r.msg),
            csv_escape(&r.eser)
        ));
    }
    if let Some(parent) = out_path.parent() {
        if !parent.as_os_str().is_empty() {
            std::fs::create_dir_all(parent)
                .map_err(|e| format!("{} oluşturulamadı: {e}", parent.display()))?;
        }
    }
    std::fs::write(&out_path, csv)
        .map_err(|e| format!("{} yazılamadı: {e}", out_path.display()))?;

    // 5) Özet.
    let broken: Vec<&Row> = rows.iter().filter(|r| !r.stage.is_empty()).collect();
    println!(
        "[sweep] {} kaynak: {} sağlam, {} bozuk",
        rows.len(),
        rows.len() - broken.len(),
        broken.len()
    );
    if !broken.is_empty() {
        println!("{:<28} {:<12} {}", "SITE", "ADIM", "MESAJ");
        for r in &broken {
            let msg: String = r.msg.chars().take(60).collect();
            println!("{:<28} {:<12} {}", r.site, r.stage, msg);
        }
    }
    println!("CSV: {}", out_path.display());
    Ok(())
}
