#!/usr/bin/env python3
"""Collect Turkish manga sources from Mihon (keiyoushi), Kotatsu (kotatsu-parsers-redo) and
Nyora (nyora-data-driven) and merge them into data/upstream_tr.json.

An upstream that cannot be reached is reported in meta.errors and skipped; the
other upstreams are still merged.
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import unicodedata
from datetime import datetime, timezone
from urllib.parse import urlparse

import requests

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
CACHE_DIR = os.path.join(DATA_DIR, "cache")
OUT_PATH = os.path.join(DATA_DIR, "upstream_tr.json")
CUSTOM_PATH = os.path.join(BASE_DIR, "sources", "custom", "sources.json")

MIHON_INDEX_URL = "https://raw.githubusercontent.com/keiyoushi/extensions/repo/index.json"
NYORA_CATALOG_URL = "https://raw.githubusercontent.com/Nyora-Manga/nyora-data-driven/main/catalogue.json"
NYORA_LIVENESS_URL = "https://raw.githubusercontent.com/Nyora-Manga/nyora-data-driven/main/liveness.json"
KOTATSU_REPO_URL = "https://github.com/Kotatsu-Redo/kotatsu-parsers-redo.git"
MIHON_TR_PREFIX = "eu.kanade.tachiyomi.extension.tr."

HTTP_TIMEOUT = 60
HTTP_ATTEMPTS = 2
GIT_TIMEOUT = 600

TLDS = ("com", "net", "org", "id", "tr", "me", "cc", "top", "us", "io", "xyz", "info", "moe",
        "site", "co", "tv", "to", "live", "world", "fun", "app", "pro", "gg", "online", "link",
        "cx", "com.tr", "net.tr", "org.tr")
TLD_RE = re.compile(r"\.(?:" + "|".join(sorted(TLDS, key=len, reverse=True)) + r")$", re.IGNORECASE)
TR_CHARS = str.maketrans({"ı": "i", "İ": "i", "ğ": "g", "Ğ": "g", "ş": "s", "Ş": "s",
                          "ç": "c", "Ç": "c", "ö": "o", "Ö": "o", "ü": "u", "Ü": "u"})

# @MangaSourceParser("ID", "Title", "lang"[, ContentType.X])
ANN_RE = re.compile(r'@MangaSourceParser\(\s*"([^"]+)"\s*,\s*"([^"]*)"\s*,\s*"([A-Za-z_-]+)"([^)]*)\)')
DOMAIN_CFG_RE = re.compile(r'ConfigKey\.Domain\(\s*"([^"]+)"')
DOMAIN_LIT_RE = re.compile(r'"((?:[a-z0-9-]+\.)+[a-z]{2,})(?:/[^"]*)?"', re.IGNORECASE)
BROKEN_RE = re.compile(r"@Broken\b")
BROKEN_REASON_RE = re.compile(r'@Broken\(\s*"([^"]*)"')


def normalize_domain(value):
    """Return the lowercase host without a leading www., or None."""
    if not value or not isinstance(value, str):
        return None
    text = value.strip()
    if "://" not in text:
        text = "https://" + text
    try:
        host = urlparse(text).hostname
    except ValueError:
        return None
    if not host:
        return None
    host = host.lower().rstrip(".")
    if host.startswith("www."):
        host = host[4:]
    return host or None


def make_key(name, domain=None):
    """Lowercase, ASCII-folded name without spaces, dashes, dots or TLD."""
    text = (name or "").strip()
    if " " not in text:
        text = TLD_RE.sub("", text)
    text = unicodedata.normalize("NFKD", text.translate(TR_CHARS).lower())
    text = "".join(ch for ch in text if ch.isascii() and ch.isalnum())
    if not text and domain:
        text = domain.split(".")[0]
    return text


def make_record(upstream, name, domain, base_url, engine, nsfw, formats, alt_domains=(), scope="tr_native"):
    return {
        "upstream": upstream,
        "name": (name or "").strip(),
        "domain": domain,
        "baseUrl": base_url,
        "engine": engine,
        "nsfw": bool(nsfw),
        "formats": formats,
        "altDomains": [d for d in alt_domains if d],
        "scope": scope,
    }


def fetch_json(url, upstream, errors):
    last_exc = None
    for _ in range(HTTP_ATTEMPTS):
        try:
            resp = requests.get(url, timeout=HTTP_TIMEOUT)
            resp.raise_for_status()
            return resp.json()
        except (requests.RequestException, ValueError) as exc:
            last_exc = exc
    errors.append({"upstream": upstream, "url": url,
                   "error": f"{type(last_exc).__name__}: {last_exc}"})
    return None


# ---------------------------------------------------------------- Mihon

def parse_mihon(index):
    """Return (records, total_entries). A TR record is an extension with a tr source or a tr. package."""
    extensions = ((index or {}).get("extensionList") or {}).get("extensions") or []
    records = []
    for ext in extensions:
        pkg = ext.get("packageName") or ""
        sources = ext.get("sources") or []
        tr_sources = [s for s in sources if s.get("language") == "tr"]
        if not tr_sources and not pkg.startswith(MIHON_TR_PREFIX):
            continue
        resources = ext.get("resources") or {}
        mihon = {"pkg": pkg, "version": ext.get("versionName"), "apkUrl": resources.get("apkUrl")}
        nsfw = "NSFW" in (ext.get("contentWarning") or "").upper()
        scope = "tr_native" if pkg.startswith(MIHON_TR_PREFIX) else "multilang"
        candidates = tr_sources or sources[:1]
        if not candidates:
            records.append(make_record("mihon", ext.get("name"), None, None, None, nsfw,
                                       {"mihon": mihon}, scope=scope))
            continue
        for src in candidates:
            home = (src.get("homeUrl") or "").strip() or None
            domain = normalize_domain(home)
            records.append(make_record("mihon", src.get("name") or ext.get("name"), domain, home,
                                       None, nsfw, {"mihon": dict(mihon)}, scope=scope))
    return records, len(extensions)


# ---------------------------------------------------------------- Kotatsu

def ensure_kotatsu_repo(refresh):
    path = os.path.join(CACHE_DIR, "kotatsu-parsers-redo")
    if refresh and os.path.isdir(path):
        shutil.rmtree(path)
    if not os.path.isdir(os.path.join(path, ".git")):
        if os.path.isdir(path):
            shutil.rmtree(path)
        os.makedirs(CACHE_DIR, exist_ok=True)
        subprocess.run(["git", "clone", "--depth", "1", KOTATSU_REPO_URL, path],
                       check=True, timeout=GIT_TIMEOUT, capture_output=True, text=True)
    return path


def git_head(repo):
    try:
        out = subprocess.run(["git", "-C", repo, "rev-parse", "--short", "HEAD"],
                             check=True, capture_output=True, text=True, timeout=30)
        return out.stdout.strip()
    except (subprocess.SubprocessError, OSError):
        return None


def parse_kotatsu(repo):
    """Return (records, files_scanned) for every @MangaSourceParser with lang "tr"."""
    records = []
    scanned = 0
    for dirpath, _, filenames in os.walk(os.path.join(repo, "src")):
        for fname in filenames:
            if not fname.endswith(".kt"):
                continue
            path = os.path.join(dirpath, fname)
            scanned += 1
            with open(path, encoding="utf-8", errors="replace") as fh:
                text = fh.read()
            if "MangaSourceParser" not in text:
                continue
            rel = os.path.relpath(path, repo).replace(os.sep, "/")
            parts = rel.split("/")
            engine = None
            if "site" in parts:
                idx = parts.index("site")
                if idx + 1 < len(parts) - 1:
                    engine = parts[idx + 1]
                    if engine == "tr":
                        engine = "custom"
            for match in ANN_RE.finditer(text):
                parser_id, title, lang, rest = match.group(1), match.group(2), match.group(3), match.group(4)
                if lang != "tr":
                    continue
                prev_ann = text.rfind("@MangaSourceParser", 0, match.start())
                between = text[max(prev_ann, 0):match.start()]
                broken = bool(BROKEN_RE.search(between))
                reason_m = BROKEN_REASON_RE.search(between)
                domain = None
                cfg = DOMAIN_CFG_RE.search(text, match.end())
                if cfg:
                    domain = normalize_domain(cfg.group(1))
                else:
                    header = text[match.end():match.end() + 400].split("{", 1)[0]
                    lit = DOMAIN_LIT_RE.search(header)
                    if lit:
                        domain = normalize_domain(lit.group(1))
                record = make_record("kotatsu", title, domain, None, engine, "HENTAI" in rest,
                                     {"jar": {"parser": parser_id, "file": rel, "broken": broken,
                                              "brokenReason": reason_m.group(1) if reason_m else None}},
                                     scope="tr_native")
                records.append(record)
    return records, scanned


# ---------------------------------------------------------------- Nyora

def parse_nyora(catalog, liveness):
    rows = catalog.get("sources", []) if isinstance(catalog, dict) else (catalog or [])
    live = liveness or {}
    dead_domains = {normalize_domain(d) for d in (live.get("deadDomains") or [])}
    dead_ids = set(live.get("deadIds") or [])
    records = []
    for row in rows:
        if row.get("lang") != "tr":
            continue
        domain = normalize_domain(row.get("domain"))
        alt = [normalize_domain(d) for d in (row.get("altDomains") or [])]
        catalog_entry = {
            "id": row.get("id"),
            "broken": bool(row.get("broken")),
            "brokenReason": row.get("brokenReason"),
            "cfWall": row.get("cfWall"),
            "antiBot": row.get("antiBot"),
            "engine": row.get("engine"),
            "deadInLiveness": bool((domain and domain in dead_domains) or row.get("id") in dead_ids),
        }
        records.append(make_record("nyora", row.get("name") or row.get("id"), domain,
                                   f"https://{domain}" if domain else None, row.get("engine"),
                                   row.get("nsfw"), {"catalog": catalog_entry}, alt, scope="tr_native"))
    return records


# ---------------------------------------------------------------- custom

def parse_custom(path):
    """Records from sources/custom/sources.json (written by analyze_site.py). They carry no
    Mihon or jar format, so build.py never publishes them as extensions; probe and health still see them."""
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    entries = data if isinstance(data, list) else (data.get("sources") or [])
    records = []
    for entry in entries:
        domain = normalize_domain(entry.get("domain") or entry.get("id"))
        if not domain:
            continue
        records.append(make_record("custom", entry.get("name"), domain, entry.get("baseUrl"),
                                   entry.get("engine"), False,
                                   {"mihon": None, "jar": None, "catalog": None},
                                   scope=entry.get("scope") or "tr_native"))
    return records


# ---------------------------------------------------------------- merge

def merge_records(records):
    """Merge records by domain (and by name for records without a domain)."""
    targets = []
    by_domain = {}
    by_key_nodomain = {}
    collisions = []
    for rec in records:
        key = make_key(rec["name"], rec["domain"])
        candidate_domains = [d for d in [rec["domain"]] + rec["altDomains"] if d]
        target = None
        for dom in candidate_domains:
            if dom in by_domain:
                target = by_domain[dom]
                break
        if target is None and not rec["domain"]:
            target = by_key_nodomain.get(key)
        if target is None and rec["domain"] and key in by_key_nodomain:
            target = by_key_nodomain.pop(key)
        if target is None:
            target = {"key": key, "name": rec["name"], "domain": None, "baseUrl": None,
                      "engine": None, "formats": {"mihon": None, "jar": None, "catalog": None},
                      "nsfw": False, "scope": "multilang", "upstreams": [], "_alt": []}
            targets.append(target)

        if rec["domain"]:
            if target["domain"] is None:
                target["domain"] = rec["domain"]
            for dom in candidate_domains:
                by_domain.setdefault(dom, target)
                if dom != target["domain"] and dom not in target["_alt"]:
                    target["_alt"].append(dom)
            by_key_nodomain.pop(key, None)
        elif target["domain"] is None:
            by_key_nodomain.setdefault(key, target)

        if rec["baseUrl"] and not target["baseUrl"]:
            target["baseUrl"] = rec["baseUrl"]
        if rec["engine"] and (target["engine"] is None or rec["upstream"] == "nyora"):
            target["engine"] = rec["engine"]
        target["nsfw"] = target["nsfw"] or rec["nsfw"]
        if rec.get("scope") == "tr_native":
            target["scope"] = "tr_native"
        if rec["upstream"] not in target["upstreams"]:
            target["upstreams"].append(rec["upstream"])
        for fmt, value in rec["formats"].items():
            if value is None:
                continue
            if target["formats"][fmt] is None:
                target["formats"][fmt] = value
            else:
                collisions.append({"key": target["key"], "format": fmt,
                                   "kept": target["formats"][fmt], "dropped": value})

    for target in targets:
        if target["domain"] and not target["baseUrl"]:
            target["baseUrl"] = f"https://{target['domain']}"
    return targets, collisions


def finalize(targets):
    final = []
    for t in targets:
        final.append({
            "key": t["key"],
            "name": t["name"],
            "domain": t["domain"],
            "baseUrl": t["baseUrl"],
            "engine": t["engine"],
            "formats": t["formats"],
            "nsfw": t["nsfw"],
            "scope": t["scope"],
            "upstreams": t["upstreams"],
            "altDomains": t["_alt"],
        })
    final.sort(key=lambda s: (s["domain"] is None, s["domain"] or "", s["key"]))
    return final


def write_json(path, payload):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    os.replace(tmp, path)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Sync Turkish manga sources from upstream repos.")
    parser.add_argument("--out", default=OUT_PATH)
    parser.add_argument("--refresh-kotatsu", action="store_true",
                        help="delete the cached kotatsu-parsers-redo clone and clone again")
    args = parser.parse_args(argv)

    errors = []
    upstreams = {}
    all_records = []

    # Mihon
    mihon_index = fetch_json(MIHON_INDEX_URL, "mihon", errors)
    if mihon_index is None:
        upstreams["mihon"] = {"status": "unavailable", "tr_records": 0, "total_entries": 0}
    else:
        mihon_recs, total = parse_mihon(mihon_index)
        upstreams["mihon"] = {"status": "ok", "tr_records": len(mihon_recs), "total_entries": total}
        all_records.extend(mihon_recs)

    # Kotatsu
    try:
        repo = ensure_kotatsu_repo(args.refresh_kotatsu)
        kotatsu_recs, scanned = parse_kotatsu(repo)
        upstreams["kotatsu"] = {"status": "ok", "tr_records": len(kotatsu_recs),
                                "files_scanned": scanned, "commit": git_head(repo)}
        all_records.extend(kotatsu_recs)
    except (subprocess.SubprocessError, OSError) as exc:
        errors.append({"upstream": "kotatsu", "error": f"{type(exc).__name__}: {exc}"})
        upstreams["kotatsu"] = {"status": "unavailable", "tr_records": 0}

    # Nyora
    catalog = fetch_json(NYORA_CATALOG_URL, "nyora", errors)
    liveness = fetch_json(NYORA_LIVENESS_URL, "nyora-liveness", errors)
    if catalog is None:
        upstreams["nyora"] = {"status": "unavailable", "tr_records": 0}
    else:
        nyora_recs = parse_nyora(catalog, liveness)
        upstreams["nyora"] = {"status": "ok", "tr_records": len(nyora_recs),
                              "liveness": "ok" if liveness is not None else "unavailable"}
        all_records.extend(nyora_recs)

    custom_recs = parse_custom(CUSTOM_PATH)
    upstreams["custom"] = {"status": "ok" if os.path.exists(CUSTOM_PATH) else "absent",
                           "tr_records": len(custom_recs)}
    all_records.extend(custom_recs)

    targets, collisions = merge_records(all_records)
    final = finalize(targets)

    membership = {name: sum(1 for s in final if name in s["upstreams"])
                  for name in ("mihon", "kotatsu", "nyora")}
    meta = {
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "python": sys.version.split()[0],
        "upstreams": upstreams,
        "raw_records": len(all_records),
        "unique_sources": len(final),
        "unique_with_domain": sum(1 for s in final if s["domain"]),
        "membership": membership,
        "in_multiple_upstreams": sum(1 for s in final if len(s["upstreams"]) > 1),
        "format_collisions": collisions,
        "errors": errors,
    }
    write_json(args.out, {"meta": meta, "sources": final})

    print(f"Output: {args.out}")
    for name in ("mihon", "kotatsu", "nyora"):
        info = upstreams[name]
        print(f"  {name:8s} status={info['status']:11s} tr_records={info['tr_records']}")
    print(f"  raw records: {len(all_records)}  unique sources: {len(final)}  "
          f"with domain: {meta['unique_with_domain']}")
    print(f"  membership: {membership}  in >1 upstream: {meta['in_multiple_upstreams']}")
    print(f"  format collisions dropped: {len(collisions)}")
    for err in errors:
        print(f"  ERROR {err}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
