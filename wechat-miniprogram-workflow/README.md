# WeChat Mini Program Monitor (微信小程序监控)

监控微信小程序热门应用，每日从阿拉丁指数 (aldzs.com) 抓取数据并同步到飞书多维表格，发送机器人通知。

## 筛选条件

- **月活跃用户**: ≥ 10,000
- **数据来源**: 阿拉丁指数综合排行榜

## 快速开始

```bash
cd wechat-miniprogram-workflow

# 1. 安装 Python 依赖
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# 2. 配置环境变量
cp .env.example .env
# 编辑 .env 填入真实凭证

# 3. 增量运行 (需要已有原始数据文件)
python src/main.py

# 4. 全量同步 (首次部署或手动补全)
python src/main.py --full
# 或
./run-full-sync.sh
```

## 运行模式

| 模式 | 命令 | 说明 |
|------|------|------|
| 增量 | `python src/main.py` | 从已有 JSON 文件处理数据 |
| 全量 | `python src/main.py --full` | 先全量抓取再处理入库 |
| 测试 | `python src/main.py --test` | 不实际写入飞书 |
| 全量同步 | `./run-full-sync.sh` | JS 全量抓取 + Python diff + 飞书同步 |
| 全量测试 | `./run-full-sync.sh --test` | 全量抓取 + 仅 diff（不写入） |

## 工作流架构

```
阿拉丁指数 API (aldzs.com)
    → fetch-wechat-miniprogram.js  ← cron schedule / 手动触发
    → /data/wechat-miniprogram/raw_miniprograms.json
    → src/main.py (Python 处理器)
    → 飞书多维表格 + Webhook 通知
```

## 数据字段

| 字段 | 说明 | 类型 |
|------|------|------|
| 小程序名称 | 小程序名称 | 文本 |
| 分类 | 所属分类 | 文本 |
| 简介 | 功能简介 | 文本 |
| 开发者 | 开发公司/个人 | 文本 |
| 月活用户数 | 月活跃用户数量 | 数字 |
| 日均活跃用户 | 日均活跃用户数量 | 数字 |
| 评分 | 阿拉丁评分 | 数字 |
| 上线日期 | 首次上线日期 | 日期 |
| 小程序ID | 微信小程序 AppID | 文本 |
| 封面图 | 小程序封面图链接 | 文本 |
| 标签 | 关键词标签 | 文本 |
| 小程序链接 | 微信小程序链接 | 超链接 |
| 履历 | 手动补充背景信息 | 文本 |
| 融资历史 | 手动补充融资信息 | 文本 |

## 环境变量

详见 [.env.example](.env.example)。

| 变量 | 必填 | 说明 |
|------|------|------|
| `FEISHU_APP_ID` | ✅ | 飞书应用 ID |
| `FEISHU_APP_SECRET` | ✅ | 飞书应用密钥 |
| `FEISHU_BASE_ID` | ✅ | 多维表格 ID |
| `FEISHU_TABLE_ID` | ✅ | 数据表 ID |
| `FEISHU_WEBHOOK_URL` | ❌ | 飞书群机器人 Webhook |
| `ALADING_API_TOKEN` | ❌ | 阿拉丁指数 API Token |
| `OPENCLAW_TOKEN` | ❌ | OpenClaw 服务器 Token |

## OpenClaw 定时任务

- **触发时间**: 每天 UTC 04:00 (北京时间 12:00)
- **Skill 名称**: `wechat-miniprogram-monitor`
- **配置文件**: `openclaw/skill-config.yaml`
