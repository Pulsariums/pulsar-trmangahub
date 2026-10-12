#!/usr/bin/env python3
"""Keiyoushi (Mihon) deposundaki Türkçe (lang == "tr") eklentileri repo-mihon/ altına aynalar.

Akış:
  1. keiyoushi/extensions 'repo' dalındaki index.min.json okunur.
  2. Yalnızca lang == "tr" girdiler alınır. sources/tr/published.json içindeki mihon
     paketlerinden (pkg) biriyle eşleşenler tutulur. published.json'da mihon bilgisi
     yoksa tüm tr girdiler alınır, ancak sources/tr/sources.json içinde tamamı karantinada
     olan paketler atlanır.
  3. Her APK indirilir (zaten varsa ve sürümü değişmediyse indirilmez).
  4. Artık dizinde olmayan APK'lar silinir; index.min.json ve README.md yazılır.

Yalnızca standart kütüphane kullanılır. Ağ hatası olan bir APK için önceki sürüm varsa
o girdi korunur; yoksa girdi dizinden çıkarılır. Upstream index'i alınamazsa hiçbir dosya
değiştirilmez ve çıkış kodu 1 olur.
"""

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request

LANG = "tr"
UPSTREAM_BASE = "https://raw.githubusercontent.com/keiyoushi/extensions/repo"
INDEX_URL = f"{UPSTREAM_BASE}/index.min.json"
APK_BASE_URL = f"{UPSTREAM_BASE}/apk/"
USER_AGENT = "pulsar-trmangahub-mihon-mirror/1.0"
TIMEOUT_SECONDS = 60
MAX_ATTEMPTS = 3
APK_MAGIC = b"PK\x03\x04"
APK_NAME_RE = re.compile(r"^[A-Za-z0-9._-]+\.apk$")

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
    mode = "wb" if isinstance(data, bytes) else "w"
    kwargs = {} if isinstance(data, bytes) else {"encoding": "utf-8"}
    with open(tmp, mode, **kwargs) as fh:
        fh.write(data)
    os.replace(tmp, path)


def published_mihon_pkgs(published):
    """published.json içindeki mihon paket kümesi. Bilgi yoksa None."""
    items = (published or {}).get("mihon") or []
    pkgs = {m.get("pkg") for m in items if isinstance(m, dict) and m.get("pkg")}
    return pkgs or None


def fully_quarantined_pkgs(sources_doc):
    """Tüm kaynakları karantinada olan mihon paketleri."""
    statuses = {}
    for src in (sources_doc or {}).get("sources", []):
        pkg = (((src.get("formats") or {}).get("mihon")) or {}).get("pkg")
        if pkg:
            statuses.setdefault(pkg, []).append(src.get("status"))
    return {pkg for pkg, sts in statuses.items() if sts and all(s == "quarantined" for s in sts)}


def select_entries(index, published_pkgs, quarantined):
    kept, seen = [], set()
    for entry in index:
        if not isinstance(entry, dict) or entry.get("lang") != LANG:
            continue
        pkg, apk = entry.get("pkg"), entry.get("apk")
        if not pkg or not apk or not APK_NAME_RE.match(apk) or pkg in seen:
            continue
        if published_pkgs is not None:
            if pkg not in published_pkgs:
                continue
        elif pkg in quarantined:
            continue
        seen.add(pkg)
        kept.append(entry)
    return kept


def sync_apks(entries, prev_by_pkg, apk_dir, fetcher=None):
    """Girdileri APK'larla eşleştirir. Döner: (sonuç girdileri, istatistik, hata listesi)."""
    os.makedirs(apk_dir, exist_ok=True)
    result, failures = [], []
    stats = {"indirildi": 0, "yeniden_kullanildi": 0, "eski_korundu": 0, "dusurildu": 0}
    for entry in entries:
        apk = entry["apk"]
        path = os.path.join(apk_dir, apk)
        prev = prev_by_pkg.get(entry["pkg"])
        if (prev and prev.get("version") == entry.get("version") and prev.get("apk") == apk
                and os.path.isfile(path)):
            result.append(entry)
            stats["yeniden_kullanildi"] += 1
            continue
        try:
            data = fetch_with_retry(APK_BASE_URL + apk, fetcher=fetcher)
            if not data.startswith(APK_MAGIC):
                raise ValueError("APK (zip) imzası yok")
            write_atomic(path, data)
            result.append(entry)
            stats["indirildi"] += 1
        except (OSError, ValueError) as exc:
            failures.append((entry["pkg"], str(exc)))
            if prev and prev.get("apk") and os.path.isfile(os.path.join(apk_dir, prev["apk"])):
                result.append(prev)
                stats["eski_korundu"] += 1
            else:
                stats["dusurildu"] += 1
    return result, stats, failures


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

Bu klasör, keiyoushi/extensions deposundaki Türkçe (`lang: tr`) Mihon eklentilerinin
birebir APK aynasıdır. `.github/workflows/build-mihon.yml` iş akışı günceller.

## Mihon'a ekleme

1. Mihon'u açın ve **Ayarlar → Eklentiler → Depolar → Depo ekle** yolunu izleyin.
2. Adres olarak şunu girin:

   `https://raw.githubusercontent.com/{slug}/main/repo-mihon/`

   Not: Adresin sonundaki `index.min.json` dosyası Mihon tarafından otomatik bulunur.

## Dosyalar

- `index.min.json`: eklenti dizini (upstream biçiminde, yalnızca Türkçe girdiler)
- `apk/`: eklenti APK dosyaları
"""


def summary_text(total_tr, kept_count, stats, failures, removed, published_known):
    lines = [
        "## Mihon deposu: Türkçe APK aynası",
        "",
        f"- Upstream'de tr girdisi: {total_tr}",
        f"- Filtre: {'published.json mihon paketleri' if published_known else 'karantina dışı tr girdileri (published.json mihon bilgisi yok)'}",
        f"- Dizinde kalan eklenti: {kept_count}",
        f"- İndirilen APK: {stats['indirildi']}",
        f"- Yeniden kullanılan APK: {stats['yeniden_kullanildi']}",
        f"- İndirme hatası nedeniyle önceki sürüm korunan: {stats['eski_korundu']}",
        f"- İndirme hatası nedeniyle dizinden çıkarılan: {stats['dusurildu']}",
        f"- Silinen eski APK: {len(removed)}",
    ]
    if failures:
        lines.append("")
        lines.append("Hatalar:")
        for pkg, reason in failures:
            lines.append(f"- {pkg}: {reason}")
    return "\n".join(lines) + "\n"


def repo_slug():
    return os.environ.get("GITHUB_REPOSITORY") or REPO_SLUG_FALLBACK


def main(argv=None, fetcher=None):
    parser = argparse.ArgumentParser(description="Mihon Türkçe APK aynası.")
    parser.add_argument("--root", default=BASE_DIR, help="depo kökü (varsayılan: bu depo)")
    args = parser.parse_args(argv)

    root = args.root
    out_dir = os.path.join(root, OUT_DIR_NAME)
    apk_dir = os.path.join(out_dir, "apk")
    published_path = os.path.join(root, "sources", "tr", "published.json")
    sources_path = os.path.join(root, "sources", "tr", "sources.json")

    try:
        index = json.loads(fetch_with_retry(INDEX_URL, fetcher=fetcher).decode("utf-8"))
    except (OSError, ValueError) as exc:
        print(f"mihon_publish: upstream index alınamadı: {exc}", file=sys.stderr)
        return 1
    if not isinstance(index, list):
        print("mihon_publish: upstream index beklenen biçimde değil", file=sys.stderr)
        return 1

    published_pkgs = published_mihon_pkgs(load_json(published_path, {}))
    quarantined = fully_quarantined_pkgs(load_json(sources_path, {}))
    total_tr = sum(1 for e in index if isinstance(e, dict) and e.get("lang") == LANG)
    candidates = select_entries(index, published_pkgs, quarantined)

    prev_index = load_json(os.path.join(out_dir, "index.min.json"), []) or []
    prev_by_pkg = {e.get("pkg"): e for e in prev_index if isinstance(e, dict) and e.get("pkg")}

    result, stats, failures = sync_apks(candidates, prev_by_pkg, apk_dir, fetcher=fetcher)
    removed = remove_stale(apk_dir, {e["apk"] for e in result})

    write_atomic(os.path.join(out_dir, "index.min.json"), index_text(result))
    write_atomic(os.path.join(out_dir, "README.md"), readme_text(repo_slug()))

    summary = summary_text(total_tr, len(result), stats, failures, removed,
                           published_pkgs is not None)
    sys.stdout.write(summary)
    step_summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if step_summary:
        with open(step_summary, "a", encoding="utf-8") as fh:
            fh.write(summary)
    return 0


if __name__ == "__main__":
    sys.exit(main())
