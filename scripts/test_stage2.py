#!/usr/bin/env python3
"""Asama 2 - gercek yolculuk testi: liste -> detay -> BIR BOLUME GIR -> o bolumde gercek sayfa
(gorsel) cekebiliyor muyuz. Stage1 "pass" bile olsa bu testten gecmek gerekir: liste sayfasinda
motor markeri bulunmasi, bolum/okuyucu kodunun calistigi anlamina gelmez (ragnarscans.net ornegi:
liste markeri var ama CHAPTER_ITEM selector'u JS-render DOM'dan alinmis, statik HTML'de 0 esanisir).

Bu test parser kodundan BAGIMSIZ, site HTML'ine dayali bir "gercek kullanici yolculugu" simulasyonu:
  1) liste sayfasi -> ilk seri linki
  2) seri detay sayfasi -> "bolum/chapter" iceren bir link (ilk bolum)
  3) bolum sayfasi -> en az 1 "gercek" img (genis/data-src/vb, placeholder/svg/logo degil)
Ayrica VARSA generated/ .kt dosyasindaki CHAPTER_ITEM / READER_IMAGES selector'lerini de statik
HTML'e karsi test eder (0 esanisir -> selector kirik, Asama 3'te onarilacak).

Kullanim: python scripts/test_stage2.py [--all]
  --all: stage1 pass olanlari da test eder (varsayilan: pass + fail, unverified_local haric)
Girdi: data/triage.json, data/triage_stage1.json
Cikti: data/triage_stage2.json
"""
import argparse
import json
import os
import re
import sys
import concurrent.futures
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TRIAGE_PATH = os.path.join(BASE_DIR, "data", "triage.json")
STAGE1_PATH = os.path.join(BASE_DIR, "data", "triage_stage1.json")
OUT_PATH = os.path.join(BASE_DIR, "data", "triage_stage2.json")

TIMEOUT = 15
WORKERS = 10
HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"),
    "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7",
}
CHAPTER_HINT_RE = re.compile(r"bolum|chapter|b%C3%B6l%C3%BCm|episode|ch-\d|/ch\d", re.I)
LIST_PATHS = ("/manga/", "/series/", "/webtoon/", "/")


def fetch(url, attempts=2):
    last_err = None
    for _ in range(attempts):
        try:
            r = requests.get(url, headers=HEADERS, timeout=TIMEOUT, allow_redirects=True)
            if r.status_code >= 400:
                last_err = f"http {r.status_code}"
                continue
            return r.text[:600_000], None
        except requests.exceptions.RequestException as exc:
            last_err = f"{type(exc).__name__}: {str(exc)[:140]}"
    return None, last_err


def find_series_link(base_url, html):
    """Liste sayfasindaki en buyuk 'tekrar eden link grubunun' ilk ogesini seri linki olarak
    doner. img sarti KALDIRILDI: bazi siteler kart gorselini arka plan/lazy-load ile farkli
    bir elementte tutar, link <img> icermeyebilir (orn. mangadiyari.com). Bunun yerine path'in
    ilk segmentine (orn. /manga/, /seri/, /webtoon/) gore gruplayip en kalabalik grubu seçiyoruz -
    recon.mjs'in JS-DOM tarafinda yaptigi gruplamanin statik HTML karsiligi."""
    soup = BeautifulSoup(html, "lxml")
    origin = f"{urlparse(base_url).scheme}://{urlparse(base_url).netloc}"
    groups = {}
    for a in soup.select("a[href]"):
        href = a.get("href") or ""
        if not href or href.startswith("#") or href.startswith("javascript:"):
            continue
        full = urljoin(base_url, href).split("#")[0].split("?")[0]
        if not full.startswith(origin):
            continue
        path = urlparse(full).path.strip("/")
        segs = path.split("/")
        if len(segs) < 2 or len(segs[-1]) <= 2:
            continue  # ana sayfa / cok kisa slug: seri sayfasi olasiligi dusuk
        prefix = segs[0]
        groups.setdefault(prefix, []).append(full)
    if not groups:
        return None
    best_prefix = max(groups, key=lambda k: len(set(groups[k])))
    seen = []
    for u in groups[best_prefix]:
        if u not in seen:
            seen.append(u)
    # Grubun en az 2 farkli sayfa icermesi gerekir, yoksa tek bir menu linki yanlislikla secilir.
    return seen[0] if len(seen) >= 2 else None


def find_chapter_link(series_url, html):
    soup = BeautifulSoup(html, "lxml")
    origin = f"{urlparse(series_url).scheme}://{urlparse(series_url).netloc}"
    series_path = urlparse(series_url).path.rstrip("/")
    best = None
    for a in soup.select("a[href]"):
        href = a.get("href") or ""
        if not href or href.startswith("#"):
            continue
        full = urljoin(series_url, href)
        if not full.startswith(origin) or full.rstrip("/") == series_url.rstrip("/"):
            continue
        path = urlparse(full).path
        if path.startswith(series_path + "/") or CHAPTER_HINT_RE.search(full):
            best = full
            break
    return best


def has_real_reader_image(html, base_url):
    soup = BeautifulSoup(html, "lxml")
    for img in soup.find_all("img"):
        src = img.get("src") or img.get("data-src") or img.get("data-lazy-src") or img.get("data-original") \
            or img.get("data-original-src") or ""
        if not src or src.startswith("data:"):
            continue
        low = src.lower()
        if any(bad in low for bad in ("logo", "icon", "avatar", "placeholder", "spinner", "loading")):
            continue
        return True, src
    return False, None


def check_static_selector(html, css):
    """CHAPTER_ITEM/READER_IMAGES gibi bir CSS selector'un statik HTML'de kac element esledigini
    doner. soupsieve bazi gelismis CSS'leri desteklemeyebilir; o durumda None (bilinmiyor) doner."""
    try:
        soup = BeautifulSoup(html, "lxml")
        return len(soup.select(css))
    except Exception:
        return None


GENPARSER_FIELD_RE = {
    "CHAPTER_ITEM": re.compile(r'const val CHAPTER_ITEM\s*=\s*"((?:[^"\\]|\\.)*)"'),
    "READER_IMAGES": re.compile(r'const val READER_IMAGES\s*=\s*"((?:[^"\\]|\\.)*)"'),
    "LIST_ITEM": re.compile(r'const val LIST_ITEM\s*=\s*"((?:[^"\\]|\\.)*)"'),
}


def extract_generated_selectors(kt_path):
    """generated/<domain>/jar/*.kt sablonundan sabit CSS selector degerlerini cikarir."""
    if not kt_path or not os.path.isfile(os.path.join(BASE_DIR, kt_path)):
        return {}
    text = open(os.path.join(BASE_DIR, kt_path), encoding="utf-8").read()
    out = {}
    for field, rx in GENPARSER_FIELD_RE.items():
        m = rx.search(text)
        if m:
            out[field] = m.group(1).encode().decode("unicode_escape")
    return out


def check_one(entry):
    domain = entry["domain"]
    base = f"https://{domain}"

    list_html, err = None, None
    for p in LIST_PATHS:
        list_html, err = fetch(base + p)
        if list_html:
            list_url = base + p
            break
    if not list_html:
        return {"domain": domain, "stage2": "skip", "reason": f"liste sayfasi cekilemedi: {err}"}

    series_url = find_series_link(list_url, list_html)
    if not series_url:
        return {"domain": domain, "stage2": "fail", "reason": "liste sayfasinda seri linki bulunamadi"}

    detail_html, err = fetch(series_url)
    if not detail_html:
        return {"domain": domain, "stage2": "fail", "reason": f"detay sayfasi cekilemedi: {err}", "series_url": series_url}

    selectors = extract_generated_selectors(entry.get("code_path")) if entry.get("kind") == "generated" else {}
    selector_report = {}
    if selectors.get("CHAPTER_ITEM"):
        n = check_static_selector(detail_html, selectors["CHAPTER_ITEM"])
        selector_report["CHAPTER_ITEM"] = {"css": selectors["CHAPTER_ITEM"], "matches": n}

    chapter_url = find_chapter_link(series_url, detail_html)
    if not chapter_url:
        return {"domain": domain, "stage2": "fail", "reason": "detay sayfasinda bolum linki bulunamadi",
                "series_url": series_url, "selector_report": selector_report}

    reader_html, err = fetch(chapter_url)
    if not reader_html:
        return {"domain": domain, "stage2": "fail", "reason": f"bolum sayfasi cekilemedi: {err}",
                "series_url": series_url, "chapter_url": chapter_url, "selector_report": selector_report}

    if selectors.get("READER_IMAGES"):
        n = check_static_selector(reader_html, selectors["READER_IMAGES"])
        selector_report["READER_IMAGES"] = {"css": selectors["READER_IMAGES"], "matches": n}

    ok, img_src = has_real_reader_image(reader_html, chapter_url)
    if not ok:
        return {"domain": domain, "stage2": "fail", "reason": "bolum sayfasinda gercek gorsel bulunamadi",
                "series_url": series_url, "chapter_url": chapter_url, "selector_report": selector_report}

    broken_fields = [f for f, info in selector_report.items() if info.get("matches") == 0]
    if broken_fields:
        # Site calisiyor (genel yontemle bolume girip gorsel cektik) ama parser kodunun
        # selector'u statik HTML'de hic eslesmiyor -> kullaniciya "bolum gelmiyor" hatasi.
        return {"domain": domain, "stage2": "selector_broken",
                "reason": f"site calisiyor ama parser selector'u kirik: {broken_fields}",
                "series_url": series_url, "chapter_url": chapter_url, "sample_image": img_src,
                "selector_report": selector_report}

    return {"domain": domain, "stage2": "pass", "reason": "liste->detay->bolum->gorsel zinciri calisti",
            "series_url": series_url, "chapter_url": chapter_url, "sample_image": img_src,
            "selector_report": selector_report}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true", help="stage1 pass olanlari da test et")
    args = ap.parse_args()

    with open(TRIAGE_PATH, encoding="utf-8") as fh:
        triage = {e["domain"]: e for e in json.load(fh)["entries"]}
    with open(STAGE1_PATH, encoding="utf-8") as fh:
        stage1 = json.load(fh)["results"]

    if args.all:
        targets = [d for d in triage if stage1.get(d, {}).get("stage1") != "unverified_local"]
    else:
        targets = [d for d, r in stage1.items() if r.get("stage1") in ("pass", "fail")]

    results = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futures = {pool.submit(check_one, triage[d]): d for d in targets}
        for fut in concurrent.futures.as_completed(futures):
            dom = futures[fut]
            try:
                results[dom] = fut.result()
            except Exception as exc:
                results[dom] = {"domain": dom, "stage2": "fail", "reason": f"crashed: {exc}"}

    counts = {}
    for r in results.values():
        counts[r["stage2"]] = counts.get(r["stage2"], 0) + 1

    out = {"generated_from": ["triage.json", "triage_stage1.json"], "counts": counts, "results": results}
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=2)
        fh.write("\n")

    print(f"Output: {OUT_PATH}")
    print(f"  tested={len(results)} counts={counts}")


if __name__ == "__main__":
    main()
