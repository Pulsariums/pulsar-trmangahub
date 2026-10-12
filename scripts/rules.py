#!/usr/bin/env python3
"""Shared status rules for one probe result. build.py and alternatives.py both use evaluate(),
so a source is quarantined in the build exactly when alternatives.py searches for it.

Rules (prev is the entry from the previous sources.json, or None):
  ok, functional != false   -> published, consecutiveFailures 0
  cf_protected              -> cf_protected_published, consecutiveFailures 0
  immediate failure         -> quarantined (dns reason, parked, http 404/410)
  other failure             -> consecutiveFailures = prev + 1
                               >= FAIL_THRESHOLD      -> quarantined
                               prev was published     -> prev status kept, failing=True
                               otherwise              -> status "failing" (not published)
  blocked / other / none    -> None (not verified this run; caller keeps previous state)

"Other failure" means dead (ssl/connect/timeout/5xx/523/525) or ok with functional false.
"""

import os

DEFAULT_FAIL_THRESHOLD = 3


def _fail_threshold():
    try:
        value = int(os.environ.get("FAIL_THRESHOLD", "") or DEFAULT_FAIL_THRESHOLD)
    except ValueError:
        value = DEFAULT_FAIL_THRESHOLD
    return max(1, value)


FAIL_THRESHOLD = _fail_threshold()
IMMEDIATE_HTTP = (404, 410)
PUBLISHED_STATUSES = ("published", "cf_protected_published")
MULTILANG_SCOPE = "multilang"


def failure_count(prev):
    try:
        return int((prev or {}).get("consecutiveFailures") or 0)
    except (TypeError, ValueError):
        return 0


def is_immediate(probe_row):
    reason = str(probe_row.get("reason") or "")
    return (reason.startswith("dns:") or reason.startswith("redirect_") or probe_row.get("status") == "parked"
            or probe_row.get("http") in IMMEDIATE_HTTP)


def _verdict(status, reason, failures, failing=False):
    return {"status": status, "reason": reason, "consecutiveFailures": failures, "failing": failing}


def evaluate(probe_row, prev=None):
    """Return {status, reason, consecutiveFailures, failing} or None when the run did not verify it."""
    if probe_row is None:
        return None
    status = probe_row.get("status")
    if status == "ok" and probe_row.get("functional") is not False:
        return _verdict("published", probe_row.get("reason"), 0)
    if status == "cf_protected":
        return _verdict("cf_protected_published", probe_row.get("reason"), 0)
    if status == "ok":
        reason = f"functional_false: {probe_row.get('functional_reason')}"
    elif status in ("dead", "parked"):
        reason = probe_row.get("reason")
    else:
        return None

    count = failure_count(prev) + 1
    if is_immediate(probe_row) or count >= FAIL_THRESHOLD:
        return _verdict("quarantined", reason, count)
    prev_status = (prev or {}).get("status")
    if prev_status in PUBLISHED_STATUSES:
        return _verdict(prev_status, reason, count, failing=True)
    return _verdict("failing", reason, count)


def is_multilang(src):
    return (src.get("scope") or "tr_native") == MULTILANG_SCOPE


def is_ok(entry):
    """Verified working in this run: probe ok + functional check passed (status 'published').
    failing (still counted as failing) and unverified (not probed this run) do not qualify."""
    return (entry.get("status") == "published" and not entry.get("failing")
            and not entry.get("unverified"))


UNVERIFIED_ADMITTED = ("published", "cf_protected_published", "failing", "unverified")

# PULSAR_ADMIT_CF=1: Cloudflare korumalı ama canlı (cf_protected_published, failing değil) kaynaklar da
# yayınlanır. Uygulama Cloudflare'i kendi WebView'ında çözer; CI koşucusu çözemediği için bu kaynakları
# "doğrulanmamış" sayıyorduk.
ADMIT_CF = os.environ.get("PULSAR_ADMIT_CF") == "1"

# PULSAR_ADMIT_ALL=1: canlı test için aday modu; karantinadakiler dahil her statüdeki kaynak seçilir.
ADMIT_ALL = os.environ.get("PULSAR_ADMIT_ALL") == "1"

# PULSAR_LIVE_GATE=1: canlı test geçmişi (data/live/history.json) hakemdir. Son canlı testi geçen kaynak
# yayınlanır; "cloudflare" hatası kesin sonuç sayılmaz (CI koşucusu CF'yi geçemez), kaynak CF'li canlı
# statüdeyse yayınlanmaya devam eder; diğer hata sınıfları (parse, empty, http_gone, dns...) yayından çıkarır.
LIVE_GATE = os.environ.get("PULSAR_LIVE_GATE") == "1"
LIVE_HISTORY = os.environ.get("PULSAR_LIVE_HISTORY") or os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "live", "history.json")
_live_cache = None

# Kesin sonuç sayılmayan hatalar: CI koşucusu Cloudflare'i geçemez, sahte bağlam webp çözemez, hotlink/hız
# sınırı CI'a özgü olabilir. Bu sınıflarda kaynağın kayıtlı durumu korunur.
INCONCLUSIVE_CLASSES = ("cloudflare", "decode", "http_blocked", "rate_limit")
# Tek testte bile kaynağı yayından çıkaran hatalar; diğerleri (timeout, connect, 5xx) üst üste 2 başarısızlık ister.
DETERMINISTIC_CLASSES = ("http_gone", "dns", "empty", "parse", "ssl")


def _live():
    global _live_cache
    if _live_cache is None:
        import json
        try:
            with open(LIVE_HISTORY, encoding="utf-8") as fh:
                _live_cache = json.load(fh)
        except (OSError, ValueError):
            _live_cache = {}
    return _live_cache


def live_verdict(entry):
    """True: canlı test geçti, False: canlı test kaldı, None: sonuç yok veya kesin değil."""
    parser = (((entry.get("formats") or {}).get("jar")) or {}).get("parser")
    rec = _live().get(parser) if parser else None
    if not rec:
        return None
    if rec.get("ok_streak", 0) >= 1:
        return True
    cls = rec.get("error_class")
    if cls in INCONCLUSIVE_CLASSES:
        return None
    if cls in DETERMINISTIC_CLASSES or rec.get("fail_streak", 0) >= 2:
        return False
    return None


def is_publishable(entry, include_unverified=False, allow_multilang=False):
    """Publication gate for the JAR, the Mihon mirror and their index 'sources' lists.

    Default: only is_ok() entries. include_unverified=True also admits cf_protected_published,
    failing and unverified entries. quarantined entries are never admitted. multilang (scope)
    entries are admitted only with allow_multilang=True, which the global bucket uses; the
    Turkish bucket and the Mihon mirror keep the default. excluded entries never qualify."""
    if is_multilang(entry) and not allow_multilang:
        return False
    if LIVE_GATE and not ADMIT_ALL:
        verdict = live_verdict(entry)
        if verdict is True:
            return entry.get("status") != "excluded"
        if verdict is False:
            return False
    if ADMIT_ALL and entry.get("status") in ("published", "cf_protected_published", "failing", "unverified",
                                              "quarantined"):
        return True
    if is_ok(entry):
        return True
    if ADMIT_CF and entry.get("status") == "cf_protected_published" and not entry.get("failing"):
        return True
    return bool(include_unverified) and entry.get("status") in UNVERIFIED_ADMITTED
