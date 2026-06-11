# AI Composer 패키지 배포 기획서 v1.3 (로컬)

> 대상 제품: **AI Composer v2.8** (ACE-Step 기반 멀티트랙 AI 작곡 + Demucs 스템 분리)
> 배포 형태: **Windows 원클릭 설치 프로그램(.exe)**
> 작성일: 2026-06-01 (v1.3 — Gemini 리뷰 병합: 임베디드 Python 제약·Ollama 데몬 동기화·백신 오탐지·용어집)

---

## 1. 개요 및 목적

AI Composer를 **비개발자 최종 사용자**가 더블클릭 한 번으로 설치·실행할 수 있는
Windows 설치 프로그램(`AIComposerSetup.exe`)으로 패키징한다.

현재는 launcher가 트레이 `.exe`를 빌드할 수 있으나, ACE-Step·Ollama·uv·Python
의존성이 **개발자 PC의 하드코딩 경로에 사전 설치**돼 있어야만 동작한다(진정한 배포 아님).
본 기획은 그 사전 요구사항을 **설치 프로그램 + 첫 실행 셋업 마법사**가 자동 처리하도록 한다.

### 목표 (Goals)
- 더블클릭 → 설치 마법사 → 바탕화면 아이콘 → 실행까지 **무(無) 명령줄**
- 파이썬/패키지/모델을 사용자가 직접 설치하지 않음
- 오프라인 PC도 고려(대용량 자산은 첫 실행 시 다운로드, 진행률 표시)

### 비목표 (Non-Goals)
- macOS/Linux 인스톨러 (1차는 Windows 10/11 x64 전용)
- 클라우드/멀티유저 배포 (로컬 단일 사용자 데스크톱 앱)
- ACE-Step·Ollama 자체 재배포(라이선스) — **공식 배포본을 자동 내려받아 설치**

---

## 2. 배포 구성요소 분류

설치 용량과 라이선스를 고려해 **동봉 / 첫 실행 다운로드 / 외부 설치**로 3분류한다.

| 구성요소 | 용량(대략) | 처리 방식 | 비고 |
|----------|-----------|----------|------|
| 백엔드 코드 + 프론트엔드 | < 5 MB | **동봉** | PyInstaller 또는 임베디드 Python |
| 트레이 런처 | < 10 MB | **동봉** | 기존 `launcher/` 재사용 |
| Python 런타임 | ~15 MB | **동봉** | python embeddable package 3.11 |
| 백엔드 순수 deps (fastapi 등) | ~30 MB | **동봉** | wheel 사전 포함 |
| torch (CUDA) + demucs | ~2.5 GB | **첫 실행 다운로드** | GPU 유무 감지 후 CUDA/CPU 휠 선택 |
| soundfile / ffmpeg | ~30 MB | **동봉** | torchaudio WAV 백엔드 필수 |
| Demucs htdemucs 가중치 | ~80 MB | **첫 실행 다운로드** | `prefetch_demucs` 재사용 |
| ACE-Step 엔진 + 모델 | 수 GB | **첫 실행 다운로드/설치** | 공식 배포본, 별도 폴더 |
| **uv (astral)** | ~30 MB | **동봉** | ACE-Step을 `uv run acestep-api`로 기동(`launcher/services.py`). 번들 후 `UV_PATH` `.env` 기록 |
| Ollama + llama3.2 | ~2 GB | **첫 실행: 공식 설치본 자동 실행** | 또는 사용자 안내 |

> **설치 프로그램 자체 크기 ≈ 80~120 MB** 목표. 대용량은 첫 실행 마법사가 처리.

---

## 3. 설치 사용자 경험 (UX 흐름)

```
AIComposerSetup.exe 더블클릭
   │
   ├─ 1. 라이선스/경로 선택 (기본 C:\Program Files\AI Composer)
   ├─ 2. 파일 복사 (동봉 구성요소)
   ├─ 3. 바탕화면/시작메뉴 바로가기 생성
   └─ 4. 설치 완료 → "지금 실행" 체크
            │
            ▼
   첫 실행 셋업 마법사 (최초 1회)
   ├─ GPU/CUDA 감지 (nvidia-smi)
   ├─ torch(CUDA or CPU) + demucs 다운로드·설치   [진행률]
   ├─ Demucs 가중치 prefetch                        [진행률]
   ├─ ACE-Step 엔진/모델 설치                        [진행률]
   ├─ Ollama 설치 확인 → 없으면 공식 설치본 실행
   │     └─ ollama pull llama3.2                     [진행률]
   └─ 준비 완료 → 트레이 런처 자동 시작 → 브라우저 오픈
            │
            ▼
   이후 실행: 트레이 아이콘 더블클릭 → 즉시 기동
```

---

## 4. 기술 스택

| 영역 | 선택 | 사유 |
|------|------|------|
| 인스톨러 | **Inno Setup 6** (`.iss` 스크립트) | 무료·안정·한글 지원·코드사이닝 가능, 스크립트 가독성 |
| 파이썬 동봉 | **Python embeddable package** | PyInstaller 단일 exe보다 deps 추가/torch 설치가 유연 |
| 첫 실행 마법사 | 기존 **트레이 런처 확장** (PySide/tkinter 진행률 창) | 코드 재사용, 별도 GUI 프레임워크 불필요 |
| 대용량 다운로드 | `pip --target` + `httpx`/`urllib` | torch는 PyTorch 인덱스, 모델은 공식 URL |
| 코드 서명(선택) | signtool + 인증서 | SmartScreen 경고 완화 |

> 대안: 전 구성요소를 동봉한 **오프라인 풀 패키지(.exe ~6GB)** 옵션도 빌드 플래그로 제공 가능.

---

## 5. 산출물 디렉터리 구조 (설치 후)

```
C:\Program Files\AI Composer\
├─ AIComposer.exe            # 트레이 런처 (진입점)
├─ python\                   # 임베디드 Python 3.11 + site-packages
├─ backend\                  # FastAPI 백엔드 (현 MOM/backend 그대로)
├─ frontend\                 # 정적 UI
├─ bin\
│   ├─ ffmpeg.exe            # mp3 export / 오디오 로딩
│   ├─ uv.exe                # ACE-Step 기동 런너 (launcher가 UV_PATH로 호출)
│   └─ ...
├─ engines\
│   └─ ace-step\             # 첫 실행 시 설치 (또는 외부 경로 링크)
├─ models\                   # demucs 가중치 등 캐시
└─ config\
    └─ .env                  # 사용자 설정 (DEMUCS_DEVICE, ACE_STEP_DIR, UV_PATH, FASTAPI_PORT, LOG_DIR 등)

%LOCALAPPDATA%\AI Composer\  # 쓰기 가능 데이터(설치 폴더와 분리)
├─ sessions.db
├─ outputs\
└─ logs\
```

> **중요:** `Program Files`는 쓰기 제한 → DB·outputs·logs는 `%LOCALAPPDATA%`로 분리.
> **현 코드 상태(P0 보완 대상):**
> - `backend/config.py`는 **이미 `DB_PATH`·`OUTPUTS_DIR` 환경변수 오버라이드 지원**(기본값만 프로젝트 루트). → 마법사가 `.env`에 `%LOCALAPPDATA%` 경로 기록하면 해결.
> - ⚠️ `launcher/config.py`의 **`LOG_DIR = PROJECT_ROOT / "logs"` 는 env 오버라이드 없이 고정** → Program Files 설치 시 쓰기 실패. **`LOG_DIR` env화 필요**(P0).
> - ⚠️ `launcher/config.py` 하드코딩 기본값 **`ACE_STEP_DIR=C:\Users\heo01\ace-step`, `UV_PATH=C:\Users\heo01\.local\bin\uv.exe`** → 설치 위치(`engines\ace-step`, `bin\uv.exe`)로 교체 + 마법사가 `.env` 기록(P0/P2).

---

## 6. 의존성 처리 전략 (핵심 난점)

### 6-1. torch CUDA vs CPU 자동 선택
- 첫 실행 마법사에서 `nvidia-smi` 성공 → CUDA 휠(`--index-url .../cu124`), 실패 → CPU 휠
- 설치 후 `torch.cuda.is_available()` 검증, 실패 시 CPU 폴백 + `.env` 자동 기록

### 6-2. torchaudio 오디오 백엔드
- **soundfile 동봉 필수** (torchaudio 2.x는 Windows 백엔드 미포함 → demucs WAV 로드 실패 이력 있음)
- ffmpeg.exe 동봉으로 mp3 export·범용 디코딩 확보

### 6-3. ACE-Step (+ uv 런너)
- **온라인 슬림:** 첫 실행 마법사가 공식 배포본을 `engines/ace-step`에 자동 설치
- **오프라인 풀:** 동봉본을 `engines/ace-step`로 복사(MIT, 재배포 허용 — §15 라이선스 고지 동봉)
- **uv 의존성(필수):** 런처는 ACE-Step을 `uv run acestep-api`로 기동(`launcher/services.py:121`).
  - **uv.exe를 `bin\uv.exe`로 동봉**하고, 마법사가 `UV_PATH=...\bin\uv.exe`를 `.env`에 기록.
  - 설치 위치를 `ACE_STEP_DIR=...\engines\ace-step`로 `.env` 기록(하드코딩 기본값 `C:\Users\heo01\ace-step` 제거).
  - 검증: `uv --version` 성공 + `uv run acestep-api` 기동 후 `:8001` health 응답.
- 기존 설치가 있으면 `ACE_STEP_DIR` `.env`로 링크해 재다운로드 생략
- 첫 요청 시 모델 lazy-load (현 구조 유지)

### 6-4. Ollama (데몬 동기화)
- 설치 감지(`where ollama`) → 없으면 공식 OllamaSetup.exe 자동 실행 안내
- **데몬 준비 대기 필수:** 설치/기동 직후 곧바로 `pull` 하면 데몬 미기동으로 실패.
  `http://localhost:11434/api/version`(또는 `/`)에 **HTTP 폴링**하여 응답 확인 후 진행
  (예: 0.5s 간격, 최대 30s 타임아웃)
- 데몬 준비 확인 → `ollama pull llama3.2` 진행률 표시

### 6-5. requirements 인코딩
- requirements*.txt는 **순수 ASCII만** (한국어 Windows cp949에서 비ASCII 시 pip 디코딩 실패 이력)

### 6-6. Python embeddable 패키지 제약 (필수 선처리)
동봉하는 python embeddable 배포본은 기본 상태로는 외부 패키지(torch 등)를 못 불러온다.
빌드 스테이징(`fetch_python.ps1`)에서 다음을 선처리한다.
- **`pythonXY._pth` 수정:** `#import site` 줄의 **주석 해제**(`import site`) →
  site-packages·`.pth` 경로 인식 활성화
- **pip 부트스트랩:** `get-pip.py`를 임베디드 인터프리터로 1회 실행해 pip 설치
- 이후 `python\python.exe -m pip install --target ...` 로 의존성 주입 가능
- 검증: `python -c "import site, pip"` 성공 여부

### 6-7. 다운로드 무결성 검증 (공급망 보안)
- 첫 실행 다운로드 자산(torch 휠, Demucs 가중치, ACE-Step 모델)은 **SHA-256 해시 매니페스트**(`manifest.json`, 빌드 시 고정)와 대조 검증한다.
- torch는 PyTorch 공식 인덱스 휠 해시, Demucs/ACE-Step은 공식 배포 해시를 기록. 불일치 시 설치 중단·재다운로드.
- 모든 다운로드는 **HTTPS 전용**, 인증서 검증 활성(검증 비활성화 금지).

### 6-8. 첫 실행 마법사 중단 복구
- 다운로드 단계별 **부분 완료 상태를 `.setup_progress.json`에 기록**(temp 디렉터리에 받고 검증 후 최종 위치로 atomic move).
- 중단(취소/전원/네트워크) 후 재실행 시 마지막 미완 단계부터 재개, 손상 temp 파일은 정리.
- `.first_run` 플래그는 **모든 단계 검증 통과 후에만** 기록(부분 설치 상태로 정상 기동 방지).

### 6-9. 런타임 포트·CORS·로컬 바인딩
- **포트 정합:** 런타임 FastAPI 포트는 **8080**(`launcher/config.py` `FASTAPI_PORT`). `.env.template`에 `FASTAPI_PORT=8080` 명시.
- **CORS 기본값 수정:** `backend/config.py`의 기본 `CORS_ORIGINS`가 `localhost:8000`이라 8080 누락.
  프론트를 FastAPI가 동일 오리진(8080)으로 서빙하면 무해하나, **`.env.template`에 `CORS_ORIGINS=http://localhost:8080,http://127.0.0.1:8080` 명시**해 불일치 제거.
- **로컬 바인딩 강제(보안):** uvicorn은 `--host 127.0.0.1`로 기동해 **LAN 노출 차단**(현재 `services.py:138`은 `--host` 미지정 → 기본 127.0.0.1이라 안전하나 명시 권장). `0.0.0.0` 바인딩 금지.
- **무인증 노출 주의:** `require_api_key`는 `API_KEY` 미설정/플레이스홀더 시 인증을 통과시킨다(로컬 단일 사용자 전제). 127.0.0.1 바인딩이 이 전제를 지키는 핵심 — 원격 접근 허용 시 반드시 `API_KEY` 설정.

---

## 7. 빌드 파이프라인 (개발자용)

```
build/ 디렉터리에 빌드 스크립트 추가
├─ 1. fetch_python.ps1     # embeddable python 내려받아 python\ 구성
├─ 2. stage_app.ps1        # backend/frontend/launcher 복사, .env.template 배치
├─ 3. fetch_offline.ps1    # (선택) 오프라인 풀 패키지용 torch/모델 사전 다운로드
├─ 4. build_launcher.bat   # PyInstaller로 AIComposer.exe (기존 build.bat 확장)
├─ 5. installer.iss        # Inno Setup 스크립트
└─ 6. make_installer.ps1   # 위 단계 오케스트레이션 → dist\AIComposerSetup.exe
```

산출물: `dist\AIComposerSetup.exe` (+ 선택적 `AIComposerSetup-offline.exe`)

---

## 8. 업데이트 / 제거

- **업데이트:** 인스톨러 재실행 → 기존 설치 감지 → 코드/런처만 교체, 모델·DB 보존
- **제거:** 제어판 또는 unins000.exe → 앱 삭제. `%LOCALAPPDATA%` 데이터는 "사용자 데이터 함께 삭제" 체크박스로 선택
- (선택) 앱 내 "업데이트 확인" → GitHub Releases 버전 비교

---

## 9. 시스템 요구사항

| 항목 | 최소 | 권장 |
|------|------|------|
| OS | Windows 10 x64 | Windows 11 x64 |
| RAM | 8 GB | 16 GB |
| GPU | 없음(CPU 폴백) | NVIDIA 6 GB+ (CUDA) |
| 디스크 | 12 GB 여유 | 20 GB+ |
| 인터넷 | 첫 실행 시 필요 | — |

> 6 GB VRAM은 Ollama·ACE-Step·Demucs가 공유 → 동시 사용 OOM 주의(큐 단일 워커로 직렬화하나 ACE-Step 서버 상주 점유 고려).

---

## 10. 리스크 및 대응

| 리스크 | 영향 | 대응 |
|--------|------|------|
| torch 2.5GB 다운로드 실패/중단 | 첫 실행 불가 | 재시도·이어받기, 오프라인 풀 패키지 옵션, 부분복구(§6-8) |
| **다운로드 자산 변조/손상** | 악성·손상 모델 실행 | SHA-256 매니페스트 검증 + HTTPS 전용(§6-7), 불일치 시 중단 |
| SmartScreen "알 수 없는 게시자" | 사용자 불안 | 코드 서명 인증서, 안내 문구 |
| **백신 오탐지(False Positive)** | 설치/실행 파일이 악성으로 차단·삭제 | PyInstaller·임베디드 exe 흔한 오탐 → 코드 서명(EV/OV)으로 평판 확보 + **백신 예외(화이트리스트) 등록 매뉴얼** 동봉. 빌드 후 VirusTotal 사전 점검 |
| Ollama 데몬 미기동 중 pull | 첫 실행 설치 실패 | 11434 포트 HTTP 폴링으로 준비 확인 후 진행(§6-4) |
| 임베디드 Python deps 미인식 | torch import 실패 | `._pth` import site 해제 + get-pip 선처리(§6-6) |
| Program Files 쓰기 권한 | DB/출력/로그 실패 | 데이터·로그 경로 %LOCALAPPDATA% 분리. ⚠️ `launcher/config.py` `LOG_DIR` env화 선행(§5) |
| GPU 미감지 오판 | 느린 CPU 동작 | 마법사에서 수동 CUDA/CPU 토글 제공 |
| ACE-Step/Ollama 대용량 | 디스크 부족 | 설치 전 용량 점검, 구성요소 선택 설치 |
| **uv 미동봉/경로 오류** | ACE-Step 기동 불가 | uv.exe `bin\` 동봉 + `UV_PATH`/`ACE_STEP_DIR` `.env` 기록, 하드코딩 기본값 제거(§6-3) |
| **백엔드 LAN 노출** | 무인증 API 외부 접근 | uvicorn `--host 127.0.0.1` 강제, 원격 허용 시 `API_KEY` 필수(§6-9) |

---

## 11. 개발 단계 (Phase)

| Phase | 작업 | 산출물 | 예상 |
|-------|------|--------|------|
| **P0** | 경로 일반화 — DB/outputs(이미 env 지원) + **`launcher` `LOG_DIR` env화**, 하드코딩 `ACE_STEP_DIR`/`UV_PATH` 기본값 제거, `--host 127.0.0.1`·`CORS_ORIGINS`·`FASTAPI_PORT=8080` `.env.template` 정비 | config/launcher 패치, `.env.template` | 1.5일 |
| **P1** | 임베디드 Python 스테이징 + **uv.exe `bin\` 번들** | `fetch_python.ps1`, `stage_app.ps1` | 1일 |
| **P2** | 첫 실행 셋업 마법사 (GPU감지·torch·모델·Ollama·uv 검증, `UV_PATH`/`ACE_STEP_DIR` `.env` 기록, 진행률 UI) | `setup_wizard.py` | 3일 |
| **P3** | Inno Setup 스크립트 + 바로가기/제거 | `installer.iss` | 1.5일 |
| **P4** | 빌드 오케스트레이션 + 온라인/오프라인 두 변형 | `make_installer.ps1` | 1일 |
| **P5** | 코드 서명(선택) + 클린 VM 설치 테스트 | 서명된 setup.exe | 1.5일 |
| **P6** | 사용자 설치 가이드 + **개발 PC `sessions.db` 일회성 복사 스크립트**(결정 §12-4) | `INSTALL.md`, `migrate_sessions.ps1` | 0.5일 |

**총 예상: 약 10일** (P5 서명 제외 시 8.5일)

---

## 12. 확정된 결정 사항

이전 버전의 의사결정 4건을 아래와 같이 확정한다. ⚠ 표시는 **빌드 전 검증** 필요.

| # | 결정 항목 | 확정 내용 | 근거 / 비고 |
|---|----------|----------|------------|
| 1 | 배포 변형 | **온라인 슬림(~100MB)을 기본**으로, **오프라인 풀(~6GB)을 보조**로 둘 다 빌드 | 빌드 플래그(`-Offline`)로 분기. 일반 사용자는 슬림, 망 분리 환경은 풀 |
| 2 | ACE-Step 동봉 | **동봉 가능 확정**(MIT). 오프라인 풀=동봉, 온라인 슬림=자동 다운로드 | ACE-Step **MIT License** — 재배포 허용. 단 MIT 의무로 **저작권·라이선스 전문을 배포물에 포함**(§15 참조) |
| 3 | 코드 서명 | **1차 릴리스는 미서명** + SmartScreen 안내 문구 동봉, 2차에 EV/OV 인증서 도입 | 인증서 미보유. 미서명은 "추가 정보 → 실행" 가이드로 우회 |
| 4 | 세션 마이그레이션 | **불필요** (신규 배포, 기존 최종 사용자 없음). 개발 PC의 기존 `sessions.db`는 **일회성 복사 스크립트**만 제공 | 데이터 경로를 처음부터 `%LOCALAPPDATA%`로 출고 |

> 결정의 후속 작업은 Phase 표(§11)에 이미 반영됨: 변형 2종 빌드(P4), 데이터 경로 분리(P0), 서명(P5).

---

## 13. 아키텍처 · 시퀀스 다이어그램

### 13-1. 런타임 컴포넌트 구성도

```
┌──────────────────────── 사용자 PC (Windows x64) ────────────────────────┐
│                                                                          │
│   [브라우저]  http://localhost:8080                                       │
│       │  HTTP/SSE                                                         │
│       ▼                                                                   │
│   ┌─────────────────┐    enqueue     ┌──────────────────────────────┐    │
│   │ FastAPI :8080    │──────────────►│ PriorityQueue (단일 워커)      │    │
│   │ (backend)        │               │  HEAVY=0 / LIGHT=1            │    │
│   └───────┬─────────┘                └──────┬───────────────┬───────┘    │
│           │                                  │               │            │
│           │ 기획(plan)                        │ 생성/분리      │ 믹스        │
│           ▼                                  ▼               ▼            │
│   ┌─────────────┐        ┌──────────────────────┐   ┌──────────────┐     │
│   │ Ollama :11434│       │ ACE-Step :8001       │   │ Demucs(서브   │     │
│   │ llama3.2     │       │ text2music/repaint   │   │ 프로세스,GPU) │     │
│   └─────────────┘        └──────────────────────┘   └──────────────┘     │
│           │                        │                        │            │
│           └──────── GPU(VRAM 공유) ─┴────────────────────────┘            │
│                                                                          │
│   [트레이 런처 AIComposer.exe] ── 프로세스 기동/감시/로그 ── 위 3개 서비스      │
│                                                                          │
│   데이터: %LOCALAPPDATA%\AI Composer\ (sessions.db, outputs\, logs\)        │
└──────────────────────────────────────────────────────────────────────────┘
```

> **포트 주의:** 패키지 런타임 FastAPI 포트는 **8080**(`launcher/config.py`의 `FASTAPI_PORT` 기본값) — 배포본 기준값. 개발 문서(`AGENTS.md`)의 `uvicorn --port 8000`은 **개발 전용**이며, 배포 마법사/런처는 8080을 사용한다. ACE-Step 8001 / Ollama 11434는 동일.

### 13-2. 설치 시퀀스 (AIComposerSetup.exe)

```
사용자        Inno Setup        파일시스템         OS
 │ 더블클릭     │                  │                │
 ├────────────►│ 라이선스/경로 선택  │                │
 │             ├─ 디스크 용량 점검 ─►│                │
 │             ├─ 동봉 파일 압축해제─►│ Program Files\ │
 │             │   (python,backend, │ AI Composer\   │
 │             │    frontend,bin,런처)│                │
 │             ├─ 데이터 폴더 생성 ──►│ %LOCALAPPDATA% │
 │             ├─ 바로가기 생성 ──────┼───────────────►│ 바탕화면/시작메뉴
 │             ├─ 레지스트리 등록 ────┼───────────────►│ 제거 정보
 │ "지금 실행"  │                    │                │
 ├────────────►│ AIComposer.exe 실행 │                │
 │             ▼                    │                │
 │      [첫 실행 셋업 마법사로 분기] (13-3)              │
```

### 13-3. 첫 실행 셋업 마법사 시퀀스 (최초 1회)

```
런처         셋업마법사        네트워크/외부            로컬
 │ 최초 실행   │  (.first_run 플래그 없음 감지)          │
 ├──────────►│ GPU 감지(nvidia-smi)                    │
 │           ├─ 성공→CUDA / 실패→CPU 결정 ──► .env 기록   │
 │           ├─ torch+demucs 설치 ───► PyTorch 인덱스    │ [진행률]
 │           │     pip --target python\site-packages    │
 │           ├─ demucs 가중치 ───────► fbaipublicfiles  │ [진행률]
 │           │     (prefetch_demucs 재사용, ~80MB)       │
 │           ├─ ACE-Step 엔진/모델 ──► 공식 배포본        │ [진행률]
 │           │     (오프라인 풀이면 동봉본 복사로 대체)      │
 │           ├─ Ollama 확인 ─ 없으면 ─► OllamaSetup 실행  │
 │           │     ollama pull llama3.2 ──────────────► │ [진행률]
 │           ├─ 검증: torch.cuda / ACE /health / ollama  │
 │           ├─ .first_run 플래그 기록 ─────────────────► │
 │ 준비완료   │                                         │
 │◄──────────┤ 트레이 서비스 기동 → 브라우저 오픈          │
```

### 13-4. 스템 분리 생성 런타임 시퀀스 (기존 구현)

```
브라우저   FastAPI    Queue(HEAVY)   ACE-Step    Demucs       DB
 │ /generate/separated │             │           │            │
 ├────────►│ enqueue   │             │           │            │
 │  SSE◄───┤───────────►│ generate_separated      │            │
 │ queue   │           ├─ 곡 생성 ───►│           │            │
 │ progress◄───────────┤◄─ _source.wav            │            │
 │ (10%)   │           ├─ 분리 ───────────────────►│ stems      │
 │ progress◄───────────┤◄─ drums/bass/other ──────┤            │
 │ (50%)   │           ├─ clear_tracks + 등록 ─────────────────►│
 │         │           ├─ stem→track_N.wav 복사    │            │
 │ done◄───┤◄──────────┤ status=done, tracks       │            │
 │ (100%)  │           │             │           │            │
```

---

## 14. 설치 테스트 · QA 계획

배포 신뢰성의 핵심은 **개발 PC가 아닌 깨끗한 환경에서의 검증**이다. 개발 PC는 이미
torch·demucs·ACE-Step·Ollama가 설치돼 있어 "내 PC에선 됨" 함정에 빠지기 쉽다.

### 14-1. 테스트 환경 매트릭스

| # | 환경 | GPU | 검증 목적 |
|---|------|-----|----------|
| E1 | 클린 Windows 11 VM | 없음(CPU) | CPU 폴백 경로, torch CPU 휠, 전체 설치 |
| E2 | 클린 Windows 11 (NVIDIA 6GB) | CUDA | GPU 감지, CUDA 휠, Demucs GPU 분리 |
| E3 | Windows 10 x64 | 무관 | 하위 OS 호환 |
| E4 | 망분리(오프라인) PC | 무관 | 오프라인 풀 패키지 단독 설치 |
| E5 | 한국어 로캘 PC | 무관 | cp949 인코딩(경로/requirements), 한글 깨짐 |
| E6 | 디스크 부족(<12GB) | 무관 | 용량 점검·중단 처리 |

> VM은 스냅샷으로 **설치 전 상태 복원**해 반복 테스트.

### 14-2. 설치 검증 체크리스트

- [ ] Setup.exe 더블클릭 → 마법사 진행 → 오류 없이 완료
- [ ] 바탕화면/시작메뉴 바로가기 생성·동작
- [ ] 첫 실행 마법사: GPU 감지 결과가 실제와 일치(.env 기록 확인)
- [ ] torch 다운로드 진행률 표시·완료, `torch.cuda.is_available()` 기대값
- [ ] 다운로드 자산 SHA-256 매니페스트 검증 통과(변조/손상 탐지)
- [ ] 설치 중단 후 재실행 시 미완 단계부터 재개·temp 정리
- [ ] Demucs 가중치 prefetch 성공(캐시 파일 존재)
- [ ] ACE-Step `/health` 정상, Ollama `llama3.2` 응답
- [ ] 데이터가 `%LOCALAPPDATA%`에 기록(Program Files 쓰기 시도 없음)
- [ ] 트레이 아이콘 상태색 전이(회색→주황→초록)
- [ ] 브라우저 자동 오픈 → UI 로드

### 14-3. 스모크 테스트 (기능 최소 검증)

1. 기획 입력 → `/plan` → 트랙 목록 생성
2. 전체 생성(`/generate/all`) → 트랙별 WAV·파형 표시
3. **스템 분리 생성(`/generate/separated`)** → drums/bass/other 3트랙 + 재생
4. 단일 재생성 / Repaint / 볼륨 조절
5. 믹스 → mp3 다운로드
6. 앱 재시작 → 세션 복원

### 14-4. 업데이트 / 제거 / 롤백 테스트

- **업데이트:** 구버전 설치 위 신버전 설치 → 코드 교체, DB·모델·outputs 보존 확인
- **제거:** unins000 → 앱 삭제. "사용자 데이터 유지/삭제" 옵션 각각 검증
- **롤백:** 설치 중 중단(취소/전원/네트워크 끊김) → 부분 설치 잔여물 정리, 재설치 정상

### 14-5. 자동화 범위

- 백엔드 로직: 기존 **pytest 7 시나리오**(스템 분리 포함) CI 유지
- 인스톨러: Inno Setup `/SILENT /VERYSILENT` 무인 설치 → PowerShell 스모크 스크립트로 `/health`·스템 분리 자동 호출
- 수동 전용: SmartScreen 경고, 트레이 UI 상호작용, 클린 VM 첫인상

### 14-6. 릴리스 게이트 (통과 기준)

E1·E2·E5 **필수 통과**, 14-2/14-3 체크리스트 **전 항목 green**, pytest **7/7** 유지 시 릴리스 승인.
E3·E4·E6은 알려진 제약 문서화 시 조건부 통과 허용.

---

## 15. 서드파티 라이선스 고지

배포물(설치 폴더)에 `licenses\` 디렉터리를 두고 각 구성요소 라이선스 전문을 포함한다.
설치 마법사 첫 화면 또는 앱 정보(About)에서 열람 가능하도록 한다.

| 구성요소 | 라이선스 | 동봉 위치 | 비고 |
|----------|---------|----------|------|
| **ACE-Step** | **MIT** | `licenses\ACE-Step-LICENSE.txt` | 저작권·전문 포함 의무 (아래) |
| Demucs | MIT | `licenses\demucs-LICENSE.txt` | |
| PyTorch (torch) | BSD-3-Clause | `licenses\pytorch-LICENSE.txt` | |
| soundfile / libsndfile | BSD-3 / LGPL | `licenses\libsndfile-LICENSE.txt` | LGPL — 동적 링크 형태 유지 |
| FFmpeg | LGPL/GPL | `licenses\ffmpeg-LICENSE.txt` | LGPL 빌드 사용(GPL 코덱 제외) |
| Ollama | MIT | 외부 설치(고지만 링크) | 자체 설치본 |
| AI Composer(본 제품) | **MIT** | `LICENSE.txt` | Copyright (c) 2026 Jaehyeon Heo — 전문 §15-2 |

> **빌드 게이트:** `licenses\` 누락 시 인스톨러 빌드 실패하도록 `make_installer.ps1`에 검증 추가.

### 15-1. ACE-Step 라이선스 전문

```
MIT License

Copyright (c) 2026 ACEStep

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

### 15-2. AI Composer 라이선스 전문

```
MIT License

Copyright (c) 2026 Jaehyeon Heo

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

---

## 16. 용어 정리

| 용어 | 설명 |
|------|------|
| **`.pth` 파일 (Python Path File)** | Python이 모듈을 찾을 때 참조하는 경로 설정 파일. Windows 임베디드 환경에선 외부 패키지 로드를 위해 `pythonXY._pth`의 `import site` 주석 해제가 필수 |
| **데몬 (Daemon)** | 사용자가 직접 제어하지 않고 백그라운드에서 상주하며 요청 시 응답하는 프로그램(서비스). 예: Ollama(11434), ACE-Step(8001) |
| **오탐지 (False Positive)** | 백신이 정상·안전한 소프트웨어를 악성 코드로 잘못 인식해 차단·삭제하는 현상. PyInstaller/임베디드 exe에서 흔함 |
| **임베디드 Python (embeddable package)** | 시스템 설치 없이 폴더째 동봉하는 경량 Python 배포본. 기본 상태론 pip·site-packages 비활성 → 선처리 필요(§6-6) |
| **휠 (wheel)** | 파이썬 사전 빌드 패키지 형식(.whl). torch는 CUDA/CPU 별로 다른 휠 제공 |
| **스템 (stem)** | 믹스에서 분리된 개별 악기 트랙(드럼/베이스/기타 등). Demucs가 사후 분리 |

---

## 부록 A. 버전 이력

| 버전 | 변경 |
|------|------|
| v1.0 | 최초 작성 — 배포 아키텍처·구성요소·Phase |
| v1.1 | 의사결정 4건 확정, 시퀀스 다이어그램(§13), QA 계획(§14) |
| v1.2 | ACE-Step MIT 동봉 확정, 서드파티 라이선스 고지(§15) |
| v1.3 | Gemini 리뷰 병합 — 임베디드 Python 제약(§6-6), Ollama 데몬 동기화(§6-4), 백신 오탐지 리스크(§10), 용어집(§16). 정합성 수정 — 제목 버전 정정, §6 절번호 순서 정렬, 8080 포트 명확화(§13-1). 보안 보강 — 다운로드 무결성 검증(§6-7), 첫 실행 중단 복구(§6-8). 자체 라이선스 확정 — AI Composer **MIT / Copyright (c) 2026 Jaehyeon Heo**(§15-2). 코드 대조 보완 6건 — uv 의존성 명문화(§2·§6-3), `launcher` `LOG_DIR` env화·하드코딩 경로 제거(§5·P0), CORS/포트/127.0.0.1 바인딩·무인증 노출(§6-9), 세션 마이그레이션 스크립트 산출물화(P6), 리스크 표·Phase 표 갱신 |
