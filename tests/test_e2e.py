"""End-to-end run on a temp root with FAKE probe data. No network is used."""

import json
import os
import sys
import tempfile
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
sys.path.insert(0, os.path.join(ROOT, "tests"))

import alternatives  # noqa: E402
import build  # noqa: E402
import fake_probe  # noqa: E402
import probe  # noqa: E402


def synthetic_upstream():
    sources = []
    for i in range(40):
        domain = f"site{i}.tr"
        key = f"site{i // 4}"  # several sources share a key, so same_key candidates exist
        sources.append({"key": key, "name": f"Site {i // 4}", "domain": domain,
                        "baseUrl": f"https://{domain}", "engine": "madara" if i % 2 else "mangathemesia",
                        "formats": {"mihon": {"pkg": f"eu.kanade.tachiyomi.extension.tr.s{i}",
                                              "version": "1.0", "apkUrl": "https://example.invalid/a.apk"},
                                    "jar": None, "catalog": None},
                        "nsfw": False, "upstreams": ["mihon"],
                        "altDomains": [f"alt{i}.tr"] if i % 7 == 0 else []})
    return {"sources": sources}



def _load_json(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _read_text(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


class EndToEndTests(unittest.TestCase):
    def _root(self, tmp, upstream):
        os.makedirs(os.path.join(tmp, "data"))
        with open(os.path.join(tmp, "data", "upstream_tr.json"), "w", encoding="utf-8") as fh:
            json.dump(upstream, fh)
        with open(os.path.join(tmp, "data", "probe_results.json"), "w", encoding="utf-8") as fh:
            json.dump(fake_probe.make_probe_document(upstream["sources"]), fh)
        return tmp

    def test_full_pipeline_with_fake_probe(self):
        upstream = synthetic_upstream()
        with tempfile.TemporaryDirectory() as tmp:
            self._root(tmp, upstream)
            prober = fake_probe.make_fake_prober(upstream["sources"])
            with mock.patch.object(probe, "probe_one", side_effect=prober):
                self.assertEqual(alternatives.main(["--data-dir", os.path.join(tmp, "data")]), 0)
            self.assertEqual(build.main(["--root", tmp]), 0)

            alts = _load_json(os.path.join(tmp, "data", "alternatives.json"))
            sources = _load_json(os.path.join(tmp, "sources", "tr", "sources.json"))
            published = _load_json(os.path.join(tmp, "sources", "tr", "published.json"))
            report = _read_text(os.path.join(tmp, "sources", "tr", "REPORT.md"))

        self.assertEqual(sources["count"], 40)
        ids = {e["id"] for e in sources["sources"]}
        self.assertEqual(len(ids), 40)
        statuses = {e["status"] for e in sources["sources"]}
        self.assertTrue(statuses <= {"published", "cf_protected_published", "quarantined", "unverified"})
        for dom, entry in alts.items():
            self.assertIn("candidate", entry)
        found = [e for e in sources["sources"] if e.get("alternative")]
        self.assertEqual(len(found), len(published["via_alternative"]))
        self.assertIn("## Özet", report)

    def test_all_blocked_fake_run_is_cancelled_and_writes_nothing(self):
        upstream = synthetic_upstream()
        with tempfile.TemporaryDirectory() as tmp:
            self._root(tmp, upstream)
            doc = {"meta": {}, "results": [
                {"key": s["key"], "name": s["name"], "domain": s["domain"], "status": "blocked",
                 "reason": "FAKE blocked", "functional": None} for s in upstream["sources"]]}
            with open(os.path.join(tmp, "data", "probe_results.json"), "w", encoding="utf-8") as fh:
                json.dump(doc, fh)
            self.assertEqual(build.main(["--root", tmp]), build.EXIT_CANCEL)
            self.assertFalse(os.path.exists(os.path.join(tmp, "sources")))


if __name__ == "__main__":
    unittest.main(verbosity=2)
