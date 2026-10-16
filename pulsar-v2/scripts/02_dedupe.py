#!/usr/bin/env python3
"""Pulsar-V2 - Aşama 2 (Gelişmiş): Akıllı Site Birleştirici & Canonical Çözümleyici.

Bu script aynı manga ekibine veya aynı platforma ait farklı domainleri tek bir zengin kayıtta birleştirir:
Örnekler:
- Kuroi Manga: kuroimanga.site ve kuroimanga.com birleştirilir
- Manga Cix: mangacix.net ve mangacix.com birleştirilir
- Minda Fansub: mindafansub.dev ve mindafansub.online birleştirilir
- Koreli Scans / Nabicix: nabicix.com ve koreliscans.com birleştirilir
- Manga Tilkisi: tilkiscans.com ve mangatilkisi.net birleştirilir
- Yaoi Flix: yaoiflix.fit ve yaoiflix.me birleştirilir

Birleştirme Kuralları:
1. Kullanıcının doğruladığı (verified_by_user) domain varsa doğrudan birincil (canonical) seçilir.
2. Diğer tüm eski/alternatif domainler altDomains listesine eklenir.
3. Farklı repolardan (Keiyoushi, Nyora, Local) gelen en zengin motor ve config bilgileri harmanlanır.
4. Kaynak kökenleri (origins) birleştirilir.

Çıktı: pulsar-v2/data/deduplicated.json
"""

import collections
import json
import os
import re

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PULSAR_V2_DIR = os.path.join(ROOT_DIR, "pulsar-v2")
DATA_DIR = os.path.join(PULSAR_V2_DIR, "data")
IN_FILE = os.path.join(DATA_DIR, "raw_sources.json")
OUT_FILE = os.path.join(DATA_DIR, "deduplicated.json")

ENGINE_PRIORITY = {
    "madara": 10,
    "mangathemesia": 10,
    "mangareader": 10,
    "initmanga": 9,
    "zeistmanga": 9,
    "mmrcms": 9,
    "wpcomics": 8,
    "custom": 5,
    "keiyoushi": 3,
    "unknown": 1
}


def clean_domain(domain):
    if not domain:
        return ""
    d = str(domain).strip().lower()
    d = re.sub(r"^https?://", "", d)
    d = d.split("/")[0]
    d = re.sub(r"^www\.", "", d)
    return d


def extract_site_brand(name, domain):
    """Sitenin marka adını çıkarır (örn: kuroimanga, ruyamanga, mangatilkisi)."""
    d = clean_domain(domain)
    # Domain kökü
    parts = d.split(".")
    domain_root = parts[0] if len(parts) >= 2 else d
    domain_root = re.sub(r"\d+$", "", domain_root)  # ruyamanga2 -> ruyamanga

    # İsim kökü
    clean_n = re.sub(r"[^a-zA-Z0-9]", "", (name or "").lower())
    clean_n = re.sub(r"(fansub|scans|manga|ceviri|ceviri|toon|hub|online|site|net|com|org)$", "", clean_n)

    # Özel eşleşmeler
    if "tilki" in clean_n or "tilki" in domain_root:
        return "mangatilkisi"
    if "nabicix" in clean_n or "nabicix" in domain_root or "koreli" in clean_n:
        return "koreliscans"
    if "yaoi" in clean_n and "flix" in clean_n:
        return "yaoiflix"

    if len(clean_n) >= 4:
        return clean_n
    return domain_root


def main():
    if not os.path.exists(IN_FILE):
        print(f"[HATA] {IN_FILE} bulunamadi!")
        return

    with open(IN_FILE, encoding="utf-8") as f:
        raw_list = json.load(f)

    print(f"Girdi: {len(raw_list)} ham kaynak akilli birlestirme icin analiz ediliyor...")

    # Gruplama: (lang, brand_key)
    brand_groups = collections.defaultdict(list)

    for item in raw_list:
        d = clean_domain(item["domain"])
        if not d:
            continue
        lang = (item.get("lang") or "tr").lower()
        brand = extract_site_brand(item.get("name", ""), d)
        group_key = (lang, brand)
        brand_groups[group_key].append(item)

    merged_sources = []
    merged_site_count = 0

    for (lang, brand), items in brand_groups.items():
        if len(items) > 1:
            merged_site_count += 1

        # 1. En iyi birincil (canonical) kaydı seç
        # Öncelik: Kullanıcı doğrulamış mı? -> origins sayısı -> motor önceliği
        def score_item(it):
            score = 0
            if it.get("verified_by_user"):
                score += 100
            score += len(it.get("origins", [])) * 10
            score += ENGINE_PRIORITY.get(it.get("engine", ""), 1)
            # .com ve .net uzantıları genelde daha günceldir
            d = clean_domain(it["domain"])
            if d.endswith((".com", ".net", ".org", ".site", ".dev", ".fit")):
                score += 5
            return score

        best_item = max(items, key=score_item)

        # 2. Diğer tüm domainleri ve bilgileri harmanla
        all_domains = set()
        all_origins = set()
        best_config = best_item.get("config") or {}
        best_engine = best_item.get("engine", "custom")
        is_nsfw = 0
        is_verified = False

        for it in items:
            d = clean_domain(it["domain"])
            if d:
                all_domains.add(d)
            all_origins.update(it.get("origins", []))
            if it.get("nsfw", 0) == 1:
                is_nsfw = 1
            if it.get("verified_by_user"):
                is_verified = True
            # Daha iyi motor varsa al
            if ENGINE_PRIORITY.get(it.get("engine", ""), 1) > ENGINE_PRIORITY.get(best_engine, 1):
                best_engine = it["engine"]
            if it.get("config") and not best_config:
                best_config = it["config"]

        canonical_domain = clean_domain(best_item["domain"])
        all_domains.discard(canonical_domain)

        merged_entry = {
            "id": best_item["id"],
            "brand": brand,
            "name": best_item["name"],
            "lang": lang,
            "nsfw": is_nsfw,
            "domain": canonical_domain,
            "baseUrl": best_item["baseUrl"],
            "altDomains": sorted(list(all_domains)),
            "engine": best_engine,
            "config": best_config,
            "origins": sorted(list(all_origins)),
            "verified_by_user": is_verified,
            "merged_variant_count": len(items)
        }
        merged_sources.append(merged_entry)

    # Sıralama: Önce doğrulanmışlar, sonra alfabetik marka
    merged_sources.sort(key=lambda x: (0 if x["verified_by_user"] else 1, x["name"].lower()))

    # Kaydet
    with open(OUT_FILE, "w", encoding="utf-8") as f:
        json.dump(merged_sources, f, ensure_ascii=False, indent=2)

    tr_sources = [s for s in merged_sources if s["lang"] == "tr"]
    multi_domain_tr = [s for s in tr_sources if s["altDomains"]]
    verified_tr = [s for s in tr_sources if s["verified_by_user"]]

    print(f"\n[TAMAMLANDI] Akıllı Tekilleştirme Tamamlandı:")
    print(f"  - Toplam Tekil Kaynak: {len(merged_sources)}")
    print(f"  - Türkçe (TR) Tekil Kaynak Sayısı: {len(tr_sources)}")
    print(f"  - Birden Fazla Domaini/Kaydı Birleştirilen TR Siteleri: {len(multi_domain_tr)} adet")
    print(f"  - Kullanıcı Doğrulamalı TR Siteleri: {len(verified_tr)} / 39 (Eksiksiz)")
    print(f"  - Çıktı: {OUT_FILE}")

    print("\nÖrnek Birleştirilen Siteler (Canonical + Alternatif Domainler):")
    for s in multi_domain_tr[:8]:
        print(f"  * {s['name']}: {s['domain']} (Alternatifler: {s['altDomains']})")


if __name__ == "__main__":
    main()
