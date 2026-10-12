"""Unit tests for scripts/jar_prepare.py against a fake upstream tree. No network is used."""

import json
import os
import shutil
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import jar_prepare  # noqa: E402

P = os.path.join("src", "main", "kotlin", "org", "koitharu", "kotatsu", "parsers")
SITE = os.path.join("src", "main", "kotlin", "org", "koitharu", "kotatsu", "parsers", "site")

FILES = {
    os.path.join(P, "MangaParser.kt"):
        "interface MangaParser {\n\tpublic val source: MangaParserSource\n}\n",
    os.path.join(P, "Broken.kt"):
        "@Retention(AnnotationRetention.SOURCE)\ninternal annotation class Broken(val reason: String)\n",
    os.path.join(P, "MangaSourceParser.kt"):
        "@Retention(AnnotationRetention.SOURCE)\n"
        "internal annotation class MangaSourceParser(val id: String, val title: String, val locale: String)\n",
    os.path.join(SITE, "madara", "MadaraParser.kt"):
        "abstract class MadaraParser(val domain: String)\n",
    os.path.join(SITE, "en", "EnBase.kt"):
        '@MangaSourceParser("ENBASE", "EnBase", "en")\nabstract class EnBase : MadaraParser("enbase.com")\n',
    os.path.join(SITE, "en", "EnOne.kt"):
        '@MangaSourceParser("ENONE", "EnOne", "en")\nclass EnOne : MadaraParser("enone.com")\n',
    os.path.join(SITE, "madara", "tr", "TrOne.kt"):
        '@MangaSourceParser("TRONE", "TrOne", "tr")\nclass TrOne : EnBase()\n',
    os.path.join(SITE, "madara", "tr", "TrTwo.kt"):
        '@MangaSourceParser("TRTWO", "TrTwo", "tr")\nclass TrTwo : MadaraParser("trtwo.com")\n',
    os.path.join(SITE, "madara", "tr", "TrThree.kt"):
        '@MangaSourceParser("TRTHREE", "TrThree", "tr")\n'
        'class TrThree : MadaraParser("oldthree.tr")\n',
    os.path.join(SITE, "madara", "tr", "TrLow.kt"):
        '@MangaSourceParser("TRLOW", "TrLow", "tr")\nclass TrLow : MadaraParser("lowold.tr")\n',
    os.path.join(SITE, "madara", "tr", "TrNoLit.kt"):
        '@MangaSourceParser("TRNOLIT", "TrNoLit", "tr")\nclass TrNoLit : MadaraParser("other.tr")\n',
    os.path.join(SITE, "tr", "MangaBall.kt"):
        '@MangaSourceParser("MANGABALL", "MangaBall", "tr")\n'
        '@MangaSourceParser("MANGABALLEN", "MangaBallEn", "en")\n'
        "internal class MangaBall : MadaraParser(\"mangaball.tr\")\n",
    os.path.join(SITE, "tr", "TrAnnBroken.kt"):
        '@Broken("cloudflare")\n@MangaSourceParser("TRANNBROKEN", "TrAnnBroken", "tr")\n'
        "class TrAnnBroken : MadaraParser(\"annbroken.tr\")\n",
    os.path.join(SITE, "tr", "TrSrcBroken.kt"):
        '@MangaSourceParser("TRSRCBROKEN", "TrSrcBroken", "tr")\n'
        "class TrSrcBroken : MadaraParser(\"srcbroken.tr\")\n",
}


def source(sid, parser, status, scope="tr_native", broken=False, failing=None, alt=None, domain=None):
    entry = {
        "id": domain or f"{sid}.tr",
        "name": sid,
        "domain": domain or f"{sid}.tr",
        "scope": scope,
        "status": status,
        "formats": {"mihon": None, "jar": {"parser": parser, "file": "x.kt", "broken": broken},
                    "catalog": None},
    }
    if failing is not None:
        entry["failing"] = failing
    if alt is not None:
        entry["alternative"] = alt
    return entry


SOURCES = [
    source("trone", "TRONE", "published"),
    source("trtwo", "TRTWO", "quarantined"),
    source("trthree", "TRTHREE", "quarantined", domain="oldthree.tr",
           alt={"domain": "newthree.tr", "how": "same_key", "confidence": "high"}),
    source("trlow", "TRLOW", "quarantined", domain="lowold.tr",
           alt={"domain": "lownew.tr", "how": "similar_key", "confidence": "low"}),
    source("trnolit", "TRNOLIT", "quarantined", domain="nolit.tr",
           alt={"domain": "nolitnew.tr", "how": "same_key", "confidence": "high"}),
    source("mangaball", "MANGABALL", "published"),
    source("trannbroken", "TRANNBROKEN", "published"),
    source("trsrcbroken", "TRSRCBROKEN", "published", broken=True),
    source("enone", "ENONE", "published", scope="multilang"),
    source("trfailing", "TRFAILING", "failing", failing=True),
]


class JarPrepareTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = self.tmp.name
        self.upstream = os.path.join(self.root, "upstream")
        self.sources = os.path.join(self.root, "sources.json")
        self.report = os.path.join(self.root, "report.json")
        self.write_upstream(FILES)
        self.write_sources(SOURCES)

    def write_upstream(self, files):
        if os.path.isdir(self.upstream):
            shutil.rmtree(self.upstream)
        for rel, text in files.items():
            path = os.path.join(self.upstream, rel)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(text)

    def write_sources(self, entries):
        with open(self.sources, "w", encoding="utf-8") as fh:
            json.dump({"sources": entries}, fh)

    def run_prepare(self, *extra):
        args = ["--upstream", self.upstream, "--sources", self.sources,
                "--report", self.report, *extra]
        self.assertEqual(jar_prepare.main(args), 0)
        with open(self.report, encoding="utf-8") as fh:
            return json.load(fh)

    def read(self, rel):
        with open(os.path.join(self.upstream, rel), encoding="utf-8") as fh:
            return fh.read()

    def exists(self, rel):
        return os.path.exists(os.path.join(self.upstream, rel))

    def test_patches_apply_once(self):
        self.run_prepare()
        self.assertIn("public val source: MangaSource\n", self.read(os.path.join(P, "MangaParser.kt")))
        broken = self.read(os.path.join(P, "Broken.kt"))
        self.assertIn("AnnotationRetention.RUNTIME", broken)
        self.assertIn("public annotation class Broken", broken)
        parser_ann = self.read(os.path.join(P, "MangaSourceParser.kt"))
        self.assertIn("AnnotationRetention.RUNTIME", parser_ann)
        self.assertIn("public annotation class MangaSourceParser", parser_ann)

    def test_missing_patch_target_exits_2(self):
        self.write_upstream({k: v for k, v in FILES.items() if not k.endswith("MangaSourceParser.kt")})
        with self.assertRaises(SystemExit) as cm:
            self.run_prepare()
        self.assertEqual(cm.exception.code, 2)

    def test_patch_literal_not_unique_exits_2(self):
        files = dict(FILES)
        files[os.path.join(P, "MangaParser.kt")] = (
            "\tpublic val source: MangaParserSource\n\tpublic val source: MangaParserSource\n")
        self.write_upstream(files)
        with self.assertRaises(SystemExit) as cm:
            self.run_prepare()
        self.assertEqual(cm.exception.code, 2)

    def test_alive_removes_quarantined_and_keeps_published(self):
        report = self.run_prepare()
        self.assertIn("TRONE", report["kept_ids"])
        self.assertIn("TRTWO", report["removed_ids"])
        self.assertFalse(self.exists(os.path.join(SITE, "madara", "tr", "TrTwo.kt")))
        self.assertTrue(self.exists(os.path.join(SITE, "madara", "tr", "TrOne.kt")))
        self.assertFalse(self.exists(os.path.join(SITE, "en", "EnOne.kt")))

    def test_alive_keeps_failing_flagged_source(self):
        self.write_upstream({**FILES, os.path.join(SITE, "madara", "tr", "TrFailing.kt"):
                             '@MangaSourceParser("TRFAILING", "TrFailing", "tr")\nclass TrFailing\n'})
        report = self.run_prepare()
        self.assertIn("TRFAILING", report["kept_ids"])

    def test_dependency_closure_rescues_base_class(self):
        report = self.run_prepare()
        self.assertTrue(self.exists(os.path.join(SITE, "en", "EnBase.kt")))
        self.assertIn(os.path.join(SITE, "en", "EnBase.kt").replace(os.sep, "/"), report["rescued_files"])
        self.assertTrue(self.exists(os.path.join(SITE, "madara", "MadaraParser.kt")))

    def test_rescue_is_transitive(self):
        self.write_upstream({**FILES,
                             os.path.join(SITE, "en", "Helper.kt"):
                                 '@MangaSourceParser("ENHELP", "EnHelp", "en")\nclass EnHelper\n',
                             os.path.join(SITE, "en", "EnBase.kt"):
                                 '@MangaSourceParser("ENBASE", "EnBase", "en")\n'
                                 "abstract class EnBase : EnHelper()\n"})
        report = self.run_prepare()
        self.assertTrue(self.exists(os.path.join(SITE, "en", "Helper.kt")))
        self.assertIn(os.path.join(SITE, "en", "Helper.kt").replace(os.sep, "/"), report["rescued_files"])

    def test_multi_annotation_file_is_kept(self):
        report = self.run_prepare()
        self.assertTrue(self.exists(os.path.join(SITE, "tr", "MangaBall.kt")))
        self.assertIn("MANGABALL", report["kept_ids"])
        self.assertIn("MANGABALLEN", report["removed_ids"])

    def test_domain_patch_high_is_applied(self):
        report = self.run_prepare()
        text = self.read(os.path.join(SITE, "madara", "tr", "TrThree.kt"))
        self.assertIn('"newthree.tr"', text)
        self.assertNotIn("oldthree.tr", text)
        self.assertEqual(report["patched_domains"],
                         [{"id": "TRTHREE", "old": "oldthree.tr", "new": "newthree.tr",
                           "confidence": "high"}])
        self.assertIn("TRTHREE", report["kept_ids"])

    def test_domain_patch_low_is_not_applied(self):
        report = self.run_prepare()
        self.assertFalse(self.exists(os.path.join(SITE, "madara", "tr", "TrLow.kt")))
        self.assertNotIn("TRLOW", [p["id"] for p in report["patched_domains"]])
        self.assertNotIn("TRLOW", [p["id"] for p in report["patch_failed"]])

    def test_domain_patch_medium_needs_high_medium(self):
        self.write_sources([s if s["formats"]["jar"]["parser"] != "TRTHREE" else
                            source("trthree", "TRTHREE", "quarantined", domain="oldthree.tr",
                                   alt={"domain": "newthree.tr", "how": "same_key",
                                        "confidence": "medium"})
                            for s in SOURCES])
        report = self.run_prepare("--apply-alternatives", "high")
        self.assertNotIn("TRTHREE", report["kept_ids"])
        self.write_upstream(FILES)
        self.write_sources([s if s["formats"]["jar"]["parser"] != "TRTHREE" else
                            source("trthree", "TRTHREE", "quarantined", domain="oldthree.tr",
                                   alt={"domain": "newthree.tr", "how": "same_key",
                                        "confidence": "medium"})
                            for s in SOURCES])
        report = self.run_prepare("--apply-alternatives", "high_medium")
        self.assertIn("TRTHREE", report["kept_ids"])

    def test_alternatives_off_disables_patching(self):
        report = self.run_prepare("--apply-alternatives", "off")
        self.assertEqual(report["patched_domains"], [])
        self.assertNotIn("TRTHREE", report["kept_ids"])
        self.assertFalse(self.exists(os.path.join(SITE, "madara", "tr", "TrThree.kt")))

    def test_missing_literal_is_patch_failed(self):
        report = self.run_prepare()
        self.assertEqual([p["id"] for p in report["patch_failed"]], ["TRNOLIT"])
        self.assertNotIn("TRNOLIT", report["kept_ids"])
        self.assertFalse(self.exists(os.path.join(SITE, "madara", "tr", "TrNoLit.kt")))

    def test_broken_rule_from_sources_and_annotation(self):
        report = self.run_prepare()
        self.assertNotIn("TRSRCBROKEN", report["kept_ids"])
        self.assertNotIn("TRANNBROKEN", report["kept_ids"])
        self.write_upstream(FILES)
        report = self.run_prepare("--include-broken", "1")
        self.assertIn("TRSRCBROKEN", report["kept_ids"])
        self.assertIn("TRANNBROKEN", report["kept_ids"])

    def test_all_tr_keeps_every_tr_locale_parser(self):
        report = self.run_prepare("--mode", "all_tr")
        self.assertIn("TRTWO", report["kept_ids"])
        self.assertIn("TRLOW", report["kept_ids"])
        self.assertNotIn("ENONE", report["kept_ids"])
        self.assertNotIn("ENBASE", report["kept_ids"])
        self.assertTrue(self.exists(os.path.join(SITE, "madara", "tr", "TrTwo.kt")))

    def test_patch_only_applies_patches_and_nothing_else(self):
        self.assertEqual(jar_prepare.main(["--upstream", self.upstream, "--patch-only"]), 0)
        self.assertIn("public val source: MangaSource\n", self.read(os.path.join(P, "MangaParser.kt")))
        self.assertIn("public annotation class Broken", self.read(os.path.join(P, "Broken.kt")))
        self.assertTrue(self.exists(os.path.join(SITE, "madara", "tr", "TrTwo.kt")))
        self.assertTrue(self.exists(os.path.join(SITE, "en", "EnOne.kt")))
        self.assertIn("oldthree.tr", self.read(os.path.join(SITE, "madara", "tr", "TrThree.kt")))
        self.assertTrue(self.exists(os.path.join(SITE, "madara", "tr", "TrNoLit.kt")))
        self.assertFalse(os.path.exists(self.report))

    def test_patch_only_fails_on_missing_patch_target(self):
        self.write_upstream({k: v for k, v in FILES.items() if not k.endswith("Broken.kt")})
        with self.assertRaises(SystemExit) as cm:
            jar_prepare.main(["--upstream", self.upstream, "--patch-only"])
        self.assertEqual(cm.exception.code, 2)

    def test_report_counts(self):
        report = self.run_prepare()
        counts = report["counts"]
        self.assertEqual(counts["patches"], 5)
        self.assertEqual(counts["patched_domains"], 1)
        self.assertEqual(counts["patch_failed"], 1)
        self.assertEqual(counts["deleted_files"], 6)
        self.assertEqual(counts["rescued_files"], 1)
        self.assertIn("upstream_commit", report)
        self.assertEqual(report["mode"], "alive")


if __name__ == "__main__":
    unittest.main(verbosity=2)
