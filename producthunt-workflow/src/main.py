"""
Product Hunt 监控工作流主入口

每日执行流程:
1. 从 OpenClaw/Product Hunt 获取产品数据
2. 从飞书多维表格获取现有数据
3. 处理数据 (去重但更新)
4. 更新飞书表格
5. 发送飞书通知
"""
import os
import sys
import json
import argparse
import subprocess
from datetime import datetime
from typing import List, Dict, Any, Optional
import logging

from config import ProductHuntConfig, FeishuConfig, OpenClawConfig
from data_processor import DataProcessor, Product, load_raw_products
from feishu_client import FeishuClient

# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class ProductHuntMonitor:
    """Product Hunt 监控工作流编排器"""
    
    def __init__(self):
        self.config = ProductHuntConfig()
        self.feishu = FeishuClient()
        self.processor = DataProcessor()
        
    def fetch_data(self, full: bool = False) -> None:
        """
        调用 JS 抓取脚本获取数据

        Args:
            full: 是否全量拉取
        """
        script_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'openclaw', 'fetch-producthunt.js'
        )

        if not os.path.exists(script_path):
            raise FileNotFoundError(f"抓取脚本不存在: {script_path}")

        cmd = ['node', script_path]
        if full:
            cmd.append('--full')

        mode_label = '全量' if full else '增量'
        logger.info(f"📡 执行数据抓取 ({mode_label}模式): {' '.join(cmd)}")

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)

        if result.stdout:
            logger.info(f"抓取脚本输出:\n{result.stdout}")
        if result.stderr:
            logger.warning(f"抓取脚本错误输出:\n{result.stderr}")

        if result.returncode != 0:
            raise RuntimeError(f"抓取脚本执行失败 (exit code {result.returncode})")

        logger.info(f"✅ 数据抓取完成 ({mode_label}模式)")

    def run(self, raw_data_path: Optional[str] = None, full: bool = False) -> Dict[str, Any]:
        """
        执行完整工作流

        Args:
            raw_data_path: 原始数据文件路径
            full: 是否全量拉取 (先调用 JS 抓取脚本全量拉取数据)

        Returns:
            执行结果摘要
        """
        start_time = datetime.now()
        mode_label = '全量' if full else '增量'
        logger.info(f"🚀 Product Hunt 监控工作流启动 ({mode_label}模式)")

        try:
            # ========== Step 0: 全量模式下先抓取数据 ==========
            if full:
                self.fetch_data(full=True)

            # ========== Step 1: 加载新数据 ==========
            data_path = raw_data_path or self.config.raw_data_path
            logger.info(f"📂 加载数据: {data_path}")
            
            if not os.path.exists(data_path):
                raise FileNotFoundError(f"数据文件不存在: {data_path}")
            
            new_products = load_raw_products(data_path)
            
            if not new_products:
                logger.info("⚠️ 没有符合条件的产品")
                return self._build_result(
                    success=True,
                    message="没有符合条件的产品",
                    start_time=start_time
                )
            
            # ========== Step 2: 加载现有数据 ==========
            logger.info("📊 从飞书多维表格加载现有数据...")
            existing_records = self.feishu.list_records()
            self.processor.load_existing_data(existing_records)
            
            # ========== Step 3: 处理数据 ==========
            logger.info("🔄 处理数据 (去重但更新)...")
            result = self.processor.process_products(new_products)
            logger.info(result.summary())
            
            # ========== Step 4: 更新飞书表格 ==========
            # 4.1 创建新记录
            if result.new_products:
                logger.info(f"📝 创建 {len(result.new_products)} 条新记录...")
                new_records = self.processor.prepare_new_records(result.new_products)
                self.feishu.create_records(new_records)
            
            # 4.2 更新现有记录
            if result.updated_products:
                logger.info(f"📝 更新 {len(result.updated_products)} 条记录...")
                update_records = self.processor.prepare_update_records(result.updated_products)
                self.feishu.update_records(update_records)
            
            # ========== Step 5: 发送飞书通知 ==========
            logger.info("📤 发送飞书通知...")
            self._send_notification(result)
            
            # 返回结果
            return self._build_result(
                success=True,
                message="工作流执行成功",
                start_time=start_time,
                new_count=len(result.new_products),
                updated_count=len(result.updated_products),
                unchanged_count=result.unchanged_count,
                new_products=result.new_products,
                updated_products=result.updated_products
            )
            
        except Exception as e:
            logger.error(f"❌ 工作流执行失败: {e}", exc_info=True)
            return self._build_result(
                success=False,
                message=str(e),
                start_time=start_time
            )
    
    def _send_notification(self, result) -> bool:
        """发送飞书卡片通知"""
        try:
            card = self._build_feishu_card(result)
            return self.feishu.send_webhook_card(card)
        except Exception as e:
            logger.error(f"发送通知失败: {e}")
            return False
    
    def _build_feishu_card(self, result) -> Dict[str, Any]:
        """构建飞书卡片消息"""
        from datetime import datetime
        
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        
        # 新增产品列表
        new_products_text = ""
        if result.new_products:
            for p in result.new_products[:5]:  # 最多显示 5 个
                new_products_text += f"**{p.product_name}**\n"
                new_products_text += f"👍 {p.votes_count} 票 | 💬 {p.comments_count} 评论 | 🏷️ {p.topics}\n"
                new_products_text += f"[查看产品]({p.product_url})\n\n"
            
            if len(result.new_products) > 5:
                new_products_text += f"*...还有 {len(result.new_products) - 5} 个产品*"
        else:
            new_products_text = "今日无新增产品"
        
        # 更新产品列表
        updated_products_text = ""
        if result.updated_products:
            for item in result.updated_products[:5]:
                p = item["product"]
                changes = item["changes"]
                updated_products_text += f"**{p.product_name}**\n"
                updated_products_text += f"👍 {p.votes_count} 票 *(+{changes['votes_change']}, +{changes['votes_change_percent']:.1f}%)*\n"
                updated_products_text += f"💬 {p.comments_count} 评论 *(+{changes['comments_change']})*\n\n"
            
            if len(result.updated_products) > 5:
                updated_products_text += f"*...还有 {len(result.updated_products) - 5} 个产品*"
        else:
            updated_products_text = "今日无产品更新"
        
        # 统计卡片
        card = {
            "msg_type": "interactive",
            "card": {
                "config": {
                    "wide_screen_mode": True
                },
                "header": {
                    "template": "orange",
                    "title": {
                        "tag": "plain_text",
                        "content": f"🔥 Product Hunt 监控日报 ({now})"
                    }
                },
                "elements": [
                    # 统计概览
                    {
                        "tag": "div",
                        "text": {
                            "tag": "lark_md",
                            "content": f"**📈 今日统计**\n\n"
                                       f"🆕 新增产品: **{len(result.new_products)}**\n"
                                       f"📈 更新产品: **{len(result.updated_products)}**\n"
                                       f"➖ 未变更: **{result.unchanged_count}**"
                        }
                    },
                    {
                        "tag": "hr"
                    },
                    # 新增产品
                    {
                        "tag": "div",
                        "text": {
                            "tag": "lark_md",
                            "content": f"**🆕 新增热门产品**\n\n{new_products_text}"
                        }
                    },
                    {
                        "tag": "hr"
                    },
                    # 更新产品
                    {
                        "tag": "div",
                        "text": {
                            "tag": "lark_md",
                            "content": f"**📈 产品热度更新**\n\n{updated_products_text}"
                        }
                    },
                    {
                        "tag": "hr"
                    },
                    # 底部按钮
                    {
                        "tag": "action",
                        "actions": [
                            {
                                "tag": "button",
                                "text": {
                                    "tag": "plain_text",
                                    "content": "📋 查看完整数据"
                                },
                                "type": "primary",
                                "url": "https://www.feishu.cn/base/xxx"  # 替换为实际链接
                            },
                            {
                                "tag": "button",
                                "text": {
                                    "tag": "plain_text",
                                    "content": "🔍 浏览 Product Hunt"
                                },
                                "type": "default",
                                "url": "https://www.producthunt.com"
                            }
                        ]
                    }
                ]
            }
        }
        
        return card
    
    def _build_result(
        self,
        success: bool,
        message: str,
        start_time: datetime,
        **kwargs
    ) -> Dict[str, Any]:
        """构建执行结果"""
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        
        return {
            "success": success,
            "message": message,
            "timestamp": end_time.isoformat(),
            "duration_seconds": duration,
            **kwargs
        }


def main():
    """命令行入口"""
    parser = argparse.ArgumentParser(description='Product Hunt 监控工作流')
    parser.add_argument(
        '--data-path',
        type=str,
        help='原始数据文件路径 (JSON)'
    )
    parser.add_argument(
        '--test',
        action='store_true',
        help='测试模式 (不实际更新数据)'
    )
    parser.add_argument(
        '--full',
        action='store_true',
        help='全量拉取模式 (先调用抓取脚本全量拉取数据，再处理入库)'
    )

    args = parser.parse_args()

    # 创建工作流实例
    monitor = ProductHuntMonitor()

    # 执行
    result = monitor.run(raw_data_path=args.data_path, full=args.full)
    
    # 输出结果
    print(json.dumps(result, indent=2, default=str))
    
    # 返回退出码
    sys.exit(0 if result["success"] else 1)


if __name__ == "__main__":
    main()
