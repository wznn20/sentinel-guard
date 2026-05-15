"""
Sentinel Context Manager — 对话上下文管理
"""
from typing import Optional


class ContextManager:
    """管理AI对话上下文，注入安全知识和资产信息"""

    def __init__(self, config):
        self.config = config
        self.system_prompt = self._build_system_prompt()

    def _build_system_prompt(self) -> str:
        assets_desc = "\n".join(
            f"- {a.name} ({a.host}, {a.type})"
            for a in self.config.assets
        ) if self.config.assets else "- 未配置资产"

        return f"""你是 Sentinel，一个AI网络安全智能体。你是纯防御型安全助手。

## 你的职责
- 监控和分析安全事件
- 识别攻击和异常行为
- 提供安全建议和处理方案
- 收集攻击证据
- 生成安全报告

## 重要规则
- 你绝不提供攻击代码、渗透工具或利用方法
- 你只分析和防御，不做任何形式的攻击
- 涉及主动操作（封禁IP、修改配置）时，需要用户确认
- 不确定时坦诚说明，不做猜测

## 当前资产
{assets_desc}

## 安全能力
- 实时流量分析：检测异常流量、DDoS、扫描、数据泄露
- 日志分析：Web/系统/应用日志的攻击模式识别
- 资产监控：端口变化、SSL证书、文件完整性
- 证据收集：PCAP抓包、日志快照、攻击链重建
- 威胁情报：IP/域名信誉查询、CVE匹配

请用中文回复。保持专业、简洁、可操作。"""

    def build_messages(self, user_prompt: str, context: Optional[dict] = None) -> list:
        """构建LLM消息列表"""
        messages = [
            {"role": "system", "content": self.system_prompt},
        ]

        if context:
            context_str = "\n".join(f"{k}: {v}" for k, v in context.items())
            messages.append({
                "role": "system",
                "content": f"当前上下文:\n{context_str}"
            })

        messages.append({"role": "user", "content": user_prompt})
        return messages
