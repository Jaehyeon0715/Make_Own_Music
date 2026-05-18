# AI Composer v2.8

ACE-Step 1.5 기반 멀티트랙 AI 기악 작곡 웹 애플리케이션.

- AI가 장르·분위기를 분석해 멀티트랙 구성 제안
- ACE-Step으로 트랙별 WAV 순차 생성
- DAW 편집 (볼륨, 재생성, Repaint, 믹스)
- AI Provider 런타임 전환 (Ollama / Claude / OpenAI / Gemini)

---

## 아키텍처

```
브라우저 → FastAPI :8000 → PriorityQueue → track_generator → ACE-Step :8001
                                          → mixer           → pydub
                                          → session_manager → SQLite
```

| 우선순위 | 태스크 |
|---------|--------|
| HEAVY=0 | 전체 트랙 생성 (먼저 처리) |
| LIGHT=1 | 단일 재생성 / Repaint / Provider 전환 |

---

## 요구사항

| 항목 | 버전 |
|------|------|
| Python | 3.9+ (Anaconda 권장) |
| ACE-Step | [ace-step](https://github.com/ace-step/ace-step) |
| Ollama | 로컬 무료 사용 시 |
| ffmpeg | MP3 export 시 필요 |

---

## 설치 및 실행

### 1. 의존성 설치

```bash
cd backend
pip install -r requirements.txt
pip install -r requirements-ollama.txt   # Ollama 사용 시
# pip install -r requirements-claude.txt  # Claude 사용 시
```

### 2. 환경변수 설정

```bash
cp backend/.env.example backend/.env
# .env 편집: AI_PROVIDER, API_KEY 등 설정
```

### 3. 서비스 실행 (터미널 3개)

```bash
# 터미널 1 — ACE-Step
cd ~/ace-step
uv run acestep-api
# → http://localhost:8001

# 터미널 2 — Ollama (ollama 사용 시)
ollama serve
ollama pull llama3.2   # 최초 1회

# 터미널 3 — FastAPI
cd backend
uvicorn main:app --reload --port 8000
# → http://localhost:8000
```

브라우저에서 `http://localhost:8000` 접속.

---

## 프로젝트 구조

```
MOM/
├── backend/
│   ├── main.py               FastAPI 앱, 전체 라우터
│   ├── db.py                 SQLite CRUD (sessions/tracks/mix_versions)
│   ├── queue_worker.py       PriorityQueue 워커 (HEAVY/LIGHT)
│   ├── track_generator.py    ACE-Step 순차 생성 + SSE
│   ├── mixer.py              pydub 볼륨 믹싱, waveform JSON
│   ├── session_manager.py    세션 복원 + TTL 24h APScheduler
│   ├── prompt_builder.py     ACE-Step caption 빌더
│   ├── ace_client.py         ACE-Step HTTP 클라이언트
│   ├── config.py             환경변수 파싱, CORS, API 키 인증
│   ├── ai_provider/          Provider 추상화 레이어
│   │   ├── base.py           TrackSpec, PlanResult, FALLBACK_RESULT
│   │   ├── factory.py        get_provider(), switch_provider()
│   │   ├── ollama_provider.py
│   │   ├── claude_provider.py
│   │   ├── openai_provider.py
│   │   └── gemini_provider.py
│   ├── requirements.txt
│   └── .env.example
├── frontend/
│   └── index.html            Vanilla JS 2페이지 DAW UI
├── tests/
│   ├── conftest.py           pytest fixtures (ace_mock, provider_mock 등)
│   └── test_integration.py   통합 테스트 6개 시나리오
└── pytest.ini
```

---

## API 요약

| Method | Path | 설명 |
|--------|------|------|
| `POST` | `/plan` | AI 트랙 기획 |
| `GET`  | `/session/{id}` | 세션 복원 |
| `POST` | `/generate/all` | 전체 생성 (SSE) |
| `POST` | `/generate/track/{id}/{order}` | 단일 재생성 (SSE) |
| `POST` | `/repaint` | 구간 재생성 (SSE) |
| `POST` | `/track/{id}/{order}/volume` | 볼륨 조절 |
| `POST` | `/track/{id}/{order}/lock` | BPM/Key 잠금 |
| `POST` | `/mix/{id}` | 믹스 생성 |
| `GET`  | `/mix/{id}/versions` | 믹스 버전 목록 |
| `GET`  | `/waveform/{id}/{order}` | 파형 데이터 |
| `POST` | `/provider/switch` | AI Provider 전환 (SSE) |
| `GET`  | `/health` | 서버/ACE-Step 상태 |

SSE 응답 이벤트: `progress` · `done` · `error` · `provider_switched`

---

## 테스트

```bash
pip install -r requirements-test.txt
pytest -v
```

| 시나리오 | 검증 항목 |
|---------|---------|
| S1 전체 생성 | /plan → /generate/all → WAV 저장 |
| S2 단일 재생성 | LIGHT queue → WAV 교체 |
| S3 Repaint | start/end 유효성 + 구간 재생성 |
| S4 믹스+버전 | mix_v1 생성, 최대 10버전 순환 |
| S5 세션 복원 | /session/{id} → 404 포함 |
| S6 Provider 전환 | LIGHT queue → provider_switched |

---

## AI Provider 추가

1. `backend/ai_provider/` 에 `{name}_provider.py` 구현 (`BaseProvider` 상속)
2. `factory.py` `_create()` 에 `elif name == "{name}":` 1줄 추가
