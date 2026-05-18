from __future__ import annotations

import asyncio
import json
import os
import uuid
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

load_dotenv(Path(__file__).resolve().parent / ".env")

from . import ace_client, db, mixer, session_manager
from .ai_provider import factory
from .config import FRONTEND_DIR, OUTPUTS_DIR, configure_cors, require_api_key
from .queue_worker import Priority, TaskType, worker
from .track_generator import generate_all, regenerate_track, repaint_track


app = FastAPI(title="AI Composer", version="2.8")
configure_cors(app)

# Serve generated audio directly from /outputs.
OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/outputs", StaticFiles(directory=str(OUTPUTS_DIR)), name="outputs")


class PlanRequest(BaseModel):
    genre: str = Field(..., min_length=1)
    mood: str = Field(..., min_length=1)
    bpm: Optional[int] = Field(default=None, ge=40, le=240)
    key: Optional[str] = None
    duration: int = Field(default=30, ge=5, le=600)
    prompt: str = ""


class SessionRequest(BaseModel):
    session_id: str


class VolumeRequest(BaseModel):
    volume: float = Field(..., ge=0, le=2)


class LockRequest(BaseModel):
    locked: int = Field(..., ge=0, le=1)
    bpm_override: Optional[int] = Field(default=None, ge=40, le=240)
    key_override: Optional[str] = None


class RepaintRequest(BaseModel):
    session_id: str
    track_order: int = Field(..., ge=1)
    start_sec: float = Field(..., ge=0)
    end_sec: float = Field(..., gt=0)


class SwitchProviderRequest(BaseModel):
    provider: str


def _track_dicts(plan) -> list[dict]:
    """Convert provider output into DB-ready track rows."""
    return [
        {
            "track_order": idx + 1,
            "name": track.name,
            "instrument": track.instrument,
            "caption": track.caption,
            "locked": 1,
            "volume": 1.0,
        }
        for idx, track in enumerate(plan.tracks)
    ]


def _sse_line(payload: dict) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


async def _stream_job(sse_queue: asyncio.Queue, done_types: set[str]):
    """Bridge QueueWorker events into Server-Sent Events."""
    while True:
        event = await sse_queue.get()
        yield _sse_line(event)
        if event.get("type") in done_types:
            break


@app.on_event("startup")
async def startup() -> None:
    await db.init_db()
    worker.start()
    session_manager.start_scheduler()


@app.on_event("shutdown")
async def shutdown() -> None:
    session_manager.stop_scheduler()


@app.get("/")
async def index():
    index_path = FRONTEND_DIR / "index.html"
    if index_path.exists():
        return FileResponse(index_path)
    return {"message": "AI Composer backend is running"}


@app.get("/health")
async def health():
    return {"ok": True, "ace_step": await ace_client.health_check()}


@app.post("/plan", dependencies=[Depends(require_api_key)])
async def plan(req: PlanRequest):
    # Planning creates a session immediately so generation can resume later.
    provider = factory.get_provider()
    result = await provider.plan_tracks(
        genre=req.genre,
        mood=req.mood,
        bpm=req.bpm,
        key=req.key,
        duration=req.duration,
        prompt=req.prompt,
    )
    session_id = uuid.uuid4().hex
    tracks = _track_dicts(result)
    await db.create_session(
        session_id=session_id,
        ai_provider=os.getenv("AI_PROVIDER", "ollama"),
        duration=req.duration,
        bpm=result.bpm,
        bpm_auto=int(result.bpm_auto),
        key=result.key,
        key_auto=int(result.key_auto),
    )
    await db.create_tracks(session_id, tracks)
    return {"session_id": session_id, "plan": result.model_dump(), "tracks": await db.get_tracks(session_id)}


@app.get("/session/{session_id}", dependencies=[Depends(require_api_key)])
async def get_session(session_id: str):
    restored = await session_manager.restore_session(session_id)
    if not restored:
        raise HTTPException(status_code=404, detail="Session not found")
    return restored


@app.post("/generate/all", dependencies=[Depends(require_api_key)])
async def generate_all_route(req: SessionRequest):
    # HEAVY work goes through the single GPU-safe worker.
    session = await db.get_session(req.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    tracks = await db.get_tracks(req.session_id)
    sse_queue: asyncio.Queue = asyncio.Queue()
    counts = worker.counts()
    await sse_queue.put({"type": "queue", **counts, "message": "Queued full generation"})
    await worker.enqueue(
        Priority.HEAVY,
        TaskType.GENERATE,
        {
            "session_id": req.session_id,
            "tracks": tracks,
            "duration": session["duration"],
            "sse_queue": sse_queue,
        },
        generate_all,
    )
    return StreamingResponse(_stream_job(sse_queue, {"done"}), media_type="text/event-stream")


@app.post("/generate/track/{session_id}/{track_order}", dependencies=[Depends(require_api_key)])
async def generate_track_route(session_id: str, track_order: int):
    # Single-track regeneration is LIGHT and waits behind any HEAVY job.
    sse_queue: asyncio.Queue = asyncio.Queue()
    await sse_queue.put({"type": "queue", **worker.counts(), "message": "Queued track generation"})
    await worker.enqueue(
        Priority.LIGHT,
        TaskType.REGENERATE,
        {"session_id": session_id, "track_order": track_order, "sse_queue": sse_queue},
        regenerate_track,
    )
    return StreamingResponse(_stream_job(sse_queue, {"done", "error"}), media_type="text/event-stream")


@app.post("/repaint", dependencies=[Depends(require_api_key)])
async def repaint_route(req: RepaintRequest):
    # Repaint updates one WAV in place for the selected time span.
    if req.end_sec <= req.start_sec:
        raise HTTPException(status_code=400, detail="end_sec must be greater than start_sec")
    sse_queue: asyncio.Queue = asyncio.Queue()
    await sse_queue.put({"type": "queue", **worker.counts(), "message": "Queued repaint"})
    await worker.enqueue(
        Priority.LIGHT,
        TaskType.REPAINT,
        {
            "session_id": req.session_id,
            "track_order": req.track_order,
            "start_sec": req.start_sec,
            "end_sec": req.end_sec,
            "sse_queue": sse_queue,
        },
        repaint_track,
    )
    return StreamingResponse(_stream_job(sse_queue, {"done", "error"}), media_type="text/event-stream")


@app.post("/track/{session_id}/{track_order}/volume", dependencies=[Depends(require_api_key)])
async def update_volume(session_id: str, track_order: int, req: VolumeRequest):
    await db.update_track_volume(session_id, track_order, req.volume)
    return {"ok": True}


@app.post("/track/{session_id}/{track_order}/lock", dependencies=[Depends(require_api_key)])
async def update_lock(session_id: str, track_order: int, req: LockRequest):
    await db.update_track_lock(session_id, track_order, req.locked, req.bpm_override, req.key_override)
    return {"ok": True}


@app.post("/mix/{session_id}", dependencies=[Depends(require_api_key)])
async def mix_route(session_id: str):
    try:
        return await mixer.mix_session(session_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/mix/{session_id}/versions", dependencies=[Depends(require_api_key)])
async def mix_versions(session_id: str):
    return {"versions": await db.get_mix_versions(session_id)}


@app.get("/waveform/{session_id}/{track_order}", dependencies=[Depends(require_api_key)])
async def waveform_route(session_id: str, track_order: int):
    try:
        return mixer.waveform(session_id, track_order)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Waveform source not found")


@app.post("/provider/switch", dependencies=[Depends(require_api_key)])
async def switch_provider_route(req: SwitchProviderRequest):
    # Provider switching is queued so it cannot interrupt current generation.
    async def handler(provider: str, sse_queue: asyncio.Queue) -> None:
        factory.switch_provider(provider)
        await db.update_all_sessions_provider(provider)
        await sse_queue.put({"type": "provider_switched", "provider": provider})

    sse_queue: asyncio.Queue = asyncio.Queue()
    await sse_queue.put({"type": "queue", **worker.counts(), "message": "Queued provider switch"})
    await worker.enqueue(
        Priority.LIGHT,
        TaskType.SWITCH_PROVIDER,
        {"provider": req.provider, "sse_queue": sse_queue},
        handler,
    )
    return StreamingResponse(_stream_job(sse_queue, {"provider_switched"}), media_type="text/event-stream")
