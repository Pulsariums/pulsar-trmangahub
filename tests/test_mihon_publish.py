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
GH = "https://github.com/keiyoushi/extensions/releases/download/abc"


def write_json(path, payload):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False)


def ext(pkg, apk, code="106037", version="1.6.37", warning="CONTENT_WARNING_SAFE", sources=None):
    return {
        "name": pkg.rsplit(".", 1)[-1],
        "packageName": pkg,
        "resources": {"apkUrl": f"{GH}/{apk}"},
        "extensionLib": "1.6",
        "versionCode": code,
        "versionName": version,
        "contentWarning": warning,
        "sources": sources if sources is not None else [
            {"id": "123", "name": "Site", "language": "tr", "homeUrl": "https://site.tr"}],
    }


def index_doc(exts):
    return {"name": "x", "extensionList": {"extensions": exts}}


ITEM = {"pkg": "p.a", "hosts": {"site.tr"}}


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


class HelperTests(unittest.TestCase):
    def sources_doc(self):
        return {"sources": [
            {"domain": "a.tr", "status": "published", "formats": {"mihon": {"pkg": "p.a", "apkUrl": "u1"}}},
            {"domain": "a2.tr", "status": "failing", "failing": True,
             "formats": {"mihon": {"pkg": "p.a", "apkUrl": "u2"}}},
            {"domain": "b.tr", "status": "cf_protected_published", "formats": {"mihon": {"pkg": "p.b"}}},
            {"domain": "c.tr", "status": "quarantined", "formats": {"mihon": {"pkg": "p.c"}}},
            {"domain": "d.tr", "status": "published", "formats": {"jar": {"parser": "D"}}},
            "junk",
        ]}

    def test_mihon_packages_default_keeps_only_ok_hosts(self):
        items = mihon_publish.mihon_packages(self.sources_doc())
        self.assertEqual([(i["pkg"], i["hosts"], i["apkUrl"]) for i in items], [("p.a", {"a.tr"}, "u1")])
        self.assertEqual(mihon_publish.mihon_packages({}), [])

    def test_mihon_packages_include_unverified_adds_failing_and_cf(self):
        items = {i["pkg"]: i for i in mihon_publish.mihon_packages(self.sources_doc(), include_unverified=True)}
        self.assertEqual(items["p.a"]["hosts"], {"a.tr", "a2.tr"})
        self.assertEqual(items["p.b"]["hosts"], {"b.tr"})
        self.assertNotIn("p.c", items)

    def test_host_of_normalizes(self):
        self.assertEqual(mihon_publish.host_of("https://www.A.tr/path"), "a.tr")
        self.assertEqual(mihon_publish.host_of("a.tr"), "a.tr")
        self.assertIsNone(mihon_publish.host_of(None))

    def test_listed_sources_only_verified_hosts(self):
        e = ext("p.a", "a.apk", sources=[
            {"id": "1", "name": "A", "language": "tr", "homeUrl": "https://www.a.tr/"},
            {"id": "2", "name": "B", "language": "tr", "homeUrl": "https://b.tr"}])
        self.assertEqual([s["id"] for s in mihon_publish.listed_sources(e, {"a.tr"})], ["1"])
        self.assertEqual(mihon_publish.listed_sources(e, set()), [])

    def test_upstream_map(self):
        m = mihon_publish.upstream_map(index_doc([ext("p.a", "a.apk"), {"name": "no pkg"}]))
        self.assertEqual(list(m), ["p.a"])

    def test_apk_name_from_url(self):
        self.assertEqual(mihon_publish.apk_name_from_url(f"{GH}/tachiyomi-tr.a-v1.apk"),
                         "tachiyomi-tr.a-v1.apk")
        self.assertIsNone(mihon_publish.apk_name_from_url("https://x.tr/"))
        self.assertIsNone(mihon_publish.apk_name_from_url("https://x.tr/a%2F..%2Fb.jar"))

    def test_build_entry_format(self):
        srcs = mihon_publish.listed_sources(ext("p.a", "a.apk"), {"site.tr"})
        e = mihon_publish.build_entry(ext("p.a", "a.apk", warning="CONTENT_WARNING_NSFW"),
                                      "p.a", "a.apk", 106037, "1.6.37", srcs)
        self.assertEqual(e["code"], 106037)
        self.assertIsInstance(e["code"], int)
        self.assertEqual(e["nsfw"], 1)
        self.assertEqual(e["lang"], "tr")
        self.assertEqual(e["version"], "1.6.37")
        self.assertEqual(e["sources"], [{"name": "Site", "lang": "tr", "id": "123",
                                         "baseUrl": "https://site.tr"}])
        safe = mihon_publish.build_entry(ext("p.a", "a.apk", warning="CONTENT_WARNING_MIXED"),
                                         "p.a", "a.apk", 1, "1", srcs)
        self.assertEqual(safe["nsfw"], 0)


class SyncTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.apk_dir = os.path.join(self.tmp.name, "apk")

    def test_downloads_fresh_apk_and_builds_entry(self):
        upstream = {"p.a": ext("p.a", "a.apk")}
        fetcher = FakeFetcher({f"{GH}/a.apk": ZIP_BYTES})
        result, stats, skipped = mihon_publish.sync([ITEM], upstream, {}, self.apk_dir,
                                                    fetcher=fetcher)
        self.assertEqual(fetcher.calls, [f"{GH}/a.apk"])
        self.assertEqual(result[0]["apk"], "a.apk")
        self.assertEqual(stats["indirildi"], 1)
        self.assertEqual(skipped, [])
        with open(os.path.join(self.apk_dir, "a.apk"), "rb") as fh:
            self.assertEqual(fh.read(), ZIP_BYTES)

    def test_skip_download_when_same_version_present(self):
        os.makedirs(self.apk_dir)
        with open(os.path.join(self.apk_dir, "a.apk"), "wb") as fh:
            fh.write(ZIP_BYTES)
        upstream = {"p.a": ext("p.a", "a.apk")}
        prev = {"p.a": {"pkg": "p.a", "apk": "a.apk", "code": 106037, "version": "1.6.37"}}
        fetcher = FakeFetcher({})
        result, stats, _ = mihon_publish.sync([ITEM], upstream, prev, self.apk_dir,
                                              fetcher=fetcher)
        self.assertEqual(fetcher.calls, [])
        self.assertEqual(stats["yeniden_kullanildi"], 1)
        self.assertEqual(len(result), 1)

    def test_version_change_redownloads(self):
        os.makedirs(self.apk_dir)
        with open(os.path.join(self.apk_dir, "a.apk"), "wb") as fh:
            fh.write(ZIP_BYTES)
        upstream = {"p.a": ext("p.a", "a.apk", code="106038", version="1.6.38")}
        prev = {"p.a": {"pkg": "p.a", "apk": "a.apk", "code": 106037, "version": "1.6.37"}}
        fetcher = FakeFetcher({f"{GH}/a.apk": ZIP_BYTES})
        result, stats, _ = mihon_publish.sync([ITEM], upstream, prev, self.apk_dir,
                                              fetcher=fetcher)
        self.assertEqual(stats["indirildi"], 1)
        self.assertEqual(result[0]["code"], 106038)

    def test_falls_back_to_published_url(self):
        upstream = {"p.a": {**ext("p.a", "new.apk"), "resources": {"apkUrl": f"{GH}/new.apk"}}}
        fetcher = FakeFetcher({f"{GH}/old.apk": ZIP_BYTES})
        result, _, skipped = mihon_publish.sync(
            [{**ITEM, "apkUrl": f"{GH}/old.apk"}], upstream, {}, self.apk_dir, fetcher=fetcher)
        self.assertEqual(set(fetcher.calls), {f"{GH}/new.apk", f"{GH}/old.apk"})
        self.assertEqual(fetcher.calls[-1], f"{GH}/old.apk")
        self.assertEqual(result[0]["apk"], "old.apk")
        self.assertEqual(skipped, [])

    def test_failed_download_is_skipped_and_logged(self):
        upstream = {"p.a": ext("p.a", "a.apk")}
        fetcher = FakeFetcher({f"{GH}/a.apk": OSError("boom")})
        result, stats, skipped = mihon_publish.sync([ITEM], upstream, {}, self.apk_dir,
                                                    fetcher=fetcher)
        self.assertEqual(result, [])
        self.assertEqual(stats["atlandi"], 1)
        self.assertEqual([p for p, _ in skipped], ["p.a"])

    def test_non_zip_payload_is_rejected(self):
        upstream = {"p.a": ext("p.a", "a.apk")}
        fetcher = FakeFetcher({f"{GH}/a.apk": b"<html>nope</html>"})
        result, _, skipped = mihon_publish.sync([ITEM], upstream, {}, self.apk_dir,
                                                fetcher=fetcher)
        self.assertEqual(result, [])
        self.assertEqual(len(skipped), 1)
        self.assertFalse(os.path.exists(os.path.join(self.apk_dir, "a.apk")))

    def test_missing_from_index_is_skipped(self):
        result, stats, skipped = mihon_publish.sync([{"pkg": "p.gone", "hosts": {"site.tr"}}], {}, {}, self.apk_dir,
                                                    fetcher=FakeFetcher({}))
        self.assertEqual(result, [])
        self.assertEqual(skipped, [("p.gone", "index.json içinde yok")])

    def test_bad_version_code_is_skipped(self):
        upstream = {"p.a": ext("p.a", "a.apk", code="abc")}
        result, _, skipped = mihon_publish.sync([ITEM], upstream, {}, self.apk_dir,
                                                fetcher=FakeFetcher({}))
        self.assertEqual(result, [])
        self.assertEqual(len(skipped), 1)

    def test_package_without_verified_host_is_not_downloaded(self):
        upstream = {"p.a": ext("p.a", "a.apk")}
        fetcher = FakeFetcher({f"{GH}/a.apk": ZIP_BYTES})
        result, _, skipped = mihon_publish.sync([{"pkg": "p.a", "hosts": {"other.tr"}}], upstream, {},
                                                self.apk_dir, fetcher=fetcher)
        self.assertEqual(result, [])
        self.assertEqual(fetcher.calls, [])
        self.assertEqual(skipped, [("p.a", "doğrulanmış kaynakla eşleşen kaynak yok")])

    def test_remove_stale(self):
        os.makedirs(self.apk_dir)
        for name in ("keep.apk", "gone.apk"):
            with open(os.path.join(self.apk_dir, name), "wb") as fh:
                fh.write(ZIP_BYTES)
        self.assertEqual(mihon_publish.remove_stale(self.apk_dir, {"keep.apk"}), ["gone.apk"])
        self.assertEqual(os.listdir(self.apk_dir), ["keep.apk"])


class MainTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = self.tmp.name
        write_json(os.path.join(self.root, "sources", "tr", "sources.json"), {"sources": [
            {"domain": "site.tr", "status": "published",
             "formats": {"mihon": {"pkg": "p.a", "apkUrl": f"{GH}/a.apk", "version": "1.6.37"}}},
            {"domain": "broken.tr", "status": "quarantined",
             "formats": {"mihon": {"pkg": "p.broken", "apkUrl": f"{GH}/broken.apk", "version": "1.0.0"}}},
        ]})

    def run_main(self, fetcher, extra_env=None):
        buf = io.StringIO()
        env = {k: v for k, v in os.environ.items() if k not in ("GITHUB_STEP_SUMMARY", "GITHUB_REPOSITORY")}
        env.update(extra_env or {})
        with mock.patch.dict(os.environ, env, clear=True), contextlib.redirect_stdout(buf):
            code = mihon_publish.main(["--root", self.root], fetcher=fetcher)
        return code, buf.getvalue()

    def test_end_to_end(self):
        doc = index_doc([ext("p.a", "a.apk"), ext("p.broken", "broken.apk"), ext("p.other", "o.apk")])
        fetcher = FakeFetcher({
            mihon_publish.INDEX_URL: json.dumps(doc).encode("utf-8"),
            f"{GH}/a.apk": ZIP_BYTES,
        })
        out_dir = os.path.join(self.root, "repo-mihon")
        os.makedirs(os.path.join(out_dir, "apk"))
        with open(os.path.join(out_dir, "apk", "stale.apk"), "wb") as fh:
            fh.write(ZIP_BYTES)
        code, out = self.run_main(fetcher)
        self.assertEqual(code, 0)
        with open(os.path.join(out_dir, "index.min.json"), encoding="utf-8") as fh:
            written = json.load(fh)
        self.assertEqual([e["pkg"] for e in written], ["p.a"])
        self.assertEqual(written[0]["code"], 106037)
        self.assertTrue(os.path.isfile(os.path.join(out_dir, "apk", "a.apk")))
        self.assertFalse(os.path.exists(os.path.join(out_dir, "apk", "stale.apk")))
        self.assertTrue(os.path.isfile(os.path.join(out_dir, "README.md")))
        self.assertNotIn(f"{GH}/broken.apk", fetcher.calls)
        self.assertIn("İndirilen APK: 1", out)

    def test_index_failure_touches_nothing(self):
        fetcher = FakeFetcher({mihon_publish.INDEX_URL: OSError("down")})
        code, _ = self.run_main(fetcher)
        self.assertEqual(code, 1)
        self.assertFalse(os.path.exists(os.path.join(self.root, "repo-mihon")))

    def test_step_summary_appended(self):
        doc = index_doc([ext("p.a", "a.apk")])
        fetcher = FakeFetcher({
            mihon_publish.INDEX_URL: json.dumps(doc).encode("utf-8"),
            f"{GH}/a.apk": ZIP_BYTES,
        })
        summary_path = os.path.join(self.root, "summary.md")
        code, _ = self.run_main(fetcher, {"GITHUB_STEP_SUMMARY": summary_path})
        self.assertEqual(code, 0)
        with open(summary_path, encoding="utf-8") as fh:
            self.assertIn("Mihon deposu", fh.read())


if __name__ == "__main__":
    unittest.main()
