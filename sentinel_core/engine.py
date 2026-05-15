"""
Sentinel Core Engine — AI网络安全智能体核心
"""
import asyncio
import logging
from pathlib import Path
from typing import Optional

from .llm_router import LLMRouter
from .config import Config
from .context import ContextManager
from .memory import MemoryStore

logger = logging.getLogger("sentinel.core")


class SentinelEngine:
    """Sentinel 核心引擎 — 协调LLM、安全工具、告警、交互"""

    def __init__(self, config_path: Optional[Path] = None):
        self.config = Config.load(config_path)
        self.llm = LLMRouter(self.config.model)
        self.context = ContextManager(self.config)
        self.memory = MemoryStore(self.config.advanced.db_path)
        self._running = False
        self._tasks: list[asyncio.Task] = []

    async def start(self):
        """启动引擎 — 初始化所有子系统"""
        logger.info("🚀 Sentinel Engine starting...")
        self._running = True

        # 初始化LLM连接
        await self.llm.initialize()

        # 启动安全子系统
        from sentinel_security.traffic.analyzer import TrafficAnalyzer
        from sentinel_security.log.analyzer import LogAnalyzer
        from sentinel_security.asset.monitor import AssetMonitor
        from sentinel_security.alerting.engine import AlertEngine

        subsystems = []

        if self.config.security.traffic_analysis.enabled:
            traffic = TrafficAnalyzer(self.config)
            subsystems.append(traffic)
            self._tasks.append(asyncio.create_task(traffic.run()))

        if self.config.security.log_analysis.enabled:
            log_analyzer = LogAnalyzer(self.config)
            subsystems.append(log_analyzer)
            self._tasks.append(asyncio.create_task(log_analyzer.run()))

        if self.config.security.asset_monitoring.enabled:
            asset_monitor = AssetMonitor(self.config)
            subsystems.append(asset_monitor)
            self._tasks.append(asyncio.create_task(asset_monitor.run()))

        alert_engine = AlertEngine(self.config, subsystems)
        self._tasks.append(asyncio.create_task(alert_engine.run()))

        logger.info(f"✅ Sentinel Engine started with {len(subsystems)} subsystems")

    async def stop(self):
        """停止引擎"""
        logger.info("🛑 Sentinel Engine stopping...")
        self._running = False
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        logger.info("✅ Sentinel Engine stopped")

    async def analyze(self, prompt: str, context: dict = None) -> str:
        """AI分析入口 — 对话式安全分析"""
        messages = self.context.build_messages(prompt, context)
        return await self.llm.chat(messages)

    async def handle_alert(self, alert: dict) -> str:
        """处理安全告警 — AI分析和建议"""
        prompt = self._build_alert_prompt(alert)
        analysis = await self.analyze(prompt, {"alert": alert})
        return analysis

    def _build_alert_prompt(self, alert: dict) -> str:
        return f"""安全告警分析：

类型: {alert.get('type')}
严重级别: {alert.get('severity')}
来源: {alert.get('source')}
时间: {alert.get('timestamp')}
详情: {alert.get('details')}

请分析：
1. 攻击类型和手法
2. 威胁程度评估
3. 建议的处理措施
4. 是否需要升级响应"""
