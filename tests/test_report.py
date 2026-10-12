"""Unit tests for scripts/report.py. No network is used; files live in a temp dir."""

import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import report  # noqa: E402


def write(path, payload):
    with open(path, "w", encoding="utf-8") as fh:
        if isinstance(payload, str):
            fh.write(payload)
        else:
            json.dump(payload, fh, ensure_ascii=False)


class HelperTests(unittest.TestCase):
    def test_table_escapes_pipes_and_newlines(self):
        lines = report.table(["A", "B"], [("x|y", "l1\nl2")])
        self.assertEqual(lines[2], "| x\\|y | l1 l2 |")

    def test_reason_prefix(self):
        self.assertEqual(report.reason_prefix("dns: Name or service not known"), "dns")
        self.assertEqual(report.reason_prefix("http 503; cloudflare"), "http 503")
        self.assertEqual(report.reason_prefix("http 404"), "http 404")
        self.assertEqual(report.reason_prefix(None), "(boş)")

    def test_report_changes_takes_only_that_section(self):
        text = ("# T\n\n## Özet\n\nx\n\n## Bu run'da değişenler\n\n"
                "- Yeni eklenen: 1 (a.com)\n- Ölen (yayından çıkan): 0\n\nNot: 2 kaynak doğrulanamadı.\n\n"
                "## Alternatifler\n\nyok\n")
        self.assertEqual(report.report_changes(text), [
            "- Yeni eklenen: 1 (a.com)", "- Ölen (yayından çıkan): 0", "Not: 2 kaynak doğrulanamadı."])


class SectionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = self.tmp.name
        self.paths = {
            "PROBE_PATH": os.path.join(self.dir, "probe.json"),
            "SOURCES_PATH": os.path.join(self.dir, "sources.json"),
            "REPORT_PATH": os.path.join(self.dir, "REPORT.md"),
            "ANALYZE_PATH": os.path.join(self.dir, "analyze.json"),
        }
        for name, path in self.paths.items():
            patcher = mock.patch.object(report, name, path)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.addCleanup(self.tmp.cleanup)

    def run_main(self, argv, env=None):
        buf = io.StringIO()
        base = {k: v for k, v in os.environ.items() if k != "GITHUB_STEP_SUMMARY"}
        with mock.patch.dict(os.environ, base, clear=True), contextlib.redirect_stdout(buf):
            os.environ.update(env or {})
            code = report.main(argv)
        self.assertEqual(code, 0)
        return buf.getvalue()

    def test_sync_reports_transitions_alternatives_and_cancel(self):
        write(self.paths["SOURCES_PATH"], {"sources": [
            {"id": "a.com", "name": "A", "status": "quarantined", "reason": "http 404",
             "alternative": {"domain": "a2.com", "how": "moved_to", "confidence": "high"}},
            {"id": "b.com", "name": "B", "status": "published", "reason": "http 200"},
            {"id": "c.com", "name": "C", "status": "cf_protected_published", "unverified": True},
        ]})
        write(self.paths["PROBE_PATH"], {
            "meta": {"counts": {"ok": 1, "cf_protected": 1, "dead": 1, "parked": 0, "other": 0,
                                "blocked": 0}, "unique_domains_probed": 3,
                     "functional": {"true": 1, "false": 0, "null": 2}},
            "results": [{"domain": "a.com", "status": "dead", "reason": "http 404"},
                        {"domain": "x.com", "status": "dead", "reason": "dns: failed"}]})
        write(self.paths["REPORT_PATH"], "# R\n\n## Bu run'da değişenler\n\n- Geri dirilen: 1 (b.com)\n")
        prev = os.path.join(self.dir, "prev.json")
        write(prev, {"sources": [
            {"id": "a.com", "status": "published"},
            {"id": "b.com", "status": "quarantined"},
        ]})

        out = self.run_main(["sync", "--prev-sources", prev],
                            env={"CANCELLED": "true", "SAFETY_RATIO": "40", "DRY_RUN": "false"})

        self.assertIn("## Senkron raporu", out)
        self.assertIn("⛔ **Şalter devreye girdi**", out)
        self.assertIn("| SAFETY_RATIO | 40 |", out)
        self.assertIn("| INCLUDE_MULTILANG | (ayarlı değil) |", out)
        self.assertIn("| unverified | 1 |", out)
        self.assertIn("| dns | 1 |", out)
        self.assertIn("| http 404 | 1 |", out)
        self.assertIn("| a.com | published | quarantined | http 404 |", out)
        self.assertIn("| b.com | quarantined | published |", out)
        self.assertIn("- Geri dirilen: 1 (b.com)", out)
        self.assertIn("| A (a.com) | a2.com | moved_to | high |", out)

    def test_sync_skips_transitions_without_previous_sources(self):
        write(self.paths["SOURCES_PATH"], {"sources": []})
        out = self.run_main(["sync", "--prev-sources", os.path.join(self.dir, "none.json")])
        self.assertNotIn("karantinaya girenler", out)
        self.assertNotIn("⛔", out)
        self.assertIn("probe_results.json okunamadı.", out)

    def test_health_limits_rows_and_names_the_total(self):
        results = [{"domain": f"d{i:03d}.com", "status": "dead", "reason": "http 404",
                    "http": 404, "engine_detected": "unknown"} for i in range(70)]
        results.append({"domain": "ok.com", "status": "ok", "reason": "http 200",
                        "http": 200, "engine_detected": "madara"})
        write(self.paths["PROBE_PATH"], {
            "meta": {"counts": {"ok": 1, "dead": 70}, "engine_detected": {"unknown": 70, "madara": 1},
                     "records_probed": 71, "unique_domains_probed": 71},
            "results": results})
        out = self.run_main(["health"])
        self.assertIn("## Sağlık raporu", out)
        self.assertIn("| madara | 1 |", out)
        self.assertIn("Toplam 70 kayıttan ilk 60 tanesi gösteriliyor.", out)
        self.assertNotIn("ok.com", out)
        table_rows = [line for line in out.splitlines() if line.startswith("| d0")]
        self.assertEqual(len(table_rows), 60)

    def test_add_without_result_says_no_result(self):
        self.assertIn("sonuç yok", self.run_main(["add"]))

    def test_add_dumps_fields(self):
        write(self.paths["ANALYZE_PATH"], {"domain": "x.com", "candidates": [{"name": "X"}]})
        out = self.run_main(["add"])
        self.assertIn("| domain | x.com |", out)
        self.assertIn('| candidates | [{"name": "X"}] |', out)

    def test_step_summary_is_appended_and_printed(self):
        write(self.paths["ANALYZE_PATH"], {"domain": "x.com"})
        summary = os.path.join(self.dir, "summary.md")
        write(summary, "önceki\n")
        out = self.run_main(["add"], env={"GITHUB_STEP_SUMMARY": summary})
        self.assertIn("| domain | x.com |", out)
        with open(summary, encoding="utf-8") as fh:
            text = fh.read()
        self.assertTrue(text.startswith("önceki\n"))
        self.assertIn("| domain | x.com |", text)

    def test_add_has_decision_files_steps_and_upstream_warning(self):
        write(self.paths["ANALYZE_PATH"], {
            "url": "https://dd.com", "domain": "dd.com", "name": "Dd", "status": "ok",
            "engine": "madara", "engine_source": "detected", "functional": True,
            "functional_reason": "madara listing marker found", "lang": "tr", "turkish_ratio": 0.05,
            "title": "Dd", "exists_upstream": True, "upstream_checked": True,
            "upstream_match": {"mihon_pkg": "eu.kanade.tachiyomi.extension.tr.dd", "jar_parser": None,
                               "upstreams": ["mihon"]},
            "scaffold": ["generated/dd.com/mihon/build.gradle.kts"], "registered": True,
            "verdict": "scaffolded", "next_steps": ["Derleme yapılmadı."]})
        out = self.run_main(["add"])
        self.assertIn("## Kaynak ekleme raporu", out)
        self.assertIn("**Karar:** ✅ scaffolded", out)
        self.assertIn("> ⚠️ **Upstream'de zaten var**", out)
        self.assertIn("| Motor | madara (detected) |", out)
        self.assertIn("- `generated/dd.com/mihon/build.gradle.kts`", out)
        self.assertIn("- Derleme yapılmadı.", out)
        self.assertIn("| domain | dd.com |", out)

    def test_unreachable_decision_and_no_warning(self):
        write(self.paths["ANALYZE_PATH"], {"domain": "x.com", "verdict": "unreachable",
                                           "exists_upstream": False, "scaffold": [], "next_steps": []})
        out = self.run_main(["add"])
        self.assertIn("**Karar:** ⛔ unreachable", out)
        self.assertNotIn("Upstream'de zaten var", out)
        self.assertIn("Dosya üretilmedi.", out)
        self.assertIn("Adım yok.", out)


if __name__ == "__main__":
    unittest.main()
