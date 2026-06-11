<#
.SYNOPSIS
  Manual test before registering services - launch ACE-Step + backend each in a new window.
.EXAMPLE
  .\start_server.ps1 -MomRoot C:\AIComposer\MOM -AceStepDir C:\AIComposer\ace-step -UvPath uv
#>
[CmdletBinding()]
param(
  [string]$MomRoot,
  [string]$AceStepDir,
  [string]$UvPath  = "uv",
  [string]$Python  = "python",
  [int]   $Port    = 8080,
  [switch]$NoAceStep,   # when ACE-Step is already running separately
  # If set, launch the wrapper script with python instead of `uv run acestep-api`
  # (the official ACE-Step repo does not expose that entry point).
  [string]$AceStepScript = ""
)
$ErrorActionPreference = "Stop"

if (-not $MomRoot -or -not (Test-Path (Join-Path $MomRoot "backend\main.py"))) {
  Write-Host "[X] -MomRoot 가 backend\main.py 미포함" -ForegroundColor Red; exit 1
}
$MomRoot = (Resolve-Path $MomRoot).Path

if (-not $NoAceStep) {
  if (-not $AceStepDir -or -not (Test-Path $AceStepDir)) { Write-Host "[X] -AceStepDir 경로 없음" -ForegroundColor Red; exit 1 }
  Write-Host "ACE-Step 기동 (새 창)..." -ForegroundColor Cyan
  if ($AceStepScript) {
    if (-not (Test-Path $AceStepScript)) { Write-Host "[X] AceStepScript 경로 없음" -ForegroundColor Red; exit 1 }
    $scriptAbs = (Resolve-Path $AceStepScript).Path
    Start-Process powershell -ArgumentList @(
      "-NoExit","-Command","`$env:ACESTEP_GENERATION_TIMEOUT='1800'; `$env:ACESTEP_PORT='8001'; `$env:ACE_STEP_DIR='$AceStepDir'; `$env:PYTHONPATH='$AceStepDir'; Set-Location '$AceStepDir'; & '$Python' '$scriptAbs'"
    )
  } else {
    Start-Process powershell -ArgumentList @(
      "-NoExit","-Command","`$env:ACESTEP_GENERATION_TIMEOUT='1800'; Set-Location '$AceStepDir'; & '$UvPath' run acestep-api"
    )
  }
  Write-Host "  ACE-Step 모델 로드까지 수십초~분 — :8001/health 확인 후 생성 가능" -ForegroundColor Gray
}

Write-Host "backend 기동 (새 창, :$Port)..." -ForegroundColor Cyan
Start-Process powershell -ArgumentList @(
  "-NoExit","-Command","Set-Location '$MomRoot'; & '$Python' -m uvicorn backend.main:app --host 0.0.0.0 --port $Port"
)

Write-Host "`n[OK] 두 창 기동. 브라우저: http://localhost:$Port" -ForegroundColor Green
Write-Host "    내 PC .exe 는 http://<이 PC의 LAN IP>:$Port 로 접속" -ForegroundColor Gray
Write-Host "    종료: 각 창 닫기 / Ctrl+C" -ForegroundColor Gray
