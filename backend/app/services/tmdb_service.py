"""
TMDB API service — search, fetch details, cache integration.

Concurrent enrichment: movies are processed in parallel using asyncio.gather,
controlled by a concurrency semaphore and a sliding-window rate limiter that
guarantees at most RATE_LIMIT_PER_WINDOW API requests in any 10-second window.
"""
import asyncio
import logging
import os
import re
import unicodedata
import weakref

import httpx
from app import config
from app.database.db import get_cached_movie, cache_movie, is_recent_miss, record_miss

logger = logging.getLogger("cinestats.tmdb")

# httpx logs every request URL at INFO level, and TMDB's v3 key travels in the
# query string. Keep that logger quiet so the key can never land in log files.
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

TMDB_BASE_URL = "https://api.themoviedb.org/3"

# Shared 30 req/s ceiling across active jobs (headroom below TMDB's ~40 req/s limit).
CONCURRENCY = 30
RATE_LIMIT_PER_WINDOW = 30
RATE_WINDOW = 1.0

# Shared per-event-loop rate-limit bucket so concurrent TMDBService instances
# cannot exceed RATE_LIMIT_PER_WINDOW combined, while separate test event loops
# remain isolated.
_loop_rate_buckets: weakref.WeakKeyDictionary[
    asyncio.AbstractEventLoop, tuple[asyncio.Semaphore, set[asyncio.Task]]
] = weakref.WeakKeyDictionary()


def _get_shared_rate_bucket() -> tuple[asyncio.Semaphore, set[asyncio.Task]]:
    loop = asyncio.get_running_loop()
    bucket = _loop_rate_buckets.get(loop)
    if bucket is None:
        bucket = (asyncio.Semaphore(RATE_LIMIT_PER_WINDOW), set())
        _loop_rate_buckets[loop] = bucket
    return bucket


async def _release_rate_token(semaphore: asyncio.Semaphore) -> None:
    """Release a shared rate-limit token after the window elapses."""
    try:
        await asyncio.sleep(RATE_WINDOW)
    finally:
        semaphore.release()


class TMDBService:
    def __init__(self):
        # Read at construction time so tests and deployments can set it late.
        # TMDB_READ_ACCESS_TOKEN (v4 bearer token) is preferred: it keeps the
        # credential out of URLs. TMDB_API_KEY (v3) still works as a fallback.
        self.read_token = os.getenv("TMDB_READ_ACCESS_TOKEN") or None
        self.api_key = os.getenv("TMDB_API_KEY") or None
        if not (self.read_token or self.api_key):
            raise RuntimeError("TMDB_API_KEY or TMDB_READ_ACCESS_TOKEN must be set.")
        headers = {"Authorization": f"Bearer {self.read_token}"} if self.read_token else {}
        self.client = httpx.AsyncClient(
            timeout=30.0,
            headers=headers,
            limits=httpx.Limits(max_connections=50, max_keepalive_connections=40),
        )
        self._request_count = 0

        # Concurrency gate: at most CONCURRENCY movies enriched at once
        self._semaphore = asyncio.Semaphore(CONCURRENCY)

        # Track release tasks created by this instance so close() can clean them up
        # without cancelling other concurrent jobs' tasks.
        self._release_tasks: set[asyncio.Task] = set()

    async def close(self):
        tasks = list(self._release_tasks)
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._release_tasks.clear()
        await self.client.aclose()

    async def _rate_limited_request(self, url: str, params: dict, retries: int = 3) -> dict | None:
        """Make a rate-limited request, retrying only on transient failures."""
        rate_tokens, shared_tasks = _get_shared_rate_bucket()
        for attempt in range(retries):
            try:
                # Acquire a shared rate-limit token (blocks if window is full)
                await rate_tokens.acquire()
                task = asyncio.create_task(_release_rate_token(rate_tokens))
                shared_tasks.add(task)
                self._release_tasks.add(task)
                task.add_done_callback(shared_tasks.discard)
                task.add_done_callback(self._release_tasks.discard)

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
        if date:
            try:
                return int(str(date)[:4])
            except ValueError:
                pass
        yr = result.get("year")
        if isinstance(yr, int):
            return yr
        return None

    @staticmethod
    def _normalize_title(title: str) -> str:
        text = unicodedata.normalize("NFKD", str(title or ""))
        text = "".join(ch for ch in text if not unicodedata.combining(ch))
        text = text.lower().replace("&", " and ")
        text = re.sub(r"[^\w\s]", " ", text)
        return re.sub(r"\s+", " ", text).strip()

    @staticmethod
    def _strip_leading_article(norm_title: str) -> str:
        for prefix in ("the ", "a ", "an "):
            if norm_title.startswith(prefix) and len(norm_title) > len(prefix):
                return norm_title[len(prefix):]
        return norm_title

    @classmethod
    def _pick_best_match(cls, results: list[dict], title: str, year: int | None) -> dict | None:
        """
        Require normalized title equivalence (exact normalized title/original_title,
        or article-stripped equivalence) and strict year matching when year is known.
        Never falls back to unrelated substring or popularity-only matches.
        """
        norm_wanted = cls._normalize_title(title)
        if not norm_wanted:
            return None
        art_wanted = cls._strip_leading_article(norm_wanted)

        def score(r: dict) -> tuple | None:
            titles = [
                cls._normalize_title(r.get("title", "")),
                cls._normalize_title(r.get("original_title", "")),
            ]
            titles = [t for t in titles if t]
            if not titles:
                return None

            is_exact = norm_wanted in titles
            is_article = any(cls._strip_leading_article(t) == art_wanted for t in titles)
            if not (is_exact or is_article):
                return None

            ry = cls._release_year(r)
            if year is not None:
                if ry == year:
                    year_tier = 2
                elif ry is not None and abs(ry - year) <= 1:
                    year_tier = 1
                elif ry is None and is_exact:
                    year_tier = 0
                else:
                    return None
            else:
                year_tier = 1

            title_tier = 2 if is_exact else 1
            pop = float(r.get("popularity") or 0)
            votes = float(r.get("vote_count") or 0)
            return (title_tier, year_tier, pop, votes)

        ranked = []
        for r in results:
            s = score(r)
            if s is not None:
                ranked.append((s, r))
        if not ranked:
            return None
        ranked.sort(key=lambda item: item[0], reverse=True)
        return ranked[0][1]

    async def enrich_favorite_films(self, favorite_urls: list[str]) -> list[dict]:
        """Resolve Letterboxd profile favourites to TMDB metadata without changing order.

        Unresolvable links remain as explicit unresolved slots; they are never
        replaced with an unrelated highly-rated film.
        """
        from html import unescape
        from urllib.parse import urljoin, urlparse

        results = []
        allowed_hosts = {"boxd.it", "www.boxd.it", "letterboxd.com", "www.letterboxd.com"}
        max_redirects = 3
        max_html_bytes = 512 * 1024

        for index, favorite_url in enumerate(favorite_urls[:4]):
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
                current_url = favorite_url
                html_text = None
                for _ in range(max_redirects + 1):
                    parsed = urlparse(current_url)
                    if parsed.scheme != "https" or parsed.hostname not in allowed_hosts:
                        break
                    async with self.client.stream(
                        "GET",
                        current_url,
                        follow_redirects=False,
                        headers={"User-Agent": "CineStats/1.0 (Letterboxd favourites import)"},
                        timeout=15.0,
                    ) as response:
                        if response.is_redirect:
                            location = response.headers.get("location")
                            if not location:
                                break
                            current_url = urljoin(current_url, location)
                            continue
                        response.raise_for_status()
                        final_url = urlparse(str(response.url))
                        if final_url.scheme != "https" or final_url.hostname not in {"letterboxd.com", "www.letterboxd.com"}:
                            break
                        chunks = []
                        total = 0
                        async for chunk in response.aiter_bytes(16384):
                            total += len(chunk)
                            if total > max_html_bytes:
                                chunks.append(chunk[: max_html_bytes - (total - len(chunk))])
                                break
                            chunks.append(chunk)
                        html_text = b"".join(chunks).decode(response.encoding or "utf-8", errors="replace")
                        break

                if not html_text:
                    results.append(item)
                    continue

                title_match = re.search(
                    r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']+)',
                    html_text,
                    flags=re.IGNORECASE,
                )
                if not title_match:
                    title_match = re.search(
                        r'<title[^>]*>(.*?)</title>',
                        html_text,
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
                        "backdrop_path": tmdb.get("backdrop_path"),
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
        params = self._auth_params({"append_to_response": "credits"})
        return await self._rate_limited_request(
            f"{TMDB_BASE_URL}/movie/{tmdb_id}", params
        )

    async def enrich_movie(self, title: str, year: int | None = None) -> dict | None:
        """Full pipeline: check cache → search → fetch details → cache result."""
        search_key = self._make_search_key(title, year)

        # Re-validate cached rows against strict title/year matching so stale
        # bad matches are automatically refreshed.
        cached = await get_cached_movie(search_key)
        if cached and self._pick_best_match([cached], title, year) is not None:
            return cached

        if await is_recent_miss(search_key, config.TMDB_MISS_TTL_DAYS):
            return None

        search_result = await self.search_movie(title, year)
        if not search_result:
            await record_miss(search_key)
            return None

        tmdb_id = search_result["id"]

        # Transient failures here are not recorded as misses so later uploads can retry.
        details = await self.get_movie_details(tmdb_id)
        if not details:
            return None

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
            "backdrop_path": details.get("backdrop_path"),
            "vote_average": details.get("vote_average"),
            "popularity": details.get("popularity"),
        }

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
