from __future__ import annotations

from dataclasses import dataclass

from .config import RoutingBinding, RoutingConfig


@dataclass
class RouteContext:
    session_id: str
    channel: str
    user: str
    account: str = "default"
    peer: str = "*"


@dataclass
class RouteResult:
    agent_id: str
    channel: str
    account: str
    peer: str
    permission: str
    sandbox_profile: str
    workspace: str | None
    tool_allow: list[str]
    binding_kind: str


class RouteResolver:
    def __init__(self, config: RoutingConfig):
        self.config = config

    def resolve(self, ctx: RouteContext) -> RouteResult:
        exact: RoutingBinding | None = None
        wildcard_peer: RoutingBinding | None = None
        channel_only: RoutingBinding | None = None

        for binding in self.config.bindings:
            if binding.channel != ctx.channel:
                continue
            if binding.account not in {"*", ctx.account}:
                continue
            if binding.peer == ctx.peer:
                exact = binding
                break
            if binding.peer == "*":
                wildcard_peer = wildcard_peer or binding
            if binding.peer in {"", "channel"}:
                channel_only = channel_only or binding

        chosen = exact or wildcard_peer or channel_only
        if chosen:
            return RouteResult(
                agent_id=chosen.agent_id,
                channel=ctx.channel,
                account=ctx.account,
                peer=ctx.peer,
                permission=chosen.permission,
                sandbox_profile=chosen.sandbox_profile,
                workspace=chosen.workspace,
                tool_allow=list(chosen.tool_allow),
                binding_kind="binding",
            )

        default_permission = self.config.channel_permissions.get(ctx.channel, "dangerous")
        return RouteResult(
            agent_id=self.config.default_agent,
            channel=ctx.channel,
            account=ctx.account,
            peer=ctx.peer,
            permission=default_permission,
            sandbox_profile="default",
            workspace=None,
            tool_allow=[],
            binding_kind="default",
        )
