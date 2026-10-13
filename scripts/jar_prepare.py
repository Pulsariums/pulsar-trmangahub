#!/usr/bin/env python3
"""Prepare a Kotatsu-Redo checkout for the Kototoro JAR build.

Steps, in order:
  a) patches: the sed replacements of .github/workflows/release.yml, each required exactly once
  b) selection: @MangaSourceParser IDs kept by rules.is_publishable() (default: only status
     'published' = probe ok + functional check passed; --include-unverified also admits
     cf_protected/failing/unverified), mode all_tr additionally limits to tr-locale parsers,
     and the broken rule
  c) deletion: files whose parsers are all dropped are removed, except files whose
     top-level class names are referenced (transitively) by kept files
  d) domain repair: quarantined/failing sources with a qualifying alternative keep their
     file and get the old domain literal replaced by the new one
  e) extras (--extra-parsers DIR): generated/<domain>/jar/*.kt files of custom (ozel) sites
     whose domain has a publishable entry are copied into the upstream tree, after deletion,
     and each copied file is re-read to confirm its @MangaSourceParser registration. Their ids
     must not collide with any upstream id.
  f) report: JSON written to --report

--mode none selects no upstream parser (only extras are built).
--allow-multilang 1 admits non-tr scope sources (global packages).
--nsfw any|only|none keeps all, only nsfw, or only non-nsfw parsers and extras. A parser is nsfw
  when any of its entries is.
--exclude-lang drops parsers and extras whose language code is in the comma separated list.
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rules  # noqa: E402

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

ALT_STATUSES = ("quarantined", "failing")
TRUSTED_STATUSES = ("published", "cf_protected_published")
RANK = {"high": 3, "medium": 2, "low": 1}

ANN_RE = re.compile(r'@MangaSourceParser\(\s*"([^"]+)"\s*,\s*"([^"]*)"(?:\s*,\s*"([A-Za-z_-]*)")?')
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


OVERRIDES_DIR = os.path.join(BASE_DIR, "overrides")


def apply_overrides(upstream):
    """overrides/<upstream içi yol> altındaki dosyalar upstream'deki aynı yolun yerine geçer (onarılmış parserlar)."""
    applied = []
    if not os.path.isdir(OVERRIDES_DIR):
        return applied
    for root, _dirs, names in os.walk(OVERRIDES_DIR):
        for name in sorted(names):
            if not name.endswith(".kt"):
                continue
            src = os.path.join(root, name)
            rel = os.path.relpath(src, OVERRIDES_DIR)
            dest = os.path.join(upstream, rel)
            if not os.path.isfile(dest):
                fail(f"override hedefi upstream'de yok (dosya taşınmış/silinmiş): {rel}")
            write_text(dest, read_text(src))
            applied.append(rel.replace(os.sep, "/"))
    return applied


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
                anns.append({"id": match.group(1), "lang": match.group(3) or "",
                             "broken_src": bool(BROKEN_RE.search(segment))})
                prev_end = match.end()
            if anns:
                rel = os.path.relpath(path, upstream).replace(os.sep, "/")
                files.append({"rel": rel, "path": path, "text": text, "anns": anns})
    return files


def load_entries(path):
    if not os.path.isfile(path):
        fail(f"sources.json yok: {path}")
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    return data.get("sources", []) if isinstance(data, dict) else data


def load_sources(path):
    entries = load_entries(path)
    by_parser = {}
    for entry in entries:
        parser = ((entry.get("formats") or {}).get("jar") or {}).get("parser")
        if parser:
            by_parser.setdefault(parser, []).append(entry)
    return by_parser


def jar_broken(entries):
    return any(bool(((e.get("formats") or {}).get("jar") or {}).get("broken")) for e in entries)


def trusted_domains(entries):
    """Hosts of entries verified live ('published' / 'cf_protected_published')."""
    return {normalize_host(e.get("domain")) for e in entries
            if e.get("status") in TRUSTED_STATUSES and normalize_host(e.get("domain"))}


def alt_ok(entry, policy, trusted=frozenset()):
    if policy == "off" or entry.get("status") not in ALT_STATUSES:
        return False
    alt = entry.get("alternative") or {}
    if not alt.get("domain"):
        return False
    confidence = alt.get("confidence")
    if normalize_host(alt.get("domain")) in trusted:
        confidence = "high"
    threshold = RANK["high"] if policy == "high" else RANK["medium"]
    return RANK.get(confidence, 0) >= threshold


def patch_domain(file_info, old, new):
    """Replace quoted literals whose host is old (optionally www./scheme/path). Return count."""
    pattern = re.compile(r'"((?:https?://)?(?:www\.)?)' + re.escape(old) + r'((?:[/?#][^"]*)?)"')
    text, count = pattern.subn(lambda m: f'"{m.group(1)}{new}{m.group(2)}"', file_info["text"])
    if count:
        write_text(file_info["path"], text)
        file_info["text"] = text
    return count


def parse_list(value):
    return sorted({item.strip().lower() for item in (value or "").split(",") if item.strip()})


def keep_candidate(nsfw, lang, nsfw_mode, exclude_lang):
    if nsfw_mode == "only" and not nsfw:
        return False
    if nsfw_mode == "none" and nsfw:
        return False
    return (lang or "").lower() not in exclude_lang


def select_and_repair(files, by_parser, mode, include_broken, policy, include_unverified=False,
                      allow_multilang=False, nsfw_mode="any", exclude_lang=(), trusted=frozenset()):
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
    if mode == "none":
        return file_of, kept, patched, patch_failed, lang_of
    for pid in sorted(file_of):
        entries = by_parser.get(pid, [])
        if not any(rules.is_publishable(e, include_unverified, allow_multilang) for e in entries):
            continue
        if mode == "all_tr" and lang_of[pid] != "tr":
            continue
        if (broken_of[pid] or jar_broken(entries)) and not include_broken:
            continue
        nsfw = any(bool(e.get("nsfw")) for e in entries)
        if not keep_candidate(nsfw, lang_of[pid], nsfw_mode, exclude_lang):
            continue
        kept.add(pid)

    for pid in sorted(kept):
        entry = next((e for e in by_parser.get(pid, []) if alt_ok(e, policy, trusted)), None)
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


def scan_extras(extra_dir, entries, include_unverified):
    """Return [{id, name, lang, nsfw, domain, path, rel}] for generated/<domain>/jar/*.kt files.
    A domain contributes only when one of its entries is publishable."""
    by_domain = {}
    for entry in entries:
        if entry.get("domain"):
            by_domain.setdefault(entry["domain"].lower(), []).append(entry)
    found = []
    if not os.path.isdir(extra_dir):
        return found
    for domain in sorted(os.listdir(extra_dir)):
        jar_dir = os.path.join(extra_dir, domain, "jar")
        if not os.path.isdir(jar_dir):
            continue
        group = by_domain.get(domain.lower(), [])
        if not any(rules.is_publishable(e, include_unverified) for e in group):
            continue
        for name in sorted(os.listdir(jar_dir)):
            if not name.endswith(".kt"):
                continue
            path = os.path.join(jar_dir, name)
            text = read_text(path)
            for match in ANN_RE.finditer(text):
                end = text.find(")", match.start())
                found.append({"id": match.group(1), "name": match.group(2) or match.group(1),
                              "lang": match.group(3) or "", "domain": domain, "path": path,
                              "rel": f"{domain}/jar/{name}",
                              "nsfw": "HENTAI" in text[match.start():end if end > 0 else None]})
    return found


def copy_extras(upstream, extras, taken_ids):
    """Copy extra parser files into the upstream tree and confirm each registration."""
    seen = {}
    kept = []
    for item in extras:
        if item["id"] in taken_ids or item["id"] in seen:
            # Bir ozel parser'in cakismasi tum paketi dusurmesin: atla ve uyar.
            print(f"UYARI: ozel parser id cakisiyor, atlandi: {item['id']} ({item['rel']})", file=sys.stderr)
            continue
        seen[item["id"]] = item["rel"]
        kept.append(item)
    extras = kept
    dest_root = os.path.join(upstream, PARSERS_DIR, "site", "ozel")
    copied = []
    for item in extras:
        sub = re.sub(r"[^A-Za-z0-9_]", "_", item["domain"])
        dest_dir = os.path.join(dest_root, sub)
        os.makedirs(dest_dir, exist_ok=True)
        dest = os.path.join(dest_dir, os.path.basename(item["path"]))
        shutil.copyfile(item["path"], dest)
        registered = {m.group(1) for m in ANN_RE.finditer(read_text(dest))}
        if item["id"] not in registered:
            fail(f"ozel parser kayıtlı değil: {item['id']} ({item['rel']})")
        copied.append({"id": item["id"], "name": item["name"], "lang": item["lang"],
                       "nsfw": item["nsfw"], "domain": item["domain"],
                       "file": os.path.relpath(dest, upstream).replace(os.sep, "/")})
    return copied


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


GROUPLE_BRANCH_RE = re.compile(r"^[ \t]*in\s+\w+\.domains\s*->\s*MangaParserSource\.(\w+)[ \t]*\r?\n", re.M)


def prune_dangling_refs(upstream, removed_ids):
    """Silinen parser sınıflarına/enum sabitlerine bağlı kalan `when` dallarını (GroupleParser) temizle."""
    pruned = []
    for root, _dirs, names in os.walk(os.path.join(upstream, "src")):
        for name in names:
            if not name.endswith(".kt"):
                continue
            path = os.path.join(root, name)
            text = read_text(path)
            if "MangaParserSource." not in text:
                continue
            new = GROUPLE_BRANCH_RE.sub(lambda m: "" if m.group(1) in removed_ids else m.group(0), text)
            if new != text:
                write_text(path, new)
                pruned.append(os.path.relpath(path, upstream))
    return pruned


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
    parser.add_argument("--mode", choices=["alive", "all_tr", "none"], default="alive")
    parser.add_argument("--include-broken", type=int, choices=[0, 1], default=0)
    parser.add_argument("--apply-alternatives", choices=["off", "high", "high_medium"], default="high")
    parser.add_argument("--include-unverified", type=int, choices=[0, 1], default=0,
                        help="cf_protected, failing ve unverified kaynakları da dahil et (varsayılan 0)")
    parser.add_argument("--allow-multilang", type=int, choices=[0, 1], default=0,
                        help="non-tr scope kaynakları da dahil et (global bucket, varsayılan 0)")
    parser.add_argument("--extra-parsers", default="",
                        help="generated/ kökü: ozel <domain>/jar/*.kt parser dosyalarını ekle")
    parser.add_argument("--nsfw", choices=["any", "only", "none"], default="any",
                        help="any: hepsi; only: yalnız nsfw; none: yalnız nsfw olmayan (varsayılan any)")
    parser.add_argument("--exclude-lang", default="",
                        help="virgülle ayrılmış dil kodları; bu dillerdeki parser ve extras atlanır")
    parser.add_argument("--report", default=os.path.join(BASE_DIR, "data", "jar_prepare.json"))
    parser.add_argument("--patch-only", action="store_true",
                        help="yalnızca yamaları uygula; seçim, silme ve domain onarımı yapma")
    args = parser.parse_args(argv)

    upstream = os.path.abspath(args.upstream)
    if not os.path.isdir(upstream):
        fail(f"upstream klasörü yok: {upstream}")

    apply_patches(upstream)
    overrides = apply_overrides(upstream)
    exclude = parse_list(args.exclude_lang)
    if args.patch_only:
        # Fallback build: no selection or deletion, but ozel extras are still copied in.
        if args.extra_parsers:
            taken = {ann["id"] for info in scan_annotated(upstream) for ann in info["anns"]}
            found = scan_extras(os.path.abspath(args.extra_parsers), load_entries(args.sources),
                                bool(args.include_unverified))
            found = [x for x in found if keep_candidate(x["nsfw"], x["lang"], args.nsfw, exclude)]
            copy_extras(upstream, found, taken)
        return 0
    files = scan_annotated(upstream)
    entries = load_entries(args.sources)
    by_parser = load_sources(args.sources)
    include_unverified = bool(args.include_unverified)
    allow_multilang = bool(args.allow_multilang)
    file_of, kept, patched, patch_failed, lang_of = select_and_repair(
        files, by_parser, args.mode, args.include_broken, args.apply_alternatives, include_unverified,
        allow_multilang, args.nsfw, exclude, trusted_domains(entries))
    all_ids = set(file_of)
    deleted, rescued = delete_and_rescue(files, kept)
    pruned_refs = prune_dangling_refs(upstream, all_ids - kept)

    extras = []
    if args.extra_parsers:
        found = scan_extras(os.path.abspath(args.extra_parsers), entries, include_unverified)
        found = [x for x in found if keep_candidate(x["nsfw"], x["lang"], args.nsfw, exclude)]
        if rules.LIVE_GATE and not rules.ADMIT_ALL:
            # Ozel/uretilmis parser canli testi gecmeden kullaniciya gitmez.
            live = rules._live()
            passed = []
            for x in found:
                rec = live.get(x["id"]) or {}
                if rec.get("ok_streak", 0) >= 1:
                    passed.append(x)
                else:
                    print(f"UYARI: canli testi gecmeyen ozel parser yayina alinmadi: {x['id']}", file=sys.stderr)
            found = passed
        extras = copy_extras(upstream, found, all_ids)
        kept |= {x["id"] for x in extras}
        for x in extras:
            lang_of[x["id"]] = x["lang"]

    report = {
        "upstream_commit": upstream_commit(upstream),
        "mode": args.mode,
        "include_unverified": include_unverified,
        "allow_multilang": allow_multilang,
        "nsfw": args.nsfw,
        "exclude_lang": exclude,
        "kept_ids": sorted(kept),
        "langs": {pid: lang_of.get(pid, "tr") for pid in sorted(kept)},
        "extra_sources": extras,
        "removed_ids": sorted(all_ids - kept),
        "rescued_files": rescued,
        "pruned_refs": pruned_refs,
        "overrides": overrides,
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
            "extra_parsers": len(extras),
        },
    }
    os.makedirs(os.path.dirname(os.path.abspath(args.report)), exist_ok=True)
    write_text(args.report, json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
