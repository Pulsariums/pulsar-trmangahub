#!/usr/bin/env python3
"""Find a working replacement domain for each broken Turkish manga source.

Input:  data/upstream_tr.json, data/probe_results.json
Output: data/alternatives.json  ({broken_domain: {candidate, how, confidence, probe}}
        or {candidate: null, tried: [...]} when nothing works)

A source is broken when its probe status is dead or parked, or when it answers
ok but probe reports functional == false. Candidates are tried in this order:
  1. moved_to host from the probe            (how=moved_to,   confidence=high)
  2. altDomains from Nyora                   (how=altDomains, confidence=high)
  3. other source with the same key          (how=same_key,   confidence=medium)
  4. other source with a key similarity >=0.85 (how=similar_key, confidence=low)
  5. other source with the same name         (how=same_name,  confidence=medium)
Within a group, sources that share the same engine are tried first. Each
candidate is checked with probe.probe_one (the same code path as probe.py); the
first candidate with status ok and functional != false wins. Results are cached
for the run, so one domain is never probed twice.
"""

import argparse
import difflib
import json
import os
import sys

import probe

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")

SIMILAR_MIN = 0.85
BROKEN_STATUSES = ("dead", "parked")


def is_broken(row):
    return row.get("status") in BROKEN_STATUSES or (
        row.get("status") == "ok" and row.get("functional") is False)


def norm_name(name):
    return " ".join((name or "").lower().split())


def engine_of(src):
    return probe.canonical_engine(src.get("engine") or ((src.get("formats") or {}).get("catalog") or {}).get("engine"))


def build_candidates(domain, src_records, sources, probe_row):
    """Return an ordered list of {domain, how, confidence} without duplicates."""
    out = []
    seen = {domain}

    def add(cand, how, confidence):
        if cand and cand not in seen:
            seen.add(cand)
            out.append({"domain": cand, "how": how, "confidence": confidence})

    if probe_row.get("moved_to"):
        add(probe_row["moved_to"], "moved_to", "high")
    for src in src_records:
        for alt in src.get("altDomains") or []:
            add(alt, "altDomains", "high")

    primary = src_records[0]
    key = primary.get("key") or ""
    name = norm_name(primary.get("name"))
    engine = engine_of(primary)
    others = [s for s in sources if s.get("domain") and s["domain"] != domain]

    def same_engine_first(items):
        return sorted(items, key=lambda o: not (engine and engine_of(o) == engine))

    for other in same_engine_first([o for o in others if o.get("key") == key]):
        add(other["domain"], "same_key", "medium")

    similar = []
    for other in others:
        okey = other.get("key") or ""
        if not key or okey == key:
            continue
        ratio = difflib.SequenceMatcher(None, key, okey).ratio()
        if ratio >= SIMILAR_MIN:
            similar.append((ratio, other))
    similar.sort(key=lambda pair: (-pair[0], not (engine and engine_of(pair[1]) == engine)))
    for _, other in similar:
        add(other["domain"], "similar_key", "low")

    for other in same_engine_first([o for o in others if name and norm_name(o.get("name")) == name]):
        add(other["domain"], "same_name", "medium")

    return out


class ProbeCache:
    def __init__(self, prober):
        self.prober = prober
        self.store = {}
        self.probes_made = 0
        self.cache_hits = 0

    def get(self, domain):
        if domain in self.store:
            self.cache_hits += 1
            return self.store[domain]
        result = self.prober(domain)
        self.probes_made += 1
        self.store[domain] = result
        return result


def find_alternative(domain, src_records, sources, probe_row, cache):
    tried = []
    for cand in build_candidates(domain, src_records, sources, probe_row):
        result = cache.get(cand["domain"])
        ok = result.get("status") == "ok" and result.get("functional") is not False
        if ok:
            return {
                "candidate": cand["domain"],
                "how": cand["how"],
                "confidence": cand["confidence"],
                "probe": {"status": result.get("status"), "functional": result.get("functional"),
                          "http": result.get("http"), "finalUrl": result.get("finalUrl")},
            }
        tried.append({"domain": cand["domain"], "how": cand["how"], "confidence": cand["confidence"],
                      "status": result.get("status"), "functional": result.get("functional")})
    return {"candidate": None, "tried": tried}


def load_inputs(data_dir):
    with open(os.path.join(data_dir, "upstream_tr.json"), encoding="utf-8") as fh:
        upstream = json.load(fh)
    with open(os.path.join(data_dir, "probe_results.json"), encoding="utf-8") as fh:
        probes = json.load(fh)
    return upstream.get("sources", []), probes.get("results", [])


def run(sources, probe_rows, prober):
    """Return the alternatives mapping for every broken domain."""
    rows_by_domain = {}
    for row in probe_rows:
        rows_by_domain.setdefault(row["domain"], row)
    records_by_domain = {}
    for src in sources:
        if src.get("domain"):
            records_by_domain.setdefault(src["domain"], []).append(src)

    cache = ProbeCache(prober)
    result = {}
    for domain in sorted(rows_by_domain):
        row = rows_by_domain[domain]
        if not is_broken(row):
            continue
        src_records = records_by_domain.get(domain) or [{"key": row.get("key"), "name": row.get("name")}]
        result[domain] = find_alternative(domain, src_records, sources, row, cache)
    return result, cache


def write_json(path, payload):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2, sort_keys=True)
        fh.write("\n")
    os.replace(tmp, path)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Find alternative domains for broken TR sources.")
    parser.add_argument("--data-dir", default=DATA_DIR)
    parser.add_argument("--out", default=None, help="default: <data-dir>/alternatives.json")
    args = parser.parse_args(argv)
    out_path = args.out or os.path.join(args.data_dir, "alternatives.json")

    try:
        sources, probe_rows = load_inputs(args.data_dir)
    except (OSError, ValueError) as exc:
        print(f"ERROR cannot read inputs: {exc}", file=sys.stderr)
        return 1

    result, cache = run(sources, probe_rows, probe.probe_one)
    write_json(out_path, result)

    found = sum(1 for v in result.values() if v.get("candidate"))
    print(f"Output: {out_path}")
    print(f"  broken domains: {len(result)}  alternatives found: {found}  "
          f"not found: {len(result) - found}")
    print(f"  candidate probes: {cache.probes_made}  cache hits: {cache.cache_hits}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
