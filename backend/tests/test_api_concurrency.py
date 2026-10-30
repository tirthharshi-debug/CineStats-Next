"""API concurrency and job-isolation regression tests."""
import asyncio
import io
import unittest
from unittest.mock import patch

from fastapi import HTTPException, UploadFile

from app.routes import api


class UploadAdmissionTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.original_jobs = api._accepted_jobs
        api._accepted_jobs = 0
        self.release_background = asyncio.Event()
        self.background_tasks = set()

    async def asyncTearDown(self):
        self.release_background.set()
        if self.background_tasks:
            await asyncio.gather(*self.background_tasks, return_exceptions=True)
        async with api._admission_lock:
            api._accepted_jobs = self.original_jobs

    async def test_simultaneous_uploads_are_admitted_atomically(self):
        async def fake_process(_job_id, _contents):
            task = asyncio.current_task()
            self.background_tasks.add(task)
            try:
                await self.release_background.wait()
            finally:
                async with api._admission_lock:
                    api._accepted_jobs = max(0, api._accepted_jobs - 1)

        def make_upload():
            return UploadFile(filename="letterboxd.zip", file=io.BytesIO(b"zip-placeholder"))

        with patch.object(api, "_process_in_background", fake_process), patch.object(
            api, "_ensure_cleanup_started"
        ):
            outcomes = await asyncio.gather(
                *(api.upload_zip(make_upload()) for _ in range(api.MAX_ACCEPTED_JOBS + 1)),
                return_exceptions=True,
            )

        accepted = [outcome for outcome in outcomes if isinstance(outcome, dict)]
        rejected = [outcome for outcome in outcomes if isinstance(outcome, HTTPException)]
        self.assertEqual(len(accepted), api.MAX_ACCEPTED_JOBS)
        self.assertEqual(len(rejected), 1)
        self.assertEqual(rejected[0].status_code, 429)
        self.assertEqual(rejected[0].headers.get("Retry-After"), "15")
        self.assertEqual(len({outcome["job_id"] for outcome in accepted}), len(accepted))

        self.release_background.set()
        if self.background_tasks:
            await asyncio.gather(*self.background_tasks, return_exceptions=True)
        self.assertEqual(api._accepted_jobs, 0)


class JobIsolationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.original_jobs = api._jobs
        api._jobs = {}

    async def asyncTearDown(self):
        api._jobs = self.original_jobs

    async def test_results_endpoint_returns_only_requested_job(self):
        api._jobs["job-a"] = {
            "status": "done",
            "result": {"success": True, "stats": {"marker": "A"}},
        }
        api._jobs["job-b"] = {
            "status": "done",
            "result": {"success": True, "stats": {"marker": "B"}},
        }

        result_a = await api.get_results_by_id("job-a")
        result_b = await api.get_results_by_id("job-b")

        self.assertEqual(result_a["stats"]["marker"], "A")
        self.assertEqual(result_b["stats"]["marker"], "B")
        self.assertNotEqual(result_a, result_b)


if __name__ == "__main__":
    unittest.main()
