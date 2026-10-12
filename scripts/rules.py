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

FAIL_THRESHOLD = 3
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
    return (reason.startswith("dns:") or probe_row.get("status") == "parked"
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
