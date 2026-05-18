from __future__ import annotations

import shutil
from pathlib import Path

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from . import db
from .config import OUTPUTS_DIR, SESSION_TTL_HOURS


_scheduler: AsyncIOScheduler | None = None


# Restore the full UI state from localStorage.session_id.
async def restore_session(session_id: str) -> dict | None:
    session = await db.get_session(session_id)
    if not session:
        return None
    return {
        "session": session,
        "tracks": await db.get_tracks(session_id),
        "mix_versions": await db.get_mix_versions(session_id),
    }


# Remove stale DB rows and generated audio after the configured TTL.
async def cleanup_expired_sessions() -> None:
    expired = await db.get_expired_sessions(SESSION_TTL_HOURS)
    for session in expired:
        sid = session["session_id"]
        shutil.rmtree(Path(OUTPUTS_DIR) / sid, ignore_errors=True)
        await db.delete_session(sid)


# FastAPI owns the scheduler lifecycle.
def start_scheduler() -> AsyncIOScheduler:
    global _scheduler
    if _scheduler and _scheduler.running:
        return _scheduler
    _scheduler = AsyncIOScheduler()
    _scheduler.add_job(cleanup_expired_sessions, "interval", hours=1, id="session_cleanup")
    _scheduler.start()
    return _scheduler


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
    _scheduler = None
