use crate::health::HealthRow;
use serde::{Deserialize, Serialize};
use std::collections::BTreeMap;
use std::path::Path;
use std::process::ExitCode;

pub const STATUS_REL: &str = "pulsar-v2/data/source-status.json";

#[derive(Deserialize, Clone, Debug, Default)]
pub struct SourceEntry {
    pub id: i64,
    #[serde(default)] pub kind: String,
    #[serde(default)] pub name: String,
    #[serde(default)] pub title: String,
    #[serde(default)] pub lang: String,
    #[serde(default)] pub nsfw: i32,
    #[serde(default)] pub domain: String,
}

#[derive(Deserialize, Default)]
pub struct SourceMap {
    #[serde(default)] pub engine: Vec<SourceEntry>,
    #[serde(default)] pub catalogue: Vec<SourceEntry>,
}

#[derive(Deserialize, Default)]
pub struct CatEntry {
    #[serde(default)] pub domain: String,
    #[serde(default)] pub lang: String,
    #[serde(default)] pub sorun: String,
}

#[derive(Deserialize, Default)]
pub struct CatalogueFile {
    #[serde(default)] pub sources: Vec<CatEntry>,
}

#[derive(Serialize, Deserialize, Clone, Debug, Default)]
pub struct Probe {
    pub status: String,
    #[serde(default)] pub http_code: String,
    #[serde(default)] pub ms: u64,
    #[serde(default)] pub detail: String,
    pub at: String,
}

#[derive(Serialize, Deserialize, Clone, Debug)]
pub struct StatusEntry {
    pub id: i64,
    pub kind: String,
    pub title: String,
    pub lang: String,
    pub nsfw: i32,
    pub domain: String,
    pub packages: Vec<String>,
    pub state: String,
    #[serde(default, skip_serializing_if = "Option::is_none")] pub health: Option<Probe>,
    #[serde(default, skip_serializing_if = "Option::is_none")] pub device: Option<Probe>,
    /// Cihaz testinde ilk düşen adım (list/search/details/chapters/covers/pages).
    /// "list" düşerse kaynak tamamen ölü; sonraki adımlar kısmi arıza demektir.
    #[serde(default, skip_serializing_if = "Option::is_none")] pub device_step: Option<String>,
    #[serde(default, skip_serializing_if = "String::is_empty")] pub note: String,
    /// Sorun türü ("cloudflare"/"login"). Dolu ise kaynak `*_sorunlu` paketine ayrılır.
    #[serde(default, skip_serializing_if = "String::is_empty")] pub sorun: String,
}

#[derive(Serialize, Deserialize, Clone, Debug, Default)]
pub struct StatusFile {
    pub generated: String,
    pub sources: BTreeMap<String, StatusEntry>,
}

pub fn packages_for(e: &SourceEntry, sorun: &str) -> Vec<String> {
    let tr = e.lang == "tr";
    let nsfw = e.nsfw == 1;
    let sorunlu = !sorun.is_empty();
    let base = match (tr, nsfw) {
        (true, false) => "tr",
        (true, true) => "tr18",
        (false, false) => "global",
        (false, true) => "global18",
    };
    vec![if sorunlu { format!("{base}_sorunlu") } else { base.to_string() }]
}

pub fn recompute_state(e: &mut StatusEntry) {
    let device = e.device.as_ref().map(|p| p.status.as_str()).unwrap_or("");
    let health = e.health.as_ref().map(|p| p.status.as_str()).unwrap_or("");
    e.state = if device == "fail" || device == "cloudflare" {
        "pending".to_string()
    } else if health == "ok" {
        "active".to_string()
    } else if health.is_empty() {
        "unknown".to_string()
    } else {
        "pending".to_string()
    };
}

fn load(root: &Path) -> StatusFile {
    std::fs::read_to_string(root.join(STATUS_REL))
        .ok()
        .and_then(|t| serde_json::from_str(&t).ok())
        .unwrap_or_default()
}

fn save(root: &Path, file: &StatusFile) -> Result<(), String> {
    let path = root.join(STATUS_REL);
    if let Some(parent) = path.parent() {
        std::fs::create_dir_all(parent).map_err(|e| e.to_string())?;
    }
    let text = serde_json::to_string_pretty(file).map_err(|e| e.to_string())?;
    std::fs::write(&path, text + "\n").map_err(|e| e.to_string())
}

pub fn ensure_all(root: &Path) -> Result<StatusFile, String> {
    let map_path = root.join("pulsar-v2/repo/source_map.json");
    let text = std::fs::read_to_string(&map_path).map_err(|e| format!("{}: {e}", map_path.display()))?;
    let map: SourceMap = serde_json::from_str(&text).map_err(|e| format!("source_map.json: {e}"))?;
    let mut file = load(root);
    // Elle işaretli "sorun" alanları cihaz sonucundan önce gelir.
    let cat_path = root.join("pulsar-v2/data/catalogue.json");
    let mut manual: std::collections::HashMap<(String, String), String> = std::collections::HashMap::new();
    if let Ok(cat_text) = std::fs::read_to_string(&cat_path) {
        if let Ok(cat) = serde_json::from_str::<CatalogueFile>(&cat_text) {
            for c in cat.sources {
                if !c.sorun.is_empty() {
                    manual.insert((c.domain.to_lowercase(), c.lang.to_lowercase()), c.sorun);
                }
            }
        }
    }
    let mut seen: std::collections::HashSet<String> = std::collections::HashSet::new();
    for e in map.engine.into_iter().chain(map.catalogue) {
        let key = e.id.to_string();
        seen.insert(key.clone());
        let s = file.sources.entry(key).or_insert_with(|| StatusEntry {
            id: e.id,
            kind: e.kind.clone(),
            title: String::new(),
            lang: String::new(),
            nsfw: 0,
            domain: String::new(),
            packages: Vec::new(),
            state: "unknown".to_string(),
            health: None,
            device: None,
            device_step: None,
            note: String::new(),
            sorun: String::new(),
        });
        // Katalogda dil/domain/nsfw değişince kimlik alanları güncellenmeli; eskiden
        // `or_insert_with` yüzünden eski id olduğu gibi kalıyor ve yayında bayat
        // kaynak görünüyordu (mangaball: tr -> en). Sağlık/cihaz/not korunur.
        s.id = e.id;
        s.kind = e.kind.clone();
        s.title = if e.title.is_empty() { e.name.clone() } else { e.title.clone() };
        s.lang = e.lang.clone();
        s.nsfw = e.nsfw;
        s.domain = e.domain.clone();
        // Sınıflama yalnız elle işarete bağlıdır. Cihaz raporu yalnızca düşen
        // kaynakları listeler; geçen kaynağın eski etiketi güncellenmediği için
        // cihazdan türetilen "sorun" bayat kalıyordu. Cihaz verisi saklanır.
        let sorun = manual
            .get(&(e.domain.to_lowercase(), e.lang.to_lowercase()))
            .cloned()
            .unwrap_or_default();
        s.sorun = sorun.clone();
        s.packages = packages_for(&e, &sorun);
        recompute_state(s);
    }
    // Katalogdan düşen id'ler yayın listesinde kalmasın.
    file.sources.retain(|k, _| seen.contains(k));
    file.generated = now();
    save(root, &file)?;
    Ok(file)
}

pub fn record_health(root: &Path, rows: &[HealthRow]) -> Result<(), String> {
    let mut file = ensure_all(root)?;
    let at = now();
    for r in rows {
        let key = r.id.to_string();
        if let Some(entry) = file.sources.get_mut(&key) {
            entry.health = Some(Probe {
                status: r.status.clone(),
                http_code: r.http_code.clone(),
                ms: r.ms as u64,
                detail: r.detail.clone(),
                at: at.clone(),
            });
            recompute_state(entry);
        }
    }
    save(root, &file)
}

pub fn record_device(root: &Path, device_path: &Path) -> Result<usize, String> {
    let text = std::fs::read_to_string(device_path).map_err(|e| format!("{}: {e}", device_path.display()))?;
    let value: serde_json::Value = serde_json::from_str(&text).map_err(|e| format!("cihaz raporu JSON değil: {e}"))?;
    let list = value.get("sources").and_then(|v| v.as_array()).cloned().unwrap_or_default();
    let mut file = ensure_all(root)?;
    let at = now();
    let mut merged = 0usize;
    for item in list {
        let name = item.get("name").and_then(|v| v.as_str()).unwrap_or("");
        let id: Option<i64> = name.strip_prefix("MIHON_").and_then(|s| s.parse().ok());
        let Some(id) = id else { continue };
        let Some(entry) = file.sources.get_mut(&id.to_string()) else { continue };
        let status = item.get("status").and_then(|v| v.as_str()).unwrap_or("fail").to_string();
        // İlk DÜŞEN adım rapora yazılır. Sıra bilinçli: liste adımı kaynağın
        // tamamen ölü olduğunu gösterir; sayfa hatası ise kaynağın büyük ölçüde
        // çalıştığını. Raporda ikisini ayırt edebilmek için adım adı korunur.
        let (step, message) = first_failing_step(&item);
        let detail = if step.is_empty() { message } else { format!("{step}: {message}") };
        entry.device = Some(Probe {
            status,
            http_code: String::new(),
            ms: 0,
            detail: detail.chars().take(180).collect(),
            at: at.clone(),
        });
        entry.device_step = if step.is_empty() { None } else { Some(step.to_string()) };
        recompute_state(entry);
        merged += 1;
    }
    save(root, &file)?;
    Ok(merged)
}

/// Cihaz raporunda ilk düşen adımı ve mesajını döner (adım yoksa boş).
/// Sıra sabit: liste adımı kaynağın bütünüyle ölü olduğunu gösterir; alfabetik
/// sıralama "chapters"ı öne alıp asıl sebebi gizlerdi.
fn first_failing_step(item: &serde_json::Value) -> (String, String) {
    const ORDER: [&str; 7] = ["list", "search", "details", "chapters", "covers", "pages", "random"];
    let Some(steps) = item.get("steps").and_then(|v| v.as_object()) else {
        return (String::new(), String::new());
    };
    for name in ORDER {
        let Some(step) = steps.get(name) else { continue };
        let status = step.get("status").and_then(|v| v.as_str()).unwrap_or("");
        if status == "fail" || status == "cloudflare" {
            let message = step.get("message").and_then(|v| v.as_str()).unwrap_or("").to_string();
            return (name.to_string(), message);
        }
    }
    (String::new(), String::new())
}

fn now() -> String {
    let secs = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_secs())
        .unwrap_or(0);
    let days = (secs / 86400) as i64;
    let rem = secs % 86400;
    let (y, m, d) = civil_from_days(days);
    format!("{:04}-{:02}-{:02}T{:02}:{:02}:{:02}Z", y, m, d, rem / 3600, (rem % 3600) / 60, rem % 60)
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

pub fn run(root: &Path, argv: &[String]) -> ExitCode {
    let result = if let Some(pos) = argv.iter().position(|a| a == "--device") {
        match argv.get(pos + 1) {
            Some(p) => record_device(root, Path::new(p)).map(|n| println!("cihaz sonucu işlendi: {n} kaynak")),
            None => Err("--device için dosya yolu gerekli".to_string()),
        }
    } else {
        ensure_all(root).map(|_| ())
    };
    if let Err(e) = result {
        eprintln!("HATA: {e}");
        return ExitCode::FAILURE;
    }
    let file = match ensure_all(root) {
        Ok(f) => f,
        Err(e) => { eprintln!("HATA: {e}"); return ExitCode::FAILURE; }
    };
    let mut by_state: BTreeMap<String, usize> = BTreeMap::new();
    for s in file.sources.values() {
        *by_state.entry(s.state.clone()).or_insert(0) += 1;
    }
    println!("DURUM DOSYASI: {} kaynak", file.sources.len());
    for (k, v) in &by_state {
        println!("  {k:<10} {v}");
    }
    ExitCode::SUCCESS
}
