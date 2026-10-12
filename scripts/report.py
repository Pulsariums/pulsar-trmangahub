#!/usr/bin/env python3
"""Markdown run raporu: python scripts/report.py {sync,health,add}.

GITHUB_STEP_SUMMARY ayarlıysa rapor oraya eklenir, değilse stdout'a yazılır.
Girdi dosyası yoksa ilgili bölüm "yok" notuyla geçilir; script hata vermez.
"""

import argparse
import collections
import json
import os
import subprocess
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROBE_PATH = os.path.join(BASE_DIR, "data", "probe_results.json")
SOURCES_PATH = os.path.join(BASE_DIR, "sources", "tr", "sources.json")
REPORT_PATH = os.path.join(BASE_DIR, "sources", "tr", "REPORT.md")
ANALYZE_PATH = os.path.join(BASE_DIR, "data", "analyze_result.json")

SETTINGS = ("DRY_RUN", "FAIL_THRESHOLD", "RUN_ALTERNATIVES",
            "REFRESH_KOTATSU", "SAFETY_RATIO")
PUBLISHED_STATUSES = ("published", "cf_protected_published")
SOURCE_STATUSES = ("published", "cf_protected_published", "failing", "quarantined")
PROBE_STATUSES = ("ok", "cf_protected", "dead", "parked", "other", "blocked")
OK_PROBE_STATUSES = ("ok", "cf_protected")
TOP_REASONS = 10
HEALTH_ROWS = 60
CHANGES_HEADING = "## Bu run'da değişenler"


def load_json(path, default=None):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return default


def read_text(path):
    try:
        with open(path, encoding="utf-8") as fh:
            return fh.read()
    except OSError:
        return None


def cell(value):
    text = "" if value is None else str(value)
    return text.replace("|", "\\|").replace("\r", " ").replace("\n", " ").strip()


def table(headers, rows):
    lines = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    for row in rows:
        lines.append("| " + " | ".join(cell(c) for c in row) + " |")
    return lines


def table_or(headers, rows, empty):
    return table(headers, rows) if rows else [empty]


def reason_prefix(reason):
    head = str(reason or "").split(";", 1)[0].split(":", 1)[0].strip()
    return head or "(boş)"


def previous_sources(path=None):
    if path:
        return load_json(path)
    try:
        out = subprocess.run(["git", "-C", BASE_DIR, "show", "HEAD:sources/tr/sources.json"],
                             capture_output=True, text=True, encoding="utf-8", timeout=30, check=True)
        return json.loads(out.stdout)
    except (subprocess.SubprocessError, OSError, ValueError):
        return None


def report_changes(text):
    out, grab = [], False
    for line in text.splitlines():
        if line.startswith("## "):
            grab = line.strip() == CHANGES_HEADING
            continue
        if grab and line.strip():
            out.append(line.strip())
    return out


def sync_section(args):
    sources = load_json(SOURCES_PATH)
    probes = load_json(PROBE_PATH)
    entries = (sources or {}).get("sources") or []
    lines = ["## Senkron raporu", ""]
    if os.environ.get("CANCELLED", "").strip().lower() == "true":
        lines += ["> ⛔ **Şalter devreye girdi**: bu run'da TR kaynak yayını iptal edildi, "
                  "hiçbir dosya değiştirilmedi.", ""]

    lines += ["### Seçilen ayarlar", ""]
    lines += table(["Ayar", "Değer"],
                   [(name, os.environ.get(name) or "(ayarlı değil)") for name in SETTINGS])
    lines.append("")

    lines += ["### Kaynak durumları", ""]
    if sources is None:
        lines += ["sources.json okunamadı.", ""]
    else:
        counts = collections.Counter(e.get("status") for e in entries)
        counts["unverified"] = sum(1 for e in entries if e.get("unverified"))
        lines += table(["Durum", "Adet"],
                       [(k, counts.get(k, 0)) for k in SOURCE_STATUSES + ("unverified",)])
        lines.append("")

    meta = (probes or {}).get("meta") or {}
    pc = meta.get("counts") or {}
    lines += ["### Probe sayıları", ""]
    if probes is None:
        lines += ["probe_results.json okunamadı.", ""]
    else:
        rows = [(k, pc.get(k, 0)) for k in PROBE_STATUSES]
        rows += [("probe edilen domain", meta.get("unique_domains_probed", 0)),
                 ("fonksiyonel kontrol false", (meta.get("functional") or {}).get("false", 0))]
        lines += table(["Probe durumu", "Adet"], rows) + [""]

    results = (probes or {}).get("results") or []
    reasons = collections.Counter(reason_prefix(r.get("reason")) for r in results
                                  if r.get("status") not in OK_PROBE_STATUSES)
    lines += ["### İlk 10 hata nedeni", ""]
    lines += table_or(["Neden", "Adet"], reasons.most_common(TOP_REASONS), "Hata nedeni yok.")
    lines.append("")

    prev = previous_sources(args.prev_sources) if sources is not None else None
    if prev is not None:
        prev_by = {e.get("id"): e for e in prev.get("sources") or []}
        new_q = [e for e in entries if e.get("status") == "quarantined" and e.get("id") in prev_by
                 and prev_by[e.get("id")].get("status") != "quarantined"]
        revived = [e for e in entries if e.get("status") in PUBLISHED_STATUSES
                   and prev_by.get(e.get("id"), {}).get("status") == "quarantined"]
        lines += ["### Bu run'da karantinaya girenler", ""]
        lines += table_or(["Kaynak", "Önceki", "Şimdi", "Neden"],
                          [(e.get("id"), prev_by[e.get("id")].get("status"), e.get("status"),
                            e.get("reason")) for e in new_q], "Yok.")
        lines += ["", "### Bu run'da geri dirilenler", ""]
        lines += table_or(["Kaynak", "Önceki", "Şimdi"],
                          [(e.get("id"), "quarantined", e.get("status")) for e in revived], "Yok.")
        lines.append("")

    report_text = read_text(REPORT_PATH)
    if report_text is not None:
        lines += ["### REPORT.md: bu run'da değişenler", ""]
        lines += report_changes(report_text) or ["REPORT.md içinde değişiklik bölümü yok."]
        lines.append("")

    alts = [e for e in entries if e.get("alternative")]
    lines += ["### Bulunan alternatifler", ""]
    lines += table_or(["Kaynak", "Alternatif", "Yöntem", "Güven"],
                      [(f"{e.get('name')} ({e.get('id')})", e["alternative"].get("domain"),
                        e["alternative"].get("how"), e["alternative"].get("confidence")) for e in alts],
                      "Alternatif bulunamadı.")
    return lines


def health_section(_args=None):
    probes = load_json(PROBE_PATH)
    lines = ["## Sağlık raporu", ""]
    if probes is None:
        return lines + ["probe sonucu yok (data/probe_results.json bulunamadı).", ""]
    meta = probes.get("meta") or {}
    results = probes.get("results") or []
    pc = meta.get("counts") or {}
    functional = meta.get("functional") or {}

    lines += ["### Sayılar", ""]
    rows = [(k, pc.get(k, 0)) for k in PROBE_STATUSES]
    rows += [("probe edilen kayıt", meta.get("records_probed", len(results))),
             ("benzersiz domain", meta.get("unique_domains_probed", 0)),
             ("fonksiyonel kontrol true", functional.get("true", 0)),
             ("fonksiyonel kontrol false", functional.get("false", 0)),
             ("fonksiyonel kontrol yok", functional.get("null", 0)),
             ("motor uyuşmazlığı", meta.get("engine_mismatch", 0))]
    lines += table(["Ölçüt", "Adet"], rows) + [""]

    engines = sorted((meta.get("engine_detected") or {}).items(), key=lambda kv: (-kv[1], kv[0]))
    lines += ["### Motor dağılımı", ""]
    lines += table_or(["Motor", "Adet"], engines, "Veri yok.")
    lines.append("")

    bad = sorted((r for r in results if r.get("status") != "ok"),
                 key=lambda r: (str(r.get("status")), str(r.get("domain"))))
    lines += ["### Ok olmayan kaynaklar", ""]
    shown = bad[:HEALTH_ROWS]
    lines += table_or(["Alan adı", "Durum", "Neden", "HTTP", "Motor"],
                      [(r.get("domain"), r.get("status"), r.get("reason"), r.get("http"),
                        r.get("engine_detected")) for r in shown], "Tüm kaynaklar ok.")
    if len(bad) > HEALTH_ROWS:
        lines += ["", f"Toplam {len(bad)} kayıttan ilk {HEALTH_ROWS} tanesi gösteriliyor."]
    lines.append("")
    return lines


ADD_DECISIONS = {"scaffolded": "✅ scaffolded", "unsupported_engine": "⚠️ unsupported_engine",
                 "unreachable": "⛔ unreachable"}
FUNCTIONAL_TEXT = {True: "evet", False: "hayır", None: "yapılmadı"}


def add_section(_args=None):
    data = load_json(ANALYZE_PATH)
    lines = ["## Kaynak ekleme raporu", ""]
    if data is None:
        return lines + ["sonuç yok", ""]
    if not isinstance(data, dict):
        data = {"sonuç": data}
    verdict = data.get("verdict")
    lines += [f"**Karar:** {ADD_DECISIONS.get(verdict, verdict or '(bilinmiyor)')}", ""]

    match = data.get("upstream_match") or {}
    if data.get("exists_upstream"):
        lines += [f"> ⚠️ **Upstream'de zaten var**: {data.get('domain')} "
                  f"(mihon: {match.get('mihon_pkg') or '-'}, jar: {match.get('jar_parser') or '-'}). "
                  "Yeni kayıt yerine mevcut olanı kullanın.", ""]

    engine = data.get("engine")
    engine_text = f"{engine} ({data.get('engine_source') or '-'})" if engine else "-"
    lang = data.get("lang") or "belirsiz"
    ratio = data.get("turkish_ratio")
    upstream_text = ("var" if data.get("exists_upstream") else
                     "yok" if data.get("upstream_checked", True) else "kontrol edilemedi")
    functional = FUNCTIONAL_TEXT.get(data.get("functional"), "yapılmadı")
    if data.get("functional_reason"):
        functional += f" ({data['functional_reason']})"
    lines += ["### Site bilgileri", ""]
    lines += table(["Alan", "Değer"], [
        ("Adres", data.get("url")), ("Domain", data.get("domain")), ("Ad", data.get("name")),
        ("Başlık", data.get("title")), ("Durum", data.get("status")), ("Motor", engine_text),
        ("İşlevsel kontrol", functional), ("Dil", f"{lang} (Türkçe karakter oranı: {ratio})"),
        ("Upstream", upstream_text), ("Kayıt (sources/custom)", "evet" if data.get("registered") else "hayır"),
    ]) + [""]

    lines += ["### Üretilen dosyalar", ""]
    files = data.get("scaffold") or []
    lines += [f"- `{path}`" for path in files] or ["Dosya üretilmedi."]
    lines += ["", "### Sıradaki adımlar", ""]
    steps = data.get("next_steps") or []
    lines += [f"- {step}" for step in steps] or ["Adım yok."]
    lines.append("")

    lines += ["### Ham alanlar", ""]
    items = data.items()
    rows = [(k, json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else v)
            for k, v in items]
    return lines + table(["Alan", "Değer"], rows) + [""]


JAR_PREPARE_PATH = os.path.join(BASE_DIR, "data", "jar_prepare.json")
JAR_BUCKET_PATHS = {"turkce": ("turkce/jar", os.path.join("sources", "tr", "sources.json")),
                    "global": ("global/jar", os.path.join("sources", "global", "sources.json")),
                    "ozel": ("ozel/jar", os.path.join("sources", "tr", "sources.json"))}
JAR_ROWS = 150
JAR_ENV_SETTINGS = (("JAR_BUCKET", "Bölüm"), ("JAR_MODE", "Mod"), ("JAR_INCLUDE_BROKEN", "Bozuk kaynaklar dahil"),
                    ("JAR_APPLY_ALTERNATIVES", "Alternatif domain politikası"),
                    ("JAR_FORCE", "Zorunlu derleme"), ("JAR_PUBLISH", "Yayınla"))


def env_text(name):
    return os.environ.get(name, "").strip()


def jar_decision_text():
    build = env_text("JAR_BUILD")
    reason = env_text("JAR_REASON") or "neden yok"
    outcome = env_text("JAR_BUILD_OUTCOME")
    if outcome == "failure":
        return "⛔ Derleme başarısız"
    if build == "true":
        return f"✅ Derlendi ({reason})"
    if build == "false":
        return f"⏭️ Atlandı ({reason})"
    return "⛔ Karar verilemedi (hazırlık adımı çalışmadı)"


def jar_section(_args=None):
    bucket = env_text("JAR_BUCKET") or "turkce"
    out_rel, sources_rel = JAR_BUCKET_PATHS.get(bucket, JAR_BUCKET_PATHS["turkce"])
    prep = load_json(JAR_PREPARE_PATH)
    info = load_json(os.path.join(BASE_DIR, out_rel, "build_info.json"))
    sources = load_json(os.path.join(BASE_DIR, sources_rel))
    entries = (sources or {}).get("sources") or []
    lines = ["## Jar derleme raporu", "", "### Karar", "", jar_decision_text(), ""]

    if env_text("JAR_FALLBACK") == "1":
        lines += ["> ⚠️ **Yedek yol kullanıldı**: upstream derlemesi başarısız oldu; eklenti "
                  "yalnızca yamalarla, seçim ve silme uygulanmadan derlendi.", ""]

    lines += ["### Ayarlar", ""]
    lines += table(["Ayar", "Değer"], [(label, env_text(name) or "(ayarlı değil)")
                                      for name, label in JAR_ENV_SETTINGS])
    lines.append("")

    lines += ["### Upstream", ""]
    lines += table(["Alan", "Değer"], [("Commit", (prep or {}).get("upstream_commit") or "(bilinmiyor)")])
    lines.append("")

    lines += ["### Sayılar", ""]
    if prep is None:
        lines += ["data/jar_prepare.json yok.", ""]
    else:
        counts = prep.get("counts") or {}
        rows = [("Tutulan kimlik", counts.get("kept", 0)),
                ("Silinen kimlik", counts.get("removed_ids", 0)),
                ("Silinen dosya", counts.get("deleted_files", 0)),
                ("Kurtarılan dosya", counts.get("rescued_files", 0)),
                ("Domain yaması", counts.get("patched_domains", 0)),
                ("Domain yaması başarısız", counts.get("patch_failed", 0))]
        lines += table(["Ölçüt", "Adet"], rows) + [""]

        lines += ["### Domain yamaları", ""]
        lines += table_or(["Kimlik", "Eski domain", "Yeni domain", "Güven"],
                          [(p.get("id"), p.get("old"), p.get("new"), p.get("confidence"))
                           for p in prep.get("patched_domains") or []], "Domain yaması yok.")
        lines.append("")

    lines += ["### Jar", ""]
    if info is None:
        lines += [f"{out_rel}/build_info.json yok (derleme atlandı ya da henüz yok).", ""]
    else:
        lines += table(["Alan", "Değer"], [
            ("Boyut (bayt)", info.get("jarBytes")), ("sha256", info.get("jarSha256")),
            ("Derleme zamanı (UTC)", info.get("builtAt")), ("Çalıştırma no", info.get("runNumber")),
        ]) + [""]

    lines += ["### Tutulan kaynaklar", ""]
    if sources is None:
        lines += ["sources.json okunamadı.", ""]
    else:
        patched_new = {p.get("id"): p.get("new") for p in (prep or {}).get("patched_domains") or []}
        by_parser = {}
        for entry in entries:
            parser = ((entry.get("formats") or {}).get("jar") or {}).get("parser")
            if parser:
                by_parser.setdefault(parser, entry)
        kept = sorted((prep or {}).get("kept_ids") or [])
        rows = []
        for pid in kept[:JAR_ROWS]:
            entry = by_parser.get(pid, {})
            domain = patched_new.get(pid) or entry.get("domain")
            rows.append((pid, entry.get("name"), domain, entry.get("status")))
        lines += table_or(["Kimlik", "Ad", "Domain", "Durum"], rows, "Tutulan kaynak yok.")
        if len(kept) > JAR_ROWS:
            lines += ["", f"Toplam {len(kept)} kaynaktan ilk {JAR_ROWS} tanesi gösteriliyor."]
        lines.append("")

    slug = env_text("GITHUB_REPOSITORY") or "<GITHUB_REPOSITORY>"
    lines += ["### Kototoro'ya ekleme", "",
              "1. Ayarlar → İçerik Kaynakları → Eklentiler → JAR Depoları → Depo ekle yolunu izleyin.",
              f"2. Bölüm adresi: `https://raw.githubusercontent.com/{slug}/main/<bölüm>/jar` "
              "(bölüm: turkce, global veya ozel).",
              "3. Depo özel iken adres çalışmaz; depo herkese açık olduğunda çalışır.", ""]
    return lines


SECTIONS = {"sync": sync_section, "health": health_section, "add": add_section, "jar": jar_section}


def main(argv=None):
    parser = argparse.ArgumentParser(description="Markdown run raporu üretir.")
    parser.add_argument("mode", choices=sorted(SECTIONS))
    parser.add_argument("--prev-sources", default=None,
                        help="önceki sources.json yolu (varsayılan: git HEAD sürümü)")
    args = parser.parse_args(argv)

    text = "\n".join(SECTIONS[args.mode](args)).rstrip() + "\n\n"
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as fh:
            fh.write(text)
    sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
