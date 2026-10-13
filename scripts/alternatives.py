#!/usr/bin/env python3
"""Find a working replacement domain for each broken Turkish manga source.

Input:  data/upstream_tr.json, data/probe_results.json, sources/tr/sources.json (previous
        run, for the failure count; optional)
Output: data/alternatives.json  ({broken_domain: {candidate, how, confidence, probe}}
        or {candidate: null, tried: [...]} when nothing works)

A source is broken only when rules.evaluate() quarantines it this run (so a source that
is still failing below the threshold gets no search). Multilang sources are never searched
and never offered as candidates. Candidates are tried in this order:
  1. moved_to host from the probe            (how=moved_to,   confidence=high)
  2. altDomains from Nyora                   (how=altDomains, confidence=high)
  3. other source with the same key          (how=same_key,   confidence=medium)
  4. other source with a key similarity >=0.85 (how=similar_key, confidence=low)
  5. other source with the same name         (how=same_name,  confidence=medium)
Within a group, sources that share the same engine are tried first. Each
candidate is checked with probe.probe_one (the same code path as probe.py); the
first candidate with status ok, functional != false and an accepted page (HTTP 200, a title
token from the source name or a manga/webtoon/bölüm/chapter keyword, no blacklisted word) wins. Results are cached
for the run, so one domain is never probed twice.
"""

import argparse
import difflib
import html
import json
import os
import re
import sys

import requests

import probe
import rules

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
PREV_SOURCES_PATH = os.path.join(BASE_DIR, "sources", "tr", "sources.json")

SIMILAR_MIN = 0.85

# Page acceptance for a candidate: HTTP 200, a title token from the source name (or a content keyword),
# and no blacklisted word in the title or URL.
PAGE_KEYWORDS = ("manga", "webtoon", "bölüm", "chapter")
SCALE_WORDS = {"manga", "manhwa", "manhua", "webtoon", "webtoons", "comic", "comics", "novel", "scan",
               "scans", "tr", "türkçe", "çeviri", "ceviri", "oku", "online"}
BLACKLIST = ("bahis", "casino", "slot", "judi", "kumar", "porn", "for sale", "parked",
             "domain satılık", "satılık", "satilik")


def norm_name(name):
    return " ".join((name or "").lower().split())


def engine_of(src):
    return probe.canonical_engine(src.get("engine") or ((src.get("formats") or {}).get("catalog") or {}).get("engine"))


def build_candidates(domain, src_records, sources, probe_row):
    """Return an ordered list of {domain, how, confidence} without duplicates."""
    out = []
    seen = {domain}
    multilang = {s["domain"] for s in sources if s.get("domain") and rules.is_multilang(s)}

    def add(cand, how, confidence):
        if cand and cand not in seen and cand not in multilang:
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
    others = [s for s in sources if s.get("domain") and s["domain"] != domain
              and not rules.is_multilang(s)]

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


def name_tokens(name):
    """Lowercase words of a source name, with spaces/dashes split and scale words dropped."""
    parts = re.split(r"[\s\-_]+", (name or "").lower())
    return [p for p in parts if len(p) >= 3 and p not in SCALE_WORDS]


def page_accepted(result, name):
    """True when the probed candidate page passes the title/keyword/blacklist rule."""
    page = result.get("page") or {}
    if page.get("http") != 200:
        return False
    title = page.get("title") or ""
    url_text = f"{result.get('domain') or ''} {page.get('finalUrl') or ''}".lower()
    if any(word in title or word in url_text for word in BLACKLIST):
        return False
    if any(token in title for token in name_tokens(name)):
        return True
    body = page.get("body") or ""
    return any(keyword in body for keyword in PAGE_KEYWORDS)


def probe_with_page(domain):
    """probe.probe_one plus one GET of the page for title/body; the page is read only when status is ok."""
    row = probe.probe_one(domain)
    if row.get("status") != "ok":
        return row
    with requests.Session() as session:
        session.headers.update(probe.HEADERS)
        raw = probe.fetch_once(session, row.get("finalUrl") or f"https://{domain}/")
    if "error_kind" in raw:
        row["page"] = {"http": None, "error": raw["error_kind"]}
        return row
    match = re.search(r"<title[^>]*>(.*?)</title>", raw["text"], re.IGNORECASE | re.DOTALL)
    title = html.unescape(match.group(1)) if match else ""
    row["page"] = {"http": raw["status"], "finalUrl": raw["final_url"],
                   "title": " ".join(title.split()).lower(), "body": raw["text"].lower()}
    return row


def find_alternative(domain, src_records, sources, probe_row, cache):
    tried = []
    name = src_records[0].get("name")
    for cand in build_candidates(domain, src_records, sources, probe_row):
        result = cache.get(cand["domain"])
        page_ok = page_accepted(result, name)
        ok = result.get("status") == "ok" and result.get("functional") is not False and page_ok
        if ok:
            return {
                "candidate": cand["domain"],
                "how": cand["how"],
                "confidence": cand["confidence"],
                "probe": {"status": result.get("status"), "functional": result.get("functional"),
                          "http": result.get("http"), "finalUrl": result.get("finalUrl")},
            }
        tried.append({"domain": cand["domain"], "how": cand["how"], "confidence": cand["confidence"],
                      "status": result.get("status"), "functional": result.get("functional"),
                      "page_ok": page_ok})
    return {"candidate": None, "tried": tried}


def load_inputs(data_dir):
    with open(os.path.join(data_dir, "upstream_tr.json"), encoding="utf-8") as fh:
        upstream = json.load(fh)
    with open(os.path.join(data_dir, "probe_results.json"), encoding="utf-8") as fh:
        probes = json.load(fh)
    return upstream.get("sources", []), probes.get("results", [])


def load_prev_by_id(path):
    """Previous build's entries keyed by id; empty when the file does not exist yet."""
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as fh:
        return {e["id"]: e for e in json.load(fh).get("sources", [])}


def run(sources, probe_rows, prober, prev_by_id=None):
    """Return the alternatives mapping for every quarantined domain.

    prev_by_id maps domain -> entry from the previous sources.json (used for the failure count).
    """
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
        src_records = records_by_domain.get(domain) or [{"key": row.get("key"), "name": row.get("name")}]
        if any(rules.is_multilang(s) for s in src_records):
            continue
        verdict = rules.evaluate(row, (prev_by_id or {}).get(domain))
        if not verdict or verdict["status"] != "quarantined":
            continue
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
    parser.add_argument("--prev", default=PREV_SOURCES_PATH,
                        help="previous sources.json (same file build.py reads)")
    args = parser.parse_args(argv)
    out_path = args.out or os.path.join(args.data_dir, "alternatives.json")

    try:
        sources, probe_rows = load_inputs(args.data_dir)
        prev_by_id = load_prev_by_id(args.prev)
    except (OSError, ValueError) as exc:
        print(f"ERROR cannot read inputs: {exc}", file=sys.stderr)
        return 1

    result, cache = run(sources, probe_rows, probe_with_page, prev_by_id)
    write_json(out_path, result)

    found = sum(1 for v in result.values() if v.get("candidate"))
    print(f"Output: {out_path}")
    print(f"  broken domains: {len(result)}  alternatives found: {found}  "
          f"not found: {len(result) - found}")
    print(f"  candidate probes: {cache.probes_made}  cache hits: {cache.cache_hits}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
