from __future__ import annotations

from dataclasses import dataclass

from .tools import ToolSpec


PERMISSION_ORDER = {
    "none": 0,
    "read": 1,
    "write": 2,
    "execute": 3,
    "dangerous": 4,
}


@dataclass
class ToolPolicyDecision:
    tool_name: str
    allowed: bool
    needs_approval: bool
    reason: str
    allowed_permission: str
    required_permission: str


class ToolPolicyEngine:
    def decide(
        self,
        spec: ToolSpec,
        allowed_permission: str,
        explicit_allow: list[str] | None = None,
    ) -> ToolPolicyDecision:
        explicit_allow = explicit_allow or []
        allowed_rank = PERMISSION_ORDER.get(allowed_permission, PERMISSION_ORDER["read"])
        required_rank = PERMISSION_ORDER.get(spec.permission, PERMISSION_ORDER["dangerous"])
        tool_allowed = spec.name in explicit_allow

        if allowed_rank < required_rank and not tool_allowed:
            return ToolPolicyDecision(
                tool_name=spec.name,
                allowed=False,
                needs_approval=False,
                reason=f"tool requires {spec.permission}, session allows {allowed_permission}",
                allowed_permission=allowed_permission,
                required_permission=spec.permission,
            )

        return ToolPolicyDecision(
            tool_name=spec.name,
            allowed=True,
            needs_approval=spec.requires_approval or required_rank >= PERMISSION_ORDER["write"],
            reason="allowed by policy",
            allowed_permission=allowed_permission,
            required_permission=spec.permission,
        )
