# Sentinel — AI网络安全智能体 · 完整设计方案

> **代号：Sentinel（哨兵）**  
> 开源、自部署、纯防御型AI网络安全智能体  
> 任何人都可以下载，配置到自己的服务器/网站/应用中

---

## 一、产品定位

### 核心理念
"你资产的AI哨兵" — 部署后7×24小时自主值守，监控、检测、告警、取证，不做攻击。

### 硬约束
| 约束 | 说明 |
|------|------|
| 🔒 **禁止攻击能力** | 不提供任何渗透测试、漏洞利用、主动入侵功能 |
| 📸 **可取证** | 检测到攻击时自动收集证据（PCAP、日志快照、请求回放） |
| 📊 **有面板** | Web仪表盘实时展示安全态势 |
| 🎨 **高级UI** | Dark + Glassmorphism 风格，对标 Linear/Vercel 级别设计 |
| 🏠 **数据不出网** | 全本地部署，无遥测，用户完全掌控 |

### 与同类产品差异

| | Sentinel | 传统WAF | 传统IDS/IPS | SIEM |
|---|---|---|---|---|
| 部署 | 自部署，依附资产 | 网关/反向代理 | 旁路镜像 | 中心化日志 |
| 智能 | AI驱动，理解上下文 | 规则匹配 | 签名匹配 | 规则关联 |
| 交互 | QQ/飞书/Discord/Web | 仪表盘 | 仪表盘 | 仪表盘 |
| 取证 | 自动攻击证据包 | ❌ | 部分 | 日志 |
| 开源 | ✅ MIT | 部分 | 部分 | 极少 |
| 自带LLM | ✅ BYO-LLM | ❌ | ❌ | ❌ |

---

## 二、架构设计

```
                              ┌──────────────────────────┐
                              │     Download Website      │
                              │  sentinel.security        │
                              │  · 下载  · 教程  · 文档   │
                              └──────────────────────────┘
                                             │
┌────────────────────────────────────────────┼────────────────────────────────────────────┐
│                                    用户基础设施                                          │
│                                                                                         │
│  ┌──────────────────────────────────────────────────────────────────────────────────┐  │
│  │                          用户交互层                                                │  │
│  │  QQ │ 飞书 │ Discord │ Telegram │ Slack │ Web Dashboard │ CLI │ HTTP API         │  │
│  └───────────────────────────────┬──────────────────────────────────────────────────┘  │
│                                  │                                                      │
│  ┌───────────────────────────────▼──────────────────────────────────────────────────┐  │
│  │                         Gateway 网关层                                            │  │
│  │  · 多平台消息路由  · 权限控制  · 会话管理  · 告警分发                              │  │
│  └───────────────────────────────┬──────────────────────────────────────────────────┘  │
│                                  │                                                      │
│  ┌───────────────────────────────▼──────────────────────────────────────────────────┐  │
│  │                      Sentinel Core 核心引擎                                       │  │
│  │                                                                                   │  │
│  │  ┌─────────────┐  ┌─────────────┐  ┌──────────────┐  ┌───────────────────┐      │  │
│  │  │ LLM Router  │  │ Context Mgr │  │ Tool Dispatch│  │ Memory & Knowledge│      │  │
│  │  │ (模型路由)   │  │ (上下文管理) │  │ (工具调度)    │  │ (记忆+知识库)      │      │  │
│  │  └─────────────┘  └─────────────┘  └──────────────┘  └───────────────────┘      │  │
│  │                                                                                   │  │
│  │  ┌─────────────────────────────────────────────────────────────────────────┐    │  │
│  │  │                     Skill System (技能系统)                               │    │  │
│  │  │  · 内置安全技能  · 用户自定义技能  · 社区技能市场  · 自动经验学习           │    │  │
│  │  └─────────────────────────────────────────────────────────────────────────┘    │  │
│  └───────────────────────────────┬──────────────────────────────────────────────────┘  │
│                                  │                                                      │
│  ┌───────────────────────────────▼──────────────────────────────────────────────────┐  │
│  │                     Security Engine (安全引擎)                                     │  │
│  │                                                                                   │  │
│  │  ┌─────────────────────┐  ┌─────────────────────┐  ┌─────────────────────────┐  │  │
│  │  │  Traffic Analyzer   │  │  Log Analyzer       │  │  Asset Monitor          │  │  │
│  │  │  流量分析引擎        │  │  日志分析引擎        │  │  资产监控                │  │  │
│  │  │  · 异常流量检测      │  │  · 攻击模式识别      │  │  · 端口变化              │  │  │
│  │  │  · DDoS识别          │  │  · 暴力破解检测      │  │  · 服务状态              │  │  │
│  │  │  · 扫描行为识别      │  │  · 路径遍历检测      │  │  · SSL证书               │  │  │
│  │  │  · 数据泄露检测      │  │  · 权限提升检测      │  │  · 文件完整性            │  │  │
│  │  │  · 协议异常          │  │  · Webshell检测      │  │  · 进程异常              │  │  │
│  │  └─────────────────────┘  └─────────────────────┘  └─────────────────────────┘  │  │
│  │                                                                                   │  │
│  │  ┌─────────────────────┐  ┌─────────────────────┐  ┌─────────────────────────┐  │  │
│  │  │  Evidence Collector │  │  Threat Intel        │  │  Alert Engine           │  │  │
│  │  │  证据收集器          │  │  威胁情报            │  │  告警引擎                │  │  │
│  │  │  · PCAP抓包          │  │  · IP信誉            │  │  · 多平台推送            │  │  │
│  │  │  · 日志快照          │  │  · 域名信誉          │  │  · 告警分级              │  │  │
│  │  │  · 请求回放          │  │  · CVE匹配           │  │  · 自动封禁(可选)        │  │  │
│  │  │  · 攻击链重建        │  │  · 暗网监控          │  │  · 升级策略              │  │  │
│  │  └─────────────────────┘  └─────────────────────┘  └─────────────────────────┘  │  │
│  └───────────────────────────────┬──────────────────────────────────────────────────┘  │
│                                  │                                                      │
│  ┌───────────────────────────────▼──────────────────────────────────────────────────┐  │
│  │                       Plugin SDK (插件开发套件)                                    │  │
│  │  用户可自由扩展：自定义检测规则、新数据源、新告警渠道                                │  │
│  └───────────────────────────────┬──────────────────────────────────────────────────┘  │
│                                  │                                                      │
│  ┌───────────────────────────────▼──────────────────────────────────────────────────┐  │
│  │                    MCP Server (外部互操作)  +  REST API                            │  │
│  │  · Hermes调用  · 其他AI智能体调用  · CI/CD集成  · Webhook                          │  │
│  └──────────────────────────────────────────────────────────────────────────────────┘  │
│                                                                                         │
└─────────────────────────────────────────────────────────────────────────────────────────┘
```

### 技术栈

| 层 | 选型 | 理由 |
|---|---|---|
| 核心 | Python 3.11+ asyncio | 安全工具生态丰富，异步高性能 |
| LLM | LiteLLM Router | 支持100+模型提供商，用户自配Key |
| Gateway | aiohttp + FastAPI | 异步高性能，WebSocket支持 |
| Dashboard | Next.js + Tailwind + shadcn/ui | 高级UI，SSR可选 |
| 数据库 | SQLite (默认) / PostgreSQL | 轻量到企业级 |
| 流量分析 | 自研引擎 + Scapy/pyshark | 协议深度解析 |
| 消息队列 | Redis (可选) | 高吞吐场景 |
| 插件 | Python entry_points | 标准易扩展 |
| 打包 | PyPI + Docker + 一键脚本 | 多分发 |

---

## 三、安全能力矩阵（纯防御）

### A. 流量分析（核心能力）

| 能力 | 描述 | 检测方式 |
|---|---|---|
| **异常流量检测** | 基于基线的流量异常识别 | 统计模型 + AI分析 |
| **DDoS识别** | SYN Flood / UDP Flood / HTTP Flood | 速率基线偏离 |
| **扫描行为识别** | 端口扫描、目录扫描、参数Fuzz | 连接模式分析 |
| **数据泄露检测** | 异常外传数据量/目标 | 流量体积+目的地异常 |
| **协议异常** | HTTP走私、DNS隧道、ICMP隧道 | 协议合规检查 |
| **C2通信检测** | Beacon行为、心跳包、DNS查询模式 | 时间规律+熵分析 |
| **Web攻击识别** | SQLi/XSS/SSRF/命令注入等 | 载荷特征+上下文AI分析 |

### B. 日志分析

| 能力 | 描述 |
|---|---|
| **Web日志分析** | Nginx/Apache/Caddy访问日志和错误日志 |
| **系统日志分析** | auth.log / syslog / auditd |
| **应用日志分析** | 自定义应用日志（用户配置路径） |
| **攻击模式识别** | 多行日志关联，识别攻击链 |
| **暴力破解检测** | SSH/FTP/数据库登录失败模式 |
| **Webshell检测** | 异常文件访问模式 |
| **权限提升检测** | sudo滥用、su切换、capability变更 |

### C. 资产监控

| 能力 | 描述 |
|---|---|
| **端口变化检测** | 新开放端口即时告警 |
| **服务状态** | HTTP/数据库/缓存等服务可用性 |
| **SSL证书监控** | 过期预警、配置问题 |
| **文件完整性** | 关键文件（/etc、webroot）变更监控 |
| **进程监控** | 异常进程启动、CPU/内存异常 |
| **依赖漏洞** | 项目依赖中的已知CVE匹配 |
| **配置审计** | Nginx/Apache/Docker/K8s安全配置 |

### D. 威胁情报

| 能力 | 描述 |
|---|---|
| **IP信誉** | 对接开源威胁情报（AbuseIPDB等） |
| **域名信誉** | 检测钓鱼/恶意域名 |
| **CVE预警** | 新CVE自动匹配用户资产 |
| **GeoIP分析** | 流量来源地理异常 |

### E. 证据收集（取证能力）

| 能力 | 描述 |
|---|---|
| **流量快照** | 攻击时刻前后N秒PCAP抓取 |
| **日志快照** | 攻击相关日志上下文导出 |
| **请求回放** | 攻击请求完整保存（含Header/Body） |
| **攻击链重建** | 多事件关联还原攻击路径 |
| **证据包导出** | 一键导出结构化证据包（JSON+PCAP+日志） |
| **时间线生成** | 攻击时间线可视化 |

### F. 告警与响应

| 能力 | 描述 |
|---|---|
| **多平台告警** | QQ/飞书/Discord/Telegram/Slack/邮件 |
| **告警分级** | Info → Low → Medium → High → Critical |
| **自动封禁** | 确认攻击后自动iptables/fail2ban（可选，需用户授权） |
| **告警抑制** | 重复告警智能合并 |
| **升级策略** | 未处理告警自动升级通知 |

---

## 四、AI能力设计

### BYO-LLM 模型路由

```yaml
# ~/.sentinel/config.yaml
model:
  # 主模型（对话、分析、报告）
  primary:
    provider: openrouter
    model: anthropic/claude-sonnet-4
    api_key: ${LLM_API_KEY}
  
  # 快速模型（实时检测、简单分类）
  fast:
    provider: openai
    model: gpt-4o-mini
    api_key: ${FAST_LLM_KEY}
  
  # 本地模型（隐私敏感场景，可选）
  local:
    provider: ollama
    model: llama3.2
    base_url: http://localhost:11434
```

### AI在Sentinel中的角色

| 场景 | AI作用 |
|---|---|
| **流量异常判定** | 综合流量基线、时间、载荷特征做上下文判断（非规则匹配） |
| **攻击链还原** | 将分散的告警关联成完整攻击故事 |
| **误报过滤** | 学习用户环境正常行为模式，降低误报 |
| **报告生成** | 自然语言安全态势报告 |
| **对话交互** | 用户通过聊天平台查询/控制Sentinel |
| **证据分析** | 对收集的证据进行AI辅助分析 |

---

## 五、仪表盘设计（Web Dashboard）

### 设计语言

**风格**: Dark Luxury + Glassmorphism  
**参考**: Linear + Vercel + Sentry 的融合  
**配色**:

| Token | 值 | 用途 |
|---|---|---|
| `--bg-root` | `#010102` | 根背景 |
| `--bg-surface` | `#0a0a0f` | 卡片/面板背景 |
| `--bg-elevated` | `#12121a` | 悬浮层 |
| `--accent-primary` | `#3b82f6` | 主强调色（极度克制使用） |
| `--accent-danger` | `#ef4444` | 危险/告警 |
| `--accent-warning` | `#f59e0b` | 警告 |
| `--accent-success` | `#22c55e` | 正常 |
| `--text-primary` | `#f1f5f9` | 主文字 |
| `--text-secondary` | `#94a3b8` | 次要文字 |
| `--text-muted` | `#475569` | 弱化文字 |
| `--border-subtle` | `#1e293b` | 边框 |
| `--glass-bg` | `rgba(255,255,255,0.03)` | 玻璃效果背景 |
| `--glass-border` | `rgba(255,255,255,0.06)` | 玻璃效果边框 |
| `--glass-blur` | `12px` | 玻璃模糊 |

### 页面结构

```
Dashboard
├── 顶部导航栏
│   ├── Sentinel Logo + 版本
│   ├── 全局状态指示灯 (🟢 正常 / 🟡 注意 / 🔴 告警)
│   ├── 资产数量 / 今日告警 / 运行时间
│   └── 设置按钮
│
├── 左侧边栏
│   ├── 📊 总览 (Dashboard)
│   ├── 🔍 告警中心
│   │   ├── 全部告警
│   │   ├── 未处理
│   │   └── 已处理
│   ├── 🌐 流量分析
│   │   ├── 实时流量
│   │   └── 历史趋势
│   ├── 📋 日志分析
│   ├── 🏗 资产管理
│   ├── 📸 证据库
│   ├── 🛡 威胁情报
│   ├── ⚙️ 设置
│   └── 📖 帮助
│
├── 主内容区 (Dashboard首页)
│   ├── [卡片] 安全评分 (大数字 + 趋势线)
│   ├── [卡片] 24h告警趋势 (迷你图表)
│   ├── [卡片] 流量异常事件 (实时列表)
│   ├── [卡片] 最新告警 (5条高优先级)
│   ├── [卡片] 资产健康度 (状态网格)
│   ├── [卡片] 攻击来源Top5 (GeoIP地图或列表)
│   └── [卡片] 最近证据包
│
└── 底部状态栏
    ├── LLM状态 + Token用量
    ├── 上次扫描时间
    └── Sentinel uptime
```

### 告警详情页

```
┌─────────────────────────────────────────────┐
│ ← 返回告警列表                              │
│                                              │
│ 🔴 CRITICAL · SQL注入尝试                    │
│ 2026-05-15 14:32:18 · 来源: 45.33.32.156   │
│                                              │
│ ┌─ 攻击详情 ──────────────────────────────┐ │
│ │ 目标: https://api.example.com/search     │ │
│ │ 载荷: ' UNION SELECT ...                │ │
│ │ 来源IP: 45.33.32.156 (US/CA)            │ │
│ │ 威胁情报: 该IP已被标记为恶意             │ │
│ └──────────────────────────────────────────┘ │
│                                              │
│ ┌─ AI分析 ────────────────────────────────┐ │
│ │ 这是一个典型的SQL注入探测。攻击者使用     │ │
│ │ UNION查询试图提取数据库表结构。           │ │
│ │ 该请求已被WAF拦截，未造成数据泄露。       │ │
│ │ 建议：监控该IP后续行为，暂时无需封禁。    │ │
│ └──────────────────────────────────────────┘ │
│                                              │
│ ┌─ 证据包 ────────────────────────────────┐ │
│ │ 📦 attack_20260515_143218.tar.gz        │ │
│ │ 包含: request.log / traffic.pcap / ...  │ │
│ │ [下载证据包] [查看攻击链]               │ │
│ └──────────────────────────────────────────┘ │
│                                              │
│ [标记为已处理] [加入观察列表] [封禁IP]     │
└─────────────────────────────────────────────┘
```

---

## 六、下载站设计（sentinel.security）

### 页面结构

```
sentinel.security
├── Hero Section
│   ├── "你的AI安全哨兵" — 大标题
│   ├── 一句话描述
│   ├── [立即下载] [查看文档]
│   └── 动态终端演示动画
│
├── Feature Grid
│   ├── 🛡 纯防御智能体
│   ├── 🧠 自带AI大脑
│   ├── 📸 自动攻击取证
│   ├── 🌐 实时流量分析
│   ├── 💬 多平台告警
│   └── 🔌 一键集成
│
├── Architecture Diagram
│   └── 交互式架构图（SVG动画）
│
├── Dashboard Preview
│   └── 仪表盘截图轮播
│
├── Comparison Table
│   └── Sentinel vs WAF vs IDS vs SIEM
│
├── Quick Start
│   ├── curl -fsSL https://sentinel.security/install.sh | bash
│   └── 一键复制
│
├── Testimonials (社区)
│
└── Footer
    ├── GitHub ★
    ├── Discord社区
    └── 文档链接
```

### 设计风格

**参考**: Linear + Vercel 下载页风格
- 深色背景 + 极克制的蓝色点缀
- Geist / Inter 字体
- 大量留白
- 精确的间距节奏
- 微妙的玻璃效果卡片
- 无侵入动画

---

## 七、与Hermes的集成

### 方式一：MCP Server（主力）

```bash
# Sentinel以MCP Server运行
sentinel mcp serve --port 9090

# Hermes配置中添加
hermes mcp add sentinel --command "sentinel mcp serve"
```

Hermes可直接调用：
- `sentinel.scan_traffic` — 分析流量
- `sentinel.check_alerts` — 查看告警
- `sentinel.get_evidence` — 获取证据包
- `sentinel.asset_status` — 资产状态
- `sentinel.threat_lookup` — 威胁情报查询

### 方式二：Skill模式

```bash
hermes skills install sentinel
hermes -s sentinel
```

Sentinel安全能力注入Hermes上下文。

### 方式三：Webhook双向联动

```
Sentinel发现威胁 → Webhook → Hermes (通知+建议)
Hermes收到指令 → Webhook → Sentinel (执行动作)
```

---

## 八、配置体系

### 最小配置

```yaml
# ~/.sentinel/config.yaml
version: 1

model:
  provider: openrouter
  model: anthropic/claude-sonnet-4
  api_key: ${SENTINEL_LLM_KEY}

gateway:
  platforms:
    - qqbot
    - web_dashboard

assets:
  - name: "主Web服务器"
    host: 192.168.1.100
    type: web_server

security:
  traffic_analysis: true
  log_analysis: true
  auto_evidence: true
```

### 完整配置

```yaml
version: 1

# === LLM配置 ===
model:
  primary:
    provider: openrouter       # openrouter | openai | anthropic | deepseek | ollama | custom
    model: anthropic/claude-sonnet-4
    api_key: ${SENTINEL_LLM_KEY}
  fast:
    provider: openai
    model: gpt-4o-mini
    api_key: ${FAST_LLM_KEY}

# === 网关配置 ===
gateway:
  web_dashboard:
    enabled: true
    port: 8443
    auth: true
  platforms:
    qqbot:
      enabled: true
    feishu:
      enabled: false
      webhook_url: ""
    discord:
      enabled: false
      bot_token: ""
    telegram:
      enabled: false
      bot_token: ""
    slack:
      enabled: false

# === 资产清单 ===
assets:
  - name: "生产Web服务器"
    host: 192.168.1.100
    type: web_server
    ports: [80, 443]
    log_paths:
      - /var/log/nginx/access.log
      - /var/log/nginx/error.log
  - name: "API服务"
    host: 192.168.1.101
    type: api_server
    ports: [8080]
  - name: "数据库服务器"
    host: 10.0.0.50
    type: database
    ports: [3306]

# === 安全策略 ===
security:
  traffic_analysis:
    enabled: true
    interfaces: [eth0]
    capture_size: 65535
    bpf_filter: ""            # 留空=全部流量
  
  log_analysis:
    enabled: true
    paths:
      - /var/log/auth.log
      - /var/log/syslog
    custom_patterns: []        # 自定义正则
  
  asset_monitoring:
    port_scan_interval: 3600
    file_integrity_paths:
      - /etc
      - /var/www
  
  evidence_collection:
    enabled: true
    capture_duration: 60       # 攻击前后各30秒
    storage_path: ~/.sentinel/evidence
    retention_days: 90
  
  threat_intel:
    abuseipdb_key: ${ABUSEIPDB_KEY}
    virus_total_key: ${VIRUSTOTAL_KEY}
  
  alerting:
    default_level: medium
    auto_block: false          # 自动封禁需手动开启
    block_duration: 3600
    merge_window: 300          # 5分钟内同类告警合并

# === 集成 ===
integrations:
  hermes:
    mode: mcp_server           # mcp_server | skill | webhook
    port: 9090
  webhooks:
    - name: "自建SIEM"
      url: "https://siem.internal/webhook"
      events: [alert, evidence]
  siem:
    type: none                 # none | elastic | splunk | wazuh| custom

# === 高级 ===
advanced:
  db_path: ~/.sentinel/sentinel.db
  log_level: info
  plugin_dir: ~/.sentinel/plugins
```

---

## 九、使用教程

### 安装

```bash
# 方式一：一键脚本（推荐）
curl -fsSL https://sentinel.security/install.sh | bash

# 方式二：pip
pip install sentinel-security
sentinel setup

# 方式三：Docker
docker pull nousresearch/sentinel:latest
mkdir -p ~/.sentinel
docker run -d \
  --name sentinel \
  --network host \
  -v ~/.sentinel:/root/.sentinel \
  -v /var/log:/var/log:ro \
  nousresearch/sentinel:latest
```

### 初始化向导

```
$ sentinel setup

  ╔══════════════════════════════════════╗
  ║     Sentinel 初始化向导              ║
  ╚══════════════════════════════════════╝

  1️⃣  AI模型配置
  ─────────────────────────────────
  提供商 [openrouter]: 
  模型 [anthropic/claude-sonnet-4]: 
  API Key (输入后不显示): ********

  2️⃣  网关配置
  ─────────────────────────────────
  Web控制面板 [Y/n]: y
  控制面板端口 [8443]: 
  QQ通知 [Y/n]: y
  飞书通知 [y/N]: n

  3️⃣  资产注册
  ─────────────────────────────────
  资产名称: 生产Web服务器
  地址: 192.168.1.100
  类型 [web_server]: 

  添加更多资产? [y/N]: n

  4️⃣  安全策略
  ─────────────────────────────────
  启用流量分析 [Y/n]: y
  监听网卡 [eth0]: 
  启用日志分析 [Y/n]: y
  自动收集证据 [Y/n]: y
  自动封禁攻击IP [y/N]: n

  ✅ 配置已保存到 ~/.sentinel/config.yaml
  ✅ Sentinel 启动中...
  
  ┌─────────────────────────────────────┐
  │ 控制面板: https://你的IP:8443        │
  │ 默认账号: admin                      │
  │ 默认密码: (随机生成，请记录)          │
  │                                      │
  │ 在QQ/飞书中 @Sentinel 开始对话       │
  └─────────────────────────────────────┘
```

### 日常使用

**对话交互示例（QQ/飞书）**:

```
用户: @sentinel 现在安全状况怎么样

Sentinel:
📊 安全态势总览 (2026-05-15 14:00)

🟢 安全评分: 92/100

━━━━ 资产状态 ━━━━
🟢 生产Web服务器 — 正常
🟢 API服务 — 正常  
🟡 数据库服务器 — 端口开放检查需注意

━━━━ 24h 告警统计 ━━━━
🔴 Critical: 1
🟡 Medium: 3
🔵 Info: 12

━━━━ 最近告警 ━━━━
🔴 14:32 | SQL注入尝试 — 来源45.33.32.156
🟡 12:15 | SSH暴力破解 — 已自动封禁
🟡 08:42 | 异常端口扫描 — 已记录

需要查看详情或处理建议吗？
```

```
用户: @sentinel 处理那个SQL注入告警

Sentinel:
🔍 正在收集证据...

📸 证据包已生成
━━━━━━━━━━━━━━━━━━
攻击IP: 45.33.32.156 (DigitalOcean, US)
攻击目标: GET /search?q=' UNION SELECT...
攻击时间: 2026-05-15 14:32:18
攻击结果: 请求被应用层防火墙拦截，未成功

🤖 AI分析:
该IP在24小时内对多个端点进行了SQL注入探测。
威胁情报显示该IP属于已知扫描器。
建议: 封禁该IP 24小时。

证据包: evidence/attack_20260515_143218.tar.gz
  ├── request_raw.txt (完整HTTP请求)
  ├── traffic_60s.pcap (前后60秒流量)
  ├── attack_chain.json (攻击链)
  └── threat_intel.json (威胁情报)

[封禁IP] [加入黑名单] [导出报告]
```

### CLI命令

```bash
sentinel start          # 启动
sentinel stop           # 停止
sentinel status         # 查看状态
sentinel setup          # 初始化向导
sentinel config edit    # 编辑配置

sentinel alert list     # 告警列表
sentinel alert show ID  # 告警详情
sentinel alert resolve ID  # 标记已处理

sentinel evidence list  # 证据列表
sentinel evidence show ID  # 证据详情
sentinel evidence export ID  # 导出证据包

sentinel traffic live   # 实时流量监控
sentinel traffic report # 流量报告

sentinel report daily   # 日报
sentinel report weekly  # 周报

sentinel plugin list    # 插件列表
sentinel plugin install NAME  # 安装插件

sentinel mcp serve      # 启动MCP Server
```

---

## 十、项目结构

```
sentinel/
├── sentinel_core/
│   ├── __init__.py
│   ├── engine.py            # 核心AI引擎
│   ├── llm_router.py        # LLM路由
│   ├── context.py           # 上下文管理
│   ├── memory.py            # 持久化记忆
│   └── skill_system.py      # 技能系统
│
├── sentinel_gateway/
│   ├── __init__.py
│   ├── gateway.py
│   └── platforms/
│       ├── qqbot.py
│       ├── feishu.py
│       ├── discord.py
│       ├── telegram.py
│       └── slack.py
│
├── sentinel_security/       # 安全引擎
│   ├── __init__.py
│   ├── traffic/
│   │   ├── analyzer.py      # 流量分析主引擎
│   │   ├── capture.py       # 抓包
│   │   ├── detector.py      # 异常检测
│   │   └── signatures/      # 检测签名
│   │       ├── web_attacks.py
│   │       ├── ddos.py
│   │       ├── scan.py
│   │       └── exfil.py
│   ├── log/
│   │   ├── analyzer.py
│   │   ├── parser.py
│   │   └── patterns/
│   ├── asset/
│   │   ├── monitor.py
│   │   ├── port_scanner.py
│   │   └── file_integrity.py
│   ├── evidence/
│   │   ├── collector.py
│   │   ├── packager.py
│   │   └── timeline.py
│   ├── threat_intel/
│   │   ├── ip_reputation.py
│   │   ├── cve_matcher.py
│   │   └── feeds.py
│   └── alerting/
│       ├── engine.py
│       ├── router.py
│       └── auto_block.py
│
├── sentinel_dashboard/      # Web控制面板
│   ├── pages/
│   │   ├── index.tsx
│   │   ├── alerts.tsx
│   │   ├── traffic.tsx
│   │   ├── assets.tsx
│   │   ├── evidence.tsx
│   │   └── settings.tsx
│   ├── components/
│   │   ├── Layout.tsx
│   │   ├── Sidebar.tsx
│   │   ├── StatusBadge.tsx
│   │   ├── AlertCard.tsx
│   │   ├── TrafficChart.tsx
│   │   ├── GlassPanel.tsx
│   │   └── ...
│   ├── styles/
│   └── api/
│
├── sentinel_mcp/
│   ├── __init__.py
│   └── server.py
│
├── sentinel_cli/
│   ├── __init__.py
│   └── commands/
│
├── plugins/                 # 内置插件
│   └── example/
│       ├── plugin.yaml
│       └── main.py
│
├── download_site/           # 下载站源码
│   ├── index.html
│   ├── docs/
│   └── assets/
│
├── tests/
├── docs/
├── scripts/
│   ├── install.sh
│   └── install.ps1
├── Dockerfile
├── docker-compose.yml
├── pyproject.toml
├── LICENSE (MIT)
├── README.md
└── DESIGN.md                # 本文件
```

---

## 十一、开发路线图

### Phase 1: MVP（核心可用）
- [x] 设计方案完成
- [ ] 项目骨架搭建
- [ ] LLM路由层（5+提供商）
- [ ] Gateway基础（QQ + Web Dashboard）
- [ ] 流量分析引擎（基本协议解析+异常检测）
- [ ] 日志分析引擎（auth.log + nginx）
- [ ] 基础告警系统
- [ ] 一键安装脚本
- [ ] 下载站上线
- **目标：能装、能对话、能检测、能告警**

### Phase 2: 完善
- [ ] 证据收集系统
- [ ] 威胁情报集成
- [ ] 资产监控完善
- [ ] 多平台支持（飞书/Discord/Telegram）
- [ ] MCP Server
- [ ] Dashboard完善
- [ ] 使用教程完善
- **目标：完整的安全智能体**

### Phase 3: 生态
- [ ] 插件SDK
- [ ] Hermes Skill模式
- [ ] 社区插件市场
- [ ] CI/CD集成
- **目标：形成生态**

---

## 十二、关键决策及理由

1. **Python** — 安全工具链生态最完善，Scapy/pyshark/paramiko等直接可用
2. **自研流量引擎** — 不依赖Suricata/Snort，保持轻量和可控
3. **SQLite默认** — 零依赖启动，用户需要时可切PostgreSQL
4. **Next.js Dashboard** — 对标Linear/Vercel的UI品质
5. **独立项目** — 目标用户是安全工程师，与Hermes互补但独立品牌
6. **MIT协议** — 最大化用户信任和采用
7. **禁攻击** — 法律风险为零，专注防御市场
