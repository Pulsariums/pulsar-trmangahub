"""Unit tests for scripts/build.py. All inputs are fixtures written to a temp root."""

import json
import os
import sys
import tempfile
import time
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import build  # noqa: E402


def src(domain, name=None, mihon=True, jar=False, engine=None):
    key = domain.split(".")[0]
    formats = {"mihon": None, "jar": None, "catalog": None}
    if mihon:
        formats["mihon"] = {"pkg": f"eu.kanade.tachiyomi.extension.tr.{key}", "version": "1.0",
                            "apkUrl": f"https://example.invalid/{key}.apk"}
    if jar:
        formats["jar"] = {"parser": key.upper(), "file": f"src/{key}.kt", "broken": False,
                          "brokenReason": None}
    return {"key": key, "name": name or key.title(), "domain": domain, "baseUrl": f"https://{domain}",
            "engine": engine, "formats": formats, "nsfw": False,
            "upstreams": ["mihon"], "altDomains": []}


def prow(domain, status, functional=None, reason=None, moved_to=None):
    return {"key": domain.split(".")[0], "name": domain, "domain": domain, "status": status,
            "reason": reason or status, "http": 200 if status == "ok" else None, "finalUrl": None,
            "moved_to": moved_to, "engine_detected": "unknown", "functional": functional,
            "functional_reason": None}


def make_root(tmp, sources, rows, alts=None, prev=None):
    os.makedirs(os.path.join(tmp, "data"), exist_ok=True)
    with open(os.path.join(tmp, "data", "upstream_tr.json"), "w", encoding="utf-8") as fh:
        json.dump({"sources": sources}, fh, ensure_ascii=False)
    with open(os.path.join(tmp, "data", "probe_results.json"), "w", encoding="utf-8") as fh:
        json.dump({"meta": {"counts": {}}, "results": rows}, fh, ensure_ascii=False)
    if alts is not None:
        with open(os.path.join(tmp, "data", "alternatives.json"), "w", encoding="utf-8") as fh:
            json.dump(alts, fh, ensure_ascii=False)
    if prev is not None:
        os.makedirs(os.path.join(tmp, "sources", "tr"), exist_ok=True)
        with open(os.path.join(tmp, "sources", "tr", "sources.json"), "w", encoding="utf-8") as fh:
            json.dump(prev, fh, ensure_ascii=False)
    return tmp


def read_out(tmp, name):
    with open(os.path.join(tmp, "sources", "tr", name), encoding="utf-8") as fh:
        return json.load(fh)


def ok_rows(domains):
    return [prow(d, "ok", functional=True) for d in domains]



def _load_json(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _read_text(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


class StatusRuleTests(unittest.TestCase):
    def test_each_probe_status_maps_to_publish_status(self):
        domains = ["ok.tr", "cf.tr", "dead.tr", "parked.tr", "wrong.tr", "blk.tr", "oth.tr"]
        sources = [src(d) for d in domains]
        rows = [prow("ok.tr", "ok", functional=True), prow("cf.tr", "cf_protected"),
                prow("dead.tr", "dead"), prow("parked.tr", "parked"),
                prow("wrong.tr", "ok", functional=False, reason="http 200"),
                prow("blk.tr", "blocked"), prow("oth.tr", "other")]
        # Keep the safety switch quiet: one blocked out of seven is fine, dead 2/7 is fine.
        with tempfile.TemporaryDirectory() as tmp:
            make_root(tmp, sources, rows)
            self.assertEqual(build.main(["--root", tmp]), 0)
            by = {e["id"]: e for e in read_out(tmp, "sources.json")["sources"]}
        self.assertEqual(by["ok.tr"]["status"], "published")
        self.assertEqual(by["cf.tr"]["status"], "cf_protected_published")
        self.assertEqual(by["dead.tr"]["status"], "quarantined")
        self.assertEqual(by["parked.tr"]["status"], "quarantined")
        self.assertEqual(by["wrong.tr"]["status"], "quarantined")
        self.assertTrue(by["wrong.tr"]["reason"].startswith("functional_false"))
        self.assertEqual(by["blk.tr"]["status"], "unverified")
        self.assertTrue(by["blk.tr"]["unverified"])
        self.assertEqual(by["oth.tr"]["status"], "unverified")

    def test_blocked_keeps_previous_published_status(self):
        domains = ["a.tr", "b.tr", "c.tr", "d.tr", "e.tr", "f.tr", "g.tr", "h.tr", "i.tr", "j.tr"]
        sources = [src(d) for d in domains]
        rows = ok_rows(domains[:9]) + [prow("j.tr", "blocked")]
        prev = {"sources": [{"id": "j.tr", "status": "published", "firstSeen": "2026-01-01T00:00:00+00:00",
                             "consecutiveFailures": 0}]}
        with tempfile.TemporaryDirectory() as tmp:
            make_root(tmp, sources, rows, prev=prev)
            self.assertEqual(build.main(["--root", tmp]), 0)
            by = {e["id"]: e for e in read_out(tmp, "sources.json")["sources"]}
            pub = read_out(tmp, "published.json")
        self.assertEqual(by["j.tr"]["status"], "published")
        self.assertTrue(by["j.tr"]["unverified"])
        self.assertIn("j.tr", [m["domain"] for m in pub["mihon"]])

    def test_domainless_sources_are_not_published_and_are_counted(self):
        sources = [src("a.tr"), {"key": "nodom", "name": "NoDom", "domain": None, "baseUrl": None,
                                 "engine": None, "formats": {"mihon": None, "jar": None, "catalog": None},
                                 "nsfw": False, "upstreams": ["nyora"], "altDomains": []}]
        rows = ok_rows(["a.tr"])
        with tempfile.TemporaryDirectory() as tmp:
            make_root(tmp, sources, rows)
            build.main(["--root", tmp])
            out = read_out(tmp, "sources.json")
            report = _read_text(os.path.join(tmp, "sources", "tr", "REPORT.md"))
        self.assertEqual([e["id"] for e in out["sources"]], ["a.tr"])
        self.assertIn("domain'siz (yayınlanmadı): 1", report)


class StateTests(unittest.TestCase):
    def test_first_seen_is_kept_and_failures_count_up_then_reset(self):
        domains = [f"s{i}.tr" for i in range(10)]
        sources = [src(d) for d in domains]
        prev = {"sources": [
            {"id": "s0.tr", "status": "published", "firstSeen": "2026-01-01T00:00:00+00:00",
             "consecutiveFailures": 2},
            {"id": "s1.tr", "status": "quarantined", "firstSeen": "2025-06-01T00:00:00+00:00",
             "consecutiveFailures": 4},
        ]}
        rows = [prow("s0.tr", "dead"), prow("s1.tr", "ok", functional=True)] + ok_rows(domains[2:])
        with tempfile.TemporaryDirectory() as tmp:
            make_root(tmp, sources, rows, prev=prev)
            build.main(["--root", tmp])
            by = {e["id"]: e for e in read_out(tmp, "sources.json")["sources"]}
        self.assertEqual(by["s0.tr"]["firstSeen"], "2026-01-01T00:00:00+00:00")
        self.assertEqual(by["s0.tr"]["consecutiveFailures"], 3)
        self.assertEqual(by["s1.tr"]["firstSeen"], "2025-06-01T00:00:00+00:00")
        self.assertEqual(by["s1.tr"]["consecutiveFailures"], 0)
        self.assertEqual(by["s1.tr"]["status"], "published")

    def test_new_source_gets_first_seen_now(self):
        domains = [f"n{i}.tr" for i in range(10)]
        with tempfile.TemporaryDirectory() as tmp:
            make_root(tmp, [src(d) for d in domains], ok_rows(domains))
            build.main(["--root", tmp])
            entry = read_out(tmp, "sources.json")["sources"][0]
        self.assertTrue(entry["firstSeen"])
        self.assertEqual(entry["consecutiveFailures"], 0)


class AlternativeTests(unittest.TestCase):
    def test_alternative_attached_and_listed_while_original_stays_quarantined(self):
        domains = [f"x{i}.tr" for i in range(10)]
        sources = [src(d) for d in domains]
        rows = [prow("x0.tr", "dead")] + ok_rows(domains[1:])
        alts = {"x0.tr": {"candidate": "x0-new.tr", "how": "moved_to", "confidence": "high",
                          "probe": {"status": "ok", "functional": True}}}
        with tempfile.TemporaryDirectory() as tmp:
            make_root(tmp, sources, rows, alts=alts)
            self.assertEqual(build.main(["--root", tmp]), 0)
            by = {e["id"]: e for e in read_out(tmp, "sources.json")["sources"]}
            pub = read_out(tmp, "published.json")
        self.assertEqual(by["x0.tr"]["status"], "quarantined")
        self.assertEqual(by["x0.tr"]["alternative"]["domain"], "x0-new.tr")
        self.assertEqual(by["x0.tr"]["alternative"]["confidence"], "high")
        self.assertEqual(len(pub["via_alternative"]), 1)
        item = pub["via_alternative"][0]
        self.assertEqual(item["label"], "published_via_alternative")
        self.assertEqual(item["domain"], "x0-new.tr")
        self.assertEqual(item["id"], "x0.tr")
        self.assertNotIn("x0.tr", [m["domain"] for m in pub["mihon"]])

    def test_candidate_null_is_not_attached(self):
        domains = [f"y{i}.tr" for i in range(10)]
        rows = [prow("y0.tr", "dead")] + ok_rows(domains[1:])
        alts = {"y0.tr": {"candidate": None, "tried": []}}
        with tempfile.TemporaryDirectory() as tmp:
            make_root(tmp, [src(d) for d in domains], rows, alts=alts)
            build.main(["--root", tmp])
            by = {e["id"]: e for e in read_out(tmp, "sources.json")["sources"]}
        self.assertNotIn("alternative", by["y0.tr"])


class SafetySwitchTests(unittest.TestCase):
    def _snapshot(self, tmp):
        out = {}
        for root, _, files in os.walk(tmp):
            for name in files:
                path = os.path.join(root, name)
                with open(path, "rb") as fh:
                    out[path] = fh.read()
        return out

    def test_more_than_40_percent_dead_cancels_with_exit_2_and_no_writes(self):
        domains = [f"d{i}.tr" for i in range(10)]
        rows = [prow(d, "dead") for d in domains[:5]] + ok_rows(domains[5:])
        with tempfile.TemporaryDirectory() as tmp:
            make_root(tmp, [src(d) for d in domains], rows)
            before = self._snapshot(tmp)
            self.assertEqual(build.main(["--root", tmp]), build.EXIT_CANCEL)
            self.assertEqual(self._snapshot(tmp), before)
            self.assertFalse(os.path.exists(os.path.join(tmp, "sources")))

    def test_more_than_40_percent_blocked_cancels(self):
        domains = [f"b{i}.tr" for i in range(10)]
        rows = [prow(d, "blocked") for d in domains[:5]] + ok_rows(domains[5:])
        with tempfile.TemporaryDirectory() as tmp:
            make_root(tmp, [src(d) for d in domains], rows)
            self.assertEqual(build.main(["--root", tmp]), 2)
            self.assertFalse(os.path.exists(os.path.join(tmp, "sources")))

    def test_exactly_40_percent_dead_is_allowed(self):
        domains = [f"e{i}.tr" for i in range(10)]
        rows = [prow(d, "dead") for d in domains[:4]] + ok_rows(domains[4:])
        with tempfile.TemporaryDirectory() as tmp:
            make_root(tmp, [src(d) for d in domains], rows)
            self.assertEqual(build.main(["--root", tmp]), 0)

    def test_all_blocked_run_is_cancelled(self):
        domains = [f"f{i}.tr" for i in range(4)]
        rows = [prow(d, "blocked") for d in domains]
        with tempfile.TemporaryDirectory() as tmp:
            make_root(tmp, [src(d) for d in domains], rows)
            self.assertEqual(build.main(["--root", tmp]), 2)

    def test_missing_probe_results_is_error_not_cancel(self):
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, "data"))
            with open(os.path.join(tmp, "data", "upstream_tr.json"), "w", encoding="utf-8") as fh:
                json.dump({"sources": []}, fh)
            self.assertEqual(build.main(["--root", tmp]), 1)


class OutputTests(unittest.TestCase):
    def test_mihon_and_jar_sections_list_published_only(self):
        sources = [src("m.tr", mihon=True, jar=False), src("j.tr", mihon=False, jar=True),
                   src("q.tr", mihon=True, jar=True)]
        domains = [s["domain"] for s in sources] + [f"z{i}.tr" for i in range(7)]
        all_sources = sources + [src(d) for d in domains[3:]]
        rows = [prow("m.tr", "ok", functional=True), prow("j.tr", "dead"), prow("q.tr", "cf_protected")] + \
               ok_rows(domains[3:])
        with tempfile.TemporaryDirectory() as tmp:
            make_root(tmp, all_sources, rows)
            build.main(["--root", tmp])
            pub = read_out(tmp, "published.json")
        self.assertEqual(sorted(m["domain"] for m in pub["mihon"] if m["domain"] in ("m.tr", "j.tr", "q.tr")),
                         ["m.tr", "q.tr"])
        self.assertEqual([j["domain"] for j in pub["jar"] if j["domain"] in ("m.tr", "j.tr", "q.tr")], ["q.tr"])
        self.assertEqual(set(pub["mihon"][0]), {"pkg", "apkUrl", "version", "domain"})
        self.assertEqual(set(pub["jar"][0]), {"parser", "file", "domain"})

    def test_report_has_summary_and_change_section(self):
        domains = [f"r{i}.tr" for i in range(10)]
        rows = [prow("r0.tr", "dead")] + ok_rows(domains[1:])
        prev = {"sources": [{"id": "r0.tr", "status": "published", "firstSeen": "2026-01-01T00:00:00+00:00",
                             "consecutiveFailures": 0}]}
        with tempfile.TemporaryDirectory() as tmp:
            make_root(tmp, [src(d) for d in domains], rows, prev=prev)
            build.main(["--root", tmp])
            report = _read_text(os.path.join(tmp, "sources", "tr", "REPORT.md"))
        self.assertIn("## Özet", report)
        self.assertIn("| quarantined (karantina) | 1 |", report)
        self.assertIn("- Ölen (yayından çıkan): 1 (r0.tr)", report)

    def test_second_identical_run_does_not_rewrite_files(self):
        domains = [f"u{i}.tr" for i in range(10)]
        with tempfile.TemporaryDirectory() as tmp:
            make_root(tmp, [src(d) for d in domains], ok_rows(domains))
            self.assertEqual(build.main(["--root", tmp]), 0)
            path = os.path.join(tmp, "sources", "tr", "sources.json")
            first = os.stat(path).st_mtime_ns
            time.sleep(0.02)
            self.assertEqual(build.main(["--root", tmp]), 0)
            self.assertEqual(os.stat(path).st_mtime_ns, first)


if __name__ == "__main__":
    unittest.main(verbosity=2)
