# -*- coding: utf-8 -*-
"""ACE-Step generation pipeline with SSE progress events."""
from __future__ import annotations

import asyncio
import shutil
from pathlib import Path

from . import ace_client, db, stem_separator
from .config import OUTPUTS_DIR
from .prompt_builder import build_caption, build_master_caption


# Korean display names for the 4 htdemucs stems.
_STEM_LABELS = {
    "drums": "드럼",
    "bass": "베이스",
    "other": "기타/멜로디",
    "vocals": "보컬",
}


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
    failures: list[str] = []

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
        last_err: str = ""
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
                last_err = f"{type(e).__name__}: {e}"
                print(f"[track_generator] track {order} attempt {attempt + 1} failed: {last_err}")
                if attempt == 0:
                    await sse_queue.put(_sse(
                        "error",
                        track_order=order,
                        message=f"Track {order} failed, retrying. {last_err}",
                    ))
                    await asyncio.sleep(1)

        if success:
            wav_url = f"/outputs/{session_id}/track_{order}.wav"
            await db.update_track_wav(session_id, order, wav_url)
            generated_paths.append(out_path)
        else:
            failures.append(f"#{order} {track['name']}: {last_err}")
            await sse_queue.put(_sse(
                "error",
                track_order=order,
                message=f"Track {order} permanently failed: {last_err}",
            ))

    # Final event lets the SSE route close cleanly.
    if failures and not generated_paths:
        # All tracks failed — session is in error state.
        await db.update_session_status(session_id, "error")
        await sse_queue.put(_sse(
            "done",
            percent=100,
            status="error",
            message="All tracks failed. " + " | ".join(failures),
            tracks=await db.get_tracks(session_id),
        ))
    else:
        status = "done" if not failures else "partial"
        await db.update_session_status(session_id, status)
        await sse_queue.put(_sse(
            "done",
            percent=100,
            status=status,
            message=(" | ".join(failures) if failures else "OK"),
            tracks=await db.get_tracks(session_id),
        ))


async def generate_separated(
    session_id: str,
    sse_queue: asyncio.Queue,
) -> None:
    """Generate one full-band track, then split it into stems with Demucs.

    HEAVY queue task. Replaces the planned track list with the real stems
    (drums / bass / other) so the existing mixer, waveform and repaint routes
    keep working unchanged on track_{order}.wav files.
    """
    await db.update_session_status(session_id, "generating")
    session = await db.get_session(session_id)
    tracks = await db.get_tracks(session_id)

    global_bpm = session["bpm"] or 90
    global_key = session["key"] or "C major"
    duration = session["duration"]
    caption = build_master_caption(tracks, global_bpm, global_key)

    out_dir = Path(OUTPUTS_DIR) / session_id
    source_path = str(out_dir / "_source.wav")

    # Step 1 — generate the full mix from text.
    await sse_queue.put(_sse("progress", phase="compose", percent=10, message="전체 곡 생성 중"))
    try:
        await ace_client.text2music(caption, duration, source_path)
    except Exception as e:
        await db.update_session_status(session_id, "error")
        await sse_queue.put(_sse(
            "done", percent=100, status="error",
            message=f"곡 생성 실패: {type(e).__name__}: {e}",
            tracks=await db.get_tracks(session_id),
        ))
        return

    # Step 2 — separate into stems.
    await sse_queue.put(_sse("progress", phase="separate", percent=50, message="스템 분리 중 (Demucs)"))
    try:
        stems = await stem_separator.separate(source_path, str(out_dir / "_stems"))
    except Exception as e:
        await db.update_session_status(session_id, "error")
        await sse_queue.put(_sse(
            "done", percent=100, status="error",
            message=f"스템 분리 실패: {type(e).__name__}: {e}",
            tracks=await db.get_tracks(session_id),
        ))
        return

    # Step 3 — register each stem as a track (replaces the planned list).
    await db.clear_tracks(session_id)
    new_tracks = [
        {
            "track_order": idx,
            "name": _STEM_LABELS.get(stem["stem"], stem["stem"]),
            "instrument": stem["stem"],
            "caption": caption,
            "locked": 1,
            "volume": 1.0,
        }
        for idx, stem in enumerate(stems, start=1)
    ]
    await db.create_tracks(session_id, new_tracks)
    for idx, stem in enumerate(stems, start=1):
        dest = _wav_path(session_id, idx)
        shutil.copyfile(stem["path"], dest)
        await db.update_track_wav(session_id, idx, f"/outputs/{session_id}/track_{idx}.wav")

    await db.update_session_status(session_id, "done")
    await sse_queue.put(_sse(
        "done", percent=100, status="done",
        message="스템 분리 완료", tracks=await db.get_tracks(session_id),
    ))


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
