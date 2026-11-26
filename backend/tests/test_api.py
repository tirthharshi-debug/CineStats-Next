import time
import unittest
from unittest.mock import patch

import _env  # noqa: F401
from fastapi.testclient import TestClient

from app import config, security
from app.main import app
from app.routes import api
from app.services import job_store
from helpers import FakeTMDBService, letterboxd_export, make_zip


def wait_for(client, job_id, token, timeout=60):
    deadline = time.time() + timeout
    while time.time() < deadline:
        response = client.get(f"/api/progress/{job_id}", headers={"X-Job-Token": token})
        assert response.status_code == 200, response.text
        body = response.json()
        if body["status"] in ("done", "error"):
            return body
        time.sleep(0.2)
    raise AssertionError("job did not finish in time")


class ApiTestCase(unittest.TestCase):
    def setUp(self):
        security.limiter.reset()
        api._jobs.clear()
        patcher = patch("app.routes.api.TMDBService", FakeTMDBService)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.client_cm = TestClient(app)
        self.client = self.client_cm.__enter__()
        self.addCleanup(lambda: self.client_cm.__exit__(None, None, None))

    def upload(self, payload=None, name="export.zip"):
        payload = payload if payload is not None else letterboxd_export()
        return self.client.post("/api/upload", files={"file": (name, payload, "application/zip")})


class FullPipelineTests(ApiTestCase):
    def test_upload_to_pdf_and_delete(self):
        started = self.upload().json()
        job_id, token = started["job_id"], started["job_token"]
        headers = {"X-Job-Token": token}

        progress = wait_for(self.client, job_id, token)
        self.assertEqual(progress["status"], "done", progress)
        self.assertNotIn("basic_stats", progress)  # progress payload stays tiny

        results = self.client.get(f"/api/results/{job_id}", headers=headers)
        self.assertEqual(results.status_code, 200)
        stats = results.json()["stats"]
        self.assertEqual(stats["basic"]["total_films"], 36)
        self.assertNotIn("_decade_ratings", stats["pro"])
        self.assertTrue(stats["patron"]["genre_analytics"]["genre_distribution"])
        self.assertTrue(stats["decade_leaderboard"])
        self.assertTrue(stats["community_comparison"]["rated_higher"] or stats["community_comparison"]["rated_lower"])
        self.assertTrue(stats["monthly_activity"][0]["films"])
        self.assertEqual(results.json()["meta"]["lists_count"], 1)  # preamble list file parsed

        pdf = self.client.get(f"/api/export/pdf/{job_id}", headers=headers)
        self.assertEqual(pdf.status_code, 200)
        self.assertTrue(pdf.content.startswith(b"%PDF"))

        self.assertEqual(self.client.delete(f"/api/jobs/{job_id}", headers=headers).status_code, 200)
        self.assertEqual(self.client.get(f"/api/results/{job_id}", headers=headers).status_code, 404)

    def test_results_survive_a_memory_wipe_like_a_restart(self):
        started = self.upload().json()
        job_id, token = started["job_id"], started["job_token"]
        wait_for(self.client, job_id, token)
        api._jobs.clear()
        ok = self.client.get(f"/api/results/{job_id}", headers={"X-Job-Token": token})
        self.assertEqual(ok.status_code, 200)
        api._jobs.clear()
        bad = self.client.get(f"/api/results/{job_id}", headers={"X-Job-Token": "wrong"})
        self.assertEqual(bad.status_code, 404)

    def test_not_a_letterboxd_export_gives_friendly_error(self):
        started = self.upload(make_zip([("notes.txt", "hello")])).json()
        progress = wait_for(self.client, started["job_id"], started["job_token"])
        self.assertEqual(progress["status"], "error")
        self.assertIn("wrong reel", progress["error"])

    def test_corrupt_zip_gets_a_clear_message(self):
        started = self.upload(b"definitely not a zip").json()
        progress = wait_for(self.client, started["job_id"], started["job_token"])
        self.assertEqual(progress["status"], "error")
        self.assertEqual(progress["error"], api.BAD_ZIP_MESSAGE)

    def test_unexpected_failures_hide_internals(self):
        with patch("app.routes.api.parse_diary", side_effect=RuntimeError("secret path /srv/x")):
            started = self.upload().json()
            progress = wait_for(self.client, started["job_id"], started["job_token"])
        self.assertEqual(progress["error"], api.GENERIC_FAILURE)
        self.assertNotIn("secret", progress["error"])

    def test_too_many_films_is_rejected_with_clear_message(self):
        with patch.object(config, "MAX_UNIQUE_MOVIES", 5):
            started = self.upload().json()
            progress = wait_for(self.client, started["job_id"], started["job_token"])
        self.assertEqual(progress["status"], "error")
        self.assertIn("limit", progress["error"])


class AccessControlTests(ApiTestCase):
    def test_every_job_endpoint_requires_the_token(self):
        started = self.upload().json()
        job_id, token = started["job_id"], started["job_token"]
        wait_for(self.client, job_id, token)
        for method, path in [("get", f"/api/progress/{job_id}"), ("get", f"/api/results/{job_id}"),
                             ("get", f"/api/export/pdf/{job_id}"), ("delete", f"/api/jobs/{job_id}")]:
            no_token = getattr(self.client, method)(path)
            wrong = getattr(self.client, method)(path, headers={"X-Job-Token": "nope"})
            self.assertEqual(no_token.status_code, 404, path)
            self.assertEqual(wrong.status_code, 404, path)
            self.assertEqual(no_token.json(), wrong.json())  # indistinguishable from "no such job"

    def test_malformed_job_ids_are_rejected(self):
        for bad in ["../secrets", "A" * 32, "x" * 10, "%2e%2e"]:
            self.assertEqual(self.client.get(f"/api/results/{bad}", headers={"X-Job-Token": "t"}).status_code, 404)

    def test_legacy_latest_job_endpoints_are_gone(self):
        for path in ["/api/progress", "/api/results", "/api/export/pdf", "/api/cache-stats"]:
            self.assertEqual(self.client.get(path).status_code, 404, path)


class LimitTests(ApiTestCase):
    def test_upload_rate_limit(self):
        with patch.object(config, "UPLOADS_PER_HOUR", 2):
            codes = [self.upload(b"x", name="bad.txt").status_code for _ in range(3)]
        self.assertEqual(codes, [400, 400, 429])

    def test_rejects_non_zip_extension(self):
        self.assertEqual(self.upload(b"x", name="export.csv").status_code, 400)

    def test_oversized_upload_is_rejected_early(self):
        with patch.object(config, "MAX_UPLOAD_BYTES", 1024):
            response = self.upload(b"x" * 200_000)
        self.assertEqual(response.status_code, 413)

    def test_active_job_cap(self):
        with patch.object(config, "MAX_ACTIVE_JOBS", 0):
            self.assertEqual(self.upload().status_code, 429)

    def test_queued_job_runs_and_full_queue_returns_429(self):
        from app.routes import api
        api._jobs["active_dummy"] = {
            "status": "enriching", "current": 0, "total": 1,
            "result": None, "error": None, "token_hash": "h",
            "created_at": time.time(), "finished_at": None,
        }
        try:
            with patch.object(config, "MAX_ACTIVE_JOBS", 1), patch.object(config, "MAX_QUEUED_JOBS", 1):
                queued_resp = self.upload()
                self.assertEqual(queued_resp.status_code, 200)
                queued = queued_resp.json()
                prog = self.client.get(
                    f"/api/progress/{queued['job_id']}",
                    headers={"X-Job-Token": queued["job_token"]},
                )
                self.assertEqual(prog.status_code, 200)
                self.assertEqual(prog.json()["status"], "queued")

                # Queue is now full (1 active + 1 queued): next upload gets 429.
                full_resp = self.upload()
                self.assertEqual(full_resp.status_code, 429)

                # Release the active slot and verify the queued job finishes.
                api._jobs.pop("active_dummy", None)
                done = wait_for(self.client, queued["job_id"], queued["job_token"])
                self.assertEqual(done["status"], "done")
        finally:
            api._jobs.pop("active_dummy", None)


class HeaderTests(ApiTestCase):
    def test_security_headers_on_api_responses(self):
        response = self.client.get("/api/health")
        self.assertEqual(response.json(), {"status": "ok"})
        for header in ("X-Content-Type-Options", "X-Frame-Options", "Referrer-Policy", "Content-Security-Policy"):
            self.assertIn(header, response.headers)
        self.assertEqual(response.headers["Cache-Control"], "no-store")

    def test_cors_only_allows_configured_origin(self):
        allowed = config.CORS_ALLOWED_ORIGINS[0]
        ok = self.client.options("/api/upload", headers={
            "Origin": allowed, "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "x-job-token"})
        self.assertEqual(ok.headers.get("access-control-allow-origin"), allowed)
        bad = self.client.options("/api/upload", headers={
            "Origin": "https://evil.example", "Access-Control-Request-Method": "POST"})
        self.assertNotIn("access-control-allow-origin", bad.headers)


class JobStoreTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        await job_store.init()

    async def test_interrupted_jobs_are_failed_on_startup(self):
        await job_store.save("a" * 32, "hash", "enriching", time.time())
        await job_store.save("b" * 32, "hash", "done", time.time(), result={"ok": True}, finished_at=time.time())
        self.assertGreaterEqual(await job_store.fail_interrupted(), 1)
        self.assertEqual((await job_store.load("a" * 32))["status"], "error")
        self.assertIn("restarted", (await job_store.load("a" * 32))["error"])
        self.assertEqual((await job_store.load("b" * 32))["result"], {"ok": True})

    async def test_expired_records_are_purged(self):
        await job_store.save("c" * 32, "hash", "done", time.time() - 99999, finished_at=time.time() - 99999)
        await job_store.purge_expired(60)
        self.assertIsNone(await job_store.load("c" * 32))


if __name__ == "__main__":
    unittest.main()
