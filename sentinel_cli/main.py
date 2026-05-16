"""
Sentinel CLI — 完整命令行入口（v0.2.0 简化版）
"""
import click
import os
import sys
import json
import yaml
import signal
import time
import sqlite3
from datetime import datetime
from pathlib import Path


CONFIG_DIR = Path.home() / ".sentinel"
CONFIG_FILE = CONFIG_DIR / "config.yaml"
PID_FILE = CONFIG_DIR / "sentinel.pid"
DB_FILE = CONFIG_DIR / "alerts.db"

DEFAULT_CONFIG = {
    "model": {"provider": "openai", "model": "gpt-4o-mini", "api_key": ""},
    "platforms": [],
    "dashboard": {"port": 8443, "host": "127.0.0.1"},
    "hermes": {"enabled": False, "mcp_port": 9120},
    "scanning": {"interval_seconds": 30, "log_sources": []},
}


# ── 数据库 ──

def get_db():
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_FILE))
    conn.execute("""CREATE TABLE IF NOT EXISTS alerts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT NOT NULL, type TEXT NOT NULL,
        severity TEXT NOT NULL, source TEXT, evidence TEXT,
        resolved INTEGER DEFAULT 0
    )""")
    conn.commit()
    return conn


def insert_alert(db, sig_name, severity, source, evidence):
    c = db.cursor()
    c.execute(
        "INSERT INTO alerts (timestamp, type, severity, source, evidence) VALUES (?,?,?,?,?)",
        (datetime.now().isoformat(), sig_name, severity, source, str(evidence)[:500]),
    )
    db.commit()


# ── 文件监控 ──

def scan_file_for_attacks(filepath: str) -> int:
    """扫描单个日志文件，返回发现的攻击数"""
    from sentinel_security.traffic.signatures.web_attacks import ATTACK_SIGNATURES

    p = Path(filepath)
    if not p.exists():
        return 0

    try:
        content = p.read_text(errors="ignore")
    except Exception:
        return 0

    db = get_db()
    count = 0
    for sig in ATTACK_SIGNATURES:
        matches = sig["pattern"].findall(content)
        for m in matches[:10]:
            insert_alert(db, sig["name"], sig["severity"], filepath, m)
            count += 1
    db.close()
    return count


def start_monitor(log_sources: list):
    """启动文件监控（轮询模式，零依赖，兼容所有环境）"""
    from sentinel_security.traffic.signatures.web_attacks import ATTACK_SIGNATURES

    # 初始全量扫描
    total = 0
    for src in log_sources:
        n = scan_file_for_attacks(src)
        total += n
    if total > 0:
        print(f"📊 初始扫描发现 {total} 条攻击特征")

    # 记录每个文件的当前大小
    last_sizes = {}
    for src in log_sources:
        p = Path(src)
        last_sizes[src] = p.stat().st_size if p.exists() else 0

    db = get_db()
    print(f"👁️  监控 {len(log_sources)} 个日志文件 (轮询, 5s)")

    try:
        while True:
            for src in log_sources:
                p = Path(src)
                if not p.exists():
                    continue
                cur_size = p.stat().st_size
                if cur_size <= last_sizes.get(src, 0):
                    continue
                try:
                    with open(p, errors="ignore") as f:
                        f.seek(last_sizes.get(src, 0))
                        new = f.read()
                except Exception:
                    continue
                last_sizes[src] = cur_size
                if not new:
                    continue
                for sig in ATTACK_SIGNATURES:
                    for m in sig["pattern"].findall(new):
                        db.execute(
                            "INSERT INTO alerts (timestamp, type, severity, source, evidence) VALUES (?,?,?,?,?)",
                            (datetime.now().isoformat(), sig["name"], sig["severity"], src, str(m)[:500]),
                        )
                        db.commit()
            time.sleep(5)
    except KeyboardInterrupt:
        pass
    finally:
        db.close()


# ── CLI ──

@click.group()
@click.version_option(version="0.3.0", prog_name="sentinel")
def cli():
    """Sentinel — AI 网络安全智能体"""
    pass


@cli.command()
def setup():
    """运行交互式配置向导（支持 litellm 100+ AI 模型）"""
    from sentinel_cli.setup_wizard import run_setup_wizard
    run_setup_wizard(CONFIG_FILE)

    click.secho("╔══════════════════════════════════════╗", fg="green")
    click.secho("║  ✅ 配置完成！ sentinel start 开始  ║", fg="green")
    click.secho("╚══════════════════════════════════════╝", fg="green")


@cli.command()
def chat():
    """启动 AI 对话模式"""
    from sentinel_core.engine import SentinelAgent

    if not CONFIG_FILE.exists():
        click.secho("❌ 先运行 sentinel setup", fg="red")
        return

    click.secho("""
╔══════════════════════════════════════╗
║   Sentinel AI 安全助手               ║
╚══════════════════════════════════════╝
""", fg="cyan")

    agent = SentinelAgent(CONFIG_FILE)
    if not agent.api_key:
        click.secho("❌ 未配置 API Key", fg="red")
        return

    click.secho(f"模型: {agent.provider}/{agent.model}", fg="green")
    click.echo("试试: 分析日志、检查安全配置、查询IP\n")

    try:
        while True:
            user_input = click.prompt("You", prompt_suffix=" > ").strip()
            if not user_input:
                continue
            if user_input.lower() in ("/quit", "/exit", "quit", "exit"):
                break
            if user_input.lower() in ("/clear", "clear"):
                agent.messages = []
                click.echo("🧹 已清空")
                continue
            click.echo()
            try:
                click.secho(agent.chat(user_input))
            except Exception as e:
                click.secho(f"❌ {e}", fg="red")
            click.echo()
    except (KeyboardInterrupt, EOFError):
        pass
    click.echo("👋 再见！")


@cli.command()
def start():
    """启动安全监控（前台）"""
    if not CONFIG_FILE.exists():
        click.secho("❌ 先运行 sentinel setup", fg="red")
        return

    with open(CONFIG_FILE) as f:
        cfg = yaml.safe_load(f)

    log_sources = cfg.get("scanning", {}).get("log_sources", [])
    click.secho("🚀 Sentinel v0.3.0 启动\n", fg="cyan")
    click.echo(f"  模型:   {cfg['model']['provider']}/{cfg['model']['model']}")
    click.echo(f"  日志源: {len(log_sources)} 个")
    click.echo(f"  仪表盘: http://127.0.0.1:8443")
    click.echo(f"  Ctrl+C 停止\n")

    if not log_sources:
        click.secho("⚠️  未配置日志源，仅AI对话可用。sentinel chat 开始对话\n", fg="yellow")
        try:
            while True:
                time.sleep(60)
        except KeyboardInterrupt:
            click.echo("\n🛑 已停止")
        return

    try:
        start_monitor(log_sources)
    except ImportError as e:
        click.secho(f"❌ 缺少依赖: {e}。请运行 pip install sentinel-guard 安装完整依赖", fg="red")
    except KeyboardInterrupt:
        click.echo("\n🛑 Sentinel 已停止")


@cli.command()
def stop():
    """停止"""
    click.echo("🛑 Sentinel 已停止")


@cli.command()
def status():
    """状态"""
    click.echo("📊 Sentinel v0.3.0\n")
    if CONFIG_FILE.exists():
        cfg = yaml.safe_load(open(CONFIG_FILE))
        click.echo(f"  模型: {cfg['model']['provider']}/{cfg['model']['model']}")
        logs = cfg.get("scanning", {}).get("log_sources", [])
        click.echo(f"  日志源: {len(logs)} 个")
    try:
        db = get_db()
        total = db.execute("SELECT COUNT(*) FROM alerts").fetchone()[0]
        unresolved = db.execute("SELECT COUNT(*) FROM alerts WHERE resolved=0").fetchone()[0]
        click.echo(f"  告警: {total} 条 ({unresolved} 未处理)")
        db.close()
    except Exception:
        pass


@cli.command()
@click.argument("action", type=click.Choice(["list", "show", "resolve", "clear"]))
@click.argument("alert_id", required=False)
def alert(action, alert_id):
    """告警管理"""
    if not DB_FILE.exists():
        click.echo("📋 暂无告警")
        return

    db = get_db()
    if action == "list":
        rows = db.execute(
            "SELECT id, timestamp, type, severity, resolved FROM alerts ORDER BY id DESC LIMIT 50"
        ).fetchall()
        if not rows:
            click.echo("📋 暂无告警")
        else:
            click.echo(f"{'ID':<6} {'时间':<20} {'类型':<28} {'级别':<10} 状态")
            click.echo("-" * 80)
            for r in rows:
                sev_color = {"critical": "red", "high": "red", "medium": "yellow", "low": "green"}
                click.echo(f"{r[0]:<6} {r[1][:19]:<20} {r[2][:28]:<28} "
                           f"{click.style(r[3], fg=sev_color.get(r[3], 'white')):<16} "
                           f"{'✅' if r[4] else '🔴'}")
    elif action == "show":
        if not alert_id:
            click.secho("❌ 需要告警ID", fg="red")
            return
        r = db.execute("SELECT * FROM alerts WHERE id=?", (int(alert_id),)).fetchone()
        if not r:
            click.echo(f"❌ 告警 #{alert_id} 不存在")
        else:
            cols = ["id", "timestamp", "type", "severity", "source", "evidence", "resolved"]
            for i, c in enumerate(cols):
                click.echo(f"  {c}: {r[i]}")
    elif action == "resolve":
        if not alert_id:
            click.secho("❌ 需要告警ID", fg="red")
            return
        db.execute("UPDATE alerts SET resolved=1 WHERE id=?", (int(alert_id),))
        db.commit()
        click.echo(f"✅ 告警 #{alert_id} 已处理")
    elif action == "clear":
        if click.confirm("⚠️  清空所有告警？"):
            db.execute("DELETE FROM alerts")
            db.commit()
            click.echo("✅ 已清空")
    db.close()


@cli.command()
def dashboard():
    """Web 仪表盘"""
    import http.server, socketserver

    click.echo("🌐 http://127.0.0.1:8443 (仅本地)\n")

    d = Path(__file__).resolve().parent.parent / "sentinel_dashboard"
    if not d.is_dir():
        import sentinel_dashboard
        d = Path(sentinel_dashboard.__file__).parent

    class H(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *a, **kw):
            super().__init__(*a, directory=str(d), **kw)
        def log_message(self, *a):
            pass

    class S(socketserver.TCPServer):
        allow_reuse_address = True

    try:
        with S(("127.0.0.1", 8443), H) as httpd:
            httpd.serve_forever()
    except KeyboardInterrupt:
        click.echo("\n👋 已停止")


@cli.command()
@click.option("--port", "-p", default=9120)
def mcp(port):
    """MCP Server (Hermes 集成)"""
    click.echo(f"🔌 MCP Server (stdio, Hermes: hermes mcp add sentinel --command \"sentinel mcp\")")

    tools = {
        "sentinel_scan_logs": {"description": "分析Web日志检测攻击", "inputSchema": {
            "type": "object", "properties": {
                "path": {"type": "string"}, "lines": {"type": "integer", "default": 500}
            }, "required": ["path"]
        }},
        "sentinel_alerts": {"description": "查询告警", "inputSchema": {
            "type": "object", "properties": {
                "limit": {"type": "integer", "default": 20}
            }
        }},
        "sentinel_status": {"description": "运行状态", "inputSchema": {"type": "object", "properties": {}}},
    }

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
            rid = req.get("id")
            m = req.get("method")

            if m == "initialize":
                resp = {"jsonrpc": "2.0", "id": rid, "result": {
                    "protocolVersion": "2024-11-05",
                    "serverInfo": {"name": "sentinel", "version": "0.2.0"},
                    "capabilities": {"tools": {}}
                }}
            elif m == "tools/list":
                resp = {"jsonrpc": "2.0", "id": rid, "result": {
                    "tools": [{"name": k, **v} for k, v in tools.items()]
                }}
            elif m == "tools/call":
                p = req.get("params", {})
                name = p.get("name", "")
                args = p.get("arguments", {})

                if name == "sentinel_status":
                    text = json.dumps({"config": str(CONFIG_FILE), "alerts_db": str(DB_FILE)})
                elif name == "sentinel_alerts":
                    db = get_db()
                    rows = db.execute("SELECT id, timestamp, type, severity FROM alerts WHERE resolved=0 ORDER BY id DESC LIMIT ?",
                                      (args.get("limit", 20),)).fetchall()
                    db.close()
                    text = json.dumps([{"id": r[0], "time": r[1], "type": r[2], "severity": r[3]} for r in rows])
                elif name == "sentinel_scan_logs":
                    n = scan_file_for_attacks(args["path"])
                    text = json.dumps({"scanned": args["path"], "attacks_found": n})
                else:
                    text = f"Unknown: {name}"

                resp = {"jsonrpc": "2.0", "id": rid, "result": {"content": [{"type": "text", "text": text}]}}
            else:
                resp = {"jsonrpc": "2.0", "id": rid, "error": {"code": -32601, "message": f"Unknown: {m}"}}

            sys.stdout.write(json.dumps(resp) + "\n")
            sys.stdout.flush()
        except Exception as e:
            sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": req.get("id", None) if 'req' in dir() else None,
                                         "error": {"code": -32603, "message": str(e)}}) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    cli()
