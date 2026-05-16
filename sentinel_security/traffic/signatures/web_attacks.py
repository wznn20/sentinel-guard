"""
Web Attack Detection Signatures
纯检测，无利用 — 识别攻击流量特征
"""
import re
from dataclasses import dataclass
from typing import Optional


@dataclass
class SignatureMatch:
    name: str
    category: str          # sqli / xss / ssrf / cmdi / traversal / upload
    severity: str
    confidence: float      # 0.0-1.0
    matched_pattern: str
    evidence: str


# SQL注入检测模式（只检测，不利用）
SQLI_PATTERNS = [
    (r"(?i)(\bUNION\s+(ALL\s+)?SELECT\b)", "UNION SELECT注入", "high"),
    (r"(?i)(\bSELECT\b.*\bFROM\b.*\bWHERE\b)", "内联SQL注入", "medium"),
    (r"(?i)(\bOR\s+['\"]?\d+['\"]?\s*=\s*['\"]?\d+['\"]?)", "OR 恒等绕过", "high"),
    (r"(?i)(\bSLEEP\s*\(|benchmark\s*\()", "时间盲注", "critical"),
    (r"(?i)(--\s*$|#\s*$|\/\*\*\/)", "SQL注释绕过", "medium"),
    (r"(?i)(\bINFORMATION_SCHEMA\b)", "信息架构探测", "medium"),
    (r"(?i)(\bLOAD_FILE\b|\bINTO\s+OUTFILE\b)", "文件操作注入", "critical"),
    (r"(?i)(\bEXEC\s*\()", "命令执行注入", "critical"),
]

# XSS检测模式
XSS_PATTERNS = [
    (r"(?i)(<script[^>]*>)", "脚本标签注入", "critical"),
    (r"(?i)(\bon\w+\s*=\s*['\"]?\s*javascript:)", "事件处理器注入", "high"),
    (r"(?i)(javascript\s*:\s*alert\s*\()", "JavaScript伪协议", "high"),
    (r"(?i)(<img[^>]+onerror\s*=)", "IMG onerror注入", "high"),
    (r"(?i)(<svg[^>]+onload\s*=)", "SVG onload注入", "high"),
    (r"(?i)(eval\s*\(|document\.cookie)", "eval/cookie窃取", "critical"),
    (r"(?i)(<iframe[^>]*>)", "iframe注入", "medium"),
]

# SSRF检测模式
SSRF_PATTERNS = [
    (r"(?i)(\bhttp://(?:127\.|localhost|10\.|172\.(?:1[6-9]|2\d|3[01])\.|192\.168\.))", "内网SSRF", "critical"),
    (r"(?i)(\bhttp://169\.254\.169\.254\b)", "云元数据SSRF", "critical"),
    (r"(?i)(\bfile:///\b)", "File协议SSRF", "high"),
    (r"(?i)(\bgopher://\b)", "Gopher协议SSRF", "high"),
]

# 命令注入检测模式
CMDI_PATTERNS = [
    (r"[\|\;]\s*(?:id|whoami|uname|cat\s+/etc/passwd)", "命令注入-信息收集", "critical"),
    (r"(?i)([\|\;]\s*(?:wget|curl)\s+)", "命令注入-下载", "critical"),
    (r"(?i)([\|\;]\s*(?:nc\s+|bash\s+-i|python\s+-c))", "反弹Shell", "critical"),
    (r"(?i)(\`[^\`]+\`)", "反引号命令注入", "high"),
    (r"(?i)(\$\([^\)]+\))", "子shell命令注入", "high"),
]

# 路径遍历检测模式
TRAVERSAL_PATTERNS = [
    (r"(\.\.(?:/|\\)){2,}", "目录遍历", "high"),
    (r"(?i)(/etc/(?:passwd|shadow|hosts)\b)", "敏感文件访问", "critical"),
    (r"(?i)(/proc/self/environ\b)", "procfs访问", "high"),
    (r"(%2e%2e(?:/|%2f)){2,}", "编码目录遍历", "high"),
]


def detect_sqli(payload: str) -> list[SignatureMatch]:
    """检测SQL注入特征"""
    matches = []
    for pattern, name, severity in SQLI_PATTERNS:
        if m := re.search(pattern, payload):
            matches.append(SignatureMatch(
                name=name, category="sqli", severity=severity,
                confidence=0.9, matched_pattern=pattern,
                evidence=m.group(0)[:100]
            ))
    return matches


def detect_xss(payload: str) -> list[SignatureMatch]:
    """检测XSS特征"""
    matches = []
    for pattern, name, severity in XSS_PATTERNS:
        if m := re.search(pattern, payload):
            matches.append(SignatureMatch(
                name=name, category="xss", severity=severity,
                confidence=0.85, matched_pattern=pattern,
                evidence=m.group(0)[:100]
            ))
    return matches


def detect_ssrf(payload: str) -> list[SignatureMatch]:
    """检测SSRF特征"""
    matches = []
    for pattern, name, severity in SSRF_PATTERNS:
        if m := re.search(pattern, payload):
            matches.append(SignatureMatch(
                name=name, category="ssrf", severity=severity,
                confidence=0.9, matched_pattern=pattern,
                evidence=m.group(0)[:100]
            ))
    return matches


def detect_cmdi(payload: str) -> list[SignatureMatch]:
    """检测命令注入特征"""
    matches = []
    for pattern, name, severity in CMDI_PATTERNS:
        if m := re.search(pattern, payload):
            matches.append(SignatureMatch(
                name=name, category="cmdi", severity=severity,
                confidence=0.9, matched_pattern=pattern,
                evidence=m.group(0)[:100]
            ))
    return matches


def detect_traversal(payload: str) -> list[SignatureMatch]:
    """检测路径遍历特征"""
    matches = []
    for pattern, name, severity in TRAVERSAL_PATTERNS:
        if m := re.search(pattern, payload):
            matches.append(SignatureMatch(
                name=name, category="traversal", severity=severity,
                confidence=0.95, matched_pattern=pattern,
                evidence=m.group(0)[:100]
            ))
    return matches


# 统一攻击特征库（用于AI工具调用的批量检测）
ALL_PATTERNS = SQLI_PATTERNS + XSS_PATTERNS + SSRF_PATTERNS + CMDI_PATTERNS + TRAVERSAL_PATTERNS

ATTACK_SIGNATURES = [
    {"name": name, "pattern": re.compile(pattern), "severity": severity}
    for pattern, name, severity in ALL_PATTERNS
]

def analyze_http_request(method: str, path: str, headers: dict, body: str = "") -> list[SignatureMatch]:
    """综合分析HTTP请求 — 检测所有类型攻击"""
    all_matches = []

    # 检查URL参数
    all_matches.extend(detect_sqli(path))
    all_matches.extend(detect_xss(path))
    all_matches.extend(detect_ssrf(path))
    all_matches.extend(detect_cmdi(path))
    all_matches.extend(detect_traversal(path))

    # 检查Body
    if body:
        all_matches.extend(detect_sqli(body))
        all_matches.extend(detect_xss(body))
        all_matches.extend(detect_cmdi(body))

    # 检查Headers
    for key, value in headers.items():
        all_matches.extend(detect_sqli(str(value)))
        all_matches.extend(detect_xss(str(value)))
        all_matches.extend(detect_ssrf(str(value)))

    # 去重 + 按严重级别排序
    severity_order = {"critical": 5, "high": 4, "medium": 3, "low": 2, "info": 1}
    unique = {m.name: m for m in all_matches}.values()
    return sorted(unique, key=lambda m: severity_order.get(m.severity, 0), reverse=True)
