#!/usr/bin/env python3
"""Kototoro JAR yayın alt komutları: decide ve index.

decide: derleme gerekip gerekmediğine karar verir. Karar stdout'a ve GITHUB_OUTPUT'a
        'build=true|false' ve 'reason=...' olarak yazılır.
index:  plugin.jar, index.min.json, build_info.json ve README.md dosyalarını repo klasörüne yazar.
"""

import argparse
import datetime
import hashlib
import json
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import jar_prepare  # noqa: E402
import rules  # noqa: E402

PKG = "org.pulsarium.trmangahub"
NAME = "Pulsar TR Manga Hub"
JAR_NAME = "plugin.jar"
REPO_SLUG_FALLBACK = "<GITHUB_REPOSITORY>"


def fail(message):
    print(f"jar_publish: {message}", file=sys.stderr)
    raise SystemExit(2)


def load_json_or_none(path):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def load_prepare(path):
    data = load_json_or_none(path)
    if not isinstance(data, dict):
        fail(f"hazırlık raporu okunamadı: {path}")
    return data


def fingerprint(commit, kept_ids, patched):
    pairs = sorted([p.get("old") or "", p.get("new") or ""] for p in patched)
    payload = json.dumps({"commit": commit or "", "kept": sorted(kept_ids), "domains": pairs},
                         ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def repo_slug():
    return os.environ.get("GITHUB_REPOSITORY") or REPO_SLUG_FALLBACK


def emit(build, reason):
    lines = [f"build={'true' if build else 'false'}", f"reason={reason}"]
    for line in lines:
        print(line)
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a", encoding="utf-8") as fh:
            fh.write("\n".join(lines) + "\n")


def cmd_decide(args):
    prep = load_prepare(args.prepare)
    commit = (jar_prepare.upstream_commit(args.upstream) if os.path.isdir(args.upstream) else None) \
        or prep.get("upstream_commit")
    fp = fingerprint(commit, prep.get("kept_ids") or [], prep.get("patched_domains") or [])
    info = load_json_or_none(args.info)
    if args.force == 1:
        build, reason = True, "zorunlu (force)"
    elif not isinstance(info, dict):
        build, reason = True, "ilk derleme (build_info yok)"
    elif info.get("fingerprint") != fp:
        build, reason = True, "parmak izi değişti"
    else:
        build, reason = False, "parmak izi aynı, atlandı"
    emit(build, reason)
    return 0


def readme_text(slug):
    return f"""# Pulsar TR Manga Hub: Kototoro eklentisi

Bu klasör, Türkçe kaynakları içeren Kototoro JAR eklentisini ve eklenti dizinini içerir.
`.github/workflows/build-jar.yml` iş akışı kaynakları derler ve bu klasörü günceller.

## Kototoro'ya ekleme

1. Kototoro'yu açın ve **Ayarlar → İçerik Kaynakları → Eklentiler → JAR Depoları → Depo ekle** yolunu izleyin.
2. Adres olarak şunu girin:

   `https://raw.githubusercontent.com/{slug}/main/repo`

3. Depo eklendikten sonra kaynaklar Kototoro içinde görünür.

Not: Depo özel (private) iken bu adres çalışmaz. Depo herkese açık (public) yapıldığında çalışır.

## Lisans

Upstream proje Kotatsu-Redo/kotatsu-parsers-redo, GPL-3.0 lisanslıdır. Bu depodaki kaynak
dönüşümleri ve derleme tarifi `.github/workflows/build-jar.yml` ile açıktır.

## Uyarı

Resmi Kotatsu uygulaması harici jar desteklemez. Bu eklentiyi kullanmak için Kototoro gerekir.

## Dosyalar

- `index.min.json`: eklenti dizini
- `apk/plugin.jar`: derlenmiş eklenti
- `build_info.json`: derleme bilgileri (parmak izi, upstream commit, sha256)
"""


def cmd_index(args):
    prep = load_prepare(args.prepare)
    kept = sorted(prep.get("kept_ids") or [])
    patched = prep.get("patched_domains") or []
    if not os.path.isfile(args.jar):
        fail(f"jar dosyası yok: {args.jar}")

    apk_dir = os.path.join(args.out, "apk")
    os.makedirs(apk_dir, exist_ok=True)
    dest = os.path.join(apk_dir, JAR_NAME)
    shutil.copyfile(args.jar, dest)

    by_parser = jar_prepare.load_sources(args.sources)
    include_unverified = bool(prep.get("include_unverified"))
    sources = []
    nsfw = 0
    for pid in kept:
        entries = [e for e in by_parser.get(pid, []) if rules.is_publishable(e, include_unverified)]
        if not entries:
            continue
        if any(e.get("nsfw") for e in entries):
            nsfw = 1
        name = entries[0].get("name") if entries and entries[0].get("name") else pid
        sources.append({"name": name, "id": pid, "lang": "tr"})

    run = args.run_number
    index = [{
        "name": NAME,
        "pkg": PKG,
        "version": f"1.0.{run}",
        "code": run,
        "apk": JAR_NAME,
        "lang": "tr",
        "nsfw": nsfw,
        "sources": sources,
    }]
    with open(os.path.join(args.out, "index.min.json"), "w", encoding="utf-8") as fh:
        json.dump(index, fh, ensure_ascii=False, separators=(",", ":"))
        fh.write("\n")

    commit = prep.get("upstream_commit")
    info = {
        "fingerprint": fingerprint(commit, kept, patched),
        "upstream_commit": commit,
        "builtAt": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "jarSha256": sha256_file(dest),
        "jarBytes": os.path.getsize(dest),
        "keptCount": len(kept),
        "patchedDomains": patched,
        "fallback": args.fallback,
        "runNumber": run,
    }
    with open(os.path.join(args.out, "build_info.json"), "w", encoding="utf-8") as fh:
        json.dump(info, fh, ensure_ascii=False, indent=2)
        fh.write("\n")

    with open(os.path.join(args.out, "README.md"), "w", encoding="utf-8") as fh:
        fh.write(readme_text(repo_slug()))
    return 0


def build_parser():
    parser = argparse.ArgumentParser(description="Kototoro JAR yayın alt komutları.")
    sub = parser.add_subparsers(dest="command", required=True)

    dec = sub.add_parser("decide", help="derleme gerekip gerekmediğine karar ver")
    dec.add_argument("--upstream", required=True)
    dec.add_argument("--prepare", required=True)
    dec.add_argument("--info", required=True)
    dec.add_argument("--force", type=int, choices=[0, 1], default=0)
    dec.set_defaults(func=cmd_decide)

    idx = sub.add_parser("index", help="repo klasörünü yaz")
    idx.add_argument("--prepare", required=True)
    idx.add_argument("--jar", required=True)
    idx.add_argument("--out", required=True)
    idx.add_argument("--run-number", type=int, required=True)
    idx.add_argument("--fallback", type=int, choices=[0, 1], default=0)
    idx.add_argument("--sources", default=os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "sources", "tr", "sources.json"))
    idx.set_defaults(func=cmd_index)
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
