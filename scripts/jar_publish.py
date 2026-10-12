#!/usr/bin/env python3
"""Kototoro JAR yayın alt komutları: decide, index ve readme.

decide: derleme gerekip gerekmediğine karar verir. Karar stdout'a ve GITHUB_OUTPUT'a
        'build=true|false' ve 'reason=...' olarak yazılır.
index:  --bucket turkce|global|ozel için plugin.jar, index.min.json, build_info.json ve README.md
        yazar. Yayınlanabilir kaynak yoksa index.min.json '[]' olur ve jar gerekmez.
readme: yalnızca README.md yazar.
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
JAR_NAME = "plugin.jar"
REPO_SLUG_FALLBACK = "<GITHUB_REPOSITORY>"
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# One JAR repository per bucket. turkce keeps the original package id so installs update in place.
BUCKETS = {
    "turkce": {"name": "Pulsar TR Manga Hub", "pkg": PKG, "lang": "tr", "path": "turkce/jar",
               "sources": os.path.join("sources", "tr", "sources.json"),
               "what": "Türkçe (tr_native) kaynakları içeren Kototoro JAR eklentisi.",
               "bucket_label": "Türkçe"},
    "global": {"name": "Pulsar Global Manga Hub", "pkg": PKG + ".global", "lang": "all",
               "path": "global/jar",
               "sources": os.path.join("sources", "global", "sources.json"),
               "what": "Kotatsu-Redo parser'larının tüm dillerini içeren Kototoro JAR eklentisi. "
                       "Yalnızca probe'dan geçen (ok) kaynaklar yayınlanır.",
               "bucket_label": "Global"},
    "ozel": {"name": "Pulsar Özel Manga Hub", "pkg": PKG + ".ozel", "lang": "tr", "path": "ozel/jar",
             "sources": os.path.join("sources", "tr", "sources.json"),
             "what": "Kaynak ekle akışıyla üretilen, yalnızca Türkçe özel siteler için parser'lar. "
                     "Üretilmiş parser yoksa dizin boştur ([]).",
             "bucket_label": "Özel"},
}


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


def readme_text(slug, bucket):
    info = BUCKETS[bucket]
    url = f"https://raw.githubusercontent.com/{slug}/main/{info['path']}"
    return f"""# Pulsar TR Manga Hub: {info['bucket_label']} Kototoro eklentisi

{info['what']}
`.github/workflows/build-jar.yml` iş akışı bu klasörü günceller.

## Kototoro'ya ekleme

1. Kototoro'yu açın ve **Ayarlar → İçerik Kaynakları → Eklentiler → JAR Depoları → Depo ekle** yolunu izleyin.
2. Adres olarak şunu girin:

   `{url}`

3. Depo eklendikten sonra kaynaklar Kototoro içinde görünür.

Not: Depo özel (private) iken bu adres çalışmaz. Depo herkese açık (public) yapıldığında çalışır.

## Lisans

Upstream proje Kotatsu-Redo/kotatsu-parsers-redo, GPL-3.0 lisanslıdır. Bu depodaki kaynak
dönüşümleri ve derleme tarifi `.github/workflows/build-jar.yml` ile açıktır.

## Uyarı

Resmi Kotatsu uygulaması harici jar desteklemez. Bu eklentiyi kullanmak için Kototoro gerekir.

## Dosyalar

- `index.min.json`: eklenti dizini
- `apk/plugin.jar`: derlenmiş eklenti (dizin boşsa yok)
- `build_info.json`: derleme bilgileri (parmak izi, upstream commit, sha256)
"""


def placeholder_index():
    return "[]\n"


def index_sources(prep, by_parser, bucket, include_unverified):
    """Return the index 'sources' list for one bucket. Each item keeps its own language code."""
    kept = sorted(prep.get("kept_ids") or [])
    langs = prep.get("langs") or {}
    extras = {x["id"]: x for x in (prep.get("extra_sources") or [])}
    sources = []
    for pid in kept:
        if pid in extras:
            x = extras[pid]
            sources.append({"name": x.get("name") or pid, "id": pid, "lang": x.get("lang") or "tr"})
            continue
        entries = [e for e in by_parser.get(pid, [])
                   if rules.is_publishable(e, include_unverified, allow_multilang=bucket == "global")]
        if not entries:
            continue
        name = entries[0].get("name") or pid
        sources.append({"name": name, "id": pid, "lang": langs.get(pid) or bucket_lang(bucket)})
    return sources


def bucket_lang(bucket):
    return BUCKETS[bucket]["lang"]


def nsfw_of(prep, sources_ids, by_parser):
    extras = {x["id"]: x for x in (prep.get("extra_sources") or [])}
    for pid in sources_ids:
        if pid in extras and extras[pid].get("nsfw"):
            return 1
        if any(e.get("nsfw") for e in by_parser.get(pid, [])):
            return 1
    return 0


def cmd_index(args):
    prep = load_prepare(args.prepare)
    bucket = args.bucket
    info_meta = BUCKETS[bucket]
    patched = prep.get("patched_domains") or []
    kept = sorted(prep.get("kept_ids") or [])
    by_parser = jar_prepare.load_sources(args.sources)
    include_unverified = bool(prep.get("include_unverified"))
    sources = index_sources(prep, by_parser, bucket, include_unverified)

    os.makedirs(args.out, exist_ok=True)
    apk_dir = os.path.join(args.out, "apk")
    dest = os.path.join(apk_dir, JAR_NAME)
    if not sources:
        # Nothing publishable: the directory is an empty index and carries no jar.
        if os.path.isfile(dest):
            os.remove(dest)
        with open(os.path.join(args.out, "index.min.json"), "w", encoding="utf-8") as fh:
            fh.write(placeholder_index())
        return 0

    if not os.path.isfile(args.jar):
        fail(f"jar dosyası yok: {args.jar}")
    os.makedirs(apk_dir, exist_ok=True)
    shutil.copyfile(args.jar, dest)

    run = args.run_number
    index = [{
        "name": info_meta["name"],
        "pkg": info_meta["pkg"],
        "version": f"1.0.{run}",
        "code": run,
        "apk": JAR_NAME,
        "lang": info_meta["lang"],
        "nsfw": nsfw_of(prep, [s["id"] for s in sources], by_parser),
        "sources": sources,
    }]
    with open(os.path.join(args.out, "index.min.json"), "w", encoding="utf-8") as fh:
        json.dump(index, fh, ensure_ascii=False, separators=(",", ":"))
        fh.write("\n")

    commit = prep.get("upstream_commit")
    info = {
        "bucket": bucket,
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
        fh.write(readme_text(repo_slug(), bucket))
    return 0


def cmd_readme(args):
    """Write only README.md for a bucket (used for the empty placeholder directories)."""
    os.makedirs(args.out, exist_ok=True)
    with open(os.path.join(args.out, "README.md"), "w", encoding="utf-8") as fh:
        fh.write(readme_text(repo_slug(), args.bucket))
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

    idx = sub.add_parser("index", help="bucket klasörünü yaz")
    idx.add_argument("--bucket", required=True, choices=sorted(BUCKETS))
    idx.add_argument("--prepare", required=True)
    idx.add_argument("--jar", default="plugin.jar")
    idx.add_argument("--out", required=True)
    idx.add_argument("--run-number", type=int, default=0)
    idx.add_argument("--fallback", type=int, choices=[0, 1], default=0)
    idx.add_argument("--sources", default=os.path.join(BASE_DIR, "sources", "tr", "sources.json"))
    idx.set_defaults(func=cmd_index)

    rd = sub.add_parser("readme", help="yalnızca bucket README.md dosyasını yaz")
    rd.add_argument("--bucket", required=True, choices=sorted(BUCKETS))
    rd.add_argument("--out", required=True)
    rd.set_defaults(func=cmd_readme)
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
