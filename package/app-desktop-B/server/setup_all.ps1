<#
.SYNOPSIS
  GPU PC one-step bootstrap - install through startup, health check, and connection address in one run.

.DESCRIPTION
  Order: prechecks -> (optional) tool auto-install (winget) -> install_server.ps1 (deps/torch/demucs/model/.env)
        -> register services (register_services.ps1, auto-elevation) or manual run (start_server.ps1)
        -> ACE-Step warmup wait -> healthcheck -> show client (.exe) connection address.
  Windows PowerShell 5.1+.

.EXAMPLE
  # Persistent services + firewall (recommended, one UAC prompt)
  .\setup_all.ps1 -MomRoot C:\AIComposer\MOM -AceStepDir C:\AIComposer\ace-step -UvPath C:\Users\me\.local\bin\uv.exe -AutoInstallTools

  # Run once for testing without registering services
  .\setup_all.ps1 -MomRoot C:\AIComposer\MOM -AceStepDir C:\AIComposer\ace-step -Mode run
#>
[CmdletBinding()]
param(
  [string]$MomRoot    = (Resolve-Path (Join-Path $PSScriptRoot "..\..\..\MOM") -ErrorAction SilentlyContinue),
  [string]$AceStepDir,
  [string]$UvPath     = "uv",
  [string]$Python     = "python",
  [string]$CudaTag    = "cu124",
  [string]$OllamaModel= "llama3.2",
  [int]   $Port       = 8080,
  [ValidateSet("service","run")][string]$Mode = "service",
  [switch]$AutoInstallTools,   # try winget for ffmpeg/ollama/uv/nssm
  [switch]$SkipInstall,        # skip dependency install, only start
  [switch]$OpenFirewall = $true,
  [int]   $WarmupTimeoutSec = 240,
  # Pass-through to register_services / start_server:
  # ACE-Step wrapper script. Required unless your install exposes `uv run acestep-api`.
  [string]$AceStepScript = "",
  # ffmpeg.exe path for backend service env (auto-detected if omitted).
  [string]$FfmpegPath  = ""
)

$ErrorActionPreference = "Stop"
function Hdr($m){ Write-Host "`n############ $m ############" -ForegroundColor Cyan }
function Ok($m) { Write-Host "  [OK] $m" -ForegroundColor Green }
function Warn($m){ Write-Host "  [!] $m" -ForegroundColor Yellow }
function Die($m){ Write-Host "  [X] $m" -ForegroundColor Red; exit 1 }
function Have($n){ return [bool](Get-Command $n -ErrorAction SilentlyContinue) }
function IsAdmin {
  $p = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
  return $p.IsInRole([Security.Principal.WindowsBuiltinRole]::Administrator)
}
function Lan-IP {
  try {
    $cfg = Get-NetIPConfiguration | Where-Object { $_.IPv4DefaultGateway -and $_.NetAdapter.Status -eq 'Up' } | Select-Object -First 1
    if ($cfg) { return $cfg.IPv4Address.IPAddress }
  } catch {}
  return "<이 PC의 LAN IP>"
}

Hdr "0. 입력 확인"
if (-not $MomRoot -or -not (Test-Path (Join-Path $MomRoot "backend\main.py"))) { Die "-MomRoot 가 backend\main.py 미포함: '$MomRoot'" }
$MomRoot = (Resolve-Path $MomRoot).Path
if ($Mode -eq "run" -or -not $SkipInstall) {
  if (-not $AceStepDir -or -not (Test-Path $AceStepDir)) { Die "-AceStepDir 경로 필요/없음: '$AceStepDir'" }
}
if ($AceStepDir) { $AceStepDir = (Resolve-Path $AceStepDir).Path }
Ok "MomRoot=$MomRoot"; if ($AceStepDir){ Ok "AceStepDir=$AceStepDir" }

# ── 1. Prechecks (items that cannot be auto-installed) ─────────
Hdr "1. 사전점검"
if (Have "nvidia-smi") { Ok ("GPU: " + ((& nvidia-smi --query-gpu=name --format=csv,noheader) | Select-Object -First 1)) }
else { Warn "nvidia-smi 없음 — CUDA 미감지. CPU 동작(느림). 드라이버 설치 권장." }
if (Have $Python) { Ok ("Python: " + (& $Python --version)) } else { Die "python 없음 — 설치 후 -Python 지정" }

# ── 2. Tool auto-install (winget, best-effort) ─────────────────
Hdr "2. 외부 도구"
function Winget-Install($id,$bin){
  if (Have $bin) { Ok "$bin 있음"; return }
  if (-not $AutoInstallTools) { Warn "$bin 없음 — 수동 설치 또는 -AutoInstallTools"; return }
  if (-not (Have "winget")) { Warn "winget 없음 — $bin 수동 설치 필요"; return }
  Write-Host "  winget install $id ..."
  & winget install --id $id -e --accept-source-agreements --accept-package-agreements --silent
  if (Have $bin) { Ok "$bin 설치됨" } else { Warn "$bin 자동설치 실패 — 수동 설치" }
}
Winget-Install "Gyan.FFmpeg"   "ffmpeg"
Winget-Install "Ollama.Ollama" "ollama"
if ($UvPath -eq "uv") { Winget-Install "astral-sh.uv" "uv" } else { if (Test-Path $UvPath){ Ok "uv=$UvPath" } else { Warn "uv 경로 없음: $UvPath" } }
if ($Mode -eq "service") {
  if (Have "nssm") { Ok "nssm 있음" }
  else { Warn "nssm 없음 — winget 미보장. https://nssm.cc 수동 설치 또는 'choco install nssm'. (없으면 -Mode run 으로 대체)" }
}

# ── 3. Dependency install ──────────────────────────────────────
Hdr "3. 의존성 설치 (install_server.ps1)"
if ($SkipInstall) { Warn "SkipInstall — 생략" }
else {
  & (Join-Path $PSScriptRoot "install_server.ps1") -MomRoot $MomRoot -Python $Python -CudaTag $CudaTag -OllamaModel $OllamaModel -Force
  if ($LASTEXITCODE -ne 0 -and $LASTEXITCODE -ne $null) { Die "install_server 실패" }
  Ok "의존성 설치 완료"
}

# ── 4. Startup (register services or manual run) ───────────────
Hdr "4. 기동 ($Mode)"
if ($Mode -eq "service") {
  if (-not (Have "nssm")) { Warn "nssm 없음 → 수동기동(run)으로 대체"; $Mode = "run" }
}
if ($Mode -eq "service") {
  $reg = Join-Path $PSScriptRoot "register_services.ps1"
  $cmd = "-NoProfile -ExecutionPolicy Bypass -File `"$reg`" -MomRoot `"$MomRoot`" -AceStepDir `"$AceStepDir`" -UvPath `"$UvPath`" -Python `"$Python`" -Port $Port"
  if ($OpenFirewall)   { $cmd += " -OpenFirewall" }
  if ($AceStepScript)  { $cmd += " -AceStepScript `"$AceStepScript`"" }
  if ($FfmpegPath)     { $cmd += " -FfmpegPath `"$FfmpegPath`"" }
  if (IsAdmin) {
    $regArgs = @{ MomRoot=$MomRoot; AceStepDir=$AceStepDir; UvPath=$UvPath; Python=$Python; Port=$Port; OpenFirewall=$OpenFirewall }
    if ($AceStepScript) { $regArgs["AceStepScript"] = $AceStepScript }
    if ($FfmpegPath)    { $regArgs["FfmpegPath"]    = $FfmpegPath }
    & $reg @regArgs
  } else {
    Warn "서비스 등록은 관리자 권한 필요 → UAC 띄움"
    # Re-launch only the service registration step elevated.
    try { Start-Process powershell -Verb RunAs -ArgumentList $cmd -Wait; Ok "서비스 등록(관리자) 완료" }
    catch { Warn "권한상승 거부 → 수동기동(run)으로 대체"; $Mode = "run" }
  }
}
if ($Mode -eq "run") {
  $runArgs = @{ MomRoot=$MomRoot; AceStepDir=$AceStepDir; UvPath=$UvPath; Python=$Python; Port=$Port }
  if ($AceStepScript) { $runArgs["AceStepScript"] = $AceStepScript }
  & (Join-Path $PSScriptRoot "start_server.ps1") @runArgs
  Ok "수동기동(두 창) — 닫으면 종료. 상시화하려면 관리자로 -Mode service 재실행"
}

# ── 5. ACE-Step warmup wait + health check ─────────────────────
Hdr "5. 웜업 대기 + 헬스체크"
# Preload the model (removes first-generation latency)
try { Invoke-RestMethod -Uri "http://localhost:8001/v1/init" -Method Post -Body "{}" -ContentType "application/json" -TimeoutSec 10 | Out-Null } catch {}
$deadline = (Get-Date).AddSeconds($WarmupTimeoutSec)
$ready = $false
while ((Get-Date) -lt $deadline) {
  try {
    $h = Invoke-RestMethod -Uri "http://localhost:$Port/health" -TimeoutSec 5
    if ($h.ok -and $h.ace_step) { $ready = $true; break }
    Write-Host "  대기 중... backend=$($h.ok) ace_step=$($h.ace_step)" -ForegroundColor Gray
  } catch { Write-Host "  backend 기동 대기..." -ForegroundColor Gray }
  Start-Sleep -Seconds 5
}
& (Join-Path $PSScriptRoot "healthcheck.ps1") -Port $Port -OllamaModel $OllamaModel

# ── 6. Connection guidance ─────────────────────────────────────
Hdr "완료"
$ip = Lan-IP
if ($ready) { Write-Host "  생성 준비 완료 (ace_step=true)." -ForegroundColor Green }
else { Warn "ACE-Step 아직 미준비 — 모델 로드 더 걸릴 수 있음. healthcheck 재실행해 ace_step=true 확인." }
Write-Host "`n  내 PC 클라이언트(.exe) 접속 주소:" -ForegroundColor Cyan
Write-Host "    http://$ip`:$Port" -ForegroundColor White
Write-Host "    (집 밖이면 Tailscale 100.x 주소 사용)" -ForegroundColor Gray
Write-Host "`n  다음: 내 PC 에서 client\build.ps1 → AIComposer.exe → 위 주소 입력" -ForegroundColor Cyan
