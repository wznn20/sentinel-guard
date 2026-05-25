from __future__ import annotations

from dataclasses import dataclass

from .policy import ToolPolicyDecision


@dataclass
class ApprovalDecision:
    approved: bool
    note: str = ""


class ApprovalEngine:
    def __init__(self, config):
        self.config = config

    def requires_approval(self, action: str) -> bool:
        return self.config.approval.enabled and action in set(self.config.approval.required_actions)

    def requires_for_tool(self, policy: ToolPolicyDecision) -> bool:
        if not self.config.approval.enabled:
            return False
        if policy.required_permission in set(self.config.approval.required_actions):
            return True
        return policy.needs_approval

    def format_request(self, action: str, payload: dict, reason: str = "") -> str:
        detail = f"\nReason: {reason}" if reason else ""
        return (
            f"Action `{action}` requires approval.{detail}\n"
            f"Payload: {payload}\n"
            "Approve only if you intend the side effect."
        )
