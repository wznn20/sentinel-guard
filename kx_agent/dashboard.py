from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>KX Dashboard</title>
  <style>
    body { font-family: ui-sans-serif, system-ui, sans-serif; background:#0b1220; color:#e5eefc; margin:0; }
    .wrap { max-width:1200px; margin:0 auto; padding:32px 20px 60px; }
    .grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(220px,1fr)); gap:16px; }
    .card { background:#121b2e; border:1px solid #223252; border-radius:16px; padding:18px; }
    .row { display:flex; gap:12px; flex-wrap:wrap; margin:12px 0 18px; }
    button { background:#1d4ed8; color:#fff; border:none; border-radius:10px; padding:10px 14px; cursor:pointer; }
    button.secondary { background:#243149; }
    input, select { background:#0a1324; color:#e5eefc; border:1px solid #223252; border-radius:10px; padding:10px 12px; }
    h1,h2 { margin:0 0 12px 0; }
    .muted { color:#9fb3d1; }
    pre { white-space:pre-wrap; word-break:break-word; background:#09111f; padding:12px; border-radius:12px; overflow:auto; }
    table { width:100%; border-collapse:collapse; }
    td,th { border-bottom:1px solid #223252; padding:8px 6px; text-align:left; font-size:14px; }
    .pill { display:inline-block; padding:4px 8px; border:1px solid #345; border-radius:999px; font-size:12px; color:#9fb3d1; }
    .msg { padding:10px 12px; border-radius:12px; margin-bottom:8px; }
    .msg.user { background:#13213d; }
    .msg.assistant { background:#10192c; }
    .msg.tool { background:#102824; border-left:3px solid #0ea5a3; }
    .msg.approval { background:#2a1d10; border-left:3px solid #f59e0b; }
    .msg.worker { background:#20123a; border-left:3px solid #8b5cf6; }
    .msg .meta { font-size:12px; color:#9fb3d1; margin-bottom:4px; }
  </style>
</head>
<body>
  <div class="wrap">
    <h1>KX Agent Dashboard</h1>
    <p class="muted">Live local runtime state with quick actions</p>
    <div class="row">
      <input id="goal" placeholder="Goal for planning..." style="min-width:280px;flex:1">
      <select id="sessionSelect" onchange="loadSession()"><option value="">Select session…</option></select>
      <button onclick="plan()">Plan Goal</button>
      <button class="secondary" onclick="aggregateNext()">Aggregate Next</button>
      <button class="secondary" onclick="refresh()">Refresh</button>
    </div>
    <div class="row">
      <input id="chatMessage" placeholder="Send a message to the selected session..." style="min-width:420px;flex:1">
      <button onclick="sendChat()">Send Message</button>
    </div>
    <div id="app">Loading…</div>
  </div>
  <script>
    async function api(path, body) {
      const opts = body ? {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(body)} : {};
      const res = await fetch(path, opts);
      return await res.json();
    }
    async function refresh() {
      const data = await api('/api/overview');
      const app = document.getElementById('app');
      app.innerHTML = `
        <div class="grid">
          <div class="card"><h2>Identity</h2><div>${data.identity}</div><div class="muted">${data.model}</div><div class="pill">${data.dashboard}</div></div>
          <div class="card"><h2>Sessions</h2><div>${data.sessions}</div></div>
          <div class="card"><h2>Tasks</h2><div>${data.tasks}</div></div>
          <div class="card"><h2>Approvals</h2><div>${data.approvals}</div></div>
        </div>
        <div class="grid" style="margin-top:16px">
          <div class="card">
            <h2>Recent Sessions</h2>
            <table><thead><tr><th>ID</th><th>Agent</th><th>Channel</th><th>Summary</th></tr></thead><tbody>
              ${data.recent_sessions.map(row => `<tr><td>${row.session_id}</td><td>${row.agent_id}</td><td>${row.channel}</td><td>${row.summary || ''}</td></tr>`).join('')}
            </tbody></table>
          </div>
          <div class="card">
            <h2>Recent Tasks</h2>
            <table><thead><tr><th>ID</th><th>Status</th><th>Owner</th><th>Title</th><th>Action</th></tr></thead><tbody>
              ${data.recent_tasks.map(row => `<tr><td>${row.id}</td><td>${row.status}</td><td>${row.owner}</td><td>${row.title}</td><td><button class="secondary" onclick="markReview(${row.id})">Review</button></td></tr>`).join('')}
            </tbody></table>
          </div>
        </div>
        <div class="grid" style="margin-top:16px">
          <div class="card">
            <h2>Approvals</h2>
            <table><thead><tr><th>ID</th><th>Action</th><th>Session</th><th>Action</th></tr></thead><tbody>
              ${data.approvals_detail.map(row => `<tr><td>${row.id}</td><td>${row.action}</td><td>${row.session_id}</td><td><button onclick="approve(${row.id}, true)">Approve</button> <button class="secondary" onclick="approve(${row.id}, false)">Deny</button></td></tr>`).join('')}
            </tbody></table>
          </div>
          <div class="card">
            <h2>Delegations</h2>
            <table><thead><tr><th>ID</th><th>Status</th><th>Child Task</th><th>Action</th></tr></thead><tbody>
              ${data.delegations_detail.map(row => `<tr><td>${row.id}</td><td>${row.status}</td><td>${row.child_task_id || ''}</td><td><button class="secondary" onclick="runDelegation(${row.id})">Run</button></td></tr>`).join('')}
            </tbody></table>
          </div>
        </div>
        <div class="grid" style="margin-top:16px">
          <div class="card"><h2>Adapters</h2><pre>${JSON.stringify(data.adapters, null, 2)}</pre></div>
          <div class="card"><h2>Sandbox</h2><pre>${JSON.stringify(data.sandbox, null, 2)}</pre></div>
        </div>
        <div class="grid" style="margin-top:16px">
          <div class="card"><h2>Session Transcript</h2><pre id="sessionTurns">Select a session.</pre></div>
          <div class="card"><h2>Session Memory Tree</h2><pre id="sessionTree">Select a session.</pre></div>
        </div>
        <div class="grid" style="margin-top:16px">
          <div class="card"><h2>Tool Runs</h2><pre id="sessionTools">Select a session.</pre></div>
          <div class="card"><h2>Session Tasks</h2><pre id="sessionTasks">Select a session.</pre></div>
        </div>
      `;
      const select = document.getElementById('sessionSelect');
      const prev = select.value;
      select.innerHTML = '<option value="">Select session…</option>' + data.recent_sessions.map(row => `<option value="${row.session_id}">${row.session_id}</option>`).join('');
      if (prev) { select.value = prev; await loadSession(); }
    }
    async function plan() {
      const goal = document.getElementById('goal').value;
      if (!goal.trim()) return;
      await api('/api/plan', {goal});
      await refresh();
    }
    async function aggregateNext() {
      await api('/api/aggregate-next', {});
      await refresh();
    }
    async function markReview(taskId) {
      await api('/api/task/update', {task_id: taskId, status: 'review'});
      await refresh();
    }
    async function approve(id, allow) {
      await api('/api/approval/decide', {approval_id: id, status: allow ? 'approved' : 'denied'});
      await refresh();
    }
    async function runDelegation(id) {
      await api('/api/delegation/run', {delegation_id: id});
      await refresh();
    }
    async function loadSession() {
      const id = document.getElementById('sessionSelect').value;
      if (!id) return;
      const data = await fetch('/api/session?session_id=' + encodeURIComponent(id)).then(r => r.json());
      document.getElementById('sessionTurns').innerHTML = (data.turns || []).map(turn => {
        let cls = turn.role;
        const ch = String(turn.channel || '');
        if (ch.includes('tool')) cls = 'tool';
        else if (ch.includes('approval')) cls = 'approval';
        else if (ch.includes('worker')) cls = 'worker';
        return `
        <div class="msg ${cls}">
          <div class="meta">${turn.role} · ${turn.skill || '-'} · ${turn.created_at || ''}</div>
          <div>${String(turn.content || '').replaceAll('<','&lt;').replaceAll('>','&gt;')}</div>
        </div>
      `}).join('') || 'No turns.';
      document.getElementById('sessionTree').textContent = JSON.stringify(data.tree, null, 2);
      document.getElementById('sessionTools').textContent = JSON.stringify(data.tool_runs, null, 2);
      document.getElementById('sessionTasks').textContent = JSON.stringify(data.tasks, null, 2);
    }
    async function sendChat() {
      const id = document.getElementById('sessionSelect').value;
      const message = document.getElementById('chatMessage').value;
      if (!id || !message.trim()) return;
      await api('/api/chat/send', {session_id: id, message});
      document.getElementById('chatMessage').value = '';
      await refresh();
      document.getElementById('sessionSelect').value = id;
      await loadSession();
    }
    refresh();
    setInterval(refresh, 5000);
  </script>
</body>
</html>
"""


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
            "recent_sessions": sessions[:5],
            "recent_tasks": tasks[:5],
            "adapters": self.agent.config.channels.adapters,
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

            def do_GET(self):
                if self.path == "/":
                    body = HTML.encode("utf-8")
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                    return
                if self.path == "/api/overview":
                    return self._send_json(dashboard.overview())
                if self.path.startswith("/api/session?session_id="):
                    import urllib.parse

                    query = urllib.parse.urlparse(self.path).query
                    params = urllib.parse.parse_qs(query)
                    sid = params.get("session_id", [""])[0]
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
