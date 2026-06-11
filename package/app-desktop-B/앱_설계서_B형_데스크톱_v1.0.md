# AI Composer v2.8 — 앱 설계서 (B형 · 데스크톱 씬 클라이언트) v1.0

> 구조: **Windows 데스크톱 .exe(씬 클라이언트) + 다른 PC GPU(풀스택 backend)**
> 출처: 로컬·클라우드 배포 기획서 v1.3
> 코드 대조: `MOM/backend/*`, `MOM/frontend/index.html`, `MOM/launcher/*`
> 작성일: 2026-06-08

---

## 1. 개요

내 PC의 `.exe`는 **원격 UI 창**일 뿐이고, 무거운 생성(ACE-Step·Demucs·Ollama)과 backend는
**GPU PC가 전부 수행**한다. 내 PC는 GPU·모델·Python 설치 불필요.

```
┌─ 내 PC ───────────────┐         ┌─ GPU PC (LAN/Tailscale) ──────────────────┐
│ AIComposer.exe        │         │ FastAPI :8080 (frontend 서빙 + API)        │
│  = pywebview 창       │─HTTP/SSE►│   ├ ACE-Step :8001 (localhost 전용)        │
│  http://<GPU_PC>:8080 │◄────────│   ├ Demucs (backend 서브프로세스, CUDA)     │
│  + 트레이 + 설정       │         │   ├ Ollama :11434 (localhost 전용)         │
└───────────────────────┘         │   └ sessions.db / outputs/ (로컬 디스크)    │
                                   └────────────────────────────────────────────┘
        ※ GPU PC는 8080만 LAN 노출. 8001·11434는 localhost 전용.
```

### 왜 코드 변경 최소인가
- `frontend/index.html`의 `api()`는 **상대경로** fetch(`/plan`, `/session/...`, `index.html:358`) →
  창이 `http://<GPU_PC>:8080`을 로드하면 모든 요청이 GPU PC로 감. **라우팅 수정 0**
  (Ollama 고정에 따른 Provider 셀렉터 숨김 1건만 예외 — §10).
- 프론트가 backend와 **동일 origin**(8080)에서 서빙됨 → **CORS 무이슈**, 인증 헤더 문제 회피.
- backend는 `/`에서 `index.html` 서빙(`main.py:107`), `/outputs` 정적 마운트(`main.py:30`) → 그대로 동작.

---

## 2. 컴포넌트 배치

| 컴포넌트 | 위치 | 비고 |
|----------|------|------|
| AIComposer.exe (창+트레이) | **내 PC** | pywebview/Tauri, 번들 경량 |
| FastAPI backend + frontend | **GPU PC** | `--host 0.0.0.0 --port 8080` |
| ACE-Step 엔진+모델 | **GPU PC** | `uv run acestep-api`, :8001 localhost |
| Demucs(분리) | **GPU PC** | backend 서브프로세스, `DEMUCS_DEVICE=cuda` |
| Ollama+llama3.2 | **GPU PC** | plan용, :11434 localhost. **AI Provider = Ollama 고정**(Claude/OpenAI/Gemini 미사용) |
| sessions.db / outputs | **GPU PC** | 로컬 디스크 |

> 데이터·세션은 **GPU PC에 집중** → 내 PC를 바꿔도 세션 보존. 다른 기기 브라우저로도 접속 가능(같은 LAN/tailnet).

---

## 3. GPU PC — 설치 · 상시 구동

### 3-1. 설치 (1회) — B형 풀스택
| # | 항목 | 명령 |
|---|------|------|
| 1 | NVIDIA 드라이버 + CUDA | 버전 정합(cu124 등) |
| 2 | Python 3.11 + uv | — |
| 3 | ACE-Step 엔진+모델 | 공식 배포본 |
| 4 | backend 순수 deps | `pip install -r requirements.txt` |
| 5 | torch CUDA → demucs+soundfile | `pip install -r requirements-demucs.txt` |
| 6 | ffmpeg | pydub mp3 export·디코딩 |
| 7 | Demucs 가중치 prefetch | `python -m backend.prefetch_demucs` |
| 8 | **Ollama + llama3.2 (필수)** | `ollama pull llama3.2` — Provider Ollama 고정이라 생략 불가 |

### 3-2. `.env` (GPU PC)
```
AI_PROVIDER=ollama          # 고정 — 런타임 교체 안 함
OLLAMA_MODEL=llama3.2       # provider 기본값
ACESTEP_URL=http://localhost:8001
ACESTEP_CLIENT_TIMEOUT=1800
DEMUCS_DEVICE=cuda
DB_PATH=./sessions.db
OUTPUTS_DIR=./outputs
# 같은 origin 서빙이라 CORS 사실상 불필요. 외부 기기 직접 접속 허용 시만:
CORS_ORIGINS=http://localhost:8080
# API_KEY 미설정 (LAN 신뢰망 전제). ⚠ 설정 시 프론트 401 — §7 참조
```

> **Provider 고정:** `AI_PROVIDER=ollama` 외 값 미사용. 외부 API(Claude/OpenAI/Gemini) 키·요금 0.
> 프론트 헤더의 Provider 셀렉터(`index.html:235`)와 `/provider/switch` 라우트(`main.py:281`)는 **미사용** → 셀렉터 숨김(§10).

### 3-3. 상시 구동 (부팅 자동)
- ACE-Step: `uv run acestep-api` (작업 스케줄러 "로그온 시" 또는 NSSM 서비스)
- backend: `uvicorn backend.main:app --host 0.0.0.0 --port 8080`
- 권장: **NSSM**으로 두 프로세스를 Windows 서비스 등록 → 부팅 시 자동, 다운 시 재시작.
- 웜업(선택): 기동 후 `POST :8001/v1/init`로 ACE-Step 모델 선로드(첫 생성 지연 제거, `services.py:93`).

---

## 4. 내 PC — .exe 씬 클라이언트 설계

### 4-1. 기술 선택
| 후보 | 장점 | 단점 |
|------|------|------|
| **pywebview** ✅ | Python, 기존 `launcher/` 자산 재사용, PyInstaller .exe | webview2 런타임 의존 |
| Tauri | 초경량(.exe 수MB), 자동업데이트 | Rust 스택 신규 |
| Electron | 생태계 큼 | 무겁다(~100MB+) |

> 기존 `launcher/`(트레이·아이콘)가 Python이라 **pywebview** 최단. WebView2는 Win10/11 기본 동반(없으면 설치).

### 4-2. 동작
```python
# 개념 — client_app.py
import webview, json, os
cfg = load_config()                      # GPU PC 주소 저장본
url = f"http://{cfg['gpu_host']}:8080"
if not reachable(url):                   # GPU PC 꺼짐/주소 오류
    url = settings_page()                # 주소 입력 + (선택) WoL 버튼
window = webview.create_window("AI Composer", url, width=1200, height=800)
webview.start()
```
- **트레이 아이콘**: 기존 `launcher/tray_app.py` 재사용 — 상태색(연결됨 초록 / GPU PC 꺼짐 회색).
- **첫 실행 설정**: GPU PC 주소(LAN IP 또는 Tailscale 100.x) 입력 → `%LOCALAPPDATA%\AIComposer\client.json` 저장.
- **연결 실패 UX**: "GPU PC가 꺼져 있습니다" + [Wake-on-LAN 보내기] + [주소 변경].

### 4-3. .exe가 **안** 하는 것
- ACE-Step/Ollama 프로세스 기동·감시 ❌ (GPU PC 담당) → 기존 `launcher/services.py:make_acestep/make_ollama/make_fastapi` **불필요**.
- torch·demucs·python 번들 ❌ → .exe 경량.

---

## 5. 네트워크 · 연결

| 경로 | 설정 | 보안 |
|------|------|------|
| **LAN(같은 집)** | `gpu_host=192.168.x.x` | 신뢰망, 평문 OK |
| **WAN(외부)** | 두 PC Tailscale → `gpu_host=100.x.x.x` | 사설 메시, 공개 0 |

- **포트포워딩 8080 직개방 금지** — backend 무인증 전제(§7). 외부는 Tailscale만.
- 8001(ACE-Step)·11434(Ollama)는 **GPU PC localhost 전용** — LAN에도 노출 불필요(backend가 localhost로 호출).
- **Wake-on-LAN**(선택): GPU PC BIOS WoL 활성 → .exe가 매직패킷 전송해 원격 기상.

---

## 6. 사용자 경험

```
[GPU PC] 부팅 → backend·ACE-Step 자동 기동(NSSM) → 대기
[내 PC ] AIComposer.exe 더블클릭
          ├ 연결 OK  → 창 열림 → 기획·생성·편집·믹스 (생성=GPU PC)
          └ 연결 실패 → 설정/WoL 화면
```
- 첫 생성만 ACE-Step lazy-load 지연(웜업하면 제거). 이후 즉답.

---

## 7. 보안 (LAN 전제)

| 항목 | 방침 |
|------|------|
| backend 노출 | 8080만 LAN. WAN은 Tailscale |
| 내부 서비스 | 8001·11434 GPU PC localhost 전용 |
| 인증 | ⚠️ **API_KEY 미설정 유지** — LAN 신뢰망 전제 |
| ⚠️ API_KEY 켜면 | `require_api_key`(`config.py:59`)는 켜지나, 프론트가 `X-API-Key` 미전송(`index.html:358`) → **자기 호출 401**. 켜려면 프론트 헤더 주입 패치 선행 |

> 결론: LAN/Tailscale 사설망이면 네트워크 격리로 충분 → API_KEY 불필요. 진짜 공개가 필요해질 때만 프론트 패치 + API_KEY.

---

## 8. 빌드 파이프라인

### 8-1. .exe (내 PC 배포물)
```
client/
├─ client_app.py        # pywebview 창 + 설정 + WoL
├─ tray.py              # 기존 launcher/tray_app.py 축소 재사용
├─ client.spec          # PyInstaller → AIComposer.exe
└─ installer.iss        # (선택) Inno Setup — 바로가기/제거
```
산출물: `AIComposerClient.exe` (경량). WebView2 미설치 PC 대비 부트스트랩 동봉(선택).

### 8-2. GPU PC (서버 셋업)
```
server/
├─ install_server.ps1   # deps·torch CUDA·demucs·ffmpeg·prefetch·ollama pull
├─ .env.template        # DEMUCS_DEVICE=cuda, host 0.0.0.0:8080
└─ register_services.ps1 # NSSM으로 acestep·backend 서비스 등록(부팅 자동)
```

---

## 9. 개발 단계 (Phase)

| Phase | 작업 | 산출물 | 예상 |
|-------|------|--------|------|
| **B0** | GPU PC 풀스택 수동 구축·검증(생성·분리·믹스) | 동작 확인 | 1일 |
| **B1** | GPU PC 서비스 자동기동(NSSM) + 웜업 | `register_services.ps1` | 1일 |
| **B2** | pywebview 창 + 설정(GPU 주소) + 연결 체크 | `client_app.py` | 1.5일 |
| **B3** | 트레이 통합(상태색) + 연결실패/WoL UX | `tray.py` | 1일 |
| **B4** | PyInstaller .exe + (선택) Inno Setup | `AIComposerClient.exe` | 1일 |
| **B5** | LAN/Tailscale E2E + 클린 PC 첫인상 | 테스트 리포트 | 1일 |

**총 ~6.5일** (서버 셋업 스크립트 포함).

---

## 10. 기존 코드 대비 변경점

| 대상 | 변경 |
|------|------|
| `backend/*` | **변경 0** (GPU PC에서 그대로 기동, `AI_PROVIDER=ollama` env 고정) |
| `frontend/index.html` | **소규모 1건** — Provider 셀렉터(`:235-243`) + change 핸들러(`:571`) 숨김/제거(Ollama 고정). 그 외 상대경로·동일 origin 무수정 |
| `launcher/services.py` | 씬 클라이언트는 **미사용**(프로세스 관리 GPU PC로 이동). GPU PC 서비스 등록은 NSSM 스크립트로 대체 |
| `launcher/tray_app.py` | **축소 재사용** — 원격 health 체크 + 창 토글 |
| 신규 | `client_app.py`(pywebview), 서버 셋업 스크립트 |

> 핵심: **애플리케이션 로직 무수정.** 작업은 "배치·기동·창 래퍼" 인프라 계층뿐.

---

## 11. 리스크 · 대응

| 리스크 | 영향 | 대응 |
|--------|------|------|
| GPU PC 꺼짐 | 생성 불가 | 연결 체크 + WoL, "GPU PC 켜세요" 안내 |
| IP 변동(DHCP) | 주소 깨짐 | 고정 IP 또는 Tailscale 100.x 고정 |
| WebView2 미설치 | 창 안 뜸 | 부트스트랩 동봉/안내 |
| ACE-Step lazy 첫 지연 | 첫 생성 느림 | 기동 시 `/v1/init` 웜업 |
| 무인증 8080 외부 노출 | 무단 사용 | 포트포워딩 금지, Tailscale만, 필요 시 API_KEY+프론트 패치 |
| VRAM 경쟁(ACE+Demucs+Ollama) | OOM | 단일 워커 직렬 유지. **Ollama 고정이라 외부 API 회피 불가** → VRAM 24GB 권장. 부족 시 더 작은 Ollama 모델(예: llama3.2:1b)로 교체 |
| NSSM 서비스 다운 | backend 중단 | NSSM 자동 재시작 + `/health` 모니터 |
```
