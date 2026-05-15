# ============================================================
# Sentinel — AI网络安全智能体
# Docker 多架构镜像 (amd64 + arm64)
# ============================================================

FROM python:3.12-slim AS base

LABEL org.opencontainers.image.title="Sentinel Security Agent"
LABEL org.opencontainers.image.description="AI网络安全智能体 — 纯防御型"
LABEL org.opencontainers.image.url="https://sentinel.security"
LABEL org.opencontainers.image.licenses="Apache-2.0"

# 系统依赖
RUN apt-get update -qq && apt-get install -y -qq --no-install-recommends \
    libpcap-dev \
    tcpdump \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# 创建 sentinel 用户
RUN useradd -m -s /bin/bash sentinel && \
    mkdir -p /home/sentinel/.sentinel/{logs,evidence,plugins,config} && \
    chown -R sentinel:sentinel /home/sentinel/.sentinel

WORKDIR /app

# 安装 Sentinel
COPY pyproject.toml README.md ./
COPY sentinel_core/ ./sentinel_core/
COPY sentinel_security/ ./sentinel_security/
COPY sentinel_gateway/ ./sentinel_gateway/
COPY sentinel_cli/ ./sentinel_cli/
COPY sentinel_mcp/ ./sentinel_mcp/

RUN pip install --no-cache-dir -e . && \
    chown -R sentinel:sentinel /app

USER sentinel

# 暴露端口
# 8443: Web Dashboard
# 9090: MCP Server
# 8080: Gateway API
EXPOSE 8443 9090 8080

VOLUME ["/home/sentinel/.sentinel/config", "/home/sentinel/.sentinel/evidence"]

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD sentinel status --json || exit 1

ENTRYPOINT ["sentinel"]
CMD ["start", "--daemon"]
