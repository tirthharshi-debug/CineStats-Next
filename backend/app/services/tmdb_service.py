"""
TMDB API service — search, fetch details, cache integration.

Concurrent enrichment: movies are processed in parallel using asyncio.gather,
controlled by a concurrency semaphore and a sliding-window rate limiter that
guarantees at most RATE_LIMIT_PER_WINDOW API requests in any 10-second window.
"""
import httpx
import asyncio
import os
import re
from dotenv import load_dotenv
from app.database.db import get_cached_movie, cache_movie

# Load .env from project root
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), ".env"))

TMDB_API_KEY = os.getenv("TMDB_API_KEY")
TMDB_BASE_URL = "https://api.themoviedb.org/3"

# ─── Process-wide concurrency & rate-limit configuration ───
# Shared across all TMDBService instances in this process. Multiple OS processes
# or containers require a shared limiter (for example Redis) for global limits.
CONCURRENCY = 20
RATE_LIMIT_PER_WINDOW = 20
RATE_WINDOW = 1.0

_REQUEST_SEMAPHORE = asyncio.Semaphore(CONCURRENCY)
_RATE_TOKENS = asyncio.Semaphore(RATE_LIMIT_PER_WINDOW)


class TMDBService:
    def __init__(self):
        self.api_key = TMDB_API_KEY
        if not self.api_key:
            raise ValueError("TMDB_API_KEY not found in environment variables.")
        self.client = httpx.AsyncClient(
            timeout=30.0,
            limits=httpx.Limits(max_connections=50, max_keepalive_connections=40),
        )
        self._request_count = 0

        # Module-level gates ensure separate jobs share this process's capacity.

    async def close(self):
        await self.client.aclose()

    async def _release_rate_token(self):
        """Release a rate-limit token after the window elapses."""
        await asyncio.sleep(RATE_WINDOW)
        _RATE_TOKENS.release()

    async def _rate_limited_request(self, url: str, params: dict, retries: int = 3) -> dict | None:
        """Make a rate-limited request with retry logic."""
        for attempt in range(retries):
            try:
                # Acquire a rate-limit token (blocks if window is full)
                await _RATE_TOKENS.acquire()
                asyncio.create_task(self._release_rate_token())

                response = await self.client.get(url, params=params)
                self._request_count += 1

                if response.status_code == 429:
                    retry_after = int(response.headers.get("Retry-After", 5))
                    await asyncio.sleep(retry_after)
                    continue

                response.raise_for_status()
                return response.json()

            except httpx.HTTPStatusError as e:
                if e.response.status_code == 429:
                    await asyncio.sleep(5 * (attempt + 1))
                    continue
                if attempt == retries - 1:
                    return None

            except (httpx.RequestError, httpx.TimeoutException):
                if attempt == retries - 1:
                    return None
                await asyncio.sleep(2 * (attempt + 1))

        return None

    def _make_search_key(self, title: str, year: int | None) -> str:
        """Create a normalized search key from title + year."""
        clean = re.sub(r'[^\w\s]', '', title.lower().strip())
        clean = re.sub(r'\s+', '_', clean)
        return f"{clean}_{year}" if year else clean

    async def search_movie(self, title: str, year: int | None = None) -> dict | None:
        """Search for a movie by title and optional year."""
        params = {"api_key": self.api_key, "query": title}
        if year:
            params["year"] = year

        data = await self._rate_limited_request(
            f"{TMDB_BASE_URL}/search/movie", params
        )

        if not data or not data.get("results"):
            # Retry without year if no results
            if year:
                params.pop("year", None)
                data = await self._rate_limited_request(
                    f"{TMDB_BASE_URL}/search/movie", params
                )
            if not data or not data.get("results"):
                return None

        # Best match: prefer exact title + year match
        results = data["results"]
        for r in results:
            r_year = int(r.get("release_date", "0000")[:4]) if r.get("release_date") else None
            if r.get("title", "").lower() == title.lower() and r_year == year:
                return r

        # Fallback: first result
        return results[0]

    async def enrich_favorite_films(self, favorite_urls: list[str]) -> list[dict]:
        """Resolve Letterboxd profile favourites to TMDB metadata without changing order.

        Unresolvable links remain as explicit unresolved slots; they are never
        replaced with an unrelated highly-rated film.
        """
        from html import unescape
        from urllib.parse import urlparse

        results = []
        allowed_hosts = {"boxd.it", "www.boxd.it", "letterboxd.com", "www.letterboxd.com"}

        for index, favorite_url in enumerate(favorite_urls):
            item = {
                "favorite_url": favorite_url,
                "position": index + 1,
                "resolved": False,
                "title": "Favourite film",
                "year": None,
                "poster_path": None,
                "tmdb_id": None,
            }
            try:
                parsed_input = urlparse(favorite_url)
                if parsed_input.scheme != "https" or parsed_input.hostname not in allowed_hosts:
                    results.append(item)
                    continue

                response = await self.client.get(
                    favorite_url,
                    follow_redirects=True,
                    headers={"User-Agent": "CineStats/1.0 (Letterboxd favourites import)"},
                    timeout=15.0,
                )
                response.raise_for_status()
                final_url = urlparse(str(response.url))
                if final_url.hostname not in {"letterboxd.com", "www.letterboxd.com"}:
                    results.append(item)
                    continue

                title_match = re.search(
                    r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']+)',
                    response.text,
                    flags=re.IGNORECASE,
                )
                if not title_match:
                    title_match = re.search(
                        r'<title[^>]*>(.*?)</title>',
                        response.text,
                        flags=re.IGNORECASE | re.DOTALL,
                    )
                page_title = unescape(title_match.group(1)).strip() if title_match else ""
                page_title = re.sub(r"\s*[—|]\s*Letterboxd\s*$", "", page_title, flags=re.IGNORECASE)
                year_match = re.search(r"\((\d{4})\)", page_title)
                year = int(year_match.group(1)) if year_match else None
                title = re.sub(r"\s*\(\d{4}\)\s*$", "", page_title).strip()
                if not title:
                    results.append(item)
                    continue

                item["title"] = title
                item["year"] = year
                tmdb = await self.enrich_movie(title, year)
                if tmdb:
                    item.update({
                        "title": tmdb.get("title") or title,
                        "year": tmdb.get("year") or year,
                        "poster_path": tmdb.get("poster_path"),
                        "tmdb_id": tmdb.get("tmdb_id"),
                        "resolved": True,
                    })
            except Exception:
                # A single broken/unavailable favourite must not fail the import.
                pass
            results.append(item)

        return results

    async def get_movie_details(self, tmdb_id: int) -> dict | None:
        """Fetch full movie details with credits."""
        params = {
            "api_key": self.api_key,
            "append_to_response": "credits"
        }
        return await self._rate_limited_request(
            f"{TMDB_BASE_URL}/movie/{tmdb_id}", params
        )

    async def enrich_movie(self, title: str, year: int | None = None) -> dict | None:
        """Full pipeline: check cache → search → fetch details → cache result."""
        search_key = self._make_search_key(title, year)

        # 1. Check cache
        cached = await get_cached_movie(search_key)
        if cached:
            return cached

        # 2. Search TMDB
        search_result = await self.search_movie(title, year)
        if not search_result:
            return None

        tmdb_id = search_result["id"]

        # 3. Fetch full details
        details = await self.get_movie_details(tmdb_id)
        if not details:
            return None

        # 4. Extract structured data
        credits = details.get("credits", {})
        directors = [
            {"id": c["id"], "name": c["name"], "profile_path": c.get("profile_path")}
            for c in credits.get("crew", [])
            if c.get("job") == "Director"
        ]
        cast_members = [
            {"id": c["id"], "name": c["name"], "character": c.get("character", ""),
             "order": c.get("order", 999), "profile_path": c.get("profile_path")}
            for c in credits.get("cast", [])[:20]  # Top 20 cast
        ]
        genres = [{"id": g["id"], "name": g["name"]} for g in details.get("genres", [])]
        countries = [
            {"iso": c["iso_3166_1"], "name": c["name"]}
            for c in details.get("production_countries", [])
        ]
        spoken_langs = [
            {"iso": l["iso_639_1"], "name": l.get("english_name", l.get("name", ""))}
            for l in details.get("spoken_languages", [])
        ]

        release_year = None
        if details.get("release_date"):
            try:
                release_year = int(details["release_date"][:4])
            except (ValueError, IndexError):
                pass

        movie_data = {
            "tmdb_id": tmdb_id,
            "title": details.get("title", title),
            "year": release_year or year,
            "search_key": search_key,
            "raw_details": details,
            "genres": genres,
            "directors": directors,
            "cast_members": cast_members,
            "runtime": details.get("runtime"),
            "production_countries": countries,
            "original_language": details.get("original_language"),
            "spoken_languages": spoken_langs,
            "release_date": details.get("release_date"),
            "poster_path": details.get("poster_path"),
            "vote_average": details.get("vote_average"),
            "popularity": details.get("popularity"),
        }

        # 5. Cache it
        await cache_movie(movie_data)

        return movie_data

    async def enrich_batch(self, movies: list[dict], progress_callback=None) -> list[dict]:
        """
        Enrich a list of movies concurrently.

        Up to CONCURRENCY movies are enriched at the same time, with API
        requests globally throttled by the sliding-window rate limiter.
        Results are returned in the same order as the input list.
        """
        total = len(movies)
        results: list[dict | None] = [None] * total  # pre-sized for index assignment
        _completed = 0
        _progress_lock = asyncio.Lock()

        async def _enrich_one(index: int, movie: dict):
            nonlocal _completed
            async with _REQUEST_SEMAPHORE:
                enriched = await self.enrich_movie(movie["title"], movie.get("year"))
                results[index] = {**movie, "tmdb": enriched}
                async with _progress_lock:
                    _completed += 1
                    if progress_callback:
                        await progress_callback(_completed, total)

        await asyncio.gather(*(_enrich_one(i, m) for i, m in enumerate(movies)))
        return results
