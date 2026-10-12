"""Unit tests for scripts/mihon_publish.py. No network is used; fetchers are fakes."""

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

import mihon_publish  # noqa: E402

ZIP_BYTES = b"PK\x03\x04fake-apk"


def write_json(path, payload):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False)


def tr_entry(pkg, apk, version="1.0.0", lang="tr"):
    return {"name": pkg, "pkg": pkg, "apk": apk, "lang": lang, "code": 1,
            "version": version, "nsfw": 0, "sources": [{"name": pkg, "lang": lang, "id": "1"}]}


class FakeFetcher:
    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    def __call__(self, url, timeout=None):
        self.calls.append(url)
        value = self.responses.get(url)
        if value is None:
            raise OSError(f"404 {url}")
        if isinstance(value, Exception):
            raise value
        return value


class SelectTests(unittest.TestCase):
    def test_published_pkgs_filter_and_lang(self):
        index = [tr_entry("p.a", "a.apk"), tr_entry("p.b", "b.apk"),
                 tr_entry("p.a", "a2.apk"), tr_entry("p.c", "c.apk", lang="en")]
        kept = mihon_publish.select_entries(index, {"p.a", "p.c"}, set())
        self.assertEqual([e["apk"] for e in kept], ["a.apk"])

    def test_fallback_skips_fully_quarantined_pkgs(self):
        index = [tr_entry("p.a", "a.apk"), tr_entry("p.b", "b.apk")]
        kept = mihon_publish.select_entries(index, None, {"p.b"})
        self.assertEqual([e["pkg"] for e in kept], ["p.a"])

    def test_bad_apk_names_are_rejected(self):
        index = [tr_entry("p.a", "../evil.apk"), tr_entry("p.b", "x/y.apk"), tr_entry("p.c", "ok.apk")]
        kept = mihon_publish.select_entries(index, None, set())
        self.assertEqual([e["apk"] for e in kept], ["ok.apk"])

    def test_fully_quarantined_pkgs(self):
        doc = {"sources": [
            {"status": "quarantined", "formats": {"mihon": {"pkg": "p.dead"}}},
            {"status": "quarantined", "formats": {"mihon": {"pkg": "p.dead"}}},
            {"status": "published", "formats": {"mihon": {"pkg": "p.mixed"}}},
            {"status": "quarantined", "formats": {"mihon": {"pkg": "p.mixed"}}},
            {"status": "quarantined", "formats": {"mihon": None}},
        ]}
        self.assertEqual(mihon_publish.fully_quarantined_pkgs(doc), {"p.dead"})

    def test_published_mihon_pkgs_none_when_missing(self):
        self.assertIsNone(mihon_publish.published_mihon_pkgs({"mihon": []}))
        self.assertIsNone(mihon_publish.published_mihon_pkgs({}))
        self.assertEqual(mihon_publish.published_mihon_pkgs({"mihon": [{"pkg": "p.a"}]}), {"p.a"})


class SyncTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.apk_dir = os.path.join(self.tmp.name, "apk")

    def url(self, apk):
        return mihon_publish.APK_BASE_URL + apk

    def test_downloads_new_and_skips_unchanged(self):
        apk_dir = self.apk_dir
        os.makedirs(apk_dir)
        with open(os.path.join(apk_dir, "a.apk"), "wb") as fh:
            fh.write(ZIP_BYTES)
        prev = {"p.a": tr_entry("p.a", "a.apk", "1.0.0")}
        fetcher = FakeFetcher({self.url("b.apk"): ZIP_BYTES})
        entries = [tr_entry("p.a", "a.apk", "1.0.0"), tr_entry("p.b", "b.apk", "2.0.0")]
        result, stats, failures = mihon_publish.sync_apks(entries, prev, apk_dir, fetcher=fetcher)
        self.assertEqual(fetcher.calls, [self.url("b.apk")])
        self.assertEqual(len(result), 2)
        self.assertEqual(stats["indirildi"], 1)
        self.assertEqual(stats["yeniden_kullanildi"], 1)
        self.assertEqual(failures, [])
        with open(os.path.join(apk_dir, "b.apk"), "rb") as fh:
            self.assertEqual(fh.read(), ZIP_BYTES)

    def test_version_change_triggers_download(self):
        os.makedirs(self.apk_dir)
        with open(os.path.join(self.apk_dir, "a.apk"), "wb") as fh:
            fh.write(ZIP_BYTES)
        prev = {"p.a": tr_entry("p.a", "a.apk", "1.0.0")}
        fetcher = FakeFetcher({self.url("a.apk"): ZIP_BYTES})
        result, stats, _ = mihon_publish.sync_apks([tr_entry("p.a", "a.apk", "1.0.1")], prev,
                                                   self.apk_dir, fetcher=fetcher)
        self.assertEqual(stats["indirildi"], 1)
        self.assertEqual(result[0]["version"], "1.0.1")

    def test_non_zip_download_is_failure_and_dropped(self):
        fetcher = FakeFetcher({self.url("bad.apk"): b"<html>not an apk</html>"})
        result, stats, failures = mihon_publish.sync_apks([tr_entry("p.bad", "bad.apk")], {},
                                                          self.apk_dir, fetcher=fetcher)
        self.assertEqual(result, [])
        self.assertEqual(stats["dusurildu"], 1)
        self.assertEqual(len(failures), 1)
        self.assertFalse(os.path.exists(os.path.join(self.apk_dir, "bad.apk")))

    def test_failure_keeps_previous_entry_when_file_exists(self):
        os.makedirs(self.apk_dir)
        with open(os.path.join(self.apk_dir, "old.apk"), "wb") as fh:
            fh.write(ZIP_BYTES)
        prev = {"p.a": tr_entry("p.a", "old.apk", "1.0.0")}
        fetcher = FakeFetcher({})
        result, stats, failures = mihon_publish.sync_apks([tr_entry("p.a", "new.apk", "1.0.1")],
                                                          prev, self.apk_dir, fetcher=fetcher)
        self.assertEqual([e["apk"] for e in result], ["old.apk"])
        self.assertEqual(stats["eski_korundu"], 1)
        self.assertEqual(len(failures), 1)

    def test_remove_stale(self):
        os.makedirs(self.apk_dir)
        for name in ("keep.apk", "gone.apk"):
            with open(os.path.join(self.apk_dir, name), "wb") as fh:
                fh.write(ZIP_BYTES)
        removed = mihon_publish.remove_stale(self.apk_dir, {"keep.apk"})
        self.assertEqual(removed, ["gone.apk"])
        self.assertEqual(os.listdir(self.apk_dir), ["keep.apk"])


class MainTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = self.tmp.name
        write_json(os.path.join(self.root, "sources", "tr", "published.json"),
                   {"mihon": [{"pkg": "p.a", "version": "1.0.0", "domain": "a.tr"}]})
        write_json(os.path.join(self.root, "sources", "tr", "sources.json"), {"sources": []})

    def run_main(self, fetcher):
        buf = io.StringIO()
        env = {k: v for k, v in os.environ.items() if k not in ("GITHUB_STEP_SUMMARY", "GITHUB_REPOSITORY")}
        with mock.patch.dict(os.environ, env, clear=True), contextlib.redirect_stdout(buf):
            code = mihon_publish.main(["--root", self.root], fetcher=fetcher)
        return code, buf.getvalue()

    def test_end_to_end_writes_index_readme_and_summary(self):
        index = [tr_entry("p.a", "a.apk", "1.0.0"), tr_entry("p.x", "x.apk", "1.0.0")]
        fetcher = FakeFetcher({
            mihon_publish.INDEX_URL: json.dumps(index).encode("utf-8"),
            mihon_publish.APK_BASE_URL + "a.apk": ZIP_BYTES,
        })
        code, out = self.run_main(fetcher)
        self.assertEqual(code, 0)
        out_dir = os.path.join(self.root, "repo-mihon")
        with open(os.path.join(out_dir, "index.min.json"), encoding="utf-8") as fh:
            written = json.load(fh)
        self.assertEqual([e["pkg"] for e in written], ["p.a"])
        self.assertEqual(written[0], index[0])
        self.assertTrue(os.path.isfile(os.path.join(out_dir, "apk", "a.apk")))
        self.assertTrue(os.path.isfile(os.path.join(out_dir, "README.md")))
        self.assertIn("Türkçe", out)
        self.assertIn("İndirilen APK: 1", out)

    def test_upstream_failure_touches_nothing(self):
        fetcher = FakeFetcher({mihon_publish.INDEX_URL: OSError("down")})
        code, _ = self.run_main(fetcher)
        self.assertEqual(code, 1)
        self.assertFalse(os.path.exists(os.path.join(self.root, "repo-mihon")))

    def test_step_summary_is_appended(self):
        index = [tr_entry("p.a", "a.apk", "1.0.0")]
        fetcher = FakeFetcher({
            mihon_publish.INDEX_URL: json.dumps(index).encode("utf-8"),
            mihon_publish.APK_BASE_URL + "a.apk": ZIP_BYTES,
        })
        summary_path = os.path.join(self.root, "summary.md")
        buf = io.StringIO()
        env = {k: v for k, v in os.environ.items() if k != "GITHUB_STEP_SUMMARY"}
        env["GITHUB_STEP_SUMMARY"] = summary_path
        with mock.patch.dict(os.environ, env, clear=True), contextlib.redirect_stdout(buf):
            self.assertEqual(mihon_publish.main(["--root", self.root], fetcher=fetcher), 0)
        with open(summary_path, encoding="utf-8") as fh:
            self.assertIn("Mihon deposu", fh.read())


if __name__ == "__main__":
    unittest.main()
