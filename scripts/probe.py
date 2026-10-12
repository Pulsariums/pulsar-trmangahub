#!/usr/bin/env python3
"""Probe every domain in data/upstream_tr.json and write data/probe_results.json.

Status classes:
  ok           HTTP < 400 with an HTML body
  cf_protected reachable but behind a Cloudflare challenge (403/503 + Cloudflare signal, or challenge page)
  dead         DNS failure, connection error, timeout, 404/410, or 5xx after retries
  parked       HTML body carries domain-sale / parking markers
  other        non-dead HTTP error (e.g. 401/403/429 without Cloudflare) or non-HTML body
  blocked      the egress proxy refused CONNECT with 403/407 (sandbox policy, not a site state)
Each domain gets up to ATTEMPTS tries, retried only for transient failures.
"""

import argparse
import collections
import concurrent.futures
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from urllib.parse import urlparse

import requests

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
IN_PATH = os.path.join(DATA_DIR, "upstream_tr.json")
OUT_PATH = os.path.join(DATA_DIR, "probe_results.json")

TIMEOUT = 15
ATTEMPTS = 2
WORKERS = 16
MAX_BODY_BYTES = 400_000
HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7",
}

CF_CHALLENGE_MARKERS = ("just a moment", "cf-browser-verification", "challenge-platform",
                        "__cf_chl", "cf-chl-", "attention required! | cloudflare")
PARKING_MARKERS = ("this domain is for sale", "domain is for sale", "buy this domain",
                   "domain parking", "parked free", "sedoparking", "dan.com/buy",
                   "hugedomains.com", "alan adı satılık", "bu alan adı satılık", "domain satılık")
ENGINE_FINGERPRINTS = (
    ("madara", ("wp-content/themes/madara", "madara-core", "wp-manga", "wp-content/plugins/wp-manga",
                "manga-chapters-holder", "page-item-detail")),
    ("mangathemesia", ("mangareader", "ts-breadcrumb", "wp-content/themes/mangareader", "themesia",
                       "ts_reader", "listupd", "bsx")),
    ("initmanga", ("initmanga",)),
)
# Catalog engine names that are equivalent to a detected engine name.
ENGINE_ALIASES = {"mangareader": "mangathemesia"}
# Engines a catalog hint may name; used for the functional check when detection finds nothing.
HINT_ENGINES = ("madara", "mangathemesia", "initmanga")
# Engine-specific listing check: (paths tried in order, markers that prove a manga listing).
# A marker is only searched in the body of a 2xx/3xx response.
FUNCTIONAL_CHECKS = {
    "madara": (("/manga/", "/"), ("page-item-detail", "c-tabs-item", "manga-item")),
    "mangathemesia": (("/manga/?page=1",), ("bsx", "listupd", "utao")),
}
DNS_ERROR_MARKERS = ("name or service not known", "nodename nor servname", "nameresolutionerror",
                     "failed to resolve", "getaddrinfo failed", "temporary failure in name resolution",
                     "no address associated with hostname")


def host_of(url):
    host = (urlparse(url).hostname or "").lower()
    return host[4:] if host.startswith("www.") else host


def detect_engine(text):
    low = text.lower()
    for name, markers in ENGINE_FINGERPRINTS:
        if any(marker in low for marker in markers):
            return name
    return "unknown"


def canonical_engine(name):
    """Lowercase engine name with catalog aliases resolved; None for an empty value."""
    if not name:
        return None
    low = str(name).strip().lower()
    return ENGINE_ALIASES.get(low, low)


def engine_hint_of(src):
    """Engine named by an upstream record (engine or formats.catalog.engine), if it is a HINT_ENGINES name."""
    raw = src.get("engine") or ((src.get("formats") or {}).get("catalog") or {}).get("engine")
    name = canonical_engine(raw)
    return name if name in HINT_ENGINES else None


def check_functional(session, domain, engine):
    """Return (functional, reason). functional is True, False or None (not checkable).

    Only a 2xx/3xx body that lacks every marker counts as False. If no request got a
    usable response (all failed), the result is None.
    """
    spec = FUNCTIONAL_CHECKS.get(engine)
    if spec is None:
        return None, "engine unknown; functional check skipped"
    paths, markers = spec
    got_response = False
    last_error = None
    for path in paths:
        raw = fetch_once(session, f"https://{domain}{path}")
        if "error_kind" in raw:
            last_error = raw["error_kind"]
            continue
        if raw["status"] >= 400:
            got_response = True
            continue
        got_response = True
        low = raw["text"].lower()
        if any(marker in low for marker in markers):
            return True, f"{engine} listing marker found on {path}"
    if got_response:
        return False, f"{engine} listing marker not found on {', '.join(paths)}"
    return None, f"functional request failed: {last_error}"


def classify_response(status, headers, text, is_html):
    """Return (status_class, reason) for an HTTP response."""
    low = text.lower()
    challenge = any(marker in low for marker in CF_CHALLENGE_MARKERS)
    cf_signal = bool(headers.get("cf-mitigated")) or "cloudflare" in headers.get("server", "").lower()
    if challenge or (status in (403, 503) and cf_signal):
        return "cf_protected", f"http {status}; cloudflare" + (" challenge page" if challenge else "")
    if status in (404, 410):
        return "dead", f"http {status}"
    if status >= 500:
        return "dead", f"http {status}"
    if status >= 400:
        return "other", f"http {status}"
    if not is_html:
        return "other", "non-html body"
    if any(marker in low for marker in PARKING_MARKERS):
        return "parked", "parking/sale markers"
    return "ok", f"http {status}"


def _charset(content_type):
    match = re.search(r"charset=([\w.-]+)", content_type or "", re.IGNORECASE)
    return match.group(1) if match else "utf-8"


def _short(exc):
    return f"{type(exc).__name__}: {str(exc)[:200]}"


def fetch_once(session, url):
    """Return a dict with either 'error_kind' or status/headers/text/final_url."""
    started = time.monotonic()

    def elapsed():
        return int((time.monotonic() - started) * 1000)

    try:
        resp = session.get(url, headers=HEADERS, timeout=TIMEOUT, allow_redirects=True, stream=True)
    except requests.exceptions.ProxyError as exc:
        kind = "proxy_policy" if re.search(r"\b(403|407)\b", str(exc)) else "proxy"
        return {"error_kind": kind, "error": _short(exc), "ms": elapsed()}
    except requests.exceptions.Timeout as exc:
        return {"error_kind": "timeout", "error": _short(exc), "ms": elapsed()}
    except requests.exceptions.ConnectionError as exc:
        msg = str(exc).lower()
        kind = "dns" if any(marker in msg for marker in DNS_ERROR_MARKERS) else "connect"
        return {"error_kind": kind, "error": _short(exc), "ms": elapsed()}
    except requests.exceptions.RequestException as exc:
        return {"error_kind": "request", "error": _short(exc), "ms": elapsed()}

    body = bytearray()
    try:
        for chunk in resp.iter_content(chunk_size=65536):
            body.extend(chunk)
            if len(body) >= MAX_BODY_BYTES:
                break
    except requests.exceptions.RequestException as exc:
        resp.close()
        return {"error_kind": "read", "error": _short(exc), "ms": elapsed()}

    content_type = resp.headers.get("Content-Type", "")
    try:
        text = bytes(body).decode(_charset(content_type), errors="replace")
    except LookupError:
        text = bytes(body).decode("utf-8", errors="replace")
    headers = {str(k).lower(): str(v) for k, v in resp.headers.items()}
    is_html = "html" in content_type.lower() or "<html" in text[:4000].lower()
    result = {
        "status": resp.status_code,
        "final_url": resp.url,
        "headers": headers,
        "text": text,
        "is_html": is_html,
        "ms": elapsed(),
    }
    resp.close()
    return result


def probe_domain(session, domain, attempts=ATTEMPTS, engine_hint=None):
    url = f"https://{domain}/"
    final = None
    for attempt in range(1, attempts + 1):
        raw = fetch_once(session, url)
        if "error_kind" in raw:
            status = "blocked" if raw["error_kind"] == "proxy_policy" else "dead"
            reason = f"{raw['error_kind']}: {raw['error']}"
            retry = raw["error_kind"] != "proxy_policy"
            record = {"status": status, "reason": reason, "http": None, "finalUrl": None,
                      "moved_to": None, "engine_detected": "unknown", "ms": raw["ms"]}
        else:
            status, reason = classify_response(raw["status"], raw["headers"], raw["text"], raw["is_html"])
            retry = status == "dead" or raw["status"] == 429
            final_host = host_of(raw["final_url"]) if raw["final_url"] else None
            record = {"status": status, "reason": reason, "http": raw["status"],
                      "finalUrl": raw["final_url"],
                      "moved_to": final_host if final_host and final_host != domain else None,
                      "engine_detected": detect_engine(raw["text"]), "ms": raw["ms"]}
        record["attempts"] = attempt
        final = record
        if not retry:
            break
    engine_source = "detected" if final["engine_detected"] != "unknown" else None
    if final["status"] == "ok":
        engine = final["engine_detected"]
        hint = canonical_engine(engine_hint)
        if engine == "unknown" and hint in HINT_ENGINES:
            engine = hint
            engine_source = "hint"
        functional, reason = check_functional(session, domain, engine)
    else:
        functional, reason = None, f"not checked: status {final['status']}"
    final["functional"] = functional
    final["functional_reason"] = reason
    final["engine_source"] = engine_source
    final["domain"] = domain
    return final


def probe_one(domain, make_session=requests.Session, engine_hint=None):
    with make_session() as session:
        session.headers.update(HEADERS)
        return probe_domain(session, domain, engine_hint=engine_hint)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Probe Turkish manga source domains.")
    parser.add_argument("--input", default=IN_PATH)
    parser.add_argument("--output", default=OUT_PATH)
    parser.add_argument("--limit", type=int, default=0, help="probe only the first N domains")
    parser.add_argument("--only", nargs="*", default=None, help="probe only these domains")
    parser.add_argument("--workers", type=int, default=WORKERS)
    args = parser.parse_args(argv)

    with open(args.input, encoding="utf-8") as fh:
        data = json.load(fh)
    sources = data.get("sources", [])
    no_domain = [s["key"] for s in sources if not s.get("domain")]
    records = [s for s in sources if s.get("domain")]
    if args.only:
        wanted = set(args.only)
        records = [s for s in records if s["domain"] in wanted]
    if args.limit:
        records = records[:args.limit]
    domains = sorted({s["domain"] for s in records})
    hints = {}
    for src in records:
        hint = engine_hint_of(src)
        if hint and src["domain"] not in hints:
            hints[src["domain"]] = hint

    probes = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(probe_one, dom, engine_hint=hints.get(dom)): dom for dom in domains}
        for fut in concurrent.futures.as_completed(futures):
            dom = futures[fut]
            try:
                probes[dom] = fut.result()
            except Exception as exc:  # keep the run going; report the failure
                probes[dom] = {"domain": dom, "status": "dead", "reason": f"probe crashed: {_short(exc)}",
                               "http": None, "finalUrl": None, "moved_to": None,
                               "engine_detected": "unknown", "ms": None, "attempts": 0,
                               "functional": None, "functional_reason": "probe crashed",
                               "engine_source": None}

    results = []
    for src in records:
        probe = probes[src["domain"]]
        catalog_engine = ((src.get("formats") or {}).get("catalog") or {}).get("engine")
        mismatch = None
        if probe["engine_detected"] != "unknown" and catalog_engine:
            mismatch = probe["engine_detected"] != canonical_engine(catalog_engine)
        results.append({
            "key": src["key"],
            "name": src["name"],
            "domain": src["domain"],
            "status": probe["status"],
            "reason": probe["reason"],
            "http": probe["http"],
            "finalUrl": probe["finalUrl"],
            "moved_to": probe["moved_to"],
            "engine_detected": probe["engine_detected"],
            "catalog_engine": catalog_engine,
            "engine_mismatch": mismatch,
            "engine_source": probe.get("engine_source"),
            "functional": probe.get("functional"),
            "functional_reason": probe.get("functional_reason"),
            "ms": probe["ms"],
            "attempts": probe["attempts"],
        })

    counts = collections.Counter(r["status"] for r in results)
    engines = collections.Counter(r["engine_detected"] for r in results)
    mismatches = sum(1 for r in results if r["engine_mismatch"])
    functional_counts = collections.Counter(
        {True: "true", False: "false", None: "null"}[r["functional"]] for r in results)
    meta = {
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "input": os.path.relpath(args.input, BASE_DIR),
        "timeout_s": TIMEOUT,
        "attempts": ATTEMPTS,
        "workers": args.workers,
        "records_probed": len(results),
        "unique_domains_probed": len(domains),
        "records_without_domain": no_domain,
        "counts": {k: counts.get(k, 0) for k in ("ok", "cf_protected", "dead", "parked", "other", "blocked")},
        "blocked_by_proxy_policy": sum(1 for r in results if r["status"] == "blocked"),
        "engine_detected": dict(engines),
        "engine_mismatch": mismatches,
        "functional": {k: functional_counts.get(k, 0) for k in ("true", "false", "null")},
    }
    write_path = args.output
    os.makedirs(os.path.dirname(write_path), exist_ok=True)
    tmp = write_path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump({"meta": meta, "results": results}, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    os.replace(tmp, write_path)

    print(f"Output: {write_path}")
    print(f"  probed records={len(results)} unique domains={len(domains)}")
    print(f"  status: {meta['counts']}")
    print(f"  blocked by proxy policy (403/407): {meta['counts']['blocked']}")
    print(f"  engines detected: {meta['engine_detected']}  engine mismatches: {mismatches}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
