"""
数据处理核心模块
实现"去重但更新数据"的核心逻辑
"""
import json
from typing import List, Dict, Any, Tuple, Optional
from dataclasses import dataclass, asdict
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

    logger.warning(f"无法解析日期: {date_str}，将原样传递")
    return None


@dataclass
class Product:
    """Product Hunt 产品数据模型"""
    id: str                           # 产品唯一 ID
    product_name: str                 # 产品名
    tagline: str                      # 标语
    description: str                  # 产品说明
    votes_count: int                 # 投票数
    comments_count: int              # 评论数
    launch_date: str                 # 发布日期
    maker: str                       # 制作者
    topics: str                      # 话题标签
    product_url: str                 # 产品链接
    thumbnail_url: str = ""          # 产品图片
    background: str = ""             # 履历 (手动补充)
    funding_history: str = ""        # 融资历史 (手动补充)
    
    @classmethod
    def from_raw(cls, raw_data: Dict[str, Any]) -> "Product":
        """从原始数据创建 Product 对象"""
        return cls(
            id=raw_data.get("id", ""),
            product_name=raw_data.get("产品名", ""),
            tagline=raw_data.get("标语", ""),
            description=raw_data.get("产品说明", ""),
            votes_count=_to_int(raw_data.get("投票数", 0)),
            comments_count=_to_int(raw_data.get("评论数", 0)),
            launch_date=raw_data.get("发布日期", ""),
            maker=raw_data.get("制作者", ""),
            topics=raw_data.get("话题标签", ""),
            product_url=raw_data.get("产品链接", ""),
            thumbnail_url=raw_data.get("产品图片", ""),
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
            TABLE_FIELDS["product_name"]: self.product_name,
            TABLE_FIELDS["tagline"]: self.tagline,
            TABLE_FIELDS["description"]: self.description,
            TABLE_FIELDS["votes_count"]: self.votes_count,
            TABLE_FIELDS["comments_count"]: self.comments_count,
            TABLE_FIELDS["maker"]: self.maker,
            TABLE_FIELDS["topics"]: self.topics,
            TABLE_FIELDS["product_url"]: {
                "text": self.product_name or "查看产品",
                "link": self.product_url
            } if self.product_url else "",
            TABLE_FIELDS["thumbnail_url"]: self.thumbnail_url,
            TABLE_FIELDS["background"]: self.background,
            TABLE_FIELDS["funding_history"]: self.funding_history
        }

        # 日期字段: 转换为毫秒时间戳
        launch_ts = _date_to_timestamp_ms(self.launch_date)
        if launch_ts is not None:
            fields[TABLE_FIELDS["launch_date"]] = launch_ts
        else:
            fields[TABLE_FIELDS["launch_date"]] = self.launch_date

        return fields
    
    def get_update_fields(self, old_votes: int, old_comments: int) -> Dict[str, Any]:
        """
        获取需要更新的字段
        只返回发生变化的字段
        """
        updates = {}
        if self.votes_count != old_votes:
            updates[TABLE_FIELDS["votes_count"]] = self.votes_count
        if self.comments_count != old_comments:
            updates[TABLE_FIELDS["comments_count"]] = self.comments_count
        return updates


@dataclass
class ProcessingResult:
    """处理结果"""
    new_products: List[Product]                    # 新增产品
    updated_products: List[Dict[str, Any]]         # 更新产品 (包含变更详情)
    unchanged_count: int                           # 未变更产品数
    errors: List[str]                              # 错误信息
    
    def summary(self) -> str:
        """生成处理摘要"""
        return (
            f"处理完成: 新增 {len(self.new_products)} 个产品, "
            f"更新 {len(self.updated_products)} 个产品, "
            f"未变更 {self.unchanged_count} 个产品"
        )


class DataProcessor:
    """
    数据处理器
    核心逻辑: 去重但更新投票数和评论数
    """
    
    def __init__(self):
        # 内存中的产品缓存: {product_url: Product}
        self.existing_products: Dict[str, Dict[str, Any]] = {}
    
    def load_existing_data(self, records: List[Dict[str, Any]]) -> None:
        """
        加载现有数据
        
        Args:
            records: 从飞书多维表格获取的记录列表
        """
        self.existing_products = {}
        
        for record in records:
            record_id = record.get("record_id")
            fields = record.get("fields", {})
            
            # 获取产品链接作为唯一标识
            product_url = fields.get(TABLE_FIELDS["product_url"], {})
            if isinstance(product_url, dict):
                product_url = product_url.get("link", "")
            
            if product_url:
                # 使用 URL 作为唯一键
                self.existing_products[product_url] = {
                    "record_id": record_id,
                    "fields": fields
                }
        
        logger.info(f"加载了 {len(self.existing_products)} 条现有记录")
    
    def process_products(
        self, 
        new_products: List[Product]
    ) -> ProcessingResult:
        """
        处理新产品数据
        核心逻辑: 去重但更新投票数和评论数
        
        Args:
            new_products: 从 Product Hunt 抓取的新产品列表
        
        Returns:
            ProcessingResult 包含新增、更新和未变更的产品信息
        """
        new_list: List[Product] = []
        updated_list: List[Dict[str, Any]] = []
        unchanged_count = 0
        errors: List[str] = []
        
        for product in new_products:
            try:
                # 检查产品是否已存在
                existing = self.existing_products.get(product.product_url)
                
                if existing is None:
                    # ========== 情况 1: 新产品 ==========
                    logger.info(f"🆕 新产品: {product.product_name}")
                    new_list.append(product)
                    
                else:
                    # ========== 情况 2: 已存在产品，检查更新 ==========
                    existing_fields = existing["fields"]
                    record_id = existing["record_id"]
                    
                    # 获取现有投票数和评论数
                    old_votes = existing_fields.get(TABLE_FIELDS["votes_count"], 0)
                    old_comments = existing_fields.get(TABLE_FIELDS["comments_count"], 0)
                    
                    # 计算需要更新的字段
                    update_fields = product.get_update_fields(old_votes, old_comments)
                    
                    if update_fields:
                        # 有更新
                        votes_change = product.votes_count - old_votes
                        comments_change = product.comments_count - old_comments
                        
                        updated_info = {
                            "record_id": record_id,
                            "fields": update_fields,
                            "product": product,
                            "changes": {
                                "votes_change": votes_change,
                                "comments_change": comments_change,
                                "votes_change_percent": (
                                    (votes_change / old_votes * 100) if old_votes > 0 else 0
                                )
                            }
                        }
                        updated_list.append(updated_info)
                        
                        logger.info(
                            f"📈 更新产品: {product.product_name}, "
                            f"投票变化: +{votes_change} ({updated_info['changes']['votes_change_percent']:.1f}%)"
                        )
                    else:
                        # 无变化
                        unchanged_count += 1
                        
            except Exception as e:
                error_msg = f"处理产品 {product.product_name} 时出错: {e}"
                logger.error(error_msg)
                errors.append(error_msg)
        
        return ProcessingResult(
            new_products=new_list,
            updated_products=updated_list,
            unchanged_count=unchanged_count,
            errors=errors
        )
    
    def prepare_new_records(self, products: List[Product]) -> List[Dict[str, Any]]:
        """准备新增记录"""
        return [p.to_feishu_fields() for p in products]
    
    def prepare_update_records(
        self, 
        updated_products: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """准备更新记录"""
        return [
            {
                "record_id": item["record_id"],
                "fields": item["fields"]
            }
            for item in updated_products
        ]


def load_raw_products(file_path: str) -> List[Product]:
    """
    从 JSON 文件加载原始产品数据
    
    Args:
        file_path: JSON 文件路径
    
    Returns:
        Product 对象列表
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        raw_products = data.get("products", [])
        products = [Product.from_raw(p) for p in raw_products]
        
        logger.info(f"从文件加载了 {len(products)} 个产品")
        return products
        
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
                "产品名": "示例产品 A",
                "投票数": 150,
                "评论数": 25,
                "产品链接": {"text": "查看", "link": "https://www.producthunt.com/products/a"}
            }
        },
        {
            "record_id": "rec_002",
            "fields": {
                "产品名": "示例产品 B",
                "投票数": 300,
                "评论数": 50,
                "产品链接": {"text": "查看", "link": "https://www.producthunt.com/products/b"}
            }
        }
    ]
    processor.load_existing_data(existing_records)
    
    # 3. 准备新数据 (模拟从 Product Hunt 抓取)
    new_products = [
        # 新产品
        Product(
            id="new_001",
            product_name="新产品 C",
            tagline="A revolutionary new product",
            description="Detailed description here",
            votes_count=200,
            comments_count=40,
            launch_date="2026-03-01",
            maker="John Doe",
            topics="AI, Productivity",
            product_url="https://www.producthunt.com/products/c"
        ),
        # 已存在但需要更新的产品
        Product(
            id="existing_001",
            product_name="示例产品 A",
            tagline="Existing product tagline",
            description="Existing description",
            votes_count=180,  # 从 150 更新
            comments_count=30,  # 从 25 更新
            launch_date="2026-02-01",
            maker="Jane Smith",
            topics="SaaS",
            product_url="https://www.producthunt.com/products/a"
        ),
        # 已存在且无变化的产品
        Product(
            id="existing_002",
            product_name="示例产品 B",
            tagline="No changes",
            description="No changes",
            votes_count=300,  # 无变化
            comments_count=50,  # 无变化
            launch_date="2026-02-15",
            maker="Bob Wilson",
            topics="Design",
            product_url="https://www.producthunt.com/products/b"
        )
    ]
    
    # 4. 处理数据
    result = processor.process_products(new_products)
    
    # 5. 输出结果
    print("\n" + "="*60)
    print(result.summary())
    print("="*60)
    
    print(f"\n🆕 新增产品 ({len(result.new_products)}):")
    for p in result.new_products:
        print(f"  - {p.product_name}: {p.votes_count} 票")
    
    print(f"\n📈 更新产品 ({len(result.updated_products)}):")
    for item in result.updated_products:
        p = item["product"]
        changes = item["changes"]
        print(f"  - {p.product_name}:")
        print(f"    投票: +{changes['votes_change']} ({changes['votes_change_percent']:.1f}%)")
        print(f"    评论: +{changes['comments_change']}")
