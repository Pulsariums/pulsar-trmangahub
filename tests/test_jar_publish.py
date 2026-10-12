"""Unit tests for scripts/jar_publish.py. No network is used; files live in a temp dir."""

import contextlib
import hashlib
import io
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import jar_publish  # noqa: E402


def write_json(path, payload):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False)


class JarPublishTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = self.tmp.name
        self.upstream = os.path.join(self.dir, "upstream")
        os.makedirs(self.upstream)
        self.prepare = os.path.join(self.dir, "jar_prepare.json")
        self.repo = os.path.join(self.dir, "jar")
        self.info = os.path.join(self.repo, "state", "tr.build_info.json")
        self.sources = os.path.join(self.dir, "sources.json")
        self.out_file = os.path.join(self.dir, "github_output")
        self.jar = os.path.join(self.dir, "plugin.jar")
        with open(self.jar, "wb") as fh:
            fh.write(b"JARBYTES")
        self.set_prepare(commit="c1", kept=["TRTWO", "TRONE"],
                         patched=[{"id": "TRTHREE", "old": "oldthree.tr", "new": "newthree.tr",
                                   "confidence": "high"}])
        write_json(self.sources, {"sources": [
            {"id": "one.tr", "name": "One", "domain": "one.tr", "nsfw": False, "status": "published",
             "formats": {"jar": {"parser": "TRONE"}}},
            {"id": "two.tr", "name": "Two", "domain": "two.tr", "nsfw": True, "status": "quarantined",
             "formats": {"jar": {"parser": "TRTWO"}}},
        ]})

    def set_prepare(self, commit, kept, patched, include_unverified=False):
        write_json(self.prepare, {"upstream_commit": commit, "kept_ids": kept, "patched_domains": patched,
                                  "include_unverified": include_unverified, "counts": {"kept": len(kept)}})

    def run_main(self, argv, env=None):
        buf = io.StringIO()
        base = {k: v for k, v in os.environ.items() if k != "GITHUB_OUTPUT"}
        with mock.patch.dict(os.environ, base, clear=True), contextlib.redirect_stdout(buf):
            os.environ.update(env or {})
            code = jar_publish.main(argv)
        self.assertEqual(code, 0)
        return buf.getvalue()

    def decide(self, force="0", env=None):
        argv = ["decide", "--upstream", self.upstream, "--prepare", self.prepare,
                "--info", self.info, "--force", force]
        return self.run_main(argv, env)

    def index(self, run=12, fallback="0", bucket="tr", prepare=None, sources=None):
        return self.run_main(["index", "--bucket", bucket, "--prepare", prepare or self.prepare,
                              "--jar", self.jar, "--out", self.repo,
                              "--run-number", str(run), "--fallback", fallback,
                              "--sources", sources or self.sources], {"GITHUB_REPOSITORY": "owner/name"})

    def read_index(self):
        with open(os.path.join(self.repo, "index.min.json"), encoding="utf-8") as fh:
            return json.load(fh)

    def test_decide_first_build_without_info(self):
        out = self.decide()
        self.assertIn("build=true", out)
        self.assertIn("reason=ilk derleme (build_info yok)", out)

    def test_decide_same_fingerprint_skips(self):
        self.index()
        out = self.decide()
        self.assertIn("build=false", out)
        self.assertIn("parmak izi aynı", out)

    def test_decide_force_builds_even_when_same(self):
        self.index()
        out = self.decide(force="1")
        self.assertIn("build=true", out)
        self.assertIn("zorunlu (force)", out)

    def test_decide_different_commit_builds(self):
        self.index()
        self.set_prepare(commit="c2", kept=["TRTWO", "TRONE"],
                         patched=[{"id": "TRTHREE", "old": "oldthree.tr", "new": "newthree.tr",
                                   "confidence": "high"}])
        out = self.decide()
        self.assertIn("build=true", out)
        self.assertIn("parmak izi değişti", out)

    def test_decide_changed_kept_or_domain_builds(self):
        self.index()
        self.set_prepare(commit="c1", kept=["TRONE"], patched=[])
        self.assertIn("build=true", self.decide())

    def test_decide_writes_github_output(self):
        self.decide(env={"GITHUB_OUTPUT": self.out_file})
        with open(self.out_file, encoding="utf-8") as fh:
            text = fh.read()
        self.assertIn("build=true\n", text)
        self.assertIn("reason=ilk derleme (build_info yok)\n", text)

    def test_index_writes_expected_layout(self):
        self.index(run=12, fallback="1")
        self.assertTrue(os.path.isfile(os.path.join(self.repo, "apk", "tr.jar")))
        self.assertFalse(os.path.exists(os.path.join(self.repo, "apk", "plugin.jar")))
        self.assertFalse(os.path.exists(os.path.join(self.repo, "README.md")))
        index = self.read_index()
        self.assertEqual(len(index), 1)
        entry = index[0]
        self.assertEqual(entry["pkg"], "org.pulsarium.trmangahub")
        self.assertEqual(entry["name"], "Pulsar TR Manga Hub")
        self.assertEqual(entry["version"], "1.0.12")
        self.assertIsInstance(entry["code"], int)
        self.assertEqual(entry["code"], 12)
        self.assertEqual(entry["apk"], "tr.jar")
        self.assertEqual(entry["lang"], "tr")
        self.assertEqual(entry["nsfw"], 0)
        self.assertEqual(entry["sources"], [{"name": "One", "id": "TRONE", "lang": "tr"}])
        with open(os.path.join(self.repo, "state", "tr.entry.json"), encoding="utf-8") as fh:
            self.assertEqual(json.load(fh), entry)

    def test_index_lists_failing_source_only_with_include_unverified(self):
        write_json(self.sources, {"sources": [
            {"id": "one.tr", "name": "One", "domain": "one.tr", "nsfw": False, "status": "published",
             "formats": {"jar": {"parser": "TRONE"}}},
            {"id": "two.tr", "name": "Two", "domain": "two.tr", "nsfw": True, "status": "failing",
             "failing": True, "formats": {"jar": {"parser": "TRTWO"}}},
        ]})
        self.set_prepare(commit="c1", kept=["TRTWO", "TRONE"], patched=[], include_unverified=True)
        self.index()
        entry = self.read_index()[0]
        self.assertEqual([s["id"] for s in entry["sources"]], ["TRONE", "TRTWO"])

    def test_index_nsfw_zero_without_nsfw_sources(self):
        self.set_prepare(commit="c1", kept=["TRONE"], patched=[])
        self.index()
        self.assertEqual(self.read_index()[0]["nsfw"], 0)

    def test_index_uses_fixed_nsfw_value_of_package(self):
        write_json(self.sources, {"sources": [
            {"id": "two.tr", "name": "Two", "domain": "two.tr", "nsfw": True, "status": "published",
             "formats": {"jar": {"parser": "TRTWO"}}},
        ]})
        self.set_prepare(commit="c1", kept=["TRTWO"], patched=[])
        self.index(bucket="tr_nsfw")
        entry = self.read_index()[0]
        self.assertEqual(entry["nsfw"], 1)
        self.assertEqual(entry["pkg"], "org.pulsarium.trmangahub.trnsfw")
        self.assertEqual(entry["name"], "Pulsar TR Manga Hub (NSFW)")
        self.assertEqual(entry["apk"], "tr-nsfw.jar")
        self.assertTrue(os.path.isfile(os.path.join(self.repo, "apk", "tr-nsfw.jar")))

    def test_index_build_info_matches_decide_fingerprint(self):
        self.index(run=5, fallback="0")
        with open(self.info, encoding="utf-8") as fh:
            info = json.load(fh)
        with open(os.path.join(self.repo, "apk", "tr.jar"), "rb") as fh:
            data = fh.read()
        self.assertEqual(info["jarSha256"], hashlib.sha256(data).hexdigest())
        self.assertEqual(info["jarBytes"], len(data))
        self.assertEqual(info["keptCount"], 2)
        self.assertEqual(info["fallback"], 0)
        self.assertEqual(info["runNumber"], 5)
        self.assertEqual(info["upstream_commit"], "c1")
        self.assertEqual(info["bucket"], "tr")
        self.assertTrue(info["builtAt"].endswith("Z"))
        self.assertEqual(len(info["patchedDomains"]), 1)
        self.assertIn("jarSha256", info)
        self.assertIn("fingerprint", info)
        self.assertIn("build=false", self.decide())

    def test_global_index_uses_all_and_per_source_lang(self):
        write_json(self.sources, {"sources": [
            {"id": "one.tr", "name": "One", "domain": "one.tr", "nsfw": False, "status": "published",
             "scope": "tr_native", "formats": {"jar": {"parser": "TRONE", "lang": "tr"}}},
            {"id": "en.com", "name": "English", "domain": "en.com", "nsfw": False, "status": "published",
             "scope": "multilang", "formats": {"jar": {"parser": "ENONE", "lang": "en"}}},
            {"id": "multi.com", "name": "Multi", "domain": "multi.com", "nsfw": False,
             "status": "cf_protected_published", "scope": "multilang",
             "formats": {"jar": {"parser": "MULTI", "lang": "ru"}}},
        ]})
        write_json(self.prepare, {"upstream_commit": "c1", "kept_ids": ["ENONE", "TRONE"],
                                  "patched_domains": [], "include_unverified": False,
                                  "langs": {"ENONE": "en", "TRONE": "tr"}, "counts": {}})
        self.index(bucket="global")
        entry = self.read_index()[0]
        self.assertEqual(entry["lang"], "all")
        self.assertEqual(entry["pkg"], "org.pulsarium.trmangahub.global")
        self.assertEqual(entry["name"], "Pulsar Global Manga Hub")
        self.assertEqual(entry["apk"], "global.jar")
        self.assertEqual(entry["sources"], [{"name": "English", "id": "ENONE", "lang": "en"}])

    def test_global_index_drops_turkish_sources(self):
        write_json(self.prepare, {"upstream_commit": "c1", "kept_ids": ["TRONE", "XX"],
                                  "patched_domains": [], "include_unverified": False,
                                  "langs": {"TRONE": "tr", "XX": "de"},
                                  "extra_sources": [{"id": "XX", "name": "Deutsch", "lang": "de",
                                                     "nsfw": False, "domain": "xx.de"}],
                                  "counts": {}})
        self.index(bucket="global")
        entry = self.read_index()[0]
        self.assertEqual(entry["sources"], [{"name": "Deutsch", "id": "XX", "lang": "de"}])

    def test_tr_index_drops_non_turkish_sources(self):
        write_json(self.prepare, {"upstream_commit": "c1", "kept_ids": ["TRONE", "XX"],
                                  "patched_domains": [], "include_unverified": False,
                                  "langs": {"TRONE": "tr", "XX": "de"},
                                  "extra_sources": [{"id": "XX", "name": "Deutsch", "lang": "de",
                                                     "nsfw": False, "domain": "xx.de"}],
                                  "counts": {}})
        self.index(bucket="tr")
        entry = self.read_index()[0]
        self.assertEqual(entry["sources"], [{"name": "One", "id": "TRONE", "lang": "tr"}])

    def test_global_index_drops_unverified_multilang_by_default(self):
        write_json(self.sources, {"sources": [
            {"id": "en.com", "name": "English", "domain": "en.com", "nsfw": False, "status": "failing",
             "failing": True, "scope": "multilang", "formats": {"jar": {"parser": "ENONE", "lang": "en"}}},
        ]})
        write_json(self.prepare, {"upstream_commit": "c1", "kept_ids": ["ENONE"], "patched_domains": [],
                                  "include_unverified": False, "langs": {"ENONE": "en"}, "counts": {}})
        self.index(bucket="global")
        self.assertEqual(self.read_index(), [])

    def test_empty_bucket_writes_null_state_and_no_jar(self):
        write_json(self.prepare, {"upstream_commit": "c1", "kept_ids": [], "patched_domains": [],
                                  "include_unverified": False, "langs": {}, "extra_sources": [],
                                  "counts": {}})
        missing_jar = os.path.join(self.dir, "missing.jar")
        self.run_main(["index", "--bucket", "tr", "--prepare", self.prepare, "--jar", missing_jar,
                       "--out", self.repo, "--run-number", "3", "--fallback", "0",
                       "--sources", self.sources], {"GITHUB_REPOSITORY": "owner/name"})
        with open(os.path.join(self.repo, "state", "tr.entry.json"), encoding="utf-8") as fh:
            self.assertEqual(fh.read().strip(), "null")
        with open(os.path.join(self.repo, "index.min.json"), encoding="utf-8") as fh:
            self.assertEqual(fh.read().strip(), "[]")
        self.assertFalse(os.path.exists(os.path.join(self.repo, "apk", "tr.jar")))

    def test_empty_bucket_removes_its_previous_jar(self):
        self.index()
        self.assertTrue(os.path.isfile(os.path.join(self.repo, "apk", "tr.jar")))
        write_json(self.prepare, {"upstream_commit": "c2", "kept_ids": [], "patched_domains": [],
                                  "include_unverified": False, "langs": {}, "extra_sources": [],
                                  "counts": {}})
        self.index()
        self.assertFalse(os.path.exists(os.path.join(self.repo, "apk", "tr.jar")))
        self.assertEqual(self.read_index(), [])

    def test_extra_sources_are_published_in_tr_package(self):
        write_json(self.prepare, {"upstream_commit": "c1", "kept_ids": ["CUSTOMONE"], "patched_domains": [],
                                  "include_unverified": False, "langs": {"CUSTOMONE": "tr"},
                                  "extra_sources": [{"id": "CUSTOMONE", "name": "Ozel Site", "lang": "tr",
                                                     "nsfw": False, "domain": "ozel.tr",
                                                     "file": "src/x/CustomOne.kt"}],
                                  "counts": {}})
        self.index(bucket="tr")
        entry = self.read_index()[0]
        self.assertEqual(entry["pkg"], "org.pulsarium.trmangahub")
        self.assertEqual(entry["sources"], [{"name": "Ozel Site", "id": "CUSTOMONE", "lang": "tr"}])
        self.assertTrue(os.path.isfile(os.path.join(self.repo, "apk", "tr.jar")))

    def test_merge_index_keeps_fixed_order_and_skips_null_or_missing(self):
        state = os.path.join(self.repo, "state")
        write_json(os.path.join(state, "global_nsfw.entry.json"), {"name": "GN"})
        write_json(os.path.join(state, "tr.entry.json"), {"name": "TR"})
        write_json(os.path.join(state, "tr_nsfw.entry.json"), None)
        write_json(os.path.join(state, "global.entry.json"), {"name": "G"})
        self.run_main(["merge-index", "--out", self.repo])
        with open(os.path.join(self.repo, "index.min.json"), encoding="utf-8") as fh:
            text = fh.read()
        self.assertEqual(json.loads(text), [{"name": "TR"}, {"name": "G"}, {"name": "GN"}])
        self.assertIn('[{"name":"TR"},{"name":"G"},{"name":"GN"}]', text)

    def test_merge_index_with_no_states_writes_empty_array(self):
        self.run_main(["merge-index", "--out", self.repo])
        with open(os.path.join(self.repo, "index.min.json"), encoding="utf-8") as fh:
            self.assertEqual(fh.read().strip(), "[]")

    def test_index_merges_all_packages_in_order(self):
        self.index(bucket="global_nsfw")
        self.index(bucket="tr")
        self.assertEqual([e["pkg"] for e in self.read_index()],
                         ["org.pulsarium.trmangahub", "org.pulsarium.trmangahub.globalnsfw"])

    def test_readme_command_writes_single_readme_with_repo_url(self):
        out_dir = os.path.join(self.dir, "jar-readme")
        with mock.patch.dict(os.environ, {"GITHUB_REPOSITORY": "owner/name"}, clear=False):
            self.run_main(["readme", "--out", out_dir])
        with open(os.path.join(out_dir, "README.md"), encoding="utf-8") as fh:
            text = fh.read()
        self.assertIn("https://raw.githubusercontent.com/owner/name/main/jar", text)
        for name in ("`tr`", "`tr_nsfw`", "`global`", "`global_nsfw`"):
            self.assertIn(name, text)
        self.assertEqual(os.listdir(out_dir), ["README.md"])

    def test_fingerprint_is_order_independent(self):
        a = jar_publish.fingerprint("c", ["B", "A"], [{"old": "x", "new": "y"}, {"old": "a", "new": "b"}])
        b = jar_publish.fingerprint("c", ["A", "B"], [{"old": "a", "new": "b"}, {"old": "x", "new": "y"}])
        self.assertEqual(a, b)
        self.assertNotEqual(a, jar_publish.fingerprint("d", ["A", "B"], []))


if __name__ == "__main__":
    unittest.main()
