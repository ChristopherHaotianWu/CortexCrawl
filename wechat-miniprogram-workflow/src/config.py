"""
配置管理模块
"""
import os
from dataclasses import dataclass
from typing import Optional
from dotenv import load_dotenv


@dataclass
class WechatMiniProgramConfig:
    """微信小程序监控配置"""
    min_monthly_active_users: int = 10000   # 最小月活跃用户数
    max_pages: int = 20                      # 最大抓取页数 (增量)
    raw_data_path: str = "/data/wechat-miniprogram/raw_miniprograms.json"


@dataclass
class FeishuConfig:
    """飞书 API 配置"""
    app_id: str = ""
    app_secret: str = ""
    base_id: str = ""           # 多维表格 ID
    table_id: str = ""          # 表格 ID
    webhook_url: str = ""       # 机器人 Webhook URL

    @classmethod
    def from_env(cls) -> "FeishuConfig":
        load_dotenv()
        return cls(
            app_id=os.getenv("FEISHU_APP_ID", ""),
            app_secret=os.getenv("FEISHU_APP_SECRET", ""),
            base_id=os.getenv("FEISHU_BASE_ID", ""),
            table_id=os.getenv("FEISHU_TABLE_ID", ""),
            webhook_url=os.getenv("FEISHU_WEBHOOK_URL", "")
        )


@dataclass
class OpenClawConfig:
    """OpenClaw 配置"""
    token: str = ""
    base_url: str = "http://localhost:15970"

    @classmethod
    def from_env(cls) -> "OpenClawConfig":
        return cls(
            token=os.getenv("OPENCLAW_TOKEN", ""),
            base_url=os.getenv("OPENCLAW_BASE_URL", "http://localhost:15970")
        )


# 表头映射 (飞书多维表格字段名)
TABLE_FIELDS = {
    "name": "小程序名称",
    "category": "分类",
    "description": "简介",
    "developer": "开发者",
    "monthly_active_users": "月活用户数",
    "daily_active_users": "日均活跃用户",
    "rating": "评分",
    "release_date": "上线日期",
    "app_id": "小程序ID",
    "cover_url": "封面图",
    "tags": "标签",
    "miniprogram_url": "小程序链接",
    "background": "履历",
    "funding_history": "融资历史"
}

# 反向映射
REVERSE_TABLE_FIELDS = {v: k for k, v in TABLE_FIELDS.items()}
