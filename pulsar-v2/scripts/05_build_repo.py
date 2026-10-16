#!/usr/bin/env python3
"""Pulsar-V2 - Aşama 6: Mihon Repo & Dizin Üretici.

Bu script pulsar-v2/data/catalogue.json içindeki kaynakları okur:
1. Nyora tarzı birleşik paketleri tanımlar:
   - Pulsar TR (Normal / SFW)
   - Pulsar TR 18+ (Yetişkin / NSFW)
   - Pulsar Global (Tüm diller / SFW)
   - Pulsar Global 18+ (Tüm diller / NSFW)
   - (İsteğe bağlı olarak --lang ja, --lang en vb. ile özel dil paketleri)
2. Mihon'un doğrudan okuyup ekleyebileceği pulsar-v2/repo/index.min.json dosyasını yazar.
3. pulsar-v2/repo/repo.json meta dosyasını oluşturur.
4. pulsar-v2/README.md kullanım kılavuzunu üretir.

Çıktı:
- pulsar-v2/repo/index.min.json
- pulsar-v2/repo/repo.json
- pulsar-v2/README.md
"""

import argparse
import hashlib
import json
import os
import sys
import time

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PULSAR_V2_DIR = os.path.join(ROOT_DIR, "pulsar-v2")
DATA_DIR = os.path.join(PULSAR_V2_DIR, "data")
REPO_DIR = os.path.join(PULSAR_V2_DIR, "repo")
CATALOGUE_FILE = os.path.join(DATA_DIR, "catalogue.json")
INDEX_FILE = os.path.join(REPO_DIR, "index.min.json")
REPO_META_FILE = os.path.join(REPO_DIR, "repo.json")
README_FILE = os.path.join(PULSAR_V2_DIR, "README.md")

REPO_BASE_URL = "https://raw.githubusercontent.com/Pulsariums/pulsar-trmangahub/main/pulsar-v2/repo"


def generate_source_entry(src):
    d = src["domain"]
    lang = src.get("lang", "tr")
    key = f"pulsar/{d}/{lang}"
    h = 1125899906842597
    for ch in key:
        h = 31 * h + ord(ch)
    h = h & 0x7FFFFFFFFFFFFFFF

    return {
        "id": str(h),
        "name": src["name"],
        "lang": lang,
        "baseUrl": src["baseUrl"]
    }


def main():
    parser = argparse.ArgumentParser(description="Pulsar-V2 Repo Indeks Uretici")
    parser.add_argument("--version-name", default="1.6.1", help="Eklenti surum adi (Mihon extensionLib uyumlu)")
    parser.add_argument("--version-code", type=int, default=106001, help="Surum kodu")
    args = parser.parse_args()

    if not os.path.exists(CATALOGUE_FILE):
        print(f"[HATA] {CATALOGUE_FILE} bulunamadi!")
        return

    with open(CATALOGUE_FILE, encoding="utf-8") as f:
        catalogue = json.load(f)

    sources = catalogue.get("sources", [])
    print(f"Katalogdan {len(sources)} kaynak okunuyor...")

    # Gruplar
    tr_sources = [s for s in sources if s.get("lang") == "tr"]
    tr_normal = [s for s in tr_sources if s.get("nsfw", 0) == 0]
    tr_nsfw = [s for s in tr_sources if s.get("nsfw", 0) == 1]

    all_normal = [s for s in sources if s.get("nsfw", 0) == 0]
    all_nsfw = [s for s in sources if s.get("nsfw", 0) == 1]

    packages = []

    # 1. Pulsar TR (Normal)
    if tr_normal:
        packages.append({
            "name": "Pulsar TR",
            "pkg": "eu.kanade.tachiyomi.extension.all.pulsar.tr",
            "apk": "pulsar-tr.apk",
            "lang": "tr",
            "code": args.version_code,
            "version": args.version_name,
            "nsfw": 0,
            "sources": [generate_source_entry(s) for s in tr_normal]
        })

    # 2. Pulsar TR 18+ (NSFW)
    if tr_nsfw:
        packages.append({
            "name": "Pulsar TR 18+",
            "pkg": "eu.kanade.tachiyomi.extension.all.pulsar.tr18",
            "apk": "pulsar-tr-18.apk",
            "lang": "tr",
            "code": args.version_code,
            "version": args.version_name,
            "nsfw": 1,
            "sources": [generate_source_entry(s) for s in tr_nsfw]
        })

    # 3. Pulsar Global (Normal)
    if all_normal:
        packages.append({
            "name": "Pulsar Global",
            "pkg": "eu.kanade.tachiyomi.extension.all.pulsar.global",
            "apk": "pulsar-global.apk",
            "lang": "all",
            "code": args.version_code,
            "version": args.version_name,
            "nsfw": 0,
            "sources": [generate_source_entry(s) for s in all_normal]
        })

    # 4. Pulsar Global 18+ (NSFW)
    if all_nsfw:
        packages.append({
            "name": "Pulsar Global 18+",
            "pkg": "eu.kanade.tachiyomi.extension.all.pulsar.global18",
            "apk": "pulsar-global-18.apk",
            "lang": "all",
            "code": args.version_code,
            "version": args.version_name,
            "nsfw": 1,
            "sources": [generate_source_entry(s) for s in all_nsfw]
        })

    os.makedirs(REPO_DIR, exist_ok=True)

    # 1. index.min.json
    with open(INDEX_FILE, "w", encoding="utf-8") as f:
        json.dump(packages, f, ensure_ascii=False, indent=2)

    # 2. repo.json
    repo_meta = {
        "index_v2": None,
        "meta": {
            "name": "Pulsar Manga Hub (V2)",
            "shortName": "Pulsar",
            "website": "https://github.com/Pulsariums/pulsar-trmangahub",
            "signingKeyFingerprint": "9add655a78e96c4ec7a53ef89dccb557cb5d767489fac5e785d671a5a75d4da2"
        }
    }
    with open(REPO_META_FILE, "w", encoding="utf-8") as f:
        json.dump(repo_meta, f, ensure_ascii=False, indent=2)

    # 3. README.md
    readme_content = f"""# Pulsar Manga Hub V2 (Mihon / Tachiyomi Deposu)

Nyora mimarisinden esinlenilmiş, cihaz üzerinde (on-device) çalışan, **çok dilli ve modüler** birleşik Mihon eklenti deposu.

Eski sistemdeki gibi onlarca ayrı APK kurmanıza gerek yoktur. Tek bir paket kurarak o dildeki tüm çalışan kaynaklara aynı anda erişebilirsiniz.

---

## Mihon'a Nasıl Eklenir?

1. **Mihon / Tachiyomi** uygulamasını açın.
2. **Daha Fazla (More) → Ayarlar (Settings) → Gözat (Browse) → Eklenti depoları (Extension repos) → +** simgesine dokunun.
3. Aşağıdaki depo URL'sini yapıştırın:

```text
{REPO_BASE_URL}/index.min.json
```

4. Ardından **Gözat → Eklentiler** sekmesine gelin. Yalnızca ihtiyacınız olan paketi kurun:

| Eklenti Adı | Paket | İçerik | Kaynak Sayısı |
|---|---|---|---|
| **Pulsar TR** | `…pulsar.tr` | Tüm Türkçe Normal (SFW) Manga Siteleri | **{len(tr_normal)} Kaynak** |
| **Pulsar TR 18+** | `…pulsar.tr18` | Tüm Türkçe Yetişkin (+18 / NSFW) Siteleri | **{len(tr_nsfw)} Kaynak** |
| **Pulsar Global** | `…pulsar.global` | Tüm Dillerdeki Normal Manga Siteleri | **{len(all_normal)} Kaynak** |
| **Pulsar Global 18+** | `…pulsar.global18` | Tüm Dillerdeki Yetişkin Manga Siteleri | **{len(all_nsfw)} Kaynak** |

---

## Mimari Özellikler

- **Tek Tıkla Kurulum:** Her site için ayrı APK indirme ve güncelleme derdi bitti.
- **Düşük Bellek Kullanımı (Lazy Loading):** Yüzlerce kaynak aynı anda belleğe yüklenmez; yalnızca tıkladığınız kaynak anlık başlatılır.
- **Cloudflare Desteği:** Mihon'un dahili "WebView ile Aç" özelliğiyle tamamen uyumludur.
- **Otomatik Bölüm Normalizasyonu:** Sitelerin ters/düz bölüm sıralama karmaşasını kronolojik olarak otomatik çözer.
- **Çok Dilli Modülerlik:** Gelecekte `--lang ja`, `--lang en` parametreleriyle istenen her dil tek komutla üretilebilir.
"""

    with open(README_FILE, "w", encoding="utf-8") as f:
        f.write(readme_content)

    print(f"\n[TAMAMLANDI] Mihon Repo Dosyalari Olusturuldu:")
    print(f"  - Dizin (index.min.json): {INDEX_FILE}")
    print(f"  - Depo Meta (repo.json): {REPO_META_FILE}")
    print(f"  - Rehber (README.md): {README_FILE}")
    print(f"\nUretilen Paketler:")
    for p in packages:
        print(f"  * {p['name']} ({p['pkg']}): {len(p['sources'])} kaynak (NSFW: {p['nsfw']}, Dil: {p['lang']})")


if __name__ == "__main__":
    main()
