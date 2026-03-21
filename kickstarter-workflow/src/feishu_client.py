"""
飞书 API 客户端
支持多维表格操作和机器人消息推送
"""
import time
import requests
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
import logging

from config import FeishuConfig, TABLE_FIELDS

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

_RETRYABLE_STATUS = {429, 500, 502, 503, 504}


class FeishuClient:
    """飞书 API 客户端"""

    BASE_URL = "https://open.feishu.cn/open-apis"

    def __init__(self, config: Optional[FeishuConfig] = None):
        self.config = config or FeishuConfig.from_env()
        self._access_token: Optional[str] = None
        self._token_expire_time: Optional[datetime] = None
        self._session = requests.Session()

    def _request(self, method: str, url: str, max_retries: int = 3, **kwargs) -> requests.Response:
        """带指数退避重试的 HTTP 请求"""
        for attempt in range(max_retries):
            try:
                response = self._session.request(method, url, timeout=30, **kwargs)
                if response.status_code in _RETRYABLE_STATUS and attempt < max_retries - 1:
                    wait = 2 ** attempt
                    logger.warning(f"HTTP {response.status_code}，{wait}s 后重试 ({attempt + 1}/{max_retries})")
                    time.sleep(wait)
                    continue
                response.raise_for_status()
                return response
            except (requests.ConnectionError, requests.Timeout) as e:
                if attempt < max_retries - 1:
                    wait = 2 ** attempt
                    logger.warning(f"请求异常: {e}，{wait}s 后重试 ({attempt + 1}/{max_retries})")
                    time.sleep(wait)
                else:
                    raise

    def _get_access_token(self) -> str:
        """获取飞书访问令牌 (带缓存)"""
        if self._access_token and self._token_expire_time:
            if datetime.now() < self._token_expire_time:
                return self._access_token

        url = f"{self.BASE_URL}/auth/v3/tenant_access_token/internal"
        data = {
            "app_id": self.config.app_id,
            "app_secret": self.config.app_secret
        }

        try:
            response = self._request("POST", url, headers={"Content-Type": "application/json"}, json=data)
            result = response.json()

            if result.get("code") != 0:
                raise Exception(f"获取 token 失败: {result}")

            self._access_token = result["tenant_access_token"]
            # Token 有效期 2 小时，提前 5 分钟刷新
            expires_in = result.get("expire", 7200) - 300
            self._token_expire_time = datetime.now() + timedelta(seconds=expires_in)

            return self._access_token

        except Exception as e:
            logger.error(f"获取飞书 access token 失败: {e}")
            raise

    def _get_headers(self) -> Dict[str, str]:
        """获取请求头"""
        return {
            "Authorization": f"Bearer {self._get_access_token()}",
            "Content-Type": "application/json"
        }

    def list_records(self, filter_formula: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        获取多维表格中的所有记录

        Args:
            filter_formula: 可选的筛选公式

        Returns:
            记录列表，每条记录包含 record_id 和 fields
        """
        url = f"{self.BASE_URL}/bitable/v1/apps/{self.config.base_id}/tables/{self.config.table_id}/records"

        all_records = []
        page_token = None

        while True:
            params = {"page_size": 500}
            if page_token:
                params["page_token"] = page_token
            if filter_formula:
                params["filter"] = filter_formula

            try:
                response = self._request("GET", url, headers=self._get_headers(), params=params)
                result = response.json()

                if result.get("code") != 0:
                    raise Exception(f"获取记录失败: {result}")

                items = result.get("data", {}).get("items", [])
                all_records.extend(items)

                has_more = result.get("data", {}).get("has_more", False)
                if not has_more:
                    break

                page_token = result.get("data", {}).get("page_token")

            except Exception as e:
                logger.error(f"获取记录失败: {e}")
                raise

        logger.info(f"共获取 {len(all_records)} 条记录")
        return all_records

    def create_records(self, records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        批量创建记录

        Args:
            records: 记录字段列表

        Returns:
            创建成功的记录列表
        """
        url = f"{self.BASE_URL}/bitable/v1/apps/{self.config.base_id}/tables/{self.config.table_id}/records/batch_create"

        # 飞书限制每次最多 500 条
        batch_size = 500
        created_records = []

        for i in range(0, len(records), batch_size):
            batch = records[i:i + batch_size]
            data = {"records": [{"fields": r} for r in batch]}

            try:
                response = self._request("POST", url, headers=self._get_headers(), json=data)
                result = response.json()

                if result.get("code") != 0:
                    raise Exception(f"批量创建记录失败: {result}")

                created = result.get("data", {}).get("records", [])
                created_records.extend(created)
                logger.info(f"成功创建 {len(created)} 条记录")

            except Exception as e:
                logger.error(f"批量创建记录失败: {e}")
                raise

        return created_records

    def update_records(self, records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        批量更新记录

        Args:
            records: 包含 record_id 和 fields 的记录列表
                [{"record_id": "xxx", "fields": {...}}, ...]

        Returns:
            更新成功的记录列表
        """
        url = f"{self.BASE_URL}/bitable/v1/apps/{self.config.base_id}/tables/{self.config.table_id}/records/batch_update"

        batch_size = 500
        updated_records = []

        for i in range(0, len(records), batch_size):
            batch = records[i:i + batch_size]
            data = {"records": batch}

            try:
                response = self._request("POST", url, headers=self._get_headers(), json=data)
                result = response.json()

                if result.get("code") != 0:
                    raise Exception(f"批量更新记录失败: {result}")

                updated = result.get("data", {}).get("records", [])
                updated_records.extend(updated)
                logger.info(f"成功更新 {len(updated)} 条记录")

            except Exception as e:
                logger.error(f"批量更新记录失败: {e}")
                raise

        return updated_records

    def send_webhook_card(self, card_data: Dict[str, Any]) -> bool:
        """
        通过 Webhook 发送卡片消息

        Args:
            card_data: 卡片消息数据

        Returns:
            是否发送成功
        """
        if not self.config.webhook_url:
            logger.warning("未配置 Webhook URL，跳过发送")
            return False

        try:
            response = self._request(
                "POST",
                self.config.webhook_url,
                headers={"Content-Type": "application/json"},
                json=card_data
            )
            result = response.json()

            if result.get("code") != 0:
                logger.error(f"发送卡片消息失败: {result}")
                return False

            logger.info("卡片消息发送成功")
            return True

        except Exception as e:
            logger.error(f"发送卡片消息失败: {e}")
            return False
