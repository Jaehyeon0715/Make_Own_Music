# AI Composer 패키지 배포 기획서 v1.3 (클라우드)

> 대상 제품: **AI Composer v2.8** (ACE-Step 기반 멀티트랙 AI 작곡 + Demucs 스템 분리)
> 배포 형태: **클라우드 GPU 호스팅 + 브라우저 접속 (PC·모바일 무관)**
> 작성일: 2026-06-01 (v1.3 — 로컬판과 쌍을 이루는 클라우드 구동 기획. 로컬판: `AI_Composer_배포_기획서_v1.3.md`)
> 핵심 전제: 트랙 생성/분리 연산을 **사용자 PC가 아닌 클라우드 GPU**에서 수행한다.

---

## 0. 로컬판 대비 핵심 차이 (요약)

| 항목 | 로컬판 | **클라우드판** |
|------|--------|---------------|
| 배포 형태 | Windows 원클릭 `.exe` 설치 | 컨테이너 이미지 + 클라우드 GPU 인스턴스 |
| 연산 위치 | 사용자 PC GPU | **클라우드 GPU** (RunPod/Vast/Lambda 등) |
| 클라이언트 | 동일 PC 브라우저 (localhost) | **어떤 기기든 브라우저** (PC/폰/태블릿) |
| 접속 | `http://localhost:8080` | `https://<도메인>` (HTTPS 필수) |
| 인증 | 로컬 단일 사용자(무인증 허용) | **인증 필수** (`API_KEY`/로그인) |
| 비용 | 1회 설치, 추가비용 0 | **GPU 시간당/요청당 과금** |
| 항상 켜짐 | 사용자가 트레이 실행 시 | 상시(B) 또는 요청시(C) |
| 보안 표면 | 127.0.0.1 바인딩(LAN 차단) | 공개 인터넷 노출 → 보안 설계 필수 |

> **코드 호환성 근거:** 트랙 생성은 전부 `ACESTEP_URL` 환경변수가 가리키는 HTTP 엔드포인트 호출이다(`backend/ace_client.py:12`).
> `DB_PATH`·`OUTPUTS_DIR`·`CORS_ORIGINS`·`API_KEY`·`AI_PROVIDER`도 모두 env 오버라이드 지원(`backend/config.py`).
> → **애플리케이션 코드 수정 없이 env·배치만으로 클라우드 전환 가능.** 본 기획의 작업 대부분은 인프라·보안·운영 영역.

---

## 1. 개요 및 목적

AI Composer를 **클라우드 GPU에서 구동**하고 사용자는 **브라우저 URL 접속만으로** 트랙 생성·편집을
이용하도록 한다. 무거운 연산(ACE-Step 음악 생성, Demucs 스템 분리, 선택적 Ollama)은 클라우드 GPU가
수행하고, 사용자 기기(PC·모바일)는 **얇은 클라이언트(브라우저)** 역할만 한다.

### 목표 (Goals)
- 사용자 PC에 GPU·모델·Python 설치 **불필요** — URL 접속만
- **모바일/태블릿에서도 동작** (반응형 + 동일 백엔드)
- 연산은 클라우드 GPU에서 — 저사양 기기에서도 풀 기능
- 컨테이너화로 **재현 가능한 배포** (개발=운영 환경 일치)

### 비목표 (Non-Goals)
- 멀티테넌트 SaaS 정식 상용화(과금·결제·요금제) — 1차는 **단일/소수 사용자 사설 호스팅**
- 자동 수평 확장(오토스케일 클러스터) — 1차는 단일 GPU 인스턴스
- 모바일 네이티브 앱(스토어 배포) — 1차는 **PWA(브라우저)** 로 충분

---

## 2. 배포 구성요소 분류 (배치 위치 기준)

로컬판은 "동봉/다운로드/외부설치"로 나눴다. 클라우드판은 **어디에 배치하는가**로 나눈다.

| 구성요소 | GPU | 배치 위치 | 비고 |
|----------|-----|----------|------|
| 프론트엔드(`index.html`) | — | 클라우드(백엔드가 정적 서빙) 또는 CDN | 어디서나 브라우저 로드 |
| FastAPI 백엔드(`backend/`) | 불필요 | 클라우드 컨테이너 | CPU 인스턴스로 충분 |
| ACE-Step 엔진+모델 | **필요(무거움)** | **클라우드 GPU** | `uv run acestep-api`, `:8001` |
| Demucs 스템 분리 | **필요(중간)** | **클라우드 GPU** | torch 서브프로세스 |
| Ollama + llama3.2 | 필요 | 클라우드 GPU **또는** 외부 API로 대체 | Claude/OpenAI 쓰면 GPU 불요 |
| Reverse proxy (Caddy/nginx) | — | 클라우드 (HTTPS·인증 게이트) | **신규 필수 구성** |
| 세션 DB(SQLite) + outputs | — | 클라우드 영속 볼륨 | 인스턴스 재생성에도 보존 |

> **AI Provider 선택이 GPU 비용을 좌우:** `AI_PROVIDER=claude/openai/gemini`로 두면 기획 단계는 외부 API가 처리 →
> 클라우드 GPU는 ACE-Step+Demucs만 담당. `AI_PROVIDER=ollama`면 Ollama도 GPU/VRAM 공유.

---

## 3. 사용자 경험 (UX 흐름)

```
사용자 기기(PC/폰/태블릿) 브라우저
   │
   ├─ https://<도메인 또는 IP>  접속
   ├─ (인증) API 키 입력 또는 로그인  ← 무인증 공개 금지
   │
   ▼
Page 1 (기획 입력) → [생성 시작]
   │  요청은 HTTPS로 클라우드 백엔드에 전달
   ▼
클라우드 GPU에서 ACE-Step 생성 / Demucs 분리 (SSE 진행률 스트리밍)
   │
   ▼
Page 2 (DAW 편집) — 볼륨/재생성/Repaint/믹스, 결과 오디오 스트리밍 재생
```

- **상시형(B/모델):** 항상 켜진 URL → 즉시 접속. PC 꺼도 됨.
- **요청형(C/서버리스):** 첫 생성 시 GPU 웜업(cold start 수십초~수분) 후 진행. 미사용 시 과금 0.
- **모바일:** 현 `index.html` DAW UI는 데스크톱 가정 → **반응형 점검 + 터치 대응**이 별도 과제(§6-6).

---

## 4. 기술 스택

| 영역 | 선택 | 사유 |
|------|------|------|
| 컨테이너 | **Docker** (백엔드 이미지 / GPU 이미지) | 재현성, 클라우드 GPU 표준 |
| GPU 클라우드 | **RunPod / Vast.ai / Lambda Labs** (상시) · **RunPod Serverless / Modal / Replicate** (요청형) | NVIDIA GPU 시간/요청 과금, ACE-Step VRAM 충족 |
| 베이스 이미지 | `nvidia/cuda:12.4-runtime` + Python 3.11 | torch CUDA 휠 호환 |
| Reverse proxy | **Caddy** (자동 HTTPS, Let's Encrypt) | 인증서 자동, 설정 간결, 인증 게이트 |
| 인증 | `API_KEY`(`X-API-Key`) + proxy Basic/토큰, (선택) OAuth | 공개 노출 방어 |
| 영속 스토리지 | 클라우드 볼륨 / 오브젝트 스토리지 | sessions.db·outputs 보존 |
| 비밀 관리 | 환경변수 시크릿(클라우드 시크릿 매니저) | API 키·토큰 노출 방지 |
| IaC(선택) | Docker Compose → 추후 Terraform | 1차는 Compose로 충분 |

> **세 가지 구동 모델(§12에서 택1):**
> - **모델 A — ACE-Step만 클라우드:** 백엔드는 로컬/소형 VM, `ACESTEP_URL`만 클라우드 GPU. 최소 변경.
> - **모델 B — 전체 스택 클라우드 1박스:** 상시 GPU VM에 ACE-Step+Demucs+백엔드+proxy. 외부 접속 깔끔.
> - **모델 C — 서버리스 GPU:** 생성 요청 시에만 GPU 웜업. 간헐 사용 최저비용, cold start 지연.

---

## 5. 배포 구조 (컨테이너/볼륨)

### 5-1. 모델 B (전체 스택 1박스) 기준 구조

```
[클라우드 GPU 인스턴스]
├─ docker-compose.yml
├─ caddy/                      # reverse proxy (HTTPS·인증 게이트)
│   └─ Caddyfile               # <도메인> → backend:8080, 인증
├─ backend (컨테이너, CPU 가능)
│   ├─ backend/  frontend/     # 현 MOM 코드 그대로
│   └─ env: ACESTEP_URL=http://acestep:8001
│           DB_PATH=/data/sessions.db
│           OUTPUTS_DIR=/data/outputs
│           CORS_ORIGINS=https://<도메인>
│           API_KEY=<강한 비밀>
│           AI_PROVIDER=claude|ollama
├─ acestep (컨테이너, GPU)
│   └─ uv run acestep-api  →  :8001  (내부 네트워크 전용, 외부 비공개)
├─ demucs                      # 백엔드 컨테이너 내 서브프로세스(GPU 공유) 또는 별도 GPU 워커
└─ volumes:
    └─ /data                   # sessions.db, outputs/, logs/  (영속)
```

### 5-2. 모델 A (ACE-Step만 클라우드) 기준

```
[로컬/소형 VM]  backend + frontend  (CPU)
        │  ACESTEP_URL=https://<클라우드 GPU>:443 (proxy 경유)
        ▼
[클라우드 GPU]  Caddy(HTTPS+토큰) → ACE-Step :8001 (localhost 전용)
```

> **포트:** 외부 공개는 **443(HTTPS)** 만. 백엔드 8080·ACE-Step 8001·Ollama 11434는 **컨테이너 내부 네트워크 전용**(외부 바인딩 금지).
> **영속성:** `DB_PATH`/`OUTPUTS_DIR`을 `/data` 볼륨으로 → 인스턴스 재생성·재배포에도 세션 보존(서버리스 C는 외부 스토리지 필수, §6-8).

---

## 6. 핵심 난점 (클라우드 전환 요점)

### 6-1. GPU 인스턴스 선정 · VRAM
- ACE-Step + Demucs(+선택 Ollama) **VRAM 공유** → 동시 OOM 주의. 큐 단일 워커로 직렬화는 유지되나 ACE-Step 상주 점유 고려.
- 권장: **16GB+ VRAM**(예: RTX 4090/A5000/L4). Ollama까지면 24GB 권장. ACE-Step turbo 단독은 8~12GB도 가능하나 여유 확보 권장.

### 6-2. 보안 — 공개 인터넷 노출 (최우선)
- **HTTPS 강제:** Caddy 자동 인증서. 평문 HTTP 금지.
- **인증 필수:** `backend/config.py`의 `require_api_key`는 `API_KEY` 미설정/플레이스홀더 시 **인증을 통과시킨다**(`config.py:59`, 로컬 전제). 클라우드에선 반드시 **강한 `API_KEY` 설정** + proxy 레벨 인증(토큰/Basic) 이중화.
- **내부 서비스 비공개:** ACE-Step 8001·Ollama 11434는 외부 바인딩 금지, proxy만 외부 노출.
- **CORS 정합:** `CORS_ORIGINS=https://<도메인>`으로 명시(와일드카드 금지, `allow_credentials=True`와 `*` 동시 사용 불가).
- **레이트 리밋:** proxy에서 IP/키별 요청 제한 → 비용·남용 방어.

### 6-3. ACE-Step (+ uv 런너) 컨테이너화
- 이미지에 `uv` 포함 → `uv run acestep-api`로 기동(로컬판 `launcher/services.py`의 기동 방식을 컨테이너 CMD로 이식).
- 모델 가중치는 **이미지에 굽거나(빌드 크게)** 또는 **첫 기동 시 영속 볼륨에 캐시**(이미지 슬림, 웜업 1회).
- `ACESTEP_URL`은 백엔드 입장에서 내부 DNS(`http://acestep:8001`) 또는 모델 A면 proxy URL.

### 6-4. AI Provider — GPU 절감 선택
- `AI_PROVIDER=claude|openai|gemini` → 기획 단계 외부 API 위임, **Ollama GPU 불요**(비용↓).
- `AI_PROVIDER=ollama` → Ollama도 컨테이너+GPU. VRAM·비용↑. 폐쇄망/무과금 선호 시.
- API 키는 시크릿으로 주입(이미지·리포에 하드코딩 금지).

### 6-5. 비용 모델 · 자동 정지
- **상시(B):** GPU 시간당 과금 → 미사용 시간 비쌈. **유휴 자동 정지/스케줄 기동** 권장.
- **서버리스(C):** 요청당 과금, 미사용 0원. cold start(모델 로드) 지연 → UX에 "웜업 중" 표시.
- 출력 오디오 스토리지·이그레스 트래픽도 과금 항목 → outputs TTL 정리(현 세션 TTL 24h 활용).

### 6-6. 모바일 클라이언트 대응
- 현 `frontend/index.html` DAW UI는 데스크톱 폭 가정 → **반응형 레이아웃·터치 타깃·뷰포트 메타** 점검 필요.
- (선택) **PWA**: manifest + service worker → "홈 화면 추가", 오프라인 셸. 백엔드는 여전히 클라우드.
- SSE는 모바일 브라우저에서도 동작하나 백그라운드 전환 시 연결 끊김 → 재연결/세션 복원(`/session/{id}`) 활용.

### 6-7. 다운로드 무결성 · 공급망 (이미지 빌드)
- 베이스 이미지·torch 휠·ACE-Step/Demucs 가중치는 **고정 태그/해시(pin)** 로 빌드 재현성 확보.
- 이미지 레지스트리는 신뢰 소스, 가능하면 다이제스트(`@sha256:`) 고정. 시크릿은 빌드 ARG 아닌 런타임 env.

### 6-8. 상태/세션 영속성 (재생성 대비)
- 인스턴스/컨테이너는 **언제든 재생성** 전제 → `DB_PATH`·`OUTPUTS_DIR`을 **영속 볼륨** 또는 **오브젝트 스토리지**로.
- 서버리스(C)는 로컬 디스크 휘발 → DB는 외부(관리형 SQLite 대안/Postgres 또는 마운트 스토리지), outputs는 S3 호환 버킷.
- SQLite WAL은 단일 라이터 전제 → 단일 백엔드 인스턴스 유지(수평 확장 시 DB 재설계 필요, 비목표).

### 6-9. 네트워크 · 포트 · 바인딩
- 백엔드 uvicorn은 컨테이너 내부에서 `--host 0.0.0.0`(컨테이너 네트워크 한정) + **proxy만 외부**. 호스트 직접 노출 금지.
- 외부 공개 포트는 443 단일. 방화벽/보안그룹은 443(+SSH 관리)만 인바운드 허용.
- 타임아웃: ACE-Step CPU 폴백은 매우 길다(`ACESTEP_CLIENT_TIMEOUT` 기본 1800s, `ace_client.py:14`) → proxy 타임아웃도 충분히 크게(기본 60s면 SSE/장시간 생성 끊김).

---

## 7. 빌드 · 배포 파이프라인 (개발자용)

```
deploy/ 디렉터리에 배포 자산 추가
├─ 1. Dockerfile.backend       # 임베디드 아님 — 표준 python:3.11-slim + requirements
├─ 2. Dockerfile.acestep       # nvidia/cuda + uv + ACE-Step + 모델 캐시
├─ 3. docker-compose.yml       # backend + acestep + caddy + volume(/data)
├─ 4. Caddyfile                # <도메인> 자동 HTTPS + 인증 + SSE 타임아웃
├─ 5. .env.cloud.template      # ACESTEP_URL, DB_PATH, OUTPUTS_DIR, CORS_ORIGINS, API_KEY, AI_PROVIDER
└─ 6. deploy.ps1 / deploy.sh   # 이미지 빌드·푸시·인스턴스 기동 오케스트레이션
```

- **모델 A:** `Dockerfile.acestep` + Caddy만 클라우드, 백엔드는 로컬 실행(`ACESTEP_URL`만 원격).
- **모델 B:** `docker-compose.yml` 한 번에 전체 기동.
- **모델 C:** ACE-Step를 서버리스 핸들러로 래핑(RunPod Serverless/Modal) → 별도 `handler.py` + 백엔드의 `ACESTEP_URL`을 서버리스 엔드포인트로.

산출물: 레지스트리에 푸시된 이미지 + `docker-compose.yml`(또는 서버리스 엔드포인트 ID).

---

## 8. 운영 · 업데이트 · 모니터링

- **업데이트:** 새 이미지 태그 빌드·푸시 → `docker compose pull && up -d`. DB·outputs 볼륨 보존.
- **롤백:** 이전 이미지 태그로 재배포. 볼륨 호환 유지.
- **모니터링:** `/health`(서버+ACE-Step 상태, `main.py`) 헬스체크 + GPU 사용률/비용 알람.
- **로그:** 컨테이너 stdout → 클라우드 로그. `logs/`도 볼륨 보존.
- **백업:** sessions.db·outputs 정기 스냅샷(특히 서버리스).
- **유휴 절감:** 상시(B)는 스케줄/유휴 정지, 서버리스(C)는 자동.

---

## 9. 시스템 요구사항 (클라우드 인스턴스)

| 항목 | 최소 | 권장 |
|------|------|------|
| GPU | NVIDIA 8GB(ACE-Step turbo 단독) | **16GB+ (4090/A5000/L4)**, Ollama 포함 시 24GB |
| vCPU | 4 | 8+ |
| RAM | 16 GB | 32 GB |
| 디스크/볼륨 | 30 GB | 50 GB+ (모델·outputs) |
| 네트워크 | 공인 IP/도메인 + HTTPS | + CDN(프론트) |
| 클라이언트 | 모던 브라우저(PC/모바일) | — (설치 불요) |

> 사용자 기기 요구사항 **없음**(브라우저만). 연산은 전부 클라우드.

---

## 10. 리스크 및 대응

| 리스크 | 영향 | 대응 |
|--------|------|------|
| **무인증/공개 노출** | API 무단 사용·비용 폭탄·데이터 유출 | `API_KEY` 필수 + proxy 인증 이중화, 내부 서비스 비공개(§6-2) |
| **GPU 비용 폭증** | 상시 GPU 과금 누적 | 유휴 자동 정지/서버리스(C), 레이트 리밋, 예산 알람(§6-5) |
| 평문 HTTP/인증서 누락 | 도청·MITM | Caddy 자동 HTTPS 강제, HTTP 리다이렉트(§6-2) |
| SSE/장시간 생성 proxy 타임아웃 | 생성 중 연결 끊김 | proxy 타임아웃 ↑(ACE-Step 1800s 대응), 세션 복원으로 결과 회수(§6-9) |
| cold start 지연(서버리스) | 첫 생성 수십초~분 | "웜업 중" UX, 최소 1 웜 인스턴스 옵션(§6-5) |
| 인스턴스 재생성 시 데이터 소실 | 세션/출력 유실 | 영속 볼륨/오브젝트 스토리지, 정기 백업(§6-8) |
| VRAM 동시 점유 OOM | 생성 실패 | 단일 워커 직렬화 유지, VRAM 여유 GPU 선정, Ollama 외부 API로 대체(§6-1·6-4) |
| 모바일 UI 미대응 | 폰 사용성 저하 | 반응형/PWA 과제 분리(§6-6) |
| SQLite 단일 라이터 | 수평 확장 불가 | 1차 단일 백엔드 유지, 확장은 DB 재설계(비목표)(§6-8) |
| 이미지/모델 변조 | 악성·손상 실행 | 베이스/휠/가중치 pin·다이제스트 고정, 시크릿 런타임 주입(§6-7) |
| API 키 유출(리포/이미지) | 외부 API 남용 과금 | 시크릿 매니저, env 주입, 키 로테이션(§6-4) |

---

## 11. 개발 단계 (Phase)

| Phase | 작업 | 산출물 | 예상 |
|-------|------|--------|------|
| **C0** | 구동 모델 확정(A/B/C) + 클라우드/GPU 벤더 선정, `.env.cloud.template` 정비(`ACESTEP_URL`·`API_KEY`·`CORS_ORIGINS`·`DB_PATH`·`OUTPUTS_DIR`·`AI_PROVIDER`) | 결정문서, env 템플릿 | 0.5일 |
| **C1** | 백엔드 컨테이너화(`Dockerfile.backend`) + 로컬 compose 검증 | 백엔드 이미지 | 1일 |
| **C2** | ACE-Step GPU 컨테이너(`Dockerfile.acestep`, uv 기동, 모델 캐시) | GPU 이미지 | 2일 |
| **C3** | Reverse proxy(Caddy) — HTTPS·인증·SSE 타임아웃·레이트리밋 | `Caddyfile` | 1일 |
| **C4** | 영속 스토리지(볼륨/오브젝트) + 백업 + 헬스체크/모니터링 | compose volume·백업 스크립트 | 1일 |
| **C5** | 보안 하드닝 — 내부 서비스 비공개, `API_KEY` 강제, CORS 정합, 시크릿 주입 | 보안 점검 리포트 | 1일 |
| **C6** | (선택) 모바일 반응형/PWA — 뷰포트·터치·manifest·SW | `index.html` 패치, `manifest.json` | 2일 |
| **C7** | (모델 C 선택 시) ACE-Step 서버리스 핸들러 래핑 + 외부 스토리지 | `handler.py` | 2일 |
| **C8** | 클라우드 E2E 테스트(생성·분리·믹스·세션복원) + 비용/부하 점검 | 테스트 리포트 | 1일 |

**총 예상:** 모델 B 기준 약 **7.5일** (C6 모바일 +2, C7 서버리스 +2 선택).

> **선행 의존:** 로컬판 P0의 env 일반화(경로/포트/CORS)와 겹침 — `config.py`는 이미 핵심 env 오버라이드 지원이라 추가 코드 변경은 최소.

---

## 12. 의사결정 사항 (확정 필요 ⚠)

| # | 결정 항목 | 옵션 | 권장 / 비고 |
|---|----------|------|------------|
| 1 | **구동 모델** | A(ACE-Step만)·B(전체 1박스)·C(서버리스) | 자주·빠른 응답 → **B**, 간헐 사용·비용 최소 → **C**, 최소 변경 시작 → **A** |
| 2 | **GPU 벤더** | RunPod / Vast.ai / Lambda / Modal / Replicate | 가성비·서버리스 → RunPod, 저가 상시 → Vast.ai. ⚠ 가격·VRAM 실측 후 확정 |
| 3 | **AI Provider** | Claude/OpenAI/Gemini(API) vs Ollama(GPU) | GPU 비용↓ → 외부 API. 폐쇄·무과금 → Ollama. ⚠ API 키 비용 vs GPU 비용 비교 |
| 4 | **인증 방식** | `API_KEY` 단독 / proxy Basic / OAuth | 소수 사용자 → `API_KEY`+proxy 토큰. 다수 → OAuth. **무인증 금지** |
| 5 | **스토리지** | 인스턴스 볼륨 / S3 호환 오브젝트 | 모델 B → 볼륨, 모델 C → 오브젝트 필수 |
| 6 | **모바일 범위** | 반응형만 / PWA / (보류) | 1차 반응형, 2차 PWA. 네이티브 앱은 비목표 |
| 7 | **도메인/인증서** | 자체 도메인 + Let's Encrypt / IP only | 도메인 권장(인증서·CORS·북마크). IP만이면 자체서명 경고 |

> ⚠ 표시 항목은 **배포 전 실측·확정** 필요(가격·VRAM·API 비용).

---

## 13. 아키텍처 · 시퀀스 다이어그램

### 13-1. 런타임 컴포넌트 구성도 (모델 B — 전체 스택 1박스)

```
┌──────── 사용자 기기 (PC/폰/태블릿) ────────┐
│   [브라우저]  https://<도메인>             │
└───────────────────┬───────────────────────┘
                    │  HTTPS / SSE (인증 헤더)
                    ▼
┌──────────────── 클라우드 GPU 인스턴스 ─────────────────────────┐
│   ┌──────────────┐  443                                        │
│   │ Caddy (proxy)│  HTTPS·인증·레이트리밋·SSE 타임아웃            │
│   └──────┬───────┘                                             │
│          │ 8080(내부)                                           │
│          ▼                                                     │
│   ┌─────────────────┐   enqueue   ┌──────────────────────────┐ │
│   │ FastAPI :8080    │────────────►│ PriorityQueue (단일 워커)  │ │
│   │ (backend, CPU)   │             │  HEAVY=0 / LIGHT=1        │ │
│   └───────┬─────────┘             └──────┬──────────┬────────┘ │
│           │ plan                          │ 생성/분리  │ 믹스     │
│           ▼                               ▼          ▼         │
│   ┌──────────────┐         ┌──────────────────┐ ┌───────────┐  │
│   │ Ollama :11434 │        │ ACE-Step :8001   │ │ Demucs    │  │
│   │ (또는 외부 API)│        │ (내부 전용)       │ │ (GPU)     │  │
│   └──────────────┘         └──────────────────┘ └───────────┘  │
│           └──────────── GPU(VRAM 공유) ──────────────┘          │
│                                                                │
│   영속 볼륨 /data : sessions.db, outputs/, logs/                │
└────────────────────────────────────────────────────────────────┘
   ※ 8080·8001·11434 외부 비공개 — 443(Caddy)만 노출
```

### 13-2. 모델 A — ACE-Step만 클라우드

```
[로컬/소형 VM]                         [클라우드 GPU]
 브라우저 → FastAPI :8080  ──HTTPS──►  Caddy(443, 토큰) ─► ACE-Step :8001
            ACESTEP_URL=                                   (localhost 전용)
            https://<클라우드>
```

### 13-3. 생성 요청 시퀀스 (클라우드, SSE)

```
브라우저   Caddy     FastAPI    Queue(HEAVY)   ACE-Step(GPU)   DB/볼륨
 │ POST /generate/all (인증)              │            │         │
 ├────────►│──────────►│ enqueue          │            │         │
 │  SSE◄───┤◄──────────┤───────────────────►│ 생성       │         │
 │ progress│           │◄─ track_N.wav ─────┤            │         │
 │ (n%)    │           ├─ 저장 ─────────────────────────────────►│
 │ done◄───┤◄──────────┤ status=done                     │         │
   ※ Caddy SSE 타임아웃 ≥ ACESTEP_CLIENT_TIMEOUT(1800s) 보장
```

### 13-4. 서버리스(모델 C) 생성 시퀀스

```
FastAPI ──HTTP──► [서버리스 GPU 엔드포인트]
                    ├─ cold start: 모델 로드(웜업, 수십초~분)  ← "웜업 중" 표시
                    ├─ ACE-Step 생성
                    └─ 결과 WAV → 오브젝트 스토리지/응답
FastAPI ◄── 결과 URL/바이트 ── 저장(외부 스토리지) ── 미사용 시 GPU 0원
```

---

## 14. 테스트 · QA 계획

배포 신뢰성의 핵심은 **클라우드 환경·공개 네트워크·인증 경로**의 검증이다.

### 14-1. 테스트 환경 매트릭스

| # | 환경 | 검증 목적 |
|---|------|----------|
| E1 | 클라우드 GPU(B) | 전체 스택 기동, 생성·분리·믹스 |
| E2 | 모델 A(로컬 백엔드 + 클라우드 ACE-Step) | `ACESTEP_URL` 원격 경로 |
| E3 | 서버리스(C) | cold start, 외부 스토리지 결과 회수 |
| E4 | 모바일 브라우저(iOS/Android) | 반응형·터치·SSE·세션 복원 |
| E5 | 인증/보안 | 무인증 차단, HTTPS, CORS, 레이트리밋 |
| E6 | 장애/재생성 | 인스턴스 재생성 후 세션·outputs 보존 |

### 14-2. 검증 체크리스트

- [ ] HTTPS 접속·인증서 유효, HTTP→HTTPS 리다이렉트
- [ ] `API_KEY` 없이 요청 시 **401 차단** (무인증 노출 방지)
- [ ] 내부 포트(8080/8001/11434) 외부에서 **접근 불가** 확인
- [ ] CORS: 허용 오리진만 통과, 와일드카드 없음
- [ ] 장시간 생성 SSE가 proxy 타임아웃에 끊기지 않음
- [ ] 인스턴스 재생성/재배포 후 sessions.db·outputs 보존
- [ ] 서버리스 cold start 후 생성 성공·결과 저장
- [ ] 모바일에서 UI 로드·기획·생성·재생 동작
- [ ] GPU 비용/유휴 정지·예산 알람 동작
- [ ] 시크릿이 이미지/리포에 평문 노출 안 됨

### 14-3. 스모크 테스트 (기능 최소 검증)

1. 인증 후 기획(`/plan`) → 트랙 목록
2. 전체 생성(`/generate/all`) → 트랙별 WAV·파형
3. 스템 분리(`/generate/separated`) → drums/bass/other
4. 단일 재생성 / Repaint / 볼륨
5. 믹스 → mp3 다운로드(스트리밍)
6. 다른 기기/브라우저로 재접속 → 세션 복원(`/session/{id}`)

### 14-4. 자동화 범위

- 백엔드 로직: 기존 **pytest 7 시나리오** CI 유지(ACE-Step 모킹).
- 배포: compose 기동 → PowerShell/bash 스모크가 `/health`·인증·생성 자동 호출.
- 수동: 모바일 사용성, cold start 체감, 비용 모니터링.

### 14-5. 릴리스 게이트

E1·E5 **필수 통과**, 14-2/14-3 체크리스트 **전 항목 green**, pytest **7/7** 유지 시 승인.
E3·E4·E6은 선택 모델에 따라 조건부.

---

## 15. 서드파티 라이선스 고지

라이선스 의무는 로컬판과 동일(MIT/BSD/LGPL). 클라우드(SaaS) 제공 시 추가 고려:

| 구성요소 | 라이선스 | 클라우드 고려 |
|----------|---------|--------------|
| ACE-Step | MIT | 호스팅 시 전문 포함 의무 유지(About/`licenses\`) |
| Demucs | MIT | 동일 |
| PyTorch | BSD-3 | 동일 |
| soundfile / libsndfile | BSD-3 / LGPL | 컨테이너 내 동적 링크 유지 |
| FFmpeg | LGPL/GPL | LGPL 빌드 사용(GPL 코덱 제외) |
| Ollama | MIT | 사용 시 고지 |
| AI Composer(본 제품) | MIT — Copyright (c) 2026 Jaehyeon Heo | App 정보/`LICENSE.txt` |

> **SaaS 주의:** MIT/BSD는 네트워크 제공만으로 소스 공개 의무 없음(AGPL 아님). 단 **고지 의무는 유지**.
> 외부 AI API(Claude/OpenAI/Gemini) 사용 시 각 **서비스 약관·데이터 정책** 준수(사용자 입력 전송 고지 권장).
> ⚠ 저작권 표기명 `Jaehyeon Heo` 정식 표기 확인 필요(로컬판과 공통 TODO).

---

## 16. 용어 정리

| 용어 | 설명 |
|------|------|
| **컨테이너 / Docker** | 앱+의존성을 격리 패키징해 어디서나 동일 실행. 클라우드 GPU 배포 표준 |
| **리버스 프록시 (Caddy/nginx)** | 외부 요청을 받아 내부 서비스로 중계. HTTPS·인증·레이트리밋 담당 |
| **cold start(웜업)** | 서버리스에서 미사용 후 첫 요청 시 모델 로드로 생기는 초기 지연 |
| **서버리스 GPU** | 요청 시에만 GPU를 깨워 과금, 미사용 0원. 간헐 사용에 유리 |
| **영속 볼륨 / 오브젝트 스토리지** | 컨테이너 재생성에도 데이터(DB·outputs) 보존하는 외부 저장소 |
| **이그레스(egress)** | 클라우드에서 외부로 나가는 트래픽. 오디오 다운로드 과금 항목 |
| **PWA** | 브라우저 앱을 "홈 화면 추가"로 네이티브처럼 쓰는 웹 기술(설치 불요) |
| **SSE (Server-Sent Events)** | 서버→브라우저 단방향 실시간 스트림. 생성 진행률 전송에 사용 |
| **스템 (stem)** | 믹스에서 분리된 개별 악기 트랙. Demucs가 사후 분리 |

---

## 부록 A. 버전 이력

| 버전 | 변경 |
|------|------|
| v1.3 (클라우드) | 로컬판 v1.3과 쌍을 이루는 클라우드 구동 기획 최초 작성. 3가지 구동 모델(A 부분/B 전체/C 서버리스), 컨테이너·proxy·보안·비용·모바일·영속성 설계. 애플리케이션 코드는 `ACESTEP_URL`·`config.py` env 오버라이드로 무수정 전환 가능함을 근거화 |

---

## 부록 B. 로컬↔클라우드 전환 체크 (env 매핑)

코드 수정 없이 아래 env만 바꾸면 동일 코드가 로컬/클라우드 양쪽 구동:

| env | 로컬판 값(예) | 클라우드판 값(예) | 출처 |
|-----|--------------|------------------|------|
| `ACESTEP_URL` | `http://localhost:8001` | `http://acestep:8001` 또는 `https://<클라우드>` | `ace_client.py:12` |
| `ACESTEP_CLIENT_TIMEOUT` | `1800` | `1800` (proxy 타임아웃도 일치) | `ace_client.py:14` |
| `DB_PATH` | 프로젝트/`%LOCALAPPDATA%` | `/data/sessions.db`(영속 볼륨) | `config.py:39` |
| `OUTPUTS_DIR` | 프로젝트/`%LOCALAPPDATA%` | `/data/outputs`(볼륨/오브젝트) | `config.py:40` |
| `CORS_ORIGINS` | `http://localhost:8080` | `https://<도메인>` | `config.py:23` |
| `API_KEY` | (미설정 허용) | **강한 비밀 필수** | `config.py:38,58` |
| `AI_PROVIDER` | `ollama` | `claude`/`ollama` | `config.py:37` |
| 바인딩 | `--host 127.0.0.1` | 컨테이너 내부 + proxy만 외부 | §6-9 |
