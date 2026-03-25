# CortexCrawl

数据采集流水线，监控众筹和产品发现平台，自动同步到飞书多维表格并发送机器人通知。

## 工作流

| 工作流 | 数据源 | 筛选条件 | 触发时间 (UTC) |
|--------|--------|---------|---------------|
| **kickstarter-workflow** | Kickstarter | 金额 ≥ $500K，2026-01-01 后 | 每日 00:00 |
| **producthunt-workflow** | Product Hunt | 投票数 ≥ 100，最近 30 天 | 每日 08:00 |

## 数据流

```
GraphQL APIs (Kickstarter / Product Hunt)
    → OpenClaw Skill (JS) — 每日定时 / webhook 触发
    → Raw JSON (/data/*/raw_*.json)
    → Python 工作流 (src/main.py) — 去重 + diff
    → 飞书多维表格 + 机器人通知
```

## 快速开始

```bash
cd kickstarter-workflow  # 或 producthunt-workflow
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env     # 填入飞书凭证

# 增量运行 (使用已有数据文件)
python src/main.py

# 全量同步 (首次部署 / 补数据)
python src/main.py --full

# 测试模式 (不写入飞书)
python src/main.py --test
```

## 远程触发

```bash
# SSH 到服务器后手动执行
ssh root@47.254.73.23

# 全量同步 (抓取 → diff → 入库 → 通知)
cd /opt/cortexcrawl/kickstarter-workflow && ./run-full-sync.sh
cd /opt/cortexcrawl/producthunt-workflow && ./run-full-sync.sh

# 仅看 diff，不写入
./run-full-sync.sh --test
```

## 项目结构

```
CortexCrawl/
├── kickstarter-workflow/          # Kickstarter 工作流
│   ├── openclaw/                  # OpenClaw JS 抓取脚本
│   │   ├── skill-config.yaml
│   │   └── fetch-kickstarter.js
│   ├── src/                       # Python 处理逻辑
│   │   ├── config.py              # 配置 + 字段映射
│   │   ├── data_processor.py      # 去重 + diff 逻辑
│   │   ├── feishu_client.py       # 飞书 API 客户端
│   │   └── main.py                # 入口
│   ├── run-full-sync.sh           # 全量同步脚本
│   └── requirements.txt
├── producthunt-workflow/          # Product Hunt 工作流 (同构)
├── scripts/
│   └── sync_deployment_to_feishu.py  # DEPLOYMENT.md → 飞书文档同步
├── DEPLOYMENT.md                  # 完整部署手册
└── CLAUDE.md                      # Claude Code 指引
```

## 文档

- **[DEPLOYMENT.md](DEPLOYMENT.md)** — 完整部署手册 (飞书平台配置、服务器部署、定时任务、故障排查)
- **[飞书在线版](https://my.feishu.cn/wiki/SYnfwn6ZDiv8xmka7ttcTmbvnMb)** — DEPLOYMENT.md 自动同步到飞书云文档

## 部署

- 服务器: 阿里云 ECS `47.254.73.23` (Alibaba Cloud Linux 3)
- OpenClaw: Node.js 直接运行 `:15970` (WebSocket 网关，非 Docker)
- Python: 需 3.9+，服务器用 `python3.11`
- 详见 [DEPLOYMENT.md](DEPLOYMENT.md)
