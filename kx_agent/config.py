from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import yaml


def _platform_shell() -> str:
    if os.name == "nt":
        return "powershell.exe"
    return os.getenv("SHELL") or "/bin/bash"


@dataclass
class ModelConfig:
    provider: str = "openai"
    litellm_prefix: str | None = None
    model: str = "gpt-4o-mini"
    api_key: str = ""
    api_key_env: str | None = None
    base_url: str | None = None
    temperature: float = 0.2
    max_tokens: int = 2048


@dataclass
class MemoryConfig:
    db_path: str = "~/.kx/kx.sqlite"
    recent_turns: int = 12
    summary_trigger: int = 20
    summary_window: int = 8
    retrieval_limit: int = 6


@dataclass
class SkillConfig:
    paths: list[str] = field(default_factory=lambda: ["~/.kx/skills"])
    auto_route: bool = True
    hub_enabled: bool = True


@dataclass
class ApprovalConfig:
    enabled: bool = True
    allow_session_tool_reuse: bool = True
    required_actions: list[str] = field(
        default_factory=lambda: [
            "write",
            "execute",
            "network",
            "dangerous",
        ]
    )


@dataclass
class GatewayConfig:
    host: str = "127.0.0.1"
    port: int = 8787
    title: str = "KX Agent Gateway"


@dataclass
class DeliveryConfig:
    enabled: bool = True
    auto_send: bool = True
    timeout_seconds: int = 20
    default_from_email: str = ""
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_use_tls: bool = True
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_from_number: str = ""
    platform_tokens: dict[str, str] = field(default_factory=dict)
    platform_base_urls: dict[str, str] = field(default_factory=dict)
    platform_settings: dict[str, dict[str, Any]] = field(default_factory=dict)


@dataclass
class ShellConfig:
    executable: str = field(default_factory=_platform_shell)
    default_cwd: str = "."
    timeout_seconds: int = 30


@dataclass
class SandboxConfig:
    read_roots: list[str] = field(default_factory=lambda: [".", "~/.kx"])
    write_roots: list[str] = field(default_factory=lambda: [".", "~/.kx"])
    shell_enabled: bool = True
    allow_shell_write: bool = False
    allow_shell_dangerous: bool = False
    allowed_shell_prefixes: list[str] = field(
        default_factory=lambda: ["pwd", "ls", "cat", "find", "rg", "git status", "dir", "type"]
    )
    denied_shell_patterns: list[str] = field(
        default_factory=lambda: [
            "rm -rf",
            "shutdown",
            "reboot",
            "mkfs",
            "curl http",
            "wget http",
            "powershell -c",
        ]
    )
    max_shell_seconds: int = 30
    max_output_bytes: int = 4000
    profiles: dict[str, dict[str, Any]] = field(
        default_factory=lambda: {
            "default": {
                "allow_write": True,
                "allow_shell": True,
                "allow_dangerous": False,
            },
            "read_only": {
                "allow_write": False,
                "allow_shell": True,
                "allow_dangerous": False,
            },
            "worker": {
                "allow_write": True,
                "allow_shell": False,
                "allow_dangerous": False,
            },
            "operator": {
                "allow_write": True,
                "allow_shell": True,
                "allow_dangerous": True,
            },
        }
    )


@dataclass
class ChannelConfig:
    enabled: list[str] = field(default_factory=lambda: ["cli", "web", "webhook"])
    stable_sessions: bool = True
    record_events: bool = True
    adapters: list[str] = field(
        default_factory=lambda: [
            "generic",
            "webhook",
            "discord",
            "slack",
            "telegram",
            "whatsapp",
            "signal",
            "mattermost",
            "matrix",
            "homeassistant",
            "email",
            "sms",
            "dingtalk",
            "api_server",
            "msgraph_webhook",
            "feishu",
            "wecom",
            "wecom_callback",
            "weixin",
            "bluebubbles",
            "qqbot",
            "yuanbao",
        ]
    )
    adapter_secrets: dict[str, str] = field(default_factory=dict)


@dataclass
class DashboardConfig:
    enabled: bool = True
    host: str = "127.0.0.1"
    port: int = 8899


@dataclass
class WorkspaceConfig:
    root: str = "."
    allow_roots: list[str] = field(default_factory=lambda: ["."])


@dataclass
class RoutingBinding:
    agent_id: str
    channel: str
    account: str = "default"
    peer: str = "*"
    workspace: str | None = None
    permission: str = "dangerous"
    sandbox_profile: str = "default"
    tool_allow: list[str] = field(default_factory=list)


@dataclass
class RoutingConfig:
    default_agent: str = "main"
    bindings: list[RoutingBinding] = field(default_factory=list)
    channel_permissions: dict[str, str] = field(default_factory=dict)


@dataclass
class KXConfig:
    identity: str = "kx-agent"
    model: ModelConfig = field(default_factory=ModelConfig)
    memory: MemoryConfig = field(default_factory=MemoryConfig)
    skills: SkillConfig = field(default_factory=SkillConfig)
    approval: ApprovalConfig = field(default_factory=ApprovalConfig)
    gateway: GatewayConfig = field(default_factory=GatewayConfig)
    delivery: DeliveryConfig = field(default_factory=DeliveryConfig)
    shell: ShellConfig = field(default_factory=ShellConfig)
    sandbox: SandboxConfig = field(default_factory=SandboxConfig)
    channels: ChannelConfig = field(default_factory=ChannelConfig)
    dashboard: DashboardConfig = field(default_factory=DashboardConfig)
    workspace: WorkspaceConfig = field(default_factory=WorkspaceConfig)
    routing: RoutingConfig = field(default_factory=RoutingConfig)

    DEFAULT_PATH = Path.home() / ".kx" / "config.yaml"

    @classmethod
    def load(cls, path: Path | None = None) -> "KXConfig":
        cfg = cls()
        config_path = path or cls.DEFAULT_PATH
        if config_path.exists():
            data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
            cfg._parse(data)

        env_candidates = [
            cfg.model.api_key_env or "",
            "KX_API_KEY",
            "OPENAI_API_KEY",
        ]
        for key in env_candidates:
            if key and not cfg.model.api_key:
                value = os.getenv(key, "")
                if value:
                    cfg.model.api_key = value
                    break
        return cfg

    def _parse(self, data: dict[str, Any]) -> None:
        self.identity = str(data.get("identity", self.identity))

        model_data = data.get("model") or {}
        self.model = ModelConfig(
            provider=str(model_data.get("provider", self.model.provider)),
            litellm_prefix=model_data.get("litellm_prefix", self.model.litellm_prefix),
            model=str(model_data.get("model", self.model.model)),
            api_key=os.path.expandvars(str(model_data.get("api_key", self.model.api_key))),
            api_key_env=model_data.get("api_key_env", self.model.api_key_env),
            base_url=model_data.get("base_url", self.model.base_url),
            temperature=float(model_data.get("temperature", self.model.temperature)),
            max_tokens=int(model_data.get("max_tokens", self.model.max_tokens)),
        )

        memory_data = data.get("memory") or {}
        self.memory = MemoryConfig(
            db_path=str(memory_data.get("db_path", self.memory.db_path)),
            recent_turns=int(memory_data.get("recent_turns", self.memory.recent_turns)),
            summary_trigger=int(memory_data.get("summary_trigger", self.memory.summary_trigger)),
            summary_window=int(memory_data.get("summary_window", self.memory.summary_window)),
            retrieval_limit=int(memory_data.get("retrieval_limit", self.memory.retrieval_limit)),
        )

        skills_data = data.get("skills") or {}
        self.skills = SkillConfig(
            paths=list(skills_data.get("paths", self.skills.paths)),
            auto_route=bool(skills_data.get("auto_route", self.skills.auto_route)),
            hub_enabled=bool(skills_data.get("hub_enabled", self.skills.hub_enabled)),
        )

        approval_data = data.get("approval") or {}
        self.approval = ApprovalConfig(
            enabled=bool(approval_data.get("enabled", self.approval.enabled)),
            allow_session_tool_reuse=bool(
                approval_data.get("allow_session_tool_reuse", self.approval.allow_session_tool_reuse)
            ),
            required_actions=list(
                approval_data.get("required_actions", self.approval.required_actions)
            ),
        )

        gateway_data = data.get("gateway") or {}
        self.gateway = GatewayConfig(
            host=str(gateway_data.get("host", self.gateway.host)),
            port=int(gateway_data.get("port", self.gateway.port)),
            title=str(gateway_data.get("title", self.gateway.title)),
        )

        delivery_data = data.get("delivery") or {}
        self.delivery = DeliveryConfig(
            enabled=bool(delivery_data.get("enabled", self.delivery.enabled)),
            auto_send=bool(delivery_data.get("auto_send", self.delivery.auto_send)),
            timeout_seconds=int(delivery_data.get("timeout_seconds", self.delivery.timeout_seconds)),
            default_from_email=os.path.expandvars(str(delivery_data.get("default_from_email", self.delivery.default_from_email))),
            smtp_host=os.path.expandvars(str(delivery_data.get("smtp_host", self.delivery.smtp_host))),
            smtp_port=int(delivery_data.get("smtp_port", self.delivery.smtp_port)),
            smtp_username=os.path.expandvars(str(delivery_data.get("smtp_username", self.delivery.smtp_username))),
            smtp_password=os.path.expandvars(str(delivery_data.get("smtp_password", self.delivery.smtp_password))),
            smtp_use_tls=bool(delivery_data.get("smtp_use_tls", self.delivery.smtp_use_tls)),
            twilio_account_sid=os.path.expandvars(str(delivery_data.get("twilio_account_sid", self.delivery.twilio_account_sid))),
            twilio_auth_token=os.path.expandvars(str(delivery_data.get("twilio_auth_token", self.delivery.twilio_auth_token))),
            twilio_from_number=os.path.expandvars(str(delivery_data.get("twilio_from_number", self.delivery.twilio_from_number))),
            platform_tokens={
                str(key): os.path.expandvars(str(value))
                for key, value in (delivery_data.get("platform_tokens") or {}).items()
            },
            platform_base_urls={
                str(key): os.path.expandvars(str(value))
                for key, value in (delivery_data.get("platform_base_urls") or {}).items()
            },
            platform_settings={
                str(key): {
                    str(inner_key): os.path.expandvars(str(inner_value))
                    for inner_key, inner_value in (value or {}).items()
                }
                for key, value in (delivery_data.get("platform_settings") or {}).items()
                if isinstance(value, dict)
            },
        )

        shell_data = data.get("shell") or {}
        self.shell = ShellConfig(
            executable=str(shell_data.get("executable", self.shell.executable)),
            default_cwd=str(shell_data.get("default_cwd", self.shell.default_cwd)),
            timeout_seconds=int(shell_data.get("timeout_seconds", self.shell.timeout_seconds)),
        )

        sandbox_data = data.get("sandbox") or {}
        self.sandbox = SandboxConfig(
            read_roots=list(sandbox_data.get("read_roots", self.sandbox.read_roots)),
            write_roots=list(sandbox_data.get("write_roots", self.sandbox.write_roots)),
            shell_enabled=bool(sandbox_data.get("shell_enabled", self.sandbox.shell_enabled)),
            allow_shell_write=bool(
                sandbox_data.get("allow_shell_write", self.sandbox.allow_shell_write)
            ),
            allow_shell_dangerous=bool(
                sandbox_data.get("allow_shell_dangerous", self.sandbox.allow_shell_dangerous)
            ),
            allowed_shell_prefixes=list(
                sandbox_data.get("allowed_shell_prefixes", self.sandbox.allowed_shell_prefixes)
            ),
            denied_shell_patterns=list(
                sandbox_data.get("denied_shell_patterns", self.sandbox.denied_shell_patterns)
            ),
            max_shell_seconds=int(
                sandbox_data.get("max_shell_seconds", self.sandbox.max_shell_seconds)
            ),
            max_output_bytes=int(
                sandbox_data.get("max_output_bytes", self.sandbox.max_output_bytes)
            ),
            profiles=dict(sandbox_data.get("profiles", self.sandbox.profiles)),
        )

        channels_data = data.get("channels") or {}
        self.channels = ChannelConfig(
            enabled=list(channels_data.get("enabled", self.channels.enabled)),
            stable_sessions=bool(channels_data.get("stable_sessions", self.channels.stable_sessions)),
            record_events=bool(channels_data.get("record_events", self.channels.record_events)),
            adapters=list(channels_data.get("adapters", self.channels.adapters)),
            adapter_secrets={
                str(key): str(value)
                for key, value in (channels_data.get("adapter_secrets") or {}).items()
            },
        )

        dashboard_data = data.get("dashboard") or {}
        self.dashboard = DashboardConfig(
            enabled=bool(dashboard_data.get("enabled", self.dashboard.enabled)),
            host=str(dashboard_data.get("host", self.dashboard.host)),
            port=int(dashboard_data.get("port", self.dashboard.port)),
        )

        workspace_data = data.get("workspace") or {}
        self.workspace = WorkspaceConfig(
            root=str(workspace_data.get("root", self.workspace.root)),
            allow_roots=list(workspace_data.get("allow_roots", self.workspace.allow_roots)),
        )

        routing_data = data.get("routing") or {}
        self.routing = RoutingConfig(
            default_agent=str(routing_data.get("default_agent", self.routing.default_agent)),
            bindings=[
                RoutingBinding(
                    agent_id=str(item.get("agent_id", self.routing.default_agent)),
                    channel=str(item.get("channel", "cli")),
                    account=str(item.get("account", "default")),
                    peer=str(item.get("peer", "*")),
                    workspace=item.get("workspace"),
                    permission=str(item.get("permission", "dangerous")),
                    sandbox_profile=str(item.get("sandbox_profile", "default")),
                    tool_allow=list(item.get("tool_allow", [])),
                )
                for item in routing_data.get("bindings", [])
            ],
            channel_permissions={
                str(key): str(value)
                for key, value in (routing_data.get("channel_permissions") or {}).items()
            },
        )

    def save(self, path: Path | None = None) -> Path:
        config_path = path or self.DEFAULT_PATH
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(
            yaml.safe_dump(self.to_dict(), sort_keys=False, allow_unicode=True),
            encoding="utf-8",
        )
        return config_path

    def to_dict(self) -> dict[str, Any]:
        return {
            "identity": self.identity,
            "model": {
                "provider": self.model.provider,
                "litellm_prefix": self.model.litellm_prefix,
                "model": self.model.model,
                "api_key": self.model.api_key,
                "api_key_env": self.model.api_key_env,
                "base_url": self.model.base_url,
                "temperature": self.model.temperature,
                "max_tokens": self.model.max_tokens,
            },
            "memory": {
                "db_path": self.memory.db_path,
                "recent_turns": self.memory.recent_turns,
                "summary_trigger": self.memory.summary_trigger,
                "summary_window": self.memory.summary_window,
                "retrieval_limit": self.memory.retrieval_limit,
            },
            "skills": {
                "paths": self.skills.paths,
                "auto_route": self.skills.auto_route,
                "hub_enabled": self.skills.hub_enabled,
            },
            "approval": {
                "enabled": self.approval.enabled,
                "allow_session_tool_reuse": self.approval.allow_session_tool_reuse,
                "required_actions": self.approval.required_actions,
            },
            "gateway": {
                "host": self.gateway.host,
                "port": self.gateway.port,
                "title": self.gateway.title,
            },
            "delivery": {
                "enabled": self.delivery.enabled,
                "auto_send": self.delivery.auto_send,
                "timeout_seconds": self.delivery.timeout_seconds,
                "default_from_email": self.delivery.default_from_email,
                "smtp_host": self.delivery.smtp_host,
                "smtp_port": self.delivery.smtp_port,
                "smtp_username": self.delivery.smtp_username,
                "smtp_password": self.delivery.smtp_password,
                "smtp_use_tls": self.delivery.smtp_use_tls,
                "twilio_account_sid": self.delivery.twilio_account_sid,
                "twilio_auth_token": self.delivery.twilio_auth_token,
                "twilio_from_number": self.delivery.twilio_from_number,
                "platform_tokens": self.delivery.platform_tokens,
                "platform_base_urls": self.delivery.platform_base_urls,
                "platform_settings": self.delivery.platform_settings,
            },
            "shell": {
                "executable": self.shell.executable,
                "default_cwd": self.shell.default_cwd,
                "timeout_seconds": self.shell.timeout_seconds,
            },
            "sandbox": {
                "read_roots": self.sandbox.read_roots,
                "write_roots": self.sandbox.write_roots,
                "shell_enabled": self.sandbox.shell_enabled,
                "allow_shell_write": self.sandbox.allow_shell_write,
                "allow_shell_dangerous": self.sandbox.allow_shell_dangerous,
                "allowed_shell_prefixes": self.sandbox.allowed_shell_prefixes,
                "denied_shell_patterns": self.sandbox.denied_shell_patterns,
                "max_shell_seconds": self.sandbox.max_shell_seconds,
                "max_output_bytes": self.sandbox.max_output_bytes,
                "profiles": self.sandbox.profiles,
            },
            "channels": {
                "enabled": self.channels.enabled,
                "stable_sessions": self.channels.stable_sessions,
                "record_events": self.channels.record_events,
                "adapters": self.channels.adapters,
                "adapter_secrets": self.channels.adapter_secrets,
            },
            "dashboard": {
                "enabled": self.dashboard.enabled,
                "host": self.dashboard.host,
                "port": self.dashboard.port,
            },
            "workspace": {
                "root": self.workspace.root,
                "allow_roots": self.workspace.allow_roots,
            },
            "routing": {
                "default_agent": self.routing.default_agent,
                "bindings": [
                    {
                        "agent_id": item.agent_id,
                        "channel": item.channel,
                        "account": item.account,
                        "peer": item.peer,
                        "workspace": item.workspace,
                        "permission": item.permission,
                        "sandbox_profile": item.sandbox_profile,
                        "tool_allow": item.tool_allow,
                    }
                    for item in self.routing.bindings
                ],
                "channel_permissions": self.routing.channel_permissions,
            },
        }
