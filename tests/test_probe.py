"""Unit tests for scripts/probe.py. The HTTP session is mocked; no network is used."""

import os
import sys
import unittest

import requests

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

import probe  # noqa: E402


class FakeResponse:
    def __init__(self, status=200, body=b"<html><body>ok</body></html>", headers=None, url="https://x.test/"):
        self.status_code = status
        self._body = body
        self.headers = {"Content-Type": "text/html; charset=utf-8"}
        self.headers.update(headers or {})
        self.url = url
        self.closed = False

    def iter_content(self, chunk_size=1):
        for i in range(0, len(self._body), chunk_size):
            yield self._body[i:i + chunk_size]

    def close(self):
        self.closed = True


class FakeSession:
    """Returns queued FakeResponse objects or raises queued exceptions, in order."""

    def __init__(self, *queue):
        self.queue = list(queue)
        self.calls = []
        self.headers = {}

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        item = self.queue.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item


class ClassifyTests(unittest.TestCase):
    def test_cloudflare_403_is_cf_protected(self):
        status, _ = probe.classify_response(403, {"server": "cloudflare"}, "<html>denied</html>", True)
        self.assertEqual(status, "cf_protected")

    def test_cf_mitigated_503_is_cf_protected(self):
        status, _ = probe.classify_response(503, {"cf-mitigated": "challenge"}, "", True)
        self.assertEqual(status, "cf_protected")

    def test_challenge_page_with_200_is_cf_protected(self):
        status, _ = probe.classify_response(200, {}, "<title>Just a moment...</title>", True)
        self.assertEqual(status, "cf_protected")

    def test_plain_cloudflare_server_on_200_is_ok(self):
        status, _ = probe.classify_response(200, {"server": "cloudflare"}, "<html>manga list</html>", True)
        self.assertEqual(status, "ok")

    def test_404_and_410_are_dead(self):
        self.assertEqual(probe.classify_response(404, {}, "", True)[0], "dead")
        self.assertEqual(probe.classify_response(410, {}, "", True)[0], "dead")

    def test_5xx_is_dead(self):
        self.assertEqual(probe.classify_response(500, {}, "", True)[0], "dead")

    def test_403_without_cloudflare_is_other(self):
        self.assertEqual(probe.classify_response(403, {}, "<html>no</html>", True)[0], "other")

    def test_non_html_200_is_other(self):
        self.assertEqual(probe.classify_response(200, {}, '{"a":1}', False)[0], "other")

    def test_parking_page_is_parked(self):
        body = "<html>This domain is for sale. Buy this domain today</html>"
        self.assertEqual(probe.classify_response(200, {}, body, True)[0], "parked")

    def test_turkish_parking_marker_is_parked(self):
        body = "<html>Bu alan adı satılık!</html>"
        self.assertEqual(probe.classify_response(200, {}, body, True)[0], "parked")

    def test_plain_html_is_ok(self):
        self.assertEqual(probe.classify_response(200, {}, "<html>Manga</html>", True)[0], "ok")


class EngineTests(unittest.TestCase):
    def test_madara(self):
        self.assertEqual(probe.detect_engine('<link href="/wp-content/themes/madara/x.css">'), "madara")

    def test_mangathemesia(self):
        self.assertEqual(probe.detect_engine('<div class="ts-breadcrumb">'), "mangathemesia")

    def test_initmanga(self):
        self.assertEqual(probe.detect_engine("<script src='initmanga.js'>"), "initmanga")

    def test_unknown(self):
        self.assertEqual(probe.detect_engine("<html>plain</html>"), "unknown")


class ProbeDomainTests(unittest.TestCase):
    def test_ok_site_records_engine_and_timeout(self):
        session = FakeSession(
            FakeResponse(200, b"<html>wp-content/themes/madara</html>", url="https://ok.test/"),
            FakeResponse(200, b"<div class='page-item-detail'>x</div>", url="https://ok.test/manga/"))
        res = probe.probe_domain(session, "ok.test")
        self.assertEqual(res["status"], "ok")
        self.assertEqual(res["http"], 200)
        self.assertEqual(res["engine_detected"], "madara")
        self.assertIsNone(res["moved_to"])
        self.assertEqual(res["attempts"], 1)
        self.assertTrue(res["functional"])
        url, kwargs = session.calls[0]
        self.assertEqual(url, "https://ok.test/")
        self.assertEqual(kwargs["timeout"], 15)
        self.assertIn("Chrome", kwargs["headers"]["User-Agent"])

    def test_redirect_sets_moved_to(self):
        session = FakeSession(FakeResponse(200, b"<html>x</html>", url="https://www.newhost.tr/tr/"))
        res = probe.probe_domain(session, "oldhost.tr")
        self.assertEqual(res["status"], "ok")
        self.assertEqual(res["moved_to"], "newhost.tr")
        self.assertEqual(res["finalUrl"], "https://www.newhost.tr/tr/")

    def test_same_host_after_www_redirect_is_not_moved(self):
        session = FakeSession(FakeResponse(200, b"<html>x</html>", url="https://www.same.tr/"))
        res = probe.probe_domain(session, "same.tr")
        self.assertIsNone(res["moved_to"])

    def test_dns_failure_is_dead_and_retried(self):
        exc = requests.exceptions.ConnectionError(
            "HTTPSConnectionPool(host='gone.tr', port=443): Max retries exceeded "
            "(Caused by NameResolutionError: Failed to resolve 'gone.tr' ([Errno -2] Name or service not known))")
        session = FakeSession(exc, exc)
        res = probe.probe_domain(session, "gone.tr")
        self.assertEqual(res["status"], "dead")
        self.assertTrue(res["reason"].startswith("dns"))
        self.assertEqual(res["attempts"], 2)

    def test_timeout_is_dead(self):
        exc = requests.exceptions.ReadTimeout("read timed out")
        session = FakeSession(exc, exc)
        res = probe.probe_domain(session, "slow.tr")
        self.assertEqual(res["status"], "dead")
        self.assertTrue(res["reason"].startswith("timeout"))
        self.assertEqual(res["attempts"], 2)

    def test_proxy_policy_block_is_dead_without_retry(self):
        exc = requests.exceptions.ProxyError("Cannot connect to proxy. Tunnel connection failed: 403 Forbidden")
        session = FakeSession(exc)
        res = probe.probe_domain(session, "blocked.tr")
        self.assertEqual(res["status"], "blocked")
        self.assertTrue(res["reason"].startswith("proxy_policy"))
        self.assertEqual(res["attempts"], 1)

    def test_503_cloudflare_is_cf_protected(self):
        session = FakeSession(FakeResponse(503, b"<html>x</html>", headers={"cf-mitigated": "challenge"}))
        res = probe.probe_domain(session, "cf.tr")
        self.assertEqual(res["status"], "cf_protected")

    def test_500_twice_is_dead_after_two_attempts(self):
        session = FakeSession(FakeResponse(500), FakeResponse(500))
        res = probe.probe_domain(session, "broken.tr")
        self.assertEqual(res["status"], "dead")
        self.assertEqual(res["attempts"], 2)

    def test_500_then_ok_recovers_on_second_attempt(self):
        session = FakeSession(FakeResponse(500), FakeResponse(200, b"<html>manga</html>"))
        res = probe.probe_domain(session, "flaky.tr")
        self.assertEqual(res["status"], "ok")
        self.assertEqual(res["attempts"], 2)

    def test_parked_domain(self):
        session = FakeSession(FakeResponse(200, b"<html>Domain is for sale</html>"))
        res = probe.probe_domain(session, "parked.tr")
        self.assertEqual(res["status"], "parked")

    def test_probe_one_uses_session_factory(self):
        created = []

        class Ctx(FakeSession):
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        def factory():
            s = Ctx(FakeResponse(200, b"<html>x</html>"))
            created.append(s)
            return s

        res = probe.probe_one("factory.tr", make_session=factory)
        self.assertEqual(res["status"], "ok")
        self.assertEqual(len(created), 1)


class TightenedFingerprintTests(unittest.TestCase):
    def test_bare_madara_word_is_not_madara(self):
        self.assertEqual(probe.detect_engine("<p>madara is a word in a blog post</p>"), "unknown")

    def test_madara_core_and_wp_manga_markers(self):
        self.assertEqual(probe.detect_engine("<script src='/plugins/madara-core/js.js'>"), "madara")
        self.assertEqual(probe.detect_engine("<body class='wp-manga'>"), "madara")

    def test_mangareader_word_is_mangathemesia(self):
        self.assertEqual(probe.detect_engine("<a href='mangareader.example'>"), "mangathemesia")

    def test_themesia_and_theme_path_markers(self):
        self.assertEqual(probe.detect_engine("<link href='/x/themesia.css'>"), "mangathemesia")
        self.assertEqual(probe.detect_engine("<link href='/wp-content/themes/mangareader/s.css'>"),
                         "mangathemesia")


class AliasTests(unittest.TestCase):
    def test_canonical_engine_maps_mangareader(self):
        self.assertEqual(probe.canonical_engine("MangaReader"), "mangathemesia")
        self.assertEqual(probe.canonical_engine("madara"), "madara")
        self.assertIsNone(probe.canonical_engine(None))

    def test_catalog_mangareader_is_not_a_mismatch_for_mangathemesia(self):
        rows = [{"key": "k", "name": "K", "domain": "k.tr", "formats": {"catalog": {"engine": "mangareader"}}}]
        fake = {"status": "ok", "reason": "http 200", "http": 200, "finalUrl": "https://k.tr/",
                "moved_to": None, "engine_detected": "mangathemesia", "ms": 1, "attempts": 1,
                "functional": True, "functional_reason": "x"}
        res = _run_main_with(rows, lambda domain: fake)
        self.assertFalse(res[0]["engine_mismatch"])
        self.assertEqual(res[0]["catalog_engine"], "mangareader")

    def test_real_mismatch_is_reported(self):
        rows = [{"key": "k", "name": "K", "domain": "k.tr", "formats": {"catalog": {"engine": "madara"}}}]
        fake = {"status": "ok", "reason": "http 200", "http": 200, "finalUrl": "https://k.tr/",
                "moved_to": None, "engine_detected": "mangathemesia", "ms": 1, "attempts": 1,
                "functional": None, "functional_reason": "x"}
        res = _run_main_with(rows, lambda domain: fake)
        self.assertTrue(res[0]["engine_mismatch"])


def _run_main_with(source_rows, fake_probe_one):
    """Run probe.main on a temp input with probe_one replaced; return results list."""
    import json
    import tempfile
    from unittest import mock

    with tempfile.TemporaryDirectory() as tmp:
        inp = os.path.join(tmp, "in.json")
        outp = os.path.join(tmp, "out.json")
        with open(inp, "w", encoding="utf-8") as fh:
            json.dump({"sources": source_rows}, fh)
        with mock.patch.object(probe, "probe_one", side_effect=fake_probe_one):
            code = probe.main(["--input", inp, "--output", outp, "--workers", "2"])
        assert code == 0
        with open(outp, encoding="utf-8") as fh:
            return json.load(fh)["results"]


class FunctionalTests(unittest.TestCase):
    def test_madara_listing_marker_gives_true(self):
        session = FakeSession(
            FakeResponse(200, b"<html>wp-content/themes/madara</html>", url="https://m.tr/"),
            FakeResponse(200, b"<div class='page-item-detail'>", url="https://m.tr/manga/"))
        res = probe.probe_domain(session, "m.tr")
        self.assertIs(res["functional"], True)
        self.assertEqual(session.calls[1][0], "https://m.tr/manga/")

    def test_madara_missing_listing_falls_back_to_root_then_false(self):
        session = FakeSession(
            FakeResponse(200, b"<html>wp-content/themes/madara</html>", url="https://m.tr/"),
            FakeResponse(404, b"", url="https://m.tr/manga/"),
            FakeResponse(200, b"<html>no list here</html>", url="https://m.tr/"))
        res = probe.probe_domain(session, "m.tr")
        self.assertEqual(res["status"], "ok")
        self.assertIs(res["functional"], False)
        self.assertIn("not found", res["functional_reason"])
        self.assertEqual([c[0] for c in session.calls[1:]], ["https://m.tr/manga/", "https://m.tr/"])

    def test_madara_marker_on_root_fallback_gives_true(self):
        session = FakeSession(
            FakeResponse(200, b"<html>wp-content/themes/madara</html>", url="https://m.tr/"),
            FakeResponse(200, b"<html>empty listing</html>", url="https://m.tr/manga/"),
            FakeResponse(200, b"<div class='c-tabs-item'>", url="https://m.tr/"))
        res = probe.probe_domain(session, "m.tr")
        self.assertIs(res["functional"], True)

    def test_mangathemesia_listing_uses_page_query(self):
        session = FakeSession(
            FakeResponse(200, b"<div class='ts-breadcrumb'>", url="https://t.tr/"),
            FakeResponse(200, b"<div class='bsx'>", url="https://t.tr/manga/?page=1"))
        res = probe.probe_domain(session, "t.tr")
        self.assertIs(res["functional"], True)
        self.assertEqual(session.calls[1][0], "https://t.tr/manga/?page=1")

    def test_mangathemesia_without_markers_is_false(self):
        session = FakeSession(
            FakeResponse(200, b"<div class='ts-breadcrumb'>", url="https://t.tr/"),
            FakeResponse(200, b"<html>nothing</html>", url="https://t.tr/manga/?page=1"))
        res = probe.probe_domain(session, "t.tr")
        self.assertIs(res["functional"], False)

    def test_unknown_engine_is_none_and_makes_no_extra_request(self):
        session = FakeSession(FakeResponse(200, b"<html>plain</html>"))
        res = probe.probe_domain(session, "p.tr")
        self.assertIsNone(res["functional"])
        self.assertEqual(len(session.calls), 1)

    def test_non_ok_status_is_not_checked(self):
        session = FakeSession(FakeResponse(503, b"<html>x</html>", headers={"cf-mitigated": "challenge"}))
        res = probe.probe_domain(session, "cf.tr")
        self.assertEqual(res["status"], "cf_protected")
        self.assertIsNone(res["functional"])
        self.assertEqual(len(session.calls), 1)

    def test_functional_request_failure_is_none(self):
        dns = requests.exceptions.ConnectionError("Failed to resolve 'm.tr' (Name or service not known)")
        session = FakeSession(
            FakeResponse(200, b"<html>wp-content/themes/madara</html>", url="https://m.tr/"),
            dns, dns)
        res = probe.probe_domain(session, "m.tr")
        self.assertEqual(res["status"], "ok")
        self.assertIsNone(res["functional"])
        self.assertIn("functional request failed", res["functional_reason"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
