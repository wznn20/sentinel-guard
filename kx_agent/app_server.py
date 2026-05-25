from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from .channels import ChannelHub
from .dashboard import HTML


class AppServer:
    def __init__(self, agent, host: str = "127.0.0.1", port: int = 8787):
        self.agent = agent
        self.host = host
        self.port = port
        self.channels = ChannelHub(
            stable_sessions=agent.config.channels.stable_sessions,
            adapters=agent.config.channels.adapters,
            adapter_secrets=agent.config.channels.adapter_secrets,
        )

    def overview(self) -> dict:
        sessions = self.agent.memory.search_sessions("", limit=20)
        tasks = self.agent.list_tasks()
        approvals = self.agent.memory.list_pending_approvals(100)
        return {
            "identity": self.agent.config.identity,
            "model": f"{self.agent.config.model.provider}/{self.agent.config.model.model}",
            "sessions": len(self.agent.memory.search_sessions("", limit=9999)),
            "tasks": len(tasks),
            "approvals": len(approvals),
            "recent_sessions": sessions[:5],
            "recent_tasks": tasks[:5],
            "adapters": self.channels.list_adapters(),
            "approvals_detail": approvals[:10],
            "delegations_detail": self.agent.list_delegations()[:10],
            "sandbox": {
                "profiles": self.agent.config.sandbox.profiles,
                "read_roots": self.agent.config.sandbox.read_roots,
                "write_roots": self.agent.config.sandbox.write_roots,
            },
            "dashboard": f"{self.host}:{self.port}",
        }

    def session_detail(self, session_id: str) -> dict:
        return {
            "session": self.agent.memory.get_session(session_id),
            "turns": self.agent.memory.list_turns(session_id, 200),
            "tree": self.agent.memory.session_tree(session_id),
            "tool_runs": self.agent.memory.list_tool_runs(session_id, 100),
            "tasks": self.agent.list_tasks(session_id=session_id),
            "delegations": self.agent.list_delegations(session_id=session_id),
        }

    def send_chat(
        self,
        session_id: str,
        message: str,
        channel: str = "dashboard",
        user: str = "dashboard",
        account: str = "default",
        peer: str = "*",
    ) -> dict:
        reply = self.agent.chat(
            message,
            session_id=session_id,
            channel=channel,
            user=user,
            account=account,
            peer=peer,
        )
        return reply.__dict__

    def serve(self) -> None:
        app = self
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
            def log_message(self, *args, **kwargs):
                return

            def _send_json(self, payload: dict, code: int = 200):
                body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
                self.send_response(code)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def _read_json(self) -> dict:
                length = int(self.headers.get("Content-Length", "0") or 0)
                raw = self.rfile.read(length).decode("utf-8") if length else "{}"
                return json.loads(raw or "{}")

            def do_GET(self):
                parsed = urlparse(self.path)
                path = parsed.path
                query = parse_qs(parsed.query)

                if path == "/":
                    body = HTML.encode("utf-8")
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                    return
                if path == "/api/overview":
                    return self._send_json(app.overview())
                if path == "/api/session":
                    sid = query.get("session_id", [""])[0]
                    return self._send_json(app.session_detail(sid))
                if path == "/health":
                    return self._send_json({"ok": True, "agent": "kx-agent"})
                if path == "/adapters":
                    return self._send_json({"adapters": channels.list_adapters()})
                if path == "/tasks":
                    return self._send_json(
                        {
                            "tasks": agent.list_tasks(
                                session_id=query.get("session_id", [None])[0],
                                status=query.get("status", [None])[0],
                            )
                        }
                    )
                if path == "/approvals":
                    return self._send_json({"approvals": agent.memory.list_pending_approvals(100)})
                if path.startswith("/webhook/"):
                    adapter_name = path.split("/", 2)[2]
                    flattened = {key: values[0] if isinstance(values, list) and values else values for key, values in query.items()}
                    proto = channels.protocol_response(adapter_name, {"query": flattened, **flattened})
                    if proto is not None:
                        if isinstance(proto, dict):
                            return self._send_json(proto)
                        return self._send_json({"response": proto})
                return self._send_json({"error": "not found"}, code=404)

            def do_POST(self):
                path = urlparse(self.path).path
                data = self._read_json()

                if path == "/api/plan":
                    return self._send_json(agent.plan_goal("dashboard", data["goal"]))
                if path == "/api/aggregate-next":
                    return self._send_json(agent.aggregate_next_task())
                if path == "/api/chat/send":
                    return self._send_json(
                        app.send_chat(
                            session_id=data["session_id"],
                            message=data["message"],
                            channel=data.get("channel", "dashboard"),
                            user=data.get("user", "dashboard"),
                            account=data.get("account", "default"),
                            peer=data.get("peer", "*"),
                        )
                    )
                if path == "/api/task/update":
                    return self._send_json(
                        agent.update_task(
                            int(data["task_id"]),
                            status=data.get("status"),
                            owner=data.get("owner"),
                            details=data.get("details"),
                            title=data.get("title"),
                            priority=data.get("priority"),
                        )
                    )
                if path == "/api/approval/decide":
                    return self._send_json(
                        agent.resolve_approval(
                            int(data["approval_id"]),
                            str(data.get("status", "approved")).lower() == "approved",
                            str(data.get("note", "")),
                        )
                    )
                if path == "/api/delegation/run":
                    return self._send_json(agent.run_delegation(int(data["delegation_id"])))
                if path == "/webhook/event":
                    code, payload = handle_event(str(data.get("adapter", "generic")), data)
                    return self._send_json(payload, code=code)
                if path.startswith("/webhook/"):
                    adapter_name = path.split("/", 2)[2]
                    code, payload = handle_event(adapter_name, data)
                    return self._send_json(payload, code=code)
                return self._send_json({"error": "not found"}, code=404)

        with ThreadingHTTPServer((self.host, self.port), Handler) as httpd:
            httpd.serve_forever()
