from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from .channels import ChannelHub


class GatewayServer:
    def __init__(self, agent, host: str = "127.0.0.1", port: int = 8787):
        self.agent = agent
        self.host = host
        self.port = port
        self.channels = ChannelHub(
            stable_sessions=agent.config.channels.stable_sessions,
            adapters=agent.config.channels.adapters,
        )

    def serve(self) -> None:
        agent = self.agent
        channels = self.channels

        def handle_event(adapter_name: str, data: dict):
            proto = channels.protocol_response(adapter_name, data)
            if proto is not None:
                return 200, proto
            event = channels.event_from(adapter_name, data)
            if channels.requires_verification(adapter_name) and not event.verified:
                return 403, {"error": "adapter verification failed", "event": event.__dict__}
            reply = agent.chat(
                event.text,
                session_id=channels.session_id_for(event) or data.get("session_id"),
                channel=event.channel,
                user=event.user,
                account=event.account,
                peer=event.peer,
            )
            plan, result = agent.delivery.send_reply(event, reply.reply)
            reply.delivery_plan = plan.__dict__
            reply.delivery_result = result.__dict__
            sid = reply.session_id
            agent.log_delivery(sid, plan.platform, plan.body, result.__dict__)
            payload = {"event": event.__dict__, "reply": reply.__dict__, "delivery_plan": plan.__dict__, "delivery_result": result.__dict__}
            code = 200 if result.success else 502
            return code, payload

        class Handler(BaseHTTPRequestHandler):
            def _send(self, code: int, payload: dict):
                body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
                self.send_response(code)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args, **kwargs):
                return

            def do_GET(self):
                parsed = urlparse(self.path)
                path = parsed.path
                query = parse_qs(parsed.query)
                if path == "/health":
                    return self._send(200, {"ok": True, "agent": "kx-agent"})
                if path == "/skills":
                    return self._send(200, {"skills": agent.skills.list()})
                if path == "/adapters":
                    return self._send(200, {"adapters": channels.list_adapters()})
                if path == "/tools":
                    return self._send(200, {"tools": agent.list_tools()})
                if path == "/recall":
                    q = query.get("q", [""])[0]
                    limit = int(query.get("limit", ["10"])[0])
                    return self._send(200, {"memories": agent.recall_global(q, limit=limit)})
                if path == "/transcripts":
                    q = query.get("q", [""])[0]
                    limit = int(query.get("limit", ["20"])[0])
                    return self._send(200, {"turns": agent.search_transcripts(q, limit=limit)})
                if path == "/profile":
                    return self._send(200, {"profile": agent.user_profile()})
                if path == "/global-digest":
                    limit = int(query.get("limit", ["10"])[0])
                    return self._send(200, agent.global_digest(limit=limit))
                if path == "/tasks":
                    return self._send(
                        200,
                        {
                            "tasks": agent.list_tasks(
                                session_id=query.get("session_id", [None])[0],
                                status=query.get("status", [None])[0],
                            )
                        },
                    )
                if path == "/delegations":
                    return self._send(
                        200,
                        {"delegations": agent.list_delegations(session_id=query.get("session_id", [None])[0])},
                    )
                if path == "/delegations/run-next":
                    return self._send(
                        200,
                        agent.run_next_delegation(session_id=query.get("session_id", [None])[0]),
                    )
                if path == "/tasks/aggregate":
                    return self._send(
                        200,
                        agent.aggregate_task(int(query.get("task_id", ["0"])[0])),
                    )
                if path == "/tasks/aggregate-next":
                    return self._send(
                        200,
                        agent.aggregate_next_task(session_id=query.get("session_id", [None])[0]),
                    )
                if path == "/tasks/inspect":
                    return self._send(
                        200,
                        agent.inspect_worker_plan(
                            int(query.get("task_id", ["0"])[0]),
                            session_id=query.get("session_id", [None])[0],
                        ),
                    )
                if path == "/sessions":
                    q = query.get("q", [""])[0]
                    limit = int(query.get("limit", ["20"])[0])
                    return self._send(200, {"sessions": agent.memory.search_sessions(q, limit=limit)})
                if path == "/route":
                    return self._send(
                        200,
                        agent.explain_route(
                            channel=query.get("channel", ["cli"])[0],
                            user=query.get("user", ["user"])[0],
                            account=query.get("account", ["default"])[0],
                            peer=query.get("peer", ["*"])[0],
                        ),
                    )
                if path == "/policy":
                    tool_name = query.get("tool_name", [""])[0]
                    permission = query.get("permission", ["read"])[0]
                    allow = query.get("allow", [])
                    return self._send(
                        200,
                        agent.explain_tool_policy(tool_name, permission, allow),
                    )
                if path.startswith("/memory/"):
                    session_id = path.split("/", 2)[2]
                    return self._send(200, agent.memory.session_tree(session_id))
                if path.startswith("/digest/"):
                    session_id = path.split("/", 2)[2]
                    return self._send(200, agent.session_digest(session_id))
                if path.startswith("/sessions/"):
                    session_id = path.split("/", 2)[2]
                    return self._send(
                        200,
                        {
                            "session": agent.memory.get_session(session_id),
                            "turns": agent.memory.list_turns(session_id, 100),
                            "tool_runs": agent.memory.list_tool_runs(session_id, 50),
                        },
                    )
                if path == "/approvals":
                    return self._send(200, {"approvals": agent.memory.list_pending_approvals(100)})
                if path.startswith("/webhook/"):
                    adapter_name = path.split("/", 2)[2]
                    flattened = {key: values[0] if isinstance(values, list) and values else values for key, values in query.items()}
                    proto = channels.protocol_response(adapter_name, {"query": flattened, **flattened})
                    if proto is not None:
                        if isinstance(proto, dict):
                            return self._send(200, proto)
                        return self._send(200, {"response": proto})
                self._send(404, {"error": "not found"})

            def do_POST(self):
                path = urlparse(self.path).path
                length = int(self.headers.get("Content-Length", "0") or 0)
                raw = self.rfile.read(length).decode("utf-8") if length else "{}"
                data = json.loads(raw or "{}")
                if path == "/chat":
                    reply = agent.chat(
                        data.get("message", ""),
                        session_id=data.get("session_id"),
                        channel=data.get("channel", "gateway"),
                        user=data.get("user", "gateway"),
                        account=data.get("account", "default"),
                        peer=data.get("peer", "*"),
                    )
                    return self._send(200, reply.__dict__)
                if path == "/webhook/event":
                    code, payload = handle_event(str(data.get("adapter", "generic")), data)
                    return self._send(code, payload)
                if path.startswith("/webhook/"):
                    adapter_name = path.split("/", 2)[2]
                    code, payload = handle_event(adapter_name, data)
                    return self._send(code, payload)
                if path == "/tool/run":
                    result = agent.execute_tool(
                        data["session_id"],
                        data["tool_name"],
                        data.get("arguments", {}),
                    )
                    if hasattr(result, "tool_name"):
                        payload = {
                            "tool_name": result.tool_name,
                            "status": result.status,
                            "output": result.output,
                            "metadata": result.metadata,
                        }
                    else:
                        payload = result
                    return self._send(200, payload)
                if path == "/task/create":
                    return self._send(
                        200,
                        agent.create_task(
                            data["session_id"],
                            title=data["title"],
                            details=data.get("details", ""),
                            priority=data.get("priority", "medium"),
                        ),
                    )
                if path == "/task/plan":
                    return self._send(
                        200,
                        agent.plan_goal(
                            session_id=data["session_id"],
                            goal=data["goal"],
                        ),
                    )
                if path == "/task/update":
                    return self._send(
                        200,
                        agent.update_task(
                            int(data["task_id"]),
                            status=data.get("status"),
                            owner=data.get("owner"),
                            details=data.get("details"),
                            title=data.get("title"),
                            priority=data.get("priority"),
                        ),
                    )
                if path == "/task/delegate":
                    return self._send(
                        200,
                        agent.delegate_task(
                            session_id=data["session_id"],
                            parent_task_id=int(data["task_id"]),
                            details=data.get("details", ""),
                        ),
                    )
                if path == "/delegation/run":
                    return self._send(
                        200,
                        agent.run_delegation(int(data["delegation_id"])),
                    )
                if path == "/task/aggregate":
                    return self._send(
                        200,
                        agent.aggregate_task(int(data["task_id"])),
                    )
                if path == "/task/aggregate-next":
                    return self._send(
                        200,
                        agent.aggregate_next_task(session_id=data.get("session_id")),
                    )
                if path == "/task/inspect":
                    return self._send(
                        200,
                        agent.inspect_worker_plan(
                            int(data["task_id"]),
                            session_id=data.get("session_id"),
                        ),
                    )
                if path == "/worker/write":
                    return self._send(
                        200,
                        agent.worker_write(int(data["task_id"]), data.get("content", "")),
                    )
                if path == "/approvals/decide":
                    result = agent.resolve_approval(
                        int(data["approval_id"]),
                        str(data.get("status", "approved")).lower() == "approved",
                        str(data.get("note", "")),
                    )
                    return self._send(200, result)
                self._send(404, {"error": "not found"})

        try:
            with ThreadingHTTPServer((self.host, self.port), Handler) as httpd:
                httpd.serve_forever()
        except PermissionError as exc:
            raise RuntimeError(
                f"Cannot bind gateway on {self.host}:{self.port} in the current environment: {exc}"
            ) from exc
