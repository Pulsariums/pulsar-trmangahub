"""Unit tests for scripts/select_domains.py. No network is used."""

import contextlib
import io
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import select_domains  # noqa: E402

ENTRIES = [
    {"domain": "a.com", "status": "published", "engine": "madara", "scope": "tr_native"},
    {"domain": "b.com", "status": "quarantined", "engine": None, "scope": "tr_native"},
    {"domain": "c.com", "status": "published", "engine": "mangathemesia"},
    {"domain": "ml.com", "status": "published", "engine": "madara", "scope": "multilang"},
    {"domain": None, "status": "published", "engine": "madara"},
]


class SelectTests(unittest.TestCase):
    def test_all_skips_multilang_and_domainless(self):
        self.assertEqual(select_domains.select(ENTRIES), ["a.com", "b.com", "c.com"])

    def test_status_filter(self):
        self.assertEqual(select_domains.select(ENTRIES, status="published"), ["a.com", "c.com"])

    def test_missing_engine_counts_as_unknown(self):
        self.assertEqual(select_domains.select(ENTRIES, engine="unknown"), ["b.com"])

    def test_engine_and_status_combined(self):
        self.assertEqual(select_domains.select(ENTRIES, engine="madara", status="published"), ["a.com"])

    def test_explicit_domains_replace_filters(self):
        got = select_domains.select(ENTRIES, status="quarantined", domains=" X.com, a.com ,x.com")
        self.assertEqual(got, ["x.com", "a.com"])

    def test_no_match_is_empty(self):
        self.assertEqual(select_domains.select(ENTRIES, engine="initmanga"), [])

    def test_cli_prints_empty_line_for_missing_sources(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = select_domains.main(["--sources", os.path.join(ROOT, "no-such-file.json")])
        self.assertEqual(code, 0)
        self.assertEqual(buf.getvalue(), "\n")


if __name__ == "__main__":
    unittest.main()
