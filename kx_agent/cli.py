from __future__ import annotations

import json
import sys
import uuid
from pathlib import Path

import click

from .agent import KXAgent
from .app_server import AppServer
from .dashboard import DashboardServer
from .config import KXConfig
from .gateway import GatewayServer


HOME = Path.home() / ".kx"
CONFIG_FILE = HOME / "config.yaml"


def _agent() -> KXAgent:
    return KXAgent(CONFIG_FILE if CONFIG_FILE.exists() else None)


@click.group()
@click.version_option(version="0.2.0", prog_name="kx")
def cli():
    """KX Agent."""


@cli.command()
def setup():
    HOME.mkdir(parents=True, exist_ok=True)
    cfg = KXConfig()
    cfg.save(CONFIG_FILE)
    (HOME / "skills").mkdir(parents=True, exist_ok=True)
    click.echo(f"Saved {CONFIG_FILE}")
    click.echo("Edit the config, then run `kx chat` or `kx serve`.")


@cli.command()
@click.option("--session", "session_id", default=None)
@click.option("--channel", default="cli")
@click.option("--user", default="user")
@click.option("--account", default="default")
@click.option("--peer", default="*")
def chat(session_id, channel, user, account, peer):
    agent = _agent()
    session_id = session_id or uuid.uuid4().hex[:12]
    click.echo(f"KX Agent session: {session_id}")
    while True:
        try:
            text = click.prompt("You", prompt_suffix=" > ")
        except (EOFError, KeyboardInterrupt):
            break
        if text.strip().lower() in {"/quit", "/exit", "quit", "exit"}:
            break
        reply = agent.chat(
            text,
            session_id=session_id,
            channel=channel,
            user=user,
            account=account,
            peer=peer,
        )
        click.echo(f"[{reply.route['agent_id']}:{reply.skill}/{reply.model}] {reply.reply}")


@cli.command()
def skills():
    agent = _agent()
    for skill in agent.skills.list():
        click.echo(
            f"{skill['name']}: {skill['description']}  [{', '.join(skill['trigger_terms'])}]"
        )


@cli.command()
@click.option("--session", "session_id", required=True)
def memory(session_id):
    agent = _agent()
    click.echo(json.dumps(agent.memory.session_tree(session_id), ensure_ascii=False, indent=2))


@cli.command()
@click.option("--query", required=True)
@click.option("--limit", default=10, type=int)
def recall(query, limit):
    agent = _agent()
    click.echo(json.dumps(agent.recall_global(query, limit=limit), ensure_ascii=False, indent=2))


@cli.command("transcripts")
@click.option("--query", required=True)
@click.option("--limit", default=20, type=int)
def transcripts(query, limit):
    agent = _agent()
    click.echo(json.dumps(agent.search_transcripts(query, limit=limit), ensure_ascii=False, indent=2))


@cli.command("profile")
def profile_cmd():
    agent = _agent()
    click.echo(json.dumps(agent.user_profile(), ensure_ascii=False, indent=2))


@cli.command("global-digest")
@click.option("--limit", default=10, type=int)
def global_digest(limit):
    agent = _agent()
    click.echo(json.dumps(agent.global_digest(limit=limit), ensure_ascii=False, indent=2))


@cli.command()
@click.option("--session", "session_id", required=True)
def digest(session_id):
    agent = _agent()
    click.echo(json.dumps(agent.session_digest(session_id), ensure_ascii=False, indent=2))


@cli.command()
@click.option("--query", default="")
@click.option("--limit", default=20, type=int)
def sessions(query, limit):
    agent = _agent()
    rows = agent.memory.search_sessions(query, limit=limit)
    for row in rows:
        click.echo(
            f"{row['session_id']}  {row['updated_at']}  "
            f"{row['agent_id']}:{row['channel']}  {row['title']}  {row['summary'][:80]}"
        )


@cli.group("task")
def task_group():
    """Manage the KX task board."""


@task_group.command("list")
@click.option("--session", "session_id", default=None)
@click.option("--status", default=None)
def task_list(session_id, status):
    agent = _agent()
    click.echo(json.dumps(agent.list_tasks(session_id=session_id, status=status), ensure_ascii=False, indent=2))


@task_group.command("add")
@click.option("--session", "session_id", required=True)
@click.option("--title", required=True)
@click.option("--details", default="")
@click.option("--priority", default="medium")
def task_add(session_id, title, details, priority):
    agent = _agent()
    click.echo(
        json.dumps(
            agent.create_task(session_id, title=title, details=details, priority=priority),
            ensure_ascii=False,
            indent=2,
        )
    )


@task_group.command("plan")
@click.option("--session", "session_id", required=True)
@click.option("--goal", required=True)
def task_plan(session_id, goal):
    agent = _agent()
    click.echo(json.dumps(agent.plan_goal(session_id=session_id, goal=goal), ensure_ascii=False, indent=2))


@task_group.command("update")
@click.argument("task_id", type=int)
@click.option("--status", default=None)
@click.option("--owner", default=None)
@click.option("--details", default=None)
@click.option("--title", default=None)
@click.option("--priority", default=None)
def task_update(task_id, status, owner, details, title, priority):
    agent = _agent()
    click.echo(
        json.dumps(
            agent.update_task(
                task_id,
                status=status,
                owner=owner,
                details=details,
                title=title,
                priority=priority,
            ),
            ensure_ascii=False,
            indent=2,
        )
    )


@task_group.command("delegate")
@click.option("--session", "session_id", required=True)
@click.option("--task-id", required=True, type=int)
@click.option("--details", default="")
def task_delegate(session_id, task_id, details):
    agent = _agent()
    click.echo(
        json.dumps(
            agent.delegate_task(session_id=session_id, parent_task_id=task_id, details=details),
            ensure_ascii=False,
            indent=2,
        )
    )


@task_group.command("delegations")
@click.option("--session", "session_id", default=None)
def task_delegations(session_id):
    agent = _agent()
    click.echo(json.dumps(agent.list_delegations(session_id=session_id), ensure_ascii=False, indent=2))


@task_group.command("run")
@click.argument("delegation_id", type=int)
def task_run(delegation_id):
    agent = _agent()
    click.echo(json.dumps(agent.run_delegation(delegation_id), ensure_ascii=False, indent=2))


@task_group.command("run-next")
@click.option("--session", "session_id", default=None)
def task_run_next(session_id):
    agent = _agent()
    click.echo(json.dumps(agent.run_next_delegation(session_id=session_id), ensure_ascii=False, indent=2))


@task_group.command("aggregate")
@click.argument("task_id", type=int)
def task_aggregate(task_id):
    agent = _agent()
    click.echo(json.dumps(agent.aggregate_task(task_id), ensure_ascii=False, indent=2))


@task_group.command("aggregate-next")
@click.option("--session", "session_id", default=None)
def task_aggregate_next(session_id):
    agent = _agent()
    click.echo(json.dumps(agent.aggregate_next_task(session_id=session_id), ensure_ascii=False, indent=2))


@task_group.command("inspect")
@click.argument("task_id", type=int)
@click.option("--session", "session_id", default=None)
def task_inspect(task_id, session_id):
    agent = _agent()
    click.echo(json.dumps(agent.inspect_worker_plan(task_id, session_id=session_id), ensure_ascii=False, indent=2))


@task_group.command("write")
@click.argument("task_id", type=int)
@click.option("--content", default="")
def task_write(task_id, content):
    agent = _agent()
    click.echo(json.dumps(agent.worker_write(task_id, content), ensure_ascii=False, indent=2))


@cli.command()
@click.option("--channel", required=True)
@click.option("--user", default="user")
@click.option("--account", default="default")
@click.option("--peer", default="*")
def route(channel, user, account, peer):
    agent = _agent()
    click.echo(
        json.dumps(
            agent.explain_route(channel=channel, user=user, account=account, peer=peer),
            ensure_ascii=False,
            indent=2,
        )
    )


@cli.command()
@click.option("--tool-name", required=True)
@click.option("--permission", required=True)
@click.option("--allow", "allow_list", multiple=True)
def policy(tool_name, permission, allow_list):
    agent = _agent()
    click.echo(
        json.dumps(
            agent.explain_tool_policy(tool_name, permission, list(allow_list)),
            ensure_ascii=False,
            indent=2,
        )
    )


@cli.group()
def approve():
    """Manage pending approvals."""


@approve.command("list")
def approve_list():
    agent = _agent()
    rows = agent.memory.list_pending_approvals()
    if not rows:
        click.echo("No pending approvals.")
        return
    for row in rows:
        click.echo(
            f"{row['id']}: {row['action']}  session={row['session_id']}  payload={row['payload_json']}"
        )


@approve.command("allow")
@click.argument("approval_id", type=int)
@click.option("--note", default="")
def approve_allow(approval_id, note):
    agent = _agent()
    result = agent.resolve_approval(approval_id, True, note)
    click.echo(json.dumps(result, ensure_ascii=False, indent=2))


@approve.command("deny")
@click.argument("approval_id", type=int)
@click.option("--note", default="")
def approve_deny(approval_id, note):
    agent = _agent()
    result = agent.resolve_approval(approval_id, False, note)
    click.echo(json.dumps(result, ensure_ascii=False, indent=2))


@cli.group()
def tool():
    """Run or inspect KX tools."""


@tool.command("list")
def tool_list():
    agent = _agent()
    click.echo(json.dumps(agent.list_tools(), ensure_ascii=False, indent=2))


@tool.command("run")
@click.argument("tool_name")
@click.argument("arguments_json")
@click.option("--session", "session_id", default="tool-session")
def tool_run(tool_name, arguments_json, session_id):
    agent = _agent()
    result = agent.execute_tool(session_id, tool_name, json.loads(arguments_json))
    if hasattr(result, "tool_name"):
        payload = {
            "tool_name": result.tool_name,
            "status": result.status,
            "output": result.output,
            "metadata": result.metadata,
        }
    else:
        payload = result
    click.echo(json.dumps(payload, ensure_ascii=False, indent=2))


@tool.command("history")
@click.option("--session", "session_id", required=True)
def tool_history(session_id):
    agent = _agent()
    click.echo(json.dumps(agent.memory.list_tool_runs(session_id), ensure_ascii=False, indent=2))


@cli.command()
@click.option("--host", default=None)
@click.option("--port", type=int, default=None)
def serve(host, port):
    agent = _agent()
    server = GatewayServer(
        agent,
        host=host or agent.config.gateway.host,
        port=port or agent.config.gateway.port,
    )
    click.echo(f"Serving KX Agent on http://{server.host}:{server.port}")
    try:
        server.serve()
    except RuntimeError as exc:
        raise click.ClickException(str(exc)) from exc


@cli.command()
@click.option("--host", default="127.0.0.1")
@click.option("--port", type=int, default=8787)
def app(host, port):
    agent = _agent()
    server = AppServer(agent, host=host, port=port)
    click.echo(f"Serving unified KX app on http://{host}:{port}")
    server.serve()


@cli.command()
@click.option("--host", default="127.0.0.1")
@click.option("--port", type=int, default=8899)
def dashboard(host, port):
    server = DashboardServer(host=host, port=port)
    click.echo(f"Serving dashboard on http://{host}:{port}")
    server.serve()


@cli.command()
def status():
    agent = _agent()
    session_count = len(agent.memory.search_sessions("", limit=9999))
    click.echo(f"identity: {agent.config.identity}")
    click.echo(f"model: {agent.config.model.provider}/{agent.config.model.model}")
    click.echo(f"skills: {len(agent.skills.skills)}")
    click.echo(f"sessions: {session_count}")
    click.echo(f"workspace: {Path(agent.config.workspace.root).expanduser().resolve()}")
    click.echo(f"shell: {agent.config.shell.executable}")


@cli.command()
def mcp():
    agent = _agent()
    tools = {
        "kx_chat": {
            "description": "chat with KX Agent",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "message": {"type": "string"},
                    "session_id": {"type": "string"},
                    "channel": {"type": "string"},
                    "user": {"type": "string"},
                    "account": {"type": "string"},
                    "peer": {"type": "string"},
                },
                "required": ["message"],
            },
        },
        "kx_skills": {
            "description": "list registered skills",
            "inputSchema": {"type": "object", "properties": {}},
        },
        "kx_memory": {
            "description": "get session memory tree",
            "inputSchema": {
                "type": "object",
                "properties": {"session_id": {"type": "string"}},
                "required": ["session_id"],
            },
        },
        "kx_digest": {
            "description": "get session digest",
            "inputSchema": {
                "type": "object",
                "properties": {"session_id": {"type": "string"}},
                "required": ["session_id"],
            },
        },
        "kx_global_digest": {
            "description": "get global memory digest",
            "inputSchema": {
                "type": "object",
                "properties": {"limit": {"type": "integer"}},
            },
        },
        "kx_profile": {
            "description": "get saved user profile",
            "inputSchema": {"type": "object", "properties": {}},
        },
        "kx_transcripts": {
            "description": "search turn transcripts",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "limit": {"type": "integer"},
                },
                "required": ["query"],
            },
        },
        "kx_recall": {
            "description": "search cross-session memory",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "limit": {"type": "integer"},
                },
                "required": ["query"],
            },
        },
        "kx_route": {
            "description": "preview route resolution",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "channel": {"type": "string"},
                    "user": {"type": "string"},
                    "account": {"type": "string"},
                    "peer": {"type": "string"},
                },
                "required": ["channel"],
            },
        },
        "kx_tasks": {
            "description": "list task board items",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "session_id": {"type": "string"},
                    "status": {"type": "string"},
                },
            },
        },
        "kx_task_create": {
            "description": "create a task board item",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "session_id": {"type": "string"},
                    "title": {"type": "string"},
                    "details": {"type": "string"},
                    "priority": {"type": "string"},
                },
                "required": ["session_id", "title"],
            },
        },
        "kx_task_plan": {
            "description": "plan a goal into tasks and delegations",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "session_id": {"type": "string"},
                    "goal": {"type": "string"},
                },
                "required": ["session_id", "goal"],
            },
        },
        "kx_task_update": {
            "description": "update a task board item",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "task_id": {"type": "integer"},
                    "status": {"type": "string"},
                    "owner": {"type": "string"},
                    "details": {"type": "string"},
                    "title": {"type": "string"},
                    "priority": {"type": "string"},
                },
                "required": ["task_id"],
            },
        },
        "kx_task_delegate": {
            "description": "delegate a task into a worker subtask",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "session_id": {"type": "string"},
                    "task_id": {"type": "integer"},
                    "details": {"type": "string"},
                },
                "required": ["session_id", "task_id"],
            },
        },
        "kx_delegations": {
            "description": "list delegations",
            "inputSchema": {
                "type": "object",
                "properties": {"session_id": {"type": "string"}},
            },
        },
        "kx_delegation_run": {
            "description": "run a delegation worker",
            "inputSchema": {
                "type": "object",
                "properties": {"delegation_id": {"type": "integer"}},
                "required": ["delegation_id"],
            },
        },
        "kx_delegation_run_next": {
            "description": "run the next assigned delegation",
            "inputSchema": {
                "type": "object",
                "properties": {"session_id": {"type": "string"}},
            },
        },
        "kx_task_aggregate": {
            "description": "aggregate a task from worker output",
            "inputSchema": {
                "type": "object",
                "properties": {"task_id": {"type": "integer"}},
                "required": ["task_id"],
            },
        },
        "kx_task_aggregate_next": {
            "description": "aggregate the next eligible task",
            "inputSchema": {
                "type": "object",
                "properties": {"session_id": {"type": "string"}},
            },
        },
        "kx_task_inspect": {
            "description": "inspect the worker tool plan for a task",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "task_id": {"type": "integer"},
                    "session_id": {"type": "string"},
                },
                "required": ["task_id"],
            },
        },
        "kx_worker_write": {
            "description": "write an artifact for a worker-owned task",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "task_id": {"type": "integer"},
                    "content": {"type": "string"},
                },
                "required": ["task_id"],
            },
        },
        "kx_policy": {
            "description": "preview tool policy decision",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "tool_name": {"type": "string"},
                    "permission": {"type": "string"},
                    "allow": {"type": "array"},
                },
                "required": ["tool_name", "permission"],
            },
        },
        "kx_approvals": {
            "description": "list pending approvals",
            "inputSchema": {"type": "object", "properties": {}},
        },
        "kx_tools": {
            "description": "list registered tools",
            "inputSchema": {"type": "object", "properties": {}},
        },
        "kx_tool_run": {
            "description": "execute a KX tool or create an approval item",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "session_id": {"type": "string"},
                    "tool_name": {"type": "string"},
                    "arguments": {"type": "object"},
                },
                "required": ["session_id", "tool_name", "arguments"],
            },
        },
    }

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        req = json.loads(line)
        rid = req.get("id")
        method = req.get("method")
        if method == "initialize":
            resp = {
                "jsonrpc": "2.0",
                "id": rid,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "serverInfo": {"name": "kx-agent", "version": "0.2.0"},
                    "capabilities": {"tools": {}},
                },
            }
        elif method == "tools/list":
            resp = {
                "jsonrpc": "2.0",
                "id": rid,
                "result": {"tools": [{"name": k, **v} for k, v in tools.items()]},
            }
        elif method == "tools/call":
            params = req.get("params", {})
            name = params.get("name")
            args = params.get("arguments", {})
            if name == "kx_chat":
                reply = agent.chat(
                    args["message"],
                    session_id=args.get("session_id"),
                    channel=args.get("channel", "mcp"),
                    user=args.get("user", "mcp"),
                    account=args.get("account", "default"),
                    peer=args.get("peer", "*"),
                )
                text = json.dumps(reply.__dict__, ensure_ascii=False)
            elif name == "kx_skills":
                text = json.dumps(agent.skills.list(), ensure_ascii=False)
            elif name == "kx_memory":
                text = json.dumps(agent.memory.session_tree(args["session_id"]), ensure_ascii=False)
            elif name == "kx_digest":
                text = json.dumps(agent.session_digest(args["session_id"]), ensure_ascii=False)
            elif name == "kx_global_digest":
                text = json.dumps(agent.global_digest(limit=int(args.get("limit", 10))), ensure_ascii=False)
            elif name == "kx_profile":
                text = json.dumps(agent.user_profile(), ensure_ascii=False)
            elif name == "kx_transcripts":
                text = json.dumps(
                    agent.search_transcripts(args["query"], limit=int(args.get("limit", 20))),
                    ensure_ascii=False,
                )
            elif name == "kx_recall":
                text = json.dumps(
                    agent.recall_global(args["query"], limit=int(args.get("limit", 10))),
                    ensure_ascii=False,
                )
            elif name == "kx_route":
                text = json.dumps(
                    agent.explain_route(
                        channel=args["channel"],
                        user=args.get("user", "user"),
                        account=args.get("account", "default"),
                        peer=args.get("peer", "*"),
                    ),
                    ensure_ascii=False,
                )
            elif name == "kx_policy":
                text = json.dumps(
                    agent.explain_tool_policy(
                        args["tool_name"],
                        args["permission"],
                        list(args.get("allow", [])),
                    ),
                    ensure_ascii=False,
                )
            elif name == "kx_tasks":
                text = json.dumps(
                    agent.list_tasks(
                        session_id=args.get("session_id"),
                        status=args.get("status"),
                    ),
                    ensure_ascii=False,
                )
            elif name == "kx_task_create":
                text = json.dumps(
                    agent.create_task(
                        args["session_id"],
                        title=args["title"],
                        details=args.get("details", ""),
                        priority=args.get("priority", "medium"),
                    ),
                    ensure_ascii=False,
                )
            elif name == "kx_task_plan":
                text = json.dumps(
                    agent.plan_goal(
                        session_id=args["session_id"],
                        goal=args["goal"],
                    ),
                    ensure_ascii=False,
                )
            elif name == "kx_task_update":
                text = json.dumps(
                    agent.update_task(
                        int(args["task_id"]),
                        status=args.get("status"),
                        owner=args.get("owner"),
                        details=args.get("details"),
                        title=args.get("title"),
                        priority=args.get("priority"),
                    ),
                    ensure_ascii=False,
                )
            elif name == "kx_task_delegate":
                text = json.dumps(
                    agent.delegate_task(
                        session_id=args["session_id"],
                        parent_task_id=int(args["task_id"]),
                        details=args.get("details", ""),
                    ),
                    ensure_ascii=False,
                )
            elif name == "kx_delegations":
                text = json.dumps(
                    agent.list_delegations(session_id=args.get("session_id")),
                    ensure_ascii=False,
                )
            elif name == "kx_delegation_run":
                text = json.dumps(
                    agent.run_delegation(int(args["delegation_id"])),
                    ensure_ascii=False,
                )
            elif name == "kx_delegation_run_next":
                text = json.dumps(
                    agent.run_next_delegation(session_id=args.get("session_id")),
                    ensure_ascii=False,
                )
            elif name == "kx_task_aggregate":
                text = json.dumps(agent.aggregate_task(int(args["task_id"])), ensure_ascii=False)
            elif name == "kx_task_aggregate_next":
                text = json.dumps(
                    agent.aggregate_next_task(session_id=args.get("session_id")),
                    ensure_ascii=False,
                )
            elif name == "kx_task_inspect":
                text = json.dumps(
                    agent.inspect_worker_plan(
                        int(args["task_id"]),
                        session_id=args.get("session_id"),
                    ),
                    ensure_ascii=False,
                )
            elif name == "kx_worker_write":
                text = json.dumps(
                    agent.worker_write(int(args["task_id"]), args.get("content", "")),
                    ensure_ascii=False,
                )
            elif name == "kx_approvals":
                text = json.dumps(agent.memory.list_pending_approvals(), ensure_ascii=False)
            elif name == "kx_tools":
                text = json.dumps(agent.list_tools(), ensure_ascii=False)
            elif name == "kx_tool_run":
                result = agent.execute_tool(
                    args["session_id"],
                    args["tool_name"],
                    args["arguments"],
                )
                if hasattr(result, "tool_name"):
                    text = json.dumps(
                        {
                            "tool_name": result.tool_name,
                            "status": result.status,
                            "output": result.output,
                            "metadata": result.metadata,
                        },
                        ensure_ascii=False,
                    )
                else:
                    text = json.dumps(result, ensure_ascii=False)
            else:
                text = json.dumps({"error": f"unknown tool {name}"}, ensure_ascii=False)
            resp = {
                "jsonrpc": "2.0",
                "id": rid,
                "result": {"content": [{"type": "text", "text": text}]},
            }
        else:
            resp = {
                "jsonrpc": "2.0",
                "id": rid,
                "error": {"code": -32601, "message": f"Unknown method: {method}"},
            }
        sys.stdout.write(json.dumps(resp) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    cli()
