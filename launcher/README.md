# AI Composer 트레이 런처

원클릭 백그라운드 실행. 트레이 아이콘으로 제어.

## 동작

1. ACE-Step + Ollama + FastAPI를 **숨겨진 프로세스**로 실행
2. ACE-Step 모델 자동 초기화 (`POST /v1/init` + 폴링)
3. 준비 완료 시 브라우저 자동 오픈
4. 트레이 아이콘에서 상태 확인 + 제어
5. 로그는 `MOM/logs/{acestep,ollama,fastapi}.log`

## 트레이 메뉴

- **● 상태** — 현재 진행 상황 (회색 / 주황 / 초록 / 빨강)
- **브라우저 열기** — `http://localhost:8080`
- **로그 폴더 열기** — `MOM/logs/`
- **재시작** — 모든 서비스 종료 후 재시작
- **종료** — 모든 서비스 종료 + 트레이 제거

## 개발 모드 실행

```cmd
cd MOM\launcher
dev_run.bat
```

## .exe 빌드

```cmd
cd MOM\launcher
build.bat
```

결과물: `MOM\dist\AIComposer.exe`
→ `MOM\` 루트로 이동 후 더블클릭

## 사전 요구사항

| 항목 | 설치 위치 |
|------|----------|
| ACE-Step | `C:\Users\heo01\ace-step` (또는 `ACE_STEP_DIR` 환경변수) |
| uv | `C:\Users\heo01\.local\bin\uv.exe` (또는 `UV_PATH` 환경변수) |
| Ollama | PATH에 `ollama` 명령어 사용 가능 |
| Python 백엔드 deps | `pip install -r backend/requirements.txt` 완료 |

## 환경변수 (선택)

| 변수 | 기본값 |
|------|-------|
| `ACE_STEP_DIR` | `C:\Users\heo01\ace-step` |
| `UV_PATH` | `C:\Users\heo01\.local\bin\uv.exe` |
| `OLLAMA_EXE` | `ollama` |
| `FASTAPI_PORT` | `8080` |
