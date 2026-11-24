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

    def test_falls_back_to_first_result(self):
        results = [result("Unrelated", 1950), result("Another", 1960)]
        self.assertEqual(TMDBService._pick_best_match(results, "Missing", 2020)["title"], "Unrelated")


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
            with self.assertRaises(ValueError):
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


if __name__ == "__main__":
    unittest.main()
