#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""06_prepare_assets.py — Derleme-varlıklığı (asset) hazırlığı.

Nyora porter'ın build.sh'deki "vendor SourcePatches.kt" adımı ne yapıyor
(Nyora'nın domain/dead tables Kotlin'a gömülü) — biz aynısını VERİDEN
üreterek yapıyoruz:

  pulsar-v2/data/liveness.json   (03_probe_fast.py çıktıları)
  pulsar-v2/data/alive_sources.json
        |
        v
  extension/src/main/assets/catalogue.json   (data-driven katalog)
  extension/src/main/assets/patches.json     (tamir/ölü/yeniden ad tablosu)

patches.json alanları:
  domainOverrides : eski domain -> canli domain (OTOMATIK_TAMIR_* + alias tamiri)
  deadHosts       : OLU_* domainler (kullanici dogrulamali olanlar HARIC)
  deadSources     : enum adi brand ile eslesen, tum varyantlari OLU kaynaklar
  titleOverrides  : tasinan/rebrand sitelerin guncel gorunen adlari

Calisma: python 06_prepare_assets.py
"""

import json
import os
import time

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(BASE, "data")
ASSETS = os.path.join(BASE, "extension", "src", "main", "assets")

DEAD_STATUSES = {
    "OLU_DNS_KAYDI_YOK",
    "OLU_HTTP_SUNUCU_KAPALI",
    "OLU_SPAM_KUMAR_YONLENDIRME",
}
REPAIR_STATUSES = {
    "OTOMATIK_TAMIR_YONLENDIRME",
    "OTOMATIK_TAMIR_ALTERNATIF",
}


def load(path, default=None):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def as_list(doc):
    if isinstance(doc, list):
        return doc
    return (doc or {}).get("sources", (doc or {}).get("results", []))


def bare(host):
    return (host or "").lower().removeprefix("www.").strip()


def main():
    liveness = as_list(load(os.path.join(DATA, "liveness.json"), []))
    alive = as_list(load(os.path.join(DATA, "alive_sources.json"), []))
    catalogue = load(os.path.join(DATA, "catalogue.json"), {})

    domain_overrides = {}
    title_overrides = {}
    dead_hosts = set()
    alive_domains = {bare(s.get("domain")) for s in alive}
    alive_brands = {s.get("brand") for s in alive if s.get("brand")}

    for r in liveness:
        status = r.get("status", "")
        old = bare(r.get("domain"))
        src = r.get("source") or {}
        brand = src.get("brand") or ""

        if status in REPAIR_STATUSES:
            new = bare(r.get("repaired_domain") or (src.get("domain") or ""))
            if old and new and old != new:
                domain_overrides[old] = new
                # motor enum'u brand adini kullaniyorsa enum-anahtarli override da ver
                if brand:
                    domain_overrides[brand.upper()] = new
                title = src.get("name")
                if title and new.rstrip(".") != old.rstrip("."):
                    title_overrides[brand.upper() or old] = title

        elif status in DEAD_STATUSES and not src.get("verified_by_user"):
            dead_hosts.add(old)
            for alt in src.get("altDomains") or []:
                dead_hosts.add(bare(alt))

    # brand'in TUM domainleri oluysa enum'u da oldur (canli varyanti yoksa)
    dead_sources = set()
    for r in liveness:
        src = r.get("source") or {}
        brand = src.get("brand")
        if (
            r.get("status") in DEAD_STATUSES
            and not src.get("verified_by_user")
            and brand
            and brand not in alive_brands
            and bare(src.get("domain")) not in alive_domains
        ):
            dead_sources.add(brand.upper())

    # ---- bakım bacasının KALICI kararları (07_maintain.py) ----
    # overrides.json liveness'in ÜZERİNE yazılır; unpinned listesi bayat
    # liveness pin'lerini kalıcı olarak susturur (spam faciası tekrarı olmasın).
    ov = load(os.path.join(DATA, "maintenance", "overrides.json"), {}) or {}
    unpinned = set(ov.get("unpinned") or [])
    for k in list(domain_overrides):
        if k in unpinned:
            del domain_overrides[k]
    domain_overrides.update(ov.get("domainOverrides") or {})
    dead_sources |= set(ov.get("deadSources") or [])
    dead_hosts |= {bare(h) for h in (ov.get("deadHosts") or [])}
    # Kendini iyileştirme (07): domain'ı CANLI doğrulanmış kaynak/host, bayat
    # liveness birleşiminden de düşürülür — yanlış karantina bir daha yapışmaz.
    dead_sources -= set(ov.get("revivedSources") or [])
    dead_hosts -= {bare(h) for h in (ov.get("revivedHosts") or [])}

    patches = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "domainOverrides": dict(sorted(domain_overrides.items())),
        "deadSources": sorted(dead_sources),
        "deadHosts": sorted(dead_hosts),
        "titleOverrides": dict(sorted(title_overrides.items())),
    }

    # katalog tekilleştirme: aynı (domain, lang) => AYNI Mihon id'si => çakışma.
    if isinstance(catalogue, dict) and isinstance(catalogue.get("sources"), list):
        seen, uniq = set(), []
        for s in catalogue["sources"]:
            key = (bare(s.get("domain")), (s.get("lang") or "all").lower())
            if key in seen:
                continue
            seen.add(key)
            uniq.append(s)
        dropped = len(catalogue["sources"]) - len(uniq)
        if dropped:
            catalogue = dict(catalogue, sources=uniq)
            print(f"[06] katalog tekilleştirme: {dropped} aynı-domain kaydı elendi")

    os.makedirs(ASSETS, exist_ok=True)
    cat_out = os.path.join(ASSETS, "catalogue.json")
    with open(cat_out, "w", encoding="utf-8") as f:
        json.dump(catalogue, f, ensure_ascii=False)
    pat_out = os.path.join(ASSETS, "patches.json")
    with open(pat_out, "w", encoding="utf-8") as f:
        json.dump(patches, f, ensure_ascii=False)

    print(f"[06] catalogue -> {cat_out} ({catalogue.get('total_count', '?')} kaynak)")
    print(f"[06] patches   -> {pat_out}")
    print(f"  domainOverrides : {len(patches['domainOverrides'])}")
    print(f"  deadSources     : {len(patches['deadSources'])}")
    print(f"  deadHosts       : {len(patches['deadHosts'])}")
    print(f"  titleOverrides  : {len(patches['titleOverrides'])}")


if __name__ == "__main__":
    main()
