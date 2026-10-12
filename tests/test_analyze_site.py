"""Unit tests for scripts/analyze_site.py. The probe, homepage fetch and functional check are
injected or mocked; no network is used. Files are written to a temp dir."""

import contextlib
import io
import json
import os
import re
import sys
import tempfile
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import analyze_site  # noqa: E402

HOME_HTML = ('<html lang="tr-TR"><head><title> Diamond   Fansub | Manga &amp; Manhwa </title></head>'
             "<body><p>Türkçe okuma sayfası, çok güzel ve şık.</p></body></html>")


def probe_row(**kw):
    row = {"domain": "diamondfansub.com", "status": "ok", "reason": "http 200", "http": 200,
           "engine_detected": "madara", "engine_source": "detected", "functional": True,
           "functional_reason": "madara listing marker found on /manga/", "catalog_engine": None,
           "ms": 10, "attempts": 1}
    row.update(kw)
    return row


def read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = self.tmp.name
        self.addCleanup(self.tmp.cleanup)
        self.paths = {
            "GENERATED_DIR": os.path.join(self.dir, "generated"),
            "CUSTOM_PATH": os.path.join(self.dir, "custom", "sources.json"),
            "RESULT_PATH": os.path.join(self.dir, "data", "analyze_result.json"),
        }
        for name, path in self.paths.items():
            patcher = mock.patch.object(analyze_site, name, path)
            patcher.start()
            self.addCleanup(patcher.stop)

    def analyze(self, row, home=HOME_HTML, upstream=None, **kw):
        fetch = lambda domain: {"status": 200, "text": home, "is_html": True}  # noqa: E731
        kw.setdefault("name", "Diamond Fansub")
        return analyze_site.analyze(
            kw.pop("domain", "diamondfansub.com"), probe_fn=lambda domain: dict(row),
            fetch_fn=fetch, functional_fn=kw.pop("functional_fn", lambda d, e: (True, "forced ok")),
            upstream=upstream if upstream is not None else {"sources": []},
            now="2026-10-12T00:00:00+00:00", **kw)


class UrlAndNameTests(unittest.TestCase):
    def test_domain_is_normalized(self):
        self.assertEqual(analyze_site.domain_from_url("https://www.Diamondfansub.com/manga/x"),
                         "diamondfansub.com")
        self.assertEqual(analyze_site.domain_from_url("gafeland.com"), "gafeland.com")

    def test_bad_urls_are_rejected(self):
        for raw in ("", "ftp://x.com", "localhost", "   "):
            with self.assertRaises(ValueError, msg=raw):
                analyze_site.domain_from_url(raw)

    def test_class_name_is_ascii_pascal_case(self):
        self.assertEqual(analyze_site.class_name("Siyah Melek", "siyahmelek.live"), "SiyahMelek")
        self.assertEqual(analyze_site.class_name("Çiçek Manga", "x.com"), "CicekManga")
        self.assertEqual(analyze_site.class_name("", "gafeland.com"), "Gafeland")
        self.assertEqual(analyze_site.class_name("3sites", "x.com"), "S3sites")

    def test_page_facts_reads_lang_title_and_turkish_ratio(self):
        facts = analyze_site.page_facts(HOME_HTML)
        self.assertEqual(facts["lang"], "tr")
        self.assertEqual(facts["lang_source"], "html")
        self.assertEqual(facts["title"], "Diamond Fansub | Manga & Manhwa")
        self.assertGreater(facts["turkish_ratio"], 0.01)

    def test_page_facts_without_lang_uses_turkish_letters(self):
        facts = analyze_site.page_facts("<html><body>Güzel şöyle öğrenci çiçek</body></html>")
        self.assertEqual((facts["lang"], facts["lang_source"]), ("tr", "text"))
        plain = analyze_site.page_facts("<html><body>plain english words only</body></html>")
        self.assertIsNone(plain["lang"])


class ScaffoldTests(Base):
    def test_madara_ok_scaffolds_mihon_and_jar(self):
        result = self.analyze(probe_row())
        self.assertEqual(result["verdict"], "scaffolded")
        self.assertEqual(result["engine"], "madara")
        self.assertEqual(result["engine_source"], "detected")
        self.assertEqual(result["lang"], "tr")
        self.assertEqual(result["title"], "Diamond Fansub | Manga & Manhwa")
        self.assertEqual(result["scaffold"], [
            "generated/diamondfansub.com/mihon/build.gradle.kts",
            "generated/diamondfansub.com/mihon/src/eu/kanade/tachiyomi/extension/tr/diamondfansub/DiamondFansub.kt",
            "generated/diamondfansub.com/jar/DiamondFansub.kt",
        ])
        gen = self.paths["GENERATED_DIR"]
        gradle = read(os.path.join(gen, "diamondfansub.com", "mihon", "build.gradle.kts"))
        self.assertIn('name = "Diamond Fansub"', gradle)
        self.assertIn('theme = "madara"', gradle)
        self.assertIn('baseUrl = "https://diamondfansub.com"', gradle)
        kt = read(os.path.join(gen, "diamondfansub.com", "mihon", "src", "eu", "kanade", "tachiyomi",
                         "extension", "tr", "diamondfansub", "DiamondFansub.kt"))
        self.assertIn("abstract class DiamondFansub : Madara()", kt)
        jar = read(os.path.join(gen, "diamondfansub.com", "jar", "DiamondFansub.kt"))
        self.assertIn('@MangaSourceParser("DIAMONDFANSUB", "Diamond Fansub", "tr")', jar)
        self.assertIn('MadaraParser(context, MangaParserSource.DIAMONDFANSUB, "diamondfansub.com", 18)', jar)
        for root, _, files in os.walk(gen):
            for fname in files:
                self.assertIsNone(re.search(r"\{\{[A-Z_]+\}\}", read(os.path.join(root, fname))), fname)

    def test_mangathemesia_uses_mangareader_jar_template(self):
        row = probe_row(domain="gafeland.com", engine_detected="mangathemesia")
        result = self.analyze(row, domain="gafeland.com", name="gafeland")
        self.assertEqual(result["verdict"], "scaffolded")
        jar = read(os.path.join(self.paths["GENERATED_DIR"], "gafeland.com", "jar", "Gafeland.kt"))
        self.assertIn("MangaReaderParser(context, MangaParserSource.GAFELAND", jar)
        kt = read(os.path.join(self.paths["GENERATED_DIR"], "gafeland.com", "mihon", "src", "eu", "kanade",
                         "tachiyomi", "extension", "tr", "gafeland", "Gafeland.kt"))
        self.assertIn("abstract class Gafeland : MangaThemesia()", kt)

    def test_initmanga_has_mihon_only(self):
        row = probe_row(domain="siyahmelek.live", engine_detected="initmanga")
        result = self.analyze(row, domain="siyahmelek.live", name="Siyah Melek")
        self.assertEqual(result["verdict"], "scaffolded")
        self.assertEqual(len(result["scaffold"]), 2)
        self.assertTrue(all(not p.endswith("jar/SiyahMelek.kt") for p in result["scaffold"]))
        self.assertTrue(any("jar şablonu yok" in step for step in result["next_steps"]))

    def test_format_mihon_skips_jar(self):
        result = analyze_site.analyze("diamondfansub.com", name="Diamond Fansub", fmt="mihon",
                                      probe_fn=lambda d: probe_row(), fetch_fn=lambda d: {"text": HOME_HTML},
                                      upstream={"sources": []}, now="t")
        self.assertEqual(len(result["scaffold"]), 2)
        self.assertFalse(any("/jar/" in p for p in result["scaffold"]))

    def test_forced_engine_overrides_detection(self):
        row = probe_row(engine_detected="unknown", engine_source=None, functional=None,
                        functional_reason="engine unknown; functional check skipped")
        result = self.analyze(row, engine="mangathemesia",
                              functional_fn=lambda d, e: (True, "mangathemesia listing marker found"))
        self.assertEqual(result["verdict"], "scaffolded")
        self.assertEqual(result["engine"], "mangathemesia")
        self.assertEqual(result["engine_source"], "forced")
        self.assertTrue(result["functional"])

    def test_forced_engine_against_detection_is_noted(self):
        result = self.analyze(probe_row(engine_detected="madara"), engine="initmanga")
        self.assertEqual(result["engine"], "initmanga")
        self.assertTrue(any("Tespit edilen motor 'madara'" in s for s in result["next_steps"]))

    def test_functional_false_scaffolds_but_asks_for_manual_check(self):
        row = probe_row(functional=False, functional_reason="madara listing marker not found on /manga/, /")
        result = self.analyze(row)
        self.assertEqual(result["verdict"], "scaffolded")
        self.assertTrue(any("İşlevsel kontrol başarısız" in s for s in result["next_steps"]))


class VerdictTests(Base):
    def test_unknown_engine_is_unsupported_and_writes_nothing(self):
        row = probe_row(engine_detected="unknown", engine_source=None, functional=None,
                        functional_reason="engine unknown; functional check skipped")
        result = self.analyze(row)
        self.assertEqual(result["verdict"], "unsupported_engine")
        self.assertEqual(result["scaffold"], [])
        self.assertFalse(os.path.exists(self.paths["GENERATED_DIR"]))
        self.assertTrue(any("özel Kotlin kodu gerekir" in s for s in result["next_steps"]))

    def test_custom_engine_is_unsupported(self):
        result = self.analyze(probe_row(), engine="custom")
        self.assertEqual(result["verdict"], "unsupported_engine")
        self.assertEqual(result["scaffold"], [])

    def test_dead_site_is_unreachable(self):
        row = probe_row(status="dead", reason="http 404", http=404, engine_detected="unknown",
                        engine_source=None, functional=None, functional_reason="not checked")
        result = self.analyze(row)
        self.assertEqual(result["verdict"], "unreachable")
        self.assertEqual(result["scaffold"], [])
        self.assertFalse(os.path.exists(self.paths["GENERATED_DIR"]))

    def test_parked_and_blocked_are_unreachable(self):
        for status in ("parked", "blocked", "other"):
            with self.subTest(status=status):
                result = self.analyze(probe_row(status=status, functional=None))
                self.assertEqual(result["verdict"], "unreachable")

    def test_cf_protected_with_known_engine_is_scaffolded(self):
        row = probe_row(status="cf_protected", functional=None,
                        functional_reason="not checked: status cf_protected")
        result = self.analyze(row)
        self.assertEqual(result["verdict"], "scaffolded")


class UpstreamTests(Base):
    UPSTREAM = {"sources": [{
        "key": "diamondfansub", "name": "DiamondFansub", "domain": "diamondfansub.com",
        "altDomains": ["diamond-fansub.com"], "upstreams": ["mihon", "kotatsu"],
        "formats": {"mihon": {"pkg": "eu.kanade.tachiyomi.extension.tr.diamondfansub"},
                    "jar": {"parser": "DIAMONDFANSUB"}}}]}

    def test_existing_upstream_is_reported(self):
        result = self.analyze(probe_row(), upstream=self.UPSTREAM)
        self.assertTrue(result["exists_upstream"])
        self.assertEqual(result["upstream_match"]["mihon_pkg"],
                         "eu.kanade.tachiyomi.extension.tr.diamondfansub")
        self.assertEqual(result["upstream_match"]["jar_parser"], "DIAMONDFANSUB")
        self.assertTrue(any("Upstream'de zaten var" in s for s in result["next_steps"]))

    def test_alt_domain_also_matches(self):
        result = self.analyze(probe_row(), domain="diamond-fansub.com", upstream=self.UPSTREAM,
                              name="x")
        self.assertTrue(result["exists_upstream"])

    def test_missing_upstream_file_is_noted(self):
        with mock.patch.object(analyze_site, "_load_upstream", return_value=None):
            result = analyze_site.analyze("new.com", probe_fn=lambda d: probe_row(domain="new.com"),
                                          fetch_fn=lambda d: {"text": HOME_HTML},
                                          functional_fn=lambda d, e: (True, "ok"), now="t")
        self.assertFalse(result["exists_upstream"])
        self.assertFalse(result["upstream_checked"])
        self.assertTrue(any("upstream karşılaştırması yapılmadı" in s for s in result["next_steps"]))


class RegisterTests(Base):
    def test_scaffolded_is_registered_and_upserted(self):
        self.analyze(probe_row(), register=1)
        first = self.analyze(probe_row(), register=1)
        self.assertTrue(first["registered"])
        with open(self.paths["CUSTOM_PATH"], encoding="utf-8") as fh:
            entries = json.load(fh)
        self.assertEqual(len(entries), 1)
        entry = entries[0]
        self.assertEqual(entry["id"], "diamondfansub.com")
        self.assertEqual(entry["scope"], "tr_native")
        self.assertEqual(entry["verdict"], "scaffolded")
        self.assertEqual(entry["addedAt"], "2026-10-12T00:00:00+00:00")
        self.assertEqual(entry["engine"], "madara")

    def test_unsupported_is_registered_without_scaffold(self):
        self.analyze(probe_row(engine_detected="unknown", engine_source=None, functional=None),
                     register=1)
        with open(self.paths["CUSTOM_PATH"], encoding="utf-8") as fh:
            entry = json.load(fh)[0]
        self.assertEqual(entry["verdict"], "unsupported_engine")
        self.assertEqual(entry["scaffold"], [])

    def test_unreachable_is_not_registered(self):
        result = self.analyze(probe_row(status="dead", http=404, functional=None), register=1)
        self.assertFalse(result["registered"])
        self.assertFalse(os.path.exists(self.paths["CUSTOM_PATH"]))

    def test_register_zero_writes_nothing(self):
        self.analyze(probe_row(), register=0)
        self.assertFalse(os.path.exists(self.paths["CUSTOM_PATH"]))


class MainTests(Base):
    def run_main(self, argv, row=None, home=HOME_HTML):
        buf = io.StringIO()
        with mock.patch.object(analyze_site, "probe_site", lambda d: dict(row or probe_row())), \
                mock.patch.object(analyze_site, "fetch_home", lambda d: {"text": home}), \
                mock.patch.object(analyze_site, "forced_functional", lambda d, e: (True, "ok")), \
                mock.patch.object(analyze_site, "_load_upstream", return_value={"sources": []}), \
                contextlib.redirect_stdout(buf):
            code = analyze_site.main(argv)
        return code, buf.getvalue()

    def test_writes_result_json_with_contract_fields(self):
        code, out = self.run_main(["--url", "https://www.diamondfansub.com/", "--name", "Diamond Fansub"])
        self.assertEqual(code, 0)
        self.assertIn("verdict=scaffolded", out)
        with open(self.paths["RESULT_PATH"], encoding="utf-8") as fh:
            data = json.load(fh)
        for key in ("url", "domain", "status", "engine", "engine_source", "functional",
                    "functional_reason", "lang", "turkish_ratio", "title", "exists_upstream",
                    "scaffold", "verdict", "next_steps"):
            self.assertIn(key, data)
        self.assertEqual(data["domain"], "diamondfansub.com")

    def test_invalid_url_exits_1_and_writes_nothing(self):
        buf = io.StringIO()
        with contextlib.redirect_stderr(buf):
            code = analyze_site.main(["--url", "ftp://nope.com"])
        self.assertEqual(code, 1)
        self.assertFalse(os.path.exists(self.paths["RESULT_PATH"]))

    def test_register_flag_is_validated(self):
        with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
            analyze_site.main(["--url", "x.com", "--register", "2"])


if __name__ == "__main__":
    unittest.main()
