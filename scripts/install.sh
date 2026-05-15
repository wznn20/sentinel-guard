#!/usr/bin/env bash
# ============================================================
# Sentinel — AI网络安全智能体
# Linux/macOS 一键安装脚本
# ============================================================
set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; CYAN='\033[0;36m'; NC='\033[0m'
BOLD='\033[1m'

SENTINEL_HOME="${SENTINEL_HOME:-$HOME/.sentinel}"
INSTALL_DIR="${INSTALL_DIR:-$HOME/.sentinel/sentinel-agent}"
VERSION="${VERSION:-latest}"
MIN_PYTHON="3.11"

banner() {
    echo -e "${CYAN}"
    echo "  ╔══════════════════════════════════════════╗"
    echo "  ║     Sentinel — AI 安全哨兵 安装程序      ║"
    echo "  ╚══════════════════════════════════════════╝"
    echo -e "${NC}"
}

detect_os() {
    case "$(uname -s)" in
        Linux*)  OS="linux";;
        Darwin*) OS="macos";;
        *)       echo -e "${RED}✗ 不支持的操作系统: $(uname -s)${NC}"; exit 1;;
    esac
    ARCH=$(uname -m)
    echo -e "  📋 检测到: ${BOLD}${OS}${NC} / ${ARCH}"
}

check_python() {
    echo -e "\n${CYAN}━━━ 检查 Python 环境 ━━━${NC}"

    # Find Python 3.11+
    PYTHON=""
    for py in python3.12 python3.11 python3; do
        if cmd=$(command -v "$py" 2>/dev/null); then
            ver=$("$cmd" --version 2>&1 | grep -oP '\d+\.\d+')
            if [ "$(printf '%s\n' "$MIN_PYTHON" "$ver" | sort -V | head -n1)" = "$MIN_PYTHON" ]; then
                PYTHON="$cmd"
                break
            fi
        fi
    done

    if [ -z "$PYTHON" ]; then
        echo -e "  ${RED}✗ 需要 Python >= ${MIN_PYTHON}${NC}"
        echo "  安装方法:"
        if [ "$OS" = "macos" ]; then
            echo "    brew install python@3.12"
        else
            echo "    sudo apt install python3.12 python3.12-venv  # Ubuntu/Debian"
            echo "    sudo dnf install python3.12                   # Fedora/RHEL"
        fi
        exit 1
    fi
    echo -e "  ${GREEN}✓${NC} Python: $($PYTHON --version)"
}

install_system_deps() {
    echo -e "\n${CYAN}━━━ 安装系统依赖 ━━━${NC}"

    if [ "$OS" = "macos" ]; then
        # macOS — brew
        if ! command -v brew &>/dev/null; then
            echo "  安装 Homebrew..."
            /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
        fi
        DEPS=(libpcap tcpdump)
        for dep in "${DEPS[@]}"; do
            if brew list "$dep" &>/dev/null; then
                echo -e "  ${GREEN}✓${NC} $dep (已安装)"
            else
                echo "  安装 $dep..."
                brew install "$dep" --quiet
            fi
        done

    elif [ "$OS" = "linux" ]; then
        # Linux — detect package manager
        if command -v apt-get &>/dev/null; then
            PKG_MGR="apt-get"
            sudo apt-get update -qq
            DEPS=(libpcap-dev tcpdump python3-venv python3-pip)
            sudo apt-get install -y -qq "${DEPS[@]}"
        elif command -v dnf &>/dev/null; then
            PKG_MGR="dnf"
            DEPS=(libpcap-devel tcpdump python3-pip)
            sudo dnf install -y -q "${DEPS[@]}"
        elif command -v pacman &>/dev/null; then
            PKG_MGR="pacman"
            DEPS=(libpcap tcpdump python-pip)
            sudo pacman -S --noconfirm "${DEPS[@]}"
        elif command -v apk &>/dev/null; then
            PKG_MGR="apk"
            DEPS=(libpcap-dev tcpdump python3 py3-pip)
            sudo apk add "${DEPS[@]}"
        else
            echo -e "  ${RED}✗ 未识别的包管理器，请手动安装: libpcap-dev, tcpdump${NC}"
        fi
        echo -e "  ${GREEN}✓${NC} 系统依赖安装完成 ($PKG_MGR)"
    fi
}

setup_python_env() {
    echo -e "\n${CYAN}━━━ 设置 Python 虚拟环境 ━━━${NC}"

    VENV="$SENTINEL_HOME/venv"
    if [ ! -d "$VENV" ]; then
        "$PYTHON" -m venv "$VENV"
        echo -e "  ${GREEN}✓${NC} 虚拟环境: $VENV"
    else
        echo -e "  ${GREEN}✓${NC} 虚拟环境已存在"
    fi

    # Activate and install
    source "$VENV/bin/activate"
    pip install --upgrade pip -q

    # Install Sentinel
    if [ "$VERSION" = "latest" ]; then
        echo "  安装 Sentinel (最新版)..."
        pip install sentinel-guard -q 2>/dev/null || {
            # Fallback: install from local
            if [ -f "$INSTALL_DIR/pyproject.toml" ]; then
                pip install -e "$INSTALL_DIR" -q
            else
                pip install "git+https://github.com/nousresearch/sentinel.git" -q
            fi
        }
    else
        pip install "sentinel-guard==$VERSION" -q
    fi
    echo -e "  ${GREEN}✓${NC} Sentinel 已安装"
}

setup_service() {
    echo -e "\n${CYAN}━━━ 配置自启动 ━━━${NC}"

    if [ "$OS" = "macos" ]; then
        # macOS — launchd
        PLIST="$HOME/Library/LaunchAgents/com.sentinel.security.plist"
        mkdir -p "$HOME/Library/LaunchAgents"

        cat > "$PLIST" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.sentinel.security</string>
    <key>ProgramArguments</key>
    <array>
        <string>$SENTINEL_HOME/venv/bin/sentinel</string>
        <string>start</string>
        <string>--daemon</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>$SENTINEL_HOME/logs/sentinel.log</string>
    <key>StandardErrorPath</key>
    <string>$SENTINEL_HOME/logs/sentinel.err</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>SENTINEL_HOME</key>
        <string>$SENTINEL_HOME</string>
    </dict>
</dict>
</plist>
EOF
        launchctl unload "$PLIST" 2>/dev/null || true
        launchctl load "$PLIST"
        echo -e "  ${GREEN}✓${NC} launchd 服务已配置 (开机自启)"

    elif [ "$OS" = "linux" ]; then
        # Linux — systemd (user)
        SYSTEMD_DIR="$HOME/.config/systemd/user"
        mkdir -p "$SYSTEMD_DIR"

        cat > "$SYSTEMD_DIR/sentinel.service" << EOF
[Unit]
Description=Sentinel AI Security Agent
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart=$SENTINEL_HOME/venv/bin/sentinel start --daemon
Restart=on-failure
RestartSec=10
Environment=SENTINEL_HOME=$SENTINEL_HOME
StandardOutput=append:$SENTINEL_HOME/logs/sentinel.log
StandardError=append:$SENTINEL_HOME/logs/sentinel.err

[Install]
WantedBy=default.target
EOF

        systemctl --user daemon-reload
        systemctl --user enable sentinel.service
        systemctl --user start sentinel.service

        # Enable lingering (keep running after logout)
        if command -v loginctl &>/dev/null; then
            loginctl enable-linger "$USER" 2>/dev/null || true
        fi
        echo -e "  ${GREEN}✓${NC} systemd 服务已配置 (开机自启)"
    fi
}

create_dirs() {
    mkdir -p "$SENTINEL_HOME"/{logs,evidence,plugins,config}
}

run_setup() {
    echo -e "\n${CYAN}━━━ 运行初始化向导 ━━━${NC}"
    "$SENTINEL_HOME/venv/bin/sentinel" setup
}

finish() {
    echo -e "\n${GREEN}${BOLD}  ✅ Sentinel 安装完成！${NC}"
    echo
    echo -e "  ${BOLD}管理命令:${NC}"
    echo -e "    sentinel start      启动"
    echo -e "    sentinel stop       停止"
    echo -e "    sentinel status     查看状态"
    echo -e "    sentinel dashboard  打开控制面板"
    echo
    echo -e "  ${BOLD}配置文件:${NC} $SENTINEL_HOME/config.yaml"
    echo -e "  ${BOLD}控制面板:${NC} http://localhost:8443"
    echo
    echo -e "  ${CYAN}Sentinel 已开始守护你的资产 🛡${NC}"
}

# === Main ===
banner
detect_os
check_python
install_system_deps
create_dirs
setup_python_env
setup_service
run_setup
finish
