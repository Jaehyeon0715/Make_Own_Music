# GPU PC 셋업 (B형 · 풀스택 backend)

내 PC `.exe`(씬 클라이언트)가 붙을 **GPU PC**를 구성한다.
GPU PC = ACE-Step + FastAPI backend + Demucs + Ollama 전부 구동.

> ⚠️ **ACE-Step 엔진은 이 패키지에 포함되지 않음** — GPU PC에서 공식 배포본을 별도 설치 후
> `-AceStepDir` 로 경로 지정. 없으면 setup이 시작 단계에서 중단된다.
>
> 스크립트 실행이 차단되면(보안 정책): `Set-ExecutionPolicy -Scope Process Bypass` 후 재실행.

## 전제 (스크립트가 설치 안 함 — 미리 준비)
- **NVIDIA 드라이버 + CUDA** (`nvidia-smi` 동작)
- **Python 3.11** (가상환경 권장: `python -m venv venv; .\venv\Scripts\activate`)
- **uv** (ACE-Step 기동) — https://docs.astral.sh/uv
- **ACE-Step 엔진 + 모델** (공식 배포본, 별도 폴더)
- **Ollama** — https://ollama.com
- **ffmpeg** — `winget install Gyan.FFmpeg` (mp3 export 필수)
- MOM 프로젝트 코드 (backend/ 포함)
- **NSSM** (상시 서비스 등록용) — https://nssm.cc

## ⭐ 원스텝 (권장)

설치 → 기동 → 웜업 → 헬스체크 → 접속주소 출력까지 한 번에:

```powershell
.\setup_all.ps1 -MomRoot C:\AIComposer\MOM -AceStepDir C:\AIComposer\ace-step `
  -UvPath C:\Users\me\.local\bin\uv.exe -AutoInstallTools `
  -AceStepScript C:\AIComposer\ace-step\acestep_server.py
```
- `-AutoInstallTools` : ffmpeg/ollama/uv 를 winget으로 자동 설치 시도(nssm은 수동).
- `-AceStepScript <wrapper.py>` : **공식 ACE-Step repo는 `uv run acestep-api` 진입점을 제공하지 않음.**
  OpenRouter 호환 wrapper(`acestep_server.py` 등)를 직접 가리켜야 ACE-Step 서비스가 뜬다.
  지정 안 하면 `uv run acestep-api` 시도 → 자기 fork에 해당 entry가 있을 때만 동작.
- `-FfmpegPath <ffmpeg.exe>` : 생략 시 자동 감지. NSSM 서비스(LocalSystem)는 winget user PATH를 못 보므로
  backend 서비스 env에 `FFMPEG_BINARY` + `PATH` 주입 필요(자동 처리).
- 서비스 등록 단계에서 **UAC 1회**(관리자 권한). 거부 시 자동으로 수동기동으로 대체.
- 끝나면 **내 PC .exe 접속 주소**(`http://<GPU_PC_IP>:8080`)를 출력.
- 서비스 없이 이번만 테스트: `-Mode run` 추가.

> **헬스체크 `ace_step=False`는 정상**(idle/lazy-load). 첫 음악 생성 요청 시 모델 로드 → True 전환.

## 개별 단계 (수동 제어)

```powershell
# 1) 의존성 설치 (backend deps + torch CUDA + demucs + 가중치 + ollama 모델 + .env)
.\install_server.ps1 -MomRoot C:\AIComposer\MOM -CudaTag cu124

# 2) backend\.env 확인 (자동 생성됨)  AI_PROVIDER=ollama 고정, DEMUCS_DEVICE=cuda

# 3) 수동 테스트
.\start_server.ps1 -MomRoot C:\AIComposer\MOM -AceStepDir C:\AIComposer\ace-step -UvPath uv
.\healthcheck.ps1 -Port 8080

# 4) 상시 서비스 등록 (관리자, 부팅 자동기동 + 방화벽 8080)
.\register_services.ps1 -MomRoot C:\AIComposer\MOM -AceStepDir C:\AIComposer\ace-step `
  -UvPath C:\Users\me\.local\bin\uv.exe -OpenFirewall

# 5) 원격(내 PC)에서 점검
.\healthcheck.ps1 -HostName <GPU_PC_LAN_IP> -Port 8080
```

## 파일
| 파일 | 역할 |
|------|------|
| `setup_all.ps1` | **원스텝** — 점검·설치·기동·웜업·헬스체크·접속안내 오케스트레이션 |
| `install_server.ps1` | 의존성·torch CUDA·demucs·가중치·ollama·`.env` 일괄 설치 |
| `.env.template` | `backend\.env` 원본 (Provider=Ollama 고정) |
| `start_server.ps1` | 수동 기동 (ACE-Step + backend 새 창) |
| `register_services.ps1` | NSSM 서비스 등록/제거 + 방화벽 |
| `healthcheck.ps1` | backend/ACE-Step/Ollama 상태 점검 |

## 네트워크 · 보안
- **8080만** LAN 노출(register `-OpenFirewall`). **8001·11434는 localhost 전용** — 개방 금지.
- 외부(집 밖) 접속은 **Tailscale**로 두 PC 연결 → `.exe` 가 `100.x.x.x:8080` 접속. 포트포워딩 금지.
- API_KEY 미설정 유지(LAN 신뢰망). 켜면 프론트 401 — 설계서 §7.

## 고정 IP / Tailscale
- DHCP면 GPU PC IP 변동 → **고정 IP** 또는 Tailscale 사설 IP 권장(`.exe` 주소 안 깨짐).

## 트러블슈팅
| 증상 | 원인 / 해결 |
|------|-----------|
| 분리 시 `Couldn't find appropriate backend` | soundfile 미설치 → `pip install soundfile` |
| mp3 export 실패 | ffmpeg 미설치/PATH 누락 |
| `torch.cuda=False` | CPU torch 설치됨 → torch 재설치 `--index-url .../cu124` (demucs 전에) |
| 첫 생성 매우 느림 | ACE-Step lazy-load → `curl -X POST localhost:8001/v1/init` 웜업 |
| `AIComposer-AceStep` 서비스 즉시 죽음 | `uv run acestep-api` 진입점 없음(공식 repo 미정의) → `-AceStepScript <wrapper.py>` 지정 |
| backend 서비스 mp3 export 실패(`Couldn't find ffmpeg`) | NSSM LocalSystem이 winget user PATH 미인식 → 자동 주입(자동 감지) 또는 `-FfmpegPath <ffmpeg.exe>` 지정 |
| ACE-Step `/health` 가 `status=idle` 만 반환 | 정상 — 첫 `/generate` 요청 시 모델 로드되며 `status=ok` 전환 |
| 원격 8080 접속 불가 | 방화벽 인바운드 / 같은 LAN·tailnet 여부 / 0.0.0.0 바인딩 확인 |
| plan 실패 | `ollama serve` 미기동 / `ollama pull llama3.2` 누락 |
