# AI Composer 다른 PC 설치 가이드

## 사전 요구사항

| 항목 | 버전/링크 |
|------|----------|
| Windows 10/11 | 64-bit |
| Python | 3.9+ (Anaconda 권장) |
| NVIDIA GPU + CUDA | 6GB+ VRAM 권장 |
| Git | https://git-scm.com/ |

## 1. ACE-Step 설치

```powershell
# uv 패키지 매니저 (없으면)
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"

# ACE-Step 클론 + 의존성 설치
git clone https://github.com/ace-step/ace-step.git C:\ace-step
cd C:\ace-step
uv sync
```

## 2. Ollama 설치 (선택, AI 기획용)

https://ollama.com/download 에서 설치 후:
```powershell
ollama pull llama3.2
```

미설치 시 자동으로 fallback 트랙 (드럼/베이스/피아노) 사용.

## 3. AI Composer 압축 해제 + 의존성 설치

```powershell
# 압축 해제한 폴더로 이동
cd C:\your\path\MOM

# Python 의존성
cd backend
pip install -r requirements.txt
pip install -r requirements-ollama.txt
cd ..

# 트레이 런처 의존성
pip install -r launcher\requirements.txt
```

## 4. 환경변수 설정

`backend\.env` 파일 생성 (예시):
```env
AI_PROVIDER=ollama
OLLAMA_HOST=http://localhost:11434
ACESTEP_URL=http://localhost:8001
API_KEY=
DB_PATH=sessions.db
OUTPUTS_DIR=outputs
CORS_ORIGINS=["http://localhost:8080","http://127.0.0.1:8080"]
SESSION_TTL_HOURS=24
MAX_MIX_VERSIONS=10
```

런처 경로가 다르면 시스템 환경변수 추가:
| 변수 | 기본값 | 설명 |
|------|-------|----|
| `ACE_STEP_DIR` | `C:\Users\heo01\ace-step` | ACE-Step 설치 경로 |
| `UV_PATH` | `C:\Users\heo01\.local\bin\uv.exe` | uv 실행 파일 |
| `OLLAMA_EXE` | `ollama` | Ollama 실행 파일 |
| `FASTAPI_PORT` | `8080` | FastAPI 포트 |

## 5. 실행

### A. dev 모드 (개발용)
```powershell
cd MOM\launcher
.\dev_run.bat
```

### B. .exe 빌드 + 더블클릭
```powershell
cd MOM\launcher
.\build.bat
# dist\AIComposer.exe 생성 → MOM\ 루트로 이동 → 더블클릭
```

트레이 아이콘 표시 + 브라우저 자동 오픈.

## 문제 해결

| 증상 | 원인 | 해결 |
|------|----|----|
| 트레이 아이콘 빨강 | 서비스 실행 실패 | `logs\*.log` 확인 |
| `ReadTimeout` | VRAM 부족 | 다른 GPU 앱 종료, 길이 5초로 시도 |
| `Ollama 404` | 모델 미설치 | `ollama pull llama3.2` |
| `503 Model not initialized` | ACE-Step 초기화 중 | 5분 대기 후 재시도 |

## 폴더 구조

```
MOM/
├── backend/         FastAPI 서버
├── frontend/        Vanilla JS UI
├── launcher/        트레이 런처 (pystray)
├── tests/           pytest 통합 테스트
├── logs/            서비스 로그 (런타임 생성)
├── outputs/         생성된 WAV/MP3 (런타임 생성)
├── sessions.db      SQLite DB (런타임 생성)
├── README.md        프로젝트 개요
├── SETUP.md         (이 파일)
└── CLAUDE.md        개발 가이드
```
