# ============================================================
# Sentinel — AI 网络安全智能体
# Windows PowerShell 一键安装脚本
# 要求: Windows 10+ / PowerShell 5.1+ / 管理员权限(部分步骤)
# ============================================================

param(
    [string]$InstallPath = "$env:USERPROFILE\.sentinel",
    [string]$Version = "latest",
    [switch]$NoService = $false,
    [switch]$SkipDeps = $false
)

$ErrorActionPreference = "Stop"

# ── 样式 ──
function Write-Banner {
    Write-Host @"
  ╔══════════════════════════════════════════╗
  ║     Sentinel — AI 安全哨兵 安装程序      ║
  ║           Windows Edition                ║
  ╚══════════════════════════════════════════╝
"@ -ForegroundColor Cyan
}

function Write-Step { Write-Host "`n━━━ $args ━━━" -ForegroundColor Cyan }
function Write-OK   { Write-Host "  ✓ $args" -ForegroundColor Green }
function Write-ERR  { Write-Host "  ✗ $args" -ForegroundColor Red; exit 1 }
function Write-WARN { Write-Host "  ⚠ $args" -ForegroundColor Yellow }

# ── 系统检测 ──
function Test-Admin {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Test-WindowsVersion {
    $ver = [Environment]::OSVersion.Version
    if ($ver.Major -lt 10) {
        Write-ERR "需要 Windows 10 或更高版本"
    }
    Write-OK "Windows $($ver.Major).$($ver.Minor) (Build $($ver.Build))"
}

# ── Python ──
function Install-Python {
    Write-Step "检查 Python 环境"

    # Check for existing Python 3.11+
    $pythonPaths = @(
        "python3", "python",
        "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe",
        "$env:LOCALAPPDATA\Programs\Python\Python311\python.exe",
        "$env:ProgramFiles\Python312\python.exe",
        "$env:ProgramFiles\Python311\python.exe"
    )

    $global:PythonExe = $null
    foreach ($p in $pythonPaths) {
        $found = Get-Command $p -ErrorAction SilentlyContinue
        if ($found) {
            $verOutput = & $found.Source --version 2>&1
            if ($verOutput -match "(\d+)\.(\d+)") {
                if ([int]$Matches[1] -ge 3 -and [int]$Matches[2] -ge 11) {
                    $global:PythonExe = $found.Source
                    Write-OK "Python: $verOutput"
                    break
                }
            }
        }
    }

    if (-not $global:PythonExe) {
        Write-WARN "未找到 Python >= 3.11，正在通过 winget 安装..."

        # Install via winget (Windows 10+ 自带)
        winget install Python.Python.3.12 --accept-package-agreements --accept-source-agreements
        if ($LASTEXITCODE -ne 0) {
            Write-ERR "Python 安装失败。请手动安装: https://www.python.org/downloads/"
        }

        # Refresh PATH
        $env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" +
                    [System.Environment]::GetEnvironmentVariable("Path", "User")

        $global:PythonExe = "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe"
        if (-not (Test-Path $global:PythonExe)) {
            $global:PythonExe = "$env:ProgramFiles\Python312\python.exe"
        }
        Write-OK "Python 3.12 安装完成"
    }
}

# ── Npcap ──
function Install-Npcap {
    Write-Step "安装 Npcap (网络抓包驱动)"

    # Check if Npcap is already installed
    $npcapPath = "$env:SystemRoot\System32\Npcap"
    if (Test-Path $npcapPath) {
        Write-OK "Npcap 已安装"
        return
    }

    Write-WARN "Npcap 未安装 (流量分析需要)"

    # Download Npcap installer
    $npcapUrl = "https://npcap.com/dist/npcap-1.80.exe"
    $npcapInstaller = "$env:TEMP\npcap-installer.exe"

    Write-Host "  下载 Npcap..."
    Invoke-WebRequest -Uri $npcapUrl -OutFile $npcapInstaller -UseBasicParsing

    Write-Host "  安装 Npcap (需要管理员权限)..."
    if (Test-Admin) {
        Start-Process -FilePath $npcapInstaller -ArgumentList "/S" -Wait -NoNewWindow
        Write-OK "Npcap 安装完成"
    } else {
        Write-WARN "需要管理员权限安装 Npcap"
        Start-Process -FilePath $npcapInstaller -ArgumentList "/S" -Verb RunAs -Wait
        Write-OK "Npcap 安装完成"
    }

    Remove-Item $npcapInstaller -Force -ErrorAction SilentlyContinue
}

# ── 虚拟环境 ──
function New-SentinelVenv {
    Write-Step "创建 Python 虚拟环境"

    $venvPath = "$InstallPath\venv"

    if (Test-Path $venvPath) {
        Write-OK "虚拟环境已存在: $venvPath"
    } else {
        & $global:PythonExe -m venv $venvPath
        Write-OK "虚拟环境: $venvPath"
    }

    # Activate venv
    $activateScript = "$venvPath\Scripts\Activate.ps1"
    . $activateScript

    # Upgrade pip
    python -m pip install --upgrade pip -q

    # Install Sentinel
    Write-Host "  安装 Sentinel..."
    pip install sentinel-guard -q 2>$null
    if ($LASTEXITCODE -ne 0) {
        # Fallback: install from git
        pip install "git+https://github.com/nousresearch/sentinel.git" -q
    }
    Write-OK "Sentinel 安装完成"
}

# ── 目录结构 ──
function New-SentinelDirs {
    $dirs = @(
        "$InstallPath\logs",
        "$InstallPath\evidence",
        "$InstallPath\plugins",
        "$InstallPath\config"
    )
    foreach ($d in $dirs) {
        New-Item -ItemType Directory -Force -Path $d | Out-Null
    }
    Write-OK "目录结构已创建"
}

# ── Windows 服务 ──
function New-SentinelService {
    if ($NoService) {
        Write-WARN "跳过服务注册 (--NoService)"
        return
    }

    Write-Step "注册 Windows 服务"

    $serviceName = "SentinelSecurity"
    $service = Get-Service -Name $serviceName -ErrorAction SilentlyContinue

    if ($service) {
        Write-OK "服务已存在: $serviceName"
        return
    }

    if (-not (Test-Admin)) {
        Write-WARN "需要管理员权限注册服务。请以管理员身份运行:"
        Write-Host "  sentinel service install"
        return
    }

    # Using nssm or sc
    $sentinelExe = "$InstallPath\venv\Scripts\sentinel.exe"
    if (Get-Command nssm -ErrorAction SilentlyContinue) {
        nssm install $serviceName $sentinelExe
        nssm set $serviceName AppParameters "start --daemon"
        nssm set $serviceName AppDirectory $InstallPath
        nssm set $serviceName Start SERVICE_AUTO_START
        nssm start $serviceName
    } else {
        sc.exe create $serviceName binPath= "$sentinelExe start --daemon" start= auto
        sc.exe description $serviceName "Sentinel AI Security Agent"
        sc.exe start $serviceName
    }
    Write-OK "Windows 服务已注册: $serviceName (开机自启)"
}

# ── 快捷方式 ──
function New-SentinelShortcut {
    Write-Step "创建快捷方式"

    # Desktop shortcut to dashboard
    $WshShell = New-Object -ComObject WScript.Shell
    $desktop = [Environment]::GetFolderPath("Desktop")
    $shortcut = $WshShell.CreateShortcut("$desktop\Sentinel Dashboard.lnk")

    # Use a simple batch wrapper
    $wrapperPath = "$InstallPath\open-dashboard.bat"
    @"
@echo off
start http://localhost:8443
"@ | Out-File -FilePath $wrapperPath -Encoding ASCII

    $shortcut.TargetPath = $wrapperPath
    $shortcut.WorkingDirectory = $InstallPath
    $shortcut.IconLocation = "$InstallPath\assets\sentinel.ico"
    $shortcut.Save()
    Write-OK "桌面快捷方式已创建"
}

# ── 完成 ──
function Write-Finish {
    Write-Host "`n" -NoNewline
    Write-Host "  ✅ Sentinel 安装完成！" -ForegroundColor Green

    Write-Host @"

  ┌─────────────────────────────────────────────┐
  │  管理命令 (PowerShell):                      │
  │    sentinel start         启动               │
  │    sentinel stop          停止               │
  │    sentinel status        查看状态            │
  │    sentinel dashboard     打开控制面板        │
  │    sentinel setup         重新配置            │
  │                                              │
  │  控制面板:  http://localhost:8443             │
  │  配置文件:  $InstallPath\config.yaml
  │  日志目录:  $InstallPath\logs
  └─────────────────────────────────────────────┘

  Sentinel 已开始守护你的资产 🛡
"@
}

# ========== 主流程 ==========
Write-Banner

Write-Step "系统检测"
Test-WindowsVersion

# 权限提示
if (-not (Test-Admin)) {
    Write-WARN "非管理员模式 — Npcap 和服务注册可能需要手动操作"
}

Install-Python

if (-not $SkipDeps) {
    Install-Npcap
}

New-SentinelDirs
New-SentinelVenv
New-SentinelService
New-SentinelShortcut

Write-Finish
