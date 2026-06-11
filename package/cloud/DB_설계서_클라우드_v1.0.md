# AI Composer v2.8 — DB 설계서 (클라우드) v1.0

> 출처: `MOM_package/cloud/AI_Composer_배포_기획서_v1.3_클라우드.md`
> 코드 대조: `MOM/backend/db.py`, `MOM/backend/config.py`
> 작성일: 2026-06-05
> 엔진: **SQLite (aiosqlite)**, WAL, `foreign_keys=ON`. 스키마는 로컬판과 동일, 영속·스토리지만 변경.

---

## 1. 개요

| 항목 | 값 | 근거 |
|------|-----|------|
| 엔진 | SQLite (aiosqlite) | `db.py:8` |
| 저널 모드 | WAL (**단일 라이터**) | `db.py:16` |
| FK 강제 | `PRAGMA foreign_keys=ON` | `db.py:17` |
| 경로 | `DB_PATH=/data/sessions.db` (영속 볼륨) | 기획 §5·부록B |
| outputs | `OUTPUTS_DIR=/data/outputs` | 기획 §5 |
| TTL | `SESSION_TTL_HOURS=24` | `config.py:42` |
| 믹스 상한 | `MAX_MIX_VERSIONS=10` | `config.py:43` |

> ⚠️ WAL 단일 라이터 → **단일 백엔드 인스턴스 유지**. 수평 확장 시 DB 재설계 필요(비목표, 기획 §6-8).

---

## 2. ERD

```
sessions (PK session_id)
   │ 1
   ├──────────────► tracks (FK session_id)         [N]
   └──────────────► mix_versions (FK session_id)   [N]
```

---

## 3. 테이블 상세

### 3-1. `sessions`
| 컬럼 | 타입 | 제약 | 기본 | 설명 |
|------|------|------|------|------|
| `session_id` | TEXT | **PK** | — | uuid4 hex |
| `created_at` | TEXT | NOT NULL | — | UTC ISO8601 |
| `ai_provider` | TEXT | NOT NULL | — | claude/openai/gemini/ollama |
| `bpm` | INTEGER | — | NULL | 전역 BPM |
| `bpm_auto` | INTEGER | — | 1 | 1=AI자동 0=지정 |
| `key` | TEXT | — | NULL | 전역 Key |
| `key_auto` | INTEGER | — | 1 | 1=AI자동 0=지정 |
| `duration` | INTEGER | NOT NULL | — | 곡 길이(초) 5~600 |
| `status` | TEXT | — | `'pending'` | pending/generating/done/error |

### 3-2. `tracks`
| 컬럼 | 타입 | 제약 | 기본 | 설명 |
|------|------|------|------|------|
| `id` | INTEGER | **PK** AUTOINC | — | 내부 ID |
| `session_id` | TEXT | NOT NULL **FK** | — | 소속 세션 |
| `track_order` | INTEGER | NOT NULL | — | 1부터, 정렬·경로 키 |
| `name` | TEXT | NOT NULL | — | 트랙명 |
| `instrument` | TEXT | NOT NULL | — | 악기 |
| `caption` | TEXT | NOT NULL | — | ACE-Step 캡션 |
| `bpm_override` | INTEGER | — | NULL | locked=0 시 반영 |
| `key_override` | TEXT | — | NULL | locked=0 시 반영 |
| `locked` | INTEGER | — | 1 | 1=전역 0=오버라이드 |
| `volume` | REAL | — | 1.0 | 믹스 볼륨 0~2 |
| `wav_url` | TEXT | — | NULL | WAV 경로(NULL=생성전) |

### 3-3. `mix_versions`
| 컬럼 | 타입 | 제약 | 기본 | 설명 |
|------|------|------|------|------|
| `id` | INTEGER | **PK** AUTOINC | — | 내부 ID |
| `session_id` | TEXT | NOT NULL **FK** | — | 소속 세션 |
| `version` | INTEGER | NOT NULL | — | 1부터(`MAX+1`) |
| `wav_path` | TEXT | NOT NULL | — | 믹스 WAV |
| `mp3_path` | TEXT | — | NULL | 믹스 MP3 |
| `created_at` | TEXT | NOT NULL | — | UTC ISO8601 |

> 상한 초과 시 oldest 행 + 디스크 파일 삭제(`db.py:254-262`).
> ⚠️ FK ON DELETE CASCADE 미선언 → `delete_session()` 명시 삭제(`db.py:124-130`).

---

## 4. 주요 연산

| 연산 | 함수 |
|------|------|
| 세션 | `create_session`, `get_session`, `update_session_status`, `update_*_provider`, `get_expired_sessions`, `delete_session` |
| 트랙 | `create_tracks`, `clear_tracks`, `get_tracks`, `update_track_wav/volume/lock` |
| 믹스 | `save_mix_version`, `get_mix_versions`, `get_latest_mix` |

---

## 5. 인덱스 권고 (현재 미선언)

| 인덱스 | 대상 |
|--------|------|
| `idx_tracks_session` | `tracks(session_id, track_order)` |
| `idx_mix_session` | `mix_versions(session_id, version)` |
| `idx_sessions_created` | `sessions(created_at)` |

---

## 6. 클라우드 영속성 / 스토리지 (핵심 차이)

| 항목 | 모델 B (1박스) | 모델 C (서버리스) |
|------|---------------|------------------|
| DB | `/data/sessions.db` 영속 볼륨 | ⚠️ 로컬 디스크 휘발 → **외부화 필수**(마운트 스토리지/Postgres 대안) |
| outputs | `/data/outputs` 볼륨 | **S3 호환 오브젝트 버킷** |
| 보존 | 인스턴스 재생성에도 유지 | 외부 스토리지로만 보존 |
| 백업 | 정기 스냅샷 | 정기 스냅샷(특히 중요) |
| 동시성 | 단일 백엔드(WAL) | 단일 백엔드(WAL) |

> 인스턴스/컨테이너는 언제든 재생성 전제 → `DB_PATH`·`OUTPUTS_DIR`을 영속 볼륨/오브젝트로(기획 §6-8).
> SQLite WAL 단일 라이터 → 수평 확장 불가. 확장 시 DB 재설계(비목표).

---

## 7. env 매핑 (로컬 → 클라우드, 부록 B)

| env | 클라우드 값 | 출처 |
|-----|------------|------|
| `DB_PATH` | `/data/sessions.db`(볼륨) | `config.py:39` |
| `OUTPUTS_DIR` | `/data/outputs`(볼륨/오브젝트) | `config.py:40` |
| `ACESTEP_URL` | `http://acestep:8001` 또는 `https://<클라우드>` | `ace_client.py:12` |
| `ACESTEP_CLIENT_TIMEOUT` | `1800` (proxy 타임아웃도 일치) | `ace_client.py:14` |
| `CORS_ORIGINS` | `https://<도메인>` | `config.py:23` |
| `API_KEY` | **강한 비밀 필수** | `config.py:38,58` |
| `AI_PROVIDER` | `claude`/`ollama` | `config.py:37` |

---

## 8. 데이터 흐름

```
/plan        → sessions INSERT + tracks INSERT(N)
/generate/all → tracks.wav_url UPDATE(N) + sessions.status UPDATE
/generate/separated → clear_tracks → tracks INSERT(drums/bass/other)
volume/lock  → tracks UPDATE
/mix         → mix_versions INSERT (상한 시 oldest DELETE + 파일/오브젝트 삭제)
TTL 24h      → get_expired → delete_session (3테이블 수동 cascade)
재접속(타 기기) → get_session + get_tracks + get_latest_mix (복원)
```
