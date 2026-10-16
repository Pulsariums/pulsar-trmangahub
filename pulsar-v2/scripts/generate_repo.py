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
            "nsfw": meta["nsfw"], "sources": None,
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
    print(f"  wrote index for {len(index)} extension(s); fingerprint={fingerprint[:16]}...")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "repo-build",
         sys.argv[2] if len(sys.argv) > 2 else "tr,tr18,global,global18")
