# 씬 클라이언트 (.exe) — 내 PC

GPU PC backend(:8080)를 데스크톱 창으로 띄우는 경량 앱.
생성·분리·믹스는 전부 GPU PC. 이 앱은 **UI 창 + 연결 설정 + Wake-on-LAN** 만 한다.

## 구성
| 파일 | 역할 |
|------|------|
| `client_app.py` | pywebview 창, 설정 로드, 연결체크, JS↔Py 브리지 |
| `settings.html` | 첫 실행 연결 설정 화면(주소·포트·MAC) |
| `wol.py` | Wake-on-LAN 매직패킷 |
| `tray.py` | 트레이 아이콘(선택, pystray) |
| `requirements.txt` | pywebview·requests (+선택 pystray/Pillow) |
| `client.spec` / `build.ps1` | PyInstaller → `dist\AIComposer.exe` |

## 개발 실행
```powershell
python -m pip install -r requirements.txt
python client_app.py
```

## 빌드
```powershell
.\build.ps1
# → dist\AIComposer.exe
```
- 아이콘 원하면 `icon.ico`(exe) / `icon.png`(트레이)를 이 폴더에 두면 자동 포함.

## 동작 흐름
```
.exe 실행
 ├ 설정 있고 GPU PC 응답 → 바로 메인 UI(http://<GPU_PC>:8080)
 └ 없음/응답 없음 → settings.html
       ├ 주소·포트 입력 → [연결] → /health 확인 → 메인 UI 로드
       └ [GPU PC 깨우기] → MAC으로 WoL 매직패킷
```
- 설정 저장 위치: `%LOCALAPPDATA%\AIComposer\client.json`

## 전제 / 주의
- **WebView2 런타임** 필요 — Win10/11 대개 기본 동반. 없으면 MS Evergreen 설치.
- GPU PC가 켜져 있고 backend 기동 상태여야 연결됨(`server/healthcheck.ps1`로 확인).
- 외부(집 밖)면 두 PC **Tailscale** → 주소에 `100.x.x.x` 입력. 포트포워딩 금지.
- WoL은 **같은 LAN**에서만(라우터 너머 X), GPU PC BIOS/NIC에서 WoL 활성 필요.

## 코드 분담 (설계서 §10)
- backend/frontend = GPU PC에서 그대로 서빙(이 앱에 복제 안 함).
- 프론트 상대경로 fetch → 동일 origin이라 CORS·라우팅 무수정.
- 유일 프론트 변경 = Provider 셀렉터 숨김(Ollama 고정) — backend 측 frontend에서 처리.
