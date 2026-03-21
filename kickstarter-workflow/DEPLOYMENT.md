# Kickstarter 监控工作流 — 部署手册

> 本文档专注于生产环境部署。开发说明和架构介绍请参考 [README.md](./README.md)。

---

## 目录

1. [前置条件](#1-前置条件)
2. [飞书平台配置](#2-飞书平台配置)
3. [OpenClaw 服务器配置](#3-openclaw-服务器配置)
4. [Python 工作流部署](#4-python-工作流部署)
5. [定时任务配置](#5-定时任务配置)
6. [验证与冒烟测试](#6-验证与冒烟测试)
7. [运维参考](#7-运维参考)

---

## 1. 前置条件

### 服务器信息

| 组件 | 地址 | 端口 |
|------|------|------|
| 阿里云 ECS | `47.254.73.23` | — |
| OpenClaw 服务 | `47.254.73.23` | `8080` |
| Python 工作流 | `47.254.73.23` | `8000` |

### 所需账号

| 账号 | 用途 | 备注 |
|------|------|------|
| 飞书企业账号（管理员） | 创建应用、配置表格 | 必需 |
| 阿里云 ECS SSH 访问 | 服务器操作 | 必需 |

### 运行环境要求

```
服务器端:
  - Python 3.9+
  - pip（最新版）
  - Docker（OpenClaw 运行依赖）
```

---

## 2. 飞书平台配置

### 2.1 创建企业自建应用

1. 访问 [飞书开发者后台](https://open.feishu.cn/app)，使用企业管理员账号登录
2. 点击右上角「创建企业自建应用」
3. 填写信息：
   - 应用名称：`Kickstarter Monitor`
   - 应用描述：`自动监控 Kickstarter 高额众筹项目`
4. 创建后，进入「凭证与基础信息」，**记录以下两项**（后续配置必用）：
   ```
   App ID:     cli_xxxxxxxxxx
   App Secret: xxxxxxxxxxxxxxxxxxxxxxxx
   ```
   > ⚠️ App Secret 仅显示一次，务必立即保存。

### 2.2 开通 API 权限

进入应用「权限管理」→「添加权限」，搜索并开通：

| 权限代码 | 说明 |
|---------|------|
| `bitable:base:read` | 读取多维表格基础信息 |
| `bitable:record:read` | 读取记录 |
| `bitable:record:write` | 新增 / 编辑记录 |
| `bitable:table:read` | 读取表格字段信息 |

添加完成后提交审核，等待企业管理员审批。

### 2.3 创建多维表格

1. 在飞书中新建多维表格，命名为 `Kickstarter 监控`
2. 按以下顺序添加字段（**字段名、类型必须完全一致**）：

| 序号 | 字段名 | 字段类型 |
|-----|-------|---------|
| 1 | 产品名 | 文本 |
| 2 | 国家 | 文本 |
| 3 | 公司 | 文本 |
| 4 | 标签 | 文本 |
| 5 | 产品说明 | 文本 |
| 6 | 众筹金额/美金 | 数字 |
| 7 | 众筹人数 | 数字 |
| 8 | 众筹开始时间 | 日期 |
| 9 | 创始人 | 文本 |
| 10 | 项目链接 | 超链接 |
| 11 | 履历 | 文本（手动填写，程序不覆盖） |
| 12 | 融资历史 | 文本（手动填写，程序不覆盖） |

3. 从表格 URL 获取 ID：
   ```
   https://www.feishu.cn/base/BAsexxxxxxxxxxxxxxxxxxx?table=tblxxxxxxxxxxxxxxxxxxx
                                └────── base_id ──────┘       └──── table_id ────┘
   ```

### 2.4 创建群机器人（可选）

如需每日推送通知：

1. 打开目标群聊 → 群设置 → 群机器人 → 添加机器人
2. 选择「自定义机器人」，命名为 `Kickstarter 监控助手`
3. 复制并保存 Webhook URL：
   ```
   https://open.feishu.cn/open-apis/bot/v2/hook/xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
   ```

---

## 3. OpenClaw 服务器配置

### 3.1 上传 Skill 文件

在**本地**执行：

```bash
cd /path/to/CortexCrawl

# 在服务器上创建目录
ssh root@47.254.73.23 "mkdir -p /opt/openclaw/skills/kickstarter-monitor"

# 上传文件
scp kickstarter-workflow/openclaw/skill-config.yaml \
    kickstarter-workflow/openclaw/fetch-kickstarter.js \
    root@47.254.73.23:/opt/openclaw/skills/kickstarter-monitor/

# 验证
ssh root@47.254.73.23 "ls -la /opt/openclaw/skills/kickstarter-monitor/"
```

### 3.2 配置环境变量

```bash
ssh root@47.254.73.23
nano /opt/openclaw/.env
```

追加以下内容（替换占位符为真实值）：

```env
OPENCLAW_TOKEN=d171c5fce114f7c6a1c13f5ac424b3c9
```

### 3.3 重启 OpenClaw

```bash
cd /opt/openclaw
docker-compose restart

# 确认服务正常
docker logs --tail 50 openclaw
curl -s http://localhost:8080/health
```

---

## 4. Python 工作流部署

以下操作均在**服务器 `47.254.73.23`** 上执行。

### 4.1 拉取代码

```bash
# 首次部署
git clone <repository-url> /opt/cortexcrawl
cd /opt/cortexcrawl/kickstarter-workflow

# 更新部署
cd /opt/cortexcrawl && git pull
```

### 4.2 创建虚拟环境并安装依赖

```bash
cd /opt/cortexcrawl/kickstarter-workflow

python3 -m venv venv
source venv/bin/activate

pip install --upgrade pip
pip install -r requirements.txt
```

### 4.3 配置环境变量

```bash
cp .env.example .env
nano .env
```

填写以下所有必填项：

```env
# ---- 飞书应用（必填）----
FEISHU_APP_ID=cli_xxxxxxxxxxxxxxxx
FEISHU_APP_SECRET=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx

# ---- 飞书多维表格（必填）----
FEISHU_BASE_ID=BAsexxxxxxxxxxxxxxxxxxx
FEISHU_TABLE_ID=tblxxxxxxxxxxxxxxxxxxx

# ---- 飞书机器人（可选）----
FEISHU_WEBHOOK_URL=https://open.feishu.cn/open-apis/bot/v2/hook/xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx

# ---- OpenClaw（可选）----
OPENCLAW_BASE_URL=http://47.254.73.23:8080/api
OPENCLAW_TOKEN=d171c5fce114f7c6a1c13f5ac424b3c9
```

### 4.4 创建数据目录

```bash
mkdir -p /data/kickstarter
```

---

## 5. 定时任务配置

### 方式 A：Cron（服务器独立运行）

```bash
crontab -e
```

添加以下两行：

```cron
# Step 1: UTC 00:00 触发 OpenClaw 抓取（北京时间 08:00）
0 0 * * * curl -s -X POST http://localhost:8080/api/kickstarter/trigger \
  -H "Authorization: Bearer d171c5fce114f7c6a1c13f5ac424b3c9" >> /var/log/kickstarter-trigger.log 2>&1

# Step 2: UTC 00:05 执行 Python 工作流（等待抓取完成）
5 0 * * * cd /opt/cortexcrawl/kickstarter-workflow && \
  /opt/cortexcrawl/kickstarter-workflow/venv/bin/python src/main.py \
  >> /var/log/kickstarter-monitor.log 2>&1
```

### 方式 B：OpenClaw 内置调度（已配置）

`skill-config.yaml` 中已设置：

```yaml
triggers:
  - type: schedule
    cron: "0 0 * * *"   # UTC 00:00，即北京时间 08:00
    timezone: "UTC"
```

OpenClaw 完成抓取后，会自动通过 Webhook 触发 Python 工作流（`http://localhost:8000/api/process-kickstarter-data`）。

> 两种方式选其一即可，避免重复执行。

---

## 6. 验证与冒烟测试

### 6.1 测试飞书连接

```bash
cd /opt/cortexcrawl/kickstarter-workflow
source venv/bin/activate

python -c "
from src.feishu_client import FeishuClient
client = FeishuClient()
records = client.list_records()
print(f'飞书连接成功，当前共 {len(records)} 条记录')
"
```

### 6.2 手动触发 OpenClaw 抓取

```bash
curl -X POST http://47.254.73.23:8080/api/kickstarter/trigger \
  -H "Authorization: Bearer d171c5fce114f7c6a1c13f5ac424b3c9"
```

等待约 1 分钟后，确认数据文件已生成：

```bash
ls -lh /data/kickstarter/raw_projects.json
```

### 6.3 测试模式运行（不写入数据）

```bash
cd /opt/cortexcrawl/kickstarter-workflow
source venv/bin/activate

python src/main.py --test
```

### 6.4 完整流程运行

```bash
python src/main.py
```

正常输出示例：

```
2026-03-20 08:00:00 - INFO - 🚀 Kickstarter 监控工作流启动
2026-03-20 08:00:01 - INFO - 📂 加载数据: /data/kickstarter/raw_projects.json
2026-03-20 08:00:02 - INFO - 📊 从飞书多维表格加载现有数据...
2026-03-20 08:00:04 - INFO - 🔄 处理数据 (去重但更新)...
2026-03-20 08:00:05 - INFO - 处理完成: 新增 3 个项目, 更新 8 个项目, 未变更 42 个项目
2026-03-20 08:00:08 - INFO - 📤 发送飞书通知...
2026-03-20 08:00:09 - INFO - 卡片消息发送成功
```

---

## 7. 运维参考

### 查看日志

```bash
# 实时跟踪 Python 工作流日志
tail -f /var/log/kickstarter-monitor.log

# 查看 OpenClaw 日志
docker logs -f openclaw --tail 100

# 过滤错误
grep -i "error\|exception" /var/log/kickstarter-monitor.log
```

### 手动指定数据文件运行

```bash
python src/main.py --data-path /path/to/custom_raw.json
```

### 常见问题速查

| 现象 | 可能原因 | 处理方式 |
|------|---------|---------|
| `401 Invalid app_id` | App ID / Secret 填错 | 重新从飞书后台复制 |
| `field type mismatch` | 表格字段类型不匹配 | 检查「众筹金额/美金」「众筹人数」是否为数字类型，「众筹开始时间」是否为日期类型 |
| 数据重复写入 | 项目链接格式不一致 | 确认 `project_url` 格式统一为 `https://www.kickstarter.com/projects/xxx` |
| 数据文件不存在 | OpenClaw 未完成抓取 | 检查 OpenClaw 日志，确认 Skill 已触发并执行完毕 |
| Kickstarter API 403 | 请求频率超限或 IP 被限制 | 增大 `fetch-kickstarter.js` 中的请求间隔，或更换出口 IP |

### 更新部署

```bash
cd /opt/cortexcrawl
git pull

cd kickstarter-workflow
source venv/bin/activate
pip install -r requirements.txt   # 如有新依赖

# 上传最新 Skill 文件到 OpenClaw
scp openclaw/* root@47.254.73.23:/opt/openclaw/skills/kickstarter-monitor/
ssh root@47.254.73.23 "cd /opt/openclaw && docker-compose restart"
```
