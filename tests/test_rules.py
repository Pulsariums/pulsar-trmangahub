"""Unit tests for scripts/rules.py (shared quarantine rules)."""

import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import rules  # noqa: E402


def row(status, reason=None, http=None, functional=None):
    return {"status": status, "reason": reason or status, "http": http, "functional": functional,
            "functional_reason": "marker missing"}


def prev(status, failures):
    return {"status": status, "consecutiveFailures": failures}


class EvaluateTests(unittest.TestCase):
    def test_ok_is_published_and_resets(self):
        v = rules.evaluate(row("ok", functional=True), prev("failing", 2))
        self.assertEqual((v["status"], v["consecutiveFailures"], v["failing"]), ("published", 0, False))

    def test_cf_protected_resets(self):
        v = rules.evaluate(row("cf_protected"), prev("cf_protected_published", 2))
        self.assertEqual((v["status"], v["consecutiveFailures"]), ("cf_protected_published", 0))

    def test_unverified_statuses_return_none(self):
        self.assertIsNone(rules.evaluate(row("blocked"), prev("published", 0)))
        self.assertIsNone(rules.evaluate(row("other", http=403), None))
        self.assertIsNone(rules.evaluate(None, None))

    def test_dns_is_immediate(self):
        v = rules.evaluate(row("dead", reason="dns: Name or service not known"), prev("published", 0))
        self.assertEqual(v["status"], "quarantined")
        self.assertEqual(v["consecutiveFailures"], 1)

    def test_parked_is_immediate(self):
        self.assertEqual(rules.evaluate(row("parked"), None)["status"], "quarantined")

    def test_http_404_and_410_are_immediate(self):
        self.assertEqual(rules.evaluate(row("dead", reason="http 404", http=404), None)["status"], "quarantined")
        self.assertEqual(rules.evaluate(row("dead", reason="http 410", http=410), None)["status"], "quarantined")

    def test_non_immediate_failure_without_history_is_failing(self):
        v = rules.evaluate(row("dead", reason="timeout: ReadTimeout"), None)
        self.assertEqual((v["status"], v["consecutiveFailures"], v["failing"]), ("failing", 1, False))

    def test_5xx_and_ssl_are_failures_not_immediate(self):
        for reason in ("http 523", "http 525", "connect: SSLError"):
            v = rules.evaluate(row("dead", reason=reason, http=523 if "523" in reason else None), None)
            self.assertEqual(v["status"], "failing", reason)

    def test_second_failure_still_failing(self):
        v = rules.evaluate(row("dead", reason="timeout: x"), prev("failing", 1))
        self.assertEqual((v["status"], v["consecutiveFailures"]), ("failing", 2))

    def test_third_failure_quarantines(self):
        v = rules.evaluate(row("dead", reason="timeout: x"), prev("failing", 2))
        self.assertEqual((v["status"], v["consecutiveFailures"]), ("quarantined", 3))

    def test_published_kept_with_failing_flag_below_threshold(self):
        v = rules.evaluate(row("dead", reason="timeout: x"), prev("published", 0))
        self.assertEqual((v["status"], v["consecutiveFailures"], v["failing"]), ("published", 1, True))

    def test_cf_published_kept_with_failing_flag(self):
        v = rules.evaluate(row("dead", reason="http 500"), prev("cf_protected_published", 1))
        self.assertEqual((v["status"], v["failing"]), ("cf_protected_published", True))

    def test_published_quarantines_at_threshold(self):
        v = rules.evaluate(row("dead", reason="timeout: x"), prev("published", 2))
        self.assertEqual((v["status"], v["consecutiveFailures"]), ("quarantined", 3))

    def test_functional_false_is_a_failure(self):
        v = rules.evaluate(row("ok", functional=False), prev("published", 0))
        self.assertEqual(v["status"], "published")
        self.assertTrue(v["failing"])
        self.assertTrue(v["reason"].startswith("functional_false"))
        v = rules.evaluate(row("ok", functional=False), None)
        self.assertEqual(v["status"], "failing")

    def test_bad_previous_count_is_treated_as_zero(self):
        v = rules.evaluate(row("dead", reason="timeout: x"), {"status": "failing", "consecutiveFailures": "x"})
        self.assertEqual(v["consecutiveFailures"], 1)

    def test_is_multilang_defaults_to_tr_native(self):
        self.assertTrue(rules.is_multilang({"scope": "multilang"}))
        self.assertFalse(rules.is_multilang({"scope": "tr_native"}))
        self.assertFalse(rules.is_multilang({}))


if __name__ == "__main__":
    unittest.main(verbosity=2)
