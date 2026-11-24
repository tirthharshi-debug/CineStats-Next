"""
TMDB API service — search, fetch details, cache integration.

Concurrent enrichment: movies are processed in parallel using asyncio.gather,
controlled by a concurrency semaphore and a sliding-window rate limiter that
guarantees at most RATE_LIMIT_PER_WINDOW API requests in any 10-second window.
"""
import httpx
import asyncio
import logging
import os
import re
from app import config
from app.database.db import get_cached_movie, cache_movie, is_recent_miss, record_miss

logger = logging.getLogger("cinestats.tmdb")

# httpx logs every request URL at INFO level, and TMDB's v3 key travels in the
# query string. Keep that logger quiet so the key can never land in log files.
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

TMDB_BASE_URL = "https://api.themoviedb.org/3"

# ─── Concurrency & rate-limit configuration ───
# TMDB's legacy 40-req/10s limit was removed in 2019.
# Current soft limits: ~40 requests/second, ~20 simultaneous connections per IP.
# We target half the request limit for safe headroom.
CONCURRENCY = 20               # max movies being enriched at the same time
RATE_LIMIT_PER_WINDOW = 20     # max API requests per sliding window
RATE_WINDOW = 1.0              # window size in seconds


class TMDBService:
    def __init__(self):
        # Read at construction time so tests and deployments can set it late.
        # TMDB_READ_ACCESS_TOKEN (v4 bearer token) is preferred: it keeps the
        # credential out of URLs. TMDB_API_KEY (v3) still works as a fallback.
        self.read_token = os.getenv("TMDB_READ_ACCESS_TOKEN") or None
        self.api_key = os.getenv("TMDB_API_KEY") or None
        if not (self.read_token or self.api_key):
            raise ValueError("TMDB_API_KEY or TMDB_READ_ACCESS_TOKEN must be set.")
        headers = {"Authorization": f"Bearer {self.read_token}"} if self.read_token else {}
        self.client = httpx.AsyncClient(
            timeout=30.0,
            headers=headers,
            limits=httpx.Limits(max_connections=50, max_keepalive_connections=40),
        )
        self._request_count = 0

        # Concurrency gate: at most CONCURRENCY movies enriched at once
        self._semaphore = asyncio.Semaphore(CONCURRENCY)

        # Sliding-window rate limiter: at most RATE_LIMIT_PER_WINDOW API
        # requests in any RATE_WINDOW-second period.  Each request acquires a
        # token; a background task releases it after RATE_WINDOW seconds.
        self._rate_tokens = asyncio.Semaphore(RATE_LIMIT_PER_WINDOW)

    async def close(self):
        await self.client.aclose()

    async def _release_rate_token(self):
        """Release a rate-limit token after the window elapses."""
        await asyncio.sleep(RATE_WINDOW)
        self._rate_tokens.release()

    async def _rate_limited_request(self, url: str, params: dict, retries: int = 3) -> dict | None:
        """Make a rate-limited request, retrying only on transient failures."""
        for attempt in range(retries):
            try:
                # Acquire a rate-limit token (blocks if window is full)
                await self._rate_tokens.acquire()
                asyncio.create_task(self._release_rate_token())

                response = await self.client.get(url, params=params)
                self._request_count += 1

                if response.status_code == 429:
                    try:
                        retry_after = min(30, max(1, int(response.headers.get("Retry-After", 5))))
                    except ValueError:
                        retry_after = 5
                    await asyncio.sleep(retry_after)
                    continue

                if response.status_code >= 500:
                    await asyncio.sleep(2 * (attempt + 1))
                    continue

                if response.status_code >= 400:
                    # 401/404 and friends will not improve on retry.
                    logger.warning("TMDB returned HTTP %s", response.status_code)
                    return None

                return response.json()

            except (httpx.RequestError, httpx.TimeoutException):
                if attempt == retries - 1:
                    return None
                await asyncio.sleep(2 * (attempt + 1))

        return None

    def _auth_params(self, params: dict) -> dict:
        """Add the v3 API key only when no bearer token is configured."""
        if not self.read_token:
            params = {**params, "api_key": self.api_key}
        return params

    def _make_search_key(self, title: str, year: int | None) -> str:
        """Create a normalized search key from title + year."""
        clean = re.sub(r'[^\w\s]', '', title.lower().strip())
        clean = re.sub(r'\s+', '_', clean)
        return f"{clean}_{year}" if year else clean

    async def search_movie(self, title: str, year: int | None = None) -> dict | None:
        """Search for a movie by title and optional year."""
        params = self._auth_params({"query": title})
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

        return self._pick_best_match(data["results"], title, year)

    @staticmethod
    def _release_year(result: dict) -> int | None:
        date = result.get("release_date") or ""
        try:
            return int(date[:4])
        except ValueError:
            return None

    @classmethod
    def _pick_best_match(cls, results: list[dict], title: str, year: int | None) -> dict:
        """
        Prefer an exact title + year match, then an exact title within one year
        (festival vs. general release dates), then any result in that year range,
        and only then fall back to TMDB's top result.
        """
        wanted = title.strip().lower()

        def title_matches(r):
            return wanted in (str(r.get("title", "")).lower(), str(r.get("original_title", "")).lower())

        if year:
            for r in results:
                if title_matches(r) and cls._release_year(r) == year:
                    return r
            for r in results:
                ry = cls._release_year(r)
                if title_matches(r) and ry is not None and abs(ry - year) <= 1:
                    return r
            for r in results:
                ry = cls._release_year(r)
                if ry is not None and abs(ry - year) <= 1:
                    return r
        else:
            for r in results:
                if title_matches(r):
                    return r
        return results[0]

    async def get_movie_details(self, tmdb_id: int) -> dict | None:
        """Fetch full movie details with credits."""
        params = self._auth_params({"append_to_response": "credits"})
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

        if await is_recent_miss(search_key, config.TMDB_MISS_TTL_DAYS):
            return None

        # 2. Search TMDB
        search_result = await self.search_movie(title, year)
        if not search_result:
            await record_miss(search_key)
            return None

        tmdb_id = search_result["id"]

        # 3. Fetch full details. A failed request (network error, rate limit)
        # is not remembered as a miss, so a later upload can try again.
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

        # Credits are already distilled into directors/cast_members above, so the
        # stored copy drops them to keep the cache small.
        slim_details = {k: v for k, v in details.items() if k != "credits"}

        movie_data = {
            "tmdb_id": tmdb_id,
            "title": details.get("title", title),
            "year": release_year or year,
            "search_key": search_key,
            "raw_details": slim_details,
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

        # 5. Cache it, then hand back a copy without the bulky raw payload.
        await cache_movie(movie_data)

        return {k: v for k, v in movie_data.items() if k != "raw_details"}

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
            async with self._semaphore:
                enriched = await self.enrich_movie(movie["title"], movie.get("year"))
                results[index] = {**movie, "tmdb": enriched}
                async with _progress_lock:
                    _completed += 1
                    if progress_callback:
                        await progress_callback(_completed, total)

        await asyncio.gather(*(_enrich_one(i, m) for i, m in enumerate(movies)))
        return results
