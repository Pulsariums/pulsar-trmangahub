#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""07_maintain.py — Canlı test sonucundan OTOMATİK TAMİR & BAKım bacası.

Girdi: cihaz/test muhabberinin JSON'u —
    {"generated": ..., "sources": [{"name": "MIHON_<id>", "status": "fail",
      "steps": {...}, "messages": {...}}, ...]}
Bu format eski JAR hattından miras; MIHON_<id> adları APK kaynaklarının
runtime id'sidir. id -> kaynak çevirisi build'in ürettiği source_map.json'dan
(emit_source_map.py) yapılır — haritasız hiçbir id'ye dokunulmaz.

Sınıflandırma ve kararlar (Nyora'nın elle SourcePatches.kt bakımının otomatigi):
  DNS        UnknownHostException      -> aday domain keşfi + İÇERİK DOĞRULAMASI
  CERT       trust anchor              -> aynı; doğrulanamazsa karantina
  DRIFT      404 / List is empty       -> upstream @Broken ise karantina; değilse izleme
  CLOUDFLARE 5xx CF / cf_protected     -> dokunma (cihazda WebView aşar), raporla
  HARNESS    "Query must be at least 3"-> kaynak suçlu değil, raporla
  UNKNOWN    haritada yok              -> YABANCI/ESKİ kurulum şüphesi, ASLA onarmaya kalkma

İÇERİK DOĞRULAMASI (toplakehorizon/situsbet faciasının panzehiri): bir tamir
adayı ancak ve ancak manga izleri taşıyıp spam/park İZİ TAŞIMADIĞINDA pin'lenir.

Kalıcılık: kararlar patches asset'inin ÜZERİNE yazılmaz (06 her build'de
sıfırdan üretir); data/maintenance/overrides.json'a yazılır ve 06 merge eder.

Kullanım: 07_maintain.py <sonuc1.json|URL> [<sonuc2 ...>] [--map source_map.json]
                        [--dry-run] [--sweep]
  --sweep: testte hiç görünmeyen TR kaynaklarını da proaktif tarar (tam bakım).
Çıkış:   0 = değişiklik yok, 2 = overrides güncellendi (workflow rebuild tetikler)
"""

import concurrent.futures as cf
import json
import os
import re
import ssl
import sys
import time
import urllib.parse
import urllib.request

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(BASE, "data")
MAINT_DIR = os.path.join(DATA, "maintenance")
OVERRIDES = os.path.join(MAINT_DIR, "overrides.json")
REPORT_MD = os.path.join(MAINT_DIR, "report.md")
REPORT_JSON = os.path.join(MAINT_DIR, "report.json")
PATCHES = os.path.join(BASE, "extension", "src", "main", "assets", "patches.json")

UA = ("Mozilla/5.0 (Linux; Android 14; Pixel 7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Mobile Safari/537.36")
CTX = ssl._create_unverified_context()  # probe amaçlı; onaylamayı içerik yapar

# Spam/park tespiki GÖRÜNÜR METİN üzerinde yapılır; ham HTML'de "slot" JS
# değişkeniyle "var slot=document.createElement..." diye eşleşip TilkiScans'ı
# haksız karantinaya atmıştı (kullanıcının elle doğruladığı listeden çıktı).
SPAM_STRONG_RE = re.compile(
    r"sedoparking|domain (?:for sale|is parked)|buy this domain|"
    r"the domain .{0,40} is (?:for sale|parked)|topdomains|afternic|parkingcrew|"
    r"under construction|voodoo:?\s*this domain", re.I)
SPAM_WEAK_RE = re.compile(
    r"\b(bahis|slot|casino|poker|kumar|jackpot|rulet|crash game|aviator)\b|"
    r"para\s*(?:[çc]ekme|yat[ıi]r)", re.I)


def visible_text(body):
    b = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", body, flags=re.I | re.S)
    return re.sub(r"<[^>]+>", " ", b)


def is_spam_text(text):
    """Kuvvetli tek kanıt (park sayfası) YA DA en az İKİ FARKLI kumar sözcüğü.
    Tek zayıf eşleşme (manga konusu 'bahis' olabilir) karantina sebebi değildir."""
    if SPAM_STRONG_RE.search(text):
        return True
    weak = {m.group(0).lower() for m in SPAM_WEAK_RE.finditer(text)}
    return len(weak) >= 2
# Host bazlı kumar/park desisleri: "situsbet200resmi.org", "814292.toplakehorizon.com"
SPAM_HOST_RE = re.compile(
    r"bet\d|bet[a-z]*(?:resmi|official)|\d{4,}[a-z]|slot|casino|poker|kumar|rulet|jackpot|"
    r"toplake|horizon\d*\.[a-z]", re.I)


# İki seviyeli kamu TLD'leri: "asurascans.com.tr" apexe "com.tr" değil
# "asurascans.com.tr" olmalı — marka (sld) çıkarımı buna bağlı.
TWO_LEVEL = {"com.tr", "net.tr", "org.tr", "info.tr", "biz.tr", "gov.tr", "web.tr",
             "k12.tr", "av.tr", "dr.tr", "com.cn", "com.br", "co.uk", "org.uk",
             "co.jp", "co.kr", "com.au", "co.za", "com.mx", "com.tw", "com.hk"}


def apex(host):
    parts = re.sub(r"^www\.", "", host.lower()).split(".")
    if len(parts) >= 3 and ".".join(parts[-2:]) in TWO_LEVEL:
        return ".".join(parts[-3:])
    return ".".join(parts[-2:]) if len(parts) >= 2 else host
MANGA_RE = re.compile(
    r"manga|manhwa|webtoon|bölüm|chapter|series|roman|çeviri|scans|fansub|okut", re.I)
# SAF KEŞİF EŞİĞİ: MANGA_RE tek başına zayıftı — "series" kelimesi bir portfolyo
# sitesini bile geçirdi (zaman.app/nabi.me sahtelikleri). Gerçek okuma sitesinde
# manga/manhwa/webtoon sözcükleri EN AZ 2 kez geçer VE bölüm/kapak izi vardır.
_STRONG_M = re.compile(r"manga|manhwa|webtoon", re.I)
_STRONG_C = re.compile(r"b[öo]l[üu]m|chapter|episode|/manga/|/series/|/detail/|/chapter", re.I)
TITLE_RE = re.compile(r"<title[^>]*>(.{0,200}?)</title>", re.I | re.S)


def looks_like_manga_site(body):
    t = body[:80_000]
    return len(_STRONG_M.findall(t)) >= 2 and bool(_STRONG_C.search(t))


# Dil kanıtı: keşif adayı, hedef kaynakla AYNI dilin sitesini kanıtlamak zorunda.
# tr: TEK ÖZEL KARAKTER yetmez (yaoi.me faciası — Japonca romanize etiketlerde
# "ö" var diye geçti). Türkçe SİTE SÖZCÜKLERİ ya da lang="tr" attribute'ü ister.
_LANG_EV = {
    "tr": re.compile(
        r"b[öo]l[üu]m|t[üu]rk[çc]e|[çc]eviri|kategori|ana\s*sayfa|hepsini\s*g[öo]r|"
        r"okuma|s[ıi]ra\s*takip|güncel", re.I),
    "en": re.compile(r"\b(the|and|chapter|read|online)\b", re.I),
}

DRIFT_RE = re.compile(r"Status=404|NotFoundException|List is empty|No results", re.I)
DNS_RE = re.compile(r"UnknownHostException|Unable to resolve host", re.I)
CERT_RE = re.compile(r"SSLHandshakeException|Trust anchor|CertificateException|CertPathValidator", re.I)
CF_RE = re.compile(r"Status=52[12356]|Blocked by Cloudflare|cf_clearance|Just a moment", re.I)
HARNESS_RE = re.compile(r"Query must be at least 3 characters", re.I)
URL_RE = re.compile(r"https?://([^/?\s\"\\]+)")


def log(msg):
    print(f"[07] {msg}", flush=True)


def load_json(path_or_url, default=None):
    if re.match(r"^https?://", path_or_url):
        req = urllib.request.Request(path_or_url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode("utf-8", "replace"))
    with open(path_or_url, encoding="utf-8") as f:
        return json.load(f)


def fetch(url, timeout=12):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "tr"})
        with urllib.request.urlopen(req, timeout=timeout, context=CTX) as r:
            return r.status, r.geturl(), r.read(200_000).decode("utf-8", "replace")
    except Exception as e:  # noqa: BLE001 — sınıf adını sınıflandırmaya kullanıyoruz
        return 0, url, type(e).__name__ + ": " + str(e)[:200]


def validate_candidate(domain, brand=None, depth=0, must=None, lang=None):
    """Aday domain TAMİR edilebilir mi? -> (kabul, red-sebebi).

    brand: kaynak adındaki marka token'ları. Farklı apexe yönlendiren aday
    ancak MARKASINI TAŞIYORSA kabul edilir (asurascans.us -> mangapark.tv
    tuzağı: yönlendirme hedefi başka marka ise bu onarım DEĞİLDİR).
    must: KEŞİF adayları için ek şart — sitenin kendi HTML'inde marka izi
    (sld/token) geçmek zorunda; yoksa bu "aynı sözcük, başka site"dır.
    lang: KEŞİF adayı kaynakla AYNI dilin sitesi olmalı (yaoi.me faciası:
    İngilizce yaoi okuma sitesi, TR "YAOITR" fansub'unun marka kelimesini
    başlıkta taşıyor diye pin'lenmişti — DİL SAFİĞİ bunu da yasaklar)."""
    if not domain or SPAM_STRONG_RE.search(domain) or SPAM_HOST_RE.search(domain):
        return False, "spam-desi"
    if depth > 2:
        return False, "yonlendirme-zinciri"
    status, final_url, body = fetch(f"https://{domain}/")
    text = visible_text(body)
    fh = URL_RE.search(final_url)
    final_host = re.sub(r"^www\.", "", (fh.group(1) if fh else domain).lower())
    if status == 0:
        kind = body.split(":")[0]
        if "UnknownHost" in kind or kind == "socket failed":
            return False, "dns-yok"
        if "SSL" in kind or "Cert" in kind:
            return False, "sertifika-bozuk"
        return False, f"erişilemedi({kind})"
    if apex(final_host) != apex(re.sub(r"^www\.", "", domain.lower())):
        # aday cross-apex yönlendiriyor — hedef ayrı bir sitedir; marka eşecek
        if is_spam_text(text[:60_000]) or SPAM_HOST_RE.search(final_host):
            return False, "spam-yonlendirme"
        if brand and not any(t in final_host.replace(".", "").replace("-", "") for t in brand):
            return False, f"marka-farkli-yonlendirme({final_host})"
        return validate_candidate(final_host, brand, depth + 1, must, lang)
    if is_spam_text(text[:60_000]) or SPAM_HOST_RE.search(final_host):
        return False, "spam-icerik"
    if not MANGA_RE.search(body):
        return False, "manga-izi-yok"
    if must:
        # KEŞİF adayı ek kontroller: marka <title>/<h1>'de GEÇMELİ (gövdedeki
        # sıradan kelime yetmez — zaman.app faciası) ve site gerçek bir okuma
        # sitesi olmalı (manga sözcüğü x2 + bölüm/kapak izi).
        head = TITLE_RE.search(body)
        h1 = re.search(r"<h1[^>]*>(.{0,200}?)</h1>", body[:20_000], re.I | re.S)
        sig = ((h1.group(1) if h1 else "") + " " + (head.group(1) if head else "")).lower()
        if not any(m in sig for m in must):
            return False, "marka-başlıkta-yok"
        if not looks_like_manga_site(body):
            return False, "okuma-sitesi-degil"
        if lang and lang != "all":
            ev = _LANG_EV.get(lang)
            if ev and not ev.search(body[:80_000]) and f'lang="{lang}"' not in body[:40_000]:
                return False, f"dil-uyumsuz({lang})"
    if status >= 500:
        return False, f"5xx({status})"
    return True, "ok"


GENERIC_TOKENS = {"MANGA", "MANGAS", "MANHWA", "MANHUA", "WEBTOON", "WEBTOONS", "OKU", "OKUT",
                  "READ", "SCANS", "SCAN", "FANSUB", "TR", "ONLINE", "SITE", "SERIES", "CHAPTER"}


def tokens(name):
    core = re.sub(r"(TR|TR18|18|NSFW|SCANS?|MANGA|FANSUB|TOON|CIX)$", "", name.upper())
    toks = {t for t in re.split(r"[^A-Z0-9]+", core) if len(t) >= 4}
    specific = toks - GENERIC_TOKENS
    # SADECE genel kelimeler kaldıysa marka token'i yok sayılır: "MANGA" gibi
    # bir genel kelime başka markaya tamir pin'letir (WebtoonOku->mangadenizi tuzağı).
    return specific


def classify(messages):
    """source adım mesajlarından tek baskın sınıf."""
    txt = " | ".join((messages or {}).values())
    if HARNESS_RE.search(txt):
        return "HARNESS"
    if DNS_RE.search(txt):
        return "DNS"
    if CERT_RE.search(txt):
        return "CERT"
    if CF_RE.search(txt):
        return "CLOUDFLARE"
    if DRIFT_RE.search(txt):
        return "DRIFT"
    if "timeout" in txt.lower():
        return "TRANSIENT"
    return "OTHER"


# --- KEŞİF: ölü markanın YENİ domainini bul (karantina değil, gerçek tamir) ---
# TR fansub/scan sitelerinin klasik ölümü = domain taşımak. İz sürülecek yollar:
#   1) TLD rotasyonu: asurascans.com.tr öldüyse asurascans.{net,xyz,app,...} dene
#   2) DuckDuckGo html: "marka manga" aramasında çıkan domainler
#   3) Wayback: eski sitenin SON anlık görüntüsündeki "taşındık" izleri/yönlendirmeler
# Bulunan aday yine validate_candidate'tan geçmek zorunda (manga izi + marka + spam yok).
ROT_TLDS = ("com", "net", "org", "info", "xyz", "site", "online", "live", "app", "co",
            "me", "tv", "io", "gg", "cc", "club", "fun", "run", "to", "day", "world", "space")
# KESİN ölüm sebepleri: pin geri-alımı ve karantina YALNIZ bunlarda.
# ConnectionReset/timeout/5xx geçicidir — sağlam siteyi "ölü" diye yetim bırakmayız.
HARD_BADS = ("dns-yok", "sertifika-bozuk", "spam-icerik", "spam-yonlendirme", "spam-desi")


def discover_domains(cur, toks, smap, ov):
    """Ölü domain/marka için KEŞİF aday listesi (doğrulanmamış)."""
    known = {re.sub(r"^www\.", "", (r.get("domain") or "").lower())
             for r in smap["engine"] + smap["catalogue"] if r.get("domain")}
    dead = {h.lower() for h in ov.get("deadHosts", [])}
    sld = apex(cur).split(".")[0] if cur else ""
    slds = {sld.replace("-", "")} | {t.lower() for t in toks}
    slds = {s for s in slds if len(s) >= 4}
    out = []
    for s in sorted(slds)[:3]:
        for tld in ROT_TLDS:
            out.append(f"{s}.{tld}")
        # ayna/versiyon örüntüleri: 1sld, sld1, sld-official...
        for pat in (f"1{s}", f"{s}1", f"{s}tr", f"tr{s}"):
            out.append(f"{pat}.com")
    # wayback: son snapshot'taki yeni domain izleri
    if cur:
        try:
            req = urllib.request.Request(
                f"https://web.archive.org/cdx/search/cdx?url={cur}&output=text&limit=-25&from=2024&collapse=urlkey",
                headers={"User-Agent": UA}, )
            with urllib.request.urlopen(req, timeout=20) as r:
                for line in r.read().decode("utf-8", "replace").splitlines():
                    parts = line.split()
                    if len(parts) > 2:
                        for m in URL_RE.finditer(" ".join(parts[2:])):
                            h = re.sub(r"^www\.", "", m.group(1).lower())
                            if any(t in h.replace(".", "").replace("-", "") for t in {x.lower() for x in toks}):
                                out.append(h)
        except Exception:  # noqa: BLE001 — keşif en iyi çabadır
            pass
    # Wayback anlık görüntüsü: ölü sitenin son arşiv kopyasında "taşındık"
    # bağlantıları/JS yönlendirmeleri kalır — markayı taşıyan hostları çıkar.
    if cur:
        try:
            req = urllib.request.Request(f"https://web.archive.org/web/2026id_/https://{cur}/",
                                         headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=25) as r:
                snap = r.read(200_000).decode("utf-8", "replace")
            tl = {t.lower() for t in toks} | {apex(cur).split(".")[0]}
            for mm in URL_RE.finditer(snap):
                h = re.sub(r"^www\.", "", mm.group(1).lower())
                if h == cur or "archive.org" in h:
                    continue
                hh = h.replace(".", "").replace("-", "")
                if any(t and len(t) >= 4 and t in hh for t in tl):
                    out.insert(0, h)
        except Exception:  # noqa: BLE001 — keşif en iyi çabadır
            pass
    cand = []
    for d in out:
        if d != cur and d not in known and d not in dead and d not in cand:
            cand.append(d)
    return cand[:40]


def ddg_domains(query):
    """DuckDuckGo html arama — en iyi çaba; CI IP'sinde bloklanabilir, sessiz geç."""
    urls = []
    try:
        req = urllib.request.Request(
            "https://html.duckduckgo.com/html/?q=" + urllib.parse.quote(query),
            headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=12) as r:
            html = r.read().decode("utf-8", "replace")
        for m in re.finditer(r'href="([^"]+)"', html):
            href = m.group(1)
            km = re.search(r"uddg=([^&\"]+)", href)
            u = urllib.parse.unquote(km.group(1)) if km else href
            hm = URL_RE.search(u if "://" in u else "http://" + u)
            if hm:
                h = re.sub(r"^www\.", "", hm.group(1).lower())
                if h not in urls and "duckduckgo" not in h:
                    urls.append(h)
    except Exception:  # noqa: BLE001
        pass
    return urls[:12]


def domains_in(messages):
    out = set()
    for v in (messages or {}).values():
        for m in URL_RE.finditer(str(v)):
            h = re.sub(r"^www\.", "", m.group(1).lower())
            out.add(h)
    return out


def main():
    dry = "--dry-run" in sys.argv
    sweep = "--sweep" in sys.argv
    map_path = None
    if "--map" in sys.argv:
        map_path = sys.argv[sys.argv.index("--map") + 1]
    args = [a for a in sys.argv[1:] if not a.startswith("--")
            and a != (map_path or "\0")]
    if not map_path:
        map_path = os.path.join(BASE, ".work", "source_map.json")

    results_docs = []
    for rp in args:
        doc = load_json(rp)
        results_docs.extend(doc.get("sources", []) if isinstance(doc, dict) else doc)
    smap = load_json(map_path)
    patches = load_json(PATCHES, {}) if os.path.exists(PATCHES) else {}

    idx = {}
    by_name = {}
    for r in smap["engine"] + smap["catalogue"]:
        idx[int(r["id"])] = r
        by_name.setdefault(r["name"], []).append(r)

    os.makedirs(MAINT_DIR, exist_ok=True)
    ov = load_json(OVERRIDES, None) if os.path.exists(OVERRIDES) else None
    ov = ov or {"domainOverrides": {}, "deadSources": [], "deadHosts": [], "unpinned": []}
    for k in ("domainOverrides", "deadSources", "deadHosts", "unpinned",
              "revivedSources", "revivedHosts"):
        ov.setdefault(k, ov.get(k) or ([] if k != "domainOverrides" else {}))
    before = json.dumps(ov, sort_keys=True)

    entries = results_docs
    rows, pinned_names = [], set()

    def quarantine(src, dom):
        if src["kind"] == "engine":
            if src["name"] not in ov["deadSources"]:
                ov["deadSources"].append(src["name"])
            # katalog tarafı da aynı hostu taşıyorsa onu da sustur
        host = re.sub(r"^www\.", "", (dom or src.get("domain") or "").lower())
        if host and host not in ov["deadHosts"]:
            ov["deadHosts"].append(host)

    # 1) MEVCUT pin'leri yeniden doğrula — eski liveness verisinin bayat/ıskartaya
    #    çıkmış OTOMATIK_TAMIR hedefleri (spam faciası) ancak böyle temizlenir.
    def revalidate_pin(item):
        key, target = item
        ok, why = validate_candidate(target)
        return key, target, ok, why

    all_pins = dict(patches.get("domainOverrides") or {})
    all_pins.update(ov.get("domainOverrides") or {})
    log(f"mevcut {len(all_pins)} pin yeniden doğrulanıyor...")
    with cf.ThreadPoolExecutor(8) as pool:
        for key, target, ok, why in pool.map(revalidate_pin, list(all_pins.items())):
            hard = why in HARD_BADS or str(why).startswith("marka-farkli")
            if not ok and hard:
                if key not in ov["unpinned"]:
                    ov["unpinned"].append(key)
                    ov["domainOverrides"].pop(key, None)
                    all_pins[key] = None
                    rows.append({"id": "-", "kind": "pin", "name": f"{key}->{target}",
                                 "class": "BAYAT_PIN", "action": "pin-geri-alindi", "detail": why})
            elif not ok:
                rows.append({"id": "-", "kind": "pin", "name": f"{key}->{target}",
                             "class": "PIN", "action": "gecici-erişim-hata", "detail": f"{why} — pin korundu, sonraki bakımda yeniden denenir"})
            else:
                rows.append({"id": "-", "kind": "pin", "name": f"{key}->{target}",
                             "class": "PIN", "action": "dogrulandi", "detail": why})

    # 2) Test sonuçlarını işle — İKİ format da desteklenir:
    #    a) Cihaz muhabberi: {"name":"MIHON_<id>","status","steps","messages"}
    #    b) CI LiveCheck.kt : {"id":NAME,"name":title,"ok","stage","error_class","error","domain"}
    CLASS_MAP = {"dns": "DNS", "ssl": "CERT", "timeout": "TRANSIENT", "cloudflare": "CLOUDFLARE",
                 "rate_limit": "CLOUDFLARE", "http_blocked": "CLOUDFLARE", "http_gone": "DRIFT",
                 "http_5xx": "TRANSIENT", "http": "DRIFT", "parse": "DRIFT", "empty": "DRIFT",
                 "connect": "DNS", "decode": "HARNESS"}
    log(f"{len(entries)} kaynak sonucu işleniyor...")
    tasks = []
    for e in entries:
        sid = None
        if "status" in e or "steps" in e or "messages" in e:      # cihaz formatı
            if e.get("status") == "pass":
                continue
            m = re.search(r"MIHON_(\d+)", str(e.get("name", "")))
            if not m:
                continue
            sid = int(m.group(1))
            src = idx.get(sid)
            klass = classify(e.get("messages"))
            doms = domains_in(e.get("messages"))
        else:                                                      # LiveCheck formatı
            if e.get("ok"):
                continue
            srcname = str(e.get("id", ""))
            cand = by_name.get(srcname)
            if not cand:
                rows.append({"id": srcname, "kind": "?", "name": srcname,
                             "class": CLASS_MAP.get(e.get("error_class", ""), "OTHER"),
                             "action": "BILINMIYOR", "detail": "source_map'te yok"})
                continue
            src = cand[0]
            sid = src["id"]
            klass = CLASS_MAP.get(e.get("error_class", ""), classify({"m": str(e.get("error", ""))}))
            doms = domains_in({"m": str(e.get("error", ""))})
        if src is None:
            rows.append({"id": sid, "kind": "?", "name": e.get("name", ""),
                         "class": klass, "action": "BILINMIYOR",
                         "detail": "source_map'te yok — yabancı eklenti/eski kurulum; dokunulmadı"})
            continue
        cur = (e.get("domain") or src.get("domain") or (next(iter(doms)) if doms else "")).lower()
        tasks.append((sid, src, klass, doms, cur))

    def last_resort_repair(src, cur, toks):
        """KEŞİF: markanın yeni domainini bul (TLD rotasyonu + DDG + Wayback).
        Başarsa repair, bulamazsa None — karantina ancak ondan sonra gelir.
        KEŞİF adayları ekstra şartla geçer: HTML'de MARKA İZİ (sld/token)."""
        name = src["name"]
        sld = apex(cur).split(".")[0] if cur else ""
        must = {t.lower() for t in toks} | {sld.replace("-", "")}
        must = {m for m in must if len(m) >= 4}
        cands = discover_domains(cur, toks, smap, ov)
        if toks:
            q = " ".join(sorted(t.lower() for t in toks)) + " manga oku"
            brand_l = {t.lower() for t in toks}
            for d in ddg_domains(q):
                if any(t in d.replace(".", "").replace("-", "") for t in brand_l):
                    cands.insert(0, d)
        for cand in cands[:24]:
            if cand == cur:
                continue
            cok, cwhy = validate_candidate(cand, toks, must=must, lang=src.get("lang"))
            if cok:
                return f"repair->{cand}", f"KEŞİF tamiri: yeni domain bulundu ({cwhy})"
        return None

    def other_share(toks, o):
        return bool(toks & tokens(o["name"])) or any(t in o["domain"] for t in toks)

    def work(t):
        sid, src, klass, doms, cur = t
        name, kind = src["name"], src["kind"]
        if klass == "SWEEP":
            # Proaktif tarama: testte hiç görünmeyen kaynak da sorgulanır.
            # Yalnız KESİN ölümler (DNS/sertifika/spam) karantinaya gider;
            # 403/5xx/JS-duvarları CI IP'si yanıltması olabilir -> watch.
            toks = tokens(name)
            ok, why = validate_candidate(cur, toks) if cur else (False, "domain-yok")
            if ok and src.get("broken"):
                return t, "quarantine", f"{cur} canlı görünüyor AMA upstream @Broken"
            if ok:
                return t, "ok", "sweep: sağlam"
            if why.startswith("marka-farkli-yonlendirme"):
                return t, "quarantine", f"{cur} {why}"
            if why not in HARD_BADS and not src.get("broken"):
                return t, "watch", f"sweep: {why} (kesin ölüm değil, izlenir)"
            toks_ = toks
            cands = [o["domain"] for o in smap["engine"] + smap["catalogue"]
                     if o is not src and o.get("domain") and o.get("lang") == src.get("lang")
                     and o.get("nsfw") == src.get("nsfw") and other_share(toks_, o)
                     and o["domain"] != cur][:4]
            for cand in cands:
                cok, cwhy = validate_candidate(cand, toks_)
                if cok:
                    return t, f"repair->{cand}", f"sweep tamiri: aday doğrulandı ({cwhy})"
            r = last_resort_repair(src, cur, toks_)
            if r:
                return t, r[0], "sweep " + r[1]
            return t, "quarantine", f"sweep: {cur} ölü ({why}); {len(cands)} aday doğrulanamadı"
        if klass == "HARNESS":
            return t, "report-only", "muhabber 3 harften kısa sorgu atıyor; kaynak sağlam (LIST/DETAILS/CHAPTERS pass)"
        if klass in ("CLOUDFLARE", "TRANSIENT"):
            return t, "watch", "CF/geçici hata — karantina edilmez, bir sonraki bakımda izlenir"
        if klass == "DRIFT" and src.get("broken"):
            return t, "quarantine", "upstream @Broken + liste boş/404 — parser kendisi bozuk"
        if klass in ("DNS", "CERT", "DRIFT", "OTHER"):
            toks = tokens(name)
            # önce mevcut domain CANLI mı? çapraz-apex/marka kontrolü ile
            ok, why = validate_candidate(cur, toks) if cur else (False, "domain-bilinmiyor")
            if ok:
                return t, "ok", f"site şu an canlı görünüyor ({why}) — test hatası/karantina kalkar"
            # KEŞİF: aynı markanın AYNI DİLDEKİ kardeş domainleri — multi/global
            # bir domain'i TR enum'una pin'lemek "multi Türkçe değildir" kuralını
            # ihlal eder; NSFW kardeşleri de birbirine giremez.
            cands = []
            for other in smap["engine"] + smap["catalogue"]:
                if other is src or not other.get("domain"):
                    continue
                if other.get("lang") != src.get("lang") or other.get("nsfw") != src.get("nsfw"):
                    continue
                if toks & tokens(other["name"]) and other["domain"] != cur:
                    cands.append(other["domain"])
            cands = cands[:6]
            for cand in cands:
                cok, cwhy = validate_candidate(cand, toks)
                if cok:
                    return t, f"repair->{cand}", f"aday doğrulandı ({cwhy})"
            return t, "quarantine", f"{cur} ölü/{why}; {len(cands)} aynı-dil aday doğrulanamadı"
        return t, "watch", klass

    with cf.ThreadPoolExecutor(10) as pool:
        results = list(pool.map(work, tasks))

        if sweep:
            done = {t[0] for t in tasks}
            stasks = [(s["id"], s, "SWEEP", {s.get("domain") or ""}, (s.get("domain") or "").lower())
                      for s in smap["engine"] + smap["catalogue"]
                      if s["id"] not in done and s.get("domain") and s.get("lang") == "tr"]
            log(f"sweep: {len(stasks)} TR kaynağı proaktif taranıyor...")
            results += list(pool.map(work, stasks))

    for (sid, src, klass, doms, cur), action, detail in results:
        name, kind = src["name"], src["kind"]
        if action == "ok":
            # KENDİNİ İYİLEŞTİRME: domain bugün CANLI doğrulandıysa eski
            # karantina kararı yanlıştı (TilkiScans vakası) — geri al.
            host = re.sub(r"^www\.", "", (cur or src.get("domain") or "").lower())
            if kind == "engine" and name in ov["deadSources"]:
                ov["deadSources"].remove(name)
                if name not in ov["revivedSources"]:
                    ov["revivedSources"].append(name)
                rows.append({"id": sid, "kind": kind, "name": name, "title": src.get("title", ""),
                             "lang": src["lang"], "nsfw": src["nsfw"], "class": klass,
                             "action": "karantina-kalktı", "detail": detail})
            if host and host in ov["deadHosts"]:
                ov["deadHosts"].remove(host)
                if host not in ov["revivedHosts"]:
                    ov["revivedHosts"].append(host)
                rows.append({"id": sid, "kind": "host", "name": host, "class": klass,
                             "action": "host-açıldı", "detail": detail})
            continue
        if action.startswith("repair->"):
            cand = action.split("->", 1)[1]
            # motor enum adı ve ölü host'un ikisi de anahtar olarak pin'lenir:
            # PulsarContext ConfigKey.Domain -> DOMAIN_OVERRIDES[name], katalog
            # baseUrl/host yolu -> DOMAIN_OVERRIDES[eski domain].
            ov["domainOverrides"][name] = cand
            if cur:
                ov["domainOverrides"][cur] = cand
            if name in ov["deadSources"]:
                ov["deadSources"].remove(name)
                if name not in ov["revivedSources"]:
                    ov["revivedSources"].append(name)
            pinned_names.add(name)
        elif action == "quarantine":
            quarantine(src, cur)
        rows.append({"id": sid, "kind": kind, "name": name, "title": src.get("title", ""),
                     "lang": src["lang"], "nsfw": src["nsfw"], "class": klass,
                     "action": action, "detail": detail, "domain": cur})

    ov["deadSources"] = sorted(set(ov["deadSources"]))
    ov["deadHosts"] = sorted(set(ov["deadHosts"]))
    ov["revivedSources"] = sorted(set(ov["revivedSources"]))
    ov["revivedHosts"] = sorted(set(ov["revivedHosts"]))
    ov["updated"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    KEYS = ("domainOverrides", "deadSources", "deadHosts", "unpinned",
            "revivedSources", "revivedHosts")
    changed = json.dumps({k: ov[k] for k in KEYS},
                         sort_keys=True) != json.dumps({k: json.loads(before)[k]
                        for k in KEYS}, sort_keys=True)

    # rapor
    summary = {}
    for r in rows:
        a = "repair" if str(r["action"]).startswith("repair") else r["action"]
        summary[a] = summary.get(a, 0) + 1
    if not dry:
        with open(OVERRIDES, "w", encoding="utf-8") as f:
            json.dump(ov, f, ensure_ascii=False, indent=1)
        with open(REPORT_JSON, "w", encoding="utf-8") as f:
            json.dump({"generated": ov["updated"], "summary": summary, "rows": rows}, f,
                      ensure_ascii=False, indent=1)
        lines = ["# Pulsar otomatik bakım raporu", "",
                 f"- Üretim: {ov['updated']}  |  kaynak sonucu: {len(entries)}",
                 f"- Özet: " + ", ".join(f"{k}:{v}" for k, v in sorted(summary.items())), "",
                 "| Kaynak | Sınıf | Karar | Detay |", "|---|---|---|---|"]
        for r in rows:
            if r["kind"] == "pin":
                continue
            lines.append(f"| {r.get('title') or r['name']} ({r['id']}) | {r['class']} "
                         f"| {r['action']} | {r['detail'][:90]} |")
        with open(REPORT_MD, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")

    log(f"özet: {summary}")
    log(f"overrides: +{len(ov['domainOverrides'])} pin, {len(ov['deadSources'])} ölü enum, "
        f"{len(ov['deadHosts'])} ölü host, {len(ov['unpinned'])} geri-alınmış bayat pin")
    if dry:
        log("DRY-RUN — dosya yazılmadı")
        sys.exit(0)
    sys.exit(2 if changed else 0)


if __name__ == "__main__":
    main()
