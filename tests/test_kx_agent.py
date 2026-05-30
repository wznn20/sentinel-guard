from __future__ import annotations

import hashlib
import hmac
from pathlib import Path
from unittest.mock import patch
from click.testing import CliRunner

import yaml

from kx_agent.agent import KXAgent
from kx_agent.channels import ChannelEvent, ChannelHub
from kx_agent.app_server import AppServer
from kx_agent.dashboard import DashboardServer
from kx_agent.delivery import DeliveryResult, DeliveryService
from kx_agent.config import KXConfig
from kx_agent.setup_wizard import run_setup_wizard
from kx_agent.cli import cli


def _write_config(path: Path, body: str) -> Path:
    path.write_text(body, encoding="utf-8")
    return path


def test_chat_creates_memory_and_offline_reply(tmp_path):
    config_path = _write_config(
        tmp_path / "config.yaml",
        f"""
identity: test-agent
workspace:
  root: "{tmp_path}"
  allow_roots:
    - "{tmp_path}"
memory:
  db_path: "{tmp_path / 'kx.sqlite'}"
skills:
  paths: []
approval:
  enabled: true
""",
    )
    agent = KXAgent(config_path)
    reply = agent.chat("remember that I prefer concise answers", session_id="s1")
    assert reply.session_id == "s1"
    assert reply.offline is True
    assert "offline mode" in reply.reply.lower()
    assert reply.route["agent_id"] == "main"
    tree = agent.memory.session_tree("s1")
    assert any(node["kind"] == "preference" for node in tree["nodes"])


def test_model_config_preserves_litellm_prefix_and_api_key_env(tmp_path):
    config_path = _write_config(
        tmp_path / "config.yaml",
        """
model:
  provider: openrouter
  litellm_prefix: openrouter
  model: anthropic/claude-sonnet-4
  api_key: ""
  api_key_env: OPENROUTER_API_KEY
  base_url: null
""",
    )
    cfg = KXConfig.load(config_path)
    assert cfg.model.provider == "openrouter"
    assert cfg.model.litellm_prefix == "openrouter"
    assert cfg.model.api_key_env == "OPENROUTER_API_KEY"


def test_write_request_creates_approval(tmp_path):
    config_path = _write_config(
        tmp_path / "config.yaml",
        f"""
workspace:
  root: "{tmp_path}"
  allow_roots:
    - "{tmp_path}"
memory:
  db_path: "{tmp_path / 'kx.sqlite'}"
skills:
  paths: []
approval:
  enabled: true
""",
    )
    agent = KXAgent(config_path)
    reply = agent.chat("create a file for me", session_id="s2")
    assert reply.model == "approval-gate"
    pending = agent.memory.list_pending_approvals()
    assert len(pending) == 1
    assert pending[0]["action"] == "write"


def test_read_tool_executes_without_approval(tmp_path):
    sample = tmp_path / "sample.txt"
    sample.write_text("hello from tool", encoding="utf-8")
    config_path = _write_config(
        tmp_path / "config.yaml",
        f"""
workspace:
  root: "{tmp_path}"
  allow_roots:
    - "{tmp_path}"
memory:
  db_path: "{tmp_path / 'kx.sqlite'}"
skills:
  paths: []
approval:
  enabled: true
""",
    )
    agent = KXAgent(config_path)
    agent.memory.ensure_session("s3", title="tool session")
    result = agent.execute_tool("s3", "read_file", {"path": str(sample)})
    assert result.status == "ok"
    assert "hello from tool" in result.output


def test_policy_blocks_write_for_read_only_channel(tmp_path):
    config_path = _write_config(
        tmp_path / "config.yaml",
        f"""
workspace:
  root: "{tmp_path}"
  allow_roots:
    - "{tmp_path}"
memory:
  db_path: "{tmp_path / 'kx.sqlite'}"
skills:
  paths: []
routing:
  channel_permissions:
    web: read
approval:
  enabled: true
""",
    )
    agent = KXAgent(config_path)
    reply = agent.chat("write hello.txt hi", session_id="web1", channel="web")
    assert reply.model == "policy"
    assert "blocked by policy" in reply.reply.lower()


def test_approval_execution_runs_tool_after_allow(tmp_path):
    output = tmp_path / "out.txt"
    config_path = _write_config(
        tmp_path / "config.yaml",
        f"""
workspace:
  root: "{tmp_path}"
  allow_roots:
    - "{tmp_path}"
memory:
  db_path: "{tmp_path / 'kx.sqlite'}"
skills:
  paths: []
approval:
  enabled: true
""",
    )
    agent = KXAgent(config_path)
    agent.memory.ensure_session("s4", title="tool session")
    pending = agent.execute_tool("s4", "write_file", {"path": str(output), "content": "abc"})
    assert "pending_approval" in pending
    resolved = agent.resolve_approval(pending["pending_approval"], True)
    assert resolved["status"] == "approved"
    assert output.read_text(encoding="utf-8") == "abc"


def test_session_tool_reuse_skips_second_approval(tmp_path):
    output = tmp_path / "out.txt"
    config_path = _write_config(
        tmp_path / "config.yaml",
        f"""
workspace:
  root: "{tmp_path}"
  allow_roots:
    - "{tmp_path}"
memory:
  db_path: "{tmp_path / 'kx.sqlite'}"
skills:
  paths: []
approval:
  enabled: true
  allow_session_tool_reuse: true
""",
    )
    agent = KXAgent(config_path)
    agent.memory.ensure_session("s5", title="tool session")
    pending = agent.execute_tool("s5", "write_file", {"path": str(output), "content": "abc"})
    agent.resolve_approval(pending["pending_approval"], True)
    result = agent.execute_tool("s5", "write_file", {"path": str(output), "content": "xyz"})
    assert result.status == "ok"
    assert output.read_text(encoding="utf-8") == "xyz"


def test_summary_is_created_after_threshold(tmp_path):
    config_path = _write_config(
        tmp_path / "config.yaml",
        f"""
workspace:
  root: "{tmp_path}"
  allow_roots:
    - "{tmp_path}"
memory:
  db_path: "{tmp_path / 'kx.sqlite'}"
  summary_trigger: 4
  summary_window: 2
skills:
  paths: []
approval:
  enabled: false
""",
    )
    agent = KXAgent(config_path)
    for i in range(6):
        agent.chat(f"message {i}", session_id="s6")
    session = agent.memory.get_session("s6")
    assert session is not None
    assert session["summary"] != ""


def test_read_many_tool_reads_multiple_files(tmp_path):
    (tmp_path / "a.txt").write_text("A", encoding="utf-8")
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "b.txt").write_text("B", encoding="utf-8")
    config_path = _write_config(
        tmp_path / "config.yaml",
        f"""
workspace:
  root: "{tmp_path}"
  allow_roots:
    - "{tmp_path}"
memory:
  db_path: "{tmp_path / 'kx.sqlite'}"
skills:
  paths: []
approval:
  enabled: false
""",
    )
    agent = KXAgent(config_path)
    agent.memory.ensure_session("s7", title="tool session")
    result = agent.execute_tool("s7", "read_many", {"path": str(tmp_path), "pattern": "*.txt"})
    assert result.status == "ok"
    assert '"content": "A"' in result.output
    assert '"content": "B"' in result.output


def test_delete_file_requires_approval(tmp_path):
    target = tmp_path / "dead.txt"
    target.write_text("x", encoding="utf-8")
    config_path = _write_config(
        tmp_path / "config.yaml",
        f"""
workspace:
  root: "{tmp_path}"
  allow_roots:
    - "{tmp_path}"
memory:
  db_path: "{tmp_path / 'kx.sqlite'}"
skills:
  paths: []
approval:
  enabled: true
""",
    )
    agent = KXAgent(config_path)
    agent.memory.ensure_session("s8", title="tool session")
    pending = agent.execute_tool("s8", "delete_file", {"path": str(target)})
    assert "pending_approval" in pending
    assert target.exists()


def test_cross_session_recall_returns_memory(tmp_path):
    config_path = _write_config(
        tmp_path / "config.yaml",
        f"""
workspace:
  root: "{tmp_path}"
  allow_roots:
    - "{tmp_path}"
memory:
  db_path: "{tmp_path / 'kx.sqlite'}"
skills:
  paths: []
approval:
  enabled: false
""",
    )
    agent = KXAgent(config_path)
    agent.chat("remember that the release codename is atlas", session_id="alpha")
    items = agent.recall_global("atlas", limit=10)
    assert any("atlas" in item["content"].lower() for item in items)


def test_session_digest_contains_counts(tmp_path):
    config_path = _write_config(
        tmp_path / "config.yaml",
        f"""
workspace:
  root: "{tmp_path}"
  allow_roots:
    - "{tmp_path}"
memory:
  db_path: "{tmp_path / 'kx.sqlite'}"
skills:
  paths: []
approval:
  enabled: false
""",
    )
    agent = KXAgent(config_path)
    agent.chat("remember my favorite editor is vim", session_id="digest1")
    digest = agent.session_digest("digest1")
    assert digest["turn_count"] >= 2
    assert digest["memory_count"] >= 1
    assert digest["agent_id"] == "main"


def test_route_and_policy_explainers(tmp_path):
    config_path = _write_config(
        tmp_path / "config.yaml",
        f"""
workspace:
  root: "{tmp_path}"
  allow_roots:
    - "{tmp_path}"
memory:
  db_path: "{tmp_path / 'kx.sqlite'}"
skills:
  paths: []
routing:
  default_agent: main
  channel_permissions:
    docs: read
  bindings:
    - agent_id: docs-agent
      channel: docs
      account: default
      peer: "*"
      permission: read
approval:
  enabled: true
""",
    )
    agent = KXAgent(config_path)
    route = agent.explain_route(channel="docs")
    assert route["agent_id"] == "docs-agent"
    policy = agent.explain_tool_policy("write_file", "read")
    assert policy["allowed"] is False


def test_user_profile_is_extracted(tmp_path):
    config_path = _write_config(
        tmp_path / "config.yaml",
        f"""
workspace:
  root: "{tmp_path}"
  allow_roots:
    - "{tmp_path}"
memory:
  db_path: "{tmp_path / 'kx.sqlite'}"
skills:
  paths: []
approval:
  enabled: false
""",
    )
    agent = KXAgent(config_path)
    agent.chat("remember that my favorite editor is neovim", session_id="prof1")
    profile = agent.user_profile()
    assert any(item["key"] == "favorite" for item in profile)


def test_search_transcripts_finds_turns(tmp_path):
    config_path = _write_config(
        tmp_path / "config.yaml",
        f"""
workspace:
  root: "{tmp_path}"
  allow_roots:
    - "{tmp_path}"
memory:
  db_path: "{tmp_path / 'kx.sqlite'}"
skills:
  paths: []
approval:
  enabled: false
""",
    )
    agent = KXAgent(config_path)
    agent.chat("the deploy region is us-east-1", session_id="tx1")
    rows = agent.search_transcripts("us-east-1", limit=10)
    assert any("us-east-1" in row["content"] for row in rows)


def test_global_digest_contains_profile_and_sessions(tmp_path):
    config_path = _write_config(
        tmp_path / "config.yaml",
        f"""
workspace:
  root: "{tmp_path}"
  allow_roots:
    - "{tmp_path}"
memory:
  db_path: "{tmp_path / 'kx.sqlite'}"
skills:
  paths: []
approval:
  enabled: false
""",
    )
    agent = KXAgent(config_path)
    agent.chat("remember that my timezone is UTC", session_id="gd1")
    digest = agent.global_digest(limit=10)
    assert len(digest["recent_sessions"]) >= 1
    assert any(item["key"] == "timezone" for item in digest["user_profile"])


def test_todo_message_creates_task(tmp_path):
    config_path = _write_config(
        tmp_path / "config.yaml",
        f"""
workspace:
  root: "{tmp_path}"
  allow_roots:
    - "{tmp_path}"
memory:
  db_path: "{tmp_path / 'kx.sqlite'}"
skills:
  paths: []
approval:
  enabled: false
""",
    )
    agent = KXAgent(config_path)
    agent.chat("todo: refactor the parser tomorrow", session_id="task1")
    tasks = agent.list_tasks(session_id="task1")
    assert any("refactor the parser" in task["title"] for task in tasks)


def test_create_and_update_task(tmp_path):
    config_path = _write_config(
        tmp_path / "config.yaml",
        f"""
workspace:
  root: "{tmp_path}"
  allow_roots:
    - "{tmp_path}"
memory:
  db_path: "{tmp_path / 'kx.sqlite'}"
skills:
  paths: []
approval:
  enabled: false
""",
    )
    agent = KXAgent(config_path)
    task = agent.create_task("task2", title="Ship release", details="prepare changelog")
    updated = agent.update_task(task["id"], status="in_progress", owner="worker")
    assert updated["status"] == "in_progress"
    assert updated["owner"] == "worker"


def test_delegate_task_creates_child_and_record(tmp_path):
    config_path = _write_config(
        tmp_path / "config.yaml",
        f"""
workspace:
  root: "{tmp_path}"
  allow_roots:
    - "{tmp_path}"
memory:
  db_path: "{tmp_path / 'kx.sqlite'}"
skills:
  paths: []
approval:
  enabled: false
""",
    )
    agent = KXAgent(config_path)
    parent = agent.create_task("task3", title="Build release plan", details="split into steps")
    delegation = agent.delegate_task("task3", parent_task_id=parent["id"], details="work on milestones")
    tasks = agent.list_tasks(session_id="task3")
    delegations = agent.list_delegations(session_id="task3")
    assert delegation["parent_task_id"] == parent["id"]
    assert any(task["parent_task_id"] == parent["id"] for task in tasks)
    assert any(item["parent_task_id"] == parent["id"] for item in delegations)


def test_run_delegation_completes_worker_flow(tmp_path):
    config_path = _write_config(
        tmp_path / "config.yaml",
        f"""
workspace:
  root: "{tmp_path}"
  allow_roots:
    - "{tmp_path}"
memory:
  db_path: "{tmp_path / 'kx.sqlite'}"
skills:
  paths: []
approval:
  enabled: false
""",
    )
    agent = KXAgent(config_path)
    parent = agent.create_task("task4", title="Investigate build issue", details="look at failure symptoms")
    delegation = agent.delegate_task("task4", parent_task_id=parent["id"], details="focus on likely causes")
    result = agent.run_delegation(delegation["delegation_id"])
    assert result["delegation_id"] == delegation["delegation_id"]
    rows = agent.list_delegations(session_id="task4")
    row = next(item for item in rows if item["id"] == delegation["delegation_id"])
    assert row["status"] == "completed"
    tasks = agent.list_tasks(session_id="task4")
    child = next(task for task in tasks if task["id"] == delegation["child_task_id"])
    assert child["status"] == "done"


def test_run_next_delegation_picks_assigned_work(tmp_path):
    config_path = _write_config(
        tmp_path / "config.yaml",
        f"""
workspace:
  root: "{tmp_path}"
  allow_roots:
    - "{tmp_path}"
memory:
  db_path: "{tmp_path / 'kx.sqlite'}"
skills:
  paths: []
approval:
  enabled: false
""",
    )
    agent = KXAgent(config_path)
    parent = agent.create_task("task5", title="Prepare QA checklist", details="derive test areas")
    delegation = agent.delegate_task("task5", parent_task_id=parent["id"], details="produce checklist draft")
    result = agent.run_next_delegation(session_id="task5")
    assert result["delegation_id"] == delegation["delegation_id"]


def test_plan_goal_creates_parent_children_and_delegations(tmp_path):
    config_path = _write_config(
        tmp_path / "config.yaml",
        f"""
workspace:
  root: "{tmp_path}"
  allow_roots:
    - "{tmp_path}"
memory:
  db_path: "{tmp_path / 'kx.sqlite'}"
skills:
  paths: []
approval:
  enabled: false
""",
    )
    agent = KXAgent(config_path)
    plan = agent.plan_goal("plan1", "Ship the next release safely")
    assert plan["parent_task"]["title"] == "Ship the next release safely"
    assert len(plan["child_tasks"]) >= 2
    assert len(plan["delegations"]) >= 1
    assert plan["planner"]["mode"] == "rules"
    tasks = agent.list_tasks(session_id="plan1")
    assert any(task["parent_task_id"] == plan["parent_task"]["id"] for task in tasks)


def test_worker_flow_auto_aggregates_parent_task(tmp_path):
    config_path = _write_config(
        tmp_path / "config.yaml",
        f"""
workspace:
  root: "{tmp_path}"
  allow_roots:
    - "{tmp_path}"
memory:
  db_path: "{tmp_path / 'kx.sqlite'}"
  summary_trigger: 100
skills:
  paths: []
approval:
  enabled: false
""",
    )
    agent = KXAgent(config_path)
    parent = agent.create_task("task6", title="Ship docs update", details="improve docs flow")
    delegation = agent.delegate_task("task6", parent_task_id=parent["id"], details="draft the docs update")
    result = agent.run_delegation(delegation["delegation_id"])
    assert result["aggregation"]["status"] == "aggregated"
    updated_parent = agent.update_task(parent["id"])
    assert updated_parent["status"] == "review"
    assert "Conclusion:" in updated_parent["details"]


def test_aggregate_next_finds_eligible_task(tmp_path):
    config_path = _write_config(
        tmp_path / "config.yaml",
        f"""
workspace:
  root: "{tmp_path}"
  allow_roots:
    - "{tmp_path}"
memory:
  db_path: "{tmp_path / 'kx.sqlite'}"
skills:
  paths: []
approval:
  enabled: false
""",
    )
    agent = KXAgent(config_path)
    parent = agent.create_task("task7", title="Fix flaky tests", details="stabilize test suite")
    delegation = agent.delegate_task("task7", parent_task_id=parent["id"], details="analyze flaky failures")
    agent.run_delegation(delegation["delegation_id"])
    result = agent.aggregate_next_task(session_id="task7")
    assert result["status"] in {"aggregated", "idle"}


def test_worker_plan_inspection_returns_tools(tmp_path):
    notes = tmp_path / "notes.txt"
    notes.write_text("hello", encoding="utf-8")
    config_path = _write_config(
        tmp_path / "config.yaml",
        f"""
workspace:
  root: "{tmp_path}"
  allow_roots:
    - "{tmp_path}"
memory:
  db_path: "{tmp_path / 'kx.sqlite'}"
skills:
  paths: []
approval:
  enabled: false
""",
    )
    agent = KXAgent(config_path)
    task = agent.create_task("task8", title="Investigate notes file", details=f"inspect `{notes}` for hello")
    plan = agent.inspect_worker_plan(task["id"])
    tool_names = [item["tool_name"] for item in plan["plan"]]
    assert "read_file" in tool_names or "search_code" in tool_names


def test_worker_plan_can_include_write_intent(tmp_path):
    config_path = _write_config(
        tmp_path / "config.yaml",
        f"""
workspace:
  root: "{tmp_path}"
  allow_roots:
    - "{tmp_path}"
memory:
  db_path: "{tmp_path / 'kx.sqlite'}"
skills:
  paths: []
approval:
  enabled: true
""",
    )
    agent = KXAgent(config_path)
    task = agent.create_task("task9", title="Draft release notes", details="create a markdown draft file")
    agent.delegate_task("task9", parent_task_id=task["id"], details="write a markdown draft file")
    plan = agent.inspect_worker_plan(task["id"])
    tool_names = [item["tool_name"] for item in plan["plan"]]
    assert "write_file" in tool_names


def test_worker_write_creates_artifact_or_approval(tmp_path):
    config_path = _write_config(
        tmp_path / "config.yaml",
        f"""
workspace:
  root: "{tmp_path}"
  allow_roots:
    - "{tmp_path}"
memory:
  db_path: "{tmp_path / 'kx.sqlite'}"
skills:
  paths: []
approval:
  enabled: true
""",
    )
    agent = KXAgent(config_path)
    task = agent.create_task("task10", title="Draft notes", details="write a markdown draft file", owner="worker")
    result = agent.worker_write(task["id"], "hello artifact")
    assert result["status"] in {"pending_approval", "ok"}


def test_channel_hub_stable_session_id():
    hub = ChannelHub(stable_sessions=True)
    event = ChannelEvent(channel="webhook", user="alice", text="hi", peer="room-1", thread_id="t1")
    sid1 = hub.session_id_for(event)
    sid2 = hub.session_id_for(event)
    assert sid1 == sid2


def test_channel_hub_lists_adapters():
    hub = ChannelHub(stable_sessions=True, adapters=["generic", "discord"])
    items = hub.list_adapters()
    assert any(item["name"] == "discord" for item in items)


def test_channel_hub_parses_platform_payloads():
    hub = ChannelHub(stable_sessions=True, adapters=["discord", "slack", "telegram"])
    discord = hub.event_from("discord", {"author": {"username": "alice"}, "content": "hi", "channel_id": "c1", "guild_id": "g1"})
    slack = hub.event_from("slack", {"event": {"user": "u1", "text": "ping", "channel": "c2", "thread_ts": "t2"}, "team_id": "team1"})
    telegram = hub.event_from("telegram", {"message": {"from": {"username": "bob"}, "text": "hello", "chat": {"id": 123}}})
    assert discord.channel == "discord" and discord.user == "alice"
    assert slack.channel == "slack" and slack.peer == "c2"
    assert telegram.channel == "telegram" and telegram.user == "bob"


def test_channel_hub_parses_extended_platform_payloads():
    hub = ChannelHub(
        stable_sessions=True,
        adapters=[
            "whatsapp",
            "signal",
            "mattermost",
            "matrix",
            "email",
            "sms",
            "dingtalk",
            "feishu",
            "wecom_callback",
            "bluebubbles",
            "qqbot",
            "yuanbao",
            "msgraph_webhook",
        ],
    )
    whatsapp = hub.event_from(
        "whatsapp",
        {
            "entry": [
                {
                    "changes": [
                        {
                            "value": {
                                "metadata": {"phone_number_id": "p1"},
                                "contacts": [{"profile": {"name": "Alice"}}],
                                "messages": [{"from": "15550001", "id": "wamid1", "text": {"body": "hello wa"}}],
                            }
                        }
                    ]
                }
            ]
        },
    )
    signal = hub.event_from(
        "signal",
        {
            "envelope": {
                "sourceName": "Bob",
                "sourceNumber": "+15550002",
                "timestamp": "12345",
                "dataMessage": {"message": "hello signal", "groupInfo": {"groupId": "g-signal"}},
            }
        },
    )
    mattermost = hub.event_from(
        "mattermost",
        {
            "user_name": "carol",
            "team_id": "team-mm",
            "channel_id": "chan-mm",
            "post": "{\"message\":\"hello mm\",\"id\":\"post1\",\"root_id\":\"root1\"}",
        },
    )
    matrix = hub.event_from(
        "matrix",
        {
            "sender": "@neo:matrix.org",
            "room_id": "!room:matrix.org",
            "event_id": "$event1",
            "content": {"body": "hello matrix", "m.relates_to": {"event_id": "$thread1"}},
        },
    )
    email = hub.event_from(
        "email",
        {"from": "alice@example.com", "to": "agent@example.com", "subject": "Need help", "body": "hello email", "message_id": "<m1>"},
    )
    sms = hub.event_from(
        "sms",
        {"From": "+15550003", "To": "+15559999", "Body": "hello sms", "MessageSid": "SM123"},
    )
    dingtalk = hub.event_from(
        "dingtalk",
        {
            "data": {
                "senderNick": "ding-user",
                "conversationId": "cid123",
                "chatbotCorpId": "corp1",
                "msgId": "msg1",
                "text": {"content": "hello ding"},
            }
        },
    )
    feishu = hub.event_from(
        "feishu",
        {
            "tenant_key": "tenant1",
            "event": {
                "sender": {"sender_id": {"open_id": "ou_1"}},
                "message": {"chat_id": "oc_1", "message_id": "om_1", "content": "{\"text\":\"hello feishu\"}"},
            },
        },
    )
    wecom_callback = hub.event_from(
        "wecom_callback",
        {"xml": {"FromUserName": "wx-user", "Content": "hello wecom", "AgentID": "1001", "MsgId": "wxmsg1"}},
    )
    bluebubbles = hub.event_from(
        "bluebubbles",
        {"handle": {"address": "imessage-user"}, "chatGuid": "chat-guid", "guid": "msg-guid", "text": "hello blue"},
    )
    qqbot = hub.event_from(
        "qqbot",
        {"d": {"author": {"username": "qq-user"}, "channel_id": "qq-chan", "guild_id": "qq-guild", "id": "qq-msg", "content": "hello qq"}},
    )
    yuanbao = hub.event_from(
        "yuanbao",
        {"message": {"sender": {"nickname": "yuan-user"}, "content": "hello yuan"}, "group_code": "group-1", "msg_id": "yb1"},
    )
    msgraph = hub.event_from(
        "msgraph_webhook",
        {"value": [{"id": "notif1", "subscriptionId": "sub1", "resource": "/me/messages", "changeType": "created"}]},
    )
    assert whatsapp.channel == "whatsapp" and whatsapp.user == "Alice"
    assert signal.channel == "signal" and signal.peer == "g-signal"
    assert mattermost.channel == "mattermost" and mattermost.thread_id == "root1"
    assert matrix.channel == "matrix" and matrix.peer == "!room:matrix.org"
    assert email.channel == "email" and "Need help" in email.text
    assert sms.channel == "sms" and sms.thread_id == "SM123"
    assert dingtalk.channel == "dingtalk" and dingtalk.user == "ding-user"
    assert feishu.channel == "feishu" and feishu.user == "ou_1"
    assert wecom_callback.channel == "wecom_callback" and wecom_callback.user == "wx-user"
    assert bluebubbles.channel == "bluebubbles" and bluebubbles.peer == "chat-guid"
    assert qqbot.channel == "qqbot" and qqbot.user == "qq-user"
    assert yuanbao.channel == "yuanbao" and yuanbao.user == "yuan-user"
    assert msgraph.channel == "msgraph_webhook" and "created" in msgraph.text


def test_channel_hub_verifies_signature():
    secret = "topsecret"
    hub = ChannelHub(stable_sessions=True, adapters=["generic"], adapter_secrets={"generic": secret})
    msg = "hello"
    sig = hmac.new(secret.encode("utf-8"), msg.encode("utf-8"), hashlib.sha256).hexdigest()
    event = hub.event_from("generic", {"message": msg, "signature": sig})
    assert event.verified is True


def test_channel_hub_protocol_responses():
    hub = ChannelHub(stable_sessions=True, adapters=["slack", "discord", "telegram"])
    slack = hub.protocol_response("slack", {"type": "url_verification", "challenge": "abc"})
    slack_event = hub.protocol_response("slack", {"type": "event_callback", "headers": {"x-slack-retry-num": "1"}})
    discord = hub.protocol_response("discord", {"type": 1})
    discord_interaction = hub.protocol_response("discord", {"type": 2})
    telegram = hub.protocol_response("telegram", {"callback_query": {"id": "cb1"}})
    telegram_message = hub.protocol_response("telegram", {"message": {"text": "hi"}})
    assert slack == {"challenge": "abc"}
    assert slack_event == {"ok": True, "retry_after": "1"}
    assert discord == {"type": 1}
    assert discord_interaction == {"type": 5}
    assert telegram["method"] == "answerCallbackQuery"
    assert telegram_message == {"ok": True}


def test_channel_hub_extended_protocol_responses():
    hub = ChannelHub(stable_sessions=True, adapters=["feishu", "msgraph_webhook", "wecom_callback", "whatsapp"])
    feishu = hub.protocol_response("feishu", {"type": "url_verification", "challenge": "ftok"})
    msgraph = hub.protocol_response("msgraph_webhook", {"validationToken": "graph-token"})
    wecom = hub.protocol_response("wecom_callback", {"echostr": "echo-token"})
    whatsapp = hub.protocol_response("whatsapp", {"hub.challenge": "wa-token"})
    assert feishu == {"challenge": "ftok"}
    assert msgraph == "graph-token"
    assert wecom == "echo-token"
    assert whatsapp == "wa-token"


def test_default_channel_config_includes_hermes_platforms():
    hub = ChannelHub(stable_sessions=True)
    items = {item["name"] for item in hub.list_adapters()}
    assert {"signal", "matrix", "email", "sms", "feishu", "wecom", "qqbot", "yuanbao"} <= items


def test_delivery_planner_builds_platform_native_reply_plans(tmp_path):
    config_path = _write_config(
        tmp_path / "config.yaml",
        f"""
workspace:
  root: "{tmp_path}"
  allow_roots:
    - "{tmp_path}"
memory:
  db_path: "{tmp_path / 'kx.sqlite'}"
skills:
  paths: []
approval:
  enabled: false
""",
    )
    service = DeliveryService(KXAgent(config_path).config)
    slack_event = ChannelEvent(channel="slack", user="u1", text="hi", peer="C123", adapter="slack", meta={"channel": "C123", "thread_ts": "t1"})
    telegram_event = ChannelEvent(channel="telegram", user="bob", text="hi", peer="123", adapter="telegram", meta={"chat_id": 123, "message_id": 88})
    email_event = ChannelEvent(channel="email", user="alice@example.com", text="help", peer="alice@example.com", adapter="email", meta={"from": "alice@example.com", "subject": "Question", "message_id": "<m1>"})
    qq_event = ChannelEvent(channel="qqbot", user="qq-user", text="hi", peer="c1", adapter="qqbot", meta={"channel_id": "c1", "msg_id": "m1"})
    slack_plan = service.build_reply_plan(slack_event, "hello slack")
    telegram_plan = service.build_reply_plan(telegram_event, "hello tg")
    email_plan = service.build_reply_plan(email_event, "hello email")
    qq_plan = service.build_reply_plan(qq_event, "hello qq")
    assert slack_plan.platform == "slack" and slack_plan.body["channel"] == "C123"
    assert telegram_plan.platform == "telegram" and telegram_plan.body["chat_id"] == 123
    assert email_plan.platform == "email" and email_plan.body["subject"].startswith("Re:")
    assert qq_plan.platform == "qqbot" and qq_plan.body["msg_id"] == "m1"


def test_shell_sandbox_rejects_non_allowlisted_command(tmp_path):
    config_path = _write_config(
        tmp_path / "config.yaml",
        f"""
workspace:
  root: "{tmp_path}"
  allow_roots:
    - "{tmp_path}"
sandbox:
  read_roots:
    - "{tmp_path}"
  write_roots:
    - "{tmp_path}"
  shell_enabled: true
  allowed_shell_prefixes:
    - "pwd"
memory:
  db_path: "{tmp_path / 'kx.sqlite'}"
skills:
  paths: []
approval:
  enabled: false
""",
    )
    agent = KXAgent(config_path)
    agent.memory.ensure_session("sandbox1", title="tool session")
    result = agent.execute_tool("sandbox1", "run_shell", {"command": "echo hello"})
    assert result.status == "error"
    assert "allowlisted" in result.output


def test_dashboard_overview_returns_kx_state(tmp_path):
    config_path = _write_config(
        tmp_path / "config.yaml",
        f"""
workspace:
  root: "{tmp_path}"
  allow_roots:
    - "{tmp_path}"
memory:
  db_path: "{tmp_path / 'kx.sqlite'}"
skills:
  paths: []
approval:
  enabled: false
""",
    )
    agent = KXAgent(config_path)
    agent.chat("remember dashboard smoke", session_id="dash1")
    dashboard = DashboardServer(agent, host="127.0.0.1", port=8899)
    overview = dashboard.overview()
    assert overview["identity"] == "kx-agent"
    assert overview["sessions"] >= 1
    assert "profiles" in overview["sandbox"]
    assert "approvals_detail" in overview


def test_dashboard_send_chat_updates_session(tmp_path):
    config_path = _write_config(
        tmp_path / "config.yaml",
        f"""
workspace:
  root: "{tmp_path}"
  allow_roots:
    - "{tmp_path}"
memory:
  db_path: "{tmp_path / 'kx.sqlite'}"
skills:
  paths: []
approval:
  enabled: false
""",
    )
    agent = KXAgent(config_path)
    dashboard = DashboardServer(agent, host="127.0.0.1", port=8899)
    reply = dashboard.send_chat("dash-chat-1", "hello dashboard")
    assert reply["session_id"] == "dash-chat-1"
    detail = dashboard.session_detail("dash-chat-1")
    assert any("hello dashboard" in turn["content"] for turn in detail["turns"])
    assert "tree" in detail and "tool_runs" in detail and "tasks" in detail


def test_app_server_overview_returns_live_state(tmp_path):
    config_path = _write_config(
        tmp_path / "config.yaml",
        f"""
workspace:
  root: "{tmp_path}"
  allow_roots:
    - "{tmp_path}"
memory:
  db_path: "{tmp_path / 'kx.sqlite'}"
skills:
  paths: []
approval:
  enabled: false
""",
    )
    agent = KXAgent(config_path)
    agent.chat("remember app server smoke", session_id="app1")
    app = AppServer(agent, host="127.0.0.1", port=8787)
    overview = app.overview()
    assert overview["identity"] == "kx-agent"
    assert overview["sessions"] >= 1
    assert "adapters" in overview
    assert "approvals_detail" in overview
    adapter_names = {item["name"] for item in overview["adapters"]}
    assert {"signal", "matrix", "email", "sms", "feishu", "qqbot", "yuanbao"} <= adapter_names


def test_app_server_send_chat_updates_session(tmp_path):
    config_path = _write_config(
        tmp_path / "config.yaml",
        f"""
workspace:
  root: "{tmp_path}"
  allow_roots:
    - "{tmp_path}"
memory:
  db_path: "{tmp_path / 'kx.sqlite'}"
skills:
  paths: []
approval:
  enabled: false
""",
    )
    agent = KXAgent(config_path)
    app = AppServer(agent, host="127.0.0.1", port=8787)
    reply = app.send_chat("chat-ui-1", "hello from dashboard", channel="dashboard")
    assert reply["session_id"] == "chat-ui-1"
    detail = app.session_detail("chat-ui-1")
    assert any("hello from dashboard" in turn["content"] for turn in detail["turns"])


def test_gateway_delivery_plan_can_be_derived_from_channel_event(tmp_path):
    config_path = _write_config(
        tmp_path / "config.yaml",
        f"""
workspace:
  root: "{tmp_path}"
  allow_roots:
    - "{tmp_path}"
memory:
  db_path: "{tmp_path / 'kx.sqlite'}"
skills:
  paths: []
approval:
  enabled: false
""",
    )
    agent = KXAgent(config_path)
    event = ChannelHub(stable_sessions=True, adapters=["telegram"]).event_from(
        "telegram",
        {"message": {"message_id": 99, "from": {"username": "bob"}, "text": "hello", "chat": {"id": 321}}},
    )
    reply = agent.chat(event.text, session_id="tg1", channel=event.channel, user=event.user, account=event.account, peer=event.peer)
    plan = agent.delivery.build_reply_plan(event, reply.reply)
    assert plan.platform == "telegram"
    assert plan.body["chat_id"] == 321
    assert plan.body["reply_to_message_id"] == 99


def test_delivery_service_execute_returns_missing_config_error(tmp_path):
    config_path = _write_config(
        tmp_path / "config.yaml",
        f"""
workspace:
  root: "{tmp_path}"
  allow_roots:
    - "{tmp_path}"
memory:
  db_path: "{tmp_path / 'kx.sqlite'}"
skills:
  paths: []
approval:
  enabled: false
delivery:
  enabled: true
""",
    )
    agent = KXAgent(config_path)
    event = ChannelEvent(channel="telegram", user="bob", text="hello", peer="321", adapter="telegram", meta={"chat_id": 321})
    plan, result = agent.delivery.send_reply(event, "hi back")
    assert plan.platform == "telegram"
    assert result.success is False
    assert "token" in result.error.lower()


def test_delivery_service_auto_send_false_returns_dry_run(tmp_path):
    config_path = _write_config(
        tmp_path / "config.yaml",
        f"""
workspace:
  root: "{tmp_path}"
  allow_roots:
    - "{tmp_path}"
memory:
  db_path: "{tmp_path / 'kx.sqlite'}"
skills:
  paths: []
approval:
  enabled: false
delivery:
  auto_send: false
""",
    )
    agent = KXAgent(config_path)
    event = ChannelHub(stable_sessions=True, adapters=["slack"]).event_from(
        "slack",
        {"event": {"user": "u1", "text": "ping", "channel": "c2", "thread_ts": "t2"}, "team_id": "team1"},
    )
    plan, result = agent.delivery.send_reply(event, "dry-run")
    assert plan.platform == "slack"
    assert result.dry_run is True
    assert result.success is True


def test_setup_wizard_writes_kx_model_and_delivery_config(tmp_path):
    config_path = tmp_path / "config.yaml"
    def fake_input(prompt: str) -> str:
        if "选择提供商" in prompt:
            return "1"
        if "选择模型" in prompt:
            return "1"
        if "Base URL" in prompt:
            return ""
        if "Temperature" in prompt:
            return "0.3"
        if "Max tokens" in prompt:
            return "4096"
        if "Workspace root" in prompt:
            return str(tmp_path)
        if "Allow roots" in prompt:
            return str(tmp_path)
        if "SQLite db path" in prompt:
            return str(tmp_path / "kx.sqlite")
        if "Gateway host" in prompt:
            return "127.0.0.1"
        if "Gateway port" in prompt:
            return "8787"
        if "Gateway title" in prompt:
            return "KX Agent Gateway"
        if "Delivery timeout" in prompt:
            return "20"
        if "Dashboard port" in prompt:
            return "8899"
        if "启用 adapters" in prompt:
            return ""
        return ""

    confirm_values = {
        "测试模型连通性？": True,
        "Webhook 回复时自动真实发送？": True,
        "启用 delivery 子系统？": True,
        "启用 Telegram Bot？": False,
        "配置 Slack？": False,
        "配置 Discord？": False,
        "配置 WhatsApp Cloud API？": False,
        "配置 Feishu / Lark？": False,
        "配置 Matrix？": False,
        "配置 Signal？": False,
        "配置 Email SMTP？": False,
        "配置 Twilio SMS？": False,
        "启用 approval gate？": True,
        "启用 dashboard？": True,
        "保存配置？": True,
    }

    def fake_confirm(prompt: str, default: bool = True) -> bool:
        return confirm_values.get(prompt, default)

    with patch("builtins.input", side_effect=fake_input), patch("getpass.getpass", return_value="sk-test"), patch("kx_agent.setup_wizard.confirm", side_effect=fake_confirm), patch("kx_agent.setup_wizard.test_connection", return_value=True):
        result = run_setup_wizard(config_path)

    assert result is not None
    saved = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert saved["model"]["provider"] == "openai"
    assert saved["model"]["litellm_prefix"] == "openai"
    assert saved["model"]["api_key_env"] == "OPENAI_API_KEY"
    assert saved["delivery"]["auto_send"] is True
    assert saved["workspace"]["root"] == str(tmp_path)


def test_cli_self_test_runs_tool_chain():
    runner = CliRunner()
    result = runner.invoke(cli, ["self-test"])
    assert result.exit_code == 0
    assert "read_file" in result.output
    assert "run_shell" in result.output
    assert '"tool_name": "delete_file"' in result.output
    assert '"status": "ok"' in result.output


def test_cli_upgrate_invokes_git_pull_and_pip_install():
    runner = CliRunner()

    class Proc:
        def __init__(self):
            self.returncode = 0
            self.stdout = "ok"
            self.stderr = ""

    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        return Proc()

    with patch("kx_agent.cli.subprocess.run", side_effect=fake_run):
        result = runner.invoke(cli, ["upgrate"])

    assert result.exit_code == 0
    assert any(cmd[:3] == ["git", "-C", "/root/hermes-security-agent"] for cmd in calls)
    assert any("pip" in " ".join(cmd) for cmd in calls)


def test_cli_dashboard_uses_agent_config_and_constructs_server():
    runner = CliRunner()
    created = {}

    class FakeServer:
        def __init__(self, agent, host="127.0.0.1", port=8899):
            created["agent"] = agent
            created["host"] = host
            created["port"] = port
            self.host = host
            self.port = port

        def serve(self):
            created["served"] = True

    with patch("kx_agent.cli.DashboardServer", FakeServer):
        result = runner.invoke(cli, ["dashboard"])

    assert result.exit_code == 0
    assert created["host"] == created["agent"].config.dashboard.host
    assert created["port"] == created["agent"].config.dashboard.port
    assert created["served"] is True


def test_agent_log_delivery_records_tool_run(tmp_path):
    config_path = _write_config(
        tmp_path / "config.yaml",
        f"""
workspace:
  root: "{tmp_path}"
  allow_roots:
    - "{tmp_path}"
memory:
  db_path: "{tmp_path / 'kx.sqlite'}"
skills:
  paths: []
approval:
  enabled: false
""",
    )
    agent = KXAgent(config_path)
    agent.memory.ensure_session("deliver1", title="delivery session")
    result = {
        "success": False,
        "platform": "telegram",
        "mode": "bot_api",
        "target": "321",
        "error": "telegram bot token missing",
        "request_body": {"chat_id": 321, "text": "hi"},
    }
    agent.log_delivery("deliver1", "telegram", {"chat_id": 321, "text": "hi"}, result)
    runs = agent.memory.list_tool_runs("deliver1")
    assert runs[0]["tool_name"] == "deliver:telegram"
    assert runs[0]["status"] == "error"


def test_delivery_service_http_sender_can_be_mocked(tmp_path):
    config_path = _write_config(
        tmp_path / "config.yaml",
        f"""
workspace:
  root: "{tmp_path}"
  allow_roots:
    - "{tmp_path}"
memory:
  db_path: "{tmp_path / 'kx.sqlite'}"
skills:
  paths: []
approval:
  enabled: false
delivery:
  enabled: true
  platform_tokens:
    telegram: "bot123"
""",
    )
    agent = KXAgent(config_path)
    event = ChannelEvent(channel="telegram", user="bob", text="hello", peer="321", adapter="telegram", meta={"chat_id": 321})
    fake = DeliveryResult(success=True, platform="telegram", mode="bot_api", target="321", url="https://api.telegram.org/botbot123/sendMessage", status_code=200, response_text='{"ok":true}', response_json={"ok": True}, request_body={"chat_id": 321, "text": "hi"})
    with patch.object(agent.delivery, "_send_telegram", return_value=fake):
        plan, result = agent.delivery.send_reply(event, "hi")
    assert plan.platform == "telegram"
    assert result.success is True
    assert result.status_code == 200


def test_gateway_event_response_includes_delivery_result_when_auto_send_disabled(tmp_path):
    config_path = _write_config(
        tmp_path / "config.yaml",
        f"""
workspace:
  root: "{tmp_path}"
  allow_roots:
    - "{tmp_path}"
memory:
  db_path: "{tmp_path / 'kx.sqlite'}"
skills:
  paths: []
approval:
  enabled: false
delivery:
  auto_send: false
""",
    )
    agent = KXAgent(config_path)
    app = AppServer(agent, host="127.0.0.1", port=8787)
    reply = app.send_chat("gx1", "hello", channel="telegram", user="bob", peer="321")
    assert reply["delivery_result"] is None  # chat() stays core-only
    event = ChannelHub(stable_sessions=True, adapters=["telegram"]).event_from(
        "telegram",
        {"message": {"message_id": 99, "from": {"username": "bob"}, "text": "hello", "chat": {"id": 321}}},
    )
    plan, result = agent.delivery.send_reply(event, "hi back")
    assert result.dry_run is True
