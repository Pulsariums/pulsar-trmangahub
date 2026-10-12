"""Unit tests for scripts/build.py. All inputs are fixtures written to a temp root."""

import json
import os
import sys
import tempfile
import time
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import build  # noqa: E402

DNS_REASON = "dns: NameResolutionError: Failed to resolve"


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


def read_out(tmp, name, bucket="tr"):
    with open(os.path.join(tmp, "sources", bucket, name), encoding="utf-8") as fh:
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
                prow("dead.tr", "dead", reason=DNS_REASON), prow("parked.tr", "parked"),
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
        self.assertEqual(by["wrong.tr"]["status"], "failing")
        self.assertTrue(by["wrong.tr"]["reason"].startswith("functional_false"))
        self.assertEqual(by["blk.tr"]["status"], "unverified")
        self.assertTrue(by["blk.tr"]["unverified"])
        self.assertEqual(by["oth.tr"]["status"], "unverified")

    def test_blocked_keeps_previous_status_but_is_not_listed(self):
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
        self.assertNotIn("j.tr", [m["domain"] for m in pub["mihon"]])

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
        rows = [prow("x0.tr", "dead", reason=DNS_REASON)] + ok_rows(domains[1:])
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
        rows = [prow("y0.tr", "dead", reason=DNS_REASON)] + ok_rows(domains[1:])
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


def run_build(target_rows, sources=None, prev_entries=None):
    """Run build on target_rows plus eight ok filler domains (keeps the safety switch quiet).

    Returns (entries by id, published.json, REPORT.md text).
    """
    targets = [r["domain"] for r in target_rows]
    fillers = [f"fill{i}.tr" for i in range(8)]
    all_sources = sources if sources is not None else [src(d) for d in targets]
    all_sources = all_sources + [src(d) for d in fillers]
    rows = list(target_rows) + ok_rows(fillers)
    prev = {"sources": prev_entries} if prev_entries is not None else None
    with tempfile.TemporaryDirectory() as tmp:
        make_root(tmp, all_sources, rows, prev=prev)
        code = build.main(["--root", tmp])
        assert code == 0, code
        by = {e["id"]: e for e in read_out(tmp, "sources.json")["sources"]}
        pub = read_out(tmp, "published.json")
        report = _read_text(os.path.join(tmp, "sources", "tr", "REPORT.md"))
    return by, pub, report


def prev_entry(domain, status, failures=0):
    return {"id": domain, "status": status, "firstSeen": "2026-01-01T00:00:00+00:00",
            "consecutiveFailures": failures}


class FailureToleranceTests(unittest.TestCase):
    def test_non_immediate_failure_without_history_is_failing_and_not_published(self):
        by, pub, _ = run_build([prow("t.tr", "dead", reason="timeout: ReadTimeout")])
        self.assertEqual(by["t.tr"]["status"], "failing")
        self.assertEqual(by["t.tr"]["consecutiveFailures"], 1)
        self.assertNotIn("failing", by["t.tr"])
        self.assertNotIn("t.tr", [m["domain"] for m in pub["mihon"]])

    def test_published_source_stays_published_but_not_listed_while_failing(self):
        by, pub, _ = run_build([prow("t.tr", "dead", reason="connect: ConnectionError")],
                               prev_entries=[prev_entry("t.tr", "published", 1)])
        self.assertEqual(by["t.tr"]["status"], "published")
        self.assertTrue(by["t.tr"]["failing"])
        self.assertEqual(by["t.tr"]["consecutiveFailures"], 2)
        self.assertNotIn("t.tr", [m["domain"] for m in pub["mihon"]])

    def test_cf_protected_published_stays_while_failing(self):
        by, pub, _ = run_build([prow("t.tr", "dead", reason="http 500")],
                               prev_entries=[prev_entry("t.tr", "cf_protected_published", 0)])
        self.assertEqual(by["t.tr"]["status"], "cf_protected_published")
        self.assertTrue(by["t.tr"]["failing"])

    def test_third_consecutive_failure_quarantines(self):
        by, pub, _ = run_build([prow("t.tr", "dead", reason="http 523")],
                               prev_entries=[prev_entry("t.tr", "published", 2)])
        self.assertEqual(by["t.tr"]["status"], "quarantined")
        self.assertEqual(by["t.tr"]["consecutiveFailures"], 3)
        self.assertNotIn("t.tr", [m["domain"] for m in pub["mihon"]])

    def test_functional_false_counts_as_failure(self):
        by, _, _ = run_build([prow("t.tr", "ok", functional=False, reason="http 200")],
                             prev_entries=[prev_entry("t.tr", "published", 0)])
        self.assertEqual(by["t.tr"]["status"], "published")
        self.assertTrue(by["t.tr"]["failing"])
        self.assertEqual(by["t.tr"]["consecutiveFailures"], 1)

    def test_success_resets_failure_count_and_clears_failing(self):
        by, pub, _ = run_build([prow("t.tr", "ok", functional=True)],
                               prev_entries=[prev_entry("t.tr", "failing", 2)])
        self.assertEqual(by["t.tr"]["status"], "published")
        self.assertEqual(by["t.tr"]["consecutiveFailures"], 0)
        self.assertNotIn("failing", by["t.tr"])

    def test_dns_failure_quarantines_immediately(self):
        by, _, _ = run_build([prow("t.tr", "dead", reason=DNS_REASON)],
                             prev_entries=[prev_entry("t.tr", "published", 0)])
        self.assertEqual(by["t.tr"]["status"], "quarantined")

    def test_parked_quarantines_immediately(self):
        by, _, _ = run_build([prow("t.tr", "parked")], prev_entries=[prev_entry("t.tr", "published", 0)])
        self.assertEqual(by["t.tr"]["status"], "quarantined")

    def test_http_404_and_410_quarantine_immediately(self):
        for code in (404, 410):
            row = prow("t.tr", "dead", reason=f"http {code}")
            row["http"] = code
            by, _, _ = run_build([row], prev_entries=[prev_entry("t.tr", "published", 0)])
            self.assertEqual(by["t.tr"]["status"], "quarantined", code)

    def test_blocked_row_is_unverified_not_failure(self):
        by, _, _ = run_build([prow("t.tr", "blocked")], prev_entries=[prev_entry("t.tr", "published", 1)])
        self.assertEqual(by["t.tr"]["status"], "published")
        self.assertTrue(by["t.tr"]["unverified"])
        self.assertEqual(by["t.tr"]["consecutiveFailures"], 1)


class MultilangScopeTests(unittest.TestCase):
    def _multilang(self, domain, jar_lang="en"):
        s = src(domain, jar=True)
        s["scope"] = "multilang"
        s["formats"]["jar"]["lang"] = jar_lang
        return s

    def test_multilang_lives_only_in_global_bucket(self):
        ml = [f"ml{i}.com" for i in range(3)]
        sources = [self._multilang(d) for d in ml]
        rows = [prow(d, "ok", functional=True) for d in ml]
        with tempfile.TemporaryDirectory() as tmp:
            make_root(tmp, sources + [src(f"f{i}.tr") for i in range(9)],
                      rows + ok_rows([f"f{i}.tr" for i in range(9)]))
            self.assertEqual(build.main(["--root", tmp]), 0)
            tr = {e["id"]: e for e in read_out(tmp, "sources.json")["sources"]}
            glob = {e["id"]: e for e in read_out(tmp, "sources.json", "global")["sources"]}
            global_pub = read_out(tmp, "published.json", "global")
            tr_pub = read_out(tmp, "published.json")
        self.assertNotIn("ml0.com", tr)
        self.assertEqual(glob["ml0.com"]["status"], "published")
        self.assertEqual(glob["ml0.com"]["scope"], "multilang")
        self.assertEqual(glob["f0.tr"]["scope"], "tr_native")
        self.assertEqual({j["domain"] for j in global_pub["jar"]}, set(ml))
        self.assertEqual([j["lang"] for j in global_pub["jar"] if j["domain"] == "ml1.com"], ["en"])
        self.assertNotIn("ml0.com", [j["domain"] for j in tr_pub["jar"]])

    def test_tr_bucket_safety_trips_alone_and_cancels_whole_run(self):
        ml = [f"ok{i}.com" for i in range(10)]
        sources = [self._multilang(d) for d in ml] + [src(f"t{i}.tr") for i in range(5)]
        rows = [prow(d, "ok", functional=True) for d in ml] + \
            [prow("t0.tr", "dead", reason=DNS_REASON), prow("t1.tr", "dead", reason=DNS_REASON),
             prow("t2.tr", "dead", reason=DNS_REASON), prow("t3.tr", "ok", functional=True),
             prow("t4.tr", "ok", functional=True)]
        with tempfile.TemporaryDirectory() as tmp:
            make_root(tmp, sources, rows)
            self.assertEqual(build.main(["--root", tmp]), build.EXIT_CANCEL)
            self.assertFalse(os.path.exists(os.path.join(tmp, "sources", "tr", "sources.json")))
            self.assertFalse(os.path.exists(os.path.join(tmp, "sources", "global", "sources.json")))

    def test_global_bucket_safety_trips_on_multilang_dead_share(self):
        ml = [f"dd{i}.com" for i in range(10)]
        sources = [self._multilang(d) for d in ml] + [src(f"k{i}.tr") for i in range(4)]
        rows = [prow(d, "dead") for d in ml] + ok_rows([f"k{i}.tr" for i in range(4)])
        with tempfile.TemporaryDirectory() as tmp:
            make_root(tmp, sources, rows)
            self.assertEqual(build.main(["--root", tmp]), build.EXIT_CANCEL)

    def test_safety_off_lets_every_bucket_through(self):
        ml = [f"dd{i}.com" for i in range(10)]
        sources = [self._multilang(d) for d in ml] + [src(f"k{i}.tr") for i in range(4)]
        rows = [prow(d, "dead") for d in ml] + ok_rows([f"k{i}.tr" for i in range(4)])
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(os.environ, {"SAFETY_RATIO": "off"}):
            make_root(tmp, sources, rows)
            self.assertEqual(build.main(["--root", tmp]), 0)
            self.assertTrue(os.path.isfile(os.path.join(tmp, "sources", "global", "published.json")))

    def test_multilang_gets_no_tr_report_line(self):
        sources = [self._multilang("ml.com")]
        with tempfile.TemporaryDirectory() as tmp:
            make_root(tmp, sources + [src(f"f{i}.tr") for i in range(9)],
                      [prow("ml.com", "ok", functional=True)] + ok_rows([f"f{i}.tr" for i in range(9)]))
            build.main(["--root", tmp])
            tr_report = _read_text(os.path.join(tmp, "sources", "tr", "REPORT.md"))
            glob_report = _read_text(os.path.join(tmp, "sources", "global", "REPORT.md"))
        self.assertIn("Domain'li toplam kaynak: 9;", tr_report)
        self.assertIn("Domain'li toplam kaynak: 10;", glob_report)
        self.assertNotIn("excluded_multilang", tr_report + glob_report)


class OutputTests(unittest.TestCase):
    def test_mihon_and_jar_sections_list_ok_only(self):
        sources = [src("m.tr", mihon=True, jar=False), src("j.tr", mihon=False, jar=True),
                   src("q.tr", mihon=True, jar=True), src("ok.tr", mihon=False, jar=True)]
        rows = [prow("m.tr", "ok", functional=True), prow("j.tr", "dead"), prow("q.tr", "cf_protected"),
                prow("ok.tr", "ok", functional=True)]
        with tempfile.TemporaryDirectory() as tmp:
            make_root(tmp, sources, rows)
            build.main(["--root", tmp])
            pub = read_out(tmp, "published.json")
        self.assertEqual([m["domain"] for m in pub["mihon"]], ["m.tr"])
        self.assertEqual([j["domain"] for j in pub["jar"]], ["ok.tr"])
        self.assertEqual(set(pub["mihon"][0]), {"pkg", "apkUrl", "version", "domain"})
        self.assertEqual(set(pub["jar"][0]), {"parser", "file", "domain", "lang"})

    def test_report_has_summary_and_change_section(self):
        domains = [f"r{i}.tr" for i in range(10)]
        rows = [prow("r0.tr", "dead", reason=DNS_REASON)] + ok_rows(domains[1:])
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
