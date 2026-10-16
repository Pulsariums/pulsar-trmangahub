#!/usr/bin/env python3
"""Pulsar-V2 - Aşama 1: Çok Dilli Kaynak Toplayıcı.

Bu script 5 farklı kaynaktan tüm manga kaynaklarını toplar ve ortak bir şemaya dönüştürür:
1. Yerel TR kaynakları: sources/tr/sources.json
2. Yerel Global kaynakları: sources/global/sources.json (varsa)
3. Yerel Özel kaynaklar: sources/custom/sources.json
4. Kullanıcının Kototoro export'u (Zemin gerçeği): sources/tr/verified_working_kototoro_export.json
5. Keiyoushi Extension Repo: canli index veya yerel onbellek
6. Nyora Data-Driven Kataloğu: https://raw.githubusercontent.com/Nyora-Manga/nyora-data-driven/main/catalogue.json

Çıktı: pulsar-v2/data/raw_sources.json
"""

import json
import os
import re
import sys
import urllib.request
import urllib.error

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PULSAR_V2_DIR = os.path.join(ROOT_DIR, "pulsar-v2")
DATA_DIR = os.path.join(PULSAR_V2_DIR, "data")
OUT_FILE = os.path.join(DATA_DIR, "raw_sources.json")

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) PulsarV2-Aggregator/2.0"


def fetch_json(url, timeout=15):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        print(f"  [UYARI] {url} cekilemedi: {e}")
        return None


def clean_domain(url_or_domain):
    if not url_or_domain:
        return ""
    d = str(url_or_domain).strip().lower()
    d = re.sub(r"^https?://", "", d)
    d = d.split("/")[0]
    d = re.sub(r"^www\.", "", d)
    return d


def normalize_entry(raw_id, name, lang, nsfw, domain, base_url, engine, config=None, origin="unknown", verified=False):
    d = clean_domain(domain or base_url)
    if not d:
        return None
    b_url = base_url.strip() if base_url else f"https://{d}"
    if not b_url.startswith("http"):
        b_url = f"https://{b_url}"

    return {
        "id": raw_id or d.replace(".", "_").upper(),
        "name": (name or d).strip(),
        "lang": (lang or "tr").lower(),
        "nsfw": 1 if nsfw in (1, True, "1", "true") else 0,
        "domain": d,
        "baseUrl": b_url.rstrip("/"),
        "engine": (engine or "custom").lower(),
        "config": config or {},
        "origins": [origin],
        "verified_by_user": bool(verified)
    }


def main():
    os.makedirs(DATA_DIR, exist_ok=True)
    all_raw = []

    # 1. Kullanicinin dogruladigi paketler
    verified_file = os.path.join(ROOT_DIR, "sources", "tr", "verified_working_kototoro_export.json")
    verified_pkgs = set()
    if os.path.exists(verified_file):
        try:
            with open(verified_file, encoding="utf-8") as f:
                v_data = json.load(f)
            verified_pkgs = set(v_data.get("verified_mihon_packages", []))
            print(f"[1] Kullanici dogrulanmis paket listesi okundu: {len(verified_pkgs)} adet")
        except Exception as e:
            print(f"[1] verified file hatasi: {e}")

    # 2. Yerel sources/tr/sources.json
    tr_file = os.path.join(ROOT_DIR, "sources", "tr", "sources.json")
    if os.path.exists(tr_file):
        with open(tr_file, encoding="utf-8") as f:
            tr_data = json.load(f)
        count = 0
        for s in tr_data.get("sources", []):
            formats = s.get("formats") or {}
            mihon_fmt = formats.get("mihon") or {}
            pkg = mihon_fmt.get("pkg", "")
            pkg_short = pkg.split(".")[-1] if pkg else ""
            is_verified = (pkg_short in verified_pkgs) or s.get("verifiedWorkingByUser", False)
            entry = normalize_entry(
                raw_id=s.get("id"),
                name=s.get("name"),
                lang=s.get("lang") or "tr",
                nsfw=s.get("isNsfw") or s.get("nsfw") or 0,
                domain=s.get("domain"),
                base_url=s.get("baseUrl"),
                engine=s.get("engine"),
                origin="local_tr",
                verified=is_verified
            )
            if entry:
                all_raw.append(entry)
                count += 1
        print(f"[2] sources/tr/sources.json okundu: {count} kaynak")

    # 3. Yerel sources/global/sources.json
    global_file = os.path.join(ROOT_DIR, "sources", "global", "sources.json")
    if os.path.exists(global_file):
        with open(global_file, encoding="utf-8") as f:
            g_data = json.load(f)
        count = 0
        for s in g_data.get("sources", []):
            entry = normalize_entry(
                raw_id=s.get("id"),
                name=s.get("name"),
                lang=s.get("lang") or "all",
                nsfw=s.get("isNsfw") or s.get("nsfw") or 0,
                domain=s.get("domain"),
                base_url=s.get("baseUrl"),
                engine=s.get("engine"),
                origin="local_global",
                verified=False
            )
            if entry:
                all_raw.append(entry)
                count += 1
        print(f"[3] sources/global/sources.json okundu: {count} kaynak")

    # 4. Yerel sources/custom/sources.json
    custom_file = os.path.join(ROOT_DIR, "sources", "custom", "sources.json")
    if os.path.exists(custom_file):
        with open(custom_file, encoding="utf-8") as f:
            c_data = json.load(f)
        c_sources = c_data if isinstance(c_data, list) else c_data.get("sources", [])
        count = 0
        for s in c_sources:
            entry = normalize_entry(
                raw_id=s.get("id"),
                name=s.get("name"),
                lang=s.get("lang") or "tr",
                nsfw=s.get("isNsfw") or s.get("nsfw") or 0,
                domain=s.get("domain"),
                base_url=s.get("baseUrl"),
                engine=s.get("engine"),
                origin="local_custom",
                verified=False
            )
            if entry:
                all_raw.append(entry)
                count += 1
        print(f"[4] sources/custom/sources.json okundu: {count} kaynak")

    # 5. Nyora Data-Driven Kataloğu (Canlı Çekim)
    print("[5] Nyora data-driven catalogue cekiliyor...")
    nyora_url = "https://raw.githubusercontent.com/Nyora-Manga/nyora-data-driven/main/catalogue.json"
    nyora_data = fetch_json(nyora_url)
    if nyora_data and "sources" in nyora_data:
        count = 0
        for s in nyora_data["sources"]:
            entry = normalize_entry(
                raw_id=s.get("id"),
                name=s.get("name"),
                lang=s.get("lang") or "all",
                nsfw=1 if s.get("nsfw") or s.get("contentType") == "HENTAI" else 0,
                domain=s.get("domain"),
                base_url=f"https://{s.get('domain')}" if s.get("domain") else None,
                engine=s.get("engine"),
                config=s.get("config"),
                origin="nyora_datadriven",
                verified=False
            )
            if entry:
                all_raw.append(entry)
                count += 1
        print(f"[5] Nyora catalogue eklendi: {count} kaynak")
    else:
        print("[5] Nyora verisi alinamadi, atlandi.")

    # 6. Keiyoushi Extension Repo (TR Filtreli + Genel)
    print("[6] Keiyoushi index.json cekiliyor...")
    kei_url = "https://raw.githubusercontent.com/keiyoushi/extensions/repo/index.json"
    kei_raw = fetch_json(kei_url)
    kei_data = []
    if isinstance(kei_raw, dict):
        ext_list = kei_raw.get("extensionList")
        if isinstance(ext_list, dict):
            kei_data = ext_list.get("extensions", [])
        elif isinstance(ext_list, list):
            kei_data = ext_list
    elif isinstance(kei_raw, list):
        kei_data = kei_raw

    if kei_data:
        count = 0
        for pkg in kei_data:
            pkg_name = pkg.get("packageName", "")
            pkg_short = pkg_name.split(".")[-1] if pkg_name else ""
            is_verified = pkg_short in verified_pkgs
            is_nsfw = 1 if "NSFW" in str(pkg.get("contentWarning", "")) else 0
            for s in pkg.get("sources", []):
                b_url = s.get("homeUrl") or s.get("baseUrl") or ""
                lang = (s.get("language") or s.get("lang") or "all").lower()
                entry = normalize_entry(
                    raw_id=s.get("id"),
                    name=s.get("name"),
                    lang=lang,
                    nsfw=is_nsfw,
                    domain=clean_domain(b_url),
                    base_url=b_url,
                    engine="keiyoushi",
                    origin="keiyoushi_index",
                    verified=is_verified
                )
                if entry:
                    all_raw.append(entry)
                    count += 1
        print(f"[6] Keiyoushi kaynaklari eklendi: {count} kaynak")
    else:
        print("[6] Keiyoushi index alinamadi, yerel verilerle devam ediliyor.")

    # Kaydet
    with open(OUT_FILE, "w", encoding="utf-8") as f:
        json.dump(all_raw, f, ensure_ascii=False, indent=2)

    tr_count = sum(1 for x in all_raw if x["lang"] == "tr")
    verified_count = sum(1 for x in all_raw if x["verified_by_user"])
    print(f"\n[TAMAMLANDI] Toplam toplanan ham kaynak: {len(all_raw)}")
    print(f"  - Türkçe (TR) kaynaklar: {tr_count}")
    print(f"  - Kullanıcı tarafından doğrulanmış: {verified_count}")
    print(f"  - Çıktı: {OUT_FILE}")


if __name__ == "__main__":
    main()
