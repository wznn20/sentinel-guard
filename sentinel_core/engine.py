"""
Sentinel Core Engine — AI网络安全智能体 (v0.3.0)
基于 litellm，支持 100+ AI 模型提供商
借鉴 Hermes agent loop 设计
"""
import json
import os
import re
import time
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional


# ═══════════════════════════════════════════
# SentinelAgent — 核心对话引擎
# ═══════════════════════════════════════════

class SentinelAgent:
    """Sentinel AI 安全助手 — litellm 驱动

    用法:
        agent = SentinelAgent(config_path=Path("~/.sentinel/config.yaml"))
        response = agent.chat("分析最近的攻击日志")
    """

    def __init__(self, config_path: Optional[Path] = None):
        import yaml

        if config_path is None:
            config_path = Path.home() / ".sentinel" / "config.yaml"

        self.config_path = Path(config_path)
        self.cfg = {}
        if self.config_path.exists():
            with open(self.config_path) as f:
                self.cfg = yaml.safe_load(f) or {}

        model_cfg = self.cfg.get("model", {})
        self.provider = model_cfg.get("provider", "openai")
        self.model = model_cfg.get("model", "gpt-4o-mini")
        self.api_key = model_cfg.get("api_key", "")
        self.base_url = model_cfg.get("base_url")

        # 尝试从环境变量获取 API key
        if not self.api_key:
            env_map = {
                "openai": "OPENAI_API_KEY",
                "anthropic": "ANTHROPIC_API_KEY",
                "google": "GEMINI_API_KEY",
                "deepseek": "DEEPSEEK_API_KEY",
                "xai": "XAI_API_KEY",
                "mistral": "MISTRAL_API_KEY",
                "cohere": "COHERE_API_KEY",
                "groq": "GROQ_API_KEY",
                "together": "TOGETHER_API_KEY",
                "fireworks": "FIREWORKS_API_KEY",
                "replicate": "REPLICATE_API_KEY",
                "zhipu": "ZHIPU_API_KEY",
                "moonshot": "MOONSHOT_API_KEY",
                "qwen": "DASHSCOPE_API_KEY",
                "baidu": "BAIDU_API_KEY",
                "minimax": "MINIMAX_API_KEY",
                "stepfun": "STEPFUN_API_KEY",
                "yi": "YI_API_KEY",
                "doubao": "DOUBAO_API_KEY",
                "baichuan": "BAICHUAN_API_KEY",
                "openrouter": "OPENROUTER_API_KEY",
                "bedrock": "AWS_ACCESS_KEY_ID",
            }
            key_name = env_map.get(self.provider, "")
            if key_name:
                self.api_key = os.environ.get(key_name, "")
                # bedrock 需要额外处理
                if self.provider == "bedrock":
                    secret = os.environ.get("AWS_SECRET_ACCESS_KEY", "")
                    region = os.environ.get("AWS_REGION_NAME", "us-east-1")
                    if self.api_key and secret:
                        os.environ.setdefault("AWS_SECRET_ACCESS_KEY", secret)
                        os.environ.setdefault("AWS_REGION_NAME", region)

        # 最后兜底：SENTINEL_API_KEY
        if not self.api_key:
            self.api_key = os.environ.get("SENTINEL_API_KEY", "")

        # 设置 base_url
        if self.base_url:
            os.environ["OPENAI_API_BASE"] = self.base_url

        self.messages: list[dict] = []
        self.max_iterations = 15
        self._db = None

    @property
    def system_prompt(self) -> str:
        """Sentinel 系统提示"""
        return """你是 Sentinel，一个纯防御型 AI 网络安全智能体。

你的核心职责：
1. **分析安全日志** — 识别 SQL注入、XSS、SSRF、命令注入、路径遍历等攻击
2. **威胁情报查询** — 查询 IP/域名/URL 的安全信誉
3. **安全配置检查** — 审计服务器配置并提供加固建议
4. **事件响应指导** — 帮助用户理解和处理安全事件

重要原则：
- 纯防御 — 不提供攻击代码、漏洞利用脚本、恶意工具
- 准确诚实 — 对于不确定的事情，明确说明
- 简洁专业 — 用中文回复，直接给结论和建议
- 可取证 — 发现攻击时，保留证据和来源

你有以下工具可用：
- analyze_logs(path): 分析指定路径的 Web 服务器日志，检测攻击行为
- check_threat(target): 查询 IP/域名/URL 的威胁情报（模拟）
- scan_config(path): 检查服务器/应用的安全配置

工具使用规则：
- 如果用户提供了日志路径，先调用 analyze_logs
- 如果用户提到了可疑 IP/域名，先调用 check_threat
- 如果用户问配置安全，先调用 scan_config
- 工具返回 JSON，你需要解读并给出自然语言建议"""

    # ── 工具集 ──

    def tool_analyze_logs(self, path: str) -> str:
        """分析 Web 服务器日志"""
        from sentinel_security.traffic.signatures.web_attacks import ATTACK_SIGNATURES

        try:
            p = Path(path)
            if not p.exists():
                return json.dumps({"error": f"文件不存在: {path}"})

            content = p.read_text(errors="ignore")
            lines = content.split("\n")
            findings = []

            for sig in ATTACK_SIGNATURES:
                matches = sig["pattern"].findall(content)
                if matches:
                    findings.append({
                        "attack_type": sig["name"],
                        "severity": sig["severity"],
                        "category": sig["category"],
                        "count": len(matches),
                        "samples": matches[:3],
                    })

            return json.dumps({
                "file": path,
                "total_lines": len(lines),
                "findings": findings,
                "summary": f"发现 {len(findings)} 类攻击特征" if findings else "未发现已知攻击特征",
                "timestamp": datetime.now().isoformat(),
            }, ensure_ascii=False, indent=2)
        except Exception as e:
            return json.dumps({"error": str(e)})

    def tool_check_threat(self, target: str) -> str:
        """威胁情报查询（模拟）"""
        import hashlib

        # 简化的威胁判断逻辑
        is_ip = re.match(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$", target)

        result = {
            "target": target,
            "type": "ip" if is_ip else "domain",
            "risk_level": "low",
            "known_malicious": False,
            "recommendations": [],
            "timestamp": datetime.now().isoformat(),
        }

        # 模拟已知恶意 IP
        known_bad = ["185.220.101.", "45.33.32.", "192.42.116.", "23.129.64."]
        if is_ip and any(target.startswith(p) for p in known_bad):
            result["risk_level"] = "high"
            result["known_malicious"] = True
            result["recommendations"] = ["立即封禁此IP", "检查相关访问日志", "更新防火墙规则"]

        return json.dumps(result, ensure_ascii=False, indent=2)

    def tool_scan_config(self, path: str) -> str:
        """安全配置检查"""
        p = Path(path)
        if not p.exists():
            return json.dumps({"error": f"路径不存在: {path}"})

        findings = []
        try:
            content = p.read_text(errors="ignore")

            # 常见不安全配置检测
            checks = [
                ("debug.*=.*true", "debug 模式开启", "high", "生产环境应关闭 debug 模式"),
                ("password.*=.*['\"]?(admin|123456|password)['\"]?", "弱密码", "critical", "检测到弱密码，请立即更换"),
                ("ssl.*=.*false", "SSL 未启用", "high", "建议启用 SSL/TLS"),
                ("0\\.0\\.0\\.0", "监听所有接口", "medium", "确认是否需要绑定所有网络接口"),
                ("PermitRootLogin.*yes", "SSH root 登录", "high", "建议禁用 root SSH 登录"),
                ("PasswordAuthentication.*yes", "SSH 密码认证", "medium", "建议使用密钥认证替代密码"),
            ]

            for pattern, issue, severity, fix in checks:
                matches = re.findall(pattern, content, re.IGNORECASE)
                if matches:
                    findings.append({
                        "issue": issue,
                        "severity": severity,
                        "matches": matches[:3],
                        "fix": fix,
                    })

            return json.dumps({
                "file": path,
                "findings": findings,
                "summary": f"发现 {len(findings)} 个安全问题" if findings else "未发现已知安全问题",
                "timestamp": datetime.now().isoformat(),
            }, ensure_ascii=False, indent=2)
        except Exception as e:
            return json.dumps({"error": str(e)})

    # ── 聊天 ──

    def chat(self, message: str, stream: bool = False) -> str:
        """发送消息并获取回复"""
        if not self.api_key and self.provider not in ("ollama", "vllm", "lmstudio"):
            return "❌ 未配置 API Key。请运行 sentinel setup 或设置环境变量。"

        tools = [
            {
                "type": "function",
                "function": {
                    "name": "analyze_logs",
                    "description": "分析指定路径的 Web 服务器日志，检测 SQL注入/XSS/SSRF/命令注入等攻击行为",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "path": {"type": "string", "description": "日志文件路径，如 /var/log/nginx/access.log"}
                        },
                        "required": ["path"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "check_threat",
                    "description": "查询一个 IP 地址、域名或 URL 的威胁情报和风险等级",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "target": {"type": "string", "description": "IP地址、域名或URL"}
                        },
                        "required": ["target"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "scan_config",
                    "description": "检查服务器或应用的安全配置文件，发现弱密码/调试模式/不安全配置等问题",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "path": {"type": "string", "description": "配置文件路径，如 /etc/ssh/sshd_config 或 .env"}
                        },
                        "required": ["path"],
                    },
                },
            },
        ]

        self.messages.append({"role": "user", "content": message})

        try:
            from litellm import completion
        except ImportError:
            return "❌ 需要安装 litellm: pip install litellm"

        # 构建 litellm 模型名
        litellm_model = self._build_model_name()

        for iteration in range(self.max_iterations):
            try:
                resp = completion(
                    model=litellm_model,
                    messages=[{"role": "system", "content": self.system_prompt}] + self.messages[-20:],
                    tools=tools,
                    tool_choice="auto",
                    api_key=self.api_key or None,
                    api_base=self.base_url,
                    timeout=60,
                )
            except Exception as e:
                error_msg = str(e)
                if "api_key" in error_msg.lower() or "unauthorized" in error_msg.lower() or "authentication" in error_msg.lower():
                    return f"❌ API 认证失败。请检查 API Key 是否正确。\n\n运行 sentinel setup 重新配置。"
                elif "timeout" in error_msg.lower():
                    return f"⏱️ 请求超时。网络可能有问题，请重试。"
                elif "not found" in error_msg.lower() and "model" in error_msg.lower():
                    return f"❌ 模型 '{self.model}' 在提供商 '{self.provider}' 上不存在。\n\n请运行 sentinel setup 更换模型。"
                else:
                    return f"❌ 请求失败: {error_msg[:200]}"

            msg = resp.choices[0].message

            if msg.tool_calls:
                self.messages.append({"role": "assistant", "content": msg.content or "", "tool_calls": [
                    {"id": tc.id, "type": "function", "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                    for tc in msg.tool_calls
                ]} if hasattr(msg, "tool_calls") and msg.tool_calls else {"role": "assistant", "content": msg.content or ""})

                for tc in msg.tool_calls or []:
                    func_name = tc.function.name
                    try:
                        args = json.loads(tc.function.arguments)
                    except json.JSONDecodeError:
                        args = {}

                    # 执行工具
                    if func_name == "analyze_logs":
                        result = self.tool_analyze_logs(args.get("path", ""))
                    elif func_name == "check_threat":
                        result = self.tool_check_threat(args.get("target", ""))
                    elif func_name == "scan_config":
                        result = self.tool_scan_config(args.get("path", ""))
                    else:
                        result = json.dumps({"error": f"未知工具: {func_name}"})

                    self.messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "name": func_name,
                        "content": result,
                    })
                continue

            # 文本回复
            if msg.content:
                self.messages.append({"role": "assistant", "content": msg.content})
                return msg.content

            return "（模型未返回内容）"

        return "⚠️ 达到最大工具调用次数，请简化问题。"

    def _build_model_name(self) -> str:
        """构建 litellm 兼容的模型名（provider/model）"""
        # 这些 provider 在 litellm 中不需要前缀
        no_prefix = {"openai", "anthropic", "deepseek", "google", "groq", "mistral", "cohere", "xai"}
        if self.provider in no_prefix:
            return f"{self.provider}/{self.model}"

        # litellm 特殊前缀映射
        prefix_map = {
            "zhipu": "zhipu",
            "qwen": "dashscope",
            "moonshot": "moonshot",
            "baidu": "baidu",
            "minimax": "minimax",
            "stepfun": "stepfun",
            "yi": "yi",
            "doubao": "doubao",
            "baichuan": "baichuan",
            "openrouter": "openrouter",
            "together": "together_ai",
            "fireworks": "fireworks_ai",
            "replicate": "replicate",
            "bedrock": "bedrock",
            "vertex": "vertex_ai",
            "azure": "azure",
            "ollama": "ollama",
            "vllm": "openai",
            "lmstudio": "openai",
            "custom": "openai",
        }

        prefix = prefix_map.get(self.provider, self.provider)
        return f"{prefix}/{self.model}"

    def clear(self):
        """清空对话历史"""
        self.messages = []


# ═══════════════════════════════════════════
# 告警数据库
# ═══════════════════════════════════════════

class AlertDB:
    """告警数据库管理"""

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or Path.home() / ".sentinel" / "alerts.db"
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        conn = sqlite3.connect(str(self.db_path))
        conn.execute("""CREATE TABLE IF NOT EXISTS alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            type TEXT NOT NULL,
            severity TEXT NOT NULL,
            source TEXT,
            evidence TEXT,
            resolved INTEGER DEFAULT 0
        )""")
        conn.commit()
        conn.close()

    def insert(self, alert_type: str, severity: str, source: str, evidence: str = ""):
        conn = sqlite3.connect(str(self.db_path))
        conn.execute(
            "INSERT INTO alerts (timestamp, type, severity, source, evidence) VALUES (?,?,?,?,?)",
            (datetime.now().isoformat(), alert_type, severity, source, evidence[:500]),
        )
        conn.commit()
        conn.close()

    def stats(self) -> dict:
        conn = sqlite3.connect(str(self.db_path))
        total = conn.execute("SELECT COUNT(*) FROM alerts").fetchone()[0]
        unresolved = conn.execute("SELECT COUNT(*) FROM alerts WHERE resolved=0").fetchone()[0]
        by_severity = {}
        for row in conn.execute("SELECT severity, COUNT(*) FROM alerts GROUP BY severity"):
            by_severity[row[0]] = row[1]
        conn.close()
        return {"total": total, "unresolved": unresolved, "by_severity": by_severity}

    def list(self, limit: int = 20, unresolved_only: bool = False) -> list:
        conn = sqlite3.connect(str(self.db_path))
        query = "SELECT id, timestamp, type, severity, source, evidence, resolved FROM alerts"
        if unresolved_only:
            query += " WHERE resolved=0"
        query += " ORDER BY id DESC LIMIT ?"
        rows = conn.execute(query, (limit,)).fetchall()
        conn.close()
        return [
            {"id": r[0], "timestamp": r[1], "type": r[2], "severity": r[3],
             "source": r[4], "evidence": r[5], "resolved": bool(r[6])}
            for r in rows
        ]
