from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib import resources
from urllib.parse import parse_qs, urlparse


ASSET_PACKAGE = "kx_agent.dashboard_assets"
ASSET_TYPES = {
    "index.html": "text/html; charset=utf-8",
    "dashboard.css": "text/css; charset=utf-8",
    "dashboard.js": "application/javascript; charset=utf-8",
}


def _load_asset(name: str) -> bytes:
    return resources.files(ASSET_PACKAGE).joinpath(name).read_bytes()


class DashboardServer:
    def __init__(self, agent, host: str = "127.0.0.1", port: int = 8899):
        self.agent = agent
        self.host = host
        self.port = port

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
            "recent_sessions": sessions[:8],
            "recent_tasks": tasks[:8],
            "adapters": self.agent.config.channels.adapters,
            "approvals_detail": approvals[:12],
            "delegations_detail": self.agent.list_delegations()[:12],
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

    def send_chat(self, session_id: str, message: str) -> dict:
        reply = self.agent.chat(message, session_id=session_id, channel="dashboard", user="dashboard")
        return reply.__dict__

    def serve(self) -> None:
        dashboard = self

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

            def _send_asset(self, asset_name: str, code: int = 200):
                body = _load_asset(asset_name)
                self.send_response(code)
                self.send_header("Content-Type", ASSET_TYPES[asset_name])
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                parsed = urlparse(self.path)
                path = parsed.path
                query = parse_qs(parsed.query)

                if path == "/":
                    return self._send_asset("index.html")
                if path == "/assets/dashboard.css":
                    return self._send_asset("dashboard.css")
                if path == "/assets/dashboard.js":
                    return self._send_asset("dashboard.js")
                if path == "/api/overview":
                    return self._send_json(dashboard.overview())
                if path == "/api/session":
                    sid = query.get("session_id", [""])[0]
                    return self._send_json(dashboard.session_detail(sid))
                return self._send_json({"error": "not found"}, code=404)

            def do_POST(self):
                length = int(self.headers.get("Content-Length", "0") or 0)
                raw = self.rfile.read(length).decode("utf-8") if length else "{}"
                data = json.loads(raw or "{}")
                if self.path == "/api/plan":
                    return self._send_json(dashboard.agent.plan_goal("dashboard", data["goal"]))
                if self.path == "/api/aggregate-next":
                    return self._send_json(dashboard.agent.aggregate_next_task())
                if self.path == "/api/task/update":
                    return self._send_json(
                        dashboard.agent.update_task(
                            int(data["task_id"]),
                            status=data.get("status"),
                            owner=data.get("owner"),
                            details=data.get("details"),
                            title=data.get("title"),
                            priority=data.get("priority"),
                        )
                    )
                if self.path == "/api/approval/decide":
                    return self._send_json(
                        dashboard.agent.resolve_approval(
                            int(data["approval_id"]),
                            str(data.get("status", "approved")).lower() == "approved",
                            str(data.get("note", "")),
                        )
                    )
                if self.path == "/api/delegation/run":
                    return self._send_json(dashboard.agent.run_delegation(int(data["delegation_id"])))
                if self.path == "/api/chat/send":
                    return self._send_json(dashboard.send_chat(data["session_id"], data["message"]))
                return self._send_json({"error": "not found"}, code=404)

        with ThreadingHTTPServer((self.host, self.port), Handler) as httpd:
            httpd.serve_forever()
