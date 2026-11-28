import unittest
from unittest.mock import AsyncMock, patch

import _env  # noqa: F401
from app.database import db
from app.services.tmdb_service import TMDBService


def result(title, year, original=None):
    return {"id": hash((title, year)) % 1000, "title": title, "original_title": original or title,
            "release_date": f"{year}-05-05"}


class MatchSelectionTests(unittest.TestCase):
    def test_prefers_exact_title_and_year(self):
        results = [result("Dune", 2021), result("Dune", 1984)]
        self.assertEqual(TMDBService._pick_best_match(results, "Dune", 1984)["release_date"][:4], "1984")

    def test_tolerates_one_year_release_difference(self):
        results = [result("Other Film", 2000), result("Cool Film", 2011)]
        self.assertEqual(TMDBService._pick_best_match(results, "Cool Film", 2010)["title"], "Cool Film")

    def test_matches_original_title(self):
        results = [result("Parasite", 2019, original="기생충"), result("Parasite", 1982)]
        self.assertEqual(TMDBService._pick_best_match(results, "기생충", 2019)["release_date"][:4], "2019")

    def test_rejects_unrelated_and_substring_collisions(self):
        # "The Fall" (2006) must NOT match "Jane Doe: The Harder They Fall" (2006).
        results = [
            {"id": 1, "title": "Jane Doe: The Harder They Fall", "original_title": "Jane Doe: The Harder They Fall", "release_date": "2006-03-01", "popularity": 50.0},
            {"id": 2, "title": "The Fall", "original_title": "The Fall", "release_date": "2006-09-09", "popularity": 20.0},
        ]
        self.assertEqual(TMDBService._pick_best_match(results, "The Fall", 2006)["id"], 2)

        # If only an unrelated or substring title is returned, return None (never results[0]).
        bad_only = [results[0], result("Unrelated", 1950)]
        self.assertIsNone(TMDBService._pick_best_match(bad_only, "The Fall", 2006))
        self.assertIsNone(TMDBService._pick_best_match(bad_only, "Missing", 2020))

    def test_festival_vs_theatrical_year_offset_prefers_major_feature(self):
        # Letterboxd logs festival premiere year (2022) for "Three of Us",
        # while TMDB indexes theatrical release as 2023-11-03.
        candidates = [
            {"id": 1001, "title": "Three of Us", "original_title": "Three of Us",
             "release_date": "2022-05-01", "popularity": 0.6, "vote_count": 1},
            {"id": 2002, "title": "Three of Us", "original_title": "Three of Us",
             "release_date": "2023-11-03", "popularity": 8.4, "vote_count": 42},
        ]
        chosen = TMDBService._pick_best_match(candidates, "Three of Us", 2022)
        self.assertIsNotNone(chosen)
        self.assertEqual(chosen["id"], 2002)


class CredentialTests(unittest.TestCase):
    def test_key_goes_in_query_only_without_bearer_token(self):
        with patch.dict("os.environ", {"TMDB_API_KEY": "k", "TMDB_READ_ACCESS_TOKEN": ""}):
            self.assertEqual(TMDBService()._auth_params({"q": 1}), {"q": 1, "api_key": "k"})
        with patch.dict("os.environ", {"TMDB_API_KEY": "k", "TMDB_READ_ACCESS_TOKEN": "tok"}):
            service = TMDBService()
            self.assertEqual(service._auth_params({"q": 1}), {"q": 1})
            self.assertEqual(service.client.headers["authorization"], "Bearer tok")

    def test_missing_credentials_raise(self):
        with patch.dict("os.environ", {"TMDB_API_KEY": "", "TMDB_READ_ACCESS_TOKEN": ""}):
            with self.assertRaises(RuntimeError):
                TMDBService()


class MissCacheTests(unittest.IsolatedAsyncioTestCase):
    async def test_unmatched_titles_are_not_searched_twice(self):
        await db.init_db()
        service = TMDBService()
        try:
            with patch.object(service, "search_movie", AsyncMock(return_value=None)) as search:
                self.assertIsNone(await service.enrich_movie("Nonexistent Film 12345", 1999))
                self.assertIsNone(await service.enrich_movie("Nonexistent Film 12345", 1999))
                self.assertEqual(search.await_count, 1)
        finally:
            await service.close()

    async def test_stale_bad_cache_row_is_refreshed(self):
        await db.init_db()
        await db.cache_movie({
            "tmdb_id": 999999,
            "title": "Jane Doe: The Harder They Fall",
            "year": 2006,
            "search_key": "the_fall_2006",
            "raw_details": {"id": 999999, "title": "Jane Doe: The Harder They Fall", "original_title": "Jane Doe: The Harder They Fall"},
            "genres": [],
            "directors": [],
            "cast_members": [],
            "runtime": 90,
            "production_countries": [],
            "original_language": "en",
            "spoken_languages": [],
            "release_date": "2006-03-01",
            "poster_path": "/bad.jpg",
            "backdrop_path": "/bad-bd.jpg",
            "vote_average": 6.0,
            "popularity": 10.0,
        })
        service = TMDBService()
        try:
            with patch.object(service, "search_movie", AsyncMock(return_value={"id": 14784})) as search, \
                 patch.object(service, "get_movie_details", AsyncMock(return_value={
                     "id": 14784, "title": "The Fall", "original_title": "The Fall",
                     "release_date": "2006-09-09", "poster_path": "/fall.jpg", "backdrop_path": "/fall-bd.jpg",
                     "runtime": 117, "genres": [{"id": 18, "name": "Drama"}],
                     "credits": {"crew": [], "cast": []}, "production_countries": [], "spoken_languages": [],
                 })):
                refreshed = await service.enrich_movie("The Fall", 2006)
                self.assertEqual(search.await_count, 1)
                self.assertEqual(refreshed["title"], "The Fall")
                self.assertEqual(refreshed["poster_path"], "/fall.jpg")
        finally:
            await service.close()

    async def test_three_of_us_2022_resolves_to_2023_feature_and_refreshes_v1_cache(self):
        await db.init_db()
        await db.cache_movie({
            "tmdb_id": 1001,
            "title": "Three of Us",
            "year": 2022,
            "search_key": "three_of_us_2022",
            "raw_details": {"id": 1001, "title": "Three of Us", "original_title": "Three of Us"},
            "genres": [],
            "directors": [],
            "cast_members": [],
            "runtime": 40,
            "production_countries": [],
            "original_language": "en",
            "spoken_languages": [],
            "release_date": "2022-05-01",
            "poster_path": "/short.jpg",
            "backdrop_path": None,
            "vote_average": 5.0,
            "popularity": 0.6,
            "match_version": 1,
        })
        service = TMDBService()
        try:
            search_payload = {
                "results": [
                    {"id": 1001, "title": "Three of Us", "original_title": "Three of Us",
                     "release_date": "2022-05-01", "popularity": 0.6, "vote_count": 1},
                    {"id": 2002, "title": "Three of Us", "original_title": "Three of Us",
                     "release_date": "2023-11-03", "popularity": 8.4, "vote_count": 42},
                ]
            }
            details_payload = {
                "id": 2002, "title": "Three of Us", "original_title": "Three of Us",
                "release_date": "2023-11-03", "poster_path": "/threeofus.jpg",
                "backdrop_path": "/threeofus-bd.jpg", "runtime": 99,
                "genres": [{"id": 18, "name": "Drama"}],
                "credits": {"crew": [{"id": 10, "name": "Avinash Arun", "job": "Director"}], "cast": []},
                "production_countries": [{"iso_3166_1": "IN", "name": "India"}],
                "spoken_languages": [{"iso_639_1": "hi", "english_name": "Hindi"}],
                "vote_average": 7.4, "popularity": 8.4,
            }
            with patch.object(service, "_rate_limited_request", AsyncMock(return_value=search_payload)) as req, \
                 patch.object(service, "get_movie_details", AsyncMock(return_value=details_payload)):
                enriched = await service.enrich_movie("Three of Us", 2022)
                self.assertEqual(req.await_count, 1)
                self.assertNotIn("year", req.await_args.args[1])
                self.assertEqual(enriched["tmdb_id"], 2002)
                self.assertEqual(enriched["runtime"], 99)
                self.assertEqual(enriched["year"], 2023)
        finally:
            await service.close()


if __name__ == "__main__":
    unittest.main()
