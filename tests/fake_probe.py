"""Deterministic FAKE probe data for offline end-to-end runs. Not a live result.

Each domain gets a fixed status derived from sha256(domain), so a run is repeatable.
The distribution is roughly: 70% ok (functional), 2% ok but functional false,
8% cf_protected, 10% dead, 5% parked, 2% other, 3% blocked.

CLI:  python3 tests/fake_probe.py --root <dir>
      writes <dir>/data/probe_results.json from <dir>/data/upstream_tr.json
"""

import argparse
import collections
import hashlib
import json
import os
import sys
from datetime import datetime, timezone

FAKE_NOTE = "FAKE deterministic fixture (sandbox offline); NOT a live probe result"


def fake_status(domain):
    """Return (status, functional) for a domain, deterministically."""
    bucket = int(hashlib.sha256(domain.encode("utf-8")).hexdigest()[:8], 16) % 100
    if bucket < 70:
        return "ok", True
    if bucket < 72:
        return "ok", False
    if bucket < 80:
        return "cf_protected", None
    if bucket < 90:
        return "dead", None
    if bucket < 95:
        return "parked", None
    if bucket < 98:
        return "other", None
    return "blocked", None


def fake_row(domain, status, functional):
    return {
        "domain": domain,
        "status": status,
        "reason": f"FAKE {status}",
        "http": 200 if status == "ok" else (503 if status == "cf_protected" else None),
        "finalUrl": f"https://{domain}/" if status == "ok" else None,
        "moved_to": None,
        "engine_detected": "unknown",
        "functional": functional,
        "functional_reason": "FAKE" if status == "ok" else None,
    }


def make_probe_document(sources):
    """Build a probe_results.json document for the given upstream sources."""
    results = []
    counts = collections.Counter()
    for src in sources:
        domain = src.get("domain")
        if not domain:
            continue
        status, functional = fake_status(domain)
        counts[status] += 1
        base = fake_row(domain, status, functional)
        results.append({
            "key": src.get("key"),
            "name": src.get("name"),
            "domain": domain,
            "status": status,
            "reason": base["reason"],
            "http": base["http"],
            "finalUrl": base["finalUrl"],
            "moved_to": None,
            "engine_detected": "unknown",
            "catalog_engine": None,
            "engine_mismatch": None,
            "functional": functional,
            "functional_reason": base["functional_reason"],
            "ms": 0,
            "attempts": 1,
        })
    meta = {
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": FAKE_NOTE,
        "records_probed": len(results),
        "unique_domains_probed": len({r["domain"] for r in results}),
        "counts": {k: counts.get(k, 0) for k in ("ok", "cf_protected", "dead", "parked", "other", "blocked")},
    }
    return {"meta": meta, "results": results}


def make_fake_prober(sources):
    """Return a probe_one replacement that answers from the same fake plan."""
    known = {s["domain"] for s in sources if s.get("domain")}

    def _probe(domain):
        if domain not in known:
            status, functional = "dead", None
        else:
            status, functional = fake_status(domain)
        return {"status": status, "reason": f"FAKE {status}", "http": 200 if status == "ok" else None,
                "finalUrl": f"https://{domain}/" if status == "ok" else None, "moved_to": None,
                "engine_detected": "unknown", "functional": functional,
                "functional_reason": "FAKE", "ms": 0, "attempts": 1}
    return _probe


def main(argv=None):
    parser = argparse.ArgumentParser(description="Write FAKE probe results for an offline run.")
    parser.add_argument("--root", required=True)
    args = parser.parse_args(argv)
    data_dir = os.path.join(args.root, "data")
    with open(os.path.join(data_dir, "upstream_tr.json"), encoding="utf-8") as fh:
        sources = json.load(fh).get("sources", [])
    doc = make_probe_document(sources)
    with open(os.path.join(data_dir, "probe_results.json"), "w", encoding="utf-8") as fh:
        json.dump(doc, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    print(f"FAKE probe written: {os.path.join(data_dir, 'probe_results.json')}")
    print(f"  counts: {doc['meta']['counts']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
