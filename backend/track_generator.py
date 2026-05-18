# -*- coding: utf-8 -*-
"""ACE-Step generation pipeline with SSE progress events."""
from __future__ import annotations

import asyncio

from . import ace_client, db
from .config import OUTPUTS_DIR
from .prompt_builder import build_caption


def _sse(event_type: str, **kwargs) -> dict:
    return {"type": event_type, **kwargs}


async def generate_all(
    session_id: str,
    tracks: list[dict],
    duration: int,
    sse_queue: asyncio.Queue,
) -> None:
    """Generate all tracks sequentially as a HEAVY queue task."""
    await db.update_session_status(session_id, "generating")
    session = await db.get_session(session_id)

    global_bpm = session["bpm"] or 90
    global_key = session["key"] or "C major"
    total = len(tracks)
    generated_paths: list[str] = []

    for idx, track in enumerate(tracks):
        order = track["track_order"]
        caption = build_caption(
            caption=track["caption"],
            locked=track.get("locked", 1),
            global_bpm=global_bpm,
            global_key=global_key,
            bpm_override=track.get("bpm_override"),
            key_override=track.get("key_override"),
        )
        out_path = _wav_path(session_id, order)

        # Notify the browser before each ACE-Step request starts.
        await sse_queue.put(_sse(
            "progress",
            track_order=order,
            track_name=track["name"],
            percent=int((idx / total) * 100),
        ))

        # First track starts from text; later tracks reference previous WAVs.
        success = False
        for attempt in range(2):
            try:
                if idx == 0:
                    await ace_client.text2music(caption, duration, out_path)
                else:
                    await ace_client.track_addition(
                        caption=caption,
                        duration=duration,
                        ref_audio_paths=generated_paths,
                        output_path=out_path,
                    )
                success = True
                break
            except Exception as e:
                if attempt == 0:
                    await sse_queue.put(_sse(
                        "error",
                        track_order=order,
                        message=f"Track {order} generation failed, retrying. ({e})",
                    ))
                    await asyncio.sleep(1)
                else:
                    await sse_queue.put(_sse(
                        "error",
                        track_order=order,
                        message=f"Track {order} generation failed permanently: {e}",
                    ))

        if success:
            wav_url = f"/outputs/{session_id}/track_{order}.wav"
            await db.update_track_wav(session_id, order, wav_url)
            generated_paths.append(out_path)

    # Final event lets the SSE route close cleanly.
    await db.update_session_status(session_id, "done")
    updated_tracks = await db.get_tracks(session_id)
    await sse_queue.put(_sse("done", percent=100, tracks=updated_tracks))


async def regenerate_track(
    session_id: str,
    track_order: int,
    sse_queue: asyncio.Queue,
) -> None:
    """Regenerate one track as a LIGHT queue task."""
    session = await db.get_session(session_id)
    tracks = await db.get_tracks(session_id)
    track = next((t for t in tracks if t["track_order"] == track_order), None)
    if not track:
        await sse_queue.put(_sse("error", track_order=track_order, message="Track not found"))
        return

    global_bpm = session["bpm"] or 90
    global_key = session["key"] or "C major"
    caption = build_caption(
        caption=track["caption"],
        locked=track.get("locked", 1),
        global_bpm=global_bpm,
        global_key=global_key,
        bpm_override=track.get("bpm_override"),
        key_override=track.get("key_override"),
    )
    out_path = _wav_path(session_id, track_order)

    prev_paths = [
        _wav_path(session_id, t["track_order"])
        for t in tracks
        if t["track_order"] < track_order and t.get("wav_url")
    ]

    await sse_queue.put(_sse("progress", track_order=track_order, track_name=track["name"], percent=0))
    try:
        if not prev_paths:
            await ace_client.text2music(caption, session["duration"], out_path)
        else:
            await ace_client.track_addition(caption, session["duration"], prev_paths, out_path)

        wav_url = f"/outputs/{session_id}/track_{track_order}.wav"
        await db.update_track_wav(session_id, track_order, wav_url)
        await sse_queue.put(_sse("progress", track_order=track_order, track_name=track["name"], percent=100))
        await sse_queue.put(_sse("done", percent=100, tracks=await db.get_tracks(session_id)))
    except Exception as e:
        await sse_queue.put(_sse("error", track_order=track_order, message=str(e)))


async def repaint_track(
    session_id: str,
    track_order: int,
    start_sec: float,
    end_sec: float,
    sse_queue: asyncio.Queue,
) -> None:
    """Regenerate a selected section of one track as a LIGHT queue task."""
    session = await db.get_session(session_id)
    tracks = await db.get_tracks(session_id)
    track = next((t for t in tracks if t["track_order"] == track_order), None)
    if not track:
        await sse_queue.put(_sse("error", track_order=track_order, message="Track not found"))
        return

    global_bpm = session["bpm"] or 90
    global_key = session["key"] or "C major"
    caption = build_caption(
        caption=track["caption"],
        locked=track.get("locked", 1),
        global_bpm=global_bpm,
        global_key=global_key,
        bpm_override=track.get("bpm_override"),
        key_override=track.get("key_override"),
    )
    audio_path = _wav_path(session_id, track_order)

    await sse_queue.put(_sse("progress", track_order=track_order, track_name=track["name"], percent=0))
    try:
        await ace_client.repaint(caption, audio_path, start_sec, end_sec, audio_path)
        await sse_queue.put(_sse("progress", track_order=track_order, track_name=track["name"], percent=100))
        await sse_queue.put(_sse("done", percent=100, tracks=await db.get_tracks(session_id)))
    except Exception as e:
        await sse_queue.put(_sse("error", track_order=track_order, message=str(e)))


def _wav_path(session_id: str, track_order: int) -> str:
    return str(OUTPUTS_DIR / session_id / f"track_{track_order}.wav")
