//! `pulsar video-repo` — Aniyomi deposu (index + APK kopyası) üretimi.
//!
//! Girdi: `pulsar-video/extension/build/outputs/apk/**/*.apk` (ya da `--apk-dir`;
//! alt dizinler de taranır — `standart/release` + `adult/release`).
//! Her APK'nın ikili `AndroidManifest.xml` (AXML) dosyası okunur; paket adı,
//! versionName/versionCode, `tachiyomi.animeextension.*` meta verileri çıkarılır.
//!
//! Çıktı: `<out>/apk/<paket>.apk` kopyaları, `<out>/index.min.json` (eklenti
//! DİZİSİ) ve `<out>/repo.json` (depo META NESNESİ). İki dosya farklı şemadır;
//! aynı baytları taşıyamazlar:
//!
//! - `index.min.json` Aniyomi'nin yayınladığı biçimdir: kök bir DİZİ, her öğe
//!   {name, pkg, apk, lang, code, version, nsfw, sources}. Ek alan yazılmaz:
//!   Aniyomi indeksi bu 8 anahtarla ayrıştırır. Kototoro eklenti listesini
//!   `"${repo.baseUrl}/index.min.json"` adresinden bu biçimde çeker.
//!   `sources` boş kalırsa Kototoro "0 etkin kaynak" gösterir ve kurulum
//!   yapılmaz. Kaynaklar paket türüne göre iki dosyadan doldurulur:
//!   - `--sources` (varsayılan `pulsar-video/data/video-sources.json`):
//!     kototoro-parsers enum'undan çıkarılmış `video` / `hentai_video` adları.
//!   - `--catalogue` (varsayılan `pulsar-video/data/video-catalogue.json`):
//!     yalnız `config` nesnesi BOŞ OLMAYAN, parser OLMAYAN kaynaklar; bunlar
//!     iki pakette de bulunur (GogoAnime/AniWorld).
//!   Normal paket (`nsfw=0`) = config + `video`; 18+ paket (`nsfw=1`) =
//!   `hentai_video`. DTO alanları `{"name": <zorunlu>, "lang": <opsiyonel>}` —
//!   `id` yazılmaz.
//! - `repo.json` Kototoro `fetchRepoDetails`'ın İLK denediği adrestir ve gövdeyi
//!   `RepoMetaWrapperDto` olarak ayrıştırır: {"index_v2": null, "meta": {name,
//!   shortName, website, signingKeyFingerprint}}. Başarısız olursa `index.pb`ye
//!   düşer (bu depoda yok) → kullanıcı depo eklerken hata alır. Bu yüzden
//!   `repo.json` asla dizi değil, bu nesne olmalıdır.
//! - `index.json` ve `plugins.json` ÜRETİLMEZ: `plugins.json` Cloudstream'in
//!   adıdır, `index.json` gereksizdir. Eski çıktılarda kalmışlarsa silinirler.
//!
//! Manga tarafında AXML okuyan kod yoktu (grep: tools/pulsar/src/*.rs içinde
//! AndroidManifest geçmiyor); ayrıştırıcı burada, bağımlılık yalnız `zip`
//! (deflate) — kabuk aracı (unzip/aapt) çağrılmaz.

use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::path::{Path, PathBuf};
use std::process::ExitCode;

const DEFAULT_APK_DIR: &str = "pulsar-video/extension/build/outputs/apk";
const DEFAULT_OUT: &str = "pulsar-video/repo";
const DEFAULT_CATALOGUE: &str = "pulsar-video/data/video-catalogue.json";
const DEFAULT_SOURCES: &str = "pulsar-video/data/video-sources.json";

/// Eklenti listesi (kök DİZİ). Kototoro/Aniyomi `"${repo.baseUrl}/index.min.json"`
/// adresinden çeker.
const INDEX_FILE: &str = "index.min.json";

/// Depo meta verisi (kök NESNE). Kototoro `fetchRepoDetails` önce bunu çeker ve
/// `RepoMetaWrapperDto` olarak ayrıştırır; ayrıştırma başarısızsa `index.pb`ye
/// düşer (bu depoda yok) → "depo eklenemedi" hatası.
const REPO_META_FILE: &str = "repo.json";

/// Artık üretilmeyen adlar. Eski çıktılarda kalırlarsa yanlış (dizi) baytlarla
/// yayında kalırlar; üretim sırasında silinirler.
const LEGACY_FILE_NAMES: [&str; 2] = ["index.json", "plugins.json"];

/// `repo.json` meta alanları. Manga deposunun (`pulsar-v2/repo/repo.json`)
/// yayındaki değerleriyle aynı imza parmak izi kullanılır.
const REPO_NAME: &str = "Pulsar Video";
const REPO_SHORT_NAME: &str = "Pulsar";
const REPO_WEBSITE: &str = "https://github.com/Pulsariums/pulsar-trmangahub";
const SIGNING_KEY_FINGERPRINT: &str =
    "55468803fc00aa073be9f40599d28644207688a447672934df661c57207b50f6";

#[derive(Default, Debug)]
struct ManifestInfo {
    package: Option<String>,
    version_name: Option<String>,
    version_code: Option<i64>,
    label: Option<String>,
    /// `tachiyomi.animeextension.*` meta-data çiftleri (name -> value).
    meta: Vec<(String, String)>,
}

impl ManifestInfo {
    fn meta(&self, key: &str) -> Option<&str> {
        self.meta
            .iter()
            .find(|(k, _)| k == key)
            .map(|(_, v)| v.as_str())
    }
}

#[derive(Debug)]
struct ApkInfo {
    path: PathBuf,
    package: String,
    version_name: String,
    version_code: i64,
    lang: String,
    nsfw: u8,
    name: String,
    class: Option<String>,
    factory: Option<String>,
    sha256: String,
    bytes: u64,
}

/// Aniyomi paket adı `eu.kanade.tachiyomi.animeextension.<lang>.<ad>` biçimindedir.
fn lang_from_package(pkg: &str) -> String {
    let parts: Vec<&str> = pkg.split('.').collect();
    if let Some(i) = parts.iter().position(|p| *p == "animeextension") {
        if let Some(lang) = parts.get(i + 1) {
            if !lang.is_empty() {
                return (*lang).to_string();
            }
        }
    }
    "all".to_string()
}

fn name_from_package(pkg: &str) -> String {
    pkg.rsplit('.')
        .next()
        .filter(|s| !s.is_empty())
        .unwrap_or(pkg)
        .to_string()
}

/// APK'ları alt dizinlerle birlikte toplar (flavor çıktıları
/// `apk/standart/release` ve `apk/adult/release` altındadır).
fn collect_apks(dir: &Path, out: &mut Vec<PathBuf>) -> std::io::Result<()> {
    for entry in std::fs::read_dir(dir)? {
        let path = entry?.path();
        if path.is_dir() {
            collect_apks(&path, out)?;
        } else if path.extension().and_then(|x| x.to_str()) == Some("apk") {
            out.push(path);
        }
    }
    Ok(())
}

pub fn run(root: &Path, argv: &[String]) -> ExitCode {
    let mut apk_dir: Option<String> = None;
    let mut out: Option<String> = None;
    let mut catalogue: Option<String> = None;
    let mut sources_file: Option<String> = None;
    let mut dry = false;
    let mut i = 0;
    while i < argv.len() {
        match argv[i].as_str() {
            "--apk-dir" => {
                i += 1;
                match argv.get(i) {
                    Some(v) => apk_dir = Some(v.clone()),
                    None => {
                        eprintln!("HATA: --apk-dir için dizin gerekli");
                        return ExitCode::from(64);
                    }
                }
            }
            "--catalogue" => {
                i += 1;
                match argv.get(i) {
                    Some(v) => catalogue = Some(v.clone()),
                    None => {
                        eprintln!("HATA: --catalogue için dosya yolu gerekli");
                        return ExitCode::from(64);
                    }
                }
            }
            "--sources" => {
                i += 1;
                match argv.get(i) {
                    Some(v) => sources_file = Some(v.clone()),
                    None => {
                        eprintln!("HATA: --sources için dosya yolu gerekli");
                        return ExitCode::from(64);
                    }
                }
            }
            "--out" => {
                i += 1;
                match argv.get(i) {
                    Some(v) => out = Some(v.clone()),
                    None => {
                        eprintln!("HATA: --out için dizin gerekli");
                        return ExitCode::from(64);
                    }
                }
            }
            "--dry-run" => dry = true,
            other => {
                eprintln!("HATA: bilinmeyen argüman: {other}");
                return ExitCode::from(64);
            }
        }
        i += 1;
    }

    let apk_dir = root.join(apk_dir.unwrap_or_else(|| DEFAULT_APK_DIR.to_string()));
    let out = root.join(out.unwrap_or_else(|| DEFAULT_OUT.to_string()));
    let catalogue = root.join(catalogue.unwrap_or_else(|| DEFAULT_CATALOGUE.to_string()));
    let sources_file = root.join(sources_file.unwrap_or_else(|| DEFAULT_SOURCES.to_string()));

    let mut apks: Vec<PathBuf> = Vec::new();
    if let Err(e) = collect_apks(&apk_dir, &mut apks) {
        eprintln!("HATA: APK dizini okunamadı ({}): {e}", apk_dir.display());
        return ExitCode::FAILURE;
    }
    apks.sort();
    if apks.is_empty() {
        eprintln!("HATA: {} içinde APK yok", apk_dir.display());
        return ExitCode::FAILURE;
    }

    let mut infos: Vec<ApkInfo> = Vec::new();
    let mut failures = 0usize;
    for apk in &apks {
        match inspect_apk(apk) {
            Ok(info) => {
                println!(
                    "[apk] {:<64} pkg={} version={} ({}) lang={} nsfw={} sha256={} bytes={}",
                    apk.file_name().unwrap_or_default().to_string_lossy(),
                    info.package,
                    info.version_name,
                    info.version_code,
                    info.lang,
                    info.nsfw,
                    info.sha256,
                    info.bytes
                );
                println!(
                    "      class={} factory={}",
                    info.class.as_deref().unwrap_or("—"),
                    info.factory.as_deref().unwrap_or("—")
                );
                infos.push(info);
            }
            Err(e) => {
                failures += 1;
                eprintln!("[fail] {}: {e}", apk.display());
            }
        }
    }
    if failures > 0 {
        eprintln!("HATA: {failures} APK okunamadı");
        return ExitCode::FAILURE;
    }
    infos.sort_by(|a, b| a.package.cmp(&b.package));

    // `sources` indeksten gelir; boş dizi Kototoro'da "0 etkin kaynak" demektir.
    // Config kaynakları (GogoAnime/AniWorld) iki pakette de bulunur.
    let config_sources = match load_catalogue_sources(&catalogue) {
        Ok(s) => s,
        Err(e) => {
            eprintln!("HATA: katalog okunamadı ({}): {e}", catalogue.display());
            return ExitCode::FAILURE;
        }
    };
    let (video_sources, hentai_sources) = match load_parser_sources(&sources_file) {
        Ok(s) => s,
        Err(e) => {
            eprintln!("HATA: kaynak listesi okunamadı ({}): {e}", sources_file.display());
            return ExitCode::FAILURE;
        }
    };
    println!(
        "[kaynak] config={} video={} hentai_video={} (katalog: {}, parser: {})",
        config_sources.len(),
        video_sources.len(),
        hentai_sources.len(),
        catalogue.display(),
        sources_file.display()
    );

    let entries: Vec<Value> = infos
        .iter()
        .map(|info| {
            let sources = if info.nsfw == 1 {
                hentai_sources.clone()
            } else {
                let mut list = config_sources.clone();
                list.extend(video_sources.iter().cloned());
                list
            };
            json!({
                "name": info.name,
                "pkg": info.package,
                "apk": format!("{}.apk", info.package),
                "lang": info.lang,
                "code": info.version_code,
                "version": info.version_name,
                "nsfw": info.nsfw,
                "sources": sources,
            })
        })
        .collect();
    let index = Value::Array(entries);
    let text = serde_json::to_string(&index).map_err(|e| e.to_string());

    let text = match text {
        Ok(t) => t,
        Err(e) => {
            eprintln!("HATA: index üretilemedi: {e}");
            return ExitCode::FAILURE;
        }
    };

    let repo_meta = json!({
        "index_v2": null,
        "meta": {
            "name": REPO_NAME,
            "shortName": REPO_SHORT_NAME,
            "website": REPO_WEBSITE,
            "signingKeyFingerprint": SIGNING_KEY_FINGERPRINT,
        },
    });
    let meta_text = match serde_json::to_string_pretty(&repo_meta) {
        Ok(t) => t,
        Err(e) => {
            eprintln!("HATA: repo.json üretilemedi: {e}");
            return ExitCode::FAILURE;
        }
    };

    println!("[index] {} uzantı", infos.len());
    println!("{text}");
    println!("[repo] {REPO_NAME} ({REPO_SHORT_NAME}) imza={SIGNING_KEY_FINGERPRINT}");

    if dry {
        for info in &infos {
            println!(
                "[dry]  kopyalanacak: {} -> {}/apk/{}.apk",
                info.path.file_name().unwrap_or_default().to_string_lossy(),
                out.display(),
                info.package
            );
        }
        println!("[dry]  yazılacak: {}/{INDEX_FILE}", out.display());
        println!("[dry]  yazılacak: {}/{REPO_META_FILE}", out.display());
        for name in LEGACY_FILE_NAMES {
            println!("[dry]  silinecek (varsa): {}/{name}", out.display());
        }
        return ExitCode::SUCCESS;
    }

    let apk_out = out.join("apk");
    if let Err(e) = std::fs::create_dir_all(&apk_out) {
        eprintln!("HATA: {} oluşturulamadı: {e}", apk_out.display());
        return ExitCode::FAILURE;
    }
    // Kendi ürettiğimiz APK'lar dışında eskiler kalmasın: paket listesi değişirse
    // depoda imzasız/artık APK kalması Aniyomi'de "bozuk güncelleme" gösterir.
    if let Ok(rd) = std::fs::read_dir(&apk_out) {
        let keep: Vec<String> = infos.iter().map(|i| format!("{}.apk", i.package)).collect();
        for entry in rd.filter_map(|e| e.ok()) {
            let name = entry.file_name().to_string_lossy().to_string();
            if name.ends_with(".apk") && !keep.contains(&name) {
                let _ = std::fs::remove_file(entry.path());
                println!("[temiz] eski APK silindi: {name}");
            }
        }
    }
    for info in &infos {
        let dest = apk_out.join(format!("{}.apk", info.package));
        if let Err(e) = std::fs::copy(&info.path, &dest) {
            eprintln!("HATA: {} kopyalanamadı: {e}", dest.display());
            return ExitCode::FAILURE;
        }
    }
    // İki dosya iki ayrı şema: index DİZİ, repo.json NESNE.
    let index_path = out.join(INDEX_FILE);
    if let Err(e) = std::fs::write(&index_path, format!("{text}\n")) {
        eprintln!("HATA: {} yazılamadı: {e}", index_path.display());
        return ExitCode::FAILURE;
    }
    let meta_path = out.join(REPO_META_FILE);
    if let Err(e) = std::fs::write(&meta_path, format!("{meta_text}\n")) {
        eprintln!("HATA: {} yazılamadı: {e}", meta_path.display());
        return ExitCode::FAILURE;
    }
    for name in LEGACY_FILE_NAMES {
        let stale = out.join(name);
        if stale.exists() {
            match std::fs::remove_file(&stale) {
                Ok(()) => println!("[temiz] eski dosya silindi: {name}"),
                Err(e) => {
                    eprintln!("HATA: {} silinemedi: {e}", stale.display());
                    return ExitCode::FAILURE;
                }
            }
        }
    }
    println!(
        "[ok] {} APK + {INDEX_FILE} (dizi) + {REPO_META_FILE} (meta nesnesi)",
        infos.len()
    );
    ExitCode::SUCCESS
}

/// Katalogdan **config tabanlı** `sources` DTO'larını üretir (iki pakette de).
///
/// Kural: parser OLMAYAN ve `config` nesnesi **boş olmayan** kayıtlar alınır.
/// `config` boş/eksik kayıt ölçülmemiş demektir; eklentide çalışmaz, sayıyı da
/// şişirir. Parser kaynakları `video-sources.json`'dan gelir; burada tekrar
/// yazılmaz (aksi hâlde 18+ pakete sızarlar).
fn load_catalogue_sources(path: &Path) -> Result<Vec<Value>, String> {
    let text = match std::fs::read_to_string(path) {
        Ok(t) => t,
        Err(e) if e.kind() == std::io::ErrorKind::NotFound => {
            eprintln!(
                "UYARI: katalog yok ({}); sources boş yazılacak",
                path.display()
            );
            return Ok(Vec::new());
        }
        Err(e) => return Err(format!("okunamadı: {e}")),
    };
    let doc: Value = serde_json::from_str(&text).map_err(|e| format!("geçersiz JSON: {e}"))?;
    let records = doc
        .get("sources")
        .and_then(Value::as_array)
        .ok_or_else(|| "kök nesnede sources dizisi yok".to_string())?;

    let mut out = Vec::new();
    for rec in records {
        if rec.get("engine").and_then(Value::as_str) == Some("parser") {
            continue;
        }
        let config_nonempty = rec
            .get("config")
            .and_then(Value::as_object)
            .map(|c| !c.is_empty())
            .unwrap_or(false);
        if !config_nonempty {
            continue;
        }
        let name = match rec.get("name").and_then(Value::as_str) {
            Some(n) if !n.is_empty() => n,
            _ => {
                eprintln!("UYARI: config'i dolu ama name'i yok kayıt atlandı");
                continue;
            }
        };
        let mut src = serde_json::Map::new();
        src.insert("name".to_string(), Value::String(name.to_string()));
        if let Some(lang) = rec.get("lang").and_then(Value::as_str) {
            if !lang.is_empty() {
                src.insert("lang".to_string(), Value::String(lang.to_string()));
            }
        }
        out.push(Value::Object(src));
    }
    Ok(out)
}

/// `video-sources.json`'dan `(video, hentai_video)` DTO listelerini üretir.
///
/// Dosya yoksa iki liste de boş döner (uydurma yok); bozuk JSON hata sayılır.
/// Öğeler `{"name","lang"}` nesnesi ya da düz ad string'i olabilir.
fn load_parser_sources(path: &Path) -> Result<(Vec<Value>, Vec<Value>), String> {
    let text = match std::fs::read_to_string(path) {
        Ok(t) => t,
        Err(e) if e.kind() == std::io::ErrorKind::NotFound => {
            eprintln!(
                "UYARI: parser kaynak listesi yok ({}); parser sources boş yazılacak",
                path.display()
            );
            return Ok((Vec::new(), Vec::new()));
        }
        Err(e) => return Err(format!("okunamadı: {e}")),
    };
    let doc: Value = serde_json::from_str(&text).map_err(|e| format!("geçersiz JSON: {e}"))?;
    Ok((
        parse_source_list(doc.get("video")),
        parse_source_list(doc.get("hentai_video")),
    ))
}

fn parse_source_list(value: Option<&Value>) -> Vec<Value> {
    let Some(items) = value.and_then(Value::as_array) else {
        return Vec::new();
    };
    let mut out = Vec::new();
    for item in items {
        let mut src = serde_json::Map::new();
        match item {
            Value::String(name) if !name.is_empty() => {
                src.insert("name".to_string(), Value::String(name.clone()));
            }
            Value::Object(obj) => {
                let Some(name) = obj.get("name").and_then(Value::as_str) else {
                    eprintln!("UYARI: parser kaynağında name yok, atlandı");
                    continue;
                };
                if name.is_empty() {
                    continue;
                }
                src.insert("name".to_string(), Value::String(name.to_string()));
                if let Some(lang) = obj.get("lang").and_then(Value::as_str) {
                    if !lang.is_empty() {
                        src.insert("lang".to_string(), Value::String(lang.to_string()));
                    }
                }
            }
            _ => continue,
        }
        out.push(Value::Object(src));
    }
    out
}

fn inspect_apk(path: &Path) -> Result<ApkInfo, String> {
    let manifest = read_manifest(path)?;
    let m = parse_manifest(&manifest)?;
    let package = m
        .package
        .clone()
        .ok_or_else(|| "manifestte package yok".to_string())?;
    let version_name = m
        .version_name
        .clone()
        .ok_or_else(|| "manifestte versionName yok".to_string())?;
    let version_code = m
        .version_code
        .ok_or_else(|| "manifestte versionCode yok".to_string())?;
    let lang = lang_from_package(&package);
    let nsfw = m
        .meta("tachiyomi.animeextension.nsfw")
        .and_then(|v| v.trim().parse::<u8>().ok())
        .unwrap_or(0);
    let name = m
        .label
        .clone()
        .filter(|s| !s.is_empty())
        .unwrap_or_else(|| name_from_package(&package));

    let bytes = std::fs::read(path).map_err(|e| format!("okunamadı: {e}"))?;
    let digest = Sha256::digest(&bytes);
    Ok(ApkInfo {
        path: path.to_path_buf(),
        package,
        version_name,
        version_code,
        lang,
        nsfw,
        name,
        class: m
            .meta("tachiyomi.animeextension.class")
            .map(str::to_string),
        factory: m
            .meta("tachiyomi.animeextension.factory")
            .map(str::to_string),
        sha256: format!("{digest:x}"),
        bytes: bytes.len() as u64,
    })
}

fn read_manifest(apk: &Path) -> Result<Vec<u8>, String> {
    let file = std::fs::File::open(apk).map_err(|e| format!("APK açılamadı: {e}"))?;
    let mut za = zip::ZipArchive::new(file).map_err(|e| format!("APK (zip) açılamadı: {e}"))?;
    let mut entry = za
        .by_name("AndroidManifest.xml")
        .map_err(|e| format!("AndroidManifest.xml yok: {e}"))?;
    let mut buf = Vec::new();
    std::io::Read::read_to_end(&mut entry, &mut buf)
        .map_err(|e| format!("AndroidManifest.xml okunamadı: {e}"))?;
    Ok(buf)
}

fn rd16(d: &[u8], o: usize) -> u16 {
    u16::from_le_bytes([d[o], d[o + 1]])
}

fn rd32(d: &[u8], o: usize) -> u32 {
    u32::from_le_bytes([d[o], d[o + 1], d[o + 2], d[o + 3]])
}

#[derive(Debug, Clone)]
enum AttrValue {
    Str(String),
    Int(i64),
    Unknown,
}

impl AttrValue {
    fn as_str(&self) -> Option<&str> {
        match self {
            AttrValue::Str(s) if !s.is_empty() => Some(s),
            _ => None,
        }
    }
    fn as_i64(&self) -> Option<i64> {
        match self {
            AttrValue::Int(i) => Some(*i),
            AttrValue::Str(s) => s.trim().parse::<i64>().ok(),
            AttrValue::Unknown => None,
        }
    }
}

/// AXML string pool'unu çözer (UTF-8 ve UTF-16 havuzları).
fn parse_string_pool(d: &[u8], start: usize, end: usize) -> Vec<String> {
    if start + 28 > end {
        return Vec::new();
    }
    let header_size = rd16(d, start + 2) as usize;
    let count = rd32(d, start + 8) as usize;
    let flags = rd32(d, start + 16);
    let strings_start = rd32(d, start + 20) as usize;
    let utf8 = flags & 0x100 != 0;
    let mut out = Vec::with_capacity(count.min(4096));
    for i in 0..count {
        let off_pos = start + header_size + i * 4;
        if off_pos + 4 > end {
            break;
        }
        let off = rd32(d, off_pos) as usize;
        let p = start + strings_start + off;
        if p >= end {
            out.push(String::new());
            continue;
        }
        if utf8 {
            // UTF-8 havuzu: [utf16 uzunluğu][bayt uzunluğu][baytlar][0]
            let mut q = p;
            let l0 = d[q] as usize;
            q += 1;
            if l0 & 0x80 != 0 && q < end {
                q += 1;
            }
            if q >= end {
                out.push(String::new());
                continue;
            }
            let mut len = d[q] as usize;
            q += 1;
            if len & 0x80 != 0 && q < end {
                len = ((len & 0x7f) << 8) | d[q] as usize;
                q += 1;
            }
            let stop = (q + len).min(end);
            out.push(String::from_utf8_lossy(&d[q..stop]).to_string());
        } else {
            let mut len = rd16(d, p) as usize;
            let mut q = p + 2;
            if len & 0x8000 != 0 && q + 2 <= end {
                len = ((len & 0x7fff) << 16) | rd16(d, q) as usize;
                q += 2;
            }
            let stop = (q + len * 2).min(end);
            let units: Vec<u16> = (q..stop).step_by(2).map(|x| rd16(d, x)).collect();
            out.push(String::from_utf16_lossy(&units));
        }
    }
    out
}

/// İkili AndroidManifest.xml'i (AXML) gezip manifest/application/meta-data alanlarını toplar.
fn parse_manifest(d: &[u8]) -> Result<ManifestInfo, String> {
    if d.len() < 8 || rd16(d, 0) != 0x0003 {
        return Err("AXML başlığı beklenen tipte değil".to_string());
    }
    let total = (rd32(d, 4) as usize).min(d.len());
    let mut strings: Vec<String> = Vec::new();
    let mut info = ManifestInfo::default();

    let mut off = 8usize;
    while off + 8 <= total {
        let ctype = rd16(d, off);
        let hsize = rd16(d, off + 2) as usize;
        let csize = rd32(d, off + 4) as usize;
        if csize < 8 {
            break;
        }
        let cend = (off + csize).min(total);
        match ctype {
            0x0001 => strings = parse_string_pool(d, off, cend),
            0x0102 => {
                let ext = off + hsize;
                if ext + 20 <= cend {
                    let elem = strings
                        .get(rd32(d, ext + 4) as usize)
                        .cloned()
                        .unwrap_or_default();
                    let attr_start = rd16(d, ext + 8) as usize;
                    let attr_size = rd16(d, ext + 10) as usize;
                    let attr_count = rd16(d, ext + 12) as usize;
                    let mut attrs: Vec<(String, AttrValue)> = Vec::new();
                    for i in 0..attr_count {
                        let a = ext + attr_start + i * attr_size;
                        if a + 20 > cend {
                            break;
                        }
                        let aname = strings
                            .get(rd32(d, a + 4) as usize)
                            .cloned()
                            .unwrap_or_default();
                        let raw = rd32(d, a + 8);
                        let dtype = d[a + 15];
                        let data = rd32(d, a + 16);
                        let val = if raw != 0xFFFF_FFFF {
                            match strings.get(raw as usize) {
                                Some(s) => AttrValue::Str(s.clone()),
                                None => AttrValue::Unknown,
                            }
                        } else {
                            match dtype {
                                0x03 => match strings.get(data as usize) {
                                    Some(s) => AttrValue::Str(s.clone()),
                                    None => AttrValue::Unknown,
                                },
                                0x10 | 0x11 => AttrValue::Int(data as i32 as i64),
                                _ => AttrValue::Unknown,
                            }
                        };
                        attrs.push((aname, val));
                    }
                    let get = |k: &str| {
                        attrs
                            .iter()
                            .find(|(n, _)| n == k)
                            .map(|(_, v)| v.clone())
                    };
                    match elem.as_str() {
                        "manifest" => {
                            if let Some(v) = get("package").and_then(|v| v.as_str().map(str::to_string)) {
                                info.package = Some(v);
                            }
                            if let Some(v) = get("versionName").and_then(|v| v.as_str().map(str::to_string)) {
                                info.version_name = Some(v);
                            }
                            if let Some(v) = get("versionCode").and_then(|v| v.as_i64()) {
                                info.version_code = Some(v);
                            }
                        }
                        "application" => {
                            if let Some(v) = get("label").and_then(|v| v.as_str().map(str::to_string)) {
                                info.label = Some(v);
                            }
                        }
                        "meta-data" => {
                            let name = get("name").and_then(|v| v.as_str().map(str::to_string));
                            let value = get("value").and_then(|v| match v {
                                AttrValue::Str(s) => Some(s),
                                AttrValue::Int(i) => Some(i.to_string()),
                                AttrValue::Unknown => None,
                            });
                            if let (Some(n), Some(v)) = (name, value) {
                                if n.starts_with("tachiyomi.animeextension") {
                                    info.meta.push((n, v));
                                }
                            }
                        }
                        _ => {}
                    }
                }
            }
            _ => {}
        }
        if cend <= off {
            break;
        }
        off = cend;
    }

    if info.package.is_none() {
        return Err("manifest öğesi okunamadı".to_string());
    }
    Ok(info)
}
