<#
.SYNOPSIS
  AI Composer layout B - GPU PC full-stack install (backend deps + torch CUDA + demucs + weights + Ollama model).
  The ACE-Step engine itself is assumed pre-installed (official build, `uv run acestep-api`).
  This script configures the backend environment only.

.DESCRIPTION
  Order: prechecks -> backend deps -> torch (CUDA) -> demucs+soundfile -> weight prefetch -> ollama pull -> .env.
  Windows PowerShell 5.1+. Does not redirect native exe stderr (judges by $LASTEXITCODE).

.EXAMPLE
  .\install_server.ps1 -MomRoot C:\AIComposer\MOM -CudaTag cu124
  .\install_server.ps1 -MomRoot C:\AIComposer\MOM -SkipTorch   # when torch is already installed
#>
[CmdletBinding()]
param(
  # Project root that contains backend/
  [string]$MomRoot   = (Resolve-Path (Join-Path $PSScriptRoot "..\..\..\MOM") -ErrorAction SilentlyContinue),
  # python to use (virtualenv recommended)
  [string]$Python    = "python",
  # PyTorch CUDA index tag (match the driver: cu121 / cu124 etc.)
  [string]$CudaTag   = "cu124",
  # Ollama model (Provider is fixed to Ollama)
  [string]$OllamaModel = "llama3.2",
  # Demucs model
  [string]$DemucsModel = "htdemucs",
  [switch]$SkipTorch,
  [switch]$SkipOllama,
  [switch]$Force      # overwrite .env
)

$ErrorActionPreference = "Stop"
$script:warn = @()

function Step($msg)  { Write-Host "`n=== $msg ===" -ForegroundColor Cyan }
function Ok($msg)    { Write-Host "  [OK] $msg" -ForegroundColor Green }
function Warn($msg)  { Write-Host "  [!] $msg" -ForegroundColor Yellow; $script:warn += $msg }
function Die($msg)   { Write-Host "  [X] $msg" -ForegroundColor Red; exit 1 }

function Have($name) { return [bool](Get-Command $name -ErrorAction SilentlyContinue) }

function Pip {
  # Use automatic $args, not a named [string[]]$Args param — $Args collides with
  # the PowerShell automatic variable and arrives empty, dropping every pip arg.
  if ($args.Count -eq 1 -and ($args[0] -is [array])) { $pipArgs = @($args[0]) }
  else { $pipArgs = @($args) }
  & $Python -m pip @pipArgs
  if ($LASTEXITCODE -ne 0) { Die "pip 실패: pip $($pipArgs -join ' ')" }
}

# ── 0. Path validation ─────────────────────────────────────────
Step "0. 경로 · 입력 확인"
if (-not $MomRoot -or -not (Test-Path (Join-Path $MomRoot "backend\main.py"))) {
  Die "MomRoot 가 backend\main.py 를 포함하지 않음: '$MomRoot'  → -MomRoot 로 지정"
}
$MomRoot = (Resolve-Path $MomRoot).Path
$backend = Join-Path $MomRoot "backend"
$reqMain = Join-Path $backend "requirements.txt"
$reqDem  = Join-Path $backend "requirements-demucs.txt"
$reqOll  = Join-Path $backend "requirements-ollama.txt"
Ok "MomRoot = $MomRoot"

# ── 1. Prechecks (GPU / python / external tools) ───────────────
Step "1. 사전 점검 (GPU · python · 외부 도구)"

if (Have "nvidia-smi") {
  $gpu = (& nvidia-smi --query-gpu=name,memory.total --format=csv,noheader) 2>$null | Select-Object -First 1
  Ok "GPU: $gpu"
} else {
  Warn "nvidia-smi 없음 → CUDA 미감지. CPU로도 동작하나 느림(DEMUCS_DEVICE=cpu)."
}

if (Have $Python) {
  $pyv = (& $Python --version)
  Ok "Python: $pyv"
} else { Die "python 없음 → -Python 으로 인터프리터 경로 지정" }

if (Have "uv")     { Ok "uv 있음 (ACE-Step 기동용)" } else { Warn "uv 없음 → ACE-Step 'uv run acestep-api' 불가. uv 설치 필요." }
if (Have "ffmpeg") { Ok "ffmpeg 있음 (mp3 export)" }   else { Warn "ffmpeg 없음 → 믹스 mp3 export 실패. 'winget install Gyan.FFmpeg' 또는 PATH 등록." }
if (Have "ollama") { Ok "ollama 있음" }                 else { Warn "ollama 없음 → plan 단계 실패. https://ollama.com 설치 후 재실행." }

# ── 2. pip upgrade + backend pure deps ─────────────────────────
Step "2. backend 순수 의존성 설치"
Pip @("install","--upgrade","pip")
if (Test-Path $reqMain) { Pip @("install","-r",$reqMain); Ok "requirements.txt" } else { Die "requirements.txt 없음: $reqMain" }
if (Test-Path $reqOll)  { Pip @("install","-r",$reqOll);  Ok "requirements-ollama.txt" } else { Warn "requirements-ollama.txt 없음(있으면 권장)" }

# ── 3. torch CUDA (must come before demucs!) ───────────────────
Step "3. PyTorch (CUDA) 설치"
if ($SkipTorch) {
  Warn "SkipTorch — torch 설치 건너뜀"
} elseif (Have "nvidia-smi") {
  $idx = "https://download.pytorch.org/whl/$CudaTag"
  Write-Host "  index-url = $idx"
  Pip @("install","torch","torchaudio","--index-url",$idx)
  Ok "torch + torchaudio ($CudaTag)"
} else {
  Warn "GPU 미감지 → CPU torch 설치"
  Pip @("install","torch","torchaudio")
}

# ── 4. demucs + soundfile ──────────────────────────────────────
Step "4. Demucs + soundfile 설치"
if (Test-Path $reqDem) { Pip @("install","-r",$reqDem); Ok "requirements-demucs.txt" }
else { Pip @("install","demucs>=4.0.0","soundfile>=0.12.0"); Ok "demucs + soundfile (fallback)" }

# Verify torch.cuda
$cudaChk = & $Python -c "import torch; print('CUDA' if torch.cuda.is_available() else 'CPU')"
if ($cudaChk -match "CUDA") { Ok "torch.cuda.is_available() = True" }
else { Warn "torch CUDA 불가 → DEMUCS_DEVICE=cpu 로 동작(느림). 드라이버/CudaTag 확인." }

# ── 5. Demucs weight prefetch ──────────────────────────────────
Step "5. Demucs 가중치 사전 다운로드 ($DemucsModel)"
Push-Location $MomRoot
try {
  $env:DEMUCS_MODEL = $DemucsModel
  & $Python -m backend.prefetch_demucs
  if ($LASTEXITCODE -ne 0) { Warn "prefetch 실패 — 첫 분리 시 자동 다운로드됨" } else { Ok "가중치 캐시 완료" }
} finally { Pop-Location }

# ── 6. Ollama model ────────────────────────────────────────────
Step "6. Ollama 모델 pull ($OllamaModel)"
if ($SkipOllama) { Warn "SkipOllama — 건너뜀" }
elseif (Have "ollama") {
  & ollama pull $OllamaModel
  if ($LASTEXITCODE -ne 0) { Warn "ollama pull 실패 — ollama serve 실행 중인지 확인" } else { Ok "$OllamaModel 준비" }
} else { Warn "ollama 미설치 → 모델 pull 생략" }

# ── 7. Generate .env ───────────────────────────────────────────
Step "7. backend\.env 생성"
$envPath = Join-Path $backend ".env"
$tmpl    = Join-Path $PSScriptRoot ".env.template"
if ((Test-Path $envPath) -and -not $Force) {
  Warn ".env 이미 존재 — 유지(-Force 로 덮어쓰기). 경로: $envPath"
} elseif (Test-Path $tmpl) {
  $content = Get-Content $tmpl -Raw -Encoding UTF8
  $content = $content.Replace("__OLLAMA_MODEL__", $OllamaModel)
  if ($cudaChk -match "CUDA") { $content = $content.Replace("__DEMUCS_DEVICE__","cuda") }
  else                        { $content = $content.Replace("__DEMUCS_DEVICE__","cpu") }
  $content | Set-Content $envPath -Encoding UTF8 -NoNewline
  Ok ".env 생성: $envPath"
} else { Warn ".env.template 없음 → 수동 작성 필요" }

# ── Summary ────────────────────────────────────────────────────
Step "설치 요약"
if ($script:warn.Count -eq 0) {
  Write-Host "  모든 단계 통과." -ForegroundColor Green
} else {
  Write-Host "  경고 $($script:warn.Count)건 — 검토:" -ForegroundColor Yellow
  $script:warn | ForEach-Object { Write-Host "   - $_" -ForegroundColor Yellow }
}
Write-Host "`n다음:" -ForegroundColor Cyan
Write-Host "  1) ACE-Step 기동 확인:  cd <ace-step>; uv run acestep-api"
Write-Host "  2) 수동 테스트:         .\start_server.ps1 -MomRoot $MomRoot"
Write-Host "  3) 상시 서비스 등록:    .\register_services.ps1 -MomRoot $MomRoot -AceStepDir <경로> -UvPath <uv.exe>"
Write-Host "  4) 헬스체크:            .\healthcheck.ps1"
