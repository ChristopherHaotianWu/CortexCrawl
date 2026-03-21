#!/bin/bash
#
# Kickstarter 全量同步脚本
# 一键执行: 全量抓取 → 对比 diff → 同步飞书 → 发送通知
#
# 用法:
#   ./run-full-sync.sh          # 全量拉取 + 同步
#   ./run-full-sync.sh --test   # 全量拉取 + 仅看 diff (不写入飞书)
#

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
LOG_PREFIX="[Kickstarter Full-Sync]"

echo "$LOG_PREFIX 开始全量同步 $(date '+%Y-%m-%d %H:%M:%S')"

# Step 1: 全量抓取
echo "$LOG_PREFIX Step 1/2: 执行全量数据抓取..."
node "$SCRIPT_DIR/openclaw/fetch-kickstarter.js" --full

if [ $? -ne 0 ]; then
  echo "$LOG_PREFIX 全量抓取失败，终止流程"
  exit 1
fi

# Step 2: 处理数据 (diff + 同步)
echo "$LOG_PREFIX Step 2/2: 处理数据 (diff + 同步飞书)..."

# 激活 Python 虚拟环境 (服务器部署路径)
if [ -f "$SCRIPT_DIR/venv/bin/activate" ]; then
  source "$SCRIPT_DIR/venv/bin/activate"
fi

# 透传额外参数 (如 --test)
python "$SCRIPT_DIR/src/main.py" "$@"

echo "$LOG_PREFIX 全量同步完成 $(date '+%Y-%m-%d %H:%M:%S')"
