# Sentinel Guard 🛡️

**AI-Powered Cybersecurity Agent** — deployable on any website, server, or application.

> ⚠️ **纯防御型安全智能体**：仅检测和告警，不执行任何攻击性操作。所有数据留在你的基础设施中。

## Quick Start

```bash
pip install git+https://github.com/wznn20/sentinel-guard.git
sentinel setup          # 配置AI模型和API Key
sentinel start          # 启动安全监控
```

## Features

- 🔍 **实时流量分析** — 检测 SQLi、XSS、SSRF、命令注入等 28+ 种攻击模式
- 🧠 **AI 驱动** — 支持 OpenAI、Claude、DeepSeek 等 100+ 模型提供商 (via litellm)
- 📊 **Dark Glassmorphism 仪表盘** — 本地 `localhost:8443`，不对外暴露
- 🔌 **多平台接入** — 支持飞书、QQ Bot、Telegram、Discord 等
- 🐳 **三端部署** — Linux / macOS / Windows + Docker
- 🧩 **Hermes 集成** — 可作为 Hermes Agent 的技能/工具调用

## Architecture

```
sentinel-guard/
├── sentinel_core/       # 核心引擎 (LLM路由、配置、上下文、记忆)
├── sentinel_security/   # 安全模块 (流量分析、攻击特征库、告警引擎)
├── sentinel_cli/        # CLI 入口
├── sentinel_dashboard/  # 本地仪表盘 (Dark Glassmorphism)
└── sentinel_plugins/    # 插件接口 (Hermes MCP 集成)
```

## Configuration

```yaml
# ~/.sentinel/config.yaml
model:
  provider: openai
  model: gpt-4o
  api_key: ${SENTINEL_API_KEY}

platforms:
  - feishu:
      webhook_url: https://open.feishu.cn/...
  - qqbot:
      app_id: xxx

hermes:
  enabled: true
  mcp_port: 9120
```

## Hermes Integration

Sentinel 可作为 Hermes Agent 的 MCP 工具：

```bash
# 在 Hermes 中注册 Sentinel
hermes mcp add sentinel --command "sentinel mcp --port 9120"
```

## License

MIT © 2026

## Links

- GitHub: https://github.com/wznn20/sentinel-guard
- PyPI: https://pypi.org/project/sentinel-guard
