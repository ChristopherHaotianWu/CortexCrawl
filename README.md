# CortexCrawl

基于 OpenClaw API 的数据采集与分析服务

## 项目简介

CortexCrawl 是一个部署在阿里云上的数据采集服务，通过 OpenClaw API 实现智能化的数据抓取和处理能力。

## 部署信息

- **服务器地址**: `47.254.73.23`
- **服务商**: 阿里云
- **部署方式**: 云服务器 ECS

## 环境配置

### 1. 配置 OpenClaw Token

> ⚠️ **安全提示**: 请勿将 Token 直接提交到代码仓库

创建 `.env` 文件：

```bash
# 复制环境变量模板
cp .env.example .env

# 编辑 .env 文件，填入你的 Token
nano .env
```

`.env` 文件内容：

```env
OPENCLAW_TOKEN=your_openclaw_token_here
SERVER_IP=47.254.73.23
```

### 2. 安装依赖

```bash
# 使用 uv 安装依赖
uv pip install -r requirements.txt
```

### 3. 运行服务

```bash
# 本地开发
python main.py

# 或生产部署
uvicorn main:app --host 0.0.0.0 --port 8000
```

## 连接到阿里云服务器

```bash
# SSH 连接到服务器
ssh root@47.254.73.23

# 或使用密钥
ssh -i ~/.ssh/your_key.pem root@47.254.73.23
```

## API 使用示例

```python
import requests
import os
from dotenv import load_dotenv

load_dotenv()

token = os.getenv("OPENCLAW_TOKEN")
base_url = f"http://{os.getenv('SERVER_IP')}:8000"

headers = {
    "Authorization": f"Bearer {token}",
    "Content-Type": "application/json"
}

# 示例：发起爬虫任务
response = requests.post(
    f"{base_url}/api/crawl",
    headers=headers,
    json={"target": "example.com"}
)

print(response.json())
```

## 项目结构

```
.
├── README.md           # 项目说明文档
├── .env.example        # 环境变量模板
├── .env                # 本地环境变量（不提交到 git）
├── requirements.txt    # Python 依赖
├── main.py            # 主程序入口
└── src/               # 源代码目录
    ├── __init__.py
    ├── crawler.py     # 爬虫核心模块
    └── api.py         # API 接口模块
```

## 注意事项

1. **安全**: 请确保 `.env` 文件已添加到 `.gitignore` 中
2. **防火墙**: 阿里云安全组需要开放相应端口（如 8000）
3. **Token 管理**: 定期更换 OpenClaw Token 以保证安全

## 联系方式

如有问题，请提交 Issue 或联系项目维护者。
