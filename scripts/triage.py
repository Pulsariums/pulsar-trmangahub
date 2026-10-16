#!/usr/bin/env python3
"""Asama 0 - envanter: sources/tr/sources.json'daki her kaydin GERCEKTE yayinda olan jar kod
yolunu cozer (override > generated > yalniz-mihon) ve data/triage.json'a yazar.

Bir domain icin uc durum olabilir:
  - override: overrides/<upstream yolu> altinda elle onarilmis bir dosya var (bu, upstream'in
    kendisinin yerine gecer; otomatik onarim BURAYA yazilmali).
  - generated: generated/<domain>/jar/<Class>.kt var (bizim scaffold'umuz; sources/custom'da
    kayitli). formats.jar alani published.json'da varsa yayinda, yoksa deneme asamasinda.
  - mihon_only: jar formati yok, yalniz resmi Mihon APK aynasinda.

Kullanim: python scripts/triage.py
Cikti: data/triage.json
"""
import json
import os
import re

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SOURCES_PATH = os.path.join(BASE_DIR, "sources", "tr", "sources.json")
PUBLISHED_PATH = os.path.join(BASE_DIR, "sources", "tr", "published.json")
CUSTOM_PATH = os.path.join(BASE_DIR, "sources", "custom", "sources.json")
OVERRIDES_DIR = os.path.join(BASE_DIR, "overrides")
GENERATED_DIR = os.path.join(BASE_DIR, "generated")
OUT_PATH = os.path.join(BASE_DIR, "data", "triage.json")

ANN_RE = re.compile(r'@MangaSourceParser\("([A-Z0-9_]+)"')


def load_json(path, default=None):
    if not os.path.isfile(path):
        return default
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def as_list(d):
    if d is None:
        return []
    return d.get("sources", d) if isinstance(d, dict) else d


def index_overrides():
    """rel upstream path -> absolute override file path."""
    idx = {}
    if not os.path.isdir(OVERRIDES_DIR):
        return idx
    for root, _dirs, names in os.walk(OVERRIDES_DIR):
        for name in names:
            if not name.endswith(".kt"):
                continue
            path = os.path.join(root, name)
            rel = os.path.relpath(path, OVERRIDES_DIR).replace(os.sep, "/")
            idx[rel] = path
    return idx


def main():
    sources = as_list(load_json(SOURCES_PATH, []))
    published = load_json(PUBLISHED_PATH, {}) or {}
    custom = load_json(CUSTOM_PATH, []) or []
    overrides_idx = index_overrides()

    published_jar_by_parser = {}
    for e in published.get("jar", []) or []:
        if e.get("parser") and e.get("file"):
            published_jar_by_parser[e["parser"]] = e

    custom_by_domain = {c.get("domain"): c for c in custom if c.get("domain")}

    entries = []
    for src in sources:
        domain = src.get("domain")
        if not domain:
            continue
        engine = src.get("engine") or ((src.get("formats") or {}).get("catalog") or {}).get("engine")
        jar_fmt = (src.get("formats") or {}).get("jar")
        parser_id = jar_fmt.get("parser") if jar_fmt else None

        pub = published_jar_by_parser.get(parser_id) if parser_id else None
        upstream_rel = pub.get("file") if pub else None
        override_path = overrides_idx.get(upstream_rel) if upstream_rel else None

        generated_rel = None
        c = custom_by_domain.get(domain)
        if c and c.get("scaffold"):
            generated_rel = c["scaffold"][0]
        elif os.path.isdir(os.path.join(GENERATED_DIR, domain, "jar")):
            for name in os.listdir(os.path.join(GENERATED_DIR, domain, "jar")):
                if name.endswith(".kt"):
                    generated_rel = f"generated/{domain}/jar/{name}"
                    break

        if override_path:
            kind = "override"
            code_rel = os.path.relpath(override_path, BASE_DIR).replace(os.sep, "/")
        elif upstream_rel:
            kind = "upstream"
            code_rel = upstream_rel
        elif generated_rel:
            kind = "generated"
            code_rel = generated_rel
        else:
            kind = "mihon_only"
            code_rel = None

        entries.append({
            "domain": domain,
            "name": src.get("name"),
            "engine": engine,
            "status": src.get("status"),
            "nsfw": bool(src.get("nsfw")),
            "parser_id": parser_id,
            "kind": kind,
            "code_path": code_rel,
            "published_domain_mismatch": bool(pub and pub.get("domain") and pub.get("domain") != domain),
            "published_domain": pub.get("domain") if pub else None,
        })

    by_kind = {}
    for e in entries:
        by_kind[e["kind"]] = by_kind.get(e["kind"], 0) + 1

    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as fh:
        json.dump({"entries": entries, "counts": by_kind}, fh, ensure_ascii=False, indent=2)
        fh.write("\n")

    print(f"Output: {OUT_PATH}")
    print(f"  total={len(entries)} by_kind={by_kind}")
    mismatches = [e["domain"] for e in entries if e["published_domain_mismatch"]]
    if mismatches:
        print(f"  domain mismatch (published.json vs sources.json): {mismatches}")


if __name__ == "__main__":
    main()
