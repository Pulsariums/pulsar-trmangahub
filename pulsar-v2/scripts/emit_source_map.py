#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""emit_source_map.py — kaynak id -> kaynak haritası (bakım bacasının gözü).

Canlı test sonuçları MIHON_<Long id> adları taşıyor; patches.json ise parser
ENUM ADI / domain ile çalışıyor. Bu script ikisi arasındaki çeviriyi DERLEME
anında üretir:

  1) Motor (kotatsu):  upstream kotatsu-parsers-redo kaynak ağacındaki
     @MangaSourceParser("NAME", "Title", "locale"[, ContentType.X]) taraması.
     KSP enum'ı tam olarak bu annotation'lardan doğar; id'miz deterministik:
     hash("pulsar-kotatsu/NAME/lang").  @Broken işaretini de taşır — upstream
     kendi kaynağını bozuk sayıyorsa bakım için altın bilgi.
  2) Katalog:          bizim catalogue.json; id = hash("pulsar/domain/lang").

Çıktı: repo-build/source_map.json (generate_repo yayın adımları köke de kopyalar)
        { "engine": [{id,name,title,lang,nsfw,broken,domain}...],
          "catalogue": [{id,name,domain,lang,nsfw,engine}...] }

Kullanım: emit_source_map.py <parsers-repo-dir> <catalogue.json> <out.json>
"""

import json
import os
import re
import sys
import time

# Kotlin tarafıyla AYNI hash (PulsarKotatsuSource / PulsarSource):
#   var h = 1125899906842597L; for (ch in key) h = 31*h + ch.code ; h and MAX_VALUE
_MASK64 = 0xFFFFFFFFFFFFFFFF


def pulsar_id(key: str) -> int:
    h = 1125899906842597
    for ch in key:
        h = (31 * h + ord(ch)) & _MASK64
    return h & 0x7FFFFFFFFFFFFFFF


ANNOT = re.compile(
    r'@MangaSourceParser\(\s*"([A-Z0-9_]+)"\s*,\s*"([^"]*)"\s*(?:,\s*"([a-z-]+)"?)?'
    r'((?:\s*,\s*ContentType\.[A-Z_]+)?)\)',
)


def scan_engine(parsers_dir: str):
    src_root = os.path.join(parsers_dir, "src", "main", "kotlin")
    rows = []
    for dirpath, _, files in os.walk(src_root):
        for fn in files:
            if not fn.endswith(".kt"):
                continue
            path = os.path.join(dirpath, fn)
            try:
                with open(path, encoding="utf-8") as f:
                    text = f.read()
            except (OSError, UnicodeDecodeError):
                continue
            for m in ANNOT.finditer(text):
                name, title, locale, ctype = m.group(1), m.group(2), m.group(3) or "", m.group(4) or ""
                nsfw = 1 if "HENTAI" in ctype or "ADULT" in ctype else 0
                broken = re.search(
                    r"@Broken\s*(?:@[^\r\n]*\s*)*@MangaSourceParser\(\s*\"" + re.escape(name) + r'"',
                    text) is not None
                # ENEME: dosyadaki İLK "MangaParserSource.X, \"domain\"" kardeş
                # şablon çağrısı olabilir (RobinManga->guildknives yanılgısı).
                # Yalnız bu enum'un kendi ctor satırındaki domain'i alır.
                dm = re.search(
                    r'MangaParserSource\.' + re.escape(name) +
                    r',\s*"([A-Za-z0-9.-]+\.[A-Za-z]{2,})"', text)
                domain = dm.group(1).lower() if dm else ""
                lang = locale if locale else "all"
                rows.append({
                    "id": pulsar_id(f"pulsar-kotatsu/{name}/{lang}"),
                    "kind": "engine",
                    "name": name,
                    "title": title,
                    "lang": lang,
                    "nsfw": nsfw,
                    "broken": bool(broken),
                    "domain": domain,
                    "file": os.path.relpath(path, src_root).replace("\\", "/"),
                })
    return rows


def scan_catalogue(cat_path: str):
    with open(cat_path, encoding="utf-8") as f:
        cat = json.load(f)
    srcs = cat["sources"] if isinstance(cat, dict) else cat
    rows = []
    for s in srcs:
        domain = (s.get("domain") or "").lower().removeprefix("www.")
        lang = (s.get("lang") or "all").lower()
        rows.append({
            "id": pulsar_id(f"pulsar/{domain}/{lang}"),
            "kind": "catalogue",
            "name": s.get("name", ""),
            "title": s.get("name", ""),
            "lang": lang,
            "nsfw": int(s.get("nsfw", 0) or 0),
            "domain": domain,
            "engine": s.get("engine", "custom"),
        })
    return rows


def main():
    if len(sys.argv) != 4:
        print(__doc__)
        sys.exit(2)
    parsers_dir, cat_path, out_path = sys.argv[1:]
    engine = scan_engine(parsers_dir)
    catalogue = scan_catalogue(cat_path)
    seen = {}
    for r in engine + catalogue:
        if r["id"] in seen:
            print(f"[UYARI] id çakışması: {r['id']} {seen[r['id']]['name']} vs {r['name']}")
        seen[r["id"]] = r
    doc = {
        "generated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "note": "id = Kotlin PulsarKotatsuSource/PulsarSource hash'inin Python kopyası; "
                "bakım bacası (07_maintain.py) MIHON_<id> -> kaynak eşlemesini bundan yapar.",
        "engine": sorted(engine, key=lambda r: r["name"]),
        "catalogue": sorted(catalogue, key=lambda r: r["name"]),
    }
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=1)
    tr = sum(1 for r in engine if r["lang"] == "tr")
    broken = sum(1 for r in engine if r["broken"])
    print(f"[map] motor: {len(engine)} enum (tr:{tr}, broken:{broken}) + katalog: {len(catalogue)} -> {out_path}")


if __name__ == "__main__":
    main()
