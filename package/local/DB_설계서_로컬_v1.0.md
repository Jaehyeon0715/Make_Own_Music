# AI Composer v2.8 — DB 설계서 (로컬) v1.0

> 출처: `MOM_package/local/AI_Composer_배포_기획서_v1.3.md`
> 코드 대조: `MOM/backend/db.py`, `MOM/backend/config.py`
> 작성일: 2026-06-05
> 엔진: **SQLite (aiosqlite)**, WAL, `foreign_keys=ON`. 테이블 3개. 로컬 단일 사용자.

---

## 1. 개요

| 항목 | 값 | 근거 |
|------|-----|------|
| 엔진 | SQLite (aiosqlite) | `db.py:8` |
| 저널 모드 | WAL | `db.py:16` |
| FK 강제 | `PRAGMA foreign_keys=ON` | `db.py:17` |
| 경로 | `DB_PATH` env, 로컬 기본 `BASE_DIR/sessions.db` → 배포 시 `%LOCALAPPDATA%\AI Composer\sessions.db` | `config.py:39`, 기획 §5 |
| TTL | `SESSION_TTL_HOURS=24` | `config.py:42` |
| 믹스 상한 | `MAX_MIX_VERSIONS=10` | `config.py:43` |

> Program Files 쓰기 제한 → DB·outputs·logs를 `%LOCALAPPDATA%`로 분리(기획 §5 P0).

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
| `ai_provider` | TEXT | NOT NULL | — | ollama/claude/openai/gemini |
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
| `bpm_override` | INTEGER | — | NULL | locked=0 시 캡션 반영 |
| `key_override` | TEXT | — | NULL | locked=0 시 캡션 반영 |
| `locked` | INTEGER | — | 1 | 1=전역 0=오버라이드 |
| `volume` | REAL | — | 1.0 | 믹스 볼륨 0~2 |
| `wav_url` | TEXT | — | NULL | WAV 경로(NULL=생성전) |

> 스템 분리 시 `clear_tracks()` 후 drums/bass/other 재삽입(`db.py:171`).

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

---

## 4. 주요 연산

| 연산 | 함수 |
|------|------|
| 세션 생성/조회/상태 | `create_session`, `get_session`, `update_session_status` |
| Provider 갱신 | `update_session_provider`, `update_all_sessions_provider` |
| 만료/삭제 | `get_expired_sessions(ttl)`, `delete_session` |
| 트랙 | `create_tracks`, `clear_tracks`, `get_tracks`, `update_track_wav/volume/lock` |
| 믹스 | `save_mix_version`, `get_mix_versions`, `get_latest_mix` |

> ⚠️ FK 있으나 ON DELETE CASCADE 미선언 → `delete_session()`이 tracks·mix_versions 명시 삭제(`db.py:124-130`).

---

## 5. 인덱스 권고 (현재 미선언)

| 인덱스 | 대상 |
|--------|------|
| `idx_tracks_session` | `tracks(session_id, track_order)` |
| `idx_mix_session` | `mix_versions(session_id, version)` |
| `idx_sessions_created` | `sessions(created_at)` (TTL 스캔) |

---

## 6. 로컬 영속성 / 백업

| 항목 | 값 |
|------|-----|
| DB 경로 | `%LOCALAPPDATA%\AI Composer\sessions.db` (`.env` `DB_PATH` 기록) |
| outputs | `%LOCALAPPDATA%\AI Composer\outputs\` (`OUTPUTS_DIR`) |
| 동시성 | 단일 사용자·단일 백엔드 (WAL 단일 라이터) |
| 백업 | 파일 복사(`migrate_sessions.ps1` 일회성 복사 스크립트, 기획 P6) |
| 업데이트 | 인스톨러 재실행 시 DB 보존(코드만 교체, 기획 §8) |

---

## 7. 데이터 흐름

```
/plan        → sessions INSERT + tracks INSERT(N)
/generate/all → tracks.wav_url UPDATE(N) + sessions.status UPDATE
/generate/separated → clear_tracks → tracks INSERT(drums/bass/other)
volume/lock  → tracks UPDATE
/mix         → mix_versions INSERT (상한 시 oldest DELETE + 파일 삭제)
TTL 24h      → get_expired → delete_session (3테이블 수동 cascade)
```
