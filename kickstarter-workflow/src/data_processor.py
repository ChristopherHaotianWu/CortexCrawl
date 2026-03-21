"""
数据处理核心模块
实现"去重但更新金额"的核心逻辑
"""
import json
from typing import List, Dict, Any, Tuple, Optional
from dataclasses import dataclass, asdict
from datetime import datetime
import logging

from config import TABLE_FIELDS

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def _to_float(value, default: float = 0.0) -> float:
    try:
        return float(value or 0)
    except (ValueError, TypeError):
        return default


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
class Project:
    """Kickstarter 项目数据模型"""
    id: str                           # 项目唯一 ID
    product_name: str                 # 产品名
    country: str                      # 国家
    company: str                      # 公司
    category: str                     # 标签
    description: str                  # 产品说明
    funding_amount: float            # 众筹金额/美金
    backers_count: int               # 众筹人数
    launch_date: str                 # 众筹开始时间
    founder: str                     # 创始人
    project_url: str                 # 项目链接
    background: str = ""             # 履历 (手动补充)
    funding_history: str = ""        # 融资历史 (手动补充)
    
    @classmethod
    def from_raw(cls, raw_data: Dict[str, Any]) -> "Project":
        """从原始数据创建 Project 对象"""
        return cls(
            id=raw_data.get("id", ""),
            product_name=raw_data.get("产品名", ""),
            country=raw_data.get("国家", ""),
            company=raw_data.get("公司", ""),
            category=raw_data.get("标签", ""),
            description=raw_data.get("产品说明", ""),
            funding_amount=_to_float(raw_data.get("众筹金额_美金", 0)),
            backers_count=_to_int(raw_data.get("众筹人数", 0)),
            launch_date=raw_data.get("众筹开始时间", ""),
            founder=raw_data.get("创始人", ""),
            project_url=raw_data.get("项目链接", ""),
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
            TABLE_FIELDS["country"]: self.country,
            TABLE_FIELDS["company"]: self.company,
            TABLE_FIELDS["category"]: self.category,
            TABLE_FIELDS["description"]: self.description,
            TABLE_FIELDS["funding_amount"]: self.funding_amount,
            TABLE_FIELDS["backers_count"]: self.backers_count,
            TABLE_FIELDS["founder"]: self.founder,
            TABLE_FIELDS["project_url"]: {
                "text": self.product_name or "查看项目",
                "link": self.project_url
            } if self.project_url else "",
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
    
    def get_update_fields(self, old_amount: float, old_backers: int) -> Dict[str, Any]:
        """
        获取需要更新的字段
        只返回发生变化的字段
        """
        updates = {}
        if self.funding_amount != old_amount:
            updates[TABLE_FIELDS["funding_amount"]] = self.funding_amount
        if self.backers_count != old_backers:
            updates[TABLE_FIELDS["backers_count"]] = self.backers_count
        return updates


@dataclass
class ProcessingResult:
    """处理结果"""
    new_projects: List[Project]                    # 新增项目
    updated_projects: List[Dict[str, Any]]         # 更新项目 (包含变更详情)
    unchanged_count: int                           # 未变更项目数
    errors: List[str]                              # 错误信息
    
    def summary(self) -> str:
        """生成处理摘要"""
        return (
            f"处理完成: 新增 {len(self.new_projects)} 个项目, "
            f"更新 {len(self.updated_projects)} 个项目, "
            f"未变更 {self.unchanged_count} 个项目"
        )


class DataProcessor:
    """
    数据处理器
    核心逻辑: 去重但更新金额
    """
    
    def __init__(self):
        # 内存中的项目缓存: {project_id: Project}
        self.existing_projects: Dict[str, Dict[str, Any]] = {}
    
    def load_existing_data(self, records: List[Dict[str, Any]]) -> None:
        """
        加载现有数据
        
        Args:
            records: 从飞书多维表格获取的记录列表
        """
        self.existing_projects = {}
        
        for record in records:
            record_id = record.get("record_id")
            fields = record.get("fields", {})
            
            # 获取项目链接作为唯一标识
            project_url = fields.get(TABLE_FIELDS["project_url"], {})
            if isinstance(project_url, dict):
                project_url = project_url.get("link", "")
            
            if project_url:
                # 使用 URL 作为唯一键
                self.existing_projects[project_url] = {
                    "record_id": record_id,
                    "fields": fields
                }
        
        logger.info(f"加载了 {len(self.existing_projects)} 条现有记录")
    
    def process_projects(
        self, 
        new_projects: List[Project]
    ) -> ProcessingResult:
        """
        处理新项目数据
        核心逻辑: 去重但更新金额和人数
        
        Args:
            new_projects: 从 Kickstarter 抓取的新项目列表
        
        Returns:
            ProcessingResult 包含新增、更新和未变更的项目信息
        """
        new_list: List[Project] = []
        updated_list: List[Dict[str, Any]] = []
        unchanged_count = 0
        errors: List[str] = []
        
        for project in new_projects:
            try:
                # 检查项目是否已存在
                existing = self.existing_projects.get(project.project_url)
                
                if existing is None:
                    # ========== 情况 1: 新项目 ==========
                    logger.info(f"🆕 新项目: {project.product_name}")
                    new_list.append(project)
                    
                else:
                    # ========== 情况 2: 已存在项目，检查更新 ==========
                    existing_fields = existing["fields"]
                    record_id = existing["record_id"]
                    
                    # 获取现有金额和人数
                    old_amount = existing_fields.get(TABLE_FIELDS["funding_amount"], 0)
                    old_backers = existing_fields.get(TABLE_FIELDS["backers_count"], 0)
                    
                    # 计算需要更新的字段
                    update_fields = project.get_update_fields(old_amount, old_backers)
                    
                    if update_fields:
                        # 有更新
                        amount_change = project.funding_amount - old_amount
                        backers_change = project.backers_count - old_backers
                        
                        updated_info = {
                            "record_id": record_id,
                            "fields": update_fields,
                            "project": project,
                            "changes": {
                                "amount_change": amount_change,
                                "backers_change": backers_change,
                                "amount_change_percent": (
                                    (amount_change / old_amount * 100) if old_amount > 0 else 0
                                )
                            }
                        }
                        updated_list.append(updated_info)
                        
                        logger.info(
                            f"📈 更新项目: {project.product_name}, "
                            f"金额变化: ${amount_change:,.0f} ({updated_info['changes']['amount_change_percent']:.1f}%)"
                        )
                    else:
                        # 无变化
                        unchanged_count += 1
                        
            except Exception as e:
                error_msg = f"处理项目 {project.product_name} 时出错: {e}"
                logger.error(error_msg)
                errors.append(error_msg)
        
        return ProcessingResult(
            new_projects=new_list,
            updated_projects=updated_list,
            unchanged_count=unchanged_count,
            errors=errors
        )
    
    def prepare_new_records(self, projects: List[Project]) -> List[Dict[str, Any]]:
        """准备新增记录"""
        return [p.to_feishu_fields() for p in projects]
    
    def prepare_update_records(
        self, 
        updated_projects: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """准备更新记录"""
        return [
            {
                "record_id": item["record_id"],
                "fields": item["fields"]
            }
            for item in updated_projects
        ]


def load_raw_projects(file_path: str) -> List[Project]:
    """
    从 JSON 文件加载原始项目数据
    
    Args:
        file_path: JSON 文件路径
    
    Returns:
        Project 对象列表
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        raw_projects = data.get("projects", [])
        projects = [Project.from_raw(p) for p in raw_projects]
        
        logger.info(f"从文件加载了 {len(projects)} 个项目")
        return projects
        
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
                "众筹金额/美金": 600000,
                "众筹人数": 1500,
                "项目链接": {"text": "查看", "link": "https://kickstarter.com/projects/a"}
            }
        },
        {
            "record_id": "rec_002",
            "fields": {
                "产品名": "示例产品 B",
                "众筹金额/美金": 800000,
                "众筹人数": 2000,
                "项目链接": {"text": "查看", "link": "https://kickstarter.com/projects/b"}
            }
        }
    ]
    processor.load_existing_data(existing_records)
    
    # 3. 准备新数据 (模拟从 Kickstarter 抓取)
    new_projects = [
        # 新项目
        Project(
            id="new_001",
            product_name="新产品 C",
            country="USA",
            company="NewCo",
            category="Technology",
            description="A revolutionary new product",
            funding_amount=750000,
            backers_count=3000,
            launch_date="2026-03-01",
            founder="John Doe",
            project_url="https://kickstarter.com/projects/c"
        ),
        # 已存在但需要更新的项目
        Project(
            id="existing_001",
            product_name="示例产品 A",
            country="USA",
            company="OldCo",
            category="Technology",
            description="An existing product",
            funding_amount=650000,  # 从 600000 更新
            backers_count=1800,      # 从 1500 更新
            launch_date="2026-02-01",
            founder="Jane Smith",
            project_url="https://kickstarter.com/projects/a"
        ),
        # 已存在且无变化的项目
        Project(
            id="existing_002",
            product_name="示例产品 B",
            country="UK",
            company="AnotherCo",
            category="Design",
            description="No changes",
            funding_amount=800000,  # 无变化
            backers_count=2000,      # 无变化
            launch_date="2026-02-15",
            founder="Bob Wilson",
            project_url="https://kickstarter.com/projects/b"
        )
    ]
    
    # 4. 处理数据
    result = processor.process_projects(new_projects)
    
    # 5. 输出结果
    print("\n" + "="*60)
    print(result.summary())
    print("="*60)
    
    print(f"\n🆕 新增项目 ({len(result.new_projects)}):")
    for p in result.new_projects:
        print(f"  - {p.product_name}: ${p.funding_amount:,.0f}")
    
    print(f"\n📈 更新项目 ({len(result.updated_projects)}):")
    for item in result.updated_projects:
        p = item["project"]
        changes = item["changes"]
        print(f"  - {p.product_name}:")
        print(f"    金额: +${changes['amount_change']:,.0f} ({changes['amount_change_percent']:.1f}%)")
        print(f"    人数: +{changes['backers_change']}")
