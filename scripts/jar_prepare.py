#!/usr/bin/env python3
"""Prepare a Kotatsu-Redo checkout for the Kototoro JAR build.

Steps, in order:
  a) patches: the sed replacements of .github/workflows/release.yml, each required exactly once
  b) selection: @MangaSourceParser IDs kept by mode (alive / all_tr) and the broken rule
  c) deletion: files whose parsers are all dropped are removed, except files whose
     top-level class names are referenced (transitively) by kept files
  d) domain repair: quarantined/failing sources with a qualifying alternative keep their
     file and get the old domain literal replaced by the new one
  e) report: JSON written to --report
"""

import argparse
import json
import os
import re
import subprocess
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KT_ROOT = os.path.join("src", "main", "kotlin")
PARSERS_DIR = os.path.join(KT_ROOT, "org", "koitharu", "kotatsu", "parsers")

PATCHES = [
    (os.path.join(PARSERS_DIR, "MangaParser.kt"),
     "public val source: MangaParserSource", "public val source: MangaSource"),
    (os.path.join(PARSERS_DIR, "Broken.kt"),
     "@Retention(AnnotationRetention.SOURCE)", "@Retention(AnnotationRetention.RUNTIME)"),
    (os.path.join(PARSERS_DIR, "Broken.kt"),
     "internal annotation class Broken", "public annotation class Broken"),
    (os.path.join(PARSERS_DIR, "MangaSourceParser.kt"),
     "@Retention(AnnotationRetention.SOURCE)", "@Retention(AnnotationRetention.RUNTIME)"),
    (os.path.join(PARSERS_DIR, "MangaSourceParser.kt"),
     "internal annotation class MangaSourceParser", "public annotation class MangaSourceParser"),
]

PUBLISHED = ("published", "cf_protected_published")
ALT_STATUSES = ("quarantined", "failing")
RANK = {"high": 3, "medium": 2, "low": 1}

ANN_RE = re.compile(r'@MangaSourceParser\(\s*"([^"]+)"\s*,\s*"([^"]*)"\s*,\s*"([A-Za-z_-]+)"')
BROKEN_RE = re.compile(r"@Broken\b")
CLASS_DEF_RE = re.compile(r"\b(?:class|object|interface)\s+([A-Z]\w*)")
IDENT_RE = re.compile(r"\b[A-Z]\w*\b")
STRIP_RE = re.compile(r'//[^\n]*|/\*.*?\*/|"(?:\\.|[^"\\\n])*"', re.S)


def fail(message):
    print(f"jar_prepare: {message}", file=sys.stderr)
    raise SystemExit(2)


def read_text(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def write_text(path, text):
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


def apply_patches(upstream):
    for rel, old, new in PATCHES:
        path = os.path.join(upstream, rel)
        if not os.path.isfile(path):
            fail(f"yama hedef dosyası yok: {rel}")
        text = read_text(path)
        count = text.count(old)
        if count != 1:
            fail(f"yama tam 1 kez uygulanmalı ({count} bulundu): {rel}: {old!r}")
        write_text(path, text.replace(old, new))


def scan_annotated(upstream):
    """Return [{rel, path, text, anns: [{id, lang, broken_src}]}] for files with @MangaSourceParser."""
    files = []
    src = os.path.join(upstream, KT_ROOT)
    for dirpath, _, names in os.walk(src):
        for name in sorted(names):
            if not name.endswith(".kt"):
                continue
            path = os.path.join(dirpath, name)
            text = read_text(path)
            anns = []
            prev_end = 0
            for match in ANN_RE.finditer(text):
                segment = text[prev_end:match.start()]
                anns.append({"id": match.group(1), "lang": match.group(3),
                             "broken_src": bool(BROKEN_RE.search(segment))})
                prev_end = match.end()
            if anns:
                rel = os.path.relpath(path, upstream).replace(os.sep, "/")
                files.append({"rel": rel, "path": path, "text": text, "anns": anns})
    return files


def load_sources(path):
    if not os.path.isfile(path):
        fail(f"sources.json yok: {path}")
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    entries = data.get("sources", []) if isinstance(data, dict) else data
    by_parser = {}
    for entry in entries:
        parser = ((entry.get("formats") or {}).get("jar") or {}).get("parser")
        if parser:
            by_parser.setdefault(parser, []).append(entry)
    return by_parser


def jar_broken(entries):
    return any(bool(((e.get("formats") or {}).get("jar") or {}).get("broken")) for e in entries)


def alive_ok(entry):
    if entry.get("scope") != "tr_native":
        return False
    status = entry.get("status")
    if status in PUBLISHED:
        return True
    return status == "failing" and entry.get("failing") is True


def alt_ok(entry, policy):
    if policy == "off" or entry.get("status") not in ALT_STATUSES:
        return False
    alt = entry.get("alternative") or {}
    if not alt.get("domain"):
        return False
    threshold = RANK["high"] if policy == "high" else RANK["medium"]
    return RANK.get(alt.get("confidence"), 0) >= threshold


def patch_domain(file_info, old, new):
    """Replace quoted literals whose host is old (optionally www./scheme/path). Return count."""
    pattern = re.compile(r'"((?:https?://)?(?:www\.)?)' + re.escape(old) + r'((?:[/?#][^"]*)?)"')
    text, count = pattern.subn(lambda m: f'"{m.group(1)}{new}{m.group(2)}"', file_info["text"])
    if count:
        write_text(file_info["path"], text)
        file_info["text"] = text
    return count


def select_and_repair(files, by_parser, mode, include_broken, policy):
    file_of = {}
    lang_of = {}
    broken_of = {}
    for info in files:
        for ann in info["anns"]:
            pid = ann["id"]
            file_of.setdefault(pid, info)
            lang_of[pid] = "tr" if (lang_of.get(pid) == "tr" or ann["lang"] == "tr") else ann["lang"]
            broken_of[pid] = broken_of.get(pid, False) or ann["broken_src"]

    kept = set()
    patched = []
    patch_failed = []
    for pid in sorted(file_of):
        entries = by_parser.get(pid, [])
        if mode == "alive":
            if not any(alive_ok(e) or alt_ok(e, policy) for e in entries):
                continue
        elif lang_of[pid] != "tr":
            continue
        if (broken_of[pid] or jar_broken(entries)) and not include_broken:
            continue
        kept.add(pid)

    for pid in sorted(kept):
        entry = next((e for e in by_parser.get(pid, []) if alt_ok(e, policy)), None)
        if entry is None:
            continue
        old = normalize_host(entry.get("domain"))
        alt = entry["alternative"]
        new = normalize_host(alt.get("domain"))
        count = patch_domain(file_of[pid], old, new) if old and new else 0
        record = {"id": pid, "old": old, "new": new, "confidence": alt.get("confidence")}
        if count:
            patched.append(record)
        else:
            patch_failed.append(record)
            kept.discard(pid)
    return file_of, kept, patched, patch_failed, lang_of


def normalize_host(value):
    if not value:
        return None
    host = value.strip().lower()
    for prefix in ("https://", "http://"):
        if host.startswith(prefix):
            host = host[len(prefix):]
    host = host.rstrip("/")
    if host.startswith("www."):
        host = host[4:]
    return host or None


def delete_and_rescue(files, kept):
    kept_files = [f for f in files if any(a["id"] in kept for a in f["anns"])]
    kept_rels = {f["rel"] for f in kept_files}
    removable = [f for f in files if f["rel"] not in kept_rels]
    by_rel = {f["rel"]: f for f in removable}

    defined = {}
    for info in removable:
        for name in CLASS_DEF_RE.findall(strip_code(info["text"])):
            defined.setdefault(name, set()).add(info["rel"])

    rescued = set()
    queue = list(kept_files)
    while queue:
        info = queue.pop()
        for ident in set(IDENT_RE.findall(strip_code(info["text"]))):
            for rel in defined.get(ident, ()):
                if rel not in rescued:
                    rescued.add(rel)
                    queue.append(by_rel[rel])

    deleted = []
    for info in removable:
        if info["rel"] in rescued:
            continue
        os.remove(info["path"])
        deleted.append(info["rel"])
    return deleted, sorted(rescued)


def strip_code(text):
    return STRIP_RE.sub(" ", text)


def upstream_commit(upstream):
    try:
        out = subprocess.run(["git", "-C", upstream, "rev-parse", "HEAD"],
                             capture_output=True, text=True, timeout=30)
    except (subprocess.SubprocessError, OSError):
        return None
    return out.stdout.strip() if out.returncode == 0 and out.stdout.strip() else None


def main(argv=None):
    parser = argparse.ArgumentParser(description="Prepare Kotatsu-Redo upstream for the JAR build.")
    parser.add_argument("--upstream", required=True)
    parser.add_argument("--sources", default=os.path.join(BASE_DIR, "sources", "tr", "sources.json"))
    parser.add_argument("--mode", choices=["alive", "all_tr"], default="alive")
    parser.add_argument("--include-broken", type=int, choices=[0, 1], default=0)
    parser.add_argument("--apply-alternatives", choices=["off", "high", "high_medium"], default="high")
    parser.add_argument("--report", default=os.path.join(BASE_DIR, "data", "jar_prepare.json"))
    parser.add_argument("--patch-only", action="store_true",
                        help="yalnızca yamaları uygula; seçim, silme ve domain onarımı yapma")
    args = parser.parse_args(argv)

    upstream = os.path.abspath(args.upstream)
    if not os.path.isdir(upstream):
        fail(f"upstream klasörü yok: {upstream}")

    apply_patches(upstream)
    if args.patch_only:
        return 0
    files = scan_annotated(upstream)
    by_parser = load_sources(args.sources)
    file_of, kept, patched, patch_failed, _ = select_and_repair(
        files, by_parser, args.mode, args.include_broken, args.apply_alternatives)
    all_ids = set(file_of)
    deleted, rescued = delete_and_rescue(files, kept)

    report = {
        "upstream_commit": upstream_commit(upstream),
        "mode": args.mode,
        "kept_ids": sorted(kept),
        "removed_ids": sorted(all_ids - kept),
        "rescued_files": rescued,
        "patched_domains": patched,
        "patch_failed": patch_failed,
        "counts": {
            "patches": len(PATCHES),
            "annotated_files": len(files),
            "annotation_ids": len(all_ids),
            "kept": len(kept),
            "removed_ids": len(all_ids - kept),
            "deleted_files": len(deleted),
            "rescued_files": len(rescued),
            "patched_domains": len(patched),
            "patch_failed": len(patch_failed),
        },
    }
    os.makedirs(os.path.dirname(os.path.abspath(args.report)), exist_ok=True)
    write_text(args.report, json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
