//! `pulsar video-mega` — Aniyomi / CloudStream / JAR depolarını tek çatı
//! altında birleştirir.
//!
//! Girdi: `pulsar-video/mega-sources.json`
//!   {"aniyomi":[{name,url}], "cloudstream":[url...], "jar":[{name,index}]}
//!
//! Çıktılar (`--out`, varsayılan `pulsar-video`):
//! - `repo/index.min.json`  Aniyomi DİZİSİ; YALNIZ yerel kayıtlar (göreli
//!   `apk` taşıyanlar) yazılır. Uzak Aniyomi indeksleri birleştirilmez:
//!   Kototoro `apk` alanını DOSYA ADI kabul eder ve indirmeyi
//!   `<repo-kök>/apk/<apk>` olarak kurar (`ExtensionRepoService.kt:421-422`,
//!   `ExtensionInstallService.kt:96-101`); uzak kayıtların `apk` alanı çoğu
//!   zaman mutlak URL olduğundan birleşik indekste 404 üretir. Bu yüzden uzak
//!   kayıtlar yalnız SAYILIR ve `mega-report.json`'da
//!   "harici depo olarak eklenmeli" diye işaretlenir.
//!   `repo/repo.json` meta nesnesi zaten varsa AYNEN korunur, yoksa yazılır.
//! - `cs/repo.json`      CloudStream depo nesnesi; `pluginLists` tüm
//!   kaynaklardan toplanmış, mutlaklaştırılmış, tekilleştirilmiş listedir.
//! - `cs/plugins.json`   Tüm pluginLists'in birleşik plugin DİZİSİ; `pkg`
//!   (`internalName`) bazında en yüksek `version` kazanır, `url` mutlaktır.
//! - `jar/index.min.json` JAR indeksi; `apk` GÖRELİ dosya adı (`plugin.jar`).
//! - `jar/apk/<dosya>`   JAR'ın kendisi indirilir (yerelleştirme): Kototoro
//!   depo köküne `<repo>/apk/<apk>` isteği atar, uzak URL'yi bileşen olarak
//!   kabul etmez.
//! - `mega-report.json`  Atlanan kaynaklar (URL + hata) ve sayılar.
//!
//! Ağ erişimi `curl` alt süreciyle yapılır (depodaki diğer komutlarla aynı
//! yöntem); yeni bir HTTP bağımlılığı eklenmez. APK indirilmez; yalnız JAR
//! (tek dosya, ~1 MB) indirilir.

use serde_json::{json, Value};
use std::cmp::Ordering;
use std::collections::{BTreeMap, HashSet};
use std::path::Path;
use std::process::{Command, ExitCode};
use std::sync::atomic::{AtomicUsize, Ordering as AtomicOrdering};

const DEFAULT_SOURCES: &str = "pulsar-video/mega-sources.json";
const DEFAULT_OUT: &str = "pulsar-video";

const INDEX_FILE: &str = "index.min.json";
const REPO_META_FILE: &str = "repo.json";
const CS_PLUGINS_FILE: &str = "plugins.json";
const REPORT_FILE: &str = "mega-report.json";

const REPO_NAME: &str = "Pulsar Video";
const REPO_SHORT_NAME: &str = "Pulsar";
const REPO_WEBSITE: &str = "https://github.com/Pulsariums/pulsar-trmangahub";
const SIGNING_KEY_FINGERPRINT: &str =
    "55468803fc00aa073be9f40599d28644207688a447672934df661c57207b50f6";

const CS_REPO_NAME: &str = "Pulsar Video Mega";
const CS_REPO_DESCRIPTION: &str =
    "Aniyomi, CloudStream ve JAR depolarinin tek catida birlesimi (Pulsar Video).";

static FETCH_SEQ: AtomicUsize = AtomicUsize::new(0);

fn http_get(url: &str) -> Result<Vec<u8>, String> {
    let n = FETCH_SEQ.fetch_add(1, AtomicOrdering::SeqCst);
    let dir = std::env::temp_dir().join(format!("pulsar-mega-{}", std::process::id()));
    std::fs::create_dir_all(&dir).map_err(|e| format!("gecici dizin: {e}"))?;
    let dest = dir.join(format!("f{n}.json"));
    let status = Command::new("curl")
        .args(["-fsSL", "--retry", "2", "--max-time", "120", "-o"])
        .arg(&dest)
        .arg(url)
        .status()
        .map_err(|e| format!("curl calistirilamadi: {e}"))?;
    if !status.success() {
        let _ = std::fs::remove_file(&dest);
        return Err(format!("curl cikis kodu {:?}", status.code()));
    }
    let bytes = std::fs::read(&dest).map_err(|e| format!("okuma: {e}"))?;
    let _ = std::fs::remove_file(&dest);
    Ok(bytes)
}

fn fetch_json(url: &str) -> Result<Value, String> {
    let bytes = http_get(url)?;
    serde_json::from_slice(&bytes).map_err(|e| format!("JSON degil: {e}"))
}

/// Bir ikili dosyayi `dest`'e indirir; yazilan bayt sayisini dondurur.
fn http_download(url: &str, dest: &Path) -> Result<u64, String> {
    if let Some(parent) = dest.parent() {
        std::fs::create_dir_all(parent)
            .map_err(|e| format!("{} olusturulamadi: {e}", parent.display()))?;
    }
    let status = Command::new("curl")
        .args(["-fsSL", "--retry", "2", "--max-time", "300", "-o"])
        .arg(dest)
        .arg(url)
        .status()
        .map_err(|e| format!("curl calistirilamadi: {e}"))?;
    if !status.success() {
        let _ = std::fs::remove_file(dest);
        return Err(format!("curl cikis kodu {:?}", status.code()));
    }
    let size = std::fs::metadata(dest)
        .map_err(|e| format!("boyut okunamadi: {e}"))?
        .len();
    if size == 0 {
        let _ = std::fs::remove_file(dest);
        return Err("bos dosya indirildi".to_string());
    }
    Ok(size)
}

/// JAR `apk` alanini goreli dosya adina indirger: `plugin.jar`,
/// `apk/plugin.jar`, `https://host/x/apk/plugin.jar` -> `plugin.jar`.
fn jar_rel_name(apk: &str) -> String {
    apk.rsplit('/')
        .next()
        .unwrap_or(apk)
        .trim()
        .trim_start_matches("./")
        .to_string()
}

fn is_absolute(url: &str) -> bool {
    url.starts_with("http://") || url.starts_with("https://")
}

/// Bir URL'nin son dosyası atılmış hâli (`ExtensionRepoUrls` base kuralı).
fn base_of(url: &str) -> &str {
    url.rsplit_once('/').map(|(b, _)| b).unwrap_or(url)
}

/// Aniyomi `apk` alanı: göreliyse `<index-kök>/apk/<dosya>`.
fn resolve_apk(index_url: &str, apk: &str) -> String {
    if is_absolute(apk) {
        return apk.to_string();
    }
    let base = base_of(index_url);
    let rel = apk.trim_start_matches("./").trim_start_matches('/');
    if rel.starts_with("apk/") {
        format!("{base}/{rel}")
    } else {
        format!("{base}/apk/{rel}")
    }
}

/// CloudStream göreli yolu: repo/plug-list URL'sinin köküne göre mutlaklaştır.
fn resolve_any(base_url: &str, rel: &str) -> String {
    if is_absolute(rel) {
        return rel.to_string();
    }
    format!(
        "{}/{}",
        base_of(base_url),
        rel.trim_start_matches("./").trim_start_matches('/')
    )
}

fn write_json(path: &Path, value: &Value, pretty: bool) -> Result<(), String> {
    if let Some(parent) = path.parent() {
        std::fs::create_dir_all(parent)
            .map_err(|e| format!("{} olusturulamadi: {e}", parent.display()))?;
    }
    let text = if pretty {
        serde_json::to_string_pretty(value)
    } else {
        serde_json::to_string(value)
    }
    .map_err(|e| format!("serilestirme: {e}"))?;
    std::fs::write(path, format!("{text}\n"))
        .map_err(|e| format!("{} yazilamadi: {e}", path.display()))
}

fn valid_aniyomi(rec: &Value) -> bool {
    rec.get("pkg")
        .and_then(Value::as_str)
        .map(|s| !s.is_empty())
        .unwrap_or(false)
        && rec
            .get("apk")
            .and_then(Value::as_str)
            .map(|s| !s.is_empty())
            .unwrap_or(false)
        && rec
            .get("version")
            .map(|v| v.is_string() || v.is_number())
            .unwrap_or(false)
        && rec.get("code").and_then(Value::as_i64).is_some()
}

#[derive(Default)]
struct Step {
    records: usize,
    unique: usize,
    invalid: usize,
    sources_ok: usize,
    sources_total: usize,
    skipped: Vec<Value>,
}

fn aniyomi_step(out_repo: &Path, doc: &Value, dry: bool) -> Result<(Step, usize), String> {
    let sources = doc
        .get("aniyomi")
        .and_then(Value::as_array)
        .cloned()
        .unwrap_or_default();
    if sources.is_empty() {
        return Err("mega-sources.json icinde aniyomi listesi yok".to_string());
    }
    let mut st = Step {
        sources_total: sources.len(),
        ..Step::default()
    };
    let mut external: usize = 0;

    for src in &sources {
        let url = src.get("url").and_then(Value::as_str).unwrap_or("");
        let name = src
            .get("name")
            .and_then(Value::as_str)
            .unwrap_or(url)
            .to_string();
        if url.is_empty() {
            st.skipped
                .push(json!({"kind":"aniyomi","name":name,"url":"","error":"url yok"}));
            continue;
        }
        match fetch_json(url) {
            Ok(Value::Array(records)) => {
                st.sources_ok += 1;
                st.records += records.len();
                let mut valid = 0usize;
                for rec in records {
                    if !valid_aniyomi(&rec) {
                        st.invalid += 1;
                        continue;
                    }
                    valid += 1;
                    external += 1;
                    // Uzak kayit INDEKSE YAZILMAZ: Kototoro `apk` alanini dosya
                    // adi kabul edip `<repo-kok>/apk/<apk>` indirir; uzak
                    // kayitlarin apk'si mutlak URL'dir ve bu adres 404 olur.
                    st.skipped.push(json!({
                        "kind":"aniyomi",
                        "name": rec.get("name").and_then(Value::as_str).unwrap_or(""),
                        "pkg": rec.get("pkg").and_then(Value::as_str).unwrap_or(""),
                        "url": url,
                        "error":"harici depo olarak eklenmeli",
                    }));
                }
                println!("[aniyomi] harici {name}: {valid} kayit indekse yazilmadi");
            }
            Ok(_) => st.skipped.push(
                json!({"kind":"aniyomi","name":name,"url":url,"error":"kok dizi degil"}),
            ),
            Err(e) => st.skipped.push(
                json!({"kind":"aniyomi","name":name,"url":url,"error":e}),
            ),
        }
    }

    // Indekse YALNIZ yerel kayitlar girer (apk'si GORELI olanlar). Onceki
    // kosudan kalan mutlak-apk kayitlari atilir; onlar tam olarak Kototoro'da
    // 404 ureten birlesik kayitlardir.
    let index_path = out_repo.join(INDEX_FILE);
    let mut local: Vec<Value> = Vec::new();
    let mut seen_pkg: HashSet<String> = HashSet::new();
    if let Ok(text) = std::fs::read_to_string(&index_path) {
        if let Ok(Value::Array(arr)) = serde_json::from_str::<Value>(&text) {
            for rec in arr {
                let relative = rec
                    .get("apk")
                    .and_then(Value::as_str)
                    .map(|s| !is_absolute(s))
                    .unwrap_or(false);
                if !relative {
                    continue;
                }
                let pkg = rec
                    .get("pkg")
                    .and_then(Value::as_str)
                    .unwrap_or("")
                    .to_string();
                if pkg.is_empty() || !seen_pkg.insert(pkg) {
                    continue;
                }
                local.push(rec);
            }
        }
    }

    st.unique = local.len();
    if local.is_empty() {
        return Err("yerel kayit yok: once `pulsar video-repo` calistirilmali \
                    (repo/apk/<eklenti>.apk + goreli apk)"
            .to_string());
    }

    if !dry {
        write_json(&index_path, &Value::Array(local.clone()), false)?;
        // repo.json META NESNESİDİR; mevcut dosya varsa baytları korunur.
        let meta_path = out_repo.join(REPO_META_FILE);
        if !meta_path.exists() {
            let meta = json!({
                "index_v2": null,
                "meta": {
                    "name": REPO_NAME,
                    "shortName": REPO_SHORT_NAME,
                    "website": REPO_WEBSITE,
                    "signingKeyFingerprint": SIGNING_KEY_FINGERPRINT,
                },
            });
            write_json(&meta_path, &meta, true)?;
        }
    }

    println!(
        "[aniyomi] kaynak={}/{} okunan={} harici={} yazilan={} gecersiz={}",
        st.sources_ok, st.sources_total, st.records, external, st.unique, st.invalid
    );
    Ok((st, local.len()))
}

fn version_str(rec: &Value) -> String {
    match rec.get("version") {
        Some(Value::String(s)) => s.clone(),
        Some(other) => other.to_string(),
        None => String::new(),
    }
}

fn num_parts(v: &str) -> Vec<u64> {
    v.split(|c: char| !c.is_ascii_digit())
        .filter(|s| !s.is_empty())
        .filter_map(|s| s.parse::<u64>().ok())
        .collect()
}

fn ver_cmp(a: &str, b: &str) -> Ordering {
    let pa = num_parts(a);
    let pb = num_parts(b);
    if pa.is_empty() || pb.is_empty() {
        a.cmp(b)
    } else {
        pa.cmp(&pb)
    }
}

fn plugin_key(rec: &Value) -> String {
    for field in ["internalName", "url", "name"] {
        if let Some(s) = rec.get(field).and_then(Value::as_str) {
            if !s.is_empty() {
                return s.to_string();
            }
        }
    }
    String::new()
}

fn cs_step(out_cs: &Path, doc: &Value, dry: bool) -> Result<(usize, Step), String> {
    let sources = doc
        .get("cloudstream")
        .and_then(Value::as_array)
        .cloned()
        .unwrap_or_default();
    if sources.is_empty() {
        return Err("mega-sources.json icinde cloudstream listesi yok".to_string());
    }
    let mut st = Step {
        sources_total: sources.len(),
        ..Step::default()
    };
    let mut lists: Vec<String> = Vec::new();
    let mut seen_lists: HashSet<String> = HashSet::new();

    for src in &sources {
        let url = src
            .as_str()
            .or_else(|| src.get("url").and_then(Value::as_str))
            .unwrap_or("");
        if url.is_empty() {
            st.skipped
                .push(json!({"kind":"cloudstream","name":"","url":"","error":"url yok"}));
            continue;
        }
        match fetch_json(url) {
            Ok(v) => {
                let Some(arr) = v.get("pluginLists").and_then(Value::as_array) else {
                    st.skipped.push(json!({
                        "kind":"cloudstream","name":"","url":url,
                        "error":"pluginLists dizisi yok"
                    }));
                    continue;
                };
                let mut added = 0usize;
                for pl in arr {
                    let Some(pl) = pl.as_str() else { continue };
                    let abs = resolve_any(url, pl);
                    if seen_lists.insert(abs.clone()) {
                        lists.push(abs);
                        added += 1;
                    }
                }
                if added > 0 {
                    st.sources_ok += 1;
                } else {
                    st.skipped.push(json!({
                        "kind":"cloudstream","name":"","url":url,
                        "error":"eklenti listesi yok"
                    }));
                }
            }
            Err(e) => st.skipped.push(
                json!({"kind":"cloudstream","name":"","url":url,"error":e}),
            ),
        }
    }

    let mut plugins: BTreeMap<String, Value> = BTreeMap::new();
    for list_url in &lists {
        match fetch_json(list_url) {
            Ok(Value::Array(items)) => {
                st.records += items.len();
                for rec in items {
                    if !rec.is_object() {
                        st.invalid += 1;
                        continue;
                    }
                    let mut rec = rec;
                    if let Some(u) = rec.get("url").and_then(Value::as_str).map(str::to_string) {
                        if !is_absolute(&u) {
                            if let Some(obj) = rec.as_object_mut() {
                                obj.insert("url".to_string(), Value::String(resolve_any(list_url, &u)));
                            }
                        }
                    }
                    let key = plugin_key(&rec);
                    if key.is_empty() {
                        st.invalid += 1;
                        continue;
                    }
                    let ver = version_str(&rec);
                    let replace = match plugins.get(&key) {
                        Some(prev) => ver_cmp(&version_str(prev), &ver) == Ordering::Less,
                        None => true,
                    };
                    if replace {
                        plugins.insert(key, rec);
                    }
                }
            }
            Ok(_) => st.skipped.push(json!({
                "kind":"cloudstream","name":list_url,"url":list_url,
                "error":"plugin listesi dizi degil"
            })),
            Err(e) => st.skipped.push(json!({
                "kind":"cloudstream","name":list_url,"url":list_url,"error":e
            })),
        }
    }

    st.unique = plugins.len();
    if st.unique == 0 {
        return Err("cloudstream birlestirmesi bos".to_string());
    }

    if !dry {
        let merged: Vec<Value> = plugins.into_values().collect();
        write_json(&out_cs.join(CS_PLUGINS_FILE), &Value::Array(merged), false)?;
        let repo = json!({
            "name": CS_REPO_NAME,
            "description": CS_REPO_DESCRIPTION,
            "manifestVersion": 1,
            "pluginLists": lists,
        });
        write_json(&out_cs.join(REPO_META_FILE), &repo, true)?;
    }

    println!(
        "[cloudstream] kaynak={}/{} liste={} plugin={} tekil={} gecersiz={}",
        st.sources_ok,
        st.sources_total,
        lists.len(),
        st.records,
        st.unique,
        st.invalid
    );
    Ok((lists.len(), st))
}

fn jar_step(out_jar: &Path, doc: &Value, dry: bool) -> (usize, usize, Vec<Value>) {
    let sources = doc
        .get("jar")
        .and_then(Value::as_array)
        .cloned()
        .unwrap_or_default();
    let mut map: BTreeMap<String, Value> = BTreeMap::new();
    let mut skipped: Vec<Value> = Vec::new();
    let mut ok = 0usize;
    let mut downloaded = 0usize;
    let mut bytes = 0u64;

    for src in &sources {
        let url = src
            .get("index")
            .and_then(Value::as_str)
            .or_else(|| src.get("url").and_then(Value::as_str))
            .unwrap_or("");
        let name = src
            .get("name")
            .and_then(Value::as_str)
            .unwrap_or(url)
            .to_string();
        if url.is_empty() {
            skipped.push(json!({"kind":"jar","name":name,"url":"","error":"index yok"}));
            continue;
        }
        match fetch_json(url) {
            Ok(Value::Array(items)) => {
                ok += 1;
                for rec in items {
                    if !rec.is_object() {
                        continue;
                    }
                    let mut rec = rec;
                    let key = rec
                        .get("pkg")
                        .and_then(Value::as_str)
                        .unwrap_or("")
                        .to_string();
                    if key.is_empty() {
                        continue;
                    }
                    let apk = rec
                        .get("apk")
                        .and_then(Value::as_str)
                        .unwrap_or("")
                        .to_string();
                    // Goreli ad: Kototoro `<repo-kok>/apk/<apk>` ister.
                    let rel = jar_rel_name(&apk);
                    if rel.is_empty() || rel == "." || rel == ".." || rel.contains("..") {
                        skipped.push(json!({
                            "kind":"jar","name":name,"url":url,"error":"apk adi gecersiz"
                        }));
                        continue;
                    }
                    let code = rec.get("code").and_then(Value::as_i64).unwrap_or(i64::MIN);
                    let replace = match map.get(&key) {
                        Some(prev) => {
                            prev.get("code").and_then(Value::as_i64).unwrap_or(i64::MIN) < code
                        }
                        None => true,
                    };
                    if !replace {
                        continue;
                    }
                    // Dosyayi YERELLEŞTİR: uzak URL bileşen olarak kullanılamaz.
                    if !dry {
                        let src_url = resolve_apk(url, &apk);
                        match http_download(&src_url, &out_jar.join("apk").join(&rel)) {
                            Ok(n) => {
                                downloaded += 1;
                                bytes += n;
                            }
                            Err(e) => {
                                skipped.push(json!({
                                    "kind":"jar","name":name,"url":src_url,"error":e
                                }));
                                continue;
                            }
                        }
                    }
                    if let Some(obj) = rec.as_object_mut() {
                        obj.insert("apk".to_string(), Value::String(rel));
                    }
                    map.insert(key, rec);
                }
            }
            Ok(_) => skipped.push(json!({
                "kind":"jar","name":name,"url":url,"error":"kok dizi degil"
            })),
            Err(e) => skipped.push(json!({"kind":"jar","name":name,"url":url,"error":e})),
        }
    }

    let unique = map.len();
    if unique > 0 && !dry {
        let merged: Vec<Value> = map.into_values().collect();
        if let Err(e) = write_json(&out_jar.join(INDEX_FILE), &Value::Array(merged), false) {
            skipped.push(json!({"kind":"jar","name":"","url":"","error":e}));
            return (ok, 0, skipped);
        }
    }
    println!(
        "[jar] kaynak={}/{} kayit={} indirilen={} bayt={}",
        ok,
        sources.len(),
        unique,
        downloaded,
        bytes
    );
    (ok, unique, skipped)
}

pub fn run(root: &Path, argv: &[String]) -> ExitCode {
    let mut sources: Option<String> = None;
    let mut out: Option<String> = None;
    let mut dry = false;
    let mut i = 0;
    while i < argv.len() {
        match argv[i].as_str() {
            "--sources" => {
                i += 1;
                match argv.get(i) {
                    Some(v) => sources = Some(v.clone()),
                    None => {
                        eprintln!("HATA: --sources icin dosya yolu gerekli");
                        return ExitCode::from(64);
                    }
                }
            }
            "--out" => {
                i += 1;
                match argv.get(i) {
                    Some(v) => out = Some(v.clone()),
                    None => {
                        eprintln!("HATA: --out icin dizin gerekli");
                        return ExitCode::from(64);
                    }
                }
            }
            "--dry-run" => dry = true,
            other => {
                eprintln!("HATA: bilinmeyen arguman: {other}");
                return ExitCode::from(64);
            }
        }
        i += 1;
    }

    let sources_path = root.join(sources.unwrap_or_else(|| DEFAULT_SOURCES.to_string()));
    let out_dir = root.join(out.unwrap_or_else(|| DEFAULT_OUT.to_string()));

    let doc: Value = match std::fs::read_to_string(&sources_path) {
        Ok(t) => match serde_json::from_str(&t) {
            Ok(v) => v,
            Err(e) => {
                eprintln!("HATA: {} gecersiz JSON: {e}", sources_path.display());
                return ExitCode::FAILURE;
            }
        },
        Err(e) => {
            eprintln!("HATA: {} okunamadi: {e}", sources_path.display());
            return ExitCode::FAILURE;
        }
    };

    println!("[kaynak] {}", sources_path.display());

    let mut fatal: Option<String> = None;
    let mut skipped: Vec<Value> = Vec::new();

    // 1) ANIYOMI
    match aniyomi_step(&out_dir.join("repo"), &doc, dry) {
        Ok((st, _local)) => skipped.extend(st.skipped),
        Err(e) => {
            eprintln!("HATA: aniyomi: {e}");
            fatal = Some(format!("aniyomi: {e}"));
        }
    }

    // 2) CLOUDSTREAM
    match cs_step(&out_dir.join("cs"), &doc, dry) {
        Ok((_, st)) => skipped.extend(st.skipped),
        Err(e) => {
            eprintln!("HATA: cloudstream: {e}");
            if fatal.is_none() {
                fatal = Some(format!("cloudstream: {e}"));
            }
        }
    }

    // 3) JAR
    let (_, _, jar_skipped) = jar_step(&out_dir.join("jar"), &doc, dry);
    skipped.extend(jar_skipped);

    println!("[atlanan] {}", skipped.len());
    if dry {
        println!("[dry]  yazilacak: {}/repo/{INDEX_FILE}", out_dir.display());
        println!("[dry]  yazilacak: {}/repo/{REPO_META_FILE} (yoksa)", out_dir.display());
        println!("[dry]  yazilacak: {}/cs/{REPO_META_FILE}", out_dir.display());
        println!("[dry]  yazilacak: {}/cs/{CS_PLUGINS_FILE}", out_dir.display());
        println!("[dry]  yazilacak: {}/jar/{INDEX_FILE}", out_dir.display());
        println!("[dry]  indirilecek: {}/jar/apk/<dosya>", out_dir.display());
        println!("[dry]  yazilacak: {}/{REPORT_FILE}", out_dir.display());
        return ExitCode::SUCCESS;
    }

    let mut summary = json!({
        "skipped": skipped,
    });
    if let Some(err) = &fatal {
        summary["fatal"] = Value::String(err.clone());
    }
    if let Err(e) = write_json(&out_dir.join(REPORT_FILE), &summary, true) {
        eprintln!("HATA: rapor yazilamadi: {e}");
        return ExitCode::FAILURE;
    }

    match fatal {
        Some(e) => {
            eprintln!("HATA: {e}");
            ExitCode::FAILURE
        }
        None => ExitCode::SUCCESS,
    }
}
