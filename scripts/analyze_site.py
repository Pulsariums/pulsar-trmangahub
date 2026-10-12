#!/usr/bin/env python3
"""Site linkinden kaynak iskeleti üretir: python scripts/analyze_site.py --url <adres>.

Akış: adres -> domain; probe.py ile durum, motor tespiti ve işlevsel kontrol; ana sayfadan
dil ve başlık; data/upstream_tr.json ile upstream'de var mı. Motor madara, mangathemesia
veya initmanga ise scripts/templates/ şablonlarından generated/<domain>/ altına iskelet
yazılır. Derleme (APK/jar) bu script'in işi değildir.

Çıktı: data/analyze_result.json. Sonuç verdict'i:
  scaffolded          motor tanındı, iskelet üretildi
  unsupported_engine  motor tanınmadı veya custom; iskelet üretilmez
  unreachable         site yanıt vermedi (dead, parked, blocked, other)
--register 1 ise scaffolded ve unsupported_engine kayıtları sources/custom/sources.json'a yazılır.
"""

import argparse
import html
import json
import os
import re
import sys
import unicodedata
from datetime import datetime, timezone

import requests

import probe
import sync

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
UPSTREAM_PATH = os.path.join(DATA_DIR, "upstream_tr.json")
RESULT_PATH = os.path.join(DATA_DIR, "analyze_result.json")
GENERATED_DIR = os.path.join(BASE_DIR, "generated")
CUSTOM_PATH = os.path.join(BASE_DIR, "sources", "custom", "sources.json")
TEMPLATE_DIR = os.path.join(BASE_DIR, "scripts", "templates")

ENGINE_CHOICES = ("auto", "madara", "mangathemesia", "initmanga", "custom")
FORMAT_CHOICES = ("both", "jar", "mihon")
SCAFFOLD_ENGINES = ("madara", "mangathemesia", "initmanga")
MIHON_TEMPLATE_DIRS = {"madara": "mihon_madara", "mangathemesia": "mihon_mangathemesia",
                       "initmanga": "mihon_initmanga"}
JAR_TEMPLATES = {"madara": "jar_madara.kt", "mangathemesia": "jar_mangareader.kt"}
REACHABLE_STATUSES = ("ok", "cf_protected")
TR_LETTERS = frozenset("ğüşıöçĞÜŞİÖÇ")
TR_RATIO_MIN = 0.01
PLACEHOLDER_RE = re.compile(r"\{\{[A-Z_]+\}\}")


def domain_from_url(raw):
    """Return the normalized host (lowercase, no www.). Raises ValueError for unusable input."""
    text = (raw or "").strip()
    if not text:
        raise ValueError("url boş")
    if "://" not in text:
        text = "https://" + text
    if not text.lower().startswith(("http://", "https://")):
        raise ValueError(f"desteklenmeyen adres: {raw}")
    domain = probe.host_of(text)
    if not domain or "." not in domain:
        raise ValueError(f"geçersiz alan adı: {raw}")
    return domain


def kt_string(value):
    """Make a value safe inside a Kotlin or Gradle string literal."""
    return re.sub(r'["\\$]', "", value or "")


def class_name(name, domain):
    """PascalCase ASCII class name; Turkish letters are folded first."""
    text = (name or "").strip() or domain.split(".")[0]
    folded = unicodedata.normalize("NFKD", text.translate(sync.TR_CHARS))
    cls = "".join(w[:1].upper() + w[1:] for w in re.findall(r"[A-Za-z0-9]+", folded))
    if not cls:
        cls = "Source"
    if cls[0].isdigit():
        cls = "S" + cls
    return cls


def page_facts(text):
    """Return lang, lang_source, title and turkish_ratio from a homepage body."""
    lang_m = re.search(r"<html[^>]*\blang\s*=\s*[\"']?([A-Za-z-]+)", text, re.IGNORECASE)
    html_lang = lang_m.group(1).lower().split("-")[0] if lang_m else None
    title_m = re.search(r"<title[^>]*>(.*?)</title>", text, re.IGNORECASE | re.DOTALL)
    title = " ".join(html.unescape(title_m.group(1)).split())[:200] if title_m else None
    visible = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", text)
    visible = re.sub(r"(?s)<[^>]+>", " ", html.unescape(visible))
    letters = [ch for ch in visible if ch.isalpha()]
    tr_count = sum(1 for ch in letters if ch in TR_LETTERS)
    ratio = round(tr_count / len(letters), 4) if letters else 0.0
    if html_lang:
        lang, source = html_lang, "html"
    elif ratio >= TR_RATIO_MIN:
        lang, source = "tr", "text"
    else:
        lang, source = None, None
    return {"lang": lang, "lang_source": source, "title": title, "turkish_ratio": ratio}


def upstream_match(domain, upstream):
    """Return the upstream record for this domain (or an altDomain), or None."""
    for src in (upstream or {}).get("sources", []):
        if domain not in [src.get("domain")] + list(src.get("altDomains") or []):
            continue
        formats = src.get("formats") or {}
        return {"key": src.get("key"), "name": src.get("name"),
                "upstreams": src.get("upstreams") or [],
                "mihon_pkg": (formats.get("mihon") or {}).get("pkg"),
                "jar_parser": (formats.get("jar") or {}).get("parser")}
    return None


def probe_site(domain):
    """probe.probe_one: status, detected engine and functional check. Returns the probe record."""
    return probe.probe_one(domain)


def forced_functional(domain, engine):
    """Functional check for an engine the user forced (probe.check_functional)."""
    with requests.Session() as session:
        session.headers.update(probe.HEADERS)
        return probe.check_functional(session, domain, engine)


def fetch_home(domain):
    """Homepage fetch for lang and title. Returns probe.fetch_once's dict."""
    with requests.Session() as session:
        session.headers.update(probe.HEADERS)
        return probe.fetch_once(session, f"https://{domain}/")


def resolve_engine(rec, forced, domain, functional_fn):
    """Return (engine, engine_source, functional, functional_reason) for a probe record."""
    if forced != "auto":
        functional, reason = rec.get("functional"), rec.get("functional_reason")
        if rec.get("status") == "ok" and forced in SCAFFOLD_ENGINES:
            functional, reason = functional_fn(domain, forced)
        return forced, "forced", functional, reason
    engine = rec.get("engine_detected") or "unknown"
    source = rec.get("engine_source") if engine != "unknown" else None
    return engine, source, rec.get("functional"), rec.get("functional_reason")


def decide(status, engine):
    if status not in REACHABLE_STATUSES:
        return "unreachable"
    if engine in SCAFFOLD_ENGINES:
        return "scaffolded"
    return "unsupported_engine"


def render(text, values):
    for key, value in values.items():
        text = text.replace("{{%s}}" % key, value)
    leftover = PLACEHOLDER_RE.findall(text)
    if leftover:
        raise ValueError(f"şablonda doldurulmayan yer tutucu: {leftover}")
    return text


def write_text(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


def scaffold(domain, name, cls, pkg, engine, fmt):
    """Write template files under generated/<domain>/. Returns the relative paths written."""
    values = {"NAME": kt_string(name), "CLASS": cls, "PKG": pkg, "DOMAIN": domain,
              "BASEURL": f"https://{domain}", "LANG": "tr", "ID": cls.upper(),
              "TITLE": kt_string(name)}
    out_root = os.path.join(GENERATED_DIR, domain)
    written = []

    if fmt in ("mihon", "both"):
        tdir = os.path.join(TEMPLATE_DIR, MIHON_TEMPLATE_DIRS[engine])
        with open(os.path.join(tdir, "build.gradle.kts"), encoding="utf-8") as fh:
            gradle = render(fh.read(), values)
        with open(os.path.join(tdir, "source.kt"), encoding="utf-8") as fh:
            source = render(fh.read(), values)
        for rel, text in (("mihon/build.gradle.kts", gradle),
                          (f"mihon/src/eu/kanade/tachiyomi/extension/tr/{pkg}/{cls}.kt", source)):
            write_text(os.path.join(out_root, rel), text)
            written.append(f"generated/{domain}/{rel}")

    if fmt in ("jar", "both") and engine in JAR_TEMPLATES:
        with open(os.path.join(TEMPLATE_DIR, JAR_TEMPLATES[engine]), encoding="utf-8") as fh:
            jar = render(fh.read(), values)
        write_text(os.path.join(out_root, "jar", f"{cls}.kt"), jar)
        written.append(f"generated/{domain}/jar/{cls}.kt")
    return written


def next_steps_for(result, fmt):
    steps = []
    verdict, engine = result["verdict"], result["engine"]
    if verdict == "scaffolded":
        steps.append(f"generated/{result['domain']}/ altındaki dosyaları inceleyin; "
                     "derleme bu aşamada yapılmadı (ikon res/ ve APK/jar derlemesi eksik).")
        if fmt in ("jar", "both"):
            if engine not in JAR_TEMPLATES:
                steps.append(f"'{engine}' için jar şablonu yok; jar iskeleti üretilmedi.")
        if result["functional"] is False:
            steps.append(f"İşlevsel kontrol başarısız ({result['functional_reason']}); "
                         "liste sayfası elle doğrulanmalı.")
        if result["engine_source"] == "forced" and result["engine_detected"] not in (None, "unknown") \
                and result["engine_detected"] != engine:
            steps.append(f"Tespit edilen motor '{result['engine_detected']}', zorlanan '{engine}'.")
    elif verdict == "unsupported_engine":
        steps.append(f"Motor tanınmadı (motor: {engine}); özel Kotlin kodu gerekir. "
                     "İskelet üretilmedi.")
    else:
        steps.append(f"Site yanıt vermedi (durum: {result['status']}, neden: {result['reason']}).")
        if result["status"] == "blocked":
            steps.append("Proxy politikası engelledi; sonucu Actions üzerinde tekrar deneyin.")
        elif result["status"] in ("dead", "parked"):
            steps.append("Adresi kontrol edin; site kapalı veya satılık olabilir.")
    if result["lang"] and result["lang"] != "tr":
        steps.append(f"Sayfa Türkçe görünmüyor (lang={result['lang']}); kaynak kapsamını kontrol edin.")
    if result["exists_upstream"]:
        match = result["upstream_match"]
        steps.append(f"Upstream'de zaten var ({', '.join(match['upstreams'])}; "
                     f"mihon={match['mihon_pkg'] or '-'}, jar={match['jar_parser'] or '-'}); "
                     "yeni kayıt yerine mevcut olanı kullanın.")
    if not result["upstream_checked"]:
        steps.append("data/upstream_tr.json yok; upstream karşılaştırması yapılmadı.")
    return steps


def analyze(domain, name="", engine="auto", fmt="both", register=0, *, probe_fn=None,
            fetch_fn=None, functional_fn=None, upstream=None, now=None):
    """Run the whole analysis for one domain. Returns the result dict (no files written
    except scaffold and the custom registry when register is 1)."""
    probe_fn = probe_fn or probe_site
    fetch_fn = fetch_fn or fetch_home
    functional_fn = functional_fn or forced_functional
    now = now or datetime.now(timezone.utc).isoformat(timespec="seconds")
    if upstream is None:
        upstream = _load_upstream()
    upstream_checked = upstream is not None

    forced = engine
    rec = probe_fn(domain)
    resolved, source, functional, reason = resolve_engine(rec, forced, domain, functional_fn)
    if forced == "custom":
        functional, reason = None, "custom engine; functional check skipped"

    facts = {"lang": None, "lang_source": None, "title": None, "turkish_ratio": 0.0}
    if rec.get("status") in REACHABLE_STATUSES:
        raw = fetch_fn(domain)
        if "error_kind" not in raw:
            facts = page_facts(raw["text"])

    verdict = decide(rec.get("status"), resolved)
    name = (name or "").strip() or domain.split(".")[0]
    cls = class_name(name, domain)
    pkg = sync.make_key(name, domain)
    if not pkg or pkg[0].isdigit():
        pkg = "s" + pkg

    match = upstream_match(domain, upstream)
    result = {
        "url": f"https://{domain}",
        "domain": domain,
        "name": name,
        "class": cls,
        "format": fmt,
        "status": rec.get("status"),
        "reason": rec.get("reason"),
        "engine": resolved,
        "engine_source": source,
        "engine_detected": rec.get("engine_detected"),
        "functional": functional,
        "functional_reason": reason,
        "lang": facts["lang"],
        "lang_source": facts["lang_source"],
        "turkish_ratio": facts["turkish_ratio"],
        "title": facts["title"],
        "exists_upstream": match is not None,
        "upstream_match": match,
        "upstream_checked": upstream_checked,
        "scaffold": [],
        "verdict": verdict,
        "registered": False,
        "analyzed_at": now,
    }
    if verdict == "scaffolded":
        result["scaffold"] = scaffold(domain, name, cls, pkg, resolved, fmt)
    result["next_steps"] = next_steps_for(result, fmt)
    if register and verdict in ("scaffolded", "unsupported_engine"):
        register_custom(result, now)
        result["registered"] = True
    return result


def _load_upstream():
    try:
        with open(UPSTREAM_PATH, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def register_custom(result, now):
    """Upsert the entry into sources/custom/sources.json (a JSON list keyed by id = domain)."""
    entries = []
    if os.path.exists(CUSTOM_PATH):
        with open(CUSTOM_PATH, encoding="utf-8") as fh:
            loaded = json.load(fh)
        entries = loaded if isinstance(loaded, list) else (loaded.get("sources") or [])
    prev = next((e for e in entries if e.get("id") == result["domain"]), None)
    entry = {
        "id": result["domain"],
        "name": result["name"],
        "domain": result["domain"],
        "baseUrl": result["url"],
        "engine": result["engine"],
        "scope": "tr_native",
        "verdict": result["verdict"],
        "scaffold": result["scaffold"],
        "addedAt": (prev or {}).get("addedAt") or now,
    }
    entries = [e for e in entries if e.get("id") != result["domain"]] + [entry]
    entries.sort(key=lambda e: e["id"])
    sync.write_json(CUSTOM_PATH, entries)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Site linkinden kaynak iskeleti üretir.")
    parser.add_argument("--url", required=True, help="manga sitesinin adresi")
    parser.add_argument("--name", default="", help="kaynak adı (boşsa domainden)")
    parser.add_argument("--engine", choices=ENGINE_CHOICES, default="auto")
    parser.add_argument("--format", choices=FORMAT_CHOICES, default="both")
    parser.add_argument("--register", type=int, choices=(0, 1), default=0)
    args = parser.parse_args(argv)

    try:
        domain = domain_from_url(args.url)
    except ValueError as exc:
        print(f"HATA: {exc}", file=sys.stderr)
        return 1

    result = analyze(domain, name=args.name, engine=args.engine, fmt=args.format,
                     register=args.register)
    sync.write_json(RESULT_PATH, result)

    print(f"Output: {RESULT_PATH}")
    print(f"  domain={result['domain']} status={result['status']} engine={result['engine']} "
          f"({result['engine_source']}) functional={result['functional']}")
    print(f"  lang={result['lang']} turkish_ratio={result['turkish_ratio']} exists_upstream={result['exists_upstream']}")
    print(f"  verdict={result['verdict']} scaffold={len(result['scaffold'])} registered={result['registered']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
