"""
SQLite database module for TMDB response caching.

Concurrency notes:
- WAL mode is enabled at init to allow concurrent reads alongside a single writer.
- A module-level asyncio.Lock serializes writes so concurrent enrichment tasks
  don't trigger "database is locked" errors.
- All connections use a 15-second timeout as an additional safety net.
"""
import asyncio
import aiosqlite
import json
import time

from app import config

DB_PATH = str(config.DATA_DIR / "tmdb_cache.db")

# Columns returned to the stats code. raw_details is intentionally left out:
# it is large, and holding it for every film in memory is wasteful.
_CACHE_COLUMNS = (
    "tmdb_id, title, year, search_key, genres, directors, cast_members, runtime, "
    "production_countries, original_language, spoken_languages, release_date, "
    "poster_path, vote_average, popularity"
)
_JSON_FIELDS = ["genres", "directors", "cast_members", "production_countries", "spoken_languages"]

# Serializes all SQLite write operations across concurrent async tasks.
_write_lock = asyncio.Lock()


async def get_db() -> aiosqlite.Connection:
    """Get a database connection."""
    db = await aiosqlite.connect(DB_PATH, timeout=15.0)
    db.row_factory = aiosqlite.Row
    return db


async def init_db():
    """Initialize the database schema and enable WAL mode."""
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(DB_PATH, timeout=15.0) as db:
        # WAL mode: allows concurrent readers while a writer is active.
        # synchronous=NORMAL: safe with WAL and reduces fsync overhead.
        await db.execute("PRAGMA journal_mode=WAL;")
        await db.execute("PRAGMA synchronous=NORMAL;")

        await db.execute("""
            CREATE TABLE IF NOT EXISTS tmdb_cache (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tmdb_id INTEGER UNIQUE,
                title TEXT NOT NULL,
                year INTEGER,
                search_key TEXT UNIQUE NOT NULL,
                raw_details JSON NOT NULL,
                genres JSON,
                directors JSON,
                cast_members JSON,
                runtime INTEGER,
                production_countries JSON,
                original_language TEXT,
                spoken_languages JSON,
                release_date TEXT,
                poster_path TEXT,
                vote_average REAL,
                popularity REAL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_search_key ON tmdb_cache(search_key)
        """)
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_tmdb_id ON tmdb_cache(tmdb_id)
        """)
        # Negative cache: titles TMDB could not match, so we do not re-search
        # them (two API calls each) on every upload.
        await db.execute("""
            CREATE TABLE IF NOT EXISTS tmdb_miss (
                search_key TEXT PRIMARY KEY,
                checked_at REAL NOT NULL
            )
        """)
        await db.commit()


async def get_cached_movie(search_key: str) -> dict | None:
    """Get a cached movie by its search key (title_year)."""
    async with aiosqlite.connect(DB_PATH, timeout=15.0) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            f"SELECT {_CACHE_COLUMNS} FROM tmdb_cache WHERE search_key = ?", (search_key,)
        )
        row = await cursor.fetchone()
        if row:
            result = dict(row)
            for field in _JSON_FIELDS:
                if result.get(field):
                    result[field] = json.loads(result[field])
            return result
        return None


async def is_recent_miss(search_key: str, ttl_days: int) -> bool:
    """True if TMDB found nothing for this key within the last ttl_days."""
    async with aiosqlite.connect(DB_PATH, timeout=15.0) as db:
        cursor = await db.execute(
            "SELECT checked_at FROM tmdb_miss WHERE search_key = ?", (search_key,)
        )
        row = await cursor.fetchone()
    return bool(row and (time.time() - row[0]) < ttl_days * 86400)


async def record_miss(search_key: str) -> None:
    async with _write_lock:
        async with aiosqlite.connect(DB_PATH, timeout=15.0) as db:
            await db.execute(
                "INSERT OR REPLACE INTO tmdb_miss (search_key, checked_at) VALUES (?, ?)",
                (search_key, time.time()),
            )
            await db.commit()


async def cache_movie(movie_data: dict):
    """Cache a movie's TMDB data. Writes are serialized via _write_lock."""
    # Copy so we don't mutate the caller's dict when serializing to JSON
    data = dict(movie_data)
    for field in ["raw_details"] + _JSON_FIELDS:
        if field in data and not isinstance(data[field], str):
            data[field] = json.dumps(data[field])

    async with _write_lock:
        async with aiosqlite.connect(DB_PATH, timeout=15.0) as db:
            await db.execute("""
                INSERT OR REPLACE INTO tmdb_cache 
                (tmdb_id, title, year, search_key, raw_details, genres, directors, 
                 cast_members, runtime, production_countries, original_language, 
                 spoken_languages, release_date, poster_path, vote_average, popularity)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                data.get("tmdb_id"),
                data.get("title"),
                data.get("year"),
                data.get("search_key"),
                data.get("raw_details"),
                data.get("genres"),
                data.get("directors"),
                data.get("cast_members"),
                data.get("runtime"),
                data.get("production_countries"),
                data.get("original_language"),
                data.get("spoken_languages"),
                data.get("release_date"),
                data.get("poster_path"),
                data.get("vote_average"),
                data.get("popularity"),
            ))
            await db.commit()


async def get_cache_stats() -> dict:
    """Get cache statistics."""
    async with aiosqlite.connect(DB_PATH, timeout=15.0) as db:
        cursor = await db.execute("SELECT COUNT(*) FROM tmdb_cache")
        row = await cursor.fetchone()
        return {"cached_movies": row[0] if row else 0}

