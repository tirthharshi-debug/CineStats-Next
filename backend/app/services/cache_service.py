"""
Cache service — thin wrapper around database operations for the route layer.
"""
from app.database.db import get_cached_movie, cache_movie, get_cache_stats, init_db


async def initialize_cache():
    """Initialize the cache database."""
    await init_db()


async def lookup_movie(search_key: str) -> dict | None:
    """Look up a cached movie response."""
    return await get_cached_movie(search_key)


async def store_movie(movie_data: dict):
    """Store a movie response in the cache."""
    await cache_movie(movie_data)


async def stats() -> dict:
    """Return cache statistics."""
    return await get_cache_stats()
