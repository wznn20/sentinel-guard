# KX Agent

KX Agent is a local-first agent runtime that combines:

- OpenClaw-style gateway routing and session isolation
- Hermes-style memory compression and skill hub
- OpenHuman-style approval gates and human oversight

This repository now contains a working cross-platform KX foundation in Python for Linux, macOS, and Windows:

- CLI chat runtime
- local HTTP gateway
- MCP stdio server
- session-aware routing
- permission-based tool policy
- approval queue with audited execution
- rolling session summaries and structured memory items
- cross-session memory recall and session digests
- user profile extraction, transcript search, and global memory digest
- task board and delegation primitives for multi-agent orchestration
- executable worker delegation workflow
- automatic goal planner that expands goals into tasks and delegations
- planner is model-driven when available, with offline rule fallback
- automatic result aggregation from worker outputs
- worker tool planning and read-only evidence collection
- worker can also propose controlled write plans under approval
- worker can execute approved write tasks and produce artifacts
- multi-channel webhook routing, finer shell sandboxing, and dashboard entrypoint
- adapter registry, sandbox profiles, and live KX dashboard overview
- unified local app server, real adapter payload normalization, and dashboard live actions
- route and policy introspection surfaces

## Platform Support

- Linux: supported through `python3`
- macOS: supported through `python3`
- Windows: supported through `python` / `py`, with PowerShell-aware shell execution metadata

The current runtime is intentionally local-first and simple. It is not yet a full desktop app, messaging super-gateway, or multi-process orchestration plane. It is the core agent runtime those surfaces can sit on top of.

## Quick Start

```bash
pip install -e .
kx setup
kx chat
```

`kx setup` 现在是交互式配置向导，参考 Hermes setup，支持：

- 第三方 API / OpenAI 兼容端点
- OpenAI / Anthropic / Gemini / DeepSeek / OpenRouter / Azure / Bedrock / Vertex
- 国内主流模型提供商
- Ollama / LM Studio / vLLM / 自定义 base URL

如需只写默认配置而不进入交互式向导：

```bash
kx setup --default
```

## Main Commands

- `kx chat` interactive agent loop
- `kx self-test` run a local end-to-end toolchain self-check
- `kx serve` local JSON gateway
- `kx skills` list loaded skills
- `kx memory --session <id>` inspect session memory tree
- `kx digest --session <id>` inspect session digest
- `kx recall --query <text>` search cross-session memory
- `kx transcripts --query <text>` search stored conversation turns
- `kx profile` inspect extracted user profile
- `kx global-digest` inspect global memory state
- `kx task list|add|update|delegate|delegations` manage orchestration state
- `kx task run <delegation_id>` and `kx task run-next` execute delegated work
- `kx task plan --session <id> --goal <text>` auto-generate task trees
- `kx task aggregate <task_id>` and `kx task aggregate-next` synthesize worker output
- `kx task inspect <task_id>` preview the worker tool plan
- worker plans may include controlled write actions under approval
- `kx task write <task_id>` execute an approved worker write task
- `kx dashboard` serve the local dashboard UI
- `kx app` serve the unified local app server
- `/webhook/event` accepts normalized channel events with stable session routing
- `/adapters` lists registered channel adapters
- `/webhook/<platform>` accepts platform-shaped payloads for:
  `discord`, `slack`, `telegram`, `whatsapp`, `signal`, `mattermost`, `matrix`,
  `homeassistant`, `email`, `sms`, `dingtalk`, `api_server`, `msgraph_webhook`,
  `feishu`, `wecom`, `wecom_callback`, `weixin`, `bluebubbles`, `qqbot`, `yuanbao`
- legacy shortcuts like `/webhook/discord`, `/webhook/slack`, `/webhook/telegram` remain supported
- platform webhook replies now execute real outbound delivery when configured,
  and always include both `delivery_plan` and `delivery_result`
- `kx sessions` inspect stored sessions
- `kx route --channel <name>` preview route resolution
- `kx policy --tool-name <name> --permission <level>` preview tool policy
- `kx approve list|allow|deny` manage approvals
- `kx tool list|run|history` inspect and run tools
- `kx mcp` expose MCP tools over stdio
- `kx upgrate` or `kx upgrade` update the local KX Agent repo and reinstall it

## Current Architecture

- `kx_agent/config.py`: cross-platform config, workspace, shell, routing, approval, memory settings
- `kx_agent/routing.py`: OpenClaw-style binding resolver
- `kx_agent/policy.py`: OpenHuman-style permission and tool gating
- `kx_agent/approvals.py`: approval engine
- `kx_agent/memory.py`: session store, summaries, memory items, approvals, tool audit log
- user profile store and transcript/global digest retrieval
- task board and delegation store
- worker execution state and results
- automatic planning outputs
- aggregation output and parent review state
- worker evidence plan output
- `kx_agent/tools.py`: bounded local tools with workspace-root enforcement
- built-in toolset now includes `read_many`, `make_dir`, and `delete_file`
- `kx_agent/agent.py`: unified runtime for chat, tool execution, policy, memory, and approvals
- `kx_agent/gateway.py`: local HTTP surface
- `kx_agent/channels.py`: Hermes-aligned platform adapter registry, payload normalization, and webhook protocol handling
- `kx_agent/delivery.py`: platform-native outbound delivery planner + sender
- `kx_agent/cli.py`: CLI + MCP entrypoints

## Verification

The environment did not have `pytest` installed, so verification was done with:

- `python3 -m compileall kx_agent tests`
- direct execution of the test functions in [tests/test_kx_agent.py](/root/hermes-security-agent/tests/test_kx_agent.py)

Covered paths:

- offline chat and memory capture
- policy denial for read-only channels
- approval creation for write actions
- approval resolution and deferred tool execution
- session-scoped tool approval reuse
- automatic rolling summary generation
- cross-session memory recall
- transcript search
- user profile extraction
- global memory digest
- task creation and delegation
- worker execution and parent/child task state flow
- automatic goal-to-task planning
- worker result aggregation and review promotion
- worker read-only tool planning
- worker write-plan generation
- worker write execution with approval
- channel session normalization and sandbox policy enforcement
- sandbox profiles and local dashboard overview API
- unified app overview API and live dashboard task actions
- multi-file read tool
- route and policy explanation

## Design

See [KX_AGENT.md](./KX_AGENT.md).
