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


class WatchPosterTests(unittest.TestCase):
    def test_enrich_watch_posters_sets_and_handles_missing(self):
        from app.services.stats_service import enrich_watch_posters

        basic = {
            "first_watched": {"title": "First Film", "year": 1999, "date": "2024-01-01", "poster_path": None},
            "most_recent_watched": {"title": "Unmatched Film", "year": 2024, "date": "2024-05-01", "poster_path": None},
        }
        enriched = [
            {"title": "First Film", "year": 1999, "tmdb": {"poster_path": "/first.jpg", "year": 1999}},
            {"title": "Unmatched Film", "year": 2024, "tmdb": None},
        ]
        enrich_watch_posters(basic, enriched)
        self.assertEqual(basic["first_watched"]["poster_path"], "/first.jpg")
        self.assertIsNone(basic["most_recent_watched"]["poster_path"])


class GenrePosterTests(unittest.TestCase):
    def test_signature_picks_most_rewatched_and_breaks_ties(self):
        import pandas as pd
        from app.services.stats_service import compute_patron_stats

        ratings_df = pd.DataFrame([
            {"name": "Film A", "year": 2001, "rating": 4.0},
            {"name": "Film B", "year": 2002, "rating": 4.5},
            {"name": "Film C", "year": 2003, "rating": 5.0},
        ])
        diary_df = pd.DataFrame([
            {"name": "Film A", "year": 2001, "rating": 4.0},
            {"name": "Film A", "year": 2001, "rating": 4.0},
            {"name": "Film A", "year": 2001, "rating": 4.0},
            {"name": "Film B", "year": 2002, "rating": 4.5},
            {"name": "Film C", "year": 2003, "rating": 5.0},
        ])
        enriched = [
            {"title": "Film A", "year": 2001, "tmdb": {"title": "Film A", "year": 2001, "poster_path": "/a.jpg", "popularity": 5.0, "genres": [{"name": "Drama"}]}},
            {"title": "Film B", "year": 2002, "tmdb": {"title": "Film B", "year": 2002, "poster_path": "/b.jpg", "popularity": 90.0, "genres": [{"name": "Drama"}]}},
            {"title": "Film C", "year": 2003, "tmdb": {"title": "Film C", "year": 2003, "poster_path": "/c.jpg", "popularity": 10.0, "genres": [{"name": "Drama"}]}},
        ]
        ga = compute_patron_stats(enriched, diary_df, ratings_df)["genre_analytics"]
        self.assertEqual(ga["signature_film"]["title"], "Film A")
        self.assertEqual(ga["signature_film"]["watch_count"], 3)
        self.assertEqual(ga["signature_film"]["poster_path"], "/a.jpg")

        # When all films have 1 watch, tie-break by highest rating, then popularity.
        ga_tied = compute_patron_stats(enriched, diary_df.drop_duplicates(subset=["name"]), ratings_df)["genre_analytics"]
        self.assertEqual(ga_tied["signature_film"]["title"], "Film C")

    def test_highest_rated_avoids_duplicate_and_handles_missing_poster(self):
        import pandas as pd
        from app.services.stats_service import compute_patron_stats

        # 5 Drama films (avg 3.8) and 5 Sci-Fi films (avg 4.2); "Shared Peak" tops both!
        ratings_df = pd.DataFrame([
            {"name": "Shared Peak", "year": 2010, "rating": 5.0},
            {"name": "Drama 2", "year": 2011, "rating": 3.5},
            {"name": "Drama 3", "year": 2012, "rating": 3.5},
            {"name": "Drama 4", "year": 2013, "rating": 3.5},
            {"name": "Drama 5", "year": 2014, "rating": 3.5},
            {"name": "Sci-Fi Runner-Up", "year": 2015, "rating": 4.5},
            {"name": "Sci-Fi 3", "year": 2016, "rating": 4.0},
            {"name": "Sci-Fi 4", "year": 2017, "rating": 4.0},
            {"name": "Sci-Fi 5", "year": 2018, "rating": 3.5},
            {"name": "Drama 6", "year": 2019, "rating": 3.0},
        ])
        diary_df = pd.DataFrame([
            {"name": "Shared Peak", "year": 2010, "rating": 5.0},
            {"name": "Shared Peak", "year": 2010, "rating": 5.0},
        ])
        enriched = [
            {"title": "Shared Peak", "year": 2010, "tmdb": {"title": "Shared Peak", "year": 2010, "poster_path": "/shared.jpg", "popularity": 50.0, "genres": [{"name": "Drama"}, {"name": "Sci-Fi"}]}},
            {"title": "Sci-Fi Runner-Up", "year": 2015, "tmdb": {"title": "Sci-Fi Runner-Up", "year": 2015, "poster_path": "/runner.jpg", "popularity": 20.0, "genres": [{"name": "Sci-Fi"}]}},
            {"title": "Drama 2", "year": 2011, "tmdb": {"title": "Drama 2", "year": 2011, "poster_path": None, "popularity": 10.0, "genres": [{"name": "Drama"}]}},
            {"title": "Drama 3", "year": 2012, "tmdb": {"title": "Drama 3", "year": 2012, "poster_path": None, "popularity": 10.0, "genres": [{"name": "Drama"}]}},
            {"title": "Drama 4", "year": 2013, "tmdb": {"title": "Drama 4", "year": 2013, "poster_path": None, "popularity": 10.0, "genres": [{"name": "Drama"}]}},
            {"title": "Drama 5", "year": 2014, "tmdb": {"title": "Drama 5", "year": 2014, "poster_path": None, "popularity": 10.0, "genres": [{"name": "Drama"}]}},
            {"title": "Drama 6", "year": 2019, "tmdb": {"title": "Drama 6", "year": 2019, "poster_path": None, "popularity": 10.0, "genres": [{"name": "Drama"}]}},
            {"title": "Sci-Fi 3", "year": 2016, "tmdb": {"title": "Sci-Fi 3", "year": 2016, "poster_path": None, "popularity": 10.0, "genres": [{"name": "Sci-Fi"}]}},
            {"title": "Sci-Fi 4", "year": 2017, "tmdb": {"title": "Sci-Fi 4", "year": 2017, "poster_path": None, "popularity": 10.0, "genres": [{"name": "Sci-Fi"}]}},
            {"title": "Sci-Fi 5", "year": 2018, "tmdb": {"title": "Sci-Fi 5", "year": 2018, "poster_path": None, "popularity": 10.0, "genres": [{"name": "Sci-Fi"}]}},
        ]
        ga = compute_patron_stats(enriched, diary_df, ratings_df)["genre_analytics"]
        self.assertEqual(ga["most_watched_genre"], "Drama")
        self.assertEqual(ga["signature_film"]["title"], "Shared Peak")
        self.assertEqual(ga["favorite_genre"]["name"], "Sci-Fi")
        self.assertEqual(ga["favorite_genre"]["representative_film"]["title"], "Sci-Fi Runner-Up")
        self.assertEqual(ga["favorite_genre"]["representative_film"]["poster_path"], "/runner.jpg")

        # Empty archive returns None cleanly.
        empty_ga = compute_patron_stats([], pd.DataFrame(), pd.DataFrame())["genre_analytics"]
        self.assertIsNone(empty_ga["signature_film"])
        self.assertIsNone(empty_ga["favorite_genre"])

    def test_top_genre_combo_film_prefers_rewatches_and_avoids_duplicates(self):
        import pandas as pd
        from app.services.stats_service import compute_advanced_stats

        ratings_df = pd.DataFrame([
            {"name": "Five Star Single", "year": 2010, "rating": 5.0},
            {"name": "Rewatched Pair", "year": 2012, "rating": 4.0},
            {"name": "Third Pair", "year": 2014, "rating": 3.5},
        ])
        diary_df = pd.DataFrame([
            {"name": "Five Star Single", "year": 2010, "rating": 5.0},
            {"name": "Rewatched Pair", "year": 2012, "rating": 4.0},
            {"name": "Rewatched Pair", "year": 2012, "rating": 4.0},
            {"name": "Rewatched Pair", "year": 2012, "rating": 4.0},
            {"name": "Third Pair", "year": 2014, "rating": 3.5},
        ])
        enriched = [
            {"title": "Five Star Single", "year": 2010, "tmdb": {"title": "Five Star Single", "year": 2010, "poster_path": "/5.jpg", "popularity": 99.0, "genres": [{"name": "Drama"}, {"name": "Romance"}]}},
            {"title": "Rewatched Pair", "year": 2012, "tmdb": {"title": "Rewatched Pair", "year": 2012, "poster_path": "/rw.jpg", "popularity": 10.0, "genres": [{"name": "Drama"}, {"name": "Romance"}]}},
            {"title": "Third Pair", "year": 2014, "tmdb": {"title": "Third Pair", "year": 2014, "poster_path": "/3.jpg", "popularity": 5.0, "genres": [{"name": "Drama"}, {"name": "Romance"}]}},
        ]
        adv = compute_advanced_stats(enriched, diary_df, ratings_df)
        self.assertEqual(adv["top_genre_combo_film"]["title"], "Rewatched Pair")
        self.assertEqual(adv["top_genre_combo_film"]["watch_count"], 3)
        self.assertEqual(adv["top_genre_combo_film"]["poster_path"], "/rw.jpg")

        # When Rewatched Pair is already used by signature/favorite genre, pick runner-up with poster.
        adv_dedup = compute_advanced_stats(
            enriched, diary_df, ratings_df, exclude_keys={("rewatched pair", 2012)}
        )
        self.assertEqual(adv_dedup["top_genre_combo_film"]["title"], "Five Star Single")

        # Empty archive returns None cleanly.
        self.assertIsNone(compute_advanced_stats([], pd.DataFrame(), pd.DataFrame())["top_genre_combo_film"])

    def test_runtime_longest_and_shortest_include_poster_path(self):
        import pandas as pd
        from app.services.stats_service import compute_patron_stats

        enriched = [
            {"title": "Long Epic", "year": 1962, "tmdb": {"title": "Long Epic", "year": 1962, "runtime": 216, "poster_path": "/long.jpg"}},
            {"title": "Short Film", "year": 2020, "tmdb": {"title": "Short Film", "year": 2020, "runtime": 18, "poster_path": None}},
        ]
        ra = compute_patron_stats(enriched, pd.DataFrame(), pd.DataFrame())["runtime_analytics"]
        self.assertEqual(ra["longest_film"]["poster_path"], "/long.jpg")
        self.assertEqual(ra["longest_film"]["year"], 1962)
        self.assertIsNone(ra["shortest_film"]["poster_path"])
        self.assertEqual(ra["shortest_film"]["year"], 2020)

    def test_decade_leaderboard_returns_up_to_six(self):
        from app.services.stats_service import compute_decade_leaderboard

        decade_ratings = {
            1950: [4.8] * 5,
            1960: [4.6] * 5,
            1970: [4.4] * 5,
            1980: [4.2] * 5,
            1990: [4.0] * 5,
            2000: [3.8] * 5,
            2010: [3.6] * 5,
            2020: [5.0] * 4,  # fewer than 5 films -> excluded
        }
        board = compute_decade_leaderboard([], decade_ratings)
        self.assertEqual(len(board), 6)
        self.assertEqual([d["decade"] for d in board], ["1950s", "1960s", "1970s", "1980s", "1990s", "2000s"])

    def test_select_hero_backdrop_prefers_top_four_and_handles_missing(self):
        from app.services.stats_service import select_hero_backdrop

        # Order within top 4: 3rd (idx 2) -> 4th (idx 3) -> 1st (idx 0) -> 2nd (idx 1) -> None.
        all_four = [
            {"title": "Fav 1", "year": 2001, "backdrop_path": "/fav1.jpg"},
            {"title": "Fav 2", "year": 2002, "backdrop_path": "/fav2.jpg"},
            {"title": "Fav 3", "year": 2003, "backdrop_path": "/fav3.jpg"},
            {"title": "Fav 4", "year": 2004, "backdrop_path": "/fav4.jpg"},
        ]
        self.assertEqual(select_hero_backdrop(all_four, [], None)["title"], "Fav 3")

        missing_3rd = [{**f, "backdrop_path": None if i == 2 else f["backdrop_path"]} for i, f in enumerate(all_four)]
        self.assertEqual(select_hero_backdrop(missing_3rd, [], None)["title"], "Fav 4")

        missing_3rd_4th = [{**f, "backdrop_path": None if i in (2, 3) else f["backdrop_path"]} for i, f in enumerate(all_four)]
        self.assertEqual(select_hero_backdrop(missing_3rd_4th, [], None)["title"], "Fav 1")

        only_2nd = [{**f, "backdrop_path": f["backdrop_path"] if i == 1 else None} for i, f in enumerate(all_four)]
        self.assertEqual(select_hero_backdrop(only_2nd, [], None)["title"], "Fav 2")

        none_in_4 = [{**f, "backdrop_path": None} for f in all_four] + [{"title": "Fav 5", "year": 2005, "backdrop_path": "/fav5.jpg"}]
        self.assertIsNone(select_hero_backdrop(none_in_4, [], None))

        # When favorites list is empty, applies [2, 3, 0, 1] across top_rated[:4].
        top_rated = {"top_rated": [
            {"title": "Rated 1", "year": 2019, "backdrop_path": "/r1.jpg"},
            {"title": "Rated 2", "year": 2020, "backdrop_path": "/r2.jpg"},
            {"title": "Rated 3", "year": 2021, "backdrop_path": "/r3.jpg"},
        ]}
        self.assertEqual(
            select_hero_backdrop([], [], top_rated),
            {"backdrop_path": "/r3.jpg", "title": "Rated 3", "year": 2021},
        )
        self.assertIsNone(select_hero_backdrop([], [], {"top_rated": []}))

    def test_remakes_keep_distinct_posters_across_dashboard_sections(self):
        import pandas as pd
        from app.services.stats_service import (
            compute_basic_stats, compute_advanced_stats,
            compute_community_comparison, enrich_watch_posters,
        )

        diary_df = pd.DataFrame([
            {"name": "The Fall", "year": 2006, "rating": 5.0, "watched_date": pd.Timestamp("2024-01-01"), "is_rewatch": False},
            {"name": "The Fall", "year": 2024, "rating": 3.0, "watched_date": pd.Timestamp("2024-06-01"), "is_rewatch": True},
        ])
        ratings_df = pd.DataFrame([
            {"name": "The Fall", "year": 2006, "rating": 5.0},
            {"name": "The Fall", "year": 2024, "rating": 3.0},
        ])
        enriched = [
            {"title": "The Fall", "year": 2006, "tmdb": {"title": "The Fall", "year": 2006, "poster_path": "/fall2006.jpg", "vote_average": 7.8, "genres": []}},
            {"title": "The Fall", "year": 2024, "tmdb": {"title": "The Fall", "year": 2024, "poster_path": "/fall2024.jpg", "vote_average": 6.0, "genres": []}},
        ]
        basic = compute_basic_stats(diary_df, ratings_df, pd.DataFrame())
        enrich_watch_posters(basic, enriched)
        self.assertEqual(basic["first_watched"]["poster_path"], "/fall2006.jpg")
        self.assertEqual(basic["most_recent_watched"]["poster_path"], "/fall2024.jpg")

        adv = compute_advanced_stats(enriched, diary_df, ratings_df)
        self.assertEqual(adv["most_rewatched_film"]["poster_path"], "/fall2024.jpg")
        self.assertEqual(adv["most_rewatched_film"]["year"], 2024)

        comm = compute_community_comparison(enriched, ratings_df, diary_df)
        self.assertEqual(comm["latest_five_star"][0]["poster_path"], "/fall2006.jpg")


if __name__ == "__main__":
    unittest.main()
