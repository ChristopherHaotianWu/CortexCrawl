"""
配置管理模块
"""
import os
from dataclasses import dataclass
from typing import Optional
from dotenv import load_dotenv


@dataclass
class KickstarterConfig:
    """Kickstarter 监控配置"""
    min_funding_amount: int = 500000
    min_launch_date: str = "2026-01-01"
    raw_data_path: str = "/data/kickstarter/raw_projects.json"


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

# 反向映射
REVERSE_TABLE_FIELDS = {v: k for k, v in TABLE_FIELDS.items()}
