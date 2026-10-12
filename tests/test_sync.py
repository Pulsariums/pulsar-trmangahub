"""Unit tests for the scope field in scripts/sync.py. No network is used."""

import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import sync  # noqa: E402


def ext(pkg, sources, name="Ext"):
    return {"packageName": pkg, "name": name, "versionName": "1.0", "sources": sources,
            "resources": {"apkUrl": "https://example.invalid/a.apk"}}


class MihonScopeTests(unittest.TestCase):
    def test_tr_package_is_tr_native(self):
        index = {"extensionList": {"extensions": [
            ext("eu.kanade.tachiyomi.extension.tr.foo",
                [{"name": "Foo", "language": "tr", "homeUrl": "https://foo.tr/"}])]}}
        records, _ = sync.parse_mihon(index)
        self.assertEqual([r["scope"] for r in records], ["tr_native"])

    def test_all_package_with_tr_source_is_multilang(self):
        index = {"extensionList": {"extensions": [
            ext("eu.kanade.tachiyomi.extension.all.bar",
                [{"name": "Bar", "language": "tr", "homeUrl": "https://bar.tr/"},
                 {"name": "BarEn", "language": "en", "homeUrl": "https://baren.com/"}])]}}
        records, _ = sync.parse_mihon(index)
        self.assertEqual([(r["domain"], r["scope"]) for r in records], [("bar.tr", "multilang")])



class MergeScopeTests(unittest.TestCase):
    def _rec(self, upstream, name, domain, scope):
        return sync.make_record(upstream, name, domain, f"https://{domain}" if domain else None,
                                None, False, {"mihon": None, "jar": None, "catalog": None},
                                scope=scope)

    def test_merged_record_is_tr_native_if_any_member_is(self):
        recs = [self._rec("mihon", "Foo", "foo.tr", "multilang"),
                self._rec("kotatsu", "Foo", "foo.tr", "tr_native")]
        targets, _ = sync.merge_records(recs)
        final = sync.finalize(targets)
        self.assertEqual(final[0]["scope"], "tr_native")

    def test_merged_record_is_multilang_when_no_member_is_tr_native(self):
        recs = [self._rec("mihon", "Bar", "bar.tr", "multilang")]
        targets, _ = sync.merge_records(recs)
        self.assertEqual(sync.finalize(targets)[0]["scope"], "multilang")

    def test_kotatsu_and_nyora_records_are_tr_native(self):
        row = {"id": "x", "name": "X", "domain": "x.tr", "lang": "tr", "engine": "madara"}
        nyora = sync.parse_nyora({"sources": [row]}, None)
        self.assertEqual([r["scope"] for r in nyora], ["tr_native"])


class CustomRegistryTests(unittest.TestCase):
    def setUp(self):
        import tempfile
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = os.path.join(self.tmp.name, "sources.json")

    def write_custom(self, payload):
        import json
        with open(self.path, "w", encoding="utf-8") as fh:
            json.dump(payload, fh)

    def test_missing_file_gives_no_records(self):
        self.assertEqual(sync.parse_custom(self.path), [])

    def test_custom_entries_have_no_mihon_or_jar_format(self):
        self.write_custom([{"id": "zz.com", "name": "Zz", "domain": "zz.com",
                            "baseUrl": "https://zz.com", "engine": "madara", "scope": "tr_native"}])
        records = sync.parse_custom(self.path)
        self.assertEqual([r["upstream"] for r in records], ["custom"])
        self.assertEqual(records[0]["formats"], {"mihon": None, "jar": None, "catalog": None})
        self.assertEqual(records[0]["engine"], "madara")
        self.assertEqual(records[0]["scope"], "tr_native")

    def test_custom_record_merges_with_upstream_by_domain(self):
        self.write_custom([{"id": "dd.com", "name": "Dd", "domain": "dd.com", "engine": "madara"}])
        mihon = sync.make_record("mihon", "Dd", "dd.com", "https://dd.com", None, False,
                                 {"mihon": {"pkg": "eu.kanade.tachiyomi.extension.tr.dd"}})
        targets, _ = sync.merge_records([mihon] + sync.parse_custom(self.path))
        final = sync.finalize(targets)
        self.assertEqual(len(final), 1)
        self.assertEqual(sorted(final[0]["upstreams"]), ["custom", "mihon"])
        self.assertEqual(final[0]["formats"]["mihon"]["pkg"], "eu.kanade.tachiyomi.extension.tr.dd")

    def test_custom_only_source_is_probed_but_not_published_as_extension(self):
        import build
        self.write_custom([{"id": "cc.com", "name": "Cc", "domain": "cc.com", "engine": "madara"}])
        targets, _ = sync.merge_records(sync.parse_custom(self.path))
        src = sync.finalize(targets)[0]
        entry = build.build_entry(src, {"status": "ok", "reason": "http 200", "functional": True,
                                        "http": 200}, None, {}, "t")
        self.assertEqual(entry["status"], "published")
        payload = build.published_payload([entry], "t")
        self.assertEqual(payload["mihon"], [])
        self.assertEqual(payload["jar"], [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
