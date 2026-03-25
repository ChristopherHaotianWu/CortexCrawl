# CortexCrawl — 完整部署手册

两个工作流共享同一台服务器和飞书应用体系，本文档按"先共享基础设施，再各工作流"的顺序部署，最后统一验证。

---

## 目录

1. [基础设施概览](#1-基础设施概览)
2. [飞书平台配置（共享）](#2-飞书平台配置共享)
3. [服务器环境准备](#3-服务器环境准备)
4. [部署 Kickstarter 工作流](#4-部署-kickstarter-工作流)
5. [部署 Product Hunt 工作流](#5-部署-product-hunt-工作流)
6. [定时任务配置](#6-定时任务配置)
   - 6.1 [全量同步（首次部署 / 手动补数据）](#61-全量同步-首次部署或手动补数据)
7. [部署验证](#7-部署验证)
8. [运维速查](#8-运维速查)

---

## 1. 基础设施概览

```
┌──────────────────────────────────────────────────────────────────┐
│                   阿里云 ECS  47.254.73.23                        │
│                                                                  │
│  ┌──────────────────────┐    ┌──────────────────────────────┐    │
│  │  OpenClaw :15970     │    │     Python 工作流             │    │
│  │  (WebSocket 网关)     │    │                              │    │
│  │                      │    │  fetch-*.js (增量/全量)       │    │
│  │  聊天指令触发          │    │    ↓ raw JSON               │    │
│  │  或 cron 定时          │───▶│  src/main.py (diff + 同步)   │    │
│  │                      │    │                              │    │
│  │                      │    │  run-full-sync.sh            │    │
│  │                      │    │    ↓ fetch --full            │    │
│  │                      │    │    ↓ diff + 同步             │    │
│  └──────────────────────┘    └──────────────────────────────┘    │
│                                          │                       │
│                                          ▼                       │
│                              ┌──────────────────────┐            │
│                              │  飞书多维表格 + 机器人  │            │
│                              └──────────────────────┘            │
└──────────────────────────────────────────────────────────────────┘
```

### 两种运行模式

| 模式 | 触发方式 | 数据范围 | 适用场景 |
|------|---------|---------|---------|
| **增量** (默认) | 每日定时 cron | 有筛选条件，最多 10-20 页 | 日常运行 |
| **全量** | 手动 CLI `--full` / `run-full-sync.sh` | 无筛选条件，最多 50 页 | 首次部署、补数据 |

### 增量模式筛选条件

| 工作流 | 触发时间（UTC） | 北京时间 | 数据筛选条件 |
|--------|--------------|---------|------------|
| Kickstarter | 00:00 | 08:00 | 金额 ≥ $500K，2026-01-01 后发布 |
| Product Hunt | 08:00 | 16:00 | 投票数 ≥ 100，最近 30 天内 |

### 全量模式触发命令

```bash
# 在服务器上执行全量同步
ssh root@47.254.73.23

# Kickstarter 全量同步
cd /opt/cortexcrawl/kickstarter-workflow && ./run-full-sync.sh

# Product Hunt 全量同步
cd /opt/cortexcrawl/producthunt-workflow && ./run-full-sync.sh

# 仅看 diff，不写入飞书
./run-full-sync.sh --test
```

> **注意**: OpenClaw 运行在端口 15970 (WebSocket 网关)，不提供 REST API webhook。数据抓取通过 cron 或手动 CLI 触发。

---

## 2. 飞书平台配置（共享）

两个工作流**各自需要独立的飞书应用和多维表格**，但操作步骤相同。

### 2.1 创建飞书应用

> 重复以下步骤两次，分别创建两个应用。

1. 访问 [飞书开发者后台](https://open.feishu.cn/app)，使用企业管理员账号登录
2. 点击「创建企业自建应用」，填写：

   | | Kickstarter | Product Hunt |
   |-|-------------|--------------|
   | 应用名称 | `Kickstarter Monitor` | `Product Hunt Monitor` |

3. 创建后进入「凭证与基础信息」，记录：
   ```
   App ID:     cli_xxxxxxxxxx
   App Secret: xxxxxxxxxxxxxxxx   ← 只显示一次，立即保存
   ```

### 2.2 开通 API 权限

两个应用均需开通相同权限。进入「开发者后台」→ 对应应用 →「权限管理」→ 搜索并勾选以下权限：

| 权限代码 | 说明 | 用途 |
|---------|------|------|
| `bitable:app` | 查看、评论、编辑和管理多维表格 | **必须** — 覆盖多维表格所有读写操作 |
| `bitable:app:readonly` | 查看多维表格 | 备选（如只需只读权限） |

> **说明**：`bitable:app` 是组合权限，已包含 `bitable:base:read`、`bitable:record:read/write`、`bitable:table:read` 等细粒度权限。只需开通这一个即可。
>
> 如果你的飞书版本支持细粒度权限控制，也可以只开通以下最小集合：

<details>
<summary>细粒度权限列表（点击展开）</summary>

| 权限代码 | 说明 |
|---------|------|
| `bitable:base:read` | 读取多维表格基础信息 |
| `bitable:record:read` | 读取记录 |
| `bitable:record:write` | 新增 / 编辑记录 |
| `bitable:table:read` | 读取表格字段信息 |

</details>

添加后提交审核，等待管理员审批通过。发布应用后权限才会生效。

### 2.3 飞书 API 接口说明

项目使用的飞书多维表格 API 端点 ([官方文档](https://open.feishu.cn/document/server-docs/docs/bitable-v1/bitable-overview))：

| 接口 | 方法 | 路径 | 限制 |
|------|------|------|------|
| 获取 Token | POST | `/auth/v3/tenant_access_token/internal` | 有效期 2 小时 |
| 列出记录 | GET | `/bitable/v1/apps/:app_token/tables/:table_id/records` | page_size 上限 500，频率 20 次/秒 |
| 批量新增 | POST | `/bitable/v1/apps/:app_token/tables/:table_id/records/batch_create` | **单次上限 500 条**，频率 50 次/秒 |
| 批量更新 | POST | `/bitable/v1/apps/:app_token/tables/:table_id/records/batch_update` | **单次上限 500 条**，频率 50 次/秒 |

**字段值格式要求**：

| 飞书字段类型 | 传值格式 | 示例 |
|-------------|---------|------|
| 文本 | 字符串 | `"产品名称"` |
| 数字 | 数字 | `500000` |
| 日期 | **毫秒时间戳** | `1740787200000` (= 2025-03-01 00:00:00) |
| 超链接 | `{"text": "显示文本", "link": "URL"}` | `{"text": "产品A", "link": "https://..."}` |

> **注意**：日期字段不能传 ISO 字符串，必须传毫秒时间戳，否则写入失败。代码中 `_date_to_timestamp_ms()` 已自动处理转换。

**并发写入注意事项**：

- 同一数据表并发调用写入接口会出现冲突 (错误码 `1254291`)
- 代码中已内置冲突重试 (最多 3 次) 和批次间 1 秒延迟

### 2.4 创建多维表格

**Kickstarter 表格**（命名：`Kickstarter 监控`）：

| 序号 | 字段名 | 类型 | 代码传值格式 |
|-----|-------|------|------------|
| 1 | 产品名 | 文本 | 字符串 |
| 2 | 国家 | 文本 | 字符串 |
| 3 | 公司 | 文本 | 字符串 |
| 4 | 标签 | 文本 | 字符串 |
| 5 | 产品说明 | 文本 | 字符串 |
| 6 | 众筹金额/美金 | **数字** | 数字 |
| 7 | 众筹人数 | **数字** | 数字 |
| 8 | 众筹开始时间 | **日期** | **毫秒时间戳** (如 `1740787200000`) |
| 9 | 创始人 | 文本 | 字符串 |
| 10 | 项目链接 | **超链接** | `{"text": "产品名", "link": "URL"}` |
| 11 | 履历 | 文本 | 字符串 |
| 12 | 融资历史 | 文本 | 字符串 |

**Product Hunt 表格**（命名：`Product Hunt 监控`）：

| 序号 | 字段名 | 类型 | 代码传值格式 |
|-----|-------|------|------------|
| 1 | 产品名 | 文本 | 字符串 |
| 2 | 标语 | 文本 | 字符串 |
| 3 | 产品说明 | 文本 | 字符串 |
| 4 | 投票数 | **数字** | 数字 |
| 5 | 评论数 | **数字** | 数字 |
| 6 | 发布日期 | **日期** | **毫秒时间戳** (如 `1740787200000`) |
| 7 | 制作者 | 文本 | 字符串 |
| 8 | 话题标签 | 文本 | 字符串 |
| 9 | 产品链接 | **超链接** | `{"text": "产品名", "link": "URL"}` |
| 10 | 产品图片 | 文本 | 字符串 |
| 11 | 履历 | 文本 | 字符串 |
| 12 | 融资历史 | 文本 | 字符串 |

> **重要**：
> - 字段名称和类型必须与上表完全一致，否则写入时会报 `field type mismatch` (错误码 `1254015`)
> - 日期字段必须传毫秒时间戳，不能传 ISO 字符串。代码中 `_date_to_timestamp_ms()` 已自动转换
> - 超链接字段必须传 `{"text": ..., "link": ...}` 对象

从表格 URL 获取 ID：
```
https://www.feishu.cn/base/BAsexxxxxxxxxxxxxxxxxxx?table=tblxxxxxxxxxxxxxxxxxxx
                             └────── base_id ──────┘       └──── table_id ────┘
```

### 2.5 创建群机器人（可选）

两个工作流各配一个机器人：

1. 目标群聊 → 群设置 → 群机器人 → 添加机器人 → 自定义机器人
2. 分别命名为 `Kickstarter 监控助手` 和 `Product Hunt 监控助手`
3. 保存各自的 Webhook URL

---

## 3. 服务器环境准备

### 服务器信息

| 项目 | 值 |
|------|------|
| 系统 | Alibaba Cloud Linux 3 (RHEL 8 兼容) |
| IP | 47.254.73.23 |
| OpenClaw | Node.js 直接运行 (`/opt/openclaw/dist/index.js`)，非 Docker |
| Python | 需要 3.9+，系统自带 3.6.8 不满足要求 |

### 3.1 安装 Python 3.11（系统自带 3.6 太旧）

```bash
ssh root@47.254.73.23

# 安装编译依赖
yum install -y gcc openssl-devel bzip2-devel libffi-devel zlib-devel

# 下载并编译 Python 3.11（altinstall 不覆盖系统 python3）
cd /tmp
curl -O https://www.python.org/ftp/python/3.11.9/Python-3.11.9.tgz
tar xzf Python-3.11.9.tgz
cd Python-3.11.9
./configure --enable-optimizations --prefix=/usr/local
make -j$(nproc)
make altinstall

# 验证
python3.11 --version   # Python 3.11.9
```

### 3.2 确认 OpenClaw 运行

```bash
# OpenClaw 以 Node.js 进程运行（非 Docker）
ps aux | grep openclaw
# 预期: /usr/bin/node /opt/openclaw/dist/index.js gateway

# 确认端口
curl -s http://localhost:15970/health
```

### 3.3 创建目录和拉取代码

```bash
# 创建数据目录
mkdir -p /data/kickstarter /data/producthunt

# 拉取代码（首次）
git clone https://github.com/ChristopherHaotianWu/CortexCrawl.git /opt/cortexcrawl
```

---

## 4. 部署 Kickstarter 工作流

### 4.1 部署代码和脚本

代码通过 git 部署到服务器：

```bash
# 在服务器上拉取最新代码（首次部署用 clone，后续用 pull）
ssh root@47.254.73.23
cd /opt/cortexcrawl && git pull

# 确保全量同步脚本可执行
chmod +x /opt/cortexcrawl/kickstarter-workflow/run-full-sync.sh
```

### 4.2 安装 Python 依赖

```bash
cd /opt/cortexcrawl/kickstarter-workflow

python3.11 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

### 4.3 配置环境变量

```bash
cp .env.example .env
nano .env
```

```env
FEISHU_APP_ID=cli_xxxxxxxxxxxxxxxx          # Kickstarter 应用的 ID
FEISHU_APP_SECRET=xxxxxxxxxxxxxxxxxxxxxxxx
FEISHU_BASE_ID=BAsexxxxxxxxxxxxxxxxxxx
FEISHU_TABLE_ID=tblxxxxxxxxxxxxxxxxxxx
FEISHU_WEBHOOK_URL=https://open.feishu.cn/open-apis/bot/v2/hook/...  # 可选

OPENCLAW_BASE_URL=http://localhost:15970
OPENCLAW_TOKEN=d171c5fce114f7c6a1c13f5ac424b3c9
```

---

## 5. 部署 Product Hunt 工作流

### 5.1 部署代码和脚本

```bash
# 代码已在 Section 4.1 通过 git pull 更新
# 确保全量同步脚本可执行
chmod +x /opt/cortexcrawl/producthunt-workflow/run-full-sync.sh
```

### 5.2 安装 Python 依赖

```bash
cd /opt/cortexcrawl/producthunt-workflow

python3.11 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

### 5.3 配置环境变量

```bash
cp .env.example .env
nano .env
```

```env
FEISHU_APP_ID=cli_yyyyyyyyyyyyyyyy          # Product Hunt 应用的 ID（不同于 Kickstarter）
FEISHU_APP_SECRET=yyyyyyyyyyyyyyyyyyyyyyyy
FEISHU_BASE_ID=BAseyyyyyyyyyyyyyyyyyyy
FEISHU_TABLE_ID=tblyyyyyyyyyyyyyyyyyy
FEISHU_WEBHOOK_URL=https://open.feishu.cn/open-apis/bot/v2/hook/...  # 可选

OPENCLAW_BASE_URL=http://localhost:15970
OPENCLAW_TOKEN=d171c5fce114f7c6a1c13f5ac424b3c9

PRODUCT_HUNT_API_TOKEN=your_token_here      # 可选，用于提升请求配额
```

### 5.4 重启 OpenClaw（加载两个新 Skill）

OpenClaw 以 Node.js 进程运行（非 Docker），重启方式：

```bash
# 找到进程并重启
ps aux | grep openclaw
kill <PID>

# 重新启动（以 admin 用户运行）
su - admin -c "cd /opt/openclaw && nohup node dist/index.js gateway > /var/log/openclaw.log 2>&1 &"

# 确认两个 Skill 都已加载
tail -100 /var/log/openclaw.log | grep -E "kickstarter|producthunt"
```

---

## 6. 定时任务配置

```bash
crontab -e
```

添加以下四行：

```cron
# ── Kickstarter（UTC 00:00 = 北京时间 08:00）──────────────────────
# JS 抓取 + Python 处理一步到位
0 0 * * * cd /opt/cortexcrawl/kickstarter-workflow && \
  node openclaw/fetch-kickstarter.js >> /var/log/ks-trigger.log 2>&1 && \
  venv/bin/python src/main.py >> /var/log/kickstarter-monitor.log 2>&1

# ── Product Hunt（UTC 08:00 = 北京时间 16:00）────────────────────
0 8 * * * cd /opt/cortexcrawl/producthunt-workflow && \
  node openclaw/fetch-producthunt.js >> /var/log/ph-trigger.log 2>&1 && \
  venv/bin/python src/main.py >> /var/log/producthunt-monitor.log 2>&1
```

验证 crontab 是否生效：

```bash
crontab -l
```

---

## 6.1 全量同步 (首次部署或手动补数据)

首次部署后，需要做一次全量拉取把历史数据灌入飞书表格。之后可以随时通过 OpenClaw webhook 手动触发。

### 方式一：在服务器上运行脚本 (推荐)

```bash
# Kickstarter
cd /opt/cortexcrawl/kickstarter-workflow
./run-full-sync.sh                   # 全量同步
./run-full-sync.sh --test            # 仅看 diff，不写入飞书

# Product Hunt
cd /opt/cortexcrawl/producthunt-workflow
./run-full-sync.sh
./run-full-sync.sh --test
```

### 方式三：通过 Python 直接运行

```bash
cd /opt/cortexcrawl/kickstarter-workflow
source venv/bin/activate
python src/main.py --full            # 全量拉取 + 同步
python src/main.py --full --test     # 全量拉取 + 仅看 diff
```

> **注意**: 全量拉取会抓取最多 50 页数据，耗时较长 (约 5-10 分钟)，超时设置为 10 分钟。

---

## 7. 部署验证

按以下顺序逐步验证，每一步通过后再进行下一步。

### 第一步：验证 OpenClaw 服务

```bash
# 确认进程运行中
ps aux | grep openclaw
# 预期: openclaw-gateway 进程

# 健康检查
curl -s http://localhost:15970/health
# 预期: {"ok":true,"status":"live"}
```

### 第二步：验证飞书连接

在各工作流目录下分别执行：

```bash
# Kickstarter
cd /opt/cortexcrawl/kickstarter-workflow && source venv/bin/activate
python -c "
from src.feishu_client import FeishuClient
c = FeishuClient()
records = c.list_records()
print(f'[Kickstarter] 飞书连接成功，表格现有 {len(records)} 条记录')
"

# Product Hunt
cd /opt/cortexcrawl/producthunt-workflow && source venv/bin/activate
python -c "
from src.feishu_client import FeishuClient
c = FeishuClient()
records = c.list_records()
print(f'[Product Hunt] 飞书连接成功，表格现有 {len(records)} 条记录')
"
```

**预期输出**：
```
[Kickstarter] 飞书连接成功，表格现有 0 条记录
[Product Hunt] 飞书连接成功，表格现有 0 条记录
```

**常见失败原因**：
- `401` → App ID / Secret 填错，或权限未审批通过
- `404` → base_id / table_id 填错

### 第三步：手动触发抓取，验证 JS → 文件

```bash
# 手动执行 Kickstarter 抓取
cd /opt/cortexcrawl/kickstarter-workflow
node openclaw/fetch-kickstarter.js

# 手动执行 Product Hunt 抓取
cd /opt/cortexcrawl/producthunt-workflow
node openclaw/fetch-producthunt.js
```

验证数据文件：

```bash
# 检查文件存在且有内容
ls -lh /data/kickstarter/raw_projects.json
ls -lh /data/producthunt/raw_products.json

# 检查文件内容格式
python3 -c "
import json
ks = json.load(open('/data/kickstarter/raw_projects.json'))
ph = json.load(open('/data/producthunt/raw_products.json'))
print(f'Kickstarter: {ks[\"count\"]} 个项目，抓取时间 {ks[\"timestamp\"]}')
print(f'Product Hunt: {ph[\"count\"]} 个产品，抓取时间 {ph[\"timestamp\"]}')
"
```

**预期输出**：
```
Kickstarter: 23 个项目，抓取时间 2026-03-20T08:00:12.345Z
Product Hunt: 87 个产品，抓取时间 2026-03-20T16:00:08.123Z
```

**如果文件不存在**：查看 OpenClaw 日志排查
```bash
tail -200 /var/log/openclaw.log | grep -E "kickstarter|producthunt|error|ERROR"
```

### 第四步：验证 Python 工作流（测试模式）

测试模式不会写入飞书，安全验证逻辑是否正常：

```bash
# Kickstarter 测试模式
cd /opt/cortexcrawl/kickstarter-workflow && source venv/bin/activate
python src/main.py --test
# 预期：输出 JSON 结果，success: true，无飞书写入

# Product Hunt 测试模式
cd /opt/cortexcrawl/producthunt-workflow && source venv/bin/activate
python src/main.py --test
# 预期：输出 JSON 结果，success: true，无飞书写入
```

### 第五步：全量同步验证（首次部署必做）

首次部署时飞书表格为空，需要通过全量同步灌入历史数据。先用 `--test` 验证 diff 逻辑，再正式写入。

```bash
# ── Kickstarter ──
cd /opt/cortexcrawl/kickstarter-workflow && source venv/bin/activate

# 5a. 先试跑 (全量抓取 + diff，但不写入飞书)
python src/main.py --full --test
# 预期: success: true，可以看到 new_count > 0

# 5b. 正式全量同步 (写入飞书 + 发通知)
python src/main.py --full
```

```bash
# ── Product Hunt ──
cd /opt/cortexcrawl/producthunt-workflow && source venv/bin/activate

python src/main.py --full --test     # 先试跑
python src/main.py --full            # 正式同步
```

**预期 JSON 输出**：
```json
{
  "success": true,
  "message": "工作流执行成功",
  "new_count": 120,
  "updated_count": 0,
  "unchanged_count": 0,
  "duration_seconds": 85.3
}
```

> 全量模式首次运行 `new_count` 会比较大（所有数据都是新增），耗时约 2-10 分钟。

验证飞书表格是否有新数据：
```bash
python -c "
from src.feishu_client import FeishuClient
c = FeishuClient()
records = c.list_records()
print(f'表格现有 {len(records)} 条记录')
if records:
    first = records[0]['fields']
    print('第一条记录字段：', list(first.keys()))
"
```

### 第六步：增量模式端到端验证

全量同步完成后，验证日常增量模式是否正常（此时大部分数据已存在，应该看到 unchanged 为主）：

```bash
# Kickstarter 增量运行
cd /opt/cortexcrawl/kickstarter-workflow && source venv/bin/activate
python src/main.py

# Product Hunt 增量运行
cd /opt/cortexcrawl/producthunt-workflow && source venv/bin/activate
python src/main.py
```

**预期**：`updated_count` 可能有几条（数值变化），`new_count` 应该为 0 或很少。

### 第七步：验证飞书通知（如已配置 Webhook）

工作流运行后，检查目标群聊是否收到卡片消息。如未收到：

```bash
# 手动测试 Webhook
python -c "
import os, requests
from dotenv import load_dotenv
load_dotenv()
url = os.getenv('FEISHU_WEBHOOK_URL')
r = requests.post(url, json={'msg_type': 'text', 'content': {'text': '部署验证测试'}})
print(r.json())
"
```

### 第八步：验证定时任务

```bash
# 检查 crontab 是否配置
crontab -l | grep -E "kickstarter|producthunt"

# 等待下次执行后检查日志时间戳
tail -5 /var/log/kickstarter-monitor.log
tail -5 /var/log/producthunt-monitor.log
```

---

## 8. 运维速查

### 日志位置

| 日志 | 路径 |
|------|------|
| Kickstarter 触发日志 | `/var/log/ks-trigger.log` |
| Kickstarter 工作流日志 | `/var/log/kickstarter-monitor.log` |
| Product Hunt 触发日志 | `/var/log/ph-trigger.log` |
| Product Hunt 工作流日志 | `/var/log/producthunt-monitor.log` |
| OpenClaw 日志 | `/var/log/openclaw.log` 或 `/tmp/openclaw/openclaw-*.log` |

### 常用命令

```bash
# ── 日志 ──
tail -f /var/log/kickstarter-monitor.log /var/log/producthunt-monitor.log

# 今日错误汇总
grep -i "error\|exception" /var/log/kickstarter-monitor.log /var/log/producthunt-monitor.log \
  | grep $(date +%Y-%m-%d)

# ── 手动触发 ──
# 全量同步（抓取 + diff + 入库 + 通知）
cd /opt/cortexcrawl/kickstarter-workflow && ./run-full-sync.sh
cd /opt/cortexcrawl/producthunt-workflow && ./run-full-sync.sh

# 全量同步（仅看 diff，不写入飞书）
cd /opt/cortexcrawl/kickstarter-workflow && ./run-full-sync.sh --test

# 增量模式重跑（使用已有数据文件）
cd /opt/cortexcrawl/kickstarter-workflow && source venv/bin/activate
python src/main.py --data-path /data/kickstarter/raw_projects.json

# ── OpenClaw ──
# 检查状态
curl -s http://localhost:15970/health

# 启动
su - admin -c "cd /opt/openclaw && nohup node dist/index.js gateway > /var/log/openclaw.log 2>&1 &"

# 重启
pkill -f "openclaw/dist/index.js" || true
su - admin -c "cd /opt/openclaw && nohup node dist/index.js gateway > /var/log/openclaw.log 2>&1 &"
```

### 故障速查表

| 现象 | 排查步骤 |
|------|---------|
| **飞书连接** | |
| 飞书 `401` | 检查 `.env` 中 App ID / Secret 是否正确；确认应用权限已审批 |
| 飞书 `404` | base_id / table_id 填错，从表格 URL 重新获取 |
| 错误码 `1254015` field type mismatch | 飞书表格字段类型与代码不符。**日期**必须传毫秒时间戳，**超链接**必须传 `{"text":..,"link":..}` 对象 |
| 错误码 `1254045` 字段名不存在 | 飞书表格中缺少代码引用的字段，检查字段名拼写是否完全一致 |
| 错误码 `1254104` 单次超限 | 单次批量操作超过 500 条 (代码已按 500 分批，正常不会触发) |
| 错误码 `1254291` 写入冲突 | 同一数据表并发写入冲突，代码已内置自动重试。频繁出现则检查是否有多个进程同时写 |
| **数据抓取** | |
| 数据文件不存在 | `tail -200 /var/log/openclaw.log` 查看 Skill 是否报错；手动触发验证 |
| 工作流无新数据 | 确认抓取文件 `count > 0`；检查筛选阈值是否过高 |
| **定时/触发** | |
| 定时任务未执行 | `crontab -l` 确认配置；`grep CRON /var/log/syslog` 查看调度日志 |
| OpenClaw 启动失败 | 查看 `/var/log/openclaw.log`；确认 admin 用户环境变量（如 `KIMI_API_KEY`）已配置 |
| full-sync 超时 | 全量模式最多 50 页，耗时约 5-10 分钟；检查网络或调大 `timeout` |
| 全量同步后 `new_count=0` | 说明所有数据已存在，检查 `updated_count` 是否有数值更新 |

### 更新部署

```bash
cd /opt/cortexcrawl && git pull

# 更新两个工作流的依赖
for wf in kickstarter-workflow producthunt-workflow; do
  cd /opt/cortexcrawl/$wf
  source venv/bin/activate
  pip install -r requirements.txt
  deactivate
done

# 确保全量同步脚本可执行
chmod +x /opt/cortexcrawl/kickstarter-workflow/run-full-sync.sh
chmod +x /opt/cortexcrawl/producthunt-workflow/run-full-sync.sh

# 确保全量同步脚本可执行
chmod +x /opt/cortexcrawl/kickstarter-workflow/run-full-sync.sh
chmod +x /opt/cortexcrawl/producthunt-workflow/run-full-sync.sh
```
