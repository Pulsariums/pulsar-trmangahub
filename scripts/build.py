#!/usr/bin/env python3
"""Build the published TR source lists from probe and alternative results.

Inputs (under <root>/data): upstream_tr.json, probe_results.json, alternatives.json (optional)
Outputs (under <root>/sources/tr): sources.json, published.json, REPORT.md

Status rules (keyed by domain) live in rules.py: evaluate() decides published,
cf_protected_published, failing (kept out of publication until it reaches the failure
threshold), or quarantined (immediately for dns/parked/404/410). Probe blocked, other
or missing results keep the previous status with unverified=true (no previous status:
status "unverified"). scope "multilang" sources get status excluded_multilang and are
never probed into publication, searched for alternatives or counted by the safety switch.

Safety switch: if more than SAFETY_RATIO percent (default 40, "off" disables) of probed
domains are dead, or the same share are blocked, nothing is written and the script exits
with code 2 (EXIT_CANCEL). INCLUDE_MULTILANG=1 publishes multilang sources too.
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone

import rules

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

EXIT_CANCEL = 2
MAX_SHARE = 0.40
PUBLISHED_STATUSES = rules.PUBLISHED_STATUSES
EXCLUDED_STATUS = "excluded_multilang"
VOLATILE_KEYS = ("generatedAt", "lastChecked")


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def safety_limit():
    """Share limit from SAFETY_RATIO (percent). None when the switch is off."""
    raw = (os.environ.get("SAFETY_RATIO") or "").strip().lower()
    if raw == "off":
        return None
    try:
        pct = float(raw) if raw else MAX_SHARE * 100
    except ValueError:
        pct = MAX_SHARE * 100
    return pct / 100


def include_multilang():
    return os.environ.get("INCLUDE_MULTILANG") == "1"


def load_json(path, default=None):
    if not os.path.exists(path):
        return default
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def write_json(path, payload):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    os.replace(tmp, path)


def write_text(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(text)
    os.replace(tmp, path)


def unique_by_domain(rows):
    out = {}
    for row in rows:
        dom = row.get("domain")
        if dom and dom not in out:
            out[dom] = row
    return out


def safety_check(probe_rows, excluded=frozenset()):
    """Return (ok, reason). Counts are over unique probed domains, minus excluded (multilang) ones."""
    domains = {dom: row for dom, row in unique_by_domain(probe_rows).items() if dom not in excluded}
    total = len(domains)
    if total == 0:
        return False, "probe sonucu yok (0 domain)"
    limit = safety_limit()
    if limit is None:
        return True, "şalter kapalı (SAFETY_RATIO=off)"
    dead = sum(1 for r in domains.values() if r.get("status") == "dead")
    blocked = sum(1 for r in domains.values() if r.get("status") == "blocked")
    if blocked / total > limit:
        return False, f"{blocked}/{total} domain proxy politikası tarafından engellendi (%{limit*100:.0f} eşiği aşıldı)"
    if dead / total > limit:
        return False, f"{dead}/{total} domain 'dead' (%{limit*100:.0f} eşiği aşıldı; ağ sorunu olabilir)"
    return True, f"dead {dead}/{total}, blocked {blocked}/{total}"


def build_entry(src, probe_row, prev, alt_map, now):
    domain = src["domain"]
    scope = "multilang" if rules.is_multilang(src) else "tr_native"
    engine = src.get("engine") or ((src.get("formats") or {}).get("catalog") or {}).get("engine")
    if not engine and probe_row and probe_row.get("engine_detected") not in (None, "unknown"):
        engine = probe_row["engine_detected"]

    entry = {
        "id": domain,
        "name": src.get("name"),
        "domain": domain,
        "baseUrl": src.get("baseUrl") or f"https://{domain}",
        "engine": engine,
        "nsfw": bool(src.get("nsfw")),
        "scope": scope,
        "formats": src.get("formats") or {"mihon": None, "jar": None, "catalog": None},
        "firstSeen": (prev or {}).get("firstSeen") or now,
    }

    if scope == "multilang" and not include_multilang():
        entry["status"] = EXCLUDED_STATUS
        entry["reason"] = "çok dilli paket (tr dışı diller); yayınlanmaz"
        entry["consecutiveFailures"] = 0
        entry["upstreams"] = src.get("upstreams") or []
        return entry

    verdict = rules.evaluate(probe_row, prev)
    if verdict is None:
        # Not verified this run: keep the previous state and label it.
        entry["status"] = (prev or {}).get("status") or "unverified"
        entry["unverified"] = True
        entry["reason"] = (probe_row or {}).get("reason") or "probe sonucu yok"
        entry["lastChecked"] = (prev or {}).get("lastChecked")
        entry["consecutiveFailures"] = (prev or {}).get("consecutiveFailures", 0)
        if (prev or {}).get("alternative"):
            entry["alternative"] = prev["alternative"]
        alt = alt_map.get(domain) or {}
        if alt.get("candidate"):
            entry["alternative"] = {"domain": alt["candidate"], "how": alt["how"],
                                    "confidence": alt["confidence"]}
    else:
        entry["status"] = verdict["status"]
        entry["reason"] = verdict["reason"]
        entry["probe"] = {
            "status": probe_row.get("status"),
            "http": probe_row.get("http"),
            "functional": probe_row.get("functional"),
        }
        entry["lastChecked"] = now
        entry["consecutiveFailures"] = verdict["consecutiveFailures"]
        if verdict["failing"]:
            entry["failing"] = True
        if verdict["status"] == "quarantined":
            alt = alt_map.get(domain) or {}
            if alt.get("candidate"):
                entry["alternative"] = {"domain": alt["candidate"], "how": alt["how"],
                                        "confidence": alt["confidence"]}

    entry["upstreams"] = src.get("upstreams") or []
    return entry


def via_alternative(entries):
    out = []
    for entry in entries:
        alt = entry.get("alternative")
        if entry["status"] == "quarantined" and alt:
            out.append({"id": entry["id"], "domain": alt["domain"], "how": alt["how"],
                        "confidence": alt["confidence"], "label": "published_via_alternative"})
    return out


def published_payload(entries, now):
    """Default publication list: only rules.is_ok() entries (cf_protected, failing, unverified
    are left out; the workflows can opt in with include_unverified)."""
    mihon, jar = [], []
    for entry in entries:
        if not rules.is_ok(entry):
            continue
        fm = entry["formats"] or {}
        if fm.get("mihon"):
            m = fm["mihon"]
            mihon.append({"pkg": m.get("pkg"), "apkUrl": m.get("apkUrl"), "version": m.get("version"),
                          "domain": entry["domain"]})
        if fm.get("jar"):
            j = fm["jar"]
            jar.append({"parser": j.get("parser"), "file": j.get("file"), "domain": entry["domain"]})
    return {"generatedAt": now, "mihon": mihon, "jar": jar}


def strip_volatile(obj):
    if isinstance(obj, dict):
        return {k: strip_volatile(v) for k, v in obj.items() if k not in VOLATILE_KEYS}
    if isinstance(obj, list):
        return [strip_volatile(v) for v in obj]
    return obj


def diff_changes(prev_entries, entries):
    prev_by = {e["id"]: e for e in prev_entries}
    cur_by = {e["id"]: e for e in entries}
    changes = {"new": [], "died": [], "revived": [], "removed": []}
    for cid, cur in cur_by.items():
        if cid not in prev_by:
            changes["new"].append(cid)
            continue
        before = prev_by[cid].get("status")
        after = cur.get("status")
        if before in PUBLISHED_STATUSES and after == "quarantined":
            changes["died"].append(cid)
        elif before == "quarantined" and after in PUBLISHED_STATUSES:
            changes["revived"].append(cid)
    for pid in prev_by:
        if pid not in cur_by:
            changes["removed"].append(pid)
    for key in changes:
        changes[key].sort()
    return changes


def count_statuses(entries):
    counts = {"published": 0, "cf_protected_published": 0, "quarantined": 0, "unverified": 0,
              "failing": 0, EXCLUDED_STATUS: 0}
    for e in entries:
        counts[e["status"]] = counts.get(e["status"], 0) + 1
    return counts


def render_report(entries, alts, probe_meta, changes, nodomain, unverified_count):
    counts = count_statuses(entries)
    with_alt = [e for e in entries if e["status"] == "quarantined" and e.get("alternative")]
    quarantined = [e for e in entries if e["status"] == "quarantined"]
    not_found = [e for e in quarantined if not e.get("alternative")]
    lines = []
    lines.append("# TR manga kaynakları - senkron raporu")
    lines.append("")
    lines.append("## Özet")
    lines.append("")
    lines.append("| Durum | Adet |")
    lines.append("|---|---|")
    lines.append(f"| published (ok) | {counts['published']} |")
    lines.append(f"| cf_protected_published (bot korumalı, erişilebilir) | {counts['cf_protected_published']} |")
    lines.append(f"| quarantined (karantina) | {counts['quarantined']} |")
    lines.append(f"| unverified (bu run doğrulanamadı) | {counts['unverified']} |")
    lines.append("")
    lines.append(f"- excluded_multilang: {counts[EXCLUDED_STATUS]}")
    lines.append(f"- Domain'li toplam kaynak: {len(entries)}; domain'siz (yayınlanmadı): {len(nodomain)}")
    lines.append(f"- Karantinadaki kaynaklardan alternatif bulunan: {len(with_alt)}; "
                 f"bulunamayan: {len(not_found)}")
    lines.append(f"- Alternatif yayın listesinde (published_via_alternative): {len(with_alt)}")
    lines.append("")
    lines.append("## Probe özeti")
    lines.append("")
    pc = probe_meta.get("counts", {})
    lines.append("| ok | cf_protected | dead | parked | other | blocked |")
    lines.append("|---|---|---|---|---|---|")
    lines.append("| " + " | ".join(str(pc.get(k, 0)) for k in
                                   ("ok", "cf_protected", "dead", "parked", "other", "blocked")) + " |")
    lines.append("")
    lines.append("## Alternatifler")
    lines.append("")
    if with_alt:
        lines.append("| Kaynak | Alternatif | Yöntem | Güven |")
        lines.append("|---|---|---|---|")
        for e in with_alt:
            a = e["alternative"]
            lines.append(f"| {e['name']} ({e['domain']}) | {a['domain']} | {a['how']} | {a['confidence']} |")
    else:
        lines.append("Bu run'da alternatif bulunamadı.")
    lines.append("")
    lines.append("## Bu run'da değişenler")
    lines.append("")
    for label, key in (("Yeni eklenen", "new"), ("Ölen (yayından çıkan)", "died"),
                       ("Geri dirilen", "revived"), ("Upstream'den kaldırılan", "removed")):
        items = changes[key]
        lines.append(f"- {label}: {len(items)}" + (f" ({', '.join(items)})" if items else ""))
    lines.append("")
    if unverified_count:
        lines.append(f"Not: {unverified_count} kaynak bu run'da doğrulanamadı (blocked/other); önceki durumu korundu.")
        lines.append("")
    return "\n".join(lines) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description="Build published TR source lists.")
    parser.add_argument("--root", default=BASE_DIR, help="repo root containing data/ (default: this repo)")
    args = parser.parse_args(argv)
    data_dir = os.path.join(args.root, "data")
    out_dir = os.path.join(args.root, "sources", "tr")

    upstream = load_json(os.path.join(data_dir, "upstream_tr.json"))
    probes = load_json(os.path.join(data_dir, "probe_results.json"))
    if upstream is None or probes is None:
        print("ERROR upstream_tr.json veya probe_results.json yok", file=sys.stderr)
        return 1
    alt_doc = load_json(os.path.join(data_dir, "alternatives.json"), default={}) or {}
    prev_doc = load_json(os.path.join(out_dir, "sources.json"), default={}) or {}

    probe_rows = probes.get("results", [])
    excluded = set() if include_multilang() else {
        s["domain"] for s in upstream.get("sources", []) if s.get("domain") and rules.is_multilang(s)}
    ok, reason = safety_check(probe_rows, excluded)
    if not ok:
        print(f"IPTAL: yayınlama durduruldu - {reason}", file=sys.stderr)
        print("Hiçbir dosya değiştirilmedi.", file=sys.stderr)
        return EXIT_CANCEL

    now = now_iso()
    prev_by_id = {e["id"]: e for e in prev_doc.get("sources", [])}
    probe_by_domain = unique_by_domain(probe_rows)

    nodomain = [s.get("key") for s in upstream.get("sources", []) if not s.get("domain")]
    src_by_domain = {}
    for src in upstream.get("sources", []):
        if src.get("domain") and src["domain"] not in src_by_domain:
            src_by_domain[src["domain"]] = src

    entries = []
    for domain in sorted(src_by_domain):
        entries.append(build_entry(src_by_domain[domain], probe_by_domain.get(domain),
                                   prev_by_id.get(domain), alt_doc, now))
    entries.sort(key=lambda e: e["id"])

    changes = diff_changes(prev_doc.get("sources", []), entries)
    counts = count_statuses(entries)

    sources_payload = {"generatedAt": now, "count": len(entries), "sources": entries}
    published = published_payload(entries, now)
    published["via_alternative"] = via_alternative(entries)
    probe_meta = probes.get("meta", {})
    report = render_report(entries, alt_doc, probe_meta, changes, nodomain, counts["unverified"])

    prev_published = load_json(os.path.join(out_dir, "published.json"), default=None)
    prev_report_path = os.path.join(out_dir, "REPORT.md")
    prev_report = None
    if os.path.exists(prev_report_path):
        with open(prev_report_path, encoding="utf-8") as fh:
            prev_report = fh.read()

    # Each file is rewritten only when its own meaningful content changed.
    written = []
    if not (prev_doc and strip_volatile(prev_doc) == strip_volatile(sources_payload)):
        write_json(os.path.join(out_dir, "sources.json"), sources_payload)
        written.append("sources.json")
    if prev_published is None or strip_volatile(prev_published) != strip_volatile(published):
        write_json(os.path.join(out_dir, "published.json"), published)
        written.append("published.json")
    if prev_report != report:
        write_text(prev_report_path, report)
        written.append("REPORT.md")
    if not written:
        print("Değişiklik yok; dosyalar yazılmadı.")
        return 0

    print(f"Yazılan: {', '.join(written)}")
    print(f"Output: {out_dir}")
    print(f"  safety: {reason}")
    print(f"  published={counts['published']} cf={counts['cf_protected_published']} "
          f"quarantined={counts['quarantined']} failing={counts['failing']} "
          f"excluded_multilang={counts[EXCLUDED_STATUS]} unverified={counts['unverified']} "
          f"via_alternative={len(published['via_alternative'])}")
    print(f"  changes: {({k: len(v) for k, v in changes.items()})}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
