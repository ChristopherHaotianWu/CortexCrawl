# Kickstarter 监控工作流

一个自动化监控 Kickstarter 高额众筹项目的完整解决方案，支持数据抓取、智能处理和飞书多维表格同步。

## 📋 目录

- [项目概述](#项目概述)
- [系统架构](#系统架构)
- [前置条件](#前置条件)
- [详细部署步骤](#详细部署步骤)
- [配置说明](#配置说明)
- [使用方法](#使用方法)
- [定时任务设置](#定时任务设置)
- [监控与日志](#监控与日志)
- [故障排查](#故障排查)
- [安全建议](#安全建议)
- [开发指南](#开发指南)

---

## 项目概述

### 功能特性

| 功能 | 描述 |
|------|------|
| 🎯 智能筛选 | 自动筛选众筹金额 ≥ $500,000 的高额项目 |
| 📅 时间过滤 | 仅监控 2026-01-01 之后发布的项目 |
| 🔄 去重更新 | 已存在项目自动更新金额和人数，不重复创建 |
| 📊 多维表格 | 数据同步到飞书多维表格，便于团队协作 |
| 🤖 自动通知 | 每日推送飞书卡片消息，展示新增和更新项目 |
| ⏰ 定时执行 | 支持 Cron 定时任务和手动触发 |

### 技术栈

- **数据抓取**: OpenClaw / Node.js + Kickstarter GraphQL API
- **数据处理**: Python 3.9+
- **数据存储**: 飞书多维表格 (Bitable)
- **通知推送**: 飞书机器人 Webhook
- **定时调度**: Cron / OpenClaw 内置调度

---

## 系统架构

```
┌─────────────────────────────────────────────────────────────────┐
│                        Kickstarter 监控工作流                      │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌─────────────┐     ┌─────────────┐     ┌─────────────────┐  │
│  │  Kickstarter │────▶│  OpenClaw   │────▶│  raw_projects   │  │
│  │   GraphQL   │     │   Skill     │     │    .json        │  │
│  └─────────────┘     └─────────────┘     └─────────────────┘  │
│                                                   │              │
│                                                   ▼              │
│  ┌─────────────┐     ┌─────────────┐     ┌─────────────────┐  │
│  │  飞书多维   │◀────│   Python    │◀────│   DataProcessor │  │
│  │   表格     │     │   工作流    │     │                 │  │
│  └─────────────┘     └──────┬──────┘     └─────────────────┘  │
│                             │                                   │
│                             ▼                                   │
│                      ┌─────────────┐                           │
│                      │  飞书卡片   │                           │
│                      │   通知     │                           │
│                      └─────────────┘                           │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 数据流向

```
Day 1: Kickstarter ──抓取──▶ 新项目 A, B, C ──写入──▶ 飞书表格 (A, B, C)
                                     │
                                     └──通知──▶ 📊 新增 3 个项目

Day 2: Kickstarter ──抓取──▶ 项目 A(金额↑), B, D ──处理──▶ 飞书表格
                                     │                     (更新 A, 新增 D)
                                     └──通知──▶ 📈 更新 1 个, 🆕 新增 1 个
```

---

## 前置条件

### 必需账号

| 账号类型 | 用途 | 获取地址 |
|---------|------|---------|
| 飞书企业账号 | 多维表格和机器人 | https://www.feishu.cn |
| OpenClaw 服务器 | 数据抓取 | 已部署: `47.254.73.23` |

### 服务器要求

```yaml
OpenClaw 服务器:
  - 阿里云 ECS: 47.254.73.23
  - Docker: 已安装
  - 端口: 8080 (OpenClaw), 8000 (Python 服务)

本地开发环境:
  - Python: 3.9+
  - pip: 最新版本
  - Git: 用于版本控制
```

### 工具准备

```bash
# 检查 Python 版本
python --version  # 需要 >= 3.9

# 安装 uv (推荐，比 pip 更快)
curl -LsSf https://astral.sh/uv/install.sh | sh

# 或使用 pip
pip install --upgrade pip
```

---

## 详细部署步骤

### 第一阶段：飞书平台配置

#### 1.1 创建企业自建应用

**步骤详解：**

1. **登录开发者后台**
   - 访问 https://open.feishu.cn/app
   - 使用企业管理员账号登录
   - 确保你有「创建应用」的权限

2. **创建应用**
   - 点击右上角「创建企业自建应用」按钮
   - 填写应用基本信息：
     ```
     应用名称: Kickstarter Monitor
     应用描述: 自动监控 Kickstarter 高额众筹项目
     应用图标: 可上传任意图标或使用默认
     ```
   - 点击「创建应用」

3. **获取凭证**
   - 创建成功后进入应用详情页
   - 点击左侧「凭证与基础信息」
   - **记录以下信息**（后续配置需要）：
     ```
     App ID: cli_xxxxxxxxxx
     App Secret: xxxxxxxxxxxxxxxxxxxxxxxx
     ```
   - ⚠️ **App Secret 只显示一次，务必保存**

#### 1.2 开通 API 权限

**操作步骤：**

1. 在应用详情页左侧，点击「权限管理」
2. 点击「添加权限」按钮
3. 搜索并添加以下权限：

| 权限名称 | 权限代码 | 说明 |
|---------|---------|------|
| 查看多维表格 | `bitable:base:read` | 读取表格基础信息 |
| 查看记录 | `bitable:record:read` | 读取表格中的数据 |
| 新增记录 | `bitable:record:write` | 创建新记录 |
| 编辑记录 | `bitable:record:write` | 更新现有记录 |
| 查看表格属性 | `bitable:table:read` | 读取表格字段信息 |

4. 添加完成后，点击「申请发布」
5. 企业管理员审批通过后权限生效

#### 1.3 创建多维表格

**详细步骤：**

1. **创建表格**
   - 打开飞书，进入「多维表格」
   - 点击「新建多维表格」
   - 命名表格：`Kickstarter 监控`

2. **添加字段（必须严格按顺序）**

   点击「添加字段」，依次添加以下字段：

   | 序号 | 字段名 | 字段类型 | 配置说明 |
   |-----|-------|---------|---------|
   | 1 | 产品名 | 文本 | 默认配置 |
   | 2 | 国家 | 文本 | 默认配置 |
   | 3 | 公司 | 文本 | 默认配置 |
   | 4 | 标签 | 文本 | 默认配置 |
   | 5 | 产品说明 | 文本 | 默认配置 |
   | 6 | 众筹金额/美金 | 数字 | 格式：数字 |
   | 7 | 众筹人数 | 数字 | 格式：数字 |
   | 8 | 众筹开始时间 | 日期 | 格式：日期时间 |
   | 9 | 创始人 | 文本 | 默认配置 |
   | 10 | 项目链接 | 超链接 | 默认配置 |
   | 11 | 履历 | 文本 | 默认配置，手动补充 |
   | 12 | 融资历史 | 文本 | 默认配置，手动补充 |

3. **获取表格 ID**
   
   方法 A - 从 URL 获取：
   ```
   表格 URL: https://www.feishu.cn/base/BAsexxxxxxxxxx?table=tblxxxxxxxxxx
                                   └─────────────┘        └────────────┘
                                    base_id               table_id
   ```
   
   方法 B - 从 API 调试台获取：
   - 访问 https://open.feishu.cn/api_explorer
   - 选择 `bitable` → `获取多维表格元数据`
   - 执行后查看返回数据

4. **记录信息**
   ```
   base_id: BAsexxxxxxxxxxxxxxxxxxx
   table_id: tblxxxxxxxxxxxxxxxxxxx
   ```

#### 1.4 创建群机器人（可选）

如果需要每日推送通知到群聊：

1. 打开目标飞书群聊
2. 点击群设置 → 「群机器人」→ 「添加机器人」
3. 选择「自定义机器人」
4. 命名机器人：`Kickstarter 监控助手`
5. 复制 Webhook URL：
   ```
   https://open.feishu.cn/open-apis/bot/v2/hook/xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
   ```

---

### 第二阶段：OpenClaw 服务器配置

#### 2.1 连接到服务器

```bash
# 使用 SSH 连接
ssh root@47.254.73.23

# 如果使用密钥
ssh -i ~/.ssh/your_key.pem root@47.254.73.23
```

#### 2.2 上传 Skill 文件

**在本地执行：**

```bash
# 进入项目目录
cd /path/to/CortexCrawl

# 创建远程目录
ssh root@47.254.73.23 "mkdir -p /opt/openclaw/skills/kickstarter-monitor"

# 上传配置文件
scp kickstarter-workflow/openclaw/* root@47.254.73.23:/opt/openclaw/skills/kickstarter-monitor/

# 验证上传
ssh root@47.254.73.23 "ls -la /opt/openclaw/skills/kickstarter-monitor/"
```

上传的文件说明：

| 文件 | 说明 |
|------|------|
| `skill-config.yaml` | OpenClaw Skill 配置文件 |
| `fetch-kickstarter.js` | Kickstarter 数据抓取脚本 |

#### 2.3 配置 Skill

**编辑配置文件：**

```bash
# 登录服务器
ssh root@47.254.73.23

# 查看配置文件
cat /opt/openclaw/skills/kickstarter-monitor/skill-config.yaml
```

配置说明：

```yaml
skill:
  name: kickstarter-monitor
  version: 1.0.0
  description: 监控 Kickstarter 高额众筹项目
  
  # 触发器配置
  triggers:
    - type: schedule
      cron: "0 0 * * *"      # 每天 UTC 00:00 执行（北京时间 08:00）
      timezone: "UTC"
    
    - type: webhook          # 支持手动触发
      path: /api/kickstarter/trigger
      method: POST
      auth: bearer_token
  
  # 筛选条件
  pipeline:
    steps:
      - name: filter_by_funding
        conditions:
          - field: pledged
            operator: gte
            value: 500000      # 最小众筹金额 $500,000
      - name: filter_by_date
        conditions:
          - field: launched_at
            operator: gte
            value: "2026-01-01T00:00:00Z"  # 2026年后发布
```

#### 2.4 配置环境变量

```bash
# 编辑环境变量文件
nano /opt/openclaw/.env
```

添加以下内容：

```env
# OpenClaw Token
OPENCLAW_TOKEN=d171c5fce114f7c6a1c13f5ac424b3c9

# 飞书配置
FEISHU_APP_ID=cli_xxxxxxxxxxxxxxxx
FEISHU_APP_SECRET=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
FEISHU_BASE_ID=BAsexxxxxxxxxxxxxxxxxxx
FEISHU_TABLE_ID=tblxxxxxxxxxxxxxxxxxxx
FEISHU_WEBHOOK_URL=https://open.feishu.cn/open-apis/bot/v2/hook/xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx

# 可选：日志级别
LOG_LEVEL=INFO
```

#### 2.5 重启 OpenClaw 服务

```bash
cd /opt/openclaw

# 重启服务
docker-compose restart

# 查看日志
docker logs -f openclaw --tail 100
```

验证服务状态：

```bash
# 检查端口
curl http://localhost:8080/health

# 测试 Skill
curl -X POST http://localhost:8080/api/kickstarter/trigger \
  -H "Authorization: Bearer $OPENCLAW_TOKEN"
```

---

### 第三阶段：Python 工作流部署

#### 3.1 克隆项目

```bash
# 如果尚未克隆
git clone <repository-url>
cd CortexCrawl/kickstarter-workflow

# 如果已克隆，进入目录
cd /path/to/CortexCrawl/kickstarter-workflow
```

#### 3.2 创建虚拟环境

```bash
# 创建虚拟环境
python -m venv venv

# 激活虚拟环境
# macOS/Linux:
source venv/bin/activate

# Windows:
# venv\Scripts\activate

# 验证激活成功
which python  # 应显示 venv 路径
```

#### 3.3 安装依赖

```bash
# 升级 pip
pip install --upgrade pip

# 安装依赖
pip install -r requirements.txt

# 验证安装
pip list
```

dependencies 说明：

| 包名 | 版本 | 用途 |
|------|------|------|
| requests | >=2.31.0 | HTTP 请求 |
| pydantic | >=2.0.0 | 数据验证 |
| python-dateutil | >=2.8.0 | 日期处理 |
| python-dotenv | >=1.0.0 | 环境变量加载 |
| structlog | >=23.0.0 | 结构化日志 |
| typing-extensions | >=4.0.0 | 类型扩展 |

#### 3.4 配置环境变量

```bash
# 复制模板文件
cp .env.example .env

# 编辑配置文件
nano .env
```

完整配置示例：

```env
# ==========================================
# Kickstarter Monitor - 环境变量配置
# ==========================================

# ------------------------------------------
# 飞书应用配置 (必填)
# ------------------------------------------
# 从飞书开发者后台获取: https://open.feishu.cn/app
FEISHU_APP_ID=cli_xxxxxxxxxxxxxxxx
FEISHU_APP_SECRET=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx

# ------------------------------------------
# 飞书多维表格配置 (必填)
# ------------------------------------------
# 从表格 URL 获取: https://www.feishu.cn/base/{base_id}?table={table_id}
FEISHU_BASE_ID=BAsexxxxxxxxxxxxxxxxxxx
FEISHU_TABLE_ID=tblxxxxxxxxxxxxxxxxxxx

# ------------------------------------------
# 飞书机器人配置 (可选)
# ------------------------------------------
# 用于发送群通知，不配置则不发送
FEISHU_WEBHOOK_URL=https://open.feishu.cn/open-apis/bot/v2/hook/xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx

# ------------------------------------------
# OpenClaw 配置 (可选)
# ------------------------------------------
# 用于本地测试连接 OpenClaw 服务器
OPENCLAW_BASE_URL=http://47.254.73.23:8080/api
OPENCLAW_TOKEN=d171c5fce114f7c6a1c13f5ac424b3c9
```

#### 3.5 测试运行

```bash
# 确保在虚拟环境中
source venv/bin/activate

# 运行主程序
python -m src.main

# 或使用测试模式（不实际更新数据）
python -m src.main --test

# 指定数据文件
python -m src.main --data-path /path/to/raw_projects.json
```

预期输出：

```
2024-01-15 08:00:00 - INFO - 🚀 Kickstarter 监控工作流启动
2024-01-15 08:00:01 - INFO - 📂 加载数据: /data/kickstarter/raw_projects.json
2024-01-15 08:00:02 - INFO - 📊 从飞书多维表格加载现有数据...
2024-01-15 08:00:03 - INFO - 共获取 150 条记录
2024-01-15 08:00:04 - INFO - 🔄 处理数据 (去重但更新)...
2024-01-15 08:00:05 - INFO - 处理完成: 新增 3 个项目, 更新 12 个项目, 未变更 135 个项目
2024-01-15 08:00:06 - INFO - 📝 创建 3 条新记录...
2024-01-15 08:00:07 - INFO - 成功创建 3 条记录
2024-01-15 08:00:08 - INFO - 📝 更新 12 条记录...
2024-01-15 08:00:09 - INFO - 成功更新 12 条记录
2024-01-15 08:00:10 - INFO - 📤 发送飞书通知...
2024-01-15 08:00:11 - INFO - 卡片消息发送成功
{
  "success": true,
  "message": "工作流执行成功",
  "timestamp": "2024-01-15T08:00:11.123456",
  "duration_seconds": 11.5,
  "new_count": 3,
  "updated_count": 12,
  "unchanged_count": 135
}
```

---

## 配置说明

### 数据筛选配置

编辑 `src/config.py`：

```python
@dataclass
class KickstarterConfig:
    """Kickstarter 监控配置"""
    min_funding_amount: int = 500000    # 最小众筹金额（美元）
    min_launch_date: str = "2026-01-01"  # 最早发布日期
    raw_data_path: str = "/data/kickstarter/raw_projects.json"
```

### 飞书字段映射

```python
TABLE_FIELDS = {
    "product_name": "产品名",
    "country": "国家",
    "company": "公司",
    "category": "标签",
    "description": "产品说明",
    "funding_amount": "众筹金额/美金",
    "backers_count": "众筹人数",
    "launch_date": "众筹开始时间",
    "founder": "创始人",
    "project_url": "项目链接",
    "background": "履历",
    "funding_history": "融资历史"
}
```

---

## 使用方法

### 手动执行

```bash
# 基本用法
python -m src.main

# 指定数据文件
python -m src.main --data-path /path/to/data.json

# 测试模式（不写入数据）
python -m src.main --test
```

### 作为模块导入

```python
from src.main import KickstarterMonitor

# 创建工作流实例
monitor = KickstarterMonitor()

# 执行工作流
result = monitor.run()

# 处理结果
if result["success"]:
    print(f"新增: {result['new_count']} 个项目")
    print(f"更新: {result['updated_count']} 个项目")
else:
    print(f"失败: {result['message']}")
```

---

## 定时任务设置

### 使用 Cron（推荐）

```bash
# 编辑 crontab
crontab -e

# 添加每日执行（北京时间 08:00 = UTC 00:00）
0 0 * * * cd /path/to/kickstarter-workflow && /path/to/venv/bin/python -m src.main >> /var/log/kickstarter-monitor.log 2>&1

# 或者每小时执行一次
0 * * * * cd /path/to/kickstarter-workflow && /path/to/venv/bin/python -m src.main >> /var/log/kickstarter-monitor.log 2>&1
```

Crontab 格式说明：

```
* * * * * 命令
│ │ │ │ │
│ │ │ │ └─── 星期 (0-7, 0 和 7 都代表星期日)
│ │ │ └───── 月份 (1-12)
│ │ └─────── 日期 (1-31)
│ └───────── 小时 (0-23)
└─────────── 分钟 (0-59)
```

### 使用 OpenClaw 调度

已在 `skill-config.yaml` 中配置：

```yaml
triggers:
  - type: schedule
    cron: "0 0 * * *"      # 每天 UTC 00:00
    timezone: "UTC"
```

---

## 监控与日志

### 日志文件位置

```bash
# Python 工作流日志
/var/log/kickstarter-monitor.log

# OpenClaw 日志
docker logs -f openclaw

# 系统日志（如果使用 systemd）
journalctl -u kickstarter-monitor
```

### 查看日志命令

```bash
# 实时查看
tail -f /var/log/kickstarter-monitor.log

# 查看最近 100 行
tail -n 100 /var/log/kickstarter-monitor.log

# 搜索错误
grep -i "error" /var/log/kickstarter-monitor.log

# 按日期查看
grep "2024-01-15" /var/log/kickstarter-monitor.log
```

### 健康检查

```bash
# 测试飞书连接
python -c "
from src.feishu_client import FeishuClient
client = FeishuClient()
records = client.list_records()
print(f'连接成功，共 {len(records)} 条记录')
"

# 测试数据处理器
python -c "
from src.data_processor import DataProcessor
processor = DataProcessor()
print('数据处理器初始化成功')
"
```

---

## 故障排查

### 常见问题

#### 1. 飞书 API 返回 401 错误

**症状：**
```
Error: 获取飞书 access token 失败: {'code': 401, 'msg': 'Invalid app_id'}
```

**原因与解决方案：**

| 可能原因 | 检查方法 | 解决方案 |
|---------|---------|---------|
| App ID 错误 | 检查 `.env` 文件 | 从飞书后台重新复制 |
| App Secret 错误 | 检查 `.env` 文件 | 重置 Secret 并更新配置 |
| 权限未开通 | 查看飞书后台 | 开通 `bitable:record:read` 等权限 |
| 应用未发布 | 查看飞书后台 | 提交审核并发布应用 |

#### 2. 表格写入失败

**症状：**
```
Error: 批量创建记录失败: {'code': 1250004, 'msg': 'field type mismatch'}
```

**检查清单：**

1. 字段名称是否完全一致（包括空格）
2. 字段类型是否正确：
   - `众筹金额/美金` 必须是「数字」类型
   - `众筹开始时间` 必须是「日期」类型
   - `项目链接` 必须是「超链接」类型

3. 字段顺序是否与配置一致

#### 3. 数据重复

**症状：**
同一项目在表格中有多条记录

**原因：**
项目链接格式不一致导致无法正确去重

**解决方案：**
- 确保所有项目链接使用统一格式：`https://kickstarter.com/projects/xxx`
- 检查 `project_url` 字段是否包含追踪参数（如 `?ref=discovery`）
- 定期清理重复数据

#### 4. OpenClaw 无法启动

**症状：**
```
Error: port 8080 is already in use
```

**解决方案：**

```bash
# 检查端口占用
sudo lsof -i :8080

# 终止占用进程
sudo kill -9 <PID>

# 或修改端口映射
docker-compose -p openclaw up -d
```

#### 5. Kickstarter 抓取失败

**症状：**
```
Error: Kickstarter API returned 403
```

**原因：**
- Kickstarter 的 GraphQL API 可能有请求频率限制
- IP 被暂时封禁

**解决方案：**
- 增加请求间隔（修改 `fetch-kickstarter.js` 中的 `sleep` 时间）
- 使用代理服务器
- 减少抓取页数

---

## 安全建议

### 1. Token 管理

```bash
# 定期更换 Token（建议每 90 天）

# 飞书 App Secret 重置
# 1. 登录飞书开发者后台
# 2. 进入应用 → 凭证与基础信息
# 3. 点击 App Secret 的「重置」按钮
# 4. 更新 .env 文件

# OpenClaw Token 更换
# 1. 登录 OpenClaw 服务器
# 2. 编辑 /opt/openclaw/.env
# 3. 生成新 Token: openssl rand -hex 16
# 4. 重启服务
```

### 2. 访问控制

```bash
# 限制 OpenClaw 服务器访问
# 在阿里云安全组中配置：

# 只允许特定 IP 访问 8080 端口
来源: 你的办公 IP/32
协议: TCP
端口: 8080

# SSH 访问限制
来源: 你的办公 IP/32
协议: TCP
端口: 22
```

### 3. 数据备份

```bash
# 定期导出飞书表格数据

# 方法 1: 使用飞书导出功能
# 在多维表格中点击「...」→ 「导出为 Excel」

# 方法 2: 使用 API 备份
python -c "
import json
from src.feishu_client import FeishuClient
client = FeishuClient()
records = client.list_records()
with open('backup.json', 'w') as f:
    json.dump(records, f, indent=2)
print(f'备份完成: {len(records)} 条记录')
"
```

### 4. 日志清理

```bash
# 设置日志轮转
sudo nano /etc/logrotate.d/kickstarter-monitor
```

添加内容：

```
/var/log/kickstarter-monitor.log {
    daily
    rotate 30
    compress
    delaycompress
    missingok
    notifempty
    create 644 root root
    postrotate
        systemctl reload rsyslog
    endscript
}
```

---

## 开发指南

### 项目结构

```
kickstarter-workflow/
├── README.md                 # 项目文档
├── DEPLOYMENT.md            # 部署指南（原文档）
├── requirements.txt         # Python 依赖
├── .env.example            # 环境变量模板
├── .env                    # 本地环境变量（不提交）
├── openclaw/               # OpenClaw Skill 文件
│   ├── skill-config.yaml   # Skill 配置
│   └── fetch-kickstarter.js # 抓取脚本
├── src/                    # Python 源代码
│   ├── __init__.py
│   ├── main.py            # 主程序入口
│   ├── config.py          # 配置管理
│   ├── data_processor.py  # 数据处理核心
│   └── feishu_client.py   # 飞书 API 客户端
└── templates/             # 模板文件
    └── notification_card.json  # 飞书卡片模板
```

### 添加新字段

1. 更新 `src/config.py` 中的 `TABLE_FIELDS`
2. 在飞书多维表格中添加对应字段
3. 更新 `src/data_processor.py` 中的 `Project` 类
4. 重新部署

### 调试模式

```bash
# 启用详细日志
export LOG_LEVEL=DEBUG
python -m src.main

# 使用 ipdb 调试
pip install ipdb
python -m ipdb -c continue -m src.main
```

---

## 更新日志

| 版本 | 日期 | 更新内容 |
|------|------|---------|
| 1.0.0 | 2024-03 | 初始版本发布 |

---

## 联系方式

如有问题，请提交 Issue 或联系项目维护者。
