"""
数据处理核心模块
实现"去重但更新数据"的核心逻辑
"""
import json
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from datetime import datetime
import logging

from config import TABLE_FIELDS

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def _to_int(value, default: int = 0) -> int:
    try:
        return int(float(value or 0))
    except (ValueError, TypeError):
        return default


def _to_float(value, default: float = 0.0) -> float:
    try:
        return float(value or 0)
    except (ValueError, TypeError):
        return default


def _date_to_timestamp_ms(date_str: str) -> Optional[int]:
    """
    将日期字符串转换为毫秒时间戳 (飞书日期字段要求)

    支持格式:
    - ISO 8601: "2026-03-01T08:00:00.000Z"
    - 日期: "2026-03-01"
    - Unix 秒级时间戳 (数字字符串)
    """
    if not date_str:
        return None

    # 已经是数字 (秒级时间戳)
    try:
        ts = float(date_str)
        if ts > 1e12:  # 已经是毫秒
            return int(ts)
        return int(ts * 1000)
    except (ValueError, TypeError):
        pass

    # ISO 8601 格式
    for fmt in ("%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(date_str, fmt)
            return int(dt.timestamp() * 1000)
        except ValueError:
            continue

    logger.warning(f"无法解析日期: {date_str}，将返回 None")
    return None


@dataclass
class MiniProgram:
    """微信小程序数据模型"""
    id: str                             # 唯一 ID
    name: str                           # 小程序名称
    category: str                       # 分类
    description: str                    # 简介
    developer: str                      # 开发者/公司
    monthly_active_users: int           # 月活跃用户数
    daily_active_users: int             # 日均活跃用户数
    rating: float                       # 评分
    release_date: str                   # 上线日期
    app_id: str                         # 小程序 ID
    cover_url: str = ""                 # 封面图 URL
    tags: str = ""                      # 标签
    miniprogram_url: str = ""           # 小程序链接
    background: str = ""               # 履历 (手动补充)
    funding_history: str = ""          # 融资历史 (手动补充)

    @classmethod
    def from_raw(cls, raw_data: Dict[str, Any]) -> "MiniProgram":
        """从原始数据创建 MiniProgram 对象"""
        app_id = raw_data.get("小程序ID", "") or raw_data.get("id", "")
        miniprogram_url = raw_data.get("小程序链接", "")
        if not miniprogram_url and app_id:
            miniprogram_url = f"https://weixin.qq.com/r/{app_id}"

        return cls(
            id=raw_data.get("id", ""),
            name=raw_data.get("小程序名称", ""),
            category=raw_data.get("分类", ""),
            description=raw_data.get("简介", ""),
            developer=raw_data.get("开发者", ""),
            monthly_active_users=_to_int(raw_data.get("月活用户数", 0)),
            daily_active_users=_to_int(raw_data.get("日均活跃用户", 0)),
            rating=_to_float(raw_data.get("评分", 0.0)),
            release_date=raw_data.get("上线日期", ""),
            app_id=app_id,
            cover_url=raw_data.get("封面图", ""),
            tags=raw_data.get("标签", ""),
            miniprogram_url=miniprogram_url,
            background=raw_data.get("履历", ""),
            funding_history=raw_data.get("融资历史", "")
        )

    def to_feishu_fields(self) -> Dict[str, Any]:
        """
        转换为飞书多维表格字段格式

        字段类型对照 (飞书 API 要求):
        - 文本: 字符串
        - 数字: 数字
        - 日期: 毫秒时间戳
        - 超链接: {"text": "显示文本", "link": "URL"}
        """
        fields = {
            TABLE_FIELDS["name"]: self.name,
            TABLE_FIELDS["category"]: self.category,
            TABLE_FIELDS["description"]: self.description,
            TABLE_FIELDS["developer"]: self.developer,
            TABLE_FIELDS["monthly_active_users"]: self.monthly_active_users,
            TABLE_FIELDS["daily_active_users"]: self.daily_active_users,
            TABLE_FIELDS["rating"]: self.rating,
            TABLE_FIELDS["app_id"]: self.app_id,
            TABLE_FIELDS["cover_url"]: self.cover_url,
            TABLE_FIELDS["tags"]: self.tags,
            TABLE_FIELDS["miniprogram_url"]: {
                "text": self.name or "查看小程序",
                "link": self.miniprogram_url
            } if self.miniprogram_url else "",
            TABLE_FIELDS["background"]: self.background,
            TABLE_FIELDS["funding_history"]: self.funding_history
        }

        # 日期字段: 转换为毫秒时间戳
        release_ts = _date_to_timestamp_ms(self.release_date)
        if release_ts is not None:
            fields[TABLE_FIELDS["release_date"]] = release_ts
        else:
            fields[TABLE_FIELDS["release_date"]] = self.release_date

        return fields

    def get_update_fields(self, old_mau: int, old_dau: int) -> Dict[str, Any]:
        """
        获取需要更新的字段
        只返回发生变化的数值字段
        """
        updates = {}
        if self.monthly_active_users != old_mau:
            updates[TABLE_FIELDS["monthly_active_users"]] = self.monthly_active_users
        if self.daily_active_users != old_dau:
            updates[TABLE_FIELDS["daily_active_users"]] = self.daily_active_users
        return updates


@dataclass
class ProcessingResult:
    """处理结果"""
    new_miniprograms: List[MiniProgram]             # 新增小程序
    updated_miniprograms: List[Dict[str, Any]]      # 更新小程序 (包含变更详情)
    unchanged_count: int                            # 未变更小程序数
    errors: List[str]                               # 错误信息

    def summary(self) -> str:
        """生成处理摘要"""
        return (
            f"处理完成: 新增 {len(self.new_miniprograms)} 个小程序, "
            f"更新 {len(self.updated_miniprograms)} 个小程序, "
            f"未变更 {self.unchanged_count} 个小程序"
        )


class DataProcessor:
    """
    数据处理器
    核心逻辑: 去重但更新月活和日均活跃用户数
    """

    def __init__(self):
        # 内存中的小程序缓存: {app_id: MiniProgram}
        self.existing_miniprograms: Dict[str, Dict[str, Any]] = {}

    def load_existing_data(self, records: List[Dict[str, Any]]) -> None:
        """
        加载现有数据

        Args:
            records: 从飞书多维表格获取的记录列表
        """
        self.existing_miniprograms = {}

        for record in records:
            record_id = record.get("record_id")
            fields = record.get("fields", {})

            # 优先使用小程序链接作为唯一标识
            miniprogram_url = fields.get(TABLE_FIELDS["miniprogram_url"], {})
            if isinstance(miniprogram_url, dict):
                miniprogram_url = miniprogram_url.get("link", "")

            # 备用: 使用小程序 ID
            if not miniprogram_url:
                miniprogram_url = fields.get(TABLE_FIELDS["app_id"], "")

            if miniprogram_url:
                self.existing_miniprograms[miniprogram_url] = {
                    "record_id": record_id,
                    "fields": fields
                }

        logger.info(f"加载了 {len(self.existing_miniprograms)} 条现有记录")

    def _get_dedup_key(self, mp: MiniProgram) -> str:
        """获取去重键: 优先使用小程序链接，否则使用小程序 ID"""
        return mp.miniprogram_url or mp.app_id

    def process_miniprograms(
        self,
        new_miniprograms: List[MiniProgram]
    ) -> ProcessingResult:
        """
        处理新小程序数据
        核心逻辑: 去重但更新月活和日均活跃用户数

        Args:
            new_miniprograms: 从数据源抓取的新小程序列表

        Returns:
            ProcessingResult 包含新增、更新和未变更的小程序信息
        """
        new_list: List[MiniProgram] = []
        updated_list: List[Dict[str, Any]] = []
        unchanged_count = 0
        errors: List[str] = []

        for mp in new_miniprograms:
            try:
                dedup_key = self._get_dedup_key(mp)
                existing = self.existing_miniprograms.get(dedup_key)

                if existing is None:
                    # ========== 情况 1: 新小程序 ==========
                    logger.info(f"🆕 新小程序: {mp.name}")
                    new_list.append(mp)

                else:
                    # ========== 情况 2: 已存在，检查更新 ==========
                    existing_fields = existing["fields"]
                    record_id = existing["record_id"]

                    # 获取现有月活和日活数
                    old_mau = existing_fields.get(TABLE_FIELDS["monthly_active_users"], 0)
                    old_dau = existing_fields.get(TABLE_FIELDS["daily_active_users"], 0)

                    # 计算需要更新的字段
                    update_fields = mp.get_update_fields(old_mau, old_dau)

                    if update_fields:
                        mau_change = mp.monthly_active_users - old_mau

                        updated_info = {
                            "record_id": record_id,
                            "fields": update_fields,
                            "miniprogram": mp,
                            "changes": {
                                "mau_change": mau_change,
                                "dau_change": mp.daily_active_users - old_dau,
                                "mau_change_percent": (
                                    (mau_change / old_mau * 100) if old_mau > 0 else 0
                                )
                            }
                        }
                        updated_list.append(updated_info)

                        logger.info(
                            f"📈 更新小程序: {mp.name}, "
                            f"月活变化: +{mau_change} ({updated_info['changes']['mau_change_percent']:.1f}%)"
                        )
                    else:
                        # 无变化
                        unchanged_count += 1

            except Exception as e:
                error_msg = f"处理小程序 {mp.name} 时出错: {e}"
                logger.error(error_msg)
                errors.append(error_msg)

        return ProcessingResult(
            new_miniprograms=new_list,
            updated_miniprograms=updated_list,
            unchanged_count=unchanged_count,
            errors=errors
        )

    def prepare_new_records(self, miniprograms: List[MiniProgram]) -> List[Dict[str, Any]]:
        """准备新增记录"""
        return [mp.to_feishu_fields() for mp in miniprograms]

    def prepare_update_records(
        self,
        updated_miniprograms: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """准备更新记录"""
        return [
            {
                "record_id": item["record_id"],
                "fields": item["fields"]
            }
            for item in updated_miniprograms
        ]


def load_raw_miniprograms(file_path: str) -> List[MiniProgram]:
    """
    从 JSON 文件加载原始小程序数据

    Args:
        file_path: JSON 文件路径

    Returns:
        MiniProgram 对象列表
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        raw_miniprograms = data.get("miniprograms", [])
        miniprograms = [MiniProgram.from_raw(mp) for mp in raw_miniprograms]

        logger.info(f"从文件加载了 {len(miniprograms)} 个小程序")
        return miniprograms

    except Exception as e:
        logger.error(f"加载文件失败: {e}")
        raise


# ========== 使用示例 ==========
if __name__ == "__main__":
    """
    演示核心逻辑的使用方式
    """

    # 1. 创建处理器
    processor = DataProcessor()

    # 2. 加载现有数据 (模拟从飞书获取)
    existing_records = [
        {
            "record_id": "rec_001",
            "fields": {
                "小程序名称": "示例小程序 A",
                "月活用户数": 50000,
                "日均活跃用户": 5000,
                "小程序链接": {"text": "查看", "link": "https://weixin.qq.com/r/wx_app_a"}
            }
        },
        {
            "record_id": "rec_002",
            "fields": {
                "小程序名称": "示例小程序 B",
                "月活用户数": 120000,
                "日均活跃用户": 12000,
                "小程序链接": {"text": "查看", "link": "https://weixin.qq.com/r/wx_app_b"}
            }
        }
    ]
    processor.load_existing_data(existing_records)

    # 3. 准备新数据 (模拟从阿拉丁指数抓取)
    new_miniprograms = [
        # 新小程序
        MiniProgram(
            id="new_001",
            name="新小程序 C",
            category="工具",
            description="一个好用的工具小程序",
            developer="某科技公司",
            monthly_active_users=30000,
            daily_active_users=3000,
            rating=4.5,
            release_date="2026-01-15",
            app_id="wx_app_c",
            miniprogram_url="https://weixin.qq.com/r/wx_app_c"
        ),
        # 已存在但需要更新的小程序
        MiniProgram(
            id="existing_001",
            name="示例小程序 A",
            category="生活服务",
            description="生活服务小程序",
            developer="某公司",
            monthly_active_users=65000,  # 从 50000 更新
            daily_active_users=6500,     # 从 5000 更新
            rating=4.2,
            release_date="2025-06-01",
            app_id="wx_app_a",
            miniprogram_url="https://weixin.qq.com/r/wx_app_a"
        ),
        # 已存在且无变化的小程序
        MiniProgram(
            id="existing_002",
            name="示例小程序 B",
            category="购物",
            description="购物小程序",
            developer="某购物公司",
            monthly_active_users=120000,  # 无变化
            daily_active_users=12000,     # 无变化
            rating=4.8,
            release_date="2025-03-01",
            app_id="wx_app_b",
            miniprogram_url="https://weixin.qq.com/r/wx_app_b"
        )
    ]

    # 4. 处理数据
    result = processor.process_miniprograms(new_miniprograms)

    # 5. 输出结果
    print("\n" + "="*60)
    print(result.summary())
    print("="*60)

    print(f"\n🆕 新增小程序 ({len(result.new_miniprograms)}):")
    for mp in result.new_miniprograms:
        print(f"  - {mp.name}: {mp.monthly_active_users:,} 月活")

    print(f"\n📈 更新小程序 ({len(result.updated_miniprograms)}):")
    for item in result.updated_miniprograms:
        mp = item["miniprogram"]
        changes = item["changes"]
        print(f"  - {mp.name}:")
        print(f"    月活: +{changes['mau_change']:,} ({changes['mau_change_percent']:.1f}%)")
        print(f"    日活: +{changes['dau_change']:,}")
