"""
Durable job records (SQLite).

Live progress stays in memory for speed; this store keeps the parts that must
survive a restart: the access-token hash, final status/error, and finished
results. Records expire with the same TTL as in-memory jobs, so uploaded data
is not kept longer than JOB_TTL_SECONDS after completion.
"""
import json
import logging
import time

import aiosqlite

from app import config

logger = logging.getLogger("cinestats.jobs")

JOB_DB_PATH = str(config.DATA_DIR / "jobs.db")
INTERRUPTED_MESSAGE = (
    "The server restarted while this analysis was running. Please upload your export again."
)


async def init() -> None:
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(JOB_DB_PATH, timeout=15.0) as db:
        await db.execute("PRAGMA journal_mode=WAL;")
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS jobs (
                job_id TEXT PRIMARY KEY,
                token_hash TEXT NOT NULL,
                status TEXT NOT NULL,
                error TEXT,
                result TEXT,
                created_at REAL NOT NULL,
                finished_at REAL
            )
            """
        )
        await db.commit()


async def save(job_id: str, token_hash: str, status: str, created_at: float,
               error: str | None = None, result: dict | None = None,
               finished_at: float | None = None) -> None:
    payload = json.dumps(result, allow_nan=False) if result is not None else None
    async with aiosqlite.connect(JOB_DB_PATH, timeout=15.0) as db:
        await db.execute(
            """
            INSERT INTO jobs (job_id, token_hash, status, error, result, created_at, finished_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(job_id) DO UPDATE SET
                status = excluded.status,
                error = excluded.error,
                result = excluded.result,
                finished_at = excluded.finished_at
            """,
            (job_id, token_hash, status, error, payload, created_at, finished_at),
        )
        await db.commit()


async def load(job_id: str) -> dict | None:
    async with aiosqlite.connect(JOB_DB_PATH, timeout=15.0) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM jobs WHERE job_id = ?", (job_id,))
        row = await cursor.fetchone()
    if not row:
        return None
    record = dict(row)
    if record.get("result"):
        record["result"] = json.loads(record["result"])
    return record


async def delete(job_id: str) -> None:
    async with aiosqlite.connect(JOB_DB_PATH, timeout=15.0) as db:
        await db.execute("DELETE FROM jobs WHERE job_id = ?", (job_id,))
        await db.commit()


async def fail_interrupted() -> int:
    """On startup, any job still marked as running was cut off by a restart."""
    async with aiosqlite.connect(JOB_DB_PATH, timeout=15.0) as db:
        cursor = await db.execute(
            """
            UPDATE jobs SET status = 'error', error = ?, finished_at = ?
            WHERE status NOT IN ('done', 'error')
            """,
            (INTERRUPTED_MESSAGE, time.time()),
        )
        await db.commit()
        return cursor.rowcount or 0


async def purge_expired(ttl_seconds: int) -> int:
    cutoff = time.time() - ttl_seconds
    async with aiosqlite.connect(JOB_DB_PATH, timeout=15.0) as db:
        cursor = await db.execute(
            "DELETE FROM jobs WHERE finished_at IS NOT NULL AND finished_at < ?", (cutoff,)
        )
        await db.commit()
        return cursor.rowcount or 0
