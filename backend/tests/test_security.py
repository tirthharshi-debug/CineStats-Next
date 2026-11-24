import unittest
from types import SimpleNamespace
from unittest.mock import patch

import _env  # noqa: F401
from app import config, security


class RateLimiterTests(unittest.TestCase):
    def test_blocks_after_limit_and_reports_retry_time(self):
        limiter = security.RateLimiter()
        for _ in range(3):
            self.assertEqual(limiter.check("b", "1.2.3.4", 3, 60), 0.0)
        self.assertGreater(limiter.check("b", "1.2.3.4", 3, 60), 0.0)

    def test_buckets_and_clients_are_independent(self):
        limiter = security.RateLimiter()
        for _ in range(2):
            limiter.check("upload", "a", 2, 60)
        self.assertGreater(limiter.check("upload", "a", 2, 60), 0.0)
        self.assertEqual(limiter.check("upload", "b", 2, 60), 0.0)
        self.assertEqual(limiter.check("poll", "a", 2, 60), 0.0)

    def test_window_expires(self):
        limiter = security.RateLimiter()
        with patch("app.security.time.monotonic", return_value=1000.0):
            limiter.check("b", "x", 1, 10)
            self.assertGreater(limiter.check("b", "x", 1, 10), 0.0)
        with patch("app.security.time.monotonic", return_value=1011.0):
            self.assertEqual(limiter.check("b", "x", 1, 10), 0.0)


class ClientIpTests(unittest.TestCase):
    def _request(self, forwarded=None, host="10.0.0.1"):
        headers = {"x-forwarded-for": forwarded} if forwarded else {}
        return SimpleNamespace(headers=headers, client=SimpleNamespace(host=host))

    def test_ignores_forwarded_header_by_default(self):
        with patch.object(config, "TRUSTED_PROXY_HOPS", 0):
            self.assertEqual(security.client_ip(self._request("6.6.6.6")), "10.0.0.1")

    def test_uses_entry_added_by_trusted_proxy_not_client_supplied_one(self):
        with patch.object(config, "TRUSTED_PROXY_HOPS", 1):
            # A client can prepend a fake IP; the proxy's own entry is last.
            self.assertEqual(security.client_ip(self._request("6.6.6.6, 203.0.113.9")), "203.0.113.9")

    def test_falls_back_to_socket_when_header_too_short(self):
        with patch.object(config, "TRUSTED_PROXY_HOPS", 2):
            self.assertEqual(security.client_ip(self._request("203.0.113.9")), "10.0.0.1")


class TokenTests(unittest.TestCase):
    def test_token_round_trip_and_rejections(self):
        token = security.new_job_token()
        digest = security.hash_token(token)
        self.assertTrue(security.token_matches(token, digest))
        self.assertFalse(security.token_matches(token + "x", digest))
        self.assertFalse(security.token_matches(None, digest))
        self.assertFalse(security.token_matches("", digest))
        self.assertFalse(security.token_matches("a" * 500, digest))

    def test_job_id_format(self):
        self.assertTrue(security.JOB_ID_RE.match("a" * 32))
        for bad in ["", "../etc/passwd", "g" * 32, "a" * 31, "A" * 32, "a" * 33]:
            self.assertFalse(security.JOB_ID_RE.match(bad), bad)


if __name__ == "__main__":
    unittest.main()
