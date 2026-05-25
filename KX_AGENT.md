# KX Agent

## Identity

KX Agent is a composite local-first agent runtime that combines:

- OpenClaw-style routing, session isolation, and control-plane thinking
- Hermes-style skills, memory compression, and agent-loop pragmatism
- OpenHuman-style approvals, permission layers, and human supervision

## Core Design

KX is built around one runtime used by every surface:

- CLI
- HTTP gateway
- MCP stdio

That runtime owns five concerns:

1. Route resolution
2. Permission and tool policy
3. Approval gating
4. Memory and summaries
5. LLM-backed or offline reply generation

## What Was Implemented

### Routing

- route bindings by `channel`, `account`, and `peer`
- per-session `agent_id`, `permission`, and optional workspace metadata
- default-channel permission fallback when no explicit binding exists

### Memory

- persistent session table
- turn log
- structured memory items for preferences, tasks, decisions, and workstreams
- rolling session summaries after a configurable turn threshold
- session tree view that merges root metadata, summaries, memories, and turns

### Policy and Approvals

- per-tool permission levels: `read`, `write`, `execute`, `dangerous`
- session permission checks before tool execution
- approval records persisted to SQLite
- deferred tool execution after approval
- optional session-scoped reuse of approved tools

### Tools

- bounded local tools:
  - `read_file`
  - `search_code`
  - `list_dir`
  - `write_file`
  - `run_shell`
- workspace-root enforcement to avoid arbitrary path escape
- cross-platform shell invocation metadata for Linux/macOS/Windows

### Interfaces

- `kx chat`
- `kx serve`
- `kx mcp`
- approval and tool inspection commands
- Hermes-aligned webhook ingress for:
  `discord`, `slack`, `telegram`, `whatsapp`, `signal`, `mattermost`, `matrix`,
  `homeassistant`, `email`, `sms`, `dingtalk`, `api_server`, `msgraph_webhook`,
  `feishu`, `wecom`, `wecom_callback`, `weixin`, `bluebubbles`, `qqbot`, `yuanbao`
- protocol handshake handling for Slack, Discord, Telegram, Feishu, WhatsApp,
  Microsoft Graph webhook, and WeCom callback verification
- platform-native outbound `delivery_plan` generation for those adapters so
  gateway callers can execute consistent reply requests
- configurable real delivery execution for HTTP/webhook, SMTP email, and Twilio SMS

## Deliberate Scope Cut

This is not yet:

- a full OpenClaw-class messaging gateway
- a Hermes-class autonomous multi-subagent system
- an OpenHuman-class desktop shell with integrations and background ingest

Those are higher-level products. The implemented runtime is the shared agent core needed before those surfaces make sense.

## Next Logical Steps

1. Add richer platform-specific SDK clients for Matrix/Signal/QQ/Yuanbao
2. Add a stronger compression pipeline with structured head/tail preservation
3. Add richer retrieval over summaries and memory items
4. Add background jobs and scheduled tasks
5. Add plugin or provider interfaces for external integrations
