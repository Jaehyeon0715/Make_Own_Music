# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 프로젝트 개요

**AI Composer v2.8** — ACE-Step 1.5 기반 멀티트랙 AI 기악 작곡 웹 애플리케이션
- 기획서: `C:\Users\heo01\Desktop\claude\AI_Composer_기획서_v2.8_수정.docx`
- 계획서: `C:\Users\heo01\Desktop\claude\AI_Composer_계획서_v2.8.docx`
- 논리설계서: `C:\Users\heo01\Desktop\claude\AI_Composer_논리설계서_v2.8.docx`

## 개발 환경

- **Python**: 3.9.13 (Anaconda)
  - ⚠️ `X | None` 문법 미지원 → `Optional[X]` + `from __future__ import annotations` 사용
- **AI Provider**: Ollama (로컬, 무료) — `llama3.2` 모델
- **ACE-Step**: `localhost:8001` (lazy-load, 첫 요청 시 모델 로드)
- **패키지 관리**: `uv` (`C:\Users\heo01\.local\bin\uv.exe`)

## 실행 명령어

```powershell
# PATH 갱신 (새 세션 시작 시)
$env:Path = "C:\Users\heo01\.local\bin;$env:Path"

# 1. ACE-Step 실행 (별도 터미널)
cd C:\Users\heo01\ace-step
uv run acestep-api
# → http://localhost:8001

# 2. Ollama 실행 (별도 터미널)
ollama serve
ollama pull llama3.2  # 최초 1회

# 3. 의존성 설치 (최초 1회)
cd C:\Users\heo01\Desktop\claude\MOM\backend
pip install -r requirements.txt
pip install -r requirements-ollama.txt

# 4. FastAPI 실행 (Phase 8 완료 후)
uvicorn main:app --reload --port 8000
```

## 구현 현황

```
MOM/backend/
├── .env                     완료 (AI_PROVIDER=ollama)
├── requirements*.txt        완료
├── db.py                    완료 (Phase 2) — SQLite WAL, 3개 테이블
├── ai_provider/             완료 (Phase 3)
│   ├── __init__.py
│   ├── base.py              TrackSpec, PlanResult, FALLBACK_RESULT
│   ├── factory.py           get_provider(), switch_provider()
│   ├── ollama_provider.py   ← 현재 사용
│   ├── claude_provider.py
│   ├── openai_provider.py
│   └── gemini_provider.py
├── queue_worker.py          완료 (Phase 4) — HEAVY=0 / LIGHT=1
├── prompt_builder.py        완료 (Phase 5) — build_caption()
├── ace_client.py            완료 (Phase 5) — text2music/track_addition/repaint
├── track_generator.py       완료 (Phase 5) — 순차 생성 + SSE
│
├── session_manager.py       미완료 (Phase 6)
├── mixer.py                 미완료 (Phase 7)
├── config.py                미완료 (Phase 8)
├── main.py                  미완료 (Phase 8)
│
└── ai_provider/outputs/     생성된 WAV/MP3 저장 위치
MOM/frontend/
└── index.html               미완료 (Phase 9)
```

## 아키텍처 핵심

```
브라우저 → FastAPI :8000 → PriorityQueue → track_generator → ACE-Step :8001
                                          → mixer           → pydub
                                          → session_manager → SQLite
```

### PriorityQueue 규칙
- `HEAVY=0` → 전체 생성, **먼저** 처리
- `LIGHT=1` → 단일 재생성/Repaint/Provider교체, **나중에** 처리
- Python PriorityQueue: 숫자 낮을수록 먼저 꺼냄

### build_caption() 핵심 로직
```python
bpm = bpm_override if (locked == 0 and bpm_override) else global_bpm
key = key_override if (locked == 0 and key_override) else global_key
return f"{caption}, {bpm} bpm, {key}, no vocals"
```

### ai_provider 확장 방법
구현 클래스 1개 + `factory.py` elif 1줄 추가

## 미해결 이슈

| 이슈 | 내용 | 해결 방법 |
|------|------|---------|
| ACE-Step `/health` 경로 미확인 | `ace_client.health_check()` → False 반환 | ACE-Step 실행 후 `curl http://localhost:8001/` 로 실제 경로 확인 |

## 다음 작업 순서

1. **Phase 6** — `session_manager.py` (세션 복원 + TTL 24h APScheduler)
2. **Phase 7** — `mixer.py` (pydub 볼륨 믹싱 + mix_vN + MP3)
3. **Phase 8** — `config.py` + `main.py` (FastAPI 전체 라우터 16개)
4. **Phase 9** — `frontend/index.html` (2페이지 DAW UI)
5. **Phase 10** — 통합 테스트 6개 시나리오
6. **Phase 11** — README + 배포 패키지
