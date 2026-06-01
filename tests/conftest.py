# conftest.py — 환경변수 설정은 import보다 먼저 (module-level)
from __future__ import annotations

import os
import tempfile

_tmp = tempfile.mkdtemp(prefix="aicomposer_test_")
os.environ.setdefault("DB_PATH",     os.path.join(_tmp, "test.db"))
os.environ.setdefault("OUTPUTS_DIR", os.path.join(_tmp, "outputs"))
os.environ.setdefault("AI_PROVIDER", "ollama")
os.environ.setdefault("API_KEY",     "")          # 테스트 중 인증 비활성화
os.environ.setdefault("ACESTEP_URL", "http://localhost:8001")
os.environ.setdefault("OLLAMA_HOST", "http://localhost:11434")

# ── 위 설정 이후에만 backend import ──────────────────────────────────────
import wave
from pathlib import Path
from unittest.mock import AsyncMock, patch

import aiosqlite
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport


# ── 공용 헬퍼 ─────────────────────────────────────────────────────────────

def make_wav(path: str | Path, secs: float = 1.0) -> None:
    """테스트용 최소 WAV 파일 생성."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(p), "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(44100)
        f.writeframes(b"\x00\x00" * int(44100 * secs))


async def collect_sse(response) -> list[dict]:
    """SSE 스트림을 이벤트 dict 리스트로 수집."""
    import json
    events = []
    async for line in response.aiter_lines():
        if line.startswith("data: "):
            events.append(json.loads(line[6:]))
    return events


# ── Fixtures ──────────────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def client():
    """
    httpx AsyncClient.
    ASGITransport은 lifespan을 실행하지 않으므로
    db.init_db()와 worker.start()를 수동 호출.
    """
    from backend import db as _db, session_manager
    from backend.queue_worker import worker
    from backend.main import app

    await _db.init_db()
    worker.start()   # 현재 event loop에서 worker 태스크 생성

    with patch.object(session_manager, "start_scheduler", return_value=None), \
         patch.object(session_manager, "stop_scheduler", return_value=None):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as c:
            yield c


@pytest_asyncio.fixture(autouse=True)
async def clean_db():
    """각 테스트 전 테이블 초기화."""
    from backend import db
    await db.init_db()
    async with aiosqlite.connect(db.DB_PATH) as conn:
        for tbl in ("mix_versions", "tracks", "sessions"):
            await conn.execute(f"DELETE FROM {tbl}")
        await conn.commit()
    yield


@pytest.fixture
def ace_mock():
    """ACE-Step 호출 대신 더미 WAV 파일 생성."""
    async def t2m(caption, duration, output_path):
        make_wav(output_path)

    async def tadd(caption, duration, ref_audio_paths, output_path):
        make_wav(output_path)

    async def repaint_fn(caption, audio_path, start_sec, end_sec, output_path):
        pass  # 파일 유지

    with patch("backend.ace_client.text2music",    side_effect=t2m), \
         patch("backend.ace_client.track_addition", side_effect=tadd), \
         patch("backend.ace_client.repaint",        side_effect=repaint_fn):
        yield


@pytest.fixture
def demucs_mock():
    """Demucs 호출 대신 3개 스템 더미 WAV 생성."""
    async def fake_separate(input_wav, out_dir):
        results = []
        for stem in ("drums", "bass", "other"):
            p = Path(out_dir) / "htdemucs" / f"{stem}.wav"
            make_wav(p)
            results.append({"stem": stem, "path": str(p)})
        return results

    with patch("backend.stem_separator.separate", side_effect=fake_separate):
        yield


@pytest.fixture
def mp3_mock():
    """ffmpeg 미설치 환경에서 MP3 export를 빈 파일로 대체."""
    from pathlib import Path
    from unittest.mock import MagicMock, patch
    from pydub import AudioSegment

    def fake_export(self, out_f, format=None, **kwargs):
        p = Path(str(out_f))
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"")
        return MagicMock()

    with patch.object(AudioSegment, "export", fake_export):
        yield


@pytest.fixture
def provider_mock():
    """OllamaProvider.plan_tracks → FALLBACK_RESULT 즉시 반환."""
    from backend.ai_provider.base import FALLBACK_RESULT
    with patch(
        "backend.ai_provider.ollama_provider.OllamaProvider.plan_tracks",
        new_callable=AsyncMock,
        return_value=FALLBACK_RESULT,
    ):
        yield
