#!/usr/bin/env python3
"""Kototoro JAR yayın alt komutları: decide, index, merge-index ve readme.

decide:      derleme gerekip gerekmediğine karar verir. Karar stdout'a ve GITHUB_OUTPUT'a
             'build=true|false' ve 'reason=...' olarak yazılır.
index:       --bucket tr|tr_nsfw|global|global_nsfw için <out>/apk/<jar> yazar, bucket girdisini
             <out>/state/<bucket>.entry.json ve build_info'yu <out>/state/<bucket>.build_info.json
             dosyalarına yazar, ardından <out>/index.min.json'u yeniden birleştirir. Yayınlanabilir
             kaynak yoksa bucket girdisi null olur ve jar gerekmez.
merge-index: <out>/index.min.json dosyasını state/ girdilerinden yeniden yazar.
readme:      <out>/README.md dosyasını yazar.
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
REPO_SLUG_FALLBACK = "<GITHUB_REPOSITORY>"
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JAR_DIR = "jar"

BUCKETS = {
    "tr": {"name": "Pulsar TR Manga Hub", "pkg": PKG, "lang": "tr", "nsfw": 0, "jar": "tr.jar"},
    "tr_nsfw": {"name": "Pulsar TR Manga Hub (NSFW)", "pkg": PKG + ".trnsfw", "lang": "tr", "nsfw": 1,
                "jar": "tr-nsfw.jar"},
    "global": {"name": "Pulsar Global Manga Hub", "pkg": PKG + ".global", "lang": "all", "nsfw": 0,
               "jar": "global.jar"},
    "global_nsfw": {"name": "Pulsar Global Manga Hub (NSFW)", "pkg": PKG + ".globalnsfw", "lang": "all",
                    "nsfw": 1, "jar": "global-nsfw.jar"},
}
BUCKET_ORDER = ("tr", "tr_nsfw", "global", "global_nsfw")
GLOBAL_BUCKETS = ("global", "global_nsfw")


def fail(message):
    print(f"jar_publish: {message}", file=sys.stderr)
    raise SystemExit(2)


def load_json_or_none(path):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def write_json(path, payload, **kwargs):
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, **kwargs)
        fh.write("\n")


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
    url = f"https://raw.githubusercontent.com/{slug}/main/{JAR_DIR}"
    return f"""# Pulsar Manga Hub JAR paketleri

Bu depo Kototoro için dört ayrı JAR paketi içerir. Her paket Kototoro'da ayrı olarak indirilebilir.

| Paket | Kapsam |
| --- | --- |
| `tr` | Yalnız Türkçe kaynaklar, NSFW olmayan |
| `tr_nsfw` | Yalnız Türkçe kaynaklar, NSFW |
| `global` | Türkçe dışındaki tüm diller, NSFW olmayan |
| `global_nsfw` | Türkçe dışındaki tüm diller, NSFW |

Kaynak ekle akışıyla eklenen özel Türkçe siteler de NSFW bayrağına göre `tr` veya `tr_nsfw` paketine girer.

## Kototoro'ya ekleme

1. Kototoro'da **Paketler** bölümünü açın.
2. Depo adresi olarak şunu kullanın:

   `{url}`

3. İstediğiniz paketi seçip indirin.

`index.min.json` tüm paketlerin dizinidir. Paket dosyaları `apk/` altındadır ve
`.github/workflows/build-jar.yml` iş akışı tarafından güncellenir.
"""


def index_sources(prep, by_parser, bucket, include_unverified):
    """Return the index 'sources' list for one package. Each item keeps its own language code."""
    kept = sorted(prep.get("kept_ids") or [])
    langs = prep.get("langs") or {}
    extras = {x["id"]: x for x in (prep.get("extra_sources") or [])}
    allow_multilang = bucket in GLOBAL_BUCKETS
    sources = []
    for pid in kept:
        if pid in extras:
            x = extras[pid]
            name = x.get("name") or pid
            lang = x.get("lang") or "tr"
        else:
            entries = [e for e in by_parser.get(pid, [])
                       if rules.is_publishable(e, include_unverified, allow_multilang=allow_multilang)]
            if not entries:
                continue
            name = entries[0].get("name") or pid
            lang = langs.get(pid) or bucket_lang(bucket)
        if not lang_fits(bucket, lang):
            continue
        sources.append({"name": name, "id": pid, "lang": lang})
    return sources


def lang_fits(bucket, lang):
    is_tr = lang == "tr"
    return not is_tr if bucket in GLOBAL_BUCKETS else is_tr


def bucket_lang(bucket):
    return BUCKETS[bucket]["lang"]


def merge_index(out):
    entries = []
    for bucket in BUCKET_ORDER:
        entry = load_json_or_none(os.path.join(out, "state", f"{bucket}.entry.json"))
        if isinstance(entry, dict):
            entries.append(entry)
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, "index.min.json"), "w", encoding="utf-8") as fh:
        json.dump(entries, fh, ensure_ascii=False, separators=(",", ":"))
        fh.write("\n")
    return entries


def cmd_index(args):
    prep = load_prepare(args.prepare)
    bucket = args.bucket
    meta = BUCKETS[bucket]
    patched = prep.get("patched_domains") or []
    kept = sorted(prep.get("kept_ids") or [])
    by_parser = jar_prepare.load_sources(args.sources)
    include_unverified = bool(prep.get("include_unverified"))
    sources = index_sources(prep, by_parser, bucket, include_unverified)

    state_dir = os.path.join(args.out, "state")
    dest = os.path.join(args.out, "apk", meta["jar"])
    entry_path = os.path.join(state_dir, f"{bucket}.entry.json")
    info_path = os.path.join(state_dir, f"{bucket}.build_info.json")
    os.makedirs(state_dir, exist_ok=True)
    if not sources:
        # Nothing publishable: this package is absent from the index and carries no jar.
        if os.path.isfile(dest):
            os.remove(dest)
        if os.path.isfile(info_path):
            os.remove(info_path)
        write_json(entry_path, None)
        merge_index(args.out)
        return 0

    if not os.path.isfile(args.jar):
        fail(f"jar dosyası yok: {args.jar}")
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    shutil.copyfile(args.jar, dest)

    run = args.run_number
    write_json(entry_path, {
        "name": meta["name"],
        "pkg": meta["pkg"],
        "version": f"1.0.{run}",
        "code": run,
        "apk": meta["jar"],
        "lang": meta["lang"],
        "nsfw": meta["nsfw"],
        "sources": sources,
    }, separators=(",", ":"))

    commit = prep.get("upstream_commit")
    write_json(info_path, {
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
    }, indent=2)
    merge_index(args.out)
    return 0


def cmd_merge_index(args):
    merge_index(args.out)
    return 0


def cmd_readme(args):
    """Write the single README.md of the JAR directory."""
    os.makedirs(args.out, exist_ok=True)
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

    idx = sub.add_parser("index", help="paket jar'ını, girdisini ve index.min.json'u yaz")
    idx.add_argument("--bucket", required=True, choices=sorted(BUCKETS))
    idx.add_argument("--prepare", required=True)
    idx.add_argument("--jar", default="plugin.jar")
    idx.add_argument("--out", required=True)
    idx.add_argument("--run-number", type=int, default=0)
    idx.add_argument("--fallback", type=int, choices=[0, 1], default=0)
    idx.add_argument("--sources", default=os.path.join(BASE_DIR, "sources", "tr", "sources.json"))
    idx.set_defaults(func=cmd_index)

    mg = sub.add_parser("merge-index", help="state/ girdilerinden index.min.json yaz")
    mg.add_argument("--out", required=True)
    mg.set_defaults(func=cmd_merge_index)

    rd = sub.add_parser("readme", help="yalnızca README.md dosyasını yaz")
    rd.add_argument("--out", required=True)
    rd.set_defaults(func=cmd_readme)
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
