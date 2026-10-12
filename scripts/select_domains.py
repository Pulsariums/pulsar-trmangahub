#!/usr/bin/env python3
"""Health-check için probe edilecek domainleri seçer ve boşlukla ayrılmış yazdırır.

Kullanım: python scripts/select_domains.py [--sources PATH] [--engine all|madara|...]
          [--status all|published|...] [--domains "a.com,b.com"]
--domains doluysa filtreler yerine o liste kullanılır. Scope multilang kaynaklar seçilmez.
Seçim boşsa çıktı boştur; çağıran taraf bu durumda tüm domainleri probe eder.
"""

import argparse
import json
import os
import sys

import rules

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_SOURCES = os.path.join(BASE_DIR, "sources", "tr", "sources.json")
ENGINES = ("all", "madara", "mangathemesia", "initmanga", "unknown")
STATUSES = ("all", "published", "cf_protected_published", "failing", "quarantined")


def parse_domains(text):
    out = []
    for part in (text or "").split(","):
        dom = part.strip().lower()
        if dom and dom not in out:
            out.append(dom)
    return out


def select(entries, engine="all", status="all", domains=""):
    explicit = parse_domains(domains)
    if explicit:
        return explicit
    out = []
    for entry in entries:
        dom = entry.get("domain")
        if not dom or rules.is_multilang(entry):
            continue
        if status != "all" and entry.get("status") != status:
            continue
        if engine != "all" and (entry.get("engine") or "unknown") != engine:
            continue
        if dom not in out:
            out.append(dom)
    return out


def load_entries(path):
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return []
    return data.get("sources") or []


def main(argv=None):
    parser = argparse.ArgumentParser(description="Health-check için domain seçer.")
    parser.add_argument("--sources", default=DEFAULT_SOURCES)
    parser.add_argument("--engine", default="all", choices=ENGINES)
    parser.add_argument("--status", default="all", choices=STATUSES)
    parser.add_argument("--domains", default="")
    args = parser.parse_args(argv)
    chosen = select(load_entries(args.sources), args.engine, args.status, args.domains)
    print(" ".join(chosen))
    return 0


if __name__ == "__main__":
    sys.exit(main())
