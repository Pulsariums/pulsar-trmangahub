//! `pulsar sweep` — Kototoro `source-host serve` sürecini sürer, katalogdaki
//! eklenti kaynaklarını adım adım gezer ve CSV basar.
//!
//! Adımlar cihaz testiyle aynı sırada: `sources` → her kaynak için `list` →
//! `cover` → `search` ("a", "one") → `details` → ilk `chapter` → `pages`.
//! Süreçle JSONL konuşulur; her isteğe artan `requestId` verilir ve yanıt
//! `requestId` ile eşleştirilir.
//!
//! İki giriş biçimi vardır:
//! - `--jar <yol>`: hazır JAR (eski davranış). `--package`/`--version-code` verilmezse
//!   varsayılan paket kullanılır.
//! - `--apk <yol>` veya `--lang <dil>`: APK doğrudan verilir ya da `index.min.json`
//!   içinden dile göre paketler bulunur. Her APK, Kototoro'nun kendi
//!   `DexConvertCliKt` sınıfıyla geçici JAR'a çevrilir; paket kimliği ve sha256
//!   dönüşüm çıktısından alınır. Böylece "güncel APK'yı test et" tek komuttur.
//!
//! Harness arızası: `source-host` köprüsü (suwayomi sınıfları) yüzünden düşen
//! çağrılar `harness` diye işaretlenir. Ölçüt, çağrının stderr bloğundaki
//! `Caused by:` satırında `NoClassDefFoundError` / `CloudflareInterceptor` /
//! `suwayomi` geçmesidir; her yığın izinde görülen sıradan `suwayomi` çerçeveleri
//! bu yüzden sayılmaz.
//!
//! Kullanım:
//!   pulsar sweep --lang tr [--nsfw 0|1] [--name <parça>]... [--limit N]
//!   pulsar sweep --apk <dosya.apk> [--catalogue <yol>]
//!   pulsar sweep --jar <dosya.jar> --package <ad> --version-code <n>
//!     [--out <csv>] [--site <domain>]... [--timeout <sn>]
//!   Ortak: `--java` ve `--app` verilmezse masaüstü Kototoro kurulumu aranır.

use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::collections::{BTreeMap, HashSet, VecDeque};
use std::io::{BufRead, BufReader, Write};
use std::path::{Path, PathBuf};
use std::process::{Child, ChildStdin, Command, ExitCode, Stdio};
use std::sync::mpsc::{self, Receiver, RecvTimeoutError};
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant, SystemTime, UNIX_EPOCH};

const PLATFORM_CLASS: &str = "org.skepsun.kototoro.desktop.compat.MihonDesktopPlatform";
const CHILD_FIRST_PLATFORM: &str = "pulsar.harness.ChildFirstPlatform";
const ENGINE_JAR_PROPERTY: &str = "pulsar.engineJar";
const PARSERS_JAR_PROPERTY: &str = "pulsar.parsersJar";
/// `pulsar-v2/extension/build.gradle.kts` içindeki `parsersRef` varsayılanı.
/// Değişirse buradaki değer de güncellenmeli; yalnız yerel engine testi içindir.
const PARSERS_REF: &str = "59c033ecfd";
const SHIM_SOURCE: &str = include_str!("../java/ChildFirstPlatform.java");
const HOST_MAIN: &str = "org.skepsun.kototoro.source.host.SourceHostCliKt";
const DEX_CONVERT_MAIN: &str = "org.skepsun.kototoro.dex.DexConvertCliKt";
const DEFAULT_PACKAGE: &str = "eu.kanade.tachiyomi.extension.all.pulsar.tr";
const DEFAULT_VERSION_CODE: i64 = 35;
const DEFAULT_CATALOGUE: &str = "pulsar-v2/extension/src/main/assets/catalogue.json";
const DEFAULT_APK_DIR: &str = "apk";
const DEFAULT_INDEX: &str = "index.min.json";
const DEFAULT_TIMEOUT_SECS: u64 = 40;
const SOURCE_BUDGET_SECS: u64 = 90;
const SEARCH_QUERIES: [&str; 2] = ["a", "one"];

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

fn arg_values(argv: &[String], name: &str) -> Vec<String> {
    argv.iter()
        .enumerate()
        .filter(|(_, a)| a.as_str() == name)
        .filter_map(|(i, _)| argv.get(i + 1).cloned())
        .map(|s| s.trim().to_lowercase())
        .filter(|s| !s.is_empty())
        .collect()
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

fn resolve_out(root: &Path, p: &str) -> PathBuf {
    let path = PathBuf::from(p);
    if path.is_absolute() {
        path
    } else {
        root.join(path)
    }
}

fn now_epoch() -> u64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_secs())
        .unwrap_or(0)
}

fn safe_name(s: &str) -> String {
    s.chars()
        .map(|c| {
            if c.is_ascii_alphanumeric() || c == '-' || c == '_' {
                c
            } else {
                '_'
            }
        })
        .collect()
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

impl Fail {
    fn unsupported(&self) -> bool {
        self.msg.contains("UNSUPPORTED_OPERATION")
    }
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
        shim_dir: Option<&Path>,
        engine_jar: Option<&Path>,
        parsers_jar: Option<&Path>,
    ) -> Result<Host, String> {
        // Windows'ta JVM sınıf yolu joker karakterini kendisi açar.
        let sep = if cfg!(windows) { ';' } else { ':' };
        let mut classpath = String::new();
        if let Some(shim) = shim_dir {
            classpath.push_str(&shim.to_string_lossy());
            classpath.push(sep);
        }
        classpath.push_str(&app.join("*").to_string_lossy());
        let mut command = Command::new(java);
        // source-host, arıza yığınlarını yalnız bu özellik verilince
        // stderr'e basar (`reportFailure`); harness imzası bunsuz görünmez.
        command.arg("-Dkototoro.source.diagnostics=stderr");
        if let Some(jar) = engine_jar {
            command.arg(format!("-D{}={}", ENGINE_JAR_PROPERTY, jar.to_string_lossy()));
        }
        if let Some(jar) = parsers_jar {
            command.arg(format!("-D{}={}", PARSERS_JAR_PROPERTY, jar.to_string_lossy()));
        }
        let mut child = command
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
        // Bu isteğe ait SOURCE_FAILURE bloğu yoksa harness imzası da yoktur.
        // Tüm arabelleği taramak, önceki kaynağın ABI izini bu satıra yazar
        // (ör. sayfa listesi boş gibi protokol hatası olmayan düşüşler).
        let start = match start {
            Some(i) => i,
            None => return false,
        };
        let block: Vec<&String> = lines
            .iter()
            .skip(start + 1)
            .take_while(|l| !l.starts_with("SOURCE_FAILURE "))
            .collect();
        block.iter().any(|l| {
            let t = l.trim();
            t.contains("NoClassDefFoundError")
                || t.contains("NoSuchMethodError")
                || t.contains("AbstractMethodError")
                || t.contains("Mihon runtime ABI failure")
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
    lang: String,
    nsfw: i32,
    engine: bool,
}

struct Row {
    package: String,
    id: String,
    site: String,
    lang: String,
    nsfw: i32,
    list: String,
    cover: String,
    details: String,
    chapters: String,
    pages: String,
    search: String,
    stage: String,
    msg: String,
    cause: String,
    fail_rid: String,
    eser: String,
}

impl Row {
    fn new(package: &str, t: &Target) -> Row {
        Row {
            package: package.to_string(),
            id: t.id.clone(),
            site: t.site.clone(),
            lang: t.lang.clone(),
            nsfw: t.nsfw,
            list: String::new(),
            cover: String::new(),
            details: String::new(),
            chapters: String::new(),
            pages: String::new(),
            search: String::new(),
            stage: String::new(),
            msg: String::new(),
            cause: String::new(),
            fail_rid: String::new(),
            eser: String::new(),
        }
    }
}

fn stage_rank(stage: &str) -> u8 {
    match stage {
        "harness" => 3,
        "zaman_asimi" => 2,
        "" => 0,
        _ => 1,
    }
}

fn set_stage(row: &mut Row, stage: &str, msg: &str, rid: &str) {
    if stage_rank(stage) > stage_rank(&row.stage) {
        row.stage = stage.to_string();
        row.msg = msg.to_string();
        row.fail_rid = rid.to_string();
    }
}

/// `SOURCE_FAILURE <rid> <Call>` bloğundan kök sebebi çıkarır. Protokol
/// bilerek sebep taşımaz; yığın izi yalnız `-Dkototoro.source.diagnostics=stderr`
/// açıkken stderr'e düşer. Son `Caused by:` satırı varsa o, yoksa ilk istisna
/// satırı kullanılır.
fn stderr_cause(lines: &[String], rid: &str) -> Option<String> {
    let start = lines
        .iter()
        .position(|l| l.starts_with("SOURCE_FAILURE ") && l.contains(rid))?;
    let block: Vec<&String> = lines
        .iter()
        .skip(start + 1)
        .take_while(|l| !l.starts_with("SOURCE_FAILURE "))
        .collect();
    let head = block.iter().find(|l| {
        let t = l.trim();
        !t.is_empty()
            && !t.starts_with("at ")
            && !t.starts_with("Caused by:")
            && !t.starts_with("Suppressed:")
            && !t.starts_with("...")
    });
    // RxJava, kaynağın kendi istisnasını `OnErrorThrowable` ile sarar; bu
    // sarmalayıcı sebep değildir. Gerçek kök `Caused by:` satırı varsa o,
    // yoksa kaynağın fırlattığı ilk istisna (bizim `TANI ...` mesajı gibi)
    // kullanılır.
    let root = block.iter().find(|l| {
        let t = l.trim();
        t.starts_with("Caused by:") && !t.contains("rx.exceptions.OnErrorThrowable")
    });
    let head_text = head.map(|l| l.trim());
    let head_is_wrapper = head_text
        .map(|h| h.starts_with("rx.exceptions.OnErrorThrowable"))
        .unwrap_or(false);
    let head_has_message = head_text.map(|h| h.contains(": ")).unwrap_or(false);
    let text = if head_is_wrapper || !head_has_message {
        root.map(|l| l.trim()).or(head_text)
    } else {
        head_text.or_else(|| root.map(|l| l.trim()))
    }?;
    let text = text.strip_prefix("Caused by: ").unwrap_or(text);
    Some(text.chars().take(180).collect())
}

fn stderr_block<'a>(lines: &'a [String], rid: &str) -> Option<Vec<&'a String>> {
    let start = lines
        .iter()
        .position(|l| l.starts_with("SOURCE_FAILURE ") && l.contains(rid))?;
    let mut out = Vec::new();
    for l in lines.iter().skip(start) {
        if !out.is_empty() && l.starts_with("SOURCE_FAILURE ") {
            break;
        }
        out.push(l);
    }
    Some(out)
}

fn record_fail(row: &mut Row, f: &Fail, stage: &str, rid: &str) -> Result<(), String> {
    if f.kind == FailKind::Fatal {
        return Err(f.msg.clone());
    }
    let new_stage = if f.harness {
        "harness"
    } else if f.kind == FailKind::Timeout {
        "zaman_asimi"
    } else {
        stage
    };
    set_stage(row, new_stage, &f.msg, rid);
    Ok(())
}

fn csv_escape(s: &str) -> String {
    let s = s.replace('\r', " ").replace('\n', " ");
    if s.contains(',') || s.contains('"') {
        format!("\"{}\"", s.replace('"', "\"\""))
    } else {
        s
    }
}

#[derive(Clone)]
struct CatSource {
    name: String,
    domain: String,
    lang: String,
    nsfw: i32,
}

struct Options {
    java: String,
    app: PathBuf,
    catalogue: PathBuf,
    out: PathBuf,
    apk_dir: PathBuf,
    index: PathBuf,
    status: PathBuf,
    timeout: Duration,
    limit: Option<usize>,
    sites: Vec<String>,
    names: Vec<String>,
    lang: Option<String>,
    nsfw: Option<i32>,
    package: Option<String>,
    version_code: Option<i64>,
    debug: bool,
    engine: bool,
    shim_dir: Option<PathBuf>,
    parsers_jar: Option<PathBuf>,
}

#[derive(Clone)]
struct IndexSource {
    name: String,
    id: String,
    base_url: String,
    lang: String,
    nsfw: i32,
}

enum Mode {
    Jar {
        path: PathBuf,
        package: String,
        version_code: i64,
        sha256: String,
        hints: Option<Vec<IndexSource>>,
    },
    Apk {
        path: PathBuf,
        hints: Option<Vec<IndexSource>>,
    },
    Packages {
        entries: Vec<PkgEntry>,
    },
}

struct PkgEntry {
    pkg: String,
    apk: String,
    lang: String,
    nsfw: i32,
    code: i64,
    sources: Vec<IndexSource>,
}

struct Converted {
    jar: PathBuf,
    package: String,
    version_code: i64,
    sha256: String,
}

struct Identity {
    package: String,
    version_code: i64,
    sha256: String,
}

fn detect_kototoro() -> Option<(String, PathBuf)> {
    let mut bases: Vec<PathBuf> = Vec::new();
    if let Ok(home) = std::env::var("KOTOTORO_HOME") {
        bases.push(PathBuf::from(home));
    }
    if let Ok(profile) = std::env::var("USERPROFILE") {
        bases.push(PathBuf::from(profile).join("Desktop").join("Kototoro"));
    }
    if let Ok(home) = std::env::var("HOME") {
        bases.push(PathBuf::from(home).join("Desktop").join("Kototoro"));
    }
    for base in bases {
        let java = base
            .join("runtime")
            .join("bin")
            .join(if cfg!(windows) { "java.exe" } else { "java" });
        let app = base.join("app");
        if java.is_file() && app.is_dir() {
            return Some((java.to_string_lossy().to_string(), app));
        }
    }
    None
}

fn parse_options(root: &Path, argv: &[String]) -> Result<Options, String> {
    let detected = detect_kototoro();
    let java = match arg_value(argv, "--java") {
        Some(v) => v,
        None => detected
            .as_ref()
            .map(|(j, _)| j.clone())
            .ok_or("--java gerekli (masaüstü Kototoro kurulumu bulunamadı)")?,
    };
    let app = match arg_value(argv, "--app") {
        Some(v) => resolve(root, &v),
        None => detected
            .as_ref()
            .map(|(_, a)| a.clone())
            .ok_or("--app gerekli (masaüstü Kototoro kurulumu bulunamadı)")?,
    };
    let catalogue = resolve(
        root,
        &arg_value(argv, "--catalogue").unwrap_or_else(|| DEFAULT_CATALOGUE.to_string()),
    );
    let out = resolve_out(
        root,
        &arg_value(argv, "--out")
            .unwrap_or_else(|| format!("pulsar-v2/data/sweep-{}.csv", now_epoch())),
    );
    let timeout_secs = match arg_value(argv, "--timeout") {
        Some(v) => v
            .parse::<u64>()
            .map_err(|e| format!("--timeout geçersiz: {e}"))?,
        None => DEFAULT_TIMEOUT_SECS,
    };
    let limit = match arg_value(argv, "--limit") {
        Some(v) => Some(
            v.parse::<usize>()
                .map_err(|e| format!("--limit geçersiz: {e}"))?,
        ),
        None => None,
    };
    let nsfw = match arg_value(argv, "--nsfw") {
        Some(v) => {
            let n = v
                .parse::<i32>()
                .map_err(|e| format!("--nsfw geçersiz: {e}"))?;
            if n != 0 && n != 1 {
                return Err("--nsfw yalnız 0 veya 1 olabilir".to_string());
            }
            Some(n)
        }
        None => None,
    };
    let lang = arg_value(argv, "--lang")
        .map(|s| s.trim().to_lowercase())
        .filter(|s| !s.is_empty());
    let sites = arg_values(argv, "--site");
    let names = arg_values(argv, "--name");
    let apk_dir = resolve(
        root,
        &arg_value(argv, "--apk-dir").unwrap_or_else(|| DEFAULT_APK_DIR.to_string()),
    );
    let index = resolve(
        root,
        &arg_value(argv, "--index").unwrap_or_else(|| DEFAULT_INDEX.to_string()),
    );
    let status = resolve(
        root,
        &arg_value(argv, "--status")
            .unwrap_or_else(|| "pulsar-v2/data/source-status.json".to_string()),
    );

    Ok(Options {
        java,
        app,
        catalogue,
        out,
        apk_dir,
        index,
        status,
        timeout: Duration::from_secs(timeout_secs.max(1)),
        limit,
        sites,
        names,
        lang,
        nsfw,
        package: arg_value(argv, "--package"),
        version_code: match arg_value(argv, "--version-code") {
            Some(v) => Some(
                v.parse::<i64>()
                    .map_err(|e| format!("--version-code geçersiz: {e}"))?,
            ),
            None => None,
        },
        debug: argv.iter().any(|a| a == "--debug"),
        engine: argv.iter().any(|a| a == "--engine"),
        shim_dir: None,
        parsers_jar: None,
    })
}

fn choose_mode(root: &Path, argv: &[String], opts: &Options) -> Result<Mode, String> {
    if let Some(jar) = arg_value(argv, "--jar") {
        let path = resolve(root, &jar);
        if path.extension().and_then(|e| e.to_str()) == Some("apk") {
            return Ok(Mode::Apk { path, hints: None });
        }
        let bytes = std::fs::read(&path)
            .map_err(|e| format!("{} okunamadı: {e}", path.display()))?;
        let sha256 = format!("{:x}", Sha256::digest(&bytes));
        let package = opts
            .package
            .clone()
            .unwrap_or_else(|| DEFAULT_PACKAGE.to_string());
        let hints = find_pkg_sources(&opts.index, &package);
        return Ok(Mode::Jar {
            path,
            package,
            version_code: opts.version_code.unwrap_or(DEFAULT_VERSION_CODE),
            sha256,
            hints,
        });
    }
    if let Some(apk) = arg_value(argv, "--apk") {
        return Ok(Mode::Apk {
            path: resolve(root, &apk),
            hints: None,
        });
    }
    let lang = opts
        .lang
        .as_deref()
        .ok_or("--jar, --apk veya --lang verilmeli")?;
    let entries = discover_packages(&opts.index, lang, opts.nsfw, &opts.apk_dir)?;
    Ok(Mode::Packages { entries })
}

fn host_of(url: &str) -> String {
    let s = url.split("://").nth(1).unwrap_or(url);
    let host = s
        .split('/')
        .next()
        .unwrap_or(s)
        .split(':')
        .next()
        .unwrap_or(s);
    host.trim_start_matches("www.").to_lowercase()
}

fn index_sources_of(p: &Value, default_lang: &str, default_nsfw: i32) -> Vec<IndexSource> {
    p.get("sources")
        .and_then(|v| v.as_array())
        .into_iter()
        .flatten()
        .filter_map(|s| {
            let id = s.get("id").and_then(|v| v.as_str()).unwrap_or("");
            if id.is_empty() {
                return None;
            }
            Some(IndexSource {
                name: s.get("name").and_then(|v| v.as_str()).unwrap_or("").to_string(),
                id: id.to_string(),
                base_url: s
                    .get("baseUrl")
                    .and_then(|v| v.as_str())
                    .unwrap_or("")
                    .to_string(),
                lang: s
                    .get("lang")
                    .and_then(|v| v.as_str())
                    .unwrap_or(default_lang)
                    .to_string(),
                nsfw: s
                    .get("nsfw")
                    .and_then(|v| v.as_i64())
                    .map(|x| x as i32)
                    .unwrap_or(default_nsfw),
            })
        })
        .collect()
}

fn find_pkg_sources(index: &Path, pkg: &str) -> Option<Vec<IndexSource>> {
    let text = std::fs::read_to_string(index).ok()?;
    let doc: Value = serde_json::from_str(&text).ok()?;
    let arr = doc.as_array()?;
    let p = arr
        .iter()
        .find(|p| p.get("pkg").and_then(|v| v.as_str()) == Some(pkg))?;
    let lang = p.get("lang").and_then(|v| v.as_str()).unwrap_or("tr");
    let nsfw = p.get("nsfw").and_then(|v| v.as_i64()).unwrap_or(0) as i32;
    Some(index_sources_of(p, lang, nsfw))
}

fn discover_packages(
    index: &Path,
    lang: &str,
    nsfw: Option<i32>,
    apk_dir: &Path,
) -> Result<Vec<PkgEntry>, String> {
    let text = std::fs::read_to_string(index)
        .map_err(|e| format!("{} okunamadı: {e}", index.display()))?;
    let doc: Value = serde_json::from_str(&text)
        .map_err(|e| format!("{} geçersiz JSON: {e}", index.display()))?;
    let arr = doc
        .as_array()
        .ok_or("index.min.json bir dizi değil")?;
    let mut out = Vec::new();
    for p in arr {
        let pkg = p.get("pkg").and_then(|v| v.as_str()).unwrap_or("");
        let apk = p.get("apk").and_then(|v| v.as_str()).unwrap_or("");
        let plang = p.get("lang").and_then(|v| v.as_str()).unwrap_or("");
        let pnsfw = p.get("nsfw").and_then(|v| v.as_i64()).unwrap_or(0) as i32;
        let code = p.get("code").and_then(|v| v.as_i64()).unwrap_or(0);
        let count = p
            .get("sources")
            .and_then(|v| v.as_array())
            .map(|a| a.len())
            .unwrap_or(0);
        if pkg.is_empty() || apk.is_empty() || count == 0 {
            continue;
        }
        if !plang.eq_ignore_ascii_case(lang) {
            continue;
        }
        if let Some(want) = nsfw {
            if pnsfw != want {
                continue;
            }
        }
        if !apk_dir.join(apk).is_file() {
            continue;
        }
        out.push(PkgEntry {
            pkg: pkg.to_string(),
            apk: apk.to_string(),
            lang: plang.to_string(),
            nsfw: pnsfw,
            code,
            sources: index_sources_of(p, plang, pnsfw),
        });
    }
    if out.is_empty() {
        return Err(format!(
            "{} içinde '{}' diline uyan APK yok",
            index.display(),
            lang
        ));
    }
    Ok(out)
}

/// `source-status.json` içinde `kind=engine` olan kimlikler. Yerel source-host
/// motor (kotatsu parser) kaynaklarını `newParserInstance` ABI uyuşmazlığı
/// yüzünden çalıştıramıyor; bu kaynaklar test edilmiş sayılmaz.
fn load_engine_ids(path: &Path) -> HashSet<String> {
    let mut out = HashSet::new();
    let Ok(text) = std::fs::read_to_string(path) else {
        return out;
    };
    let Ok(doc) = serde_json::from_str::<Value>(&text) else {
        return out;
    };
    let Some(sources) = doc.get("sources").and_then(|v| v.as_object()) else {
        return out;
    };
    for (id, entry) in sources {
        if entry.get("kind").and_then(|v| v.as_str()) == Some("engine") {
            out.insert(id.clone());
        }
    }
    out
}

fn load_catalogue(path: &Path) -> Result<Vec<CatSource>, String> {
    let text = std::fs::read_to_string(path)
        .map_err(|e| format!("{} okunamadı: {e}", path.display()))?;
    let doc: Value = serde_json::from_str(&text)
        .map_err(|e| format!("{} geçersiz JSON: {e}", path.display()))?;
    let arr = doc
        .get("sources")
        .and_then(|v| v.as_array())
        .ok_or("catalogue.json içinde 'sources' dizisi yok")?;
    let mut out = Vec::with_capacity(arr.len());
    for s in arr {
        let name = s
            .get("name")
            .and_then(|v| v.as_str())
            .or_else(|| s.get("title").and_then(|v| v.as_str()))
            .unwrap_or("")
            .to_string();
        let domain = s
            .get("domain")
            .and_then(|v| v.as_str())
            .or_else(|| s.get("id").and_then(|v| v.as_str()))
            .unwrap_or("")
            .to_string();
        if domain.is_empty() {
            continue;
        }
        out.push(CatSource {
            name,
            domain,
            lang: s
                .get("lang")
                .and_then(|v| v.as_str())
                .unwrap_or("tr")
                .to_string(),
            nsfw: s.get("nsfw").and_then(|v| v.as_i64()).unwrap_or(0) as i32,
        });
    }
    Ok(out)
}

fn json_str_field(line: &str, key: &str) -> Option<String> {
    let pat = format!("\"{key}\":\"");
    let start = line.find(&pat)? + pat.len();
    let rest = &line[start..];
    let end = rest.find('"')?;
    Some(rest[..end].to_string())
}

fn json_i64_field(line: &str, key: &str) -> Option<i64> {
    let pat = format!("\"{key}\":");
    let start = line.find(&pat)? + pat.len();
    let rest = &line[start..];
    let end = rest
        .find(|c: char| !(c.is_ascii_digit() || c == '-'))
        .unwrap_or(rest.len());
    rest[..end].parse().ok()
}

/// Maven'daki parser JAR'ını (`--engine`) bir kez indirip önbelleğe alır.
/// APK'nın dex çıktısı arayüz varsayılan metotlarında masaüstü JVM'e uymaz;
/// aynı rev'in JVM bayt kodu child-first yükleyicide kullanılır.
fn ensure_parsers_jar(root: &Path) -> Result<PathBuf, String> {
    let dir = root.join("pulsar-v2/.work/harness");
    let jar = dir.join(format!("kotatsu-parsers-{PARSERS_REF}.jar"));
    if std::fs::metadata(&jar).map(|m| m.len() > 1_000_000).unwrap_or(false) {
        return Ok(jar);
    }
    std::fs::create_dir_all(&dir)
        .map_err(|e| format!("{} oluşturulamadı: {e}", dir.display()))?;
    let url = format!(
        "https://jitpack.io/com/github/clquwu/kotatsu-parsers-redo/{PARSERS_REF}/kotatsu-parsers-redo-{PARSERS_REF}.jar"
    );
    let part = jar.with_extension("jar.part");
    let status = Command::new("curl")
        .args(["-fsSL", "--retry", "2", "--max-time", "180", "-o"])
        .arg(&part)
        .arg(&url)
        .status()
        .map_err(|e| format!("curl başlatılamadı: {e}"))?;
    if !status.success() {
        return Err(format!("engine parser JAR indirilemedi: {url}"));
    }
    let size = std::fs::metadata(&part).map(|m| m.len()).unwrap_or(0);
    if size < 1_000_000 {
        return Err(format!(
            "engine parser JAR beklenenden küçük ({size} bayt): {}",
            part.display()
        ));
    }
    std::fs::rename(&part, &jar)
        .map_err(|e| format!("{} taşınamadı: {e}", part.display()))?;
    Ok(jar)
}

/// Engine kaynakları için child-first platform sarmalayıcısını derler.
/// `javac` JRE ile birlikte gelmezse PATH'teki `javac` denenir.
fn compile_shim(java: &str, app: &Path, tmp_root: &Path) -> Result<PathBuf, String> {
    let sibling = Path::new(java).with_file_name(if cfg!(windows) { "javac.exe" } else { "javac" });
    let javac = if sibling.is_file() {
        sibling
    } else {
        PathBuf::from("javac")
    };
    let dir = tmp_root.join("shim");
    std::fs::create_dir_all(&dir)
        .map_err(|e| format!("{} oluşturulamadı: {e}", dir.display()))?;
    let source = dir.join("ChildFirstPlatform.java");
    std::fs::write(&source, SHIM_SOURCE)
        .map_err(|e| format!("{} yazılamadı: {e}", source.display()))?;
    let output = Command::new(&javac)
        .arg("-cp")
        .arg(app.join("*"))
        .arg("-d")
        .arg(&dir)
        .arg(&source)
        .output()
        .map_err(|e| format!("javac başlatılamadı ({}): {e}", javac.display()))?;
    if !output.status.success() {
        let err = String::from_utf8_lossy(&output.stderr);
        let lines: Vec<&str> = err.lines().collect();
        let tail = lines
            .iter()
            .skip(lines.len().saturating_sub(10))
            .cloned()
            .collect::<Vec<_>>()
            .join("\n");
        return Err(format!("harness köprüsü derlenemedi: {tail}"));
    }
    Ok(dir)
}

fn convert_apk(java: &str, app: &Path, apk: &Path, jar: &Path) -> Result<Converted, String> {
    let classpath = app.join("*");
    let output = Command::new(java)
        .arg("-cp")
        .arg(&classpath)
        .arg(DEX_CONVERT_MAIN)
        .arg(apk)
        .arg(jar)
        .output()
        .map_err(|e| format!("APK→JAR dönüşümü başlatılamadı: {e}"))?;
    if !output.status.success() {
        let err = String::from_utf8_lossy(&output.stderr);
        let lines: Vec<&str> = err.lines().collect();
        let tail = lines
            .iter()
            .skip(lines.len().saturating_sub(12))
            .cloned()
            .collect::<Vec<_>>()
            .join("\n");
        return Err(format!(
            "APK→JAR dönüşümü düştü ({}): {}",
            apk.display(),
            tail
        ));
    }
    let stdout = String::from_utf8_lossy(&output.stdout);
    let line = stdout
        .lines()
        .collect::<Vec<_>>()
        .into_iter()
        .rev()
        .find(|l| l.trim_start().starts_with("CONVERTED "))
        .ok_or("DexConvertCli çıktısı okunamadı (CONVERTED satırı yok)")?;
    // Windows'ta `output` alanı kaçışsız ters bölü içerir; DexConvertCli'nin
    // ürettiği satır bu yüzden geçerli JSON değildir. İhtiyacımız olan üç alan
    // kaçış içermez, doğrudan metinden çıkarılır.
    let json_text = line.trim_start().trim_start_matches("CONVERTED ").trim();
    let package = json_str_field(json_text, "packageName")
        .ok_or("CONVERTED içinde packageName yok")?;
    let version_code =
        json_i64_field(json_text, "versionCode").ok_or("CONVERTED içinde versionCode yok")?;
    let sha256 = json_str_field(json_text, "sha256").ok_or("CONVERTED içinde sha256 yok")?;
    if !jar.is_file() {
        return Err(format!("dönüşüm çıktısı yok: {}", jar.display()));
    }
    Ok(Converted {
        jar: jar.to_path_buf(),
        package,
        version_code,
        sha256,
    })
}

fn budget_over(started: Instant) -> bool {
    started.elapsed() >= Duration::from_secs(SOURCE_BUDGET_SECS)
}

fn run_one(
    opts: &Options,
    identity: &Identity,
    jar: &Path,
    package_label: &str,
    cat: &[CatSource],
    hints: Option<&[IndexSource]>,
    engine_ids: &HashSet<String>,
    seen: &mut HashSet<String>,
    remaining: &mut Option<usize>,
    tmp_root: &Path,
) -> Result<Vec<Row>, String> {
    let tmp = tmp_root.join(safe_name(package_label));
    if tmp.exists() {
        let _ = std::fs::remove_dir_all(&tmp);
    }
    for sub in ["imageDirectory", "preferenceDirectory", "catalogDirectory"] {
        std::fs::create_dir_all(tmp.join(sub))
            .map_err(|e| format!("{} oluşturulamadı: {e}", tmp.join(sub).display()))?;
    }
    let config_path = tmp.join("config.json");
    let engine_jar = if opts.engine { Some(jar) } else { None };
    let config = json!({
        "platformClass": if engine_jar.is_some() { CHILD_FIRST_PLATFORM } else { PLATFORM_CLASS },
        "jars": [{
            "path": jar.to_string_lossy(),
            "identity": {
                "packageName": identity.package,
                "versionCode": identity.version_code,
                "sha256": identity.sha256,
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
        &opts.java,
        &opts.app,
        &config_path,
        opts.timeout,
        opts.shim_dir.as_deref(),
        engine_jar,
        opts.parsers_jar.as_deref(),
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
        return Err(format!("{package_label}: sources yanıtı boş"));
    }

    // 2) Hedefler: indeksten gelen kaynak listesi varsa onu kullan (motor
    // kaynakları da kapsar); yoksa katalogdan üret. Her iki durumda da
    // harness'ın gerçekten oluşturduğu kaynaklarla kesiştir.
    let mut targets: Vec<Target> = Vec::new();
    if let Some(hints) = hints {
        for s in hints {
            if matches!(*remaining, Some(0)) {
                break;
            }
            if let Some(want) = &opts.lang {
                if !s.lang.eq_ignore_ascii_case(want) {
                    continue;
                }
            }
            if let Some(want) = opts.nsfw {
                if s.nsfw != want {
                    continue;
                }
            }
            let site = host_of(&s.base_url);
            if site.is_empty() {
                continue;
            }
            if !opts.names.is_empty() {
                let hay = format!("{} {}", s.name, site).to_lowercase();
                if !opts.names.iter().any(|k| hay.contains(k)) {
                    continue;
                }
            }
            if !opts.sites.is_empty()
                && !opts
                    .sites
                    .iter()
                    .any(|x| x == &site || x == &format!("www.{site}"))
            {
                continue;
            }
            let name = format!("MIHON_{}", s.id);
            if !available.contains(&name) {
                continue;
            }
            if !seen.insert(name.clone()) {
                continue;
            }
            targets.push(Target {
                id: s.id.clone(),
                name,
                site,
                lang: s.lang.clone(),
                nsfw: s.nsfw,
                engine: engine_ids.contains(&s.id),
            });
            if let Some(n) = remaining.as_mut() {
                *n = n.saturating_sub(1);
            }
        }
    } else {
        for s in cat {
            if matches!(*remaining, Some(0)) {
                break;
            }
            if let Some(want) = &opts.lang {
                if !s.lang.eq_ignore_ascii_case(want) {
                    continue;
                }
            }
            if let Some(want) = opts.nsfw {
                if s.nsfw != want {
                    continue;
                }
            }
            if !opts.names.is_empty() {
                let hay = format!("{} {}", s.name, s.domain).to_lowercase();
                if !opts.names.iter().any(|k| hay.contains(k)) {
                    continue;
                }
            }
            let site_lower = s.domain.to_lowercase();
            if !opts.sites.is_empty()
                && !opts
                    .sites
                    .iter()
                    .any(|x| x == &site_lower || x == &format!("www.{site_lower}"))
            {
                continue;
            }
            let hash = source_hash(&format!("pulsar/{}/{}", s.domain, s.lang));
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
                site: s.domain.clone(),
                lang: s.lang.clone(),
                nsfw: s.nsfw,
                engine: false,
            });
            if let Some(n) = remaining.as_mut() {
                *n = n.saturating_sub(1);
            }
        }
    }
    if targets.is_empty() {
        return Ok(Vec::new());
    }

    // 3) Her kaynak: list → cover → search → details → chapters → pages.
    let mut rows: Vec<Row> = Vec::with_capacity(targets.len());
    for t in &targets {
        let started = Instant::now();
        let mut row = Row::new(package_label, t);
        if t.engine && !opts.engine {
            set_stage(
                &mut row,
                "harness",
                "yerel harness engine kaynağını çalıştıramıyor (ABI)",
                "",
            );
            row.cause =
                "engine kaynağı: newParserInstance ABI uyuşmazlığı (yerel harness)".to_string();
            rows.push(row);
            continue;
        }

        let list_rid = format!("s{}-list", t.id);
        let list_resp = match host.request(
            &list_rid,
            json!({"operation": "list", "sourceName": t.name, "offset": 0}),
        ) {
            Ok(v) => v,
            Err(f) => {
                record_fail(&mut row, &f, "list", &list_rid)?;
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
            set_stage(&mut row, "list", "liste boş", "");
            rows.push(row);
            continue;
        }

        // 3a) Kapak — ilk eserin görseli gerçekten indi mi?
        if budget_over(started) {
            set_stage(&mut row, "zaman_asimi", "kaynak bütçesi (90 sn) doldu", "");
            rows.push(row);
            continue;
        }
        // Cihaz testi kapakları liste öğeleri üzerinde dener; ilk öğenin
        // kapağı yoksa kaynak bozuk sayılmaz. İlk 3 öğe denenir.
        let mut cover_ok = false;
        let mut cover_fail: Option<(String, Fail)> = None;
        for (i, item) in content.iter().take(3).enumerate() {
            let cover_rid = format!("s{}-cover-{i}", t.id);
            match host.request(
                &cover_rid,
                json!({"operation": "cover", "content": item}),
            ) {
                Ok(v) => {
                    // `byteSize` Long alanı protokolde ondalık string olarak gelir.
                    let bytes = value_i64(v.pointer("/result/artifact/byteSize"));
                    row.cover = bytes.to_string();
                    if bytes > 0 {
                        cover_ok = true;
                        break;
                    }
                }
                Err(f) => {
                    if f.unsupported() {
                        row.cover = "yok".to_string();
                        cover_ok = true;
                        break;
                    }
                    cover_fail = Some((cover_rid, f));
                }
            }
        }
        if !cover_ok {
            match cover_fail {
                Some((rid, f)) => {
                    record_fail(&mut row, &f, "cover", &rid)?;
                    row.cover = "hata".to_string();
                }
                None => {
                    set_stage(
                        &mut row,
                        "cover",
                        "kapak 0 bayt (ilk 3 eser)",
                        &format!("s{}-cover-0", t.id),
                    );
                }
            }
        }

        // 3b) Arama — cihazın kullandığı iki sorgu; biri sonuç dönerse geçer.
        if budget_over(started) {
            set_stage(&mut row, "zaman_asimi", "kaynak bütçesi (90 sn) doldu", "");
            rows.push(row);
            continue;
        }
        let mut search_ok = false;
        let mut search_unsupported = false;
        let mut search_error = false;
        for q in SEARCH_QUERIES {
            let rid = format!("s{}-search-{q}", t.id);
            match host.request(
                &rid,
                json!({"operation": "list", "sourceName": t.name, "offset": 0,
                       "filter": {"query": q}}),
            ) {
                Ok(v) => {
                    let n = v
                        .pointer("/result/content")
                        .and_then(|c| c.as_array())
                        .map(|a| a.len())
                        .unwrap_or(0);
                    if n > 0 {
                        row.search = format!("{q}:{n}");
                        search_ok = true;
                        break;
                    }
                    row.search = "0".to_string();
                }
                Err(f) => {
                    if f.unsupported() {
                        row.search = "yok".to_string();
                        search_unsupported = true;
                        break;
                    }
                    record_fail(&mut row, &f, "search", &rid)?;
                    row.search = "hata".to_string();
                    search_error = true;
                    break;
                }
            }
        }
        if !search_ok && !search_unsupported && !search_error {
            set_stage(
                &mut row,
                "search",
                &format!("arama boş ({})", SEARCH_QUERIES.join(", ")),
                "",
            );
        }

        // 3c) Detay + bölümler. Details hatası sonraki esere geçirir; harness
        // imzalı hata geçiş yapmaz, o adımda biter.
        let mut last_detail: Option<Value> = None;
        let mut detail_ok: Option<Value> = None;
        let mut details_failed = false;
        let mut attempted = 0usize;
        const MAX_ESER: usize = 3;
        let attempts = content.len().min(MAX_ESER);
        for (i, item) in content.iter().take(MAX_ESER).enumerate() {
            attempted = i + 1;
            if budget_over(started) {
                set_stage(&mut row, "zaman_asimi", "kaynak bütçesi (90 sn) doldu", "");
                break;
            }
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
                    let harness = f.harness
                        || f.msg.contains("suwayomi")
                        || f.msg.contains("NoClassDefFoundError")
                        || f.msg.contains("CloudflareInterceptor");
                    if harness {
                        record_fail(&mut row, &f, "details", &details_rid)?;
                        row.details = "hata".to_string();
                        details_failed = true;
                        break;
                    }
                    if i + 1 >= attempts {
                        record_fail(&mut row, &f, "details", &details_rid)?;
                        row.details = "hata".to_string();
                        details_failed = true;
                        break;
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
            let chapters = detail
                .and_then(|c| c.get("chapters"))
                .and_then(|v| v.as_array())
                .cloned()
                .unwrap_or_default();
            row.chapters = chapters.len().to_string();
            last_detail = detail.cloned();
            if !chapters.is_empty() {
                detail_ok = detail.cloned();
                break;
            }
        }

        if details_failed {
            rows.push(row);
            continue;
        }
        let Some(detail) = detail_ok else {
            let msg = if attempted >= MAX_ESER {
                "3 eserde de bölüm yok".to_string()
            } else if attempted <= 1 {
                "bölüm yok".to_string()
            } else {
                format!("{attempted} eserde de bölüm yok")
            };
            if last_detail.is_some() {
                set_stage(&mut row, "chapters", &msg, "");
            } else {
                set_stage(&mut row, "details", &msg, "");
            }
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

        if budget_over(started) {
            set_stage(&mut row, "zaman_asimi", "kaynak bütçesi (90 sn) doldu", "");
            rows.push(row);
            continue;
        }
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
                if n == 0 {
                    set_stage(&mut row, "pages", "sayfa listesi boş", &pages_rid);
                }
            }
            Err(f) => {
                if f.unsupported() {
                    row.pages = "yok".to_string();
                } else {
                    record_fail(&mut row, &f, "pages", &pages_rid)?;
                    row.pages = "hata".to_string();
                }
            }
        }
        rows.push(row);
    }

    // 3d) stderr yığınları yanıtlardan sonra akabilir; koşu bitince harness
    // sınıflandırmasını tüm log üzerinden tazele.
    std::thread::sleep(Duration::from_millis(800));
    let err_log = host.err_log();
    if opts.debug {
        for r in rows.iter() {
            if r.fail_rid.is_empty() {
                continue;
            }
            if let Some(block) = stderr_block(&err_log, &r.fail_rid) {
                println!("[debug] {} / {} / {}", r.site, r.stage, r.fail_rid);
                for line in block.iter().take(120) {
                    println!("[debug] {line}");
                }
            }
        }
    }
    for r in rows.iter_mut() {
        if r.fail_rid.is_empty() || r.stage == "zaman_asimi" {
            if r.cause.is_empty() && !r.msg.is_empty() {
                r.cause = r.msg.clone();
            }
            continue;
        }
        if let Some(cause) = stderr_cause(&err_log, &r.fail_rid) {
            r.cause = cause;
        }
        if Host::stderr_has_harness(&err_log, &r.fail_rid) {
            if r.stage == "pages" {
                r.pages = "hata(harness)".to_string();
            } else if r.stage == "cover" {
                r.cover = "hata(harness)".to_string();
            } else if r.stage == "search" {
                r.search = "hata(harness)".to_string();
            }
            r.stage = "harness".to_string();
        }
    }
    for r in rows.iter_mut() {
        if r.cause.is_empty() && !r.stage.is_empty() {
            r.cause = if r.stage == "harness" {
                "yerel harness (engine ABI / Cloudflare köprüsü)".to_string()
            } else {
                r.msg.clone()
            };
        }
    }

    Ok(rows)
}

fn value_i64(v: Option<&Value>) -> i64 {
    match v {
        Some(Value::Number(n)) => n.as_i64().unwrap_or(0),
        Some(Value::String(s)) => s.parse().unwrap_or(0),
        _ => 0,
    }
}

fn sweep(root: &Path, argv: &[String]) -> Result<(), String> {
    let mut opts = parse_options(root, argv)?;
    let cat = load_catalogue(&opts.catalogue)?;
    let engine_ids = load_engine_ids(&opts.status);
    let mode = choose_mode(root, argv, &opts)?;

    let tmp_root = std::env::temp_dir().join(format!("pulsar-sweep-{}", std::process::id()));
    if tmp_root.exists() {
        let _ = std::fs::remove_dir_all(&tmp_root);
    }
    std::fs::create_dir_all(&tmp_root)
        .map_err(|e| format!("{} oluşturulamadı: {e}", tmp_root.display()))?;
    if opts.engine {
        opts.shim_dir = Some(compile_shim(&opts.java, &opts.app, &tmp_root)?);
        opts.parsers_jar = Some(ensure_parsers_jar(root)?);
    }

    let mut all_rows: Vec<Row> = Vec::new();
    let mut seen: HashSet<String> = HashSet::new();
    let mut remaining = opts.limit;

    match mode {
        Mode::Jar {
            path,
            package,
            version_code,
            sha256,
            hints,
        } => {
            let identity = Identity {
                package: package.clone(),
                version_code,
                sha256,
            };
            let rows = run_one(
                &opts,
                &identity,
                &path,
                &package,
                &cat,
                hints.as_deref(),
                &engine_ids,
                &mut seen,
                &mut remaining,
                &tmp_root,
            )?;
            all_rows.extend(rows);
        }
        Mode::Apk { path, hints } => {
            let jar = tmp_root.join(format!("{}.jar", safe_name("apk")));
            let conv = convert_apk(&opts.java, &opts.app, &path, &jar)?;
            if let Some(want) = &opts.package {
                if want != &conv.package {
                    return Err(format!(
                        "--package {} ile APK paketi {} uyuşmuyor",
                        want, conv.package
                    ));
                }
            }
            if let Some(want) = opts.version_code {
                if want != conv.version_code {
                    return Err(format!(
                        "--version-code {} ile APK sürümü {} uyuşmuyor",
                        want, conv.version_code
                    ));
                }
            }
            let identity = Identity {
                package: conv.package.clone(),
                version_code: conv.version_code,
                sha256: conv.sha256.clone(),
            };
            let hints = hints.or_else(|| find_pkg_sources(&opts.index, &conv.package));
            let rows = run_one(
                &opts,
                &identity,
                &conv.jar,
                &conv.package,
                &cat,
                hints.as_deref(),
                &engine_ids,
                &mut seen,
                &mut remaining,
                &tmp_root,
            )?;
            all_rows.extend(rows);
        }
        Mode::Packages { entries } => {
            for (i, e) in entries.iter().enumerate() {
                if matches!(remaining, Some(0)) {
                    break;
                }
                let apk = opts.apk_dir.join(&e.apk);
                if !apk.is_file() {
                    eprintln!("ATLANDI: {} (APK yok: {})", e.pkg, apk.display());
                    continue;
                }
                let jar = tmp_root.join(format!("{}-{}.jar", i, safe_name(&e.pkg)));
                let conv = convert_apk(&opts.java, &opts.app, &apk, &jar)?;
                if conv.package != e.pkg || conv.version_code != e.code {
                    return Err(format!(
                        "indeks ile APK uyuşmuyor: {} (idx {}/{}, apk {}/{})",
                        e.pkg, e.pkg, e.code, conv.package, conv.version_code
                    ));
                }
                let identity = Identity {
                    package: conv.package.clone(),
                    version_code: conv.version_code,
                    sha256: conv.sha256.clone(),
                };
                let rows = run_one(
                    &opts,
                    &identity,
                    &conv.jar,
                    &e.pkg,
                    &cat,
                    Some(&e.sources),
                    &engine_ids,
                    &mut seen,
                    &mut remaining,
                    &tmp_root,
                )?;
                all_rows.extend(rows);
            }
        }
    }

    if all_rows.is_empty() {
        return Err("test edilecek kaynak bulunamadı".to_string());
    }
    write_report(&opts.out, &all_rows)?;
    print_summary(&all_rows, &opts.out);
    let _ = std::fs::remove_dir_all(&tmp_root);
    Ok(())
}

fn write_report(out_path: &Path, rows: &[Row]) -> Result<(), String> {
    let mut csv = String::from(
        "paket,id,site,lang,nsfw,list,cover,details,chapters,pages,search,asama_hata,mesaj,sebep,eser\n",
    );
    for r in rows {
        csv.push_str(&format!(
            "{},{},{},{},{},{},{},{},{},{},{},{},{},{},{}\n",
            csv_escape(&r.package),
            r.id,
            csv_escape(&r.site),
            csv_escape(&r.lang),
            r.nsfw,
            csv_escape(&r.list),
            csv_escape(&r.cover),
            csv_escape(&r.details),
            csv_escape(&r.chapters),
            csv_escape(&r.pages),
            csv_escape(&r.search),
            csv_escape(&r.stage),
            csv_escape(&r.msg),
            csv_escape(&r.cause),
            csv_escape(&r.eser)
        ));
    }
    if let Some(parent) = out_path.parent() {
        if !parent.as_os_str().is_empty() {
            std::fs::create_dir_all(parent)
                .map_err(|e| format!("{} oluşturulamadı: {e}", parent.display()))?;
        }
    }
    std::fs::write(out_path, csv)
        .map_err(|e| format!("{} yazılamadı: {e}", out_path.display()))?;
    Ok(())
}

fn print_summary(rows: &[Row], out_path: &Path) {
    let harness: Vec<&Row> = rows.iter().filter(|r| r.stage == "harness").collect();
    let broken: Vec<&Row> = rows
        .iter()
        .filter(|r| !r.stage.is_empty() && r.stage != "harness")
        .collect();
    println!(
        "[sweep] {} kaynak: {} sağlam, {} bozuk, {} yerel harness dışı",
        rows.len(),
        rows.len() - broken.len() - harness.len(),
        broken.len(),
        harness.len()
    );

    let mut per_pkg: BTreeMap<&str, (usize, usize, usize)> = BTreeMap::new();
    for r in rows {
        let e = per_pkg.entry(r.package.as_str()).or_insert((0, 0, 0));
        e.0 += 1;
        if r.stage == "harness" {
            e.2 += 1;
        } else if !r.stage.is_empty() {
            e.1 += 1;
        }
    }
    println!("[sweep] paket bazında:");
    for (pkg, (total, bad, h)) in &per_pkg {
        println!(
            "  {:<58} {:>3} kaynak, {:>3} bozuk, {:>3} harness dışı",
            pkg, total, bad, h
        );
    }

    let mut stages: BTreeMap<&str, usize> = BTreeMap::new();
    for r in &broken {
        *stages.entry(r.stage.as_str()).or_insert(0) += 1;
    }
    if !stages.is_empty() {
        let line = stages
            .iter()
            .map(|(k, v)| format!("{k} {v}"))
            .collect::<Vec<_>>()
            .join(", ");
        println!("[sweep] gerçek hata adımları: {line}");
    }

    if !broken.is_empty() {
        println!("{:<28} {:<12} {}", "SITE", "ADIM", "MESAJ");
        for r in &broken {
            let msg: String = r.msg.chars().take(70).collect();
            println!("{:<28} {:<12} {}", r.site, r.stage, msg);
            if !r.cause.is_empty() && r.cause != msg {
                let cause: String = r.cause.chars().take(150).collect();
                println!("  sebep: {cause}");
            }
        }
    }
    if !harness.is_empty() {
        println!(
            "[sweep] {} kaynak yerel harness yüzünden kesin değil (engine ABI / Cloudflare köprüsü); CSV'de asama_hata=harness.",
            harness.len()
        );
    }
    println!("CSV: {}", out_path.display());
}
