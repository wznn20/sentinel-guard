from __future__ import annotations

import os
import shutil
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import yaml

from .config import KXConfig


C = {
    "reset": "\033[0m",
    "bold": "\033[1m",
    "dim": "\033[2m",
    "cyan": "\033[36m",
    "green": "\033[32m",
    "yellow": "\033[33m",
    "red": "\033[31m",
}


def c(color: str, text: str) -> str:
    return f"{C.get(color, '')}{text}{C['reset']}"


def box(text: str, color: str = "cyan") -> str:
    lines = text.strip().split("\n")
    width = max(len(line) for line in lines) + 4
    top = f"╭{'─' * width}╮"
    mid = "\n".join(f"│  {line}{' ' * (width - len(line) - 2)}│" for line in lines)
    bottom = f"╰{'─' * width}╯"
    return c(color, f"{top}\n{mid}\n{bottom}")


def section(title: str) -> None:
    print(f"\n{c('cyan', '━━━')} {c('bold', title)} {c('cyan', '━━━')}\n")


def ask(prompt: str, default: str = "", password: bool = False) -> str:
    suffix = c("dim", f" [{default}]") if default else ""
    label = f"  {prompt}{suffix}: "
    if password:
        import getpass

        value = getpass.getpass(label)
    else:
        value = input(label).strip()
    return value if value else default


def confirm(prompt: str, default: bool = True) -> bool:
    yn = "Y/n" if default else "y/N"
    raw = input(f"  {prompt} [{yn}]: ").strip().lower()
    if not raw:
        return default
    return raw in {"y", "yes"}


def test_connection(provider_id: str, model: str, api_key: str, base_url: str | None = None) -> bool:
    try:
        from litellm import completion
    except Exception:
        if provider_id in {"ollama", "lmstudio"}:
            return bool(model)
        return bool(model and (api_key or PROVIDERS.get(provider_id, {}).get("api_key_env")))

    provider = PROVIDERS.get(provider_id, {})
    prefix = provider.get("litellm_prefix", provider_id)
    litellm_model = f"{prefix}/{model}" if prefix else model
    kwargs: dict[str, Any] = {
        "model": litellm_model,
        "messages": [{"role": "user", "content": "ping"}],
        "max_tokens": 8,
        "timeout": 15,
    }
    if api_key:
        kwargs["api_key"] = api_key
    if base_url:
        kwargs["base_url"] = base_url
    try:
        response = completion(**kwargs)
        return bool(response.choices[0].message.content)
    except Exception:
        return False


PROVIDERS: dict[str, dict[str, Any]] = {
    "openai": {
        "name": "OpenAI",
        "default_model": "gpt-4o-mini",
        "models": ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "o3-mini", "o1-mini"],
        "api_key_env": "OPENAI_API_KEY",
        "litellm_prefix": "openai",
        "base_url": "",
    },
    "anthropic": {
        "name": "Anthropic Claude",
        "default_model": "claude-sonnet-4-20250514",
        "models": ["claude-sonnet-4-20250514", "claude-opus-4-20250514", "claude-3-5-sonnet-20241022"],
        "api_key_env": "ANTHROPIC_API_KEY",
        "litellm_prefix": "anthropic",
        "base_url": "",
    },
    "google": {
        "name": "Google Gemini",
        "default_model": "gemini-2.0-flash",
        "models": ["gemini-2.5-pro", "gemini-2.0-flash", "gemini-1.5-pro", "gemini-1.5-flash"],
        "api_key_env": "GEMINI_API_KEY",
        "litellm_prefix": "gemini",
        "base_url": "",
    },
    "deepseek": {
        "name": "DeepSeek",
        "default_model": "deepseek-chat",
        "models": ["deepseek-chat", "deepseek-reasoner"],
        "api_key_env": "DEEPSEEK_API_KEY",
        "litellm_prefix": "deepseek",
        "base_url": "",
    },
    "xai": {
        "name": "xAI Grok",
        "default_model": "grok-2-1212",
        "models": ["grok-3", "grok-2-1212"],
        "api_key_env": "XAI_API_KEY",
        "litellm_prefix": "xai",
        "base_url": "",
    },
    "mistral": {
        "name": "Mistral",
        "default_model": "mistral-large-latest",
        "models": ["mistral-large-latest", "mistral-medium-latest", "mistral-small-latest"],
        "api_key_env": "MISTRAL_API_KEY",
        "litellm_prefix": "mistral",
        "base_url": "",
    },
    "cohere": {
        "name": "Cohere",
        "default_model": "command-r-plus",
        "models": ["command-r-plus", "command-r"],
        "api_key_env": "COHERE_API_KEY",
        "litellm_prefix": "cohere",
        "base_url": "",
    },
    "groq": {
        "name": "Groq",
        "default_model": "llama-3.3-70b-versatile",
        "models": ["llama-3.3-70b-versatile", "llama-3.1-8b-instant"],
        "api_key_env": "GROQ_API_KEY",
        "litellm_prefix": "groq",
        "base_url": "",
    },
    "openrouter": {
        "name": "OpenRouter",
        "default_model": "anthropic/claude-sonnet-4",
        "models": ["anthropic/claude-sonnet-4", "openai/gpt-4o", "google/gemini-2.0-flash"],
        "api_key_env": "OPENROUTER_API_KEY",
        "litellm_prefix": "openrouter",
        "base_url": "",
    },
    "azure": {
        "name": "Azure OpenAI",
        "default_model": "gpt-4o-mini",
        "models": ["gpt-4o", "gpt-4o-mini", "gpt-4"],
        "api_key_env": "AZURE_API_KEY",
        "litellm_prefix": "azure",
        "base_url": "",
    },
    "bedrock": {
        "name": "AWS Bedrock",
        "default_model": "us.anthropic.claude-3-5-sonnet-20241022-v2:0",
        "models": ["us.anthropic.claude-3-5-sonnet-20241022-v2:0", "us.meta.llama3-1-70b-instruct-v1:0"],
        "api_key_env": "AWS_ACCESS_KEY_ID",
        "litellm_prefix": "bedrock",
        "base_url": "",
    },
    "vertex": {
        "name": "Google Vertex AI",
        "default_model": "gemini-1.5-pro",
        "models": ["gemini-1.5-pro", "gemini-1.5-flash"],
        "api_key_env": "GOOGLE_APPLICATION_CREDENTIALS",
        "litellm_prefix": "vertex_ai",
        "base_url": "",
    },
    "zhipu": {
        "name": "智谱 GLM",
        "default_model": "glm-4-flash",
        "models": ["glm-4-plus", "glm-4-flash", "glm-4-air"],
        "api_key_env": "ZHIPU_API_KEY",
        "litellm_prefix": "zhipu",
        "base_url": "",
    },
    "qwen": {
        "name": "通义千问",
        "default_model": "qwen-max",
        "models": ["qwen-max", "qwen-plus", "qwen-turbo"],
        "api_key_env": "DASHSCOPE_API_KEY",
        "litellm_prefix": "dashscope",
        "base_url": "",
    },
    "moonshot": {
        "name": "Moonshot Kimi",
        "default_model": "moonshot-v1-8k",
        "models": ["moonshot-v1-8k", "moonshot-v1-32k", "moonshot-v1-128k"],
        "api_key_env": "MOONSHOT_API_KEY",
        "litellm_prefix": "moonshot",
        "base_url": "",
    },
    "baidu": {
        "name": "百度文心",
        "default_model": "ernie-4.0-turbo-8k",
        "models": ["ernie-4.0-turbo-8k", "ernie-3.5-8k"],
        "api_key_env": "BAIDU_API_KEY",
        "litellm_prefix": "baidu",
        "base_url": "",
    },
    "minimax": {
        "name": "MiniMax",
        "default_model": "abab6.5s-chat",
        "models": ["abab7-chat", "abab6.5s-chat"],
        "api_key_env": "MINIMAX_API_KEY",
        "litellm_prefix": "minimax",
        "base_url": "",
    },
    "stepfun": {
        "name": "阶跃星辰",
        "default_model": "step-2-16k",
        "models": ["step-2-16k", "step-1-8k"],
        "api_key_env": "STEPFUN_API_KEY",
        "litellm_prefix": "stepfun",
        "base_url": "",
    },
    "yi": {
        "name": "零一万物 Yi",
        "default_model": "yi-large",
        "models": ["yi-large", "yi-medium"],
        "api_key_env": "YI_API_KEY",
        "litellm_prefix": "yi",
        "base_url": "",
    },
    "doubao": {
        "name": "字节豆包",
        "default_model": "doubao-pro-32k",
        "models": ["doubao-pro-32k", "doubao-pro-128k"],
        "api_key_env": "DOUBAO_API_KEY",
        "litellm_prefix": "doubao",
        "base_url": "",
    },
    "baichuan": {
        "name": "百川",
        "default_model": "Baichuan4",
        "models": ["Baichuan4", "Baichuan3-Turbo"],
        "api_key_env": "BAICHUAN_API_KEY",
        "litellm_prefix": "baichuan",
        "base_url": "",
    },
    "ollama": {
        "name": "Ollama",
        "default_model": "llama3.2",
        "models": ["llama3.2", "qwen2.5", "deepseek-r1", "mistral"],
        "api_key_env": None,
        "litellm_prefix": "ollama",
        "base_url": "http://localhost:11434",
    },
    "vllm": {
        "name": "vLLM / OpenAI Compatible",
        "default_model": "",
        "models": [],
        "api_key_env": "OPENAI_API_KEY",
        "litellm_prefix": "openai",
        "base_url": "http://localhost:8000/v1",
    },
    "lmstudio": {
        "name": "LM Studio",
        "default_model": "local-model",
        "models": [],
        "api_key_env": None,
        "litellm_prefix": "openai",
        "base_url": "http://localhost:1234/v1",
    },
    "custom": {
        "name": "自定义第三方 API",
        "default_model": "",
        "models": [],
        "api_key_env": "OPENAI_API_KEY",
        "litellm_prefix": "openai",
        "base_url": "http://localhost:8080/v1",
    },
}


PROVIDER_GROUPS: dict[str, list[str]] = {
    "🌍 国际主流": ["openai", "anthropic", "google", "deepseek", "xai", "mistral", "cohere", "groq"],
    "🔗 模型路由": ["openrouter", "azure", "bedrock", "vertex"],
    "🇨🇳 国内主流": ["zhipu", "qwen", "moonshot", "baidu", "minimax", "stepfun", "yi", "doubao", "baichuan"],
    "💻 本地 / 自部署": ["ollama", "vllm", "lmstudio", "custom"],
}


def _print_header(config_path: Path, has_existing: bool) -> None:
    print()
    print(
        box(
            "KX Agent\n\n"
            "交互式配置向导\n\n"
            "参考 Hermes setup 设计\n"
            "支持第三方 API 与主流大模型提供商",
            "cyan",
        )
    )
    print(f"\n{c('dim', f'  配置文件: {config_path}')}")
    if has_existing:
        print(f"  {c('yellow', '检测到已有配置，将在此基础上更新')}")
    print()


def _choose_provider(existing_provider: str) -> str:
    section("① 模型提供商")
    print(f"  {c('dim', 'KX 使用 litellm 风格 provider/model 配置。')}")
    print(f"  {c('dim', '支持 OpenAI、Claude、Gemini、DeepSeek、OpenRouter、国内大模型、Ollama、自定义兼容 API。')}\n")
    provider_list: list[str] = []
    idx = 1
    for group_name, ids in PROVIDER_GROUPS.items():
        print(f"  {c('bold', group_name)}")
        for pid in ids:
            p = PROVIDERS[pid]
            desc = f"({', '.join(p['models'][:2])}{'...' if len(p['models']) > 2 else ''})" if p["models"] else ""
            print(f"    [{c('green', str(idx))}] {c('bold', p['name']):<24} {c('dim', desc)}")
            provider_list.append(pid)
            idx += 1
        print()
    default_idx = provider_list.index(existing_provider) + 1 if existing_provider in provider_list else 1
    raw = ask(f"选择提供商 (1-{len(provider_list)})", str(default_idx))
    try:
        chosen = int(raw) - 1
    except ValueError:
        chosen = default_idx - 1
    if chosen < 0 or chosen >= len(provider_list):
        chosen = default_idx - 1
    provider_id = provider_list[chosen]
    print(f"\n  {c('green', '✔')} 已选择: {c('bold', PROVIDERS[provider_id]['name'])}")
    return provider_id


def _choose_model(provider_id: str, existing_model: str) -> str:
    provider = PROVIDERS[provider_id]
    models = provider["models"]
    section("② 模型名称")
    if models:
        print(f"  {c('dim', '推荐模型:')}")
        for i, model in enumerate(models[:8], 1):
            print(f"    [{c('green', str(i))}] {model}")
        print(f"    [{c('green', '0')}] 自定义输入\n")
        choice = ask("选择模型", "1")
        try:
            number = int(choice)
        except ValueError:
            number = -1
        if number == 0:
            return ask("输入模型名称", existing_model or provider["default_model"])
        if 1 <= number <= len(models[:8]):
            return models[number - 1]
    return ask("模型名称", existing_model or provider["default_model"])


def _collect_model_config(existing: dict[str, Any]) -> dict[str, Any]:
    model_existing = existing.get("model") or {}
    provider_id = _choose_provider(str(model_existing.get("provider", "openai")))
    provider = PROVIDERS[provider_id]
    model_name = _choose_model(provider_id, str(model_existing.get("model", "")))
    section("③ API 与 Endpoint")
    env_key = provider.get("api_key_env")
    env_val = os.getenv(env_key, "") if env_key else ""
    existing_key = str(model_existing.get("api_key", ""))
    if env_key:
        hint = c("dim", f" 环境变量: {env_key}")
        if env_val:
            hint += c("dim", " (当前 shell 已设置)")
        print(f"  {hint}")
    local_provider = provider_id in {"ollama", "lmstudio"}
    if local_provider:
        api_key = ""
        print(f"  {c('dim', '该提供商通常不需要 API Key。')}")
    else:
        api_key = ask("API Key（可回车留空，后续走环境变量）", existing_key, password=True)
    default_base = str(model_existing.get("base_url", provider.get("base_url") or "") or "")
    base_url = ask("Base URL（留空使用官方默认）", default_base)
    temperature = ask("Temperature", str(model_existing.get("temperature", 0.2)))
    max_tokens = ask("Max tokens", str(model_existing.get("max_tokens", 2048)))
    try:
        temperature_value = float(temperature)
    except ValueError:
        temperature_value = 0.2
    try:
        max_tokens_value = int(max_tokens)
    except ValueError:
        max_tokens_value = 2048
    if model_name:
        print()
        if confirm("测试模型连通性？", True):
            print(f"  {c('cyan', '测试中...')}")
            if test_connection(provider_id, model_name, api_key, base_url or None):
                print(f"  {c('green', '连接成功')}")
            else:
                print(f"  {c('yellow', '连接失败或当前环境无法直连，仍会保存配置')}")
    return {
        "provider": provider_id,
        "litellm_prefix": provider.get("litellm_prefix", provider_id),
        "model": model_name,
        "api_key": api_key,
        "api_key_env": env_key,
        "base_url": base_url or None,
        "temperature": temperature_value,
        "max_tokens": max_tokens_value,
    }


def _collect_workspace_config(existing: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    workspace_existing = existing.get("workspace") or {}
    memory_existing = existing.get("memory") or {}
    section("④ 工作区与记忆")
    root = ask("Workspace root", str(workspace_existing.get("root", ".")))
    allow_raw = ask(
        "Allow roots（逗号分隔）",
        ",".join(workspace_existing.get("allow_roots", [root or "."])),
    )
    db_path = ask("SQLite db path", str(memory_existing.get("db_path", "~/.kx/kx.sqlite")))
    return (
        {
            "root": root,
            "allow_roots": [item.strip() for item in allow_raw.split(",") if item.strip()],
        },
        {
            "db_path": db_path,
            "recent_turns": int(memory_existing.get("recent_turns", 12)),
            "summary_trigger": int(memory_existing.get("summary_trigger", 20)),
            "summary_window": int(memory_existing.get("summary_window", 8)),
            "retrieval_limit": int(memory_existing.get("retrieval_limit", 6)),
        },
    )


def _collect_gateway_config(existing: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    gateway_existing = existing.get("gateway") or {}
    delivery_existing = existing.get("delivery") or {}
    section("⑤ Gateway 与 Delivery")
    host = ask("Gateway host", str(gateway_existing.get("host", "127.0.0.1")))
    port = ask("Gateway port", str(gateway_existing.get("port", 8787)))
    title = ask("Gateway title", str(gateway_existing.get("title", "KX Agent Gateway")))
    auto_send = confirm("Webhook 回复时自动真实发送？", bool(delivery_existing.get("auto_send", True)))
    enabled = confirm("启用 delivery 子系统？", bool(delivery_existing.get("enabled", True)))
    timeout_seconds = ask("Delivery timeout seconds", str(delivery_existing.get("timeout_seconds", 20)))
    try:
        port_value = int(port)
    except ValueError:
        port_value = 8787
    try:
        timeout_value = int(timeout_seconds)
    except ValueError:
        timeout_value = 20
    return (
        {
            "host": host,
            "port": port_value,
            "title": title,
        },
        {
            "enabled": enabled,
            "auto_send": auto_send,
            "timeout_seconds": timeout_value,
        },
    )


def _collect_platform_delivery(existing: dict[str, Any], delivery_cfg: dict[str, Any]) -> dict[str, Any]:
    section("⑥ 第三方平台 / API")
    current_tokens = dict((existing.get("delivery") or {}).get("platform_tokens") or {})
    current_urls = dict((existing.get("delivery") or {}).get("platform_base_urls") or {})
    tokens = dict(current_tokens)
    urls = dict(current_urls)

    if confirm("配置 Telegram Bot？", "telegram" in current_tokens or "telegram" in current_urls):
        tokens["telegram"] = ask("  Telegram Bot Token", tokens.get("telegram", ""), password=True)
        urls["telegram"] = ask("  Telegram Base URL", urls.get("telegram", ""))

    if confirm("配置 Slack？", "slack" in current_tokens or "slack" in current_urls):
        tokens["slack"] = ask("  Slack Bot Token（或留空改用 Webhook URL）", tokens.get("slack", ""), password=True)
        urls["slack"] = ask("  Slack Webhook URL（可留空）", urls.get("slack", ""))

    if confirm("配置 Discord？", "discord" in current_tokens or "discord" in current_urls):
        tokens["discord"] = ask("  Discord Webhook Token / Path（可留空）", tokens.get("discord", ""), password=True)
        urls["discord"] = ask("  Discord Webhook URL（可留空）", urls.get("discord", ""))

    if confirm("配置 WhatsApp Cloud API？", "whatsapp" in current_tokens or "whatsapp" in current_urls):
        tokens["whatsapp"] = ask("  WhatsApp Access Token", tokens.get("whatsapp", ""), password=True)
        tokens["whatsapp_phone_number_id"] = ask("  Phone Number ID", tokens.get("whatsapp_phone_number_id", ""))
        urls["whatsapp"] = ask("  WhatsApp Base URL", urls.get("whatsapp", "https://graph.facebook.com/v19.0"))

    if confirm("配置 Feishu / Lark？", "feishu" in current_tokens or "feishu" in current_urls):
        tokens["feishu"] = ask("  Feishu Tenant/User Token", tokens.get("feishu", ""), password=True)
        urls["feishu"] = ask("  Feishu Base URL", urls.get("feishu", "https://open.feishu.cn"))

    if confirm("配置 Matrix？", "matrix" in current_tokens or "matrix" in current_urls):
        tokens["matrix"] = ask("  Matrix Access Token", tokens.get("matrix", ""), password=True)
        urls["matrix"] = ask("  Matrix Homeserver URL", urls.get("matrix", ""))

    if confirm("配置 Signal？", "signal" in current_urls):
        urls["signal"] = ask("  Signal HTTP daemon URL", urls.get("signal", "http://127.0.0.1:8080"))

    if confirm("配置 Email SMTP？", bool((existing.get("delivery") or {}).get("smtp_host"))):
        delivery_cfg["default_from_email"] = ask("  From Email", str((existing.get("delivery") or {}).get("default_from_email", "")))
        delivery_cfg["smtp_host"] = ask("  SMTP Host", str((existing.get("delivery") or {}).get("smtp_host", "")))
        delivery_cfg["smtp_port"] = int(ask("  SMTP Port", str((existing.get("delivery") or {}).get("smtp_port", 587))))
        delivery_cfg["smtp_username"] = ask("  SMTP Username", str((existing.get("delivery") or {}).get("smtp_username", "")))
        delivery_cfg["smtp_password"] = ask("  SMTP Password", str((existing.get("delivery") or {}).get("smtp_password", "")), password=True)
        delivery_cfg["smtp_use_tls"] = confirm("  SMTP use STARTTLS?", bool((existing.get("delivery") or {}).get("smtp_use_tls", True)))

    if confirm("配置 Twilio SMS？", bool((existing.get("delivery") or {}).get("twilio_account_sid"))):
        delivery_cfg["twilio_account_sid"] = ask("  Twilio Account SID", str((existing.get("delivery") or {}).get("twilio_account_sid", "")))
        delivery_cfg["twilio_auth_token"] = ask("  Twilio Auth Token", str((existing.get("delivery") or {}).get("twilio_auth_token", "")), password=True)
        delivery_cfg["twilio_from_number"] = ask("  Twilio From Number", str((existing.get("delivery") or {}).get("twilio_from_number", "")))

    delivery_cfg["platform_tokens"] = tokens
    delivery_cfg["platform_base_urls"] = urls
    return delivery_cfg


def _collect_misc(existing: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    approval_existing = existing.get("approval") or {}
    channels_existing = existing.get("channels") or {}
    dashboard_existing = existing.get("dashboard") or {}
    section("⑦ 运行策略")
    approval_enabled = confirm("启用 approval gate？", bool(approval_existing.get("enabled", True)))
    dashboard_enabled = confirm("启用 dashboard？", bool(dashboard_existing.get("enabled", True)))
    dashboard_port = ask("Dashboard port", str(dashboard_existing.get("port", 8899)))
    try:
        dashboard_port_value = int(dashboard_port)
    except ValueError:
        dashboard_port_value = 8899
    adapters_raw = ask(
        "启用 adapters（逗号分隔）",
        ",".join(channels_existing.get("adapters", KXConfig().channels.adapters)),
    )
    return (
        {
            "enabled": approval_enabled,
            "allow_session_tool_reuse": bool(approval_existing.get("allow_session_tool_reuse", True)),
            "required_actions": list(approval_existing.get("required_actions", ["write", "execute", "network", "dangerous"])),
        },
        {
            "enabled": list(channels_existing.get("enabled", ["cli", "web", "webhook"])),
            "stable_sessions": bool(channels_existing.get("stable_sessions", True)),
            "record_events": bool(channels_existing.get("record_events", True)),
            "adapters": [item.strip() for item in adapters_raw.split(",") if item.strip()],
            "adapter_secrets": dict(channels_existing.get("adapter_secrets", {})),
        },
        {
            "enabled": dashboard_enabled,
            "host": str(dashboard_existing.get("host", "127.0.0.1")),
            "port": dashboard_port_value,
        },
    )


def run_setup_wizard(config_path: Path) -> dict[str, Any] | None:
    config_path.parent.mkdir(parents=True, exist_ok=True)
    existing = {}
    if config_path.exists():
        existing = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    _print_header(config_path, bool(existing))
    model_cfg = _collect_model_config(existing)
    workspace_cfg, memory_cfg = _collect_workspace_config(existing)
    gateway_cfg, delivery_cfg = _collect_gateway_config(existing)
    delivery_cfg = _collect_platform_delivery(existing, delivery_cfg)
    approval_cfg, channels_cfg, dashboard_cfg = _collect_misc(existing)
    config: dict[str, Any] = {
        "identity": str(existing.get("identity", "kx-agent")),
        "model": model_cfg,
        "workspace": workspace_cfg,
        "memory": memory_cfg,
        "gateway": gateway_cfg,
        "delivery": delivery_cfg,
        "approval": approval_cfg,
        "channels": channels_cfg,
        "dashboard": dashboard_cfg,
        "skills": dict(existing.get("skills", {"paths": ["~/.kx/skills"], "auto_route": True, "hub_enabled": True})),
        "shell": dict(existing.get("shell", {})),
        "sandbox": dict(existing.get("sandbox", {})),
        "routing": dict(existing.get("routing", {})),
    }
    section("⑧ 确认并保存")
    print(f"  {c('bold', '模型')}: {PROVIDERS[model_cfg['provider']]['name']} / {model_cfg['model']}")
    if model_cfg.get("base_url"):
        print(f"  {c('bold', 'Base URL')}: {model_cfg['base_url']}")
    print(f"  {c('bold', 'Workspace')}: {workspace_cfg['root']}")
    print(f"  {c('bold', 'Gateway')}: http://{gateway_cfg['host']}:{gateway_cfg['port']}")
    print(f"  {c('bold', 'Delivery')}: {'enabled' if delivery_cfg['enabled'] else 'disabled'} / auto_send={'on' if delivery_cfg['auto_send'] else 'off'}")
    print(f"  {c('bold', 'Adapters')}: {', '.join(channels_cfg['adapters'])}")
    print()
    if not confirm("保存配置？", True):
        print(f"  {c('yellow', '已取消。')}")
        return None
    config_path.write_text(yaml.safe_dump(config, sort_keys=False, allow_unicode=True), encoding="utf-8")
    skills_dir = config_path.parent / "skills"
    skills_dir.mkdir(parents=True, exist_ok=True)
    print()
    print(
        box(
            "配置完成\n\n"
            "kx chat\n"
            "kx serve\n"
            "kx app\n"
            "kx status",
            "green",
        )
    )
    env_key = model_cfg.get("api_key_env")
    if env_key and not model_cfg.get("api_key"):
        print(f"\n  {c('yellow', '提示')}: 你也可以通过环境变量设置 API Key")
        print(f"  {c('cyan', f'export {env_key}=YOUR_KEY')}")
    print()
    return config
