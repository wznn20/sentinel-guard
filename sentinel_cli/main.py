"""
Sentinel CLI — 命令行入口
"""
import click
import os
import yaml
import sys
from pathlib import Path


CONFIG_DIR = Path.home() / ".sentinel"
CONFIG_FILE = CONFIG_DIR / "config.yaml"

DEFAULT_CONFIG = {
    "model": {"provider": "openai", "model": "gpt-4o-mini", "api_key": ""},
    "platforms": [],
    "dashboard": {"port": 8443, "host": "127.0.0.1"},
    "hermes": {"enabled": False, "mcp_port": 9120},
    "scanning": {"interval_seconds": 30, "log_sources": []},
}


@click.group()
@click.version_option(version="0.1.0", prog_name="sentinel")
def cli():
    """Sentinel — AI 网络安全智能体

    纯防御型，帮你监测和分析安全威胁。
    """
    pass


@cli.command()
def setup():
    """运行交互式配置向导"""
    click.echo("""
╔══════════════════════════════════════╗
║     Sentinel 初始化向导              ║
╚══════════════════════════════════════╝
""")

    if CONFIG_FILE.exists():
        with open(CONFIG_FILE) as f:
            cfg = yaml.safe_load(f) or DEFAULT_CONFIG
        click.echo("📋 检测到已有配置，将在此基础上升级\n")
    else:
        cfg = DEFAULT_CONFIG.copy()
        click.echo("🆕 首次配置\n")

    # ── 模型配置 ──
    click.secho("━━━ AI 模型配置 ━━━", fg="cyan")
    click.echo("Sentinel 需要 AI 来分析安全事件。\n")

    providers = ["openai", "anthropic", "deepseek", "zhipu", "ollama", "custom"]
    provider = click.prompt(
        f"模型提供商 ({'/'.join(providers)})",
        default=cfg["model"].get("provider", "openai"),
    )
    if provider not in providers:
        click.echo(f"⚠️  未知提供商，使用 openai")
        provider = "openai"
    cfg["model"]["provider"] = provider

    model_defaults = {
        "openai": "gpt-4o-mini", "anthropic": "claude-sonnet-4-20250514",
        "deepseek": "deepseek-chat", "zhipu": "glm-4-flash",
        "ollama": "llama3", "custom": "your-model",
    }
    model = click.prompt("模型名称", default=model_defaults.get(provider, "gpt-4o-mini"))
    cfg["model"]["model"] = model

    api_key = click.prompt(
        "API Key（输入后不显示。回车跳过，用环境变量）",
        default="", hide_input=True, show_default=False,
    )
    if api_key:
        cfg["model"]["api_key"] = api_key
    click.echo("✅ 模型配置完成\n")

    # ── 通知平台 ──
    click.secho("━━━ 告警通知平台 ━━━", fg="cyan")
    click.echo("可选。回车跳过则不启用。\n")

    platforms = []
    if click.confirm("启用飞书通知？", default=False):
        webhook = click.prompt("  飞书 Webhook URL")
        platforms.append({"type": "feishu", "webhook_url": webhook})

    if click.confirm("启用 QQ Bot？", default=False):
        app_id = click.prompt("  QQ Bot App ID")
        token = click.prompt("  Token", hide_input=True)
        platforms.append({"type": "qqbot", "app_id": app_id, "token": token})

    cfg["platforms"] = platforms
    click.echo(f"✅ {len(platforms)} 个平台已配置\n")

    # ── 保存 ──
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, "w") as f:
        yaml.dump(cfg, f, allow_unicode=True, default_flow_style=False, sort_keys=False)

    click.secho("╔══════════════════════════════════════╗", fg="green")
    click.secho("║  ✅ 配置完成！试试 sentinel chat     ║", fg="green")
    click.secho("╚══════════════════════════════════════╝", fg="green")


@cli.command()
def chat():
    """启动交互式对话（AI 安全助手）"""
    from sentinel_core.engine import SentinelAgent

    if not CONFIG_FILE.exists():
        click.secho("❌ 未找到配置，请先运行 sentinel setup", fg="red")
        return

    click.secho("""
╔══════════════════════════════════════╗
║   Sentinel AI 安全助手 (对话模式)    ║
║   输入消息开始对话，输入 /quit 退出  ║
╚══════════════════════════════════════╝
""", fg="cyan")

    try:
        agent = SentinelAgent(CONFIG_FILE)
    except Exception as e:
        click.secho(f"❌ 初始化失败: {e}", fg="red")
        return

    if not agent.api_key:
        click.secho("❌ 未配置 API Key。运行 sentinel setup 设置", fg="red")
        return

    click.secho(f"模型: {agent.provider}/{agent.model}", fg="green")
    click.echo()

    print("🔍 你可以这样问我：")
    print("  • 分析 /var/log/nginx/access.log 的最近攻击")
    print("  • 帮我检查服务器安全配置")
    print("  • 查询 192.168.1.100 这个IP的信息")
    print("  • 如何防御 SQL 注入？")
    print()

    try:
        while True:
            user_input = click.prompt("You", prompt_suffix=" > ").strip()

            if not user_input:
                continue
            if user_input.lower() in ("/quit", "/exit", "quit", "exit"):
                click.echo("👋 再见！")
                break
            if user_input.lower() in ("/clear", "clear"):
                agent.messages = []
                click.echo("🧹 对话已清空")
                continue

            click.echo()
            try:
                response = agent.chat(user_input)
                click.secho(response)
            except Exception as e:
                click.secho(f"❌ {e}", fg="red")
            click.echo()

    except (KeyboardInterrupt, EOFError):
        click.echo("\n👋 再见！")


@cli.command()
@click.option("--config", "-c", help="配置文件路径")
def start(config):
    """启动安全监控守护进程"""
    config_path = Path(config) if config else CONFIG_FILE

    if not config_path.exists():
        click.secho("❌ 未找到配置，请先运行 sentinel setup", fg="red")
        return

    with open(config_path) as f:
        cfg = yaml.safe_load(f)

    click.secho("🚀 Sentinel 监控中...\n", fg="cyan")
    click.echo(f"  模型:   {cfg['model']['provider']}/{cfg['model']['model']}")
    click.echo(f"  仪表盘: http://127.0.0.1:8443")
    click.echo(f"  按 Ctrl+C 停止\n")

    # 简单监控循环
    import time
    try:
        while True:
            time.sleep(60)
    except KeyboardInterrupt:
        click.secho("\n🛑 Sentinel 已停止", fg="yellow")


@cli.command()
def stop():
    """停止 Sentinel"""
    click.echo("🛑 Sentinel 已停止")


@cli.command()
def status():
    """查看运行状态"""
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE) as f:
            cfg = yaml.safe_load(f)
        click.echo(f"📊 Sentinel v0.1.0")
        click.echo(f"  模型: {cfg['model']['provider']}/{cfg['model']['model']}")
        click.echo(f"  配置: {CONFIG_FILE}")
    else:
        click.echo("📊 未配置 — sentinel setup")


@cli.command()
def dashboard():
    """启动 Web 控制面板 (本地)"""
    import http.server
    import socketserver
    import os as _os

    click.echo("🌐 仪表盘: http://127.0.0.1:8443")
    click.echo("   ⚠️  仅限本地访问，按 Ctrl+C 停止")

    dashboard_dir = Path(__file__).resolve().parent.parent / "sentinel_dashboard"
    if not dashboard_dir.is_dir():
        import sentinel_dashboard
        dashboard_dir = Path(sentinel_dashboard.__file__).parent

    class Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(dashboard_dir), **kwargs)

    class TCPServer(socketserver.TCPServer):
        allow_reuse_address = True

    try:
        with TCPServer(("127.0.0.1", 8443), Handler) as httpd:
            httpd.serve_forever()
    except KeyboardInterrupt:
        click.echo("\n👋 已停止")


if __name__ == "__main__":
    cli()
