//! `pulsar embed` — patches/catalogue verisini Kotlin kaynağına gömer.
//!
//! Neden asset değil: eklenti `Injekt.get<Application>()` ile KONAK uygulamanın
//! Application'ını alır. `app.assets` konak uygulamanın asset'leridir; bizim
//! APK'mızdaki dosya orada yoktur. `createPackageContext` ile kendi paketimizin
//! asset'lerine erişmek denendi, Kototoro'nun sideload/yükleme yolunda yine
//! boş döndü — cihazda Pulsar TR hâlâ 103 (filtresiz) kaynak gösteriyor.
//!
//! Nyora'nın kanıtladığı yol: tabloyu `SourcePatches.kt` olarak KAYNAĞA gömmek.
//! Biz de aynısını build anında üretiyoruz: JSON'u Base64'e çevirip
//! `PulsarData.kt` içine sabit olarak yazıyoruz. Çalışma anında dosya/Context
//! erişimi yok; veri dex'in içinde.
//!
//! Kullanım:
//!   pulsar embed [--patches <patches.json>] [--catalogue <catalogue.json>]
//!                [--out <PulsarData.kt>] [--dry-run]

use std::path::{Path, PathBuf};
use std::process::ExitCode;

const PATCH_REL: &str = "pulsar-v2/extension/src/main/assets/patches.json";
const CAT_REL: &str = "pulsar-v2/extension/src/main/assets/catalogue.json";
const OUT_REL: &str =
    "pulsar-v2/extension/src/main/kotlin/eu/kanade/tachiyomi/extension/all/pulsar/PulsarData.kt";

struct Opts {
    patches: PathBuf,
    catalogue: PathBuf,
    out: PathBuf,
    dry: bool,
}

pub fn run(root: &Path, argv: &[String]) -> ExitCode {
    let mut o = Opts {
        patches: root.join(PATCH_REL),
        catalogue: root.join(CAT_REL),
        out: root.join(OUT_REL),
        dry: false,
    };
    let mut i = 0;
    while i < argv.len() {
        match argv[i].as_str() {
            "--patches" => match argv.get(i + 1) {
                Some(v) => {
                    o.patches = PathBuf::from(v);
                    i += 1;
                }
                None => return usage("--patches için yol gerekli"),
            },
            "--catalogue" => match argv.get(i + 1) {
                Some(v) => {
                    o.catalogue = PathBuf::from(v);
                    i += 1;
                }
                None => return usage("--catalogue için yol gerekli"),
            },
            "--out" => match argv.get(i + 1) {
                Some(v) => {
                    o.out = PathBuf::from(v);
                    i += 1;
                }
                None => return usage("--out için yol gerekli"),
            },
            "--dry-run" => o.dry = true,
            other => return usage(&format!("bilinmeyen argüman: {other}")),
        }
        i += 1;
    }
    match embed(&o) {
        Ok(()) => ExitCode::SUCCESS,
        Err(e) => {
            eprintln!("HATA: {e}");
            ExitCode::FAILURE
        }
    }
}

fn usage(msg: &str) -> ExitCode {
    eprintln!("HATA: {msg}");
    eprintln!("kullanım: pulsar embed [--patches p.json] [--catalogue c.json] [--out PulsarData.kt] [--dry-run]");
    ExitCode::from(64)
}

fn embed(o: &Opts) -> Result<(), String> {
    let patches = std::fs::read(&o.patches)
        .map_err(|e| format!("{} okunamadı: {e}", o.patches.display()))?;
    let catalogue = std::fs::read(&o.catalogue)
        .map_err(|e| format!("{} okunamadı: {e}", o.catalogue.display()))?;
    // Geçerli JSON mu? Bozuk veriyi dex'e gömmek sessiz çökme demek.
    serde_json::from_slice::<serde_json::Value>(&patches)
        .map_err(|e| format!("patches.json geçersiz: {e}"))?;
    serde_json::from_slice::<serde_json::Value>(&catalogue)
        .map_err(|e| format!("catalogue.json geçersiz: {e}"))?;

    let p64 = b64(&patches);
    let c64 = b64(&catalogue);
    // Kotlin/JVM sabit havuzu tek string için 65535 BAYT sınırı koyar.
    for (name, s) in [("patches", &p64), ("catalogue", &c64)] {
        if s.len() > 65_000 {
            return Err(format!(
                "{name} Base64 {0} B — 65000 sınırını aşıyor; parçalara bölmek gerekir",
                s.len()
            ));
        }
    }

    let kt = format!(
        r#"// ÜRETİLMİŞ DOSYA — elle düzenleme. Kaynak: tools/pulsar `embed` komutu.
// patches.json ve catalogue.json build anında Base64 olarak gömülür; çalışma
// anında dosya/Context erişimi yoktur (eklenti asset'leri konak uygulamada
// görünmüyordu).
package eu.kanade.tachiyomi.extension.all.pulsar

import android.util.Base64

internal object PulsarData {{

    private const val PATCHES_B64 = "{p}"

    private const val CATALOGUE_B64 = "{c}"

    private fun decode(data: String): String =
        String(Base64.decode(data, Base64.NO_WRAP), Charsets.UTF_8)

    private val patches: String by lazy {{ decode(PATCHES_B64) }}
    private val catalogue: String by lazy {{ decode(CATALOGUE_B64) }}

    /** Gömülü veri varsa döner; yoksa null (asset okuma yoluna düşülür). */
    fun embedded(name: String): String? = when (name) {{
        "patches.json" -> patches
        "catalogue.json" -> catalogue
        else -> null
    }}
}}
"#,
        p = p64,
        c = c64
    );

    if o.dry {
        println!(
            "[embed] dry-run: patches {} B, catalogue {} B -> {}",
            patches.len(),
            catalogue.len(),
            o.out.display()
        );
        return Ok(());
    }
    if let Some(parent) = o.out.parent() {
        std::fs::create_dir_all(parent).map_err(|e| format!("dizin: {e}"))?;
    }
    std::fs::write(&o.out, kt).map_err(|e| format!("{} yazılamadı: {e}", o.out.display()))?;
    println!(
        "[embed] gömüldü: patches {} B + catalogue {} B (base64 {}+{}) -> {}",
        patches.len(),
        catalogue.len(),
        p64.len(),
        c64.len(),
        o.out.display()
    );
    Ok(())
}

/// Standart Base64 (bağımlılık eklememek için elle).
fn b64(data: &[u8]) -> String {
    const T: &[u8; 64] = b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
    let mut out = String::with_capacity(data.len().div_ceil(3) * 4);
    for chunk in data.chunks(3) {
        let b = [
            chunk[0],
            *chunk.get(1).unwrap_or(&0),
            *chunk.get(2).unwrap_or(&0),
        ];
        let n = ((b[0] as u32) << 16) | ((b[1] as u32) << 8) | b[2] as u32;
        out.push(T[(n >> 18) as usize & 63] as char);
        out.push(T[(n >> 12) as usize & 63] as char);
        out.push(if chunk.len() > 1 { T[(n >> 6) as usize & 63] as char } else { '=' });
        out.push(if chunk.len() > 2 { T[n as usize & 63] as char } else { '=' });
    }
    out
}
