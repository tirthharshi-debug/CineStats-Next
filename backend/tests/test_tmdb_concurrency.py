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


if __name__ == "__main__":
    unittest.main()
