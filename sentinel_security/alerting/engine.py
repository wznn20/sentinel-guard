"""
Sentinel Alert Engine — 告警分级、合并、分发
"""
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional

logger = logging.getLogger("sentinel.alert")


class AlertEngine:
    """告警引擎 — 接收各子系统告警，去重合并后分发"""

    def __init__(self, config, subsystems: list):
        self.config = config
        self.subsystems = subsystems
        self._running = False
        self._alert_queue: asyncio.Queue = asyncio.Queue()
        self._recent_alerts: dict = {}  # 去重

    async def run(self):
        """主循环 - 处理告警队列"""
        logger.info("🔔 Alert Engine started")
        self._running = True

        while self._running:
            try:
                alert = await asyncio.wait_for(self._alert_queue.get(), timeout=1.0)
                await self._process_alert(alert)
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error(f"Alert processing error: {e}")

    async def _process_alert(self, alert: dict):
        """处理单条告警 — 去重、分级、分发"""
        dedup_key = f"{alert.get('type')}:{alert.get('source_ip')}"

        # 去重：5分钟内同类告警合并
        if dedup_key in self._recent_alerts:
            last_time = self._recent_alerts[dedup_key]
            if datetime.now() - last_time < timedelta(minutes=5):
                logger.debug(f"Suppressed duplicate alert: {dedup_key}")
                return

        self._recent_alerts[dedup_key] = datetime.now()

        # 清理过期去重记录
        cutoff = datetime.now() - timedelta(minutes=10)
        self._recent_alerts = {
            k: v for k, v in self._recent_alerts.items() if v > cutoff
        }

        # 分发到各平台
        await self._dispatch(alert)

    async def push(self, alert: dict):
        """子系统推送告警"""
        await self._alert_queue.put(alert)

    async def _dispatch(self, alert: dict):
        """分发告警到通知平台"""
        severity_emoji = {
            "critical": "🔴", "high": "🟠",
            "medium": "🟡", "low": "🔵", "info": "⚪"
        }
        emoji = severity_emoji.get(alert.get("severity", "info"), "⚪")

        message = (
            f"{emoji} **{alert.get('severity', 'INFO').upper()}** "
            f"{alert.get('type', 'Unknown')}\n"
            f"来源: {alert.get('source_ip', 'N/A')}\n"
            f"目标: {alert.get('destination', 'N/A')}\n"
            f"时间: {alert.get('timestamp', datetime.now().isoformat())}\n"
            f"详情: {alert.get('details', '无')}"
        )

        logger.info(f"Alert dispatched: {message[:100]}...")
        # TODO: 推送到QQ/飞书/Discord等

    async def stop(self):
        self._running = False
        logger.info("Alert Engine stopped")
