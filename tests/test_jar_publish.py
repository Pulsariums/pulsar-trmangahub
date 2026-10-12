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
        self.info = os.path.join(self.dir, "repo", "build_info.json")
        self.sources = os.path.join(self.dir, "sources.json")
        self.out_file = os.path.join(self.dir, "github_output")
        self.jar = os.path.join(self.dir, "plugin.jar")
        self.repo = os.path.join(self.dir, "repo")
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

    def index(self, run=12, fallback="0"):
        return self.run_main(["index", "--prepare", self.prepare, "--jar", self.jar, "--out", self.repo,
                              "--run-number", str(run), "--fallback", fallback,
                              "--sources", self.sources], {"GITHUB_REPOSITORY": "owner/name"})

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
        self.assertTrue(os.path.isfile(os.path.join(self.repo, "apk", "plugin.jar")))
        with open(os.path.join(self.repo, "index.min.json"), encoding="utf-8") as fh:
            index = json.load(fh)
        self.assertEqual(len(index), 1)
        entry = index[0]
        self.assertEqual(entry["pkg"], "org.pulsarium.trmangahub")
        self.assertEqual(entry["name"], "Pulsar TR Manga Hub")
        self.assertEqual(entry["version"], "1.0.12")
        self.assertIsInstance(entry["code"], int)
        self.assertEqual(entry["code"], 12)
        self.assertEqual(entry["apk"], "plugin.jar")
        self.assertEqual(entry["lang"], "tr")
        self.assertEqual(entry["nsfw"], 0)
        self.assertEqual(entry["sources"], [{"name": "One", "id": "TRONE", "lang": "tr"}])

    def test_index_lists_failing_source_only_with_include_unverified(self):
        write_json(self.sources, {"sources": [
            {"id": "one.tr", "name": "One", "domain": "one.tr", "nsfw": False, "status": "published",
             "formats": {"jar": {"parser": "TRONE"}}},
            {"id": "two.tr", "name": "Two", "domain": "two.tr", "nsfw": True, "status": "failing",
             "failing": True, "formats": {"jar": {"parser": "TRTWO"}}},
        ]})
        self.set_prepare(commit="c1", kept=["TRTWO", "TRONE"], patched=[], include_unverified=True)
        self.index()
        with open(os.path.join(self.repo, "index.min.json"), encoding="utf-8") as fh:
            entry = json.load(fh)[0]
        self.assertEqual(entry["nsfw"], 1)
        self.assertEqual([s["id"] for s in entry["sources"]], ["TRONE", "TRTWO"])

    def test_index_nsfw_zero_without_nsfw_sources(self):
        self.set_prepare(commit="c1", kept=["TRONE"], patched=[])
        self.index()
        with open(os.path.join(self.repo, "index.min.json"), encoding="utf-8") as fh:
            self.assertEqual(json.load(fh)[0]["nsfw"], 0)

    def test_index_build_info_matches_decide_fingerprint(self):
        self.index(run=5, fallback="0")
        with open(os.path.join(self.repo, "build_info.json"), encoding="utf-8") as fh:
            info = json.load(fh)
        with open(os.path.join(self.repo, "apk", "plugin.jar"), "rb") as fh:
            data = fh.read()
        self.assertEqual(info["jarSha256"], hashlib.sha256(data).hexdigest())
        self.assertEqual(info["jarBytes"], len(data))
        self.assertEqual(info["keptCount"], 2)
        self.assertEqual(info["fallback"], 0)
        self.assertEqual(info["runNumber"], 5)
        self.assertEqual(info["upstream_commit"], "c1")
        self.assertTrue(info["builtAt"].endswith("Z"))
        self.assertEqual(len(info["patchedDomains"]), 1)
        self.assertIn("jarSha256", info)
        self.assertIn("fingerprint", info)
        self.assertIn("build=false", self.decide())

    def test_index_readme_is_turkish_and_has_url(self):
        self.index()
        with open(os.path.join(self.repo, "README.md"), encoding="utf-8") as fh:
            text = fh.read()
        self.assertIn("https://raw.githubusercontent.com/owner/name/main/repo", text)
        self.assertIn("JAR Depoları", text)
        self.assertIn("GPL-3.0", text)
        self.assertIn("Resmi Kotatsu uygulaması harici jar desteklemez", text)

    def test_fingerprint_is_order_independent(self):
        a = jar_publish.fingerprint("c", ["B", "A"], [{"old": "x", "new": "y"}, {"old": "a", "new": "b"}])
        b = jar_publish.fingerprint("c", ["A", "B"], [{"old": "a", "new": "b"}, {"old": "x", "new": "y"}])
        self.assertEqual(a, b)
        self.assertNotEqual(a, jar_publish.fingerprint("d", ["A", "B"], []))


if __name__ == "__main__":
    unittest.main()
