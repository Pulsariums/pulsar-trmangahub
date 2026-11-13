//! `pulsar merge` — aynı sitenin klon kayıtlarını tek kaynağa indirir.
//!
//! Neden gerekli: eklentide iki motor yan yana çalışıyor — APK'ya gömülü
//! kotatsu ayrıştırıcıları (`engine`) ve kendi veri hattımızın ürettiği
//! katalog (`catalogue`). İkisi de aynı siteyi tanıdığında kullanıcı listede
//! aynı adı iki kez görüyordu (AdonisFansub, DiamondFansub, MangaWOW...).
//!
//! Kural (kullanıcı kararı): aynı host **ve** aynı dil/NSFW → tek kayıt.
//! Kanıtlanmış ayrıştırıcı (engine, `@Broken` değilse) kalır; katalog klonu
//! düşer. Taşınmış alan adları (patches.json domainOverrides: eski → canlı)
//! silinmez, kalan kaynağın `mirrors` dizisine yazılır — böylece site alan
//! adı değiştirdiğinde yedek adres kaybolmaz.
//!
//! Kullanım:
//!   pulsar merge [--map <source_map.json>] [--catalogue <catalogue.json>]
//!                [--patches <patches.json>] [--out <catalogue.json>]
//!                [--report <merge-report.json>] [--dry-run]

use serde_json::{json, Map, Value};
use std::collections::{BTreeMap, BTreeSet};
use std::path::{Path, PathBuf};
use std::process::ExitCode;

const MAP_REL: &str = "pulsar-v2/repo/source_map.json";
const CAT_REL: &str = "pulsar-v2/extension/src/main/assets/catalogue.json";
const PATCH_REL: &str = "pulsar-v2/extension/src/main/assets/patches.json";
const REPORT_REL: &str = "pulsar-v2/data/merge-report.json";

fn bare(host: &str) -> String {
    let mut h = host.trim().to_lowercase();
    for scheme in ["https://", "http://"] {
        if let Some(rest) = h.clone().strip_prefix(scheme) {
            h = rest.to_string();
            break;
        }
    }
    h.split('/').next().unwrap_or("").trim_start_matches("www.").to_string()
}

fn read_json(path: &Path) -> Result<Value, String> {
    let text = std::fs::read_to_string(path).map_err(|e| format!("{} okunamadı: {e}", path.display()))?;
    serde_json::from_str(&text).map_err(|e| format!("{} geçersiz JSON: {e}", path.display()))
}

struct Opts {
    map: PathBuf,
    catalogue: PathBuf,
    patches: PathBuf,
    out: PathBuf,
    report: PathBuf,
    dry: bool,
}

fn parse_args(root: &Path, argv: &[String]) -> Result<Opts, String> {
    let mut o = Opts {
        map: root.join(MAP_REL),
        catalogue: root.join(CAT_REL),
        patches: root.join(PATCH_REL),
        out: root.join(CAT_REL),
        report: root.join(REPORT_REL),
        dry: false,
    };
    let mut i = 0;
    while i < argv.len() {
        match argv[i].as_str() {
            "--map" => o.map = next_path(argv, &mut i, "--map")?,
            "--catalogue" => o.catalogue = next_path(argv, &mut i, "--catalogue")?,
            "--patches" => o.patches = next_path(argv, &mut i, "--patches")?,
            "--out" => o.out = next_path(argv, &mut i, "--out")?,
            "--report" => o.report = next_path(argv, &mut i, "--report")?,
            "--dry-run" => o.dry = true,
            other => return Err(format!("bilinmeyen argüman: {other}")),
        }
        i += 1;
    }
    Ok(o)
}

fn next_path(argv: &[String], i: &mut usize, what: &str) -> Result<PathBuf, String> {
    *i += 1;
    argv.get(*i)
        .map(PathBuf::from)
        .ok_or_else(|| format!("{what} için yol gerekli"))
}

/// (host, lang, nsfw) anahtarları — katalogda klonu varsa düşürülecek motor kümesi.
fn engine_keys(map: &Value) -> BTreeMap<(String, String, i64), String> {
    let mut keys = BTreeMap::new();
    let engine = map.get("engine").and_then(|v| v.as_array()).cloned().unwrap_or_default();
    for row in engine {
        if row.get("broken").and_then(|v| v.as_bool()).unwrap_or(false) {
            continue;
        }
        let host = bare(row.get("domain").and_then(|v| v.as_str()).unwrap_or(""));
        if host.is_empty() {
            continue;
        }
        let lang = row.get("lang").and_then(|v| v.as_str()).unwrap_or("all").to_lowercase();
        let nsfw = row.get("nsfw").and_then(|v| v.as_i64()).unwrap_or(0);
        let title = row
            .get("title")
            .and_then(|v| v.as_str())
            .filter(|s| !s.is_empty())
            .or_else(|| row.get("name").and_then(|v| v.as_str()))
            .unwrap_or("")
            .to_string();
        keys.insert((host, lang, nsfw), title);
    }
    keys
}

/// PulsarSource.id / emit_source_map.py ile birebir aynı hash.
fn pulsar_id(key: &str) -> i64 {
    let mut h: i64 = 1_125_899_906_842_597;
    for ch in key.chars() {
        h = h.wrapping_mul(31).wrapping_add(ch as i64);
    }
    h & i64::MAX
}

/// Alan adı gibi mi: en az bir nokta ve harf TLD (2+ karakter).
/// "eldermanga", "ELDERMANGA" gibi enum adlarını eler.
fn looks_like_host(s: &str) -> bool {
    let Some((label, tld)) = s.rsplit_once('.') else { return false };
    !label.is_empty()
        && tld.len() >= 2
        && tld.chars().all(|c| c.is_ascii_alphabetic())
        && !s.contains(' ')
}

/// eski host -> canlı host tablosunu ters çevirir: canlı host -> eski adresler.
fn mirrors_by_domain(patches: &Value) -> BTreeMap<String, BTreeSet<String>> {
    let mut out: BTreeMap<String, BTreeSet<String>> = BTreeMap::new();
    let overrides = patches.get("domainOverrides").and_then(|v| v.as_object()).cloned().unwrap_or_default();
    for (old, new) in overrides {
        let Some(new) = new.as_str() else { continue };
        let new_host = bare(new);
        let old_host = bare(&old);
        // domainOverrides hem parser ENUM adı (ELDERMANGA) hem host tutar;
        // enum adından türeyen "eldermanga" geçerli bir adres değildir.
        if !looks_like_host(&old_host) || new_host.is_empty() || old_host == new_host {
            continue;
        }
        out.entry(new_host).or_default().insert(old_host);
    }
    out
}

pub fn run(root: &Path, argv: &[String]) -> ExitCode {
    let opts = match parse_args(root, argv) {
        Ok(o) => o,
        Err(e) => {
            eprintln!("HATA: {e}");
            return ExitCode::from(64);
        }
    };
    match merge(root, &opts) {
        Ok(code) => code,
        Err(e) => {
            eprintln!("HATA: {e}");
            ExitCode::FAILURE
        }
    }
}

fn merge(_root: &Path, opts: &Opts) -> Result<ExitCode, String> {
    let map = read_json(&opts.map)?;
    let patches = if opts.patches.exists() { read_json(&opts.patches)? } else { json!({}) };
    let doc = read_json(&opts.catalogue)?;

    let is_object = doc.is_object();
    let mut sources: Vec<Value> = match &doc {
        Value::Array(a) => a.clone(),
        Value::Object(o) => o
            .get("sources")
            .and_then(|v| v.as_array())
            .cloned()
            .ok_or("catalogue.json içinde 'sources' dizisi yok")?,
        _ => return Err("catalogue.json beklenmeyen biçimde".into()),
    };

    let engines = engine_keys(&map);
    let mirrors = mirrors_by_domain(&patches);

    let mut dropped: Vec<Value> = Vec::new();
    let mut dropped_ids: Vec<i64> = Vec::new();
    let mut kept: Vec<Value> = Vec::with_capacity(sources.len());
    let mut mirror_count = 0usize;

    for mut src in sources.drain(..) {
        let Some(obj) = src.as_object_mut() else {
            kept.push(src);
            continue;
        };
        // id hesabında PulsarSource'un gördüğü HAM domain kullanılır
        // (rawConfig["domain"]); bare() yalnız eşleştirme içindir.
        let raw_domain = obj.get("domain").and_then(|v| v.as_str()).unwrap_or("").to_string();
        let host = bare(&raw_domain);
        let lang = obj.get("lang").and_then(|v| v.as_str()).unwrap_or("all").to_lowercase();
        let nsfw = obj.get("nsfw").and_then(|v| v.as_i64()).unwrap_or(0);

        if let Some(engine_title) = engines.get(&(host.clone(), lang.clone(), nsfw)) {
            dropped_ids.push(pulsar_id(&format!("pulsar/{raw_domain}/{lang}")));
            dropped.push(json!({
                "name": obj.get("name").cloned().unwrap_or(Value::Null),
                "domain": host,
                "lang": lang,
                "nsfw": nsfw,
                "kept": engine_title,
            }));
            continue;
        }

        obj.remove("mirrors");
        if let Some(hosts) = mirrors.get(&host) {
            let list: Vec<Value> = hosts
                .iter()
                .map(|h| Value::String(format!("https://{h}")))
                .collect();
            if !list.is_empty() {
                mirror_count += 1;
                obj.insert("mirrors".into(), Value::Array(list));
            }
        }
        kept.push(src);
    }

    let kept_count = kept.len();
    let report = json!({
        "generated": crate::now_iso(),
        "note": "Ayni host+dil+nsfw motor kaynagi katalogdan dusuruldu; tasinmis alan adlari mirrors'a yazildi.",
        "engine_keys": engines.len(),
        "catalogue_before": kept_count + dropped.len(),
        "catalogue_after": kept_count,
        "dropped": dropped,
        "mirrors": mirror_count,
        // İndeks üretimi bu id'leri listelemez: APK'da artık yoklar.
        "dropped_ids": dropped_ids,
    });

    if !opts.dry {
        let out_doc = if is_object {
            let mut o: Map<String, Value> = doc.as_object().cloned().unwrap_or_default();
            o.insert("sources".into(), Value::Array(kept.clone()));
            o.insert("total_count".into(), json!(kept_count));
            Value::Object(o)
        } else {
            Value::Array(kept.clone())
        };
        if let Some(parent) = opts.out.parent() {
            std::fs::create_dir_all(parent).map_err(|e| format!("dizin: {e}"))?;
        }
        std::fs::write(
            &opts.out,
            serde_json::to_string(&out_doc).map_err(|e| format!("serileştirme: {e}"))?,
        )
        .map_err(|e| format!("{} yazılamadı: {e}", opts.out.display()))?;

        if let Some(parent) = opts.report.parent() {
            std::fs::create_dir_all(parent).map_err(|e| format!("dizin: {e}"))?;
        }
        std::fs::write(
            &opts.report,
            serde_json::to_string_pretty(&report).map_err(|e| format!("serileştirme: {e}"))? + "\n",
        )
        .map_err(|e| format!("{} yazılamadı: {e}", opts.report.display()))?;
    }

    println!(
        "[merge] katalog: {} -> {} kaynak ({} klon elendi, {} kaynağa mirror yazıldı){}",
        kept_count + dropped.len(),
        kept_count,
        dropped.len(),
        mirror_count,
        if opts.dry { "  [dry-run]" } else { "" }
    );
    Ok(ExitCode::SUCCESS)
}
