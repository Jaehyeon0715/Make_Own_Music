# -*- coding: utf-8 -*-
"""Async SQLite data access for sessions, tracks, and mix versions."""

import os
from datetime import datetime, timezone
from typing import Optional

import aiosqlite

DB_PATH = os.getenv("DB_PATH", "sessions.db")


async def init_db() -> None:
    """Create database tables and enable WAL mode."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("PRAGMA journal_mode=WAL")
        await db.execute("PRAGMA foreign_keys=ON")

        await db.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                session_id   TEXT PRIMARY KEY,
                created_at   TEXT NOT NULL,
                ai_provider  TEXT NOT NULL,
                bpm          INTEGER,
                bpm_auto     INTEGER DEFAULT 1,
                key          TEXT,
                key_auto     INTEGER DEFAULT 1,
                duration     INTEGER NOT NULL,
                status       TEXT DEFAULT 'pending'
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS tracks (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id   TEXT NOT NULL REFERENCES sessions(session_id),
                track_order  INTEGER NOT NULL,
                name         TEXT NOT NULL,
                instrument   TEXT NOT NULL,
                caption      TEXT NOT NULL,
                bpm_override INTEGER,
                key_override TEXT,
                locked       INTEGER DEFAULT 1,
                volume       REAL DEFAULT 1.0,
                wav_url      TEXT
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS mix_versions (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id   TEXT NOT NULL REFERENCES sessions(session_id),
                version      INTEGER NOT NULL,
                wav_path     TEXT NOT NULL,
                mp3_path     TEXT,
                created_at   TEXT NOT NULL
            )
        """)

        await db.commit()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def create_session(
    session_id: str,
    ai_provider: str,
    duration: int,
    bpm: Optional[int] = None,
    bpm_auto: int = 1,
    key: Optional[str] = None,
    key_auto: int = 1,
) -> dict:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("PRAGMA foreign_keys=ON")
        await db.execute(
            """INSERT INTO sessions
               (session_id, created_at, ai_provider, bpm, bpm_auto, key, key_auto, duration, status)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending')""",
            (session_id, _now(), ai_provider, bpm, bpm_auto, key, key_auto, duration),
        )
        await db.commit()
    return await get_session(session_id)


async def get_session(session_id: str) -> Optional[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM sessions WHERE session_id = ?", (session_id,)
        ) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


async def update_session_status(session_id: str, status: str) -> None:
    """status: pending | generating | done | error"""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE sessions SET status = ? WHERE session_id = ?",
            (status, session_id),
        )
        await db.commit()


async def update_session_provider(session_id: str, provider: str) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE sessions SET ai_provider = ? WHERE session_id = ?",
            (provider, session_id),
        )
        await db.commit()


async def update_all_sessions_provider(provider: str) -> None:
    """Update provider name for all sessions after a global provider switch."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE sessions SET ai_provider = ?", (provider,))
        await db.commit()


async def delete_session(session_id: str) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("PRAGMA foreign_keys=ON")
        await db.execute("DELETE FROM tracks WHERE session_id = ?", (session_id,))
        await db.execute("DELETE FROM mix_versions WHERE session_id = ?", (session_id,))
        await db.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
        await db.commit()


async def get_expired_sessions(ttl_hours: int) -> list[dict]:
    """Return sessions older than ttl_hours."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """SELECT * FROM sessions
               WHERE datetime(created_at) < datetime('now', ?)""",
            (f"-{ttl_hours} hours",),
        ) as cur:
            rows = await cur.fetchall()
            return [dict(r) for r in rows]


async def create_tracks(session_id: str, tracks: list[dict]) -> None:
    """Insert the planned track list for a session."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("PRAGMA foreign_keys=ON")
        for t in tracks:
            await db.execute(
                """INSERT INTO tracks
                   (session_id, track_order, name, instrument, caption,
                    bpm_override, key_override, locked, volume)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    session_id,
                    t["track_order"],
                    t["name"],
                    t["instrument"],
                    t["caption"],
                    t.get("bpm_override"),
                    t.get("key_override"),
                    t.get("locked", 1),
                    t.get("volume", 1.0),
                ),
            )
        await db.commit()


async def clear_tracks(session_id: str) -> None:
    """Delete all tracks for a session, keeping the session row intact.

    Used when stem separation replaces the planned track list with real stems.
    """
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM tracks WHERE session_id = ?", (session_id,))
        await db.commit()


async def get_tracks(session_id: str) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM tracks WHERE session_id = ? ORDER BY track_order",
            (session_id,),
        ) as cur:
            rows = await cur.fetchall()
            return [dict(r) for r in rows]


async def update_track_wav(session_id: str, track_order: int, wav_url: str) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE tracks SET wav_url = ? WHERE session_id = ? AND track_order = ?",
            (wav_url, session_id, track_order),
        )
        await db.commit()


async def update_track_volume(session_id: str, track_order: int, volume: float) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE tracks SET volume = ? WHERE session_id = ? AND track_order = ?",
            (volume, session_id, track_order),
        )
        await db.commit()


async def update_track_lock(
    session_id: str,
    track_order: int,
    locked: int,
    bpm_override: Optional[int] = None,
    key_override: Optional[str] = None,
) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """UPDATE tracks
               SET locked = ?, bpm_override = ?, key_override = ?
               WHERE session_id = ? AND track_order = ?""",
            (locked, bpm_override, key_override, session_id, track_order),
        )
        await db.commit()


async def save_mix_version(
    session_id: str,
    wav_path: str,
    mp3_path: Optional[str],
    max_versions: int = 10,
) -> int:
    """Save a mix version and delete the oldest version when max_versions is exceeded."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row

        async with db.execute(
            "SELECT MAX(version) as mv FROM mix_versions WHERE session_id = ?",
            (session_id,),
        ) as cur:
            row = await cur.fetchone()
            new_version = (row["mv"] or 0) + 1

        async with db.execute(
            """SELECT * FROM mix_versions WHERE session_id = ?
               ORDER BY version ASC LIMIT 1""",
            (session_id,),
        ) as cur:
            count_cur = await db.execute(
                "SELECT COUNT(*) as cnt FROM mix_versions WHERE session_id = ?",
                (session_id,),
            )
            count_row = await count_cur.fetchone()
            if count_row["cnt"] >= max_versions:
                oldest = await cur.fetchone()
                if oldest:
                    for path in [oldest["wav_path"], oldest["mp3_path"]]:
                        if path and os.path.exists(path):
                            os.remove(path)
                    await db.execute(
                        "DELETE FROM mix_versions WHERE id = ?", (oldest["id"],)
                    )

        await db.execute(
            """INSERT INTO mix_versions (session_id, version, wav_path, mp3_path, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (session_id, new_version, wav_path, mp3_path, _now()),
        )
        await db.commit()

    return new_version


async def get_mix_versions(session_id: str) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM mix_versions WHERE session_id = ? ORDER BY version DESC",
            (session_id,),
        ) as cur:
            rows = await cur.fetchall()
            return [dict(r) for r in rows]


async def get_latest_mix(session_id: str) -> Optional[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """SELECT * FROM mix_versions WHERE session_id = ?
               ORDER BY version DESC LIMIT 1""",
            (session_id,),
        ) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None
