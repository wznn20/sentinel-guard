# ============================================================
# KX Agent — local-first orchestration runtime
# Docker 多架构镜像 (amd64 + arm64)
# ============================================================

FROM python:3.12-slim AS base

LABEL org.opencontainers.image.title="KX Agent"
LABEL org.opencontainers.image.description="Local-first orchestration runtime with memory and approvals"
LABEL org.opencontainers.image.url="https://github.com/wznn20/sentinel-guard"
LABEL org.opencontainers.image.licenses="Apache-2.0"

# 系统依赖
RUN apt-get update -qq && apt-get install -y -qq --no-install-recommends \
    libpcap-dev \
    tcpdump \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# 创建 kx 用户
RUN useradd -m -s /bin/bash kx && \
    mkdir -p /home/kx/.kx/{logs,skills,config} && \
    chown -R kx:kx /home/kx/.kx

WORKDIR /app

# 安装 KX Agent
COPY pyproject.toml README.md ./
COPY sentinel_core/ ./sentinel_core/
COPY sentinel_security/ ./sentinel_security/
COPY sentinel_gateway/ ./sentinel_gateway/
COPY sentinel_cli/ ./sentinel_cli/
COPY sentinel_mcp/ ./sentinel_mcp/
COPY kx_agent/ ./kx_agent/

RUN pip install --no-cache-dir -e . && \
    chown -R kx:kx /app

USER kx

# 暴露端口
# 8899: Dashboard
# 8787: Gateway / app server
EXPOSE 8899 8787

VOLUME ["/home/kx/.kx/config", "/home/kx/.kx/skills"]

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD kx status --json || exit 1

ENTRYPOINT ["kx"]
CMD ["app", "--host", "0.0.0.0", "--port", "8787"]
