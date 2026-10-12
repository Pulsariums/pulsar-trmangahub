#!/usr/bin/env python3
"""Yayınlanan Mihon (keiyoushi) TR eklentilerini repo-mihon/ altına aynalar.

Akış:
  1. sources/tr/sources.json okunur; formats.mihon.pkg değeri olan ve rules.is_publishable()
     geçen (varsayılan: yalnızca status 'published') kaynaklar pakete göre gruplanır. Bir paketin
     en az bir kaynağı dahil edilebilirse paket alınır; yalnızca dahil edilebilir kaynakların
     domainleri 'hosts' olarak taşınır. --include-unverified cf_protected/failing/unverified
     kaynakları da ekler.
  2. keiyoushi/extensions 'repo' dalındaki index.json alınır; packageName -> eklenti haritası kurulur.
     (Eski index.min.json kullanılmaz.)
  3. Her paket için index.json'daki kaynaklardan yalnızca 'hosts' içindekiler (homeUrl domaini
     eşleşenler) index'e yazılır. Eşleşen kaynağı olmayan paket dışarıda kalır.
  4. Her yayınlanan pkg için APK indirilir. Önce index.json içindeki resources.apkUrl denenir,
     olmazsa sources.json içindeki apkUrl. Dosya repo-mihon/apk/<url'nin dosya adı> olarak yazılır.
     Aynı sürüm ve dosya zaten varsa indirilmez.
  5. repo-mihon/index.min.json bu eklentilerden yazılır; repo-mihon/README.md güncellenir.
     Artık listede olmayan APK'lar silinir.

Yalnızca standart kütüphane kullanılır. İndirilemeyen, index.json'da bulunmayan veya
geçersiz girdiler atlanır ve raporda listelenir. index.json alınamazsa hiçbir dosya
değiştirilmez ve çıkış kodu 1 olur.
"""

import argparse
import json
import os
import re
import sys
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rules  # noqa: E402

UPSTREAM_BASE = "https://raw.githubusercontent.com/keiyoushi/extensions/repo"
INDEX_URL = f"{UPSTREAM_BASE}/index.json"
USER_AGENT = "pulsar-trmangahub-mihon-mirror/1.0"
TIMEOUT_SECONDS = 60
MAX_ATTEMPTS = 3
APK_MAGIC = b"PK\x03\x04"
APK_NAME_RE = re.compile(r"^[A-Za-z0-9._-]+\.apk$")
LANG = "tr"

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR_NAME = "repo-mihon"
REPO_SLUG_FALLBACK = "<GITHUB_REPOSITORY>"


def fetch(url, timeout=TIMEOUT_SECONDS):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def fetch_with_retry(url, fetcher=None, attempts=MAX_ATTEMPTS):
    fetcher = fetcher or fetch
    last_error = None
    for _ in range(attempts):
        try:
            return fetcher(url)
        except (OSError, ValueError) as exc:
            last_error = exc
    raise last_error


def load_json(path, default=None):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return default


def write_atomic(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    if isinstance(data, bytes):
        with open(tmp, "wb") as fh:
            fh.write(data)
    else:
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.write(data)
    os.replace(tmp, path)


def host_of(value):
    """Domain veya URL'den küçük harfli host (www. olmadan). Geçersizse None."""
    if not value or not isinstance(value, str):
        return None
    raw = value.strip().lower()
    if "://" not in raw:
        raw = "https://" + raw
    host = urllib.parse.urlsplit(raw).hostname or ""
    if host.startswith("www."):
        host = host[4:]
    return host or None


def mihon_packages(sources_doc, include_unverified=False):
    """Dahil edilebilir Mihon paketleri, pkg başına tek kayıt:
    {pkg, apkUrl, version, hosts}. hosts yalnızca dahil edilebilir kaynakların domainleridir."""
    packages = {}
    for entry in (sources_doc or {}).get("sources") or []:
        if not isinstance(entry, dict):
            continue
        mihon = (entry.get("formats") or {}).get("mihon") or {}
        pkg = mihon.get("pkg")
        if not pkg or not rules.is_publishable(entry, include_unverified):
            continue
        item = packages.setdefault(pkg, {"pkg": pkg, "apkUrl": mihon.get("apkUrl"),
                                         "version": mihon.get("version"), "hosts": set()})
        host = host_of(entry.get("domain"))
        if host:
            item["hosts"].add(host)
    return [packages[pkg] for pkg in sorted(packages)]


def upstream_map(index_doc):
    """index.json içinden packageName -> eklenti sözlüğü."""
    exts = ((index_doc or {}).get("extensionList") or {}).get("extensions") or []
    return {e["packageName"]: e for e in exts if isinstance(e, dict) and e.get("packageName")}


def apk_name_from_url(url):
    name = os.path.basename(urllib.parse.unquote(urllib.parse.urlsplit(url).path))
    return name if APK_NAME_RE.match(name) else None


def listed_sources(ext, hosts):
    """index.json eklentisinin yalnızca hosts içindeki (doğrulanmış) kaynakları."""
    out = []
    for src in ext.get("sources") or []:
        if not isinstance(src, dict):
            continue
        if host_of(src.get("homeUrl")) not in hosts:
            continue
        out.append({
            "name": src.get("name") or "",
            "lang": LANG,
            "id": str(src.get("id") or ""),
            "baseUrl": src.get("homeUrl") or "",
        })
    return out


def build_entry(ext, pkg, apk, code, version, sources):
    warning = str(ext.get("contentWarning") or "")
    return {
        "name": ext.get("name") or pkg,
        "pkg": pkg,
        "apk": apk,
        "lang": LANG,
        "code": code,
        "version": version,
        "nsfw": 1 if "NSFW" in warning else 0,
        "sources": sources,
    }


def sync(items, upstream, prev_by_pkg, apk_dir, fetcher=None):
    """Her paket için girdi üretir. Döner: (girdiler, istatistik, atlananlar)."""
    os.makedirs(apk_dir, exist_ok=True)
    result, skipped = [], []
    stats = {"indirildi": 0, "yeniden_kullanildi": 0, "atlandi": 0}
    for item in items:
        pkg = item["pkg"]
        ext = upstream.get(pkg)
        if ext is None:
            skipped.append((pkg, "index.json içinde yok"))
            stats["atlandi"] += 1
            continue
        sources = listed_sources(ext, item.get("hosts") or set())
        if not sources:
            skipped.append((pkg, "doğrulanmış kaynakla eşleşen kaynak yok"))
            stats["atlandi"] += 1
            continue
        try:
            code = int(ext["versionCode"])
        except (KeyError, TypeError, ValueError):
            skipped.append((pkg, "geçersiz versionCode"))
            stats["atlandi"] += 1
            continue
        version = ext.get("versionName") or item.get("version") or ""
        candidates = []
        for url in ((ext.get("resources") or {}).get("apkUrl"), item.get("apkUrl")):
            if url and url not in candidates:
                candidates.append(url)

        prev = prev_by_pkg.get(pkg)
        apk, errors = None, []
        for url in candidates:
            name = apk_name_from_url(url)
            if not name:
                errors.append(f"geçersiz dosya adı: {url}")
                continue
            path = os.path.join(apk_dir, name)
            if prev and prev.get("code") == code and prev.get("apk") == name and os.path.isfile(path):
                apk = name
                stats["yeniden_kullanildi"] += 1
                break
            try:
                data = fetch_with_retry(url, fetcher=fetcher)
                if not data.startswith(APK_MAGIC):
                    raise ValueError("APK (zip) imzası yok")
                write_atomic(path, data)
                apk = name
                stats["indirildi"] += 1
                break
            except (OSError, ValueError) as exc:
                errors.append(f"{url}: {exc}")
        if apk is None:
            skipped.append((pkg, "; ".join(errors) or "APK adresi yok"))
            stats["atlandi"] += 1
            continue
        result.append(build_entry(ext, pkg, apk, code, version, sources))
    return result, stats, skipped


def remove_stale(apk_dir, keep_names):
    removed = []
    if not os.path.isdir(apk_dir):
        return removed
    for name in sorted(os.listdir(apk_dir)):
        full = os.path.join(apk_dir, name)
        if name not in keep_names and os.path.isfile(full):
            os.remove(full)
            removed.append(name)
    return removed


def index_text(entries):
    return json.dumps(entries, ensure_ascii=False, separators=(",", ":")) + "\n"


def readme_text(slug):
    return f"""# Pulsar TR Manga Hub: Mihon deposu (Türkçe APK aynası)

Bu klasör, Türkçe Mihon eklentilerinin APK aynasıdır. Kaynak olarak keiyoushi/extensions
deposu kullanılır; yalnızca bu deponun yayınlanan Türkçe kaynakları alınır.
`.github/workflows/build-mihon.yml` iş akışı günceller.

## Mihon'a ekleme

1. Mihon'u açın ve **Ayarlar → Eklentiler → Depolar → Depo ekle** yolunu izleyin.
2. Adres olarak şunu girin:

   `https://raw.githubusercontent.com/{slug}/main/repo-mihon/`

## Dosyalar

- `index.min.json`: eklenti dizini (Türkçe girdiler)
- `apk/`: eklenti APK dosyaları
"""


def summary_text(stats, skipped, removed, published_count, kept_count):
    lines = [
        "## Mihon deposu: Türkçe APK aynası",
        "",
        f"- Dahil edilebilir Mihon paketi (sources.json): {published_count}",
        f"- Dizinde kalan eklenti: {kept_count}",
        f"- İndirilen APK: {stats['indirildi']}",
        f"- Yeniden kullanılan APK: {stats['yeniden_kullanildi']}",
        f"- Atlanan: {stats['atlandi']}",
        f"- Silinen eski APK: {len(removed)}",
    ]
    if skipped:
        lines.append("")
        lines.append("Atlanan paketler:")
        for pkg, reason in skipped:
            lines.append(f"- {pkg}: {reason}")
    return "\n".join(lines) + "\n"


def repo_slug():
    return os.environ.get("GITHUB_REPOSITORY") or REPO_SLUG_FALLBACK


def main(argv=None, fetcher=None):
    parser = argparse.ArgumentParser(description="Mihon Türkçe APK aynası.")
    parser.add_argument("--root", default=BASE_DIR, help="depo kökü (varsayılan: bu depo)")
    parser.add_argument("--include-unverified", action="store_true",
                        help="cf_protected, failing ve unverified kaynakları da dahil et")
    args = parser.parse_args(argv)

    root = args.root
    out_dir = os.path.join(root, OUT_DIR_NAME)
    apk_dir = os.path.join(out_dir, "apk")
    sources_path = os.path.join(root, "sources", "tr", "sources.json")

    try:
        index_doc = json.loads(fetch_with_retry(INDEX_URL, fetcher=fetcher).decode("utf-8"))
    except (OSError, ValueError) as exc:
        print(f"mihon_publish: upstream index.json alınamadı: {exc}", file=sys.stderr)
        return 1
    if not isinstance(index_doc, dict):
        print("mihon_publish: upstream index.json beklenen biçimde değil", file=sys.stderr)
        return 1

    items = mihon_packages(load_json(sources_path, {}), args.include_unverified)
    prev_index = load_json(os.path.join(out_dir, "index.min.json"), []) or []
    prev_by_pkg = {e.get("pkg"): e for e in prev_index if isinstance(e, dict) and e.get("pkg")}

    result, stats, skipped = sync(items, upstream_map(index_doc), prev_by_pkg, apk_dir, fetcher=fetcher)
    removed = remove_stale(apk_dir, {e["apk"] for e in result})

    write_atomic(os.path.join(out_dir, "index.min.json"), index_text(result))
    write_atomic(os.path.join(out_dir, "README.md"), readme_text(repo_slug()))

    summary = summary_text(stats, skipped, removed, len(items), len(result))
    sys.stdout.write(summary)
    step_summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if step_summary:
        with open(step_summary, "a", encoding="utf-8") as fh:
            fh.write(summary)
    return 0


if __name__ == "__main__":
    sys.exit(main())
