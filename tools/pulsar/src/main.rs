use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::collections::BTreeMap;
use std::path::{Path, PathBuf};
use std::process::{Command, ExitCode};

mod health;
mod merge;
mod status;

const CONFIG_REL: &str = "pulsar-v2/config/upstreams.json";
const STATE_REL: &str = "pulsar-v2/data/upstreams-state.json";
const WORK_REL: &str = "pulsar-v2/.work/upstreams";

#[derive(Deserialize, Serialize, Clone, Debug)]
struct Upstream {
    id: String,
    name: String,
    kind: String,
    url: String,
    #[serde(default = "default_true")]
    enabled: bool,
}

fn default_true() -> bool {
    true
}

#[derive(Deserialize, Serialize, Clone, Debug)]
struct Config {
    #[serde(default = "one")]
    version: u32,
    upstreams: Vec<Upstream>,
}

fn one() -> u32 {
    1
}

#[derive(Deserialize, Serialize, Clone, Debug, Default)]
struct StateEntry {
    sha256: String,
    bytes: u64,
    #[serde(default)]
    entries: Option<usize>,
    fetched_at: String,
    path: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    error: Option<String>,
}

#[derive(Deserialize, Serialize, Clone, Debug, Default)]
struct State {
    updated_at: String,
    #[serde(default)]
    upstreams: BTreeMap<String, StateEntry>,
}

fn find_root() -> Option<PathBuf> {
    let mut dir = std::env::current_dir().ok()?;
    loop {
        if dir.join("pulsar-v2").is_dir() {
            return Some(dir);
        }
        if !dir.pop() {
            return None;
        }
    }
}

fn load_config(root: &Path) -> Result<Config, String> {
    let path = root.join(CONFIG_REL);
    let text = std::fs::read_to_string(&path)
        .map_err(|e| format!("{} okunamadı: {e}", path.display()))?;
    serde_json::from_str(&text).map_err(|e| format!("{} geçersiz JSON: {e}", path.display()))
}

fn load_state(root: &Path) -> State {
    let path = root.join(STATE_REL);
    std::fs::read_to_string(&path)
        .ok()
        .and_then(|t| serde_json::from_str(&t).ok())
        .unwrap_or_default()
}

fn save_state(root: &Path, state: &State) -> Result<(), String> {
    let path = root.join(STATE_REL);
    if let Some(parent) = path.parent() {
        std::fs::create_dir_all(parent).map_err(|e| format!("dizin: {e}"))?;
    }
    let text = serde_json::to_string_pretty(state).map_err(|e| format!("serileştirme: {e}"))?;
    std::fs::write(&path, text + "\n").map_err(|e| format!("{} yazılamadı: {e}", path.display()))
}

fn now_iso() -> String {
    let secs = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_secs())
        .unwrap_or(0);
    let days = (secs / 86400) as i64;
    let rem = secs % 86400;
    let (y, m, d) = civil_from_days(days);
    format!(
        "{:04}-{:02}-{:02}T{:02}:{:02}:{:02}Z",
        y,
        m,
        d,
        rem / 3600,
        (rem % 3600) / 60,
        rem % 60
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

fn count_entries(value: &serde_json::Value) -> Option<usize> {
    match value {
        serde_json::Value::Array(a) => Some(a.len()),
        serde_json::Value::Object(o) => {
            for key in ["extensions", "sources", "catalogue", "sites"] {
                if let Some(serde_json::Value::Array(a)) = o.get(key) {
                    return Some(a.len());
                }
            }
            o.values().find_map(|v| match v {
                serde_json::Value::Array(a) => Some(a.len()),
                _ => None,
            })
        }
        _ => None,
    }
}

fn git_output(dir: &Path, args: &[&str]) -> Result<String, String> {
    let out = Command::new("git")
        .arg("-C")
        .arg(dir)
        .args(args)
        .output()
        .map_err(|e| format!("git çalıştırılamadı: {e}"))?;
    if !out.status.success() {
        return Err(format!(
            "git {:?} başarısız: {}",
            args,
            String::from_utf8_lossy(&out.stderr).trim()
        ));
    }
    Ok(String::from_utf8_lossy(&out.stdout).trim().to_string())
}

fn rel(root: &Path, path: &Path) -> String {
    path.strip_prefix(root)
        .unwrap_or(path)
        .to_string_lossy()
        .replace('\\', "/")
}

fn fetch(root: &Path, u: &Upstream) -> Result<StateEntry, String> {
    let work = root.join(WORK_REL);
    std::fs::create_dir_all(&work).map_err(|e| format!("çalışma dizini: {e}"))?;

    match u.kind.as_str() {
        "http" => {
            let dest = work.join(format!("{}.json", u.id));
            let status = Command::new("curl")
                .args(["-fsSL", "--retry", "2", "--max-time", "180", "-o"])
                .arg(&dest)
                .arg(&u.url)
                .status()
                .map_err(|e| format!("curl çalıştırılamadı: {e}"))?;
            if !status.success() {
                return Err(format!("curl çıkış kodu {:?}", status.code()));
            }
            let bytes = std::fs::read(&dest).map_err(|e| format!("okuma: {e}"))?;
            let value: serde_json::Value =
                serde_json::from_slice(&bytes).map_err(|e| format!("JSON değil: {e}"))?;
            let digest = Sha256::digest(&bytes);
            Ok(StateEntry {
                sha256: format!("{digest:x}"),
                bytes: bytes.len() as u64,
                entries: count_entries(&value),
                fetched_at: now_iso(),
                path: rel(root, &dest),
                error: None,
            })
        }
        "git" => {
            let dest = work.join(&u.id);
            if dest.join(".git").is_dir() {
                git_output(&dest, &["fetch", "--depth", "1", "origin"])?;
                git_output(&dest, &["reset", "--hard", "FETCH_HEAD"])?;
            } else {
                let status = Command::new("git")
                    .args(["clone", "--depth", "1"])
                    .arg(&u.url)
                    .arg(&dest)
                    .status()
                    .map_err(|e| format!("git çalıştırılamadı: {e}"))?;
                if !status.success() {
                    return Err(format!("git clone çıkış kodu {:?}", status.code()));
                }
            }
            let sha = git_output(&dest, &["rev-parse", "HEAD"])?;
            Ok(StateEntry {
                sha256: sha,
                bytes: 0,
                entries: None,
                fetched_at: now_iso(),
                path: rel(root, &dest),
                error: None,
            })
        }
        other => Err(format!("bilinmeyen kind: {other}")),
    }
}

fn cmd_list(root: &Path) -> ExitCode {
    let cfg = match load_config(root) {
        Ok(c) => c,
        Err(e) => {
            eprintln!("HATA: {e}");
            return ExitCode::FAILURE;
        }
    };
    let state = load_state(root);
    println!(
        "{:<18} {:<5} {:<5} {:>8} {:>10}  {:<9} {}",
        "ID", "TÜR", "AÇIK", "KAYNAK", "BAYT", "SHA", "ÇEKİLDİ"
    );
    for u in &cfg.upstreams {
        let s = state.upstreams.get(&u.id);
        let entries = s
            .and_then(|x| x.entries)
            .map(|n| n.to_string())
            .unwrap_or_else(|| "—".to_string());
        let bytes = s
            .map(|x| x.bytes)
            .filter(|b| *b > 0)
            .map(|b| b.to_string())
            .unwrap_or_else(|| "—".to_string());
        let sha = s
            .map(|x| {
                let h = x.sha256.as_str();
                h[..h.len().min(9)].to_string()
            })
            .filter(|x| !x.is_empty())
            .unwrap_or_else(|| "—".to_string());
        let at = s
            .map(|x| x.fetched_at.clone())
            .filter(|x| !x.is_empty())
            .unwrap_or_else(|| "—".to_string());
        let flag = if s.map(|x| x.error.is_some()).unwrap_or(false) {
            " HATA"
        } else {
            ""
        };
        println!(
            "{:<18} {:<5} {:<5} {:>8} {:>10}  {:<9} {}{}",
            u.id,
            u.kind,
            if u.enabled { "evet" } else { "hayır" },
            entries,
            bytes,
            sha,
            at,
            flag
        );
    }
    println!(
        "\nTOPLAM: {} upstream ({} etkin)",
        cfg.upstreams.len(),
        cfg.upstreams.iter().filter(|u| u.enabled).count()
    );
    ExitCode::SUCCESS
}

fn cmd_update(root: &Path, argv: &[String]) -> ExitCode {
    let mut only: Option<String> = None;
    let mut dry = false;
    let mut i = 0;
    while i < argv.len() {
        match argv[i].as_str() {
            "--only" => {
                i += 1;
                match argv.get(i) {
                    Some(v) => only = Some(v.clone()),
                    None => {
                        eprintln!("HATA: --only için id gerekli");
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

    let cfg = match load_config(root) {
        Ok(c) => c,
        Err(e) => {
            eprintln!("HATA: {e}");
            return ExitCode::FAILURE;
        }
    };
    let mut state = load_state(root);
    let mut failures = 0usize;
    let mut ran = 0usize;

    for u in cfg.upstreams.iter().filter(|u| u.enabled) {
        if let Some(id) = &only {
            if &u.id != id {
                continue;
            }
        }
        if dry {
            println!("[dry]  {:<18} {}", u.id, u.url);
            ran += 1;
            continue;
        }
        ran += 1;
        match fetch(root, u) {
            Ok(entry) => {
                println!(
                    "[ok]   {:<18} kaynak={} sha={} bayt={}",
                    u.id,
                    entry
                        .entries
                        .map(|n| n.to_string())
                        .unwrap_or_else(|| "—".to_string()),
                    &entry.sha256[..entry.sha256.len().min(9)],
                    entry.bytes
                );
                state.upstreams.insert(u.id.clone(), entry);
            }
            Err(e) => {
                failures += 1;
                println!("[fail] {:<18} {}", u.id, e);
                state.upstreams.insert(
                    u.id.clone(),
                    StateEntry {
                        sha256: String::new(),
                        bytes: 0,
                        entries: None,
                        fetched_at: now_iso(),
                        path: String::new(),
                        error: Some(e),
                    },
                );
            }
        }
    }

    if ran == 0 {
        eprintln!("HATA: eşleşen upstream yok");
        return ExitCode::FAILURE;
    }
    state.updated_at = now_iso();
    if !dry {
        if let Err(e) = save_state(root, &state) {
            eprintln!("HATA: durum yazılamadı: {e}");
            return ExitCode::FAILURE;
        }
    }
    if failures > 0 {
        ExitCode::FAILURE
    } else {
        ExitCode::SUCCESS
    }
}

fn main() -> ExitCode {
    let args: Vec<String> = std::env::args().skip(1).collect();
    let root = match find_root() {
        Some(r) => r,
        None => {
            eprintln!("HATA: repo kökü bulunamadı (pulsar-v2/ dizini yok)");
            return ExitCode::from(2);
        }
    };
    match (args.first().map(|s| s.as_str()), args.get(1).map(|s| s.as_str())) {
        (Some("sources"), Some("list")) => cmd_list(&root),
        (Some("sources"), Some("update")) => cmd_update(&root, &args[2..]),
        (Some("health"), _) => health::run(&root, &args[1..]),
        (Some("status"), _) => status::run(&root, &args[1..]),
        (Some("merge"), _) => merge::run(&root, &args[1..]),
        _ => {
            eprintln!("kullanım:");
            eprintln!("  pulsar sources list");
            eprintln!("  pulsar sources update [--only <id>] [--dry-run]");
            eprintln!("  pulsar health [--lang tr] [--nsfw 0|1] [--limit N] [--jobs N] [--timeout sn]");
            eprintln!("  pulsar status [--device <cihaz-raporu.json>]");
            eprintln!("  pulsar merge [--map <source_map.json>] [--catalogue <catalogue.json>] [--dry-run]");
            ExitCode::from(64)
        }
    }
}
