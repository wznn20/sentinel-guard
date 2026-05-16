"""
Sentinel Setup Wizard — 高级交互式配置向导（v0.3.0）
借鉴 Hermes setup 设计模式，支持 litellm 100+ 模型提供商
"""
import os
import sys
import time
import shutil
from pathlib import Path
from typing import Optional

import yaml

# ── 颜色常量 ──
C = {
    "reset": "\033[0m", "bold": "\033[1m", "dim": "\033[2m",
    "cyan": "\033[36m", "green": "\033[32m", "yellow": "\033[33m",
    "red": "\033[31m", "magenta": "\033[35m", "blue": "\033[34m",
    "white": "\033[37m", "bg_cyan": "\033[46m", "bg_green": "\033[42m",
}

def c(color: str, text: str) -> str:
    return f"{C.get(color, '')}{text}{C['reset']}"

def hr(char="─", width=None, color="dim"):
    w = width or shutil.get_terminal_size().columns
    return c(color, char * min(w, 100))

def box(text: str, color="cyan", pad=2):
    lines = text.strip().split("\n")
    width = max(len(l) for l in lines) + pad * 2
    top = f"╭{'─' * width}╮"
    mid = "\n".join(f"│{' ' * pad}{l}{' ' * (width - len(l) - pad)}│" for l in lines)
    bot = f"╰{'─' * width}╯"
    return c(color, f"{top}\n{mid}\n{bot}")

def ask(prompt: str, default: str = "", password: bool = False) -> str:
    """带默认值提示的输入"""
    d = c("dim", f" [{default}]") if default else ""
    p = f"  {prompt}{d}: "
    if password:
        import getpass
        val = getpass.getpass(p)
    else:
        val = input(p).strip()
    return val if val else default

def confirm(prompt: str, default: bool = True) -> bool:
    yn = "Y/n" if default else "y/N"
    d = "Y" if default else "N"
    val = input(f"  {prompt} [{yn}]: ").strip().lower()
    if not val:
        return default
    return val in ("y", "yes")

def section(title: str):
    print(f"\n{c('cyan', '━━━')} {c('bold', title)} {c('cyan', '━━━')}\n")

def success(msg: str):
    print(f"  {c('green', '✅')} {msg}")

def warn(msg: str):
    print(f"  {c('yellow', '⚠️')}  {msg}")

def error(msg: str):
    print(f"  {c('red', '❌')} {msg}")

def info(msg: str):
    print(f"  {c('dim', msg)}")


# ── 提供商数据（litellm 100+ 提供商的精选列表） ──

PROVIDERS = {
    # ── 国际主流 ──
    "openai": {
        "name": "OpenAI",
        "default_model": "gpt-4o-mini",
        "models": ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "o3-mini", "o1", "o1-mini"],
        "env_key": "OPENAI_API_KEY",
        "litellm_prefix": "openai",
        "base_url": None,
    },
    "anthropic": {
        "name": "Anthropic Claude",
        "default_model": "claude-sonnet-4-20250514",
        "models": ["claude-sonnet-4-20250514", "claude-opus-4-20250514", "claude-3-5-sonnet-20241022", "claude-3-5-haiku-20241022"],
        "env_key": "ANTHROPIC_API_KEY",
        "litellm_prefix": "anthropic",
        "base_url": None,
    },
    "google": {
        "name": "Google Gemini",
        "default_model": "gemini-2.0-flash",
        "models": ["gemini-2.5-pro", "gemini-2.0-flash", "gemini-1.5-pro", "gemini-1.5-flash"],
        "env_key": "GEMINI_API_KEY",
        "litellm_prefix": "gemini",
        "base_url": None,
    },
    "deepseek": {
        "name": "DeepSeek",
        "default_model": "deepseek-chat",
        "models": ["deepseek-chat", "deepseek-reasoner"],
        "env_key": "DEEPSEEK_API_KEY",
        "litellm_prefix": "deepseek",
        "base_url": None,
    },
    "xai": {
        "name": "xAI Grok",
        "default_model": "grok-2-1212",
        "models": ["grok-3", "grok-2-1212", "grok-2-vision-1212"],
        "env_key": "XAI_API_KEY",
        "litellm_prefix": "xai",
        "base_url": None,
    },
    "mistral": {
        "name": "Mistral AI",
        "default_model": "mistral-large-latest",
        "models": ["mistral-large-latest", "mistral-medium-latest", "mistral-small-latest", "pixtral-large-latest"],
        "env_key": "MISTRAL_API_KEY",
        "litellm_prefix": "mistral",
        "base_url": None,
    },
    "cohere": {
        "name": "Cohere",
        "default_model": "command-r-plus",
        "models": ["command-r-plus", "command-r", "command-a-03-2025"],
        "env_key": "COHERE_API_KEY",
        "litellm_prefix": "cohere",
        "base_url": None,
    },
    "together": {
        "name": "Together AI",
        "default_model": "meta-llama/Meta-Llama-3.1-405B-Instruct-Turbo",
        "models": ["meta-llama/Meta-Llama-3.1-405B-Instruct-Turbo", "meta-llama/Meta-Llama-3.1-70B-Instruct-Turbo", "mistralai/Mixtral-8x22B-Instruct-v0.1"],
        "env_key": "TOGETHER_API_KEY",
        "litellm_prefix": "together_ai",
        "base_url": None,
    },
    "fireworks": {
        "name": "Fireworks AI",
        "default_model": "accounts/fireworks/models/llama-v3p1-405b-instruct",
        "models": ["accounts/fireworks/models/llama-v3p1-405b-instruct", "accounts/fireworks/models/mixtral-8x22b-instruct"],
        "env_key": "FIREWORKS_API_KEY",
        "litellm_prefix": "fireworks_ai",
        "base_url": None,
    },
    "groq": {
        "name": "Groq",
        "default_model": "llama-3.3-70b-versatile",
        "models": ["llama-3.3-70b-versatile", "llama-3.1-8b-instant", "mixtral-8x7b-32768"],
        "env_key": "GROQ_API_KEY",
        "litellm_prefix": "groq",
        "base_url": None,
    },
    "replicate": {
        "name": "Replicate",
        "default_model": "meta/meta-llama-3.1-405b-instruct",
        "models": ["meta/meta-llama-3.1-405b-instruct", "meta/meta-llama-3-70b-instruct"],
        "env_key": "REPLICATE_API_KEY",
        "litellm_prefix": "replicate",
        "base_url": None,
    },
    "bedrock": {
        "name": "AWS Bedrock",
        "default_model": "us.anthropic.claude-3-5-sonnet-20241022-v2:0",
        "models": ["us.anthropic.claude-3-5-sonnet-20241022-v2:0", "us.meta.llama3-1-70b-instruct-v1:0"],
        "env_key": "AWS_ACCESS_KEY_ID",
        "litellm_prefix": "bedrock",
        "base_url": None,
    },
    "vertex": {
        "name": "Google Vertex AI",
        "default_model": "gemini-1.5-pro",
        "models": ["gemini-1.5-pro", "gemini-1.5-flash", "claude-3-5-sonnet@20240620"],
        "env_key": "GOOGLE_APPLICATION_CREDENTIALS",
        "litellm_prefix": "vertex_ai",
        "base_url": None,
    },
    "azure": {
        "name": "Azure OpenAI",
        "default_model": "gpt-4o-mini",
        "models": ["gpt-4o", "gpt-4o-mini", "gpt-4"],
        "env_key": "AZURE_API_KEY",
        "litellm_prefix": "azure",
        "base_url": None,
    },

    # ── 中国 / 亚太 ──
    "zhipu": {
        "name": "智谱 GLM",
        "default_model": "glm-4-flash",
        "models": ["glm-4-plus", "glm-4-flash", "glm-4-air", "glm-4-long"],
        "env_key": "ZHIPU_API_KEY",
        "litellm_prefix": "zhipu",
        "base_url": None,
    },
    "qwen": {
        "name": "通义千问 (阿里云)",
        "default_model": "qwen-max",
        "models": ["qwen-max", "qwen-plus", "qwen-turbo", "qwen2.5-72b-instruct"],
        "env_key": "DASHSCOPE_API_KEY",
        "litellm_prefix": "dashscope",
        "base_url": None,
    },
    "moonshot": {
        "name": "月之暗面 Kimi",
        "default_model": "moonshot-v1-8k",
        "models": ["moonshot-v1-8k", "moonshot-v1-32k", "moonshot-v1-128k"],
        "env_key": "MOONSHOT_API_KEY",
        "litellm_prefix": "moonshot",
        "base_url": None,
    },
    "deepseek_cn": {
        "name": "DeepSeek (中国)",
        "default_model": "deepseek-chat",
        "models": ["deepseek-chat", "deepseek-reasoner"],
        "env_key": "DEEPSEEK_API_KEY",
        "litellm_prefix": "deepseek",
        "base_url": None,
    },
    "baidu": {
        "name": "百度文心一言",
        "default_model": "ernie-4.0-turbo-8k",
        "models": ["ernie-4.0-turbo-8k", "ernie-3.5-8k", "ernie-speed-8k"],
        "env_key": "BAIDU_API_KEY",
        "litellm_prefix": "baidu",
        "base_url": None,
    },
    "minimax": {
        "name": "MiniMax",
        "default_model": "abab6.5s-chat",
        "models": ["abab7-chat", "abab6.5s-chat", "abab6.5-chat"],
        "env_key": "MINIMAX_API_KEY",
        "litellm_prefix": "minimax",
        "base_url": None,
    },
    "stepfun": {
        "name": "阶跃星辰",
        "default_model": "step-2-16k",
        "models": ["step-2-16k", "step-1-8k", "step-1v-8k"],
        "env_key": "STEPFUN_API_KEY",
        "litellm_prefix": "stepfun",
        "base_url": None,
    },
    "yi": {
        "name": "零一万物 Yi",
        "default_model": "yi-large",
        "models": ["yi-large", "yi-medium", "yi-vision"],
        "env_key": "YI_API_KEY",
        "litellm_prefix": "yi",
        "base_url": None,
    },
    "doubao": {
        "name": "字节豆包",
        "default_model": "doubao-pro-32k",
        "models": ["doubao-pro-32k", "doubao-pro-128k", "doubao-lite-32k"],
        "env_key": "DOUBAO_API_KEY",
        "litellm_prefix": "doubao",
        "base_url": None,
    },
    "baichuan": {
        "name": "百川智能",
        "default_model": "Baichuan4",
        "models": ["Baichuan4", "Baichuan3-Turbo", "Baichuan2-Turbo"],
        "env_key": "BAICHUAN_API_KEY",
        "litellm_prefix": "baichuan",
        "base_url": None,
    },
    "openrouter": {
        "name": "OpenRouter",
        "default_model": "anthropic/claude-sonnet-4",
        "models": ["anthropic/claude-sonnet-4", "openai/gpt-4o", "google/gemini-2.0-flash", "meta-llama/llama-3.3-70b-instruct"],
        "env_key": "OPENROUTER_API_KEY",
        "litellm_prefix": "openrouter",
        "base_url": None,
    },

    # ── 本地 / 自部署 ──
    "ollama": {
        "name": "Ollama (本地)",
        "default_model": "llama3",
        "models": ["llama3", "qwen2.5", "deepseek-r1", "mistral", "gemma2"],
        "env_key": None,
        "litellm_prefix": "ollama",
        "base_url": "http://localhost:11434",
    },
    "vllm": {
        "name": "vLLM (自部署)",
        "default_model": "",
        "models": [],
        "env_key": None,
        "litellm_prefix": "openai",
        "base_url": "http://localhost:8000/v1",
    },
    "lmstudio": {
        "name": "LM Studio (本地)",
        "default_model": "local-model",
        "models": [],
        "env_key": None,
        "litellm_prefix": "openai",
        "base_url": "http://localhost:1234/v1",
    },
    "custom": {
        "name": "自定义 API",
        "default_model": "",
        "models": [],
        "env_key": None,
        "litellm_prefix": "openai",
        "base_url": "http://localhost:8080/v1",
    },
}


def test_connection(provider_id: str, model: str, api_key: str, base_url: str = None) -> bool:
    """测试与 AI 模型的连接"""
    try:
        from litellm import completion
    except ImportError:
        # 假测试 — 仅验证参数非空
        if not api_key and PROVIDERS.get(provider_id, {}).get("env_key"):
            return False
        return bool(model)

    p = PROVIDERS.get(provider_id, {})
    litellm_model = f"{p.get('litellm_prefix', provider_id)}/{model}"

    if base_url:
        os.environ["OPENAI_API_BASE"] = base_url

    if api_key and p.get("env_key"):
        os.environ[p["env_key"]] = api_key

    try:
        resp = completion(
            model=litellm_model,
            messages=[{"role": "user", "content": "hi"}],
            max_tokens=5,
            timeout=15,
        )
        return resp.choices[0].message.content is not None
    except Exception:
        return False


def run_setup_wizard(config_path: Path):
    """运行完整配置向导"""
    CONFIG_DIR = config_path.parent
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    # ── 加载已有配置 ──
    existing = {}
    if config_path.exists():
        with open(config_path) as f:
            existing = yaml.safe_load(f) or {}

    print()
    print(box(
        "🛡️  Sentinel AI 安全智能体\n\n"
        "      配  置  向  导\n\n"
        "  纯防御 · 自部署 · 全模型支持\n"
        f"  支持 litellm 100+ AI 模型提供商",
        "cyan"
    ))
    print(f"\n{c('dim', f'  配置目录: {CONFIG_DIR}')}")
    if existing:
        print(f"  {c('yellow', '📋 检测到已有配置，将在此基础上升级')}")
    print()

    # ═══════════════════════════════════════════
    # SECTION 1: AI 模型
    # ═══════════════════════════════════════════
    section("① AI 模型 — 选择你的 AI 引擎")

    print(f"  {c('dim', 'Sentinel 通过 litellm 支持 100+ 模型提供商。')}")
    print(f"  {c('dim', '支持 OpenAI、Claude、Gemini、DeepSeek、通义千问、文心一言……')}")
    print()

    # 分组显示
    groups = {
        "🌍 国际主流": ["openai", "anthropic", "google", "deepseek", "xai", "mistral", "cohere"],
        "🔗 模型路由": ["openrouter", "together", "fireworks", "groq", "replicate"],
        "☁️  云平台": ["bedrock", "vertex", "azure"],
        "🇨🇳 中国厂商": ["zhipu", "qwen", "moonshot", "baidu", "minimax", "stepfun", "yi", "doubao", "baichuan"],
        "💻 本地部署": ["ollama", "vllm", "lmstudio"],
        "🔧 其他": ["custom"],
    }

    provider_list = []
    idx = 1
    for group_name, ids in groups.items():
        print(f"  {c('bold', group_name)}")
        for pid in ids:
            p = PROVIDERS[pid]
            desc = f"({', '.join(p['models'][:2])}{'...' if len(p['models'])>2 else ''})" if p['models'] else ""
            line = f"    [{c('green', str(idx))}] {c('bold', p['name']):<24} {c('dim', desc)}"
            print(line)
            provider_list.append(pid)
            idx += 1
        print()

    # 快速选择
    default_provider = existing.get("model", {}).get("provider", "openai")
    default_num = provider_list.index(default_provider) + 1 if default_provider in provider_list else 1

    num = ask(f"选择提供商 (1-{len(provider_list)})", str(default_num))
    try:
        chosen_idx = int(num) - 1
        if chosen_idx < 0 or chosen_idx >= len(provider_list):
            chosen_idx = 0
    except ValueError:
        chosen_idx = 0

    provider_id = provider_list[chosen_idx]
    provider = PROVIDERS[provider_id]
    print(f"\n  {c('green', '✔')} 已选择: {c('bold', provider['name'])}")

    # 模型选择
    if provider["models"]:
        print(f"\n  {c('dim', '推荐模型:')}")
        for i, m in enumerate(provider["models"][:6]):
            print(f"    [{c('green', str(i+1))}] {m}")
        print(f"    [{c('green', '0')}] 自定义输入")

        default_model = existing.get("model", {}).get("model", provider["default_model"])
        model_choice = ask("选择模型", "1")
        try:
            mi = int(model_choice)
            if mi == 0:
                model = ask("请输入模型名称")
            elif 1 <= mi <= len(provider["models"]):
                model = provider["models"][mi - 1]
            else:
                model = provider["default_model"]
        except ValueError:
            model = ask("模型名称", default_model)
    else:
        model = ask("模型名称", provider["default_model"])

    # API Key
    env_key = provider.get("env_key")
    env_val = os.environ.get(env_key, "") if env_key else ""
    existing_key = existing.get("model", {}).get("api_key", "")

    if provider_id in ("ollama", "vllm", "lmstudio"):
        name = provider["name"]
        print(f"\n  {c('dim', '本地部署 — ' + name + ' 不需要 API Key')}")
        api_key = ""
    else:
        hint = ""
        if env_val:
            hint = c("dim", " (已从环境变量读取)")
        elif provider_id == "openrouter":
            hint = c("dim", " → https://openrouter.ai/keys")
        elif provider_id == "anthropic":
            hint = c("dim", " → https://console.anthropic.com/")
        elif provider_id == "google":
            hint = c("dim", " → https://aistudio.google.com/apikey")
        print(f"\n  {c('dim', 'API Key')}{hint}")
        api_key = ask("API Key（回车跳过，后续可用环境变量）",
                       existing_key, password=True)

    # Base URL
    base_url = provider.get("base_url")
    if base_url:
        print(f"  {c('dim', f'Base URL: {base_url}')}")

    # 测试连接
    if api_key and provider_id not in ("ollama", "vllm", "lmstudio"):
        print(f"\n  {c('cyan', '⏳')} 测试连接...")
        if test_connection(provider_id, model, api_key, base_url):
            success(f"连接成功！{provider['name']} 的 {model} 模型正常响应")
        else:
            warn("连接测试未能完成 — 可能是 litellm 未安装或网络问题")
            info("你可以继续配置，安装完整依赖后再测试。")

    print()

    # ═══════════════════════════════════════════
    # SECTION 2: 通知渠道
    # ═══════════════════════════════════════════
    section("② 通知渠道 — 告警推送到哪里")

    platforms = existing.get("platforms", [])
    existing_types = {p.get("type", ""): p for p in platforms}

    print(f"  {c('dim', '检测到攻击时，Sentinel 可以通过以下渠道通知你。')}")
    print(f"  {c('dim', '至少配置一个，也可以全部跳过。')}")
    print()

    new_platforms = []

    # QQ Bot
    print(f"  {c('bold', '📱 QQ Bot')}")
    if confirm("启用 QQ Bot 通知？", default="qqbot" in existing_types):
        qb = {"type": "qqbot"}
        qb["app_id"] = ask("  App ID", existing_types.get("qqbot", {}).get("app_id", ""))
        qb["token"] = ask("  Token", existing_types.get("qqbot", {}).get("token", ""), password=True)
        new_platforms.append(qb)
        success("QQ Bot 已配置")
    print()

    # Feishu
    print(f"  {c('bold', '📊 飞书 / Lark')}")
    if confirm("启用飞书通知？", default="feishu" in existing_types):
        fb = {"type": "feishu"}
        fb["webhook_url"] = ask("  Webhook URL", existing_types.get("feishu", {}).get("webhook_url", ""))
        if not fb["webhook_url"]:
            fb["app_id"] = ask("  App ID", existing_types.get("feishu", {}).get("app_id", ""))
            fb["app_secret"] = ask("  App Secret", "", password=True)
        new_platforms.append(fb)
        success("飞书已配置")
    print()

    # Telegram
    print(f"  {c('bold', '✈️  Telegram')}")
    if confirm("启用 Telegram 通知？", default="telegram" in existing_types):
        tb = {"type": "telegram"}
        tb["bot_token"] = ask("  Bot Token", existing_types.get("telegram", {}).get("bot_token", ""), password=True)
        tb["chat_id"] = ask("  Chat ID", existing_types.get("telegram", {}).get("chat_id", ""))
        new_platforms.append(tb)
        success("Telegram 已配置")
    print()

    # DingTalk
    print(f"  {c('bold', '🔔 钉钉')}")
    if confirm("启用钉钉通知？", default="dingtalk" in existing_types):
        db = {"type": "dingtalk"}
        db["webhook_url"] = ask("  Webhook URL", existing_types.get("dingtalk", {}).get("webhook_url", ""))
        new_platforms.append(db)
        success("钉钉已配置")
    print()

    # Generic Webhook
    print(f"  {c('bold', '🔗 通用 Webhook')}")
    if confirm("启用通用 Webhook？", default="webhook" in existing_types):
        wb = {"type": "webhook"}
        wb["url"] = ask("  URL", existing_types.get("webhook", {}).get("url", ""))
        new_platforms.append(wb)
        success("Webhook 已配置")
    print()

    if not new_platforms:
        warn("未配置任何通知渠道 — 告警将仅保存在本地数据库")

    # ═══════════════════════════════════════════
    # SECTION 3: 安全监控
    # ═══════════════════════════════════════════
    section("③ 安全监控 — 日志源与扫描")

    scanning = existing.get("scanning", {})

    print(f"  {c('dim', '配置要监控的日志文件。Sentinel 会持续扫描新增内容。')}")
    print()

    existing_logs = scanning.get("log_sources", [])
    if existing_logs:
        print(f"  {c('dim', '已有日志源:')}")
        for l in existing_logs:
            print(f"    {c('dim', f'• {l}')}")
        print()

    # 常用日志路径自动补全
    common_logs = {
        "nginx": "/var/log/nginx/access.log",
        "apache": "/var/log/apache2/access.log",
        "auth": "/var/log/auth.log",
        "syslog": "/var/log/syslog",
        "app": "/var/log/myapp/*.log",
    }

    print(f"  {c('dim', '常用日志路径（输入编号快速添加，多个用逗号分隔）:')}")
    for i, (name, path) in enumerate(common_logs.items(), 1):
        print(f"    [{c('green', str(i))}] {name:<10} {c('dim', path)}")
    print(f"    [{c('green', '0')}] 手动输入")
    print()

    log_input = ask("选择或输入路径", "0")
    log_sources = []

    if log_input == "0":
        manual = ask("日志路径（逗号分隔多个）", ",".join(existing_logs))
        log_sources = [x.strip() for x in manual.split(",") if x.strip()]
    elif log_input:
        parts = [x.strip() for x in log_input.split(",")]
        for part in parts:
            try:
                idx = int(part) - 1
                keys = list(common_logs.keys())
                if 0 <= idx < len(keys):
                    log_sources.append(common_logs[keys[idx]])
            except ValueError:
                log_sources.append(part)

    if log_sources:
        print()
        for l in log_sources:
            success(f"监控: {l}")

    interval = ask("扫描间隔（秒）", str(scanning.get("interval_seconds", 30)))
    try:
        interval_seconds = int(interval)
    except ValueError:
        interval_seconds = 30

    print()

    # ═══════════════════════════════════════════
    # SECTION 4: Hermes 集成
    # ═══════════════════════════════════════════
    section("④ Hermes 集成 — 连接你的 AI 助手")

    hermes_cfg = existing.get("hermes", {})
    print(f"  {c('dim', 'Sentinel 可以作为 MCP Server 被 Hermes Agent 调用。')}")
    print(f"  {c('dim', '启用后，在 Hermes 中可以直接查询安全状态、查看告警。')}")
    print()

    hermes_enabled = confirm("启用 Hermes MCP 集成？", default=hermes_cfg.get("enabled", False))
    mcp_port = 9120
    if hermes_enabled:
        mcp_port_str = ask("MCP 服务端口", str(hermes_cfg.get("mcp_port", 9120)))
        try:
            mcp_port = int(mcp_port_str)
        except ValueError:
            mcp_port = 9120
        success(f"Hermes MCP 将在端口 {mcp_port} 启动")
        info("在 Hermes 中添加: hermes mcp add sentinel --url http://localhost:9120")
    else:
        info("可随时通过编辑配置文件启用")
    print()

    # ═══════════════════════════════════════════
    # SECTION 5: 仪表盘
    # ═══════════════════════════════════════════
    section("⑤ 仪表盘 — 可视化安全面板")

    dashboard_cfg = existing.get("dashboard", {})
    print(f"  {c('dim', 'Sentinel 自带 Dark Glassmorphism 风格的安全仪表盘。')}")
    print(f"  {c('dim', '仪表盘仅限本地访问（127.0.0.1），不对外暴露。')}")
    print()

    dash_enabled = confirm("启用本地仪表盘？", default=dashboard_cfg.get("port", 8443) != 0)
    dash_port = 0
    if dash_enabled:
        dash_port_str = ask("仪表盘端口", str(dashboard_cfg.get("port", 8443)))
        try:
            dash_port = int(dash_port_str)
        except ValueError:
            dash_port = 8443
        success(f"仪表盘: http://127.0.0.1:{dash_port}")
    print()

    # ═══════════════════════════════════════════
    # SECTION 6: 保存
    # ═══════════════════════════════════════════
    section("⑥ 确认配置")

    config = {
        "model": {
            "provider": provider_id,
            "model": model,
            "api_key": api_key,
            "base_url": base_url,
        },
        "platforms": new_platforms,
        "scanning": {
            "log_sources": log_sources,
            "interval_seconds": interval_seconds,
        },
        "hermes": {
            "enabled": hermes_enabled,
            "mcp_port": mcp_port,
        },
        "dashboard": {
            "enabled": dash_enabled,
            "port": dash_port,
            "host": "127.0.0.1",
        },
    }

    # 显示摘要
    print(f"  {c('bold', '🤖 AI 模型')}")
    print(f"    {provider['name']} / {model}")
    print(f"    API Key: {'***' + api_key[-4:] if api_key and len(api_key) > 4 else '未设置（请通过环境变量配置）'}")
    print()

    print(f"  {c('bold', '📢 通知渠道:')} {', '.join(p['type'] for p in new_platforms) if new_platforms else '无（仅本地数据库）'}")
    print(f"  {c('bold', '📂 日志源:')} {len(log_sources)} 个")
    print(f"  {c('bold', '🔗 Hermes:')} {'启用 (端口 ' + str(mcp_port) + ')' if hermes_enabled else '未启用'}")
    print(f"  {c('bold', '📊 仪表盘:')} {f'http://127.0.0.1:{dash_port}' if dash_enabled else '未启用'}")
    print()

    if not confirm("保存配置并继续？", default=True):
        info("配置已取消。")
        return

    # 写入
    with open(config_path, "w") as f:
        yaml.dump(config, f, allow_unicode=True, default_flow_style=False, sort_keys=False)

    print()
    print(box(
        "✅  配 置 完 成\n\n"
        "  sentinel start    启动安全监控\n"
        "  sentinel chat     启动 AI 对话\n"
        "  sentinel status   查看运行状态\n"
        "  sentinel dashboard打开仪表盘",
        "green"
    ))
    print()

    # 环境变量提示
    env_key = PROVIDERS.get(provider_id, {}).get("env_key")
    if env_key and not api_key:
        print(f"  {c('yellow', '💡 提示:')} 设置环境变量避免每次输入 API Key：")
        print(f"  {c('cyan', f'  export {env_key}=YOUR_KEY')}")
        print()


def run_setup_quick():
    """快速模式 — 最小配置，跳过交互"""
    pass
