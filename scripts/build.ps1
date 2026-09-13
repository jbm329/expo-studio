
# scripts/build.ps1
$ErrorActionPreference = "Stop"
Set-Location (Split-Path (Split-Path $MyInvocation.MyCommand.Path -Parent) -Parent)
Write-Host "[build.ps1] Kör: uv run build-release"
& uv run build-release
