from __future__ import annotations

import math
import shutil
import wave
from pathlib import Path

from pydub import AudioSegment

from . import db
from .config import MAX_MIX_VERSIONS, OUTPUTS_DIR


def _track_path(session_id: str, track_order: int) -> Path:
    return Path(OUTPUTS_DIR) / session_id / f"track_{track_order}.wav"


def _volume_to_db(volume: float) -> float:
    volume = max(0.0, float(volume))
    if volume <= 0:
        return -120.0
    return 20.0 * math.log10(volume)


# Overlay all generated tracks, applying each saved volume slider value.
async def mix_session(session_id: str) -> dict:
    session = await db.get_session(session_id)
    if not session:
        raise ValueError("Session not found")

    tracks = await db.get_tracks(session_id)
    audio_parts: list[AudioSegment] = []
    for track in tracks:
        path = _track_path(session_id, track["track_order"])
        if not path.exists():
            continue
        volume = float(track.get("volume", 1.0) or 0.0)
        audio_parts.append(AudioSegment.from_file(path) + _volume_to_db(volume))

    if not audio_parts:
        raise ValueError("No generated tracks to mix")

    mix = audio_parts[0]
    for part in audio_parts[1:]:
        mix = mix.overlay(part)

    out_dir = Path(OUTPUTS_DIR) / session_id
    out_dir.mkdir(parents=True, exist_ok=True)
    latest = await db.get_latest_mix(session_id)
    version = int(latest["version"]) + 1 if latest else 1
    wav_path = out_dir / f"mix_v{version}.wav"
    mp3_path = out_dir / f"mix_v{version}.mp3"
    mix.export(wav_path, format="wav")
    mix.export(mp3_path, format="mp3")
    # Stable download URL for the frontend, while DB keeps numbered history.
    shutil.copyfile(mp3_path, out_dir / "mix_latest.mp3")

    saved_version = await db.save_mix_version(
        session_id,
        str(wav_path),
        str(mp3_path),
        max_versions=MAX_MIX_VERSIONS,
    )
    return {
        "version": saved_version,
        "wav_url": f"/outputs/{session_id}/{wav_path.name}",
        "mp3_url": f"/outputs/{session_id}/{mp3_path.name}",
        "latest_mp3_url": f"/outputs/{session_id}/mix_latest.mp3",
    }


# Downsample WAV peaks for lightweight Canvas rendering.
def waveform(session_id: str, track_order: int, samples: int = 1200) -> dict:
    path = _track_path(session_id, track_order)
    if not path.exists():
        raise FileNotFoundError(str(path))

    with wave.open(str(path), "rb") as wav:
        channels = wav.getnchannels()
        width = wav.getsampwidth()
        rate = wav.getframerate()
        frames = wav.getnframes()
        raw = wav.readframes(frames)

    if width != 2:
        audio = AudioSegment.from_file(path)
        audio = audio.set_sample_width(2).set_channels(1)
        raw = audio.raw_data
        channels = 1
        rate = audio.frame_rate
        frames = len(raw) // 2

    values = []
    step = max(1, frames // samples)
    max_int = 32768.0
    for i in range(0, frames, step):
        start = i * channels * 2
        end = min(len(raw), (i + step) * channels * 2)
        if start >= end:
            break
        peak = 0
        for j in range(start, end, 2):
            sample = int.from_bytes(raw[j:j + 2], "little", signed=True)
            peak = max(peak, abs(sample))
        values.append(round(peak / max_int, 4))

    duration = frames / float(rate) if rate else 0
    return {"duration": duration, "sample_rate": rate, "peaks": values}
