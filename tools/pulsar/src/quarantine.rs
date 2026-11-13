//! `pulsar quarantine` — cihazda LİSTE adımında düşen kaynakları karantinaya alır.
//!
//! Neden: indeksteki `sources` dizisi uygulamadaki kaynak listesini kontrol
//! ETMEZ; o liste eklentinin `PulsarSourceFactory.createSources()` çıktısıdır.
//! Bir kaynak listeden ancak `patches.json` içindeki `deadSources` (motor enum
//! adı) veya `deadHosts` (katalog alan adı) ile çıkarılır — fabrika o kaynağı
//! hiç oluşturmaz.
//!
//! Kural: yalnız `device_step == "list"` olan kayıtlar karantinaya girer.
//! Liste adımı geçip sonraki adımda (sayfa/detay) düşen kaynak listede kalır;
//! kullanıcı en azından mangayı bulur.
//!
//! Kalıcılık: `data/maintenance/overrides.json` — 06_prepare_assets.py bunu
//! `patches.json` ile birleştirir, yani build'de sıfırlanmaz.
//!
//! Kullanım: pulsar quarantine [--dry-run] [--clear]

use serde_json::{json, Map, Value};
use std::collections::{BTreeMap, BTreeSet};
use std::path::Path;
use std::process::ExitCode;

const OVERRIDES_REL: &str = "pulsar-v2/data/maintenance/overrides.json";
const MAP_REL: &str = "pulsar-v2/repo/source_map.json";
const STATUS_REL: &str = "pulsar-v2/data/source-status.json";

fn read(root: &Path, rel: &str) -> Result<Value, String> {
    let path = root.join(rel);
    let text = std::fs::read_to_string(&path).map_err(|e| format!("{} okunamadı: {e}", path.display()))?;
    serde_json::from_str(&text).map_err(|e| format!("{} geçersiz JSON: {e}", path.display()))
}

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

pub fn run(root: &Path, argv: &[String]) -> ExitCode {
    let dry = argv.iter().any(|a| a == "--dry-run");
    let clear = argv.iter().any(|a| a == "--clear");
    match quarantine(root, dry, clear) {
        Ok(()) => ExitCode::SUCCESS,
        Err(e) => {
            eprintln!("HATA: {e}");
            ExitCode::FAILURE
        }
    }
}

fn quarantine(root: &Path, dry: bool, clear: bool) -> Result<(), String> {
    let map = read(root, MAP_REL)?;
    let status = read(root, STATUS_REL)?;

    // id -> motor enum adı (DEAD_SOURCES ile aynı biçim)
    let mut engine_name: BTreeMap<String, String> = BTreeMap::new();
    for row in map.get("engine").and_then(|v| v.as_array()).into_iter().flatten() {
        let (Some(id), Some(name)) = (
            row.get("id").and_then(|v| v.as_i64()),
            row.get("name").and_then(|v| v.as_str()),
        ) else {
            continue;
        };
        engine_name.insert(id.to_string(), name.to_string());
    }

    let mut dead_sources: BTreeSet<String> = BTreeSet::new();
    let mut dead_hosts: BTreeSet<String> = BTreeSet::new();
    let mut quarantined: Vec<Value> = Vec::new();

    if !clear {
        let sources = status
            .get("sources")
            .and_then(|v| v.as_object())
            .ok_or("source-status.json içinde 'sources' yok")?;
        for (id, e) in sources {
            if e.get("device_step").and_then(|v| v.as_str()) != Some("list") {
                continue;
            }
            let detail = e
                .get("device")
                .and_then(|d| d.get("detail"))
                .and_then(|v| v.as_str())
                .unwrap_or("");
            // Yalnız KALICI sebepler karantinaya girer. timeout/reset/5xx tek
            // ölçümde geçici olabilir; onları listeden silmek çalışan kaynağı
            // da götürür. Bu yüzden yalnız şu imzalar:
            //   404 (kaynak taşınmış), DNS (host yok), SSL zinciri (cihaz
            //   doğrulayamıyor), "Liste boş" (ayrıştırıcı boş dönüyor).
            let deterministic = detail.contains("Status=404")
                || detail.contains("UnknownHost")
                || detail.contains("SSLHandshake")
                || detail.contains("Liste bo")
                || detail.contains("liste bo");
            if !deterministic {
                continue;
            }
            let kind = e.get("kind").and_then(|v| v.as_str()).unwrap_or("");
            let title = e.get("title").and_then(|v| v.as_str()).unwrap_or("").to_string();
            let detail: String = detail.chars().take(120).collect();
            match kind {
                "engine" => {
                    if let Some(name) = engine_name.get(id) {
                        dead_sources.insert(name.clone());
                        quarantined.push(json!({"kind": "engine", "name": name, "title": title, "detail": detail}));
                    }
                }
                "catalogue" => {
                    let host = bare(e.get("domain").and_then(|v| v.as_str()).unwrap_or(""));
                    if !host.is_empty() {
                        dead_hosts.insert(host.clone());
                        quarantined.push(json!({"kind": "catalogue", "host": host, "title": title, "detail": detail}));
                    }
                }
                _ => {}
            }
        }
    }

    // Mevcut overrides korunur; yalnız deadSources/deadHosts güncellenir.
    let existing = std::fs::read_to_string(root.join(OVERRIDES_REL))
        .ok()
        .and_then(|t| serde_json::from_str::<Value>(&t).ok())
        .unwrap_or_else(|| json!({}));
    let mut doc: Map<String, Value> = existing.as_object().cloned().unwrap_or_default();

    // Karantina AYRI anahtarlarda tutulur: --clear yalnız bunları siler,
    // 07_maintain'in elle doğrulanmış deadSources/deadHosts kararlarına dokunmaz.
    if clear {
        doc.remove("quarantineSources");
        doc.remove("quarantineHosts");
    } else {
        let mut src: BTreeSet<String> = doc
            .get("quarantineSources")
            .and_then(|v| v.as_array())
            .into_iter()
            .flatten()
            .filter_map(|v| v.as_str().map(|s| s.to_string()))
            .collect();
        src.extend(dead_sources.iter().cloned());
        let mut hosts: BTreeSet<String> = doc
            .get("quarantineHosts")
            .and_then(|v| v.as_array())
            .into_iter()
            .flatten()
            .filter_map(|v| v.as_str().map(|s| s.to_string()))
            .collect();
        hosts.extend(dead_hosts.iter().cloned());
        doc.insert("quarantineSources".into(), json!(src.iter().collect::<Vec<_>>()));
        doc.insert("quarantineHosts".into(), json!(hosts.iter().collect::<Vec<_>>()));
    }
    doc.insert("quarantineUpdated".into(), json!(crate::now_iso()));

    let total_dead = doc
        .get("quarantineSources")
        .and_then(|v| v.as_array())
        .map(|a| a.len())
        .unwrap_or(0)
        + doc
            .get("quarantineHosts")
            .and_then(|v| v.as_array())
            .map(|a| a.len())
            .unwrap_or(0);

    if !dry {
        let path = root.join(OVERRIDES_REL);
        if let Some(parent) = path.parent() {
            std::fs::create_dir_all(parent).map_err(|e| format!("dizin: {e}"))?;
        }
        std::fs::write(
            &path,
            serde_json::to_string_pretty(&Value::Object(doc)).map_err(|e| format!("serileştirme: {e}"))? + "\n",
        )
        .map_err(|e| format!("{} yazılamadı: {e}", path.display()))?;
    }

    println!(
        "[quarantine] bu tur: motor {} + katalog {} kaynak listeden cikarildi; overrides toplam {} kayit{}",
        dead_sources.len(),
        dead_hosts.len(),
        total_dead,
        if dry { "  [dry-run]" } else { "" }
    );
    for q in quarantined.iter().take(12) {
        println!(
            "  - {}",
            q.get("name")
                .or_else(|| q.get("host"))
                .and_then(|v| v.as_str())
                .unwrap_or("")
        );
    }
    if quarantined.len() > 12 {
        println!("  ... {} kayıt daha", quarantined.len() - 12);
    }
    Ok(())
}
