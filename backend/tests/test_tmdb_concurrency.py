"""Concurrency regression tests for TMDB enrichment controls."""
import asyncio
import unittest
from unittest.mock import patch

from app.services import tmdb_service


class TMDBConcurrencyTests(unittest.IsolatedAsyncioTestCase):
    async def test_concurrency_limit_is_shared_across_service_instances(self):
        original_limit = tmdb_service.CONCURRENCY
        # Use a small deterministic limit so the test is quick and observable.
        old_semaphore = tmdb_service._REQUEST_SEMAPHORE
        limit = 3
        tmdb_service.CONCURRENCY = limit
        tmdb_service._REQUEST_SEMAPHORE = asyncio.Semaphore(limit)
        active = 0
        peak_active = 0
        active_lock = asyncio.Lock()

        async def fake_enrich(_service, title, year=None):
            nonlocal active, peak_active
            async with active_lock:
                active += 1
                peak_active = max(peak_active, active)
            await asyncio.sleep(0.01)
            async with active_lock:
                active -= 1
            return {"title": title, "year": year}

        try:
            first = tmdb_service.TMDBService.__new__(tmdb_service.TMDBService)
            second = tmdb_service.TMDBService.__new__(tmdb_service.TMDBService)
            with patch.object(tmdb_service.TMDBService, "enrich_movie", fake_enrich):
                movies_a = [{"title": f"A{i}", "year": 2000 + i} for i in range(8)]
                movies_b = [{"title": f"B{i}", "year": 2010 + i} for i in range(8)]
                results_a, results_b = await asyncio.gather(
                    first.enrich_batch(movies_a),
                    second.enrich_batch(movies_b),
                )

            self.assertLessEqual(peak_active, limit)
            self.assertEqual([m["title"] for m in results_a], [m["title"] for m in movies_a])
            self.assertEqual([m["title"] for m in results_b], [m["title"] for m in movies_b])
            self.assertEqual(len(results_a), len(movies_a))
            self.assertEqual(len(results_b), len(movies_b))
        finally:
            tmdb_service._REQUEST_SEMAPHORE = old_semaphore
            tmdb_service.CONCURRENCY = original_limit

    async def test_rate_limiter_is_shared_between_service_instances(self):
        old_tokens = tmdb_service._RATE_TOKENS
        tmdb_service._RATE_TOKENS = asyncio.Semaphore(1)
        acquired = 0
        peak_acquired = 0
        lock = asyncio.Lock()

        class FakeResponse:
            status_code = 200
            headers = {}

            def raise_for_status(self):
                return None

            def json(self):
                return {"ok": True}

        class FakeClient:
            async def get(self, *_args, **_kwargs):
                nonlocal acquired, peak_acquired
                async with lock:
                    acquired += 1
                    peak_acquired = max(peak_acquired, acquired)
                await asyncio.sleep(0.01)
                async with lock:
                    acquired -= 1
                return FakeResponse()

        try:
            first = tmdb_service.TMDBService.__new__(tmdb_service.TMDBService)
            second = tmdb_service.TMDBService.__new__(tmdb_service.TMDBService)
            first.client = FakeClient()
            second.client = FakeClient()
            first._request_count = 0
            second._request_count = 0
            with patch.object(tmdb_service, "RATE_WINDOW", 0.02):
                responses = await asyncio.gather(
                    first._rate_limited_request("https://example.test/one", {}),
                    second._rate_limited_request("https://example.test/two", {}),
                )
            self.assertEqual(responses, [{"ok": True}, {"ok": True}])
            self.assertLessEqual(peak_acquired, 1)
        finally:
            tmdb_service._RATE_TOKENS = old_tokens


class FavoriteRedirectSecurityTests(unittest.IsolatedAsyncioTestCase):
    async def test_direct_letterboxd_url_is_parsed(self):
        service = tmdb_service.TMDBService.__new__(tmdb_service.TMDBService)
        calls = []

        class FakeResponse:
            status_code = 200
            headers = {}
            text = '<html><title>Arrival (2016) — Letterboxd</title></html>'
            url = "https://letterboxd.com/film/arrival/"

            def raise_for_status(self):
                return None

        class FakeClient:
            async def get(self, url, **kwargs):
                calls.append((url, kwargs))
                return FakeResponse()

        service.client = FakeClient()
        async def fake_enrich(title, year):
            return {"title": title, "year": year, "tmdb_id": 1, "poster_path": None}
        service.enrich_movie = fake_enrich

        results = await service.enrich_favorite_films(["https://letterboxd.com/film/arrival/"])
        self.assertTrue(results[0]["resolved"])
        self.assertEqual(results[0]["title"], "Arrival")
        self.assertEqual(results[0]["year"], 2016)
        self.assertFalse(calls[0][1]["follow_redirects"])

    async def test_short_link_redirect_to_letterboxd_is_allowed(self):
        service = tmdb_service.TMDBService.__new__(tmdb_service.TMDBService)
        calls = []

        class FakeResponse:
            def __init__(self, status_code, headers=None, text=""):
                self.status_code = status_code
                self.headers = headers or {}
                self.text = text

            def raise_for_status(self):
                return None

        class FakeClient:
            async def get(self, url, **kwargs):
                calls.append(url)
                if url == "https://boxd.it/abc":
                    return FakeResponse(302, {"Location": "https://letterboxd.com/film/arrival/"})
                return FakeResponse(200, text="<title>Arrival (2016) — Letterboxd</title>")

        service.client = FakeClient()
        async def fake_enrich(title, year):
            return {"title": title, "year": year, "tmdb_id": 1, "poster_path": None}
        service.enrich_movie = fake_enrich

        results = await service.enrich_favorite_films(["https://boxd.it/abc"])
        self.assertTrue(results[0]["resolved"])
        self.assertEqual(calls, [
            "https://boxd.it/abc",
            "https://letterboxd.com/film/arrival/",
        ])

    async def test_unsafe_redirect_target_is_never_requested(self):
        service = tmdb_service.TMDBService.__new__(tmdb_service.TMDBService)
        calls = []

        class FakeResponse:
            status_code = 302
            headers = {"Location": "http://127.0.0.1/admin"}
            text = ""

            def raise_for_status(self):
                return None

        class FakeClient:
            async def get(self, url, **kwargs):
                calls.append(url)
                return FakeResponse()

        service.client = FakeClient()
        results = await service.enrich_favorite_films(["https://boxd.it/abc"])
        self.assertFalse(results[0]["resolved"])
        self.assertEqual(calls, ["https://boxd.it/abc"])

    async def test_untrusted_redirect_host_is_never_requested(self):
        service = tmdb_service.TMDBService.__new__(tmdb_service.TMDBService)
        calls = []

        class FakeResponse:
            status_code = 302
            headers = {"Location": "https://evil.example/steal"}
            text = ""

            def raise_for_status(self):
                return None

        class FakeClient:
            async def get(self, url, **kwargs):
                calls.append(url)
                return FakeResponse()

        service.client = FakeClient()
        results = await service.enrich_favorite_films(["https://boxd.it/abc"])
        self.assertFalse(results[0]["resolved"])
        self.assertEqual(calls, ["https://boxd.it/abc"])


if __name__ == "__main__":
    unittest.main()
