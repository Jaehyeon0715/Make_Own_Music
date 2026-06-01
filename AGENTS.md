# AGENTS.md

This file provides guidance to Codex (Codex.ai/code) when working with code in this repository.

## 프로젝트 개요

**AI Composer v2.8** — ACE-Step 1.5 기반 멀티트랙 AI 기악 작곡 웹 애플리케이션  
기획서: `C:\Users\heo01\Desktop\Codex\AI_Composer_기획서_v2.8_수정.docx`  
계획서: `C:\Users\heo01\Desktop\Codex\AI_Composer_계획서_v2.8.docx`

## 실행 명령어

```bash
# 1. ACE-Step 서버 먼저 실행 (필수)
cd ace-step && uv sync && uv run acestep-api

# 2. 의존성 설치
pip install -r backend/requirements.txt
pip install -r backend/requirements-Codex.txt   # 선택한 Provider에 맞게

# 3. 환경 변수 설정
cd backend && cp .env.example .env   # AI_PROVIDER, API 키 입력

# 4. FastAPI 실행
uvicorn backend.main:app --reload --port 8000

# 5. ffmpeg 설치 (MP3 변환 필수)
winget install ffmpeg
```

## 아키텍처

```
브라우저 (index.html)
  │  HTTP / SSE
  ▼
FastAPI :8000
  ├── asyncio.PriorityQueue
  │     HEAVY(0): /generate/all       ← GPU 집약, 먼저 처리
  │     LIGHT(1): /generate/track     ← 단일 트랙
  │               /repaint            ← 구간 수정
  │               /provider/switch    ← Provider 교체 (HEAVY 완료 후)
  ├── SQLite sessions.db
  │     sessions / tracks / mix_versions
  └── AI Provider (전역 교체 가능)
        Codex / OpenAI / Gemini / Ollama
  │  HTTP
  ▼
ACE-Step :8001  (text2music, track_addition, repaint)
```

### 2페이지 화면 흐름
- **Page 1**: 장르·분위기 자유 타이핑 → AI 트랙 구성 제안 → [생성 시작]
- **전환**: POST /generate/all (HEAVY enqueue) + SSE 진행률
- **Page 2**: DAW 편집 — 파형도 Canvas + 볼륨 슬라이더 + 뮤트 + 믹스 다운로드
- **복귀**: [기획으로] 버튼 → 세션 유지한 채 Page 1

## 파일 구조

```
MOM/
├── backend/
│   ├── main.py                  # FastAPI 앱, 전체 라우터 (16개 엔드포인트)
│   ├── ai_provider/
│   │   ├── base.py              # BaseProvider 추상 클래스
│   │   ├── factory.py           # switch_provider() + Provider 팩토리
│   │   └── *_provider.py        # Codex / openai / gemini / ollama
│   ├── queue_worker.py          # HEAVY/LIGHT PriorityQueue 워커
│   ├── db.py                    # SQLite CRUD (WAL 모드, 트랜잭션)
│   ├── track_generator.py       # ACE-Step 순차 생성 + SSE 스트림
│   ├── mixer.py                 # pydub 볼륨 믹싱, mix_vN, MP3
│   ├── session_manager.py       # 세션 복원 + TTL 24h APScheduler
│   ├── prompt_builder.py        # build_caption() — BPM/Key 오버라이드 적용
│   ├── ace_client.py            # ACE-Step HTTP 클라이언트
│   ├── config.py                # CORS, Rate Limit 설정
│   ├── .env                     # 실제 설정값 (gitignore)
│   └── .env.example             # 환경 변수 템플릿
├── frontend/
│   └── index.html               # 2페이지 DAW UI (Vanilla JS)
├── outputs/
│   └── {session_id}/            # track_N_*.wav, mix_vN.wav, mix_latest.mp3
└── sessions.db                  # SQLite DB
```

## 핵심 설계 결정 및 주의사항

### ⚠️ PriorityQueue 우선순위
Python `asyncio.PriorityQueue`는 **숫자가 낮을수록 먼저 처리**된다.
- `HEAVY = 0` → **먼저** 처리
- `LIGHT = 1` → **나중에** 처리
- SWITCH_PROVIDER는 LIGHT(1)이므로 현재 HEAVY 완료 후 처리됨 (SSE로 알림)

### SQLite DB 설계
- WAL 모드 활성화 (읽기/쓰기 동시성)
- `tracks.locked = 1` 기본값 — 해제 시에만 `bpm_override` / `key_override` 적용
- `mix_versions` 최대 10개 — 초과 시 가장 오래된 것부터 파일·DB 동시 삭제
- 세션 복원: `localStorage.session_id` → `GET /session/{sid}` → DB 전체 상태 복원

### AI Provider 추상화
- `BaseProvider.plan_tracks()` → Pydantic 검증 → 실패 시 2회 재시도 → 폴백(기본 트랙)
- 새 Provider 추가: 구현 클래스 1개 + `factory.py` elif 1줄

### 파형도 렌더링
- 백엔드: pydub으로 WAV 다운샘플링 → waveform JSON → `GET /waveform/{sid}/{n}`
- 프론트: Canvas 2D로 렌더링, 드래그로 Repaint 구간(`start_sec`~`end_sec`) 선택

### build_caption() 핵심 로직
```python
def build_caption(track, global_bpm, global_key):
    bpm = track.bpm_override if track.locked == 0 else global_bpm
    key = track.key_override if track.locked == 0 else global_key
    return f"{track.caption}, {bpm} bpm, {key}, no vocals"
```

## SSE 이벤트 타입

| 타입 | 시점 | 주요 필드 |
|------|------|---------|
| `queue` | 큐 진입 시 | `heavy`, `light`, `message` |
| `progress` | 트랙 생성 중 | `track_order`, `track_name`, `percent` |
| `done` | 전체 완료 | `percent: 100`, `tracks: [...]` |
| `provider_switched` | Provider 교체 완료 | `provider` |

## Rate Limit

| 엔드포인트 | 제한 |
|-----------|------|
| `POST /plan` | 10회/분 |
| `POST /generate/*` | 5회/분 |
| `POST /mix/*` | 30회/분 |

## Phase별 개발 순서 (총 12.5일)

| Phase | 산출물 | 기간 |
|-------|--------|------|
| 1 | 환경 구성, `.env.example`, `requirements*.txt` | 0.5일 |
| 2 | `db.py` — 3개 테이블 + WAL + 트랜잭션 | 1일 |
| 3 | `ai_provider/` — 4개 구현체 + 폴백 | 2일 |
| 4 | `queue_worker.py` — HEAVY/LIGHT 워커 | 1일 |
| 5 | `track_generator.py` — ACE-Step + SSE | 1일 |
| 6 | `session_manager.py` — 복원 + TTL | 0.5일 |
| 7 | `mixer.py` — pydub + MP3 | 0.5일 |
| 8 | `main.py` — 전체 라우터 + 인증 + Rate Limit | 1일 |
| 9 | `index.html` — 2페이지 DAW UI | **4일** |
| 10 | 통합 테스트 6개 시나리오 | 0.5일 |
| 11 | README, .gitignore, 배포 패키지 | 0.5일 |

> Phase 9는 기획서 원안 2.5일 → **4일**로 조정 (파형도 렌더링·Repaint·Web Audio 복잡도 반영)
