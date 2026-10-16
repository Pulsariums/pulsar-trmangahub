#!/usr/bin/env python3
"""Pulsar-V2 - Aşama 4: Tam Otomatik Kaynak & Seçici Üretici.

Bu script pulsar-v2/data/alive_sources.json içindeki canlı kaynakları işler:
1. Bilinen CMS motorları (Madara, MangaThemesia, InitManga, ZeistManga, MMRCMS vb.) için
   standart konfigürasyonları ve seçicileri otomatik tanımlar.
2. Özel (Custom) siteler için repodaki data/recon/*.spec.json dosyalarındaki doğrulanmış seçicileri
   (özellikle Ragnarscans gibi statik HTML ile onarılmış selector'ları) aktarır.
3. Çıktıyı Nyora data-driven şemasıyla uyumlu, hem tekil derlemeye hem de birleşik
   SourceFactory'ye girdi olacak nihai pulsar-v2/data/catalogue.json dosyasına derler.

Çıktı: pulsar-v2/data/catalogue.json
"""

import json
import os
import re
import sys
import time

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PULSAR_V2_DIR = os.path.join(ROOT_DIR, "pulsar-v2")
DATA_DIR = os.path.join(PULSAR_V2_DIR, "data")
IN_FILE = os.path.join(DATA_DIR, "alive_sources.json")
OUT_FILE = os.path.join(DATA_DIR, "catalogue.json")
RECON_DIR = os.path.join(ROOT_DIR, "data", "recon")

# Motor varsayılan şablonları
ENGINE_DEFAULTS = {
    "madara": {
        "engine": "madara",
        "listPath": "/manga",
        "itemSelector": "div.page-item-detail, div.manga",
        "chapterSelector": "li.wp-manga-chapter, div.chapter-item",
        "readerSelector": "div.page-break img, div.reading-content img"
    },
    "mangathemesia": {
        "engine": "mangathemesia",
        "listPath": "/manga",
        "itemSelector": "div.bsx",
        "chapterSelector": "div.eph-num, li.wp-manga-chapter",
        "readerSelector": "div#readerarea img"
    },
    "initmanga": {
        "engine": "initmanga",
        "listPath": "/manga",
        "itemSelector": "div.manga-card, div.bsx",
        "chapterSelector": "div.chapter-item",
        "readerSelector": "#init-manga-single-chapter img, div#readerarea img"
    },
    "zeistmanga": {
        "engine": "zeistmanga",
        "listPath": "/p/manga-list.html",
        "itemSelector": "div.grid-item, div.animepost",
        "chapterSelector": "ul.clstyle li, div.chapter-list li",
        "readerSelector": "div#readerarea img, div.separator img"
    },
    "mangareader": {
        "engine": "mangareader",
        "listPath": "/manga",
        "itemSelector": "div.bsx",
        "chapterSelector": "div.eph-num a",
        "readerSelector": "div#readerarea img"
    },
    "custom": {
        "engine": "custom",
        "listPath": "/manga",
        "itemSelector": "div.manga-card, div.bsx, div.page-item-detail",
        "chapterSelector": "div.chapter-item, li.wp-manga-chapter, div.eph-num",
        "readerSelector": "div.page-break img, div#readerarea img, #init-manga-single-chapter img"
    }
}


def load_spec_for_domain(domain):
    """Eğer domain için özel recon spec dosyası varsa oku."""
    spec_path = os.path.join(RECON_DIR, f"{domain}.spec.json")
    if os.path.exists(spec_path):
        try:
            with open(spec_path, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None
    return None


def generate_source_config(src):
    domain = src["domain"]
    engine = (src.get("engine") or "custom").lower()

    # Varsayılan motor ayarlarını al
    base_defaults = ENGINE_DEFAULTS.get(engine, ENGINE_DEFAULTS["custom"]).copy()

    # Spec dosyasından özel seçicileri ara
    spec = load_spec_for_domain(domain)
    if spec:
        css = spec.get("css", {})
        if css.get("chapter_item"):
            base_defaults["chapterSelector"] = css["chapter_item"]
        if css.get("reader_images"):
            base_defaults["readerSelector"] = css["reader_images"]
        if css.get("list_item"):
            base_defaults["itemSelector"] = css["list_item"]

    # Ragnarscans özel statik HTML seçicileri (Daha önce başarıyla onardığımız)
    if "ragnarscans" in domain:
        base_defaults["engine"] = "initmanga"
        base_defaults["itemSelector"] = "div.manga-card"
        base_defaults["chapterSelector"] = "div.chapter-item"
        base_defaults["readerSelector"] = "#init-manga-single-chapter img, div.chapter-image img"

    # Kaynak nesnesini oluştur
    cfg = src.get("config") or {}
    cfg.update(base_defaults)

    return {
        "id": src["id"],
        "name": src["name"],
        "lang": src.get("lang", "tr"),
        "nsfw": src.get("nsfw", 0),
        "domain": domain,
        "baseUrl": src.get("baseUrl") or f"https://{domain}",
        "engine": base_defaults["engine"],
        "config": cfg,
        "verified_by_user": src.get("verified_by_user", False),
        "origins": src.get("origins", [])
    }


def main():
    if not os.path.exists(IN_FILE):
        print(f"[HATA] {IN_FILE} bulunamadi!")
        return

    with open(IN_FILE, encoding="utf-8") as f:
        alive_sources = json.load(f)

    print(f"Girdi: {len(alive_sources)} canli kaynak icin katalog ve konfigurasyon uretiliyor...")

    catalog_sources = []
    for s in alive_sources:
        src_cfg = generate_source_config(s)
        catalog_sources.append(src_cfg)

    # Sıralama: Önce doğrulanmışlar, sonra alfabetik isim
    catalog_sources.sort(key=lambda x: (0 if x["verified_by_user"] else 1, x["name"].lower()))

    output_data = {
        "schema_version": 2,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "total_count": len(catalog_sources),
        "languages": sorted(list(set(s["lang"] for s in catalog_sources))),
        "sources": catalog_sources
    }

    with open(OUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)

    tr_sources = [s for s in catalog_sources if s["lang"] == "tr"]
    tr_nsfw = [s for s in tr_sources if s["nsfw"] == 1]
    tr_normal = [s for s in tr_sources if s["nsfw"] == 0]
    verified = [s for s in catalog_sources if s["verified_by_user"]]

    print(f"\n[TAMAMLANDI] Katalog Uretildi: {OUT_FILE}")
    print(f"  - Toplam Kaynak: {len(catalog_sources)}")
    print(f"  - Türkçe (TR) Kaynaklar: {len(tr_sources)}")
    print(f"      * Normal (SFW): {len(tr_normal)}")
    print(f"      * Yetişkin (NSFW): {len(tr_nsfw)}")
    print(f"  - Kullanıcı Doğrulamalı: {len(verified)}")
    print(f"  - Motor Dağılımı:")
    engines = {}
    for s in catalog_sources:
        engines[s["engine"]] = engines.get(s["engine"], 0) + 1
    for eng, count in sorted(engines.items(), key=lambda x: -x[1]):
        print(f"      * {eng}: {count}")


if __name__ == "__main__":
    main()
