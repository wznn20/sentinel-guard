"""
Sentinel CLI — 命令行入口
"""
import click
from pathlib import Path


@click.group()
@click.version_option(version="0.1.0", prog_name="sentinel")
def cli():
    """Sentinel — AI网络安全智能体

    纯防御型，7×24小时自主值守你的数字资产。
    """
    pass


@cli.command()
@click.option("--config", "-c", help="配置文件路径")
def start(config):
    """启动 Sentinel"""
    click.echo("🚀 Starting Sentinel...")
    # TODO: 启动引擎
    click.echo("✅ Sentinel is running")


@cli.command()
def stop():
    """停止 Sentinel"""
    click.echo("🛑 Stopping Sentinel...")


@cli.command()
def status():
    """查看运行状态"""
    click.echo("📊 Sentinel Status")
    click.echo("  Status: Not running")
    click.echo("  Version: 0.1.0")


@cli.command()
def setup():
    """运行初始化向导"""
    click.echo("""
╔══════════════════════════════════════╗
║     Sentinel 初始化向导              ║
╚══════════════════════════════════════╝
    """)
    # TODO: 交互式配置向导


@cli.command()
@click.argument("action", type=click.Choice(["list", "show", "resolve"]))
@click.argument("alert_id", required=False)
def alert(action, alert_id):
    """管理安全告警"""
    if action == "list":
        click.echo("📋 告警列表")
        # TODO
    elif action == "show" and alert_id:
        click.echo(f"🔍 告警详情: {alert_id}")
    elif action == "resolve" and alert_id:
        click.echo(f"✅ 已标记处理: {alert_id}")


@cli.command()
@click.argument("action", type=click.Choice(["list", "show", "export"]))
@click.argument("evidence_id", required=False)
def evidence(action, evidence_id):
    """管理证据包"""
    click.echo("📸 证据管理")
    # TODO


@cli.command()
def dashboard():
    """启动Web控制面板"""
    click.echo("🌐 Starting Dashboard on https://localhost:8443")
    # TODO


@cli.command()
def mcp():
    """启动MCP Server"""
    click.echo("🔌 Starting MCP Server on port 9090")
    # TODO


if __name__ == "__main__":
    cli()
