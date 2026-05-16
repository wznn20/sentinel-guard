"""
Sentinel Core Engine — AI网络安全智能体
借鉴 Hermes agent loop 设计，轻量但完整。
"""
import json
import logging
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger("sentinel")


class SentinelAgent:
    """Sentinel 核心 — 对话式AI安全助手

    用法:
        agent = SentinelAgent(config_path="~/.sentinel/config.yaml")
        response = agent.chat("帮我分析一下最近的攻击日志")
    """

    def __init__(self, config_path: Optional[Path] = None):
        import yaml

        if config_path is None:
            config_path = Path.home() / ".sentinel" / "config.yaml"

        self.config_path = Path(config_path)
        if self.config_path.exists():
            with open(self.config_path) as f:
                self.cfg = yaml.safe_load(f) or {}
        else:
            self.cfg = {}

        model_cfg = self.cfg.get("model", {})
        self.provider = model_cfg.get("provider", "openai")
        self.model = model_cfg.get("model", "gpt-4o")
        self.api_key = model_cfg.get("api_key", "") or os.environ.get("SENTINEL_API_KEY", "")

        # 尝试从环境变量获取对应provider的key
        if not self.api_key:
            env_map = {
                "openai": "OPENAI_API_KEY",
                "anthropic": "ANTHROPIC_API_KEY",
                "deepseek": "DEEPSEEK_API_KEY",
            }
            self.api_key = os.environ.get(env_map.get(self.provider, ""))

        self._client = None
        self.messages: list[dict] = []
        self.max_iterations = 20

    def _get_client(self):
        """惰性加载 OpenAI 客户端"""
        if self._client is None:
            from openai import OpenAI

            if self.provider in ("openai", "custom"):
                base = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
            elif self.provider == "deepseek":
                base = "https://api.deepseek.com/v1"
            elif self.provider == "anthropic":
                base = "https://api.anthropic.com/v1"
            elif self.provider == "zhipu":
                base = "https://open.bigmodel.cn/api/paas/v4"
            elif self.provider == "ollama":
                base = "http://localhost:11434/v1"
            else:
                base = "https://api.openai.com/v1"

            self._client = OpenAI(api_key=self.api_key, base_url=base)
        return self._client

    @property
    def system_prompt(self) -> str:
        return """你是 Sentinel，一个纯防御型 AI 网络安全智能体。

你的职责：
1. 分析安全日志、检测攻击行为
2. 提供安全建议和修复方案
3. 回答网络安全相关问题
4. 帮助用户理解和处理安全事件

重要原则：
- 你只做防御，不执行任何攻击性操作
- 你不会提供恶意代码、漏洞利用脚本
- 对于不确定的事情，你会诚实说明
- 回复简洁专业，用中文

你有以下工具可用：
- analyze_logs: 分析指定路径的 Web 服务器日志
- check_threat: 查询一个 IP/域名/URL 的威胁情报
- scan_config: 检查服务器安全配置"""

    def chat(self, message: str, stream: bool = False) -> str:
        """发送消息并获取回复（对话模式）"""
        if not self.api_key:
            return (
                "❌ 未配置 API Key。请运行 `sentinel setup` 设置，"
                "或设置环境变量 SENTINEL_API_KEY / OPENAI_API_KEY。"
            )

        # 如果消息列表为空，添加系统提示
        if not self.messages:
            self.messages.append({"role": "system", "content": self.system_prompt})

        self.messages.append({"role": "user", "content": message})

        try:
            response = self._run_loop(stream=stream)
        except Exception as e:
            response = f"❌ 调用 AI 模型失败: {e}\n请检查: 1) API Key 是否正确 2) 网络是否可达 3) 模型名称是否支持"
            self.messages.pop()  # 移除失败的用户消息

        return response

    def _run_loop(self, stream: bool = False) -> str:
        """核心 agent loop — 调用模型 → 执行工具 → 循环直到得到文本回复"""
        client = self._get_client()
        tools = self._get_tools()
        tool_schemas = self._tool_schemas()

        # 保持消息列表在合理长度
        if len(self.messages) > 30:
            # 保留系统消息 + 最近29条
            self.messages = [self.messages[0]] + self.messages[-29:]

        call_count = 0
        while call_count < self.max_iterations:
            call_count += 1

            kwargs = dict(
                model=self.model,
                messages=self.messages,
                max_tokens=2048,
            )
            if tool_schemas:
                kwargs["tools"] = tool_schemas

            if stream:
                response = client.chat.completions.create(**kwargs, stream=True)
                # 流式模式：收集完整响应
                full_content = ""
                tool_calls_data = []
                for chunk in response:
                    delta = chunk.choices[0].delta
                    if delta.content:
                        full_content += delta.content
                    if delta.tool_calls:
                        for tc in delta.tool_calls:
                            idx = tc.index
                            while len(tool_calls_data) <= idx:
                                tool_calls_data.append({"id": "", "function": {"name": "", "arguments": ""}})
                            if tc.id:
                                tool_calls_data[idx]["id"] = tc.id
                            if tc.function:
                                if tc.function.name:
                                    tool_calls_data[idx]["function"]["name"] = tc.function.name
                                tool_calls_data[idx]["function"]["arguments"] += tc.function.arguments or ""

                if tool_calls_data:
                    self.messages.append({"role": "assistant", "content": full_content or None, "tool_calls": tool_calls_data})
                    for tc in tool_calls_data:
                        result = self._execute_tool(tc["function"]["name"], tc["function"]["arguments"])
                        self.messages.append({
                            "role": "tool",
                            "tool_call_id": tc["id"],
                            "content": result,
                        })
                    continue
                else:
                    self.messages.append({"role": "assistant", "content": full_content})
                    return full_content
            else:
                response = client.chat.completions.create(**kwargs)
                msg = response.choices[0].message

                if msg.tool_calls:
                    # 记录助手消息
                    assistant_msg = {"role": "assistant", "content": msg.content}
                    tcs = []
                    for tc in msg.tool_calls:
                        tcs.append({
                            "id": tc.id,
                            "type": "function",
                            "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                        })
                    assistant_msg["tool_calls"] = tcs
                    self.messages.append(assistant_msg)

                    # 执行工具
                    for tc in tcs:
                        result = self._execute_tool(tc["function"]["name"], tc["function"]["arguments"])
                        self.messages.append({
                            "role": "tool",
                            "tool_call_id": tc["id"],
                            "content": result,
                        })
                    continue
                else:
                    self.messages.append({"role": "assistant", "content": msg.content})
                    return msg.content

        return "⚠️ 达到最大推理步数，请简化问题重试。"

    def _get_tools(self) -> dict:
        """返回工具函数映射"""
        return {
            "analyze_logs": self._tool_analyze_logs,
            "check_threat": self._tool_check_threat,
            "scan_config": self._tool_scan_config,
        }

    def _tool_schemas(self) -> list:
        """OpenAI 工具 schema"""
        return [
            {
                "type": "function",
                "function": {
                    "name": "analyze_logs",
                    "description": "分析 Web 服务器日志文件，检测攻击行为",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "path": {"type": "string", "description": "日志文件完整路径"},
                            "lines": {"type": "integer", "description": "分析最近N行，默认500", "default": 500},
                        },
                        "required": ["path"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "check_threat",
                    "description": "查询 IP/域名/URL 的基本威胁信息（whois、端口等）",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "target": {"type": "string", "description": "IP地址、域名、或URL"},
                        },
                        "required": ["target"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "scan_config",
                    "description": "检查当前服务器的安全配置状态",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "check_type": {
                                "type": "string",
                                "enum": ["ssh", "firewall", "ports", "all"],
                                "description": "检查类型",
                                "default": "all",
                            },
                        },
                    },
                },
            },
        ]

    def _execute_tool(self, name: str, args_str: str) -> str:
        """执行工具调用"""
        try:
            args = json.loads(args_str) if args_str else {}
        except json.JSONDecodeError:
            args = {}

        tool_fn = self._get_tools().get(name)
        if tool_fn:
            try:
                return tool_fn(**args)
            except Exception as e:
                return f"工具执行错误: {e}"
        return f"未知工具: {name}"

    # ── 工具实现 ──

    def _tool_analyze_logs(self, path: str, lines: int = 500) -> str:
        """分析日志文件"""
        p = Path(path)
        if not p.exists():
            return f"❌ 文件不存在: {path}"

        try:
            with open(p, errors="ignore") as f:
                all_lines = f.readlines()

            recent = all_lines[-lines:] if len(all_lines) > lines else all_lines
            content = "".join(recent)

            # 攻击特征检测
            from sentinel_security.traffic.signatures.web_attacks import ATTACK_SIGNATURES

            findings = []
            for sig in ATTACK_SIGNATURES:
                matches = sig["pattern"].findall(content)
                if matches:
                    findings.append(f"- {sig['name']} ({sig['severity']}): 发现 {len(matches)} 处匹配")

            summary = f"""日志分析结果: {path}
总行数: {len(all_lines)}
分析范围: 最近 {len(recent)} 行

攻击特征检测:
{chr(10).join(findings) if findings else '✅ 未发现已知攻击特征'}

原始日志样例 (最近10行):
{''.join(recent[-10:])[:2000]}
"""
            return summary
        except Exception as e:
            return f"❌ 日志分析失败: {e}"

    def _tool_check_threat(self, target: str) -> str:
        """威胁情报查询"""
        import subprocess

        results = [f"威胁查询: {target}\n"]

        # 提取IP或域名
        clean = target.replace("https://", "").replace("http://", "").split("/")[0].split(":")[0]

        # DNS查询
        try:
            import socket
            ip = socket.gethostbyname(clean)
            results.append(f"解析IP: {ip}")
            results.append(f"主机名: {socket.gethostbyaddr(ip)[0] if ip != clean else 'N/A'}")
        except Exception:
            results.append("DNS解析: 失败")

        # 检查是否可ping
        try:
            r = subprocess.run(["ping", "-c", "1", "-W", "3", clean],
                             capture_output=True, text=True, timeout=5)
            results.append(f"可达性: {'✅ 可达' if r.returncode == 0 else '❌ 不可达'}")
        except Exception:
            results.append("可达性: 无法检测")

        # 检查本地端口（仅对localhost/内网有效）
        try:
            r = subprocess.run(["ss", "-tlnp"], capture_output=True, text=True, timeout=3)
            listening = [l for l in r.stdout.split("\n") if "LISTEN" in l]
            results.append(f"\n本机监听端口: {len(listening)} 个")
        except Exception:
            pass

        return "\n".join(results)

    def _tool_scan_config(self, check_type: str = "all") -> str:
        """安全配置检查"""
        import subprocess
        import platform

        results = [f"安全配置检查 ({platform.system()})\n"]

        if check_type in ("ssh", "all"):
            sshd_config = Path("/etc/ssh/sshd_config")
            if sshd_config.exists():
                content = sshd_config.read_text()
                issues = []
                if "PermitRootLogin yes" in content and "PermitRootLogin prohibit-password" not in content:
                    issues.append("⚠️  Root登录未禁用")
                if "PasswordAuthentication yes" in content:
                    issues.append("⚠️  密码认证已启用（建议用密钥）")
                if "Port 22" in content and "Port " not in content.replace("Port 22", ""):
                    issues.append("ℹ️  使用默认22端口")
                results.append(f"SSH配置: {sshd_config}")
                results.extend(issues if issues else ["✅ SSH配置安全"])
            else:
                results.append("SSH: 未找到 sshd_config")

        if check_type in ("firewall", "all"):
            try:
                r = subprocess.run(["iptables", "-L", "-n"], capture_output=True, text=True, timeout=5)
                rules_count = len([l for l in r.stdout.split("\n") if l and not l.startswith("Chain")])
                results.append(f"\n防火墙规则: {rules_count} 条")
            except Exception:
                results.append("\n防火墙: 无法检查 (需要 root)")

        if check_type in ("ports", "all"):
            try:
                r = subprocess.run(["ss", "-tlnp"], capture_output=True, text=True, timeout=3)
                ports = []
                for line in r.stdout.split("\n"):
                    if "LISTEN" in line:
                        parts = line.split()
                        if len(parts) >= 5:
                            addr = parts[4]
                            ports.append(addr)
                results.append(f"\n监听端口:\n" + "\n".join(f"  {p}" for p in ports) if ports else "  无对外监听")
            except Exception:
                pass

        return "\n".join(results)


# 便捷函数
def create_agent(config_path: Optional[str] = None) -> SentinelAgent:
    """工厂函数 — 从配置文件创建 Agent"""
    return SentinelAgent(Path(config_path) if config_path else None)
