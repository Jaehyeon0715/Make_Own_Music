"""
통합 테스트 6개 시나리오 — AI Composer v2.8

실행:
    cd MOM/
    pip install -r requirements-test.txt
    pytest -v
"""
from __future__ import annotations

from pathlib import Path

import pytest

from tests.conftest import collect_sse


# ══════════════════════════════════════════════════════════════
# Scenario 1 — 전체 생성 정상 흐름
# /plan → /generate/all → SSE done → WAV 저장
# ══════════════════════════════════════════════════════════════

async def test_s1_full_generation(client, ace_mock, provider_mock):
    from backend import db
    from backend.config import OUTPUTS_DIR

    # 1-a. AI 기획
    plan_res = await client.post("/plan", json={
        "genre": "lo-fi jazz", "mood": "relaxed", "duration": 10,
    })
    assert plan_res.status_code == 200, plan_res.text
    data = plan_res.json()
    sid = data["session_id"]
    assert sid
    assert len(data["tracks"]) > 0

    # 1-b. 전체 생성 SSE
    events = []
    async with client.stream("POST", "/generate/all", json={"session_id": sid}) as r:
        assert r.status_code == 200
        events = await collect_sse(r)

    done_events = [e for e in events if e.get("type") == "done"]
    assert done_events, f"'done' SSE 없음. 수신 이벤트: {events}"

    # 1-c. WAV 파일 저장 확인
    tracks = await db.get_tracks(sid)
    assert tracks, "DB 트랙 없음"
    for t in tracks:
        assert t["wav_url"], f"track {t['track_order']} wav_url 없음"
        wav = OUTPUTS_DIR / sid / f"track_{t['track_order']}.wav"
        assert wav.exists(), f"{wav} 파일 없음"

    # 1-d. 세션 상태 → done
    session = await db.get_session(sid)
    assert session["status"] == "done"


# ══════════════════════════════════════════════════════════════
# Scenario 2 — 단일 트랙 재생성 (LIGHT queue)
# /generate/track → SSE done → wav_url 갱신
# ══════════════════════════════════════════════════════════════

async def test_s2_regenerate_track(client, ace_mock, provider_mock):
    from backend import db

    # 세팅: 전체 생성 완료
    plan_res = await client.post("/plan", json={"genre": "pop", "mood": "happy", "duration": 10})
    sid = plan_res.json()["session_id"]
    async with client.stream("POST", "/generate/all", json={"session_id": sid}) as r:
        await collect_sse(r)

    tracks = await db.get_tracks(sid)
    order = tracks[0]["track_order"]

    # 단일 재생성
    events = []
    async with client.stream("POST", f"/generate/track/{sid}/{order}") as r:
        assert r.status_code == 200
        events = await collect_sse(r)

    done_events = [e for e in events if e.get("type") == "done"]
    assert done_events, f"재생성 'done' SSE 없음. 수신: {events}"

    # wav_url 존재 확인
    updated = await db.get_tracks(sid)
    url = next(t["wav_url"] for t in updated if t["track_order"] == order)
    assert url, "재생성 후 wav_url 없음"


# ══════════════════════════════════════════════════════════════
# Scenario 3 — Repaint
# 유효성(end > start) + 정상 실행 → SSE done
# ══════════════════════════════════════════════════════════════

async def test_s3_repaint(client, ace_mock, provider_mock):
    from backend import db

    plan_res = await client.post("/plan", json={"genre": "ambient", "mood": "calm", "duration": 10})
    sid = plan_res.json()["session_id"]
    async with client.stream("POST", "/generate/all", json={"session_id": sid}) as r:
        await collect_sse(r)

    tracks = await db.get_tracks(sid)
    order = tracks[0]["track_order"]

    # 잘못된 범위 → 400
    bad = await client.post("/repaint", json={
        "session_id": sid, "track_order": order,
        "start_sec": 5.0, "end_sec": 3.0,
    })
    assert bad.status_code == 400, f"잘못된 범위가 400이 아님: {bad.status_code}"

    # 정상 Repaint
    events = []
    async with client.stream("POST", "/repaint", json={
        "session_id": sid, "track_order": order,
        "start_sec": 0.0, "end_sec": 3.0,
    }) as r:
        assert r.status_code == 200
        events = await collect_sse(r)

    done_events = [e for e in events if e.get("type") == "done"]
    assert done_events, f"Repaint 'done' SSE 없음. 수신: {events}"


# ══════════════════════════════════════════════════════════════
# Scenario 4 — 믹스 + 버전 관리
# 첫 믹스 → version=1, 11회 → 최대 10버전 유지
# ══════════════════════════════════════════════════════════════

async def test_s4_mix_and_versioning(client, ace_mock, provider_mock, mp3_mock):
    plan_res = await client.post("/plan", json={"genre": "jazz", "mood": "night", "duration": 10})
    sid = plan_res.json()["session_id"]
    async with client.stream("POST", "/generate/all", json={"session_id": sid}) as r:
        await collect_sse(r)

    # 첫 믹스
    mix1 = await client.post(f"/mix/{sid}")
    assert mix1.status_code == 200, mix1.text
    data1 = mix1.json()
    assert data1["version"] == 1
    assert data1["wav_url"]
    assert data1["mp3_url"]
    assert data1["latest_mp3_url"]

    # 10번 추가 믹스 (총 11회)
    for _ in range(10):
        r = await client.post(f"/mix/{sid}")
        assert r.status_code == 200

    # 버전 목록 → 최대 10개
    ver_res = await client.get(f"/mix/{sid}/versions")
    assert ver_res.status_code == 200
    versions = ver_res.json()["versions"]
    assert len(versions) <= 10, f"버전 수 {len(versions)} > 10"


# ══════════════════════════════════════════════════════════════
# Scenario 5 — 세션 복원
# /session/{id} → session + tracks + mix_versions 반환
# 없는 세션 → 404
# ══════════════════════════════════════════════════════════════

async def test_s5_session_restore(client, provider_mock):
    plan_res = await client.post("/plan", json={"genre": "bossa", "mood": "sunny", "duration": 15})
    assert plan_res.status_code == 200
    sid = plan_res.json()["session_id"]

    # 복원
    restore = await client.get(f"/session/{sid}")
    assert restore.status_code == 200
    body = restore.json()
    assert body["session"]["session_id"] == sid
    assert isinstance(body["tracks"], list)
    assert len(body["tracks"]) > 0
    assert isinstance(body["mix_versions"], list)

    # 없는 세션 → 404
    missing = await client.get("/session/nonexistent_session_xyz")
    assert missing.status_code == 404


# ══════════════════════════════════════════════════════════════
# Scenario 6 — Provider 전환 (LIGHT queue)
# /provider/switch → SSE provider_switched → factory 업데이트
# ══════════════════════════════════════════════════════════════

async def test_s6_provider_switch(client):
    from backend.ai_provider import factory

    # ollama → ollama (self-switch, 항상 성공)
    events = []
    async with client.stream("POST", "/provider/switch", json={"provider": "ollama"}) as r:
        assert r.status_code == 200
        events = await collect_sse(r)

    switched = [e for e in events if e.get("type") == "provider_switched"]
    assert switched, f"'provider_switched' 이벤트 없음. 수신: {events}"
    assert switched[0]["provider"] == "ollama"

    # factory 실제 전환 확인
    assert factory._current_provider is not None


# ══════════════════════════════════════════════════════════════
# Scenario 7 — 스템 분리 생성 (Demucs 사후 분리)
# /generate/separated → 전체 곡 생성 → Demucs → drums/bass/other 트랙
# ══════════════════════════════════════════════════════════════

async def test_s7_separated_generation(client, ace_mock, provider_mock, demucs_mock):
    from backend import db
    from backend.config import OUTPUTS_DIR

    plan_res = await client.post("/plan", json={"genre": "funk", "mood": "groovy", "duration": 10})
    sid = plan_res.json()["session_id"]

    events = []
    async with client.stream("POST", "/generate/separated", json={"session_id": sid}) as r:
        assert r.status_code == 200
        events = await collect_sse(r)

    done = [e for e in events if e.get("type") == "done"]
    assert done, f"'done' SSE 없음. 수신: {events}"
    assert done[0]["status"] == "done", f"분리 실패: {done[0]}"

    # 계획 트랙 → 실제 스템으로 교체됨
    tracks = await db.get_tracks(sid)
    assert {t["instrument"] for t in tracks} == {"drums", "bass", "other"}
    for t in tracks:
        assert t["wav_url"], f"track {t['track_order']} wav_url 없음"
        wav = OUTPUTS_DIR / sid / f"track_{t['track_order']}.wav"
        assert wav.exists(), f"{wav} 파일 없음"

    # 없는 세션 → 404
    missing = await client.post("/generate/separated", json={"session_id": "nope_xyz"})
    assert missing.status_code == 404
