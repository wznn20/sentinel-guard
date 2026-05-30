$ErrorActionPreference = "Stop"

$WheelUrl = if ($env:WHEEL_URL) { $env:WHEEL_URL } else { "https://github.com/wznn20/sentinel-guard/releases/latest/download/kx_agent-latest-py3-none-any.whl" }
$PythonBin = if ($env:PYTHON_BIN) { $env:PYTHON_BIN } else { "python" }

Write-Host "==> KX Agent bootstrap"

if (-not (Get-Command $PythonBin -ErrorAction SilentlyContinue)) {
    throw "python not found"
}

& $PythonBin -m pip install --upgrade pip
& $PythonBin -m pip install --upgrade $WheelUrl

$KxHome = Join-Path $HOME ".kx"
$ConfigPath = Join-Path $KxHome "config.yaml"
New-Item -ItemType Directory -Force -Path $KxHome | Out-Null
if (-not (Test-Path $ConfigPath)) {
    & $PythonBin -m kx_agent.cli setup --default
}

Write-Host ""
Write-Host "KX Agent installed."
Write-Host "Run:"
Write-Host "  kx status --json"
Write-Host "  kx chat"
Write-Host "  kx app"
