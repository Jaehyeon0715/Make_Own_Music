<#
.SYNOPSIS
  Build the thin-client .exe (PyInstaller).
.EXAMPLE
  .\build.ps1                # install deps + build
  .\build.ps1 -SkipDeps      # build only
#>
[CmdletBinding()]
param(
  [string]$Python = "python",
  [switch]$SkipDeps
)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not $SkipDeps) {
  Write-Host "의존성 설치..." -ForegroundColor Cyan
  & $Python -m pip install -r requirements.txt
  if ($LASTEXITCODE -ne 0) { Write-Host "[X] pip 실패" -ForegroundColor Red; exit 1 }
}

Write-Host "PyInstaller 빌드..." -ForegroundColor Cyan
& $Python -m PyInstaller client.spec --noconfirm --clean
if ($LASTEXITCODE -ne 0) { Write-Host "[X] 빌드 실패" -ForegroundColor Red; exit 1 }

$exe = Join-Path $PSScriptRoot "dist\AIComposer.exe"
if (Test-Path $exe) {
  Write-Host "`n[OK] 산출물: $exe" -ForegroundColor Green
  Write-Host "    더블클릭 → 첫 실행 시 GPU PC 주소 입력 → 연결" -ForegroundColor Gray
  Write-Host "    ⚠ 대상 PC에 WebView2 런타임 필요(Win10/11 대개 기본 동반)" -ForegroundColor Yellow
} else {
  Write-Host "[X] dist\AIComposer.exe 없음" -ForegroundColor Red; exit 1
}
