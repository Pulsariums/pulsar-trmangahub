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


if __name__ == "__main__":
    unittest.main(verbosity=2)
