from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any


@dataclass
class LLMResult:
    text: str
    used_model: str
    offline: bool = False


class LLMClient:
    def __init__(self, config):
        self.config = config

    def chat(self, messages: list[dict[str, str]]) -> LLMResult:
        model = f"{self.config.model.provider}/{self.config.model.model}"
        if not self.config.model.api_key:
            return LLMResult(
                text=self._offline_reply(messages),
                used_model="offline",
                offline=True,
            )

        try:
            from litellm import completion

            response = completion(
                model=model,
                messages=messages,
                api_key=self.config.model.api_key,
                base_url=self.config.model.base_url,
                temperature=self.config.model.temperature,
                max_tokens=self.config.model.max_tokens,
            )
            return LLMResult(
                text=response.choices[0].message.content or "",
                used_model=model,
                offline=False,
            )
        except Exception as exc:
            return LLMResult(
                text=f"[LLM unavailable] {exc}\n\n{self._offline_reply(messages)}",
                used_model=model,
                offline=True,
            )

    def plan_json(self, system_prompt: str, user_prompt: str) -> tuple[dict[str, Any] | None, LLMResult]:
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        result = self.chat(messages)
        if result.offline:
            return None, result
        try:
            payload = self._extract_json(result.text)
            return payload, result
        except Exception:
            return None, result

    def _offline_reply(self, messages: list[dict[str, str]]) -> str:
        user = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")
        return (
            "KX Agent is running in offline mode.\n"
            f"Observed request: {user[:240]}\n"
            "I can route the task, preserve memory, and prepare a safe next step."
        )

    def _extract_json(self, text: str) -> dict[str, Any]:
        stripped = text.strip()
        if stripped.startswith("{") and stripped.endswith("}"):
            return json.loads(stripped)
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start >= 0 and end > start:
            return json.loads(stripped[start : end + 1])
        raise ValueError("no json object found")
