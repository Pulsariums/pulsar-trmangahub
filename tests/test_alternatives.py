"""Unit tests for scripts/alternatives.py. The prober is mocked; no network is used."""

import json
import os
import sys
import tempfile
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import alternatives  # noqa: E402
import probe  # noqa: E402


def src(key, name, domain, engine=None, alt=(), upstreams=("mihon",)):
    return {"key": key, "name": name, "domain": domain, "baseUrl": f"https://{domain}",
            "engine": engine, "formats": {"mihon": None, "jar": None, "catalog": None},
            "nsfw": False, "upstreams": list(upstreams), "altDomains": list(alt)}


def row(domain, status, functional=None, moved_to=None, engine_detected="unknown", key=None, name=None):
    return {"key": key or domain.split(".")[0], "name": name or domain, "domain": domain,
            "status": status, "reason": status, "http": 200 if status == "ok" else None,
            "finalUrl": None, "moved_to": moved_to, "engine_detected": engine_detected,
            "functional": functional, "functional_reason": None}


def prober_from(table, calls=None):
    """Return a prober that answers from table (domain -> row) and records calls."""
    def _probe(domain):
        if calls is not None:
            calls.append(domain)
        base = table.get(domain, {"status": "dead", "reason": "dead", "http": None, "finalUrl": None,
                                  "moved_to": None, "engine_detected": "unknown", "functional": None})
        out = dict(base)
        out.setdefault("finalUrl", None)
        return out
    return _probe


OK_TABLE = {"ok.tr": {"status": "ok", "functional": True, "http": 200, "finalUrl": "https://ok.tr/"}}


class SelectionTests(unittest.TestCase):
    def test_broken_selection_rules(self):
        rows = [row("dead.tr", "dead"), row("parked.tr", "parked"),
                row("wrongfunc.tr", "ok", functional=False),
                row("cf.tr", "cf_protected"), row("other.tr", "other"), row("blocked.tr", "blocked"),
                row("good.tr", "ok", functional=True), row("unk.tr", "ok", functional=None)]
        sources = [src(r["key"], r["name"], r["domain"]) for r in rows]
        result, _ = alternatives.run(sources, rows, prober_from({}))
        self.assertEqual(sorted(result), ["dead.tr", "parked.tr", "wrongfunc.tr"])


class CandidateTests(unittest.TestCase):
    def test_moved_to_is_first_and_high(self):
        rows = [row("old.tr", "dead", moved_to="new.tr")]
        sources = [src("old", "Old", "old.tr"), src("old", "Old", "other.tr")]
        table = {"new.tr": {"status": "ok", "functional": True, "http": 200}}
        result, _ = alternatives.run(sources, rows + [row("other.tr", "ok", functional=True)],
                                     prober_from(table))
        self.assertEqual(result["old.tr"]["candidate"], "new.tr")
        self.assertEqual(result["old.tr"]["how"], "moved_to")
        self.assertEqual(result["old.tr"]["confidence"], "high")
        self.assertEqual(result["old.tr"]["probe"]["status"], "ok")

    def test_alt_domains_from_nyora_are_high(self):
        rows = [row("old.tr", "parked")]
        sources = [src("old", "Old", "old.tr", alt=["alt.tr"])]
        table = {"alt.tr": {"status": "ok", "functional": None, "http": 200}}
        result, _ = alternatives.run(sources, rows, prober_from(table))
        self.assertEqual(result["old.tr"]["candidate"], "alt.tr")
        self.assertEqual(result["old.tr"]["how"], "altDomains")
        self.assertEqual(result["old.tr"]["confidence"], "high")

    def test_same_key_is_medium_and_prefers_same_engine(self):
        rows = [row("old.tr", "dead")]
        sources = [src("olds", "Olds", "old.tr", engine="madara"),
                   src("olds", "Olds", "mangaish.tr", engine="mangathemesia"),
                   src("olds", "Olds", "madarish.tr", engine="madara")]
        calls = []
        table = {"madarish.tr": {"status": "ok", "functional": True, "http": 200}}
        result, _ = alternatives.run(sources, rows, prober_from(table, calls))
        self.assertEqual(calls[0], "madarish.tr")
        self.assertEqual(result["old.tr"]["candidate"], "madarish.tr")
        self.assertEqual(result["old.tr"]["how"], "same_key")
        self.assertEqual(result["old.tr"]["confidence"], "medium")

    def test_similar_key_is_low_and_threshold_respected(self):
        rows = [row("old.tr", "dead")]
        sources = [src("mangaoku", "Manga Oku", "old.tr"),
                   src("mangaokuu", "Manga Okuu", "close.tr"),
                   src("zzzzqqqq", "Other", "far.tr")]
        calls = []
        table = {"close.tr": {"status": "ok", "functional": True, "http": 200}}
        result, _ = alternatives.run(sources, rows, prober_from(table, calls))
        self.assertEqual(calls, ["close.tr"])
        self.assertEqual(result["old.tr"]["how"], "similar_key")
        self.assertEqual(result["old.tr"]["confidence"], "low")

    def test_same_name_is_medium(self):
        rows = [row("old.tr", "dead")]
        sources = [src("alpha", "Ortak Ad", "old.tr"), src("beta", "ortak  ad", "named.tr")]
        table = {"named.tr": {"status": "ok", "functional": True, "http": 200}}
        result, _ = alternatives.run(sources, rows, prober_from(table))
        self.assertEqual(result["old.tr"]["how"], "same_name")
        self.assertEqual(result["old.tr"]["confidence"], "medium")

    def test_functional_false_candidate_is_skipped(self):
        rows = [row("old.tr", "dead")]
        sources = [src("old", "Old", "old.tr", alt=["bad.tr", "good.tr"])]
        table = {"bad.tr": {"status": "ok", "functional": False, "http": 200},
                 "good.tr": {"status": "ok", "functional": True, "http": 200}}
        result, _ = alternatives.run(sources, rows, prober_from(table))
        self.assertEqual(result["old.tr"]["candidate"], "good.tr")

    def test_not_found_writes_tried_list(self):
        rows = [row("old.tr", "dead", moved_to="gone.tr")]
        sources = [src("old", "Old", "old.tr", alt=["cf.tr"])]
        table = {"gone.tr": {"status": "dead"}, "cf.tr": {"status": "cf_protected"}}
        result, _ = alternatives.run(sources, rows, prober_from(table))
        entry = result["old.tr"]
        self.assertIsNone(entry["candidate"])
        self.assertEqual([t["domain"] for t in entry["tried"]], ["gone.tr", "cf.tr"])
        self.assertEqual(entry["tried"][1]["status"], "cf_protected")

    def test_candidate_equal_to_broken_domain_is_skipped(self):
        rows = [row("old.tr", "dead", moved_to="old.tr")]
        sources = [src("old", "Old", "old.tr")]
        calls = []
        result, _ = alternatives.run(sources, rows, prober_from({}, calls))
        self.assertEqual(calls, [])
        self.assertIsNone(result["old.tr"]["candidate"])
        self.assertEqual(result["old.tr"]["tried"], [])


class CacheTests(unittest.TestCase):
    def test_same_candidate_probed_once_per_run(self):
        rows = [row("a.tr", "dead"), row("b.tr", "dead")]
        sources = [src("a", "A", "a.tr", alt=["shared.tr"]), src("b", "B", "b.tr", alt=["shared.tr"])]
        calls = []
        table = {"shared.tr": {"status": "ok", "functional": True, "http": 200}}
        result, cache = alternatives.run(sources, rows, prober_from(table, calls))
        self.assertEqual(calls.count("shared.tr"), 1)
        self.assertEqual(cache.cache_hits, 1)
        self.assertEqual(result["a.tr"]["candidate"], "shared.tr")
        self.assertEqual(result["b.tr"]["candidate"], "shared.tr")


class MainTests(unittest.TestCase):
    def test_main_writes_flat_mapping_with_default_prober(self):
        upstream = {"sources": [src("old", "Old", "old.tr", alt=["new.tr"])]}
        probes = {"meta": {}, "results": [row("old.tr", "dead")]}
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "upstream_tr.json"), "w", encoding="utf-8") as fh:
                json.dump(upstream, fh)
            with open(os.path.join(tmp, "probe_results.json"), "w", encoding="utf-8") as fh:
                json.dump(probes, fh)
            fake = {"status": "ok", "functional": True, "http": 200, "finalUrl": "https://new.tr/"}
            with mock.patch.object(probe, "probe_one", return_value=fake) as p:
                code = alternatives.main(["--data-dir", tmp])
            self.assertEqual(code, 0)
            p.assert_called_once_with("new.tr")
            with open(os.path.join(tmp, "alternatives.json"), encoding="utf-8") as fh:
                out = json.load(fh)
        self.assertEqual(out["old.tr"]["candidate"], "new.tr")
        self.assertEqual(out["old.tr"]["how"], "altDomains")
        self.assertEqual(out["old.tr"]["confidence"], "high")
        self.assertEqual(out["old.tr"]["probe"]["status"], "ok")

    def test_missing_inputs_exit_1(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(alternatives.main(["--data-dir", tmp]), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
