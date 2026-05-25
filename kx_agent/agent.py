from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .approvals import ApprovalEngine
from .config import KXConfig
from .delivery import DeliveryResult, DeliveryService
from .llm import LLMClient
from .memory import MemoryStore
from .policy import ToolPolicyDecision, ToolPolicyEngine
from .routing import RouteContext, RouteResolver
from .skills import Skill, SkillRegistry
from .tools import ToolRegistry, ToolResult


DEFAULT_SYSTEM = """You are KX Agent.

You combine:
- OpenClaw-style routing and session isolation
- Hermes-style memory compression and skills
- OpenHuman-style approvals and human oversight

Rules:
- Stay concise and concrete.
- Preserve user preferences, decisions, and open tasks.
- Respect session permissions and route metadata.
- Ask for approval before side effects.
- Prefer safe incremental actions.
"""

WORKER_SYSTEM = """You are a KX worker sub-agent.

You execute one delegated subtask at a time.

Rules:
- Stay concise and task-focused.
- Do not invent completion if blocked.
- Produce a useful result summary for the parent agent.
- Prefer analysis and safe planning over side effects unless tools are explicitly used.
Use read-only workspace tools when needed to inspect files or search for evidence.
"""

PLANNER_SYSTEM = """You are the KX planning engine.

Return a single JSON object with this schema:
{
  "steps": [
    {
      "title": "short step title",
      "details": "what this step should do",
      "priority": "high|medium|low",
      "owner": "worker|planner",
      "delegate": true
    }
  ]
}

Rules:
- Produce 2 to 5 steps.
- Prefer concrete execution-oriented steps.
- Default owner should be "worker" unless the step is purely coordination.
- Output JSON only.
"""


@dataclass
class KXReply:
    session_id: str
    skill: str
    model: str
    reply: str
    offline: bool
    memory_summary: str
    tree: dict[str, Any]
    route: dict[str, Any]
    tool_result: dict[str, Any] | None = None
    delivery_plan: dict[str, Any] | None = None
    delivery_result: dict[str, Any] | None = None


class KXAgent:
    def __init__(self, config_path: Path | None = None):
        self.config = KXConfig.load(config_path)
        self.memory = MemoryStore(self.config.memory.db_path)
        extra_skill_dirs = [Path(path).expanduser() for path in self.config.skills.paths]
        self.skills = SkillRegistry(extra_dirs=extra_skill_dirs)
        self.llm = LLMClient(self.config)
        workspace_root = Path(self.config.workspace.root).expanduser().resolve()
        allow_roots = [Path(p).expanduser().resolve() for p in self.config.workspace.allow_roots]
        self.tools = ToolRegistry(
            workspace_root=workspace_root,
            allow_roots=allow_roots,
            shell_config=self.config.shell,
            sandbox_config=self.config.sandbox,
        )
        self.delivery = DeliveryService(self.config)
        self.route_resolver = RouteResolver(self.config.routing)
        self.tool_policy = ToolPolicyEngine()
        self.approvals = ApprovalEngine(self.config)
        self._bootstrap_skills()

    def _bootstrap_skills(self) -> None:
        for skill in self.skills.skills:
            self.memory.register_skill(
                skill.name,
                skill.trigger_terms,
                skill.description,
                skill.path,
                skill.source,
            )

    def chat(
        self,
        message: str,
        session_id: str | None = None,
        channel: str = "cli",
        user: str = "user",
        account: str = "default",
        peer: str = "*",
    ) -> KXReply:
        session_id = session_id or uuid.uuid4().hex[:12]
        route = self.route_resolver.resolve(
            RouteContext(
                session_id=session_id,
                channel=channel,
                user=user,
                account=account,
                peer=peer,
            )
        )
        self.memory.ensure_session(
            session_id,
            title=f"{user} session",
            route={
                "agent_id": route.agent_id,
                "channel": route.channel,
                "user": user,
                "account": account,
                "peer": peer,
                "permission": route.permission,
                "sandbox_profile": route.sandbox_profile,
                "workspace": route.workspace or "",
            },
        )

        summary_before = self.memory.latest_summary(session_id)
        skill = self.skills.match(message, summary_before if self.config.skills.auto_route else "")
        user_turn_id = self.memory.append_turn(session_id, "user", message, channel=channel, skill=skill.name)
        self._extract_memory(session_id, message, skill.name, user_turn_id)
        summary = self._compress_if_needed(session_id)

        tool_plan = self._detect_tool_request(message)
        if tool_plan:
            return self._handle_tool_request(
                session_id=session_id,
                channel=channel,
                route=route,
                skill=skill,
                summary=summary,
                plan=tool_plan,
            )

        action = self._infer_action(message)
        if self.approvals.requires_approval(action):
            pending_id = self.memory.request_approval(
                session_id,
                action,
                {
                    "message": message,
                    "skill": skill.name,
                    "channel": channel,
                    "route": route.__dict__,
                },
            )
            reply = self.approvals.format_request(
                action,
                {"approval_id": pending_id, "skill": skill.name},
            )
            self.memory.append_turn(session_id, "assistant", reply, channel=channel, skill=skill.name)
            return self._reply(
                session_id,
                skill.name,
                "approval-gate",
                reply,
                False,
                summary,
                route.__dict__,
            )

        messages = self._build_messages(session_id, message, skill, route.__dict__)
        result = self.llm.chat(messages)
        self.memory.append_turn(
            session_id,
            "assistant",
            result.text,
            channel=channel,
            skill=skill.name,
        )
        self._extract_assistant_memory(session_id, message, result.text, skill.name)
        return self._reply(
            session_id,
            skill.name,
            result.used_model,
            result.text,
            result.offline,
            summary,
            route.__dict__,
        )

    def _reply(
        self,
        session_id: str,
        skill_name: str,
        model: str,
        text: str,
        offline: bool,
        summary: str,
        route: dict[str, Any],
        tool_result: dict[str, Any] | None = None,
        delivery_plan: dict[str, Any] | None = None,
        delivery_result: dict[str, Any] | None = None,
    ) -> KXReply:
        return KXReply(
            session_id=session_id,
            skill=skill_name,
            model=model,
            reply=text,
            offline=offline,
            memory_summary=summary,
            tree=self.memory.session_tree(session_id),
            route=route,
            tool_result=tool_result,
            delivery_plan=delivery_plan,
            delivery_result=delivery_result,
        )

    def _build_messages(
        self,
        session_id: str,
        message: str,
        skill: Skill,
        route: dict[str, Any],
    ) -> list[dict[str, str]]:
        recent = self.memory.list_turns(session_id, self.config.memory.recent_turns)
        summary = self.memory.latest_summary(session_id) or "No prior summary."
        recall = self.memory.recall(session_id, message, limit=self.config.memory.retrieval_limit)
        recall_block = self._render_recall(recall)
        global_recall = self.memory.recall_global(message, limit=max(2, self.config.memory.retrieval_limit // 2))
        global_block = self._render_global_recall(session_id, global_recall)
        profile_block = self._render_profile(self.memory.profile())
        digest_block = self._render_global_digest(self.memory.global_digest(limit=4))
        tasks_block = self._render_tasks(self.memory.list_tasks(session_id=session_id))

        context = [
            {"role": "system", "content": DEFAULT_SYSTEM},
            {
                "role": "system",
                "content": (
                    f"Route: agent={route['agent_id']} channel={route['channel']} "
                    f"permission={route['permission']} workspace={route.get('workspace') or '.'}"
                ),
            },
            {"role": "system", "content": f"User profile:\n{profile_block}"},
            {"role": "system", "content": f"Active skill: {skill.name}\n{skill.instructions}"},
            {"role": "system", "content": f"Session summary:\n{summary}"},
            {"role": "system", "content": f"Relevant memory:\n{recall_block}"},
            {"role": "system", "content": f"Cross-session memory:\n{global_block}"},
            {"role": "system", "content": f"Global digest:\n{digest_block}"},
            {"role": "system", "content": f"Task board:\n{tasks_block}"},
        ]
        if self.config.skills.hub_enabled:
            context.append({"role": "system", "content": f"Skill hub:\n{self.skills.render_hub()}"})
        for turn in recent:
            context.append({"role": turn["role"], "content": turn["content"]})
        context.append({"role": "user", "content": message})
        return context

    def _render_recall(self, items: list[dict[str, Any]]) -> str:
        if not items:
            return "No matched memory."
        lines = []
        for item in items:
            lines.append(f"- [{item['kind']}] {item['title']}: {item['content'][:220]}")
        return "\n".join(lines)

    def _render_global_recall(self, session_id: str, items: list[dict[str, Any]]) -> str:
        usable = [item for item in items if item["session_id"] != session_id]
        if not usable:
            return "No matched cross-session memory."
        lines = []
        for item in usable[:6]:
            lines.append(
                f"- [{item['session_id']}/{item['kind']}] {item['title']}: {item['content'][:180]}"
            )
        return "\n".join(lines)

    def _render_profile(self, items: list[dict[str, Any]]) -> str:
        if not items:
            return "No saved user profile."
        return "\n".join(f"- {item['key']}: {item['value']}" for item in items[:12])

    def _render_global_digest(self, digest: dict[str, Any]) -> str:
        lines: list[str] = []
        sessions = digest.get("recent_sessions", [])
        if sessions:
            lines.append("Recent sessions:")
            for row in sessions[:4]:
                lines.append(
                    f"- {row['session_id']} [{row['agent_id']}/{row['channel']}]: {str(row['summary'])[:140]}"
                )
        memory = digest.get("top_memory", [])
        if memory:
            lines.append("Top memory:")
            for row in memory[:4]:
                lines.append(
                    f"- {row['session_id']} [{row['kind']}] {row['title']}: {row['content'][:140]}"
                )
        tasks = digest.get("tasks", [])
        if tasks:
            lines.append("Tasks:")
            for row in tasks[:4]:
                lines.append(
                    f"- {row['session_id']} [{row['status']}/{row['owner']}] {row['title']}"
                )
        return "\n".join(lines) if lines else "No global digest."

    def _render_tasks(self, tasks: list[dict[str, Any]]) -> str:
        if not tasks:
            return "No active tasks."
        lines = []
        for task in tasks[:10]:
            lines.append(
                f"- #{task['id']} [{task['status']}/{task['priority']}/{task['owner']}] {task['title']}"
            )
        return "\n".join(lines)

    def _compress_if_needed(self, session_id: str) -> str:
        turn_count = self.memory.count_turns(session_id)
        session = self.memory.get_session(session_id) or {}
        summary = str(session.get("summary") or "")
        if turn_count <= self.config.memory.summary_trigger:
            return summary

        last_turn_id = self.memory.last_turn_id(session_id)
        window = max(self.config.memory.summary_window, 2)
        cutoff_turn_id = max(0, last_turn_id - window)
        already = self.memory.summarized_until_turn_id(session_id)
        if cutoff_turn_id <= already:
            return summary

        turns = self.memory.turns_for_summary(session_id, already, cutoff_turn_id)
        if not turns:
            return summary

        new_summary = self._summarize_turns(summary, turns)
        self.memory.summarize_session(
            session_id,
            new_summary,
            start_turn_id=turns[0]["id"],
            end_turn_id=turns[-1]["id"],
        )
        return new_summary

    def _summarize_turns(self, previous_summary: str, turns: list[dict[str, Any]]) -> str:
        lines: list[str] = []
        if previous_summary:
            lines.append(f"Previous summary: {previous_summary[:600]}")
        for turn in turns:
            lines.append(f"{turn['role']}[{turn['skill'] or '-'}]: {turn['content'][:220]}")
        tail = lines[-12:]
        return " | ".join(tail)

    def _detect_tool_request(self, message: str) -> dict[str, Any] | None:
        text = message.strip()
        lower = text.lower()
        if lower.startswith("digest "):
            session = text.split(" ", 1)[1]
            return {"tool_name": "session_digest", "arguments": {"session_id": session}}
        if lower.startswith("task add "):
            title = text.split(" ", 2)[2]
            return {"tool_name": "task_add", "arguments": {"title": title}}
        if lower.startswith("task done "):
            task_id = int(text.split(" ", 2)[2])
            return {"tool_name": "task_done", "arguments": {"task_id": task_id}}
        if lower.startswith("task list"):
            return {"tool_name": "task_list", "arguments": {}}
        if lower.startswith("plan "):
            goal = text.split(" ", 1)[1]
            return {"tool_name": "task_plan", "arguments": {"goal": goal}}
        if lower.startswith("delegate "):
            raw = text.split(" ", 1)[1]
            task_part, _, detail = raw.partition(" ")
            return {
                "tool_name": "task_delegate",
                "arguments": {"task_id": int(task_part), "details": detail},
            }
        if lower.startswith("worker run "):
            delegation_id = int(text.split(" ", 2)[2])
            return {"tool_name": "worker_run", "arguments": {"delegation_id": delegation_id}}
        if lower.startswith("worker next"):
            return {"tool_name": "worker_next", "arguments": {}}
        if lower.startswith("aggregate "):
            task_id = int(text.split(" ", 1)[1])
            return {"tool_name": "task_aggregate", "arguments": {"task_id": task_id}}
        if lower.startswith("aggregate-next"):
            return {"tool_name": "task_aggregate_next", "arguments": {}}
        if lower.startswith("worker write "):
            raw = text.split(" ", 2)[2]
            task_part, _, content = raw.partition(" ")
            return {
                "tool_name": "worker_write",
                "arguments": {"task_id": int(task_part), "content": content},
            }
        if lower.startswith("tool "):
            try:
                _, tool_name, raw_json = text.split(" ", 2)
                return {"tool_name": tool_name.strip(), "arguments": json.loads(raw_json)}
            except (ValueError, json.JSONDecodeError):
                return {"tool_name": "__invalid__", "arguments": {"raw": text}}
        if lower.startswith("read ") or lower.startswith("open "):
            path = text.split(" ", 1)[1]
            return {"tool_name": "read_file", "arguments": {"path": path}}
        if lower.startswith("readmany "):
            raw = text.split(" ", 1)[1]
            root, _, pattern = raw.partition(" ")
            return {"tool_name": "read_many", "arguments": {"path": root, "pattern": pattern or "*"}}
        if lower.startswith("ls ") or lower.startswith("list "):
            path = text.split(" ", 1)[1]
            return {"tool_name": "list_dir", "arguments": {"path": path}}
        if lower.startswith("mkdir "):
            path = text.split(" ", 1)[1]
            return {"tool_name": "make_dir", "arguments": {"path": path}}
        if lower.startswith("rm "):
            path = text.split(" ", 1)[1]
            return {"tool_name": "delete_file", "arguments": {"path": path}}
        if lower.startswith("search "):
            pattern = text.split(" ", 1)[1]
            return {"tool_name": "search_code", "arguments": {"pattern": pattern}}
        if lower.startswith("write "):
            _, raw = text.split(" ", 1)
            target, _, content = raw.partition(" ")
            return {"tool_name": "write_file", "arguments": {"path": target, "content": content}}
        if lower.startswith("run "):
            command = text.split(" ", 1)[1]
            return {"tool_name": "run_shell", "arguments": {"command": command}}
        return None

    def _handle_tool_request(
        self,
        session_id: str,
        channel: str,
        route,
        skill: Skill,
        summary: str,
        plan: dict[str, Any],
    ) -> KXReply:
        tool_name = plan["tool_name"]
        if tool_name == "__invalid__":
            reply = "Invalid tool request. Use `tool <name> <json>`."
            self.memory.append_turn(session_id, "assistant", reply, channel=channel, skill=skill.name)
            return self._reply(session_id, skill.name, "tool-router", reply, False, summary, route.__dict__)

        if tool_name == "session_digest":
            digest = self.memory.session_digest(plan["arguments"]["session_id"])
            reply = json.dumps(digest, ensure_ascii=False, indent=2)
            self.memory.append_turn(session_id, "assistant", reply, channel=channel, skill=skill.name)
            return self._reply(session_id, skill.name, "digest", reply, False, summary, route.__dict__)

        if tool_name == "task_add":
            task_id = self.memory.create_task(
                session_id,
                title=plan["arguments"]["title"],
                details="Created from conversation",
                owner=route.agent_id,
            )
            reply = f"Created task #{task_id}: {plan['arguments']['title']}"
            self.memory.append_turn(session_id, "assistant", reply, channel=channel, skill=skill.name)
            return self._reply(session_id, skill.name, "task-board", reply, False, summary, route.__dict__)

        if tool_name == "task_done":
            self.memory.update_task(plan["arguments"]["task_id"], status="done")
            reply = f"Marked task #{plan['arguments']['task_id']} done."
            self.memory.append_turn(session_id, "assistant", reply, channel=channel, skill=skill.name)
            return self._reply(session_id, skill.name, "task-board", reply, False, summary, route.__dict__)

        if tool_name == "task_list":
            tasks = self.memory.list_tasks(session_id=session_id)
            reply = json.dumps(tasks, ensure_ascii=False, indent=2)
            self.memory.append_turn(session_id, "assistant", reply, channel=channel, skill=skill.name)
            return self._reply(session_id, skill.name, "task-board", reply, False, summary, route.__dict__)

        if tool_name == "task_plan":
            plan_result = self.plan_goal(session_id=session_id, goal=plan["arguments"]["goal"])
            reply = json.dumps(plan_result, ensure_ascii=False, indent=2)
            self.memory.append_turn(session_id, "assistant", reply, channel=channel, skill=skill.name)
            return self._reply(session_id, skill.name, "planner", reply, False, summary, route.__dict__)

        if tool_name == "task_delegate":
            delegation = self.delegate_task(
                session_id=session_id,
                parent_task_id=plan["arguments"]["task_id"],
                details=plan["arguments"].get("details", ""),
            )
            reply = json.dumps(delegation, ensure_ascii=False, indent=2)
            self.memory.append_turn(session_id, "assistant", reply, channel=channel, skill=skill.name)
            return self._reply(session_id, skill.name, "task-board", reply, False, summary, route.__dict__)

        if tool_name == "worker_run":
            result = self.run_delegation(plan["arguments"]["delegation_id"])
            reply = json.dumps(result, ensure_ascii=False, indent=2)
            self.memory.append_turn(session_id, "assistant", reply, channel=channel, skill=skill.name)
            return self._reply(session_id, skill.name, "worker", reply, False, summary, route.__dict__)

        if tool_name == "worker_next":
            result = self.run_next_delegation(session_id=session_id)
            reply = json.dumps(result, ensure_ascii=False, indent=2)
            self.memory.append_turn(session_id, "assistant", reply, channel=channel, skill=skill.name)
            return self._reply(session_id, skill.name, "worker", reply, False, summary, route.__dict__)

        if tool_name == "task_aggregate":
            result = self.aggregate_task(plan["arguments"]["task_id"])
            reply = json.dumps(result, ensure_ascii=False, indent=2)
            self.memory.append_turn(session_id, "assistant", reply, channel=channel, skill=skill.name)
            return self._reply(session_id, skill.name, "aggregator", reply, False, summary, route.__dict__)

        if tool_name == "task_aggregate_next":
            result = self.aggregate_next_task(session_id=session_id)
            reply = json.dumps(result, ensure_ascii=False, indent=2)
            self.memory.append_turn(session_id, "assistant", reply, channel=channel, skill=skill.name)
            return self._reply(session_id, skill.name, "aggregator", reply, False, summary, route.__dict__)

        if tool_name == "worker_write":
            result = self.worker_write(plan["arguments"]["task_id"], plan["arguments"]["content"])
            reply = json.dumps(result, ensure_ascii=False, indent=2)
            self.memory.append_turn(session_id, "assistant", reply, channel=channel, skill=skill.name)
            return self._reply(session_id, skill.name, "worker", reply, False, summary, route.__dict__)

        spec_names = {spec["name"] for spec in self.tools.list_tools()}
        if tool_name not in spec_names:
            reply = f"Unknown tool: {tool_name}"
            self.memory.append_turn(session_id, "assistant", reply, channel=channel, skill=skill.name)
            return self._reply(session_id, skill.name, "tool-router", reply, False, summary, route.__dict__)

        spec = self.tools.spec(tool_name)
        policy = self.tool_policy.decide(spec, route.permission, route.tool_allow)
        if not policy.allowed:
            reply = f"Tool `{tool_name}` blocked by policy: {policy.reason}"
            self.memory.append_turn(session_id, "assistant", reply, channel=channel, skill=skill.name)
            return self._reply(session_id, skill.name, "policy", reply, False, summary, route.__dict__)

        if self._tool_needs_approval(session_id, tool_name, policy):
            pending_id = self.memory.request_approval(
                session_id,
                tool_name,
                {
                    "tool_name": tool_name,
                    "arguments": plan["arguments"],
                    "skill": skill.name,
                    "channel": channel,
                    "route": route.__dict__,
                    "policy": policy.__dict__,
                },
            )
            reply = self.approvals.format_request(
                tool_name,
                {
                    "approval_id": pending_id,
                    "tool_name": tool_name,
                    "arguments": plan["arguments"],
                },
                reason=policy.reason,
            )
            self.memory.append_turn(session_id, "assistant", reply, channel=channel, skill=skill.name)
            return self._reply(session_id, skill.name, "approval-gate", reply, False, summary, route.__dict__)

        tool_result = self._run_tool(session_id, tool_name, plan["arguments"])
        reply = self._format_tool_reply(tool_result)
        self.memory.append_turn(session_id, "assistant", reply, channel=channel, skill=skill.name)
        return self._reply(
            session_id,
            skill.name,
            "tool-exec",
            reply,
            False,
            summary,
            route.__dict__,
            tool_result={
                "tool_name": tool_result.tool_name,
                "status": tool_result.status,
                "metadata": tool_result.metadata,
            },
        )

    def _tool_needs_approval(
        self,
        session_id: str,
        tool_name: str,
        policy: ToolPolicyDecision,
    ) -> bool:
        if not self.approvals.requires_for_tool(policy):
            return False
        if (
            self.config.approval.allow_session_tool_reuse
            and self.memory.has_tool_reuse(session_id, tool_name)
        ):
            return False
        return True

    def _run_tool(self, session_id: str, tool_name: str, arguments: dict[str, Any]) -> ToolResult:
        session = self.memory.get_session(session_id) or {}
        sandbox_profile = str(session.get("sandbox_profile") or "default")
        try:
            result = self.tools.execute(tool_name, arguments, sandbox_profile=sandbox_profile)
        except Exception as exc:
            result = ToolResult(tool_name, "error", str(exc), {"arguments": arguments})
        self.memory.log_tool_run(
            session_id,
            tool_name,
            arguments,
            result.status,
            result.output[:4000],
            result.metadata,
        )
        return result

    def _format_tool_reply(self, result: ToolResult) -> str:
        output = result.output[:3000]
        return (
            f"Tool `{result.tool_name}` finished with status `{result.status}`.\n"
            f"Metadata: {result.metadata}\n"
            f"Output:\n{output}"
        )

    def list_tools(self) -> list[dict[str, Any]]:
        return self.tools.list_tools()

    def log_delivery(
        self,
        session_id: str,
        platform: str,
        request_body: dict[str, Any],
        result: dict[str, Any],
    ) -> None:
        status = "ok" if result.get("success") else "error"
        output = result.get("response_text") or result.get("error") or ""
        self.memory.log_tool_run(
            session_id,
            f"deliver:{platform}",
            request_body,
            status,
            str(output)[:4000],
            result,
        )

    def explain_route(
        self,
        channel: str,
        user: str = "user",
        account: str = "default",
        peer: str = "*",
        session_id: str | None = None,
    ) -> dict[str, Any]:
        route = self.route_resolver.resolve(
            RouteContext(
                session_id=session_id or "route-preview",
                channel=channel,
                user=user,
                account=account,
                peer=peer,
            )
        )
        return route.__dict__

    def explain_tool_policy(
        self,
        tool_name: str,
        permission: str,
        explicit_allow: list[str] | None = None,
    ) -> dict[str, Any]:
        spec = self.tools.spec(tool_name)
        decision = self.tool_policy.decide(spec, permission, explicit_allow or [])
        return decision.__dict__

    def recall_global(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        return self.memory.recall_global(query, limit=limit)

    def session_digest(self, session_id: str) -> dict[str, Any]:
        return self.memory.session_digest(session_id)

    def global_digest(self, limit: int = 10) -> dict[str, Any]:
        return self.memory.global_digest(limit=limit)

    def search_transcripts(self, query: str, limit: int = 20) -> list[dict[str, Any]]:
        return self.memory.search_transcripts(query, limit=limit)

    def user_profile(self) -> list[dict[str, Any]]:
        return self.memory.profile()

    def list_tasks(self, session_id: str | None = None, status: str | None = None) -> list[dict[str, Any]]:
        return self.memory.list_tasks(session_id=session_id, status=status)

    def list_delegations(self, session_id: str | None = None) -> list[dict[str, Any]]:
        return self.memory.list_delegations(session_id=session_id)

    def create_task(
        self,
        session_id: str,
        title: str,
        details: str = "",
        priority: str = "medium",
        owner: str = "main",
        parent_task_id: int | None = None,
    ) -> dict[str, Any]:
        task_id = self.memory.create_task(
            session_id,
            title=title,
            details=details,
            priority=priority,
            owner=owner,
            parent_task_id=parent_task_id,
        )
        return self.memory.get_task(task_id) or {"id": task_id}

    def update_task(self, task_id: int, **kwargs: Any) -> dict[str, Any]:
        self.memory.update_task(task_id, **kwargs)
        return self.memory.get_task(task_id) or {"id": task_id}

    def delegate_task(self, session_id: str, parent_task_id: int, details: str = "") -> dict[str, Any]:
        parent = self.memory.get_task(parent_task_id)
        if not parent:
            raise ValueError(f"task {parent_task_id} not found")
        child_title = f"Subtask for #{parent_task_id}: {parent['title']}"
        child_task_id = self.memory.create_task(
            session_id,
            title=child_title,
            details=details or parent.get("details", ""),
            owner="worker",
            parent_task_id=parent_task_id,
        )
        child_session_id = f"{session_id}-sub{child_task_id}"
        delegation_id = self.memory.delegate_task(
            session_id=session_id,
            parent_task_id=parent_task_id,
            child_task_id=child_task_id,
            child_session_id=child_session_id,
            role="worker",
            status="assigned",
            note=details,
        )
        self.memory.update_task(parent_task_id, status="delegated")
        self.memory.update_task(child_task_id, status="in_progress")
        return {
            "delegation_id": delegation_id,
            "parent_task_id": parent_task_id,
            "child_task_id": child_task_id,
            "child_session_id": child_session_id,
            "status": "assigned",
        }

    def plan_goal(self, session_id: str, goal: str) -> dict[str, Any]:
        parent = self.create_task(
            session_id,
            title=goal[:160],
            details=goal,
            priority="high",
            owner="planner",
        )
        self.memory.update_task(parent["id"], status="planned", owner="planner")

        steps, planner_meta = self._plan_steps(goal)
        children: list[dict[str, Any]] = []
        delegations: list[dict[str, Any]] = []
        for step in steps:
            child = self.create_task(
                session_id,
                title=step["title"],
                details=step["details"],
                priority=step["priority"],
                owner=step["owner"],
                parent_task_id=parent["id"],
            )
            children.append(child)
            if step["delegate"]:
                delegations.append(
                    self.delegate_task(
                        session_id=session_id,
                        parent_task_id=child["id"],
                        details=step["details"],
                    )
                )

        self.memory.remember(
            session_id,
            kind="plan",
            title=f"plan for task #{parent['id']}",
            content=f"Goal: {goal}\nSteps: " + " | ".join(step["title"] for step in steps),
            score=0.9,
        )
        return {
            "parent_task": parent,
            "steps": steps,
            "child_tasks": children,
            "delegations": delegations,
            "planner": planner_meta,
        }

    def _plan_steps(self, goal: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        payload, llm_result = self.llm.plan_json(
            PLANNER_SYSTEM,
            f"Goal: {goal}\nCreate a concrete execution plan.",
        )
        steps = self._normalize_planner_payload(payload) if payload else []
        if steps:
            return steps, {"mode": "llm", "model": llm_result.used_model, "offline": llm_result.offline}
        return self._derive_plan_steps(goal), {"mode": "rules", "model": llm_result.used_model, "offline": llm_result.offline}

    def _normalize_planner_payload(self, payload: dict[str, Any] | None) -> list[dict[str, Any]]:
        if not payload:
            return []
        raw_steps = payload.get("steps")
        if not isinstance(raw_steps, list):
            return []
        steps: list[dict[str, Any]] = []
        for item in raw_steps[:5]:
            if not isinstance(item, dict):
                continue
            title = str(item.get("title", "")).strip()
            details = str(item.get("details", "")).strip()
            if not title:
                continue
            priority = str(item.get("priority", "medium")).lower()
            if priority not in {"high", "medium", "low"}:
                priority = "medium"
            owner = str(item.get("owner", "worker")).lower()
            if owner not in {"worker", "planner"}:
                owner = "worker"
            delegate = bool(item.get("delegate", owner == "worker"))
            steps.append(
                {
                    "title": title,
                    "details": details or title,
                    "priority": priority,
                    "owner": owner,
                    "delegate": delegate,
                }
            )
        return steps

    def _derive_plan_steps(self, goal: str) -> list[dict[str, Any]]:
        text = goal.strip()
        lower = text.lower()
        if any(word in lower for word in ["release", "ship", "launch"]):
            return [
                {
                    "title": "Gather current state",
                    "details": f"Collect context and constraints for: {text}",
                    "priority": "high",
                    "owner": "worker",
                    "delegate": True,
                },
                {
                    "title": "Draft execution checklist",
                    "details": f"Produce a concrete checklist for: {text}",
                    "priority": "high",
                    "owner": "worker",
                    "delegate": True,
                },
                {
                    "title": "Review risks and blockers",
                    "details": f"Identify risks and open blockers for: {text}",
                    "priority": "medium",
                    "owner": "worker",
                    "delegate": True,
                },
            ]
        if any(word in lower for word in ["bug", "incident", "issue", "failure", "fix"]):
            return [
                {
                    "title": "Reconstruct the problem",
                    "details": f"Summarize symptoms and likely causes for: {text}",
                    "priority": "high",
                    "owner": "worker",
                    "delegate": True,
                },
                {
                    "title": "Propose remediation path",
                    "details": f"Suggest a fix path and verification steps for: {text}",
                    "priority": "high",
                    "owner": "worker",
                    "delegate": True,
                },
            ]
        if any(word in lower for word in ["plan", "roadmap", "strategy", "project"]):
            return [
                {
                    "title": "Define scope",
                    "details": f"Clarify the scope and success criteria for: {text}",
                    "priority": "high",
                    "owner": "worker",
                    "delegate": True,
                },
                {
                    "title": "Break work into milestones",
                    "details": f"Produce milestones and sequencing for: {text}",
                    "priority": "high",
                    "owner": "worker",
                    "delegate": True,
                },
                {
                    "title": "Identify dependencies",
                    "details": f"List dependencies and risks for: {text}",
                    "priority": "medium",
                    "owner": "worker",
                    "delegate": True,
                },
            ]
        return [
            {
                "title": "Understand the goal",
                "details": f"Restate and analyze: {text}",
                "priority": "high",
                "owner": "worker",
                "delegate": True,
            },
            {
                "title": "Propose next actions",
                "details": f"Recommend actionable next steps for: {text}",
                "priority": "medium",
                "owner": "worker",
                "delegate": True,
            },
        ]

    def run_next_delegation(self, session_id: str | None = None) -> dict[str, Any]:
        delegation = self.memory.next_pending_delegation(session_id=session_id)
        if not delegation:
            return {"status": "idle", "message": "No assigned delegations."}
        return self.run_delegation(delegation["id"])

    def run_delegation(self, delegation_id: int) -> dict[str, Any]:
        delegation = self.memory.get_delegation(delegation_id)
        if not delegation:
            raise ValueError(f"delegation {delegation_id} not found")
        parent_task = self.memory.get_task(delegation["parent_task_id"])
        child_task = self.memory.get_task(delegation["child_task_id"]) if delegation.get("child_task_id") else None
        if not parent_task or not child_task:
            raise ValueError(f"delegation {delegation_id} is missing linked tasks")

        self.memory.update_delegation_result(
            delegation_id,
            status="running",
            note="worker started",
            started=True,
        )
        self.memory.update_task(child_task["id"], status="in_progress", owner="worker")

        child_session_id = delegation["child_session_id"]
        parent_session = self.memory.get_session(parent_task["session_id"]) or {}
        workspace_root = str(parent_session.get("workspace") or self.config.workspace.root)
        self.memory.ensure_session(
            child_session_id,
            title=f"worker for task {child_task['id']}",
            route={
                "agent_id": "worker",
                "channel": "worker",
                "user": "worker",
                "account": "internal",
                "peer": f"task:{child_task['id']}",
                "permission": "read",
                "workspace": workspace_root,
            },
        )

        prompt = self._build_worker_prompt(parent_task, child_task, delegation)
        tool_results = self._execute_worker_tool_plan(
            child_session_id=child_session_id,
            workspace_root=workspace_root,
            parent_task=parent_task,
            child_task=child_task,
            delegation=delegation,
        )
        evidence_block = self._render_worker_evidence(tool_results)
        worker_messages = [
            {"role": "system", "content": WORKER_SYSTEM},
            {"role": "user", "content": f"{prompt}\n\nEvidence:\n{evidence_block}"},
        ]
        result = self.llm.chat(worker_messages)
        self.memory.append_turn(
            child_session_id,
            "user",
            f"{prompt}\n\nEvidence:\n{evidence_block}",
            channel="worker",
            skill="builder",
        )
        self.memory.append_turn(
            child_session_id,
            "assistant",
            result.text,
            channel="worker",
            skill="builder",
        )

        summary = {
            "delegation_id": delegation_id,
            "child_session_id": child_session_id,
            "child_task_id": child_task["id"],
            "parent_task_id": parent_task["id"],
            "result": result.text[:4000],
            "offline": result.offline,
            "tool_results": tool_results,
        }
        self.memory.update_delegation_result(
            delegation_id,
            status="completed",
            result=summary,
            note="worker completed",
            completed=True,
        )
        self.memory.update_task(child_task["id"], status="done", details=result.text[:4000])
        self.memory.update_task(parent_task["id"], status="in_progress")
        self.memory.remember(
            parent_task["session_id"],
            kind="delegation_result",
            title=f"delegation #{delegation_id}",
            content=result.text[:500],
            score=0.88,
        )
        self.memory.append_turn(
            parent_task["session_id"],
            "assistant",
            f"Worker completed delegated task #{child_task['id']}.\n{result.text[:1200]}",
            channel="worker-summary",
            skill="builder",
        )
        aggregation = self.aggregate_task(parent_task["id"])
        summary["aggregation"] = aggregation
        return summary

    def aggregate_task(self, task_id: int) -> dict[str, Any]:
        parent = self.memory.get_task(task_id)
        if not parent:
            raise ValueError(f"task {task_id} not found")
        children = self.memory.child_tasks(task_id)
        delegations = self.memory.delegations_for_parent_task(task_id)
        completed_children = [child for child in children if child["status"] == "done"]
        completed_delegations = [item for item in delegations if item["status"] == "completed"]
        if not completed_children and not completed_delegations:
            return {
                "task_id": task_id,
                "status": "idle",
                "message": "No completed subtasks to aggregate.",
            }

        evidence = []
        for child in completed_children:
            evidence.append(f"child #{child['id']}: {child['title']} -> {child['details'][:220]}")
        for item in completed_delegations:
            payload = item.get("result") or {}
            evidence.append(
                f"delegation #{item['id']}: {str(payload.get('result', ''))[:220]}"
            )

        synthesis = self._synthesize_aggregation(parent, evidence)
        self.memory.update_task(
            task_id,
            status="review",
            details=synthesis,
            owner="planner",
        )
        self.memory.remember(
            parent["session_id"],
            kind="aggregation",
            title=f"aggregation for task #{task_id}",
            content=synthesis[:600],
            score=0.92,
        )
        self.memory.append_turn(
            parent["session_id"],
            "assistant",
            synthesis,
            channel="aggregator",
            skill="builder",
        )
        return {
            "task_id": task_id,
            "status": "aggregated",
            "child_tasks": len(completed_children),
            "delegations": len(completed_delegations),
            "summary": synthesis,
        }

    def aggregate_next_task(self, session_id: str | None = None) -> dict[str, Any]:
        tasks = self.memory.list_tasks(session_id=session_id)
        for task in tasks:
            if task["status"] in {"delegated", "in_progress", "planned", "review"}:
                result = self.aggregate_task(task["id"])
                if result.get("status") != "idle":
                    return result
        return {"status": "idle", "message": "No aggregatable tasks found."}

    def inspect_worker_plan(
        self,
        task_id: int,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        task = self.memory.get_task(task_id)
        if not task:
            raise ValueError(f"task {task_id} not found")
        session = self.memory.get_session(task["session_id"]) or {}
        workspace_root = str(session.get("workspace") or self.config.workspace.root)
        delegation_text = " ".join(item.get("note", "") for item in self.memory.delegations_for_parent_task(task_id))
        text = " ".join([task.get("title", ""), task.get("details", ""), delegation_text]).strip()
        plan = self._worker_tool_plan(text, workspace_root)
        return {
            "task_id": task_id,
            "session_id": session_id or task["session_id"],
            "workspace_root": workspace_root,
            "plan": plan,
        }

    def worker_write(self, task_id: int, content: str) -> dict[str, Any]:
        task = self.memory.get_task(task_id)
        if not task:
            raise ValueError(f"task {task_id} not found")
        if task.get("owner") != "worker":
            raise ValueError("worker_write only applies to worker-owned tasks")
        session = self.memory.get_session(task["session_id"]) or {}
        workspace_root = Path(str(session.get("workspace") or self.config.workspace.root)).expanduser().resolve()
        if not content.strip():
            content = f"Draft content for {task['title']}\n"
        path = workspace_root / self._suggest_worker_file_name(task.get("details") or task["title"])
        pending = self.execute_tool(
            task["session_id"],
            "write_file",
            {"path": str(path), "content": content},
        )
        if isinstance(pending, dict) and "pending_approval" in pending:
            return {
                "status": "pending_approval",
                "task_id": task_id,
                "approval_id": pending["pending_approval"],
                "path": str(path),
            }
        if hasattr(pending, "tool_name"):
            result = {
                "status": pending.status,
                "task_id": task_id,
                "path": str(path),
                "tool_name": pending.tool_name,
                "metadata": pending.metadata,
            }
        else:
            result = pending
        if result.get("status") == "ok":
            self.memory.update_task(
                task_id,
                status="done",
                details=f"Wrote artifact at {path}",
                owner="worker",
            )
            self.memory.remember(
                task["session_id"],
                kind="artifact",
                title=f"artifact for task #{task_id}",
                content=f"{path}\n{content[:400]}",
                score=0.91,
            )
            self.memory.append_turn(
                task["session_id"],
                "assistant",
                f"Wrote artifact to {path}",
                channel="worker-write",
                skill="builder",
            )
        return result

    def _synthesize_aggregation(self, parent: dict[str, Any], evidence: list[str]) -> str:
        bullet_text = "\n".join(f"- {line}" for line in evidence[:10])
        return (
            f"Aggregation for task #{parent['id']} [{parent['title']}]\n"
            f"Current state: {parent['status']}\n"
            f"Evidence:\n{bullet_text}\n"
            "Conclusion: consolidate the worker outputs into the parent plan, then decide if another pass is needed."
        )

    def _build_worker_prompt(
        self,
        parent_task: dict[str, Any],
        child_task: dict[str, Any],
        delegation: dict[str, Any],
    ) -> str:
        return (
            f"Parent task #{parent_task['id']}: {parent_task['title']}\n"
            f"Parent details: {parent_task.get('details', '')}\n"
            f"Child task #{child_task['id']}: {child_task['title']}\n"
            f"Child details: {child_task.get('details', '')}\n"
            f"Delegation note: {delegation.get('note', '')}\n"
            "Produce a concise work result, next risks, and recommended next step."
        )

    def _session_workspace(self, session_id: str) -> str:
        session = self.memory.get_session(session_id) or {}
        return str(session.get("workspace") or self.config.workspace.root)

    def _execute_worker_tool_plan(
        self,
        child_session_id: str,
        workspace_root: str,
        parent_task: dict[str, Any],
        child_task: dict[str, Any],
        delegation: dict[str, Any],
    ) -> list[dict[str, Any]]:
        text = " ".join(
            [
                parent_task.get("title", ""),
                parent_task.get("details", ""),
                child_task.get("title", ""),
                child_task.get("details", ""),
                delegation.get("note", ""),
            ]
        ).strip()
        plan = self._worker_tool_plan(text, workspace_root)
        results: list[dict[str, Any]] = []
        for item in plan:
            tool_name = item["tool_name"]
            if tool_name not in {"read_file", "read_many", "search_code", "list_dir", "write_file", "make_dir"}:
                continue
            result = self._run_tool(child_session_id, tool_name, item["arguments"])
            results.append(
                {
                    "tool_name": result.tool_name,
                    "status": result.status,
                    "metadata": result.metadata,
                    "output": result.output[:1200],
                }
            )
            self.memory.append_turn(
                child_session_id,
                "assistant",
                f"[tool:{result.tool_name}] {result.output[:800]}",
                channel="worker-tool",
                skill="builder",
            )
        return results

    def _worker_tool_plan(self, text: str, workspace_root: str) -> list[dict[str, Any]]:
        lower = text.lower()
        plan: list[dict[str, Any]] = []
        write_intent = any(
            word in lower
            for word in [
                "create",
                "write",
                "draft file",
                "generate file",
                "save file",
                "draft",
                "notes",
                "markdown",
                "document",
                "doc",
                "file",
            ]
        )
        if write_intent:
            filename = self._suggest_worker_file_name(text)
            plan.append(
                {
                    "tool_name": "write_file",
                    "arguments": {
                        "path": str(Path(workspace_root) / filename),
                        "content": f"Draft generated from task context:\n{text}\n",
                    },
                }
            )
        if any(word in lower for word in ["inspect", "review", "analyze", "analyse", "debug", "investigate", "check"]):
            plan.append({"tool_name": "list_dir", "arguments": {"path": workspace_root}})

        path_hits = self._extract_paths(text)
        for path in path_hits:
            plan.append({"tool_name": "read_file", "arguments": {"path": path}})

        search_hits = self._extract_search_patterns(text)
        for pattern in search_hits:
            plan.append(
                {
                    "tool_name": "search_code",
                    "arguments": {"path": workspace_root, "pattern": pattern},
                }
            )

        if "files" in lower and not plan:
            plan.append(
                {
                    "tool_name": "read_many",
                    "arguments": {"path": workspace_root, "pattern": "*", "limit": 8},
                }
            )
        if not plan:
            plan.append({"tool_name": "list_dir", "arguments": {"path": workspace_root}})
        return plan[:5]

    def _suggest_worker_file_name(self, text: str) -> str:
        words = re.findall(r"[A-Za-z0-9]+", text.lower())
        selected = [word for word in words if len(word) > 3][:4]
        stem = "-".join(selected) if selected else "worker-draft"
        return f"{stem[:32]}.md"

    def _extract_paths(self, text: str) -> list[str]:
        candidates: list[str] = []
        for match in re.findall(r"`([^`]+)`", text):
            if any(sep in match for sep in ["/", "\\"]) or "." in Path(match).name:
                candidates.append(match)
        for token in re.findall(r"(?:\.{1,2}[\\/][^\s,;:]+|[A-Za-z]:[\\/][^\s,;:]+)", text):
            candidates.append(token)
        seen: set[str] = set()
        out: list[str] = []
        for item in candidates:
            item = item.strip().strip(",")
            if item and item not in seen:
                seen.add(item)
                out.append(item)
        return out

    def _extract_search_patterns(self, text: str) -> list[str]:
        patterns: list[str] = []
        quoted = re.findall(r"['\"]([^'\"]{2,80})['\"]", text)
        patterns.extend(quoted)
        for token in re.findall(r"\b[a-zA-Z0-9_\-]{4,}\b", text):
            if token.lower() not in {"inspect", "review", "analyze", "analyse", "debug", "investigate", "check", "task", "plan", "please"}:
                patterns.append(token)
        seen: set[str] = set()
        out: list[str] = []
        for item in patterns:
            item = item.strip()
            if item and item not in seen:
                seen.add(item)
                out.append(item)
        return out[:3]

    def _render_worker_evidence(self, tool_results: list[dict[str, Any]]) -> str:
        if not tool_results:
            return "No tools used."
        lines = []
        for item in tool_results:
            lines.append(
                f"- {item['tool_name']} [{item['status']}]: {item['output'][:240]}"
            )
        return "\n".join(lines)

    def execute_tool(self, session_id: str, tool_name: str, arguments: dict[str, Any]) -> ToolResult | dict[str, Any]:
        session = self.memory.get_session(session_id)
        if not session:
            self.memory.ensure_session(session_id, title="tool session")
            session = self.memory.get_session(session_id) or {}
        permission = str(session.get("permission") or "dangerous")
        spec = self.tools.spec(tool_name)
        policy = self.tool_policy.decide(spec, permission)
        if not policy.allowed:
            return {"error": policy.reason, "tool_name": tool_name}
        if self._tool_needs_approval(session_id, tool_name, policy):
            approval_id = self.memory.request_approval(
                session_id,
                tool_name,
                {"tool_name": tool_name, "arguments": arguments, "policy": policy.__dict__},
            )
            return {"pending_approval": approval_id, "tool_name": tool_name, "arguments": arguments}
        return self._run_tool(session_id, tool_name, arguments)

    def resolve_approval(self, approval_id: int, allow: bool, note: str = "") -> dict[str, Any]:
        approval = self.memory.get_approval(approval_id)
        if not approval:
            raise ValueError(f"approval {approval_id} not found")
        payload = json.loads(approval["payload_json"])
        result_payload: dict[str, Any] = {}
        if allow and "tool_name" in payload:
            tool_name = payload["tool_name"]
            tool_result = self._run_tool(
                approval["session_id"],
                tool_name,
                payload.get("arguments", {}),
            )
            result_payload = {
                "tool_name": tool_result.tool_name,
                "status": tool_result.status,
                "output": tool_result.output[:3000],
                "metadata": tool_result.metadata,
            }
            if self.config.approval.allow_session_tool_reuse:
                self.memory.grant_tool_reuse(approval["session_id"], tool_name)
            self.memory.append_turn(
                approval["session_id"],
                "assistant",
                self._format_tool_reply(tool_result),
                channel="approval",
                skill=payload.get("skill", "human"),
            )
        self.memory.decide_approval(
            approval_id,
            "approved" if allow else "denied",
            note,
            result=result_payload,
        )
        return {
            "approval_id": approval_id,
            "status": "approved" if allow else "denied",
            "result": result_payload,
        }

    def _infer_action(self, message: str) -> str:
        text = message.lower()
        if any(word in text for word in ["delete", "remove", "drop"]):
            return "dangerous"
        if any(word in text for word in ["write", "create", "save", "patch"]):
            return "write"
        if any(word in text for word in ["shell", "terminal", "command", "run"]):
            return "execute"
        if any(word in text for word in ["webhook", "http", "network", "call api"]):
            return "network"
        return "none"

    def _extract_memory(self, session_id: str, user_text: str, skill_name: str, source_turn_id: int) -> None:
        lower = user_text.lower()
        if "prefer" in lower or "remember" in lower:
            self.memory.remember(
                session_id,
                kind="preference",
                title="user preference",
                content=user_text[:400],
                score=0.95,
                source_turn_id=source_turn_id,
            )
            self._extract_profile(session_id, user_text, source_turn_id)
        if "todo" in lower or "next" in lower:
            self.memory.remember(
                session_id,
                kind="task",
                title="open task",
                content=user_text[:400],
                score=0.85,
                source_turn_id=source_turn_id,
            )
            self.memory.create_task(
                session_id,
                title=user_text[:120],
                details=user_text[:400],
                owner="main",
            )
        if skill_name == "builder":
            self.memory.remember(
                session_id,
                kind="workstream",
                title="implementation request",
                content=user_text[:400],
                score=0.7,
                source_turn_id=source_turn_id,
            )

    def _extract_assistant_memory(
        self,
        session_id: str,
        user_text: str,
        assistant_text: str,
        skill_name: str,
    ) -> None:
        if "decision" in assistant_text.lower() or "tradeoff" in assistant_text.lower():
            self.memory.remember(
                session_id,
                kind="decision",
                title=f"{skill_name} decision",
                content=assistant_text[:500],
                score=0.8,
            )

    def _extract_profile(self, session_id: str, user_text: str, source_turn_id: int) -> None:
        lower = user_text.lower()
        patterns = [
            ("favorite", "favorite"),
            ("prefer", "preference"),
            ("timezone", "timezone"),
            ("language", "language"),
            ("editor", "editor"),
            ("os", "os"),
        ]
        for needle, key in patterns:
            if needle in lower:
                self.memory.upsert_profile(key, user_text[:300], session_id, source_turn_id)
