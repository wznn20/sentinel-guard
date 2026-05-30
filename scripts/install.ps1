$ErrorActionPreference = "Stop"

Write-Host "Sentinel branding is deprecated for this runtime."
Write-Host "Forwarding to the KX installer..."
Write-Host ""

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
& (Join-Path $ScriptDir "install_kx.ps1")
