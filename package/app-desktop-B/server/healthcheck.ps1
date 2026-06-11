<#
.SYNOPSIS
  GPU PC stack health check - backend /health, ACE-Step, Ollama model.
.EXAMPLE
  .\healthcheck.ps1 -Port 8080
  .\healthcheck.ps1 -HostName 192.168.0.50 -Port 8080   # remote check from another PC
#>
[CmdletBinding()]
param(
  [string]$HostName    = "localhost",
  [int]   $Port        = 8080,
  [string]$OllamaModel = "llama3.2"
)

function Probe($label,[scriptblock]$fn) {
  try { $r = & $fn; Write-Host ("  [OK] {0}: {1}" -f $label,$r) -ForegroundColor Green; return $true }
  catch { Write-Host ("  [X ] {0}: {1}" -f $label,$_.Exception.Message) -ForegroundColor Red; return $false }
}

Write-Host "`n=== AI Composer 헬스체크 ($HostName`:$Port) ===" -ForegroundColor Cyan

# 1. backend /health  -> { ok, ace_step }
# Note: ace_step=False can be normal (ACE-Step idle / model not yet loaded).
# The first /generate request lazy-loads the model and ace_step flips to True.
$beOk = Probe "backend /health" {
  $j = Invoke-RestMethod -Uri "http://$HostName`:$Port/health" -TimeoutSec 5
  $note = if (-not $j.ace_step) { " (idle — 정상, 첫 생성 요청 시 모델 로드)" } else { "" }
  "ok=$($j.ok), ace_step=$($j.ace_step)$note"
}

# 2. ACE-Step direct (localhost only - succeeds on the GPU PC itself)
Probe "ACE-Step :8001/health" {
  $j = Invoke-RestMethod -Uri "http://localhost:8001/health" -TimeoutSec 5
  $p = if ($j.data) { $j.data } else { $j }
  "status=$($p.status), model=$($p.loaded_model)"
} | Out-Null

# 3. Ollama model present
Probe "Ollama $OllamaModel" {
  $j = Invoke-RestMethod -Uri "http://localhost:11434/api/tags" -TimeoutSec 5
  $names = @($j.models | ForEach-Object { $_.name })
  if ($names -match [regex]::Escape($OllamaModel)) { "설치됨 ($($names -join ', '))" }
  else { throw "모델 미설치 — ollama pull $OllamaModel" }
} | Out-Null

Write-Host ""
if ($beOk) { Write-Host "backend 정상 → 내 PC .exe 가 http://<GPU_PC_IP>:$Port 로 접속 가능" -ForegroundColor Green }
else       { Write-Host "backend 응답 없음 → 서비스/방화벽/포트 확인 (.\register_services.ps1, $Port 인바운드)" -ForegroundColor Red }
