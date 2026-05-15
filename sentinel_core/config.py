"""
Sentinel Configuration — 配置加载与验证
"""
import os
import yaml
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ModelConfig:
    provider: str = "openrouter"
    model: str = "anthropic/claude-sonnet-4"
    api_key: str = ""

@dataclass
class TrafficAnalysisConfig:
    enabled: bool = True
    interfaces: list[str] = field(default_factory=lambda: ["eth0"])
    capture_size: int = 65535
    bpf_filter: str = ""

@dataclass
class LogAnalysisConfig:
    enabled: bool = True
    paths: list[str] = field(default_factory=lambda: ["/var/log/auth.log"])

@dataclass
class AssetMonitoringConfig:
    enabled: bool = True
    port_scan_interval: int = 3600
    file_integrity_paths: list[str] = field(default_factory=lambda: ["/etc"])

@dataclass
class SecurityConfig:
    traffic_analysis: TrafficAnalysisConfig = field(default_factory=TrafficAnalysisConfig)
    log_analysis: LogAnalysisConfig = field(default_factory=LogAnalysisConfig)
    asset_monitoring: AssetMonitoringConfig = field(default_factory=AssetMonitoringConfig)
    auto_block: bool = False

@dataclass
class Asset:
    name: str = ""
    host: str = ""
    type: str = "web_server"
    ports: list[int] = field(default_factory=list)

@dataclass
class GatewayConfig:
    web_dashboard: bool = True
    dashboard_port: int = 8443
    platforms: list[str] = field(default_factory=lambda: ["qqbot"])

@dataclass
class AdvancedConfig:
    db_path: str = "~/.sentinel/sentinel.db"
    log_level: str = "info"


class Config:
    """Sentinel配置管理"""

    DEFAULT_PATH = Path.home() / ".sentinel" / "config.yaml"

    def __init__(self):
        self.model = ModelConfig()
        self.gateway = GatewayConfig()
        self.assets: list[Asset] = []
        self.security = SecurityConfig()
        self.advanced = AdvancedConfig()

    @classmethod
    def load(cls, path: Optional[Path] = None) -> "Config":
        config = cls()
        config_path = path or cls.DEFAULT_PATH

        if config_path.exists():
            with open(config_path) as f:
                data = yaml.safe_load(f) or {}
            config._parse(data)

        # 环境变量覆盖
        if env_key := os.getenv("SENTINEL_LLM_KEY"):
            config.model.api_key = env_key

        return config

    def _parse(self, data: dict):
        if "model" in data:
            m = data["model"]
            self.model = ModelConfig(
                provider=m.get("provider", "openrouter"),
                model=m.get("model", "anthropic/claude-sonnet-4"),
                api_key=os.path.expandvars(m.get("api_key", "")),
            )

        if "gateway" in data:
            g = data["gateway"]
            self.gateway = GatewayConfig(
                web_dashboard=g.get("web_dashboard", True),
                dashboard_port=g.get("port", 8443),
            )

        if "assets" in data:
            self.assets = [
                Asset(
                    name=a.get("name", ""),
                    host=a.get("host", ""),
                    type=a.get("type", "web_server"),
                    ports=a.get("ports", []),
                )
                for a in data["assets"]
            ]

        if "security" in data:
            s = data["security"]
            self.security.auto_block = s.get("auto_block", False)

            if "traffic_analysis" in s:
                ta = s["traffic_analysis"]
                self.security.traffic_analysis = TrafficAnalysisConfig(
                    enabled=ta.get("enabled", True),
                    interfaces=ta.get("interfaces", ["eth0"]),
                    capture_size=ta.get("capture_size", 65535),
                    bpf_filter=ta.get("bpf_filter", ""),
                )

            if "log_analysis" in s:
                la = s["log_analysis"]
                self.security.log_analysis = LogAnalysisConfig(
                    enabled=la.get("enabled", True),
                    paths=la.get("paths", ["/var/log/auth.log"]),
                )

        if "advanced" in data:
            a = data["advanced"]
            self.advanced = AdvancedConfig(
                db_path=os.path.expanduser(a.get("db_path", "~/.sentinel/sentinel.db")),
                log_level=a.get("log_level", "info"),
            )

    def save(self, path: Optional[Path] = None):
        """保存配置到文件"""
        raise NotImplementedError
