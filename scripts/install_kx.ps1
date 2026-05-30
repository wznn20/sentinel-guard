$ErrorActionPreference = "Stop"

$RepoUrl = if ($env:REPO_URL) { $env:REPO_URL } else { "https://github.com/wznn20/sentinel-guard.git" }
$InstallDir = if ($env:INSTALL_DIR) { $env:INSTALL_DIR } else { Join-Path $HOME ".kx\kx-agent" }
$PythonBin = if ($env:PYTHON_BIN) { $env:PYTHON_BIN } else { "python" }

Write-Host "==> KX Agent bootstrap"

if (-not (Get-Command $PythonBin -ErrorAction SilentlyContinue)) {
    throw "python not found"
}

if (-not (Test-Path (Join-Path $InstallDir ".git"))) {
    New-Item -ItemType Directory -Force -Path (Split-Path $InstallDir) | Out-Null
    git clone --depth 1 $RepoUrl $InstallDir
} else {
    git -C $InstallDir pull --ff-only origin main
}

& $PythonBin -m pip install --upgrade pip
& $PythonBin -m pip install -e $InstallDir

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
