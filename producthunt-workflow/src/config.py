"""
配置管理模块
"""
import os
from dataclasses import dataclass
from typing import Optional
from dotenv import load_dotenv


@dataclass
class ProductHuntConfig:
    """Product Hunt 监控配置"""
    min_votes: int = 100                 # 最小投票数
    min_launch_date: str = "2026-01-01"  # 最早发布日期
    days_back: int = 30                  # 抓取最近 N 天的产品
    raw_data_path: str = "/data/producthunt/raw_products.json"


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
    base_url: str = "http://47.254.73.23:8080/api"
    
    @classmethod
    def from_env(cls) -> "OpenClawConfig":
        return cls(
            token=os.getenv("OPENCLAW_TOKEN", ""),
            base_url=os.getenv("OPENCLAW_BASE_URL", "http://47.254.73.23:8080/api")
        )


# 表头映射 (飞书多维表格字段名)
TABLE_FIELDS = {
    "product_name": "产品名",
    "tagline": "标语",
    "description": "产品说明",
    "votes_count": "投票数",
    "comments_count": "评论数",
    "launch_date": "发布日期",
    "maker": "制作者",
    "topics": "话题标签",
    "product_url": "产品链接",
    "thumbnail_url": "产品图片",
    "background": "履历",
    "funding_history": "融资历史"
}

# 反向映射
REVERSE_TABLE_FIELDS = {v: k for k, v in TABLE_FIELDS.items()}
