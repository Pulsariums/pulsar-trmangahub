#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Nyora generate-repo.py örüntüsü — kendi varyantımız.

Derlenmiş APK'lardan repo/ yayınını üretir:
  index.min.json : eklenti dizini (NetworkLegacyExtension[])
  repo.json      : depo metadata'si; signingKeyFingerprint APK'nın İMZASINDAN
                   otomatik okunur (elle yazılamaz — Nyora'nın kanıtladığı gibi
                   APK/index/repo.json üçgeni aynı anahtardan doğar).

Sürüm (versionCode/versionName) ve tachiyomix.extensionLib APK'nın KENDİSİNDEN
okunur. KONTRAT BEKÇİSİ: versionName'in major.minor'u manifest extensionLib'e
eşit değilse build PATLAR — Mihon'un "kalıcı güncelleme rozeti" tuzağı (bkz.
ExtensionManager.updateExists: repo libVersion = version.substringBeforeLast('.')).

Kullanım:
    generate_repo.py <repo-build-dir> [pulsar_build.sh ile aynı FLAVORS listesi]
    aapt/apksigner yoksa (yerel geliştirmede) hata verir — CI'da SDK hazırdır.
"""

import glob
import json
import os
import re
import shutil
import struct
import subprocess
import sys

WEBSITE = "https://github.com/Pulsariums/pulsar-trmangahub"

# pulsar_build.sh ile AYNI eşleme (tek kaynak doğruluk: flavor -> ad/nsfw)
FLAVOR_DEFS = {
    ".tr":      {"name": "Pulsar TR",        "lang": "tr",  "nsfw": 0},
    ".tr18":    {"name": "Pulsar TR 18+",    "lang": "tr",  "nsfw": 1},
    ".global":  {"name": "Pulsar Global",    "lang": "all", "nsfw": 0},
    ".global18": {"name": "Pulsar Global 18+", "lang": "all", "nsfw": 1},
}


def load_status(repo_dir):
    """Tek durum dosyası: pulsar-v2/data/source-status.json (health + cihaz testi)."""
    path = os.path.join(os.path.dirname(repo_dir), "data", "source-status.json")
    if not os.path.exists(path):
        print(f"  ! durum dosyası yok: {path} — sources boş kalacak", file=sys.stderr)
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f).get("sources", {})


def load_dropped_ids(repo_dir):
    """pulsar merge'in elediği katalog klonlarının id'leri (data/merge-report.json).

    Bu id'ler APK'da artık YOK; indekse yazılırsa istemci olmayan kaynağı
    listeler. Rapor yoksa (ilk derleme / araç çalışmadıysa) boş küme döner.
    """
    path = os.path.join(os.path.dirname(repo_dir), "data", "merge-report.json")
    try:
        with open(path, encoding="utf-8") as f:
            return {str(i) for i in (json.load(f).get("dropped_ids") or [])}
    except (OSError, ValueError):
        return set()


def load_runtime_filters(repo_dir):
    """Eklentinin ÇALIŞMA ANINDA uyguladığı elemeler.

    İndeks "aktif" sayarken eklenti ayrıca patches.json'daki deadSources /
    deadHosts listesine bakıp kaynağı hiç oluşturmuyor. Bu ikisi eşitlenmezse
    depo kartı 48, yüklü kart 45 gösterir (TR'de tam olarak bu oldu:
    RobinManga, NoxScans, MangaKazani).
    """
    base = os.path.dirname(repo_dir)
    filters = {"dead_hosts": set(), "dead_sources": set(), "engine_name": {}}
    try:
        with open(os.path.join(base, "extension", "src", "main", "assets", "patches.json"),
                  encoding="utf-8") as f:
            patches = json.load(f)
        filters["dead_hosts"] = {
            (h or "").lower().removeprefix("www.") for h in patches.get("deadHosts") or []
        }
        filters["dead_sources"] = set(patches.get("deadSources") or [])
    except (OSError, ValueError):
        pass
    try:
        with open(os.path.join(repo_dir, "source_map.json"), encoding="utf-8") as f:
            source_map = json.load(f)
        filters["engine_name"] = {
            str(e.get("id")): e.get("name", "") for e in source_map.get("engine") or []
        }
    except (OSError, ValueError):
        pass
    return filters


def runtime_filtered(entry, filters):
    """Bu kayıt eklenti tarafından oluşturulmuyor mu?"""
    kind = entry.get("kind")
    if kind == "catalogue":
        host = (entry.get("domain") or "").lower().removeprefix("www.")
        return host in filters["dead_hosts"]
    if kind == "engine":
        name = filters["engine_name"].get(str(entry.get("id", "")))
        return bool(name) and name in filters["dead_sources"]
    return False


def package_sources(status, suffix, dropped=(), filters=None):
    """Yalnız state=active ve paketi eşleşen kaynaklar indekse girer."""
    pkg = suffix.lstrip(".")
    filters = filters or {"dead_hosts": set(), "dead_sources": set(), "engine_name": {}}
    rows = []
    for entry in status.values():
        if entry.get("state") != "active":
            continue
        if pkg not in (entry.get("packages") or []):
            continue
        if str(entry.get("id", "")) in dropped:
            continue
        if runtime_filtered(entry, filters):
            continue
        rows.append({
            "name": entry.get("title") or "",
            "id": str(entry.get("id", "")),
            "lang": entry.get("lang") or "all",
            "baseUrl": f"https://{entry.get('domain')}" if entry.get("domain") else "",
        })
    rows.sort(key=lambda r: r["name"].lower())
    return rows


def write_pending_report(repo_dir, status):
    """Çalışmayan/bekleyen kaynaklar silinmez; sebebiyle burada raporlanır."""
    path = os.path.join(os.path.dirname(repo_dir), "data", "pending-sources.md")
    lines = [
        "# Beklemedeki kaynaklar",
        "",
        "Bu kaynaklar yayınlanan paketlerde aktif değil; sebebiyle birlikte burada dururlar.",
        "",
        "| Paket | Kaynak | Dil | Domain | Sebep |",
        "|---|---|---|---|---|",
    ]
    rows = [e for e in status.values() if e.get("state") != "active"]
    rows.sort(key=lambda e: (",".join(e.get("packages") or []), (e.get("title") or "").lower()))
    for e in rows:
        health = e.get("health") or {}
        device = e.get("device") or {}
        reason = health.get("status") or device.get("status") or e.get("state") or ""
        detail = (health.get("detail") or device.get("detail") or "").replace("|", "/")[:90]
        lines.append(
            f"| {','.join(e.get('packages') or [])} | {e.get('title','')} | "
            f"{e.get('lang','')} | {e.get('domain','')} | {reason} {detail} |"
        )
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"  beklemede: {len(rows)} kaynak -> {path}")


_SDK_ROOTS = [
    os.environ.get("ANDROID_HOME"),
    os.environ.get("ANDROID_SDK_ROOT"),
    os.path.expanduser("~/Library/Android/sdk"),
    os.path.expanduser("~/Android/Sdk"),
]


def _find_tool(name):
    for root in filter(None, _SDK_ROOTS):
        cands = sorted(glob.glob(os.path.join(root, "build-tools", "*", name)))
        if cands:
            return cands[-1]
    onpath = shutil.which(name)
    if onpath:
        return onpath
    raise FileNotFoundError(f"{name} not found (set ANDROID_HOME)")


def cert_fingerprint(apk):
    out = subprocess.run([_find_tool("apksigner"), "verify", "--print-certs", apk],
                         capture_output=True, text=True).stdout
    m = re.search(r"certificate SHA-256 digest:\s*([0-9a-fA-F]+)", out)
    return m.group(1).lower() if m else ""


def apk_version(apk):
    out = subprocess.run([_find_tool("aapt"), "dump", "badging", apk],
                         capture_output=True, text=True).stdout
    m = re.search(r"versionCode='(\d+)' versionName='([^']+)'", out)
    if not m:
        raise RuntimeError(f"versionCode/versionName okunamadi: {apk}")
    return int(m.group(1)), m.group(2)


def apk_extension_lib(apk):
    """tachiyomix.extensionLib manifest float'ı (Mihon'un libVersion'ı)."""
    out = subprocess.run([_find_tool("aapt"), "dump", "xmltree", apk, "AndroidManifest.xml"],
                         capture_output=True, text=True).stdout
    m = re.search(r"tachiyomix\.extensionLib.*?\n.*?=\(type 0x4\)0x([0-9a-fA-F]{8})", out)
    if not m:
        raise RuntimeError(f"tachiyomix.extensionLib yok: {apk}")
    return struct.unpack(">f", struct.pack(">I", int(m.group(1), 16)))[0]


def main(repo_dir, flavors="tr,tr18,global,global18"):
    suffixes = ["." + f.strip().removeprefix(".") for f in flavors.split(",")]

    status = load_status(repo_dir)
    dropped_ids = load_dropped_ids(repo_dir)
    filters = load_runtime_filters(repo_dir)
    index = []
    fingerprint = None
    for suffix in suffixes:
        meta = FLAVOR_DEFS.get(suffix)
        if not meta:
            print(f"  ! bilinmeyen flavor {suffix} — atlandı", file=sys.stderr)
            continue
        pkg = f"eu.kanade.tachiyomi.extension.all.pulsar{suffix}"
        apk = f"{pkg}.apk"
        path = os.path.join(repo_dir, "apk", apk)
        if not os.path.exists(path):
            print(f"  ! eksik apk {apk} — atlandı", file=sys.stderr)
            continue
        fp = cert_fingerprint(path)
        if fingerprint and fp != fingerprint:
            sys.exit(f"::error::{apk} FARKLI anahtarla imzalı ({fp}) — tüm paketler tek anahtar olmalı")
        fingerprint = fp
        code, version = apk_version(path)
        lib = apk_extension_lib(path)
        major_minor = version.rsplit(".", 1)[0]
        if abs(float(major_minor) - lib) > 1e-6:
            sys.exit(
                f"::error::{apk} versionName '{version}' libVersion {major_minor} diyor "
                f"ama manifest extensionLib {lib} — Mihon KALICI güncelleme rozeti basar. "
                f"versionName '<extensionLib>.<patch>' kontratına uydur."
            )
        index.append({
            "name": meta["name"], "pkg": pkg, "apk": apk,
            "lang": meta["lang"], "code": code, "version": version,
            "nsfw": meta["nsfw"], "sources": package_sources(status, suffix, dropped_ids, filters),
        })

    if not index:
        sys.exit("::error::repo-build/apk içinde derlenmiş APK yok")

    # ikonlar: uzantı resourcelarından kopyala (opsiyonel)
    icon_dir = os.path.join(repo_dir, "icon")
    os.makedirs(icon_dir, exist_ok=True)
    for e in index:
        for cand in glob.glob(os.path.join(os.path.dirname(repo_dir), "extension", "src", "main", "res", "mipmap-*", "ic_launcher.png")):
            dest = os.path.join(icon_dir, f"{e['pkg']}.png")
            if not os.path.exists(dest):
                shutil.copy(cand, dest)
            break

    with open(os.path.join(repo_dir, "index.min.json"), "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False)
    with open(os.path.join(repo_dir, "repo.json"), "w", encoding="utf-8") as f:
        json.dump({
            "index_v2": None,
            "meta": {
                "name": "Pulsar Manga Hub",
                "shortName": "Pulsar",
                "website": WEBSITE,
                "signingKeyFingerprint": fingerprint,
            },
        }, f, ensure_ascii=False, indent=2)
    write_pending_report(repo_dir, status)
    print(f"  wrote index for {len(index)} extension(s); fingerprint={fingerprint[:16]}...")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "repo-build",
         sys.argv[2] if len(sys.argv) > 2 else "tr,tr18,global,global18")
