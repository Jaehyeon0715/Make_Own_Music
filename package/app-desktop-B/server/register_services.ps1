<#
.SYNOPSIS
  Register ACE-Step + backend as NSSM Windows services (auto-start on boot, restart on crash).

.DESCRIPTION
  Requires NSSM (https://nssm.cc). Creates two services:
    AIComposer-AceStep  : uv run acestep-api  (cwd=AceStepDir)
    AIComposer-Backend  : python -m uvicorn backend.main:app --host 0.0.0.0 --port <Port> (cwd=MomRoot)
  Ollama runs its own background process when installed on Windows (use -IncludeOllama to service-ize it).
  Run from an elevated (Administrator) PowerShell.

.EXAMPLE
  .\register_services.ps1 -MomRoot C:\AIComposer\MOM -AceStepDir C:\AIComposer\ace-step -UvPath C:\Users\me\.local\bin\uv.exe -OpenFirewall
  .\register_services.ps1 -Remove
#>
[CmdletBinding()]
param(
  [string]$MomRoot,
  [string]$AceStepDir,
  [string]$UvPath      = "uv",
  [string]$Python      = "python",
  [int]   $Port        = 8080,
  [string]$Nssm        = "nssm",
  [switch]$IncludeOllama,
  [string]$OllamaExe   = "ollama",
  [switch]$OpenFirewall,
  [switch]$Remove,
  # ACE-Step startup mode:
  #   ""               -> uv run acestep-api (default; only valid if your fork exposes this entry point)
  #   "<file.py>"      -> python <file.py>   (recommended — OpenRouter-compatible wrapper)
  # The official ACE-Step repo does NOT define an "acestep-api" entry point, so most
  # installs need a wrapper script (see GPU PC field report 2026-06-11).
  [string]$AceStepScript = "",
  # ffmpeg.exe path — injected into the backend service env so LocalSystem can find it
  # (winget installs ffmpeg into user PATH only, which the service account does not see).
  [string]$FfmpegPath  = ""
)

$ErrorActionPreference = "Stop"
$SVC_ACE = "AIComposer-AceStep"
$SVC_BE  = "AIComposer-Backend"
$SVC_OLL = "AIComposer-Ollama"

function Have($n) { return [bool](Get-Command $n -ErrorAction SilentlyContinue) }
function IsAdmin {
  $p = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
  return $p.IsInRole([Security.Principal.WindowsBuiltinRole]::Administrator)
}
function Nssm { param([string[]]$a) & $Nssm @a; if ($LASTEXITCODE -ne 0) { throw "nssm $($a -join ' ') 실패" } }

if (-not (IsAdmin)) { Write-Host "[X] 관리자 권한 PowerShell 필요." -ForegroundColor Red; exit 1 }
if (-not (Have $Nssm)) { Write-Host "[X] nssm 없음 → https://nssm.cc 설치 또는 -Nssm 경로 지정." -ForegroundColor Red; exit 1 }

# ── Remove mode ────────────────────────────────────────────────
if ($Remove) {
  foreach ($s in @($SVC_BE,$SVC_ACE,$SVC_OLL)) {
    if (Get-Service $s -ErrorAction SilentlyContinue) {
      & $Nssm stop $s   2>$null | Out-Null
      & $Nssm remove $s confirm 2>$null | Out-Null
      Write-Host "  제거: $s" -ForegroundColor Yellow
    }
  }
  Write-Host "[OK] 서비스 제거 완료." -ForegroundColor Green
  exit 0
}

# ── Input validation ───────────────────────────────────────────
if (-not $MomRoot -or -not (Test-Path (Join-Path $MomRoot "backend\main.py"))) {
  Write-Host "[X] -MomRoot 가 backend\main.py 미포함: '$MomRoot'" -ForegroundColor Red; exit 1
}
if (-not $AceStepDir -or -not (Test-Path $AceStepDir)) {
  Write-Host "[X] -AceStepDir 경로 없음: '$AceStepDir'" -ForegroundColor Red; exit 1
}
$MomRoot    = (Resolve-Path $MomRoot).Path
$AceStepDir = (Resolve-Path $AceStepDir).Path
$logDir     = Join-Path $MomRoot "logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null

function Register-Svc {
  param([string]$Name,[string]$App,[string]$Params,[string]$Dir,[hashtable]$Env)
  if (Get-Service $Name -ErrorAction SilentlyContinue) {
    & $Nssm stop $Name 2>$null | Out-Null
    & $Nssm remove $Name confirm 2>$null | Out-Null
  }
  Nssm @("install",$Name,$App)
  Nssm @("set",$Name,"AppParameters",$Params)
  Nssm @("set",$Name,"AppDirectory",$Dir)
  Nssm @("set",$Name,"AppStdout",(Join-Path $logDir "$Name.out.log"))
  Nssm @("set",$Name,"AppStderr",(Join-Path $logDir "$Name.err.log"))
  Nssm @("set",$Name,"Start","SERVICE_AUTO_START")
  Nssm @("set",$Name,"AppExit","Default","Restart")
  # NSSM AppEnvironmentExtra replaces on every call, so all KEY=val pairs must go in ONE call.
  if ($Env -and $Env.Count -gt 0) {
    $pairs = @(); foreach ($k in $Env.Keys) { $pairs += "$k=$($Env[$k])" }
    Nssm (@("set",$Name,"AppEnvironmentExtra") + $pairs)
  }
  Write-Host "  등록: $Name" -ForegroundColor Green
}

# Auto-detect ffmpeg.exe dir so the backend service (LocalSystem) can mp3 export.
$ffmpegBin = ""
if ($FfmpegPath) {
  if (Test-Path $FfmpegPath) { $ffmpegBin = (Split-Path (Resolve-Path $FfmpegPath) -Parent) }
} else {
  $cmd = Get-Command ffmpeg -ErrorAction SilentlyContinue
  if ($cmd) { $ffmpegBin = (Split-Path $cmd.Source -Parent) }
}
if (-not $ffmpegBin) {
  Write-Host "  [!] ffmpeg 미감지 → backend 서비스에 PATH 주입 못 함. mp3 export 실패 가능." -ForegroundColor Yellow
  Write-Host "      해결: -FfmpegPath <ffmpeg.exe 경로> 또는 시스템 PATH 등록." -ForegroundColor Yellow
} else {
  Write-Host "  ffmpeg PATH: $ffmpegBin" -ForegroundColor Gray
}

Write-Host "`n=== 서비스 등록 ===" -ForegroundColor Cyan

# ── ACE-Step ──
# Default `uv run acestep-api` only works if your install exposes that entry point.
# The official ACE-Step repo does NOT, so most setups need -AceStepScript pointing
# at an OpenRouter-compatible wrapper (see GPU PC field report 2026-06-11).
if ($AceStepScript) {
  if (-not (Test-Path $AceStepScript)) { Write-Host "[X] AceStepScript 경로 없음: $AceStepScript" -ForegroundColor Red; exit 1 }
  $scriptAbs = (Resolve-Path $AceStepScript).Path
  Register-Svc -Name $SVC_ACE -App $Python -Params "`"$scriptAbs`"" -Dir $AceStepDir `
    -Env @{
      ACE_STEP_DIR             = $AceStepDir
      ACESTEP_GENERATION_TIMEOUT = "1800"
      ACESTEP_PORT             = "8001"
      PYTHONPATH               = $AceStepDir
    }
} else {
  Register-Svc -Name $SVC_ACE -App $UvPath -Params "run acestep-api" -Dir $AceStepDir `
    -Env @{ ACESTEP_GENERATION_TIMEOUT = "1800" }
}

# ── backend (uvicorn 0.0.0.0:Port) — main.py loads .env from backend\.env ──
$beEnv = @{}
if ($ffmpegBin) {
  $beEnv["FFMPEG_BINARY"] = (Join-Path $ffmpegBin "ffmpeg.exe")
  # Prepend to PATH so child processes (e.g. ffprobe via pydub) also resolve.
  $beEnv["PATH"]         = "$ffmpegBin;$env:PATH"
}
Register-Svc -Name $SVC_BE -App $Python `
  -Params "-m uvicorn backend.main:app --host 0.0.0.0 --port $Port" -Dir $MomRoot `
  -Env $beEnv

# Ollama (optional)
if ($IncludeOllama) {
  Register-Svc -Name $SVC_OLL -App $OllamaExe -Params "serve" -Dir $MomRoot
}

# ── Firewall (LAN inbound 8080) ────────────────────────────────
if ($OpenFirewall) {
  $ruleName = "AIComposer-Backend-$Port"
  if (-not (Get-NetFirewallRule -DisplayName $ruleName -ErrorAction SilentlyContinue)) {
    New-NetFirewallRule -DisplayName $ruleName -Direction Inbound -Action Allow `
      -Protocol TCP -LocalPort $Port -Profile Private | Out-Null
    Write-Host "  방화벽 허용: TCP $Port (Private)" -ForegroundColor Green
  } else { Write-Host "  방화벽 규칙 이미 존재" -ForegroundColor Yellow }
  Write-Host "  ⚠ 8001(ACE-Step)·11434(Ollama)는 개방 금지 — localhost 전용 유지" -ForegroundColor Yellow
}

# ── Start ──────────────────────────────────────────────────────
Write-Host "`n=== 서비스 시작 ===" -ForegroundColor Cyan
foreach ($s in @($SVC_ACE,$SVC_BE)) { & $Nssm start $s 2>$null | Out-Null; Write-Host "  start: $s" }
if ($IncludeOllama) { & $Nssm start $SVC_OLL 2>$null | Out-Null }

Write-Host "`n[OK] 완료. 부팅 시 자동 기동. 상태확인: .\healthcheck.ps1 -Port $Port" -ForegroundColor Green
Write-Host "    로그: $logDir" -ForegroundColor Gray
Write-Host "    제거: .\register_services.ps1 -Remove" -ForegroundColor Gray
