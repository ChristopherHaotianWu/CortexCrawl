# 微信小程序监控 - 部署文档

## 服务器信息

- **服务器**: Alibaba Cloud ECS `47.254.73.23`
- **部署路径**: `/opt/cortexcrawl/wechat-miniprogram-workflow`
- **数据路径**: `/data/wechat-miniprogram/raw_miniprograms.json`

## 部署步骤

### 1. 上传代码

```bash
rsync -avz wechat-miniprogram-workflow/ root@47.254.73.23:/opt/cortexcrawl/wechat-miniprogram-workflow/
```

### 2. 服务器初始化

```bash
ssh root@47.254.73.23
cd /opt/cortexcrawl/wechat-miniprogram-workflow

# 安装 Node.js 依赖
npm install axios

# 创建 Python 虚拟环境 (使用 python3.11)
python3.11 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 配置环境变量
cp .env.example .env
vim .env  # 填入真实凭证

# 创建数据目录
mkdir -p /data/wechat-miniprogram

# 赋予执行权限
chmod +x run-full-sync.sh
```

### 3. 首次全量同步

```bash
cd /opt/cortexcrawl/wechat-miniprogram-workflow
source venv/bin/activate
./run-full-sync.sh
```

### 4. 注册 OpenClaw Skill

```bash
# 将 skill-config.yaml 注册到 OpenClaw
curl -X POST http://localhost:15970/api/skills/register \
  -H "Authorization: Bearer $OPENCLAW_TOKEN" \
  -H "Content-Type: application/yaml" \
  --data-binary @openclaw/skill-config.yaml
```

## OpenClaw 定时调度

- **Cron**: `0 4 * * *` (每天 UTC 04:00, 北京时间 12:00)
- **Skill**: `wechat-miniprogram-monitor`
- **触发方式**: OpenClaw WebSocket 网关 → 执行 `run-full-sync.sh`

## 手动触发

```bash
# 服务器上手动全量同步
ssh root@47.254.73.23
cd /opt/cortexcrawl/wechat-miniprogram-workflow && ./run-full-sync.sh

# 仅运行 Python 处理器 (已有原始数据)
cd /opt/cortexcrawl/wechat-miniprogram-workflow
source venv/bin/activate
python src/main.py

# 仅抓取数据，不同步飞书
node openclaw/fetch-wechat-miniprogram.js --full
```

## 飞书多维表格

| 配置项 | 说明 |
|--------|------|
| `FEISHU_BASE_ID` | 多维表格 ID（URL 中的 base 部分）|
| `FEISHU_TABLE_ID` | 数据表 ID（URL 中的 table 部分）|

表格字段请参考 `src/config.py` 中的 `TABLE_FIELDS`。

## 故障排查

```bash
# 查看最新日志
journalctl -u openclaw -n 50

# 检查原始数据文件
cat /data/wechat-miniprogram/raw_miniprograms.json | python3 -m json.tool | head -50

# 手动测试 Python 处理器
cd /opt/cortexcrawl/wechat-miniprogram-workflow
source venv/bin/activate
python src/main.py --test
```
