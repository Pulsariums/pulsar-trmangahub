#!/usr/bin/env python3
"""Asama 1 - hizli HTTP taramasi: data/triage.json'daki her domain icin liste sayfasini ceker ve
motora gore bir "manga listesi" markeri arar. probe.py'nin FUNCTIONAL_CHECKS'inden farki: tum
motorlari (madara, mangathemesia, initmanga, zeistmanga, mmrcms, signedrest, custom) kapsar.

Gecen (marker bulundu) -> stage1 "pass": sağlıklı sayılır, Asama 2'ye girmez.
Gecemeyen (http hata / marker yok / cf / dead) -> stage1 "fail": Asama 2'ye devam eder.

Kullanim: python scripts/test_stage1.py
Girdi: data/triage.json (triage.py'nin ciktisi)
Cikti: data/triage_stage1.json
"""
import json
import os
import sys
import concurrent.futures

import requests

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE_DIR, "scripts"))
IN_PATH = os.path.join(BASE_DIR, "data", "triage.json")
OUT_PATH = os.path.join(BASE_DIR, "data", "triage_stage1.json")

TIMEOUT = 15
WORKERS = 16
HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7",
}
CF_MARKERS = ("just a moment", "cf-browser-verification", "challenge-platform", "__cf_chl", "cf-chl-")

# (paths denenir sirayla, markerlardan biri govdede bulunursa listesi calisiyor sayilir)
FUNCTIONAL_CHECKS = {
    "madara": (("/manga/", "/"), ("page-item-detail", "c-tabs-item", "manga-item")),
    "mangathemesia": (("/manga/?page=1", "/manga/"), ("bsx", "listupd", "utao")),
    "initmanga": (("/manga/", "/webtoon/", "/"), ("chapter-item", "uk-grid", "manga-item", "wp-manga")),
    "zeistmanga": (("/", "/search/label/"), ("blog-posts", "PopularPosts", "status-publish")),
    "mmrcms": (("/manga-list.html", "/filterList"), ("manga-box", "line-list", "manga-item")),
    "signedrest": (("/api/manga", "/manga"), ('"title"', '"slug"', "manga-item")),
    "custom": (("/manga/", "/series/", "/"), ("chapter-item", "manga-item", "page-item-detail")),
}


def fetch(session, url):
    try:
        r = session.get(url, headers=HEADERS, timeout=TIMEOUT, allow_redirects=True)
        return {"status": r.status_code, "text": r.text[:400_000], "final_url": r.url}
    except requests.exceptions.RequestException as exc:
        return {"error": f"{type(exc).__name__}: {str(exc)[:160]}"}


def check_one(session, entry):
    domain = entry["domain"]
    engine = (entry.get("engine") or "custom").lower()
    if engine == "mangareader":
        engine = "mangathemesia"
    spec = FUNCTIONAL_CHECKS.get(engine, FUNCTIONAL_CHECKS["custom"])
    paths, markers = spec

    home = fetch(session, f"https://{domain}/")
    if "error" in home:
        # Bu makineden/agdan baglanti reddi (SSL/ConnectionReset) cok sayida domain'de ayni
        # sekilde cikiyor -> site tarafi bir ariza degil, yerel/ISP erisim kisitlamasi olasi.
        # Kesin "kirik" saymiyoruz; gercek dogrulama CI'da (_test.yml, farkli IP/datacenter).
        kind = "connreset_or_ssl" if ("ConnectionResetError" in home["error"] or "SSLError" in home["error"]) else "other"
        return {"domain": domain, "stage1": "unverified_local", "reason": f"home unreachable: {home['error']}",
                "unreachable_kind": kind}
    if home["status"] >= 400:
        return {"domain": domain, "stage1": "fail", "reason": f"home http {home['status']}"}
    low_home = home["text"].lower()
    if any(m in low_home for m in CF_MARKERS):
        return {"domain": domain, "stage1": "fail", "reason": "cloudflare challenge on home"}

    for path in paths:
        res = fetch(session, f"https://{domain}{path}")
        if "error" in res or res["status"] >= 400:
            continue
        low = res["text"].lower()
        if any(m.lower() in low for m in markers):
            return {"domain": domain, "stage1": "pass", "reason": f"marker found on {path}", "engine_used": engine}
    return {"domain": domain, "stage1": "fail", "reason": f"no listing marker on {paths} for engine={engine}",
            "engine_used": engine}


def main():
    with open(IN_PATH, encoding="utf-8") as fh:
        triage = json.load(fh)
    entries = triage["entries"]

    results = {}
    with requests.Session() as session, concurrent.futures.ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futures = {pool.submit(check_one, requests.Session(), e): e["domain"] for e in entries}
        for fut in concurrent.futures.as_completed(futures):
            dom = futures[fut]
            try:
                results[dom] = fut.result()
            except Exception as exc:
                results[dom] = {"domain": dom, "stage1": "fail", "reason": f"crashed: {exc}"}

    passed = sum(1 for r in results.values() if r["stage1"] == "pass")
    unverified = sum(1 for r in results.values() if r["stage1"] == "unverified_local")
    failed = sum(1 for r in results.values() if r["stage1"] == "fail")
    out = {"generated_from": "triage.json",
           "counts": {"pass": passed, "fail": failed, "unverified_local": unverified},
           "results": results}
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=2)
        fh.write("\n")

    print(f"Output: {OUT_PATH}")
    print(f"  pass={passed} fail={failed} unverified_local={unverified}")
    print("  (fail -> Asama 2'ye devam eder; unverified_local -> yerelden erisilemedi, CI'da dogrulanmali, Asama 2'ye GIRMEZ)")


if __name__ == "__main__":
    main()
